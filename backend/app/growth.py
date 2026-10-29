"""Additive channel onboarding and content planning; no external paid calls."""
import re
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs, quote
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from .db import Session, setting, set_setting, Project, Job, event, now
from . import youtube

NICHE_TOPICS = {
 'Faceless Tech & Future Gadgets':['privasi smartphone','alat AI untuk belajar','memilih gadget sesuai kebutuhan','otomasi pekerjaan rutin','keamanan akun','fitur aksesibilitas','backup foto','rumah pintar','mitos baterai','membandingkan spesifikasi'],
 'True Crime & Mystery Storytelling':['membedakan fakta dan spekulasi','kronologi kasus terdokumentasi','bias saksi mata','jejak digital','misteri sejarah','etika bercerita tentang korban','membaca sumber primer','teknik investigasi','hoaks kasus viral','pelajaran keamanan pribadi'],
 'Finance, Wealth & Business Case Studies':['anggaran bulanan','dana darurat','model bisnis warung','biaya tersembunyi','arus kas usaha','kebiasaan menabung','risiko investasi','harga dan margin','studi kegagalan usaha','literasi pinjaman'],
 'Daily Motivation, Mindset & Stoicism':['kebiasaan kecil','lingkar kendali','mengatasi penundaan','refleksi harian','disiplin realistis','menghadapi kritik','fokus satu tugas','tujuan mingguan','istirahat berkualitas','evaluasi kemajuan'],
 'Pop Culture, Movie Analysis & Entertainment':['struktur cerita','motivasi karakter','simbol visual','musik dan suasana','perjalanan pahlawan','adaptasi buku','sudut pandang narator','ending terbuka','desain dunia','kritik tanpa spoiler'],
 'Health, Fitness & Biohacking':['rutinitas jalan kaki','tidur teratur','teknik pemanasan','membaca label makanan','hidrasi sehari-hari','istirahat latihan','mitos kebugaran','postur saat bekerja','membangun kebiasaan sehat','menilai klaim kesehatan'],
 'Educational Science & Fun Facts':['mengapa langit biru','energi sehari-hari','siklus air','ilusi optik','gravitasi','suara dan getaran','ekosistem kecil','metode ilmiah','listrik statis','skala tata surya'],
 'Gaming News, Lore & Esports Highlights':['strategi pemula','membaca patch resmi','lore karakter','komunikasi tim','analisis replay sendiri','pengaturan aksesibilitas','latihan mekanik','desain level','etika komunitas','manajemen waktu bermain'],
 'Tutorial Software & Produktivitas':['shortcut keyboard','spreadsheet pemula','organisasi file','presentasi jelas','backup dokumen','kolaborasi daring','catatan digital','otomasi sederhana','email efektif','fokus kerja'],
 'Sejarah & Budaya Nusantara':['sumber sejarah lokal','tradisi lisan','arsitektur daerah','sejarah kuliner','jalur perdagangan','aksara daerah','museum lokal','perubahan kota','warisan kerajinan','membandingkan arsip'],
 'Kuliner Rumahan Hemat':['menu mingguan','persiapan bahan','penyimpanan sayur','resep satu panci','bekal sederhana','bumbu dasar','takaran dapur','sisa bahan','membandingkan bahan','kebersihan dapur'],
 'Belajar Bahasa Inggris':['perkenalan diri','percakapan kerja','pengucapan dasar','kosakata harian','mendengar aktif','menulis email','ungkapan sopan','kesalahan umum','latihan cerita','evaluasi belajar'],
 'Travel Lokal & Hidden Gems':['rencana perjalanan lokal','transportasi umum','etika berkunjung','anggaran wisata','kuliner daerah','rute jalan kaki','wisata sejarah','persiapan barang','catatan perjalanan','wisata bertanggung jawab'],
 'Parenting & Aktivitas Keluarga':['bermain tanpa layar','membaca bersama','rutinitas keluarga','komunikasi empatik','aktivitas kreatif','keamanan digital','tugas rumah bersama','mengelola emosi','waktu berkualitas','belajar dari lingkungan'],
 'DIY, Kerajinan & Home Living':['organisasi meja','perbaikan sederhana','daur ulang kardus','tanaman pemula','dekorasi hemat','alat dasar','pencahayaan ruang','perawatan barang','kerajinan kertas','proyek akhir pekan'],
 'Karier & Freelance Pemula':['portofolio pertama','menulis CV','persiapan wawancara','komunikasi klien','menentukan lingkup kerja','manajemen waktu','belajar keterampilan','menangani revisi','mencari pengalaman','evaluasi proyek']}

