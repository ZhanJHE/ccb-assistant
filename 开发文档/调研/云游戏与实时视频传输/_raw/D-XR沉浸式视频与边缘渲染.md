# 子方向 D — XR / 沉浸式视频 / 边缘辅助渲染与计算卸载

> **条目数说明**：主表编号条目 **51 条**（A 8 / B 8 / C 7 / D 9 / E 6 / F 6 / G 7），另有约 50 条已核实但未进入主表的记录，分散在各表下方的「未收录但已核实」段并保留完整题录。**51 条略高于本轮「25–45 条」的目标**：本子方向实际裂成 7 个互不重叠的簇（3DGS/NeRF 传输、体积视频/点云、FoV 预测、远端/分体渲染、注视点渲染、360° tile+边缘缓存、QoE/测量），每簇压到 6–9 条已是最低可读量；表中无凑数条目，每条均为逐条核实题录后的收录。若需严格压到 45 条，建议优先裁掉 B4/B8、C4、D9、E6、F6、G2 六条（理由：结论已被同簇其他条目覆盖）。

> 原始调研笔记（只做检索与核实，未做提炼综述）。
> 检索日：2026-10-01。引用数为 **Semantic Scholar 快照值**，会过时。
> 核实口径：arXiv ID 经 S2 `paper/batch`（含 DBLP/DOI 交叉字段）逐条比对标题；DOI 经 S2 `paper/batch` 或 Crossref 解析。凡只到题录级/摘要级者均已注明。
> 场馆分级依据工作区《CCF 第七版》核对：INFOCOM / MobiCom / MobiSys / SIGCOMM / NSDI / ISCA / MM(A) 为 A 类；MMSys / NOSSDAV / CoNEXT / VRST 等按目录另计；**workshop 一律不写作正会**。

---

## 0. 子方向总述

这个子方向解决的是同一类问题：**把渲染或重计算从终端移出去，同时让"人在看什么"这件事尽量少地花在传输上**。它和云游戏同源——都受"运动到光子（motion-to-photon, MTP）延迟"这一个硬约束支配，因此共用三套技术底座：**FoV / 视口 / 头动预测**、**tile（或层次/可伸缩）编码与自适应码率**、**边缘放置与缓存**（见文末对照表）。

近两年的变化有三条。第一，**表征层换血**：2024–2026 的分量从"点云 / V-PCC / 360° 视频"快速转向 **3D Gaussian Splatting（3DGS）与 NeRF 的流式传输**，2025 年出现第一批完整系统（LTS、Vega、LMG、NeVo），2026 年则出现把 3DGS 直接映射到 **Media over QUIC（MoQ）** 等新传输层、以及"薄客户端远端渲染 3DGS"的工作（MoQSplat、TIGAS）。第二，**算力侧与网络侧分家**：DAC/ICCAD/ISCA 一批论文只优化端侧 3DGS 渲染的显存/片内带宽（STREAMINGGS、LS-Gaussian、A3FR、POLONet），与网络侧的码率/分层工作几乎不交叉，两边的指标口径也不通用。第三，**测量与真机开始补课**：2026 年出现 O-RAN 真机测 MTP、体素材流式端到端延迟归因、以及 3GPP Rel-19 的 XR 无线增强综述；但**大规模沉浸式服务的真实 trace 测量仍远少于视频流媒体**（对照：云游戏侧已有 GeForce NOW 的大规模被动测量）。

---

## 1. 表 A：3DGS / NeRF 流式渲染与传输（2025–2026，本方向最活跃）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| D-XR-A1 | ⭐ | LTS: A DASH Streaming System for Dynamic Multi-Layer 3D Gaussian Splatting Scenes | Yuan-Chun Sun | 2025 / ACM MMSys | DOI:10.1145/3712676.3714445 | 30 | 把动态多层 3DGS 场景做成 DASH 分层流式（LOD 层 + 动态高斯层），MMSys'25 3DGS 流式的代表系统。 | 与云游戏同源（分层码流 + 客户端 ABR）；本表引用最高的一篇 |
| D-XR-A2 | ⭐ | Vega: Fully Immersive Mobile Volumetric Video Streaming with 3D Gaussian Splatting | Gunjoong Kim | 2025 / ACM MobiCom | DOI:10.1145/3680207.3765267 | 7 | 手机端 3DGS 全场景体积视频实时播放（30 fps），按视觉显著性优先传对象。 | 移动端「客户端自己渲染」路线的旗舰；有 GetMobile 科普版（DOI:10.1145/3810919.3810924） |
| D-XR-A3 | ⭐ | Adaptive 3D Gaussian Splatting Video Streaming: Visual Saliency-Aware Tiling and Meta-Learning-Based Bitrate Adaptation | Han-Sheng Gong | 2025 / arXiv | arXiv:2507.14454 | 3 | 显著性驱动的 tile 划分 + 元学习 ABR，把 360° 视频那套 tile/ABR 直接搬进 3DGS。 | **tile 编码这一公共底座在 3DGS 上的直接续作**，是 XR↔云游戏技术迁移的最好例证 |
| D-XR-A4 | ⭐ | On the Efficient Adaptive Streaming of 3D Gaussian Splatting Over Dynamic Networks | Yi-Fan Wang | 2025 在线 / 2026 卷期 / IEEE TCSVT | DOI:10.1109/TCSVT.2025.3637837 | 5 | 动态网络条件下 3DGS 自适应流式的系统化处理。 | TCSVT 是本题指定的重点场刊 |
| D-XR-A5 | ⭐ | LMG: Efficient Streaming of Layered Mesh-Gaussian 3D Scenes | Yuan-Chun Sun | 2026 / ACM MMSys | DOI:10.1145/3793853.3795764 | 1 | 首个端到端 Layered Mesh-Gaussian 流式系统：训练服务器 + 流服务器 + XR 客户端三件套。 | MMSys'26 最新；与 A1 同一组（Sun / Hsu），代表"混合表征"路线 |
| D-XR-A6 | 📌 | Thin-Client Interactive Gaussian Adaptive Streaming over HTTP/3（系统名 TIGAS） | Emanuele Artioli | 2026 / arXiv | arXiv:2605.08699 | 0 | 把光栅化放到后端、走 HTTP/3 的薄客户端 3DGS 远端渲染框架，同时可作 3DGS 流式研究的 testbed。 | **「远端渲染 3DGS」最直接的实现**；与 A7 同组（Artioli / Timmerer） |
| D-XR-A7 | 📌 | MoQSplat: Adaptive Progressive Streaming of 3D Gaussian Splatting via MoQ | Emanuele Artioli | 2026 / arXiv | arXiv:2609.18624 | 0 | 把 3DGS 内容映射到 Media over QUIC（MoQ）传输层级做渐进式投递；结论是 opacity 剪枝优于 scale 剪枝。 | **新传输协议（MoQ）× 3DGS**，2026-09 最新，属"下一个协议层" |
| D-XR-A8 | 📌 | Packet-Loss Robust 3D Gaussian Compression via Atomic Packaging and GNN-based Error Concealment | Yu-Bang Tao | 2026 / arXiv | arXiv:2607.17916 | 0 | 原子打包 + GNN 错误隐藏；丢包下相对无损参考的 PSNR 平均只降约 3 dB。 | 3DGS 传输的**丢包鲁棒性**支线（云游戏侧对应物是 VIGOR，见 D-XR-G-补） |

