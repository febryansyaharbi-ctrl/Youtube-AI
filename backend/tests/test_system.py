import os
import uuid
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import Session, Project, Job, User, Base, engine, now
from app.worker import execute, cache
from app.media import ROOT
from app.security import ph

def test_real_workflow_and_security():
    assert engine.url.database.endswith('_test'), 'Tests require an isolated test database'
    Base.metadata.drop_all(engine)
    cache.flushdb()
    with TestClient(app,base_url=os.environ['PUBLIC_URL']) as c:
        assert c.get('/api/projects').status_code==401
        r=c.post('/api/login',json={'username':os.environ['ADMIN_USER'],'password':os.environ['ADMIN_PASSWORD']})
        assert r.status_code==200,r.text
        headers={'X-CSRF-Token':r.json()['csrf']}
        assert c.post('/api/projects',json={'title':'My test'}).status_code==403
        assert c.post('/api/projects',json={'title':'My test'},headers={**headers,'Origin':'https://evil.example'}).status_code==403
        p=c.post('/api/projects',json={'title':'Tips belajar','script':'Mulailah dengan satu langkah kecil. Belajar setiap hari membangun kebiasaan.','language':'id'},headers=headers).json()
        assert p['id']
        payload={'kind':'render','project_id':p['id'],'idempotency_key':str(uuid.uuid4())}
        assert c.post('/api/jobs',json=payload,headers=headers).status_code==400
        payload['accept_estimate']=True
        first=c.post('/api/jobs',json=payload,headers=headers)
        assert first.status_code==200,first.text
        assert c.post('/api/jobs',json=payload,headers=headers).json()['id']==first.json()['id']
        assert c.put('/api/projects/'+p['id'],json={'title':'Changed'},headers=headers).status_code==409
        job_id=first.json()['id']
        assert c.post('/api/jobs/'+job_id+'/pause',headers=headers).json()['status']=='paused'
        execute(job_id)
        with Session() as s: assert s.get(Job,job_id).status=='paused'
        assert c.post('/api/jobs/'+job_id+'/resume',headers=headers).status_code==200
        execute(job_id)
        with Session() as s:
            job=s.get(Job,job_id)
            assert job.status=='completed',job.error
            assert (ROOT/job.result['video']).stat().st_size>1000
            assert (ROOT/job.result['subtitles']).read_text().startswith('1\n')
            video=job.result['video']
        assert c.get('/api/media',params={'path':video}).status_code==200
        assert c.get('/api/media',params={'path':'../../etc/passwd'}).status_code==404
        assert c.post('/api/jobs',json={'kind':'upload','project_id':p['id'],'idempotency_key':str(uuid.uuid4()),'accept_estimate':True},headers=headers).status_code==400
        with Session() as s:
            other=User(username='other',password=ph.hash('other-test-password'));s.add(other);s.flush()
            hidden=Project(user_id=other.id,title='Private project');s.add(hidden);s.commit();hidden_id=hidden.id
        assert c.put('/api/projects/'+hidden_id,json={'title':'Stolen'},headers=headers).status_code==404
        scheduled=c.post('/api/jobs',json={'kind':'mentor','idempotency_key':str(uuid.uuid4()),'due':(now()+timedelta(hours=2)).isoformat(),'accept_estimate':True},headers=headers)
        assert scheduled.status_code==200,scheduled.text
        assert scheduled.json()['status']=='scheduled'
        assert c.get('/api/settings').json()['paid_enabled'] is False
        assert c.post('/api/logout',headers=headers).status_code==200
        assert c.get('/api/projects').status_code==401

def test_render_checkpoints_and_subtitle_format():
    from app.media import srt_time,segments
    assert srt_time(3661.234)=='01:01:01,234'
    assert len(segments(' '.join(['kata']*40)))==3
