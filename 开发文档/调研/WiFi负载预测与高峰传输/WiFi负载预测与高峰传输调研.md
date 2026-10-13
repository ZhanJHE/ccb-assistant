# 《WiFi 负载预测与高峰时段高效传输》调研

## 0. 元信息
- **主题**：用"模型 + 算法"混合预测 WiFi 使用情况，以在高峰时段支持更高效的网络传输；含"中断重下抬高高峰负载"这一具体观察。
- **调研目标 / 边界**：①判定这个点子里各部分**是否已被研究**；②找出最接近的撞题工作；③识别真空白并给出证据强度。边界：只做**文献层面**的定性判断，不做方案设计、不做性能验证。
- **创建日期**：2026-09-29　**最后更新**：2026-09-29
- **关键词 & 同义词**：
  - 预测侧：WiFi/WLAN traffic prediction、AP load prediction、wireless traffic forecasting、channel utilization prediction、congestion prediction
  - 削峰侧：delay-tolerant / deferrable traffic、peak shaving、off-peak scheduling、demand shaping、delay-tolerant bulk data transfer、carbon-aware data movement
  - 浪费侧：traffic wastage、redundant traffic、protocol-independent redundancy elimination (RE/DRE)、partial packet recovery、resumable download / HTTP range request
  - 方法论：learning-augmented algorithms、algorithms with predictions、predict-then-optimize、peak-aware competitive analysis

---

## 1. 一句话总览

**这个点子的三块拼图——"用 ML 预测 WiFi 负载""在高峰做传输择时/削峰""用预测+算法混合并保证最坏情况"——每一块单独看都是成熟领域，分别有 20 年、17 年和 8 年的积累，且都有权威综述。真正没被人做的是第四块：把"无效/重复传输的字节量"本身当作一等优化目标，并让它与负载预测耦合。** 用户给出的"中断→无法续传→重下→抬高高峰负载"这条因果链，**在本次检索范围内没有任何论文做过量化**——这既是最有辨识度的空白，也意味着没有现成的动机段数字可以直接引用，需要自己测。

---

## 2. 把点子拆成 5 个可检索命题

这是本调研最重要的一步。用户的直觉是一个整体判断，但它在文献里对应五条互不相通的脉络；不拆开就会得出"好像都有人做过"或"好像没人做过"这类无效结论。

| 命题 | 内容 | 结论 | 证据强度 |
|---|---|---|---|
| **P1** | 用 ML/DL 预测 WiFi/WLAN/AP 的负载、拥塞、信道利用率、吞吐 | **红海**，有权威综述与成型小圈子 | 强 |
| **P2** | "模型驱动 + 数据驱动"混合预测（解析/物理/排队模型 + 学习） | 网络域仅有零散落点，**WiFi AP 负载上没人做** | 中 |
| **P3** | 用预测驱动"何时开始/是否推迟传输"，即高峰削峰择时 | **已做过 17 年**，奠基工作 2008–2013 | 强 |
| **P4** | 量化并抑制"无效/重复传输"的字节浪费 | 部分红海（视频浪费、链路上冗余消除），但**"中断重下"这条链无人量化** | 中（受检索限流影响） |
| **P5** | 用带最坏情况保证的"预测 + 在线算法"混合框架 | **成熟方法论**（learning-augmented algorithms），网络场景已有落地 | 强 |

下面逐条展开。

---

## 3. P1｜WiFi 负载预测：红海

### 3.1 成熟度证据
- 最早可追到 **2006 年**：Feng 等《SVM-Based Models for Predicting WLAN Traffic》（IEEE ICC 2006）与 2009 年的 Wi-Fi ARIMA 预测。
- 至少 5–6 篇综述，其中三篇是大权威：
  - **Szott 等《Wi-Fi Meets ML: A Survey on Improving IEEE 802.11 Performance With ML》**（IEEE COMST 2022，54 页 / 384 篇参考文献 / 分析 250+ 篇）——WiFi × ML 的头号综述。
  - **Jiang 等《Cellular traffic prediction with machine learning: A survey》**（ESWA 2022）。
  - **Sun 等《Wireless network traffic prediction—A comprehensive survey》**（Ad Hoc Networks，DOI 见 §8）——目前见到的最新一篇无线流量预测综述（**正文未取得，仅题录核实**）。
- 已有连续多届 Workshop（如 LATA 之于学习增强算法），说明是社区行为而非散点。

### 3.2 最接近用户想法的落点（必读）
| 论文 | 年/出处 | 为什么接近 |
|---|---|---|
| **AI/ML-based Load Prediction in IEEE 802.11 Enterprise Networks**（Wilhelmi，arXiv:2310.07467） | ICMLCN 2024 | 直接做**企业 WiFi 负载预测**；硬件受限模型平均误差 <20%、85 分位误差 3%；论文自述目标就是"主动驱动 WiFi 优化" |
| **Distributed Learning for Wi-Fi AP Load Prediction**（Salami，arXiv:2405.05140） | GLOBECOM 2024 | 联邦学习 + 知识蒸馏，在**真实大型校园网**上预测 AP 负载；精度较集中式最高 +93%，通信/能耗 −80% |
| **Cluster-Specific Predictive Modeling for Resource-Constrained Wi-Fi Controllers**（Fontanesi，arXiv:2603.21778） | MeditCom 2026 | 最新：WiFi 中央控制器上按簇建专属预测模型 |
| **A Spatio-temporal Prediction Methodology Based on Deep Learning and Real Wi-Fi Measurements**（Shaabanzadeh，arXiv:2408.09423） | Computer Networks 2024（CCF-B） | **100 个真实 AP、3 个月**数据，CNN+RNN 同时预测**流量负载与传输失败率**——"预测 WiFi 负载"这件事本身已被做完 |
| **FLAG**（Chen W.） | IEEE IoT-J 2021 | 大规模 WiFi **用户负载**长时预测；说明预测对象已覆盖"用户数"而非只有"吞吐" |

> 一个值得注意的细节：Wilhelmi / Salami / Fontanesi / Galati-Giordano / Kasslin 高度重叠，说明"WiFi AP 负载预测"已被一个固定团队当作主线在推进。

### 3.3 预测粒度与对象（已系统覆盖）
- **粒度**：从秒/分钟级（802.11 信道利用率短期预测，CNSM 2019；Wi-Fi 实时吞吐预测，JNCA 2020）到 10 分钟/小时级（绝大多数蜂窝 STGNN 论文）。甚至已有专文研究**测量粒度对预测精度的影响**（De Castro，IEEE HPSR 2026）。
- **对象**：业务量/吞吐（TU、throughput）、用户数/用户负载（FLAG）、信道利用率/占用率（CU、channel occupancy）、拥塞等级与丢包类型（UEMCON 2018；PlatCon 2024 区分"拥塞性丢包 vs 无线链路丢包"）、AP 负载。

### 3.4 预测→动作的闭环在 WiFi 上已很拥挤
WLAN 侧的"预测→决策"见 §7（P6 补充），典型是 AP 关联/切换/漫游、信道分配、空口公平。**但这些工作的目标函数是吞吐、公平、时延、能耗，没有一篇以"减少无谓/重复传输字节"为目标。**

---

