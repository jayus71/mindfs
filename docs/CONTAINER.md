# MindFS 容器部署

容器继续使用 `mindfs` 命令，网页标题为 `MindFS RCC Container`，默认映射 `127.0.0.1:7332 → 容器 7331`。镜像包含 MindFS CLI、网页静态资源和固定版本 Codex CLI；HOME、provider 配置、Codex 配置及项目元数据保存在容器专用目录。主机现有 MindFS 的安装、7331 端口和配置保持独立。

本部署适用于一个明确的项目目录。Compose 将项目挂载到容器内相同的绝对路径，保证 RCC 外部节点解析 canonical cwd 时保留路径身份。项目文件可由容器中的工具修改。项目根目录的 `.mindfs` 由私有元数据目录覆盖，原有数据库和会话不会导入。新加入的其他项目、嵌套项目及它们的 `.mindfs` 需要各自配置覆盖挂载；当前 Compose 只隔离所选项目根目录。

先准备 Docker Engine、Compose v2、Python 3 和一个已有项目目录。从本仓库根目录运行下面的步骤。路径须为无符号链接的绝对路径，私有 HOME 放在仓库和项目目录之外。`compose.sh` 使用当前用户的 UID/GID 构建非 root 运行用户，私有目录权限为 0700。

```bash
export MINDFS_CONTAINER_HOME="$HOME/.local/share/mindfs-rcc-container"
export MINDFS_PROJECT_DIR=/absolute/path/to/one/project
export MINDFS_CONTAINER_PORT=7332
export MINDFS_CONTAINER_IMAGE=mindfs-rcc:local
```

`deploy/container/container.env.example` 可复制到仓库外作为路径配置。使用配置文件时，在运行 helper 前通过 shell 导出其中变量：

```bash
set -a
source /absolute/private/container.env
set +a
```

一次性导入须在第一次运行 `compose.sh` 前完成：导入目标必须不存在或为空，helper 随后会创建持久元数据目录。下面的命令由操作者在确认源路径后执行，复制 provider、Codex 配置、Codex 登录文件和 Codex agent 环境变量到私有 HOME。

```bash
python3 deploy/container/import-settings.py \
  --mindfs-config-dir "$HOME/.config/mindfs" \
  --codex-home "$HOME/.codex" \
  --destination "$MINDFS_CONTAINER_HOME" \
  --include-mindfs-providers \
  --include-codex-auth \
  --include-agent-env
```

导入脚本只读取显式指定的源目录，源文件保持原样。`--include-mindfs-providers` 复制含凭据的 provider 记录；`--include-codex-auth` 复制 `auth.json`；`--include-agent-env` 仅提取 `agents.json` 中 Codex 的环境变量，并使用容器内的 `codex` 命令定义。按实际需要省略这些开关。`config.toml` 总会按原文复制，它本身也可能包含凭据。导入保留模型、effort、fast service、固定模型及有效 provider 选择；registry、旧会话、数据库、relay 凭据、launcher 节点、配置备份和宿主工具命令不在导入范围。文件权限为 0600，目录为 0700。

启动前检查私有副本的主机相关设置：Codex 的绝对路径、MCP 命令及依赖、agent 环境变量，以及 provider URL。容器中的 `127.0.0.1` 指向容器自身；需要的工具和网络入口应在容器中可用。后续在网页中管理、切换 provider 时，修改的是这个私有副本。源配置没有持续挂载，重复运行导入脚本会拒绝覆盖已有数据。

导入的 Codex env 在启动时叠加到容器的运行环境。HOME、CODEX_HOME、PATH 和两个 XDG 目录使用容器值，避免宿主路径覆盖私有目录。入口脚本在私有 HOME 中生成权限 0600 的额外 agent 配置，原导入文件保持原样。这是每次启动生成的 env 快照；后续修改 Codex agent env 后，重启容器生效。Codex API provider 切换仍直接写入私有 `config.toml`，按原有行为生效。空 env 沿用 SDK 默认继承行为。此步骤在容器内执行，主机导入脚本不会读取整套主机环境变量。

