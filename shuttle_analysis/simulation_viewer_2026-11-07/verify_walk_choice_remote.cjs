// Public immutable-data parity, separate from model and browser validation.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const base=process.argv[2],kind=process.argv[3],output=process.argv[4];
assert(base&&['data','ui'].includes(kind)&&output);
const root=path.join(__dirname,'public'),read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const latest=read('routing-model/latest.json'),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const datasets=['common','charts',...['peak','regular'].flatMap(s=>['mon','tue','wed','thu','fri'].map(d=>s+'-'+d))];
const files=[...datasets.map(n=>'data/capacity_v9/'+n+'.json'),'data/half_hour_v1/capacity_v9.json','data/walk_review_v1/report.json',latest.payload_path.slice(1),'walk-choice-waits.csv'];
if(kind==='ui')files.push('routing-model/latest.json','viewer-v5.js','graphs-v5.js','json-loader.js','index.html','city.html','walk-choice-review.js','walk-choice-methodology.html','walk-choice-methodology.md','data/capacity_v7/common.json');
let index=0;const results=[];
async function worker(){while(index<files.length){
  const name=files[index++],raw=fs.readFileSync(path.join(root,name)),started=performance.now();
  const res=await fetch(new URL(name,base),{signal:AbortSignal.timeout(120000)});assert.equal(res.status,200,name);
  const actual=Buffer.from(await res.arrayBuffer());assert.equal(sha(actual),sha(raw),name);
  if(name.startsWith('data/')){assert.equal(res.headers.get('content-encoding'),'br',name);assert(res.headers.get('content-type').includes('application/json'),name);assert(res.headers.get('cache-control').includes('immutable'),name);}
  results.push({path:name,status:res.status,sha256:sha(actual),decoded_bytes:actual.length,encoding:res.headers.get('content-encoding'),seconds:Math.round((performance.now()-started)*100)/100});
}}
(async()=>{
  await Promise.all([worker(),worker()]);
  const payload=read(latest.payload_path.slice(1));assert.equal(sha(fs.readFileSync(path.join(root,latest.payload_path.slice(1)))),latest.sha256);
  assert.equal(payload.latest_simulation.source_simulation,'capacity_v9');
  assert.equal(payload.walk_choice_behavior.maximum_changes,null);
  let excluded=0;
  for(const day of payload.queue_readiness.visits_by_weekday){for(const [rid,audit] of Object.entries(day.routes)){
    const rows=payload.routes[rid].ready_packets.filter(r=>r[0]===day.weekday);
    const mass=rows.reduce((sum,r)=>sum+r[3],0);assert(Math.abs(mass-(audit.ready_entry_weight||0))<1e-5);
    assert(Math.abs(audit.source_visit_weight-(audit.ready_entry_weight||0)-(audit.preparation_cancelled_weight||0)-(audit.after_window_ready_weight||0))<1e-5);
    for(const row of rows)assert(row[4]===null||row[4]>=row[2]);
    excluded+=audit.preparation_cancelled_weight||0;
  }}
  assert(excluded>0);
  const result={status:'PASS',base,kind,files:results.length,routing_model_id:latest.model_id,source_simulation:'capacity_v9',payload_sha256:latest.sha256,excluded_preparation_visit_weight:excluded,source_demand_removed:false,results};
  fs.writeFileSync(output,JSON.stringify(result,null,2));console.log(JSON.stringify({...result,results:undefined}));
})().catch(e=>{console.error(e);process.exitCode=1});
