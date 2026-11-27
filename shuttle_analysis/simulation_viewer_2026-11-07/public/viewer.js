const $ = id => document.getElementById(id);
const DAYS = {mon:'월요일',tue:'화요일',wed:'수요일',thu:'목요일',fri:'금요일'};
const COLORS = ['#3e947b','#d89a42','#547db1','#8b6abd'];
const START = 680, END = 1390;
const state = {day:'mon',mode:'movement',minute:925,speed:5,playing:false,ready:false,common:null,data:null,request:0,last:0,frame:0};
const cache = new Map();
const escape = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock = minute => `${String(Math.floor(minute/60)).padStart(2,'0')}:${String(Math.floor(minute%60)).padStart(2,'0')}`;
const clamp = value => Math.max(START,Math.min(END,value));
const format = value => new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(value);

const params = new URLSearchParams(location.search);
if (params.has('day') && DAYS[params.get('day')]) state.day=params.get('day');
if (params.has('minute') && Number.isFinite(Number(params.get('minute')))) state.minute=clamp(Number(params.get('minute')));
if (params.get('view')==='queue') state.mode='queue';
$('weekday').value=state.day;

const map=L.map('map',{zoomControl:false,preferCanvas:true,minZoom:13,maxZoom:19}).setView([37.4609,126.9507],15);
L.control.zoom({position:'topright'}).addTo(map);
map.attributionControl.setPrefix(false);
map.attributionControl.addAttribution('<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap 기여자</a>');
const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,keepBuffer:1,updateWhenIdle:true}).addTo(map);
let tileFailed=false;
tiles.on('tileerror',()=>{tileFailed=true;});
const background=L.layerGroup().addTo(map);
const labels=L.layerGroup().addTo(map);
const queueLabels=L.layerGroup();
const canvas=document.createElement('canvas');canvas.className='people-canvas';canvas.setAttribute('aria-hidden','true');map.getContainer().append(canvas);
const ctx=canvas.getContext('2d');
const pathCache=new Map();
let labelsCreated=false;
let queueMarkers=[];

