# Beyond Three Axes: A Multi-Axis Robustness Evaluation and Lightweight Hardening for ML-based Network Intrusion Detection
# 超越三轴：面向机器学习网络入侵检测的多轴鲁棒性评测与轻量增强

> **状态**：草稿 Draft v0.1（2026-10-09）· 项目 [`实验项目/NIDS-多轴鲁棒性/`](../AGENTS.md)
> ⚠️ **示例性质**：§5 中带 `[B]` 的是 AIN-18（arXiv:2609.13511，开源）**已发表的真实数字**，用作复现锚点；带 `🔲[Mx 待填]` 的是本工作**尚未跑出**的占位，**严禁当结果引用或对外传播**。
> 📖 **阅读约定**：每段先英文、紧跟 `>` 引用块为中文；🔧 缝点用中文，不需翻译。

---

## 故事五要素 → 论文结构

| 故事要素 | 对应章节 | 一句话 |
|---|---|---|
| 背景 | §1 开头 | 机器学习 NIDS 论文无数，几乎都在同分布上刷分 |
| **冲突** | §1 中段 | 但同分布的高分在**跨域 / 对抗**下给出**相反的模型推荐**（AIN-18），而"时间"这一维无人评 |
| 主角 | §3 | 一个**四轴统一 harness** + 轻量增强模块 |
| 情节 | §5 | 复现三轴 → 加第四轴 → 轴间交互 → 增强 |
| 主题 | §7 | 部署前必须做"**多轴体检**"，并说明哪一轴能用低成本修 |

---

## Abstract

Machine-learning-based network intrusion detection systems (NIDS) are overwhelmingly evaluated on a single axis — same-distribution accuracy — yet deployment exposes them to shifted traffic, adaptive adversaries, and protocol/attack evolution over time. Prior work shows a two-model comparison can flip its verdict between the same-distribution axis and the adversarial axis; we show the picture is still incomplete.

> 机器学习网络入侵检测系统（NIDS）绝大多数只在**单一轴**（同分布精度）上评测，但真实部署面对的是漂移流量、自适应对手，以及**协议/攻击随时间的演化**。已有工作表明，同一对模型的优劣判断会在"同分布轴"与"对抗轴"之间**反转**；我们认为这幅图景仍不完整。

We present a **four-axis** evaluation protocol that unifies same-distribution, cross-dataset, adversarial, and **temporal (concept-drift)** robustness under one harness, and we quantify **cross-axis interactions** that decide which model a practitioner should deploy.

> 我们提出一个**四轴**评测协议，在同一套 harness 下统一：同分布、跨数据集、对抗、以及**时间（概念漂移）**鲁棒性；并量化决定"该部署哪个模型"的**轴间交互**。

On two independently collected NetFlow v2 networks with a shared 43-feature schema, we find that XGBoost and RoBERTa-LoRA are statistically tied in-distribution (0.9966/0.9938 on UNSW), diverge sharply cross-network (0.8116 vs 0.6582), and reverse on the adversarial axis (0.7720 vs 0.9448 at ε=0.5); we additionally show that on the temporal axis **[🔲 M2 待填]** the ranking changes again, so that no single axis is a sufficient basis for model selection.

> 在两个独立采集、共享 43 特征的 NetFlow v2 网络集上，我们发现 XGBoost 与 RoBERTa-LoRA 在同分布下打平（UNSW：0.9966/0.9938），跨网络时急剧分化（0.8116 对 0.6582），而在对抗轴上**反转**（ε=0.5：0.7720 对 0.9448）；进一步地，在**时间轴上排名再次变化** **[🔲 M2 待填]**——因此任一单轴都不足以支撑模型选型。

We then show that a lightweight hardening stack **[🔲 M4 待填]** recovers a measurable fraction of drift-induced loss at negligible inference cost, whereas robustness to adaptive evasion is largely architecture-determined.

> 我们随后表明：一套轻量增强 **[🔲 M4 待填]** 能以近乎为零的推理开销挽回一部分漂移带来的损失；而对自适应逃逸的鲁棒性则主要由架构决定。

> 🔧 **缝点**：Abstract 骨架 = *"把 AIN-18 的三轴扩成四轴 + 补交互分析 + 补增强"*。数字沿用 baseline，未跑的先留空；**叙事照抄目标期刊摘要三段式（现状→缺口→发现）**。

---

## 1 Introduction / 引言

### Background / 背景

