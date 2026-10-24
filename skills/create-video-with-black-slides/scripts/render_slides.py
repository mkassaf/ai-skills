#!/usr/bin/env python3
"""Render declarative speech-timed black lightboard graphics (Pillow + FFmpeg)."""
import argparse
import json
import math
import subprocess
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from common import ffmpeg_binary

DEFAULTS={'mint':'#89efda','purple':'#baa5ff','white':'#eef2f6','muted':'#9ca7b3','dim':'#43525d'}

def ease(value): return 1-(1-max(0,min(1,value)))**3

def rgba(value, palette):
    if isinstance(value,(tuple,list)):
        if len(value) not in (3,4): raise ValueError('Color array needs 3 or 4 channels')
        return tuple(value)+(255,) if len(value)==3 else tuple(value)
    value=palette.get(value,value)
    if isinstance(value,str) and value.startswith('#') and len(value)==7:
        return tuple(int(value[i:i+2],16) for i in (1,3,5))+(255,)
    raise ValueError(f'Invalid color: {value!r}')

@lru_cache(None)
def font(size, style='hand', bold=False, override=None):
    if override: return ImageFont.truetype(override,size)
    candidates=(
        [('/System/Library/Fonts/Supplemental/Chalkboard.ttc',1 if bold else 0),
         ('/System/Library/Fonts/Supplemental/Comic Sans MS.ttf',0)] if style=='hand' else
        [('/System/Library/Fonts/Avenir Next.ttc',0 if bold else 7),
         ('/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf',0)])
    candidates += [('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',0)]
    for path,index in candidates:
        if Path(path).exists(): return ImageFont.truetype(path,size,index=index)
    raise RuntimeError('No usable font found. Pass --font-clean and --font-hand with TTF font paths.')

