/* Device preferences only. No locations, route histories or network requests. */
(() => {
  'use strict';
  const key='snu-route-preferences-v1';
  const fields=['time','crowd','walk','transfers'];
  let presets={fast:{time:75,crowd:5,walk:15,transfers:5},comfort:{time:25,crowd:45,walk:20,transfers:10},walk:{time:20,crowd:5,walk:70,transfers:5},transfer:{time:25,crowd:5,walk:10,transfers:60}};
  const clone=value=>JSON.parse(JSON.stringify(value));
  const validWeights=value=>value&&fields.every(f=>typeof value[f]==='number'&&Number.isFinite(value[f])&&value[f]>=0&&value[f]<=100)&&fields.reduce((sum,f)=>sum+value[f],0)>0;
  const base=()=>({preset:'fast',weights:{...presets.fast},includeShuttle:true,largeText:false,reduceMotion:Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)});
  function load(){
    const fallback=base();
    try{
      const raw=localStorage.getItem(key);if(!raw||raw.length>4096)return fallback;
      const stored=JSON.parse(raw);
      if(!stored||!validWeights(stored.weights))return fallback;
      return {preset:Object.hasOwn(presets,stored.preset)?stored.preset:'custom',weights:Object.fromEntries(fields.map(f=>[f,stored.weights[f]])),
        includeShuttle:typeof stored.includeShuttle==='boolean'?stored.includeShuttle:true,
        largeText:stored.largeText===true,reduceMotion:typeof stored.reduceMotion==='boolean'?stored.reduceMotion:fallback.reduceMotion};
    }catch{return fallback;}
  }
  let value=load(),draft=clone(value),dialog,opener,previousNav;
  const initialOpen=new URL(location.href).searchParams.get('settings')==='1';
  const $=id=>document.getElementById(id);
  function applyAccessibility(){
    document.documentElement.dataset.largeText=String(value.largeText);
    document.documentElement.dataset.reduceMotion=String(value.reduceMotion);
  }
  applyAccessibility();
  function message(text){if($('settings-status'))$('settings-status').textContent=text;}
  function persist(){try{localStorage.setItem(key,JSON.stringify(value));return true;}catch{message('이 기기에서 설정을 저장할 수 없어 이번 화면에만 적용합니다.');return false;}}
  function markPresets(){document.querySelectorAll('[data-default-preset]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.defaultPreset===draft.preset)));}
  function render(){
    if(!dialog)return;
    draft=clone(value);markPresets();
    const labels={time:'시간',crowd:'혼잡',walk:'도보',transfers:'환승'};
    $('settings-weight-controls').replaceChildren();
    for(const field of fields){
      const label=document.createElement('label');label.className='settings-weight';label.htmlFor='default-weight-'+field;
      const text=document.createElement('span');text.textContent=labels[field];
      const input=document.createElement('input');input.id=label.htmlFor;input.type='range';input.min='0';input.max='100';input.value=draft.weights[field];input.setAttribute('aria-label','기본 '+labels[field]+' 선호도');
      const output=document.createElement('output');output.htmlFor=input.id;output.value=String(draft.weights[field]);
      input.addEventListener('input',()=>{draft.weights[field]=Number(input.value);draft.preset='custom';output.value=input.value;markPresets();});
      label.append(text,input,output);$('settings-weight-controls').append(label);
    }
    $('settings-include-shuttle').checked=value.includeShuttle;
    $('settings-large-text').checked=value.largeText;$('settings-reduce-motion').checked=value.reduceMotion;
  }
  function open(event){
    if(!dialog||dialog.open)return;
    opener=event?.currentTarget||document.activeElement;render();message('');
    previousNav=document.querySelector('.mobile-nav [aria-current]');previousNav?.removeAttribute('aria-current');
    $('mobile-settings')?.setAttribute('aria-current','page');dialog.showModal();
  }
  function notify(){document.dispatchEvent(new CustomEvent('route-defaults-change',{detail:clone(value)}));}
  window.RouteSettings=Object.freeze({read:()=>clone(value),initialOpen,
    configure(serverPresets,version){
      if(serverPresets)for(const name of Object.keys(presets))if(validWeights(serverPresets[name]))presets[name]={...serverPresets[name]};
      if(Object.hasOwn(presets,value.preset))value.weights={...presets[value.preset]};
      if($('settings-version'))$('settings-version').textContent=version?'서울대 하교길 · v'+version:'서울대 하교길';
      if(dialog?.open)markPresets();
    }});
  function bind(){
    dialog=$('settings-dialog');if(!dialog)return;
    document.querySelectorAll('[data-open-settings]').forEach(button=>button.addEventListener('click',open));
    $('settings-close').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('close',()=>{$('mobile-settings')?.removeAttribute('aria-current');previousNav?.setAttribute('aria-current','page');if(opener?.isConnected)opener.focus({preventScroll:true});});
    dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();});
    document.querySelectorAll('[data-default-preset]').forEach(button=>button.addEventListener('click',()=>{
      draft.preset=button.dataset.defaultPreset;draft.weights={...presets[draft.preset]};markPresets();
      fields.forEach(field=>{const input=$('default-weight-'+field);input.value=draft.weights[field];input.nextElementSibling.value=String(draft.weights[field]);});
    }));
    $('settings-preferences-form').addEventListener('submit',event=>{
      event.preventDefault();if(!validWeights(draft.weights)){message('한 가지 이상의 선호도를 높여 주세요.');return;}
      value={...value,preset:draft.preset,weights:{...draft.weights},includeShuttle:$('settings-include-shuttle').checked};
      const saved=persist();notify();if(saved)message('기본 선호도를 저장했습니다. 다음 경로 검색부터 적용됩니다.');
    });
    for(const [id,field] of [['settings-large-text','largeText'],['settings-reduce-motion','reduceMotion']])$(id).addEventListener('change',event=>{
      value[field]=event.target.checked;applyAccessibility();if(persist())message('접근성 설정을 저장했습니다.');
    });
    $('settings-reset').addEventListener('click',()=>{
      let removed=true;try{localStorage.removeItem(key);}catch{removed=false;}
      value=base();applyAccessibility();if(window.RouteTheme?.set('system')===false)removed=false;render();notify();
      message(removed?'이 기기의 설정을 초기화했습니다.':'기기 저장소에 접근할 수 없어 이번 화면의 설정만 초기화했습니다.');
    });
    render();if(initialOpen)open();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind,{once:true});else bind();
})();
