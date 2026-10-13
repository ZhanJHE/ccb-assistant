# 选题 A 可行性五问答复：DPDK 用户态 KV 传输

> 调研日期：2026-09-27。方法：Semantic Scholar / arXiv Atom / Crossref / USENIX 官网页 / GitHub 仓库（含文件树与代码检索）四源交叉；对 RDMA-KV 传输与内核旁路两条线做引文雪球；KV 体量与 CPU 成本由 Python 脚本计算（`%TEMP%\kvcalc\kvcalc.py`）。
> **证据等级约定**：`全文` = 读到实验节原文；`摘要` = 只取得摘要/官方页；`题录` = 只核到标题/年份/场馆；`实测(本工作区)` = 本次亲手抓取核对。
> 铁律：未取到可靠出处的断言一律标"待核实"，不编造。

## 结论速览

| 问题 | 结论 | 最关键的一条依据 |
|---|---|---|
| Q1 有没有 RDMA 做 KV 传输的文献？ | **很多，且已形成独立子领域（S2 检索 66 篇起步）**；其中 5 篇的实验口径可直接照搬，1 篇（PDD）的拓扑与我们几乎重合 | PDD 跨 DC 用 2×10 Gbps 以太网传 KV（`arXiv:2609.13161`）；SmartGen 在 15/25/32 Gbps 云网络上量化传输占比（`arXiv:2607.28150`） |
| Q2 DPDK 相对内核 TCP 有多大提升？ | **带宽倍数很小（约 1.2–2×），但每 GB 的 CPU 成本低 25–250×**；收益主要来自包处理开销、拷贝次数与尾延，不是吞吐 | 内核栈每包 950 ns（netmap ATC'12）vs DPDK 每包 61 cycles @2.4 GHz（ANCS'19）；DPDK 25.11 官方报告实测 17–20 cycles/包 |
| Q3 工程量多大？ | **8 个月可完成，属中等偏上**；MVP 可砍到 6 个模块/约 12 人周，最大不确定性是 CUDA staging 的 DMA 映射与 F-Stack 集成 | 模块级拆解见 §3；关键路径 5 项 |
| Q4 能否拿到 CCF-B？ | **可以，但不是"做了就行"**：该档场馆确实接收仿真为主的系统论文，但前提是三条硬条件全中 | TCC'26 TORTA、TCC'25 RAMPA、TNSM'26 CoInfer 均为纯仿真；TOS/TACO 已连续发 KV 系统论文 |
| Q5 会撞题吗？ | **核心数据面仍无人占位，但动机段与"普通以太网 KV 传输引擎"命题已被占**；贡献必须收敛到端系统 CPU/拷贝成本 | arXiv `DPDK AND LLM` 0 命中；**Mooncake TENT 已有 16 个 transport，其中 `hp_tcp` 自称数据中心 TCP 上的 KV 传输引擎（ASIO 内核 socket、v1 不含 GPU 内存）** |

---

## Q1：已有用 RDMA 做 KV 传输的研究？能否对齐实验环境与结果？

**是，而且相当密集。** 这一条线已经形成独立子领域，原因很直接：PD 分离架构把 KV 从"单卡内部状态"变成了"跨节点网络流量"。

### 1.1 可对齐实验环境表（按与我们选题的接近度排序）

