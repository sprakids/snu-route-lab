"""Owner-only gzip export, before the 30-day raw retention deadline."""
import argparse,json,os,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import server

def credentials():
    p=Path(os.environ['LOCALAPPDATA'])/'SnuTransit/credentials/collector_backend.dpapi'
    return json.loads(server.crypt(p.read_bytes(),decrypt=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('day');p.add_argument('--output',type=Path,required=True);a=p.parse_args();c=credentials()
    from datetime import date
    date.fromisoformat(a.day)
    req=urllib.request.Request(c['url']+'/export?day='+a.day,headers={'Authorization':'Bearer '+c['token'],'User-Agent':'SNU-Route-Lab/0.4'})
    with urllib.request.urlopen(req,timeout=30) as r:data=r.read()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(data);print('Exported',a.day,len(data),'bytes')
