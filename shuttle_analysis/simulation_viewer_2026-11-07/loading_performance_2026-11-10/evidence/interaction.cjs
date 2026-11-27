const {chromium}=require('C:/Users/김예준/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const root='C:/Users/김예준/Documents/ChatGPT/공대 문제해결/shuttle_analysis/simulation_viewer_2026-11-07/public',base='http://127.0.0.1:8799/';
const read=n=>JSON.parse(fs.readFileSync(path.join(root,n),'utf8')),common=read('data/capacity_v7/common.json');
const fmt=n=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(n);
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),requests=[],errors=[];
 page.on('request',r=>{if(r.url().includes('/data/'))requests.push(r.url().split('/data/')[1]);});page.on('pageerror',e=>errors.push(String(e)));
 const ready=()=>page.waitForFunction(()=>!document.querySelector('#play-button').disabled&&document.querySelector('#loading-overlay').hidden,null,{timeout:120000});
 try{
  await page.route('**/capacity_v7/common.json',async route=>{await new Promise(r=>setTimeout(r,1200));await route.continue();});
  await page.goto(base+'?day=mon&second=61380',{waitUntil:'domcontentloaded'});
  await page.selectOption('#weekday','tue');await page.selectOption('#weekday','wed');await ready();
  assert.equal(await page.locator('#weekday').inputValue(),'wed');
  const data=read('data/capacity_v7/peak-wed.json'),node=common.hot_nodes.admin_snu,q=data.queue_timeline[node].findLast(r=>r[0]<=61380)?.[1]||0;
  assert.equal(await page.locator('#stop-queue').innerText(),fmt(q));
  assert.equal(requests.filter(r=>r==='half_hour_v1/capacity_v7.json').length,1);
  assert.equal(requests.filter(r=>r==='chart_reference_v1/legacy.json').length,1);
  assert(!requests.some(r=>r.endsWith('/charts.json')));
  for(const policy of ['fixed','adaptive','city']){
   await page.selectOption('#policy',policy);await ready();await page.click('#charts-tab');
   await page.waitForFunction(()=>document.querySelectorAll('#current-heatmap .heat-cell').length===70);
   await page.waitForSelector('#queue-line svg');await page.click('#map-tab');
  }
  await page.click('[data-focus="admin"]');const marker=page.locator('.stop-map-marker[title*="행정관"]').first();await marker.click();
  await page.waitForSelector('.stop-queue-popup [data-total-queue]');assert((await page.locator('.stop-queue-popup').innerText()).includes('대기'));
  assert.equal(errors.length,0,JSON.stringify(errors));
  const result={status:'PASS',rapid_selection_before_common_ready:true,latest_selection_queue_parity:true,metadata_request_deduplication:true,large_charts_requests:0,policies_tested:['fixed','adaptive','city'],stop_click_popup:true,errors};
  fs.writeFileSync(path.join(__dirname,'interaction.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
