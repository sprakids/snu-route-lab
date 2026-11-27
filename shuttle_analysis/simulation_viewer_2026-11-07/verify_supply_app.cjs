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
  // Average wait over clock phases does not identify a single actual vehicle.
  for(const bus of buses){assert.equal(bus.automatic_queue.capacity_assumption,44);assert.equal(bus.automatic_queue.capacity_basis,'selected_vehicle_original_terminal_dispatch');}
  assert.equal(q.latest_simulation.peak_pair_operation.vehicles_per_peak_dispatch,2);
  const reported=Date.now()/1000,opportunity=reported+120;
  const manual=await get('/api/plan',{...body,mode:'live',departure_at:reported,
    queue_context:{route_id:'shuttle-41841',station_id:'snu-410',reported_at:reported,queue_ahead:66,next_seats:44,
      opportunity_departure_at:opportunity,opportunity_vehicle_id:null,opportunity_terminal_dispatch_at:opportunity}});
  fs.writeFileSync(path.join(work,'app-public-manual-scenario.json'),JSON.stringify(manual));
  const projected=manual.candidates.flatMap(c=>c.legs).filter(l=>l.route_id==='shuttle-41841'&&l.queue_projection);
  assert(projected.length>0,'fresh manual scenario applied');
  const selected=projected[0];assert.equal(selected.queue_projection.capacity_assumption,44);
  assert.equal(selected.queue_projection.skipped_departures,1);assert.equal(selected.vehicle_supply.capacity,44);
  assert.equal(selected.vehicle_supply.batch_vehicles,2);assert(Math.abs(selected.departure_at-opportunity)<2);
  const result={status:'PASS',anonymous:true,public_app:base,model_id:q.model_id,payload_sha256:q.sync.payload_sha256,
    compatibility_sha256:q.sync.compatibility_sha256,sync_error:q.sync.last_error,candidates:plan.candidates.length,
    administration_shuttle_candidates:buses.length,average_capacity_assumption:44,
    manual_scenario_only_not_a_field_report:{queue_ahead:66,next_seats:44,passed_first_vehicle:1,boards_second_at_same_clock:true},
    selected_supply:JSON.parse(JSON.stringify(selected.vehicle_supply)),
    real_route_calculation_uses_corrected_supply:true,new_behavior_algorithm_included:false};
  fs.writeFileSync(path.join(work,'app-public-new-verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exitCode=1});
