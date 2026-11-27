const $=id=>document.getElementById(id),fmt=v=>v===null||v===undefined?'—':new Intl.NumberFormat('ko-KR',{maximumFractionDigits:2}).format(v);
const ns='http://www.w3.org/2000/svg';
function svgElement(tag,attributes={},text=''){
  const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attributes))el.setAttribute(k,v);if(text)el.textContent=text;return el;
}
async function start(){
  const response=await fetch('data/capacity_review_v1/report.json');if(!response.ok)throw new Error('검증 자료 응답 '+response.status);
  const data=await response.json();if(data.summary.status!=='PASS')throw new Error('완료된 검증 자료가 아닙니다.');
  const curve=data.walking_curve,svg=$('walking-curve'),X=d=>50+d/2000*590,Y=w=>215-w*190;
  for(const weight of [0,.25,.5,.75,1]){
    svg.append(svgElement('line',{x1:50,x2:640,y1:Y(weight),y2:Y(weight),stroke:'currentColor',opacity:'.12'}));
    svg.append(svgElement('text',{x:42,y:Y(weight)+4,'text-anchor':'end',fill:'currentColor','font-size':11},String(weight*100)));
  }
  for(const distance of [0,500,1000,1500,2000])svg.append(svgElement('text',{x:X(distance),y:242,'text-anchor':'middle',fill:'currentColor','font-size':11},distance+'m'));
  svg.append(svgElement('path',{d:curve.map(([d,w],i)=>(i?'L':'M')+X(d)+','+Y(w)).join(' '),fill:'none',stroke:'currentColor','stroke-width':3}));
  const cursor=svgElement('circle',{r:5,fill:'currentColor',stroke:'white','stroke-width':2});svg.append(cursor);
  function showDistance(){const d=Number($('distance').value),w=curve[Math.round(d/5)][1];cursor.setAttribute('cx',X(d));cursor.setAttribute('cy',Y(w));$('distance-value').textContent=`${fmt(d)}m · 상대 도보 고려도 ${new Intl.NumberFormat('ko-KR',{maximumFractionDigits:4}).format(w*100)} / 100`;}
  $('distance').addEventListener('input',showDistance);showDistance();
  function render(){
    const query=$('review-search').value.trim();
    const rows=data.rows.filter(r=>r.weekday===$('review-day').value&&r.scenario===$('review-scenario').value&&(!query||(r.stop+' '+r.ars).includes(query))).sort((a,b)=>b.max_continuous_wait_min-a.max_continuous_wait_min||b.max_queue-a.max_queue);
    const fragment=document.createDocumentFragment();
    for(const row of rows){
      const tr=document.createElement('tr');tr.dataset.node=row.node;
      for(const value of [row.stop+(row.ars?' · '+row.ars:''),fmt(row.mean_continuous_wait_min),fmt(row.p90_continuous_wait_min),fmt(row.max_continuous_wait_min),fmt(row.before_max_wait_min),fmt(row.over_20_minute_weight),fmt(row.max_queue)]){
        const td=document.createElement('td');td.textContent=value;tr.append(td);
      }fragment.append(tr);
    }
    $('review-body').replaceChildren(fragment);
    const over=rows.reduce((sum,r)=>sum+r.over_20_minute_weight,0),max=rows.reduce((m,r)=>Math.max(m,r.max_continuous_wait_min),0);
    $('review-status').textContent=`${rows.length}개 대기열 · 최대 연속대기 ${fmt(max)}분 · 20분 초과 ${fmt(over)}명 상당·회`;
    const changes=data.route_change_distribution[$('review-scenario').value][$('review-day').value],h=changes.weight_by_count;
    const percentages=[0,1,2,3,4].map(n=>`${n}회 ${fmt(100*(h[n]||0)/changes.input_weight)}%`);
    const tail=Object.entries(h).reduce((s,[n,w])=>s+(Number(n)>=5?w:0),0);
    $('change-summary').textContent=`선택 요일·배차의 전체 가중 이동: 변경 평균 ${fmt(changes.mean)}회 · ${percentages.join(' / ')} / 5회 이상 ${fmt(100*tail/changes.input_weight)}%. 횟수 상한 없이 계산한 결과이며 비율을 강제로 맞춘 값이 아닙니다.`;
  }
  for(const id of ['review-day','review-scenario'])$(id).addEventListener('change',render);
  $('review-search').addEventListener('input',render);render();
}
start().catch(error=>{$('review-status').textContent='검증 자료를 불러오지 못했습니다. 새로고침 후 다시 확인해 주세요.';$('review-status').setAttribute('role','alert');console.error(error);});
