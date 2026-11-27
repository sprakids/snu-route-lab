"""Create the v5 entry point while retaining the original adaptive.html replay."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent


def build():
    source=(ROOT/'public/adaptive.html').read_text(encoding='utf-8')
    source=source.replace('viewer-v4.js','viewer-v5.js')
    source=source.replace('<link rel="stylesheet" href="viewer-v2.css">','<link rel="stylesheet" href="viewer-v2.css"><link rel="stylesheet" href="viewer-v5.css">')
    source,n=re.subn(r'<title>.*?</title>','<title>하교길 실험실 · 시내버스·셔틀 정원과 운행계획</title>',source);assert n==1
    source,n=re.subn(r'<h1>.*?</h1>','<h1>시내버스도<br>자리가 있어야 탑니다.</h1>',source);assert n==1
    source,n=re.subn(r'<select id="policy">.*?</select>','<select id="policy"><option value="city" selected>시내 정원 v5</option><option value="adaptive">이전 v4</option><option value="fixed">이전 v3</option></select>',source);assert n==1
    source=source.replace('대기줄을 본 뒤<select id="policy">','계산 모형<select id="policy">')
    source,n=re.subn(r'(<label class="field">요일<select id="weekday">.*?</select></label>)',
        r'\1<label class="field">차량 표시<select id="vehicle-filter"><option value="all">전체 차량</option><option value="city">시내버스만</option><option value="shuttle">셔틀만</option></select></label>',source);assert n==1
    source=source.replace('<p id="last-bus" class="last-bus"></p>','<p id="last-bus" class="last-bus"></p><p id="city-history" class="city-history"></p>')
    source,n=re.subn(r'(<p class="mobile-caveat">).*?(</p>)',
        r'\1셔틀60·역순환25 / 시내50·마을24(제원 참고). 실차종 미확인·외부 승객 미포함. 교내 최고40·교외65 km/h.\2',source);assert n==1
    source=source.replace('<footer class="sidebar-footer">','<footer class="sidebar-footer"><p><strong>시내: 제원 참고정원 50명 / 마을 24명</strong><br>실제 투입 차종·등록정원 미확인 · 배경 승객 미포함. 차량 표시는 통계 계산을 바꾸지 않습니다.</p>')
    source=source.replace('지도와 같은 계산을 그래프로','시내·셔틀 대기열을 같은 계산으로')
    source=source.replace('다음 셔틀','다음 버스')
    source=source.replace('<div id="map"','<p class="stop-map-hint">정류장 표식을 누르면 현재 대기량을 볼 수 있습니다.</p><div id="map"')
    about='''<dialog id="about-dialog" aria-labelledby="about-title"><form method="dialog"><button aria-label="안내 닫기" class="close-button">닫기</button></form>
<h2 id="about-title">시내버스와 셔틀의 정원·운행계획</h2>
<p><a href="methodology.html" target="_blank" rel="noopener noreferrer">전체 가정·자료·출처 설명서 ↗</a> · <a href="methodology.md" download>Markdown 내려받기</a></p>
<p class="city-source-note">서울시 공개 노선정보의 <strong>평일 첫차·막차·배차간격</strong>과 저장된 구간속도 제공값을 반영했습니다. 아래 첫차·막차는 <strong>기점 출발 계획</strong>이며 각 정류장 통과시각은 재구성한 모형 시각입니다. 실제 회차별 출발표·현재 실차 GPS가 아닙니다.</p>
<div id="city-plan-table" class="city-plan-wrap"></div>
<h3>정원과 공유 대기열</h3>
<p>일반 시내버스는 APOLLO 1100의 좌석24+입석26=<strong>승객50명</strong>, 마을버스는 APOLLO 900의 좌석20+입석4=<strong>승객24명</strong>을 제조사 제원 참고 시나리오로 적용했습니다. 운전석은 제외했습니다. 해당 차종이 각 노선에 실제로 배치됐거나 모든 실차의 등록정원이 이 값이라는 확인은 없습니다. 대형 셔틀60·역순환25는 기존 모형 조건을 유지합니다.</p>
<p>같은 모형 회차에서 앞 정류장의 승차·하차·여석을 공유합니다. 못 탄 흐름은 빨간 점으로 남아 다음 호환 차량을 기다립니다. 서울대학교21128의 다섯 노선 공동 대기는 단일 대기열에서 먼저 오는 탑승 가능한 차량을 이용하며, 다른 노선을 기다리는 흐름이 호환 승객의 승차를 막지는 않습니다.</p>
<h3>과거 자료의 사용 범위</h3>
<p>서울시 제공기관의 저장 구간속도로 시내 이동시간을 늦추되 교내 최고40·교외 목표65km/h의 기존 가감속 곡선보다 빠르게 만들지 않았습니다. 시간당 구간 재차인원합은 같은 노선·방향·요일·시간대의 과거 비교값으로 표시합니다. 평균·최대 재차인원과 운행횟수가 빠져 있어 이를 실차 한 대의 인원·여석으로 환산하지 않았습니다.</p>
<p><strong>외부 배경 승객은 미포함</strong>입니다. 표시 차내 인원과 대기열은 수업 기반 가중 통행 모형이며 실제 전체 승객·고유 학생 수가 아닙니다. 제원 정원만으로 현실의 탑승 가능성을 보장하지 않습니다. 목적지 비중·기숙사19.49%·수업 직후 이동50%는 기존 참고 가정을 유지했습니다.</p>
<h3>경로 변경·시각·그래프</h3>
<p>도착·60초 간격·만차 뒤에 남은 시간을 비교해 예상120초 이상 개선되면 최대2회 변경하고 변경 후180초 유지합니다. 시내 줄에서는 직접 도보와 같은 승차지의 준비된 호환 노선 후보를 비교합니다. 이미 기다린 시간은 재가산하지 않습니다. 실제 선호를 조사해 적합한 계수는 아닙니다.</p>
<p>피크 최소 간격은15~19시 셔틀 입구역3분·순환5분이며 기준은4분·6분입니다. 시내버스는 두 시나리오 모두 같은 공식 평일 간격을 씁니다. 야간·막차와 차량회전 실행 가능성은 별도 한계가 있습니다. 초기 경로는 대표 난수시드20261106의 기존 선택을 유지했습니다.</p>
<p>점1개는 약2명 상당의 표시 표본입니다. 정원과 통계는 전체 가중 흐름으로 계산합니다. 그래프 평균 대기는 해당 승차지의 탑승 완료 흐름 기준이고 변경·미탑승은 별도입니다. 이전v3/v4는 시내 정원을 제한하지 않은 자료로 보존했으며 새v5와의 차이를 정원 한 가지 요인의 효과라고 해석할 수 없습니다.</p>
</dialog>'''
    source,n=re.subn(r'<dialog id="about-dialog".*?</dialog>',lambda m:about,source,flags=re.S);assert n==1
    (ROOT/'public/city.html').write_text(source,encoding='utf-8')
    print('Built public/city.html without changing the existing default entry point.')


if __name__=='__main__':build()
