const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('C:/Users/김예준/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.join(__dirname,'peak_pair_correction_2026-11-10');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.addInitScript(()=>{
   window.labBusTexts=[];const clear=CanvasRenderingContext2D.prototype.clearRect,fill=CanvasRenderingContext2D.prototype.fillText;
   CanvasRenderingContext2D.prototype.clearRect=function(...args){if(this.canvas.classList.contains('people-canvas'))window.labBusTexts=[];return clear.apply(this,args)};
   CanvasRenderingContext2D.prototype.fillText=function(text,x,y,...rest){if(this.canvas.classList.contains('people-canvas')&&String(text).endsWith('/44'))window.labBusTexts.push({text,x,y});return fill.call(this,text,x,y,...rest)};
  });
  await page.goto('https://snu-shuttle-simulation.vercel.app/?day=tue&scenario=regular&second=55441');
  await page.waitForFunction(()=>!document.getElementById('play-button').disabled&&document.getElementById('loading-overlay').hidden,{timeout:120000});
  await page.selectOption('#vehicle-filter','shuttle');await page.locator('[data-focus=admin]').click();
  await page.waitForFunction(()=>window.labBusTexts.length>=2,{timeout:30000});await page.waitForTimeout(500);
  const texts=await page.evaluate(()=>window.labBusTexts);assert(texts.some((a,i)=>texts.slice(i+1).some(b=>Math.abs(a.x-b.x)<.1&&Math.abs(Math.abs(a.y-b.y)-46)<.1)),JSON.stringify(texts));
  assert.equal(errors.length,0);await page.screenshot({path:path.join(root,'two44-vehicles-public.png')});
  const result={status:'PASS',anonymous:true,two_separate44_vehicle_labels:true,coincident_icons_separated_pixels:46,time:'Tue15:24:01',texts,runtime_errors:errors};
  fs.writeFileSync(path.join(root,'pair-render-verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
