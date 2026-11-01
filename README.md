# CCB Assistant（查查呗论文）

> **Breaking change in 0.3.0.** The tool was renamed from `lit` to `ccb`: the package, the CLI, the MCP entry point, all 16 tool names and all environment variables carry the new name, and **no compatibility layer is kept** — update any `lit` invocation, `LIT_*` environment variable or MCP registration you still have.
>
> **0.3.0 破坏性变更。** 工具从 `lit` 全量改名（更名）为 `ccb`：包名、CLI、MCP 入口、16 个工具名和所有环境变量均使用新名，**不保留兼容层**——请更新所有 `lit` 调用、`LIT_*` 环境变量和 MCP 注册。

**Agents:** start with [开发文档/for-agents.md](开发文档/for-agents.md) — the two ways to drive ccb, what each costs in context, and the three rules that keep answers checkable.

**Docs site:** <https://zhanjhe.github.io/ccb-assistant/> — design, module map, decisions and development records. The site publishes `开发文档/` only, built by MkDocs; every page is reachable from the [documentation index](开发文档/index.md). 文档站只发布 `开发文档/`。

---

## English

`ccb` answers three questions that most literature tooling answers separately and badly:

1. **How do I get this paper from any of the sources I have access to?** Free APIs, keyed APIs, MCP servers, local CLI tools and hand-supplied PDFs all sit behind one interface.
2. **Why am I downloading and parsing this paper again?** Because nothing was kept. `ccb` keeps it.
3. **What should I work on next?** The corpus already documents what the field cannot do. `ccb topics` mines that, one topic at a time, with the evidence attached.

### The three modules

```
topics    mine the corpus for one research topic, with its evidence
   │
search    find and obtain a paper from any legal source
   │
library   the durable local corpus: stable ids, dedup, provenance, evidence
   │
core      records, identities, normalisation, PDF extraction
```

### Clone it and use it

```bash
git clone <this repo> && cd ccb-assistant
python ccb.py channels
python ccb.py find "diffusion models for molecules" -n 10
python ccb.py get arxiv:1706.03762 --with-pdf
python ccb.py ask "how does scaled dot-product attention work"
python ccb.py cite arxiv:1706.03762
python ccb.py export --format bibtex -o refs.bib
```

### Where your data goes

Everything lands in **`papers/`**, inside this clone:

```
papers/
  library.json  library.jsonl   library metadata, and the append-only ledger
  works/                        one JSON record per paper, with field-level provenance
  evidence/                     raw channel responses, so nothing is ever re-fetched
  files/                        the PDFs
  blobs/                        extracted full text
  index.sqlite                  derived query index — deletable, always rebuildable
  topics/                       mined topics: surveys, candidates, records, drafts
```

The location is resolved from **the clone**, not from your working directory. To keep several corpora apart, use `--library papers-<topic>` or `$CCB_HOME`.

`papers/` is **local data, and is not in version control**. Two consequences:

- It is your **only** copy of the corpus. Back it up by copying the directory.
- Because the directory is ignored wholesale, **`git clean -Xdf` deletes the whole corpus.**

### Key commands

| Command | What it does |
|---|---|
| `ccb find "<topic>" -n 10` | Search local first, then channels |
| `ccb get <id> --with-pdf` | Acquire one paper (idempotent) |
| `ccb open <id> --head 20000` | Read locally, zero network |
| `ccb ask "<question>"` | Page-anchored passage retrieval |
| `ccb cite <id>` | Citation + field provenance |
| `ccb export --format bibtex` | Bibliography |
| `ccb check --all` | Re-verify: retraction, new version, OA |
| `ccb topics survey "<direction>"` | Map a research direction |
| `ccb contract` | The operating rules, machine-readable |

Exit codes: `0` ok, `2` usage, `3` not found, `4` partial, `5` failed.

### Channels

| Channel | Status | Role |
|---|---|---|
| `openalex` | works keyless | Broadest index; best OA locator |
| `crossref` | works keyless | Publisher of record |
| `arxiv` | works | Preprints and LaTeX source |
| `europepmc` | works keyless | Biomedical full text |
| `openreview` | works keyless | CS conference identity (no DOI needed) |
| `dblp` | gated (Anubis) | CS bibliographic spine |

Add a channel without code: declare it in `papers/channels.yaml` (kind: http / cli / mcp).

### Credentials

Keyed channels read credentials from **`papers/credentials.yaml`** — a flat map of
credential name to value, never committed (the whole `papers/` directory is ignored):

```yaml
S2_API_KEY: your-key-here
OPENALEX_EMAIL: you@example.edu   # joins polite pools; not a secret, same file
```

