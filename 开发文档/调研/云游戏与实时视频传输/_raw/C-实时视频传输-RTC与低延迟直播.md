# C 实时视频传输 —— RTC、低延迟直播、拥塞控制与丢包修复（原始调研笔记）

> **调研日期**：2026-10-01
> **检索通道**：Semantic Scholar Graph API（`paper/search`）、arXiv Atom API（`id_list` 批量核验）、Crossref（逐 DOI 核验）、Tavily 网页检索（USENIX 官方页取正文片段）
> **检索范围**：主体 2024–2026，少量 2016–2023 奠基工作（标注「经典」）
> **著录约定**
> - 引用数一律为 **S2 快照值**（2026-10-01 抓取），会过时；取不到的写「待核实」。
> - **状态列** = 重要度标记（⭐重点 / 📥待读 / 📌归档）+ **核验级别**：
>   - **题录级** = 标题 / 一作 / 年份 / 出处 / ID 已在 S2、Crossref 或 arXiv 三者之一逐字比对通过（未读摘要）；
>   - **摘要级** = 另读了官方摘要（arXiv summary 或 S2 abstract）；
>   - **正文级** = 读了正文片段（本轮仅少数，见注）。
> - **workshop 与正会严格区分**：NOSSDAV、EMS@SIGCOMM、ANRW、Mile-High Video、QoMEX、ICMEW、CSCN、NINeS 均为 workshop；SIGCOMM 2026 Posters and Demos 亦非正会。
> - 未找到可靠出处的条目一律不进正式表，写入文末「不得引用清单」。
>
> **条目数说明**：正式表 **C-RT-01 … C-RT-80 共 80 条**，另有备选 30 条（§11）。**这超出了任务给出的 25–45 条目标。** 原因是本子方向的关键词范围异常宽（任务列出约 20 组关键词，横跨云游戏 / 云 VR / 云电脑 / 视频会议 / 低延迟直播四类负载，以及 CC / L4S / QUIC-MoQ / FEC / ABR / 可编程数据面六条技术线），若压到 45 条会丢掉对"两类负载差别"和"研究空白"判断必需的证据。**若要收敛**：只保留各表 ⭐ 标记项 + §10 综述，约为 30 余条；§11 与各表 📌 项可按需裁剪，不影响任何结论方向。

---

## 0. 子方向总述

这个子方向研究**为交互式/实时视频服务的传输层与端到端系统**：从 RTP/WebRTC 到 LL-HLS/LL-DASH/CMAF，从实时媒体拥塞控制到 FEC/ARQ 丢包修复，覆盖云游戏、云 VR、视频会议、低延迟直播四类负载。它解决的核心矛盾是：**延迟预算被压缩到几十到几百毫秒后，重传不可行、缓冲不可用，而可用带宽仍在剧烈波动**——传统"试错式探带宽 + 大缓冲换平稳"的两条路都被掐断。

近两年的三个明显变化：
1. **交付范式从"流"转向"命名对象 + 中继"**：Media over QUIC Transport（MoQ）由 CDN 生产化落地，把媒体拆成具名 Object 由中继转发，传输层因此失去对帧语义的可见性，调度/优先级/ABR 都要重做（C-RT-32/33/28/29）。
2. **拥塞控制从"端到端黑盒试错"转向"跨层拿信息"**：物理层/无线调度器/帧级编码节奏被直接喂给 CC（OCC、BLADE、5G 上行双环、Camel），原因是纯端到端试错在蜂窝与 Wi-Fi 上已经探不准（C-RT-11/14/15/16）。
3. **L4S 从 RFC 走到产品**：RFC 9330/9331/9332 的架构-协议-AQM 三件套已成体系，2024–2026 出现大量"现网部分部署 / 低带宽下行为 / WebRTC 适配"的实证与踩坑论文（C-RT-21~27）。同时**学习型 CC 从"能否赢"退回到"能否公平、能否可部署"**（Jury、EchoCC、Learning vs Human-Derived），神经编解码与生成式修复开始替代传统 FEC 的位置（GRACE、Reparo、AutoRec、Semantic-Aware NVC）。

---

## 1. 应用需求与场景对比：云游戏 / 云 VR / 云电脑 vs 视频会议 / 直播

> **本节回答"云游戏/云电脑的传输需求与视频会议/直播的差别"**（见 §5 小结）。

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-01 | ⭐摘要级 | Dissecting and Streamlining the Interactive Loop of Mobile Cloud Gaming | Yang Li（清华，Feng Qian / Tianyin Xu 合作） | 2025 / USENIX NSDI（正会） | DBLP:conf/nsdi/LiQ000Y00XQX25（**无 DOI**） | 11 | 对 8 个商用移动云游戏平台做一个月实测：**即使网络条件良好，交互延迟仍达 112–403 ms**；根因是 Android 图形管线的 VSync 被调用多达 5 次把云-端管线串行化。作者提出 LoopTailor 端到端 VSync 调节器，降低约 34%，真实部署达 **sub-100 ms**。 | **需求侧最硬证据**：云游戏的真实瓶颈有一半在云侧渲染管线而非网络；传输优化必须与渲染管线协同，否则天花板很低。 |
| C-RT-02 | ⭐摘要级 | Network Anatomy and Real-Time Measurement of Nvidia GeForce NOW Cloud Gaming | Minzhao Lyu | 2024 / PAM（正会） | arXiv:2401.06366 | 19 | 建立 GFN 会话识别方法并做实时测量。明文数字：**本地主机游戏约需 100–200 kbps，而云游戏最低需要 10–20 Mbps**，且要求网络连接稳定。 | **"云游戏 ≠ 普通视频"最直接的量化出处**：带宽差 2 个数量级。同时点明 ISP 是体验的关键一方。 |
| C-RT-03 | 📥题录级 | Games Are Not Equal: Classifying Cloud Gaming Contexts for Effective User Experience Measurement | Yifan Wang | 2025 / arXiv | arXiv:2509.19669 | 待核实 | 把云游戏按游戏类型/上下文分类后再做 UX 测量，说明"云游戏"不是单一负载类。 | 提醒：把"云游戏"当同质负载做评测会被审稿人挑；C-RT-05 的"延迟敏感度分层"是同一思路。 |
| C-RT-04 | ⭐摘要级 | SAIL: Perceptual Quality-Aware Rate Control for Cloud Gaming | Houde Qian | 2026 / arXiv | arXiv:2607.11231 | 0（新） | 某云游戏平台（摘要称 "T cloud gaming platform"）实测：**带宽占运营成本 30–60%**；且码率-感知曲线存在饱和阈值，越过阈值后加码率几乎不提升感知 → 生产系统"尽力而为推高码率"造成系统性冗余。 | 云游戏成本侧的稀缺数据；与工作区既有的"视频流量浪费"主题（Sieber 2015/2016、Zhang 2021、Su 2024）同源，可衔接。 |
| C-RT-05 | ⭐题录级 | Trinity: Exploiting Latency Sensitivity to Improve Quality of Experience on Cloud VR Gaming | Lingzhi Zhao | 2026 / ACM MMSys（正会） | DOI:10.1145/3793853.3795744（Crossref 核对） | 0（新） | 利用不同内容对延迟的敏感度差异重分配资源，提升云 VR 游戏 QoE。 | 与 C-RT-03 呼应：**延迟需求在应用内部是不均匀的**，一刀切 SLO 会浪费。 |
| C-RT-06 | 📌摘要级 | EyeNexus: Adaptive Gaze-Driven Quality and Bitrate Streaming for Seamless VR Cloud Gaming Experiences | Ze Wu | 2025 / PACMNET（Proc. ACM Netw.） | arXiv:2509.11807 | 7 | 把实时眼动驱动的空间压缩（FSC）与注视点编码（FVE）结合，在受限网络下做云 VR 码率自适应。 | 云 VR 这一类负载的传输侧代表；与工作区 learning-augmented 360° 视频流（Chen/Hajiesmaili/Sitaraman 2026）相邻但不同（这里是注视点+码率，不是学习增强在线算法）。 |
| C-RT-07 | 📌题录级 | Gaming in the Cloud: 5G as the Pillar for Future Gaming Approaches | César Baena | 2024 / IEEE Communications Magazine | DOI:10.1109/MCOM.005.2300256（Crossref 核对） | 10 | 工业界视角综述云游戏对 5G 的能力需求与部署形态。 | 写引言"云游戏需要什么网络"时可引的综述型出处。 |
| C-RT-08 | ⭐题录级 | Enhancing Video Smoothness in Cloud Desktops: An Improved Compression Framework With Adaptive Fast Search Algorithm | Jingxin Zhou | 2025 / IEEE ISSSR | DOI:10.1109/ISSSR65654.2025.00033（S2 核对） | 0 | 面向**云桌面**流畅度的编码端改进（自适应快速搜索）。 | **本节最接近"云电脑"的一次命中，且只做编码、不做传输。** 见 §13 研究空白 ①。 |

**本组补充观察（非正式表）**：云 PC / 云桌面（cloud PC、remote desktop、VDI）方向，本轮在 S2 用 `cloud desktop / cloud PC / remote desktop transport` 多组关键词检索，**只命中编码侧（screen content coding）与个别会议短文**（见文末备选清单），未找到任何 2024–2026 顶会级的"云桌面传输/拥塞控制"专门论文。screen content coding 是编解码社区独立议题（arXiv `all:"screen content coding"` 检索前 12 条全是编码/压缩，无一条传输或 CC）。

---

