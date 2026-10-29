"""Bounded FFmpeg clip rendering and safe ASS caption styling."""
import re, math
from pydantic import BaseModel, Field
from .media import ROOT, run, duration, srt_time

class SubtitleStyle(BaseModel):
    font:str=Field(default='DejaVu Sans',pattern='^(DejaVu Sans|DejaVu Serif|DejaVu Sans Mono|Liberation Sans)$')
    size:int=Field(default=46,ge=20,le=90)
    bold:bool=True
    color:str=Field(default='#FFFFFF',pattern='^#[0-9a-fA-F]{6}$')
    keyword_color:str=Field(default='#4EE0AC',pattern='^#[0-9a-fA-F]{6}$')
    preset:str=Field(default='clean',pattern='^(clean|bold|karaoke|neon)$')
    outline:int=Field(default=3,ge=0,le=8)
    shadow:int=Field(default=1,ge=0,le=6)
    box:bool=False
    position:str=Field(default='bottom',pattern='^(top|center|bottom)$')
    x:int=Field(default=0,ge=-250,le=250)
    y:int=Field(default=0,ge=-250,le=250)
    max_words:int=Field(default=5,ge=1,le=8)
    keywords:str=Field(default='',max_length=200)

class ClipRange(BaseModel):
    start:float=Field(ge=0,le=1800,allow_inf_nan=False)
    end:float=Field(gt=0,le=1800,allow_inf_nan=False)
    reason:str=Field(default='',max_length=300)

def validate_ranges(ranges,total):
    if not 1<=len(ranges)<=10: raise ValueError('Pilih 1–10 klip per pekerjaan.')
    seen=set()
    for item in ranges:
        a,b=item['start'],item['end']
        if not math.isfinite(a+b) or b-a<1 or b-a>180 or b>total+.1: raise ValueError('Setiap klip harus 1–180 detik dan berada di dalam durasi sumber.')
        if (a,b) in seen: raise ValueError('Rentang klip duplikat.')
        seen.add((a,b))

def ass_time(t):
    cs=round(max(t,0)*100);h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);sec,cs=divmod(cs,100)
    return f'{h}:{m:02}:{sec:02}.{cs:02}'
def color(s): return '&H00'+s[5:7]+s[3:5]+s[1:3]
def safe(s): return re.sub(r'[{}\\\r\n]',' ',s)

def write_subtitles(folder,segments,style,portrait=True,start=0,end=None):
    st=SubtitleStyle(**style);w,h=(720,1280) if portrait else (1280,720)
    y={'top':int(h*.16),'center':h//2,'bottom':int(h*.8)}[st.position]+st.y
    x=w//2+st.x;y=max(70,min(h-70,y));x=max(100,min(w-100,x))
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{st.font},{st.size},{color(st.color)},{color(st.keyword_color)},&H00101010,&H88000000,{-1 if st.bold else 0},0,0,0,100,100,0,0,{3 if st.box else 1},{st.outline},{st.shadow},5,55,55,60,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines=[];srt=[];keywords=set(st.keywords.lower().split())
    for seg in segments:
        a=max(float(seg['start']),start);b=min(float(seg['end']),end if end is not None else float(seg['end']))
        if b<=a: continue
        words=str(seg['text']).split()
        if not words: continue
        for n in range(0,len(words),st.max_words):
            chunk=words[n:n+st.max_words];t0=a+(b-a)*n/len(words)-start;t1=a+(b-a)*(n+len(chunk))/len(words)-start
            tagged=[]
            for word in chunk:
                text=safe(word)
                if st.preset=='karaoke': text='{\\kf'+str(max(1,round((t1-t0)*100/len(chunk))))+'}'+text
                elif word.lower().strip('.,!?') in keywords or (st.preset=='bold' and not keywords and len(tagged)==0): text='{\\c'+color(st.keyword_color)+'&}'+text+'{\\c'+color(st.color)+'&}'
                tagged.append(text)
            effect='{\\pos('+str(x)+','+str(y)+')'+('\\blur3' if st.preset=='neon' else '')+'}'
            lines.append(f'Dialogue: 0,{ass_time(t0)},{ass_time(t1)},Default,,0,0,0,,{effect}'+ ' '.join(tagged))
            srt.append(f'{len(srt)+1}\n{srt_time(t0)} --> {srt_time(t1)}\n'+ ' '.join(chunk)+'\n')
    (folder/'captions.ass').write_text(header+'\n'.join(lines),encoding='utf-8')
    (folder/'subtitles.srt').write_text('\n'.join(srt),encoding='utf-8')

def burn_video(source,folder,segments,style,portrait,check,start=0,end=None):
    folder.mkdir(parents=True,exist_ok=True)
    write_subtitles(folder,segments,style,portrait,start,end)
    w,h=(720,1280) if portrait else (1280,720)
    # Paths below are UUID-based server paths; never interpolate user input into filters.
    vf=f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,ass={folder}/captions.ass'
    args=['ffmpeg','-nostdin','-y','-ss',str(start),'-i',str(source)]
    if end is not None: args+=['-t',str(end-start)]
    args+=['-map','0:v:0','-map','0:a?','-vf',vf,'-c:v','libx264','-preset','ultrafast','-threads','2','-r','24','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(folder/'video.tmp.mp4')]
    run(args,check);(folder/'video.tmp.mp4').replace(folder/'video.mp4')
    return {'video':str((folder/'video.mp4').relative_to(ROOT)),'subtitles':str((folder/'subtitles.srt').relative_to(ROOT))}

def multiclip(job,payload,source,transcript,check,report):
    ranges=payload['clips'];validate_ranges(ranges,duration(source));results=[]
    for i,clip in enumerate(ranges):
        check();report(5+int(i/len(ranges)*90),f'Merender klip {i+1}/{len(ranges)}')
        folder=ROOT/'clips'/job/f'{i+1:02}'
        if not (folder/'video.mp4').exists(): burn_video(source,folder,transcript,payload['subtitle_style'],payload['format']=='short',check,clip['start'],clip['end'])
        results.append({**clip,'video':str((folder/'video.mp4').relative_to(ROOT)),'subtitles':str((folder/'subtitles.srt').relative_to(ROOT)),'duration':round(duration(folder/'video.mp4'),2)})
        # Each finished clip is downloadable immediately and survives pause/retry.
        from .db import Session, Job
        with Session() as s:
            j=s.get(Job,job);j.result={**j.result,'clips':list(results)};s.commit()
    return {'clips':results,'source_asset':payload['asset_id'],'retention':'permanent_until_explicit_delete','timing_note':'Timing subtitle diperkirakan per kata dari segmen transkripsi; tinjau hasil sebelum publikasi.'}
