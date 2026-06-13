# Python AgentOps Harness SDD - 执行计划

**状态：** 草案 v0.1  
**日期：** 2026-06-13  
**源系统：** `D:\go-tiny-claw` Go 原实现  
**目标系统：** `D:\go-tiny-claw\python-claw` Python AgentOps Harness  
**推荐路线：** 生产骨架先行，Mock Engine 闭环

## 1. 背景

`go-tiny-claw` 的 Go 原实现是一个轻量 Agent Harness，核心价值不是框架封装，而是显式掌控 Agent Loop、工具编排、上下文管理、审批和运行反馈。

本次 Python 重构不是逐行翻译 Go 代码，而是在保留 Go 版核心行为的基础上，构建一套更适合生产演进的 Python AgentOps Harness。Python 版从第一天起按 CLI、Web/API、ChatOps、审批、持久化、可观测和测试闭环规划，但第一阶段不接真实 LLM 和真实飞书 SDK，先用 Mock LLM 跑通核心链路。

Go 版事实基线主要来自：

- `D:\go-tiny-claw\cmd\claw\main.go`：本地 CLI 入口。
- `D:\go-tiny-claw\cmd\agentops\main.go`：飞书 ChatOps 服务入口。
- `D:\go-tiny-claw\cmd\bench\main.go`：benchmark 入口。
- `D:\go-tiny-claw\internal\engine\loop.go`：手写 ReAct Agent Loop。
- `D:\go-tiny-claw\internal\tools\*.go`：工具注册和文件/shell 工具。
- `D:\go-tiny-claw\internal\context\*.go`：session、prompt composer、compactor、recovery、skills。
- `D:\go-tiny-claw\internal\feishu\*.go`：ChatOps 和审批。
- `D:\go-tiny-claw\internal\observability\*.go`：trace 和 usage tracking。

## 2. 目标

Python 版必须达成以下目标：

1. 保留 Go 版 Harness over Framework 思想，核心 Agent Loop 由项目自身实现。
2. 同时规划 CLI、本地 API、ChatOps、审批、持久化和可观测能力。
3. 使用 Mock LLM 先跑通确定性的 Engine、工具调用、审批和持久化闭环。
4. 使用端口接口隔离 LLM、工具、Reporter、ChatOps、Repository 和 Trace。
5. 默认测试不依赖真实 LLM、飞书、外部数据库或外部网络。
6. 补齐 Go 版工具系统中不完整的 workspace sandbox 边界，避免路径逃逸。
7. 保持文件工具和 `edit_file` 的关键语义与 Go 版兼容。
8. 为后续 DeepSeek/OpenAI-compatible adapter、飞书 adapter、PostgreSQL 和 benchmark 留出清晰里程碑。

## 3. 非目标

第一阶段不做：

1. 不接真实 LLM API。
2. 不实现真实飞书 SDK adapter。
3. 不实现 `spawn_subagent`，只预留接口或里程碑。
4. 不构建通用多智能体平台。
5. 不引入 LangChain、AutoGen、CrewAI 等 agent 框架接管核心 loop。
6. 不引入 Celery、Redis、Kafka、Temporal 等重型分布式组件。
7. 不让默认测试依赖真实 API key、真实飞书服务、外部 PostgreSQL 或外部网络。
8. 不把 Go 版现有安全缺口原样复制到 Python 版。

## 4. 固定技术栈

| 层级 | 选择 |
|---|---|
| Python | Python 3.12+ |
| 包管理/构建 | `pyproject.toml`，优先 `uv` 或标准 `pip` 可兼容 |
| CLI | Typer |
| Web/API | FastAPI |
| ASGI Server | Uvicorn |
| 数据访问 | SQLAlchemy 2.x |
| 数据迁移 | Alembic |
| 本地/测试数据库 | SQLite |
| 生产目标数据库 | PostgreSQL |
| 配置 | Pydantic Settings 或等价配置层 |
| 测试 | pytest |
| HTTP 测试 | httpx / FastAPI TestClient |
| 代码质量 | ruff，必要时 mypy |
| LLM 第一阶段 | Mock LLM Gateway |
| 后续真实 LLM | OpenAI-compatible adapter，支持 DeepSeek/智谱等兼容接口 |

禁止默认引入：

- LangChain、AutoGen、CrewAI 作为核心 Agent 框架。
- Django/DRF 作为第一版主框架。
- Celery、Redis、Kafka、Temporal。
- 默认测试中的真实 LLM、飞书或外部数据库依赖。
- 硬编码 API key、app secret、数据库密码。

