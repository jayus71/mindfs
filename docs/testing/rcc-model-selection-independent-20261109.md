# RCC 模型选择独立测试

独测通过，未发现阻断问题。被测产品固定为 `5d37e18b722010dcd4686ebac62d9e3c32890794`，其基线为 `0b6f36a121fc1e555683e1246fb57a478998e952`。独立分支为 `test/rcc-model-selection-independent-20261110`，工作区为 `/media/main/hongbo/mindfs-rcc-models-independent`。本报告与新增回归测试在同一独测提交交付；仅新增测试和报告，未修改产品。

## 核心结果

实际 Chromium 打开项目现有 AgentSelector 夹具，依次点击 `sonnet`、`opus`、`fable` 和默认模型入口，真实组件回调分别返回 `rcc:sonnet`、`rcc:opus`、`rcc:fable`、`rcc:`。操作期间没有 session API 请求。该检查复跑开发提交中的 Playwright 测试，使用独立 worktree 的源代码与本机已有 Chromium。

新增 Pool 边界测试覆盖空模型和全部三个别名，各自执行新建及带远端 ID 的重新打开，共八种组合。测试通过真实 SDK 与独立子进程管道交互，检查子进程收到的实际 argv：指定别名保留原值，恢复携带指定 `--resume`，空模型没有 `--model`，所有组合均不从别名推断 `--effort`。使用自定义 agent 名 `remote-alias-profile` 验证协议配置生效。

新增 usecase→Pool→SDK 隔离进程测试确认：首轮请求 `sonnet` 进入实际 `--model sonnet`；已有会话切换 `opus` 复用同一 runtime 并发送 `set_model`；随后空模型保留已有 `opus`，没有发送清空控制消息。开发原有 SDK 测试同时检查显式模型切换，以及 `--resume`、模型和 effort 在重新打开后的传递。

全局安装探测的已有独立边界测试通过：可执行文件中设置的启动标记没有产生。结合 RCC 分支直接返回安装状态的代码检查，探测只执行 `LookPath`，没有创建临时项目、初始化远端会话或读取本机 Claude/provider。返回的三项标为运行端别名，没有具体版本、价格、effort 能力或账号目录声明；完整模型 ID 的 API 透传测试通过。

## 实际检查

工具链为 Go 1.25.8、已有 Node/npm 依赖和 Playwright Chromium。Go 使用任务已有临时工具链，前端通过临时 symlink 复用主 clone 的依赖；交付前已移除 symlink。

| 检查 | 结果 |
| --- | --- |
| `go test ./server/internal/agent/... ./server/internal/api/usecase/... -count=1` | 通过，全部相关包；执行时产品固定为被测 SHA，尚未新增独测测试 |
| `go test -race ./server/internal/agent ./server/internal/agent/claude ./server/internal/api/usecase -run RCC -count=1` | 通过，含新增 Pool 八种组合 |
| `go test -race ./server/internal/agent ./server/internal/api/usecase -run RCCModelsIndependent -count=1` | 通过，含全部新增 Pool 和 usecase→SDK 测试 |
| `CHROMIUM_PATH=<本机已有 Chromium> node --test tests/rcc-model-selection.e2e.test.mjs` | 1 项通过，真实浏览器组件交互 |
| `npm run typecheck` | 通过 |
| `git diff --check` | 通过 |

## 验证范围与遗留

本轮检查真实 UI 回调、会话 usecase、Pool、SDK 参数与管道控制协议。浏览器 API 由本地夹具提供，子进程为隔离协议夹具；没有执行生产 HTTPS/E2EE 浏览器到运行端的完整模型请求。三个别名的账号实际权限、解析后的模型版本及运行端拒绝响应留待另行授权的真实账号联调。运行端 CLI 2.1.317 的只读 help 证据沿用维护者已核实记录，本独测没有重复登录或启动生产 CLI。

已有会话空模型保留当前选择属于本轮确认的 API 语义；菜单已说明“新会话沿用运行端默认；已有会话保留当前模型”。未发现需开发返修的产品问题。未连接生产服务、读取私有凭据、修改 RCC 私有仓库，未 push 或部署。
