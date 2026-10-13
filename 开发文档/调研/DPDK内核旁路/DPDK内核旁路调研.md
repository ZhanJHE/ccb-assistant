# 《DPDK 内核旁路与用户态数据面》调研

> 面向"DPDK 零基础 → 能做内核旁路方向研究"的知识建设与领域地图。
> 逐条资料清单见 **[论文学习列表.md](../../导航/论文学习列表.md)**；本文件只讲**领域结构、技术路线、权衡与研究空白**。
> 索引编号见 `文献索引.md` 的 **DRE+ / KVT+ / DBK+** 三节。

## 0. 元信息

- **主题**：DPDK / 内核旁路（kernel bypass）/ 用户态网络栈 / 用户态数据面
- **调研目标**：为研究生新生建立该方向的知识坐标系；确定哪些是必须读的奠基工作、哪些是当前活跃面、哪里还有空白。服务本工作区**选题 A（基于 DPDK 的用户态 KV 传输引擎）**的前置知识建设。
- **边界**：不覆盖纯硬件交换 ASIC / P4 数据面编程（另见 `调研卷宗/在网计算-LLM/`）；不覆盖 RDMA 语义细节（另见选题方案 C）。以**端系统软件数据面**为核心。
- **创建日期**：2026-09-29　**最后更新**：2026-09-29
- **关键词 & 同义词**：DPDK = Data Plane Development Kit；kernel bypass = 内核旁路 = userspace networking；netmap / PF_RING / PFQ / Snabb / VPP / FD.io；poll mode driver (PMD)；hugepage / UIO / VFIO / IOMMU；AF_XDP / XDP / eBPF；SmartNIC / DPU / IPU / off-path NIC；DPA (Data Path Accelerator)；user-space TCP stack（mTCP / f-stack / Z-Stack）；single-sided RDMA；zero-copy；PCIe / DDIO / NUMA / cache line。

## 1. 一句话总览

内核网络栈为通用性付出了每包中断、拷贝、系统调用与协议栈锁的代价，在 10 Gbps 以上成为瓶颈；**内核旁路**用"用户态轮询 + 零拷贝 + 巨页 + 绑核"把这套代价一次性删掉，代价是**失去内核提供的隔离、复用与统一调度**。此后二十年的全部工作，本质都是在回答**"删掉代价之后，怎么把丢掉的东西补回来，以及下一步把数据面推到哪"**。当前三条主线并行：**（a）在主机内重建可控的数据面 OS**（IX → Snap → Demikernel）；**（b）把数据面搬到网卡/DPU 上**（iPipe → FlexTOE → DPA）；**（c）不开销那么大的替代路线**（XDP/AF_XDP、io_uring）。趋势是：**旁路已从"性能优化手段"变成"现代数据中心的默认架构"**（DBK-18），研究焦点从"能不能快"转向"快的同时如何隔离、可观测、可移植、可共享"。

## 2. 背景与问题定义

- **为什么需要它**：C10K → C10M 之后，通用服务器要做线速包处理（转发、负载均衡、NFV、存储、AI 数据面）。Linux 网络栈的设计目标是**通用性与公平性**，其固定开销（中断、sk_buff 分配、多次拷贝、系统调用、协议栈锁）在 10 Gbps / 千万 pps 量级时把 CPU 全吃掉。
- **核心矛盾**（入门者必须记牢的三组）：
  1. **性能 vs 隔离**：旁路把内核挡在外面，多租户与安全隔离随之消失 → IX / Arrakis / FairNIC / CAPIO 都在补这一块。
  2. **轮询 vs CPU 效率**：100% 占核换来低延迟；一旦流量稀疏或需要省电，纯轮询就是浪费 → Metronome / EnergyTracer 在补这一块。
  3. **专用与可移植的矛盾**：每种旁路设备（DPDK、RDMA、eBPF、DPU）都有自己的 API，上层系统被绑死 → Demikernel / Pegasus 在补这一块。
- **评价指标**：吞吐（Gbps / Mpps）、延迟与**尾延迟**（p50/p99/p99.9）、**每包 CPU 周期数**、核数与核占用、PCIe 带宽占用、能耗、隔离性/公平性、可移植性、可观测性。

## 3. 技术路线分类（核心）

