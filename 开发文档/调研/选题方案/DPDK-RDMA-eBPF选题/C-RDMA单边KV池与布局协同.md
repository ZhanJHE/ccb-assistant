# 选题 C：RDMA 单边操作的 KV 池与布局协同（OneS-KV）

> 三件套：初步计划 + 文献调研 + 可行性。创建：2026-09-26。
> 暂定英文标题：*OneS-KV: One-Sided RDMA KV Pool with Semantic-Aware Layout for Disaggregated LLM Serving*

## 一、研究背景与动机

PD 分离 + 全局 KV 池（Mooncake、MemServe）让 decode 节点能跨节点取 KV。这些系统的 KV 取数多用：
- **双边消息（two-sided SEND/RECV）**：需要远端 CPU 参与处理每个请求，远端 CPU 成为瓶颈；
- 或 **单边 RDMA READ/WRITE（one-sided）**：远端 CPU 完全不参与，延迟低、可扩展性好，但要求**请求方事先知道数据在远端内存的精确地址与布局**。

矛盾点：LLM 的 KV 在压缩/驱逐/分页后布局是**动态、不规则**的（block 被打散、混精度、稀疏），单边 RDMA 的"固定地址直接取"与"动态布局"天然冲突——请求方需要多次 READ 先查索引再取数据（额外 RTT），或退化为双边让远端 CPU 帮忙。

**核心论点**：设计一种 **KV 语义感知的远端内存布局 + 轻量地址目录**，让 decode 节点用**最少的单边 READ 次数**（理想为 1 次 READ 取一整个逻辑 KV 连续段）直接取到动态 KV，既绕开远端 CPU，又不牺牲压缩/驱逐带来的容量收益。

## 二、文献调研（均已核实）

