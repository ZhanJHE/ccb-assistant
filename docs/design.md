# lit — 设计定稿

> 一句话目标：**问第二次时直接命中本地论文库，不再把「查询→下载→处理→读取」重跑一遍；在此基础上，从库里挖出值得做的课题，并且每条论断都能被回溯。**

---

## 0. 要解决的病

现在每个 AI 工具处理文献都是这个循环：

```
用户问 → 联网搜 → 下载 PDF → 抽取文本 → 塞进上下文 → 丢弃
用户再问 → 联网搜 → 下载 PDF → 抽取文本 → 塞进上下文 → 丢弃
（重复 N 次，每次都花网络、花 token、花时间，且结果不稳定）
```

调研证实：**没有任何现有工具打破这个循环**。arXiv 检索有 ≥8 个独立实现，DOI→PDF 兜底链被重写多遍，跨源去重只在单次查询内存里做、做完就把身份映射丢掉。

于是产生第二个病：**语料留不下来，所以也没法从它里面长出东西**。选题只能靠人翻文献，或者靠模型凭记忆编。

---

## 1. 结构：三个模块 + 一个共享底层

```
topics    从语料里挖出一个课题，附带证据
   │
search    从任何合法来源找到并取得论文
   │
library   持久化本地语料：稳定 ID、去重、provenance、原始证据
   │
core      记录模型、身份链、文本规范化、PDF 抽取
────────────────────────────────────────────────────────
★  本地优先：每次请求先问 library，未命中才上 search
```

**依赖规则：模块只能 import 它下面的东西。** `core` 不 import 任何自家模块；`library` 不碰网络；`search` 是唯一的写库方；`topics` 读上面三者、只写自己的产物。

这条规则不是注释，是测试：`tests/test_modules.py` 直接解析真实 import 图，越界即失败。**边界不被测试就会侵蚀。**

重组顺带解决了两处真实的循环依赖：

| 现状 | 问题 | 重组后 |
|---|---|---|
| `channels/*` import `evidence.EvidenceStore`（快照写进库目录） | L1 反依赖 L2 | `evidence` 归 `library`，成为合法的 `search → library` |
| `library.py` import `cite.to_bibtex`、`passages.chunk_text` | L2 反依赖 L4 | `cite`/`passages` 归 `library`，成为模块内引用 |

`extract.py` 放 `core`：`search`（下载后抽取）和 `library`（重新抽取）都要用，放任一侧都会造出新环。

---

## 2. 模块一：搜索与下载（`lit.search`）

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

### 2.3 本地优先协议

这是「不重跑全过程」的具体实现机制，住在本模块：

```
get(identifier):
    hit = library.resolve(identifier)      # 本地命中？
    if hit and hit.has_fulltext: return hit        # 直接返回，零网络
    if hit and not hit.has_fulltext: 只补全文      # 不重查元数据
    else: 走渠道获取 → 落库 → 返回                # 首次才走全链路
```

实测（arXiv 1706.03762，2.2 MB PDF）：首次 ~5–7 s，第二次 **0.2 s 且零网络**，换用 DOI 查询同样是 0.2 s 且落到同一个 `work_id`。

---

## 3. 模块二：论文库（`lit.library`）

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
| 5 | `t:<规范标题>\|<一作姓>\|<年>` | 兜底，仅当上面全空 |

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

### 3.4 去重：两段式，匹配结果可审计

1. **精确段**：键优先级链命中 → 直接同一 work
2. **模糊段**：规范化标题 + token 集合 Jaccard + 一作姓 + 年份容差 → Jaccard ≥ 0.92 才自动合并；0.60–0.92 之间生成一条 `merge_candidate` 进账本，由 `lit merge` 确认

保守优先：**宁可留候选，不要错合并**。错合并会污染引用，代价远高于多一条候选。

### 3.5 库里还住着「检索」与「导出」

`ask`（BM25 + 页码锚点）和 `cite`（BibTeX/RIS/CSL）都属于本模块：它们是**对语料的读取**，不碰网络。搜索模块通过薄委托暴露它们，纯粹是为了让只持有 Resolver 的调用方不必再拿一个 Library。

---

## 4. 模块三：课题生成（`lit.topics`）

### 4.1 贯穿一切的原则：工具不写散文

模块只产出**结构化证据 + 结构骨架 + 打分与理由**，正文由 Agent 撰写。这样做的理由有两条，缺一不可：

