const hour=at=>new Date(at*1000+9*3600000).getUTCHours();
export function updatePacked(data,vehicles,stops,day){
 data=data||{schema:2,day,progress:{},grades:{},travel:{}};
 data.availability||={};data.headways||={};data.last_passage||={};
 let changed=false;
 for(const v of vehicles){
  const seq=Number(v.section_order),at=v.provided_at;
  if(!v.id||!Number.isFinite(at)||at<=0||!Number.isInteger(seq)||seq<1)continue;
  if(new Date(at*1000+9*3600000).toISOString().slice(0,10)!==day)continue;
  let previous=data.progress[v.id];
  if(previous&&at<=previous.at)continue;
  const newTrip=previous&&(seq<previous.seq||at-previous.at>1800);
  const history=newTrip?[]:(previous?.stops||[]);
  const freshPassage=!previous||newTrip||seq!==previous.seq;
  let gradeRecorded=!freshPassage&&(previous.grade_recorded??true),availabilityRecorded=!freshPassage&&previous.availability_recorded;
  if(!gradeRecorded&&['3','4','5','6'].includes(v.crowd_code)){
   const slot=Math.floor((hour(at)*3600+new Date(at*1000+9*3600000).getUTCMinutes()*60)/900);
   const key=`${seq}:${slot}:${v.crowd_code}`;data.grades[key]=(data.grades[key]||0)+1;
   gradeRecorded=true;
  }
  if(!availabilityRecorded&&v.full_known===true){
   const slot=Math.floor((hour(at)*3600+new Date(at*1000+9*3600000).getUTCMinutes()*60)/900);
   const grade=['3','4','5','6'].includes(v.crowd_code)?v.crowd_code:'unknown';
   const key=`${seq}:${slot}:${grade}`,cell=data.availability[key]||[0,0];
   cell[0]+=Number(v.full===true);cell[1]++;data.availability[key]=cell;availabilityRecorded=true;
  }
  const stop=stops.find(s=>s.seq===seq),prior=v.previous_observation;
  const near=stop&&Math.hypot((v.lon-stop.lon)*Math.cos(v.lat*Math.PI/180)*111195,(v.lat-stop.lat)*111195)<=60;
  if(v.at_stop&&near&&prior&&at-prior.provided_at>0&&at-prior.provided_at<=120&&!history.some(x=>x.seq===seq)){
   const last=data.last_passage[seq],gap=last?at-last.at:0;
   if(last&&last.vehicle!==v.id&&gap>=15&&gap<=3600){
    const key=`${hour(at)}:${seq}`,cell=data.headways[key]||{n:0,bins:{}};
    const bin=Math.round(gap/15);cell.bins[bin]=(cell.bins[bin]||0)+1;cell.n++;data.headways[key]=cell;
   }
   if(!last||at>last.at)data.last_passage[seq]={at,vehicle:v.id};
   for(const p of history){
    const seconds=at-p.at,from=stops.find(s=>s.seq===p.seq);
    if(!from||seq<=p.seq||seq-p.seq>12||seconds<=0||seconds>1800)continue;
    const meters=Math.hypot((stop.lon-from.lon)*Math.cos(stop.lat*Math.PI/180)*111195,(stop.lat-from.lat)*111195);
    if(seconds<meters/(100/3.6))continue;
    const key=`${hour(p.at)}:${p.seq}:${seq}`,cell=data.travel[key]||{n:0,bins:{}};
    const bin=Math.round(seconds/15);cell.bins[bin]=(cell.bins[bin]||0)+1;cell.n++;data.travel[key]=cell;
   }
   history.push({seq,at});
  }
  data.progress[v.id]={seq,at,stops:history.slice(-12),grade_recorded:gradeRecorded,availability_recorded:availabilityRecorded};changed=true;
 }
 return {value:data,changed};
}

export function crowdSummary(records,route,targetHour){
 const sections={},total=[0,0,0,0],availability={};
 for(const {day,value} of records){
  for(const [key,n] of Object.entries(value.grades||{})){
   const [seq,slot,grade]=key.split(':');if(Math.floor(Number(slot)/4)!==targetHour)continue;
   const s=sections[seq]||{counts:[0,0,0,0],dates:new Set(),availability:{}};
   s.counts[Number(grade)-3]+=n;s.dates.add(day);sections[seq]=s;total[Number(grade)-3]+=n;
  }
  for(const [key,pair] of Object.entries(value.availability||{})){
   const [seq,slot,grade]=key.split(':');if(Math.floor(Number(slot)/4)!==targetHour)continue;
   const s=sections[seq]||{counts:[0,0,0,0],dates:new Set(),availability:{}};
   const a=s.availability[grade]||[0,0],all=availability[grade]||[0,0];
   for(let i=0;i<2;i++){a[i]+=pair[i];all[i]+=pair[i];}
   s.availability[grade]=a;availability[grade]=all;s.dates.add(day);sections[seq]=s;
  }
 }
 return {route,hour:targetHour,counts:total,availability,dates:records.map(r=>r.day),
  sections:Object.fromEntries(Object.entries(sections).map(([seq,s])=>[seq,{...s,dates:[...s.dates]}])),
  unit:'deduplicated_vehicle_section_observations_not_passengers'};
}

export function headwaySummary(records,route,targetHour){
 const groups={};
 for(const {day,value} of records)for(const [key,c] of Object.entries(value.headways||{})){
  const [h,seq]=key.split(':');if(Number(h)!==targetHour)continue;
  const g=groups[seq]||{n:0,bins:{},dates:new Set()};g.n+=c.n;g.dates.add(day);
  for(const [bin,n] of Object.entries(c.bins))g.bins[bin]=(g.bins[bin]||0)+n;groups[seq]=g;
 }
 return Object.fromEntries(Object.entries(groups).map(([seq,g])=>{
  let n=0,median=0;for(const [bin,count] of Object.entries(g.bins).map(([b,n])=>[Number(b),n]).sort((a,b)=>a[0]-b[0])){
   n+=count;if(n>=Math.ceil(g.n/2)){median=bin*15;break;}
  }
  return [seq,{n:g.n,median_seconds:median,dates:[...g.dates],hour:targetHour,unit:'distinct_vehicle_confirmed_stop_passage_gaps'}];
 }));
}
export function travelSummary(records,route,targetHour){
 const groups={};
 for(const {day,value} of records)for(const [key,c] of Object.entries(value.travel||{})){
  const [h,a,b]=key.split(':');if(Number(h)!==targetHour)continue;
  const id=`${route}:${a}:${b}`,g=groups[id]||{n:0,bins:{},dates:new Set()};
  g.n+=c.n;g.dates.add(day);for(const [k,n] of Object.entries(c.bins))g.bins[k]=(g.bins[k]||0)+n;groups[id]=g;
 }
 return Object.fromEntries(Object.entries(groups).map(([id,g])=>{
  const bins=Object.entries(g.bins).map(([k,n])=>[Number(k)*15,n]).sort((a,b)=>a[0]-b[0]);
  const q=p=>{let n=0;for(const [seconds,count] of bins){n+=count;if(n>=Math.max(1,Math.ceil(p*g.n)))return seconds;}};
  return [id,{n:g.n,days:g.dates.size,dates:[...g.dates],median_seconds:q(.5),p10_seconds:q(.1),p90_seconds:q(.9),
   cohort:'same_hour_pooled_dates',kind:'deduplicated_at_stop_travel_histogram_15s',sampling_gap_max_seconds:120}];
 }));
}
