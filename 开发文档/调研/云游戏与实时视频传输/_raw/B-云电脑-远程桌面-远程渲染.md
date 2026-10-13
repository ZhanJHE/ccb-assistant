# 子方向 B：云电脑 / 远程桌面 / 远程显示 / 屏幕内容编码

> 检索日期：2026-10-01　检索人：文献调研 subagent
> 通道：Semantic Scholar Graph API（MCP + curl）、arXiv Atom API、OpenAlex、Crossref、Tavily、GO-EUC（工业界实测）
> 引用数为 **S2 Graph API 快照值（2026-10-01）**，会过时；S2 无记录的写 `—`（该条为 OpenAlex/Crossref 核到的题录）。
> 状态图例：⭐重点 / 📌归档 / 🧱经典（2010–2022）/ ⚠️待核实
> **所有条目的标题+年份+场馆均已用 Crossref 或 arXiv `id_list` 逐条核验**；未核到的明确标注。

---

## 0. 子方向总述

云电脑/远程桌面的技术链是「服务端渲染整块桌面 → 抓取屏幕更新 → 屏幕内容编码 → 低延迟传输 → 终端解码显示 → 输入回传」。它要解决的问题与游戏串流**同源但不同权重**：游戏串流可以牺牲文字细节换取帧率与端到端延迟，而云电脑的载荷是**文字、表格、UI 控件与光标**，代价函数里「文本可读性」是硬约束、帧率反而是软约束。2024–2026 年这一方向出现三个明显变化：① **屏幕内容编码（SCC）正式成为编解码器主赛道而非扩展包**——VVC 把 SCC 工具并入 v1，AV2 正在制定 SCC 工具集（ICIP 2026 有官方 overview），JPEG XS 增加了 Intra Pattern Copy（IPC），AVS3 也补齐了 IBC；② **学习式屏幕内容压缩（learned SCIC）出现爆发**，2024–2026 有十余篇 TCSVT/TMM/TBC/TIP 级工作，并开始引入「文本/非文本特征解耦」这类**专门保文本**的设计；③ **云电脑侧仍以工程优化与低档会议论文为主**，学术上几乎没有人对 Azure Virtual Desktop / Amazon WorkSpaces / Windows 365 做公开实测——本子方向最明显的空白就在这里（见 §3 与「检索局限」）。

---

## 1. B-A 云电脑 / VDI：实测与 QoE 方法

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要 / 与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| B-A-1 | ⭐ | Observing the Relationship between QoS Unpredictability, Prediction Error, and User Activity in a Remote Desktop Service | Keisuke Ishibashi 等 (7) | 2026-07 / arXiv 预印本（未见正式场馆） | arXiv:2607.28216 | 0 | 用**真实生产 RDS**（"Thin-Telework System"）按用户分析 RTT / 包数 / 收字节时序：**不只是平均 RTT，RTT 的时间波动（std）与瞬时偏离（prediction error）都与用户活动显著相关**。 | **本子方向最像"真论文"的一条**：现有 RDS-RTT 研究都在实验床做、样本少；这是首个用生产日志把「QoS 不可预测性」与用户行为联系起来的。与 WiFi/网络预测主题（本工作区 WTP 系列）天然相邻。 |
| B-A-2 | 🧱 | Performance Evaluation of VDI Environment | Hafiz ur Rahman 等 (5) | **2016 / INTECH**（同作者 2019 年 arXiv 重发 arXiv:1911.01923） | DOI:10.1109/INTECH.2016.7845102 | 22 | 早期 VDI 环境端到端性能评测，给出 VDI 的 CPU/网络/存储瓶颈画像。 | 云电脑实测的**奠基引用**。注意：S2 把 arXiv 重发版记作 2016（venue=InTech），正式场馆是 INTECH 2016，引用它时不要写成 2019 或 arXiv。 |
| B-A-3 | 🧱⭐ | Remote access protocols for Desktop-as-a-Service solutions | Eduardo Magaña 等 (4) | 2019 / **PLOS ONE** | DOI:10.1371/journal.pone.0207512 | 25 | 系统对比 DaaS 场景下的 **RDP / ICA(HDX) / PCoIP / RFB / TeamViewer** 五种远程桌面协议的带宽-延迟-画质权衡。 | 本子方向**唯一被广泛引用的"协议横评"**，是做远程桌面协议对照实验的默认基线（游戏串流侧的对应物是 GeForce NOW 那批测量）。 |
| B-A-4 | 🧱⭐ | Protocol-agnostic method for monitoring interactivity time in remote desktop services | Jesús Arellano-Uson 等 (4) | 2021 / Multimedia Tools and Applications | DOI:10.1007/s11042-021-10708-3 | 9 | 提出**协议无关的交互时间（interactivity time）测量方法**，可在 RDP/ICA 等加密协议上直接测端到端交互时延。 | 把"远程桌面 QoE"从主观问卷变成**可自动化测量的指标**；后续 2023、2024、2026 三篇都是这条线。 |
| B-A-5 | 📌 | Survey on Quality of Experience Evaluation for Cloud-Based Interactive Applications | Jesús Arellano-Uson 等 (4) | 2024 / Applied Sciences (MDPI) | DOI:10.3390/app14051987 | 11 | 综述云交互应用（远程桌面、云游戏、云 VR）的 QoE 评价方法：主观量表、客观指标、网络参数映射三条路线及其局限。 | **本子方向首选入门综述**，可用来一次性圈定"云电脑 QoE 该测什么"。 |
| B-A-6 | ⚠️ | Enhancing Remote Desktop QoE: decomposing interactivity time through a dual-agent observability architecture | Jesús Arellano-Uson 等 (4) | 2026 / SSRN 预印本（**未经同行评审**） | DOI:10.2139/ssrn.6293192 | — | 用双 agent 可观测架构把交互时间**分解**成若干阶段，定位延迟到底出在服务端/编码/网络/终端哪一段。 | 直接对应"端到端延迟拆解"这一空白；但只是 SSRN 预印本，**只能当方向线索，不能当结论用**。2023 年同组还有一篇 ITNAC 短文（DOI:10.1109/ITNAC59571.2023.10368539，S2 引用 2）用 RTT 近似交互时间，可一并追。 |

