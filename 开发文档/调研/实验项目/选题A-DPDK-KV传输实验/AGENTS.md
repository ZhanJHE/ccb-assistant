# 选题 A · DPDK 用户态 KV 传输实验（项目规则与起步文档）

> 本文件是本实验项目的**工作规则 + 起步文档**，约束范围：`实验项目/选题A-DPDK-KV传输实验/` 目录。
> 相关材料：本项目内 `docs/`（选题依据与方案：A-DPDK用户态KV传输引擎 / A-可行性五问答复 / A-实验环境方案）、`analysis/`（核算产出）、`scripts/`（核算脚本）；工作区级 `../../../文献索引.md`（唯一总库）、`../../../选题方案/DPDK-RDMA-eBPF选题/`（B~E 未立项选题）、`../../../调研卷宗/`（主题综述）。
> 创建：2026-09-27。维护人：ZhanJH。**任何 Agent 在本目录开始工作前必须先读本文件与 §2 的事实基线，不要重新调研已核实的结论。**

## 0. 30 秒速览（给新接手的 Agent）

- **做什么**：在 Mooncake 的 **TENT** 传输引擎里新增一个 **`dpdk_transport`** 后端，用 DPDK 内核旁路在**普通以太网卡**上传 PD 分离 LLM serving 的 KV cache，并与 TENT 自带的 `hp_tcp` / `tcp`（可选 `rdma`）**同台对比**。
- **为什么可行**：Mooncake 的 `transfer_engine_py.cpp` 已有 `MC_USE_TENT` 运行时开关，**vLLM 与 connector 一行不改**即可把数据面切到 TENT；因此工作量集中在传输后端本身。
- **产出**：可投 CCF-B 的系统论文 + 可复现的实验代码与数据 + 一次与生产栈的正面比较。
- **不做什么**：不发明逐层流水调度（已被 Topology-Aware 占位）、不声称"普通以太网能传 KV"（已被 PrfaaS 占位）、不在云上测微基准（见 §8）。
- **第一个里程碑**：G1（环境跑通）→ G2（TENT 后端接口跑通），见 §4。

## 1. 项目定义

### 1.1 一句话
> 在工业级 KV 传输引擎中落地一个 DPDK 用户态后端，用**端系统数据面**（每字节 CPU 成本与拷贝次数）而非"能不能传"来定义贡献。

### 1.2 可宣称（claim）与不可宣称

| 可宣称 | 不可宣称 |
|---|---|
| 每 GB 的 **CPU 成本**与**拷贝次数**相对内核 TCP 的下降（量级 10–250×，见 §2.4） | 带宽的成倍提升（链路受限时通常只有 1.0–1.3×） |
| incast 与尾延表现（投递时延 4.3–5.0 µs → 0.47 µs；p99.99 76.6 → 5.8 µs 是文献值，需自测） | "替代 RDMA" |
| 与 `hp_tcp`/`tcp`/`rdma` 的**同台对比**与成本-性能 Pareto 位置 | 绝对推理吞吐 / t·s⁻¹（除非有大模型真机数据） |
| KV 语义驱动的 credit / 优先级 / 块级 ACK 机制 | GPU 显存直通（消费级 GeForce 不支持 GPUDirect，见 §2.3） |

### 1.3 为什么走 S2（TENT 后端）而不是 S1（vLLM connector）
接口面更窄（9 个虚函数 + 5 处登记）、引擎已提供持久 lane / sub-batch / failover、自带生产级对照基线、且 vLLM 零改动。S1 仅作为**备用集成点**：若 TENT 集成在 2–3 周内跑不通，把同一份传输实现改挂到 vLLM 的 `kv_connector` 上。

## 2. 已核实的事实基线（不要重新调研）

### 2.1 集成契约（源码级，2026-09-27 核实）
**TENT 后端必须实现（`mooncake-transfer-engine/tent/include/tent/runtime/transport.h` 的 `class Transport`）**：
`install` / `uninstall` / `quiesce`、`allocateSubBatch` / `freeSubBatch`、`submitTransferTasks`、`getTransferStatus`、`retryTransferTask`、`addMemoryBuffer` / `removeMemoryBuffer`、`getName` / `getEstimatedBandwidth` / `getNicLoadStats`（行号见下，2026-09-28 在 v0.3.14-rc1 上复核）。
> **这是"必做核心"，不是全集**：rc1 的 `Transport` 另有 10 个虚函数需按需覆盖——`capabilities`(:87)、`supportsCancellation`(:129)、`cancelTransferTask`(:131)、`allocateLocalMemory`(:136)、`freeLocalMemory`(:141)、`warmupMemory`(:148)、`tracksLocalBuffer`(:171)、`supportNotification`(:173)、`sendNotification`(:175)、`receiveNotification`(:181)。

