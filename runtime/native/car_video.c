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
#include <pthread.h>
#endif

typedef struct {
    tjhandle dec, enc;
    unsigned char *jpeg;
    unsigned long capacity;
    char error[256];
    void *decoder_state;
    void *stripes[2];
    unsigned width,height,stride;
} Codec;
WV_API const char *wv_version(void) { return "car-video/3;libjpeg-turbo/" WV_TURBO_VERSION; }
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
    /* C270 also appends 1--3 bytes after the completed baseline scan before
     * EOI. Accept only this bounded trailer once every output row exists.
     * Entropy/marker errors inside the scan still reject the whole frame. */
    if(decoder->is_decompressor && error->base.msg_code==JWRN_EXTRANEOUS_DATA &&
       error->base.msg_parm.i[0]>=1 && error->base.msg_parm.i[0]<=3 &&
       error->base.msg_parm.i[1]==JPEG_EOI) {
        j_decompress_ptr state=(j_decompress_ptr)decoder;
        if(!state->progressive_mode && state->output_height>0 &&
           state->output_scanline==state->output_height) {
            error->padding_warnings++;return;
        }
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
    c->width=1280;c->height=720;c->stride=5120;
    return c;
}
WV_API const char *wv_codec_error(void *handle) { return handle ? ((Codec *)handle)->error : "codec is closed"; }
WV_API void wv_codec_close(void *handle) {
    Codec *c = (Codec *)handle;
    if (!c) return;
    for(int i=0;i<2;i++) if(c->stripes[i]) wv_codec_close(c->stripes[i]);
    destroy_decode_state(c);
    tjDestroy(c->dec); tjDestroy(c->enc); tjFree(c->jpeg); free(c);
}
WV_API int wv_codec_configure(void *handle,unsigned width,unsigned height) {
    Codec *c=(Codec *)handle;
    if(!c || !((width==1280 && height==720)||(width==640 && height==360)))return -1;
    destroy_decode_state(c);
    c->width=width;c->height=height;c->stride=width*4;
    return 0;
}
/* Optional full-resolution 720p decode extension.  Each independent context
 * decodes one 1280x360 restart-aligned 4:2:2 stripe.  The caller validates and
 * reconstructs the JPEG headers; the production frame remains 1280x720. */
WV_API int wv_codec_configure_region(void *handle,unsigned width,unsigned height) {
    Codec *c=(Codec *)handle;
    if(!c || width!=1280 || height!=360)return -1;
    destroy_decode_state(c);
    c->width=width;c->height=height;c->stride=width*4;
    return 0;
}
WV_API int wv_decode(void *handle, const unsigned char *jpeg, unsigned long length,
                     unsigned char *bgrx, unsigned long output_length) {
    Codec *c=(Codec *)handle;
    struct jpeg_decompress_struct decoder;
    DecodeError error;
    if (!c || !jpeg || !bgrx || output_length != (unsigned long)c->stride*c->height || length < 4) return -1;
    memset(&decoder,0,sizeof(decoder));memset(&error,0,sizeof(error));
    decoder.err=jpeg_std_error(&error.base);error.base.error_exit=decode_error;
    error.base.emit_message=decode_message;error.message=c->error;
    if(setjmp(error.failed)) { jpeg_destroy_decompress(&decoder);return -1; }
    jpeg_create_decompress(&decoder);jpeg_mem_src(&decoder,jpeg,length);
    jpeg_read_header(&decoder,TRUE);
    if(decoder.image_width!=c->width || decoder.image_height!=c->height) {
        snprintf(c->error,sizeof(c->error),"JPEG dimensions must match configured profile, got %ux%u",decoder.image_width,decoder.image_height);
        jpeg_destroy_decompress(&decoder);return -1;
    }
    decoder.out_color_space=JCS_EXT_BGRX;decoder.dct_method=JDCT_ISLOW;
    jpeg_start_decompress(&decoder);
    while(decoder.output_scanline<decoder.output_height) {
        JSAMPROW row=bgrx+decoder.output_scanline*c->stride;
        jpeg_read_scanlines(&decoder,&row,1);
    }
    jpeg_finish_decompress(&decoder);jpeg_destroy_decompress(&decoder);
    return error.padding_warnings; /* ABI 2: >=0 completed; <0 rejected. */
}
/* Optional profile extension; the legacy entry point remains byte-compatible.
 * A failed reusable context is destroyed, so the following frame starts clean. */
