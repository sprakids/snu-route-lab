// BUSIN is a schematic stop-area feed. Times below are interval-censored
// detections, never GPS fixes or exact provider arrival/departure timestamps.
import {kstDay,dayStart,START,END} from './schedule.mjs';
export const CORE=new Set(['41841','41946','41914']);
export function cadence(route,ms){const m=(ms-dayStart(kstDay(ms)))/60000;return CORE.has(route)&&m>=900&&m<1140?30:120;}
export function shuttleSlot(route,ms){
  const day=kstDay(ms),start=dayStart(day)+START*60000,end=dayStart(day)+END*60000;
  if(ms<start||ms>end)return null;
  const step=cadence(route,ms)*1000,at=Math.floor(ms/step)*step;
  return {day,at,step,id:`${day}:${route}:${at}`};
}
export function nextShuttleAt(ms){
  const day=kstDay(ms),start=dayStart(day)+START*60000,end=dayStart(day)+END*60000;
  if(ms<start)return start;if(ms>=end)return dayStart(kstDay(ms+86400000))+START*60000;
  const m=(ms-dayStart(day))/60000,step=m>=900&&m<1140?30000:120000;
  return Math.min(end,(Math.floor(ms/step)+1)*step);
}
export function locate(x,y,anchors){
  let best=null,near=0;for(let i=0;i<anchors.length;i++){
    const a=anchors[i],b=anchors[(i+1)%anchors.length];
    if(Math.hypot(x-a.x,y-a.y)<Math.hypot(x-anchors[near].x,y-anchors[near].y))near=i;
    const dx=b.x-a.x,dy=b.y-a.y,den=dx*dx+dy*dy;
    if(!den)continue;const t=Math.max(0,Math.min(1,((x-a.x)*dx+(y-a.y)*dy)/den));
    const offset=Math.hypot(x-a.x-t*dx,y-a.y-t*dy);
    if(!best||offset<best.offset)best={offset,segment_index:i,schematic_progress:t};
  }
  if(!best||best.offset>45)return null;
  const at_stop=Math.hypot(x-anchors[near].x,y-anchors[near].y)<=11;
  return {segment_index:at_stop?near:best.segment_index,at_stop_index:at_stop?near:null,at_stop,
    from_name:anchors[at_stop?near:best.segment_index].name,to_name:anchors[((at_stop?near:best.segment_index)+1)%anchors.length].name,
    schematic_progress:at_stop?0:Math.round(best.schematic_progress*1000)/1000,
    position_kind:at_stop?'schematic_stop_area':'schematic_landmark_interval'};
}
export function parseShuttle(data,spec,at,previous=[]){
  if(typeof data?.d!=='string')throw Error('invalid_shuttle_envelope');
  const seen=new Set(),old=new Map(previous.map(v=>[v.id,v]));let changed=0;
  const vehicles=[];for(const raw of data.d.split(';')){
    const f=raw.split('/');if(f.length!==6)continue;
    const [id]=f,x=Number(f[1]),y=Number(f[2]);
    if(!id||seen.has(id)||!Number.isFinite(x)||!Number.isFinite(y))continue;
    seen.add(id);const p=locate(x,y,spec.anchors);
    if(p)p.direction=spec.id==='41841'?(p.segment_index<4?'towards_admin':'towards_station'):spec.direction_label;
    const prev=old.get(id),moved=Boolean(prev&&(prev.x!==x||prev.y!==y));changed+=Number(moved);
    vehicles.push({id,route_id:'shuttle-'+spec.id,route_name:spec.name,x,y,captured_at:at,position:p,moved_since_previous:moved});
  }
  if(data.d.trim()&&!vehicles.length)throw Error('unrecognized_shuttle_records');
  return {captured_at:at,vehicles,error:null,provider_timestamp:null,moved_observations:changed,
    position_kind:'schematic_stop_area_or_interval',collection_source:'scheduled_busin'};
}
function add(stats,type,key,sample){const box=stats[type][key]||={n:0,samples:[]};box.n++;box.samples.push(sample);if(box.samples.length>128)box.samples.shift();}
export function updateShuttleStats(previous,feed,spec){
  const p=structuredClone(previous||{version:1,progress:{},last:{},headways:{},rides:{},events:[],polls:0,vehicles_seen:0});
  const at=feed.captured_at;if(!Number.isFinite(at)||at<=Number(p.last_poll||0)||feed.error)return p;
  p.last_poll=at;p.polls++;p.vehicles_seen+=feed.vehicles.length;
  const events=[],n=spec.anchor_count??spec.anchors.length;
  for(const v of feed.vehicles){
    const pos=v.position;if(!pos)continue;let old=p.progress[v.id];
    // A missing sample, eviction gap or position jump is not a completed trip.
    if(old&&(at-old.seen>180||at<=old.seen))old=null;
    const current=pos.at_stop?pos.at_stop_index:null,open=old?.open||[];
    if(old&&old.stop!==null&&old.stop!==undefined&&current!==old.stop){
      const e={kind:'departure',stop:old.stop,lo:old.seen,hi:at,vehicle:v.id,direction:old.direction};events.push(e);
      open.push({stop:old.stop,lo:e.lo,hi:e.hi});
    }
    if(old&&current!==null&&current!==old.stop){
      const e={kind:'arrival',stop:current,lo:old.seen,hi:at,vehicle:v.id,direction:pos.direction};events.push(e);
      for(const d of open){
        if(d.stop===current||at-d.hi>3600)continue;
        const lo=Math.max(0,e.lo-d.hi),hi=e.hi-d.lo;
        if(hi<20||hi>3600)continue;
        const h=Math.floor((d.hi-dayStart(kstDay(d.hi*1000))/1000)/3600);
        add(p,'rides',`${d.stop}:${current}:${h}`,{lo,hi,seconds:(lo+hi)/2,known_at:at,at:d.hi,vehicle:v.id});
      }
      // Returning to an already departed stop starts a new circuit.
      const repeat=open.findIndex(x=>x.stop===current);if(repeat>=0)open.splice(0,repeat+1);
    }
    p.progress[v.id]={seen:at,stop:current,direction:pos.direction,open:open.filter(x=>at-x.hi<=3600).slice(-n)};
  }
  const groups=new Map();for(const e of events){const key=`${e.kind}:${e.stop}:${e.direction}`;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(e);}
  for(const [key,rows] of groups){
    const lo=Math.min(...rows.map(x=>x.lo)),hi=at,old=p.last[key],h=Math.floor((at-dayStart(kstDay(at*1000))/1000)/3600);
    if(old&&lo<=old.hi){
      // Adjacent poll intervals can be the two members of one dispatch.
      // Their order is not resolved: merge the detection batch rather than
      // count a second headway and then also expand the two-vehicle supply.
      p.last[key]={lo:old.lo,hi,count:old.count+rows.length};continue;
    }
    if(old&&lo>old.hi&&hi-old.hi<=3600){
      const lower=Math.max(0,lo-old.hi),upper=hi-old.lo;
      add(p,'headways',`${key}:${h}`,{lo:lower,hi:upper,seconds:(lower+upper)/2,known_at:at,at,vehicles_in_detection_batch:rows.length});
    }
    p.last[key]={lo,hi,count:rows.length};
  }
  p.events.push(...events);p.events=p.events.slice(-1200);
  for(const [id,v] of Object.entries(p.progress))if(at-v.seen>3600)delete p.progress[id];
  return p;
}

