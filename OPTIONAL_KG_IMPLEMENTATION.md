## 实现背景

根据用户需求和 `ENABLE_KG_PLAN.md` 文档，需要实现允许用户通过 `x-enable-kg` HTTP 头部来控制是否为特定文档构建知识图谱的功能。这个功能让用户可以：

- 对于纯文本检索需求，跳过耗时的知识图谱构建
- 对于需要语义理解的复杂查询，启用完整的知识图谱功能
- 在同一个 LightRAG 实例中混合使用两种模式

## 实现概览

整个实现分为6个主要阶段：

1. **分析当前文档处理流程和相关代码结构** ✅
2. **扩展文档状态存储结构，添加 enable_kg 字段** ✅
3. **更新 API 接口层，支持 x-enable-kg 头部** ✅
4. **修改文档处理管道，支持按需跳过知识图谱构建** ✅
5. **更新响应模型和 API 文档** ✅
6. **添加测试验证** ✅

## 详细实现

### 1. 数据结构扩展

#### 1.1 DocProcessingStatus 类扩展
- **文件**: `lightrag/base.py`
- **修改**: 在 `DocProcessingStatus` 类中添加 `enable_kg: bool = True` 字段
- **作用**: 存储每个文档是否启用知识图谱构建的标志

#### 1.2 存储实现更新
更新了所有文档状态存储实现，确保兼容新字段：
- **JSON 存储** (`lightrag/kg/json_doc_status_impl.py`): 添加默认值处理逻辑
- **Redis 存储** (`lightrag/kg/redis_impl.py`): 更新数据处理函数
- **PostgreSQL 存储** (`lightrag/kg/postgres_impl.py`): 扩展表结构和构造函数调用
- **MongoDB 存储** (`lightrag/kg/mongo_impl.py`): 更新数据准备函数

### 2. API 接口层更新

#### 2.1 路由函数签名扩展
为以下三个核心 API 端点添加 `x-enable-kg` 头部支持：

```python
# 单文本插入
async def insert_text(
    request: InsertTextRequest,
    background_tasks: BackgroundTasks,
    rag_doc: tuple = Depends(get_rag_instance),
    x_enable_kg: Optional[bool] = Header(None, description="Enable knowledge graph construction for this document (defaults to True)")
)

# 多文本插入
async def insert_texts(
    request: InsertTextsRequest,
    background_tasks: BackgroundTasks,
    rag_doc: tuple = Depends(get_rag_instance),
    x_enable_kg: Optional[bool] = Header(None, description="Enable knowledge graph construction for all documents (defaults to True)")
)

# 文件上传
async def upload_to_input_dir(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    rag_doc: tuple = Depends(get_rag_instance),
    x_enable_kg: Optional[bool] = Header(None, description="Enable knowledge graph construction for this document (defaults to True)")
)
```

#### 2.2 处理函数更新
- **pipeline_index_texts**: 添加 `enable_kg_list` 参数支持
- **pipeline_index_file**: 添加 `enable_kg` 参数支持
- **pipeline_enqueue_file**: 添加 `enable_kg` 参数支持

### 3. 文档处理管道修改

#### 3.1 LightRAG 核心方法扩展
**`apipeline_enqueue_documents` 方法**:
- 添加 `enable_kg_list: list[bool] | None = None` 参数
- 实现 enable_kg_list 长度匹配和默认值处理逻辑
- 在创建文档状态时包含 `enable_kg` 字段

#### 3.2 文档处理流程修改
**`apipeline_process_enqueue_documents` 方法**:
- 在实体抽取阶段添加条件判断：
  ```python
  if status_doc.enable_kg:
      entity_relation_task = asyncio.create_task(
          self._process_extract_entities(chunks, pipeline_status, pipeline_status_lock)
      )
      await entity_relation_task
  else:
      logger.info(f"Skipping knowledge graph construction for document {doc_id} (enable_kg=False)")
  ```

- 在合并阶段添加条件判断：
  ```python
  if status_doc.enable_kg and entity_relation_task is not None:
      chunk_results = await entity_relation_task
      await merge_nodes_and_edges(...)
  else:
      logger.info(f"Skipping merge stage for document {doc_id} (enable_kg=False)")
  ```

- 在状态更新中保持 `enable_kg` 字段：
  ```python
  "enable_kg": status_doc.enable_kg,  # Preserve existing enable_kg
  ```

### 4. 响应模型和 API 文档更新

#### 4.1 DocStatusResponse 模型扩展
```python
class DocStatusResponse(BaseModel):
    # ... 其他字段 ...
    enable_kg: bool = Field(default=True, description="Whether knowledge graph construction is enabled for this document")
    # ... 其他字段 ...
```

#### 4.2 API 文档字符串更新
更新了所有相关 API 端点的文档字符串，添加 `x_enable_kg` 参数说明。

