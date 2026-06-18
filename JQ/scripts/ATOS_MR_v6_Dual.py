# -*- coding: utf-8 -*-
"""
ATOS MR v6 Dual Strategy
Params: mp=22, ps=17%, hold=8, sl=-2%, tp=30%
Dual Signal: MR (drop+RSI) + Trend (MA20 breakthrough + volume)
Architecture: single daily_handle at 09:30 (no pending queues)
"""
import numpy as np

STOCK_POOL = "ALL"

DISABLE_STOCK = {"000661","000792","002594","002737","002815","002913",
    "300401","300451","300602","300628","300773","300856",
    "301071","301487","301551","600167"}

def to_jq_code(c):
    return c + ".XSHG" if c.startswith("6") else c + ".XSHE"

# ==================== Stock Code Lists ====================
HS300_CODES_RAW = [
    '000001','000002','000063','000100','000157','000166','000301','000333',
    '000338','000408','000425','000538','000568','000596','000617','000625',
    '000630','000651','000708','000725','000768','000776','000786','000807',
    '000858','000876','000895','000938','000963','000975','000977','000983',
    '000999','001391','001965','001979','002001','002027','002028','002049',
    '002050','002074','002142','002179','002230','002236','002241','002252',
    '002304','002311','002352','002371','002384','002415','002422','002459',
    '002460','002463','002466','002475','002493','002600','002601','002625',
    '002648','002709','002714','002736','002916','002920','002938','003816',
    '300014','300015','300033','300059','300122','300124','300251','300274',
    '300308','300316','300347','300394','300408','300413','300418','300433',
    '300442','300476','300498','300502','300661','300750','300759','300760',
    '300782','300803','300832','300866','300896','300979','300999','301236',
    '301269','302132','600000','600009','600010','600011','600015','600016',
    '600018','600019','600023','600025','600026','600027','600028','600029',
    '600030','600031','600036','600039','600048','600050','600061','600066',
    '600085','600089','600104','600111','600115','600150','600160','600161',
    '600176','600183','600188','600196','600219','600233','600276','600309',
    '600346','600362','600372','600377','600406','600415','600426','600436',
    '600438','600460','600482','600489','600515','600519','600522','600547',
    '600570','600584','600585','600588','600600','600660','600674','600690',
    '600741','600760','600795','600803','600809','600845','600875','600886',
    '600887','600893','600900','600905','600918','600919','600926','600930',
    '600938','600941','600958','600989','600999','601006','601009','601012',
    '601018','601021','601058','601059','601066','601077','601088','601100',
    '601111','601117','601127','601136','601138','601166','601169','601186',
    '601211','601225','601229','601236','601238','601288','601298','601318',
    '601319','601328','601336','601360','601377','601390','601398','601456',
    '601600','601601','601607','601618','601628','601633','601658','601668',
    '601669','601688','601689','601698','601728','601766','601788','601800',
    '601808','601816','601818','601825','601838','601857','601868','601872',
    '601877','601878','601881','601888','601898','601899','601901','601916',
    '601919','601939','601985','601988','601995','601998','603019','603195',
    '603259','603260','603288','603296','603369','603392','603501','603799',
    '603893','603986','603993','605117','605499','688008','688009','688012',
    '688036','688041','688047','688082','688111','688126','688169','688187',
    '688223','688256','688271','688303','688396','688472','688506','688981',
]

CYB_STAR_50_CODES_RAW = [
    '300002','300014','300015','300017','300024','300033','300058','300059',
    '300073','300115','300122','300124','300136','300207','300223','300251',
    '300255','300274','300308','300316','300339','300346','300347','300373',
    '300394','300395','300408','300418','300433','300442','300450','300458',
    '300474','300476','300496','300502','300548','300604','300724','300748',
    '300750','300759','300760','300763','300782','300803','300857','301236',
    '301308','302132','688008','688009','688012','688027','688036','688041',
    '688047','688065','688072','688082','688099','688111','688114','688120',
    '688122','688126','688169','688183','688187','688188','688213','688220',
    '688223','688234','688249','688256','688271','688278','688297','688303',
    '688349','688361','688375','688396','688469','688472','688506','688521',
    '688525','688538','688568','688578','688599','688608','688617','688702',
    '688728','688777','688981','689009',
]

