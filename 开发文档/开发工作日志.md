# 开发工作日志

> **记录范围（硬性）**：只记录**开发相关工作**——提交、功能、修复、设计决策、已知问题与遗留。
> **不记录**：使用数据、用户行为、具体课题、论文、研究方向等内容性信息；涉及数据迁移时只写
> "外部文献工作区数据迁移"，不展开来源内容。
>
> **格式**：`## YYYY-MM-DD` 按日期正序，最新日期写在最上方；每条挂提交哈希可追溯。
> 每个开发会话收尾时**追加当日条目**（AGENTS.md 开发模式硬规则第 4 条）；没有提交的会话不写。

---

## 2026-10-13（续三）· 评审发现修复（四阶段）

- **评审**：全项目复评，得 27 项发现（严重 7 / 中 13 / 轻 7）。四层子代理并行审，结论**逐条自验**：
  实验推翻了子代理 3 条（SKILL.md "越界"——渲染剥离 front matter 后是 8169，未越界；文档行数
  "全表漂移"——那是按总行数算，文档口径是非空行；块键第二前缀其实有写入），也推翻了 2 条
  "死代码"（`Param.choices` 在用；`cite.include_notes` 在无字段记录上会触发）。
- `c0631a6` **身份以归一化值为准**：`compute_work_id` 算了 `normalize_doi` 却仍取原始值，同一篇论文
  按 DOI 写法分叉（真实库 165/787 条与重算不一致）。新增 `normalize_url` 与 `_ID_FIELDS["url"]`，
  `work_id_from_keys` 同步。**迁移只走显式命令**：`repair --reidentify`（含 `--dry-run`），旧 id 进
  aliases 且保留在索引中，先前回传过的 id 不会失效。同批：`resolve()` 文件名兜底改为直接读文件
  （把转义 stem 回灌成 id 使 DOI/标题键永远打不中）、每次建库只写一条 `work_created`、
  `check-files` 正斜杠归一（Windows 上把 89 个被引用 PDF 全报成孤儿，真实孤儿仅 10 个）。
- `a9856e3` **限速按主机生效**：速率表以渠道名为键、查询用 netloc，从未命中，所有主机退化为 1 rps，
  arXiv 声明的 3s/请求形同虚设。渠道新增 `ChannelSpec.hosts`，注册表按主机建表（最严者胜）；
  `spec` 改为实例级（`_apply_config` 原先改的是类属性）。同批：`Retry-After` 上限 60s、响应
  charset 参与解码、凭证脱敏补齐 `ChannelResult` / `Response.json()` / evidence `command` 三处、
  `Request()` 移入 try（无 scheme 的 URL 不再突破 "never raises"）、`find --stop-after`
  （并删除无调用者的 `Registry.fan_out/with_cap` 第二实现）。
- `584327c` **去重 / 分块 / 选题口径**：块键补 `x|` 桶（无年份记录原先永不参与模糊比较）并版本化
  自愈（`PRAGMA user_version`；老索引首查自动重建，4485 → 5957 桶）；自动合并门槛改看
  `title_sim`（0.875 标题相似 + 作者/年份加成曾达 0.92 而合并）；分块步进修复（边界落在重叠窗内时
  逐字符推进 → 单页 125 段）；`self_check` 改数索引行（此前只比文件指纹，缺行永远"健康"）且三个
  维护方法进锁；`pending_merges` 读归档；`save()` 的语料状态改在最外层解锁时写一次（`find` 每渠道
  一次锁），消除 O(n²)；内容寻址 PDF 补 fsync。选题：覆盖数改为**方向语料内**（原先分子是全库、
  分母是方向，小 survey + 大库会报"50 of 25"并把 novelty 归零），未测量不再写成 0
  （`--no-self-check` 或中文证据抽不出术语时权重重归一化，basis 记 `null`/`skipped`），候选键并入
  证据句子（同页两个缺口曾共用一个 id → 第二次 `topics draft` 覆盖前一条记录）。