**登记点 5 处**（行号以 v0.3.14-rc1 为准）：`tent/include/tent/common/types.h:46` 类型枚举（枚举体含 `HP_TCP`）、同文件 `transportTypeName:72` / `parseTransportType:108`、`tent/include/tent/transfer_engine.h:102-115` 的 `TRANSPORT_*` 常量（含 `TRANSPORT_HP_TCP (13)`）、`tent/src/runtime/transport_loader.cpp:60 loadTransports()`（登记模式：`if (conf_->get("transports/<名字>/enable", 默认值)) transport_list_[<类型>] = std::make_shared<XxxTransport>();`）、`tent/src/transport/CMakeLists.txt`（14 个 `add_subdirectory` + `tent_xport_*` 目标列表）。**行号会随上游漂移**（同一断言在 0.3.13.post1 上是 `55` / `1122`），核对时抓上下文而不是只认行号。**另有 2 处"登记点"原文没写、但漏了会出问题**：① `tent/src/transport/CMakeLists.txt` 里除 `add_subdirectory(<名字>)` 外，还必须把新目标名（如 `tent_xport_dpdk`）加进 `tent_transport_all` 的 `foreach` 目标名单，否则链接测试可执行文件会失败；② `tent/tests/transport_selector_test.cpp` 里有硬编码断言 `EXPECT_EQ(static_cast<int>(kNumTransportTypes), 14)`，追加任何 transport 类型都会让它变红（2026-09-28 实测 `Which is: 15 / 14`）——该断言不在 M2 的三条基线里，只跑那三条会漏。

**硬约束**：`submitTransferTasks` 必须 **all-or-nothing**（`transport.h:98` 起 8 行注释逐字写明：出错返回时不得有任何 `request_list` 中的请求被派发、sub-batch 必须保持调用前状态、已开始接受的必须回滚；这样引擎 failover 才不会**重复执行已接受的前缀**或丢失原 sub-batch），否则 failover 会重复投递。

**捷径**：`mooncake-integration/transfer_engine/transfer_engine_py.cpp:1137`（0.3.13.post1 为 1122）存在 `MC_USE_TENT` / `MC_USE_TEV1` 运行时开关；设 `MC_USE_TENT=1` 即可让 vLLM 的 `mooncake.engine.TransferEngine` 走 TENT。

**可直接复用的测试台**：`tent/tests/tcp_transport_test.cpp`、`hp_tcp_transport_test.cpp`、`tcp_datapath_roundtrip_test.cpp`（三者在 v0.3.14-rc1 均存在；ctest 名分别是 `tent_tcp_transport_test` / `tent_hp_tcp_transport_test` / `tent_tcp_datapath_roundtrip_test_{single_threaded,multi_threaded_rpc}`）。`FakeTransport` **不在**这三个文件里，定义于 `progress_worker_test.cpp:70`、`transport_selector_test.cpp:36`、`metrics_recording_test.cpp:189`、`runtime_queue_dispatch_test.cpp:47`、`delegate_rpc_test.cpp:50`、`stage_buffer_concurrency_test.cpp:51`。`tent/benchmark/` 确实只有 `hip_bandwidth_bench.cpp`，但**通用带宽基准不必自建**：`mooncake-transfer-engine/benchmark/` 就是 **tebench**（`te_backend` = classic TE、`tent_backend` = TENT，含 `workload_config` 与 QoS 指标），由 `-DBUILD_BENCHMARK=ON` 控制。

**vLLM 侧契约**（备用集成点，`vllm/distributed/kv_transfer/kv_connector/v1/base.py`）：`register_kv_caches` / `save_kv_layer(layer_name,…)` / `wait_for_layer_load(layer_name)` / `wait_for_save` / `get_num_new_matched_tokens` / `update_state_after_alloc` / `get_transfer_results`。其中 `save_kv_layer` 与 `wait_for_layer_load` 是逐层钩子。

