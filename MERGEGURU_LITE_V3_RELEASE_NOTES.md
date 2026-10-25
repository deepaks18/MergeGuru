# MergeGuru Lite v3.0 - Production Release Notes

> Historical binary record. These results apply to the v3.0 artifact identified
> by the hash below, not automatically to later source changes. "Production"
> here means the promoted internal build; it is not a security certification.

Release date: 4 October 2026

## Release Status

MergeGuru Lite v3.0 is the production Lite edition. It replaces v2.4 at:

`editions_dist/lite/MergeGuru_Lite.exe`

The previous production build is preserved in the verified v2.4 rollback
bundle under `releases/MergeGuru_Lite_v2_4_Rollback/`.

## User Experience

- Four clear stages: Sources, Check & Prepare, Filters, and Export.
- Responsive branded interface tested at 720x560, 900x640, and 1060x780.
- Folder selection or multi-file selection from different locations.
- Yellow-star reference template indicator and per-file exclusion/restoration.
- Conditional header/footer controls and logical format-specific controls.
- Sticky operation dock showing phase, percentage, elapsed time, ETA, and details.
- Safe Cancel behavior and locked settings while an operation is active.
- Export success actions: Open file, Open folder, Open audit report, change
  filters, or export another file without reloading source data.

## Data Processing

- Excel, CSV, and ZIP-contained Excel/CSV discovery.
- Different worksheet names can be matched by template headers.
- Columns align by normalized header name even when source order is shuffled.
- Files with all required columns and additional columns can pass with warning;
  extra columns are appended when the option is enabled.
- Sequential or controlled-parallel combine with conservative worker limits.
- Optional lossless memory optimization and a pre-combine RAM warning.
- Prepared data remains cached for repeated filter/export combinations.
- Source/layout changes invalidate prepared data and filters; export settings do
  not force a source reread.

## Filters And Preview

- Searchable category picker with case-insensitive Starts-with search by default.
- Typing `Wa` shows every category starting with `Wa`; Select, Clear, and Invert
  apply to every match, including values not yet rendered on screen.
- Include, Exclude, Starts-with, and Contains filter actions.
- Edit, remove, clear, and undo filter changes.
- Category collection stops safely after proving a column exceeds 20,000 unique
  values; high-cardinality columns use text filters instead of an incomplete list.
- Draft counts use a Boolean mask without materializing another filtered table.
- Preview limits UI rendering to 5, 10, or 25 rows and 50 columns without
  limiting the final export.

## Export And Audit

- Excel, CSV, CSV-Unique text, and Parquet output.
- CSV-Unique text exposes its protected-column picker directly below the format.
- Writes use a temporary sibling file and replace the destination only after a
  complete successful export.
- Excel output includes a `Validation Report` worksheet.
- Every successful format receives a human-readable `.audit.txt` companion.
- The audit records validation, source inclusion, filters, row/column counts,
  extra columns, output details, and the performance-safe quality-scan status.

## Security

- Processing is local. There is no telemetry, upload, browser request, cloud API,
  or automatic data transmission.
- Local preferences intentionally exclude source names and filters.
- The production EXE is self-contained; Python is not required on user laptops.
- The EXE is currently unsigned. Enterprise distribution should add an approved
  organization code-signing certificate to reduce Windows trust warnings.

## Verification

- Production release suite: `13/13` passed.
- Packaged launch: passed from the final production path.
- FileVersion/ProductVersion: `3.0.0`.
- Size: `66,588,234` bytes (`63.50 MiB`).
- SHA-256: `54E0283B5A171550571C5616B84A6A96E8A1D25FA476399A48260E771D8EFD06`.
- v2.4 rollback SHA-256:
  `7463A0662AEC0C90C3F2183E6822EC0823D860D303866EA9D207A2F7A29BCD4F`.

## Operational Guardrails

- Folder selection scans the chosen folder itself, not all subfolders.
- Deep blank-row and duplicate-row scans remain off by default to avoid hidden
  full-data work; the audit reports that status.
- Parquet support depends on the packaged pyarrow runtime.
- Production promotion does not remove the v3 Beta candidate or v2.4 rollback.
