# 生产环境部署配置

## 启动方式

### 方式一：Nginx + Uvicorn（推荐）

#### 1. 启动后端（生产模式）
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### 2. 启动 Nginx
```bash
nginx.exe -c E:\bchao-test\nginx.conf
```

访问 http://localhost

### 方式二：纯 Uvicorn（开发/测试）

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers
```

前端构建产物在 `frontend/dist`，需要配合 Nginx 或单独部署。

### 方式三：Docker（可选）

```bash
docker-compose up -d
```

## 端口

- Nginx: 80
- Backend API: 8000（Nginx 代理）

## 注意事项

1. 首次运行请先初始化数据库：
   ```bash
   cd backend
   python -m app.init_db
   ```

2. 初始化默认模型和提示词模板：
   ```bash
   curl -X POST http://localhost:8000/api/model/init-defaults
   curl -X POST http://localhost:8000/api/prompt-templates/init-defaults
   ```

3. 如需外网访问，请修改 `backend/.env` 中的 `DATABASE_URL` 等配置。