Deep-learning and LLM-based NIDS now report in-distribution F1 in the high 0.99s on public datasets such as UNSW-NB15 and CSE-CIC-IDS2018. Because these numbers are easy to obtain, they have become the de-facto yardstick for "which model is better".

> 基于深度学习与大模型的 NIDS，如今在 UNSW-NB15、CSE-CIC-IDS2018 等公开数据集上都能报告 0.99 以上的同分布 F1。因为容易拿到，这个数字就成了判断"哪个模型更好"的事实标准。

### The conflict / 冲突

That yardstick is fragile, and the field is beginning to document how fragile. A 2026 stress test (AIN-18) holds everything fixed except the evaluation axis and finds three different verdicts on the same two models:

> 但这个标尺很脆弱，而领域正开始记录它到底有多脆弱。一项 2026 年的压力测试（AIN-18）**只改变评测轴、其余全部固定**，结果对**同一对模型**给出了**三种不同的结论**：

| Axis / 轴 | XGBoost | RoBERTa-LoRA | Winner / 胜者 |
|---|---|---|---|
| Same-dataset (UNSW) / 同分布 | 0.9966 | 0.9938 | Tie 打平 |
| Same-dataset (CIC) / 同分布 | 0.9776 | 0.9745 | Tie 打平 |
| Cross-dataset (UNSW→CIC) / 跨域 | **0.8116** | 0.6582 | XGBoost |
| Cross-dataset (CIC→UNSW) / 跨域 | 0.0730 | 0.0599 | both collapse 双双崩塌 |
| Adversarial (ε=0.5) / 对抗 | 0.7720 | **0.9448** | RoBERTa |

The same study shows F1 alone is actively misleading: RoBERTa's "moderate" cross-network F1 of 0.6582 hides an FPR of 0.7756 and a balanced accuracy of 0.5477 — it is barely better than chance.

> 该研究还表明**仅看 F1 会误导**：RoBERTa 跨网络的"中等"F1 = 0.6582，掩盖了 **FPR = 0.7756、balanced accuracy = 0.5477**——几乎只比随机猜好一点（它靠把大量良性流量误判为攻击来维持召回）。

In parallel, AIN-17 shows that, for graph NIDS, pipeline choices (snapshot window, preprocessing) dominate architectural complexity, and 18/18 detector–dataset pairs cannot even alert in streaming. The message is uncomfortable: the published metric often measures the evaluation setup, not the model.

> 与此同时，AIN-17 表明对图 NIDS 而言，**流水线选择（快照窗口、预处理）压过架构复杂度**，且 18/18 个"检测器–数据集"组合**都无法做到事件到达即告警**。结论令人不安：**发表的指标常常衡量的是评测装置，而不是模型**。

### The gap / 缺口

Three things remain open, and they are exactly what a deployment decision needs:

> 还有三件事悬而未决，而它们恰恰是部署决策必需的：

**(1) The "time" axis is missing.** Traffic, protocols and attack tooling evolve after deployment; a model is trained once and frozen. Neither prior study evaluates temporal/concept drift on the same harness.

> **（1）缺"时间"轴**：部署后流量、协议、攻击工具都在演化，而模型训练一次即冻结；前述两篇均未在同一 harness 上评测**时间/概念漂移**。

**(2) Interactions are unquantified.** We know single axes can flip a verdict, but not which combinations flip it, nor how the recommendation moves as two stressors co-occur (e.g. shifted and adversarial).

> **（2）交互未被量化**：我们知道单轴能翻转结论，但不知道**哪些组合**会翻转，也不知道两种压力**同时出现**（如既漂移又对抗）时推荐如何移动。

**(3) Diagnosis without remedy.** Both prior studies diagnose fragility; neither offers a cheap fix. A practitioner who learns "my model collapses under drift" still has no actionable lever.

> **（3）只诊断、不给药**：两篇都诊断了脆弱性，**都没给出低成本解法**。一个得知"我的模型在漂移下会崩"的工程师，仍然没有可操作的抓手。

### The protagonist and contributions / 主角与贡献

We close these gaps by extending an existing, complete harness rather than building a new one — the fastest defensible path to a robust artifact:

> 我们**复用一套现成且完整的 harness、在其上做扩展**，而不是从零造新系统——这是通往"站得住的成果"最快的路径：

- **(A) Axis IV — temporal drift**: we add a time-based evaluation axis (temporal split + graded concept drift) alongside the three existing axes.
- **(B) Cross-axis interaction analysis**: we report model rankings as a function of joint condition, and quantify transfer directionality and metric sensitivity (F1 vs FPR vs balanced accuracy).
- **(C) Lightweight hardening**: we test inexpensive, model-agnostic remedies (time-aware re-weighting, domain adaptation, feature selection) and report which axis each one can actually buy.