- 测试：318 → 357 → 360。
- 决策：`模块设计.md` 的逐文件行数改为**量级**表述（连续多轮过期，文档自己也声明以代码为准）；
  `PAYLOAD_KEYS` 保持"按路径索引的第二张表"（不动 `Operation` 结构），改为在文档里写清机制。
- **真实库迁移（已执行并复核）**：`papers/` 先整目录备份（1100 文件 / 182.7 MB，
  存于 `Desktop\MyProject\ccb-papers-backup-20261013`，确认后即可删）；`repair --reidentify`
  迁移 **165/787** 条、失败 0、再跑为 0；**迁移前的 work_id 仍可解析**（aliases + 归一化 id 表）；
  `doctor` 无 problems；`check-files` 孤儿 99 → **10**（真实值）；独立复核身份漂移 165 → **0**，
  重复标题 0、空记录 0。
- **europepmc 全文 URL：已联网实证并修复**。真因**不是参数名**——`fulltextRepo?pprId=PMC…`、
  `pmcid=PMC…`、以及 API 自己声明的 `?pdf=render` 链接**全部 403**（新旧文章一致），换浏览器 UA
  仍 403：`europepmc.org` 对本客户端设了浏览器门（API 主机 `www.ebi.ac.uk` 通畅）。按项目策略
  "有浏览器挑战的明确报告、不做对抗"处理：**不再伪造 `pdf_url`**（它是永久死链，还让 `_fetch_pdf`
  每篇 OA 记录白试一个候选），改为把 API 声明的链接放进 `extras.fulltext_urls`（含人类浏览器可用
  的那条），并在渠道 notes 写明这道门。附带确认：preprint 记录本就没有 pmcid/OA 标记，原
  `pprId` 分支唯一触发场景恰好是它不该用的期刊论文。
- **待立项（本次实证发现的能力缺口）**：`https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/fullTextXML`
  实测 200 + 181 KB JATS XML（新旧文章均可），是欧洲 PMC 真正的全文通道；若要给它名副其实的
  `CAP_FULLTEXT`（无需 PDF 的生物医学全文），需新增 JATS→文本 解析，属功能而非修复。
- 遗留：`dblp` 不可达分支与 `candidates.WEIGHTS` 副本导出未清理（惰性，零行为影响）。

---

## 2026-10-13（续二）· 工程评审与四阶段修复

- **评审**：全项目软件工程自审，产出 14 项发现（严重 3 / 中 7 / 轻 4），按优先级排期执行。
- **凭据配置化**（`1a1cfd6`）：凭据源从环境变量改为 `papers/credentials.yaml`
  （平面映射，papers/ 整体 gitignore）；`ChannelSpec.auth` 语法 `env:VAR` → `VAR`
  （可选保留 `?`）；**基于值的脱敏**——加载的每个凭据值注册进注册表，快照 / 验证器
  缓存 / 报告写入前一律擦除（比模式脱敏更强，根治验证器 sidecar 可能泄漏 URL 内
  key 的问题）。`mailto` polite-pool 地址同源化。
- **topics 去耦合**（`a6a2c5a`）：`topics/commands.py` 的 28 处 `getattr(args…)`
  替换为 `TopicParams` dataclass——topics 层不再依赖 CLI 的 argparse 形状
  （import-DAG 测试查不出的隐式耦合）；CLI 与 MCP 两面各自组装。
- **索引加固**（同提交）：`connect()` 增加 `busy_timeout=5000`（懒重建并发窗口）。
- **一次性脚本清理**（同提交）：8 个迁移/审计脚本出库（git 历史保留）。
- **store.py 上帝类拆分**（`bb1f8c6`）：977 行 → 协调者 741 行 + 三个内聚组件
  （`ledger.py` 74 / `dedup.py` 99 / `fulltext.py` 103）；`DedupCandidate` 迁至
  `core/model`，`fs_safe` 迁至 `core/util`；死代码 `render_work` 删除。公共 API、
  单写路径、锁语义零变化；黑盒测试零改动。
