const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const work=path.join(__dirname,'peak_pair_correction_2026-11-10'),base='https://snu-route-lab.vercel.app';
async function get(endpoint,body){const r=await fetch(base+endpoint,{signal:AbortSignal.timeout(90000),...(body?{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}:{})});assert.equal(r.status,200,endpoint);return r.json()}
(async()=>{
  const q=await get('/api/queue-model');fs.writeFileSync(path.join(work,'app-public-new-queue-model.json'),JSON.stringify(q));
  assert.equal(q.model_id,'261110162302');assert.equal(q.sync.payload_sha256,'f39be2fbe61185f198ac27da9b8b57565cccfb80824e0a4f8f65f68915cbd130');
  assert.equal(q.sync.compatibility_sha256,'d55ae84edbee58b42c8d2d641fa50075e157a197fa159e93e10caab9aa1d0c2d');assert.equal(q.sync.last_error,null);
  const now=Date.now()/1000,body={origin_id:'snu-410',destination_id:'snu-station',preset:'fast',mode:'plan',departure_at:now+60};
  const plan=await get('/api/plan',body);fs.writeFileSync(path.join(work,'app-public-new-plan.json'),JSON.stringify(plan));
  assert(plan.candidates.length>0);const buses=plan.candidates.flatMap(c=>c.legs).filter(l=>l.type==='bus'&&l.route_id==='shuttle-41841');assert(buses.length>0);
  const supplies=buses.map(l=>l.vehicle_supply).filter(Boolean);assert(supplies.length>0);
  for(const supply of supplies){assert.equal(supply.capacity,44);assert.equal(supply.batch_vehicles,2);assert.equal(supply.basis,'active_model_original_terminal_dispatch');}
  const result={status:'PASS',anonymous:true,public_app:base,model_id:q.model_id,payload_sha256:q.sync.payload_sha256,
    compatibility_sha256:q.sync.compatibility_sha256,sync_error:q.sync.last_error,candidates:plan.candidates.length,
    administration_shuttle_candidates:buses.length,selected_supply:JSON.parse(JSON.stringify(supplies[0])),
    real_route_calculation_uses_corrected_supply:true,new_behavior_algorithm_included:false};
  fs.writeFileSync(path.join(work,'app-public-new-verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exitCode=1});