> - **（A）第四轴——时间漂移**：在既有三轴之外，增加基于时间的评测轴（时间切分 + 分级概念漂移）。
> - **（B）轴间交互分析**：把模型排名表示为**联合条件**的函数，并量化迁移方向性与指标敏感性（F1 vs FPR vs balanced accuracy）。
> - **（C）轻量增强**：测试廉价、与模型无关的手段（时间感知重加权、域适应、特征选择），并报告每个手段**真正能改善哪一轴**。

### Thesis / 主题

Our thesis is simple and, we argue, overdue: a model should be selected by a multi-axis "deployment physical", not by a single number. We make the protocol and code public so that reporting four axes is as easy as reporting one.

> 我们的主张简单，而且（我们认为）早该如此：**模型应由"多轴部署体检"来选，而不是由单一数字来选。** 我们公开协议与代码，让"报告四个轴"和"报告一个轴"一样省事。

> 🔧 **缝点**：Introduction 是这条路线里**最值钱、也唯一不能缝**的一节——套路固定：**背景一句 → 抛冲突（引 AIN-18/17 的相反结论）→ 列三个缺口（时间轴缺/交互缺/只诊断不修）→ 主角登场（恰好对应三创新点）→ 主题升华**。表格直接搬 AIN-18 README 的 headline 表（真实数字，注明出处）。

---

## 2 Related Work / 相关工作

**ML/DL for NIDS.** LSTM/autoencoder/graph detectors, typically single-axis; surveys note weak cross-dataset generalization.

> **NIDS 的机器学习**：LSTM/自编码器/图检测器，通常都是单轴评测；综述已指出跨数据集泛化差。

**Cross-dataset generalization.** Cantone et al. document near-perfect same-dataset numbers collapsing under network shift across four datasets; AIN-18 extends this to a matched two-model, three-axis protocol.

> **跨数据集泛化**：Cantone 等发现在四个数据集上"同分布近乎完美、一换网络就崩"；AIN-18 把它扩展成"两模型三轴"的匹配协议。

**Adversarial robustness of NIDS.** Feature-space evasion and the "FPR-checking" discipline.

> **NIDS 的对抗鲁棒性**：特征空间逃逸攻击，以及"必须同时报 FPR"的纪律。

**Concept drift in traffic analysis.** AIN-6 empirically shows encrypted-traffic classifiers degrade under data drift.

> **流量分析中的概念漂移**：AIN-6 实证了加密流量分类器在数据漂移下显著退化。

**Evaluation validity.** AIN-17 (pipeline-dominated GIDS results, streaming-readiness) and AIN-9/10 (label provenance and protocol drift in encrypted-traffic benchmarks) establish "evaluation validity" as a first-class contribution.

> **评测有效性**：AIN-17（流水线主导 GIDS 结果、流式就绪性）、AIN-9/10（加密流量基准的标签来源与协议漂移审计）——都把"评测有效性"确立为一等贡献。

**Positioning.** To our knowledge, no prior work places same-distribution, cross-domain, adversarial, and temporal robustness on one NIDS harness and then quantifies their interactions and offers hardening.

> **定位**：据我们所知，**没有**先前工作把同分布、跨域、对抗、时间四种鲁棒性放在**同一 harness** 上，并进一步量化它们的交互、还给出增强。

> 🔧 **缝点**：Related Work = **抄目标期刊的"三层结构"（领域 → 最近邻两条线 → 一句 positioning）**。每段一句话挂 1–2 篇；最后一句必须直说"没人同时做过这四轴 + 交互 + 增强"。

---

## 3 Approach / 方法

> 🔧 **缝点总纲**：§3 是"缝"的主战场——**baseline 提供 3.1 的整套 harness，我们只"加一条轴、加一层分析、加一组模块"。**

### 3.1 The four-axis protocol (reused harness) / 四轴协议（复用 harness）

We adopt, unchanged, the fair evaluation harness of AIN-18 (`run_full_benchmark`), which trains and scores every model under matched conditions with a single `evaluate()` (F1, precision, recall, balanced accuracy, FPR, FNR, throughput) and balanced 50k-per-class sampling.

