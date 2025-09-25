# 项目中文说明

本文件用于记录 LightRAG 项目的关键要点及当前改造计划。

- 项目核心由 `LightRAG` 类驱动，负责协调索引与查询流程。
- 文档在插入时会经过分块、实体关系抽取以及图谱合并等步骤。
- 查询流程基于关键词提取、知识图谱检索与生成模型组合完成回答。
- API 层提供文档上传、扫描、查询等接口。
- 若需扩展存储或模型服务，可实现对应的抽象类并在配置中注册。

## 功能改造计划：按文档控制知识图谱构建（`x-enable-kg`）

1. **接口层改造**  
   - 在 `/documents/text(s)` 与 `/documents/upload` 等路由读取自定义 Header `x-enable-kg`，解析为布尔值并传入后续流程。
   - Header 与文档绑定：文本批量插入时需要针对每条文本维护对应布尔列表。

2. **管道与入队流程扩展**  
   - 更新 `pipeline_index_texts`、`pipeline_enqueue_file` 与 `LightRAG.ainsert` 等入口，新增 `enable_kg` 参数并传递到 `apipeline_enqueue_documents`。
   - 在多文档场景下保持 `enable_kg` 与每个文档一一对应，默认值为 `True`。

3. **文档状态存储结构调整**  
   - 为 `DocProcessingStatus` 增加 `enable_kg: bool = True` 字段，并确保所有 `doc_status.upsert` 调用写入该值。
   - 扩展 JSON、Redis、Mongo、Postgres 等文档状态存储实现：缺省时补全为 `True`，Postgres 需添加新的布尔列及迁移逻辑。

4. **索引流程按需跳过知识图谱**  
   - 在 `apipeline_process_enqueue_documents` 中，根据文档的 `enable_kg` 决定是否执行 `_process_extract_entities` 与 `merge_nodes_and_edges`。
   - 即使跳过知识图谱，也要写入文本切片、向量库并调用 `_insert_done`，同时记录日志说明理由。

5. **响应模型与文档接口展示**  
   - 更新 `DocStatusResponse` 等 Pydantic 模型增加 `enable_kg` 字段，并同步 API 示例。
   - API 调用在查看文档状态时需能看到该标志，便于后续检索流程识别。

6. **验证与文档更新**  
   - 为新增行为补充 FastAPI 端点单测或集成测试，覆盖 KG 跳过与构建两种路径。
   - API 文档注释中补充描述。

注意：不用改动webui前端模块，保持默认行为，只要在接口层添加功能即可
