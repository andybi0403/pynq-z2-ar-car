/* Original project code. Linux V4L2 mmap capture + pinned TurboJPEG BGRX ABI.
 * Each codec/camera handle is owned by one worker; Python CDLL releases the GIL.
 * Windows builds exercise codecs only and explicitly reject physical capture.
 */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <setjmp.h>
#include <jpeglib.h>
#include <jerror.h>
#include <turbojpeg.h>
#ifdef _WIN32
#define WV_API __declspec(dllexport)
#else
#define WV_API __attribute__((visibility("default")))
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>
#endif

typedef struct {
    tjhandle dec, enc;
    unsigned char *jpeg;
    unsigned long capacity;
    char error[256];
    void *decoder_state;
} Codec;
WV_API const char *wv_version(void) { return "car-video/2;libjpeg-turbo/" WV_TURBO_VERSION; }
typedef struct {
    struct jpeg_error_mgr base;
    jmp_buf failed;
    char *message;
    int padding_warnings;
} DecodeError;
static void decode_error(j_common_ptr decoder) {
    DecodeError *error=(DecodeError *)decoder->err;
    (*error->base.format_message)(decoder,error->message);
    longjmp(error->failed,1);
}
static void decode_message(j_common_ptr decoder,int level) {
    DecodeError *error=(DecodeError *)decoder->err;
    if(level>=0) return;
    /* C270 firmware emits surplus bytes before RST markers. Only this
       warning is recoverable here; missing data, bad codes, wrong markers,
       and all other warnings still fail the whole frame. Check EVERY warning,
       rather than accepting the last TurboJPEG error string alone. */
    if(error->base.msg_code==JWRN_EXTRANEOUS_DATA &&
       error->base.msg_parm.i[0]>=1 &&
       error->base.msg_parm.i[1]>=0xd0 && error->base.msg_parm.i[1]<=0xd7) {
        error->padding_warnings++;return;
    }
    decode_error(decoder);
}
typedef struct { struct jpeg_decompress_struct decoder; DecodeError error; } DecodeState;
static void destroy_decode_state(Codec *c) {
    DecodeState *state=(DecodeState *)c->decoder_state;
    if(state) { jpeg_destroy_decompress(&state->decoder);free(state);c->decoder_state=NULL; }
}
WV_API void *wv_codec_open(void) {
    Codec *c = (Codec *)calloc(1, sizeof(*c));
    if (!c) return NULL;
    c->dec = tjInitDecompress(); c->enc = tjInitCompress();
    c->capacity = tjBufSize(1280, 720, TJSAMP_444);
    c->jpeg = tjAlloc((int)c->capacity);
    if (!c->dec || !c->enc || !c->jpeg) {
        if(c->dec) tjDestroy(c->dec);
        if(c->enc) tjDestroy(c->enc);
        if(c->jpeg) tjFree(c->jpeg);
        free(c); return NULL;
    }
    return c;
}
WV_API const char *wv_codec_error(void *handle) { return handle ? ((Codec *)handle)->error : "codec is closed"; }
WV_API void wv_codec_close(void *handle) {
    Codec *c = (Codec *)handle;
    if (!c) return;
    destroy_decode_state(c);
    tjDestroy(c->dec); tjDestroy(c->enc); tjFree(c->jpeg); free(c);
}
WV_API int wv_decode(void *handle, const unsigned char *jpeg, unsigned long length,
                     unsigned char *bgrx, unsigned long output_length) {
    Codec *c=(Codec *)handle;
    struct jpeg_decompress_struct decoder;
    DecodeError error;
    if (!c || !jpeg || !bgrx || output_length != 1280UL*720*4 || length < 4) return -1;
    memset(&decoder,0,sizeof(decoder));memset(&error,0,sizeof(error));
    decoder.err=jpeg_std_error(&error.base);error.base.error_exit=decode_error;
    error.base.emit_message=decode_message;error.message=c->error;
    if(setjmp(error.failed)) { jpeg_destroy_decompress(&decoder);return -1; }
    jpeg_create_decompress(&decoder);jpeg_mem_src(&decoder,jpeg,length);
    jpeg_read_header(&decoder,TRUE);
    if(decoder.image_width!=1280 || decoder.image_height!=720) {
        snprintf(c->error,sizeof(c->error),"JPEG must be 1280x720, got %ux%u",decoder.image_width,decoder.image_height);
        jpeg_destroy_decompress(&decoder);return -1;
    }
    decoder.out_color_space=JCS_EXT_BGRX;decoder.dct_method=JDCT_ISLOW;
    jpeg_start_decompress(&decoder);
    while(decoder.output_scanline<decoder.output_height) {
        JSAMPROW row=bgrx+decoder.output_scanline*5120UL;
        jpeg_read_scanlines(&decoder,&row,1);
    }
    jpeg_finish_decompress(&decoder);jpeg_destroy_decompress(&decoder);
    return error.padding_warnings; /* ABI 2: >=0 completed; <0 rejected. */
}
/* Optional profile extension; the legacy entry point remains byte-compatible.
 * A failed reusable context is destroyed, so the following frame starts clean. */