### 2.2 上游版本锁定（每次实验必须在记录卡里写明）
| 组件 | 版本 | 许可 |
|---|---|---|
| Mooncake | **v0.3.14-rc1**，提交 `78566d459c140956fd15606e102132b1acc83eec`（2026-09-07）。**该 tag 是附注标签**——标签对象是 `cfacafca…`，锁定必须用 `git rev-parse <tag>^{commit}`。选择理由：`hp_tcp` / `quiesce` / `retryTransferTask` 自 rc1 起才有，0.3.13.post1 没有（证据见实现仓库 `results/2026-09-28-mooncake-lock-verify/`） | Apache-2.0 |
| DPDK | **25.11.3 LTS**（已锁定；tar 包 sha256 `3719acc586b310c4f60ba230683bf4f1e12c6f2f5bee11f7c01b1bbd0ded7490`） | BSD-3-Clause（核心）/ GPL-2.0（内核组件） |
| vLLM | 0.30.0 | Apache-2.0 |
| F-Stack（保底协议栈） | 1.21.6（以 tag 固定） | BSD-2-Clause |
| CUDA | 13.4 | NVIDIA 专有 |

### 2.3 平台与硬件
- **首选（云上端到端）**：阿里云按量 ECS × 2，同 VPC 同可用区，**六代（g6/c6/r6）及以后**；官方文档《使用 VFIO 驱动替代 UIO 驱动》给出在**普通云服务器**上跑 DPDK 的完整步骤（设 HugePages → GRUB 加 `intel_iommu=on` 并删 `iommu=pt` → 重启 → `modprobe vfio vfio-pci` → `enable_unsafe_noiommu_mode` → `ethtool -i` 取 bus-info → `dpdk-devbind.py -b vfio-pci` → testpmd）。
- **首选（微基准与干净数据）**：本地 Linux 机器 + 二手双口 10G 卡自环（100–300 元）。
- **RDMA 对照**：改用阿里云支持 **ERI/eRDMA** 的实例族（c8i/c9i/c8a、hpc9a 等），按《在企业级实例上启用 eRDMA》在 VPC 内互联（中间不能跨 SLB 等网元）。
- **不支持**：AutoDL 常规容器实例（无 `CAP_SYS_MODULE`/`CAP_SYS_ADMIN`、无 PCI 直通、且租户实例间**不支持内网互通**）；华为云 BMS（**只能包年包月**）。
- **GPU 侧**：本地 RTX 4060（8 GB）跑正确性闭环；云上短租补端到端。**GPUDirect / DMA-BUF 不作为前提**——消费级 GeForce 不在官方支持范围（文档只写 Tesla/Quadro 与 data center GPUs）。

### 2.4 模型与 KV 几何（判据，来自 `../analysis/选题A-选型核算.md`）
- 每 token KV 字节 = `2 × 层数 × KV头数 × head_dim × 2B`。实取结果：Qwen2.5-1.5B **28 KB**、7B **56 KB**、Llama-3.1-8B 128 KB、Qwen2.5-32B 256 KB、Llama-2-7B **512 KB**（MHA 32 头）、LLaMA2-70B 形态 320 KB。
- **选型判据**：`r ≈ (KV字节/token × F) / (2 × 参数量 × B)`，`p = r/(1+r)`，目标 **p ∈ [0.2, 0.5]**（F = 实测标定的有效 prefill 算力，B = 链路字节率）。
- **打满链路所需 KV 产出**：10 GbE 需要 Qwen2.5-1.5B 43,597 tok/s（≈134 TFLOPS）或 Llama-2-7B 2,384 tok/s（≈31.9 TFLOPS）。**结论：单张消费级 GPU 喂不满链路，满线速必须用合成 KV 流**（打满 10 GbE 只需 4,768 块/s @256 KB，单核 memcpy 可达）。
- 每 GB CPU 成本（文献值，需自测复现）：内核 TCP 0.85–4.31 核秒/GB vs DPDK 0.017–0.034（MTU 1500）；**必须报告 TSO/GSO 开关**（开启后内核开销塌缩到 0.0145–0.0872 核秒/GB，结论会翻转）。