> 我们**原样采用** AIN-18 的公平评测 harness（`run_full_benchmark`）：在同一批匹配条件下训练并评分所有模型，统一用同一个 `evaluate()`（F1、precision、recall、balanced accuracy、FPR、FNR、吞吐），并采用每类 50k 的均衡采样。

> 🔧 **缝点 A（复用）**：直接调用 `src/evaluation.py::run_full_benchmark` + `src/data_loading.py::load_and_clean`。**不改第三方源码**——"缝"的第一原则。

### 3.2 Axis IV — temporal / concept drift (new) / 第四轴（新增）

We add a fifth condition family to the same harness: (i) a **temporal split** (train on the earlier portion, test on the later, time-ordered), and (ii) **graded drift** by mixing a fraction λ ∈ {0, .25, .5, .75, 1} of the other network's traffic into the test stream. Both reuse the existing loaders; only the splitter/mixer is new.

> 我们在同一 harness 上增加第五类条件：(i) **时间切分**（按时间先后，前段训练、后段测试）；(ii) **分级漂移**——把另一个网络的流量按比例 λ ∈ {0, .25, .5, .75, 1} 混入测试流。两者都复用既有数据加载器，**只新增切分/混合代码**。

> 🔧 **缝点 B（加模块）**：新代码 `axis_temporal.py`；**接口照抄 baseline 的 `(df_src, df_tgt) → results dict`**，从而可被同一 `evaluate()` 复用——这是"可插拔模块"的标准做法。

### 3.3 Cross-axis interaction analysis (new) / 轴间交互分析（新增）

Rather than reporting axes in isolation, we report the ranking function r(condition) over models, detect rank reversals between axes, and evaluate co-occurring stressors (shifted+adversarial; drifted+frozen) plus metric sensitivity (F1- vs FPR/balanced-accuracy-based rankings).

> 我们不孤立地报各轴，而是给出**模型上的排序函数 r(条件)**、检测**轴间排序翻转**，并评估**共现压力**（漂移+对抗；漂移+冻结）以及**指标敏感性**（基于 F1 与基于 FPR/balanced-accuracy 的排名差异）。

> 🔧 **缝点 C（换摆法）**：几乎零新算法——把 baseline 已有的条件输出**并排成"条件 × 模型 × 指标"三维表**，再算排序翻转。**创新点常常不是新算法，而是新的"摆法"。**

### 3.4 Lightweight hardening (new) / 轻量增强（新增）

We plug three model-agnostic remedies behind the same harness: **H1 time-aware re-weighting** (down-weight training samples far from the deployment era); **H2 domain adaptation** (feature-statistic alignment, e.g. quantile/standardization alignment, optional CORAL moment matching); **H3 per-axis feature selection** (re-derive the leak-free feature set per axis instead of one fixed 29-feature set).

> 我们在同一 harness 后插入三个与模型无关的手段：**H1 时间感知重加权**（离部署时间越远的训练样本权重越低）；**H2 域适应**（源/目标特征统计对齐，如分位数/标准化对齐，可选 CORAL 矩匹配）；**H3 逐轴选特征**（每轴重选无泄漏特征，而非固定一套 29 特征）。

> 🔧 **缝点 D（堆叠）**：H1–H3 全是"通用模块"，从别处搬到本任务——正是裁缝的"复刻/堆叠"思想。每个模块只需在 baseline 的 `evaluate()` 前后各插一行。

---

## 4 Experimental Setup / 实验设置

