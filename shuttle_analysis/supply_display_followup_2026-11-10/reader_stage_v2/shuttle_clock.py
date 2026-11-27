"""One shared published terminal clock for timetable and capacity simulations."""
from datetime import datetime,timedelta

WINDOWS={
 '41841':[(420,480,15),(480,660,4),(660,900,10),(900,1140,4),(1140,1200,15),(1200,1260,30)],
 '41843':[(420,480,15),(480,660,6.5),(660,1140,10)],
 '41946':[(480,1140,6),(1140,1260,20)],
 '41842':[(480,660,7)],'41868':[(480,660,10)],'41869':[(510,660,5)]}
FIXED={'41914':list(range(590,1031,20)),'41915':[1270,1300,1330,1360,1390],
       '41942':[1270,1300,1330,1360,1390],'41916':[1440,1470,1500,1530,1560]}

def dispatches(rid,phase,combined=True):
    rid=rid.removeprefix('shuttle-');out=[]
    for start,end,h in WINDOWS.get(rid,[]):
        value=start+phase*h
        while value<end-1e-7:out.append(value*60);value+=h
    out.extend(m*60 for m in FIXED.get(rid,[]))
    if rid in ('41841','41843') and combined:
        out.extend(m*60 for m in FIXED['41915'] for _ in range(2))
    # The current notice supplies explicit last terminal departures.
    if rid in ('41841','41843','41842','41868','41869','41946'):
        out.append(WINDOWS[rid][-1][1]*60)
    return sorted(out)
