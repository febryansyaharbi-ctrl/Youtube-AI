#!/usr/bin/env python3
import os, secrets, base64
from pathlib import Path
os.umask(0o077)
root=Path(__file__).resolve().parents[1]
if (root/'.env').exists(): raise SystemExit('Environment already exists; preserving secrets.')
db=secrets.token_hex(24);password=secrets.token_urlsafe(16)
(root/'.env').write_text(f'DB_PASSWORD={db}\nDATABASE_URL=postgresql+psycopg://creatorpilot:{db}@db:5432/creatorpilot\nREDIS_URL=redis://redis:6379/0\nENCRYPTION_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}\nADMIN_USER=harnet\nADMIN_PASSWORD={password}\nPUBLIC_URL=https://studio.cekwifi.site\nOLLAMA_URL=http://ollama:11434\nMEDIA_ROOT=/data/media\n')
(root/'access.txt').write_text(f'URL: https://studio.cekwifi.site\nUsername: harnet\nPassword: {password}\n')
print('Environment generated. Credentials are in access.txt (mode 600).')
