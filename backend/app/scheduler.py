import time, logging
from datetime import timedelta
from sqlalchemy import select, or_
from .db import Session, Job, now
from .worker import queue, cache
logging.basicConfig(level=logging.INFO)
while True:
    try:
        with cache.lock('scheduler',timeout=20,blocking_timeout=1):
            with Session() as s:
                for j in s.scalars(select(Job).where(Job.status=='scheduled',Job.due<=now()).with_for_update(skip_locked=True)):
                    j.status='queued';j.stage='Jadwal tiba';j.dispatched=None
                for j in s.scalars(select(Job).where(Job.status=='running',Job.heartbeat<now()-timedelta(minutes=2)).with_for_update(skip_locked=True)):
                    if not cache.exists('job:'+j.id): j.status='queued';j.dispatched=None;j.stage='Memulihkan checkpoint'
                s.commit()
                for j in s.scalars(select(Job).where(Job.status=='queued',or_(Job.dispatched==None,Job.dispatched<now()-timedelta(minutes=2)))):
                    queue.send_task('creatorpilot.run',args=[j.id]);j.dispatched=now()
                s.commit()
    except Exception as error: logging.error('scheduler: %s',type(error).__name__)
    time.sleep(5)
