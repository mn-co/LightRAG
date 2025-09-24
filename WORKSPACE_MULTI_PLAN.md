# LightRAG Workspace Header 支持改造计划

## 背景
现有 API 服务器仅支持在启动参数中指定单一 `workspace`，不利于在同一个服务实例下操作多个知识库。目标是允许调用方通过 HTTP 头部携带 `X-Workspace`（暂定命名）指定目标 workspace，默认回退到初始化时的 workspace；同时在 API 文档与 Web UI 中提供字段/输入框，让用户显式选择或输入 workspace。

## 目标
- 服务器可基于请求头切换到不同的 `LightRAG` 实例，并复用配置/存储隔离机制。
- API 文档（FastAPI Docs/README）明确说明新的 header 参数及默认行为。
- Web UI 提供 workspace 输入框，调用接口时自动携带对应 header。
- 保持向后兼容：未提供 header 时继续使用服务器启动时默认 workspace。

## 关键改动模块
1. `lightrag/api/lightrag_server.py`
   - 引入 `WorkspaceManager`，按需创建/缓存 `LightRAG` 实例。
   - 在 `create_app` 中初始化默认 workspace，并将管理器挂载到 `app.state`。
2. `lightrag/api/routers/*.py`
   - 添加依赖函数 `get_rag_instance(request)`，从 header 解析 workspace；未经提供则使用默认。
   - 路由函数使用依赖返回的实例替代原有单例。
   - 对文档上传、查询、图谱、缓存等接口统一处理 workspace 参数。
3. `lightrag/api/utils_api.py` 与 `handlers`
   - 在服务配置输出中展示当前默认 workspace 及 header 用法。
4. `lightrag/api/config.py`
   - 保留 CLI `--workspace` 作为默认值，供未传 header 时回退。
5. `lightrag_webui`
   - 新增全局 workspace 输入框（导航栏或设置面板）。
   - 前端请求统一在 header 中附加 workspace 名称。
   - 在状态/查询页面显示当前 workspace。
6. 文档更新
   - `README-zh.md`、`README.md`、`docs/Algorithm.md` 或相关文档新增 workspace 操作说明。
   - API 文档注释中补充 header 描述。

## 实施步骤
1. **内部管理器设计**
   - 编写 `WorkspaceManager`（线程/协程安全），提供 `get_or_create(workspace)`、`list_workspaces()`、`shutdown_all()` 等方法。
   - 实例化时传入默认 `LightRAG` 设置；创建新实例时调用 `ainitialize_storages()`。

2. **请求注入**
   - 在每个路由文件新增 `Depends(get_rag_instance)`。
   - `get_rag_instance` 接受 `Request`，解析 `X-Workspace`，调用 `WorkspaceManager`。
   - 确保后台任务（如异步索引）保留 workspace 信息。

3. **文档 & FastAPI OpenAPI 描述**
   - 使用 `Header` 依赖将 workspace header 反映到 Swagger。
   - 更新说明文档，示例请求中加入 header。

4. **Web UI 改造**
   - 在全局状态管理中加入 `workspace`。
   - 所有 API 调用统一读取该状态，并在请求头中发送。
   - 可选：记住最近使用的 workspace。

5. **落地细节处理**
   - 在 `DocumentManager` 内部允许传入 workspace，构造对应目录。
   - 调整 Drop/Delete 功能时记录当前 workspace。
   - 更新日志打印格式，方便排查。

6. **测试验证**
   - 编写/更新测试用例校验不同 workspace 间数据隔离（尤其 API 测试）。
   - 手动测试 Web UI 切换 workspace 的上传/查询效果。

## 注意事项与风险
- 多 workspace 并发时，要确保共享锁 `shared_storage` 的前缀正确，避免名称碰撞。
- `WorkspaceManager` 需要防止实例泄漏；可考虑限制可创建的 workspace 数量或提供清理接口。
- 若部署为多进程，需要评估各进程的 workspace 缓存是否一致；必要时通过外部存储同步。
- Web UI 需对 workspace 输入做合法性校验，防止目录穿越（仅允许字母数字和下划线等安全字符）。

## 验收标准
- 通过 header 切换 workspace 后，索引/查询/删除操作只影响指定 workspace 的数据。
- Web UI 支持输入/切换 workspace，并实时生效。
- Swagger 文档展示新的 header 参数，并包含示例。
- 原有单 workspace 流程保持可用，未传 workspace 时行为不变。

