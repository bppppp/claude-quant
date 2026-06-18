# ATOS MR v2 策略回测报告 (全部测试集汇总)

**生成时间**: 2026-06-17 10:52:08
**回测区间**: 2018-01-01 ~ 2022-12-31 (5 年)
**策略版本**: ATOS MR v2 (无前视偏差, T+1 结算)

---

## 4 个测试集汇总对比

| 测试集 | 股票数 | 年化 | 累计 | 最大回撤 | 胜率 | 笔数 | 单笔均值 |
|--------|--------|------|------|----------|------|------|----------|
| HS300 (沪深 300) | 296 | +26.52% | +223.57% | -15.06% | 49.7% | 1772 | +1.324% |
| CSI1000 (中证 1000) | 988 | +9.67% | +58.51% | -37.84% | 42.8% | 2832 | +0.688% |
| CYB_STAR_50 (创业板 50 + 科创板 50) | 100 | +22.97% | +180.71% | -9.98% | 49.8% | 1133 | +1.493% |
| ALL (合并 (HS300+CSI1000+CYB50)) | 1339 | +9.61% | +58.11% | -29.80% | 43.3% | 3030 | +0.743% |

---

## 各测试集详细报告

| 测试集 | 报告位置 |
|--------|----------|
| HS300 | reports\HS300\ATOS_MR_v2_HS300_report.md |
| CSI1000 | reports\CSI1000\ATOS_MR_v2_CSI1000_report.md |
| CYB_STAR_50 | reports\CYB_STAR_50\ATOS_MR_v2_CYB_STAR_50_report.md |
| ALL | reports\ALL\ATOS_MR_v2_ALL_report.md |

---

## 关键发现

### 1. HS300 是主推测试集
- **年化 26.52%**, 最大回撤 15.06%, 胜率 49.7%
- 4/5 年跑赢沪深 300 基准 (仅 2019 牛市少跑)
- 风险收益比最优, 推荐作为主回测

### 2. CYB_STAR_50 风险最低
- **年化 22.97%**, 最大回撤仅 9.98%
- 创业板 50 + 科创板 50 的高波动股票反而因为均值回归信号更强
- 适合追求低回撤的资金

### 3. CSI1000 表现较弱
- 年化 9.67%, 最大回撤 37.84%
- 中证 1000 标的小盘股多, 流动性较差, 均值回归效应弱

### 4. 合并 ALL 是综合表现
- 年化 9.61%, 最大回撤 29.80%
- 由于 CSI1000 权重 74% 拉低整体, 与单独 CSI1000 接近

---

## 推荐使用

| 场景 | 推荐测试集 |
|------|-----------|
| 主力回测 (与本地一致) | **HS300** |
| 低回撤需求 | CYB_STAR_50 |
| 全市场覆盖 | ALL |
| 小盘股研究 | CSI1000 |

---

## 聚宽上传方式

每个测试集有独立的 strategy_*.py 文件, 自包含, 可直接粘贴到聚宽:

- HS300: D:\claude-quant\JQ\scripts\HS300\strategy_HS300.py
- CSI1000: D:\claude-quant\JQ\scripts\CSI1000\strategy_CSI1000.py
- CYB_STAR_50: D:\claude-quant\JQ\scripts\CYB_STAR_50\strategy_CYB_STAR_50.py
- ALL: D:\claude-quant\JQ\scripts\ALL\strategy_ALL.py

---

## 参考资料

- 策略实现: D:\claude-quant\atos\backtest\mr_v2.py
- 策略文档: D:\claude-quant\strategies\ATOS_MR_v2.md
- 聚宽移植指南: D:\claude-quant\JQ\createBase\ATOS_MR_v2_JQ_GUIDE.md
- 聚宽脚本: D:\claude-quant\JQ\scripts\