### 2.5 撞车与差异化（论文里必须逐句照做）
| 已有工作 | 它占了什么 | 我们必须怎么写 |
|---|---|---|
| Mooncake TENT `hp_tcp` | "数据中心 TCP 上的 KV 传输引擎"。已核实（v0.3.14-rc1，`docs/source/design/tent/hp-tcp.md`）：persistent lane ✅、"versioned TCP protocol" ✅、v1 **明确不含 GPU 内存** ✅。**"AF 内核 socket""1 MiB 切片""per-WRITE ACK"三个措辞在该版本的文档与源码里找不到出处 → 标"待核实"**。该后端自 v0.3.14-rc1 起存在（0.3.13.post1 没有） | 强调"替换的是**数据面操作系统路径**（PMD 轮询 + hugepage 零拷贝 + 内核旁路），且覆盖 GPU staging"，并**以 TENT 新 backend 形式同台对比**（对照基线用 v0.3.14-rc1 的 `hp_tcp`，同时保留 `tcp` 作兼容路径基线） |
| PrfaaS（arXiv:2604.15039） | "over commodity Ethernet" + 去 RDMA 的动机 | 承认其调度层贡献，说明我们的贡献在端系统数据面 |
| Topology-Aware（arXiv:2607.28633） | 逐层流水掩盖传输 | 逐层流水只作**工程化复用**，不作创新点；增量在"该流水在轮询模式 NIC 上的实现" |
| RTT- or Bandwidth-Bound（NAIC'25） | 逐块串行在高 RTT 下退化 | 引用其诊断，我们回答它留下的数据面问题 |

## 3. 实验设计（默认配置，改动需在记录卡说明理由）

### 3.1 链路档位
**默认 10 GbE**（或 tc 限速到 1 / 2.5 / 5 Gbps 做敏感度）。25/100 GbE 只作补充——`p` 太小会测不出差异。

### 3.2 负载：模型 × 数据集
| 角色 | 模型 | 数据集 |
|---|---|---|
| 本地正确性闭环 | Qwen2.5-1.5B（FP16 可放 8 GB） | ShareGPT（到达过程） |
| 形态现实性（主实验） | Qwen2.5-7B / Llama-3.1-8B（GQA） | ShareGPT + LMSYS-Chat-1M |
| 链路压力（暴露瓶颈） | Llama-2-7B（MHA，512 KB/token）或 Qwen2.5-32B | LongBench / RULER 长输入（32K/128K） |
| 满线速与扫参 | **合成 KV**（按 config.json 几何生成） | ShareGPT 到达过程驱动 |
| 70B 形态（不真跑） | dummy LLaMA2-70B 架构（Mooncake 先例） | Mooncake 风格真实 trace（若可获得，否则合成） |
> 精度指标只在做压缩/量化消融时需要（LongBench / RULER）。

### 3.3 消融矩阵
KV 精度（FP16/INT8/INT4）× 块大小（64 KB/256 KB/1 MB）× incast 度（1/4/16）× TSO/GSO 开关 × 传输后端（内核 TCP / `hp_tcp` / `dpdk`[+ 可选 AF_XDP / eRDMA]）。

### 3.4 指标定义（唯一口径，禁止另立）
`每 GB CPU 成本（核秒/GB）`、`传输耗时占 JCT 比例`、`TTFT`、`TPOT`、`goodput@90% SLO`、`p50/p99/p999`、`KV 传输字节`、`有效带宽`。
大消息口径统一到"传完一个 70B/4K 形态的 KV 段"或"一个 4K 请求的 KV"。

### 3.5 对照组
① 内核 TCP（`iperf3` + vLLM 原生路径）；② Mooncake `hp_tcp`；③（可选）AF_XDP 作旁路纯度消融；④（可选）阿里云 eRDMA 作 RDMA 上限参照。可照抄阿里云 E-HPC 文档的 OSU-Benchmark 口径（`FI_PROVIDER="tcp;ofi_rxm"` vs `"verbs;ofi_rxm"`）。

## 4. 里程碑与 Go/No-Go（2026-09 → 2027-05）