## 2. 实时视频拥塞控制（RTC CCA）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-09 | ⭐题录级 | Themis: Toward Stable Near-Zero Queuing Delay in Congestion Control for Low-Latency Interactive Video Streaming | Feida Liu | 2025 / **ACM Multimedia（正会）** | DOI:10.1145/3746027.3754552（Crossref 核对） | 0 | 针对低延迟交互视频的 CC：抑制自激振荡，平均帧时延降低 13.5%，在高码率与低排队时延之间取得更好权衡。 | 交互式（帧级 deadline）CC 的最新正会代表之一。与 C-RT-10 / C-RT-11 构成 2025–2026 同题三强。 |
| C-RT-10 | ⭐题录级 | A Practical Congestion Control Algorithm for Low-Latency Interactive Video Streaming | Shibo Wang | 2025 / **IEEE/ACM ToN** | DOI:10.1109/TON.2024.3519902（Crossref 核对） | 2 | 面向低延迟交互视频的**可落地** CC（作者组同源多篇，含 C-RT-57）。 | 期刊版的可部署性论证；ToN 承接说明该题已进 CCF-A 期刊。 |
| C-RT-11 | ⭐摘要级 | Camel: Frame-Level Bandwidth Estimation for Low-Latency Live Streaming under Video Bitrate Undershooting | Liming Liu | 2026 / **The Web Conference (WWW)**（正会） | arXiv:2602.09500 · DOI:10.1145/3774904.3792535 | 0（新） | 观察到反直觉现象：**即便编码码率未跑满可用带宽，卡顿仍频繁**。根因是实时编码的帧级时变让包级 CC 误判可用带宽。作者用**帧级网络反馈**测真实容量，对编码导致的非规则发送模式免疫。 | **"包级 CC 在实时视频上系统性失准"的最清晰论断**。与 C-RT-14（物理层）、C-RT-55（带宽测量）同属"换个观测粒度"路线。同组另有 up-streaming 版：C-RT-12 邻域（EMS@SIGCOMM'25，DOI:10.1145/3746441.3748236，题录级，0 引用）。 |
| C-RT-12 | ⭐题录级 | Enhanced Bandwidth Measurement and Robust Rate Adaptation for Low-Latency Live Streaming | Jiahui Chen | 2025 / **IEEE INFOCOM（正会）** | DOI:10.1109/INFOCOM55648.2025.11044628（Crossref 核对） | 4 | 改进带宽测量 + 鲁棒码率自适应，服务低延迟直播。 | INFOCOM 正会的同题基线；与 C-RT-13 是同一作者组的期刊延伸。 |
| C-RT-13 | 📥题录级 | Toward Robust Low-Latency Live Streaming: Measurement, Prediction, and Rate Adaptation Under Uncertainty | Jiahui Chen | 2026 / **IEEE TMC** | DOI:10.1109/TMC.2026.3656223（Crossref 核对） | 0（新） | 把"测量 → 预测 → 码率自适应"放进不确定性框架下（C-RT-12 的期刊扩展）。 | 说明该题已从"算法"走向"带不确定性的系统方法论"，新意门槛被抬高。 |
| C-RT-14 | ⭐摘要级 | OCC: Physical-Layer Assisted Congestion Control for Real-Time Communications | Yufan Zhuang | 2026 / arXiv | arXiv:2604.22383 | 0（新） | 论证现有 RTC 方案因**依赖试错式探带宽**而无法同时保低延迟与高码率；OCC 直接用物理层信息**显式获得可用带宽**，从而对蜂窝网络的大幅波动做到快速适配。动机段明确点名 cloud gaming / teleoperation / XR 为 6G 核心 RTC 应用。 | **"跨层拿真值"范式的代表**；与 C-RT-15、C-RT-16 构成 2026 年跨层 CC 三连。写"为什么端到端不够"时的最佳引用。 |
| C-RT-15 | ⭐摘要级 | BLADE: Adaptive Wi-Fi Contention Control for Next-Generation Real-Time Communication | Fengqian Guo | 2026 / arXiv | arXiv:2603.16119 | 0（新） | 作者首个大规模测量发现：**即便已部署边缘服务器、专用 CC 与丢包恢复机制，云游戏用户在 Wi-Fi 上仍遭遇长尾延迟**；根因是 Wi-Fi 末跳 AP 的竞争控制标准导致**短时"发送干旱"**。BLADE 分布式自适应调整所有发送端的竞争窗。 | **把长尾延迟从"传输层问题"重新定位到"Wi-Fi MAC 层问题"**——与工作区"边缘端侧/WiFi"主题天然衔接。是"传输优化已到边界、瓶颈在接入"的最强新证据。 |
| C-RT-16 | ⭐题录级 | Synchronizing with the Scheduler: Dual-Loop Congestion Control for 5G Uplink on Commodity Devices | Qiang Wu | 2026 / **ACM SIGCOMM（正会）** | DOI:10.1145/3789240.3829199（Crossref 核对） | 0（新） | 在商用终端上把 CC 与 5G 上行调度器同步的双环设计。 | SIGCOMM 正会 2026 已收"CC × 无线调度器"题；说明"让 CC 看见调度器"是被顶级会议认可的新方向。 |
| C-RT-17 | ⭐题录级 | A Congestion Control Test Suite for Real-Time Communication | Quanwei Zhang | 2025 / **ACM MMSys（正会）** | DOI:10.1145/3712676.3718341（S2 核对） | 1 | 统一评测平台，整合 AlphaRTC、Pandia 等容器化工具，支持多拓扑 + 多 RTC 流并发。 | **做 RTC CC 实验的现成脚手架**；对"我要自己搭评测栈"的项目是直接可用的 baseline 基础设施。 |
| C-RT-18 | 📌题录级 | Mustang: Improving QoE for Real-Time Video in Cellular Networks by Masking Jitter | Encheng Yu | 2024 / **ACM TOMM** | DOI:10.1145/3672399（Crossref 核对） | 6 | 通过"掩盖抖动"而非"消除抖动"改善蜂窝实时视频 QoE。 | 与 C-RT-19/20 的"抖动/排队控制"线相邻；思路上比"压延迟"更工程化。 |
| C-RT-19 | ⭐题录级 **【经典】** | Analysis and design of the google congestion control for web real-time communication (WebRTC) | Gaetano Carlucci | 2016 / **ACM MMSys** | DOI:10.1145/2910017.2910605（Crossref 核对） | 293 | WebRTC GCC（Google Congestion Control）的权威分析与设计。 | **本子方向的奠基文献之一**，任何 RTC CC 工作都必须交代与 GCC 的关系。 |
| C-RT-20 | ⭐题录级 **【经典】** | Congestion Control for Web Real-Time Communication | Gaetano Carlucci | 2017 / **IEEE/ACM ToN** | DOI:10.1109/TNET.2017.2703615（S2 核对） | 139 | 上文的期刊版与体系化。 | 与 C-RT-19 一起构成 GCC 引用的"标准两件套"。 |

---

## 3. L4S / AQM 与超低延迟队列

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-21 | ⭐题录级 **【标准】** | Low Latency, Low Loss, and Scalable Throughput (L4S) Internet Service: Architecture | B. Briscoe | 2023 / **IETF RFC 9330** | DOI:10.17487/RFC9330 | 118 | L4S 架构总纲：用 ECN 双队列 + 可扩展 CC 把排队时延压到近零而不牺牲吞吐。 | L4S 一切工作的引用起点。 |
| C-RT-22 | ⭐题录级 **【标准】** | Dual-Queue Coupled Active Queue Management (AQM) for L4S | Koen De Schepper | 2023 / **IETF RFC 9332** | DOI:10.17487/RFC9332 | 48 | 双队列耦合 AQM 的具体规范（配套协议规范为 **RFC 9331**，DOI:10.17487/RFC9331，36 引用）。 | 实施 L4S 路由侧行为的唯一权威定义。 |
| C-RT-23 | 📌摘要级 | SwiftQueue: Optimizing Low-Latency Applications with Swift Packet Queuing | Siddhant Ray | 2024 / NINeS（workshop） | arXiv:2410.06112 | 2 | 指出 L4S 现在按**流**选队列（同流所有包同队列），但瞬时拥塞只影响部分包 → 用逐包时延预测器决定哪些包该走低延迟队列。 | **L4S 内部的一个真空白**：per-flow 队列选择 vs per-packet 时延差异化。与 C-RT-24 的"包重要性"思路呼应。 |
| C-RT-24 | ⭐题录级 | Lag-Busting WebRTC: L4S-Enabled Adaptive Video Streaming | Yu You | 2026 / **ACM MMSys（正会）** | DOI:10.1145/3793853.3798195（Crossref 核对） | 1 | 把 L4S 与 WebRTC 自适应码率结合起来的最新正会工作。 | L4S × WebRTC 的 2026 年最新态；与 C-RT-25 同会。 |
| C-RT-25 | ⭐题录级 | Low-Latency Volumetric Video Conferencing in Congested Networks Through L4S | Matthias De Fré | 2025 / **ACM MMSys（正会）** | DOI:10.1145/3712676.3714443（Crossref 核对） | 7 | 在拥塞网络下用 L4S 支撑低延迟体积视频会议。 | 把 L4S 推向"比普通会议更重"的负载；与 C-RT-67（同组的 SFU 评测）同一作者线。 |
| C-RT-26 | ⭐题录级 | Adaptable L4S Congestion Control for Cloud-Based Real-Time Streaming Over 5G | Jangwoo Son | 2024 / **IEEE OJSP** | DOI:10.1109/OJSP.2024.3405719（Crossref 核对） | 10 | 云侧实时流（云游戏/云渲染）在 5G 上的可适配 L4S 拥塞控制。 | **"云游戏 + L4S"的直接交叉点**，与 C-RT-02/04 的云游戏需求形成闭环。同作者另有 ICME 2023 版（DOI:10.1109/ICME55011.2023.00176，7 引用，workshop/会议短文，题录级）。 |
| C-RT-27 | ⭐题录级 | To Adopt or Not to Adopt L4S-compatible Congestion Control? Understanding Performance in a Partial L4S Deployment | Fatih Berkay Sarpkaya | 2024 / **PAM（正会）** | arXiv:2411.10952 | 13 | 系统研究**部分部署**（只有一端支持 L4S）时的性能表现。 | **竞品/反方必读**：L4S 的收益在"没全员升级"时会被显著削弱，写"为何还需要端侧方案"的现成论据。 |

