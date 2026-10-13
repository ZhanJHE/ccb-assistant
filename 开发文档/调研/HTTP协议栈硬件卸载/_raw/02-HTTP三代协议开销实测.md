# 02 — HTTP/1.1 / HTTP/2 / HTTP/3 三代协议本体的性能与 CPU/资源开销（实测证据）

- 采集日期：2026-10-05
- 检索源：Semantic Scholar Graph API（/paper/search、/paper/{id}）、arXiv Atom API、RFC 原文、工程博客原文（Tavily + FetchURL）
- 本文件范围：只回答「三代协议在 CPU、吞吐、延迟上差多少、差在哪、机制的代价是什么」。
  同一工作区其他主题（DPDK 内核旁路、云游戏、KV-cache、在网计算）不在本文件范围，勿重复登记。
- 核验状态图例：`实测fetch`（我抓到了原文/原文摘要页）/ `S2元数据`（S2 记录齐全，未读全文）/ `仅摘要`（只有摘要无全文）/ `工业测量`（厂商或工程博客，非同行评审）/ `待核实`。
- **引用数为 S2 抓取值，仅作新旧参考，不代表质量。**

---

## A. 协议本体规范与设计论文（一手来源）

| 编号 | 标题 | 一作/机构 | 年/出处 | arXiv·DOI·URL | 引用数 | 一句话结论（含关键数字） | 核验状态 |
|---|---|---|---|---|---|---|---|
| 02-A1 | RFC 7540: HTTP/2 | M. Belshe (BitGo), R. Peon, M. Thomson | 2015 / IETF Standards Track | https://www.rfc-editor.org/rfc/rfc7540.txt | — | HTTP/2 二进制分帧 + 单 TCP 连接多路复用。§4.3 明文规定：**每个 header block 必须作为"连续帧序列"传输，不得被其他类型或其他流的帧插入** —— 这是 HPACK 解码无法并行/无法乱序的规范根因。 | 实测fetch |
| 02-A2 | RFC 7541: HPACK Header Compression for HTTP/2 | R. Peon (Google), H. Ruellan (Canon) | 2015 / IETF Standards Track | https://www.rfc-editor.org/rfc/rfc7541.txt | 88 | 头压缩用**每连接一份动态表**；原文写"解码器执行**由编码器规定**的表修改，并在过程中重建 header list" → 解码是有状态的强顺序过程。§7.1 另指出动态表状态可被旁路探测（压缩长度侧信道）。 | 实测fetch（全文） |
| 02-A3 | RFC 9114: HTTP/3 | M. Bishop (Akamai), Ed. | 2022 / IETF Standards Track | https://www.rfc-editor.org/rfc/rfc9114.txt | — | HTTP/3 = HTTP 语义 + QUIC 传输 + QPACK；把队头阻塞从"连接级"下移到"流级"。 | 实测fetch |
| 02-A4 | RFC 9204: QPACK Field Compression for HTTP/3 | C. Krasic, M. Bishop, A. Frindell | 2022 / IETF Standards Track | https://www.rfc-editor.org/rfc/rfc9204.txt | 11 | 为了在"流间乱序"的 QUIC 上保住压缩率，把动态表更新挪到**独立 encoder 流**；代价是 §2.2.1 **blocked decoding**（`Required Insert Count > Known Received Count` 时该 header block 被阻塞等待），并用 `SETTINGS_QPACK_BLOCKED_STREAMS` 限流。§2.1.4 定义 Known Received Count 作为"哪些表项可安全引用"的记账变量。 | 实测fetch |
| 02-A5 | RFC 9000: QUIC: A UDP-Based Multiplexed and Secure Transport | J. Iyengar (Fastly), M. Thomson, Ed. | 2021 / IETF Standards Track | https://www.rfc-editor.org/rfc/rfc9000.txt | — | 可靠传输/多路复用/拥塞控制/加密全部搬到 UDP 之上；**每个包强制加密**并做 header protection（等于每包至少两遍对称加密操作）。 | 实测fetch |
| 02-A6 | RFC 9002: QUIC Loss Detection and Congestion Control | J. Iyengar (Fastly), I. Swett, Ed. | 2021 / IETF Standards Track | https://www.rfc-editor.org/rfc/rfc9002.txt | — | QUIC 的丢包检测/ACK 语义独立于 TCP；ACK 本身也在加密包里（这是后文"用户态 ACK 处理贵"的规范来源之一）。 | 实测fetch |
| 02-A7 | RFC 8446: TLS 1.3 | E. Rescorla (Mozilla) | 2018 / IETF Standards Track | https://www.rfc-editor.org/rfc/rfc8446.txt | — | 1-RTT 握手 + 0-RTT 复用。注意：QUIC **复用 TLS 1.3 握手与密钥调度，但不用 TLS 记录层**，记录层换成了 QUIC 自己的包保护。 | 实测fetch |
| 02-A8 | The QUIC Transport Protocol: Design and Internet-Scale Deployment | Adam Langley 等 (Google) | 2017 / SIGCOMM | DOI:10.1145/3098822.3098842 | 937 | Google 全球部署经验：2017 年 QUIC 已承载约 **7% 的互联网流量**；给出搜索/YouTube 指标收益。业界反复引用的"服务端 QUIC 的 CPU 约为 TCP+TLS 的 **2 倍**"据称出自此文，**但我没能直接读到该句原文，只见二手引用，标待核实**。 | S2元数据（摘要）+ "2x" 待核实 |
| 02-A9 | QPACK: Header Compression for HTTP over QUIC（草案演化） | M. Bishop, A. Frindell, C. Krasic | 2018–2019 / IETF draft | https://datatracker.ietf.org/doc/html/draft-ietf-quic-qpack-03 | 1 | 草案 §7.3.2 与 §7.4 直接给出设计取舍原文：引用尚未确认的表项可提高压缩率，但"若丢包或乱序，该流会在解码器处被阻塞"；编码器必须把可能阻塞的流数限制在 SETTINGS 值内。 | 实测fetch（草案页） |

---

## B. 端到端协议版本对比：既有基线（用户"横评"命题的直接前作）

