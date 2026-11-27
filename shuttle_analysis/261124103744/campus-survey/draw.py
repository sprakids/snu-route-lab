"""Draw the two measured walking networks and their extrema on an offline map."""
import gzip
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import LineString
from survey import HERE, OSM, boundaries, forward, ordinary, outdoor, point_xy

fontdir=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
def font(size,bold=False):
    return ImageFont.truetype(str(fontdir/('malgunbd.ttf' if bold else 'malgun.ttf')),size)

with gzip.open(OSM,'rt',encoding='utf8') as stream:
    entries={(e['type'],e['id']):e for e in json.load(stream)['elements']}
city,osm,_=boundaries(entries)
result=json.loads((HERE/'result.json').read_text(encoding='utf8'))['cases']
features=json.loads((HERE/'extremes.geojson').read_text(encoding='utf8'))['features']
canvas=Image.new('RGB',(1440,1040),'#f6f7f4')
p=ImageDraw.Draw(canvas)
p.text((46,25),'관악캠퍼스에서 얼마나 오르내릴까요?',font=font(40,True),fill='#19372e')
p.text((48,91),'연결된 두 지점의 최대 고도차와 보행거리 100m당 최대 경사',font=font(23),fill='#465b54')
for i,(scope,label,region) in enumerate([('everyday','강의동·생활관 생활권',city.intersection(osm)),('school','서울시 학교시설 경계 · 산길 포함',city)]):
    left=40+i*700
    p.rounded_rectangle((left,154,left+665,928),radius=20,fill='white',outline='#d7ded8',width=2)
    p.text((left+24,173),label,font=font(27,True),fill='#19372e')
    row=result[scope]
    p.text((left+24,224),f"최대 고도차 {abs(row['net_up']['net_m']):.0f}m    |    100m 최대 경사 {row['grade_up']['grade_percent']:.0f}%",font=font(21),fill='#285e51')
    minx,miny,maxx,maxy=region.bounds
    scale=min(580/(maxx-minx),505/(maxy-miny))
    def screen(xy):
        return (left+333+(xy[0]-(minx+maxx)/2)*scale,540-(xy[1]-(miny+maxy)/2)*scale)
    for poly in ([region] if region.geom_type=='Polygon' else region.geoms):
        p.polygon([screen(x) for x in poly.exterior.coords],fill='#eef3e9',outline='#99ac96',width=2)
        for hole in poly.interiors:
            p.polygon([screen(x) for x in hole.coords],fill='white')
    for (kind,wid),w in entries.items():
        t=w.get('tags',{})
        if kind!='way' or not outdoor(t) or (i==0 and not ordinary(t)):
            continue
        line=LineString([point_xy(entries['node',n]) for n in w['nodes']]).intersection(region)
        for sub in line.geoms if hasattr(line,'geoms') else [line]:
            if sub.geom_type=='LineString' and not sub.is_empty:
                p.line([screen(q) for q in sub.coords],fill='#c2cdc2',width=1)
    for metric,color,width in [('net_up','#245d70',4),('grade_up','#d25332',8)]:
        feature=next(f for f in features if f['properties']==dict(scope=scope,metric=metric))
        coords=[screen(forward(*q)) for q in feature['geometry']['coordinates']]
        p.line(coords,fill=color,width=width)
        if metric=='net_up':
            for xy in (coords[0],coords[-1]):
                x,y=xy
                p.ellipse((x-6,y-6,x+6,y+6),outline=color,width=3,fill='white')
    p.text((left+24,811),'낮은 곳  정문 부근',font=font(19),fill='#31483e')
    p.text((left+24,844),'높은 곳  '+('제2공학관 옆' if i==0 else '관악산 정상 표지점 부근'),font=font(19),fill='#31483e')
    p.text((left+24,877),'급경사  '+('제1공학관 옆 계단·보행로' if i==0 else '자운암능선 등산로'),font=font(19),fill='#a13b21')
p.line((51,964,103,964),fill='#245d70',width=5)
p.text((112,947),'최저·최고 지점을 잇는 최단 보행로',font=font(19),fill='#31483e')
p.line((475,964,526,964),fill='#d25332',width=8)
p.text((538,947),'가장 가파른 100m',font=font(19),fill='#31483e')
p.text((49,994),'서울특별시 도시계획시설 2026.09  ·  © OpenStreetMap contributors (ODbL)  ·  Mapzen / AWS Terrain Tiles     |     지형고도 추정, 북쪽이 위',font=font(15),fill='#52645c')
canvas.save(HERE/'캠퍼스_고도차.png')
