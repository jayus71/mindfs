# MindFS 容器独立测试（2026-11-09）

容器候选通过本轮独测。原命令 `mindfs`、网页、Codex 离线握手及真实 MindFS SDK→假 app-server 双轮对话均成功；一次性复制后的 provider 可独立切换、删除，并随会话数据库跨重启和容器重建保留。假源配置的内容与权限、宿主项目原 `.mindfs` sentinel 均保持不变。本轮未发现需要开发返修的问题。

## 固定来源与执行范围

开发提交为 clean `16a4ab9c0970a231f1308f872fe32d3bf54daab8`。独测分支为 `test/container-runtime-independent-20261109`，工作区为 `/media/main/hongbo/mindfs-rcc-container-independent`；完整通过时的夹具提交为 clean `bae3d41eb9b398b4227effa971fb0ecf005cc913`，其产品与部署文件均保持开发提交版本。

本轮固定复用开发构建镜像 `sha256:0599ebd803ad488ecf7faf5c9823cf800ce277175a4dff2da216bda1bccd7274`，未另行重建大镜像。构建步骤、首次网络失败及成功构建日志见 [开发验证记录](../CONTAINER-VALIDATION-20261109.md)。独测核对交付相对基线 `1489e91ad07b8f1616f369f37f5b7d7519b47415` 的 `cli/`、`server/`、`web/`、Go module 文件、`agents.json` 和 `task_template.json` 无变化，随后在固定镜像中完成下列实际运行验证。

运行环境为 Linux amd64、Docker 29.1.3、Compose 2.33.0，镜像用户 UID/GID 为 1002/1001。正式 Compose 项目为 `mindfs-independent-zacfj2`，仅使用本轮 `/tmp/mindfs-container-independent-ZACFJ2` 内的假配置、私有 HOME、项目和只读夹具，主机端口为回环 59015。RCC 仅挂载已有完整二进制发行 `/media/main/hongbo/.local/lib/rcc/interactive-2cf97f2e87a0`，挂载为只读；其 `bin/rcc` SHA-256 为 `e4e883f51825f0c8c91c78b7b5bb97f160ac725e26243de563b8ca2701c4b4d1`。私有 RCC 源码没有进入 fork 或镜像。

## 实际结果

| 验证 | 结果与证据 |
| --- | --- |
| 交付脚本检查 | 独立执行导入单测 11 项，全部通过；`bash -n compose.sh`、`sh -n entrypoint.sh`、`git diff --check` 通过。 |
| 一次性导入 | 显式导入假 provider、选择偏好、Codex config/auth 四个文件；目录 0700、文件 0600；再次导入退出 1。假历史、registry、relay 凭据及本地 CLI token 未复制。 |
| 运行隔离 | Compose 与实际 Docker inspect 均确认独立 bridge 网络、非 privileged、回环发布端口；无 Docker socket、宿主 DBus 或整 HOME 挂载，假源目录未持续挂载。项目在容器内保留原绝对路径，原 `.mindfs` 被私有元数据覆盖。 |
| 镜像命令与网页 | `mindfs --version`、`codex --version` 成功；Codex 为 0.162.1。`/health` 返回 `ok`，网页及打包 JS 正常读取；真实 Chromium 渲染标题 `MindFS RCC Container`，无页面异常。截图保留于本轮证据目录。 |
| 真实 Codex 离线入口 | 另起自有容器，使用 `--network none`、只读根文件系统及空临时 HOME，经正常入口创建 Codex 目录后完成 `initialize` / `initialized` 并退出 0。响应报告 Codex 0.162.1、Linux 和 `/home/mindfs/.codex`。 |
| MindFS→Codex SDK | MindFS 的真实 Go SDK 启动本轮静态 Go 假 app-server，argv 包含 `app-server`；HOME/CODEX_HOME 指向容器私有目录，thread cwd 为所选项目绝对路径。同一会话 `1794235380-d71678c3f73c` 完成两轮并收到对应文本事件；`mindfs --agents` 查询成功。 |
| 独立 provider 管理 | API 从两个已导入 provider 中切换到 `provider-v2`，私有 Codex 配置实际改变，新 app-server 返回 v2；删除 v1 后列表仅剩 v2。假源目录全部文件的 SHA-256 与权限保持不变。 |
| 持久化 | Compose restart 后，v2、当前选择与原会话仍存在，同 key 续发成功。随后 down/up 创建不同容器 ID，provider 和会话数据库仍保留，证明数据来自私有挂载。 |
| RCC 装载与接线 | 实际只读发行执行 `rcc --help` 成功；入口生成 `--node external-fixture-node` 的额外 agent 配置。MindFS RCC SDK 启动真实客户端，错误参数按预期回传“客户端参数无效”，验证可执行装载和非零诊断链路。 |

真实 Codex 的离线 stderr 提示 PATH 未安装系统 bubblewrap，将使用内置版本；握手与退出均成功。本轮未执行真实模型 turn 或沙箱工具行为。

RCC 本轮验证覆盖二进制、显式外部节点参数和 SDK 诊断，未登录或建立新的外部节点成功会话。此前真实 RCC、官方 Claude、双 VM 与 mock 的六项链路结果见 [既有独测报告](rcc-independent-20261109.md)。轻量容器没有用户 systemd，容器新节点自动登记及本机工具执行仍不属于已验证能力。当前 Compose 的元数据覆盖范围为所选项目根目录；新增或嵌套项目须另配覆盖挂载。

## 复现与现场

独测仅新增 [夹具及结果摘要](../../tools/container-independent/README.md) 和本报告。正式命令为：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/container-independent/run.py \
  --repo /media/main/hongbo/mindfs-rcc-container-independent \
  --state /tmp/mindfs-container-independent-ZACFJ2 \
  --go /tmp/rcc-setup-token-74/go/bin/go \
  --rcc-release /media/main/hongbo/.local/lib/rcc/interactive-2cf97f2e87a0 \
  --playwright-module /media/main/hongbo/mindfs-rcc-integration/web/node_modules/playwright-core \
  --chromium-executable /media/main/hongbo/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome \
  --reuse-image sha256:0599ebd803ad488ecf7faf5c9823cf800ce277175a4dff2da216bda1bccd7274
```

重新执行须使用新建的 `/tmp/mindfs-container-independent-*` 目录。本轮结果原件为 `/tmp/mindfs-container-independent-ZACFJ2/result.json`，stdout/stderr、Compose 实际渲染、离线 Codex stderr、截图与清理核查位于同目录的 `formal-run.log` 和 `evidence/`；可提交摘要为 [results.json](../../tools/container-independent/results.json)。

准备阶段修正了夹具的空 HOME 初始化方式、相对资产 URL 和本机 Chromium 路径，相关未完成现场分别保留于 `/tmp/mindfs-container-independent-{qE9Qep,wgIfNm,vk7sJV}`。这些修正均限于独测夹具，完整通过结果来自上述固定夹具 SHA。

收尾核查确认四轮自有容器与网络全部清理，正式端口 59015 无监听；失败轮次镜像别名已删除，最终固定镜像别名 `mindfs-independent-zacfj2:test` 与私有证据保留供审阅。公开版 MindFS PID 2287866 仍在。整个测试未读取真实 provider/Codex 凭据、未发真实模型请求、未改现有容器、实际 FRP 或生产服务。
