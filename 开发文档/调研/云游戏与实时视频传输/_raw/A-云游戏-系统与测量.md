# A-云游戏-系统与测量（raw 笔记）

> 调研日期：**2026-10-01**。子方向：**云游戏系统本体 —— 架构、延迟测量、QoE、资源调度**。
> 检索通道：Semantic Scholar Graph API（`search` + `paper/batch`）、arXiv Atom API（`id_list` 批量核验）、Crossref（DOI 核验）、Tavily。
> 引用数一律为 **S2 快照值（2026-10-01 抓取）**，仅作参考、会过时。
> 状态标记：⭐=必读 / 📌=备选 / ⚠️=需注意著录陷阱 / 🔁=经典（2010–2023 奠基）。
> **本文件与工作区 `文献索引.md` 无重叠条目**；相邻但已收录的（Sieber 2015/2016、Zhang 2021、Su 2024、Krishnan 2012、Nam 2016、Shafiq 2014、Minovski 2021、Yue 2018、Narayanan 2020 Lumos5G、Jiang 2015 DDA、Chen/Hajiesmaili/Sitaraman 2026 `DOI:10.1145/3793853.3795754`、Laoutaris 2009、Schulman 2010、Tadrous 2013、LENS `DOI:10.1145/3625468.3652170`）在此仅作背景引用，不占编号。

---

## 子方向总述

云游戏把"渲染—编码—传输—显示—输入回传"整条链路搬到远端，因此它同时是**分布式系统问题**、**实时视频编码问题**和**人因 QoE 问题**：端到端交互延迟的每一次抖动都换算成玩家可感知的操控劣化，同时还要维持 GPU 利用率、带宽成本与编码质量的三角平衡。近两年（2024–2026）本方向发生三处明显位移：

1. **测量从"实验室搭台"转向"厂商/运营商规模的真实流量"** —— NVIDIA GeForce NOW 从单点解剖（PAM'24）走到万级会话的 ISP 侧长期测量（ToN'26），并把"游戏标题 + 玩家活动阶段"等上下文引入体验度量（IMC'25）。
2. **瓶颈定位从"网络 RTT"转回"客户端与服务端图形流水线的同步"** —— NSDI'25 的交互回路解构指出 **VSync 事件本身**就是可裁的延迟大户；同时 NSDI'24 Pudica / NSDI'25 Tooth 把云游戏专用拥塞控制与细粒度 FEC 单独立题。
3. **"AI 上机"从学术 demo 变成服务端基础设施** —— 超分/神经增强（River）、感知驱动码率控制（SAIL）、注视点编码（EyeNexus）与帧生成（TailClip）都在争夺"用算力换带宽"的位置；GPU 多租户共享（Combo、Guardian）与 SoC 集群高密度托管（ATC'24 SFG）在压单位并发用户的成本。

**仍未解决的**：没有一篇论文把"网络侧可见指标"与"玩家留存/流失"建立起像普通视频那样的因果链（对照 Krishnan 2012、Nam 2016 的方法学）。云游戏 QoE 研究整体仍停留在 **MOS 预测层**，且 IMC'25 已明确指出"不同游戏不可用同一模型度量"，但跨服务的迁移学习（TNSM'24）又给出相反希望——这一矛盾尚无定论。

---

