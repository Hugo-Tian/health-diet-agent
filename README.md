# 三餐有数 · 健康饮食 Agent

Vue 3 + TypeScript + Pinia + Vue Router / FastAPI + SQLAlchemy + Alembic / **LangChain**。

项目目录：`C:\Users\omen\Desktop\港大semester1\health-diet-agent`。根目录保留原始《健康饮食Agent_整体设计与CodexPrompt.md》，与来源文件内容一致。当前是可运行的开发 MVP，食物库已接入 79 个 USDA SR Legacy 参考条目，保留逐项来源；历史演示记录继续明确标注。

## 本机运行

本次已安装 Python 虚拟环境与前端依赖、构建前端、迁移并初始化 SQLite。直接在 PowerShell 执行：

```powershell
cd 'C:\Users\omen\Desktop\港大semester1\health-diet-agent'
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

浏览器打开 http://localhost:8000 。自行注册邮箱格式的账号，密码至少 10 位；无默认账号或默认密码。邮箱仅作登录标识，不发送邮件。首次进入“我的”完成三步档案、确认目标，再生成计划草案。

全新电脑需 Python 3.13、Node.js 22 或更新版本：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

上述 Bypass 只影响本次脚本进程，不更改系统持久执行策略。按 Ctrl+C 停止服务；若端口已占用可加 `-Port 8001`。启动脚本默认仅监听本机。SQLite 文件位于 `backend/diet.db`，不要将其提交到代码仓库。

## 使用闭环

1. 注册 → “我的”填写成年确认、就餐条件、过敏原和目标。
2. “今日”生成计划草案 → 查看三餐和份量 → 确认应用。
3. 在午餐选择“记录实际吃的” → 核对实际克数、时间、吃完状态 → 保存。
4. 查看反馈；晚餐点“换一种”或让助手“帮我调整晚餐”。
5. 比较修改前后，确认后产生新版本；已记录吃过的餐次不能替换。
6. 在“助手”说“这两天吃得有点多，安排未来三天” → 查看多日草案 → 点击整组确认，未来计划一起更新。
7. 在助手上传/粘贴/拖入餐食照片 → 授权识别 → 自动保存待确认记录 → 核对食物、克数和吃完状态后计入摄入。
8. 切换日期补录；记录页编辑/删除；趋势页看七日已知量；我的页面导出或删除账号。

未确认记录不计入摄入；自定义食物营养未知时保留未知计数。计划估算不算实际摄入。手动目标不会自动决定餐食克数，不用单日偏差调整长期目标。

## LangChain 模式

默认 `LLM_MODE=demo`，无需 Key：LangChain RunnableLambda 编排真实业务工具，固定规则返回解释和草案。明确标记为规则演示。

真实模式在项目根目录创建 `.env`（可复制 `.env.example`），配置：

```dotenv
LLM_MODE=live
LLM_API_KEY=替换为服务端密钥
LLM_BASE_URL=https://你的兼容服务地址/v1
LLM_MODEL=你的服务支持的模型名称
LLM_TIMEOUT=20
AGENT_TIMEOUT=45
LANGCHAIN_TRACING_V2=false
LANGSMITH_TRACING=false
```

重启后在助手勾选本次外部处理授权。兼容服务必须实际支持工具调用；使用 LangChain ChatOpenAI 适配器不意味着所有服务自动兼容。模型可以检索食物、组合候选、提出替换，所有营养数字由服务端重算。最多 6 轮 / 12 次工具调用，不能自行确认草案。密钥不进入浏览器。不要启用远程 LangSmith tracing 上传健康上下文。

### DeepSeek 配置

本项目本地 `.env` 已切换为 DeepSeek：`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`、`LLM_MODE=live`。密钥已在本地 `.env` 配置，文件不提交到仓库；更换密钥后重启后端。适配器针对 DeepSeek 显式发送 `thinking.type=disabled`，使用非思考模式工具调用。配置依据为 2026-10-18 查阅的 [DeepSeek 官方文档](https://api-docs.deepseek.com/zh-cn/) 与 [工具调用文档](https://api-docs.deepseek.com/guides/tool_calls/)。

可在 backend 目录执行 `..\.venv\Scripts\python.exe check_llm.py`，使用合成测试文本验证认证、工具调用、工具结果回传。测试会产生少量 API 用量，不读取或发送用户健康记录；失败只输出错误类型和 HTTP 状态，不输出密钥或原始服务响应。缺少密钥时仅提示 MISSING_KEY，不发送请求。

真实接口未配置或失败时返回明确 fallback 和本地汇总。2026-10-18 补充验证：DeepSeek `deepseek-flash` 真实认证、LangChain 工具调用及工具结果回传通过，应用助手接口返回 `mode=live`。使用合成测试账号，不发送用户饮食记录，测试账号已删除。另已测工具协议替身、非法输出回滚、无 Key 和无授权行为。

## 开发与测试

```powershell
# 后端核心测试和前端类型检查/构建
powershell -ExecutionPolicy Bypass -File .\test.ps1

