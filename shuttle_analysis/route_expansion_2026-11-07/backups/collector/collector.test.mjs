import test from 'node:test';import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';import {DatabaseSync} from 'node:sqlite';
import {pathToFileURL} from 'node:url';
import {ROUTES,LIMITS,kstDay,dayStart,schedule,allowedReservation,chooseRoute} from './schedule.mjs';
import {operatingPolicy,batchCalendar} from './policy_v2.mjs';
const original=await readFile(new URL('./worker.mjs',import.meta.url),'utf8');
const source=original.replace("import {DurableObject} from 'cloudflare:workers';","const DurableObject=class {constructor(ctx,env){this.ctx=ctx;this.env=env;}};")
  .replace("import profile from './demand.json';","const profile={};")
  .replace("import routeStops from './route_stops.json';",'const routeStops='+JSON.stringify(JSON.parse(await readFile(new URL('./route_stops.json',import.meta.url),'utf8')))+';')
  .replace(/from '(\.\/[^']+\.mjs)'/g,(_,name)=>`from '${new URL(name,import.meta.url).href}'`);
const {Coordinator,DailyHistory}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
function context(){
 const db=new DatabaseSync(':memory:');let alarm=null;
 return {storage:{sql:{exec(q,...v){const s=db.prepare(q);const rows=s.all(...v.map(x=>x instanceof Uint8Array?Buffer.from(x):x));const changed=/^\s*(INSERT|REPLACE|UPDATE|DELETE)/i.test(q)?Number(db.prepare('SELECT changes() AS n').get().n):0;return {rowsRead:rows.length+1,rowsWritten:changed*3,toArray:()=>rows,[Symbol.iterator]:()=>rows[Symbol.iterator]()};}},
  transactionSync(fn){db.exec('BEGIN IMMEDIATE');try{const r=fn();db.exec('COMMIT');return r;}catch(e){db.exec('ROLLBACK');throw e;}},
  async getAlarm(){return alarm;},async setAlarm(t){alarm=t;},async deleteAlarm(){alarm=null;},async deleteAll(){for(const r of db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all())db.exec('DROP TABLE '+r.name);}},db};
}
test('calendar has 360 baseline and 405/135 extras, on every weekday and weekend',()=>{
 for(let i=0;i<7;i++){const d=kstDay(dayStart('2026-11-09')+i*86400000),jobs=schedule(d);
  for(const p of ['baseline','peak','offpeak'])assert.equal(jobs.filter(j=>j.pool===p).length,LIMITS[p]);
  assert.equal(new Set(jobs.map(x=>x.id)).size,900);
  assert.equal(jobs.filter(j=>j.route===ROUTES[0]).length,72);
  assert(jobs.every(j=>j.at>=dayStart(d)+680*60000&&j.at<=dayStart(d)+1390*60000));
 }
});
test('atomic SQL reservations include errors and remain spent across restarts',()=>{
 const ctx=context(),day='2026-11-09',now=dayStart(day)+900*60000;let c=new Coordinator(ctx,{});let n=0;
 for(const [pool,max] of Object.entries(LIMITS))for(let i=0;i<max;i++){
  const job={id:`${day}:${pool}:${i}`,pool};assert.equal(c.reserve(job,ROUTES[0],now),true);n++;
  assert.equal(c.reserve(job,ROUTES[1],now),false);if(i%17===0)c=new Coordinator(ctx,{});
 }
 assert.equal(n,950);assert.equal(c.reserve({id:day+':retry:overflow',pool:'retry'},ROUTES[0],now),false);
 assert.equal(c.counts('2026-11-08').baseline,0);
 assert.equal(Object.values(c.counts(day)).reduce((a,b)=>a+b),950);
 const next='2026-11-10';assert(c.reserve({id:next+':base:0',pool:'baseline'},ROUTES[0],dayStart(next)));
 assert(!c.reserve({id:day+':wrong-day',pool:'baseline'},ROUTES[0],dayStart(next)));
});
test('15-second route spacing and unchanged-source backoff',()=>{
 const now=dayStart('2026-11-09')+901*60000,latest=Object.fromEntries(ROUTES.map(r=>[r,{attempted_at:now-14000}]));
 assert.equal(chooseRoute({},latest,{},'2026-11-09',now),null);
 latest[ROUTES[2]]={attempted_at:now-61000,duplicate_count:2};
 assert.equal(chooseRoute({},latest,{},'2026-11-09',now),ROUTES[2]);
 latest[ROUTES[2]].attempted_at=now-30000;assert.equal(chooseRoute({},latest,{},'2026-11-09',now),null);
});
test('repeated adaptive polls do not become extra passage samples; exports are gzip NDJSON',async()=>{
 const ctx=context(),a=new DailyHistory(ctx,{}),at=Date.now()/1000;
 const v={route_id:ROUTES[0],id:'vehicle',section_order:'8',provided_at:at,crowd_code:'5'};
 await a.append({job_id:'a',at,vehicles:[v]});await a.append({job_id:'b',at:at+15,vehicles:[{...v,provided_at:at+15}]});
 const agg=await a.aggregate();assert.equal(agg.rows.reduce((s,x)=>s+x.n,0),1);
 const r=await a.export();const body=await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).text();
 assert.equal(body.trim().split('\n').map(JSON.parse).length,2);
});
test('public requests cannot trigger provider collection',async()=>{
 const c=new Coordinator(context(),{});let calls=0;c.collect=()=>{calls++;throw Error('must not collect');};
 for(let i=0;i<100;i++)assert.equal((await c.fetch(new Request('https://test/snapshot'))).status,200);
 assert.equal(calls,0);assert.equal(Object.values(c.counts(kstDay(Date.now()))).reduce((a,b)=>a+b),0);
});
test('alarm retries and reconstructed objects cannot issue the same provider request twice',async()=>{
 const ctx=context(),day='2026-11-09',at=dayStart(day)+680*60000,originalNow=Date.now,originalFetch=globalThis.fetch;
 let calls=0;Date.now=()=>at;
 globalThis.fetch=async url=>{if(String(url).includes('/buspos/'))calls++;return new Response(JSON.stringify({msgHeader:{headerCd:'4'}}));};
 const env={SEOUL_BUS_SERVICE_KEY:'fixture-only',HISTORY:{getByName(){return {append:async()=>({bytes:1,raw_bytes:1,aggregate_bytes:0,reads:1,writes:1})};}}};
 try{
  let c=new Coordinator(ctx,env);c.put('enabled',true);await c.alarm();assert.equal(calls,5);
  c=new Coordinator(ctx,env);await c.alarm();assert.equal(calls,5);
  assert.equal(c.ledger(day).counts.baseline,5);
 }finally{Date.now=originalNow;globalThis.fetch=originalFetch;}
});
test('an unavailable durable ledger blocks the external request',async()=>{
 const ctx=context(),day='2026-11-09',originalNow=Date.now,originalFetch=globalThis.fetch;
 let calls=0;Date.now=()=>dayStart(day)+680*60000;globalThis.fetch=async()=>{calls++;throw Error('unexpected');};
 const c=new Coordinator(ctx,{SEOUL_BUS_SERVICE_KEY:'fixture-only'});c.put('enabled',true);
 const exec=c.sql.exec;c.sql.exec=(q,...args)=>{if(q.startsWith('INSERT INTO state')&&args[0]==='ledger-v2')throw Error('storage unavailable');return exec(q,...args);};
 try{await assert.rejects(c.alarm(),/storage unavailable/);assert.equal(calls,0);}finally{Date.now=originalNow;globalThis.fetch=originalFetch;}
});

