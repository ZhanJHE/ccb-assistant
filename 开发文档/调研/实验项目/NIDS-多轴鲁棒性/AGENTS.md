# NIDS 多轴鲁棒性 项目工作规则（评测与增强）

> 本项目隶属 `论文学习/` 工作区，工作区根 [AGENTS.md](../../AGENTS.md) 规则依然有效；本文件规则优先。
> **创建**：2026-10-09　**状态**：M1（复现 AIN-18 三轴 harness）
> **环境**：实验以**可租云 Linux / RK3588 自带 Linux / 实验室硬件（P4 交换机、BlueField、VU13P）**为准。
> **唯一禁令（2026-10-10 用户澄清）**：**只用这台台式机的 WSL 会崩网络 → 不碰这台机的 WSL**；但云 Linux、板卡自带 Linux、租 GPU 均允许。

## 项目一句话

把 ML-based NIDS 的评测从"同分布单轴"扩到 **多轴**（同分布 / 跨域 / 对抗 / **时序漂移**），量化"轴间交互与排序反转"，并给出轻量鲁棒增强。

- 暂定标题：*Beyond Three Axes: Multi-Axis Robustness Evaluation and Lightweight Hardening for ML-based Network Intrusion Detection*
- 来源 idea：[`选题方案/Idea池/AI4Net-idea集-2026-10-09.md`](../../选题方案/Idea池/AI4Net-idea集-2026-10-09.md) I7（扩展）
- 作战计划：[`选题方案/AI4Net-作战计划（裁缝版）.md`](../../选题方案/AI4Net-作战计划（裁缝版）.md)
- 专题调研 + 精读：[`调研卷宗/智能网络/智能网络调研.md`](../../调研卷宗/智能网络/智能网络调研.md)（AIN-18 / AIN-17 / AIN-6）

## 三道裁决门（Go/No-Go，事前冻结）

| 门 | 内容 | 状态 |
|---|---|---|
| **G1** | M1 复现：跨域退化是否复现（binary F1 掉幅 ≥ **10** 点，对齐 AIN-18 的 +15 F1 量级） | ⬜ 未开始 |
| **G2** | M2 第四轴（**A4a 真时间**／A4b 跨域严重度）是否导致**模型排序反转** | ⬜ 未开始 |
| **G3** | M4 增强是否有**可测鲁棒增益**（≥ 阈值，M4 前冻结具体数） | ⬜ 未开始 |
| **G4** | 轴间排名**不一致性**（如 Kendall τ < 0.5 的轴对 ≥ 1 对）——支撑"轴间不可约性"钩子 | ⬜ 未开始 |
| **G5** | ≥1 个增强在 ≥1 个轴上有**统计显著**增益（Wilcoxon） | ⬜ 未开始 |
| **G6** | 时间轴与跨域轴排名**不一致**（证明两轴不可互相替代） | ⬜ 未开始 |

> **判据前提（2026-10-09 修订）**：**A4a（真时间漂移）依赖数据是否含时间戳**；已核查 baseline `config.py`——NetFlow v2 的 43 列**无 wall-clock 时间**（仅 `FLOW_DURATION_MILLISECONDS` 时长）。故 A4a 需换数据（CIC-IDS2017 / 原始 IDS2018）或**诚实声明暂缺**；A4b（λ 跨域严重度）不受影响。详见 [评审反思与改进方案](docs/评审反思与改进方案.md)。

G1 判据（冻结）：复现不出跨域崩塌 → 前提不成立 → 转纯复现短文或换题（回 I5）。

## 目录结构

```
NIDS-多轴鲁棒性/
  AGENTS.md            ← 本文件
  docs/                ← 计划、对照表、精读笔记
  论文/                ← 论文草稿与图表
  scripts/             ← 采集/评测/分析脚本（可重复跑；参数写在脚本头注释）
  analysis/            ← 分析产物（图表、统计）
  results/             ← 原始数据与中间产物（大文件不入库）
  code/                ← baseline 与增强实现（git clone 的第三方代码放 code/thirdparty/）
```

## 项目规则

1. **环境纪律**：只在 **Windows 原生**跑；**任何 WSL 命令都不要执行**。第三方依赖用项目内 venv（`code/.venv`），**不装系统级包**；需 `pip install` 前先跟用户确认。
2. **基线纪律**：第三方 baseline 代码放 `code/thirdparty/`，记录 commit hash 与来源 URL（写在 `code/thirdparty/SOURCES.md`）；**不改第三方源码**，增强走独立模块 + 配置。
3. **数据纪律**：数据集放 `results/`（不入 git）；下载来源与校验（大小/SHA256 前 8 位）记入 `docs/数据集清单.md`。
4. **撞车监控**：关键词 `NIDS multi-axis evaluation` / `temporal drift intrusion detection` / `cross-dataset transfer NIDS`；结果记 `docs/撞车监控日志.md`。
5. **文献纪律**：新读论文先查 [`文献索引.md`](../../文献索引.md) 再登记（AIN 编号续排）。
6. **凭证不落盘**：API Key 一律走环境变量。
7. **承诺冻结**：贡献声明以 `docs/Phase0-贡献声明与对照表.md` 为准，改动需记日期与理由。
8. **反裁缝底线**：数据真实、可复现；**禁止**改数据/互换结果/伪造/抄袭。
