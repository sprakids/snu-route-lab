"""Count linked paid journeys from the two engineering stops; export aggregates only."""
import csv
from collections import Counter,defaultdict
from pathlib import Path
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
ARCHIVE=HERE.parent/'tdata_campus_cards_2026-11-10/archives/TAIMS_20261109.zip'
PAIR={'120000173','120000174'}
TERMINALS={'120900119','120900110'}
LINE='120900011'
DATE='20261105'


def rows(z,filter_line):
    for table in ('DC','DD','DX'):
        with z.open(f'VW_KSCC_{table}_CARD.csv') as f:
            fields=next(csv.reader([f.readline().decode('utf-8-sig')]))
            assert fields[0]=='TRCR_ID'
            for line in f:
                if filter_line(line):
                    r=dict(zip(fields,next(csv.reader([line.decode('utf8')]))))
                    if r['STDR_DE']==DATE and r['RIDE_DTM'].startswith(DATE):
                        yield r


def main():
    anchors=defaultdict(list); legs=defaultdict(lambda:defaultdict(list)); counts=Counter()
    quality=Counter()
    with ZipFile(ARCHIVE) as z:
        for r in rows(z,lambda b:b'120000173' in b or b'120000174' in b):
            stop=r['RIDE_BSST_ID']; hour=int(r['RIDE_DTM'][8:10])
            if stop not in PAIR or not 17<=hour<21 or r['TRTR_FCNT']!='0' or not r['ROUTE_ID']:continue
            key=(r['TRCR_ID'],r['TRNC_ID'])
            if not all(key):
                quality['missing_key']+=int(r['PSNG_NUM']);continue
            anchors[key].append((r['RIDE_DTM'],stop))
        cards={k[0].encode() for k in anchors}
        for r in rows(z,lambda b:b.partition(b',')[0].strip(b'"') in cards):
            key=(r['TRCR_ID'],r['TRNC_ID'])
            if key in anchors and r['TRTR_FCNT'].isdigit():
                legs[key][int(r['TRTR_FCNT'])].append((r['RIDE_DTM'],r['ALGH_DTM'],r['RIDE_BSST_ID'],
                    r['ALGH_BSST_ID'],r['ROUTE_ID'],int(r['PSNG_NUM'])))
    for key,anchor in anchors.items():
        seq=legs[key]
        if len(anchor)!=1 or len(seq[0])!=1:
            quality['ambiguous_anchor_journeys']+=1;continue
        first=seq[0][0];hour=int(first[0][8:10]); w=first[5]
        quality['anchor_passengers']+=w
        if 1 in seq:quality['next_leg_available']+=w
        assert first[2] in PAIR and (first[0],first[2])==anchor[0]
        seen_line=False; prev_end=None; reached_bus=False; rail=False; used_at_bus=False; first_at_bus=False
        for i in range(max(seq)+1):
            matches=seq.get(i,[])
            if len(matches)!=1:
                quality['broken_or_ambiguous_prefix']+=w;break
            enter,end,stop,alight,rid,n=matches[0]
            if i and (not prev_end or enter<prev_end or w!=n):
                quality['inconsistent_prefix']+=w;break
            if not rid:
                quality['first_rail_reached_any_station']+=w
                rail=(stop=='0227')
                break
            seen_line |= rid==LINE
            if alight in TERMINALS and not reached_bus and len(end)==14 and end>=enter:
                reached_bus=True
                used_at_bus=seen_line
                first_at_bus=first[4]==LINE
            prev_end=end if len(end)==14 and end>=enter else None
        categories={'first_paid_journeys':True,'bus_alight':reached_bus,'bus_alight_used_line':reached_bus and used_at_bus,
                    'bus_alight_first_line':reached_bus and first_at_bus,'confirmed_bus_or_rail':reached_bus or rail,
                    'confirmed_used_line':(used_at_bus if reached_bus else rail and seen_line),
                    'rail_board':rail,'rail_only_additional':rail and not reached_bus}
        for metric,ok in categories.items():counts[hour,first[2],metric]+=w*ok
    with (HERE/'11월5일_카드연결_시간별.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['first_board_hour','first_board_stop','metric','passengers'])
        writer.writerows([*k,v] for k,v in sorted(counts.items()))
    import json
    (HERE/'card_checks.json').write_text(json.dumps(dict(quality),ensure_ascii=False,indent=2),encoding='utf-8')
    print('linked journey counts exported',flush=True)


if __name__=='__main__':main()