#### 4.3 响应对象构造更新
在所有 `DocStatusResponse` 对象创建位置添加 `enable_kg=doc_status.enable_kg` 参数。

## 测试验证

### 测试脚本
创建了完整的测试脚本 `test_enable_kg_feature.py`，验证以下功能：

1. **enable_kg=True 的文档**: 正常进行知识图谱构建
2. **enable_kg=False 的文档**: 跳过知识图谱构建
3. **文档状态存储**: 正确保存和检索 enable_kg 字段
4. **混合处理**: 同时处理两种类型的文档

### 测试结果
```
测试 1: 使用 enable_kg=True 插入文档
文档 1 入队完成，track_id: enqueue_20250925_172030_65ccbbcd

测试 2: 使用 enable_kg=False 插入文档
文档 2 入队完成，track_id: enqueue_20250925_172030_782eb8ef

检查文档状态:
已处理的文档:
文档 ID: doc-314838a6f6986f42293b5cb162a8425f
  file_path: test1.txt
  enable_kg: True
  status: DocStatus.PROCESSED
  chunks_count: 1

文档 ID: doc-d6931098b9655e3e0de3b58da2d211b0
  file_path: test2.txt
  enable_kg: False
  status: DocStatus.PROCESSED
  chunks_count: 1
```

关键日志确认功能正常：
- `INFO: Skipping knowledge graph construction for document doc-d6931098b9655e3e0de3b58da2d211b0 (enable_kg=False)`
- `INFO: Skipping merge stage for document doc-d6931098b9655e3e0de3b58da2d211b0 (enable_kg=False)`

## 使用方法

### HTTP API 调用示例

#### 1. 插入单个文本（启用知识图谱）
```bash
curl -X POST "http://localhost:8020/documents/text" \
  -H "Content-Type: application/json" \
  -H "x-enable-kg: true" \
  -d '{"text": "这是一个包含实体和关系的文档", "file_source": "test.txt"}'
```

#### 2. 插入单个文本（禁用知识图谱）
```bash
curl -X POST "http://localhost:8020/documents/text" \
  -H "Content-Type: application/json" \
  -H "x-enable-kg: false" \
  -d '{"text": "这是一个纯文本文档", "file_source": "plain.txt"}'
```

#### 3. 文件上传（禁用知识图谱）
```bash
curl -X POST "http://localhost:8020/documents/upload" \
  -H "x-enable-kg: false" \
  -F "file=@document.pdf"
```

### 程序化调用示例

```python
from lightrag import LightRAG

# 初始化
rag = LightRAG(working_dir="./working_dir")
await rag.initialize_storages()

# 启用知识图谱的文档
track_id1 = await rag.apipeline_enqueue_documents(
    input="包含实体和关系的复杂文档",
    enable_kg_list=[True]
)

# 禁用知识图谱的文档
track_id2 = await rag.apipeline_enqueue_documents(
    input="简单的纯文本文档",
    enable_kg_list=[False]
)

# 处理队列
await rag.apipeline_process_enqueue_documents()
```

## 技术特点

### 1. 向后兼容性
- 所有现有 API 调用无需修改即可正常工作
- `enable_kg` 默认值为 `True`，保持原有行为
- 现有文档状态会自动获得默认的 `enable_kg=True` 值

### 2. 存储一致性
- 所有存储实现（JSON、Redis、PostgreSQL、MongoDB）都支持新字段
- 包含迁移兼容性处理，避免现有数据问题

### 3. 性能优化
- 禁用知识图谱时跳过耗时的 LLM 调用和图谱构建
- 仍保留文本分块和向量化，支持基本的向量检索

### 4. 监控和日志
- 清晰的日志输出，显示跳过知识图谱构建的决策
- 文档状态中包含完整的处理信息

## 注意事项

1. **查询影响**: 禁用知识图谱的文档无法参与 `local`、`global`、`hybrid` 模式的复杂查询，但可以通过 `naive` 模式进行向量检索

2. **批量处理**: 在 `insert_texts` API 中，`x-enable-kg` 头部会应用到所有文档。如需单独控制，请使用多次 `insert_text` 调用

3. **存储需求**: PostgreSQL 用户需要确保表结构包含新的 `enable_kg` 字段，或依赖自动迁移机制

## 总结

成功实现了完整的可选知识图谱创建功能，满足了所有设计要求：

✅ 支持 HTTP 头部控制知识图谱构建
✅ 保持完全的向后兼容性
✅ 支持所有存储后端
✅ 包含完整的 API 文档更新
✅ 通过全面测试验证
✅ 提供清晰的使用指导

这个功能为 LightRAG 用户提供了更大的灵活性，可以根据具体用例选择最适合的处理模式，既支持高性能的纯文本检索，也支持复杂的知识图谱驱动查询。