CSI1000_CODES_RAW = [
    '000012','000019','000028','000029','000030','000035','000048','000049',
    '000058','000059','000061','000065','000089','000099','000156','000403',
    '000420','000422','000498','000503','000543','000550','000552','000555',
    '000557','000567','000581','000589','000597','000600','000603','000612',
    '000620','000628','000636','000650','000672','000676','000680','000681',
    '000682','000685','000686','000688','000690','000712','000719','000727',
    '000737','000756','000758','000761','000762','000766','000767','000778',
    '000791','000795','000801','000810','000811','000813','000828','000829',
    '000833','000837','000848','000860','000875','000880','000885','000899',
    '000901','000902','000913','000917','000923','000927','000928','000930',
    '000935','000950','000966','000969','000970','000990','001203','001227',
    '001236','001287','001301','001308','001309','001337','001339','001356',
    '001382','001914','002003','002004','002006','002010','002011','002015',
    '002017','002019','002020','002023','002036','002038','002041','002043',
    '002045','002046','002048','002051','002053','002060','002061','002063',
    '002068','002073','002075','002077','002079','002081','002091','002093',
    '002096','002097','002099','002100','002101','002104','002110','002121',
    '002123','002125','002127','002139','002145','002149','002151','002158',
    '002163','002170','002171','002174','002176','002182','002183','002192',
    '002194','002204','002212','002215','002216','002219','002221','002222',
    '002226','002233','002237','002239','002242','002243','002245','002249',
    '002251','002254','002258','002267','002268','002270','002275','002276',
    '002287','002292','002302','002315','002317','002320','002324','002326',
    '002332','002338','002345','002351','002354','002364','002368','002373',
    '002378','002389','002390','002396','002399','002400','002405','002408',
    '002416','002421','002428','002434','002456','002458','002468','002484',
    '002487','002488','002489','002497','002498','002506','002507','002511',
    '002516','002518','002531','002534','002536','002537','002539','002541',
    '002543','002544','002545','002550','002557','002563','002572','002588',
    '002597','002605','002611','002612','002617','002626','002635','002643',
    '002649','002651','002654','002668','002675','002681','002690','002697',
    '002698','002701','002705','002706','002716','002727','002745','002747',
    '002755','002761','002777','002779','002791','002807','002827','002832',
    '002839','002840','002847','002859','002867','002881','002882','002891',
    '002892','002895','002896','002897','002901','002906','002911','002925',
    '002928','002929','002936','002941','002946','002947','002948','002960',
    '002965','002967','002978','002979','002985','002987','002993','003006',
    '003012','003039','300007','300008','300009','300026','300031','300034',
    '300035','300036','300045','300047','300049','300065','300075','300077',
    '300079','300080','300083','300085','300087','300088','300098','300101',
    '300102','300113','300119','300127','300130','300131','300133','300134',
    '300151','300166','300170','300171','300180','300181','300182','300183',
    '300184','300185','300188','300199','300224','300226','300229','300232',
    '300236','300244','300253','300257','300260','300276','300284','300294',
    '300296','300298','300303','300315','300319','300323','300327','300337',
    '300341','300348','300357','300360','300363','300378','300398','300406',
    '300409','300415','300416','300428','300438','300443','300446','300455',
    '300456','300457','300459','300463','300468','300470','300475','300482',
    '300492','300493','300525','300548','300568','300573','300576','300579',
    '300580','300593','300595','300598','300607','300613','300618','300620',
    '300624','300633','300634','300638','300641','300655','300657','300660',
    '300663','300666','300672','300674','300678','300682','300685','300687',
    '300693','300702','300705','300723','300725','300726','300738','300747',
    '300755','300761','300762','300768','300770','300772','300775','300776',
    '300777','300779','300783','300809','300811','300820','300821','300827',
    '300841','300850','300855','300861','300870','300872','300910','300913',
    '300917','300925','300926','300953','301000','301004','301015','301018',
    '301029','301031','301035','301039','301047','301050','301061','301078',
    '301087','301091','301095','301101','301109','301127','301153','301155',
    '301171','301175','301177','301205','301207','301215','301217','301219',
    '301238','301262','301263','301267','301268','301275','301291','301293',
    '301297','301316','301325','301327','301339','301345','301363','301371',
    '301376','301377','301381','301392','301458','301500','301508','301510',
    '301511','301522','301526','301550','301556','301565','301571','301589',
    '301592','301600','301602','301606','301622','301626','301631','301658',
    '301665','301678','600006','600012','600017','600020','600022','600033',
    '600037','600055','600056','600057','600058','600059','600063','600064',
    '600072','600075','600094','600100','600105','600113','600114','600116',
    '600120','600123','600125','600129','600133','600151','600155','600158',
    '600163','600179','600185','600186','600197','600201','600206','600210',
    '600211','600216','600217','600223','600226','600246','600248','600252',
    '600258','600259','600266','600267','600269','600273','600285','600292',
    '600301','600305','600315','600320','600323','600325','600328','600330',
    '600331','600335','600338','600353','600361','600366','600373','600388',
    '600389','600395','600399','600403','600409','600416','600420','600422',
    '600428','600446','600452','600456','600458','600459','600461','600475',
    '600478','600480','600490','600502','600507','600508','600509','600529',
    '600531','600550','600552','600556','600557','600559','600572','600575',
    '600577','600586','600587','600595','600596','600597','600612','600618',
    '600619','600621','600623','600629','600633','600635','600639','600640',
    '600641','600643','600645','600649','600651','600654','600657','600662',
    '600664','600667','600675','600682','600686','600710','600717','600718',
    '600726','600728','600729','600740','600744','600746','600750','600751',
    '600757','600761','600771','600773','600776','600782','600783','600787',
    '600789','600810','600812','600821','600827','600835','600850','600859',
    '600861','600864','600866','600867','600869','600872','600877','600882',
    '600888','600894','600903','600908','600916','600928','600929','600933',
    '600961','600963','600971','600975','600986','600993','600996','600997',
    '601003','601020','601022','601033','601038','601068','601069','601083',
    '601089','601096','601101','601107','601126','601137','601163','601187',
    '601200','601208','601222','601311','601326','601369','601375','601500',
    '601519','601528','601595','601606','601609','601619','601636','601677',
    '601678','601702','601777','601778','601801','601811','601858','601860',
    '601869','601882','601890','601900','601908','601949','601952','601963',
    '601969','601975','603005','603009','603013','603014','603025','603026',
    '603027','603033','603039','603043','603055','603057','603063','603072',
    '603083','603093','603099','603100','603103','603108','603118','603119',
    '603127','603128','603162','603169','603171','603193','603194','603197',
    '603202','603218','603219','603220','603227','603229','603236','603256',
    '603262','603267','603279','603283','603297','603299','603300','603305',
    '603306','603308','603317','603323','603327','603328','603337','603355',
    '603358','603360','603383','603393','603395','603456','603477','603496',
    '603505','603508','603516','603530','603533','603556','603567','603583',
    '603588','603599','603612','603613','603619','603638','603662','603663',
    '603667','603678','603690','603693','603698','603713','603730','603733',
    '603809','603826','603866','603871','603876','603881','603883','603887',
    '603888','603915','603919','603983','603997','605009','605011','605020',
    '605090','605099','605111','605116','605118','605123','605198','605296',
    '605333','605376','605507','605555','605599','688001','688003','688005',
    '688006','688007','688016','688029','688032','688048','688050','688062',
    '688063','688068','688083','688088','688091','688097','688102','688106',
    '688107','688110','688116','688123','688127','688128','688131','688139',
    '688141','688146','688147','688150','688153','688158','688165','688177',
    '688182','688185','688190','688200','688205','688206','688208','688209',
    '688232','688252','688262','688276','688279','688289','688300','688306',
    '688313','688321','688326','688327','688331','688332','688333','688337',
    '688343','688348','688351','688352','688362','688372','688380','688382',
    '688390','688400','688403','688408','688409','688432','688433','688439',
    '688443','688484','688486','688498','688502','688503','688515','688516',
    '688519','688522','688523','688536','688543','688548','688549','688552',
    '688559','688567','688575','688584','688586','688591','688596','688612',
    '688630','688631','688639','688652','688658','688660','688686','688690',
    '688696','688698','688700','688717','688726','688739','688766','688776',
    '688779','688789','688798','688800',
]

