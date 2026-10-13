# 选题 A 实验环境方案（多套独立方案并列）

> 创建：2026-09-27。配套：《[A-DPDK用户态KV传输引擎.md](A-DPDK用户态KV传输引擎.md)》《[A-可行性五问答复.md](A-可行性五问答复.md)》《[../analysis/选题A-环境核算.md](../analysis/选题A-环境核算.md)》《[../../../参考资料/CCF目录解析/CCF目录核对结果.md](../../../参考资料/CCF目录解析/CCF目录核对结果.md)》。
> 本文**不给出唯一推荐**：下面 5 套方案各自自洽、技术栈不重复，逐套给出 8 个固定字段，最后给横向对照与可组合关系。所有版本/许可来自官方页（本轮实测 HTTP 200）；所有数字有出处或由脚本产出。
> 证据等级沿用《A-可行性五问答复.md》约定：`读到源码` / `官方文档` / `摘要` / `题录`。

## 0. 五套方案速览

| 编号 | 方案 | 集成点 | 传输数据面 | GPU↔主机搬运 | 需要什么硬件 | 改造量 |
|---|---|---|---|---|---|---|
| **S1** | vLLM 自定义 connector | `vllm/.../kv_connector/v1/` 新写 `dpdk_connector` | DPDK PMD（ixgbe/mlx5）+ 自写轻协议或 F-Stack | pinned hugepage staging → `cudaHostRegister` 外部 mbuf | 1 台 Linux + 双口 10G（可自环）；可选 2 台 | 中（要写完整传输栈 + connector） |
| **S2** | **Mooncake TENT 新 backend** | `tent/src/transport/dpdk/` + 设 `MC_USE_TENT=1` | DPDK PMD，复用 TENT 引擎（持久 lane / sub-batch / failover） | 参考 TENT 的 `gds`/`bufio` 与内存注册路径 | 同 S1 | **小**（~9 个虚函数 + 5 处登记，vLLM 零改动） |
| **S3** | AF_XDP 半旁路 | vLLM connector 或独立协议进程 | AF_XDP（`XDP_SKB` copy / `XDP_DRV` zero-copy） | 同 S1 | 任意 Linux + 任意网卡（云 virtio 也可） | 中（协议仍要自己写，但部署最省） |
| **S4** | 纯仿真/参数化 | 无（离线） | 模型化（每包 cycles、投递时延、块大小、RTT） | 不涉及 | 仅需 PC | 小 |
| **S5** | DMA-BUF/VMM 真零拷贝 | 同 S1 | 同 S1 | `cuMemCreate` + `cuMemExportToShareableHandle` + DMA-BUF，网卡直读显存 | **必须数据中心卡**（GeForce 不在官方支持范围） | 大（且可行性未证） |

---

## S1｜vLLM 自定义 DPDK connector 路线

