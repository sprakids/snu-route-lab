"""Compare the recorded opposite-direction case with the corrected-code outcome."""
from pathlib import Path
import argparse,gzip,hashlib,json,math
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'direction-repair-diagnosis.json';assert not out.exists();cases=[]
    for model in ['261115154738',w.name]:
        group=w.parent/model/'grid-validation.json'
        if group.exists():r=next(r for r in read(group)['results'] if r['case']['day']=='화' and r['case']['scenario']=='regular')
        else:r=read(w.parent/model/'runs/direction-combined-regular-tue/attempt_01/repair_analysis.json')
        ap=Path(r['source_directory'])/'audit-regular-tue.json.gz';audit=read(ap);selected=[t for t in audit['legs'] if t['id']==798720];assert selected
        mass=math.fsum(t['weight'] for t in selected);vehicles={v['id']:v for v in audit['vehicles']};pieces=[]
        for t in selected:
            legs=[]
            for l in t['legs']:
                v=vehicles[l[6]] if l[0]==3 else None
                legs.append({'kind':l[0],'start':l[1],'end':l[2],'minutes':(l[2]-l[1])/60,'node':l[4],'route':v['rid'] if v else None})
            pieces.append({'weight':t['weight'],'unserved':t['unserved'],'total_min':(t['finish_time']-t['start'])/60,'history':t['history'],'legs':legs})
        cases.append({'model':model,'uid':798720,'source':str(ap),'source_sha256':sha(ap),'weight':mass,'pieces':pieces,'weighted_mean_total_min':math.fsum(t['weight']*t['total_min'] for t in pieces)/mass})
    assert abs(cases[0]['weight']-cases[1]['weight'])<1e-8
    source=read(w.parent/'261115154738/frozen/prepared_capacity44_pair.json.gz');route=source['prepared']['routes']['100100253']
    details={str(i):{k:route['stops'][i].get(k) for k in ['name','ars','direction']} for i in [15,52,73]}
    result={'scope':'Same synthetic UID, demand, operations and seed across one confirmed bug fix; not a measured student or whole-model empirical validation','cases':cases,'frozen_5516_stops':details,'numeric_parameters_fitted':False,'production_writes':False}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print('DIRECTION_CASE_BEFORE_AFTER',[(r['model'],r['weighted_mean_total_min'],r['weight']) for r in cases],flush=True)
if __name__=='__main__':main()