| 编号 | 标题 | 一作/机构 | 年/出处 | arXiv·DOI·URL | 引用数 | 一句话结论（含关键数字） | 核验状态 |
|---|---|---|---|---|---|---|---|
| 02-B1 | Taking a long look at QUIC（IMC 版） | Arash Molavi Kakhki (Northeastern / ThousandEyes) | 2017 / ACM IMC | DOI:10.1145/3131365.3131368 | 161 | 第一个严谨的 QUIC vs TCP 端到端评测（多链路速率 × 多对象大小矩阵 + PLT/TTFB）。核心发现：二者同用 CUBIC，但 QUIC 窗口增长更激进，**在竞争场景下 QUIC 始终吃掉 >50% 的瓶颈带宽**，对 TCP 不公平。 | S2元数据 |
| 02-B2 | Taking a long look at QUIC（CACM 期刊版） | 同上 | 2019 / Communications of the ACM | DOI:10.1145/3330336 | 31 | 同一工作的期刊版，可用作正式引用源。 | S2元数据 |
| 02-B3 | Replication: "Taking a long look at QUIC" | Naveenraj Muthuraj, Nooshin Eghbal, Paul Lu (U. Alberta) | 2024 / ACM IMC | DOI:10.1145/3646547.3688453 | 5 | 2024 年在 Emulab 上复现 2017 实验并扩展到 IETF QUICv1：0-RTT/多流带来的优势在 gQUICv37 与 QUICv1 上**一致存在**；QUICv1 因改用 BBR + 新丢包检测，在**乱序**场景更好。→ 说明"QUIC 端到端更快"这一结论已被复现，横评本身不构成新贡献。 | 仅摘要 |
| 02-B4 | A First Look at QUIC in the Wild | Jan Rüth (RWTH Aachen) | 2018 / PAM | arXiv:1801.05168 · DOI:10.1007/978-3-319-76481-8_19 | 122 | Alexa Top 1M 大规模被动测量：QUIC 在**大流量下载**中占比很高，但在**小流量请求**中占比很低 —— 服务器实际把 QUIC 当成"大文件专用通道"。 | S2元数据 |
| 02-B5 | QUIC is not Quick Enough over Fast Internet | Xumiao Zhang (U. Michigan) | 2024 / ACM WWW (Pages 2713-2722) | arXiv:2310.09423 · DOI:10.1145/3589334.3645323 | 42 | 高速网络下 UDP+QUIC+HTTP/3 相比 TCP+TLS+HTTP/2 **数据率最多降 45.2%**，视频码率最多降 **9.8%**；带宽越高差距越大。根因定位在**接收侧**：内核上送的用户态包数量过多 + QUIC 的**用户态 ACK**。论文 Table 1：桌面以太网下载 HTTP/2 9.32 s vs HTTP/3 18.60 s（+99%），CPU 77.5% vs 96.9%；Pixel 5 mmWave 下 30.10 s vs 63.20 s（+110%），CPU 128.43% vs 165.20%。 | 实测fetch（arXiv 摘要 + 论文表） |
| 02-B6 | QUIC is not Quick Enough over Fast Internet（海报版） | 同上 | 2023 / ACM IMC Poster | DOI:10.1145/3618257.3625002 | 2 | 同一工作的早期海报版。 | S2元数据 |
| 02-B7 | Measuring HTTP/3: Adoption and Performance | Martino Trevisan (Univ. Genova) | 2021 / MedComNet | arXiv:2102.12358 · DOI:10.1109/MedComNet52149.2021.9501274 | 39 | 对数千个启用 HTTP/3 的网站做大规模测量：**HTTP/3 只在高时延或差带宽场景给出可观收益**；很多网站的关键对象仍托管在只支持 H2/H1.1 的第三方域上，抵消了收益。 | 实测fetch（arXiv 摘要页） |
| 02-B8 | A first look at HTTP/3 adoption and performance | Gianluca Perna (Politecnico di Torino) | 2022 / Computer Communications | DOI:10.1016/j.comcom.2022.02.005 | 21 | 上文期刊扩展版。结论一致：HTTP/3 仅在高时延/移动网络显著更好；对**视频流媒体目前无收益**。 | 实测fetch（摘要）+ 仅摘要 |
| 02-B9 | An Early Benchmark of QoE Between HTTP/2 and HTTP/3 using Lighthouse | Darius Saif (Carleton) | 2021 / IEEE ICC | arXiv:2004.01978 · DOI:10.1109/ICC42927.2021.9500258 | 41 | 用 Lighthouse 多指标（而非只看 PLT）对比 H2 与早期 H3 实现：**H3 多数 QoE 指标更差，但平均吞吐更高**。与 B7/B8 的"高延迟才赢"形成互补/冲突证据。 | 实测fetch（arXiv 摘要）+ S2元数据 |
| 02-B10 | A performance perspective on web optimized protocol stacks: TCP+TLS+HTTP/2 vs. QUIC | Konrad Wolsing (RWTH Aachen) | 2019 / ACM ANRW | arXiv:1906.07415 · DOI:10.1145/3340301.3341123 | 44 | 指出既有对比都在"优化过的 QUIC vs 没优化的 TCP"上做；论文把 TCP 参数调到最优后 QUIC 仍胜，优势主要来自**连接建立 RTT 更少**与**丢包下规避队头阻塞**。→ 这是横评类工作最常被审稿人引用的"方法论打脸"文献。 | 仅摘要 |
| 02-B11 | Resource Multiplexing and Prioritization in HTTP/2 over TCP Versus HTTP/3 over QUIC | Robin Marx (Hasselt) | 2019 / WEBIST（Springer 卷） | DOI:10.1007/978-3-030-61750-9_5 | 22 | 直接对齐"HTTP/2 多路复用/优先级 vs HTTP/3"的资源复用与优先级设计差异，是横评命题最接近的前作之一。 | S2元数据 |
| 02-B12 | Web Performance Characteristics of HTTP/2 and Comparison to HTTP/1.1 | Robin Marx, Maarten Wijnants, Peter Quax | 2017 / WEBIST | DOI:10.1007/978-3-319-93527-0_5 | 1 | HTTP/1.1 vs HTTP/2 的页面级性能特征对比（含对象数与 PLT 关系）。 | S2元数据 |
| 02-B13 | Is the Web HTTP/2 Yet? | Matteo Varvello (Bell Labs) | 2016 / PAM | DOI:10.1007/978-3-319-30505-9_17 | 76 | HTTP/2 早期部署与真实性能测量（服务端支持度低、收益不确定）。 | S2元数据 |
| 02-B14 | To HTTP/2, or Not To HTTP/2, That Is The Question | Matteo Varvello | 2015 / arXiv | arXiv:1507.06562 | 8 | HTTP/2 刚定稿时的收益评估，是"HTTP/2 到底有没有用"的早期基线。 | S2元数据 |
| 02-B15 | QUIC: Better for what and for whom? | Sarah Cook (Northeastern) | 2017 / IEEE ICC | DOI:10.1109/ICC.2017.7997281 | 86 | 从"对谁更好"的角度拆解 QUIC 的收益来源（与 B1 同一课题组脉络）。 | S2元数据 |
| 02-B16 | QUICker or not? - an Empirical Analysis of QUIC vs TCP for Video Streaming QoE Provisioning | Michael Seufert (Univ. Würzburg) | 2019 / ICIN | DOI:10.1109/ICIN.2019.8685913 | 39 | 视频流 QoE 视角的 QUIC vs TCP 实测：收益依场景而定，非普遍更优。 | S2元数据 |
| 02-B17 | Can HTTP/2 Really Help Web Performance on Smartphones? | Yi Liu 等 | 2016 / IEEE SCC | DOI:10.1109/SCC.2016.36 | 11 | HTTP/2 在移动端（高 RTT/易丢包）的收益评估。 | S2元数据 |
| 02-B18 | The curious case of parallel connections in HTTP/2 | Jawad Manzoor (U. Twente) | 2016 / CNSM | DOI:10.1109/CNSM.2016.7818414 | 14 | 真实浏览器在 HTTP/2 下仍开多条并行连接，削弱了单连接多路复用的设计意图。 | S2元数据 |
| 02-B19 | HTTP/2 performance evaluation with latency and packet losses | Naoki Oda, Saneyasu Yamaguchi | 2018 / IEEE CCNC | DOI:10.1109/CCNC.2018.8319285 | 6 | 时延与丢包对 HTTP/2 的定量影响（S2 无摘要，需查原文）。 | S2元数据 |
| 02-B20 | Same Standards, Different Decisions: A Study of QUIC and HTTP/3 Implementation Diversity | Robin Marx (Hasselt) | 2020 / EPIQ@SIGCOMM | DOI:10.1145/3405796.3405828 | 70 | 实证对比 **15 个** IETF QUIC+HTTP/3 实现，发现流控/拥塞控制/0-RTT/多路复用/打包行为**高度异质**，多数实现尚未优化或验证充分。→ 任何"协议 A vs 协议 B"的单实现横评都会被这条打掉。 | 仅摘要 |
| 02-B21 | On the Performance of Transport Protocols Over mmWave Links: Empirical Comparison of TCP and QUIC | Sidna Jeddou (Univ. Paris-Saclay) | 2023 / IEEE OJ-COMS | DOI:10.1109/OJCOMS.2023.3325764 | 6 | mmWave 链路下 TCP vs QUIC 实测对比。 | S2元数据 |
| 02-B22 | HTTP/3 Performance Comparison on NGINX, OpenLiteSpeed, and Caddy in 5G-Like Networks | Muhammad Fachry Abiwardhana | 2026 / IEEE IITS | DOI:10.1109/IITS69561.2026.11648461 | 0 | 同类服务器、5G 模拟网络下的三款 HTTP/3 服务端实现对比：说明"实现选择"对结果的影响大于协议本身。 | S2元数据 |
| 02-B23 | Exploring Proxying QUIC and HTTP/3 for Satellite Communication | Marius Kosek (TU Berlin) | 2022 / IFIP Networking | DOI:10.23919/IFIPNetworking55013.2022.9829773 | 20 | 高 RTT（卫星）场景下代理 QUIC 的收益，属"高延迟才赢"证据链。 | S2元数据 |
| 02-B24 | QUIC vs. TCP: A Performance Evaluation over LTE with NS-3 | A. Kyratzis | 2022 / Communications and Network | DOI:10.4236/cn.2022.141002 | 9 | 蜂窝网络仿真下的 QUIC vs TCP 对比。 | S2元数据 |

