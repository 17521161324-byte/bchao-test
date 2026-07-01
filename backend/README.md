# B 超语音测试平台 — 后端

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制并修改）
cp .env.example .env

# 3. 启动（开发模式）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. 查看 API 文档
# http://localhost:8000/docs
```

## 生产部署（Windows + PM2）

```bash
pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8000" --name bchao-backend
pm2 save
pm2 startup
```
