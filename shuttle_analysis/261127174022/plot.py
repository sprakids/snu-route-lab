"""Show actual boarding volumes and the smaller before/after differences separately."""
from pathlib import Path
import csv
from statistics import mean
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
FONTS = {"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 10}


def main():
    plt.rcParams.update(FONTS)
    obs, ref = {}, {}
    with (HERE/"정류장_카드대조.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r["service"],r["stop"],r["metric"]) != ("peak","120000173","all"):
                continue
            h = int(r["hour"])
            obs[r["day"],r["date"],h] = int(r["obs"])
            ref[r["day"],r["mode"],h] = float(r["modeled"])
    fig, axes = plt.subplots(2,2,figsize=(10.2,6.3),sharex=True,
                             gridspec_kw={"height_ratios":(1.65,1)})
    hours = list(range(12,23))
    for j,(day,title) in enumerate((("thu","목요일 · 11월 5·12·19일"),("wed","수요일 · 11월 11일 별도 검증"))):
        ax,delta = axes[:,j]
        dates=sorted({d for (w,d,h) in obs if w==day})
        by_hour=[[obs[day,d,h] for d in dates] for h in hours]
        if len(dates)>1:
            ax.fill_between(hours,[min(xs) for xs in by_hour],[max(xs) for xs in by_hour],color="#CAD2D5",alpha=.65)
        ax.plot(hours,[mean(x) for x in by_hour],color="#222C31",marker="o",markersize=3,label="카드 실측")
        for mode,label,color,style in (("base","직전 R","#718197","--"),("within","낮 출발을 저녁으로","#AE572C",":"),
                                       ("relocate","저녁 출발 권역 재배분","#087D79","-")):
            v=[ref[day,mode,h] for h in hours]
            ax.plot(hours,v,color=color,linestyle=style,label=label,lw=2)
            if mode!="base":
                delta.plot(hours,[ref[day,mode,h]-ref[day,"base",h] for h in hours],color=color,
                           linestyle=style,lw=2,marker="o",markersize=3)
        ax.set_title(title,loc="left",fontweight="bold")
        ax.set_ylim(bottom=0)
        delta.axhline(0,color="#7D8587",lw=.8)
        for a in (ax,delta):
            a.axvspan(17.5,20.5,color="#DCF0EC",alpha=.35,zorder=0)
            a.spines[["right","top"]].set_visible(False)
            a.grid(axis="y",alpha=.2)
        delta.set_xticks(hours,[str(h) for h in hours])
        delta.set_xlabel("승차 시간대의 시작 시각")
    top=max(a.get_ylim()[1] for a in axes[0])
    for a in axes[0]: a.set_ylim(0,top)
    bound=max(max(abs(v) for v in a.get_ylim()) for a in axes[1])
    for a in axes[1]: a.set_ylim(-bound,bound)
    axes[0,0].set_ylabel("시간당 승차 건수")
    axes[1,0].set_ylabel("직전 R 대비 증감(건)")
    fig.suptitle("제2공학관 승차 실측과 윗공대 저녁 활동 가정의 효과",fontsize=15,fontweight="bold")
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="lower center",bbox_to_anchor=(.5,.055),ncol=4,frameon=False)
    fig.text(.5,.032,"회색 띠는 세 목요일의 실측 범위, 검은 선은 관측일 평균입니다. 청록색 음영은 18~21시입니다.",
             ha="center",fontsize=9)
    fig.subplots_adjust(top=.85,bottom=.21,left=.075,right=.98,wspace=.14,hspace=.23)
    fig.savefig(HERE/"제2공학관_승차.png",dpi=155)
    plt.close(fig)


if __name__=="__main__":
    main()
