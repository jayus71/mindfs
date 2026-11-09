# RCC agent 独立测试（2026-11-09）

MindFS 的 RCC 接入已通过真实链路的双轮对话、节点文件读写与 Bash、AskUserQuestion 回答、指定远端会话恢复，以及 turn context 取消后的同一 MindFS 会话续发。官方 Claude Code 使用隔离 loopback mock，生产服务与官方凭据均未访问。六项实际链路用例均退出 0，本轮 native 会话均经 RCC list 确认 stopped/stopped。

## 固定版本与隔离范围

开发固定 SHA 为 `c0c78168577d1649b3d78143c9af4f096925f1b5`；正式独测工作区为 `/media/main/hongbo/mindfs-rcc-independent-20261109`，分支为 `test/rcc-agent-independent-20261109`。双轮、恢复、工具与 context 取消的测试基线为 clean `81acced715c8637dc52e69409dc6b95fc2f0ba81`；增加 UI 取消 API 场景后使用 clean `004871d3ef6d06acec7368bce599e819ed84eac1`。这两次基线的产品代码均逐字节来自同一开发 SHA。

RCC 源码从固定 `56de616a3db3b960e4b0f28d62919942ad1f5b26` 建立独立 detached worktree `/tmp/mindfs-rcc-independent-20261109/rcc-source`，由 Go 1.25.8 以 `go build -mod=vendor -buildvcs=false` 分别构建三组件。正式用例的主机客户端与两 VM 均使用这组固定来源构建；初期从活动主目录构建的二进制不计入最终结果。

| 组件 | 最终 SHA-256 |
| --- | --- |
| RCC | `ce0a2ca1d201283fec28174163cd58bff86344bfb5f11d8c41b3d1834a78f0d3` |
| reach | `a1fa0fd1f9976503a5cb3e96bb6609974953c7d0d5445494ee0698c190694dd7` |
| helper | `c72f7480a26fa786d7c67fc94ebb252301687db0355f2fd5783d835389cd1944` |
| 官方 Claude Code 2.1.317 | `eb224419e344575faa4a1f39b290b649425a10cd5ee2ef1d003480cd9ae57eb0` |
| 本轮 Python Anthropic mock | `c8a147989b11e8fa941000fc268d0ebf3a92ad89339d49a32d83cb5e1b92475b` |

实际链路为 MindFS Pool → Claude Go SDK → 主机真实 RCC → HTTPS/WSS → 运行机 VM 的 RCC serve/web → 普通 UID 2285 的官方 Claude Code → 运行机 loopback mock。文件工具经 reach/helper 连接另一台工作节点 VM。官方 CLI 在测试包装内仅设置进程级 `BUN_JSC_useJIT=0` 适配 TCG，原官方二进制未修改。主机与 VM 使用本轮隔离 HOME、测试账号和固定 mock key。

两 VM 使用本轮新建 overlay，位于 `/tmp/rcc-task87s3-mindfs-independent-20261109/{node,runtime}`；SSH/HTTPS 端口分别为 loopback 36287、59235、39295。只读 checkpoint 的 SHA-256 为 `3e698788109939a4b9965e210883b677d9e75d10c9d503acdcd9685c2d7d4e4c`。未操作旧 VM 状态、其他任务、现有 MindFS 服务或运行配置。RCC 主工作区仅曾产生并已删除本轮 Python import 缓存，未修改产品源码；后续导入禁写 bytecode。

## 结果与证据