class Renderer:
    def __init__(self,story,font_clean=None,font_hand=None):
        self.story=story
        for key,default in [('width',1280),('height',720),('fps',30)]:
            value=story.get(key,default)
            if isinstance(value,bool) or not math.isfinite(float(value)) or not float(value).is_integer():raise ValueError(f'{key} must be an integer')
        self.width=int(story.get('width',1280));self.height=int(story.get('height',720))
        self.fps=int(story.get('fps',30));self.duration=float(story['duration'])
        if not math.isfinite(self.duration) or min(self.width,self.height,self.fps,self.duration)<=0 or self.width%2 or self.height%2:
            raise ValueError('Dimensions must be positive even integers; fps and duration positive')
        self.palette={**DEFAULTS,**story.get('palette',{})}
        self.fonts={'clean':font_clean,'hand':font_hand}
        self.scenes=story['scenes']
        cursor=0
        for scene in self.scenes:
            start,end=float(scene['start']),float(scene['end'])
            if not all(math.isfinite(v) for v in [start,end]) or abs(start-cursor)>.001 or end<=start or end>self.duration+.001:
                raise ValueError('Scenes must cover [0,duration] continuously without overlaps')
            scene['_events']=[]
            for event in scene.get('events',[]):
                at=float(event['at']);until=float(event.get('end',end))
                if not start<=at<until<=end+.001: raise ValueError(f'Invalid event timing: {event}')
                for e in self.expand(dict(event,end=until)):
                    e=dict(e);e.setdefault('duration',.55 if e['kind']=='text' else .65)
                    if e['duration']<=0:raise ValueError('Reveal duration must be positive')
                    e['_end']=until
                    if e['kind']=='text':e['_sprite'],e['_x']=self.text_sprite(e)
                    elif e['kind']=='path':
                        if len(e['points'])<2:raise ValueError('A path needs at least two points')
                        e['_lengths']=[math.dist(a,b) for a,b in zip(e['points'],e['points'][1:])]
                        if any(not (0<=x<=self.width and 0<=y<=self.height) for x,y in e['points']):raise ValueError('Path outside canvas')
                        if int(e.get('width',3))<=0:raise ValueError('Stroke width must be positive')
                    else:raise ValueError(f"Unknown event kind: {e['kind']}")
                    scene['_events'].append(e)
            cursor=end
        if not self.scenes or abs(cursor-self.duration)>.001:raise ValueError('Scenes must end at duration')

    def expand(self,e):
        if e['kind'] in ('text','path'):return [e]
        if e['kind'] not in ('box','node'): raise ValueError(f"Unknown event kind: {e['kind']}")
        x,y,w,h=e['x'],e['y'],e['w'],e['h'];r=min(12,w/6,h/6)
        points=[(x+r,y),(x+w-r,y),(x+w,y+r),(x+w,y+h-r),(x+w-r,y+h),(x+r,y+h),(x,y+h-r),(x,y+r),(x+r,y)]
        border={k:v for k,v in e.items() if k in ('at','end','duration','color','width')}
        border.update(kind='path',points=points)
        if e['kind']=='box':return [border]
        size=e.get('size',30)
        label={'kind':'text','text':e['text'],'x':x+w/2,'y':y+(h-size)/2,'align':'center','size':size,'font':e.get('font','hand'),'bold':e.get('bold',False),'color':e.get('text_color',e.get('color','mint')),'max_width':w-12,'at':e['at']+min(.25,max(.0,(e.get('end',self.duration)-e['at'])/4)),'duration':.55}
        if 'end' in e:label['end']=e['end']
        return [border,label]

    def text_sprite(self,e):
        size=int(e.get('size',30));style=e.get('font','hand')
        if style not in self.fonts:raise ValueError('Font must be hand or clean')
        ft=font(size,style,e.get('bold',False),self.fonts[style]);text=str(e['text'])
        if '\n' in text:raise ValueError('Use separate text events for multiple lines')
        bbox=ft.getbbox(text);width=max(1,math.ceil(ft.getlength(text))+6)
        height=max(size*2,bbox[3]-bbox[1]+4)
        if e.get('max_width') and width>e['max_width']:raise ValueError(f'Text too wide: {text!r}')
        im=Image.new('RGBA',(width,height),(0,0,0,0))
        ImageDraw.Draw(im).text((2,-bbox[1]+2),text,font=ft,fill=rgba(e.get('color','white'),self.palette))
        x=float(e['x']);align=e.get('align','left')
        if align=='center':x-=width/2
        elif align=='right':x-=width
        elif align!='left':raise ValueError('Text align must be left, center or right')
        if x<0 or x+width>self.width or e['y']<0 or e['y']+bbox[3]-bbox[1]+4>self.height:
            raise ValueError(f'Text outside canvas: {text!r}')
        return im,round(x)

    def paint_path(self,d,e,t):
        progress=ease((t-e['at'])/e['duration'])
        if progress<=0:return
        pts=e['points'];remain=sum(e['_lengths'])*progress;traced=[pts[0]]
        for a,b,length in zip(pts,pts[1:],e['_lengths']):
            if remain>=length:traced.append(b);remain-=length
            else:
                if length:traced.append((a[0]+(b[0]-a[0])*remain/length,a[1]+(b[1]-a[1])*remain/length))
                break
        color=rgba(e.get('color','mint'),self.palette);width=int(e.get('width',3))
        if len(traced)>1:d.line(traced,fill=color,width=width,joint='curve')
        if e.get('arrow') and progress>.99:
            a,b=pts[-2:];theta=math.atan2(b[1]-a[1],b[0]-a[0]);wing=11
            d.line([(b[0]-wing*math.cos(theta-.5),b[1]-wing*math.sin(theta-.5)),b,(b[0]-wing*math.cos(theta+.5),b[1]-wing*math.sin(theta+.5))],fill=color,width=width,joint='curve')

    def frame(self,t):
        if not 0<=t<self.duration:raise ValueError('Preview time must be within [0,duration)')
        scene=next(s for s in self.scenes if s['start']<=t<s['end'])
        ink=Image.new('RGBA',(self.width,self.height),(0,0,0,0));d=ImageDraw.Draw(ink)
        for e in scene['_events']:
            if not e['at']<=t<e['_end']:continue
            if e['kind']=='path':self.paint_path(d,e,t)
            else:
                progress=ease((t-e['at'])/e['duration']);sprite=e['_sprite']
                if progress<1:
                    sprite=sprite.crop((0,0,max(1,int(sprite.width*progress)),sprite.height))
                    sprite.putalpha(sprite.getchannel('A').point(lambda a:round(a*min(1,progress*2))))
                ink.alpha_composite(sprite,(e['_x'],round(e['y'])))
        glow=ink.filter(ImageFilter.GaussianBlur(3));glow.putalpha(glow.getchannel('A').point(lambda a:round(a*.25)))
        result=Image.new('RGBA',ink.size,(0,0,0,255));result.alpha_composite(glow);result.alpha_composite(ink)
        fade=min(1,max(0,(scene['end']-t)/.2))
        if fade<1:result=Image.blend(Image.new('RGBA',ink.size,(0,0,0,255)),result,fade)
        return result.convert('RGB')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--storyboard',required=True);ap.add_argument('--out')
    ap.add_argument('--preview-dir');ap.add_argument('--times',help='Comma-separated preview times; defaults to scene midpoints')
    ap.add_argument('--font-clean');ap.add_argument('--font-hand');ap.add_argument('--ffmpeg')
    args=ap.parse_args()
    if not args.out and not args.preview_dir:ap.error('Specify --out or --preview-dir')
    board=Path(args.storyboard).resolve();renderer=Renderer(json.loads(board.read_text()),args.font_clean,args.font_hand)
    if args.preview_dir:
        directory=Path(args.preview_dir);directory.mkdir(parents=True,exist_ok=True)
        times=[float(v) for v in args.times.split(',')] if args.times else [(s['start']+s['end'])/2 for s in renderer.scenes]
        for t in times:renderer.frame(t).save(directory/f'frame-{t:08.3f}.png')
    if args.out:
        out=Path(args.out).resolve()
        if out==board:raise ValueError('Output must differ from storyboard')
        out.parent.mkdir(parents=True,exist_ok=True)
        cmd=[ffmpeg_binary(args.ffmpeg),'-y','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{renderer.width}x{renderer.height}','-r',str(renderer.fps),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        try:
            for i in range(math.ceil(renderer.duration*renderer.fps)):
                p.stdin.write(renderer.frame(i/renderer.fps).tobytes())
                if i%(renderer.fps*10)==0:print(f'{i/renderer.fps:.1f}s / {renderer.duration:.1f}s',flush=True)
        finally:p.stdin.close()
        if p.wait():raise RuntimeError('Graphics encode failed')
        print(out)
if __name__=='__main__':main()
