# MergeGuru
### From scattered files to a reviewable dataset.

**Sources → Check & Prepare → Filters → Export**

A desktop workflow for analysts who repeatedly consolidate operational files: choose a reference, review structural issues, prepare accepted sources once, and reuse the prepared data for filtering and export.

> **Evidence status — 3 November 2026:** Current `main` at `bfbcdec` contains the active Lite v3.1 candidate source, build configuration and automated checks. The workflow below is grounded in committed implementation. `PRODUCTION_READINESS.md` records local source, generated-load and frozen self-test results. The latest reviewed GitHub Actions run passed engine integration, health and Lite regression checks, then failed high-risk integrity checks; source self-test, executable build and packaged self-test were skipped. Current-build screenshots, a recording and observed results for this demo remain pending.

[Demo capture plan and synthetic fixtures](docs/demo/CAPTURE_PLAN.md)

## Watch the workflow

<table>
<tr><td><strong>01 · Select</strong><br>Choose sources and the reference template.</td><td><strong>02 · Check</strong><br>Inspect validation and align columns by header name.</td></tr>
<tr><td><strong>03 · Refine</strong><br>Change filters against prepared data.</td><td><strong>04 · Review</strong><br>Export, then inspect the output and audit.</td></tr>
</table>

> **GIF / VIDEO PLACEHOLDER — recording not attached**  
> Capture a 60–90 second run using synthetic data. Suggested future asset: `docs/demo/assets/mergeguru-workflow.gif`. No playable demo is claimed here.

| Screenshot slot | What the real capture should show | Status |
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
5. Export CSV-Unique text with RecordID protected; inspect the serialized identifiers and confirm that the adjacent `.audit.txt` file was written. Export completion alone does not establish audit creation.

This sequence demonstrates correctness, iteration, and reviewability. It does not depend on an unmeasured speed claim. The capture plan supplies exact synthetic inputs and expected counts.

## Compared with manual Excel merging

| Task | Manual copy/paste in Excel | Implemented Lite v3.1 workflow |
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
| Source discovery, validation, normalized-header alignment, cached re-filtering and category selection | Implemented in the committed Lite UI and shared engine. Current CI passed engine integration and Lite regression checks; the proposed demo has not been recorded or reconciled. |
| CSV, CSV-Unique text, Excel and Parquet export; protected columns; Excel Validation Report | Implemented in committed source. Excel round-trip coverage is documented and the current CI engine integration check passed. This does not establish representative acceptance for every format. |
| Atomic output replacement, cancellation protection, source-change detection and filter-failure handling | Implemented in source. Production-readiness documentation reports local integrity/recovery coverage, but the latest reviewed CI high-risk integrity step failed. Do not describe the full current CI gate as passing. |
| Human-readable export audit | Implemented as a separate write after data export. Audit failure produces a warning and does not undo the completed data export. Confirm both files in the demo. |
| Project presets and local support diagnostics | Present in the current v3.1 source; optional for this core demo. Their appearance and operation in the selected recording build still require confirmation. |
| Build and packaged verification | Build configuration and CI packaging/self-test steps are committed. An isolated frozen candidate pass is documented locally; the latest reviewed CI run skipped packaging and packaged self-test. No published GitHub Release was available at review. |
| Recording, installation acceptance, signing and deployment readiness | Current-build visual proof, representative workload acceptance, clean managed-device testing, signature verification and organizational approvals remain separate release gates. |
| Earlier product-demo video | Not supplied or assessed in this review. Reuse requires checking its version, privacy and shown behavior. |

The active source is the Lite v3.1 candidate, identified by `README.md` and `PRODUCTION_READINESS.md`. The documented decision is controlled internal evaluation, with wider rollout subject to the listed acceptance and approval gates. Historical Beta and preview results provide background; they do not establish a passing current CI run, a signed distributable or current visual proof.

## Built around a BI problem

> I built MergeGuru to make recurring file consolidation easier to inspect: select sources, validate against a template, prepare once, then filter and export with an audit trail. This showcase describes the committed Lite v3.1 implementation. A current-build recording and representative real-volume acceptance results remain pending.

**Scope:** Local desktop consolidation and filtering. The committed application has no upload or telemetry feature. Prepared data is held in memory, preview is bounded, and deep duplicate/blank-row scans are off by default. Do not claim unlimited scale, automatic deduplication or guaranteed performance on company workloads.

<details>
<summary>Evidence provenance</summary>

Reviewed against PR head `ca21667` and current `main` `bfbcdec` on 3 November 2026:

- [README.md](https://github.com/deepaks18/MergeGuru/blob/bfbcdec474dfdb3a994c08ab8a3741af7a4b5fad/README.md) — canonical application, workflow, export formats and data-safety boundaries.
- `mergeguru_lite_v3/` and `mergeguru_engine.py` on the reviewed main revision — implemented workflow, filtering, export and audit behavior.
- [PRODUCTION_READINESS.md](https://github.com/deepaks18/MergeGuru/blob/bfbcdec474dfdb3a994c08ab8a3741af7a4b5fad/PRODUCTION_READINESS.md) — documented local verification and remaining rollout gates.
- [.github/workflows/mergeguru-ci.yml](https://github.com/deepaks18/MergeGuru/blob/bfbcdec474dfdb3a994c08ab8a3741af7a4b5fad/.github/workflows/mergeguru-ci.yml) — configured Windows source, packaging and self-test gates.
- [GitHub Actions run 40211464982](https://github.com/deepaks18/MergeGuru/actions/runs/40211464982) — partial source-check success, high-risk integrity failure and skipped packaging steps.

Historical Beta QA and v3.1 preview records remain background evidence and are now committed on `main`. No current-build recording was assessed. This review inspected source and recorded results; it did not rerun the application or tests.

</details>