STEPS=[
 ('direction','Pilih arah channel','Pilih satu niche dan satu kelompok penonton di bawah. Tuliskan masalah mereka yang ingin Anda bantu. Hasil: janji manfaat channel yang spesifik.','https://www.youtube.com/creators/'),
 ('account','Buat channel pertama','Masuk ke YouTube memakai akun Google Anda. Foto profil → Setelan → Tambahkan atau kelola channel → Buat channel. Isi nama, handle, dan foto. Simpan URL channel di profil mentor. Pembuatan akun dilakukan langsung oleh Anda.','https://support.google.com/youtube/answer/1646861?hl=id'),
 ('brand','Atur identitas channel','Buka YouTube Studio → Penyesuaian → Profil. Pasang foto, banner, nama, handle, dan deskripsi. Jelaskan siapa penonton Anda, manfaat channel, dan jadwal setiap tiga hari. Klik Publikasikan.','https://support.google.com/youtube/answer/3027950?hl=id'),
 ('settings','Selesaikan setelan dasar','YouTube Studio → Setelan: periksa negara, bahasa, default upload privat, izin channel, dan pengaturan audiens. Tentukan dibuat untuk anak-anak berdasarkan isi sebenarnya, bukan demi jangkauan. Periksa kelayakan fitur dan verifikasi yang diminta YouTube. Aktifkan keamanan dua langkah akun Google.','https://studio.youtube.com/'),
 ('research','Riset 5 channel dalam niche','Cari lima channel yang melayani audiens serupa. Catat pertanyaan penonton, struktur hook dan bagian yang belum dijawab. Jangan menyalin naskah, suara, atau visual. Pilih tiga pilar konten dari kebutuhan penonton.','https://www.youtube.com/'),
 ('plan','Susun kalender 90 hari','Buka Kalender 90 hari. Tentukan tanggal hari pertama dan jam WIB. Sistem menyusun 30 slot pada hari 3, 6, hingga 90, bergantian AI, Clip, Prompt. Edit ide agar memakai pengalaman dan contoh Anda. Kalender adalah rencana, belum perintah upload.',''),
 ('produce','Produksi video pertama','Buat proyek dari kalender. AI: tulis/periksa naskah dan render. Clip: unggah file asli berizin, transkripsi, tinjau rentang, render multi-clip. Prompt: susun prompt visual lalu unggah hasil visual milik Anda sebagai latar.',''),
 ('review','Tinjau sebelum publikasi','Putar hasil sampai selesai. Periksa fakta, salah ucap, subtitle, pacing, lisensi aset/audio dan privasi orang. Tambahkan komentar atau penjelasan orisinal untuk cuplikan. Pemotongan dan subtitle saja tidak menjamin monetisasi.','https://support.google.com/youtube/answer/2797466?hl=id'),
 ('publish','Upload pertama & hubungkan akun','Anda dapat upload manual di YouTube Studio. Untuk otomasi, isi OAuth Google di Pengaturan, lalu setujui akses sendiri. Mulai privat, tinjau pemeriksaan YouTube, isi judul/deskripsi/audiens dan pengungkapan sintetis sesuai isi. Publikasikan setelah siap.','https://studio.youtube.com/'),
 ('improve','Evaluasi dan lanjutkan','Setelah ada data, baca retensi, klik thumbnail dan komentar. Bandingkan dengan video Anda sebelumnya; ubah satu hal tiap percobaan. Cek tab Penghasilan YouTube Studio untuk kelayakan aktual. Monetisasi ditinjau YouTube dan tidak dijamin.','https://studio.youtube.com/')]

class ChannelProfile(BaseModel):
    niche:str=Field(min_length=3,max_length=200)
    audience:str=Field(min_length=3,max_length=300)
    language:str=Field(default='id',pattern='^(id|en)$')
    channel_name:str=Field(default='',max_length=100)
    channel_url:str=Field(default='',max_length=250)
    goal:str=Field(default='',max_length=500)
    done:list[str]=Field(default_factory=list,max_length=10)

def profile(s,user): return setting(s,'channel:'+user,{})

def youtube_id(url):
    p=urlparse(url)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443): raise ValueError('Gunakan URL HTTPS YouTube resmi.')
    if p.hostname=='youtu.be': vid=p.path.strip('/')
    elif p.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
        vid=parse_qs(p.query).get('v',[''])[0] if p.path=='/watch' else (p.path.split('/')[2] if p.path.startswith(('/shorts/','/embed/','/live/')) else '')
    else: raise ValueError('Domain harus youtube.com atau youtu.be.')
    if not re.fullmatch(r'[\w-]{11}',vid,flags=re.ASCII): raise ValueError('ID video tidak valid.')
    return vid

