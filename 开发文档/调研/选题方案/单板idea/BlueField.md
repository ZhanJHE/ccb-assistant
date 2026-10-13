# BlueField DPU 单板研究 idea 集（非 KV-cache 方向）

> 创建：2026-10-02。为研究生（8 个月窗口 2026-09→2027-05，目标 CCF-B，期刊优先 Computer Networks / IEEE TCC / JPDC，会议 CoNEXT / ICNP / IWQoS / ICDCS）构思的 BlueField DPU 研究 idea。
> **硬件假设**：按 BF-2 保守假设（8×Arm A72 + 网络加速器，DOCA 环境，底层融合 DPDK/SPDK/UCX）；不依赖 BF-3 的 DPA。
> **排除**：KV-cache / LLM serving 数据面（已由选题1 DPU 内联 KV Codec 占位）。
> **依据**：全部空白判断挂 `文献索引.md` 的真实编号（DBK/DRE/CGA-CGE/WTP 等）；本轮新增补录见文末 §8。
> **工程量原则**：优先"Arm 核数据面 + 标准加速器"形态；DOCA 学习曲线陡，6 个 idea 均按"单人 8 个月可完成"裁剪。

---

## 0. 总览

| # | 暂定标题 | 大方向 | 核心空白出处 | 新颖性把握 | 目标场馆（首选） |
|---|---|---|---|---|---|
| BF-Sec | DPDK/DOCA 用户态数据面的系统性安全刻画与定向模糊测试 | DPDK 安全/可靠性 | DBK 专题空白①（文献索引 §DBK 末尾"研究空白"） | **高** | DSN / ACSAC（B）→ Computer Networks |
| BF-RTC-CC | 学习增强 × 硬 deadline：交互式视频拥塞控制的 DPU 发送侧实现 | 传输层/拥塞控制 | 云游戏调研空白 5（CGC 节）；WTP-78/80/84/91 | **中高** | IWQoS / CoNEXT → IEEE TCC |
| BF-SFU | 媒体语义感知的 RTC 中继数据面：BlueField 上的有状态 SFU 卸载 | 视频/RTC 数据面 | 云游戏调研空白 4；CGC-18（Scallop）、CGC-12（MoMQ） | **中** | IWQoS / ICDCS → Computer Networks |
| BF-Waste | "作废字节"的服务器侧线速测量与峰值感知择时传输 | 测量 + 传输调度 | WiFi 调研 G1/G3（WTP 节）；WTP-37~43、WTP-91 | **中高**（测量）/ 中（调度） | IMC / CoNEXT → Computer Networks |
| BF-Model | SmartNIC 卸载边界的可预测代价模型：什么该留在主机、什么该上 DPU | 卸载框架/刻画 | DPDK 调研空白 4（§7）；DBK-46/47/48 | **中** | ICNP / IWQoS → JPDC |
| BF-Iso | 多租户 DOCA 数据面的公平共享与性能隔离 | 卸载框架/系统 | DBK-50（FairNIC）、DBK-59/60 | **中低** | ICDCS / IWQoS → Computer Networks |

六个 idea 覆盖 **4 个大方向**（DPDK 安全、传输层 CC、视频数据面、卸载框架/测量），两两之间技术栈与贡献类型均不同。

---

## BF-Sec｜DPDK/DOCA 用户态数据面的系统性安全刻画与定向模糊测试

**暂定标题**：*Bypassed and Exposed: A Systematic Security Study of Userspace Dataplanes on DPU*（DPDK/DOCA 的内存安全刻画与定向模糊测试）

### 动机与研究空白
- DBK 专题的实质结论之一：**未检索到任何可核实的"DPDK 本体安全/模糊测试/漏洞分析"学术论文**（多组关键词 S2 命中 0；常被误引的 CSET'19《Automated Attack Discovery in Data Plane Systems》实为 P4 交换硬件工作，文献索引 §DBK 末尾"不得引用清单"与"研究空白"）。
- 但 DPDK 已大规模部署于电信与云基础设施（DBK-18 论证旁路已是"必需架构"；KVT-32 的 5G RAN PoC、DBK-37/39 的 OVS/虚拟交换机工业部署），且 **CVE 流持续不断**：vhost 库反复出问题（本轮验证性搜索确认：CVE-2021-3839 未校验 `num_queues` 致越界读写、CVE-2024-11614 vhost checksum offload 越界读可让恶意 VM 打崩宿主机 vSwitch、2020 年 virtio ring descriptor TOCTOU、2026-09 又有 virtio-net control-queue 越界读）。**攻击面真实存在且在增长，学术界却零系统研究**——动机段数字可直接从 CVE/NVD 统计得出。
- 对照组现成：eBPF 侧已有 SoK（DBK-61，IEEE S&P'25）系统梳理内存安全；DPDK 侧完全没有对应物。**"内核内旁路有 SoK、用户态旁路没有"本身就是一句话卖点**。