WV_API int wv_decode_profile(void *handle,const unsigned char *jpeg,unsigned long length,
                            unsigned char *bgrx,unsigned long output_length,int fast,int reuse) {
    Codec *c=(Codec *)handle;DecodeState *state;int warnings;
    if(!c || !jpeg || !bgrx || output_length!=1280UL*720*4 || length<4 ||
       (fast!=0 && fast!=1) || (reuse!=0 && reuse!=1)) return -1;
    if(!reuse) destroy_decode_state(c);
    state=(DecodeState *)c->decoder_state;
    if(!state) {
        state=(DecodeState *)calloc(1,sizeof(*state));
        if(!state) { snprintf(c->error,sizeof(c->error),"decoder allocation failed");return -1; }
        c->decoder_state=state;
        state->decoder.err=jpeg_std_error(&state->error.base);
        state->error.base.error_exit=decode_error;state->error.base.emit_message=decode_message;
        state->error.message=c->error;
        if(setjmp(state->error.failed)) { destroy_decode_state(c);return -1; }
        jpeg_create_decompress(&state->decoder);
    }
    state->error.padding_warnings=0;
    if(setjmp(state->error.failed)) { destroy_decode_state(c);return -1; }
    jpeg_mem_src(&state->decoder,jpeg,length);jpeg_read_header(&state->decoder,TRUE);
    if(state->decoder.image_width!=1280 || state->decoder.image_height!=720) {
        snprintf(c->error,sizeof(c->error),"JPEG must be 1280x720");destroy_decode_state(c);return -1;
    }
    state->decoder.out_color_space=JCS_EXT_BGRX;
    state->decoder.dct_method=fast?JDCT_IFAST:JDCT_ISLOW;
    jpeg_start_decompress(&state->decoder);
    while(state->decoder.output_scanline<state->decoder.output_height) {
        JSAMPROW row=bgrx+state->decoder.output_scanline*5120UL;
        jpeg_read_scanlines(&state->decoder,&row,1);
    }
    jpeg_finish_decompress(&state->decoder);warnings=state->error.padding_warnings;
    if(!reuse) destroy_decode_state(c);
    return warnings;
}
WV_API int wv_encode_profile(void *handle, const unsigned char *bgrx, unsigned long length,
                     int quality, int subsampling, int accurate_dct,
                     const unsigned char **jpeg, unsigned long *jpeg_length) {
    Codec *c=(Codec *)handle; unsigned long size;
    if(!c || !bgrx || !jpeg || !jpeg_length || length!=1280UL*720*4 || quality<1 || quality>100 ||
       (subsampling!=TJSAMP_444 && subsampling!=TJSAMP_422 && subsampling!=TJSAMP_420) ||
       (accurate_dct!=0 && accurate_dct!=1)) return -1;
    size=c->capacity;
    if(tjCompress2(c->enc,bgrx,1280,5120,720,TJPF_BGRX,&c->jpeg,&size,subsampling,quality,
                   TJFLAG_NOREALLOC|(accurate_dct?0:TJFLAG_FASTDCT))<0) {
        snprintf(c->error,sizeof(c->error),"%s",tjGetErrorStr2(c->enc)); return -1;
    }
    *jpeg=c->jpeg; *jpeg_length=size; return 0;
}
WV_API int wv_encode(void *handle, const unsigned char *bgrx, unsigned long length,
                     int quality, const unsigned char **jpeg, unsigned long *jpeg_length) {
    return wv_encode_profile(handle,bgrx,length,quality,
        quality>=85?TJSAMP_444:TJSAMP_420,quality>=85,jpeg,jpeg_length);
}