| 场景 | 结果 | 实际证据 |
| --- | --- | --- |
| 双轮对话 | 通过，16.467 秒 | 同一 SDK 进程连续完成两次 SendMessage；两个 prompt 均到达 mock，收到两个规范化文本事件；native 会话在 Close 后 2.151 秒确认 stopped/stopped。 |
| 远端恢复 | 通过，16.131 秒 | 新 SDK/RCC 进程使用上一轮官方 UUID 恢复，UUID 保持一致，mock 请求包含先前两轮历史与本轮新 prompt；停止确认 1.786 秒。主机隔离 HOME 未提供本地 Claude 历史。 |
| Write/Read/Bash/AskUserQuestion | 通过，36.973 秒 | 文件实际写入工作节点，主机同路径无新增文件；Bash tool_result 含预期 stdout，AskUserQuestion 到达 MindFS 回调并回传 Blue，最终 tool_result 含该回答；停止确认 2.154 秒。 |
| turn context 取消及同 key 续发 | 通过，53.864 秒 | 在待回答问题处取消 context；旧 native 会话 5.303 秒确认 stopped/stopped；Pool 同 key 创建新 RCC 进程，恢复同一官方 UUID 并完成续发，两个 native ID 最终均 stopped/stopped。 |
| CancelCurrentTurn API | 通过，50.839 秒 | 调用 UI 使用的取消 API，旧 native 会话在 7.355 秒确认 stopped/stopped；同 key 续发保持官方 UUID，最终新旧 native 会话均 stopped/stopped。 |
| 外部 SIGTERM | 通过，15.648 秒 | 本机真实 RCC 子进程在 301.338 毫秒退出，随后 2.231 秒查询确认本次 native ID 为 stopped/stopped。 |
| 真实 RCC 非零诊断 | 通过 | 无效 RCC 参数在真实客户端产生 exit 1；OpenSession 错误保留 exec.ExitError 与“客户端参数无效”stderr 诊断。 |
| probe 与历史边界 | 通过 | 全局 ProbeOne 在可执行存在时不执行配置命令，即使配置含 --confirm-project；RCC 外部历史 importer 返回不支持。 |

`go test -p 2 ./server/internal/agent ./server/internal/agent/claude ./server/internal/api/usecase -count=1` 在 clean `81acced` 全部退出 0。该回归包含开发提供的模拟 RCC 进程测试，用来覆盖 argv 的 `-- -p` 边界、SDK control request/response、退出码和 stderr；上表前六项另经实际 RCC、官方 CLI、两 VM 与 mock 验证。

独测新增代码仅位于 `server/internal/agent/rcc_independent_*_test.go`、`tools/rcc-independent/` 和本报告。Go 独测文件仅在 Linux 构建；实际用例默认跳过，需显式提供本轮私有 fixture。公开文件不包含 RCC 源码、VM 镜像、凭据或原始请求日志。

原始 stdout/stderr、受控 mock 请求和 VM 状态位于本轮私有目录；可提交摘要见 `tools/rcc-independent/results.json`。测试二进制、散列核对与用例输出位于 `/tmp/mindfs-rcc-independent-20261109`。复现入口为：

```sh
python3 tools/rcc-independent/run_isolated.py \
  --rcc-source <固定 RCC 源码树> --state <本轮隔离状态目录> \
  --rcc <固定 RCC 二进制> --test-binary <独测 Go 二进制> <场景名>
```

初期 mock 仅返回 SSE，导致官方 set_model 的非 stream 模型验证读取 usage 失败；本轮补齐标准 JSON/usage 响应，原失败保留于私有 `basic-initial-fixture-error.{log,json}`。用户要求暂停时已关闭自有 VM；恢复后确认 VM 的 /tmp 项目目录消失，重建目录并备份本轮旧绑定/会话状态后，使用 project-b 重新建立固定绑定。首次 Close 查询返回 stopping，随后确认 stopped；正式检查按用例打开前后 native ID 的差集限定本次会话，最多等待 20 秒，只有实际查询到 stopped/stopped 才通过。

最终官方 `rcc list` 包含 9 条本轮隔离 native 会话（包括一次等待停止确认的诊断运行），全部为 stopped/stopped。

本轮未发现需要开发返修的 MindFS 产品问题。停止收敛与客户端退出均按实际观测分别记录，未把 stopping 计为通过；生产部署和真实模型请求未纳入本轮。

收尾时已核验并关闭本轮两台 QEMU（node PID 3254604、runtime PID 3254614）；三个 loopback 端口均已无监听，自有测试进程已退出。仅保留私有 overlay、隔离授权状态和证据供审阅，未提交或推送到公开仓库。
