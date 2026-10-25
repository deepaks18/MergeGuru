# MergeGuru v2.4 - Detailed Feature and Architecture Brief

## 1. Executive Summary

MergeGuru is a local desktop application for combining, validating, filtering, and exporting Excel, CSV, and ZIP-contained data files. It is designed for business users who regularly handle downloaded dumps, operational reports, and large folder-based datasets without relying on Power Query, VBA, or macros.

The key design principle is controlled automation: the application guides the user through source selection, reference selection, schema validation, combining, filtering, preview, and export while keeping the data local on the user's machine.

## 2. Core Business Problems Solved

MergeGuru addresses these common real-world problems:

- Combining many Excel/CSV files into one output without writing code.
- Detecting mismatched schemas before files are merged.
- Handling shuffled columns safely.
- Allowing optional extra columns while keeping reference columns first.
- Handling report dumps where the real header is not on row 1.
- Filtering large combined datasets without repeatedly recombining the source folder.
- Exporting multiple filtered outputs from the same combined dataset.
- Producing a human-readable audit report for traceability.
- Working locally without uploading files to any cloud service.
- Selecting either an entire folder or only specific files when the user does not want to reorganize files into a separate folder.

## 3. Supported Input Types

MergeGuru supports:

- Direct `.xlsx` files.
- Direct `.csv` files.
- `.zip` files containing `.xlsx` or `.csv` files.

For ZIP files, MergeGuru reads supported inner files directly from the archive. This avoids requiring the user to manually extract the ZIP before processing.

Source selection options:

- `Browse Folder...` scans all supported files in the selected folder.
- `Select Files...` allows Ctrl-selecting specific `.xlsx`, `.csv`, or `.zip` files directly.
- When specific files are selected, MergeGuru processes only those files instead of scanning the whole folder.

## 4. Wizard Workflow

The application follows a six-step wizard:

1. Select Data
2. Discover Sources
3. Reference Sheet
4. Validate Files
5. Add Filters
6. Export

This structure reduces user error because each decision is made in sequence.

## 5. Reference-Based Validation

MergeGuru uses one selected source file as the reference template.

Validation compares every file against the reference columns after cleaning the headers. Header cleaning includes:

- Trimming leading/trailing spaces.
- Replacing line breaks with spaces.
- Collapsing repeated whitespace.
- Converting names to lowercase.

This means columns such as ` Customer ID ` and `customer id` are treated consistently.

## 6. Handling Shuffled Columns

MergeGuru does not require input files to have columns in the same order as the reference file.

Algorithm:

1. Read the header row from each file.
2. Clean each column name.
3. Compare required columns by name, not by position.
4. During combine, reindex each DataFrame into the reference column order.

This prevents data corruption when one file has columns like:

`Amount, Region, ID`

while the reference has:

`ID, Region, Amount`

The output still follows the reference order.

## 7. Handling Extra Columns

By default, validation is strict: files with extra columns fail validation.

When the user enables `Allow extra columns and append at end`, MergeGuru allows files that contain all reference columns plus additional columns.

Algorithm:

1. Check that all reference columns are present.
2. Check that there are no duplicate headers.
3. Detect extra columns not present in the reference.
4. Mark the file as a warning instead of a failure.
5. Append extra columns after the reference columns in the output.
6. Keep `source_file` as the final tracking column.

This gives flexibility without silently changing the core structure.

## 8. Handling Missing Columns

If any required reference column is missing, the file fails validation and is excluded from combine.

Reason:

Missing required columns mean the file cannot reliably produce the same business dataset as the reference.

## 9. Handling Duplicate Headers

Files with duplicate column names fail validation.

Reason:

Duplicate headers make column alignment ambiguous. For example, if a file contains two `amount` columns, the app cannot safely know which one should be used.

## 10. Header and Footer Cleanup

Some downloaded dumps contain unwanted report rows above the real table or footer rows below the data.

MergeGuru includes an optional layout-fix checkbox. When enabled, the user can specify:

- Header row number.
- Number of footer rows to ignore.

Algorithm:

- Header row `N` becomes Pandas header index `N - 1`.
- Footer rows are skipped using `skipfooter`.
- CSV files use the Python parsing engine when footer skipping is required.

This supports reports such as:

- Row 1: Report title
- Row 2: Export timestamp
- Row 3: Real column headers
- Last row: Total or footer note

