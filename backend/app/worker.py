import os, time, json, threading, logging
from datetime import timedelta
from pathlib import Path
import redis
from celery import Celery
from sqlalchemy import select
from .db import Session, Job, Project, Asset, now, event
from .providers import get_provider, script_prompt
from .media import ROOT, Controlled, render
from . import youtube
log=logging.getLogger('creatorpilot')
queue=Celery('creatorpilot',broker=os.environ['REDIS_URL'])
queue.conf.update(task_acks_late=True,task_reject_on_worker_lost=True,worker_prefetch_multiplier=1,broker_transport_options={'visibility_timeout':7200},task_ignore_result=True,task_time_limit=7200)
cache=redis.Redis.from_url(os.environ['REDIS_URL'])

def progress(job_id,percent,stage):
    with Session() as s:
        j=s.get(Job,job_id);j.progress=percent;j.stage=stage;j.heartbeat=now();s.commit()

def check(job_id):
    with Session() as s:
        j=s.get(Job,job_id)
        if j.status in ('paused','cancelled'): raise Controlled(j.status)

def heartbeat(job_id,stop,lock):
    while not stop.wait(10):
        try:
            lock.extend(60,replace_ttl=True)
            with Session() as s:
                j=s.get(Job,job_id);j.heartbeat=now();s.commit()
        except Exception: return

