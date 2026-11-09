# RCC 首次登记与普通子目录接入验收

本轮已完成独测、主审及实际部署。MindFS 产品提交为 `5a7b7f481f35dac930537e56eba3d96a19727012`，独测提交为 `2ddb72163a7f095acb991796a57b65b0afef2e04`。开发和独测分别使用独立分支/worktree；[开发检查](rcc-project-confirm-20261110.md)和[真实发行 RCC 独测](rcc-project-confirm-independent-20261110.md)记录具体参数、默认行为与不消费模型输入的验证。

原问题包含两项：容器生成的 RCC 参数没有确认首次目录登记；工作节点的旧 helper 把普通父目录和其子目录视为重叠冲突。前者通过显式实例设置 `RCC_CONFIRM_PROJECT=true` 自动登记，后者在 RCC 项目单独实现独立父子身份和共同文件事务协调。本 fork 未复制 RCC 私有源码。

部署容器镜像为 `sha256:2ac5dfc3b728547aa6a8ab9a00118eade4f8b3cc794db949b3898bcb66a51116`，版本 `rcc-5a7b7f4`。私有环境持续启用自动登记，生成参数为 `rcc --node hongbo-workstation --confirm-project`；确认开关留在 SDK 的 `--` 分隔符之前。升级前确认没有正在回复的会话或活动任务，原有数据、独立 HOME、provider、登录、HOME 挂载及 TLS/E2EE/FRP 接线保留。

工作节点 helper 配套产品固定为 `b1aca73c13b5c7694c86abbc4f7403fcb5c7335a`，独测为 `77f27aadba45cca005530b272cf4b4b94008d4c0`；实际 helper SHA256 为 `ab4a7d4d99eb463d37a8a96178d661a630997d5531f483bd8b5b996f01519076`。保留既有节点配置路径及原 6 个 binding/seal，仅新增报错项目的子 binding。

实际验证中，`migration_agent-handoff-20261109` 确认登记及随后不带确认的重复解析均 ready，原 `python_projects` 父项目和初始项目继续 ready。真实容器→RCC→运行端官方 CLI 的 stream-json initialize 成功；没有发送 user 消息或模型请求。关闭 stdin 后客户端退出 0，自有测试会话 stopped、unit 无进程、节点 S2 session Closed=true，原有会话未停止。

公网 HTTPS 首页和 health、未配对文件/API/WS 拒绝、正确配对的 API 解密与 WS 加密 pong 均通过；容器 healthy，原公开版进程继续运行。私有原始证据及旧 helper 备份位于部署目录的 `nested-helper-b1aca73/DEPLOYMENT.private.md` 与关联 manifest，未进入 Git。

用户主目录作为文件浏览根保留。用户已明确不要求在 HOME 根启动 RCC；包含内部状态的 HOME 根限制继续生效。已建立父子 binding 后需要继续使用新版 helper，旧 helper 二进制不构成直接业务降级方案。