test('section speed polls have a separate durable cap, ten minute cache, and reject zero speed',async()=>{
 const ctx=context(),c=new Coordinator(ctx,{SEOUL_BUS_SERVICE_KEY:'fixture-only'}),originalFetch=globalThis.fetch;
 let calls=0;c.recordTraffic=()=>{};
 globalThis.fetch=async()=>{calls++;return new Response(JSON.stringify({msgHeader:{headerCd:'0'},msgBody:{itemList:[{seq:2,sectSpd:'20'},{seq:3,sectSpd:'0'}]}}));};
 try{
  const value=await c.collectTraffic(ROUTES[0]);assert.equal(value.sections['2'].speed_kmh,20);assert.equal(value.sections['3'],undefined);
  assert.equal(await c.collectTraffic(ROUTES[0]),null);assert.equal(calls,1);
  assert.equal(Object.values(c.counts(kstDay(Date.now()))).reduce((a,b)=>a+b),0);
  c.sql.exec('INSERT OR REPLACE INTO generic_calls VALUES(?,?,?)',kstDay(Date.now()),'seoul_route_traffic',400);
  assert.equal(await c.collectTraffic(ROUTES[1]),null);assert.equal(calls,1);
 }finally{globalThis.fetch=originalFetch;}
});

test('packed at-stop observations reject impossible speed and deduplicate a lingering bus',async()=>{
 const stops=JSON.parse(await readFile(new URL('./route_stops.json',import.meta.url),'utf8'))[ROUTES[0]];
 const c=new Coordinator(context(),{}),at=Date.now()/1000;
 const v=(stop,t)=>({id:'probe',route_id:ROUTES[0],section_order:String(stop.seq),at_stop:true,provided_at:t,lat:stop.lat,lon:stop.lon,previous_observation:{provided_at:t-15}});
 const read=()=>JSON.parse(c.sql.exec('SELECT value FROM route_stats').toArray()[0].value);
 c.recordPacked(ROUTES[0],[v(stops[0],at)]);c.recordPacked(ROUTES[0],[v(stops[0],at+15)]);
 assert.equal(read().progress.probe.stops.length,1);
 c.recordPacked(ROUTES[0],[v(stops[3],at+16)]);assert.equal(Object.keys(read().travel).length,0);
 c.recordPacked(ROUTES[0],[v(stops[4],at+316)]);assert.ok(Object.keys(read().travel).length>0);
});

