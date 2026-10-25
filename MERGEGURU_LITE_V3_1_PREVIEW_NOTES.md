# MergeGuru Lite v3.1 Preview

Preview date: 6 October 2026

## Status

This is a separate controlled-deployment candidate. It does not replace the
verified v3.0 executable at `editions_dist/lite/MergeGuru_Lite.exe` until a new
packaged build completes the release gates in `PRODUCTION_READINESS.md`.

## Project Presets

- Save an explicit `.mergeguru.json` project from the Sources page.
- Restore source locations, reference template, exclusions, worksheet/layout
  rules, performance settings, filters, export format, protected text columns,
  and the preferred output directory.
- Reopen folder-based projects against the folder's current supported files.
- Revalidate and recombine every source after opening; prepared data is never
  embedded in or trusted from a project file.
- Restore filters only after a successful fresh preparation and skip filters
  whose columns are no longer available.
- Ignore outputs recorded in the project so a previous MergeGuru CSV is not
  accidentally re-imported from the source folder.
- Validate project schema, types, sizes, operations, and safe limits before use.

Project files contain local paths and filter criteria, which can themselves be
sensitive. They contain no source rows and are created only when the user
explicitly saves one.

## Privacy-Safe Diagnostics

- Maintain a bounded local operational log with task names, durations, counts,
  and error classes.
- Rotate the local log at 512 KB.
- Save a human-readable support report from the Sources page or technical-detail
  dialog.
- Exclude source filenames, filesystem paths, worksheet names, column names,
  filter values, and source/output data from the support report.
- Never upload or transmit diagnostics automatically.

## Code-Signing Readiness

- `tools/sign_windows_release.ps1` discovers SignTool and valid code-signing
  certificates without changing any file when run with `-CheckOnly`.
- Signing requires an explicit certificate thumbprint and organization-provided
  RFC 3161 timestamp URL.
- The script preserves the unsigned candidate, signs a temporary copy with
  SHA-256, verifies Authenticode, and commits a separate signed artifact only
  after verification succeeds.
- This development machine currently has no SignTool installation and no usable
  code-signing certificate. The preview therefore remains unsigned.

## HD Branding

- Replaced the 34-line Tk canvas mark with a supersampled Pillow/ImageTk mark.
- Added a transparent `1024 x 1024` logo master and `1600 x 400` brand lockup.
- Rebuilt every ICO resolution from the 1024px master.
- Rebuilt the splash at `720 x 360` from a supersampled composition, retaining a
  compact launch size while improving edges and text clarity.
- Enabled Windows DPI awareness before the Tk window is created to prevent
  bitmap scaling on high-DPI displays.

## Source Selection Polish

- Highlighted `Use as template` with a bright brand-amber star treatment when
  exactly one source file is selected.
- Kept the action visibly muted while unavailable so users can distinguish its
  state from an actionable template choice.

## Verification

- Automated Lite workflow checks: `21/21` passed in the current source.
- High-risk integrity checks: `29/29` passed in the current source.
- Shared-engine Excel round-trip and canonical health checks: passed.
- Generated-data load suite: all 9 stages passed, including 1,000,000-row CSV
  combine and 50,000-row streamed Excel round-trip.
- Frozen packaged self-test: all 8 checks passed.
- FileVersion/ProductVersion: `3.1.0-preview`.
- QA candidate path: `work/release_gate_build_20261011/dist/MergeGuru_Lite_v3_1_Preview.exe`.
- Candidate size: `67,722,680` bytes.
- Candidate SHA-256:
  `2C230655CCA72F7FC054127D86675A8E1270229A8EC870789BAFD3726811743F`.
- This QA candidate has not been promoted or code-signed.
- v3.0 production and v2.4 rollback artifacts remain unchanged.
