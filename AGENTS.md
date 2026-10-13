# CCB Assistant（查查呗论文）

This directory is **both the code repository for the ccb tool** and **a literature workspace**. Decide the mode before you act.

---

## English

### Routing (decide the mode first — do not guess)

| User intent | Mode | Read |
|---|---|---|
| Find papers / get PDFs / read full text / ask the corpus / export citations / mine a topic | **Use** | Load the `ccb` skill, follow SKILL.md's step sequences |
| Change code / tests / docs / explain the implementation | **Develop** | `开发文档/设计定稿.md` + `开发文档/`; run the full test suite before changing anything |
| Both | — | **Ask first** |

Declare which mode you chose at the start (one line is enough). A wrong call is corrected on the spot.

### Use mode — three hard rules

1. **Rules come from the tool, not from memory**: run `python ccb.py contract` (or MCP `ccb_contract`) first — authoritative, machine-readable, and non-drifting.
2. **Local first, then network**: `find` already goes local first. Do not bypass it with other search tools.
3. **No prose, no invented citations**: `ask` returns page-anchored passages — build the answer from those and cite them; if `grounded: false`, answer "the corpus does not cover this". Never answer from memory.

### Develop mode — three hard rules

1. The module DAG is not negotiable: `core ← library ← search ← topics`; `tests/test_modules.py` will fail otherwise.
2. Never change an on-disk format without a migration; `works/*.json` is the source of truth, the index is disposable.
3. `python -m unittest discover -s tests` must pass after every change.
4. Close every development session by appending to the development work log
   (`开发文档/开发工作日志.md`): development work only — commits, fixes, decisions,
   known issues — never usage data, user behaviour, or research content.

### Tool arbitration (when other literature tools exist on this machine)

Other retrieval tools may also be installed (skills, MCP servers, CLIs). Decide by purpose:

- Anything that must be **stored / deduplicated / traced / reused** → always `ccb` (it only writes `papers/`).
- A one-off query that will not be kept → other tools are fine, but **never hand-feed their results into `papers/`**.
- On conflict `ccb` wins: the local corpus's consistency is the only authority in this directory.

Rationale: bypassing the persistence layer silently breaks "the same paper is never searched twice", and untracked results have no provenance — mixed into the library they are indistinguishable from sourced records.

### Never allowed

- Hand-editing anything under `papers/` (all changes go through commands).
- Asking for or echoing any API key's **value** (name the environment variable only; the user sets it).
- Bypassing paywalls / mirror hunting (see `ccb contract`'s `legal-sources-only`).

### Document destinations (two doc trees, two purposes)

| Content | Directory |
|---|---|
| About building this tool (design, walkthrough, borrowing survey, for-agents) | `开发文档/` |
| The user's own research material (surveys, selection plans, idea pools, experiment projects, venue catalogues) | `用户文档/` |
| Pre-project research (read-only history) | `notes/` |

Place a new document by what it *is*, not by who is talking. User research material never goes into `开发文档/`, and tool documentation never goes into `用户文档/`.

---

## 中文

本目录同时是 **ccb 工具的代码仓库** 和 **文献工作区**。动手前先分流。

### 分流（先判定模式，不要猜）

| 用户意图 | 模式 | 读什么 |
|---|---|---|
| 找论文 / 下 PDF / 读全文 / 问文献 / 导出引用 / 选题 | **使用** | 加载技能 `ccb`，按 SKILL.md 的步骤序列执行 |
| 改代码 / 改测试 / 改文档 / 解释实现 | **开发** | `开发文档/设计定稿.md` + `开发文档/`；改动前先跑全量测试 |
| 两者都像 | — | **先问一句** |

开头声明你选了哪个模式（一行即可）。判断错了用户能当场纠正。

### 使用模式三条硬规则

1. **规则从工具取，不要凭记忆**：先 `python ccb.py contract`（或 MCP `ccb_contract`）——
   权威、机器可读、且不漂移。
2. **先本地，后网络**：`find` 已本地优先。不要绕过它直接调用其它检索工具。
3. **不写散文、不编引用**：`ask` 返回带页码锚点的段落，你据此组织答案并引用；
   `grounded: false` 就回答"语料未覆盖"，绝不凭记忆答。

### 开发模式三条硬规则

1. 模块 DAG 不可破：`core ← library ← search ← topics`；`tests/test_modules.py` 会 fail。
2. 不改磁盘格式而不写迁移；`works/*.json` 是真相源，索引可弃。
3. 改完必须 `python -m unittest discover -s tests` 全绿。
4. 开发会话收尾必须追加开发工作日志（`开发文档/开发工作日志.md`）：只记开发
   （提交 / 修复 / 决策 / 已知问题），不记使用数据、用户行为与课题内容。

### 能力裁决（本机存在同类工具时）

本机可能同时装有其它文献检索工具（技能、MCP server、CLI）。按用途裁决：

- 需要**落库 / 去重 / 溯源 / 复用** → 一律走 `ccb`（它只写 `papers/`）。
- 只需一次性查询、不打算留存 → 可用其它检索工具，但**不得手工把结果塞进 `papers/`**。
- 冲突时 `ccb` 优先：本地语料的一致性是本目录唯一权威。

理由：绕过持久层会让"同一篇论文不再重查"静默失效，而且那些结果没有 provenance，
与库内记录混在一起后无法区分来源。

### 从未允许

- 手工编辑 `papers/` 下任何文件（一切变更走命令）。
- 索要或回显任何 API key 的**值**（只告知环境变量名，让用户自己设置）。
- 绕过付费墙 / 镜像狩猎（见 `ccb contract` 的 `legal-sources-only`）。

### 文档去向（两处目录的功能区分）

| 内容 | 目录 |
|---|---|
| 关于造这个工具的（设计方案、讲解、借鉴调研、for-agents） | `开发文档/` |
| 用户的科研资料（调研综述、选题方案、Idea 池、实验项目、场馆目录） | `用户文档/` |
| 立项前调研（只读历史） | `notes/` |

新文档按**内容归属**放，不按"谁在说话"放：用户的调研材料不进 `开发文档/`，工具文档不进 `用户文档/`。
