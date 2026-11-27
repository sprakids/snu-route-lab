"""Small deterministic networks for physical FIFO regression, not empirical data."""
from artifacts import ROOT,START,read
import copy

def leg(rid='A',board=0,alight=1):
    return {'rid':rid,'board':board,'alight':alight,'wait_path':0,'ride_path':0,'ride_seconds':60.,'next_walk':[0,5.]}

def fixture(groups,config=None):
    point=[37.45,126.95];routes={};info={};plans=[];supply={}
    for uid,(rid,weight,first) in enumerate(groups,1):
        routes[rid]={'id':rid,'name':rid,'stops':[{'id':'s0'},{'id':'s1'}]}
        info[rid]={'n':2,'offsets':[0.,60.],'segments':[0],'anchor':0,'city':True,'capacity':50}
        plans.append([uid,'301','snu',float(weight),float(START),[0,1.],[leg(rid)]])
        supply[rid]=[START+first,START+first+100]
    common={'nodes':[{'id':'city|s0','city':True,'route':'city','name':'shared','lat':point[0],'lon':point[1]}],
            'city_nodes':[0],'route_info':info,'paths':[[point,[point[0]+.001,point[1]]]]}
    cfg=read(ROOT/'config.json');cfg.update(config or {})
    return {'prepared':{'common':common,'routes':routes,'plans':{'월':plans}},
            'city_node_lookup':{r+'|0':0 for r in routes},'walk_scales':{str(p[0]):1. for p in plans},
            'destination_keys':{str(p[0]):'snu' for p in plans},'alternatives':{'0|snu':[]},
            'parent_ids':{str(p[0]):p[0] for p in plans},'source_parent_mass':{str(p[0]):p[3] for p in plans},
            'supply':{'regular':supply,'peak':supply},'prototype_config':cfg,'origin_catalog':{},
            'physical_paths':[{'meters':111.,'seconds':83.25,'stairs_meters':0.}]}

def vehicle(rid='A',cap=50,onboard=()):
    return {'id':0,'rid':rid,'cap':cap,'onboard':list(onboard),'last_stop':-1}

def waiter(weight,rid='A'):return {'w':float(weight),'stages':[leg(rid)],'stage':0}