## 4. P2｜"模型 + 算法混合预测"：方法论上不是新东西，但落在 WiFi 上确实没人做

这里要把用户口中的"模型+算法混合"拆成两种可能的意思，它们在文献里是完全不同的东西：

### 路线 A：模型驱动 + 数据驱动混合预测（物理/解析基线 + 学习残差）
- **网络域最明确的落点**：Wei 等《Hybrid Model-Data Driven Network Slice Reconfiguration by Exploiting Prediction Interval and Robust Optimization》（IEEE TNSM 2022）——把预测**区间**（而非点估计）喂给鲁棒优化做切片重配置。这是"预测 + 算法混合"最工整的网络侧范例。
- **最贴合该范式的技术文**：《Physics-Informed Digital Twins for Channel Estimation and Traffic Prediction of Non-Terrestrial Networks》（arXiv:2605.23155）——**确定性物理流量基线 + 神经网络预测随机残差再融合**。这是"混合"的标准配方。
- 其他：PINN 图网络流量预测（Electronics 2026）；排队论 + ML 混合预测过载（Computing 2025，异构领域可直接迁移）；PINN + 卡尔曼滤波混合（CISS 2024）。
- **空白**：PINN/"物理基线+残差"路线目前只落在**图神经网络 / 6G 蜂窝 / NTN 数字孪生**上，**没有一篇把它做到 WiFi 接入点负载**。这是用户点子里最新的一小块，但**"新"来自应用迁移，不是方法创新**——审稿人会这么问。

### 路线 B：预测器 + 在线算法 + 最坏情况保证（learning-augmented）
这是更强、更有发表价值的一支，见 §6。

### 陷阱提示
`traffic` 一词高度歧义。本次检索中 `physics-informed machine learning network traffic` 返回 40363 条，**绝大多数是道路交通/车辆流**；文献里的 `hybrid` 也常指"CNN+LSTM 之类的架构混合"而非"模型驱动+数据驱动"。后续检索必须显式加 `cat:cs.NI` 或 `WLAN/WiFi/802.11` 限定。

---

## 5. P3｜预测驱动的高峰削峰择时：已被做过 17 年

### 5.1 奠基与主线
| 论文 | 年/出处 | 关键点 |
|---|---|---|
| **Delay-Tolerant Bulk Data Transfers on the Internet**（Laoutaris，DOI:10.1145/1555349.1555376） | SIGMETRICS 2009（期刊版 ToN） | **本命题开山**：把可延迟的大批量传输存起来，挑网络空闲/廉价时段再送。前作 HotNets 2008《Good Things Come to Those Who (Can) Wait》直接主张给"可等待的流量"单独的时段/通道管理 |
| **Bartendr: a practical approach to energy-aware cellular data scheduling**（Schulman，DOI:10.1145/1859995.1860006） | MobiCom 2010（引用 287） | **"预测→决定何时传输"的经典闭环**，但预测对象是**信号/能耗**，目标是**省电** |
| **Economics of WiFi Offloading: Trading Delay for Cellular Capacity**（Lee，arXiv:1207.6607） | INFOCOM 2013 / TWC 2014 | 明确把**"延迟"当可交易资源**换取容量/成本，给出延迟容忍度阈值 |
| **Proactive Data Download and User Demand Shaping**（Tadrous，arXiv:1304.5745） | arXiv 2013 | **"预测用户需求→提前下载"并做需求整形（削峰）** |
| **Demand Shaping in Cellular Networks**（Zhou，arXiv:1707.02503） | Allerton 2014 / IEEE TCNS 2018 | 把蜂窝网需求整形形式化：可延迟流量参与调度以削峰 |
| **Proactive Resource Allocation**（El Gamal，arXiv:1010.1800；Tadrous，arXiv:1110.4703） | Allerton 2010 / IEEE TIT 2013 | **概念奠基**：利用用户行为的可预测性在**时间维度上**主动平衡无线流量 |

### 5.2 动机谱系（重要）
- **早期（2009–2015）**：设备**省电**（TailEnder / IMC 2009、Bartendr、5G inactive-state 利用）。
- **中期（2013–2018）**：**容量/成本/削峰**（WiFi offloading、demand shaping、DTN bulk transfer）。
- **2022–2026**：动机整体转向**碳**——Carbon-Aware End-to-End Data Movement（arXiv:2406.09650）、LinTS 碳感知时移传输（arXiv:2506.04117，IEEE CLOUD 2025，碳排放最多降 66%）、geo-shifted workloads 的网络碳代价（arXiv:2504.14022）。
- **"纯为削峰而推迟下载"在近中期文献里没有被单独强调**——这是用户点子在动机上的一个空隙，但也要注意：碳感知本质上是削峰的升级版，容易被归到同一族。

### 5.3 与用户想法最像的最新工作（**必读**）
| 论文 | 年 | 关键点 |
|---|---|---|
| **Predictive Traffic Shaping as a UE Network Control Loop in Wireless Systems**（Vasudevan，arXiv:2608.30019） | 2026 | **整条线里最像的一篇**：UE 用**带置信度**的预测，把弹性需求在"前瞻窗口"内择时释放到 RAN，并可向网络共享"未来风险描述符" |
| **Predictive and Preventive Digital Twin Framework for Indoor Wireless Networks**（Chen，arXiv:2601.13838，44 页） | 2026 | **撞题度最高**：数字孪生刻画时空信道+流量，**预测未来拥塞并在发生前**改配置；摘要原话 "predict time-dependent network congestion and mitigate it in advance" |
| **Admission Control for Inelastic Traffic on a Link Shared by Deadline-Driven Elastic Traffic**（Kreidl，arXiv:2509.08135） | 2025 | **准入控制**形式化为随机最短路径：状态=弹性流量大小/deadline，动作=准入哪些流，权衡"立即收益 vs 错过 deadline 风险" |
| **Carbon-Aware Temporal Data Transfer Scheduling Across Cloud Datacenters (LinTS)**（Rodrigues & Kosar，arXiv:2506.04117） | 2025 | 按"何时最合适"择时搬数据，碳排最多降 66% |

> **闭口径已存在**：预测侧有 LinkForecast、Lumos5G、TUBO、LEAD；闭环侧有 Bartendr、Chen 2026、Vasudevan 2026、Prediction-Guided Control in DCN（arXiv:2601.03593，2026）。**但"把 WiFi/AP 层面的未来负载预测直接接到客户端批量传输何时开始"我没有检索到。**

---

## 6. P4｜"无效/重复传输"的量化与抑制：一半是红海，缺的那一半正是用户直觉

这一节是本次调研信息量最大、也最需要用户认真读的一节，因为它同时给出**正面证据**和**反方证据**。