export function recordingRows(rows,day){return {day,raw_retention_days:30,aggregate_retention_days:365,position_kind:'schematic_stop_area_or_interval',
  routes:rows.map(({route,value})=>{const p=JSON.parse(value);return {route,polls:p.polls,last_poll:p.last_poll,
    detected_arrivals:p.events.filter(e=>e.kind==='arrival').length,detected_departures:p.events.filter(e=>e.kind==='departure').length,
    headway_intervals:Object.values(p.headways).reduce((n,x)=>n+x.n,0),completed_trip_segments:Object.values(p.rides).reduce((n,x)=>n+x.n,0),bytes:value.length};})};}

export function dayProfile(rows,day,hour,wanted){
  const routes={};for(const {route,value} of rows){const p=JSON.parse(value),out=routes['shuttle-'+route]={headways:{},rides:{}};
    for(const type of ['headways','rides'])for(const [key,box] of Object.entries(p[type]||{})){
      const parts=key.split(':'),h=Number(parts.pop());if(Math.abs(h-hour)>1)continue;const id=parts.join(':');
      if(type==='rides'&&!(wanted['shuttle-'+route]||[]).includes(id))continue;
      const samples=box.samples||[],dest=out[type][id]||=[];
      for(let i=0;i<Math.min(4,samples.length);i++)dest.push({...samples[Math.floor(i*(samples.length-1)/Math.max(1,Math.min(4,samples.length)-1))],day});
    }
  }return routes;
}
