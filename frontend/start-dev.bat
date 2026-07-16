@echo off
cd /d E:\bchao-test\frontend
node node_modules\vite\bin\vite.js --port 5190 --strict-port --host 0.0.0.0 %*
