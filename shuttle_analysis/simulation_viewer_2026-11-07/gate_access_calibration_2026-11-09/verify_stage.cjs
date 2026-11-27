const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib'),crypto=require('node:crypto'),cp=require('node:child_process'),util=require('node:util');
const execFile=util.promisify(cp.execFile),root=path.resolve(__dirname,'..');
const host=process.argv[2]||'https://snu-shuttle-simulation-i0grflldr-june-f3d1.vercel.app';
const cli='C:/Users/김예준/AppData/Local/npm-cache/_npx/29d463b7a51d914c/node_modules/vercel/dist/vc.js';
const cwd=path.join(root,'deployment/gate_access_release_261109173153'),out=path.join(__dirname,'qa',process.argv[3]||'stage-http');fs.mkdirSync(out,{recursive:true});
const paths=process.argv[4]==='ui-only'?['routing-model/latest.json','viewer-v5.js','initial-clock.js']:['routing-model/latest.json','routing-model/releases/261109173153.json','viewer-v5.js','initial-clock.js','gate-access-summary.json','gate-access-methodology.html','data/capacity_v7/peak-mon.json','data/half_hour_v1/capacity_v7.json','data/capacity_v5/peak-mon.json','data/capacity_v6/common.json'];
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{
 const queue=[...paths],results=[];
 async function worker(){for(;;){const rel=queue.shift();if(!rel)return;const dest=path.join(out,rel.replaceAll('/','__'));
  const r=await execFile(process.execPath,[cli,'curl',host+'/'+rel,'--output',dest,'--write-out','%{http_code}|%header{content-encoding}'],{cwd,windowsHide:true,maxBuffer:100000});
  if(!r.stdout.trim().startsWith('200|'))throw new Error(rel+' HTTP '+r.stdout);
  const raw=fs.readFileSync(dest),isData=rel.startsWith('data/'),decoded=isData?z.brotliDecompressSync(raw):raw;
  if(isData&&!r.stdout.includes('|br'))throw new Error('encoding '+rel);
  if(sha(decoded)!==sha(fs.readFileSync(path.join(root,'public',rel))))throw new Error('payload differs '+rel);
  results.push({path:rel,http_status:200,encoding:isData?'br':'identity',decoded_sha256:sha(decoded),source_matches:true});
 }}
 await Promise.all([worker(),worker(),worker()]);
 fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({status:'PASS',host,authenticated:true,protection_settings_changed:false,checks:results},null,2));
 console.log(JSON.stringify({status:'PASS',host,files:results.length,decoded_sources_match:true}));
})().catch(e=>{console.error(e);process.exit(1)});
