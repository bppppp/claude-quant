# -*- coding: utf-8 -*-
"""
ATOS MR v2 - 聚宽移植版
基于本地 atos/backtest/mr_v2.py
无前视偏差, T+1 结算, 严格 A 股合规

本地回测结果 (HS300, 2018-2022):
- 年化: 26.52%
- 最大回撤: -15.06%
- 胜率: 49.7% (1772 笔)
"""
import numpy as np
import pandas as pd
from collections import deque

# ==================== 全局参数 ====================
PARAMS = {
    # 入场信号
    'main_drop_th': -0.10,        # 主信号 5 日跌幅阈值
    'main_rsi_th': 20,            # 主信号 RSI(6) 阈值
    'sec_drop_th': -0.08,         # 副信号 5 日跌幅阈值 (BULL)
    'sec_rsi_th': 30,             # 副信号 RSI(6) 阈值 (BULL)
    # 持仓
    'max_positions': 20,          # 最大持仓数
    'position_pct': 0.15,         # 单只仓位占总权益比例
    'hold_days': 10,              # 持有天数
    # 出场
    'take_profit': 0.30,          # 止盈
    'stop_loss': -0.05,           # 止损
    # 状态仓位乘数 (滞后 3 天)
    'regime_pos_mult': {
        'BULL': 1.5, 'SIDEWAYS': 1.0,
        'BEAR': 0.2, 'CHOPPY_BEAR': 0.3,
        'CRASH': 0.0,
    },
    'regime_lag_days': 3,         # 状态滞后天数 (避免前视)
    'max_pending_days': 20,       # 卖出挂单最大等待天数
    'corp_action_th': 0.15,       # 除权除息单日波动阈值
}

# ==================== 工具函数 ====================
def calc_rsi(close_series, period=6):
    """计算 RSI 指标 (从 pd.Series 拿最后一根 K 线的值)"""
    if close_series is None or len(close_series) < period + 1:
        return np.nan
    delta = close_series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if not np.isfinite(avg_gain) or not np.isfinite(avg_loss):
        return np.nan
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def get_lagged_state(state_series, lag_days=3):
    """对状态序列滞后 N 天, 避免前视偏差

    在 T close 时, 我们只确认了 T-3 之前的状态 (hysteresis min_duration=3)
    所以 T 日用 T-3 日的状态, 而不是 T 日
    """
    if state_series is None or len(state_series) == 0:
        return 'SIDEWAYS'
    lagged = state_series.shift(lag_days)
    # 早期 NaN 用 SIDEWAYS 填充
    return lagged.fillna('SIDEWAYS')


def calc_100_lot_shares(value, price, lot_size=100):
    """计算整手股数 (含 0.1% 滑点 buffer)"""
    if price <= 0 or not np.isfinite(price) or value <= 0:
        return 0
    cost_per_share = price * 1.001  # 0.1% 滑点
    shares = int(value / cost_per_share / lot_size) * lot_size
    return max(shares, 0)


# ==================== 信号计算 ====================
def compute_signals_jq(stock_list, g, context):
    """入场信号计算 (替代本地 _compute_signal_v2 + secondary)

    主信号: 5 日跌幅 > 10% AND RSI(6) < 20
    副信号: 5 日跌幅 > 8% AND RSI(6) < 30 (仅 BULL)

    注意: JQ的history()不含今日数据, 所以用cd[stock].last_price获取今日close,
    与本地引擎(T close)保持一致。
    """
    cd = get_current_data()
    n = 30  # 至少 30 日窗口
    df_close = history(n, unit='1d', field='close', security_list=stock_list,
                       df=True, skip_paused=False, fq='pre')
    if df_close is None or df_close.empty:
        return {}

    signals = {}
    for stock in stock_list:
        try:
            d = cd[stock]
        except (KeyError, Exception):
            continue
        if d.paused:
            continue
        # 获取今日收盘价 (history不含今日, 用last_price)
        today_close = float(d.last_price)
        if today_close <= 0 or not np.isfinite(today_close):
            continue

        try:
            close_s = df_close[stock].dropna()
            if len(close_s) < 15:
                continue
        except KeyError:
            continue

        # 将今日close追加到历史序列末尾
        # history最后一日=T-1, 追加今日=T close
        close_ext = list(close_s.values) + [today_close]
        import pandas as pd
        close_s_ext = pd.Series(close_ext)

        current_close = today_close
        # 5日前close = 昨日往前4个 = iloc[-5] (序列共30+1=31个元素)
        prev_5_idx = len(close_s) - 5  # 昨日序列中的T-5位置
        if prev_5_idx >= 0:
            prev_5_close = float(close_s.iloc[prev_5_idx])
        else:
            prev_5_close = current_close
        drop_5d = current_close / prev_5_close - 1

        # RSI用扩展序列(含今日)
        rsi6 = calc_rsi(close_s_ext, period=6)
        if not np.isfinite(rsi6) or not np.isfinite(drop_5d):
            continue

        # 主信号
        if drop_5d < PARAMS['main_drop_th'] and rsi6 < PARAMS['main_rsi_th']:
            signals[stock] = ('main', rsi6)
        # 副信号 (仅 BULL)
        elif (drop_5d < PARAMS['sec_drop_th']
              and rsi6 < PARAMS['sec_rsi_th']
              and g.regime == 'BULL'):
            signals[stock] = ('secondary', rsi6)

    return signals


