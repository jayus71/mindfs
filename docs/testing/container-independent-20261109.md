# MindFS 容器独立测试（2026-11-09）

容器候选通过本轮独测，F01 已关闭。`mindfs` 原命令、网页、真实 Codex 离线握手及 MindFS→Codex Go SDK→假 app-server 对话均成功；一次性复制后的 provider 可独立切换、删除，并随会话数据库跨重启和容器重建保留。非空 agent env 导入后，子进程同时保留导入键、当前容器环境和私有路径，重新生成的环境快照能更新运行变量并移除旧键。

## 固定来源

| 轮次 | 产品提交 | 实际镜像 ID | 完整通过时的独测夹具提交 |
| --- | --- | --- | --- |
| 基础 8 项 | `16a4ab9c0970a231f1308f872fe32d3bf54daab8` | `sha256:0599ebd803ad488ecf7faf5c9823cf800ce277175a4dff2da216bda1bccd7274` | `bae3d41eb9b398b4227effa971fb0ecf005cc913` |
| F01 定向复验 | `938f8bc0c1b761a22a486ef7506f57af75de1899` | `sha256:382a12315214ec5fe764d406337ba5918a832f0416a3dac09d005b4c69146cd8` | `2b5fae7f11aa8ee5ce608c4d441b2a473d6eb720` |

独测分支为 `test/container-runtime-independent-20261109`，工作区为 `/media/main/hongbo/mindfs-rcc-container-independent`。两个镜像均按完整 ID 固定复用开发产物，本轮未另行重建；构建来源、命令和日志见 [开发验证记录](../CONTAINER-VALIDATION-20261109.md)。独测核对开发交付相对原始基线 `1489e91ad07b8f1616f369f37f5b7d7519b47415` 的 Go、前端、module 文件、`agents.json` 和 `task_template.json` 无变化；F01 修改限于容器入口、部署检查与文档。

环境为 Linux amd64、Docker 29.1.3、Compose 2.33.0，镜像用户 UID/GID 为 1002/1001。基础轮与返修轮分别使用 `/tmp/mindfs-container-independent-ZACFJ2`、`/tmp/mindfs-container-independent-oNYcUv` 内的假配置、私有 HOME、单项目和只读夹具，主机回环端口分别为 59015、54231。

RCC 仅只读挂载已有完整二进制发行 `/media/main/hongbo/.local/lib/rcc/interactive-2cf97f2e87a0`；其 `bin/rcc` SHA-256 为 `e4e883f51825f0c8c91c78b7b5bb97f160ac725e26243de563b8ca2701c4b4d1`。私有 RCC 源码没有进入 fork 或镜像。

## 基础轮结果

| 验证 | 实际结果 |
| --- | --- |
| 一次性导入 | 显式导入假 provider、选择偏好、Codex config/auth 四个文件；目录 0700、文件 0600；再次导入退出 1。假历史、registry、relay 凭据及本地 CLI token 未复制。 |
| 运行隔离 | Compose 与实际 Docker inspect 确认独立 bridge 网络、非 privileged、回环发布端口；无 Docker socket、宿主 DBus 或整 HOME 挂载。假源目录未持续挂载；项目保留原绝对路径，原 `.mindfs` 被私有元数据覆盖。 |
| 原命令与网页 | `mindfs --version`、`codex --version` 成功；Codex 为 0.162.1。`/health` 返回 `ok`，网页及打包 JS 可读取；真实 Chromium 渲染标题 `MindFS RCC Container`，无页面异常。 |
| 真实 Codex 离线入口 | 自有容器以 `--network none`、只读根文件系统及空临时 HOME 完成 `initialize` / `initialized`，退出 0。响应包含 Codex 0.162.1、Linux 和 `/home/mindfs/.codex`。 |
| MindFS→Codex SDK | 真实 Go SDK 启动静态 Go 假 app-server，argv 含 `app-server`，HOME/CODEX_HOME 为私有目录，thread cwd 为项目绝对路径。同一会话 `1794235380-d71678c3f73c` 完成两轮，`mindfs --agents` 查询成功。 |
| provider 独立管理 | 从两个已导入 provider 切换到 v2，私有 Codex 配置实际改变，新 app-server 返回 v2；删除 v1 后仅保留 v2。假源目录全部文件的 SHA-256 与权限保持不变。 |
| 持久化 | Compose restart 后 v2、当前选择及原会话保留，同 key 续发成功。随后 down/up 创建不同容器 ID，provider 与会话数据库继续保留。宿主原 `.mindfs` sentinel 的内容和条目保持不变。 |
| RCC 装载与接线 | 真实发行执行 `rcc --help` 成功，入口生成 `--node external-fixture-node` 定义；MindFS RCC SDK 启动真实客户端，错误参数按预期返回“客户端参数无效”。 |

