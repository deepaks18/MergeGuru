# MergeGuru
### From scattered files to a reviewable dataset.

**Sources → Check & Prepare → Filters → Export**

A desktop workflow for analysts who repeatedly consolidate operational files: choose a reference, review structural issues, prepare accepted sources once, and reuse the prepared data for filtering and export.

> **Evidence status — 19 October 2026:** This showcase describes the documented Lite v3 Beta workflow. The historical QA record reports 12/12 checks passed on 4 October 2026 using temporary CSV fixtures. No application source, executable, or recording was present in the inspected repository tree. These are documented capabilities, not a fresh test of this repository.

[Demo capture plan and synthetic fixtures](docs/demo/CAPTURE_PLAN.md)

## Watch the workflow

<table>
<tr><td><strong>01 · Select</strong><br>Choose sources and the reference template.</td><td><strong>02 · Check</strong><br>Inspect validation and align columns by header name.</td></tr>
<tr><td><strong>03 · Refine</strong><br>Change filters against prepared data.</td><td><strong>04 · Review</strong><br>Export, then inspect the output and audit.</td></tr>
</table>

> **GIF / VIDEO PLACEHOLDER — recording not attached**  
> Capture a 60–90 second run using synthetic data. Suggested future asset: `docs/demo/assets/mergeguru-workflow.gif`. No playable demo is claimed here.

| Screenshot slot | What the real capture should prove | Status |
| --- | --- | --- |
| Sources | Selected files and reference template | **PLACEHOLDER — capture needed** |
| Check & Prepare | Reordered columns accepted; missing required column excluded | **PLACEHOLDER — capture needed** |
| Filters | Category selection and changed result after preparation | **PLACEHOLDER — capture needed** |
| Export and audit | Reconciled output, text identifier, audit file | **PLACEHOLDER — capture needed** |

These are capture slots, not simulated application screenshots. Add real images only after checking the recorded build and output.

## The strongest demo: one preparation, several views

1. Select three small CSV files and make the first the template.
2. Show that reordered columns align by normalized header name, while a source missing a required column is excluded.
3. Prepare the accepted sources. Search categories with `Wa`, select matching values, and preview the result.
4. Change the filter without another source read.
5. Export CSV-Unique text; inspect the leading-zero identifier and the adjacent `.audit.txt` file.

This sequence demonstrates correctness, iteration, and reviewability. It does not depend on an unmeasured speed claim. The capture plan supplies exact synthetic inputs and expected counts.

## Compared with manual Excel merging

| Task | Manual copy/paste in Excel | Documented Lite v3 workflow |
| --- | --- | --- |
| Consolidate files | Open files and append rows; review headers yourself | Select sources, choose a template, validate, then combine |
| Reordered columns | Reorder or map columns before appending | Align by normalized header name |
| Revisit a subset | Filter the consolidated sheet | Re-filter the cached prepared data |
| Explain exclusions | Maintain your own reconciliation notes | Review failed-source validation and the export audit |
| Choose the tool | Practical for a small, one-off task | Designed around a recurring consolidation workflow |

Excel Power Query can also automate consolidation. This comparison concerns manual copy/paste, not Excel's full capabilities. No measured time savings, error reduction, or superiority over Power Query is established.

## What is supported by evidence?

| Capability or claim | Evidence and boundary |
| --- | --- |
| Source discovery/combine; shuffled-column alignment; cached re-filtering; `Wa` category selection | Covered in the historical 4 October Beta QA record using CSV fixtures |
| CSV-Unique text preservation; validation/audit construction; cancellation preserving an existing destination | Covered in that same historical QA record; not rerun here |
| Excel export with a Validation Report worksheet; CSV, Excel and Parquet export options | Described in the Beta workflow notes; representative format testing remained a pilot exit criterion |
| Project presets and local support diagnostics | Described in the separate 6 October v3.1 preview notes; keep outside the core Beta demo until the recorded build is confirmed |
| Current downloadable build, supported installation, signing, performance and company-file reliability | **Needs confirmation**; no release or production-readiness claim |
| Prior product-demo video | Mentioned in project context, but a usable recording was not located for this package |

The Beta QA record recommended a controlled pilot and did not authorize replacement of stable v2.4. Later v3.1 preview notes refer to a verified v3.0 production executable and 17/17 preview regression checks; they do not identify which application version, if any, is committed here. The preview was unsigned. Neither historical result establishes current repository readiness.

## Built around a BI problem

> I built MergeGuru to make recurring file consolidation easier to inspect: select sources, validate against a template, prepare once, then filter and export with an audit trail. This showcase follows the documented Lite workflow; a current-build recording and reproducible benchmark are still pending.

**Scope:** Desktop consolidation and filtering. The Beta notes describe local processing without automatic data transfer. They also state that deep duplicate/blank-row scans are off by default, preview is bounded, and prepared data is held in memory. Do not present this as unlimited-scale processing or automatic deduplication.

<details>
<summary>Evidence provenance</summary>

Reviewed project records supplied before this repository change:

- `LITE_V3_BETA_README.md` — workflow, export behavior and deliberate guardrails.
- `LITE_V3_BETA_QA_REPORT.md`, 4 October 2026 — 12/12 historical checks, pilot criteria and screenshot-sign-off limitation.
- `MERGEGURU_LITE_V3_1_PREVIEW_NOTES.md`, 6 October 2026 — separate preview status, project presets, diagnostics and unsigned candidate.

These records were reviewed outside this repository; the filenames are provenance labels, not download links. Repository root and open pull requests were inspected on 19 October 2026: only the original README was present and no open PR was returned. README content is outside this package's scope.

</details>
