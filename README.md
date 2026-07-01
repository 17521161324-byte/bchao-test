# B 超语音测试平台

辅助生殖 B 超语音识别测试平台 —— 对比不同 ASR / LLM 模型、收音设备、提示词在真实业务场景下的识别效果。

## 功能特性

- 📁 **数据管理**：录音文件树形浏览 + B 超结果 xlsx 导入
- 🤖 **模型配置**：支持本地 / 在线 ASR 和 LLM 模型，可配置、可测试连通性
- ▶️ **单条测试**：选病历号 → 选模型组合 → SSE 实时进度 → 结构化输出
- 📊 **结果评估**：自动对比 ground truth + 人工修正 + 字段级准确率
- 📝 **测试历史**：历史记录回溯、重测

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + TypeScript + Ant Design 5 + Vite |
| 后端 | Python 3.11+ + FastAPI + SQLAlchemy |
| 数据库 | SQLite（MVP）|
| 部署 | Nginx + PM2 |

## 快速开始

### 前置要求

- Python 3.9+
- Node.js 18+
- PM2（`npm install -g pm2`）

### 1. 启动后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# 修改 .env 中的配置

# 开发模式
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式（PM2）
pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8000" --name bchao-backend
pm2 save
pm2 startup
```

### 2. 启动前端

```bash
cd frontend
npm install

# 开发模式
npm run dev    # http://localhost:5173

# 构建生产包
npm run build  # 产物在 dist/
```

### 3. 配置 Nginx

将 `nginx.conf` 复制到 Nginx 配置目录，修改路径后重启。

```nginx
# 关键配置
server {
    listen 80;
    server_name _;

    # 前端静态文件
    root /path/to/frontend/dist;

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;
    }

    # 录音文件（支持 range 请求）
    location /recordings/ {
        alias /path/to/backend/data/recordings/;
        add_header Accept-Ranges bytes;
    }
}
```

## API 文档

启动后端后访问：`http://localhost:8000/docs`

## 项目结构

```
bchao-test/
├── backend/          # FastAPI 后端
├── frontend/         # React 前端
├── nginx.conf        # Nginx 配置
├── docs/             # 产品文档
└── README.md
```

## 许可证

MIT
