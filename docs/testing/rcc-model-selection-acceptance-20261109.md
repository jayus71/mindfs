# RCC 模型选择与用户目录挂载验收

本轮主审通过，并已更新独立 MindFS 容器。产品提交为 `5d37e18b722010dcd4686ebac62d9e3c32890794`，独测提交为 `fbc8e7a57528363f292583e5de52381e332b1888`。开发与独测使用各自分支及 worktree，RCC 主仓库产品代码未变动。

## 模型选择

问题来自适配层：RCC 已支持 `--model`，MindFS 的 RCC 全局安装检测没有返回模型菜单。当前菜单提供运行端 CLI help 声明的 `sonnet`、`opus`、`fable` 别名及默认入口。模型由运行端解析，菜单不声明账号权限、具体版本或 effort。完整模型 ID 的显式 API 透传保留。

同时修复 SDK 自带模型默认值覆盖运行端配置的问题。新会话未选模型时，RCC 子进程不接收 `--model`。已有会话显式切换沿用 `set_model`；已有会话的空选择保留当前模型，菜单已标明该行为。

主审核对了安装检测、API 校验、SDK transport 默认值及选择器变更。全局检测继续只检查本地安装，不启动临时项目或远端会话。开发验证见[开发报告](rcc-model-selection-20261109.md)，独立 Chromium、Pool 八种新建/恢复组合及 usecase→SDK 验证见[独测报告](rcc-model-selection-independent-20261109.md)。相关 Go 回归、RCC race、前端类型检查与构建通过。

## 运行实例

部署镜像固定为 `sha256:90ed7da48baddcdb7d27214ceb4893925342da0e135fdf09e76256ccdcd28488`，`mindfs --version` 返回 `rcc-5d37e18`，容器用户为 `1002:1001`。镜像从上述固定产品提交构建；之后的独测提交仅增加测试和报告。

宿主用户目录按相同绝对路径读写共享，并在新版 UI 登记为 `hongbo` 根。容器自身 HOME 保持 `/home/mindfs`，provider、Codex、RCC 登录及原初始项目保留。宿主 registry 已登记的 12 个项目使用独立 `.mindfs` 覆盖挂载；新项目元数据默认保存到容器 HOME。未登记目录若已有 `.mindfs`，后续作为独立项目加入前仍需追加覆盖挂载。普通文件浏览不注册新项目。

本轮运行配置存放在仓库外的私有部署目录，未写入源码。后续更新统一使用该目录的 `remote-compose` launcher，以保留 HOME 挂载、TLS/E2EE、FRP 和 RCC 发行挂载。UID/GID、镜像源及 Go 构建代理已在私有环境文件固定。原镜像保留为回退标签。

更新前通过 API 确认正在回复的会话为 0，两个根的任务均为 0。重建后验证：

- 线上 E2EE `/api/agents?root=project` 返回 RCC available，以及三个预期别名；没有推断默认模型或 effort。
- 自有临时文件完成宿主→容器读、容器→宿主读及同 inode 检查，随后删除。
- 12 个容器元数据目录均指向独立覆盖目录；宿主原目录 inode/mtime 和公开版 registry 哈希保持。
- `project` 与 `hongbo` 根均保留，原有会话数保持 2。
- RCC `list` 认证成功；容器 healthy；原公开版进程继续运行。
- 公网 HTTPS 首页与 health 返回 200；未配对文件/API/WS 返回 401；正确配对后的 API 解密与 WebSocket 101/加密 pong 通过。

私有证据为部署目录中的 `home-mount.private.md`、`home-mount-verification.json`、`model-deployment-before.json`、`model-deployment-verification.json` 和 `remote-verification.json`；访问与配对资料继续保存在 `remote-access.private.md`，不进入 Git。

本轮没有发送真实模型请求。账号对别名的权限及其解析出的具体版本尚未实测；现有验证覆盖真实选择器、服务端接线、隔离 SDK/RCC 协议和线上已部署模型目录。
