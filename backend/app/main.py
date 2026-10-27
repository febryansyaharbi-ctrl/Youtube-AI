import os, json, secrets, hashlib, shutil, re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from urllib.parse import urlencode, urlparse, parse_qs
import httpx, psutil
from fastapi import FastAPI, Depends, Request, Response, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from PIL import Image
from .db import Base, engine, Session, User, Login, Project, Job, Asset, Setting, Connection, Event, now, uid, setting, set_setting, event
from .security import ph, current, digest, encrypt, decrypt
from .worker import cache
from .media import ROOT
from . import youtube
PUBLIC_URL=os.environ['PUBLIC_URL'].rstrip('/')
ACTIVE=('queued','running','paused','scheduled')

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with Session() as s:
        if not s.scalar(select(User).limit(1)):
            s.add(User(username=os.environ.get('ADMIN_USER','harnet'),password=ph.hash(os.environ['ADMIN_PASSWORD'])))
        if not s.get(Setting,'brand'): set_setting(s,'brand',{'name':'CreatorPilot AI'})
        s.commit()
    yield
app=FastAPI(title='CreatorPilot API',lifespan=lifespan,docs_url=None,redoc_url=None)

@app.middleware('http')
async def guards(req,call_next):
    if req.method not in ('GET','HEAD','OPTIONS'):
        origin=req.headers.get('origin')
        if origin and origin!=PUBLIC_URL: return Response('Origin tidak diizinkan',403)
    response=await call_next(req)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    return response

def limit(key,maximum,seconds):
    count=cache.incr(key)
    if count==1: cache.expire(key,seconds)
    if count>maximum: raise HTTPException(429,'Terlalu banyak permintaan. Tunggu sebentar.')
def own(s,model,id,user):
    item=s.get(model,id)
    if not item or item.user_id!=user: raise HTTPException(404,'Data tidak ditemukan.')
    return item

def job_dict(j):
    return {'id':j.id,'project_id':j.project_id,'kind':j.kind,'status':j.status,'progress':j.progress,'stage':j.stage,'result':{k:v for k,v in j.result.items() if not k.startswith('_')},'error':j.error,'created':j.created,'due':j.due,'attempts':j.attempts}
def project_dict(p): return {key:getattr(p,key) for key in ('id','title','niche','audience','language','format','mode','script','description','result','rights','approved','made_for_kids','synthetic','revision','created')}

@app.get('/api/health')
def health():
    try:
        with Session() as s: s.execute(text('SELECT 1'))
        cache.ping()
        return {'status':'ok','version':'0.1.0'}
    except Exception: raise HTTPException(503,'Layanan belum siap')
@app.get('/api/brand')
def brand():
    with Session() as s: return setting(s,'brand',{'name':'CreatorPilot AI'})
class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=100)
    password:str=Field(min_length=1,max_length=200)
@app.post('/api/login')
def login(data:Credentials,res:Response,req:Request):
    # Global per-account limit prevents proxy/header spoofing from bypassing controls.
    limit('login:'+digest(data.username.lower()),10,300)
    with Session() as s:
        user=s.scalar(select(User).where(User.username==data.username))
        try:
            if not user: ph.verify(ph.hash('dummy-verification'),data.password);raise ValueError()
            ph.verify(user.password,data.password)
        except Exception: raise HTTPException(401,'Username atau password salah.')
        token=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(24)
        s.add(Login(token=digest(token),user_id=user.id,csrf=csrf,expires=now()+timedelta(days=7)));event(s,user.id,'login');s.commit()
    res.set_cookie('cp_session',token,httponly=True,secure=PUBLIC_URL.startswith('https'),samesite='lax',max_age=604800,path='/')
    return {'csrf':csrf,'username':user.username}
@app.get('/api/me')
def me(req:Request,user=Depends(current)):
    with Session() as s:
        login=s.get(Login,digest(req.cookies['cp_session']))
        return {'username':s.get(User,user).username,'csrf':login.csrf}
@app.post('/api/logout')
def logout(req:Request,res:Response,user=Depends(current)):
    with Session() as s:
        s.delete(s.get(Login,digest(req.cookies['cp_session'])));s.commit()
    res.delete_cookie('cp_session');return {'ok':True}
class PasswordChange(BaseModel):
    current_password:str
    new_password:str=Field(min_length=12,max_length=200)
@app.post('/api/password')
def password(data:PasswordChange,user=Depends(current)):
    with Session() as s:
        u=s.get(User,user)
        try: ph.verify(u.password,data.current_password)
        except Exception: raise HTTPException(400,'Password lama salah.')
        u.password=ph.hash(data.new_password)
        for row in s.scalars(select(Login).where(Login.user_id==user)): s.delete(row)
        event(s,user,'password.changed');s.commit()
    return {'ok':True}