## 2. B-B 云电脑的网络侧：吞吐/带宽预测与视频传输优化

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要 / 与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| B-B-1 | ⭐ | DeskTransfer: Predicting Multi-Scenario Video Stream Throughput in Cloud Desktop Based on Transfer Autoencoder | Zuodong Jin 等 (5) | 2025 / **IEEE TMM** | DOI:10.1109/TMM.2025.3613109 | 0 | 用迁移自编码器做**云桌面多场景下视频流吞吐预测**，解决跨场景（不同应用/不同分辨率）分布漂移。 | 云电脑侧最贴近本工作区「链路预测 × 传输优化」母题的一篇；同一课题组的 DeskPred / ColoEP 构成一条线。 |
| B-B-2 | ⭐ | DeskPred: Two-Stage Video Stream Bandwidth Prediction for Cold-Start and Training Forgetting in Cloud Desktops | Zuodong Jin 等 (6) | TCSVT（**2025-11 early access；Crossref 出版年 2026**） | DOI:10.1109/TCSVT.2025.3632222 | 1 | 两阶段带宽预测，显式处理**冷启动**（新用户无历史）与**训练遗忘**（负载漂移后模型退化）两个工程痛点。 | 「冷启动 + 概念漂移」正好是本工作区 WiFi 负载预测主题（WTP-5/WTP-33 综述）里公认的难点，跨域可迁移。 |
| B-B-3 | 📌 | ColoEP: Resource Estimation and Preemption for Cloud Desktop Colocation Tasks Based on Meta and Reinforcement Learning | Zuodong Jin 等 (5) | 2026 / **IEEE TMC** | DOI:10.1109/TMC.2026.3688424 | 0 | 元学习 + RL 估计并抢占云桌面混部任务所需资源，提高单机可承载云桌面密度。 | 云电脑的**供给侧（一台服务器塞多少桌面）**问题；与 vGPU 共享（B-C 组）互补。 |
| B-B-4 | 📌 | A Novel CCA-MoE for Real-Time Bandwidth Prediction in Cloud Desktop Environments | Xidong Sun 等 (5) | 2026 / **IEEE ICCE-Taiwan** | DOI:10.1109/ICCE-Taiwan71481.2026.11652730 | 0 | 用交叉通道注意力 + 混合专家做云桌面实时带宽预测。 | 与 B-B-1/B-B-2 同一问题的第三条技术路线（MoE），说明这个小方向已经"卷起来了"。 |
| B-B-5 | 📌 | Cloud Desktop Frame Rate Enhancement Based on Video Frame Interpolation | Weihong He 等 (3) | 2024 / ICCEA（**非顶会**） | DOI:10.1109/ICCEA62105.2024.10603985 | 0 | 在云桌面链路里插入视频插帧，把低帧率编码流补到高帧率显示。 | **直接触及"帧率 vs 带宽"的取舍**：云桌面为了省带宽降帧率，再用插帧补观感。可作为"云桌面不希望被当游戏串流处理"的反例论据（插帧对文字反而糊）。 |

