# HTTP/1·2·3 协议栈硬件卸载调研（HTO 专题）

> **缘起**：用户提出点子——"测试 HTTP/1.1（TCP）、HTTP/2（TCP+HPACK）、HTTP/3（QUIC）三代协议在卸载到 FPGA / 智能网卡的情况下，在特定/通用场景下的性能、吞吐量、占用等指标对比"；随后把参比平台扩展为**三类卸载载体**：**FPGA（XCVU13P）**、**DPU / SmartNIC（BlueField）**、**SoC 内置加速器（RK3588）**。
> **创建**：2026-10-05。**本文是持续更新的综述**，不是一次性清单。
> **原始笔记**（本轮 262 条，远多于本表）：
> - `_raw/02-HTTP三代协议开销实测.md`（79 条：协议本体规范 / 端到端横评基线 / QUIC CPU 拆解 / HPACK-QPACK / TLS 加密 / 硬件邻居）
> - `_raw/03-L7硬件卸载现状.md`（100 条：HTTP 服务端 / TLS / QUIC / DPU / 可编程交换机 / 平台基础）
> - `_raw/04-卸载方法论与资源核算.md`（34 条：卸载方法论范本 / 资源能耗口径 / CCF-B 测量类先例 / CCF 场馆逐条核对）
> - `_raw/05-RK3588平台能力与边缘卸载.md`（49 条：RK3588 crypto 引擎源码级核查 / ARM 侧 HTTP-QUIC 既有工作 / 差异化判断）
> **交叉去重**：与既有主题不重复登记的有——`DBK-15 FlexTOE`、`DBK-46 Characterizing Off-path SmartNIC`、`DBK-47 Demystifying DPA`、`DBK-48 BF idiosyncrasies`、`DBK-49 PCIe`、`DBK-53 Honeycomb`、`WTP-54 The Cost of the S in HTTPS`、`NIAC2026-4 NetCache`、`NPD-2 OrbitCache`、`CGC-18 Scallop`、`KVT-10 Tiara`（同名不同篇，已注）。
> **检索局限**：S2 大面积 429；ACM DL / ScienceDirect 正文 403；`WebSearch` 在本环境 403（改用 Tavily + 官方页直抓）；DBLP 被反爬；**四路均未做引用滚雪球**。**"没找到" ≠ "不存在"**。

---

## 0. 结论速览

1. **原命题（三代协议栈都进硬件、同平台横评）在技术前提上大部分不成立。** 三个结构性障碍：① **QUIC 的包头本身被加密**，硬件不解密就看不到帧类型与流 ID，因此 QPACK 与 HTTP/3 帧层**无法成为独立的硬件模块**（把它单独抽出硬件化在语义上就错了）；② **HPACK 是每连接一份动态表 + header block 强制连续传输**（RFC 7541 §2.2、RFC 7540 §4.3），是有状态串行状态机，与流水线硬件天然不合；③ **PCIe 墙**——Gen3 x8 的 TLP 层上限 57.88 Gb/s、实测常 ≤50 Gb/s（SIGCOMM'18 原文），若 FPGA 靠主机喂包，**协议代际差异会被 PCIe 上限吞掉**。
2. **"横评"本身不是贡献，而且软件侧已被做烂。** IMC'17、CACM'19、IMC'24 复现、ANRW'19、WWW'24、MedComNet'21、Comput.Commun.'22、ICC'21，外加 Google/Cloudflare/Meta/Fastly/Akamai 一整圈工业测量。**已成共识的数字**：QUIC 每比特 CPU 成本是 TCP 的 1.4–3.5×（取决于实现与 offload 开关，不是协议固有）；优化手段就是"降 ACK 频率 + UDP GSO + 大包 + 内核旁路"（2–3×）；QUIC 只在高 RTT/丢包下胜，干净高速链路上可能**慢 45.2%**（WWW'24）。
3. **有一条比"谁快"好得多的主线，而且被文献结构本身支持：可卸载性随协议代际单调下降。**
   - HTTP/1.1 请求解析：**无状态、明文、可枚举** → 硬件最友好（Strega 已证：FPGA 上 1.7 M req/s、16 µs）
   - HTTP/2 HPACK：**明文但每连接串行状态机** → 硬件不友好，且**零前人工作**
   - HTTP/3 QPACK：**被 QUIC 头加密阻断** → 不可独立硬件化，只能给"不可卸载下界"
   而**恰好相反**：软件 CPU 成本随代际**上升**（QUIC 最贵）。即 **"成本最高的那一代，恰恰是最难卸载的那一代"** —— 这是一条可证伪、有机制解释、且可用现有数字量化的**卸载悖论**。
4. **三类平台其实是"卸载载体谱系"的三个档位**：可编程逻辑（FPGA，能做 RTL）→ 通用核 + 专用加速器（DPU，能做状态机）→ **纯专用加速器（RK3588，只有 crypto 引擎）**。用同一套判据测这三档，"卸载边界"就不是空话。
5. **最重要的负面证据（必须写进论文动机）**：RK3588 的硬件 crypto 引擎**比同一颗芯片的 CPU 指令慢 5.7×**（AES-256-GCM：引擎 310 MB/s vs 一个 A76 核 1,763.9 MB/s），且 Rockchip 把驱动内核注册优先级设为 **0**（ARMv8 `gcm-aes-ce` 是 **300**），因此 **kTLS 永远不会选硬件引擎**（源码级证据）。**"换个专用硬件就更快"这个默认假设是被证伪的。**
6. **真空白（按可信度排序）**：① "硬件卸载下的三代协议统一横评"——arXiv + S2 双通道零命中；② **HPACK/QPACK 编解码的 CPU 占比：零篇量化**；③ **"卸载边界/代价模型"**——Clara（HotNets'20）明确点出、至今无成熟答案；④ ARM SoC × 三代协议 × 硬件 crypto 卸载——零命中；⑤ **没人测过 RK3588 crypto 引擎在 TLS/QUIC 负载下的表现**（连 2026 年的专业评测都写 "the dedicated accelerator's throughput remains unmeasured"）。
7. **场馆须按官方第七版目录修正**：❌ **TACO 是 A 类不是 B**；❌ **PAM 是 C 类**；**TMA 与 ACM CCR 均未收录**。✅ 可行 B 类：**IMC**（测量最对口）、**ICNP / CoNEXT**、**FPGA / ICCD / DATE**、**TRETS / Computer Networks / TCC / JPDC**、**ICS**。