## 11. Validation Performance

Validation reads only file headers, not full data.

Current optimization:

- Header validation runs in parallel using `ThreadPoolExecutor`.
- Up to 6 worker threads are used.
- UI updates are still performed safely on the Tkinter main thread.

Why this matters:

Opening many Excel files just to read headers can be slow. Parallel header reads improve validation time without loading full datasets into memory.

## 12. Validation Error Classification

MergeGuru classifies validation failures into clearer categories:

- Password-protected or encrypted file.
- Locked or permission issue.
- Corrupt, invalid, or partially downloaded file.
- Read error.
- Schema mismatch.
- Missing columns.
- Extra columns.
- Duplicate headers.

This helps users understand whether the problem is with the file structure, access permissions, or file health.

## 13. Duplicate Source Detection

MergeGuru detects possible duplicate source files during discovery.

Algorithm:

1. Normalize each source filename.
2. Read file size.
3. Group files by `(normalized filename, file size)`.
4. If multiple files share the same key, show a possible duplicate warning.

This does not block the workflow because duplicate-looking files may be intentional. It simply warns the user early.

## 14. Combining Algorithm

MergeGuru combines only files that passed validation.

Algorithm:

1. Loop through passed source files.
2. Read each file fully.
3. Clean the columns.
4. Reindex columns to reference order.
5. Append allowed extra columns at the end.
6. Add a `source_file` column.
7. Store each file's DataFrame temporarily.
8. Concatenate in rolling batches to reduce peak memory.
9. Produce one combined DataFrame.

The `source_file` column is important because it lets users trace every row back to the original file.

## 15. Rolling Concat for Lower Memory

Instead of concatenating all individual DataFrames in one large operation, MergeGuru uses rolling batches.

Current approach:

- Batch size: 10 frames.
- Concatenate each batch into an intermediate frame.
- Clear the original frame list.
- Concatenate the smaller batch results into the final DataFrame.

Benefit:

This reduces peak RAM compared with holding every individual DataFrame and one huge final combined copy at the same time.

## 16. Small Data Handling

For small and moderate datasets, MergeGuru prioritizes convenience and richer UI feedback.

Small-data behavior includes:

- Full preview is fast enough to calculate on demand.
- Optional duplicate-row checks are available when deeper diagnostics are enabled.
- Optional blank-row checks are available when deeper diagnostics are enabled.
- Excel export is practical.
- Category pick-lists are shown when unique values are within the configured limit.
- Filters can be edited and recalculated quickly.

Small datasets benefit from the most interactive experience.

## 17. Large Data Handling

For large datasets, MergeGuru shifts toward memory safety and controlled processing.

Large-data behavior includes:

- Memory pre-check before combining.
- Low-memory warning with recommendations.
- Rolling concat to reduce peak RAM.
- Optional fast combine mode using controlled parallel reads.
- Optional memory optimization after combine.
- Optional deeper data quality checks; disabled by default for speed.
- CSV chunked export with progress.
- Parquet export option for large output.
- Excel row-limit protection.
- Duplicate-row checks run only when explicitly enabled and still skip above the safety limit.
- Blank-row checks run only when explicitly enabled and still skip above the safety limit.
- Category pick-list is hidden above `20,000` unique values.
- Progress display includes elapsed time, ETA, file count, size progress, and RAM where available.

## 18. Fast Combine Mode

MergeGuru includes an optional fast combine mode for users who want higher read throughput.

Default behavior:

- Combine remains sequential by default.
- This is the safest mode for large Excel files and low-memory machines.
- It minimizes the number of DataFrames being loaded at the same time.

Fast combine behavior:

- Enabled by `Fast combine mode (parallel reads, uses more memory)`.
- Reads multiple source files in parallel using a controlled worker pool.
- Uses conservative limits instead of using every CPU core.
- Caps workers lower when Excel files are present.
- Caps workers lower for very large folders above roughly `1 GB`.
- Preserves final output order by sorting completed reads back to the original validated source order.

Why it is optional:

- Parallel reads can reduce combine time for many CSV or medium-sized files.
- Parallel reads can increase RAM pressure because multiple files are loaded at the same time.
- Excel parsing is heavier than CSV parsing, so uncontrolled parallel Excel reads can cause memory spikes.

Management explanation:

