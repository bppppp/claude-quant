# ATOS MR v2/v5 聚宽 (JQ) 回测脚本

## 目录结构

```
JQ/scripts/
├── README.md           # 本文件
├── mr_v2.py            # 策略核心 (VSCode开发用)
├── univ.py             # 测试集定义 (VSCode开发用)
├── run_all.py          # 本地批量回测
│
├── HS300/              # HS300 测试集 (296 stocks)
│   ├── strategy_HS300.py    # 上传聚宽用 (自包含)
│   └── run_HS300.py         # 说明入口
│
├── CSI1000/            # CSI1000 测试集 (988 stocks)
│   ├── strategy_CSI1000.py
│   └── run_CSI1000.py
│
├── CYB_STAR_50/        # 创业板50+科创50 (100 stocks)
│   ├── strategy_CYB_STAR_50.py
│   └── run_CYB_STAR_50.py
│
├── ALL/                # 合并测试集 (1339 stocks)
│   └── strategy_ALL.py
│
└── HS300_CYB50/        # [NEW v5] ALL检测 + HS300+CYB50交易 (352 stocks)
    ├── strategy_HS300_CYB50.py  # 上传聚宽用 (3616 lines)
    └── run_HS300_CYB50.py
```

## 本地回测结果 (2018-01-01 ~ 2022-12-31)

| 策略 | 检测池 | 交易池 | 年化 | 最大回撤 | 胜率 | 笔数 |
|------|--------|--------|------|----------|------|------|
| **v5 HS300_CYB50** | ALL 1339 | HS300+CYB50 352 | **+19.81%** | -16.57% | 48.7% | 1968 |
| v2 HS300 | HS300 296 | HS300 296 | +26.52% | -15.06% | 49.7% | 1772 |
| v2 CYB_STAR_50 | CYB50 100 | CYB50 100 | +22.97% | -9.98% | 49.8% | 1133 |
| v2 ALL | ALL 1339 | ALL 1339 | +9.61% | -29.80% | 43.3% | 3030 |
| v2 CSI1000 | CSI1000 988 | CSI1000 988 | +9.67% | -37.84% | 42.8% | 2832 |

## 上传到聚宽

每个 `strategy_*.py` 都是自包含的:
1. 登录 https://www.joinquant.com，新建策略 Python3 (JQBoson)
2. 复制 `strategy_*.py` 全部内容到编辑器
3. **设置初始资金 1,000,000**
4. 回测区间: 2018-01-01 ~ 2022-12-31，频率: 日
5. 对比本地结果 (允许 ±3-5% 偏差)

## v5 vs v2 区别

- **v5**: 在 ALL 1339 只股票上检测信号，但只交易 HS300+CYB50 352 只
- **v2**: 检测池 = 交易池 = 单一 universe

v5 验证了"扩大股池找规律，过滤噪声执行"的理念。

## 关键工程注意 (8 quirk)

详见 `D:\claude-quant\JQ\createBase\ATOS_MR_v2_JQ_GUIDE.md`

## 本地验证

```bash
cd D:\claude-quant
PYTHONPATH=. python JQ/scripts/run_all.py
```