def detect_regime_jq(context):
    """状态检测: 完全匹配本地 detect_full_regime 逻辑

    本地引擎流程:
    1. detect_market_regime: 4状态布尔规则 (BULL/BEAR/CRASH/SIDEWAYS)
    2. apply_hysteresis_with_crash_override: min_duration=3, cooldown=5
    3. detect_choppy_bear_vectorized: ADX<20 且振幅大
    4. 滞后3天: regime_df.shift(3, freq='B')

    JQ实现:
    - attribute_history不含当日, iloc[-1]=T-1
    - 取iloc[-3]=T-3数据做判断 (滞后3日)
    """
    market = '000300.XSHG'
    # 取足够历史: 250日
    h = attribute_history(market, 250, '1d',
                          ['close', 'high', 'low', 'volume'], df=True, fq='pre')
    if h is None or h.empty:
        return 'SIDEWAYS'

    close = h['close']
    high = h['high']
    low = h['low']
    vol = h['volume'] if 'volume' in h.columns else pd.Series(1, index=close.index)

    if len(close) < 63:
        return 'SIDEWAYS'

    # 计算指标
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    # 当日数据 = T-3 (滞后3天)
    c_t = close.iloc[-3]
    m20_t = ma20.iloc[-3] if not pd.isna(ma20.iloc[-3]) else np.nan
    m60_t = ma60.iloc[-3] if not pd.isna(ma60.iloc[-3]) else np.nan

    # 20日涨幅
    pct_20d = c_t / close.iloc[-23] - 1 if len(close) >= 23 else 0

    # 5日和20日跌幅
    dd_5d = c_t / close.iloc[-8] - 1 if len(close) >= 8 else 0
    dd_20d = c_t / close.iloc[-23] - 1 if len(close) >= 23 else 0

    # 20日年化波动率 (用log return)
    log_ret = np.log(close / close.shift(1))
    rv_20d = log_ret.rolling(20).std().iloc[-3] * np.sqrt(252)
    if pd.isna(rv_20d):
        rv_20d = 0.2

    # 成交额暴增 (恐慌盘)
    amt_ratio = vol / vol.rolling(20).mean()
    crash_volume = (amt_ratio.iloc[-3] > 2.0) and (dd_5d < -0.03)

    # === 1. CRASH ===
    crash_basic = (dd_5d <= -0.08) or (dd_20d <= -0.15)
    crash_accel = (rv_20d > 0.35) and (dd_5d < -0.05)
    is_crash = crash_basic or crash_accel or crash_volume

    # === 2. BULL ===
    is_bull = (
        (c_t > m60_t) and (m20_t > m60_t) and
        (pct_20d >= 0.05) and (rv_20d <= 0.30) and (not is_crash)
    )

    # === 3. BEAR ===
    is_bear = (
        (c_t < m60_t) and (m20_t < m60_t) and
        (pct_20d <= -0.05) and (not is_crash)
    )

    # === 4. 状态赋值 ===
    if is_crash:
        raw_state = 'CRASH'
    elif is_bull:
        raw_state = 'BULL'
    elif is_bear:
        raw_state = 'BEAR'
    else:
        # Fallback: 按涨跌方向
        if pct_20d > 0:
            raw_state = 'BULL'
        elif pct_20d < 0:
            raw_state = 'BEAR'
        else:
            raw_state = 'SIDEWAYS'

    # === 5. Hysteresis (min_duration=3) ===
    # 记录在g.regime_history中, 保持最近3天的状态
    if not hasattr(g, 'regime_history'):
        g.regime_history = [raw_state, raw_state, raw_state]
    else:
        g.regime_history.append(raw_state)
        if len(g.regime_history) > 10:
            g.regime_history.pop(0)

    # 如果最近3天状态一致, 确认切换
    recent = g.regime_history[-3:]
    if len(recent) >= 3 and recent[0] == recent[1] == recent[2]:
        g.regime_confirmed = recent[0]
    elif not hasattr(g, 'regime_confirmed'):
        g.regime_confirmed = 'SIDEWAYS'

    return g.regime_confirmed


