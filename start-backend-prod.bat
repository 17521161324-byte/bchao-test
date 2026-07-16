@echo off
REM 生产环境启动脚本
cd /d E:\bchao-test/backend

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo Stopping old backend process on port 8000: %%a
  taskkill /PID %%a /F
)

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers
