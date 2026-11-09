# RCC agent 独立测试（2026-11-09）

测试范围为 MindFS fork 的 RCC agent 接入。隔离环境使用新建的运行机 VM 和工作节点 VM；生产服务、生产 Claude 授权及官方凭据均未访问。报告以最终固定开发 SHA 与独立测试 SHA 补齐后交付。

## 环境与复现

MindFS 上游基线为 `6768bc1e5180bea0c16b435bdc6e87c40c51602b`，开发分支为 `feature/rcc-agent-20261109`，独测分支为 `test/rcc-agent-independent-20261109`，独测工作区为 `/media/main/hongbo/mindfs-rcc-independent-20261109`。Go 为 1.25.8（`/tmp/rcc-setup-token-74/go/bin/go`）。

RCC 从产品代码 `56de616a3db3b960e4b0f28d62919942ad1f5b26` 构建，使用 `go build -mod=vendor -buildvcs=false`，未修改产品实现。二进制 SHA-256：

| 组件 | SHA-256 |
| --- | --- |
| RCC | `7b155de87402685e12e3b9defc4eb9e5f76c5c26c731b564767a231152276e5e` |
| reach | `3fa671852e19969f14b92650a11f0ba9099b48f284f8fbfd6c82075e55387927` |
| helper | `25c8e210330793ad42732db863559a67be6f7d98b317d36ad3615ee109af071c` |
| loopback mock | `4d0f6404677b6d68b34b226a8cdcd1f19acbca57bcb4ae8870032a1485f692e9` |
| 官方 Claude Code 2.1.317 | `eb224419e344575faa4a1f39b290b649425a10cd5ee2ef1d003480cd9ae57eb0` |

VM 基于只读 checkpoint `/tmp/rcc-task85-os-proof-67_giq3o/integration-checkpoint.qcow2`，SHA-256 `3e698788109939a4b9965e210883b677d9e75d10c9d503acdcd9685c2d7d4e4c`，建立独测专用 overlay。状态位于 `/tmp/rcc-task87s3-mindfs-independent-20261109`。旧 `/tmp/rcc-task87s3-integration-4ibdb_kh` 已确认处于 `stopped-and-ephemeral-secrets-removed`，其 overlay 不存在，本轮未改动旧状态。

实际链路为 MindFS Pool → Claude Go SDK → 主机真实 RCC 二进制 → HTTPS/WSS → VM 中的 RCC serve/web → 普通 UID 2285 的官方 Claude Code → 运行机 loopback mock；文件工具经 reach/helper 连接独立工作节点 VM。测试进程与官方 CLI 使用隔离 HOME；mock API key 为固定测试值。为适配 TCG，VM 官方 CLI 启动包装仅设置进程级 `BUN_JSC_useJIT=0`，原官方二进制未改动。

独测入口：`server/internal/agent/rcc_independent_integration_test.go`、`server/internal/agent/rcc_independent_boundary_test.go`、`tools/rcc-independent/run_isolated.py`。正式测试使用固定 clean 提交构建测试二进制，再按 basic、resume、question、terminate、cancel-resume 逐项运行。证据只记录测试 prompt、受控 mock 响应与本轮隔离会话。

## 结果

待固定开发 SHA 后执行。