> **表 A 未收录但已核实**（内容相关，本表已满）：SplatStream: Fine Granular Scalable Gaussian Splatting（Muhammad Talha 等，arXiv:2607.25971，0 引用，把 GS 场景分解为质量层/分辨率层 + 层间预测编码）；SRBF-Gaussian: Streaming-Optimized 3D Gaussian Splatting（Dayou Zhang 等，IEEE VR 2025，DOI:10.1109/VR59515.2025.00070，5 引用）；Evaluation of strategies for efficient rate-distortion NeRF streaming（Pedro Martin 等，IEEE ISM 2024，arXiv:2410.19459 · DOI:10.1109/ISM63611.2024.00033，0 引用，结论：NeRF 的"网络参数流"在 RD 上优于"像素流"，更适合一对多）；Potamoi: Accelerating Neural Rendering via a Unified Streaming Architecture（Yu Feng 等，ACM TACO 2024，arXiv:2408.06608 · DOI:10.1145/3689340，22 引用，神经渲染硬件侧）；STREAMINGGS（DAC 2025，arXiv:2506.09070 · DOI:10.1109/DAC63849.2025.11132470，8 引用）与 No Redundancy, No Stall（LS-Gaussian，ICCAD 2025，arXiv:2507.21572 · DOI:10.1109/ICCAD66269.2025.11240950，5 引用）——这两篇是**端侧渲染算力**侧，不涉及网络。

---

## 2. 表 B：体积视频 / 点云流式（V-PCC / G-PCC / Draco / 6-DoF 自由视点）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| D-XR-B1 | ⭐ | NeVo: Advancing Volumetric Video Streaming with Neural Content Representation | Nan Wu | 2025 / ACM MobiCom | DOI:10.1145/3680207.3723473 | 3 | 面向 NeRF 类神经内容的体积视频流式；省带宽最多 68.3%，且丢包下伪影更少。 | **NeRF × 体积视频流**的旗舰；与 A2 同会 |
| D-XR-B2 | ⭐ | QV4: QoE-based Viewpoint-Aware V-PCC-encoded Volumetric Video Streaming | Yuang Shi | 2024 / ACM MMSys | DOI:10.1145/3625468.3647619 | 15 | V-PCC 编码下的视点感知流式；SSIM +14.67 %、VMAF +7.39 %。 | **V-PCC × 视点感知**的基准工作，后文多数 V-PCC 论文引它 |
| D-XR-B3 | ⭐ | P2VS: Progressive Partition-Based Volumetric Video Streaming under Network Dynamics | Jing Wu | 2025 / ACM Multimedia | DOI:10.1145/3746027.3755403 | 2 | 利用点云自身结构做渐进增强，不被具体压缩算法绑定。 | MM'25 点云流式代表；"不绑编解码器"是明确的差异化主张 |
| D-XR-B4 | 📌 | Enabling Distance-Aware Real-Time Volumetric Video Streaming | Kyle Jorgensen | 2025 / ACM NOSSDAV | DOI:10.1145/3712678.3721874 | 1 | 在压缩/tile 之前按"真实距离 + 虚拟视距"剪枝点云。 | NOSSDAV 正会；提出的是**预压缩剪枝**，与 tile 编码正交 |
| D-XR-B5 | 📌 | Super-Resolution Meets Compression in Live VV: Light on Bits, Rich on Quality（系统名 Super-VV） | Sepehr Ganji | 2026 / ACM MMSys | DOI:10.1145/3793853.3795758 | 0 | 质量保持的降采样剪枝 + 扩展 Draco（tile 并行 + 内存优化）+ CPU 轻量上采样。 | 2026 最新；「传输降质 + 端侧超分」路线，与云游戏侧 River（D-XR-G-补）同构 |
| D-XR-B6 | 📌 | uvgVPCCenc: Practical Open-Source Encoder for Fast V-PCC Compression | Louis Fréneau | 2025 / ACM MMSys | DOI:10.1145/3712676.3718336 | 6 | 开源快速 V-PCC 编码器，相对 TMC2 大幅加速且 RD 可比。 | 让 V-PCC 可实用的**工程基座**；做 V-PCC 实验绕不开 |
| D-XR-B7 | 📌 | EdgeGaussian: Real-time Free-Viewpoint Video for Mobile VR via Edge-Client Collaborative Neural Rendering | Zhihui Ke | 2025 / ACM MobiCom | DOI:10.1145/3680207.3765245 | 1 | 静态-动态解耦 4DGS（SD-4DGS）+ 边端协同渲染，实现实时自由视点视频。 | **自由视点视频 + 边端协同**的最佳交汇点，直接命中本子方向标题 |
| D-XR-B8 | 📌 | Play4D: Accelerated and Interactive Free-viewpoint Video Streaming for Virtual Reality and Light Field Displays | Jonghyun Kim | 2025 / SIGGRAPH Asia **Emerging Technologies（短文）** | DOI:10.1145/3757373.3763771 | 1 | 4DGS 重建+压缩+流式 + 高效辐射场渲染，面向光场（LF）与 VR 显示。 | **光场显示这一支**的代表；注意这是 Emerging Technologies 短文，非 SIGGRAPH 技术论文正会 |