@app.get('/api/dashboard')
def dashboard(user=Depends(current)):
    with Session() as s:
        projects=list(s.scalars(select(Project).where(Project.user_id==user)))
        jobs=list(s.scalars(select(Job).where(Job.user_id==user).order_by(Job.created.desc()).limit(100)))
        connection=s.get(Connection,user)
        disk=shutil.disk_usage(ROOT)
        return {'projects':len(projects),'videos':sum(bool(p.result.get('video')) for p in projects),'active_jobs':sum(j.status in ACTIVE for j in jobs),'completed_jobs':sum(j.status=='completed' for j in jobs),'recent_jobs':[job_dict(j) for j in jobs[:5]],'channel':connection.channel if connection else None,'analytics':connection.analytics if connection else None,'synced_at':connection.updated if connection else None,'resources':{'disk_free_gb':round(disk.free/1024**3,1),'disk_used_gb':round(disk.used/1024**3,1),'ram_available_gb':round(psutil.virtual_memory().available/1024**3,1),'cpu_percent':psutil.cpu_percent(),'workers':1},'missions':setting(s,'missions:'+user,{'done':[]})}
class Missions(BaseModel): done:list[int]=Field(max_length=20)
@app.put('/api/missions')
def missions(data:Missions,user=Depends(current)):
    with Session() as s: set_setting(s,'missions:'+user,data.model_dump());s.commit()
    return data
class ProjectData(BaseModel):
    title:str=Field(min_length=3,max_length=150)
    niche:str=Field(default='Edukasi',max_length=200)
    audience:str=Field(default='Pemula',max_length=300)
    language:str=Field(default='id',pattern='^(id|en)$')
    format:str=Field(default='short',pattern='^(short|long)$')
    mode:str=Field(default='semi',pattern='^(manual|semi|auto)$')
    script:str=Field(default='',max_length=15000)
    description:str=Field(default='',max_length=4800)
    rights:bool=False
    approved:bool=False
    made_for_kids:bool=False
    synthetic:bool=True
@app.get('/api/projects')
def projects(user=Depends(current)):
    with Session() as s: return [project_dict(p) for p in s.scalars(select(Project).where(Project.user_id==user).order_by(Project.created.desc()))]
@app.post('/api/projects')
def create_project(data:ProjectData,user=Depends(current)):
    limit('create:'+user,30,3600)
    with Session() as s:
        p=Project(user_id=user,**data.model_dump());s.add(p);s.commit();return project_dict(p)
@app.put('/api/projects/{id}')
def update_project(id:str,data:ProjectData,user=Depends(current)):
    with Session() as s:
        p=s.scalar(select(Project).where(Project.id==id,Project.user_id==user).with_for_update())
        if not p: raise HTTPException(404,'Proyek tidak ditemukan.')
        if s.scalar(select(Job).where(Job.project_id==id,Job.status.in_(ACTIVE))): raise HTTPException(409,'Selesaikan atau batalkan job proyek sebelum mengedit.')
        changed=any(getattr(p,k)!=getattr(data,k) for k in ('script','title','language','format'))
        for k,v in data.model_dump().items(): setattr(p,k,v)
        if changed: p.revision+=1;p.approved=False
        s.commit();return project_dict(p)

class JobRequest(BaseModel):
    kind:str=Field(pattern='^(script|render|pipeline|mentor|analytics|upload|transcribe|highlights|captions)$')
    project_id:str|None=None
    idempotency_key:str=Field(min_length=8,max_length=100)
    payload:dict=Field(default_factory=dict)
    due:datetime|None=None
    accept_estimate:bool=False

def estimate(kind,project=None):
    long=project and project.format=='long'
    return {'api_cost_idr':0,'billing':'Lokal; tidak memakai API AI berbayar. Resource VPS tetap digunakan.','estimated_minutes':'5–25' if kind in ('script','mentor','pipeline') else ('3–15' if kind=='render' else '1–10'),'estimated_ram_gb':3.5 if kind in ('script','mentor','pipeline','highlights') else 1.5,'estimated_disk_mb':300 if long else 100,'concurrency':1,'upload_budget':'Batas aplikasi 10 upload/hari; kuota Google aktual mengikuti proyek Google Cloud.','note':'Perkiraan awal, bukan benchmark. Kecepatan bergantung panjang konten dan beban server.'}
@app.post('/api/estimate')
def get_estimate(data:JobRequest,user=Depends(current)):
    with Session() as s: return estimate(data.kind,own(s,Project,data.project_id,user) if data.project_id else None)
