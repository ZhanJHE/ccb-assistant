# lit — 设计定稿

> 一句话目标：**问第二次时，直接命中本地论文库；而不是把「查询→下载→处理→读取」重跑一遍。**

---

## 0. 要解决的病

现在每个 AI 工具处理文献都是这个循环：

```
用户问 → 联网搜 → 下载 PDF → 抽取文本 → 塞进上下文 → 丢弃
用户再问 → 联网搜 → 下载 PDF → 抽取文本 → 塞进上下文 → 丢弃
（重复 N 次，每次都花网络、花 token、花时间，且结果不稳定）
```

调研证实：**没有任何现有工具打破这个循环**。arXiv 检索有 ≥8 个独立实现，DOI→PDF 兜底链被重写多遍，跨源去重只在单次查询内存里做、做完就把身份映射丢掉。

## 1. 解决方案：四层 + 一个协议

```
L4 引用/导出   BibTeX / RIS / GB-T 7714 / 带页码引用的问答
L3 读取        PDF→文本（复用本机 liteparse/pdfplumber，不重写）
L2 论文库      持久化本地库：稳定 ID + 跨源去重 + 字段级 provenance + 原始证据
L1 渠道整合    统一入口整合：免费 API / 需 Key 渠道 / MCP / 本地 CLI 工具
─────────────────────────────────────────────────────────
★ 本地优先协议（Local-first）：每次请求先问 L2，只有未命中才上 L1
```

**决定性的那一条是「本地优先协议」**——它就是「不重跑全过程」的具体实现机制：

```
get(identifier):
    hit = library.resolve(identifier)      # 本地命中？
    if hit and hit.has_fulltext: return hit        # 直接返回，零网络
    if hit and not hit.has_fulltext: 只补全文      # 不重查元数据
    else: 走 L1 获取 → 落库 → 返回                # 首次才走全链路
```

## 2. L1：渠道整合层

### 2.1 渠道描述符（声明式）

每个渠道是一份声明，不是散落的 if-else。渠道有四种 `kind`，但**对使用者完全透明**：

| kind | 含义 | 例子 |
|---|---|---|
| `http` | 直接调 HTTP API | DBLP、arXiv、OpenAlex、Crossref、OpenReview、Unpaywall |
| `cli` | 包装本地命令行工具 | 本机已装的 `paper-search`（21 源） |
| `mcp` | 通过 MCP server 调用 | 未来接入他人 MCP |
| `manual` | 人工投喂 | 用户直接给 PDF |

描述符字段：

```yaml
name: dblp
kind: http
license: CC0            # 数据许可，用于合规审计
auth: none              # none | env:VAR | keyfile
rate: {rps: 1.0}        # 礼貌限流
caps: [search, lookup, venue]    # 能干什么
cs_authority: true      # 是否 CS 身份权威源
```

**凭据透明**：渠道声明 `auth: env:S2_API_KEY`，运行期缺失该环境变量 → 该渠道自动降级为「不可用」并**在结果里明确报告**，其余渠道照常工作。用户不需要知道谁要 key。

### 2.2 实测的渠道可用性（本机验证过）

| 渠道 | 实测 | 定位 |
|---|---|---|
| **DBLP** | 200 | ✅ **CS 身份脊柱**（唯一 CS 原生书目） |
| **arXiv** | 200 | ✅ 预印本 + LaTeX 源（3 秒/请求） |
| **OpenAlex** | 200 | ✅ 全学科元数据 + OA 定位 |
| **Crossref** | 200 | ✅ DOI 权威元数据 |
| **OpenReview v2** | 200 | ✅ **CS 会议核心**（投稿/评审/决定） |
| **Unpaywall** | 200 | ✅ 合法 OA 定位（**必须带真实 email**） |
| **Europe PMC** | 200 | ✅ 生物医学全文 |
| **DOAJ** / **CORE** | 200 | ✅ OA 期刊 / OA 全文库 |
| **paper-search**（本地 CLI） | 可用 | ✅ 桥接 21 源，作为补充 |
| Semantic Scholar | **429** | ⚠️ 无 key 频繁限流 → 可选 |
| OpenCitations | 400 | ⚠️ 端点数需修正 |
| IACR | 404 | ⚠️ 端点已变 |
| Google Scholar | — | ❌ 违反 ToS，不作依赖 |

## 3. L2：论文库（本项目的核心资产）

### 3.1 双层身份：Work / Manifestation

现有工具全栽在「把身份压成一个键」上。这里分两层，**两层都是确定性纯函数，都可解释**：

```
work_id        概念层：「这篇论文」是谁
manifestation  载体层：arXiv v1/v2、NeurIPS 正式版、OpenReview 投稿、期刊版
```

**work_id 不用「聪明」的指代消解，而是一条显式键优先级链**，命中即用，并把「用了哪条」记进账本：

| 优先级 | 键 | 例 |
|---|---|---|
| 1 | `doi` | `doi:10.1145/3292500.3330701` |
| 2 | `openreview` | `openreview:abcDEF123` |
| 3 | `arxiv` | `arxiv:1706.03762` |
| 4 | `acl` \| `pmlr:<vol>:<page>` \| `dblp:<key>` | `pmlr:97:1` |
| 5 | `t:<规范标题>|<一作姓>|<年>` | 兜底，仅当上面全空 |

