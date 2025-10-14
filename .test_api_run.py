import uvicorn, asyncio, threading, time, json, socket
from api.main import app
import httpx
results={}

def run_server():
    uvicorn.run(app, host='127.0.0.1', port=8776, log_level='error')

th=threading.Thread(target=run_server, daemon=True)
th.start()
for _ in range(50):
    try:
        s=socket.create_connection(('127.0.0.1',8776),timeout=0.2)
        s.close()
        break
    except Exception:
        time.sleep(0.1)

async def check():
    async with httpx.AsyncClient() as client:
        r= await client.get('http://127.0.0.1:8776/health')
        results['health']={'code':r.status_code,'json':r.json()}
        r2= await client.get('http://127.0.0.1:8776/')
        results['root']={'code':r2.status_code,'json':r2.json()}
asyncio.run(check())
print(json.dumps(results, indent=2))