## 3. B-C VDI / 云桌面系统与 GPU 共享

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要 / 与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| B-C-1 | 📌 | A CRC Comparison-Based Screen Data Management for Energy Efficient Virtual Desktop Infrastructure | Chang Yeop Han 等 (7) | 2025 / **IEEE Access** | DOI:10.1109/ACCESS.2025.3578943 | 1 | 用加速 CRC 比对管理 VDI 屏幕数据，减少内存访问与功耗。 | VDI 的**屏幕差分/变化检测**环节（IBC 的工程替代品）；"省的是内存带宽与功耗"这一口径在学术 VDI 文献里很少见。 |
| B-C-2 | 📌 | Toward Enabling a Containerized Virtual Desktop System | Hsin Chou 等 (3) | 2026 / **IEEE Access** | DOI:10.1109/ACCESS.2026.3721962 | 1 | 用容器替代虚拟机承载虚拟桌面，改善资源效率、可扩展性与能耗。 | VDI→**容器化桌面**的转型样本；与 VM 隔离/启动开销主题相邻（本工作区另有 Colaboot，arXiv:2408.17045，云盘无盘启动，S2 引用 3）。 |
| B-C-3 | 🧱 | Multi-Tier GPU Virtualization for Deep Learning in Cloud-Edge Systems | Jason Kennedy 等 (4) | 2023 / **IEEE TPDS** | DOI:10.1109/TPDS.2023.3274957 | 29 | 云-边场景下多层 GPU 虚拟化方案（API 重定向 / 直通 / 分片）的性能与适用性对比。 | vGPU 共享对抗的**参考基线**；虽以 DL 为负载，但 GPU 虚拟化层的开销结论可直接迁移到 VDI 图形加速。 |
| B-C-4 | 📌 | nvshare: Practical GPU Sharing without Memory Size Constraints | Georgios Alexopoulos 等 (2) | 2024 / **ICSE-Companion**（**工具/短文轨道，非 ICSE 正会**） | DOI:10.1145/3639478.3640034 | 10 | 无显存大小约束的实用 GPU 共享方案（时间片 + 显存超售）。 | 云桌面/云游戏共用 GPU 的最直接开源方案；与另外两条 GPU 共享线相邻：gShare（ASPLOS 2026，DOI:10.1145/3779212.3790168，S2 引用 3）与 NFV 场景的时空 GPU 共享（IEEE TC 2023，DOI:10.1109/TC.2023.3278541，S2 引用 4）。 |

## 4. B-D 屏幕内容编码（SCC）：标准、工具与硬件加速

