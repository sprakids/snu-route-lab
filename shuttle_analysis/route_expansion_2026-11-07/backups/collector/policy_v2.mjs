import {ROUTES,START,END,dayStart} from './schedule.mjs';
export function operatingPolicy(day,approved=1000){
 const weekend=[0,6].includes(new Date(day+'T12:00:00+09:00').getUTCDay());
 return approved>=10000?{id:'focused-6500-v2',cap:weekend?2000:6500,reserve:weekend?220:520,peak_seconds:15,other_seconds:120,weekend,approved_limit:approved}:
  {id:'approval-pending-950',cap:950,reserve:50,approved_limit:approved,weekend};
}
export function batchCalendar(day,policy){
 const zero=dayStart(day),out=[];
 for(let second=START*60;second<=END*60;){
  const peak=!policy.weekend&&second>=900*60&&second<1140*60;
  out.push({id:`${day}:v2:${second}`,at:zero+second*1000,routes:ROUTES,pool:peak?'peak':'baseline'});
  second+=peak?15:120;
 }
 return out;
}
