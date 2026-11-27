const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const source='C:/Users/김예준/Documents/ChatGPT/공대 문제해결/shuttle_analysis/simulation_viewer_2026-11-07/public';
const base='https://snu-shuttle-simulation.vercel.app',hash=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{
 const checks=await Promise.all(['viewer-v5.js','json-loader.js','index.html','data/capacity_v7/common.json','data/capacity_v7/peak-mon.json','data/capacity_v7/charts.json','data/half_hour_v1/capacity_v7.json'].map(async name=>{
  const r=await fetch(base+'/'+name);assert(r.ok);const b=Buffer.from(await r.arrayBuffer());assert.equal(hash(b),hash(fs.readFileSync(path.join(source,name))));
  if(name.startsWith('data/'))assert.match(r.headers.get('cache-control'),/31536000.*immutable/);
  return {file:name,status:r.status,bytes:b.length,sha256:hash(b),cache:r.headers.get('cache-control')};
 }));
 const pointer=await(await fetch(base+'/routing-model/latest.json')).json();assert.equal(pointer.model_id,'261110005327');assert.equal(pointer.source_simulation,'capacity_v7');
 const r=await fetch(base+pointer.payload_path),payload=Buffer.from(await r.arrayBuffer());assert.equal(hash(payload),pointer.sha256);assert.equal(pointer.sha256,'6e5a1e6fbf879b0e7552f57745b47f2f38fc8d3f0834de9c101cb4050c729031');
 const result={status:'PASS',deployment:'dpl_Ggh4Rph1EM3KUEqzT6wHRy5RgvNK',model_id:pointer.model_id,model_unchanged:true,payload_sha256:hash(payload),checks};
 fs.writeFileSync(path.join(__dirname,'public-integrity.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,model_id:result.model_id,verified_assets:checks.length,model_unchanged:true}));
})().catch(e=>{console.error(e);process.exit(1)});
