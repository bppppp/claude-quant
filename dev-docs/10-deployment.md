# 10 - 部署与监控

## 10.1 职责

策略从开发到上线的最后一公里：
- 调度系统
- 实时监控
- 告警通知
- 应急处理

## 10.2 模块结构

```
monitoring/
├── __init__.py
├── dashboard.py          # Streamlit 看板
├── alerts.py             # 告警（钉钉/飞书/微信）
└── scheduler.py          # 调度

deploy/
├── docker-compose.yml
├── Dockerfile
├── cron/
│   ├── update_data.sh
│   ├── daily_signal.sh
│   └── weekly_report.sh
└── nginx.conf
```

## 10.3 调度系统

### 10.3.1 每日任务时间表（修复 B9-01: 与 §10.11 一致）

| 时间 | 任务 |
|---|---|
| 16:00 | 拉取当日收盘数据（akshare/baostock） |
| 17:00 | 预计算所有指标 + 因子（增量） |
| 17:30 | 计算大盘状态 + 4 状态识别 |
| 18:00 | 生成次日选股清单（横截面日榜） |
| 18:30 | 生成交易信号（6 买点 + 4 卖点） |
| 19:00 | 推送次日交易计划 + 日报 |

### 10.3.2 cron 配置（修复 B9-02: 模块名统一）

```bash
# /etc/cron.d/atos

# 每日 16:00 - 更新数据（修复 B9-03: 金玥数据已预存，此处是增量 baostock）
0 16 * * 1-5 atos /app/scripts/precompute_update_data.sh

# 每日 17:00 - 预计算所有指标和因子
0 17 * * 1-5 atos /app/scripts/precompute_indicators.sh

# 每日 17:30 - 大盘状态 + 4 状态识别
30 17 * * 1-5 atos /app/scripts/precompute_regime.sh

# 每日 18:00 - 生成次日选股清单
0 18 * * 1-5 atos /app/scripts/precompute_selection.sh

# 每日 18:30 - 生成交易信号
30 18 * * 1-5 atos /app/scripts/daily_signal.sh

# 每周日 22:00 - 周报
0 22 * * 0 atos /app/scripts/weekly_report.sh

# 每月 1 日 02:00 - 月度回测
0 2 1 * * atos /app/scripts/monthly_backtest.sh
```

### 10.3.3 Airflow 备选

```python
# dags/atos_daily.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'atos',
    'retries': 2,
    'retry_delay': timedelta(minutes=5)
}

dag = DAG('atos_daily', default_args=default_args,
           schedule_interval='0 18 * * 1-5',
           start_date=datetime(2026, 1, 1))

update_data = PythonOperator(
    task_id='update_data',
    python_callable=update_all_data,
    dag=dag
)

generate_signals = PythonOperator(
    task_id='generate_signals',
    python_callable=daily_signal_generation,
    dag=dag
)

update_data >> generate_signals
```

## 10.4 每日信号脚本

```bash
#!/bin/bash
# scripts/daily_signal.sh

set -e

cd /app

echo "[$(date)] Starting daily signal generation..."

# 1. 更新数据（修复 B9-02/B9-03: 适配金玥数据本地 + 增量大盘 baostock）
python -c "
import sys; sys.path.insert(0, '.')
from data.benchmark_loader import load_benchmark
from data.loader import load_stock_series
from indicators.pipeline import calc_indicators_with_cache

# 加载大盘 10 指数
for name in ['hs300', 'sse_index', 'sse50', 'csi500', 'csi1000',
             'csi_consumer', 'csi_pharma', 'csi_finance',
             'chinext', 'szse_component']:
    df = load_benchmark(name)
    df = calc_indicators_with_cache(name, df=df, force_recalc=False)
    print(f'  {name}: {len(df)} rows')
"

# 2. 生成信号（修复 [v8.3] E34: 全 A 选股而非单标的）
python -c "
import sys; sys.path.insert(0, '.')
import pandas as pd
from data.benchmark_loader import load_benchmark
from data.loader import load_stock_series
from data.universe import get_universe  # 修复 E34: 加载全 A 股票池
from indicators.pipeline import calc_indicators_with_cache
from regime import detect_full_regime
from config import load_config
from signals import generate_daily_signals
from selection.selector import StockSelector
from datetime import datetime

config = load_config()

# 2.1 加载大盘数据（沪深 300，状态识别用）
market_df = load_benchmark('hs300')
market_df = calc_indicators_with_cache('hs300', df=market_df, force_recalc=False)

# 2.2 加载候选股票池（修复 E34: 全 A 而非单标的）
universe = get_universe('HS300')  # 或 'CSI1000'、'all_A'
stock_data = {}
for symbol in universe[:200]:  # Top 200 流动性优先
    try:
        df = load_stock_series(symbol, start='2020-01-01')
        df = calc_indicators_with_cache(symbol, df=df, force_recalc=False)
        stock_data[symbol] = df
    except FileNotFoundError:
        continue
print(f'Loaded {len(stock_data)} stocks')

# 2.3 状态识别（修复 [v8.4] A42: 先调用 detect_full_regime 才能用 regime_df）
regime_df = detect_full_regime(market_df, config)
today = market_df.index[-1]
regime = regime_df.loc[today, 'effective_state']
print(f'Current regime: {regime}')

# 2.4 多标的选择 + 信号生成（修复 E34）
selector = StockSelector(config)
top_stocks = selector.select(date=today, stock_data=stock_data,
                              state=regime, top_n=10)
print(f'Top stocks: {top_stocks}')

signals = {'buy': top_stocks, 'sell': []}
print(f'Signals: {signals}')
"

# 3. 推送通知
python -c "
import sys; sys.path.insert(0, '.')
from monitoring.alerts import send_daily_report
from datetime import datetime

send_daily_report(datetime.now())
"

echo "[$(date)] Daily signal generation complete."
```

