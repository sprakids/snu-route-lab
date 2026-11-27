// Resolve only the initial view. Subsequent user selections remain untouched.
export function initialReplayClock(now=new Date(),search='',start=40800,end=83400){
  const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{
    timeZone:'Asia/Seoul',weekday:'short',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',
  }).formatToParts(now).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
  const today=parts.weekday.toLowerCase().slice(0,3),days=['mon','tue','wed','thu','fri'];
  const names={mon:'월요일',tue:'화요일',wed:'수요일',thu:'목요일',fri:'금요일',sat:'토요일',sun:'일요일'};
  const current=Number(parts.hour)*3600+Number(parts.minute)*60+Number(parts.second);
  const params=new URLSearchParams(search),daySpecified=days.includes(params.get('day'));
  const day=daySpecified?params.get('day'):days.includes(today)?today:'fri';
  const finite=key=>params.has(key)&&params.get(key).trim()!==''&&Number.isFinite(Number(params.get(key)));
  const timeSpecified=finite('second')||finite('minute');
  const requested=finite('second')?Number(params.get('second')):finite('minute')?Number(params.get('minute'))*60:current;
  const second=Math.floor(Math.max(start,Math.min(end,requested))),notes=[];
  const clock=n=>`${String(Math.floor(n/3600)).padStart(2,'0')}:${String(Math.floor(n/60)%60).padStart(2,'0')}`;
  if(!daySpecified&&!days.includes(today))notes.push(`오늘은 ${names[today]}입니다. 주말 자료가 없어 금요일 참고 모형을 표시합니다.`);
  if(!timeSpecified){
    if(current<start||current>end)notes.push(`현재 한국 시각 ${clock(current)} · 재생 범위 ${clock(start)}~${clock(end)} 중 가까운 시각을 표시합니다.`);
    else notes.push(`현재 한국 시각 ${clock(current)}에서 시작합니다.`);
  }else if(requested<start||requested>end)notes.push('링크의 시각이 재생 범위를 벗어나 가까운 시각을 표시합니다.');
  const requiresNotice=(!daySpecified&&!days.includes(today))||requested<start||requested>end;
  return {day,second,kstWeekday:today,kstCurrentSecond:current,daySpecified,timeSpecified,requiresNotice,notice:notes.join(' ')};
}
