# RCC 模型选择开发验证

本轮基线为 `0b6f36a121fc1e555683e1246fb57a478998e952`，开发分支为 `feature/rcc-model-selection-20261110`，工作区为 `/media/main/hongbo/mindfs-rcc-models-dev`。修改范围是 MindFS agent 状态、RCC 默认参数、会话模型验证、现有模型选择器及必要测试和说明。未修改 RCC 私有仓库、运行容器配置或服务，未 push、安装或部署。

## UI 与目录范围

`/api/agents` 对 RCC 返回 `sonnet`、`opus`、`fable` 三个官方 CLI 别名。维护者使用运行机 Claude Code 2.1.317 的 `--help`（空临时 HOME、无模型请求）确认其示例声明。本轮 UI 将每项标为“运行端别名”，说明具体版本和账号可用性由运行端决定。用户在首轮前就能通过现有 AgentSelector 点击选中，选择值进入现有 `onAgentChange(agent, model)` 链路。

全局 prober 继续只检查安装；不存在临时目录、项目绑定、初始化会话或模型探测请求。别名列表没有具体版本、价格或 effort 声明。正常会话 `ListModels` 仍能读取该会话 initialize 的 `supported_models`；本轮不把它写入全局 catalog，不持久化或合并不同 agent/profile 的目录。完整模型 ID 的既有 API 透传保留，服务端不会把这份别名列表当成完整白名单。

菜单提供空值“默认模型”入口。新会话空值不发送 `--model` 或 `set_model`，由运行端官方 CLI 选择默认模型。测试发现 SDK 自带具体默认模型，现已在 RCC 专用 transport options 中清除该默认 argv；SDK client 的内部必填校验仍沿用 SDK 默认值。此修复只作用于 RCC。

已有会话显式模型切换沿用 SDK `set_model`；取消后的重建沿用 `--resume`、`--model`。空模型沿用已有 usecase 语义：已有会话保持当前选择，UI 对默认入口明确显示“新会话沿用运行端默认；已有会话保留当前模型”。effort 仍沿用现有 API：不同 effort 重开并恢复会话，别名菜单不推断 effort。

## 已执行验证

- Go 1.25.8：`go test ./server/internal/agent/... ./server/internal/api/usecase/... -count=1`。
- `go test -race ./server/internal/agent ./server/internal/agent/claude ./server/internal/api/usecase -run RCC -count=1`。
- `go build -buildvcs=false ./server/...`。默认 VCS stamping 在该机器的父目录 Git 布局下失败：Go 在 `/media/main/hongbo` 执行 `git status` 返回 128；关闭 stamping 后构建成功。
- `npm run typecheck`、`npm run build`。依赖复用主 clone 的只读缓存 symlink，构建只写本 worktree 的 `web/dist`；Vite 保留既有 Lexical 注释及大 chunk 提示。
- `CHROMIUM_PATH=... node --test tests/rcc-model-selection.e2e.test.mjs`：实际 Chromium 打开现有模型菜单 fixture，依次点击三个 RCC 别名和默认入口，断言实际 callback 值为 `rcc:sonnet`、`rcc:opus`、`rcc:fable`、`rcc:`，且不产生 session 请求。
- `git diff --check`。

Go 隔离子进程测试检查实际 SDK→假 RCC 的 argv：`--model sonnet --effort high --resume remote-history-id`；检查 `set_model remote-model` 控制消息；重新打开后检查 `--model opus --effort low --resume remote-history-id`。默认测试检查无 `--model`、无 `--effort`、无 `set_model`。保留原取消、超时、退出后 Pool 重建与恢复测试。usecase 回归检查 RCC effort 变化触发重开，以及完整模型 ID 不因静态别名菜单被拦截。

## 未测试边界

本轮没有启动生产 CLI 或真实模型请求，因此没有验证生产账号对三个别名的实际权限、别名解析出的具体模型、运行端拒绝某模型时的实际提示。浏览器测试验证真实选择器和 callback；argv、模型切换、恢复使用隔离 SDK/RCC 进程测试，未执行带生产 HTTPS/E2EE 的完整浏览器到运行端模型请求。独立测试与最终集成由维护者另行安排。
