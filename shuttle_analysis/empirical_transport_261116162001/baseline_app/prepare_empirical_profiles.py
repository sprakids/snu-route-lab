"""Aggregate existing saved passages, no network calls and no public vehicle IDs."""
import hashlib,json,math,statistics
from collections import defaultdict
from pathlib import Path
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).parent;KST=timezone(timedelta(hours=9))

def build():
    source=ROOT.parent/'bottleneck_study_2026-11-08/sources/deduplicated_passages.private.json'
    rows=json.loads(source.read_text(encoding='utf-8'));grades=defaultdict(lambda:[0]*4)
    headways=defaultdict(list);times=defaultdict(dict);transitions=defaultdict(lambda:[0]*4);prior={}
    for r in sorted(rows,key=lambda x:x['provided_at']):
        at=r['provided_at'];d=datetime.fromtimestamp(at,KST);rid=r['route_id'];seq=int(r.get('section_order') or 0)
        code=str(r.get('crowd_code'));grade=3 if r.get('full') else int(code)-3 if code in ('3','4','5','6') else None
        if seq<1:continue
        day=d.date().isoformat()
        if grade is not None:
            grades[(day,rid,seq,d.hour)][grade]+=1
            key=(day,rid,r['id'],r['trip']);old=prior.get(key)
            if old and 0<at-old[0]<=1200 and 0<seq-old[1]<=12:
                bucket=0 if seq-old[1]<=3 else 1 if seq-old[1]<=8 else 2
                transitions[(day,rid,old[2],bucket)][grade]+=1
            prior[key]=(at,seq,grade)
        if r.get('at_stop'):
            times[(day,rid,seq,d.hour)][(r['id'],r['trip'])]=at
    for key,items in times.items():
        stamps=sorted(items.values());gaps=[b-a for a,b in zip(stamps,stamps[1:]) if 60<=b-a<=1800]
        if len(gaps)>=3:headways[key]=[len(gaps),round(statistics.median(gaps))]
    result={'schema':'empirical_passage_priors_v1','model_id':'saved-passages-'+hashlib.sha256(source.read_bytes()).hexdigest()[:12],
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'dates':sorted({r['date'] for r in rows}),
            'grades':[[*k,*v] for k,v in sorted(grades.items())],
            'headways':[[*k,*v] for k,v in sorted(headways.items())],
            'transitions':[[*k,*v] for k,v in sorted(transitions.items())],
            'calibrated':False,'counts_unit':'one vehicle-trip-section passage; not repeated polls or persons',
            'limitations':['토·일 일부 시각만 확보·평일 검증 없음','관악02 등급 미제공·0을 여유로 학습하지 않음',
                            '구간 통과 간격은 실제 출발시간표가 아님','잠정 과거 분포·전이이며28일 독립검증모델과 구분']}
    target=ROOT/'data/empirical_profiles.json';target.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print({'grade_cells':len(grades),'headway_cells':len(headways),'transition_cells':len(transitions),'dates':result['dates'],'bytes':target.stat().st_size})
    return result

if __name__=='__main__':build()
