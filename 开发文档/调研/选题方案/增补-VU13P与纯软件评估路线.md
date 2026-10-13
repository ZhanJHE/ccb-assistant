# 增补：VU13P 大卡 + Mininet 纯软件评估路线（约束更新后的选题重排）

> 创建：2026-09-26。本文更新《毕设选题建议.md》《选题2与选题4详细分析.md》中的两处前提：
> ① 实验室新增 **XCVU13P 超大 FPGA**；② 导师组 CCF-B 期刊接受 **Mininet 民用 PC 仿真**的评估方法（Fine-grained HTTP/3 Prioritization, COMNET 2023, [DOI:10.1016/j.comnet.2023.109880](https://doi.org/10.1016/j.comnet.2023.109880)）。
>
> **待核实（2026-09-27 加注）**：② 的说法本轮核查**只部分成立**。可核实的是该文用 `quic-go` **真实协议实现** + 端到端应用层指标（FCP 降 3.1–21.0%、PLT 降 5.3–23.7%）+ 与 HTTP/3 默认 Round-Robin 对比；**"Mininet + 一台民用 PC"这一平台定性未能核实**（ScienceDirect 与 ACM DL 均 403，未见 OA 副本）。因此：先例支持"真实协议实现 + 端到端指标"可发 COMNET，**但不足以证明"纯仿真可发"**——3S 路线的可行性论证需另找证据（如 TCC'26 TORTA、TCC'25 RAMPA、TNSM'26 CoInfer 三篇纯仿真论文，见《A-可行性五问答复.md》Q4）。

## 1. 两个新事实

### 1.1 VU13P 能力画像（AMD 官方 DS923/产品页）
| 资源 | XCVU13P | 对比 U280（FlightLLM 平台） |
|---|---|---|
| System logic cells | 3,780,000 | ~1.3M（约 2.9×） |
| LUT（约） | 1,303,680 | ~1.3M（相当） |
| DSP48/Slices | **12,288** | 9,024（**1.36×**） |
| 片上存储 | **455 Mb ≈ 57 MB**（BRAM + UltraRAM） | U280 片上约 38Mb BRAM，主要靠 HBM |
| 外部存储 | **板载 DDR4（开发板形态，无 HBM）** | **HBM2 ≈ 460 GB/s** |
| 主机接口 | PCIe Gen3 x16 | PCIe Gen3 x16 |

**关键架构洞察**：VU13P 是"**算力/片上内存极强、外部带宽弱**"的器件，与 U280"靠 HBM 喂算力"恰好相反。它最独特的能力是 **≈57 MB 片上存储**——足以把**大批并发 decode 请求的 KV Cache 常驻片上**（正是 FlightLLM "always-on-chip decode" 思想，但容量大一个数量级），从而**绕开 DDR4 外部带宽短板**。

### 1.2 纯软件评估路线（已被导师自己的 CCF-B 论文验证）
HTTP/3 那篇的范式：
```
Minitnet（民用 PC）= 网络拓扑/带宽/RTT/丢包仿真（namespace + veth）
  + 真实协议代码（QUIC 实现）跑在 namespace 里
  → 测到的是"真实代码在仿真网络条件下"的行为
```
迁移到 LLM serving 的对应范式（本文建议）：
```
Mininet/bmv2（民用 PC，零成本）
  + 真实调度/KV 管理代码（vLLM/SGLang 的策略层，或自写调度器）
  + GPU 计算时序用 trace 参数建模（来自你已收集的 vLLM trace / 论文公开 timing）
  → 测真实系统逻辑在仿真分离式拓扑下的命中率/迁移量/TTFT/p99
```
**适用边界（诚实）**：适合评估**调度、路由、换页、缓存策略、传输协议**等系统逻辑；不适合声称"绝对推理算力/某模型真实 t/s"——后者需真机 GPU，但可作为论文中占比很小的补充验证（短期租卡）。

## 2. 选题重排（新约束下）

| 新版选题 | 与旧版关系 | 评估方式 | 花钱 | 推荐度 |
|---|---|---|---|---|
| **2+：VU13P KV-Centric 加速器**（片上 KV 池 + 压缩/管理/attention） | 选题 2 升级 | FPGA 实测 + trace 端到端 | 少（可几乎不租卡） | ★★★★★ |
| **3S：Mininet 上的交换机辅助 KV 调度** | 选题 3 软件化 | Mininet+bmv2+trace，民用 PC | **0** | ★★★★★ |
| 5S：纯软件 learned 多动作调度器 | 选题 5 去 GPU 化 | trace-driven + CPU 小模型 | 0 | ★★★★ |
| 4：RK3588 EdgeKV（不变） | — | 真机免费 | 0 | ★★★★ |

## 3. 新版选题 2+：VU13P KV-Centric 加速器（详细）

**暂定标题**：*OnChip-KV: Exploiting Massive On-Chip Memory for KV-Cache-Centric LLM Decode Acceleration on FPGA*

### 为什么现在成立且更强
- 旧选题 2 的两大死穴（35T 算力不足、100M 平台被质疑）**全部消失**：VU13P 算力 U280 级，PCIe 直连主机。
- 不必复刻 FlightLLM 的完整 mapping flow（工作量过大），而是**聚焦其最有价值的设计点并做到极致**：把 KV Cache 作为一等公民，利用 **57 MB 片上存储**做大规模 on-chip KV 池。

### 三个贡献（scope 可控）
1. **On-chip KV 池微结构**：BRAM/UltraRAM 分级组织，支持多并发请求 decode 的 KV 全片上驻留 + block 级动态分配/回收（DDR4 只在上下文超长时兜底）。
2. **片上 KV 算子**：低比特 KV 压缩（对接 KIVI 式 INT4/2-bit）、驱逐选择（可融入你的 learned predictor 的整数版）、gather/重排全在片上完成，零外部流量。
3. **与 vLLM 的 PCIe 集成**：作为 decode 加速器，host 侧经 KV Offloading Connector（vLLM 2026-01 官方接口）对接。

### 可行性
- **资源充裕**：12,288 DSP + 57MB 片上，即使 0.5-1B 量化模型部分层也能上片；建议先支持 Qwen2.5-0.5B/1.5B（INT4/稀疏）做端到端，7B 用 trace+时序外推。
- **风险**：① 工程量比协处理器大 → 用"**KV 子系统优先、GEMM 复用开源 IP/简化数据宽度**"控制 scope；② DDR4 带宽弱 → 这正是"片上 KV 池"故事的动机，弱点转化为卖点；③ UltraRAM 开发经验 → 预留学习时间，UltraRAM 用法接近 BRAM。
- 场馆：**FPGA（CCF-B）**、ICCD/DATE；期刊 **TACO/TOS**。平台不再被质疑后，FPGA 会议成为现实目标。

## 4. 新版选题 3S：Mininet 交换机辅助 KV 调度（零成本、最贴导师方法论）

**暂定标题**：*KVAssist: Switch-Assisted KV Routing and Prefetch Scheduling for Disaggregated LLM Serving — A Mininet Emulation Study*

### 方法（完全复刻导师 COMNET 论文的被接受路径）
- **bmv2 软件交换机 + Mininet** 构建 PD 分离拓扑（多 prefill/decode 节点、可配带宽/RTL/incast）；
- P4 程序实现 KV 位置摘要（sketch/Bloom 压缩表项）、KV-aware 转发、预取信号；
- 节点上跑**真实 Python 调度/KV 管理代码**，GPU 计算时间用 trace 时序参数代入；
- 输出：命中率、KV 迁移次数、网络字节、TTFT/p99（仿真）。

### 与 Monic/Quark 的差异（不变）
交换机不做模型计算，只做 KV 路由/摘要/遥测辅助——networking assist，正交。
**额外优势**：纯软件、零成本、迭代极快（改 P4/调度器分钟级重跑），8 个月时间非常宽裕，可做多组敏感性分析，论文完整度容易做高。导师对该方法学和 COMNET/TNSM 审稿口味有一手经验。

### 风险（诚实）
- 纯仿真的**天花板**：COMNET/TNSM 合适，但难再宣称系统实现贡献；若想升级，最后用 1-2 周租卡或在 Tofino 上补一小节真机验证即可显著增强说服力。
- bmv2 与 Tofino 资源模型有差异，论文需注明资源数字为模型估计。

## 5. 更新后的决策建议
1. **想做硬件、追求最强简历（FPGA + LLM 系统经验，硕士极吃香）**→ **选题 2+（VU13P）**。这是本次信息更新的最大赢家。
2. **想零成本、低风险、最贴导师成功路径，8 个月从容做完**→ **选题 3S（Mininet）**，后期可选补真机。
3. 两者还能合流：**先用 3S 的 Mininet 框架做系统设计与策略探索（1-2 个月），再把验证过的最佳设计落到 VU13P（2+）**——软件探路 + 硬件兑现，风险最低、故事最完整，是资源条件允许下的最优组合。
4. 租卡预算（1000-3000 元）从"必需"降级为"后期可选增强"，多数情况下甚至可以不花。
