@echo off
cd /d C:\MedSpa\medspa_pipeline

call .venv\Scripts\activate.bat

python main.py

echo.
echo Pipeline finished. Press any key to close this window.
pause >nul
