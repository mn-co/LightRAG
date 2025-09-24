# LightRAG Agents 指南

本指南从“Agent”视角梳理 LightRAG 工程的模块职责、数据流以及可扩展点，便于快速理解整体框架并在需要时定制或扩展各类能力。

## 文档目的
- 获取项目的宏观结构与关键目录定位。
- 理解文档索引、知识图谱构建、检索生成等核心 Agent 的分工与协作。
- 了解模型接入、存储插件、API/WebUI 等配套 Agent，便于二次开发与部署。

## 工程总体结构
| 目录 / 文件 | Agent 角色定位 |
| --- | --- |
| `lightrag/` | 核心运行时：`LightRAG` 类、`QueryParam`、操作流水线、公共常量与工具。 |
| `lightrag/operate.py` | 索引 / 检索算法核心 Agent：分块、实体/关系抽取、关键词提取、上下文组装。 |
| `lightrag/base.py` | 存储抽象基类、查询参数、文档状态定义，Agent 通用基座。 |
| `lightrag/kg/` | 持久化 Agent 插件：向量库、KV、图数据库、文档状态多种实现与共享锁机制。 |
| `lightrag/llm/` | 模型适配 Agent：OpenAI、Ollama、Anthropic、Bedrock、HuggingFace 等绑定与配置。 |
| `lightrag/rerank.py` | 重排序 Agent：统一调用 Jina/Cohere/阿里等 Rerank API。 |
| `lightrag/api/` | FastAPI 服务 Agent：REST 接口、Ollama 兼容 API、鉴权、运行参数管理。 |
| `lightrag/tools/` | 运行辅助 Agent：初始化脚本、可视化工具。 |
| `lightrag_webui/` | 前端 Agent：基于 Vite/React 的 Web UI，驱动图谱可视化与操作。 |
| `examples/` | 使用示例与脚本。 |
| `docs/` | 官方流程图与部署文档。 |
| `tests/` | 集成 / 单元测试覆盖核心 Agent 工作流。 |

## 核心 Agent 分层

### 1. 核心调度 Agent（`LightRAG` Core）
- 所在：`lightrag/lightrag.py`
- 职责：聚合所有存储、模型、辅助配置，暴露 `insert/ainsert`、`query/aquery`、`aquery_data` 等同步/异步接口。
- 关键结构：
  - `LightRAG` 数据类以配置项方式声明默认存储、并发参数、阈值等，可通过环境变量覆盖。
  - `QueryParam` 描述查询模式、TopK、Token Budget、流式输出、上下文格式、用户自定义提示等。
  - 内置 `priority_limit_async_func_call` 限流装饰器，统一约束 LLM 请求并提供多层超时保护。

### 2. 索引构建 Agent（Document Pipeline）
- 入口：`LightRAG.ainsert` -> `apipeline_enqueue_documents` -> `apipeline_process_enqueue_documents`。
- 流程：
  1. **排队 Agent**：校验/生成文档 ID，写入 `DocStatusStorage`（如 JSON/Redis/Postgres），标记状态与追踪编号。
  2. **分块 Agent**：`chunking_by_token_size` 按 Token 或指定字符切分，保留原文与位置信息供引用。
  3. **抽取 Agent**：`extract_entities` 调用 LLM 生成实体/关系候选，支持多次 gleaning 与缓存，解析 JSON 并规避格式错误。
  4. **合并 Agent**：`merge_nodes_and_edges` 去重、合并候选，写入知识图谱、向量库、KV 存储，并维护引用链路。
  5. **持久化 Agent**：`_insert_done` 触发各存储 `index_done_callback`，将内存增量刷新到磁盘/远程服务。
- 共享能力：
  - `lightrag/kg/shared_storage.py` 提供跨协程/多实例的命名空间、锁、流水线状态共享。
  - 通过 `llm_response_cache` 进行提示缓存，避免重复抽取。

### 3. 知识图谱与存储 Agent
- 抽象基类：`StorageNameSpace`、`BaseVectorStorage`、`BaseKVStorage`、`BaseGraphStorage`、`DocStatusStorage` 定义统一能力契约。
- 插件注册：`lightrag/kg/__init__.py` 中 `STORAGES`、`STORAGE_ENV_REQUIREMENTS` 列出可选实现与所需环境变量，支持 JSON、Redis、Postgres、Mongo、Milvus、Qdrant、Faiss、Neo4j、Memgraph 等。
- 命名空间：`lightrag/namespace.py` 固化实体、关系、Chunk、缓存等命名约定，确保多后端协作一致。
- Graph Agent：`chunk_entity_relation_graph` 默认基于 NetworkX，可切换 Neo4j/PG 等；所有边视为无向，强调度量与描述同步更新。