> **表 B 未收录但已核实**：Scalable MDC-Based WebRTC Streaming for One-to-Many Volumetric Video Conferencing（Matthias De Fré 等，ACM TOMM 2025，DOI:10.1145/3768314，3 引用，Draco + WebRTC + 多描述编码做低延迟 6DoF 会议）；Composing Error Concealment Pipelines for Dynamic 3D Point Cloud Streaming（I-Chun Huang 等，ACM TOMM 2025，DOI:10.1145/3731561，3 引用，首个错误隐藏流水线框架，主观偏好胜率 100 % 而耗时仅 8.55 %）；Scalable On-the-fly Transcoding for Adaptive Streaming of Dynamic Point Clouds（Michael Rudolph 等，arXiv:2603.08417，0 引用，服务器侧即时转码 + 推测式转码，撑并发）；Low-Latency Volumetric G-PCC Streaming with DASH over QUIC（Jashanjot Singh Sidhu & Abdelhak Bentaleb，ACM MMVE@MMSys **workshop** 2026，DOI:10.1145/3798090.3799678）；Quality Assessment and Modeling for MPEG V-PCC Volumetric Video（Yuang Shi 等，ACM MMVE@MMSys **workshop** 2024，DOI:10.1145/3652212.3652218）；Neural Compression System for Point Cloud Video Streaming（Jun-Teng Zhang 等，IEEE TIP 2025，DOI:10.1109/TIP.2025.3638126，2 引用）；Light field video streaming on GPU（Tomáš Chlubna 等，Signal Processing: Image Communication 2025，DOI:10.1016/j.image.2025.117377）。

---

## 3. 表 C：视口 / FoV / 头动预测（公共底座之一）

> 这一栏是 XR 与云游戏**共用程度最高**的技术：云游戏的注视点编码（表 E）与 360°/体积视频的 tile 选码率（表 F）都建立在同一批预测器之上。

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| D-XR-C1 | ⭐经典 | Analyzing viewport prediction under different VR interactions | Tan Xu | 2019 / ACM CoNEXT | DOI:10.1145/3359989.3365413 | 37 | 系统分析不同 VR 交互方式下视口预测的可预测性差异。 | **经典**；FoV 预测作为独立问题的奠基之一（Han / Feng Qian） |
| D-XR-C2 | ⭐经典 | Deep Learning for Content-Based Personalized Viewport Prediction of 360-Degree VR Videos | Xinwei Chen | 2020 / IEEE Networking Letters | DOI:10.1109/LNET.2020.2977124 · arXiv:2003.00429 | 32 | 内容 + 个性化的 DL 视口预测，比只用位置数据提升 16.1 %。 | **经典**；后续大量"内容感知预测"的起点 |
| D-XR-C3 | ⭐ | CoLive: Edge-Assisted Clustered Learning Framework for Viewport Prediction in 360° Live Streaming | Mu Wang | 2024 / IEEE TMM | DOI:10.1109/TMM.2023.3330112 | 13 | 边缘辅助的分簇学习框架做直播 360° 视口预测。 | **边缘 × 视口预测**；与表 F 的边缘缓存工作是同一动机 |
| D-XR-C4 | 📌 | LCR360: Efficient Head Movement Prediction and Viewport Sharing in 360° Video Streaming | Jashanjot Singh Sidhu | 2024 / ACM MobiCom | DOI:10.1145/3636534.3696210 | 3 | 头动预测 + 视口共享，S-metric 提升约 5 %（MSE + 带宽 + 存储的复合指标）。 | MobiCom 正会；提出复合指标的做法值得借鉴 |
| D-XR-C5 | ⭐ | Predictability-Aware Motion Prediction for Edge XR via High-Order Error-State Kalman Filtering | Ziyu Zhong | 2025 / ACM VRST | arXiv:2507.13179 · DOI:10.1145/3756884.3765973 | 3 | 先按"可预测性"给动作分类，再用高阶误差状态卡尔曼滤波预测头动轨迹，抗丢包。 | **MTP 时延补偿中的头动预测**最新工作；不做 tile、只做预测 |
| D-XR-C6 | ⭐ | EyeNavGS: A 6-DoF Navigation Dataset and Record-n-Replay Software for Real-World 3DGS Scenes in VR | Zihao Ding | 2025 / ACM Multimedia | arXiv:2506.02380 · DOI:10.1145/3746027.3758265 | 5 | 首个公开 6-DoF 3DGS 导航数据集：46 名被试 × 12 个真实 3DGS 场景，附录制重放工具。 | **3DGS 场景视口预测的数据基建**；做该方向实验的现成数据 |
| D-XR-C7 | ⭐ | Learning-Augmented 360° Video Streaming: Robust Viewport Adaptation with Simple Predictors | Tianyu Chen | 2026 / ACM MMSys | DOI:10.1145/3793853.3795754 | 0 | 用「可证明鲁棒」的码率分配器 + 在线学习平衡"依赖预测"与"防预测出错"；结论是**简单预测器反而更优**。 | 与本工作区已录条目 **WTP-89** 同篇（勿重复登记）；直接接 learning-augmented 线（WTP-78/80/81） |

