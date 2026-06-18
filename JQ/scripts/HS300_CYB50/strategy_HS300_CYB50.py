# -*- coding: utf-8 -*-
"""
ATOS MR v5 OPTIMIZED
Params: mp=12, ps=22%, hold=14, sl=-3%, tp=30%
Signal: MR (drop+RSI) only
Architecture: single daily_handle at 09:30 (no pending queues)
"""
import numpy as np

STOCK_POOL = "HS300"

DISABLE_STOCK = {"000661","000792","002594","002737","002815","002913",
    "300401","300451","300602","300628","300773","300856",
    "301071","301487","301551","600167"}

def to_jq_code(c):
    return c + ".XSHG" if c.startswith("6") else c + ".XSHE"

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

TRADING_UNIVERSE_JQ = set(to_jq_code(c) for c in HS300_CODES_RAW if c not in DISABLE_STOCK)

PARAMS = {
    'max_positions': 12,
    'position_pct': 0.22,
    'hold_days': 14,
    'stop_loss': -0.03,
    'take_profit': 0.30,
    'corp_action_th': 15.0,
    'regime_pos_mult': {
        'BULL': 1.5, 'SIDEWAYS': 1.0, 'BEAR': 0.2,
        'CHOPPY_BEAR': 0.3, 'CRASH': 0.0,
    },
}

def calc_rsi(close_list, period=6):
    n = len(close_list)
    if n < period + 1: return float('nan')
    closes = [float(x) for x in close_list]
    gains, losses = [], []
    for i in range(1, n):
        d = closes[i] - closes[i-1]
        if d > 0: gains.append(d); losses.append(0.0)
        else: gains.append(0.0); losses.append(abs(d))
    alpha = 1.0 / period
    avg_gain, avg_loss = gains[0], losses[0]
    for i in range(1, len(gains)):
        avg_gain = avg_gain * (1 - alpha) + gains[i] * alpha
        avg_loss = avg_loss * (1 - alpha) + losses[i] * alpha
    if not np.isfinite(avg_gain) or not np.isfinite(avg_loss): return float('nan')
    if avg_loss == 0: return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

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
        cc = float(close_s.iloc[-1]); p5 = float(close_s.iloc[-6]) if len(close_s) >= 6 else cc
        drop_5d = cc / p5 - 1
        rsi6 = calc_rsi(list(close_s), period=6)
        if not np.isfinite(rsi6) or not np.isfinite(drop_5d): continue
        if drop_5d < -0.10 and rsi6 < 20:
            signals[stock] = ('main', rsi6)
        elif drop_5d < -0.08 and rsi6 < 30:
            if g.regime == 'BULL': signals[stock] = ('secondary', rsi6)
    return signals

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

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
        open_commission=0.00025, close_commission=0.00025,
        close_today_commission=0, min_commission=5), type='stock')
    set_slippage(FixedSlippage(0.002))
    log.set_level('order', 'error')
    g.universe = [to_jq_code(c) for c in HS300_CODES_RAW if c not in DISABLE_STOCK]
    set_universe(g.universe)
    g.holdings = {}
    g.regime = 'SIDEWAYS'
    g.bar_index = 0
    run_daily(daily_handle, '09:30')
    log.info('ATOS MR v5 OPT: universe=%d trading=%d' % (len(g.universe), len(TRADING_UNIVERSE_JQ)))

def daily_handle(context):
    g.bar_index += 1
    if g.bar_index == 1: return
    g.regime = detect_regime_jq(context)
    cd = get_current_data()
    today = context.current_dt.date()
    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash
    regime_mult = PARAMS['regime_pos_mult'].get(g.regime, 0.5)

    for stock in list(g.holdings.keys()):
        h = g.holdings[stock]
        try: d = cd[stock]
        except KeyError: continue
        h['last_close'] = float(d.last_price) if d.last_price > 0 else h.get('last_close', h['entry_price'])
        h['holding_days'] = h.get('holding_days', 0) + 1

    for stock, h in list(g.holdings.items()):
        if h.get('entry_date') == today: continue
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
        if not should_sell: continue
        log.info('[SELL] %s reason=%s ret=%.2f%% held=%dd' % (stock, reason, ret*100, days_held))
        if d.paused: continue
        exec_price = float(d.last_price) if d.last_price > 0 else h['entry_price']
        if d.low_limit > 0 and d.last_price <= d.low_limit: continue
        if reason == 'corp_action':
            try:
                hist = attribute_history(stock, 2, '1d', ['close'], skip_paused=False, df=False, fq='pre')
                if hist is not None and len(hist['close']) >= 2: exec_price = float(hist['close'][-2])
            except Exception: pass
        order_result = None
        if stock.startswith('688'):
            order_result = order(stock, -h['shares'], LimitOrderStyle(min(exec_price*0.995, 9999.99)))
        else:
            order_result = order_target_value(stock, 0)
        if order_result is not None and (not hasattr(order_result, 'filled') or order_result.filled > 0):
            log.info('[SELL-DONE] %s @ %.2f reason=%s' % (stock, exec_price, reason))
            del g.holdings[stock]

    held = set(g.holdings.keys())
    available = [s for s in g.universe if s not in held and s in TRADING_UNIVERSE_JQ]
    mr_signals = compute_signals_jq(available, g)
    n_to_buy = PARAMS['max_positions'] - len(g.holdings)
    if g.regime != 'CRASH' and n_to_buy > 0:
        sorted_mr = sorted(mr_signals.items(), key=lambda x: x[1][1])
        for stock, (sig_type, rsi) in sorted_mr[:n_to_buy]:
            if not check_filters(stock, cd): continue
            if not check_recent_extreme(stock): continue
            _execute_buy(stock, cd, cash, total_value, regime_mult, context)
            cash = context.portfolio.available_cash

    if g.bar_index % 60 == 0 or len(mr_signals) > 0 or len(g.holdings) == 0:
        log.info('[%s] regime=%s holdings=%d cash=%.0f total=%.0f signals=%d' %
                 (today, g.regime, len(g.holdings), cash, total_value, len(mr_signals)))

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