### 6.1 "下载了却没用上 = 浪费"已是成熟子领域，但全部落在视频/预取场景
| 论文 | 年/出处 | 关键数字 |
|---|---|---|
| **The cost of aggressive HTTP adaptive streaming: Quantifying YouTube's redundant traffic**（Sieber） | IM 2015 | 网络条件变化时并行下多个码率、只有一个被播放，**冗余流量最高 33%** |
| **Sacrificing efficiency for QoE: YouTube's redundant traffic behavior**（Sieber） | IFIP Networking 2016 | **>12,000 次观看**大规模实验：同一 segment 被传两遍以上码率 |
| **Short Video Streaming With Data Wastage Awareness**（Zhang） | ICME 2021 | 实测**45.2% 的短视频数据被浪费**（下载后因用户切走被丢弃）；所提 WAS 可降浪费 **70%** |
| **Reducing Traffic Wastage in Video Streaming via Bandwidth-Efficient Bitrate Adaptation**（Su，arXiv:2412.07270） | 2024 | 首次严格建模 "traffic wastage = 用户最终不消费却已下载的 segment"，提出 BDV 指标 |
| **Bandwidth-Efficient Multi-video Prefetching for Short Video Streaming**（Zuo，arXiv:2206.09839） | 2022 | 用户下滑切走导致显著带宽浪费；给出自适应多视频预取形式化 |
| **Prefetching for Short Video Streaming: ... at Planetary Scale**（Zhang） | SIGCOMM 2026 | 头部短视频平台**两年**预取算法演进，上亿用户 A/B，显式权衡 startup/卡顿/带宽用量 |

**与用户想法的关系**：这些量化的正是"无效传输占总流量的比例"，同源；但**浪费成因是"用户行为突变（跳过/早退/码率切换）"，不是"传输中断后无续传能力而从零重下"**。

### 6.2 "用户因体验差而放弃"也被量化透了
- **Krishnan 2012（IMC）**：首次建立"画质→用户放弃"的**因果**关系。
- **Nam 2016（INFOCOM，YouSlow，40 万+ 观看 / 100+ 国家）**：rebuffer 造成放弃率是启动延迟的 **6 倍**；单次 rebuffer 的影响是码率切换的 **3 倍**；提高码率反而可致放弃率升 **4 倍**。
- **Shafiq 2014（SIGMETRICS）**：运营商侧一个月数据、31 个网络因子对移动视频参与度的影响。
- **Arapakis 2021（CHIIR）**：用户耐心锚点——移动用户比桌面**宽容 4×**，但超过 **7–10 s** 阈值后体验显著恶化。

### 6.3 连接建立 / 状态转换 / 重启的成本，被反复量化
- 蜂窝侧：Qian 2010（首个可推断 UMTS 状态机的轻量探测法）、Perälä 2009（4 网/3 国实测 RRC 状态转换）、Huang 2012（LTE 功耗权威模型）、Rosen 2014、**Deng 2012（CoNEXT，预测流量突发起止可省 3G 51–66%、LTE 67% 能量）**、**Huang 2013（SIGCOMM，LTE 下平均实际使用带宽 < 可用带宽的 50%）**。
- WiFi 侧：**Mishra 2003（CCR，引用 861）**——802.11 MAC 层切换延迟分解实测，probe 是主要贡献项。
- 握手/安全侧：Naylor 2014（CoNEXT，"The Cost of the S in HTTPS"）。
- TCP 重启侧：Dukkipati 2010（CCR，初始拥塞窗口从 ~4KB 起步的代价）。

> **结论**："连接建立/状态转换有成本"不是空白，是经典结论。这为用户"中断代价很高"的直觉提供了可引用的支撑。

### 6.4 断点续传被当成系统问题研究过，但方向是"少传"而非"失败重下的浪费"
- **MP-H2（MobiCom 2019）**：把单个 HTTP 对象切成 byte range requests，同时走 WiFi+蜂窝多路径并动态负载均衡。
- **Seekable OCI（arXiv:2607.06868，2026）**：给标准 OCI 镜像建外部索引，运行时用 HTTP range request 按需取字节，不必下整镜像。
- **DBPP（arXiv:2607.05596，2026）**：containerd 把层切块并发 range 拉取，乱序块堆积撑爆堆内存——31–48 GiB 镜像下成为主瓶颈。
- **CDN Backfired（DSN 2020）**：HTTP Range 请求被当**安全攻击面**系统研究（range 滥用可放大攻击）。
- 元老：**rsync（Tridgell 1996）**——用 delta 只传差异；**RFC 7233** 是断点续传依赖的协议本体。

### 6.5 网络中间节点的冗余消除：25 年的成熟方向
| 论文 | 年/出处 | 关键数字 |
|---|---|---|
| **A protocol-independent technique for eliminating redundant network traffic**（Spring & Wetherall，DOI:10.1145/347059.347408） | SIGCOMM 2000（引用 394） | **开山之作**：Rabin 指纹 + 缓存 + 抽样字节，无需理解应用协议即可消除重复串 |
| **SmartRE**（Anand，DOI:10.1145/1592568.1592580） | SIGCOMM 2009（引用 245） | 把 RE 从单体中间盒升级为**网络级协同服务** |
| **EndRE**（Aggarwal） | USENIX NSDI 2010（引用 210） | 11 个企业站点 TB 级 trace + 试点：**平均省 26% 带宽**，1.5–4 Gbps |
| **Redundancy in network traffic: findings and implications**（Anand，DOI:10.1145/1555349.1555355） | SIGMETRICS 2009（引用 229） | Winnowing 比 Rabin 多省 5–10%，个别 trace 达 35% |
| **On Protocol-Independent Data Redundancy Elimination**（Zhang，综述） | IEEE COMST 2014 | **行业公认区间**：接入链路 **15–60%**、**Wi-Fi 近 50%**、蜂窝数据量最高 **60%** |

#### 无线/WiFi 侧的专门工作
- **ZipTx（MobiCom 2008，引用 124，DOI:10.1145/1409944.1409984）**：**WiFi 链路级"避免整包重传"的代表**——从部分损坏包恢复数据，且不需改 PHY。同族有 Maranello（NSDI 2010）、Unite（MobiSys 2011）。
- **Halepovic（IEEE ICC 2012）**：**WLAN 上的 RTE 专项**——WLAN 上可行但弱于有线；把 MAC 头也纳入 RTE 可在公共 WLAN 再多省 **53%**；丢帧/重传是主要挑战。
- **Sanadhya（MobiCom 2012）**：30 个移动用户 trace，源端缓存只需目的端 1/100，仍能消除 **>89%** 的可达冗余。
- **Lumezanu（IMC 2010）**：三家运营商 trace，蜂窝 RE 能让**多数用户省 ≥10%**。
- **OARE（IEEE TVT 2016）**：**AP 侧** RE，利用无线广播被旁听特性编码分块，包传输时间降 **7.8%–23.2%**。
- **Finamore（CoNEXT 2013，引用 55）**：**最贴近用户直觉的一篇**——3G/4G 瓶颈在接入链路时，缓存**无法**减轻无线链路负担，因为同一对象的多份副本仍要各自过空口。

#### ⚠️ 反方证据（必须知道）
- **Hu & Seetharam《Redundancy Elimination Might Be Overrated: A Quantitative Study on Real-World Wireless Traffic》（INFOCOM WKSHPS 2017，arXiv:1605.04021）**：真实无线流量中实测冗余**远低于**文献报告值（除非用户兴趣高度同步），加密进一步削弱效果。
- 这意味着"无线侧能省多少"这件事本身**是有争议的**，不能拿 2014 综述的 50% 当既成事实。