## 5. 推荐目录结构

```text
D:\go-tiny-claw\python-claw
  pyproject.toml
  README.md
  alembic.ini
  src\python_claw\
    __init__.py
    domain\
    application\
    ports\
    adapters\
      cli\
      api\
      persistence\
      tools\
      reporters\
      llm\
      chatops\
      observability\
    config\
  tests\
    unit\
    integration\
```

依赖方向固定为：

```text
domain <- application <- ports <- adapters <- config
```

边界规则：

- `domain` 不依赖 FastAPI、Typer、SQLAlchemy、文件系统、HTTP、LLM SDK 或飞书 SDK。
- `application` 只依赖 `domain` 和 `ports`。
- `ports` 只定义接口和边界模型。
- `adapters` 负责 CLI、API、数据库、文件系统、shell、LLM、ChatOps 和观测实现。
- `config` 只负责配置加载和对象装配，不承载业务规则。

## 6. 核心组件职责

### 6.1 domain

定义纯领域对象和状态机：

- `Message`
- `ToolCall`
- `ToolResult`
- `ToolDefinition`
- `Session`
- `AgentRun`
- `ApprovalRequest`
- `TraceSpan`
- `UsageRecord`

状态要求：

- `AgentRun` 只能从 `PENDING/RUNNING` 进入 `COMPLETED/FAILED/CANCELLED/TIMED_OUT`。
- `ApprovalRequest` 只能从 `PENDING` 进入 `APPROVED/REJECTED/EXPIRED`。
- 非法状态流转必须 fail-fast。
- 集合字段不得为 `None`，默认使用空列表或空字典。
- 时间应由调用方传入或通过可替换 clock 生成，便于测试。

### 6.2 application

实现 Harness 主流程：

- `AgentEngine`
- `PromptComposer`
- `ContextCompactor`
- `RecoveryManager`
- `ReminderInjector`
- `ApprovalService`
- `SessionService`
- `RunService`
- `ToolExecutionService`

`application` 不得直接依赖 FastAPI request、Typer command、SQLAlchemy session、飞书 SDK 或真实 LLM SDK。

### 6.3 ports

定义可替换接口：

- `LlmGateway`
- `AgentTool`
- `ToolRegistry`
- `SessionRepository`
- `MessageRepository`
- `RunRepository`
- `ToolExecutionRepository`
- `ApprovalRepository`
- `Reporter`
- `ChatOpsPort`
- `TraceRecorder`
- `Clock`

第一阶段必须提供 fake/mock adapter，使核心流程可确定性测试。

### 6.4 adapters

第一阶段实现：

- Typer CLI。
- FastAPI app，至少包含 health 和 basic run endpoint。
- SQLAlchemy repository。
- SQLite 数据库配置。
- Alembic migration。
- `read_file`、`write_file`、`edit_file`、`bash` 工具。
- `MockLlmGateway`。
- `TerminalReporter` 和 `NoopReporter`。
- 轻量 TraceRecorder。

后续实现：

- OpenAI-compatible LLM adapter。
- Feishu ChatOps adapter。
- PostgreSQL profile。
- Benchmark runner。

## 7. 数据模型和持久化

第一版使用 SQLAlchemy 2.x 建模，Alembic 管理 schema。默认开发/测试使用 SQLite，生产目标为 PostgreSQL。

首批表：

```text
agent_sessions
agent_messages
agent_runs
tool_executions
approval_requests
trace_spans
usage_records
```

### 7.1 agent_sessions

字段：

- `id`
- `workspace_root`
- `status`
- `created_at`
- `updated_at`
- `total_prompt_tokens`
- `total_completion_tokens`
- `total_cost`

用途：

- 断点恢复。
- 工作区绑定。
- 累计 usage 和 cost。

### 7.2 agent_messages

字段：

- `id`
- `session_id`
- `role`
- `content`
- `tool_calls_json`
- `tool_call_id`
- `usage_json`
- `created_at`

要求：

- Tool observation 仍按 Go 语义作为 user-role message 写回。
- `tool_call_id` 用于关联 assistant tool call 和 tool result。
- `tool_calls_json` 只保存 assistant message 的 tool calls。

### 7.3 agent_runs

字段：

- `id`
- `session_id`
- `status`
- `started_at`
- `completed_at`
- `error_message`
- `max_turns`
- `runtime_limit_seconds`

要求：

- 每次执行都必须可审计。
- run 失败不能丢失已产生的 message 和 tool execution。