function metres(a,b){const r=Math.PI/180;return Math.hypot((b[1]-a[1])*r*Math.cos((a[0]+b[0])/2*r),(b[0]-a[0])*r)*6371000;}
function preparedPath(id){
  if(pathCache.has(id))return pathCache.get(id);
  const points=state.common.paths[id];const distances=new Float64Array(points.length);
  for(let i=1;i<points.length;i++)distances[i]=distances[i-1]+metres(points[i-1],points[i]);
  const path={points,distances,total:distances.at(-1)||0};pathCache.set(id,path);return path;
}
function position(id,progress){
  const p=preparedPath(id);if(p.points.length===1||!p.total)return p.points[0];
  const at=Math.max(0,Math.min(1,progress))*p.total;let lo=0,hi=p.points.length-1;
  while(lo+1<hi){const m=(lo+hi)>>1;if(p.distances[m]<at)lo=m;else hi=m;}
  const delta=p.distances[hi]-p.distances[lo];const f=delta?(at-p.distances[lo])/delta:0;
  return [p.points[lo][0]+(p.points[hi][0]-p.points[lo][0])*f,p.points[lo][1]+(p.points[hi][1]-p.points[lo][1])*f];
}
function sizeCanvas(){const s=map.getSize(),dpr=Math.min(window.devicePixelRatio||1,2);canvas.width=Math.round(s.x*dpr);canvas.height=Math.round(s.y*dpr);canvas.style.width=s.x+'px';canvas.style.height=s.y+'px';ctx.setTransform(dpr,0,0,dpr,0,0);draw();}
function focusMap(area){
  const bounds={all:[[37.445,126.933],[37.4825,126.9705]],engineering:[[37.447,126.9478],[37.4548,126.956]],admin:[[37.4558,126.9448],[37.466,126.9565]]};
  const mobile=innerWidth<=650;
  map.fitBounds(bounds[area],{paddingTopLeft:[24,65],paddingBottomRight:[24,mobile?205:225],maxZoom:area==='all'?15:17,animate:false});
  document.querySelectorAll('[data-focus]').forEach(b=>b.classList.toggle('is-active',b.dataset.focus===area));
}
function drawDot(point,radius,color,alpha=1){
  const p=map.latLngToContainerPoint(point),s=map.getSize();if(p.x<-10||p.y<-10||p.x>s.x+10||p.y>s.y+10)return;
  ctx.globalAlpha=alpha;ctx.beginPath();ctx.arc(p.x,p.y,radius,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();
}
function sampleQueues(second){
  const f=Math.max(0,Math.min(state.data.queues.length-1,(second-state.common.start_second)/state.data.queue_step_seconds));
  const a=Math.floor(f),b=Math.min(a+1,state.data.queues.length-1),t=f-a;
  return state.data.queues[a].map((v,i)=>v*(1-t)+state.data.queues[b][i]*t);
}
function draw(){
  const s=map.getSize();ctx.clearRect(0,0,s.x,s.y);if(!state.ready||!state.data)return;
  const second=state.minute*60;let count=0;const counts=[0,0,0,0];
  if(state.mode==='movement'){
    for(const [id,building,destination,weight,legs] of state.data.trips){
      if(second<legs[0][1]||second>=legs.at(-1)[2])continue;
      const leg=legs.find(v=>v[1]<=second&&second<v[2]);if(!leg)continue;
      const [kind,a,b,pathid]=leg;const p=position(pathid,(second-a)/(b-a));
      const jitter=kind===1?0.000009:0.000004;
      const q=[p[0]+(((id%13)/12)-.5)*jitter,p[1]+((((id>>>5)%13)/12)-.5)*jitter];
      drawDot(q,kind===1?2.8:2.1+Math.min(1.2,Math.sqrt(weight/2)*.35),COLORS[kind],.85);
      count++;counts[kind]++;
    }
    $('point-count').textContent=`${count.toLocaleString('ko-KR')}개`;
    $('map-status').textContent=`도보 ${counts[0]} · 대기 ${counts[1]} · 시내 ${counts[2]} · 셔틀 ${counts[3]}${tileFailed?' · 저장된 지도 도형 표시':''}`;
  }else{
    const quantities=sampleQueues(second);
    const bin=Math.max(0,Math.min(state.data.waits.length-1,Math.floor((state.minute-START)/5)));
    quantities.forEach((quantity,i)=>{
      const node=state.common.nodes[i],points=Math.ceil(quantity/2);count+=points;
      // Illustrative queue placement near each stop, not measured locations of people.
      const side=i===0?-1:i===1?1:i%2?-1:1;
      for(let k=0;k<Math.min(points,500);k++){
        const row=Math.floor(k/4),column=k%4;
        const pos=[node.lat+(row*.000019+.000018)*side,node.lon+(column-1.5)*.000021+(i===1?.000055:0)];
        const alpha=k===points-1?Math.max(.25,(quantity/2)%1||1):1;
        drawDot(pos,2.7,COLORS[1],alpha*.92);
      }
      const label=$(`queue-number-${i}`);if(label)label.textContent=format(quantity);
      const wait=$(`queue-wait-${i}`);const w=state.data.waits[bin][i];if(wait)wait.textContent=w===null?'해당 도착량 없음':`이때 도착 평균 ${format(w)}분`;
      queueMarkers[i].setTooltipContent(`${escape(node.label)}<br>모형 대기 ${format(quantity)}`);
    });
    $('point-count').textContent=`${format(quantities.reduce((a,b)=>a+b,0))} 상당`;
    $('map-status').textContent='평균 유입 · 20개 출발시각 경우의 평균 대기열';
  }
  ctx.globalAlpha=1;canvas.dataset.visibleDots=String(count);canvas.dataset.mode=state.mode;canvas.dataset.minute=state.minute.toFixed(2);
}
function updateClock(){
  const value=clock(state.minute);$('clock').textContent=value;$('time-input').value=value;
  $('time-slider').value=String(Math.floor(state.minute));$('time-slider').setAttribute('aria-valuetext',`${Math.floor(state.minute/60)}시 ${Math.floor(state.minute%60)}분`);
  $('day-label').textContent=DAYS[state.day];
}
function setPlaying(value){
  state.playing=Boolean(value&&state.ready);state.last=0;
  $('play-button').setAttribute('aria-label',state.playing?'일시정지':'재생');$('play-label').textContent=state.playing?'일시정지':'재생';
  document.querySelector('.play-icon').toggleAttribute('hidden',state.playing);document.querySelector('.pause-icon').toggleAttribute('hidden',!state.playing);
}
function selectTime(value){setPlaying(false);state.minute=clamp(value);updateClock();draw();}
function setMode(mode){
  state.mode=mode;
  const movement=mode==='movement';
  $('movement-view').classList.toggle('is-active',movement);$('queue-view').classList.toggle('is-active',!movement);
  $('movement-view').setAttribute('aria-pressed',String(movement));$('queue-view').setAttribute('aria-pressed',String(!movement));
  $('movement-legend').hidden=!movement;$('queue-legend').hidden=movement;$('queue-panel').hidden=movement;
  $('mode-note').textContent=movement?'모형 재생 · 대표 1회(정원 반영 전) · 실제 GPS 아님':'평균 유입 대기열 · 대형 60명/소형 25명 가정 · 실측 아님';
  $('summary-label').textContent=movement?'현재 시각의 이동 표본':'주요 6개 승차지의 모형 대기량';
  $('sample-note').textContent=movement?'점은 약 2명 상당의 모형 이동량을 대표하는 가중 표본입니다.':'점 1개 ≈ 가중치 2 · 기존 탑승객과 수업 외 이동은 미반영입니다.';
  if(movement){map.removeLayer(queueLabels);if(!map.hasLayer(labels))labels.addTo(map);}else{queueLabels.addTo(map);map.removeLayer(labels);}
  draw();
}
async function getJSON(url){const response=await fetch(url);if(!response.ok)throw new Error(`자료 응답 ${response.status}`);return response.json();}
async function loadDay(day){
  const request=++state.request;setPlaying(false);state.ready=false;$('play-button').disabled=true;$('error-panel').hidden=true;$('loading-overlay').hidden=false;
  $('loading-label').textContent=`${DAYS[day]}의 이동을 준비하고 있습니다.`;draw();
  try{
    if(!cache.has(day))cache.set(day,getJSON(`data/${day}.json`));
    const data=await cache.get(day);if(request!==state.request)return;
    if(!Array.isArray(data.trips)||!Array.isArray(data.queues))throw new Error('재생자료 형식을 확인할 수 없습니다.');
    state.day=day;state.data=data;state.ready=true;$('loading-overlay').hidden=true;$('play-button').disabled=false;updateClock();setMode(state.mode);draw();
  }catch(error){
    if(request!==state.request)return;cache.delete(day);$('loading-overlay').hidden=true;$('error-panel').hidden=false;$('error-message').textContent='로컬 재생 서버가 실행 중인지 확인한 뒤 다시 불러오세요.';console.error('Replay data load failed',error);
  }
}
function addLandmark(point,label){L.circleMarker(point,{radius:3,color:'#43685b',weight:1,fillColor:'#fff',fillOpacity:1}).bindTooltip(escape(label),{permanent:true,direction:'top',offset:[0,-6],className:'landmark-label'}).addTo(labels);}
function initializeGeography(){
  const c=state.common;
  for(const r of c.route_lines)L.polyline(r.geometry,{weight:2.5,color:'#a3b4ac',opacity:.38,interactive:false}).addTo(background);
  for(const b of c.footprints)L.polygon(b.polygon,{weight:.65,color:'#a9b8ac',fillColor:'#e6eadf',fillOpacity:.66,interactive:false}).addTo(background);
  const byBuilding=Object.fromEntries(c.buildings.map(b=>[b.id,b]));
  for(const [id,label] of [['302','302동'],['301','301동'],['38','38동'],['200','농생대'],['500','자연대'],['60','행정관']]){const b=byBuilding[id];if(b)addLandmark([b.lat,b.lon],label);}
  if(!byBuilding['60'])addLandmark([c.nodes[0].lat,c.nodes[0].lon],'행정관');
  for(const [key,label] of [['snu','서울대입구역'],['nak','낙성대역'],['daehak','대학동']])addLandmark(c.destinations[key],label);
  $('queue-stops').replaceChildren();
  c.nodes.forEach((n,i)=>{
    const button=document.createElement('button');button.className='queue-stop';button.innerHTML=`<span>${escape(n.label)}<small id="queue-wait-${i}" style="display:block;margin-top:3px">—</small></span><strong id="queue-number-${i}">—</strong>`;
    button.addEventListener('click',()=>map.setView([n.lat,n.lon],17,{animate:false}));$('queue-stops').append(button);
    const marker=L.circleMarker([n.lat,n.lon],{radius:5,color:'#1b5a50',weight:2,fillColor:'#fff',fillOpacity:1}).bindTooltip(escape(n.label),{permanent:true,direction:i%2?'right':'left',offset:[i%2?9:-9,0],className:'queue-label'}).addTo(queueLabels);queueMarkers.push(marker);
  });
  labelsCreated=true;focusMap('all');sizeCanvas();
}
function frame(timestamp){
  if(state.playing){if(state.last){const dt=Math.min((timestamp-state.last)/1000,.1);state.minute=clamp(state.minute+dt*state.speed);if(state.minute>=END)setPlaying(false);}state.last=timestamp;updateClock();draw();}
  state.frame=requestAnimationFrame(frame);
}
$('weekday').addEventListener('change',event=>loadDay(event.target.value));
$('movement-view').addEventListener('click',()=>setMode('movement'));$('queue-view').addEventListener('click',()=>setMode('queue'));
$('time-slider').addEventListener('input',event=>selectTime(Number(event.target.value)));
$('time-input').addEventListener('change',event=>{const [h,m]=event.target.value.split(':').map(Number);if(Number.isFinite(h+m))selectTime(h*60+m);});
$('play-button').addEventListener('click',()=>{if(state.minute>=END)state.minute=START;setPlaying(!state.playing);});
$('back-button').addEventListener('click',()=>selectTime(state.minute-5));$('forward-button').addEventListener('click',()=>selectTime(state.minute+5));
$('speed').addEventListener('change',event=>{state.speed=Number(event.target.value);});
$('retry-button').addEventListener('click',()=>loadDay($('weekday').value));
$('about-button').addEventListener('click',()=>$('about-dialog').showModal());
document.querySelectorAll('[data-focus]').forEach(b=>b.addEventListener('click',()=>focusMap(b.dataset.focus)));
map.on('move zoom resize',()=>{sizeCanvas();});
new ResizeObserver(()=>{map.invalidateSize({pan:false});sizeCanvas();}).observe($('map'));
document.addEventListener('visibilitychange',()=>{if(document.hidden)setPlaying(false);});
window.addEventListener('pagehide',()=>cancelAnimationFrame(state.frame),{once:true});
async function start(){
  try{state.common=await getJSON('data/common.json');initializeGeography();await loadDay(state.day);requestAnimationFrame(frame);}
  catch(error){$('loading-overlay').hidden=true;$('error-panel').hidden=false;$('error-message').textContent='지도 재생자료를 확인할 수 없습니다. 서버를 다시 실행한 뒤 새로고침해 주세요.';console.error('Replay initialization failed',error);}
}
updateClock();start();