> 这一组是**云电脑/远程桌面的核心使能技术**：IBC（intra block copy）、palette、ACT 等 SCC 工具正是因为屏幕内容"高重复、有限色彩、锐利边缘"才被加进标准的。

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要 / 与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| B-D-1 | ⭐ | An Overview of Screen-Content Coding Tools in AV2 | Qingyang Zhou 等 (9) | 2026 / **IEEE ICIP 2026** | DOI:10.1109/icip61757.2026.11630506 | 0 | AOMedia **AV2** 的屏幕内容编码工具官方 overview（palette、IBC 等工具的设计与取舍）。 | **AV2 SCC 是目前最新的一手标准进展**，作者来自 AOMedia 成员方；S2 把场馆误记为 "International Conference on Information Photonics"，**Crossref 确认为 ICIP 2026**。 |
| B-D-2 | ⭐ | Improved Intra Block Copy Mode Beyond AV1 | Qingyang Zhou 等 (7) | 2025 / **VCIP 2025** | DOI:10.1109/VCIP67698.2025.11396863 | 0 | 在 AV1 之外进一步改进 IBC 模式（同组，落进 AV2 的工具）。 | 与 B-D-1 同一作者组，**"AV2 SCC 从哪来"的技术细节在这里**。 |
| B-D-3 | ⭐ | Reconstruction Reordered Intra Block Copy for Screen Content Coding | Zhipin Deng, Kai Zhang, Li Zhang (3) | 2025 / **IEEE TIP** | DOI:10.1109/TIP.2025.3579988 | 2 | 重排重建顺序的 IBC，缓解 IBC 参考块可依赖性问题，提升 SCC 压缩效率。 | **标准制定者署名（字节跳动/快手系，Kai Zhang 为 VVC 重要贡献者）**，是 TIP 级 SFR（standard-facing research）代表。 |
| B-D-4 | ⭐ | Frequency Domain Intra Pattern Copy for JPEG XS Screen Content Coding | Yao Li, Dong Liu, Li Li 等 (4) | 2025 / **IEEE TCSVT** | DOI:10.1109/TCSVT.2025.3562963 | 2 | 把 IBC 思想推广到 **JPEG XS 的频域 Intra Pattern Copy（IPC）**，服务低复杂度低延迟远桌面场景。 | JPEG XS 是**远桌面/专业视频的轻量编解码器**（编码复杂度极低），这条线对"云电脑要低编码开销"特别对味。 |
| B-D-5 | 📌 | An FPGA Implementation of Displacement Vector Search for Intra Pattern Copy in JPEG XS | Qiyue Chen 等 (6) | 2026-03 / arXiv:2603.10671（**未见正式场馆**） | arXiv:2603.10671 | 0 | JPEG XS IPC 的位移矢量搜索 FPGA 实现。 | **硬件侧落地**，与本工作区的 FPGA/DPDK 取向高度一致；与 B-D-4 同一条技术线（软件→硬件）。 |
| B-D-6 | 📌 | A Power-Efficient Hardware Accelerator for Real-Time Hashmap Construction in VVC Intra Block Copy | Zehao Tao 等 (6) | TCSII（**2026-02 期，DOI 号为 2025**） | DOI:10.1109/TCSII.2025.3639153 | 0 | VVC IBC 的哈希表构造**硬件加速器**，面向实时/低功耗编码。 | IBC 的搜索复杂度是实时代码的瓶颈；这类"把 IBC 塞进硬件"的工作是实现侧关键。 |
| B-D-7 | 📌 | Ultra-Fast Intra Screen Content Coding via Accelerated Re-Visit CU-Coding in AVS3 | Xueyan Cao 等 (7) | 2025 / **ACM TOMM** | DOI:10.1145/3748509 | 0 | AVS3 的加速 Revisit CU 编码（ARC），并给出 SCC 搜索空间的算子级复杂度分析。 | **改写（revisit）不是跳过（skip）**——不是靠剪枝换速度，而是重排搜索；复杂度分析口径可直接复用。 |
| B-D-8 | 📌 | GCOTSC: Green Coding Techniques for Online Teaching Screen Content Implemented in AVS3 | Liping Zhao 等 (7) | 2024 / **IEEE TBC** | DOI:10.1109/TBC.2023.3340042 | 7 | 面向**在线教学屏幕内容**的绿色（省能耗）编码工具，落地在 AVS3。 | 罕见的**按应用场景（在线教学）挑 SCC 工具**的工作，与"云 Office"场景最接近的现成文献。 |
| B-D-9 | 📌 | Multi-Stage Prediction CNN: Fast CU Partition for VVC Screen Content Coding | Jing Chen 等 (5) | 2026 / **IEEE TMM** | DOI:10.1109/tmm.2026.3680425 | 0 | 多阶段 CNN 预测 VVC-SCC 的 CU 划分，降低编码复杂度。 | VVC-SCC 编码复杂度的一整条线（见 B-D-10/11），本条最新。 |
| B-D-10 | 🧱 | Fast Mode and CU Splitting Decision for Intra Prediction in VVC SCC | Dayong Wang 等 (7) | 2024 / **IEEE TBC** | DOI:10.1109/TBC.2024.3394288 | 19 | 快速模式与 CU 划分联合决策（VVC SCC 帧内），大幅降复杂度。 | 这条线里**引用最高**的一篇（19），可作为该子方向的对照基线；同组还有 TBC 2025 的 Fast Coding Mode Decision（DOI:10.1109/TBC.2025.3541773，引用 2）与 ICASSP 2024 的 SCBS 快速帧内模式（DOI:10.1109/ICASSP48485.2024.10445831）。 |
| B-D-11 | 📌 | Width-Adaptive CNN: Fast CU Partition Prediction for VVC Screen Content Coding | Chao Jiao 等 (6) | 2024 / **IEEE TMM** | DOI:10.1109/TMM.2024.3410116 | 9 | 宽度自适应 CNN 预测 CU 划分——**首次从 CU partition 角度降 VVC-SCC 复杂度**。 | 学习式加速 SCC 的代表作；与 B-D-9 同一问题不同网络结构。 |
| B-D-12 | ⭐ | Optimizing an Open VVC Encoder for Low Delay Remote Desktop Applications | Anastasia Henkel 等 (7) | 2024 / **IEEE ICMEW**（**workshop，非 ICME 正会**） | DOI:10.1109/ICMEW63481.2024.10645432 | 0 | 把开源 VVC 编码器针对**低延迟远程桌面**场景调优（低延迟配置 + SCC 工具取舍）。 | **本子方向"最正中心"的一篇**：直接研究"VVC 怎么配才能服务远程桌面"，是把 SCC 与云电脑连起来的关键引用。**注意是 ICMEW workshop**，不要写成 ICME。 |
| B-D-13 | 🧱⭐ | Overview of Screen Content Coding in Recently Developed Video Coding Standards | Xiaozhong Xu, Y. Xu (2) | 2022 / **IEEE TCSVT**（前身：VCIP 2020 tutorial，DOI:10.1109/VCIP49819.2020.9301789；预印本 arXiv:2011.14068） | DOI:10.1109/TCSVT.2021.3064210 | — | 横向综述 **HEVC-SCC / VVC / AVS3 / AV1 / EVC** 五大标准的 SCC 工具与相对收益。 | **入门必读且是"经典"**：一份材料就能说清 SCC 工具的谱系（IBC / palette / ACT / transform-skip / BDPCM）与各标准的实现差异。作者是标准参与者。 |
| B-D-14 | 📌 | Lossless 4:2:0 Screen Content Coding Using Luma-Guided Soft Context Formation | Hannah Och, André Kaup (2) | 2025 / **EUSIPCO 2025** | DOI:10.23919/eusipco63237.2025.11226648 | — | 把 soft context formation 无损编码扩展到 4:2:0，用亮度引导色度预测。 | **无损**路线：远程桌面里"文字不能糊"的极限解法（无损/近无损 SC 编码），与有损 learned SCIC 是两派。同组另一篇 ICASSP 2024（DOI:10.1109/ICASSP48485.2024.10447125，引用 2）是 VVC 内的同类改进。 |

