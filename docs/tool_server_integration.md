# Tool Server 接入约定

当前 Agent 不绑定某一种设备连接方式。状态机只要求执行器提供：

```python
execute(action: AgentAction) -> dict
```

返回结构遵守 `docs/data_contract.md` 的 Parser JSON：

```json
{
  "success": true,
  "device": "R2",
  "vendor": "huawei_vrp",
  "command_type": "DISPLAY_INTERFACE",
  "facts": {},
  "error": null
}
```

当前仓库提供两个执行器：

- `MockExecutor`：直接读取结构化 `mock_outputs.json`，用于隔离 Agent 问题；
- `ReplayExecutor`：读取保存的 CLI 文本，经 Parser 转换为 Facts，用于 benchmark。

接入 Track B CLI Server 时，只需新增一个执行器：负责把 `build_execution_request()` 生成的 `device` 和 `command` 发送给服务器，再把服务器回显交给 `parser.parse_cli_output()`。真实连接地址、认证方式和服务器协议属于外部环境，不写死在 Agent 状态机中。

仓库中的 `LiveExecutor` 已提供这个适配器。它依赖一个很小的传输接口：

```python
class CommandTransport:
    def send(self, device: str | None, command: str | None) -> str: ...
```

因此 SSH、HTTP CLI Server 或竞赛仿真器都可以作为 `transport` 注入，不需要修改 Agent 或 Parser。

执行失败或解析失败必须返回 `success: false`、空 `facts` 和非空 `error`。状态机会停止猜测并返回 `NEED_MORE_DATA`。