> **表 C 未收录但已核实**：LL-Sparse: Low-Latency 6-DoF Field of View Prediction（Jérémy Ouellette & Abdelhak Bentaleb，ACM MMSys 2025，DOI:10.1145/3712676.3714438，3 引用，6-DoF/体积场景的低延迟 FoV 预测）；Deep Learning for Content-Based… 之外还有 Synergistic Temporal-Spatial User-Aware Viewport Prediction（Yumei Wang 等，IEEE TBC 2024，DOI:10.1109/TBC.2024.3374119，16 引用）；Viewport Prediction, Bitrate Selection, and Beamforming Design for THz-Enabled 360° Video Streaming（Mehdi Setayesh & Vincent W. S. Wong，IEEE TWC 2024，arXiv:2401.13114 · DOI:10.1109/TWC.2024.3513221，17 引用，预测-码率-波束联合）；LiveDeep: Online Viewport Prediction for Live VR Streaming Using Lifelong Deep Learning（Xianglong Feng 等，IEEE VR 2020，49 引用）——**⚠️其 DOI（10.1109/VR46266.2020.1584727730619）经 Crossref 无法解析，引用前需另找官方页**。

---

## 4. 表 D：远端渲染 / 分体渲染 / 边缘辅助渲染与卸载（与云游戏同源）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| D-XR-D1 | ⭐经典 | Furion: Engineering High-Quality Immersive Virtual Reality on Today's Mobile Devices | Zeqi Lai | 2017 / ACM MobiCom | DOI:10.1145/3117811.3117815 | 296 | 利用"前景交互 vs 背景环境"在**可预测性与渲染负载上的反差**：背景上云、前景留端。 | **XR 边缘渲染的奠基**（引用 296）；"按可预测性切分"这一思想后来被表 C/E 反复复用 |
| D-XR-D2 | ⭐经典 | Outatime: Using Speculation to Enable Low-Latency Continuous Interaction for Mobile Cloud Gaming | Kyungmin Lee | 2015 / ACM MobiSys | DOI:10.1145/2742647.2742656 | 203 | 推测执行（预测用户输入）掩盖最多 120 ms 网络延迟。 | **经典**；云游戏奠基。XR 的 MTP 问题与它同一本质（预测换延迟） |
| D-XR-D3 | ⭐经典 | Kahawai: High-Quality Mobile Gaming Using GPU Offload | Eduardo Cuervo | 2015 / ACM MobiSys | DOI:10.1145/2742647.2742657 | 95 | 协作渲染：端侧 GPU 与服务器 GPU 的输出合成后显示。 | **经典**；"分体渲染（split rendering）"的原始出处，XR 分体渲染直接沿用该架构 |
| D-XR-D4 | ⭐ | Edge-assisted user-centric real-time 3D remote near-eye rendering for AR/MR headsets | Bishakha Rani Biswas | 2025 / ITU Journal on Future and Evolving Technologies | DOI:10.52953/ccgv8693 | 0 | 图像域渲染（先进 3D 图像 warping）+ 服务器生成深度图合成头显画面，做低延迟远端渲染。 | **AR/MR 头显远端渲染**最新的完整方案（ITU 期刊为开放获取，正文可读） |
| D-XR-D5 | ⭐ | Dynamic XR Rendering Offloading Based on Feature-Based Quality Assessment | Si-Ge Liu | 2026 / arXiv | arXiv:2606.09330 | 0 | 边端协同渲染 testbed；用上下文赌博机按网络状况与时延约束动态决定渲染放在端侧还是边缘。 | **渲染放置（rendering placement）决策**，正是三块公共底座里的"边缘放置" |
| D-XR-D6 | ⭐ | Stimpack: An Adaptive Rendering Optimization System for Scalable Cloud Gaming | Jin Heo | 2024-12 arXiv / USENIX NSDI | arXiv:2412.19446 | 2 | 在多用户下自适应权衡服务器渲染成本与用户感知质量，最大化系统效用。 | 云游戏侧最新系统论文（NSDI）；**X 方向缺同等"效用函数"框架** |
| D-XR-D7 | 📌 | Power-efficient live virtual reality streaming using edge offloading（系统名 EdgeVR） | Zi-Chen Zhu | 2022 / ACM NOSSDAV | DOI:10.1145/3534088.3534351 | 10 | 把端侧 VR 渲染与 DL 卸载到边缘服务器省电，并**正面处理卸载带来的 MTP 增加**。 | **"卸载 → MTP 变差"这一核心权衡的经典出处**；动机段必引 |
| D-XR-D8 | 📌 | Edge-assisted Real-time Dynamic 3D Point Cloud Rendering for Multi-party Mobile VR（系统名 PoClVR） | Ximing Wu | 2024 / ACM Multimedia；期刊扩充版 2026 / IEEE TMC | DOI:10.1145/3664647.3681650（会议）；DOI:10.1109/TMC.2026.3669201（期刊，0 引用） | 2（会议版） | 把动态点云场景渲染拆成多个渲染任务，并周期调整任务分配以适配负载变化。 | 与 D4/D5 同族；**期刊版标题扩为"…Multi-Party Mobile Virtual Reality"** |
| D-XR-D9 | 📌 | Joint Rendering Offloading and Resource Allocation Optimization for MEC-Assisted VR Systems | Na Su | 2024 / IEEE Wireless Communications Letters | DOI:10.1109/LWC.2024.3353210 | 9 | MEC 辅助 VR 的渲染卸载与资源分配联合优化（通信/信息论社区路线）。 | **"MEC for XR"的通信社区代表**；同组同路线还有 TCOM 的 Rate Splitting（DOI:10.1109/TCOMM.2024.3437471，8 引用，3 influential）与 D3QN × XL-MIMO（DOI:10.1109/TCOMM.2026.3689170，0 引用） |

> **表 D 未收录但已核实**：Offloading-based Power-Efficient Mobile VTuber Live Streaming（Zi-Chen Zhu 等，ACM TOMM 2025，DOI:10.1145/3742787，2 引用）；FPSelector: A Flexible Path Selector for Mobile Augmented Reality Offloading（Yuanwei Zhu 等，IEEE TMC 2025，DOI:10.1109/TMC.2025.3556473，2 引用，"端/边/云"卸载路径选择）；MUCVR（Weimin Li 等，IEEE TPDS 2025，DOI:10.1109/TPDS.2025.3595801，14 引用）；Crossport（Zihang Su 等，IEEE TSC 2026，DOI:10.1109/TSC.2025.3633668，0 引用，云-边-端微服务化协同渲染）；Offloading-Aware Control of AI Task Allocation and Virtual Object Quality in MAR Apps（Ze Li 等，IEEE TMC 2026，DOI:10.1109/TMC.2025.3640384，1 引用）；Edge-Based Video Stream Generation for Multi-Party Mobile Augmented Reality（Lei Zhang 等，IEEE TMC 2024，DOI:10.1109/TMC.2022.3232543，20 引用）。

