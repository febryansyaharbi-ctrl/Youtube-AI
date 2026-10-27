import os, json, re, httpx
from .db import Session, setting
class ProviderError(Exception): pass
class OllamaProvider:
    def generate(self, prompt, check=lambda:None):
        with Session() as s: config=setting(s,'ai',{'model':'qwen3:4b'})
        model=config['model']
        chunks=[]
        with httpx.Client(timeout=httpx.Timeout(900,connect=15)) as client:
            with client.stream('POST',os.getenv('OLLAMA_URL','http://ollama:11434')+'/api/chat',json={
                'model':model,'messages':[{'role':'system','content':'You are a careful original content producer. Follow the requested language. Never invent citations or guarantee revenue. Output only the requested JSON.'},{'role':'user','content':prompt}],
                'format':'json','think':False,'stream':True,'keep_alive':0,
                'options':{'num_ctx':4096,'num_predict':2200,'temperature':0.7,'num_thread':2}}) as response:
                if response.status_code!=200: raise ProviderError('Model lokal belum tersedia atau sedang bermasalah.')
                for line in response.iter_lines():
                    check()
                    if line:
                        part=json.loads(line)
                        if part.get('error'): raise ProviderError('Ollama gagal memproses permintaan.')
                        chunks.append(part.get('message',{}).get('content',''))
        try: return json.loads(''.join(chunks))
        except ValueError: raise ProviderError('Format jawaban AI belum valid. Coba ulangi dengan topik lebih spesifik.')

def get_provider(): return OllamaProvider()

def script_prompt(p):
    language='Bahasa Indonesia' if p.language=='id' else 'English'
    words='100-140' if p.format=='short' else '350-500'
    return f'''Write an original educational video script in {language}. Topic: {p.title}. Niche: {p.niche}. Audience: {p.audience}. {words} words. Include a strong hook, a concrete useful example, and a short closing. No stage directions, no markdown, no invented statistics. JSON keys: script (plain spoken text), description (YouTube description), title (at most 90 characters), fact_check (array of claims to verify), tags (array).'''
