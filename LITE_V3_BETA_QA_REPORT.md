# MergeGuru Lite v3 Beta - QA Record

Date: 4 October 2026

## Decision

The functional Beta is ready for a controlled user pilot. It is not yet approved
to replace the stable v2.4 Lite executable.

## Automated Result

`12/12` checks passed in `tools/lite_v3_beta_check.py`.

Coverage includes:

- One continuous mapped Tk session at 720x560, 900x640, and 1060x780.
- Visible sticky progress, cancel, safe cancellation, and retry in the same session.
- Real source discovery and combine using temporary CSV fixtures.
- Shuffled-column alignment and accepted extra-column append behavior.
- Searchable category picker: `Wa` returns and bulk-selects all matching values.
- Bounded category scanning above 20,000 unique values.
- Cached re-filtering without source rereads and mask-only draft counts.
- CSV-Unique text preservation, validation report construction, and text audit.
- Atomic cancellation preserving an existing destination.
- Preference persistence excluding filters and source names.
- Stable v2.4 executable checksum protection.

## Packaging Result

- Candidate: `editions_dist/beta/MergeGuru_Lite_v3_Beta.exe`
- Size: `66,586,776` bytes (`63.50 MiB`)
- SHA-256: `6A24A4F6AA62DD5E41B992A95DDB81C69485038233A9BDEAD91B7C69C82D3EF4`
- Startup smoke: passed; one responsive child window was present with title
  `MergeGuru Lite | v3.0 Beta` after the branded splash handoff.
- PyInstaller included pandas, openpyxl, pyarrow, psutil, and Tk. Its only named
  hidden-import warning was optional `jinja2`; the Beta does not use pandas Styler.

## Rollback Protection

- Stable executable: `editions_dist/lite/MergeGuru_Lite.exe`
- Stable SHA-256:
  `7463A0662AEC0C90C3F2183E6822EC0823D860D303866EA9D207A2F7A29BCD4F`
- The stable source, build spec, and EXE were not modified by the Beta work.

## Pilot Exit Criteria

1. Complete representative tests with CSV, Excel, ZIP, dated worksheet names,
   header/footer corrections, extra columns, and at least one large folder.
2. Confirm output row counts, protected text IDs, validation worksheet, and audit
   text with business users.
3. Record startup/combine/export timings and peak memory on target laptops.
4. Resolve pilot defects, rerun stable plus Beta regression checks, and sign the
   final executable before any production replacement.

The Windows automation service could not enumerate the source-launched Tk window
for screenshot capture in this session. Layout was therefore verified through
mapped-window geometry assertions rather than a screenshot-based visual sign-off.
