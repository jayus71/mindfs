# 容器部署开发验证（2026-11-09）

本轮在 `feature/container-runtime-20261109` 上，以 `1489e91ad07b8f1616f369f37f5b7d7519b47415` 为基线实现容器部署。修改仅涉及 Docker 构建上下文、`deploy/container/`、部署文档及 Python 缓存忽略规则；Go、前端与 RCC 产品源码均未修改。真实配置复制由维护者后续执行。

镜像保留 `mindfs` 命令，包含原网页和 Codex CLI 0.162.1，以非 root 用户运行。Compose 默认绑定 `127.0.0.1:7332:7331`，私有 HOME 持久化，并在保留项目绝对路径的同时覆盖项目根 `.mindfs`。RCC 完整私有发行通过可选只读挂载提供。

开发环境为 Docker 29.1.3、Compose v2.33.0，构建 UID/GID 为 1002/1001。首次构建在 `go mod download` 访问 `proxy.golang.org` 时连接超时；随后只调整本次构建参数，成功构建：

```bash
docker build --network host -f deploy/container/Dockerfile \
  --build-arg MINDFS_UID=1002 --build-arg MINDFS_GID=1001 \
  --build-arg NODE_IMAGE=docker.m.daocloud.io/library/node:22-bookworm-slim \
  --build-arg GO_IMAGE=docker.m.daocloud.io/library/golang:1.25-bookworm \
  --build-arg RUNTIME_IMAGE=docker.m.daocloud.io/library/ubuntu:24.04 \
  --build-arg GOPROXY=https://goproxy.cn \
  --build-arg GOSUMDB=sum.golang.google.cn \
  -t mindfs-rcc-container-dev:20261109 .
```

产物镜像 ID 为 `sha256:0599ebd803ad488ecf7faf5c9823cf800ce277175a4dff2da216bda1bccd7274`。构建日志位于本机 `/tmp/mindfs-rcc-container-build-20261109-retry.log`，首次失败日志为 `/tmp/mindfs-rcc-container-build-20261109.log`。默认构建源仍为官方地址；代理和镜像源可由构建参数设置。未更改主机全局网络设置。

实际执行的检查与结果如下：

| 检查 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s deploy/container -p 'test_*.py' -v` | 11 项通过，覆盖导入白名单、显式凭据开关、文件权限、源内容保持、符号链接和覆盖拒绝、输出脱敏 |
| `bash -n deploy/container/compose.sh`、`sh -n deploy/container/entrypoint.sh` | 通过 |
| `python3 -m py_compile deploy/container/smoke-container.py` | 通过 |
| 完整 Docker 多阶段构建 | 通过；网页构建、Go CLI 编译和运行层依赖安装完成 |
| 默认 Compose 渲染及隔离测试端口 | 默认回环 7332；烟测使用独立回环 17332 |
| 运行用户和 Codex CLI | UID 1002；`codex-cli 0.162.1`，未请求模型 |
| 缺少元数据覆盖的入口 | 拒绝启动 |
| `/health`、网页、打包 JS、`/api/dirs`、带 root 的 `/api/sessions` | 通过；网页包含独立标题 |
| provider 列表与切换 | 列表不包含假密钥；切换成功写入私有 Codex 配置；主机假源文件哈希保持一致 |
| 原项目 `.mindfs` 隔离 | 原 sentinel 内容和目录条目保持一致；新元数据写入私有 HOME |
| 重启 | 私有配置和元数据 sentinel 保留 |
| RCC 可选发行挂载 | 真实完整发行以只读方式运行 `rcc --help`；额外 agent 配置生成 `--node fixture-external-node` |
| `git diff --check` | 通过 |

完整烟测命令如下，RCC 路径仅指向已存在的私有二进制发行：

```bash
python3 deploy/container/smoke-container.py \
  --image mindfs-rcc-container-dev:20261109 \
  --rcc-release-dir /media/main/hongbo/.local/lib/rcc/interactive-2cf97f2e87a0
