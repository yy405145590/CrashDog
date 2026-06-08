# 符号文件上传与管理功能 — 需求文档

## 1. 背景与动机

### 现状

CrashDog 当前的符号文件（PDB）硬编码存放在项目 `/bin/` 目录下，`config.py` 中 `PDB_SEARCH_PATH` 指向该固定路径。存在以下问题：

- **仅支持单版本**：`/bin/` 下只能存放一组 PDB + EXE，无法同时支持多个游戏版本的崩溃分析
- **无版本关联**：崩溃报告中包含 `build_version` 和 `svn_revision`，但符号解析时无法自动匹配对应版本的符号文件
- **手动部署**：更新符号文件需要手动拷贝到服务器 `/bin/` 目录，无法通过 Web 界面操作
- **无生命周期管理**：旧版本符号文件无法清理，也无法查看当前有哪些版本的符号可用

### 目标

提供符号文件的 Web 端上传、版本化管理、自动匹配能力，使崩溃分析能自动关联正确版本的符号文件进行解析。

---

## 2. 核心概念

### 符号包 (Symbol Package)

一个符号包代表某个特定构建版本的调试符号集合，包含：

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 唯一标识（自动生成） | `sym_a1b2c3d4` |
| `game_name` | 游戏名称 | `QingCheng` |
| `build_version` | 构建版本号 | `1.2.3` |
| `svn_revision` | SVN 修订号（可选） | `12345` |
| `platform` | 目标平台 | `Windows` |
| `upload_time` | 上传时间 | `2026-05-26 10:00:00` |
| `file_size` | 文件总大小 | `2.8 GB` |
| `status` | 状态 | `ready` / `uploading` / `failed` |
| `description` | 备注说明（可选） | `Release Build` |
| `file_list` | 包含的文件清单 | `QingCheng.pdb, QingCheng.exe` |
| `store_path` | 磁盘存储路径 | `backend/symbols/QingCheng/1.2.3/` |

---

## 3. 功能需求

### 3.1 符号文件上传

**描述**：用户通过 Web 界面上传符号文件包（ZIP 格式），系统自动解压并归档。

**详细规则**：

- 支持 ZIP 格式上传，ZIP 内应包含 `.pdb` 文件，可选包含 `.exe` 文件
- 上传时必填：`game_name`、`build_version`、`platform`
- 上传时选填：`svn_revision`、`description`
- 同一 `game_name + build_version + platform` 组合视为唯一标识，重复上传时：
  - 提示用户已存在，确认后**覆盖**旧版本
- ZIP 解压后按 `backend/symbols/{game_name}/{build_version}/` 路径存储
- 上传过程中状态为 `uploading`，成功后变为 `ready`，失败标记为 `failed`
- 考虑 PDB 文件体积较大（可达数 GB），需支持：
  - 后端接收大文件（调整上传限制）
  - 前端显示上传进度条

### 3.2 符号文件列表与查询

**描述**：在管理界面展示所有已上传的符号包，支持筛选和搜索。

**功能点**：

- 列表展示字段：游戏名称、版本号、SVN 修订号、平台、文件大小、上传时间、状态
- 支持按 `game_name`、`platform` 筛选
- 支持按 `build_version` 或 `svn_revision` 搜索
- 按上传时间倒序排列

### 3.3 符号文件删除

**描述**：支持删除不再需要的符号包，释放磁盘空间。

**功能点**：

- 删除前二次确认
- 删除时同时清理磁盘上的符号文件目录
- 若该符号包正被某个崩溃分析任务使用，提示用户并阻止删除

### 3.4 符号文件详情

**描述**：查看某个符号包的详细信息。

**功能点**：

- 显示所有元数据字段
- 显示 ZIP 包内文件清单（文件名 + 大小）
- 显示关联的崩溃报告数量（即有多少崩溃报告使用了该版本符号进行解析）

### 3.5 崩溃分析自动匹配符号

**描述**：崩溃报告在符号化解析时，自动根据版本信息匹配对应的符号包。

**匹配规则（优先级从高到低）**：

1. **精确匹配**：`game_name` + `build_version` + `platform` 完全一致
2. **SVN 修订号匹配**：`game_name` + `svn_revision` + `platform` 一致
3. **回退到默认路径**：若无匹配，仍使用当前 `/bin/` 目录作为兜底（保持向后兼容）

**改造点**：

