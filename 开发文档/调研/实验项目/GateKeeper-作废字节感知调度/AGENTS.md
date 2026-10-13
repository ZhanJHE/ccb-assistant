# GateKeeper 项目工作规则（作废字节一等目标 × 负载预测的网关择时调度）

> 本项目隶属 `论文学习/` 工作区，工作区根 AGENTS.md 规则依然有效；本文件规则优先。
> **创建**：2026-10-02　**状态**：Phase 0（立题裁决，G0 已通过）

## 项目一句话

在家庭网关（RK3588）上，把"作废字节（wasted bytes）"作为一等优化目标，与 WiFi 负载预测耦合：
先量化"中断→作废→重传→抬高高峰负载"这条因果链（M0 测量），再构建作废感知 × 负载预测的择时调度系统。

- 暂定标题：*Wasted-Byte-Aware Scheduling on a Home Gateway: Coupling Redundant-Transfer Suppression with WiFi Load Prediction*
- 原始 idea：`选题方案/单板idea/RK3588.md` Idea 1
- 专题调研：`调研卷宗/WiFi负载预测与高峰传输/WiFi负载预测与高峰传输调研.md`（WTP 专题，含 G2 空白与 G0 复核记录）

## 三道裁决门（Go/No-Go）

| 门 | 内容 | 状态 |
|---|---|---|
| **G0** | 补充检索复核空白 | ✅ 2026-10-02 通过（OpenAlex+S2 双源 20+ 组关键词零命中，可信度"中高"；见调研 §6.6） |
| **G1** | M0 测量数字裁决（作废占比 + 高峰抬升量） | ⬜ 未开始 |
| **G2'** | 系统层消融后确认增量（vs WTP-26/27） | ⬜ 未开始 |

G1 判据（预先冻结，防止事后挪动球门）：
- 作废占比 ≥10% 量级 → "测量+系统"完整论文（CoNEXT/IMC → Computer Networks）；
- 个位数但高峰抬升显著 → 转纯测量论文（PAM/IMC）；
- 数字小且因果弱 → 止损，回 `选题方案/单板idea/RK3588.md` 重选（优先 Idea 3 NPUscope）。

## 目录结构

```
GateKeeper-作废字节感知调度/
  AGENTS.md            ← 本文件
  docs/                ← 计划、对照表、精读笔记、论文草稿
  scripts/             ← 采集/注入/分析脚本（可重复跑）
  analysis/            ← 分析产物（图表、统计）
  results/             ← 原始数据与 trace（大文件不入库）
  code/                ← 调度器/预测器实现
```

## 项目规则

1. **撞车监控**：每月 1 号前后复查 arXiv 新稿，关键词：wasted bytes / traffic wastage / retry storm / predictive traffic shaping / WiFi load prediction scheduling；重点盯 WTP-26/27 作者组续作。结果记入 `docs/撞车监控日志.md`。
2. **文献纪律**：新读论文先查 `文献索引.md` 再登记（WTP 编号续排）；PDF 放 `调研卷宗/WiFi负载预测与高峰传输/`（文件名带 WTP 前缀）。
3. **数据纪律**：trace 与原始数据放 `results/`，不入 git；采集脚本必须可重复（参数写在脚本头注释）。
4. **凭证不落盘**：API Key 一律走环境变量（`S2_API_KEY` 等）。
5. **承诺冻结**：贡献声明以 `docs/Phase0-贡献声明与对照表.md` 为准，改动需记日期与理由。
