const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('C:/Users/김예준/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base=process.argv[2],label=process.argv[3],out=path.join(__dirname,label);fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});const rows=[];try{
 for(const mobile of [true,false]){
  const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,hasTouch:mobile,timezoneId:'Asia/Seoul'});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(base+'?day=tue&second=55800');await page.waitForFunction(()=>!document.getElementById('play-button').disabled&&document.getElementById('loading-overlay').hidden,{timeout:120000});
  async function query(){await page.click('#snapshot-open');await page.selectOption('#snapshot-day','tue');await page.fill('#snapshot-time','15:30:00');await page.selectOption('#snapshot-stop','admin_snu');await page.click('#snapshot-submit');await page.waitForFunction(()=>!document.getElementById('snapshot-dialog').open);await page.waitForSelector('.leaflet-popup');}
  await query();const before={time:await page.locator('#clock').innerText(),stop:await page.locator('#stop-select').inputValue(),queue:await page.locator('#stop-queue').innerText()};
  await page.setViewportSize(mobile?{width:320,height:568}:{width:1340,height:960});await page.waitForTimeout(600);
  if(mobile)assert.equal(await page.locator('.leaflet-popup').count(),0,'old popup closes after phone resize');
  else assert.equal(await page.locator('.leaflet-popup').count(),1,'desktop popup behavior retained');
  assert.deepEqual({time:await page.locator('#clock').innerText(),stop:await page.locator('#stop-select').inputValue(),queue:await page.locator('#stop-queue').innerText()},before);
  if(mobile){
   await page.click('#lab-sheet-toggle');await page.click('#lab-tab-stops');assert(await page.locator('#stop-select').isVisible());assert.equal(await page.locator('#stop-queue').innerText(),before.queue);await page.keyboard.press('Escape');
   await query();await page.setViewportSize({width:844,height:390});await page.waitForTimeout(600);assert.equal(await page.locator('.leaflet-popup').count(),0);
   assert.equal(await page.locator('#clock').innerText(),before.time);assert.equal(await page.locator('#stop-select').inputValue(),before.stop);
  }
  assert.equal(errors.length,0);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(out,mobile?'phone-after-resize.png':'desktop-popup-preserved.png')});
  rows.push({mobile,status:'PASS',selection_clock_queue_preserved:true,old_popup_closed_only_in_mobile:mobile,errors});await context.close();
 }
 const result={status:'PASS',base,anonymous:base.startsWith('https:'),results:rows};fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