### 为什么必须是 BlueField
1. **真实部署形态**：云厂商的 DPDK 正越来越跑在 DPU 上（DOCA 就是 NVIDIA 的 DPDK 发行版 + Arm 移植）。在 BF 上研究 DPDK 安全 = 研究它未来最主要的部署环境，而非实验室 x86 玩具配置。
2. **Arm A72 是被忽视的测试目标**：DPDK 社区主战场在 x86；弱内存模型 + 不同的 cache/原子语义下，ring/mempool 的无锁并发边界问题（TOCTOU、ABA、描述符校验窗口）可能有 x86 上暴露不出来的行为。**"同一代码库 × 两种内存模型的安全差集"是天然的贡献点**。
3. **攻防同体的实验拓扑**：BF 既可当被测目标（Arm 核跑 DOCA/DPDK 数据面），又可当线速攻击流量发生器（用网络加速器/DPDK pktgen 从网口打自己），一台卡 + 一台民用 PC 构成闭环，无需额外设备。
4. 普通服务器做这件事没有平台故事；FPGA/交换机跑不了 DPDK 本体。

### 实验设计
- **Step 1（刻画，1.5 月）**：系统梳理 DPDK 攻击面分类学——mbuf/mempool 边界、ring 无锁协议、vhost-user/virtio 描述符校验、PMD 报文解析路径、hugepage/VA 暴露面；从 NVD 拉全部 DPDK CVE 做根因归类，得出"哪类 bug 反复出现"的统计结论（这是论文第 3 节）。
- **Step 2（工具，2.5 月）**：面向 DPDK 的定向模糊测试器。关键挑战是**状态在共享内存里、输入既是包也是描述符**——采用 structure-aware 变异（virtio 描述符 + 报文双层），用 BF 的 Arm 核跑被测库、用 host/对打 PC 经网口或 vhost-user socket 注入；崩溃检测用 ASan 移植 + 自定义 canary（mempool redzone）。
- **Step 3（评估，2 月）**：对象选 vhost-user 库（CVE 最密集）+ 1~2 个 PMD 解析路径 + DOCA 的 DPDK 封装层；指标：覆盖导向 fuzzing 的边覆盖率、独特崩溃数、与既有 CVE 的复现/新发现。基线：AFL++ 裸跑（无结构感知）。
- **产出形态**：分类学 + 工具 + ≥1 个真实 bug 报告（负责任披露，DPDK 有官方 security process）。**即使没有新 0day，"首个系统刻画 + 可复现基准"也够 B 类**。
- 全部实验 BF-2 + 一台民用 PC 对打即可；不需要 GPU。

### 目标场馆
首选 **DSN（CCF-B，可靠性+安全交叉，正合"刻画+工具"形态）**、ACSAC（B）；系统/网络口径改写后可投 **Computer Networks（B 期刊）** 或 Euro-Par/ICDCS（B）。安全顶会（S&P/USENIX Sec/CCS 均为 A）8 个月内不现实，不作首选。

### 风险与撞车检查
- **撞车风险低**：本轮再次验证（web 搜索 + 此前 S2 多组查询 0 命中），学术侧无人占位；只有 CVE 数据库与 2017 年 KVM Forum 工程幻灯片。
- **风险 1**：fuzzing 工具的工程量大——裁剪为"vhost-user + 1 个 PMD"两个目标，不做全库覆盖。
- **风险 2**：安全社区审稿人对"没有新漏洞"的工作接受度——对策是把贡献定位为**分类学 + 可复现基准 + Arm/x86 差集发现**，按 DSN 的 dependability 口径写。
- **风险 3**：DOCA 版本绑定。锁定一个 LTS 版 DOCA，论文中明确版本。
- **新颖性把握：高**。依据：DBK 专题 0 命中结论 + 本轮 web 复验仅见 CVE/工程资料。