### 路线 A：主机内用户态数据面 OS（"把 OS 重建一遍"）
- **代表论文**：mTCP（NSDI'14, DRE-1）、IX（OSDI'14, DBK-2）[经典]、Arrakis（OSDI'14, DBK-3）[经典]、Snap（SOSP'19, DBK-9）、ZygOS（SOSP'17, DBK-10）、Demikernel（SOSP'21, DBK-12）、Pegasus（EuroSys'25, DBK-17）
- **思路**：内核退为控制面（只做隔离与硬件配置），数据面在用户态以批处理 + 零拷贝运行；再往上补齐调度（work-conserving / 核间再平衡）、统一设备抽象（Demikernel）、透明接入（Pegasus）。
- **优点**：性能上限最高（nanoPU 69 ns 是极限参照）；语义可控，适合做**自定义传输协议**。
- **局限**：与内核生态割裂（需重写或桥接协议栈）；安全边界靠用户态框架自己保证；维护成本高。

### 路线 B：netmap / TAP 式"最小旁路"与框架化
- **代表论文**：netmap（ATC'12, DBK-1）[经典]、Fast userspace packet processing（ANCS'15, DBK-7）、User Space Network Drivers / ixy（ANCS'19, DBK-6）、MultiStack（CCR'14, DBK-8）
- **思路**：不追求"重建 OS"，只把**包 I/O 的固定开销**（分配、拷贝、系统调用）摊掉：预分配缓冲环 + 元数据共享 + 批量摊销。
- **优点**：**理解旁路本质的最短路径**（ixy 不足 1000 行）；可与既有协议栈共存（MultiStack）。
- **局限**：性能上限低于路线 A；对多队列/卸载等现代特性支持弱。

### 路线 C：DPDK 及其工程化（"工业化的一条龙"）
- **代表资料/论文**：DPDK 专著（CRC'20, DBK-24）、官方文档（DBK-66）、ixy（作为对照）、Metronome（ToN'22, DBK-27）、Z-Stack（LANMAN'24, DBK-28）、TurboMem（arXiv'26, DBK-30）、DPDK Observability（ICPE'26, DBK-31）
- **思路**：把路线 A/B 的全部优化沉淀成库（EAL 巨页与绑核、Ring、Mempool/Mbuf、PMD、rte_flow、Graph、**MLDEV**），并绑定生态（VPP / OVS-DPDK / SPDK / 5G UPF）。
- **优点**：**事实标准**，工程资料最厚（官方文档 + 三本中文书 + Summit 录像），找工作与研究都最通用；支持多厂商网卡与多架构。
- **局限**：独占网卡、独占核；用不了常规调试与性能工具（→ 催生可观测性研究）；抽象层次固定，做非包语义（如 KV 张量）传输时需要"逆用"它。

### 路线 D：内核内可编程旁路（XDP / AF_XDP / eBPF）
- **代表论文**：XDP（CoNEXT'18, DBK-20）[经典]、Understanding Delays in AF_XDP（ICC'24, DBK-21）、FLASH（SoCC'25, DBK-22）、uXDP（eBPF@SIGCOMM'25, DBK-23）、MiddleNet（TNSM'23, DBK-58）
- **思路**：在网卡驱动的早期钩子上跑 eBPF，保留内核的共存与安全模型；AF_XDP 再把包零拷贝直接送到用户态。
- **优点**：不独占网卡、不独占核、与内核栈共存，**云原生与容器场景的实际首选**。
- **局限**：性能上限低于 DPDK；表达力受限（有状态处理与循环受限）；版本绑定内核。
- **对选题 A 的意义**：这是**必须正面回答的"为什么不用它"**——选型论证缺这一块会被直接质疑。

### 路线 E：卸载到网卡 / DPU（"数据面离开主机"）
- **代表论文**：KV-Direct（SOSP'17, #31）、iPipe（SIGCOMM'19, #32）、Floem（OSDI'18, DBK-14）、LineFS（SOSP'21, #33）、FlexTOE（NSDI'22, DBK-15）、Characterizing Off-path SmartNIC（OSDI'23, DBK-46）、DPA 刻画（ICNP'24, DBK-47）、BlueField 实测（ICS'25, DBK-48）、Wave（ASPLOS'25, DBK-51）、FairNIC（SIGCOMM'20, DBK-50）、SKV（CLUSTER'22, DBK-52）、Honeycomb（TC'23, DBK-53）、Offloading distributed KV with off-path SmartNIC（COMNET'25, KVT-31）
- **思路**：把 KV 存储、文件系统数据面、TCP 数据面、资源管理交给可编程网卡/DPU 的独立核与加速器（DPA）。
- **优点**：省主机 CPU 与内存带宽；延迟可预测；天然贴近"高频小操作"（KV、RPC）。
- **局限**：网卡侧算力/内存极小（BF-3 的 L1/L2/L3 分别约 1/8/16 MB，DDR5 仅两通道）；编程模型不成熟；调试困难。
- **对选题 A 的意义**：这是**上游竞争者**，也是**可能的落地形态**（把引擎做成 TENT 的一个 backend，或卸载到 DPA）。

