# 子方向 E：面向游戏/交互视频的编解码、感知质量与生成式方法

> 原始笔记（raw）。检索日期 **2026-10-01**。检索范围：2024–2026（优先 2025–2026），经典奠基工作少量收录并标注「经典」。
> 所有 arXiv ID 均经 `export.arxiv.org` 的 `id_list` **批量逐字核对标题**；所有 DOI 均经 **Crossref `/works/<doi>`** 核对（或明确标注仅 S2 题录级）。
> 引用数为 **Semantic Scholar 快照值（2026-10-01 当日）**，新论文普遍滞后甚至为 0，不作为质量判断依据。

---

## 0. 子方向总述

这个子方向回答的是一个非常具体的问题：**在同一条带宽上，画面能有多好**。它夹在传输层（子方向 A–D 关心的调度、预测、在网计算）和终端渲染之间，是"钱花在哪"的直接决定层——云游戏平台的带宽占运营成本 30–60%（SAIL, arXiv:2607.11231），而一旦跨过"感知无损"阈值，再加码率几乎买不到可见的画质提升。

近两年最大的变化有三条：

1. **学习式视频编码（NVC）从"追平 VVC"走到"可实时"**。DCVC 系列（DCVC → DCVC-DC → DCVC-FM → DCVC-RT）已经把 1080p 编/解码推到 125.2/112.8 fps，且比 H.266/VTM 平均省 21% 码率（DCVC-RT, CVPR 2025）。更关键的是它指出真正的瓶颈不是算力而是**非计算操作开销**（内存 I/O、函数调用次数）——这把 NVC 的工程化问题从"模型太大"改写成"系统没设计好"。

2. **生成式/扩散式编解码成为独立的第二波**，主打超低码率下的感知质量（0.01 bpp 以下仍"好看"）。但这一波**离云游戏/实时传输还很远**：目前最好的实时方案要靠 8 张消费级 GPU 并行（ReGenVC）或数据中心 H 系列 GPU（DiffVC-RT）才勉强进帧预算，而传统解码器是一块 ASIC。

3. **质量评价层正在被自己的工具反噬**。VMAF 已是行业默认货币，但 (a) 无参考场景要另造 NR-VMAF，(b) 神经/生成式编解码器的失真模式与 VMAF 假设不同——已有主观实验显示 VMAF 在被测 NVC 上未必有效（PCS 2025），(c) 游戏内容是 VMAF 未针对训练的域，需要专门数据集（GamingVideoSET → GameScope）。

---

## A. 学习式/神经视频编解码（NVC）主线与综述

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| A1 | 经典 | Deep Contextual Video Compression (DCVC) | Jiahao Li | 2021 / NeurIPS | arXiv:2109.15047 | 517 | 把预测编码范式换成**条件编码**：用高维特征域上下文同时喂编解码器。 | 现代 NVC 主线的起点；后续 DCVC-TCM/DC/ FM/RT 全部是它的直系后代。 |
| A2 | 经典 | Neural Video Compression with Diverse Contexts (DCVC-DC) | Jiahao Li | 2023 / CVPR | arXiv:2302.14402 | 354 | 组内偏移多样性 + 四叉树 latent 划分，扩大上下文多样性。 | 首个在低延迟配置下稳定压过同代传统编码器的 NVC，是后续所有对比的"传统 NVC 基线"。 |
| A3 | ⭐ | Neural Video Compression with Feature Modulation (DCVC-FM) | Jiahao Li | 2024 / CVPR | arXiv:2402.17414 · DOI:10.1109/CVPR52733.2024.02466 | 239 | 用特征调制解两个核心问题；比上一代 SOTA NVC 省 29.7% 码率、MACs 少 16%。 | 目前被第三方基准（PCS 2025 / VCIP 2024）当作"学习式一侧的代表"来跟 ECM 对比。 |
| A4 | ⭐ | Towards Practical Real-Time Neural Video Compression (DCVC-RT) | Zhaoyang Jia | 2025 / CVPR | arXiv:2502.20762 · DOI:10.1109/CVPR52734.2025.01170 | 149 | 1080p 编/解码 125.2/112.8 fps，比 H.266/VTM 平均省 21% 码率；识别出**运行开销（内存 I/O、调用次数）而非算力**才是速度瓶颈。 | 本方向 2025 年最重要的一篇：把 NVC 从"能不能压"推进到"能不能实时"。Microsoft 维护（github.com/microsoft/DCVC）。**与云游戏/互动视频的实时约束直接相邻**。 |
| A5 | ⭐综述 | Emerging Advances in Learned Video Compression: Models, Systems and Beyond | Chuanmin Jia | 2024 / IJCAI | arXiv:2504.21445 · DOI:10.24963/ijcai.2024/1165 | 12 | 覆盖单向/双向预测 NVC 全谱，**并把系统设计与硬件实现挑战单列**，含标准化进展。 | 目前覆盖面最"系统侧"的中文团队综述，适合作为入门框架（arXiv 版 2025-04 挂出）。 |
| A6 | ⭐综述 | End-to-End Neural Video Compression: A Review | Jiovana S. Gomes | 2025 / IEEE Open Journal of Circuits and Systems | DOI:10.1109/OJCAS.2025.3559774 | 9 | NVC 压缩效率已**与最新混合编码器 VVC 相当**，但要实用仍需硬件友好化以在移动/能耗受限设备上快速推理。 | 结论与 A4 相互印证：效率不再是主要障碍，**部署成本才是**。 |
| A7 | ⭐综述 | End-to-end learned video compression: A comprehensive review | Huanjie He | 2026 / Neurocomputing | DOI:10.1016/j.neucom.2026.133839 | 1 | 最新一篇端到端学习式视频压缩系统综述（2026 年 9 月）。 | 与 A5/A6 三足鼎立，可作为"最新版文献地图"。引用数低是因为太新。 |

