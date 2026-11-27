"""Conservation decomposition at previously used field reports. No tuning or reruns."""
from pathlib import Path
import gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mass_at(waits,node,t):return math.fsum(w for n,a,b,w,*_ in waits if n==node and a<=t<b)
def main():
    target=ROOT/'historical_queue_flow_decomposition.json';assert not target.exists()
    sources={'V11':ANALYSIS/'simulation_viewer_2026-11-07/peak_pair_correction_2026-11-10',
      'V12':ANALYSIS/'261112111627/runs'}
    results=[]
    for day in ('tue','mon'):
        for model,directory in sources.items():
            p=directory/f'audit-regular-{day}.json.gz' if model=='V11' else directory/f'v12_empirical-combined-regular-{day}/attempt_01/audit-regular-{day}.json.gz'
            audit=read(p);waits=audit['waits']
            for node,begin,t in ([(1,54000,55380),(1,54000,55440-1e-5)] if day=='tue' else [(1,59400,60780),(1,59400,60840-1e-5)]):
                subset=[r for r in waits if r[0]==node]
                q0=mass_at(subset,node,begin);q=mass_at(subset,node,t)
                arrivals=math.fsum(r[3] for r in subset if begin<r[1]<=t)
                board=math.fsum(r[3] for r in subset if begin<r[2]<=t and r[7]=='boarded')
                switch=math.fsum(r[3] for r in subset if begin<r[2]<=t and r[7]=='switched')
                other=math.fsum(r[3] for r in subset if begin<r[2]<=t and r[7] not in ('boarded','switched'))
                assert abs(q-(q0+arrivals-board-switch-other))<1e-5
                results.append({'model':model,'day':day,'node':node,'begin':begin,'at':t,'initial_queue':q0,
                  'arrivals':arrivals,'boarded':board,'switched_out':switch,'other_exits':other,'queue':q,
                  'source':str(p),'sha256':sha(p)})
                print(model,day,'at',t,'q',q,'q0',q0,'in',arrivals,'board',board,'walkout',switch,flush=True)
    target.write_text(json.dumps({'scope':'Known field reports, not independent validation; hypothetical model flow identities',
       'note':'Both models have the same administration shuttle capacity/dispatch scenario; city network and behavioral assignments differ.',
       'rows':results},ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
