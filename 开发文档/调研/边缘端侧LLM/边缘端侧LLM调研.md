# 边缘/端侧 LLM 推理优化 调研（ARM SoC + NPU，面向 RK3588）

> 持续更新的主题综述。首次建立：2026-09。
> 配套总库见 `文献索引.md`（本专题编号 E1–E25；云端 KV/FPGA 条目见总库 #1–#35）。

## 0. 元信息
- **目标读者**：即将读研、有 RK3588（8×A76/A55 + Mali-G610 + 6 TOPS NPU，RKNN 工具链）+ Artix-7 FPGA + BlueField DPU 的本科生；目标 6–9 个月做出可投 CCF-B 的原型（**分级依官方《第七版 CCF 推荐目录》核对，2026-09-27 更正**：边缘相关 B 类会议 SenSys/MobiSys/ICDCS/ICPP/Euro-Par；B 类期刊 **Computer Networks**——**`TNSM` 实为 C 类**，此前误标为 B；MobiQuitous/ICPADS/SEC 为 C 类）。
- **边界**：只收真实可验证的论文/项目；性能数字全部带出处；查无实据的系统名单列"未证实"，绝不引用。
- **关键词**：on-device/edge LLM, NPU offload, heterogeneous scheduling, CPU-GPU-NPU, KV cache quantization/eviction/paging, KV offload to flash/UFS/SSD, edge-cloud collaborative inference, speculative decoding edge, early-exit, BitNet/1.58-bit。

## 1. 一句话总览
端侧 LLM 的 decode 阶段是**内存带宽/容量瓶颈**、prefill 阶段是**算力瓶颈**；2023–2024 的系统（llama.cpp、MLC、MNN、PowerInfer）主要在 CPU/消费级 GPU 上靠量化+稀疏激活解决，2025 起 **NPU offload（llm.npu/Panda）** 与 **KV cache 分层换页到闪存（KVSwap、mzCache、TierKV）** 成为两条最新主线；但 NPU 的静态图、弱浮点、不支持 per-group MatMul 与动态 KV 操作，导致"NPU 只擅长 prefill、decode 仍靠 CPU"，这正是可切入的空白。

## 2. 技术路线分类与权衡

