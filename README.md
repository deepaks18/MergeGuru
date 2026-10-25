# MergeGuru

MergeGuru is a local Windows desktop application for discovering, validating,
combining, filtering, and exporting CSV and Excel data. The active Lite source
is the v3.1 candidate. It is suitable for controlled internal evaluation; see
`PRODUCTION_READINESS.md` before a wider deployment.

## Canonical Application

- Launcher: `main_gui_lite_v3.py`
- Lite UI: `mergeguru_lite_v3/`
- Shared processing engine: `mergeguru_engine.py`
- PyInstaller definition: `MergeGuru_Lite.spec`
- Compatibility entry point: `main_gui.py`

`main_gui.py` still routes a normal launch to the v3 Lite UI, but also retains
legacy definitions required by historical checks and the Pro source. New Lite
work should target the canonical launcher, UI package, and shared engine.

## Run From Source

```powershell
.\.venv\Scripts\python.exe main_gui_lite_v3.py
```

The familiar compatibility command remains available:

```powershell
.\.venv\Scripts\python.exe main_gui.py
```

## Core Workflow

1. Select a folder or multiple source files.
2. Choose a reference file and worksheet.
3. Configure optional layout handling, then validate the sources.
4. Combine once, preview the result, and add or edit filters.
5. Export repeatedly without rereading unchanged source files.

Supported output formats are Excel, CSV, CSV-Unique text, and Parquet. Excel
exports use an atomic, row-streaming XlsxWriter path and can include a
`Validation Report` worksheet. Every completed export can also receive a local,
human-readable audit text file.

## Data Safety

- Processing is local; the application has no upload or telemetry feature.
- Completed output replaces the destination only after a successful temporary
  write.
- Filter failures do not fall back to exporting unfiltered data.
- Source metadata is checked after validation to detect many in-place changes.
- Formula-like and URL-like source text is written as literal Excel text.
- Excel row and column limits are rejected before an export starts.

The application is not a security certification or a guarantee that a breach is
impossible. Enterprise use still requires the firm's normal endpoint, access,
code-signing, retention, and security-review controls.

## Verification

Run the current source release gate:

```powershell
.\.venv\Scripts\python.exe tools\shared_engine_check.py
.\.venv\Scripts\python.exe tools\health_check.py
.\.venv\Scripts\python.exe tools\lite_v3_release_check.py
.\.venv\Scripts\python.exe tools\high_risk_qa.py
```

GitHub Actions repeats these checks on Windows, builds the executable, and runs
the packaged self-test. The workflow is `.github/workflows/mergeguru-ci.yml`.

See `ARCHITECTURE.md` for ownership boundaries and
`PRODUCTION_READINESS.md` for verified coverage and remaining release gates.