class PlanRequest(BaseModel):
    start:date
    time:str=Field(default='19:00',pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    replace:bool=False

def matrix(p,data):
    topics=NICHE_TOPICS.get(p['niche'],[p['niche']+' untuk pemula',p.get('goal') or 'dasar '+p['niche'], 'kesalahan umum dalam '+p['niche']])
    items=[]
    for i in range(30):
        day=(i+1)*3; topic=topics[(i//3)%len(topics)];method=['AI','Clip','Prompt'][i%3]
        angle=['3 langkah memahami ','Bedah contoh nyata: ','Lihat cara kerja '][i%3]
        title=(angle+topic)[:150]
        hook=f'Sudah paham {topic}? Tunjukkan satu kesalahan umum, lalu contoh yang bisa dipakai {p["audience"]}.'
        concept={'AI':f'Narasi orisinal: definisi {topic}, tiga langkah, contoh sehari-hari dan kesimpulan.', 'Clip':f'Gunakan rekaman sendiri/berizin tentang {topic}; pilih bagian dengan konteks cukup, tambahkan analisis Anda dan atribusi.', 'Prompt':f'Visualisasikan {topic} dengan tiga adegan; narasi menjelaskan proses dan satu pelajaran praktis.'}[method]
        items.append({'day':day,'date':(data.start+timedelta(days=day-1)).isoformat(),'time':data.time,'timezone':'Asia/Jakarta','method':method,'title':title,'hook':hook,'summary':concept,'description':f'{title}. Panduan untuk {p["audience"]}. {concept} Apa pengalaman Anda? Tulis di komentar dan ikuti {p.get("channel_name") or "channel ini"} untuk seri berikutnya.','hashtags':['#YouTubeShorts','#Belajar','#'+re.sub(r'[^\w]','',p['niche'].split('&')[0].split(',')[0])[:40]],'status':'planned','project_id':None})
    return {'profile':p,'start':data.start.isoformat(),'timezone':'Asia/Jakarta','created':now().isoformat(),'generator':'Matriks strategi berbasis template niche; judul perlu ditinjau, bukan data tren/volume pencarian.','items':items}

class PromptRequest(BaseModel):
    subject:str=Field(min_length=3,max_length=500)
    lighting:str=Field(default='soft cinematic daylight',max_length=100)
    camera:str=Field(default='slow dolly in',max_length=100)
    style:str=Field(default='Photorealistic',pattern='^(Photorealistic|3D|Anime|Documentary)$')
    ratio:str=Field(default='9:16',pattern='^(9:16|16:9)$')
    provider:str=Field(default='Runway',pattern='^(Runway|Pika|Sora|Midjourney|Leonardo AI)$')
class LinkRequest(BaseModel): url:str=Field(max_length=500)
class PlanEdit(BaseModel):
    title:str=Field(min_length=3,max_length=150)
    hook:str=Field(max_length=1000)
    summary:str=Field(max_length=2000)
    description:str=Field(max_length=4800)
    hashtags:list[str]=Field(max_length=15)
    status:str=Field(pattern='^(planned|producing|reviewed|published)$')

def register(app,current):
    @app.get('/api/mentor')
    def mentor(user=Depends(current)):
        with Session() as s: return {'profile':profile(s,user),'niches':list(NICHE_TOPICS),'steps':[dict(id=a,title=b,instructions=c,url=d) for a,b,c,d in STEPS],'calendar':setting(s,'calendar:'+user),'prompts':setting(s,'prompts:'+user,[])}
    @app.put('/api/mentor/profile')
    def save_profile(data:ChannelProfile,user=Depends(current)):
        if any(x not in [s[0] for s in STEPS] for x in data.done): raise HTTPException(400,'Langkah tidak valid.')
        if data.channel_url and not data.channel_url.startswith(('https://www.youtube.com/','https://youtube.com/')): raise HTTPException(400,'URL channel harus YouTube.')
        with Session() as s: set_setting(s,'channel:'+user,data.model_dump());event(s,user,'mentor.profile.saved');s.commit()
        return data
    @app.post('/api/mentor/calendar')
    def calendar(data:PlanRequest,user=Depends(current)):
        with Session() as s:
            p=profile(s,user)
            if not p: raise HTTPException(400,'Simpan niche dan audiens terlebih dahulu.')
            old=setting(s,'calendar:'+user)
            if old and not data.replace: return old
            if old: set_setting(s,'calendar-history:'+user+':'+now().isoformat(),old)
            result=matrix(p,data);set_setting(s,'calendar:'+user,result);s.commit();return result
    @app.put('/api/mentor/calendar/{day}')
    def edit_plan(day:int,data:PlanEdit,user=Depends(current)):
        with Session() as s:
            plan=setting(s,'calendar:'+user)
            if not plan or day not in range(3,91,3): raise HTTPException(404)
            plan['items'][day//3-1].update(data.model_dump());set_setting(s,'calendar:'+user,dict(plan));s.commit();return plan
    @app.post('/api/mentor/calendar/{day}/project')
    def plan_project(day:int,user=Depends(current)):
        with Session() as s:
            # Serialize concurrent double-clicks through the user's calendar row.
            from sqlalchemy import select
            from .db import Setting
            row=s.scalar(select(Setting).where(Setting.key=='calendar:'+user).with_for_update())
            if not row or day not in range(3,91,3): raise HTTPException(404)
            plan=dict(row.value);item=plan['items'][day//3-1]
            if item.get('project_id'): return {'id':item['project_id'],'method':item['method']}
            p=plan['profile'];project=Project(user_id=user,title=item['title'],description=item['description'],niche=p['niche'],audience=p['audience'],language=p['language'])
            s.add(project);s.flush();item['project_id']=project.id;item['status']='producing';row.value=plan
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(row,'value');s.commit();return {'id':project.id,'method':item['method']}
    @app.post('/api/mentor/prompt')
    def prompt(data:PromptRequest,user=Depends(current)):
        with Session() as s:
            p=profile(s,user)
            if not p: raise HTTPException(400,'Simpan niche dan audiens terlebih dahulu.')
            text=f'Subject: {data.subject}. Channel niche: {p["niche"]}. Intended audience: {p["audience"]}. Lighting: {data.lighting}. Camera movement: {data.camera}. Visual style: {data.style}. Aspect ratio: {data.ratio}. Clear focal subject, consistent environment, visual storytelling, room for captions. No logos, no watermarks, no baked-in text. Create original visuals; avoid impersonation.'
            if data.provider=='Midjourney': text+=' --ar '+data.ratio
            result={**data.model_dump(),'prompt':text,'niche':p['niche'],'audience':p['audience'],'created':now().isoformat(),'note':'Prompt teks siap disalin. Tidak memanggil layanan eksternal; biaya dan dukungan parameter mengikuti penyedia.'}
            history=setting(s,'prompts:'+user,[]);set_setting(s,'prompts:'+user,[result]+history[:49]);s.commit();return result
    @app.post('/api/clipper/source')
    def source(data:LinkRequest,user=Depends(current)):
        try: vid=youtube_id(data.url)
        except ValueError as e: raise HTTPException(400,str(e))
        result={'video_id':vid,'url':'https://www.youtube.com/watch?v='+vid,'license':'unknown','risk':'Belum terverifikasi','title':'','channel':'','checks':['Klaim Content ID/audio tidak dapat dipastikan dari URL atau API metadata.','Fair use tidak dapat disahkan otomatis. Tinjau konteks, atribusi, dan izin setiap aset.','Unggah file asli milik Anda atau yang diberikan pemegang hak. Tidak mengunduh video dari YouTube.']}
        try:
            data=youtube.request(user,'videos',{'part':'snippet,status','id':vid})
            if data.get('items'):
                v=data['items'][0];result.update(title=v['snippet']['title'],channel=v['snippet']['channelTitle'],license=v['status'].get('license','unknown'))
                result['risk']='CC BY tertera; verifikasi hak audio, atribusi dan asal unggahan' if result['license']=='creativeCommon' else 'Lisensi standar; perlu izin pemegang hak sebelum menggunakan ulang'
        except youtube.YouTubeError: result['checks'].append('Hubungkan OAuth YouTube untuk memeriksa metadata lisensi melalui API resmi.')
        with Session() as s: p=profile(s,user)
        result['alternatives']=[{'title':'Cari sumber '+p.get('niche','edukasi')+' (periksa lisensi tiap video)','url':'https://www.youtube.com/results?search_query='+quote(p.get('niche','edukasi')+' creative commons')},{'title':'Rekaman Anda sendiri / file dari pemegang hak','url':'https://studio.youtube.com/'},{'title':'Musik: YouTube Audio Library (periksa atribusi)','url':'https://studio.youtube.com/'}]
        return result
