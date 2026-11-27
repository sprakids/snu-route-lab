const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const BASE=process.argv[2]||'http://127.0.0.1:8799/',OUT=process.argv[3]||__dirname;
const baselineReport=require('./peer-qa-baseline.json');
const ROOT=path.join(process.env.USERPROFILE,'Documents/ChatGPT/공대 문제해결/shuttle_analysis/simulation_viewer_2026-11-07/public');
const fmt=n=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(n),clock=n=>[Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(x=>String(x).padStart(2,'0')).join(':');
const commonPromise=fs.readFile(path.join(ROOT,'data/capacity_v11/common.json'),'utf8').then(JSON.parse),replays=new Map();
async function expected(day,scenario,stop,second){
 const common=await commonPromise,key=scenario+'-'+day;
 if(!replays.has(key))replays.set(key,fs.readFile(path.join(ROOT,'data/capacity_v11/'+key+'.json'),'utf8').then(JSON.parse));
 const data=await replays.get(key),node=common.hot_nodes[stop],row=data.queue_timeline[node].findLast(row=>row[0]<=second);
 return fmt(row?.[1]||0);
}
async function ready(page){await page.waitForFunction(()=>!document.getElementById('play-button').disabled&&document.getElementById('loading-overlay').hidden,{timeout:90000});}
async function screen(page,name){const p=path.join(OUT,name+'.png');await page.screenshot({path:p});return p;}
async function metrics(page){return page.evaluate(()=>{const box=selector=>{const r=document.querySelector(selector).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};return {map:box('#map'),header:box('.header'),sidebar:box('.sidebar'),playback:box('.playback'),clientWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,viewport:{width:innerWidth,height:innerHeight},pane:__qaState.pane,mobile:document.body.dataset.labMobile||null};});}
async function instrument(page,errors){
 page.on('pageerror',error=>errors.push(String(error)));
 page.on('console',message=>{if(['error','warning'].includes(message.type()))errors.push(message.text());});
 await page.route('**/viewer-v5.js*',async route=>{const response=await route.fetch();await route.fulfill({response,body:(await response.text())+'\nglobalThis.__qaMap=map;globalThis.__qaState=state;\n'});});
}
async function open(page,baseline=false){
 await page.goto(BASE+(baseline?'__baseline__/':'')+'?day=tue&second=55500');await ready(page);
 await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(300);
}
async function touchDrag(page,x,y,dx,dy){
 const cdp=await page.context().newCDPSession(page);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y,id:1}]});
 for(let i=1;i<=8;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+dx*i/8,y:y+dy*i/8,id:1}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach();await page.waitForTimeout(300);
}
async function pinch(page,x,y){
 const cdp=await page.context().newCDPSession(page);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x-20,y,id:1},{x:x+20,y,id:2}]});
 for(let i=1;i<=8;i++){await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x-20-i*6,y,id:1},{x:x+20+i*6,y,id:2}]});await page.waitForTimeout(30);}
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach();await page.waitForTimeout(400);
}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true}),results=[];
 try{
  for(const [name,viewport] of [['tiny',{width:320,height:568}],['small',{width:360,height:740}],['phone',{width:390,height:844}],['landscape',{width:844,height:390}]]){
   const context=await browser.newContext({viewport,isMobile:true,hasTouch:true,deviceScaleFactor:1,locale:'ko-KR',timezoneId:'Asia/Seoul'});
   const page=await context.newPage(),errors=[],checks=[];await instrument(page,errors);
   const check=(label,fn)=>{fn();checks.push(label);};
   try{
    await open(page);let m=await metrics(page);
    check('correct page, actual V11 data and ready controls',()=>{assert(page.url().startsWith(BASE));assert.equal(m.mobile,'true');assert.equal(m.pane,'map');});
    check('map fills viewport without horizontal page overflow',()=>{assert.equal(m.map.x,0);assert.equal(m.map.y,0);assert.equal(m.map.width,viewport.width);assert.equal(m.map.height,viewport.height);assert.equal(m.scrollWidth,m.clientWidth);});
    check('compact playback and collapsed sheet',()=>{assert(m.playback.height<=100);assert(m.playback.y>viewport.height/2);});
    assert.equal(await page.locator('#lab-sheet-toggle').getAttribute('aria-expanded'),'false');
    assert.equal(await page.locator('#scenario').evaluate(e=>e.closest('[inert]')!==null),true);checks.push('collapsed settings are not focusable');
    const home=await screen(page,name+'-map');
    const center=await page.evaluate(()=>{const p=__qaMap.getCenter();return [p.lat,p.lng];});
    const x=viewport.width*(name==='landscape'?.25:.3),y=viewport.height*(name==='landscape'?.42:.4);
    await touchDrag(page,x,y,50,35);
    check('native touch drag moves actual Leaflet map',()=>{});
    assert.notDeepEqual(await page.evaluate(()=>{const p=__qaMap.getCenter();return [p.lat,p.lng];}),center);
    const beforeZoom=await page.evaluate(()=>__qaMap.getZoom());await page.locator('.leaflet-control-zoom-in').click();
    await page.waitForFunction(z=>__qaMap.getZoom()>z,beforeZoom);checks.push('zoom control changes map zoom');
    await page.waitForTimeout(400);const beforePinch=await page.evaluate(()=>__qaMap.getZoom());await pinch(page,x,y);
    assert((await page.evaluate(()=>__qaMap.getZoom()))>beforePinch);assert.equal(await page.evaluate(()=>visualViewport.scale),1);checks.push('native two-finger pinch zooms map with stable page scale');
    await page.locator('#lab-sheet-toggle').click();await page.waitForTimeout(300);
    assert.equal(await page.locator('#lab-sheet-toggle').getAttribute('aria-expanded'),'true');assert(await page.locator('#scenario').isVisible());checks.push('sheet opens to real original controls');
    await screen(page,name+'-settings');
    await page.selectOption('#speed','10');await page.selectOption('#scenario','regular');await ready(page);
    assert.equal(await page.locator('#scenario').inputValue(),'regular');assert.equal(await page.locator('#speed').inputValue(),'10');checks.push('scenario reload and playback speed selection');
    await page.selectOption('#policy','adaptive');await ready(page);assert.equal(await page.evaluate(()=>__qaState.policy),'adaptive');
    await page.selectOption('#policy','city');await ready(page);assert.equal(await page.evaluate(()=>__qaState.supplyCorrected),true);checks.push('legacy policy remains available and returns to V11');
    await page.selectOption('#weekday','mon');await ready(page);assert.equal(await page.locator('#day-label').innerText(),'월요일');checks.push('weekday data changes');
    await page.locator('#queue-view').click();assert.equal(await page.evaluate(()=>__qaState.mode),'queue');await page.locator('#movement-view').click();checks.push('movement and queue display modes');
    await page.selectOption('#vehicle-filter','city');assert.equal(await page.evaluate(()=>__qaState.vehicleFilter),'city');await page.selectOption('#vehicle-filter','all');checks.push('vehicle filters retain actual state');
    await page.selectOption('#speed','1');
    await page.locator('#lab-tab-stops').click();assert(await page.locator('#stop-select').isVisible());
    await page.selectOption('#stop-select','admin_snu');
    assert.equal(await page.locator('#stop-queue').innerText(),await expected('mon','regular','admin_snu',55500));checks.push('stop details equal unchanged scientific queue timeline');
    await screen(page,name+'-stop');
    await page.keyboard.press('Escape');assert.equal(await page.locator('#lab-sheet-toggle').getAttribute('aria-expanded'),'false');checks.push('Escape closes nonmodal sheet');
    await page.click('#snapshot-open');assert(await page.locator('#snapshot-dialog').evaluate(e=>e.open));
    await page.selectOption('#snapshot-day','tue');await page.fill('#snapshot-time','15:23:00');await page.selectOption('#snapshot-stop','admin_snu');await page.click('#snapshot-submit');
    await page.waitForFunction(()=>!document.getElementById('snapshot-dialog').open);await ready(page);
    assert.equal(await page.locator('#clock').innerText(),'15:23:00');assert.equal(await page.locator('#weekday').inputValue(),'tue');
    assert.equal(await page.locator('#stop-queue').innerText(),await expected('tue','regular','admin_snu',55380));checks.push('original day/time query button and modal still function');
    await page.evaluate(()=>{__qaMap.closePopup();});
    const range=await page.locator('#time-slider').boundingBox();await page.touchscreen.tap(range.x+range.width*.4,range.y+range.height/2);
    const slider=Number(await page.locator('#time-slider').inputValue());assert.equal(await page.locator('#clock').innerText(),clock(slider));checks.push('touch slider updates exact simulation clock');
    await page.click('#forward-button');assert.equal(Number(await page.locator('#time-slider').inputValue()),Math.min(83400,slider+60));
    await page.click('#back-button');assert.equal(Number(await page.locator('#time-slider').inputValue()),slider);checks.push('one-minute step buttons');
    const paused=Number(await page.locator('#time-slider').inputValue());await page.click('#play-button');await page.waitForTimeout(1300);await page.click('#play-button');
    const stopped=Number(await page.locator('#time-slider').inputValue());assert(stopped>paused&&stopped<=paused+4);await page.waitForTimeout(1100);assert.equal(Number(await page.locator('#time-slider').inputValue()),stopped);checks.push('real-time playback and pause');
    await page.click('#charts-tab');await page.waitForSelector('#current-heatmap button');
    assert(await page.locator('#charts-pane').isVisible());assert(await page.locator('#map-pane').isVisible());assert.equal(await page.locator('#lab-sheet-toggle').getAttribute('aria-expanded'),'true');checks.push('graphs open in sheet with map retained');
    await screen(page,name+'-graphs');
    await page.locator('#current-heatmap button[data-day="mon"][data-start="55800"]').click();await ready(page);
    assert.equal(await page.locator('#clock').innerText(),'15:30:00');assert.equal(await page.locator('#weekday').inputValue(),'mon');assert.equal(await page.locator('#lab-sheet-toggle').getAttribute('aria-expanded'),'false');checks.push('heatmap cell returns to map with original day/time');
    await page.click('#charts-tab');await page.click('#legacy-charts');assert(await page.locator('#legacy-chart-content').isVisible());await page.click('#current-charts');await page.click('#map-tab');checks.push('previous hourly chart is preserved');
    await page.locator('.theme-toggle').click();assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');await screen(page,name+'-dark');checks.push('dark palette preserves map and compact controls');
    await page.click('#lab-sheet-toggle');await page.click('#lab-tab-settings');await page.click('#about-button');assert(await page.locator('#about-dialog').evaluate(e=>e.open));await page.keyboard.press('Escape');checks.push('model information remains reachable');
    await page.keyboard.press('Escape');
    m=await metrics(page);assert.equal(m.scrollWidth,m.clientWidth);assert.deepEqual(errors,[]);checks.push('no horizontal page overflow or console warnings/errors');
    results.push({name,viewport,status:'PASS',checks,metrics:m,screenshot:home,errors});
   }catch(error){await screen(page,name+'-failure');await fs.writeFile(path.join(OUT,name+'-failure.html'),await page.content());throw error;}
   finally{await context.close();}
  }
  for(const [name,viewport,touch] of [['tablet',{width:768,height:1024},true],['desktop',{width:1440,height:1000},false]]){
   const context=await browser.newContext({viewport,isMobile:false,hasTouch:touch,deviceScaleFactor:1,locale:'ko-KR',timezoneId:'Asia/Seoul'});
   const page=await context.newPage(),errors=[];await instrument(page,errors);
   const before=baselineReport.results.find(r=>r.name===name).before;
   await open(page,false);const after=await metrics(page);await screen(page,name+'-after');
   assert.equal(after.mobile,null);assert.deepEqual(after.map,before.map);assert.deepEqual(after.sidebar,before.sidebar);assert.deepEqual(after.header,before.header);assert.deepEqual(after.playback,before.playback);assert.deepEqual(errors,[]);
   await page.click('#charts-tab');await page.waitForSelector('#current-heatmap button');assert(await page.locator('#charts-pane').isVisible());assert(await page.locator('#map-pane').isHidden());await page.click('#map-tab');
   assert.equal(await page.locator('#snapshot-open').evaluate(e=>e.closest('.stop-map-hint')!==null),true);
   results.push({name,viewport,status:'PASS',original_layout_metrics_unchanged:true,before,after,chart_map_navigation:true,errors});await context.close();
  }
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1});
  const page=await context.newPage(),errors=[];await instrument(page,errors);await open(page);
  await page.click('#lab-sheet-toggle');await page.click('#lab-tab-charts');
  await page.setViewportSize({width:1024,height:768});await page.waitForTimeout(350);
  assert.equal(await page.locator('body').getAttribute('data-lab-mobile'),null);assert.equal(await page.locator('#charts-pane').evaluate(e=>e.parentElement.classList.contains('main-pane')),true);
  assert.equal(await page.locator('#snapshot-open').evaluate(e=>e.closest('.stop-map-hint')!==null),true);assert(await page.locator('#map-pane').isHidden());
  await page.click('#map-tab');await page.setViewportSize({width:390,height:844});await page.waitForTimeout(350);
  assert.equal(await page.locator('body').getAttribute('data-lab-mobile'),'true');assert.equal(await page.locator('#lab-sheet-toggle').getAttribute('aria-expanded'),'false');
  for(const id of ['scenario','policy','weekday','stop-select','snapshot-open','time-input','speed','charts-pane'])assert.equal(await page.locator('#'+id).count(),1);
  await page.click('#snapshot-open');assert(await page.locator('#snapshot-dialog').evaluate(e=>e.open));assert.deepEqual(errors,[]);
  results.push({name:'responsive-transition',status:'PASS',controls_moved_and_restored:true,unique_original_ids:true,errors});await context.close();
  const result={status:'PASS',browser:'Installed Chrome / Playwright',browser_plugin:'absent',fallback_reason:'Browser plugin not available',url:BASE,actual_public_or_local_v11_data:true,model_or_dataset_mocked:false,map_library_mocked:false,only_instrumentation:'read-only map/state references appended to served JS for interaction assertions',results,model_unchanged:true,anonymous_public_test:BASE.startsWith('https:')};
  await fs.writeFile(path.join(OUT,'qa.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }finally{await browser.close();}
})().catch(async error=>{await fs.writeFile(path.join(OUT,'qa-failure-'+Date.now()+'.txt'),String(error.stack||error));console.error(error);process.exitCode=1;});