| 时间 | 目标 | Go/No-Go 判据 |
|---|---|---|
| 10 月上 | 环境：本地或阿里云按量双节点跑通 testpmd + 双节点 echo | **G1**：跑不通 → 退 AF_XDP 或纯仿真 |
| 10 月下–11 月 | 实现 `dpdk_transport` 骨架并打通接口语义。**已完成 2026-09-28（v1 口径）**：4 个新文件 + 6 处登记，自建 `dpdk_transport_test` 7/7 通过、6 条回归全绿，数据面走真 PMD 收发；证据见实现仓库 `results/2026-09-28-dpdk-transport-skeleton/` | **G2（已达成）**：2–3 周内接口跑不通 → 退 S1（vLLM connector）。v1 明确未做：零拷贝、credit 流控、超时→FAILED、性能
| 12 月 | 真网卡双节点收发 + 零拷贝（外部 buffer）+ credit 流控 | 吞吐/CPU 达成预期一半以上 |
| 1 月 | 逐层流水 + incast 场景；与 `hp_tcp` 首轮对比 | **G3**：收益不显著（<2×）→ 主线改为"KV 语义调度（credit/优先级/incast）" |
| 2–3 月 | 端到端（TTFT/goodput）+ 全部消融 + 合成 KV 满线速 | 数据齐备，含 TSO/GSO 对照 |
| 4 月 | 写作投稿（Computer Networks / TCC / JPDC；或 ICDCS/ICPP/Euro-Par/ICCD/DATE） | 投稿前自检 §7 |

## 5. 目录与产物约定

```
选题A-DPDK-KV传输实验/
  AGENTS.md            ← 本文件（项目规则与起步文档）
  docs/                ← 选题依据与方案：A-课题规划书（导师汇报版）.md / A-DPDK用户态KV传输引擎.md / A-可行性五问答复.md / A-实验环境方案.md
  scripts/             ← 本项目核算脚本（选题A-环境核算.py / 选题A-选型.py）
  analysis/            ← 脚本产出（选题A-环境核算.md / 选题A-选型核算.md）
  results/             ← 每次实验一个目录：results/YYYY-MM-DD-<名字>/{cmd.txt, config.yaml, raw/, summary.md}
  code/                ← 实验代码（Mooncake fork、dpdk_transport 后端、实验脚本）
  论文/                ← 写作与图表源文件
```
> 与工作区的分工：`../../../工具/` **只放跨项目通用脚本**（如 CCF 目录解析）；本项目专有脚本一律放 `scripts/`，其产出放 `analysis/`，实验记录放 `results/`。

