# 选题 D：eBPF 内核级 KV 换页与计算协同调度（CoSched-BPF）

> 三件套：初步计划 + 文献调研 + 可行性。创建：2026-09-26。
> 暂定英文标题：*CoSched-BPF: In-Kernel Coordination of KV-Cache Swapping and LLM Computation with eBPF*

## 一、研究背景与动机

LLM serving 中，KV Cache 的换页（GPU↔CPU DRAM↔SSD）与 GPU 计算（prefill/decode）必须精确协调：换早了浪费 I/O，换晚了 GPU 空等；而调度决策通常散落在**用户态运行时（vLLM/SGLang）**里。问题在于——

- 真正的 I/O 事件（NVMe 完成、缺页、DMA 结束）首先发生在**内核**，用户态要通过系统调用/中断/轮询才能感知，存在上下文切换与唤醒延迟；
- GPU 任务派发与 KV 换页是两套异步链，靠用户态粗粒度同步，容易出现"KV 还没到 GPU 就开始 attention"或"GPU 已算完 KV 还占着位"。

**核心论点**：把"KV 换页决策 + 计算触发"下沉到内核中靠近 NVMe/内存/驱动的 eBPF 钩子，在内核内完成"I/O 完成 → 就地更新 KV 有效性 → 直接触发设备任务/唤醒"的短闭环，消除用户态-内核的往返延迟，让 KV I/O 与 GPU 计算更紧地重叠。

## 二、文献调研（均已核实）