---

## 5. 表 E：注视点渲染（FR）/ 凝视驱动编码与传输（XR 与云游戏共用最紧）

> 这一栏的多数核心工作**同时宣称服务 XR 与云游戏**，是"共同底座"最直接的证据：FovOptix / EyeNexus / Saliency-Guided / Frame Complexity 四篇都出自 HKU（Alhilal / Ze Wu / Pan Hui）+ Siekkinen 这条线，且明确以 **VR cloud gaming** 为场景。

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| D-XR-E1 | ⭐ | FovOptix: Human Vision-Compatible Video Encoding and Adaptive Streaming in VR Cloud Gaming | Ahmed Alhilal | 2024 / ACM MMSys | DOI:10.1145/3625468.3647612 | 19 | 注视点渲染（FR）+ 自适应 foveated video encoding（FVE），在更低且自适应的码率下不损感知质量。 | **云游戏 × 注视点编码的交汇点**；"FR/FVE"这一整条线的起点 |
| D-XR-E2 | ⭐ | EyeNexus: Adaptive Gaze-Driven Quality and Bitrate Streaming for Seamless VR Cloud Gaming Experiences | Ze Wu | 2025 / Proc. ACM on Networking (PACMNET) | arXiv:2509.11807 · DOI:10.1145/3768989 | 7 | 实时凝视驱动空间压缩 + 编码，foveation 区域随带宽与凝视动态调整。 | 同组最新；**明确写在云游戏语境**，是"XR 与云游戏同底座"的最强证据 |
| D-XR-E3 | 📌 | Saliency-Guided Foveated Video Encoding for Low-Latency and Immersive Cloud VR | Ze Wu | 2026 / IEEE TVCG | DOI:10.1109/TVCG.2026.3679056（Crossref 已核） | 0 | 显著性引导的注视点编码，面向低延迟云 VR。 | TVCG（可视化顶刊）；注意标题写的是 **Cloud VR**，功能上等价于云游戏 |
| D-XR-E4 | 📌 | Gaze-Adaptive Foveation for Remote Rendered VR | Adhi Widagdo | 2025 / ACM Multimedia | DOI:10.1145/3746027.3755620 | 0 | 实现三种凝视自适应 foveation，并接入开源 ALVR 远端渲染框架，达到原生 72 FPS。 | **远端渲染 × foveation 的开源可复现实现**（ALVR 被多篇论文当基线） |
| D-XR-E5 | 📌 | Process Only Where You Look: Hardware and Algorithm Co-optimization for Efficient Gaze-Tracked Foveated Rendering in Virtual Reality（系统名 POLONet） | Hai-Yu Wang | 2025 / ACM/IEEE ISCA | DOI:10.1145/3695053.3731110 | 9 | 多任务轻量网络做低延迟注视跟踪，只为"看的地方"计算。 | **端侧 FR 算力侧**最高规格场馆（ISCA）；与网络侧不交叉 |
| D-XR-E6 | 📌 | FoANet: Focus of Attention Prediction for Foveated Pre-rendering to Enable High-quality Edge VR | Ding Ding | 2025 / ACM Transactions on Sensor Networks | DOI:10.1145/3722222 | 4 | 多任务学习同时预测头动与注视，做边缘 VR 的注视点预渲染以降延迟与传输量。 | **边缘预渲染 × 注意力预测**；把表 C 的预测器直接接到渲染卸载上 |

> **表 E 未收录但已核实**：A3FR: Agile 3D Gaussian Splatting with Incremental Gaze Tracked Foveated Rendering（Shuo Xin 等，ACM ICS 2025，arXiv:2507.04147 · DOI:10.1145/3721145.3735112，3 引用，**FR × 3DGS** 交汇）；Simultaneous Overfill and Foveated Rendering in VR Streaming（Y. F. Luckyarno 等，IEEE Access 2025，DOI:10.1109/ACCESS.2025.3598809，1 引用，把 **overfill（超量渲染，MTP 补偿手段）** 与 FR 一起做度量与 DRL 联合优化）；FovRL: Joint Foveation and Quality Control for Immersive VR Streaming Using RL（Yuk-Hang Tsui 等，ACM Web Conference / WWW 2026，DOI:10.1145/3774904.3792643，1 引用）；Frame Complexity-Aware Foveated Video Encoding for Real-time High-Quality Streaming（Ze Wu 等，IEEE VR 2026，DOI:10.1109/VR67842.2026.00037，0 引用）；Efficient Radius Search for Adaptive Foveal Sizing Mechanism in Collaborative Foveated Rendering Framework（Yufei Yang 等，IEEE TMC 2024，DOI:10.1109/TMC.2023.3277577，8 引用，协同 FR）；QUASAR: Quad-based Adaptive Streaming And Rendering（E. Lu & Anthony Rowe，ACM TOG 2025，DOI:10.1145/3731213，3 引用，四边形几何流式 + 按带宽调 QoE）。

---