| 短名 | 年/场馆 | 传输机制 | 实验拓扑与规模（证据等级） | 关键数字 | 开源 | 对我们的意义 |
|---|---|---|---|---|---|---|
| **PDD** | 2026 / arXiv:2609.13161 | 集群内 RDMA + **跨 DC TCP 以太网**（三 tier：P/RelayDecode/MainDecode） | 两 DC、200 节点/256 GPU，**DC 间仅 2×10 Gbps WAN 以太网**（全文） | KV payload 需求 >180 Gbps vs 跨 DC 供给 10–100 Gbps；BCR 比同构 DC 内 PD 高 37.5% | 未见 | **拓扑最接近**：把它的"DC 间那一段"换成 DPDK 栈即可对齐 |
| **SmartGen** | 2026 / arXiv:2607.28150 | 租用云实例的普通网络，三条传输路径 | 阿里云 3×prefill（L20×2，32 Gbps）+ 1×decode（L20，25 Gbps），另测 15 Gbps（全文） | 48K token 传输耗时是 prefill 的 **6.5×**；TTST 改善 2.5×→**3.3×（15 Gbps）**；传输可占 JCT **42.2%** | 未见 | **低带宽档实验模板**，直接复刻"带宽-指标"曲线 |
| **FlowKV** | 2025 / arXiv:2504.03775 | NCCL / IPC / **RDMA** 三路可切换 | 单机 8×A100-SXM4-80G(NVLink)；异构 L20+H20（全文） | KV 传输延迟 **0.944 s → 0.053 s（−96%）**；吞吐 +95%/+39%/+35% vs DistServe/Mooncake/vLLM-Disagg | 待核实 | 它的痛点是"块不连续→传输调用次数多"，正是我们零拷贝大块要打的点 |
| **KVDirect** | 2024 / arXiv:2501.14743 | 自研 tensor-centric RDMA 通信库，pull 式 | ≤4 台 × 8×H100-80G，**每 GPU 一张 400 Gbps RDMA NIC**（全文） | 1024 block 传输 **22.23 GB/s vs UCX 4.05 GB/s**；per-request 延迟 −55% | ✅ `TensorDirect/KVDirect` | **微基准口径可直接照抄**（把它的 block 数-带宽曲线重跑） |
| **DistServe** | 2024 / OSDI（工作区已录） | RDMA/NCCL 跨节点 + NVLink 节点内 | 4 节点 × 8×A100-80GB，**跨节点 25 Gbps**（全文） | goodput 7.4×；SLO 收紧 12.6× | ✅ `LLMServe/DistServe` | **指标定义标准**（TTFT/TPOT/goodput@90% SLO），跨节点 25 Gbps 正是我们的量级 |
| **Mooncake** | 2024→TOS'26 / FAST'25 | Transfer Engine，多 backend（RDMA/TCP/…） | 真集群，每节点 8×A800-80GB，节点间 RDMA 800 Gbps；23,000 条真实 trace 回放（全文） | 有效请求容量 +59–498%（摘要）；模拟场景吞吐最高 +525% | ✅ `kvcache-ai/Mooncake` | 已占位但**未评估 DPDK 路径**；同时是我们的集成宿主（见 Q5） |
| **Topology-Aware** | 2026 / arXiv:2607.28633 | NVLink/IB/TCP/CXL 按互连选路 | **无真实集群**（作者声明超出学术资源）→ 分析模型（全文） | 70B：**1.3 GB/请求**，聚合 >100 GB/s；NVLink 900 GB/s vs IB 50 GB/s vs 跨 DC TCP **12.5 GB/s**；传输隐藏 76–100% | 未见 | 空白背书：它承认缺跨节点实测条件——正是我们的优势位 |
| **TraCT** | 2025 / arXiv:2512.18194 | **CXL 共享内存**（load/store + DMA，去 NIC hop） | 真 CXL-HM 原型：**640 ns / 10.1 GB/s / 64 GB 共享区**（摘要） | TTFT 平均降 9.8×、P99 降 6.2× | 未见 | "去 NIC"另一条路线；10.1 GB/s≈80 Gbps 可作量级参照 |
| **RTT- or Bandwidth-Bound?** | 2025 / NAIC（DOI:10.1145/3748273.3749196） | 跨域 KV 传输（PagedAttention 块式顺序传） | geo-distributed（摘要） | 结论：geo 场景是 **RTT-bound 而非带宽 bound**，块式串行在高 RTT 下像 TCP 小发送窗崩塌 | 未见 | **离我们最近的邻居**，必须在相关工作里正面处理 |
| **PrfaaS** | 2026 / arXiv:2604.15039 | 普通以太网跨 DC 的 KV 缓存调度 | 跨 DC 集群（摘要） | 选择性卸载 + 缓存感知放置（数字待核实） | 未见 | 占位动机（commodity Ethernet + 去 RDMA）；数据面留有空隙 |
| **SplitZip** | 2026 / arXiv:2605.01708 | 传输前 GPU 上无损压缩 | 微基准 + 端到端（全文） | 压缩 613 GB/s、解压 2182 GB/s；传输 1.32×、TTFT 1.30× | ✅ `Intelligent-Microsystems-Lab/SplitZip` | 正交可叠加（减字节 vs 减每字节成本） |
| **ShadowServe** | 2025 / arXiv:2509.16857 | SmartNIC(BlueField-3) 数据面卸载 | 单机 2×Xeon/504GB/L40S + BF-3 + 双口 CX-7（摘要） | TPOT −2.2×、TTFT −1.38×、吞吐 +1.35%× | 未见 | 硬件卸载路线对照（≤20 Gbps 档） |
| **LMCache** | 2025 / arXiv:2510.09665 | GPU/CPU/SSD/网络多层 KV 层 | 企业级部署（摘要） | 与 vLLM 组合吞吐最高 15× | ✅ `LMCache/LMCache` | 最现实的工程底座 |
| **A CXL Memory Rack** | 2026 / arXiv:2607.18141 | CXL-HM（DRAM+SSD 后备） | 真实原型，单机与 PD 分离两配置（摘要） | 同 DRAM 预算比本地 LMCache 快 3.0×/1.45×；DRAM 少 16× | 未见 | 正交（存储层） |
| **semi-PD / Prefill Deflection / RAPID-Serve** | 2025–2026 | **少传或不传 KV**路线 | 2P2D A100（原文）等 | Prefill Deflection：prefill 仅占 P95 TTFT 的 **2–23%**，其余是排队+跨节点 KV 传输 | 未见 | 给出"KV 传输占 TTFT 大头"的实测口径，也提醒存在"取消传输"竞品路线 |
| **NIKA / ARK / Tiara / UCM / MatriX-KV** | 2025–2026 | 解析最优判据 / 路由冲突规避 / RMA ISA / DPDK 做 RDMA 建连 | 见 §5 | ARK：源端口选择做路径预留；UCM：DPDK 实现用户态 RDMA 控制面 | 未见 | 均为"旁路/传输"同族，不碰 KV 语义 |