**Datasets.** NF-UNSW-NB15-v2 and NF-CSE-CIC-IDS2018-v2 (UQ NetFlow v2, shared 43-feature schema); balanced 50k/class; binary benign-vs-attack (the two networks' attack taxonomies are near-disjoint).

> **数据**：NF-UNSW-NB15-v2 与 NF-CSE-CIC-IDS2018-v2（UQ NetFlow v2，共享 43 特征 schema）；每类均衡 50k；二分类（良性 vs 攻击），因为两网络的攻击构成几乎不重叠。

**Models.** XGBoost (100 trees, seeds 42–45); RoBERTa-base + LoRA (r=8, α=16, q/k/v), flow serialized as `FEATURE=value …` text.

> **模型**：XGBoost（100 棵树，seed 42–45）；RoBERTa-base + LoRA（r=8、α=16，作用在 q/k/v），流记录序列化为 `FEATURE=value …` 文本。

**Axes.** A1 same-distribution (×2); A2 cross-dataset (bidirectional); A3 adversarial (feature-space linear interpolation toward the benign centroid, ε∈[0,1], 10 steps, benign flows included in eval); **A4 temporal/drift (new)**.

> **轴**：A1 同分布（×2）；A2 跨数据集（双向）；A3 对抗（特征空间向良性质心的线性插值，ε∈[0,1] 共 10 档，评测集含良性流以便测 FPR）；**A4 时间/漂移（新增）**。

**Metrics.** F1, precision, recall, balanced accuracy, FPR, FNR, throughput — always reported together.

> **指标**：F1、precision、recall、balanced accuracy、FPR、FNR、吞吐——始终一起报告。

**Hardware.** **[🔲 待填：Windows 原生 / CPU；RoBERTa 臂视算力而定]**

> **硬件**：**[🔲 待填：Windows 原生 / CPU；RoBERTa 臂视算力而定]**

> 🔧 **缝点**：§4 = 把 baseline README 的 Method summary **压缩 + 加一行 A4**。审稿人极看重"是否公平可比"，故共享 schema / 均衡采样 / 同一 evaluate() 必须写清。

---

## 5 Results / 结果

> ⚠️ `[B]` = AIN-18 已发表真实值（复现锚点）；`🔲` = 本工作待跑，**不得引用**。

### 5.1 Reproducing the three axes (M1) / 复现三轴

| Condition / 条件 | XGBoost | RoBERTa-LoRA | Verdict / 结论 |
|---|---|---|---|
| Same UNSW | 0.9966 **[B]** | 0.9938 **[B]** | Tie 打平 **[B]** |
| Same CIC | 0.9776 **[B]** | 0.9745 **[B]** | Tie 打平 **[B]** |
| Cross UNSW→CIC | 0.8116 **[B]** | 0.6582 **[B]** | XGBoost **[B]** |
| Cross CIC→UNSW | 0.0730 **[B]** | 0.0599 **[B]** | both collapse 双双崩塌 **[B]** |
| Adversarial ε=0.5 | 0.7720 **[B]** | 0.9448 **[B]** | RoBERTa **[B]** |

Our reproduction (M1) matches these within **[🔲 M1 待填]** points (G1 判据：XGBoost 跨域 F1 掉幅 ≥ 10 点).

> 我们的复现（M1）与上述值的差距在 **[🔲 M1 待填]** 点以内（G1 判据：XGBoost 跨域 F1 掉幅 ≥ 10 点）。

> 🔧 **缝点**：§5.1 = **纯复现**，直接引 baseline 数字 + 自己的复现值。**这是裁缝最稳的"地基段"**——先证明"我能跑通人家的结果"，审稿信赖度立刻上来。

### 5.2 Axis IV: temporal / concept drift (M2) / 第四轴：时间/概念漂移

| λ (foreign fraction 混入比例) | XGBoost | RoBERTa | ranking 排名 |
|---|---|---|---|
| 0.00 | 🔲 | 🔲 | 🔲 |
| 0.25 | 🔲 | 🔲 | 🔲 |
| 0.50 | 🔲 | 🔲 | 🔲 |
| 1.00 | 🔲 | 🔲 | 🔲 |

**Falsifiable claim:** the temporal axis induces a rank reversal relative to the same-distribution axis, adding a fourth distinct verdict.

> **可证伪断言**：时间轴会相对同分布轴造成**排序翻转**，从而增加**第四种**不同结论。

> 🔧 **缝点**：§5.2 = **新轴**。表格在跑之前就搭好（"表格先行"），数字后填。**G2 判据就是这张表到底翻不翻转。**

### 5.3 Cross-axis interactions (M3) / 轴间交互

Ranking matrix over {A1,A2,A3,A4} × {XGB, RoBERTa} × {F1, FPR, bal-acc} → 🔲 待填（含"漂移+对抗"共现条件）。

> {A1,A2,A3,A4} × {XGB, RoBERTa} × {F1, FPR, bal-acc} 的排名矩阵 → 🔲 待填（含"漂移+对抗"共现条件）。

### 5.4 Hardening (M4) / 增强

| Remedy / 手段 | A2 增益 | A3 增益 | A4 增益 | 推理开销 |
|---|---|---|---|---|
| H1 time-reweight | 🔲 | 🔲 | 🔲 | ~0 |
| H2 domain align | 🔲 | 🔲 | 🔲 | ~0 |
| H3 per-axis feats | 🔲 | 🔲 | 🔲 | 0 |

> 🔧 **缝点**：§5.4 = **增强模块**。判据 G3：若某模块没有可测增益，就删掉它——**宁缺勿灌**。

---

## 6 Discussion & Limitations / 讨论与局限

**Implication.** Multi-axis reporting should be mandatory; a single number can recommend the wrong model.

> **含义**：多轴报告应成为强制项；单一数字可能推荐出**错误**的模型。

**Which lever works.** **[🔲 待填]** — 初步预期"漂移"可被 H1/H2 部分修复，而"对抗"主要由架构决定（与 AIN-18 的观察一致）。

> **哪根杠杆有效**：**[🔲 待填]**——初步预期：漂移可被 H1/H2 部分修复，而对抗鲁棒性主要由架构决定（与 AIN-18 一致）。

**Limitations.**（照抄 baseline 的诚实清单，再加 A4 相关）单机队两数据集；特征空间对抗 ≠ problem-space 可实现；二元标签掩盖攻击子类；RoBERTa 单架构单 seed；文本序列化给 LLM 额外的特征名锚点。**新增**：A4 的"漂移"为受控合成（混入异网络流量 / 时间切分），非真实跨时间采集。

> **局限**：单机队、仅两数据集；特征空间的对抗**不保证**在真实问题空间可实现；二元标签掩盖攻击子类；RoBERTa 单架构单 seed；文本序列化给 LLM 额外的特征名锚点。**新增**：A4 的"漂移"是**受控合成**（混异网流量/时间切分），并非真实跨时间采集。

> 🔧 **缝点**：Limitations 直接**借用 baseline 与 AIN-17 的自陈局限**（它们已经替你想好审稿人会问什么），只补 A4 的新局限。

---

## 7 Conclusion / 结论

Evaluation practice, not model capacity, often decides the reported winner. We extended an existing three-axis NIDS stress test into a four-axis protocol, quantified cross-axis interactions, and showed which robustness failures are cheaply fixable and which are not. Our call to action: report the multi-axis physical, or your "SOTA" is a statement about your testbed.

> 决定"谁赢"的，往往不是模型能力，而是**评测实践**。我们把既有的三轴 NIDS 压力测试扩展为**四轴**协议，量化了**轴间交互**，并区分了哪些鲁棒性缺陷**能低成本修复**、哪些不能。我们的号召是：**请报告多轴体检，否则你的"SOTA"只是在描述你的测试床。**

> 🔧 **缝点**：Conclusion = 主题升华，**一句话回扣 Introduction 的冲突**，不引入任何新信息。

---

## References / 参考文献（示例格式，正式版全部替换为真实 BibTeX）

1. Atif & Ali. *A Three-Axis Stress Test of LLM vs Classical ML for NIDS…* 2026. arXiv:2609.13511. **[AIN-18]**
2. Zhao & Hassan. *A First-Principles Evaluation of Graph-Based NIDS.* 2026. CCS. **[AIN-17]**
3. Cantone et al. Cross-dataset NIDS generalization. **[AIN-18 引 [5]]**
4. Sarhan, Layeghy, Portmann. *NetFlow v2 NIDS datasets.* **[data]**
5. Malekghaini et al. *ETC under data drift.* 2023. Computer Networks. **[AIN-6]**
6. *(相关 8–15 篇，正式写作时从 `文献索引.md` AIN 节补全)*

---

## 附录 A · "缝点"总表（这篇稿子是怎么"缝"出来的）

| 论文部件 | 来源 | 动作 |
|---|---|---|
| Abstract 骨架 / Introduction 冲突 / 表 1 | AIN-18 README headline | **搬**（注明出处） |
| §3.1 harness / §4 setup / §6 limitations | AIN-18 `src/` + README | **复用**（不改源码） |
| §3.2 第四轴（时间/漂移） | 新写 `axis_temporal.py` | **加模块**（接口对齐 baseline） |
| §3.3 轴间交互 | baseline 已有输出重排 | **换摆法**（零新算法） |
| §3.4 / §5.4 增强 H1–H3 | 通用技术（重加权/域适应/特征选择） | **堆叠**（搬到本任务） |
| §2 Related Work | `文献索引.md` AIN 节 | **三步结构 + 一句 positioning** |
| 图（摘要图/框架图/结果图） | 三张图规范 | M5 再画 |

> **一句话**：这篇稿子**没有一处是全新发明**——但它在**同一 harness 上叠了一条新轴 + 一层新分析 + 一组新模块**，并用"**单轴评测会误导**"这条冲突把它串起来。这就是"学术裁缝 + 讲故事"的标准产线；只要**数据是真跑出来的**，它就不越线。