### 7.4 tool_executions

字段：

- `id`
- `run_id`
- `tool_call_id`
- `tool_name`
- `arguments_json`
- `output_preview`
- `is_error`
- `started_at`
- `completed_at`
- `duration_ms`

要求：

- 非 0 shell exit code 记录为 `is_error=true` 或工具错误结果，但不得直接让 run 崩溃。
- `output_preview` 必须截断，避免数据库和日志膨胀。

### 7.5 approval_requests

字段：

- `id`
- `run_id`
- `tool_call_id`
- `tool_name`
- `arguments_preview`
- `status`
- `decision_reason`
- `created_at`
- `decided_at`
- `expires_at`

要求：

- 审批拒绝原因必须作为 tool observation 写回上下文。
- 第一阶段可用同步策略模拟审批，后续支持 ChatOps 异步恢复。

### 7.6 trace_spans

字段：

- `id`
- `run_id`
- `parent_span_id`
- `name`
- `started_at`
- `ended_at`
- `duration_ms`
- `attributes_json`

要求：

- 记录 Agent run、turn、LLM generate、tool execute 等关键节点。
- 不记录敏感 payload。

### 7.7 usage_records

字段：

- `id`
- `run_id`
- `provider`
- `model`
- `prompt_tokens`
- `completion_tokens`
- `cost`
- `metadata_json`
- `created_at`

要求：

- 第一阶段 Mock LLM 可写 0 或固定 usage。
- 真实 usage 只在后续真实 LLM adapter 中启用。

## 8. Agent 运行流程

主流程：

1. CLI/API 创建或恢复 session。
2. 追加 user message。
3. 创建 `agent_run`，状态为 `RUNNING`。
4. `PromptComposer` 生成 system message。
5. `PromptComposer` 加载 workspace 下的 `AGENTS.md` 和 `.claw/skills/**/SKILL.md`。
6. `SessionService` 获取 working memory。
7. 如果 working memory 开头是孤立 tool result，则剔除或注入占位 user message，保持协议连续性。
8. `ContextCompactor` 对超长上下文做截断或摘要占位。
9. `LlmGateway.generate(...)` 返回 assistant message 和 tool calls。
10. 持久化 assistant message。
11. 如果无 tool call，run 标记 `COMPLETED`。
12. 如果有 tool call，经 `ToolRegistry` 执行。
13. 每个工具执行前通过 approval policy。
14. 被审批拒绝时，拒绝原因作为 error tool result 写回模型上下文。
15. 工具结果作为 observation message 写入 session。
16. `RecoveryManager` 对工具错误注入修复提示。
17. `ReminderInjector` 检测连续同参数失败，达到阈值后写入提醒消息。
18. 进入下一轮，直到完成、失败、取消、超出 `max_turns` 或超时。

第一阶段必须支持：

- `max_turns`
- 单工具 timeout
- shell output truncation
- run status persistence
- deterministic mock LLM script
- terminal/noop reporter event

后续支持：

- `max_runtime_seconds`
- cancellation
- ChatOps 异步审批恢复
- real usage/cost tracking

## 9. 工具系统

首批工具：

```text
read_file
write_file
edit_file
bash
```

`spawn_subagent` 第一版不实现，只保留里程碑或接口预留。

### 9.1 read_file

要求：

- 参数：`path`。
- 路径必须基于 workspace root 解析。
- `resolve()` 后仍必须位于 workspace 内。
- 禁止 workspace 外绝对路径。
- 禁止 `..` 逃逸。
- 禁止符号链接逃逸。
- 输出默认截断，例如 8000 字符。

### 9.2 write_file

要求：

- 参数：`path`、`content`。
- 自动创建父目录。
- 写入前执行 workspace sandbox 校验。
- 生产/ChatOps 策略下默认需要审批。
- 不允许写入 workspace 外。

### 9.3 edit_file

要求：

- 参数：`path`、`old_text`、`new_text`。
- 写入前读取文件并校验 sandbox。
- 保留 Go 版 fuzzy replace 语义：
  1. 精确匹配。
  2. 换行归一化匹配。
  3. trim 匹配。
  4. 逐行忽略缩进匹配。
- 0 次匹配必须失败。
- 多次匹配必须失败，并要求提供更多上下文。
- 生产/ChatOps 策略下默认需要审批。

### 9.4 bash

要求：