### 路线 F（横向）：GPU/NIC 直连与"CPU 消失"
- **代表论文**：Toward GPU-centric Networking（EdgeSys'24, KVT-12）、GPU-Initiated Networking for NCCL（arXiv'25, DBK-54）、CEIO（SIGCOMM'25, DBK-55）、Blink（arXiv'26, #34）
- **思路**：让 GPU 或网卡直接发起/终结传输，CPU 退出数据路径。
- **意义**：这是选题 A 的**长期威胁**——如果 CPU 最终从传输路径上消失，"优化端系统 CPU/拷贝成本"的命题会被架空。必须在引言里给出"为什么 CPU 中继在短期内仍是必需的"论证。

## 4. 时间线

- **2009–2012 早期奠基**：RouteBricks（SOSP'09）证明"通用服务器可做网络设备"；PacketShader（SIGCOMM'10）证明"专用算力 + 高速包 I/O"可行；**netmap（ATC'12）**给出快速包 I/O 的范式。
- **2013–2015 关键转折**：DPDK 开源（Intel，2010 起，2013 年在 DPDK.org 建立社区）；mTCP / IX / Arrakis（2014）确立"用户态栈 + 数据面/控制面分离"；Fast userspace packet processing（ANCS'15）给出量化对比。
- **2017–2021 成熟与体系化**：ZygOS（2017，尾延迟）、Floem（2018）、XDP（2018，内核内旁路）、eRPC（2019）、Snap（2019，工业范本）、Demikernel（2021，可移植抽象）、nanoPU（2021，性能极限）；同期卸载线：KV-Direct（2017）、iPipe（2019）、FlexTOE（2022）。
- **2022–2024 反差与细化**：Kernel vs. User-Level Networking（2023，**反方**）、Comparing User Space and In-Kernel（2023，适用范围）、Off-path SmartNIC 刻画（OSDI'23）、DPA 刻画（ICNP'24）。
- **2025–2026 最新进展**：A Wake-Up Call for Kernel-Bypass（DaMoN'25，**定性转为"必需架构"**）、Pegasus（EuroSys'25，透明化）、Wave（ASPLOS'25，卸载资源管理）、Z-Stack（LANMAN'24）与用户态 UDP 80 Gbps（ICSPS'25）代表"在 DPDK 上重造传输栈"回潮；**KV 方向成为 DPDK/网络侧的新出口**——SIGCOMM'26 上 ARK（KV 传输路由冲突）、DualPath（分离式 KV 存储 I/O）、FlowTurbo（OVS MegaFlow 硬件卸载）三篇；**NVIDIA 转向产品化**（CMX + BlueField-4 + DOCA Memos，KVT 专题 NPD-18）。

## 5. 重点论文清单（入门必读 20 条，按阅读顺序）

