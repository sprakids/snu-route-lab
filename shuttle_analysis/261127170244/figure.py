"""Plot the measured and simulated one-bus OD counts on the same axes."""
from collections import Counter
from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})


def main():
    series=Counter()
    with (HERE/'목요일_두역방면.csv').open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            h=int(r['hour'])
            if r['service']!='peak' or not 15<=h<23:continue
            series[r['model'],r['metric'],h]+=float(r['modeled'])
            if r['model']=='base':series['card',r['metric'],h]+=int(r['measured'])
    hours=range(15,23)
    fig,axes=plt.subplots(1,2,figsize=(10.8,4.4),sharey=True)
    for ax,metric,title in zip(axes,('nak','snu'),('낙성대역·낙성대입구 하차','서울대입구역 2번 출구 하차')):
        ax.axvspan(16.5,20.5,color='#f1f5fa',zorder=0)
        for model,label,color,marker,style in [('card','11월 5일 카드','#222C32','s','-'),('base','직전 R','#747E90','o','--'),
                                                ('joint_soft','체류 + 거리별 접근 확률','#006C83','D','-')]:
            ax.plot(hours,[series[model,metric,h] for h in hours],label=label,color=color,linestyle=style,
                    linewidth=1.9,markersize=4,marker=marker)
        ax.set_title(title,loc='left',fontweight='bold')
        ax.set_xticks(list(hours),[f'{h}시' for h in hours]);ax.set_ylim(bottom=0)
        ax.grid(axis='y',alpha=.22);ax.spines[['right','top']].set_visible(False)
    axes[0].set_ylabel('승차 건수')
    fig.suptitle('제1·제2공학관에서 같은 버스로 두 역 방면까지 간 승차',fontweight='bold',fontsize=15,y=.98)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',ncol=3,frameon=False,bbox_to_anchor=(.5,.07))
    fig.text(.5,.03,'가로축은 승차한 한 시간의 시작 시각입니다. 음영은 실험의 저녁 시간대(17~21시)입니다.',ha='center',fontsize=9)
    fig.subplots_adjust(left=.075,right=.985,top=.81,bottom=.25,wspace=.12)
    fig.savefig(HERE/'목요일_두역방면.png',dpi=160)
    plt.close(fig)


if __name__=='__main__':main()