- 参数：`command`。
- 在 workspace 内执行。
- 默认 30 秒超时。
- 捕获 stdout 和 stderr。
- 输出截断。
- 非 0 exit code 作为 tool result 返回，不直接打崩 run。
- 执行前通过 dangerous command policy。
- Windows 环境可配置 shell executor，但工具名保持 `bash` 以兼容 Go 语义。

## 10. 审批和安全策略

默认策略：

- `read_file`：放行。
- `write_file`：生产/ChatOps 下需要审批。
- `edit_file`：生产/ChatOps 下需要审批。
- `bash`：命中高危模式需要审批。

高危命令模式至少包含：

```text
rm -r
sudo
drop
nginx -s
systemctl
kill
```

策略要求：

- 审批策略必须可配置。
- 审批拒绝不能让 run 直接崩溃。
- 审批拒绝原因必须作为 observation 写回 session。
- ChatOps 异步审批是后续里程碑，第一阶段允许同步 fake approval。
- 默认测试必须覆盖批准、拒绝、过期三类状态。

安全要求：

- 不输出密钥、完整敏感请求头或敏感正文。
- trace 和日志只保存必要 preview。
- 配置项通过环境变量、`.env` 或 profile 注入。
- 示例密钥只能使用占位符。
- 默认测试不得要求真实 API key。

## 11. ChatOps 设计

Python 版采用通用 `ChatOpsPort`，飞书是第一个生产 adapter，但不进入第一阶段实现。

`ChatOpsPort` 需要表达：

- 接收用户消息。
- 发送 reporter event。
- 发送审批请求。
- 接收审批决定。
- 将 ChatOps 会话映射到 agent session。

第一阶段只需：

- 定义端口。
- 用 fake adapter 或 noop adapter 测试 application 边界。
- 在 SDD 和里程碑中明确 Feishu adapter 后续实现。

后续 Feishu adapter 要求：

- webhook 事件校验。
- 普通消息触发 agent run。
- `approve <approval_id>` 和 `reject <approval_id>` 解析。
- 每个 chat 使用独立 reporter/session。
- webhook handler 快速返回，长任务由受控 run 机制执行。

## 12. LLM 适配

第一阶段：

- 只实现 `MockLlmGateway`。
- Mock LLM 支持脚本化响应，例如：
  - 第 1 轮返回 assistant tool call。
  - 第 2 轮读取 observation 后返回最终 assistant message。
- Mock LLM 可返回固定 usage，用于 usage 链路测试。

后续：

- 实现 OpenAI-compatible adapter。
- 支持 DeepSeek/智谱等兼容 Chat Completions 的接口。
- API key、base URL、model 必须通过配置注入。
- 真实 LLM 测试必须 opt-in，默认跳过。

## 13. Reporter 和可观测

第一阶段 Reporter：

- `TerminalReporter`
- `NoopReporter`
- 测试用 `RecordingReporter`

Reporter 事件：

- `on_thinking`
- `on_tool_call`
- `on_tool_result`
- `on_message`
- `on_approval_requested`
- `on_run_failed`
- `on_run_completed`

Trace 要求：

- 记录 run、turn、LLM generate、tool execute。
- attributes 中不得记录完整敏感 payload。
- trace 可存数据库，也可后续导出 JSON。

Usage 要求：

- 第一阶段 Mock usage 可为 0。
- 数据结构必须支持真实 provider usage。

## 14. 测试策略

### 14.1 Unit Test

必须覆盖：

- domain 状态流转。
- approval lifecycle。
- working memory windowing。
- context compaction。
- fuzzy edit replacement。
- workspace sandbox。
- dangerous command policy。
- recovery hint injection。
- repeated failure reminder。
- tool registry lookup。

### 14.2 Integration Test

必须覆盖：

- Alembic 从空 SQLite 库创建 schema。
- SQLAlchemy repository 基础读写。
- CLI run with Mock LLM。
- FastAPI health endpoint。
- FastAPI basic run endpoint。
- Mock LLM + 真实文件工具闭环。
- approval rejection 写回 observation。
- tool execution 持久化。

### 14.3 E2E Opt-In

后续覆盖：

- 真实 OpenAI-compatible adapter。
- 真实飞书 webhook。
- PostgreSQL profile。
- benchmark runner。

默认跳过，不进入普通 `pytest`。

## 15. 里程碑计划

### M1 Python Skeleton

交付：

- `pyproject.toml`
- `src/python_claw` layout
- Typer CLI 基线
- FastAPI app 基线
- 配置加载
- pytest 基线
- ruff 配置

验收：

- `pytest` 通过。
- CLI 能输出 help。
- FastAPI health endpoint 可测。

