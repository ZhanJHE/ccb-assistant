# 选题 B：基于 XDP/eBPF 的 KV 感知负载均衡与轻量遥测（eBPF-KVEdge）

> 三件套：初步计划 + 文献调研 + 可行性。创建：2026-09-26。
> 暂定英文标题：*KV-Aware Request Steering and Lightweight Telemetry with XDP/eBPF for Disaggregated LLM Serving*

## 一、研究背景与动机

LLM serving 集群前端通常需要一个 L4/L7 负载均衡器（LB）决定每个请求路由到哪个 decode 实例。传统 LB 只看负载/连接数，**不感知"哪个实例已缓存该请求的前缀 KV"**，导致大量本可命中的 KV 被迫重算或迁移（Llumnix 的动态迁移、Mooncake 的全局池都在主机/GPU 侧解决）。

问题：把"KV 位置感知"做进前置 LB 需要在数据面解析请求、查询 KV 索引、并以线速转发——用专用硬件贵，用 iptables/IPVS 等内核方案表达能力弱、不可编程。**eBPF/XDP 恰好提供"内核内、安全、可热加载、接近线速"的可编程数据面**，在生产 LB（Facebook Katran）中已被验证，但还没有被用于"KV 感知的 LLM 请求调度"。

**核心论点**：在前置服务器/每台主机的 XDP 钩子中，用紧凑的 KV 位置摘要（Bloom filter/sketch）做一次查询即可把请求导向"已有前缀 KV"的 decode 实例，同时用 eBPF map 导出每请求/每实例的细粒度遥测，零额外探针开销。

## 二、文献调研（均已核实）