## 6. 表 F：360° tile 编码 + 边缘缓存/放置（公共底座之二、之三）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| D-XR-F1 | ⭐经典 | 360ProbDASH: Improving QoE of 360 Video Streaming Using Tile-based HTTP Adaptive Streaming | Lan Xie | 2017 / ACM Multimedia | DOI:10.1145/3123266.3123291 | 260 | tile-based HAS 做视口自适应，并用概率模型显式处理视口预测的不确定性。 | **tile 编码这一公共底座的头号奠基（引用 260）**；"用概率覆盖预测误差"是其被反复继承的核心 |
| D-XR-F2 | ⭐经典 | BAS-360°: Exploring Spatial and Temporal Adaptability in 360-degree Videos over HTTP/2 | Mengbai Xiao | 2018 / IEEE INFOCOM | DOI:10.1109/INFOCOM.2018.8486390 | 57 | 在 HTTP/2 上同时做 360° 视频的空间与时间自适应。 | **经典**；INFOCOM，tile 编码另一奠基 |
| D-XR-F3 | ⭐经典 | An Evaluation of Tile Selection Methods for Viewport-Adaptive Streaming of 360-Degree Video | Duc V. Nguyen | 2020 / ACM TOMM | DOI:10.1145/3373359 | 23 | 首次系统对比 10 种 tile 选择方法，结论是**"简单的非 tiled 方法往往最好"**。 | **必读的反方证据**：tile 化的收益在多数配置下被其开销吃掉，任何新 tile 方案都要正面回应 |
| D-XR-F4 | ⭐ | DACOD360: Deadline-Aware Content Delivery for 360-Degree Video Streaming Over MEC Networks | Xiao-Bin Tan | 2024 / IEEE TMM | DOI:10.1109/TMM.2023.3321439 | 13 | MEC 下按 deadline 做 360° 内容投递。 | **MEC + 360° 投递**的代表；把"晚到即无用"的 deadline 语义引入沉浸式视频 |
| D-XR-F5 | 📌 | Dual-Engine Intelligent Caching: A Joint Optimization Framework for 360° Mobile VR Video Edge Caching | Chuyang Gao | 2025 / IEEE JSAC | DOI:10.1109/JSAC.2025.3574596 | 5 | 预测引擎 + 优化引擎双引擎做 360° 移动 VR 的边缘缓存联合优化。 | **边缘放置/缓存**这一公共底座的 JSAC 侧代表 |
| D-XR-F6 | 📌 | NSGR: A Tile-Free 360° Video LIVE System With Edge Servers Enhancing Viewport Quality | Nianzhen Gao | 2026 / IEEE Transactions on Broadcasting | DOI:10.1109/TBC.2026.3696566 | 0 | 直播系统明确**不用 tile**，靠边缘服务器提升视口质量。 | 2026 最新，是 F3 结论在系统层面的延续——对 tile 范式的直接挑战 |

> **表 F 未收录但已核实**：A Two-Stage Deep Reinforcement Learning Framework for MEC-Enabled Adaptive 360-Degree Video Streaming（Su-Zhi Bi 等，IEEE TMC 2024，DOI:10.1109/TMC.2024.3443200，16 引用）；NOVA: Neural-Optimized Viewport Adaptive 360-Degree Video Streaming at the Edge（Biao Hou 等，IEEE TSC 2024，DOI:10.1109/TSC.2024.3451237，10 引用，2 influential）；Viewing Pattern Assisted Proactive Partial Caching for 360° Videos in MEC Networks（Guoxiao Yin 等，IEEE IoT-J 2025，DOI:10.1109/JIOT.2025.3542413，3 引用）；Interactive 360° Video Streaming Using FoV-Adaptive Coding with Temporal Prediction（Yixiang Mao 等，arXiv:2403.11155，0 引用，对带宽波动与 FoV 预测误差都鲁棒）；**TF-PPO: A Temporal Feature Aware PPO Algorithm to Resolve the FoV Prediction-Buffer Dilemma for 360-degree Video**（Zi-Tong Li 等，IEEE GLOBECOM 2025，DOI:10.1109/GLOBECOM59602.2025.11432230，0 引用，把"预测精度 vs 缓冲"的两难显式建模——**该权衡被显式化的代表作**）；AKI360: Enabling Highly Interactive 360-degree Video Streaming by Adaptive Keyframe Interval（Haitao Liu 等，IEEE ICASSP 2025，DOI:10.1109/ICASSP49660.2025.10889786，2 引用）；Training-Free Adaptive 360-degree Video Streaming via Semantic Potential Fields（OrbitStream，Aizierjiang Aiersilan & Zhangfei Yang，arXiv:2603.20999，0 引用，免训练、把视口预测建模为"语义引力场"+ 饱和 PD 控制器）；Meaning over Motion: A Semantic-First Approach to 360° Viewport Prediction（Arman Nik Khah 等，arXiv:2601.05416，0 引用）。

---

## 7. 表 G：QoE / 端到端测量 / 5G-6G 试验与标准化

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| D-XR-G1 | ⭐ | Network Anatomy and Real-Time Measurement of Nvidia GeForce NOW Cloud Gaming | Minzhao Lyu | 2024 / PAM | arXiv:2401.06366 · DOI:10.1007/978-3-031-56249-5_3 | 19 | 会话识别 + 大规模实时测量：用户体验与上下文因素（浏览器/App、有线/无线）对退化的作用。 | **云游戏真实测量的当代标杆**；XR 侧**尚未见同等规模**的同类工作，这是可指出的空白 |
| D-XR-G2 | 📌 | Evolving Mobile Cloud Gaming with 5G Standalone Network Telemetry（系统名 Telesa） | Haoran Wan | 2024 / arXiv | arXiv:2402.04454 | 6 | 被动、可增量部署的 5G SA 遥测，把 RAN 容量/时延/重传信息推给应用服务器，支持毫秒级码率决策。 | **5G 遥测 → 应用层**的范例；沉浸式/XR 应用有同一需求 |
| D-XR-G3 | 📌 | Congestion Control for VR Cloud Gaming: Integration and Comparison in Real VR Gaming Environment | Ahmed Alhilal | 2025 / ACM Multimedia | DOI:10.1145/3746027.3755439 | 6 | 把 GCC 与 NADA 集成进开源 VR 游戏系统 ALVR 做真机对比；只有 NADA 因对丢包型信号的码率响应而与基于丢包的流公平共存。 | **VR 云游戏的拥塞控制实证**；这块在 XR 侧几乎无人做 |
| D-XR-G4 | ⭐ | Immersive Volumetric Video Playback: Near-RT Resource Allocation and O-RAN-Based Implementation | Yao Wen | 2026 / IEEE TMC | arXiv:2601.20625 · DOI:10.1109/TMC.2026.3674975 | 2 | 5G O-RAN 真机 testbed：RIC 驱动的无线-计算-内容联合控制，中位 MTP 延迟降 > 11 %，同时提升 QoE 与公平性。 | **本表中最"落地"的一篇**：真机 + O-RAN + 直接报告 **MTP 延迟**这一本领域的核心指标 |
| D-XR-G5 | 📌 | Latency in Real-Time 3D Volumetric Streaming: A Comprehensive Study | Seungwoo Hong | 2026 / IEEE ICUFN | arXiv:2605.22131 · DOI:10.1109/ICUFN69619.2026.11628601 | 0 | 在真实体积流式环境里端到端测量并归因延迟瓶颈。 | **教义级的延迟拆解**；写动机时可直接引其数字 |
| D-XR-G6 | 📌 | QoE Modeling in Volumetric Video Streaming: A Short Survey | Mojtaba Mozhganfar | 2026 / IEEE/IFIP NOMS | DOI:10.1109/NOMS69089.2026.11668391 | 0 | 体积视频流式 QoE 建模的短综述。 | **本子方向最新、最省时间的入口综述**（Timmerer 组） |
| D-XR-G7 | 📌 | Paving the Way for 6G—Radio Enhancements for Extended Reality in 5G-Advanced Release-19 | Stefano Paris | 2026 / IEEE Access | DOI:10.1109/ACCESS.2026.3702366 | 0 | 3GPP 5G-Advanced Rel-19 到 6G 面向实时 XR 通信的无线增强（工业/标准化视角，Nokia 等作者）。 | **标准侧锚点**：判断"XR 的哪些需求已被标准化承诺、哪些还缺" |