---

## 1. 为什么原命题按原样做不行：三个硬约束

### 1.1 约束一：卸载对象必须分层指定，"offload HTTP"不是一件事

"把 HTTP 卸载到硬件"至少包含六个独立的切面，难度、硬件成本、收益差一个数量级：

| 层 | 硬件可行性 | 依据 |
|---|---|---|
| L4 TCP（H1.1 / H2 的载体） | ✅ 现实，但**红海** | AccelTCP（NSDI'20）已把 TCP 状态机卸到网卡；F4T（ISCA'23）FPGA 全栈 TCP 只用 2 核吃满 100 Gbps、省 64% CPU 周期；ContaTOE（IEEE CLOUD'26）仍在做 |
| UDP + QUIC 拥塞控制/丢包恢复 | ⚠️ 半现实 | 包头可解析、ACK/重传可做，但**帧类型与流 ID 在加密区内** |
| TLS 记录层（对称加解密） | ✅ 现实且**已生产化** | kTLS `TLS_HW` + ConnectX-6Dx/BF inline crypto；学术侧 Autonomous NIC offloads（ASPLOS'21）、XTLS（APSys'26） |
| TLS 握手 | ❌ 全行业都没做 | NVIDIA DOCA 官方明写 `HW-record`（含握手）**当前不支持**；Linux 内核文档明写 `TLS_HW_RECORD` **不可用于生产**；ASPLOS'21 的设计就是"握手留软件" |
| HTTP/1.1 请求解析 | ✅ 现实 | Strega（TRETS，开源）整个网络栈 + HTTP 服务端栈进 FPGA，16 µs vs nginx 108 µs |
| **HPACK（HTTP/2）** | ⚠️ 可做但很难，**无前人** | 每连接动态表 + 增量索引 + Huffman；RFC 7540 §4.3 强制 header block 连续传输 |
| **QPACK / HTTP/3 帧层** | ❌ 基本不可行 | QUIC 头加密 → 硬件看不到帧边界；QPACK 依赖 QUIC 单/双向流与乱序语义，**抽出硬件化在语义上就错了** |
| 请求路由（URL/header 匹配） | ✅ 现实 | 正则/多模式匹配在 FPGA 成熟；BF-3 的 RegEx 引擎官方称近 75 Gb/s |
| 缓存 | ❌ 幻想层 | 交换机 8 MB 只放得下 16B key（NetCache）；VU13P 的 57 MB 虽大，但 DDR4 弱、无 HBM |

**结论**：**"三代协议栈横评"里可硬件化的那部分（L4 + TLS 记录层 + H1.1 解析）价值最低且已被占位；不可硬件化的那部分（HPACK/QPACK/帧层）才是有空白的部分。** 这个错位是原命题最根本的问题，也是重构的入口。

### 1.2 约束二：PCIe 与板载内存会先于协议差异饱和

SIGCOMM'18（Neugebauer 等）原文数字（本工作区 **DBK-49**）：Gen3 单 lane 7.87 Gb/s → x8 = 62.96 Gb/s 物理层 → 扣 DLL 8–10% 后 **TLP 层 57.88 Gb/s**，实测可用常 **≤50 Gb/s**。**x16 等比例外推 ≈125.9 / 115.8 Gb/s（外推值，非原文）**。

VU13P 的画像：**算力/片上内存极强（12,288 DSP、片上 ≈455 Mb ≈57 MB）、外部带宽弱（板载 DDR4，无 HBM）、PCIe Gen3 x16**。这有三个直接后果：

- 若让 100 GbE 流量穿过主机再回 FPGA，**PCIe 先饱和**，横评数字区分不出协议差异；
- 正确做法是 **FPGA 直连网络**（片上 100G MAC / 128 路 GTY），PCIe 只走控制面——这也正是 ETH 组 EuroSys'23 poster《Release Your Accelerator From the PCIe Cage!》的论点；
- **每连接状态必须压在片上 57 MB 里**——这个容量恰好是"多并发连接的 HPACK/QPACK 动态表 + 等待中的 header block 缓冲"的尺度，应当成为**代价模型的关键参数**。

### 1.3 约束三：横评的数字会被"实现差异"吞掉

- EPIQ'20《Same Standards, Different Decisions》对比 **15 个** IETF QUIC+HTTP/3 实现，发现流控/拥塞控制/0-RTT/打包行为**高度异质** → 任何"协议 A vs 协议 B"的**单实现**横评都会被这条打掉。
- QUIC on the Highway（IFIP Networking'23）：10G 链路下不同实现 goodput 从 **90 Mbit/s 到 4900 Mbit/s（差 50 倍以上）**。
- IFIP Networking'25：**只换应用层协议（HTTP/3 vs HTTP/0.9）就能让 goodput 掉 27%**；TUM 10GBase-T 上 msquic 5443 / lsquic 2568 / quiche 1847 / picoquic 1445 Mbit/s（**3.8×**）。
- 反过来，QUIC 的"贵"有一半来自"没优化"：Fastly 单核 400 MHz 受控实验，未调优 quicly **196 Mbps** → 延迟 ACK **240** → UDP GSO **348** → GSO 20 包 **431** → 包长提到 1460B **466 Mbps，追平 TLS/TCP**。

**含义**：必须**固定实现或用多实现交叉验证**，并且**把 offload 开关当成实验因子**而不是"顺便开着"。否则任何倍数都不可复现。

---

## 2. 三代协议的成本事实（数字对照表）

> 三代协议**不存在统一的"核/Gbps"公开数字**（见 §5 空白②）。下表把能核实的量级放进来并标注条件，**跨行不可直接相减**。

