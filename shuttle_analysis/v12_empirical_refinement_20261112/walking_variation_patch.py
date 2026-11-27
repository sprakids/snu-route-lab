"""Restore inherited person-specific relative walking factors, without new draws."""
def replace(path,old,new):
    text=path.read_text(encoding='utf8');assert text.count(old)==1,(path,old[:70],text.count(old))
    path.write_text(text.replace(old,new),encoding='utf8')
def apply(work):
    replace(work/'prepare.py',"    physical=config['physics']!='v9_frozen'", "    physical=config['physics']!='v9_frozen'\n    heterogeneous=physical and config.get('restore_source_walking_variation',False)\n    inherited_scales=dict(bundle['walk_scales'])")
    replace(work/'prepare.py',"        bundle['walk_scales']={str(p[0]):1. for p in plans}","""        if heterogeneous:
            from engine import scaled_stages
            # Nominal path-local4.8/stair/slope physics is retained. A person's
            # inherited relative factor scales every walking leg exactly once.
            for p in plans:
                factor=inherited_scales[str(p[0])]
                p[5][1]*=factor;p[6]=scaled_stages(p[6],factor)
            bundle['walk_scales']={str(p[0]):inherited_scales[str(p[0])] for p in plans}
        else:bundle['walk_scales']={str(p[0]):1. for p in plans}""")
    replace(work/'prepare.py',"            sig=(p[5][0],stage_key(p[6]));target=origin_catalog.setdefault(key,{})\n            target.setdefault(sig,{'walk':p[5],'stages':p[6],'key':repr(sig)})", """            sig=(p[5][0],stage_key(p[6]));target=origin_catalog.setdefault(key,{})
            if heterogeneous:
                from engine import scaled_stages
                factor=bundle['walk_scales'][str(p[0])]
                walk=[p[5][0],p[5][1]/factor];rows=scaled_stages(p[6],1/factor)
            else:walk=p[5];rows=p[6]
            target.setdefault(sig,{'walk':walk,'stages':rows,'key':repr(sig)})""")
    replace(work/'policy.py',"            options=bundle['origin_catalog'].get(repr((plan[1],plan[2],origin)),[]);candidates=[]", "            options=bundle['origin_catalog'].get(repr((plan[1],plan[2],origin)),[]);candidates=[]\n            factor=state['factor'] if config.get('restore_source_walking_variation') and config['physics']!='v9_frozen' else 1.")
    replace(work/'policy.py',"pred=self.predict(option['stages'],at,state,option['walk'][1],1.,access_path=option['walk'][0])", "pred=self.predict(option['stages'],at,state,option['walk'][1]*factor,factor,access_path=option['walk'][0])")
    replace(work/'policy.py',"                state['plan']=[*plan[:5],list(op['walk']),op['stages']];state['stages']=op['stages']", "                rows=scaled_stages(op['stages'],factor)\n                state['plan']=[*plan[:5],[op['walk'][0],op['walk'][1]*factor],rows];state['stages']=rows")
    replace(work/'analyze_followup.py',"            if kind==0 and paths is not None:close(b-a,paths[pid]['seconds'])", "            if kind==0 and paths is not None:\n                factor=frozen['walk_scales'][str(parent)] if receipt['config'].get('restore_source_walking_variation') else 1.\n                close(b-a,paths[pid]['seconds']*factor)")