#### 可编程交换机时代的停滞（一个重要观察）
- **TRE-PRO（Jang，IEEE Network 2021）**：在可编程交换机 ASIC 上在线消除冗余，**唯一直接的"交换机数据面 TRE"实现论文**，S2/OpenAlex 引用数均为 **0**。
- 2023–2026 的"交换机内去重"工作全部转向**应用侧**：NetCache（SOSP 2017，缓存热键）、CableCache（HotStorage 2025，KV 请求去重）、MPINT（CoNEXT WS 2025，遥测去重）。
- **没有一篇继续做通用流量的在网去重**，而硬件能力（可编程缓存、P4 算力）这几年在涨 → **"能力在涨、研究没人做"**。

### 6.6 本命题中"没人做"的部分
用 `aborted transfer / interrupted download / restart from scratch / re-download / duplicate transfer due to failure / download retry overhead / redundant retransmission cost` 等 12+ 组关键词，跨 arXiv + OpenAlex + S2 合计 50+ 次查询，**没有命中任何一篇实测研究给出"因中断且不可续传而从零重下造成的额外流量占比"数字**。最接近的计量替代物只有：
- 视频冗余/浪费占比（33%、45.2%）
- 蜂窝下带宽利用率不足（<50%）
- 连接状态转换/重连的能耗代价（51–67%）

**"没找到" ≠ "不存在"**：该量词可能藏在 ① 运营商/网管流量审计与计费偏差报告，② DTN/mobility 社区用不同术语（如 failed transmission energy cost），③ 3GPP/厂商白皮书等非论文材料。本次均未覆盖。

> **2026-10-02 G0 复核（更换网络环境后）**：用 OpenAlex + S2 REST（带 Key）双源，在原 12+ 组关键词上增补上述①②盲区术语（failed transmission / intermittent connectivity / opportunistic network / traffic audit / billing accuracy 等），合计 20+ 组查询重跑——**仍零命中**。过程中只捞出三个近邻：DTD-HTTP（Mogul，NSDI 2004，HTTP 层重复负载检测，属 RE 家族）、RetryGuard（arXiv:2511.23278，云/微服务重试风暴）、Flare（OSDI 2018，360° 视口浪费变体）——均已登记为 WTP-134/135/136。另更正：WTP-40 已正式发表于 IEEE TMC 2024（DOI:10.1109/TMC.2024.3373498）。**G2 空白可信度由"中"上调至"中高"**；剩余盲区：DBLP/Google Scholar（反爬不可达）、IEEE Xplore API（账号待激活）。

---

## 7. P5｜"模型 + 算法混合"的最强版本：learning-augmented algorithms（已有成熟框架）

如果用户想要的是"**预测器 + 算法，且预测不准时仍保证不坏**"，那这不是新点子，而是有教科书式框架的成熟领域。

### 7.1 奠基与综述
| 论文 | 年/出处 | 关键点 |
|---|---|---|
| **Competitive Caching with Machine Learned Advice**（Lykouris & Vassilvitskii，arXiv:1802.05399 / DOI:10.1145/3447579） | ICML 2018 / JACM 2021 | **领域奠基**：paging 加"预测下一请求"的顾问，首次形式化 **consistency**（预测准→近最优）与 **robustness**（预测再烂→最坏情况有界）的权衡 |
| **Improving Online Algorithms via ML Predictions**（Purohit 等） | NeurIPS 2018 | 引入 ski-rental 与非先知调度框架，提出"误差容忍度 η" |
| **Algorithms with Predictions**（Mitzenmacher & Vassilvitskii，arXiv:2006.09123 / DOI:10.1145/3528087） | 书章 2020 / **CACM 2022** | **头号入门综述**，明确设计目标与全部基础例子 |
| **Learning-Augmented Algorithms: Guarantees, Construction Mechanisms, and System-Level Implications**（Zhao 等，arXiv:2609.04787） | 2026 综述 | **最新综述**：系统化"预测接口 / 误差度量 / consistency–robustness 权衡 / 五类构造机制"，并区分**形式保证**与**系统实证** |
| **Optimal Robustness-Consistency Trade-offs**（Wei & Zhang，arXiv:2010.11443） | NeurIPS 2020 | 给出 ski-rental 与非先知调度的**权衡下界**——证明前述权衡已最优 |
| **Online Metric Algorithms with Untrusted Predictions**（Antoniadis 等，arXiv:2003.02144） | ICML 2020 / TALG 2023 | "**不可信预测**"通用框架：性能写成**预测误差 ε 的函数** |
| **LATA（4th Workshop on Learning-augmented Algorithms）**（DOI:10.1145/3848038.3848057） | ACM SIGMETRICS PER 2026 | **已有连续四届专题 Workshop + ACM 特刊** → 成熟社区 |

### 7.2 网络 / 传输 / 带宽场景的落地（说明"已有先例"）
| 论文 | 年/出处 | 关键点 |
|---|---|---|
| **Learning-Augmented Online Packet Scheduling with Deadlines**（Liang, Stein, Wei，arXiv:2305.07164） | arXiv 2023 | **最接近交换机场景**：每步决定转发/丢弃哪些包，用预测提升竞争比且**预测误差任意大时竞争比仍有界** |
| **Asymptotically Robust Learning-Augmented Algorithms for Preemptive FIFO Buffer Management**（Hsieh & Liang，arXiv:2604.26349） | arXiv 2026 | 交换机 FIFO 缓冲管理：同时达 **1-consistency / η-smoothness / √3-robustness**；提出"输出型预测误差度量" |
| **Prediction Augmented Segment Routing**（Kodialam & Lakshman） | IEEE HPSR 2021 | 预测直接用于**段路由**，摘要即写 consistency/robustness 两目标 |
| **A Learning-Augmented Overlay Network**（Dallot 等，arXiv:2509.11904） | arXiv 2025 | 用**不可信需求预测**分布式调 overlay 拓扑与转发表 |
| **Safeguard Network Slicing in 5G**（Cheng 等） | IEEE JSAC 2020 | 5G 网络切片的两阶段学习增强优化 |
| **Learning-Augmented 360° Video Streaming**（Chen, Hajiesmaili, Sitaraman） | ACM 2026 | **带宽受限视频传输**：明确"需要能对抗预测精度变化的码率分配器" |
| **Scheduling with Speed Predictions**（Balkanski 等） | 2024/2025 | **速度（=带宽类比物）可预测**的调度，误差函数化的界 |
| **Contract Scheduling with Predictions**（Angelopoulos & Kamali，DOI:10.1613/jair.1.14117） | JAIR 2023 / AAAI 2021 | **中断/重启式的"合同调度"加预测**——与"传输被打断"结构上相关 |

### 7.3 峰值感知（peak-aware）——**只在能源域存在**
| 论文 | 年/出处 | 关键点 |
|---|---|---|
| **Learning-Assisted Competitive Algorithms for Peak-Aware Energy Scheduling**（Lee, Hajiesmaili, Li，arXiv:1911.07972） | 2019 | 提出 "**peak-aware**" 竞争框架：目标是压低**峰值**而非均值，预测差时鲁棒、预测准时时近最优，实测比纯在线算法好 **15.13%** |
| **Online demand peak shaving with machine-learned advice**（Feng 等，DOI:10.1049/dgt2.12012） | 2024 | **"削峰 + ML 建议 + 保最坏界"**——用户想法在能源域的镜像 |
| **Risk-Sensitive Peak-Aware Energy Scheduling**（Himmelreich, Christianson, Wierman，DOI:10.1145/3848038.3848064） | SIGMETRICS PER 2026 | 把"峰值感知"升级为**风险敏感**版本，说明该线仍在活跃推进 |
| **Online Primal-Dual Algorithms with Predictions**（Thang，arXiv:2110.00391） | 2021 | 预测驱动的原始-对偶构造 |