## 5. B-E 学习式屏幕内容压缩与质量评价

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要 / 与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| B-E-1 | ⭐ | FD-LSCIC: Frequency Decomposition-Based Learned Screen Content Image Compression | Shiqi Jiang 等 (5) | 2025 / **IEEE TBC**（预印本 arXiv:2502.15174） | DOI:10.1109/TBC.2025.3609052 | 7 | 频域分解驱动的学习式屏幕内容图像压缩，针对 SC 的"低频大片 + 高频锐利文字边缘"结构。 | learned SCIC 里成体系的一支（同组 OMR-Net 系列，B-E-2）；"频域分解"直接对应文字边缘保护。 |
| B-E-2 | 📌 | OMR-Net+: A Frequency-Aware Feature Refinement and Entropy Modeling Method for Efficient Screen Content Image Compression | Shiqi Jiang 等 (5) | 2025 / **IEEE SPL** | DOI:10.1109/LSP.2025.3596872 | 6 | 八度多尺度残差 + 频率感知特征精炼与熵建模（OMR-NET 的扩展，前作 SPL 2024 引用 11）。 | 对 baseline LIC 在 SC 上的**系统性改进**；是"通用 LIC 直接拿来压屏幕内容会吃亏"的证据链。 |
| B-E-3 | ⭐ | Text and Non-Text Latent Feature Disentanglement for Screen Content Image Compression | Hao Wang 等 (8) | 2026 / **IEEE TCSVT** | DOI:10.1109/TCSVT.2025.3602506 | 1 | 在隐空间**显式解耦文本与非文本特征**分别建模，保文字锐度同时不浪费码率。 | **"文字是云电脑的硬约束"最直接的编码侧证据**；同组 ICME 2025 的 text-rich 插件处理网络（DOI:10.1109/ICME59968.2025.11209161，引用 0）是同一思路的轻量版。 |
| B-E-4 | ⭐ | Enhanced Screen Content Image Compression: A Synergistic Approach for Structural Fidelity and Text Integrity Preservation | Fangtao Zhou 等 (7) | 2024 / **ACM Multimedia 2024** | DOI:10.1145/3664647.3681354 | 7 | 全局空间注意力 + **对文字区域加权 MSE 的损失设计**，同时保结构保文字。 | 顶会级证据：把"文本完整性"写成显式优化目标。与 B-E-3 互为软/硬两条实现路线。 |
| B-E-5 | 📌 | SCID-Compress900: A Multi-Scene Dataset of 4K and 1080P Screen Content Images for Image Compression Research | Huiming Zheng 等 (3) | 2025 / **ACM Multimedia 2025** | DOI:10.1145/3746027.3756883 | 2 | 900 张 4K/1080P 多场景屏幕内容图像压缩数据集。 | **云电脑/远程桌面压缩研究缺的正是"真实桌面内容"数据**；与 2023 年的 LSCD 视频数据集（arXiv:2308.09332）互补，是新工作的评测底座。 |
| B-E-6 | 📌 | Deep Screen Content Image Compression with Palette Context and Hash Attention | Feifeng Wang 等 (7) | 2026 / **IEEE TCSVT** | DOI:10.1109/tcsvt.2026.3714976 | 0 | 把 palette（调色板）先验与哈希注意力塞进深度 SCIC，吸收传统 SCC 工具的优势。 | **传统 SCC 工具 × 学习式编码的融合**趋势样本（对照 B-D 组的纯标准工具路线）。 |
| B-E-7 | 📌 | RA-SCIC: Region-Aware Screen Content Image Coding Towards Fidelity and Efficiency | Chao Jiao 等 (6) | 2026 / **IEEE TMM** | DOI:10.1109/tmm.2026.3712238 | 0 | 区域感知：对文字/图形区域与图自然图像区域用不同策略，平衡保真与效率。 | 与"按区域分配码率"思想一致，可直接用于云电脑的**区域自适应码率**设计。 |
| B-E-8 | 📌 | A No-Reference Quality Assessment Model for Screen Content Videos via Hierarchical Spatiotemporal Perception | Zhihong Liu 等 (6) | 2025 / **IEEE TCSVT** | DOI:10.1109/TCSVT.2024.3469180 | 4 | 无参考屏幕内容视频质量评价（分层时空感知）。 | 云电脑链路里**终端侧无法拿到原始画面**，无参考评价是唯一可行路径；同主题还有 TMM 2025（DOI:10.1109/TMM.2025.3599071，引用 2）与 TBC 2024 的深度学习版（DOI:10.1109/TBC.2024.3374042，引用 10）。 |

