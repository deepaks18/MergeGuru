# MergeGuru Lite Stability Pass

> Historical test snapshot for the v2.4 artifact and environment described
> below. The measurements are useful regression evidence, not current-source or
> enterprise certification.

Date: 2026-10-03. Release: v2.4. Scope: stabilize the existing Lite workflow,
not redesign it or certify every production scenario.

## Fixes From Reproduced Failures

1. **Parallel combine cancellation:** the UI previously became available before
   active background readers finished. Cancellation now cancels pending reads,
   skips work not yet started, and keeps the operation busy until active readers
   drain. A file read already in progress cannot necessarily stop immediately.
2. **Lossless memory optimization:** float downcasting previously could alter
   values. It is now applied only when conversion back to the original dtype
   reproduces every value exactly. This shared-engine fix applies to both Lite
   and Pro source versions; it can reduce memory savings for precise values.
3. **Export recovery:** an exception before the existing save handler could leave
   export controls permanently busy. A worker-level guard now restores controls,
   reports the failure, and retains combined data for retry.
4. **Modal wait handling:** an already-displayed export question no longer treats
   the user's time to answer as a 30-second UI timeout. Pending UI work still has
   a timeout; abandoned callbacks are not executed later.

## Verification

All listed checks passed against the updated source or packaged Lite executable.
Counts represent different kinds of tests and scenarios, not a single unit suite.

| Suite | Coverage | Result |
|---|---|---|
| `tools/high_risk_qa.py` | Filter errors, identifiers, schema changes, atomic writes, Excel limits, Lite/Pro regressions | 29 tests passed |
| `tools/lite_ux_check.py` | Navigation/control state, preview, category selection, footer visibility, activity animation | 9 scenarios passed; no Tk callback errors |
| `tools/stability_fault_checks.py` | Parallel cancellation, float precision, worker failure, actual Windows destination lock, forced writer termination, modal wait | 6 tests passed |
| `tools/stability_recovery_check.py` | Cancel/recombine, simulated write failure, cancelled overwrite, successful retry with audit | 4 scenarios passed; no Tk callback errors |
| `tools/stability_load_check.py` | Generated larger datasets and actual output round-trips | 9 stages passed |
| Packaged `--self-test` | Bundled CSV/XLSX/ZIP reading, validation, combine, filtering, Excel/CSV/Parquet writing, cancellation, hidden Lite initialization | 8 checks passed; frozen executable |
| Health/shared-engine checks | Existing basic integration coverage | Both passed |
| Syntax compilation | Lite, Pro, shared engine, diagnostics and stability helpers | Passed |

Recovery tests preserved an existing completed output after failed/cancelled
writes, including a locked Windows destination. The forced-termination test
stopped a generated-data helper process midway through writing: the previous
output survived. A hard process kill can leave a temporary `.mergeguru-*` file;
normal cancellation and handled failures clean it up. No restart/resume guarantee
is provided for an interrupted operation.

## Generated-Data Load Results

Test environment: Windows, Python 3.12.1, pandas 3.0.2, openpyxl 3.1.5,
pyarrow 23.0.1. Available RAM at load-test start: 1.86 GiB.

- Wide CSV: 400,000 rows across four files, 109.9 MiB on disk. Includes shuffled
  columns, extra columns, source attribution, and zero-padded identifiers.
- Compact CSV: 1,000,000 rows across two files, 24.7 MiB on disk.
- Excel: 50,000 rows across two workbooks, 0.67 MiB on disk, with differently
  dated worksheet names and separate summary sheets.

| Stage | Seconds | Sampled Peak Process RSS (MiB) |
|---|---:|---:|
| Validate wide CSV sources | 0.03 | 108.7 |
| Combine 400,000 rows sequentially | 1.70 | 301.8 |
| Four cached filtered CSV exports, 200,000 rows each | 5.80 | 478.9 |
| 400,000-row Parquet round-trip | 1.39 | 557.8 |
| Combine 400,000 rows in parallel | 1.52 | 339.4 |
| Combine 1,000,000 compact CSV rows | 2.21 | 230.9 |
| Validate differently named Excel worksheets | 0.05 | 190.2 |
| Combine 50,000 Excel rows | 0.93 | 188.2 |
| Excel export and value round-trip, 50,000 rows | 3.38 | 185.9 |

Sequential and parallel results were compared for equality. Repeated filtered
exports were checked without rereading source files. Output checks covered row
counts, numeric totals, identifiers, provenance and extra-column alignment.
Excel output also verified the Data and Validation Report worksheets.

These synthetic local measurements are evidence for these fixtures, not a speed
promise or comparison with Power Query/VBA. RSS was sampled every 50 ms, includes
libraries and retained Python allocator memory, and can miss brief spikes.
Generated source/export fixtures were removed after the tests.

## Packaged Build

The tested executable is `editions_dist/lite/MergeGuru_Lite.exe`.

- Size: 66,854,081 bytes, approximately 63.76 MiB.
- SHA-256: `7463A0662AEC0C90C3F2183E6822EC0823D860D303866EA9D207A2F7A29BCD4F`.
- The installed release copy's hash matches the tested build.
- Previous executable retained at
  `releases/lite_pre_stability_20261003_133632/MergeGuru_Lite.exe`.
- Packaged test evidence: `work/lite_packaged_selftest.txt`.
- Generated load-test evidence: `work/stability_load_results.md`.
- Pro was not rebuilt. Its source uses the updated shared float optimization;
  an existing Pro EXE does not automatically receive source changes.

The build emitted an optional missing `jinja2` hook warning. The tested export
paths do not use pandas Styler, and actual packaged Excel/CSV/Parquet checks
passed. This does not certify untested styling-dependent code paths.

The opt-in self-test creates temporary synthetic fixtures and a local text report;
it does not send data to a service. Normal application startup is unchanged.

```powershell
.\editions_dist\lite\MergeGuru_Lite.exe --self-test "C:\path\to\selftest.txt"
```

## Before Production Rollout

- Test the actual 2 GB source folder on representative hardware/storage. A
  million compact rows is not equivalent to 2 GB of wide Excel data. This pass
  did not force a real out-of-memory condition.
- Test startup and export on a clean Windows laptop without Python installed,
  including firm antivirus and endpoint restrictions. Packaged tests here ran
  on the development machine, not a clean machine.
- Visually check the default window, smaller displays and Windows scaling, and
  have nontechnical users complete the workflow. Hidden-window assertions do not
  certify visual quality, accessibility or every DPI setting.
- Test firm-specific network shares, permissions, OneDrive sync conflicts and
  real locked/password-protected/corrupt inputs. A simulated write failure is not
  a real full-disk test.
- Treat security review as separate work. This pass is not a penetration test,
  security certification or assurance that a data breach is impossible.

## Repeat Source Checks

```powershell
.\.venv\Scripts\python.exe tools\high_risk_qa.py
.\.venv\Scripts\python.exe tools\lite_ux_check.py
.\.venv\Scripts\python.exe tools\stability_fault_checks.py
.\.venv\Scripts\python.exe tools\stability_recovery_check.py
.\.venv\Scripts\python.exe tools\stability_load_check.py
.\.venv\Scripts\python.exe tools\shared_engine_check.py
.\.venv\Scripts\python.exe tools\health_check.py
```