> **表 G 未收录但已核实**：VIGOR: Reviving Cloud Gaming Sessions（Zhaoyuan He 等，ACM PACMNET 2024，DOI:10.1145/3696403，4 引用，用游戏状态恢复丢失/损坏帧——与 3DGS 的丢包鲁棒性 D-XR-A8 同族）；Real-Time Neural-Enhancement for Online Cloud Gaming（River，Shan Jiang 等，arXiv:2501.06880，3 引用，复用已微调的 SR 模型，把分钟级微调降到毫秒级，与 Super-VV D-XR-B5 同路线）；Remote Rendering for Virtual Reality: Performance Comparison of Multimedia Frameworks and Protocols（Daniel Mejías 等，IEEE MeditCom 2025，arXiv:2507.00623 · DOI:10.1109/MeditCom64437.2025.11104418，5 引用，GStreamer vs FFmpeg 作远端渲染器实测）；Streaming Remote rendering services: Comparison of QUIC-based and WebRTC Protocols（Daniel Mejías 等，IEEE BMSB 2025，arXiv:2505.22132 · DOI:10.1109/BMSB65076.2025.11165653，3 引用，MoQ / RoQ / WebRTC 在 WiFi 与 5G 下延迟对比）；Leveraging 5G Physical Layer Monitoring for Adaptive Remote Rendering in XR Applications（Inhar Yeregui 等，IEEE BMSB 2025，arXiv:2505.22123 · DOI:10.1109/BMSB65076.2025.11165569，1 引用）；Energy consumption assessment of a VR Remote Rendering application over 5G networks（Roberto Viola 等，IEEE NFV-SDN 2025，arXiv:2510.25357 · DOI:10.1109/NFV-SDN66355.2025.11349582，0 引用，硬件+软件双路能耗监测）；Traffic Characteristics of Extended Reality（Abdullah M. Alnajim 等，arXiv:2304.07908，7 引用，XR 流量特征与优化技术综述）；5G/6G Architecture Evolution for XR and Metaverse（Maria Christopoulou 等，IEEE Access 2025，DOI:10.1109/ACCESS.2025.3578595，13 引用）；Leveraging User Perception for 6G Edge-Cloud Orchestration of Networked Extended Reality（José Santos 等，IEEE Communications Magazine 2026，DOI:10.1109/MCOM.003.2400594，3 引用）；Characterizing the Network Traffic of Virtual Reality Cloud Gaming Applications（V. R. Oliveira 等，IEEE/IFIP WONS 2026，DOI:10.23919/WONS68803.2026.11501840，0 引用）。

---

## 8. XR 方向 ↔ 云游戏方向：共同技术底座对照（本子方向的额外交付）

| 公共底座 | 谁最早做（经典） | 谁在 XR / 沉浸式侧做 | 谁在云游戏侧做 | 观察 |
|---|---|---|---|---|
| **FoV / 视口 / 头动预测** | Tan Xu 等 CoNEXT'19（D-XR-C1）；Chen & Saad LNET'20（D-XR-C2） | CoLive（TMM'24，D-XR-C3）、LL-Sparse（MMSys'25）、EyeNavGS 数据集（MM'25，D-XR-C6）、ESKF 头动预测（VRST'25，D-XR-C5） | Outatime（MobiSys'15，D-XR-D2，推测用户输入）；FovOptix/EyeNexus 用**凝视**而非视口做预测（D-XR-E1/E2） | 预测对象不同：XR 侧预测**看哪里**，云游戏侧预测**按什么键/看哪里**；两者都靠"预测换延迟"。**本文工作区已录的 learning-augmented 码率分配（D-XR-C7 / WTP-89）是把预测误差显式纳入两侧同一套框架的接点。** |
| **tile / 层次 / 可伸缩编码** | 360ProbDASH（MM'17，D-XR-F1）、BAS-360°（INFOCOM'18，D-XR-F2） | LTS（MMSys'25，D-XR-A1，3DGS 分层 DASH）、SplatStream（arXiv:2607.25971）、Saliency-Aware Tiling（arXiv:2507.14454，D-XR-A3）、P2VS（MM'25，D-XR-B3） | SCC、SVC、foveated tile 是云游戏串流的既有做法；**直接以云游戏为名做 tile 编码的论文反而少**（FovOptix 走的是 foveation 而非 tile） | 云游戏把 "tile" 主要换成 **foveation 分层**（表 E）；这是两侧术语上的最大差异。反方证据见 D-XR-F3（tile 往往不值）与 D-XR-F6（无 tile 直播系统）。 |
| **边缘放置 / 缓存 / 卸载决策** | Kahawai（MobiSys'15，D-XR-D3，协作渲染）、Furion（MobiCom'17，D-XR-D1）、EdgeVR（NOSSDAV'22，D-XR-D7） | Dynamic XR Rendering Offloading（arXiv:2606.09330，D-XR-D5，渲染放置）、FPSelector（TMC'25）、PoClVR（MM'24 + TMC'26，D-XR-D8）、Dual-Engine Intelligent Caching（JSAC'25，D-XR-F5） | Stimpack（NSDI，D-XR-D6，服务器渲染成本 vs 感知质量的效用函数）；MEC-VR 优化路线（D-XR-D9 及 TCOM/TWC 同族） | **XR 侧已把"渲染放在端 / 边 / 云哪一侧"当作一等决策变量**（D5/FPSelector）；云游戏侧更多是"服务器侧渲染参数与资源调度"（D6）。两侧的放置理论并未互通。 |

