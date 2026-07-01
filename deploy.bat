@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   B 超语音测试平台 - 一键部署脚本
echo ========================================
echo.

set BASE_DIR=C:\bchao-test
set BACKEND_DIR=%BASE_DIR%\backend
set FRONTEND_DIR=%BASE_DIR%\frontend

REM ===== 1. 检查前置软件 =====
echo [1/6] 检查前置软件...

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+ 并勾选 "Add to PATH"
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo   - Python 已安装

node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js 18+
    echo 下载地址: https://nodejs.org/
    pause
    exit /b 1
)
echo   - Node.js 已安装

pm2 --version >nul 2>&1
if errorlevel 1 (
    echo [信息] 正在安装 PM2...
    npm install -g pm2
)
echo   - PM2 已安装

nginx -v >nul 2>&1
if errorlevel 1 (
    echo [警告] 未检测到 Nginx，请手动安装并配置
    echo 下载地址: https://nginx.org/en/download.html
)
echo   - Nginx 检查完成

REM ===== 2. 拉取最新代码 =====
echo.
echo [2/6] 拉取最新代码...
cd %BASE_DIR%
git pull origin main
if errorlevel 1 (
    echo [警告] 代码拉取失败，使用本地已有代码
)

REM ===== 3. 后端部署 =====
echo.
echo [3/6] 部署后端...
cd %BACKEND_DIR%

echo   - 安装 Python 依赖...
pip install -r requirements.txt

if not exist .env (
    echo   - 创建 .env 配置文件...
    copy .env.example .env
    echo   [提示] 请编辑 .env 文件配置录音目录等参数
)

echo   - 启动后端服务 (PM2)...
pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8000" --name bchao-backend 2>nul
pm2 save

REM ===== 4. 前端构建 =====
echo.
echo [4/6] 构建前端...
cd %FRONTEND_DIR%

echo   - 安装 Node 依赖...
npm install

echo   - 构建生产包...
npm run build
if errorlevel 1 (
    echo [错误] 前端构建失败，请检查错误信息
    pause
    exit /b 1
)

REM ===== 5. Nginx 配置 =====
echo.
echo [5/6] 配置 Nginx...

set NGINX_CONF=C:\nginx\conf\nginx.conf
if exist %NGINX_CONF% (
    echo   - 备份原有配置...
    copy %NGINX_CONF% %NGINX_CONF%.bak
)

echo   - 复制项目 Nginx 配置...
copy %BASE_DIR%\nginx.conf %NGINX_CONF%

echo.
echo [提示] 请确认 Nginx 配置中的路径是否正确：
echo   - root 应指向: %FRONTEND_DIR%\dist
echo   - alias 应指向: %BACKEND_DIR%\data\recordings
echo.
echo 修改后执行: nginx -s reload

REM ===== 6. 验证 =====
echo.
echo [6/6] 验证服务状态...
pm2 list

echo.
echo ========================================
echo   部署完成！
echo ========================================
echo.
echo 访问地址: http://%COMPUTERNAME% 或 http://服务器IP
echo.
echo 常用命令：
echo   查看后端日志:  pm2 logs bchao-backend
echo   重启后端:      pm2 restart bchao-backend
echo   停止后端:      pm2 stop bchao-backend
echo   查看服务列表:  pm2 list
echo.
pause
