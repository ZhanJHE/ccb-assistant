# Europe PMC 全文通道方案（含两处惰性清理）

> 立项依据：2026-10-13 评审的"项 2"联网实证（提交 `5f5bbd8`）。结论是 `europepmc.org` 的全文
> 页面（含 API 自己声明的 `?pdf=render`）对本客户端一律 403——浏览器门，按政策不绕——但 API 主机
> `www.ebi.ac.uk` 通畅，且 `…/rest/{PMCID}/fullTextXML` 实测 **200 + 181 KB JATS XML**（新旧文章
> 均可）。因此欧洲 PMC 的全文能力不该走 PDF，而该走 JATS。
>
> 顺带修掉评审里两处零风险的惰性清理。结构性重构（`generic.py` 三拆等）**不在本方案内**，另立。

---

## 0. 现状（为什么这是一个"缺口"而不是"优化"）

| 事实 | 位置 |
|---|---|
| `CAP_FULLTEXT` 只有声明，**全树没有消费者**：没有 `def fulltext`，没有 `chan.has(CAP_FULLTEXT)` | `search/channels/base.py:35`、`europepmc.py:38`、`arxiv.py:56` |
| 全文只能从**本地 PDF** 抽取（`extract_into`：PDF → 文本 → `store_fulltext` + `store_passages`） | `library/retrieve.py:119`、`acquire.py:334` |
| 已存的 pmcid 在 `extras["pmcid"]`（不在 `ids`，`KEY_CHAIN` 无 pmcid） | `search/channels/europepmc.py` |
| 证据快照 >256 KB 落 sidecar | `library/evidence.py:28` |

结论：欧洲 PMC 的 `CAP_FULLTEXT` 是**装饰性声明**；生物医学论文因此只能靠"找到 PDF 再抽"这一条路，
而 PDF 恰恰是被门挡住的那一半。

---

## 1. 目标与非目标

**目标**
1. 给 `europepmc` 一个**名副其实**的全文能力：对 OA 且 `inEPMC=Y` 的记录走 JATS XML，落 fulltext +
   passages，全程走既有单写路径与证据快照。
2. `get --extract`（既有的"要可读文本"语义）在没有本地 PDF 时也能拿到候选全文；
   `topics survey` 的补齐因此自动受益（它已经传 `extract=True`）。
3. 引用锚点**诚实**：JATS 无页码，绝不把"第 1 页"当作页码报出去。

**非目标**
- 不做浏览器门的对抗（政策：明确报告，不做对抗）。
- 不解析非 JATS 的全文（PDF 路线不变）。
- 不引入第三方依赖（`xml.etree.ElementTree` + `re`）。
- 不做 `generic.py` 三拆 / ops 模板外移 / 错误码常量化 / work 缓存上限（另立方案）。

---

## 2. 设计决策（含被否方案）

| # | 决策 | 被否方案与原因 |
|---|---|---|
| D1 | JATS→文本放在**新 `core/jats.py`**，纯函数（字符串进、结构出），归入 `test_purity` 的 `PURE` | 放 `search/`：`library` 重解析时也要用（与 `extract.py` 放 core 同理）；放 `library/`：会产生 `search→library` 之外的重复实现 |
| D2 | 渠道返回**已转换的文本**（`Channel.fulltext(work)`），不是原始 XML | 让 library 拿 XML 自己转：渠道才知道自己抓的是什么格式，且快照要按渠道落 |
| D3 | 触发条件 = `extract=True`，**不**绑定 `with_pdf` | 让"只要元数据"的 `get` 悄悄联网抓全文，违反最小惊讶 |
| D4 | 只有 OA（`isOpenAccess=Y`）且 `inEPMC=Y` 才抓；非 OA/无 XML 一律"报告拿不到" | 抓非 OA 全文越界；静默失败违反 `report-failures` |
| D5 | 锚点：`page` 保持 1，**新增非分页标记**，引用改渲染 `[work §Methods]` | 造伪页码（`page=2,3…` 按字数切）会在引用里说谎；完全不给 passages 又丢掉全部价值 |
| D6 | `Manifestation.fulltext_source` 为**附加可选字段**（dataclass 默认值 + 白名单序列化） | 改 schema 版本要迁移，而 `papers/` 是唯一副本 |
| D7 | XML 解析前**限长**（>4 MB 直接拒绝并报告） | 不设限：`ElementTree` 对实体膨胀（billion laughs）无防护；零依赖前提下只能用限长缓解，残余风险写进文档 |

