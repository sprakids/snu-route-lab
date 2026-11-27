"""Standalone research figures from the completed, hash-linked review only."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'_plot_deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
def main():
    source=ROOT/'review.json';r=json.loads(source.read_bytes())
    targets=[ROOT/'iteration_waits.png',ROOT/'weekday_waits.png']
    assert all(not p.exists() for p in targets)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(10,4.7),layout='constrained')
    for kind,color,label in [('baseline','#2563eb','Legacy fixed operation clocks'),('distribution_v8','#d97706','V8 distribution / entry-time profiles')]:
        rows=[x for x in r['iterations'] if x['operations']==kind]
        xs=[0 if x['revision']=='P0' else int(x['revision'][1:]) for x in rows]
        ax.plot(xs,[x['max_continuous_wait_min'] for x in rows],marker='o',label=label,color=color,lw=2)
    ax.axhline(20,color='#dc2626',ls='--',label='20-min audit boundary')
    ax.set(yscale='log',ylabel='Maximum continuous stop wait (minutes, log scale)',xlabel='Prototype revision',
           xticks=list(range(8)),xticklabels=['P0',*['R'+str(i) for i in range(1,8)]],title='Monday regular: preserved failures and subsequent repairs')
    ax.set_yticks([10,20,40,100,400]);ax.set_yticklabels(['10','20','40','100','400']);ax.grid(axis='y',alpha=.2)
    ax.legend(loc='upper right',frameon=False,fontsize=9)
    fig.savefig(targets[0],dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    days=['월','화','수','목','금'];x=list(range(5))
    for scenario,offset,color,label in [('regular',-.18,'#2563eb','Regular'),('peak',.18,'#0f766e','Peak')]:
        rows=[next(a for a in r['weekday_grid'] if a['weekday']==day and a['scenario']==scenario) for day in days]
        bars=axes[0].bar([i+offset for i in x],[a['max_continuous_wait_min'] for a in rows],.34,color=color,label=label)
        axes[0].bar_label(bars,fmt='%.2f',fontsize=8,padding=3)
        axes[1].plot(x,[a['candidate_total_min']-a['baseline_total_min'] for a in rows],marker='o',color=color,label=label)
    axes[0].axhline(20,color='#dc2626',ls='--',label='Audit boundary')
    axes[0].set(ylabel='Maximum stop wait (min)',title='Ten weekday / dispatch scenarios',ylim=(0,max(22.,1.2*max(a['max_continuous_wait_min'] for a in r['weekday_grid']))))
    axes[1].axhline(0,color='#6b7280',lw=1)
    axes[1].set(ylabel='Candidate minus V11 mean total (min)',title='Total effect: physics, behavior and city clocks')
    for ax in axes:
        ax.set_xticks(x,['Mon','Tue','Wed','Thu','Fri']);ax.grid(axis='y',alpha=.2);ax.legend(frameon=False,fontsize=9)
    fig.suptitle('Conditional scenario outputs; empirical accuracy NOT_EVALUABLE',fontsize=10)
    fig.savefig(targets[1],dpi=180);plt.close(fig)
    manifest={'source':'review.json','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'matplotlib_version':matplotlib.__version__,
              'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in targets},
              'not_a_guarantee_for_all_days_or_seeds':True}
    (ROOT/'figure_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8');print('FIGURES_CREATED')
if __name__=='__main__':main()