---

## C. QUIC 的 CPU 成本：拆解、量化与优化手段

| 编号 | 标题 | 一作/机构 | 年/出处 | arXiv·DOI·URL | 引用数 | 一句话结论（含关键数字） | 核验状态 |
|---|---|---|---|---|---|---|---|
| 02-C1 | QUIC CPU Performance / "As QUIC as TCP, Optimizing QUIC and HTTP/3 CPU usage"（EPIQ 2020 主题演讲 + 幻灯片） | Ian Swett (Google, Chrome QUIC 团队) | 2020 / EPIQ@SIGCOMM | https://conferences.sigcomm.org/sigcomm/2020/files/slides/epiq/0%20QUIC%20and%20HTTP_3%20CPU%20Performance.pdf | — | 最完整的一份"QUIC 服务端 CPU 拆解"公开材料：(1) **UDP 发送占其负载 CPU 的 25%，部分环境 >50%**；(2) Linux 下 **UDP `sendmsg` 的 cycle/byte 最高是 TCP 的 3.5 倍**，`sendmmsg` 只省掉"每包一次 syscall"；(3) 收到包侧：BPF 按 connection ID 分流避免线程跳转、**UDP GRO 补丁把接收 CPU 降 35%**；(4) 仅"每包一个 STREAM 帧"这一项优化就省 5%；(5) **UDP GSO + 硬件分段卸载再给 2-3x**，"累积加速理想 10x、典型 5x"；结论是"QUIC 应能在对称加密被卸载后与 kTLS 一样快"。副标题就是本子领域的核心问题：*Can HTTP/3 be as efficient as HTTP/2 and HTTP 1.1?* | 工业测量（非同行评审；Google 内部数据） |
| 02-C2 | Making QUIC Quicker With NIC Offload | Xiangrui Yang (Politecnico di Milano) 等 | 2020 / EPIQ@SIGCOMM | DOI:10.1145/3405796.3405827 | 37 | 系统拆解多个 QUIC 实现各组件成本后指出：**内核↔用户态通信、crypto 模块、包重排序算法**三者是 CPU 大户，且常是应用性能退化的原因；据此提出 NIC 应暴露的 QUIC 卸载原语。→ 直接命中"QUIC 卸载该卸哪一块"。 | 仅摘要 + 实测fetch（摘要原文） |
| 02-C3 | QUIC on the Highway: Evaluating Performance on High-rate Links | Benedikt Jaeger (TU Munich) | 2023 / IFIP Networking | arXiv:2309.16395 · DOI:10.23919/IFIPNetworking57963.2023.10186365 | 25 | 10G 链路上的可复现基线：**不同 QUIC 实现 goodput 从 90 Mbit/s 到 4900 Mbit/s（差 50 倍以上）**；默认 socket buffer 小一个数量级需调大；**QUIC 从 NIC offload 与 AES-NI 得到的收益明显小于 TCP** —— 后者在开启这些特性后可达约 8000 Mbit/s。 | 实测fetch（arXiv 摘要） |
| 02-C4 | A high-speed QUIC implementation（picoquic-dpdk） | Nikita Tyunyayev (UCLouvain) 等 | 2022 / CoNEXT Student Workshop | DOI:10.1145/3565477.3569154 | 17 | 用 DPDK 旁路 Linux 网络栈改造 picoquic：**吞吐提升 3 倍**，超过所有被测 QUIC 栈，并**追平甚至超过带常规优化的 TCP+TLS**。 | 实测fetch（摘要原文） |
| 02-C5 | Kernel Bypass Surgery: A Viable Procedure for Maximizing QUIC Bandwidth? | J. Späth (TU Munich) 等 | 2026 / IEEE-IFIP NOMS | DOI:10.1109/NOMS69089.2026.11668379 | 0 | 把 DPDK 集成进 **4 个** QUIC 实现（含 SR-IOV 共享网口方案）：内核旁路最高带来 **3x 加速、goodput 超过 10 Gbit/s**。但作者明确两点保留：**加速幅度高度依赖实现**（有一个实现用了 DPDK 也没更快），且**"如果系统提供 offload 且实现正确使用，也能达到类似性能"** —— 即"必须内核旁路才快"不成立。 | 实测fetch（摘要原文） |
| 02-C6 | LiteQUIC: Improving QoE of Video Streams by Reducing CPU Overhead of QUIC | Peng-Qiang Bi 等 | 2024 / ACM Multimedia | DOI:10.1145/3664647.3681670 | 4 | 拆出 QUIC 的 CPU 瓶颈为**ACK 处理、发包路径、数据加密**三项；在 CPU 受限时 **HTTP/3 吞吐甚至低于 HTTP/1.1**。组合优化（降 ACK 频率 + UDP GSO + PicoTLS）后用于 DASH 视频，比"只开 GSO+PicoTLS 的优化版 QUIC"平均码率高 1.2x、重缓冲时间低 93.3%。 | 实测fetch（摘要原文） |
| 02-C7 | Implementation and Performance Evaluation of the QUIC Protocol in Linux Kernel | Peng Wang 等 | 2018 / ACM MSWiM | DOI:10.1145/3242102.3242106 | 30 | 早年的"把 QUIC 放进内核"实现与评测，是 C9/LWN 路线的学术先声。 | S2元数据 |
| 02-C8 | Characterizing the Performance of QUIC on Android and Wear OS Devices | Anirudh Ganji (WPI) | 2021 / IEEE ICCCN | DOI:10.1109/ICCCN52240.2021.9522258 | 7 | 移动/穿戴端 QUIC 实现的性能与资源占用实测（端侧而非服务端）。 | S2元数据 |
| 02-C9 | QUIC for the kernel（LWN 报道 Xin Long 的内核 QUIC 补丁系列） | Jonathan Corbet / Xin Long (Red Hat) | 2025-07-22 / LWN.net | https://lwn.net/Articles/1029851 | — | 内核态 QUIC（`IPPROTO_QUIC`，握手仍留用户态）自带基准：**内核 QUIC 吞吐在内核 kTLS 面前低近 3 倍；把 1-RTT 加密关掉后与裸 TCP 比，TCP 最多快 4 倍以上**。作者给的原因：QUIC 侧**缺分段卸载（GSO）**、发送路径**多一次数据拷贝**、**QUIC 头部需要额外加密**。→ 连"搬进内核"也没自动解决，瓶颈是 offload 与拷贝。 | 工业测量（内核补丁自带基准，经 LWN 报道） |
| 02-C10 | Linux 内核 QUIC 协议补丁系列（初版） | Xin Long (Red Hat) | 2024-09-10 / netdev 邮件列表 | https://lists.openwall.net/netdev/2024/09/10/31 | — | 补丁自带表格可见的量级：`mtu:1500` 下 kTLS 约 3.04 Gbit/s 而 QUIC 约 1.67 Gbit/s；把 1-RTT 加密关掉后 `size:16384` 时 QUIC 6.09 vs TCP 15.1 Gbit/s、`mtu:9000/size:65536` 时 19.1 vs 31.3 Gbit/s。作者自陈差距来自缺 GSO、TX 多一次拷贝、头部加密。**（页面正文我只抓到标题，表格数字来自检索快照，标待核实）** | 待核实 |
| 02-C11 | Measuring QUIC vs TCP computational efficiency（quicly 微基准，Fastly 博客） | Alessandro Ghedini 等 (Fastly) | 2020 / Fastly Blog | https://www.fastly.com/blog/measuring-quic-vs-tcp-computational-efficiency | — | 单核 400MHz、Gbit 网口、无硬件卸载的受控实验：裸 TCP **708 Mbps**；TLS1.3 over TCP（picotls/AES128-GCM）**466 Mbps（≈裸 TCP 的 66%）**；未调优 quicly **196 Mbps（≈TLS/TCP 的 40%）**。逐项优化：ACK 频率 1/2→1/10 得 **240 Mbps**；加 UDP GSO（10 包）得 **348 Mbps（+45%）**；GSO 20 包得 **431 Mbps（再 +45%）**；包长 1280→1460 得 **466 Mbps（追平 TLS/TCP）**；最终 quicly 在 1460 首包下 **464 Mbps**、Chrome 默认 1350 首包下 **425 Mbps**。→ 结论是"QUIC 可以做到与 TCP 同等的计算效率"，而非"QUIC 天生贵"。 | 工业测量（非同行评审） |
| 02-C12 | Accelerating UDP packet transmission for QUIC（Cloudflare 博客） | Alessandro Ghedini (Cloudflare) | 2020 / Cloudflare Blog | https://blog.cloudflare.com/accelerating-udp-packet-transmission-for-quic | — | 用 `sendmmsg` + UDP GSO（可组合，单次 syscall 最多 64 段）把实现吞吐从 **640 Mbps 提升到 1.6 Gbps**；并记录 syscall 数量显著下降。 | 工业测量（非同行评审） |
| 02-C13 | Optimizing QUIC performance（Huitema 个人博客） | Christian Huitema（picoquic 作者） | 2023 / privateoctopus.com | https://www.privateoctopus.com/2023/12/12/quic-performance.html | — | 用 flame graph 拆实现的 CPU：**2019 年发现 70-80% 的 CPU 花在 socket 层（sendto/recvfrom/sendmsg/recvmsg），而不是当初假设的加密**；沿 Cloudflare 路线（sendmsg/GSO）把 picoquic 单线程做到 1.5-2 Gbps。 | 工业测量（非同行评审，作者为 QUIC 标准主要作者之一） |
| 02-C14 | How Facebook is bringing QUIC to billions | Matt Joras, Yang Chi (Meta) | 2020 / Engineering at Meta | https://engineering.fb.com/2020/10/21/networking-traffic/how-facebook-is-bringing-quic-to-billions | — | Meta 自陈在把 QUIC 推到静态内容（图片/视频）前，"必须解决两个顾虑：**mvfst 的 CPU 效率**和 BBR 的效果"；同一时期 **>75% 的 Meta 互联网流量**走 QUIC/HTTP/3。→ 大厂确实为 QUIC 的 CPU 成本付了工程代价。 | 工业测量（非同行评审） |
| 02-C15 | Making Chrome QUICer | Fan Yang, Ian Swett (Google) | 2024-12 / Google Chromium Blog | https://blog.google/chromium/making-chrome-quicer | — | Chrome 2020-10 默认开启 HTTP/3 后的后续优化与收益（搜索时延下降、YouTube 重缓冲减少），是"QUIC 的客户端收益"现状说明。 | 工业测量（非同行评审） |
| 02-C16 | Comparing HTTP/3 vs. HTTP/2 Performance（Cloudflare 自测） | Cloudflare | 2020 / Cloudflare Blog | https://blog.cloudflare.com/http-3-vs-http-2 | — | 自家网络上的页面级对比：15KB 小页 HTTP/3 **443 ms** vs HTTP/2 **458 ms**；1MB 大页 HTTP/3 **2.33 s** vs HTTP/2 **2.30 s**；TTFB 176 ms vs 201 ms（HTTP/3 好 12.4%）；但在北美/欧洲/亚洲/南美平均 **HTTP/3 仍落后 1-4%**，作者自陈混杂因素是 HTTP/2 用 BBR v1 而 HTTP/3 用 CUBIC。→ 页面加载时间这个指标在三代协议间已经很不敏感。 | 工业测量（非同行评审） |
| 02-C17 | Measuring HTTP/3 Real-World Performance（ISOC Pulse） | Robin Marx (ISOC Pulse) | 2023 / Internet Society | https://pulse.internetsociety.org/en/blog/2023/07/measuring-http-3-real-world-performance | — | 汇总 Google/Cloudflare/Akamai 的实测：Google 搜索桌面加载时间平均降 8%、移动降 3.6%、最慢 1% 用户最多降 16%、YouTube 卡顿最多降 20%；Akamai 某直播客户 HTTP/3 达 ≥5 Mbps 的连接占 **69.7%** vs HTTP/2 **56.4%**。文末明确写道 QUIC/HTTP3 **"托管成本（CPU 时间与内存）高于 TCP 和 HTTP/2"**，大厂是用业务收益抵掉的。 | 工业测量（非同行评审） |
| 02-C18 | Implementation and Analysis of QUIC for MQTT | Puneet Kumar, Behnam Dezfouli (Santa Clara U.) | 2018 / arXiv | arXiv:1810.07730 | — | 资源受限（IoT）设备上的 QUIC vs TCP/TLS 实测：量化了 QUIC 在端侧的握手与记录层开销，是少见的"端侧资源占用"对照。 | S2元数据（摘要） |
| 02-C19 | An update on QUIC adoption and traffic levels | CellStream（二手汇总） | 2025 / CellStream Blog | https://www.cellstream.com/2025/02/14/an-update-on-quic-adoption-and-traffic-levels/ | — | 汇总口径：2025 年约 35-40% 网站宣告支持 HTTP/3，大平台流量占比远高（Meta 2020 年即 >75%）。**仅作背景，不作技术结论引用。** | 工业测量（二手，可信度低） |
| 02-C20 | （非正式）Netflix 工程师关于 QUIC 服务成本的口述 | 自称 Netflix 工程师的 HN 用户 `drewg123` | 2021-01-30 / Hacker News | https://news.ycombinator.com/item?id=25970258 | — | 广为流传的一段：Netflix 静态视频场景下，因为 QUIC 失去 TSO/LRO/软件 kTLS，同样机器从 **90 Gb/s @ 62% CPU 掉到 35 Gb/s 并被 CPU 限死，等于要多 3 倍服务器**。**身份与数字均未能在正式出版物中核实，仅作线索**（正式可引版本见 E 节 Netflix 的 kTLS 论文）。 | 待核实（工业界口述，非正式） |
| 02-C21 | A CPU+DCU / QFAM 等 QUIC 握手洪水与重试类工作 | Jiahao Wu (TurboRetry) 等 | 2024-2026 / arXiv | arXiv:2608.02264（TurboRetry）· arXiv:2412.08936（QFAM） | 0 / 3 | QUIC 握手期的**非对称 CPU 消耗**本身被当成攻击面（握手洪水能靠少量客户端 CPU 打爆服务端），TurboRetry 用**现成 DPU 卸载**缓解。→ 说明"QUIC 的 CPU 成本可从威胁侧量化"，是横评之外的一个可引用的旁证。 | S2元数据 + 仅摘要 |

