# How Many Labels to Diagnose Drift? Label-Budgeted Diagnosis-and-Hardening for Multi-Axis Robustness in ML-based Network Intrusion Detection
# 诊断漂移要几个标签？标签预算下的多轴 NIDS「诊断—加固」

> 方案 β（NIDS 线）· **草稿 Draft v0.2（2026-10-10）**· 项目 [`实验项目/NIDS-多轴鲁棒性/`](../AGENTS.md)
> ⚠️ `[B]` = AIN-18 已发表真数（复现锚点）；`🔲` = 待跑，**不得引用**。
> 📖 每段先英文、紧随 `>` 中文。**`🔧 缝点`/附录为内部注记，投稿版删除**。
> **salami 声明**：本稿是**唯一一篇**；此前的"多轴评测稿"（`论文稿-多轴NIDS.md`）**并入本稿 §3/§5**，**不再单独投递**（回应子代理评审的 salami 指控）。

## v0.2 修订说明（回应子代理评审）
1. **修致命硬伤"诊断不可识别"**：v0.1 说用 MMD/KL/对抗验证在**无标签**下分协变量/概念漂移——**不成立**（概念漂移是 P(Y|X) 变化，从边际分布不可识别）。v0.2 改为三件套：**(A) 可识别性边界（负结果）** + **(B) 标签预算下的主动诊断（budget–gain 曲线）** + **(C) 可证伪主张**：等预算下"诊断驱动选药 > 盲目选药"。
2. **解 salami**：与评测稿**合并为一篇**（见上声明）。
3. **去 HARKing**：§5 改为**预注册假设**，删除全部"预期/we expect"；**先注册阈值，跑完再写摘要**。
4. **降级过度声称**：轴感知集成从"genuinely new method"降为**一个被测试的对照**（并与 stacking / 单一全域专家 / 普通 MoE gating 对比）。
5. **补外部效度 + 统计**：≥4 数据集（含一个非 v2 家族）× ≥4 模型族；≥5 seed；效应量 + **BH 校正**。
6. **档位校准**：先定 **CCF-C / Q2**，达标后再谈擦边 B。

---

## 故事五要素 → 结构

| 要素 | 章节 | 一句话 |
|---|---|---|
| 背景 | §1 | NIDS 单轴刷分；AIN-18 证明单轴会选错模型 |
| **冲突** | §1 | 有人开始"诊断"——**但"无标签诊断漂移类型"在方法上根本不可识别**（v0.1 的死穴） |
| 主角 | §3 | **标签预算化诊断** + 诊断驱动选药（+ 一个集成对照） |
| 情节 | §5 | 预算—增益曲线；等预算下"诊断驱动 vs 盲目"对比 |
| 主题 | §7 | 诊断漂移**不是免费的**：它有一个**标签价格**，且并非所有轴都买得起 |

---

## Abstract

"Diagnose the drift, then prescribe a remedy" sounds free, but it is not: **covariate vs concept drift is not identifiable from unlabeled marginals** — the two can produce identical feature distributions while differing in P(Y|X). **[v0.2 核心更正]** We therefore recast diagnosis as a **label-budgeted** problem and ask the operational question: *how many target labels does it take to decide the drift type and to recover performance?*

> "先诊断漂移，再开方"听起来免费，其实不然：**协变量漂移与概念漂移无法从无标签的边际分布中区分**——两者可以给出完全相同的特征分布，却在 P(Y|X) 上不同。**[v0.2 核心更正]** 因此我们把它重述为**标签预算**问题，并追问一个可操作的问题：***判断漂移类型并恢复性能，究竟需要多少目标标签？***

We give (A) an **identifiability boundary** (a negative result: zero-label drift-type diagnosis is impossible in general), (B) a **budget–gain protocol** that quantifies labels-to-type and labels-to-recovery, and (C) a **falsifiable claim** that at equal label budget, *diagnosis-guided* remedy selection beats *diagnosis-free* selection. All results are pending (**pre-registered hypotheses, §5**).

