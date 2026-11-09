# 独立容器验证夹具

`run.py` 在 `/tmp/mindfs-container-independent-*` 中自行生成假 provider、Codex 配置和假登录文件，通过交付的导入脚本及 Compose 启动独立实例。Go 夹具实现本轮需要的 Codex app-server JSON-RPC；MindFS 运行真实 Codex Go SDK。另用镜像中的真实 Codex 在 `--network none`、空临时 HOME 中完成 initialize/initialized 握手，不执行模型 turn。

脚本检查两轮消息、provider 切换与删除、容器重启及重建后的持久化、项目 `.mindfs` 覆盖，以及实际 RCC 二进制只读挂载、`--node` 配置和 SDK 非零诊断。RCC 不登录、不创建容器节点或外部会话。源配置与宿主项目的假元数据必须保持不变。测试只关闭自己命名的容器与网络，保留临时数据和本轮镜像供核查。

需要 Docker、Compose、Python 3、Go，以及一个完整的私有 RCC 二进制发行目录；目录仅在运行时只读挂载。可选的浏览器检查使用已安装的 Playwright Chromium；版本路径不匹配时可用 `--chromium-executable` 指定已有浏览器。不要提供真实 HOME、真实 provider 或实际 RCC 凭据。

```bash
state=$(mktemp -d /tmp/mindfs-container-independent-XXXXXX)
PYTHONDONTWRITEBYTECODE=1 python3 tools/container-independent/run.py \
  --repo "$PWD" --state "$state" \
  --go /absolute/path/to/go \
  --rcc-release /absolute/private/rcc-release \
  --playwright-module /absolute/path/to/node_modules/playwright-core
```

追加 `--with-agent-env` 会通过交付导入脚本复制假 Codex 附加环境，并验证实际 SDK 同时继承容器 HOME/CODEX_HOME 与该假键。默认从当前源码构建独立镜像。已有构建可追加 `--reuse-image sha256:<完整镜像ID>`；该模式固定并复用所指定产物，不声称独立重建。测试结果与过程日志位于 `$state/result.json` 和 `$state/evidence/`。测试镜像名由临时目录后缀生成，避免覆盖开发或安装版镜像。