---

## D. HPACK / QPACK：串行依赖的固有代价

| 编号 | 标题 | 一作/机构 | 年/出处 | arXiv·DOI·URL | 引用数 | 一句话结论（含关键数字） | 核验状态 |
|---|---|---|---|---|---|---|---|
| 02-D1 | 规范层面的串行依赖（汇总 A1+A2+A4 三条） | IETF | 2015 / 2022 | RFC 7540 §4.3 · RFC 7541 §2.2/§7.1 · RFC 9204 §2.2.1 | — | 三重叠加：(1) HPACK 动态表**每连接一份**且由编码器驱动修改，解码器只能顺序执行；(2) HTTP/2 要求 header block 以**连续帧序列**传输、不得被其他流插入，等价于强制"按到达顺序解码"；(3) QPACK 把表更新搬到独立 encoder 流后仍有 **blocked decoding**，必须用 SETTINGS 限量。→ 结论：两代头压缩都是**有状态、按连接串行的状态机**，天然不友好于流水化/并行化硬件。 | 实测fetch（RFC 原文） |
| 02-D2 | Denial-of-Service Attack Against the HTTP/3 Stack via QPACK Blocked Decoding（安全公告） | Envoy Proxy 项目 | 2025 / GitHub Security Advisory GHSA-p7c7-7c47-pwch | https://github.com/envoyproxy/envoy/security/advisories/GHSA-p7c7-7c47-pwch | — | 现实实现里 blocked decoding 的代价被量化到位：header block 一旦因缺少动态表项而阻塞，**QPACK 解码器内部堆缓冲仍持有这些字节，而 QUIC 流控却已把额度归还对端**，且"阻塞流数量上限只约束并发数、不约束每个被阻塞块的驻留大小"→ 攻击者可无界撑大内存导致 OOM。→ **"串行依赖"在实现上等于"必须缓存住等待的表状态"**，这是硬件实现要背的状态量。 | 工业测量（安全公告，非论文） |
| 02-D3 | Exploring HTTP/2 Header Compression | Kazuhiko Yamamoto 等 | 2017 / ACM CFI | DOI:10.1145/3095786.3095787 | 2 | 少数直接以 HPACK 头压缩本身为对象的研究（压缩行为/效果分析），**未见 CPU 占比量化**。 | S2元数据 |
| 02-D4 | QMIN / Header Compression for QUIC 等早期 QUIC 头压缩提案 | D. Tikhonov / C. Krasic 等 | 2017-2018 / IETF draft | （无 DOI，见 S2 记录） | 0 | QPACK 之前的候选设计（QMIN 等），记录了"QUIC 乱序 → 头压缩必须重新设计"这一过程。 | S2元数据 |
| 02-D5 | Comparison of HTTP 2 Header Compression Methods | Oleksandr Ulichev 等 | 2024 / 乌克兰农业机械类期刊（非 CS 主流） | DOI:10.32515/2414-3820.2024.54.106-116 | 0 | 标题相关但载体与可信度都很低，**不引用其结论**，仅登记以防重复检索。 | S2元数据（低可信） |
| 02-D6 | Same Standards, Different Decisions（再次，从 QPACK 角度） | Robin Marx 等 | 2020 / EPIQ@SIGCOMM | DOI:10.1145/3405796.3405828 | 70 | 15 个实现对比中发现 QPACK 相关行为（表大小、blocked stream 限额、是否用 post-base 索引）在实现间差异很大 → 说明头压缩成本**实现依赖极强**，不存在"协议的 HPACK/QPACK 开销"这一单一数字。 | 仅摘要 |

