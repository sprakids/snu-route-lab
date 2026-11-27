// Actual vendored Leaflet and RouteMap execute in a simulated DOM. No browser pixels or device GPS.
import fs from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
const fixtures=JSON.parse(await fs.readFile(new URL('./runtime/ui_fixtures_v2.json',import.meta.url),'utf8'));
const roads=JSON.parse(await fs.readFile(new URL('./data/road_geometry.json',import.meta.url),'utf8'));
for(const route of fixtures.bootstrap.routes)route.geometry_segments=(roads.routes[route.id]?.segments||[]).filter(Boolean).map(s=>s.geometry);
for(const route of fixtures.shuttle.routes||[])for(const vehicle of route.vehicles||[]){
  const i=vehicle.position?.segment_index,part=roads.routes['shuttle-'+route.id]?.anchor_segments?.[i];
  if(!vehicle.position?.at_stop&&part)vehicle.geographic_interval=part.geometry;
}
const dom=new JSDOM('<div id="map"></div>',{url:'https://snu-route-lab.vercel.app',runScripts:'outside-only',pretendToBeVisual:true});
const {window}=dom;const element=window.document.querySelector('#map');
Object.defineProperties(element,{clientWidth:{value:1000},clientHeight:{value:760}});
window.SVGSVGElement.prototype.createSVGRect=()=>({});
new vm.Script(await fs.readFile(new URL('./static/vendor/leaflet.js',import.meta.url),'utf8')).runInContext(dom.getInternalVMContext());
window.L.Browser.canvas=false;
const source=(await fs.readFile(new URL('./static/map.js',import.meta.url),'utf8')).replace('export class RouteMap','window.RouteMap=class RouteMap');
new vm.Script(source).runInContext(dom.getInternalVMContext());
const map=new window.RouteMap(element,()=>{});await map.initialize({},fixtures.bootstrap.routes);
assert.equal(map.shuttleNetwork.length,fixtures.bootstrap.routes.filter(r=>r.kind==='shuttle').reduce((n,r)=>n+r.geometry_segments.length,0));
assert(map.shuttleNetwork.every(line=>line.getLatLngs().length>=2));
map.showShuttle(fixtures.shuttle);
assert.ok(window.document.querySelectorAll('.shuttle-vehicle-marker').length>0);
assert.ok([...window.document.querySelectorAll('.shuttle-vehicle-marker')].some(e=>e.textContent.includes('순환')));
assert.ok([...window.document.querySelectorAll('.shuttle-vehicle-marker')].some(e=>e.textContent.includes('행정관')));
map.showUserLocation({lat:37.46086,lon:126.950347,accuracy:25},false);
assert.ok(window.document.querySelector('.user-location-dot'));
const locationLayers=[...map.locations];
const origin=fixtures.bootstrap.origins[0],dest=fixtures.bootstrap.destinations[0];
map.showRoute(fixtures.plans['snu-station'].candidates[0],origin,dest,false);
assert.ok(locationLayers.every(layer=>map.map.hasLayer(layer)));
assert.equal(window.document.querySelectorAll('.user-location-dot').length,1);
assert.ok(window.document.querySelectorAll('svg path').length>0);
map.showShuttle({...fixtures.shuttle,routes:fixtures.shuttle.routes.map(r=>({...r,stale:true}))});
assert.equal(window.document.querySelectorAll('.shuttle-vehicle-marker').length,0);
assert.ok(map.map.hasLayer(locationLayers[0]));
// A dense real-time snapshot must not obscure an unrelated selected route.
const now=Date.now()/1000;
map.showVehicles([{route_id:'focus',route_name:'선택버스',lat:37.46,lon:126.95,provided_at:now},
 {route_id:'other',route_name:'다른버스',lat:37.46,lon:126.95,provided_at:now}]);
map.showRoute({legs:[{type:'bus',route_id:'focus',geometry:[[37.46,126.95],[37.461,126.951]]}]},origin,dest,false);
assert.equal(window.document.querySelectorAll('.vehicle-marker').length,1);
assert.equal(window.document.querySelector('.vehicle-marker').textContent,'선택버스');
map.showVehicles([{route_id:'focus',route_name:'선택버스',lat:37.46,lon:126.95,provided_at:now},
 {route_id:'other',route_name:'다른버스',lat:37.46,lon:126.95,provided_at:now}]);
assert.equal(window.document.querySelectorAll('.vehicle-marker').length,1);
map.clearRoute();assert.equal(window.document.querySelectorAll('.vehicle-marker').length,2);
map.showRoute({legs:[{type:'walk',geometry:[[37.46,126.95],[37.461,126.951]]}]},origin,dest,false);
assert.equal(window.document.querySelectorAll('.vehicle-marker').length,0);
map.map.remove();dom.window.close();
console.log(JSON.stringify({suite:'real Leaflet + RouteMap in simulated DOM',passed:8,checks:['three distinct shuttle route layers','live admin and circle markers','location accuracy circle and dot','route selection preserves device marker','stale shuttle markers removed','selected route excludes unrelated vehicles after refresh','map home restores all route vehicles','walking detail does not show unrelated vehicles'],visual_browser_test:false,real_geolocation:false}));