typedef struct { uint32_t sequence, flags; uint64_t captured_ns; uint32_t width,height,fps_num,fps_den; } FrameInfo;
#ifndef _WIN32
typedef struct { void *address; size_t length; } Map;
typedef struct { int fd, streaming; unsigned count; Map maps[16]; uint32_t num,den; } Camera;
static int xi(int fd, unsigned long request, void *arg) {
    int r; do { r=ioctl(fd,request,arg); } while(r<0 && errno==EINTR); return r;
}
/* Measured C270 profile. Other cameras retain their own settings. Read back
 * every control and roll back on failure; do not silently run a partial profile.
 * WV_CAMERA_PROFILE=0 is reserved for explicit baseline comparisons. */
static int c270_profile(int fd, const char *card) {
    const uint32_t ids[]={V4L2_CID_CONTRAST,V4L2_CID_SHARPNESS,
                         V4L2_CID_POWER_LINE_FREQUENCY,V4L2_CID_EXPOSURE_AUTO_PRIORITY};
    const int values[]={36,32,V4L2_CID_POWER_LINE_FREQUENCY_50HZ,0};
    int old[4]; unsigned i,j;
    const char *profile=getenv("WV_CAMERA_PROFILE");
    if((profile && strcmp(profile,"0")==0) ||
       (!strstr(card,"0825") && !strstr(card,"C270"))) return 0;
    for(i=0;i<4;i++) {
        struct v4l2_control ctrl; memset(&ctrl,0,sizeof(ctrl));ctrl.id=ids[i];
        if(xi(fd,VIDIOC_G_CTRL,&ctrl)<0) return -1;
        old[i]=ctrl.value;
    }
    for(i=0;i<4;i++) {
        struct v4l2_control ctrl; memset(&ctrl,0,sizeof(ctrl));ctrl.id=ids[i];ctrl.value=values[i];
        if(xi(fd,VIDIOC_S_CTRL,&ctrl)<0 || xi(fd,VIDIOC_G_CTRL,&ctrl)<0 || ctrl.value!=values[i]) {
            int saved=errno?errno:EIO;
            for(j=0;j<4;j++) {ctrl.id=ids[j];ctrl.value=old[j];xi(fd,VIDIOC_S_CTRL,&ctrl);}
            errno=saved;return -1;
        }
    }
    return 0;
}
WV_API void wv_camera_close(void *handle) {
    Camera *c=(Camera *)handle; unsigned i; enum v4l2_buf_type type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if(!c) return;
    if(c->streaming) xi(c->fd,VIDIOC_STREAMOFF,&type);
    for(i=0;i<c->count;i++) if(c->maps[i].address && c->maps[i].address!=MAP_FAILED)
        munmap(c->maps[i].address,c->maps[i].length);
    if(c->fd>=0) close(c->fd);
    free(c);
}
WV_API void *wv_camera_open(const char *device, char *error, unsigned error_size) {
    Camera *c=(Camera *)calloc(1,sizeof(*c)); unsigned i; uint32_t caps;
    struct v4l2_capability cap; struct v4l2_format fmt; struct v4l2_streamparm parm;
    struct v4l2_requestbuffers req; enum v4l2_buf_type type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if(!c) return NULL;
    c->fd=-1;
    c->fd=open(device,O_RDWR|O_NONBLOCK|O_CLOEXEC);
    if(c->fd<0) goto fail;
    memset(&cap,0,sizeof(cap)); if(xi(c->fd,VIDIOC_QUERYCAP,&cap)<0) goto fail;
    caps=(cap.capabilities&V4L2_CAP_DEVICE_CAPS)?cap.device_caps:cap.capabilities;
    if(!(caps&V4L2_CAP_VIDEO_CAPTURE) || !(caps&V4L2_CAP_STREAMING)) { errno=ENOTSUP; goto fail; }
    if(c270_profile(c->fd,(const char *)cap.card)<0) goto fail;
    memset(&fmt,0,sizeof(fmt)); fmt.type=type;
    fmt.fmt.pix.width=1280;fmt.fmt.pix.height=720;fmt.fmt.pix.pixelformat=V4L2_PIX_FMT_MJPEG;
    fmt.fmt.pix.field=V4L2_FIELD_NONE;
    if(xi(c->fd,VIDIOC_S_FMT,&fmt)<0) goto fail;
    if(fmt.fmt.pix.width!=1280 || fmt.fmt.pix.height!=720 || fmt.fmt.pix.pixelformat!=V4L2_PIX_FMT_MJPEG) { errno=ENOTSUP;goto fail; }
    memset(&parm,0,sizeof(parm));parm.type=type;
    parm.parm.capture.timeperframe.numerator=1;parm.parm.capture.timeperframe.denominator=30;
    if(xi(c->fd,VIDIOC_S_PARM,&parm)<0 || xi(c->fd,VIDIOC_G_PARM,&parm)<0) goto fail;
    c->num=parm.parm.capture.timeperframe.numerator;c->den=parm.parm.capture.timeperframe.denominator;
    if(!c->num || (double)c->den/c->num<29.7 || (double)c->den/c->num>30.3) { errno=ENOTSUP;goto fail; }
    memset(&req,0,sizeof(req));req.count=4;req.type=type;req.memory=V4L2_MEMORY_MMAP;
    if(xi(c->fd,VIDIOC_REQBUFS,&req)<0) goto fail;
    if(req.count<2 || req.count>16) { errno=ENOBUFS;goto fail; }
    c->count=req.count;
    for(i=0;i<c->count;i++) {
        struct v4l2_buffer b; memset(&b,0,sizeof(b));b.type=type;b.memory=V4L2_MEMORY_MMAP;b.index=i;
        if(xi(c->fd,VIDIOC_QUERYBUF,&b)<0) goto fail;
        c->maps[i].length=b.length;
        c->maps[i].address=mmap(NULL,b.length,PROT_READ|PROT_WRITE,MAP_SHARED,c->fd,b.m.offset);
        if(c->maps[i].address==MAP_FAILED || xi(c->fd,VIDIOC_QBUF,&b)<0) goto fail;
    }
    if(xi(c->fd,VIDIOC_STREAMON,&type)<0) goto fail;
    c->streaming=1;return c;
fail:
    if(error && error_size) snprintf(error,error_size,"MJPEG 1280x720@30 negotiation: %s",strerror(errno));
    wv_camera_close(c);return NULL;
}
WV_API int wv_camera_read(void *handle,unsigned char *jpeg,unsigned capacity,FrameInfo *info,int timeout_ms) {
    Camera *c=(Camera *)handle;struct pollfd p;struct v4l2_buffer b;int r,valid;
    if(!c || !jpeg || !info || timeout_ms<0) return -1;
    p.fd=c->fd;p.events=POLLIN;p.revents=0;
    do {r=poll(&p,1,timeout_ms);} while(r<0 && errno==EINTR);
    if(r==0) return 0;
    if(r<0 || (p.revents&(POLLERR|POLLHUP|POLLNVAL))) return -1;
    memset(&b,0,sizeof(b));b.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;b.memory=V4L2_MEMORY_MMAP;
    if(xi(c->fd,VIDIOC_DQBUF,&b)<0) return errno==EAGAIN?0:-1;
    info->sequence=b.sequence;info->flags=b.flags;
    valid=b.index<c->count && b.bytesused>=4 && b.bytesused<=capacity &&
          b.bytesused<=c->maps[b.index].length && !(b.flags&V4L2_BUF_FLAG_ERROR);
    if(b.index>=c->count) return -1;
    if((b.flags&V4L2_BUF_FLAG_TIMESTAMP_MASK)!=V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC ||
       b.timestamp.tv_sec<0 || b.timestamp.tv_usec<0 || b.timestamp.tv_usec>=1000000) {
        xi(c->fd,VIDIOC_QBUF,&b);return -3;
    }
    if(valid) {
        memcpy(jpeg,c->maps[b.index].address,b.bytesused);
        info->sequence=b.sequence;info->flags=b.flags;
        info->captured_ns=(uint64_t)b.timestamp.tv_sec*1000000000ULL+(uint64_t)b.timestamp.tv_usec*1000ULL;
        info->width=1280;info->height=720;info->fps_num=c->num;info->fps_den=c->den;
    }
    r=(int)b.bytesused; /* QBUF may update descriptor fields; retain DQBUF length. */
    if(xi(c->fd,VIDIOC_QBUF,&b)<0) return -1;
    if(!valid) return -2;
    return r;
}
#else
WV_API void *wv_camera_open(const char *device,char *error,unsigned size) {
    (void)device;if(error && size) snprintf(error,size,"V4L2 capture requires Linux; Windows codec tests are not hardware evidence");return NULL;
}
WV_API void wv_camera_close(void *handle) { (void)handle; }
WV_API int wv_camera_read(void *h,unsigned char *j,unsigned n,FrameInfo *i,int t) {
    (void)h;(void)j;(void)n;(void)i;(void)t;return -1;
}
#endif