> **本节的明确缺口**：本次检索（S2 关键词 6 组 + arXiv 2 组）**没有找到任何一篇量化 HPACK 或 QPACK 编解码在总 CPU/时延中占比的论文**。唯一能给出量级的是 C1（"每包一个 STREAM 帧"级优化省 5%，属帧层而非头压缩层）。这条空白建议用户重点核实是否值得作为切入点。

---

## E. 加密与 TLS 的成本占比、以及卸载手段的数字

| 编号 | 标题 | 一作/机构 | 年/出处 | arXiv·DOI·URL | 引用数 | 一句话结论（含关键数字） | 核验状态 |
|---|---|---|---|---|---|---|---|
| 02-E1 | QTLS: high-performance TLS asynchronous offload framework with Intel QuickAssist Technology | Xiao-Kang Hu (Alibaba) 等 | 2019 / ACM PPoPP | DOI:10.1145/3293883.3295705 | 16 | 直接卸载 crypto 会因"offload I/O 长阻塞"导致 CPU 与加速器双双闲置；QTLS 把 TLS 卸载拆成四阶段消除阻塞 + 内核旁路事件通知，实测 **CPS 最高 9x（RSA-2048）、安全传输吞吐 2x、平均响应时间降 85%**。→ 卸载不是"把 crypto 丢给硬件"就完事，**调度与通知路径才是瓶颈**。 | 实测fetch（摘要原文） |
| 02-E2 | Unlocking Security to the Board: An Evaluation of SmartNIC-driven TLS Acceleration with kTLS | Felipe Novais, F. Verdi (UFSCar) | 2024 / IEEE-IFIP NOMS | DOI:10.1109/NOMS59830.2024.10575053 | 4 | 系统比较软件 kTLS 与硬件加速模式（TOE、Chelsio T6 协处理器）对 CPU 时间、功耗、网络速率的影响，是"SmartNIC 做 TLS"最贴近用户命题的学术评测。 | 实测fetch（摘要原文） |
| 02-E3 | kTLS Offload Performance Enhancements for Real-life Use Cases（netdev 0x14 论文） | NVIDIA/Mellanox 作者组 | 2020 / netdev 0x14 | https://netdevconf.info/0x14/pub/papers/29/0x14-paper29-talk-paper.pdf | — | 用 NVIDIA ConnectX-6Dx + Nginx 对比软件 kTLS 与硬件 kTLS 卸载：**单 TCP 流 >2.5x 加速；8 流时软件 kTLS 卡在约 50 Gbps 而硬件卸载直接打到 100GbE 线速；在两者都能线速的场景，硬件卸载 CPU 低 50-60%**。 | 工业测量（会议论文，非同行评审期刊） |
| 02-E4 | Improving High-Bandwidth TLS in the FreeBSD kernel | Randall Stewart, Scott Long (Netflix) | 2017 / AsiaBSDCon | https://openconnect.netflix.com/publications/asiabsd_tls_improved.pdf | — | Netflix OpenConnect 上的内核 TLS 演进史与多种批量加密实现对比；2015 年论文指出内核加密"可行但增益有限"，本篇记录后续把成本压下来的过程。 | 工业测量（会议论文） |
| 02-E5 | Serving 100 Gbps from an Open Connect Appliance（Netflix 技术博客） | Netflix | — / Netflix Tech Blog | https://netflixtechblog.com/serving-100-gbps-from-an-open-connect-appliance-cdb51dda3b99 | — | 给出 Netflix 侧的关键分界：在 kTLS/卸载之前的软件 TLS 只能做到约 **58 Gbps**，之后才达到 100 Gbps 目标。可作"TLS 软件成本 ≈ 半条 100G 线"的工业证据。 | 工业测量（非同行评审） |
| 02-E6 | TLS Offload to Network Devices | Boris Pismenny, Ilya Lesokhin, Liran Liss, Haggai Eran (Mellanox) | 2016 / Netdev 1.2 | （S2 记录：Netdev 1.2） | 1 | "把 TLS 卸载到网卡"的早期系统性论述，后被 netdev 0x14（E3）延伸。 | S2元数据 |
| 02-E7 | KTLS: Linux Kernel Transport Layer Security | David Watson | 2016 / Netdev | （S2 记录，无 DOI） | 9 | Linux 内核 TLS 的原始设计说明。 | S2元数据 |
| 02-E8 | 由 C11 反推的 TLS 记录层占比 | Fastly（同上 C11 数据） | 2020 / Fastly Blog | https://www.fastly.com/blog/measuring-quic-vs-tcp-computational-efficiency | — | 同一台机器上裸 TCP 708 Mbps → TLS1.3/TCP 466 Mbps，即**TLS 记录层加密成本约占该栈总成本的 1/3（466/708 = 66%，损失 34%）**；这是本文件里唯一可直接给出的"加密占栈内比例"数字。 | 工业测量（由数字反推） |
| 02-E9 | Enhanced Performance and Privacy for TLS over TCP Fast Open | Erik Sy (Univ. Hamburg) | 2020 / PoPETs | arXiv:1905.03518 · DOI:10.2478/popets-2020-0027 | 13 | 小流占 Web 流量多数，TCP 三次握手与 TLS 握手是主要固定成本；TFO 可显著降低该成本。→ 支撑"握手成本不能忽略，且 0-RTT 的收益要打折看（有重放风险）"。 | 实测fetch（arXiv 摘要页） |

