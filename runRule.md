# ATOS 策略迭代规则（防止下次执行遗忘）

> **最后更新**: 2026-06-15
> **基于**: ATOS1 V1-V5 + ATOS2 v1 V1-V5 共 10 次迭代经验

---

## 1. 项目结构与命名规则

### 1.1 测试集（3 个 universe，每次小版本必跑）

| Universe | 数量 | 来源 | 风格 |
|----------|------|------|------|
| **HS300** | 300 | data/config.py HS300 | 大盘蓝筹 |
| **CSI1000** | 1000 | data/config.py CSI1000 | 中小盘 |
| **CYB_STAR_50** | ~100 | data/config.py CYB_STAR_50 | 高波动（创业板 50 + 科创板 50） |

> 每次小版本必须跑 3 个 universe，每个 universe 1 份报告。

### 1.2 命名规则

- **大版本号**：ATOS{N}（N=1, 2, 3, ...）
- **小版本号**：v1（baseline）/ v2 ~ v10（迭代，共 10 次）
- **完整名**：ATOS{N}_v{M}.md（如 ATOS2_v5.md）
- **报告名**：report{N}_v{M}_{UNI}.md（UNI = HS300 / CSI1000 / CYBSTAR）
- **STRATEGY_VERSION**：{N}_v{M}（大_小版本，不含 universe）

### 1.3 文件结构

D:\claude-quant\
├── ATOS-des.md              # 原 spec
├── goodIdeal.md             # 硬指标参考
├── read.md                  # ATOS1 综合分析
├── read_ATOS2_v1_round1.md  # ATOS2 v1 第一轮综合分析
├── runRule.md               # 本文件
├── strategies/              # 策略文档
├── reports/                 # 回测报告
│   ├── report{N}_v{M}_{UNI}.md
│   └── detail/
└── atos/                    # 回测系统代码

---

## 2. 迭代模式

### 2.1 大版本升级（每轮开始）

1. 写新 spec 文档 到 strategies/ATOS{N}_v1.md
2. 修改回测系统（最小化原则 + 单元测试）
3. 更新 params.yaml + report.py 的 STRATEGY_VERSION
4. 记录到 §3.1 大版本变更表

### 2.2 10 次调优（每轮内部）

1. 改 params.yaml（一个或几个参数）
2. 改 report.py 的 STRATEGY_VERSION
3. 跑 3 次回测（3 个 universe）：

```bash
python -m atos.run --mode portfolio --config atos/config/params.yaml \
  --start 2018-01-01 --end 2020-04-30 \
  --universe HS300 --output D:/claude-quant/reports
python -m atos.run ... --universe CSI1000 ...
python -m atos.run ... --universe CYB_STAR_50 ...
```

4. 写分析到 strategies/ATOS{N}_v{M}.md（含 3 universe 对比）
5. 重复 10 次（V1-V10）
6. 记录到 §3.2 小版本参数变更表

### 2.3 3 轮大版本循环

ATOS2 v1 (spec 升级) → V1-V10 调优（× 3 universe）→ 综合分析
ATOS2 v2 (基于 v1 升级) → V1-V10 调优（× 3 universe）→ 综合分析
ATOS2 v3 (基于 v2 升级) → V1-V10 调优（× 3 universe）→ 最终综合

> **大版本升级原则**：v(N+1) 必须综合考虑：
> 1. 本大版本（vN）的 V1-V10 调优结果
> 2. 之前大版本（v1, v2, ..., v(N-1)）的变更记录（§3.1）
> 3. 跨大版本的"未解决问题"（§3.3）

### 2.4 时间预算

- 每次回测（1 universe）：~30 秒
- 每次小版本（3 universe）：~2 分钟
- 10 次小版本调优：~20 分钟
- 1 轮大版本（含 spec 升级 + 引擎调整 + 30 次回测 + 综合分析）：~60-90 分钟
- **3 轮大版本：~3-4.5 小时**

---

## 3. 版本变动记录（**核心档案，下轮升级必读**）

### 3.1 大版本变更记录

| 大版本 | 时间 | spec 文档 | 引擎代码改动 | 关键升级点 |
|--------|------|----------|-------------|-----------|
| **ATOS1 v1** | 2026-06 之前 | ATOS-des.md | 原版 | 4 状态 + 13 因子 + 5 层风控 |
| **ATOS2 v1** | 2026-06-15 | strategies/ATOS2_v1.md | engine/universe/factors/strategy_config | 8 项升级：状态 v2、凯利、回撤阶梯、流动性过滤、14 因子、IC 加权预留等 |
| **ATOS3 v1** | 2026-06-16 | strategies/ATOS3_v1.md | factors/market_regime/combined/strategy_config/adaptive/breadth/engine | 5 项升级：IC 加权实施、状态 v3 (ADX/RSI)、真实 breadth、自适应 Kelly、bb_width |
| **ATOS4 v1** | 2026-06-16 | strategies/ATOS4_v1.md | strategy_config/adaptive/params | 4 项升级：per_universe、样本量 Kelly、cash 提升、测试集合并 |
| **ATOS5 v1** | 2026-06-16 | strategies/ATOS5_v1.md | params (时段) | 3 项升级：时段扩展至 2024、多时间框架、风险预算 |