### 4. 检索与生成 Agent
- 入口：`LightRAG.aquery/aquery_data`。
- 核心组件：
  - **关键词 Agent**：`extract_keywords_only` 使用指定 LLM 生成高/低级关键词，支持缓存与自定义历史对话。
  - **上下文构建 Agent**：`kg_query` 按模式从实体/关系/Chunk 组合上下文，支持 Round-robin 混排、本地/全局融合、向量检索与 Rerank。
  - **模式说明**：
    | 模式 | 行为 |
    | --- | --- |
    | `local` | 依赖低级关键词，从节点视角找邻域实体/关系。 |
    | `global` | 使用高级关键词，自关系出发扩展图谱。 |
    | `hybrid` | 同时启用 local/global，两类上下文交替合并。 |
    | `mix` | 在 hybrid 基础上引入向量 Chunk 与 rerank。 |
    | `naive` | 仅使用向量库进行经典 RAG，不走知识图谱。 |
    | `bypass` | 直接调用 LLM，无上下文检索。 |
  - **回答 Agent**：根据 `response_type` 与自定义提示拼接 System Prompt，调用模型生成文本或流式输出；提供 `only_need_context`/`only_need_prompt` 便于外部组合。
  - **结构化输出**：`aquery_data` 可直接返回实体/关系/Chunk 原始数据，便于可视化或下游处理。

### 5. 模型适配 Agent
- LLM：`lightrag/llm/*.py` 封装 OpenAI、Azure、Anthropic、Bedrock、Ollama、HuggingFace、Jina、硅基流动等 API，统一 `llm_model_func` 接口（`prompt`, `system_prompt`, `history_messages`, `enable_cot`, `stream`）。
- 绑定选项：`binding_options.py` 提供命令行/环境变量解析与默认参数，兼容 API 服务器对接。
- Embedding：`EmbeddingFunc` 结构体描述向量化函数、维度、批量限制；索引与检索均依赖该 Agent。
- Rerank：`rerank.py` 将 Cohere/Jina/阿里等服务统一化，支持超时重试与错误提示。
- Prompt：`prompt.py` 统一管理系统提示、示例、标签，方便本地化。

### 6. API 与 运维 Agent
- FastAPI Server：`lightrag/api/lightrag_server.py` 启动 Web 服务，处理配置校验、日志、鉴权、热加载与优雅停止。
- 路由：
  - `routers/document_routes.py`：文档上传、状态查询、批处理。
  - `routers/query_routes.py`：接口化查询与数据模式输出。
  - `routers/graph_routes.py`：知识图谱可视化与节点检索。
  - `routers/ollama_api.py`：模拟 Ollama 聊天模型，让第三方前端直接访问。
- 实用工具：`api/utils_api.py` 输出环境概览、ASCII 仪表盘；`auth.py` 支持简单账号密码鉴权。
- 守护与部署：提供 `docker-compose.yml`、`lightrag.service.example` 以及 `k8s-deploy/` 便于容器化与系统服务部署。

### 7. 前端与生态配套 Agent
- `lightrag_webui/`：Vite + React + Tailwind 实现的 Web UI，聚合上传、查询、图谱浏览、向量列表等界面。
- `reproduce/`、`examples/`：复现脚本与使用案例，覆盖 Chat、Index、Query 多种场景。
- `tests/`：针对 API 与 Graph 操作的单测/集成测试，验证核心 Agent 的关键路径。

## 数据流总结

### 文档索引流
1. 用户调用 `insert/ainsert` → 核心调度 Agent 生成追踪任务。
2. 分块 Agent 产生 Chunk 并写入 KV/向量候选。
3. 抽取 Agent 调用 LLM 解析实体关系，多轮纠错与缓存校验。
4. 合并 Agent 将数据写入图数据库、向量库、KV，并同步文档状态。
5. 持久化 Agent 刷新各存储后返回 Track ID，供 WebUI/API 查询进度。

### 查询生成流
1. 用户携带 `QueryParam` 调用 `query/aquery`。
2. 关键词 Agent 基于历史与提示抽取高低层关键词（或复用用户输入）。
3. 上下文 Agent 结合图谱、向量检索、Rerank 组装上下文，控制 Token 预算。
4. 回答 Agent 拼接系统提示，调用模型生成响应或流式输出；可同时写入缓存。
5. API / WebUI 可通过 `aquery_data` 拿到结构化结果进行可视化或追踪引用。

## 扩展与最佳实践
- **新增存储后端**：实现对应 Base 类并在 `STORAGES` 中注册，同时补充必需环境变量与初始化逻辑。
- **替换模型服务**：自定义 `llm_model_func` 并传入 `LightRAG` 或 `QueryParam.model_func`，亦可扩展 `binding_options` 支持 CLI 配置。
- **控制缓存策略**：通过 `.env` 中的 `ENABLE_LLM_CACHE`、`TOP_K` 等变量调整缓存与上下文行为，重构 `hashing_kv` 可实现分布式缓存。
- **多租户 / 工作区**：依赖 `workspace` 参数隔离存储前缀，配合 `NameSpace` 保证命名一致性。
- **测试 / 监控**：复用 `tests/` 案例扩展自测；利用 `pipeline_status`、`DocumentManager` 输出的状态面板监控索引进度；必要时在 API 层添加指标导出。

---
通过上述 Agent 视角，可以快速定位 LightRAG 中各模块的职责边界，并据此定制索引策略、接入新模型或扩展运维能力。