| 维度 | HTTP/1.1（TCP） | HTTP/2（TCP+TLS1.3） | HTTP/3（QUIC） | 来源与条件 |
|---|---|---|---|---|
| 单核吞吐上限（无硬件卸载） | 裸 TCP **708 Mbps** | TLS1.3/TCP **466 Mbps**（=裸 TCP 的 66% → **TLS 记录层约占栈内 1/3**） | 未调优 quicly **196**；调优后 **464 Mbps，追平** | Fastly 单核 400 MHz（工业测量） |
| 10G 链路 goodput | TCP 开 NIC offload + AES-NI ≈**8000 Mbit/s** | — | 各实现 **90–4900 Mbit/s**；**QUIC 从 NIC offload/AES-NI 得到的增益明显小于 TCP** | Jaeger et al., IFIP Networking'23 |
| 发送路径成本 | TCP sendmsg 基准 1× | — | Linux **UDP sendmsg 的 cycle/byte 最高是 TCP 的 3.5×**；UDP 发送占其负载 CPU **25%，部分环境 >50%** | Swett, EPIQ'20（Google） |
| CPU 花在哪 | 内核态，连接状态复用、TSO/GRO 可用 | 同栈 + TLS | **70–80% 花在 socket 层**（sendto/recvfrom/sendmsg/recvmsg）；内核↔用户态通信、crypto、包重排序次之 | Huitema（picoquic 作者）；Yang et al., EPIQ'20 |
| 服务端 CPU/比特（相对 TCP） | 1× | ≈1× | 业界常引 **约 2×**（SIGCOMM'17 原文未核到）；实录区间 **1.4–3.5×** | Langley SIGCOMM'17（待核实）；Fastly 反推 |
| 内核态 | 裸 TCP | 内核 kTLS 吞吐约为内核 QUIC 的 **约 3×** | 关 1-RTT 加密后裸 TCP 部分用例快 **>4×**；原因：缺 GSO、TX 多一次拷贝、头部额外加密 | Linux 内核 QUIC 补丁自带基准（LWN 报道，工业测量） |
| 高速网络数据率（H3 vs H2） | — | 基准 | 最多 **−45.2%**（视频码率 −9.8%），带宽越高差距越大；根因在**接收侧**（内核上送包过多 + 用户态 ACK） | WWW'24（U. Michigan） |
| 页面加载（真实 CDN） | — | 15KB 页 458 ms；1MB 2.30 s；TTFB 201 ms | 15KB 443 ms；1MB 2.33 s；TTFB 176 ms；四区域平均**仍落后 H2 约 1–4%** | Cloudflare 自测（H2 用 BBR v1、H3 用 CUBIC，混杂） |
| 队头阻塞 | 传输层 HoL | 应用层多流，**TCP 层 HoL 仍在** | 流级隔离，无跨流 HoL；换来 **QPACK blocked decoding** | RFC 7540/7541/9204 |
| 头部压缩的硬件友好性 | 无（明文，可任意解析） | **HPACK：每连接动态表 + 强制连续传输** → 按连接串行 | **QPACK：表更新走独立 encoder 流，但引入 blocked decoding 与"必须缓存等待中的头块"** | RFC 原文 |
| **头压缩的 CPU 占比** | — | **未找到** | **未找到（零篇量化）** | 见 §5 空白② |

**七条关键发现**

1. **"QUIC 比 TCP 贵几倍"已收敛，且瓶颈不是加解密**：Google 官方拆解显示 UDP 发送占 25%~>50% CPU、`sendmsg` cycle/byte 最高为 TCP 的 3.5×；Huitema 的 flame graph 显示 **70–80% 时间在 socket 层**（2019 年业界自己判断失误，以为瓶颈是加密）。
2. **这个倍数有一半来自"没优化"，不是协议固有**（见 §1.3 的 Fastly 阶梯）。含义：**任何"QUIC 慢 N 倍"的数字，不写清实现版本与 offload 开关就没有意义**——这是审稿人最可能攻击的点。
3. **不要假定"必须内核旁路/上硬件才快"**：NOMS'26 把 4 个实现改为 DPDK 后最好 3×，但**其中一个毫无改善**，作者明确写"如果系统提供 offload 且实现正确使用，也能达到类似性能"。**→ FPGA 方案必须先给同机 DPDK/AF_XDP 基线**，否则无法把加速归因到硬件卸载。
4. **搬进内核也没自动解决**：Linux 在研内核 QUIC 比内核 kTLS 慢约 3×、比裸 TCP 慢 >4×（关 1-RTT 加密时），原因依旧是**缺 GSO、TX 多一次拷贝、头部额外加密**。**成本大头是"每包被触摸的次数"，不是"内核 vs 用户态"这个二分法。**
5. **加密成本占比可给出一个可用数字：TLS 记录层约占栈内 1/3**（708 → 466 Mbps）。其卸载收益已被量化（QAT：F5 白皮书 128B 包 34,173 vs 3,660 TPS ≈ 9.3×；netdev 0x14：NIC 硬件 kTLS 单流 2.5×、8 流 50→100 Gbps、省 50–60% CPU）。**但 QUIC 的加密不是 TLS 记录层**，而是每包强制的包保护（header protection，至少两遍对称操作），**无法照搬 kTLS 的卸载形态**。
6. **端到端三代横评的结论互相打架，差异主要来自实现与拥塞控制**："H3 只在高延迟/差带宽才赢"、"平均吞吐更高但多数 QoE 指标更差"、"快网下最多慢 45.2%"、"自家 CDN 上平均还落后 1–4%"。**同一句"HTTP/3 比 HTTP/2 快/慢 X%"几乎不可证伪。**
7. **头压缩是三代里唯一的"必然状态量"**：无论怎么实现，都必须为"每连接动态表 + 等待中的 header block 缓冲"预留存储。现实实现里这个状态的代价已被量化到位——Envoy 的 QPACK blocked decoding 漏洞（GHSA-p7c7-7c47-pwch）：**阻塞期间头块字节仍驻留堆内，但 QUIC 流控已把额度归还对端**，且"阻塞流数量上限只约束并发数、不约束每个被阻塞块的驻留大小" → 攻击者可无界撑大内存导致 OOM。**"串行依赖"在实现上等于"必须缓存住等待的表状态"。**

---

## 3. 分层卸载现状：哪一层已经有人在做了