---

## BF-RTC-CC｜学习增强 × 硬 deadline：交互式视频拥塞控制的 DPU 发送侧实现

**暂定标题**：*DeadlineGuard: Learning-Augmented Congestion Control for Interactive Video, Offloaded to the DPU*

### 动机与研究空白
- 云游戏调研的**真空白 5**："learning-augmented × 硬 deadline 的交互式视频传输"——RTC 拥塞控制方向 12 条检索无一相关，而 learning-augmented 方法论已有教科书框架（WTP-78/80/81：consistency-robustness 权衡）且在交换机调度（WTP-84/85）、360° 视频（WTP-89）、能源调度（WTP-91/92/93 peak-aware）均已落地。**独缺交互式视频 CC 这一格**。
- RTC/CC 侧现状：云游戏专用 CC 已有 Pudica（CGA-13，近零排队）与 Themis（CGC-2，抑制自激振荡）；Camel（CGC-3）指出包级 CC 被编码的帧级时变误导；OCC（CGC-4）用物理层信息。**但全部是"反应式/启发式"，无一提供预测不准时的最坏情况保证**。
- 传输层奠基文献齐备（DRE-14 DCQCN、DRE-15 HPCC、DRE-16 Swift、DRE-19 Homa、CGC-7 Copa）供基线与对照。

### 为什么必须是 BlueField
1. **DOCA PCC（可编程拥塞控制）**是 BF 独有的标准加速器能力：CC 决策在网卡侧以硬件 pacing 执行，**时戳与定速精度不受主机调度抖动污染**——而交互式视频的硬 deadline 语义最怕的正是主机侧 jitter（CGB-1 证明"波动而非均值"才伤害用户）。
2. **隔离性**：CC 逻辑跑在 Arm 核上，视频服务器（民用 PC）的 CPU 负载变化不影响控制回路；这是"在普通服务器内核/用户态做 CC"给不出的性质。
3. **遥测在同一张卡上**：RTT/ECN/速率采样可在线速完成，不需要主机参与。
4. FPGA/交换机做不了"带预测模型的 CC"（模型推理需要通用核）；普通服务器做得了算法但给不了 pacing 精度与隔离——**这正是"为什么 DPU 是正确平台"的完整论证**。

### 实验设计
- **算法（2 月）**：发送侧 CC = "稳健基线（Copa/Swift 式 delay-based）+ 短期带宽预测建议 + learning-augmented 组合器"。组合器按预测近期误差自适应调权（WTP-83 的 ε-函数化框架），并证明 consistency/robustness 界（理论 1 小节，照 WTP-84 模板改造）。Deadline 语义：帧级 deadline 不可达时主动降帧/切层而非排队（D3 的"晚到=无用"，WTP-69）。
- **实现（2.5 月）**：BF-2 Arm 核上 DOCA PCC/DPDK 实现发送侧 CC；视频源用真实 WebRTC/ffmpeg 推流（民用 PC），DPU 做 pacing 与速率决策；可选用 DPDK 轮询线程内的轻量预测器（线性/LightGBM 级，不用深度模型）。
- **评估（2 月）**：BF + 民用 PC 对打；网络条件用 tc/netem 仿真（带宽抖动、loss burst、RTT 变化）+ 公开蜂窝/WiFi trace（Lumos5G WTP-66 类）；负载用真实游戏/会议录像推流。基线：GCC（CGC-6）、Copa（CGC-7）、Pudica 复现（CGA-13）。指标：帧级延迟 p95/p99、卡死时间、带宽利用率、**预测被注入误差时的性能退化曲线（robustness 证据）**——这是别人都没有的一张图。
- 不需要 GPU；视频内容用录屏回放。

### 目标场馆
**IWQoS / CoNEXT（均 B）** 首选；期刊扩展投 **IEEE TCC 或 Computer Networks（B）**。

