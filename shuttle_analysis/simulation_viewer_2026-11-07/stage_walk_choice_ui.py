"""Prepare a v9 UI candidate without changing the live or source-default viewer."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'crowding_walk_choices_2026-11-10/candidate_ui'

def build():
    OUT.mkdir(exist_ok=True);public=ROOT/'public';source=public/'viewer-v5.js'
    s=source.read_text(encoding='utf8')
    old="['gate_access_v1','capacity_v7']]);"
    assert old in s;s=s.replace(old,"['gate_access_v1','capacity_v7'],['walk_choices_v1','capacity_v9']]);",1)
    s=s.replace("||'capacity_v7';","||'capacity_v9';",1)
    s=s.replace("state.gateAccess=CITY_DATASET==='capacity_v7';","state.walkChoices=CITY_DATASET==='capacity_v9';\nstate.gateAccess=CITY_DATASET==='capacity_v7'||state.walkChoices;")
    s=s.replace('if(state.gateAccess){','if(state.gateAccess&&!state.walkChoices){',1)
    anchor="const map=L.map('map'"
    assert anchor in s
    block="""if(state.walkChoices){
  document.title='하교길 실험실 · 혼잡에 따른 확률적 경로 변경';
  $('policy').querySelector('[value="city"]').textContent='혼잡·도보 경로 변경';
  const note=document.createElement('p');note.className='city-model-note empirical-source-note';
  note.innerHTML='현재 기본 모형 · 긴 줄·반복 만차에 따라 다른 노선·교내 셔틀·도보를 다시 고려합니다. 변경 횟수에 제한은 없습니다. <a href="walk-choice-methodology.html" target="_blank" rel="noopener">행동 가정·전 정류장 검사 ↗</a> · <a href="./?dataset=gate_access_v1">이전 v7 ↗</a>';
  document.querySelector('.intro').append(note);
  const mobile=document.createElement('p');mobile.className='empirical-mobile-note';mobile.innerHTML='혼잡에 따른 경로 변경 · <a href="walk-choice-methodology.html" target="_blank" rel="noopener">가정·대기 검사</a> · <a href="./?dataset=gate_access_v1">이전 v7</a>';document.querySelector('.sidebar').append(mobile);
  for(const p of $('about-dialog').querySelectorAll('p'))if(p.textContent.includes('최대2회'))p.textContent='줄·만차·누적 대기와 보행 경로의 거리를 함께 고려합니다. 변경 횟수에 상한은 없고, 두 번째부터 기본 변경 확률이 급격하게 낮아지며 반복 만차·장시간 대기 때 다시 높아집니다. 0~500m의 기본 도보 고려도는 같고 1km를 넘으면 빠르게 낮아집니다. 20분은 모든 정류장 대기의 검토 기준입니다. 대기를 강제로 잘라내지 않습니다. 이 계수는 사용자 시나리오이며 실측 행동 비율이 아닙니다.';
  const doc=document.querySelector('.header a.methodology-link');if(doc)doc.href='walk-choice-methodology.html';
  const detail=document.createElement('p');detail.className='city-source-note';detail.innerHTML='이전 모형의 같은 수강 기반 가중 이동량과 목적지·출발시각, 차량 정원·배차·속도를 유지해 행동 규칙만 바꿨습니다. 약40명은 서울대정문·법대사회대입구에 대한 사용자 기억의 참고값이며 실측 상한이 아닙니다. <a href="walk-choice-methodology.html" target="_blank" rel="noopener">모든 요일·정류장 검증과 출처 ↗</a>';$('about-dialog').append(detail);
}
"""
    s=s.replace(anchor,block+anchor,1)
    (OUT/'viewer-v5.js').write_text(s,encoding='utf8',newline='')
    p=public/'graphs-v5.js';g=p.read_text(encoding='utf8')
    g=g.replace("(state.gateAccess?'정문 도보 보정 모형':", "(state.walkChoices?'혼잡·도보 경로 변경':state.gateAccess?'정문 도보 보정 모형':",1)
    (OUT/'graphs-v5.js').write_text(g,encoding='utf8',newline='')
    (OUT/'source_manifest.json').write_text(json.dumps({'status':'CANDIDATE_NOT_ACTIVATED','inputs':{
        name:hashlib.sha256((public/name).read_bytes()).hexdigest() for name in ['viewer-v5.js','graphs-v5.js']}},indent=2),encoding='utf8')
    print('Prepared candidate UI; default source and production unchanged')

if __name__=='__main__':build()
