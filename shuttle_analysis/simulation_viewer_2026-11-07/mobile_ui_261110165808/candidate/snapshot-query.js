// Read-only queries of the same replay and half-hour aggregates used by the map
// and charts. A retrospective bin mean is not a new arrival's point forecast.
export function parseSnapshotTime(value,start=40800,end=83400){
  if(typeof value!=='string'||!/^\d{2}:\d{2}(:\d{2})?$/.test(value))return null;
  const [hour,minute,second=0]=value.split(':').map(Number);
  if(hour>23||minute>59||second>59)return null;
  const time=hour*3600+minute*60+second;
  return time>=start&&time<=end?time:null;
}

export function snapshotAt(state){
  const node=state.common.hot_nodes[state.stop],t=state.second;
  const start=state.common.start_second,end=state.common.end_second;
  const rows=state.data.queue_timeline[node]||[];
  let lo=0,hi=rows.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(rows[mid][0]<=t)lo=mid+1;else hi=mid;}
  const current=lo?rows[lo-1]:[t,0,0];
  const bin=Math.floor(t/1800)*1800;
  // The replay endpoint is selectable, but is outside the final half-open
  // arrival bin. Do not silently return the preceding bin's average there.
  const metric=t>=start&&t<end?state.chartData?.half_hourly?.[state.scenario]?.[state.day]?.[String(node)]?.[String(bin)]:null;
  const next=state.data.events.find(e=>e[1]===node&&e[0]>t);
  return {
    node,second:t,queue:current[1],denied:current[2],
    binStart:Math.max(start,bin),binEnd:Math.min(end,bin+1800),
    metric:metric||null,
    mean:metric?.mean_wait_min??null,p90:metric?.p90_wait_min??null,
    nextSecond:next?.[0]??null,nextWait:next?(next[0]-t)/60:null,
    atEnd:t>=end,
  };
}

export function summaryMarkup(s,{clock,fmt}){
  const minutes=value=>value===null?'—':`${fmt(value)}분`;
  const next=s.nextSecond===null?'남은 모형 운행 없음':`다음 모형 차량까지 ${minutes(s.nextWait)} · ${clock(s.nextSecond)}`;
  const window=s.atEnd?'재생 범위 끝 · 도착 구간 없음':`${clock(s.binStart).slice(0,5)}~${clock(s.binEnd).slice(0,5)} 도착 구간`;
  let note='탑승 완료 흐름 기준 · 경로 변경·미탑승 제외';
  if(s.mean===null)note=s.atEnd?'이 시각은 마지막 도착 구간의 바깥입니다.':!s.metric?'구간 대기자료 없음':s.metric.arrival_weight<=0?'이 구간의 도착량 없음':'탑승 완료 흐름이 없어 평균 계산 불가';
  return `<p class="snapshot-instant">현재 대기 <strong data-snapshot-queue>${fmt(s.queue)}</strong>명 상당 · 만차 잔류 <b>${fmt(s.denied)}</b></p><p class="snapshot-window" data-snapshot-window>${window}</p><div class="snapshot-metrics"><span>평균 대기<strong data-snapshot-mean>${minutes(s.mean)}</strong></span><span title="탑승 완료 흐름의 90%가 이 시간 이내 대기">90백분위<strong data-snapshot-p90>${minutes(s.p90)}</strong></span></div><p class="snapshot-next" data-snapshot-next>${next}</p><p class="snapshot-note">${note}<br>구간 통계이며 개인의 시점 예측·실측이 아닙니다. 다음 차 탑승을 보장하지 않습니다.</p>`;
}