### 3.2 小版本参数变更记录

#### ATOS1 系列（仅记录突破性版本）
| 版本 | 年化 | 关键参数 | 备注 |
|------|------|---------|------|
| V1 | -6.55% | 旧 spec 默认 | baseline |
| V2~V5 | -6% ~ -8% | 在 V1 基础上扰动 | 全部负收益，触底 |

#### ATOS2 v1 系列（**核心调优档案**）
| 版本 | 年化 | 关键参数 | 备注 |
|------|------|---------|------|
| V1 | -1.49% | 默认（min_dur=2, kelly=0.5, 流动性开） | baseline（CSI 1000） |
| **V2** | **-0.88%** | min_dur=1, cd=2, kelly=0.3 | **最佳**（CSI 1000） |
| V3 | -0.99% | 关流动性过滤, kelly=0.2 | 中间 |
| V4 | -6.66% | **关凯利+关回撤** | 失败（验证新功能关键性） |
| V5 | -1.49% | min_dur=2, kelly=0.4, cd=2 | 与 V1 baseline 相同 |

> **V2-V5 关键发现**：
> - 凯利公式 + 回撤阶梯 + 流动性过滤贡献 5-6pp 年化改善
> - 交易笔数从 160 笔降到 12-15 笔（cash 大量闲置）
> - 仍未达成 ≥15% 目标

### 3.3 跨大版本"未解决问题"（下轮升级必看）

#### ATOS2 v1 未解决
1. **IC 加权未实施**：spec §7.3 预留但未集成（v2 候选项）
2. **状态识别无前瞻**：BULL/BEAR 仅基于 MA/涨幅/波动率，无 ADX/RSI 前瞻（v2 候选项）
3. **市场宽度是指数代理**：未用沪深 300 真实成份股（v2 候选项）
4. **凯利乘数固定**：未随滚动胜率自适应（v2 候选项）
5. **样本量过小**：12-15 笔交易，胜率统计无意义
6. **cash 大量闲置**：年化波动率 0.88-0.98%（异常低）
7. **未测试牛市**：仅测 2018-2020.4 震荡+熊市

#### ATOS2 v2 候选升级方向（v1→v2）
1. **IC 加权实施**（spec §7.3）
2. **状态识别 v3**（加 ADX/RSI 前瞻）
3. **真实 market_breadth**（HS300 全样本）
4. **自适应 Kelly**（随胜率缩放）
5. **补全 14 因子**（修复 v1 缺失 bb_width）

#### ATOS2 v3 候选升级方向（v2→v3）
待 v2 完成后填入

#### ATOS3 v1 未解决（→ ATOS4 升级方向）
1. **CSI1000 始终负收益**：需要 universe-specific 参数或新策略
2. **V6-V10 触局部最优**：需要结构性升级
3. **CYB_STAR_50 +3.51% 距目标 15% 还差 11.49pp**：需大幅升级
4. **V3 改动（IC 加权/状态 v3）影响有限**：5 项升级中只有 min_dur/cooldown 真正起作用
5. **10-50 笔交易，统计意义弱**：需要更长时间区间

#### ATOS3 v1 关键发现（3 universe）
- **最佳 V5**（min_dur=3, cooldown=5）：HS300 +2.76%, CSI1000 -1.11%, CYB_STAR_50 +3.51%
- **V4-V5 是分水岭**：状态确认稳定性比 IC 加权更重要
- **CYB_STAR_50 全程正收益**：最适合 ATOS 策略
- **V6-V10 触局部最优**：6 个连续版本未改善 V5

#### ATOS4 候选升级方向
1. **Universe-specific 参数**：per_universe_overrides 实施
2. **CSI1000 专项策略**：更激进 top_n、更短 holding
3. **CYB_STAR_50 强化**：保持 8-10 只持仓
4. **真实 market_breadth 完整实施**
5. **多时间段验证**：扩展到 2020-2021 牛市

---

## 4. 关键规则

### 4.1 调优必须"符合 spec"
- 不能新增 spec 未要求的功能
- 只能调 params.yaml 里的参数
- 偏离 spec 的调整要在策略文档里说明

### 4.2 测试必须全过
- 跑 `python -m pytest atos/tests/`
- 96+ 测试必须全过
- 新增功能必须加单元测试

### 4.3 调优不能引入系统性 bug
- 每改一处引擎代码，加单元测试
- 跑测试确保无回归

### 4.4 报告命名严格按 §1.2
- 报告 = report{STRATEGY_VERSION}_{UNI}.md
- UNI 必须为 HS300 / CSI1000 / CYBSTAR 之一

