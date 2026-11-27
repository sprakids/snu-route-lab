import {createGraphs} from './graphs-v2.js';
import {motionAt} from './bus-motion.js';
const $=id=>document.getElementById(id),ROOT='data/capacity_v3/';
const DAYS={mon:'월요일',tue:'화요일',wed:'수요일',thu:'목요일',fri:'금요일'};
const COLORS=['#3e947b','#d89a42','#547db1','#8b6abd'],RED='#c85645',START=40800,END=83400;
const state={day:'mon',scenario:'peak',stop:'circle_302',mode:'movement',pane:'map',second:55500,speed:1,playing:false,last:0,ready:false,common:null,data:null,chartData:null,request:0};
const cache=new Map(),pathCache=new Map();let selectedMarker=null,selectedEventRows=[],lastSidebarSecond=-1;
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(n);
const clamp=t=>Math.max(START,Math.min(END,t));
const clock=t=>{const n=Math.floor(t);return `${String(Math.floor(n/3600)).padStart(2,'0')}:${String(Math.floor(n/60)%60).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;};
const params=new URLSearchParams(location.search);
if(DAYS[params.get('day')])state.day=params.get('day');
if(['regular','peak'].includes(params.get('scenario')))state.scenario=params.get('scenario');
if(params.has('second')&&Number.isFinite(Number(params.get('second'))))state.second=clamp(Number(params.get('second')));
else if(params.has('minute')&&Number.isFinite(Number(params.get('minute'))))state.second=clamp(Number(params.get('minute'))*60);
$('weekday').value=state.day;$('scenario').value=state.scenario;
const map=L.map('map',{zoomControl:false,preferCanvas:true,minZoom:13,maxZoom:19}).setView([37.451,126.952],16);
L.control.zoom({position:'topright'}).addTo(map);map.attributionControl.setPrefix(false);
map.attributionControl.addAttribution('<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap 기여자</a>');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,keepBuffer:1,updateWhenIdle:true}).addTo(map);
const geography=L.layerGroup().addTo(map),labels=L.layerGroup().addTo(map);
const canvas=document.createElement('canvas');canvas.className='people-canvas';canvas.setAttribute('aria-hidden','true');map.getContainer().append(canvas);const ctx=canvas.getContext('2d');
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
  const m=motionAt(profile,elapsed),p=preparedPath(id);
  return {point:position(id,p.total?m.distance/p.total:0),kmh:m.speed*3.6};
}
function latest(rows,t,column=0){let lo=0,hi=rows.length;while(lo<hi){const m=(lo+hi)>>1;if(rows[m][column]<=t)lo=m+1;else hi=m;}return lo-1;}
function activeLeg(legs,t){const i=latest(legs,t,1);return i>=0&&t<legs[i][2]?legs[i]:null;}
export function queueAt(data,node,t){const rows=data.queue_timeline[node],i=latest(rows,t);return i<0?[0,0]:[rows[i][1],rows[i][2]];}
function sizeCanvas(){const s=map.getSize(),d=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(s.x*d);canvas.height=Math.round(s.y*d);canvas.style.width=s.x+'px';canvas.style.height=s.y+'px';ctx.setTransform(d,0,0,d,0,0);draw();}
function focusMap(area){
  const bounds={all:[[37.445,126.933],[37.4825,126.9705]],engineering:[[37.447,126.9478],[37.4548,126.956]],admin:[[37.4558,126.9448],[37.466,126.9565]]};
  map.fitBounds(bounds[area],{paddingTopLeft:[22,65],paddingBottomRight:[22,innerWidth<=700?205:225],maxZoom:area==='all'?15:17,animate:false});
  document.querySelectorAll('[data-focus]').forEach(b=>b.classList.toggle('active',b.dataset.focus===area));
}
function dot(point,r,color,alpha=.9){
  const p=map.latLngToContainerPoint(point),s=map.getSize();if(p.x<-15||p.y<-15||p.x>s.x+15||p.y>s.y+15)return;
  ctx.globalAlpha=alpha;ctx.beginPath();ctx.arc(p.x,p.y,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();
}
function drawBus(point,load,capacity,kmh,offset=0){
  const p=map.latLngToContainerPoint(point),s=map.getSize();if(p.x<0||p.x>s.x||p.y<0||p.y>s.y)return;
  p.y+=offset;
  const text=`${fmt(load)}/${capacity}`;ctx.globalAlpha=.97;ctx.font="600 10px 'Malgun Gothic',sans-serif";const w=ctx.measureText(text).width+12;
  ctx.fillStyle=load>=capacity-.01?RED:'#365b65';ctx.beginPath();ctx.roundRect(p.x-w/2,p.y-12,w,30,5);ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.stroke();ctx.fillStyle='#fff';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,p.x,p.y-3);ctx.font="8px 'Malgun Gothic',sans-serif";ctx.fillText(kmh<.5?'정차':`${Math.round(kmh)} km/h`,p.x,p.y+10);
}
function draw(){
  const s=map.getSize();ctx.clearRect(0,0,s.x,s.y);if(!state.ready||!state.data||state.pane!=='map')return;
  const t=state.second,busPositions=new Map(),buses=[];
  for(const v of state.data.vehicles){const legs=v[3],i=latest(legs,t),leg=i>=0?legs[i]:null;if(!leg||t>=leg[1])continue;const motion=busMotion(leg[2],t-leg[0],leg[1]-leg[0]);busPositions.set(v[0],motion.point);buses.push([motion.point,leg[3],v[2],motion.kmh]);}
  const waiting=new Map();let count=0,redCount=0;
  for(const trip of state.data.trips){
    const [identity,building,dest,weight,legs]=trip,leg=activeLeg(legs,t);if(!leg)continue;
    const [kind,a,b,pid,node,denied,vehicle]=leg;
    if(kind===1&&node>=0){if(!waiting.has(node))waiting.set(node,[]);waiting.get(node).push([trip,leg]);continue;}
    if(state.mode==='queue')continue;
    const p=kind===3&&busPositions.has(vehicle)?busPositions.get(vehicle):kind===2||kind===3?busMotion(pid,t-a,b-a).point:position(pid,(t-a)/(b-a));
    const jitter=kind===1?.00002:.000006;
    dot([p[0]+((identity%17)/16-.5)*jitter,p[1]+(((identity>>>5)%17)/16-.5)*jitter],kind===1?2.5:2.1,COLORS[kind]);count++;
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
  for(const group of groups.values())group.forEach((bus,i)=>drawBus(...bus,(i-(group.length-1)/2)*33));ctx.globalAlpha=1;
  $('map-status').textContent=`이동 표본 ${count.toLocaleString('ko-KR')}개 · 만차 잔류 표본 ${redCount}개 · 모형 셔틀 ${buses.length}대`;
  canvas.dataset.mode=state.mode;canvas.dataset.second=t.toFixed(3);canvas.dataset.deniedDots=redCount;canvas.dataset.sampleDots=count;canvas.dataset.maxShuttleKmh=Math.max(0,...buses.map(b=>b[3])).toFixed(3);
  updateSidebar();
}
function updateSidebar(force=false){
  if(!state.ready)return;const integer=Math.floor(state.second);if(!force&&integer===lastSidebarSecond)return;lastSidebarSecond=integer;
  const node=state.common.hot_nodes[state.stop],n=state.common.nodes[node],[q,d]=queueAt(state.data,node,state.second);
  $('stop-queue').textContent=fmt(q);$('stop-denied').textContent=fmt(d);
  const index=latest(selectedEventRows,state.second),previous=selectedEventRows[index],next=selectedEventRows[index+1];
  const nextGroup=next?selectedEventRows.filter(e=>e[0]===next[0]):[];
  const previousGroup=previous?selectedEventRows.filter(e=>e[0]===previous[0]):[];
  $('next-bus').textContent=next?`다음 셔틀 ${clock(next[0])} · ${next[3]}명${nextGroup.length>1?` × ${nextGroup.length}대`:''}`:'이 노선의 남은 운행이 없습니다.';
  $('last-bus').textContent=previous?`직전 ${clock(previous[0])} · 탑승 ${fmt(previousGroup.reduce((sum,e)=>sum+e[6],0))} · 준비 후 잔류 ${fmt(previous[8])}`:'현재 시각 이전 정차가 없습니다.';
  if(selectedMarker)selectedMarker.setTooltipContent(`${esc(n.name)} · ${state.stop.startsWith('admin')?esc($('stop-select').selectedOptions[0].textContent.split('→')[1]?.trim()||''):state.stop.startsWith('reverse')?'역순환':'순환'}<br>대기 ${fmt(q)} · 만차 잔류 ${fmt(d)}`);
}
function selectStop(focus=false){
  if(!state.common)return;const node=state.common.hot_nodes[state.stop],n=state.common.nodes[node];
  selectedEventRows=(state.data?.events||[]).filter(e=>e[1]===node);lastSidebarSecond=-1;
  if(selectedMarker)selectedMarker.setLatLng([n.lat,n.lon]);
  else selectedMarker=L.circleMarker([n.lat,n.lon],{radius:5,color:'#1b5a50',weight:2,fillColor:'#fff',fillOpacity:1}).bindTooltip(esc(n.name),{permanent:true,direction:'left',offset:[-10,0],className:'selected-stop-label'}).addTo(map);
  if(focus){map.setView([n.lat-.0008,n.lon],17,{animate:false});document.querySelectorAll('[data-focus]').forEach(b=>b.classList.toggle('active',b.dataset.focus===(state.stop.startsWith('admin')?'admin':'engineering')));}
  updateSidebar(true);if(state.pane==='charts')graphs?.render();
  if(state.data){const hasLocal=state.data.events.some(e=>e[1]===node&&e[8]>1&&e[0]>=START&&e[0]<END);$('highlight-button').textContent=hasLocal?'만차 장면으로 이동 ↗':'다른 승차지의 만차 장면 ↗';}
  const clone=$('chart-stop-select');if(clone)clone.value=state.stop;
}
function updateClock(){const value=clock(state.second);$('clock').textContent=value;$('time-input').value=value;$('time-slider').value=Math.floor(state.second);$('time-slider').setAttribute('aria-valuetext',value);$('day-label').textContent=DAYS[state.day];}
function setPlaying(value){state.playing=Boolean(value&&state.ready&&state.pane==='map');state.last=0;$('play-button').setAttribute('aria-label',state.playing?'일시정지':'재생');$('play-label').textContent=state.playing?'일시정지':'재생';$('play-symbol').textContent=state.playing?'Ⅱ':'▶';}
function selectTime(t){setPlaying(false);state.second=clamp(t);updateClock();lastSidebarSecond=-1;updateSidebar(true);draw();graphs?.updateCursor();}
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`Replay data ${r.status}`);return r.json();}
async function load(scenario,day){
  const key=`${scenario}-${day}`;if(!cache.has(key))cache.set(key,json(ROOT+key+'.json').catch(e=>{cache.delete(key);throw e;}));return cache.get(key);
}
async function loadSelected(){
  const token=++state.request;setPlaying(false);state.ready=false;$('play-button').disabled=true;$('highlight-button').disabled=true;$('error-panel').hidden=true;$('loading-overlay').hidden=false;
  $('loading-label').textContent=`${DAYS[state.day]} · ${state.scenario==='peak'?'피크 최소 간격':'기준 배차'} 자료를 준비하고 있습니다.`;
  try{
    const data=await load(state.scenario,state.day);if(token!==state.request)return;
    if(!data.queue_timeline||data.schema_version!==2)throw new Error('Capacity replay schema is not ready');
    state.data=data;state.ready=true;$('loading-overlay').hidden=true;$('play-button').disabled=false;$('highlight-button').disabled=!data.highlights.length;
    $('scenario-note').textContent=state.scenario==='peak'?'15~19시 · 입구역 3분 / 순환 5분':'15~19시 · 입구역 4분 / 순환 6분';
    selectStop(false);updateClock();draw();
  }catch(error){if(token!==state.request)return;$('loading-overlay').hidden=true;$('error-panel').hidden=false;console.error('Capacity replay load failed',error);}
}
function setMode(mode){state.mode=mode;for(const [id,on] of [['movement-view',mode==='movement'],['queue-view',mode==='queue']]){$(id).classList.toggle('active',on);$(id).setAttribute('aria-pressed',on);}draw();}
function pane(name){state.pane=name;setPlaying(false);$('map-pane').hidden=name!=='map';$('charts-pane').hidden=name!=='charts';for(const [id,on] of [['map-tab',name==='map'],['charts-tab',name==='charts']]){$(id).classList.toggle('active',on);$(id).setAttribute('aria-pressed',on);}if(name==='map'){map.invalidateSize({pan:false});sizeCanvas();}else graphs.render();}
let graphs=createGraphs({state,load,queueAt,clock,dayName:d=>DAYS[d],selectTime,goTo:async(day,t)=>{state.day=day;$('weekday').value=day;await loadSelected();selectTime(t);pane('map');selectStop(true);}});
function highlight(){
  if(!state.ready)return;const node=state.common.hot_nodes[state.stop];
  const candidates=state.data.events.filter(e=>e[1]===node&&e[8]>1&&e[0]>=START&&e[0]<END).sort((a,b)=>b[8]-a[8]);
  const e=candidates.find(e=>e[0]>=54000&&e[0]<68400)||candidates[0]||state.data.highlights[0];if(!e)return;
  const hot=Object.entries(state.common.hot_nodes).find(([key,value])=>value===e[1]);if(hot){state.stop=hot[0];$('stop-select').value=state.stop;}
  selectTime(e[0]+1);pane('map');selectStop(true);setMode('queue');
}
function geographyInit(){
  if(state.common.bus_speed_model?.campus_polygon)L.polygon(state.common.bus_speed_model.campus_polygon,{weight:1,color:'#659279',dashArray:'5 6',fill:false,opacity:.6,interactive:false}).addTo(geography);
  for(const r of state.common.route_lines)L.polyline(r.geometry,{weight:2.5,color:'#9daf9f',opacity:.3,interactive:false}).addTo(geography);
  for(const b of state.common.footprints)L.polygon(b.polygon,{weight:.6,color:'#adbaad',fillColor:'#e5eadf',fillOpacity:.4,interactive:false}).addTo(geography);
  const add=(p,label)=>L.circleMarker(p,{radius:3,color:'#43685b',weight:1,fillColor:'#fff',fillOpacity:1}).bindTooltip(esc(label),{permanent:true,direction:'top',offset:[0,-6],className:'landmark-label'}).addTo(labels);
  const by=Object.fromEntries(state.common.buildings.map(b=>[b.id,b]));
  for(const [id,label] of [['302','302동'],['301','301동'],['38','38동'],['200','농생대'],['500','자연대']])if(by[id])add([by[id].lat,by[id].lon],label);
  const n=state.common.nodes[state.common.hot_nodes.admin_snu];add([n.lat,n.lon],'행정관');
  for(const [key,label] of [['snu','서울대입구역'],['nak','낙성대역'],['daehak','대학동']])add(state.common.destinations[key],label);
  focusMap('engineering');sizeCanvas();
}
const chartStopLabel=document.createElement('label');chartStopLabel.className='field chart-stop-field';chartStopLabel.textContent='그래프 승차지';
const chartStop=$('stop-select').cloneNode(true);chartStop.id='chart-stop-select';chartStopLabel.append(chartStop);document.querySelector('.chart-intro').append(chartStopLabel);
chartStop.addEventListener('change',e=>{state.stop=e.target.value;$('stop-select').value=state.stop;selectStop(false);});
const mobileHighlight=document.createElement('button');mobileHighlight.id='map-highlight';mobileHighlight.textContent='만차 장면';mobileHighlight.addEventListener('click',highlight);document.querySelector('.map-tools').append(mobileHighlight);
$('scenario').addEventListener('change',e=>{state.scenario=e.target.value;loadSelected();});$('weekday').addEventListener('change',e=>{state.day=e.target.value;loadSelected();});
$('stop-select').addEventListener('change',e=>{state.stop=e.target.value;selectStop(state.pane==='map');});
$('map-tab').addEventListener('click',()=>pane('map'));$('charts-tab').addEventListener('click',()=>pane('charts'));
$('movement-view').addEventListener('click',()=>setMode('movement'));$('queue-view').addEventListener('click',()=>setMode('queue'));
$('highlight-button').addEventListener('click',highlight);$('time-slider').addEventListener('input',e=>selectTime(Number(e.target.value)));
$('time-input').addEventListener('focus',()=>setPlaying(false));$('time-input').addEventListener('change',e=>{const a=e.target.value.split(':').map(Number);if(a.length>=2&&a.every(Number.isFinite))selectTime(a[0]*3600+a[1]*60+(a[2]||0));});
$('play-button').addEventListener('click',()=>{if(state.second>=END)state.second=START;setPlaying(!state.playing);});$('speed').addEventListener('change',e=>state.speed=Number(e.target.value));
$('back-button').addEventListener('click',()=>selectTime(state.second-60));$('forward-button').addEventListener('click',()=>selectTime(state.second+60));
$('about-button').addEventListener('click',()=>$('about-dialog').showModal());$('retry-button').addEventListener('click',()=>location.reload());
document.querySelectorAll('[data-focus]').forEach(b=>b.addEventListener('click',()=>focusMap(b.dataset.focus)));
map.on('move zoom resize',sizeCanvas);new ResizeObserver(()=>{if(state.pane==='map'){map.invalidateSize({pan:false});sizeCanvas();}}).observe($('map'));
document.addEventListener('visibilitychange',()=>{if(document.hidden)setPlaying(false);});
function frame(timestamp){if(state.playing){if(state.last)state.second=clamp(state.second+Math.max(0,(timestamp-state.last)/1000)*state.speed);state.last=timestamp;if(state.second>=END)setPlaying(false);updateClock();draw();}requestAnimationFrame(frame);}
async function start(){
  try{[state.common,state.chartData]=await Promise.all([json(ROOT+'common.json'),json(ROOT+'charts.json')]);geographyInit();await loadSelected();requestAnimationFrame(frame);}
  catch(error){$('loading-overlay').hidden=true;$('error-panel').hidden=false;console.error('Capacity viewer initialization failed',error);}
}
updateClock();start();
