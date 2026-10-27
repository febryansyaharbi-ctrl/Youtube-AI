import os, json, time
from datetime import timedelta
from urllib.parse import urlencode, urlparse
import httpx
from .db import Session, Connection, Job, now, setting
from .security import encrypt, decrypt
from .media import ROOT
SCOPES='https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly https://www.googleapis.com/auth/youtube.force-ssl'
class YouTubeError(Exception): pass

def config():
    with Session() as s: c=setting(s,'oauth',{})
    if not c: raise YouTubeError('OAuth Google belum dikonfigurasi.')
    return {'client_id':c['client_id'],'client_secret':decrypt(c['secret']),'redirect_uri':os.environ['PUBLIC_URL']+'/api/youtube/callback'}
def exchange(code):
    c=config()
    r=httpx.post('https://oauth2.googleapis.com/token',data={**c,'code':code,'grant_type':'authorization_code'},timeout=30)
    if r.status_code!=200: raise YouTubeError('Google menolak otorisasi. Periksa konfigurasi OAuth.')
    data=r.json();data['expires_at']=time.time()+data.get('expires_in',3600)
    return data

def token(user):
    with Session() as s:
        row=s.get(Connection,user)
        if not row: raise YouTubeError('Hubungkan channel YouTube dahulu.')
        data=json.loads(decrypt(row.encrypted))
        if data.get('expires_at',0)<time.time()+90:
            c=config()
            r=httpx.post('https://oauth2.googleapis.com/token',data={'client_id':c['client_id'],'client_secret':c['client_secret'],'refresh_token':data.get('refresh_token',''),'grant_type':'refresh_token'},timeout=30)
            if r.status_code!=200: raise YouTubeError('Sesi YouTube kedaluwarsa. Hubungkan ulang channel.')
            data.update(r.json());data['expires_at']=time.time()+data.get('expires_in',3600);row.encrypted=encrypt(json.dumps(data));s.commit()
        return data['access_token']

def request(user,path,params=None):
    r=httpx.get('https://www.googleapis.com/youtube/v3/'+path,params=params,headers={'Authorization':'Bearer '+token(user)},timeout=30)
    if r.status_code!=200: raise YouTubeError(f'YouTube API menolak permintaan ({r.status_code}). Periksa izin dan kuota di Google Cloud.')
    return r.json()

def sync(user):
    channel=request(user,'channels',{'part':'snippet,statistics','mine':'true'})
    if not channel.get('items'): raise YouTubeError('Akun Google belum memiliki channel YouTube.')
    item=channel['items'][0]
    today=now().date();start=today-timedelta(days=28)
    r=httpx.get('https://youtubeanalytics.googleapis.com/v2/reports',params={'ids':'channel==MINE','startDate':str(start),'endDate':str(today),'metrics':'views,estimatedMinutesWatched,averageViewDuration,subscribersGained','dimensions':'day','sort':'day'},headers={'Authorization':'Bearer '+token(user)},timeout=30)
    analytics=r.json() if r.status_code==200 else {'unavailable':True,'message':'Analitik belum tersedia. Periksa izin atau tunggu data channel.'}
    with Session() as s:
        row=s.get(Connection,user);row.channel=item;row.analytics=analytics;row.updated=now();s.commit()
    return {'channel':item,'analytics':analytics}

def save_upload(job_id,**values):
    with Session() as s:
        j=s.get(Job,job_id);j.result={**j.result,**values};s.commit()

def upload(job_id,user,payload,check,progress):
    with Session() as s: state=s.get(Job,job_id).result.copy()
    if state.get('youtube_id'): return state
    path=ROOT/payload['video'];size=path.stat().st_size
    headers={'Authorization':'Bearer '+token(user)}
    with httpx.Client(timeout=90,follow_redirects=False) as client:
        if state.get('_upload_uri'):
            uri=decrypt(state['_upload_uri'])
        else:
            if state.get('_initiated'):
                raise YouTubeError('Status inisialisasi upload belum pasti. Periksa YouTube Studio sebelum membuat upload baru.')
            save_upload(job_id,_initiated=True)
            response=client.post('https://www.googleapis.com/upload/youtube/v3/videos',params={'uploadType':'resumable','part':'snippet,status'},headers={**headers,'X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(size)},json={
                'snippet':{'title':payload['title'][:100],'description':payload['description'][:4800],'categoryId':'27','defaultLanguage':payload['language']},
                'status':{'privacyStatus':payload.get('privacy','private'),'selfDeclaredMadeForKids':payload['made_for_kids'],'containsSyntheticMedia':payload['synthetic']}})
            if response.status_code not in (200,201): raise YouTubeError(f'Inisialisasi upload ditolak ({response.status_code}). Periksa izin/kuota.')
            uri=response.headers.get('location','')
            if urlparse(uri).hostname not in ('www.googleapis.com','upload.youtube.com'): raise YouTubeError('Alamat upload tidak valid.')
            save_upload(job_id,_upload_uri=encrypt(uri))
        probe=client.put(uri,headers={**headers,'Content-Length':'0','Content-Range':f'bytes */{size}'})
        if probe.status_code in (200,201):
            result={'youtube_id':probe.json()['id'],'url':'https://youtu.be/'+probe.json()['id']};save_upload(job_id,**result);return result
        if probe.status_code!=308: raise YouTubeError('Sesi upload tidak dapat dilanjutkan. Periksa YouTube Studio untuk menghindari duplikasi.')
        offset=int(probe.headers.get('range','bytes=0--1').split('-')[-1])+1 if 'range' in probe.headers else 0
        with path.open('rb') as media:
            media.seek(offset)
            while offset<size:
                check();chunk=media.read(4*1024*1024);end=offset+len(chunk)-1
                response=client.put(uri,content=chunk,headers={**headers,'Content-Type':'video/mp4','Content-Range':f'bytes {offset}-{end}/{size}'})
                if response.status_code in (200,201):
                    result={'youtube_id':response.json()['id'],'url':'https://youtu.be/'+response.json()['id']};save_upload(job_id,**result);return result
                if response.status_code!=308: raise YouTubeError('Upload terhenti; ulangi untuk melanjutkan sesi yang sama.')
                offset=end+1;progress(int(95*offset/size),'Mengunggah ke YouTube')
    raise YouTubeError('Upload belum terkonfirmasi. Ulangi untuk memeriksa sesi yang sama.')
