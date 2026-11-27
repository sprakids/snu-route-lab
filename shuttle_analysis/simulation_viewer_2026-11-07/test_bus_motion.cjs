const assert=require('node:assert/strict');
(async()=>{
  const {motionAt}=await import('./public/bus-motion.js');
  const p={t:[0,10,20,35],d:[0,50,100,100],v:[0,10,0,0],cap:[40,40,0]};
  assert.deepEqual(motionAt(p,-1),{distance:0,speed:0,limit:40});
  assert.equal(motionAt(p,5).distance,12.5);assert.equal(motionAt(p,5).speed,5);
  assert.equal(motionAt(p,15).distance,87.5);assert.equal(motionAt(p,15).speed,5);
  assert.equal(motionAt(p,25).distance,100);assert.equal(motionAt(p,25).speed,0);
  assert.equal(motionAt(p,40).distance,100);assert.equal(motionAt(p,40).speed,0);
  console.log('PASS: acceleration, braking, dwell, and endpoint motion cases');
})().catch(e=>{console.error(e);process.exit(1);});
