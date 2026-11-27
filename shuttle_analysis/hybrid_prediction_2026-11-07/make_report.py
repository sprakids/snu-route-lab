"""Source-linked scientific readout; preserve the earlier experiment and plots."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'.taskdeps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import pandas as pd
from common import *

LABEL={'history_only':'과거 평균','weekday_history':'요일별 과거 평균',
       'history_plus_background':'과거 평균 + 배경', 'history_plus_class':'과거 평균 + 수업',
       'history_background_class':'과거 평균 + 수업·배경'}
GROUPS=('forward_20261102','retrospective_20261012_16','all_six_dates')
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])

def main():
    report=ROOT/'과거평균_수업_배경_결합모형_검증.md'
    assert not report.exists(),'Preserve the previous report'
    evaluation=load(ROOT/'evaluation/evaluation_receipt.json');frozen=load(ROOT/'selection_frozen.json')
    score=pd.read_csv(ROOT/'evaluation/metrics.csv',dtype={'group':str})
    score=score[score.scope=='campus_origin_bbox']
    by={(r.group,r.model):r for r in score.itertuples()}
    fw=by[(GROUPS[0],'history_only')];fc=by[(GROUPS[0],'history_background_class')];fd=by[(GROUPS[0],'weekday_history')]
    rw=by[(GROUPS[1],'history_only')];rc=by[(GROUPS[1],'history_background_class')]
    cw=by[(GROUPS[2],'history_only')];cc=by[(GROUPS[2],'history_background_class')]
    ci=evaluation['retrospective_day_cluster_bootstrap_WAPE_improvement_95pct_interval']
    fp=FontProperties(fname='C:/Windows/Fonts/malgun.ttf')
    plt.rcParams['font.family']=fp.get_name();plt.rcParams['axes.unicode_minus']=False
    models=['history_only','history_background_class','weekday_history'];colors=['#747d8c','#245e92','#4d7c65']
    fig,axes=plt.subplots(1,2,figsize=(10.5,3.4),sharex=True)
    for ax,group,title in zip(axes,GROUPS[:2],['11월 2일 · 새 월요일 1일','10월 12~16일 · 미사용 과거 5일']):
        values=[by[(group,m)].WAPE*100 for m in models]
        ax.barh(range(3),values,color=colors,height=.56)
        ax.set_yticks(range(3),['과거 평균','수업·배경 결합','요일별 과거 평균']);ax.invert_yaxis()
        for i,v in enumerate(values):ax.text(v+.25,i,f'{v:.2f}%',va='center',fontsize=10)
        ax.set_xlim(0,26);ax.set_xticks([0,5,10,15,20,25]);ax.set_xlabel('WAPE (%) · 낮을수록 좋음',fontsize=10)
        ax.set_title(title,fontsize=12,pad=14);ax.spines[['right','top','left']].set_visible(False)
        ax.tick_params(axis='y',length=0,labelsize=10);ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
    fig.suptitle('시간별 버스 구간 재차합 예측 · 고정된 모형의 새 날짜 평가',fontsize=13,y=1.02)
    fig.text(.5,-.02,'11월 6일 수강자료 소급 적용 · 배경은 과거 캠퍼스 bbox 밖 통행량 대리지표',ha='center',fontsize=9)
    fig.tight_layout(w_pad=3)
    fig.savefig(ROOT/'heldout-error-comparison.png',dpi=170,bbox_inches='tight');plt.close(fig)
    metric_rows=[]
    for model in MODELS:
        metric_rows.append((LABEL[model],*[f'{by[(g,model)].WAPE*100:.3f}%' for g in GROUPS]))
    daily=[]
    for date in sorted(evaluation['test_dates']):
        base=by[(date,'history_only')];mix=by[(date,'history_background_class')];hist=by[(date,'weekday_history')]
        daily.append((date,int(base.valid_cells),f'{base.WAPE*100:.3f}%',f'{mix.WAPE*100:.3f}%',
                      f'{(base.WAPE-mix.WAPE)*100:+.3f}',f'{hist.WAPE*100:.3f}%'))
    artifact=load(ROOT/'frozen_models.json')
    coefficients=[(ROUTES[r],*[f'{x:.5f}' for x in z]) for r,z in artifact['models']['history_background_class']['coefficients'].items()]
    tune=frozen['selected'];tune_rows=[(LABEL[m],f'{tune[m]["development_score"]["WAPE"]*100:.3f}%',str(tune[m]['settings'])) for m in MODELS]
    lines=[
        '# 과거 평균·수업 종료 수요·배경 패턴 결합모형의 새 날짜 검증',
        '',
        '2026-11-07. 관측값은 서울시 T-data 제공 시간별 버스 구간 재차합이며, 모형 계수와 학생 거주·귀가 확률을 구분했습니다.',
        '',
        f'**결합모형은 구현됐지만 개선 폭은 작습니다.** 개발 기간 뒤인 11월 2일의 WAPE는 과거 평균 {fw.WAPE*100:.3f}% → 결합형 {fc.WAPE*100:.3f}%로 {(fw.WAPE-fc.WAPE)*100:.3f}%p(상대 {(1-fc.WAPE/fw.WAPE)*100:.2f}%) 줄었습니다. 요일별 과거 평균은 {fd.WAPE*100:.3f}%로 결합형보다 좋았습니다. 과거 평가 주의 개선은 {(rw.WAPE-rc.WAPE)*100:.3f}%p에 그쳤고, 날짜별로는 악화한 날도 있습니다. 수업·배경 신호의 추가 효과가 안정적으로 확인됐다고 말할 근거는 부족합니다.',
        '',
        '![미사용 날짜의 예측 오차 비교](heldout-error-comparison.png)',
        '',
        '## 날짜와 평가 범위',
        '',
        '- 학습 15일: 9/7~11, 9/14~18, 10/19~23. 각 요일 3일씩입니다.',
        '- 튜닝 5일: 10/26~30. 이전 실험에서 열람한 날짜이므로 모두 개발 자료로 재분류했습니다.',
        '- 새 평가: 11/2(개발 기간 뒤 월요일 1일)과 10/12~16(일부 개발 날짜보다 앞인 후향 평가 5일). 두 결과를 분리했습니다.',
        '- 11/3~6은 인증된 첫 페이지 조회에서 빈 배열이었습니다. 빈 응답을 교통량 0으로 쓰지 않았습니다.',
        '- 모형·모든 전처리 통계·하이퍼파라미터를 확정하고, 6일 전체 예측값을 파일에 저장한 다음 새 목표 날짜 자료를 수집했습니다. 이후 모형·계수·범위를 다시 조정하지 않았습니다.',
        '- 관측 대상은 5511·5513·5516·관악02-1·관악02-2의 259구간입니다. 주 비교는 이전과 같은 잠정 bbox 안의 출발 정류장을 가진 125구간, 양방향, 12:00~22:59입니다. bbox는 공식 학내 경계가 아닙니다.',
        f'- 새 6일의 주 범위 예상 8,250셀 중 {int(cc.valid_cells):,}셀을 비교했습니다. 10/13 관악02-2의 22시 17개 구간은 null이어서 모든 모형에서 공통 제외했습니다. 관측된 0은 유지했고 모형이 0인 셀도 제외하지 않았습니다.',
        '',
        '**시점 한계:** 11월 2일은 목표 날짜 순서상 개발 기간 뒤이지만, 수업 특징은 11월 6일 수강편람에서 파생됐습니다. 실제 당시 수강·취소·휴강·출석을 복원한 엄격한 사전 예측 실험은 아닙니다. 후향 5일을 미래 5일처럼 표현하지 않으며, 월요일 1일을 다른 요일에 일반화하지 않습니다.',
        '',
        '## 모형이 어떻게 바뀌었는가',
        '',
        '기본값 H는 학습 자료의 노선·정류장 순서·출발/도착 ID·시간별 전체 승객 재차합 평균입니다. H에는 수업 관련 승객과 배경 승객이 이미 함께 들어 있습니다. 따라서 수업 모형의 평균 인원을 다시 더하지 않고, 해당 요일의 수업 신호가 학습 평균에서 벗어나는 부분을 더합니다.',
        '',
        '`예측 = max(0, H + a × 배경편차 + b × 수업편차 + c × 1시간 지연 수업편차)`',
        '',
        '1. **수업 신호:** 기존 강의동·종료시각·보행·대기·승하차 경로 모형의 구간 통과량을 재사용했습니다. 목적지 균등·기숙사 5,772/29,613·즉시 이동 50%의 참고 가정은 유지했습니다. 이 값은 고유 학생 수나 실제 탑승 기록이 아닙니다.',
        '2. **중심화와 지연:** 같은 target 구간·시간의 유효 학습 날짜로 현재 수업 특징과 1시간 전 특징의 평균을 각각 구해 뺐습니다. 12시의 지연 신호는 11시 값을 사용합니다. 통계적 지연 특징이며 실제 학생을 정확히 1시간 머무르게 한 경로 시뮬레이션은 아닙니다.',
        '3. **배경 신호:** 학습 자료의 bbox 밖 구간에서 노선·요일·시간별 평균과 노선·시간 평균의 비율 R을 구하고 `H × (R−1)`을 사용했습니다. 예측 대상일의 관측값은 입력하지 않습니다. 이 신호에는 서울대 학생과 배차 차이도 섞일 수 있어 실제 비학생 수라고 해석하지 않습니다.',
        '4. **과적합 제한:** 노선마다 배경 계수 a는 0~1, 수업 계수 b,c는 0 이상으로 제한했습니다. 평균 제곱손실에 각 특징의 학습 평균제곱으로 정규화한 ridge를 더했습니다. 원 단위 계수로 제약을 걸고 작은 active-set 문제를 풀어 KKT 조건을 검사했습니다. 클리핑 전 손실을 적합하고 예측 때만 0 아래를 자릅니다.',
        '5. **선택과 재적합:** 배경·수업 ridge는 각각 0.01/0.1/1/10의 사전 후보에서 전체 튜닝 WAPE로 선택했습니다. 하이퍼파라미터는 모든 노선에 공통이고 계수만 노선별입니다. 최종 선택을 유지한 채 학습+튜닝 20일로 평균·대리지표·중심화·계수를 다시 맞췄습니다.',
        '',
        '요일별 과거 평균은 같은 요일의 평균을 전체 평균 쪽으로 줄인 비교 기준선입니다. 학습 관측 수 n에 대해 가중치 n/(n+k)를 적용했고 k는 사전 후보에서 튜닝으로 선택했습니다. 수업·배경을 뺀 두 비교 모형도 각각 독립적으로 튜닝해 공개합니다.',
        '',
        '## 새 날짜의 오차',
        '',
        'WAPE = 절대오차 합 / 관측 합. 낮을수록 좋으며, 정확도나 확률로 바꾸어 읽지 않습니다. 첫 열의 11/2는 1,375셀, 후향 주는 6,858셀입니다. 합산 열은 보조 요약이며 미래 6일 성능을 뜻하지 않습니다.',
        '',
        table(['모형','11/2 월요일','10/12~16 후향 주','새 6일 합산'],metric_rows),
        '',
        table(['날짜','유효 셀','과거 평균','수업·배경 결합','개선(%p, 양수가 개선)','요일별 평균'],daily),
        '',
        f'모형 선택에 사용하지 않은 **사후 보조 분석**으로, 후향 5일을 날짜 단위로 재표집한 개선량의 조건부 95% bootstrap 구간은 {ci[0]*100:+.3f}~{ci[1]*100:+.3f}%p로 0을 포함합니다. 단 5개 날짜이고 모형 적합 불확실성까지 포함한 구간도 아니므로 안정적인 개선의 증거로 보지 않습니다. 11/2 한 날짜에는 날짜 수준의 불확실성 구간을 붙이지 않았습니다.',
        '',
        '**수업·배경 효과의 해석:** 11/2에서는 수업만 추가하거나 배경만 추가해도 기준 평균보다 조금 나아졌습니다. 후향 주에서는 수업만 추가한 모형이 더 나빴고, 결합형의 개선도 매우 작았습니다. 더 단순한 요일별 역사 평균이 두 평가 묶음 모두에서 결합형보다 좋았습니다. 따라서 결합형을 기본 모형으로 채택해야 한다고 결론 내리지 않습니다.',
        '',
        '## 보정 계수와 개발 결과',
        '',
        table(['노선','배경 a','현재 수업 b','1시간 지연 c'],coefficients),
        '',
        '위 계수는 잔차 예측용입니다. 0은 이번 손실·제약·규제 아래 기여가 선택되지 않았다는 뜻이며, 승객이 없거나 수업이 영향을 주지 않는다는 뜻이 아닙니다. 귀가 확률·거주율·비학생 비율로 바꾸어 쓰지 않습니다.',
        '',
        table(['모형','튜닝 WAPE','선택 설정'],tune_rows),
        '',
        '기존 실험의 20.15%와 이번 19.35%를 개선량으로 비교하지 않습니다. 학습 자료가 5일에서 15일로 달라졌기 때문입니다. 이번 표의 모든 예측은 같은 20일 재적합 자료와 같은 새 평가 관측 마스크를 사용했습니다.',
        '',
        '## 적용과 남은 검증',
        '',
        '- 의존성 없는 predictor.py와 frozen_models.json으로 계수·역사 패턴을 로드해 예측할 수 있습니다. 입력은 날짜·노선·정류장 순서·양 끝 ID·시간이며 당일 승객 관측값이나 API 키를 받지 않습니다. 운영 앱과 Vercel에는 아직 적용하지 않았습니다.',
        '- 현재 모형은 같은 요일이면 같은 역사적 보정을 냅니다. 당일 비·행사·실제 휴강·운행 간격 변화를 감지하는 모형은 아닙니다.',
        '- 제공된 값은 1시간 구간 재차합입니다. 평균·최대 재차인원과 운행횟수가 null이고, 시간 귀속의 세부 산식도 기관 확인 전입니다. 한 대당 혼잡률·5분 대기열·셔틀 탑승 실패·버스와 셔틀 줄의 상관계수는 검증하지 않았습니다.',
        '- 더 큰 개선을 검증하려면 실제 시점의 수강·휴강 정보, 배차·차량별 부하, 학교 밖 OD와 셔틀 대기 관측 등이 필요합니다. 이번 새 평가 값을 다시 튜닝 자료로 쓸 경우에는 별도의 미사용 평가 날짜가 추가로 필요합니다.',
        '',
        '## 근거와 재현 파일',
        '',
        '- [서울시 T-data API1025 공식 안내](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1025): 일자·시간대·노선·구간별 승객수, 교통정책지원시스템(TAIMS). 재차합 등 필드 제공.',
        '- experiment_plan.json: 새 목표값을 보기 전 고정한 날짜·후보·시간·범위·해석.',
        '- development/tuning_candidates.csv, selected_settings.json, fit_checks.json: 개발 후보 전체와 선택·제약 검산.',
        '- selection_frozen.json: 평가 자료 수집 전 생성된 모형·예측·계획 해시와 개발 입력 해시.',
        '- frozen_models.json, frozen_test_predictions.csv: 모든 비교 모형과 6일의 사전 고정 예측.',
        '- evaluation/metrics.csv, cell_predictions_and_observations.csv, source_audit.json, evaluation_receipt.json: 날짜·노선·범위별 오차와 실제 관측·예측 대조.',
        '- predictor.py: 외부 라이브러리 없이 고정된 예측을 재현하는 계산 코드.',
        '- 원 API 페이지와 목표 노선 JSON은 이전 tdata_calibration_2026-11-07/collected/YYYYMMDD/에 보존했습니다. 키는 프로젝트 밖 Windows DPAPI 보관을 그대로 사용했습니다.',
        '',
        '제공: 서울특별시 서울교통 빅데이터 플랫폼 / 교통정책지원시스템(TAIMS). 저작권자 표시(BY) 조건에 따라 출처를 표시합니다. 모형·가공·해석의 책임은 본 프로젝트에 있습니다.',
        ''
    ]
    report.write_text('\n'.join(lines),encoding='utf-8')
    dump(ROOT/'report_receipt.json',{'report_sha256':sha(report),'plot_sha256':sha(ROOT/'heldout-error-comparison.png'),
                                   'evaluation_receipt_sha256':sha(ROOT/'evaluation/evaluation_receipt.json'),
                                   'freeze_hash_unchanged':sha(ROOT/'frozen_models.json')==frozen['frozen_model_sha256']})
    print(str(report))

if __name__=='__main__':main()
