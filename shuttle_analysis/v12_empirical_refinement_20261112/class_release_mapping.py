"""Validate source packet lineage before considering any class-release calibration."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    course=ANALYSIS/'course_demand_2026-11-06/outputs/course_endings_current.json'
    frozen=ANALYSIS/'261112132736/frozen/prepared_capacity44_pair.json.gz'
    events=[e for e in read(course) if e['included_main'] and e['weekday'] in '월화수목금' and e['end_minute']<=1390]
    bundle=read(frozen);counts=Counter();low=float('inf');high=0.;failures=[]
    for day,plans in bundle['prepared']['plans'].items():
        for p in plans:
            index=(p[0]-1)//48
            if not 0<=index<len(events):failures.append([p[0],'index']);continue
            e=events[index];lag=p[4]-e['end_minute']*60
            if e['weekday']!=day or str(e['building'])!=p[1] or not 60<=lag<=480:
                failures.append([p[0],day,p[1],e['weekday'],e['building'],lag]);continue
            counts[day]+=1;low=min(low,lag);high=max(high,lag)
    assert not failures,failures[:5]
    payload={'schema':'validated_source_class_release_map_v1','parent_prepared_sha256':sha(frozen),
      'source_sha256':sha(course),'source_path':str(course),'parent_index_rule':'(source_parent_id-1)//48',
      'packets_per_course_ending':48,'meaning':'Four destination groups times12 weighted source packets; not48 unique students',
      'all_parent_packets_checked':sum(counts.values()),'checks_by_weekday':dict(counts),'failures':0,
      'observed_in_original_synthetic_inputs_egress_seconds_range':[low,high],
      'departure_lag_is_empirically_observed':False,
      'events':[{'section_id':e['section_id'],'weekday':e['weekday'],'building':str(e['building']),
          'class_end_seconds':e['end_minute']*60,'enrollment':e['enrollment']} for e in events]}
    target=ROOT/'class_release_map.json.gz';assert not target.exists()
    target.write_bytes(gzip.compress(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    note={k:v for k,v in payload.items() if k!='events'};note['event_count']=len(events);note['map_sha256']=sha(target)
    (ROOT/'class_release_mapping_verification.json').write_text(json.dumps(note,ensure_ascii=False,indent=2),encoding='utf8')
    print('SOURCE_LINEAGE_VERIFIED',sum(counts.values()),'packets',len(events),'class events; egress remains scenario')
if __name__=='__main__':main()