> 表中"全文/摘要"依据调研助手实际读到的内容；未打开全文的项已标注，**引用前请勿把这些数字当一手核实**。

### 1.2 可直接照搬的实验口径（推荐 4 个）

1. **PDD（2609.13161）**——照抄它的场景与缺口分析格式：跨 DC、带宽受限以太网、KV payload 需求 vs 链路供给的对比；我们把它跨 DC 那段替换为 DPDK 传输即可，拓扑按 2 节点等比缩小。
2. **SmartGen（2607.28150）**——照抄它的带宽参数化实验：同一负载在 15/25/32 Gbps 三挡下测传输耗时占比与 TTST，用于证明"带宽越低，我们的收益越大"。
3. **DistServe（OSDI'24）**——照抄它的指标定义：TTFT / TPOT / goodput@90% SLO。别自己发明指标。
4. **KVDirect（2501.14743）**——照抄它的微基准：固定 block 数（1024）测有效带宽，我们重跑同一口径即可与 RDMA 版同图对比。

---

## Q2：理论上 DPDK 相对传统 TCP/IP 有多大提升？

### 2.1 已发表的每包/每字节成本（全部带出处）

| 指标 | 数值 | 条件 | 出处 |
|---|---|---|---|
| 内核占用 CPU 比例 | 处理 TCP 连接占 **70–80%** CPU 周期；内核态耗时占 80–83% | 8 核 Xeon，短 TCP 事务 | [mTCP, NSDI'14](https://www.usenix.org/conference/nsdi14/technical-sessions/presentation/jeong) |
| 用户态栈 vs 内核 | IX 比 Linux 高 **10×**、比 mTCP 高 1.9×；内核时间占比 75%→<10% | 10 GbE，短消息 | [IX, OSDI'14](https://www.usenix.org/conference/osdi14/technical-sessions/presentation/belay) |
| 单向时延 | IX **5.7 µs** vs Linux **24 µs** | 10 GbE，64B | 同上 |
| 内核 UDP `sendto()` | **950 ns/包**（进内核 96 + 协议栈/驱动 ~730 + 220） | FreeBSD 单核，含驱动 | [netmap, ATC'12](https://www.usenix.org/conference/atc12/technical-sessions/presentation/rizzo) |
| 用户态每包成本 | netmap **60–65 cycles/包**；DPDK **61 cycles**（关向量 TX 91）、ixy 96 | 64B，2.4 GHz 单核 | [User Space Network Drivers, ANCS'19](https://arxiv.org/abs/1901.10664) |
| 单核收包上限 | recvmmsg **175 kpps**（开 conntrack）→470 kpps（SO_BUSY_POLL）；同机 **XDP 10.1 Mpps** | 单核，14 Mpps 入流量 | [Cloudflare 2018](https://blog.cloudflare.com/how-to-drop-10-million-packets/) |
| 包投递时延 | 内核→busy-poll 应用 **4.3–5.0 µs** vs OpenOnload **0.47 µs** | 10 GbE/82599，硬件时间戳 | [Cloudflare 低时延篇](https://blog.cloudflare.com/how-to-achieve-low-latency/) |
| 尾延 | polling 99.99 分位 **5.8 µs** vs 中断不节流 **76.6 µs** | 0.1 Mpps | ANCS'19 |
| DPDK 官方吞吐 | 1×100 GbE testpmd **1 核**：64B **145.05 Mpps**，官方自算 **17–20 cycles/包**；2×25 GbE l3fwd 全尺寸线速用 4 核 | DPDK 25.11，Xeon 8380 @2.3 GHz | [Intel DPDK 25.11 Perf Report](https://fast.dpdk.org/doc/perf/DPDK_25_11_Intel_NIC_performance_report.pdf) |

### 2.2 脚本核算（KV 体量 + 分包 + CPU 成本）

**KV 体量**（公式 `2 × 层数 × KV头数 × head_dim × seq × 字节数`；70B 按 80 层/GQA 8 头/head_dim 128）

| 模型/上下文 | FP16 | INT8 | INT4 |
|---|---|---|---|
| 70B / 4K | **1.342 GB**（≈1.25 GiB，与"约 1.3 GB"吻合） | 0.671 GB | 0.336 GB |
| 70B / 32K | 10.737 | 5.369 | 2.684 |
| 70B / 128K | 42.950 | 21.475 | 10.737 |
| 7B / 4K | 0.235 | 0.117 | 0.059 |
| 1.5B / 4K（本地 4060 可闭环） | 0.117 | 0.059 | 0.029 |

**分包**：64 KB/256 KB/1 MB 的块 → 20480 / 5120 / 1280 块；MTU 1500 下 1.342 GB = **919,300 个 IP 包**，MTU 9000 = 149,797 个。

**每 GB 的 CPU 成本（单核秒；含 2 次拷贝 0.20–0.40）**

| MTU | 内核 TCP | DPDK | 内核/DPDK 倍数 |
|---|---|---|---|
| 1500 | 0.85–4.31 | 0.017–0.034 | **25–248×** |
| 9000 | 0.31–1.04 | 0.003–0.006 | **55–366×** |

打满 100 GbE（MTU 1500）所需核数：内核 **8.1–48.9 核** vs DPDK **0.22–0.43 核**。

### 2.3 反直觉检验：结论有一半不成立，必须改写 claim

- **"大消息让 DPDK 优势消失"——不成立。** 每包开销按**包数**计费，而 KV 大消息仍是多包：MTU 1500 下 256 KB 块 = 180 包，内核每包开销合计 171–1029 µs，**已超过该块在 10 GbE 上的线路时间 210 µs**。不做优化，内核栈根本打不满 10 GbE。
- **"DPDK 吞吐倍数很高"——只有小包场景成立。** 带宽维度上两端都被链路与内存带宽锁住，合理倍数只有 **约 1.2–2×**。
- **必须控制的实验变量：TSO/GSO。** 若内核路径启用 TSO/GSO（每 64 KB 才入栈一次），每包开销会塌缩到 0.0145–0.0872 核秒/GB，残差只剩两次拷贝（0.20–0.40 核秒/GB）。**实验里必须明确报告 TSO/GSO 开关**，否则结论会被推翻。这本身就是一个可写的实验发现。

**结论（可写进论文的表述）**：DPDK 在 KV 传输中的价值不是"带宽快几倍"，而是**每 GB CPU 成本降 25–250×（绝对省 0.2–5 核秒/GB）**、**包投递时延 4.3–5.0 µs → 0.47 µs、99.99 分位 76.6 → 5.8 µs**，以及在 CPU 稀缺的 serving 主机上**把核还给推理**的机会成本。

**不可声称**：绝对推理吞吐 / t·s⁻¹；"替代 RDMA"（RDMA 在时延与 CPU 卸载上仍占优）。

---

## Q3：工程量与难度

### 3.1 工作分解（人周按熟练度中等估）

| 模块 | 人周 | 难度 | 依赖 | 备注 |
|---|---|---|---|---|
| M0 Linux 环境 + hugepage + vfio 绑定 + testpmd 基线 | 1 | 低 | 一台 Linux 机器 | 你在 Windows 上，这一步是前置硬约束 |
| M1 最小 DPDK 数据面（单进程收发、KV 消息格式） | 2 | 低中 | M0 | 用 `net_tap` 可先在无卡环境调逻辑 |
| M2 F-Stack 集成（先保正确性） | 2 | 中 | M1 | 复用开源，别自己写 TCP |
| M3 自定义轻协议（L2 + 选择性重传 + 块级 ACK） | 3 | 中高 | M1 | 增量项；不做也能发，但少一半故事 |
| M4 CUDA staging → 零拷贝（外部 buffer + DMA 映射） | 2–3 | **高** | M1 | 最大技术风险，见 3.3 |
| M5 credit 流控 + 逐层流水调度 | 3 | 中高 | M3 | **真正的贡献点** |
| M6 trace 实验台（重放 PD 分离拓扑） | 2 | 中 | 工作区已有 trace 能力 | 可复用你现有框架 |
| M7 测量与对照（内核 TCP / F-Stack / 自定义 / 可选 RDMA） | 2 | 中 | M2–M6 | 含 TSO/GSO 对照 |
| M8 写作与图表 | 3 | 中 | 全部 | 期刊 rolling |
| **合计** | **20–23 人周** | — | — | 8 个月时间窗充裕 |

### 3.2 最短可发表版本（MVP）

**保留**：M0、M1、M2（或 M3）、M5、M6、M7、M8 = **约 12 人周**。
**可砍**：M4 降级为"pinned hugepage staging + cudaMemcpyAsync"（诚实的零拷贝：无用户态拷贝，但不声称 GPUDirect）；M3 用 F-Stack 替代。

### 3.3 三个难点与对策

1. **DMA 映射（M4）**：hugepage 的 IOVA 注册（`rte_extmem_register` / vfio DMA map）常卡住。**先用 DPDK mempool 分配 staging 再 cudaMemcpy 进去**，外部 buffer 作为后续优化。
2. **F-Stack 与自定义协议都想做 = 工作量翻倍**：F-Stack 先出正确性数据保底，自定义协议作为增量。
3. **"为什么不用 RDMA"**：用成本模型回答（普通云/边缘云租不到 RoCE、跨 DC 无 RDMA），并引用 IRN（SIGCOMM'18）"普通以太网可实现 RDMA 语义"作为背景。

### 3.4 关键路径与 Go/No-Go

关键路径：M0 → M1 → M4/M5 → M7 → M8。
**11 月底 Go/No-Go**：若 M2/M3 阶段测出 DPDK 相对内核 TCP（关闭 TSO/GSO 的公平对比）CPU 优势 < 2×，则把主线从"传输引擎"改为"KV 语义调度（credit + 逐层流水 + incast）"——后者恰恰是无人占位的部分（见 Q5）。

---

## Q4：完成实验后有多大可能拿到 CCF-B？

### 4.1 场馆门槛标尺（2024–2026 实发论文）

| 论文 | 场馆·年 | 评估规模 | 与 KV/传输 |
|---|---|---|---|
| Mooncake | ACM TOS 2026（[10.1145/3773772](https://doi.org/10.1145/3773772)） | 真集群 8×A800/节点、RDMA 800 Gbps、23,000 条真实 trace、vLLM 基线、6 表/31 图（全文） | **直接相关** |
| Hermes | ACM TACO 2026（[10.1145/3803390](https://doi.org/10.1145/3803390)，预印本 [arXiv:2506.14851](https://arxiv.org/abs/2506.14851)） | 两类真机（A100；8×H800 + 4-way TP）、4 条基线、LLaMA2/3、约 15 图（全文） | 间接 |
| AdaptiveKV | ACM TACO 2026（[10.1145/3821219](https://doi.org/10.1145/3821219)） | 吞吐 1.90×；**自建 FPGA-based CXL 内存仿真器**探边界（摘要） | **KV offload 直接相关** |
| ShuffleInfer | ACM TACO 2025（[10.1145/3732941](https://doi.org/10.1145/3732941)） | PD 分离 + 两级调度：资源 −38%、TTFT −97%（摘要） | **PD 分离直接相关** |
| WindowQuant | ACM TACO 2026（[10.1145/3817053](https://doi.org/10.1145/3817053)） | 多数据集 vs SOTA VLM 与 KV 量化（摘要） | 直接相关 |
| TORTA | IEEE TCC 2026（[10.1109/TCC.2026.3702578](https://doi.org/10.1109/TCC.2026.3702578)） | **纯仿真**：6h/480 时隙、4 拓扑、异构 GPU、真实电价模型、3+ 基线（全文） | 相关=调度 |
| RAMPA | IEEE TCC 2025（[10.1109/TCC.2025.3626959](https://doi.org/10.1109/TCC.2025.3626959)） | **纯仿真**：光交换 0.03 µs、10/100 Gbps、4 种 GPU 参数表、6 类服务（全文） | 间接 |
| CoInfer | IEEE TNSM 2026（[10.1109/TNSM.2026.3710972](https://doi.org/10.1109/TNSM.2026.3710972)） | **纯仿真**：SUMO + PyTorch、4 条基线、2 表（全文） | 相关=推理任务调度 |
| Offloading distributed KV stores with off-path SmartNICs | Computer Networks 2025（[10.1016/j.comnet.2025.111197](https://doi.org/10.1016/j.comnet.2025.111197)） | 评估规模未核实（ScienceDirect 403） | **题录最接近（KV 卸载）** |
| An end-to-end DPDK-integrated open-source 5G SA RAN | Computer Networks 2024（[10.1016/j.comnet.2024.110533](https://doi.org/10.1016/j.comnet.2024.110533)） | 未核实 | **证明 DPDK 在该刊有版面** |

**读法**：该档场馆**确实接收仿真为主的系统/网络论文**（TCC/TNSM/COMNET 各有现成例子），但它们共同形态是"标准仿真器或真实数据驱动的参数模型 + 多拓扑 × ≥3–4 条基线 + 端到端指标"；而同档最强的 KV 论文（TOS/TACO）几乎都带真机+真实 trace。所以"无大模型真机"是**风险项，不是否决项**。

### 4.2 有利 / 不利（不给打分）

**有利**
1. 该档接收纯仿真论文：TORTA（TCC'26）、RAMPA（TCC'25）、CoInfer（TNSM'26）、InFC（COMNET'26）均有据。
2. 这些仿真论文的规模并不夸张（4 基线 + 2 表也可发），**可达**。
3. KV 是这些场馆正在收的主题：TOS 发了 Mooncake，TACO 连发 AdaptiveKV/WindowQuant/Q-Infer/ShuffleInfer。
4. 组内有同刊先例（见 4.4）。
5. 平台成本对照：AdaptiveKV 要自建 FPGA 内存仿真器、Mooncake/Hermes 要 8 卡真机，**我们的复现成本更低**（此条为对照推断）。

**不利**
1. 同档最强的对标带真机 + 真实 trace，全无真机容易被问外部效度。
2. "把 DPDK 用在 KV 上"容易被判增量（TACO 已收多种 KV offload/量化/调度）——这是判断，非证据。
3. 收益幅度门槛：同档论文报的是 15%（TORTA）、35.7%（CoInfer）、97%（ShuffleInfer）；若相对内核 TCP 只有个位数提升，claim 站不住。
4. 平台不稀缺：用户态 TCP/DPDK 是成熟技术，"用起来"本身加分有限（判断）。
5. 自研小仿真容易被质疑可信度（CoInfer 用 SUMO，TORTA 用真实电价/拓扑数据）。

### 4.3 三条"必须做到否则掉档"的硬条件

1. **基线必须正面对比内核 TCP，并至少再加一条（RDMA/RoCE 或 UCX/gRPC），且报端到端指标**（TTFT / 端到端完成时间 / SLO 内吞吐），不能只报微基准带宽。
2. **必须有 KV 语义层的机制贡献**（块级 credit、逐层流水、incast 感知、精度/优先级与传输协同），而不是"任何大 payload 都适用"的用户态传输。
3. **评估 ≥3 类场景/拓扑/负载 × ≥3 条基线 + 可复现参数表 + 开源代码**，规模至少对齐 CoInfer（仿真 + 4 基线 + 参数表）。

### 4.4 一处需要更正的工作区结论（重要）

工作区多份文档称"导师 COMNET 2023 的 HTTP/3 论文就是 **Mininet + 一台民用 PC**，证明该刊接受纯仿真"。**本轮核实结果：只核实到该文用 `quic-go` 真实协议实现 + 端到端应用层指标（FCP 降 3.1–21.0%、PLT 降 5.3–23.7%）+ 与 HTTP/3 默认 Round-Robin 对比**；"Mininet + 民用 PC 仿真"这一定性**未能核实**（ScienceDirect 与 ACM DL 均 403，未见 OA 副本）。结论：先例能证明"真实协议实现 + 端到端指标"可发该刊，**不足以证明"纯仿真可发"**。→ 已按铁律在 `增补-VU13P与纯软件评估路线.md` 加注。

---

## Q5：有没有类似文献？是否撞题？

### 5.1 核心证据：三条零命中

| 来源 | 查询 | 结果 |
|---|---|---|
| arXiv（元数据级） | `all:"DPDK" AND all:"LLM"` | **0** |
| arXiv | `all:"DPDK" AND all:"inference"` / `all:"transport engine" AND all:"KV cache"` | **0 / 0** |
| GitHub 代码检索（用户已授权） | `DPDK repo:vllm-project/vllm`、`repo:LMCache/LMCache`、`repo:sgl-project/sglang`、`repo:ai-dynamo/nixl`、`repo:openucx/ucx` | **全部 0** |
| GitHub 文件树 + 文档 | `kvcache-ai/Mooncake` | 唯一 DPDK 踪迹 = `mooncake-store/CMakeLists.txt` 中由 SPDK 带入的 `DPDK_INCLUDE_DIR`；**无 dpdk transport 目录** |

> arXiv 只索引标题/摘要/作者，0 命中不等于全文级空白；但与"主流引擎无 DPDK backend"合并后，证据强度足够。

### 5.2 撞题风险清单（含可直接使用的差异化措辞）

| 工作 | 重叠点 | 差异化措辞 | 风险 |
|---|---|---|---|
| **Mooncake TENT `hp_tcp`**（仓库主干，`mooncake-transfer-engine/tent/src/transport/hp_tcp/`，设计文档 `docs/source/design/tent/hp-tcp.md`） | **最高**：TENT 已有 16 个 transport（hp_tcp/tcp/rdma/nvlink/shm/gds/io_uring/sunrise_link/ub/tpu/xpu/ascend/mnnvl…）；`hp_tcp` 自称"data-center TCP 上的高性能 KV 传输"（持久 lane、静态 multi-rail、1 MiB 切片、per-WRITE ACK），与"逐块 ACK + credit"高度接近 | "Mooncake 的 `hp_tcp` 已证明普通 TCP 可承载 KV，但它**基于 ASIO 内核 socket、面向 CPU DRAM，且 v1 明确不含 GPU 内存**；本文替换的是**数据面操作系统路径本身**（PMD 轮询 + hugepage 零拷贝 + 内核旁路），并首次量化该场景下**每字节的 CPU 成本**。我们的实现以 TENT 新 backend 的形式对接，与 `hp_tcp`/`rdma` 同台对比。" | **高**（工程实现级占位；同时也是最好的集成路径） |
| **PrfaaS**（2604.15039） | 占动机："over commodity Ethernet"+"去 RDMA 依赖" | "PrfaaS 把普通以太网当作既有带宽预算来调度（选择性卸载 + 缓存感知放置），传输数据面仍是内核栈；本文不改 serving 调度，而是把 prefill 主机的 CPU 占用从传输路径上移除。" | 高 |
| **PDD**（2609.13161） | 跨 DC + 用提前解码掩盖 KV 传输 | "PDD 在应用层隐藏 WAN 传输，跨域段仍走内核 TCP；本文不改变 serving 流水，在同一 RTT 预算内把主机 CPU 开销与拷贝次数降到旁路栈水平。" | 高 |
| **RTT- or Bandwidth-Bound?**（NAIC'25） | 已发表"逐块串行在高 RTT 下退化"的诊断 | "已有工作指出块级串行在高 RTT 下崩溃；我们回答它留下的数据面问题：用批量 mbuf 链 + 轮询收发消除每块的 CPU 与系统调用开销，使块级开销不随块数线性增长。" | 高 |
| **Topology-Aware**（2607.28633） | **逐层流水掩盖传输**已被提出 | "逐层流水由该工作提出；我们的增量是该流水在**轮询模式 NIC 上的实现与 per-layer 消息调度**（无中断、无系统调用），并给出重叠率下界。" | 高（创新点 2 只能作为工程化复用） |
| **Blink**（2604.07609） | "把 CPU 从稳态推理路径移除"同一叙事 | "Blink 用 SmartNIC 消 CPU，需专有 DPU；我们在**无 SmartNIC 的普通网卡**上用 DPDK 达到同一目的。" | 中 |
| **GIGANETS**（SIGCOMM'26）、**Toward GPU-centric Networking on Commodity Hardware**（EdgeSys'24） | 标题级"商品硬件 + GPU 中心网络" | 需读全文后定；后者初步定位为单机/边缘 GPU 收发路径（无 DPDK、无 KV 语义、无 PD 分离场景） | 中（待核实） |
| SpectrumKV / SplitZip / SmartGen | 都在减少**传输字节** | "上述工作减少要传的字节数，本文减少**每字节的搬运成本**，正交且可叠加。" | 中低 |
| ARK（SIGCOMM'26）、KV-Direct（SOSP'17）、iPipe（SIGCOMM'19）、UCM（APNet'25） | 路径选择 / 可编程 NIC 侧 KV / DPDK 做建连 | "KV-Direct/iPipe 把键值逻辑放进可编程 NIC，需要专门硬件；本文不动网卡固件，只在主机侧重塑 KV 传输数据面。" | 低 |

### 5.3 撞题结论与主张修正

**空白仍成立，但只剩一个窄缝**：*"网络侧内核旁路（DPDK/AF_XDP）+ 零拷贝 host-staging→NIC + KV 语义流控"的全栈数据面实现*，三源均无占位者。
**已被占位**：动机段（PrfaaS、PDD）、"普通以太网 KV 传输引擎"命题（Mooncake `hp_tcp`）、逐层流水（Topology-Aware）、块级串行退化诊断（NAIC'25）。

**因此主张必须收敛为**：
> 我们不改 serving 调度、不发明逐层流水、不声称"普通以太网能传 KV"；我们回答的是**端系统数据面**问题——在无 RDMA/SmartNIC 的普通网卡上，把 KV 传输的**每字节 CPU 成本与拷贝次数**降到内核旁路水平，并用 KV 语义（块级 credit + 优先级 + incast 感知）把这一能力转化为 TTFT/p99 收益；实现以 Mooncake TENT / vLLM `kv_connector` 的新 backend 形式对接。

### 5.4 引用勘误（本轮发现）

`arXiv:2508.02001` 实为 *Versatile yet Efficient Network Traffic Analysis: Offloading Network Foundation Model to SmartNIC*（网络流量分析），**不是**"BF-3 上做 LLM KV 卸载"。`A-DPDK用户态KV传输引擎.md` 原文把它当作"硬件路线对照"引用，已更正。

---

## 动手前还缺的证据（诚实清单）

1. **GIGANETS 摘要**（SIGCOMM'26，ACM DL 403）与 **Toward GPU-centric Networking on Commodity Hardware** 正文（EdgeSys'24）——两者都可能含直接重叠点，Q5 的"中风险"两条依赖它们。
2. **Mooncake `hp_tcp` 的 GPU 内存路线图**：issue/PR 级未发现 DPDK 需求，但需确认官方是否有 GPU staging 计划。
3. **导师 COMNET 2023 论文全文**：核实"Mininet + 民用 PC"说法（现为待核实）。
4. **ComNet 2025 "Offloading distributed KV stores with off-path SmartNICs"** 的评估规模（题录最接近），用于判断同刊对"KV 卸载"类工作的门槛。
