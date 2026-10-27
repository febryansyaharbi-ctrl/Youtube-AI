import os, hashlib, secrets
from datetime import timedelta
from cryptography.fernet import Fernet
from argon2 import PasswordHasher
from fastapi import HTTPException, Request
from sqlalchemy import select
from .db import Session, Login, User, now
ph=PasswordHasher()
fernet=Fernet(os.environ['ENCRYPTION_KEY'].encode())
def encrypt(text): return fernet.encrypt(text.encode()).decode()
def decrypt(text): return fernet.decrypt(text.encode()).decode()
def digest(text): return hashlib.sha256(text.encode()).hexdigest()
def current(request: Request):
    token=request.cookies.get('cp_session','')
    with Session() as s:
        login=s.get(Login,digest(token))
        if not login or login.expires < now(): raise HTTPException(401,'Silakan masuk kembali.')
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''), login.csrf):
                raise HTTPException(403,'Token keamanan tidak valid. Muat ulang halaman.')
        return s.get(User,login.user_id).id
