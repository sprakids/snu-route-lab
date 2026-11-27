const $=id=>document.getElementById(id);
const DID=['mon','tue','wed','thu','fri'],DAY=['월','화','수','목','금'];
const fmt=(n,d=1)=>n===null||n===undefined?'—':new Intl.NumberFormat('ko-KR',{maximumFractionDigits:d}).format(n);
const color=(v,max)=>v===null?'#f0f3ed':`hsl(96 29% ${96-Math.min(1,v/max)*49}%)`;
const timeLabel=t=>`${String(Math.floor(t/3600)).padStart(2,'0')}:${String(Math.floor(t/60)%60).padStart(2,'0')}`;
export function createGraphs(ctx){
  let request=0,pair=null,lineNode=-1,lineWidth=760;
  function heatmap(target,getValue,{legacy=false,maxOverride=null}={}){
    const step=legacy?3600:1800,starts=Array.from({length:legacy?7:14},(_,i)=>43200+i*step);
    const rows=DID.map((d,i)=>starts.map(start=>({d,i,start,end:start+step,...getValue(d,i,start)})));
    const max=maxOverride??Math.max(20,...rows.flat().map(c=>c.mean_wait_min??0));
    const table=document.createElement('table');table.className=`heatmap ${legacy?'legacy-hourly':'half-hour'}`;
    table.innerHTML=`<caption class="sr-only">요일·정류장 도착 ${legacy?'1시간':'30분'} 구간별 평균 대기시간, 분</caption><thead><tr><th scope="col">요일</th>`+starts.map(t=>`<th scope="col">${timeLabel(t)}${legacy?'':`<small>~${timeLabel(t+step)}</small>`}</th>`).join('')+'</tr></thead>';
    const body=document.createElement('tbody');
    rows.forEach((row,i)=>{
      const tr=document.createElement('tr');tr.innerHTML=`<th scope="row">${DAY[i]}</th>`;
      row.forEach(cell=>{
        const td=document.createElement('td'),mark=document.createElement(legacy?'span':'button');mark.className='heat-cell';
        mark.style.background=color(cell.mean_wait_min,max);if(legacy)mark.style.display='block';
        const value=cell.mean_wait_min;mark.textContent=fmt(value);
        if((cell.unserved_weight??0)>.005){const small=document.createElement('small');small.textContent=`미탑승 ${fmt(cell.unserved_weight)}`;mark.append(small);}
        mark.title=`${DAY[i]} ${timeLabel(cell.start)}~${timeLabel(cell.end)} 도착 · 평균 ${fmt(value)}분 · 도착량 ${fmt(cell.arrival_weight)} · 미탑승 ${fmt(cell.unserved_weight??0)}`;
        if(!legacy){
          mark.dataset.day=cell.d;mark.dataset.start=cell.start;mark.dataset.end=cell.end;
          mark.setAttribute('aria-label',mark.title);mark.classList.toggle('selected',ctx.state.day===cell.d&&ctx.state.second>=cell.start&&ctx.state.second<cell.end);
          mark.addEventListener('click',()=>ctx.goTo(cell.d,cell.start));
        }
        td.append(mark);tr.append(td);
      });body.append(tr);
    });table.append(body);
    const legend=document.createElement('p');legend.className='chart-footnote';legend.textContent=`색 농도: 0~${fmt(max)}분 · 진할수록 오래 대기`;
    $(target).replaceChildren(table,legend);
  }
  function table(halfHourly){
    const el=document.createElement('table');el.className='metrics-table';
    el.innerHTML='<thead><tr><th>도착 시간대</th><th>탑승자 평균(분)</th><th>90백분위(분)</th><th>만차 경험</th><th>경로 변경</th><th>미탑승 가중치</th></tr></thead>';
    const body=document.createElement('tbody');
    for(let t=39600;t<83400;t+=1800){
      const start=Math.max(40800,t),end=Math.min(83400,t+1800);
      const r=halfHourly[String(t)],tr=document.createElement('tr');tr.dataset.start=start;tr.dataset.end=end;
      if(ctx.state.second>=start&&ctx.state.second<end)tr.className='selected';
      const window=`${timeLabel(start)}–${timeLabel(end)}`;
      tr.innerHTML=`<td>${window}</td><td>${fmt(r.mean_wait_min)}</td><td>${fmt(r.p90_wait_min)}</td><td>${r.denied_share===null?'—':fmt(r.denied_share*100)+'%'}</td><td>${fmt(r.switched_weight??0)}</td><td>${fmt(r.unserved_weight)}</td>`;
      body.append(tr);
    }el.append(body);$('hourly-table').replaceChildren(el);
  }
  function line(){
    if(!pair)return;const {state}=ctx,node=state.common.hot_nodes[state.stop];lineNode=node;
    const W=Math.max(340,Math.min(760,$('queue-line').clientWidth||760)),H=245,P={l:47,r:14,t:15,b:33},start=state.common.start_second,end=state.common.end_second;lineWidth=W;
    const data=pair.map(d=>d.queues.map(row=>row[node]));
    const max=Math.max(5,...data.flat());const top=Math.ceil(max/5)*5;
    const x=t=>P.l+(t-start)/(end-start)*(W-P.l-P.r),y=v=>H-P.b-v/top*(H-P.t-P.b);
    const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('role','img');svg.setAttribute('tabindex','0');svg.setAttribute('aria-label','기준 배차와 피크 최소 간격의 시간별 대기열 비교');
    for(let i=0;i<=4;i++){
      const v=top*i/4,yy=y(v);svg.insertAdjacentHTML('beforeend',`<line x1="${P.l}" x2="${W-P.r}" y1="${yy}" y2="${yy}" stroke="#e7ede2"/><text x="${P.l-9}" y="${yy+3}" text-anchor="end">${fmt(v,0)}</text>`);
    }
    for(const h of [12,15,19,23])svg.insertAdjacentHTML('beforeend',`<text x="${x(h*3600)}" y="${H-9}" text-anchor="middle">${h}:00</text>`);
    for(let t=Math.ceil(start/1800)*1800;t<=end;t+=1800)svg.insertAdjacentHTML('beforeend',`<line x1="${x(t)}" x2="${x(t)}" y1="${H-P.b}" y2="${H-P.b+4}" stroke="#a7b8b0"/>`);
    // Same scale for both scenarios; zero included. Every stored 5-second sample is retained.
    [1,0].forEach(i=>{
      const path=document.createElementNS(ns,'path');path.setAttribute('d',data[i].map((v,k)=>`${k?'L':'M'}${x(start+k*pair[i].queue_step_seconds).toFixed(2)},${y(v).toFixed(2)}`).join(''));
      path.setAttribute('fill','none');path.setAttribute('stroke',i?'#a48565':'#1b5a50');path.setAttribute('stroke-width',i?'1.5':'2');
      if(i)path.setAttribute('stroke-dasharray','5 4');svg.append(path);
    });
    const cursor=document.createElementNS(ns,'line');cursor.id='line-time-cursor';cursor.setAttribute('stroke','#c85645');cursor.setAttribute('stroke-width','1.2');cursor.setAttribute('y1',P.t);cursor.setAttribute('y2',H-P.b);svg.append(cursor);
    svg.addEventListener('click',event=>{const r=svg.getBoundingClientRect(),px=(event.clientX-r.left)/r.width*W;ctx.selectTime(start+Math.max(0,Math.min(1,(px-P.l)/(W-P.l-P.r)))*(end-start));});
    svg.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();ctx.selectTime(state.second+(event.key==='ArrowRight'?60:-60));}});
    $('queue-line').replaceChildren(svg);updateCursor();
  }
  function updateCursor(){
    for(const el of $('current-heatmap').querySelectorAll('[data-start]'))el.classList.toggle('selected',el.dataset.day===ctx.state.day&&ctx.state.second>=Number(el.dataset.start)&&ctx.state.second<Number(el.dataset.end));
    for(const el of $('hourly-table').querySelectorAll('tr[data-start]'))el.classList.toggle('selected',ctx.state.second>=Number(el.dataset.start)&&ctx.state.second<Number(el.dataset.end));
    if(!pair||lineNode<0)return;const {state}=ctx,start=state.common.start_second,end=state.common.end_second;
    const x=47+(state.second-start)/(end-start)*(lineWidth-47-14),el=$('line-time-cursor');
    if(el){el.setAttribute('x1',x);el.setAttribute('x2',x);}
    $('line-values').replaceChildren(...pair.map((d,i)=>{const span=document.createElement('span');span.textContent=`${i?'기준 배차':'피크 최소 간격'} · ${ctx.clock(state.second)} · 대기 ${fmt(ctx.queueAt(d,lineNode,state.second)[0])}`;return span;}));
  }
  async function render(){
    const token=++request,{state}=ctx;if(!state.ready||!state.common||!state.chartData?.half_hourly)return;
    const node=state.common.hot_nodes[state.stop],charts=state.chartData;
    $('heatmap-scenario').textContent=`${state.policy==='city'?(state.empiricalSpeed?'관측 속도 참고판':'시내·셔틀 정원 v5'):state.policy==='adaptive'?'이전 v4 경로 변경':'이전 v3 경로 유지'} · ${state.common.scenarios[state.scenario].label} · ${$('stop-select').selectedOptions[0].textContent}`;
    const halves=charts.half_hourly;
    const scaleMax=Math.max(20,...Object.values(halves).flatMap(days=>Object.values(days).flatMap(d=>Object.entries(d[String(node)]).filter(([t])=>Number(t)>=43200&&Number(t)<68400).map(([t,r])=>r.mean_wait_min??0))));
    heatmap('current-heatmap',(d,i,t)=>halves[state.scenario][d][String(node)][String(t)],{maxOverride:scaleMax});
    table(halves[state.scenario][state.day][String(node)]);
    const legacy=charts.legacy_wait_charts.find(c=>c.node===state.stop);
    heatmap('legacy-heatmap',(d,i,t)=>({mean_wait_min:legacy?.config.rows.find(r=>r.weekday===DAY[i]&&r.hour===`${t/3600}시`)?.wait_min??null}),{legacy:true});
    $('line-selection').textContent=`${ctx.dayName(state.day)} · ${$('stop-select').selectedOptions[0].textContent}`;
    $('queue-line').textContent='두 배차 시나리오의 그래프를 준비하고 있습니다.';
    try{
      const results=await Promise.all([ctx.load('peak',state.day),ctx.load('regular',state.day)]);
      if(token!==request)return;pair=results;line();
    }catch(error){if(token===request)$('queue-line').textContent='비교 자료를 불러오지 못했습니다. 다시 선택해 주세요.';console.error('Comparison chart load failed',error);}
  }
  for(const [id,legacy] of [['current-charts',false],['legacy-charts',true]])$(id).addEventListener('click',()=>{
    $('current-chart-content').hidden=legacy;$('legacy-chart-content').hidden=!legacy;
    $('current-charts').classList.toggle('active',!legacy);$('legacy-charts').classList.toggle('active',legacy);
    $('current-charts').setAttribute('aria-pressed',String(!legacy));$('legacy-charts').setAttribute('aria-pressed',String(legacy));
  });
  window.addEventListener('resize',()=>{if(ctx.state.pane==='charts')line();});
  return {render,updateCursor};
}