## 6. B-F 远程渲染 / 像素流

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要 / 与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| B-F-1 | ⭐ | Remote Rendering for Virtual Reality: Performance Comparison of Multimedia Frameworks and Protocols | Daniel Mejías 等 (5) | 2025 / **IEEE MeditCom 2025**（预印本 arXiv:2507.00623） | DOI:10.1109/MeditCom64437.2025.11104418 | 5 | 把 GStreamer / FFmpeg 分别接到 Remote Renderer，对比不同传输协议在 WiFi/5G 下的端到端表现。 | 远程渲染链路的**"框架 × 协议"对照表**；同组 BMSB 2025 做了 MoQ vs RoQ vs WebRTC 的 QUIC 对比（DOI:10.1109/BMSB65076.2025.11165653，引用 3）。 |
| B-F-2 | 📌 | Leveraging 5G Physical Layer Monitoring for Adaptive Remote Rendering in XR Applications | Inhar Yeregui 等 (6) | 2025 / **IEEE BMSB 2025**（预印本 arXiv:2505.22123） | DOI:10.1109/BMSB65076.2025.11165569 | 1 | 用 5G 物理层监测驱动远程渲染的**码率/帧率/分辨率实时自适应**。 | 与 B-F-1 同组；"用物理层信息而非应用层吞吐估计来做自适应"是网络侧新角度。 |
| B-F-3 | ⭐ | Thin-Client Interactive Gaussian Adaptive Streaming over HTTP/3 | Emanuele Artioli 等 (7) | 2026-05 / arXiv:2605.08699（**未见正式场馆**） | arXiv:2605.08699 | 0 | TIGAS：把 3DGS 光栅化放到后端、客户端只做交互，走 HTTP/3 自适应传输。 | **"thin client + 服务端渲染"最新形态**（2026）；虽面向 3D 场景而非桌面，但架构与云电脑同构，且给出可复用 testbed。 |
| B-F-4 | 📌 | Towards Interactive Volumetric Video experiences on Lightweight VR Devices through Remote Rendering | Miguel Fernández-Dasí 等 (6) | 2026 / **ACM IMX 2026** | DOI:10.1145/3788851.3815052 | 0 | 面向轻量 VR 设备的端到端远程渲染架构与组件/工作流。 | 端到端**系统架构**参考；与 B-F-3 同属"把重活搬到云、终端只解码"的路线。 |
| B-F-5 | 📌 | DHR+S: Distributed Hybrid Rendering with Realistic Real-time Shadows for Interactive Thin Client Metaverse and Game Applications | Yu Wei Tan 等 (5) | 2024 / **The Visual Computer**（预印本 arXiv:2406.06963） | DOI:10.1007/s00371-024-03501-4 | 13 | 分布式混合渲染 + 软阴影近似，让 thin client 也能跑实时阴影。 | **混合渲染（云渲染 + 端渲染）**路线代表：不把画面全部推给云，可显著降码率。这是云电脑也能借鉴的方向（端侧合成 UI 图层）。 |

## 7. B-G 游戏串流 vs 云电脑：需求差异的证据