```

烟测输出保存在本机 `/tmp/mindfs-rcc-container-smoke-20261109.log`。测试使用自动命名的 `mindfs-smoke-*` Compose 项目和 `/tmp/mindfs-container-smoke-*` 假配置目录，结束时清理自己的容器、网络和临时目录。未停止或重建既有容器，公开版 MindFS 进程 PID 2287866 与回环 7331 监听仍在。

本轮验证的是部署和配置隔离。未导入真实 provider/Codex 配置、未登录官方 Claude、未执行模型请求、未建立 RCC 外部节点会话、未更改实际 FRP 或生产服务。轻量容器尚未支持依赖用户 systemd 的 RCC 自动本机节点流程；现有接线通过已授权外部节点完成。项目根 `.mindfs` 的覆盖不自动扩展到嵌套项目或新增项目，操作者须为这些路径单独配置隔离挂载。

部署步骤见 [CONTAINER.md](CONTAINER.md)。独立测试可从交付的固定提交重建镜像并运行上述脚本；本报告为开发自测记录。

## F01：导入非空 agent env 的运行接线返修

独测补充检查发现，原提交使用 `--include-agent-env` 导入非空 Codex env 后，现有 SDK 将该映射作为子进程的完整环境，导致 HOME、CODEX_HOME 和 PATH 丢失。返修基线为 `ed4952d7cfa3cc278146ec74956588a4841f9fe9`，已包含原独测夹具及报告。

返修仅修改容器入口和部署回归检查。入口在容器内读取当前运行环境，叠加导入的 Codex env，并保持私有 HOME、CODEX_HOME、PATH 及 XDG 目录。额外 agent 定义与 RCC 外部节点定义一起原子写入私有配置，权限为 0600；原导入文件不变，每次启动重新生成，避免残留上一轮已移除的运行变量。该配置是启动时的 env 快照，后续修改 Codex agent env 须重启容器；Codex API provider 切换仍直接写私有 config，沿用既有行为。主机导入脚本和 Go/前端产品代码保持不变，未读取或复制整套主机环境变量。

沿用本报告上方完整构建参数，将镜像标签改为 `mindfs-rcc-container-dev:f01-20261109`，构建得到 `sha256:382a12315214ec5fe764d406337ba5918a832f0416a3dac09d005b4c69146cd8`。构建日志为 `/tmp/mindfs-rcc-container-f01-build-20261109.log`。

新增 4 项入口回归，与原 11 项导入检查合计 15 项通过；覆盖非空 env 与必要容器环境叠加、外来 HOME/PATH 覆盖防护、源文件保持、生成文件权限、重启环境刷新、RCC 共存、空 env 默认继承及错误信息脱敏。Shell 语法、Python 编译和 diff 检查通过。

另执行 `deploy/container/smoke-agent-env.py`，由已有独测 Go 假 app-server 夹具承接真实 MindFS SDK。显式导入假 marker 和错误的宿主 HOME/CODEX_HOME/PATH 后，同一会话两轮分别返回 `fixture-response provider-v1 1` 与 `fixture-response provider-v1 2`，重启后原会话续接成功。子进程实际观察到：

```json
{
  "HOME": "/home/mindfs",
  "CODEX_HOME": "/home/mindfs/.codex",
  "PATH": "/opt/rcc/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin",
  "XDG_CONFIG_HOME": "/home/mindfs/.config",
  "XDG_STATE_HOME": "/home/mindfs/.local/state",
  "IMPORTED_MARKER": "present",
  "CONTAINER_RUNTIME_MARKER": "runtime-present"
}
```

假源配置与私有导入副本的字节保持不变。定向 SDK 日志为 `/tmp/mindfs-rcc-container-f01-sdk-20261109.log`。原容器烟测也在返修镜像上重跑通过，日志为 `/tmp/mindfs-rcc-container-f01-smoke-20261109.log`，覆盖网页、provider 切换、元数据隔离、重启与 RCC 只读挂载。本轮只启动并清理自有临时实例，未操作维护者已部署的 7332 实例或真实来源配置，未执行真实模型请求。
