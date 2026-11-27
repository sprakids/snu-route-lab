from pathlib import Path
import shutil,json,hashlib
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'peak_pair_correction_2026-11-10/candidate_ui'

def build():
    OUT.mkdir(exist_ok=True)
    for name in ('viewer-v5.js','graphs-v5.js'):
        original=OUT/('before-'+name)
        if not original.exists():shutil.copy2(ROOT/'public'/name,original)
    source=(OUT/'before-viewer-v5.js').read_text(encoding='utf8')
    old="['walk_choices_v1','capacity_v9']]);";assert old in source
    source=source.replace(old,"['walk_choices_v1','capacity_v9'],['corrected_supply_v1','capacity_v11']]);",1)
    source=source.replace("||'capacity_v9';","||'capacity_v11';",1)
    source=source.replace("state.walkChoices=CITY_DATASET==='capacity_v9';","state.supplyCorrected=CITY_DATASET==='capacity_v11';\nstate.walkChoices=CITY_DATASET==='capacity_v9'||state.supplyCorrected;",1)
    insertion='''
if(state.supplyCorrected){
  document.title='하교길 실험실 · 설입44명·피크2대 공급';
  $('policy').querySelector('[value="city"]').textContent='정원44·피크2대';
  const note=document.querySelector('.city-model-note');
  if(note)note.innerHTML='행정관 설입 주간44명/차 · 가정한15~19시 피크 창에 두 대 묶음. 기존 행동계수 유지. <a href="capacity-correction.html" target="_blank" rel="noopener">정원·공급·관측 비교 ↗</a> · <a href="./?dataset=walk_choices_v1">이전 v9 ↗</a>';
  const mobile=document.querySelector('.empirical-mobile-note');
  if(mobile)mobile.innerHTML='설입44명·피크2대 · <a href="capacity-correction.html" target="_blank" rel="noopener">가정·전체 대기 검사</a> · <a href="./?dataset=walk_choices_v1">이전 v9</a>';
  document.querySelectorAll('a[href="walk-choice-methodology.html"]').forEach(a=>a.href='capacity-correction.html');
  for(const p of document.querySelectorAll('p')){
    p.innerHTML=p.innerHTML.replace('셔틀60·역순환25','설입 주간44·기타 통학60·역순환25');
  }
  const p=document.createElement('p');p.className='city-source-note';p.textContent='설입 주간44명/차·가정한15~19시 명목 배차마다 별도 차량 두 대. 정확한 피크 경계·반복 간격은 미확인입니다. 야간 도서관60명은 기존 미확인 가정입니다. 기존 경로 변경 규칙과 수요는 유지했으며 신규 행동 프로토타입은 운영에 적용하지 않았습니다. 도착·탑승·출발은 전역 모형에서 같은 사건으로 근사하므로 현장189초/30초를 각각 재현하지 않습니다.';$('about-dialog').append(p);
}else if(state.walkChoices){
  const note=document.querySelector('.city-model-note');if(note)note.innerHTML=note.innerHTML.replace('현재 기본 모형','이전 v9 모형');
}
'''
    marker="const pathShape="
    # Place after dataset-specific introductory notes, before map helpers.
    index=source.index('\nfunction ',source.index('if(state.walkChoices)'))
    source=source[:index]+insertion+source[index:]
    target="    $('scenario-note').textContent=";start=source.index(target);end=source.index('\n',start)
    source=source[:end]+"\n    if(state.supplyCorrected&&state.policy==='city')$('scenario-note').textContent+=(state.scenario==='peak'?' · 設入3分ごと2台':' · 設入4分ごと2台').replace('設入','설입').replace('分ごと2台','분 명목 배차마다2대')+' · 15~19시는 적용창 가정';"+source[end:]
    source=source.replace("(state.scenario==='peak'?' · 設入3分ごと2台':' · 設入4分ごと2台').replace('設入','설입').replace('分ごと2台','분 명목 배차마다2대')","(state.scenario==='peak'?' · 설입3분 명목 배차마다2대':' · 설입4분 명목 배차마다2대')")
    (OUT/'viewer-v5.js').write_text(source,encoding='utf8')
    graph=(OUT/'before-graphs-v5.js').read_text(encoding='utf8')
    old="state.walkChoices?'혼잡·도보 경로 변경':";assert old in graph
    graph=graph.replace(old,"state.supplyCorrected?'정원44·피크2대':state.walkChoices?'혼잡·도보 경로 변경':",1)
    (OUT/'graphs-v5.js').write_text(graph,encoding='utf8')
    print('Prepared corrected-supply UI with historical v9 selector retained')

if __name__=='__main__':build()
