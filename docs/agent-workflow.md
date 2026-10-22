# LangChain Agent 工作流

根据用户追加要求，采用 LangChain 架构。没有引入复杂多 Agent 或向量数据库。

## 模块

- `backend/app/agent.py`：LangChain `@tool`、`ChatOpenAI.bind_tools`、`SystemMessage/HumanMessage/ToolMessage` 和 `RunnableLambda`。
- `services.py`：确定性营养、约束、快照、版本、事务。
- `schemas.py`：Pydantic 输入约束；`AgentOutput` 校验模型最终输出。
- `main.py`：已鉴权 API 与用户确认写入。模型没有确认工具、SQL 工具或账号选择参数。

## 顺序

1. 浏览器发送所选日期、问题及本次外部处理授权。
2. 后端从 HttpOnly 会话确定账号。工具闭包绑定当前用户和日期。
3. 读取档案的饮食相关字段、实际摄入汇总和生效计划。
4. 模型通过 LangChain 请求业务工具，服务器验证工具名、参数和资源归属。
5. 仅创建 pending 草案；最终结构不合法或任何错误时回滚本轮草案。
6. 界面展示修改前后、理由、已知事实、未知项与工具轨迹。
7. 用户调用确认 API，服务器重新验证限制、已吃餐次、版本和数据修订号后事务写入。

工具：get_profile、search_food、calculate_nutrients、get_daily_plan、get_food_logs、propose_plan、validate_plan、propose_adjustment、get_recent_food_logs、get_future_plans、propose_future_plans。

## 两种运行模式

`LLM_MODE=demo`：RunnableLambda 按明确关键词路由，同一套 LangChain 工具读取真实后端记录；输出是规则演示，未调用模型。

`LLM_MODE=live`：配置服务端密钥、模型名、Base URL。至少调用一个工具，最多 6 轮 / 12 次业务工具调用；每请求 timeout 默认为 20 秒，总流程 45 秒（上限 60 秒），不自动重试。不依赖 provider 的 JSON mode，最终文本必须通过 Pydantic JSON 校验。未授权时不发送外部请求。

失败包括缺密钥、认证/网络问题、工具协议不兼容、超时、未知工具、非法 JSON、超限。界面明确显示 fallback，返回本地已知事实，不假装真实模型成功。协议单测替身不代表真实服务连通。

## 数据和边界

食物营养数字和汇总始终由库与代码计算。模型输出只能给 summary 与最多两条 suggestions，不能覆盖 known_facts、data_revision 或营养值。模型文本与工具数据均不可变更系统规则。外部模型不接收邮箱和账号密码；用户自己写入问题的身份信息仍可能传给服务商，因此仅在授权时发送。账号数据库保留聊天文本和结构化答复，可随账号导出/删除；授权后最近 6 轮文本作为上下文。不启用远程 tracing。

提示词和关键词拦截不是医学安全验证；公众上线前必须进行模型红队、服务范围与医疗安全评估。USDA 参考食物和历史 demo 快照都不是对真实食堂菜品的成分保证。

参考：[LangChain bind_tools 官方接口](https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/bind_tools)。

## 聊天多日计划与照片

`chat_actions.py` 持久化多轮聊天，将 1–7 天草案放入同一 batch。一次确认在单一事务内校验并写入全部日期，只提高一次 revision；中途失败整体回滚。每个日期保留旧计划版本。日期限制在用户本地今天至未来 14 天。模型无确认工具；确认按钮是唯一生效入口。

`vision.py` 用 LangChain ChatOpenAI 发送图像及最小食物目录，Pydantic 校验食物匹配、克数和置信度。后端从库重新计算营养，未知匹配保留 null。原图只用于本次请求，不落盘；识别结果存为 pending FoodLog，前端打开既有记录编辑器核对。工具输出和聊天持久化同一事务，request_id 防止重试重复创建。

## 每轮档案 SystemMessage 与计划工具

`model_context.py` 从当前会话对应账号读取最新 ProfileData、已确认目标、数据修订号及本地日期，构造独立 SystemMessage。文本聊天和图片识别均注入；同轮工具循环保留这条消息，下一轮重新从数据库读取，不依赖模型主动调用 get_profile 或历史聊天记忆。账号邮箱、密码、会话和 API Key 不进入档案消息。自由文本明确作为数据，不能修改系统规则；未填写值保留 null。

- `propose_plan(items, plan_date)`：创建指定日期单日草案（显式日期为今天至未来 14 天），返回带日期、食物、克数、营养合计和确认状态的客户端卡片。
- `propose_future_plans(plans)`：创建 1–7 天整组草案，返回多日卡片。
- `propose_adjustment(...)`：提出尚未吃过餐次的替换。

上述工具由 LangChain 绑定。食物先检索，营养由后端重算，草案和聊天同一事务保存。客户端展示 proposals / batches，确认后写入生效计划，刷新或切换设备可继续查看。模型不能自行确认覆盖原计划。

工具创建候选遇到业务校验 422 时，将错误作为 ToolMessage 返回模型，在原有轮数预算内修正；每次创建调用使用事务保存点，失败回滚该调用的全部草案。外层事务在最终响应失败时仍整体回滚。

RAG 使用 knowledge.py 的 LangChain BaseRetriever 自动召回已知主题，并提供 search_health_guidance 工具。最终输出 citations 由服务器核对本轮检索集合，转换为来源快照。完整说明见 health-rag.md。