- `symbolizer.py` 的 `symbolize()` 方法需改造，在调用 CDB 前先查询数据库确定 PDB 搜索路径
- CDB 的 `-y` 参数改为动态传入匹配到的符号存储路径
- 崩溃报告中新增字段 `symbol_package_id`，记录实际使用的符号包

### 3.6 符号文件自动清理

**描述**：为避免同一游戏长期上传符号包后持续堆积、占用磁盘空间，系统在符号包上传成功后自动清理过期符号文件。

**清理规则**：

- 清理范围按 `game_name` 维度计算，同一个游戏名称下的符号包参与同一组保留策略
- 每个游戏至少保留按上传时间倒序排序后的最近 **5** 个符号包
- 上传时间在最近 **2 天** 内的符号包始终保留，即使数量超过 5 个也不删除
- 不满足“最近 5 个”且上传时间早于 2 天的符号包视为过期，自动删除数据库记录和磁盘目录
- 正在被崩溃分析任务使用的符号包不自动删除，保留并记录跳过原因
- 自动清理只在新符号包处理成功并进入 `ready` 状态后触发，上传失败不会触发清理

---

## 4. API 设计

### 4.1 上传符号包

```
POST /api/symbols/upload
Content-Type: multipart/form-data

参数：
  - file: ZIP 文件（必填）
  - game_name: string（必填）
  - build_version: string（必填）
  - platform: string（必填，默认 "Windows"）
  - svn_revision: string（选填）
  - description: string（选填）

响应 200：
{
  "id": "sym_xxx",
  "game_name": "QingCheng",
  "build_version": "1.2.3",
  "platform": "Windows",
  "status": "ready",
  "file_size": 2800000000,
  "file_count": 2,
  "upload_time": "2026-05-26T10:00:00"
}
```

### 4.2 查询符号包列表

```
GET /api/symbols?game_name=QingCheng&platform=Windows&search=1.2

响应 200：
{
  "total": 5,
  "items": [
    {
      "id": "sym_xxx",
      "game_name": "QingCheng",
      "build_version": "1.2.3",
      "svn_revision": "12345",
      "platform": "Windows",
      "file_size": 2800000000,
      "status": "ready",
      "upload_time": "2026-05-26T10:00:00",
      "description": "Release Build",
      "linked_crash_count": 3
    }
  ]
}
```

### 4.3 获取符号包详情

```
GET /api/symbols/{symbol_id}

响应 200：
{
  "id": "sym_xxx",
  "game_name": "QingCheng",
  "build_version": "1.2.3",
  "svn_revision": "12345",
  "platform": "Windows",
  "file_size": 2800000000,
  "status": "ready",
  "upload_time": "2026-05-26T10:00:00",
  "description": "Release Build",
  "store_path": "backend/symbols/QingCheng/1.2.3/",
  "file_list": [
    {"name": "QingCheng.pdb", "size": 2750000000},
    {"name": "QingCheng.exe", "size": 386000000}
  ],
  "linked_crash_count": 3
}
```

### 4.4 删除符号包

```
DELETE /api/symbols/{symbol_id}

响应 200：
{"message": "符号包已删除"}

响应 409（有关联崩溃正在解析）：
{"detail": "该符号包正在被使用，无法删除"}
```

---

## 5. 数据库设计

### 新增表：`symbol_packages`

```sql
CREATE TABLE symbol_packages (
    id          TEXT PRIMARY KEY,           -- 唯一ID，如 sym_xxxx
    game_name   TEXT NOT NULL,              -- 游戏名称
    build_version TEXT NOT NULL,            -- 构建版本号
    svn_revision TEXT,                      -- SVN 修订号
    platform    TEXT NOT NULL DEFAULT 'Windows', -- 平台
    description TEXT,                       -- 备注
    file_size   INTEGER,                    -- 总文件大小(bytes)
    file_list   TEXT,                       -- 文件清单 JSON
    store_path  TEXT NOT NULL,              -- 磁盘存储路径
    status      TEXT NOT NULL DEFAULT 'uploading', -- uploading/ready/failed
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(game_name, build_version, platform)
);
```

### 修改表：`crash_reports`

```sql
ALTER TABLE crash_reports ADD COLUMN symbol_package_id TEXT REFERENCES symbol_packages(id);
```

---

## 6. 前端页面设计

### 6.1 符号管理页面（新增）

**路由**：`/symbols`

