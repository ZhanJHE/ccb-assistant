# 硬件 Offload 加速 LLM 推理（FPGA / DPU-SmartNIC / SSD）文献调研

> 调研日期：2026-09；面向：即将读研、具备 Verilog（手写过单周期 CPU）+ vLLM 工程（learned KV eviction、trace-driven 仿真）背景的本科生。
> 目标会议（**依官方《第七版 CCF 推荐目录》核对，2026-09-27 更正**）：CCF-B —— ICCD、ICCAD、DATE、ICPP、Euro-Par、MSST、FPGA、ICDCS；CCF-C —— FCCM、FPL、FPT、ICPADS、SYSTOR。期刊 CCF-B —— **TCC、JPDC**（**TOS 与 TACO 实为 A 类**，此前误标为 B；TCAD、TC、TPDS 亦为 A 类）。
> 铁律：下表每条都经 arXiv 页面 / Crossref / USENIX 官网实际打开验证；无法证实者明确标注"待核实"，绝不凭记忆编造。

---

## 0. 一句话总览

LLM 推理的瓶颈已从"算力"转向"**显存容量与 KV cache 搬运**"。三条硬件技术路线分别从不同角度切入：

1. **FPGA**：以极致低比特（2–4bit / 三值）+ 稀疏 + 数据流，把**压缩后的 KV 操作与 attention** 做进可重构逻辑；小器件只能做"窄而深"的 KV 相关算子，不能碰大矩阵乘。
2. **SSD / 多级存储**：把 KV cache 当作 OS 里的"页"，在 **GPU HBM → CPU DRAM → SSD/NVMe（甚至 CXL）** 之间分层换入换出，用容量换成本。
3. **DPU / SmartNIC**：把 KV 的**网络搬运、压缩/反量化、调度**从主机 CPU/GPU 卸载到网卡；2024–2026 处于"系统概念快速涌现、专门的 KV 算子级 offload 仍很少"的阶段——这正是选题空白所在。

---

## 1. 技术路线分类（按 5 个子方向）

### 路线 A：FPGA 加速 LLM 推理（代表：FlightLLM 及 2024–2026 后续）

