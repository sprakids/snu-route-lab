// Simulated DOM interaction tests. This is deliberately not a visual browser test.
import fs from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';

const fixtures=JSON.parse(await fs.readFile(new URL('./runtime/ui_fixtures_v2.json',import.meta.url),'utf8'));
const townCatalog=JSON.parse(await fs.readFile(new URL('./data/shuttle_network.json',import.meta.url),'utf8'));
for(const spec of townCatalog.routes){
  if(!fixtures.shuttle.routes.some(r=>r.id===spec.id))fixtures.shuttle.routes.push({...spec,captured_at:null,stale:true,vehicles:[],error:null,schematic_anchors:spec.anchors});
}
fixtures.shuttle.model_predictions=[{route_id:'shuttle-41842',boarding_stop:'서울대입구역(승차)',expected_boarding_at:Date.now()/1000+222,
  automatic_queue:{model_only:true,cohort_available:false,queue_at_arrival:null,queue_now:null,expected_wait_seconds:202}}];
const html=await fs.readFile(new URL('./static/index.html',import.meta.url),'utf8');
const source=(await fs.readFile(new URL('./static/app.js',import.meta.url),'utf8')).replace(/^import[^\n]+\n/,'');
const dom=new JSDOM(html,{url:'http://localhost:8840',pretendToBeVisual:true,runScripts:'outside-only'});
const {window}=dom;const requests=[];const checks=[];
window.setInterval=()=>0;
window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
window.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
window.RouteMap=class {
  constructor(element,onPick){this.provider='osm';window.testMap=this;this.onPick=onPick;}
  async initialize(){return 'osm';}
  showRoute(candidate){this.selected=candidate;}
  showVehicles(values){this.vehicles=values;}
  showShuttle(value){this.shuttle=value;}
  showUserLocation(value,focus){this.userLocation=value;this.locationFocused=focus;}
  fit(){}
  toggleStops(){return false;}
  clearRoute(){this.selected=null;}
};
window.fetch=async(path,options={})=>{
  const body=options.body?JSON.parse(options.body):null;requests.push({path,body});
  if(path==='/api/plan'&&window.testFailPlan)throw new Error('Fixture connection failure');
  let data;
  if(path==='/api/bootstrap')data=fixtures.bootstrap;
  else if(path==='/api/refresh'||path==='/api/status')data=fixtures.positions;
  else if(path==='/api/shuttle')data=fixtures.shuttle;
  else if(path==='/api/arrivals')data={stops:body.targets.map(t=>({...t,values:[]}))};
  else if(path==='/api/plan')data=fixtures.plans[body.destination_id];
  else if(path==='/api/observations')data={saved:true,id:1,time_error_seconds:60};
  else throw new Error('Unexpected frontend request: '+path);
  data=structuredClone(data);
  if(path==='/api/plan'&&body.decision_context){
    const current=data.candidates.find(c=>c.continuation_key===body.decision_context.current_key);
    const best=data.candidates.reduce((a,b)=>a.total_seconds<b.total_seconds?a:b);
    data.adaptive_decision={action:'suggest_switch',reason:'worth_switching',current_candidate_id:current?.id,
      recommended_candidate_id:best.id,gain_seconds:(current?.total_seconds||0)-best.total_seconds};
    data.queue_report_applied=Boolean(body.queue_context);
  }
  if(path==='/api/plan'&&body.weights.crowd===100&&body.weights.time+body.weights.walk+body.weights.transfers===0){
    data.effective_weights={};data.winners={};data.notes=['알려진 평가 지표에 가중치를 지정해 주세요.'];
    for(const candidate of data.candidates){candidate.score=null;candidate.badges=[];}
  }
  return {ok:true,json:async()=>data};
};
async function until(predicate,label){
  const end=Date.now()+3000;
  while(!predicate()){if(Date.now()>end)throw new Error('DOM test timed out: '+label);await new Promise(r=>setTimeout(r,10));}
}
const document=window.document;
function check(label,action){action();checks.push(label);}
new vm.Script(source,{filename:'app.js'}).runInContext(dom.getInternalVMContext());
await until(()=>document.querySelectorAll('#origin option').length>2,'bootstrap');
assert.equal(requests.filter(r=>r.path==='/api/plan').length,0);
document.querySelector('#origin').value=fixtures.bootstrap.origins[0].id;
document.querySelector('#origin').dispatchEvent(new window.Event('change'));
document.querySelector('#destination').value='snu-station';
document.querySelector('#route-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await until(()=>document.querySelectorAll('.route-card').length>0,'initial candidates');
check('initial candidates and map selection',()=>{assert.ok(document.querySelectorAll('.route-card').length>1);assert.ok(window.testMap.selected);});
check('every route has a walking waiting bus segment bar',()=>{
  assert.equal(document.querySelectorAll('#results .journey-bar').length,document.querySelectorAll('.route-card').length);
  assert.match(document.querySelector('.mobile-phase-summary').textContent,/도보.*대기.*차내/);
});
const countdownProbe=document.createElement('div');document.body.append(countdownProbe);countdownProbe.id='countdown-probe';
const requestCount=requests.length;
new vm.Script(`{
  const saved=state.plan.live_predictions_used;state.plan.live_predictions_used=true;
  const t=nowSeconds();
  $('countdown-probe').innerHTML=arrivalContent({route_id:'probe',from_seq:1,from_name:'시험정류소',route_name:'5511',ready_at:t+30,
    arrival_options:[{departure_at:t+222,provided_at:t,vehicle_id:'a'}]});
  updateCountdowns();state.plan.live_predictions_used=saved;
}`).runInContext(dom.getInternalVMContext());
check('arrival countdown renders minutes and seconds without a provider request',()=>{
  assert.match(countdownProbe.textContent,/3분 42초/);assert.equal(requests.length,requestCount);
});
new vm.Script(`{
  const saved=state.plan.live_predictions_used;state.plan.live_predictions_used=true;const t=nowSeconds();
  $('countdown-probe').innerHTML=forecastRow({route_id:'shuttle-probe',route_name:'시간표 셔틀',ready_at:t,
    arrival_forecast:{time_basis:'timetable_simulation_only',ready_at:t,base_departure_at:t+222,last_service_at:t+3600,
      headway_seconds:600,range_seconds:[0,600],next_scheduled_departure_at:t+200}},null);
  updateCountdowns();state.plan.live_predictions_used=saved;
}`).runInContext(dom.getInternalVMContext());
check('shuttle timetable model countdown has seconds and a separate next scheduled departure',()=>{
  assert.match(countdownProbe.textContent,/3분 42초 후 예상 승차/);assert.match(countdownProbe.textContent,/시간표 다음/);
  assert.doesNotMatch(countdownProbe.textContent,/실측|미사용|미확인|모형 추정/);assert.equal(requests.length,requestCount);
});
// Restore the observed-arrival fixture for its independent expiry regression.
new vm.Script(`{
  const saved=state.plan.live_predictions_used;state.plan.live_predictions_used=true;const t=nowSeconds();
  $('countdown-probe').innerHTML=arrivalContent({route_id:'probe',from_seq:1,from_name:'시험정류소',route_name:'5511',ready_at:t+30,
    arrival_options:[{departure_at:t+222,provided_at:t,vehicle_id:'a'}]});state.plan.live_predictions_used=saved;
}`).runInContext(dom.getInternalVMContext());
countdownProbe.querySelector('[data-observed-at]').dataset.observedAt=String(Date.now()/1000-151);
new vm.Script('updateCountdowns()').runInContext(dom.getInternalVMContext());
check('expired arrival data continues as an explicitly modeled service estimate',()=>{assert.match(countdownProbe.textContent,/예상/);assert.doesNotMatch(countdownProbe.textContent,/정보 만료|갱신 대기|관측 사이 추정/);assert.equal(requests.length,requestCount);});
new vm.Script(`{
  const saved=state.plan.live_predictions_used;state.plan.live_predictions_used=true;const t=nowSeconds();
  $('countdown-probe').innerHTML=arrivalContent({route_id:'probe',from_seq:1,from_name:'셔틀',route_name:'교내셔틀',ready_at:t,
    arrival_options:[{departure_at:t+240,provided_at:t,vehicle_id:'s',arrival_source:'live_shuttle',eta_window_seconds:[180,300]}]});
  updateCountdowns();state.plan.live_predictions_used=saved;
}`).runInContext(dom.getInternalVMContext());
check('shuttle interval estimates retain uncertainty',()=>assert.match(countdownProbe.textContent,/약 .*~.*분 후 도착 예상/));
new vm.Script(`{
  $('countdown-probe').innerHTML=compactArrivalContent({route_id:'shuttle-41842',from_seq:1,from_name:'설입',route_name:'302셔틀',
    automatic_queue:{cohort_available:false,queue_at_arrival:null,expected_wait_seconds:210},arrival_options:[]});
}`).runInContext(dom.getInternalVMContext());
check('compact mobile queue summary preserves unknown instead of displaying zero people',()=>{
  assert.match(countdownProbe.textContent,/예상 대기 3분 30초/);assert.doesNotMatch(countdownProbe.textContent,/미산출|실측/);assert.doesNotMatch(countdownProbe.textContent,/0명/);
});
new vm.Script(`{
  const saved=state.plan.live_predictions_used;state.plan.live_predictions_used=false;
  $('countdown-probe').innerHTML=arrivalContent({route_id:'probe',from_seq:1,from_name:'미래 출발'});
  state.plan.live_predictions_used=saved;
}`).runInContext(dom.getInternalVMContext());
check('future departures do not claim a live countdown',()=>assert.equal(countdownProbe.querySelector('[data-arrival-at]'),null));
new vm.Script(`{
  const t=nowSeconds(),f={base_departure_at:t-700,ready_at:t-900,headway_seconds:420,range_seconds:[0,420],rolling:true,last_service_at:t+3600};
  $('countdown-probe').textContent=forecastText(f,t);
}`).runInContext(dom.getInternalVMContext());
check('old service phases advance as a range without fabricating a fresh observed countdown',()=>{
  assert.match(countdownProbe.textContent,/약 .*~.*분 · 예상 승차기회/);assert.doesNotMatch(countdownProbe.textContent,/만료|갱신 대기|00초/);
});
new vm.Script(`{const t=nowSeconds();$('countdown-probe').textContent=forecastText({base_departure_at:t-60,rolling:false,future_departures_at:[t+600],range_seconds:[60,60],ready_at:t-120},t);}`).runInContext(dom.getInternalVMContext());
check('fixed timetable estimates use the next scheduled opportunity',()=>assert.match(countdownProbe.textContent,/약 10~10분/));
new vm.Script(`{const t=nowSeconds();$('countdown-probe').textContent=forecastText({base_departure_at:t-60,last_service_at:t-30,rolling:true,headway_seconds:300},t);}`).runInContext(dom.getInternalVMContext());
check('a forecast past registered service hours offers walking instead of phantom buses',()=>assert.match(countdownProbe.textContent,/운행시간 지남 · 도보 대안/));
countdownProbe.remove();
check('no end-user API key form',()=>assert.equal([...document.querySelectorAll('input')].filter(i=>/key|api키|인증키/i.test(i.name+' '+i.id+' '+i.getAttribute('aria-label'))).length,0));
document.querySelector('[data-preset="comfort"]').click();
await until(()=>requests.filter(x=>x.path==='/api/plan').length>=2,'comfort preset');
check('preference preset sent as numeric weights',()=>assert.equal(requests.filter(x=>x.path==='/api/plan').at(-1).body.weights.crowd,45));
for(const input of document.querySelectorAll('[data-weight]')){input.value='0';input.dispatchEvent(new window.Event('input',{bubbles:true}));}
const before=requests.length;
document.querySelector('#route-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
check('zero-weight request blocked in UI',()=>{assert.equal(requests.length,before);assert.match(document.querySelector('#toast').textContent,/가중치/);});

for(const input of document.querySelectorAll('[data-weight]')){input.value=input.dataset.weight==='crowd'?'100':'0';input.dispatchEvent(new window.Event('input',{bubbles:true}));}
document.querySelector('#route-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await until(()=>document.querySelector('#results-caption').textContent.includes('예상시간순'),'missing selected criterion');
check('unknown crowd-only preference does not claim a winner',()=>{assert.ok(document.querySelectorAll('.route-card').length>0);assert.equal(document.querySelector('.recommended'),null);});
document.querySelector('[data-preset="fast"]').click();await new Promise(r=>setTimeout(r,20));
document.querySelector('#destination').value='nakseongdae';
document.querySelector('#route-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await until(()=>document.querySelector('#results-caption').textContent.includes('낙성대역'),'destination rendering');
check('destination switch uses corresponding candidates',()=>assert.equal(requests.filter(x=>x.path==='/api/plan').at(-1).body.destination_id,'nakseongdae'));
const card=document.querySelectorAll('.route-card')[1];card.click();
check('route card changes selected route and map',()=>{assert.equal(card.getAttribute('aria-pressed'),'true');assert.equal(window.testMap.selected.id,card.dataset.route);});
document.querySelector('#sources-button').click();
check('data source dialog explains unknown information',()=>{assert.ok(document.querySelector('#sources-dialog').open);assert.match(document.querySelector('#source-content').textContent,/불확실성 비용/);});
document.querySelector('[data-close="sources-dialog"]').click();
document.querySelector('#shuttle-button').click();
check('real shuttle records render as schematic positions',()=>{assert.ok(document.querySelector('#shuttle-dialog').open);assert.equal(document.querySelectorAll('.shuttle-observation').length,fixtures.shuttle.routes.find(r=>r.id==='41841').vehicles.length);assert.doesNotMatch(document.querySelector('#shuttle-content').textContent,/GPS 좌표로 바꾸지|실측 아님/);});

document.querySelector('#shuttle-route').value='41946';document.querySelector('#shuttle-route').dispatchEvent(new window.Event('change'));
check('circle selector uses its own vehicle records and source',()=>{const line=fixtures.shuttle.routes.find(r=>r.id==='41946');assert.equal(document.querySelectorAll('.shuttle-observation').length,line.vehicles.length);assert.ok([...document.querySelectorAll('#shuttle-content a')].some(a=>a.href.includes('41946')));});
document.querySelector('#shuttle-route').value='41914';document.querySelector('#shuttle-route').dispatchEvent(new window.Event('change'));
check('empty reverse route never borrows admin vehicles',()=>{const line=fixtures.shuttle.routes.find(r=>r.id==='41914');assert.equal(document.querySelectorAll('.shuttle-observation').length,line.vehicles.length);if(!line.vehicles.length)assert.match(document.querySelector('#shuttle-content').textContent,/표시할 차량이 없습니다/);});
for(const rid of ['41843','41942']){
  document.querySelector('#shuttle-route').value=rid;document.querySelector('#shuttle-route').dispatchEvent(new window.Event('change'));
  check('Daehak-dong '+rid+' selector keeps its own direction and provider',()=>{
    assert.match(document.querySelector('.dialog-caption').textContent,/대학동/);
    assert.ok([...document.querySelectorAll('#shuttle-content a')].some(a=>a.href.includes(rid)));
    assert.equal(document.querySelectorAll('.shuttle-observation').length,0);
  });
}
check('all ten student shuttle routes are selectable',()=>assert.equal(document.querySelector('#shuttle-route').options.length,10));
document.querySelector('#shuttle-route').value='41842';document.querySelector('#shuttle-route').dispatchEvent(new window.Event('change'));
check('commuter shuttle model shows ETA without inventing a zero-person queue',()=>{
  const text=document.querySelector('#shuttle-content').textContent;
  assert.match(text,/후 예상 승차/);assert.doesNotMatch(text,/유입 코호트 없음|줄 인원 미산출|실측 아님/);
  assert.doesNotMatch(text,/도착 시 약 0명/);
});
document.querySelector('[data-close="shuttle-dialog"]').click();
document.querySelector('#pick-origin').click();window.testMap.onPick(37.4600,126.9520);
document.querySelector('#route-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await new Promise(r=>setTimeout(r,20));
check('map-selected origin reaches backend request',()=>{const body=requests.filter(x=>x.path==='/api/plan').at(-1).body;assert.equal(body.origin.lat,37.46);assert.equal(body.origin_id,undefined);});
document.querySelector('#departure-mode').value='specified';document.querySelector('#departure-mode').dispatchEvent(new window.Event('change'));
document.querySelector('#route-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await new Promise(r=>setTimeout(r,20));
check('future departure is explicitly an estimate',()=>{assert.equal(document.querySelector('#departure-time').hidden,false);assert.equal(requests.filter(x=>x.path==='/api/plan').at(-1).body.mode,'estimate');});
check('specified-time map does not present current vehicles as future positions',()=>{
  assert.equal(window.testMap.vehicles.length,0);assert.equal(window.testMap.shuttle.vehicles.length,0);
});
const selectedKey=window.testMap.selected.observation_key;
document.querySelector('#record-button').click();
document.querySelector('[name=actual]').value='30';
document.querySelector('#observation-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await until(()=>requests.some(x=>x.path==='/api/observations'),'observation payload');
check('measurement record has route context without API keys',()=>{const body=requests.find(x=>x.path==='/api/observations').body;assert.equal(body.candidate,selectedKey);assert.equal(body.actual_minutes,30);assert.equal(JSON.stringify(body).includes('serviceKey'),false);});

let geoReply,geoError;
Object.defineProperty(window.navigator,'geolocation',{configurable:true,value:{getCurrentPosition(success,error,options){window.geoOptions=options;geoReply=success;geoError=error;}}});
document.querySelector('#my-location').click();
geoReply({coords:{latitude:37.46086,longitude:126.950347,accuracy:22},timestamp:Date.now()});
await until(()=>document.querySelector('#location-status').textContent.includes('출발지로 사용 중'),'current location origin');
await new Promise(r=>setTimeout(r,20));
check('device coordinates, accuracy marker and route origin agree',()=>{assert.equal(window.testMap.userLocation.accuracy,22);assert.equal(window.testMap.userLocation.lat,37.46086);assert.equal(requests.filter(x=>x.path==='/api/plan').at(-1).body.origin.lon,126.950347);assert.equal(window.geoOptions.enableHighAccuracy,true);});
const previousOrigin=requests.filter(x=>x.path==='/api/plan').at(-1).body.origin;
document.querySelector('#my-location').click();geoError({code:1});
await until(()=>document.querySelector('#location-status').textContent.includes('권한이 꺼져'),'denied location');
check('location permission denial preserves chosen origin',()=>assert.deepEqual(requests.filter(x=>x.path==='/api/plan').at(-1).body.origin,previousOrigin));
document.querySelector('#my-location').click();geoReply({coords:{latitude:37.50,longitude:127.0,accuracy:30},timestamp:Date.now()});
await until(()=>document.querySelector('#location-status').textContent.includes('교외'),'outside coverage location');
check('outside-campus location is shown without an unsupported route request',()=>{assert.equal(window.testMap.userLocation.lat,37.50);assert.deepEqual(requests.filter(x=>x.path==='/api/plan').at(-1).body.origin,previousOrigin);});
document.querySelector('#my-location').click();geoReply({coords:{latitude:37.4609,longitude:126.9503,accuracy:600},timestamp:Date.now()});
await until(()=>document.querySelector('#location-status').textContent.includes('파란 원'),'low accuracy location');
check('imprecise location requires choosing an origin',()=>assert.deepEqual(requests.filter(x=>x.path==='/api/plan').at(-1).body.origin,previousOrigin));
document.querySelector('#my-location').click();
document.querySelector('#origin').value=fixtures.bootstrap.origins[0].id;document.querySelector('#origin').dispatchEvent(new window.Event('change'));
geoReply({coords:{latitude:37.46086,longitude:126.950347,accuracy:20},timestamp:Date.now()});
await until(()=>document.querySelector('#location-status').textContent.includes('선택한 출발지를 유지'),'late location response');
check('late location response preserves a newer manual origin selection',()=>assert.equal(document.querySelector('#origin').value,fixtures.bootstrap.origins[0].id));
fixtures.positions.position_updates_paused=true;
fixtures.positions.storage={observations_available:false,message:'저장소 무료 한도로 기록 저장과 버스 위치 수집을 일시 중단했습니다.'};
document.querySelector('#refresh-button').click();
await until(()=>!document.querySelector('#service-notice').hidden,'storage outage notice');
check('storage outage explains limited service and disables record submission',()=>{
  assert.match(document.querySelector('#service-notice').textContent,/일부 기능이 일시 중단/);
  assert.equal(document.querySelector('#observation-form button[type="submit"]').disabled,true);
  assert.match(document.querySelector('#live-label').textContent,/버스 안내|시간 지정/);
});
const recordsBefore=requests.filter(x=>x.path==='/api/observations').length;
document.querySelector('#observation-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
check('storage outage does not claim that a record was saved',()=>{
  assert.equal(requests.filter(x=>x.path==='/api/observations').length,recordsBefore);
  assert.match(document.querySelector('#toast').textContent,/저장되지 않았습니다/);
});
const strategyFixture=fixtures.plans['snu-station'];
const strategyA=strategyFixture.candidates[0],strategyB=strategyFixture.candidates[1];
const strategySummary=(c,type,seconds)=>({...c,strategy:type,total_seconds:seconds,
  walk_seconds:type==='shuttle_wait'?90:600,wait_seconds:type==='shuttle_wait'?900:100,ride_seconds:490,
  boarding_seconds:20,boarding:[{route_name:type==='shuttle_wait'?'행정관 셔틀':'5515',crowd_label:'정보 부족',crowd_source:'unavailable',arrival_source:'estimate'}],
  historical_demand:{available:true,label:'과거 수요가 많은 시간대'},uses_unobserved_departure:true});
strategyFixture.strategy_comparison={strategies:{shuttle_wait:strategySummary(strategyA,'shuttle_wait',1500),walk_to_gate:strategySummary(strategyB,'walk_to_gate',1200)},
  compared_at:Date.now()/1000,faster_strategy:'walk_to_gate',difference_seconds:300,recommended_candidate_id:strategyB.id,
  missing_reasons:{},note:'과거 재차합을 혼잡등급이나 추가 대기 분으로 환산하지 않습니다.'};
document.querySelector('#destination').value='snu-station';
await new vm.Script("state.preset='fast';state.weights={time:75,crowd:5,walk:15,transfers:5};search();").runInContext(dom.getInternalVMContext());
check('shuttle and gate strategies render with an explicit time comparison',()=>{
  assert.equal(document.querySelector('#strategy-comparison').hidden,false);
  assert.equal(document.querySelectorAll('[data-strategy-route]').length,2);
  assert.match(document.querySelector('.strategy-verdict').textContent,/정문.*5분.*빠릅니다/);
  assert.equal(document.querySelector('.strategy-demand'),null);
});
check('fast mode selects the declared shortest candidate instead of weighted order',()=>assert.equal(window.testMap.selected.id,strategyB.id));
document.querySelector('[data-strategy-route="'+strategyA.id+'"]').click();
check('strategy selection updates the real route map and pressed state',()=>{
  assert.equal(window.testMap.selected.id,strategyA.id);
  assert.equal(document.querySelector('[data-strategy-route="'+strategyA.id+'"]').getAttribute('aria-pressed'),'true');
});
const strategyRequestsBefore=requests.filter(x=>x.path==='/api/plan').length;
const strategyRefreshBefore=requests.filter(x=>x.path==='/api/refresh').length;
document.querySelector('#recompare-strategies').click();
await until(()=>!document.querySelector('#search-button').disabled,'strategy recompare completed');
check('recompare requests one new plan without a direct position refresh',()=>{
  assert.equal(requests.filter(x=>x.path==='/api/plan').length,strategyRequestsBefore+1);
  assert.equal(requests.filter(x=>x.path==='/api/refresh').length,strategyRefreshBefore);
});
// Explicit waiting-state fixtures: no real location or observation is submitted.
const shuttleSpec=fixtures.bootstrap.routes.find(r=>r.id==='shuttle-41841');
const waitingStop=shuttleSpec.stops.find(s=>s.id==='snu-410');
const waitingCandidate=structuredClone(strategyA),alternative=structuredClone(strategyB);
waitingCandidate.id='wait-shuttle';waitingCandidate.total_seconds=1500;waitingCandidate.continuation_key='shuttle-41841:snu-410';
waitingCandidate.route_names=[shuttleSpec.name];
Object.assign(waitingCandidate.legs.find(l=>l.type==='bus'),{route_id:shuttleSpec.id,route_name:shuttleSpec.name,mode:'shuttle',
  station_id:waitingStop.id,from_seq:waitingStop.seq,from_name:waitingStop.name,queue_report_opportunity:{departure_at:Date.now()/1000+200,vehicle_id:'fixture-only'}});
const autoQueueFixture={queue_at_arrival:32.5,queue_now:20,queue_range:[12,70],expected_wait_seconds:400,
  wait_scenario_range_seconds:[90,900],historical_signal:{available:true},live_signal:{available:true,vehicles:2,
    newest_observed_at:Date.now()/1000-60,source:'observed'},observed_queue:false,calibrated:false};
Object.assign(waitingCandidate.legs.find(l=>l.type==='bus'),{automatic_queue:autoQueueFixture,arrival_source:'shuttle_auto_queue_estimate'});
alternative.id='other-choice';alternative.total_seconds=700;alternative.continuation_key='100100250:other-stop';
strategyFixture.candidates=[waitingCandidate,alternative];strategyFixture.live_predictions_used=true;
strategyFixture.strategy_comparison.recommended_candidate_id=waitingCandidate.id;
strategyFixture.strategy_comparison.strategies.shuttle_wait=strategySummary(waitingCandidate,'shuttle_wait',1500);
strategyFixture.strategy_comparison.strategies.shuttle_wait.automatic_queues=[autoQueueFixture];
strategyFixture.strategy_comparison.shuttle_options=[strategyFixture.strategy_comparison.strategies.shuttle_wait];
strategyFixture.strategy_comparison.strategies.walk_to_gate=strategySummary(alternative,'walk_to_gate',700);
document.querySelector('#departure-mode').value='now';await new vm.Script('search()').runInContext(dom.getInternalVMContext());
check('automatic queue is visible and included before any manual waiting action',()=>{
  assert.equal(document.querySelector('.strategy-card .automatic-queue-evidence'),null);
  assert.match(document.querySelector('#selected-panel').textContent,/예상 줄 약 33명/);
  const body=requests.filter(r=>r.path==='/api/plan').at(-1).body;assert.equal(body.queue_context,undefined);
});
check('automatic queue shows bus observation evidence without an observed shuttle countdown',()=>{
  assert.doesNotMatch(document.querySelector('#selected-panel').textContent,/시내버스 혼잡 2대 관측|실측 아님/);
  assert.equal(document.querySelectorAll('#selected-panel [data-arrival-at]').length,0);
});
const mixedAges=new vm.Script(`automaticQueueText({...${JSON.stringify(autoQueueFixture)},live_signal:{available:true,vehicles:2,source:'last_observation_estimate',newest_observed_at:nowSeconds()-60,oldest_age_seconds:180}},true)`).runInContext(dom.getInternalVMContext());
check('queue summary keeps useful estimates and omits observation metadata',()=>{assert.match(mixedAges,/예상 줄 약 33명.*예상 대기/);assert.doesNotMatch(mixedAges,/분 전|실측/);});
const specifiedQueue=new vm.Script(`automaticQueueText({...${JSON.stringify(autoQueueFixture)},future_query:true},true)`).runInContext(dom.getInternalVMContext());
check('specified-time queue explains that current crowd observations are deliberately unused',()=>{
  assert.doesNotMatch(specifiedQueue,/실측|미사용/);assert.doesNotMatch(specifiedQueue,/2대 관측/);
});
document.querySelector('.strategy-shuttle-options [data-strategy-route]').click();
check('route-specific shuttle estimates remain selectable alongside the best shuttle',()=>{
  assert.match(document.querySelector('.strategy-shuttle-options').textContent,/행정관 셔틀/);
  assert.equal(window.testMap.selected.id,waitingCandidate.id);
});
document.querySelector('#start-waiting').click();await until(()=>!document.querySelector('#search-button').disabled,'waiting started');
check('waiting starts only after arrival selection and recalculates from the stop',()=>{
  const body=requests.filter(r=>r.path==='/api/plan').at(-1).body;
  assert.equal(body.origin.lat,waitingStop.lat);assert.equal(body.origin.lon,waitingStop.lon);
  assert.equal(body.decision_context.current_key,'shuttle-41841:snu-410');
  assert.match(document.querySelector('#adaptive-monitor').textContent,/남은시간/);
});
document.querySelector('[name=ahead]').value='65';document.querySelector('[name=seats]').value='0';document.querySelector('[name=full]').checked=true;
document.querySelector('#queue-report-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await until(()=>!document.querySelector('#search-button').disabled,'queue report submitted');
check('optional queue and seats report is passed as a fresh user input',()=>{
  const body=requests.filter(r=>r.path==='/api/plan').at(-1).body;
  assert.equal(body.queue_context.queue_ahead,65);assert.equal(body.queue_context.next_seats,0);assert.equal(body.queue_context.next_full,true);
  assert.match(document.querySelector('#adaptive-monitor').textContent,/後続|후속/);
});
let automaticBefore=requests.filter(r=>r.path==='/api/plan').length;
const refreshBeforeAuto=requests.filter(r=>r.path==='/api/refresh').length;
await new vm.Script('state.journey.lastCheckAt=nowSeconds()-61;recheckWaiting()').runInContext(dom.getInternalVMContext());
await new vm.Script('recheckWaiting()').runInContext(dom.getInternalVMContext());
check('waiting rechecks once per 60 seconds through the existing plan endpoint',()=>{
  assert.equal(requests.filter(r=>r.path==='/api/plan').length,automaticBefore+1);
  assert.equal(requests.filter(r=>r.path==='/api/refresh').length,refreshBeforeAuto);
});
Object.defineProperty(document,'visibilityState',{value:'hidden',configurable:true});
await new vm.Script('state.journey.lastCheckAt=nowSeconds()-61;recheckWaiting()').runInContext(dom.getInternalVMContext());
check('hidden waiting page does not requery',()=>assert.equal(requests.filter(r=>r.path==='/api/plan').length,automaticBefore+1));
Object.defineProperty(document,'visibilityState',{value:'visible',configurable:true});
automaticBefore=requests.filter(r=>r.path==='/api/plan').length;window.testFailPlan=true;
await new vm.Script('state.journey.lastCheckAt=nowSeconds()-61;recheckWaiting()').runInContext(dom.getInternalVMContext());
await new vm.Script('recheckWaiting()').runInContext(dom.getInternalVMContext());
check('failed automatic request waits another 60 seconds instead of retrying every tick',()=>assert.equal(requests.filter(r=>r.path==='/api/plan').length,automaticBefore+1));
window.testFailPlan=false;await new vm.Script('search(null,{monitor:true})').runInContext(dom.getInternalVMContext());
automaticBefore=requests.filter(r=>r.path==='/api/plan').length-1;
document.querySelector('#toggle-monitor').click();
await new vm.Script('recheckWaiting()').runInContext(dom.getInternalVMContext());
check('automatic waiting comparison can be stopped without a provider refresh',()=>assert.equal(requests.filter(r=>r.path==='/api/plan').length,automaticBefore+1));
document.querySelector('#accept-switch').click();
check('accepting a switch counts once and pauses while moving',()=>{
  assert.equal(window.testMap.selected.id,alternative.id);
  assert.match(document.querySelector('#adaptive-monitor').textContent,/변경 1\/2회/);
  assert.match(document.querySelector('#adaptive-monitor').textContent,/이동 중 · 자동 비교 중지/);
  assert.equal(document.querySelector('#accept-switch'),null);
});
document.querySelector('#departure-mode').value='specified';document.querySelector('#departure-mode').dispatchEvent(new window.Event('change'));
await new vm.Script('search()').runInContext(dom.getInternalVMContext());
check('specified-time search clears waiting decisions and manual queue reports',()=>{
  const body=requests.filter(r=>r.path==='/api/plan').at(-1).body;
  assert.equal(body.decision_context,undefined);assert.equal(body.queue_context,undefined);
  assert.equal(document.querySelector('#adaptive-monitor').hidden,true);
});
const report={suite:'jsdom simulated DOM interactions',passed:checks.length,checks,visual_browser_test:false,real_observations_written:false};
await fs.writeFile(new URL('./runtime/ui_validation.json',import.meta.url),JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));dom.window.close();
