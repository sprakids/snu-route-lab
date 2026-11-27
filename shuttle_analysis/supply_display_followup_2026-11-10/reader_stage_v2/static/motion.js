/* Presentation only: no provider requests, route changes, or stored trip data. */
(() => {
  'use strict';
  const root=document.documentElement;
  const media=window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const reduced=()=>root.dataset.reduceMotion==='true'||Boolean(media?.matches);
  const controls='button,a[href],summary,[role="button"],.settings-themes label,.shuttle-option,.settings-check';
  const active=new Map();
  let pointer=null;
  function eligible(node){
    const el=node?.closest?.(controls);
    return el&&(!el.closest('#map')||el.closest('.leaflet-control-zoom'))&&!el.closest('.liquid-ripple')&&!el.disabled&&el.getAttribute('aria-disabled')!=='true'?el:null;
  }
  function scan(node){
    if(node.nodeType!==1||node.closest('.liquid-ripple')||node.closest('#map')&&!node.closest('.leaflet-control-zoom'))return;
    if(node.matches(controls))node.classList.add('liquid-control');
    node.querySelectorAll(controls).forEach(el=>{if(!el.closest('#map')||el.closest('.leaflet-control-zoom'))el.classList.add('liquid-control');});
  }
  function clearRipple(el){
    const old=active.get(el);if(!old)return;
    clearTimeout(old.timer);old.layer.remove();active.delete(el);
  }
  function drop(el,x,y){
    if(reduced()||!el.isConnected)return;
    clearRipple(el);
    // Limit composited decoration even during very rapid tapping.
    while(active.size>=4)clearRipple(active.keys().next().value);
    const bounds=el.getBoundingClientRect();
    if(!bounds.width||!bounds.height)return;
    const layer=document.createElement('span');layer.className='liquid-ripple';layer.setAttribute('aria-hidden','true');
    layer.style.setProperty('--drop-x',Math.max(0,Math.min(bounds.width,x-bounds.left))+'px');
    layer.style.setProperty('--drop-y',Math.max(0,Math.min(bounds.height,y-bounds.top))+'px');
    layer.style.setProperty('--drop-size',Math.min(620,Math.max(100,Math.hypot(bounds.width,bounds.height)*1.35))+'px');
    el.append(layer);
    layer.addEventListener('animationend',()=>clearRipple(el),{once:true});
    active.set(el,{layer,timer:setTimeout(()=>clearRipple(el),800)});
  }
  const running=new Map();
  function enter(el,keyframes,duration=320){
    if(!el||!el.isConnected||reduced()||!el.animate||getComputedStyle(el).display==='none')return;
    running.get(el)?.cancel();
    const animation=el.animate(keyframes,{duration,easing:'cubic-bezier(.2,.75,.25,1)',fill:'none'});
    running.set(el,animation);
    animation.finished.then(()=>{if(running.get(el)===animation)running.delete(el);},()=>{if(running.get(el)===animation)running.delete(el);});
  }
  function view(from,to){
    if(from===to||reduced())return;
    const narrow=window.innerWidth<=700;
    const targets=to==='home'?['.mobile-home-search','.mobile-home-bottom']:to==='results'?['.sidebar']:['#selected-panel','#mobile-detail-back'];
    for(const selector of targets){
      const el=document.querySelector(selector),sheet=narrow&&selector==='#selected-panel';
      enter(el,[{opacity:0,transform:sheet?'translateY(28px)':narrow?'translateY(12px)':'translateX(-16px)'},{opacity:1,transform:'translate(0,0)'}],sheet?380:300);
    }
    // Fade the resized canvas without animating Leaflet's position transforms.
    enter(document.querySelector('.map-area'),[{opacity:.78},{opacity:1}],280);
  }
  function list(id='results'){enter(document.getElementById(id),[{opacity:.35,transform:'translateY(7px)'},{opacity:1,transform:'translateY(0)'}],220);}
  function route(){enter(document.querySelector('.map-area'),[{opacity:.72},{opacity:1}],280);}
  function stop(){
    for(const el of [...active.keys()])clearRipple(el);
    for(const animation of running.values())animation.cancel();running.clear();
  }
  window.RouteMotion=Object.freeze({view,list,route,reduced});
  function boot(){
    if(!document.body.classList.contains('campus-route'))return;
    scan(document.body);
    new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)scan(node);}).observe(document.body,{childList:true,subtree:true});
    document.addEventListener('pointerdown',event=>{
      if(event.button!=null&&event.button!==0)return;
      const el=eligible(event.target);if(!el)return;
      pointer={el,id:event.pointerId,x:event.clientX,y:event.clientY,time:performance.now()};drop(el,event.clientX,event.clientY);
    },{capture:true,passive:true});
    document.addEventListener('pointermove',event=>{if(pointer?.id===event.pointerId&&Math.hypot(event.clientX-pointer.x,event.clientY-pointer.y)>12)clearRipple(pointer.el);},{passive:true});
    document.addEventListener('pointercancel',()=>{if(pointer)clearRipple(pointer.el);pointer=null;},{passive:true});
    document.addEventListener('click',event=>{
      if(event.detail!==0)return;
      const el=eligible(event.target);if(!el||pointer?.el===el&&performance.now()-pointer.time<600)return;
      const r=el.getBoundingClientRect();drop(el,r.left+r.width/2,r.top+r.height/2);
    },{capture:true,passive:true});
    const inMap=target=>Boolean(target?.closest?.('#map'));
    // Native page zoom is separate from the map SDK's own gesture handlers.
    document.addEventListener('wheel',event=>{if(event.ctrlKey||event.metaKey)event.preventDefault();},{passive:false});
    document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&!event.altKey&&['+','=','-','_','Add','Subtract','ZoomIn','ZoomOut'].includes(event.key))event.preventDefault();},{capture:true});
    function touchGuard(event){if(event.touches.length>1&&!Array.from(event.touches).every(t=>inMap(t.target)))event.preventDefault();}
    document.addEventListener('touchstart',touchGuard,{passive:false});
    document.addEventListener('touchmove',touchGuard,{passive:false});
    for(const type of ['gesturestart','gesturechange'])document.addEventListener(type,event=>event.preventDefault(),{passive:false});
    document.addEventListener('dblclick',event=>{if(!inMap(event.target)&&!event.target.closest?.('input,textarea,[contenteditable=true]'))event.preventDefault();});
    new MutationObserver(()=>{if(reduced())stop();}).observe(root,{attributes:true,attributeFilter:['data-reduce-motion']});
    media?.addEventListener?.('change',()=>{if(reduced())stop();});
    requestAnimationFrame(()=>root.classList.add('motion-ready'));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
