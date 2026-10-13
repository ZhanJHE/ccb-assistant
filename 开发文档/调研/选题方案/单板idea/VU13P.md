# VU13P 单板非 KV 方向研究 idea 集

> 创建：2026-10-02。**约束**：XCVU13P（≈378 万 SLC、**12,288 DSP48**、**片上 ≈455 Mb ≈ 57 MB BRAM+URAM**、板载 DDR4 弱带宽、PCIe Gen3 x16）；8 个月（2026-09→2027-05）、单人、Verilog 基础（手写 RISC-V CPU）、无 HLS 量产经验、无 GPU 服务器；目标 CCF-B（FPGA/ICCD/DATE 会议；TCC/JPDC/Computer Networks 期刊；FCCM/FPL/FPT 保底）。
> **排除**：KV-cache / LLM serving（已有选题 2+ OnChip-KV 与 FlightLLM 类，见 `文献索引.md` #1–#38 与 `选题方案/增补-VU13P与纯软件评估路线.md`）。
> **依据**：所有动机出处均引 `文献索引.md` 编号；检索验证仅做 2 次轻量搜索（2026-10-02，Tavily）。
> **统一平台论据**（各 idea 复用）：VU13P 的画像是"**算力/片上内存极强、外部带宽弱**"。57 MB 片上 ≈ Tofino 全程 SRAM 的 3–5 倍、BlueField-3 L1/L2/L3（1/8/16 MB）的 2 倍以上（DBK-46/47、NPD 节补充数字）；而 DDR4 弱 → **凡是"状态/字典/指纹库必须常驻高速存储"的负载，片上 57 MB 就是差异化武器**；PCIe Gen3 x16（≈13 GB/s 有效，DBK-49 论证端系统真瓶颈在 PCIe）+ 主机 DPDK 喂数（DBK 专题）就是现成的实验床。

---

## Idea 1（首推）：OnChip-TRE —— 57 MB 片上指纹库的线速流量冗余消除引擎

- **暂定标题**：*OnChip-TRE: Line-Rate Traffic Redundancy Elimination with a 57 MB On-Chip Fingerprint Store*
- **动机与空白**：
  - 协议无关冗余消除（RE）是经典命题：Spring & Wetherall（SIGCOMM'00，**WTP-112**）实测"内存 <1 MB 只能省 ~10%，100 MB 级才能到 ~50%"——**省字节率是存储容量的函数**；EndRE（NSDI'10，**WTP-115**）企业链路平均省 26%，但用软件 + DRAM。
  - 可编程数据面上唯一实现是 TRE-PRO（IEEE Network'21，**WTP-124**），**引用 0、无人跟进**——交换机 SRAM 只有 MB 级，指纹库被容量掐死，正是 WTP-112 那条曲线的最左端。这是工作区明确标注的"能力涨、人没做"缺口。
  - 2026-10-02 轻量检索确认：未见任何 FPGA 版 RE/线速去重实现（命中的只有原始软件实现与商用抓包卡）。
  - 反方证据必须正面回应：WTP-122（真实无线流量冗余被高估）、WTP-123（接入瓶颈下缓存救不了）→ 场景要选在**企业出口/DCN/WAN 汇聚**而非无线接入，用 WTP-116（接入链路 15–60% 的行业区间）定目标。
- **为什么 VU13P（而不是别的平台）**：
  - **57 MB 片上**：WTP-112 的"冗余率–内存"曲线在 10–100 MB 区间最陡——57 MB 恰好落在收益陡增段，且指纹库全片上、**每包 1 次片上哈希查找、零外部访存**。Tofino（NetCache 只有 8 MB 表，NPD 节）与 BF-3（L3 16 MB，#29 注记）都放不下这个量级的指纹库；GPU 做则违背"线速 + 确定性延迟"；CPU 软件方案就是 EndRE，吞吐封顶 1.5–4 Gbps。
  - Rabin 指纹/winnowing 是移位+异或流水线（FPGA 线速字符串/模式匹配有 20 年积累，**NPD-15**），不吃 DSP，逻辑资源充裕。
  - **DDR4 弱不是缺陷而是叙事**：去重引擎的价值恰在于"不碰外部存储"；碰了就把瓶颈从链路搬到内存。
