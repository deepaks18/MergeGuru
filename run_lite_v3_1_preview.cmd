@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo MergeGuru virtual environment was not found.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "main_gui_lite_v3.py"
endlocal