> **关键结论**：**"压低峰值"作为竞争目标在网络/带宽侧没有被形式化过**——peak-aware 只在能源调度里存在。这是本命题里最干净的一个理论空白。

### 7.4 边界说明：另一套保证观
- **predict-then-optimize**（Elmachtoub & Grigas，ICML 2020，SPO）：训练损失对齐**下游决策代价**，但**没有**最坏情况竞争比——与 learning-augmented 是两套保证观，别混引。
- **DRL for networking**（Valadarsky《Learning to Route》HotNets 2017，引用 249；Jay《Internet Congestion Control via DRL》2018）：能超过 OSPF，但**无任何最坏情况保证**——正是 learning-augmented 要补的那一半。

---

## 8. 补充｜P6：WLAN 负载感知管理（AP 关联/切换/信道/公平）与预测结合

虽然用户的点子不在这一层，但既然涉及"WiFi 高峰"，这一层是最容易被审稿人拿来问的相邻工作。

| 论文 | 年/出处 | 关键点 |
|---|---|---|
| **Fairness and Load Balancing in Wireless LANs Using Association Control**（Bejerano，DOI:10.1145/1023720.1023751） | MobiCom 2004 / ToN 2007（引用 584） | **奠基**：把 AP 关联控制形式化为负载均衡 + max-min 公平；用**当前**（非预测）负载 |
| **Ending the Anomaly: Low Latency and Airtime Fairness in WiFi**（Høiland-Jørgensen，arXiv:1703.00064） | USENIX ATC 2017 | 尾部速率 station 会**吃掉不成比例的空口时间（浪费空口）**，用 FQ-CoDel + airtime 记账修复 |
| **Channel Load Aware AP / Extender Selection in Home WiFi Using 802.11k/v**（Adame，arXiv:2004.08110） | IEEE Access 2021 | **负载感知 AP 选择代表作**：仿真下可多承载 **35%** 流量不拥塞，真实部署总吞吐 **+77.12%**；用的是**实时**负载，不是预测 |
| **Load-aware Channel Selection for 802.11 WLANs with Limited Measurement**（Karaca，arXiv:1301.2750） | ICT 2016 | **用高斯过程回归"补出"未测信道的负载**再选信道，负载测量耗时 **−46%**——"学习→负载→决策"的早期代表作 |
| **ML-based Handover Prediction and AP Selection in Cognitive Wi-Fi Networks**（Khan，arXiv:2111.13879） | 2021 | **最贴近"预测→关联"**：把**不必要切换减少 60%/50%**，吞吐 **+9.2%/+8%** |
| **Forecaster-Aided User Association and Load Balancing in Multi-Band Mobile Networks**（Gupta，arXiv:2301.09294） | IEEE TWC 2023 | **方法学上就是用户想法的"蜂窝版"**：先 RNN 预测用户未来可达速率，再做凸效用最大化的关联/频段分配 |
| **A Survey of Anticipatory Mobile Networking**（Bui，DOI:10.1109/COMST.2017.2694140） | IEEE COMST 2017（引用 219） | **"预测→网络优化"整条线的权威综述**，说明该思路在 2016 年前已系统性存在 |
| **Multi-Link Operation and Wireless Digital Twin to Support Enhanced Roaming in Next-Gen Wi-Fi（WiTwin）**（Scanzio，arXiv:2404.18313） | IEEE WFCS 2024 | 数字孪生指导 station 在正确时机做最优关联/重关联（含 Wi-Fi 7 MLO） |
| **AI-Driven Multi-Objective Optimization for Energy-Efficient Campus Wireless LANs**（Huangfu） | IEEE ICEACE 2025 | **与"高峰浪费"最同构（但对象是能耗）**：校园 WLAN 的**潮汐式流量模式造成大量能量浪费** |
| **PACT: AI and Digital Twin based Proactive Congestion Prediction**（Chezhiyan） | IEEE GCON 2026 | 摘要直指"**peak traffic events** 下传统反应式拥塞控制导致时延上升" |

### 产业界（只列**已核实**的部分）
- **HPE Aruba Networking Central**：官网写 "AI-native agentic intelligence, self-driving automation"、客户案例含 "AI-powered visibility and **predictive analytics**"——但**页面没有说"预测 WiFi 负载"**，属 AIOps/预测性运维范畴。
- **Cisco Catalyst Center**：有 "Cisco **AI Network Analytics**"、"assurance with **AI/ML**"、"deep insights into capacity and performance"——措辞是 assurance/analytics，**未见"预测负载"字面承诺**。
- **华为 Stellar AI Network / AirEngine**：以"AI 网络"整体包装 WLAN，**抓到的页面没有"AI 预测 WiFi 负载"具体表述**。
- ⚠️ **待核实**：华为 iMaster NCE-CampusInsight（最可能承载该宣传语的产品名）4 个候选 URL 全部 404；Juniper Mist AI / Marvis 页面 404/403。**因此本次不能声称任何厂商宣传过"AI 预测 WiFi 负载"**，需查产品 Data Sheet 或发布会稿。

### 目标函数的实情
这一层的优化目标是：吞吐/空口效率、公平（max-min、airtime fairness）、时延/QoS、能耗、避免性能退化。**没有任何一篇以"减少无谓/重复流量字节"为一等目标。** 最接近的三个"半占位"是：Khan（减少**不必要切换**，牺牲的是信令开销不是数据字节）、airtime fairness 系列（消灭**浪费的空口时间**，但目标是公平与时延）、Huangfu（同样的"潮汐浪费"直觉，但度量是**电**）。

### 术语陷阱
`band steering` / `client steering` 在 arXiv 全文检索 **0 命中**，S2 里大量混入天线波束赋形论文；学术等价物是 **dual-band access selection**（Zhang，IEEE TNSM 2019）。这两个词基本停留在厂商文档/专利域。

---

## 9. 撞题清单（按"必须先读"排序）

1. **Predictive Traffic Shaping as a UE Network Control Loop**（arXiv:2608.30019，2026）——整条线最像，机制上已含"带置信度预测 + 前瞻窗口择时释放弹性需求"。
2. **Predictive and Preventive Digital Twin Framework for Indoor Wireless Networks**（arXiv:2601.13838，2026）——WiFi 上"预测拥塞并提前缓解"已实现。
3. **AI/ML-based Load Prediction in IEEE 802.11 Enterprise Networks**（arXiv:2310.07467，ICMLCN 2024）——WiFi AP 负载预测 + 明确说用于驱动优化。
4. **A Spatio-temporal Prediction Methodology … Real Wi-Fi Measurements**（arXiv:2408.09423，Computer Networks 2024）——100 AP / 3 个月的负载与失败率预测。
5. **Delay-Tolerant Bulk Data Transfers on the Internet**（SIGMETRICS 2009）+ **Bartendr**（MobiCom 2010）——"择时传输"的两块奠基石。
6. **Learning-Augmented Online Packet Scheduling with Deadlines**（arXiv:2305.07164）+ **FIFO Buffer Management**（arXiv:2604.26349）——把预测+算法用到交换机的现成模板。
7. **Learning-Assisted Competitive Algorithms for Peak-Aware Energy Scheduling**（arXiv:1911.07972）+ **Online demand peak shaving with ML advice**（DOI:10.1049/dgt2.12012）——"峰值感知 + 预测 + 保证"的完整范式，但在能源域。
8. **Redundancy Elimination Might Be Overrated**（arXiv:1605.04021）+ **Finamore CoNEXT 2013**——两条**泼冷水**的证据，决定"能省多少"的可信区间。