- **实验设计**：
  - RTL：CDC（content-defined chunking，winnowing 变体 WTP-114）→ Rabin/SHA-1 截断指纹 → cuckoo/组相联指纹库（片上 URAM）→ 编码（重复段换 20 B 引用）/解码对称引擎。单引擎深而窄，符合 8 个月约束。
  - 主机侧：DPDK 抓包 → PCIe Gen3 x16 送入卡 → 处理 → 回注；对照组 = 主机纯软件 EndRE 复刻 + 内核栈。
  - 数据：CAIDA/MAWI 公开 trace + 校园网真实出口 trace（需导师资源）+ WTP-114 的公开 traces；指标 = 字节节省率 vs 指纹库容量曲线、吞吐（目标 25–100 Gbps）、p99 处理延迟、与 WTP-112/115 报告值交叉验证。
- **目标场馆**：FPGA / ICCD / DATE（系统+架构贡献）；扩展"负载时序耦合"（WTP 专题结论：RE 文献不看负载时序）后可冲 Computer Networks / JPDC。
- **风险与撞车**：
  - 工程量中：流水线本身不难，难点在**乱序/丢包下的流重组**与编码协议设计——scope 控制：第一版只做"单向链路 + 无损"假设，协议对齐 WTP-112 经典设计。
  - 商用 WAN 优化器（Riverbed 等）存在但非学术、非可编程平台，引言需交代。
  - **新颖性把握：高**。依据：TRE-PRO 引用 0 + FPGA 实现零命中 + 容量曲线论据。
  - 待核实：FPGA dedup 可能藏在存储压缩文献里（非网络语境），立题前补一轮检索。

## Idea 2：GlyphChip —— 云桌面"像素域字形字典"硬件编码器（ClearCodec 空位）

- **暂定标题**：*GlyphChip: A Pixel-Domain Glyph-Dictionary Encoder on FPGA for Ultra-Low-Latency Cloud Desktop Streaming*
- **动机与空白**：
  - 云电脑/远程桌面的技术核心是屏幕内容编码 SCC（CGB-6~13），而**远程会话约 80% 图形数据是文字**（微软官方，CGG-3）；规范级答案是 ClearCodec——文字专用无损编码 + V-Bar 像素柱 + 4000 条字形字典，**被 MS-RDPEGFX 定为强制，却无任何开源 RDP 服务端实现**（CGG-4、CGG-16；2026-10-02 检索再确认："The Mandatory Codec Nobody Implements"）。
  - 工作区三组检索（文字层分离 × 远程桌面、压缩视频内文字替换重渲染、文字覆盖旁路）**均 0 命中**（CGG 节）——把它接到现代编码 + 云桌面场景是真空白。
  - 学术侧证据链：JBIG2"每字形只编码一次"（CGG-10，2000 年即进标准）、MRC 分层（CGG-9）、文字区加权 MSE（CGB-12，ACM MM'24）——**思想成熟，硬件与流式系统形态无人做**。
  - 商用 GPU 编码器（NVENC/QuickSync）只有 H.264/265 通用通路，无文字专用硬件（检索确认）→ "通用视频编码器压文字"的效率缺口真实存在。
- **为什么 VU13P**：
  - **57 MB 片上字形字典**：ClearCodec 字典只有 4000 条（规范受限于 2012 年内存假设）；片上 57 MB 可放**十万级字形条目 + 多会话/多租户各自独立字典**，还能做"跨会话持久字典"（字典命中率 vs 容量的消融实验本身就是论文图表）。
  - 字形提取 = 像素域连通/哈希/模板匹配，规则运算、流水线友好，不吃 DSP；**DDR4 弱反而强化设计**：字典与行缓冲全片上，帧数据从 PCIe 流入、码流流出，中间零外部访存。
  - 低延迟是云桌面硬指标（CGA-1：交互回路 112–403 ms；CGB-1：波动更致命）——行级流水（不整帧缓冲）可做到亚毫秒编码延迟，这是 GPU 整帧编码器给不了的。