### M2 Domain + Ports

交付：

- 领域模型。
- 端口接口。
- 状态流转和不变量测试。

验收：

- domain 不依赖 FastAPI、Typer、SQLAlchemy 或外部 SDK。
- 状态流转测试通过。

### M3 Persistence

交付：

- SQLAlchemy models。
- Alembic migration。
- SQLite repository。
- session/message/run/approval/tool execution 基础读写。

验收：

- Alembic 可从空库初始化 schema。
- repository integration tests 通过。

### M4 Tools + Safety

交付：

- `read_file`
- `write_file`
- `edit_file`
- `bash`
- workspace sandbox。
- dangerous command policy。

验收：

- 文件工具不能逃逸 workspace。
- `edit_file` fuzzy replace 测试通过。
- shell timeout/output/exit code 测试通过。

### M5 Mockable Agent Engine

交付：

- `AgentEngine`。
- `PromptComposer`。
- `ContextCompactor`。
- `RecoveryManager`。
- `ReminderInjector`。
- `MockLlmGateway`。
- terminal/noop reporter。

验收：

- Mock LLM 可触发工具调用并完成 run。
- tool observation 持久化。
- run 状态正确完成或失败。

### M6 CLI/API Parity Baseline

交付：

- `python-claw run --prompt ... --dir ... --session ...`
- FastAPI basic run endpoint。
- run audit query 基线。

验收：

- CLI 可完成 Mock LLM 任务。
- API 可创建 run。
- run 可通过数据库审计。

### M7 ChatOps Port + Feishu Plan

交付：

- `ChatOpsPort`。
- ChatOps reporter/approval 协议。
- fake ChatOps adapter 测试。

验收：

- application 不依赖飞书 SDK。
- 审批协议可由 fake adapter 驱动。

### M8 Real LLM Adapter

交付：

- OpenAI-compatible adapter。
- DeepSeek/智谱配置示例。
- opt-in 真实 LLM 测试。

验收：

- 默认测试不调用真实 LLM。
- opt-in 配置齐全时可运行真实调用 smoke test。

### M9 Observability + Benchmark

交付：

- trace export。
- usage/cost tracking。
- benchmark runner。
- 对齐 Go 的两个 benchmark 场景。

验收：

- benchmark 可在 Mock 模式稳定运行。
- 真实 LLM benchmark 为 opt-in。

## 16. 第一阶段验收标准

第一阶段完成时必须满足：

1. `pytest` 通过。
2. Alembic 能从空 SQLite 库创建 schema。
3. Mock LLM 能触发工具调用并完成 run。
4. 工具执行、审批拒绝、错误恢复都能写入数据库。
5. 文件和 shell 工具不能逃逸 workspace。
6. 默认测试不需要真实 API key、飞书、外部数据库、外部网络。
7. CLI 和 FastAPI health/basic run endpoint 可用。
8. 文档能指导下一轮 AI 分阶段实施。

## 17. 执行规则

后续实现 Python 版时必须遵守：

1. 先读本 SDD，再改代码。
2. 每个里程碑只实现必要文件。
3. 先写或更新测试，再实现核心逻辑。
4. 默认不触碰 Go 原实现和 Java 重构实现。
5. 不把临时文件、缓存、虚拟环境、数据库文件或构建产物作为交付成果。
6. 临时文件、缓存和生成物不得放到 C: 盘。
7. 真实密钥不得写入源码、测试或文档。
8. 如发现 Go 版行为和本 SDD 不一致，以 Go 可运行代码为事实来源，以本 SDD 为 Python 目标方向，并在汇报中说明差异。

## 18. 后续开放问题

以下问题不阻塞第一阶段：

1. 生产运行是否需要后台任务队列，还是由 FastAPI 进程内受控 run 先承载。
2. Feishu adapter 是否需要支持卡片消息，还是先用纯文本消息。
3. PostgreSQL 集成测试是否使用 Testcontainers 等价方案，还是只保留 opt-in 本地 PostgreSQL。
4. `spawn_subagent` 是否在 M10 后进入实现。
5. benchmark 是否完全复用 Go 版两个场景，还是扩展 Python 专属场景。

## 19. 推荐下一步

下一轮实施建议从 M1 开始：

1. 创建 Python 工程骨架。
2. 建立 pytest/ruff 基线。
3. 实现 Typer CLI help 和 FastAPI health。
4. 不接真实 LLM、不接数据库业务逻辑，先确保工程可运行。

完成 M1 后，再进入 M2 Domain + Ports。
