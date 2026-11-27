"""Paired initial-assignment contrasts, including explicit downside metrics."""
from pathlib import Path
import csv,json
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;WORK=ANALYSIS/'261112132736'
def read(p):return json.loads(p.read_bytes())
def write_csv(p,rows):
    assert not p.exists()
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    experiment=read(WORK/'origin_pilots-validation.json')['results'];tue=read(ANALYSIS/'261112132407/focal-validation.json')['results'][0]
    get=lambda day,free:next(x for x in experiment if x['case']['day']==day and x['case']['case'].startswith('ablation')==free)
    rows=[]
    for day in ('월','화'):
        main=get(day,False);free=get(day,True) if day=='월' else tue
        assert all(main['case'][k]==free['case'][k] for k in ('day','scenario','seed','operations'))
        for metric in ('walk_min','cumulative_wait_min','total_min','changes'):
            old=free['extended_diagnostics']['finished_trip_quantiles'][metric];new=main['extended_diagnostics']['finished_trip_quantiles'][metric]
            rows.append({'day':day,'scenario':'regular','metric':metric,'preserved_release':WORK.name,
              'free_release':WORK.name if day=='월' else '261112132407',
              **{'free_'+k:v for k,v in old.items()},**{'preserved_'+k:v for k,v in new.items()},
              'free_audit_sha256':free['audit_sha256'],'preserved_audit_sha256':main['audit_sha256']})
    write_csv(WORK/'origin-assignment-comparison.csv',rows)
    lines=['# 초기 배분 보존의 대조 결과','',
      '수요·공급·시드0을 같게 두고 초기 자유 선택과 기존 배분 보존을 비교했습니다. 월요일은 같은 후보 안의 설정 대조이고, 화요일은 앞 후보261112132407의 완료된 자유 선택 결과를 재사용했습니다. 후자의 런타임 파일 중 차이는 보존 설정을 해석하는 run_case 분기이며, 공통 물리/행동 모듈은 같습니다. 각 조건의 소스와 설정 영수증을 보존했습니다.','',
      '보존은 과거 줄 관측에 대한 오차 일부를 줄였지만 여정 시간을 모두 개선한 선택은 아닙니다. 아래에서 두 종류의 목표를 구분합니다. 이것은 오래된 관측에 참고한 구조 선택이므로 독립 검증이 아닙니다.','',
      '|요일|평균 총시간 자유→보존|p99 총시간 자유→보존|최장 총시간 자유→보존|','|---|---:|---:|---:|']
    for day in ('월','화'):
        row=next(x for x in rows if x['day']==day and x['metric']=='total_min')
        cells=[f"{row['free_'+k]:.2f}→{row['preserved_'+k]:.2f}" for k in ('mean','p99','maximum')]
        lines.append('|'+day+'|'+'|'.join(cells)+'|')
    lines += ['', '단위는 분입니다. 원래 V12 대비 여정 꼬리가 개선되는 것과, 수정 후보끼리 모든 목표에서 우월한 것은 구분해야 합니다. 보존 모드의 p99가 자유 선택 모드보다 나빠지는 결과도 그대로 공개합니다. [전체 분포](origin-assignment-comparison.csv).','']
    path=WORK/'ORIGIN_CONTRAST.md';assert not path.exists();path.write_text('\n'.join(lines),encoding='utf8')
    print('ORIGIN_CONTRAST_COMPLETE',len(rows))
if __name__=='__main__':main()
