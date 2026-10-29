import os,uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import Session,Job,Asset,User,Base,engine
from app.worker import cache,execute
from app.media import ROOT,run,duration
from app.growth import youtube_id,matrix,PlanRequest
from app.clipping import SubtitleStyle,write_subtitles,validate_ranges

def test_guided_channel_and_real_multiclip():
    assert engine.url.database.endswith('_test')
    assert cache.connection_pool.connection_kwargs.get('db')==15
    Base.metadata.create_all(engine)
    with TestClient(app,base_url=os.environ['PUBLIC_URL']) as c:
        r=c.post('/api/login',json={'username':os.environ['ADMIN_USER'],'password':os.environ['ADMIN_PASSWORD']});assert r.status_code==200
        h={'X-CSRF-Token':r.json()['csrf']}
        profile={'niche':'Educational Science & Fun Facts','audience':'Pelajar SMA Indonesia','language':'id','channel_name':'Sains Contoh','done':['direction']}
        assert c.put('/api/mentor/profile',json=profile,headers=h).status_code==200
        d=c.get('/api/mentor').json();assert len(d['niches'])>=16 and len(d['steps'])==10
        assert d['profile']['audience']==profile['audience']
        p=c.post('/api/projects',json={'title':'Sains pertama','niche':'wrong'},headers=h).json();assert p['niche']==profile['niche']
        plan=c.post('/api/mentor/calendar',json={'start':'2026-11-01'},headers=h).json()
        assert len(plan['items'])==30 and plan['items'][0]['date']=='2026-11-03' and plan['items'][-1]['date']=='2027-01-29'
        assert [x['method'] for x in plan['items'][:3]]==['AI','Clip','Prompt']
        item=plan['items'][0];item['title']='Judul yang diedit'
        assert c.put('/api/mentor/calendar/3',json=item,headers=h).status_code==200
        assert c.get('/api/mentor').json()['calendar']['items'][0]['title']==item['title']
        a=c.post('/api/mentor/calendar/3/project',headers=h).json();b=c.post('/api/mentor/calendar/3/project',headers=h).json();assert a['id']==b['id']
        prompt=c.post('/api/mentor/prompt',json={'subject':'Ilustrasi gravitasi','provider':'Midjourney'},headers=h).json();assert profile['audience'] in prompt['prompt'] and '--ar 9:16' in prompt['prompt']
        assert c.post('/api/clipper/source',json={'url':'https://evil.example/watch?v=abcdefghijk'},headers=h).status_code==400
        r=c.post('/api/clipper/source',json={'url':'https://youtu.be/abcdefghijk'},headers=h);assert r.status_code==200 and r.json()['license']=='unknown'
        style=SubtitleStyle(preset='karaoke',max_words=3).model_dump()
        assert c.put('/api/subtitle-style',json=style,headers=h).status_code==200
        assert c.get('/api/subtitle-style').json()['preset']=='karaoke'
        folder=ROOT/'test-source';folder.mkdir(exist_ok=True)
        path=folder/'source.mp4'
        run(['ffmpeg','-nostdin','-y','-f','lavfi','-i','color=c=blue:s=320x240:r=24:d=4','-f','lavfi','-i','sine=frequency=440:duration=4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(path)],lambda:None)
        with Session() as s:
            user=s.scalar(select(User).where(User.username==os.environ['ADMIN_USER']))
            asset=Asset(user_id=user.id,name='clip fixture',path=str(path.relative_to(ROOT)),mime='video/mp4',size=path.stat().st_size,sha256='fixture'+uuid.uuid4().hex,license='Test original');s.add(asset);s.flush()
            trans=Job(user_id=user.id,kind='transcribe',idempotency_key=uuid.uuid4().hex,status='completed',payload={'asset_id':asset.id},result={'transcript':[{'start':0,'end':4,'text':'Belajar sains dengan contoh sederhana hari ini.'}]});s.add(trans);s.commit();aid=asset.id;tid=trans.id
        data={'kind':'multiclip','accept_estimate':True,'idempotency_key':uuid.uuid4().hex,'payload':{'asset_id':aid,'transcript_job':tid,'rights_confirmed':True,'clips':[{'start':0,'end':2},{'start':2,'end':4}],'subtitle_style':style}}
        bad={**data,'payload':{**data['payload'],'rights_confirmed':False}}
        assert c.post('/api/jobs',json=bad,headers=h).status_code==400
        bad={**data,'payload':{**data['payload'],'clips':[{'start':0,'end':9}]}}
        assert c.post('/api/jobs',json=bad,headers=h).status_code==400
        r=c.post('/api/jobs',json=data,headers=h);assert r.status_code==200,r.text
        jid=r.json()['id'];assert c.post('/api/jobs',json=data,headers=h).json()['id']==jid
        execute(jid)
        with Session() as s:
            j=s.get(Job,jid);assert j.status=='completed',j.error
            clips=j.result['clips'];assert len(clips)==2
            for x in clips: assert 1.9<=duration(ROOT/x['video'])<=2.2 and (ROOT/x['subtitles']).stat().st_size>0
        assert c.get('/api/media',params={'path':clips[0]['video']}).status_code==200
        assert c.delete('/api/outputs/'+jid+'/clips/0',headers=h).status_code==200
        assert not (ROOT/clips[0]['video']).exists()
        assert (ROOT/clips[1]['video']).exists()
        assert c.get('/api/media',params={'path':clips[0]['video']}).status_code==404
        assert c.delete('/api/outputs/'+jid+'/clips/99',headers=h).status_code==404
        # Existing AI production gains the same real subtitle renderer.
        p=c.post('/api/projects',json={'title':'Subtitle AI test','script':'Belajar sains dengan contoh sederhana.'},headers=h).json()
        r=c.post('/api/jobs',json={'kind':'render','project_id':p['id'],'idempotency_key':uuid.uuid4().hex,'accept_estimate':True,'payload':{'subtitle_style':style}},headers=h)
        assert r.status_code==200,r.text
        execute(r.json()['id'])
        with Session() as s:
            j=s.get(Job,r.json()['id']);assert j.status=='completed',j.error
            assert (ROOT/j.result['video']).stat().st_size>1000

def test_url_and_ranges_are_bounded():
    for url in ['https://youtube.com.evil.test/watch?v=abcdefghijk','file:///etc/passwd','https://youtube.com@evil.test/watch?v=abcdefghijk','http://youtu.be/abcdefghijk']:
        with pytest.raises(ValueError): youtube_id(url)
    assert youtube_id('https://www.youtube.com/shorts/abcdefghijk')=='abcdefghijk'
    with pytest.raises(ValueError): validate_ranges([{'start':0,'end':2},{'start':0,'end':2}],10)
    with pytest.raises(ValueError): validate_ranges([{'start':0,'end':float('nan')}],10)