test('approved calendar has 5980 weekday polls and 1780 weekend polls, with reserved retries',()=>{
 for(const [day,regular,cap] of [['2026-11-09',5980,6500],['2026-11-07',1780,2000]]){
  const p=operatingPolicy(day,10000),jobs=batchCalendar(day,p);
  assert.equal(jobs.length*5,regular);assert.equal(p.cap,cap);assert.equal(regular+p.reserve,cap);
  assert.equal(new Set(jobs.map(j=>j.id)).size,jobs.length);
 }
 assert.equal(operatingPolicy('2026-11-09',1000).cap,950);
});

test('reading snapshots and fresh shared cache entries performs zero SQL writes',async()=>{
 const c=new Coordinator(context(),{});c.put('enabled',false);
 const before=c.usage().writes;
 for(let n=0;n<100;n++)await c.fetch(new Request('https://fixture/snapshot'));
 assert.equal(c.usage().writes,before);
});

test('batched reservations count partial failures, restarts, retry limits and KST day changes',()=>{
 const ctx=context(),day='2026-11-09',now=dayStart(day)+900*60000;
 let c=new Coordinator(ctx,{});c.put('provider_approved_limit',10000);
 const jobs=Array.from({length:7000},(_,i)=>({id:day+':batch-fixture:'+i,pool:i<5980?'peak':'retry',route:ROUTES[i%5]}));
 assert.equal(c.reserveBatch(jobs,now).length,6500);
 c=new Coordinator(ctx,{});assert.equal(c.reserveBatch(jobs,now).length,0);
 assert.equal(Object.values(c.ledger(day).counts).reduce((a,b)=>a+b),6500);
 assert.equal(c.reserveBatch([{id:'2026-11-10:new',pool:'baseline',route:ROUTES[0]}],dayStart('2026-11-10')).length,1);
 assert.equal(c.reserveBatch([{id:day+':late',pool:'retry',route:ROUTES[0]}],dayStart('2026-11-10')).length,0);
});

