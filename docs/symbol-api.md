# 符号包管理 API 接口文档

**Base URL:** `/api/symbols`

---

## 1. 上传符号包

上传一个 `.zip` 格式的符号包（包含 `.pdb` 等调试符号文件）。如果相同 `game_name + build_version + platform` 的符号包已存在，会自动覆盖旧版本。

上传成功并进入 `ready` 状态后，系统会按游戏名称自动清理历史符号包：同一个 `game_name` 下保留最近 5 个符号包，同时保留最近 2 天内上传的符号包；更早且不在最近 5 个内的符号包会自动删除磁盘目录和数据库记录，正在分析任务中使用的符号包会跳过清理。

### 请求

```
POST /api/symbols/upload
Content-Type: multipart/form-data
```

### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `file` | File | 是 | - | `.zip` 格式的符号包文件 |
| `game_name` | string | 是 | - | 游戏名称（不可包含 `/`、`\`、`..`） |
| `build_version` | string | 是 | - | 构建版本号（不可包含 `/`、`\`、`..`） |
| `platform` | string | 否 | `"Windows"` | 目标平台，可选值：`Windows`、`Linux`、`Mac` |
| `svn_revision` | string | 否 | `null` | SVN 修订号 |
| `description` | string | 否 | `null` | 符号包描述信息 |

### 成功响应

**状态码:** `200 OK`

```json
{
  "id": "sym_a1b2c3d4e5f6",
  "game_name": "QingCheng",
  "build_version": "1.0.23",
  "svn_revision": "12345",
  "platform": "Windows",
  "file_size": 104857600,
  "status": "ready",
  "upload_time": "2026-05-26T08:30:00.000000",
  "description": "正式版符号包",
  "linked_crash_count": 0
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 符号包唯一 ID，格式 `sym_` + 12 位十六进制 |
| `game_name` | string | 游戏名称 |
| `build_version` | string | 构建版本号 |
| `svn_revision` | string \| null | SVN 修订号 |
| `platform` | string | 目标平台 |
| `file_size` | int \| null | 解压后文件总大小（字节） |
| `status` | string | 状态：`uploading`（上传中）、`ready`（就绪）、`failed`（失败） |
| `upload_time` | string | 上传时间（ISO 8601 UTC） |
| `description` | string \| null | 描述信息 |
| `linked_crash_count` | int | 关联的崩溃报告数量 |

### 错误响应

| 状态码 | 场景 | 响应示例 |
|--------|------|----------|
| `400` | 文件不是 `.zip` 格式 | `{"detail": "请上传 .zip 文件"}` |
| `400` | 名称包含路径分隔符 | `{"detail": "名称中不能包含路径分隔符"}` |
| `500` | 解压或处理失败 | `{"detail": "处理符号包失败: ..."}` |

### cURL 示例

```bash
curl -X POST http://localhost:8000/api/symbols/upload \
  -F "file=@symbols.zip" \
  -F "game_name=QingCheng" \
  -F "build_version=1.0.23" \
  -F "platform=Windows" \
  -F "svn_revision=12345" \
  -F "description=正式版符号包"
```

### Python 示例

```python
import requests

url = "http://localhost:8000/api/symbols/upload"
files = {"file": ("symbols.zip", open("symbols.zip", "rb"), "application/zip")}
data = {
    "game_name": "QingCheng",
    "build_version": "1.0.23",
    "platform": "Windows",
    "svn_revision": "12345",
    "description": "正式版符号包",
}

response = requests.post(url, files=files, data=data)
print(response.json())
```

### JavaScript 示例

```javascript
const formData = new FormData();
formData.append("file", fileInput.files[0]);
formData.append("game_name", "QingCheng");
formData.append("build_version", "1.0.23");
formData.append("platform", "Windows");
formData.append("svn_revision", "12345");
formData.append("description", "正式版符号包");

const response = await fetch("/api/symbols/upload", {
  method: "POST",
  body: formData,
});
const result = await response.json();
```

---

## 2. 查询符号包列表

获取所有符号包，支持按游戏名称、平台过滤，以及按版本号/SVN 号搜索。

### 请求

```
GET /api/symbols
```

### 查询参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `game_name` | string | 否 | 按游戏名称精确过滤 |
| `platform` | string | 否 | 按平台精确过滤 |
| `search` | string | 否 | 模糊搜索 `build_version` 或 `svn_revision` |

### 成功响应

**状态码:** `200 OK`

```json
{
  "total": 2,
  "items": [
    {
      "id": "sym_a1b2c3d4e5f6",
      "game_name": "QingCheng",
      "build_version": "1.0.23",
      "svn_revision": "12345",
      "platform": "Windows",
      "file_size": 104857600,
      "status": "ready",
      "upload_time": "2026-05-26T08:30:00.000000",
      "description": "正式版符号包",
      "linked_crash_count": 3
    },
    {
      "id": "sym_f6e5d4c3b2a1",
      "game_name": "QingCheng",
      "build_version": "1.0.22",
      "svn_revision": "12300",
      "platform": "Windows",
      "file_size": 98000000,
      "status": "ready",
      "upload_time": "2026-05-25T10:00:00.000000",
      "description": null,
      "linked_crash_count": 5
    }
  ]
}
```

### cURL 示例

```bash
# 查询全部
curl http://localhost:8000/api/symbols

# 按游戏名称过滤
curl "http://localhost:8000/api/symbols?game_name=QingCheng"

# 按平台过滤 + 搜索
curl "http://localhost:8000/api/symbols?platform=Windows&search=1.0"
```

---

## 3. 查询符号包详情

获取单个符号包的详细信息，包括文件列表。

### 请求

```
GET /api/symbols/{symbol_id}
```

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `symbol_id` | string | 是 | 符号包 ID |

### 成功响应

**状态码:** `200 OK`

```json
{
  "id": "sym_a1b2c3d4e5f6",
  "game_name": "QingCheng",
  "build_version": "1.0.23",
  "svn_revision": "12345",
  "platform": "Windows",
  "file_size": 104857600,
  "status": "ready",
  "upload_time": "2026-05-26T08:30:00.000000",
  "description": "正式版符号包",
  "linked_crash_count": 3,
  "store_path": "h:\\CrashDog\\backend\\symbols\\QingCheng\\1.0.23",
  "file_list": [
    {"name": "QingCheng.pdb", "size": 52428800},
    {"name": "QingChengEditor.pdb", "size": 52428800}
  ]
}
```

### 错误响应

| 状态码 | 场景 | 响应示例 |
|--------|------|----------|
| `404` | 符号包不存在 | `{"detail": "符号包不存在"}` |

---

## 4. 删除符号包

删除指定的符号包，同时清除磁盘上的文件。如果有崩溃报告正在使用该符号包进行分析，则拒绝删除。

### 请求

```
DELETE /api/symbols/{symbol_id}
```

### 路径参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `symbol_id` | string | 是 | 符号包 ID |

### 成功响应

**状态码:** `200 OK`

```json
{
  "detail": "符号包已删除"
}
```

### 错误响应

| 状态码 | 场景 | 响应示例 |
|--------|------|----------|
| `404` | 符号包不存在 | `{"detail": "符号包不存在"}` |
| `409` | 正在被使用 | `{"detail": "该符号包正在被使用，无法删除"}` |

---

## 数据模型

### SymbolPackageSummary

列表和上传接口的返回模型。

```json
{
  "id": "string",
  "game_name": "string",
  "build_version": "string",
  "svn_revision": "string | null",
  "platform": "string",
  "file_size": "int | null",
  "status": "string",
  "upload_time": "datetime",
  "description": "string | null",
  "linked_crash_count": "int"
}
```

### SymbolPackageDetail

详情接口的返回模型，在 `SymbolPackageSummary` 基础上增加：

| 字段 | 类型 | 说明 |
|------|------|------|
| `store_path` | string | 服务端存储路径 |
| `file_list` | SymbolFileEntry[] \| null | 文件列表 |

### SymbolFileEntry

```json
{
  "name": "string",
  "size": "int (bytes)"
}
```

---

## 业务规则

1. **唯一性约束**：`(game_name, build_version, platform)` 三元组唯一，重复上传会自动覆盖旧版本。
2. **状态流转**：`uploading` → `ready`（成功）或 `failed`（失败）。
3. **删除保护**：当关联的崩溃报告处于 `analyzing` 状态时，禁止删除符号包。
4. **安全校验**：
   - 仅接受 `.zip` 文件
   - `game_name` 和 `build_version` 不允许包含路径分隔符（防止路径遍历）
   - ZIP 解压时校验目标路径，防止 Zip Slip 攻击
5. **文件存储**：符号文件解压至 `backend/symbols/{game_name}/{build_version}/` 目录。