- **实验设计**：
  - RTL 窄引擎：滚动行缓冲 → 文字区检测（边缘密度/连通域启发式，非神经网络）→ 字形归一化 + 哈希查字典 → 命中发索引、未命中插入字典并发无损原始块（字典替换策略可对照 CGG-10 的 class-based/tree-based 设计）→ 非文字区交给主机侧 H.264（x264/NVENC 兜底，混合模式与 EGFX 混合编码同构）。
  - 主机集成：xrdp（CGG-16 指出其 gfx.toml 只有 H.264/RFX）或自研抓屏 demo + PCIe DMA；对照组 = xrdp H.264、VNC、软件字形字典（复刻 CGG-4 规范描述）。
  - 评估：屏幕录像数据集（自采真实办公/IDE/浏览器操作，含 CGH-6/CGH-8 的无参考屏幕质量度量 + OCR 文字可读性）；指标 = 码率、端到端编码延迟、文字区 CER/可读性、字典命中率 vs 容量曲线。
  - ⚠️ 安全面必须在文中交代：字形缓存是历史攻击面（CGG-14/15 两个 CVE），字典通道要做边界校验设计。
- **目标场馆**：FPGA / DATE / ICCD；期刊 Computer Networks 或 IEEE TCC（系统向）。
- **风险与撞车**：
  - 工程量中高：像素域引擎本身可控，但"与视频编码器的 RD 分工"（什么区域走字形通道）是研究难点也是贡献点；第一版用固定阈值启发式即可。
  - 撞车：JBIG2/MRC 是老标准（文档扫描场景，非流式）；ClearCodec 无开源实现但有完整规范 → 我们是"首个开源 + 首个硬件化 + 容量消融"，定位要写成"系统与硬件研究"而非"新编解码标准"。
  - **新颖性把握：高**。依据：CGG 节三组零命中 + ClearCodec 空位 + 无文字专用编码硬件。
  - 待核实：工业界（Teradici/PCoIP）是否有文字专用硬件通路，需查专利与产品文档。

## Idea 3：FlowState-57 —— 每流状态全片上的线速流级遥测与特征引擎（吃 NPD-16 的工具链红利）

- **暂定标题**：*FlowState-57: Million-Flow Line-Rate Stateful Telemetry on FPGA — What the Missing P4 `register` Extern Costs You*
- **动机与空白**：
  - **硬约束事实**：Vitis Networking P4（WP555，2024-01）**不支持 `register` extern**（NPD-16）——即在 AMD FPGA 上用 P4 写有状态流表目前不可行；Tofino 又已停产且 open-p4studio BSP 窗口关闭（NPD-17）。→ **"FPGA 上的有状态数据面"出现工具链真空，只能靠 RTL 填**，而社区还没有一个容量标尺回答"FPGA 有状态流处理到底能做到多大"。
  - 对照容量：NetCache/NetChain 在 Tofino 上只有 64K 条 × 8 stage ≈ 8 MB 表（NPD 节补充数字）；BF-3 L3 16 MB（#29 注记）。**57 MB 片上 ≈ 百万级流、每流 48–64 B 状态全驻留**——这是交换机 ASIC 与 DPU 都给不了的容量点。
  - 应用钩子（任选其一做深）：① 交互式视频/云游戏的**流量侧 QoE 推断**——IMC'25 证明仅凭流量即可估体验但需分场景特征（CGA-5），Computer Networks'25 用 ML 做云游戏延迟预测（CGA-6）；把特征提取（IAT 直方图、包长序列、突发结构）放到线速数据面，主机只做轻量推理，IIsy/Planter（NIAC2026-6/7）证明在网 ML 分类可行；② 大规模连接追踪/DDoS 检测（经典但红海，建议只作第二用例）。
  - 注意新邻居：F3（CoNEXT'24，FPGA 协处理器做遥测查询，2026-10-02 检索命中，**待核实细节**）——我们的差异在"流状态容量 + 特征语义"而非通用查询框架。
- **为什么 VU13P**：
  - 57 MB 片上 → 流表（cuckoo hash）+ 每流计数器/直方图全片上，**查表延迟确定性、无 DDR4 排队**；12288 DSP 可并行做特征归约（直方图桶、矩估计）。
  - 对比：Tofino 容量不够（8 MB）；BF-3 内存层级小且 DDR5 仅 2 通道（#29）；GPU/CPU 无线速确定性。
