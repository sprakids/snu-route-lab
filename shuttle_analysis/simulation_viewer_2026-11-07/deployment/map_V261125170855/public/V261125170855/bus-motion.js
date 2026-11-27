/** Distance in metres and speed in m/s from the exported constant-acceleration phases. */
export function motionAt(profile,elapsed){
  const {t,d,v,cap}=profile;
  if(elapsed<=0)return {distance:0,speed:0,limit:cap[0]||0};
  if(elapsed>=t.at(-1))return {distance:d.at(-1),speed:0,limit:0};
  let lo=0,hi=t.length;while(lo<hi){const m=(lo+hi)>>1;if(t[m]<=elapsed)lo=m+1;else hi=m;}
  const i=Math.max(0,lo-1),dt=elapsed-t[i],duration=t[i+1]-t[i],a=(v[i+1]-v[i])/duration;
  return {distance:Math.min(d[i+1],Math.max(d[i],d[i]+v[i]*dt+.5*a*dt*dt)),
    speed:Math.max(0,Math.min((cap[i]||0)/3.6,v[i]+a*dt)),limit:cap[i]||0};
}