@queue.task(name='creatorpilot.run')
def execute(job_id):
    lock=cache.lock('job:'+job_id,timeout=60,blocking_timeout=0,thread_local=False)
    if not lock.acquire(blocking=False): return
    stop=threading.Event()
    try:
        with Session() as s:
            j=s.get(Job,job_id)
            if not j or j.status not in ('queued','running'): return
            j.status='running';j.attempts+=1;j.heartbeat=now();j.error='';s.commit()
            p=s.get(Project,j.project_id) if j.project_id else None
            payload=j.payload.copy();kind=j.kind;user=j.user_id
        threading.Thread(target=heartbeat,args=(job_id,stop,lock),daemon=True).start()
        guard=lambda:check(job_id)
        report=lambda pct,stage:progress(job_id,pct,stage)
        guard()
        if kind in ('script','pipeline') and not payload.get('script_done'):
            report(5,'AI sedang menyusun naskah orisinal')
            data=get_provider().generate(script_prompt(p),guard)
            script=data.get('script','')
            if not isinstance(script,str) or len(script)<40: raise RuntimeError('AI menghasilkan naskah kosong. Coba ulangi.')
            with Session() as s:
                project=s.get(Project,p.id)
                if project.revision!=payload['revision']: raise RuntimeError('Proyek berubah sejak job dibuat.')
                project.revision+=1
                project.script=script[:15000];project.description=str(data.get('description',''))[:4800];project.approved=False
                project.result={**project.result,'fact_check':data.get('fact_check',[]),'tags':data.get('tags',[])}
                j=s.get(Job,job_id);j.payload={**j.payload,'script_done':True,'revision':project.revision};s.commit();p=project
            result={'message':'Naskah tersedia. Periksa fakta dan orisinalitas sebelum publikasi.'}
        if kind in ('render','pipeline'):
            if not p.script.strip(): raise RuntimeError('Isi naskah sebelum merender video.')
            folder=ROOT/'renders'/p.id/job_id
            background=None
            if payload.get('asset_id'):
                with Session() as s:
                    asset=s.get(Asset,payload['asset_id'])
                    if not asset or asset.user_id!=user or not asset.mime.startswith('image/'): raise RuntimeError('Aset latar tidak valid.')
                    background=ROOT/asset.path
            result=render(p,folder,guard,report,background)
            guard()
            with Session() as s:
                project=s.get(Project,p.id)
                project.result={**project.result,**result,'render_revision':project.revision};project.approved=False;s.commit()
        elif kind=='mentor':
            report(10,'Menganalisis niche dan menyusun misi')
            result=get_provider().generate('Respond in Indonesian. Build a practical YouTube strategy for a beginner. Niche: '+payload['niche']+'. Audience: '+payload['audience']+'. JSON keys: positioning (string), pillars (array of 3 strings), ideas (array of 7 objects with title, hook), missions (array of 5 strings), cautions (array of strings). No guarantees of revenue. Do not invent search volumes.',guard)
        elif kind=='analytics':
            report(20,'Mengambil data resmi YouTube');result=youtube.sync(user)
        elif kind=='upload':
            result=youtube.upload(job_id,user,payload,guard,report)
        elif kind=='transcribe':
            from faster_whisper import WhisperModel
            with Session() as s: asset=s.get(Asset,payload['asset_id'])
            if not asset or asset.user_id!=user: raise RuntimeError('Aset tidak ditemukan.')
            report(5,'Memuat Whisper; unduhan model pertama mungkin diperlukan')
            model=WhisperModel('tiny',device='cpu',compute_type='int8',cpu_threads=2,download_root='/data/models/whisper')
            items,info=model.transcribe(str(ROOT/asset.path),language=payload.get('language','id'),beam_size=1)
            from .media import srt_time
            subtitles=[];transcript=[]
            for i,item in enumerate(items):
                guard();subtitles.append(f'{i+1}\n{srt_time(item.start)} --> {srt_time(item.end)}\n{item.text.strip()}\n');transcript.append({'start':item.start,'end':item.end,'text':item.text.strip()});report(min(95,int(item.end/max(info.duration,1)*100)),'Mentranskripsi audio')
            folder=ROOT/'transcripts'/job_id;folder.mkdir(parents=True,exist_ok=True)
            (folder/'subtitles.srt').write_text('\n'.join(subtitles));result={'transcript':transcript,'subtitles':str((folder/'subtitles.srt').relative_to(ROOT))}
        elif kind=='highlights':
            with Session() as s: source=s.get(Job,payload['transcript_job'])
            report(10,'Menganalisis poin penting dari transkrip')
            result=get_provider().generate('In Indonesian, select useful segments from this timestamped transcript. Do not invent timestamps. JSON keys: highlights (array of objects start, end, reason). Transcript: '+json.dumps(source.result.get('transcript',[]))[:10000],guard)
        elif kind=='captions':
            report(10,'Mengambil caption melalui API resmi')
            tracks=youtube.request(user,'captions',{'part':'snippet','videoId':payload['video_id']})
            if not tracks.get('items'): raise RuntimeError('Caption tidak tersedia. Unggah SRT atau audio milik Anda.')
            import httpx
            r=httpx.get('https://www.googleapis.com/youtube/v3/captions/'+tracks['items'][0]['id'],params={'tfmt':'srt'},headers={'Authorization':'Bearer '+youtube.token(user)},timeout=40)
            if r.status_code!=200: raise RuntimeError('Google mensyaratkan izin mengedit video untuk mengambil caption. Gunakan video milik channel terhubung.')
            folder=ROOT/'transcripts'/job_id;folder.mkdir(parents=True,exist_ok=True);(folder/'subtitles.srt').write_text(r.text)
            result={'subtitles':str((folder/'subtitles.srt').relative_to(ROOT)),'text':r.text}
        guard()
        with Session() as s:
            j=s.get(Job,job_id);j.status='completed';j.progress=100;j.stage='Selesai';j.result={**j.result,**result};j.heartbeat=now();event(s,user,'job.completed',kind);s.commit()
        log.info(json.dumps({'event':'job.completed','job_id':job_id,'kind':kind}))
    except Controlled: pass
    except Exception as error:
        # Never expose upstream response bodies, credentials, or resumable URLs.
        safe=str(error) if isinstance(error,(RuntimeError,youtube.YouTubeError)) else 'Proses gagal ('+type(error).__name__+'). Periksa koneksi/model lalu coba ulangi.'
        with Session() as s:
            j=s.get(Job,job_id)
            if j and j.status not in ('paused','cancelled'):
                j.status='failed';j.error=safe[:500];j.stage='Perlu perhatian';s.commit()
        log.error(json.dumps({'event':'job.failed','job_id':job_id,'type':type(error).__name__}))
    finally:
        stop.set()
        try: lock.release()
        except Exception: pass