# 前端开发：先在另一个终端启动后端
cd frontend
npm.cmd run dev
# http://localhost:5173，/api 由 Vite 代理到 127.0.0.1:8000

# 浏览器端验收，先确保同源应用运行在 8000
npx.cmd playwright install chromium
node tests/browser-smoke.mjs
```

浏览器测试创建并删除专用测试账号，将截图和结果写入 `work/browser`。不要用真实用户账号跑测试。前后端依赖分别锁定于 `frontend/package-lock.json` 和 `backend/requirements.lock.txt`。`.env.example` 的 `APP_ORIGIN` 支持默认开发代理；自定义访问地址时调整为准确 origin。业务数据不存 localStorage，也不缓存到 Service Worker；离线写入失败时明确提示未确认保存。

后端 OpenAPI：`/docs`。所有业务 API 位于 `/api/v1`。开发 SQLite 验证通过；生产采用 PostgreSQL。迁移：在 backend 目录运行 `..\.venv\Scripts\python.exe -m alembic upgrade head`，种子：`..\.venv\Scripts\python.exe -m app.seed`。seed 幂等，导入 USDA 参考食物并停用旧演示条目，不改动历史快照。详见 [食物数据来源与复现](docs/food-data.md)。

## 局域网手机访问

在可信私有 Wi-Fi 上执行 `start.ps1 -Lan`，手机访问 `http://电脑局域网IP:8000`，例如 `http://192.168.1.20:8000`。必要时由你确认 Windows 私有网络防火墙放行该端口。同一个账号、同一个后端才能共享数据；不同电脑各自启动独立 SQLite 不会同步。不要把手机地址写成 localhost，也不要做公网端口转发。

本机/局域网 HTTP 仅供开发测试；正式健康数据必须用 HTTPS。HTTP 测试保持 `COOKIE_SECURE=false`；HTTPS 部署改成 `true`。

## Docker 与 PostgreSQL

先启动 Docker Desktop Linux engine，在 `.env` 设置强随机 `POSTGRES_PASSWORD`（建议字母数字，特殊字符须考虑数据库 URL 编码），然后：

```powershell
docker compose up --build -d
```

Compose 启动应用及 PostgreSQL 16，不向宿主机公开数据库端口，应用默认只映射 `127.0.0.1:8000`。数据存 PostgreSQL 命名卷；不要用 `docker compose down -v`，除非你确实要删除数据库。当前环境 Docker 引擎未启动，所以未声称镜像构建或 PostgreSQL 集成测试已通过。

正式部署应由 HTTPS 反向代理接入应用，设置准确 `APP_ORIGIN`、`COOKIE_SECURE=true`，配置代理可信边界、集中限流、秘密管理、备份恢复和监控。当前进程内登录限流适合单实例开发，多实例需共享限流存储。账号暂无邮箱验证、密码找回或 MFA。

## 数据与隐私