---

## 5. 调优经验

### 5.1 旧 spec V1-V5 教训
- **BULL 状态识别滞后**：5 版本都因 BULL 累计 -103% ~ -138% 拖后腿
- **缩短持仓数过头**：V3 减少到 4 只反而变差
- **缩短移动止盈 k 过头**：V3 k=2.0 反而被频繁止损
- **调优空间已触底**：V1-V5 全部 -6% ~ -8%

### 5.2 ATOS2 v1 验证
- **凯利+回撤+流动性是关键**：V4 关闭后立刻 -6.66%
- **V2 最佳配置**：min_dur=1, cd=2, kelly=0.3, 过滤 1 亿
- **仍有大空间**：年化 -0.88% → 目标 15%

### 5.3 多 universe 调优经验（**新增**）
- HS300 vs CSI1000 vs CYB_STAR_50：风格差异大
- 同一参数在不同 universe 表现可能差 5-10pp 年化
- 调优时**优先在 3 个 universe 上都跑**，再选全局最优

---

## 6. 命令速查

### 6.1 跑单 universe 回测

```bash
cd D:/claude-quant
python -m atos.run --mode portfolio \
  --config atos/config/params.yaml \
  --start 2018-01-01 --end 2020-04-30 \
  --universe HS300 \
  --output D:/claude-quant/reports
```

### 6.2 跑 3 个 universe（推荐用于小版本）

```bash
cd D:/claude-quant
for UNI in HS300 CSI1000 CYB_STAR_50; do
  python -m atos.run --mode portfolio \
    --config atos/config/params.yaml \
    --start 2018-01-01 --end 2020-04-30 \
    --universe $UNI \
    --output D:/claude-quant/reports
done
```

### 6.3 跑测试

```bash
cd D:/claude-quant
python -m pytest atos/tests/ -v
```

### 6.4 单标的回测

```bash
python -m atos.run --mode single --symbol 000001 \
  --start 2018-01-01 --end 2020-04-30
```

---

## 7. 注意事项

### 7.1 引擎代码修改清单（ATOS2 v1 已加）
- engine.py: 凯利公式 / 回撤阶梯
- universe.py: liquidity_filter / get_cyb_star_50() / get_universe() 路由
- factors.py: price_momentum_5d（13→14 因子）
- strategy_config.py: kelly_multiplier / drawdown_step_enabled / liquidity_filter_enabled
- run.py: --universe 参数
- report.py: STRATEGY_VERSION + UNI 后缀

### 7.2 已知限制
- 胜率 0% 在小样本下无意义（V1-V5 中 12-15 笔交易）
- 年化波动率 0.88% 异常低（因 cash 大量闲置）
- 凯利公式在样本 < 10 时不应用

### 7.3 Universe 注意事项
- **CYB_STAR_50** 仅 100 只左右，样本小
- **HS300** 大盘蓝筹，alpha 难做
- **CSI1000** 推荐作为主测试集

---

## 8. 恢复指引（如果系统坏了）

### 8.1 重新初始化
1. 检查 params.yaml 的 strategy_version
2. 检查 report.py 的 STRATEGY_VERSION
3. 检查 data/config.py 的 3 个 universe
4. 跑测试：python -m pytest atos/tests/

### 8.2 报告找不到时
- 检查 reports/ 目录
- 检查 STRATEGY_VERSION + --universe 是否与文件名匹配

### 8.3 回测崩溃时
- DrawdownTracker.current_dd（不是 current_drawdown）
- liquidity_filter 列名（用 amount 不用 "成交额"）
- universe 名是否在 data/config.py 中

---

## 9. 后续工作建议

### 9.1 已完成 ✅
- ATOS1 V1-V5（10 次迭代）
- ATOS2 v1 V1-V5（5 次迭代）
- 综合分析：read.md, read_ATOS2_v1_round1.md

### 9.2 待完成 ⏳
- ATOS2 v1 V6-V10（补足 10 次）
- ATOS2 v2 大版本升级（基于 v1 + §3.3 候选方向）
- ATOS2 v3 大版本升级
- 3 universe × 10 版本 × 3 大版本 = 90 份报告

### 9.3 下一次执行时
1. 读 runRule.md 了解规则
2. 读 §3.3 跨大版本"未解决问题"
3. 选择继续 v1 剩余 5 次，或启动 v2 大版本
4. 按 §2.3 流程执行 3 轮大版本循环

---

**核心原则**:
1. 调优符合 spec（不能擅自加新功能）
2. 测试必须全过（96+）
3. 报告用 STRATEGY_VERSION + UNI 命名
4. 每次小版本跑 3 universe
5. 大版本升级综合考虑本轮 + 历史变更 + 未解决问题
6. 引擎修改最小化 + 加测试
7. 详细记录到 §3 版本变动档案