@app.post('/api/jobs')
def create_job(data:JobRequest,user=Depends(current)):
    if not data.accept_estimate: raise HTTPException(400,'Setujui estimasi resource sebelum memulai.')
    limit('jobs:'+user,30,3600)
    with Session() as s:
        existing=s.scalar(select(Job).where(Job.user_id==user,Job.idempotency_key==data.idempotency_key))
        if existing: return job_dict(existing)
        p=None;payload={}
        if data.kind in ('script','render','pipeline','upload'):
            p=s.scalar(select(Project).where(Project.id==data.project_id,Project.user_id==user).with_for_update())
            if not p: raise HTTPException(404,'Proyek tidak ditemukan.')
            if s.scalar(select(Job).where(Job.project_id==p.id,Job.status.in_(ACTIVE))): raise HTTPException(409,'Proyek ini sudah memiliki pekerjaan aktif.')
            payload={'revision':p.revision}
            if data.kind=='render' and not p.script.strip(): raise HTTPException(400,'Naskah masih kosong.')
            if len(p.script.split())>1500 and data.kind=='render': raise HTTPException(400,'Batasi naskah hingga 1.500 kata untuk kapasitas server ini.')
            if data.payload.get('asset_id'):
                a=own(s,Asset,data.payload['asset_id'],user)
                if not a.mime.startswith('image/'): raise HTTPException(400,'Latar harus berupa gambar.')
                payload['asset_id']=a.id
            if data.kind=='upload':
                if not p.rights or not p.approved: raise HTTPException(400,'Tinjau video dan konfirmasi hak penggunaan sebelum upload.')
                if not p.result.get('video') or p.result.get('render_revision')!=p.revision: raise HTTPException(400,'Render ulang setelah mengubah naskah/judul.')
                if not s.get(Connection,user): raise HTTPException(400,'Hubungkan YouTube terlebih dahulu.')
                old=list(s.scalars(select(Job).where(Job.project_id==p.id,Job.kind=='upload')))
                if any(j.payload.get('revision')==p.revision and (j.result.get('_initiated') or j.status!='cancelled') for j in old): raise HTTPException(409,'Versi ini sudah memiliki upload. Lanjutkan job sebelumnya untuk menghindari duplikasi.')
                privacy=data.payload.get('privacy','private')
                if privacy not in ('private','unlisted','public'): raise HTTPException(400,'Privasi tidak valid.')
                payload.update({k:getattr(p,k) for k in ('title','description','language','made_for_kids','synthetic')});payload.update(video=p.result['video'],privacy=privacy)
                limit('uploads:'+user+':'+now().strftime('%Y%m%d'),10,86400)
        elif data.kind=='mentor':
            payload={'niche':str(data.payload.get('niche','Edukasi'))[:200],'audience':str(data.payload.get('audience','Pemula'))[:300]}
        elif data.kind=='transcribe':
            asset=own(s,Asset,data.payload.get('asset_id',''),user)
            if not asset.mime.startswith(('audio/','video/')): raise HTTPException(400,'Pilih aset audio/video.')
            payload={'asset_id':asset.id,'language':data.payload.get('language','id')}
            if payload['language'] not in ('id','en'): raise HTTPException(400,'Bahasa tidak didukung.')
        elif data.kind=='highlights':
            source=own(s,Job,data.payload.get('transcript_job',''),user)
            if not source.result.get('transcript'): raise HTTPException(400,'Pilih transkripsi yang sudah selesai.')
            payload={'transcript_job':source.id}
        elif data.kind=='captions':
            video=str(data.payload.get('video_id',''))
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video): raise HTTPException(400,'Video ID tidak valid.')
            if not s.get(Connection,user): raise HTTPException(400,'Hubungkan YouTube terlebih dahulu.')
            payload={'video_id':video}
        elif data.kind=='analytics' and not s.get(Connection,user): raise HTTPException(400,'Hubungkan YouTube terlebih dahulu.')
        if data.due and (not data.due.tzinfo or data.due<=now()): raise HTTPException(400,'Jadwal harus di masa depan dan menyertakan zona waktu.')
        if shutil.disk_usage(ROOT).free<2*1024**3: raise HTTPException(507,'Ruang disk tersisa kurang dari 2 GB. Bersihkan media dahulu.')
        j=Job(user_id=user,project_id=p.id if p else None,kind=data.kind,payload=payload,idempotency_key=data.idempotency_key,due=data.due,status='scheduled' if data.due else 'queued')
        s.add(j);event(s,user,'job.created',data.kind)
        try: s.commit()
        except IntegrityError:
            s.rollback();j=s.scalar(select(Job).where(Job.user_id==user,Job.idempotency_key==data.idempotency_key))
            if not j: raise HTTPException(409,'Konflik antrean. Muat ulang.')
        return job_dict(j)