> 备注：INR（隐式神经表示）路线另有独立一支（NVRC, NeurIPS 2024, arXiv:2409.07414；GIViC, ICCV 2025, arXiv:2503.19604 号称首个在 RA 配置下超过 VTM 的 INR 编解码器），因与实时传输距离较远，本轮未展开成行。

---

## B. 生成式 / 扩散式视频编解码（2024–2026 这一波，单独成组）

**这一组在解决什么**：在 <0.05 bpp 甚至 <0.01 bpp 的"极端码率"下，传统编码器会碎成块效应；生成式解码器用视频/图像生成先验"补"出细节，把优化目标从 PSNR 换成 LPIPS/DISTS/FID 这类感知指标。

**组内演进脉络**：单帧图像先验 → 时序条件化（抑制 flicker）→ 一步/少步采样（降延迟）→ 视频原生 DiT 先验 → 与系统并行化结合。

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| B1 | 📌 | Extreme Video Compression with Pre-trained Diffusion Models | Bohan Li | 2024 / arXiv（另有 WCSP 2024 会议版） | arXiv:2402.08934 | 11 | 把预训练扩散模型的预测能力放在**解码端**，做极端压缩。 | 这一波的起点之一；确立了"码率换生成先验"的基本盘。 |
| B2 | 📌 | M3-CVC: Controllable Video Compression with Multimodal Generative Models | Rui Wan | 2024 / ICASSP 2025 | arXiv:2411.15798 · DOI:10.1109/ICASSP49660.2025.10888491 | 12 | 多模态生成模型 + 可控码率，超低码率下优于 VVC，保住语义与感知保真。 | **解码成本的"反面教材"**：第三方分析称其解码需 RTX 3090，一条序列 142.5 s，而 VVC 在 Xeon 上只要 23.1 s（见 §B-补 工程化距离，⚠️ 数据来自第三方博客，非论文自报）。 |
| B3 | ⭐ | Diffusion-based Perceptual Neural Video Compression with Temporal Diffusion Information Reuse (DiffVC) | Wenzhuo Ma | 2025 / ACM TOMM | arXiv:2501.13528 · DOI:10.1145/3761815 | 30 | 把扩散基础模型嵌进视频条件编码范式，复用已解码帧与重建的时序上下文。 | 这一波里"码率高、但把时序一致性真做进去了"的代表；后续 DiffVC-OSD/RT/ONE 都出自同组。 |
| B4 | ⭐ | DiffVC-RT: Towards Practical Real-Time Diffusion-based Perceptual Neural Video Compression | Wenzhuo Ma | 2026 / arXiv | arXiv:2601.20564 | 3 | 首个面向实时的扩散式感知 NVC：**720p 编/解码 206/30 fps**（NVIDIA H800），LPIPS 口径比 VTM-17.0 省 80.1% 码率。 | 生成式编解码"最接近可用"的一个点。注意：720p、30 fps 解码、**数据中心级 GPU**——三条约束叠加后离云游戏产线仍有距离。 |
| B5 | 📌 | Generative Neural Video Compression via Video Diffusion Prior (GNVC-VD) | Qi Mao | 2025 / arXiv | arXiv:2512.05016 | 18 | 首个基于 DiT 的生成式 NVC：从已解码时空 latent 出发学习修正项，而非从纯高斯噪声去噪，解决逐帧图像先验导致的**闪烁**。 | 指向"视频原生先验 > 图像先验"这一共识；0.01 bpp 以下仍保持时序一致。 |
| B6 | 📌 | Generative Latent Video Compression (GLVC) | Zongyu Guo | 2025 / arXiv（ICLR 2026 投稿版） | arXiv:2510.09987 | 10 | 用预训练连续 tokenizer 把帧投到感知对齐 latent 空间，把感知约束从码率优化中解耦。 | **算力账本最清楚的一篇**：100.4M 参数，单 A100 上 1080p 编/解码 194/306 ms（5/3 fps）、720p 70/112 ms（14/9 fps）。 |
| B7 | 📌 | OSCAR: One-Step Diffusion Codec Across Multiple Bit-rates | Jinpei Guo | 2025 / NeurIPS | arXiv:2505.16091 | 22 | 观点：压缩后的 latent 已保留丰富结构，**一步去噪足够**，多步采样对生成式压缩并非必要。 | "少步化"的理论依据；是生成式编解码能否降延迟的关键论证。 |
| B8 | ⭐ | Generative Latent Coding for Ultra-Low Bitrate Image and Video Compression (GLC) | Linfeng Qi | 2025 / IEEE TCSVT | arXiv:2505.16177 · DOI:10.1109/TCSVT.2025.3571944 | 35 | 在（超）低码率区间用类别化超先验 + 生成式 latent 编码，图像与视频两版。 | 与 B7 互补：不追求一步采样，而是把熵模型做成感知友好。IEEE 正刊，属"生成式压缩"里较稳的一支。 |
| B9 | ⭐ | ReGenVC: End-to-End Real-Time Generative Video Coding at Ultra-Low Bitrate | Zheyuan Zhang | 2026 / arXiv | arXiv:2607.28144 | 0 | 说话头视频：77 帧序列压到约 26 kB（x264/x265 需 250–280 kB）；用**8 卡节点** + 四步蒸馏扩散 Transformer 达到 24 fps 实时浏览器直播。 | **本方向工程化距离的核心证据**（见 §C）。作者自陈："部署这类编解码器的核心障碍就是解码延迟"。 |
| B10 | ⭐ | CoD-Lite: Real-Time Diffusion-Based Generative Image Compression | Zhaoyang Jia | 2026 / arXiv | arXiv:2604.12525 | 0 | 一步像素域卷积扩散解码：28M 编码器 + 52M 解码器，**单 A100 上 1080p 编码 60 fps / 解码 42 fps**。 | 与 B9 形成鲜明对照：**图像域已经能实时，视频域还差一个量级**——这本身就是一条重要结论（同一作者团队，Microsoft GenCodec）。 |
| B11 | ⭐ | PULSE: Unlocking Practical Image Compression on Single-Thread CPU | Zhaoyang Jia | 2026 / arXiv | arXiv:2609.18602 | 0 | 极低复杂度接收端：base 模型 5.2 kMAC/pixel，整数线性 CDF 预测 + CPU rANS，**单线程 CPU 解码**，带移动 NPU 部署工具。 | 直接回答了"生成式/学习式编解码怎么落到消费端"：不靠 GPU，靠把解码端复杂度压到 ASIC/NPU 可承载。与 B10 同队。 |
| B12 | ⭐ | Gen2-VC: Unlocking Generative Priors for Video Compression | Yinhuan Huang | 2026 / arXiv | arXiv:2609.34725 | 0 | 用预训练视频先验**增强现有传统/学习式编解码器的输出**，比特流与参考帧更新流程完全不变。 | 本组里"工程上最可能先落地"的形态：不替换标准编解码链路，只在解码后加一层生成式后处理。**与客户端超分（§D）思路同源**。 |