### RDMA 单边远程内存奠基
- **Pilaf**（Mitchell C., et al., *Using RDMA Efficiently for Key-Value Services*, SIGCOMM 2013，[DOI:10.1145/2486001.2486031](https://doi.org/10.1145/2486001.2486031)）：客户端用单边 READ 直查 KV，GET 完全绕开服务器 CPU——单边 KV 开山。
- **HERD**（Kalia A., et al., *Using RDMA Efficiently ... HERD*, SIGCOMM 2014；CMU 技术报告 [CMU-CS-19-126](http://reports-archive.adm.cs.cmu.edu/anon/anon/home/ftp/home/anon/usr/ftp/2019/CMU-CS-19-126.pdf)）：对比单边/双边设计空间，指出"WRITE + 服务端轮询"等最优组合。
- **FaRM**（Dragojević A., et al., *FaRM: Fast Remote Memory*, NSDI 2014；FaRM-KV 扩展）：单边 WRITE 实现的分布式内存与 KV。
- **IRN**（Kalia A., et al., *Revisiting Network Support for RDMA*, SIGCOMM 2018，[DOI:10.1145/3230543.3230557](https://doi.org/10.1145/3230543.3230557)）：证明可用更弱网络硬件（无无损以太网）实现 RDMA 语义——降低部署门槛，对本选题"普通网络可跑"是重要支撑。
- **FaSST**（Kalia A., et al., *FaSST: Fast, Scalable ... with RDMA*, SOSP 2016）：双边 RPC 在数据中心规模的极限性能（对照）。

### LLM KV 池侧（差异化对象）
- **Mooncake** [arXiv:2407.00079](https://arxiv.org/abs/2407.00079)：全局 KV 池，但以 transfer engine/双边高效搬运为主，未针对"纯单边 + 动态布局"做地址目录优化。
- **MemServe**（OSDI 2024，[arXiv:2406.17565](https://arxiv.org/abs/2406.17565)）：弹性分布式 KV 池。
- **InfiniGen**（OSDI 2024，[arXiv:2406.19707](https://arxiv.org/abs/2406.19707)）：动态 KV + 按需换入预测。
- **ShadowServe** [arXiv:2509.16857](https://arxiv.org/abs/2509.16857)：无干扰 KV 取数、最小拷贝（取数路径优化，可对标单边方案）。

**空白结论**：截至 2026-09，**"针对 LLM 动态/压缩 KV 的纯单边 RDMA 地址目录与布局"无专门论文**；经典 Pilaf/HERD 面向通用 KV（键值短小、PUT/GET 语义），未处理 LLM 大块、分层、混精度 KV。动手前再扫确认。

## 三、研究问题与创新点

1. **语义连续布局（semantic contiguous layout）**：在远端内存按"逻辑 KV 连续段"（同 layer/同 block 范围）放置，即使底层压缩也把相关 block 物理聚拢，使一次单边 READ 取一整段（减少 READ 次数→减少 RTT）。
2. **两级地址目录（directory）**：
   - 一级：版本化的紧凑元数据（逻辑段→{远端地址,长度,精度}），decode 节点一次小 READ 缓存到本地（目录变更用 RDMA WRITE 主动推送/版本号失效）；
   - 二级：物理 free 区管理（远端后台线程只做分配/回收，不参与取数热路径）。
3. **READ 合并/流水（read coalescing）**：把多个相邻小 READ 合并为一个大 READ（RDMA READ 对大消息更优，小 READ 受 RTT 主导）；跨 layer 的 READ 批量下发并行等待。
4. **混精度 KV 感知**：配合 SpectrumKV 式 INT4/INT8 布局，地址目录记录每段精度，单边取回后就地反量化（或交给选题 A/B/FPGA）。
5. 给出**单边 READ 方案 vs 双边（Mooncake/ShadowServe）的 CPU-延迟-RTT 解析模型**，并在高 RTT（跨数据中心）场景展示单边优势。

## 四、技术方案

```
Prefill 节点：生成 KV
  → 语义连续布局写入 KV 池节点（RDMA WRITE，按逻辑段聚拢）
  → 更新目录（WRITE 目录区 + 版本号）
Decode 节点：
  → 本地缓存目录（按需一次 READ 拉目录）
  → 计算所需逻辑段的物理地址 → 合并相邻段
  → 批量 RDMA READ（单边，远端 CPU 空闲）
  → 取回 GPU staging → attention
池节点后台：仅 free-list/GC，不进取数热路径
```
- 可靠性：RDMA READ 失败/版本失配 → 退回双边 RPC 兜底（保证正确性）。
- 无 RoCE 硬件时：用 **IRN 的软件 RDMA 思路 / Soft-RoCE（rxe）** 做功能开发与仿真；真机性能用租 RoCE 实例测得。

## 五、初步计划（8 个月）

| 阶段 | 时间 | 内容 | 交付 |
|---|---|---|---|
| P0 | 10 月 | RDMA(verbs) 环境、Soft-RoCE、复现 Pilaf 式单边 GET | 单边 READ 取数 demo |
| P1 | 11 月 | trace 驱动的 KV 布局/访问模型；测量 READ 大小×RTT 曲线 | 仿真器 |
| P2 | 12 月 | 语义连续布局 + 两级目录 + 版本失效 | 单边取数原型 |
| P3 | 1-2 月 | READ 合并/批量；混精度目录；与 vLLM 对接 | 端到端原型 |
| P4 | 3 月 | 租 RoCE 双机真机测；对比双边 Mooncake | 完整评估 |
| P5 | 4 月 | 写作投稿 | 投稿 |

## 六、可行性分析

### 条件
- **技能匹配**：C（libibverbs）、你懂 KV block 与访问模式；RDMA 编程有学习曲线但 Pilaf/HERD/FaRM 提供清晰范式与大量开源代码（如 eRPC/HERD 仓库）。
- **硬件**：开发用 Soft-RoCE（零成本，任意 Linux）；真机性能短期租云 RoCE 实例（1-2 周，预算内）；实验室 BlueField 本身就是 RDMA 网卡（免费，可作端点）。
- IRN 论文背书"普通以太网可实现 RDMA"，降低被质疑"必须 InfiniBand"。

### 风险与对策
| 风险 | 等级 | 对策 |
|---|---|---|
| RDMA verbs 编程复杂、调试难 | 中 | 先基于开源 eRPC/rdma-core 示例；P0 快速验证 |
| Soft-RoCE 性能不能代表真机 | 中 | 性能结论只来自租来的 RoCE 真机；Soft-RoCE 仅做功能 |
| 动态布局下一 READ 理想难以达到 | 中 | 以"READ 次数最小化"为优化目标给出上界/实测；达不到 1 次也显著优于逐条 READ |
| 远端仍需后台线程，"完全无 CPU"被质疑 | 低 | 明确区分：后台只做低频 GC，热取数零远端 CPU |
| Mooncake 后续增强单边支持 | 低中 | 贡献聚焦"语义布局 + 目录"，非传输引擎本身 |

### 目标场馆
- **CCF-B 会议**：ICDCS、ICPP、Euro-Par、ICNP；**CCF-B 期刊**：Computer Networks、TNSM、ACM TOS、TCC。
- 强分布式系统 + 协议味 → ICDCS/Computer Networks/TOS 对口。

## 七、参考文献（真实可点击）
- Pilaf, SIGCOMM 2013：[DOI:10.1145/2486001.2486031](https://doi.org/10.1145/2486001.2486031)
- HERD（技术报告）：[CMU-CS-19-126](http://reports-archive.adm.cs.cmu.edu/anon/anon/home/ftp/home/anon/usr/ftp/2019/CMU-CS-19-126.pdf)
- FaRM, NSDI 2014：[USENIX](https://www.usenix.org/conference/nsdi14/technical-sessions/dragojevi%C4%87)
- IRN, SIGCOMM 2018：[DOI:10.1145/3230543.3230557](https://doi.org/10.1145/3230543.3230557)
- FaSST, **OSDI 2016**（原稿误记为 SOSP'16，已核实）：[USENIX](https://www.usenix.org/conference/osdi16/technical-sessions/presentation/kalia)
- Mooncake：[arXiv:2407.00079](https://arxiv.org/abs/2407.00079)
- MemServe：[arXiv:2406.17565](https://arxiv.org/abs/2406.17565)
- InfiniGen：[arXiv:2406.19707](https://arxiv.org/abs/2406.19707)
- ShadowServe：[arXiv:2509.16857](https://arxiv.org/abs/2509.16857)