/* Decode flags: bit 0 IFAST DCT, bit 1 merged (non-fancy) chroma upsampling.
 * No spatial downscaling. Existing callers using flags 0/1 stay unchanged. */
WV_API int wv_decode_flags_supported(void) { return 3; }
WV_API int wv_decode_profile(void *handle,const unsigned char *jpeg,unsigned long length,
                            unsigned char *bgrx,unsigned long output_length,int fast,int reuse) {
    Codec *c=(Codec *)handle;DecodeState *state;int warnings;
    if(!c || !jpeg || !bgrx || output_length!=(unsigned long)c->stride*c->height || length<4 ||
       fast<0 || fast>3 || (reuse!=0 && reuse!=1)) return -1;
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
    if(state->decoder.image_width!=c->width || state->decoder.image_height!=c->height) {
        snprintf(c->error,sizeof(c->error),"JPEG dimensions must match configured profile");destroy_decode_state(c);return -1;
    }
    state->decoder.out_color_space=JCS_EXT_BGRX;
    state->decoder.dct_method=(fast&1)?JDCT_IFAST:JDCT_ISLOW;
    state->decoder.do_fancy_upsampling=(fast&2)?FALSE:TRUE;
    jpeg_start_decompress(&state->decoder);
    while(state->decoder.output_scanline<state->decoder.output_height) {
        JSAMPROW row=bgrx+state->decoder.output_scanline*c->stride;
        jpeg_read_scanlines(&state->decoder,&row,1);
    }
    jpeg_finish_decompress(&state->decoder);warnings=state->error.padding_warnings;
    if(!reuse) destroy_decode_state(c);
    return warnings;
}
typedef struct {
    Codec *codec;const unsigned char *jpeg;unsigned long length;
    unsigned char *output;int fast,result;
} StripeJob;
static void *decode_stripe_job(void *arg) {
    StripeJob *job=(StripeJob *)arg;
    job->result=wv_decode_profile(job->codec,job->jpeg,job->length,job->output,1280UL*360*4,job->fast,1);
    return NULL;
}
/* C-side marker scanning avoids a Python per-byte loop on the ARM. The
 * midpoint is a restart boundary, with unchanged entropy and 4:2:2 pixels.
 * Invalid marker counts/sequences fail; unsupported formats decode normally.
 * The native worker is always joined before caller-owned memory is returned. */