test('historical queries exclude the current and future dates and latest traffic',()=>{
 const c=new Coordinator(context(),{}),when=dayStart(kstDay(Date.now()))/1000+16*3600;
 const today=kstDay(Date.now()),prior=kstDay(Date.now()-86400000);
 for(const [day,speed] of [[prior,20],[today,90]])c.sql.exec('INSERT INTO traffic_aggregate VALUES(?,?,?,?,?)',day,ROUTES[0],16,0,JSON.stringify({'2':[speed]}));
 c.put('traffic',{[ROUTES[0]]:{sections:{'2':{speed_kmh:99}}}});
 const result=c.historyFor(when);assert.equal(result.historical_traffic[ROUTES[0]].sections['2'].speed_kmh,20);
 assert.deepEqual(result.traffic,{});assert.equal(result.live_observations_used,false);
});

test('full 6500-poll fixture day stays under the 70000-row write target',async()=>{
 const ctx=context(),historyCtx=context(),history=new DailyHistory(historyCtx,{}),day='2026-11-09';
 const stops=JSON.parse(await readFile(new URL('./route_stops.json',import.meta.url),'utf8'));
 const originalNow=Date.now,originalFetch=globalThis.fetch;let clock=dayStart(day)+680*60000,positionCalls=0;
 Date.now=()=>clock;
 globalThis.fetch=async input=>{
  const u=new URL(input),rid=u.searchParams.get('busRouteId'),seq=1+Math.floor((clock-dayStart(day))/60000)%stops[rid].length;
  if(!u.pathname.includes('/buspos/'))return new Response(JSON.stringify({msgHeader:{headerCd:'0'},msgBody:{itemList:[{seq:2,sectSpd:20}]}}));
  positionCalls++;const stop=stops[rid][seq-1];
  const dataTm=new Date(clock+9*3600000).toISOString().replace(/[-:T]/g,'').slice(0,14);
  return new Response(JSON.stringify({msgHeader:{headerCd:'0'},msgBody:{itemList:Array.from({length:40},(_,i)=>({vehId:rid+'-fixture-'+i,gpsY:stop.lat,gpsX:stop.lon,sectOrd:seq,dataTm,stopFlag:'1',congetion:'5'}))}}));
 };
 const c=new Coordinator(ctx,{SEOUL_BUS_SERVICE_KEY:'fixture-only',HISTORY:{getByName:()=>history}});
 try{
  c.put('provider_approved_limit',10000);c.put('enabled',true);
  let retried=0;
  for(const slot of batchCalendar(day,operatingPolicy(day,10000))){
   clock=slot.at;await c.alarm();
   if(retried<104&&clock<dayStart(day)+900*60000){
    clock+=30000;const jobs=ROUTES.map(route=>({id:`${day}:load-retry:${retried}:${route}`,pool:'retry',route,at:clock}));
    const book=c.ledger(day);book.retries=jobs;c.put('ledger-v2',book);await c.alarm();retried++;
   }
  }
  const used=Object.values(c.ledger(day).counts).reduce((a,b)=>a+b),usage=c.usage();
  assert.equal(used,6500);assert.equal(positionCalls,6500);assert.ok(usage.writes<70000,JSON.stringify(usage));
  assert.equal(c.sql.exec('SELECT COUNT(*) AS n FROM route_stats').toArray()[0].n,5);
  console.log(JSON.stringify({validation:'synthetic_full_day_not_provider_load',positionCalls,sql_write_estimate:usage.writes,vehicles_per_route:40,archived_batches:historyCtx.db.prepare('SELECT COUNT(*) AS n FROM raw').get().n}));
  let auxiliary=0;
  for(let i=0;i<5000;i++){
   try{c.auxExec('INSERT INTO cache VALUES(?,?,?,?,?)','aux-fixture-'+i,'null',0,'fixture',0);auxiliary++;}
   catch(e){assert.match(e.message,/auxiliary_write_budget/);break;}
  }
  assert.ok(auxiliary>0);assert.ok(c.usage().aux_writes<=12000);
  assert.ok(c.usage().writes+8000<85000,'reserve headroom for cron and retention cleanup');
  console.log(JSON.stringify({validation:'bounded_auxiliary_writes_plus_maintenance_margin',auxiliary_rows:auxiliary,sql_write_estimate:c.usage().writes,maintenance_margin:8000}));
 }finally{Date.now=originalNow;globalThis.fetch=originalFetch;}
});