| 栈层 | 已有谁做了 | 做到什么程度 | 剩余空白 |
|---|---|---|---|
| L4 TCP | AccelTCP（NSDI'20，**状态机**卸载）、FlexTOE（NSDI'22，`DBK-15`）、PnO-TCP（2025）、ContaTOE（2026）、F4T（ISCA'23，100 Gbps/2 核） | 可卸载状态机、可线速 | **红海**，且不是三代协议差异所在 |
| TLS 记录层 | kTLS `TLS_HW` + ConnectX-6Dx/BF inline crypto；QAT（F5 白皮书 9.3×）；Autonomous NIC offloads（ASPLOS'21）；XTLS（APSys'26） | **已生产化**，但**只作用于 TCP** —— kTLS 是 TCP ULP，**覆盖不到 QUIC 的 TLS-over-UDP** | ① QUIC 记录层加密卸载（无成熟通道）；② kTLS 对隧道/虚拟接口不卸载（5-tuple 限制） |
| TLS 握手 | 只有 QAT **加速非对称运算**（QTLS, PPoPP'19），状态机仍在 CPU；交换机侧只做 **SNI 明文提取**（ICC/NOMS'25） | **未落地**（三方独立反证，见 §1.1） | **真空白**：握手全硬件化（能扛 rekey/KeyUpdate/异常路径） |
| HTTP/1.1 解析 | **Strega（TRETS，开源）**：整个网络栈 + HTTP 服务端栈进 FPGA；Blott HotCloud'13 的 request parser；一批嵌入式 FPGA web server（2012–2018） | 能跑、延迟低一个数量级 | 本体接近"已做"；**但从没有人把它和 /2、/3 放在同一硬件平台上比过** |
| HTTP 语义进可编程交换机 | Miresga（WWW'25：3.9× 吞吐、0.4× 时延，但**HTTP 内容解析仍在 front-end server**）；L7LB（INFOCOM-W'23）；P4DDPI（DNS 变长解析的可为与不可为） | 只做 L4/L7 的"转发与建连"，**HTTP 语义仍在 CPU** | **HTTP 语义真正进数据平面** |
| **HPACK** | **零**（arXiv `abs:"HPACK"` = 0；S2 `"HPACK decoder implementation"` 返回全是 LDPC/Polar 解码器） | **零硬件实现** | **真空白**（也可能是"本来就不该做"的空白） |
| **QPACK / HTTP/3 帧层** | **零**（arXiv `abs:"QPACK"` = 0；`all:"HTTP/3" AND all:"FPGA"` = 0）；仅 Design Gateway 的**客户端** QUIC IP 核（1 GbE 商品 IP） | **零硬件实现** | **真空白**，障碍是结构性的 |
| 请求路由 / L7 LB | 软件：Ananta（SIGCOMM'13）、Hermes（SIGCOMM'25）、XLB（eBPF, 2026）；交换机：Miresga、L7LB；硬件 L4：Tiara（NSDI'22） | "路由决策下沉"已在做，但 **HTTP 感知部分基本还在 CPU** | **HTTP 语义匹配真正进硬件数据平面** |
| 缓存 | 交换机侧只有 KV 缓存（NetCache `NIAC2026-4`、OrbitCache `NPD-2`），**不是 HTTP 对象缓存** | **放不下**：8 MB、16B key；54 个真实 workload 中 42 个连一条都放不下 | HTTP 对象缓存进硬件 = 真空白（且从容量看是幻想层） |
| DPU 的 L7 能力 | **DOCA 服务清单里没有任何 HTTP/L7 服务**（FLOW/Gateway/Firewall/DPI/App Shield/Rivermax/RegEx/Storage/DPA/Inline Crypto） | 上限 = L4 + TLS 记录层 inline crypto + **RegEx（BF-3 近 75 Gb/s，但单 job ≤16 KB）** + **DPA（BF-3 才有的 RISC-V 通用子系统，要自己写）**；**BF-2 没有 DPA** | DPU 上做 L7 协议栈 = 空白 |
| 可编程交换机做 L7 | SilkRoad（SIGCOMM'17，**L4**）、RedPlane（SIGCOMM'21，有状态）、Miresga（WWW'25 → IEEE TC'26）、**Scallop（SIGCOMM'25，`CGC-18`）**、INFOCOM'26 服务网格 L7 控制 | 已有连续工作线 | 共同结构是"交换机做转发/建连/丢弃，HTTP 语义留 CPU" |

> **四组零命中查询（arXiv 元数据级 + S2 题录级双通道）**：`all:"HTTP/2" AND all:"FPGA"`、`all:"HTTP/3" AND all:"FPGA"`、`all:"HTTP" AND all:"SmartNIC"`、`all:"QUIC" AND all:"FPGA"`、`abs:"HPACK"`、`all:"header compression" AND all:"hardware"`、S2 `"HTTP/2 header compression hardware implementation"`、S2 `"hardware TLS offload evaluation overhead not worth"` = `{"total": 0}`。
> **结论**：**没有检索到任何"把三代 HTTP 栈在硬件卸载下做统一横向对比"的已发表工作**。空白可信度：**中高**（受"arXiv `all:` 不覆盖全文 + ACM/IEEE 正文 403 + 未做滚雪球"三重限制）。

---

## 4. 三类卸载载体：能力谱系与代价

### 4.1 FPGA（XCVU13P）—— 唯一能写自定义解析器的一档

- **能做**：RTL 数据面、自定义解析器、正则/多模式匹配、TLS 记录层 AEAD、L4 状态机。
- **不能做**：QPACK/HTTP-3 帧层（QUIC 头加密）；HPACK 很难（串行）；HTTP 对象缓存（DDR4 弱）。
- **硬约束**：PCIe Gen3 x16 有效上限 ≈100 Gbps 量级（**x16 为外推值**，且要扣协议开销与描述符往返）；**必须让 FPGA 直连网络**；每连接状态压在片上 **57 MB** 里。
- **现成基线**：Corundum（FCCM'20，开源 100 Gbps FPGA NIC）、Sidler FCCM'15（10 Gbps TCP/IP 栈）、ClickNP（SIGCOMM'16，FPGA 上写 NF 的框架）、Beehive（MICRO'24，直连加速器的可编程网络栈）。

### 4.2 DPU / SmartNIC（BlueField）—— "把通用核搬到网卡上"这一档