### §B-补：生成式/扩散式视频编解码离云游戏与实时传输还有多远

**结论：图像域已实时，视频域尚未；视频域里"能实时"的方案要么降分辨率、要么堆 8 张 GPU、要么用数据中心卡。**

具体证据（均为论文自报，除注明外）：

| 系统 | 分辨率 | 编码/解码速度 | 硬件 | 出处 |
|---|---|---|---|---|
| DCVC-RT（非生成式 NVC 对照） | 1080p | 125.2 / **112.8** fps | 单 GPU | arXiv:2502.20762 |
| DiffVC-RT | 720p | 206 / **30** fps | NVIDIA **H800**（数据中心） | arXiv:2601.20564 |
| ReGenVC | 说话头，25 帧窗口 | 24 fps（972 ms/窗口，预算 1000 ms） | **8 卡**节点（消费级 GPU），CPU 跑编码器 | arXiv:2607.28144 |
| GLVC | 1080p | 194 / **306 ms/帧**（≈5/3 fps） | 单 **A100**（100.4M 参数） | arXiv:2510.09987（ICLR'26 投稿） |
| CoD-Lite（**图像**域） | 1080p | 60 / **42** fps | 单 A100，一步扩散 | arXiv:2604.12525 |

ReGenVC 论文里的逐 kernel 性能剖析（RTX 5090D, bfloat16）更能说明问题：**单次 transformer 前向 368.8 ms，4 步采样器本身就是整个帧预算；VAE 解码 957 ms、编码 564 ms**；串行总工作量 1475 ms，靠 8 卡统一序列并行（Ulysses/Ring）+ 空间切分 VAE + 三级流水线才压回实时。作者原话：这些是"任何扩散式编解码器都必须付的固定成本"。

⚠️ 第三方分析（Streaming Learning Center 对 M3-CVC 的评测）称 M3-CVC 在 RTX 3090 上解码一条序列需 142.5 s（VVC 在 Xeon Gold 6230 上 23.1 s），并判断"适配消费级硬件需要 6–8 年或更久"。**这是行业分析博客、非同行评议，也未在论文原文中直接给出该数字**，仅作旁证。

**对云游戏的直接含义**：云游戏的解码端是**客户端**（手机/电视/轻薄本），那里有专用解码 ASIC 和越来越强的 NPU，但没有 8 卡 GPU 节点。所以生成式编解码在云游戏里的现实形态，大概率不是"端到端生成式编解码器"，而是 **B12 那种"标准码流 + 客户端生成式后处理/超分"**——这与 §D 的技术栈正好重合。反过来说，**服务端**（编码侧）反而更有希望先用上生成式/学习式方法，因为编码可以批量、可以离线、可以有 GPU 池。