@app.get('/api/jobs')
def jobs(user=Depends(current)):
    with Session() as s: return [job_dict(j) for j in s.scalars(select(Job).where(Job.user_id==user).order_by(Job.created.desc()).limit(200))]
@app.post('/api/jobs/{id}/{action}')
def control(id:str,action:str,user=Depends(current)):
    with Session() as s:
        j=own(s,Job,id,user)
        if action=='pause' and j.status in ('queued','running','scheduled'): j.status='paused';j.stage='Dijeda; checkpoint tersimpan'
        elif action=='cancel' and j.status in ACTIVE: j.status='cancelled';j.stage='Dibatalkan'
        elif action in ('resume','retry') and j.status in ('paused','failed','cancelled'):
            if j.kind=='upload' and j.result.get('youtube_id'): raise HTTPException(409,'Video sudah diunggah.')
            if cache.exists('job:'+id): raise HTTPException(409,'Worker sedang berhenti. Coba lagi beberapa detik.')
            if j.project_id:
                p=own(s,Project,j.project_id,user)
                if p.revision!=j.payload.get('revision'): raise HTTPException(409,'Proyek telah berubah. Buat pekerjaan baru.')
                if s.scalar(select(Job).where(Job.project_id==j.project_id,Job.id!=id,Job.status.in_(ACTIVE))): raise HTTPException(409,'Proyek memiliki job aktif lain.')
            j.status='scheduled' if j.due and j.due>now() else 'queued';j.dispatched=None;j.error='';j.stage='Menunggu dilanjutkan'
        else: raise HTTPException(409,'Tindakan tidak sesuai status job.')
        event(s,user,'job.'+action,id);s.commit();return job_dict(j)

@app.get('/api/assets')
def assets(user=Depends(current)):
    with Session() as s: return [{'id':a.id,'name':a.name,'mime':a.mime,'size':a.size,'license':a.license} for a in s.scalars(select(Asset).where(Asset.user_id==user).order_by(Asset.created.desc()))]
