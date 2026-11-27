import {createGraphs} from './graphs-v5.js';
import {motionAt} from './bus-motion.js';
import {snapshotAt,summaryMarkup,installSnapshotQuery} from './snapshot-query.js';
import {initialReplayClock} from './initial-clock.js';
import {createJsonLoader} from './json-loader.js';
import {installMobileLab} from './mobile-lab.js?v=261110173652';
const $=id=>document.getElementById(id), ROOT='viewer-data/';
const DAYS={mon:'월요일',tue:'화요일',wed:'수요일',thu:'목요일',fri:'금요일'};
const COLORS=['#3e947b','#d89a42','#547db1','#8b6abd'],RED='#c85645',START=40800,END=83400;
const initialClock=initialReplayClock(new Date(),location.search);
const state={day:initialClock.day,scenario:'peak',policy:'city',stop:'admin_snu',vehicleFilter:'all',mode:'movement',pane:'map',second:initialClock.second,speed:1,playing:false,last:0,ready:false,common:null,data:null,chartData:null,request:0};
state.supplyCorrected=true;
state.destination='all';
const json=createJsonLoader(8),replayJson=createJsonLoader(4),pathCache=new Map();
let commonReady,selectedMarker=null,selectedEventRows=[],lastSidebarSecond=-1;
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(n);
const clamp=t=>Math.max(START,Math.min(END,t));
const clock=t=>{const n=Math.floor(t);return `${String(Math.floor(n/3600)).padStart(2,'0')}:${String(Math.floor(n/60)%60).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;};
const params=new URLSearchParams(location.search);
if(['regular','peak'].includes(params.get('scenario')))state.scenario=params.get('scenario');

$('weekday').value=state.day;$('scenario').value=state.scenario;

if(initialClock.notice){
  const note=document.createElement('p');note.className='city-source-note initial-clock-note'+(initialClock.requiresNotice?'':' sr-only');note.textContent=initialClock.notice;
  note.style.gridColumn='1 / -1';note.style.fontSize='11px';note.style.margin='4px 0';
  document.querySelector('.control-grid').insertAdjacentElement('afterend',note);
}
const map=L.map('map',{zoomControl:false,preferCanvas:true,minZoom:13,maxZoom:19}).setView([37.451,126.952],16);
L.control.zoom({position:'topright'}).addTo(map);map.attributionControl.setPrefix(false);
map.attributionControl.addAttribution('<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap 기여자</a>');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,keepBuffer:1,updateWhenIdle:true}).addTo(map);
const geography=L.layerGroup().addTo(map),labels=L.layerGroup().addTo(map),rerouteOverlay=L.layerGroup().addTo(map);
const cityLines=L.layerGroup().addTo(map);
const stopMarkers=L.layerGroup().addTo(map);let stopGroups=[],activeStopPopup=null;
const peoplePane=map.createPane('simulationPeople');peoplePane.style.zIndex='450';peoplePane.style.pointerEvents='none';
const canvas=document.createElement('canvas');canvas.className='people-canvas';canvas.setAttribute('aria-hidden','true');peoplePane.append(canvas);const ctx=canvas.getContext('2d');
const MODEL='R261124102753';
const landmarks={snu:'서울대입구역',nak:'낙성대역',daehak:'대학동',dorm_ug:'학부생활관',dorm_grad:'대학원생활관',gwanaksan_4411:'관악산(서울대)역'};
const destinationNames={all:'전체 목적지',snu:'서울대입구역',nak:'낙성대역',daehak:'대학동',dorm:'기숙사',gwanaksan_4411:'관악산(서울대)역'};
const destinationSelect=$('destination');
const journeyLayer=L.layerGroup().addTo(map);
const previewButton=document.createElement('button');
previewButton.type='button';
previewButton.className='highlight-button';
previewButton.textContent='이 시각 경로 예시 보기';
const previewLabel=document.createElement('output');
previewLabel.className='journey-label';
document.querySelector('.demand-summary').append(previewButton,previewLabel);
for(const [key,label] of Object.entries(destinationNames)){
  destinationSelect.add(new Option(key==='gwanaksan_4411'?'관악산역':label,key));
}
if(Object.hasOwn(destinationNames,params.get('destination')))state.destination=params.get('destination');
destinationSelect.value=state.destination;
function showDemand(run,data){
  if(run.model!==MODEL || run.scenario!==data.report.scenario || run.weekday!==data.report.weekday ||
     Math.abs(run.total-data.report.input_weight)>0.00001)throw new Error('선택한 실행의 통계가 일치하지 않습니다.');
  state.demand=run;
  updateDemand();
}
function updateDemand(){
  previewButton.hidden=state.destination==='all';
  previewButton.disabled=!state.demand;
  if(!state.demand)return;
  const count=state.destination==='all'?state.demand.total:state.demand.destinations[state.destination];
  $('destination-count').textContent=fmt(count)+'명 상당';
  $('destination-label').textContent=destinationNames[state.destination]+' · 하루 모의 통행';
}
function clearJourney(){
  journeyLayer.clearLayers();
  previewLabel.textContent='';
}
previewButton.addEventListener('click',()=>{
  if(!state.ready || state.destination==='all')return;
  clearJourney();
  const trips=state.data.trips.filter(t=>t[2]===state.destination && !t[5] && t[4].length);
  if(!trips.length){previewLabel.textContent='이 목적지의 지도 표본이 없습니다.';return;}
  const trip=trips.reduce((a,b)=>Math.abs(a[4][0][1]-state.second)<=Math.abs(b[4][0][1]-state.second)?a:b);
  const legs=trip[4];
  const bounds=L.latLngBounds([]);
  let walk=0,wait=0,ride=0;
  for(const [kind,start,end,id] of legs){
    const duration=(end-start)/60;
    if(kind===1){wait+=duration;continue;}
    const points=state.common.paths[id];
    if(kind===0)walk+=duration;else ride+=duration;
    L.polyline(points,{color:kind===0?'#138071':'#344f9b',dashArray:kind===0?'5 5':null,
      weight:5,opacity:.88,interactive:false}).addTo(journeyLayer);
    for(const pt of points)bounds.extend(pt);
  }
  setPlaying(false);
  const sheet=$('lab-sheet-toggle');
  if(sheet?.getAttribute('aria-expanded')==='true')sheet.click();
  if(bounds.isValid())map.fitBounds(bounds,{
    paddingTopLeft:[30,95],paddingBottomRight:[30,document.body.dataset.labMobile?145:210],maxZoom:17,animate:false});
  previewLabel.textContent=trip[1]+'동 → '+destinationNames[trip[2]]+' · '+clock(legs[0][1]).slice(0,5)+' 출발 · 도보 '+fmt(walk)+'분 · 대기 '+fmt(wait)+'분 · 차내 '+fmt(ride)+'분';
});
destinationSelect.addEventListener('change',()=>{
  state.destination=destinationSelect.value;
  clearJourney();
  rerouteOverlay.clearLayers();
  const url=new URL(location.href);url.searchParams.set('destination',state.destination);history.replaceState(null,'',url);
  updateDemand();
  draw();
});
function metres(a,b){const r=Math.PI/180;return Math.hypot((b[1]-a[1])*r*Math.cos((a[0]+b[0])/2*r),(b[0]-a[0])*r)*6371000;}
function preparedPath(id){
  if(pathCache.has(id))return pathCache.get(id);const points=state.common.paths[id],d=new Float64Array(points.length);
  for(let i=1;i<points.length;i++)d[i]=d[i-1]+metres(points[i-1],points[i]);
  const p={points,d,total:d.at(-1)||0};pathCache.set(id,p);return p;
}
function position(id,f){
  const p=preparedPath(id);if(p.points.length===1||!p.total)return p.points[0];const at=Math.max(0,Math.min(1,f))*p.total;
  let lo=0,hi=p.points.length-1;while(lo+1<hi){const m=(lo+hi)>>1;if(p.d[m]<at)lo=m;else hi=m;}
  const delta=p.d[hi]-p.d[lo],a=delta?(at-p.d[lo])/delta:0;
  return [p.points[lo][0]+(p.points[hi][0]-p.points[lo][0])*a,p.points[lo][1]+(p.points[hi][1]-p.points[lo][1])*a];
}
function busMotion(id,elapsed,duration){
  const profile=state.common.motion_profiles?.[String(id)];
  if(!profile)return {point:position(id,elapsed/duration),kmh:0};
  const ratio=profile.duration/duration,m=motionAt(profile,elapsed*ratio),p=preparedPath(id);
  return {point:position(id,p.total?m.distance/p.total:0),kmh:m.speed*3.6*ratio};
}
function latest(rows,t,column=0){let lo=0,hi=rows.length;while(lo<hi){const m=(lo+hi)>>1;if(rows[m][column]<=t)lo=m+1;else hi=m;}return lo-1;}
function activeLeg(legs,t){const i=latest(legs,t,1);return i>=0&&t<legs[i][2]?legs[i]:null;}
export function queueAt(data,node,t){const rows=data.queue_timeline[node]||[],i=latest(rows,t);return i<0?[0,0]:[rows[i][1],rows[i][2]];}
function sizeCanvas(){const s=map.getSize(),d=Math.min(devicePixelRatio||1,2);L.DomUtil.setPosition(canvas,map.containerPointToLayerPoint([0,0]));canvas.width=Math.round(s.x*d);canvas.height=Math.round(s.y*d);canvas.style.width=s.x+'px';canvas.style.height=s.y+'px';ctx.setTransform(d,0,0,d,0,0);draw();}
function focusMap(area){
  const bounds={all:[[37.445,126.933],[37.4825,126.9705]],engineering:[[37.447,126.9478],[37.4548,126.956]],admin:[[37.4558,126.9448],[37.466,126.9565]]};
  const destination=state.common?.destinations.gwanaksan_4411;
  if(destination)bounds.station=L.latLngBounds(destination,destination).pad(.01);
  map.fitBounds(bounds[area],{paddingTopLeft:[22,65],paddingBottomRight:[22,innerWidth<=700?205:225],maxZoom:area==='all'?15:17,animate:false});
  document.querySelectorAll('[data-focus]').forEach(b=>b.classList.toggle('active',b.dataset.focus===area));
}
function dot(point,r,color,alpha=.9){
  const p=map.latLngToContainerPoint(point),s=map.getSize();if(p.x<-15||p.y<-15||p.x>s.x+15||p.y>s.y+15)return;
  ctx.globalAlpha=alpha;ctx.beginPath();ctx.arc(p.x,p.y,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();
}
function showVehicle(rid){return state.vehicleFilter==='all'||state.vehicleFilter==='city'&&!rid.startsWith('shuttle')||state.vehicleFilter==='shuttle'&&rid.startsWith('shuttle')||state.vehicleFilter===rid;}
function routeName(rid){return state.common.city_services?.find(r=>r.route_id===rid)?.name||({'shuttle-41841':'입구역 셔틀','shuttle-daehak':'대학동 셔틀','shuttle-41946':'교내 순환','shuttle-41914':'역순환'}[rid]||rid);}
function drawBus(point,load,capacity,kmh,rid,offset=0){
  const p=map.latLngToContainerPoint(point),s=map.getSize();if(p.x<0||p.x>s.x||p.y<0||p.y>s.y)return;
  p.y+=offset;
  const text=`${fmt(load)}/${capacity}`,name=routeName(rid);ctx.globalAlpha=.97;ctx.font="600 10px 'Malgun Gothic',sans-serif";const w=Math.max(ctx.measureText(text).width,ctx.measureText(name).width)+12;
  ctx.fillStyle=load>=capacity-.01?RED:rid.startsWith('shuttle')?'#365b65':'#3b5f9d';ctx.beginPath();ctx.roundRect(p.x-w/2,p.y-19,w,43,5);ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.stroke();ctx.fillStyle='#fff';ctx.textAlign='center';ctx.textBaseline='middle';ctx.font="600 9px 'Malgun Gothic',sans-serif";ctx.fillText(name,p.x,p.y-10);ctx.font="600 10px 'Malgun Gothic',sans-serif";ctx.fillText(text,p.x,p.y+3);ctx.font="8px 'Malgun Gothic',sans-serif";ctx.fillText(kmh<.5?'정차':`${Math.round(kmh)} km/h`,p.x,p.y+15);
}
function draw(){
  const s=map.getSize();ctx.clearRect(0,0,s.x,s.y);if(!state.ready||!state.data||(state.pane!=='map'&&!document.body.dataset.labMobile))return;
  const t=state.second,busPositions=new Map(),buses=[];
  for(const v of state.data.vehicles){const legs=v[3],i=latest(legs,t),leg=i>=0?legs[i]:null;if(!leg||t>=leg[1])continue;const motion=busMotion(leg[2],t-leg[0],leg[1]-leg[0]);busPositions.set(v[0],motion.point);if(showVehicle(v[1]))buses.push([motion.point,leg[3],v[2],motion.kmh,v[1]]);}
  const waiting=new Map();let count=0,redCount=0,reroutedWalkDots=0;
  for(const trip of state.data.trips){
    const [identity,building,dest,weight,legs]=trip;
    if(state.destination!=='all' && dest!==state.destination)continue;
    const leg=activeLeg(legs,t);if(!leg)continue;
    const [kind,a,b,pid,node,denied,vehicle]=leg;
    if(kind===1&&node>=0){if(!waiting.has(node))waiting.set(node,[]);waiting.get(node).push([trip,leg]);continue;}
    if(state.mode==='queue')continue;
    const p=kind===3&&busPositions.has(vehicle)?busPositions.get(vehicle):kind===2||kind===3?busMotion(pid,t-a,b-a).point:position(pid,(t-a)/(b-a));
    const jitter=kind===1?.00002:.000006;
    const rerouted=kind===0&&leg[7]===true;if(rerouted)reroutedWalkDots++;
    dot([p[0]+((identity%17)/16-.5)*jitter,p[1]+(((identity>>>5)%17)/16-.5)*jitter],kind===1?2.5:rerouted?3:2.1,rerouted?'#008dac':COLORS[kind]);count++;
  }
  for(const [node,rows] of waiting){
    rows.sort((a,b)=>a[1][1]-b[1][1]||a[0][0]-b[0][0]);const n=state.common.nodes[node];
    rows.forEach(([trip,leg],i)=>{
      const denied=leg[5]>=0&&leg[5]<=t;if(denied)redCount++;
      // Queue dot placement is illustrative. Arrival order persists until boarding.
      const row=Math.floor(i/4),col=i%4,side=n.route==='shuttle-daehak'?-1:1;
      const p=[n.lat+(row*.000020+.000022)*side,n.lon+(col-1.5)*.000022+(n.route==='shuttle-daehak'?.00007:0)];
      dot(p,denied?3.1:2.7,denied?RED:COLORS[1],.95);count++;
    });
  }
  const groups=new Map();for(const bus of buses){const key=bus[0].map(v=>v.toFixed(7)).join(',');if(!groups.has(key))groups.set(key,[]);groups.get(key).push(bus);}
  for(const group of groups.values())group.forEach((bus,i)=>drawBus(...bus,(i-(group.length-1)/2)*46));ctx.globalAlpha=1;
  $('map-status').textContent=`이동 표본 ${count.toLocaleString('ko-KR')}개 · 만차 잔류 ${redCount}개 · 변경 후 도보 ${reroutedWalkDots}개`;
  canvas.dataset.destination=state.destination;
  canvas.dataset.reroutedWalkDots=reroutedWalkDots;
  canvas.dataset.mode=state.mode;canvas.dataset.second=t.toFixed(3);canvas.dataset.deniedDots=redCount;canvas.dataset.sampleDots=count;canvas.dataset.maxShuttleKmh=Math.max(0,...buses.map(b=>b[3])).toFixed(3);
  canvas.dataset.cityVehicles=buses.filter(b=>!b[4].startsWith('shuttle')).length;
  canvas.dataset.shuttleVehicles=buses.filter(b=>b[4].startsWith('shuttle')).length;
  updateSidebar();
}
function updateSidebar(force=false){
  if(!state.ready)return;const integer=Math.floor(state.second);if(!force&&integer===lastSidebarSecond)return;lastSidebarSecond=integer;
  const node=state.common.hot_nodes[state.stop],n=state.common.nodes[node],[q,d]=queueAt(state.data,node,state.second);
  $('stop-queue').textContent=fmt(q);$('stop-denied').textContent=fmt(d);
  $('snapshot-sidebar').innerHTML=summaryMarkup(snapshotAt(state),{clock,fmt});
  const index=latest(selectedEventRows,state.second),previous=selectedEventRows[index],next=selectedEventRows[index+1];
  const nextGroup=next?selectedEventRows.filter(e=>e[0]===next[0]):[];
  const previousGroup=previous?selectedEventRows.filter(e=>e[0]===previous[0]):[];
  const nextRid=next?state.data.vehicles.find(v=>v[0]===next[2])?.[1]:null;
  $('next-bus').textContent=next?`다음 ${routeName(nextRid||'버스')} ${clock(next[0])} · 참고정원 ${next[3]}${nextGroup.length>1?` × ${nextGroup.length}회차`:''}`:'이 승차지의 남은 모형 운행이 없습니다.';
  $('last-bus').textContent=previous?`직전 ${clock(previous[0])} · 탑승 ${fmt(previousGroup.reduce((sum,e)=>sum+e[6],0))} · 해당 노선 만차 잔류 ${fmt(previous[8])}`:'현재 시각 이전 정차가 없습니다.';
  const switches=(state.data.switches||[]).filter(e=>e[0]<=state.second),local=switches.filter(e=>e[1]===node);
  $('switch-count').textContent=fmt(local.reduce((s,e)=>s+e[2],0));
  $('gate-count').textContent=fmt((state.data.gate_boardings||[]).filter(e=>e[0]<=state.second).reduce((s,e)=>s+e[2],0));
  $('adaptive-status').textContent=state.policy==='city'?'시내·셔틀 정원 연계 · 동일 승차지 대기줄과 변경 사건의 가중치':state.policy==='adaptive'?'이전 v4 · 셔틀 줄 경로 변경 / 시내 정원 제한 없음':'이전 v3 · 줄을 보고 경로를 변경하지 않음';
  if(selectedMarker)selectedMarker.setTooltipContent(`${esc(n.name)} · ${n.city?'시내 공동 승차지':state.stop.startsWith('admin')?'통학 셔틀':state.stop.startsWith('reverse')?'역순환':'순환'}<br>대기 ${fmt(q)} · 만차 잔류 ${fmt(d)}`);
  renderHistory();
  updateStopPopup();
}
function renderHistory(){
  const box=$('city-history');if(!box||!state.common||!state.data)return;
  const n=state.common.nodes[state.common.hot_nodes[state.stop]],weekday=Object.keys(DAYS).indexOf(state.day),hour=Math.floor(state.second/3600);
  if(!n.city||state.policy!=='city'){box.textContent='시내 승차지를 선택하면 과거 시간당 구간 재차합을 별도로 표시합니다.';return;}
  const rows=[];
  for(const s of n.services){const stops=state.common.city_route_stops[s.rid],a=stops[s.board],b=stops[s.board+1];if(!b)continue;
    const value=state.common.city_history.profiles[[s.rid,a.seq,a.id,b.id,weekday,hour].join('|')];
    if(value)rows.push(`${s.route_name}: ${fmt(value.mean_sum_load)} (${value.sample_dates}일)`);
  }
  box.textContent=rows.length?`과거 ${hour}시 구간 재차합 평균 · ${rows.join(' / ')}. 차량 1대의 인원·여석이 아닙니다.`:'해당 요일·시간·방향 구간의 과거 재차합 자료가 없습니다. 결측을 0명으로 바꾸지 않습니다.';
}
function stopOptions(){
  const select=$('stop-select'),keys=Object.keys(state.common.hot_nodes),seen=new Set();
  const shuttle=document.createElement('optgroup');shuttle.label='셔틀 승차지';const city=document.createElement('optgroup');city.label='시내버스 공동 승차지';
  for(const key of keys){const node=state.common.hot_nodes[key],n=state.common.nodes[node];if(seen.has(node)||n.city&&state.policy!=='city')continue;seen.add(node);
    const label=n.city?`${n.name}${n.ars?' ('+n.ars+')':''} · ${[...new Set(n.services.map(s=>s.route_name))].join('/')}`:n.label;
    (n.city?city:shuttle).append(new Option(label,key));
  }
  select.replaceChildren(shuttle,...(city.children.length?[city]:[]));
  if(!select.querySelector(`option[value="${state.stop}"]`))state.stop=state.policy==='city'&&state.common.hot_nodes.city_302!==undefined?'city_302':'circle_302';
  select.value=state.stop;$('chart-stop-select').innerHTML=select.innerHTML;$('chart-stop-select').value=state.stop;
}
function syncCityLines(){cityLines.clearLayers();if(state.policy!=='city')return;for(const r of state.common.city_route_lines||[])if(showVehicle(r.id))L.polyline(r.geometry,{color:r.color,weight:2.8,opacity:.55,interactive:true}).bindTooltip(`${esc(r.name)} · 서울시 노선 도형`).addTo(cityLines);}
function nodeKey(node){return Object.keys(state.common.hot_nodes).find(key=>state.common.hot_nodes[key]===node);}
function stopGroupTotals(group){return group.nodes.reduce((sum,node)=>{const [q,d]=queueAt(state.data,node,state.second);return [sum[0]+q,sum[1]+d];},[0,0]);}
function nodeCaption(node){
  const n=state.common.nodes[node];if(!n.city)return n.label;
  const routes=[...new Set(n.services.map(s=>s.route_name))].join(' / ');
  return `시내 공동 대기열 · ${routes}`;
}
function updateStopPopup(){
  if(!activeStopPopup||!state.ready)return;
  const {root,groups}=activeStopPopup;
  root.querySelector('.stop-popup-clock').textContent=`${DAYS[state.day]} ${clock(state.second)}`;
  root.querySelector('[data-snapshot-stop]').hidden=!groups[0].nodes.length;
  root.querySelector('[data-snapshot-summary]').hidden=!groups[0].nodes.length;
  root.querySelector('[data-snapshot-stop]').textContent=`선택 대기열 · ${nodeCaption(state.common.hot_nodes[state.stop])}`;
  root.querySelector('[data-snapshot-summary]').innerHTML=summaryMarkup(snapshotAt(state),{clock,fmt});
  for(const section of root.querySelectorAll('[data-group-index]')){
    const group=groups[Number(section.dataset.groupIndex)],[q,d]=stopGroupTotals(group);
    section.querySelector('[data-total-queue]').textContent=fmt(q);
    section.querySelector('[data-total-denied]').textContent=fmt(d);
  }
  for(const button of root.querySelectorAll('[data-queue-node]')){
    const node=Number(button.dataset.queueNode),[q,d]=queueAt(state.data,node,state.second);
    button.querySelector('[data-row-queue]').textContent=fmt(q);
    button.querySelector('[data-row-denied]').textContent=fmt(d);
    button.classList.toggle('is-selected',state.common.hot_nodes[state.stop]===node);
    button.setAttribute('aria-pressed',String(state.common.hot_nodes[state.stop]===node));
  }
}
function openStopPopup(group){
  if(!state.ready)return;
  map.closePopup();
  const current=state.common.hot_nodes[state.stop];
  if(group.nodes.length){state.stop=nodeKey(group.nodes.includes(current)?current:group.nodes[0]);$('stop-select').value=state.stop;selectStop(false);}
  // Nearby markers can overlap at this zoom. List them separately, without
  // merging opposite-direction or city/shuttle queues into a single count.
  const at=map.latLngToContainerPoint(group.point);
  const groups=[group,...stopGroups.filter(other=>other!==group&&map.latLngToContainerPoint(other.point).distanceTo(at)<14)];
  const root=document.createElement('div');root.className='stop-popup';
  root.innerHTML='<div class="stop-popup-clock"></div><p class="stop-popup-intro" data-snapshot-stop></p><div class="snapshot-wait" data-snapshot-summary></div>';
  groups.forEach((item,i)=>{
    const section=document.createElement('section');section.dataset.groupIndex=i;
    section.innerHTML=`${i?'<p class="nearby-stop">가까운 승차지 · 별도 대기열</p>':''}<h3>${esc(item.name)}${item.ars?` <small>${esc(item.ars)}</small>`:''}</h3><div class="stop-popup-totals"><span>대기 <strong data-total-queue>0</strong>명 상당</span><span class="stop-popup-denied">그중 만차 잔류 <strong data-total-denied>0</strong></span></div>`;
    for(const node of item.nodes){
      const button=document.createElement('button');button.type='button';button.className='stop-queue-option';button.dataset.queueNode=node;
      button.innerHTML=`<span class="stop-queue-label">${esc(nodeCaption(node))}</span><span>대기 <b data-row-queue>0</b> · 만차 <b data-row-denied>0</b><em>선택 ↗</em></span>`;
      button.addEventListener('click',()=>{state.stop=nodeKey(node);$('stop-select').value=state.stop;selectStop(false);});
      section.append(button);
    }
    if(!item.nodes.length){const note=document.createElement('p');note.className='stop-no-inflow';note.textContent=`${item.routes.join(' / ')} · 이 모형에서 학생 승차대기 유입을 배정하지 않은 정류장입니다.`;section.append(note);}
    root.append(section);
  });
  const foot=document.createElement('p');foot.className='stop-popup-footnote';foot.textContent='재생·시각 변경에 따라 갱신됩니다. 만차 잔류는 대기의 일부이며, 명 상당은 가중 통행 계산값입니다. 실제 전체 승객 수가 아닙니다.';root.append(foot);
  const popup=L.popup({className:'stop-queue-popup',maxWidth:310,minWidth:230,maxHeight:innerWidth<=700?Math.max(120,Math.min(220,map.getSize().y-330)):400,autoPanPaddingTopLeft:[14,90],autoPanPaddingBottomRight:[14,220]}).setLatLng(group.point).setContent(root);
  activeStopPopup={popup,groups,root};popup.on('remove',()=>{if(activeStopPopup?.popup===popup)activeStopPopup=null;});
  updateStopPopup();popup.openOn(map);
}
function syncStopMarkers(){
  map.closePopup();stopMarkers.clearLayers();const groups=new Map();
  function add(key,stop,city){
    if(!groups.has(key))groups.set(key,{key,name:stop.name,ars:stop.ars||'',city,point:[stop.lat,stop.lon],nodes:[],routes:[]});
    return groups.get(key);
  }
  state.common.nodes.forEach((n,node)=>{
    if(n.city&&state.policy!=='city')return;
    const group=add(`${n.city?'city':'shuttle'}|${n.stop_id}`,n,Boolean(n.city));group.nodes.push(node);
  });
  if(state.policy==='city')for(const [rid,stops] of Object.entries(state.common.city_route_stops))for(const s of stops){
    const group=add('city|'+s.id,s,true),name=routeName(rid);if(!group.routes.includes(name))group.routes.push(name);
  }
  stopGroups=[...groups.values()];
  for(const group of stopGroups){
    const icon=L.divIcon({className:`stop-map-marker ${group.city?'city-stop':'shuttle-stop'}`,html:'<span class="stop-pin-dot" aria-hidden="true"></span>',iconSize:[30,30],iconAnchor:[15,15]});
    const marker=L.marker(group.point,{icon,keyboard:true,title:`${group.name} · 정류장 대기량 보기`,riseOnHover:true});
    marker.on('add',()=>{const el=marker.getElement();el.dataset.stopGroup=group.key;el.setAttribute('role','button');el.setAttribute('aria-label',`${group.name} ${group.city?'시내버스':'셔틀'} 정류장 대기량 보기`);el.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();openStopPopup(group);}});});
    marker.on('click',()=>openStopPopup(group));
    marker.bindTooltip(()=>{const [q,d]=stopGroupTotals(group);return `${esc(group.name)} · 대기 ${fmt(q)} · 만차 잔류 ${fmt(d)}`;},{direction:'top',offset:[0,-8],className:'stop-count-tooltip'});
    marker.addTo(stopMarkers);
  }
}
function selectStop(focus=false){
  if(!state.common)return;const node=state.common.hot_nodes[state.stop],n=state.common.nodes[node];
  selectedEventRows=(state.data?.events||[]).filter(e=>e[1]===node);lastSidebarSecond=-1;
  if(selectedMarker)selectedMarker.setLatLng([n.lat,n.lon]);
  else selectedMarker=L.circleMarker([n.lat,n.lon],{radius:5,color:'#1b5a50',weight:2,fillColor:'#fff',fillOpacity:1,interactive:false}).bindTooltip(esc(n.name),{permanent:true,direction:'left',offset:[-10,0],className:'selected-stop-label'}).addTo(map);
  if(focus){map.setView([n.lat-.0008,n.lon],17,{animate:false});document.querySelectorAll('[data-focus]').forEach(b=>b.classList.toggle('active',b.dataset.focus===(state.stop.startsWith('admin')?'admin':'engineering')));}
  updateSidebar(true);if(state.pane==='charts')graphs?.render();
  if(state.data){const hasLocal=state.data.events.some(e=>e[1]===node&&e[8]>1&&e[0]>=START&&e[0]<END);$('highlight-button').textContent=hasLocal?'만차 장면으로 이동 ↗':'다른 승차지의 만차 장면 ↗';}
  const clone=$('chart-stop-select');if(clone)clone.value=state.stop;
}
function updateClock(){const value=clock(state.second);$('clock').textContent=value;$('time-input').value=value;$('time-slider').value=Math.floor(state.second);$('time-slider').setAttribute('aria-valuetext',value);$('day-label').textContent=DAYS[state.day];}
function setPlaying(value){state.playing=Boolean(value&&state.ready&&state.pane==='map');state.last=0;$('play-button').setAttribute('aria-label',state.playing?'일시정지':'재생');$('play-label').textContent=state.playing?'일시정지':'재생';$('play-symbol').textContent=state.playing?'Ⅱ':'▶';}
function selectTime(t){setPlaying(false);state.second=clamp(t);updateClock();lastSidebarSecond=-1;updateSidebar(true);draw();graphs?.updateCursor();}
async function load(scenario,day){
  return replayJson(ROOT+scenario+'-'+day+'.json');
}
async function loadSelected(){
  map.closePopup();
  clearJourney();
  rerouteOverlay.clearLayers();
  previewButton.disabled=true;
  const token=++state.request;setPlaying(false);state.ready=false;state.demand=null;$('destination-count').textContent='—';draw();$('play-button').disabled=true;$('snapshot-open').disabled=true;$('highlight-button').disabled=true;$('error-panel').hidden=true;$('loading-overlay').hidden=false;
  $('loading-label').textContent=`${DAYS[state.day]} · ${state.scenario==='peak'?'피크 최소 간격':'기준 배차'} 자료를 준비하고 있습니다.`;
  try{
    const [data,chartData,halfHours]=await Promise.all([load(state.scenario,state.day),json('data/chart_reference_v1/legacy.json'),json('map-stats.json'),commonReady]);if(token!==state.request)return;
    if(halfHours.interval_seconds!==1800)throw new Error('30-minute chart intervals are not ready');
    if(!data.queue_timeline||![2,4,5].includes(data.schema_version))throw new Error('Capacity replay schema is not ready');
    state.chartData={...chartData,half_hourly:halfHours.scenarios};
    showDemand(halfHours.runs[state.scenario][state.day],data);rerouteOverlay.clearLayers();
    state.data=data;state.ready=true;$('loading-overlay').hidden=true;$('play-button').disabled=false;$('snapshot-open').disabled=false;$('highlight-button').disabled=!data.highlights.length;
    $('scenario-note').textContent=(state.scenario==='peak'?'15~19시 셔틀 · 입구역 3분 / 순환 5분':'15~19시 셔틀 · 입구역 4분 / 순환 6분')+(state.policy==='city'?' · 시내는 공식 평일 간격':' · 이전 모형');
    if(state.supplyCorrected&&state.policy==='city')$('scenario-note').textContent+=(state.scenario==='peak'?' · 설입3분 명목 배차마다2대':' · 설입4분 명목 배차마다2대')+' · 15~19시는 적용창 가정';
    stopOptions();syncCityLines();syncStopMarkers();
    selectStop(false);updateClock();draw();
    if(token>1){
      const url=new URL(location.href);url.searchParams.set('day',state.day);url.searchParams.set('scenario',state.scenario);history.replaceState(null,'',url);
    }
    // Large web fonts can download after the replay is usable instead of
    // competing with the model on a slow connection. Final typography is unchanged.
    delete document.documentElement.dataset.replayLoading;
    performance.mark('replay-ready');
    $('switch-highlight').disabled=!(data.switches||[]).some(e=>e[0]>=START&&e[0]<END);
    $('map-switch-highlight').disabled=$('switch-highlight').disabled;
    if(state.pane==='charts')graphs.render();
  }catch(error){if(token!==state.request)return;$('loading-overlay').hidden=true;$('error-panel').hidden=false;console.error('Capacity replay load failed',error);}
}
function setMode(mode){state.mode=mode;for(const [id,on] of [['movement-view',mode==='movement'],['queue-view',mode==='queue']]){$(id).classList.toggle('active',on);$(id).setAttribute('aria-pressed',on);}draw();}
function pane(name){state.pane=name;setPlaying(false);$('map-pane').hidden=name!=='map';$('charts-pane').hidden=name!=='charts';for(const [id,on] of [['map-tab',name==='map'],['charts-tab',name==='charts']]){$(id).classList.toggle('active',on);$(id).setAttribute('aria-pressed',on);}if(name==='map'){map.invalidateSize({pan:false});sizeCanvas();}else graphs.render();document.dispatchEvent(new CustomEvent('lab:panechange',{detail:{pane:name}}));}
let graphs=createGraphs({state,load,queueAt,clock,dayName:d=>DAYS[d],selectTime,goTo:async(day,t)=>{state.day=day;$('weekday').value=day;await loadSelected();selectTime(t);pane('map');selectStop(true);}});
installSnapshotQuery({state,clock,goTo:async(day,t,stop,isOpen)=>{
  if(state.day!==day||!state.ready){state.day=day;$('weekday').value=day;await loadSelected();}
  if(!state.ready||state.day!==day||!isOpen())return false;
  if(state.common.hot_nodes[stop]===undefined)return false;
  state.stop=stop;$('stop-select').value=stop;
  selectTime(t);pane('map');selectStop(true);
  const group=stopGroups.find(group=>group.nodes.includes(state.common.hot_nodes[stop]));
  if(group)openStopPopup(group);
  return true;
}});
function highlight(){
  if(!state.ready)return;const node=state.common.hot_nodes[state.stop];
  const candidates=state.data.events.filter(e=>e[1]===node&&e[8]>1&&e[0]>=START&&e[0]<END).sort((a,b)=>b[8]-a[8]);
  const e=candidates.find(e=>e[0]>=54000&&e[0]<68400)||candidates[0]||state.data.highlights[0];if(!e)return;
  const hot=Object.entries(state.common.hot_nodes).find(([key,value])=>value===e[1]);if(hot){state.stop=hot[0];$('stop-select').value=state.stop;}
  selectTime(e[0]+1);pane('map');selectStop(true);setMode('queue');
}
function switchHighlight(){
  if(!state.ready)return;const node=state.common.hot_nodes[state.stop];
  const samples=new Map();for(const trip of state.data.trips){
    if(state.destination!=='all' && trip[2]!==state.destination)continue;
    if(!samples.has(trip[7]))samples.set(trip[7],[]);samples.get(trip[7]).push(trip);
  }
  const visibleLeg=e=>(samples.get(e[3])||[]).flatMap(t=>t[4]).find(l=>l[0]===0&&l[7]===true&&Math.abs(l[1]-e[0])<.02&&l[2]-l[1]>.1);
  // Some small weighted flows have no displayed dot. Highlight an actual
  // rendered flow so the scene always contains the announced walking action.
  const all=(state.data.switches||[]).filter(e=>e[0]>=START&&e[0]<END&&visibleLeg(e));
  const local=all.filter(e=>e[1]===node);const candidates=local.length?local:all;
  const e=candidates.find(e=>e[5]==='gate_pool'&&e[0]>=54000)||candidates.find(e=>e[5]==='gate_pool')||candidates.find(e=>e[0]>=54000)||candidates[0];if(!e)return;
  const hot=Object.entries(state.common.hot_nodes).find(([k,v])=>v===e[1]);if(hot){state.stop=hot[0];$('stop-select').value=state.stop;}
  const leg=visibleLeg(e);selectTime(e[0]+Math.min(5,(leg[2]-leg[1])/2));pane('map');selectStop(false);setMode('movement');rerouteOverlay.clearLayers();
  const n=state.common.nodes[e[1]];
  if(leg){const path=state.common.paths[leg[3]];L.polyline(path,{color:'#008dac',weight:4,opacity:.8}).addTo(rerouteOverlay);map.fitBounds(path,{padding:[70,100],maxZoom:17,animate:false});}
  else map.setView([n.lat,n.lon],16,{animate:false});
  $('switch-detail').textContent=`${clock(e[0])} · ${n.name} · ${e[6]} · 예상 ${e[7]===null?'운행 없음':fmt((e[7]-e[0])/60)+'분'} → ${fmt((e[8]-e[0])/60)}분`;
}
function geographyInit(){
  if(state.common.bus_speed_model?.campus_polygon)L.polygon(state.common.bus_speed_model.campus_polygon,{weight:1,color:'#659279',dashArray:'5 6',fill:false,opacity:.6,interactive:false}).addTo(geography);
  for(const r of state.common.route_lines)L.polyline(r.geometry,{weight:2.5,color:'#9daf9f',opacity:.3,interactive:false}).addTo(geography);
  for(const b of state.common.footprints)L.polygon(b.polygon,{weight:.6,color:'#adbaad',fillColor:'#e5eadf',fillOpacity:.4,interactive:false}).addTo(geography);
  const add=(p,label)=>L.circleMarker(p,{radius:3,color:'#43685b',weight:1,fillColor:'#fff',fillOpacity:1}).bindTooltip(esc(label),{permanent:true,direction:'top',offset:[0,-6],className:'landmark-label'}).addTo(labels);
  const by=Object.fromEntries(state.common.buildings.map(b=>[b.id,b]));
  for(const [id,label] of [['302','302동'],['301','301동'],['38','38동'],['200','농생대'],['500','자연대']])if(by[id])add([by[id].lat,by[id].lon],label);
  const n=state.common.nodes[state.common.hot_nodes.admin_snu];add([n.lat,n.lon],'행정관');
  for(const [key,label] of Object.entries(landmarks)){
    const marker=add(state.common.destinations[key],label);
    marker.on('click',()=>{
      destinationSelect.value=key.startsWith('dorm_')?'dorm':key;
      destinationSelect.dispatchEvent(new Event('change'));
    });
  }
  if(state.common.gate_pool)add(state.common.gate_pool.point,'서울대학교 21128 · 5개 노선');
  focusMap('all');sizeCanvas();
}
const chartStopLabel=document.createElement('label');chartStopLabel.className='field chart-stop-field';chartStopLabel.textContent='그래프 승차지';
const chartStop=$('stop-select').cloneNode(true);chartStop.id='chart-stop-select';chartStopLabel.append(chartStop);document.querySelector('.chart-intro').append(chartStopLabel);
chartStop.addEventListener('change',e=>{map.closePopup();state.stop=e.target.value;$('stop-select').value=state.stop;selectStop(false);});
const mobileHighlight=document.createElement('button');mobileHighlight.id='map-highlight';mobileHighlight.textContent='만차 장면';mobileHighlight.addEventListener('click',highlight);document.querySelector('.map-tools').append(mobileHighlight);
const mobileSwitch=document.createElement('button');mobileSwitch.id='map-switch-highlight';mobileSwitch.textContent='경로 변경';mobileSwitch.disabled=true;mobileSwitch.addEventListener('click',switchHighlight);document.querySelector('.map-tools').append(mobileSwitch);
$('scenario').addEventListener('change',e=>{state.scenario=e.target.value;loadSelected();});$('weekday').addEventListener('change',e=>{state.day=e.target.value;loadSelected();});
$('vehicle-filter').addEventListener('change',e=>{state.vehicleFilter=e.target.value;syncCityLines();draw();});
$('switch-highlight').addEventListener('click',switchHighlight);
$('stop-select').addEventListener('change',e=>{map.closePopup();state.stop=e.target.value;selectStop(state.pane==='map');});
$('map-tab').addEventListener('click',()=>pane('map'));$('charts-tab').addEventListener('click',()=>pane('charts'));
$('movement-view').addEventListener('click',()=>setMode('movement'));$('queue-view').addEventListener('click',()=>setMode('queue'));
$('highlight-button').addEventListener('click',highlight);$('time-slider').addEventListener('input',e=>selectTime(Number(e.target.value)));
$('time-input').addEventListener('focus',()=>setPlaying(false));$('time-input').addEventListener('change',e=>{const a=e.target.value.split(':').map(Number);if(a.length>=2&&a.every(Number.isFinite))selectTime(a[0]*3600+a[1]*60+(a[2]||0));});
$('play-button').addEventListener('click',()=>{if(state.second>=END)state.second=START;setPlaying(!state.playing);});$('speed').addEventListener('change',e=>state.speed=Number(e.target.value));
$('back-button').addEventListener('click',()=>selectTime(state.second-60));$('forward-button').addEventListener('click',()=>selectTime(state.second+60));
$('about-button').addEventListener('click',()=>{renderPlans();$('about-dialog').showModal();});$('retry-button').addEventListener('click',()=>location.reload());
document.querySelectorAll('[data-focus]').forEach(b=>b.addEventListener('click',()=>focusMap(b.dataset.focus)));
map.on('move zoom resize',sizeCanvas);new ResizeObserver(()=>{if(state.pane==='map'){map.invalidateSize({pan:false});sizeCanvas();}}).observe($('map'));
document.addEventListener('visibilitychange',()=>{if(document.hidden)setPlaying(false);});
function frame(timestamp){if(state.playing){if(state.last)state.second=clamp(state.second+Math.max(0,(timestamp-state.last)/1000)*state.speed);state.last=timestamp;if(state.second>=END)setPlaying(false);updateClock();draw();}requestAnimationFrame(frame);}
async function start(){
  try{commonReady=json(ROOT+'common.json').then(common=>{
    if(common.candidate_id!==MODEL || !common.destinations?.gwanaksan_4411) throw new Error('통합 R 공용 지도를 확인해 주세요.');
    state.common=common;
    state.common.nodes.forEach((n,node)=>{if(nodeKey(node)===undefined)state.common.hot_nodes['node_'+node]=node;});
    for(const r of state.common.city_services)$('vehicle-filter').append(new Option(r.name,r.route_id));
    geographyInit();
  });
    // Common geography and the selected replay/stats start together; there is
    // no second network wave waiting for the full common payload to be parsed.
    await loadSelected();
    // Start the ordinary current-time view at real-time speed once data is ready.
    // Explicit links, fallback dates and selections made during loading stay paused.
    if(state.ready&&state.request===1&&state.pane==='map'&&state.day===initialClock.day&&state.second===initialClock.second&&state.speed===1&&!initialClock.daySpecified&&!initialClock.timeSpecified&&!initialClock.requiresNotice){
      const current=initialReplayClock(new Date(),location.search);
      if(current.day===state.day&&!current.requiresNotice&&current.second<END){
        $('speed').value='1';selectTime(current.second);setPlaying(true);
      }
    }
    requestAnimationFrame(frame);}
  catch(error){$('loading-overlay').hidden=true;$('error-panel').hidden=false;console.error('Capacity viewer initialization failed',error);}
}
installMobileLab({map,getState:()=>state,setPane:pane});
updateClock();start();
function renderPlans(){
  const box=$('city-plan-table');if(!box||!state.common)return;
  box.innerHTML='<table class="metrics-table"><thead><tr><th>노선</th><th>기점</th><th>평일 기점 출발</th><th>간격</th><th>승객 참고정원</th></tr></thead><tbody>'+state.common.city_services.map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(r.official_origin)}</td><td>${esc(r.weekday_hours)}</td><td>${r.headway_minutes}분</td><td>${r.passenger_capacity}명</td></tr>`).join('')+'</tbody></table>';
}