MergeGuru gives users both safety and speed. The default mode favors stability, while fast combine mode gives power users an acceleration option when machine capacity and data shape are suitable.

## 19. Memory Optimization

MergeGuru includes optional memory optimization after combine.

Algorithm:

- Integer columns are downcast to smaller integer types where possible.
- Float columns are downcast to smaller float types where possible.
- Low-cardinality text columns are converted to categorical dtype.

Example:

- `int64` may become `int16` or `int32`.
- Repeated text like region/status/category may become a memory-efficient category.

The app records before/after memory usage when optimization succeeds.

## 20. Memory Safety Pre-Check

Before combining, MergeGuru estimates whether enough RAM is available.

Algorithm:

1. Sum input file sizes.
2. Estimate needed memory using file size and a safety multiplier.
3. Compare against available system RAM.
4. Warn the user if memory may be insufficient.

Recommendation shown to users:

- Close Excel or other heavy applications.
- Keep memory optimization enabled.
- Use CSV or Parquet for very large exports.
- Process fewer files at once if needed.

## 21. Progress and ETA

MergeGuru provides progress details during long operations.

Validation:

- Files completed.
- Elapsed time.
- Estimated remaining time.
- Validation summary.

Combine:

- File count.
- Percentage.
- Bytes processed.
- Total input size.
- ETA.
- RAM usage when available.

Export:

- Percentage.
- Elapsed time.
- ETA.
- Output file size where available.
- Writing status.

## 22. Cancellation

MergeGuru supports cooperative cancellation.

Combine cancellation:

- User can request cancel.
- Combine stops after the current file finishes reading.

Export cancellation:

- CSV and CSV-Unique exports can stop between chunks.
- Parquet can stop before the write starts.
- Excel can stop before the `to_excel` call starts, but not safely mid-write because Pandas/openpyxl does not expose a clean cancellation hook.

This is a safe design because it avoids corrupting in-memory state during a file operation.

## 23. Filter System

MergeGuru supports three filter types:

### Category Filter

Used for columns with manageable unique values.

Capabilities:

- Include selected values.
- Exclude selected values.
- Search values.
- Select all visible.
- Clear all visible.
- Invert visible selection.

Category pick-list limit:

- `20,000` unique values.

If a column exceeds this limit, the app recommends Text/ID filtering instead of trying to render a huge list.

### Text / ID Filter

Supports:

- Equals.
- Not equals.
- Contains.
- Starts with.
- Include pasted list.
- Exclude pasted list.

This is useful for account numbers, IDs, invoice numbers, employee codes, and large cardinality columns.

### Date Filter

Supports:

- Equals.
- Before.
- After.
- Between.

Dates are parsed using Pandas with invalid dates converted safely to missing values.

## 24. Filter Performance

MergeGuru caches computed filter results.

Algorithm:

1. Build a cache key from the active filters.
2. If filters have not changed, reuse the cached filtered DataFrame.
3. Cache string-converted series for text/category filters.
4. Cache date-converted series for date filters.
5. Recalculate only when filters change.

This improves repeated export and preview workflows.

## 25. Reusing Combined Data

After export, the user can choose `Change Filters`.

This returns to the filter step without recombining source files.

Business benefit:

The expensive combine operation is paid once. Users can create multiple filtered outputs from the same combined dataset.

## 26. Preview Before Export

The export page includes `Preview Filtered Rows`.

Behavior:

- Preview is user-triggered.
- It shows up to 25 rows.
- It shows up to 8 columns.
- It reports total filtered row count.

This avoids slowing the normal export path while still giving users confidence before saving large outputs.

## 27. Export Formats

MergeGuru supports:

- Excel `.xlsx`
- CSV `.csv`
- CSV-Unique text `.csv`
- Parquet `.parquet`

### Excel

Uses `openpyxl` through Pandas for conservative, reliable Excel export.

Excel safeguards:

- Warns above `300,000` rows.
- Blocks or redirects above Excel's hard limit of `1,048,576` rows.
- Offers CSV or Parquet when Excel is too large.

### CSV

CSV export writes in chunks.

Chunk size:

- Maximum of `10,000` rows or approximately 1/20th of the file.

This allows progress updates and cancellation points.

### CSV-Unique Text

This mode protects one selected column by prefixing values with an apostrophe.

Use case:

- Employee IDs.
- Account numbers.
- Codes with leading zeroes.
- Long numeric identifiers that Excel might auto-convert.

