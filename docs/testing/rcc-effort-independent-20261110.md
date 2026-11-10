# RCC 思考等级独立测试

最终独测通过。被测产品固定 SHA 为 `6925897c5139340da797fdf2172ecb943301605e`，开发基线为 `2af4ce733c799c2dae4aecc49e9df59f8dac9869`。独立分支 `test/rcc-effort-independent-20261110`，工作区 `/media/main/hongbo/mindfs-rcc-effort-independent`。本独测仅新增独立测试与报告。

## 验证结果

实际 Chromium 加载真实 ActionBar 与 AgentSelector。新会话、已有空 effort 会话首次发送得到 `high`；已有 `low` 会话发送保持 `low`。实际菜单提供 `low/medium/high/xhigh/max`，用户选择 `max` 后发送回调包含 `max`。独测将 agent catalog 响应延迟 900ms，检查已有会话选择在能力目录到达后仍保留；刷新后重新加载已有会话的 `low` 正确恢复。刷新场景的后端会话由固定夹具提供，本测试没有模拟服务器保存新发送的交换记录。

首个产品 SHA `4d3a5b09fd6a94d14bd6fff6730795194c1ff1a5` 在选择 `max` 后切换同一 RCC 的 `fable` 模型，会把下一次发送 effort 重置为 `high`。独测通过真实浏览器复现并交回开发；最终 SHA 将同一 RCC 的模型切换改为保留 effort，独立测试复验三种会话场景均保持 `max`。跨 agent 默认规则沿用现有路径。

新增 usecase→Pool→真实 SDK 隔离子进程测试覆盖默认 high，以及显式 low、medium、xhigh、max。每轮检查实际子进程 argv 同时含 `--effort <值>`、`--model opus` 和 `--resume independent-resume`；effort 变化创建新 runtime，并使用 manager 中持久保存的远端绑定恢复。同一会话随后换模型的默认解析保留已有 effort。协议夹具不执行官方 CLI 或模型请求。

已有 SDK 参数测试逐一检查五个等级，RCC 安装探测测试继续确认全局 probe 不创建项目或进程。usecase 和 preferences 完整相关包测试通过，覆盖非 RCC 默认规则和偏好逻辑；代码审查确认协议级 capability 与发送 fallback 限于 RCC，非 RCC 的逐模型 effort 能力规则保留。用户已取消的 stopping 问题未纳入本轮。

## 实际检查

| 检查 | 结果 |
| --- | --- |
| `go test -race ./server/internal/agent ./server/internal/agent/claude ./server/internal/api/usecase ./server/internal/preferences -run RCC -count=1` | 通过，首个固定 SHA；最终返修未修改 Go |
| `go test -race ./server/internal/api/usecase -run '^TestRCCEffortIndependent' -count=1` | 新增真实 usecase→SDK 五等级与重开恢复检查通过 |
| `go test ./server/internal/api/usecase ./server/internal/preferences -count=1` | 全部通过 |
| `CHROMIUM_PATH=<已有 Chromium> node --test tests/rcc-effort-independent.e2e.test.mjs tests/rcc-effort.e2e.test.mjs` | 最终 SHA 两项通过，含延迟目录、切模型、刷新恢复与真实发送回调 |
| `npm run typecheck` | 通过 |
| `git diff --check` | 通过 |

Go 为 1.25.8。浏览器使用本机已有 Playwright Chromium，依赖通过临时 symlink 复用既有 node_modules，交付前移除；没有安装或部署。CLI 2.1.317 五个 effort 的 help 依据沿用维护者已核实记录，本轮未重复访问运行端账号。

## 范围与遗留

无剩余本轮返修项。本轮验证 UI 的真实组件发送回调、后端默认解析、持久会话绑定、SDK argv 和恢复行为；浏览器后端与 RCC 子进程均为隔离夹具。没有验证真实账号在各模型上对每个等级的兼容性，没有运行生产模型、读取凭据或修改运行端 settings。未 push 或部署。