- **能做**：**Arm 核上跑任意状态机**（这是 RTL 给不了的）、DOCA Flow 的 L2–L4 匹配动作、**inline TLS crypto**、**RegEx 引擎**（BF-3 近 75 Gb/s，单 job ≤16 KB）、压缩、IPsec、哈希。
- **不能做**：BF-2 **没有 DPA**；DOCA **不提供任何 HTTP/L7 服务**；DPA 是通用 RISC-V 子系统（BF-3 16 个超线程核），要自己写。
- **代价底表**：`DBK-46`（BF-2 多通信路径刻画）、`DBK-47`（BF-3 DPA 刻画，含**反直觉结论：DPA 比板载 ARM 与 host CPU 都更"弱"**，但专用化后仍能获益）、`DBK-48`（新 BF 实测，含 PCIe/内存瓶颈）。
- **身份**：这一档的关键价值不是"更快"，而是**隔离性 + 确定性 + 不占主机核**（IEEE TCC / JPDC 口味）。

### 4.3 SoC 内置加速器（RK3588）—— "纯专用加速器"这一档，且是**负面样本**

**能力边界只有两样**（其余加速器与协议栈无关）：

1. **GMAC**：DWC_ether_qos 4.20a，**SoC 自带 2×1GbE**（数据手册明写 10/100/1000M；板载 2.5G 一律是外挂 RTL8125 走 PCIe Gen2 x1）。厂商 BSP **单队列、无 RSS**；**GMAC DMA 只能寻址 4 GB 以下物理内存**（官方文档原文）；PCIe 侧需手工维护 DMA 一致性。
2. **Crypto/PKA 引擎**（crypto V2，2 个 cipher 引擎 + 独立 PKA 时钟域）：算法覆盖全套（AES/SM4/DES/3DES + GCM/CCM/XTS、SHA/HMAC、RSA≤4096/ECC/SM2）。

**五条源码级/官方级证据，直接回答"专用加速器值不值得"**：

| 证据 | 内容 | 出处 |
|---|---|---|
| ① 引擎比 CPU 指令慢 **5.7×** | 引擎 AES-256-GCM **310 MB/s**（官方 librkcrypto 自测）vs 一个 A76 核 **1,763.9 MB/s**（AES-128-GCM 2,185.7） | Rockchip `perf_reports/RK3588_perf.txt`；TinyComputers 实测 |
| ② **内核优先级 0** | Rockchip 把自家算法注册优先级设为 **0**；ARMv8 `gcm-aes-ce` 是 **300**；`net/tls/tls_sw.c` 用 `crypto_alloc_aead` 按优先级选实现 | `rk_crypto_core.h` L39；`ghash-ce-glue.c`；主线 `tls_sw.c` |
| ③ **kTLS 永远不用它** | ⇒ 在 RK3588 上 kTLS 会挑 `gcm-aes-ce`，**硬件引擎永远轮不到**（源码级否定答案） | 同上 |
| ④ **无 kTLS 硬件 record offload** | `stmmac` 驱动全文件 0 次实质 `tls` 命中 → 没有 `ndo_tls_dev_add` 一类接口 ⇒ `TLS_HW`/`TLS_HW_RECORD` 不可用 | 主线 `stmmac_main.c` |
| ⑤ **真实流量下大量退回 CPU** | debugfs：`ecb-aes-rk2 reqs=131 / fallback=2005`（alignment 1649、length 352）；`cbc-aes-rk2 reqs=154 / fallback=2164`（**注：该统计出自 RK3568，节点名是驱动名；标待核实**） | 论坛（`论坛待核实`） |

**机理**：DMA 型引擎对**块对齐/长度/SG**敏感，且数据要经 DMA 往返 → 延迟更高；而 ARMv8 CE **就是 CPU 指令集的一部分**，没有这些开销。同一机理在 NXP SEC/CAAM 上也被指出过。

**RK3588 给得了 FPGA/DPU 给不了的三样**：
- **真实产品级边缘节点形态**：整板空闲 **4–5 W**、满载 **10–12 W**，完整 Debian + 8 核 A76/A55 + 2.5GbE；
- **同硅片上的三方受控对照**：纯软件（`OPENSSL_armcap=0`，OpenSSL 官方支持的开关）vs ARMv8 指令（默认）vs 硬件引擎（cryptodev/librkcrypto）——**不换平台、不换板卡、不换 PCIe**；
- **"协议栈加速器与业务加速器抢同一份 DRAM/功耗预算"** 的边缘特有问题（NPU/VPU/crypto/8 核共享 LPDDR4X，既有实测 17–22 GB/s）。

**并且它是没人做过的那一格**：没有任何学术工作把 RK3588 当网络/边缘服务器本体刻画（学术界的 RK3588 = CV/AI 推理）；RK3588 的 DPDK/AF_XDP 公开实测为零（只有 Rockchip 对 **RK3568** 的 580 Mbit/s@64B 单核）。

---

## 5. 空白清单（按可信度分级）

**高可信（多通道检索一致 + 有结构性解释）**

1. **"硬件卸载下的三代 HTTP 协议统一横评"不存在**——arXiv 元数据级 + S2 题录级双通道零命中（8 组查询，见 §3）。
2. **HPACK / QPACK 编解码的 CPU 占比：零篇量化**（6 组 S2 + 2 组 arXiv 全空）。
3. **"卸载边界/代价模型"**——Clara（HotNets'20，30 引）明确点出"开发者事前无从判断该不该卸"，**至今没有成熟答案**。这是最该占的位置。
4. **HPACK / QPACK / HTTP-3 帧层的硬件实现 = 零**。找到的全部是：HTTP/1.1 上 FPGA（Strega）、TCP 全栈上 FPGA（F4T）、QUIC **握手加解密**上 FPGA（CFcoQUIC，RSA ≥19.1×/AES ≥5×）、QUIC 握手上 DPU（TurboRetry）。
5. **ARM SoC × 三代 HTTP × 硬件 crypto 卸载：零命中**。最接近的是 **Caiazza et al.（PMC 2024）**——手机 + 一块 SBC 测三代 HTTP 的**能耗**：M2M 场景下 HTTP/3 在 2 MB 载荷时比 H1.1 **多耗能 30–36%**、4 MB 时 **45–53%**，且 **H1.1 ≈ H2（无显著差异）**，根因指向"HTTP/3 在用户态花的时间更多"。**但它不含吞吐/CPU 分解、不含服务器侧、不含任何硬件卸载。**
6. **没人测过 RK3588 crypto 引擎在 TLS/QUIC 负载下的表现**——2026 年的专业评测作者本人明写 "the dedicated accelerator's throughput remains unmeasured"；已有引擎数字全是裸算法 benchmark（1 MB 连续、DMA），**没有记录层口径（小 record / 逐块 AEAD / 混合握手）的数字**。

