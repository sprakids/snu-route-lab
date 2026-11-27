import {RouteMap} from './map.js';
const $=id=>document.getElementById(id);
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const minutes=seconds=>Math.max(0,Math.ceil(seconds/60));
const durationText=seconds=>{const n=Math.max(0,Math.round(Number(seconds)||0));return n>=60?`${Math.floor(n/60)}분${n%60?' '+String(n%60)+'초':''}`:`${n}초`;};
const nowSeconds=()=>Date.now()/1000+(state.clockOffset||0);
const distanceLabel=m=>m>=1000?`${(m/1000).toFixed(1)}km`:`${Math.round(m)}m`;
const timeLabel=timestamp=>new Intl.DateTimeFormat('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Seoul'}).format(new Date(timestamp*1000));
const displayCrowd=value=>{const text=String(value||'');return /정보|미확인|혼잡도.*추정/.test(text)?'':text.replace(/ 추정/g,'').replace(/^탑승부담 /,'');};
const evidenceLabel=l=>['observation_simulation_estimate','historical_simulation_estimate'].includes(l.crowd_source)?'이전 관측·과거 등급·수업 신호의 잠정 추정':l.crowd_source==='simulation_scenario_estimate'?'수요 모형의 기준 위험 추정 · 등급 실측 없음':l.crowd_source==='shuttle_simulation_estimate'?'최신 셔틀 시뮬레이션의 탑승부담 추정':l.crowd_source==='pooled_service_estimate'?'공동노선별 혼잡위험의 가중 추정':l.crowd_source==='observed'?'실측':l.crowd_source==='last_observation_estimate'?`${Math.ceil((l.age_seconds||0)/60)}분 전 관측 기반 추정`:l.crowd_source==='calibrated_history'?'검증된 과거 패턴 추정':'정보 부족 · 불확실성 비용 반영';
const modeLabels={fast:'최단시간',comfort:'혼잡도 비교',walk:'최소도보',transfer:'최소환승'};
const shuttleShort=r=>r.short_name||({'41841':'행정관','41946':'순환','41914':'역순환','41843':'대학동','41942':'대학동 야간'}[r.id])||r.name;
const state={bootstrap:null,weights:{time:75,crowd:5,walk:15,transfers:5},preset:'fast',picking:false,customOrigin:null,plan:null,selected:null,request:0,originRevision:0,userLocation:null,locating:false,shuttleRouteId:'41841'};
let map,toastTimer;
state.arrivalPreviews=new Map();state.clockOffset=0;state.previewBusy=false;
state.journey=null;state.planBusy=false;state.queueReport=null;
state.arrivalLegs=new Map();state.nextLegKey=1;
state.mobileView='home';state.mobileFilter='all';state.mobileLimit=12;
state.buildingQueryDirty=false;state.placeMatches=[];state.placeActive=-1;
function normalizePlaceText(value){return String(value||'').normalize('NFKC').toLowerCase().replace(/[‐‑‒–—−]/g,'-').replace(/[^a-z0-9가-힣-]/g,'');}
function searchCampusBuildings(query){
  const raw=String(query||'').slice(0,80).trim(),q=normalizePlaceText(raw).replace(/^(서울대학교|서울대|관악캠퍼스)/,'');if(!q)return [];
  const number=q.match(/^제?(\d+)(?:-(\d+))?동?$/),code=number?String(Number(number[1]))+(number[2]!=null?'-'+String(Number(number[2])):''):null;
  const tokens=raw.split(/\s+/).map(normalizePlaceText).filter(Boolean);
  return (state.bootstrap?.origins||[]).filter(b=>b.official_building_id).map(b=>{
    const n=String(b.number),name=normalizePlaceText(b.name),aliases=(b.aliases||[]).map(normalizePlaceText),eng=normalizePlaceText(b.english_name),all=[n,n+'동',name,eng,...aliases].join('|');let score=Infinity;
    if(code!=null){if(n===code)score=0;else if(n.startsWith(code))score=3;}
    else if(name===q||aliases.includes(q))score=1;
    else if(name.startsWith(q)||aliases.some(a=>a.startsWith(q)))score=2;
    else if(all.includes(q)||tokens.length>1&&tokens.every(t=>all.includes(t)))score=5;
    return {building:b,score};
  }).filter(x=>Number.isFinite(x.score)).sort((a,b)=>a.score-b.score||a.building.number.localeCompare(b.building.number,'ko',{numeric:true})).map(x=>x.building);
}
function closeBuildingResults(){if(!$('origin-search'))return;$('origin-search-popup').hidden=true;$('origin-search').setAttribute('aria-expanded','false');$('origin-search').removeAttribute('aria-activedescendant');}
function syncOriginSearch(){
  if(!$('origin-search'))return;const b=origin();state.buildingQueryDirty=false;
  $('origin-search').value=b?.official_building_id?b.label:'';$('origin-search-clear').hidden=!$('origin-search').value;
  $('origin-search-status').textContent=b?.official_building_id?b.access.note:`공식 캠퍼스맵 ${state.bootstrap?.building_catalog?.count||''}개 건물 · 번호 또는 이름으로 검색`;
  closeBuildingResults();
}
function setActivePlace(index){
  state.placeActive=index;const options=[...$('origin-search-results').querySelectorAll('[role=option]')];
  options.forEach((n,i)=>n.setAttribute('aria-selected',String(i===index)));
  if(options[index]){$('origin-search').setAttribute('aria-activedescendant',options[index].id);options[index].scrollIntoView?.({block:'nearest'});}
}
function renderBuildingResults(){
  const input=$('origin-search'),query=input.value.trim();$('origin-search-clear').hidden=!query;
  if(!query){closeBuildingResults();return;}
  const matches=searchCampusBuildings(query);state.placeMatches=matches.slice(0,8);state.placeActive=-1;
  $('origin-search-popup').hidden=false;input.setAttribute('aria-expanded','true');input.removeAttribute('aria-activedescendant');
  $('origin-search-count').textContent=matches.length?`${matches.length}개 건물${matches.length>8?' · 상위 8개 · 번호나 이름을 더 입력해 주세요':''}`:'일치하는 교내 건물이 없습니다. 번호나 이름을 다시 확인해 주세요.';
  $('origin-search-results').innerHTML=state.placeMatches.map((b,i)=>`<li role="option" id="origin-place-${i}" data-building-id="${escape(b.id)}" aria-selected="false"><strong>${escape(b.label)}</strong><small>${escape(b.name)}</small></li>`).join('');
  $('origin-search-status').textContent=matches.length?'검색 결과를 선택하면 출발지에 반영합니다.':'검색 결과 없음 · 다른 번호·이름 또는 지도에서 출발지를 선택해 주세요.';
}
function chooseBuilding(id){
  const b=state.bootstrap.origins.find(x=>x.id===id&&x.official_building_id);if(!b)return;
  $('origin').value=b.id;$('origin').dispatchEvent(new Event('change',{bubbles:true}));syncOriginSearch();
}
function bindOriginSearch(){
  const input=$('origin-search');if(!input)return;
  input.addEventListener('input',()=>{state.originRevision++;state.buildingQueryDirty=Boolean(input.value.trim());if(state.buildingQueryDirty)renderBuildingResults();else{closeBuildingResults();$('origin-search-clear').hidden=true;$('origin-search-status').textContent='아래에 선택된 출발지를 사용합니다. 다른 건물은 번호·이름으로 검색하세요.';}});
  input.addEventListener('focus',()=>{if(state.buildingQueryDirty)renderBuildingResults();});
  input.addEventListener('keydown',event=>{
    if(event.isComposing)return;
    if(event.key==='Escape'&&!$('origin-search-popup').hidden){event.preventDefault();event.stopPropagation();closeBuildingResults();return;}
    if(['ArrowDown','ArrowUp'].includes(event.key)){
      event.preventDefault();if($('origin-search-popup').hidden)renderBuildingResults();
      const n=state.placeMatches.length;if(n)setActivePlace(state.placeActive<0?(event.key==='ArrowDown'?0:n-1):(state.placeActive+(event.key==='ArrowDown'?1:-1)+n)%n);return;
    }
    if(event.key==='Enter'&&!$('origin-search-popup').hidden){event.preventDefault();const b=state.placeMatches[Math.max(0,state.placeActive)];if(b)chooseBuilding(b.id);}
  });
  $('origin-search-results').addEventListener('pointerdown',event=>{if(event.target.closest('[data-building-id]'))event.preventDefault();});
  $('origin-search-results').addEventListener('click',event=>{const row=event.target.closest('[data-building-id]');if(row)chooseBuilding(row.dataset.buildingId);});
  $('origin-search-clear').onclick=()=>{input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();};
  document.addEventListener('pointerdown',event=>{if(!$('origin-search-widget').contains(event.target))closeBuildingResults();});
  document.addEventListener('focusin',event=>{if(!$('origin-search-widget').contains(event.target))closeBuildingResults();});
  syncOriginSearch();
}
const isMobile=()=>window.innerWidth<=700;
const icon=name=>`<span class="ms" aria-hidden="true">${name}</span>`;
let formAnchor,monitorAnchor,editorDraft,editorCommitted=false,previousMobile=isMobile();
function syncMobileLabels(){
  if(!$('mobile-origin-label'))return;
  $('mobile-origin-label').textContent=(state.planOrigin||origin())?.label||'현재 위치';
  $('mobile-destination-label').textContent=(state.planDestination||destination())?.label||'목적지';
  $('mobile-departure-label').textContent=state.plan?`${timeLabel(state.plan.departure_at)} 출발`:'지금 출발';
}
function mobileView(view,push=true){
  if(view!=='home'&&!state.plan)view='home';
  const previous=state.mobileView,changed=view!==previous;state.mobileView=view;document.body.dataset.mobileView=view;
  if(push&&changed){try{history.pushState({...history.state,snuMobile:view},'',view==='home'?location.pathname:view==='results'?'#routes':'#route');}catch{}}
  syncMobileLabels();
  for(const b of [$('mobile-home'),$('mobile-directions')]){if(b.id===(view==='home'?'mobile-home':'mobile-directions'))b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
  requestAnimationFrame(()=>{map?.resize?.();if(view==='detail'||!isMobile()&&view==='results'){if(state.selected&&state.planOrigin&&state.planDestination)map?.showRoute(state.selected,state.planOrigin,state.planDestination,false);map?.fit();}else if(view==='home'){map?.clearRoute?.();map?.home?.();}});
  if(changed&&view==='results')$('mobile-back-home').focus({preventScroll:true});
  if(changed)window.RouteMotion?.view(previous,view);
}
function editorSnapshot(){return {origin:$('origin').value,destination:$('destination').value,customOrigin:state.customOrigin,weights:{...state.weights},preset:state.preset,mode:$('departure-mode').value,time:$('departure-time').value,shuttle:$('include-shuttle').checked,journey:state.journey,queueReport:state.queueReport,originSearch:{query:$('origin-search').value,dirty:state.buildingQueryDirty}};}
function openMobileEditor(dest){
  if(!state.bootstrap)return;
  if(!$('mobile-editor').open){editorDraft=editorSnapshot();editorCommitted=false;}
  if(dest)$('destination').value=dest;
  $('mobile-form-slot').append($('route-form'));
  if(!$('mobile-editor').open)$('mobile-editor').showModal();
  if(!isMobile())requestAnimationFrame(()=>$('origin-search').focus({preventScroll:true}));
}
function closeMobileEditor(commit=false){editorCommitted=commit;if($('mobile-editor').open)$('mobile-editor').close();}
function restoreEditorDraft(){
  if(!editorCommitted&&state.planBusy){state.request++;state.planBusy=false;$('search-button').disabled=false;$('search-button').firstElementChild.textContent='경로 비교하기';}
  if(!editorCommitted&&editorDraft){const d=editorDraft;state.originRevision++;state.customOrigin=d.customOrigin;state.weights=d.weights;state.preset=d.preset;$('origin').value=d.origin;$('destination').value=d.destination;$('departure-mode').value=d.mode;$('departure-time').value=d.time;$('include-shuttle').checked=d.shuttle;$('departure-time').hidden=d.mode!=='specified';renderWeights();document.querySelectorAll('[data-preset]').forEach(b=>{b.classList.toggle('active',b.dataset.preset===d.preset);b.setAttribute('aria-pressed',String(b.dataset.preset===d.preset));});}
  if(!editorCommitted&&editorDraft){state.journey=editorDraft.journey;state.queueReport=editorDraft.queueReport;renderMonitor();renderStatus(state.bootstrap.status);if(state.shuttle)map?.showShuttle(shuttleMapData(state.shuttle));}
  if(!editorCommitted&&editorDraft){syncOriginSearch();if(editorDraft.originSearch){$('origin-search').value=editorDraft.originSearch.query;state.buildingQueryDirty=editorDraft.originSearch.dirty;}}
  closeBuildingResults();editorDraft=null;
}
function bindMobile(){
  if(!$('mobile-search'))return;
  formAnchor=document.createComment('desktop route form');$('route-form').before(formAnchor);
  monitorAnchor=document.createComment('desktop waiting comparison');$('adaptive-monitor').before(monitorAnchor);
  if(isMobile())$('mobile-form-slot').append($('route-form'));
  try{history.replaceState({...history.state,snuMobile:'home'},'',location.pathname);}catch{}
  $('mobile-search').onclick=()=>openMobileEditor();$('mobile-directions').onclick=()=>openMobileEditor();
  document.querySelectorAll('[data-destination]').forEach(b=>b.onclick=()=>openMobileEditor(b.dataset.destination));
  $('mobile-editor-close').onclick=()=>closeMobileEditor();$('mobile-editor').addEventListener('close',restoreEditorDraft);
  $('mobile-back-home').onclick=()=>mobileView('home');$('mobile-home').onclick=()=>mobileView('home');
  $('mobile-edit-route').onclick=()=>openMobileEditor();$('mobile-edit-time').onclick=()=>openMobileEditor();
  $('mobile-locate').onclick=()=>requestCurrentLocation();$('mobile-shuttle').onclick=()=>{renderShuttle();$('shuttle-dialog').showModal();};
  $('mobile-detail-back').onclick=()=>mobileView('results');
  $('wide-details').onclick=()=>{if(state.selected){mobileView('detail');renderSelected(state.selected);}};
  document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{state.mobileFilter=b.dataset.filter;state.mobileLimit=12;renderResults();if(!isMobile()){const items=mobileCandidates();if(!items.length)map?.clearRoute?.();else selectRoute((items.find(c=>c.id===state.selected?.id)||items[0]).id,true);}window.RouteMotion?.list();});
  $('mobile-sort').onchange=()=>{state.mobileLimit=12;renderResults();window.RouteMotion?.list();};
  $('selected-panel').addEventListener('transitionend',event=>{if(event.target===$('selected-panel')&&event.propertyName==='height'&&state.mobileView==='detail')map?.fit();});
  window.addEventListener('popstate',event=>{closeMobileEditor();mobileView(event.state?.snuMobile||'home',false);});
  window.addEventListener('resize',()=>{const mobile=isMobile();if(mobile!==previousMobile){previousMobile=mobile;if(!$('mobile-editor').open){if(mobile)$('mobile-form-slot').append($('route-form'));else formAnchor.after($('route-form'));}restoreMonitor();if(state.plan){renderResults();if(state.selected){renderSelected(state.selected);if(!mobile&&state.mobileView!=='home')map?.showRoute(state.selected,state.planOrigin||origin(),state.planDestination||destination(),false);}}mobileView(state.mobileView,false);}map?.resize?.();if(state.selected&&state.mobileView!=='home')map?.fit();});
}
function restoreMonitor(){const box=$('adaptive-monitor');if(box&&monitorAnchor)monitorAnchor.after(box);}
function mobileCandidates(){
  let items=state.plan.candidates.filter(c=>state.mobileFilter==='all'||(state.mobileFilter==='transit'?c.route_names.length:!c.route_names.length));
  const sort=$('mobile-sort').value;
  if(sort==='time'||(sort==='recommended'&&state.preset==='fast'))items.sort((a,b)=>a.total_seconds-b.total_seconds);
  else if(sort==='walk')items.sort((a,b)=>a.walk_m-b.walk_m||a.total_seconds-b.total_seconds);
  else if(sort==='crowd')items.sort((a,b)=>(a.crowd_risk??3)-(b.crowd_risk??3)||a.total_seconds-b.total_seconds);
  return items;
}
function compactArrivalContent(leg){
  return arrivalContent(leg).replace('▰ ',icon('directions_bus')+' ');
}
function mobileCard(c,index){
  const first=c.legs.find(l=>l.type==='bus');
  const crowd=c.legs.filter(l=>l.type==='bus').map(l=>displayCrowd(l.crowd_label)?`${l.route_name} ${displayCrowd(l.crowd_label)}`:'').filter(Boolean).join(' / ');
  return `<article class="route-card mobile-card" data-route="${escape(c.id)}" role="button" tabindex="0" aria-label="${escape(c.route_names.join(' 환승 ')||'도보')} 약 ${minutes(c.total_seconds)}분 경로 보기" aria-pressed="${c.id===state.selected?.id}"><div class="card-badges">${index===0?'<span class="card-badge">'+($('mobile-sort').value==='recommended'?'추천':$('mobile-sort').selectedOptions[0].textContent)+'</span>':''}${!c.route_names.length?'<span class="card-badge">도보 이동</span>':c.transfers?`<span class="card-badge">환승 ${c.transfers}회</span>`:''}</div><div class="card-main"><div class="card-time">${minutes(c.total_seconds)}<small>분</small></div><span class="arrival-time">${timeLabel(c.arrival_at)} 도착 예상<br>${distanceLabel(c.walk_m)} 걷기</span></div>${journeyBar(c)}${mobilePhases(c)}${first?`${crowd?`<p class="mobile-crowd">${escape(crowd)}</p>`:''}`+arrivalBlock(first,true):''}<div class="mobile-card-bottom"><span>${escape(c.route_names.join(' → ')||'목적지까지 걸어서')}</span><span class="route-open">경로 보기 ${icon('chevron_right')}</span></div></article>`;
}
function mobilePhases(c){return `<div class="mobile-phase-summary"><span>도보 <strong>${durationText(c.walk_seconds)}</strong></span><span>대기 <strong>${durationText(c.wait_seconds)}</strong></span><span>차내 <strong>${durationText(c.ride_seconds)}</strong></span></div>`;}
function renderMobileResults(){
  const all=state.plan.candidates,items=mobileCandidates();syncMobileLabels();
  if(!isMobile())$('wide-details').hidden=!items.length||!state.selected;
  for(const b of document.querySelectorAll('[data-filter]')){const n=all.filter(c=>b.dataset.filter==='all'||(b.dataset.filter==='transit'?c.route_names.length:!c.route_names.length)).length;b.querySelector('span').textContent=n;b.setAttribute('aria-pressed',String(b.dataset.filter===state.mobileFilter));}
  $('results').innerHTML=(state.plan.origin_access?`<p class="origin-access-banner">${escape(state.plan.origin_access.note)}</p>`:'')+(items.length?items.slice(0,state.mobileLimit).map(mobileCard).join(''):'<div class="empty-state">이 분류에는 연결 가능한 경로가 없습니다. 다른 이동 수단이나 출발지를 선택해 주세요.</div>')+(items.length>state.mobileLimit?`<button type="button" class="load-more" id="mobile-load-more">경로 더 보기 · ${items.length-state.mobileLimit}개</button>`:'')+'<p class="mobile-list-note">검색 시점의 예상시간입니다. 관측 사이에는 이전 운행·시간표·모형으로 추정합니다. 승차 여유 20초 포함.</p>';
  $('mobile-load-more')?.addEventListener('click',()=>{state.mobileLimit+=12;renderResults();window.RouteMotion?.list();});
  for(const e of $('results').querySelectorAll('[data-route]')){e.onclick=()=>selectRoute(e.dataset.route,true);e.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectRoute(e.dataset.route,true);}};}
}
function renderMobileSelected(c){
  restoreMonitor();const start=state.planOrigin||origin(),dest=state.planDestination||destination();
  const steps=c.legs.filter(l=>['walk','bus'].includes(l.type)&&l.seconds>0);
  $('selected-panel').innerHTML=`<button type="button" class="sheet-grip" id="mobile-expand" aria-label="경로 상세 패널 ${document.body.dataset.sheetExpanded==='true'?'축소':'확대'}" aria-expanded="${document.body.dataset.sheetExpanded==='true'}"></button><div class="mobile-detail-summary"><button type="button" id="mobile-close-detail" class="icon-button" aria-label="경로 목록으로 돌아가기">${icon('close')}</button><div class="detail-total">${minutes(c.total_seconds)}<small>분 예상</small></div><p class="detail-arrival">${timeLabel(state.plan.departure_at)} 출발 → ${timeLabel(c.arrival_at)} 도착 · ${escape(c.route_names.join(' → ')||'도보 이동')}</p>${journeyBar(c)}${mobilePhases(c)}</div><div class="mobile-timeline"><div class="mobile-step"><span class="step-icon">${icon('location_on')}</span><div><h3>${escape(start?.label||'출발지')}</h3><p>출발 · ${timeLabel(state.plan.departure_at)}</p>${state.plan.origin_access?`<p class="origin-access-note">${escape(state.plan.origin_access.note)}</p>`:''}</div></div>${steps.map(l=>`<div class="mobile-step ${l.type}"><span class="step-icon">${icon(l.type==='walk'?'directions_walk':'directions_bus')}</span><div><h3>${l.type==='walk'?`도보 ${distanceLabel(l.meters)} · ${durationText(l.seconds)}`:escape(l.route_name)+' · '+durationText(l.seconds)}</h3>${l.type==='bus'?`<p>${escape(l.from_name)} 승차 → ${escape(l.to_name)} 하차${Number.isFinite(l.to_seq-l.from_seq)?' · '+(l.to_seq-l.from_seq)+'개 정류장':''}</p>${arrivalBlock(l,true)}`:`<p>${escape(l.label||'보행 경로')}${l.steps_m?' · 계단 '+l.steps_m+'m 포함':''}</p>`}</div></div>`).join('')}<div class="mobile-step"><span class="step-icon">${icon('location_on')}</span><div><h3>${escape(dest.label)}</h3><p class="mobile-destination-detail">${escape(dest.detail||'대표 도착 지점 기준')}</p><p>${timeLabel(c.arrival_at)} 도착 예상</p></div></div></div><div class="detail-actions"><button type="button" id="record-button">실제 이동 기록</button><button type="button" id="mobile-detail-sources">데이터 안내</button></div>`;
  $('selected-panel').hidden=false;
  $('selected-panel').append($('adaptive-monitor'));renderMonitor();
  $('mobile-close-detail').onclick=()=>mobileView('results');$('mobile-expand').onclick=()=>{document.body.dataset.sheetExpanded=String(document.body.dataset.sheetExpanded!=='true');renderMobileSelected(c);map?.fit();};
  $('record-button').onclick=()=>$('observation-dialog').showModal();$('mobile-detail-sources').onclick=showSources;
}