ALL_CODES_RAW = sorted(set(HS300_CODES_RAW) | set(CSI1000_CODES_RAW) | set(CYB_STAR_50_CODES_RAW))

TRADING_UNIVERSE_JQ = set(
    [to_jq_code(c) for c in HS300_CODES_RAW if c not in DISABLE_STOCK] +
    [to_jq_code(c) for c in CYB_STAR_50_CODES_RAW if c not in DISABLE_STOCK]
)

# ==================== Global Parameters ====================
PARAMS = {
    'max_positions': 22,
    'position_pct': 0.17,
    'hold_days': 8,
    'stop_loss': -0.02,
    'take_profit': 0.30,
    'max_pending_days': 20,
    'corp_action_th': 15.0,
    'regime_pos_mult': {
        'BULL': 1.5, 'SIDEWAYS': 1.0, 'BEAR': 0.2,
        'CHOPPY_BEAR': 0.3, 'CRASH': 0.0,
    },
    'trend_vol_mult': 1.2,
}

# ==================== Utility Functions ====================
def calc_rsi(close_list, period=6):
    n = len(close_list)
    if n < period + 1:
        return float('nan')
    closes = [float(x) for x in close_list]
    gains, losses = [], []
    for i in range(1, n):
        d = closes[i] - closes[i-1]
        if d > 0: gains.append(d); losses.append(0.0)
        else: gains.append(0.0); losses.append(abs(d))
    alpha = 1.0 / period
    avg_gain = gains[0]
    avg_loss = losses[0]
    for i in range(1, len(gains)):
        avg_gain = avg_gain * (1 - alpha) + gains[i] * alpha
        avg_loss = avg_loss * (1 - alpha) + losses[i] * alpha
    if not np.isfinite(avg_gain) or not np.isfinite(avg_loss):
        return float('nan')
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)