---

## C. 感知质量评价指标（含游戏/渲染内容专用）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| C1 | ⭐经典/综述 | Perceptual Video Quality Assessment: A Survey | Xiongkuo Min | 2024 / Science China Information Sciences | arXiv:2402.03413 · DOI:10.1007/s11432-024-4133-3 | 210 | 系统梳理 VQA 的经典工作与近期进展（含 UGC/VR/AIGC 分支）。 | 引用数最高的一篇中文团队 VQA 综述，作为本组的"总入口"。 |
| C2 | 经典 | VMAF reproducibility: Validating a perceptual practical video quality metric | R. Rassool | 2017 / IEEE BMSB | DOI:10.1109/BMSB.2017.7986143 | 209 | 独立复现验证 VMAF 的感知有效性。 | VMAF 从"Netflix 内部指标"变成"行业公共货币"的合法性基石之一。 |
| C3 | ⭐ | No-Reference VMAF: A Deep Neural Network-Based Approach to Blind Video Quality Assessment | Axel De Decker | 2024 / IEEE Transactions on Broadcasting | DOI:10.1109/TBC.2024.3399479 | 7 | 用 DNN 做无参考 VMAF 预测，摆脱对参考序列的依赖。 | 云游戏/直播的**服务端实时监控**只能拿到码流和重建帧，无参考是刚需；与 C4（Herb）的"VMAF 对 NVC 未必有效"共同构成"VMAF 不够用"的证据链。 |
| C4 | ⭐ | Evaluating Video Quality Metrics for Neural and Traditional Codecs using 4K/UHD-1 Videos | Benjamin Herb | 2025 / Picture Coding Symposium | arXiv:2511.00969 · DOI:10.1109/PCS65673.2025.11417577 | 3 | 用 AV1/VVC 与 DCVC-FM/DCVC-RT 做主观实验后发现：VMAF 与 AVQBits\|H0\|f 皮尔逊相关强，而 **PSNR 在序列内排序相关性最高**；无参考里 FasterVQA 最好。 | **本组最关键的一篇**：说明现行质量指标在神经编解码器上并不可靠。做"学习式编码选型/码率阶梯"必须先解决这个测量问题，否则优化目标本身就是错的。 |
| C5 | 经典 | GamingVideoSET: A Dataset for Gaming Video Streaming Applications | Nabajeet Barman | 2018 / NetGames（ACM SIGCOMM *Workshop*，非正会） | DOI:10.1109/NetGames.2018.8463362 | 69 | 游戏视频流媒体的主观质量数据集奠基工作。 | 游戏内容域 VQA 的起点；后续 GameScope、nofu 等都在它的问题设定上做扩展。 |
| C6 | ⭐ | GameScope: A Multi-Attribute, Multi-Codec Benchmark Dataset for Gaming Video Quality Assessment | Rajesh Sureddi | 2026 / arXiv（S2 标注会议存疑；⚠️待核实为 ICIP 2026） | arXiv:2605.01272 | 0 | 目前**最大**的游戏视频质量数据集，同时覆盖 UGC 与 PGC，且明确面向**跨编解码器**一致性。 | 直接对准 C4 提出的问题：要跨 codec 可比的质量模型，就需要跨 codec 标注的数据。与云游戏平台选型直接相关。 |

---

## D. 客户端超分 / 神经增强传输（client-side SR）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| D1 | 经典 | Neural Adaptive Content-aware Internet Video Delivery (NAS) | H. Yeo | 2018 / USENIX OSDI | 无 DOI（S2 题录） | 244 | 用客户端 DNN 把"传高码率"换成"传低分辨率 + 客户端超分"，画质不再线性依赖带宽。 | client-side SR 这条线的奠基；今天所有"传 1080p、端侧补到 4K"的商业方案都是它的后代。 |
| D2 | ⭐ | GameStreamSR: Enabling Neural-Augmented Game Streaming on Commodity Mobile Platforms | Sandeepa Bhuyan | 2024 / ISCA | DOI:10.1109/ISCA59077.2024.00097 | 10 | 在**商用移动平台**上做神经增强的游戏流媒体，给出真实的端侧算力/能耗预算。 | 把 D1 的思路落到手机（云游戏最主流的客户端形态）。与 E 组注视点方向天然可组合。 |
| D3 | ⭐ | Compressed Domain Prior-Guided Video Super-Resolution for Cloud Gaming Content (CPGSR) | Qizhe Wang | 2025 / IEEE DCC | arXiv:2501.01773 · DOI:10.1109/DCC62719.2025.00016 | 3 | 轻量网络利用**压缩域先验**（编码信息）引导游戏内容超分，配分区聚焦频率损失。 | 指出"游戏内容超分"与自然视频超分不同（纹理锐、运动矢量可得）。与 J 组的"渲染感知编码"合起来就是"用编码器已有的信息帮解码器"。 |
| D4 | ⭐ | FlashVSR: Towards Real-Time Diffusion-Based Streaming Video Super-Resolution | Junhao Zhuang | 2025 / arXiv | arXiv:2510.12747 | 41 | 首个面向实时的**一步扩散流式** VSR：单 A100 上 768×1408 约 17 FPS。 | 生成的"客户端超分可行版本"。注意仍是 A100 + 17 FPS——端侧移植尚需量化/蒸馏（参见 B11 PULSE 的思路）。 |
| D5 | 📌 | Energy-aware bitrate ladder for VVC streaming with client-side super-resolution (E2-Stream) | Amritha Premkumar | 2026 / Frontiers in Signal Processing | DOI:10.3389/frsip.2026.1802483 | 0 | 把 VVC 编码、多模型 VSR 增强、客户端解码与增强的**能耗**一起纳入码率阶梯构造。 | 唯一一篇把"客户端超分算力/能耗"当作码率阶梯一等约束的工作。与 F 组（阶梯优化）交叉，是"端侧补画质值不值"的量化依据。 |

