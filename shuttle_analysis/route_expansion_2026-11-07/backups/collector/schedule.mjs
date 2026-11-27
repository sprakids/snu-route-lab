export const ROUTES=['100100250','100100251','100100253','120900011','120900012'];
export const LIMITS={baseline:360,peak:405,offpeak:135,retry:50};
export const START=11*60+20,END=23*60+10;
export function kstDay(ms){return new Date(ms+9*3600000).toISOString().slice(0,10);}
export function dayStart(day){return Date.parse(day+'T00:00:00+09:00');}
export function allocate(total,weights,cap=100){
  const out=weights.map(()=>0);let left=total;
  while(left>0){
    const active=weights.map((w,i)=>({i,w:Math.max(.001,w)})).filter(x=>out[x.i]<cap);
    if(!active.length)break;
    const sum=active.reduce((s,x)=>s+x.w,0);let placed=0;
    const shares=active.map(x=>({...x,share:left*x.w/sum}));
    for(const x of shares){const n=Math.min(cap-out[x.i],Math.floor(x.share));out[x.i]+=n;placed+=n;}
    left-=placed;
    for(const x of shares.sort((a,b)=>(b.share%1)-(a.share%1)||a.i-b.i)){
      if(!left)break;if(out[x.i]<cap){out[x.i]++;left--;}
    }
  }
  return out;
}
export function demand(profile,day,minute,route){
  const weekday=(new Date(day+'T12:00:00+09:00').getUTCDay()+6)%7;
  const p=profile?.[String(weekday)]?.[String(minute)]?.[route]||{};
  const term=day>='2026-09-01'&&day<='2026-12-21'&&!['2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-10-15'].includes(day);
  return {history:Math.min(1,Math.max(0,p.history||0)),classes:term?Math.min(1,Math.max(0,p.classes||0)):0};
}
export function schedule(day,profile={}){
  const zero=dayStart(day),jobs=[];
  for(let m=START;m<=END;m+=10)for(const route of ROUTES)
    jobs.push({id:`${day}:base:${m}:${route}`,route,pool:'baseline',at:zero+m*60000});
  for(const pool of ['peak','offpeak']){
    const bins=[];
    for(let m=START;m<END;m+=5)if((m>=900&&m<1140)===(pool==='peak'))bins.push(m);
    const weights=bins.map(m=>ROUTES.reduce((s,r)=>{const d=demand(profile,day,m,r);return s+.5*d.history+.25*d.classes+.01;},0));
    const counts=allocate(LIMITS[pool],weights);
    bins.forEach((m,b)=>{for(let n=0;n<counts[b];n++)jobs.push({id:`${day}:${pool}:${m}:${n}`,pool,
      at:zero+m*60000+Math.floor(n*300/counts[b]/15)*15000});});
  }
  return jobs.sort((a,b)=>a.at-b.at||(a.pool==='baseline'?-1:b.pool==='baseline'?1:a.id.localeCompare(b.id)));
}
export function chooseRoute(job,latest,profile,day,now){
  if(job.route)return job.route;
  const minute=Math.floor((now-dayStart(day))/60000),bin=Math.floor(minute/5)*5;
  // Never put an extra request immediately before/after a fixed baseline tick.
  const phase=(now-(dayStart(day)+START*60000))%600000;
  if(phase<15000||phase>585000)return null;
  return ROUTES.map(route=>{
    const s=latest[route]||{},age=(now-(s.attempted_at||0))/1000;
    const d=demand(profile,day,bin,route);
    return {route,age,score:.5*d.history+.25*d.classes+.25*Math.max(Math.min(1,age/600),s.changed?1:0),
      eligible:age>=((s.duplicate_count||0)>=2?60:15)};
  }).filter(x=>x.eligible).sort((a,b)=>b.score-a.score||b.age-a.age||a.route.localeCompare(b.route))[0]?.route||null;
}
export function allowedReservation(counts,pool){return Object.values(counts).reduce((a,b)=>a+b,0)<950&&(counts[pool]||0)<LIMITS[pool];}
