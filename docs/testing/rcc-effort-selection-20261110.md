# RCC 思考等级选择开发验证

基线 `2af4ce733c799c2dae4aecc49e9df59f8dac9869`；分支 `feature/rcc-effort-default-20261110`；工作区 `/media/main/hongbo/mindfs-rcc-effort-dev`。本轮仅修改 MindFS 的 RCC 目录元数据、现有菜单与输入栏、会话默认处理及必要测试和说明。没有修改 RCC 私有仓库、运行端 settings 或正式容器，也没有发模型请求。

## 行为与优先级

RCC 状态声明协议级 `efforts=[low,medium,high,xhigh,max]` 和 `default_effort=high`。这份列表来自维护者对运行机官方 CLI 2.1.317 `--help` 的核查。模型别名继续保持原列表，不添加版本、价格或账号能力声明。菜单提示“默认 high；选项来自运行端 CLI，当前模型与账号的兼容性由运行端验证”。全局 probe 仍只检查安装。

此前别名条目没有逐模型 effort 能力，AgentSelector 与 ActionBar 都要求选中模型声明 `supportEffort`，因此没有显示入口，并在发送前滤掉 effort。现对 RCC 使用明确的协议级选项，运行端默认模型与显式 opus 等别名都能调节。恢复会话时若会话状态先于目录返回，ActionBar 会等待能力数据，不再提前清掉已经保存的等级。

发送优先级为当前明确选择、已有会话保存的 effort、记忆的用户偏好、RCC 初始默认 high。显式模型也应用该规则；已有空 effort 会话下一轮采用默认。空偏好不会覆盖 high，用户使用其他等级后沿用上游“记住上次选择”的默认行为。非 RCC 默认规则保持；ActionBar 发送时新增 fallback 限于 RCC。

等级变化沿用现有重开与 `--resume` 机制，选中值经 SDK `--effort` 传到官方 CLI。运行端本人 settings 已由维护者设置 high；该设置没有通过本机 Claude/provider 推测或修改。历史会话 effort 字段为空只说明 MindFS 当时未显式传该参数，无法由此还原历史 opus 内部实际采用的等级。

## 实际验证

- Go 1.25.8：`go test ./server/internal/agent/... ./server/internal/api/usecase/... ./server/internal/preferences/... -count=1`，通过。
- `go test -race ./server/internal/agent ./server/internal/agent/claude ./server/internal/api/usecase ./server/internal/preferences -run RCC -count=1`，通过。
- `go build -buildvcs=false ./server/...`，通过。沿用本机父目录 Git 布局所需的 stamping 关闭参数。
- `npm run typecheck`、`npm run build`，通过。构建仅写本 worktree；依赖临时链接到既有缓存，交付前删除链接。Vite 仍有既有大 chunk 与 Lexical 注释提示。
- `CHROMIUM_PATH=... node --test web/tests/rcc-effort.e2e.test.mjs`，通过。真实 Chromium 加载实际 ActionBar/AgentSelector 和受控 API fixture，覆盖新会话、已有空 effort 会话、已有 low 会话。新会话明确选 opus，发送实际 callback 得到 high；已有 low 保留 low。三种场景均打开真实思考等级菜单，检查五个选项和运行端兼容性说明，选择 max 后实际发送得到 max。
- SDK 隔离假 RCC 子进程逐一检查五个 effort 的实际 argv，同时检查 `--model opus`、`--resume existing-remote-session`。既有测试继续检查 high→low 重开后的模型/恢复参数。
- usecase 回归检查显式 opus、空模型、legacy 空 effort、保留已有 max、当前 medium 覆盖 max，以及非 RCC 显式模型空 effort 语义。preferences 回归检查空偏好保留 high，显式 low/max 正常记忆。RCC 安装检测测试检查默认与选项，同时继续拒绝临时 probe 会话。
- `git diff --check`，通过。

本轮未验证账号在各模型上对每个 effort 的实际支持，未运行生产模型请求或完整生产 HTTPS/E2EE 调用。取消 stopping 问题不在本轮范围。维护者负责后续独立测试、主审和部署。

## 独测返修：同一 RCC 切模型保留等级

独立测试发现选 max 后从 opus 切 fable，ActionBar 的通用 `onAgentChange` 无条件应用默认，将 effort 重置为 high。开发回归在修复前稳定复现 `high != max`；现仅在同一 RCC agent 内保留当前 effort，跨 agent 与非 RCC 仍使用原默认行为，模型与账号兼容性继续交由官方 CLI 验证。

新增浏览器检查覆盖新会话、已有空等级和已有 low 三种场景：选 max 并发送后切 fable，等待实际发送 callback 的 model 成为 fable，再断言 effort 为 max，避免把前一次 callback 当作通过。修复后该浏览器回归与 `npm run typecheck` 通过。本次没有改 Go；按受影响范围不重复 Go 回归或构建，不改独测文件和生产。