---

## E. 注视点 / ROI / 显著性编码（foveated & ROI）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| E1 | ⭐ | FovOptix: Human Vision-Compatible Video Encoding and Adaptive Streaming in VR Cloud Gaming | A. Alhilal | 2024 / ACM MMSys | DOI:10.1145/3625468.3647612 | 19 | 把注视点渲染（FR）与自适应注视点编码（FVE）组合，在保持感知质量的前提下显著降码率。 | VR 云游戏场景下"人眼只看一小块"的正统工程实现；与 B/D 组可叠加（只在注视区做生成式增强）。 |
| E2 | ⭐ | EyeNexus: Adaptive Gaze-Driven Quality and Bitrate Streaming for Seamless VR Cloud Gaming Experiences | Ze Wu | 2025 / Proc. ACM on Networking | arXiv:2509.11807 · DOI:10.1145/3768989 | 7 | 用实时 gaze 数据**动态调整注视点区域大小**（随带宽变化），把压缩与码率分配一起做。 | 目前把视线数据真正接进控制环的最新代表；与"用预测的视线做前馈"（子方向 A–D 的预测式传输）是同一族问题。 |
| E3 | 📌 | Saliency-Guided Foveated Video Encoding for Low-Latency and Immersive Cloud VR | Ze Wu | 2026 / IEEE TVCG | DOI:10.1109/TVCG.2026.3679056 | 0 | 显著性引导的注视点编码，面向低延迟沉浸式云 VR。 | E2 的期刊延续；2026 年该组仍在同一路线上持续产出，说明这条线尚未收敛。 |

> 另注：ROI 方向 2024–2026 有大量工作（ROI-DVC, ICIP 2024, DOI:10.1109/icip51287.2024.10647832；能源高效显著性引导编码, IEEE JETCAS 2025, DOI:10.1109/JETCAS.2024.3525339 等），但绝大多数面向监控/医疗/自动驾驶而非游戏，本轮不展开。

---

## F. 码率阶梯 / per-title / per-chunk 编码参数优化

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/谁相邻 |
|---|---|---|---|---|---|---|---|---|
| F1 | ⭐ | JND-Aware Two-Pass Per-Title Encoding Scheme for Adaptive Live Streaming (JTPS) | Vignesh V Menon | 2024 / IEEE TCSVT | DOI:10.1109/TCSVT.2023.3290725 | 37 | 引入最小可觉差（JND）约束的受限 VBR 两遍 per-title 编码，**省 68.96% 存储、省 18.58% 编码时间**。 | per-title 从 VOD 走向直播的关键一步；与"感知无损阈值以上不再加码率"（SAIL, G1）是同一个洞察。 |
| F2 | 📌 | Optimal Transcoding Resolution Prediction for Efficient Per-Title Bitrate Ladder Estimation | Jinhai Yang | 2024 / IEEE DCC | arXiv:2401.04405 · DOI:10.1109/DCC58796.2024.00114 | 5 | 现有 per-title 方法估出的其实是 Pareto 前沿上的参数，**仍需后续预编码**；该文直接预测最优转码分辨率。 | 直指 per-title 方法真正的成本（预编码开销）。与 F3（RL 版）路线不同、目标相同。 |
| F3 | 📌 | DQ-Ladder: A Deep Reinforcement Learning-based Bitrate Ladder for Adaptive Video Streaming | Reza Farahani | 2026 / arXiv | arXiv:2603.13597 | 3 | 用 DRL 构造时间与质量感知的码率阶梯，且对带宽预测误差的敏感度显著低于对比方法。 | "RL 做编码参数优化"这一支的最新代表。注意它优化的是**阶梯**而非逐 chunk 的 ABR 决策——两者常被混淆。 |
| F4 | ⭐ | Content Adaptive Encoding For Interactive Game Streaming | Shakarim Soltanayev | 2025 / Picture Coding Symposium | arXiv:2511.22327 · DOI:10.1109/PCS65673.2025.11417690 | 1 | 用 CNN 从当前场景的编码块统计（滑动窗口）推断下一场景的最佳分辨率；作者称这是**首个面向分辨率的互动游戏流 CAE 方案**。 | 本子方向与"游戏"最贴合的一篇编码参数优化工作。与 J 组"渲染感知编码"同源：都用编码器内部已有的块统计做决策，几乎零额外开销。 |