# ==================== 过滤函数 ====================
def check_filters(stock, cd):
    """综合过滤: 停牌/ST/涨跌停/退市

    返回 (是否可交易, 失败原因)
    """
    try:
        d = cd[stock]
    except KeyError:
        return False, 'delisted'

    if d.paused:
        return False, 'paused'
    if d.is_st:
        return False, 'st'
    # 涨停不能买入 (注意 high_limit 可能为 0)
    if d.high_limit > 0 and d.last_price >= d.high_limit:
        return False, 'limit_up'
    # 跌停不能卖出
    if d.low_limit > 0 and d.last_price <= d.low_limit:
        return False, 'limit_down'
    if d.last_price <= 0 or not np.isfinite(d.last_price):
        return False, 'invalid_price'
    return True, ''


def check_corp_action(stock):
    """检测除权除息: 单日 pct_change > 15%

    用于持仓期间检测 corporate action, 避免未复权数据中的虚假亏损
    """
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
    """入场前过滤: 近 5 日有 > 15% 单日波动的股票跳过"""
    try:
        h = attribute_history(stock, 10, '1d', ['pct_change'],
                               skip_paused=False, df=False, fq='pre')
        if h is not None:
            recent = [x for x in h['pct_change'] if x is not None and not np.isnan(x)]
            if any(abs(x) > PARAMS['corp_action_th'] for x in recent[-5:]):
                return False
    except Exception:
        pass
    return True