## 10.5 告警系统

```python
# monitoring/alerts.py
import requests
import json
import logging
from enum import Enum
from typing import Optional


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    DINGTALK = "dingtalk"
    WECHAT = "wechat"
    FEISHU = "feishu"
    EMAIL = "email"


class AlertManager:
    """告警管理器"""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("atos")

    def send(self, level: AlertLevel, title: str, message: str,
              channel: AlertChannel = AlertChannel.DINGTALK):
        """发送告警"""
        # 1. 记录日志
        log_method = {
            AlertLevel.INFO: self.logger.info,
            AlertLevel.WARNING: self.logger.warning,
            AlertLevel.CRITICAL: self.logger.error
        }
        log_method[level](f"[{level.value}] {title}: {message}")

        # 2. 发送通知
        if level == AlertLevel.CRITICAL:
            self._send_critical(title, message, channel)
        elif level == AlertLevel.WARNING:
            self._send_warning(title, message, channel)
        # INFO 仅记录日志

    def _send_critical(self, title, message, channel):
        """严重告警 - 多渠道（修复 [v8.3] C30）

        修复说明：
        - 旧版 for ch in AlertChannel 会同时发 4 个渠道，导致群组接收重复。
        - 新版按优先级发送（钉钉 → 飞书 → 微信 → 邮件），任一即时报渠道成功则停。
        - 邮件作为兜底（即使即时通讯失败也能到达）。
        """
        priority_order = [
            AlertChannel.DINGTALK,
            AlertChannel.FEISHU,
            AlertChannel.WECHAT,
            AlertChannel.EMAIL,  # 兜底
        ]
        for ch in priority_order:
            try:
                self._send_to_channel(ch, title, message, AlertLevel.CRITICAL)
                # 即时通讯渠道成功则不继续（避免重复打扰）
                if ch in (AlertChannel.DINGTALK, AlertChannel.FEISHU, AlertChannel.WECHAT):
                    return
            except Exception as e:
                self.logger.error(f"Alert send via {ch} failed: {e}")
                continue

    def _send_warning(self, title, message, channel):
        """警告"""
        self._send_to_channel(channel, title, message, AlertLevel.WARNING)

    def _send_to_channel(self, channel, title, message, level):
        """发送具体渠道"""
        try:
            if channel == AlertChannel.DINGTALK:
                self._send_dingtalk(title, message, level)
            elif channel == AlertChannel.WECHAT:
                self._send_wechat(title, message, level)
            elif channel == AlertChannel.FEISHU:
                self._send_feishu(title, message, level)
            elif channel == AlertChannel.EMAIL:
                self._send_email(title, message, level)
        except Exception as e:
            self.logger.error(f"Alert send failed: {e}")

    def _send_dingtalk(self, title, message, level):
        """钉钉机器人"""
        webhook = self.config.dingtalk_webhook
        if not webhook:
            return

        text = f"### {title}\n\n**级别**: {level.value}\n\n{message}"
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text}
        }
        requests.post(webhook, json=payload, timeout=5)

    def _send_wechat(self, title, message, level):
        """企业微信机器人"""
        webhook = self.config.wechat_webhook
        if not webhook:
            return

        text = f"{title}\n{message}"
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": text}
        }
        requests.post(webhook, json=payload, timeout=5)

    def _send_feishu(self, title, message, level):
        """飞书机器人"""
        webhook = self.config.feishu_webhook
        if not webhook:
            return

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title}
                },
                "elements": [{
                    "tag": "markdown",
                    "content": f"**级别**: {level.value}\n\n{message}"
                }]
            }
        }
        requests.post(webhook, json=payload, timeout=5)

    def _send_email(self, title, message, level):
        """邮件"""
        import smtplib
        from email.mime.text import MIMEText

        if not self.config.email_smtp:
            return

        msg = MIMEText(message, 'plain', 'utf-8')
        msg['Subject'] = f"[ATOS][{level.value}] {title}"
        msg['From'] = self.config.email_from
        msg['To'] = ', '.join(self.config.email_to)

        with smtplib.SMTP(self.config.email_smtp) as server:
            server.send_message(msg)
```