- **实验设计**：
  - RTL：解析 → 流表（插入/老化/驱逐）→ 每流特征更新 → 阈值触发上报（dma 事件到主机）。引擎窄而深。
  - 主机侧：DPDK 分流 + 轻量模型（决策树/小型 MLP，对照 IIsy 的模型规模）做 QoE/异常判定；Mininet + trace 重放造拓扑（导师组认可的方法学，见 `增补-VU13P与纯软件评估路线.md` §1.2）。
  - 评估：容量–准确率曲线（流数 1K→1M）、线速吞吐、p99 特征新鲜度、与 Tofino/BF-3 公开容量数字的表格对照；QoE 用例用 CGA-5/CGA-6 的公开方法复现作标签。
- **目标场馆**：FPGA / ICCD / DATE；若 QoE 用例做透，Computer Networks（CGA-6 同刊）。
- **风险与撞车**：
  - 撞车风险中：FPGA flow monitoring/sketch 文献厚（Elastic Trie、UnivMon 类，**工作区未收录，立题前必须补检索**）；F3/N3IC 是最危险邻居。差异化锚点 = "容量标尺 + P4 register 空白的定量回答 + 交互视频 QoE 应用"。
  - **新颖性把握：中**。引擎形态新（57 MB 容量点），但"FPGA 流遥测"大类拥挤。
  - 待核实：NPD-16 之后 Vitis 新版（UG1308 最新版）是否已补 register extern——若已补，动机要改写为"P4 表达力 vs RTL 容量"的对照研究。

## Idea 4：DictPress —— 57 MB 片上字典的日志/备份流式压缩卸载引擎

- **暂定标题**：*DictPress: On-Chip-Dictionary Streaming Compression Offload for Log and Backup Ingestion*
- **动机与空白**：
  - 经典 LZ 系窗口只有 32 KB–数 MB，而日志/遥测/备份流的重复结构跨文件、跨天存在；RE 文献（WTP-112/116）早已证明大字典的收益，但没人把"**字典常驻片上**"做成压缩卸载形态。
  - 存储侧卸载是活跃方向（SPDK 哲学 DBK-41、XRP 把存储函数下沉 DRE-7），但压缩卸载的学术形态多停在"把 gzip 搬上 FPGA"。
- **为什么 VU13P**：57 MB 片上 = **32 MB 级匹配窗口 + 哈希表全片上**（标准 zstd 窗口的 1000 倍），匹配查找零外部访存；DDR4 弱对压缩引擎是致命的（每字节多次访存），片上字典恰好绕开；DSP 可用于哈希/匹配归约并行。
- **实验设计**：RTL 窄引擎（哈希链 + 最长匹配 + 熵编码第一版可用静态 Huffman）；主机侧 SPDK/DPDK 风格轮询管道，数据集 = 公开日志集（LogHub）+ 备份 trace；对照 = 主机 zstd/gzip 各级别 + FPGA 商用 gzip IP。
- **目标场馆**：FCCM/FPL（保底 C 类）→ 若压缩率-吞吐帕累托显著优于现有 FPGA 压缩器，冲 DATE/ICCD。
- **风险与撞车**：
  - **撞车风险高**：Xilinx Vitis Libraries 已开源 zstd/gzip 内核；FPGA 压缩器文献多（工作区未收录，需补检索）。差异化只剩"超大片上字典 + 跨流持久字典"这一格。
  - **新颖性把握：中低**。列为备选，除非 Idea 1/2 在预研中证伪。

## Idea 5：CLUT-VSR —— 云游戏客户端流式视频超分加速器

- **暂定标题**：*CLUT-VSR: A Convolutional-LUT Streaming Super-Resolution Accelerator for Cloud Gaming Clients*
- **动机与空白**：
  - "服务端降码率 + 端侧神经增强"已在顶会立足（Rosevin，INFOCOM'24，CGF-17；GameStreamSR，ISCA'24 移动平台，CGE-9；云游戏端到端系统 CGF-14 是最危险邻居），且"最优码率阶梯本质设备相关"（CGF-20）——**端侧增强硬件能力已成编码决策变量，但端侧增强本身没有开放的硬件实现**。
  - CLUT（Convolutional LUT，TIP'24，CGF-15）把卷积塌缩成查表，**天然是 FPGA 友好形态**（LUT 就是 FPGA 的原语）；压缩域感知的在线 VSR（CGF-16）给出"用码流运动矢量省算力"的下一步。
  - 生成式超分不适用文字/屏幕内容（会幻觉，CGI 节；CGF-3），CLUT 类是保形路线，安全。
