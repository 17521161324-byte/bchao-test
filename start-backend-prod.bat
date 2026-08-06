@echo off
REM 生产环境启动脚本
REM ===== 读取部署配置（.env.deploy）覆盖路径与端口 =====
if exist "%~dp0.env.deploy" (
  for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env.deploy") do set %%a=%%b
)
if "%BASE_DIR%"=="" set BASE_DIR=E:\bchao-test
if "%BACKEND_PORT%"=="" set BACKEND_PORT=8000
@echo off
REM 生产环境启动脚本
cd /d "%BASE_DIR%\backend"

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo Stopping old backend process on port 8000: %%a
  taskkill /PID %%a /F
)

python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --workers 4 --proxy-headers
