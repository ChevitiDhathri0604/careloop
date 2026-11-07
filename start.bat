@echo off
echo ======================================================================
echo  Starting CareLoop Multi-Agent Control Plane & Ops Console...
echo ======================================================================
cd /d "%~dp0"
echo Opening browser to http://127.0.0.1:8000
start http://127.0.0.1:8000
python run_demo.py --serve
pause