### 风险与撞车检查
- **最危险的邻居**：**BEACON（SIGCOMM'26，本轮新发现，见 §8 补录）**——硬件卸载 CCA 的基准框架，说明"DPU 上 CC"这个概念本身已进 A 类视野。差异化：BEACON 是评估框架不是新算法，不做 deadline、不做学习增强、不做保证；必须正面引用并划界。COER（TACO'24，RDMA NIC 上 CC 协同设计）也需引。
- Pudica/Themis 占"云游戏 CC"但不占"学习增强+保证"；robustness 曲线是天然区分点。
- **风险 1**：DOCA PCC 的可编程粒度（能否表达自定义速率决策逻辑）需 1~2 周验证性 spike；若 PCC 不够灵活，退回"Arm 核 + DPDK 软件 pacing"（仍可成立，但平台论证变弱）。
- **风险 2**：理论证明若做不出紧致界，退为"ε-参数化的经验 robustness"，论文仍成立但贡献降半档。
- **新颖性把握：中高**。"交互视频 × learning-augmented × 最坏情况保证"检索零命中；"DPU 上 CC"已有占位者需划界。

---

## BF-SFU｜媒体语义感知的 RTC 中继数据面：BlueField 上的有状态 SFU 卸载

**暂定标题**：*Stateful Media Relay on the DPU: Frame-Aware SFU Offload for Interactive Video*

### 动机与研究空白
- 云游戏调研**空白 4**：传输层缺"媒体重要性"的统一抽象——MoMQ（CGC-12）诊断出"多路径调度器只看到字节、看不到关键帧"，MoQ、语义打包、CC 感知编解码各自发明重要性表达、互不兼容。
- Scallop（CGC-18，SIGCOMM'25）证明生产 SFU 本质是"丢弃与转发"，并把其拆成**硬件数据面 + 软件控制面**——但它用的是 P4 交换机。**P4 路线有两个现实问题**：① Intel Tofino 已停产且 open-p4studio BSP 申请窗口 2026-01 已关闭（NPD-17），新建 P4 实验环境基本不可行；② 交换机 ASIC 做不了"每帧状态 + 内容级决策"（Scallop 自己也只能做浅层逻辑）。
- 云游戏负载与会议不同（10–20 Mbps、60–120 fps、硬交互 deadline，CGA-3/CGA-1），中继侧的丢弃/转发决策需要**帧级 + 层级（I/P/FEC）状态**，这超出 match-action 的表达力。

### 为什么必须是 BlueField
1. **通用 Arm 核 + 线速网络加速器**恰好落在"比 P4 有状态、比主机 CPU 便宜/可预测"的空档：SFU 每流每帧的状态机（关键帧追踪、层级映射、尾丢策略）可以在 Arm 核上表达，转发加速与 QoS 队列走加速器。
2. **Tofino 路线死了之后**（NPD-17），"可编程数据面做媒体中继"需要一个活着的平台——BF 是最直接的替代者，这本身就是论文的 motivation 段落。
3. 普通服务器 SFU（如 Galene/mediasoup）要过内核栈、吃主机 CPU，且无法给出每包确定性；FPGA 成本高、开发慢，8 个月单人做不完。

### 实验设计
- **系统（3 月）**：BF-2 上实现有状态 SFU 数据面：Arm 核跑每流帧解析（RTP 头 + 编解码层的 frame-marking/layer id），维护"关键帧保护"状态机；转发/排队/标记走 DPDK + 硬件 QoS。策略集：关键帧优先丢弃、FEC 预算分配（对照 Tooth CGA-14 的细粒度 FEC）、按 deadline 的尾丢。
- **对照（1.5 月）**：基线 = 主机内核 SFU（如 mediasoup 类转发逻辑）+ Scallop 策略的软件复现（浅层丢弃）。
- **评估（2 月）**：民用 PC 群（2–3 台即可）仿真多路会议/云游戏推流；netem 仿真拥塞；指标：端到端帧延迟分布、关键帧丢失率、单卡可承载流数 vs 主机 CPU 占用（卸载收益）、拥塞下 MOS 代理指标。
- **规模问题的诚实处理**：单机单卡仿真"边缘节点"规模（数十流），不声称数据中心级。

### 目标场馆
**IWQoS / ICDCS（B）**；期刊投 **Computer Networks**（该刊已收 DPDK 系统论文，KVT-32/DBK-35）。