---

## 3. 改动面

### C1 惰性清理（独立提交，零行为变化）
1. `search/channels/dblp.py:111-113`：删不可达的 bot 挑战分支（`request_json` 已在 `data is None`
   分支写好 `challenge_reason`，108 行先返回）。
2. `topics/candidates.py:510`：`"weights": WEIGHTS` → `dict(WEIGHTS)`（别把模块级字典按引用交出去）。
3. 测试：dblp 挑战体仍被识别为错误（走 `request_json` 路径）；payload 的 `weights` 改动不影响
   任何调用方；`_score` 的权重语义不变。

### C2 `core/jats.py`（新，PURE）
```
parse_jats(xml: str, *, max_bytes: int = 4_000_000) -> JatsDocument
JatsDocument: title, abstract, sections: list[(name, text)], text: str, warnings
```
- 取 `<article-title>`、`<abstract>`、`<body>` 下各 `<sec>`（`<title>` 作为**裸标题行**输出，
  让既有的 `detect_sections` 能认出来）、丢弃 `<ref-list>`/`<back>`/`<table-wrap>` 的表格体
  （保留 `<caption>`）。
- 嵌套 `<sec>` 展平，`<title>` 行同时充当分节边界。
- `text` 是最终落盘形态：段落之间空行，无 markdown 记号（保持与 PDF 抽取同样的纯文本约定）。
- 畸形 XML / 超长 → 返回带 `error` 的结构，**不抛**（与 `extract.py` 同约定）。
- 测试：真实响应裁剪成 fixture（含嵌套 sec、表格、ref-list）；纯/IO 分类（`test_purity` 会强制）；
  限长；畸形输入。

### C3 落盘与模型（`library` + `core`）
- `core/model.py`：`Manifestation.fulltext_source: str = ""`（`as_dict`/`from_dict` 白名单 + `_merge_manifestation` 补空字段）。
- `library/retrieve.py`：新增 `store_text(library, work, text, *, source, mid="") -> dict`
  —— `extract_into` 的非 PDF 孪生：`store_fulltext` → `attach_fulltext(..., fulltext_source=source)`
  → `chunk_text` + `store_passages(source_sha256=...)`。**仍然只走 `Library` 的写路径。**
- 测试：`fulltext_source` 往返；旧记录（无该字段）照常加载；`store_text` 产出 passages 且 digest 自愈
  语义与 `extract_into` 一致。

### C4 渠道能力 + acquire 接线 + 锚点诚实（`search`）
- `search/channels/base.py`：`Channel.fulltext(self, work) -> ChannelFulltext | None`，
  `ChannelFulltext = (text, source, url, ev_id, warnings)`；默认返回 `None`（无此能力）。
- `search/channels/europepmc.py`：实现它——读 `work.extras["pmcid"]` 与 OA/`inEPMC` 标记，
  GET `…/rest/{PMCID}/fullTextXML`（**同一主机，限速自动生效**），`snapshot()` 落证据，
  `parse_jats` 转换；无可抓时返回 `None` 并给出原因。
- `search/acquire.py`：`get` 在"无本地 PDF / 无全文"且 `extract=True` 且非 offline 时，
  向 `registry.usable(CAP_FULLTEXT)` 的渠道问一轮，成功则 `store_text`，动作文案写进 `actions`
  （`full text from europepmc (jats)`），失败写 `warnings`。**PDF 与 JATS 两条路互不阻塞**。
- 锚点诚实：`PassageIndex.set_metadata(work_id, title, year, paged=True)`；
  `Hit.citation` 在 `paged=False` 且 `section` 非空时渲染 `[work_id §<section>]`，否则维持 `p.x`。
  `ask` 从 `work.manifestations[*].fulltext_source` 判定是否分页。