---

## 10. 研究空白判断（标注证据强度）

| # | 空白 | 说明 | 证据强度 |
|---|---|---|---|
| **G1** | **把"无效/重复传输的字节量"作为一等目标函数，并与负载预测耦合** | RE 文献的目标是链路省带宽，但不看负载时序；负载预测文献不涉及冗余抑制。用户的想法正落在两者缝隙 | **强**（多路独立检索一致，且反方文献也未越界） |
| **G2** | **"中断 → 无法续传 → 从零重下 → 抬高高峰负载"这条因果链的量化与建模** | 跨 arXiv/OpenAlex/S2 用 12+ 组关键词、50+ 次查询，无一篇给出该占比数字 | **中**（受 429/403 限流影响，"没找到"≠"不存在"） |
| **G3** | **peak-aware 的"带宽/传输"竞争调度** | peak-aware 只在能源调度里被形式化；网络侧只有吞吐/时延/竞争比目标 | **中强**（方法论文献覆盖较完整，仍受限流影响） |
| **G4** | **模型驱动 + 数据驱动的混合预测用在 WiFi AP 负载** | PINN/"物理基线+残差"只落在 GNN / 6G 蜂窝 / NTN 数字孪生 | **中**（属应用迁移，非方法创新，价值有限） |
| **G5** | **把"用户是否会中途放弃/断线"作为传输准入或择时的输入信号** | "用户放弃"研究全部停在测量与建模；所有"预测→择时/准入"工作都以链路条件/能量/碳/成本为预测对象 | **中** |
| **G6** | **可编程交换机上的通用流量冗余消除（2021 后停滞）** | TRE-PRO（2021）是唯一实现且引用为 0；后续全转应用侧去重。硬件能力在涨、研究没人做 | **中**（存在反方证据质疑无线侧冗余被高估） |

---

## 11. 给用户的收敛建议（三个切口）

### 切口 A（推荐，方法论最稳）：峰值感知 + 预测驱动的可延迟传输准入
- **一句话**：把"压低高峰时段的传输峰值"形式化为 online 目标，用加载荷预测的算法做"准入 / 推迟 / 降级"决策，并给出预测不准时的最坏情况保证。
- **为什么可行**：①"模型+算法混合"的字面要求完全吻合；②方法论有成熟模板（Lykouris、Mitzenmacher、Liang/Stein/Wei、peak-aware 系列）可迁移；③真空白明确（G3）。
- **风险**：理论贡献需要竞争比分析，门槛在数学而非工程；若只做仿真验证，需注意 CCF 分级期刊对"纯理论/纯仿真"的接受度差异。

### 切口 B（最贴近原始直觉，工作量在测量）：重下浪费的实测与抑制
- **一句话**：在受控实验（Mininet/ns-3 + 真实 trace，或真实 AP）中量化"无续传 → 重下"造成的额外字节与高峰负载抬升，再证明"续传能力 + 按预测负载门控"能削掉多少。
- **为什么可行**：①G2 无人量化，动机段可以自己造数字；②国际上有可比的测量方法论（Sieber / Zhang / Su 的视频 wastage 口径可借）。
- **必须先回答的问题**：**"无断点续传"这个前提在 2026 年还成立吗？** 见 §12 的技术提醒。

### 切口 C（工程向，慎选）：AP/家用路由器上的"负载预测 + 冗余抑制"联合调度
- **一句话**：把 2021 年停滞的在网去重（客户可选择可编程交换机或 FPGA 方案）重新捡起来，用负载预测作为去重的启停/调度信号。
- **风险**：**Hu 2017 的反方证据**直接质疑无线侧冗余量级；且需要真实硬件（可编程交换机获取门槛正在变高——见本工作区既有结论：Tofino 已停产）。

---

## 12. 一个必须指出的技术前提问题

用户的观察是"如果**他不能断点续传**，就要从头重下"。这里有一处需要修正：

- **HTTP Range 请求（断点续传）早在 1999 年（HTTP/1.1）就标准化了**（RFC 2616 → 现 RFC 7233），现代浏览器、下载工具、包管理器、容器运行时**普遍支持**续传；断点续传的早期工程文献可追到 2001 年的 resumable FTP。
- 也就是说，"客户端完全不支持续传导致整体重下"这个**特定前提，在今天的通用场景里已经基本消失**。
- 但**浪费本身没有消失，只是换了形式**：
  - 服务端/中间件**不支持 Range**（部分动态生成内容、部分存储后端）；
  - **Range 粒度粗**（DBPP 2026 指出容器镜像分块并发拉取会撑爆内存）；
  - 连接断开后**已传字节白传**的更宽泛形式——用户切走、码率切换、预取落空（视频场景实测 33%–45.2%）；
  - **重复取回同一对象**（Anand 2009、Rhea 2003 的"资源被修改/URI 别名"）。

**所以建议把命题从"支持断点续传"升级为"减少已传字节的作废率"。** 这个版本：①更符合 2026 年的技术现实；②可以直接对接已有的 33%/45.2% 浪费口径，动机段有数字可引；③仍然完整保留用户的核心洞见——**浪费的字节会抬高高峰时段的负载，而这件事可以由负载预测来优化**。

---

## 13. 检索方法与局限（诚实说明）

### 已做的
- **双源检索**：arXiv Atom API（`export.arxiv.org`）+ Semantic Scholar Graph API（`x-api-key` 来自环境变量，未落盘）。
- **7 条独立线索并行**：WiFi 负载预测 / 削峰择时 / 中断浪费测量 / 吞吐与准入预测 / 学习增强算法 / WLAN 负载感知管理 / 网络侧冗余消除。
- **滚雪球**：对 Lykouris 2021（152 条被引）、Bartendr（40 条）、D3（40 条）、Wilhelmi/Salami、Bejerano 2004、Gupta 2023 等做了 citations / references 追踪。
- **独立复核**：本次由主会话**逐条核验**了 20 个 arXiv ID（批量 `id_list` 拉取，标题逐字比对）与 14 个 DOI（S2 `paper/batch`，年份/场馆/引用数比对），全部命中。