def calc_sma(close_list, period):
    n = len(close_list)
    if n < period: return float('nan')
    return sum(float(x) for x in close_list[-period:]) / period

# ==================== Regime Detection ====================
def detect_regime_jq(context):
    market = '000300.XSHG'
    h = attribute_history(market, 120, '1d', ['close','high','low','volume'], df=True, fq='pre')
    if h is None or h.empty: return 'SIDEWAYS'
    close = h['close']; vol = h['volume']; n = len(close)
    if n < 63: return 'SIDEWAYS'
    ma20 = close.rolling(20).mean(); ma60 = close.rolling(60).mean()
    log_ret = np.log(close / close.shift(1))
    vol_20d = log_ret.rolling(20).std() * np.sqrt(252)
    ret_20d = close / close.shift(20) - 1
    dd_5d = close / close.shift(5) - 1; dd_20d = close / close.shift(20) - 1
    idx = -4
    c_t3 = float(close.iloc[idx]); ma20_t3 = float(ma20.iloc[idx]); ma60_t3 = float(ma60.iloc[idx])
    ret_20d_t3 = float(ret_20d.iloc[idx]); vol_20d_t3 = float(vol_20d.iloc[idx])
    dd_5d_t3 = float(dd_5d.iloc[idx]); dd_20d_t3 = float(dd_20d.iloc[idx])
    vol_20_avg = float(vol.rolling(20).mean().iloc[idx])
    vol_ratio = float(vol.iloc[idx]) / vol_20_avg if vol_20_avg > 0 else 1.0
    if not all(np.isfinite([c_t3, ma20_t3, ma60_t3, ret_20d_t3, vol_20d_t3, dd_5d_t3, dd_20d_t3])):
        return 'SIDEWAYS'
    is_crash = (dd_5d_t3 <= -0.08 or dd_20d_t3 <= -0.15 or
                (vol_20d_t3 > 0.35 and dd_5d_t3 < -0.05) or
                (vol_ratio > 2.0 and dd_5d_t3 < -0.03))
    is_bull = (c_t3 > ma60_t3 and ma20_t3 > ma60_t3 and
               ret_20d_t3 >= 0.05 and vol_20d_t3 <= 0.30 and not is_crash)
    is_bear = (c_t3 < ma60_t3 and ma20_t3 < ma60_t3 and
               ret_20d_t3 <= -0.05 and not is_crash)
    if is_crash: base_state = 'CRASH'
    elif is_bull: base_state = 'BULL'
    elif is_bear: base_state = 'BEAR'
    else: base_state = 'SIDEWAYS'
    cum_ret_60d = c_t3 / float(close.iloc[idx-59]) - 1 if n >= (abs(idx)+60) else 0
    vol_60d = float(log_ret.rolling(60).std().iloc[idx] * np.sqrt(252)) if n >= (abs(idx)+60) else 1.0
    ma60_20d_ago = float(ma60.iloc[idx-19]) if n >= (abs(idx)+20) else float(ma60.iloc[idx])
    ma60_slope = (ma60_t3 - ma60_20d_ago) / (ma60_20d_ago + 1e-9)
    choppy_score = sum([cum_ret_60d < -0.05, vol_60d < 0.18,
                        abs(ma60_slope) < 0.00025, ma20_t3 < ma60_t3])
    if choppy_score >= 3: return 'CHOPPY_BEAR'
    return base_state

