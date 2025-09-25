## 改造背景

### 原始需求
现有 LightRAG API 服务器仅支持在启动参数中指定单一 `workspace`，不利于在同一个服务实例下操作多个知识库。业务需求要求：

1. 允许调用方通过 HTTP 头部携带 `X-Workspace` 指定目标 workspace
2. 未提供 header 时回退到初始化时的 workspace（保持向后兼容）
3. 在 API 文档中提供字段，让用户显式输入 workspace
4. 保持 WebUI 现有行为不变

### 技术挑战
- **数据隔离**: 不同 workspace 需要完全独立的数据存储
- **实例管理**: 动态创建和缓存 LightRAG 实例
- **并发安全**: 多请求同时访问不同 workspace
- **向后兼容**: 不破坏现有单 workspace 的使用方式

## 改造思路与架构设计

### 核心设计原则

1. **依赖注入模式**: 通过 FastAPI 的依赖注入系统动态获取workspace特定的实例
2. **工作区管理器**: 统一管理多个 LightRAG 实例的生命周期
3. **透明化接入**: 现有API接口保持不变，仅添加可选的workspace参数
4. **资源复用**: 相同配置的多个workspace复用底层资源

### 架构组件

```
┌─────────────────────────────────────────────────────────────┐
│                    HTTP Request                              │
│                 X-Workspace: project_a                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Dependencies.py                              │
│  - get_rag_instance()                                       │
│  - get_rag_only()                                          │
│  - get_doc_manager_only()                                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│               WorkspaceManager                               │
│  - validate_workspace_name()                               │
│  - get_or_create()                                         │
│  - shutdown_workspace()                                    │
│  Cache: {workspace_name -> (LightRAG, DocumentManager)}    │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              LightRAG Instances                             │
│  project_a: LightRAG(workspace="project_a")                │
│  project_b: LightRAG(workspace="project_b")                │
│  default: LightRAG(workspace="default")                    │
└─────────────────────────────────────────────────────────────┘
```

## 详细实施过程

### 第一阶段：核心组件设计与实现

#### 1.1 WorkspaceManager 类设计
**文件**: `lightrag/api/workspace_manager.py`

**核心职责**:
- 线程安全的 LightRAG 实例缓存管理
- 工作区名称验证与安全检查
- 实例生命周期管理（创建、缓存、销毁）

**关键特性**:
```python
class WorkspaceManager:
    def __init__(self, default_workspace: str, rag_config: dict, doc_manager_config: dict)
    async def get_or_create(self, workspace: Optional[str] = None) -> tuple[LightRAG, DocumentManager]
    def validate_workspace_name(workspace: str) -> bool
    async def shutdown_workspace(workspace: str) -> bool
    async def shutdown_all(self) -> None
```