### 局限（影响"没找到"结论的可信度，必须知道）
1. **arXiv 官方 API 在本环境大范围返回 HTTP 429**（7 条线索中有 5 条报告"多组查询因限流失败"），因此**"按提交日期排序扫最新"这一步没有完整做成**，近 3 年覆盖依赖 S2/OpenAlex 的预印本索引与 `arxiv.org/search` HTML 页。
2. **WebSearch 工具返回 403（当前订阅无权限）**，全程未能用搜索引擎兜底交叉验证。
3. **DBLP 不可达**（连接失败/人机验证），未能用于 CS 场馆交叉核对；**ACM DL 部分 403**、IEEE Xplore 未直连、ScienceDirect 403。
4. 因此：**"没找到"在这几处不等于"不存在"**。若要正式立题，"G2/G3/G5"应先补一轮不受限流的检索（换网络环境、直连 DBLP + IEEE Xplore），并在正式综述里重跑一遍关键查询。
5. 本表中**所有引用数均为抓取时刻的快照**（S2 / OpenAlex），会过时，仅供相对比较。
6. 多篇论文仅取得题录/摘要（付费墙或摘要截断），已在表中以"待核实"标注；**引用其实测数字前需开全文核对**。

---

## 14. 参考文献（真实可点击出处）

> 只列正文引用到的核心条目；完整登记见 `文献索引.md` 的 **WTP+** 一节。
> 标注 ⚠️ 者表示本次只到题录/摘要级，数字或场馆待核实。