- **可复现**：同一输入同一输出，没有模型参与，可测试。
- **可审计**：课题里每一条论断，都能回到库里某篇论文的某一页。

这是一条不变式（`evidence-anchored-topics`），由测试守着：草稿里不可能出现没有锚点的论断。

### 4.2 五步流程

```
1. survey      该方向库里有什麼，够不够挖；不够则自动联网补齐到阈值
2. gaps        缺口证据：作者自述的局限/未来工作 + 稀疏术语对
3. candidates  (证据 × 创新算子) 候选，打分排序，排除已挖过的组合
4. draft       一次只提交一个，产出章节骨架，每条论断绑锚点
5. rate        CCF 评级预估：上界 + 分档 + 逐条依据 + 置信度 + 风险
6. save        落库 + 导出 Markdown + 退役去重键
```

`survey_id` 是 (query, 窗口, work_id 集合) 的哈希，所以同一方向同一语料给出同一个 id 和同一组数字。

### 4.3 缺口证据从哪来

**一、作者自述句（最强信号）**

从全文/摘要里抽含标记的句子，带 `work_id` + `page` + 原句。一个作者写下「未来工作将探索 X」，他就已经替你命名了一个课题，而且这句话是可引用的证据。

按六类打标，因为不同类支撑完全不同的课题：

| kind | 句子在说什么 | 喂给哪些算子 |
|---|---|---|
| `future_work` | 作者点出了下一步 | transfer, new-setting, revalidate |
| `absence` | 没人研究过 | fill-absence, transfer, benchmark, integrate |
| `limitation` | 只在某个范围内成立 | boundary, paradox |
| `inefficiency` | 规模上太贵 | scale-up |
| `idealization` | 假设了不现实的东西 | relax-assumption |
| `breadth` | 太粗、不够具体 | benchmark, paradox |

中英文标记都认（`未来工作`、`未考虑`、`缺乏`…）。

**二、稀疏术语对（可计算的 A+B）**

```
expected = docs(a) * docs(b) / works      # 若两者独立
deficit  = expected - together
```

只在 `deficit ≥ 1.0` 时报告。这正是「学术裁缝」里 A+B 拼接的可计算形式：两个概念各自被领域大量使用，却几乎从不一起出现。用文档频次而非出现次数，免得一篇长文把某个词堆成「主题」。

### 4.4 创新算子（把写论文的套路工程化）

调研文献里关于「怎么找创新点」的说法收敛到十一个动作，机械到可以编码。每个算子带创新类型、难度、现实可及的 CCF 上界，以及它消费哪类证据。

| id | 动作 | 类型 | 难度 | 上界 | 消费 |
|---|---|---|---|---|---|
| `recombination` | A + B → C | fusion | 3 | B | 稀疏对 |
| `transfer` | 把成熟方法跨边界搬过来 | application | 2 | C | absence, future_work |
| `new-setting` | 老方法，新场景/新数据集 | application | 2 | C | future_work, absence |
| `revalidate` | 新技术重验老问题 | comparison | 4 | B | future_work, absence |
| `relax-assumption` | 去掉简化假设 | modification | 3 | B | idealization |
| `scale-up` | 拆掉规模墙 | modification | 3 | B | inefficiency |
| `fill-absence` | 做那件「据说没人做」的事 | modification | 3 | B | absence |
| `boundary` | 把局限变成精确条件 | theory | 5 | A | limitation |
| `benchmark` | 多方法放到同一协议下比 | comparison | 4 | B | absence, breadth |
| `integrate` | 架起两套理论的桥 | fusion | 3 | A | 稀疏对, absence |
| `paradox` | 解释一个被记录下来的矛盾 | theory | 5 | A | limitation, breadth |

难度沿用领域自己的排序：**新问题新方法 > 老问题新方法 > 新问题老方法 > 老问题老方法**。

算子产出的是**问题骨架**，不是句子。例如 `recombination` 产出的是「该方向同时大量使用 {a} 和 {b}，却几乎从不一起出现（{total} 篇里 {together} 篇，独立预期 {expected}）——把 {a} 用到 {b} 所处理的问题上，换来了什么，在哪个指标上？」——这是待回答的问题，不是待粘贴的文字。

### 4.5 打分：四个部分，全部摊开