### eBPF / XDP 负载均衡奠基
- **Katran**（Facebook/Meta，开源 L4 LB，[GitHub facebookincubator/katran](https://github.com/facebookincubator/katran)；工程博客）：基于 XDP + consistent hashing 的高可用 LB，支撑海量生产流量。**无学术论文，引仓库/官方博客**——XDP 做 LB 的权威工程证据。
- **Cilium**（开源，eBPF 网络与安全、K8s CNI，[官方文档](https://cilium.io/)）：eBPF 数据面 + service mesh，可作集成基座。
- **An Application Perspective on (e)BPF**（Hoven R., et al.，说法为 ACM SIGCOMM CCR 2021）：**待核实，暂不引用**——原引 DOI `10.1145/3471469.3471471` 经 Crossref 解析为 *The Book Review Column*（ACM SIGACT News），与 eBPF 无关；该标题在 Crossref 与 Semantic Scholar 均未命中（2026-09-27 核查）。
- XDP 综述/原理：内核社区 XDP 资料（[LPC XDP talk](http://vger.kernel.org/lpc_net2018_talks/LPC_XDP_Shirokov_v2.pdf)）；XDP 三返回模式 XDP_TX/REDIRECT/PASS。

### eBPF 存储/系统协同（证明内核钩子可承载复杂逻辑）
- **XRP: In-Kernel Storage Functions with eBPF**（Zhong Y., et al., OSDI 2022，[USENIX](https://www.usenix.org/conference/osdi22/presentation/zhong)）：在 NVMe 驱动内用 eBPF 做存储函数、跨应用-内核零上下文切换——本选题"内核内 KV 查询"最直接的方法学先行。
- **eBPF-Based System Instrumentation**（2025，系统可观测性，原引 ACM DOI `10.1145/3748355`）：**待核实**——该 DOI 经 Crossref 解析为 *Proceedings of the 3rd Workshop on eBPF and Kernel Extensions* 论文集页，并非单篇论文；需要具体插桩论文时另行检索。

### LLM 调度侧（差异化对象）
- **Llumnix**（OSDI 2024，[arXiv:2406.03243](https://arxiv.org/abs/2406.03243)）：动态调度 + KV live migration（主机侧）。
- **Mooncake** [arXiv:2407.00079](https://arxiv.org/abs/2407.00079)：全局 KV 池 + transfer engine。
- **Monic**（INFOCOM 2026，导师组）：交换机上算 MoE（compute），本选题是主机/服务器内"网络辅助"，正交。

**空白结论**：截至 2026-09，**XDP/eBPF 做"KV 位置感知请求路由 + 遥测"无专门论文**。动手前再扫 arXiv/USENIX 确认。

## 三、研究问题与创新点

1. **XDP KV-aware steering**：解析请求标识（连接建立时在 SOCK_OPS/cgroup 钩子绑定 prompt 前缀哈希；XDP 收包时查 eBPF map 中的"前缀→实例"摘要），一次哈希/Bloom 查询选择命中实例并 XDP_REDIRECT，绕过内核 socket 栈。
2. **紧凑 KV 位置索引**：decode 实例把新增/驱逐 KV 的前缀指纹以 Bloom filter/counting sketch 形式同步到 LB map（数据面可容纳百万级前缀）；冲突率与误路由率建模。
3. **负载 × 命中联合决策**：当多个实例都有前缀时，结合 eBPF 维护的实时队列/配额（per-cpu map）选最优；无命中时走 least-loaded。
4. **零开销遥测**：用 ringbuf/perf-event + BPF map 聚合导出每请求 TTFT 分段、命中/重算、实例负载，供调度器闭环（替代独立 sidecar 探针）。
5. 给出 eBPF/XDP 与 IPVS、用户态 LB（DPDK 选题 A）、P4 交换机（选题 3）的**能力-成本对比**。

## 四、技术方案

```
客户端请求
  → cgroup/connect 钩子：关联会话/prompt 前缀指纹 fp
  → XDP ingress：
       查 Bloom/sketch map（fp→decode 实例集合）
       结合负载 map 选实例 → XDP_REDIRECT（同主机/邻主机）
       未命中 → least-loaded 兜底
decode 实例（用户态）：
  KV 变化 → 更新前缀指纹 map（BPF_MAP 批量更新）
遥测：XDP/socket 钩子计数 → ringbuf → 用户态采集
```
- 数据面限制处理：eBPF 程序有指令上限（旧 4096 条，现 1M 经许可）、map 类型受限；复杂决策拆 tail-call 多程序串联。
- 部署形态：①独立 LB 节点（XDP）；②每主机 sidecar 式 BPF（分布式一致决策）。两形态对比。

## 五、初步计划（8 个月）

| 阶段 | 时间 | 内容 | 交付 |
|---|---|---|---|
| P0 | 10 月 | eBPF/XDP 环境、Katran/Cilium 源码研读、toy LB | XDP 转发 demo |
| P1 | 11 月 | 前缀指纹 map + Bloom 查询 + redirect | KV-aware steering 原型（trace 输入） |
| P2 | 12 月 | 负载联合决策 + 误路由/冲突建模 | 仿真评估（命中率） |
| P3 | 1-2 月 | 遥测 ringbuf 闭环 + 与 vLLM 前端对接 | 端到端原型 |
| P4 | 3 月 | 真机压测（无 GPU 时用 stub 服务 + trace 时序）；对比 IPVS | 完整数据 |
| P5 | 4 月 | 写作投稿 | 投稿 |

## 六、可行性分析

### 条件
- **零硬件成本**：任意 Linux 主机即可（内核 ≥5.x 支持较新 BPF 特性）；CO-RE（一次编译到处运行）+ libbpf-go/libbpf。
- **技能匹配**：C（BPF 程序）+ Python/Go（用户态），你有 Linux 与 KV 语义基础；eBPF 学习曲线中等但资料极多。
- 导师方向（智能网络）相关，易获指导；Katran 提供大量可复用模式。

### 风险与对策
| 风险 | 等级 | 对策 |
|---|---|---|
| eBPF 数据面无法解析加密/应用层 prompt 来识别前缀 | 中高 | 在**建连/认证后的可控握手点**绑定前缀指纹（由客户端/网关计算哈希），不在 XDP 解析正文 |
| Bloom 误判导致错误路由 | 中 | 用 counting Bloom + 实例侧二次校验，误判即回退；报告误判-内存曲线 |
| 生产 LB 已有成熟方案，增量被质疑 | 中 | 增量明确是"KV 感知 + 遥测"，非通用 LB；用命中率/TTFT 数据说话 |
| 内核版本/验证器（verifier）限制 | 中 | 固定内核版本 + CO-RE；复杂逻辑 tail-call 拆分 |
| 纯软件天花板 | 低 | 后期可在 Tofino/DPU 补一小节，或与选题 3 合流 |

### 目标场馆
- **CCF-B 会议**：CoNEXT、ICNP、IWQoS、ICDCS、Euro-Par；**CCF-B 期刊**：Computer Networks、TNSM、ACM TOS。
- 系统+网络测量味浓 → CoNEXT/ICNP/Computer Networks 最对口。

## 七、参考文献（真实可点击）
- Katran：[GitHub](https://github.com/facebookincubator/katran)
- Cilium：[cilium.io](https://cilium.io/)
- eBPF 应用综述（CCR 2021 说法）：**待核实**——原引 DOI `10.1145/3471469.3471471` 经 Crossref 解析为 *The Book Review Column*（ACM SIGACT News），与 eBPF 无关；标题在 Crossref / Semantic Scholar 均未命中，确认前不引用
- XRP, OSDI 2022：[USENIX](https://www.usenix.org/conference/osdi22/presentation/zhong)
- Llumnix, OSDI 2024：[arXiv:2406.03243](https://arxiv.org/abs/2406.03243)
- Mooncake：[arXiv:2407.00079](https://arxiv.org/abs/2407.00079)
- eBPF 系统插桩：**待核实**——原引 ACM DOI `10.1145/3748355` 经 Crossref 解析为 *Proceedings of the 3rd Workshop on eBPF and Kernel Extensions*（论文集页），非单篇论文