---

## F. 硬件卸载方向的邻居工作（FPGA / SmartNIC / DPU）

| 编号 | 标题 | 一作/机构 | 年/出处 | arXiv·DOI·URL | 引用数 | 一句话结论（含关键数字） | 核验状态 |
|---|---|---|---|---|---|---|---|
| 02-F1 | Strega: An HTTP Server for FPGAs | Fabio Maschi, Gustavo Alonso (ETH Zurich) | 2023 / ACM TRETS | DOI:10.1145/3611312 | 2 | **最危险的邻居**：开源轻量 HTTP 服务器直接跑在 FPGA 上，单节点 **1.7 M HTTP req/s、端到端时延低至 16 µs**，在这两个指标上**打败 32 vCPU 上的 nginx**，并可作为 PCIe/OpenCL 之外调用 FPGA 加速函数的 RESTful 通道。注意：它是 **HTTP/1.1 语义**，不涉及 HPACK/QPACK/多路复用。 | 实测fetch（摘要原文） |
| 02-F2 | F4T: A Fast and Flexible FPGA-based Full-stack TCP Acceleration Framework | Junehyuk Boo (KAIST) 等 | 2023 / ISCA | DOI:10.1145/3579371.3589090 | 13 | FPGA 全栈 TCP 加速：**仅用 2 个 CPU 核就吃满 100 Gbps**，跑 Nginx 时**省 64% 的 CPU 周期**、把 2.8x 的 CPU 周期还给应用。→ "把传输层搬进 FPGA"已被做到工业级指标，用户再证明一次没有增量。 | 实测fetch（摘要原文） |
| 02-F3 | CFcoQUIC: CPU/FPGA Co-design Accelerated QUIC for Low-Power IoT Communication | Xin Dong (BJTU) 等 | 2025 / IEEE ICCCN | DOI:10.1109/ICCCN65249.2025.11133951 | 0 | 目前找到**唯一直接做"QUIC + FPGA"的工作**，但只做**握手期加解密并行化**：FPGA 上 RSA 加解密比 CPU **至少快 19.1x**，AES **至少快 5x**。不涉及数据面、不涉及 HTTP/3 语义、不做三代对比。 | 实测fetch（摘要原文） |
| 02-F4 | TurboRetry: Mitigating Large-Scale QUIC Handshake Floods with Off-the-Shelf DPU Offloading | Jiahao Wu 等 | 2026 / arXiv | arXiv:2608.02264 | 0 | 用现成 DPU 卸载 QUIC 握手以抗洪水；是"QUIC → DPU"路线的最新实例。 | 仅摘要 |
| 02-F5 | FpgaNIC: An FPGA-based Versatile 100Gb SmartNIC for GPUs | Ze-Ke Wang 等 | 2022 / USENIX ATC | （S2 记录：USENIX ATC 2022） | 58 | FPGA SmartNIC 作为通用卸载平台的代表作，是"板卡能力上限"的引用源。 | S2元数据 |
| 02-F6 | Beehive: A Flexible Network Stack for Direct-Attached Accelerators | Katie Lim 等 | 2024 / IEEE MICRO | arXiv:2403.14770 · DOI:10.1109/MICRO61859.2024.00037 | 5 | 为"直连加速器"设计的可编程网络栈（在 FPGA 上提供 socket 抽象），减少 CPU 参与与内存拷贝。→ 与用户的"在加速器上终止应用层协议"命题高度相邻。 | S2元数据（摘要） |
| 02-F7 | SmartNS: Enabling Line-rate and Flexible Network Stack with SmartNIC | Xu-Zheng Chen 等 | 2026 / ACM EuroSys | DOI:10.1145/3767295.3803594 | 0 | 最新一代 SmartNIC 网络栈卸载（线速 + 灵活性），是"卸载到网卡"路线 2026 年的基线。 | S2元数据 |
| 02-F8 | Fast userspace packet processing | Tom Barbette 等 (KTH) | 2015 / ACM ANCS | DOI:10.1109/ANCS.2015.7110116 | 216 | 用户态包处理的奠基综述/评测（DPDK、netmap、PF_RING 等），是"每包成本主要由谁决定"的引用源。 | S2元数据 |
| 02-F9 | Understanding Delays in AF_XDP-based Applications | Killian Castillon du Perron 等 | 2024 / IEEE ICC | arXiv:2402.10513 · DOI:10.1109/ICC51166.2024.10622351 | 5 | AF_XDP 相对 DPDK/内核路径的时延来源分解，是"内核旁路能省多少、还剩多少"的定量参考。 | S2元数据 |
| 02-F10 | OXDP: Offloading XDP to SmartNIC for Accelerating Packet Processing | Feng Wang 等 | 2022/2023 / IEEE ICPADS | DOI:10.1109/ICPADS56603.2022.00103 | 8 | 把 XDP 程序整体下沉到 SmartNIC，是"eBPF/内核旁路 → 网卡"的直接前作。 | S2元数据 |

---

## 本子领域结论

### ① 三代协议 CPU / 吞吐 / 延迟的数字对照表

> 说明：三代协议**不存在统一的"核/Gbps"公开数字**（见空白 ②）。下表把能核实的量级放进来，并标注每个数字的实验条件，**跨行不可直接相减**。