---

## 4. QUIC / Media over QUIC / HTTP-3 用于媒体

> **这是本子方向 2024–2026 增长最快的一块**：MoQ 从测试走向 CDN 生产化，随之暴露"传输层看不到帧语义"的系统性问题。

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-28 | ⭐题录级 | Media over QUIC: Initial Testing, Findings and Results | Zafer Gurel | 2023 / **ACM MMSys** | DOI:10.1145/3587819.3593937（Crossref 核对） | 27 | MoQ 的早期测试与发现（Comcast 作者组）。 | MoQ 线的起点引用；其后 2024–2026 的多篇（C-RT-29/32/33）都建立在它上面。 |
| C-RT-29 | ⭐题录级 | Streaming Face-Off: A Testbed Analysis of Media-over-QUIC and Low-Latency DASH | Minh Nguyen | 2025 / **ACM MMSys** | DOI:10.1145/3712676.3719264（Crossref 核对） | 4 | 测试床上正面对比 MoQ 与 LL-DASH。 | **"新范式 vs 老范式"的现成对照实验**，做 MoQ 动机段直接可引。 |
| C-RT-30 | 📌题录级 | Video Streaming Over QUIC: A Comprehensive Study | Jashanjot Singh Sidhu | 2025 / **ACM TOMM** | arXiv:2505.21769 · DOI:10.1145/3793674 | 10 | 核心结论：**同一 CC 算法在不同 QUIC 实现上性能差异显著**，直接影响视频会话 QoE → 需要 QUIC CC 与 ABR 的跨层联合设计。 | **"实现差异 > 算法差异"的重要论断**；为"跨层联合"提供实证动机，与 C-RT-11/57 一致。 |
| C-RT-31 | 📌题录级 | QUIC as Multiplexing Layer in WebRTC | Mathis Engelbart | 2026 / ANRW（workshop） | DOI:10.1145/3822163.3827919（Crossref 核对） | 1 | 实现用 QUIC 同时承载媒体流与 data channel 的原型，能在与数据流公平分享带宽的同时降低媒体延迟与抖动。 | **WebRTC × QUIC 的接口层实验**；是"RTP/RTCP 要不要换掉"这个问题的近期答案之一。 |
| C-RT-32 | ⭐摘要级 | Media-over-Multipath-QUIC for Realtime Video Applications（系统名 MoMQ） | Tanya Shreedhar | 2026 / arXiv | arXiv:2608.10741 | 0（新） | 关键洞察：多路径调度器**只看到字节、看不到帧语义**，分不清"锚定一秒视频的关键帧"与"只损失一帧的增强帧"。限制因素不是路径多样性不足，而是**缺少让应用把语义告诉传输层的通道**。MoMQ 复用 MoQT 的 Object 元数据让应用/中继在边缘装规则来做路径决策。 | **本子方向最重要的一篇新论文之一**：把"传输层语义盲"讲成了可工程化的机制（在 MoQ 上扩展），而不是继续加启发式。与 C-RT-33、C-RT-24 同属"语义感知传输"。 |
| C-RT-33 | ⭐摘要级 | MultiMoQ: Multi-Access Media-Over-QUIC for Robust Immersive Video Streaming | Yitong Li | 2026 / arXiv | arXiv:2608.06102 | 0（新） | 指出 MoQ 在带宽受限下鲁棒性不足、常导致播放停顿；MultiMoQ 基于 MoQ 重做多接入分片流（tile）投递，支持灵活分片调度与无缝接入切换。 | MoQ × 多路径 × 沉浸式（含 360° 分片）；与 C-RT-32 是同期同题的两种解法（一个改调度语义，一个改多接入投递）。 |
| C-RT-34 | 📌题录级 | SwiftShift: Accelerating QUIC Migration for Ultra-Low-Latency Interactive Media | Fangshuo Han | 2026 / NOSSDAV（workshop） | DOI:10.1145/3798065.3798080（Crossref 核对） | 1 | 无需网络侧改动、可无缝集成的 QUIC 迁移加速框架，在紧播放预算下维持 jitter buffer 稳定，迁移期间媒体连续性不中断。 | 与 C-RT-41（Aero）同会；"迁移/切换"是 ULL 场景里被低估的一环。 |
| C-RT-35 | 📌题录级 | Reset the Stream, Keep the Keyframe: Partial Reliability for Media over QUIC Delivery Timeouts | Sebastian Rust | 2026 / ANRW（workshop） | DOI:10.1145/3822163.3827920（Crossref 核对） | 0（新） | MoQ 投递超时下的部分可靠性策略：宁可丢非关键帧也要保住关键帧。 | MoQ 的可靠性语义设计问题；与 C-RT-32 的"帧重要性"是同一根问题。 |
| C-RT-36 | 📌题录级 | Thin-Client Interactive Gaussian Adaptive Streaming over HTTP/3（TIGAS） | Emanuele Artioli | 2026 / arXiv | arXiv:2605.08699 | 0（新） | 把 3D Gaussian Splatting 光栅化卸载到后端，向轻量 Web 客户端**经 QUIC 传视角相关 2D 投影**，绕开网络波动带来的高延迟。 | 远程渲染（云渲染）传输的最新形态；与 C-RT-08 云桌面、C-RT-51 远程渲染协议对比构成"渲染卸载"小群。 |
| C-RT-37 | 📌题录级 | Aero: A Pluggable Congestion Control for QUIC | Jashanjot Singh Sidhu | 2025 / NOSSDAV（**workshop，非正会**） | DOI:10.1145/3712678.3721878（Crossref 核对） | 5 | 面向 QUIC 的首个**基于学习的即插即用** CC，可集成进任意 QUIC 实现。 | 学习型 CC × QUIC 的代表；同作者另有 C-RT-30 与其 TOMM 扩展（DOI:10.1145/3827616，2026，题录级）。**引用时勿标为正会。** |
| C-RT-38 | 📌题录级 | Impact of Prioritized HTTP/3 Transport on Low-Latency Live Streaming | Ayse B. Demir | 2024 / ICMEW（workshop） | DOI:10.1109/ICMEW63481.2024.10645374（S2 核对） | 1 | HTTP/3 优先级机制对低延迟直播的实测影响（Comcast 作者组）。 | 与工作区既有「Fine-grained HTTP/3 Prioritization via RL（Computer Networks 2023）」（文献索引"方法学参考"）同一作者线的延续，可直接衔接。 |

---

## 5. 云游戏 / 云电脑 vs 视频会议 / 直播：传输需求差别的证据小结

> 本节是把上面各表的证据**显式对齐**，用于回答"两类负载差别在哪"。**每条都给出处。**

| 维度 | 云游戏 / 云 VR / 云电脑 | 视频会议 / 低延迟直播 | 证据 |
|---|---|---|---|
| **带宽量级** | 云游戏**最低 10–20 Mbps** | 主机本地游戏约 100–200 kbps；多方可接受约 1 Mbps 级 | C-RT-02（arXiv:2401.06366，摘要级）；QoMEX 2016 的 "1Mbps is enough"（DOI:10.1109/QoMEX.2016.7498961，题录级，21 引用） |
| **延迟预算的刚性与粒度** | **输入→显示端到端**受约束；实测商用平台 112–403 ms 已"严重损害体验"，优化目标是 **sub-100 ms** | 会议容忍度更高（单向百毫秒级至数百毫秒可接受）；低延迟直播目标是秒级以内 | C-RT-01（NSDI'25，摘要级：112–403 ms、sub-100 ms）；C-RT-55 组（LL-DASH/LLS 的秒级目标） |
| **延迟在应用内是否均匀** | **不均匀**：不同内容/场景延迟敏感度不同，可据此重分配 | 同样不均匀，但会议对"音画同步"有额外交互约束 | C-RT-05（MMSys'26 Trinity，题录级）；C-RT-03（arXiv:2509.19669，题录级） |
| **成本结构** | **带宽占云游戏运营成本 30–60%** → 码率是成本项而非纯体验项 | 直播侧成本主要体现为 CDN 带宽与预取浪费 | C-RT-04（arXiv:2607.11231，摘要级） |
| **瓶颈位置** | 一是**云侧渲染管线**（VSync 串行化，C-RT-01）；二是**Wi-Fi 末跳竞争控制导致的发送干旱**（C-RT-15） | 一是**端到端 CC 的带宽误估**（C-RT-11 帧级 vs 包级）；二是 **L4S 部分部署下收益打折**（C-RT-27） | C-RT-01、C-RT-15、C-RT-11、C-RT-27 |
| **丢包修复的可用手段** | 严格 deadline → **重传基本不可行**，必须走 FEC/神经编解码 | 同左，但可在 CDN 侧做**延期 ARQ + 多供应商**的加速恢复 | C-RT-46（GRACE 摘要："high-latency 下重传不可行"）、C-RT-48（Reparo 摘要："重传因实时播放不可行"）、C-RT-49（AutoRec 摘要：多供应商市场只需服务端改动） |
| **协议栈现状** | WebRTC/RTP 为主，正在被 WebTransport/MoQ 侵蚀；**云桌面另有 Guacamole/远程桌面系协议** | LL-DASH/LL-HLS/CMAF 与 WebRTC 并存；MoQ 作为新范式快速上升 | C-RT-11（WebTransport 云串流）、C-RT-29（MoQ vs LL-DASH）、C-RT-31（QUIC as multiplexing layer）；云桌面协议见文末备选 |
| **"云电脑/云桌面"单独一类** | 内容为文本/UI（屏幕内容），编码社区已有成熟 SCC 工具链；传输侧**有**带宽/吞吐预测一条线（DeskTransfer/DeskPred/CCA-MoE，见同目录 B 文件），但**拥塞控制、丢包修复、协议级实测均缺** | — | 见 §13 研究空白 ① |