---

## G. 低延迟码率控制 / 质量感知码控

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| G1 | ⭐⭐ | SAIL: Perceptual Quality-Aware Rate Control for Cloud Gaming | Houde Qian | 2026 / arXiv | arXiv:2607.11231 | 0 | **已在生产云游戏平台（T）全量部署**：编码器零成本输出驱动的实时质量评估 + 混合码控 + 网络感知策略，省 **44.27% 带宽**、降 8.37% 端到端延迟，服务数千万用户。 | 本子方向**最重要的一篇**。它给出了两个可直接引用的量化事实：(1) 云游戏带宽占运营成本 **30–60%**；(2) "码率–感知"曲线会饱和，阈值以上纯属浪费。工程形态是**后编码（post-encoding）反馈**，毫秒级、近零开销——这条设计约束值得直接抄。 |
| G2 | 📌 | Feedback-Driven Rate Control for Learned Video Compression | Zhixin Xu | 2026 / arXiv | arXiv:2604.20104 | 1 | 为学习式视频压缩提供可控码率 + 改善 RD 性能的反馈式码控框架。 | NVC 落地绕不开的问题：传统码控（基于 QP）在学习式编码器上不成立，必须重建一套。与 A4（DCVC-RT 的 module-bank 码控）呼应。 |

---

## H. 标准侧：AV1 / VVC / ECM / AV2

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| H1 | ⭐ | Benchmarking Conventional and Learned Video Codecs with a Low-Delay Configuration | Si-Yue Teng | 2024 / VCIP | arXiv:2408.05042 · DOI:10.1109/VCIP63160.2024.10849793 | 7 | **低延迟配置**下横向比较 VTM、JVET ECM、AV1 libaom、AOM AVM、DCVC-DC、DCVC-FM：JVET ECM 综合最佳，**比 AVM 省 16.1%（PSNR 口径）、比 DCVC-FM 省 11.0%**。 | **云游戏/直播场景唯一直接的"传统 vs 学习式"低延迟基准**（多数基准用的是允许延迟的 RA 配置，结论不可直接搬到互动场景）。做选型时的第一手数字。 |
| H2 | ⭐ | Ultra-low latency software (HEVC and VVC) encoding: capabilities and applications | Mauricio Alvarez-Mesa | 2026 / Mile-High Video Conference | DOI:10.1145/3789239.3793289 | 0 | 在**同等算力预算**下，VVC 在超低延迟编码场景仍能胜过 HEVC。 | 与 H1 互补：H1 说的是"相对效率"，这篇说的是"给定实时算力后还剩多少效率"。云游戏的实际约束就是后者。 |

> **标准进展（行业侧，非同行评议，仅作背景，需自行核实）**：AV2 规范 1.0.0 于 **2026-05-28** 定稿、AOMedia 于 2026-06-09 正式发布；相比 AV1 号称约 30% 码率节省，但**目前无任何浏览器/设备支持**，参考软件解码复杂度约为 AV1 的 2.5–5 倍。AV1 处于"17% 生产部署 + 40% 计划 2026 内上线"的状态（NETINT《2026 State of Video Encoding》调查，经行业报道转述）。VVC/LCEVC 的硬件解码在消费设备上仍很罕见。以上均为厂商/媒体来源，⚠️ 不作为学术结论使用。

---

## I. 帧插值 / 帧生成（用于降码率或稳延迟）

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| I1 | ⭐综述 | AceVFI: A Comprehensive Survey of Advances in Video Frame Interpolation | Dahyeon Kye | 2025 / IEEE TCSVT | arXiv:2506.01061 · DOI:10.1109/TCSVT.2026.3672288 | 15 | 覆盖 250+ 篇的 VFI 全景综述，按核心设计原理分类。 | 若要把"降帧率传输 + 端侧补帧"作为省带宽手段，这是入口文献（注意 VFI 主导的感知指标 FloLPIPS 与传统指标差异很大）。 |
| I2 | 📌 | Perception-Aware Frame Display Scheduling for Low-Latency Cloud Gaming (PASync) | Houde Qian | 2026 / ACM NOSSDAV | DOI:10.1145/3798065.3798067 | 0 | 发现存在**感知最大帧率 pFR**——超过它再加帧率买不到感知收益；据此做帧显示调度，在零撕裂前提下最小化缓冲延迟。 | 与 G1 同组（同一作者），把"感知饱和"从码率维度扩展到帧率维度。**直接约束了云游戏的帧率/码率联合优化空间**。 |

---

## J. 游戏/云游戏内容编码与 QoE 工程

