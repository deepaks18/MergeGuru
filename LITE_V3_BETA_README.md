# MergeGuru Lite v3 Beta

This is the separate functional Beta of the approved Lite workflow redesign.
It uses the shared `mergeguru_engine.py` processing engine and does not replace
the stable v2.4 source or `editions_dist/lite/MergeGuru_Lite.exe`.

## Run From Source

Double-click `run_lite_v3_beta.cmd`, or run:

```powershell
.\.venv\Scripts\python.exe main_gui_lite_v3.py
```

## Workflow

1. **Sources**: browse one folder or select files from multiple locations,
   choose the yellow-star template, and exclude unwanted files.
2. **Check & Prepare**: select the reference worksheet, handle dated/different
   sheet names by matching headers, optionally retain extra columns, configure
   header/footer rows, validate, and combine once.
3. **Filters**: add/edit/remove filters against the cached DataFrame. Category
   search uses case-insensitive **Starts with** by default, so typing `Wa` shows
   every value starting with `Wa`; Select/Clear/Invert affects all matches.
4. **Export**: preview the cached filtered result, choose Excel, CSV,
   CSV-Unique text, or Parquet, and export without rereading source files.

## Processing And Safety Behavior

- File discovery, worksheet inspection, validation, combine, filtering, and
  export run away from Tk's UI thread. The fixed progress dock shows phase,
  percentage, elapsed time, ETA, file/byte detail, and Cancel.
- Validation classifies unreadable, corrupt, locked/permission, unsupported,
  and password-protected sources through the shared engine. Failed files are
  excluded from combine and shown in the validation table/report.
- Columns are aligned by normalized header name, not physical order. Files that
  contain every template column plus extra columns pass with a warning when
  **Keep extra columns at the end** is enabled.
- Combine can use controlled parallel reads. Worker count is conservative for
  Excel and large input sets. Memory optimization downcasts only when values are
  preserved. A RAM estimate is shown before preparation and warns when unsafe.
- Prepared data remains cached for additional filter/export combinations. A
  source, worksheet, layout, or processing-setting change invalidates prepared
  data and clears filters; output-format/path changes do not trigger a reread.
- CSV/Excel writes use a temporary sibling file and commit only after completion.
  Cancellation therefore does not replace an existing destination with a
  partial file.
- Excel output includes a `Validation Report` worksheet. Every successful
  format also receives a human-readable `.audit.txt` file beside the output.
- There is no telemetry, upload, browser request, cloud API, or automatic data
  transfer in this Beta. Preferences are local and intentionally omit source
  names and filters.

## Deliberate Guardrails

- Folder selection scans the selected folder itself, not every subfolder.
- Category checkbox mode supports up to 20,000 unique values. Above that limit,
  the UI explains the tradeoff and offers text Starts-with/Contains filters
  rather than displaying an incomplete value list.
- Preview shows 5, 10, or 25 rows and at most the first 50 columns. This limits
  UI rendering only; export includes every matching row and column.
- Deep blank-row and duplicate-row scans are not run by default. The audit says
  so explicitly, avoiding a hidden full-data scan during combine.
- Parquet export requires the packaged `pyarrow` dependency.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tools.lite_v3_beta_check -v
```

The suite uses temporary CSV fixtures and one mapped Tk session. It covers
cancel/retry, real discovery, validation, shuffled columns, accepted extra
columns, the visible `Wa` bulk-selection flow, cached filtering, CSV-Unique text,
atomic cancellation, validation/audit reports, preference scope, and the stable
v2.4 EXE checksum.

This Beta should be user-tested with representative company files before it is
promoted over v2.4. The recommended rollout is a small pilot followed by defect
triage and one final regression/package-signing pass.

## Current Candidate

- Executable: `editions_dist/beta/MergeGuru_Lite_v3_Beta.exe`
- Size: `66,586,776` bytes (`63.50 MiB`)
- SHA-256: `6A24A4F6AA62DD5E41B992A95DDB81C69485038233A9BDEAD91B7C69C82D3EF4`
- Packaged startup: one responsive window titled `MergeGuru Lite | v3.0 Beta`
- Automated result: `12/12` checks passed on 4 October 2026
- Stable v2.4 SHA-256 remains
  `7463A0662AEC0C90C3F2183E6822EC0823D860D303866EA9D207A2F7A29BCD4F`