| 论文 | 年份/会议 | 核心思路 | 权衡/局限 |
|---|---|---|---|
| **FlightLLM** [arXiv:2401.03868](https://arxiv.org/abs/2401.03868) | 2024 / FPGA | 完整 mapping flow：可配置稀疏 DSP chain + **always-on-chip decode**（KV 常驻片上）+ 长度自适应编译；U280 能效 6× V100S | 用的是**数据中心级** U280/VHK158（HBM、千级 DSP）；小 FPGA 无法复制其矩阵算力 |
| **AccLLM** [arXiv:2505.03745](https://arxiv.org/abs/2505.03745) | 2025 | W2A8**KV4**（2bit 权重 / 8bit 激活 / **4bit KV**）+ pruning + Λ-shaped attention 的软硬协同 | 精度激进，长上下文质量仍需逐模型验证 |
| **FAST-Prefill** [arXiv:2602.20515](https://arxiv.org/abs/2602.20515) | 2026 | FPGA 上稀疏 **prefill** attention（多数 FPGA 工作只优化 decode） | 稀疏模式的在线判定开销 |
| **Hummingbird** [arXiv:2507.03308](https://arxiv.org/abs/2507.03308) | 2025 / ICCAD | **嵌入式 FPGA**（资源极小）上"更小更快"的 LLM 加速器 | 与 XC7A35T 量级最接近的参考之一 |
| **TeLLMe / TeLLMe v2** [2504.16266](https://arxiv.org/abs/2504.16266) · [2510.15926](https://arxiv.org/abs/2510.15926) | 2025 | BitNet 式**三值** LLM 边缘加速，table-lookup matmul，prefill+decode 端到端 | 依赖三值量化生态，通用性受限 |
| **TENET** [arXiv:2509.13765](https://arxiv.org/abs/2509.13765) | 2025 | **LUT-centric**、稀疏感知的三值推理架构 | 同上 |
| **PD-Swap** [arXiv:2512.11550](https://arxiv.org/abs/2512.11550) | 2025 | 用**动态部分重配置（DPR）**在 prefill/decode 两套逻辑间切换 | 重配置延迟需被摊薄；思路新颖，适合小器件"一片多用" |
| **StreamTensor** [arXiv:2509.13694](https://arxiv.org/abs/2509.13694) | 2025 / MICRO | FPGA 数据流加速器中的张量流式化（tiling/kernel fusion/资源分配） | 偏编译/调度框架 |
| **ELiTeFormer** [arXiv:2607.03652](https://arxiv.org/abs/2607.03652) | 2026 | FPGA 上 **attention 与 FFN 联合**协同（多数工作只做其一） | 资源需求仍较高 |

> **怎么看**：FPGA LLM 工作分两类——(i) 数据中心 FPGA（U280/VHK158，HBM）正面对标 GPU；(ii) 边缘/嵌入式 FPGA 靠**超低比特 + 稀疏 + 部分重配置**取胜。XC7A35T 属于后者中资源**最紧张**的一档（仅 ~90K logic cells、少量 DSP、DDR3），只能承载 KV 相关的窄算子（见 §2）。

### 路线 B：KV 特定操作的硬件/架构（量化、压缩、attention 内核）

| 论文 | 年份/会议 | 核心结论 |
|---|---|---|
| **SpAtten** [arXiv:2012.09852](https://arxiv.org/abs/2012.09852) · [DOI](https://doi.org/10.1109/HPCA51647.2021.00018) | 2021 / HPCA | 级联 **token pruning + head pruning** 的稀疏 attention 专用架构（经典开山） |
| **Energon** [arXiv:2110.09310](https://arxiv.org/abs/2110.09310) | 2022 | **动态**稀疏 attention，面向边缘加速 |
| **ALISA** [arXiv:2403.17312](https://arxiv.org/abs/2403.17312) | 2024 / ISCA | 稀疏感知 KV caching 的加速架构 |
| **FlashAttention** [arXiv:2205.14135](https://arxiv.org/abs/2205.14135) | 2022 | **IO 感知 + 分块 + 在线 softmax**，精确 attention 大幅减少 HBM 读写（算法奠基） |
| **FlashAttention-3** [arXiv:2407.08608](https://arxiv.org/abs/2407.08608) | 2024 | Hopper **异步**（warp specialization / TMA）+ **FP8**，H100 1.5–2× |
| **KIVI** [arXiv:2402.02750](https://arxiv.org/abs/2402.02750) | 2024 / ICML | 免调优**非对称 2bit KV**：key 按通道、value 按 token 量化 |
| **H2O** [arXiv:2306.14048](https://arxiv.org/abs/2306.14048) | 2023 | **Heavy-hitter oracle** KV 驱逐，大幅省显存、保精度（软件经典，与你做过的 learned eviction 直接相关） |

> 关键点：**KV 量化/反量化、稀疏索引生成、top-K/heavy-hitter 选择、在线 softmax** 都是"**数据量中等、逻辑规则、低精度/整型友好**"的算子——这正是小 FPGA/DPU 的甜点，而 GPU 做它们反而效率低、占主机 CPU。

### 路线 C：KV cache 换页到 SSD / DRAM 的多级系统

| 论文 | 年份/会议 | 核心机制 |
|---|---|---|
| **PagedAttention / vLLM** [arXiv:2309.06180](https://arxiv.org/abs/2309.06180) | 2023 / SOSP | OS 式**分页**管理 KV，近零碎片，2–4× 吞吐（一切工作的地基） |
| **Pensieve** [arXiv:2312.05516](https://arxiv.org/abs/2312.05516) | 2024 / OSDI | 多轮会话中把历史 KV **换出到 CPU/SSD**，纯 GPU 方案大幅省显存 |
| **FlexGen** [arXiv:2303.06865](https://arxiv.org/abs/2303.06865) | 2023 / ICML | GPU/CPU/磁盘多级、块调度与计算-IO 重叠的高吞吐单卡离线推理 |
| **InfiniGen** [arXiv:2406.19707](https://arxiv.org/abs/2406.19707) | 2024 / OSDI | **动态 KV 管理 + 按需换入预测**的 offloading 推理 |
| **CachedAttention** [arXiv:2403.19708](https://arxiv.org/abs/2403.19708) | 2024 / USENIX ATC | 跨多轮会话复用 KV，减少重复 prefill |
| **InstInfer**（原名 InstAttention）[arXiv:2409.04992](https://arxiv.org/abs/2409.04992) | 2024 | **存储侧 offload attention**，低成本长上下文（与 SSD/近存交叉） |
| **LMCache** [arXiv:2510.09665](https://arxiv.org/abs/2510.09665) | 2025 | 企业级 KV 缓存层：跨实例复用 + CPU/磁盘扩展 |
| **Strata** [arXiv:2508.18572](https://arxiv.org/abs/2508.18572) | 2025 | 长上下文**分层** context caching |
| **SpectrumKV** [arXiv:2606.08635](https://arxiv.org/abs/2606.08635) | 2026 | PD 分离下按 token 分配 **FP16/INT8/INT4** 精度，减少 KV **网络传输** |
| **CacheBlend** [arXiv:2405.16444](https://arxiv.org/abs/2405.16444) | 2024 / EuroSys | RAG 中复用**非前缀** KV 并融合 |

> **vLLM 官方 KV offloading**：2026-01 vLLM 发布 KV Offloading Connector（[官方博客](https://vllm.ai/blog/2026-01-08-kv-offloading-connector)），把 KV 透明换出到外部内存以最大化吞吐——说明"外部 KV 层"已是主流引擎的官方方向。

### 路线 D：DPU / SmartNIC 上的 LLM serving 与 KV 搬运

| 论文 | 年份 | 与 KV offload 的关系 |
|---|---|---|
| **Mooncake** [arXiv:2407.00079](https://arxiv.org/abs/2407.00079) | 2024 | Kimi 的 **KVCache-centric** prefill/decode 分离架构 + 全局 KV 池（工业级标杆） |
| **Splitwise** [arXiv:2311.18677](https://arxiv.org/abs/2311.18677) | 2024 / ISCA | prefill/decode **阶段拆分**，KV 在两池间传递 |
| **ShadowServe** [arXiv:2509.16857](https://arxiv.org/abs/2509.16857) | 2025 | 分布式 prefix caching 中**无干扰 KV 取数** + 最小拷贝数据面 |
| **Blink** [arXiv:2604.07609](https://arxiv.org/abs/2604.07609) | 2026 | 把 serving 栈委托给 **GPU + SmartNIC**，实现"无 CPU"推理（SmartNIC 承担连接/调度/搬运） |
| **（技术报告）** Skews detectable from DPU [arXiv:2509.18114](https://arxiv.org/abs/2509.18114) | 2025 | 用 BlueField-3 在 decode 期检测/缓解 TP 推理负载不均（非正式发表，仅作线索） |

> **重要判断**：截至 2026-09，**专门把 KV 的量化/反量化/重排算子做进 DPU 数据面**的成熟论文仍然很少——现有工作多把 SmartNIC 当作"快速搬运 + 调度"的角色（Mooncake、Blink、ShadowServe）。**"在 BlueField 上做 KV 算子级 inline offload" 是清晰的空白**，且与你的 vLLM 工程经验高度契合。

### 路线 E：SmartNIC 上的 KV 存储/缓存系统（经典，思想可迁移）

| 论文 | 年份/会议 | 核心贡献 |
|---|---|---|
| **KV-Direct** [DOI:10.1145/3132747.3132756](https://doi.org/10.1145/3132747.3132756) | 2017 / SOSP | 可编程 NIC **直连远端内存**的高性能 KV，绕开主机 |
| **iPipe** [DOI:10.1145/3341302.3342079](https://doi.org/10.1145/3341302.3342079) | 2019 / SIGCOMM | 多核 SoC SmartNIC 上构建/卸载分布式应用的**通用框架** |
| **LineFS** [DOI:10.1145/3477132.3483565](https://doi.org/10.1145/3477132.3483565) | 2021 / SOSP | 文件系统数据面**流水线并行**卸载到 SmartNIC |
| **ReDMArk**（背景，非 LLM）[USENIX 页面](https://www.usenix.org/conference/usenixsecurity21/presentation/rothenberger) | 2021 / USENIX Security | RDMA 安全机制与 RNIC 行为评估，帮助理解 RDMA/NIC 能力边界 |

---

## 2. 对小 FPGA（Artix-7 XC7A35T）与 BlueField 的可行性判断

### XC7A35T 的资源量级（务必正视）
- **33,280 logic cells / 20,800 LUT / 41,600 FFs**、**90 个 DSP48E1**、**50 × 36Kb BRAM = 1.8Mb ≈ 225 KB**，外接板载 **DDR3**（无 HBM、无硬核 CPU）。（数字为 Xilinx DS180/Artix-7 product table 标准值。）
- 达芬奇板接口约束：**以太网为 10/100M（LAN8720，峰值 ≈12.5MB/s），非千兆**；无直连主机 PCIe 通道。
- 对比：FlightLLM 用的 U280 有 **~1M+ LUT、9024 DSP、HBM**；Hummingbird/TeLLMe 面向的"嵌入式 FPGA"也多为更大的 Zynq UltraScale+。
- 结论：**35T 的 LUT/DSP 约为 U280 的 1/50~1/100**，做不了任何 LLM 的矩阵乘主算力，甚至装不下完整 KV。

### 35T 上**适合**做的（窄而深的 KV 算子 / 控制-网络类）
1. **KV 低比特反量化/打包**（INT4/INT8 ↔ FP16 的流式重排）——纯整型、规则、高吞吐。
2. **KV 稀疏索引生成 / top-K / heavy-hitter 选择**（H2O 式 score 排序/选择的硬件化）。
3. **分页/块表管理与 DMA 引擎**：PagedAttention 式 block table、gather/scatter、DDR3 地址翻译。
4. **RoPE/简单逐元素算子**、attention 中 softmax 的**片上近似**（查表/分段线性）。
5. 作为 **GPU/CPU 的外挂协处理器**：以太网/DMA 进、做 KV 压缩、再出——**不参与 GEMM**。

### 35T 上**不适合**做的
- 任何 layer 的 QKV/FFN **矩阵乘主算力**（DSP 数量差两个数量级）。
- 完整 KV/模型的片上驻留（片上 BRAM 仅 ≈225KB）。
- 高带宽 HBM 级流式 attention（只有 DDR3，带宽 ~10GB/s 且位宽窄）。

### BlueField（若为 BF-2）
- BF-2 = 8 核 A72 Arm + ConnectX-6 DX 网络引擎 + DDR，**可跑 DOCA/RDMA**，但数据面可定制逻辑远不如 FPGA 自由。
- BF-2 适合：**KV 的 RDMA 搬运、连接/调度、轻量压缩**；若要做复杂 KV 算子，建议 **BlueField 负责传输 + Artix 负责 KV 算子** 的 FPGA-in-the-loop，或升级到 BF-3（含 DPA 数据路径加速器，已有 KV 树/ordered store 工作，[arXiv:2601.06231](https://arxiv.org/abs/2601.06231)）。

---

## 3. 研究空白（6–9 个月可做原型）

> 每条都给出最相关的 2–3 篇先行论文。

1. **DPU/SmartNIC 上 KV 算子级 inline offload**：把 KV 反量化/重排做进网卡数据面，GPU 收到即用。
   - 先行：Mooncake（2407.00079）、Blink（2604.07609）、KIVI（2402.02750）。
2. **小 FPGA 上的 KV 压缩/解协处理器 + vLLM 集成**：FPGA 经以太网/DMA 接入，作为 vLLM 的 KV codec/block-manager 外挂。
   - 先行：FlightLLM（2401.03868）、PD-Swap（2512.11550）、PagedAttention（2309.06180）。
3. **硬件加速的 learned/heavy-hitter KV eviction**：把你已做过的 learned eviction 的打分/选择关键路径做进 FPGA/DPU，降低在线开销。
   - 先行：H2O（2306.14048）、ALISA（2403.17312）、SpAtten（2012.09852）。
4. **SSD↔GPU KV 换页的硬件化 gather/prefetch 引擎**：针对 KV 块的确定性访问做直接路径与预测预取。
   - 先行：Pensieve（2312.05516）、InfiniGen（2406.19707）、InstInfer（2409.04992）。
5. **混合精度 KV 传输的硬件执行单元**：SpectrumKV 提出按 token 分 FP16/INT8/INT4，但只做了软件/GPU timing；其**网络侧/网卡侧执行与打包**尚无人实现。
   - 先行：SpectrumKV（2606.08635）、Mooncake（2407.00079）、ShadowServe（2509.16857）。
6. **小器件"一片多用"的 DPR 调度**：PD-Swap 验证了 prefill/decode 逻辑切换，但**重配置时机与服务 SLO 的协同**仍是开放问题。
   - 先行：PD-Swap（2512.11550）、FAST-Prefill（2602.20515）。
7. **Tofino/交换机内 attention 前缀聚合**（高风险高新意）：在 P4 数据面做有限状态的 KV/attention 前缀操作。
   - 先行：路线 E 的 iPipe/KV-Direct + FlashAttention 思想（注：任务提到的 "iAttention" 未能证实，见 §5）。

---

## 4. 论文清单（25 篇核心，表格）

| # | 标题 | 一作（前2） | 年份/出处 | 链接 | 引用* | 一句话结论 |
|---|---|---|---|---|---|---|
| 1 | FlightLLM | Shulin Zeng 等 | FPGA'24 | [arXiv](https://arxiv.org/abs/2401.03868) | 175 | FPGA 完整 mapping flow 跑压缩 LLM，能效对标 GPU |
| 2 | AccLLM | Yanbiao Liang 等 | 2025 | [arXiv](https://arxiv.org/abs/2505.03745) | — | W2A8KV4 软硬协同长上下文 |
| 3 | FAST-Prefill | R. Jayanth, V. Prasanna | 2026 | [arXiv](https://arxiv.org/abs/2602.20515) | — | FPGA 稀疏 prefill attention |
| 4 | Hummingbird | Jindong Li 等 | ICCAD'25 | [arXiv](https://arxiv.org/abs/2507.03308) | — | 嵌入式 FPGA 上的小型 LLM 加速器 |
| 5 | TeLLMe / v2 | Ye Qiao 等 | 2025 | [arXiv](https://arxiv.org/abs/2504.16266) | — | 三值 LLM 边缘 FPGA 加速 |
| 6 | TENET | Zhirui Huang 等 | 2025 | [arXiv](https://arxiv.org/abs/2509.13765) | — | LUT-centric 三值稀疏架构 |
| 7 | PD-Swap | Yifan Zhang 等 | 2025 | [arXiv](https://arxiv.org/abs/2512.11550) | — | DPR 在 prefill/decode 逻辑间切换 |
| 8 | StreamTensor | Hanchen Ye, Deming Chen | MICRO'25 | [arXiv](https://arxiv.org/abs/2509.13694) | — | 数据流加速器中张量流式化 |
| 9 | ELiTeFormer | Victor Agostinelli 等 | 2026 | [arXiv](https://arxiv.org/abs/2607.03652) | — | attention+FFN 联合 FPGA 协同 |
| 10 | SpAtten | Hanrui Wang 等 | HPCA'21 | [arXiv](https://arxiv.org/abs/2012.09852) | — | 级联 token/head pruning（经典） |
| 11 | Energon | Zhe Zhou 等 | 2022 | [arXiv](https://arxiv.org/abs/2110.09310) | — | 动态稀疏 attention 边缘加速 |
| 12 | FlashAttention | Tri Dao 等 | NeurIPS'22 | [arXiv](https://arxiv.org/abs/2205.14135) | — | IO 感知精确 attention（奠基） |
| 13 | FlashAttention-3 | Jay Shah 等 | 2024 | [arXiv](https://arxiv.org/abs/2407.08608) | — | Hopper 异步 + FP8 |
| 14 | KIVI | Zirui Liu 等 | ICML'24 | [arXiv](https://arxiv.org/abs/2402.02750) | — | 免调优 2bit 非对称 KV 量化 |
| 15 | H2O | Zhenyu Zhang 等 | NeurIPS'23 | [arXiv](https://arxiv.org/abs/2306.14048) | — | heavy-hitter KV 驱逐（经典） |
| 16 | ALISA | Youpeng Zhao 等 | ISCA'24 | [arXiv](https://arxiv.org/abs/2403.17312) | — | 稀疏感知 KV caching 架构 |
| 17 | PagedAttention/vLLM | Woosuk Kwon 等 | SOSP'23 | [arXiv](https://arxiv.org/abs/2309.06180) | — | 分页 KV 管理（奠基） |
| 18 | Pensieve | Lingfan Yu 等 | OSDI'24 | [arXiv](https://arxiv.org/abs/2312.05516) | — | 会话 KV 换出 CPU/SSD（奠基） |
| 19 | InfiniGen | Wonbeom Lee 等 | OSDI'24 | [arXiv](https://arxiv.org/abs/2406.19707) | — | 动态 KV + 按需换入预测 |
| 20 | FlexGen | Ying Sheng 等 | ICML'23 | [arXiv](https://arxiv.org/abs/2303.06865) | — | 多级 GPU/CPU/磁盘高吞吐推理 |
| 21 | CachedAttention | Bin Gao 等 | ATC'24 | [arXiv](https://arxiv.org/abs/2403.19708) | — | 跨多轮复用 KV |
| 22 | Splitwise | Pratyush Patel 等 | ISCA'24 | [arXiv](https://arxiv.org/abs/2311.18677) | — | prefill/decode 阶段拆分 |
| 23 | Mooncake | Ruoyu Qin 等 | 2024 | [arXiv](https://arxiv.org/abs/2407.00079) | — | KVCache-centric 分离架构（工业标杆） |
| 24 | LMCache | Yuhan Liu 等 | 2025 | [arXiv](https://arxiv.org/abs/2510.09665) | — | 企业级 KV 缓存层 |
| 25 | SpectrumKV | Pengju Yang | 2026 | [arXiv](https://arxiv.org/abs/2606.08635) | — | 按 token 混合精度 KV 传输 |

补充（未编号但已验证存在）：Strata [2508.18572](https://arxiv.org/abs/2508.18572)、CacheBlend [2405.16444](https://arxiv.org/abs/2405.16444)、InstInfer [2409.04992](https://arxiv.org/abs/2409.04992)、ShadowServe [2509.16857](https://arxiv.org/abs/2509.16857)、Blink [2604.07609](https://arxiv.org/abs/2604.07609)、S³Attention [2408.08567](https://arxiv.org/abs/2408.08567)、KV-Direct [DOI](https://doi.org/10.1145/3132747.3132756)、iPipe [DOI](https://doi.org/10.1145/3341302.3342079)、LineFS [DOI](https://doi.org/10.1145/3477132.3483565)、ReDMArk [USENIX](https://www.usenix.org/conference/usenixsecurity21/presentation/rothenberger)。

\* 引用数：仅 FlightLLM（175）与 KV-Direct（Crossref "is-referenced-by-count" = 174）为本次实际查到的数据；其余因 **S2 API 全程 429、arXiv API 429** 未能取得，标"—"，不做估计。

---

## 5. 实际访问验证过的链接清单

**arXiv 摘要页（HTTP 200 逐一打开）**：2401.03868、2505.03745、2602.20515、2507.03308、2504.16266、2510.15926、2509.13765、2512.11550、2509.13694、2607.03652、2012.09852、2110.09310、2205.14135、2407.08608、2402.02750、2306.14048、2403.17312、2309.06180、2312.05516、2406.19707、2303.06865、2403.19708、2311.18677、2407.00079、2510.09665、2508.18572、2405.16444、2409.04992、2606.08635、2509.16857、2604.07609、2408.08567、2509.18114、2601.06231。

**Crossref（DOI 元数据 200）**：
- KV-Direct https://api.crossref.org/works/10.1145/3132747.3132756
- iPipe https://api.crossref.org/works/10.1145/3341302.3342079
- LineFS https://api.crossref.org/works/10.1145/3477132.3483565
- （ASPLOS'25 Vol.3 proceedings 验证）10.1145/3676642

**USENIX 官网（200）**：ReDMArk 页面 https://www.usenix.org/conference/usenixsecurity21/presentation/rothenberger

**工程/事实性页面**：
- vLLM KV Offloading Connector 博客 https://vllm.ai/blog/2026-01-08-kv-offloading-connector
- AttentionStore（FAST'25）Scilit 条目（**未直接打开 USENIX 官方页，待补验**）https://www.scilit.com/publications/8fe5eee5e9d1d24b9aa020bacaecb28c
- 同名新论文 S³Attention 2026：https://arxiv.org/abs/2601.17702

### 未能证实、标注"待核实"的三个名称
- **iAttention**（疑为 DPU/BlueField 上的 KV attention）：arXiv 标题检索 0 命中、web_search 仅返回无关的 MDPI 自动评分 "iAttention Transformer" 与 TensorRT API。
- **DO: Near Zero-Overhead CPU-GPU Communication via DPU Offloading**：arXiv 与 web_search 均未定位到该确切标题/会议。
- **Octo（SmartNIC 上 int8 KV 迁移的 preemptible multitask serving）**：未定位；搜索结果中的 "Octopus" 是 RDMA PM 文件系统（ATC'17），"Splitwise/Splitwiser" 是阶段拆分，均非所指工作。

> 建议后续在 **DBLP（会议官网 bibtex）/USENIX proceedings 页面**对以上三个名称二次核实；在证实前，不应在综述或选题依据中引用它们。

---

## 6. 检索方法与遇到的限制（可复现）

- **arXiv Atom API**（export.arxiv.org/api/query）与 **Semantic Scholar API**：本次会话中对本机/数据中心 IP **持续返回 HTTP 429**（含 5–160s 指数退避仍失败）。
- **绕行方案（成功）**：
  1. 直接抓取 **arXiv 网页搜索** `https://arxiv.org/search/?searchtype=all&query=...`（HTML，200），按标题精确匹配后再打开 `/abs/<id>` 验证；
  2. 用 **Crossref REST API**（api.crossref.org/works）按标题查询并核对 DOI、作者、年份、页码；
  3. USENIX 论文直接打开官网 presentation 页面确认。
- **脚本坑（已解决）**：Windows PowerShell 5.1 对无 BOM 的 UTF-8 脚本按 ANSI 解析，导致中文路径乱码；且 `[xml](Invoke-RestMethod)` 在多对象时抛错。解决：一律用 **pwsh 7**、`Invoke-WebRequest ... | % Content` 再转 XML。
