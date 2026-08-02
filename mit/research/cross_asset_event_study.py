from __future__ import annotations
from pathlib import Path
import json, math, zipfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path('/mnt/data/cross_asset_reversal_continuation')
ROOT.mkdir(parents=True, exist_ok=True)


def ema(s, length):
    return s.ewm(span=length, adjust=False).mean()


def rsi_wilder(close, length=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    ag = gain.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    al = loss.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    rs = ag / al.replace(0, np.nan)
    out = 100 - 100/(1+rs)
    out = out.where(~((ag == 0) & (al == 0)), 50)
    out = out.where(al != 0, 100)
    return out


def atr_wilder(data, length=14):
    pc = data['Close'].shift()
    tr = pd.concat([(data['High']-data['Low']), (data['High']-pc).abs(), (data['Low']-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, adjust=False, min_periods=length).mean()


def dmi_adx(data, length=14):
    up = data['High'].diff(); down = -data['Low'].diff()
    pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=data.index)
    mdm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=data.index)
    pc = data['Close'].shift()
    tr = pd.concat([(data['High']-data['Low']), (data['High']-pc).abs(), (data['Low']-pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    pdi = 100*pdm.ewm(alpha=1/length, adjust=False, min_periods=length).mean()/atr
    mdi = 100*mdm.ewm(alpha=1/length, adjust=False, min_periods=length).mean()/atr
    dx = 100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    adx = dx.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    return pdi, mdi, adx


def load_asset(symbol):
    if symbol == 'SPY':
        raw = pd.read_csv('/mnt/data/SPY_5m.csv')
        raw['Datetime'] = pd.to_datetime(raw['Datetime'], utc=True).dt.tz_convert('America/New_York')
        source = 'SPY_5m.csv'
    elif symbol == 'TSLA':
        raw = pd.read_csv('/mnt/data/TSLAUSUSD_M5.csv', sep='\t').rename(columns={'Time':'Datetime'})
        raw['Datetime'] = pd.to_datetime(raw['Datetime'], utc=True).dt.tz_convert('America/New_York')
        # Normalize the unadjusted source to post-2022 split basis.
        pre_2020 = raw['Datetime'] < pd.Timestamp('2020-08-31', tz='America/New_York')
        between = (raw['Datetime'] >= pd.Timestamp('2020-08-31', tz='America/New_York')) & (raw['Datetime'] < pd.Timestamp('2022-08-25', tz='America/New_York'))
        raw.loc[pre_2020, ['Open','High','Low','Close']] /= 15.0
        raw.loc[between, ['Open','High','Low','Close']] /= 3.0
        source = 'TSLAUSUSD_M5.csv; split-adjusted in research code'
    else:
        raise ValueError(symbol)
    raw = raw.set_index('Datetime').sort_index()
    r = raw.between_time('09:30','15:59').copy()
    r['date'] = r.index.date
    counts = r.groupby('date').size()
    complete_days = counts[counts == 78].index
    df = r[r['date'].isin(complete_days)][['Open','High','Low','Close','Volume','date']].copy()
    return df, source, complete_days


def live_htf(data, minutes, prefix, ema_len=5, bb_len=20, bb_mult=2.0, rsi_len=14):
    idx = data.index
    mins = (idx.hour*60 + idx.minute) - (9*60+30)
    bucket_num = np.zeros(len(data), dtype=int) if minutes is None else (mins//minutes).astype(int)
    keys = pd.MultiIndex.from_arrays([pd.Index(data['date']), bucket_num])
    bucket_id = pd.factorize(keys)[0]
    bucket_s = pd.Series(bucket_id, index=idx)
    completed = data['Close'].groupby(bucket_s).last()
    completed_ema = completed.ewm(span=ema_len, adjust=False).mean()
    prev_ema = completed_ema.shift(1)
    prev_close = completed.shift(1)
    alpha = 2/(ema_len+1)
    curr = data['Close'].to_numpy()
    live_ema = alpha*curr + (1-alpha)*prev_ema.reindex(bucket_id).to_numpy()

    nprev = bb_len-1
    psum = completed.shift(1).rolling(nprev,min_periods=nprev).sum().reindex(bucket_id).to_numpy()
    psq = (completed*completed).shift(1).rolling(nprev,min_periods=nprev).sum().reindex(bucket_id).to_numpy()
    basis = (psum+curr)/bb_len
    var = (psq+curr*curr)/bb_len - basis*basis
    sd = np.sqrt(np.maximum(var,0))

    delta = completed.diff(); gain=delta.clip(lower=0); loss=(-delta).clip(lower=0)
    ag = gain.ewm(alpha=1/rsi_len, adjust=False, min_periods=rsi_len).mean().shift(1).reindex(bucket_id).to_numpy()
    al = loss.ewm(alpha=1/rsi_len, adjust=False, min_periods=rsi_len).mean().shift(1).reindex(bucket_id).to_numpy()
    pc = prev_close.reindex(bucket_id).to_numpy()
    cd = curr-pc; cg=np.maximum(cd,0); cl=np.maximum(-cd,0)
    lag=(ag*(rsi_len-1)+cg)/rsi_len; lal=(al*(rsi_len-1)+cl)/rsi_len
    rs=lag/lal
    lrsi=100-100/(1+rs)
    lrsi=np.where((lal==0)&(lag>0),100,lrsi)
    lrsi=np.where((lal==0)&(lag==0),50,lrsi)
    return pd.DataFrame({
        prefix+'ema5':live_ema,
        prefix+'bb_basis':basis,
        prefix+'bb_upper':basis+bb_mult*sd,
        prefix+'bb_lower':basis-bb_mult*sd,
        prefix+'rsi':lrsi,
    }, index=idx)


def enrich(df):
    df=df.copy()
    df['ema5']=ema(df['Close'],5)
    df['rsi14']=rsi_wilder(df['Close'],14)
    df['rsi_basis']=df['rsi14'].rolling(20).mean()
    rsd=df['rsi14'].rolling(20).std(ddof=0)
    df['rsi_upper']=df['rsi_basis']+2*rsd; df['rsi_lower']=df['rsi_basis']-2*rsd
    df['ema20_h']=ema(df['High'],20); df['ema20_m']=ema((df['High']+df['Low']+df['Close'])/3,20); df['ema20_l']=ema(df['Low'],20)
    df['pdi'],df['mdi'],df['adx']=dmi_adx(df,14)
    df['adx_slope2']=df['adx']-df['adx'].shift(2)
    df['atr5']=atr_wilder(df,14)
    for minutes,prefix in [(15,'m15_'),(30,'m30_'),(60,'h1_'),(240,'h4_'),(None,'d1_')]:
        df=df.join(live_htf(df,minutes,prefix))
    daily=df.groupby('date').agg(Open=('Open','first'),High=('High','max'),Low=('Low','min'),Close=('Close','last'))
    daily['previous_close']=daily['Close'].shift(1)
    daily['tr']=pd.concat([(daily['High']-daily['Low']),(daily['High']-daily['previous_close']).abs(),(daily['Low']-daily['previous_close']).abs()],axis=1).max(axis=1)
    daily['atr14']=daily['tr'].ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    daily['previous_atr14']=daily['atr14'].shift(1)
    df['previous_day_close']=df['date'].map(daily['previous_close'])
    df['previous_daily_atr']=df['date'].map(daily['previous_atr14'])
    df['day_open']=df['date'].map(daily['Open'])
    df['gap_pct']=100*(df['day_open']/df['previous_day_close']-1)
    df['atr_ratio']=df['atr5']/df['previous_daily_atr']

    df['mtf_bull']=np.logical_and.reduce([df['Close']>df['ema5'],df['Close']>df['m15_ema5'],df['Close']>df['h1_ema5'],df['Close']>df['h4_ema5'],df['Close']>df['d1_ema5']])
    df['mtf_bear']=np.logical_and.reduce([df['Close']<df['ema5'],df['Close']<df['m15_ema5'],df['Close']<df['h1_ema5'],df['Close']<df['h4_ema5'],df['Close']<df['d1_ema5']])
    df['ribbon_bull']=df['Close']>df['ema20_h']; df['ribbon_bear']=df['Close']<df['ema20_l']
    df['rsi_flow_bull']=(df['rsi14']>df['rsi_basis'])&(df['rsi14']>50)
    df['rsi_flow_bear']=(df['rsi14']<df['rsi_basis'])&(df['rsi14']<50)
    df['adx_bull']=(df['pdi']>df['mdi'])&(df['adx']>=20)
    df['adx_bear']=(df['mdi']>df['pdi'])&(df['adx']>=20)
    return df,daily


def bento_events(df, dual=True, min_abs_gap_pct=0.0):
    rows=[]
    for day,g in df.groupby('date', sort=False):
        if len(g)<6 or pd.isna(g['previous_day_close'].iloc[0]): continue
        gap=float(g['gap_pct'].iloc[0])
        if abs(gap)<min_abs_gap_pct or gap==0: continue
        r=g.iloc[5 if dual else 2]
        gd=1 if gap>0 else -1
        if gd==1:
            c15=r['Close']>r['m15_bb_upper'] and r['m15_rsi']>=70
            c30=r['Close']>r['m30_bb_upper'] and r['m30_rsi']>=70
            direction=-1
        else:
            c15=r['Close']<r['m15_bb_lower'] and r['m15_rsi']<=30
            c30=r['Close']<r['m30_bb_lower'] and r['m30_rsi']<=30
            direction=1
        if c15 and (c30 if dual else True):
            rows.append(dict(signal_time=r.name,date=day,direction=direction,gap_direction=gd,gap_pct=gap,signal_price=float(r['Close']),previous_daily_atr=float(r['previous_daily_atr']),variant='Bento 15m+30m' if dual else 'Bento 15m'))
    return pd.DataFrame(rows)


def pulse_events(df,bull,bear,name,cooldown=6):
    state=np.where(np.asarray(bull,dtype=bool),1,np.where(np.asarray(bear,dtype=bool),-1,0))
    rows=[]; prev=0; last=-10**9
    idx=df.index; close=df['Close'].to_numpy(); dates=df['date'].to_numpy(); datr=df['previous_daily_atr'].to_numpy(); adx=df['adx'].to_numpy(); ratio=df['atr_ratio'].to_numpy()
    for i,s in enumerate(state):
        if s!=0 and s!=prev and i-last>=cooldown and np.isfinite(datr[i]):
            rows.append(dict(signal_time=idx[i],date=dates[i],direction=int(s),signal_price=float(close[i]),previous_daily_atr=float(datr[i]),adx=float(adx[i]),atr_ratio=float(ratio[i]),variant=name))
            last=i
        prev=s
    return pd.DataFrame(rows)


def combined_confirm(df,bento,min_score=5,max_wait=24):
    if bento.empty: return pd.DataFrame()
    loc=pd.Series(np.arange(len(df)),index=df.index)
    rows=[]
    for e in bento.itertuples(index=False):
        p=int(loc.loc[e.signal_time]); direction=int(e.direction)
        end=min(len(df),p+1+max_wait)
        for j in range(p+1,end):
            r=df.iloc[j]
            if r['date']!=e.date: break
            prev=df.iloc[j-1]
            if direction==-1:
                comp=[r['Close']<=r['m15_bb_upper'],r['Close']<=r['ema20_h'],r['rsi14']<r['rsi_basis'] and r['rsi14']<prev['rsi14'],r['mdi']>r['pdi'],not bool(r['mtf_bull']),r['Close']<prev['Close']]
            else:
                comp=[r['Close']>=r['m15_bb_lower'],r['Close']>=r['ema20_l'],r['rsi14']>r['rsi_basis'] and r['rsi14']>prev['rsi14'],r['pdi']>r['mdi'],not bool(r['mtf_bear']),r['Close']>prev['Close']]
            score=int(sum(bool(x) for x in comp))
            if score>=min_score:
                rows.append(dict(signal_time=df.index[j],date=e.date,direction=direction,signal_price=float(r['Close']),previous_daily_atr=float(r['previous_daily_atr']),gap_pct=float(e.gap_pct),gap_direction=int(e.gap_direction),arm_time=e.signal_time,delay_min=(df.index[j]-e.signal_time).total_seconds()/60,score=score,variant=f'Combined reversal {min_score}/6'))
                break
    return pd.DataFrame(rows)


def router_events(df,bento,threshold=4):
    # At the Bento extreme, use Trinity components to decide fade vs continuation.
    rows=[]
    for e in bento.itertuples(index=False):
        r=df.loc[e.signal_time]; gd=int(e.gap_direction)
        if gd==1:
            comps=[bool(r['mtf_bull']),bool(r['ribbon_bull']),bool(r['rsi_flow_bull']),bool(r['adx_bull']),bool(r['atr_ratio']>=0.14)]
        else:
            comps=[bool(r['mtf_bear']),bool(r['ribbon_bear']),bool(r['rsi_flow_bear']),bool(r['adx_bear']),bool(r['atr_ratio']>=0.14)]
        score=sum(comps)
        direction=gd if score>=threshold else -gd
        rows.append(dict(signal_time=e.signal_time,date=e.date,direction=direction,signal_price=e.signal_price,previous_daily_atr=e.previous_daily_atr,gap_pct=e.gap_pct,gap_direction=gd,trinity_gap_score=score,decision='continuation' if direction==gd else 'reversal',variant=f'Bento-Trinity router {threshold}/5'))
    return pd.DataFrame(rows)


def first_touch(fav,adv,threshold):
    for f,a in zip(fav,adv):
        fh=f>=threshold; ah=a>=threshold
        if fh and ah: return 'ambiguous'
        if fh: return 'favorable'
        if ah: return 'adverse'
    return 'none'


def evaluate(events,df,horizons=(15,30,60,120),fixed=(10,25,50,100),atr_fracs=(0.10,0.20)):
    if events.empty: return events.copy()
    idx=df.index; pos=pd.Series(np.arange(len(df)),index=idx)
    high=df['High'].to_numpy(); low=df['Low'].to_numpy(); close=df['Close'].to_numpy(); dates=df['date'].to_numpy()
    # end position per row
    end_by_date={d:inds[-1] for d,inds in pd.Series(np.arange(len(df)),index=df.index).groupby(df['date'].to_numpy())}
    rows=[]
    for e in events.to_dict('records'):
        p=int(pos.loc[e['signal_time']]); end=int(end_by_date[e['date']])
        if p>=end: continue
        entry=float(e['signal_price']); direction=int(e['direction'])
        hs=high[p+1:end+1]; ls=low[p+1:end+1]; cs=close[p+1:end+1]
        if direction==1:
            fav=(hs/entry-1)*10000; adv=(1-ls/entry)*10000
        else:
            fav=(1-ls/entry)*10000; adv=(hs/entry-1)*10000
        out=e.copy()
        out['normalized_10pct_datr_bp']=float(0.10*e['previous_daily_atr']/entry*10000) if np.isfinite(e.get('previous_daily_atr',np.nan)) else np.nan
        for minutes in list(horizons)+['eod']:
            n=len(fav) if minutes=='eod' else min(len(fav),int(minutes)//5)
            if n<=0: continue
            f=fav[:n]; a=adv[:n]; c=cs[n-1]
            label='eod' if minutes=='eod' else f'{minutes}m'
            out[f'mfe_{label}_bp']=float(np.max(f)); out[f'mae_{label}_bp']=float(np.max(a)); out[f'close_{label}_bp']=float(direction*(c/entry-1)*10000); out[f'mfe_gt_mae_{label}']=int(np.max(f)>np.max(a))
            for t in fixed:
                out[f'hit_{t}bp_{label}']=int(np.any(f>=t)); out[f'first_{t}bp_{label}']=first_touch(f,a,t)
            for frac in atr_fracs:
                t=frac*float(e['previous_daily_atr'])/entry*10000
                key=f'{int(frac*100)}pct_datr'
                out[f'hit_{key}_{label}']=int(np.any(f>=t)); out[f'first_{key}_{label}']=first_touch(f,a,t)
        rows.append(out)
    return pd.DataFrame(rows)


def wilson(k,n,z=1.96):
    if n==0:return (np.nan,np.nan)
    p=k/n; den=1+z*z/n; center=(p+z*z/(2*n))/den; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return 100*(center-half),100*(center+half)


def summary_row(symbol,name,res,coverage_base=None):
    row={'symbol':symbol,'model':name,'signals':len(res)}
    if len(res)==0:return row
    for h in ['30m','60m']:
        row[f'directional_close_{h}_pct']=100*(res[f'close_{h}_bp']>0).mean()
        row[f'mfe_gt_mae_{h}_pct']=100*res[f'mfe_gt_mae_{h}'].mean()
        for key in ['10bp','25bp','50bp','100bp','10pct_datr','20pct_datr']:
            col=f'first_{key}_{h}'
            if col not in res:continue
            resolved=res[col].isin(['favorable','adverse'])
            n=int(resolved.sum()); k=int((res.loc[resolved,col]=='favorable').sum())
            row[f'first_{key}_{h}_resolved_n']=n
            row[f'first_{key}_{h}_favorable_pct']=100*k/n if n else np.nan
            lo,hi=wilson(k,n); row[f'first_{key}_{h}_ci_low']=lo; row[f'first_{key}_{h}_ci_high']=hi
            row[f'hit_{key}_{h}_pct']=100*res[f'hit_{key}_{h}'].mean()
    row['median_mfe_30m_bp']=res['mfe_30m_bp'].median(); row['median_mae_30m_bp']=res['mae_30m_bp'].median()
    if 'delay_min' in res: row['median_delay_min']=res['delay_min'].median()
    if coverage_base: row['coverage_vs_bento_pct']=100*len(res)/coverage_base
    return row


def run_asset(symbol):
    outdir=ROOT/symbol; outdir.mkdir(exist_ok=True)
    base,source,days=load_asset(symbol)
    df,daily=enrich(base)
    b15=bento_events(df,dual=False)
    bdual=bento_events(df,dual=True)
    core_bull=df['mtf_bull']&df['ribbon_bull']&df['rsi_flow_bull']&df['adx_bull']
    core_bear=df['mtf_bear']&df['ribbon_bear']&df['rsi_flow_bear']&df['adx_bear']
    trinity=pulse_events(df,core_bull&(df['adx_slope2']>0)&(df['atr_ratio']>=0.14),core_bear&(df['adx_slope2']>0)&(df['atr_ratio']>=0.14),'Trinity continuation')
    combined4=combined_confirm(df,bdual,4); combined5=combined_confirm(df,bdual,5)
    routers={t:router_events(df,bdual,t) for t in [3,4,5]}
    models={'Bento reversal':bdual,'Trinity continuation':trinity,'Combined reversal 4/6':combined4,'Combined reversal 5/6':combined5}
    models.update({f'Router {t}/5':ev for t,ev in routers.items()})
    results={name:evaluate(ev,df) for name,ev in models.items()}
    for name,res in results.items():
        safe=name.lower().replace(' ','_').replace('/','of')
        res.to_csv(outdir/f'events_{safe}.csv',index=False)
    rows=[]
    for name,res in results.items(): rows.append(summary_row(symbol,name,res,len(bdual) if name.startswith('Combined') else None))
    summ=pd.DataFrame(rows); summ.to_csv(outdir/'summary.csv',index=False)
    # Per-year stability for key models.
    yearly=[]
    for name in ['Bento reversal','Trinity continuation','Combined reversal 5/6','Router 4/5']:
        res=results[name].copy()
        if res.empty:continue
        res['year']=pd.to_datetime(res['date']).dt.year
        for y,g in res.groupby('year'):
            rr=summary_row(symbol,name,g)
            rr['year']=int(y); yearly.append(rr)
    pd.DataFrame(yearly).to_csv(outdir/'yearly_stability.csv',index=False)
    meta={'symbol':symbol,'source':source,'bars':len(df),'complete_sessions':len(days),'start':str(df.index.min()),'end':str(df.index.max()),'split_adjustment':'TSLA: /15 before 2020-08-31, /3 from 2020-08-31 through 2022-08-24' if symbol=='TSLA' else 'source-adjusted','outcomes':'directional close, MFE versus MAE, and symmetric first-touch at fixed and prior-daily-ATR-normalized thresholds'}
    (outdir/'metadata.json').write_text(json.dumps(meta,indent=2))
    return summ,results,meta


if __name__=='__main__':
    all_s=[]; all_results={}; metas={}
    for symbol in ['SPY','TSLA']:
        s,r,m=run_asset(symbol); all_s.append(s); all_results[symbol]=r; metas[symbol]=m
    summary=pd.concat(all_s,ignore_index=True)
    summary.to_csv(ROOT/'cross_asset_summary.csv',index=False)

    # Comparison chart using cross-asset 10% prior daily ATR first-touch metric.
    pick=['Bento reversal','Trinity continuation','Combined reversal 5/6','Router 4/5']
    plot=summary[summary['model'].isin(pick)].copy()
    pivot=plot.pivot(index='model',columns='symbol',values='first_10pct_datr_30m_favorable_pct').reindex(pick)
    ax=pivot.plot(kind='bar',figsize=(11,6))
    ax.set_ylim(0,100); ax.set_ylabel('Predicted side touched first (%)'); ax.set_xlabel('')
    ax.set_title('30-minute first-touch precision at 10% of prior daily ATR')
    plt.xticks(rotation=12,ha='right'); plt.tight_layout(); plt.savefig(ROOT/'cross_asset_first_touch.png',dpi=180); plt.close()

    # Concise decision table.
    cols=['symbol','model','signals','directional_close_30m_pct','mfe_gt_mae_30m_pct','first_10pct_datr_30m_resolved_n','first_10pct_datr_30m_favorable_pct','first_10pct_datr_30m_ci_low','first_10pct_datr_30m_ci_high','hit_10pct_datr_30m_pct','median_delay_min','coverage_vs_bento_pct']
    decision=summary[summary['model'].isin(pick)][[c for c in cols if c in summary.columns]]
    decision.to_csv(ROOT/'decision_table.csv',index=False)

    # Bundle.
    bundle=Path('/mnt/data/cross_asset_reversal_continuation_bundle.zip')
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob('*'):
            if p.is_file() and p != bundle and '__pycache__' not in str(p): z.write(p,p.relative_to(ROOT))
    print(decision.to_string(index=False))
    print('\nBundle:',bundle)
