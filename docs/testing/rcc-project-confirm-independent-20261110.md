# 容器首次项目确认独立测试

独测通过，未发现本轮容器接线的阻断问题。产品固定 SHA 为 `5a7b7f481f35dac930537e56eba3d96a19727012`，基线为 `c7a48657cb5b553891a2667e6a0ee2249e8236ce`。独立分支 `test/rcc-project-confirm-independent-20261110`，工作区 `/media/main/hongbo/mindfs-rcc-project-confirm-independent`。本独测只新增测试与报告。

## 结果

Compose 默认将 `RCC_CONFIRM_PROJECT` 传为 `false`，显式 `true` 才为生成的 RCC agent 加上 `--confirm-project`。默认和显式关闭均保留原参数；连续启动重新生成配置时启用状态保留，关闭后不再生成开关。未配置节点时开关本身不创建 RCC agent，非法值在入口阶段报错。原 Codex 环境导入、容器 HOME/PATH/XDG 保护、配置权限和来源不变性测试全部通过。

新增独测使用已发行 RCC 二进制、私有临时状态和只监听 loopback 的自签 TLS HTTP 夹具。没有构建或修改 RCC。测试通过实际入口脚本生成 agent 配置，将其 args 传给真实 RCC，并使用与 SDK 相同的 `-- -p --input-format stream-json --output-format stream-json --verbose` 边界。真实 SDK 的隔离子进程测试另行验证确认开关实际位于 SDK 分隔符之前。

真实 RCC 组合结果如下，所有调用均在 `/api/client/start` 启动边界前或边界处终止，没有启动官方 CLI 或模型：

| 入口设置 | 实际 resolve Confirm 序列 | 启动边界请求 | 模型 stdin 已读取字节 |
| --- | --- | --- | --- |
| 未设置 | `false` | 0 | 0 |
| `false` | `false` | 0 | 0 |
| `true` | `false → true` | 1 | 0 |
| 再次启动，仍为 `true` | `false → true` | 1 | 0 |

未启用时真实 RCC 返回原错误“首次项目绑定需要 --confirm-project”；启用后确认当前目录并到达启动边界。测试检查实际请求中的目录、确认标志和 Claude 参数，确认开关没有混入 Claude args。模型输入文件以 `y` 开头并携带标记文本，所有调用后的共享文件偏移仍为零，且未输出交互确认提示。这直接验证登记没有消费模型输入。测试同时保留导入的 Codex 环境，检查其容器 HOME 与导入字段在重建后正确。

## 实际执行

- `python3 -m unittest discover -s deploy/container -p 'test_*.py' -v`：产品提交的 18 项通过。
- `RCC_INDEPENDENT_BINARY=<已发行 rcc> python3 -m unittest discover -s deploy/container -p 'test_rcc_project_confirm_independent.py' -v`：新增独测通过，包含上表四个子场景。
- Go 1.25.8：`go test -race ./server/internal/agent/claude -run '^TestRCCSDKProcessRoundtripAndResume$' -count=1`：通过，实际 SDK 子进程 argv、模型控制和恢复行为保持。
- `docker compose -f deploy/container/compose.yaml config --format json`：仅解析配置；分别验证未设置、`false`、`true`，结果为 `false`、`false`、`true`。
- `sh -n deploy/container/entrypoint.sh`、`git diff --check`：通过。

已发行二进制为 `/media/main/hongbo/.local/share/mindfs-rcc-container/rcc-release/bin/rcc`，SHA-256 为 `e4e883f51825f0c8c91c78b7b5bb97f160ac725e26243de563b8ca2701c4b4d1`。夹具使用自行生成的假设备状态与自签证书，全部置于自动清理的临时目录，未读取生产凭据或调用生产服务。

## 范围与遗留

本轮确认的是容器配置到 RCC 首次目录登记的接线。夹具在启动请求处返回错误，不启动远端会话，因此没有验证真实节点的目录可接纳性、模型请求或权限提示。HOME 根目录、内部状态路径和父子目录重叠约束继续由 RCC 判断；该开关不改变这些约束，也没有证明 HOME 根目录或 `migration` 已可用。维护者正在另行调查的真实 `node_binding` 结果不属于本轮配置改动的修复结论。

无本轮产品返修项。未修改正式容器、私有 RCC 仓库或真实服务，未 push、部署或执行全量 Go 回归。
