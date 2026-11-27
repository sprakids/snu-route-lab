import {DurableObject} from 'cloudflare:workers';
import profile from './demand.json';
import routeStops from './route_stops.json';
import {ROUTES,LIMITS,START,END,kstDay,dayStart,schedule,chooseRoute,allowedReservation} from './schedule.mjs';

const names={'100100250':'5511','100100251':'5513','100100253':'5516','120900011':'관악02-1','120900012':'관악02-2'};
const json=(x,status=200,extra={})=>new Response(JSON.stringify(x),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',...extra}});
const auth=(req,env)=>Boolean(env.BACKEND_TOKEN)&&req.headers.get('Authorization')==='Bearer '+env.BACKEND_TOKEN;
const finite=(v)=>Number.isFinite(Number(v));
const providerTime=(s)=>/^\d{14}$/.test(String(s))?Date.parse(`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}T${s.slice(8,10)}:${s.slice(10,12)}:${s.slice(12,14)}+09:00`)/1000:null;
async function gzip(value){return new Uint8Array(await new Response(new Blob([JSON.stringify(value)+'\n']).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());}

export default {
  async fetch(req,env){
    const url=new URL(req.url);
    if(!auth(req,env))return json({error:'Unauthorized'},401);
    return env.COORDINATOR.getByName('production-v1').fetch(req);
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
    this.jobs=[];this.jobDay='';
  }
  get(k,fallback=null){const r=this.sql.exec('SELECT value FROM state WHERE key=?',k).toArray()[0];return r?JSON.parse(r.value):fallback;}
  put(k,v){this.sql.exec('INSERT OR REPLACE INTO state VALUES(?,?)',k,JSON.stringify(v));}
  counts(day){const c={baseline:0,peak:0,offpeak:0,retry:0};for(const r of this.sql.exec('SELECT pool,COUNT(*) AS n FROM attempts WHERE day=? GROUP BY pool',day))c[r.pool]=r.n;return c;}
  usage(now=Date.now()){
    const u=this.get('usage',{}),day=new Date(now).toISOString().slice(0,10);
    const current=u.day===day?u:{day,requests:0,reads:0,writes:0};
    const sizes=this.get('history_sizes',{});let bytes=0;
    for(const [day,v] of Object.entries(sizes))bytes+=typeof v==='number'?v:v.aggregate_bytes+((now-dayStart(day))/86400000<=31?v.raw_bytes:0);
    const actual=this.get('platform_usage',{});
    // Conservative app allowances leave capacity for indexes, platform work and other requests.
    const ratio=Math.max(current.requests/80000,current.reads/2500000,current.writes/50000,bytes/(4*1024**3),actual.ratio||0);
    return {...current,stored_bytes:bytes,ratio,warning:ratio>=.8,throttled:ratio>=.9,scope:'application_estimate_with_optional_platform_metrics'};
  }
  meter(reads=1,writes=1){const u=this.usage();this.put('usage',{day:u.day,requests:u.requests+1,reads:u.reads+reads,writes:u.writes+writes+1});}
  reserve(job,route,now){
    return this.ctx.storage.transactionSync(()=>{
      if(this.sql.exec('SELECT id FROM attempts WHERE id=?',job.id).toArray().length)return false;
      const day=kstDay(now);if(!job.id.startsWith(day+':')||!allowedReservation(this.counts(day),job.pool))return false;
      this.sql.exec('INSERT INTO attempts VALUES(?,?,?,?,?,NULL)',job.id,day,job.pool,route,now);
      return true;
    });
  }
  async wake(){
    const day=kstDay(Date.now());if(this.get('cleanup_day')!==day){this.cleanup(day);this.put('cleanup_day',day);}
    if(!this.get('enabled',false))return;
    const a=await this.ctx.storage.getAlarm();
    if(a===null||a<Date.now()-60000)await this.ctx.storage.setAlarm(Date.now()+1000);
  }
  async alarm(){
    const now=Date.now(),day=kstDay(now);if(!this.get('enabled',false))return;
    // Always arm a recovery alarm before I/O. A crash cannot erase the watchdog.
    await this.ctx.storage.setAlarm(now+60000);
    if(this.jobDay!==day){this.jobs=schedule(day,profile);this.jobDay=day;}
    this.meter(20,8);
    const latest=this.get('latest',{}),done=this.get('done',{day,ids:[]});
    const seen=new Set(done.day===day?done.ids:[]);
    const retries=this.get('retries',[]).filter(j=>j.id.startsWith(day+':'));
    const all=[...this.jobs,...retries].sort((a,b)=>a.at-b.at);
    const pending=all.filter(j=>!seen.has(j.id)&&j.at<=now&&j.at>=now-60000).slice(0,8);
    for(const job of all)if(job.at<now-60000)seen.add(job.id); // No catch-up request storm.
    for(const job of pending){
      if(!this.get('enabled',false))break;
      seen.add(job.id);const usage=this.usage();
      if(now<dayStart(day)+START*60000||now>=dayStart(day)+(END+1)*60000)continue;
      if(usage.ratio>=1||usage.throttled&&['peak','offpeak'].includes(job.pool))continue;
      const route=chooseRoute(job,latest,profile,day,now);
      if(!route)continue;
      if(!this.env.SEOUL_BUS_SERVICE_KEY)continue;
      // Durable reservation commits before the provider request; unknown outcomes stay spent.
      if(!this.reserve(job,route,Date.now()))continue;
      latest[route]={...latest[route],attempted_at:Date.now()};this.put('latest',latest);
      const result=await this.collect(route,job,latest[route]);
      latest[route]=result;this.put('latest',latest);
      this.sql.exec('UPDATE attempts SET ok=? WHERE id=?',result.error?0:1,job.id);
      if(result.error&&(job.retry||0)<2&&Date.now()+30000<dayStart(day)+(END+1)*60000)retries.push({id:`${day}:retry:${job.id}:${(job.retry||0)+1}`,route,pool:'retry',retry:(job.retry||0)+1,at:Date.now()+30000});
    }
    this.put('done',{day,ids:[...seen]});this.put('retries',retries);
    const next=all.filter(j=>!seen.has(j.id)&&j.at>Date.now()).map(j=>j.at).concat(retries.filter(j=>!seen.has(j.id)&&j.at>Date.now()).map(j=>j.at));
    const tomorrow=dayStart(kstDay(now+86400000))+START*60000;
    const at=Math.max(Date.now()+1000,Math.min(tomorrow,...next));
    this.put('next_scheduled_at',at);await this.ctx.storage.setAlarm(at);
    if(this.get('cleanup_day')!==day){this.cleanup(day);this.put('cleanup_day',day);}
  }
  cleanup(day){
    const old=kstDay(dayStart(day)-2*86400000),year=kstDay(dayStart(day)-365*86400000);
    this.sql.exec('DELETE FROM attempts WHERE day<?',old);this.sql.exec('DELETE FROM generic_calls WHERE day<?',old);
    this.sql.exec('DELETE FROM observations WHERE day<?',year);this.sql.exec('DELETE FROM cache WHERE expires<? AND lease<?',Date.now()-86400000,Date.now());
    this.sql.exec('DELETE FROM travel_samples WHERE day<?',year);
    this.sql.exec('DELETE FROM traffic_aggregate WHERE day<?',year);
    const sizes=this.get('history_sizes',{});for(const d of Object.keys(sizes))if(d<year)delete sizes[d];this.put('history_sizes',sizes);
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
        at_stop:String(v.stopFlag)==='1',full:String(v.isFullFlag)==='1',crowd_code:String(v.congetion||'0'),
        crowd_label:({'3':'여유','4':'보통','5':'혼잡','6':'매우혼잡'})[String(v.congetion)]||'정보 없음'}));
      for(const v of rows){
        const prior=(previous.vehicles||[]).find(p=>p.id===v.id);
        if(prior&&v.provided_at>prior.provided_at)v.previous_observation={lat:prior.lat,lon:prior.lon,provided_at:prior.provided_at,section_order:prior.section_order};
        else if(prior?.previous_observation)v.previous_observation=prior.previous_observation;
      }
    }catch(e){error=String(e.message||'provider_unavailable').replace(/https?:\S+/g,'[redacted]').slice(0,100);}
    const traffic=await this.collectTraffic(route);
    if(!error)for(const v of rows)this.recordStop(v);
    const signature=rows.map(v=>v.id+':'+v.provided_at).sort().join('|');
    const duplicate=!error&&signature&&signature===previous.signature;
    const record={job_id:job.id,route_id:route,at:at/1000,error,vehicles:rows,...(traffic?{traffic}: {})};
    // Archive normalized data, never the URL or the key. Identical observations are deduplicated.
    if(!duplicate||traffic){
      try{
        const archive=this.env.HISTORY.getByName(kstDay(at));const archived=await archive.append(record);
        const sizes=this.get('history_sizes',{});sizes[kstDay(at)]={raw_bytes:archived.raw_bytes,aggregate_bytes:archived.aggregate_bytes};this.put('history_sizes',sizes);
        this.meter(archived.reads,archived.writes);
      }catch{this.put('enabled',false);error='durable_archive_unavailable';}
    }
    return {...previous,attempted_at:at,error,duplicate_count:duplicate?(previous.duplicate_count||0)+1:0,
      ...(!error?{vehicles:rows,captured_at:at/1000,signature,changed:JSON.stringify(rows.map(v=>v.crowd_code))!==JSON.stringify((previous.vehicles||[]).map(v=>v.crowd_code))}:{})};
  }
  async collectTraffic(route){
    const all=this.get('traffic',{}),now=Date.now();if(now/1000-(all[route]?.fetched_at||0)<600)return null;
    const day=kstDay(now),reserved=this.ctx.storage.transactionSync(()=>{
      const n=this.sql.exec('SELECT used FROM generic_calls WHERE day=? AND service=?',day,'seoul_route_traffic').toArray()[0]?.used||0;
      if(n>=400)return false;
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
      all[route]=value;this.put('traffic',all);this.recordTraffic(route,value);return value;
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
  recordStop(v){
    if(!v.at_stop||!v.provided_at)return;
    const seq=Number(v.section_order),stop=routeStops[v.route_id]?.find(s=>s.seq===seq);if(!stop)return;
    const dx=(v.lon-stop.lon)*Math.cos(v.lat*Math.PI/180)*111195,dy=(v.lat-stop.lat)*111195;
    if(Math.hypot(dx,dy)>60)return;
    const prior=v.previous_observation;
    if(!prior||v.provided_at-prior.provided_at>120||v.provided_at<=prior.provided_at)return;
    const id=v.route_id+':'+v.id,row=this.sql.exec('SELECT value FROM vehicle_stops WHERE id=?',id).toArray()[0];
    let history=row?JSON.parse(row.value):[];
    if(history.length&&(seq<history.at(-1).seq||v.provided_at-history.at(-1).at>1800))history=[];
    if(history.some(x=>x.seq===seq))return;
    const summaries=this.get('travel_summary',{});let reads=3,writes=3;
    for(const p of history){
      const seconds=v.provided_at-p.at;if(seq<=p.seq||seq-p.seq>12||seconds<=0||seconds>1800)continue;
      const from=routeStops[v.route_id]?.find(s=>s.seq===p.seq);
      if(!from)continue;
      const direct=Math.hypot((stop.lon-from.lon)*Math.cos(stop.lat*Math.PI/180)*111195,(stop.lat-from.lat)*111195);
      if(seconds<direct/(100/3.6))continue;
      const sampleId=`${id}:${p.at}:${seq}`;this.sql.exec('INSERT OR IGNORE INTO travel_samples VALUES(?,?,?,?,?,?)',sampleId,kstDay(v.provided_at*1000),v.route_id,p.seq,seq,seconds);
      const samples=this.sql.exec('SELECT day,seconds FROM travel_samples WHERE route=? AND from_seq=? AND to_seq=? ORDER BY day DESC LIMIT 500',v.route_id,p.seq,seq).toArray();
      const values=samples.map(x=>x.seconds).sort((a,b)=>a-b),q=f=>values[Math.floor((values.length-1)*f)];
      reads+=samples.length;writes+=3;
      summaries[`${v.route_id}:${p.seq}:${seq}`]={n:values.length,days:new Set(samples.map(x=>x.day)).size,median_seconds:q(.5),p10_seconds:q(.1),p90_seconds:q(.9),
        latest_at:v.provided_at,kind:'observed_at_stop_timestamp_difference',maximum_sampling_gap_seconds:120,cohort:'all_observed_hours'};
    }
    this.put('travel_summary',summaries);history.push({seq,at:v.provided_at});
    this.sql.exec('INSERT OR REPLACE INTO vehicle_stops VALUES(?,?)',id,JSON.stringify(history.slice(-12)));
    this.meter(reads,writes);
  }
  status(){
    const now=Date.now(),latest=this.get('latest',{}),counts=this.counts(kstDay(now));
    const used=Object.values(counts).reduce((s,x)=>s+x,0);
    const services={};for(const r of this.sql.exec('SELECT service,used FROM generic_calls WHERE day=?',kstDay(now)))services[r.service]=r.used;
    return {captured_at:Math.max(0,...Object.values(latest).map(v=>v.captured_at||0))||null,service_calls:services,
      traffic:this.get('traffic',{}),historical_traffic:this.get('historical_traffic',{}),travel_history:this.get('travel_summary',{}),
      vehicles:Object.values(latest).flatMap(v=>v.vehicles||[]),routes:ROUTES.map(id=>({id,name:names[id],captured_at:latest[id]?.captured_at||null,error:latest[id]?.error||null})),
      errors:Object.entries(latest).filter(([,v])=>v.error).map(([id,v])=>names[id]+': '+v.error),
      source:'서울시 버스위치정보 OpenAPI',position_calls_today:used,position_calls_remaining:950-used,position_app_daily_limit:950,
      budget_pools:counts,budget_limits:LIMITS,next_scheduled_at:(this.get('next_scheduled_at')||0)/1000||null,
      enabled:this.get('enabled',false),configured:Boolean(this.env.SEOUL_BUS_SERVICE_KEY),usage:this.usage(),
      mode:this.get('enabled',false)?'scheduled':'collector_paused',server_time:now/1000};
  }
  async fetch(req){
    const url=new URL(req.url),path=url.pathname;this.meter(4,2);
    if(path==='/snapshot'||path==='/status')return json(this.status());
    if(req.method==='POST'&&path==='/control'){
      const b=await req.json();if(typeof b.enabled!=='boolean')return json({error:'enabled required'},400);
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
        this.sql.exec('INSERT INTO observations VALUES(?,?,?,?)',id,kstDay(Date.now()),new Date().toISOString(),JSON.stringify(record));
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
      const b=await req.json();if(!['public_arrivals','busin_live'].includes(b.service))return json({allowed:false});
      const day=kstDay(Date.now()),limit=Math.min(b.service==='busin_live'?6000:1200,Math.max(0,Number(b.limit)||0));
      const ok=this.ctx.storage.transactionSync(()=>{
        const row=this.sql.exec('SELECT used FROM generic_calls WHERE day=? AND service=?',day,b.service).toArray()[0];
        if((row?.used||0)>=limit)return false;
        this.sql.exec('INSERT OR REPLACE INTO generic_calls VALUES(?,?,?)',day,b.service,(row?.used||0)+1);return true;
      });return json({allowed:ok});
    }
    if(req.method==='POST'&&path==='/cache'){
      const b=await req.json(),now=Date.now();if(!/^[a-zA-Z0-9_-]{1,150}$/.test(b.key||''))return json({error:'invalid cache key'},400);
      const doc=this.sql.exec('SELECT * FROM cache WHERE key=?',b.key).toArray()[0];
      if(b.action==='read')return json(doc?{value:JSON.parse(doc.value||'null'),expires_at:doc.expires/1000}:{});
      if(b.action==='claim'){
        if(doc&&(doc.expires>now||doc.lease>now))return json({owned:false,value:JSON.parse(doc.value||'null')});
        const owner=crypto.randomUUID();this.sql.exec('INSERT OR REPLACE INTO cache VALUES(?,?,?,?,?)',b.key,doc?.value||'null',doc?.expires||0,owner,now+55000);
        return json({owned:true,owner,value:JSON.parse(doc?.value||'null')});
      }
      if(b.action==='publish'&&doc?.owner===b.owner){this.sql.exec('UPDATE cache SET value=?,expires=?,lease=0 WHERE key=?',JSON.stringify(b.value),now+Math.min(120,Math.max(1,b.seconds||15))*1000,b.key);return json({saved:true});}
      if(b.action==='release'&&doc?.owner===b.owner){this.sql.exec('UPDATE cache SET lease=0 WHERE key=?',b.key);return json({saved:true});}
      return json({saved:false},409);
    }
    if(path==='/export'||path==='/aggregate'){
      const day=url.searchParams.get('day');if(!/^\d{4}-\d{2}-\d{2}$/.test(day||''))return json({error:'day required'},400);
      const a=this.env.HISTORY.getByName(day);return path==='/export'?a.export():json(await a.aggregate());
    }
    return json({error:'Not found'},404);
  }
}

export class DailyHistory extends DurableObject {
  constructor(ctx,env){
    super(ctx,env);this.ctx=ctx;this.sql=ctx.storage.sql;
    this.sql.exec('CREATE TABLE IF NOT EXISTS raw(id TEXT PRIMARY KEY,at REAL,payload BLOB)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS passages(id TEXT PRIMARY KEY,route TEXT,section TEXT,slot INTEGER,grade TEXT,at REAL)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS progress(id TEXT PRIMARY KEY,section INTEGER,trip INTEGER,at REAL)');
  }
  async append(record){
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
  async export(){
    const records=this.sql.exec('SELECT payload FROM raw ORDER BY at').toArray();
    if(!records.length)return json({error:'No raw records or retention expired'},404);
    // A gzip file permits concatenated members; each member is an independent JSON object.
    const stream=new ReadableStream({start(controller){for(const r of records)controller.enqueue(new Uint8Array(r.payload));controller.close();}});
    return new Response(stream,{headers:{'Content-Type':'application/gzip','Content-Disposition':'attachment; filename="snu-bus-observations.jsons.gz"','Cache-Control':'no-store'}});
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