---

## 6. 学习增强 / 神经 CC / 语义与生成式传输（新范式）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-39 | ⭐题录级 | Astraea: Towards Fair and Efficient Learning-based Congestion Control | Xudong Liao | 2024 / **ACM EuroSys** | arXiv:2403.01798 · DOI:10.1145/3689031.3696065 | 40 | 在奖励里编码性能目标，使学习型 CC **即使在未见过的竞争场景下**也不伤害其他流。 | 学习型 CC 的"公平性"问题的首个主流答案；与 C-RT-40 同会。 |
| C-RT-40 | ⭐题录级 | Achieving Fairness Generalizability for Learning-based Congestion Control with Jury | Han Tian | 2025 / **ACM EuroSys** | DOI:10.1145/3689031.3696065（Crossref 核对） | 13 | 用"陪审团"机制做跨场景公平泛化。**注意：S2 检索把 Astraea 与 Jury 的 DOI 都指向 10.1145/3689031.3696065，其中至少一条是 S2 元数据串号——本表 Astraea 的 DOI 以 arXiv:2403.01798 为准，Jury 的 DOI 以 Crossref 查询结果为准。** | 与 C-RT-39 是同一条问题线的两篇；**两篇并存说明"公平性泛化"到 2025 仍未解决**（见 §13 研究空白 ③）。 |
| C-RT-41 | 📌题录级 | EchoCC: Refining Learning-Based Congestion Control With WordBook | Yu Fan | 2025 / **IEEE/ACM ToN** | DOI:10.1109/TON.2025.3566495（Crossref 核对） | 2 | 用 WordBook 对学习型 CC 做修正/精化。 | 学习型 CC 的另一条补救路线（"手工修正学习结果"）；期刊级。 |
| C-RT-42 | ⭐题录级 | Learning-Based vs Human-Derived Congestion Control: An In-Depth Experimental Study | Mihai Mazilu | 2025 / arXiv | arXiv:2510.25105 | 3 | 可复现的系统性对比评测，目标不是"谁赢"而是**揭示学习型 CC 的根本局限**，并明确指出该领域"仍需大量研究才能产出可部署方案"。 | **本子方向最值得引的"泼冷水"**：给"学习型 CC 还不能上生产"提供可引断言。 |
| C-RT-43 | 📌摘要级 | Loss-tolerant neural video codec aware congestion control for real time video communication | Zhengxu Xia | 2024 / arXiv | arXiv:2411.06742 | 0 | 指出在线 RL 训练的**试错行为本身会让 RTC 的 QoE 在运行时灾难性下降**，必须有回退到手工启发式的保底策略——但保底又打断学习。目标是让 CC 感知"神经编解码可容忍哪些丢包"。 | **把"CC"与"抗丢包编解码"耦合起来的第一类论文**；与 C-RT-46/54 的神经编解码线合流。 |
| C-RT-44 | ⭐题录级 | Enhancing Mobile Immersive Streaming Experience via Deadline-Aware Scheduling and Learning-Enhanced Congestion Control | Long Luo | 2025 / IEEE IoT-J | DOI:10.1109/JIOT.2025.3621630（S2 核对） | 8 | 把 deadline 感知调度与"学习增强"拥塞控制结合服务移动沉浸式流。 | **检索到的最接近 "learning-augmented CC" 的一篇**（见 §13 研究空白 ④）。 |
| C-RT-45 | ⭐题录级 | Goal-Oriented Semantic Communication for Wireless Video Transmission via Generative AI | Nan Li | 2025 / **IEEE TWC** | arXiv:2502.20927（**正规期刊 DOI 本轮未取到，引用请用 arXiv 版**） | 24 | 用生成式 AI 做目标导向的无线视频语义传输。 | 语义/生成式传输的代表作；**注意这是"无线通信"社区的问题设定**（仿真为主、PHY 层抽象），与端到端 RTC 系统论文的评估口径不可直接比较——引用时要说明。同线还有：Generative AI for Immersive Video（IJCAI'24，DOI:10.24963/ijcai.2024/1162，2 引用，题录级）。 |
| C-RT-46 | 📌题录级 | GenRL-CC: A GAN-Augmented Deep Reinforcement Learning Framework for Adaptive Congestion Control in Real-Time Communication | Md Ruman Islam | 2026 / IEEE ICCCN | DOI:10.1109/ICCCN69946.11662826（**DOI 疑似截断，S2 原样：10.1109/ICCCN69946.2026.11662826**） | 0（新） | 用 GAN 增强 DRL 做 RTC 自适应拥塞控制。 | 说明"RL + 生成式增强做 CC"仍在快速增密，但多数落在非顶会；**引用前需在 IEEE Xplore 核对 DOI**。 |

---

## 7. 丢包修复：FEC / 流式码 / ARQ / 神经与生成编解码

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-47 | ⭐摘要级 | GRACE: Loss-Resilient Real-Time Video through Neural Codecs | Yihua Cheng | 2023 / **USENIX NSDI（正会）** | arXiv:2305.12333 | 53 | 明确的动机断言：**实时视频通信中，高延迟网络下重传不可行**。传统两条路（编码端 FEC / 解码端错误掩盖）各有硬伤：FEC 的冗余度无法事前最优；掩蔽要牺牲压缩效率且不改编码器就无法真正恢复。GRACE 用一个统一的神经视频编解码帧在宽丢包区间保住 QoE。 | **神经编解码抗丢包线的起点**，被 C-RT-48/54 直接延续。写"FEC 的冗余度矛盾"必引。 |
| C-RT-48 | ⭐题录级 **【经典】** | Tambur: Efficient loss recovery for videoconferencing via streaming codes | Michael Rudow | 2023 / **USENIX NSDI（正会）** | 无 ID（S2 未给 arXiv/DOI；DBLP 见会议页） | 77 | 用**流式码（streaming codes）**做视频会议丢包恢复的经典系统工作。 | 与工作区已知的 Rudow & Rashmi "Learning-Augmented Streaming Codes"（IEEE ISIT 2022）**同一作者线**——文献索引已有后者，本条是系统侧前作，可直接对接。 |
| C-RT-49 | ⭐摘要级 | Reparo: Loss-Resilient Generative Codec for Video Conferencing | Tianhong Li | 2023 / arXiv | arXiv:2305.14135 | 25 | 指出重传因实时播放不可行、FEC 因 Internet 丢包**不可预测且突发**而难定冗余量：多了浪费带宽、少了帧不可解并连锁劣化后续帧。Reparo 用生成式深度模型按已收数据**生成缺失信息**。 | 与 C-RT-47 同期、思路互补（生成 vs 编码）；**"FEC 冗余度的两难"在这两篇里被讲得最清楚**。 |
| C-RT-50 | ⭐摘要级 | AutoRec: Accelerating Loss Recovery for Live Streaming in a Multi-Supplier Market | Tong Li | 2025 / **IEEE/ACM ToN** | arXiv:2511.22046（**期刊 DOI 本轮未取到，引用请用 arXiv 版**） | 1 | 大规模测量（**最多 5000 万条直播流**）发现：真实环境中丢包具有动态性、直播存在频繁的 on-off 模式切换；**被重传丢包放大的恢复延迟是影响客户端 QoE（如卡顿）的关键因素**。AutoRec 把 on-off 切换的劣势转化为减少丢包重传的优势。 | **需求侧最强的"丢包修复"规模证据**；同时点明 CDN 多供应商市场下**只能改服务端**的工程约束（这直接排除了很多双边方案）。 |
| C-RT-51 | 📌题录级 | Toward Timeliness-Enhanced Loss Recovery for Large-Scale Live Streaming | Bo Wu | 2024 / **ACM Multimedia（正会）** | DOI:10.1145/3664647.3681423（Crossref 核对） | 3 | 面向大规模直播的"时效性增强"丢包恢复。 | 与 C-RT-50 同题的会议版；二者可互证"及时性 > 完整性"这一设定在大规模直播中成立。 |
| C-RT-52 | ⭐题录级 | Triage: Boosting Cross-region Video Conferencing with Proactive FEC on Overlay Network | Yifan Liu | 2026 / PACMNET（Proc. ACM Netw.） | DOI:10.1145/3830396（Crossref 核对） | 0（新） | 在 overlay 网络上做**主动 FEC** 以提升跨区域视频会议质量。 | FEC 从"端侧自适应"走向"网络侧主动注入"；与 C-RT-62/63（SFU/SDN 化会议）是同一"网络参与会议传输"的趋势。 |
| C-RT-53 | ⭐题录级 | SmartFEC: adaptive SmartNIC-enabled forward error correction for low-latency video services | Qianyun Gong | 2026 / **Science China Information Sciences** | DOI:10.1007/s11432-025-5014-9（Crossref 核对） | 0（新） | 把自适应 FEC 卸载到 SmartNIC 上，服务低延迟视频。 | **"FEC 卸载到可编程网卡"这个交叉点**；与工作区 DPDK/SmartNIC 主题（DBK-E）和对"内核旁路数据面"的兴趣天然衔接。 |
| C-RT-54 | 📌题录级 | Semantic-Aware Neural Video Codec for Error-Resilient Low-Latency Transmission | Matin Mortaheb | 2026 / arXiv | arXiv:2609.16279 | 0（新） | 基于实时神经编解码器 DCVC-RT，把编码表示**按语义/特征重要度分层打包**，不同优先级走不同流；并设计抗错熵编码模式。 | **把"帧/包重要度分层"同时用在编解码与传输两侧**，是 C-RT-43（CC 感知）与 C-RT-32（传输语义通道）的汇合点。 |
| C-RT-55 | 📌题录级 | Breath: Adaptive Protection Boundary in FEC Encoding for Mobile Real-Time Video Streaming | Shiyang Huang | 2026 / **The Web Conference (WWW)** | DOI:10.1145/3774904.3792265（S2 核对） | 0（新） | 移动实时视频 FEC 编码的"保护边界"自适应。 | 传统 FEC 路线的 2026 年正会新作；说明 FEC 未被神经方法完全取代。 |

