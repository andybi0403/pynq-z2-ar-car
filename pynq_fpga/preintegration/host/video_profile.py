"""One immutable per-process video profile; a profile change requires restart."""
import os
PROFILES={'wireless720':(1280,720,30),'wireless360':(640,360,25),'wireless720_jpeg':(1280,720,25)}
PROFILE=os.environ.get('PYNQ_VIDEO_PROFILE','wireless720')
if PROFILE not in PROFILES:raise ValueError('unsupported video profile: '+PROFILE)
WIDTH,HEIGHT,FPS=PROFILES[PROFILE]
STRIDE=WIDTH*4
FRAME_BYTES=STRIDE*HEIGHT

MAX_FRAME_AGE_NS=150_000_000 if PROFILE=="wireless360" else 200_000_000 if PROFILE=='wireless720_jpeg' else 500_000_000
