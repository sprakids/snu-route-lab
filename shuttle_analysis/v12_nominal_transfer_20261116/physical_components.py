"""All-cohort mean physical components, with explicit units for legacy fields."""
from pathlib import Path
import argparse,csv,hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261116010854'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'mean-physical-components.csv';assert not out.exists();rows=[]
    for model in (PARENT,w):
        path=model/'grid-validation.json';v=read(path)
        for r in v['results']:
            assert r['unserved_trip_weight']==0
            # analyze_followup.verify divides all *_seconds aggregates by60.
            # Only its optional standalone main renames keys to *_min.
            m=r['scope']['all']['metrics'];get=lambda name:m.get(name+'_min',m.get(name+'_seconds'))['prototype']
            values={name+'_min':get(name) for name in ('walk','wait','ride','total')}
            q=r['extended_diagnostics']['finished_trip_quantiles']
            assert abs(values['total_min']-math.fsum(values[k] for k in ('walk_min','wait_min','ride_min')))<1e-7
            for left,right in [('walk_min','walk_min'),('wait_min','cumulative_wait_min'),('total_min','total_min')]:assert abs(values[left]-q[right]['mean'])<1e-7
            rows.append({'model':model.name,'weekday':r['case']['day'],'scenario':r['case']['scenario'],'demand_weight':r['scope']['all']['weight'],
              **values,'changes':q['changes']['mean'],'source_sha256':sha(path),'scope':'all weighted trips; physical minutes, not generalized cost or observed persons'})
    with out.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,list(rows[0]));writer.writeheader();writer.writerows(rows)
    print('PHYSICAL_COMPONENTS_PASS',len(rows),'mean rows, minute-unit and sum checks',flush=True)
if __name__=='__main__':main()