---

## 8. 低延迟直播的 ABR 与帧级控制

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-56 | ⭐题录级 | Low-Latency Live Video Streaming over a Low-Earth-Orbit Satellite Network with DASH | Jinwei Zhao | 2024 / **ACM MMSys（正会）** | DOI:10.1145/3625468.3647616（Crossref 核对） | 48 | LEO 卫星网下的低延迟 DASH 直播（本组引用最高的一篇）。 | **星地链路是 2024–2026 的新变量**，与 C-RT-73（SIGCOMM'26 在 Starlink 上测会议应用）构成同一新场景的两条证据。 |
| C-RT-57 | ⭐题录级 | Enhancing Low Latency Adaptive Live Streaming Through Precise Bandwidth Prediction | Bo Wang | 2024 / **IEEE/ACM ToN** | DOI:10.1109/TNET.2024.3426607（Crossref 核对） | 8 | 用精确带宽预测改善低延迟自适应直播。 | 与工作区「吞吐/链路预测」主题（Minovski 2021、Yue 2018 LinkForecast、Narayanan 2020 Lumos5G）**直接相邻**：那里是蜂窝吞吐预测，这里是低延迟直播专用带宽预测。 |
| C-RT-58 | ⭐题录级 | Rethinking Bitrate Adaptation in WebRTC-Based Low-Latency Live Streaming Systems（系统名 Salmon） | Shibo Wang | 2026 / NOSSDAV（workshop） | DOI:10.1145/3798065.3798073（Crossref 核对） | 0（新） | 针对 WebRTC 系 LLLS 的**新 QoE 目标、双流切换、用户交互行为、应用特定信号语义**四个新挑战重构码率自适应。 | **LLLS 的 ABR 与 VOD 的 ABR 不是同一个问题**；与 C-RT-10 同作者组。 |
| C-RT-59 | ⭐题录级 | Cross-Layer Dynamics in Live Low-Latency: A Dataset of ABR, CC, and AQM Interactions | Md Tariqul Islam | 2026 / QoMEX（workshop） | DOI:10.1109/QoMEX69967.2026.11618338（S2 核对） | 0（新） | 公开发布 **ABR × CC × AQM 三者交叉作用的数据集**（Timmerer/Rothenberg/Tashtarian 组）。 | **做实验时的现成数据集/对照基准**；同时说明"三层交互"已被公认为需要专门数据集来研究的对象。 |
| C-RT-60 | 📌题录级 | Playing Catch-Up: Evaluating Playback Speed Control in Low-Latency Live Streaming | Yunhao Liang | 2024 / QoMEX（workshop） | DOI:10.1109/QoMEX61742.2024.10598290（S2 核对） | 3 | 系统评估低延迟直播里的**播放速度控制**（追赶而非丢帧）。 | 与 C-RT-11/C-RT-58 的"延迟追赶"是同一类机制；"改播放速度"是低延迟直播特有而 VOD 没有的手段。 |
| C-RT-61 | ⭐题录级 **【经典】** | HxL3: Optimized Delivery Architecture for HTTP Low-Latency Live Streaming | Farzad Tashtarian | 2023 / **IEEE TMM** | DOI:10.1109/TMM.2022.3148587（Crossref 核对） | 22 | HTTP 低延迟直播的优化投递架构（该方向的体系化代表）。 | LL-HLS/LL-DASH/CMAF 交付架构的必引；与 C-RT-59 同作者群。 |
| C-RT-62 | 📌题录级 | Hybrid Unicast–Broadcast Video Delivery for Scalable Low-Latency Live Streaming | Casper Haems | 2026 / **ACM TOMM** | DOI:10.1145/3742868（Crossref 核对） | 5 | 把 5G 广播与单播融合，实现 **sub-1 秒**直播延迟；解决大规模并发时的可扩展性。 | **"广播补单播"是低延迟直播特有的可扩展性路线**，云游戏/会议没有对应手段——正好是两类负载的差别之一。 |
| C-RT-63 | 📌题录级 | Conflux: A Multi-Homed Adaptive Bitrate Protocol for On-Site Live Video Streaming | Sharon Choy | 2025 / **IEEE/ACM ToN** | DOI:10.1109/TON.2025.3577974（Crossref 核对） | 0 | 多宿主（multi-homed）现场直播的自适应码率协议。 | 现场直播（体育/新闻）的多链路聚合并发；与 C-RT-32/33 的多路径线相邻。 |

---

## 9. 架构：SFU / SDN 化 / 在网处理 / 云边协同

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-64 | ⭐摘要级 | Scalable Video Conferencing Using SDN Principles（系统名 Scallop） | Oliver Michel | 2025 / **ACM SIGCOMM（正会）** | arXiv:2503.11649 · DOI:10.1145/3718958.3750489（Crossref 核对） | 15 | 洞察：**生产环境的 SFU 本质就是在做"丢弃与转发"**——因此把会议应用拆成"硬件数据面做延迟敏感的频繁媒体操作 + 软件面做慢操作"的 SDN 式 SFU。 | **本子方向最重要的架构新论文**：把"可编程数据面"引入实时会议，与工作区在网计算/DPDK 主题直接交汇。 |
| C-RT-65 | 📌题录级 | A Selective Forwarding Unit Implementation in P4 | Pavlos Tsikrikas | 2024 / IEEE CSCN（会议短文） | DOI:10.1109/CSCN63874.2024.10849740（S2 核对） | 1 | 在 P4 上实现 SFU。 | 与 C-RT-64 同题的早期实现；文献量极少，说明"SFU 下沉到可编程数据面"仍很空。 |
| C-RT-66 | ⭐题录级 | DSJA: Distributed Server-Driven Joint Route Scheduling and Streaming Adaptation for Multi-Party Realtime Video Streaming | Dayou Zhang | 2024 / **IEEE TMC** | DOI:10.1109/TMC.2023.3339671（Crossref 核对） | 13 | 多方实时视频的"路径调度 + 流自适应"联合优化（服务端驱动、分布式）。 | 多方会议的服务侧联合优化代表；与 C-RT-17（评测基建）、C-RT-64（数据面下沉）互补。 |
| C-RT-67 | ⭐题录级 | CellFusion: Multipath Vehicle-to-Cloud Video Streaming with Network Coding in the Wild | Yunzhe Ni | 2023 / **ACM SIGCOMM（正会）** | DOI:10.1145/3603269.3604832（Crossref 核对） | 43 | 车-云多路径视频流 + **网络编码**，真实路测。 | 多路径 + 网络编码在移动实时视频的最强实地验证；与 C-RT-32/33（MoQ 多路径）是不同协议栈下的同题做法。 |
| C-RT-68 | 📌题录级 | WebRTC-Based Volumetric Video Conferencing: SFU Architecture Evaluation and Benchmarking | Matthias De Fré | 2026 / NOSSDAV（workshop） | DOI:10.1145/3798065.3798070（Crossref 核对） | 0（新） | 开源、编解码无关的体积视频 SFU；在 5 ms/10 ms 网络延迟下，**WebRTC 比 TCP 系对手分别快 13% 和 36%** 地把画质自适应到用户运动。 | 会议负载变重后的架构评测；与 C-RT-25 同组。 |
| C-RT-69 | 📌题录级 | uvgComm: Open Software for Low-Latency Multi-party Video Communication | Joni Räsänen | 2024 / **ACM Multimedia** | DOI:10.1145/3664647.3685514（**Crossref 未命中，仅 S2 题录**） | 1 | 低延迟多方视频通信的开源软件。 | 可复用的开源实验平台候选；**DOI 待 Crossref 复核后方可正式引用**。 |

---

