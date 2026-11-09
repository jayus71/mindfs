# RCC agent 接入

Linux 工作节点上的 MindFS 现在可以通过内置 `rcc` agent 使用运行端的 Claude Code。MindFS 启动本地 RCC 客户端，RCC 把 SDK 的 stream-json 输入、输出和控制消息送到运行端；官方 CLI、账号凭据与原生会话历史保留在运行端。

## 使用

该功能位于本 fork 的源码中。构建需要 Go 1.25 或更新版本、Node.js 和 npm；在仓库根目录执行：

```bash
cd web
npm ci
npm run build
cd ..
go build -o mindfs ./cli/cmd
```

生成的 `mindfs` 使用同目录下的 `web/dist`。构建不会安装、重启或替换已有服务；实际切换版本时同时使用这两项产物。

先按 RCC 的发行方式安装客户端，并以运行 MindFS 的同一操作系统用户执行 `rcc login`，完成设备与工作节点授权。在准备使用的项目目录完成 RCC 项目绑定；默认 agent 配置不会自动确认项目。

启动 MindFS 后选择 `rcc`。安装检测只检查本地可执行文件；首次实际会话会检查登录、项目绑定和运行端连接状态。失败时会显示 RCC 退出码与最后 4 KiB stderr，例如需要运行 `rcc login`、首次项目需要 `--confirm-project` 或该项目已有活动会话。

可通过额外的 `agents.json` 指定二进制和 RCC 自身选项：

```json
{
  "agents": [
    {
      "name": "rcc",
      "protocol": "rcc",
      "command": "/path/to/rcc",
      "args": ["--profile", "/path/to/rcc-profile.json"]
    }
  ]
}
```

以 `mindfs -agent-config /path/to/agents.json` 加载。`args` 只放 RCC 自身选项，适配器统一追加 `-- -p` 和 Claude SDK 参数；不要自行加入分隔符或 Claude 参数。`env` 可用于隔离 RCC 客户端配置，秘密配置应放在用户私有目录。

需要由首次非交互调用确认项目时，可明确把 `--confirm-project` 加入该 agent 的 `args`。这会对使用该配置的每个首次项目绑定生效，应由使用者决定授权范围。它只确认 RCC 项目绑定，Claude Code 的项目信任和工具权限仍由运行端处理。

容器部署可在已设置 `RCC_NODE_ID` 的基础上显式启用 `RCC_CONFIRM_PROJECT=true`，由入口脚本生成上述参数。此开关默认关闭，适用于该容器实例已授权自动登记的各个受支持项目目录；设备和节点认证、官方 CLI 权限以及 RCC 目录支持约束继续生效。启用、关闭和重建步骤见[容器部署说明](CONTAINER.md)。

## 会话行为与范围

- 支持同一进程内多轮输入、流式回复、工具控制消息、AskUserQuestion、计划模式和 MindFS 开发者指令。
- MindFS 保存运行端返回的原生会话 ID；重新打开时通过官方 `--resume` 传回该 ID。调用取消、超时或客户端退出后，连接池移除失效句柄，下一次输入重新建立客户端并恢复远端会话。
- 关闭、取消和调用超时先向 RCC 客户端发送 SIGTERM，给它十五秒的远端停止清理时间，再执行最后的进程组强制终止。已回收的子进程不会再次接收信号。
- 同一 RCC 项目只允许一个活动会话。并行 MindFS 会话或任务应使用分别授权的项目目录；项目冲突由 RCC 返回具体错误。
- 模型选择器提供 `sonnet`、`opus`、`fable` 三个运行端官方 CLI 别名，首次会话前即可选择；选中的值通过 SDK `--model` 传入官方 CLI。别名由运行端解析，具体版本和账号可用性以运行端为准。新会话不选择模型时沿用运行端默认配置。模型子菜单保留“默认模型”入口。
- 这三个别名来自运行机 Claude Code 2.1.317 的 `--help` 声明。全局安装检测不创建项目、会话或模型请求，也不读取工作节点的 Claude/provider 配置。本轮全局菜单采用固定别名入口，不缓存或合并不同会话/profile 的 `supported_models`。正常授权会话已有 `ListModels` 可读取 initialize 返回的目录，但本轮未将它同步到全局菜单；菜单不声明账号已验证模型目录、具体版本、价格或 effort 能力。
- 已有会话选择显式模型时沿用 SDK `set_model` 控制消息；取消后重建与恢复时透传模型及远端会话 ID。effort 沿用既有显式 API 语义，变化会重开并恢复会话，别名菜单不推断 effort。已有会话中空模型仍沿用现有会话选择；“默认模型”的空值不强制覆盖已经选择的远端会话模型。
- 本轮不提供远端历史浏览/导入和指定消息分叉。调用历史导入或分叉接口会返回明确的不支持错误；不会读取工作节点的 `~/.claude` 冒充远端历史。现有通用 UI 的这些入口尚未按 RCC 隐藏。
- RCC 没有本地 provider 切换或凭据备份配置。运行端管理官方 Claude Code 与账号，工作节点仅保存 RCC 自身的客户端授权。

