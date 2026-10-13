# 选题 A：DPDK 用户态 KV Cache 高速传输引擎（KV-DPDK）

> 三件套：初步计划 + 文献调研 + 可行性。创建：2026-09-26。
> 暂定英文标题：*KV-DPDK: A Kernel-Bypass Userspace Transport Engine for KV-Cache Transfer in Disaggregated LLM Serving*

## 一、研究背景与动机

PD（prefill/decode）分离已成为 LLM serving 主流架构（DistServe、Splitwise、Mooncake）。每次请求的 KV Cache 都要从 prefill 节点传到 decode 节点：70B 模型 4K 上下文约 1.3 GB/请求，生产规模聚合带宽超 100 GB/s（[Topology-Aware, arXiv:2607.28633](https://arxiv.org/abs/2607.28633)）。

主流工业方案要么用 **RDMA/RoCE**（需要 InfiniBand/RoCE 网卡 + 无损以太网，贵），要么用**内核 TCP 协议栈**（系统调用、中断、多次拷贝、上下文切换开销大，CPU 占用高）。第三条路——**DPDK 内核旁路（kernel bypass）用户态网络**——在电信/网关领域成熟，但在 LLM serving 的 KV 传输中几乎没有被系统研究。

**核心论点**：在没有 RDMA、只有普通以太网卡的集群/边缘云（这是绝大多数低成本部署的现实），用 DPDK 轮询模式 + 零拷贝把 KV 块直接从 GPU 暂存的 hugepage 送到网卡，可以接近 RDMA 的 CPU 效率，而成本只是普通网卡。

一个极具价值的现成锚点：**DPDK 已内置 MLDEV（Machine Learning Device）库**（[DPDK 官方文档 mldev](https://doc.dpdk.org/guides-25.11/prog_guide/mldev.html)；2022 年 RFC，[mails.dpdk.org](https://mails.dpdk.org/archives/dev/2022-August/247559.html)），允许在 DPDK 轮询线程内统一调度 GPU/NPU 推理设备——为本选题"传输 + 设备协同"提供了官方基础。

## 二、文献调研（均已核实）

### 用户态/内核旁路网络
- **mTCP**（Jeong E., et al., *mTCP: a High-Performance User-Level TCP Stack for Multi-Core Systems*, NSDI 2014）：用户态 TCP，小包吞吐数量级提升——内核旁路在多核上的奠基性证据。
- **DPDK**（Data Plane Development Kit，Intel/开源，[官方文档](https://doc.dpdk.org/)）：PMD（Poll Mode Driver）、hugepage、UIO/VFIO。工程事实标准（无学术论文，引官方文档）。
- **F-Stack / VPP(FD.io)**：基于 DPDK 的用户态完整协议栈（GitHub 开源项目，可作为 TCP 层基座，避免手写）。
- **Andromeda**（Dalton M., et al., OSDI 2018，[USENIX](https://www.usenix.org/conference/nsdi18/presentation/dalton)）：Google 主机侧网络虚拟化，offload 快路径到主机内核——"主机侧快路径"架构范式。
- TU Darmstadt 博士论文（[tuprints](https://tuprints.ulb.tu-darmstadt.de/)）系统比较 kernel-bypass 两大栈（DPDK 类）与内核栈，可作方法学参考。

### LLM KV 传输侧（本课题组已有，作为基线/对比对象）
- Mooncake [arXiv:2407.00079](https://arxiv.org/abs/2407.00079)：Mooncake Transfer Engine，统一多目标传输；**TENT 框架已有 16 个 transport（含 `hp_tcp`：数据中心 TCP 上的高性能 KV 传输，但基于 ASIO 内核 socket、v1 明确不含 GPU 内存）**——既是撞车点也是最佳集成宿主，详见《A-可行性五问答复.md》Q5。
- Topology-Aware [arXiv:2607.28633](https://arxiv.org/abs/2607.28633)：按物理互连选 transport（其"分层传输 + 逐层流水"思路可借鉴；**该文已占位"逐层流水掩盖传输"，我们的逐层调度只能作为工程化增量**）。
- GIGANETS（SIGCOMM 2026，[ACM](https://dl.acm.org/doi/10.1145/3789240.3828738)）：GPU-centric 无状态 serving（ACM DL 403，摘要待核实）。
- ~~Nepco [arXiv:2508.02001]：BF-3 SmartNIC 卸载~~ → **勘误**：该 arXiv 实为 *Versatile yet Efficient Network Traffic Analysis: Offloading Network Foundation Model to SmartNIC*（网络流量分析），与"KV 传输的硬件对照"不符，不应作为本选题的对照文献。
- PrfaaS [arXiv:2604.15039](https://arxiv.org/abs/2604.15039)：**"普通以太网跨 DC 传 KV cache"的动机已被该文占位**（贡献在调度层，数据面仍是内核栈）。
- RTT- or Bandwidth-Bound? [DOI:10.1145/3748273.3749196](https://doi.org/10.1145/3748273.3749196)：已发表"逐块串行传输在高 RTT 下退化"的诊断——离本选题最近的邻居。

**空白结论（2026-09-27 更新）**：*"网络侧内核旁路 + 零拷贝 host-staging→NIC + KV 语义流控"的全栈数据面实现*仍无人占位——arXiv `all:"DPDK" AND all:"LLM"` **0 命中**，vLLM / SGLang / LMCache / NIXL / UCX 代码树 **无 DPDK**，Mooncake 唯一 DPDK 踪迹是由 SPDK 带入的 include 路径。
**但动机与外围已被占位**：PrfaaS 占"普通以太网 + 去 RDMA"，Mooncake `hp_tcp` 占"普通以太网上的 KV 专用传输引擎"，Topology-Aware 占"逐层流水"，NAIC'25 那篇占"块级串行退化诊断"。**因此主张必须收敛到端系统数据面（每字节 CPU 成本与拷贝次数），不能再声称"普通以太网能传 KV"或"逐层流水"作为创新点。**

## 三、研究问题与创新点

1. **零拷贝 KV 快路径**（**未占位，核心**）：GPU 侧 KV 块落入 DPDK hugepage mempool，PMD 直接 DMA 发送，消除内核协议栈的用户态↔内核拷贝与系统调用。**量化口径 = 每 GB 的 CPU 成本与拷贝次数，而非带宽倍数**（核算见《A-可行性五问答复.md》Q2：内核 0.85–4.31 核秒/GB vs DPDK 0.017–0.034 核秒/GB，MTU 1500）。
2. **逐层（layer-by-layer）流水传输**（**已被 Topology-Aware 占位**，只能作为工程化增量）：把 KV 的 layer 边界作为消息调度单位，与 prefill 计算重叠；本选题的增量是"该流水在**轮询模式 NIC** 上的实现与 per-layer 消息调度"（无中断、无系统调用），不是流水本身。
3. **credit-based 流控 + 块级 ACK**（**部分占位**：Mooncake TENT `hp_tcp` 已有持久 lane + per-WRITE ACK）：适配 decode 节点显存动态变化、避免 incast 溢出；差异点是这张信用/优先级表**由 KV 语义驱动**（块重要性、精度、layer 紧迫度），而非纯传输层窗口。
4. **（亮点）MLDEV 协同**（**未占位**）：在同一 DPDK 轮询线程内用 MLDEV 派发 GPU/NPU 任务，实现"传输完成即推理"的事件驱动，无内核等待。注意：MLDEV 是较新的子系统、社区用法很薄，**作为加分项，不做主线依赖**。
5. **DPDK vs 内核 TCP vs RDMA 的成本-性能模型**（普通网卡场景下 DPDK 的 Pareto 位置）。**必须在同一实验中报告 TSO/GSO 开关**——开启 TSO/GSO 时内核每 GB 开销会塌缩到 0.0145–0.0872 核秒/GB，若不注明，全部结论会被推翻。

**实验设计的两条硬约束（来自 Q5 撞车分析）**：① 逐块串行在高 RTT 下退化已被 NAIC'25 诊断，我们不能再把"块级传输机制"当新发现；② 主张必须落在**端系统数据面**，实现以 Mooncake TENT / vLLM `kv_connector` 的新 backend 形式对接（现有 connector：nixl/lmcache/mooncake/moriio/hf3fs/…，**无 DPDK**）。

## 四、技术方案

```
GPU 显存 KV → (cuda memcpy, 映射/注册到 hugepage)
           → DPDK mbuf (零拷贝引用 hugepage 块)
           → PMD TX 轮询发送
对端：PMD RX → 用户态协议处理（F-Stack 提供 TCP，或自定义 L2 轻协议）
           → 按 block 表直接写入 GPU staging → attention 使用
控制面：credit/ACK 走单独可靠通道；MLDEV 派发设备任务
```
- 协议选择：先用 **F-Stack（用户态 FreeBSD TCP）** 保证正确性与互通；再实现自定义轻量协议（L2 + 选择性重传）冲性能，两版都保留对比。
- 规模仿真：单机用 **virtio-user + namespace** 仿真 N 个节点；真实网卡测单机线速与 CPU 占用。

### 集成点（2026-09-27 补齐，依《A-实验环境方案.md》源码级核实）
本选题有**两个现成集成口**，二者共用同一份 DPDK 传输实现：
1. **vLLM 自定义 connector**（`vllm/distributed/kv_transfer/kv_connector/v1/`）：契约即 `KVConnectorBase_V1`（`register_kv_caches` / `save_kv_layer` / `wait_for_layer_load` / `wait_for_save` / `get_transfer_results`），模板可抄 `nixl_connector.py`。**逐层流水无需自研调度器**——`save_kv_layer` 与 `wait_for_layer_load` 本身就是 per-layer 钩子。
2. **Mooncake TENT 新 transport**（`tent/src/transport/dpdk/`）：需实现 `install/uninstall/quiesce`、`allocateSubBatch/freeSubBatch`、`submitTransferTasks`、`getTransferStatus`、`retryTransferTask`、`addMemoryBuffer/removeMemoryBuffer`、`getName`、`getEstimatedBandwidth`、`getNicLoadStats`，并在 5 处登记（类型枚举、名称解析、`transfer_engine.h` 常量、`transport_loader.cpp`、CMake）。**硬约束**：`submitTransferTasks` 必须 all-or-nothing，否则引擎 failover 会重复执行。
> **关键捷径**：Mooncake 的 `transfer_engine_py.cpp` 已有 `MC_USE_TENT` 运行时开关——**只写一个 TENT `dpdk_transport` + 设环境变量，vLLM 与 connector 一行不改**即可让 PD 分离跑在 DPDK 上。这是目前改造面最小的端到端路径。
> **可复用基准**：TENT `tests/` 的 `tcp_transport_test.cpp` / `hp_tcp_transport_test.cpp` / `tcp_datapath_roundtrip_test.cpp`（含 `FakeTransport`）与 LMCache 的 `transfer_channel_benchmark`。注意 `tent/benchmark/` 只有 hip 带宽基准，通用带宽基线需自建。

## 五、初步计划（8 个月）

| 阶段 | 时间 | 内容 | 交付 |
|---|---|---|---|
| P0 | 10 月上 | 环境搭建：DPDK、hugepage、VFIO、F-Stack 跑通 | 两台 VM/主机间 DPDK 收发 demo |
| P1 | 10 月下-11 月 | trace 时序模型 + KV block 消息格式 + credit 流控 | 仿真器（可对比内核 TCP） |
| P2 | 12 月 | 零拷贝 KV 路径（GPU staging hugepage）；真机微基准 | 吞吐/延迟/CPU 每 Gb 数据 |
| P3 | 1-2 月 | 逐层流水 + MLDEV 协同；virtio 多节点仿真 | 端到端原型 |
| P4 | 3 月 | 短期租 RoCE 实例做 RDMA 对照；补端到端数据 | 完整评估表 |
| P5 | 4 月 | 写作投稿 | 论文初稿/投稿 |

## 六、可行性分析

### 条件
- **技能匹配**：C/C++（DPDK 是 C 库）、你熟悉 vLLM KV block 布局；Linux 网络。
- **硬件**：任意普通支持 DPDK 的网卡即可（实验室 PC + 二手 10G 网卡百元级，且不算核心预算）；无 GPU 时 GPU 侧用 trace 时序 + 内存缓冲模拟。
- **资源省钱**：主体真机零成本，仅 P4 阶段租 RoCE 云实例 1-2 周。

### 风险与对策
| 风险 | 等级 | 对策 |
|---|---|---|
| DPDK 轮询占满 CPU 核，节能差 | 中 | 用 interrupt-wait 混合模式（低负载休眠）；论文同时报 CPU 占用与能效 |
| 无 RDMA 时性能上限仍受普通网卡带宽限制 | 中 | 卖点定位为"普通网卡下逼近 RDMA 的 CPU 效率 + 成本优势"，非绝对带宽 |
| F-Stack 与自定义协议工作量大 | 中 | 先 F-Stack 出正确结果保底，自定义协议作为增量 |
| 被质疑"为何不用 RDMA" | 中 | 明确场景：边缘云/普通云租不到 RoCE、跨数据中心 TCP 场景；用成本模型回应 |
| 撞车：**已不是"可能"而是既成事实**（Mooncake TENT `hp_tcp` = 数据中心 TCP 上的 KV 传输引擎，16 个 transport 并存） | **高** | ① 差异化锚在**端系统数据面**（PMD 轮询 + hugepage 零拷贝 + 内核旁路 + GPU staging），不碰"普通以太网能传 KV"这一已被占位的命题；② **把实现做成 TENT 的新 backend**，与 `hp_tcp`/`tcp`/`rdma` 同台对比，把撞车点转成实验优势；③ 逐层流水与块级 ACK 只能作为工程化复用，不作创新点声明 |

### 目标场馆（2022 CCF 分级）
- **CCF-B 会议**：ICDCS、ICPP、Euro-Par、ICCD；**CCF-B 期刊**：Computer Networks、TNSM、ACM TOS、TCC。
- 该题系统 + 实测 + 成本模型完整时，Computer Networks / TCC 最对口。

## 七、参考文献（真实可点击）
- mTCP, NSDI 2014：[USENIX](https://www.usenix.org/conference/nsdi14/technical-sessions/presentation/jeong)
- Andromeda, NSDI 2018：[USENIX](https://www.usenix.org/conference/nsdi18/presentation/dalton)
- DPDK 文档：[doc.dpdk.org](https://doc.dpdk.org/)；MLDEV：[mldev guide](https://doc.dpdk.org/guides-25.11/prog_guide/mldev.html)
- Mooncake：[arXiv:2407.00079](https://arxiv.org/abs/2407.00079)
- Topology-Aware：[arXiv:2607.28633](https://arxiv.org/abs/2607.28633)
- GIGANETS, SIGCOMM 2026：[ACM](https://dl.acm.org/doi/10.1145/3789240.3828738)
- Nepco：[arXiv:2508.02001](https://arxiv.org/abs/2508.02001)