WV_API int wv_decode_parallel(void *handle,const unsigned char *jpeg,unsigned long length,
                             unsigned char *bgrx,unsigned long output_length,int fast) {
    Codec *c=(Codec *)handle;unsigned long i=2,sof=0,sos=0,begin=0,end=0;
    unsigned restart=0,seen=0,boundary=0,expected=0;int supported=1;
    static const unsigned char frame_spec[15]={8,2,208,5,0,3,1,33,0,2,17,1,3,17,1};
    static const unsigned char scan_spec[10]={3,1,0,2,17,3,17,0,63,0};
    if(!c || !jpeg || !bgrx || length<4 || output_length!=1280UL*720*4 ||
       c->width!=1280 || c->height!=720 || (fast!=0 && fast!=1))return -1;
    if(jpeg[0]!=255 || jpeg[1]!=216 || jpeg[length-2]!=255 || jpeg[length-1]!=217)goto invalid;
    while(i<length-3) {
        unsigned marker,n;
        if(jpeg[i]!=255)goto invalid;
        marker=jpeg[i+1];if(marker==255){i++;continue;}
        if(marker==0 || (marker>=0xd0 && marker<=0xd9))goto invalid;
        n=((unsigned)jpeg[i+2]<<8)|jpeg[i+3];
        if(n<2 || n>length-i-2)goto invalid;
        if(marker==0xc0) {
            if(sof)goto invalid;
            sof=i;if(n!=17 || memcmp(jpeg+i+4,frame_spec,15))supported=0;
        } else if((marker>=0xc1 && marker<=0xc3) || (marker>=0xc5 && marker<=0xc7) ||
                  (marker>=0xc9 && marker<=0xcb) || (marker>=0xcd && marker<=0xcf)) supported=0;
        if(marker==0xdd) {
            if(restart || n!=4)goto invalid;
            restart=((unsigned)jpeg[i+4]<<8)|jpeg[i+5];
        }
        if(marker==0xda) {
            if(n!=12 || memcmp(jpeg+i+4,scan_spec,10))supported=0;
            sos=i+n+2;break;
        }
        i+=n+2;
    }
    if(!sos)goto invalid;
    if(!supported || !sof || !restart || 3600%restart || (3600/restart)%8)
        return wv_decode_profile(c,jpeg,length,bgrx,output_length,fast,1);
    boundary=3600/restart;expected=7199/restart;i=sos;
    while(i<length-1) {
        const unsigned char *next=memchr(jpeg+i,255,length-i);
        unsigned long start;unsigned marker;
        if(!next)goto invalid;
        start=(unsigned long)(next-jpeg);i=start;
        while(i<length && jpeg[i]==255)i++;
        if(i==length)goto invalid;
        marker=jpeg[i++];if(marker==0)continue;
        if(marker>=0xd0 && marker<=0xd7) {
            if(marker!=0xd0+(seen%8))goto invalid;
            seen++;if(seen==boundary){begin=start;end=i;}continue;
        }
        if(marker==0xd9){if(i!=length)goto invalid;break;}
        goto invalid;
    }
    if(seen!=expected || !begin || !end)goto invalid;
    {
        unsigned long sizes[2]={begin+2,sos+length-end};
        unsigned char *parts[2]={NULL,NULL};StripeJob jobs[2];int result=-1;
        for(int k=0;k<2;k++) {
            parts[k]=(unsigned char *)malloc(sizes[k]);
            if(!parts[k]){snprintf(c->error,sizeof(c->error),"JPEG stripe allocation failed");goto cleanup;}
            if(!c->stripes[k]) {
                c->stripes[k]=wv_codec_open();
                if(!c->stripes[k] || wv_codec_configure_region(c->stripes[k],1280,360)) {
                    snprintf(c->error,sizeof(c->error),"JPEG stripe context failed");goto cleanup;
                }
            }
            memcpy(parts[k],jpeg,sos);parts[k][sof+5]=1;parts[k][sof+6]=104;
        }
        memcpy(parts[0]+sos,jpeg+sos,begin-sos);parts[0][begin]=255;parts[0][begin+1]=217;
        memcpy(parts[1]+sos,jpeg+end,length-end);
        for(int k=0;k<2;k++) {
            jobs[k].codec=(Codec *)c->stripes[k];jobs[k].jpeg=parts[k];jobs[k].length=sizes[k];
            jobs[k].output=bgrx+k*(1280UL*360*4);jobs[k].fast=fast;jobs[k].result=-1;
        }
#ifndef _WIN32
        {
            pthread_t worker;
            int started=pthread_create(&worker,NULL,decode_stripe_job,&jobs[0])==0;
            if(!started)decode_stripe_job(&jobs[0]);
            decode_stripe_job(&jobs[1]);
            if(started) {
                /* Join has no timeout: memory ownership cannot be returned
                 * while a native decoder still writes the caller's buffer. */
                if(pthread_join(worker,NULL)!=0)abort();
            }
        }
#else
        decode_stripe_job(&jobs[0]);decode_stripe_job(&jobs[1]);
#endif
        if(jobs[0].result<0 || jobs[1].result<0) {
            int failed=jobs[0].result<0?0:1;
            snprintf(c->error,sizeof(c->error),"%s",jobs[failed].codec->error);
        } else result=jobs[0].result+jobs[1].result;
cleanup:
        free(parts[0]);free(parts[1]);return result;
    }
invalid:
    snprintf(c->error,sizeof(c->error),"invalid restart-partitioned JPEG");return -1;
}

