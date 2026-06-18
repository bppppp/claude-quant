# -*- coding: utf-8 -*-
"""
ATOS MR v6 Dual Strategy - Polywide
Params: mp=22, ps=17%, hold=8, sl=-2%, tp=30%
Dual Signal: MR (drop+RSI) + Trend (MA20 breakthrough + volume)
Local: annual ~39.2% (2018-2022), DD ~-14%, Sharpe ~1.78
"""

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

ALL_CODES_RAW = sorted(set(HS300_CODES_RAW) | set(CYB_STAR_50_CODES_RAW))

# v6: Trading universe = HS300 + CYB_STAR_50
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
        'BULL': 1.5,
        'SIDEWAYS': 1.0,
        'BEAR': 0.2,
        'CHOPPY_BEAR': 0.3,
        'CRASH': 0.0,
    },
    # Trend signal params (v6 new)
    'trend_ma_period': 20,
    'trend_vol_mult': 1.2,
}

# ==================== Utility Functions ====================
def calc_rsi(close_list, period=6):
    """RSI via Wilder smoothing (matches local ewm(alpha=1/period, adjust=False).mean())"""
    n = len(close_list)
    if n < period + 1:
        return float('nan')
    closes = [float(x) for x in close_list]
    gains = []
    losses = []
    for i in range(1, n):
        d = closes[i] - closes[i-1]
        if d > 0:
            gains.append(d); losses.append(0.0)
        else:
            gains.append(0.0); losses.append(abs(d))

    # Wilder smoothing (matches pandas ewm(alpha=1/period, adjust=False))
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
    """Simple moving average"""
    n = len(close_list)
    if n < period:
        return float('nan')
    return sum(float(x) for x in close_list[-period:]) / period


# ==================== Regime Detection (matches local detect_full_regime) ====================
def detect_regime_jq(context):
    """Market regime detection matching local atos/regime/ pipeline:
    1. detect_market_regime: BULL/BEAR/SIDEWAYS/CRASH (4-state boolean rules)
    2. detect_choppy_bear_vectorized: 4-condition CHOPPY_BEAR overlay
    3. Lag 3 days to avoid hysteresis look-ahead bias
    """
    market = '000300.XSHG'
    h = attribute_history(market, 120, '1d',
                          ['close', 'high', 'low', 'volume'], df=True, fq='pre')
    if h is None or h.empty:
        return 'SIDEWAYS'

    close = h['close']
    high = h['high']
    vol = h['volume']
    n = len(close)
    if n < 63:
        return 'SIDEWAYS'

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    log_ret = np.log(close / close.shift(1))
    vol_20d = log_ret.rolling(20).std() * np.sqrt(252)
    ret_20d = close / close.shift(20) - 1
    dd_5d = close / close.shift(5) - 1
    dd_20d = close / close.shift(20) - 1

    # Use T-3 index (lag 3 days to avoid hysteresis look-ahead)
    idx = -4  # T-3
    c_t3 = float(close.iloc[idx])
    ma20_t3 = float(ma20.iloc[idx])
    ma60_t3 = float(ma60.iloc[idx])
    ret_20d_t3 = float(ret_20d.iloc[idx])
    vol_20d_t3 = float(vol_20d.iloc[idx])
    dd_5d_t3 = float(dd_5d.iloc[idx])
    dd_20d_t3 = float(dd_20d.iloc[idx])

    # Panic volume: amount ratio > 2x AND 5d drop < -3%
    vol_20_avg = float(vol.rolling(20).mean().iloc[idx])
    vol_ratio = float(vol.iloc[idx]) / vol_20_avg if vol_20_avg > 0 else 1.0

    if not all(np.isfinite([c_t3, ma20_t3, ma60_t3, ret_20d_t3, vol_20d_t3, dd_5d_t3, dd_20d_t3])):
        return 'SIDEWAYS'

    # ---- Step 1: 4-state classification (matches detect_market_regime) ----
    # CRASH (highest priority, OR logic)
    crash_basic = dd_5d_t3 <= -0.08 or dd_20d_t3 <= -0.15
    crash_accel = vol_20d_t3 > 0.35 and dd_5d_t3 < -0.05
    crash_panic = vol_ratio > 2.0 and dd_5d_t3 < -0.03
    is_crash = crash_basic or crash_accel or crash_panic

    # BULL (4-condition AND)
    is_bull = (c_t3 > ma60_t3 and ma20_t3 > ma60_t3 and
               ret_20d_t3 >= 0.05 and vol_20d_t3 <= 0.30 and not is_crash)

    # BEAR (3-condition AND)
    is_bear = (c_t3 < ma60_t3 and ma20_t3 < ma60_t3 and
               ret_20d_t3 <= -0.05 and not is_crash)

    if is_crash:
        base_state = 'CRASH'
    elif is_bull:
        base_state = 'BULL'
    elif is_bear:
        base_state = 'BEAR'
    else:
        base_state = 'SIDEWAYS'

    # ---- Step 2: CHOPPY_BEAR overlay (matches detect_choppy_bear_vectorized) ----
    # 4 conditions, score >= 3 triggers CHOPPY_BEAR
    cum_ret_60d = c_t3 / float(close.iloc[idx-59]) - 1 if n >= (abs(idx)+60) else 0
    vol_60d = float(log_ret.rolling(60).std().iloc[idx] * np.sqrt(252)) if n >= (abs(idx)+60) else 1.0
    ma60_20d_ago = float(ma60.iloc[idx-19]) if n >= (abs(idx)+20) else float(ma60.iloc[idx])
    ma60_slope = (ma60_t3 - ma60_20d_ago) / (ma60_20d_ago + 1e-9)

    cond1 = cum_ret_60d < -0.05           # 60d cumulative return negative but not extreme
    cond2 = vol_60d < 0.18                 # low volatility
    cond3 = abs(ma60_slope) < 0.00025      # MA60 flat
    cond4 = ma20_t3 < ma60_t3              # MA20 below MA60

    choppy_score = sum(1 for c in [cond1, cond2, cond3, cond4] if c)
    is_choppy = choppy_score >= 3

    if is_choppy:
        return 'CHOPPY_BEAR'

    return base_state