## 10. 测量研究与权威综述

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C-RT-70 | ⭐摘要级 | **Low-Latency Video Streaming: Applications, Challenges, and Trends** | Xun Tang（清华，Qing Li / Yong Jiang 组） | 2026 / **IEEE COMST** 28:6384-6414 | DOI:10.1109/COMST.2026.3689266（Crossref 核对） | 4 | **本子方向的头号权威综述**（199 篇参考文献）。摘要明确：现有综述多只覆盖流水线单个环节，缺少统一视角；本文组织为「应用域 → 三大复现挑战（Large Data / Network Bandwidth / Prediction）→ 压缩与交付、传输与拥塞控制、自适应流、QoS/QoE 预测 → AI 如何重塑流水线（学习型优化、生成式/基础模型驱动的流媒体、智能网络控制）」。**并明确"先总结代表应用域，再说明其延迟需求如何引出不同的技术瓶颈"。** | **写任何引言的第一引**；其"应用域 × 延迟需求 × 瓶颈"的组织方式正是本文件 §5 的权威背书。 |
| C-RT-71 | ⭐题录级 | Evaluating Transport Layer Congestion Control Algorithms: A Comprehensive Survey | Christian L. Vielhaus | 2026 / **IEEE COMST** | DOI:10.1109/COMST.2025.3533303（Crossref 核对） | 14 | 传输层拥塞控制算法的系统评测综述。 | CC 侧的权威参照；与 C-RT-70 互补（一个从应用看，一个从 CC 看）。 |
| C-RT-72 | ⭐题录级 | Immersive Multimedia Communication: State-of-the-Art on Extended Reality Streaming | Haopeng Wang | 2025 / **ACM TOMM** | arXiv:2506.10004 · DOI:10.1145/3721292（S2+Crossref 核对） | 15 | XR 流媒体的现状综述。 | 云 VR / 云渲染一侧的综述；与 C-RT-70 分工不同。 |
| C-RT-73 | ⭐题录级 | Real-Time Immersive Aerial Video Streaming: A Comprehensive Survey, Benchmarking, and Open Challenges | Mohit K. Sharma | 2024 / **IEEE OJCOMS** | DOI:10.1109/OJCOMS.2024.3455763（Crossref 核对） | 24 | 实时沉浸式空中（无人机）视频流的综述 + benchmark + 开放挑战。 | **罕见的"综述里带 benchmark"**；若要做实验脚手架可参考其评测口径。 |
| C-RT-74 | ⭐题录级 | Towards AI-Assisted Sustainable Adaptive Video Streaming Systems: Tutorial and Survey | Reza Farahani | **2026** / **ACM Computing Surveys**（S2 记 2024，Crossref 记 2026，以 Crossref 为准） | arXiv:2406.02302 · DOI:10.1145/3838182（Crossref 核对） | 25 | AI 辅助/可持续的自适应视频流系统教程 + 综述。 | 与 C-RT-70 互补的方法论综述；也是"AI × 视频流"的入门读物。**年份以 Crossref 为准。** |
| C-RT-75 | ⭐题录级 | Where Does My Call Go? Measuring Google Meet, Zoom, and Microsoft Teams on Starlink | Kousar Malekinasab | 2026 / **ACM SIGCOMM（正会）** | DOI:10.1145/3789240.3827595（Crossref 核对） | 0（新） | 在 Starlink 上测量三大商用会议平台的实际行为。 | **"云会议在 LEO 卫星接入下的行为"刚被顶会正面研究**；与 C-RT-56（LL-DASH over LEO）合起来说明 LEO 是新变量。 |
| C-RT-76 | ⭐题录级 | Automated, Cross-Layer Root Cause Analysis of 5G Video-Conferencing Quality Degradation | Fan Yi | 2025 / **ACM IMC（正会）** | arXiv:2505.14540 · DOI:10.1145/3730567.3764434（Crossref 核对） | 6 | 同时测私有 CBRS 与商用蜂窝，把**物理层/链路层事件**与网络层、传输层及会议应用本身的表现关联起来做跨层归因。 | **跨层归因方法论的最佳范本**；直接支撑 C-RT-14/15/16 的"跨层拿信息"路线。 |
| C-RT-77 | ⭐题录级 | Evaluation of Uplink Video Streaming QoE in 4G and 5G Cellular Networks Using Real-World Measurements | Darius Chmieliauskas | 2025 / IEEE Access | DOI:10.1109/ACCESS.2025.3554340（Crossref 核对） | 9 | 4G/5G 上行视频流 QoE 的真机测量与开放数据集。 | **上行**方向（直播推流）的实测底表；多数 RTC 研究只关心下行，上行是相对空白。 |
| C-RT-78 | 📌题录级 | A First Look at Immersive Telepresence on Apple Vision Pro | Ruizhi Cheng | 2024 / **ACM IMC（正会）** | arXiv:2405.10422 · DOI:10.1145/3646547.3689006（S2+Crossref 核对；**注意 S2 曾把它误挂到 C-RT-76 的 DOI 上**） | 31 | 对 Vision Pro 沉浸式临场感的首次测量。 | 端侧硬件形态变化（头显）带来的新测量对象；与 C-RT-72/73 的 XR 线相邻。 |
| C-RT-79 | ⭐题录级 | Estimating WebRTC Video QoE Metrics Without Using Application Headers | Taveesh Sharma | 2023 / **ACM IMC（正会）** | arXiv:2306.01194 | 49 | 不依赖应用头，从网络侧推断 WebRTC 视频 QoE 指标。 | **网络运营商视角的 QoE 测量奠基**；对"无法改客户端"的部署约束（同 C-RT-50）是同一类问题的另一面。 |
| C-RT-80 | ⭐题录级 | NIER: Practical Neural-enhanced Low-bitrate Video Conferencing | Anlan Zhang | 2025 / **ACM SIGCOMM（正会）** | DOI:10.1145/3718958.3750518（Crossref 核对） | 0（新） | 神经增强低码率视频会议的生产化尝试。 | **"神经增强"进入 SIGCOMM 正会的标志**；与 C-RT-54（神经编解码分层打包）互补。**注意**：该 DOI 前缀 `10.1145/3718958.*` 与 Scallop 同会次但不同论文，勿混。 |

---

## 11. 另有价值但本轮未展开的条目（题录级，勿直接引用正文细节）

> 以下条目均已通过 S2 或 Crossref 题录核验（标题/年份/出处/ID），但**未读摘要或正文**，只作为扩展线索。

| 标题 | 一作 | 年份/出处 | ID | 引用(S2快照) |
|---|---|---|---|---|
| AUGUR: Practical Mobile Multipath Transport Service for Low Tail Latency in Real-Time Streaming | Yuhan Zhou | 2024 / USENIX NSDI（正会） | 无 ID（S2 题录） | 26 |
| Ultra-low Latency Video Delivery Over WebRTC Data Channels | Nelson Francisco | 2024 / Mile-High Video（workshop） | DOI:10.1145/3638036.3640247 | 6 |
| Design and Implementation of a Low-Latency Origin and Relay for Media-over-QUIC Transport | Zafer Gurel | 2024 / ACM MMSys（正会） | DOI:10.1145/3625468.3652914 | 1 |
| LLL-CAdViSE: Live Low-Latency Cloud-Based Adaptive Video Streaming Evaluation Framework | Babak Taraghi | 2023 / IEEE Access | DOI:10.1109/ACCESS.2023.3257099 | 14 |
| ABRF: Adaptive BitRate-FEC Joint Control for Real-Time Video Streaming | Shengcheng Cheng | 2023 / IEEE TCSVT | DOI:10.1109/TCSVT.2023.3248164 | 16 |
| ReCoCo: Reinforcement learning-based Congestion control for Real-time applications | Dena Markudova | 2023 / IEEE HPSR | DOI:10.1109/HPSR57248.2023.10147986 | 10 |
| Anole: A Pragmatic Blend of Classic and Learning-Based Algorithms in Congestion Control | Feixue Han | 2025 / IEEE TC | DOI:10.1109/TC.2025.3566872 | 4 |
| Combining Heuristic and Reinforcement Learning to Achieve the Low-latency and High-throughput Receiver-side Congestion Control（系统名 Nuwa） | Xianliang Jiang | 2025 / arXiv | arXiv:2502.16498 | 4 |
| A Concern-Decoupled Architecture for Scenario-Optimized Congestion Control in Large-Scale Live Video CDNs | Danfu Yuan | 2026 / IEEE/ACM ToN | DOI:10.1109/TON.2026.3651621 | 0 |
| ML Models for Detecting QoE Degradation in Low-Latency Applications: A Cloud-Gaming Case Study | Joël Roman Ky | 2023 / IEEE TNSM | DOI:10.1109/TNSM.2023.3293806 | 6 |
| In-Network AR/CG Traffic Classification Entirely Deployed in the Programmable Data Plane: Unlocking RTP Features and L4S Integration | Alireza Shirmarz | 2025 / IEEE NetSoft | DOI:10.1109/NetSoft64993.2025.11080610 | 5 |
| Decento: A New Scalable Interactive Live Streaming System via Control Plane Decentralization | Jongyun Lee | 2026 / IEEE INFOCOM（正会） | DOI:10.1109/INFOCOM59046.2026.11571270 | 0 |
| ALIVE: A Latency- and Cost-Aware Hybrid P2P-CDN Framework for Live Video Streaming | Reza Farahani | 2024 / IEEE TNSM | DOI:10.1109/TNSM.2023.3335190 | 30 |
| Prototyping QoE-Aware Rate Adaptation in Cellular Networks with Commercial Applications | Szilveszter Nádas | 2026 / arXiv | arXiv:2609.09490 | 2 |
| An Evaluation of ABR Switching for Time-Shifted Clients in MoQ | Abanisenioluwa Orojo | 2026 / arXiv | arXiv:2606.26368 | 0 |
| MoQSplat: Adaptive Progressive Streaming of 3D Gaussian Splatting via MoQ | Emanuele Artioli | 2026 / arXiv | arXiv:2609.18624 | 0 |
| MLVC: Multi-platform Learned Video Codec for Real-World Deployment | Tanel Pärnamaa | 2026 / arXiv | arXiv:2606.28027 | 1 |
| Artic: AI-oriented Real-time Communication for MLLM Video Assistant | Jiangkai Wu | 2026 / SIGCOMM 系（S2 题录名 "Conference on Applications, Technologies, Architectures, and Protocols for Computer Communication"） | arXiv:2602.12641 | 0 |
| Adaptive Video Encoder for Network Bandwidth Drops in Real-Time Communication | Hua Meng | 2025 / **ACM SIGCOMM 2025 Posters and Demos（非正会）** | DOI:10.1145/3744969.3748452 | 0 |
| Optimizing an Open VVC Encoder for Low Delay Remote Desktop Applications | Anastasia Henkel | 2024 / ICMEW（workshop） | DOI:10.1109/ICMEW63481.2024.10645432 | 0 |
| Video transmission optimization scheme based on the Guacamole protocol | Xuan Zheng | 2025 / 会议论文（SPIE） | DOI:10.1117/12.3071178 | 0 |
| NeR-SC: Adapting Neural Video Representation to Screen Content | Ruohan Shi | 2026 / arXiv | arXiv:2605.27024（**已用 arXiv `id_list` 核验**） | 0 |
| Media over QUIC with Bicast in Wireless Multihomed Networks（QoE 评估） | Yamato Kashihara | 2026 / ICOIN | DOI:10.1109/ICOIN68469.2026.11480624 | 0 |
| Bandwidth Prediction for Media over QUIC | Sepehr Shirani | 2025 / Mile-High Video（workshop） | DOI:10.1145/3715675.3715844 | 1 |
| FrameTrace: Frame-Level Telemetry for Media over QUIC | Birkan Denizer | 2025 / EMS@SIGCOMM（workshop） | DOI:10.1145/3746441.3748231 | 2 |
| Towards Available Bandwidth Estimation for Low-Latency Up-Streaming Amidst Application-Limited Scenarios | Zhidong Jia | 2025 / EMS@SIGCOMM（workshop） | DOI:10.1145/3746441.3748236 | 0 |
| PulseQUIC: Enhancing QUIC-Based Video Streaming through DRL-Guided Adaptive Pacing | Guillermo Tremols Suarez | 2025 / EMS@SIGCOMM（workshop） | DOI:10.1145/3746441.3748232 | 0 |
| Streaming Remote rendering services: Comparison of QUIC-based and WebRTC Protocols | Daniel Mejías | 2025 / IEEE BMSB | arXiv:2505.22132 · DOI:10.1109/BMSB65076.2025.11165653 | 3 |
| Evaluating L4S Framework Performance with Programmable Data Plane Hardware | Leandro C. de Almeida | 2024 / SBRC WGRS（workshop） | DOI:10.5753/wgrs.2024.3286 | 5 |
| iRED: A Disaggregated P4-AQM Fully Implemented in Programmable Data Plane Hardware | Leandro C. de Almeida | 2026 / IEEE/ACM ToN | arXiv:2310.18088 · DOI:10.1109/TON.2026.3651911 | 4 |
| SMART: Software-Driven Programmable Network Support for Real-Time Applications | — | 见 SBRC/WGRS 同系列 | 待核实 | — |

