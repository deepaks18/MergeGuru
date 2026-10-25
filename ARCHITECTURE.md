# MergeGuru Architecture

## Source Of Truth

The current Lite application has three primary layers:

| Layer | Location | Responsibility |
|---|---|---|
| Launcher | `main_gui_lite_v3.py` | Normal startup and packaged `--self-test` routing |
| Lite UI | `mergeguru_lite_v3/` | Wizard pages, user state, dialogs, progress, preferences, projects, and reports |
| Shared engine | `mergeguru_engine.py` | Discovery, validation, reading, alignment, filtering, combining, and export |

`main_gui.py` is a compatibility boundary. Every direct execution, including
`--self-test`, delegates to the canonical launcher. Older definitions remain
available only when the module is imported by historical checks or the Pro
source. It is not the preferred location for new Lite behavior.

## Processing Flow

1. Discovery creates source descriptors for supported files and ZIP members.
2. Validation reads headers using the selected layout rules and compares
   normalized names with the reference schema.
3. A validation snapshot records stable source keys and file metadata.
4. Combine rereads accepted sources, verifies their metadata, aligns columns by
   normalized name, and publishes the combined frame only on success.
5. Filters operate on the cached combined frame so repeated exports do not
   reread unchanged source files.
6. Export writes a temporary sibling file, verifies cancellation, and atomically
   replaces the destination only after completion.

## Excel Export

Excel output is written directly with XlsxWriter in `constant_memory` mode. Rows
are emitted in order from `DataFrame.itertuples()` rather than through Pandas'
column-oriented Excel writer, avoiding the incomplete-sheet risk of combining
Pandas `to_excel()` with XlsxWriter constant-memory mode.

The writer disables formula and URL conversion for source strings, supports
ZIP64 workbooks, reports bounded progress, and can append a Validation Report
sheet. Excel's hard limits are checked before the background export starts.

## Integrity Boundary

Source-change detection uses path/member identity plus file size and high-
resolution modification/creation timestamps. This is fast and catches ordinary
edits, replacements, and truncation between validation and combine. It is not a
cryptographic content proof and must not be described as one.

Adding full-file hashing would reread every source and materially increase I/O
for multi-gigabyte jobs. If an audit policy requires cryptographic provenance,
it should be introduced as an explicit opt-in mode with measured performance.

## Packaging And Tests

`MergeGuru_Lite.spec` packages the canonical launcher. The Windows CI workflow
runs source integration and high-risk suites, builds the EXE, then invokes its
synthetic `--self-test`. Historical release folders remain evidence for their
specific binaries; changing source does not update an already-built EXE.