> 这一组不是云电脑本体，但**是回答"两类应用需求如何不同"的唯一证据来源**。用它们时必须说明是游戏侧结论。

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要 / 与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| B-G-1 | ⭐ | Games Are Not Equal: Classifying Cloud Gaming Contexts for Effective User Experience Measurement | Yifan Wang 等 (3) | 2025 / **ACM IMC 2025** | DOI:10.1145/3730567.3764455（arXiv:2509.19669） | 4 | **云游戏内部也不是同质的**：不同游戏类型（竞技/剧情/策略）对延迟与画质的敏感度不同，UX 测量必须按 context 分类。 | **反向支持"云电脑≠云游戏"**的顶会证据：如果一个领域内部都不能用一套指标，跨领域更不行。|
| B-G-2 | ⭐ | Network Anatomy and Real-Time Measurement of Nvidia GeForce NOW Cloud Gaming | Minzhao Lyu 等 (4) | 2024 / **PAM 2024**（LNCS） | DOI:10.1007/978-3-031-56249-5_3（arXiv:2401.06366） | 19 | 对 GeForce NOW 做网络解剖与实时测量：码率、帧率、延迟行为随网络条件的演化。 | **商业云游戏系统的公开实测标杆**。同组期刊扩展版见 **IEEE/ACM ToN**（DOI:10.1109/TON.2025.3623962，S2 引用 2）。**云电脑侧至今没有等价论文**——这正是空白（见 §检索局限）。 |
| B-G-3 | 📌 | Real-time latency prediction for cloud gaming applications | Doriana Monaco 等 (7) | 2025 / **Computer Networks** | DOI:10.1016/j.comnet.2025.111235 | 13 | 用网络测量特征实时预测云游戏端到端延迟。 | 与云电脑的 B-B-1/B-B-2（吞吐/带宽预测）**问题同构、指标不同**：游戏侧关心"延迟可预测"，云电脑侧关心"带宽可预测"。可用来论证两类应用的优化目标确实不同。 |

---

## 8. 明确区分：游戏串流 vs 云电脑 / 远程桌面

以下每条都挂了具体出处，**不靠直觉**。

### 8.1 帧率：游戏要 60–120 fps，VDI 出厂默认 30 fps

