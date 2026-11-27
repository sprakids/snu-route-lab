"""Compare full passenger ledgers to card transactions and field reports."""
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
import sys

HERE = Path(__file__).resolve().parent
V12 = HERE.parent/'261125170855'
ACC = V12/'comparison_20261127/accuracy'
sys.path.insert(0,str(ACC))
from check_r_regressions import card_observations, field_rows
from score_versions import DAYS, SERVICES, records, read, save_json, write_rows, transit

TARGET = '120000173'
NEAR = ['120000174','120000190']
HOURS = range(15,19)


def folder(variant,key):
    return V12/'runs/candidate'/key if variant=='V12' else HERE/'runs'/variant/key


def compare():
    names, observed, campus = card_observations()
    common = read(V12/'viewer-data/common.json.gz')
    route_ids = {r['name']:r['id'] for r in read(HERE.parent/'app/data/network.json')['routes']}
    raw = records(ACC.parent/'일자별_정류장승하차.csv')
    daily_obs = defaultdict(list)
    for r in raw:
        if r['비교상태'].startswith('동일') and r['정류장ID']==TARGET:
            daily_obs[DAYS[date.fromisoformat(r['날짜']).weekday()]].append(r)
    detail, card, design, field, daily, safety = [], [], [], [], [], []
    field_source = [records(ACC/f) for f in ['queue.csv','departures.csv','personal.csv']]
    for service in SERVICES:
        for variant in (('origin','choice','both') if service=='peak' else ('both',)):
            field.extend(field_rows([HERE/'runs'],variant,service,*field_source))
        for day in DAYS:
            key = f'{service}-{day}'
            singles = day=='thu' or (service=='peak' and day in ('mon','tue','wed'))
            variants = ['V12','origin','choice','both'] if singles else ['V12','both']
            for v in variants:
                ref = read(folder('both',key)/'summary.json')
                if v!='V12':
                    s = read(folder(v,key)/'summary.json')
                    d,actual = s['design'],s['upper_actual']
                    total, planned = d['upper_r'],d['first_target_r']
                else:
                    s = read(folder(v,key)/'summary.json')
                    d, actual = ref['design'],ref['upper_actual_v12']
                    total, planned = d['upper_v12'],d['first_target_v12']
                design.append(dict(service=service,day=day,model=v,campus=s['daily'],upper_mass=total,
                                   planned_first_target=planned,planned_pct=100*planned/total,
                                   actual_first_target=actual['first_board_mass'],
                                   actual_first_pct=100*actual['first_board_mass']/total,
                                   actual_ever_target=actual['ever_board_mass'],
                                   actual_ever_pct=100*actual['ever_board_mass']/total))
                safety.append(dict(service=service,day=day,model=v,daily=s['daily'],
                                   **{k:s[k] for k in ['max_continuous_wait','over20_weight','capacity_violations','unserved']}))
                audit=read(folder(v,key)/f'audit-{key}.json.gz')
                boards,_,_,od=transit(audit,common,set(names),campus)
                for r in daily_obs[day]:
                    k = route_ids[r['노선']],int(r['순번']),TARGET
                    if v=='V12':
                        field_key=('기준' if service=='regular' else '피크')+'모의승차'
                        assert abs(boards[k]-float(r[field_key]))<.000501
                    daily.append(dict(service=service,model=v,day=day,date=r['날짜'],route=r['노선'],
                                      seq=r['순번'],observed=int(r['실측승차']),predicted=boards[k]))
                if day!='thu':
                    continue
                for stop in names:
                    for h in HOURS:
                        detail.append(dict(service=service,model=v,stop_id=stop,stop=names[stop],hour=h,
                                           observed=observed[stop,h],modeled=od[stop,h]))
                scopes = {'제2공학관':[TARGET], '제1공학관':[NEAR[0]], '공대입구':[NEAR[1]],
                          '인근 2곳':NEAR, '나머지 35곳':[n for n in names if n not in [TARGET,*NEAR]],
                          '전체 38곳':list(names)}
                for scope,stops in scopes.items():
                    y=[sum(observed[stop,h] for stop in stops) for h in HOURS]
                    m=[sum(od[stop,h] for stop in stops) for h in HOURS]
                    card.append(dict(service=service,model=v,scope=scope,hourly_observed=y,hourly_pred=m,
                                     obs_total=sum(y),pred_total=sum(m),late_share=100*sum(m[2:])/sum(m),
                                     stop_hour_mae=mean(abs(observed[s,h]-od[s,h]) for s in stops for h in HOURS)))
    write_rows(HERE/'목요일_38곳_시간별.csv',detail)
    write_rows(HERE/'윗공대_출발과_실제승차.csv',design)
    write_rows(HERE/'별도날짜_제2공학관_노선별.csv',daily)
    write_rows(HERE/'현장관측.csv',field)
    write_rows(HERE/'운영검산.csv',safety)
    save_json(HERE/'card_scores.json',card)

    extra = []
    for service in SERVICES:
        # Different weekdays have distinct demand levels. Compare exact route sequence on each date.
        for v in ('V12','both'):
            other = [r for r in daily if r['model']==v and r['service']==service and r['date']!='20261105']
            sums = defaultdict(lambda:[0.,0.])
            for r in other:
                sums[r['date']][0]+=r['observed']
                sums[r['date']][1]+=r['predicted']
            extra.append(dict(service=service,model=v,dates=len(sums),cells=len(other),
                              mean_daily_observed=mean(y for y,_ in sums.values()),mean_daily_pred=mean(m for _,m in sums.values()),
                              daily_sum_mae=mean(abs(y-m) for y,m in sums.values()),
                              route_day_mae=mean(abs(r['observed']-r['predicted']) for r in other)))
    save_json(HERE/'other_dates_scores.json',extra)
    assert len(detail)==2*4*38*4 and len(field)==76 and len(safety)==30
    for r in safety:
        assert r['unserved']==0 and r['capacity_violations']==0


if __name__=='__main__':
    compare()