**中可信（受检索限制）**

7. **没有公开可比的"核/Gbps"成本模型**——现有数字都是"某实现 + 某机器 + 单流 + 某开关状态"。
8. **缺"同一台机器上 H1.1/H2/H3 三栈并排 + 把 offload 当因子"的受控测量**。
9. **三代协议的能耗-吞吐对照曲线缺失**（只有零散的移动端/视频流能耗工作）。
10. **接收侧 vs 发送侧不对称**：WWW'24 指出业界工作几乎只优化发送侧且方法论不可复现（有的客户端与服务端跑在同一台笔记本上）；接收侧 CPU 归属仍是被点名的开放问题。
11. **"硬件 crypto 引擎接进数据面"有 x86/QAT 版本**（XDP + QAT 内联 crypto，ISPA 2023），**ARM SoC 版本为空**。
12. **FPGA 资源比较的公平性**：未检索到专门批评"FPGA 资源比较不公平"的方法论文献（S2 + Crossref 多组关键词命中 0/噪声）→ **必须自立口径并显式解释，不能靠引文豁免**。

---

## 6. 撞车清单（最危险的邻居）

| 排名 | 论文 | 撞什么 | 必须说清的话 |
|---|---|---|---|
| 1 | **Strega: An HTTP Server for FPGAs**（TRETS, DOI:10.1145/3611312，开源） | "首次把 HTTP 服务搬上 FPGA"会被直接否决（1.7 M req/s、16 µs、胜过 32 vCPU nginx） | 对象必须限定为 **H2/H3**，并说清相对 HTTP/1.1 简单解析**新增的协议状态复杂度代价** |
| 2 | **Miresga**（WWW'25 + IEEE TC'26） | 若讲成"交换机/硬件做 L7 LB" | 它的架构诚实说明"HTTP 解析留在 CPU"，正说明缺口还在 |
| 3 | **Making QUIC Quicker With NIC Offload**（EPIQ@SIGCOMM'20）+ **Intel Netdev'19** | 若讲成"给 QUIC 设计硬件卸载原语" | 这两篇已论证"该卸载什么、接口长什么样"；Intel 那条还明确了**硬件不做 QUIC 头封装解封装**（因为头是加密的） |
| 4 | **F4T**（ISCA'23）/ **Beehive**（MICRO'24）/ **FpgaNIC**（ATC'22）/ **Corundum**（FCCM'20） | "在 FPGA 上卸载传输层/网络栈"已到 100 Gbps / 2 核 / 省 64% CPU 周期 | 不要把 TX/RX 通路或 TCP 卸载算作贡献 |
| 5 | **XTLS**（APSys'26）+ **Autonomous NIC offloads**（ASPLOS'21）+ **SSLShader**（NSDI'11） | TLS 卸载的栈协同设计 / 硬件 vs commodity CPU | SSLShader 是"多核 commodity CPU 就够便宜"的经典反方 |
| 6 | **picoquic-dpdk**（CoNEXT SW'22）+ **Kernel Bypass Surgery**（NOMS'26） | 不能假定"FPGA/SmartNIC 一定比 DPDK 快" | **必须先给同机 DPDK 基线** |
| 7 | **Caiazza et al.**（PMC 2024） | 嵌入式侧三代 HTTP 的唯一前作 | 它测的是**能耗、客户端侧、无卸载**；增量在吞吐/CPU/服务器侧/加密路径对照 |
| 8 | **Scallop**（SIGCOMM'25） | "某 L7 应用拆成硬件数据面 + 软件控制面"的方法论撞车 | Scallop 是视频会议 SFU；需把负载换成 HTTP |
| 9 | **CFcoQUIC**（ICCCN'25） | QUIC 握手加解密上 FPGA 已有人做 | 重复做握手加速增量极低 |
| 10 | **Clara**（HotNets'20） | 若也做"判据/代价模型"会撞 | 它是 workshop 短文、无完整系统验证——**正面引用它作为"我们填的坑"** |

---

## 7. 重构方案：从"三代横评"到"可卸载性谱系 + 卸载边界"

### 7.0 核心命题（可证伪）

> **卸载悖论**：HTTP 协议越现代，**软件 CPU 成本越高**，但**可硬件卸载的比例越低**——因为代际演进的方向是"用更多协议状态换更少网络状态"（H1.1 无状态串行 → H2 每连接头压缩状态 + 单连接多流 → H3 每连接加密状态 + 流级隔离），而**协议状态正是硬件最不擅长承载的东西**。

三代的机制各不相同，这条曲线因此不是"数字对比"而是**分类学**：

| 代际 | 软件成本 | 可卸载性 | **原因（机制）** |
|---|---|---|---|
| HTTP/1.1 | 低（≈裸 TCP + TLS） | **高** | 无状态、明文、可枚举字符串解析 |
| HTTP/2 | 中（≡H1.1 栈 + HPACK） | **中** | **HPACK 每连接动态表 + header block 强制连续 → 串行状态机** |
| HTTP/3 | **高（1.4–3.5×）** | **低** | **QUIC 头加密 → 帧层对硬件不可见；每包两遍包保护；用户态 ACK** |

**这条命题的价值**：它不依赖跨实现的可比性（绕开 §1.3 最致命的坑），且每一格的证据都可以从 RFC 与已有测量里拿到。

### 7.1 方案 A（推荐，硬件向）：可卸载性谱系的最小原型 + 判据

**规模裁剪**：不做"三代全栈进硬件"，只做**能形成单调曲线的最小切片**：

| 切片 | 做法 | 角色 |
|---|---|---|
| HTTP/1.1 请求解析 | 复用/复刻 Strega 式无状态解析（或直接引其数字） | **上界**（已证可硬件化） |
| **HTTP/2 HPACK 解码器** | 在 VU13P 上实现（含动态表 + 增量索引 + Huffman），测：每连接状态字节、**连接数上限 N\***（受 57 MB 片上存储约束）、每请求周期数、与软件 HPACK 对照 | **主角**（真空白、明文可见、串行状态机） |
| HTTP/3 QPACK | **不实现**，只做"不可卸载下界"分析（每包包保护 + blocked decoding 的字节缓冲驻留） | **下界**（证明为什么做不了） |