| 对比维度 | HTTP/1.1（TCP） | HTTP/2（TCP+TLS1.3） | HTTP/3（QUIC） | 来源与条件 |
|---|---|---|---|---|
| 受控单核吞吐上限（无硬件卸载） | 裸 TCP **708 Mbps** | TLS1.3/TCP **466 Mbps**（=裸 TCP 的 66% → **TLS 记录层约占栈内 1/3**） | 未调优 quicly **196 Mbps**（=TLS/TCP 的 40%）；调优后（延迟 ACK + UDP GSO + 1460B 包）**464 Mbps，追平 TLS/TCP** | C11，单核限频 400 MHz + Gbit 网口，Fastly |
| 10G 链路上 goodput | TCP 开 NIC offload + AES-NI 约 **8000 Mbit/s** | — | 各实现 **90 – 4900 Mbit/s**（相差 50 倍以上）；QUIC 从 NIC offload/AES-NI 得到的增益明显小于 TCP | C3，Jaeger et al., IFIP Networking 2023 |
| 单实现 UDP 发送路径成本 | TCP sendmsg 基准 1x | — | Linux **UDP sendmsg 的 cycle/byte 最高为 TCP 的 3.5 倍**；UDP 发送占其服务负载 CPU 的 25%，部分环境 >50% | C1，Ian Swett（Google）EPIQ 2020 |
| CPU 花在哪 | 内核态，连接状态复用、TSO/GRO 可用 | 与 H1.1 同栈，额外 TLS 加密成本 | **70-80% 花在 socket 层（sendto/recvfrom/sendmsg/recvmsg）**；crypto、包重排序次之 | C13 Huitema；C2 Yang et al. |
| 服务端 CPU/比特（相对 TCP 的倍数） | 1x（基准） | ≈1x（同栈，仅加 TLS） | 业界引用值 **约 2x**（Google SIGCOMM'17，**原文未核到**）；用户态实测区间 **1.4x–3.5x** 取决于实现与 offload 开关 | A8（待核实）；C11 反推（196/466 → 单位吞吐 CPU 约 2.4x）；C12/C13 |
| 内核态对比（Linux 在研内核 QUIC） | 裸 TCP 基准 | 内核 kTLS 吞吐约为内核 QUIC 的 **约 3 倍** | 关掉 1-RTT 加密后，裸 TCP 在部分用例比 QUIC 快 **>4 倍**；原因：缺 GSO、TX 多一次拷贝、头部额外加密 | C9 / C10 |
| 内核旁路能带来的改善 | — | — | DPDK 化 picoquic **3x** 并追平 TCP+TLS（C4）；4 个实现 DPDK 化最高 **3x、>10 Gbit/s**，但其中一个无改善，"若系统提供 offload 也可达类似性能"（C5） | C4（CoNEXT SW 2022）、C5（NOMS 2026） |
| 页面加载时间（真实 CDN） | 基准（本文件未收 H1.1 的 CDN 数字） | 15KB 页 **458 ms**；1MB 页 **2.30 s**；TTFB **201 ms** | 15KB 页 **443 ms**；1MB 页 **2.33 s**；TTFB **176 ms**；北美/欧洲/亚洲/南美平均**仍落后 H2 约 1-4%** | C16，Cloudflare 自测（拥塞控制不一致，H2 用 BBR v1、H3 用 CUBIC） |
| 高速网络数据率（H3 vs H2） | — | 基准 | 最多 **-45.2%**（视频码率 -9.8%），带宽越高差距越大 | B5，WWW'24 |
| 慢网/高 RTT 场景 | — | 基准 | HTTP/3 优势显著（多篇一致）；**视频流媒体暂无收益** | B7/B8/B23 |
| 队头阻塞 | 传输层 HoL，单连接串行 | 应用层多流，但 **TCP 层 HoL 仍在**（丢包阻塞所有流） | 流级隔离，无跨流 HoL；换来 **QPACK blocked decoding**（表状态未齐则该流头部无法解码，字节须缓冲） | A1/A3/A4、D1/D2 |
| 握手 | TCP 3WHS + TLS 握手（两个 RTT 量级） | 1-RTT（TLS1.3 完整握手；TLS early data 在 HTTP/2 上鲜有部署） | 1-RTT / **0-RTT 复用**；Initial 包触发服务端非对称 CPU 消耗，被用作 DoS 面 | A5/A7、C21 |
| 头部压缩的硬件友好性 | 无（明文文本，可任意解析/并行） | **HPACK**：每连接动态表 + header block 必须连续传输 → 按连接串行解码 | **QPACK**：表更新走独立 encoder 流（可解耦），但引入 blocked decoding 与"必须缓存等待中的头块" | A1/A2/A4、D1/D2 |
| 头压缩的 CPU 占比 | 未找到 | **未找到** | **未找到**（本次检索零命中） | 见空白 ① |

### ② 关键发现（7 条）

1. **"QUIC 比 TCP 贵几倍"已经收敛，且公认的瓶颈不是加解密。** Google（Swett, EPIQ 2020）公开拆解显示 **UDP 发送占 25%~>50% CPU、`sendmsg` 每字节周期数最高为 TCP 的 3.5 倍**，接收侧瓶颈在"内核上送的包过多 + 用户态 ACK"（WWW'24 独立复现）；Huitema 的 flame graph 显示 **70-80% 时间在 socket 层**。所以"瓶颈是 AES"这个直觉是错的（这是 2019 年业界自己的判断失误）。
2. **但这个倍数有一半来自"没优化"，不是协议固有：** 只加延迟 ACK + UDP GSO + 把包长从 1280 提到 1460，quicly 就从 196 Mbps 涨到 464 Mbps（打平 TLS/TCP）；Cloudflare 用 `sendmmsg`+GSO 把 640 Mbps 做到 1.6 Gbps；再加硬件 GSO 还有 2-3x。**含义：任何"QUIC 慢 N 倍"的横评数字，不写清实现版本与 offload 开关就没有意义**——这正是审稿人最可能攻击的点。
3. **不要假定"必须内核旁路/上硬件才快"。** NOMS 2026 把 4 个实现改成 DPDK 后最好 3x，但**其中一个毫无改善**，作者明确写"如果系统提供 offload 且实现正确使用，也能达到类似性能"。反过来说，用户的 FPGA 方案**必须先给出同机的 DPDK/内核旁路基线**，否则无法把加速归因到"硬件卸载"。
4. **把 QUIC 搬进内核并不能自动解决**：Linux 在研内核 QUIC 的基准显示它比内核 kTLS 还慢约 3 倍、比裸 TCP 慢 >4 倍（关掉 1-RTT 加密时），原因依旧是**缺 GSO、TX 多一次拷贝、头部要额外加密**。→ 成本大头是"每包被触摸的次数"，不是"内核 vs 用户态"这个二分法。这与 EPIQ 2020 的结论完全一致。
5. **头压缩是"有状态串行状态机"，是硬件化最难受的一块。** HPACK 每连接一张动态表且由编码器驱动、解码器顺序执行（RFC 7541），HTTP/2 又强制 header block 连续传输（RFC 7540 §4.3）；QPACK 用独立 encoder 流解耦了更新，但付出 blocked decoding（RFC 9204 §2.2.1）的代价，且现实中已导致"阻塞期间头块字节必须驻留堆内、流控却已归还额度"的 OOM 漏洞（Envoy 安全公告）。**推论：任何想在硬件里做 HTTP/2 或 HTTP/3 的方案，都必须为"每连接动态表 + 等待中的头块缓冲"预留片上/片上外存储，这是三代协议里唯一的"必然状态量"。**
6. **端到端三代横评已经被做烂，且结论互相打架，差异主要来自实现与拥塞控制而非协议名**：H3 有"只在高延迟/差带宽才赢"（MedComNet'21、Comput.Commun.'22，视频无收益）、"平均吞吐更高但多数 QoE 指标更差"（ICC'21 Lighthouse）、"快网下最多慢 45.2%"（WWW'24）、"自家 CDN 上平均还落后 1-4%"（Cloudflare 自测，混杂 BBR vs CUBIC）。加上 EPIQ'20 的 15 实现异质性研究，**同一句"HTTP/3 比 HTTP/2 快/慢 X%"几乎不可证伪**。
7. **加密成本占比可给出一个可用数字：TLS 记录层约占栈内 1/3**（Fastly：裸 TCP 708 → TLS1.3/TCP 466 Mbps）。它的**卸载收益是明确且已被量化的**：QAT 异步卸载 2x 吞吐 / 9x CPS / 85% 时延下降（QTLS, PPoPP'19）；NIC 硬件 kTLS 单流 2.5x、8 流 50→100 Gbps、并能省 50-60% CPU（netdev 0x14）；Netflix 软件 TLS 约 58 Gbps 是 100G 目标的拦路石。**但注意 QUIC 的加密不是"TLS 记录层"**，而是每包两遍对称操作（header protection），无法照搬 kTLS 的卸载形态。

