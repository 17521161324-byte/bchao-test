# AGENTS.md

## 项目概述

B超语音测试平台 — 内部工具，用于对比不同 ASR/LLM 模型在真实 B 超录音上的识别准确率。非生产产品。

## 技术栈

- **后端**: Python 3.11+ / FastAPI / SQLAlchemy (async) / SQLite (aiosqlite) / Pydantic v2
- **前端**: Vue 3 / TypeScript / Vite 5 / ant-design-vue 4 / Pinia / vue-router
- **部署**: Windows + PM2 + Nginx（无 Docker）

## 目录结构

```
backend/
  app/
    main.py          # FastAPI 入口，lifespan 启动 DB + ExperimentWorker
    config.py         # pydantic-settings，从 .env 加载
    database.py       # 异步 SQLAlchemy 引擎，init_db() 含手动 ALTER TABLE 迁移
    models/           # SQLAlchemy 模型（DateFolder, PatientRecord, AudioSeg, BUltraResult, ModelConfig, TestRun, PromptTemplate, Experiment*）
    schemas/          # Pydantic 请求/响应模型
    routers/          # API 路由，prefix 均为 /api/*
    services/
      asr/            # ASR 抽象层 + 多 provider 实现（local, qwen, mimo, iflytek, volcengine 等）
      llm/            # LLM 抽象层 + 多 provider 实现（OpenAI 兼容协议为主）
      parser.py       # 卵泡字段解析 + LLM 提示词模板 + evaluate_result()
      test_executor.py
      experiment_*.py
    workers/          # 后台实验任务 Worker
  tests/              # pytest + pytest-asyncio，内存 SQLite
  mock_funasr.py      # 开发用模拟 ASR 服务（端口 50000）
  .env.example        # 环境变量模板
  requirements.txt
  requirements-dev.txt
frontend/
  src/
    api/client.ts     # axios 封装，所有 API 调用在此
    pages/            # 页面组件（DataImport, AsrCompare, AsrOptimize, ModelConfig, Experiments）
    router/index.ts   # 路由配置
    stores/           # Pinia 状态管理
    types/            # TypeScript 类型
  vite.config.ts      # dev 端口 5190，proxy /api → localhost:8000
  package.json
```

## 开发命令

```bash
# 后端
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install
npm run dev          # Vite dev server, 端口 5190

# 测试（从 backend/ 目录运行）
cd backend
pip install -r requirements-dev.txt
pytest               # 内存 SQLite，无需真实数据库
pytest tests/test_parser.py -v   # 单文件
pytest -k "test_name"            # 单个测试

# Mock ASR（开发用，无需真实 ASR 服务）
cd backend
python mock_funasr.py            # 端口 50000
```

## 关键架构细节

### 数据库迁移

无正式迁移工具。`database.py:init_db()` 在启动时通过 `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` 做增量字段添加。新增字段需在此函数中添加 `_ensure_column()` 调用。

### ASR/LLM Provider 扩展

通过 `create_asr(provider, **kwargs)` 和 `create_llm(provider, **kwargs)` 工厂函数注册。新增 provider 需：
1. 在 `services/asr/` 或 `services/llm/` 实现类
2. 在对应 `__init__.py` 的 `match/case` 中添加分支

### 提示词模板

`parser.py` 中的 `DEFAULT_PROMPT_TEMPLATE` 使用 `{transcript}` 占位符。**必须用 `str.replace()` 替换，不能用 `.format()`**，因为模板包含 JSON 示例的花括号会被误解析。

### 热词优先级

接口传入 > 模型配置 `params.hotwords` > `config.py` 中的 `DEFAULT_ASR_HOTWORDS`

### SSE 流式

ASR 转写和测试执行通过 SSE 推送进度。前端用 `EventSource` 接收。Nginx 需关闭 proxy buffering（已配置）。

### 前端自动导入

`unplugin-auto-import` + `unplugin-vue-components` 已配置，Vue API 和 ant-design-vue 组件无需手动 import。图标在 `main.ts` 中全局注册。

## API 端口

- 后端: 8000（uvicorn）
- 前端 dev: 5190（vite）
- Nginx 生产: 80
- Nginx 代理后端: 8001（见 `nginx.conf`，注意与 uvicorn 默认 8000 不同）

## 生产初始化

```bash
cd backend
python -m app.init_db
curl -X POST http://localhost:8000/api/model/init-defaults
curl -X POST http://localhost:8000/api/prompt-templates/init-defaults
```

## CI/CD

`.github/workflows/deploy.yml` — push 到 main 触发 SSH 部署到 Windows 服务器：git pull → pip install → pm2 restart → npm run build → nginx reload。

## 注意事项

- Windows 路径：生产环境 `nginx.conf` 和 `.env` 中使用 `E:/bchao-test/` 硬编码路径，本地开发需调整
- SQLite URL 转换：`database.py` 自动将 `sqlite:///` 转为 `sqlite+aiosqlite:///` 并解析相对路径到 backend 目录
- 无认证：API 无鉴权，内部工具
- 中文：项目文档和注释均为中文，代码标识符用英文