- 密码 scrypt；随机会话令牌仅存哈希；HttpOnly / SameSite Cookie；写请求校验 CSRF；同源访问不开放通配 CORS。
- 数据库按 user_id 隔离，计划/日志快照保留当时食物来源和版本。修改档案或日志后旧草案返回 409；重复确认已确认草案不重复创建计划。
- 确认过程以用户 revision 原子条件更新串行化用户写入，同用户同日期 active pointer 唯一；历史版本不会被覆盖。
- 数据库时间用 UTC；用餐日期按档案时区确定并保存。修改时区不会悄悄搬移历史记录；重新编辑用餐时间时按新时区归属。
- API 响应 no-store；关闭普通请求访问日志；普通日志不记录密码、健康档案、密钥或聊天全文。账号数据库保存聊天文本与结构化答复，支持导出及账号删除；向模型发送最近 6 轮文本上下文需要本次授权。原始照片不落盘保存。
- 删除账号级联删除当前库的会话、档案、手动目标、计划、日志、草案、反馈、体重和聊天记录。公共食物库保留；已导出文件、备份及第三方可能留存的数据不在删除能力内。

## 已知范围和发布门槛

当前支持账号、档案、一般结构计划、食物替换、实际记录、确定性汇总、反馈、确认调整、历史版本、七日记录视图、体重、LangChain 助手、导出和删除。预算是用户设定金额，不是当地市场价格；厨房与备餐条件作为上下文，演示模式只给简单蒸煮/选餐提示，不做库存、价格或时间优化。偏好只做明确食物名匹配，硬约束优先。食物限制不推断宗教细则，需填写具体禁止食材。

过敏校验针对本地整理的保守食物标签，未知复合菜或不支持的过敏原阻止推荐，不保证真实餐饮供应链无交叉接触。当前数值源于公开的 USDA 数据；历史 demo 快照与当前参考库分离。中文名称映射、美国品种和本地菜肴差异仍需持续校核。

公开上线前必须完成：更广泛本地食物数据及中文映射审查；营养策略专业审查；模型工具兼容与安全评估；PostgreSQL 集成和并发负载验证；HTTPS、集中限流、备份恢复、隐私/数据处理审查、账号恢复流程。语音、购物清单、周报、外卖下单、PWA 安装体验未实现，属于后续范围。

详见 `docs/design.md`、`docs/agent-workflow.md`、`docs/acceptance.md`。

## 照片模型

默认与文本共用 DeepSeek 模型，可设置 `LLM_VISION_MODEL` 单独指定支持图片输入的模型。实现依据 [DeepSeek 视觉文档](https://api-docs.deepseek.com/guides/vision/)。支持 JPEG / PNG / WebP；浏览器缩至最长边 1600 像素、重新编码去除原始元数据。服务端限制 4MB、4096 像素。照片分析失败不写记录，识别到食物才创建待确认记录。未识别到食物时明确提示。

## 可重复聊天界面验收

隔离服务使用 `work/ui-chat-fixture.db` 和视觉替身，不连接真实模型、不读取用户数据库。在项目根目录运行 `.\.venv\Scripts\python.exe backend/tests/ui_fixture_server.py`；另一个终端进入 frontend 后运行 `node tests/chat-smoke.mjs`。测试 1440px / 390px、多日草案确认与刷新保留、图片上传到待确认记录、手动核对后营养汇总。真实视觉准确率需要另行用标注餐食样本评估。

## 饮食健康知识库 RAG

已接入8个主题、16个片段，来自9个NIDDK/NHLBI官方页面。LangChain本地BM25与整理问法匹配通过RRF融合，支持部分口语和明确指代追问。助手页可浏览知识和试搜。无需额外Embedding Key。详见[知识库与评测](docs/health-rag.md)、[GitHub方法参考](docs/rag-references.md)。中文整理未经临床专业审查。

在 frontend 执行 `node tests/rag-smoke.mjs` 可用合成账号运行真实模型与引用界面验收（会产生 API 用量，完成后删除测试账号）。


## 桌面启动

双击桌面“启动健康饮食Agent.cmd”，调用项目launch.ps1，后台启动成功后打开助手页。重复运行复用已就绪服务；端口被其他服务占用时显示原因，不停止其他程序。日志位于work/logs。不会自动安装依赖或重建前端，修改源码后需构建/重启。

调试：`powershell -NoProfile -ExecutionPolicy Bypass -File .\launch.ps1 -NoBrowser`。start.ps1仍可前台运行，用Ctrl+C停止。桌面脚本绑定当前项目路径，移动项目后需更新路径。