## 实现与维护

本次基线为 `6768bc1e5180bea0c16b435bdc6e87c40c51602b`，开发分支为 `feature/rcc-agent-20261109`。新增独立 `rcc` protocol，并复用已有 Claude session 的消息归一化和控制处理。

适配器使用现有 `claude-agent-sdk-go` 的 `WithTransport`、`NewSubprocessTransportWithRunner` 和 `SubprocessRunner` 扩展点，不修改依赖。上游 SDK 构造官方参数，RCC runner 在进程边界补齐自身选项、`--` 和必需的 `-p`。适配器保留实际 `exec.ExitError`，并在 SDK 丢弃读取迭代器错误的情况下向启动错误和待完成 turn 传递退出信息。stderr 尾部只在内存中有界保存，在失败时作为错误返回；沿用 MindFS 现有的错误展示与日志策略。

多轮真实进程测试同时发现了既有 Claude session 的 `sawMessageText` 跨 goroutine 写入竞争。本次让该状态由消息消费 goroutine 独占，并在唤醒下一轮之前完成重置。

MindFS 的 AGPL-3.0 许可与版权保留。本适配仅实现公开命令与协议边界，未复制 RCC 源码；RCC 作为独立安装的 MIT 程序使用，其许可证与版权由 RCC 发行物保留。

## 开发验证

本次自测使用 Go 1.25.8、Linux 与隔离的 Go 测试子进程，没有登录生产账号、读取或迁移官方凭据，也没有启动真实模型请求。

已执行：

- `go test ./server/internal/agent/... ./server/internal/api/usecase/... -count=1`：通过。
- `go test -race ./server/internal/agent ./server/internal/agent/claude -run RCC -count=1`：通过。
- `go test ./server/internal/api/... -run 'Test.*(Provider|AgentConfig|Session)' -count=1`：通过。
- `go build ./server/...`：通过。
- `npm ci --ignore-scripts --no-audit --no-fund`、`npm run typecheck`、`npm run build`、`node tests/agent-lifecycle-restart.test.mjs`（`web` 目录）：通过；构建仍有上游的大 chunk 与 Lexical 注释提示。

RCC 进程测试覆盖实际 SDK 的 argv 分隔、cwd、环境变量、initialize、双向工具控制、多轮输入、远端 ID 恢复、调用取消/超时后重开、非零退出与 stderr 诊断、禁用临时探测/本地历史、以及超过五秒的远端清理。假 RCC 进程通过真实 stdin/stdout 管道与 SDK 交互；实际 RCC 隔离链路由独立测试角色另行记录。

实际 RCC、官方 CLI 与模型夹具的独测条件和结果见[独立测试报告](testing/rcc-independent-20261109.md)。维护者另执行了 `go vet ./server/internal/agent/... ./server/internal/api/usecase/...`、CLI 构建和构建产物的 `--version` 检查，均通过。