## 10.6 告警规则

```python
# monitoring/alert_rules.py
from monitoring.alerts import AlertManager, AlertLevel, AlertChannel


def check_alerts(equity: float, drawdown: float, regime: str,
                  alert_mgr: AlertManager):
    """检查告警规则"""
    # 净值回撤 > 5%
    if drawdown < -0.05:
        alert_mgr.send(
            AlertLevel.WARNING,
            "净值回撤警告",
            f"当前回撤 {drawdown:.2%}，超过 5% 阈值",
            AlertChannel.DINGTALK
        )

    # 净值回撤 > 10%
    if drawdown < -0.10:
        alert_mgr.send(
            AlertLevel.CRITICAL,
            "净值回撤严重",
            f"当前回撤 {drawdown:.2%}，触发降仓",
            AlertChannel.DINGTALK
        )

    # CRASH 状态
    if regime == "CRASH":
        alert_mgr.send(
            AlertLevel.CRITICAL,
            "CRASH 状态触发",
            "已强制清仓，停止新开仓",
            AlertChannel.DINGTALK
        )

    # 单日亏损 > 2%
    # ...
```

## 10.6.1 每日报告发送（修复 C29）

```python
# monitoring/alerts.py 中添加

def send_daily_report(
    report_date: pd.Timestamp,
    regime: str = None,
    equity: float = None,
    daily_pnl: float = None,
    signals: dict = None,
    channel: AlertChannel = AlertChannel.DINGTALK,
    config = None  # 修复 [v8.4] A44: 必须传入真实 config，否则 webhook 拿不到
):
    """发送每日报告（修复 [v8.4] A44: 必须传真实 config）

    Args:
        report_date: 报告日期
        regime: 当前市场状态
        equity: 当日净值
        daily_pnl: 当日盈亏
        signals: 当日信号
        channel: 发送渠道
        config: **必须传入** StrategyConfig（含 dingtalk_webhook 等）
    """
    if config is None:
        raise ValueError(
            "send_daily_report 必须传入 config 参数（含 webhook 配置），"
            "不能传 {} 或 None"
        )

    # 构建报告
    text = f"""### 每日交易报告 ({report_date.strftime('%Y-%m-%d')})

**市场状态**: {regime or 'N/A'}
**当日净值**: {equity:,.0f} (盈亏: {daily_pnl:+,.0f})
**当日信号**:
- 买入: {signals.get('buy', [])}
- 卖出: {signals.get('sell', [])}
"""
    # 发送（修复 A44: 用真实 config）
    alert_mgr = AlertManager(config=config)
    alert_mgr._send_to_channel(
        channel,
        title="ATOS 每日报告",
        message=text,
        level=AlertLevel.INFO
    )
```

## 10.7 Streamlit 监控看板