export function installSnapshotQuery({state,clock,goTo}){
  const $=id=>document.getElementById(id);
  // Mount once from the shared v5 module, so both entry pages and later HTML
  // rebuilds retain the feature without a second copy of the form template.
  if(!$('snapshot-open'))document.querySelector('.stop-map-hint').innerHTML='<span>정류장 표식에서 현재 대기량 확인</span><button type="button" id="snapshot-open" class="snapshot-launch" aria-haspopup="dialog" aria-controls="snapshot-dialog" disabled>요일·시간 조회 ↗</button>';
  if(!$('snapshot-sidebar'))$('next-bus').insertAdjacentHTML('beforebegin','<div id="snapshot-sidebar" class="snapshot-wait" aria-label="선택 시각의 대기시간 참고"></div>');
  if(!$('snapshot-dialog'))document.body.insertAdjacentHTML('beforeend',`<dialog id="snapshot-dialog" aria-labelledby="snapshot-title" aria-describedby="snapshot-help">
<button type="button" id="snapshot-close" class="close-button" aria-label="요일·시간 조회 닫기">닫기</button>
<h2 id="snapshot-title">요일·시간으로 상황 보기</h2>
<p id="snapshot-help">선택한 시각의 지도·대기인원과 해당 도착 구간의 평균 대기시간을 함께 확인합니다.</p>
<p id="snapshot-context" class="snapshot-context"></p>
<form id="snapshot-form" novalidate>
<div class="snapshot-fields"><label class="field" for="snapshot-day">요일<select id="snapshot-day" required autofocus></select></label><label class="field" for="snapshot-time">시각<input id="snapshot-time" type="time" min="11:20:00" max="23:10:00" step="1" required aria-describedby="snapshot-time-help snapshot-error"></label></div>
<p id="snapshot-time-help" class="snapshot-note">조회 범위 11:20:00~23:10:00 · 현재 배차 시나리오와 계산 모형을 유지합니다.</p>
<label class="field" for="snapshot-stop">승차지<select id="snapshot-stop" required></select></label>
<p id="snapshot-error" class="snapshot-error" role="alert"></p>
<button type="submit" id="snapshot-submit" class="snapshot-submit">지도와 대기시간 보기</button>
<p class="snapshot-note">대기인원은 가중 모형값입니다. 평균·90백분위 대기는 해당 30분 도착 구간의 탑승 완료 흐름 통계이며, 개인의 시점 예측이나 실측 대기시간이 아닙니다.</p>
</form></dialog>`);
  const dialog=$('snapshot-dialog'),form=$('snapshot-form');
  let busy=false;
  $('snapshot-open').addEventListener('click',()=>{
    if(!state.ready)return;
    $('snapshot-day').innerHTML=$('weekday').innerHTML;$('snapshot-day').value=state.day;
    $('snapshot-stop').innerHTML=$('stop-select').innerHTML;$('snapshot-stop').value=state.stop;
    $('snapshot-time').value=clock(state.second);$('snapshot-time').setCustomValidity('');
    $('snapshot-context').textContent=`${$('scenario').selectedOptions[0].textContent} · ${$('policy').selectedOptions[0].textContent}`;
    $('snapshot-error').textContent='';dialog.showModal();
  });
  $('snapshot-close').addEventListener('click',()=>dialog.close());
  $('snapshot-time').addEventListener('input',()=>{$('snapshot-time').setCustomValidity('');$('snapshot-error').textContent='';});
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;
    const time=parseSnapshotTime($('snapshot-time').value,state.common.start_second,state.common.end_second);
    if(time===null){$('snapshot-time').setCustomValidity('11:20:00부터 23:10:00 사이의 시각을 입력해 주세요.');form.reportValidity();return;}
    if(!form.reportValidity())return;
    busy=true;form.setAttribute('aria-busy','true');$('snapshot-submit').disabled=true;$('snapshot-submit').textContent='조회 중…';
    try{
      const success=await goTo($('snapshot-day').value,time,$('snapshot-stop').value,()=>dialog.open);
      if(!success)throw new Error('선택한 자료를 불러오지 못했습니다. 다시 조회해 주세요.');
      if(dialog.open)dialog.close();
    }catch(error){$('snapshot-error').textContent=error.message;}
    finally{busy=false;form.removeAttribute('aria-busy');$('snapshot-submit').disabled=false;$('snapshot-submit').textContent='지도와 대기시간 보기';}
  });
}
