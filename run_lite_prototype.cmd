@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo This preview needs the project's existing Python environment.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "main_gui_lite_prototype.py"