原始结果见 [results-base.json](../../tools/container-independent/results-base.json)。这一轮未导入 agent env；F01 的失败与修复另按下节验证。

## F01 发现与修复验证

原镜像经 `--include-agent-env` 导入单个假 env 键后，真实 SDK 子进程记录 `HOME_set= CODEX_HOME_set= imported_marker=present argv=app-server -c thread_unload_delay_secs=0`。既有 SDK 将非空 `Env` 作为完整进程环境，新容器接线没有补回运行环境，导致假 app-server 因缺少私有 HOME 失败。复现现场位于 `/tmp/mindfs-container-independent-env-hz1ex4u8`。

返修入口在容器内合并当前环境与导入键，并使用容器的 HOME/CODEX_HOME/PATH/XDG 路径。它将 Codex 定义与 RCC 定义一起原子生成到私有额外配置，每次启动刷新，文件权限为 0600。原导入文件保持不变。

独立复验通过交付脚本实际导入非空 env，额外放入错误的假宿主 HOME/CODEX_HOME/PATH/XDG 值。测试仅将 Codex 命令替换为独立假进程，并固定运行前的私有 `agents.json` 字节。真实 SDK 的实际观测为：

| 条件 | 子进程观测 |
| --- | --- |
| 私有 HOME / CODEX_HOME | `/home/mindfs` / `/home/mindfs/.codex` |
| PATH | `/opt/rcc/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin` |
| XDG config / state | `/home/mindfs/.config` / `/home/mindfs/.local/state` |
| 导入 marker | `present` |
| 初次启动的运行变量 | `runtime-v1`，临时旧键为 `old` |
| 重建后的运行变量 | `runtime-v2`，已移除的临时键为空 |

同一会话 `1794236240-3e0794959013` 完成两轮；provider 切换/删除、同 key 重启续发、重建后续发、RCC 定义共存、`--help` 与 SDK 非零诊断均通过。源配置与运行前私有 `agents.json` 的字节保持不变；provider 的私有 config 按切换预期更新。生成配置的实际权限为 0600。返修镜像的真实 Codex 离线握手也成功。

独立执行导入与入口单测共 15 项，全部通过；`bash -n compose.sh`、`sh -n entrypoint.sh` 和 `git diff --check` 通过。返修轮结果见 [results.json](../../tools/container-independent/results.json)。网页完整浏览器渲染沿用基础轮证据，返修轮核对 HTTP 页面、相同打包资产及命令入口。

## 能力范围与现场

真实 Codex 离线 stderr 提示 PATH 未安装系统 bubblewrap，将使用内置版本；握手与退出均成功。本轮未执行真实模型 turn 或沙箱工具行为。

RCC 本轮覆盖二进制、显式外部节点参数和 SDK 诊断，未登录或建立新的外部节点成功会话。此前真实 RCC、官方 Claude、双 VM 与 mock 的六项链路见 [既有独测报告](rcc-independent-20261109.md)。轻量容器没有用户 systemd，容器新节点自动登记及本机工具执行仍不属于已验证能力。当前元数据覆盖适用于所选项目根目录；新增或嵌套项目须另配覆盖挂载。

本轮仅新增或修改 [独测夹具、说明与结果](../../tools/container-independent/README.md) 及本报告。F01 复验命令如下；重新执行时使用新建的 `/tmp/mindfs-container-independent-*` 目录：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/container-independent/run.py \
  --repo /media/main/hongbo/mindfs-rcc-container-independent \
  --state /tmp/mindfs-container-independent-oNYcUv \
  --go /tmp/rcc-setup-token-74/go/bin/go \
  --rcc-release /media/main/hongbo/.local/lib/rcc/interactive-2cf97f2e87a0 \
  --reuse-image sha256:382a12315214ec5fe764d406337ba5918a832f0416a3dac09d005b4c69146cd8 \
  --with-agent-env
```

两轮正式证据分别位于上述临时目录的 `result.json`、`formal-run.log` 与 `evidence/`，基础轮额外保留 `web.png`。准备阶段的空 HOME 初始化、相对资产 URL 和本机 Chromium 路径调整现场保留于 `/tmp/mindfs-container-independent-{qE9Qep,wgIfNm,vk7sJV}`，均为独测夹具调整。

收尾核查确认六轮自有容器与网络全部清理，端口 59015、54231 无监听。失败准备轮的镜像别名已删除，两个固定通过镜像别名与私有证据保留供审阅。公开版 PID 2287866 仍在；正式 7332 实例、其他既有容器和真实配置来源均未操作。测试未读取真实 provider/Codex 凭据、未发真实模型请求、未改实际 FRP 或生产服务。
