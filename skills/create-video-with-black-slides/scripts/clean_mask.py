#!/usr/bin/env python3
"""Optional matte repairs: isolated components or local background-reference cleanup."""
import argparse,math,subprocess,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
from common import ffmpeg_binary


def exact(stream,count):
    data=bytearray()
    while len(data)<count:
        chunk=stream.read(count-len(data))
        if not chunk:break
        data.extend(chunk)
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['components','reference'],required=True)
    p.add_argument('--mask',required=True);p.add_argument('--out',required=True)
    p.add_argument('--duration',type=float,required=True)
    p.add_argument('--width',type=int,default=1280);p.add_argument('--height',type=int,default=720);p.add_argument('--fps',type=int,default=30)
    p.add_argument('--source');p.add_argument('--roi',nargs=4,type=int,metavar=('X','Y','W','H'))
    p.add_argument('--reference-time',type=float)
    p.add_argument('--difference-low',type=float,default=25);p.add_argument('--difference-high',type=float,default=50)
    p.add_argument('--preserve-cool-dark',action='store_true',help='Optional navy-clothing protection; inspect actual colors before using')
    p.add_argument('--ffmpeg');a=p.parse_args();ff=ffmpeg_binary(a.ffmpeg)
    if min(a.width,a.height,a.fps,a.duration)<=0 or a.width%2 or a.height%2:p.error('Invalid profile')
    if Path(a.out).resolve() in {Path(v).resolve() for v in [a.mask,a.source] if v}:p.error('Output must differ from inputs')
    if not Path(a.mask).is_file():p.error('Mask does not exist')
    if a.mode=='reference':
        if not a.source or not Path(a.source).is_file() or a.roi is None or a.reference_time is None:p.error('Reference cleanup requires --source --roi --reference-time')
        if a.reference_time<0 or a.difference_high<=a.difference_low:p.error('Invalid reference time or difference thresholds')
        x,y,rw,rh=a.roi
        if min(x,y)<0 or min(rw,rh)<=0 or x+rw>a.width or y+rh>a.height:p.error('ROI must be within profile')
        fit=f'scale={a.width}:{a.height}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,pad={a.width}:{a.height}:(ow-iw)/2:(oh-ih)/2,format=rgb24,crop={rw}:{rh}:{x}:{y}:exact=1'
        data=subprocess.check_output([ff,'-hide_banner','-loglevel','error','-ss',str(a.reference_time),'-i',a.source,'-vf',fit,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        if len(data)!=rw*rh*3:raise ValueError('Reference frame unavailable')
        bg=np.frombuffer(data,np.uint8).reshape(rh,rw,3).astype(np.int16)
    else:
        from scipy import ndimage as ndi
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    processes=[]
    try:
        mask=subprocess.Popen([ff,'-hide_banner','-loglevel','error','-i',a.mask,'-t',str(a.duration),'-vf',f'fps={a.fps},scale={a.width}:{a.height}','-an','-f','rawvideo','-pix_fmt','gray','pipe:1'],stdout=subprocess.PIPE);processes.append(mask)
        if a.mode=='reference':
            source=subprocess.Popen([ff,'-hide_banner','-loglevel','error','-i',a.source,'-t',str(a.duration),'-vf',f'fps={a.fps},'+fit,'-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE);processes.append(source)
        output=subprocess.Popen([ff,'-y','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','gray','-s',f'{a.width}x{a.height}','-r',str(a.fps),'-i','pipe:0','-an','-c:v','ffv1','-pix_fmt','gray',a.out],stdin=subprocess.PIPE);processes.append(output)
        for index in range(math.ceil(a.duration*a.fps)):
            data=exact(mask.stdout,a.width*a.height)
            if len(data)!=a.width*a.height:raise ValueError(f'Matte ends before frame {index}')
            m=np.frombuffer(data,np.uint8).reshape(a.height,a.width).copy()
            if a.mode=='reference':
                data=exact(source.stdout,rw*rh*3)
                if len(data)!=rw*rh*3:raise ValueError(f'Source ends before frame {index}')
                roi=np.frombuffer(data,np.uint8).reshape(rh,rw,3).astype(np.int16)
                difference=np.max(np.abs(roi-bg),axis=2)
                keep=np.clip((difference-a.difference_low)/(a.difference_high-a.difference_low),0,1)
                if a.preserve_cool_dark:
                    cool=np.clip((roi[:,:,2]-roi[:,:,0]-5)/5,0,1)*np.clip((125-roi.max(axis=2))/25,0,1)
                    keep=np.maximum(keep,cool)
                keep=np.asarray(Image.fromarray((keep*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(.7)),np.float32)/255
                m[y:y+rh,x:x+rw]=(m[y:y+rh,x:x+rw].astype(np.float32)*keep).astype(np.uint8)
            else:
                # Max pooling and dilation retain small fingers around the selected silhouette.
                factor=4 if a.width%4==0 and a.height%4==0 else 2
                small=m.reshape(a.height//factor,factor,a.width//factor,factor).max(axis=(1,3))>24
                labels,_=ndi.label(small,structure=np.ones((3,3),np.uint8));sizes=np.bincount(labels.ravel());sizes[0]=0
                if sizes.max()>0:
                    keep=ndi.binary_dilation(labels==int(sizes.argmax()),iterations=2).repeat(factor,0).repeat(factor,1)
                    m[~keep]=0
            output.stdin.write(m.tobytes())
        output.stdin.close();mask.stdout.close()
        if a.mode=='reference':source.stdout.close()
        for process in processes:
            code=process.wait()
            if code:raise RuntimeError(f'FFmpeg cleanup failed with code {code}')
    finally:
        for process in processes:
            if process.poll() is None:process.kill();process.wait()
    print(Path(a.out).resolve())
if __name__=='__main__':main()