| # | 论文 | 年份 | 路线 | 引用 | 关键贡献 | 链接 |
|---|---|---|---|---|---|---|
| 1 | netmap | 2012 | B | 957 | 快速包 I/O 范式奠基 | [USENIX](https://www.usenix.org/conference/atc12/technical-sessions/presentation/rizzo) |
| 2 | User Space Network Drivers (ixy) | 2019 | B/C | 32 | <1000 行看清旁路本质 | [DOI](https://doi.org/10.1109/ANCS.2019.8901894) · [代码](https://github.com/emmericp/ixy) |
| 3 | mTCP | 2014 | A | 474 | 用户态 TCP 栈起点 | [USENIX](https://www.usenix.org/conference/nsdi14/technical-sessions/presentation/jeong) |
| 4 | IX | 2014 | A | 494 | 数据面/控制面分离 + 保隔离 | [USENIX](https://www.usenix.org/conference/osdi14/technical-sessions/presentation/belay) |
| 5 | Arrakis | 2014 | A | 211 | 内核只做控制面 | [DOI](https://doi.org/10.1145/2812806) |
| 6 | MultiStack | 2014 | B | 61 | 自定义传输协议的合法性论证 | [DOI](https://doi.org/10.1145/2602204.2602212) |
| 7 | RouteBricks | 2009 | — | 562 | 通用服务器做网络设备 | [DOI](https://doi.org/10.1145/1629575.1629578) |
| 8 | PacketShader | 2010 | — | 662 | 高速包 I/O 引擎前身 | [DOI](https://doi.org/10.1145/1851182.1851207) |
| 9 | Snap | 2019 | A | 258 | 工业界用户态栈范本 | [DOI](https://doi.org/10.1145/3341301.3359657) |
| 10 | ZygOS | 2017 | A | 292 | 微秒级任务低尾延迟调度 | [DOI](https://doi.org/10.1145/3132747.3132780) |
| 11 | eRPC | 2019 | A | 404 | 普通硬件上单核 10M RPC/s | [USENIX](https://www.usenix.org/conference/nsdi19/presentation/kalia) |
| 12 | Demikernel | 2021 | A | 161 | 异构旁路设备统一抽象 | [DOI](https://doi.org/10.1145/3477132.3483569) |
| 13 | The eXpress Data Path (XDP) | 2018 | D | 441 | 内核内旁路奠基 | [DOI](https://doi.org/10.1145/3281411.3281443) |
| 14 | Kernel vs. User-Level Networking | 2023 | 反方 | 10 | 旁路并非银弹 | [DOI](https://doi.org/10.1145/3626780) |
| 15 | A Wake-Up Call for Kernel-Bypass | 2025 | 定性 | 12 | 旁路已是必需架构 | [DOI](https://doi.org/10.1145/3736227.3736235) |
| 16 | Z-Stack | 2024 | C | 11 | DPDK 上重造零拷贝 TCP/IP 栈 | [DOI](https://doi.org/10.1109/LANMAN61958.2024.10621881) |
| 17 | Understanding PCIe Performance for End Host Networking | 2018 | — | 286 | 旁路后的真瓶颈是 PCIe | [DOI](https://doi.org/10.1145/3230543.3230560) |
| 18 | Characterizing Off-path SmartNIC | 2023 | E | 75 | BF-2 多路径实测底表 | [USENIX](https://www.usenix.org/conference/osdi23/presentation/wei) |
| 19 | RTT- or Bandwidth-Bound? KV Cache Transfer | 2025 | KV | — | KV 传输是 RTT-bound，留出数据面问题 | [DOI](https://doi.org/10.1145/3748273.3749196) |
| 20 | UCM: User-space RDMA Connection Setup | 2025 | KV/C | — | **用 DPDK 做控制面**的先例 | [DOI](https://doi.org/10.1145/3735358.3735388) |

## 6. 在特定领域的应用 / 已有研究

| 领域 | 代表工作 | 与本方向的关系 |
|---|---|---|
| **虚拟交换 / 云网络** | OVS 十年回顾（SIGCOMM'21, DBK-37）、Hoda（EuroSys'24）、Byte vSwitch（EuroSys'25）、FlowTurbo（SIGCOMM'26） | DPDK 最成熟的落地场景；说明"通用流水线 vs 专用快路径"的权衡 |
| **存储** | SPDK（CloudCom'17, DBK-41）、存储栈横向对比（CHEOPS'23, DBK-42） | SPDK 与 DPDK 同源；Mooncake 正是经 SPDK 把 `DPDK_INCLUDE_DIR` 带入代码树 |
| **5G / 电信** | DPDK 端到端 5G SA RAN PoC（COMNET'24, KVT-32）、UPF 四模式 I/O 对比（arXiv'26, DBK-57）、VPP 论文（DBK-34/35） | 论文投稿定位参考（COMNET 已收 DPDK 系统论文） |
| **LLM serving** | KV-Direct（SOSP'17, #31）、FlowKV（KVT-3）、KVDirect（KVT-4）、ShadowServe（#29）、Blink（#34）、ARK / DualPath（SIGCOMM'26） | **本工作区选题 A 的主战场**；见下节空白分析 |
| **安全 / 多租户** | FairNIC（SIGCOMM'20）、CAPIO（arXiv'25）、Safe Sharing（arXiv'25）、eBPF 内存安全 SoK（S&P'25） | 旁路的隔离性缺口，是当前最有活力的补丁方向之一 |

## 7. 研究空白与待解决问题

1. **DPDK 本体的安全与可靠性研究几乎为零（本轮实测的空白）**。多组关键词在 Semantic Scholar 检索"DPDK 安全 / 模糊测试 / 漏洞分析"**均 0 命中**；`Automated Attack Discovery in Data Plane Systems`（CSET'19）实为 P4 交换硬件工作，常被误引。但 DPDK 已大规模部署于电信与云基础设施，其内存安全、mempool 边界、驱动层解析缺乏系统研究。**这是一个可独立成题、且无需大硬件投入的缺口**。风险：无现成文献可引，需自行从 CVE/CNVD 与 DPDK 官方 Security Process 起步。
2. **"内核旁路数据面 + KV 语义"仍无人占位**。arXiv `all:"DPDK" AND all:"LLM"`、`"DPDK" AND "inference"`、`"transport engine" AND "KV cache"` **均为 0 命中**；vLLM / SGLang / LMCache 代码树无 DPDK。但动机段已被 PrfaaS（KVT-2）与 Mooncake TENT `hp_tcp`（KVT-13）占位 → 贡献必须收敛到**端系统 CPU/拷贝成本**这一格。
3. **轮询模型的资源代价缺少新解**。Metronome（2022）之后，DPDK 的"独占一个核"在多租户/共置/省电场景仍是硬伤；EnergyTracer（2026）只是测量。**"在不退化为内核栈的前提下做间歇轮询/动态核共享"仍未解决**。
4. **卸载边界缺乏统一理论**。什么该留在主机、什么该上 DPU/DPA，目前主要靠实测（OSDI'23、ICNP'24、ICS'25），没有可预测的代价模型。arXiv:2609.32055《Towards Simple Models of Complex SmartNICs》是最新尝试，仅 0 引用。
5. **可观测性与可调试性**。DPDK 应用无法用常规 perf/gdb 姿势，相关工作零星（DBK-31 引用 0）。**"让旁路程序可被正常观测"仍是开放问题**。
6. **AF_XDP 与 DPDK 的边界在移动**。两边都在补齐对方的能力（eBPF 加状态、DPDK 加虚拟 PMD），**"什么时候必须选 DPDK"缺少 2025 年之后的新实证**——DBK-57（UPF 四模式对比）是目前最新的对照，但仅限 5G 场景。

## 8. 参考文献（全部为真实可点击出处）

- [netmap: A Novel Framework for Fast Packet I/O](https://www.usenix.org/conference/atc12/technical-sessions/presentation/rizzo)（2012, USENIX ATC）
- [mTCP: a Highly Scalable User-level TCP Stack for Multicore Systems](https://www.usenix.org/conference/nsdi14/technical-sessions/presentation/jeong)（2014, NSDI）
- [IX: A Protected Dataplane Operating System](https://www.usenix.org/conference/osdi14/technical-sessions/presentation/belay)（2014, OSDI）
- [Arrakis: The Operating System is the Control Plane](https://doi.org/10.1145/2812806)（2014, OSDI / TOCS'15）
- [RouteBricks](https://doi.org/10.1145/1629575.1629578)（2009, SOSP）
- [PacketShader](https://doi.org/10.1145/1851182.1851207)（2010, SIGCOMM）
- [User Space Network Drivers (ixy)](https://doi.org/10.1109/ANCS.2019.8901894)（2019, ANCS）
- [Fast userspace packet processing](https://doi.org/10.1109/ANCS.2015.7110116)（2015, ANCS）
- [Rekindling network protocol innovation with user-level stacks](https://doi.org/10.1145/2602204.2602212)（2014, CCR）
- [Snap: A Microkernel Approach to Host Networking](https://doi.org/10.1145/3341301.3359657)（2019, SOSP）
- [ZygOS](https://doi.org/10.1145/3132747.3132780)（2017, SOSP）
- [Datacenter RPCs can be General and Fast (eRPC)](https://www.usenix.org/conference/nsdi19/presentation/kalia)（2019, NSDI）
- [The Demikernel Datapath OS Architecture](https://doi.org/10.1145/3477132.3483569)（2021, SOSP）
- [The nanoPU](https://www.usenix.org/conference/osdi21/presentation/ibanez)（2021, OSDI）
- [Floem](https://www.usenix.org/conference/osdi18/presentation/phothilimthana)（2018, OSDI）
- [FlexTOE](https://www.usenix.org/conference/nsdi22/presentation/shashidhara)（2022, NSDI）
- [Kernel vs. User-Level Networking](https://doi.org/10.1145/3626780)（2023, POMACS）
- [Pegasus: Transparent and Unified Kernel-Bypass Networking](https://doi.org/10.1145/3689031.3696083)（2025, EuroSys）
- [A Wake-Up Call for Kernel-Bypass on Modern Hardware](https://doi.org/10.1145/3736227.3736235)（2025, DaMoN@SIGMOD）
- [The eXpress Data Path (XDP)](https://doi.org/10.1145/3281411.3281443)（2018, CoNEXT）
- [Understanding Delays in AF_XDP-based Applications](https://doi.org/10.1109/ICC51166.2024.10622351)（2024, ICC）
- [FLASH: Fast Linked AF_XDP Sockets](https://doi.org/10.1145/3772052.3772258)（2025, SoCC）
- [Comparing User Space and In-Kernel Packet Processing for Edge Data Centers](https://doi.org/10.1145/3594255.3594257)（2023, CCR）
- [Data Plane Development Kit (DPDK) 专著](https://doi.org/10.1201/9780429353512)（2020, CRC Press）
- [Z-Stack: A High-Performance DPDK-Based Zero-Copy TCP/IP Protocol Stack](https://doi.org/10.1109/LANMAN61958.2024.10621881)（2024, LANMAN）
- [Metronome: Adaptive and Precise Intermittent Packet Retrieval in DPDK](https://doi.org/10.1109/TNET.2022.3208799)（2022, IEEE-ACM ToN）
- [High-Speed Software Data Plane via Vectorized Packet Processing](https://doi.org/10.1109/MCOM.2018.1800069)（2018, IEEE Comm. Mag.）
- [Revisiting the Open vSwitch Dataplane Ten Years Later](https://doi.org/10.1145/3452296.3472914)（2021, SIGCOMM）
- [SPDK: A Development Kit to Build High Performance Storage Applications](https://doi.org/10.1109/CloudCom.2017.14)（2017, CloudCom）
- [Performance Characterization of Modern Storage Stacks](https://doi.org/10.1145/3578353.3589545)（2023, CHEOPS@EuroSys）
- [A Comprehensive Survey on SmartNICs](https://doi.org/10.1109/ACCESS.2024.3437203)（2024, IEEE Access）
- [Characterizing Off-path SmartNIC for Accelerating Distributed Systems](https://www.usenix.org/conference/osdi23/presentation/wei)（2023, OSDI）
- [Demystifying Datapath Accelerator Enhanced Off-path SmartNIC](https://doi.org/10.1109/ICNP61940.2024.10858560)（2024, ICNP）
- [Understanding PCIe Performance for End Host Networking](https://doi.org/10.1145/3230543.3230560)（2018, SIGCOMM）
- [SmartNIC Performance Isolation with FairNIC](https://doi.org/10.1145/3387514.3405895)（2020, SIGCOMM）
- [Offloading distributed key-value stores with off-path SmartNICs](https://doi.org/10.1016/j.comnet.2025.111197)（2025, Computer Networks）
- [RTT- or Bandwidth-Bound? Demystifying the KV Cache Transfer in LLM Serving](https://doi.org/10.1145/3748273.3749196)（2025, NAIC）
- [UCM: Fast and Maintainable User-space RDMA Connection Setup](https://doi.org/10.1145/3735358.3735388)（2025, APNet）
- [Toward GPU-centric Networking on Commodity Hardware](https://doi.org/10.1145/3642968.3654820)（2024, EdgeSys）
- 一手文档：[DPDK Programmer's Guide](https://doc.dpdk.org/guides/prog_guide/)、[SPDK](https://spdk.io/doc/)、[VPP/FD.io](https://fd.io/)、[Open vSwitch](https://docs.openvswitch.org/)、[ixy 源码](https://github.com/emmericp/ixy)、[xdp-tutorial](https://github.com/xdp-project/xdp-tutorial)

## 9. 待办 / 下次继续

- [ ] 待核实：`arXiv:2609.32055《Towards Simple Models of Complex SmartNICs》` 的会议去向（本轮仅 arXiv + S2 题录级）。
- [ ] 待检索：DPDK 安全的**非学术来源**（CVE / CNVD / DPDK 官方 Security Process 页面 / oss-fuzz 覆盖情况），用以判断第 7 节空白 1 是否真的无人做。
- [ ] 待检索：`f-stack`、`Seastar`、`Snabb`、`Lagopus` 是否有正式学术论文（本轮只核实到仓库，未找到对应论文）。
- [ ] 待补：`Pegasus`（DBK-17）作者全名 S2 未返回，需查 ACM DL 或 Crossref。
- [ ] 待补：2026 年 SIGCOMM 三篇（ARK / DualPath / FlowTurbo）正文多被 403，需换校内渠道取全文后再定其对选题 A 的威胁等级。
- [ ] 待做：把本文第 3 节的六条路线画成一张图，放进 `导航/毕设研究全景.html`。