```bash
bash deploy/container/compose.sh build
bash deploy/container/compose.sh up -d --no-build
bash deploy/container/compose.sh ps
curl --fail http://127.0.0.1:7332/health
bash deploy/container/compose.sh exec mindfs mindfs --version
bash deploy/container/compose.sh exec mindfs codex --version
```

浏览器打开 `http://127.0.0.1:7332`。容器在前台运行服务，由 Compose 管理启动和重启。入口脚本会检查私有 `.mindfs` 覆盖挂载，缺少覆盖时拒绝启动。镜像没有官方 Claude Code；Codex 配置和环境均归此实例管理。

受限网络中可通过构建参数选择镜像源、Go 模块代理与校验服务，默认仍使用官方源。它们只影响镜像构建。例如：

```bash
export NODE_IMAGE=docker.m.daocloud.io/library/node:22-bookworm-slim
export GO_IMAGE=docker.m.daocloud.io/library/golang:1.25-bookworm
export RUNTIME_IMAGE=docker.m.daocloud.io/library/ubuntu:24.04
export GOPROXY=https://goproxy.cn
export GOSUMDB=sum.golang.google.cn
bash deploy/container/compose.sh build
```

RCC 使用完整私有发行目录的只读挂载，发行目录应包含可执行的 `bin/rcc` 和 `bin/reach-helper`。`~/.local/bin/rcc` 可能只是指向发行目录的 wrapper，挂载完整发行目录才能保留所需文件。镜像构建上下文与 Git 均不包含 RCC 私有发行。

```bash
export RCC_RELEASE_DIR=/absolute/private/rcc-release
export RCC_NODE_ID=an-already-authorized-external-node
bash deploy/container/compose.sh up -d --no-build
bash deploy/container/compose.sh exec mindfs rcc --help
```

设置 `RCC_NODE_ID` 后，入口脚本在私有 HOME 生成额外 agent 定义，以 `rcc --node <ID>` 连接已授权的外部节点。RCC 的 profile、登录状态及凭据同样保存在容器 HOME；操作者需在容器内配置服务 profile，再按已有设备授权流程使用 `rcc login --code`。不要把宿主 RCC 凭据目录作为持续挂载。

当前轻量容器支持 RCC 二进制运行和外部节点参数接线。RCC 自动登记本机节点及本机工具执行依赖用户 systemd，当前容器没有这套运行环境，完整新节点流程尚未支持。部署不使用 privileged 模式或宿主 systemd/DBus 挂载。外部节点的项目路径、授权与实际会话仍需在对应环境中验证。

更新时在新版本源码中重建镜像并重建容器；私有 HOME 和项目元数据保留。容器中的 `mindfs --update` 属于原安装器流程，镜像升级统一使用以下命令：

```bash
bash deploy/container/compose.sh build
bash deploy/container/compose.sh up -d --no-build --force-recreate
# 停止并删除本部署容器；私有 HOME 仍保留在主机。
bash deploy/container/compose.sh down
```

`deploy/container/frpc.example.toml` 仅提供 `127.0.0.1:7332` 的 FRP TCP 转发模板。操作者将模板并入已有私有认证/TLS 配置后自行部署；本轮没有配置真实 FRP 或公网端口。Compose 固定绑定主机回环地址。

部署自测使用独立的临时目录、假 provider 和不存在的 agent 命令，验证时不会执行模型请求。脚本清理自己创建的容器和临时数据：

```bash
python3 -m unittest discover -s deploy/container -p 'test_*.py' -v
python3 deploy/container/smoke-container.py --image mindfs-rcc:local
# 可选：额外验证真实私有发行的只读挂载、--help 与外部节点参数生成。
python3 deploy/container/smoke-container.py --image mindfs-rcc:local \
  --rcc-release-dir /absolute/private/rcc-release
# 导入非空 env 后，运行真实 MindFS SDK→假 app-server 双轮及重启续接。
python3 deploy/container/smoke-agent-env.py --image mindfs-rcc:local \
  --go /absolute/path/to/go
```

烟测默认占用独立回环端口 17332，可用 `--port` 替换。镜像须按当前用户 UID/GID 预先构建。此烟测覆盖安装、配置隔离和服务运行，不创建 RCC 登录或外部节点会话。
