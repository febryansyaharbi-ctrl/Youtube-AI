#!/usr/bin/env python3
from pathlib import Path
import subprocess
path=Path('/etc/caddy/sites/wificover.caddy')
original=path.read_text()
if '@creatorpilot' in original: raise SystemExit('CreatorPilot route already exists; preserving config.')
if not original.strip().startswith(':8081 {') or 'reverse_proxy 127.0.0.1:8011' not in original:
    raise SystemExit('Unexpected existing configuration; inspect manually.')
body=original.strip()[len(':8081 {'):].rsplit('}',1)[0]
body=body.replace('bind 127.0.0.1','',1)
backup=path.with_suffix('.caddy.before-creatorpilot')
if not backup.exists(): backup.write_text(original)
new=':8081 {\n bind 127.0.0.1\n route {\n  @creatorpilot host studio.cekwifi.site\n  handle @creatorpilot {\n   reverse_proxy 127.0.0.1:8033\n  }\n  handle {\n'+body+'\n  }\n }\n}\n'
path.write_text(new)
check=subprocess.run(['caddy','validate','--config','/etc/caddy/Caddyfile'],capture_output=True,text=True)
if check.returncode:
    path.write_text(original)
    raise SystemExit('Configuration validation failed; original restored. '+check.stderr)
subprocess.run(['systemctl','reload','caddy'],check=True)
print('CreatorPilot route installed. Existing Cekwifi routes preserved.')
