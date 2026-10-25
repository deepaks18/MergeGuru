@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "MergeGuru Lite v3 Beta" ".venv\Scripts\pythonw.exe" "main_gui_lite_v3.py"
) else (
    pythonw "main_gui_lite_v3.py"
)

endlocal