### 预测侧
- [AI/ML-based Load Prediction in IEEE 802.11 Enterprise Networks](https://arxiv.org/abs/2310.07467)（ICMLCN 2024, DOI:10.1109/ICMLCN59089.2024.10624775）
- [Distributed Learning for Wi-Fi AP Load Prediction](https://arxiv.org/abs/2405.05140)（GLOBECOM 2024, DOI:10.1109/GLOBECOM52923.2024.10901369）
- [Cluster-Specific Predictive Modeling for Resource-Constrained Wi-Fi Controllers](https://arxiv.org/abs/2603.21778)（MeditCom 2026）
- [A Spatio-temporal Prediction Methodology Based on Deep Learning and Real Wi-Fi Measurements](https://arxiv.org/abs/2408.09423)（Computer Networks 2024, DOI:10.1016/j.comnet.2024.110569）
- [Wi-Fi Meets ML: A Survey on Improving IEEE 802.11 Performance With ML](https://arxiv.org/abs/2109.04786)（IEEE COMST 2022, DOI:10.1109/COMST.2022.3179242）
- [Studying the Role of Synthetic Data for ML-based Wireless Networks Traffic Forecasting](https://arxiv.org/abs/2601.07646)（arXiv 2026）
- ⚠️ Wireless network traffic prediction—A comprehensive survey（Ad Hoc Networks, DOI:10.1016/j.adhoc.2026.104380）——正文未取得
- [Analyzing the Impact of Temporal Measurement Granularity on Network Traffic Forecasting](https://doi.org/10.1109/HPSR68369.2026.11615136)（IEEE HPSR 2026）
- 经典：[SVM-Based Models for Predicting WLAN Traffic](https://doi.org/10.1109/ICC.2006.254860)（ICC 2006）；[An ARIMA model for forecasting Wi-Fi data network traffic values](https://doi.org/10.15446/ing.investig.v29n2.15163)（2009）

### 预测→动作 / 削峰择时
- [Delay-Tolerant Bulk Data Transfers on the Internet](https://doi.org/10.1145/1555349.1555376)（SIGMETRICS 2009）
- [Bartendr: a practical approach to energy-aware cellular data scheduling](https://doi.org/10.1145/1859995.1860006)（MobiCom 2010）
- [Economics of WiFi Offloading: Trading Delay for Cellular Capacity](https://arxiv.org/abs/1207.6607)（INFOCOM 2013 / TWC 2014）
- [Proactive Data Download and User Demand Shaping for Data Networks](https://arxiv.org/abs/1304.5745)（arXiv 2013）
- [Proactive Resource Allocation: Harnessing the Diversity and Multicast Gains](https://arxiv.org/abs/1110.4703)（IEEE TIT 2013）
- [Proactive Resource Allocation: Turning Predictable Behavior into Spectral Gain](https://arxiv.org/abs/1010.1800)（Allerton 2010）
- [Predictive Traffic Shaping as a UE Network Control Loop in Wireless Systems](https://arxiv.org/abs/2608.30019)（arXiv 2026）
- [A Predictive and Preventive Digital Twin Framework for Indoor Wireless Networks](https://arxiv.org/abs/2601.13838)（arXiv 2026）
- [Admission Control for Inelastic Traffic on a Link Shared by Deadline-Driven Elastic Traffic](https://arxiv.org/abs/2509.08135)（arXiv 2025）
- [Carbon-Aware Temporal Data Transfer Scheduling Across Cloud Datacenters](https://arxiv.org/abs/2506.04117)（IEEE CLOUD 2025）
- [Carbon-Aware End-to-End Data Movement](https://arxiv.org/abs/2406.09650)（arXiv 2024）
- [A Survey of Anticipatory Mobile Networking](https://doi.org/10.1109/COMST.2017.2694140)（IEEE COMST 2017）

### 浪费 / 中断 / 续传 / 冗余消除
- [The cost of aggressive HTTP adaptive streaming: Quantifying YouTube's redundant traffic](https://doi.org/10.1109/INM.2015.7140478)（IM 2015）
- [Short Video Streaming With Data Wastage Awareness](https://doi.org/10.1109/ICME51207.2021.9428379)（ICME 2021）
- [Reducing Traffic Wastage in Video Streaming via Bandwidth-Efficient Bitrate Adaptation](https://arxiv.org/abs/2412.07270)（arXiv 2024）
- [Bandwidth-Efficient Multi-video Prefetching for Short Video Streaming](https://arxiv.org/abs/2206.09839)（arXiv 2022）
- [Prefetching for Short Video Streaming: Experiences from a Longitudinal Evolution at Planetary Scale](https://doi.org/10.1145/3789240.3829158)（SIGCOMM 2026）
- [Video stream quality impacts viewer behavior](https://doi.org/10.1145/2398776.2398799)（IMC 2012）
- [QoE matters more than QoS: Why people stop watching cat videos](https://doi.org/10.1109/INFOCOM.2016.7524426)（INFOCOM 2016）
- [Characterizing radio resource allocation for 3G networks](https://doi.org/10.1145/1879141.1879159)（IMC 2010）
- [A close examination of performance and power characteristics of 4G LTE networks](https://doi.org/10.1145/2307636.2307658)（MobiSys 2012）
- [An in-depth study of LTE](https://doi.org/10.1145/2486001.2486006)（SIGCOMM 2013）
- [Traffic-aware techniques to reduce 3G/LTE wireless energy consumption](https://doi.org/10.1145/2413176.2413198)（CoNEXT 2012）
- [An empirical analysis of the IEEE 802.11 MAC layer handoff process](https://doi.org/10.1145/956981.956990)（CCR 2003）
- [The Cost of the "S" in HTTPS](https://doi.org/10.1145/2674005.2674991)（CoNEXT 2014）
- [An argument for increasing TCP's initial congestion window](https://doi.org/10.1145/1823844.1823848)（CCR 2010）
- [MP-H2: A Client-only Multipath Solution for HTTP/2](https://doi.org/10.1145/3300061.3300131)（MobiCom 2019）
- [Seekable OCI: Lazy-Loading Container Images via Range-Request Indexing](https://arxiv.org/abs/2607.06868)（arXiv 2026）
- [Bounded-Memory Parallel Image Pulling for Large Container Images](https://arxiv.org/abs/2607.05596)（arXiv 2026）
- [A protocol-independent technique for eliminating redundant network traffic](https://doi.org/10.1145/347059.347408)（SIGCOMM 2000）
- [SmartRE: an architecture for coordinated network-wide redundancy elimination](https://doi.org/10.1145/1592568.1592580)（SIGCOMM 2009）
- [Redundancy in network traffic: findings and implications](https://doi.org/10.1145/1555349.1555355)（SIGMETRICS 2009）
- [On Protocol-Independent Data Redundancy Elimination](https://doi.org/10.1109/SURV.2013.052213.00186)（IEEE COMST 2014）
- [On the performance of Redundant Traffic Elimination in WLANs](https://doi.org/10.1109/ICC.2012.6364592)（ICC 2012）
- [ZipTx: Harnessing Partial Packets in 802.11 Networks](https://doi.org/10.1145/1409944.1409984)（MobiCom 2008）
- [Asymmetric caching: improved network deduplication for mobile devices](https://doi.org/10.1145/2348543.2348565)（MobiCom 2012）
- [The effect of packet loss on redundancy elimination in cellular wireless networks](https://doi.org/10.1145/1879141.1879179)（IMC 2010）
- [Redundancy Elimination Might Be Overrated: A Quantitative Study on Real-World Wireless Traffic](https://arxiv.org/abs/1605.04021)（INFOCOM WKSHPS 2017）
- [Is there a case for mobile phone content pre-staging?](https://doi.org/10.1145/2535372.2535414)（CoNEXT 2013）
- [Traffic Redundancy Elimination over a Programmable Data Plane](https://doi.org/10.1109/MNET.011.2100169)（IEEE Network 2021）

### 吞吐/完成时间预测与准入
- [Throughput Prediction Using Machine Learning in LTE and 5G Networks](https://doi.org/10.1109/TMC.2021.3099397)（IEEE TMC 2021）
- [LinkForecast: Cellular Link Bandwidth Prediction in LTE Networks](https://doi.org/10.1109/TMC.2017.2756937)（IEEE TMC 2018）
- [Lumos5G: Mapping and Predicting Commercial mmWave 5G Throughput](https://doi.org/10.1145/3419394.3423629)（IMC 2020）
- [DDA: Cross-Session Throughput Prediction with Applications to Video Bitrate Selection](https://arxiv.org/abs/1505.02056)（arXiv 2015）
- [The tail at scale](https://doi.org/10.1145/2408776.2408794)（CACM 2013）
- [Better never than late: meeting deadlines in datacenter networks](https://doi.org/10.1145/2018436.2018443)（SIGCOMM 2011）
- [Towards providing reliable job completion time predictions using PCS](https://arxiv.org/abs/2401.10354)（arXiv 2024）
- [Conditional Recurrent Neural Networks for Enhancing Throughput Prediction and Slow File Transfers Detection](https://doi.org/10.1109/CCNC54725.2025.10976138)（IEEE CCNC 2025）
- [Impact of Response Latency on User Behaviour in Mobile Web Search](https://doi.org/10.1145/3406522.3446038)（CHIIR 2021）

### 学习增强在线算法（方法论）
- [Competitive Caching with Machine Learned Advice](https://arxiv.org/abs/1802.05399)（ICML 2018 / JACM 2021, DOI:10.1145/3447579）
- [Algorithms with Predictions](https://arxiv.org/abs/2006.09123)（书章 2020 / CACM 2022, DOI:10.1145/3528087）
- [Learning-Augmented Algorithms: Guarantees, Construction Mechanisms, and System-Level Implications](https://arxiv.org/abs/2609.04787)（arXiv 2026 综述）
- [Optimal Robustness-Consistency Trade-offs for Learning-Augmented Online Algorithms](https://arxiv.org/abs/2010.11443)（NeurIPS 2020）
- [Online Metric Algorithms with Untrusted Predictions](https://arxiv.org/abs/2003.02144)（ICML 2020）
- [Learning-Augmented Online Packet Scheduling with Deadlines](https://arxiv.org/abs/2305.07164)（arXiv 2023）
- [Asymptotically Robust Learning-Augmented Algorithms for Preemptive FIFO Buffer Management](https://arxiv.org/abs/2604.26349)（arXiv 2026）
- [A Learning-Augmented Overlay Network](https://arxiv.org/abs/2509.11904)（arXiv 2025）
- [Learning-Assisted Competitive Algorithms for Peak-Aware Energy Scheduling](https://arxiv.org/abs/1911.07972)（arXiv 2019）
- [Online demand peak shaving with machine-learned advice](https://doi.org/10.1049/dgt2.12012)（Digital Twins and Applications 2024）
- [Contract Scheduling with Predictions](https://doi.org/10.1613/jair.1.14117)（JAIR 2023）
- [Learning to Route](https://doi.org/10.1145/3152434.3152441)（HotNets 2017）
- ⚠️ Improving Online Algorithms via ML Predictions（NeurIPS 2018）——仅核到 DBLP key，未取到官方页

### WLAN 管理
- [Fairness and Load Balancing in Wireless LANs Using Association Control](https://doi.org/10.1145/1023720.1023751)（MobiCom 2004）
- [Ending the Anomaly: Achieving Low Latency and Airtime Fairness in WiFi](https://arxiv.org/abs/1703.00064)（USENIX ATC 2017）
- [Channel Load Aware AP / Extender Selection in Home WiFi Networks Using IEEE 802.11k/v](https://arxiv.org/abs/2004.08110)（IEEE Access 2021）
- [Load-aware Channel Selection for 802.11 WLANs with Limited Measurement](https://arxiv.org/abs/1301.2750)（ICT 2016）
- [ML-based Handover Prediction and AP Selection in Cognitive Wi-Fi Networks](https://arxiv.org/abs/2111.13879)（2021）
- [Forecaster-Aided User Association and Load Balancing in Multi-Band Mobile Networks](https://arxiv.org/abs/2301.09294)（IEEE TWC 2023）
- [Multi-Link Operation and Wireless Digital Twin to Support Enhanced Roaming in Next-Gen Wi-Fi](https://arxiv.org/abs/2404.18313)（IEEE WFCS 2024）

---

## 15. 待办 / 下次继续
- [ ] **补一轮不受限流的关键词检索**：换网络环境后重跑 `G2/G3/G5` 相关查询（`aborted download wasted bytes`、`peak-aware bandwidth scheduling`、`resumable transfer measurement`），直连 DBLP + IEEE Xplore。
- [ ] **精读 4 篇必读**：arXiv:2608.30019、arXiv:2601.13838、arXiv:2305.07164、arXiv:1911.07972。
- [ ] **取全文核对数字**：ZipTx 增益、TRE-PRO 性能、EndRE 26%、SmartRE 节省倍率、Halepovic WLAN 数字、Lumos5G / Minovski 精度。
- [ ] **核实厂商宣传语**：华为 iMaster NCE-CampusInsight、Juniper Mist AI 的正确官方页路径。
- [ ] **判断切口**：在 A（峰值感知准入）/ B（重下浪费实测）/ C（AP 侧 RE + 预测）之间选一个，再决定是否立题。