| 部分 | 权重 | 何时高 |
|---|---|---|
| `directness` | 0.35 | 作者自述缺口（1.0），而非统计推断（0.5） |
| `support` | 0.25 | 该方向多篇工作与这条证据相关 |
| `ambition` | 0.20 | 算子难度高（2/5 → 0.0 … 5/5 → 1.0） |
| `novelty` | 0.20 | 库里共享该候选术语的工作少 |

四项都以该方向的语料规模归一化（用固定分母会让小语料全部饱和成一列相同的分数，排序就失去了信息），并且**逐项写进 `score_basis`**，可以手算复核：`score = Σ value × weight`。

同时给出 `local_coverage`：库里共享该候选术语的工作清单。**先读它们，再说这个组合没人做过。**

### 4.6 「一次一个」

`candidates` 提议，`draft` 提交。每个提交的课题退役一个 `dedup_key`（`<算子>::<证据键>`），后续轮次会把它过滤掉（`excluded_as_mined`）。

没有这一条，同一个方向挖两次会得到同一个点子换套说法，而一堆近重复的课题比没有课题更糟。

### 4.7 CCF 评级：可审计的启发式，不是承诺

输出**上界 + 分档 + 置信度 + 逐条依据 + 风险**，五个输入全部可复算：

1. **算子天花板**——起点上界。现有方法的应用到不了顶会，新框架可以。
2. **自述还是推断**——作者原句 vs 共现统计。推断扣一档。
3. **语料支撑**——低于该方向 30% 的工作相关，扣一档。
4. **本地覆盖**——超过 60% 的工作共享术语，扣一档。
5. **算子难度**——≤ 2/5（增量动作），扣一档。

`--venue X` 会查表：已知 venue 的自身等级封顶，算子天花板低于目标档位时给明确警告。**没收录的 venue 报 `unmatched`，绝不从相似名字插值。**

### 4.8 CCF 目录是数据，不是代码

`src/lit/topics/data/ccf_recommended.csv`，字段 `abbr,aliases,name,kind,field,rank`。两条刻意为之：

- **内置的是精选子集**（159 条主流 CS 会议/期刊），不是官方全量文档；`LIT_CCF_CATALOG` 可整体替换，`lit topics venues --verify` 先检查重复与畸形行。
- **未匹配是一个真实答案**。匹配保守：缩写必须是连续的 token 串，或名字精确相等。**不做子串匹配**，因为 `ai` 是 `artificial` 的子串，而错的等级比没有等级更糟。

### 4.9 落盘布局

```
papers/
  topics/
    index.json          已挖历史 + 已退役的去重键
    surveys/<id>.json   领域测绘
    candidates/<id>.json 候选集（自包含，内嵌所用 survey）
    records/<id>.json   已提交课题：算子、证据、章节、评级
    drafts/<id>.md      `topics save` 导出的 Markdown 草稿
```

---

## 5. 磁盘布局（纯文本为真相源）

**库里在这个仓库里**：默认根是 `<checkout>/papers`，与代码同目录、使用者一眼可见。解析顺序 `--library` > `$LIT_HOME` > `$LIT_REPO` > **checkout 锚定** > `<cwd>` 兜底。

锚在 checkout 而不是 cwd 是刻意的：harness 从使用者的项目目录调用工具，cwd 相对默认值会让语料长在**调用者所在的地方**，而 clone 出来的那个目录——唯一可见且稳定的位置——反而空着。「clone 即用」要求数据落在 clone 里。

```
papers/
  library.json          # 库元信息 + schema 版本
  works/<2>/<2>/<work_id>.json   # 权威记录：身份 + claims + manifestations
  evidence/<ev_id>.json # 原始响应快照
  files/<2>/<sha256>.pdf # 内容寻址：同一文件永不重复存
  blobs/<work_id>/fulltext.txt   # 抽取出的文本
  blobs/<work_id>/passages.json  # 段落索引：派生，缺了自愈重建
  library.jsonl         # 只追加事件流，审计用
  index.sqlite          # 从上面重建的查询索引，随时可删
  channels.yaml         # 可选：不写代码声明额外渠道
  topics/               # 模块三的产物（见 4.9）
```

**为什么文本为真相源而不是直接上 SQLite**：可 diff、可 grep、可被 agent 直接读、可手工改，且 `index.sqlite`、`passages.json` 等派生件删了都能从文本与记录重建——所以**永不出现「库损坏且无法恢复」**。