```python
# monitoring/dashboard.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data.storage import ParquetStorage
from datetime import datetime, timedelta


def render_dashboard():
    """Streamlit 监控看板（修复 E36: 支持 mock/真实数据切换）"""
    st.set_page_config(
        page_title="ATOS Monitor",
        page_icon="📈",
        layout="wide"
    )

    st.title("📈 ATOS 策略实时监控")

    # 修复 E36: 数据源切换
    use_mock = st.sidebar.checkbox("使用 Mock 数据（演示模式）", value=False)
    if use_mock:
        metrics = _get_mock_metrics()
        equity_df = _get_mock_equity()
    else:
        metrics = _get_real_metrics()
        equity_df = _get_real_equity()

    # 1. 关键指标
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("今日净值", f"{metrics['equity']:,.0f}", f"{metrics['daily_pnl']:+,.0f}")
    with col2:
        st.metric("最大回撤", f"{metrics['max_dd']:.2%}", f"{metrics['dd_change']:+.2%}")
    with col3:
        st.metric("夏普比率", "1.35", "+0.05")
    with col4:
        st.metric("当前状态", "BULL", "BULL")

    # 2. 净值曲线
    st.subheader("净值曲线")
    equity_df = load_equity_curve()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df.index, y=equity_df["equity"],
        mode="lines", name="策略"
    ))
    fig.add_trace(go.Scatter(
        x=equity_df.index, y=equity_df["benchmark"],
        mode="lines", name="沪深300"
    ))
    st.plotly_chart(fig, use_container_width=True)

    # 3. 回撤
    st.subheader("回撤")
    cummax = equity_df["equity"].cummax()
    dd = (equity_df["equity"] - cummax) / cummax
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=dd.index, y=dd.values,
        fill="tozeroy", mode="lines", name="回撤"
    ))
    st.plotly_chart(fig_dd, use_container_width=True)

    # 4. 当前持仓
    st.subheader("当前持仓")
    positions_df = load_current_positions()
    st.dataframe(positions_df)

    # 5. 状态历史
    st.subheader("状态历史")
    regime_df = load_regime_history()
    fig_r = go.Figure()
    fig_r.add_trace(go.Scatter(
        x=regime_df.index, y=regime_df["state"],
        mode="lines+markers", name="状态"
    ))
    st.plotly_chart(fig_r, use_container_width=True)

    # 6. 因子表现
    st.subheader("因子 IC")
    ic_df = load_factor_ic()
    st.line_chart(ic_df)


# 修复 E36: 数据加载辅助函数
def _get_mock_metrics() -> dict:
    """Mock 数据（演示用）"""
    return {
        "equity": 1_050_000,
        "daily_pnl": 5_000,
        "max_dd": -0.052,
        "dd_change": -0.003,
        "sharpe": 1.35,
        "sharpe_change": 0.05,
        "regime": "BULL"
    }


def _get_real_metrics() -> dict:
    """真实数据加载"""
    from pathlib import Path
    import json
    metrics_path = Path("reports/latest_metrics.json")
    if metrics_path.exists():
        with open(metrics_path) as f:
            return json.load(f)
    return _get_mock_metrics()


def _get_mock_equity() -> pd.DataFrame:
    """Mock 净值曲线"""
    import numpy as np
    np.random.seed(42)
    n = 252
    equity = 1_000_000 * np.cumprod(1 + np.random.randn(n) * 0.01 + 0.0003)
    return pd.DataFrame({
        "equity": equity,
        "benchmark": equity * (1 + np.random.randn(n).cumsum() * 0.005)
    }, index=pd.date_range("2024-01-01", periods=n))


def _get_real_equity() -> pd.DataFrame:
    """真实净值曲线加载"""
    path = Path("reports/equity_curve.csv")
    if path.exists():
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        # 尝试加载基准
        bench_path = Path("reports/benchmark_curve.csv")
        if bench_path.exists():
            df["benchmark"] = pd.read_csv(bench_path, index_col=0)["equity"]
        return df
    return _get_mock_equity()


def load_equity_curve():
    """加载净值曲线"""
    return pd.read_csv("reports/equity_curve.csv", index_col=0, parse_dates=True)


def load_current_positions():
    """加载当前持仓"""
    return pd.read_csv("reports/current_positions.csv")


def load_regime_history():
    """加载状态历史"""
    return pd.read_csv("reports/regime_history.csv", index_col=0, parse_dates=True)


def load_factor_ic():
    """加载因子 IC"""
    return pd.read_csv("reports/factor_ic.csv", index_col=0, parse_dates=True)


if __name__ == "__main__":
    render_dashboard()
```

## 10.8 Docker 部署

```dockerfile
# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 默认命令
CMD ["python", "run.py"]
```

```yaml
# docker-compose.yml
version: '3'

services:
  atos:
    build: .
    container_name: atos
    restart: unless-stopped
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports
      - ./config:/app/config
    environment:
      - TZ=Asia/Shanghai
    command: >
      sh -c "
        python scripts/update_data.sh &&
        python scripts/daily_signal.sh &&
        streamlit run monitoring/dashboard.py --server.port 8501
      "

  scheduler:
    image: atos
    container_name: atos-scheduler
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports
    command: >
      sh -c "
        echo '0 18 * * 1-5 python /app/scripts/daily_signal.sh' | crontab - &&
        crond -f
      "
```

## 10.9 应急处理