> **实现仓库位置（2026-09-27 起）**：实验**代码与实验记录**的落地位置改为独立 git 仓库 `C:\Users\ZhanJH\Desktop\MyProject\Lab1_DPDK_KV_Cache\`（内含 `code/`、`results/`，为**唯一 git 仓库**）；**本目录继续作为规则与方案文档的唯一来源**（`AGENTS.md`、`docs/`、`analysis/`、`scripts/`）。两处 AGENTS.md 必须保持**逐字节一致**，任何修订同时改两份（校验：`diff -q`）。构建与运行在 **WSL2 原生文件系统**（`~/lab1/`）内进行；第三方源码与构建产物不入库，版本与校验值记在实现仓库 `code/dpdk/PROVENANCE.md`。

## 6. 工作规则（对 Agent 有约束力）

### 6.1 每次会话
- **开场**：读本文件 §2（事实基线）与 `results/` 最新一条 `summary.md`；不要重复调研已核实结论。
- **收尾**：把本轮**新增**的事实与踩坑写回本文件（若改变结论）与该次 `results/*/summary.md`。

### 6.2 实验记录卡（强制，缺一项即视为该实验无效）
`results/YYYY-MM-DD-<名字>/summary.md` 必须含：目的 / 环境（组件版本 + 机器规格 + 链路档）/ 命令原文 / 参数 / **原始输出文件路径** / 观察到的数字 / 结论（含反例）/ 异常与未解问题 / 花费（云上）。

### 6.3 凭证与安全
- 阿里云 AccessKey、S2 Key、HuggingFace token 一律**从环境变量读**，**禁止写入任何文件、日志、截图或提交**。
- 会失联的操作（`dpdk-devbind.py -b vfio-pci` 绑唯一网卡、改 GRUB、重启）**必须先确认**，并保留带外通道（云上留串口/控制台，本地留板载网口做 SSH）。

### 6.4 成本纪律
- 云上按量实例：**跑完立即释放**（关机不等于停费）；单次实验预算上限 50 元、月度 300 元，超限须先确认；不要把抢占式实例用于长实验（随时回收）。
- 每次云上实验在记录卡里写明**实际花费**。

### 6.5 版本与可复现
- 锁定 DPDK 版本、Mooncake commit、vLLM 版本、内核版本；任何上游改动都要留 diff（`code/patches/`）。
- 合成 KV 生成脚本、限速命令（`tc`）、绑核（`cpuset`）都必须进 `cmd.txt`。

### 6.6 禁止事项
- 禁止编造任何数字、版本、链接；无法验证的标"待核实"。
- 禁止在云上 VF 上测"每包 cycles"微基准并当物理网卡结论（见 §8）。
- 禁止把 TSO/GSO 默认开着测内核 TCP 作为公平对比。
- 禁止把逐层流水、块级串行退化当作本方创新点（已被占位）。

## 7. 投稿口径（依官方《第七版 CCF 推荐目录》）
- **CCF-B 期刊**：Computer Networks、IEEE TCC、JPDC。**会议**：ICDCS、ICPP、Euro-Par、MSICC 系列（ICCD/ICCAD/DATE）、CoNEXT、ICNP、IWQoS。
- **注意**：`ACM TOS` / `ACM TACO` 是 **A 类**（不要当 B 类目标写）；`IEEE TNSM` 与 `Computer Communications` 是 **C 类**。
- 投稿前自检三条硬条件：① 与内核 TCP + 至少一条 RDMA/UCX **正面对比**且报端到端指标；② 有 **KV 语义层**的机制贡献；③ ≥3 场景 × ≥3 基线 + 参数表 + 开源代码。

## 8. 常见陷阱（本轮已踩或文档写明）
1. **云上 VF ≠ 物理网卡**：bus-info 形如 `0000:00:06.0`，且需 `vfio enable_unsafe_noiommu_mode` → 微基准只在本机物理网卡做。
2. **VF 会在宿主机维护时消失**（Azure 文档明确，国内云同理）→ 长测要有重连与重试。
3. **自动 KL**：hugepage 未预留、`iommu=pt` 未删、`vfio-pci` 未 `modprobe` 都会在启动时报错——按 §2.3 的官方步骤顺序走。
4. **`submitTransferTasks` 非 all-or-nothing** 会导致 failover 重复投递（宪法级约束，见 §2.1）。
5. **轮询线程占满核**：用 interrupt-wait 混合模式，并同时报 CPU 与能效。
6. **TENT 上游演进**：`MC_USE_TENT` 是新路径，行为可能变 → 锁 commit，月度只做一次 diff 审计。
7. **成本**：忘记释放按量实例是最贵的错误。
8. **WSL2 只作代码路径台**（2026-09-27 实测）：本机 WSL2（Ubuntu 24.04 / kernel `6.6.87.2-microsoft-standard-WSL2`）无 PCI 直通（`/sys/class/iommu` 为空），`eth0` 为 Hyper-V netvsc（无对应 PMD）→ 只能跑 `net_tap` / `net_ring` 虚拟机件，**数据不得用于性能结论**；**2 MiB 大页可预留**（2026-09-28 实测：`sysctl -w vm.nr_hugepages=2048` 成功、`/dev/hugepages` 由 WSL 预挂，无需 `--no-huge`；但 WSL 重启即丢，需重跑 `code/env/wsl2-hugepages.sh`）。另：`wsl.exe ... -- bash -lc '<脚本>'` 会吃掉脚本里的 `$变量`（产生假结论），必须**脚本落盘后 `bash <file>`** 执行；Git Bash 传 `/mnt/c/...` 需加 `MSYS2_ARG_CONV_EXCL='*'`。
9. **testpmd 三个坑**（2026-09-28 实测，DPDK 25.11.3，行号为本地检出）：① CLI 的 `--tx-first` 不能用于交互模式（`app/test-pmd/testpmd.c:4619`），要用交互命令 **`start tx_first`**（`cmdline.c:145`）；② `set fwd` 必须在端口未启动时下发（`testpmd.c:3162` 报 "Please stop the ports first"），否则沿用旧引擎、计数会假通过（首轮就是这样停在 ring 容量 1023）；③ 多进程要分配不同 lcore 与不同 `--file-prefix`。自环用 net_ring + `--port-topology=paired` + `set fwd mac`；跨进程用 net_tap + 内核 bridge。
10. **`net_ring` 是端口自环，不是两端口互联**（2026-09-28 实测 + 源码）：`drivers/net/ring/rte_eth_ring.c` 的 `eth_dev_ring_create` 只建一个 ring `ETH_RXTX0_<name>`，用 `rte_eth_from_rings(r->name, &r, 1, &r, 1, …)` 把**同一个 ring 同时当 rx 与 tx** → `--vdev=net_ring0` 的 TX 由它自己的 RX 收到，`net_ring1` 收不到任何东西。**任何"用 net_ring 造一条链路"的设计都要按端口自环写**；真正的跨端点必须用 `net_tap` + 内核 bridge（M1 已证）。
11. **追加 transport 类型有两个隐藏必改点**：`tent/src/transport/CMakeLists.txt` 的 `tent_transport_all` 目标名单（漏了会链接失败）；`tent/tests/transport_selector_test.cpp` 里硬编码的 `kNumTransportTypes == 14` 断言（漏了测试红，且它不在基线三条里）。新增枚举值要插在哨兵之前，且**不要改动既有类型的值**（`TRANSPORT_HP_TCP (13)` 是 C ABI 契约）。
12. **DPDK 未安装时 `pkg-config libdpdk` 拿不到**：DPDK 构建树 `build/meson-uninstalled/` 里只有 `libdpdk-uninstalled.pc`，其 `Requires: libdpdk-libs` 在同目录缺对应文件 → 需 `ninja -C <build> install`（本项目已装到 WSL 的 `/usr/local`，`pkg-config --modversion libdpdk` = 25.11.3）。CMake 侧用 `pkg_check_modules(DPDK IMPORTED_TARGET libdpdk)` + `#ifdef USE_DPDK` 门控，保证没有 DPDK 的机器仍能正常构建。

---
### 变更记录
| 日期 | 变更 | 依据 |
|---|---|---|
| 2026-09-27 | 创建本文件 | 汇总 `docs/A-实验环境方案.md`、`docs/A-可行性五问答复.md`、`analysis/选题A-选型核算.md` 的核实结论 |
| 2026-09-27 | 目录重排后同步路径 | 工作区分为 导航/调研卷宗/选题方案/实验项目/参考资料；本项目的方案文档移入 `docs/`、脚本移入 `scripts/`、产出移入 `analysis/`；§5 目录约定与全文路径已同步 |
| 2026-09-27 | 补 §5「实现仓库位置」与 §8 陷阱 8；两份 AGENTS.md 同步 | 实测：本机无 10G 网卡且板载 GbE 处于 Disabled、WSL2 无 PCI 直通、`wsl.exe` 吃 `$变量`、`raw.githubusercontent.com` 不可达；证据见实现仓库 `results/2026-09-27-env-probe/summary.md` |
| 2026-09-28 | 修订 §8 陷阱 8（大页可预留，推翻原预判）、新增陷阱 9（testpmd 三个坑） | M1 实测：DPDK 25.11.3 在 WSL2 编译通过，net_ring 自环与 net_tap 跨进程收发均跑通；证据见实现仓库 `results/2026-09-28-wsl2-dpdk-bringup/summary.md` |
| 2026-09-28 | **版本锁前移：Mooncake 0.3.13.post1 → v0.3.14-rc1**（提交 `78566d45`，附注标签）；§2.1 补全虚函数全集与登记点行号（60 / 1137）、修正测试台清单；§2.5 `hp_tcp` 行补证据并标"待核实" | M2 实测：`hp_tcp` / `quiesce` / `retryTransferTask` 自 rc1 起才有（post1 全无）；rc1 上三条基线测试全绿；证据见实现仓库 `results/2026-09-28-mooncake-lock-verify/summary.md` |
| 2026-09-28 | §4 的 G2 标记为已达成（v1 口径）；§2.1 补 2 处隐藏登记点（`tent_transport_all` 目标名单、`transport_selector_test` 的硬编码类型数断言）；§8 新增陷阱 10–12（`net_ring` 端口自环 / 追加类型的必改点 / `libdpdk` 获取方式） | M3 实测：`dpdk_transport` 骨架编译通过、自建测试 7/7 通过、6 条回归全绿，数据面为真 PMD 收发（`rte_eth_tx_burst`/`rx_burst`）；证据见实现仓库 `results/2026-09-28-dpdk-transport-skeleton/summary.md` |
| 2026-09-28 | 新增 `docs/A-课题规划书（导师汇报版）.md` 并登记进 §5 的 docs 清单 | 应用户要求产出面向导师的完整规划书（方法学与规划层：问题定义、贡献边界、差异化、实验设计、里程碑与 Go/No-Go、资源成本、风险退路、投稿目标、待导师确认事项） |