**为什么整目录不进 git**：它是*使用*工具产生的数据，不是源码；Git 只跟踪代码、测试、开发文档与 skill。连带两个后果，文档里必须写明：`papers/` 是语料的**唯一副本**（备份靠整个目录拷贝），且因为它被整体 ignore，`git clean -Xdf` 会连语料一起删。

---

## 6. 落地形态与兼容性

同一核心三种形态 —— 注意它们是**同一个目录的三个入口**，不是三种分发方式：

```
lit CLI (JSON)  ←── 确定层，可测试（<checkout>/lit.py，免安装）
  ├─► Agent Skill（.dsh/skills/lit/）：就住在这个仓库里，agent 在本目录工作即被发现
  └─► MCP server：16 个工具（9 个检索/库 + 7 个课题）
```

课题生成刻意拆成 7 个 MCP 工具而非 1 个大工具：**中间有判断**，Agent 必须先读证据再选，选了才起草。

**实测的硬约束**：

- agentskills.io 规范的超集写法（`name` ≤64 kebab-case、`description` ≤1024、可选 `license`/`compatibility`/`metadata`/`allowed-tools`）
- DSH 更严：技能发现**只有一层深**（`<name>/SKILL.md`），单个 SKILL.md 渲染后 **< 8192 字符** → 大块内容放 `references/`
- 扫描根：`<projectRoot>/.dsh/skills`、`~/.dsh/skills`
- Windows/GBK：子进程必须显式 UTF-8 I/O

**零第三方依赖**：只用标准库 `urllib`/`json`/`sqlite3`/`hashlib`/`csv`。
PDF 抽取按可用性探测 `pdfplumber` → `pypdf`，都没有则提示走本机 `liteparse` 技能。

**过渡期兼容**：旧导入路径（`lit.library`、`lit.resolver`、`lit.channels.*` 等）保留为 `sys.modules` 别名，与规范路径是**同一个模块对象**，不会产生两份状态。待外部调用方迁移后删除。

---

## 7. 安全与合规基线（不可协商）

| 项 | 策略 |
|---|---|
| Sci-Hub / Anna's Archive | **绝不引入**（调研发现 ≥6 个工具含它） |
| 抓取 Google Scholar | 不作依赖（违反 ToS 且反爬未解） |
| 凭据 | 只从环境变量读；**绝不写入产物、绝不回显、绝不进日志** |
| ACM DL 等有浏览器挑战的 | 明确报告「拿不到」，不做对抗 |
| 代码来源 | 不复制无许可/非商用代码（调研发现多个此类条目） |
| 依赖源 | 只用官方源，锁版本（防 `iflow-mcp_*` 之类转发镜像） |

新增一条属于课题生成的：

| 项 | 策略 |
|---|---|
| 编造等级 / 编造点子 | 未收录 venue 报 unmatched；无锚点的论断不产出；评级永远附带依据与风险，不作为承诺 |

---

## 8. 命令面

```
lit channels                     列出所有渠道、可用性、缺哪个 key（不泄露值）
lit find "<query>"               检索：先本地，再渠道；结果落入候选
lit get <identifier>             取得论文：本地优先，必要时补元数据/补全文
lit open <work_id>               直接读本地全文（零网络）
lit ask "<question>"             检索带页码锚点的段落（不生成散文）
lit library stats|report|list|merges   库统计与待确认合并
lit library check                增量复查：撤稿/新版/OA 变化
lit export --format bibtex       导出引用
lit merge <a> <b>                确认合并候选

lit topics survey "<方向>"       ① 领域测绘（不足则补齐）
lit topics gaps <survey_id>      ② 缺口证据（自述句 + 稀疏术语对）
lit topics candidates <survey_id> ③ 候选课题（证据 × 算子，打分排序）
lit topics draft <candidate_id>  ④ 提交一个，产出章节骨架（绑锚点）
lit topics rate <topic_id>       ⑤ CCF 评级预估（上界/分档/依据/风险）
lit topics save <topic_id>       ⑥ 落库 + 导出 Markdown + 退役去重键
lit topics list|show|venues|operators   历史 / 详情 / CCF 目录 / 算子目录
```

所有命令支持 `--pretty`（人读）与 `--offline`（禁止联网）。退出码：`0` 成功、`2` 用法错、`3` 未找到、`4` 部分成功（渠道有失败，或语料薄到不足以挖掘）、`5` 失败。

`lit contract` 以机器可读 JSON 返回全部规则，**包含三个模块的边界声明与课题生成的规定步骤**——契约住在代码里，而不是会漂移的文档里。
