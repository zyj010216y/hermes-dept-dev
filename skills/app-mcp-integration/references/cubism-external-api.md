# Cubism 5.4 alpha 外部 API 知识库（实测 + 官方手册 + jar 反编译交叉验证）

## 连接与鉴权
- WebSocket: ws://localhost:22033（端口可在 Editor 外部应用集成设置改）
- 协议: {"Version":"1.1.0","RequestId":hex,"Type":"Request|Response|Error|Event","Method":...,"Data":{...}}
- 首消息 RegisterPlugin {"Token":..., "Name":...}；token 复用（~/.cubism-mcp/token.txt），已授权则原样返回
- **启动坑**：开关是持久化的（~/.config 下 .ser 文件，RemoteConnect.ser=Boolean true, ServerPort.ser=Integer 22033），
  重启后端口未开只是 Java 应用启动慢——等 60 秒，不是开关被重置
- 授权分级：GetIsApproval（读 Allow）/ GetIsEditApproval（写 Edit），两个都要

## 方法全集（服务器实际 58 个；官方文档 57 - SetParameterValue 单数 + jar 发现 2）

### 基础 API（21 官方 + 2 jar 发现）
RegisterPlugin, GetAPIVersion(jar), GetIsApproval, GetCurrentModelUID,
GetCurrentDocumentUID, GetDocuments, GetDocument, GetCurrentEditMode,
GetParameters, GetParameterGroups, GetParameterValues, SetParameterValues,
ClearParameterValues, GetPhysicsInfo, SetPhysicsInfo(jar), SetGlobalVersion,
SendCubismLog, NotifyChangeEditMode/NotifyMocFileExported/NotifyMotionFileExported/
NotifyMotionSyncFileExported/NotifyPhysicsFileExported（事件）
- SetParameterValue（单数）文档有但 5.4 alpha 服务器 MethodNotFound（4.2 遗留）
- SetParameterValues 写入是临时缓冲，0.5s 自动丢弃，不落盘

### 编辑 API（官方 5.4 alpha1 手册 36 个）
公共: GetIsEditApproval, EditBegin{Silent}, EditEnd{Cancel}, EditSendLog{Message},
      EditSendProgress{Value}, NotifyUndoCancel(事件)
键: AddParameterKey, DeleteParameterKey{Strict,KeyValue}, MoveParameterKey{FromValue,ToValue,ForceOverwrite},
    GetParameterKeys, GetObjectsByParameterKeys, GetParameterStructure
参数: Add/Edit/Delete/Move Parameter + ParameterGroup
选择: GetSelectedObjects, AddSelectedObjects, ClearSelectedObjects（必须在 EditBegin 内）
结构: GetPartStructure, GetObject, GetDeformerStructure
对象: DeleteObject, MoveObjectOnPartsPalette, AddPart, EditPart, EditArtMesh,
      EditGlue, AddRotationDeformer, AddWarpDeformer, EditRotationDeformer, EditWarpDeformer

## 实测行为要点（踩坑记录）
1. **EditRotationDeformer/WarpDeformer "No keyform found"**：默认精确匹配要求**完整参数签名**——
   DefHead 的 keyform 由 ParamAngleX+Y+Z 三参数同键值共同定义，只传 AngleX 会报错。
   解法：传全相关参数同键值，或 is_exact_match=False 模糊匹配单参数。
   写之前先 GetParameterKeys 看对象的键绑定。
2. **GetCurrentDocumentUID**：无文档打开时挂起不响应 → 必须设超时（8s）
3. **GetObjectsByParameterKeys**：请求只有 ModelUID/ParameterId/KeyValue，Ids 是**响应字段**（传 Ids 报 Unknown field）
4. **EditWarpDeformer 无顶点坐标**：协议层只支持 Opacity/颜色/标签/WarpDivH/V/BezierDivH/V（分割数 2~100/1~100）；
   GetObject 返回 Rectangle 四角；网格顶点编辑只能 GUI——官方 5.4 alpha1 硬限制
5. **GetObject 响应双层嵌套**：Data.Data，MCP 层要展开
6. 编辑事务：EditBegin→操作→EditEnd；操作失败用 EditEnd{Cancel:true} 回滚
7. AddSelectedObjects/ClearSelectedObjects/EditSendLog/EditSendProgress 都要求 EditBegin 事务内
8. 事件（Notify*）是服务器主动推送的 Event 消息，客户端需缓存供轮询（MCP 无推送通道）

## 官方资源
- 5.4 alpha 下载/手册帖: https://creatorsforum.live2d.com/t/topic/3938
- 编辑 API 手册（4 语言）: https://cubism.live2d.com/link/manual5_4_alpha_external-api-intergration_en
- 官方样例: https://github.com/Live2D-Garage/CubismExternalAppPluginSamples/tree/54alpha/04_EditSample/
- 基础 API 清单: https://docs.live2d.com/en/cubism-editor-manual/external-application-integration-api-list/
- 现有 MCP: nana7chi/CubismExternalEditMCP（缺 11 个接口：物理/版本/日志/选择/事件）
- 本项目: ~/Desktop/codex项目列表/cubism-mcp-full（55 工具全覆盖，已注册 codex）
