# MindFS 容器部署验收（2026-11-09）

容器部署已通过开发自测、独立测试与维护者审查，并在本机启动。容器继续使用 `mindfs` 命令；provider 与 Codex 配置一次性复制后由容器独立管理。改动集中在部署、导入脚本和验证材料，`cli/`、`server/`、`web/` 及依赖声明相对已验收基线均无变化。

最终开发提交为 `938f8bc0c1b761a22a486ef7506f57af75de1899`，独测交付为 `b9e0c2400da19d278906458c96c5d9507c645efc`，修复轮完整通过的夹具来源为 `2b5fae7f11aa8ee5ce608c4d441b2a473d6eb720`。运行镜像固定为 `sha256:382a12315214ec5fe764d406337ba5918a832f0416a3dac09d005b4c69146cd8`，本机别名为 `mindfs-rcc:local`。独测复用了固定构建产物，另行执行了运行行为验证。

需求符合性审查通过：命令、独立端口与 HOME、项目根元数据覆盖、Codex CLI、一次性配置导入和独立 provider 管理均有对应证据。代码质量审查通过：导入采用明确文件范围、私有权限和临时目录提交，拒绝覆盖已用目录；运行容器使用普通用户和独立 bridge 网络，RCC 发行仅在运行期只读挂载。独测发现的非空 agent env 丢失 HOME 问题 F01 已修复并通过复验；入口在容器内合并运行环境，保护私有目录与 PATH，每次启动刷新权限为 0600 的额外配置。镜像入口脚本与提交源码的 SHA-256 一致，当前无待返修项。

开发自测及独测均通过 15 项导入与入口测试。运行验证覆盖完整镜像构建、真实 Chromium 页面、真实 Codex 0.162.1 的无网络握手、MindFS 实际 SDK 到假 app-server 的双轮对话、provider 切换与删除、重启与重建后的持久化，以及 RCC 二进制和 SDK 非零诊断。F01 复验实际导入非空 env，确认私有路径、导入变量和容器运行变量同时保留，重建后移除的旧环境变量也不再残留。详见[开发记录](../CONTAINER-VALIDATION-20261109.md)和[独立测试报告](container-independent-20261109.md)。

## 本机运行结果

实例名为 `mindfs-rcc-mindfs-1`，仅发布 `127.0.0.1:7332 → 容器 7331`，Docker 健康状态为 `healthy`。维护者实际读取 `/health`、网页和 provider 列表，并确认网页标题正确，10 个已保存 provider 的 ID 与来源一致，列表不返回密钥。容器内 `mindfs --version`、`codex --version` 和 `rcc --help` 均退出 0。F01 修复后确认该新实例无会话，再重建到最终镜像，健康状态与 provider 保留检查再次通过。

运行目录为 `/media/main/hongbo/.local/share/mindfs-rcc-container/`：`home/` 保存独立状态，`project/` 为初始空项目，`rcc-release/` 仅包含所需发行二进制、manifest 和许可证。私有 `container.env` 保存路径和端口，目录位于 Git 仓库外。主机的 provider、Codex config/auth 已复制到独立 HOME；没有持续挂载来源配置。导入时确认对应副本逐字节一致，文件权限为 0600、目录为 0700；真实凭据未进入镜像或 Git。

现有公开版 PID 2287866 保持运行；provider、Codex config/auth、registry 及身份相关文件的哈希保持一致。公开版的 preferences 在运行期间出现后续更新，容器继续使用导入时的独立副本。新实例挂载范围仅包括自己的 HOME、空项目、私有项目元数据和只读 RCC 发行，不含来源配置目录、主机 Docker socket、DBus 或整 HOME。

从仓库根目录管理该实例：

```bash
set -a
source /media/main/hongbo/.local/share/mindfs-rcc-container/container.env
set +a
bash deploy/container/compose.sh ps
bash deploy/container/compose.sh exec mindfs mindfs --version
# 停止本实例，保留持久数据：
bash deploy/container/compose.sh down
```

## 使用范围

本轮没有发送真实模型请求。RCC 客户端已装载，实际使用时仍需在容器内完成独立设备登录并指定已授权的外部工作节点；轻量容器没有用户 systemd，自动成为新 RCC 工作节点尚未支持。既有 RCC 六项实际链路验证见[接入独测](rcc-independent-20261109.md)。

当前只挂载初始空项目，并隔离该项目根目录的 `.mindfs`；使用实际工程、新项目或嵌套项目时，按[部署说明](../CONTAINER.md)调整项目和元数据挂载。FRP 已提供模板，实际远程地址和端口尚未配置。

验收后已清理合入的容器开发与独测 worktree，分支和私有 `/tmp` 证据保留。已取消的独立命名方案工作区保留其未提交现场，未合入本次交付。
