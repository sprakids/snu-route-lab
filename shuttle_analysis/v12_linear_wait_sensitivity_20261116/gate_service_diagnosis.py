"""Separate unchanged bus clocks from endogenous onboard loads at the gate."""
from pathlib import Path
from collections import Counter
import argparse,json,gzip,hashlib,math
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'gate-service-diagnosis.json';assert not out.exists();results=[]
    for model in ['261116105704',w.name]:
        root=w.parent/model;group='grid' if (root/'grid-validation.json').exists() else 'pilot';r=next(r for r in read(root/f'{group}-validation.json')['results'] if r['case']['day']=='월' and r['case']['scenario']=='regular' and not r['case']['case'].startswith('ablation'))
        source=Path(r['source_directory'])/'audit-regular-mon.json.gz';a=read(source);rows=[]
        for e in a['events']:
            if e[1]!=62 or not 59400<e[0]<=61440:continue
            rows.append({'time':e[0],'route':e[11],'vehicle':e[2],'capacity':e[3],'model_onboard_before':e[4],'alighting':e[5],
                'model_free_before_gate_boarding':e[3]-e[4]+e[5],'boarded':e[6],'model_load_after':e[7]})
        results.append({'model':model,'source':str(source),'source_sha256':sha(source),'arrivals':rows,'bus_events':len(rows),
            'offered_seat_events':math.fsum(x['model_free_before_gate_boarding'] for x in rows),'boarded_weight':math.fsum(x['boarded'] for x in rows)})
    keys=lambda r:[(x['time'],x['route'],x['vehicle'],x['capacity']) for x in r['arrivals']]
    assert keys(results[0])==keys(results[1])
    out.write_text(json.dumps({'scope':'Model-known incoming occupancy, not measured external people. Repeated seat opportunities are not unique seats or passengers. Bus clocks/capacities identical.','cases':results,'unchanged_exogenous_gate_service':True,'production_writes':False},ensure_ascii=False,indent=2),encoding='utf8')
    print('GATE_SERVICE_COMPARE',[(r['model'],r['bus_events'],r['offered_seat_events'],r['boarded_weight']) for r in results],flush=True)
if __name__=='__main__':main()
