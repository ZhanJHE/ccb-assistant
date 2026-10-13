# DPDK / RDMA / eBPF × LLM Serving 选题集（README）

> 创建：2026-09-26。围绕老师介绍的 **DPDK、RDMA、eBPF** 三大网络/内核技术，结合个人兴趣（KV Cache、offload），
> 设计 5 个可发 **CCF-B** 的毕设选题。每个选题一份独立报告，均含【初步计划 + 文献调研 + 可行性分析】。
> 所有引用论文均经 arXiv/DOI/USENIX 页面核实，不确定者已标"待核实"，未编造。

## 五个选题一览

| 文件 | 技术栈 | 一句话 | 主要场馆（CCF-B） | 成本 |
|---|---|---|---|---|
| [A-DPDK用户态KV传输引擎](../../实验项目/选题A-DPDK-KV传输实验/docs/A-DPDK用户态KV传输引擎.md) **（已立项）** | DPDK | 普通网卡下内核旁路、零拷贝传 KV，逼近 RDMA 的 CPU 效率 | Computer Networks / TCC / ICDCS | 低（普通网卡+短期租 RoCE） |
| [B-eBPF的KV感知负载均衡与遥测](B-eBPF的KV感知负载均衡与遥测.md) | XDP/eBPF | 内核内一次查询把请求导向"已有前缀 KV"的实例 + 零开销遥测 | CoNEXT / ICNP / Computer Networks | **零**（任意 Linux） |
| [C-RDMA单边KV池与布局协同](C-RDMA单边KV池与布局协同.md) | RDMA one-sided | 语义连续布局 + 地址目录，用最少单边 READ 取动态 KV，远端 CPU 不参与 | ICDCS / TOS / Computer Networks | 低（Soft-RoCE+租真机） |
| [D-eBPF内核级KV换页与计算协同调度](D-eBPF内核级KV换页与计算协同调度.md) | eBPF+sched_ext | 内核事件驱动"I/O 完成→唤醒计算"短闭环，紧耦合换页与计算 | CoNEXT / ICNP / TOS | **零**（新内核+NVMe） |
| [E-KV流量的拥塞控制与多路径调度](E-KV流量的拥塞控制与多路径调度.md) | 拥塞控制/P4 | 按 KV block deadline/优先级做速率控制与多路径，降 incast 尾延 | CoNEXT / ICNP / Computer Networks | 低（ns-3 仿真为主） |

## 横向对比与选择建议

| 维度 | A DPDK | B eBPF-LB | C RDMA | D eBPF-调度 | E 拥塞控制 |
|---|---|---|---|---|---|
| 与 KV 兴趣匹配 | 高 | 高 | 高 | 高 | 高 |
| 与导师主业匹配 | 中高 | 中高 | 中 | 中 | **最高**（CC+INT+P4） |
| 硬件/花钱 | 低 | **零** | 低 | **零** | 低 |
| 对 GPU 依赖 | 可无（trace） | 可无（stub） | 可无（Soft-RoCE） | **可无**（核心指标内核延迟） | 可无（ns-3） |
| 学习曲线 | 中 | 中 | 中高 | 中高 | 中 |
| 新颖性安全度 | 高 | 高 | 高 | 高 | 高（均需动手前再扫 arXiv） |

### 推荐组合
1. **最稳、零成本、快速迭代** → **选题 B**（eBPF LB）或 **D**（内核调度）。两者数据面都不依赖 GPU，无卡也能出扎实结果。
2. **最贴导师、最易获手把手指导** → **选题 E**（KV 拥塞控制），可直接复用实验室 HPCC/SPRINT/INT/Tofino 积累。
3. **想要"网络+设备"完整系统故事** → **选题 A**（DPDK+MLDEV），工程展示性强。
4. **可合流路线**：B（LB 决策）+ E（路径拥塞）天然互补——一个决定"去哪个实例"，一个决定"走哪条路、什么速率"，可融合为一篇更完整的"KV-aware network fabric"工作。

## 共性评估方法（呼应导师 HTTP/3 论文的被接受路径）
- **真实系统/协议代码 + 仿真网络/拓扑（Mininet / ns-3 / Soft-RoCE / virtio）+ GPU 时序用 trace 参数代入**；
- 真机/租云只用于占比很小的关键性能验证；
- 适用边界：能扎实支撑"调度/网络/缓存策略"结论，不声称"绝对推理算力"。

## 下一步
1. 与崔老师确认：① BlueField 型号（是否支持作为 RDMA/DPDK 端点）；② 五个选题是否与实验室在投工作冲突；③ 老师偏好。
2. 动手前对选定方向再做一轮 arXiv 精确检索，确认空白仍在。
3. 先搭"trace + 仿真"公共实验台（所有选题共用）。
