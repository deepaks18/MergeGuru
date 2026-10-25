# MergeGuru Editions

## Shared Engine

Both editions use `mergeguru_engine.py` for:

- Source discovery and ZIP expansion
- Excel/CSV reading
- Sheet resolution
- Header cleaning and schema validation
- Shuffled and extra-column handling
- Sequential and controlled parallel combine
- Memory optimization
- Filtering
- Excel, CSV, CSV-Unique text, and Parquet export

Engine changes must be made in the shared module so Lite and Pro receive the
same processing behavior.

## MergeGuru Lite v3.1 - Preview

- Entry point: `main_gui_lite_v3.py` or `main_gui.py`
- UI package: `mergeguru_lite_v3/`
- UI framework: Tkinter with the branded responsive workbench
- Build specification: `MergeGuru_Lite.spec`
- Preview EXE: `editions_dist/preview/MergeGuru_Lite_v3_1_Preview.exe`
- Dependencies: `requirements-lite.txt`
- Status: development preview; does not replace v3.0 production

Run:

```powershell
.\.venv\Scripts\python.exe main_gui_lite_v3.py
```

Verification:

```powershell
.\.venv\Scripts\python.exe tools\lite_v3_1_release_check.py
.\tools\sign_windows_release.ps1 -CheckOnly
```

## MergeGuru Lite v3.0 - Production

- Frozen source snapshot: `releases/MergeGuru_Lite_v3_0/MergeGuru_Lite_v3_0_Source.zip`
- UI framework: Tkinter with the branded responsive workbench
- Frozen build specification: `releases/MergeGuru_Lite_v3_0/MergeGuru_Lite.spec`
- Production EXE: `editions_dist/lite/MergeGuru_Lite.exe`
- Dependencies: `requirements-lite.txt`
- Status: promoted to production on 4 October 2026

## MergeGuru Lite v2.4 - Rollback

- Legacy source entry: `main_gui.py`
- Rollback bundle: `releases/MergeGuru_Lite_v2_4_Rollback/`
- Rollback EXE: `MergeGuru_Lite_v2_4.exe`
- SHA-256: `7463A0662AEC0C90C3F2183E6822EC0823D860D303866EA9D207A2F7A29BCD4F`

The v2.4 source and executable are retained only for controlled rollback.

## MergeGuru Lite v3 Beta - Historical Candidate

- Entry point: `main_gui_lite_v3.py`
- UI package: `mergeguru_lite_v3/`
- UI framework: Tkinter with the branded responsive workbench components
- Build specification: `MergeGuru_Lite_v3_Beta.spec`
- Candidate EXE: `editions_dist/beta/MergeGuru_Lite_v3_Beta.exe`
- Status: retained as the pre-production candidate that preceded v3.0 promotion

Run:

```powershell
.\.venv\Scripts\python.exe main_gui_lite_v3.py
```

Historical Beta verification:

```powershell
.\.venv\Scripts\python.exe -m unittest tools.lite_v3_beta_check -v
```

## MergeGuru Pro

- Entry point: `main_gui_pro.py`
- UI framework: PySide6
- Build specification: `MergeGuru_Pro.spec`
- Dependencies: `requirements-pro.txt`
- Goal: modern interface with richer tables, dialogs, and interaction

Run:

```powershell
.\.venv\Scripts\python.exe main_gui_pro.py
```

## Verification

```powershell
.\.venv\Scripts\python.exe tools\health_check.py
.\.venv\Scripts\python.exe tools\shared_engine_check.py
.\.venv\Scripts\python.exe tools\lite_v3_release_check.py
```
