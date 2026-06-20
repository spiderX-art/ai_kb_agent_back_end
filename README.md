# AI KB Agent Back End

企业知识库客服 Agent 系统的后端服务，基于 FastAPI 构建。

## 当前骨架包含

- FastAPI 应用入口
- 统一配置读取
- API v1 路由聚合
- 健康检查接口：`GET /api/v1/health`
- 数据库连接基础设施：SQLAlchemy `engine`、`SessionLocal`、`get_db`
- SQLAlchemy ORM 基类：后续所有数据库模型都继承 `app.db.base.Base`
- 统一 API 响应结构：`{"code": 0, "message": "ok", "data": ...}`
- 统一异常处理：业务异常、404、参数校验错误、未知错误都会返回固定 JSON 结构
- 数据库连接健康检查：`GET /api/v1/health/db`
- CORS 配置，方便前端本地联调
- 登录模块：`POST /api/v1/auth/login`、`POST /api/v1/auth/logout`、`GET /api/v1/auth/profile`
- 知识库管理模块：知识库列表、详情、新建、编辑、删除
- 文档管理模块：文档列表分页/排序/筛选、元数据创建、真实文件上传、下载、解析状态流转、删除
- 智能问答模块：会话列表、会话消息、基于知识库检索的抽取式问答和引用来源
- 启动时自动创建数据库表，并初始化默认用户 `admin / 123456`、`user / 123456`

## 本地启动

需要使用 Python 3.11 或更高版本。macOS 自带的 `python3` 可能是 3.9，
如果你本机有 `python3.11`，优先使用下面的命令。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn app.main:app --reload
```

本地默认使用 SQLite 文件数据库，启动时会读取 `.env` 里的：

```bash
DATABASE_URL="sqlite:///./app.db"
```

这表示数据库文件会生成在后端项目根目录的 `app.db`。后续如果切换到
PostgreSQL 或 MySQL，主要就是改这个连接字符串。

登录模块还会读取：

```bash
SECRET_KEY="dev-secret-change-me"
ACCESS_TOKEN_EXPIRE_MINUTES=1440
DEFAULT_ADMIN_USERNAME="admin"
DEFAULT_ADMIN_PASSWORD="123456"
DEFAULT_ADMIN_ROLE="admin"
DEFAULT_USERNAME="user"
DEFAULT_PASSWORD="123456"
DEFAULT_USER_ROLE="user"
DOCUMENT_STORAGE_DIR="storage/documents"
MAX_DOCUMENT_FILE_SIZE_MB=50
```

生产环境必须替换 `SECRET_KEY` 和默认密码。上传文档默认保存在后端项目根目录的
`storage/documents`，该目录不会提交到 Git。

启动后访问：

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health
- 数据库健康检查：http://127.0.0.1:8000/api/v1/health/db

默认登录账号：

```text
admin / 123456
user / 123456
```

## 统一响应格式

成功响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

失败响应：

```json
{
  "code": 42200,
  "message": "请求参数校验失败",
  "data": {
    "errors": []
  }
}
```

约定：

- `code`：业务状态码，`0` 代表成功。
- `message`：给前端或用户看的简短说明。
- `data`：成功时放业务数据，失败时可以放错误详情。
- HTTP 状态码仍然保留，例如参数错误是 `422`，未登录是 `401`，服务错误是 `500`。

## 目录说明

```text
app/
  main.py             # FastAPI 应用入口
  core/
    config.py         # 环境变量和应用配置
    errors.py         # 业务错误码和 AppError
    exception_handlers.py
                      # 全局异常处理器
  db/
    base.py           # SQLAlchemy ORM 基类
    init_db.py        # 创建表并初始化默认用户
    session.py        # 数据库 engine、SessionLocal、get_db
  models/
    user.py           # 用户 ORM 模型
  schemas/
    auth.py           # 登录、用户信息响应模型
    response.py       # 统一响应模型 ApiResponse
  api/
    deps.py           # 当前登录用户等通用依赖
    v1/
      router.py       # v1 路由统一入口
      auth.py         # 登录、退出、当前用户接口
      health.py       # 服务和数据库健康检查接口
      knowledge_bases.py
                    # 知识库管理接口
```

## 知识库管理接口

普通用户和管理员都可以查看知识库，只有管理员可以新增、编辑和删除。

- `GET /api/v1/knowledge-bases`
- `POST /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases/{knowledge_base_id}`
- `PUT /api/v1/knowledge-bases/{knowledge_base_id}`
- `DELETE /api/v1/knowledge-bases/{knowledge_base_id}`

## 文档管理接口

普通用户和管理员都可以查看与下载文档，只有管理员可以上传、更新状态和删除。

- `GET /api/v1/documents`：支持 `page`、`page_size`、`sort_by`、`sort_order`、`knowledge_base_id`、`status`、`file_type`、`keyword`
- `POST /api/v1/documents`
- `POST /api/v1/documents/upload`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/download`
- `POST /api/v1/documents/{document_id}/parse`
- `PATCH /api/v1/documents/{document_id}/status`
- `DELETE /api/v1/documents/{document_id}`

当前上传接口会保存原始文件和文档元数据。解析接口会抽取 PDF、TXT、MD 正文并写入文本分片，
DOCX 先保留上传、下载和预览下载能力。解析状态按 `uploaded -> parsing -> completed/failed`
流转，失败后可重新发起解析。

## 智能问答接口

普通用户和管理员都可以基于自己创建的会话提问和查看历史。当前回答使用本地检索结果生成，
返回答案时会附带命中的文档分片作为引用来源。

- `POST /api/v1/chat/messages`
- `GET /api/v1/chat/conversations`
- `GET /api/v1/chat/conversations/{conversation_id}/messages`

## 学习提示

FastAPI 请求流向可以先理解成：

```text
浏览器 / 前端请求
  -> app/main.py 创建的 FastAPI 应用
  -> app/api/v1/router.py 找到对应路由
  -> app/api/v1/health.py 执行接口函数
  -> 返回 JSON 响应
```

数据库请求会多一步：

```text
接口函数需要 db: Session
  -> FastAPI 调用 app/db/session.py 的 get_db()
  -> get_db() 创建数据库会话
  -> 接口函数使用 db.execute(...) 或后续的 ORM 查询
  -> 请求结束后 get_db() 自动关闭会话
```
