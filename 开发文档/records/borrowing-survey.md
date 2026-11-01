# 同类项目借鉴调研（代码级）

- 日期：2026-10-13
- 方法：在 `notes/02`（功能级扫描，2026-10-11）基础上，对 4 个最相关项目做 **shallow clone + 代码级阅读**；本文只记录功能对照表里看不出来的**实现层面手法**。
- 克隆位置：`%TEMP%\ccb-ref\`（临时，只读检查）

| 项目 | 规模 | 定位 | 与 ccb 的关系 |
|---|---|---|---|
| [openags/paper-search-mcp](https://github.com/openags/paper-search-mcp) | 34 源 / 134 文件 | 检索聚合（MCP+CLI+DSH skill） | 最大的"红海"样本；也是唯一同样发 DSH 技能包的 |
| [blazickjp/arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server) | 19 工具 / 115 文件 | arXiv 深度（LaTeX/引文图/订阅） | 单源纵深样本；MCP prompts/resources 面的参考 |
| [Future-House/paper-qa](https://github.com/Future-House/paper-qa) | src 25 文件 | LLM 文献问答（PaperQA2） | 上层消费者样本；验证 ccb"工具不写散文"的边界 |
| [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) | 498 文件 | Zotero 桥（MCP+CLI） | **Agent 文档模式**的标杆 |

---

## A. 直接可落地（小改动，高价值）

### A1. SKILL.md 增加"措辞级"反幻觉规则 —— 抄自 paper-search-mcp

他们的技能里有三条 ccb 没有的**输出措辞**规则：

> "Do not describe an abstract or metadata record as retrieved full text."
> "Discover the current tool list rather than assuming every source supports full text."
> "For speed, prefer a targeted set (`search_arxiv`, `search_crossref`) over multi-source search when the field is clear."

ccb 的诚实机制在**字段层**（`has_fulltext`/`outcome`/`errors`），缺**措辞层**：agent 拿到 `has_fulltext: false` 时该怎么说、多源搜索前该不该先定向、该不该假设某源有全文——这些 SKILL.md 没写。三条各一行，加进 `.dsh/skills/ccb/SKILL.md`（预算余量 ~170 字符，需压缩别处或外移）。

### A2. `for-agents.md` 模式 + 实测 token 成本 —— 抄自 zotero-mcp

他们的 [docs/for-agents.md](https://github.com/54yyyu/zotero-mcp/blob/main/docs/for-agents.md) 开头："This page is written for you; the README is written for people"，并且**实测了自己两个面的 token 成本**：

> "If you have a shell, prefer `zotero-cli`: the MCP server's tool schemas cost about **13.4k tokens on every request** whether or not they are used."

ccb 有一模一样的双面结构（`ccb.py` vs 16 个 `ccb_*` MCP 工具），但从未测过 MCP 工具表占多少上下文。做法：

1. 给 `ccb-mcp.py --list-tools` 的 schema 估算 token 数，写进 for-agents 文档；
2. 明确引导："有 shell 就用 `ccb.py`；只有 MCP 客户端时才挂 server"；
3. 顺手提供 `ccb install-skill`（把 `.dsh/skills/ccb` 装进用户项目或 `~/.dsh/skills`——zotero 的 `install-skill` 子命令就是这么做的）。

这与"控制 Agent 行为/省 token"的既有方向完全同路。

### A3. 章节级标注的段落索引 —— 抄自 paper-search-mcp `sections.py`

ccb 的 `passages.json` 是**页级**切块。他们的抽取带**章节标签**（abstract/introduction/background/methods/...）+ 有界并行 + 大小上限（20MB PDF、3MB worker 输出）。价值：

- `ask` 检索可按章节过滤（"只在 methods 里找"）；
- `topics gaps` 的局限句集中在 discussion/conclusion，章节先验能提高挖掘精度；
- 页码锚点不变，只是 chunk 多一个 `section` 字段。

落点：`core/extract.py` 的抽取结果加章节探测（正则 + 首行启发式即可起步），`passages.py` 的 `chunk_text` 透传。

### A4. `whenToUse` frontmatter —— 一行改动

agentskills.io 规范字段，paper-search-mcp 在用（"Use when the user asks to find, download, or read..."）。ccb 的 SKILL.md 有 `description` 没有 `whenToUse`。一行；对 DSH 的触发判断可能有帮助（需实测 DSH 是否读取）。

---

## B. 值得规划（中等改动）

### B1. MCP prompts / resources 面 —— 抄自 arxiv-mcp-server

他们除了 tools 还暴露 `prompts/`（compare_papers、deep_research_analysis、literature_review、summarize_paper——预置的多步工作流模板）和 `resources/papers.py`（论文作为 MCP resources）。ccb 的 `ops.py` 注册表加一个 `kind: "prompt"` 参数即可派生第三种面——**这正是操作注册表"声明一次、派生多面"的红利**。prompt 模板内容可直接源自 SKILL.md 的 canonical sequence（选题六步就是现成的 literature_review prompt）。

### B2. topic watch（订阅式发现）—— 抄自 arxiv-mcp-server `alerts.py` + scholar-feed-mcp

ccb 的 `check` 是**复查存量**（撤稿/新版本）；watch 是**发现增量**（某方向有新论文时提示，带 drain cursor 语义避免重复推送）。两者互补。落点：`topics watch "<方向>"` 存一个监视（查询串 + 上次检查时间），`ccb watch check` 拉取增量——数据结构可直接复用 `topics/index.json` 的模式。

### B3. 引文图遍历 —— 抄自 arxiv-mcp-server `citation_graph`（磁盘缓存）

ccb 的 openalex/crossref 有 `CAP_CITATIONS` 但没有图遍历工具。`ccb related <work_id>`（一跳引文/被引，落盘缓存）与 `topics` 天然衔接：引文图是"饱和度判断"和"稀疏术语对"的输入。

### B4. 证据缓存的隐私规则 —— 抄自 paper-search-mcp `search_cache.py`

他们的缓存**拒绝持久化凭据下取得的响应**：探测 `~/.netrc`、排除带 key 的连接器、只缓存白名单公共源。ccb 的 `evidence/` 现在 7 渠道全 keyless 风险低，但接 IEEE/Scopus 这类 entitlement 源时，**响应体可能含订阅权限下的内容**。落点：设计基线加一条"带凭据取得的响应不写 `evidence/`（或标记为受限）"——一行 `ChannelSpec` 字段 + 一个测试即可。

### B5. Zotero 桥 —— 抄自 zotero-mcp / zotero translation-server

notes/02 的结论（"Zotero 是唯一严肃答案"）+ 他们的连接模式表（本地 `:23119` / Web API / hybrid）。ccb 的落点：`ccb export --zotero`（写 Zotero）或把 translation-server（`:1969`，零认证、DOI→条目）作为一个 `http` 渠道声明——**后者其实零代码，一份 channels.yaml 就行**。

---

## C. 明确不抄的

| 不抄 | 理由 |
|---|---|
| 34 源全接（paper-search-mcp） | 红海；ccb 的组织层定位；且他们 34 源里含 `sci_hub.py` —— 许可红线，ccb 的"刻意不做"是对的 |
| 检索结果缓存（`search_cache.py` 320 行） | ccb 的库本身就是持久层，再加一层查询缓存是重复；但其**隐私规则**值得抄（见 B4） |
| PaperQA2 的 LLM 管线（evidence 打分、矛盾检测） | 依赖 LLM，违反"同输入同输出、工具不写散文"的立身之本 |
| 语义检索（arxiv-mcp 付费档） | 需要嵌入模型；BM25 确定性是卖点 |
| 论文落盘为 Markdown（arxiv-mcp） | ccb 的 blobs 是页级真文本 + 派生 passages，保真度更高；MD 是另一种投影，可后加 |

## 顺带确认了 ccb 的领先处（避免妄自菲薄）

- paper-search-mcp 的 `Paper` 模型是**单 ID 平面模型**（`paper_id: str` 一个字段）——证实双层身份（work/manifestation）是真实差异化；
- 他们的 CLI/MCP parity 靠 `CLI_TOOL_PARITY_PROVENANCE.md` 人工记录——ccb 是构造性派生 + `test_ops` 互证；
- 他们的技能没有契约工具——规则只能靠 SKILL.md 散文，而 ccb 是 `ccb contract` + 可执行测试；
- 四个项目都**没有**：字段级 provenance、账本、增量复查、跨源身份持久化——notes/02 的差距分析在代码级复核后依然成立。

---

## 落地建议（按优先级）

> **状态（2026-10-13）**：A1/A4 已落地（SKILL.md 措辞规则 + whenToUse）；A2 已落地
> （docs/for-agents.md + 实测 6197 字符 schema（~1.5k tokens）+ `ccb install-skill`，
> 测试锁定数字）；A3 已落地（core/sections.py + 段落 section 字段 + `ask --section`）；
> B1 已落地（MCP prompts 面，3 个模板，协议+测试）；B4 已落地（`sensitive_response`
> 声明 → 快照 `restricted` 标记）。**未落地：B2（topic watch）、B3（引文图）、B5
> （Zotero 桥）**，见文末"明确不抄的"之后的排期说明。

1. **A1 + A4**（半小时）：SKILL.md 三条措辞规则 + `whenToUse`。
2. **A2**（半天）：for-agents 文档 + 实测 MCP token 成本 + `ccb install-skill`。
3. **A3**（1–2 天）：章节标注进抽取与 passages，`ask` 加 `--section` 过滤。
4. **B1**（1 天）：ops 表加 prompt 面（选题六步即现成模板）。
5. **B2/B3/B5**：各自独立，按需求排期。