WV_API int wv_encode_profile(void *handle, const unsigned char *bgrx, unsigned long length,
                     int quality, int subsampling, int accurate_dct,
                     const unsigned char **jpeg, unsigned long *jpeg_length) {
    Codec *c=(Codec *)handle; unsigned long size;
    if(!c || !bgrx || !jpeg || !jpeg_length || length!=(unsigned long)c->stride*c->height || quality<1 || quality>100 ||
       (subsampling!=TJSAMP_444 && subsampling!=TJSAMP_422 && subsampling!=TJSAMP_420) ||
       (accurate_dct!=0 && accurate_dct!=1)) return -1;
    size=c->capacity;
    if(tjCompress2(c->enc,bgrx,c->width,c->stride,c->height,TJPF_BGRX,&c->jpeg,&size,subsampling,quality,
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
typedef struct { int fd, streaming; unsigned count; Map maps[16]; uint32_t num,den,width,height; } Camera;
static int xi(int fd, unsigned long request, void *arg) {
    int r; do { r=ioctl(fd,request,arg); } while(r<0 && errno==EINTR); return r;
}
/* Measured C270 profile. Other cameras retain their own settings. Read back
 * every control and roll back on failure; do not silently run a partial profile.
 * WV_CAMERA_PROFILE=0 is reserved for explicit baseline comparisons. */
static int c270_profile(int fd, const char *card, int streaming) {
    const uint32_t ids[]={V4L2_CID_CONTRAST,V4L2_CID_SHARPNESS,
                         V4L2_CID_POWER_LINE_FREQUENCY,V4L2_CID_EXPOSURE_AUTO_PRIORITY,
                         V4L2_CID_EXPOSURE_AUTO,V4L2_CID_EXPOSURE_ABSOLUTE};
    /* V4L2 exposure units are 100 us. A 20 ms shutter prevents dim scenes
     * from stretching capture to 121 ms despite a negotiated 25 fps rate.
     * Match the 50 Hz lighting period; adequate scene lighting is required. */
    const int values[]={36,32,V4L2_CID_POWER_LINE_FREQUENCY_50HZ,0,
                        V4L2_EXPOSURE_MANUAL,200};
    enum { CONTROL_COUNT=sizeof(ids)/sizeof(ids[0]) };
    int old[CONTROL_COUNT]; unsigned i,j;
    const char *profile=getenv("WV_CAMERA_PROFILE");
    if((profile && strcmp(profile,"0")==0) ||
       (!strstr(card,"0825") && !strstr(card,"C270"))) return 0;
    for(i=0;i<CONTROL_COUNT;i++) {
        struct v4l2_control ctrl; memset(&ctrl,0,sizeof(ctrl));ctrl.id=ids[i];
        if(xi(fd,VIDIOC_G_CTRL,&ctrl)<0) return -1;
        old[i]=ctrl.value;
    }
    for(i=0;i<CONTROL_COUNT;i++) {
        struct v4l2_control ctrl; memset(&ctrl,0,sizeof(ctrl));ctrl.id=ids[i];ctrl.value=values[i];
        int allowed_quantization=streaming && ids[i]==V4L2_CID_EXPOSURE_ABSOLUTE ? 5 : 0;
        /* This C270 reads 205 after a streaming request for 200 (100 us
         * units). Only that measured <=0.5 ms exposure quantization is
         * accepted; all other controls must still match exactly. */
        if(xi(fd,VIDIOC_S_CTRL,&ctrl)<0 || xi(fd,VIDIOC_G_CTRL,&ctrl)<0 ||
           abs(ctrl.value-values[i])>allowed_quantization) {
            int saved=errno?errno:EIO;
            /* Restore exposure value before returning its mode to automatic. */
            for(j=CONTROL_COUNT;j>0;j--) {ctrl.id=ids[j-1];ctrl.value=old[j-1];xi(fd,VIDIOC_S_CTRL,&ctrl);}
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
WV_API void *wv_camera_open_config(const char *device, char *error, unsigned error_size, unsigned width, unsigned height, unsigned fps) {
    Camera *c=(Camera *)calloc(1,sizeof(*c)); unsigned i; uint32_t caps;
    struct v4l2_capability cap; struct v4l2_format fmt; struct v4l2_streamparm parm;
    struct v4l2_requestbuffers req; enum v4l2_buf_type type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if(!c) return NULL;
    if(!((width==1280 && height==720)||(width==640 && height==360)) || (fps!=25 && fps!=30)) { free(c);return NULL; }
    c->width=width;c->height=height;
    c->fd=-1;
    c->fd=open(device,O_RDWR|O_NONBLOCK|O_CLOEXEC);
    if(c->fd<0) goto fail;
    memset(&cap,0,sizeof(cap)); if(xi(c->fd,VIDIOC_QUERYCAP,&cap)<0) goto fail;
    caps=(cap.capabilities&V4L2_CAP_DEVICE_CAPS)?cap.device_caps:cap.capabilities;
    if(!(caps&V4L2_CAP_VIDEO_CAPTURE) || !(caps&V4L2_CAP_STREAMING)) { errno=ENOTSUP; goto fail; }
    if(c270_profile(c->fd,(const char *)cap.card,0)<0) goto fail;
    memset(&fmt,0,sizeof(fmt)); fmt.type=type;
    fmt.fmt.pix.width=width;fmt.fmt.pix.height=height;fmt.fmt.pix.pixelformat=V4L2_PIX_FMT_MJPEG;
    fmt.fmt.pix.field=V4L2_FIELD_NONE;
    if(xi(c->fd,VIDIOC_S_FMT,&fmt)<0) goto fail;
    if(fmt.fmt.pix.width!=width || fmt.fmt.pix.height!=height || fmt.fmt.pix.pixelformat!=V4L2_PIX_FMT_MJPEG) { errno=ENOTSUP;goto fail; }
    memset(&parm,0,sizeof(parm));parm.type=type;
    parm.parm.capture.timeperframe.numerator=1;parm.parm.capture.timeperframe.denominator=fps;
    if(xi(c->fd,VIDIOC_S_PARM,&parm)<0 || xi(c->fd,VIDIOC_G_PARM,&parm)<0) goto fail;
    c->num=parm.parm.capture.timeperframe.numerator;c->den=parm.parm.capture.timeperframe.denominator;
    if(!c->num || (double)c->den/c->num<fps-.3 || (double)c->den/c->num>fps+.3) { errno=ENOTSUP;goto fail; }
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
    c->streaming=1;
    /* S_FMT/S_PARM/STREAMON change this camera's effective exposure timing.
     * Reassert and verify the profile after streaming starts: setting only
     * the pre-stream values produced ~16.5 fps despite negotiating 25 fps.
     * A streaming exposure write restored ~25 fps on the real C270. */
    if(c270_profile(c->fd,(const char *)cap.card,1)<0) goto fail;
    return c;
fail:
    if(error && error_size) snprintf(error,error_size,"MJPEG 1280x720@30 negotiation: %s",strerror(errno));
    wv_camera_close(c);return NULL;
}
WV_API void *wv_camera_open(const char *device,char *error,unsigned error_size) {
    return wv_camera_open_config(device,error,error_size,1280,720,30);
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
        info->width=c->width;info->height=c->height;info->fps_num=c->num;info->fps_den=c->den;
    }
    r=(int)b.bytesused; /* QBUF may update descriptor fields; retain DQBUF length. */
    if(xi(c->fd,VIDIOC_QBUF,&b)<0) return -1;
    if(!valid) return -2;
    return r;
}
#else
WV_API void *wv_camera_open_config(const char *device,char *error,unsigned size,unsigned width,unsigned height,unsigned fps) {
    (void)device;(void)width;(void)height;(void)fps;
    if(error && size)snprintf(error,size,"V4L2 capture requires Linux");return NULL;
}
WV_API void *wv_camera_open(const char *device,char *error,unsigned size) {
    (void)device;if(error && size) snprintf(error,size,"V4L2 capture requires Linux; Windows codec tests are not hardware evidence");return NULL;
}
WV_API void wv_camera_close(void *handle) { (void)handle; }
WV_API int wv_camera_read(void *h,unsigned char *j,unsigned n,FrameInfo *i,int t) {
    (void)h;(void)j;(void)n;(void)i;(void)t;return -1;
}
#endif
