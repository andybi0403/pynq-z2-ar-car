"""Separate real capture, JPEG throughput and PC receipt; no synthetic FPS pass."""
import argparse
import asyncio
import io
import json
import math
from pathlib import Path
import platform
import statistics
import time
from native_video import NativeLibrary,Camera,Codec,FRAME_BYTES,CameraWarmingUp


def percentile(values,p):
    ordered=sorted(values)
    return ordered[max(0,math.ceil(len(ordered)*p)-1)] if ordered else None


def codec_benchmark(native,jpeg,seconds):
    frame=bytearray(FRAME_BYTES);count=0;encoded_bytes=0;decode=[];encode=[]
    with Codec(native) as codec:
        codec.decode_into(jpeg,frame)
        began=time.monotonic();cpu=time.process_time()
        while time.monotonic()-began<seconds:
            t=time.perf_counter();codec.decode_into(jpeg,frame);decode.append((time.perf_counter()-t)*1000)
            t=time.perf_counter();encoded=codec.encode(frame,75);encode.append((time.perf_counter()-t)*1000)
            encoded_bytes+=len(encoded);count+=1
        elapsed=time.monotonic()-began;cpu=time.process_time()-cpu
    return {'kind':'decode_encode_benchmark','machine':platform.machine(),'platform':platform.platform(),
            'native_version':native.lib.wv_version().decode(),'frames':count,'seconds':elapsed,
            'combined_fps':count/elapsed,'encode_only_fps':1000/statistics.mean(encode),
            'decode_p95_ms':percentile(decode,.95),'encode_p95_ms':percentile(encode,.95),
            'mean_jpeg_bytes':encoded_bytes/count,'mean_video_mbps_at_30fps':encoded_bytes/count*30*8/1e6,
            'process_cpu_core_equivalents':cpu/elapsed,'quality':75,'subsampling':'4:2:0',
            'hardware_performance_validated':False,
            'note':'A host result cannot establish Cortex-A9 performance; combined PL/network load still required.'}


def capture_benchmark(native,device,seconds):
    frames=[];sizes=[];negotiated=None;started=time.monotonic()
    with Camera(native,device) as camera:
        while time.monotonic()-started<seconds:
            try:frame_id,stamp,jpeg,info=camera.read()
            except CameraWarmingUp:continue
            frames.append((frame_id,stamp));sizes.append(len(jpeg))
            negotiated={'width':info.width,'height':info.height,'fps_num':info.fps_num,'fps_den':info.fps_den}
        drops=camera.dropped
    if len(frames)<2:raise RuntimeError('capture benchmark requires at least two real frames after startup')
    elapsed=time.monotonic()-started
    capture_span=(frames[-1][1]-frames[0][1])/1e9 if len(frames)>1 else elapsed
    return {'kind':'real_V4L2_capture','machine':platform.machine(),'negotiated':negotiated,
            'unique_frames':len(frames),'seconds':elapsed,'wall_fps':len(frames)/elapsed,
            'timestamp_fps':(len(frames)-1)/capture_span,'camera_dropped':drops,
            'mean_jpeg_bytes':statistics.mean(sizes),'hardware_performance_validated':False}


async def receive_benchmark(url,token,seconds):
    from aiohttp import ClientSession,ClientTimeout
    timestamps=[];last=-1;gaps=0;payload=0;start=time.monotonic();buckets={}
    async with ClientSession(timeout=ClientTimeout(total=seconds+5,sock_read=2)) as session:
        async with session.get(url,headers={'Authorization':'Bearer '+token}) as response:
            response.raise_for_status()
            while time.monotonic()-start<seconds:
                line=await response.content.readline()
                if line.strip()!=b'--carframe':
                    if not line:raise EOFError('video stopped')
                    continue
                headers={}
                while True:
                    line=await response.content.readline()
                    if not line:raise EOFError('truncated MJPEG header')
                    if line==b'\r\n':break
                    key,value=line.decode().split(':',1);headers[key.lower()]=value.strip()
                size=int(headers['content-length']);identity=int(headers['x-frame-id'])
                if not 4<=size<=4*1024*1024:raise ValueError('unbounded JPEG length')
                jpeg=await response.content.readexactly(size)
                if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):raise ValueError('damaged JPEG')
                if identity<=last:raise ValueError('repeated/out-of-order receiver frame')
                if last>=0:gaps+=identity-last-1
                last=identity;payload+=size;now=time.monotonic();timestamps.append(now)
                minute=int((now-start)//60);buckets[minute]=buckets.get(minute,0)+1
    elapsed=time.monotonic()-start
    return {'kind':'PC_MJPEG_receipt','unique_frames':len(timestamps),'seconds':elapsed,
            'receipt_fps':len(timestamps)/elapsed,'frame_id_gaps':gaps,
            'full_minute_fps':{str(m):buckets.get(m,0)/60 for m in range(int(elapsed//60))},
            'payload_mbps':payload*8/elapsed/1e6,'screen_display_fps':'PENDING_EXTERNAL_MEASUREMENT',
            'glass_to_glass_p95_ms':'PENDING_VISIBLE_TIMER_OR_VIDEO','hardware_performance_validated':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['codec','capture','receive'])
    parser.add_argument('--native',type=Path,default=Path('native-build/libcar_video.so'))
    parser.add_argument('--jpeg',type=Path);parser.add_argument('--device',default='/dev/video0')
    parser.add_argument('--seconds',type=float,default=60)
    parser.add_argument('--url',default='http://192.168.8.10:8080/api/video?view=processed')
    parser.add_argument('--token');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds<=0:parser.error('positive finite seconds required')
    if args.mode=='codec' and args.jpeg is None:parser.error('codec benchmark requires a real 720p --jpeg')
    if args.mode=='receive' and not args.token:parser.error('receive requires current --token')
    if args.mode=='receive':result=asyncio.run(receive_benchmark(args.url,args.token,args.seconds))
    else:
        native=NativeLibrary(args.native)
        result=codec_benchmark(native,args.jpeg.read_bytes(),args.seconds) if args.mode=='codec' else capture_benchmark(native,args.device,args.seconds)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