- **过程记录（诚实）**：拆分的脚本化抽取两次失败（方法体空行终止提取、装饰器与
  def 的边界交互），均由 `git checkout` 恢复后改用手工精确编辑完成——自动化文本
  手术对含多行字符串的方法不可靠，黑盒测试网是唯一的施工安全网。
- 文档：`模块设计.md` 的 library 章节更新为组件化结构；测试 317 → 318。

---

## 2026-10-13（续）· 输出形状契约

- `f32cbb8` 全部 36 条命令路径的输出顶层键声明进 `ops.PAYLOAD_KEYS`，`ccb contract` 以
  `payload_shapes` 暴露；`test_ops` 锁声明完备性，`test_cli` 形状锁运行所有叶子命令
  （身份类命令用真实参数、构造最小含文本 PDF 走 add-file 链），断言"永不发出声明外键、
  干净运行与声明相等"。起因：验证脚本靠猜键名连错四次，违反本项目第一条铁律
  （规则从工具取，不要凭记忆）——契约缺口（C1 输出收口只做了 records_key 一半）与行为
  违规都已修正。
- `c17311e` 散文中的测试计数停止写精确值（连续三轮过期），改为 "300+"。

## 2026-10-13 · extras 修复 + 笔记进索引 + 数据可用性

- `26d5242` **审计抓到真 bug**：`to_work()` 只搬 claim 字段，`ChannelRecord.extras`
  被静默丢弃——数据迁移的 775 条用户批注全部丢失。修复：`extras` 成为 `WorkRecord`
  正式字段（附加可选，无迁移成本），`to_work()` 携带、`_absorb` last-writer-wins 合并、
  序列化往返。从原封未动的源索引重灌 770/775 条。
- 笔记进 FTS 暴露第二个问题：默认 tokenizer 把整段中文当一个 token，中文查询永远打不中。
  索引换 **trigram** tokenizer（旧形状检测 → 丢表自动重建）+ <3 字 CJK 查询的 LIKE 回退。
- 批量全文抽取：88/89 篇 PDF 抽取成功（1 篇旋转文本 PDF 如实报告无全文）；
  `ask` 在真实语料上首次给出 grounded 回答（8146 段落）。
- 数据质量审计：0 次模糊合并（222 个跨专题"重复"全是精确身份命中）；10 个字段冲突
  属实（作者格式变体 / camera-ready 标题变更 / 注记泄漏进字段），其中 8 条已由渠道
  数据（arXiv/Crossref/OpenAlex，trust 高于迁移源）接管显示，2 条等标识符。

## 2026-10-13 · 方法论 prompts

- `e7f0a08` 新增两个 MCP prompt：`ccb-idea-review`（三视角 fresh-eyes 子代理初审：
  子代理只喂草稿与锚点、主会话先核前提再采纳/打折、上限按贡献类型判断）与
  `ccb-topic-stitch`（模块缝合 + ABT 故事线，诚实规则写进模板：80% 组合是常态、
  结果报全、编造冲突=造假）。方法论来自用户工作区已验证的流程（P3 Idea 生成 /
  子代理评审 / 裁缝流水线）与外部叙事结构（And-But-Therefore）。SKILL.md 预算配平
  8169/8192。

## 2026-10-13 · 文档体系

- `3770681` AGENTS.md 增加"文档去向"规则：`开发文档/` 只放工具开发文档，
  `用户文档/` 只放用户科研资料，按内容归属不按说话者。
- `d48103f` + `21469d5` 用户科研资料从 `开发文档/` 拆出至根目录 `用户文档/`（拍平多余层级）。
- `ce70482` `docs/` 并入 `开发文档/`（设计定稿 / for-agents / 调研资料），README 与
  AGENTS.md 改为中英双语（英文在上、中文在下，内容一致）。
- 数据迁移：`94a9446` 外部文献工作区数据迁入本项目库（索引条目 → work 记录走
  upsert 幂等摄取；PDF 内容寻址存储并挂载；人类分析文档归入文档树）。

## 2026-10-13 · 健壮性四修

