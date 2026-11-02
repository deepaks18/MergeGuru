# Record the MergeGuru showcase

**Target:** a 60–90 second recording of the committed Lite v3.1 candidate workflow using synthetic CSVs. This plan describes an implemented workflow, not a completed demo run or benchmark.

## Before capture

- Record the source revision and actual application version. The source is included on current `main`; use `main_gui_lite_v3.py` or an explicitly identified Windows build. For an executable, record its SHA-256, signature status and packaged self-test result. The latest reviewed CI run did not reach packaging, and no published GitHub Release was available at review.
- Use a disposable folder containing only the following three files. Save as UTF-8 CSV. All rows and identifiers below are invented.
- Select `01-reference.csv` as the template. Keep default required-column validation.
- Use a clean output folder outside the source folder.
- CSV-Unique text and protected-column controls are implemented in current source. Before recording, confirm that the selected build exposes these controls and select RecordID for protection.

### 01-reference.csv

```csv
RecordID,Category,Amount
000101,Wallet,100
000102,Card,200
```

### 02-reordered.csv

```csv
Amount,RecordID,Category
300,000103,Wallet
400,000104,Water
```

### 03-missing-column.csv

```csv
RecordID,Category
000105,Wallet
```

## Capture script

| Approximate edit position | On screen | Narration |
| --- | --- | --- |
| 0–10 seconds | Sources; three files; reference selected | “Three files. One has columns in a different order; another is missing Amount.” |
| 10–28 seconds | Check & Prepare; validation; accepted and excluded sources | “MergeGuru checks against a template and aligns by header name. Review the failed source before continuing.” |
| 28–48 seconds | Prepare once; Filters; search Wa; select all matches | “Prepare the accepted files once. Wa finds Wallet and Water; select both categories.” |
| 48–62 seconds | Change the filter to Wallet only; preview | “Change the subset using the prepared data.” |
| 62–90 seconds | CSV-Unique text export; protected RecordID; output and audit | “Export the subset, then reconcile the records, identifiers and audit.” |

These are editing targets, not processing-time estimates. If preparation takes longer, cut with a visible “elapsed time omitted” label. Do not imply real-time performance from edited footage. Cached re-filtering is implemented against the prepared in-memory dataframe. Describe this as source-backed behavior; footage alone does not prove the absence of source reads. Any claim about observed reads in the captured build requires instrumentation.

## Reconcile before publishing

Expected from the synthetic inputs, **not observed application results**:

| Checkpoint | Expected result |
| --- | --- |
| Source validation | Two accepted sources; missing-Amount file excluded |
| Prepared data | 4 rows; Amount total 1,000 |
| Wa category selection | Wallet + Water; 3 rows; Amount total 800 |
| Wallet-only selection | 2 rows; Amount total 400 |
| Wallet-only RecordID values | Logical identifiers 000101 and 000103. Current CSV-Unique text serialization wraps protected values in apostrophes: `'000101'` and `'000103'`. |
| Export and audit | Completed data output plus an adjacent human-readable audit file. Audit writing can fail after data export succeeds; confirm the file exists and reconcile its contents. |

Inspect the raw CSV in a text editor. Current CSV-Unique text serialization adds surrounding apostrophes to protected values; confirm that representation explicitly. Excel may reinterpret CSV values, so opening the file directly in Excel does not establish raw serialization or compatibility with every downstream tool.

If any expected result differs, stop capture, investigate and update the evidence status. Do not silently change the expected count.

## Media handoff

All assets below are **missing placeholders**. No broken image links are embedded in SHOWCASE.md.

| Future path | Required capture |
| --- | --- |
| assets/01-sources.png | Sources and selected template |
| assets/02-validation.png | Accepted reordered file and missing-column exclusion |
| assets/03-filters.png | Wa category selection; readable row count |
| assets/04-export-audit.png | Export result and audit, with identifiers checked |
| assets/mergeguru-workflow.gif | Short readable loop of the real workflow |
| assets/mergeguru-workflow.mp4 | Optional full 60–90 second version |

Use real application captures, not generated UI. Keep customer information, personal paths, account names and notifications out of public footage. Use the synthetic folder and a neutral capture account.

Once captured, insert relative media links in SHOWCASE.md and add the executable version, capture date, observed counts and whether the recording is edited. The earlier shared demo can be reused only after locating it and checking its version, privacy and shown behavior.

## Optional second cut

Show cancelling a CSV/Excel export to an existing destination and verify that the destination bytes remain unchanged. Atomic replacement and cancellation protection are implemented in current source, and local cancellation/writer-failure coverage is documented. The latest reviewed CI high-risk integrity step failed, so verify the selected build and compare destination bytes before and after cancellation. Keep this out of the primary 90-second flow unless it remains clear and readable.

Record the active v3.1 candidate and label its exact revision and build. Project presets may be shown as an optional separate segment because they are implemented in current source. If using an older Beta build, label it explicitly and exclude v3.1-only behavior.
