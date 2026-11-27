"""Measure endpoint elevations along existing dorm routes using Terrarium z14 tiles."""
from functools import lru_cache
from pathlib import Path
import hashlib
import gzip
import json
import math
from PIL import Image

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent/'261124101820'
UPPER = {'300','301','302'}


@lru_cache(maxsize=8)
def tile(x,y):
    with Image.open(HERE/'terrain'/f'{x}-{y}.png') as image:
        return image.convert('RGB')


@lru_cache(maxsize=250000)
def elevation(lat,lon):
    n=2**14*256
    x=(lon+180.)/360*n-.5
    y=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n-.5
    ix,iy=math.floor(x),math.floor(y)
    total=0.
    for px,wx in [(ix,1-(x-ix)),(ix+1,x-ix)]:
        for py,wy in [(iy,1-(y-iy)),(iy+1,y-iy)]:
            r,g,b=tile(px//256,py//256).getpixel((px%256,py%256))
            total+=wx*wy*(256*r+g+b/256.-32768.)
    return total


def horizontal(a,b):
    phi, psi = map(math.radians,(a[0],b[0]))
    dlat = psi-phi
    dlon = math.radians(b[1]-a[1])
    h = math.sin(dlat/2)**2+math.cos(phi)*math.cos(psi)*math.sin(dlon/2)**2
    return 2*6371000.*math.asin(min(1.,math.sqrt(h)))


def slope_profile(path, step=25):
    planar = surface = rise = fall = 0.
    z = elevation(*path[0])
    for a,b in zip(path,path[1:]):
        length = horizontal(a,b)
        if length < 1e-6:
            continue
        pieces = math.ceil(length/step)
        for i in range(1,pieces+1):
            f=i/pieces
            next_z=elevation(a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1]))
            dz=next_z-z
            surface+=math.hypot(length/pieces,dz)
            planar+=length/pieces
            rise+=max(dz,0.)
            fall+=max(-dz,0.)
            z=next_z
    assert surface>=planar and math.isclose(fall-rise,elevation(*path[0])-elevation(*path[-1]),abs_tol=.001)
    return planar,surface,rise,fall


def main():
    def load(name):
        with gzip.open(REFERENCE/name,'rt',encoding='utf8') as stream:
            return json.load(stream)
    common=load('common.json.gz')
    catalog=load('dorm_paths.json.gz')
    rows=[]
    for building in common['buildings']:
        if building['id'] not in UPPER:
            continue
        origin=[building['lat'], building['lon']]
        for dest in ('dorm_ug','dorm_grad'):
            route=next((r for r in catalog['routes'] if r['origin']==origin and r['dorm']==dest),None)
            target=common['destinations'][dest]
            start_z,end_z=elevation(*origin),elevation(*target)
            row=dict(building=building['id'],name=building['name'],dorm=dest,origin=origin,target=target,
                     start_m=start_z,end_m=end_z,drop_m=start_z-end_z)
            if route:
                path=common['paths'][route['path']]
                assert path[0]==origin and path[-1]==target
                planar,surface,rise,fall=slope_profile(path)
                assert abs(planar-route['meters'])/route['meters']<.02,(row,planar,route)
                grade=(start_z-end_z)/planar
                row.update(path=route['path'],meters=route['meters'],seconds=route['seconds'],
                           planar_m=planar,surface_m=surface,ascent_m=rise,descent_m=fall,
                           net_downhill_grade=grade,choice_m=surface/(1+max(0.,grade)/.05),
                           time_multiplier=surface/planar,
                           revised_seconds=route['seconds']*surface/planar,
                           sensitivity_surface_m={s:slope_profile(path,s)[1] for s in [15,50]})
            rows.append(row)
    files=sorted((HERE/'terrain').glob('*.png'))
    hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    (HERE/'terrain.json').write_text(json.dumps(dict(rows=rows,zoom=14,source='Mapzen Terrain Tiles',
        url='https://s3.amazonaws.com/elevation-tiles-prod/terrarium/14/{x}/{y}.png',
        docs='https://registry.opendata.aws/terrain-tiles/',sha256=hashes),ensure_ascii=False,indent=2),encoding='utf8')
    for r in rows:
        print(r['building'],r['dorm'],r.get('meters'),round(r['drop_m'],1),round(r.get('net_downhill_grade',0)*100,1))


if __name__=='__main__':
    main()
