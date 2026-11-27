import {DurableObject} from 'cloudflare:workers';
import profile from './demand.json';
import routeStops from './route_stops.json';
import {operatingPolicy,batchCalendar} from './policy_v2.mjs';
import {meteredSql} from './sql_meter.mjs';
import {ShuttleCollection} from './shuttle_collection.mjs';
import {updateShuttleStats,recordingRows,dayProfile} from './shuttle_stats.mjs';
import {updatePacked,travelSummary,crowdSummary,headwaySummary} from './packed_stats.mjs';
import {ROUTES,ROUTE_NAMES,LIMITS,START,END,kstDay,dayStart,schedule,chooseRoute,allowedReservation} from './schedule.mjs';

const names=ROUTE_NAMES;
const shuttleCacheKeys=new Set(['41841','41946','41914','41843','41942','41842','41869','41868','41915','41916'].map(id=>'shuttle-v2-'+id));
const json=(x,status=200,extra={})=>new Response(JSON.stringify(x),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',...extra}});
const auth=(req,env)=>Boolean(env.BACKEND_TOKEN)&&req.headers.get('Authorization')==='Bearer '+env.BACKEND_TOKEN;
const finite=(v)=>Number.isFinite(Number(v));
const providerTime=(s)=>/^\d{14}$/.test(String(s))?Date.parse(`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}T${s.slice(8,10)}:${s.slice(10,12)}:${s.slice(12,14)}+09:00`)/1000:null;
async function gzip(value){return new Uint8Array(await new Response(new Blob([JSON.stringify(value)+'\n']).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());}

export default {
  async fetch(req,env){
    const url=new URL(req.url);
    if(!auth(req,env))return json({error:'Unauthorized'},401);
    try{return await env.COORDINATOR.getByName('production-v1').fetch(req);}
    catch{return json({error:'shared_backend_unavailable'},503);}
  },
  async scheduled(event,env,ctx){ctx.waitUntil(env.COORDINATOR.getByName('production-v1').wake());}
};

export class Coordinator extends DurableObject {
  constructor(ctx,env){
    super(ctx,env);this.ctx=ctx;this.env=env;this.sql=ctx.storage.sql;
    this.sql.exec('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY,value TEXT NOT NULL)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY,day TEXT NOT NULL,pool TEXT NOT NULL,route TEXT NOT NULL,at INTEGER NOT NULL,ok INTEGER)');
    this.sql.exec('CREATE INDEX IF NOT EXISTS attempts_day ON attempts(day,pool)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS generic_calls(day TEXT,service TEXT,used INTEGER,PRIMARY KEY(day,service))');
    this.sql.exec('CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,day TEXT,created TEXT,record TEXT)');
    this.sql.exec("CREATE INDEX IF NOT EXISTS observation_candidate ON observations(json_extract(record,'$.candidate'))");
    this.sql.exec('CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,value TEXT,expires INTEGER,owner TEXT,lease INTEGER)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS vehicle_stops(id TEXT PRIMARY KEY,value TEXT)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS travel_samples(id TEXT PRIMARY KEY,day TEXT,route TEXT,from_seq INTEGER,to_seq INTEGER,seconds REAL)');
    this.sql.exec('CREATE INDEX IF NOT EXISTS travel_pair ON travel_samples(route,from_seq,to_seq,day)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS traffic_aggregate(day TEXT,route TEXT,hour INTEGER,weekday INTEGER,value TEXT,PRIMARY KEY(day,route,hour))');
    this.sql.exec('CREATE INDEX IF NOT EXISTS traffic_hour ON traffic_aggregate(route,hour,day)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS route_stats(day TEXT,route TEXT,value TEXT,PRIMARY KEY(day,route)) WITHOUT ROWID');
    this.sql.exec('CREATE INDEX IF NOT EXISTS route_stats_route_day ON route_stats(route,day)');
    this.pendingCost={reads:0,writes:0,requests:0,aux_writes:0};this.lastUsageFlush=0;this.auxMode=false;
    this.sql=meteredSql(this.sql,(reads,writes)=>{this.pendingCost.reads+=reads;this.pendingCost.writes+=writes;if(this.auxMode)this.pendingCost.aux_writes+=writes;});
    this.jobs=[];this.jobDay='';this.running=false;
    this.shuttleCache=null;this.shuttleCacheSavedAt=0;this.shuttleBudget=null;
    this.shuttles=new ShuttleCollection(this);
  }
  get(k,fallback=null){
    if(['latest','history_sizes'].includes(k)){
      const shared=this.sql.exec('SELECT value FROM state WHERE key=?','collection-v3').toArray()[0];
      if(shared)return JSON.parse(shared.value)[k]??fallback;
    }
    const r=this.sql.exec('SELECT value FROM state WHERE key=?',k).toArray()[0];return r?JSON.parse(r.value):fallback;
  }
  put(k,v){
    if(['latest','history_sizes'].includes(k)){v={latest:this.get('latest',{}),history_sizes:this.get('history_sizes',{}),[k]:v};k='collection-v3';}
    this.sql.exec('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',k,JSON.stringify(v));
  }
  async setAlarm(at){await this.ctx.storage.setAlarm(at);this.pendingCost.writes++;}
  counts(day){const c={baseline:0,peak:0,offpeak:0,retry:0};for(const r of this.sql.exec('SELECT pool,COUNT(*) AS n FROM attempts WHERE day=? GROUP BY pool',day))c[r.pool]=r.n;return c;}
  usage(now=Date.now()){
    const u=this.get('usage',{}),day=new Date(now).toISOString().slice(0,10);
    const current=u.day===day?u:{day,requests:0,reads:0,writes:0};
    const sizes=this.get('history_sizes',{});let bytes=0;
    for(const [d,v] of Object.entries(sizes))bytes+=typeof v==='number'?v:v.aggregate_bytes+((now-dayStart(d))/86400000<=31?v.raw_bytes:0);
    for(const [d,v] of Object.entries(this.get('shuttle_archive_sizes',{})))if(now-dayStart(d)<=365*86400000)
      bytes+=typeof v==='number'?(now-dayStart(d)<=31*86400000?v:0):(v.aggregate_bytes||0)+(now-dayStart(d)<=31*86400000?(v.raw_bytes||0):0);
    for(const [d,v] of Object.entries(this.get('shadow_archive_sizes',{})))if(now-dayStart(d)<=31*86400000)bytes+=v;
    const c={...current,requests:current.requests+this.pendingCost.requests,reads:current.reads+this.pendingCost.reads,writes:current.writes+this.pendingCost.writes,
      aux_writes:(current.aux_writes||0)+(this.pendingCost.aux_writes||0)};
    bytes+=Math.max(this.get('packed_total_bytes',0),Number(this.ctx.storage.sql.databaseSize)||0);
    const coordinatorBytes=Math.max(this.get('packed_total_bytes',0),Number(this.ctx.storage.sql.databaseSize)||0);
    const actual=this.get('platform_usage',{});
    const ratio=Math.max(c.requests/80000,c.reads/4000000,c.writes/100000,bytes/4000000000,coordinatorBytes/900000000,actual.ratio||0);
    return {...c,stored_bytes:bytes,ratio,warning:ratio>=.8,throttled:ratio>=.85,
      coordinator_bytes:coordinatorBytes,coordinator_storage_guard_bytes:900000000,
      write_target:70000,write_stop:85000,scope:'application_sql_cursor_metrics_and_estimated_requests_not_account_total'};
  }
  meter(){} // All local SQL is now counted from consumed cursor metadata.
  flushUsage(force=false){
    if(!force&&Date.now()-this.lastUsageFlush<60000)return;
    const value=this.usage();this.pendingCost={reads:0,writes:0,requests:0,aux_writes:0};
    this.put('usage',{day:value.day,requests:value.requests,reads:value.reads+8,writes:value.writes+4,aux_writes:value.aux_writes});
    this.pendingCost={reads:0,writes:0,requests:0,aux_writes:0};this.lastUsageFlush=Date.now();
  }
  auxExec(query,...args){
    if(this.usage().aux_writes+12>9000)throw Error('auxiliary_write_budget_exhausted');
    this.auxMode=true;try{return this.sql.exec(query,...args);}finally{this.auxMode=false;}
  }
  shuttleWriteAvailable(){
    const u=this.usage();return u.writes+32<65000&&!u.throttled;
  }
  reserveShuttleCall(day,limit){
    // Reserve a small block durably BEFORE calls. On eviction unused slots stay
    // charged; a restart can waste reservations, but can never reset the cap.
    if(!this.shuttleWriteAvailable())return false;
    return this.ctx.storage.transactionSync(()=>{
      let block=this.shuttleBudget;
      if(!block||block.day!==day||block.next>=block.end){
        const used=this.sql.exec('SELECT used FROM generic_calls WHERE day=? AND service=?',day,'busin_live').toArray()[0]?.used||0;
        if(used>=limit)return false;
        const end=Math.min(limit,used+32);
        this.sql.exec('INSERT OR REPLACE INTO generic_calls VALUES(?,?,?)',day,'busin_live',end);
        block={day,next:used,end};this.shuttleBudget=block;
      }
      if(block.next>=limit)return false;
      block.next++;return true;
    });
  }
  cachedShuttle(b,now){
    // One globally shared DO cache, not one cache per Vercel instance. The ten
    // ephemeral feeds do not need a SQLite lease + value write every 15 seconds.
    if(!this.shuttleCache){
      const saved=this.get('shuttle-cache-v1',{});this.shuttleCacheSavedAt=saved.at||0;
      this.shuttleCache=new Map(Object.entries(saved.entries||{}).filter(([key])=>shuttleCacheKeys.has(key))
        .map(([key,doc])=>[key,{...doc,owner:null,lease:0}]));
      for(const doc of this.sql.exec('SELECT * FROM cache WHERE key IN ('+[...shuttleCacheKeys].map(()=>'?').join(',')+')',...shuttleCacheKeys)){
        if(!this.shuttleCache.has(doc.key))this.shuttleCache.set(doc.key,{value:JSON.parse(doc.value||'null'),expires:doc.expires,owner:null,lease:0});
      }
    }
    const doc=this.shuttleCache.get(b.key),value=doc?.value??null;
    if(b.action==='read')return json(doc?{value,expires_at:doc.expires/1000}:{});
    if(b.action==='claim'){
      // Once the scheduler owns these feeds, visitors only consume its cache.
      if(this.shuttles.enabled())return json({owned:false,value,scheduled:true});
      if(doc&&(doc.expires>now||doc.lease>now))return json({owned:false,value});
      const owner=crypto.randomUUID();this.shuttleCache.set(b.key,{value,expires:doc?.expires||0,owner,lease:now+55000});
      return json({owned:true,owner,value});
    }
    if(!b.owner||doc?.owner!==b.owner||doc.lease<=now)return json({saved:false},409);
    if(b.action==='publish'){
      this.shuttleCache.set(b.key,{value:b.value,expires:now+Math.min(120,Math.max(1,b.seconds||15))*1000,owner:null,lease:0});
      // A single compact checkpoint per minute keeps last observations across
      // restarts. It uses total-write headroom, independent of the auxiliary cap.
      if(now-this.shuttleCacheSavedAt>=60000&&this.shuttleWriteAvailable()){
        this.put('shuttle-cache-v1',{at:now,entries:Object.fromEntries([...this.shuttleCache].map(([key,d])=>[key,{value:d.value,expires:d.expires}]))});
        this.shuttleCacheSavedAt=now;
      }
      return json({saved:true});
    }
    if(b.action==='release'){doc.owner=null;doc.lease=0;return json({saved:true});}
    return json({saved:false},409);
  }
  policy(day=kstDay(Date.now())){return operatingPolicy(day,this.get('provider_approved_limit',1000));}
  ledger(day){
    const book=this.get('ledger-v2',{});
    return book.day===day?book:{day,spent:Object.fromEntries(this.sql.exec('SELECT id FROM attempts WHERE day=?',day).toArray().map(r=>[r.id,true])),counts:this.legacyCounts(day),retries:[]};
  }
  legacyCounts(day){const c={baseline:0,peak:0,offpeak:0,retry:0};for(const r of this.sql.exec('SELECT pool,COUNT(*) AS n FROM attempts WHERE day=? GROUP BY pool',day))c[r.pool]=r.n;return c;}
  reserveBatch(jobs,now){
    return this.ctx.storage.transactionSync(()=>{
      const day=kstDay(now),policy=this.policy(day),book=this.ledger(day),accepted=[];
      let used=Object.values(book.counts).reduce((s,n)=>s+n,0);
      for(const j of jobs){
        if(!j.id.startsWith(day+':')||book.spent[j.id])continue;
        const retry=j.pool==='retry',retriesUsed=book.counts.retry||0;
        if(used>=policy.cap||!retry&&used-retriesUsed>=policy.cap-policy.reserve||retry&&retriesUsed>=policy.reserve)continue;
        book.spent[j.id]=true;book.counts[j.pool]=(book.counts[j.pool]||0)+1;used++;accepted.push(j);
      }
      if(accepted.length)this.put('ledger-v2',book); // Reservation is durable before any HTTP request.
      return accepted;
    });
  }
  reserve(job,route,now){
    return this.ctx.storage.transactionSync(()=>{
      if(this.sql.exec('SELECT id FROM attempts WHERE id=?',job.id).toArray().length)return false;
      const day=kstDay(now);if(!job.id.startsWith(day+':')||!allowedReservation(this.counts(day),job.pool))return false;
      this.sql.exec('INSERT INTO attempts VALUES(?,?,?,?,?,NULL)',job.id,day,job.pool,route,now);
      return true;
    });
  }
  async wake(){
    this.pendingCost.requests++;this.flushUsage();
    await this.shuttles.tick();await this.shuttles.arm();
    const day=kstDay(Date.now());if(this.get('cleanup_day')!==day){this.cleanup(day);this.put('cleanup_day',day);}
    if(!this.get('enabled',false))return;
    const a=await this.ctx.storage.getAlarm();
    if(a===null||a<Date.now()-60000)await this.setAlarm(Date.now()+1000);
  }
  async alarm(){
    if(this.running)return;this.running=true;
    try{await this.runBatchAlarm();}catch(e){
      try{this.put('enabled',false);this.put('collector_error','durable_collection_or_archive_unavailable');}catch{}
      throw e;
    }finally{this.running=false;await this.shuttles.tick();await this.shuttles.arm();}
  }
  async runBatchAlarm(){
    const now=Date.now(),day=kstDay(now);this.pendingCost.requests++;
    if(!this.get('enabled',false))return;
    await this.setAlarm(now+60000);
    const policy=this.policy(day),book=this.ledger(day),latest=this.get('latest',{});
    const calendar=policy.cap>950?batchCalendar(day,policy).flatMap(g=>g.routes.map(route=>({id:g.id+':'+route,at:g.at,pool:g.pool,route}))):schedule(day,profile);
    const all=[...calendar,...book.retries].sort((a,b)=>a.at-b.at);
    const due=all.filter(j=>j.at<=now&&j.at>=now-60000&&!book.spent[j.id]);
    // One newest due slot, never a catch-up burst of missed fifteen-second jobs.
    const slot=due.at(-1)?.at;
    let jobs=due.filter(j=>j.at===slot).map(j=>({...j,route:chooseRoute(j,latest,profile,day,now)})).filter(j=>j.route);
    if(policy.cap>950)jobs=jobs.filter(j=>now-(latest[j.route]?.attempted_at||0)>=((latest[j.route]?.duplicate_count||0)>=2?60000:15000));
    const u=this.usage();
    if(u.writes>=85000||u.ratio>=.9)jobs=[];
    else if(u.writes-(u.aux_writes||0)>=70000||u.throttled)jobs=jobs.filter(j=>!['peak','offpeak'].includes(j.pool));
    if(now<dayStart(day)+START*60000||now>=dayStart(day)+(END+1)*60000||!this.env.SEOUL_BUS_SERVICE_KEY)jobs=[];
    const reserved=this.reserveBatch(jobs,now),records=[];
    // Network calls run concurrently; state mutations below remain serialized.
    const results=await Promise.all(reserved.map(async j=>({job:j,result:await this.collect(j.route,j,latest[j.route]||{})})));
    const updated=this.ledger(day),priorRetries=JSON.stringify(updated.retries);
    updated.retries=updated.retries.filter(j=>j.at>now&&!updated.spent[j.id]);
    this.ctx.storage.transactionSync(()=>{
      let delta=0;for(const {job,result} of results)delta+=this.recordPacked(job.route,result.raw_record.vehicles,false);
      if(delta)this.put('packed_total_bytes',Math.max(0,this.get('packed_total_bytes',0)+delta));
    });
    for(const {job,result} of results){
      const raw=result.raw_record;delete result.raw_record;latest[job.route]=result;
      if(!result.duplicate||raw.traffic||raw.error)records.push(raw);
      if(result.error&&(job.retry||0)<2)updated.retries.push({id:`${day}:v2retry:${job.id}:${(job.retry||0)+1}`,at:Date.now()+30000,
        pool:'retry',route:job.route,retry:(job.retry||0)+1});
    }
    if(reserved.length){
      const sizes=this.get('history_sizes',{});
      if(JSON.stringify(updated.retries)!==priorRetries)this.put('ledger-v2',updated);
      if(records.length){
        const archive=this.env.HISTORY.getByName(day),packed={format:'packed-v2',job_id:'batch-v2:'+reserved.map(j=>j.id).sort().join('|'),at:now/1000,
          vehicles:records.flatMap(r=>r.vehicles),route_records:records.map(({vehicles,...r})=>({...r,vehicle_count:vehicles.length}))};
        const archived=await archive.append(packed);this.pendingCost.requests++;
        this.pendingCost.reads+=archived.reads||0;this.pendingCost.writes+=archived.writes||0;
        sizes[day]={raw_bytes:archived.raw_bytes,aggregate_bytes:0};
      }
      // Latest positions and archive byte counters commit together in one row.
      this.put('collection-v3',{latest,history_sizes:sizes});
    }
    const future=[...calendar,...updated.retries].filter(j=>j.at>Date.now()&&!updated.spent[j.id]).map(j=>j.at);
    const tomorrow=dayStart(kstDay(now+86400000))+START*60000;
    const next=Math.max(Date.now()+1000,Math.min(tomorrow,...future));
    this.put('next_scheduled_at',next);await this.setAlarm(next);this.flushUsage();
    if(this.get('cleanup_day')!==day){this.cleanup(day);this.put('cleanup_day',day);}
  }
  recordPacked(route,vehicles,updateSize=true){
    if(!vehicles.length)return 0;
    const day=kstDay(Date.now()),row=this.sql.exec('SELECT value FROM route_stats WHERE day=? AND route=?',day,route).toArray()[0];
    const result=updatePacked(row?JSON.parse(row.value):null,vehicles,routeStops[route]||[],day);
    if(result.changed){
      const text=JSON.stringify(result.value);if(new TextEncoder().encode(text).length>1500000)throw Error('packed_statistics_too_large');
      const delta=new TextEncoder().encode(text).length-(row?new TextEncoder().encode(row.value).length:0);
      this.sql.exec('INSERT INTO route_stats VALUES(?,?,?) ON CONFLICT(day,route) DO UPDATE SET value=excluded.value',day,route,text);
      if(updateSize)this.put('packed_total_bytes',Math.max(0,this.get('packed_total_bytes',0)+delta));
      return delta;
    }
    return 0;
  }
  historyFor(when){
    if(!finite(when))throw Error('Invalid prediction timestamp');
    const date=new Date(Number(when)*1000+9*3600000),hour=date.getUTCHours(),weekday=(date.getUTCDay()+6)%7;
    const cutoff=kstDay(Math.min(Date.now(),Number(when)*1000)),traffic={},travel={},crowd={},headways={};
    const median=a=>a.sort((x,y)=>x-y)[Math.floor(a.length/2)];
    for(const route of ROUTES){
      const rows=this.sql.exec('SELECT day,weekday,value FROM traffic_aggregate WHERE route=? AND hour=? AND day<? ORDER BY day DESC LIMIT 56',route,hour,cutoff).toArray();
      const matched=rows.filter(r=>r.weekday===weekday),chosen=matched.length>=3?matched:rows,groups={};
      for(const r of chosen)for(const [seq,a] of Object.entries(JSON.parse(r.value)))(groups[seq]||=[]).push(median(a));
      traffic[route]={weekday,hour,dates:chosen.map(r=>r.day),cohort:matched.length>=3?'same_weekday_hour':'pooled_hour',
        sections:Object.fromEntries(Object.entries(groups).map(([seq,a])=>[seq,{speed_kmh:median(a),days:a.length}]))};
      const packed=this.sql.exec('SELECT day,value FROM route_stats WHERE route=? AND day<? ORDER BY day DESC LIMIT 56',route,cutoff).toArray().map(r=>({...r,value:JSON.parse(r.value)}));
      const same=packed.filter(r=>(new Date(r.day+'T12:00:00+09:00').getUTCDay()+6)%7===weekday);
      const cohort=same.length>=3?same:packed;
      Object.assign(travel,travelSummary(cohort,route,hour));
      crowd[route]={...crowdSummary(cohort,route,hour),weekday,cohort:same.length>=3?'same_weekday_hour':'pooled_hour'};
      headways[route]=headwaySummary(cohort,route,hour);
      for(const item of Object.values(headways[route]))item.weekday=weekday;
    }
    return {historical_traffic:traffic,travel_history:travel,crowd_history:crowd,headway_history:headways,traffic:{},before_date:cutoff,requested_at:Number(when),
      source:'completed_prior_dates_only',label:'완료된 이전 날짜·요청 요일·시간의 기록만 사용',live_observations_used:false};
  }
  cleanup(day){
    const old=kstDay(dayStart(day)-2*86400000),year=kstDay(dayStart(day)-365*86400000);
    this.sql.exec('DELETE FROM attempts WHERE day<?',old);this.sql.exec('DELETE FROM generic_calls WHERE day<?',old);
    this.sql.exec('DELETE FROM observations WHERE day<?',year);this.sql.exec('DELETE FROM cache WHERE expires<? AND lease<?',Date.now()-86400000,Date.now());
    this.sql.exec('DELETE FROM travel_samples WHERE day<?',year);
    this.sql.exec('DELETE FROM traffic_aggregate WHERE day<?',year);
    this.sql.exec('DELETE FROM route_stats WHERE day<?',year);
    this.put('packed_total_bytes',this.sql.exec('SELECT COALESCE(SUM(length(value)),0) AS n FROM route_stats').toArray()[0].n);
    const sizes=this.get('history_sizes',{});for(const d of Object.keys(sizes))if(d<year)delete sizes[d];this.put('history_sizes',sizes);
    this.shuttles.cleanup(day);
  }
  async collect(route,job,previous){
    const at=Date.now();let rows=[];let error=null;let payload=null;
    try{
      const url=new URL('http://ws.bus.go.kr/api/rest/buspos/getBusPosByRtid');
      url.search=new URLSearchParams({serviceKey:decodeURIComponent(this.env.SEOUL_BUS_SERVICE_KEY),busRouteId:route,resultType:'json'});
      const response=await fetch(url,{signal:AbortSignal.timeout(8000),headers:{'User-Agent':'SNU-Route-Lab/0.4'}});
      if(!response.ok)throw new Error('provider_http_'+response.status);
      payload=await response.json();const code=String(payload.msgHeader?.headerCd);
      if(!['0','4'].includes(code))throw new Error('provider_code_'+code);
      rows=payload.msgBody?.itemList||[];if(!Array.isArray(rows))rows=[rows];
      rows=rows.filter(v=>finite(v.gpsY)&&finite(v.gpsX)&&v.gpsY>=33&&v.gpsY<=39&&v.gpsX>=124&&v.gpsX<=132).map(v=>({
        id:String(v.vehId||''),route_id:route,route_name:names[route],lat:Number(v.gpsY),lon:Number(v.gpsX),
        provided_at:providerTime(v.dataTm),captured_at:at/1000,section_order:String(v.sectOrd||''),section_distance_raw:Number(v.sectDist)||0,
        at_stop:String(v.stopFlag)==='1',full:String(v.isFullFlag)==='1',full_known:['0','1'].includes(String(v.isFullFlag)),crowd_code:String(v.congetion||'0'),
        crowd_label:({'3':'여유','4':'보통','5':'혼잡','6':'매우혼잡'})[String(v.congetion)]||'정보 없음'}));
      for(const v of rows){
        const prior=(previous.vehicles||[]).find(p=>p.id===v.id);
        if(prior&&v.provided_at>prior.provided_at)v.previous_observation={lat:prior.lat,lon:prior.lon,provided_at:prior.provided_at,section_order:prior.section_order};
        else if(prior?.previous_observation)v.previous_observation=prior.previous_observation;
      }
    }catch(e){error=String(e.message||'provider_unavailable').replace(/https?:\S+/g,'[redacted]').slice(0,100);}
    const traffic=await this.collectTraffic(route);

    const signature=rows.map(v=>v.id+':'+v.provided_at).sort().join('|');
    const duplicate=!error&&signature&&signature===previous.signature;
    const record={job_id:job.id,route_id:route,at:at/1000,error,vehicles:rows,...(traffic?{traffic}: {})};
    return {...previous,raw_record:record,duplicate:Boolean(duplicate),attempted_at:at,error,duplicate_count:duplicate?(previous.duplicate_count||0)+1:0,
      ...(!error?{vehicles:rows,captured_at:at/1000,signature,changed:JSON.stringify(rows.map(v=>v.crowd_code))!==JSON.stringify((previous.vehicles||[]).map(v=>v.crowd_code))}:{})};
  }
  async collectTraffic(route){
    const all=this.get('traffic',{}),now=Date.now();if(now/1000-(all[route]?.fetched_at||0)<600)return null;
    const day=kstDay(now),reserved=this.ctx.storage.transactionSync(()=>{
      const n=this.sql.exec('SELECT used FROM generic_calls WHERE day=? AND service=?',day,'seoul_route_traffic').toArray()[0]?.used||0;
      if(n>=600)return false;
      this.sql.exec('INSERT OR REPLACE INTO generic_calls VALUES(?,?,?)',day,'seoul_route_traffic',n+1);return true;
    });
    if(!reserved)return null;
    try{
      const url=new URL('http://ws.bus.go.kr/api/rest/busRouteInfo/getStaionByRoute');url.search=new URLSearchParams({serviceKey:decodeURIComponent(this.env.SEOUL_BUS_SERVICE_KEY),busRouteId:route,resultType:'json'});
      const response=await fetch(url,{signal:AbortSignal.timeout(8000),headers:{'User-Agent':'SNU-Route-Lab/0.5'}});
      if(!response.ok)throw Error('traffic HTTP error');const data=await response.json();
      if(String(data.msgHeader?.headerCd)!=='0')throw Error('traffic provider error');
      let rows=data.msgBody?.itemList||[];if(!Array.isArray(rows))rows=[rows];
      const sections={};for(const r of rows){const speed=Number(r.sectSpd),seq=Number(r.seq);if(seq>0&&speed>=.5&&speed<=100)sections[seq]={speed_kmh:speed,reported_m:Number(r.fullSectDist)||null};}
      const value={fetched_at:now/1000,provider_timestamp:null,sections,source:'서울시 노선정보조회 구간 소통속도',unit:'km/h',kind:'provider_section_speed_not_completed_trip'};
      const merged=this.get('traffic',{});merged[route]=value;this.put('traffic',merged);this.recordTraffic(route,value);return value;
    }catch{return null;}
  }
  recordTraffic(route,traffic){
    const day=kstDay(traffic.fetched_at*1000),date=new Date(traffic.fetched_at*1000+9*3600000),hour=date.getUTCHours(),weekday=(date.getUTCDay()+6)%7;
    const previous=this.sql.exec('SELECT value FROM traffic_aggregate WHERE day=? AND route=? AND hour=?',day,route,hour).toArray()[0];
    const cells=previous?JSON.parse(previous.value):{};
    for(const [seq,point] of Object.entries(traffic.sections))cells[seq]=[...(cells[seq]||[]),point.speed_kmh].slice(-6);
    this.sql.exec('INSERT OR REPLACE INTO traffic_aggregate VALUES(?,?,?,?,?)',day,route,hour,weekday,JSON.stringify(cells));
    const past=this.sql.exec('SELECT day,weekday,value FROM traffic_aggregate WHERE route=? AND hour=? AND day<? ORDER BY day DESC LIMIT 365',route,hour,day).toArray();
    const matched=past.filter(r=>r.weekday===weekday),chosen=matched.length>=3?matched:past,grouped={};
    const median=values=>{values.sort((a,b)=>a-b);return values[Math.floor(values.length/2)];};
    for(const r of chosen)for(const [seq,values] of Object.entries(JSON.parse(r.value)))(grouped[seq]||=[]).push(median(values));
    const profiles=this.get('historical_traffic',{});profiles[route]={weekday,hour,cohort:matched.length>=3?'same_weekday_hour':'pooled_hour',
      dates:chosen.map(r=>r.day),sections:Object.fromEntries(Object.entries(grouped).map(([seq,values])=>[seq,{speed_kmh:median(values),days:values.length}])),
      source:'과거 서울시 구간속도의 날짜별 중앙값 · 교통카드 인원 자료와 별도'};
    this.put('historical_traffic',profiles);this.meter(past.length+3,5);
  }
  status(){
    const now=Date.now(),latest=this.get('latest',{}),counts=this.ledger(kstDay(now)).counts,policy=this.policy(kstDay(now));
    const used=Object.values(counts).reduce((s,x)=>s+x,0);
    const services={};for(const r of this.sql.exec('SELECT service,used FROM generic_calls WHERE day=?',kstDay(now)))services[r.service]=r.used;
    return {captured_at:Math.max(0,...Object.values(latest).map(v=>v.captured_at||0))||null,service_calls:services,
      traffic:this.get('traffic',{}),historical_traffic:this.get('historical_traffic',{}),travel_history:this.get('travel_summary',{}),
      vehicles:Object.values(latest).flatMap(v=>v.vehicles||[]),routes:ROUTES.map(id=>({id,name:names[id],captured_at:latest[id]?.captured_at||null,error:latest[id]?.error||null})),
      errors:Object.entries(latest).filter(([,v])=>v.error).map(([id,v])=>names[id]+': '+v.error),
      source:'서울시 버스위치정보 OpenAPI',position_calls_today:used,position_calls_remaining:Math.max(0,policy.cap-used),position_app_daily_limit:policy.cap,collection_policy:policy,
      budget_pools:counts,budget_limits:policy.cap>950?{baseline:policy.weekend?356*ROUTES.length:236*ROUTES.length,
        peak:policy.weekend?0:Math.ceil(14400/policy.peak_seconds)*ROUTES.length,offpeak:0,retry:policy.reserve}:LIMITS,
      next_scheduled_at:(this.get('next_scheduled_at')||0)/1000||null,
      enabled:this.get('enabled',false),configured:Boolean(this.env.SEOUL_BUS_SERVICE_KEY),usage:this.usage(),shadow_collection:this.shuttles.shadowAvailability(),
      mode:this.get('enabled',false)?'scheduled':'collector_paused',server_time:now/1000};
  }
  async fetch(req){
    const url=new URL(req.url),path=url.pathname;this.pendingCost.requests++;
    if(path.startsWith('/shuttle/')||path.startsWith('/shadow/')){
      const response=await this.shuttles.handle(req,url);if(response)return response;
    }
    if(path==='/snapshot'||path==='/status')return json(this.status());
    if(path==='/history')return json(this.historyFor(Number(url.searchParams.get('when'))));
    if(path==='/recording'){
      const day=url.searchParams.get('day')||kstDay(Date.now());
      if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return json({error:'Invalid day'},400);
      const rows=this.sql.exec('SELECT route,value FROM route_stats WHERE day=?',day).toArray();
      return json({day,raw_retention_days:30,aggregate_retention_days:365,
        unit:'deduplicated_vehicle_section_observations_not_passengers',routes:rows.map(({route,value})=>{
          const p=JSON.parse(value),a=Object.values(p.availability||{});
          return {route,grade_observations:Object.values(p.grades||{}).reduce((a,b)=>a+b,0),
            known_full_flag_observations:a.reduce((n,x)=>n+x[1],0),full_flag_observations:a.reduce((n,x)=>n+x[0],0),
            observed_stop_headways:Object.values(p.headways||{}).reduce((n,x)=>n+x.n,0),
            bytes:new TextEncoder().encode(value).length};})});
    }
    if(req.method==='POST'&&path==='/control'){
      const b=await req.json();if(typeof b.enabled!=='boolean')return json({error:'enabled required'},400);if(b.provider_approved_limit!==undefined){if(![1000,10000,15000].includes(b.provider_approved_limit))return json({error:'unsupported approved limit'},400);this.put('provider_approved_limit',b.provider_approved_limit);if(b.enabled)await this.ctx.storage.setAlarm(Date.now()+1000);}
      if(typeof b.enabled!=='boolean')return json({error:'enabled required'},400);
      if(b.enabled&&!this.env.SEOUL_BUS_SERVICE_KEY)return json({error:'Provider key missing'},409);
      this.put('enabled',b.enabled);if(b.enabled)await this.wake();else await this.ctx.storage.deleteAlarm();return json(this.status());
    }
    if(req.method==='POST'&&path==='/usage'){
      const b=await req.json();if(!finite(b.ratio)||b.ratio<0)return json({error:'invalid usage'},400);
      this.put('platform_usage',{ratio:Number(b.ratio),at:Date.now()});return json(this.usage());
    }
    if(path==='/observations'){
      if(req.method==='GET')return json({records:this.sql.exec('SELECT record FROM observations ORDER BY created DESC LIMIT 100').toArray().map(r=>JSON.parse(r.record))});
      if(req.method==='POST'){
        const b=await req.json();const n=Number(b.actual_seconds),p=Number(b.planned_seconds);
        if(!finite(n)||!finite(p)||n<=0||n>14400||p<=0||p>10800)return json({error:'invalid observation'},400);
        const id=crypto.randomUUID(),record={...b,id};delete record.lat;delete record.lon;delete record.origin;
        this.auxExec('INSERT INTO observations VALUES(?,?,?,?)',id,kstDay(Date.now()),new Date().toISOString(),JSON.stringify(record));
        return json({id,saved:true},201);
      }
    }
    if(path==='/observation-errors'&&req.method==='POST'){
      const b=await req.json();if(!Array.isArray(b.keys)||b.keys.length>40||b.keys.some(x=>!/^[a-f0-9]{24}$/.test(x)))return json({error:'invalid candidates'},400);
      if(!b.keys.length)return json({records:[]});
      const records=this.sql.exec("SELECT record FROM observations WHERE json_extract(record,'$.candidate') IN ("+b.keys.map(()=>'?').join(',')+") ORDER BY created DESC LIMIT 5000",...b.keys).toArray().map(r=>JSON.parse(r.record));
      return json({records});
    }
    if(req.method==='POST'&&path==='/budget'){
      const b=await req.json();if(this.usage().writes>=65000)return json({allowed:false,reason:'write_headroom_reserved_for_collector'});if(!['public_arrivals','busin_live'].includes(b.service))return json({allowed:false});
      const day=kstDay(Date.now()),limit=Math.min(b.service==='busin_live'?6000:1200,Math.max(0,Number(b.limit)||0));
      if(b.service==='busin_live')return json({allowed:this.reserveShuttleCall(day,limit),reservation_block_size:32});
      const ok=this.ctx.storage.transactionSync(()=>{
        const row=this.sql.exec('SELECT used FROM generic_calls WHERE day=? AND service=?',day,b.service).toArray()[0];
        if((row?.used||0)>=limit)return false;
        this.auxExec('INSERT OR REPLACE INTO generic_calls VALUES(?,?,?)',day,b.service,(row?.used||0)+1);return true;
      });return json({allowed:ok});
    }
    if(req.method==='POST'&&path==='/cache'){
      const b=await req.json(),now=Date.now();if(!/^[a-zA-Z0-9_-]{1,150}$/.test(b.key||''))return json({error:'invalid cache key'},400);
      if(shuttleCacheKeys.has(b.key))return this.cachedShuttle(b,now);
      const doc=this.sql.exec('SELECT * FROM cache WHERE key=?',b.key).toArray()[0];
      if(b.action==='read')return json(doc?{value:JSON.parse(doc.value||'null'),expires_at:doc.expires/1000}:{});
      if(b.action==='claim'){
        if(doc&&(doc.expires>now||doc.lease>now))return json({owned:false,value:JSON.parse(doc.value||'null')});
        const owner=crypto.randomUUID();this.auxExec('INSERT OR REPLACE INTO cache VALUES(?,?,?,?,?)',b.key,doc?.value||'null',doc?.expires||0,owner,now+55000);
        return json({owned:true,owner,value:JSON.parse(doc?.value||'null')});
      }
      if(b.action==='publish'&&doc?.owner===b.owner){this.auxExec('UPDATE cache SET value=?,expires=?,lease=0 WHERE key=?',JSON.stringify(b.value),now+Math.min(120,Math.max(1,b.seconds||15))*1000,b.key);return json({saved:true});}
      if(b.action==='release'&&doc?.owner===b.owner){this.auxExec('UPDATE cache SET lease=0 WHERE key=?',b.key);return json({saved:true});}
      return json({saved:false},409);
    }
    if(path==='/export'||path==='/aggregate'){
      const day=url.searchParams.get('day');if(!/^\d{4}-\d{2}-\d{2}$/.test(day||''))return json({error:'day required'},400);
      if(path==='/aggregate'){
        const packed=this.sql.exec('SELECT route,value FROM route_stats WHERE day=?',day).toArray();
        if(packed.length)return json({unit:'observed_vehicle_section_passage_labels',rows:packed.flatMap(({route,value})=>
          Object.entries(JSON.parse(value).grades||{}).map(([key,n])=>{const [section,slot,grade]=key.split(':');return {route,section,slot:Number(slot),grade,n};})),
          raw_expires_after_days:30,aggregate_expires_after_days:365,source:'packed_route_statistics'});
      }
      const a=this.env.HISTORY.getByName(day);return path==='/export'?a.export():json(await a.aggregate());
    }
    return json({error:'Not found'},404);
  }
}

export class DailyHistory extends DurableObject {
  constructor(ctx,env){
    super(ctx,env);this.ctx=ctx;this.sql=ctx.storage.sql;
    this.sql.exec('CREATE TABLE IF NOT EXISTS raw(id TEXT PRIMARY KEY,at REAL,payload BLOB)');
    this.sql.exec('CREATE INDEX IF NOT EXISTS raw_at ON raw(at)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS passages(id TEXT PRIMARY KEY,route TEXT,section TEXT,slot INTEGER,grade TEXT,at REAL)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS progress(id TEXT PRIMARY KEY,section INTEGER,trip INTEGER,at REAL)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS shuttle_stats(route TEXT PRIMARY KEY,value TEXT) WITHOUT ROWID');
    this.cost={reads:0,writes:0};
    this.sql=meteredSql(this.sql,(reads,writes)=>{this.cost.reads+=reads;this.cost.writes+=writes;});
  }
  async updateShuttles(records,catalogueSha){
    const before={...this.cost};
    this.ctx.storage.transactionSync(()=>{
      const stored=this.sql.exec('SELECT value FROM meta WHERE key=?','shuttle-catalogue-sha').toArray()[0]?.value;
      if(stored&&stored!==catalogueSha)throw Error('shuttle_catalogue_changed_midday');
      if(!stored&&catalogueSha)this.sql.exec('INSERT INTO meta VALUES(?,?)','shuttle-catalogue-sha',catalogueSha);
      for(const record of records){
        if(record.value.error)continue;
        const old=this.sql.exec('SELECT value FROM shuttle_stats WHERE route=?',record.route).toArray()[0];
        const value=updateShuttleStats(old?JSON.parse(old.value):null,record.value,{anchor_count:record.anchor_count});
        this.sql.exec('INSERT INTO shuttle_stats VALUES(?,?) ON CONFLICT(route) DO UPDATE SET value=excluded.value',record.route,JSON.stringify(value));
      }
    });
    const bytes=this.sql.exec('SELECT COALESCE(SUM(length(value)),0) AS n FROM shuttle_stats').toArray()[0].n;
    return {aggregate_bytes:bytes,reads:this.cost.reads-before.reads,writes:this.cost.writes-before.writes};
  }
  async shuttleRecording(){
    const day=this.sql.exec('SELECT value FROM meta WHERE key=?','day').toArray()[0]?.value;
    return recordingRows(this.sql.exec('SELECT route,value FROM shuttle_stats').toArray(),day);
  }
  async shuttleProfile(hour,wanted,catalogueSha){
    const stored=this.sql.exec('SELECT value FROM meta WHERE key=?','shuttle-catalogue-sha').toArray()[0]?.value;
    if(catalogueSha&&stored!==catalogueSha)return {};
    const day=this.sql.exec('SELECT value FROM meta WHERE key=?','day').toArray()[0]?.value;
    return dayProfile(this.sql.exec('SELECT route,value FROM shuttle_stats').toArray(),day,hour,wanted);
  }
  async append(record){
    if(record.format==='packed-v2'){
      const day=kstDay(record.at*1000),data=await gzip(record),before={...this.cost};
      if(data.byteLength>1500000)throw Error('archive_row_too_large');
      const bytes=this.ctx.storage.transactionSync(()=>{
        const saved=this.sql.exec('SELECT value FROM meta WHERE key=?','packed-v2-totals').toArray()[0];
        // One migration scan for existing archives, then constant-size metadata reads.
        const totals=saved?JSON.parse(saved.value):{raw_bytes:this.sql.exec('SELECT COALESCE(SUM(length(payload)),0) AS bytes FROM raw').toArray()[0].bytes};
        const exists=this.sql.exec('SELECT id FROM raw WHERE id=?',record.job_id).toArray().length;
        if(!exists){
          this.sql.exec('INSERT INTO raw VALUES(?,?,?)',record.job_id,record.at,data);totals.raw_bytes+=data.byteLength;
          this.sql.exec('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value','packed-v2-totals',JSON.stringify(totals));
        }
        this.sql.exec('INSERT OR IGNORE INTO meta VALUES(?,?)','day',day);
        return totals.raw_bytes;
      });
      let alarmWrites=0;
      if(!await this.ctx.storage.getAlarm()){await this.ctx.storage.setAlarm(record.at*1000+30*86400000+1000);alarmWrites=1;}
      return {raw_bytes:bytes,aggregate_bytes:0,reads:this.cost.reads-before.reads,writes:this.cost.writes-before.writes+alarmWrites};
    }
    const day=kstDay(record.at*1000),data=await gzip(record);
    if(data.byteLength>1500000)throw new Error('archive_row_too_large');
    this.sql.exec('INSERT OR IGNORE INTO raw VALUES(?,?,?)',record.job_id,record.at,data);
    this.sql.exec('INSERT OR IGNORE INTO meta VALUES(?,?)','day',day);
    let writes=2,reads=3;
    for(const v of record.vehicles){
      if(!v.provided_at||!['3','4','5','6'].includes(v.crowd_code))continue;
      // Progress changes identify passages; repeated polls at a stopped bus add no labels.
      const id=v.route_id+':'+v.id,section=Number(v.section_order),slot=Math.floor((v.provided_at*1000-dayStart(day))/900000);
      if(!Number.isInteger(section)||section<1)continue;
      const previous=this.sql.exec('SELECT * FROM progress WHERE id=?',id).toArray()[0];
      reads++;
      if(previous&&(v.provided_at<=previous.at||section===previous.section))continue;
      const trip=(previous?.trip||0)+(previous&&section<previous.section-5?1:0);
      this.sql.exec('INSERT OR REPLACE INTO progress VALUES(?,?,?,?)',id,section,trip,v.provided_at);
      this.sql.exec('INSERT OR IGNORE INTO passages VALUES(?,?,?,?,?,?)',`${id}:${trip}:${section}`,v.route_id,v.section_order,slot,v.crowd_code,v.provided_at);
      writes+=2;
    }
    const count=this.sql.exec('SELECT COALESCE(SUM(length(payload)),0) AS bytes FROM raw').toArray()[0].bytes;
    if(!await this.ctx.storage.getAlarm())await this.ctx.storage.setAlarm(record.at*1000+30*86400000+1000);
    const aggregate=this.sql.exec('SELECT COUNT(*) AS n FROM passages').toArray()[0].n*160;
    return {bytes:count+aggregate,raw_bytes:count,aggregate_bytes:aggregate,reads,writes};
  }
  async aggregate(){return {unit:'observed_vehicle_section_passage_labels',rows:this.sql.exec('SELECT route,section,slot,grade,COUNT(*) AS n FROM passages GROUP BY route,section,slot,grade').toArray(),raw_expires_after_days:30,aggregate_expires_after_days:365};}
  async export(filename='snu-bus-observations.jsons.gz'){
    if(!/^snu-[a-z0-9.-]+\.gz$/.test(filename))throw Error('invalid_archive_name');
    const records=this.sql.exec('SELECT payload FROM raw ORDER BY at').toArray();
    if(!records.length)return json({error:'No raw records or retention expired'},404);
    // A gzip file permits concatenated members; each member is an independent JSON object.
    const stream=new ReadableStream({start(controller){for(const r of records)controller.enqueue(new Uint8Array(r.payload));controller.close();}});
    return new Response(stream,{headers:{'Content-Type':'application/gzip','Content-Disposition':'attachment; filename="'+filename+'"','Cache-Control':'no-store'}});
  }
  async alarm(){
    const day=this.sql.exec('SELECT value FROM meta WHERE key=?','day').toArray()[0]?.value;
    if(!day)return;
    const age=(Date.now()-dayStart(day))/86400000;
    if(age>=365){await this.ctx.storage.deleteAll();return;}
    if(age>=30)this.sql.exec('DELETE FROM raw WHERE at<?',Date.now()/1000-30*86400);
    const earliest=this.sql.exec('SELECT MIN(at) AS at FROM raw').toArray()[0].at;
    await this.ctx.storage.setAlarm(earliest?Math.max(Date.now()+1000,earliest*1000+30*86400000+1000):dayStart(day)+365*86400000);
  }
}