# ==================== Dual Signal Computation (v6) ====================
def compute_signals_jq(stock_list, g, context):
    """
    v6 Dual Signal:
      Signal A (MR): 5d drop > 10% AND RSI6 < 20 (main)
                     5d drop > 8% AND RSI6 < 30 (secondary, BULL only)
      Signal B (Trend): MA20 breakthrough + volume confirmation
                      Only fills remaining slots when MR signals < needed
    Returns: {stock: (sig_type, rsi_value_or_99, priority)}
      priority 0=MR main, 1=MR secondary, 2=Trend
    """
    n = 30
    df_close = history(n, unit='1d', field='close', security_list=stock_list,
                       df=True, skip_paused=False, fq='pre')
    if df_close is None or df_close.empty:
        return {}

    signals = {}
    cd = get_current_data()

    for stock in stock_list:
        try:
            close_s = df_close[stock].dropna()
            if len(close_s) < 15:
                continue
        except KeyError:
            continue

        current_close = float(close_s.iloc[-1])
        prev_5_close = float(close_s.iloc[-6]) if len(close_s) >= 6 else current_close
        drop_5d = current_close / prev_5_close - 1

        rsi6 = calc_rsi(list(close_s), period=6)
        if not np.isfinite(rsi6) or not np.isfinite(drop_5d):
            continue

        # Signal A: Mean Reversion
        if drop_5d < -0.10 and rsi6 < 20:
            signals[stock] = ('main', rsi6)
        elif drop_5d < -0.08 and rsi6 < 30:
            if g.regime == 'BULL':
                signals[stock] = ('secondary', rsi6)

    return signals


def compute_trend_signals_jq(stock_list, g, context, exclude_stocks):
    """
    v6 Signal B: Trend Following (MA20 breakthrough + volume)
    Only used to fill remaining slots when MR signals are insufficient.
    Priority=2 (lower than MR main=0, secondary=1).
    """
    n = 25
    df_close = history(n, unit='1d', field='close', security_list=stock_list,
                       df=True, skip_paused=False, fq='pre')
    df_vol = history(n, unit='1d', field='volume', security_list=stock_list,
                     df=True, skip_paused=False, fq='pre')
    if df_close is None or df_close.empty:
        return []

    candidates = []
    cd = get_current_data()

    for stock in stock_list:
        if stock in exclude_stocks:
            continue
        try:
            close_s = df_close[stock].dropna()
            vol_s = df_vol[stock].dropna()
            if len(close_s) < 21 or len(vol_s) < 21:
                continue
        except KeyError:
            continue

        c = float(close_s.iloc[-1])        # today close
        c1 = float(close_s.iloc[-2])       # yesterday close
        ma20 = calc_sma(list(close_s), 20)
        v = float(vol_s.iloc[-1])          # today volume
        v20 = calc_sma(list(vol_s), 20)

        if not all(np.isfinite([c, c1, ma20, v, v20])):
            continue
        if v20 <= 0:
            continue

        # MA20 breakthrough + volume confirmation
        if c > ma20 and c1 < ma20 and v > PARAMS['trend_vol_mult'] * v20:
            # Basic filters
            try:
                d = cd[stock]
            except KeyError:
                continue
            if d.paused:
                continue
            if d.is_st:
                continue
            if d.high_limit > 0 and d.last_price >= d.high_limit:
                continue
            candidates.append((stock, c))

    return candidates


