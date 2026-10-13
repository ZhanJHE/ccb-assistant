# 开发这套代码时的约束

本文件只在你的操作触及 `src/ccb/` 时才会进入上下文。使用模式下的规则见仓库根的
`AGENTS.md`。

- **依赖方向自内向外**：`core ← library ← search ← topics`。`core` 不 import 自家模块。
  `tests/test_modules.py` 解析真实 import 图，越界即失败。
- **唯一写路径**：所有库变更走 `library/store.py`，记录 / 索引 / 账本一起写。
  没有任何模块应该自己打开 `works/` 写文件。
- **派生件可弃**：`index.sqlite`、`blobs/**/passages.json` 必须能从文本与记录重建；
  `read_passages` 已按 `source_sha256` 自愈。不要新增"必须手动 reindex"的步骤。
- **磁盘格式变更 = 迁移 + 测试**：`papers/` 是使用者的唯一数据副本，没有第二份。
- **包名是 `ccb`，没有旧名兼容层**：不要新增 `lit` 别名、shim 文件或 `LIT_*` 环境变量；
  `tests/test_naming.py` 会失败。
- **三个面共用一张操作表**（`src/ccb/ops.py`）：新增一个操作只需在表里声明一次，
  CLI / MCP / 契约三面自动派生并互相校验（`tests/test_ops.py`）。不要往 `cli/_handlers.py`
  或 `mcp_server.py` 里手写第三份。
- **契约是可执行的**：`contract.py` 里 `kind: command` 的每条命令都会被测试实际解析
  （`tests/test_contract.py`）。改了 flag 就要改契约。
- 提交前：`ruff check src tests` + `python -m unittest discover -s tests`（当前 305 用例，无网络）。
