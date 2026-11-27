const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const metres=(a,b)=>{const r=Math.PI/180,x=(b[1]-a[1])*r*Math.cos((a[0]+b[0])/2*r),y=(b[0]-a[0])*r;return Math.hypot(x,y)*6371000;};
const along=(path,m)=>{for(let i=1;i<path.length;i++){const d=metres(path[i-1],path[i]);if(m<=d){const t=d?Math.max(0,m/d):0;return path[i-1].map((x,k)=>x+(path[i][k]-x)*t);}m-=d;}return path.at(-1);};

export class RouteMap {
  constructor(element,onPick) { this.element=element;this.onPick=onPick;this.lines=[];this.pins=[];this.vehicles=[];this.shuttleIntervals=[];this.locations=[];this.shuttleNetwork=[];this.stops=[];this.stopsVisible=true;this.provider='osm'; }
  async initialize(config,routes) {
    if(config.javascript_key) {
      try {
        await new Promise((resolve,reject)=>{
          const script=document.createElement('script');
          const timeout=setTimeout(()=>reject(new Error('Map SDK timeout')),8000);
          script.src=`https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(config.javascript_key)}&autoload=false`;
          script.onload=()=>{if(!window.kakao?.maps){clearTimeout(timeout);reject(new Error('Map SDK unavailable'));}else window.kakao.maps.load(()=>{clearTimeout(timeout);resolve();});};
          script.onerror=()=>{clearTimeout(timeout);reject(new Error('Map SDK unavailable'));};document.head.append(script);
        });
        this.provider='kakao';
        this.map=new kakao.maps.Map(this.element,{center:new kakao.maps.LatLng(37.4609,126.9522),level:5});
        kakao.maps.event.addListener(this.map,'click',event=>this.onPick(event.latLng.getLat(),event.latLng.getLng()));
      } catch { this.provider='osm';this.element.replaceChildren(); }
    }
    if(this.provider==='osm') {
      this.map=L.map(this.element,{zoomControl:false,preferCanvas:true}).setView([37.4622,126.953],15);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'}).addTo(this.map);
      L.control.zoom({position:'bottomright'}).addTo(this.map);
      this.map.on('click',event=>this.onPick(event.latlng.lat,event.latlng.lng));
      this.stopLayer=L.layerGroup().addTo(this.map);this.vehicleLayer=L.layerGroup().addTo(this.map);
    }
    const unique=new Map();for(const route of routes)for(const stop of route.stops)if(stop.lat>=37.442&&stop.lat<=37.484&&stop.lon>=126.943&&stop.lon<=126.97)unique.set(stop.id,stop);
    for(const stop of unique.values()) {
      if(this.provider==='osm') {
        const marker=L.circleMarker([stop.lat,stop.lon],{radius:3.1,color:'#7d9b84',weight:1.2,fillColor:'#fff',fillOpacity:.95}).bindTooltip(esc(stop.name),{direction:'top'});
        marker.addTo(this.stopLayer);
      } else {
        const circle=new kakao.maps.Circle({center:new kakao.maps.LatLng(stop.lat,stop.lon),radius:5,strokeWeight:1,strokeColor:'#7d9b84',fillColor:'#fff',fillOpacity:1,map:this.map});this.stops.push(circle);
      }
    }
    for(const route of routes.filter(r=>r.kind==='shuttle')) {
      for(const coords of route.geometry_segments||[]) {
      if(this.provider==='osm')this.shuttleNetwork.push(L.polyline(coords,{color:route.color,weight:3,opacity:.25,dashArray:'6 7'}).bindTooltip(`${esc(route.name)} · 도로 경로`).addTo(this.map));
      else this.shuttleNetwork.push(new kakao.maps.Polyline({path:coords.map(p=>new kakao.maps.LatLng(...p)),strokeWeight:3,strokeColor:route.color,strokeOpacity:.25,strokeStyle:'dash',map:this.map}));
      }
    }
    return this.provider;
  }
  remove(items) { for(const item of items)if(this.provider==='osm')this.map.removeLayer(item);else item.setMap(null);items.length=0; }
  pin(point,type,label) {
    const html=`<div class="map-pin ${type}">${type==='destination'?'도착':'출발'}</div>`;
    if(this.provider==='osm') {
      const marker=L.marker([point.lat,point.lon],{icon:L.divIcon({html,className:'',iconSize:[31,31],iconAnchor:[15,15]}),zIndexOffset:2000}).bindTooltip(esc(label),{direction:'top',offset:[0,-14]}).addTo(this.map);this.pins.push(marker);
    } else {
      const overlay=new kakao.maps.CustomOverlay({position:new kakao.maps.LatLng(point.lat,point.lon),content:html,xAnchor:.5,yAnchor:.5,zIndex:20,map:this.map});this.pins.push(overlay);
    }
  }
  showRoute(candidate,origin,destination,fit=true) {
    this.remove(this.lines);this.remove(this.pins);this.selected=candidate;
    const all=[];
    for(const leg of candidate.legs) {
      if(!leg.geometry?.length)continue;
      const walk=leg.type==='walk',wide=window.innerWidth>700,color=walk?'#a18a5d':leg.route_color||(leg.route_name?.startsWith('관악')?'#2b8069':'#315f73');
      all.push(...leg.geometry);
      if(this.provider==='osm') {
        this.lines.push(L.polyline(leg.geometry,{color:'#fff',weight:walk?(wide?8:6):(wide?11:8),opacity:.9,lineCap:'round',interactive:false}).addTo(this.map));
        this.lines.push(L.polyline(leg.geometry,{color,weight:walk?(wide?4:3):(wide?7:4.5),opacity:.95,dashArray:walk?'3 7':undefined,lineCap:'round',interactive:false}).addTo(this.map));
      } else {
        this.lines.push(new kakao.maps.Polyline({path:leg.geometry.map(p=>new kakao.maps.LatLng(p[0],p[1])),strokeWeight:walk?(wide?4:3):(wide?7:5),strokeColor:color,strokeOpacity:.95,strokeStyle:walk?'dash':'solid',map:this.map}));
      }
    }
    this.pin(origin,'origin',origin.label||'선택한 출발지');this.pin(destination,'destination',destination.label);
    this.bounds=all.length?all:[[origin.lat,origin.lon],[destination.lat,destination.lon]];
    if(this.latestVehicles)this.showVehicles(this.latestVehicles);
    if(this.latestShuttle)this.showShuttle(this.latestShuttle);
    if(fit)this.fit();
  }
  showUserLocation(point,focus=false) {
    this.remove(this.locations);this.userLocation=point;
    const label=`현재 위치 · 기기 위치 오차 약 ${Math.round(point.accuracy)}m`;
    if(this.provider==='osm') {
      this.locations.push(L.circle([point.lat,point.lon],{radius:point.accuracy,color:'#3986dc',weight:1,fillColor:'#3986dc',fillOpacity:.10,interactive:false}).addTo(this.map));
      this.locations.push(L.marker([point.lat,point.lon],{icon:L.divIcon({html:'<span class="user-location-dot"></span>',className:'',iconSize:[18,18],iconAnchor:[9,9]}),zIndexOffset:2500}).bindTooltip(esc(label),{direction:'top'}).addTo(this.map));
      if(focus)this.map.setView([point.lat,point.lon],16);
    } else {
      const center=new kakao.maps.LatLng(point.lat,point.lon);
      this.locations.push(new kakao.maps.Circle({center,radius:point.accuracy,strokeWeight:1,strokeColor:'#3986dc',fillColor:'#3986dc',fillOpacity:.10,map:this.map}));
      this.locations.push(new kakao.maps.CustomOverlay({position:center,content:`<span class="user-location-dot" title="${esc(label)}"></span>`,xAnchor:.5,yAnchor:.5,zIndex:30,map:this.map}));
      if(focus){this.map.setCenter(center);this.map.setLevel(4);}
    }
  }
  resize(){if(!this.map)return;if(this.provider==='osm')this.map.invalidateSize?.({pan:false});else this.map.relayout();}
  clearRoute(){this.remove(this.lines);this.remove(this.pins);this.selected=null;this.bounds=null;if(this.latestVehicles)this.showVehicles(this.latestVehicles);if(this.latestShuttle)this.showShuttle(this.latestShuttle);}
  home(){const p=this.userLocation;if(this.provider==='osm')this.map.setView(p?[p.lat,p.lon]:[37.4622,126.953],p?16:15,{animate:false});else{this.map.setCenter(new kakao.maps.LatLng(p?.lat||37.4622,p?.lon||126.953));this.map.setLevel(p?4:5);}}
  fit() {
    if(!this.bounds?.length)return;
    if(this.provider==='osm') {
      const mobile=window.innerWidth<=700;
      const panel=mobile?document.getElementById('selected-panel')?.getBoundingClientRect().height:0;
      // On wide screens the map canvas starts beside the left panel, so it needs
      // only control padding rather than another sidebar-sized empty margin.
      this.map.fitBounds(this.bounds,{paddingTopLeft:[32,mobile?80:85],paddingBottomRight:[32,mobile?Math.min(window.innerHeight-170,(panel||window.innerHeight*.55)+16):70],maxZoom:16,animate:false});
    } else {
      const bounds=new kakao.maps.LatLngBounds();for(const point of this.bounds)bounds.extend(new kakao.maps.LatLng(point[0],point[1]));
      const mobile=window.innerWidth<=700,panel=mobile?document.getElementById('selected-panel')?.getBoundingClientRect().height:0;
      this.map.setBounds(bounds,90,40,mobile?Math.min(window.innerHeight-170,(panel||window.innerHeight*.55)+16):70,40);
    }
  }
  showVehicles(vehicles) {
    this.latestVehicles=vehicles;
    const focused=this.selected?new Set(this.selected.legs.filter(l=>l.type==='bus').map(l=>String(l.route_id))):null;
    clearInterval(this.motionTimer);this.motion=[];
    if(this.provider==='osm')this.vehicleLayer.clearLayers();else this.remove(this.vehicles);
    for(const v of vehicles) {
      if(focused&&!focused.has(String(v.route_id)))continue;
      if(v.lat<37.442||v.lat>37.484||v.lon<126.942||v.lon>126.97)continue;
      if(!v.provided_at||Date.now()/1000-v.provided_at>600)continue;
      const stale=v.position_source==='estimated'||Date.now()/1000-v.provided_at>90;
      const cls=stale?'stale':!['3','4','5','6'].includes(v.crowd_code)?'unknown':['4','5','6'].includes(v.crowd_code)?'busier':'';
      const html=`<div class="vehicle-marker ${cls}">${esc(v.route_name)}</div>`;
      if(this.provider==='osm') {
        const marker=L.marker([v.lat,v.lon],{icon:L.divIcon({html,className:'',iconSize:[40,21],iconAnchor:[20,10]}),zIndexOffset:500})
          .bindTooltip(`${esc(v.route_name)} · ${esc(v.crowd_label)}`,{direction:'top',offset:[0,-10]}).addTo(this.vehicleLayer);
        this.motion.push({marker,v,received:Date.now()});
      } else {
        this.vehicles.push(new kakao.maps.CustomOverlay({content:html,position:new kakao.maps.LatLng(v.lat,v.lon),map:this.map,zIndex:10,xAnchor:.5,yAnchor:.5}));
      }
    }
    this.motionTimer=setInterval(()=>{
      if(document.visibilityState==='hidden')return;
      for(const {marker,v,received} of this.motion){
        if(Date.now()/1000-v.provided_at>600){this.vehicleLayer.removeLayer(marker);continue;}
        if(v.motion_geometry?.length>1&&v.motion_speed_mps>0){const p=along(v.motion_geometry,Math.min(60,(Date.now()-received)/1000)*v.motion_speed_mps);if(p)marker.setLatLng(p);}
      }
    },1000);
  }
  toggleStops() {
    this.stopsVisible=!this.stopsVisible;
    if(this.provider==='osm')this.stopsVisible?this.stopLayer.addTo(this.map):this.map.removeLayer(this.stopLayer);
    else for(const stop of this.stops)stop.setMap(this.stopsVisible?this.map:null);
    return this.stopsVisible;
  }
  showShuttle(state) {
    this.latestShuttle=state;
    const focused=this.selected?new Set(this.selected.legs.filter(l=>l.type==='bus').map(l=>String(l.route_id))):null;
    this.remove(this.shuttleIntervals);
    for(const route of state.routes||[state]) {
      if(focused&&!focused.has('shuttle-'+route.id))continue;
      if(route.stale||route.error)continue;
      const groups=new Map();
      for(const v of route.vehicles) {
        if(!v.geographic_interval||!v.position)continue;
        const key=String(v.position.segment_index)+'-'+String(v.position.at_stop);
        if(!groups.has(key))groups.set(key,[]);groups.get(key).push(v);
      }
      for(const values of groups.values()) {
        const vehicle=values[0],coords=vehicle.geographic_interval,p=vehicle.position,color=route.color||'#bb7e2e';
        const area=p.at_stop?`${p.from_name} 부근`:`${p.from_name}→${p.to_name} 구간`;
        const label=`${route.name||'행정관 셔틀'} · ${area} · ${values.length}대`;
        const html=`<span class="shuttle-vehicle-marker" style="background:${esc(color)}">${esc(route.short_name||({'41946':'순환','41914':'역순환','41843':'대학동','41942':'대학동 야간'}[route.id])||'행정관')} ${values.length} · ${esc(p.at_stop?p.from_name+' 부근':'구간 위치')}</span>`;
        const center=along(coords,coords.slice(1).reduce((s,p,i)=>s+metres(coords[i],p),0)/2);
        if(this.provider==='osm') {
          if(!p.at_stop)this.shuttleIntervals.push(L.polyline(coords,{color,weight:9,opacity:.5,dashArray:'4 7'}).bindTooltip(esc(label)).addTo(this.map));
          this.shuttleIntervals.push(L.marker(center,{icon:L.divIcon({html,className:'',iconSize:[140,25],iconAnchor:[70,12]}),zIndexOffset:1200}).bindTooltip(esc(label),{direction:'top'}).addTo(this.map));
        } else {
          if(!p.at_stop)this.shuttleIntervals.push(new kakao.maps.Polyline({path:coords.map(p=>new kakao.maps.LatLng(...p)),strokeWeight:9,strokeColor:color,strokeOpacity:.5,strokeStyle:'dash',map:this.map}));
          this.shuttleIntervals.push(new kakao.maps.CustomOverlay({position:new kakao.maps.LatLng(...center),content:`<span title="${esc(label)}">${html}</span>`,xAnchor:.5,yAnchor:.5,zIndex:15,map:this.map}));
        }
      }
    }
  }
}