Loaded values are registered and scrubbed from every snapshot, cache and report, so a
key never reaches disk anywhere except this file. `ccb channels` reports exactly which
credential each channel is missing and what it buys.

### Development

```bash
ruff check src tests
python -m unittest discover -s tests -v     # 300+ tests, no network, no dependencies
python ccb.py install-skill                 # teach the agents in THIS project to use ccb
python -m pip install -r requirements-docs.txt && mkdocs serve   # docs preview
```

---

## 中文

`ccb` 回答三个大多数文献工具分开处理且处理不好的问题：

1. **怎么从我够得着的来源拿到这篇论文？** 免费 API、需 key 的 API、MCP server、本地 CLI 和手动投递的 PDF 都走同一个接口。
2. **为什么同一篇论文要反复下载和解析？** 因为之前什么都没保存。`ccb` 会保存。
3. **接下来该做什么课题？** 语料本身记录了领域做不到的事。`ccb topics` 从中挖掘，一次一个课题，附带证据。

### 三个模块

```
topics    从语料里挖出一个课题，附带证据
   │
search    从任何合法来源找到并获取论文
   │
library   持久本地语料：稳定 ID、去重、provenance、证据
   │
core      记录模型、身份链、文本规范化、PDF 抽取
```

### Clone 下来即用

```bash
git clone <本仓库> && cd ccb-assistant
python ccb.py channels
python ccb.py find "diffusion models for molecules" -n 10
python ccb.py get arxiv:1706.03762 --with-pdf
python ccb.py ask "scaled dot-product attention 是怎么工作的"
python ccb.py cite arxiv:1706.03762
python ccb.py export --format bibtex -o refs.bib
```

### 数据放在哪

使用过程中的一切都落在 **`papers/`**（clone 内）：

```
papers/
  library.json  library.jsonl   库元信息 + 只追加审计流水
  works/                        每篇论文一个 JSON 记录，带字段级 provenance
  evidence/                     渠道原始响应快照，永不重复抓取
  files/                        论文 PDF
  blobs/                        抽取出的全文
  index.sqlite                  派生查询索引——可删、随时可重建
  topics/                       已挖课题：测绘、候选、记录、草稿
```

路径从 **clone 目录**解析，与工作目录无关。要区分多个语料库，用 `--library papers-<课题>` 或 `$CCB_HOME`。

`papers/` 是**本地数据，不进版本控制**。两个后果：

- 它是语料的**唯一**副本。备份靠整个目录拷贝。
- 因为该目录被整体忽略，**`git clean -Xdf` 会删掉整个语料库。**

### 常用命令

| 命令 | 功能 |
|---|---|
| `ccb find "<主题>" -n 10` | 先查本地，未命中走渠道 |
| `ccb get <id> --with-pdf` | 获取一篇论文（幂等） |
| `ccb open <id> --head 20000` | 本地阅读，零网络 |
| `ccb ask "<问题>"` | 带页码锚点的段落检索 |
| `ccb cite <id>` | 引用 + 字段来源 |
| `ccb export --format bibtex` | 参考文献 |
| `ccb check --all` | 复查：撤稿、新版本、OA 变化 |
| `ccb topics survey "<方向>"` | 测绘一个研究方向 |
| `ccb contract` | 操作规则，机器可读 |

退出码：`0` 成功、`2` 用法错、`3` 未找到、`4` 部分成功、`5` 失败。

### 渠道

| 渠道 | 状态 | 角色 |
|---|---|---|
| `openalex` | 免 key 可用 | 覆盖面最广；最佳 OA 定位器 |
| `crossref` | 免 key 可用 | 出版方权威记录 |
| `arxiv` | 可用 | 预印本与 LaTeX 源 |
| `europepmc` | 免 key 可用 | 生物医学全文 |
| `openreview` | 免 key 可用 | CS 会议身份（无需 DOI） |
| `dblp` | 被反爬挡住 | CS 书目脊柱 |

不写代码加渠道：在 `papers/channels.yaml` 里声明（kind: http / cli / mcp）。

### 凭据

需要 key 的渠道从 **`papers/credentials.yaml`** 读取——"凭据名: 值"的平面映射，永不进
版本控制（整个 `papers/` 目录被忽略）。已加载的值会注册并从所有快照、缓存与报告中
擦除，因此 key 除本文件外不会落到任何磁盘位置。`ccb channels` 会精确报告每个渠道
缺哪个凭据、以及它能换来什么。

### 开发

```bash
ruff check src tests
python -m unittest discover -s tests -v     # 300+ 用例，无网络，无第三方依赖
python ccb.py install-skill                 # 让本项目的 agent 学会用 ccb
python -m pip install -r requirements-docs.txt && mkdocs serve   # 本地预览文档站
```