**页面布局**：

```
┌─────────────────────────────────────────────────────┐
│  符号文件管理                          [上传符号包]   │
├─────────────────────────────────────────────────────┤
│  筛选：[游戏名称 ▼]  [平台 ▼]  [搜索版本号...]     │
├─────────────────────────────────────────────────────┤
│  游戏名称  │ 版本号 │ SVN  │ 平台    │ 大小   │ 状态 │ 上传时间   │ 操作  │
│  QingCheng │ 1.2.3  │ 12345│ Windows │ 2.8 GB │ 就绪 │ 2026-05-26 │ 详情 删除│
│  QingCheng │ 1.2.2  │ 12300│ Windows │ 2.7 GB │ 就绪 │ 2026-05-20 │ 详情 删除│
│  ...       │        │      │         │        │      │            │         │
└─────────────────────────────────────────────────────┘
```

### 6.2 上传对话框

```
┌───────────────── 上传符号包 ─────────────────┐
│                                               │
│  游戏名称：  [QingCheng        ▼]             │
│  版本号：    [________________]  *必填        │
│  SVN修订号： [________________]               │
│  平台：      [Windows          ▼]             │
│  备注：      [________________]               │
│                                               │
│  [拖拽或点击上传 ZIP 文件]                      │
│  ████████████████░░░░  78%   2.1GB / 2.8GB    │
│                                               │
│              [取消]    [上传]                   │
└───────────────────────────────────────────────┘
```

### 6.3 崩溃详情页改造

在现有崩溃详情页中增加符号匹配状态展示：

- 显示当前使用的符号包版本
- 若未匹配到符号包，显示警告提示
- 提供「重新符号化」按钮（使用新上传的符号包重新解析）

---

## 7. 存储目录结构

```
backend/
├── symbols/                          # 符号文件根目录（新增）
│   └── {game_name}/
│       └── {build_version}/
│           ├── QingCheng.pdb
│           └── QingCheng.exe
├── uploads/                          # 崩溃包上传临时目录（已有）
├── crashes/                          # 崩溃解压目录（已有）
bin/                                  # 默认兜底符号目录（已有，保持兼容）
```

---

## 8. 改造影响范围

| 模块 | 文件 | 改动内容 |
|------|------|---------|
| 数据库模型 | `backend/models.py` | 新增 `SymbolPackage` 模型，`CrashReport` 新增 `symbol_package_id` 字段 |
| 接口定义 | `backend/schemas.py` | 新增符号包相关的请求/响应 Schema |
| 路由 | `backend/routers/symbol.py` | **新增**：符号包 CRUD 路由 |
| 主入口 | `backend/main.py` | 注册符号路由 |
| 配置 | `backend/config.py` | 新增 `SYMBOL_DIR` 配置 |
| 符号解析 | `backend/services/symbolizer.py` | 改造：动态查询符号路径 |
| 前端路由 | `frontend/src/router/index.js` | 新增 `/symbols` 路由 |
| 前端 API | `frontend/src/api/symbol.js` | **新增**：符号包 API 调用 |
| 前端页面 | `frontend/src/views/SymbolList.vue` | **新增**：符号管理页面 |
| 前端页面 | `frontend/src/views/CrashDetail.vue` | 改造：展示符号匹配信息 |
| 导航 | `frontend/src/App.vue` | 新增符号管理导航入口 |

---

## 9. 非功能需求

### 性能
- 大文件上传支持流式传输，避免内存溢出
- 上传文件大小上限建议设置为 **5 GB**
- 符号包上传成功后执行自动清理，控制同一游戏历史符号文件占用的磁盘空间

### 兼容性
- 保持 `/bin/` 目录作为默认兜底路径，不破坏现有工作流
- 已有崩溃报告的 `symbol_package_id` 为空时，行为与改造前一致

### 安全性
- 上传文件类型校验（仅接受 ZIP）
- ZIP 解压时检查路径遍历攻击（ZipSlip）
- 限制单次上传文件大小

---

## 10. 待讨论项

1. **是否需要支持分片上传？** — PDB 文件可达数 GB，网络不稳定时分片上传体验更好，但实现复杂度增加
2. **是否需要支持直接上传单个 PDB 文件（非 ZIP）？** — 简化单文件场景
3. **符号包是否需要与 Git/SVN 集成自动拉取？** — CI/CD 场景下自动同步符号文件
