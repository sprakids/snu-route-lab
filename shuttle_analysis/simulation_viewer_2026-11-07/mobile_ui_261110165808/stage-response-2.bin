// Responsive presentation only. Existing controls and their event handlers move
// into the mobile sheet and return to their original anchors above 700px.
export function installMobileLab({map,getState,setPane}){
  // Archived entry pages share the viewer module but keep their own layout.
  if(!document.querySelector('link[data-mobile-lab]'))return;
  const $=id=>document.getElementById(id),media=matchMedia('(max-width:700px), (max-width:1000px) and (max-height:500px) and (pointer:coarse)');
  const sidebar=document.querySelector('.sidebar'),mapPane=$('map-pane'),charts=$('charts-pane');
  let active=false,opened=false,section='settings',moves=[],header,body,tabs,sections,timeButton,observer,queryIcon,queryLabel;
  let pointer=null,skipClick=false;
  const originalLabel=sidebar.getAttribute('aria-label');
  const resizeMap=()=>requestAnimationFrame(()=>map.invalidateSize({pan:false}));
  function move(node,target){
    if(!node)return;
    const anchor=document.createComment('mobile lab original position');node.before(anchor);
    moves.push({node,anchor});target.append(node);
  }
  function summary(){
    if(!active)return;
    const option=$('stop-select').selectedOptions[0],state=getState();
    const label=state.ready?(option?.textContent||'승차지 선택'):'재생자료 준비 중';
    if($('lab-sheet-stop').textContent!==label)$('lab-sheet-stop').textContent=label;
    if($('lab-sheet-stop').title!==label)$('lab-sheet-stop').title=label;
    const q=$('stop-queue').textContent;
    const status=state.ready?`모형 대기량 ${q}`:'설정과 상세';
    if($('lab-sheet-status').textContent!==status)$('lab-sheet-status').textContent=status;
    if($('time-slider').getAttribute('aria-valuetext')!==$('clock').textContent)$('time-slider').setAttribute('aria-valuetext',$('clock').textContent);
  }
  function selectSection(name){
    const changed=section!==name;section=name;
    for(const button of tabs.querySelectorAll('button')){
      const selected=button.dataset.labSection===name;
      button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;
    }
    for(const [key,panel] of Object.entries(sections))panel.hidden=key!==name;
    if(changed)body.scrollTop=0;
  }
  function expand(value){
    if(!active)return;
    opened=value;document.body.dataset.labSheet=value?'open':'closed';
    $('lab-sheet-toggle').setAttribute('aria-expanded',String(value));
    $('lab-sheet-toggle').setAttribute('aria-label',value?'실험 설정과 상세 접기':'실험 설정과 상세 펼치기');
    body.inert=!value;
    if(!value&&body.contains(document.activeElement))$('lab-sheet-toggle').focus({preventScroll:true});
    resizeMap();
  }
  function choose(name){
    if(name==='charts'){
      if(getState().pane!=='charts')setPane('charts');
      else{selectSection(name);expand(true);}
    }else{
      if(getState().pane!=='map')setPane('map');
      selectSection(name);expand(true);
    }
  }
  function collapse(){
    if(getState().pane!=='map')setPane('map');
    expand(false);
  }
  function paneChanged(event){
    if(!active)return;
    // Graphs are in the sheet on phones; the map remains behind it.
    mapPane.hidden=false;
    if(event.detail.pane==='charts'){selectSection('charts');expand(true);}
    else{if(section==='charts')selectSection('stops');expand(false);}
  }
  function mount(){
    if(active)return;active=true;moves=[];
    document.body.dataset.labMobile='true';sidebar.setAttribute('aria-label','실험 설정과 승차지 상세');
    const children=[...sidebar.children];
    header=document.createElement('div');header.className='lab-sheet-header';
    header.innerHTML='<button type="button" id="lab-sheet-toggle" aria-expanded="false" aria-controls="lab-sheet-body"><span class="lab-sheet-heading">실험 설정 · 상세<span id="lab-sheet-status"></span></span><strong id="lab-sheet-stop">승차지 선택</strong><svg class="lab-sheet-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 14 6-6 6 6"/></svg></button>';
    body=document.createElement('div');body.id='lab-sheet-body';body.className='lab-sheet-body';
    tabs=document.createElement('div');tabs.className='lab-sheet-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','실험실 상세');
    sections={};
    for(const [key,label] of [['settings','실험 설정'],['stops','승차지'],['charts','그래프']]){
      const button=document.createElement('button');button.type='button';button.id='lab-tab-'+key;button.dataset.labSection=key;
      button.textContent=label;button.setAttribute('role','tab');button.setAttribute('aria-controls','lab-panel-'+key);
      button.addEventListener('click',()=>choose(key));tabs.append(button);
      const panel=document.createElement('section');panel.id='lab-panel-'+key;panel.className='lab-sheet-section';panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',button.id);sections[key]=panel;
    }
    body.append(tabs,...Object.values(sections));sidebar.append(header,body);
    const timeFields=document.createElement('div');timeFields.className='lab-time-fields';sections.settings.append(timeFields);
    move(document.querySelector('.time-input-label'),timeFields);move(document.querySelector('.speed-label'),timeFields);
    const notes=document.createElement('details');notes.className='lab-model-notes';notes.innerHTML='<summary>모형·표시 안내</summary>';
    for(const child of children){
      if(child.classList.contains('control-grid')||child.classList.contains('view-switch'))move(child,sections.settings);
      else if(child.classList.contains('stop-card'))move(child,sections.stops);
      else move(child,notes);
    }
    move(document.querySelector('.stop-map-hint'),sections.stops);
    const query=$('snapshot-open');queryLabel=query.getAttribute('aria-label');
    query.classList.add('lab-snapshot-button');query.setAttribute('aria-label','요일과 시간으로 대기 상황 조회');
    queryIcon=document.createElement('span');queryIcon.setAttribute('aria-hidden','true');
    queryIcon.innerHTML='<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m16 16 5 5M11 7v4l3 2"/></svg>';
    query.append(queryIcon);move(query,header);
    move(charts,sections.charts);
    move(document.querySelector('.map-status'),notes);move(document.querySelector('.bus-key'),notes);
    sections.settings.append(notes);
    const links=document.createElement('div');links.className='lab-sheet-links';
    move(document.querySelector('.header .methodology-link'),links);move($('about-button'),links);sections.settings.append(links);
    timeButton=document.createElement('button');timeButton.type='button';timeButton.className='lab-time-settings';
    timeButton.setAttribute('aria-label','재생 시각과 속도 설정');timeButton.setAttribute('aria-controls','lab-sheet-body');
    timeButton.addEventListener('click',()=>{choose('settings');$('time-input').focus({preventScroll:true});});
    document.querySelector('.playback-heading').append(timeButton);
    $('lab-sheet-toggle').addEventListener('click',()=>{if(skipClick){skipClick=false;return;}opened?collapse():expand(true);});
    $('lab-sheet-toggle').addEventListener('pointerdown',event=>{pointer={id:event.pointerId,y:event.clientY};event.currentTarget.setPointerCapture(event.pointerId);});
    $('lab-sheet-toggle').addEventListener('pointerup',event=>{
      if(!pointer||event.pointerId!==pointer.id)return;
      const delta=event.clientY-pointer.y;pointer=null;
      if(Math.abs(delta)>32){skipClick=true;delta<0?expand(true):collapse();}
    });
    $('lab-sheet-toggle').addEventListener('pointercancel',()=>{pointer=null;});
    tabs.addEventListener('keydown',event=>{
      const buttons=[...tabs.querySelectorAll('button')],index=buttons.indexOf(event.target);
      if(index<0||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;
      buttons[next].focus();choose(buttons[next].dataset.labSection);
    });
    observer=new MutationObserver(summary);
    for(const id of ['stop-queue','clock'])observer.observe($(id),{childList:true,characterData:true,subtree:true});
    observer.observe($('snapshot-open'),{attributes:true,attributeFilter:['disabled']});
    selectSection(getState().pane==='charts'?'charts':'settings');mapPane.hidden=false;
    expand(getState().pane==='charts');summary();resizeMap();
  }
  function restore(){
    if(!active)return;
    active=false;observer?.disconnect();body.inert=false;
    queryIcon.remove();$('snapshot-open').classList.remove('lab-snapshot-button');
    if(queryLabel===null)$('snapshot-open').removeAttribute('aria-label');else $('snapshot-open').setAttribute('aria-label',queryLabel);
    for(const {node,anchor} of moves.reverse()){anchor.before(node);anchor.remove();}
    header.remove();body.remove();timeButton.remove();moves=[];
    sidebar.setAttribute('aria-label',originalLabel);delete document.body.dataset.labMobile;delete document.body.dataset.labSheet;
    mapPane.hidden=getState().pane!=='map';charts.hidden=getState().pane!=='charts';resizeMap();
  }
  media.addEventListener('change',()=>media.matches?mount():restore());
  document.addEventListener('lab:panechange',paneChanged);
  document.addEventListener('keydown',event=>{
    if(active&&opened&&event.key==='Escape'&&!document.querySelector('dialog[open]')){event.preventDefault();collapse();}
  });
  if(media.matches)mount();
}
