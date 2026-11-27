"""Date-split retrospective proxy checks; no pristine holdout or queue truth."""
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone,timedelta
import argparse,bisect,csv,gzip,hashlib,json,math,sys

ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;KST=timezone(timedelta(hours=9))
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def seconds(at):
    d=datetime.fromtimestamp(at,KST);return d.hour*3600+d.minute*60+d.second
def distance(v,s):return math.hypot((v['lon']-s['lon'])*math.cos(v['lat']*math.pi/180)*111195,(v['lat']-s['lat'])*111195)
def score(values):return {'n':len(values),'mae_seconds':sum(abs(x) for x in values)/len(values) if values else None,
    'bias_seconds':sum(values)/len(values) if values else None}

def exact_adjacent(release):
    stopfile=ANALYSIS/'collector/route_stops.json'
    proof=read(ANALYSIS/'prototype_observation_bridge_2026-11-12/stop_identity_reconciliation.json')
    assert sha(stopfile)==proof['reference_sha256']
    stops={(rid,int(s['seq'])):s for rid,rows in read(stopfile).items() for s in rows}
    raw=release/'evidence/collected_data_review_2026-11-12/raw/2026-11-11.jsons.gz'
    seen=set();progress={};history=defaultdict(list);out=[]
    with gzip.open(raw,'rt',encoding='utf8') as stream:
        for line in stream:
            for v in json.loads(line).get('vehicles',[]):
                rid=v.get('route_id');vid=v.get('id');at=v.get('provided_at');seq=v.get('section_order')
                if not rid or not vid or not at or not str(seq).isdigit():continue
                key=(rid,vid,at)
                if key in seen:continue
                seen.add(key);seq=int(seq);pk=(rid,vid);previous=progress.get(pk)
                if datetime.fromtimestamp(at,KST).date().isoformat()!='2026-11-11' or previous and at<=previous[0]:continue
                reset=bool(previous and (seq<previous[1] or at-previous[0]>1800))
                if reset:history[pk]=[]
                stop=stops.get((rid,seq));prior=v.get('previous_observation')
                near=bool(stop and distance(v,stop)<=60)
                checked=bool(v.get('at_stop') and near and prior and 0<at-prior.get('provided_at',0)<=120)
                if checked and not any(p['seq']==seq for p in history[pk]):
                    for before in history[pk]:
                        dt=at-before['at'];fr=stops.get((rid,before['seq']))
                        if fr and seq==before['seq']+1 and 0<dt<=1800:
                            meters=distance({'lat':stop['lat'],'lon':stop['lon']},fr)
                            if dt>=meters/(100/3.6):out.append({'route':rid,'from_seq':before['seq'],'to_seq':seq,'at':before['at'],'seconds':dt})
                    history[pk].append({'seq':seq,'at':at});history[pk]=history[pk][-12:]
                progress[pk]=(at,seq)
    expected=read(release/'evidence/collected_data_review_2026-11-12/observed_intervals.json')
    a=defaultdict(list);b=defaultdict(list)
    for r in out:a[r['route'],r['from_seq'],r['to_seq'],int(seconds(r['at'])//3600)].append(r['seconds'])
    for r in expected['travel']:
        if r['day']=='2026-11-11' and r['to_seq']==r['from_seq']+1:b[r['route'],r['from_seq'],r['to_seq'],r['hour']].extend(r['seconds'])
    assert {k:sorted(v) for k,v in a.items()}=={k:sorted(v) for k,v in b.items()},'Exact-time reconstruction disagrees with preserved detection intervals'
    return out

def main(release):
    release=Path(release).resolve();target=release/'observed_input_backtest_mapped.json';assert not target.exists()
    sys.path.insert(0,str(release));from empirical_v12 import Evidence
    from time_profiles import values_at
    empirical=read(release/'frozen/empirical_evidence.json');evidence=Evidence(empirical)
    operations=read(release/'frozen/operations_v12_empirical.json')
    old=read(release/'frozen/operations_distribution_v8.json');mapping={}
    for rid,route in operations['routes'].items():
        for k,(a,b) in enumerate(zip(route['stops'],route['stops'][1:])):mapping[rid,a['seq'],b['seq']]=k
    exact=exact_adjacent(release);base=defaultdict(list);new=defaultdict(list);missing=0
    for r in exact:
        key=r['route'],r['from_seq'],r['to_seq']
        if key not in mapping:missing+=1;continue
        rid=key[0];k=mapping[key];at=seconds(r['at']);profiles=old['routes'][rid]['segment_profiles']['2']
        i=max(0,bisect.bisect_right([x[0] for x in profiles],at)-1)
        before=profiles[i][2][k];after=values_at(operations['routes'][rid],at,2)[k]
        for g in (rid,'ALL'):base[g].append(before-r['seconds']);new[g].append(after-r['seconds'])
    segment=[{'route':rid,'old':score(base[rid]),'v12_continuous':score(new[rid])} for rid in sorted(base)]
    raw=read(release/'evidence/collected_data_review_2026-11-12/observed_intervals.json');hw_old=[];hw_new=[];hw_missing=0;hw_unmapped=0
    seqs={rid:set(r['route_sequences']) if 'route_sequences' in r else {s['seq'] for s in r['stops']} for rid,r in operations['routes'].items()}
    for r in raw['headways']:
        if r['day']!='2026-11-11':continue
        rid=r['route']
        if r['seq'] not in seqs.get(rid,set()):hw_unmapped+=len(r['seconds']);continue
        values,source=evidence.headways(rid,r['seq'],r['hour']*3600)
        if not values:hw_missing+=len(r['seconds']);continue
        s=sorted(values);median=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2
        nominal=operations['routes'][rid]['official_plan']['headway_seconds']
        for x in r['seconds']:hw_old.append(nominal-x);hw_new.append(median-x)
    grade_n=0;grade_brier=0.;grade_missing=0;grade_unmapped=0;tracks=defaultdict(list)
    with (release/'evidence/collected_data_review_2026-11-12/deduplicated_grade_passages.csv').open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r['day']!='2026-11-11':continue
            at=float(r['at']);hour=int(seconds(at)//3600);level=int(r['grade']);rid=r['route'];seq=int(r['seq'])
            tracks[rid,r['vehicle'],r['trip']].append((at,seq,level))
            if seq not in seqs.get(rid,set()):grade_unmapped+=1;continue
            cell=empirical['grades'].get(f'{rid}|{seq}|{hour}')
            if not cell:grade_missing+=1;continue
            counts=cell['counts'];total=sum(counts);p=[x/total for x in counts]
            grade_brier+=sum((p[j]-int(level==j))**2 for j in range(4));grade_n+=1
    trans_n=0;trans_brier=carry_brier=0.;trans_unmapped=0
    for (rid,vid,trip),rows in tracks.items():
        rows.sort()
        for a,b in zip(rows,rows[1:]):
            if b[1]!=a[1]+1 or not 0<b[0]-a[0]<=180:continue
            if a[1] not in seqs.get(rid,set()) or b[1] not in seqs.get(rid,set()):trans_unmapped+=1;continue
            matrix=empirical['transitions'].get(f'{rid}|{a[1]}|{b[1]}|{int(seconds(a[0])//3600)}')
            counts=matrix['counts'][a[2]] if matrix else [];n=sum(counts)
            if not n:continue
            trans_brier+=sum((counts[j]/n-int(b[2]==j))**2 for j in range(4))
            carry_brier+=sum((int(a[2]==j)-int(b[2]==j))**2 for j in range(4));trans_n+=1
    result={'status':'DATE_SPLIT_RETROSPECTIVE_PROXY_CHECK','fit_dates':['2026-11-10'],'check_dates':['2026-11-11'],
      'pristine_holdout':False,'exact_adjacent_intervals_reconstructed':len(exact),'unmapped_segment_intervals':missing,
      'segment_errors':segment,'headway_interval_errors':{'official_nominal_reference':score(hw_old),'training_stop_median':score(hw_new),
       'unsupported_intervals':hw_missing,'unmapped_intervals':hw_unmapped,'is_individual_wait_validation':False},
      'ordinal_grade_distribution':{'n':grade_n,'missing_training_cells':grade_missing,'unmapped_rows':grade_unmapped,'multiclass_brier':grade_brier/grade_n if grade_n else None,
        'interpretation':'ordinal labels only; no numeric onboard truth or independent samples'},
      'ordinal_transition':{'n':trans_n,'unmapped_pairs':trans_unmapped,'brier':trans_brier/trans_n if trans_n else None,'carry_previous_grade_brier':carry_brier/trans_n if trans_n else None},
      'grade_scope':'Only stops/links represented in the fixed V12 network. Original all-archive ordinal check retained separately in observed_input_backtest.json.',
      'independent_queue_or_personal_wait_accuracy':'NOT_EVALUABLE','no_coefficients_refit':True}
    save=target.write_text;save(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    allrow=next(r for r in segment if r['route']=='ALL')
    print('V12_INPUT_PROXY_CHECK_DONE',allrow,'headway_n',len(hw_new),'grade_n',grade_n,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--release',required=True);a=p.parse_args();main(a.release)
