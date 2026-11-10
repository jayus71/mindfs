# RCC 思考等级选择验收

本轮已通过独立测试、主审并部署到现有容器。产品固定提交 `6925897c5139340da797fdf2172ecb943301605e`，独测固定提交 `00f0d087868ac8103348a5850e89257c9254b5c1`。开发和独测使用独立 worktree；[开发报告](rcc-effort-selection-20261110.md)与[独测报告](rcc-effort-independent-20261110.md)记录实际检查和首轮返修。

RCC 模型菜单现在提供 `low / medium / high / xhigh / max`，初始默认 `high`。用户显式选择优先，已有会话保存的等级和上次使用偏好按原有记忆行为保留。同一 RCC 内切换模型保留所选强度；已有空等级会话下一轮采用默认。五档来自运行端 CLI 的参数声明，各模型及账号的兼容性由运行端校验。

主审核对了协议级能力、前后端默认处理、偏好与续接语义，另运行相关 agent/usecase 的 `go vet` 通过。独立 Chromium 验证真实输入栏菜单、实际发送值、延迟目录、切换模型及刷新；usecase→Pool→SDK 隔离进程验证五档参数与持久远端会话 ID 的恢复。首轮切换模型将 max 重置 high 的问题已返修并独测关闭。非 RCC 的默认和逐模型能力规则保留。本轮不处理用户取消的打断停止问题。

部署镜像固定为 `sha256:4b0b9ccd0121ba527428c08ff77b00cc551fda8e830ce7ee9b3fccc281cc0837`，版本 `rcc-6925897`。镜像从固定产品构建；独测后继只增加测试和报告。更新前确认没有正在回复的会话或活动任务，通过私有 `remote-compose` 重建。原三个根、五个会话、首次项目自动登记、私有 HOME、provider、RCC 登录与目录挂载保留。

线上 E2EE agent API 返回五档选项及 `default_effort=high`，容器 healthy。公网 HTTPS 首页/health、未配对文件/API/WS 拒绝、正确配对的 API 解密及 WS 加密 pong 均通过。原运行端本人官方设置 `effortLevel=high` 保持；MindFS 的显式参数可覆盖该默认。

私有部署证据为 `/media/main/hongbo/.local/share/mindfs-rcc-container/effort-deployment-verification.json` 和 `effort-before.private.json`。本轮没有发送生产模型请求，未逐模型验证账号对全部档位的实际支持。