# ==================== Signal Computation ====================
def compute_signals_jq(stock_list, g):
    n = 30
    df_close = history(n, unit='1d', field='close', security_list=stock_list,
                       df=True, skip_paused=False, fq='pre')
    if df_close is None or df_close.empty: return {}
    signals = {}
    for stock in stock_list:
        try:
            close_s = df_close[stock].dropna()
            if len(close_s) < 15: continue
        except KeyError: continue
        current_close = float(close_s.iloc[-1])
        prev_5_close = float(close_s.iloc[-6]) if len(close_s) >= 6 else current_close
        drop_5d = current_close / prev_5_close - 1
        rsi6 = calc_rsi(list(close_s), period=6)
        if not np.isfinite(rsi6) or not np.isfinite(drop_5d): continue
        if drop_5d < -0.10 and rsi6 < 20:
            signals[stock] = ('main', rsi6)
        elif drop_5d < -0.08 and rsi6 < 30:
            if g.regime == 'BULL': signals[stock] = ('secondary', rsi6)
    return signals

def compute_trend_signals_jq(stock_list, exclude_stocks):
    n = 25
    df_close = history(n, unit='1d', field='close', security_list=stock_list,
                       df=True, skip_paused=False, fq='pre')
    df_vol = history(n, unit='1d', field='volume', security_list=stock_list,
                     df=True, skip_paused=False, fq='pre')
    if df_close is None or df_close.empty: return []
    candidates = []; cd = get_current_data()
    for stock in stock_list:
        if stock in exclude_stocks: continue
        try:
            close_s = df_close[stock].dropna(); vol_s = df_vol[stock].dropna()
            if len(close_s) < 21 or len(vol_s) < 21: continue
        except KeyError: continue
        c = float(close_s.iloc[-1]); c1 = float(close_s.iloc[-2])
        ma20 = calc_sma(list(close_s), 20)
        v = float(vol_s.iloc[-1]); v20 = calc_sma(list(vol_s), 20)
        if not all(np.isfinite([c, c1, ma20, v, v20])) or v20 <= 0: continue
        if c > ma20 and c1 < ma20 and v > PARAMS['trend_vol_mult'] * v20:
            try: d = cd[stock]
            except KeyError: continue
            if d.paused or d.is_st: continue
            if d.high_limit > 0 and d.last_price >= d.high_limit: continue
            candidates.append((stock, c))
    return candidates

