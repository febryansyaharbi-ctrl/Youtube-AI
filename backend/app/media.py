import os, re, json, time, subprocess, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(os.getenv('MEDIA_ROOT','/data/media'))
ROOT.mkdir(parents=True,exist_ok=True)
class Controlled(Exception): pass

def run(args,check,timeout=1800):
    # No shell; stderr is captured to a private temporary file, never exposed to users.
    import tempfile
    with tempfile.TemporaryFile() as errors:
        process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=errors)
        start=time.monotonic()
        try:
            while process.poll() is None:
                check()
                if time.monotonic()-start>timeout: raise RuntimeError('Proses media melewati batas waktu.')
                time.sleep(.5)
            if process.returncode: raise RuntimeError('Pemrosesan media gagal. Periksa format dan coba lagi.')
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(5)
                except subprocess.TimeoutExpired: process.kill();process.wait()

def duration(path):
    result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(path)],capture_output=True,text=True,timeout=20)
    return float(json.loads(result.stdout)['format']['duration'])

def segments(text):
    sentences=re.split(r'(?<=[.!?])\s+',text.strip())
    result=[]
    for sentence in sentences:
        words=sentence.split()
        while words: result.append(' '.join(words[:18]));words=words[18:]
    return result[:100]

def card(path,text,title,index,total,portrait=True,background=None):
    w,h=(720,1280) if portrait else (1280,720)
    image=Image.new('RGB',(w,h),'#0c1221')
    if background:
        from PIL import ImageOps
        with Image.open(background) as raw: image=ImageOps.fit(raw.convert('RGB'),(w,h))
        overlay=Image.new('RGB',(w,h),'#0c1221');image=Image.blend(image,overlay,.72)
    draw=ImageDraw.Draw(image)
    font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    label=ImageFont.truetype(font,20);body=ImageFont.truetype(font,42 if portrait else 36)
    draw.rounded_rectangle((48,55,230,96),radius=15,fill='#4ee0ac')
    draw.text((64,64),'CREATOR STUDIO',font=ImageFont.truetype(font,15),fill='#081810')
    draw.text((50,130),title[:48],font=label,fill='#9aa9bd')
    lines=textwrap.wrap(text,width=25 if portrait else 50)
    y=(h-len(lines)*60)//2
    for line in lines: draw.text((50,y),line,font=body,fill='#f4f6fa');y+=60
    draw.rounded_rectangle((50,h-90,w-50,h-82),radius=4,fill='#263248')
    draw.rounded_rectangle((50,h-90,50+int((w-100)*index/total),h-82),radius=4,fill='#4ee0ac')
    draw.text((50,h-60),f'{index:02d} / {total:02d}',font=label,fill='#9aa9bd')
    image.save(path)

def srt_time(seconds):
    ms=round(seconds*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

def render(project,folder,check,progress,background=None):
    folder.mkdir(parents=True,exist_ok=True)
    parts=segments(project.script)
    if not parts: raise RuntimeError('Naskah masih kosong.')
    clips=[];subtitles=[];cursor=0
    for i,text in enumerate(parts):
        check();progress(10+int(75*i/len(parts)),f'Merender adegan {i+1}/{len(parts)}')
        wav=folder/f'{i:03}.wav';png=folder/f'{i:03}.png';clip=folder/f'{i:03}.mp4'
        if not clip.exists():
            txt=folder/f'{i:03}.txt';txt.write_text(text,encoding='utf-8')
            run(['espeak-ng','-v','id' if project.language=='id' else 'en-us','-s','155','-f',str(txt),'-w',str(wav)],check)
            card(png,text,project.title,i+1,len(parts),project.format=='short',background)
            run(['ffmpeg','-nostdin','-y','-loop','1','-i',str(png),'-i',str(wav),'-c:v','libx264','-preset','ultrafast','-tune','stillimage','-threads','2','-r','24','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-shortest',str(clip.with_suffix('.tmp.mp4'))],check)
            clip.with_suffix('.tmp.mp4').replace(clip)
        length=duration(clip);subtitles.append(f'{i+1}\n{srt_time(cursor)} --> {srt_time(cursor+length)}\n{text}\n');cursor+=length;clips.append(clip)
    listing=folder/'concat.txt';listing.write_text('\n'.join(f"file '{p.name}'" for p in clips))
    run(['ffmpeg','-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(folder/'video.tmp.mp4')],check)
    (folder/'video.tmp.mp4').replace(folder/'video.mp4')
    (folder/'subtitles.srt').write_text('\n'.join(subtitles),encoding='utf-8')
    card(folder/'thumbnail.png',project.title,project.niche,1,1,False,background)
    return {'video':str((folder/'video.mp4').relative_to(ROOT)),'subtitles':str((folder/'subtitles.srt').relative_to(ROOT)),'thumbnail':str((folder/'thumbnail.png').relative_to(ROOT)),'duration':round(cursor,1),'voice':'eSpeak NG (suara sintetis dasar)'}
