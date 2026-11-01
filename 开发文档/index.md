# ccb 开发文档

`ccb`（查查呗论文）是一个文献检索与本地语料工具：所有合法渠道走同一个接口，
抓到的论文留在本地，同一篇不重查、不重下、不重解析。

这一页是开发文档的入口。本站只发布 `开发文档/`——设计、模块、方案与开发记录。
README、用户科研材料、语料数据都不在站内。

## 从哪读起

| 你是谁 | 读什么 |
|---|---|
| 想用这个工具 | 仓库 [README](https://github.com/ZhanJHE/ccb-assistant/blob/main/README.md)：安装、命令、渠道、凭据 |
| AI Agent | [给 Agent](for-agents.md)：两个入口面、各自的上下文成本、三条规则 |
| 要改代码 | [设计定稿](design/spec.md) → [模块设计](design/modules.md) |
| 想知道某个决定为什么这么定 | [仓库即工作区改造](decisions/repo-as-workspace.md) · [Europe PMC 全文通道](decisions/europepmc-fulltext.md) |
| 想知道做过什么、评审发现了什么 | 开发记录 |

## 文档地图

| 页面 | 内容 | 状态 |
|---|---|---|
| [设计定稿](design/spec.md) | 要解决什么问题、模块边界、身份与去重、检索与课题挖掘的口径 | 现行 |
| [模块设计](design/modules.md) | 代码现在长什么样、改一个东西要动哪些面、测试地图、维护手册 | 现行 |
| [仓库即工作区改造](decisions/repo-as-workspace.md) | 为什么数据根在 clone 内的 `papers/`，为什么 Git 只跟踪开发产物 | 已实施决策 |
| [Europe PMC 全文通道](decisions/europepmc-fulltext.md) | 为什么欧洲 PMC 的全文走 JATS 而不是 PDF | 已实施决策 |
| [开发工作日志](records/log.md) | 按日期的提交、修复、决策、已知问题 | 时点记录 |
| [工程评审（2026-10-13）](records/review-2026-10-13.md) | 一次完整的软件工程评审：结论、证据、复现记录 | 时点记录 |
| [同类项目借鉴调研](records/borrowing-survey.md) | 四个同类项目的代码级对照，以及哪些手法被吸收 | 时点记录 |
| [项目讲解](walkthrough/index.html) | 面向人的长文讲解（自包含 HTML） | 静态页 |

## 维护约定

1. 导航定义在仓库根的 `mkdocs.yml`。新增、改名、删除页面必须同步 `nav`，
   否则 `tests/test_docs.py` 会失败。
2. `开发文档/` 是唯一来源，站点不另存副本；`mkdocs build` 的输出 `site/` 不进版本控制。
3. 记录类文档（开发工作日志、工程评审、借鉴调研）保留写作当时的路径与提交哈希，
   不随目录调整改写。现行文档（设计定稿、模块设计、两份决策方案）必须指向当前路径。
4. 本地预览：

   ```bash
   python -m pip install -r requirements-docs.txt
   mkdocs serve
   ```

发布：`.github/workflows/docs.yml` 在 `main` 上构建并部署到 GitHub Pages。
