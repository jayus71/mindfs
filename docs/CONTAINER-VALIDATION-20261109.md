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
