import {ROUTES,START,END,dayStart} from './schedule.mjs';
export function operatingPolicy(day,approved=1000){
 const weekend=[0,6].includes(new Date(day+'T12:00:00+09:00').getUTCDay());
 const expanded=ROUTES.length>5,ready=approved>=15000;
 return approved>=10000?{id:expanded?'focused-eight-v3':'focused-6500-v2',
  cap:expanded?(weekend?3200:ready?10400:9800):(weekend?2000:6500),
  reserve:expanded?(weekend?352:ready?832:712):(weekend?220:520),
  peak_seconds:expanded&&!ready?16:15,other_seconds:120,weekend,approved_limit:approved,route_count:ROUTES.length,
  higher_limit_verified:ready,quota_mode:expanded&&!ready?'existing_10000_eight_routes':'verified_operating_limit'}:
  {id:'approval-pending-950',cap:950,reserve:50,approved_limit:approved,weekend};
}
export function batchCalendar(day,policy){
 const zero=dayStart(day),out=[];
 for(let second=START*60;second<=END*60;){
  const peak=!policy.weekend&&second>=900*60&&second<1140*60;
  out.push({id:`${day}:v2:${second}`,at:zero+second*1000,routes:ROUTES,pool:peak?'peak':'baseline'});
  second+=peak?policy.peak_seconds:policy.other_seconds;
 }
 return out;
}