- 测试：桩 `urlopen` 200（XML → 文本 + 证据快照 + passages + 引用带 `§`）；404/非 OA/preprint
  → 不请求或报告原因；`--with-pdf` 单独使用**不**触发；offline 不触发；非分页引用的渲染。

### C5 文档与版本
- `开发文档/设计定稿.md`：§2 渠道表补"欧洲 PMC 全文走 JATS（`CAP_FULLTEXT` 名副其实）"、
  §3 提及 `fulltext_source`、§7 合规补"仅 OA 子集"。
- `开发文档/模块设计.md`：`core` 表加 `jats.py`；§7 测试地图加 JATS 用例所在文件。
- `.dsh/skills/ccb/references/channels.md`：写清"europepmc 的 PDF 页面被浏览器门挡（403），
  全文走 `fullTextXML`；非 OA 不抓"。
- SKILL.md **不改**（当前 8169/8192，,任何新增都要等量删减——本次是内部行为变化，references 足够）。
- 版本 `0.5.0 → 0.6.0`（`src/ccb/__init__.py` + SKILL.md metadata，`test_naming` 会强制同步）。
- 收尾追加 `开发文档/开发工作日志.md`（含 5 个提交哈希与遗留）。

---

## 4. 提交与顺序

| 提交 | 内容 | 预估 |
|---|---|---|
| C1 | 惰性清理（dblp 3 行 + `WEIGHTS` 副本）+ 测试 | 15 min |
| C2 | `core/jats.py` + 纯分类 + 测试 | 45 min |
| C3 | `fulltext_source` + `store_text` + 测试 | 20 min |
| C4 | 渠道能力 + acquire 接线 + 引用锚点 + 测试 | 60 min |
| C5 | 文档 + 0.6.0 + 工作日志 | 30 min |

每步都跑 `python -m unittest discover -s tests` 与 `ruff check src tests tools`；不绿不进入下一步。

---

## 5. 验收标准

1. 全量测试通过（预计 360 → **≈372**）；ruff 干净。
2. `doctor` 无 `problems`；`check-files` 仍 `ok:89 / orphans:10`（不新增文件种类）。
3. **一次联网实测**：`get <某 OA PMCID 作品> --extract` → `actions` 出现 JATS 全文、`open` 可读、
   `ask "<该文关键词>"` 返回带 `§<section>` 锚点的命中；`show` 的 `fulltext_source="europepmc-jats"`。
4. **不兼容性检查**：老记录（无 `fulltext_source`）加载/保存往返无差异；`papers/` 不做迁移。
5. 非 OA 与 preprint 记录：`get --extract` 不产生任何 europepmc 全文请求（以桩断言）。
6. `CAP_FULLTEXT` 从"装饰"变为"有消费者"（`grep 'has(CAP_FULLTEXT)'` 有实现路径）。

## 6. 风险与回退

| 风险 | 处置 |
|---|---|
| XML 实体膨胀 | 4 MB 限长 + 仅可信主机 + 文档写明残余风险（零依赖下无安全解析器）；超限"报告拿不到" |
| 把非 OA 全文落盘（越界） | 只认 `isOpenAccess=Y` 且 `inEPMC=Y`；测试用桩断言"非 OA 不请求" |
| 误把 `page=1` 当页码引用 | D5 的非分页标记 + 引用渲染测试；`Passage.as_dict` 的 `section` 已有 |
| JATS 结构与预期不同（新标签） | 解析失败即返回 `error` 且**不落半成品**；只落"解析成功且文本非空"的结果 |
| 抓全文拖慢 `get` | 只在 `extract=True` 且无全文时问一轮；渠道限速沿用 `www.ebi.ac.uk` 的既有桶 |

## 7. 假设

1. 允许对 `www.ebi.ac.uk` 发少量真实请求用于验收（每篇 1 次；不抓正文以外的内容）。
2. Europe PMC OA 子集的全文可用于文本挖掘（按文章 license，逐条记在 `license` claim 里）；
   非 OA 一律不抓。
3. 只在 `papers/`（已 gitignore）落文本，不进仓库。