### 风险与撞车检查
- **最危险邻居**：Scallop（CGC-18）。差异化三条：① 平台换代（P4→DPU，且 Tofino 停产）；② 状态深度（帧级状态机 vs match-action）；③ 负载换成云游戏/云桌面（Scallop 主打会议）。若审稿人认为"只是换平台"，贡献不够——必须把"帧级状态机带来 Scallop 做不到的策略"做出实测收益。
- **风险**：WebRTC/RTP 栈的工程熟悉成本；可裁剪为只支持一种编解码（H.264 单流 + 时域分层）。
- **新颖性把握：中**。SFU 卸载概念已被 Scallop 占位，新颖性在"有状态 + DPU + 交互负载"的交集。

---

## BF-Waste｜"作废字节"的服务器侧线速测量与峰值感知择时传输

**暂定标题**：*Counting Wasted Bytes at Line Rate: DPU-based Server-Side Telemetry and Peak-Aware Transfer Scheduling*

### 动机与研究空白
- WiFi 专题的**两个硬空白**（WTP 节 §10）：**G1**——"中断→无续传→重下→抬高高峰负载"这条因果链**无任何量化研究**（12+ 组关键词、50+ 次查询零命中）；**G3**——peak-aware 的竞争调度只在能源域被形式化（WTP-91/92/93），网络/带宽侧没有。
- 客户端侧的浪费已被量化透（视频 33% 冗余 WTP-37/38、短视频 45.2% WTP-39、预取浪费 WTP-41/42），但**全部是被动的、客户端/播放器视角**；服务器/网络侧"到底有多少字节被传了却作废"没有任何在线测量基础设施——现有 RE 文献（WTP-112~124）只做链路省带宽、不看负载时序，且 TRE-PRO（WTP-124）证明"可编程数据面做 RE"引用为 0、无人跟进（"能力涨、人没做"缺口）。
- 这个 idea 补齐 WiFi 调研里"需要服务器/网卡侧能力"的那块拼图：**测量（G1 的量化）+ 动作（G3 的 peak-aware 择时）在同一数据面上闭环**。

### 为什么必须是 BlueField
1. **线速、零主机开销的每流状态**：要识别"作废"（连接中断前的已传字节、被 range 重下覆盖的字节、用户早停对应的已发段），需要在发送侧维护每流字节级账本；在主机内核做会污染被测系统，在 BF Arm 核上做则对服务器完全透明。
2. **既能测又能动**：同一张卡测出作废字节后，可以直接在数据面上执行择时动作（延迟弹性流、降速、标记 ECN），形成"测量→调度"闭环——这是被动测量工具（如 NetFlow/sFlow）做不到的。
3. 交换机做不了应用语义（识别 HTTP range 重叠、ABR segment 边界需要 L7 浅解析，Arm 核正合适）；FPGA 做 L7 状态成本太高。

### 实验设计
- **测量系统（2.5 月）**：BF-2 上实现对大对象传输（HTTP/HTTPS 之外用自建分发服务，或明文测试协议 + QUIC 自研端点）的每流字节账本：已发字节、ACK 字节、连接中断点、重连后 range 重叠检测 → **作废字节率**指标族。在校园/实验室可控负载发生器（民用 PC × N）上跑合成负载 + 回放公开 trace。
- **调度器（2 月）**：peak-aware 择时：弹性传输（软件更新、云游戏预载、备份）在预测高峰到来前被推迟/限速；预测器输入 = 测量系统自身产出的负载序列（自举），算法按 WTP-91 peak-aware 模板 + WTP-78 consistency/robustness 框架设计。
- **评估（2 月）**：两台 PC + BF 构成"服务器—DPU—客户端"链路；netem 仿真高峰；指标：作废字节率（基线 vs 调度后）、高峰时段链路利用率峰值、弹性流完成时间、交互流的 p99 延迟受损界。
- **诚实边界**：测量语义依赖自建服务（HTTPS 下无法看 range），论文定位为"内容分发者自愿部署的服务器侧能力"（CDN 边缘场景）。

### 目标场馆
**IMC / CoNEXT（B，测量口径）**；期刊投 **Computer Networks**。