| 编号 | 状态 | 标题 | 一作 | 年份/出处 | arXiv/DOI | 引用(S2快照) | 一句话结论 | 为什么重要/与谁相邻 |
|---|---|---|---|---|---|---|---|---|
| J1 | 经典 | Modeling Gaming QoE: Towards the Impact of Frame Rate and Bit Rate on Cloud Gaming | Saman Zadtootaghaj | 2018 / QoMEX | DOI:10.1109/QoMEX.2018.8463416 | 51 | 首个系统量化"帧率 × 码率"对云游戏 QoE 交互影响的研究。 | 云游戏编码参数优化的经典 QoE 依据；G1/I2 的"感知饱和"结论本质上是在更新它的模型。 |
| J2 | ⭐ | Codec Compression Efficiency Evaluation for Ultra Low–Latency Cloud Gaming Applications | Nabajeet Barman | 2024 / QoMEX | DOI:10.1109/QoMEX61742.2024.10598276 | 2 | 面向超低延迟云游戏的编解码器压缩效率评测。 | 与 H1/H2 一起构成"云游戏该选哪个编解码器"的实测证据；作者是该领域数据集奠基人（C5）。 |

---

## K. 工业落地情况（哪些已经真的在用）

| 技术 | 落地程度 | 可核验证据 |
|---|---|---|
| **VMAF** | 已全行业落地，事实标准 | Netflix 2016-06 开源 VDK（Apache-2.0，github.com/netflix/vmaf），与 USC 郭宗杰团队合作；获 Emmy；被用于码率阶梯、编解码器比较、A/B 实验。第三方复现验证见 C2。衍生品：VMAF NEG、NR-VMAF（C3）。 |
| **Per-title / per-shot encoding** | 已落地并扩散到主要厂商 | Netflix 2015-12 发布 per-title（技术博客）；2018 上线 Dynamic Optimizer 做逐镜头 Lagrangian 优化，声称在 per-title 基础上再省 27–37% 码率。Bitmovin/Mux 等有对应商业产品。⚠️ 均为厂商博客/白皮书，非同行评议。学术侧对应 F1/F2/F3。 |
| **客户端超分 / 神经增强** | 已产品化，但有硬件门槛 | NVIDIA RTX Video Super Resolution：2023-02 上线，在 Chrome/Edge 中把低分辨率流实时升到 4K，需 RTX 30/40 系；2025-01 更新换了更省算力的模型（最高质量档省约 30% GPU 资源）并支持 HDR。云游戏侧：GeForce NOW 已用 AV1 编码 + DLSS 帧生成。⚠️ NVIDIA 官方文档/博客。学术本源见 D1（NAS）。 |
| **云游戏质量感知码控** | 已在大规模生产环境部署 | G1 SAIL：生产云游戏平台，省 44.27% 带宽、服务数千万用户、累计数十亿游戏小时。**这是本子方向 2026 年最有分量的落地证据。** |
| **学习式 / 生成式编解码（NVC / 生成式 codec）** | **未找到公开的大规模商用落地证据** | DCVC 系列由 Microsoft Research 开源维护（github.com/microsoft/DCVC）；DCVC-RT 是明确的"面向实用实时"尝试。但**没有任何公开证据表明某家流媒体/云游戏平台在生产链路中用它替代了传统编码器**。搜索到的最接近的是 B12 Gen2-VC 这类"标准码流 + 生成式后处理"的混合形态，以及 D 组的客户端超分。 |

---

## L. 研究空白与待解决问题

1. **"学习式/生成式编解码器的质量评价"本身是个未解决问题。** C4（PCS 2025）用主观实验证明现行指标在 DCVC-FM/DCVC-RT 上表现不一致（PSNR 序列内排序最好但绝对不感知、VMAF 与 AVQBits 相关但覆盖不足）；C6（GameScope, 2026）则指出跨 codec 可比的质量模型缺数据。**后果**：F 组的码率阶梯优化若用 VMAF 做目标，在学习式/生成式编码器上优化的是错的东西。这是本子方向最"地基级"的空白。

2. **生成式编解码的解码延迟与硬件形态矛盾尚未解决。** ReGenVC 需要 8 卡并行才到 24 fps（且只针对说话头）、DiffVC-RT 需要 H800 才到 720p@30fps 解码、GLVC 单 A100 上 1080p 只有 3 fps 解码。对照 B10（图像域单 A100 已 42 fps 解码）和 B11（图像域单线程 CPU 解码），差距是**一个数量级**，且瓶颈被 ReGenVC 明确定位为"VAE 解码 + 4 步采样的固定成本"。目前只有 B11 一条明确的"往 CPU/NPU 走"的路线，视频域还没有对应工作。

3. **"感知饱和"被分别发现，但没有联合模型。** G1 证明码率维度存在感知无损阈值（跨过即浪费），I2 证明帧率维度存在感知最大帧率 pFR。但**没有一篇工作把码率、帧率、分辨率、以及客户端增强算力放进同一个联合优化**——F4（游戏 CAE）只调分辨率，E2（EyeNexus）只调注视区与码率，D5（E2-Stream）只把 SR 能耗纳入阶梯。云游戏平台的真实决策空间是这几者的笛卡尔积。

4. **游戏内容的域特性没有系统性写进编码工具。** CPGSR（D3）和 GameIR（ACCV-W 2024, arXiv:2408.16866）都指出游戏/渲染内容与自然视频不同（锐利纹理、可得的运动矢量/相机信息、压缩伪影形态不同），但主流编码器与质量指标都不是为这个域训练的。学术界已有"用相机信息辅助运动矢量预测"（云游戏编码，DCC 2024/2025）等零散尝试，**没有形成被标准采纳的游戏专用工具集**。