- **工业界实测（非学术，但方法可复现）**：GO-EUC 用 **NVIDIA LDAT** 测 VDI 输入延迟，Citrix HDX **默认 30 FPS 时平均端到端输入延迟 106 ms，调到 60 FPS 后降到 58 ms（−45%）**；作者同时指出代价是 VDI 与终端 CPU 延迟上升、带宽消耗必然增加。测试样本 100 次/轮。— [Measuring Input Latency in Virtual Desktops: Citrix HDX](https://www.go-euc.com/measuring-input-latency-in-virtual-desktops-citrix-hdx)（同系列还测了 VMware Blast；**注意这是厂商生态的工程博客，不是同行评审论文，引用时要标清**）
- 对读：云游戏侧把 60 fps 当**下限**在讨论（Trinity, MMSys 2026, DOI:10.1145/3793853.3795744：同一游戏内不同动作的延迟敏感度还不同）。→ **同一份带宽，游戏侧买帧率，云电脑侧买文字清晰度**。

### 8.2 质量约束：文字可读性 vs 运动流畅度

- 云电脑的载荷以文字/UI 为主，**通用自然图像编解码器直接拿来会吃亏**，所以 SCC 才需要 IBC / palette / ACT 这类工具（谱系见 B-D-13（TCSVT 2022 综述））。
- 学习式编码已经把"文字"写成**显式优化目标**：对文字区域加权 MSE（B-E-4, ACM MM 2024）、隐空间文本/非文本特征解耦（B-E-3, TCSVT 2026）、text-rich 内容的插件式前后处理（ICME 2025）。
- 因此云电脑的 SFR（standard-facing research）在往"无损/近无损 + 低复杂度"走（B-D-14, EUSIPCO 2025），而游戏串流侧更愿意接受感知有损换码率（云游戏侧普遍用超分/增强，如 Real-Time Neural-Enhancement for Online Cloud Gaming, arXiv:2501.06880）。

### 8.3 延迟：交互延迟是共性硬约束，但"波动"对桌面更致命

- B-A-1（arXiv:2607.28216）在生产 RDS 日志上发现：**与用户活动显著相关的不仅是平均 RTT，还有 RTT 的时间标准差与瞬时偏离**（即 QoS 不可预测性）。这比"平均延迟够低就行"的游戏侧口径更严。
- 云游戏侧的对应证据是设"延迟预算"（如 NSDI 2025 的 LoopTailor 把移动云游戏交互延迟压到稳定 <100 ms）——**用均值/分位数指标**，对"波动本身伤害用户"没有等价结论。

### 8.4 不要混用的两条口径澄清

- **ICMEW ≠ ICME**：B-D-12（Optimizing an Open VVC Encoder for Low Delay Remote Desktop Applications）是 **ICMEW 2024 workshop** 论文。
- **ICSE-Companion ≠ ICSE**：B-C-4（nvshare）是 ICSE 2024 的 Companion（工具/短文）轨道。
- **arXiv 重发 ≠ 原会议**：B-A-2 的正式出处是 **INTECH 2016**；arXiv:1911.01923（2019）是同一作者的重发版本。
- B-D-1（AV2 SCC overview）的 S2 场馆字段是错的（写成 "International Conference on Information Photonics"），**以 Crossref 的 ICIP 2026 为准**。

---

## 9. 检索局限（含哪些查询失败/被限流）

1. **Semantic Scholar 大面积 429 限流**：即使 `S2_API_KEY` 已设置，`/paper/search` 在连续调用下约 1/3 请求返回 429（"Too Many Requests"），另一批成功。已用 **OpenAlex + Crossref + arXiv** 三路替代，并把能拿到的 S2 结果用 `paper/batch`（单次 POST）集中取引用数快照。**"S2 查不到" ≠ "不存在"**。
2. **云电脑/远程桌面的学术实测文献确实稀少**：`title_and_abstract.search:"Azure Virtual Desktop"`（OpenAlex，2022 起，命中 63 但全部是 Apress 技术书章节）；`"Amazon WorkSpaces"`（命中 65，无一篇网络实测）；`"Windows 365" cloud PC`（命中 3，全部是 Zenodo/SSRN 的自出版白皮书）。→ **未检索到任何针对 Microsoft Azure Virtual Desktop / Amazon WorkSpaces / Windows 365 的公开学术实测（题录级核到"没找到"）**。
3. **RDP / HDX / PCoIP / Blast 的协议级学术测量主要集中在 2019–2021**：2024–2026 年只有零星低档会议与安全向论文（RDP 凭据窃取、RDP 横向移动，ACM 2026），**传输/QoE 向几乎没有新论文**。最新的协议级 GUI 延迟数据只能靠工业界（GO-EUC）——**该来源非同行评审**。
   - 另：**开源远程桌面栈（X2Go / KDrive、Guacamole、noVNC、RustDesk）在学术上几乎无人研究**。本次只命中了 2 条低档工作（X2Go KDrive 传输优化，EIECC 2024，DOI:10.1109/EIECC64539.2024.10929510，S2 引用 0；Guacamole 协议视频传输优化，DOI:10.1117/12.3071178，S2 引用 0）。因档次太低、信息量不足，**未列入正表**，仅在此备注。
4. **厂商系统论文缺席**：Microsoft / Amazon / VMware / Citrix 均未在任何 A/B 类会议发表自家云桌面的架构或实测论文（检索 `${厂商} VDI measurement`、`Horizon Blast performance` 均未命中学术论文）。VMware Blast / Citrix HDX 的具体编码器细节**只能从 Citrix 官方文档与第三方博客得知，未做学术核实**。
5. **arXiv Atom API** 本次未出现 429，8 组 query 均正常返回；但 `all:"cloud desktop"` 全库仅命中 1 条（CyberEye, 2022），说明**这个英文术语在 arXiv 上几乎不被使用**——云电脑相关工作更多以 "cloud gaming" / "remote rendering" / "virtual desktop" 的标签出现，仅靠关键词检索会漏。
6. **S2 场馆字段质量差**：至少 3 条出现明显错误（AV2 SCC overview、Adapting Learned Image Codecs to Screen Content 均被写成 "International Conference on Information Photonics"；Matches 真实的 ICIP）。**本笔记所有场馆已用 Crossref 复核，以 Crossref 为准**。
7. **两条只到"题录/摘要级"**：
   - B-A-6（SSRN 预印本）——只核到题录，未读正文，**不可引用其结论**。
   - B-D-5、B-F-3（arXiv 预印本，未见正式发表）——只核到 arXiv 题录与标题，未读正文。
8. **未核实到 DOI 的条目**：B-A-1（arXiv:2607.28216 无 DOI）、B-D-5、B-F-3 三条无 DOI；B-E-8 的 TCSVT 2025 期号与 DOI（10.1109/TCSVT.2024.3469180）已用 Crossref 核到。
9. **CCF 分级未逐条查证**：本笔记只标"期刊/会议/workshop"层级，**未对照《第七版 CCF 推荐目录》逐条定级**。已知可确定的：TMM / TIP / TCSVT / TMC / TPDS / TBC / SPL 为期刊；ACM MM、ICIP、ICASSP、IMC、MMSys、PAM 等为会议（**ICMEW、ICSE-Companion、VCIP、EUSIPCO、MeditCom、BMSB、IMX、PRMVAI、ICCE-Taiwan、ICCEA、EIECC 需另行定级**）。
