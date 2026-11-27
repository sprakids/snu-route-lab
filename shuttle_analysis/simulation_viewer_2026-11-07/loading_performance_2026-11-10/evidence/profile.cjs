const {chromium}=require('C:/Users/김예준/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
const base=process.argv[2]||'https://snu-shuttle-simulation.vercel.app/',label=process.argv[3]||'baseline';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}), page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 await page.addInitScript(()=>{
   window.__perf={json:[],long:[]};
   new PerformanceObserver(list=>window.__perf.long.push(...list.getEntries().map(e=>({start:e.startTime,duration:e.duration})))).observe({type:'longtask',buffered:true});
   const native=Response.prototype.json;
   Response.prototype.json=async function(){const start=performance.now();const value=await native.call(this);window.__perf.json.push({url:this.url,start,end:performance.now()});return value;};
 });
 if(process.env.THROTTLE){const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:1.6*1024*1024/8,uploadThroughput:750*1024/8});await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});}
 const runs=[];
 try{
 for(let i=0;i<3;i++){
   await page.goto(new URL('?day=mon&second=61380',base).toString(),{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>!document.getElementById('play-button').disabled&&document.getElementById('loading-overlay').hidden,null,{timeout:180000});
   const result=await page.evaluate(()=>({ready:performance.now(),marks:performance.getEntriesByType('mark').map(e=>({name:e.name,start:e.startTime})),
    resources:performance.getEntriesByType('resource').map(e=>({name:e.name.split('/').slice(-3).join('/'),start:e.startTime,ttfb:e.responseStart-e.requestStart,end:e.responseEnd,duration:e.duration,transfer:e.transferSize,encoded:e.encodedBodySize,decoded:e.decodedBodySize})),
    ...window.__perf,clock:document.querySelector('#clock').textContent,queue:document.querySelector('#stop-queue').textContent}));
   runs.push({run:i+1,cache:i?'warm':'cold',...result});
   console.log(JSON.stringify({label,run:i+1,ready_ms:Math.round(result.ready),json:result.json.map(j=>({name:j.url.split('/').pop(),start:Math.round(j.start),end:Math.round(j.end)})),data:result.resources.filter(r=>r.name.includes('.json')).map(r=>({name:r.name,start:Math.round(r.start),end:Math.round(r.end),transfer:r.transfer,decoded:r.decoded})),long:result.long}));
   if(i===0)await page.screenshot({path:path.join(__dirname,label+'-map.png')});
 }
 fs.writeFileSync(path.join(__dirname,label+'.json'),JSON.stringify({base,label,runs,errors},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