---

## M. 检索局限

1. **Semantic Scholar 限流**：本次共发起约 50 个 S2 检索查询，其中约 12 次返回 HTTP 429（"Too Many Requests"），已用指数退避（2/4/8/16 s）+ 3 s 间隔逐一重试，最终仅有极少查询未取回原始结果（已重试补齐）。**因此同一批查询结果的 `total` 计数与覆盖面不完全一致**，本表是"按相关性排序的前 20 条"里筛出来的，不代表该主题的全部文献。
2. **一个本地环境问题**：Windows 临时目录在检索过程中被清理过一次，导致 3 个子查询的输出文件丢失，已换目录重跑成功（`game_qoe`、`codec_ecm`、`vvc_ml` 及若干经典工作检索）。
3. **一条 DOI 核不实**：`10.1145/3774904.3792643`（FovRL, The Web Conference 2026）在 Crossref 返回 "Resource not found"，**未通过 DOI 验证**。该条的标题/作者/年份/会议/引用数来自 S2 题录，属**题录级**，本轮未在表中收录（避免拉低证据质量）。
4. **S2 会议名字段有明显噪声**：多篇 ICIP 论文在 S2 中被记为 "International Conference on Information Photonics"（例如 GameScope）。凡遇此情况已在表中注明"⚠️待核实"，未直接采信。
5. **引用数为 S2 快照（2026-10-01）**，2025–2026 年的论文普遍为 0–10，**不可用于横向比较新旧论文的影响力**。部分 2026 年期刊论文 S2 未给出 `publicationDate`（显示为 None）。
6. **工业落地证据的等级较低**：VMAF 开源、Netflix per-title、NVIDIA RTX VSR、AV2 发布时间线、AV1 部署率等来自厂商博客、产品文档、行业调查与媒体报道，**不是同行评议来源**，已在 §K 逐条标注 ⚠️。M3-CVC 的解码耗时（142.5 s @ RTX 3090）来自第三方分析博客，**论文原文并未自报该数字**。
7. **未做完整的滚雪球**：因限流与时间成本，本轮未对 DCVC-RT、DiffVC-RT、SAIL 做正向/反向引用展开（`/citations`、`/references`）。若要确认"生成式编解码是否已有被工业采纳的后续"，建议下一步对 DCVC-RT 与 ReGenVC 做正向引用检索。
8. **本工作区既有索引 `文献索引.md` 已核对**，其中与视频相关的条目（Sieber 2015/2016、Zhang 2021 短视频浪费、Su 2024 traffic wastage、YouSlow 系列、Chen/Hajiesmaili/Sitaraman 2026 学习增强 360° 流）均属传输/QoE 层，与子方向 E 的"编码与质量"层不重叠，本轮未重复检索，也未改动索引文件。

---

## N. 附：本轮检索到、但因条数上限（目标 25–45）未展开成行的条目（仅备查，未做完整核实到正文级）

- NVRC: Neural Video Representation Compression — Ho Man Kwan, 2024 / NeurIPS, arXiv:2409.07414（INR 视频压缩）
- GIViC: Generative Implicit Video Compression — Ge Gao, 2025 / ICCV, arXiv:2503.19604（INR 超过 VTM）
- ECVC: Exploiting Non-Local Correlations in Multiple Frames for Contextual Video Compression — Wei Jiang, 2025 / CVPR, arXiv:2410.09706（与 DCVC-RT 同代竞争）
- nofu — A Lightweight No-Reference Pixel Based Video Quality Model for Gaming Content — Steve Göring, 2019 / QoMEX, DOI:10.1109/QoMEX.2019.8743262（游戏内容 NR 指标经典，32 引用）
- No-Reference Rendered Video Quality Assessment: Dataset and Metrics — Sipeng Yang, 2025 / arXiv:2510.13349（渲染视频 NR-VQA 数据集）
- CodecArena: Codec Quality Assessment via Visual Reinforcement Learning — Jiaye Fu, 2026 / arXiv:2608.09139（用 VLM 评估编解码质量，直指 LPIPS/DISTS 会奖励"幻觉"）
- GameIR: A Large-Scale Synthesized Ground-Truth Dataset for Image Restoration over Gaming Content — Lebin Zhou, 2024 / ACCV Workshops, arXiv:2408.16866
- iSR: Super-resolution for Immersive Cloud VR Gaming Platforms — Ghazaleh Bakhtiariazad, 2026 / ACM MMSys, DOI:10.1145/3793853.3795746
- HTTP Adaptive Streaming: A Review on Current Advances and Future Challenges — Christian Timmerer, 2025 / ACM TOMM, DOI:10.1145/3736306（19 引用，ABR 侧综述）
- Decoding Complexity-Aware Bitrate-Ladder Estimation for Adaptive VVC Streaming — Zoha Azimi, 2024 / EUSIPCO, DOI:10.23919/eusipco63174.2024.10715338
- VCIP 2025 Ultra Low-Bitrate Video Compression Challenge — Guo Lu, 2025 / VCIP, DOI:10.1109/VCIP67698.2025.11396877（说明超低码率已是社区竞赛主题）
