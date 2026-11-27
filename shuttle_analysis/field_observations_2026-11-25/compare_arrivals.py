"""Summarize the validated historical branches against the reported sequence."""
import csv
import gzip
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
rows=[]
for service,variant in (('regular','mid'),('peak','mid'),('peak','early'),('peak','late'),
                        ('regular','mid-paired'),('peak','mid-paired')):
    folder=HERE/'runs'/f'{service}-{variant}'
    result=json.loads((folder/'comparison.json').read_text(encoding='utf8'))
    with gzip.open(folder/f'{service}-wed.json.gz','rt',encoding='utf8') as stream:
        data=json.load(stream)
    (vid,)=map(int,data['observed_return_vehicles'])
    opened=result['opening']
    events=[(t,w) for t,_,v,w,_,_ in data['preboard_events'] if v==vid]
    start,end=result['window']
    queue=result['replay_outside_minute']
    rows.append(dict(service=service,variant=variant,scheduled_slot=result['scheduled_anchor'],
        modeled_open=opened,modeled_depart=result['departure_used'],queue_before_open=result['outside_just_before_open'],
        measured_queue=result['measured_before_boarding'],minute_min=queue['minimum'],minute_max=queue['maximum'],
        board_at_open=result['boarded_at_open'],first_board_after_open_s=min((t-opened for t,_ in events),default=None),
        board_within_30s=sum(w for t,w in events if opened<=t<opened+30),
        boards_in_report_minute=sum(w for t,w in events if start<=t<end),
        demand=result['demand'],unserved=result['unserved'],capacity_violations=result['capacity_violations'],
        max_outside_wait_min=result['max_outside_wait_min']))
with (HERE/'수요일_1600_도착승차_비교.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
for row in rows:
    print(row['service'],row['variant'],*[round(row[key],2) for key in (
        'queue_before_open','minute_min','minute_max','board_at_open','board_within_30s','boards_in_report_minute')])