# ==================== Filters ====================
def check_filters(stock, cd):
    try: d = cd[stock]
    except KeyError: return False
    if d.paused or d.is_st: return False
    if d.high_limit > 0 and d.last_price >= d.high_limit: return False
    if d.low_limit > 0 and d.last_price <= d.low_limit: return False
    if d.last_price <= 0 or not np.isfinite(d.last_price): return False
    return True

def check_corp_action(stock):
    try:
        h = attribute_history(stock, 1, '1d', ['pct_change'], skip_paused=False, df=False, fq='pre')
        if h is not None and len(h['pct_change']) > 0:
            pct = h['pct_change'][-1]
            if pct is not None and not np.isnan(pct): return abs(pct) > PARAMS['corp_action_th']
    except Exception: pass
    return False

def check_recent_extreme(stock):
    try:
        h = attribute_history(stock, 10, '1d', ['pct_change'], skip_paused=False, df=False, fq='pre')
        if h is not None:
            recent = [x for x in h['pct_change'] if x is not None and not np.isnan(x)]
            if any(abs(x) > PARAMS['corp_action_th'] for x in recent[-5:]): return False
    except Exception: pass
    return True

# ==================== Initialize ====================
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
        open_commission=0.00025, close_commission=0.00025,
        close_today_commission=0, min_commission=5), type='stock')
    set_slippage(FixedSlippage(0.002))
    log.set_level('order', 'error')
    if STOCK_POOL == 'HS300':
        g.universe = [to_jq_code(c) for c in HS300_CODES_RAW if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'CSI1000':
        g.universe = [to_jq_code(c) for c in CSI1000_CODES_RAW if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'CYB_STAR_50':
        g.universe = [to_jq_code(c) for c in CYB_STAR_50_CODES_RAW if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'ALL':
        g.universe = [to_jq_code(c) for c in ALL_CODES_RAW if c not in DISABLE_STOCK]
    else: raise ValueError('Unknown stock_pool: ' + STOCK_POOL)
    set_universe(g.universe)
    g.holdings = {}          # {stock: {entry_date, entry_price, shares, holding_days}}
    g.regime = 'SIDEWAYS'
    g.bar_index = 0
    run_daily(daily_handle, '09:30')
    log.info('ATOS MR v6 Dual: stock_pool=%s, universe=%d, trading=%d'
             % (STOCK_POOL, len(g.universe), len(TRADING_UNIVERSE_JQ)))

# ==================== Main Loop (09:30) ====================
def daily_handle(context):
    """T 09:30: update holdings → exit check & execute → entry check & execute"""
    g.bar_index += 1
    if g.bar_index == 1: return  # skip first day
    g.regime = detect_regime_jq(context)
    cd = get_current_data()
    today = context.current_dt.date()
    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash
    regime_mult = PARAMS['regime_pos_mult'].get(g.regime, 0.5)

    # ---- Step 1: update holdings with T-1 close ----
    for stock in list(g.holdings.keys()):
        h = g.holdings[stock]
        try: d = cd[stock]
        except KeyError: continue
        h['last_close'] = float(d.last_price) if d.last_price > 0 else h.get('last_close', h['entry_price'])
        h['holding_days'] = h.get('holding_days', 0) + 1

    # ---- Step 2: exit check & execute ----
    exit_reasons = []  # (stock, reason)
    for stock, h in list(g.holdings.items()):
        if h.get('entry_date') == today: continue  # T+1 lock
        try: d = cd[stock]
        except KeyError: continue
        cur_close = float(d.last_price)
        if cur_close <= 0: continue
        ret = (cur_close - h['entry_price']) / h['entry_price']
        days_held = h.get('holding_days', 0)
        is_corp = check_corp_action(stock)
        should_sell = False; reason = ''
        if is_corp: should_sell = True; reason = 'corp_action'
        elif ret >= PARAMS['take_profit']: should_sell = True; reason = 'tp'
        elif ret <= PARAMS['stop_loss']: should_sell = True; reason = 'sl'
        elif days_held >= PARAMS['hold_days']: should_sell = True; reason = 'time'
        elif g.regime == 'CRASH': should_sell = True; reason = 'crash'
        if should_sell:
            exit_reasons.append((stock, reason, h))

    # Execute exits
    for stock, reason, h in exit_reasons:
        log.info('[SELL] %s reason=%s' % (stock, reason))
        try: d = cd[stock]
        except KeyError: continue
        if d.paused: continue
        exec_price = float(d.last_price) if d.last_price > 0 else h['entry_price']
        if d.low_limit > 0 and d.last_price <= d.low_limit:
            continue  # limit-down, try tomorrow
        if reason == 'corp_action':
            try:
                hist = attribute_history(stock, 2, '1d', ['close'], skip_paused=False, df=False, fq='pre')
                if hist is not None and len(hist['close']) >= 2:
                    exec_price = float(hist['close'][-2])
            except Exception: pass
        order_result = None
        if stock.startswith('688'):
            order_result = order(stock, -h['shares'], LimitOrderStyle(min(exec_price*0.995, 9999.99)))
        else:
            order_result = order_target_value(stock, 0)
        if order_result is not None and (not hasattr(order_result, 'filled') or order_result.filled > 0):
            log.info('[SELL-DONE] %s @ %.2f reason=%s' % (stock, exec_price, reason))
            del g.holdings[stock]

    # ---- Step 3: entry signals ----
    held = set(g.holdings.keys())
    available = [s for s in g.universe if s not in held and s in TRADING_UNIVERSE_JQ]
    mr_signals = compute_signals_jq(available, g)
    n_to_buy = PARAMS['max_positions'] - len(g.holdings)
    mr_count = 0
    if g.regime != 'CRASH' and n_to_buy > 0:
        sorted_mr = sorted(mr_signals.items(), key=lambda x: x[1][1])
        for stock, (sig_type, rsi) in sorted_mr[:n_to_buy]:
            if not check_filters(stock, cd): continue
            if not check_recent_extreme(stock): continue
            _execute_buy(stock, cd, cash, total_value, regime_mult, context)
            mr_count += 1
            cash = context.portfolio.available_cash
    remaining = n_to_buy - mr_count
    if g.regime != 'CRASH' and remaining > 0:
        exclude = held | set([s for s in g.holdings.keys()])
        trend_available = [s for s in g.universe if s not in exclude and s in TRADING_UNIVERSE_JQ]
        trend_candidates = compute_trend_signals_jq(trend_available, exclude)
        trend_candidates.sort(key=lambda x: x[1])
        for stock, _ in trend_candidates[:remaining]:
            if not check_recent_extreme(stock): continue
            _execute_buy(stock, cd, cash, total_value, regime_mult, context)
            cash = context.portfolio.available_cash

    log.info('[%s] regime=%s holdings=%d cash=%.0f total=%.0f signals=%d trend=%d' %
             (today, g.regime, len(g.holdings), cash, total_value,
              len(mr_signals), len(trend_candidates) if 'trend_candidates' in dir() else 0))

def _execute_buy(stock, cd, cash, total_value, regime_mult, context):
    try: d = cd[stock]
    except KeyError: return
    if d.paused: return
    if d.high_limit > 0 and d.last_price >= d.high_limit: return
    last_price = float(d.last_price)
    if last_price <= 0 or not np.isfinite(last_price): return
    per_value = total_value * PARAMS['position_pct'] * regime_mult
    shares = int(per_value / (last_price * 1.001) / 100) * 100
    if shares < 100: shares = 100
    cost = shares * last_price * 1.001
    if cost > cash * 0.95:
        affordable = int(cash * 0.95 / (last_price * 1.001) / 100) * 100
        if affordable < 100: return
        shares = affordable
    if shares < 100: return
    order_result = None
    if stock.startswith('688'):
        order_result = order(stock, shares, LimitOrderStyle(min(last_price*1.005, 9999.99)))
    else:
        order_result = order(stock, shares)
    if order_result is None or (hasattr(order_result, 'filled') and order_result.filled == 0):
        return
    g.holdings[stock] = {
        'entry_date': context.current_dt.date(),
        'entry_price': last_price,
        'shares': shares,
        'holding_days': 1,
    }
