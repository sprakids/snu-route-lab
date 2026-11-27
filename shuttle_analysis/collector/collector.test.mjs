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
  c.sql.exec('INSERT OR REPLACE INTO generic_calls VALUES(?,?,?)',kstDay(Date.now()),'seoul_route_traffic',600);
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

test('eight-route calendar has 9568 weekday polls, 2848 weekend polls, and a bounded pending policy',()=>{
 for(const [day,approved,regular,cap] of [['2026-11-09',15000,9568,10400],['2026-11-07',15000,2848,3200],['2026-11-09',10000,9088,9800]]){
  const p=operatingPolicy(day,approved),jobs=batchCalendar(day,p);
  assert.equal(jobs.length*ROUTES.length,regular);assert.equal(p.cap,cap);assert.equal(regular+p.reserve,cap);
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
 let c=new Coordinator(ctx,{});c.put('provider_approved_limit',15000);
 const jobs=Array.from({length:11000},(_,i)=>({id:day+':batch-fixture:'+i,pool:i<9568?'peak':'retry',route:ROUTES[i%ROUTES.length]}));
 assert.equal(c.reserveBatch(jobs,now).length,10400);
 c=new Coordinator(ctx,{});assert.equal(c.reserveBatch(jobs,now).length,0);
 assert.equal(Object.values(c.ledger(day).counts).reduce((a,b)=>a+b),10400);
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

test('full 10400-poll fixture day stays under the 70000-row write target',async()=>{
 const ctx=context(),historyCtx=context(),history=new DailyHistory(historyCtx,{}),day='2026-11-09';
 const stops=JSON.parse(await readFile(new URL('./route_stops.json',import.meta.url),'utf8'));
 const originalNow=Date.now,originalFetch=globalThis.fetch;let clock=dayStart(day)+680*60000,positionCalls=0;
 Date.now=()=>clock;
 globalThis.fetch=async input=>{
  const u=new URL(input),rid=u.searchParams.get('busRouteId'),seq=1+Math.floor((clock-dayStart(day))/60000)%stops[rid].length;
  if(!u.pathname.includes('/buspos/'))return new Response(JSON.stringify({msgHeader:{headerCd:'0'},msgBody:{itemList:stops[rid].map(s=>({seq:s.seq,sectSpd:10+s.seq%25}))}}));
  positionCalls++;
  const dataTm=new Date(clock+9*3600000).toISOString().replace(/[-:T]/g,'').slice(0,14);
  return new Response(JSON.stringify({msgHeader:{headerCd:'0'},msgBody:{itemList:Array.from({length:80},(_,i)=>{
   const s=stops[rid][(seq-1+i*3)%stops[rid].length];
   return {vehId:rid+'-fixture-'+i,gpsY:s.lat,gpsX:s.lon,sectOrd:s.seq,dataTm,stopFlag:'1',isFullFlag:String(Number((i+seq)%7===0)),congetion:String(3+(i+seq)%4)};
  })}}));
 };
 const c=new Coordinator(ctx,{SEOUL_BUS_SERVICE_KEY:'fixture-only',HISTORY:{getByName:()=>history}});
 try{
  c.put('provider_approved_limit',15000);c.put('enabled',true);
  let retried=0;
  for(const slot of batchCalendar(day,operatingPolicy(day,15000))){
   clock=slot.at;await c.alarm();
   if(retried<104&&clock<dayStart(day)+900*60000){
    clock+=30000;const jobs=ROUTES.map(route=>({id:`${day}:load-retry:${retried}:${route}`,pool:'retry',route,at:clock}));
    const book=c.ledger(day);book.retries=jobs;c.put('ledger-v2',book);await c.alarm();retried++;
   }
  }
  const used=Object.values(c.ledger(day).counts).reduce((a,b)=>a+b),usage=c.usage();
  assert.equal(used,10400);assert.equal(positionCalls,10400);assert.ok(usage.writes<70000,JSON.stringify(usage));
  assert.equal(c.sql.exec('SELECT COUNT(*) AS n FROM route_stats').toArray()[0].n,8);
  console.log(JSON.stringify({validation:'synthetic_full_day_not_provider_load',positionCalls,sql_write_estimate:usage.writes,vehicles_per_route:80,archived_batches:historyCtx.db.prepare('SELECT COUNT(*) AS n FROM raw').get().n}));
  let auxiliary=0;
  for(let i=0;i<5000;i++){
   try{c.auxExec('INSERT INTO cache VALUES(?,?,?,?,?)','aux-fixture-'+i,'null',0,'fixture',0);auxiliary++;}
   catch(e){assert.match(e.message,/auxiliary_write_budget/);break;}
  }
  assert.ok(auxiliary>0);assert.ok(c.usage().aux_writes<=9000);
  assert.ok(c.usage().writes+10000<85000,'reserve headroom for cron and retention cleanup');
  const bytes=historyCtx.db.prepare('SELECT COALESCE(SUM(length(payload)),0) AS n FROM raw').get().n;
  const stats=c.sql.exec('SELECT SUM(length(value)) AS n FROM route_stats').toArray()[0].n;
  const traffic=c.sql.exec('SELECT SUM(length(value)) AS n FROM traffic_aggregate').toArray()[0].n||0;
  console.log(JSON.stringify({validation:'bounded_auxiliary_writes_plus_maintenance_margin',auxiliary_rows:auxiliary,
    sql_write_estimate:c.usage().writes,maintenance_margin:10000,reads:usage.reads,archive_bytes_per_day:bytes,
    packed_stats_bytes_per_day:stats,traffic_bytes_per_day:traffic,
    retention_projection_bytes:bytes*30+(stats+traffic)*365,projection_kind:'synthetic_fixture_30d_raw_365d_stats_excludes_indexes_and_other_projects'}));
 }finally{Date.now=originalNow;globalThis.fetch=originalFetch;}
});

test('shared crowd history excludes current and future dates and recording diagnostics read packed rows',async()=>{
 const c=new Coordinator(context(),{}),today=kstDay(Date.now()),prior=kstDay(Date.now()-86400000),rid=ROUTES[0];
 const row=(grade,n)=>({grades:{[`2:64:${grade}`]:n},availability:{'2:64:5':[1,5]},travel:{},progress:{}});
 c.sql.exec('INSERT INTO route_stats VALUES(?,?,?)',prior,rid,JSON.stringify(row(3,5)));
 c.sql.exec('INSERT INTO route_stats VALUES(?,?,?)',today,rid,JSON.stringify(row(6,999)));
 const result=c.historyFor(dayStart(today)/1000+16*3600);
 assert.deepEqual(result.crowd_history[rid].counts,[5,0,0,0]);assert.deepEqual(result.crowd_history[rid].dates,[prior]);
 const recording=await (await c.fetch(new Request('https://test/recording?day='+prior))).json();
 assert.equal(recording.routes[0].grade_observations,5);assert.equal(recording.routes[0].known_full_flag_observations,5);
 const aggregate=await (await c.fetch(new Request('https://test/aggregate?day='+prior))).json();
 assert.equal(aggregate.source,'packed_route_statistics');assert.equal(aggregate.rows[0].n,5);
});

test('per-object storage guard throttles before the free object limit',()=>{
 const c=new Coordinator(context(),{});c.put('packed_total_bytes',820000000);
 assert.ok(c.usage().ratio>=.9);assert.equal(c.usage().coordinator_storage_guard_bytes,900000000);
});

const post=(c,path,body)=>c.fetch(new Request('https://fixture'+path,{method:'POST',body:JSON.stringify(body)}));
test('reverse shuttle cache and budget work after the auxiliary write guard is exhausted',async()=>{
 const c=new Coordinator(context(),{}),key='shuttle-v2-41914';
 c.put('usage',{day:new Date().toISOString().slice(0,10),requests:10000,reads:80000,writes:24000,aux_writes:8989});
 assert.throws(()=>c.auxExec('DELETE FROM cache WHERE key=?','unused'),/auxiliary_write_budget/);
 const claims=await Promise.all(Array.from({length:20},()=>post(c,'/cache',{key,action:'claim'}).then(r=>r.json())));
 assert.equal(claims.filter(x=>x.owned).length,1);
 const claim=claims.find(x=>x.owned);
 assert.equal((await (await post(c,'/budget',{service:'busin_live',limit:6000})).json()).allowed,true);
 const value={captured_at:Date.now()/1000,vehicles:[{id:'reverse-fixture'}],error:null};
 assert.equal((await (await post(c,'/cache',{key,action:'publish',owner:claim.owner,value,seconds:15})).json()).saved,true);
 const before=c.usage().writes;
 for(let n=0;n<50;n++){
  const hit=await (await post(c,'/cache',{key,action:'claim'})).json();
  assert.equal(hit.owned,false);assert.deepEqual(hit.value,value);
 }
 assert.equal(c.usage().writes,before,'fresh shared cache performs no writes');
 assert.ok(c.usage().writes<24032,'first reservation and checkpoint use a few rows');
});

test('shuttle checkpoints preserve source time, reject old owners, and persist at most once per minute',async()=>{
 const ctx=context(),c=new Coordinator(ctx,{}),realNow=Date.now;let now=dayStart('2026-11-09')+17*3600000;Date.now=()=>now;
 const key='shuttle-v2-41914',publish=async(value)=>{
  const claim=await (await post(c,'/cache',{key,action:'claim'})).json();
  assert.equal(claim.owned,true);
  return post(c,'/cache',{key,action:'publish',owner:claim.owner,value,seconds:15});
 };
 try{
  const value={captured_at:now/1000,vehicles:[{id:'reverse-fixture'}],error:null};await publish(value);
  const before=c.usage().writes;now+=16000;await publish({...value,captured_at:now/1000});
  assert.equal(c.usage().writes,before);
  now+=60000;const next={...value,captured_at:now/1000};await publish(next);
  const restarted=new Coordinator(ctx,{}),read=await (await post(restarted,'/cache',{key,action:'read'})).json();
  assert.deepEqual(read.value,next);assert.equal(read.value.captured_at,next.captured_at,'restart must not refresh observation time');
  now+=16000;
  const old=await (await post(restarted,'/cache',{key,action:'claim'})).json();now+=55001;
  const newer=await (await post(restarted,'/cache',{key,action:'claim'})).json();
  assert.notEqual(old.owner,newer.owner);
  assert.equal((await post(restarted,'/cache',{key,action:'publish',owner:old.owner,value:{},seconds:15})).status,409);
  assert.equal((await post(restarted,'/cache',{key,action:'release',owner:newer.owner})).status,200);
 }finally{Date.now=realNow;}
});

test('BUSIN batch reservations never exceed 6000 across restarts or a KST midnight',async()=>{
 const ctx=context(),realNow=Date.now;let now=dayStart('2026-11-09')+17*3600000;Date.now=()=>now;
 let c=new Coordinator(ctx,{}),grants=0;
 try{
  for(let n=0;n<6100;n++){
   if(n%157===0)c=new Coordinator(ctx,{});
   const result=await (await post(c,'/budget',{service:'busin_live',limit:100000})).json();
   if(result.allowed)grants++;
  }
  const spent=ctx.db.prepare('SELECT used FROM generic_calls WHERE day=? AND service=?').get('2026-11-09','busin_live').used;
  assert.equal(spent,6000);assert.ok(grants<=6000&&grants>5500,'unused restart reservations remain charged');
  now=dayStart('2026-11-10');assert.equal((await (await post(c,'/budget',{service:'busin_live',limit:6000})).json()).allowed,true);
  assert.equal(ctx.db.prepare('SELECT used FROM generic_calls WHERE day=? AND service=?').get('2026-11-09','busin_live').used,6000);
 }finally{Date.now=realNow;}
});

test('new shuttle reservations fail closed on storage failure or total write exhaustion',async()=>{
 const ctx=context(),c=new Coordinator(ctx,{}),exec=c.sql.exec;
 c.sql.exec=(q,...args)=>{if(q.includes('INSERT OR REPLACE INTO generic_calls'))throw Error('disk unavailable');return exec(q,...args);};
 await assert.rejects(post(c,'/budget',{service:'busin_live',limit:6000}),/disk unavailable/);
 assert.equal(c.shuttleBudget,null);
 c.sql.exec=exec;
 c.put('usage',{day:new Date().toISOString().slice(0,10),requests:0,reads:0,writes:65000,aux_writes:0});
 assert.equal((await (await post(c,'/budget',{service:'busin_live',limit:6000})).json()).allowed,false);
 assert.equal(ctx.db.prepare('SELECT COUNT(*) AS n FROM generic_calls').get().n,0);
 assert.equal((await (await post(c,'/budget',{service:'seoul_position',limit:100000})).json()).allowed,false);
});

test('a busy 12-hour ten-route shuttle cache stays small with 6000 durable call reservations',async()=>{
 const c=new Coordinator(context(),{}),realNow=Date.now;let now=dayStart('2026-11-09')+680*60000;Date.now=()=>now;
 const keys=['41841','41946','41914','41843','41942','41842','41869','41868','41915','41916'].map(id=>'shuttle-v2-'+id);
 const before=c.usage().writes;let calls=0;
 try{
  for(let tick=0;tick<2880;tick++,now+=15000)for(const key of keys){
   const claim=await (await post(c,'/cache',{key,action:'claim'})).json();if(!claim.owned)continue;
   const allowed=(await (await post(c,'/budget',{service:'busin_live',limit:6000})).json()).allowed;
   calls+=Number(allowed);
   await post(c,'/cache',{key,action:'publish',owner:claim.owner,seconds:15,
    value:{captured_at:allowed?now/1000:null,vehicles:[],error:allowed?null:'budget_limit'}});
  }
  assert.equal(calls,6000);assert.equal(c.shuttleCache.size,10);
  assert.ok(c.usage().writes-before<3000,JSON.stringify(c.usage()));
  assert.equal(c.usage().aux_writes,0,'15-second cache no longer consumes the auxiliary write pool');
 }finally{Date.now=realNow;}
});

test('midday 15000 approval keeps the spent ledger and cannot backfill or double-poll',async()=>{
 const ctx=context(),realNow=Date.now,day='2026-11-09';let now=dayStart(day)+900*60000+48000;Date.now=()=>now;
 let calls=0;
 const c=new Coordinator(ctx,{SEOUL_BUS_SERVICE_KEY:'fixture-only',HISTORY:{getByName:()=>({append:async()=>({raw_bytes:1,reads:1,writes:1})})}});
 c.collect=async route=>{calls++;return {captured_at:now/1000,attempted_at:now,vehicles:[],error:null,duplicate:false,
  raw_record:{route_id:route,at:now/1000,vehicles:[]}};};
 try{
  c.put('provider_approved_limit',10000);c.put('enabled',true);await c.alarm();assert.equal(calls,8);
  const spent=JSON.stringify(c.ledger(day).spent);
  const upgrade=await (await post(c,'/control',{enabled:true,provider_approved_limit:15000})).json();
  assert.equal(upgrade.collection_policy.approved_limit,15000);assert.equal(upgrade.collection_policy.cap,10400);
  assert.equal(upgrade.position_calls_today,8);assert.equal(JSON.stringify(c.ledger(day).spent),spent);
  now+=1000;await c.alarm();assert.equal(calls,8,'new 15-second calendar cannot re-poll one second after the previous 16-second slot');
  now=dayStart(day)+901*60000+15000;await c.alarm();assert.equal(calls,16);
  const used=Object.values(c.ledger(day).counts).reduce((a,b)=>a+b,0);assert.equal(used,16);
  now=dayStart(day)+915*60000;await c.alarm();assert.equal(calls,24,'long scheduler gap collects one newest slot, not missed past slots');
  assert.equal(Object.values(c.ledger(day).counts).reduce((a,b)=>a+b,0),24);
 }finally{Date.now=realNow;}
});

test('scheduled shuttle slots survive duplicate alarms and reconstructed objects; visitors cannot poll',async()=>{
 const ctx=context(),realNow=Date.now,realFetch=globalThis.fetch;let now=dayStart('2026-11-16')+900*60000,calls=0,archives=0;
 Date.now=()=>now;
 const specs=JSON.parse(await readFile(new URL('./shuttle_catalog.json',import.meta.url),'utf8')).routes;
 const buckets=new Map();const env={HISTORY:{getByName:name=>{if(!buckets.has(name)){
  const d=new DailyHistory(context(),{}),append=d.append.bind(d);d.append=async record=>{archives++;assert.equal(record.kind,'shuttle_positions_v1');return append(record);};buckets.set(name,d);
 }return buckets.get(name);}}};
 globalThis.fetch=async(url,options)=>{assert.equal(url,'https://web.busin.co.kr/BuslineCircleS.aspx/GetRoute');calls++;
  const id=JSON.parse(options.body).data.split(',')[2],a=specs.find(x=>x.id===id).anchors[0];return new Response(JSON.stringify({d:`fixture/${a.x}/${a.y}/a/b/c`}));};
 try{
  let c=new Coordinator(ctx,env);c.put('shuttle_collection_enabled',true);await c.shuttles.tick();assert.equal(calls,10);assert.equal(archives,1);
  await c.shuttles.tick();assert.equal(calls,10);
  c=new Coordinator(ctx,env);await c.shuttles.tick();assert.equal(calls,10);
  assert.equal((await c.cachedShuttle({action:'claim',key:'shuttle-v2-41914'},now).json()).owned,false);
  now+=30000;await c.shuttles.tick();assert.equal(calls,13);assert.equal(archives,2);
  assert.equal((await c.shuttles.recording('2026-11-16')).routes.length,10);
 }finally{Date.now=realNow;globalThis.fetch=realFetch;}
});

test('scheduled shuttle collection stops before storage quota and does not disable city service',async()=>{
 const c=new Coordinator(context(),{}),realNow=Date.now,realFetch=globalThis.fetch;Date.now=()=>dayStart('2026-11-16')+900*60000;
 c.put('enabled',true);c.put('shuttle_collection_enabled',true);c.put('usage',{day:'2026-11-16',requests:0,reads:0,writes:65000});
 let calls=0;globalThis.fetch=async()=>{calls++;throw Error('forbidden');};
 try{await c.shuttles.tick();assert.equal(calls,0);assert.equal(c.get('enabled'),true);}finally{Date.now=realNow;globalThis.fetch=realFetch;}
});

test('R shadow claims deduplicate, preserve V11, reject location data and archive matched comparisons',async()=>{
 let appended=[];const env={HISTORY:{getByName:name=>({append:async row=>{appended.push({name,row});return {raw_bytes:100,reads:1,writes:3};}})}};
 const ctx=context();let c=new Coordinator(ctx,env),id='a'.repeat(32);
 assert.equal((await (await post(c,'/shadow/claim',{id})).json()).allowed,true);
 c=new Coordinator(ctx,env);assert.equal((await (await post(c,'/shadow/claim',{id})).json()).allowed,false);
 assert.equal((await post(c,'/shadow/record',{id,comparison:{status:'complete',legs:[{lat:37,lon:126}]}})).status,400);
 const value={status:'complete',created_at:Date.now()/1000,candidate_model:'R_fixture',operating_model:'V11',automatic_promotion:false,matched_candidate_deltas:[{wait_seconds:-20,total_seconds:10}]};
 assert.equal((await (await post(c,'/shadow/record',{id,comparison:value})).json()).saved,true);
 assert.equal(appended.length,1);assert(appended[0].name.startsWith('shadow:'));
 const status=await (await c.fetch(new Request('https://fixture/shadow/status'))).json();
 assert.equal(status.latest.candidate_model,'R_fixture');assert.equal(status.operating_model,'V11');assert.equal(status.automatic_promotion,false);
 assert.equal(status.aggregate.comparisons,1);assert.equal(status.aggregate.accuracy_validation,false);
});

test('R shadow claims fail closed at the daily cap or reduced write headroom',async()=>{
 const c=new Coordinator(context(),{}),day=kstDay(Date.now());
 for(let i=0;i<500;i++)c.sql.exec('INSERT INTO shadow_runs VALUES(?,?,?,?,?)',i.toString(16).padStart(32,'0'),day,Date.now()/1000,'claimed','{}');
 assert.equal((await (await post(c,'/shadow/claim',{id:'b'.repeat(32)})).json()).allowed,false);
 const other=new Coordinator(context(),{});other.put('usage',{day:new Date().toISOString().slice(0,10),requests:0,reads:0,writes:60000});
 assert.equal((await (await post(other,'/shadow/claim',{id:'c'.repeat(32)})).json()).allowed,false);
});

test('shuttle profiles use previous days, preserve timestamp bounds and restrict requested trip pairs',async()=>{
 const catalogueSha=JSON.parse(await readFile(new URL('./shuttle_catalog.json',import.meta.url),'utf8')).source_sha256;
 const buckets=new Map(),env={HISTORY:{getByName:name=>buckets.get(name)}};
 const c=new Coordinator(context(),env),realNow=Date.now;Date.now=()=>dayStart('2026-11-16')+960*60000;
 try{
  for(const day of ['2026-11-10','2026-11-11','2026-11-16','2026-11-17']){
   const seconds=day>='2026-11-16'?999:300,at=(dayStart(day)+960*60000)/1000;
   const box={n:6,samples:Array.from({length:6},(_,i)=>({lo:seconds-15,hi:seconds+15,seconds,known_at:at+i*60,at:at+i*60}))};
   const daily=new DailyHistory(context(),{});daily.sql.exec('INSERT INTO meta VALUES(?,?)','day',day);daily.sql.exec('INSERT INTO meta VALUES(?,?)','shuttle-catalogue-sha',catalogueSha);
   daily.sql.exec('INSERT INTO shuttle_stats VALUES(?,?)','41841',JSON.stringify({headways:{'departure:4:forward:16':box},rides:{'4:0:16':box,'4:1:16':box}}));
   buckets.set('shuttle:'+day,daily);
  }
  c.put('shuttle_archive_sizes',Object.fromEntries([...buckets.keys()].map(x=>[x.slice(8),{raw_bytes:1,aggregate_bytes:1}])));
  const p=await c.shuttles.profile(Date.now()/1000,Date.now()/1000,{'shuttle-41841':['4:0']});
  const r=p.routes['shuttle-41841'];assert.equal(r.rides['4:0'].length,8);assert.equal(r.rides['4:1'],undefined);
  assert(r.rides['4:0'].every(x=>x.seconds===300&&x.day<'2026-11-16'));assert.equal(new Set(r.rides['4:0'].map(x=>x.day)).size,2);
 }finally{Date.now=realNow;}
});

test('daily shuttle retention removes 30-day raw records but keeps statistics until one year',async()=>{
 const ctx=context(),d=new DailyHistory(ctx,{}),day='2026-11-16',realNow=Date.now;
 const record={format:'packed-v2',job_id:'retention-fixture',at:dayStart(day)/1000,routes:[]};
 await d.append(record);d.sql.exec('INSERT INTO shuttle_stats VALUES(?,?)','41841','{}');
 try{
  Date.now=()=>dayStart(day)+31*86400000;await d.alarm();
  assert.equal(d.sql.exec('SELECT COUNT(*) AS n FROM raw').toArray()[0].n,0);
  assert.equal(d.sql.exec('SELECT COUNT(*) AS n FROM shuttle_stats').toArray()[0].n,1);
  Date.now=()=>dayStart(day)+365*86400000;await d.alarm();
  assert.equal(ctx.db.prepare("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table'").get().n,0);
 }finally{Date.now=realNow;}
});

test('comparison retention runs even when shuttle collection is disabled',()=>{
 const c=new Coordinator(context(),{}),day='2026-11-16',old='2026-09-01';
 c.sql.exec('INSERT INTO shadow_runs VALUES(?,?,?,?,?)','old',old,1,'complete','{}');
 c.put('shadow_latest',{created_at:dayStart(old)/1000});c.put('shuttle_collection_enabled',false);
 c.cleanup(day);assert.equal(c.sql.exec('SELECT COUNT(*) AS n FROM shadow_runs').toArray()[0].n,0);assert.equal(c.get('shadow_latest'),null);
});