```python
# monitoring/emergency.py
from monitoring.alerts import AlertManager, AlertLevel, AlertChannel
import logging

logger = logging.getLogger("atos")


class EmergencyHandler:
    """应急处理器"""

    def __init__(self, alert_mgr: AlertManager):
        self.alert_mgr = alert_mgr

    def handle_market_crash(self, context: dict):
        """处理市场崩盘"""
        logger.critical(f"Market crash detected: {context}")
        self.alert_mgr.send(
            AlertLevel.CRITICAL,
            "市场崩盘告警",
            f"大盘 {context.get('drawdown', 'N/A')} 跌幅，触发熔断",
            AlertChannel.DINGTALK
        )
        # 暂停所有交易
        # self.pause_all_trading()

    def handle_data_error(self, error: Exception, context: dict):
        """处理数据错误"""
        logger.error(f"Data error: {error}, context: {context}")
        self.alert_mgr.send(
            AlertLevel.CRITICAL,
            "数据错误",
            f"无法获取 {context.get('symbol', 'N/A')} 数据，错误：{error}",
            AlertChannel.DINGTALK
        )

    def handle_system_error(self, error: Exception):
        """处理系统错误"""
        logger.exception(f"System error: {error}")
        self.alert_mgr.send(
            AlertLevel.CRITICAL,
            "系统错误",
            f"ATOS 系统异常：{str(error)[:200]}",
            AlertChannel.DINGTALK
        )
```

## 10.10 监控指标清单

| 指标 | 阈值 | 等级 |
|---|---|---|
| 净值回撤 > 5% | 黄 | 通知 |
| 净值回撤 > 10% | 红 | 短信 + 降仓 |
| 净值回撤 > 15% | 红 | 暂停 5 日 |
| 净值回撤 > 20% | 红 | 永久暂停 |
| 单日亏损 > 2% | 黄 | 通知 |
| 单日亏损 > 5% | 红 | 短信 |
| CRASH 状态 | 红 | 短信 + 强平 |
| 黑天鹅 | 红 | 立即清仓 |
| 数据缺失 | 红 | 暂停信号 |
| 系统错误 | 红 | 暂停策略 |

## 10.11 预计算调度（衔接 12-precompute.md）

```bash
# /etc/cron.d/atos-precompute

# 每日 16:00 增量更新原始数据
0 16 * * 1-5 atos /app/scripts/precompute_update_data.sh

# 每日 17:00 预计算所有指标和因子
0 17 * * 1-5 atos /app/scripts/precompute_indicators.sh

# 每日 17:30 计算大盘状态 + 当日全市场横截面
30 17 * * 1-5 atos /app/scripts/precompute_regime.sh

# 每日 18:00 生成次日选股清单
0 18 * * 1-5 atos /app/scripts/precompute_selection.sh

# 每周日 22:00 全量校验 + 重建损坏缓存
0 22 * * 0 atos /app/scripts/precompute_weekly_check.sh
```

### 10.11.1 预计算脚本示例

```bash
#!/bin/bash
# scripts/precompute_indicators.sh

set -e
cd /app

echo "[$(date)] Starting indicator precompute..."

python -m precompute.run --mode=incremental \
    --workers=4 \
    --universe=HS300+CSI1000 \
    --output=logs/precompute_$(date +%Y%m%d).log

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "Precompute failed!" | /app/scripts/send_alert.sh "ATOS预计算失败" CRITICAL
    exit $EXIT_CODE
fi

echo "[$(date)] Indicator precompute complete."
```

### 10.11.2 首次全量预计算

```bash
#!/bin/bash
# scripts/precompute_first_time.sh
# 首次部署时执行（全量预计算，约 1-2 小时）

set -e
cd /app

echo "[$(date)] First-time full precompute starting..."

# 1. 全量下载原始数据
python -m data.downloader --all --universe=all_A

# 2. 全量计算（4 worker，约 30 分钟）
python -m precompute.run --mode=full --workers=4

# 3. 计算大盘状态
python -m precompute.regime --market=000300

# 4. 生成历史日榜（10 年 × 2500 个文件，约 1 小时）
python -m precompute.selection --history

echo "[$(date)] Full precompute complete."
```

## 10.12 容量估算

| 数据 | 大小 | 备注 |
|---|---|---|
| 原始 K 线 | ~10 GB | 5841 只 × 10 年 |
| 预计算指标 | ~1.5 GB | float32 优化后 |
| 横截面日榜 | ~250 MB | 10 年 × 2500 日 |
| 大盘状态 | ~10 MB | 单标的 |
| Metadata | ~50 MB | 交易日历、行业、市值 |
| **总计** | **~12 GB** | 适合 SSD 存储 |