**安全验证规则**:
- 只允许字母数字、下划线、连字符、点号
- 禁止目录遍历模式 (`..`, `/`, `\`)
- 禁用系统保留名称 (`con`, `prn`, `aux` 等)
- 长度限制 (≤255字符)

#### 1.2 依赖注入系统
**文件**: `lightrag/api/dependencies.py`

**设计模式**: FastAPI 依赖注入 + Header 参数解析

```python
async def get_rag_instance(
    request: Request,
    x_workspace: Optional[str] = Header(None, description="Target workspace...")
) -> tuple[LightRAG, DocumentManager]:
    workspace_manager = request.app.state.workspace_manager
    return await workspace_manager.get_or_create(x_workspace)
```

**依赖函数族**:
- `get_rag_instance()`: 返回 (LightRAG, DocumentManager) 元组
- `get_rag_only()`: 仅返回 LightRAG 实例
- `get_doc_manager_only()`: 仅返回 DocumentManager 实例

### 第二阶段：服务器集成

#### 2.1 主服务器改造
**文件**: `lightrag/api/lightrag_server.py`

**关键改动**:
1. **WorkspaceManager 初始化**:
   ```python
   workspace_manager = WorkspaceManager(
       default_workspace=args.workspace,
       rag_config=rag_config,
       doc_manager_config=doc_manager_config
   )
   ```

2. **应用状态集成**:
   ```python
   app.state.workspace_manager = workspace_manager
   ```

3. **生命周期管理**:
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # 启动时初始化默认workspace
       rag, doc_manager = await workspace_manager.get_or_create()
       # ...
       yield
       # 关闭时清理所有workspace
       await workspace_manager.shutdown_all()
   ```

#### 2.2 路由创建函数重构
所有 `create_*_routes` 函数均移除直接的 RAG 实例参数：

```python
# Before:
def create_document_routes(rag: LightRAG, doc_manager: DocumentManager, api_key: str)

# After:
def create_document_routes(api_key: Optional[str] = None)
```

### 第三阶段：路由系统重构

#### 3.1 循环导入问题解决
**问题**: 模块级导入造成循环依赖链
```
dependencies.py -> workspace_manager.py -> document_routes.py -> dependencies.py
```

**解决方案**: 函数级本地导入
```python
def create_document_routes(api_key: Optional[str] = None):
    from lightrag.api.dependencies import get_rag_instance, get_rag_only
    # 路由定义...
```

#### 3.2 路由函数模式标准化
**统一模式**:
```python
async def route_function(
    request_params,
    rag: LightRAG = Depends(get_rag_only)  # 或 rag_doc: tuple = Depends(get_rag_instance)
):
    from lightrag.api.dependencies import get_rag_only  # 本地导入避免循环依赖
    # 函数实现保持不变
```

#### 3.3 各路由模块改造统计

| 路由模块 | 函数数量 | 改造类型 | 主要依赖 |
|---------|----------|----------|----------|
| document_routes.py | 13个函数 | 混合依赖 | get_rag_instance (9个), get_rag_only (4个) |
| query_routes.py | 3个函数 | 单一依赖 | get_rag_only (全部) |
| graph_routes.py | 7个函数 | 单一依赖 | get_rag_only (全部) |
| ollama_api.py | 2个函数 | 特殊处理 | get_rag_only + 类重构 |

### 第四阶段：OllamaAPI 特殊处理

#### 4.1 架构问题
OllamaAPI 采用类封装模式，构造函数需要固定的 RAG 实例：
```python
class OllamaAPI:
    def __init__(self, rag: LightRAG, top_k: int, api_key: str)
```

#### 4.2 重构方案
1. **构造函数解耦**:
   ```python
   def __init__(self, ollama_server_infos, top_k: int, api_key: str)
   ```

2. **路由函数依赖注入**:
   ```python
   async def generate(
       raw_request: Request,
       rag: LightRAG = Depends(get_rag_only)
   ):
   ```

3. **实例引用替换**: 所有 `self.rag` 替换为依赖注入的 `rag` 参数

### 第五阶段：文档与测试

#### 5.1 API 文档集成
FastAPI 自动识别 Header 依赖并生成文档：
```python
x_workspace: Optional[str] = Header(None, description="Target workspace for the operation. Uses server default if not provided.")
```

## 关键问题与解决方案

### 问题1: 空字符串工作区验证失败
**现象**: CLI 默认工作区为空字符串，但验证函数拒绝空字符串
**影响**: 服务器启动失败，所有未携带 X-Workspace 的请求返回 400
**根本原因**: `config.py` 中默认值为 `""` 但 `validate_workspace_name` 要求非空
**解决方案**:
```python
# 在 get_or_create 方法中添加
if not workspace or workspace.strip() == "":
    workspace = "default"
```

### 问题2: RLock + await 死锁
**现象**: 并发请求创建同一工作区时发生死锁
**根本原因**: `threading.RLock` 与 `asyncio.gather` 的事件循环冲突
**技术分析**:
- RLock 是同步锁，持有期间执行 await 会阻塞事件循环
- 第二个协程等待锁释放，但第一个协程需要事件循环完成 await
- 形成典型的死锁条件

**解决方案**: 双锁策略
```python
self._async_lock = asyncio.Lock()    # 异步操作专用
self._sync_lock = RLock()            # 快速同步操作专用

# 异步方法使用
async with self._async_lock:
    await some_async_operation()

# 同步方法使用
with self._sync_lock:
    return simple_value
```

### 问题3: 浅拷贝导致配置污染
**现象**: 不同工作区的 `llm_model_kwargs` 相互影响
**根本原因**: `dict.copy()` 只进行浅拷贝，嵌套的可变对象仍被共享
**影响范围**:
- `llm_model_kwargs` 字典
- `addon_params` 字典
- 其他嵌套的可变配置对象

**解决方案**: 深拷贝
```python
rag_config = copy.deepcopy(self.rag_config)
doc_manager_config = copy.deepcopy(self.doc_manager_config)
```

## 技术要点与最佳实践

### 并发安全设计
1. **锁策略**: 区分同步/异步操作使用不同锁类型
2. **资源管理**: 确保异常情况下资源正确释放
3. **缓存一致性**: 多线程环境下的实例缓存安全

### 内存管理优化
1. **实例复用**: 相同配置的工作区共享底层资源
2. **延迟初始化**: 按需创建工作区实例
3. **生命周期管理**: 及时清理不再使用的实例

### API 设计原则
1. **向后兼容**: 新功能不影响现有使用方式
2. **渐进增强**: Header 参数为可选，有合理默认值
3. **清晰文档**: 参数含义和使用示例明确

### 错误处理策略
1. **输入验证**: 严格的工作区名称安全检查
2. **异常传播**: 合理的 HTTP 状态码映射
3. **日志记录**: 关键操作的详细日志

## 性能影响分析

### 内存开销
- **每个活跃工作区**: ~50MB 基础内存 + 数据存储
- **缓存策略**: LRU 淘汰机制避免内存泄漏
- **配置复制**: 深拷贝带来额外内存开销，但确保隔离性

### CPU 开销
- **实例创建**: 首次访问时初始化成本较高
- **锁竞争**: 双锁策略最小化锁竞争影响
- **依赖注入**: FastAPI 依赖解析带来的微小开销

### 存储隔离
- **命名空间**: 基于工作区名称的存储前缀
- **并行访问**: 不同工作区可并行读写
- **一致性**: 工作区级别的数据一致性保证

## 测试验证方案

### 单元测试覆盖
- [x] 工作区名称验证逻辑
- [x] 实例创建和缓存机制
- [x] 并发安全性测试
- [x] 配置隔离验证
- [x] 异常处理路径

### 集成测试验证
- [x] HTTP 头部解析
- [x] API 端点工作区切换
- [x] 服务器启动与关闭
- [x] 多工作区数据隔离

### 压力测试场景
- 并发创建相同工作区
- 高频率工作区切换
- 大量工作区同时活跃
- 内存压力下的稳定性