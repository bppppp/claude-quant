import numpy as np, sys
sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK

h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)

starts=['2018-01-01','2018-04-01','2018-07-01','2018-10-01','2019-01-01','2019-04-01','2019-07-01','2019-10-01','2020-01-01','2020-04-01','2020-07-01','2020-10-01','2021-01-01','2021-04-01']
windows=[(s,str(int(s[:4])+1)+s[4:]) if int(s[5:7])<=6 else (s,str(int(s[:4])+2)+s[4:]) for s in starts]
# Fix windows: all 18 months
windows2=[]
for s in starts:
    y=int(s[:4]); m=int(s[5:7])
    ey=y+(m+18)//12; em=(m+18)%12; if em==0: em=12; ey-=1
    windows2.append((s,f'{ey:04d}-{em:02d}-01',''))

for ver,label in [('v2','bs'),('v1','jy')]:
    print(f'=== {label} ({ver}) ===')
    results=[]
    for st,en,_ in windows2:
        if en > '2022-12-31': continue
        r=backtest_v2(st,en,'ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,data_version=ver,verbose=False)
        a=r['annual_return']*100; d=abs(r['max_drawdown'])*100
        lb=st[2:4]+st[5:7]+'-'+en[2:4]+en[5:7]
        results.append((lb,a,d))
        print(f'  {lb}: ann={a:+6.1f}% dd={d:5.1f}%')
    anns=[r[1] for r in results]; dds=[r[2] for r in results]
    print(f'  Range: ann={min(anns):+.1f}~{max(anns):+.1f}% dd={min(dds):.1f}~{max(dds):.1f}%')
    print(f'  Mean ann={np.mean(anns):+.1f}% AllPos={all(a>0 for a in anns)}')
    print()
