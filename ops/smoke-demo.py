"""Run inside the API container, after readiness. Creates one original draft, never publishes."""
import os
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import Session, Project
TITLE='Contoh studio: tiga langkah membuat video edukasi orisinal'
with TestClient(app,base_url=os.environ['PUBLIC_URL']) as client:
    response=client.post('/api/login',json={'username':os.environ['ADMIN_USER'],'password':os.environ['ADMIN_PASSWORD']})
    response.raise_for_status()
    headers={'X-CSRF-Token':response.json()['csrf']}
    with Session() as s: existing=s.scalar(select(Project).where(Project.title==TITLE))
    if existing: project_id=existing.id
    else:
        r=client.post('/api/projects',headers=headers,json={'title':TITLE,'niche':'Edukasi kreator pemula','audience':'Pemula Indonesia','mode':'auto','language':'id','format':'short'})
        r.raise_for_status();project_id=r.json()['id']
    response=client.post('/api/jobs',headers=headers,json={'kind':'pipeline','project_id':project_id,'idempotency_key':'installation-demo-v1','accept_estimate':True})
    response.raise_for_status()
    print({'project_id':project_id,'job_id':response.json()['id'],'status':response.json()['status']})
    client.post('/api/logout',headers=headers)
