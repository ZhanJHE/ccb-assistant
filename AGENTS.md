# CCB Assistant（查查呗论文）

This directory is the **code repository for the ccb tool**. It is also a literature workspace — the user's research material and the pre-project notes sit here, ignored by Git. Decide the mode before you act.

---

## English

### Routing (decide the mode first — do not guess)

| User intent | Mode | Read |
|---|---|---|
| Find papers / get PDFs / read full text / ask the corpus / export citations / mine a topic | **Use** | Load the `ccb` skill, follow SKILL.md's step sequences |
| Change code / tests / docs / explain the implementation | **Develop** | `开发文档/design/spec.md` + `开发文档/`; run the full test suite before changing anything |
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
   (`开发文档/records/log.md`): development work only — commits, fixes, decisions,
   known issues — never usage data, user behaviour, or research content.
5. The documentation tree and the site's navigation move together: a page added,
   renamed or deleted under `开发文档/` must be reflected in `mkdocs.yml`'s `nav`, or
   `tests/test_docs.py` fails. `mkdocs build --strict` (run by
   `.github/workflows/docs.yml`) catches the links `nav` cannot see.

### Documentation site

`开发文档/` is the only source; `mkdocs.yml` names every page in `nav`; the site is
built by `.github/workflows/docs.yml` and served at
<https://zhanjhe.github.io/ccb-assistant/>. The pages fall into four groups, and the
group is what tells a reader whether a page describes the code as it is now:

| Group | Directory | read it as |
|---|---|---|
| Design | `design/` — `spec.md`, `modules.md` | current behaviour |
| Decisions | `decisions/` — one page per decision | why it is built this way; already implemented |
| Records | `records/` — work log, reviews, surveys | a point in time; paths and hashes inside are **not** updated |
| Walkthrough | `walkthrough/` — one self-contained HTML page | teaching material for people |

`for-agents.md` sits at the root of `开发文档/` on purpose: the skill, the README and
`tests/test_docs.py` all name that path, so it does not move with the groups.

Local preview: `python -m pip install -r requirements-docs.txt && mkdocs serve`.

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

### Document destinations (what is tracked, what is local)

| Content | Directory | Git |
|---|---|---|
| About building this tool (design, module map, decisions, records, walkthrough, for-agents) | `开发文档/` | tracked, published as the documentation site |
| The user's own research material (surveys, selection plans, idea pools, experiment projects, venue catalogues) | `用户文档/` | **local only**, ignored |
| Pre-project research (read-only history) | `notes/` | **local only**, ignored |

Place a new document by what it *is*, not by who is talking. User research material never goes into `开发文档/`, and tool documentation never goes into `用户文档/`.

`用户文档/` and `notes/` are ignored *wholesale*, so `git clean -Xdf` deletes them — back them up by copying the directory, not through Git.

---

## 中文

本目录是 **ccb 工具的代码仓库**。它同时是一个文献工作区：用户的科研资料与立项前笔记
放在这里，但被 Git 忽略。动手前先分流。

### 分流（先判定模式，不要猜）

| 用户意图 | 模式 | 读什么 |
|---|---|---|
| 找论文 / 下 PDF / 读全文 / 问文献 / 导出引用 / 选题 | **使用** | 加载技能 `ccb`，按 SKILL.md 的步骤序列执行 |
| 改代码 / 改测试 / 改文档 / 解释实现 | **开发** | `开发文档/design/spec.md` + `开发文档/`；改动前先跑全量测试 |
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
4. 开发会话收尾必须追加开发工作日志（`开发文档/records/log.md`）：只记开发
   （提交 / 修复 / 决策 / 已知问题），不记使用数据、用户行为与课题内容。
5. 文档树与站点导航同步动：`开发文档/` 下新增、改名、删除页面必须同步
   `mkdocs.yml` 的 `nav`，否则 `tests/test_docs.py` 失败；`mkdocs build --strict`
   （由 `.github/workflows/docs.yml` 执行）负责抓 `nav` 看不到的坏链接。

### 文档站

`开发文档/` 是唯一来源，`mkdocs.yml` 的 `nav` 定义导航，站点由
`.github/workflows/docs.yml` 构建并发布在 <https://zhanjhe.github.io/ccb-assistant/>。
页面分四组，分组本身说明该页描述的是"现在"还是"当时"：

| 组 | 目录 | 怎么读 |
|---|---|---|
| 设计 | `design/` —— `spec.md`、`modules.md` | 现行行为 |
| 决策与方案 | `decisions/` —— 一个决定一页 | 为什么这么造；均已实施 |
| 开发记录 | `records/` —— 工作日志、评审、借鉴调研 | 时点记录；里面的路径与哈希**不会**更新 |
| 项目讲解 | `walkthrough/` —— 一个自包含 HTML 页 | 面向人的长文讲解 |

`for-agents.md` 故意留在 `开发文档/` 根：技能、README 与 `tests/test_docs.py` 都指着
这个路径，它不随分组移动。

本地预览：`python -m pip install -r requirements-docs.txt && mkdocs serve`。

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

### 文档去向（什么入库，什么只在本机）

| 内容 | 目录 | Git |
|---|---|---|
| 关于造这个工具的（设计方案、模块地图、决策、记录、讲解、for-agents） | `开发文档/` | 入库，并作为文档站发布 |
| 用户的科研资料（调研综述、选题方案、Idea 池、实验项目、场馆目录） | `用户文档/` | **只在本机**，已忽略 |
| 立项前调研（只读历史） | `notes/` | **只在本机**，已忽略 |

新文档按**内容归属**放，不按"谁在说话"放：用户的调研材料不进 `开发文档/`，工具文档不进 `用户文档/`。

`用户文档/` 与 `notes/` 是整体忽略的：`git clean -Xdf` 会把它们一起删掉。备份靠整个目录拷贝，不走 Git。
