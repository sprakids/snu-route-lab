// Lossless transport compression; the scientific JSON is never rewritten.
const fs=require('node:fs'),path=require('node:path'),z=require('node:zlib'),crypto=require('node:crypto'),util=require('node:util');
const root=path.resolve(__dirname,'..'),publicRoot=path.join(root,'public');
const original=path.join(root,'deployment/realtime_autoplay_261109175408');
const release=JSON.parse(fs.readFileSync(path.join(publicRoot,'routing-model/latest.json')));
if(release.source_simulation!=='capacity_v8')throw Error('Expected verified v8 queue release');
const stage=path.join(root,'deployment/weekday_operations_release_'+release.model_id);
if(fs.existsSync(stage))throw Error('Preserve existing staging evidence; choose a fresh stage after inspection');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const files=d=>fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(d,e.name)):[path.join(d,e.name)]);
const compress=util.promisify(z.brotliCompress);
(async()=>{
  fs.mkdirSync(stage,{recursive:true});fs.cpSync(path.join(original,'public'),path.join(stage,'public'),{recursive:true});
  fs.mkdirSync(path.join(stage,'.vercel'));fs.copyFileSync(path.join(original,'.vercel/project.json'),path.join(stage,'.vercel/project.json'));
  const identity=JSON.parse(fs.readFileSync(path.join(stage,'.vercel/project.json')));
  if(identity.projectId!=='prj_EZEIl5YWei929wYAdurHkdWOwndM'||identity.orgId!=='team_BKZDs09pK9fVgNkBOC2oU7RL')throw Error('Wrong deployment project');
  for(const old of files(path.join(stage,'public'))){
    const rel=path.relative(path.join(stage,'public'),old);
    if(rel.startsWith('data'+path.sep)||rel.startsWith('routing-model'+path.sep))continue;
    const source=path.join(publicRoot,rel);if(fs.existsSync(source)&&fs.statSync(source).isFile())fs.copyFileSync(source,old);
  }
  for(const name of ['weekday-operations-methodology.html','weekday-operations-methodology.md','weekday-operations-summary.json'])
    fs.copyFileSync(path.join(publicRoot,name),path.join(stage,'public',name));
  fs.cpSync(path.join(publicRoot,'routing-model'),path.join(stage,'public/routing-model'),{recursive:true});
  const inputs=files(path.join(publicRoot,'data/capacity_v8')).filter(p=>p.endsWith('.json.gz'));
  inputs.push(path.join(publicRoot,'data/half_hour_v1/capacity_v8.json.gz'));
  const compressed=[];
  async function worker(){
    for(;;){const source=inputs.shift();if(!source)return;
      const originalBytes=z.gunzipSync(fs.readFileSync(source));
      const expected=source.slice(0,-3);if(!originalBytes.equals(fs.readFileSync(expected)))throw Error('Gzip mismatch');
      if(/C:[\\/]|(?:api|service)[_-]?key=|BEGIN [A-Z ]*PRIVATE KEY/i.test(originalBytes.toString()))throw Error('Unexpected private material');
      const encoded=await compress(originalBytes,{params:{[z.constants.BROTLI_PARAM_QUALITY]:10,[z.constants.BROTLI_PARAM_MODE]:z.constants.BROTLI_MODE_TEXT}});
      if(!z.brotliDecompressSync(encoded).equals(originalBytes))throw Error('Brotli roundtrip mismatch');
      const rel=path.relative(publicRoot,expected)+'.br',target=path.join(stage,'public',rel);
      fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,encoded);
      compressed.push({path:rel.split(path.sep).join('/'),bytes:encoded.length,decoded_sha256:hash(originalBytes)});
      console.log('COMPRESSED',rel,encoded.length);
    }
  }
  await Promise.all([worker(),worker(),worker()]);
  fs.copyFileSync(path.join(original,'vercel.json'),path.join(stage,'vercel.json'));
  fs.writeFileSync(path.join(stage,'.vercelignore'),'.vercel\n.env*\n.git\n');
  const manifest=files(path.join(stage,'public')).map(p=>({path:path.relative(path.join(stage,'public'),p).split(path.sep).join('/'),bytes:fs.statSync(p).size,sha256:hash(fs.readFileSync(p))}));
  const bytes=manifest.reduce((s,r)=>s+r.bytes,0);if(bytes>=100000000)throw Error('Source upload size '+bytes);
  const receipt={status:'PASS',stage,model_id:release.model_id,source_simulation:'capacity_v8',project:identity,
    files:manifest.length,upload_bytes:bytes,lossless_decoded_json_verified:true,compressed,manifest};
  fs.writeFileSync(path.join(__dirname,'stage_verification.json'),JSON.stringify(receipt,null,2));
  console.log(JSON.stringify({...receipt,manifest:undefined,compressed:undefined}));
})().catch(e=>{console.error(e);process.exit(1)});
