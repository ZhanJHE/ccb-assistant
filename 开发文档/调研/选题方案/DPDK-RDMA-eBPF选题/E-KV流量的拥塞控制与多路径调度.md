# 选题 E：面向 KV Cache 流量的拥塞控制与多路径调度（KV-CC）

> 三件套：初步计划 + 文献调研 + 可行性。创建：2026-09-26。
> 暂定英文标题：*KV-CC: Block-Semantics-Aware Congestion Control and Multipath Scheduling for KV-Cache Transfer*

## 一、研究背景与动机

分离式 LLM serving 的网络流量形态与传统数据中心负载（搜索/存储/训练）**显著不同**：
- **大消息、突发、incast**：70B 4K 请求 KV 约 1.3 GB（[Topology-Aware](https://arxiv.org/abs/2607.28633)），decode 节点常常同时从多个 prefill 节点取数 → 多打一 incast；
- **时间敏感且有优先级**：即将被 attention 用到的 KV block 更紧急，晚到的 block 直接拖慢该 token；但同一请求内不同 block 紧急程度不同；
- **可分层**：冷 KV/低精度 KV 晚到甚至可降级处理，热 KV 必须准时。

现有数据中心拥塞控制（DCQCN、HPCC、Swift、pFabric/Homa）各自针对通用流量设计，**不理解"KV block 的语义与 DDL（deadline）"**：要么对所有字节一视同仁，要么反应滞后，在 KV incast 下造成缓冲膨胀、热 KV 排队、尾延抖动。

**核心论点**：把 **KV block 的 deadline / 优先级 / 大小**作为显式信息带入拥塞控制与多路径选择，在交换机/网卡/主机侧做"块语义感知"的速率调整与分流，可在 incast 下显著降低 KV 的 p99 尾延，且几乎不牺牲吞吐。

## 二、文献调研（均已核实）

### 数据中心拥塞控制/传输奠基
- **DCQCN**（Zhu Y., et al., *Congestion Control for Large-Scale RDMA Deployments*, SIGCOMM 2015，[DOI:10.1145/2785956.2787484](https://doi.org/10.1145/2785956.2787484)）：RoCE 标配拥塞控制（ECN + 速率）。
- **HPCC**（Li Y., et al., *HPCC: High Precision Congestion Control*, SIGCOMM 2019，[DOI:10.1145/3341302.3342085](https://doi.org/10.1145/3341302.3342085)）：用 INT 精确负载信息快速收敛——本选题"遥测驱动速率"的直接先行。
- **Swift**（Kumar G., et al., *Swift: Delay is Simple and Effective*, SIGCOMM 2020）：端到端 RTT 驱动，区分 fabric/主机延迟。
- **pFabric**（Alizadeh M., et al., SIGCOMM 2013）/ **NDP**（Handley M., et al., SIGCOMM 2017）：极简仲裁 + 流优先级/裁剪，incast 下近理想流完成时间。
- **Homa**（Ousterhout J., *Homa: a Receiver-Driven Low-Latency Transport*, SIGCOMM 2018，[DOI:10.1145/3230543.3230564](https://doi.org/10.1145/3230543.3230564)）：接收端驱动、优先级队列，专为低延迟 incast 设计——与 KV 流量最贴近的传输基线。
- **1RMA**（Singhvi A., et al., *1RMA: Re-envisioning Remote Memory Access for Multi-tenant Datacenters*, SIGCOMM **2020**，[DOI:10.1145/3387514.3405897](https://doi.org/10.1145/3387514.3405897)）：为单边 RDMA 提供硬件支持（相关背景）。**注**：原稿记作 "Mittal R. 等 / SIGCOMM 2016"，经 Crossref + Semantic Scholar 核实为一作 Arjun Singhvi、SIGCOMM 2020，已更正。

### LLM 侧
- **Topology-Aware** [arXiv:2607.28633](https://arxiv.org/abs/2607.28633)：量化 KV 流量（1.3GB、100GB/s 聚合）与 incast 特征。
- **Mooncake** [arXiv:2407.00079](https://arxiv.org/abs/2407.00079)；**DualPath**（SIGCOMM 2026，[ACM](https://dl.acm.org/doi/10.1145/3789240.3829159)）：agentic KV 存储 I/O。
- **CE-CoLLM**（[arXiv:2411.02829](https://arxiv.org/abs/2411.02829)）：指出云边上下文传输是瓶颈（WAN 侧佐证）。
- 导师 **SPRINT（INFOCOM 2026）**：线速 INT，可为本选题提供可靠遥测输入。

**空白结论**：截至 2026-09，**"KV block deadline/语义感知的拥塞控制与多路径"无专门论文**；Homa/pFabric 提供优先级机制但不知 KV block 的真实 DDL，HPCC 有遥测但不按 block 调度。动手前再扫确认。

## 三、研究问题与创新点

1. **block deadline 建模**：根据 decode 调度顺序推导每个 KV block 的"最晚到达时间"（attention 将在第几 token 用到它），作为传输层优先级/截止期；区分热块（硬 DDL）与冷块（软/无 DDL）。
2. **块语义感知速率控制**：借鉴 HPCC，用交换机 INT 负载 + 发送端按 block 优先级分配速率，incast 时优先保热块、冷块降速/缓冲（而非所有流同步退避导致热块受害）。
3. **多路径块级分流（multipath）**：把一个大 KV 消息按 block 拆到多条等价路径，按各路径实时负载（INT）调度，缓解单路径 incast；接收端按 block 重组（你已有 block 表，重组天然支持）。
4. **接收端驱动的块授权（receiver-driven grant）**：借鉴 Homa，decode 节点按自身显存/进度给 prefill 发送 grant，控制超发；grant 粒度=block。
5. 给出与 DCQCN/HPCC/Homa 的解析对比，并在多打一 incast、不同 block DDL 分布下评估 p50/p99/p999。

## 四、技术方案

```
发送端（prefill）：
  为每个 block 标注 {大小, DDL, 精度层级}
  → 按 DDL 排优先级 → 按 INT 负载选路径（多路径分流）
  → 接收 grant 后发送
网络（可选 P4/BFV）：
  → INT 标记队列/负载；按优先级调度/ECN
接收端（decode）：
  → block grant（按显存/进度）→ 收齐按 block 表重组 → 触发 attention
拥塞反应：热块维持速率/抢占，冷块先退避
```
- 实现层次（择机对比）：①纯主机端算法（eBPF/DPDK 钩子，无需改交换机）；②P4 交换机提供 INT/优先级增强。先用主机端闭环保底，网络增强为加分。
- 无真实集群：用 **ns-3 / OMNeT++ 大规模仿真**（incast、拓扑、CC 算法成熟），主机端真实逻辑跑小规模实测——完全契合导师"仿真+真实代码"的被接受路径。

## 五、初步计划（8 个月）

| 阶段 | 时间 | 内容 | 交付 |
|---|---|---|---|
| P0 | 10 月 | 读透 DCQCN/HPCC/Homa；ns-3 复现 incast 基线 | 仿真基线 |
| P1 | 11 月 | trace 推导 block DDL；优先级映射模型 | deadline 模型 |
| P2 | 12 月 | 块语义速率控制 + receiver grant（ns-3 + 主机） | 算法原型 |
| P3 | 1-2 月 | 多路径分流 + INT 负载调度；小规模真实链路 | 端到端原型 |
| P4 | 3 月 | 大规模仿真 + 真机/租云小集群；p99 数据 | 完整评估 |
| P5 | 4 月 | 写作投稿 | 投稿 |

## 六、可行性分析

### 条件
- **成本低**：主体 ns-3/OMNeT++ 仿真（零成本），主机端真实代码用普通 Linux + DPDK/eBPF；真机仅小规模，租云可选。
- **技能匹配**：C++（ns-3）、Python（trace/DDL 推导），你有 KV block 与调度语义基础。
- 最贴**导师主业（拥塞控制 + INT + P4）**，可获最强指导；SPRINT/HPCC 范式清晰。

### 风险与对策
| 风险 | 等级 | 对策 |
|---|---|---|
| DDL 依赖准确的 decode 调度预知，实际难精确 | 中 | 用概率/软 DDL + 在线修正；先在确定性 trace 下验证 |
| 需要交换机支持 INT/优先级才有完整收益 | 中 | 主机端版本（RTT/grant 驱动）先独立成立；P4 增强用实验室 Tofino |
| 与 Homa/HPCC 看似增量 | 中 | 增量明确为"KV 块语义 + DDL"，用 p99/热块延迟数据说话 |
| 仿真真实性被质疑 | 中 | 仿真 + 小规模真机互证（导师论文同款方法），注明参数来源 |
| 多路径乱序/重组开销 | 低 | 块级天然可重组；报告重组 CPU 成本 |

### 目标场馆
- **CCF-B 会议**：CoNEXT、ICNP、IWQoS、ICDCS、ICPP、Euro-Par；**CCF-B 期刊**：Computer Networks、TNSM。
- 强网络/传输味 → CoNEXT/ICNP/IWQoS/Computer Networks 最对口。

## 七、参考文献（真实可点击）
- DCQCN, SIGCOMM 2015：[DOI:10.1145/2785956.2787484](https://doi.org/10.1145/2785956.2787484)
- HPCC, SIGCOMM 2019：[DOI:10.1145/3341302.3342085](https://doi.org/10.1145/3341302.3342085)
- Swift, SIGCOMM 2020：[DOI:10.1145/3387514.3406591](https://doi.org/10.1145/3387514.3406591)（原稿 DOI 属 SIGCOMM'19 论文集前缀，经 Crossref 核实更正）
- pFabric, SIGCOMM 2013：[DOI:10.1145/2486001.2486031](https://doi.org/10.1145/2486001.2486031)（原稿 .2486032 指向 *Expressive privacy control with pseudonyms*，已更正）
- NDP, SIGCOMM 2017：[DOI:10.1145/3098822.3098825](https://doi.org/10.1145/3098822.3098825)（原稿 .3098855 指向 *Detecting Peering Infrastructure Outages in the Wild*，已更正）
- Homa, SIGCOMM 2018：[DOI:10.1145/3230543.3230564](https://doi.org/10.1145/3230543.3230564)（原稿 .3230562 指向 *Trident*，已更正）
- 1RMA, SIGCOMM **2020**：[DOI:10.1145/3387514.3405897](https://doi.org/10.1145/3387514.3405897)（原稿记作 SIGCOMM 2016 / Mittal R.，实为一作 Arjun Singhvi，已更正）
- Topology-Aware：[arXiv:2607.28633](https://arxiv.org/abs/2607.28633)
- Mooncake：[arXiv:2407.00079](https://arxiv.org/abs/2407.00079)
- DualPath, SIGCOMM 2026：[ACM](https://dl.acm.org/doi/10.1145/3789240.3829159)
- CE-CoLLM：[arXiv:2411.02829](https://arxiv.org/abs/2411.02829)