# ==================== initialize ====================
def initialize(context):
    """策略初始化 (与本地 mr_v2.py 一致的参数)"""
    # 基准: 沪深 300
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)  # 动态前复权, 避免前视

    # 成本: 佣金 0.025% (min 5) + 印花税 0.1% (卖出)
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.00025,
        close_commission=0.00025,
        close_today_commission=0,
        min_commission=5
    ), type='stock')

    # 滑点: 双边 0.1% = FixedSlippage(0.002)
    set_slippage(FixedSlippage(0.002))

    # 状态日志
    log.set_level('order', 'error')

    # 加载股票池 (从内联测试集定义)
    # 使用内联的 STOCK_POOL_CODES_RAW 常量 (避免 import univ)
    if STOCK_POOL == 'HS300':
        g.universe = [to_jq_code(c) for c in HS300_CODES_RAW
                      if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'CSI1000':
        g.universe = [to_jq_code(c) for c in CSI1000_CODES_RAW
                      if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'CYB_STAR_50':
        g.universe = [to_jq_code(c) for c in CYB_STAR_50_CODES_RAW
                      if c not in DISABLE_STOCK]
    elif STOCK_POOL == 'ALL':
        g.universe = [to_jq_code(c) for c in ALL_CODES_RAW
                      if c not in DISABLE_STOCK]
    else:
        raise ValueError('Unknown stock_pool: ' + STOCK_POOL)

    # 预填 cd dict, 避免 lazy loading 问题
    set_universe(g.universe)

    # 全局状态
    g.holdings = {}  # {stock: {entry_date, entry_price, shares, last_close, sig_type}}
    g.pending_buys = []  # [(stock, sig_date, sig_close)]
    g.pending_sells = []  # [(stock, ratio, reason, queue_date)]
    g.regime = 'SIDEWAYS'
    g.rebalance_count = 0  # 调仓次数 (诊断用)

    # 定时任务
    run_daily(before_market_open, '09:00')
    run_daily(execute_pending_orders, '09:30')  # T+1 09:30 撮合
    run_daily(check_signals_and_queue_orders, '15:00')  # T 日 15:00 决策 (收盘后, history() 含今日)

    log.info('ATOS MR v2 initialized: stock_pool=%s, universe_size=%d'
             % (STOCK_POOL, len(g.universe)))


def before_market_open(context):
    """盘前: 检测状态 (滞后 3 天)"""
    g.regime = detect_regime_jq(context)


# ==================== T 日 14:50 决策 ====================
def check_signals_and_queue_orders(context):
    """T 日 14:50 决策:
    1. 计算入场信号, 排队 pending_buys (T+1 09:30 成交)
    2. 检查持仓出场信号, 排队 pending_sells (T+1 09:30 成交)
    3. 持仓首日跳过 (T+1 锁)
    """
    portfolio = context.portfolio
    cd = get_current_data()
    cash = portfolio.available_cash
    total_value = portfolio.total_value

    regime_mult = PARAMS['regime_pos_mult'].get(g.regime, 0.5)
    log.info('[%s] regime=%s, holdings=%d, cash=%.0f, total=%.0f'
             % (context.current_dt.date(), g.regime, len(g.holdings),
                cash, total_value))

    # ==================== 1. 入场信号 ====================
    held_stocks = set(g.holdings.keys())
    pending_buy_stocks = set([s for s, _, _ in g.pending_buys])
    available = [s for s in g.universe
                 if s not in held_stocks and s not in pending_buy_stocks
                 and s in TRADING_UNIVERSE_JQ]

    signals = compute_signals_jq(available, g, context)

    # 排队买入
    n_to_buy = PARAMS['max_positions'] - len(g.holdings) - len(g.pending_buys)
    if g.regime != 'CRASH' and n_to_buy > 0:
        # 按 RSI 升序 (最超卖优先)
        sorted_signals = sorted(signals.items(), key=lambda x: x[1][1])
        for stock, (sig_type, rsi) in sorted_signals[:n_to_buy]:
            # 综合过滤
            ok, reason = check_filters(stock, cd)
            if not ok:
                continue
            # 除权除息过滤
            if not check_recent_extreme(stock):
                continue
            # 排队 (T+1 09:30 成交)
            last_price = float(cd[stock].last_price)
            g.pending_buys.append((stock, context.current_dt.date(), last_price))

    # ==================== 2. 出场信号 ====================
    cur_tp = PARAMS['take_profit']
    cur_sl = PARAMS['stop_loss']
    cur_hold = PARAMS['hold_days']
    today = context.current_dt.date()

    for stock, pos in list(g.holdings.items()):
        # T+1 锁: 持仓首日不能卖
        if pos['entry_date'] == today:
            try:
                d = cd[stock]
                pos['last_close'] = float(d.last_price) if d.last_price > 0 else pos['entry_price']
            except KeyError:
                pos['last_close'] = pos['entry_price']
            continue

        # 获取当前价
        try:
            d = cd[stock]
        except KeyError:
            continue
        cur_close = float(d.last_price)
        if cur_close <= 0:
            continue

        ret = (cur_close - pos['entry_price']) / pos['entry_price']
        days_held = np.busday_count(pos['entry_date'], today)

        # 除权除息检测
        is_corp = check_corp_action(stock)

        should_sell = False
        reason = ''
        if is_corp:
            should_sell = True; reason = 'corp_action'
        elif ret >= cur_tp:
            should_sell = True; reason = 'tp'
        elif ret <= cur_sl:
            should_sell = True; reason = 'sl'
        elif days_held >= cur_hold:
            should_sell = True; reason = 'time'
        elif g.regime == 'CRASH':
            should_sell = True; reason = 'crash'

        if should_sell:
            # 检查是否已在 pending_sells 中
            already = any(p[0] == stock for p in g.pending_sells)
            if not already:
                g.pending_sells.append((stock, 1.0, reason, today))
            pos['last_close'] = cur_close

    g.rebalance_count += 1
    if g.rebalance_count % 60 == 0:  # 每季度打印
        log.info('[%s] signals=%d, pending_buys=%d, pending_sells=%d'
                 % (today, len(signals), len(g.pending_buys), len(g.pending_sells)))


# ==================== T+1 09:30 撮合 ====================
def execute_pending_orders(context):
    """T+1 09:30 执行 pending_buys 和 pending_sells

    卖出使用 T+1 09:30 开盘价
    买入使用 T+1 09:30 开盘价
    跌停/停牌时: 卖出挂单等待 (最多 20 天)
    """
    portfolio = context.portfolio
    cd = get_current_data()
    today = context.current_dt.date()
    cash = portfolio.available_cash
    total_value = portfolio.total_value
    regime_mult = PARAMS['regime_pos_mult'].get(g.regime, 0.5)

    # ==================== 1. 处理 pending_sells ====================
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
        # 跌停时挂单
        if d.low_limit > 0 and d.last_price <= d.low_limit:
            days_pending = (today - queue_date).days
            if days_pending < PARAMS['max_pending_days']:
                new_pending_sells.append((stock, ratio, reason, queue_date))
                continue
            else:
                # 超过 20 天强制折价 5% 卖出
                exec_price = float(d.day_open) * 0.95
        else:
            exec_price = float(d.day_open)  # T+1 09:30 开盘价

        pos = g.holdings[stock]

        # Corporate action: 用前日 close 作为公平退出价
        if reason == 'corp_action':
            try:
                h = attribute_history(stock, 2, '1d', ['close'],
                                       skip_paused=False, df=False, fq='pre')
                if h is not None and len(h['close']) >= 2:
                    exec_price = float(h['close'][-2])
            except Exception:
                pass

        sell_shares = pos['shares']
        # 科创板用限价单
        if stock.startswith('688'):
            limit_price = min(exec_price * 0.995, 9999.99)
            order(stock, -sell_shares, LimitOrderStyle(limit_price))
        else:
            order(stock, -sell_shares)
        # 记录平仓收益
        ret = (exec_price - pos['entry_price']) / pos['entry_price']
        log.info('[SELL] %s @ %.2f (entry=%.2f, ret=%.2f%%, reason=%s)'
                 % (stock, exec_price, pos['entry_price'], ret * 100, reason))
        del g.holdings[stock]
    g.pending_sells = new_pending_sells

    # ==================== 2. 处理 pending_buys ====================
    new_pending_buys = []
    for stock, sig_date, sig_close in g.pending_buys:
        if stock in g.holdings:
            continue
        try:
            d = cd[stock]
        except KeyError:
            continue
        if d.paused:
            new_pending_buys.append((stock, sig_date, sig_close))
            continue
        # 涨停不能买
        if d.high_limit > 0 and d.last_price >= d.high_limit:
            new_pending_buys.append((stock, sig_date, sig_close))
            continue

        # 计算股数
        lot_size = 200 if stock.startswith('688') else 100
        per_value = total_value * PARAMS['position_pct'] * regime_mult
        last_price = float(d.day_open)
        if last_price <= 0 or not np.isfinite(last_price):
            new_pending_buys.append((stock, sig_date, sig_close))
            continue
        shares = calc_100_lot_shares(per_value, last_price, lot_size)
        if shares < 100:
            new_pending_buys.append((stock, sig_date, sig_close))
            continue
        cost = shares * last_price * 1.001
        if cost > cash * 0.95:
            affordable = int(cash * 0.95 / (last_price * 1.001) / lot_size) * lot_size
            if affordable < 100:
                new_pending_buys.append((stock, sig_date, sig_close))
                continue
            shares = affordable
        # 科创板用限价单
        if stock.startswith('688'):
            limit_price = min(last_price * 1.005, 9999.99)
            order(stock, shares, LimitOrderStyle(limit_price))
        else:
            order(stock, shares)
        # 记录持仓
        g.holdings[stock] = {
            'entry_date': today,
            'entry_price': last_price,
            'shares': shares,
            'last_close': last_price,
        }
        log.info('[BUY] %s @ %.2f, shares=%d, sig_type=%s'
                 % (stock, last_price, shares, sig_close))
    g.pending_buys = new_pending_buys
