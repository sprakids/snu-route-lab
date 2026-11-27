"""Build map-facing statistics from verified runs, using the preceding R as comparison."""
import sys
from timing_inputs import HERE, REFERENCE, MODEL, ref
sys.path.insert(0,str(ref.HERE/'local-map'))
import build_stats as maps


def main():
    maps.PREVIOUS=REFERENCE
    maps.VERSION=MODEL
    src=ref.ref.load_v11()['prepared']['plans']
    dest={day:{p[0]:p[2] for p in rows} for day,rows in src.items()}
    upper={day:{p[0] for p in rows if p[1] in ('300','301','302') and p[2]=='dorm'} for day,rows in src.items()}
    del src
    common=ref.load(HERE/'viewer-data/common.json.gz')
    halves={};runs={};station={}
    for service in ('peak','regular'):
        halves[service]={};runs[service]={};station[service]={}
        for day,did in ref.DAYS.items():
            key=f'{service}-{did}'
            audit=HERE/'runs'/key/'attempt-01'/f'audit-{key}.json.gz'
            patch={**ref.load(ref.INPUTS/f'{did}.json.gz'),'model':MODEL}
            halves[service][did],runs[service][did],station[service][did]=maps.case(
                audit,HERE/'viewer-data'/f'{key}.json.gz',dest[day],upper[day],patch,common,did,service)
    maps.publish(HERE/'map-stats.json.gz',dict(interval_seconds=1800,scenarios=halves,runs=runs))
    maps.publish(HERE/'station-access.json.gz',dict(model=MODEL,destination='gwanaksan_4411',station_code='4411',
                 event='arrival at station marker',runs=station))


if __name__=='__main__':
    main()
