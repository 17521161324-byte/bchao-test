# B 超语音测试平台 - 前端

## 快速启动

```bash
# 1. 安装依赖
npm install

# 2. 启动开发模式（需要后端同时运行）
npm run dev
# http://localhost:5173

# 3. 构建生产包
npm run build
# 产物在 dist/ 目录
```

## 开发代理

vite.config.ts 已配置 `/api` 代理到 `http://localhost:8000`，开发时无需处理跨域。

## 目录结构

```
src/
├── api/            # API 客户端封装
├── components/     # 通用组件（音频播放器、Seg列表、布局）
├── pages/          # 5 个核心页面
│   ├── DataImport/     # 数据管理
│   ├── ModelConfig/    # 模型配置
│   ├── SingleTest/     # 单条测试
│   ├── Evaluation/     # 结果评估
│   └── TestHistory/    # 测试历史
├── store/          # Zustand 状态管理
├── types/          # TypeScript 类型定义
├── App.tsx         # 路由配置
└── main.tsx        # 入口
```
