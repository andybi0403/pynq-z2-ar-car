"""Reproducible COMPLEX synthetic host scene; explicitly not board evidence."""
from pathlib import Path
import sys
import json
import numpy as np
from PIL import Image
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'preintegration/host'))
from native_video import NativeLibrary
from wireless_benchmark import codec_benchmark


def main():
    folder=PROJECT/'preintegration/evidence/wireless_20261004'
    folder.mkdir(parents=True,exist_ok=True)
    random=np.random.default_rng(4251009)
    texture=random.integers(0,256,size=(720,1280,3),dtype=np.uint8)
    fixture=folder/'complex_host_fixture.jpg'
    Image.fromarray(texture).save(fixture,quality=90,subsampling=0)
    native=NativeLibrary(PROJECT/'fpga/build/wireless_native_host_v2/Release/car_video.dll')
    result=codec_benchmark(native,fixture.read_bytes(),5)
    result.update(scene='seeded random 720p RGB texture; synthetic HOST scene',
                  simd='OFF on Windows correctness build',arm_720p30_acceptance='PENDING')
    (folder/'host_codec_benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