- **为什么 VU13P**：57 MB 片上 → **LUT 权重表 + 多行行缓冲全片上**，帧不进 DDR4；12288 DSP 做索引计算与插值并行；对比 GPU（用户客户端未必有，实验室也无 GPU 服务器——这本身就是动机："一张 PCIe 卡把任意旧 PC 变成 4K 云游戏终端"）；对比小 FPGA：放不下整表与行缓冲。
- **实验设计**：RTL 实现 CLUT 前向（训练在主机 PyTorch 完成，只把表量化导出）；PCIe 接入解码后帧（FFmpeg 软解），输出增强帧；对照 = 软件 CLUT（CPU）、双三次、（可借卡补）GPU；指标 = 1080p→4K 帧率（目标 60 fps）、PSNR/VMAF、板卡功耗。数据用 LDV-WebRTC（CGF-15 附带的真实流媒体 SR 数据集）与 GameScope（CGE-8）。
- **目标场馆**：FPGA / ICCD / DATE；或 IEEE TCC。
- **风险与撞车**：
  - 撞车：FPGA SR 加速器文献存在（FSRCNN/LAPAR 类，**工作区未收录，需补检索**）；CLUT 原作者若自己做 FPGA 版则直接撞车——**立题前必须查证**。
  - 工程量中：前向算子简单，难点在 PCIe 帧通路 + 与解码器集成的端到端 demo。
  - **新颖性把握：中**。卖点是"首个 CLUT 类流式 SR 的开源硬件 + 端侧硬件能力回归编码决策"的系统闭环（接 CGF-20 的设备相关码率阶梯）。

## 备选（不展开）：MoQ 语义感知中继数据面
Scallop（CGC-18）已占"SFU 硬件数据面"，MoMQ（CGC-12）已占"媒体重要性元数据"，空白只剩"**57 MB 片上帧级抖动/重排缓冲 + 重要性丢弃**"——撞车风险中高、工程量高，仅当 Idea 3 的工具链前提（NPD-16）被证伪时作为替换。

---

## 横向比较与建议

| Idea | 大方向 | 新颖性 | 工程量（8 个月单人） | 撞车风险 | 天花板 |
|---|---|---|---|---|---|
| 1 OnChip-TRE | 网络/数据面 | **高** | 中 | 低 | FPGA/DATE + COMNET |
| 2 GlyphChip | 视频编码/云桌面 | **高** | 中高 | 低-中 | FPGA/DATE + TCC |
| 3 FlowState-57 | 网络/遥测 | 中 | 中 | 中 | FPGA/ICCD + COMNET |
| 4 DictPress | 存储/压缩 | 中低 | 低-中 | 高 | FCCM–DATE |
| 5 CLUT-VSR | 视频/端侧增强 | 中 | 中 | 中 | FPGA/ICCD + TCC |

- **首推 Idea 1（OnChip-TRE）**：空白证据最硬（TRE-PRO 引用 0 + FPGA 零命中）、与 VU13P 的 57 MB 形成"教科书级"动机（WTP-112 容量曲线的陡增段）、引擎窄、可用纯 trace + 民用 PC 评估，且与选题 A 的 DPDK 技能栈完全复用（DPDK 抓包 → PCIe → 卡），一份学习两份产出。
- **次推 Idea 2（GlyphChip）**：新颖性同样高且故事独特（ClearCodec 空位 + 80% 文字），但像素域编码器 + RD 分工的工程量与评估（可读性度量）都比 Idea 1 重，适合作为 Idea 1 做完后的延续或并行备选。
- Idea 3/5 是"中新颖性、中工程量"的稳妥项；Idea 4 仅作保底。

## 立题前必须补的检索（诚实清单）

1. FPGA dedup/RE 的存储语境变体（Idea 1）；
2. Teradici/PCoIP 及专利侧的文字专用硬件通路（Idea 2）；
3. FPGA flow telemetry/sketch 与 F3、N3IC 的全文比对（Idea 3）；
4. Xilinx Vitis 压缩库与 FPGA zstd 学术实现清单（Idea 4）；
5. CLUT 原作者团队与 FPGA SR 加速器最新工作（Idea 5）；
6. NPD-16 之后 Vitis NP4 是否已支持 register extern（影响 Idea 3 动机）。