### Parquet

Parquet is offered for large data where compact storage and faster downstream analytics are useful.

Parquet requires optional dependencies such as `pyarrow` or `fastparquet`.

## 28. Auto Output Naming

MergeGuru automatically suggests timestamped output names.

Pattern:

`combined_output_YYYYMMDD_HHMMSS.xlsx`

If filters exist, the name includes the filter count.

If the filename already exists, MergeGuru adds a numeric suffix.

This reduces accidental overwrites.

## 29. Export History

The export page shows session export history.

History includes:

- Export time.
- Row count.
- Format.
- File size.
- Filename.
- Open file action.
- Open folder action.

This is session-only and does not persist after app close.

## 30. Audit Report

Every successful export creates a human-readable `.audit.txt` file beside the output.

Audit report includes:

- App name and version.
- Timestamp.
- Source folder.
- Reference source.
- Selected sheet.
- Layout/header/footer settings.
- Output path.
- Output format.
- Exported row count.
- Output file size.
- Save time.
- Validation summary.
- Data quality summary.
- Filter list.
- Possible duplicate source warnings.
- Included and excluded sources.

This supports internal review, troubleshooting, and management reporting.

## 31. Data Quality Summary

After combine, MergeGuru produces a lightweight data quality summary by default.

Default metrics:

- Row count.
- Column count.
- Number of included files.

Optional deeper diagnostics:

- Blank columns.
- Blank rows when dataset size is reasonable.
- Duplicate rows when dataset size is reasonable.

The deeper diagnostics are controlled by the checkbox:

`Run deeper data quality checks after combine (slower)`

Large-data guardrails:

- If deeper diagnostics are disabled, blank-row and duplicate-row scans are not run at all.
- If deeper diagnostics are enabled, blank-row scan is skipped above `500,000` rows.
- If deeper diagnostics are enabled, duplicate-row scan is skipped above `250,000` rows.

Reason:

These checks can be expensive on very large datasets and should not slow the main workflow unnecessarily. MergeGuru therefore separates critical validation from optional diagnostics.

## 32. Security Position

MergeGuru is designed as a local desktop tool.

Security characteristics:

- No cloud upload.
- No external API calls.
- No macro execution.
- No VBA.
- Source files remain in their original folder.
- Output is written only to the user-selected destination.
- Audit report is written locally beside the export.

This is materially safer than macro-based workflows in environments where macros are restricted or disabled.

## 33. Comparison With Power Query, VBA, and Macros

### Power Query

Power Query is powerful but often requires Excel-specific knowledge, refresh configuration, and workbook maintenance.

MergeGuru advantages:

- Purpose-built wizard.
- Schema validation before combine.
- Local audit report.
- Easier repeated filtered exports.
- Better handling of folders with mixed CSV/XLSX/ZIP sources.

### VBA / Macros

VBA can automate similar tasks but introduces maintainability and security concerns.

MergeGuru advantages:

- No macro security warnings.
- No code editing for users.
- More visible validation and progress.
- Less risk of hidden workbook logic.
- Easier for non-technical users to operate.

## 34. Known Limitations

Current limitations:

- Excel export cannot be cancelled once the actual `to_excel` write is underway.
- Password-protected Excel files are not processed.
- Multi-row headers are not fully merged into one schema.
- Very large CSV files are still loaded into memory during combine.
- Parquet requires optional dependency support.
- Date parsing can be ambiguous when source files mix regional date formats.

## 35. Why This Matters to Senior Management

MergeGuru reduces operational risk in recurring data consolidation work.

It improves:

- Accuracy through validation.
- Transparency through audit reports.
- Productivity through guided workflow.
- Security by avoiding macros and uploads.
- Repeatability through saved in-session combined data and export history.
- Large-data handling through memory checks, chunked export, and format recommendations.

## 36. Suggested Presentation Talking Points

- MergeGuru is a controlled local alternative to manual Excel consolidation.
- It validates files before combining, preventing silent bad merges.
- It handles common dump issues such as shuffled columns, extra columns, and report header/footer rows.
- It supports large data with memory warnings, chunked export, and Excel row-limit protection.
- It produces a human-readable audit report beside every export.
- It avoids macros, VBA, and cloud upload.
- It allows one combine operation to produce multiple filtered outputs.
