import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, Integer, DateTime, JSON, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())
engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Login(Base):
    __tablename__ = 'sessions'
    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    csrf: Mapped[str] = mapped_column(String)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))
class Setting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(200))
    niche: Mapped[str] = mapped_column(String(200), default='Edukasi')
    audience: Mapped[str] = mapped_column(String(300), default='Pemula')
    language: Mapped[str] = mapped_column(String, default='id')
    format: Mapped[str] = mapped_column(String, default='short')
    mode: Mapped[str] = mapped_column(String, default='semi')
    script: Mapped[str] = mapped_column(Text, default='')
    description: Mapped[str] = mapped_column(Text, default='')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    rights: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    made_for_kids: Mapped[bool] = mapped_column(Boolean, default=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Job(Base):
    __tablename__ = 'jobs'
    __table_args__ = (UniqueConstraint('user_id','idempotency_key'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    project_id: Mapped[str | None] = mapped_column(ForeignKey('projects.id'), nullable=True)
    kind: Mapped[str] = mapped_column(String)
    idempotency_key: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default='queued', index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String, default='Menunggu antrean')
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default='')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Asset(Base):
    __tablename__ = 'assets'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    mime: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    license: Mapped[str] = mapped_column(String)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Connection(Base):
    __tablename__ = 'connections'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    encrypted: Mapped[str] = mapped_column(Text)
    channel: Mapped[dict] = mapped_column(JSON, default=dict)
    analytics: Mapped[dict] = mapped_column(JSON, default=dict)
    updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Event(Base):
    __tablename__ = 'events'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(String)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

def setting(s, key, default=None):
    row=s.get(Setting,key)
    return row.value if row else default

def set_setting(s,key,value):
    row=s.get(Setting,key)
    if row: row.value=value
    else: s.add(Setting(key=key,value=value))

def event(s,user,action,detail=''): s.add(Event(user_id=user,action=action,detail=detail))