### ③ 明确空白

1. **HPACK/QPACK 编解码在总 CPU/时延中的占比：零篇量化。** 本次用 6 组 S2 关键词 + 2 组 arXiv 查询均未命中。能沾边的只有"每包一个 STREAM 帧省 5%"（帧层，非头压缩）。
2. **没有公开、可比的"核/Gbps"或"核/Tbps"成本模型。** 现有数字都是"某实现 + 某机器 + 单流 + 某开关状态"，最多能横比到同论文内部（如 C3、C5），跨论文不可加。
3. **缺"同一台服务器上 H1.1/H2/H3 三栈并排"的受控测量**，尤其是把 offload（GSO/GRO/sendmmsg/AES-NI/kTLS/硬件卸载）作为**因子**而非"顺便开着"的实验设计。现有 CPU 数据要么来自 QUIC 单方，要么来自发送端 microbenchmark。
4. **HTTP/2 或 HTTP/3 全栈的硬件卸载（FPGA/SmartNIC）基本不存在。** 找到的全部是：HTTP/1.1 上 FPGA（Strega, F1）；TCP 全栈上 FPGA（F4T, F2）；QUIC **握手加解密**上 FPGA（CFcoQUIC, F3）；QUIC 握手上 DPU（TurboRetry, F4）。**没有一篇做 QPACK/流调度/连接状态在硬件上的实现与代价分析。**
5. **能耗对照缺失**：只找到零散的移动端/视频流能耗工作（如 QUIC over MQTT for IoT, C18），没有三代协议在同一硬件上的能耗-吞吐对照曲线。
6. **接收侧 vs 发送侧的不对称**：WWW'24（B5）明确指出业界已有工作几乎都只优化**发送侧**、且方法论不可复现（例如 Cloudflare 的客户端与服务端跑在同一台笔记本上）。接收侧的 CPU 归属仍是被点名的开放问题。

### ④ 对"横评三代协议"这个点子的告诫

**已经被做过、重做没有增量的对比：**
- "跑 h2load/wrk/curl-quic 各打一遍，比吞吐、CPU%、页面加载时间" —— IMC'17（B1）、CACM'19（B2）、IMC'24 复现（B3）、ANRW'19（B10）、WWW'24（B5）、MedComNet'21（B7）、Comput.Commun.'22（B8）、ICC'21（B9），外加 Google/Cloudflare/Meta/Fastly/Akamai/Netflix 一整圈工业测量。**这一层已经饱和。**
- "QUIC 比 TCP CPU 贵多少、贵在哪" —— 发送侧拆解（Google EPIQ'20, C1）、接收侧拆解（WWW'24, B5）、内核侧拆解（LWN/内核补丁, C9/C10）、nic 卸载原语拆解（EPIQ'20, C2）**都有人做了**。
- "内核旁路能救 QUIC" —— picoquic-dpdk（C4, 3x）和 NOMS 2026（C5, 4 个实现, 最高 3x）已经把这条结论钉死，且 C5 给了反向证据（有实现无改善、offload 可等价）。

**已成共识、不能当作新发现的数字：**
- QUIC 每比特 CPU 成本高于 TCP（多个独立来源，区间约 1.4x–3.5x，取决于实现与 offload）；
- 优化手段就是"降 ACK 频率 + UDP GSO + 大包 + 内核旁路"，效果 2-3x；
- QUIC 在**高 RTT/丢包**下胜、在**干净高速链路**上不一定胜，甚至可能输 45%；
- TLS 记录层约占栈内 1/3，卸载后可回收。

**最危险的邻居（必须正面处理，否则被一句话驳回）：**
1. **Strega（TRETS'23, F1）** —— "首次把 HTTP 服务搬上 FPGA"这个说法会被它直接否决：1.7M req/s、16 µs、胜过 32 vCPU nginx。**用户必须把自己的对象明确限定为 HTTP/2 或 HTTP/3，并说清相对 Strega（HTTP/1.1 + 简单解析）新增的协议状态复杂度代价。**
2. **F4T（ISCA'23, F2）/ Beehive（MICRO'24, F6）/ FpgaNIC（ATC'22, F5）** —— "在 FPGA 上卸载传输层/网络栈"已到 100 Gbps / 2 核 / 省 64% CPU 周期的工业级水平。用户若把 TX/RX 通路或 TCP 卸载算作贡献，等于重做。
3. **picoquic-dpdk（C4）+ Kernel Bypass Surgery（C5）** —— 不能假定"FPGA/SmartNIC 一定比 DPDK 快"。**必须先给同机 DPDK 基线**，否则无法把加速归因到硬件。
4. **EPIQ'20 Ian Swett（C1）+ WWW'24（B5）** —— QUIC 的 CPU 拆解（发送侧 + 接收侧）已被做完，用户如果要"再拆一次"必须换视角。
5. **CFcoQUIC（F3）** —— 已经有人做"QUIC 握手加解密上 FPGA"。用户若重复做握手加速，只有 19.1x/5x 这两个已知倍数可对比，增量极低。

**唯一看起来有增量的切口（供主代理决策，非本调研的结论）：**
把命题从"**三代协议谁快**"改成"**三代协议各自的 CPU 成本项中，哪些能被硬件消除、哪些不能被消除，以及不可消除部分的下界是多少**"。具体地：
- 可消除项（有先行证据）：syscall/上下文切换与数据拷贝（内核旁路, C4/C5/F1）、批量分段与校验（GSO/TSO, C1/C12）、对称加密（QAT/kTLS, E1/E3）。
- **不可消除项（尚无硬件实现研究，是真空）**：每包强制的 header protection 两遍对称加密（A5）、HPACK/QPACK 的每连接串行状态机与等待头块缓冲（A1/A2/A4, D1/D2）、流控/重传/拥塞控制状态（A6）。
- 一个可落地的形态：在 FPGA 上实现"QUIC 包保护 + QPACK 串行状态机"这两个**不可消除项**的最小原型，量化它们的**每 GB 周期数下界**，并与纯软件栈（quicoquic/quiche）逐项对照。这类"成本分解模型 + 下界测量"比"三代横评谁快"更容易在 CCF-B 上站住，因为它不依赖跨实现的可比性，也就绕开了本文第 ③ 条最致命的空白。

---

### 检索局限说明（供后续会话避免重复劳动）

- **Semantic Scholar 频繁 429**：本次 S2 共发起约 20 次检索，约 5 次触发限流，已用指数退避重试并降速至 5-7 s/次；仍有 2 条元数据（DOI:10.1145/3611312 首次、DOI:10.1145/3293883.3295705 首次）需补查，后已补到。
- **Netdev / openwall 邮件列表正文抓取失败**：C10 的补丁自带性能表只拿到检索快照，数字已在文中标 `待核实`。
- **未阅读全文的条目**：除标 `实测fetch`（含 arXiv 摘要页）外，其余为 `S2元数据`/`仅摘要`，其结论句来自官方摘要，未经全文复核。
- **未做的事**：没有下载任何 PDF 全文；没有做 S2 正向/反向滚雪球（时间预算用在了三代协议本体的数字核验上）。若后续需要，建议以 C1（Swett EPIQ'20）、B5（WWW'24）、C9（内核 QUIC）三篇为中心做引文滚雪球。
- **工业测量类的可信度分级**：本文件中 `工业测量` 标注的一律非同行评审；其中 CellStream（C19）、blazingcdn 类二手营销博客**已刻意不采用其数字**；HN 口述（C20）已标 `待核实`，正式引用请改用 E3/E4/E5。
