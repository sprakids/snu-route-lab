"""Reproducible standalone figures from the final review tables."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'prototype_review_2026-11-10/_plot_deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
def main():
    source=ROOT/'review.json';r=json.loads(source.read_bytes());targets=[ROOT/'weekday_waits.png',ROOT/'factor_times.png']
    assert all(not p.exists() for p in targets)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(11,4.7),layout='constrained')
    days=['월','화','수','목','금'];x=list(range(5))
    for scenario,shift,color,label in [('regular',-.18,'#2563eb','Regular'),('peak',.18,'#0f766e','Peak')]:
        rows=[next(a for a in r['weekday_comparison'] if a['weekday']==day and a['scenario']==scenario) for day in days]
        bars=axes[0].bar([n+shift for n in x],[a['candidate_max_stop_wait_min'] for a in rows],.34,color=color,label=label)
        axes[0].bar_label(bars,fmt='%.2f',fontsize=8,padding=3,rotation=90)
        axes[1].plot(x,[a['candidate_total_min']-a['baseline_total_min'] for a in rows],marker='o',color=color,label=label)
    validation=Path(r['validation'])/'validation.json'
    assert hashlib.sha256(validation.read_bytes()).hexdigest()==r['validation_sha256']
    extra=[a for a in json.loads(validation.read_bytes())['results'] if a['case']['seed'] in (1,2)]
    axes[0].scatter([5,6],[a['maximum_continuous_wait_min'] for a in extra],marker='^',color='#7c3aed',s=45,label='Mon regular extra seeds',zorder=5)
    for shift,a in zip([5,6],extra):axes[0].annotate(f'{a["maximum_continuous_wait_min"]:.2f}',(shift,a['maximum_continuous_wait_min']),xytext=(0,8),textcoords='offset points',ha='center',fontsize=8,color='#7c3aed')
    axes[0].axhline(20,color='#dc2626',ls='--',label='20-min audit boundary')
    axes[0].set(ylabel='Maximum continuous stop wait (min)',title='Ten weekday cases + two extraMon seeds',
                ylim=(0,max(24.,1.2*r['maximum_continuous_wait_min'])))
    axes[1].axhline(0,color='#6b7280',lw=1)
    axes[1].set(ylabel='Candidate minus V11 mean total (min)',title='Total effect: physics, behavior and city clocks')
    axes[0].set_xticks(list(range(7)),['Mon','Tue','Wed','Thu','Fri','Mon\ns1','Mon\ns2'])
    axes[1].set_xticks(x,['Mon','Tue','Wed','Thu','Fri'])
    for ax in axes:ax.grid(axis='y',alpha=.2);ax.legend(frameon=False,fontsize=8,loc='upper left' if ax is axes[0] else 'lower right')
    fig.suptitle('Conditional scenario outputs; empirical accuracy NOT_EVALUABLE',fontsize=10)
    fig.savefig(targets[0],dpi=180);plt.close(fig)
    rows=r['factor_comparison'];fig,ax=plt.subplots(figsize=(9.8,4.9),layout='constrained')
    xs=list(range(len(rows)));walk=[a['walk_min'] for a in rows];wait=[a['wait_min'] for a in rows];ride=[a['total_min']-a['wait_min']-a['walk_min'] for a in rows]
    assert min(ride)>=0
    ax.bar(xs,walk,label='Walking',color='#d97706');ax.bar(xs,wait,bottom=walk,label='Cumulative waiting',color='#2563eb')
    bars=ax.bar(xs,ride,bottom=[a+b for a,b in zip(walk,wait)],label='On vehicle',color='#0f766e')
    ax.bar_label(bars,labels=[f'{a["total_min"]:.2f}' for a in rows],padding=3,fontsize=9)
    labels=[('Previous' if a['behavior']=='previous' else 'Candidate')+'\n'+{'baseline':'Legacy clocks','distribution_v8':'V8 distribution','gate_reference':'Gate reference'}[a['operations']] for a in rows]
    ax.set_xticks(xs,labels,fontsize=8)
    ax.set(ylabel='Weighted mean journey minutes',title='Monday regular: same4.8km/h physics, demand and44-seat paired supply')
    ax.set_ylim(0,max(a['total_min'] for a in rows)*1.24);ax.grid(axis='y',alpha=.2);ax.legend(frameon=False,ncol=3,loc='upper center',fontsize=9)
    fig.suptitle('Behavior / forecast and operation-clock factors; scenario comparison only',fontsize=10)
    fig.savefig(targets[1],dpi=180);plt.close(fig)
    (ROOT/'figure_manifest.json').write_text(json.dumps({'source':'review.json','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'matplotlib_version':matplotlib.__version__,'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in targets}},indent=2),encoding='utf8')
    print('FINAL_FIGURES_CREATED')
if __name__=='__main__':main()