价值：**v2 与正式版是同一 work 的两个 manifestation**——PDF 是两份、页码不同、引用应指正式版。现有工具要么当两篇（重复），要么粗暴合并（丢版本信息）。

### 3.2 字段级 provenance（不是条目级）

每个字段都是一组 **claim**，而不是一个被反复覆盖的值：

```json
"title": [
  {"src": "dblp",    "val": "Attention is All you Need", "at": "2026-10-11T...", "ev": "ev_8f3a"},
  {"src": "openalex", "val": "Attention Is All You Need", "at": "2026-10-11T...", "ev": "ev_2c19"}
]
```

- 显示值时按**源权威度规则**选一条，但**所有 claim 都保留**。
- `ev` 指向 `evidence/` 里的原始响应快照。
- 好处：多源矛盾（卷号/页码/年份不一致）**被看见而不是被吞掉**；任何字段都能追溯到「哪个渠道、什么查询、什么时候」产出的。

### 3.3 先存原始证据，再解析（snapshot-first）

每次调用渠道，先落盘**原始响应 + 端点 + 参数 + 时间戳 + 状态码**，解析在本地做。

这一条同时解决四件事：
1. 字段级 provenance 变成免费的
2. 离线可重放、可重建索引
3. 多源冲突不丢信息
4. **增量复查可做**：复查 = 对已存记录重跑少量端点，diff 出撤稿/新版本/OA 变化

### 3.4 磁盘布局（纯文本为真相源）

```
library/
  library.json          # 库元信息 + schema 版本
  works/<hash2>/<work_id>.json    # 权威记录：身份 + claims + manifestations
  evidence/<ev_id>.json           # 原始响应快照
  files/<content_sha256>.pdf      # 内容寻址：同一文件永不重复存
  blobs/<work_id>/fulltext.txt    # 抽取出的文本
  ledger.jsonl                    # 只追加事件流，审计用
  index.sqlite                    # 从上面重建的查询索引，随时可删
```

**为什么文本为真相源而不是直接上 SQLite**：可 diff、可 grep、可被 agent 直接读、可手工改、可提交进 git。`index.sqlite` 只是加速层，删了能从 works 重建——所以**永不出现「库损坏且无法恢复」**。

### 3.5 去重：两段式，匹配结果可审计

1. **精确段**：键优先级链命中 → 直接同一 work
2. **模糊段**：规范化标题（小写、去标点、去 LaTeX、Unicode NFKC）+ token 集合 Jaccard + 一作姓 + 年份容差 → 过阈值后**不自动合并**，而是生成一条 `merge_candidate` 进账本，可由 `lit merge` 确认

保守优先：**宁可留候选，不要错合并**。错合并会污染引用，代价远高于多一条候选。

## 4. 落地形态与兼容性

同一核心三种形态：

```
lit CLI (JSON)  ←── 确定层，可测试
  ├─► Agent Skill（.dsh/skills/lit/）：LLM 负责编排与判断
  └─► MCP server：给支持 MCP 的 harness（后续）
```

**实测的硬约束**：
- agentskills.io 规范的超集写法（`name` ≤64 kebab-case、`description` ≤1024、可选 `license`/`compatibility`/`metadata`/`allowed-tools`）
- DSH 更严：技能发现**只有一层深**（`<name>/SKILL.md`），单个 SKILL.md 渲染后 **< 8192 字符** → 大块内容放 `references/`
- 扫描根：`<projectRoot>/.dsh/skills`、`~/.dsh/skills`
- Windows/GBK：子进程必须显式 UTF-8 I/O

**零第三方依赖**：只用标准库 `urllib`/`json`/`sqlite3`/`hashlib`。
PDF 抽取按可用性探测 `pdfplumber` → `pypdf`，都没有则提示走本机 `liteparse` 技能。

## 5. 安全与合规基线（不可协商）

| 项 | 策略 |
|---|---|
| Sci-Hub / Anna's Archive | **绝不引入**（调研发现 ≥6 个工具含它） |
| 抓取 Google Scholar | 不作依赖（违反 ToS 且反爬未解） |
| 凭据 | 只从环境变量读；**绝不写入产物、绝不回显、绝不进日志** |
| ACM DL 等有浏览器挑战的 | 明确报告「拿不到」，不做对抗 |
| 代码来源 | 不复制无许可/非商用代码（调研发现多个此类条目） |
| 依赖源 | 只用官方源，锁版本（防 `iflow-mcp_*` 之类转发镜像） |

## 6. 命令面

```
lit channels                     列出所有渠道、可用性、缺哪个 key（不泄露值）
lit find "<query>"               检索：先本地，再渠道；结果落入候选
lit get <identifier>             取得论文：本地优先，必要时补元数据/补全文
lit open <work_id>               直接读本地全文（零网络）
lit library stats                库统计
lit library check                增量复查：撤稿/新版/OA 变化
lit export --format bibtex       导出引用
lit merge <a> <b>                确认合并候选
```

所有命令支持 `--json`（默认）与 `--offline`。