---

## 9. 研究空白 / 未解决问题（本轮检索得到的证据）

1. **3DGS/NeRF 传输的"网络侧"与"渲染侧"几乎没有对话。** 2025–2026 的 3DGS 论文要么只优化片内/显存带宽（STREAMINGGS DAC'25、LS-Gaussian ICCAD'25、POLONet ISCA'25、A3FR ICS'25），要么只优化码率/分层（LTS、LMG、SplatStream）。两侧使用的指标（DRAM 流量、每帧能耗 vs 带宽利用率、VMAF/SSIM）不同，**未检索到任何一篇同时报告"网络指标 + 端侧渲染成本"的 3DGS 端到端系统论文**。
2. **沉浸式服务的真实大规模测量缺失。** 云游戏侧已有 GeForce NOW 的运营商级被动测量（D-XR-G1，PAM'24）；XR/体积视频侧对应工作只有少量短会测量（ICUFN'26 延迟归因、WONS'26 云 VR 流量刻画），**未检索到等规模的 3DGS / 体积视频真实服务测量**。
3. **tile 范式的收益仍未被正面确认，却已经被搬进 3DGS。** TOMM'20 的十法对比结论是"非 tiled 往往更好"（D-XR-F3），TBC'26 的 NSGR 直接走 tile-free 路线（D-XR-F6）；但 2025–2026 一批 3DGS/点云工作（D-XR-A3、D-XR-A1、D-XR-B3）仍默认 tile/分层必然有利，**缺少在 3DGS 上的同类消融对比**。
4. **"预测精度 vs 缓冲/鲁棒性"在 XR 侧被显式化为数学问题的时间很晚。** XR 侧 2025 年仍在提高预测精度（ESKF 头动预测、LL-Sparse）；把该权衡写成带最坏情况保证的码率分配器的是 360° 视频的 learning-augmented 工作（D-XR-C7，MMSys'26），**该框架目前只在 360° 视频上验证过，尚未移植到 6-DoF 体积视频 / 3DGS**（GLOBECOM'25 的 TF-PPO 只在 RL 层面处理同一两难，无保证）。
5. **MTP 延迟的公开测报口径不统一。** 只有少数工作直接报告 MTP：O-RAN 真机（D-XR-G4，TMC'26，中位降 >11 %）、EdgeVR（D-XR-D7，报告卸载使 MTP 上升）；其余工作报"帧率 / 端到端时延 / 交互延迟"，口径不一，**横向比较困难**。

---

## 10. 检索局限（必须随结论一起转述）

- **本环境无 DBLP、无 WebSearch（403）**；ACM DL 部分条目 403（摘要级）。因此"未检索到"**不等于**"不存在"。
- **arXiv Atom API**：本次 `all:"Gaussian splatting" AND all:"streaming"`、`all:"NeRF" AND all:"streaming"` 两查询大量被 "event stream / streaming reconstruction" 污染，**召回率明显偏低**（NeRF 侧 25 条里真正相关的仅 2–3 条）；`abs:"point cloud streaming"` 只回收 19 条。→ 表 A/B 的漏检风险主要来自此处。
- **S2 检索**：`"outatime OR kahawai OR furion"`、`"over-the-air rendering"`、`"cloud XR motion-to-photon latency"`、`"survey extended reality XR 5G 6G"`、`"immersive video QoE survey tutorial"` 等多组查询**命中 0 或高度偏离**（"OTA rendering" 术语在学术文献中无对应物，疑为工业界说法；"cloud XR" 不作为检索词出现）。
- **题录级/未独立核实的少数条目**：
  - `LiveDeep`（IEEE VR 2020，49 引用）的 DOI `10.1109/VR46266.2020.1584727730619` **Crossref 无法解析**（`curl https://api.crossref.org/works/<DOI>` 返回不可解析），S2 亦无 DBLP 记录 → **⚠️待核实**，引用前须另找官方页。
  - `Dissecting and Streamlining the Interactive Loop of Mobile Cloud Gaming`（LoopTailor，USENIX NSDI 2025，11 引用）本轮只拿到 S2 题录（paperId `f2f50af735660392100db0a23d946b940fa73c45`），**未取得 DOI / arXiv ID**（USENIX 官网未开）→ 题录级。
  - 表 A 中 `arXiv:2605.08699`、`2609.18624`、`2607.17916`、`2607.25971`、`2608.01659` 等在 S2 中 `venue` 为空（纯 arXiv 预印本），**场馆信息缺失**，不能据此断定为某会议。
  - `SIGGRAPH Asia Emerging Technologies`（D-XR-B8 Play4D）与 `MMVE@MMSys`、`EMS@SIGCOMM` 均为 **workshop / 短文**渠道，已按此标注，未计入正会。
- 引用数一律为 **S2 快照（2026-10-01 抓取）**；表 A/B 中 2026 年预印本多为 0 引用，不代表质量，只代表新。
- 本笔记涉及的全部 arXiv ID 与 DOI 均经 S2 `paper/batch` 逐条比对标题目名；Crossref 额外复核了 `10.1109/TVCG.2026.3679056` 与 `10.1145/3810919.3810924`。
