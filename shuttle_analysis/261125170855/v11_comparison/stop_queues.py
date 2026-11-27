"""Duration above the user's 40-person reference, for each physical stop and direction."""
from compare_models import V11, R, DAYS, SERVICES, read, Curve, HERE, write_rows


def main():
    common=read(V11/'common.json.gz')
    stop_ids={'21269','21270','21298','21299','21128'}
    selected={i:(n['name'],n['ars']) for i,n in enumerate(common['nodes']) if n.get('ars') in stop_ids}
    rows=[]
    for service in SERVICES:
        for day in DAYS:
            key=f'{service}-{day}'
            for model,folder in [('V11',V11),('R',R/'runs/candidate'/key)]:
                replay=read(folder/f'{key}.json.gz')
                for node,(name,ars) in selected.items():
                    curve=Curve(replay['queue_timeline'][node])
                    boundaries=[54000,*(t for t in curve.times if 54000<t<68400),68400]
                    spans=[(a,b,curve.at(a)) for a,b in zip(boundaries,boundaries[1:])]
                    start,_,maximum=max(spans,key=lambda x:x[2])
                    over=sum(b-a for a,b,v in spans if v>40+1e-7)
                    rows.append(dict(model=model,service=service,day=day,stop=name,ars=ars,
                        peak=maximum,peak_second=start,over40_minutes=over/60))
    write_rows(HERE/'정류장별_15시_19시.csv',rows)


if __name__=='__main__':
    main()
