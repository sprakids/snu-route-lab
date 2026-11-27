const {chromium}=require('C:/Users/김예준/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:8792/',label=process.argv[3]||'local';
const output=path.join(__dirname,label);fs.mkdirSync(output,{recursive:true});
const sec=s=>s.split(':').map(Number).reduce((a,v)=>a*60+v,0);
async function fakeClock(page,iso){
 await page.addInitScript(iso=>{const RealDate=Date,epoch=RealDate.parse(iso),start=performance.now();globalThis.Date=class extends RealDate{
  constructor(...args){super(...(args.length?args:[epoch+performance.now()-start]))}
  static now(){return epoch+performance.now()-start}
 }},iso);
}
async function ready(page){await page.waitForFunction(()=>!document.getElementById('play-button').disabled&&document.getElementById('loading-overlay').hidden,{timeout:90000})}
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true}),results=[];
 try{
  for(const [device,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
   const page=await browser.newPage({viewport}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await fakeClock(page,'2026-11-11T08:15:42Z');
   await page.route('**/data/capacity_v7/peak-wed.json',async route=>{await new Promise(r=>setTimeout(r,1800));await route.continue()});
   await page.goto(base);await ready(page);await page.waitForFunction(()=>document.getElementById('play-button').getAttribute('aria-label')==='일시정지');
   assert.equal(await page.locator('#speed').inputValue(),'1');assert.equal(await page.locator('#weekday').inputValue(),'wed');
   const wall=await page.evaluate(()=>{const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(x=>[x.type,x.value]));return Number(p.hour)*3600+Number(p.minute)*60+Number(p.second)});
   const first=sec(await page.locator('#clock').innerText());assert(Math.abs(first-wall)<=1,'refresh current clock after delayed load');
   await page.waitForTimeout(2200);const advanced=sec(await page.locator('#clock').innerText())-first;assert(advanced>=1&&advanced<=3,'one simulated second per real second');
   await page.screenshot({path:path.join(output,device+'-autoplay.png')});
   await page.click('#play-button');const paused=await page.locator('#clock').innerText();await page.waitForTimeout(1200);assert.equal(await page.locator('#clock').innerText(),paused);
   await page.click('#play-button');await page.waitForTimeout(1400);assert(sec(await page.locator('#clock').innerText())>sec(paused));
   await page.fill('#time-input','17:03:00');await page.locator('#time-input').dispatchEvent('change');await page.waitForTimeout(1200);
   assert.equal(await page.locator('#clock').innerText(),'17:03:00');assert.equal(await page.locator('#play-button').getAttribute('aria-label'),'재생');
   await page.click('#charts-tab');await page.waitForSelector('#current-heatmap button');assert(await page.locator('#charts-pane').isVisible());
   await page.click('#map-tab');assert.equal(await page.locator('#play-button').getAttribute('aria-label'),'재생');
   const url=new URL(base);url.searchParams.set('day','mon');url.searchParams.set('second','61380');await page.goto(url.toString());await ready(page);await page.waitForTimeout(1300);
   assert.equal(await page.locator('#clock').innerText(),'17:03:00');assert.equal(await page.locator('#weekday').inputValue(),'mon');assert.equal(await page.locator('#play-button').getAttribute('aria-label'),'재생');
   assert.equal(errors.length,0,JSON.stringify(errors));assert(await page.locator('#error-panel').isHidden());
   results.push({device,status:'PASS',speed:1,auto_started:true,startup_load_delay_ms:1800,clock_lag_seconds:Math.abs(first-wall),advanced_in_2200ms:advanced,pause_resume_and_manual_time:true,explicit_link_paused:true,charts_retained:true,runtime_errors:errors});await page.close();
  }
  for(const [name,iso,day,time] of [['after-hours','2026-11-11T14:20:00Z','wed','23:10:00'],['weekend','2026-11-14T08:00:00Z','fri',null]]){
   const page=await browser.newPage({viewport:{width:1280,height:900}});await fakeClock(page,iso);await page.goto(base);await ready(page);await page.waitForTimeout(1000);
   assert.equal(await page.locator('#play-button').getAttribute('aria-label'),'재생');assert.equal(await page.locator('#weekday').inputValue(),day);
   if(time)assert.equal(await page.locator('#clock').innerText(),time);assert(await page.locator('.initial-clock-note').isVisible());
   results.push({case:name,status:'PASS',fallback_is_paused_and_labelled:true});await page.close();
  }
  fs.writeFileSync(path.join(output,'verification.json'),JSON.stringify({status:'PASS',base,browser:'Edge/Playwright; Browser plugin not available',results},null,2));console.log(JSON.stringify({status:'PASS',base,cases:results.length,results}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