**由此得到三个可证伪的断言**（每个都要能被数据否证）：
1. 存在连接数阈值 **N\***，超过后 **HTTP/2 的卸载收益转负**（HPACK 动态表吃掉片上存储）——给出 `N* = f(表大小, 并发连接数, 片上 57 MB)` 的闭式或经验判据；
2. **QUIC 的"不可卸载部分"存在与实现无关的下界**（每包 header protection 两遍 + 用户态 ACK 归属）；
3. **专用加速器的收益与"数据是否已在 CPU 里"强相关**——RK3588 的 crypto 引擎给出负面样本（慢 5.7×），把它的机理（DMA 往返 + 对齐/长度 fallback + 优先级政策）写成**判据的另一半**。

**基线（缺一不可）**：内核栈 / 内核栈调优版 / DPDK 或 AF_XDP 用户态栈 / 每平台各自的最强软件实现。**没有同机 DPDK 基线，加速不能归因到硬件。**

**目标场馆**：**FPGA / ICCD / DATE**（硬件实现）＋ **TRETS / Computer Networks**（期刊）。

### 7.2 方案 B（最省、最快出数据、可当 A 的前哨）：RK3588 单平台深挖

**两个实验，都便宜且数字缺口明确**：

1. **"硬件引擎 vs ARMv8 指令 vs 纯软件"三方受控对照**（`OPENSSL_armcap=0` / 默认 / cryptodev+librkcrypto），输出 AES-256-GCM / SHA-256 / RSA-2048 的**吞吐 + CPU 占用 + 整板功耗**。先验证据已指向"引擎会输"，**价值落在"为什么"与"什么条件下会赢"（大块连续、密钥不落地、低 CPU 占用场景）**——这是**批判性测量**，叙事要摆正。
   - ⚠️ 前提：必须用 Rockchip vendor BSP 内核（主线无 crypto 节点），接受"vendor BSP 不可复现"这个弱点，并同时报告主线内核下的对照组。
2. **同一台 RK3588 跑 H1.1 / H2 / H3 服务端**，报 **吞吐 / 每请求 CPU 时间 / 每字节能耗 / 整板功率** 四联表，检验 Caiazza 观察到的"HTTP/3 更费能"在 SBC 上是否成立（注意固定实现或多实现交叉验证）。

**目标场馆**：**Computer Networks / IEEE TCC**（B 类）；会议 **ICNP / CoNEXT**。

### 7.3 方案 C（纯测量，无硬件）：把 offload 当因子的三代协议成本分解

在民用 PC 上做**同机 H1.1/H2/H3 三栈并排 + offload 因子设计**（GSO/GRO/sendmmsg/AES-NI/kTLS 逐项开关），目标是**首个可比的成本分解**。先例形态最贴近：`Opening Up Kernel-Bypass TCP Stacks`（USENIX ATC'25，CCF-A）——自陈"这些栈从未在同一组基础负载下比较过，很可能因为它们很难跑起来"，跑通即贡献。

**风险**：软件侧横评红海；天花板受限于"测量类"期刊出口（`Computer Communications`/`TNSM` 都是 C 类）。**只建议作为 A/B 的配套测量章节，不建议单独作为主线。**

### 7.4 关于"通用场景 vs 特定场景"的建议

原命题里的"特定/通用场景"应**收敛到一个具体场景**，二选一：
- **CDN 边缘（大并发小对象）**：这是 HPACK 动态表状态量最吃紧、也是 Strega/Miresga 的共同场景；
- **边缘节点（云游戏/云桌面/边缘 LLM 的服务端）**：正好复用本工作区既有积累（`CGA`/`CGB` 云游戏与云桌面、`CGT`/`KVT` KV 传输），且 RK3588 的能耗维度在这里才有意义。

---

## 8. 方法学规范（可直接抄进论文）

**资源报告：绝对量 + 归一化量，两套都要给**

- **绝对量**（必须给全）：器件型号 + 速度等级、工具版本、LUT / FF / BRAM / **URAM** / DSP、**布局布线后实测 Fmax**（不是综合目标频率）、DDR4 实测带宽。
- **归一化量**：`LUT/Gbps`、`BRAM/Gbps`、`DSP/Gbps`、`Gbps/W`、**每连接字节资源**。
- **呈现方式**：报 **(资源, Fmax, 吞吐) 三元组 + 资源-吞吐帕累托前沿**，不要单点柱状图。
- 可引做法：Sidler FCCM'15（早期范式）、F4T ISCA'23、**Corundum FCCM'20**（开源可复现）、Honeycomb TC'23。
- **Threats to Validity 三条自陈**：只报加速比不报资源 / 只报资源不报频率 / 单一器件外推。

**能耗口径：四问必须逐条回答**

1. **分子**：per-packet / per-byte（NetFPGA 系列有先例）/ per-useful-bit（Ammer SECON'06）/ **per-request（本方向需新造）**；
2. **边界**：仅器件？含 DDR4+收发器+风扇的整卡？含主机 CPU？（Huang ISPASS'23 / IISWC'23 用 SLO+TCO 把主机侧拉进来）；
3. **测法**：Vivado 后实现报告的**估算值**（注明 vector-based / SAIF）与**板级实测**必须分开标注（两者差 10–30% 是常态）；
4. **基线**：是否扣 idle 功耗、测量时长、采样率。
- 可引做法：Sivaraman INFOCOM-W'11（per-packet + per-byte）、**Pham Ngoc, Computer Networks'15（CCF-B）**、**Fiandrino, IEEE TCC'17（CCF-B，85 引）**——**"指标口径本身"就是 B 类贡献**。

**卸载研究"为什么上硬件"的七要素论证结构**（现有范本高度一致）：

1. 成本现状（datacenter tax 版图）→ 2. **最强软件基线的实测数字** → 3. "前人只卸了半层"的判决句 → 4. **本层特有的结构障碍** → 5. 资源/通路约束的定量化 → 6. **可判定的卸载边界 / 代价模型** → 7. 可反驳断言。
> ③ 的现成弹药（可直接引）：Strega 原话"TCP/IP 这类协议的硬件卸载已很清楚，但**更高网络层的加速器支持仍然大量缺失**"；EPIQ'20"**QUIC 卸载此前只考虑了 crypto 一个模块**"。
> ⑥ 的坑位由 Clara（HotNets'20）明确点出且**至今无成熟答案**。

