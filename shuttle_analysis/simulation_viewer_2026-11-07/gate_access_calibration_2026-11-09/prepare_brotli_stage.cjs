// Transport compression only. Decoded JSON bytes must match the source exactly.
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib'),crypto=require('node:crypto'),util=require('node:util');
const compress=util.promisify(z.brotliCompress),root=path.resolve(__dirname,'..');
const input=path.join(root,'deployment/static_site'),manifest=JSON.parse(fs.readFileSync(path.join(root,'public/routing-model/latest.json')));
const target=process.argv[2]?path.resolve(process.argv[2]):path.join(root,'deployment/gate_access_release_'+manifest.model_id),source=path.join(input,'public');
if(!target.startsWith(path.join(root,'deployment')+path.sep))throw new Error('stage must stay within deployment workspace');
const hash=buf=>crypto.createHash('sha256').update(buf).digest('hex');
function files(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(dir,e.name)):[path.join(dir,e.name)])}
(async()=>{
  assertNewOrEmpty();fs.mkdirSync(path.join(target,'public'),{recursive:true});
  fs.mkdirSync(path.join(target,'.vercel'),{recursive:true});fs.copyFileSync(path.join(input,'.vercel/project.json'),path.join(target,'.vercel/project.json'));
  const queue=files(source),results=[];let done=0;
  async function worker(){
    for(;;){const file=queue.shift();if(!file)return;const rel=path.relative(source,file);let raw=fs.readFileSync(file),dest=rel,decoded=null;
      if(rel.startsWith('data'+path.sep)&&rel.endsWith('.json.gz')){
        decoded=z.gunzipSync(raw);raw=await compress(decoded,{params:{[z.constants.BROTLI_PARAM_QUALITY]:10,[z.constants.BROTLI_PARAM_MODE]:z.constants.BROTLI_MODE_TEXT}});
        if(!z.brotliDecompressSync(raw).equals(decoded))throw new Error('roundtrip '+rel);
        dest=rel.slice(0,-3)+'.br';
      }
      const output=path.join(target,'public',dest);fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,raw);
      results.push({path:dest.split(path.sep).join('/'),bytes:raw.length,sha256:hash(raw),decoded_sha256:decoded?hash(decoded):null});
      done++;if(done%15===0)console.log('STAGED',done);
    }
  }
  await Promise.all([worker(),worker(),worker()]);
  const config=JSON.parse(fs.readFileSync(path.join(input,'vercel.json')));
  config.headers=config.headers.map(h=>h.source==='/data/:dataset/:file.json'?{...h,headers:h.headers.map(v=>v.key==='Content-Encoding'?{key:v.key,value:'br'}:v)}:h);
  config.rewrites=config.rewrites.map(r=>r.destination==='/data/:dataset/:file.json.gz'?{...r,destination:'/data/:dataset/:file.json.br'}:r);
  fs.writeFileSync(path.join(target,'vercel.json'),JSON.stringify(config,null,2));fs.writeFileSync(path.join(target,'.vercelignore'),'.vercel\n.env*\n.git\n');
  const total=results.reduce((s,r)=>s+r.bytes,0);if(total>=100000000)throw new Error('source limit '+total);
  const report={status:'PASS',stage:target,source_model:manifest.model_id,transport_encoding:'br',quality:10,files:results.length,upload_bytes:total,lossless_decoded_json_verified:true,manifest:results};
  fs.writeFileSync(path.join(__dirname,'brotli_stage_verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,manifest:undefined}));
})().catch(e=>{console.error(e);process.exit(1)});
function assertNewOrEmpty(){if(fs.existsSync(target)&&files(target).some(p=>!p.includes(path.sep+'.vercel'+path.sep)))throw new Error('stage already contains evidence: '+target)}
