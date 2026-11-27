import test from 'node:test';import assert from 'node:assert/strict';
import {cadence,shuttleSlot,nextShuttleAt,updateShuttleStats,parseShuttle} from './shuttle_stats.mjs';
import {dayStart} from './schedule.mjs';
const mid=dayStart('2026-11-16'),at=m=>mid+m*60000;
const spec={id:'41841',name:'fixture',direction_label:'forward',anchors:[{x:0,y:0,name:'A'},{x:100,y:0,name:'B'},{x:100,y:100,name:'C'}]};
function feed(t,stops){return {captured_at:t,vehicles:stops.map(([id,stop])=>({id,position:{at_stop:stop!==null,at_stop_index:stop,direction:'forward'}}))};}
test('cadence covers all ten routes within 6000 provider reservations',()=>{
  const ids=['41841','41946','41914','41843','41942','41842','41869','41868','41915','41916'];let n=0;
  for(const id of ids){const seen=new Set();for(let t=at(680);t<=at(1390);t+=15000){const s=shuttleSlot(id,t);if(s)seen.add(s.id);}n+=seen.size;}
  assert(n<5000);assert(n>4400);assert.equal(cadence('41841',at(900)),30);assert.equal(cadence('41843',at(900)),120);
  assert.equal(shuttleSlot('41841',at(679)),null);assert.equal(shuttleSlot('41841',at(1391)),null);
  assert.equal(nextShuttleAt(at(1390)),mid+86400000+680*60000);
});
test('parked first sample is left-censored; repeated parked observations are not arrivals',()=>{
  let p=updateShuttleStats(null,feed(100,[['one',0]]),spec);
  p=updateShuttleStats(p,feed(130,[['one',0]]),spec);
  assert.equal(p.events.length,0);assert.equal(Object.keys(p.rides).length,0);
  assert.deepEqual(updateShuttleStats(p,feed(130,[['one',1]]),spec),p);
});
test('complete travel excludes origin parking and retains interval uncertainty',()=>{
  let p=updateShuttleStats(null,feed(100,[['one',0]]),spec);
  p=updateShuttleStats(p,feed(160,[['one',0]]),spec);
  p=updateShuttleStats(p,feed(190,[['one',null]]),spec);
  p=updateShuttleStats(p,feed(250,[['one',1]]),spec);
  const row=Object.values(p.rides)[0].samples[0];assert.equal(row.lo,0);assert.equal(row.hi,90);assert.equal(row.seconds,45);
  assert.deepEqual(p.events.map(e=>e.kind),['departure','arrival']);
});
test('two vehicles in one detection batch do not become zero-second headways',()=>{
  let p=updateShuttleStats(null,feed(100,[['one',null],['two',null]]),spec);
  p=updateShuttleStats(p,feed(130,[['one',0],['two',0]]),spec);
  assert.equal(p.events.filter(e=>e.kind==='arrival').length,2);assert.equal(Object.keys(p.headways).length,0);
  p=updateShuttleStats(p,feed(160,[['one',null],['two',null]]),spec);
  p=updateShuttleStats(p,feed(190,[['one',1],['two',1]]),spec);
  assert.equal(Object.values(p.rides)[0].n,2);
});
test('a restart-sized observation gap cannot manufacture a trip',()=>{
  let p=updateShuttleStats(null,feed(100,[['one',0]]),spec);
  p=updateShuttleStats(p,feed(1000,[['one',1]]),spec);
  assert.equal(Object.keys(p.rides).length,0);assert.equal(p.events.length,0);
});
test('unresolved pair members in adjacent polls merge into one opportunity batch',()=>{
  let p=updateShuttleStats(null,feed(100,[['one',null],['two',null]]),spec);
  p=updateShuttleStats(p,feed(130,[['one',0],['two',null]]),spec);
  p=updateShuttleStats(p,feed(160,[['one',0],['two',0]]),spec);
  assert.equal(Object.keys(p.headways).length,0);assert.equal(p.last['arrival:0:forward'].count,2);
});
test('schematic parser deduplicates vehicles and preserves empty valid feeds',()=>{
  const p=parseShuttle({d:'one/0/0/a/b/c;one/0/0/a/b/c'},spec,100);
  assert.equal(p.vehicles.length,1);assert.equal(p.provider_timestamp,null);assert.equal(p.vehicles[0].position.at_stop,true);
  assert.equal(parseShuttle({d:''},spec,100).vehicles.length,0);assert.throws(()=>parseShuttle({d:'bad'},spec,100));
});