function toast(message) { $('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6500); }
async function api(path,body) {
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();if(Number.isFinite(data.server_time))state.clockOffset=data.server_time-Date.now()/1000;
  if(!response.ok)throw new Error(data.error||'요청에 실패했습니다.');return data;
}
function origin() { return state.customOrigin||state.bootstrap.origins.find(x=>x.id===$('origin').value); }
function destination() { return state.bootstrap.destinations.find(x=>x.id===$('destination').value); }
function renderWeights() {
  const labels={time:'시간',crowd:'혼잡',walk:'도보',transfers:'환승'};
  $('weight-controls').innerHTML=Object.entries(labels).map(([key,label])=>`<label class="weight-row">${label}<input type="range" min="0" max="100" value="${state.weights[key]}" data-weight="${key}" aria-label="${label} 가중치"><output id="weight-${key}">${state.weights[key]}</output></label>`).join('');
  for(const input of $('weight-controls').querySelectorAll('input'))input.addEventListener('input',()=>{
    state.weights[input.dataset.weight]=Number(input.value);$('weight-'+input.dataset.weight).textContent=input.value;state.preset='custom';
    document.querySelectorAll('[data-preset]').forEach(b=>{b.classList.remove('active');b.setAttribute('aria-pressed','false');});
  });
}
function setPreset(name) {
  state.preset=name;state.weights={...state.bootstrap.presets[name]};renderWeights();
  document.querySelectorAll('[data-preset]').forEach(button=>{const active=button.dataset.preset===name;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
  if(state.plan&&!isMobile()&&!$('mobile-editor').open)search();
}
function renderStatus(status) {
  const specified=$('departure-mode').value==='specified';
  state.bootstrap.status=status;map?.showVehicles(specified?[]:status.vehicles||[]);
  const notice=$('service-notice');notice.hidden=!status.storage?.message;notice.textContent=status.storage?.message?'일부 기능이 일시 중단되었습니다.':'';
  const submit=$('observation-form').querySelector('button[type="submit"]');
  submit.disabled=status.storage?.observations_available===false;
  submit.textContent=submit.disabled?'기록 저장 일시 중단':'이동 결과 기록하기 →';
  const age=status.captured_at?Date.now()/1000-status.captured_at:Infinity;
  $('live-dot').classList.toggle('warning',age>150||status.errors?.length>0);
  $('live-label').textContent=specified?'시간 지정':status.position_updates_paused?'버스 안내':status.captured_at?'버스 위치':'버스 안내';
}
function shuttleMapData(data){return $('departure-mode').value==='specified'?{...data,vehicles:[],routes:(data.routes||[]).map(r=>({...r,vehicles:[]}))}:data;}
async function refresh(quiet=false) {
  const button=$('refresh-button');button.disabled=true;
  try { const status=await api('/api/status');renderStatus(status);if(!quiet)toast(status.errors?.length?status.errors.join(' '):status.captured_at?`공용 수집 결과 · 최근 수신 ${timeLabel(status.captured_at)}`:'예약 수집 결과를 기다리고 있습니다.'); }
  catch(error){if(!quiet)toast(error.message);}
  finally{button.disabled=false;}
}
async function refreshShuttle() {
  try {
    const data=await api('/api/shuttle');state.shuttle=data;map?.showShuttle(shuttleMapData(data));
    $('shuttle-label').textContent=data.routes?.map(r=>`${shuttleShort(r)} ${r.error?'지연':r.stale?'대기':r.vehicles.length}`).join(' · ')||(data.error?'셔틀 연결 지연':`셔틀 위치 ${data.vehicles.length}건`);
    if(data.routes?.length>5)$('shuttle-label').textContent=`셔틀 ${data.routes.length}노선 · ${data.vehicles?.length||0}대 관측`;
    if(!data.vehicles?.length&&data.timetable)$('shuttle-label').textContent=data.timetable.operating_day?'관측 간격 · 시간표·이전 운행·모형으로 비교':'시간표상 미운행일 · 셔틀 안내';
    if($('departure-mode').value==='specified')$('shuttle-label').textContent='선택 날짜 · 셔틀 시간표·모형 비교';
    $('shuttle-label').textContent='셔틀 안내';
    if($('shuttle-dialog').open)renderShuttle();
  }catch{
    $('shuttle-label').textContent='셔틀 연결 지연';
    if(state.shuttle){state.shuttle={...state.shuttle,error:'실시간 조회 연결이 지연돼 이전 관측을 표시합니다.',routes:(state.shuttle.routes||[]).map(r=>({...r,error:'조회 연결 지연 · 이전 관측'}))};map?.showShuttle(shuttleMapData(state.shuttle));if($('shuttle-dialog').open)renderShuttle();}
  }
}
function renderShuttle() {
  const overall=state.shuttle||state.bootstrap.shuttle;
  const routes=overall.routes||[{...overall,id:'41841',name:'행정관 셔틀',color:'#bb7e2e'}];
  const data=routes.find(r=>r.id===state.shuttleRouteId)||routes[0];
  const prediction=overall.model_predictions?.find(p=>p.route_id==='shuttle-'+data.id);
  const anchors=data.schematic_anchors||[];
  const lines=anchors.map(a=>`${a.x},${a.y}`).join(' ');
  $('shuttle-content').innerHTML=`<label class="shuttle-route-label" for="shuttle-route">노선 선택</label><select id="shuttle-route" class="shuttle-route-select">${routes.map(r=>`<option value="${escape(r.id)}" ${r.id===data.id?'selected':''}>${escape(r.name)}</option>`).join('')}</select>
    <p class="dialog-caption">${escape(data.direction_label||'서울대입구역 ↔ 행정관')}</p>
    ${prediction?`<div class="comparison-note"><strong>${escape(prediction.boarding_stop)}</strong>${prediction.expected_boarding_at?`<p data-shuttle-boarding-at="${prediction.expected_boarding_at}">약 ${durationText(Math.max(0,prediction.expected_boarding_at-nowSeconds()))} 후 예상 승차</p>${prediction.next_scheduled_departure_at?`<p>시간표 다음 출발 ${timeLabel(prediction.next_scheduled_departure_at)}</p>`:''}${prediction.automatic_queue?automaticQueueText(prediction.automatic_queue,true):''}`:`<p>${escape(prediction.reason)}</p>`}</div>`:''}
    ${overall.timetable?`<p><a href="${escape(overall.timetable.source_url)}" target="_blank" rel="noopener">공식 셔틀 시간표 ↗</a></p>`:''}
    ${data.error?'<p class="comparison-note">차량 위치 연결 지연</p>':''}
    ${!data.vehicles.length?'<p class="comparison-note">현재 표시할 차량이 없습니다.</p>':''}
    <svg class="shuttle-schematic" viewBox="-90 -5 500 450" role="img" aria-label="셔틀 실제 수신 노선도 위치"><polyline points="${lines} ${anchors.length?`${anchors[0].x},${anchors[0].y}`:''}" fill="none" stroke="${escape(data.color||'#bb7e2e')}" stroke-opacity=".2" stroke-width="8" stroke-linejoin="round"/>
    ${anchors.map((a,i)=>`<circle cx="${a.x}" cy="${a.y}" r="5" fill="#fff" stroke="#7f987c" stroke-width="2"/><text x="${a.x+(a.x<150?-12:a.x>180?12:0)}" y="${a.y+(a.x>=150&&a.x<=180?(i===0?-14:24):4)}" text-anchor="${a.x<150?'end':a.x>180?'start':'middle'}" fill="#587253" font-size="11">${escape(a.name)}</text>`).join('')}
    ${(data.vehicles||[]).map(v=>`<circle class="shuttle-observation" cx="${v.x}" cy="${v.y}" r="5.5" fill="${data.stale||data.error?'#929b93':escape(data.color||'#bb7e2e')}" stroke="#fff" stroke-width="1.5"><title>차량 ${escape(v.id)} · ${escape(v.position?`${v.position.from_name}→${v.position.to_name}`:'구간 미해석')}</title></circle>`).join('')}</svg>
    <div class="shuttle-records">${(data.vehicles||[]).slice(0,8).map(v=>`<div class="source-row"><strong>차량 ${escape(v.id)}</strong><span>${escape(v.position?`${v.position.from_name} → ${v.position.to_name}`:'노선도상 구간 미해석')}${v.moved_since_previous?' · 위치 변화 관측':''}</span></div>`).join('')}</div>
    <p><a href="${escape(data.source_url)}" target="_blank" rel="noopener">선택 노선 실시간 원문 ↗</a></p>`;
  $('shuttle-route').addEventListener('change',event=>{state.shuttleRouteId=event.target.value;renderShuttle();window.RouteMotion?.list('shuttle-content');});
}
function departure() {
  if($('departure-mode').value==='now')return Date.now()/1000;
  const date=new Date($('departure-time').value);if(!Number.isFinite(date.getTime()))throw new Error('출발 시각을 선택해 주세요.');return date.getTime()/1000;
}
async function search(event,options={}) {
  event?.preventDefault();
  if(!state.bootstrap)return;
  if(state.buildingQueryDirty){toast('건물 검색 결과에서 출발지를 선택해 주세요.');openMobileEditor();$('origin-search').focus();renderBuildingResults();return;}
  if(!origin()||!destination()){toast(!origin()?'현재 위치를 확인하거나 출발지를 직접 선택해 주세요.':'목적지를 선택해 주세요.');openMobileEditor();return;}
  if(Object.values(state.weights).reduce((a,b)=>a+b,0)===0){toast('한 가지 이상의 가중치를 높여 주세요.');return;}
  const id=++state.request;state.planBusy=true;const button=$('search-button');button.disabled=true;button.firstElementChild.textContent='이용 가능한 경로 확인 중';
  $('results-caption').textContent='보행시간 뒤에 탈 수 있는 차량을 찾고 있습니다.';
  try {
    const start={...origin()},target={...destination()};
    const data=await api('/api/plan',{
      ...(state.customOrigin?{origin:{lat:start.lat,lon:start.lon}}:{origin_id:start.id}),
      destination_id:$('destination').value,departure_at:departure(),weights:state.weights,
      preset:state.preset,mode:$('departure-mode').value==='now'?'live':'estimate',include_shuttle:$('include-shuttle').checked,
      ...(state.journey&&$('departure-mode').value==='now'?{decision_context:{current_key:state.journey.currentKey,switch_count:state.journey.switchCount,
        last_switch_at:state.journey.lastSwitchAt,abandoned_keys:state.journey.abandoned,waiting_since:state.journey.waiting?state.journey.waitingSince:null},
        queue_context:state.queueReport&&nowSeconds()-state.queueReport.reported_at<=90&&state.queueReport.opportunity_departure_at>nowSeconds()?state.queueReport:null}:{}),
    });
    if(id!==state.request)return;
    state.arrivalPreviews.clear();state.arrivalLegs.clear();state.nextLegKey=1;state.plan=data;state.planOrigin=start;state.planDestination=target;state.mobileLimit=12;
    if(state.journey)state.journey.lastCheckAt=nowSeconds();
    state.selected=(state.journey&&data.adaptive_decision?data.candidates.find(c=>c.id===data.adaptive_decision.current_candidate_id):null)||
      (state.preset==='fast'&&data.strategy_comparison?data.candidates.find(c=>c.id===data.strategy_comparison.recommended_candidate_id):null)||data.candidates[0]||null;renderResults();
    if(!options.monitor){closeMobileEditor(true);mobileView('results');$('results').closest('.sidebar').scrollTop=0;}
    if(state.selected){if(!isMobile()||options.monitor)selectRoute(state.selected.id,!options.monitor);}
    else {$('selected-panel').hidden=true;$('wide-details').hidden=true;map?.clearRoute?.();toast(data.access_message||'현재 조건에서 연결 가능한 대안을 찾지 못했습니다. 다른 출발점도 확인해 주세요.');}
  } catch(error) {
    if(id!==state.request)return;
    $('results').innerHTML=`<div class="empty-state">${escape(error.message)}</div>`;$('results-caption').textContent='출발지와 데이터 연결 상태를 확인해 주세요.';toast(error.message);
  } finally { if(id===state.request){state.planBusy=false;button.disabled=false;button.firstElementChild.textContent='경로 비교하기';} }
}
function pills(candidate) {
  if(!candidate.route_names.length)return '<span class="route-pill walk">⌁ 도보 이동</span>';
  return ['<span class="route-pill walk">도보</span>',...candidate.route_names.map(n=>`<span class="route-pill ${n.includes('셔틀')?'shuttle':n.startsWith('관악')?'village':''}">${escape(n)}</span>`),'<span class="route-pill walk">도보</span>'].join('<span class="route-arrow">›</span>');
}
function historicalLine(forecast,detail=false) {
  if(!forecast)return '';
  if(!forecast.available)return `<p class="forecast-unavailable">요일별 예측 · ${escape(forecast.reason||'제공 자료가 없습니다.')}</p>`;
  const value=new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(forecast.mean_sum_load);
  const coverage=forecast.partial?` · ${forecast.matched_segments}/${forecast.total_segments}구간`:'';
  const shuttle=forecast.shuttle_legs_without_history?' · 셔틀 제외':'';
  return `<div class="historical-forecast${detail?' detail':''}"><span>요일별 과거 이용량</span><strong>${value}</strong><small>시간당 구간 재차합 평균${coverage}${shuttle}</small></div>`;
}
function waitEvidence(leg){
  if(leg.automatic_queue)return '<br>'+automaticQueueText(leg.automatic_queue,true);
  const q=leg.arrival_options?.find(a=>a.queue_model)?.queue_model;
  return q?`<br>조건부 대기모형 · 실측 아님<br>해당 도착시간대 모형 평균 ${durationText(q.reference_mean_seconds)} · 모형 P90 ${durationText(q.reference_p90_seconds)}<br>정원 부족 추가 대기 ${durationText(q.capacity_extra_seconds)}${q.extra_applied===false?' · 막차 조건으로 미적용':''}`:'';
}
function card(candidate,index) {
  const badges=(candidate.badges||[]).filter(x=>x!==state.preset).slice(0,2);
  return `<article class="route-card ${candidate.id===state.selected?.id?'selected':''}" data-route="${candidate.id}" role="button" tabindex="0" aria-label="${escape(candidate.route_names.join(' 환승 ')||'도보')} 약 ${minutes(candidate.total_seconds)}분 경로 선택" aria-pressed="${candidate.id===state.selected?.id}">
    <div class="card-top"><div class="card-badges">${index===0&&candidate.score!=null?`<span class="card-badge recommended">${state.preset==='fast'&&state.plan?.strategy_comparison?'예상 최단시간':'추천'}</span>`:''}${badges.map(x=>`<span class="card-badge">${modeLabels[x]}</span>`).join('')}</div><span class="card-radio"></span></div>
    <div class="card-main"><div class="card-time"><span class="approx">약</span>${minutes(candidate.total_seconds)}<small>분</small></div><span class="arrival-time">${timeLabel(candidate.arrival_at)} 도착 예상</span></div>
    <div class="route-pills">${pills(candidate)}</div>
    ${journeyBar(candidate)}
    <div class="phase-summary"><span>도보 <strong>${durationText(candidate.walk_seconds)}</strong></span><span>버스 <strong>${durationText(candidate.ride_seconds)}</strong></span><span>대기 <strong>${durationText(candidate.wait_seconds)}</strong></span></div>
    ${candidate.legs.filter(l=>l.type==='bus').map(arrivalBlock).join('')}
    <div class="card-metrics"><span>도보 <strong>${distanceLabel(candidate.walk_m)}</strong></span><span>환승 <strong>${candidate.transfers}회</strong></span>${displayCrowd(candidate.crowd_label)?`<span>혼잡 <strong>${escape(displayCrowd(candidate.crowd_label))}</strong></span>`:''}</div>
    ${candidate.route_names.length?historicalLine(candidate.historical_forecast):''}
    <span class="evidence-label ${['live','live_shuttle','mixed_live'].includes(candidate.evidence)?'live':''}">${candidate.evidence==='live'?'● 도착예정 기반 · 주행 일부 추정':candidate.evidence==='walking'?'보행망·보행속도 기반 예상':candidate.evidence==='live_shuttle'?'● 실시간 셔틀 위치 · 도착시간 추정':candidate.evidence==='mixed_live'?'● 실시간 셔틀 연결 · 버스·보행 추정 포함':'운행간격 시나리오 · 실제 출발 확인 전'}</span>
  </article>`;
}
function journeyBar(c){
  const phases=[];
  for(const l of c.legs){if(!l.seconds)continue;const type=l.type==='board'?'wait':l.type;
    if(type==='wait'&&phases.at(-1)?.type==='wait')phases.at(-1).seconds+=l.seconds;
    else phases.push({type,seconds:l.seconds});}
  return `<div class="journey-bar" aria-label="도보·대기·버스 시간 구성">${phases.map(p=>`<span class="journey-segment ${p.type}" style="flex:${p.seconds}" title="${{walk:'도보',wait:'대기·승차 여유',bus:'버스'}[p.type]} ${durationText(p.seconds)}"><span>${p.seconds>=60?`${Math.round(p.seconds/60)}분`:''}</span></span>`).join('')}</div>`;
}
function arrivalBlock(leg,compact=false){
  if(!leg.uiArrivalKey)leg.uiArrivalKey=String(state.nextLegKey++);
  state.arrivalLegs.set(leg.uiArrivalKey,leg);
  return `<div class="boarding-arrivals" data-arrival-list="${escape(leg.route_id+':'+leg.from_seq)}" data-leg-display-key="${leg.uiArrivalKey}" data-compact="${compact}">${compact?compactArrivalContent(leg):arrivalContent(leg)}</div>`;
}
function forecastFor(leg,entry){
  if(leg.arrival_source==='pooled_headway_estimate')entry=null;
  const value=entry?.arrival_forecast||leg.arrival_forecast;
  if(value){
    const f={...value},ready=Math.max(nowSeconds(),Number(leg.ready_at)||f.ready_at||0);
    if(f.last_service_at&&ready>f.last_service_at)return {...f,unreachable_after_walk:true};
    if(f.base_departure_at<ready){
      const next=f.future_departures_at?.find(t=>t>=ready);
      const leave=next??(f.rolling&&f.headway_seconds>0?f.base_departure_at+Math.ceil((ready-f.base_departure_at)/f.headway_seconds)*f.headway_seconds:null);
      if(leave!=null){const old=f.base_departure_at-f.ready_at,range=f.range_seconds||[0,f.headway_seconds];f.range_seconds=[Math.max(0,leave-ready-Math.max(0,old-range[0])),leave-ready+Math.max(0,range[1]-old)];f.base_departure_at=leave;f.ready_at=ready;}
      else return {...f,unreachable_after_walk:true};
    }
    return f;
  }
  const route=state.bootstrap?.routes?.find(r=>r.id===leg.route_id),headway=Number(route?.interval_minutes)*60;
  if(!(headway>0))return null;
  const at=state.plan?.departure_at||nowSeconds(),base=Number(leg.departure_at)||at+headway/2;
  return {base_departure_at:base,ready_at:Number(leg.ready_at)||at,headway_seconds:headway,
    range_seconds:[0,headway],source:'registered_headway',rolling:true};
}
function forecastText(f,at=nowSeconds()){
  if(!f)return '시간표·모형 예상 운행 · 경로 비교에서 다음 기회 확인';
  if(f.unreachable_after_walk)return '도보 도착 후 시간표상 이용 곤란 · 다시 비교';
  let leave=f.base_departure_at;const h=Number(f.headway_seconds)||0;
  if(f.last_service_at&&at>f.last_service_at)return '등록 시간표상 운행시간 지남 · 도보 대안 비교';
  if(leave<at){
    const fixed=f.future_departures_at?.find(t=>t>=at);
    if(fixed!=null)leave=fixed;
    else if(f.rolling&&h>0)leave+=Math.ceil((at-leave)/h)*h;
    else return '시간표상 다음 운행 없음 · 도보 대안 비교';
  }
  if(f.last_service_at&&leave>f.last_service_at)return '등록 시간표상 다음 운행 없음 · 도보 대안 비교';
  const original=Math.max(0,f.base_departure_at-(f.ready_at??f.base_departure_at));
  const spread=f.range_seconds||[0,h],low=Math.max(0,leave-at-Math.max(0,original-spread[0]));
  const high=Math.max(low,leave-at+Math.max(0,spread[1]-original));
  if(['timetable_simulation_only','shuttle_schedule_model'].includes(f.time_basis))return `약 ${durationText(Math.max(0,leave-at))} 후 예상 승차`;
  return `약 ${Math.floor(low/60)}~${Math.max(1,Math.ceil(high/60))}분 · 예상 승차기회`;
}
function forecastRow(leg,entry){
  if(entry?.unavailable_reason)return '<p class="arrival-status">이 시각에는 탑승이 어렵습니다.</p>';
  const f=forecastFor(leg,entry);if(!f)return '';
  const live=Boolean(state.plan?.live_predictions_used),at=live?nowSeconds():state.plan?.departure_at||nowSeconds();
  return `<div class="arrival-row"><span>${escape(leg.route_name||'다음 운행')}</span><strong ${live?`data-service-forecast="${escape(JSON.stringify(f))}"`:''}>${escape(forecastText(f,at))}</strong>${f.next_scheduled_departure_at?`<small>시간표 다음 ${timeLabel(f.next_scheduled_departure_at)}</small>`:''}</div>`;
}
function arrivalContent(leg){
  const entry=state.plan?.live_predictions_used?state.arrivalPreviews.get(leg.route_id+':'+leg.from_seq):null,values=entry?.values||leg.arrival_options||[];
  const title=`<div class="boarding-name">▰ ${escape(leg.from_name)}${leg.station_ars?` <small>${escape(leg.station_ars)}</small>`:''}</div>`;
  if(leg.automatic_queue){
    const matches=entry?.ready_at&&Math.abs(entry.ready_at-Math.max(nowSeconds(),leg.ready_at))<45;
    const q=(matches&&entry?.values?.find(v=>v.automatic_queue)?.automatic_queue)||leg.automatic_queue;
    return title+(forecastRow(leg,matches?entry:null)||`<p class="arrival-status">예상 대기 ${durationText(q.expected_wait_seconds)}</p>`)+(q.cohort_available!==false&&q.queue_at_arrival!=null?`<p class="automatic-queue-evidence">예상 줄 약 ${Math.ceil(q.queue_at_arrival)}명</p>`:'');
  }
  if(leg.arrival_source==='pooled_headway_estimate')return title+forecastRow(leg,entry);
  if(leg.queue_projection){const q=leg.queue_projection;return title+`<p class="arrival-status">내 앞 ${escape(q.queue_ahead)}명 · ${q.skipped_departures}대 이후 승차 예상</p>`;}
  if(!state.plan?.live_predictions_used&&!values.some(a=>a.arrival_source==='shuttle_timetable_estimate'))return title+forecastRow(leg,entry);
  const rows=values.map(a=>{
    const source=a.arrival_source||'live';
    if(source==='shuttle_timetable_estimate')return `<div class="arrival-row"><span>${escape(leg.route_name)}</span><strong>${a.fixed_departure?'시간표 '+timeLabel(a.departure_at)+' 출발':'예상 대기 '+durationText(a.wait_seconds??Math.max(0,a.departure_at-leg.ready_at))}</strong>${a.next_scheduled_departure_at?`<small>시간표 다음 ${timeLabel(a.next_scheduled_departure_at)}</small>`:''}</div>`;
    if(!Number.isFinite(a.departure_at)||!Number.isFinite(a.provided_at))return '';
    const window=source==='live_shuttle'&&a.eta_window_seconds;
    const data=window?`data-low-at="${a.provided_at+window[0]}" data-high-at="${a.provided_at+window[1]}"`:'';
    const passed=a.departure_at<leg.ready_at,fallback=forecastFor(leg,entry);
    const crowd=displayCrowd(a.full?'만차':entry?.crowd_prediction?.crowd_label||leg.crowd_label||a.crowd_label);
    return `<div class="arrival-row${a.vehicle_id===leg.vehicle_id?' chosen':''}"><span>${escape(leg.route_name)}</span><strong class="arrival-countdown" data-arrival-at="${a.departure_at}" data-observed-at="${a.provided_at}" data-arrival-kind="${source==='live_shuttle'?'shuttle':'bus'}" ${fallback?`data-fallback-forecast="${escape(JSON.stringify(fallback))}"`:''} ${data}>도착정보 확인 중</strong>${crowd||passed?`<small>${escape(crowd)}${passed?' · 도보 도착 전 통과 예상':''}</small>`:''}</div>`;
  }).join('');
  return title+(rows||forecastRow(leg,entry));
}
function updateCountdowns(){
  const now=nowSeconds();
  let aged=false;
  if(state.plan?.live_predictions_used)for(const c of state.plan.candidates)for(const l of c.legs){
    if(l.type==='bus'&&l.crowd_source==='observed'&&l.observed_at&&now-l.observed_at>90){
      if(l.crowd_after_expiry)Object.assign(l,l.crowd_after_expiry);
      else {l.crowd_estimate=l.crowd_cost;l.crowd_cost=null;l.crowd_source='last_observation_estimate';l.crowd_risk=Math.min(3,(l.crowd_estimate??1.5)+1);l.crowd_label=l.crowd_label.replace(/ 추정$/,'')+' 추정';}
      l.age_seconds=Math.round(now-l.observed_at);aged=true;
    }
  }
  if(aged){syncCrowdSummaries();renderResults();if(state.selected)renderSelected(state.selected);}
  for(const node of document.querySelectorAll('[data-arrival-at]')){
    const remaining=Number(node.dataset.arrivalAt)-now,age=now-Number(node.dataset.observedAt),shuttle=node.dataset.arrivalKind==='shuttle';
    if(age>(shuttle?60:150)||age< -5||remaining<=0){node.textContent=forecastText(node.dataset.fallbackForecast?JSON.parse(node.dataset.fallbackForecast):null,now);const evidence=node.parentElement?.querySelector('small');if(evidence)evidence.textContent='';continue;}
    if(shuttle){const lo=Math.max(0,Math.floor((Number(node.dataset.lowAt)-now)/60)),hi=Math.max(0,Math.ceil((Number(node.dataset.highAt)-now)/60));node.textContent=Number(node.dataset.highAt)<=now?forecastText(node.dataset.fallbackForecast?JSON.parse(node.dataset.fallbackForecast):null,now):`약 ${lo}~${hi}분 후 도착 예상`;}
    else node.textContent=`${Math.floor(Math.ceil(remaining)/60)}분 ${String(Math.ceil(remaining)%60).padStart(2,'0')}초`;
  }
  for(const node of document.querySelectorAll('[data-service-forecast]'))node.textContent=forecastText(JSON.parse(node.dataset.serviceForecast),now);
  for(const node of document.querySelectorAll('[data-shuttle-boarding-at]'))node.textContent=Number(node.dataset.shuttleBoardingAt)>now?`약 ${durationText(Number(node.dataset.shuttleBoardingAt)-now)} 후 예상 승차`:'예상 시각 경과 · 시간표·모형 다시 확인 중';
}
function syncCrowdSummaries(){
  if(!state.plan)return;
  for(const c of state.plan.candidates){const rides=c.legs.filter(l=>l.type==='bus');if(!rides.length)continue;
    c.crowd_cost=rides.every(l=>l.crowd_cost!=null)?Math.max(...rides.map(l=>l.crowd_cost)):null;
    c.crowd_risk=Math.max(...rides.map(l=>l.crowd_risk??3));
    c.crowd_label=c.crowd_cost==null?'혼잡도 모형 추정':({0:'여유',1:'보통',2:'혼잡',3:'매우혼잡'}[Math.round(c.crowd_cost)]||'혼잡도 추정');
  }
  const compare=state.plan.strategy_comparison;
  for(const s of [...Object.values(compare?.strategies||{}),...(compare?.shuttle_options||[])]){
    const c=s&&state.plan.candidates.find(c=>c.id===s.id);if(c)Object.assign(s,{crowd_cost:c.crowd_cost,crowd_risk:c.crowd_risk,crowd_label:c.crowd_label});
  }
}
async function refreshSelectedArrivals(){
  if(state.previewBusy||!state.plan?.live_predictions_used||!state.selected||document.visibilityState==='hidden')return;
  const legs=state.selected.legs.filter(l=>l.type==='bus'&&!['shuttle_queue_estimate','pooled_headway_estimate'].includes(l.arrival_source));if(!legs.length)return;
  if(legs.every(l=>Date.now()-(state.arrivalPreviews.get(l.route_id+':'+l.from_seq)?.fetched||0)<60000))return;
  state.previewBusy=true;
  try{
    const data=await api('/api/arrivals',{targets:legs.map(l=>({route_id:l.route_id,seq:l.from_seq,ready_at:Math.max(nowSeconds()+20,l.ready_at||0),forecast_only:l.mode==='shuttle'&&l.arrival_source!=='live_shuttle'}))});
    for(const r of data.stops){const key=r.route_id+':'+r.seq,old=state.arrivalPreviews.get(key);state.arrivalPreviews.set(key,{...r,values:r.values?.length?r.values:r.error&&old?old.values:r.values,fetched:Date.now()});}
    for(const r of data.stops){const leg=legs.find(l=>l.route_id===r.route_id&&l.from_seq===r.seq);if(leg&&r.crowd_prediction)Object.assign(leg,r.crowd_prediction);}
    for(const node of document.querySelectorAll('[data-arrival-list]')){const leg=state.arrivalLegs.get(node.dataset.legDisplayKey);if(leg)node.innerHTML=node.dataset.compact==='true'?compactArrivalContent(leg):arrivalContent(leg);}
    if(data.stops.some(r=>r.crowd_prediction)){const sidebar=document.querySelector('.sidebar'),top=sidebar?.scrollTop;syncCrowdSummaries();renderResults();if(sidebar)sidebar.scrollTop=top;}
    if(state.selected)renderSelected(state.selected);
    updateCountdowns();
  }catch{}finally{state.previewBusy=false;}
}
function renderStrategies(){
  const data=state.plan.strategy_comparison,container=$('strategy-comparison');
  container.hidden=!data;if(!data)return;
  const names={shuttle_wait:'셔틀 기다리기',walk_to_gate:'정문까지 걷고 첫 버스',walk_only:'목적지까지 도보',other_city:'다른 시내버스'};
  const best=state.plan.candidates.find(c=>c.id===data.recommended_candidate_id);
  const comparison=data.difference_seconds==null?'이용 가능한 경로를 비교해 보세요.':data.difference_seconds<1?'두 방법의 예상 시간이 같습니다.':`${names[data.faster_strategy]}가 약 ${durationText(data.difference_seconds)} 빠릅니다.`;
  const cards=Object.entries(names).map(([key,title])=>{
    const c=data.strategies[key];
    if(!c)return `<div class="strategy-card unavailable"><strong>${title}</strong><p>이용 가능한 경로 없음</p></div>`;
    const crowd=c.boarding.map(b=>displayCrowd(b.crowd_label)).filter(Boolean).join(' / ');
    return `<button type="button" class="strategy-card${c.id===state.selected?.id?' selected':''}" data-strategy-route="${escape(c.id)}" aria-pressed="${c.id===state.selected?.id}"><span class="strategy-name">${title}</span><span class="strategy-time">약 ${minutes(c.total_seconds)}<small>분</small></span><span class="strategy-phases">도보 ${durationText(c.walk_seconds)}<br>대기 ${durationText(c.wait_seconds)} · 차내 ${durationText(c.ride_seconds)}</span>${crowd?`<span class="strategy-crowd">${escape(crowd)}</span>`:''}</button>`;
  }).join('');
  container.innerHTML=`<div class="strategy-heading"><h3>경로 비교</h3><button type="button" id="recompare-strategies">다시 비교 ↻</button></div><p class="strategy-verdict">${escape(comparison)}</p><div class="strategy-grid">${cards}</div>${best?`<p class="strategy-best">추천 · ${escape(best.route_names.join(' → ')||'도보')} · 약 ${minutes(best.total_seconds)}분</p>`:''}`;
  if(data.shuttle_options?.length){
    const detail=document.createElement('details');detail.className='strategy-shuttle-options';
    detail.innerHTML='<summary>셔틀 경로 더 보기</summary>'+data.shuttle_options.map(c=>`<button type="button" data-strategy-route="${escape(c.id)}"><strong>${escape(c.route_names.join(' → '))} · 약 ${minutes(c.total_seconds)}분</strong><span>${escape(c.boarding[0].from_name)} 승차</span></button>`).join('');container.append(detail);
  }
  for(const button of container.querySelectorAll('[data-strategy-route]'))button.addEventListener('click',()=>selectRoute(button.dataset.strategyRoute,true));
  $('recompare-strategies').addEventListener('click',()=>search());
}
function adaptiveReferenceText(){
  const ref=state.bootstrap.adaptive_reference;if(!ref)return '';
  const all=ref.summaries.find(r=>r.scenario==='peak'&&r.origin==='all'&&r.scope==='snu_all');
  return `<p>경로 변경 시뮬레이션 참고${all?`: 하루 누적 대기 ${all.wait_before.toFixed(2)}→${all.wait_after.toFixed(2)}분, 양쪽 완주 집단 총시간 ${all.total_before.toFixed(2)}→${all.total_after.toFixed(2)}분`:''}. 수업 종료 코호트의 가중 모형 결과이며 현재 줄 인원·실측 절감시간이 아닙니다. 이 평균을 ETA에서 차감하지 않습니다.</p>`;
}
function automaticQueueText(q,detail=false){
  const wait=`예상 대기 ${durationText(q.expected_wait_seconds)}`;
  return q.cohort_available===false||q.queue_at_arrival==null?wait:`예상 줄 약 ${Math.ceil(q.queue_at_arrival)}명 · ${wait}`;
}
function continuationKey(c){const b=c?.legs.find(l=>l.type==='bus');return c?.continuation_key||(c?.common_gate_service?'gate-first:120000029':b?b.route_id+':'+b.station_id:'walk-only');}
function endJourney(){state.journey=null;state.queueReport=null;renderMonitor();}
function startWaiting(){
  const j=state.journey;
  const c=j?state.plan.candidates.find(c=>continuationKey(c)===j.currentKey):state.selected;
  const b=c?.legs.find(l=>l.type==='bus');if(!b||!state.plan.live_predictions_used)return;
  const route=state.bootstrap.routes.find(r=>r.id===b.route_id),stop=route?.stops.find(s=>s.seq===b.from_seq);
  if(!stop)return;
  state.journey=j||{startedAt:nowSeconds(),currentKey:continuationKey(c),switchCount:0,lastSwitchAt:null,abandoned:[]};
  Object.assign(state.journey,{waiting:true,waitingSince:nowSeconds(),monitoring:true,anchor:{lat:stop.lat,lon:stop.lon,name:b.from_name,route_id:b.route_id,station_id:stop.id},lastCheckAt:0});
  state.originRevision++;state.customOrigin={lat:stop.lat,lon:stop.lon,label:b.from_name+' · 대기 정류장'};
  let option=$('origin').querySelector('[value="custom"]');if(!option){option=new Option('','custom');$('origin').add(option);}
  option.textContent=state.customOrigin.label;$('origin').value='custom';state.queueReport=null;
  $('location-status').textContent='도착했다고 선택한 정류장 기준입니다. 이동하면 현재 위치를 다시 확인해 주세요.';
  search(null,{monitor:true});
}
function acceptSuggestedSwitch(){
  const j=state.journey,d=state.plan.adaptive_decision;
  if(!j||d?.action!=='suggest_switch')return;
  const next=state.plan.candidates.find(c=>c.id===d.recommended_candidate_id);if(!next)return;
  if(j.currentKey!=='walk-only')j.abandoned=[...j.abandoned,j.currentKey].slice(-2);
  j.currentKey=continuationKey(next);j.switchCount++;j.lastSwitchAt=nowSeconds();j.monitoring=false;j.waiting=false;
  state.queueReport=null;state.plan.adaptive_decision=null;selectRoute(next.id,true);
  toast('경로를 변경했습니다. 이동 중 재판단은 멈춥니다. 현재 위치를 갱신하거나 다음 정류장 도착을 선택해 주세요.');
}
function queueCapacity(leg){
  if(!leg)return null;
  const catalogue=state.bootstrap?.routes?.find(r=>r.id===leg.route_id);
  const choices=[leg.queue_report_opportunity?.vehicle_supply?.capacity,leg.vehicle_supply?.capacity,
    leg.queue_projection?.capacity_assumption,leg.automatic_queue?.capacity_assumption,catalogue?.capacity];
  return choices.find(n=>typeof n==='number'&&Number.isFinite(n)&&n>0)??null;
}
function renderMonitor(){
  const box=$('adaptive-monitor'),plan=state.plan,j=state.journey;if(!plan){box.hidden=true;return;}
  const bus=state.selected?.legs.find(l=>l.type==='bus');
  box.hidden=!j&&(!plan.live_predictions_used||$('departure-mode').value!=='now'||!bus);if(box.hidden)return;
  if(!j){box.innerHTML=`<h3>기다리는 중에도 비교</h3><p>정류장에 도착한 뒤 켜 주세요. 선택한 정류장에서 남은 이동시간을 60초마다 비교합니다.</p><button type="button" id="start-waiting">${escape(bus.from_name)} 도착 · 대기 비교 시작</button>`;$('start-waiting').addEventListener('click',startWaiting);return;}
  const d=plan.adaptive_decision,labels={worth_switching:'다른 경로로 변경을 권합니다.',current_unavailable:'기존 경로의 탑승 연결이 없어 대안을 권합니다.',current_fastest:'기존 경로가 예상 최단입니다.',small_gain:'예상 개선이 2분 미만이라 기존 경로 유지를 권합니다.',cooldown:'변경 직후 3분 유지 중입니다.',switch_limit:'이번 이동의 변경 권고 2회를 사용했습니다.',no_alternative:'지금 연결 가능한 대안이 없습니다.'};
  const current=plan.candidates.find(c=>continuationKey(c)===j.currentKey);
  const b=current?.legs.find(l=>l.type==='bus');
  const queue=b?.mode==='shuttle'&&j.waiting;
  const capacity=queueCapacity(b);
  const old=state.queueReport,expired=old&&(nowSeconds()-old.reported_at>90||old.opportunity_departure_at<=nowSeconds());
  box.innerHTML=`<h3>대기 중 남은시간 비교</h3><p>${j.waiting?escape(j.anchor.name)+' 기준':'현재 선택 출발점 기준'} · ${j.waiting?'정류장 대기 중':'이동 중 · 자동 비교 중지'} · 변경 ${j.switchCount}/2회</p>${b?.automatic_queue?`<p class="automatic-queue-evidence">${automaticQueueText(b.automatic_queue,true)}<br>직접 입력 없이 추천 시간에 반영 중입니다.</p>`:''}<p>${escape(d?labels[d.reason]||'남은시간을 비교합니다.':'현재 위치를 갱신하거나 다음 대기 정류장 도착을 선택해 주세요.')}${d?.gain_seconds!=null?` 예상 차이 ${durationText(Math.abs(d.gain_seconds))}.`:''}</p>${d?.action==='suggest_switch'?'<button type="button" id="accept-switch">추천 경로로 변경</button>':''}
    <div class="monitor-actions">${j.waiting?`<button type="button" id="toggle-monitor">${j.monitoring?'자동 비교 중지':'60초 자동 비교 켜기'}</button>`:b?'<button type="button" id="arrived-waiting">다음 정류장 도착 · 대기 재개</button>':''}<button type="button" id="monitor-location">현재 위치로 갱신</button><button type="button" id="end-monitor">이동 비교 종료</button></div>
    ${queue?`<details><summary>지금 보이는 줄·다음 차 여석 입력 (선택)</summary><form id="queue-report-form"><label>내 앞 대기 인원<input name="ahead" type="number" min="0" max="10000" step="1" required value="${expired?'':old?.queue_ahead??''}"></label><label>다음 차 여석 (모르면 비워두기)<input name="seats" type="number" min="0" ${capacity!=null?`max="${capacity}"`:'disabled'} step="1" value="${expired||old?.next_seats>capacity?'':old?.next_seats??''}"></label><label class="queue-full"><input name="full" type="checkbox" ${!expired&&old?.next_full?'checked':''}> 다음 차량 만차</label><button type="submit">줄 정보로 다시 계산</button></form><p>입력은 기준 차량 통과 전·최대 90초 동안만 사용합니다. ${capacity!=null?`선택한 차량 정원 ${capacity}명 기준입니다.`:'차량 정원이 확인되면 여석을 입력할 수 있습니다.'}${expired?' 입력의 기준 차량이 지났거나 90초가 지나 만료됐습니다. 현재 줄 인원을 새로 입력해 주세요.':old?(plan.queue_report_applied?' 입력을 반영한 FIFO 추정입니다.':' 현재 위치·정류소 조건에서 입력이 적용되지 않았습니다.'):''}</p></details>`:''}
    <details><summary>변경 기준과 근거</summary><p>앞으로 남은 보행·대기·차내·환승시간만 비교합니다. 이미 기다린 시간은 다시 더하지 않습니다. 2분 이상 개선·60초 재판단·변경 후 180초 유지·최대 2회는 시뮬레이션의 가정입니다. 실제 수단선택 계수로 검증되지 않았습니다. 떠난 승차지로의 복귀 권고를 제외합니다.</p>${adaptiveReferenceText()}<p>공용 캐시와 기존 호출 예산을 재사용합니다. 화면이 보이는 동안, 도착했다고 선택한 정류장에서만 자동 비교합니다. 위치가 바뀌면 갱신해 주세요.</p></details>`;
  $('accept-switch')?.addEventListener('click',acceptSuggestedSwitch);
  $('toggle-monitor')?.addEventListener('click',()=>{j.monitoring=!j.monitoring;renderMonitor();});
  $('arrived-waiting')?.addEventListener('click',startWaiting);
  $('monitor-location').addEventListener('click',()=>requestCurrentLocation());
  $('end-monitor').addEventListener('click',endJourney);
  $('queue-report-form')?.addEventListener('submit',event=>{event.preventDefault();const f=event.target;if(!f.checkValidity())return;
    if(!b.queue_report_opportunity||b.queue_report_opportunity.departure_at<=nowSeconds()){toast('다음 차량 기준이 오래됐습니다. 다시 비교한 뒤 입력해 주세요.');return;}
    const data=new FormData(f);state.queueReport={route_id:b.route_id,station_id:b.station_id,queue_ahead:Number(data.get('ahead')),
      next_seats:data.get('seats')===''?null:Number(data.get('seats')),next_full:data.has('full'),reported_at:nowSeconds(),
      opportunity_departure_at:b.queue_report_opportunity.departure_at,opportunity_vehicle_id:b.queue_report_opportunity.vehicle_id,
      opportunity_terminal_dispatch_at:b.queue_report_opportunity.vehicle_supply?.terminal_dispatch_at??null};search(null,{monitor:true});});
}
async function recheckWaiting(){
  if($('mobile-editor')?.open)return;
  const j=state.journey;if(!j?.waiting||!j.monitoring||state.planBusy||document.visibilityState!=='visible'||$('departure-mode').value!=='now'||nowSeconds()-j.lastCheckAt<60)return;
  if((state.bootstrap.status.arrival_calls_today||0)>=1200){j.monitoring=false;renderMonitor();toast('도착정보 보호 한도에 도달해 자동 비교를 중지했습니다.');return;}
  j.lastCheckAt=nowSeconds();await search(null,{monitor:true});
}
function renderResults() {
  const plan=state.plan;
  if(isMobile()){renderMonitor();renderMobileResults();return;}
  renderStrategies();
  renderMonitor();
  $('result-count').textContent=plan.candidate_count?`${plan.candidate_count}개 대안`:'';
  $('results-caption').textContent=`${timeLabel(plan.departure_at)} 출발 · ${destination().label} · ${Object.keys(plan.effective_weights).length?'추천 경로':'예상시간순'}`;
  $('comparison-note').hidden=true;$('comparison-note').textContent='';
  if(!plan.candidates.length){$('results').innerHTML='<div class="empty-state">연결 가능한 경로가 없습니다. 지도의 실제 통로 주변에서 출발지를 다시 선택해 주세요.</div>';return;}
  renderMobileResults();
}
function selectRoute(id,fit) {
  const candidate=state.plan.candidates.find(c=>c.id===id);if(!candidate)return;
  state.selected=candidate;
  renderMonitor();
  for(const button of $('strategy-comparison').querySelectorAll('[data-strategy-route]')){const selected=button.dataset.strategyRoute===id;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));}
  for(const card of $('results').querySelectorAll('[data-route]')){const selected=card.dataset.route===id;card.classList.toggle('selected',selected);card.setAttribute('aria-pressed',String(selected));}
  if(isMobile())mobileView('detail');
  map.showRoute(candidate,state.planOrigin||origin(),state.planDestination||destination(),fit);
  if(!isMobile()&&fit)window.RouteMotion?.route();
  renderSelected(candidate);
  $('wide-details').hidden=false;
  $('wide-details').querySelector('span:not(.ms)').textContent=`${minutes(candidate.total_seconds)}분 경로 · 상세 안내`;
  updateCountdowns();refreshSelectedArrivals();
}
function renderSelected(c) {renderMobileSelected(c);}
function showSources() {
  const status=state.bootstrap.status;
  const historical=state.bootstrap.historical_prediction;
  const routingModel=state.plan?.routing_model||state.bootstrap.routing_model;
  const continuity=state.bootstrap.continuity_model;
  const queueModel=state.plan?.prediction_model?.queue_release||state.bootstrap.automatic_queue;
  const weightLine=state.plan?Object.entries(state.plan.effective_weights).filter(([,v])=>v>0).map(([key,value])=>`${{time:'시간',walk:'도보',crowd:'혼잡',transfers:'환승'}[key]} ${Math.round(value*100)}%`).join(' · '):'경로 비교 후 표시';
  const kakaoWalkUsed=state.plan?.candidates.some(c=>c.legs.some(l=>l.type==='walk'&&l.source?.startsWith('카카오 도보')));
  $('source-content').innerHTML=`${state.bootstrap.building_catalog?`<div class="source-row"><strong>교내 건물 검색</strong><span>서울대 공식 캠퍼스맵 ${state.bootstrap.building_catalog.count}개 건물<br>${escape(state.bootstrap.building_catalog.source.retrieved_at.slice(0,10))} 자료 · 검색 중 외부 API 호출 없음</span></div><p>건물 대표 좌표와 도보 안내 시작점을 구분합니다. 출입구 연결이 없는 곳은 건물 부근의 실제 지도 보행로에서 계산하며, 실내 이동과 미확인 연결 구간은 포함하지 않습니다. <a href="https://map.snu.ac.kr/web/main.action" target="_blank" rel="noopener">서울대 공식 캠퍼스맵</a></p>`:''}<div class="source-row"><strong>지도·보행 경로</strong><span>전체 보행 평균4.8km/h · 계단 구간 별도 표시<br>${map.provider==='kakao'?'카카오 지도':'OpenStreetMap 검토용 지도'}<br>${kakaoWalkUsed?'카카오 도보 API':'OSM 보행망 · 현장 검증 전'}</span></div>
    <div class="source-row"><strong>버스 위치</strong><span>서울시 버스위치 OpenAPI<br>${status.captured_at?timeLabel(status.captured_at)+' 수집':'최근 수신 자료 없음'}</span></div>
    <div class="source-row"><strong>버스 도착예정</strong><span>서울시 공식 모바일 웹 조회<br>최근 예측값을 받을 때만 사용</span></div>
    ${historical?`<div class="source-row"><strong>기본 이용량 예측</strong><span>${escape(historical.label)} · 평일 12~22시<br>${escape(historical.history_start)}~${escape(historical.history_end)} 중 ${historical.history_days}일</span></div><p>서울특별시 서울교통 빅데이터 플랫폼·TAIMS의 과거 구간 자료입니다. 동일 요일과 전체 평일 평균을 함께 반영합니다. 실시간 혼잡 관측과 구분하며, 시간당 재차합을 차량 한 대의 인원·대기 인원·혼잡 점수로 바꾸지 않습니다. 셔틀과 주말에는 이 자료를 적용하지 않습니다. <a href="${escape(historical.source_url)}" target="_blank" rel="noopener">원자료 안내 · 저작권자 표시(BY)</a></p>`:''}
    ${continuity?`<div class="source-row"><strong>관측 사이 예측</strong><span>${escape(continuity.model_id)}<br>과거 차량등급·마지막 관측·최신v5 수업 유입</span></div><p>새 관측 사이에도 예상 승차기회와 혼잡위험을 제시합니다. 차량별 등급 실측은 ${escape(continuity.empirical_dates.join(', '))}의 일부 토·일 자료로 평일 정확도를 검증하지 못했습니다. 관악02 등급 미제공 구간은 수요 모형의 보수적 기준위험입니다. 혼잡 예측에는 불확실성 비용을 반영하며, 자료와 계산 근거는 이 안내에서 확인할 수 있습니다. 개인 도보4.8km/h와 v5 기준집단 보행 분포는 구분하며 전체집단을 새 속도로 재실행한 결과가 아닙니다.</p>`:''}
    <div class="source-row"><strong>비교 범위</strong><span>시내버스 8개 + 행정관·교내 순환·역순환<br>셔틀 환승 시 실제 보행 경로 포함</span></div>
    ${queueModel?`<div class="source-row"><strong>실험실 대기모델</strong><span>${escape(queueModel.model_id)}<br>교내 셔틀${queueModel.city_wait?.available?' · 시내버스 '+queueModel.city_wait.route_count+'개 노선':''}</span></div><p>실시간 도착예정과 정류장별 FIFO 승차 지연을 함께 반영합니다. 완료된 이전 날짜의 혼잡등급·알려진 만차 여부·정류장 통과간격을 기록하고 예측에 사용합니다. 혼잡등급을 실제 줄 인원이나 여석으로 환산하지 않습니다. 실험실의 새 발행은 요청 시 최대 60초에 한 번 확인하며, 한 번의 경로 비교에는 같은 모델을 적용합니다.</p>`:''}
    ${(queueModel?.city_operations?.available)?'<p><a href="https://snu-shuttle-simulation.vercel.app/weekday-operations-methodology.html" target="_blank" rel="noopener">평일 운행·대기모형 설명서</a></p>':''}
    ${routingModel?`<div class="source-row"><strong>소요시간·탐색 모형</strong><span>${escape(routingModel.model_id)}<br>${escape(routingModel.algorithm)}</span></div><p>${escape(routingModel.priority)}. ${escape(routingModel.dwell_convention)}. ${escape(routingModel.assumptions)}. 경로를 시간순으로 계산한 뒤 최대40개를 남깁니다.</p>`:''}
    <div class="source-row"><strong>반영된 가중치</strong><span>${escape(weightLine)}</span></div>
    <h3>버스 도착 카운트다운</h3><p>초 단위 숫자는 마지막 도착예정시각에서 남은 시간을 계산합니다. 선택 경로의 도착정보는 공용 캐시로 갱신하며, 관측이 오래되거나 예정시각이 지나면 이전 운행·시간표·시뮬레이션의 예상 운행기회로 이어서 안내합니다. 추정 운행기회는 실제 차량 확인과 구분합니다. 경로 총시간은 검색 시점 기준입니다.</p><h3>예상시간의 계산 기준</h3><ul>${(state.plan?.assumptions||['전체 보행 평균4.8km/h · 계단 구간 별도 표시','차내시간: 도착예정 차이·완료 관측·최신 구간속도 우선, 일치하는 미관측 구간은 v5 도로·가감속·정차 모형','승차 여유 20초','배차정보 기준일 2026-11-04 · 임시 운행 변경 확인 전']).map(x=>`<li>${escape(x)}</li>`).join('')}</ul>
    <h3>정보가 없는 경우</h3><p>혼잡도가 없거나 오래된 경로에는 불확실성 비용을 별도로 반영합니다. 정보 부족을 실제 혼잡 관측이나 착석 확률로 표시하지 않습니다. 도착 관측이 없는 구간도 이전 도착·과거 구간간격·시간표·모형으로 예상 승차기회를 안내합니다. 실제 차량 확인과 구분합니다.</p>
    <h3>셔틀과 현장 검증</h3><p>${escape(state.bootstrap.scope.shuttle_note)} 교내 출입구·계단·보행 통행 가능성과 추천 정확도는 추가 관측이 필요합니다. 지정한 미래 시각에 실시간 셔틀 위치를 외삽하지 않습니다.</p>
    <p><a href="/docs/shuttle-timetable.pdf" target="_blank" rel="noopener">공식 셔틀 시간표 원문</a> · <a href="https://www.data.go.kr/data/15000332/openapi.do" target="_blank" rel="noopener">서울시 위치 API</a> · <a href="https://www.data.go.kr/data/15000193/openapi.do" target="_blank" rel="noopener">서울시 공식 노선 경로</a> · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap 기여자</a></p>`;
  $('sources-dialog').showModal();
}
function selectPoint(lat,lon,label='지도에서 선택한 출발지',preserveJourney=false) {
  if(!(lat>=37.438&&lat<=37.486&&lon>=126.936&&lon<=126.970)){toast('관악캠퍼스와 인근 목적지 주변에서 출발지를 선택해 주세요.');return;}
  if(!preserveJourney){state.journey=null;state.queueReport=null;}
  else if(state.journey&&Math.hypot((lat-state.journey.anchor.lat)*111000,(lon-state.journey.anchor.lon)*88000)>60){state.journey.monitoring=false;state.journey.waiting=false;state.queueReport=null;}
  state.originRevision++;state.customOrigin={lat,lon,label};
  if(state.userLocation&&!label.startsWith('현재 위치'))$('location-status').textContent='내 위치 표시는 유지합니다. 경로 출발지는 지도에서 선택한 지점입니다.';
  let option=$('origin').querySelector('[value="custom"]');if(!option){option=new Option(label,'custom');$('origin').add(option);}
  const wasPicking=state.picking;option.textContent=label;$('origin').value='custom';state.picking=false;$('map-hint').hidden=true;$('pick-origin').classList.remove('active');
  syncOriginSearch();
  if($('mobile-location-note'))$('mobile-location-note').textContent=label;if(wasPicking){openMobileEditor();return;}if(state.journey){search(null,{monitor:true});return;}
  if(isMobile()||state.mobileView==='home'||$('mobile-editor').open||!destination())return;
  toast('출발지를 선택했습니다. 경로를 비교하고 있습니다.');search();
}
async function requestCurrentLocation(automatic=false) {
  const status=$('location-status'),button=$('my-location');
  if(state.locating)return;
  if(!navigator.geolocation){status.textContent='이 브라우저는 위치 조회를 지원하지 않습니다. 지도에서 출발지를 골라 주세요.';return;}
  const revision=state.originRevision;status.hidden=false;state.locating=true;button.disabled=true;button.textContent='위치 확인 중';status.textContent='기기 위치를 확인합니다. 브라우저의 위치 요청을 허용해 주세요.';
  try {
    const position=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:15000,maximumAge:30000}));
    const {latitude:lat,longitude:lon,accuracy}=position.coords;
    if(!Number.isFinite(lat)||!Number.isFinite(lon)||!Number.isFinite(accuracy)||accuracy<0)throw new Error('위치 응답을 확인할 수 없습니다.');
    const location={lat,lon,accuracy,timestamp:position.timestamp||Date.now()};state.userLocation=location;map.showUserLocation(location,!automatic);
    const inside=lat>=37.438&&lat<=37.486&&lon>=126.936&&lon<=126.970;
    if(!inside){status.textContent=`현재 위치 확인 · 오차 약 ${distanceLabel(accuracy)} · 교외에 계십니다. 경로 계산은 교내 출발지를 선택해 주세요.`;return;}
    if(accuracy>250){status.textContent=`위치 오차 약 ${distanceLabel(accuracy)}입니다. 파란 원을 확인하고 지도에서 출발지를 선택해 주세요.`;return;}
    if(state.originRevision!==revision){status.textContent=`내 위치 확인 · 오차 약 ${distanceLabel(accuracy)} · 선택한 출발지를 유지합니다.`;return;}
    selectPoint(lat,lon,`현재 위치 · 오차 약 ${distanceLabel(accuracy)}`,Boolean(state.journey));
    status.hidden=true;status.textContent=`현재 위치를 출발지로 사용 중 · 오차 약 ${distanceLabel(accuracy)} · ${new Intl.DateTimeFormat('ko-KR',{hour:'2-digit',minute:'2-digit'}).format(new Date(location.timestamp))} 확인`;
  } catch(error) {
    const messages={1:'위치 권한이 꺼져 있습니다. 주소창의 사이트 권한에서 위치를 허용한 뒤 현재 위치를 눌러 주세요.',2:'기기 위치를 찾지 못했습니다. 위치 서비스를 확인하거나 지도에서 출발지를 골라 주세요.',3:'위치 확인 시간이 초과됐습니다. 현재 위치를 다시 눌러 주세요.'};
    status.textContent=messages[error.code]||error.message||'위치를 확인하지 못했습니다.';if(!automatic)toast(status.textContent);
  } finally {state.locating=false;button.disabled=false;button.textContent='현재 위치';if($('mobile-location-note'))$('mobile-location-note').textContent=origin()?.label||'위치 권한을 허용하거나 출발지를 선택해 주세요';}
}
function bind() {
  document.addEventListener('route-defaults-change',event=>{
    const defaults=event.detail;state.weights={...defaults.weights};state.preset=defaults.preset;
    $('include-shuttle').checked=defaults.includeShuttle;renderWeights();
    document.querySelectorAll('[data-preset]').forEach(b=>{const active=b.dataset.preset===state.preset;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  });
  $('route-form').addEventListener('submit',search);
  document.querySelectorAll('[data-preset]').forEach(b=>b.addEventListener('click',()=>setPreset(b.dataset.preset)));
  $('origin').addEventListener('change',()=>{endJourney();state.originRevision++;if($('origin').value!=='custom')state.customOrigin=null;if($('origin').value==='device')requestCurrentLocation();else $('location-status').textContent=origin()?.official_building_id?'선택한 건물을 출발지로 사용합니다.':'선택한 정류소·건물을 출발지로 사용합니다.';syncOriginSearch();});
  $('destination').addEventListener('change',endJourney);
  $('departure-mode').addEventListener('change',()=>{endJourney();$('departure-time').hidden=$('departure-mode').value!=='specified';renderStatus(state.bootstrap.status);if(state.shuttle)map?.showShuttle(shuttleMapData(state.shuttle));});
  $('pick-origin').addEventListener('click',()=>{state.picking=!state.picking;$('map-hint').hidden=!state.picking;$('pick-origin').classList.toggle('active',state.picking);if(state.picking){closeMobileEditor(true);mobileView('home');}});
  $('cancel-pick').addEventListener('click',()=>{state.picking=false;$('map-hint').hidden=true;$('pick-origin').classList.remove('active');});
  $('my-location').addEventListener('click',()=>requestCurrentLocation());
  $('refresh-button').addEventListener('click',()=>refresh());$('fit-button').addEventListener('click',()=>map.fit());
  $('stops-button').addEventListener('click',()=>{$('stops-button').setAttribute('aria-pressed',String(map.toggleStops()));});
  $('sources-button').addEventListener('click',showSources);
  $('shuttle-button').addEventListener('click',()=>{renderShuttle();$('shuttle-dialog').showModal();});
  document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>$(button.dataset.close).close()));
  for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
  $('observation-form').addEventListener('submit',async event=>{
    event.preventDefault();if(!state.selected)return;const form=new FormData(event.target);const button=event.target.querySelector('button[type=submit]');button.disabled=true;
    if(state.bootstrap.status.storage?.observations_available===false){toast('기록 저장이 일시 중단돼 입력한 내용은 저장되지 않았습니다.');return;}
    try {
      const result=await api('/api/observations',{candidate:state.selected.observation_key,planned_seconds:state.selected.total_seconds,actual_minutes:Number(form.get('actual')),satisfaction:Number(form.get('satisfaction')),seated:form.get('seated')});
      $('observation-dialog').close();event.target.reset();toast(`이동 결과를 기록했습니다. 예상과 실제 차이 ${Math.round(result.time_error_seconds/60)}분`);
    }catch(error){toast(error.message);}finally{button.disabled=state.bootstrap.status.storage?.observations_available===false;}
  });
}
async function initialize() {
  try {
    state.bootstrap=await api('/api/bootstrap');
    window.RouteSettings?.configure(state.bootstrap.presets,state.bootstrap.version);
    const defaults=window.RouteSettings?.read();
    if(defaults){state.weights={...defaults.weights};state.preset=defaults.preset;$('include-shuttle').checked=defaults.includeShuttle;}
    document.querySelectorAll('[data-preset]').forEach(b=>{const active=b.dataset.preset===state.preset;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
    $('origin').innerHTML='<option value="device">현재 위치</option>'+state.bootstrap.origins.map(x=>`<option value="${x.id}">${escape(x.label)}</option>`).join('');
    $('destination').innerHTML='<option value="" disabled selected>목적지를 선택해 주세요</option>'+state.bootstrap.destinations.map(x=>`<option value="${x.id}">${escape(x.label)}</option>`).join('');
    const now=new Date();$('clock').textContent=new Intl.DateTimeFormat('ko-KR',{weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).format(now);
    const next=new Date(Date.now()+30*60000);next.setMinutes(next.getMinutes()-next.getTimezoneOffset());$('departure-time').value=next.toISOString().slice(0,16);
    renderWeights();bind();bindMobile();bindOriginSearch();
    map=new RouteMap($('map'),(lat,lon)=>{if(state.picking)selectPoint(lat,lon);});
    const provider=await map.initialize(state.bootstrap.map,state.bootstrap.routes);
    $('map-provider').textContent=provider==='kakao'?'카카오 지도 · 보행망 출처 별도':'보행망 © OpenStreetMap';
    renderStatus(state.bootstrap.status);
    if(window.RouteSettings?.initialOpen){
      $('results').innerHTML='<div class="empty-state">출발지와 목적지를 선택하고 경로를 비교해 주세요.</div>';
      $('results-caption').textContent='원하는 출발지와 목적지를 선택해 주세요.';
    }else requestCurrentLocation(true);
    await Promise.allSettled([refresh(true),refreshShuttle()]);
    setInterval(()=>{if(document.visibilityState==='visible')refreshShuttle();},15000);
    setInterval(()=>{if(document.visibilityState==='visible')refresh(true);},15000);
    setInterval(()=>{updateCountdowns();recheckWaiting();},1000);
    setInterval(refreshSelectedArrivals,15000);
  }catch(error){$('results').innerHTML=`<div class="empty-state">서버 연결을 확인해 주세요.<br>${escape(error.message)}</div>`;$('live-label').textContent='연결 확인 필요';toast('데이터를 불러오지 못했습니다. 서버 상태를 확인해 주세요.');}
}
initialize();