## A-1 系统架构与交互回路解构（本体系统）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A1-1 | ⭐ | Dissecting and Streamlining the Interactive Loop of Mobile Cloud Gaming（LoopTailor） | Yang Li（李扬） | 2025 / **USENIX NSDI** | [USENIX](https://www.usenix.org/conference/nsdi25/presentation/li-yang)（无 DOI/arXiv） | 11 | 逐段解剖移动云游戏交互回路，发现 **VSync 事件**是延迟大户；提出端到端 VSync 调节器，解耦游戏渲染与冗长的云端图形流水线、让云端渲染直接与客户端协同，交互延迟稳定压到 **100 ms 以下**。 | 本子方向**最重要的"本体解构"论文**。把"延迟从哪来"从网络层拉回图形流水线同步层，是近两年最硬的系统贡献。 |
| A1-2 | ⭐ | High-density Mobile Cloud Gaming on Edge SoC Clusters（SFG） | Li Zhang（张力） | 2024 / **USENIX ATC** | [USENIX](https://www.usenix.org/conference/atc24/presentation/zhang-li-gaming)（无 DOI） | 6 | 首个在**手机 SoC 集群**上做高密度云游戏的系统；两项技术延长旧 SoC 集群寿命，使其能服务单颗 SoC 因 GPU 资源不足而跑不动的新游戏。 | "用退役手机 SoC 当边缘渲染节点"路线的最强系统证据。**成本侧核心对照**；其期刊延伸为 IEEE TMC 2026《Prototyping and Analyzing Mobile SoC Clusters as Modern Edge Servers》（DOI:10.1109/TMC.2026.3657619，Crossref 已核）。 |
| A1-3 | ⭐ | Stimpack: An Adaptive Rendering Optimization System for Scalable Cloud Gaming | Jin Heo | 2024-12 / arXiv → **NSDI 2026** | arXiv:2412.19446 · DBLP:conf/nsdi/HeoWBG26 | 2 | 面向可扩展云游戏的自适应渲染优化系统（S2 记入 NSDI'26）。 | 与 A1-1 直接同赛道：都在服务端渲染侧做自适应。**入场前必读的最新一篇**。 |
| A1-4 | 📌 | VIGOR: Reviving Cloud Gaming Sessions | Zhaoyuan He | 2024 / **PACMNET** | DOI:10.1145/3696403（Crossref 已核） | 4 | 云游戏会话中断后的恢复/续播。 | 唯一正面处理"会话被打断怎么办"的系统论文；可与工作区 WTP 专题的"中断→浪费流量"因果链**交叉引用**。 |
| A1-5 | 📌 | Sudoku: Scalable High-Density Cloud Rendering Multi-Client Architecture | Yun Wang | 2025 / **IEEE TSC** | DOI:10.1109/TSC.2025.3607449（Crossref 已核） | 0 | 高密度云渲染的多客户端架构（十人作者，工业侧痕迹明显）。 | "一块 GPU 喂多个串流客户"的架构侧工业方案；与 A-7 的 GPU 共享条目互补。 |

---

## A-2 厂商/运营商规模实测（本子方向重点）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A2-1 | ⭐⭐ | Network Anatomy and Real-Time Measurement of Nvidia GeForce NOW Cloud Gaming | Minzhao Lyu | 2024 / **PAM**（CCF-B） | arXiv:2401.06366 · DOI:10.1007/978-3-031-56249-5_3（arXiv 已核标题） | 19 | 在 ISP 网络内**实时识别 GeForce NOW 会话**并度量其用户体验；量化浏览器 vs 客户端、有线 vs 无线的性能劣化差异。 | **本方向"厂商规模实测"的基准篇**：给出可复用的会话识别方法学 + 上下文因子。A2-2/A2-3 均为其续作。 |
| A2-2 | ⭐ | A Large-Scale Network Measurement Study of NVIDIA GeForce NOW Cloud Gaming in the Wild | Minzhao Lyu; Vijay Sivaraman | 2026 / **IEEE/ACM ToN** | DOI:10.1109/TON.2025.3623962（Crossref 已核） | 2 | 上述 PAM'24 工作的**大规模扩展**：运营商视角的"野外"长期测量。 | 目前可核实的**最大规模 NVIDIA 云游戏网络测量**；投 ToN/TMC 时的规模标尺。 |
| A2-3 | ⭐ | Games Are Not Equal: Classifying Cloud Gaming Contexts for Effective User Experience Measurement | Yifan Wang | 2025 / **ACM IMC** | arXiv:2509.19669 · DOI:10.1145/3730567.3764455（两者均已核） | 4 | 仅靠网络流量即可实时估计云游戏体验，且必须**按"游戏标题 + 玩家活动阶段"分场景**建模；方法部署在承载 NVIDIA 云游戏服务器的 ISP 内。 | 直指"云游戏体验不可用一个通用模型测"这一方法论痛点。**做任何云游戏 QoE 预测前必读的负面约束**。 |
| A2-4 | ⭐ | Evolving Mobile Cloud Gaming with 5G Standalone Network Telemetry | Haoran Wan; Kyle Jamieson | 2024-02 / arXiv | arXiv:2402.04454（id_list 已核） | 6 | 用 **5G SA 网络遥测**（而非端侧推断）支撑移动云游戏自适应。 | 罕见的"5G 运营商遥测 × 云游戏"实测；与 A2-1 的被动 ISP 测量互补（主动遥测路线）。 |
| A2-5 | 📌 | Characterizing the Network Traffic of Virtual Reality Cloud Gaming Applications | V. R. Oliveira | 2026 / **WONS** | DOI:10.23919/WONS68803.2026.11501840（Crossref 已核） | 0 | VR 云游戏的流量刻画（包大小/码率/突发模式）。 | VR 子类最新流量底表；与 A-5 的注视点编码条目配合看"VR 流量的特殊性"。 |
| A2-6 | 🔁 | Dissecting Cloud Gaming Performance with DECAF | Hassan Iqbal | 2021 **POMACS** / 2022 SIGMETRICS | **期刊全文** DOI:10.1145/3491043（POMACS 2021-12-14）· **会议摘录版** DOI:10.1145/3489048.3522628（Crossref 证实为 "Abstract Proceedings of the 2022 ACM SIGMETRICS/IFIP PERFORMANCE"） | 12（期刊版）/ 17（会议版） | 提出 **DECAF** 框架，沿流水线逐段归因云游戏性能瓶颈。 | **经典**：所有后续"延迟分解"工作的共同参照物，A3-1 与 A1-1 都建立在这一分解思路上。⚠️ **引全文请用 POMACS 期刊版 DOI**，SIGMETRICS'22 那条只是摘要版。另有两篇更早的多平台网络分析（Di Domenico 等 2020，《A network analysis on cloud gaming: Stadia, GeForce Now and PSNow》，arXiv:2012.06774，S2 快照 **82** 引用）——**经典**，但对象已过时（Stadia 已关停、PS Now 已并入 PS Plus），且是目前唯一同时覆盖这三家的文献。 |

---

## A-3 延迟分解 / 端到端延迟预测与显示调度

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A3-1 | ⭐ | Real-time latency prediction for cloud gaming applications（CLAAP） | Doriana Monaco | 2025 / **Computer Networks**（CCF-B） | DOI:10.1016/j.comnet.2025.111235（Crossref 已核） | 13 | 用 ML 模型**实时预测**云游戏延迟并预测未来网络演化，从而在恶劣网络下做容忍性决策。 | **"延迟可预测"命题在云游戏域的当下答案**；与工作区既有的链路吞吐预测线（Minovski / Yue / Narayanan）同源，但预测对象是端到端交互延迟。 |
| A3-2 | ⭐ | Perception-Aware Frame Display Scheduling for Low-Latency Cloud Gaming（PASync） | Houde Qian | 2026 / **NOSSDAV**（ACM SIGMM **Workshop**，勿记为正会） | DOI:10.1145/3798065.3798067（Crossref 已核，container = 36th Workshop on NOSSDAV） | 0 | 利用"感知最大帧率 pFR"——超过 pFR 的额外帧不再被感知为更流畅——设计帧调度算法，在**严格零撕裂**约束下最小化缓冲延迟。 | 把"帧调度"从工程技巧提升为**感知约束下的优化问题**。端侧显示/帧节奏优化的直接起点。 |
| A3-3 | ⭐ | Trinity: Exploiting Latency Sensitivity to Improve Quality of Experience on Cloud VR Gaming | Lingzhi Zhao | 2026 / **ACM MMSys** | DOI:10.1145/3793853.3795744（Crossref 已核） | 0 | 观察到玩家交互的**延迟敏感度异质**（不同动作要求不同），据此差异化处理，使云 VR 体验接近本地串流。 | MMSys'26 云 VR 代表工作；与 A2-5 流量刻画、A-5 注视点编码构成"云 VR 三件套"。 |
| A3-4 | 🔁 | Timely cloud gaming | R. Yates | 2017 / **IEEE INFOCOM**（CCF-A） | DOI:10.1109/INFOCOM.2017.8057197 | 60 | 把云游戏帧投递形式化为"及时性（timeliness）"问题——过期帧无用。 | **经典**：云游戏与时延敏感传输理论的关键桥接文献；与工作区 WTP 中的 D3"better never than late"同家族。 |

---

## A-4 QoE 建模 / 主观与客观质量评价

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A4-1 | ⭐ | Adaptive Cloud VR Gaming Optimized by Gamer QoE Models | Kuan-Yu Lee | 2024/2025 / **ACM TOMM** | DOI:10.1145/3680551（Crossref 已核，published 2025） | 12 | 搭建可仿真多种网络条件的云 VR 测试床，建**首个云 VR 游戏 QoE 模型**，并用它动态调编码参数。 | 云 VR QoE 建模的**权威一手工作**；把 QoE 模型闭环回编码控制，是本子方向"QoE 不只是打分"的范例。 |
| A4-2 | ⭐ | QoE Estimation Across Different Cloud Gaming Services Using Transfer Learning | Marcos Carvalho | 2024 / **IEEE TNSM**（CCF-C） | DOI:10.1109/TNSM.2024.3451300（Crossref 已核） | 6 | 用**迁移学习**在**不同云游戏服务之间**迁移 QoE 估计模型。 | 正面回答"QoE 模型能否跨平台复用"；与 A2-3"游戏之间不等价"形成互补的两难。 |
| A4-3 | ⭐ | Study of Subjective and Objective Quality Assessment of Mobile Cloud Gaming Videos | Avinab Saha | 2023 / **IEEE TIP** | arXiv:2305.17260 · DOI:10.1109/TIP.2023.3281170（均核） | 17 | 移动云游戏视频的**主客观质量评价数据集与方法**（含主观实验与客观指标对比）。 | 云游戏视频质量评价的**数据集地基**；A4-4/A4-5 建在其上或与之对照。 |
| A4-4 | 🔁 | GAMIVAL: Video Quality Prediction on Mobile Cloud Gaming Content | Yu-Chih Chen | 2023 / **IEEE SPL** | arXiv:2305.02422 · DOI:10.1109/LSP.2023.3255011（均核） | 14 | 面向移动云游戏内容的无参考视频质量预测模型。 | **经典**（本方向客观质量预测的标准基线之一）。 |
| A4-5 | ⭐ | GameScope: A Multi-Attribute, Multi-Codec Benchmark Dataset for Gaming Video Quality Assessment | Rajesh Sureddi | 2026 / arXiv（S2 记 venue = ICIP 系会议） | arXiv:2605.01272（id_list 已核） | 0 | **多属性、多编解码器**的游戏视频质量评价基准数据集（H.264/H.265/AV1 等）。 | **最新数据集**：直接对位"AV1 进云游戏"这一热点，是 2026 年做编码侧质量对比的现成弹药。 |
| A4-6 | 🔁 | Modeling Gaming QoE: Towards the Impact of Frame Rate and Bit Rate on Cloud Gaming | Saman Zadtootaghaj | 2018 / **QoMEX** | DOI:10.1109/QoMEX.2018.8463416 | 51 | 建立帧率与码率对云游戏 QoE 影响的定量模型。 | **经典**：后续所有"帧率 vs 码率"权衡论文的引用源头；A3-2 的 pFR 概念正是对它的延伸。 |
| A4-7 | ⭐ | Survey on Quality of Experience Evaluation for Cloud-Based Interactive Applications | Jesus Arellano-Uson | 2024 / **Applied Sciences**（MDPI，非 CCF） | DOI:10.3390/app14051987 | 11 | 云交互应用（含云游戏）QoE 评测技术的系统性综述：输入指标 / 策略 / 评测架构的分类学。 | 本轮找到的**最对口 QoE 综述**；刊物体量轻，只作方法论索引，不作权威背书。 |

---

## A-5 编码 / 码率控制 / AI 增强（AV1、超分、帧生成、注视点）—— **近两年最热**

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A5-1 | ⭐ | SAIL: Perceptual Quality-Aware Rate Control for Cloud Gaming | Houde Qian | 2026-07 / arXiv | arXiv:2607.11231（id_list 已核） | 0 | 云游戏的**感知质量感知码率控制**（11 作者，工业界参与痕迹明显）。 | 该子方向**最新一篇**（2026-07），与 A3-2 同为一作；代表"码率控制 × 感知模型"这一 2026 主线。 |
| A5-2 | ⭐ | Content Adaptive Encoding For Interactive Game Streaming | Shakarim Soltanayev | 2025-11 / arXiv（S2 记 venue = **PCS**） | arXiv:2511.22327 | 1 | 面向交互式游戏串流的**内容自适应编码**。 | 与 A5-1 并列为 2025 下半年编码侧最新两篇；S2 记其 venue 为 Picture Coding Symposium，**具体届次待核实**。 |
| A5-3 | ⭐ | Codec Compression Efficiency Evaluation for Ultra Low–Latency Cloud Gaming Applications | Nabajeet Barman | 2024 / **QoMEX** | DOI:10.1109/QoMEX61742.2024.10598276（Crossref 已核） | 2 | 在**超低延迟**配置下横向评测各编解码器的压缩效率。 | "云游戏该用哪个 codec"的**唯一近期直接评测**；回答 AV1 是否值得的关键一手证据。 |
| A5-4 | 📌 | Evaluation of GPU Video Encoder for Low-Latency Real-Time 4K UHD Encoding | Kasidis Arunruangsirilert | 2025-11 / **VCIP** | arXiv:2511.18688 · DOI:10.1109/VCIP67698.2025.11396901 | 3 | 评测 GPU 硬件编码器（NVENC 类）在低延迟实时 **4K UHD** 下的表现。 | 唯一直接刻画"GPU 硬件编码器在云游戏时延预算内能否扛 4K"的论文；与 A5-3 互补（一个比 codec、一个比硬件实现）。 |
| A5-5 | ⭐ | Real-Time Neural-Enhancement for Online Cloud Gaming（River） | Shan Jiang | 2025-01 / arXiv | arXiv:2501.06880（id_list 已核） | 3 | 观察到云游戏视频段特征**高度重复冗余**，据此复用微调过的超分模型，把微调延迟从分钟级压到毫秒级查询延迟。 | **AI 超分上服务端**的代表作；"重复视频段 → 复用神经网络"这一观察可迁移，属巧思型贡献。 |
| A5-6 | 📌 | Compressed Domain Prior-Guided Video Super-Resolution for Cloud Gaming Content（CPGSR） | Qizhe Wang | 2025 / **DCC** | arXiv:2501.01773 · DOI:10.1109/DCC62719.2025.00016 | 3 | 压缩域先验引导的云游戏超分网络（轻量 + 分区聚焦频率损失保高频）。 | 与 A5-5 同赛道（超分换带宽）但走"轻量 + 压缩域先验"路线；可作对照实现。 |
| A5-7 | 📌 | Decoupling Video Upscaling from Rendering for Cloud Gaming | Deniz Ugur | 2025 / **ACM MMSys** | DOI:10.1145/3712676.3714439（Crossref 已核） | 2 | 把**超分器从游戏渲染器解耦**，使不同超分器不经改游戏源码即可接入。 | 解决"超分方案难以落地部署"的工程瓶颈；与 A5-5 构成"算法 vs 可部署性"的一对。 |
| A5-8 | 📌 | TailClip: Mitigating Tail Latency in Cloud Gaming via Smart Video Frame Generation | Qianyun Gong | 2024 / **IEEE ICME** | DOI:10.1109/ICME57554.2024.10687836 | 0 | 用**智能帧生成**兜住云游戏尾延迟（丢帧时生成替代帧而非卡顿）。 | **"帧生成（frame generation）"进云游戏**的直接代表；与 A3-2 帧调度构成互补手段对。 |
| A5-9 | 🔁 | FovOptix: Human Vision-Compatible Video Encoding and Adaptive Streaming in VR Cloud Gaming | Ahmad Alhilal | 2024 / **ACM MMSys** | DOI:10.1145/3625468.3647612（Crossref 已核；container 显示异常为 "…MMSys 2024 on ZZZ"，以 MMSys'24 为准） | 19 | 人眼兼容的注视点（foveated）编码与自适应串流，用于 VR 云游戏。 | **注视点编码**在云 VR 的标杆工作（该子类最高引用）；A5-10 是其 2025 年续作。 |
| A5-10 | ⭐ | EyeNexus: Adaptive Gaze-Driven Quality and Bitrate Streaming for Seamless VR Cloud Gaming Experiences | Ze Wu | 2025 / **PACMNET** | arXiv:2509.11807 · DOI:10.1145/3768989（均核） | 7 | 实时注视驱动的空间压缩 + 注视驱动编码，foveation 区域随带宽与注视动态调整，保证 FVE 质量梯度平滑。 | **2025 年注视点 / 云 VR 的最新系统**（与 A5-9 同组延续）；代表"眼球追踪 + 自适应码率"合流。 |

---

## A-6 传输与网络：拥塞控制、FEC、多路径

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A6-1 | ⭐ | Pudica: Toward Near-Zero Queuing Delay in Congestion Control for Cloud Gaming | Shibo Wang | 2024 / **USENIX NSDI** | [USENIX](https://www.usenix.org/conference/nsdi24/presentation/wang-shibo)（无 DOI/arXiv） | 32 | 面向云游戏的端到端拥塞控制：追求**近零排队延迟 + 高链路利用率**，兼顾跨流公平，并配整体码率调整策略。 | **云游戏专用拥塞控制的头号工作**（32 引用，本子方向最高之一）；与工作区既有拥塞控制线（DCQCN/HPCC/Swift）场景完全不同，是其"实时交互"分支。 |
| A6-2 | ⭐ | Tooth: Toward Optimal Balance of Video QoE and Redundancy Cost by Fine-Grained FEC in Cloud Gaming Streaming | Congkai An | 2025 / **USENIX NSDI** | [USENIX](https://www.usenix.org/conference/nsdi25/presentation/an)（无 DOI/arXiv） | 20 | **细粒度 FEC** 在云游戏串流中平衡视频 QoE 与冗余开销（11 作者，含运营商侧作者）。 | **丢包恢复**在云游戏域的最新答案；与工作区 WTP 的"冗余传输"线互为镜像——那边关心省字节，这边主动花字节买 QoE。 |
| A6-3 | ⭐ | AUGUR: Practical Mobile Multipath Transport Service for Low Tail Latency in Real-Time Streaming | Yuhan Zhou | 2024 / **USENIX NSDI** | [USENIX](https://www.usenix.org/conference/nsdi24/presentation/zhou-yuhan) | 26 | 多路径传输服务降低移动实时串流的**长尾延迟与卡顿率**；用状态概率模型 + ILP 决定重传时机与路径选择。 | 多路径 + 重传决策的组合；与 A6-2 同为"用冗余/多路买尾延迟"路线。作者组与 A3-2、A6-2 有重叠（北大/字节系）。 |
| A6-4 | 📌 | Improving Cloud Gaming Traffic QoS: A Comparison Between Class-Based Queuing Policy and L4S | Philippe Graff | 2024 / **TMA** | DOI:10.23919/TMA62044.2024.10558920（Crossref 已核） | 10 | 对比 **CBQ（基于类的队列）** 与 **L4S** 两种网络层方案对云游戏流量的 QoS 保护效果；两者都能保住 QoS 但运维约束不同。 | **网络运营商视角**的排队策略评测；与工作区 WTP 的 L4S 相关条目可交叉引用。 |
| A6-5 | ⭐ | Experimental Evaluation of Interactive Edge/Cloud Virtual Reality Gaming over Wi-Fi using Unity Render Streaming | Miguel Casasnovas | 2024 / **Computer Communications**（CCF-C） | arXiv:2402.00540 · DOI:10.1016/j.comcom.2024.08.001（均已核） | 25 | 用 Unity Render Streaming 在 Wi-Fi 上实测边缘/云 VR 游戏，结合真实数据与 Wi-Fi 仿真评估 VR 串流的 QoS 适配性。 | **"云/边缘 VR 游戏 + Wi-Fi"的完整实测**（引用 25，本子方向高）；把 Wi-Fi 空口与 VR 流量特性连起来，是 A-8 现实接入条件的关键证据。 |
| A6-6 | 🔁 | Nebula: Reliable Low-latency Video Transmission for Mobile Cloud Gaming | Ahmad Alhilal | 2022 / **The Web Conference (WWW)** | arXiv:2201.07738 · DOI:10.1145/3485447.3512276 | 44 | 面向移动云游戏的可靠低延迟视频传输（协议/冗余设计）。 | **经典**：A5-9、A5-10 同一作者组的奠基工作，读其系列必先读本篇。注：本文另一篇 VR 云游戏拥塞控制实测（GCC vs NADA，接入 ALVR）发表于 **ACM Multimedia 2025**（DOI:10.1145/3746027.3755439，S2 6 引用），亦由 Alhilal 一作。 |

---

## A-7 资源调度 / GPU 共享 / 容量规划（基础设施侧）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A7-1 | ⭐ | Maximizing the Utilization of GPUs Used by Cloud Gaming through Adaptive Co-location with Combo | Binghao Chen | 2023 / **ACM SoCC** | DOI:10.1145/3620678.3624660（Crossref 已核，GOLD 开放获取） | 7 | 两级空间共享（intra-SM + inter-SM），在保证渲染帧 QoS 前提下提升 GPU 吞吐；按运行时渲染负载自适应共置。 | **"多租户渲染共享 GPU"的核心系统论文**且开放获取；A7-4 的容器化路线与它正面对比。 |
| A7-2 | 📌 | Guardian: Safe GPU Sharing in Multi-Tenant Environments | Manos Pavlidakis | 2024 / **ACM Middleware** | arXiv:2401.09290 · DOI:10.1145/3652892.3700768（均核） | 23 | PTX 层边界检查实现 GPU 内存隔离，支持动态 GPU 空间共享，对 Caffe/PyTorch 透明。 | **不是云游戏专文**，但"多租户 GPU 共享的安全性"是云游戏服务商的实际前置约束；与 A7-1（性能侧）互补。 |
| A7-3 | ⭐ | Personalized Cloud Gaming: Multi-Objective Optimization for Resource Utilization and Video Encoding | Jingjing Zhang | 2025 / **IEEE TCC**（CCF-B） | DOI:10.1109/TCC.2025.3571095（Crossref 已核） | 2 | 把"资源利用率"与"视频编码"放在一起做多目标优化（个性化云游戏）。 | **"调度与编码联合优化"**这一交叉点的最新论文；与 A-5（只管编码）和 A7-1（只管 GPU）都不同，是少见的联立视角。 |
| A7-4 | 📌 | Towards an Efficient Containerized Cloud Gaming Platform | Adrien Gegout | 2025 / **IEEE IPDPSW**（**workshop 卷**） | DOI:10.1109/IPDPSW66978.2025.00018（openAccess GREEN） | 1 | 用**容器**替代 Windows VM 跑游戏，并提出面向游戏容器的 GPU 共享方案，能耗最多降 10.6% 且不影响体验。 | 容器化路线唯一近期论文；与 A7-1 的"裸机空间共享"是两种成本压缩哲学的对照。 |
| A7-5 | ⭐ | Enhancing Cloud Gaming Experience through Optimized Virtual Machine Placement: A Comprehensive Review | Sawsan Ali Hamid | 2024 / **JNSM** | DOI:10.1007/s10922-024-09864-2（Crossref 已核） | 6 | 云游戏 **VM 放置（VMP）** 问题的综述：架构、优化方法学、服务模式。 | **本轮找到的最对口"资源调度"综述**（Springer 二线刊）；A7-1 / A7-3 都可放进它的分类框架。 |
| A7-6 | 📌 | Deep-Reinforcement-Learning-Based Resource Allocation for Cloud Gaming via Edge Computing | Xiaoheng Deng | 2023 / **IEEE IoT-J** | DOI:10.1109/JIOT.2022.3222210 | 40 | 用 DRL 做边缘云游戏的资源分配。 | 引用 40 说明"DRL 调云游戏资源"这条线**极拥挤**；立题时须当红海对待。同类还有 Iryanto Jaya 等（2024，Multimedia Tools and Applications，DOI:10.1007/s11042-024-18337-2，3 引用，目标函数为成本）。 |
| A7-7 | 🔁 | ShareRender: Bypassing GPU Virtualization to Enable Fine-grained Resource Sharing for Cloud Gaming | Wei Zhang | 2017 / **ACM Multimedia** | DOI:10.1145/3123266.3123306（Crossref 已核；Crossref 题名被截写为 "ShareRender"，全名以 S2/DBLP 为准） | 19 | **绕过 GPU 虚拟化**做细粒度资源分享（在 GPU 内加拦截层）。 | **经典**：A7-1 Combo（2023）与 A7-4（2025）的直系祖先，证明"绕过 hypervisor 层"思路已有近十年积累。 |
| A7-8 | 🔁 | Delay-Aware Resource Provisioning for Cost-Efficient Cloud Gaming | Mohaddeseh Basiri | 2018 / **IEEE TCSVT** | DOI:10.1109/TCSVT.2016.2632121 | 31 | 延迟感知的资源供给，用于成本高效的云游戏。 | **经典**：把"延迟约束"写进成本优化模型的早期范式；A7-3 / A7-6 的目标函数都可追溯到这里。 |

---

## A-8 边缘 / 云 VR / 云 XR 与网络辅助服务

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A8-1 | 📌 | VR Cloud Gaming UX: Exploring the Impact of Network Quality on Emotion, Presence, Game Experience and Cybersickness | Maximilian Warsinke | 2024 / **ISMAR-Adjunct**（**workshop 卷**） | arXiv:2408.12238 · DOI:10.1109/ISMAR-Adjunct64951.2024.00166 | 5 | 主观实验：网络质量如何影响云 VR 的情绪、临场感、游戏体验与晕动症。 | 把云游戏 QoE 从 MOS 扩展到**情绪/临场感/眩晕**等维度；是做"QoE 之外的玩家后果"时唯一近期主观数据源。 |
| A8-2 | 📌 | Evaluating Cloud VR Gaming Experience over LEO Satellite and 5G mmWave Networks | Ei Kyi Phyu Khin | 2025 / **IEEE ICMEW**（**workshop 卷**） | DOI:10.1109/ICMEW68306.2025.11152037（Crossref 已核） | 1 | 在 **LEO 卫星**与 **5G mmWave** 两类极端接入下评估云 VR 游戏体验。 | 接入条件的极端两端；与 A6-5（Wi-Fi）合并可拼出"云 VR 接入全景"。工作区已有 LENS（LEO 测量数据集，MMSys'24，DOI:10.1145/3625468.3652170）可作 LEO 侧补充。 |
| A8-3 | 📌 | Toward Scalable VR-Cloud Gaming: An Attention-aware Adaptive Resource Allocation Framework for 6G Networks | Gabriel Almeida | 2025-12 arXiv / **Computer Networks**（S2/DBLP 记 2026） | arXiv:2512.11667 · DBLP:journals/cn/AlmeidaENKC26 | 0 | 6G 下可扩展、QoE 感知的多阶段优化框架；引入基于视觉注意力（玩家注视虚拟物体）的用户中心 QoE 模型，指导分辨率与帧率选择。 | "注意力/QoE → 资源分配"的最新一篇；与 A3-3 Trinity（延迟敏感度异质）是同一思路的两个实例。**arXiv 记 2025 / DBLP 记 2026，引用时以最终期刊版为准**。 |
| A8-4 | 📌 | Optimizing Edge Gaming Slices through an Enhanced User Plane Function and Analytics in Beyond-5G Networks | Bruno Marques da Silva | 2025-07 / arXiv（亦见 WPEIF'25） | arXiv:2507.17843 · DOI:10.5753/wpeif.2025.8714 | 1 | 打通 **NWDAF（网络数据分析功能）与 UPF 闭环**，估计用户延迟、使 5G 控制面具备延迟感知能力，用于游戏切片。 | **运营商 MEC/切片侧的近期试验**；注意其会议 venue 为巴西本地 workshop，学术分量有限，只作 5G 试验参考。 |

---

## A-9 综述 / 数据集 / 实验工具（含著录陷阱）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A9-1 | ⭐ | Low-Latency Video Streaming: Applications, Challenges, and Trends | Xun Tang | 2026 / **IEEE COMST**（CCF-A 综述刊） | DOI:10.1109/COMST.2026.3689266（Crossref 已核） | 4 | 低延迟视频串流的统一综述：应用、挑战、趋势（8 作者，含 G.-M. Muntean）。 | **本轮找到分量最重的综述**。云游戏是其应用场景之一；**入场前应整篇读完**。 |
| A9-2 | ⭐ | CGReplay: Capture and Replay of Cloud Gaming Traffic for QoE/QoS Assessment | Alireza Shirmarz | 2025 / **IEEE NetSoft** | arXiv:2505.11973 · DOI:10.1109/NetSoft64993.2025.11080563（均核） | 1 | 按序同步地**捕获并回放**玩家指令与其对应视频帧，保证可复现性，从而在不同网络条件下做 QoE/QoS 评估。 | **实验方法学工具**：解决"云游戏实验不可复现"这一老大难；做本方向系统实验时应优先采用/对比。 |
| A9-3 | ⚠️ | CGSynth: Cloud Gaming Synthesizer | Alireza Shirmarz | 2025 / **ACM SIGCOMM 2025 Posters and Demos**（**非正会！**） | DOI:10.1145/3744969.3748445（Crossref 已**确证** container = SIGCOMM 2025 Posters and Demos） | 1 | 生成可配置的合成云游戏流量，并内置 QoE 评估模块验证合成流量的视频质量与响应性。 | **重要陷阱**：S2 把 venue 记成 "Conference on Applications, Technologies, Architectures, and Protocols for Computer Communication"（≈SIGCOMM 正会），**这是错的**。引用时**必须写 "SIGCOMM 2025 Posters and Demos 短文"**。功能上是 A9-2 的姊妹工具。 |
| A9-4 | 📌 | Video Streaming and Cloud Gaming Services Over 4G and 5G: A Complete Network and Service Metrics Dataset | César Baena | 2023 / **IEEE Communications Magazine** | DOI:10.1109/MCOM.005.2200719（Crossref 已核） | 19 | 4G/5G 下视频串流与云游戏的**网络 + 服务指标数据集**（西班牙运营商实测）。 | 公开数据集（引用 19）；做 4G/5G 云游戏对比时的现成数据。与工作区既有 Lumos5G 属同一类"运营商实测数据集"。 |
| A9-5 | 🔁 | CGD: a cloud gaming dataset with gameplay video and network recordings | Iva Slivar | 2022 / **ACM MMSys** | DOI:10.1145/3524273.3532898（Crossref 已核） | 5 | 公开数据集：云游戏**游玩视频 + 网络记录**配对。 | **经典数据集**；A4-3/A4-4/A4-5 类质量评价工作的常见数据源。 |
| A9-6 | 📌 | A Cross-Perspective Annotated Dataset for Dynamic Object-Level Attention Modeling in Cloud Gaming | Hongqin Lei | 2025-08 / arXiv | arXiv:2508.06077（id_list 已核） | 1 | 用 GTA V 游玩片段标注玩家关注对象，识别出玩家游戏内速度、物体大小、物体速度为三大因素。 | 支撑"注意力/显著区域驱动云游戏编码"（A5-9/A5-10/A8-3）的数据集；注意 arXiv 分类标为 cs.DB，实际内容属多媒体。 |

---

## 近两年最热的关键词（依本轮检索命中密度与引用速度）

1. **感知驱动的码率/质量控制**（A5-1 SAIL、A3-2 PASync、A4-1、A8-3）——"感知"从评测指标变成控制器的输入；2026 年最密集。
2. **AI 超分 / 神经增强换带宽**（A5-5 River、A5-6 CPGSR、A5-7 解耦）——焦点已从"能不能超分"转到"能不能部署 / 复用模型"。
3. **注视点 / 眼动驱动编码**（A5-9 FovOptix、A5-10 EyeNexus、A9-6 注意力数据集）——云 VR 专属且持续走高。
4. **帧生成 / 帧调度 / 播放缓冲**（A5-8 TailClip、A3-2 PASync）——"帧节奏"成为独立可优化对象。
5. **厂商规模真实测量与上下文化体验度量**（A2-1/A2-2 GeForce NOW、A2-3 Games Are Not Equal、A2-4 5G SA 遥测）——从实验室转真实流量，且强调"上下文依赖"。
6. **云游戏专用拥塞控制与细粒度 FEC**（A6-1 Pudica、A6-2 Tooth、A6-3 AUGUR）——2024 起连续两年在顶会出现。
7. **AV1 / GPU 硬件编码器评测**（A5-3 Barman、A5-4 4K UHD、A4-5 GameScope 多 codec）——直接回应 AV1 进云游戏。
8. **GPU 多租户共享与容器化降本**（A7-1 Combo、A7-2 Guardian、A7-4 容器化、A1-5 Sudoku）——成本侧主线，2026 仍在增密。
9. **边缘 SoC 集群与 6G 切片闭环**（A1-2 SFG、A8-3、A8-4）——"边缘 MEC 云游戏试验"的当代形态已从 VM/容器移到 **SoC 集群**与 **NWDAF/UPF 闭环**。

---

## 检索局限

**（1）限流与工具问题**
- **Semantic Scholar Graph API 反复 HTTP 429**（带 API key 亦然）。为绕开改为带退避重试的 `curl`；`cloud gaming capacity planning provisioning`、`cloud gaming AV1 low latency video encoding`、`cloud gaming 2026` 三条查询**首轮失败，重试后才成功**。
- **WebSearch 工具未使用**（本环境常 403）。Tavily 对 "cloud gaming survey" 的检索**返回几乎全是市场研究报告**（BCG《Video Gaming Report 2026》、market.us、Grand View Research、Market Research Future 等），**无学术综述**；故综述条目仅由 S2 + arXiv 提供。
- 兜底提醒：**"没找到"≠"不存在"**。

**（2）真实检索空白（零命中，但受上述限流影响，建议在无限制环境复核）**
- **云游戏 QoE → 玩家留存/流失**：`cloud gaming player engagement / retention` 在 S2 与 arXiv 均**零命中云游戏专文**（S2 返回的全是手游抽卡留存、电竞营销、行为经济学）。普通视频侧有 Krishnan 2012 / Nam 2016 建立的"画质→放弃"因果链，**云游戏侧没有对应工作**。
- **netcode / lag compensation**：只找到 *Formalizing Rollback Netcodes*（OPODIS 2025，形式化分布式算法视角）与 *Advanced Latency Compensation Techniques*（IEEE I2CT 2024，低质量），**没有可核实的联网游戏 netcode 系统实测论文**。
- **中国国内云游戏平台实测**：腾讯 START、网易云游戏、咪咕等，S2/arXiv 多组关键词 **0 命中**。
- **Xbox Cloud Gaming / Amazon Luna / PlayStation Now 的 2024–2026 独立学术实测**：**均未检索到**。厂商侧目前只有 NVIDIA 有系列实测（A2-1/A2-2）；唯一同时覆盖三家的可用文献是 2020 年的 arXiv:2012.06774（已过时，见 A2-6 行内注）。
- **"云游戏成本"**（纯成本命题）：被通用云计算 FinOps 论文淹没，无云游戏专文。

**（3）只到题录级 / 摘要级的条目（正文未取得，引用前请自行复核）**
A1-3 Stimpack（仅 arXiv 摘要 + DBLP 场馆）、A2-5 WONS'26、A4-3 之外的 QoMEX'25 条目、A5-2（venue = PCS 由 S2 给出，**具体届次未核实**）、A7-4 IPDPSW'25、A8-2 ICMEW'25、A8-4 WPEIF'25。

**（4）场馆 / 著录陷阱（均已核实并更正）**
- **CGSynth（A9-3）**：S2 记为正会 SIGCOMM，Crossref 实为 **SIGCOMM 2025 Posters and Demos**。
- **PASync（A3-2）**：Crossref container = "36th Workshop on NOSSDAD"——**NOSSDAV 是 workshop，不是正会**。
- **A7-4（IPDPSW）**、**A8-1（ISMAR-Adjunct）**、**A8-2（ICMEW）**、**A8-4（WPEIF）** 均为 **workshop / adjunct 卷**。
- **A5-9 FovOptix**：Crossref container-title 异常地写作 "…MMSys 2024 on ZZZ"，实为 **MMSys 2024**。
- **A8-3**：arXiv 记 2025-12，DBLP 记 Computer Networks 2026，**年份以最终期刊版为准**。
- **A2-6**：DECAF 有 POMACS'21 期刊版与 SIGMETRICS'22 会议版两个 DOI，勿混用。

**（5）有一篇被主动排除**
Hai Huang《Enhancing video quality and reducing network latency in cloud gaming: a literature review》（2025，SPIE 会议论文集，DOI:10.1117/12.3077777，单作者，0 引用）：**摘要措辞像自述实验而非综述**，学术价值存疑，**仅登记不建议引用**。

**（6）本轮核验方式（可复查）**
- arXiv `id_list` 批量核验 **20 个 arXiv ID**（标题逐字比对，**全部命中**）。
- Crossref 逐条核验 **30 个 DOI**（container-title / 年份 / 作者数，**全部命中**；`10.1016/j.comcom.2024.08.001` 首次超时，重试成功）。
- S2 `paper/batch` 核验 18 个 ID 的引用数与场馆。
- USENIX 页面实测 HTTP 200：NSDI'25 li-yang、NSDI'25 an、ATC'24 zhang-li-gaming、NSDI'24 wang-shibo、NSDI'26 heo。

---

**本轮条目总数：A1(5) + A2(6) + A3(4) + A4(7) + A5(10) + A6(6) + A7(8) + A8(4) + A9(6) = 56 行**；其中 ⭐ 必读 **29 条**、🔁 经典 **9 条**、状态列标 ⚠️ 的著录陷阱 **1 条**（A9-3 CGSynth，A2-6 行内的 ⚠️ 为叙述性提醒）。
（超出 25–45 目标，原因见检索局限：本子方向横跨 9 条独立线索，且顶会（NSDI/ATC/IMC/MMSys/ACM MM）近两年产出密集。若需压缩，建议优先保留 A2 全部、A1-1/A1-2/A1-3、A6-1/A6-2，其余按 📌 降级。）