> 我们给出：(A) **可识别性边界**（负结果：一般情况下零标签的漂移类型诊断不可能）；(B) **预算—增益协议**，量化"判类型要几标签、恢复性能要几标签"；(C) **可证伪主张**：等标签预算下，*诊断驱动*选药优于*盲目*选药。全部结果待跑（**预注册假设见 §5**）。

> 🔧 **缝点**：Abstract 改为"标签预算化 + 可识别性边界"，**把 v0.1 的死穴写成本文的卖点**。未跑留空。

---

## 1 Introduction / 引言

**Background.** ML-based NIDS report in-distribution F1 in the high 0.99s on UNSW-NB15 and CSE-CIC-IDS2018 — the field's de-facto yardstick.

> **背景**：ML-based NIDS 在 UNSW-NB15、CSE-CIC-IDS2018 上的同分布 F1 都在 0.99 以上，是领域事实标尺。

**The conflict.** AIN-18 shows that yardstick lies: the same two models tie in-distribution, split cross-network (0.8116 vs 0.6582 **[B]**), and reverse adversarially (0.7720 vs 0.9448 **[B]**); AIN-17 adds that pipeline choices dominate architecture. The literature now **diagnoses** fragility — and the natural next step ("diagnose the drift type, then fix it") **rests on a false premise**: concept drift changes P(Y|X), which **no unlabeled statistic (MMD/KL/adversarial validation) can separate** from covariate drift.

> **冲突**：AIN-18 证明标尺会说谎——同分布打平、跨网络分化（0.8116 对 0.6582 **[B]**）、对抗反转（0.7720 对 0.9448 **[B]**）；AIN-17 补充"流水线压过架构"。领域如今会**诊断**脆弱；而顺理成章的下一步"先判漂移类型再修" **建立在一个错误前提上**：概念漂移改的是 P(Y|X)，**任何无标签统计量（MMD/KL/对抗验证）都分不开它与协变量漂移**。

**Protagonist.** We fix the premise instead of hand-waving it: **(1)** state the **identifiability boundary**; **(2)** make diagnosis **label-budgeted** (spend *b* labels to decide type/remedy); **(3)** test the falsifiable claim that budget-matched diagnosis-guided hardening beats blind hardening. We also test — as a **control**, not a headline — an axis-aware ensemble.

> **主角**：我们不糊弄这个前提，而是**把它修好**：**(1)** 给出**可识别性边界**；**(2)** 把诊断变成**标签预算化**（花 *b* 个标签去判类型/选药）；**(3)** 检验可证伪主张：等预算下诊断驱动加固优于盲目加固。另把一个轴感知集成作为**对照**（不是头条）。

**Contributions.** (A) identifiability boundary for unlabeled drift-type diagnosis; (B) a budget–gain protocol (labels-to-type, labels-to-recovery); (C) a budget-matched, diagnosis-vs-blind comparison with controls (stacking; single global expert; generic gating MoE).

> **贡献**：(A) 无标签漂移类型诊断的**可识别性边界**；(B) **预算—增益协议**（判类型/恢复性能各要几标签）；(C) **等预算**的"诊断 vs 盲目"对比，配对照（stacking；单一全域专家；普通 MoE gating）。

**Thesis.** Diagnosis is not free; robustness failures carry a **label price**, and not every axis is affordable.

> **主题**：诊断**不免费**；鲁棒性缺陷有**标签价格**，且不是每个轴都买得起。

> 🔧 **缝点**：Introduction 重写——**把 v0.1 的方法学死穴（不可识别）变成论文的立命点**。这是把"评审的一刀"转成"贡献"的标准做法。

---

## 2 Related Work / 相关工作

**NIDS robustness.** Cross-dataset collapse (Cantone); three-axis protocol (AIN-18); pipeline dominance (AIN-17).

> **NIDS 鲁棒性**：跨数据集崩塌（Cantone）、三轴协议（AIN-18）、流水线主导（AIN-17）。