# ==================== Filter Functions ====================
def check_filters(stock, cd):
    """Comprehensive pre-trade filter"""
    try:
        d = cd[stock]
    except KeyError:
        return False, 'delisted'
    if d.paused:
        return False, 'paused'
    if d.is_st:
        return False, 'st'
    if d.high_limit > 0 and d.last_price >= d.high_limit:
        return False, 'limit_up'
    if d.low_limit > 0 and d.last_price <= d.low_limit:
        return False, 'limit_down'
    if d.last_price <= 0 or not np.isfinite(d.last_price):
        return False, 'invalid_price'
    return True, ''


def check_corp_action(stock):
    """Detect corporate action: single day pct_change > 15%"""
    try:
        h = attribute_history(stock, 1, '1d', ['pct_change'],
                               skip_paused=False, df=False, fq='pre')
        if h is not None and len(h['pct_change']) > 0:
            today_pct = h['pct_change'][-1]
            if today_pct is not None and not np.isnan(today_pct):
                return abs(today_pct) > PARAMS['corp_action_th']
    except Exception:
        pass
    return False


def check_recent_extreme(stock):
    """Pre-entry filter: skip stocks with > 15% daily move in last 5 days"""
    try:
        h = attribute_history(stock, 10, '1d', ['pct_change'],
                               skip_paused=False, df=False, fq='pre')
        if h is not None:
            recent = [x for x in h['pct_change']
                      if x is not None and not np.isnan(x)]
            if any(abs(x) > PARAMS['corp_action_th'] for x in recent[-5:]):
                return False
    except Exception:
        pass
    return True