@app.post('/api/assets')
async def add_asset(file:UploadFile=File(...),license:str=Form(...),user=Depends(current)):
    if not license.strip() or len(license)>500: raise HTTPException(400,'Tuliskan sumber dan hak penggunaan aset.')
    ext=Path(file.filename or '').suffix.lower()
    types={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.mp4':'video/mp4','.mp3':'audio/mpeg','.wav':'audio/wav','.m4a':'audio/mp4'}
    if ext not in types: raise HTTPException(400,'Format didukung: PNG, JPG, WebP, MP4, MP3, WAV, M4A.')
    if shutil.disk_usage(ROOT).free<2*1024**3: raise HTTPException(507,'Ruang penyimpanan hampir penuh.')
    id=uid();rel=f'assets/{user}/{id}{ext}';path=ROOT/rel;path.parent.mkdir(parents=True,exist_ok=True);size=0;sha=hashlib.sha256()
    try:
        with path.open('wb') as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>200*1024**2: raise HTTPException(413,'Maksimal 200 MB per aset.')
                sha.update(chunk);out.write(chunk)
        if types[ext].startswith('image/'):
            with Image.open(path) as image:
                if image.width*image.height>40_000_000: raise HTTPException(400,'Resolusi gambar terlalu besar.')
                image.verify()
        else:
            from .media import duration
            if duration(path)>1800: raise HTTPException(400,'Maksimal durasi aset 30 menit.')
        with Session() as s:
            old=s.scalar(select(Asset).where(Asset.user_id==user,Asset.sha256==sha.hexdigest()))
            if old: path.unlink();return {'id':old.id,'duplicate':True}
            s.add(Asset(id=id,user_id=user,name=(file.filename or 'asset')[:200],path=rel,mime=types[ext],size=size,sha256=sha.hexdigest(),license=license));s.commit()
        return {'id':id}
    except HTTPException: path.unlink(missing_ok=True);raise
    except Exception: path.unlink(missing_ok=True);raise HTTPException(400,'File media tidak dapat dibaca.')
@app.get('/api/media')
def download(path:str,user=Depends(current)):
    target=(ROOT/path).resolve()
    if not target.is_relative_to(ROOT.resolve()) or not target.is_file(): raise HTTPException(404)
    with Session() as s:
        values=[]
        for p in s.scalars(select(Project).where(Project.user_id==user)): values.extend(p.result.get(k) for k in ('video','subtitles','thumbnail'))
        for j in s.scalars(select(Job).where(Job.user_id==user)): values.extend(j.result.get(k) for k in ('video','subtitles','thumbnail'))
        values.extend(s.scalars(select(Asset.path).where(Asset.user_id==user)))
        if path not in values: raise HTTPException(404)
    return FileResponse(target)

@app.get('/api/settings')
def settings(user=Depends(current)):
    with Session() as s:
        return {'brand':setting(s,'brand'),'ai':setting(s,'ai',{'model':'qwen3:4b'}),'oauth_configured':bool(setting(s,'oauth')),'youtube_connected':bool(s.get(Connection,user)),'redirect_uri':PUBLIC_URL+'/api/youtube/callback','providers':{'llm':'Ollama lokal','tts':'eSpeak NG — suara sintetis dasar','video':'FFmpeg — video teks/slide dengan aset Anda','stt':'faster-whisper tiny CPU'},'paid_enabled':False}
class Brand(BaseModel): name:str=Field(min_length=2,max_length=50)
@app.put('/api/settings/brand')
def brand_update(data:Brand,user=Depends(current)):
    with Session() as s: set_setting(s,'brand',data.model_dump());event(s,user,'brand.updated');s.commit()
    return data
class OAuthConfig(BaseModel):
    client_id:str=Field(min_length=10,max_length=300)
    client_secret:str=Field(min_length=10,max_length=300)
@app.put('/api/settings/oauth')
def oauth_config(data:OAuthConfig,user=Depends(current)):
    if not data.client_id.endswith('.apps.googleusercontent.com'): raise HTTPException(400,'Gunakan OAuth client ID aplikasi web Google.')
    with Session() as s: set_setting(s,'oauth',{'client_id':data.client_id,'secret':encrypt(data.client_secret)});event(s,user,'oauth.configured');s.commit()
    return {'ok':True}
@app.get('/api/providers/status')
def providers(user=Depends(current)):
    try:
        result=httpx.get(os.getenv('OLLAMA_URL','http://ollama:11434')+'/api/tags',timeout=5)
        models=[m['name'] for m in result.json().get('models',[])]
    except Exception: models=[]
    return {'ollama':bool(models),'models':models,'ffmpeg':bool(shutil.which('ffmpeg')),'tts':bool(shutil.which('espeak-ng'))}
@app.post('/api/youtube/connect')
def connect(user=Depends(current)):
    try: c=youtube.config()
    except youtube.YouTubeError as e: raise HTTPException(400,str(e))
    state=secrets.token_urlsafe(32);cache.setex('oauth:'+state,600,user)
    return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':c['client_id'],'redirect_uri':c['redirect_uri'],'response_type':'code','scope':youtube.SCOPES,'access_type':'offline','prompt':'consent','state':state})}
@app.get('/api/youtube/callback')
def callback(state:str='',code:str='',error:str='',user=Depends(current)):
    owner=cache.getdel('oauth:'+state)
    if not owner or owner.decode()!=user: raise HTTPException(400,'Sesi OAuth tidak valid atau kedaluwarsa.')
    if error or not code: return RedirectResponse('/?youtube=denied')
    try: data=youtube.exchange(code)
    except youtube.YouTubeError as e: raise HTTPException(400,str(e))
    with Session() as s:
        row=s.get(Connection,user)
        if row:
            old=json.loads(decrypt(row.encrypted))
            if not data.get('refresh_token'): data['refresh_token']=old.get('refresh_token')
            row.encrypted=encrypt(json.dumps(data));row.updated=now()
        else: s.add(Connection(user_id=user,encrypted=encrypt(json.dumps(data))))
        event(s,user,'youtube.connected');s.commit()
    return RedirectResponse('/?youtube=connected')
@app.post('/api/youtube/disconnect')
def disconnect(user=Depends(current)):
    with Session() as s:
        row=s.get(Connection,user)
        if row:
            data=json.loads(decrypt(row.encrypted))
            try: httpx.post('https://oauth2.googleapis.com/revoke',data={'token':data.get('refresh_token',data['access_token'])},timeout=15)
            except Exception: pass
            s.delete(row)
        for j in s.scalars(select(Job).where(Job.user_id==user,Job.kind=='upload',Job.status.in_(ACTIVE))): j.status='cancelled'
        event(s,user,'youtube.disconnected');s.commit()
    return {'ok':True}
@app.get('/api/events')
def events(user=Depends(current)):
    with Session() as s: return [{'action':e.action,'detail':e.detail,'created':e.created} for e in s.scalars(select(Event).where(Event.user_id==user).order_by(Event.created.desc()).limit(100))]
