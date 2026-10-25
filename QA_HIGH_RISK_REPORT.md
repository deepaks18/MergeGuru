# MergeGuru Focused QA Results

Date: 2026-10-03

Scope: the six priority data-integrity cases identified in the code review,
including their shared-engine behavior and selected Lite/Pro entry points.
This is a focused automated regression pass, not execution of the entire
previously proposed manual test suite or production certification.

## Outcome

The initial 16 checks reproduced 12 failures and one error. After source fixes
and expanded coverage, all 29 focused regression tests passed. The existing
shared-engine integration check, Lite health check, and headless Pro workflow
check also passed.

| Original Test ID | Risk | Reproduced Behavior | Implemented Change | Final Result |
|---|---|---|---|---|
| FIL-14 | High | Lite exported the combined, unfiltered dataset after a filter error. Pro could retain an older filtered result. | Lite stops before saving on filter errors; Pro reevaluates current filters before exporting and stops on errors. | PASS |
| EXP-07 | High | Numeric inference removed leading zeros from CSV and Excel text identifiers. | Read lexical values before inference; retain zero-padded and long numeric strings; protect selected CSV columns without converting missing values to text. | PASS for tested identifiers |
| EXP-09 | High | Excel accepted a data-row count that left no space for the header. | Enforce 1,048,575 data rows plus one header row; check the 16,384-column limit for both exported worksheets. | PASS |
| EXP-14 | High | Cancelled/failed writes left incomplete files or damaged an existing destination. | Write to a temporary file beside the destination, check cancellation, and replace the destination only after successful writing. Excel checks cancellation between row chunks. | PASS within checkpoint limits |
| COM-06 | High | Generated provenance overwrote a business column named source_file and introduced duplicate output headers. | Choose source_file, mergeguru_source_file, or a numbered alternative without overwriting source columns. | PASS in engine and Lite |
| COM-07 | High | A changed source could combine with missing columns silently filled with nulls. | Record source metadata during validation; check it before/after reading; recheck full-read schema; stop Lite combine on read/schema failure. | PASS |

## Executed Regression Coverage

| Test | Result |
|---|---|
| Lite filter error never exports unfiltered data | PASS |
| Invalid Contains regex is rejected | PASS |
| CSV zero-padded and long identifiers survive reading | PASS |
| Excel text identifiers survive reading | PASS |
| ZIP-contained CSV identifiers survive reading | PASS |
| CSV-Unique text preserves blanks instead of emitting null text | PASS |
| Excel rejects excessive data rows before opening a writer | PASS |
| Excel rejects excessive columns before opening a writer | PASS |
| Lite switches format at the header-inclusive Excel limit | PASS |
| Last valid Excel data-row count passes the guard | PASS |
| Cancelled CSV preserves an existing destination | PASS |
| Cancelled CSV leaves no new destination or temporary file | PASS |
| Cancelled Excel before commit preserves existing destination | PASS |
| Cancelled Excel between chunks preserves existing destination | PASS |
| Parquet cancellation after writer return prevents destination replacement | PASS |
| CSV write failure preserves destination and removes temporary output | PASS |
| Progress reaches 100 percent only after destination commit | PASS |
| Engine preserves source_file and another provenance-name collision | PASS |
| Source schema changed after validation is rejected | PASS |
| Missing required columns are rejected even without a validation snapshot | PASS |
| Source data changed with unchanged schema is rejected | PASS |
| Source change during reading is rejected | PASS |
| Lite preserves a business source_file column | PASS |
| Lite stops combine when an approved source changes | PASS |
| Combine cancelled at the final-file checkpoint does not publish data | PASS |
| Pro filter error does not export stale results | PASS |
| Excel Data and Validation Report worksheets round-trip correctly | PASS |
| Excel 10,000-row chunk boundary neither repeats headers nor drops rows | PASS |
| Actual Parquet round-trip preserves identifiers and numeric values | PASS |

## Remaining Verification And Limits

- Live desktop dialogs, Windows scaling, title-bar close, and packaged executable
  behavior were not manually exercised. The Pro workflow check runs headlessly.
- The exact Excel maximum-row acceptance check mocks the writer. Oversized inputs
  are rejected before writing; this pass did not create million-row workbooks.
- CSV cancellation occurs between chunks. Excel cancellation occurs between
  10,000-row chunks and before commit; workbook finalization may delay the response.
  Parquet's writer runs to completion before a pending cancellation discards its
  temporary result. Active combine reads can also delay cancellation.
- Controlled cancellation and write exceptions clean up temporary outputs. A
  forced process termination or power loss can leave a temporary file behind.
- Source change detection uses file size and nanosecond modification/change times,
  not a content hash. It is intended to catch normal edits, replacement, and changes
  during reading; it is not a cryptographic integrity guarantee.
- Identifier coverage is zero-padded strings and long numeric strings. Numbers
  already stored numerically in Excel, displayed with a custom zero-padding format,
  do not contain their original lexical representation. Other lexical conventions
  such as scientific notation need separate requirements and tests.
- Lossless identifier inference adds work during loading. No multi-GB speed or
  peak-memory benchmark was performed in this pass.
- At the time of this initial integrity pass, packaged EXEs were not rebuilt.
  The subsequent Lite stability pass rebuilt and tested Lite; see
  STABILITY_PASS_REPORT.md for current packaged evidence. Pro was not rebuilt.

## Reproduce

Run from the project folder with the development environment that includes both
Lite and Pro dependencies:

```powershell
.\.venv\Scripts\python.exe tools\high_risk_qa.py
.\.venv\Scripts\python.exe tools\shared_engine_check.py
.\.venv\Scripts\python.exe tools\health_check.py
.\.venv\Scripts\python.exe tools\pro_workflow_check.py
```