# ==================== Initialize ====================
def initialize(context):
    """Strategy initialization (matching local mr_v2.py backtest_v2)"""
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

    # Costs: commission 0.025% (min 5) + stamp tax 0.1% (sell only)
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.00025,
        close_commission=0.00025,
        close_today_commission=0,
        min_commission=5
    ), type='stock')

    # Slippage: 0.1% each side = FixedSlippage(0.002) total
    set_slippage(FixedSlippage(0.002))

    log.set_level('order', 'error')

    # Load stock pool
    if STOCK_POOL == 'HS300':
        g.universe = [to_jq_code(c) for c in HS300_CODES_RAW
                      if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'CSI1000':
        g.universe = [to_jq_code(c) for c in CYB_STAR_50_CODES_RAW
                      if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'CYB_STAR_50':
        g.universe = [to_jq_code(c) for c in CYB_STAR_50_CODES_RAW
                      if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'ALL':
        all_raw = sorted(set(HS300_CODES_RAW) | set(CYB_STAR_50_CODES_RAW))
        g.universe = [to_jq_code(c) for c in all_raw
                      if c not in DISABLE_STOCK]
    else:
        raise ValueError('Unknown stock_pool: ' + STOCK_POOL)

    set_universe(g.universe)

    # Global state
    g.holdings = {}       # {stock: {entry_date, entry_price, shares, last_close, sig_type}}
    g.pending_buys = []   # [(stock, sig_date, sig_close)]
    g.pending_sells = []  # [(stock, ratio, reason, queue_date)]
    g.regime = 'SIDEWAYS'
    g.rebalance_count = 0

    # Schedule: daily tasks
    run_daily(before_market_open, '09:00')
    run_daily(execute_pending_orders, '09:30')
    run_daily(check_signals_and_queue_orders, '14:50')

    log.info('ATOS MR v6 Dual initialized: stock_pool=%s, universe=%d, trading=%d'
             % (STOCK_POOL, len(g.universe), len(TRADING_UNIVERSE_JQ)))


def before_market_open(context):
    """Pre-market: detect regime (lagged 3 days)"""
    g.regime = detect_regime_jq(context)


# ==================== T-day 14:50 Decision ====================
def check_signals_and_queue_orders(context):
    """T-day 14:50:
    1. Compute MR entry signals, queue pending_buys (T+1 09:30)
    2. Compute Trend signals to fill remaining slots (v6 new)
    3. Check exit signals for holdings, queue pending_sells
    4. Skip entry-day sells (T+1 lock)
    """
    portfolio = context.portfolio
    cd = get_current_data()
    cash = portfolio.available_cash
    total_value = portfolio.total_value

    regime_mult = PARAMS['regime_pos_mult'].get(g.regime, 0.5)
    log.info('[%s] regime=%s, holdings=%d, cash=%.0f, total=%.0f'
             % (context.current_dt.date(), g.regime, len(g.holdings),
                cash, total_value))

    # ===== 1. MR Entry Signals =====
    held_stocks = set(g.holdings.keys())
    pending_buy_stocks = set([s for s, _, _ in g.pending_buys])
    available_mr = [s for s in g.universe
                    if s not in held_stocks
                    and s not in pending_buy_stocks
                    and s in TRADING_UNIVERSE_JQ]

    signals = compute_signals_jq(available_mr, g, context)

    n_to_buy = PARAMS['max_positions'] - len(g.holdings) - len(g.pending_buys)

    # ===== 2. Queue MR buys =====
    mr_count = 0
    if g.regime != 'CRASH' and n_to_buy > 0:
        sorted_signals = sorted(signals.items(), key=lambda x: x[1][1])  # RSI asc
        for stock, (sig_type, rsi) in sorted_signals[:n_to_buy]:
            ok, reason = check_filters(stock, cd)
            if not ok:
                continue
            if not check_recent_extreme(stock):
                continue
            last_price = float(cd[stock].last_price)
            g.pending_buys.append((stock, context.current_dt.date(), last_price))
            mr_count += 1

    # ===== 3. Trend Signals (v6 new: fill remaining slots) =====
    remaining = n_to_buy - mr_count
    if g.regime != 'CRASH' and remaining > 0:
        exclude = held_stocks | pending_buy_stocks | set([s for s, _, _ in g.pending_buys])
        # Recompute pending_buy_stocks after MR additions
        pb_stocks = set([s for s, _, _ in g.pending_buys])
        exclude = held_stocks | pb_stocks
        available_trend = [s for s in g.universe
                           if s not in exclude
                           and s in TRADING_UNIVERSE_JQ]

        trend_candidates = compute_trend_signals_jq(available_trend, g, context, exclude)
        # Sort by close price (no RSI for trend signals)
        trend_candidates.sort(key=lambda x: x[1])
        for stock, _ in trend_candidates[:remaining]:
            if not check_recent_extreme(stock):
                continue
            last_price = float(cd[stock].last_price)
            g.pending_buys.append((stock, context.current_dt.date(), last_price))

    # ===== 4. Exit Signals =====
    cur_tp = PARAMS['take_profit']
    cur_sl = PARAMS['stop_loss']
    cur_hold = PARAMS['hold_days']
    today = context.current_dt.date()

    for stock, pos in list(g.holdings.items()):
        # T+1 lock: cannot sell on entry day
        if pos['entry_date'] == today:
            try:
                d = cd[stock]
                pos['last_close'] = float(d.last_price) if d.last_price > 0 else pos['entry_price']
            except KeyError:
                pos['last_close'] = pos['entry_price']
            continue

        try:
            d = cd[stock]
        except KeyError:
            continue
        cur_close = float(d.last_price)
        if cur_close <= 0:
            continue

        ret = (cur_close - pos['entry_price']) / pos['entry_price']
        days_held = np.busday_count(pos['entry_date'], today)

        # Corp action check
        is_corp = check_corp_action(stock)

        should_sell = False
        reason = ''
        if is_corp:
            should_sell = True
            reason = 'corp_action'
        elif ret >= cur_tp:
            should_sell = True
            reason = 'tp'
        elif ret <= cur_sl:
            should_sell = True
            reason = 'sl'
        elif days_held >= cur_hold:
            should_sell = True
            reason = 'time'
        elif g.regime == 'CRASH':
            should_sell = True
            reason = 'crash'

        if should_sell:
            already = any(p[0] == stock for p in g.pending_sells)
            if not already:
                g.pending_sells.append((stock, 1.0, reason, today))
            pos['last_close'] = cur_close

    g.rebalance_count += 1
    if g.rebalance_count % 60 == 0:
        log.info('[%s] signals=%d, trend=%d, pending_buys=%d, pending_sells=%d'
                 % (today, len(signals),
                    len(trend_candidates) if 'trend_candidates' in dir() else 0,
                    len(g.pending_buys), len(g.pending_sells)))


# ==================== T+1 09:30 Execution ====================
def execute_pending_orders(context):
    """T+1 09:30 execute pending buys and sells

    Sells: execute at T+1 open price
    Buys: execute at T+1 open price
    Limit-down/suspended: queue for up to 20 days, then force-sell at 5% discount
    """
    portfolio = context.portfolio
    cd = get_current_data()
    today = context.current_dt.date()
    cash = portfolio.available_cash
    total_value = portfolio.total_value
    regime_mult = PARAMS['regime_pos_mult'].get(g.regime, 0.5)

    # ===== 1. Process pending_sells =====
    new_pending_sells = []
    for stock, ratio, reason, queue_date in g.pending_sells:
        if stock not in g.holdings:
            continue
        try:
            d = cd[stock]
        except KeyError:
            continue
        if d.paused:
            new_pending_sells.append((stock, ratio, reason, queue_date))
            continue

        # Limit-down: queue
        if d.low_limit > 0 and d.last_price <= d.low_limit:
            days_pending = (today - queue_date).days
            if days_pending < PARAMS['max_pending_days']:
                new_pending_sells.append((stock, ratio, reason, queue_date))
                continue
            else:
                exec_price = float(d.day_open) * 0.95  # force sell at 5% discount
        else:
            exec_price = float(d.day_open)

        pos = g.holdings[stock]

        # Corporate action: use previous close as fair exit price
        if reason == 'corp_action':
            try:
                h = attribute_history(stock, 2, '1d', ['close'],
                                       skip_paused=False, df=False, fq='pre')
                if h is not None and len(h['close']) >= 2:
                    exec_price = float(h['close'][-2])
            except Exception:
                pass

        sell_shares = pos['shares']
        if sell_shares <= 0:
            del g.holdings[stock]
            continue
        if stock.startswith('688'):
            limit_price = min(exec_price * 0.995, 9999.99)
            try:
                order(stock, -sell_shares, LimitOrderStyle(limit_price))
            except Exception:
                new_pending_sells.append((stock, ratio, reason, queue_date))
                continue
        else:
            try:
                order(stock, -sell_shares)
            except Exception:
                new_pending_sells.append((stock, ratio, reason, queue_date))
                continue
        del g.holdings[stock]

    g.pending_sells = new_pending_sells

    # ===== 2. Process pending_buys =====
    new_pending_buys = []
    for stock, sig_date, sig_close in g.pending_buys:
        if stock in g.holdings:
            continue
        try:
            d = cd[stock]
        except KeyError:
            continue
        if d.paused:
            continue
        if d.high_limit > 0 and d.last_price >= d.high_limit:
            continue

        per_value = total_value * PARAMS['position_pct'] * regime_mult
        last_price = float(d.day_open)
        if last_price <= 0 or not np.isfinite(last_price):
            continue

        # Minimum affordability: need at least 100 shares worth of cash
        min_cost = last_price * 100 * 1.001
        if cash < min_cost:
            continue

        shares = int(per_value / (last_price * 1.001) / 100) * 100
        if shares < 100:
            shares = 100  # force minimum lot if per_value undershoots
        cost = shares * last_price * 1.001
        if cost > cash * 0.95:
            affordable = int(cash * 0.95 / (last_price * 1.001) / 100) * 100
            if affordable < 100:
                continue
            shares = affordable

        # Final safety net: double-check shares >= 100 and cost <= cash
        if shares < 100 or shares * last_price * 1.001 > cash * 0.95:
            continue

        if stock.startswith('688'):
            limit_price = min(last_price * 1.005, 9999.99)
            try:
                order(stock, shares, LimitOrderStyle(limit_price))
            except Exception:
                continue
        else:
            try:
                order(stock, shares)
            except Exception:
                continue

        g.holdings[stock] = {
            'entry_date': today,
            'entry_price': last_price,
            'shares': shares,
            'last_close': last_price,
            'sig_type': 'trend' if sig_date is None else 'mr',
        }

    g.pending_buys = new_pending_buys
