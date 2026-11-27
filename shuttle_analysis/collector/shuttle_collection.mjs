import catalog from './shuttle_catalog.json' with {type:'json'};
import {kstDay,dayStart} from './schedule.mjs';
import {shuttleSlot,nextShuttleAt,parseShuttle,cadence} from './shuttle_stats.mjs';
const json=(x,status=200)=>new Response(JSON.stringify(x),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
const DAY=/^\d{4}-\d{2}-\d{2}$/;
const ENDPOINT='https://web.busin.co.kr/BuslineCircleS.aspx/GetRoute';
export class ShuttleCollection {
  constructor(owner){this.o=owner;this.running=false;this.profileCache=new Map();
    owner.sql.exec('CREATE TABLE IF NOT EXISTS shadow_runs(id TEXT PRIMARY KEY,day TEXT,created REAL,state TEXT,value TEXT) WITHOUT ROWID');
    owner.sql.exec('CREATE INDEX IF NOT EXISTS shadow_runs_day ON shadow_runs(day)');
    owner.sql.exec('CREATE TABLE IF NOT EXISTS shadow_daily(day TEXT PRIMARY KEY,value TEXT) WITHOUT ROWID');
  }
  enabled(){return this.o.get('shuttle_collection_enabled',false);}
  shadowAvailability(){const day=kstDay(Date.now()),counter=this.o.get('shadow_counter',{}),used=counter.day===day?counter.used:0,u=this.o.usage();return {day,available:used<500&&u.writes<60000&&!u.throttled,used,daily_cap:500};}
  cleanup(day){
    const o=this.o,month=kstDay(dayStart(day)-30*86400000),year=kstDay(dayStart(day)-365*86400000);
    o.sql.exec('DELETE FROM shadow_runs WHERE day<?',month);o.sql.exec('DELETE FROM shadow_daily WHERE day<?',year);
    const latest=o.get('shadow_latest');if(latest&&latest.created_at<dayStart(month)/1000)o.put('shadow_latest',null);
    for(const [key,cutoff] of [['shuttle_archive_sizes',year],['shadow_archive_sizes',month]]){
      const sizes=o.get(key,{}),old=Object.keys(sizes).filter(d=>d<cutoff);
      if(old.length){for(const d of old)delete sizes[d];o.put(key,sizes);}
    }
  }
  async arm(){if(!this.enabled())return;const at=nextShuttleAt(Date.now()),old=await this.o.ctx.storage.getAlarm();if(old===null||old>at)await this.o.setAlarm(at);}
  async tick(){
    if(!this.enabled()||this.running)return;this.running=true;
    try{
      const o=this.o,now=Date.now(),day=kstDay(now);
      if(!o.shuttleWriteAvailable()){o.put('shuttle_collection_state',{at:now/1000,status:'paused_storage_headroom'});return;}
      const slots=o.get('shuttle_slots_v1',{}),due=[];
      for(const spec of catalog.routes){const slot=shuttleSlot(spec.id,now);if(slot&&slots[spec.id]!==slot.id){slots[spec.id]=slot.id;due.push({spec,slot});}}
      if(!due.length)return;
      // Durable slot claim precedes every network request. Retried alarms and
      // cold starts may miss a sample, but never repeat a reserved slot.
      o.put('shuttle_slots_v1',slots);
      const allowed=due.filter(()=>o.reserveShuttleCall(day,6000));
      o.cachedShuttle({action:'read',key:'shuttle-v2-41841'},now); // hydrate fleet checkpoint
      let proxied=null;
      if(o.env.SHUTTLE_PROXY_URL&&allowed.length){
        try{
          const response=await fetch(o.env.SHUTTLE_PROXY_URL,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+o.env.BACKEND_TOKEN},
            body:JSON.stringify({routes:allowed.map(x=>x.spec.id)}),signal:AbortSignal.timeout(18000)});
          if(!response.ok)throw Error('shuttle_proxy_http_'+response.status);
          proxied=(await response.json()).routes||{};
        }catch{proxied={};}
      }
      const records=await Promise.all(allowed.map(async({spec,slot})=>{
        const old=o.shuttleCache.get('shuttle-v2-'+spec.id)?.value;
        try{
          let data;
          if(proxied!==null){data=proxied[spec.id];if(!data||data.error)throw Error('shuttle_proxy_or_provider_unavailable');}
          else{
            const response=await fetch(ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json; charset=utf-8','User-Agent':'SNU-Route-Lab/shuttle-archive-1'},
              body:JSON.stringify({data:',F,'+spec.id+',snu_1'}),signal:AbortSignal.timeout(7000)});
            if(!response.ok)throw Error('busin_http_'+response.status);data=await response.json();
          }
          return {route:spec.id,slot:slot.id,value:{...parseShuttle(data,spec,Date.now()/1000,old?.vehicles||[]),sampling_interval_seconds:cadence(spec.id,now)}};
        }catch(error){const reason=/^(?:busin_http_\d{3}|invalid_shuttle_envelope|unrecognized_shuttle_records|shuttle_proxy_or_provider_unavailable)$/.test(error.message)?error.message:'shuttle_network_or_response_error';
          return {route:spec.id,slot:slot.id,value:{...(old||{captured_at:null,vehicles:[]}),error:reason,attempted_at:Date.now()/1000}};}
      }));
      if(!records.length)return;
      const daily=o.env.HISTORY.getByName('shuttle:'+day);
      const archive=await daily.append({format:'packed-v2',kind:'shuttle_positions_v1',
        job_id:'shuttle:'+records.map(r=>r.slot).sort().join('|'),at:now/1000,routes:records,
        time_basis:'received_interval_not_provider_timestamp',position_kind:'schematic_stop_area_or_interval',catalog_source_sha256:catalog.source_sha256});
      o.pendingCost.requests++;o.pendingCost.reads+=archive.reads||0;o.pendingCost.writes+=archive.writes||0;
      const stats=await daily.updateShuttles(records.map(record=>({...record,anchor_count:catalog.routes.find(s=>s.id===record.route).anchors.length})),catalog.source_sha256);
      o.pendingCost.requests++;o.pendingCost.reads+=stats.reads||0;o.pendingCost.writes+=stats.writes||0;
      const sizes=o.get('shuttle_archive_sizes',{});sizes[day]={raw_bytes:archive.raw_bytes,aggregate_bytes:stats.aggregate_bytes};
      for(const d of Object.keys(sizes))if(now-dayStart(d)>365*86400000)delete sizes[d];
      o.put('shuttle_archive_sizes',sizes);
      for(const record of records){
        const value=record.value;
        o.shuttleCache.set('shuttle-v2-'+record.route,{value,expires:now+cadence(record.route,now)*1000,owner:null,lease:0});
      }
      o.put('shuttle-cache-v1',{at:now,entries:Object.fromEntries([...o.shuttleCache].map(([key,d])=>[key,{value:d.value,expires:d.expires}]))});o.shuttleCacheSavedAt=now;
      o.put('shuttle_collection_state',{at:Date.now()/1000,status:'collecting',routes:records.length,errors:records.filter(x=>x.value.error).length});
      o.flushUsage();
    }catch{
      // A shuttle/archive failure does not disable the existing city collector.
      this.o.put('shuttle_collection_state',{at:Date.now()/1000,status:'archive_or_collection_error'});
    }finally{this.running=false;}
  }
  async recording(day){this.o.pendingCost.requests++;return {...await this.o.env.HISTORY.getByName('shuttle:'+day).shuttleRecording(),day};}
  async profile(when,asof,wanted={}){
    if(!Number.isFinite(when)||!Number.isFinite(asof))throw Error('invalid_profile_time');
    // Only completed previous days can train a future/historical forecast.
    // Today's partial samples remain available for research, not automatic fit.
    const cutoff=kstDay(Math.min(Date.now()/1000,when,asof)*1000),hour=new Date(when*1000+9*3600000).getUTCHours();
    if(!wanted||typeof wanted!=='object'||Object.keys(wanted).length>10||Object.entries(wanted).some(([rid,pairs])=>!/^shuttle-\d{5}$/.test(rid)||!Array.isArray(pairs)||pairs.length>80||pairs.some(p=>!/^\d{1,2}:\d{1,2}$/.test(p))))throw Error('invalid_profile_pairs');
    const cacheKey=cutoff+':'+new Date(when*1000+9*3600000).getUTCDay()+':'+hour+':'+JSON.stringify(wanted),cached=this.profileCache.get(cacheKey);
    if(cached&&Date.now()-cached.at<300000)return cached.value;
    const targetDay=new Date(when*1000+9*3600000).getUTCDay(),weekend=[0,6].includes(targetDay),result={schema:'shuttle_interval_profiles_v1',before_date:cutoff,catalog_source_sha256:catalog.source_sha256,routes:{},minimum_days:2,minimum_samples:5};
    const days=Object.keys(this.o.get('shuttle_archive_sizes',{})).filter(day=>day<cutoff&&day>=kstDay(dayStart(cutoff)-28*86400000)).sort().reverse();
    const matched=days.filter(day=>new Date(day+'T12:00:00+09:00').getUTCDay()===targetDay),chosen=matched.length>=3?matched:days.filter(day=>[0,6].includes(new Date(day+'T12:00:00+09:00').getUTCDay())===weekend);
    const daily=[];for(let i=0;i<chosen.length;i+=4){const part=chosen.slice(i,i+4);this.o.pendingCost.requests+=part.length;
      daily.push(...await Promise.all(part.map(day=>this.o.env.HISTORY.getByName('shuttle:'+day).shuttleProfile(hour,wanted,catalog.source_sha256))));}
    for(const spec of catalog.routes){
      const out={headways:{},rides:{},dates:chosen,weekday_specific:matched.length>=3};
      for(const doc of daily){const r=doc['shuttle-'+spec.id]||{};for(const type of ['headways','rides'])for(const [key,samples] of Object.entries(r[type]||{}))
        (out[type][key]||=[]).push(...samples.filter(s=>kstDay(s.known_at*1000)<cutoff));}
      for(const type of ['headways','rides'])for(const [key,rows] of Object.entries(out[type]))if(rows.length>64)
        out[type][key]=Array.from({length:64},(_,i)=>rows[Math.floor(i*(rows.length-1)/63)]);
      out.dates=[...new Set(['headways','rides'].flatMap(type=>Object.values(out[type]).flatMap(rows=>rows.map(x=>x.day))))].sort();
      result.routes['shuttle-'+spec.id]=out;
    }
    if(this.profileCache.size>24)this.profileCache.clear();this.profileCache.set(cacheKey,{at:Date.now(),value:result});return result;
  }
  async handle(req,url){
    const o=this.o,path=url.pathname,day=url.searchParams.get('day')||kstDay(Date.now());
    if(path==='/shuttle/status')return json({enabled:this.enabled(),...o.get('shuttle_collection_state',{}),next_scheduled_at:this.enabled()?nextShuttleAt(Date.now())/1000:null,
      peak_core_seconds:30,other_seconds:120,provider_daily_cap:6000,recording:await this.recording(day)});
    if(path==='/shuttle/control'&&req.method==='POST'){
      const b=await req.json();if(typeof b.enabled!=='boolean')return json({error:'enabled required'},400);
      o.put('shuttle_collection_enabled',b.enabled);await this.arm();return json({enabled:this.enabled()});
    }
    if(path==='/shuttle/recording'){if(!DAY.test(day))return json({error:'invalid day'},400);return json(await this.recording(day));}
    if(path==='/shuttle/export'){if(!DAY.test(day))return json({error:'invalid day'},400);return o.env.HISTORY.getByName('shuttle:'+day).export('snu-shuttle-positions-'+day+'.jsons.gz');}
    if(path==='/shuttle/profile'){
      const b=req.method==='POST'?await req.json():{};
      return json(await this.profile(Number(b.when??url.searchParams.get('when')),Number(b.asof??url.searchParams.get('asof')),b.pairs||{}));
    }
    if(path==='/shadow/status'){
      const counts=o.sql.exec('SELECT state,COUNT(*) AS n FROM shadow_runs WHERE day=? GROUP BY state',day).toArray();
      const latest=o.get('shadow_latest'),aggregate=o.sql.exec('SELECT value FROM shadow_daily WHERE day=?',day).toArray()[0];
      return json({day,counts,latest:latest&&latest.created_at>Date.now()/1000-30*86400?latest:null,
        aggregate:aggregate?JSON.parse(aggregate.value):null,daily_cap:500,automatic_promotion:false,operating_model:'V11',raw_retention_days:30,aggregate_retention_days:365});
    }
    if(path==='/shadow/export'){if(!DAY.test(day))return json({error:'invalid day'},400);return o.env.HISTORY.getByName('shadow:'+day).export('snu-shadow-comparisons-'+day+'.jsons.gz');}
    if(path==='/shadow/claim'&&req.method==='POST'){
      const b=await req.json();if(!/^[a-f0-9]{32}$/.test(b.id||''))return json({allowed:false},400);
      const allowed=o.ctx.storage.transactionSync(()=>{
        if(o.usage().writes>=60000||o.usage().throttled)return false;
        if(o.sql.exec('SELECT id FROM shadow_runs WHERE id=?',b.id).toArray().length)return false;
        const n=o.sql.exec('SELECT COUNT(*) AS n FROM shadow_runs WHERE day=?',day).toArray()[0].n;if(n>=500)return false;
        o.sql.exec('INSERT INTO shadow_runs VALUES(?,?,?,?,?)',b.id,day,Date.now()/1000,'claimed','{}');o.put('shadow_counter',{day,used:n+1});return true;
      });return json({allowed});
    }
    if(path==='/shadow/record'&&req.method==='POST'){
      const b=await req.json();if(!/^[a-f0-9]{32}$/.test(b.id||''))return json({saved:false},400);
      const value=JSON.stringify(b.comparison);if(value.length>100000)return json({saved:false},413);
      // An explicit allowlist on the app side plus this recursive key guard:
      // never persist the request, coordinates, geometry, IP or a signed ticket.
      if(/"(?:lat|lon|latitude|longitude|origin|geometry|ticket|body|ip|token)"\s*:/.test(value))return json({saved:false},400);
      const row=o.sql.exec('SELECT state FROM shadow_runs WHERE id=?',b.id).toArray()[0];
      if(row?.state!=='claimed')return json({saved:false,duplicate:Boolean(row)},409);
      if(o.usage().writes>=65000)return json({saved:false,reason:'storage_headroom'},429);
      const archived=await o.env.HISTORY.getByName('shadow:'+day).append({format:'packed-v2',kind:'V11_R_paired_prediction',job_id:b.id,at:Date.now()/1000,comparison:b.comparison});
      o.pendingCost.requests++;o.pendingCost.reads+=archived.reads||0;o.pendingCost.writes+=archived.writes||0;
      const sizes=o.get('shadow_archive_sizes',{});sizes[day]=archived.raw_bytes;
      for(const d of Object.keys(sizes))if(Date.now()-dayStart(d)>31*86400000)delete sizes[d];o.put('shadow_archive_sizes',sizes);
      const complete=b.comparison?.status==='complete',state=complete?'complete':'failed';
      o.sql.exec('UPDATE shadow_runs SET state=?,value=? WHERE id=?',state,JSON.stringify({candidate_model:b.comparison?.candidate_model,reason:b.comparison?.reason}),b.id);
      if(complete){
        const row=o.sql.exec('SELECT value FROM shadow_daily WHERE day=?',day).toArray()[0];
        const p=row?JSON.parse(row.value):{comparisons:0,matched_routes:0,delta_wait_seconds_sum:0,delta_total_seconds_sum:0,accuracy_validation:false,automatic_promotion:false};
        p.comparisons++;for(const delta of b.comparison.matched_candidate_deltas||[]){p.matched_routes++;p.delta_wait_seconds_sum+=delta.wait_seconds||0;p.delta_total_seconds_sum+=delta.total_seconds||0;}
        o.sql.exec('INSERT INTO shadow_daily VALUES(?,?) ON CONFLICT(day) DO UPDATE SET value=excluded.value',day,JSON.stringify(p));
        o.put('shadow_latest',b.comparison);
      }
      o.flushUsage();return json({saved:true});
    }
    return null;
  }
}