**Drift identifiability.** Covariate vs concept drift and their non-identifiability without target labels; domain-adaptation theory (Ben-David et al.); MMD/对抗验证的适用边界。

> **漂移可识别性**：协变量 vs 概念漂移、及其在无目标标签下的**不可识别性**；域适应理论（Ben-David 等）；MMD/对抗验证的适用边界——**本文主线的理论来源**。

**Label-efficient / active diagnosis.** Active learning and label-budgeted evaluation.

> **标签高效/主动诊断**：主动学习与"标签预算"评测——**我们的 (B) 从这里取工具**。

**Remedies & ensembles.** Domain alignment (TL-CRANN/CARD), feature selection (Access'26), gating MoE.

> **处方与集成**：域对齐（TL-CRANN/CARD）、特征选择（Access'26）、gating MoE——**我们的对照/处方来源**。

---

## 3 Approach / 方法

> 🔧 **缝点总纲**：§3 = AIN-18 harness（骨）+ 可识别性分析 + 预算化诊断 + 处方 + 集成对照。

### 3.1 Multi-axis harness (reused; folds in the evaluation paper)
AIN-18's harness (`run_full_benchmark`, 29 features, balanced 50k/class), extended with A4a temporal and A4b cross-domain severity. **本稿即为合并稿：评测（发现问题）与加固（给处方）在此统一。**

> 复用 AIN-18 harness，扩展 A4a 时间 / A4b 跨域严重度。**本稿即合并稿：评测与加固在此统一。**

### 3.2 Identifiability boundary (the fix)
State when drift type is/n't identifiable from unlabeled data; show a construction where covariate and concept drift yield identical marginals ⇒ **zero-label type diagnosis is impossible in general**. Budgeted diagnosis then targets a **near-identifiable** regime (few labels).

> **可识别性边界（本稿的修法）**：给出漂移类型在无标签下可/不可识别的条件；并构造"协变量与概念漂移给出相同边际分布"的反例 ⇒ **零标签判类型一般不可能**。预算化诊断因此瞄准**近可识别**区间（少量标签）。

### 3.3 Budgeted diagnosis + prescriptions
Given budget *b* target labels: (i) decide drift type; (ii) pick among H1 time-reweighting / H2 domain alignment / H3 per-axis feature selection; (iii) report labels-to-type and labels-to-recovery.

> **预算化诊断 + 处方**：给定 *b* 个目标标签：(i) 判漂移类型；(ii) 在 H1 时间重加权 / H2 域对齐 / H3 逐轴特征选择中选一个；(iii) 报"判类型所需标签"与"恢复性能所需标签"。

### 3.4 Controls (incl. a demoted ensemble)
Compare against: **blind** (all-remedy / no-remedy), **stacking**, **single global expert**, **generic gating MoE**, and an **axis-aware ensemble** — the ensemble is now a *control*, claimed new only if it beats generic gating at equal cost.

> **对照**：与 **盲目**（全上/不上）、**stacking**、**单一全域专家**、**普通 MoE gating**、以及**轴感知集成**对比——集成**降为对照**，只有在等成本下胜过普通 gating 才宣称新。

---

## 4 Experimental Setup / 实验设置

**Data**: NF-UNSW-NB15-v2, NF-CSE-CIC-IDS2018-v2, **CIC-IDS2017（含时间戳，供 A4a）**, + **一个非 v2 家族集（TON-IoT 或等价，待获取）** **[🔲]**.
**Models (4 族)**: XGBoost, RandomForest, MLP, RoBERTa-LoRA.
**Budget sweep**: b ∈ {0, 10, 50, 200, …} target labels.
**Metrics**: F1 / bal-acc / FPR; **mean±std over ≥5 seeds**; effect size; **BH-corrected** significance.

> **数据**：NF-UNSW-NB15-v2、NF-CSE-CIC-IDS2018-v2、**CIC-IDS2017（含时间戳 → A4a）**、+ **一个非 v2 家族集** **[🔲]**。**模型（4 族）**：XGBoost、RandomForest、MLP、RoBERTa-LoRA。**预算扫描**：b ∈ {0, 10, 50, 200, …}。**指标**：F1/bal-acc/FPR；**≥5 seed 均值±std**；效应量；**BH 校正**。

---

## 5 Results / 结果（**预注册假设，非结论**）

> ⚠️ **本节为预注册分析计划；无任何自有结果，不得把假设当结论；阈值在跑数前冻结。**

- **H1（可识别性）**：b=0 时漂移类型判不准（≈随机）；存在有限 b* 使判型显著优于随机 → 门槛曲线。
- **H2（诊断价有所值）**：等预算下"诊断驱动"优于"盲目"，BH 校正后显著。
- **H3（可修性二分）**：漂移轴可被处方显著改善；对抗轴不可（架构决定）。
- **H4（集成对照）**：轴感知集成**仅在**等成本下胜过普通 gating 才算贡献；否则并入对照表。

| 条件 | A2 跨域 | A3 对抗 | A4 漂移 | b*（判类型） | BH 显著 |
|---|---|---|---|---|---|
| 盲目（全上） | 🔲 | 🔲 | 🔲 | — | 🔲 |
| 诊断驱动 | 🔲 | 🔲 | 🔲 | 🔲 | 🔲 |
| stacking | 🔲 | 🔲 | 🔲 | — | 🔲 |
| 单一全域专家 | 🔲 | 🔲 | 🔲 | — | 🔲 |
| 普通 MoE gating | 🔲 | 🔲 | 🔲 | — | 🔲 |
| 轴感知集成 | 🔲 | 🔲 | 🔲 | — | 🔲 |

> 🔧 **缝点**：结果表**先列假设/阈值再留空**（预注册）；**删除 v0.1 的全部"预期"**。

---

## 6 Discussion & Limitations

**Take-away (to test).** Diagnosis has a **label price**; some axes are affordable, some are not — stated as hypotheses, not conclusions.

> **结论（待检验）**：诊断有**标签价格**；有的轴买得起，有的买不起——以假设形式陈述，非结论。

**Limitations.** 漂移类型仅在"近可识别区间"可判（诚实边界）；对抗仍限特征空间；多数 LLM 臂受算力限制（单 seed 标注）；条件变量/目标标签的可获取性需在部署中论证。

> **局限**：漂移类型仅"近可识别区间"可判；对抗限特征空间；LLM 臂受算力限制；条件变量/目标标签的可得性需论证。

> **删除**：v0.1 的"技术不新/已知技术"自曝段。

---

## 7 Conclusion

Diagnosis without identifiability is wishful; hardening without a price tag is incomplete. We state both, and put them on one budgeted axis.

> 无可识别性的诊断是空想；无价签的加固不完整。我们把两者都讲清，并放进同一条预算轴上。

---

## References（示例）
1. **AIN-18** (arXiv:2609.13511) — 三轴压力测试（骨架 + 复现锚点）
2. **AIN-17** (arXiv:2609.12263；**已由 arXiv 正文确认为 CCS'26，DOI:10.1145/3830454.3846576**；文献索引条目场馆待对齐)
3. Cantone et al. — 跨数据集 NIDS 泛化
4. Ben-David et al. — 域适应理论（可识别性参照）
5. SHAP-Guided FS (10.1109/ACCESS.2026.3703481) · TL-CRANN (10.3389/frai.2026.1934604) · CARD (10.1109/TDSC.2025.3562600)
6. Sarhan et al. — NetFlow v2 数据

---

## 附录 · 缝点总表（**内部注记，投稿版删除**）
| 部件 | 来源 | 动作 |
|---|---|---|
| harness / setup | AIN-18 | 复用并合并评测稿 |
| 可识别性分析 | Ben-David 等 | 加理论边界 |
| H1/H2/H3 处方 | Access'26 / TL-CRANN / CARD | 堆叠为"处方池" |
| 集成 | gating MoE | 降为**对照** |
| 故事 | "诊断有标签价格" | 编故事 |