---

## 12. 检索局限（必须随结论一起转述）

### 12.1 成功的核验
- **arXiv `id_list` 批量核验 4 轮，共 40 个 arXiv ID**，逐字比对标题 + 提交年月 + 一作，**全部命中**（含 2602.09500 / 2608.10741 / 2608.06102 / 2604.22383 / 2603.16119 / 2605.08699 / 2609.16279 / 2609.09490 / 2609.18624 / 2606.28027 / 2602.12641 / 2509.19669 / 2505.22132 / 2509.11807 / 2505.14540 / 2503.11649 / 2401.06366 / 2305.12333 / 2305.14135 / 2411.06742 / 2511.22046 / 2502.16498 / 2510.25105 / 2410.06112 等）。
- **Crossref 逐 DOI 核验 42 个 DOI**，逐条比对题名 / container-title / 出版年 / 一作。据此确认了几处容易出错的地方：
  - `10.1109/COMST.2026.3689266` 确为 COMST 2026 卷 28 页 6384-6414；
  - `10.1145/3789240.3827595` 的 container-title 明文为 **"Proceedings of the ACM SIGCOMM 2026 Conference"**（正会，非 workshop）；
  - `10.1145/3798065.*` 与 `10.1145/3712678.*` 的 container-title 明文为 **"…Workshop on Network and Operating System Support for Digital Audio and Video"**（NOSSDAV，**workshop**）；
  - `10.1145/3744969.3748452` 的 container-title 明文为 **"Proceedings of the ACM SIGCOMM 2025 Posters and Demos"**（**非正会**）；
  - `10.1145/3746441.*` 的 container-title 为 **"…Workshop on Emerging Multimedia Systems"**（EMS@SIGCOMM，**workshop**）。

### 12.2 失败 / 受限的通道
1. **S2 `POST /paper/batch` 完全不可用**：本环境对该端点的 POST 请求**连接被重置**（`curl: (35) Recv failure: Connection was reset`，HTTP 000），实测 3 次均失败；MCP 侧的 `bulk_papers` JSON 批量校验**超时失败**（20 个 ID、48 s 后 "Request timed out after all retries"）。→ 批量核验改走 **Crossref GET + arXiv `id_list`** 两条独立通道，覆盖等价。
2. **S2 Graph API 限流严重**：`paper/search` 与 `paper/{id}` 在密集调用下反复返回 **429 Too Many Requests**；文中"引用数"取自**限流间隙成功抓取的快照**，个别条目（如 C-RT-03 Games Are Not Equal）**未取到 S2 引用数，已标"待核实"**，不得补填。
3. **S2 元数据串号（已发现并标注）**：`Astraea` 与 `Jury` 的 S2 记录都指向同一 DOI `10.1145/3689031.3696065`；`A First Look at Immersive Telepresence on Apple Vision Pro` 的 S2 DOI 与 `Automated, Cross-Layer Root Cause Analysis…` 相同（`10.1145/3730567.3764434`）。→ 表中已明确以 Crossref / arXiv 为准，引用前须再核。
4. **局部 DOI 未解析成功**：`10.1109/ACCESS.2024.3405719`（Adaptable L4S CC 的 S2 记录 DOI）与 `10.1145/3664647.3685514`（uvgComm）**Crossref 无响应/未命中**，已在表中以 S2 题录标注并加"待复核"。
5. **未做事**：本轮**未做** S2 的 `citations` / `references` 滚雪球（`include_references` / `include_citations`）——受限于 429 与新论文多为 2026 年 9 月刚挂（引用关系尚未建立，滚雪球价值低）；**未读任何 PDF 正文**（正文级仅 §5 中通过 Tavily 抓到的 USENIX 页面片段，已在 C-RT-01 标注）；**未检索 DBLP**（工作区历史记录显示本环境被反爬拦截）。
6. **"没找到" ≠ "不存在"**：本轮所有"未找到"类结论（云桌面传输、learning-augmented CC、MoQ 的 ABR-CC 耦合）**均受上述 429/连接重置影响**，正式立题前需补一轮不受限流的检索。

### 12.3 不得引用清单（本轮核实后仍不成立 / 未核实）
- **`uvgComm`（DOI:10.1145/3664647.3685514）**：仅 S2 题录，Crossref 未命中 → 未核到场馆页面前不得标为"ACM Multimedia 论文"。
- **SBRC/WGRS 同系列中"SMART: Software-Driven Programmable Network Support for Real-Time Applications"**：本轮未在 S2/Crossref 取得可靠题录，**删除，不得引用**。
- **Artic（arXiv:2602.12641）的场馆**：S2 只给出通用 container 名，**未确认是 SIGCOMM 正会还是 workshop**；引用前须开 ACM DL 页面核。
- **`Enhancing Mobile Immersive Streaming Experience via Deadline-Aware Scheduling and Learning-Enhanced Congestion Control`（DOI:10.1109/JIOT.2025.3621630）**：S2 题录已核，但**该文是否为真正的 "learning-augmented（带最坏情况保证）"仍需读正文确认**，本表暂按"学习增强"（learning-enhanced）引用，勿升格为 learning-augmented。
- **C-RT-45 的期刊 DOI**：本轮未取到，**只可用 arXiv:2502.20927**（表中已删除占位符）。
- **C-RT-50 的期刊 DOI**：本轮未取到，**只可用 arXiv:2511.22046**。
- **C-RT-46 的 DOI**：S2 原样为 `10.1109/ICCCN69946.2026.11662826`，表中已按 S2 原样记录，**引用前须在 IEEE Xplore 复核**。

### 12.4 本轮自查中**已发现并更正**的著录错误（提示后续会话不要沿用旧值）

| 误值 | 正确值 | 说明 |
|---|---|---|
| Scallop 的 DOI `10.1145/3718958.3750518` | **`10.1145/3718958.3750489`** | `…3750518` 实为 **NIER: Practical Neural-enhanced Low-bitrate Video Conferencing**（同会另一篇，已单列为 C-RT-80）。两篇同前缀极易混。 |
| AI-Assisted Sustainable Streaming 综述的 DOI `10.1145/3689061` | **`10.1145/3838182`** | `…3689061` 经 Crossref 解析为 *Proceedings of the 7th ACM International Workshop on Multimedia Content Analysis in Sports*，**与本文无关**。 |
| 该综述的年份"2024" | **2026（Crossref）**，S2 记 2024 | 两源不一致，以 Crossref 为准并双记。 |
| XR 流媒体综述的 DOI `10.1145/3733589` | **`10.1145/3721292`** | `…3733589` 经 Crossref 无法解析。 |
| Apple Vision Pro 论文的 DOI 沿用 `10.1145/3730567.3764434` | **`10.1145/3646547.3689006`** | 前者是 IMC 2025（C-RT-76）的 DOI；S2 把两者串号。 |

> 提示：`10.1145/3718958.*` = **ACM SIGCOMM 2025 会议论文集**；`10.1145/3744969.*` = **SIGCOMM 2025 Posters and Demos**（非正会）；`10.1145/3789240.*` = **ACM SIGCOMM 2026 会议论文集**；`10.1145/3793853.*` = **ACM MMSys 2026**；`10.1145/3712676.*` = **ACM MMSys 2025**；`10.1145/3798065.*` 与 `10.1145/3712678.*` = **NOSSDAV 2026 / 2025（workshop）**。前缀可快速判场馆，但**同一前缀内可能是不同论文**，必须逐 DOI 核。

