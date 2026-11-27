const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const base=process.argv[2],kind=process.argv[3],output=process.argv[4];assert(base&&['data','ui'].includes(kind)&&output);
const root=path.join(__dirname,'public'),work=path.join(__dirname,'peak_pair_correction_2026-11-10');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8')),m=read(path.join(work,'pending_release.json'));
const pending=path.join(__dirname,m.directory),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const dataNames=['common','charts',...['peak','regular'].flatMap(s=>['mon','tue','wed','thu','fri'].map(d=>s+'-'+d))];
const files=[];
for(const [dataset,review,csv] of [['capacity_v9','walk_review_v1','walk-choice-waits.csv'],['capacity_v11','capacity_review_v1','capacity-correction-waits.csv']]){
  files.push(...dataNames.map(n=>'data/'+dataset+'/'+n+'.json'),'data/half_hour_v1/'+dataset+'.json','data/'+review+'/report.json',csv);
}
files.push('routing-model/releases/261110150729.json',m.payload_path.slice(1));
if(kind==='ui')files.push('routing-model/latest.json','viewer-v5.js','graphs-v5.js','json-loader.js','index.html','city.html',
  'capacity-correction-review.js','capacity-correction.html','capacity-correction.md','data/capacity_v7/common.json');
if(kind==='ui'&&fs.existsSync(path.join(root,'mobile-lab.js')))files.push('mobile-lab.js','mobile-lab.css');
function expected(name){if(name===m.payload_path.slice(1))return fs.readFileSync(path.join(pending,'payload.json'));
  if(name==='routing-model/latest.json')return fs.readFileSync(path.join(pending,'latest.json'));return fs.readFileSync(path.join(root,name));}
let index=0;const results=[];
async function worker(){while(index<files.length){
  const name=files[index++],raw=expected(name),started=performance.now();
  const res=await fetch(new URL(name,base),{signal:AbortSignal.timeout(120000)});assert.equal(res.status,200,name);
  const actual=Buffer.from(await res.arrayBuffer());assert.equal(sha(actual),sha(raw),name);
  if(name.startsWith('data/')){assert.equal(res.headers.get('content-encoding'),'br',name);assert(res.headers.get('content-type').includes('application/json'),name);assert(res.headers.get('cache-control').includes('immutable'),name);}
  results.push({path:name,status:200,sha256:sha(actual),decoded_bytes:actual.length,encoding:res.headers.get('content-encoding'),seconds:Math.round((performance.now()-started)*100)/100});
}}
(async()=>{
  await Promise.all([worker(),worker()]);const payload=read(path.join(pending,'payload.json'));
  assert.equal(sha(expected(m.payload_path.slice(1))),m.sha256);assert.equal(payload.latest_simulation.source_simulation,'capacity_v11');
  assert.equal(payload.walk_choice_behavior.maximum_changes,null);assert.equal(payload.routes['shuttle-41841'].capacity,44);
  assert.deepEqual(payload.routes['shuttle-41841'].capacity_periods,[{start_second:75600,capacity:60}]);
  assert.deepEqual(payload.routes['shuttle-41841'].dispatch_batches,[{start_second:54000,end_second:68400,vehicles:2}]);
  let excluded=0;
  for(const day of payload.queue_readiness.visits_by_weekday)for(const [rid,audit] of Object.entries(day.routes)){
    const rows=payload.routes[rid].ready_packets.filter(r=>r[0]===day.weekday),mass=rows.reduce((sum,r)=>sum+r[3],0);
    assert(Math.abs(mass-(audit.ready_entry_weight||0))<1e-5);assert(Math.abs(audit.source_visit_weight-(audit.ready_entry_weight||0)-(audit.preparation_cancelled_weight||0)-(audit.after_window_ready_weight||0))<1e-5);
    for(const row of rows)assert(row[4]===null||row[4]>=row[2]);excluded+=audit.preparation_cancelled_weight||0;
  }
  assert(excluded>0);const result={status:'PASS',anonymous:true,base,kind,files:results.length,routing_model_id:m.model_id,
    source_simulation:'capacity_v11',payload_sha256:m.sha256,excluded_preparation_visit_weight:excluded,
    old_v9_preserved:true,new_algorithm_included:false,results};fs.writeFileSync(output,JSON.stringify(result,null,2));console.log(JSON.stringify({...result,results:undefined}));
})().catch(e=>{console.error(e);process.exitCode=1});