### eBPF 内核内存储/调度先行
- **XRP: In-Kernel Storage Functions with eBPF**（Zhong Y., et al., OSDI 2022，[USENIX](https://www.usenix.org/conference/osdi22/presentation/zhong)）：NVMe 驱动内 eBPF 函数，应用发起 I/O 后**无上下文切换**即在内核完成索引/聚合。**本选题最直接的方法学基础**。
- **sched_ext（SCX）**：Linux 内核 6.12 合入的 **BPF 可编程 CPU 调度类**（[kernel 文档 sched-ext](https://github.com/sched-ext/scx)；LPC 2025 报告）。证明 eBPF 可承载**核心调度决策**——为本选题"内核内调度 KV/计算"提供官方机制。注意：sched_ext 调度的是 CPU 任务（含 vLLM worker 线程），不直接驱动 GPU，但可编排 worker/换页线程的唤醒顺序。
- **FlexGMalloc / XRP 系列**（2022 起）：BPF 辅助的用户态-内核快速内存/IO 路径。
- eBPF 系统插桩（原引 ACM DOI `10.1145/3748355`）：**待核实**——该 DOI 经 Crossref 解析为 *Proceedings of the 3rd Workshop on eBPF and Kernel Extensions*（会议论文集页），并非单篇论文；需要具体插桩论文时另行检索。

### LLM KV 换页侧（差异化对象）
- **Pensieve**（OSDI 2024，[arXiv:2312.05516](https://arxiv.org/abs/2312.05516)）：会话 KV 换出 CPU/SSD（用户态决策）。
- **APEX**（[arXiv:2506.03296](https://arxiv.org/abs/2506.03296)）：KV/部分 attention offload CPU + 预测式调度最大化重叠——与本选题"计算-IO 重叠"目标相近，但 APEX 是**用户态预测调度**，本选题是**内核事件驱动短闭环**，差异清晰。
- **InfiniGen**（OSDI 2024，[arXiv:2406.19707](https://arxiv.org/abs/2406.19707)）：按需换入预测。
- **Llumnix**（OSDI 2024，[arXiv:2406.03243](https://arxiv.org/abs/2406.03243)）。

**空白结论**：截至 2026-09，**"用内核 eBPF 钩子做 KV 换页 × 设备计算的事件驱动协同"无专门论文**；XRP 面向通用存储函数（KVS/索引），未处理 LLM 的 GPU 计算时序与 KV 语义。动手前再扫确认。

## 三、研究问题与创新点

1. **内核内 KV 有效性状态机**：在 BPF map 中维护每个 KV block 的位置（GPU/DRAM/SSD）与就绪位；NVMe/IO 完成钩子（tracepoint/kprobe at `nvme_complete_rq` 类）就地更新，无需唤醒用户态。
2. **I/O 完成 → 计算触发短闭环**：KV 就绪后经 sched_ext/用户态快速通道（BPF ringbuf + io_uring 事件）精准唤醒对应 worker，缩短"最后一公里"延迟；对比纯用户态轮询的唤醒时延。
3. **换页 × 计算的紧耦合流水**：基于真实 I/O 完成时刻（而非预测均值）动态调整换入顺序，把 I/O 藏进 GPU compute；给出 overlap 解析模型。
4. **（亮点）sched_ext 编排**：用 BPF CPU 调度类对 prefill worker / 换页线程 / GPU 回调线程做优先级与核绑定，减少同步阻塞与优先级反转。
5. 内核态短闭环 vs 用户态预测调度（APEX）的**延迟/吞吐/CPU 对比与适用边界**。

## 四、技术方案

```
vLLM worker（用户态）
  → 发起 KV 换页请求（io_uring / NVMe passthrough）
内核：
  → NVMe 完成 tracepoint 上的 BPF 程序：
       更新 block 位置/就绪 map
       ringbuf 推送就绪事件（或直接唤醒 sched_ext 中的目标线程）
  → sched_ext BPF：按就绪集合调度 worker/换页线程
  → worker 被唤醒时所需 KV 已在内存/已触发 DMA → 计算
控制：精度/可靠性决策保留用户态，BPF 只做事件与触发（安全、可回退）
```
- 安全边界：BPF 不做不可逆驱逐决策（避免内核内 bug），只做"位置追踪 + 事件触发 + 线程编排"；策略可热卸载回纯用户态（对照/保底）。
- 无 GPU 时：用 stub 设备 + trace 时序模拟 GPU compute，验证内核闭环延迟（这恰是本选题核心可测项）。

## 五、初步计划（8 个月）

| 阶段 | 时间 | 内容 | 交付 |
|---|---|---|---|
| P0 | 10 月 | 新内核 + sched_ext 跑通；BPF tracepoint 抓 NVMe 完成 | IO 事件→ringbuf demo |
| P1 | 11 月 | KV block 状态机 map；换页 trace 驱动 | 状态追踪原型 |
| P2 | 12 月 | I/O 完成→唤醒短闭环；测唤醒延迟（对照用户态轮询） | 微基准 |
| P3 | 1-2 月 | sched_ext 编排 worker/换页线程；io_uring 集成；与 vLLM 对接 | 端到端原型 |
| P4 | 3 月 | trace + stub 真机全面评估；CPU/延迟/重叠率 | 完整数据 |
| P5 | 4 月 | 写作投稿 | 投稿 |

## 六、可行性分析

### 条件
- **零硬件成本**：较新内核 Linux PC + 一块 NVMe 即可；sched_ext 已进主线（6.12+），机制稳定。
- **技能匹配**：C（BPF）+ Python（vLLM），你有 KV 语义与 trace 经验；XRP/sched_ext 提供清晰范式。
- 核心可测指标（内核唤醒/闭环延迟、重叠率）**不依赖 GPU**，无 GPU 也能拿出扎实数据。

### 风险与对策
| 风险 | 等级 | 对策 |
|---|---|---|
| 内核钩子点随版本变化、不稳定（kprobe 符号变动） | 中 | 优先稳定 tracepoint/BTF + CO-RE；固定内核大版本 |
| sched_ext 不能直接驱动 GPU，收益被质疑 | 中 | 主张限定为"缩短 I/O→唤醒→派发链 + 线程编排"，实测该段延迟；不夸大为 GPU 调度 |
| 内核态调试复杂、verifier 限制 | 中 | BPF 只做事件/状态，复杂策略留用户态；增量迭代 |
| 收益可能只有几十~几百 μs，量级小 | 中 | 在高并发/低延迟 SLO 场景放大意义；同时报 CPU 与尾延收益 |
| 与 APEX 看似重叠 | 低中 | 显式区分"内核事件驱动"vs"用户态预测"，并做正面对比 |

### 目标场馆
- **CCF-B 会议**：CoNEXT、ICNP、ICDCS、ICPP、Euro-Par、APEX 类系统会议；**CCF-B 期刊**：Computer Networks、TNSM、ACM TOS、TCC。
- 内核机制 + 测量味浓 → CoNEXT/ICNP/TOS；偏调度 → ICDCS/Euro-Par。

## 七、参考文献（真实可点击）
- XRP, OSDI 2022：[USENIX](https://www.usenix.org/conference/osdi22/presentation/zhong)
- sched_ext：[scx 仓库/文档](https://github.com/sched-ext/scx)
- Pensieve, OSDI 2024：[arXiv:2312.05516](https://arxiv.org/abs/2312.05516)
- APEX：[arXiv:2506.03296](https://arxiv.org/abs/2506.03296)
- InfiniGen, OSDI 2024：[arXiv:2406.19707](https://arxiv.org/abs/2406.19707)
- Llumnix, OSDI 2024：[arXiv:2406.03243](https://arxiv.org/abs/2406.03243)
- eBPF 系统插桩：**待核实**（原引 ACM DOI `10.1145/3748355` 实为 *Proceedings of the 3rd Workshop on eBPF and Kernel Extensions* 论文集页，非单篇论文）
