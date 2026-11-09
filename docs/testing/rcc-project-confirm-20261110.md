# 容器 RCC 首次项目自动登记开发验证

基线为 `c7a48657cb5b553891a2667e6a0ee2249e8236ce`，分支为 `feature/rcc-project-confirm-20261110`，工作区为 `/media/main/hongbo/mindfs-rcc-project-confirm-dev`。本轮修改容器 Compose、入口脚本、环境示例、相关说明及必要测试；没有修改 RCC 仓库、MindFS 通用默认 agent 配置或生产容器。

## 行为

Compose 新增 `RCC_CONFIRM_PROJECT`，默认 `false`。操作者为该实例明确设置 `true`，并已设置 `RCC_NODE_ID` 时，入口脚本生成 `rcc --node <ID> --confirm-project` agent 参数。SDK 随后补齐 `-- -p` 与官方 CLI 参数，确认开关留在 RCC 侧。各个受支持项目目录首次使用时可自动完成 RCC 绑定登记，之后由 RCC 复用既有绑定。

每次容器启动都按当前环境重建生成配置。持续启用时重启保留此行为；关闭并重建容器后生成配置不再带确认开关，已经登记的 RCC 绑定不受影响。未设置节点时不会因为该开关创建额外 agent。非法布尔值在入口阶段报错，避免静默忽略配置。

只读核查了 RCC 客户端的凭据获取、项目解析和确认调用路径：凭据获取仍发生在实际会话入口前；`--confirm-project` 仅在非交互项目解析返回 `confirmation_required` 时使客户端提交确认请求。它不修改官方 CLI 参数或权限。节点认证、HOME 根目录内部状态、父子重叠目录等现有约束继续由原路径处理。本轮没有把 HOME 作为验收项目，也未扩大容器挂载范围。

## 自测结果

- `python3 -m unittest discover -s deploy/container -p 'test_*.py' -v`：18 项通过。新增测试覆盖默认关闭、显式关闭、启用、连续重启保留、关闭后删除开关、未设置节点和非法值。生成参数精确断言不含 SDK 分隔符；既有 Codex 环境导入与私有配置测试继续通过。
- `sh -n deploy/container/entrypoint.sh`：通过。
- 对 Compose 执行只读 `docker compose ... config --format json`，分别不设置、设置 `false` 和设置 `true`，生成环境分别为 `false`、`false`、`true`。仅解析配置，未启动容器。
- Go 1.25.8：`go test -race ./server/internal/agent/claude -run '^TestRCCSDKProcessRoundtripAndResume$' -count=1`：通过。真实 SDK 启动隔离假 RCC 子进程，检查 argv 前缀为 `... --confirm-project -- -p`，同时保留已有双轮、控制消息、模型、effort 和恢复参数检查。假 RCC fixture 显式接受并核验确认开关。
- `git diff --check`：通过。

本轮未启动真实 RCC/官方 CLI、未发模型请求、未部署镜像。维护者后续启用该实例环境并独立验证受支持的新项目目录首次登记；实际账号、运行端项目登记及官方权限行为不计入本轮开发自测。