- `275ee06` 来自改进审计的四项：①跨进程互斥锁（msvcrt/flock，按路径可重入，
  全部变更方法挂装饰器；双进程竞态测试 2×15 upserts 零丢失）；②抽取尺寸守卫
  （20 MB，`CCB_MAX_EXTRACT_BYTES` 可覆盖）；③账本压缩 `ledger --compact`（归档
  append-only，`count_events` 跨 live+archive 保自检不变量）；④`check` 条件请求
  （Http 持久化 ETag/Last-Modified，crossref/openalex 304 短路为 unchanged）。
- 同批发现去重缺陷：`title_tokens` 丢弃单个数字 token，"仅数字不同"的标题被自动
  合并（真数据丢失）；改为保留含数字 token 并加回归测试。

## 2026-10-13 · 版本 0.4.0 与借鉴落地

- `6366865` 发布 0.4.0。此前六项借鉴落地（`fa48fed`…`dce12d2`）：SKILL.md 措辞级
  反幻觉规则 + `whenToUse`；for-agents 文档（实测 MCP 面 token 成本，测试锁定）+
  `install-skill`（四路径）；段落章节标注 + `ask --section`（CJK 章节标签）；证据
  `restricted` 标记；MCP prompts 面（三模板 + 协议能力位）。
- `f302ece` 四个同类项目的代码级借鉴调研（结论驱动上述六项）。

## 2026-10-13 · 大改造（六项）与改名

- `dc7ee39` 项目全量改名（产品名 CCB Assistant / 查查呗论文），**零兼容层**。
- `2803806` 两层 AGENTS.md（根 = 模式分流与铁律；`src/ccb/AGENTS.md` = 开发约束），
  凭据缺失可操作化。
- `50b2ccd` 共享地板纯/IO 拆分（util 纯计算，files 触盘）+ cli 拆包。
- `630e770` CI（ruff + unittest 双平台双版本）、ruff 规则声明、版本单一来源。
- `89d51e8` 文档与改名同步。
- `1a19d39` 首次 ruff 清零（47 处）。
- 过程修复：checkout 探测标记因 cli 拆包失效（`src/ccb/cli.py` → 无后缀
  `src/ccb/cli`），库根曾静默退回 cwd——由索引测试抓出。

## 2026-10-12 · 契约可执行与输出收口

- `5cbb352` 契约可执行化（每条 `kind: command` 被测试真实解析）；渲染器 `records_key`
  声明制——终结"渲染器猜 payload 形状"的崩溃。
- `960fc74` 渠道表区分"可用性"与"可达性"。
- `f9271dd` 讲解向 HTML（左侧标签栏 + 右侧长页布局）。
- `e375458` / `2ec98df` / `1467929` 工作区方案落档、每安装形态一个启动器、库根锚定
  到 checkout 可见的 `papers/`。

## 2026-10-11 · 立项

- `cb146fb` 初版：来源无关的论文获取 + 持久本地库（single-write-path、text-is-truth、
  self-check-first、local-first、no-overwrite、conservative-dedup、evidence-before-parse
  等不变量在此定型）。
- `f3d2c9a` 拆分三模块（search / library / topics）+ 共享地板，课题生成并入。

---

## 遗留与已知问题（滚动更新）

- **未推送 GitHub**：CI（ruff + 全量测试，双平台双版本）待首次 push 生效。
- **版本号**：0.4.0 之后已累积功能（健壮性四修、方法论 prompts、extras/索引升级），
  待发布 0.5.0（SKILL.md metadata 由测试同步）。
- **推迟项**：topics watch（订阅式发现）、引文图、Zotero 桥、输出 TypedDict 铺开、
  mypy（core 严格）、覆盖率门槛、`topics idea` 存储操作。
- **topics draft/rate/save 成功态形状**：已声明（自 handler 代码），但形状锁测试中
  走 unknown-id 子集断言——待真实使用产出候选后收紧为相等断言。
- **两个 t: 键记录**（缺强标识符）：字段冲突保持用户措辞，等用户提供 DOI 后
  `ccb get doi:…` 一条接管。
- **推迟**（工程评审 #4/#6/#7/#8）：错误码常量化、ops 模板外移、generic.py 三拆、
  work 缓存上限。