### 风险与撞车检查
- 撞车风险低：G1/G3 均有 50+ 查询零命中的证据链；TRE-PRO 引用 0。
- **风险 1**：L7 语义在加密流量下不可得——用"自建分发服务 + QUIC 端点配合"绕过（测量对象是自己部署的服务，非第三方流量）。
- **风险 2**：作废字节的"真实世界占比"可能很小（WTP-122 的反方证据：真实冗余被高估）——把 WTP-122 写进 related work 并把"在哪些负载下作废率显著"做成研究发现，即使数字小也是结论。
- **新颖性把握：测量部分中高，调度部分中**。

---

## BF-Model｜SmartNIC 卸载边界的可预测代价模型

**暂定标题**：*Where to Draw the Line: A Predictive Cost Model for Host/DPU Offload Boundaries*

### 动机与研究空白
- DPDK 调研**空白 4**：什么该留主机、什么该上 DPU/DPA，目前全靠实测——BF-2 刻画（DBK-46，OSDI'23）、BF-3 DPA 刻画（DBK-47，ICNP'24）、新 BF 实测（DBK-48，ICS'25）、PCIe 瓶颈（DBK-49）都是"测一遍告诉你数字"，**没有可预测的代价模型**；最新尝试 arXiv:2609.32055《Towards Simple Models of Complex SmartNICs》仅 0 引用（DPDK 调研 §9 待核实项）。
- 卸载文献的分歧结果（iPipe #32、LineFS #33、FlexTOE DBK-15、Wave DBK-51 各自卸载不同部件、收益各异）说明**缺一个能解释"为什么这个卸载赚、那个卸载亏"的统一框架**。

### 为什么必须是 BlueField
研究对象就是 BF 本身：BF-2 的三条通信路径（host⇄Arm、Arm⇄网络、host⇄网络经加速器）已在 OSDI'23 被刻画（DBK-46），提供了模型的部分参数与验证基线。普通服务器没有"卸载边界"这个问题；FPGA SmartNIC 可作为对照但非必需。

### 实验设计
- **模型（2 月）**：把卸载决策建模为"函数粒度 × 数据流拓扑 × 三种执行位置（host CPU / DPU Arm / 加速器路径）"的代价图；参数 = 各路径带宽/延迟/CPU 占用（复用 DBK-46 的测量方法自测一遍）；决策 = 最小化"主机 CPU 秒 + 尾延迟惩罚"的划分。
- **验证（3 月）**：选 3 个代表性数据面函数做卸载实验（如：遥测聚合、限速/CC 计算、浅层 L7 解析），在 BF-2 + 民用 PC 上实测每种划分，检验模型预测误差（目标 <20%）。
- **产出**：模型 + 决策工具 + 三个案例的"反直觉发现"（预期能复现 OSDI'23 的部分结论并给出解释）。

### 目标场馆
**ICNP / IWQoS（B）**；期刊投 **JPDC（B）**。

### 风险与撞车检查
- **风险 1（最大）**：容易做成"又一篇刻画论文"——DBK-46/47/48 已经把测量做完了。生存线在于**模型的预测力**（能对新函数预测卸载收益）而非新的测量数字。
- **风险 2**：arXiv:2609.32055 需先精读（DPDK 调研 §9 待办），若它已解决问题则本 idea 降级。
- **新颖性把握：中**。刻画红海中的模型空白，"预测力"是唯一护城河。

---

## BF-Iso｜多租户 DOCA 数据面的公平共享与性能隔离

**暂定标题**：*Sharing the DPU: Fair and Isolated Multi-Tenant Offload on BlueField*（备选/第六 idea）

### 动机与研究空白
- 旁路失去内核隔离是经典矛盾（DPDK 调研 §2 核心矛盾 1）；FairNIC（DBK-50，SIGCOMM'20）做了 SmartNIC 多租户公平性，CAPIO（DBK-59）与 Safe Sharing（DBK-60）从 capability 角度补共享安全——**但都停在 2020–2025 的 x86 SmartNIC/主机语境，DOCA 时代"多个 host 应用/VM 共享一张 BF 的 Arm 核与加速器"的隔离与公平没有新工作**；Wave（DBK-51，ASPLOS'25）把资源管理卸到网卡核，恰好制造了"谁在网卡核上调度谁"的新问题。
- 若未来多个卸载功能（如本文件 BF-RTC-CC 的 CC、BF-Waste 的遥测）共存于一张卡，租户间干扰就是现实问题。