### 路线 A：通用端侧推理引擎（编译 + 量化）
- **llama.cpp**（GitHub 项目，**无论文**）：GGUF 格式 + 高度优化的 CPU/GPU kernel，ARM NEON 支持成熟；事实端侧基线。优点：模型生态最全；缺点：NPU 用不上（RK3588 上纯 CPU）。
- **MLC-LLM**（GitHub 项目，**无正式论文**；相关论文为其浏览器版本 WebLLM，[arXiv:2412.15803](https://arxiv.org/abs/2412.15803)）：TVM 编译 + 各平台 GPU（含 WebGPU/Vulkan/Metal）。优点：跨平台 GPU；缺点：不支持厂商 NPU。
- **MNN**（[arXiv:2002.12418](https://arxiv.org/abs/2002.12418)，MLSys'20，阿里，S2 引用 192）：CPU/GPU/NPU 多后端通用引擎，国内边缘部署常用。
- 权衡：通用性强但无法吃透专有 NPU，性能靠量化与 kernel 优化，上限受内存带宽锁死。

### 路线 B：稀疏激活（neuron sparsity）
- **PowerInfer**（[arXiv:2312.12456](https://arxiv.org/abs/2312.12456)，SOSP'24）：神经元激活呈幂律，热神经元常驻 GPU、冷神经元 CPU 计算；RTX4090 上比 llama.cpp 快最多 11.69×（数字见论文摘要）。
- **PowerInfer-2**（[arXiv:2406.06282](https://arxiv.org/abs/2406.06282)）：把矩阵拆成**神经元簇**，密集簇上 **NPU**、稀疏簇 CPU，配 I/O-计算流水线；首次在手机跑 47B 模型（11.68 t/s），最高 27.8× 加速（论文摘要数字）。
- 权衡：依赖 ReLU/稀疏激活结构与预测器；动态稀疏与 NPU 静态执行模型天然冲突，是 PowerInfer-2 要专门设计簇调度的原因。

### 路线 C：NPU offload 与异构调度（2025 新主线）
- **llm.npu / 社区常称 Panda**（[arXiv:2407.05858](https://arxiv.org/abs/2407.05858)，ASPLOS'25，北大 Daliang Xu / Mengwei Xu 等）：
  - 直接量化 NPU 的三大硬限制（论文 §2.3）：① 只支持**静态 shape**，变长 prompt 要重编译图（Gemma-2B 图优化 11.54 s）；② **不支持 per-group MatMul**，AWQ/K-Quant 式分组量化要拆成多个子矩阵再浮点归约，开销 8.1–10.7×；③ **浮点极弱**（FP16 MatMul 比 INT8 慢百倍量级），而 LayerNorm/Attention 离不开浮点。
  - 三招：chunk-sharing graph（定长块复用静态图，内存开销降 75%）、shadow outlier execution（0.1–0.3% 离群通道抽去 CPU/GPU 并行补精度）、out-of-order block 调度。
  - 结果（摘要数字）：prefill 平均快 **22.4×**、节能 **30.7×**；端到端应用最高 32.8×；1B 模型 prefill 首次 >1000 t/s。
- **APEX**（[arXiv:2506.03296](https://arxiv.org/abs/2506.03296)）：把 KV 管理与部分 attention offload 到 CPU，用 profiling 预测执行时间、最大化 CPU-GPU 异步重叠；T4 吞吐 +84–96%、A10 +11–89%（摘要数字）。
- 测量类佐证：
  - **Is Your NPU Ready for LLMs?**（[arXiv:2607.05475](https://arxiv.org/abs/2607.05475)，2026）：5 框架×CPU/GPU/NPU 跨层测量，核心结论——**NPU 强 prefill、CPU 强 decode**（NPU 偏好大的定长任务，与 decode 小 kernel/动态性冲突）；框架在 NPU 上差距可达 10×；最佳配置省能 54.8%。
  - **Hydra**（[arXiv:2608.25053](https://arxiv.org/abs/2608.25053)，IISWC'26）：三代边缘 SoC（Xavier/Orin/Thor）× 13 LLM × 5 种执行格式的分阶段特征框架，约 10.7 万条记录开源（github.com/amirtaherin/hydra）。
- 权衡：NPU 只接得住规则、稠密、静态、整型的计算；decode 的 GEMV + 动态 KV 操作仍被赶回 CPU/DRAM。

### 路线 D：边缘 KV cache 优化（量化 / 驱逐 / 换页，本调研结合点）
- **量化**：**KIVI**（[arXiv:2402.02750](https://arxiv.org/abs/2402.02750)，ICML'24）——Key 按 channel、Value 按 token 做 2-bit，峰值显存 -2.6×、batch ×4、吞吐 2.35–3.47×（摘要数字）。
- **驱逐/稀疏**：
  - **StreamingLLM**（[arXiv:2309.17453](https://arxiv.org/abs/2309.17453)，ICLR'24，S2 引用 2475）：attention sink，保留 sink+滑窗即可无限长度。
  - **H2O**（[arXiv:2306.14048](https://arxiv.org/abs/2306.14048)，NeurIPS'23，S2 引用 949）：动态保留 recent + heavy-hitter，20% hitter 对 OPT-6.7B/30B 最高 29× 吞吐（摘要数字）。
  - **SnapKV**（[arXiv:2404.14469](https://arxiv.org/abs/2404.14469)，NeurIPS'24，S2 引用 951）：生成前用 prefill 注意力簇级选 KV。
  - **PyramidKV**（[arXiv:2406.02069](https://arxiv.org/abs/2406.02069)，S2 引用 433）：分层金字塔预算。
  - **InfiniGen**（[arXiv:2406.19707](https://arxiv.org/abs/2406.19707)，OSDI'24，S2 引用 338）：动态预测并按需换回重要 KV。
- **换页/分层到存储（端侧 2025–2026 最新）**：
  - **KVSwap**（[DOI:10.1145/3745756.3809234](https://doi.org/10.1145/3745756.3809234)，SenSys'25，北大）：磁盘感知分组 KV offload + 低秩 key 摘要预测重要性 + rolling buffer。
  - **mzCache**（[arXiv:2609.01338](https://arxiv.org/abs/2609.01338)，MobiCom'26）：多任务内存压力下把权重/KV 细粒度弹性驱逐，统一内存上 GPU 零等待、CPU 并发恢复，TTFT 降 2.1–5.5×。
  - **TierKV**（[arXiv:2609.21172](https://arxiv.org/abs/2609.21172)，2026）：decode 前用 prefill hidden state 预测，把 token 分到 exact/低秩/flash 三层；RAM 中 KV 降 12.5–34%、prefill 快 17.6×。
  - **KVNAND**（[arXiv:2512.03608](https://arxiv.org/abs/2512.03608)，cs.AR'25）：权重+KV 全放可计算 3D NAND 的无 DRAM 架构，page 级 KV 映射；MHA-7B/GQA-70B 在 128/1K/10K 上下文 geomean 快约 2×，并解决 100K 上下文 OOM。
- 权衡：量化省容量但 NPU 不吃 per-group；驱逐不可逆、易伤长任务召回；换页容量大但 I/O 停顿，需要预测式预取与存储感知布局——三者在端侧都还没有与 NPU 调度深度协同的成熟方案。

### 路线 E：边缘-云协同 / 多设备
- **CE-CoLLM**（[arXiv:2411.02829](https://arxiv.org/abs/2411.02829)，ICWS'25）：明确指出**上下文数据在云边间传输是主瓶颈**；latency-aware early-exit + 云端上下文管理 + 独立/协同双模式；延迟 -13.81%、84.53% 计算下沉（摘要数字）。
- **SpecEdge**（[arXiv:2505.17052](https://arxiv.org/abs/2505.17052)，NeurIPS'25，KAIST）：边缘消费级 GPU 用 speculative decoding 起草、云端只做验证、**只传 token 不传中间状态**；主动起草掩盖 WAN 延迟（实测 RTT 14.07 ms）；服务器吞吐 2.22×、成本效率 1.91×、token 间延迟 -11.24%（摘要数字）。
- **LinguaLinked**（[DOI:10.18653/v1/2024.acl-demos.16](https://doi.org/10.18653/v1/2024.acl-demos.16)，ACL'24 Demos）：多个可信移动设备分布式推理，线性规划做模型分片-设备匹配 + 运行时负载均衡。
- 权衡：层切分（Neurosurgeon 式）每 token 都要通信，在 LLM 自回归下延迟反而更高（SpecEdge 测出层切分比纯云端慢 2.35×）；speculative 式只传 token 通信少，但要求边缘起草模型足够强。

### 路线 F：权重量化与 1.58-bit
- 经典 PTQ：**GPTQ**（[arXiv:2210.17323](https://arxiv.org/abs/2210.17323)，S2 引用 2605）、**AWQ**（[arXiv:2306.00978](https://arxiv.org/abs/2306.00978)，引用 1801）、**SmoothQuant**（[arXiv:2211.10438](https://arxiv.org/abs/2211.10438)，引用 1914）、**Atom**（[arXiv:2310.19102](https://arxiv.org/abs/2310.19102)，引用 372）。
- **BitNet b1.58**（[arXiv:2402.17764](https://arxiv.org/abs/2402.17764)，S2 引用 471）：权重三值 {-1,0,1}，原生训练，参数量按 1.58-bit 计。
- 边缘落地现状（2025–2026）：多为**硬件架构探索**而非 RK3588 实测，如 FPGA LUT 式三值加速器 TeLLMe/TENET（总库 #5/#6）、CGLA 上 Signed-Int4 跑 BitNet（[arXiv:2609.27453](https://arxiv.org/abs/2609.27453)，待核实细节）；**RK3588 上 1.58-bit 缺高效 kernel、RKLLM 仅 W8A8（RK3576 另有 W4A16）**，即低比特在该平台仍难落地（出处：RKLLM benchmark.md，见下节）。

## 3. RK3588 能力画像（全部带出处）

### 3.1 硬件与内存带宽
- 配置：4×Cortex-A76 @2.4 GHz + 4×Cortex-A55 @1.8 GHz（8nm）；缓存：每 A76 核 512 KB L2、A55 128 KB，共享 3 MB L3（出处：[Turing Pi RK1 Benchmarks](https://turingpi.com/rk1-benchmarks/)，2026-04）。
- **内存接口是 64-bit LPDDR4X，理论峰值约 34 GB/s**（同出处明确写出 "64-bit LPDDR4X interface with a theoretical peak of ~34 GB/s"）。
- 实测带宽（Turing Pi，RK1 板）：
  - STREAM 理想顺序：**21–22 GB/s**；mbw MCBLOCK 17–19 GB/s；mbw MEMCPY 8–9 GB/s。
  - 并发悬崖：2 路内存受限任务时每路掉到约 60–65%（13–14 GB/s），3 路时 40–50%（8–10 GB/s）。
- 交叉验证（Radxa 工程师 tinymembench 实测，[Gist](https://gist.github.com/RadxaStephen/88b6a5e09699017d04a2299192104232)，2024-04）：
  - LPDDR5-2736（Rock-5-ITX）：NEON LDP load **20.6 GB/s**、C copy 13.9 GB/s、memchr scan 18.7 GB/s；
  - LPDDR4X-2112（Rock-5B，出货常见）：NEON LDP load **16.9 GB/s**、C copy 9.9 GB/s、memchr scan 14.6 GB/s。
- **结论：用户问题中"约 50–60 GB/s"的印象不成立**；RK3588 内存带宽实测约 **17–22 GB/s（LPDDR4X 板更低，10–17 GB/s）**，这就是 decode 带宽墙。

### 3.2 功耗与温度（Turing Pi，被动散热，25 分钟持续）
- 单板功耗：空闲 **4–5 W**、混合负载 6–9 W、CPU+内存满载 **10–12 W**；4 节点集群最大约 80 W。
- 温度：空闲 38–42 ℃，稳态满载 66–74 ℃，约 80 ℃ 以上开始降频；A76 稳态约 2.2–2.3 GHz。

### 3.3 跑 LLM 的实测性能
- **CPU（llama.cpp，GGUF，30 分钟持续）**（Turing Pi）：4B 5–8 t/s；7B 3–7 t/s；14B 2–4 t/s。
- **CPU 精确对照（llama-bench，pp1024 + tg256，4 线程）**（[GGUF 量化对比](https://turingpi.com/llm-inference-benchmarks-rk3588-gguf-quantization/)，2026-07）：

  | 模型 | 量化 | 1024 prompt 处理(s) | 生成 t/s | 峰值 RSS (MiB) |
  |---|---|---|---|---|
  | Qwen2.5-1.5B | Q4_K_M | 18.77 | **22.57** | 2021.5 |
  | Qwen2.5-1.5B | Q8_0 | 12.39 | 15.26 | 3281.2 |
  | Llama-3.2-3B | Q4_K_M | 40.09 | **11.25** | 4086.0 |
  | Qwen2.5-7B | Q4_K_M | 89.98 | **5.44** | 8885.0 |
  | Qwen2.5-7B | Q8_0 | 68.09 | 3.43 | 15138.3 |

  注：4 线程反而比 8 线程快（同出处方法论）；Q4_K_M 是该平台速度最优档。
- **NPU（RKLLM 官方 benchmark.md，release-v1.3.0，定频；[GitHub](https://github.com/airockchip/rknn-llm/blob/release-v1.3.0/benchmark.md)）**：

  | 模型 | W8A8 t/s | TTFT(ms) | 内存(MB) |
  |---|---|---|---|
  | Qwen2-0.5B | 41.58 | 145.9 | 669.6 |
  | TinyLLAMA-1.1B | 24.43 | 243.9 | 1093.7 |
  | Qwen2.5-1.5B | 16.69 | 378.3 | 1689.2 |
  | Gemma2-2B | 10.37 | 598.4 | 2779.2 |
  | Phi3-3.8B | 7.45 | 1017.3 | 3758.3 |
  | ChatGLM3-6B | 4.98 | 1352.9 | 5986.0 |

  （seqlen=128, new_tokens=64；RK3588 仅 **W8A8**；W4A16 只出现在 RK3576 表。）
- **NPU vs CPU 第三方对照**（[Turing Pi RKLLM 实测](https://turingpi.com/rkllm-rk3588-npu-llm-inference-turing-pi-rk1/)，2026-08，RKLLM 1.3.0 + 驱动 0.9.7）：同模型 W8A8 NPU 与 Q4_K_M CPU 不是同精度、不能直接比；部署上 NPU 必须先用 x86 Linux 上的 Toolkit 转成硬件专属 `.rkllm`，不能直接吃 GGUF。该文实测 Qwen2.5-1.5B/3B，结论是 NPU 路径转换与兼容性成本显著。

### 3.4 NPU 对动态结构 / KV 操作的限制
综合 llm.npu 论文（§2.2/2.3）与 RKNN/RKLLM 工具链现状：
1. **静态图 / 静态 shape**：变长输入要重新 build+optimize 图（QNN 上 Gemma-2B 图优化 11.54 s）；RKNN 同样是转换期固定 shape/图结构的部署模型（`.rknn`/`.rkllm`），运行时不能改图。
2. **不支持 per-group（分组）量化 MatMul**：AWQ/GPTQ 的分组低比特要拆子矩阵+浮点归约，开销 8.1–10.7×；这导致 INT4 权重在 NPU 上难高效（RK3588 RKLLM 只开放 W8A8）。
3. **浮点能力弱**：FP16 MatMul 比 INT8 慢百倍量级；LayerNorm/softmax/Attention 等浮点算子必须留在 CPU/GPU，形成跨处理器关键路径。
4. **算子不支持即回退 CPU**：NPU 工具链对不支持的算子采用 CPU 回退，频繁回退+同步会吃掉 offload 收益（llm.npu 的 out-of-order 调度与 NPU 测量论文 §insight 3 均指出同步/线程配置不当可造成 40% 能耗浪费）。
5. **自定义算子困难**：NPU SDK 闭源（llm.npu §2.2 明确 "closed-source nature of NPU SDKs"），动态 KV 驱逐/换页/稀疏 gather 这类数据相关操作无法表达成静态 NPU 图，只能在 CPU 侧做。
- 一句话：**RK3588 NPU 是为规则、稠密、静态、整型的 CNN/前馈计算设计的；LLM 中数据相关、动态、低比特分组、需要 gather/scatter 的 KV 操作基本落在 CPU/DRAM 上。**

## 4. 研究空白：6–9 个月可出原型的选题（挂先行论文）

> 评估标准：能在 RK3588（+可选 Artix-7/BlueField）上做出端到端可测原型，评测维度含延迟/吞吐/能耗/精度，且目前无直接竞品。

1. **NPU 友好的 KV 换页协同调度器**：现有 KVSwap（SenSys'25）只做磁盘换页、llm.npu（ASPLOS'25）只优化 prefill offload，二者未结合。做"NPU 跑静态 chunk 线性层的同时，CPU 异步预取/量化下一批 KV"的联合调度，消除 I/O 与 NPU 气泡。先行：KVSwap、llm.npu、APEX。
2. **Per-group 量化的 NPU 高效映射**：llm.npu 测出分组 MatMul 8.1–10.7× 开销；可用"通道重排+离群值 shadow + 子矩阵静态批量"把 INT4/AWQ 映射到 RK3588 NPU，目标让 RK3588 也能高效跑 INT4（目前仅 W8A8）。先行：llm.npu、AWQ、SmoothQuant。
3. **预测式 KV 三级（SRAM/DRAM/UFS）放置**：TierKV（2026）用 prefill hidden state 预测分层，但未针对 RK3588 的 UFS/NVMe 真实延迟与 NPU 带宽墙做 co-design。在 RK3588 上实测各层延迟、训练轻量预测器、闭式/贪心放置。先行：TierKV、InfiniGen、mzCache。
4. **端侧长上下文 KV 驱逐 + 云回补**：H2O/StreamingLLM 驱逐不可逆；设计"边缘驱逐但保留低秩摘要/布隆索引，命中失败时向边缘服务器/云端按需回补精确 KV"，兼顾容量与召回。先行：H2O、StreamingLLM、CE-CoLLM、Pensieve（总库#18）。
5. **边缘小模型起草 + NPU prefill 的通信高效协同**：SpecEdge 的边缘起草在 GPU 上；把 draft 模型放到 RK3588 NPU（静态、短 draft）、云端验证，只传 token，并随真实网络 RTT 自适应 draft 深度。先行：SpecEdge、PowerInfer-2、CE-CoLLM。
6. **多 RK3588/手机分布式 KV 切分（非层切分）**：LinguaLinked 做模型分片；改为按** KV/注意力头**切分以匹配每设备带宽，配合 Wi-Fi 带宽预测做运行时再均衡，避免层切分每 token 通信（SpecEdge 测其慢 2.35×）。先行：LinguaLinked、SpecEdge。
7. **BitNet b1.58 在 RK3588 的 kernel 与 KV 协同**：现有 1.58-bit 边缘工作多为 FPGA/专用架构（总库 TeLLMe/TENET），RK3588 上缺高效三值 GEMV kernel；用 A76 NEON/ Mali GPU 做三值 kernel 并联合 KV 量化，给出首组 RK3588 1.58-bit 实测能效。先行：BitNet b1.58、TeLLMe、KIVI。
8. **多任务/后台抢占下的 LLM 内存弹性**：mzCache（MobiCom'26）刚提出该问题但基于手机 GPU；在 RK3588 Linux + NPU 上做权重/KV 的细粒度驱逐-恢复，量化"后台 App 切换/并发推理"对 TTFT 的影响。先行：mzCache、Pensieve。
9. **能耗感知的 prefill/decode 后端动态切换**：NPU 强 prefill、CPU 强 decode（Is Your NPU Ready 2026 的核心测量），但没有运行时按温度/频率/请求长度自动切后端的系统；做在线 profiling + DVFS/后端切换策略（目标 30%+ 省能）。先行：Is Your NPU Ready、Hydra、PELM（[arXiv:2609.09662](https://arxiv.org/abs/2609.09662)，待核实）。
10. **BlueField DPU 做边缘 KV/预处理卸载**（结合学生独有硬件）：把 tokenization、KV 量化/反量化、前缀 KV 存取或 RAG 检索卸载到 DPU，主机 SoC 只做核心 GEMM；智能网卡数据面卸载有 iPipe/LineFS 先例（总库#32/#33），LLM 场景尚无公开工作。先行：iPipe、LineFS、Blink（总库#34）、KIVI。

### 投稿匹配建议
- 系统实现强、含 NPU/能耗实测：MobiQuitous、ICPADS、ICPADS/ICPP、SEC；冲 MobiSys/SenSys/边缘 track。
- 软硬协同/编译器/硬件：TCAD、TC（需更深入架构）、ICCD/ICCAD 类。
- 分布式/云边协同：TPDS、ICWS、边缘 Computing 期刊。
- 期刊扩展版：IoT-J、TMC（需真实部署+用户研究）、TPDS。

## 5. 实际验证过的链接清单（本次逐一打开/检索确认）
1. https://arxiv.org/abs/2407.05858 — llm.npu/Panda，ASPLOS'25（ar5iv 全文已读）
2. https://doi.org/10.1145/3669940.3707239 — 同文 DOI
3. https://arxiv.org/abs/2312.12456 — PowerInfer，SOSP'24
4. https://arxiv.org/abs/2406.06282 — PowerInfer-2
5. https://arxiv.org/abs/2310.17752 — PockEngine，MICRO'23
6. https://arxiv.org/abs/2407.21325 — EdgeLLM CPU-FPGA，TCAS-I
7. https://arxiv.org/abs/2002.12418 — MNN，MLSys'20
8. https://arxiv.org/abs/2412.15803 — WebLLM
9. https://arxiv.org/abs/2402.02750 — KIVI，ICML'24
10. https://arxiv.org/abs/2306.14048 — H2O，NeurIPS'23
11. https://arxiv.org/abs/2309.17453 — StreamingLLM，ICLR'24
12. https://arxiv.org/abs/2404.14469 — SnapKV，NeurIPS'24
13. https://arxiv.org/abs/2406.02069 — PyramidKV
14. https://arxiv.org/abs/2406.19707 — InfiniGen，OSDI'24
15. https://arxiv.org/abs/2310.19102 — Atom，MLSys'24
16. https://doi.org/10.1145/3745756.3809234 — KVSwap，SenSys'25（ACM DL）
17. https://arxiv.org/abs/2609.01338 — mzCache，MobiCom'26
18. https://arxiv.org/abs/2609.21172 — TierKV
19. https://arxiv.org/abs/2512.03608 — KVNAND
20. https://arxiv.org/abs/2607.05475 — Is Your NPU Ready for LLMs
21. https://arxiv.org/abs/2506.03296 — APEX
22. https://arxiv.org/abs/2411.02829 — CE-CoLLM，ICWS'25
23. https://arxiv.org/abs/2505.17052 — SpecEdge，NeurIPS'25
24. https://doi.org/10.18653/v1/2024.acl-demos.16 — LinguaLinked，ACL'24 Demos
25. https://arxiv.org/abs/2608.25053 — Hydra，IISWC'26
26. https://arxiv.org/abs/2210.17323 — GPTQ
27. https://arxiv.org/abs/2306.00978 — AWQ
28. https://arxiv.org/abs/2211.10438 — SmoothQuant
29. https://arxiv.org/abs/2402.17764 — BitNet b1.58
30. https://turingpi.com/rk1-benchmarks/ — RK3588 带宽/功耗/温度实测
31. https://turingpi.com/llm-inference-benchmarks-rk3588-gguf-quantization/ — CPU llama-bench 16 组实测
32. https://turingpi.com/rkllm-rk3588-npu-llm-inference-turing-pi-rk1/ — NPU RKLLM 实测
33. https://gist.github.com/RadxaStephen/88b6a5e09699017d04a2299192104232 — Radxa tinymembench LPDDR5/LPDDR4X 实测
34. https://github.com/airockchip/rknn-llm/blob/release-v1.3.0/benchmark.md — RKLLM 官方性能表

## 6. 待核实 / 局限
- **引用数**：仅 MNN/H2O/StreamingLLM/SnapKV/PyramidKV/InfiniGen/Atom/GPTQ/AWQ/SmoothQuant/BitNet 拿到 S2 快照（调研期间 S2 无 key 持续 429）；其余标注"待核实"，需配置 `S2_API_KEY` 后批量回填。
- **未证实系统名**：SiliFry、ELIA、NPU 语境 LazyCtrl、Flipusta、手机 LLM 语境 Centauri 全网无可靠记录，不引用。
- llama.cpp、MLC-LLM 是 GitHub 项目而非论文，引用时应引用其项目页/相关技术报告（WebLLM）。
- RKLLM 1.3.0 为 2026 现行版本；官方数字随版本变化，投稿前需在本人板子上复现全部基线。

## 7. 下次继续
- [ ] 配 S2 key 回填引用数 + 拉 llm.npu/PowerInfer-2 的引用网络
- [ ] 在 RK3588 上复现 Qwen2.5-1.5B（CPU Q4_K_M 与 NPU W8A8）建立自有基线
- [ ] 深读 KVSwap 全文（SenSys'25 ACM PDF）确认低秩摘要与 rolling buffer 细节