---

## 13. 新范式归纳（近两年）与研究空白

### 13.1 近两年出现的 RTC / 低延迟传输新范式（回应任务要求 ①）

| 范式 | 代表论文 | 证据/状态 |
|---|---|---|
| **命名对象 + 中继交付（MoQ）取代流式交付** | C-RT-28 → C-RT-29/30/31/32/33/34/35 | MoQ 已"部署在生产 CDN 上"（C-RT-32 摘要原话）；随之暴露"中继不解释元数据 → 调度器语义盲"的新问题。**这是 2023–2026 最实质的交付范式切换。** |
| **跨层喂真值取代端到端试错** | C-RT-14（物理层测可用带宽）、C-RT-15（Wi-Fi 竞争窗）、C-RT-16（5G 上行调度器 + CC 双环）、C-RT-11（帧级反馈） | 四条独立证据都指向"试错式探带宽已失效"。OCC 摘要直接写现有方案的瓶颈是"reliance on trial-and-error-based mechanisms"。**SIGCOMM 2026 收 C-RT-16 → 该范式已被顶会接纳。** |
| **L4S 作为"网络层超低延迟服务"** | C-RT-21/22（RFC）、C-RT-23/24/25/26/27 | RFC 三件套（2023）+ 2024–2026 大量实证；C-RT-27 专门研究**部分部署**下的收益折损。 |
| **神经/生成编解码替代 FEC 做丢包修复** | C-RT-47（GRACE）、C-RT-48（Reparo）、C-RT-54（语义分层 + 抗错熵编码） | GRACE 摘要明确"重传不可行"、Reparo 明确"FEC 冗余度两难"；到 2026 已进入"按语义重要度分层打包"。 |
| **学习型 CC 从"打榜"退到"可部署/可公平"** | C-RT-39（Astraea）、C-RT-40（Jury）、C-RT-41（EchoCC）、C-RT-42（学习 vs 手工的系统评测） | EuroSys 2024→2025 连续两篇都在做**公平性泛化**；C-RT-42 明文写该领域"仍需大量研究…才能产出可部署方案"。 |
| **帧/对象语义可见化（应用→传输的语义通道）** | C-RT-32（MoMQ 用 MoQT Object 元数据做路径决策）、C-RT-35（丢超时就丢非关键帧）、C-RT-43（CC 感知神经编解码的丢包容忍） | 共同点是"让传输层知道哪个包重要"。 |
| **可编程数据面下沉到会议/SFU 与 FEC** | C-RT-64（Scallop，SIGCOMM'25）、C-RT-65（SFU in P4）、C-RT-53（SmartFEC on SmartNIC） | 与本工作区的在网计算/DPDK 主题直接交汇。 |
| **学习增强（learning-augmented，带最坏情况保证）** | **未找到应用于 RTC 拥塞控制的论文**；最接近的是 C-RT-44（learning-enhanced）与工作区已有的 Chen/Hajiesmaili/Sitaraman 2026（learning-augmented 360° 视频流） | 见 §13.2 ④。 |
| **语义/生成式通信（semantic communication）** | C-RT-45、C-RT-54，及备选表中的多条 | **主要是无线通信社区的问题设定（仿真、PHY 抽象）**，与端到端 RTC 系统论文评估口径不可比。做系统方向时只能作为"叙事动机"，不能作为 baseline。 |

### 13.2 研究空白 / 未解决问题（每条附支撑证据）

**① 云电脑 / 云桌面（cloud PC、remote desktop、VDI）的传输研究不是空白，但窄且偏"预测侧"（已按交叉核对修正表述）。**
证据（**已与同目录并列子方向笔记 `B-云电脑-远程桌面-远程渲染.md` 交叉核对**，本条引用其检索结论，未改动该文件）：
- **存在**一条成形的"云桌面带宽/吞吐预测"线：DeskTransfer（IEEE TMM 2025, DOI:10.1109/TMM.2025.3613109）、DeskPred（IEEE TCSVT, DOI:10.1109/TCSVT.2025.3632222）、A Novel CCA-MoE（IEEE ICCE-Taiwan 2026, DOI:10.1109/ICCE-Taiwan71481.2026.11652730），同一课题组连发三篇。
- **但是**：B 文件明确记录——`"Azure Virtual Desktop"` / `"Amazon WorkSpaces"` / `"Windows 365"` 的公开学术实测**全部为零**（OpenAlex 命中项全是 Apress 技术书章节、Zenodo/SSRN 自出版白皮书）；**RDP / HDX / PCoIP / Blast 的协议级学术测量集中在 2019–2021，2024–2026 传输/QoE 向几乎没有新论文**；开源远程桌面栈（X2Go/KDrive、Guacamole、noVNC、RustDesk）学术上几乎无人研究。
- 我的独立检索方向一致但更粗：S2 多组关键词（`cloud desktop` / `cloud PC transport latency` / `remote desktop transport`）+ arXiv `all:"screen content coding"` 命中全是**编码侧**；C-RT-08 是唯一"云桌面 + 视频传输"的直接命中，且只做编码。
→ **修正后的空白表述**：云桌面的传输研究集中在**带宽/吞吐预测**；**拥塞控制、丢包修复、协议级实测三个方向均缺**。且云桌面（文本/UI、屏幕内容、低频大幅刷新）与云游戏（连续高码率视频）负载特性完全不同，把云游戏结论直接迁移不成立。
⚠️ 受 §12.2 的 429/连接重置影响，"没找到" ≠ "不存在"，立题前须补检索。

**② 传输层对媒体语义的"可见性"刚被工程化，但缺少统一抽象。**
证据：C-RT-32（MoMQ）明确诊断为"调度器只看到字节，看不到关键帧"；C-RT-35（MoQ 超时下保关键帧）、C-RT-54（按语义重要度分层）、C-RT-43（CC 感知编解码的丢包容忍）**各自发明了一套"重要性"表达**。这四条来自不同社区（MoQ 传输 / 编码 / 学习型 CC），**互不兼容，没有共同的重要性度量或接口**。

**③ 学习型 CC 的公平性泛化与可部署性到 2026 仍未解决。**
证据：C-RT-39（EuroSys'24 Astraea）与 C-RT-40（EuroSys'25 Jury）**连续两年在同一会议做同一问题**（crowd 场景下的公平性泛化）；C-RT-41（EchoCC）还要额外加"WordBook"修正；C-RT-42 的系统评测直接写学习型 CC"in its early days"、产出可部署方案"substantial research is required"。→ 这不是"没人在做"，而是**做了两年还没解决**。

**④ 用 learning-augmented（带最坏情况保证）方法做 RTC 拥塞控制——本轮检索基本空白。**
证据：S2 `learning-augmented congestion control predictions` 查询的 12 条命中里，**无一条是 RTC 拥塞控制**（命中项为段路由、能源调度、数据中心、MPC、水基础设施等）；最接近的 C-RT-44 只是 "Learning-Enhanced"，且是否具最坏情况保证待读正文。而工作区已确认 **learning-augmented 在 360° 视频流（Chen/Hajiesmaili/Sitaraman 2026, DOI:10.1145/3793853.3795754）已有落地** → **"learning-augmented × 严格 deadline 的 RTC 传输"是一个真空白**，且工作区已有该方法的成熟文献底座（WTP-78/80/81/82/83/84/85）。

**⑤ MoQ 与 ABR / CC 的耦合仍无标准做法。**
证据：C-RT-33（MultiMoQ）明确写 MoQ "lacks robustness under bandwidth-constrained conditions"；C-RT-29 才刚做 MoQ vs LL-DASH 的测试床对比；到 **2026-06 才出现第一篇专门研究 MoQ 下 ABR 切换的论文**（备选表：arXiv:2606.26368）；C-RT-35 还在讨论"投递超时该丢什么"。→ MoQ 的 per-Object 语义与传统 ABR/CC 的时间尺度不一致，是开放问题。

**⑥ 上行（推流）方向的实证明显少于下行。**
证据：本表 80 条中，明确做**上行**的只有 C-RT-77（4G/5G 上行视频流 QoE 实测）、C-RT-12/邻域（低延迟上行带宽估计）与 C-RT-42/77 相关几条；而直播推流、云游戏输入回传、会议上行都是上行主导。**下行结论不能直接迁移到上行**（OCC 摘要也强调蜂窝上/下行波动区间都在扩大）。

**⑦ "部分部署/渐进升级"下的收益折损研究稀缺。**
证据：C-RT-27（PAM'24）专门研究 L4S **部分部署**下的性能，是少数派；C-RT-50（AutoRec）指出 CDN **多供应商市场下只能改服务端**；C-RT-79（IMC'23）指出运营商**无法改客户端**就只能从网络侧推断。→ 大量论文假设双端可改，但真实部署经常不是。

### 13.3 本子方向"必读四篇"（供后续会话快速定位）
1. **C-RT-70** Low-Latency Video Streaming: Applications, Challenges, and Trends（IEEE COMST 2026）—— 唯一的统一权威综述，其"应用域 × 延迟需求 × 瓶颈"框架可直接作为选题叙事骨架。
2. **C-RT-01** Dissecting and Streamlining the Interactive Loop of Mobile Cloud Gaming（NSDI 2025）—— 云游戏需求侧最硬实测（112–403 ms）。
3. **C-RT-32** Media-over-Multipath-QUIC / MoMQ（arXiv 2026）—— "传输层语义盲"的机制化诊断与解法，新范式代表。
4. **C-RT-15** BLADE（arXiv 2026）—— 把长尾延迟根因从传输层重新定位到 Wi-Fi MAC 层，是"瓶颈已换位置"的最强新证据。