### 为什么 BlueField
BF 是"多租户共享网卡"的实际部署形态（云厂商 DPU 即插在多租户宿主机上）；Arm 核 + 硬件队列/加速器提供了可操作的隔离杠杆（硬件队列隔离 + Arm 核 cgroup + 加速器仲裁）。

### 实验设计（概要）
- 在 BF-2 上跑 2~4 个异质数据面租户（转发、遥测、CC），注入干扰源（CPU 密集型邻居、高速率邻居），测量尾延迟/吞吐的租户间干扰矩阵；设计两层隔离机制（硬件队列配额 + Arm 核调度权重），与 FairNIC 策略对比。
- 平台与负载全部复用前几个 idea 的代码资产。

### 目标场馆
**ICDCS / IWQoS（B）**；期刊 **Computer Networks**。

### 风险与撞车检查
- **新颖性把握：中低**——FairNIC 已经定义了这个问题，差异化靠"DOCA 时代 + 异质卸载负载共存"的新场景；若审稿人认为只是 FairNIC 的 BF 复刻则危险。**建议作为其他 idea 的"第二贡献"章节，而非独立首选题**。

---

## 7. 横向比较与推荐

| 维度 | BF-Sec | BF-RTC-CC | BF-SFU | BF-Waste | BF-Model | BF-Iso |
|---|---|---|---|---|---|---|
| 新颖性把握 | **高** | 中高 | 中 | 中高 | 中 | 中低 |
| DOCA 学习曲线风险 | 低（DPDK 层即可） | 中（PCC 待验证） | 中高 | 中 | 低 | 中 |
| 撞车风险 | 低 | 中（BEACON/COER 需划界） | 中高（Scallop） | 低 | 中（刻画红海） | 高（FairNIC） |
| 无需 GPU | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 8 个月可完成度 | 高 | 中高 | 中 | 中高 | 高 | 中 |
| 与实验室系统实现特长匹配 | 高 | 高 | 高 | 高 | 中高 | 高 |

**首选推荐：BF-Sec**。理由：① 唯一"零学术占位"的空白（两轮检索互证），新颖性最安全；② 工程量最可控，不依赖 DOCA 高级特性（DPDK 层即可起步），BF-2 即够用；③ CVE 流持续供给了现成的动机与测试种子；④ 即使无新 0day 也有"分类学 + 基准 + Arm/x86 差集"的保底贡献；⑤ 与 KV-cache 选题零重叠，且能为实验室后续所有 DPDK/DOCA 工作提供安全基线。
**次选：BF-RTC-CC**（空白真实 + 平台论证最完整，但需先花 1~2 周验证 DOCA PCC 可编程性，且必须精读 BEACON 划界）。

## 8. 本轮补录（新发现条目，已登记文献索引）

| 编号 | 条目 | 与本文件的关系 |
|---|---|---|
| DRE-23 | BEACON: Benchmarking Adaptability of Hardware-Offloaded Congestion Control Algorithms，Dadhania 等，2026 / SIGCOMM，DOI:10.1145/3789240.3828743 | BF-RTC-CC 的最危险邻居（硬件卸载 CCA 评估框架，非新算法） |
| DRE-24 | COER: A Network Interface Offloading Architecture for RDMA and Congestion Control Protocol Codesign，Ketong Wu; Dezun Dong，2024 / ACM TACO，DOI:10.1145/3660525 | BF-RTC-CC 的近邻（RDMA NIC 上 CC 卸载架构） |
| DRE-25 | DFlush: DPU-Offloaded Flush for Disaggregated LSM-based Key-Value Stores，Chen Ding 等，2025 / Proc. ACM Manag. Data，DOI:10.1145/3725284 | 旁证"DPU 卸载 + 自适应控制面"形态已被数据库社区接受（与本文件各 idea 正交） |

> 另：DPDK CVE 线索（CVE-2021-3839 / CVE-2024-11614 / virtio 系列）为本轮 web 检索确认的非学术来源，BF-Sec 动机段使用；正式立题时需从 NVD 逐条核对并登记。