### 1.1 技术栈组合（逐层点名）
| 层 | 选型 | 版本 | 许可 | 官方链接 |
|---|---|---|---|---|
| 服务引擎 | **vLLM** | 0.30.0 | Apache-2.0 | [github](https://github.com/vllm-project/vllm) · [docs](https://docs.vllm.ai/en/latest/) |
| 集成壳 | 自研 `dpdk_connector`，契约类 `KVConnectorBase_V1`（`base.py`），模板 `nixl_connector.py` / `example_connector.py` | 随 vLLM | Apache-2.0 | [目录](https://github.com/vllm-project/vllm/tree/main/vllm/distributed/kv_transfer/kv_connector/v1) |
| 传输数据面 | **DPDK**（PMD：ixgbe / mlx5）+ 自写 L2 轻协议（块级 ACK + 选择性重传） | 26.07.0（2026-07-22）或 LTS **25.11.3** | BSD-3-Clause（核心）/ GPL-2.0（内核组件） | [download](https://core.dpdk.org/download/) |
| 正确性保底 | **F-Stack**（DPDK 上的用户态 TCP/IP） | 1.21.6（以 tag 固定，`VERSION` 文件为占位值） | BSD-2-Clause | [github](https://github.com/F-Stack/f-stack) |
| GPU↔主机 | `cudaHostAlloc` / `cudaHostRegister` 注册 DPDK hugepage + `cudaMemcpyAsync` | CUDA Runtime **13.4** | NVIDIA 专有 | [CUDART Memory](https://docs.nvidia.com/cuda/cuda-runtime-api/cuda_runtime_api/group__CUDART__MEMORY.html) |
| 负载生成 | 合成 KV buffer（memcpy，带宽受限）+ Qwen2.5-1.5B 真机 | 模型 Apache-2.0（除 3B/72B） | — | [Qwen2.5 博客](https://qwenlm.github.io/blog/qwen2.5/) · [Qwen2.5-1.5B](https://huggingface.co/Qwen/Qwen2.5-1.5B) |
| 测量 | `dpdk-testpmd`、`pktgen-dpdk`、`iperf3`、vLLM `benchmarks/benchmark_serving.py`、CUDA event | testpmd 随 DPDK；pktgen-26.02.3；iperf3 3.21 | BSD-3 | [testpmd](https://doc.dpdk.org/guides/testpmd_app_ug/) · [pktgen](https://github.com/pktgen/Pktgen-DPDK) · [iperf](https://github.com/esnet/iperf) |

### 1.2 拓扑
```
[prefill 进程：vLLM + dpdk_connector]                      [decode 进程：vLLM + dpdk_connector]
   KV tensor (GPU) → pinned hugepage staging (CPU)            DPDK RX → staging → KV tensor (GPU)
        │ cudaMemcpyAsync                                          ▲
        ▼                                                          │
   DPDK mbuf（外部 buffer 引用同一 hugepage）── PMD TX ──10GbE──► PMD RX
   控制面：credit / 块级 ACK 走独立通道（或 F-Stack）
```
- 单机形态：一张双口 10G 卡（如 X520-DA2，二手 100–300 元）+ DAC 自环，两个进程分属两个 network namespace，互不干扰内核栈；
- 双机形态：把上述两个进程分到两台机器，链路拓扑不变。

### 1.3 模型与算力
- **合成 KV 是主线**：核算见 `../analysis/选题A-环境核算.md` §3/§4——单张消费级 GPU 在任何模型规模下都喂不满 10 GbE（如 Qwen2.5-1.5B 需 43,597 tok/s，对应 134 TFLOPS prefill；Llama-2-7B 因 MHA 32 个 KV 头也需 31.9 TFLOPS）。满线速实验必须用合成 KV 流（打满 10 GbE 只需 4,768 块/s @256 KB，纯 memcpy 即单核可达）。
- **真实模型闭环**：Qwen2.5-1.5B（28 KB/token，4K prefill 一次产出 **0.117 GB**）可放本地 RTX 4060（8 GB）；覆盖"KV 真从 A 传到 B 并被 decode 用上"的正确性，报亚线速 TTFT。
- **租用**：2 台实例 × 40 卡时 ≈ 120–400 元（1.5–2.5 元/卡时敏感度见核算文件 §5）。**注意**：普通 virtio 实例做不了 DPDK，必须裸金属或支持 SR-IOV/vfio 的实例。

### 1.4 能产出的数据
传输微基准（吞吐、每 GB CPU、投递时延、p99、incast 尾延）、connector 正确性与逐层流水时间线、小模型端到端 TTFT/TPOT、与内核 TCP/F-Stack 的正面对比。

### 1.5 产不出的数据（诚实列出）
大模型（70B 级）真实 t/s 与生产级并发 goodput；GPUDirect 类"网卡直读显存"的零拷贝结论（GeForce 不受支持）。

### 1.6 优点 / 缺点（并列）
**优点**：① 走官方插件接口，契约固定（`register_kv_caches` / `save_kv_layer` / `wait_for_layer_load` / `wait_for_save` / `get_transfer_results`），改动边界清楚；② 源码可直接开源，别人能复现（Q4 硬条件之一）；③ 逐层流水无需自研调度器——vLLM 本身就有 per-layer 钩子；④ 与 vLLM 生态对齐，论文叙事直白。
**缺点**：① 只覆盖 vLLM 一家，对生产栈（Mooncake/NIXL）的说服力需另做适配；② 传输栈（协议/重传/流控）要自己写，工程量最大；③ connector 抽象层带来额外开销，需在论文里剥离；④ vLLM 版本演进快（0.30.0 的 v1 connector 仍在变动），需锁版本。

### 1.7 适配的论文叙事
"首个面向 KV 传输的 DPDK connector"：端到端 TTFT/goodput + 每 GB CPU 成本 + incast 尾延，与内核 TCP/F-Stack/RDMA 三方同图。

### 1.8 主要风险与失效条件
绑 `vfio-pci` 会把网卡从内核摘走（用板载口做 SSH，别把自己关在门外）；轮询线程 100% 占核（改 interrupt-wait 混合模式）；**内核开 TSO/GSO 时收益塌缩**（核算文件 §6 的失效条件），必须在论文中报告该开关。

---

## S2｜Mooncake TENT 新 backend 路线（改造面最小，vLLM 零改动）

### 2.1 技术栈组合
| 层 | 选型 | 版本 | 许可 | 证据 |
|---|---|---|---|---|
| 传输引擎 | **Mooncake TENT**（`mooncake-transfer-engine/tent/`），已有 16 个 transport（hp_tcp / tcp / rdma / nvlink / shm / gds / io_uring / sunrise_link / ub / tpu / xpu / ascend / mnnvl / bufio / mpcomm…） | Mooncake 0.3.13.post1 | Apache-2.0 | 读到源码 |
| 新增后端 | `tent/src/transport/dpdk/`（+ `include/tent/transport/dpdk/`） | — | 随仓库 | 读到源码 |
| 抽象基类 | `tent/include/tent/runtime/transport.h` 的 `class Transport`；类型枚举 `tent/include/tent/common/types.h:46`；注册点 `tent/src/runtime/transport_loader.cpp:64 loadTransports()` | — | — | 读到源码 |
| vLLM 侧 | **零改动**：`transfer_engine_py.cpp:1367` 已有 `MC_USE_TENT` / `MC_USE_TEV1` 运行时开关，把同一个 `mooncake.engine.TransferEngine` Python API 转发给 TENT | — | — | 读到源码 |
| 对照基线 | 同仓库 `hp_tcp`（ASIO 内核 socket）、`tcp`、`rdma` 三条现成后端 | — | — | 读到源码 |

### 2.2 拓扑
与 S1 相同的双端拓扑，但两端跑 **Mooncake TransferEngine**：`vLLM(mooncake connector) → mooncake.engine.TransferEngine → TENT → dpdk_transport → PMD`。可用 `MC_USE_TENT=1` + `transports/dpdk/enable=true` 切换，不改 vLLM 与 connector 代码。

### 2.3 模型与算力
与 S1 完全一致（合成 KV 打满链路 + Qwen2.5-1.5B 真机闭环 + 可选 2 节点短租）。额外收益：TENT 自带的 `tests/` 里有现成往返测试（`tcp_transport_test.cpp`、`hp_tcp_transport_test.cpp`、`tcp_datapath_roundtrip_test.cpp`，含 `FakeTransport`），可直接改造成 DPDK 后端的对齐基准。

### 2.4 能产出的数据
与 S1 相同的传输指标，**外加**：与 `hp_tcp`/`tcp`/`rdma` 三条生产级后端的**同台对比**（这是本方案独有的）；TENT 引擎层面的 `getEstimatedBandwidth`、`getNicLoadStats`、sub-batch 调度与 failover 行为。

### 2.5 产不出的数据
与 S1 相同（无大模型真实 t/s）；另外 `hp_tcp` **v1 明确不含 GPU 内存**，因此"GPU 显存直通"这条仍要自己在 TENT 的内存注册路径里实现或论证。

### 2.6 优点 / 缺点（并列）
**优点**：① **改造面最小**——需实现的虚函数集合明确（`install/uninstall/quiesce`、`allocateSubBatch/freeSubBatch`、`submitTransferTasks`、`getTransferStatus`、`retryTransferTask`、`addMemoryBuffer/removeMemoryBuffer`、`getName`、`getEstimatedBandwidth`、`getNicLoadStats`），登记点仅 5 处（`types.h` 枚举、`transportTypeName/parseTransportType`、`transfer_engine.h` 常量、`transport_loader.cpp`、`CMakeLists.txt`）；② vLLM 一行不改，端到端链路天然打通；③ 撞车点（`hp_tcp`）直接变成实验优势——同台对比；④ 引擎已处理持久 lane / sub-batch / failover，可专注于数据面本身。
**缺点**：① 要读懂 C++ 引擎与 `submitTransferTasks` 的 **all-or-nothing 契约**（`transport.h:98-106` 明写：出错不得投递任何请求、不得留部分状态，否则 failover 会重复执行）；② TENT 是较新的子系统，文档与社区用法都薄；③ 需要 fork 上游并承担同步成本；④ `tent/benchmark/` 只有 `hip_bandwidth_bench.cpp`，**没有通用带宽基准**，得自建或用 vLLM 侧指标。

### 2.7 适配的论文叙事
"把 DPDK 做进生产级 KV 传输引擎，与 TCP/RDMA 后端同台对比"——系统论文味道最正，也最贴合工业界关心的"普通网卡部署"。可主张的增量：端系统数据面的每字节 CPU 成本与拷贝次数，而非"普通以太网能传 KV"（后者已被占位）。

### 2.8 主要风险与失效条件
与 S1 相同的 TSO/GSO 失效条件；额外风险是**上游变动**（`MC_USE_TENT` 属新路径，行为可能调整）与 **TENT 内存注册语义**（GPU staging 需自己接）；若 `MC_USE_TENT` 路径在实测中不稳定，退化为"S2 的 dpdk_transport 挂到 vLLM 的 mooncake connector"（即与 S1 合流）。

---

## S3｜AF_XDP 半旁路路线（门槛最低、最易复现）

### 3.1 技术栈组合
| 层 | 选型 | 版本 | 许可 | 官方链接 |
|---|---|---|---|---|
| 传输数据面 | **AF_XDP**：`XDP_SKB`（generic，copy，任意网卡）/ `XDP_DRV`（native，zero-copy，需驱动支持；`XDP_ZEROCOPY` 可强制失败探测） | 随内核（文档见 7.3.0-rc4） | GPL-2.0（内核） | [af_xdp](https://docs.kernel.org/networking/af_xdp.html) |
| 程序加载 | **libbpf** | v1.7.0 | LGPL-2.1-only / BSD-2-Clause | [github](https://github.com/libbpf/libbpf) |
| 集成壳 | vLLM 自定义 connector（同 S1），或独立用户态协议进程 | — | — | 同 S1 |
| GPU↔主机 | 同 S1（pinned hugepage + `cudaMemcpyAsync`） | — | — | — |
| 对照 | 内核 TCP（`iperf3`）与 S1/S2 的 DPDK 结果 | — | — | — |

### 3.2 拓扑
同 S1，但无需 `vfio-pci` 绑定、无需 hugepage/专用 PMD：**任意 Linux + 任意网卡**即可，云上 virtio 实例也能跑通（这是本方案最大的可取之处）。零拷贝成色取决于网卡驱动是否支持 native XDP。

### 3.3 模型与算力
同 S1/S2。由于不需要租裸金属实例，端到端实验可以直接用**普通云实例**完成，成本最低。

### 3.4 能产出的数据
传输吞吐/CPU/尾延（AF_XDP 两种模式下分别测）、connector 正确性、小模型端到端 TTFT、与内核 TCP 的对比。**特别有价值**：AF_XDP 与 DPDK 在同一硬件上的三方对照（内核栈 / AF_XDP / DPDK），是文献里少见的"旁路程度 × 收益"消融。

### 3.5 产不出的数据
不能声称"内核旁路"的完整收益：AF_XDP 仍在内核网络栈内 attach，`XDP_SKB` 模式还要 copy；`XDP_DRV` 语义好但仍受驱动实现影响。

### 3.6 优点 / 缺点（并列）
**优点**：① 部署门槛最低（不绑驱动、不配 hugepage，不怕把网卡摘走失联）；② 云实例可复现，端到端实验成本最低；③ generic/zero-copy 两种模式天然构成"旁路纯度"的消融实验；④ 内核文档明确支持，官方措辞可引。
**缺点**：① **"内核旁路"纯度不足**，与选题名（kernel-bypass）存在张力，审稿人易质疑；② AF_XDP 的收益需自己实测，不能直接引用 DPDK 的每包 cycles 数字；③ 无 DPDK 的 PMD 生态（无 `testpmd`/`pktgen` 现成工具，测试台要自建）；④ 若 Kernel 网络栈仍参与（SKB 模式），论文的"移除协议栈开销"主张会被削弱。

### 3.7 适配的论文叙事
适合作**对照与消融**章节（"旁路程度 vs 收益"），而不是主线；也可作为"低门槛复现版本"降低别人的复现门槛。

### 3.8 主要风险与失效条件
驱动不支持 native XDP 时只能 copy 模式，收益大幅缩水；若最终结论是"AF_XDP ≈ DPDK"，反而会削弱 DPDK 的卖点——这也是一个有价值但需要预先想好怎么叙述的结果。

---

## S4｜纯仿真/参数化路线（零硬件，扫参最快）

### 4.1 技术栈组合
| 层 | 选型 | 版本 | 许可 | 说明 |
|---|---|---|---|---|
| 网络仿真 | **ns-3** | 3.48 | GPL-2.0（官方许可页未抓，**待核实**） | 带宽/RTT/incast 参数扫描 |
| 拓扑与低门槛验证 | **Mininet** | 2.3.0 | BSD-3-Clause | 需要在真实协议栈上跑逻辑时用 |
| 参数来源 | DPDK 实测：每包 61 cycles @2.4 GHz、投递时延 0.47 µs、p99.99 5.8 µs；内核栈 950 ns/包、4.3–5.0 µs | — | — | 见《A-可行性五问答复.md》Q2 |
| 负载时序 | 工作区已有 vLLM trace（317K 事件）重放 | — | — | 复用已有能力 |

### 4.2 拓扑
无物理链路；在仿真器里构造 1 P → N D 的 PD 分离拓扑，参数化（带宽 1/10/25/100 GbE、RTT 0.05–50 ms、incast 度 1–16、块大小 64 KB–1 MB）。

### 4.3 模型与算力
不需要 GPU。KV 体量与到达过程由 trace 与核算脚本给出。

### 4.4 能产出的数据
多参数扫描下的传输完成时间、尾延分布、incast 最坏情形、解析模型拟合（与《A-可行性五问答复.md》的 p×s 推导互证）。**先于硬件出结论**，用于决定真机实验的参数点。

### 4.5 产不出的数据
一切真机数据：无实测吞吐/CPU/尾延，无法满足 Q4 硬条件 1（与内核 TCP 真机正面对比）。

### 4.6 优点 / 缺点（并列）
**优点**：① 零成本、零硬件门槛；② 扫参速度最快，适合做敏感性分析与解析模型；③ 可作为真机方案的"预测—验证"闭环，先标定再上机。
**缺点**：① 外部效度弱，同档期刊的仿真论文多用第三方标准仿真器（CoInfer 用 SUMO、TORTA 用真实电价/拓扑数据），自研小仿真易被质疑；② 不能独立构成一篇该档论文（须与真机工作合并）；③ 参数取自他人实测，存在"套用数字"的方法论风险，需明确标注。

### 4.7 适配的论文叙事
作为 S1/S2 的配套章节："解析模型 + 参数扫描 + 真机验证"三段式，这与导师组偏好的"仿真 + 真实代码"路径一致。

### 4.8 主要风险与失效条件
若仿真与真机结论背离（尤其 TSO/GSO 开关带来的差异），需回头修正模型；不能把仿真结论当作实测结论陈述。

---

## S5｜DMA-BUF / VMM 真零拷贝路线（最激进，需数据中心卡）

### 5.1 技术栈组合
| 层 | 选型 | 版本 | 许可 | 官方链接 |
|---|---|---|---|---|
| 显存分配/导出 | `cuMemCreate` + `cuMemExportToShareableHandle`（CUDA Driver VMM API） | CUDA 13.4 | NVIDIA 专有 | [CUDA VA API](https://docs.nvidia.com/cuda/cuda-driver-api/cuda_driver_api/group__CUDA__VA.html) |
| 跨设备共享 | **DMA-BUF**（Linux 内核导出/导入同一 buffer） | 随内核 | GPL-2.0 | [dma-buf](https://docs.kernel.org/driver-api/dma-buf.html) |
| 低延迟映射拷贝（可选） | **GDRCopy** | v2.6 | MIT | [github](https://github.com/NVIDIA/gdrcopy) |
| RDMA 对照（可选） | `nvidia-peermem` + **perftest** / **UCX** | perftest 26.04.17；UCX 1.22.0 | 双许可 / BSD-3 | [perftest](https://github.com/linux-rdma/perftest) · [UCX](https://github.com/openucx/ucx) |
| 传输数据面 | DPDK（需自行验证 dmabuf 注册路径的可用性——**本轮未证实 DPDK 官方支持 dmabuf 注册**） | — | — | — |

### 5.2 拓扑
prefill 端显存 buffer 直接导出 → 网卡 DMA 读显存 → decode 端写入显存，**完全去掉主机 staging**。控制面与 S1 相同。

### 5.3 模型与算力
**必须租数据中心卡**（A100 / L40S 级）。依据（官方原文）：GPUDirect RDMA 文档写 "available on both Tesla and Quadro GPUs"，开发者页写 "NVIDIA data center GPUs"；**全文检索 "GeForce" 命中 0 次**，故 RTX 40 系不在支持范围。另有硬约束：IOMMU 需关闭或 1:1 直通、POWER8 不支持、ARM64 无保证、需 ConnectX-3 VPI 及以上 HCA。

### 5.4 能产出的数据
"真零拷贝"上界数据：显存→网卡直读的吞吐/延迟，与 staging 方案的差异；可回答"staging 拷贝到底占多少"这一 S1/S2 无法回答的问题。

### 5.5 产不出的数据
消费级硬件上的可行性结论（不能外推）；若 DPDK 的 dmabuf 支持不成立，则本方案在 DPDK 路径上**根本做不出来**（只能退回 RDMA/GPUDirect 路径，那就偏离选题了）。

### 5.6 优点 / 缺点（并列）
**优点**：① 卖点最强——直接消除 staging 拷贝，与"端系统数据面成本"的主张最契合；② 可作为 S1/S2 的性能上界参照，论文里的"我们离上界有多远"很有说服力。
**缺点**：① 硬件门槛高（须租数据中心卡 + 支持 P2P 的 NIC/主板）；② 驱动/IOMMU 约束多，环境搭建失败风险最高；③ **DPDK 侧的 dmabuf 支持未经验证**，是本方案最大的未知数；④ 即使成功，也无法在 GeForce 上复现，削弱"低成本"叙事。

### 5.7 适配的论文叙事
作为 S1/S2 的"上界探索"或 future work；不宜作为唯一主线。

### 5.8 主要风险与失效条件
任一环节（IOMMU、HCA 型号、DPDK dmabuf）不成立则整条路线失败；建议先做**两周可行性探针**（只验"显存 buffer 能否被网卡 DMA 读到"），再决定是否投入。

---

## 6. 横向对照表

| 维度 | S1 vLLM connector | S2 TENT backend | S3 AF_XDP | S4 纯仿真 | S5 DMA-BUF |
|---|---|---|---|---|---|
| 真机纯度 | 高（全栈真机） | 高（全栈真机，且是生产引擎） | 中（仍在内核网络栈内） | 无 | 最高（但需数据中心卡） |
| 数据完整度 | 高（微基准+端到端） | **高（含与 hp_tcp/tcp/rdma 同台对比）** | 中高（三方可对照） | 低（仅模型） | 中（只覆盖上界） |
| 复现成本 | 中（1 台 Linux + 双口 10G） | 中（同 S1） | **最低（任意 Linux/云实例）** | 零 | 高（租数据中心卡） |
| 上手风险 | 中（要写完整传输栈） | **低（改造面最小、契约明确）** | 低 | 低 | **高（未知数最多）** |
| 与生产栈距离 | 中（只进 vLLM 生态） | **最近（Mooncake 上游）** | 中 | 远 | 中 |
| 与撞车文献可比性 | 中（可与 SmartGen/PDD 对齐口径） | **高（直接对标 hp_tcp，且 Mooncake 是工业标杆）** | 中 | 低 | 低 |
| 上限 | 中高 | 高 | 中 | 低（不独立成文） | 最高 |
| 最大失效条件 | 内核 TSO/GSO 开启→收益塌缩 | 上游 `MC_USE_TENT` 路径变动 | 驱动不支持 native XDP | 仿真不被采信 | IOMMU/HCA/DPDK dmabuf 任一不成立 |

> 说明：本表用**定性描述**而非打分；每格的依据见各方案对应小节。

## 7. 可组合关系（不指定唯一推荐）

1. **S4 → S1/S2**：先用仿真扫参确定"哪一档带宽/RTT/块大小收益最显著"，再上真机验证同一组参数（预测—验证闭环）。
2. **S1 与 S2 共享传输实现**：同一个 DPDK 传输数据面（mbuf/外部 buffer/信用与 ACK 设计）可分别挂在 S1 的 connector 壳与 S2 的 TENT backend 上；两者是"同一引擎、两个集成口"，不是两套工程。
3. **S3 作为 S2 的低门槛对照**：AF_XDP 与 DPDK 在同一硬件上对比，给出"旁路程度 × 收益"消融。
4. **S5 作为 S1/S2 的上界**：回答"staging 拷贝占多少成本"——S1/S2 无法回答的问题。
5. **三条成本—叙事路线**（择一或组合，由你决定）：
   - **最低成本**：S4 + S3（零租卡，任意 Linux 或云实例即可完成端到端）；
   - **最平衡**：S4 + S2 + 短租 2 节点端到端（约 120–400 元）；
   - **最强叙事**：S2（主线，同台对比 hp_tcp/rdma）+ S1（connector 侧的第二集成点）+ S4（参数扫描）+ 可选 S5 上界。

## 8. 模型、算力与提升空间（脚本产出，摘要）

- **KV 体量（实取 config.json）**：Qwen2.5-0.5B 12 KB/token、1.5B 28 KB、7B 56 KB、32B 256 KB、Llama-3.1-8B 128 KB、Llama-2-7B **512 KB**（MHA 32 头）。4K 上下文 FP16 总量：1.5B 0.117 GB、7B 0.235 GB、32B 1.074 GB、Llama-2-7B 2.147 GB（70B 的 1.3 GB 量级见《A-可行性五问答复.md》）。
- **关键约束**：打满 10 GbE 需要 Qwen2.5-1.5B 43,597 tok/s（≈134 TFLOPS）或 Llama-2-7B 2,384 tok/s（≈31.9 TFLOPS）→ **单卡消费级 GPU 喂不满链路，满线速必须用合成 KV 流**。
- **成本**：2 实例 × 40 卡时 ≈ 120–400 元（1.5–2.5 元/卡时，**单价待核实**）。
- **提升空间**：传输微基准层面每 GB CPU 成本降 25–250×、打满 100 GbE 所需核数降 19–222×、投递时延降 9–11×、p99.99 降 13×；端到端层面按 `改善 ≈ p × s` 估 **2%–21%**（p∈[0.2,0.42]、s∈[0.1,0.5]）；**失效条件**：链路充裕且内核启用 TSO/GSO 时收益趋近 0。

## 9. 场馆分级（依官方目录核对，投稿定位用）

来源：《第七版中国计算机学会推荐国际学术会议和期刊目录（正式版）》（原件见 `../../../参考资料/CCF推荐目录第七版.pdf`），解析结果见 `../../../参考资料/CCF目录解析/CCF目录核对结果.md`。

| 档次 | 可用于本选题的期刊 | 可用于本选题的会议 |
|---|---|---|
| A | TOS、TACO、TC、TCAD、TPDS、ToN、TMC、JSAC | INFOCOM/SIGCOMM/NSDI/MobiCom、ISCA/MICRO/HPCA/ASPLOS、OSDI/SOSP、FAST、SC、HPDC、DAC |
| **B** | **IEEE TCC、JPDC、Computer Networks** | **ICDCS、ICPP、Euro-Par、MSST、SoCC、CLUSTER、CoNEXT、ICNP、IWQoS、IMC、SenSys、MobiSys、FPGA、ICCD、ICCAD、DATE、Middleware** |
| C | TNSM、Computer Communications、Ad Hoc Networks、JNCA、MONET、WCMC | FCCM、FPL、FPT、ASP-DAC、CCGRID、NPC、SYSTOR、SEC、ICPADS、MobiQuitous |

> **重要更正**：本工作区此前多份文档把 **TOS/TACO 当作 CCF-B**（实为 A 类）、把 **TNSM 当作 CCF-B**（实为 C 类）、把 **HPDC 当作 B 类**（实为 A 类），并列出**未收录**的 TVT。已在 `文献索引.md`、`毕设选题建议.md`、`在网计算与LLM serving调研.md`、`KV-cache两篇调研`、`边缘端侧LLM调研.md`、`毕设研究全景.html` 就地更正。

## 10. 本轮已核实 / 仍缺

**已核实（附证据强度）**：vLLM connector 契约（读到源码）；Mooncake 16 个 transport 与 `hp_tcp` 设计文档、`MC_USE_TENT` 开关（读到源码）；7 个系统的替换点（读到源码，其中 KVDirect/DistServe 只有调用点）；32 项技术组件的版本与许可（官方页 HTTP 200）；GeForce 不支持 GPUDirect 的官方措辞（原文引用）；AF_XDP 两种模式（内核文档原文）；模型配置（HF config.json 实取）；CCF 分级（官方 PDF 解析）。

**仍缺**：① FlowKV / SGLang transfer engine / Dynamo 的非 NIXL 部分未查；② DPDK 是否支持 dmabuf 注册（S5 的关键未知数）；③ ns-3 许可页未抓；④ `pktgen-dpdk`/perftest/UCX 的 SPDX 未取；⑤ HuggingFace 主站不可达（本轮经 hf-mirror.com 取数）。

## 11. 算力平台的硬约束：AutoDL 能否承载 S2 的数据面（2026-09-27 核查）

**结论：AutoDL 的常规容器实例无法承载 DPDK 数据面，属结构性限制，不是配置问题。**

官方文档依据（`api.autodl.com/docs/`、`autodl.com/docs/`）：
- 实例形态："容器实例是使用 **Docker** 技术进行资源划分与隔离的 Container"；"**容器实例内不支持使用 Docker，如需使用 Docker 请联系客服租用裸金属服务器（整机包月起租）**"（`docs/env/`）。
- 网络：同地区实例**共享带宽**（一个地区约 3~10 Gbps，上下行相等，不单独计费）；**"不再支持开通内网 IP 进行多机多卡并行"**（`docs/network/`、`docs/distributed_training/`）→ **默认拿不到"第二个 DPDK 端点"**。
- CPU/内存按 GPU 数量**成比例**分配（如 32GB/GPU、8 核/GPU）；**无卡模式仅 0.5 核 + 2GB 内存**（0.1 元/小时；私有云文档称该配额"即将支持可自定义"）。
- CPU 型号（按区域）：北京 A 区 H20 用 AMD EPYC 9K84；北京 B 区 4090 用 Xeon Gold 6430；内蒙 A 区 A100 用 EPYC 7763；重庆 A 区 4090D 用 Xeon Platinum 8474C；西北 B 区 4090/4090D 用 EPYC 9654/9754；L20 专区用 Xeon Platinum 8457C。

技术前提对照（DPDK 26.07 官方文档 + 容器实践）：DPDK 需要 ①预定 hugepage（`/sys/kernel/mm/hugepages/.../nr_hugepages` 或内核启动参数）；②加载 `vfio-pci`/`uio` 内核模块；③把物理 NIC 从内核驱动 unbind 并 bind 到 `vfio-pci`；④容器需 `--privileged` 或 `--cap-add SYS_ADMIN/SYS_RAWIO/IPC_LOCK` + `--device=/dev/vfio/...` + 挂载 `/dev/hugepages` + `memlock=-1`。
- 社区实测记录（CSDN 文库，2025-06，**权威性一般、建议自行复核**）：AutoDL 容器 `CapEff = 00000000a80425fb`（特权模式为 `0000003fffffffff`），**缺 `CAP_SYS_ADMIN`、`CAP_NET_RAW`、`CAP_SYS_MODULE`** → 无法 `modprobe`、无法改 sysctl/挂 hugetlbfs、无法 raw socket。
- 结论：**四个前提在 AutoDL 常规实例上全部不满足**；因此既没有可绑定的物理网卡，也没有第二个可互联的端点，更没有独占轮询核的调度保证（共享 vCPU 上跑轮询，每包成本数据无意义）。

**AutoDL 仍然可做的部分（用于 S2 的"控制侧/模型侧"）**：
1. 标定有效 prefill 算力 `F`（跑 prefill 微基准）→ 让《选题A-选型核算.md》里的 `p` 从区间变成可预测值；
2. 量 KV 几何与真实到达（ShareGPT/LMSYS 重放）、产出 trace；
3. vLLM 端到端亚线速 TTFT/TPOT（真实模型侧的唯一可靠云上数据）；
4. 纯 Python 侧逻辑验证：vLLM `KVConnectorBase_V1` 契约、TENT 的接口语义（用 `FakeTransport`）。
**不能做的**：任何 DPDK/内核旁路的数据面性能实验；任何"两节点 KV 传输"实验（无内网互通）。

**替代路线**：① 本地 Linux 机器 + 二手双口 10G 卡自环（S2 数据面主体，成本 100–300 元）；② 需要云上双节点时，改用**支持 SR-IOV/裸金属**的实例（AutoDL 亦提供裸金属但按月起租），须先确认 PCI 直通与实例间内网可达；③ 同一实例内的 `net_ring`/`net_tap` 只能验证代码路径正确性，**不可用于性能结论**。

## 12. 哪些云平台能做 DPDK、多少钱（2026-09-27 核查）

| 平台 | 能否 DPDK | 依据（官方） | 计费粒度 | 价格量级 | 结论 |
|---|---|---|---|---|---|
| **阿里云 ECS（六代 g6/c6/r6 及以后，含通用算力型 u1）** | **能，普通实例即可** | 《使用 VFIO 驱动替代 UIO 驱动》明写"在**普通云服务器和弹性裸金属服务器**中使用 VFIO 替代 UIO，解决 DPDK 应用运行异常"；给出 设 HugePages → GRUB 加 `intel_iommu=on`（删 `iommu=pt`）→ 重启 → `modprobe vfio vfio-pci` → `enable_unsafe_noiommu_mode` → `ethtool -i` 取 bus-info → `dpdk-devbind.py -b vfio-pci` → testpmd 全流程 | 按量付费（按秒计费、整点结算）/ 抢占式 | 8核16G：`e-c1m2.2xlarge` ≈0.9 元/时、`u1-c1m2.2xlarge` ≈1.40 元/时、`c9i.2xlarge` ≈1.55 元/时；8核32G ≈1.95 元/时（第三方整理的目录价，**以 ECS 价格计算器为准**） | **首选**：两节点同 VPC 内网互通，几十元即可跑完一轮 |
| **阿里云 eRDMA/ERI 实例（c8i/c9i/c8a…、弹性裸金属 ebmg8i/8y/9a、HPC hpc9a 等）** | 能，且**额外带 RDMA** | 《在企业级实例上启用 eRDMA》：给出支持规格族清单；两实例可在 **VPC 内**做 eRDMA 互联（中间不能跨 SLB 等网元）；`hpc9a` 提供 **200 Gbps eRDMA** | 同 ECS | 与同规格 ECS 同价 | **RDMA 基线对照的最省事路径**（不需要额外网卡） |
| **腾讯云裸金属云服务器（原黑石）** | 能（整机物理机，支持嵌套虚拟化） | 官方公告：裸金属多实例类型**已开放按量计费**（按秒计费、按小时结算，单价为包年包月的 1–1.4 倍） | 按量 | 标准型 BMS4 ≈12,884 元/月 → 按量折算 **≈17–24 元/时**（**本文推算**） | 要"真物理网卡数据"时用，成本高 |
| **华为云 BMS** | 技术上能，但**只能包年包月** | 官方计费说明多处一致："裸金属服务器计费模式为包年包月付费，**不支持按量付费**" | 包年包月 | 月付数千元起 | **排除**（学生短期实验不可行） |
| **Azure（国际站）Linux VM + Accelerated Networking** | 能，官方有专门文档 | 《DPDK in an Azure Linux VM》：**所有 region 支持**；前提是 VM 启用 **Accelerated Networking（SR-IOV）**，VF 以 PCI 设备出现（mlx4/mlx5/MANA），至少两张网卡（一张管理）；MANA 需 **Linux 内核 ≥6.14** | 按秒 | 按 VM 规格 | 有境外账号/结算时的替代 |

**三条比价格更重要的警告（写进论文必须知道）**
1. **云上的"网卡"是 SR-IOV 虚拟功能，不是物理网卡**：阿里云文档中的 bus-info 形如 `0000:00:06.0`（virtio/神龙 VF），且要求打开 `vfio enable_unsafe_noiommu_mode`。→ **每包 cycles 这类微基准在云上测出的数字不能冒充物理网卡结果**；建议微基准放在本机物理网卡，云上只做两节点端到端与对照组。
2. **宿主机维护会让 VF 消失/重现**（Azure 文档明确提到，阿里云/腾讯云同理），DPDK 应用会中断，长测需重连与重试。
3. **计费陷阱**：按量实例**关机不等于停费**（腾讯云仅当系统盘+数据盘均为云盘时关机不收费；阿里云需开节省停机模式）；抢占式虽可低至 1 折但**随时回收，不能用于长实验**。

**推荐用法（预算内）**：阿里云按量 ECS × 2（同 VPC、同可用区、六代+、8核16G 级），先花半天（约 10 元）验证 DPDK 在云上能否跑通；再跑两节点 KV 传输 + 内核 TCP 对照（数小时，约 20–50 元）；如需 RDMA 对照，换用支持 ERI 的实例族按官方文档启用 eRDMA。整套云上实验预计**几十到两三百元**，在 1000 元预算内。可照抄阿里云 E-HPC 文档的 OSU-Benchmark 方法（`FI_PROVIDER="tcp;ofi_rxm"` vs `"verbs;ofi_rxm"`）作为 TCP/RDMA 对照口径。