**CCF-B 上"测量/对比类"能成立的 5 种贡献形态**（原命题若只做横评，一种都不占）：

| 形态 | 贡献句模板 | 先例 |
|---|---|---|
| ① 首个统一口径横评 | "首次把 A/B/C 放在同一负载、同一基线与同一度量口径下对比，此前因 X 从未可比" | Opening Up Kernel-Bypass TCP Stacks（ATC'25）｜Comparing DNS Resolvers（IMC'10） |
| ② 方法学纠正 | "此前关于 A vs B 的结论因 P/Q/R 不可比而站不住；我们提出新方法并给出不同结论" | Taking a Long Look at QUIC（IMC'17）｜其 IMC'24 复现 |
| ③ 系统刻画 + 反直觉结论 + 设计指南 | "首个系统刻画，得到与直觉相反的三条结论，并给出设计指南" | Demystifying DPA（ICNP'24）｜BF DPU 刻画（ICS'25） |
| ④ 指标/口径定义与统一 | "梳理并统一了 X 领域的性能与能效指标口径，指出既有指标适用边界" | Fiandrino（TCC'17）｜Pham Ngoc（Comput. Networks'15） |
| ⑤ 复现/复核 | "用 N 年后的软硬件重做 X 的实验，发现原结论在条件 A 成立、条件 B 失效" | IMC 有正式 replication 赛道（IMC'24） |

**推荐的复合定位**：本节命题同时落在 **① + ③ + ④** 的交叉处——"首个可比的卸载边界横评 + 反直觉结论（卸载悖论）+ 统一资源/能耗口径"。这是 CCF-B 认得出的形态。

---

## 9. 场馆（按官方《第七版 CCF 推荐目录》逐条核对）

| 场馆 | 第七版实际 | 用途 |
|---|---|---|
| **IMC** | **B** ✅ | 测量/横评最对口 |
| **ICNP / CoNEXT** | **B** ✅ | 系统与网络 |
| **FPGA / ICCD / DATE** | **B** ✅ | 硬件实现 |
| **TRETS / Computer Networks / IEEE TCC / JPDC** | **B** ✅ | 期刊（TRETS 与 Strega 同刊；COMNET 有 DPDK/HTTP-3 版面） |
| **ICS** | **B** ✅ | 体系结构刻画 |
| ~~TACO~~ | **A 类**（与 TOCS/TOS/TCAD/TPDS 同块） | ❌ 不能当 B 类保底 |
| ~~PAM~~ | **C 类** | ❌ |
| ~~TMA / ACM CCR~~ | **未收录** | ❌ |
| ~~IISWC~~ | 未检出，级别待核实 | ⚠️ |

**投稿策略**：**硬件实现侧投 FPGA / ICCD / DATE，测量与代价模型侧投 IMC / ICNP，期刊侧投 TRETS 或 Computer Networks**——两端并行，比"押一个横评投 Computer Networks"成功率高得多。

---

## 10. 待核实与检索局限（宁缺勿假）

1. **全部四路均未做引用滚雪球**（正向 citations / 反向 references）。建议以 **Swett EPIQ'20、WWW'24、内核 QUIC 补丁**（三代成本）；**Strega、Miresga**（硬件邻居）；**Clara**（代价模型）为中心补做。
2. **多篇只到题录/摘要级**（ACM DL 与 ScienceDirect 403）：Strega、Miresga、XTLS、Scallop、QDSR 等；数字引用前须回正文。**唯一逐句核对过原文的是 PCIe 那篇**（SIGCOMM'18）。
3. **SIGCOMM'17 QUIC 论文里"服务端 QUIC CPU 约为 TCP+TLS 的 2 倍"这句话没能读到原文**，只见二手引用 → **标待核实，勿当权威数字引**。
4. **内核 QUIC 补丁自带性能表**只拿到检索快照（netdev/openwall 正文抓取失败）→ 数字已标 `待核实`；正式引用请用 LWN 报道或重跑。
5. **RK3588 侧待补的板上实测**：① `OPENSSL_armcap=0` 的纯软件 AES-GCM 基线（本次只拿到同族平台 18–22× 的比值）；② RK3588（非 RK3568/3588S）的 DPDK/AF_XDP pps 与 Gbps（公开渠道零命中）；③ 厂商 BSP 单队列 vs 主线 DTS 2 队列，硬件是否真支持 RSS（需板上 `/sys/class/net/*/queues` + ethtool 验证）；④ 论坛那份 debugfs fallback 统计出自 **RK3568**（节点名 `rk3588_crypto` 是驱动名），**不可当 RK3588 数据**。
6. **librkcrypto 的 `virt` 路径数字自相矛盾**（AES-256-GCM virt 1223 > dma_fd 310 MB/s）→ **报告时不要引用 virt 数字**。
7. **VU13P 规格（12,288 DSP、≈455 Mb 片上、PCIe Gen3 x16）本轮只读到二手页**，未逐项抓 AMD 官方 DS922/产品表；与用户前提一致，正式引用前须核官方文档。
8. **用户线索的核实结果**：**"Cheetah 类 FPGA HTTP 服务器"❌ 不存在**（同名 Cheetah 分别是 DPDK 软件 LB 框架、FPGA CNN 加速器、交换机数据库剪枝、蛋白质服务器，均与 HTTP/FPGA 服务端无关——**判为名称记忆偏差**）；**Catapult ✅ 真但著录需修正**（会议版是 **MICRO 2016**，DOI `10.1109/MICRO.2016.7783710`；2014 年的是前身 ISCA'14）；**SilkRoad ✅ 真但是 L4 非 L7**；**Ananta ✅ 真但是纯软件**；**NICA 是 USENIX ATC'19 不是 ISCA'19**；**sPIN 是 SC'17 不是 ASPLOS'19**。
9. **空白可信度的边界**：所有"零命中"结论都受"arXiv `all:` 只覆盖元数据、ACM/IEEE 正文 403、未做全文检索、DBLP 被反爬"四重限制。**立题前建议补一轮 IEEE Xplore 全文检索**（`HPACK` / `QPACK` / `"HTTP/2" AND "accelerator"`）与**按作者追被引**（Strega 的 fpgasystems 组、Miresga 的 Xiaoyi Shi 组）。
