# MergeGuru Lite Workflow Prototype

This is an isolated, interactive design preview, not a production replacement.
It uses 18 generated sample rows and three fictitious file names. No real source
files are opened, and no export, audit, preference or history file is written.
Task duration, progress and ETA are simulated, not performance measurements.

## Run

Double-click `run_lite_prototype.cmd` in the project root, or run:

```powershell
.\.venv\Scripts\python.exe main_gui_lite_prototype.py
```

Only Python's standard library and Tkinter are needed. The launcher uses the
existing project environment; this is not yet a separate portable EXE.
Production `main_gui.py`, its theme, engine, build spec and release EXE are not
modified or imported by this prototype.

## Design Direction

- Brand-aligned workbench based on the supplied Merge-M concept board: icy-white
  surfaces, deep-navy header, royal-blue actions, cyan progress accents and a
  two-tone wordmark with MERGE. VALIDATE. EXPORT. Separate sans-serif title,
  section, body and caption scales. Warnings remain amber, success remains green
  and the template star remains gold to preserve meaning.
- The compact header mark and window icon are a code-native interpretation, not an extracted
  official logo. The prototype adds no imaging/theme dependencies and does not
  load the Downloads image at runtime. Before release, use the designer's clean
  master SVG or transparent PNG for the final logo and app icon. Brand colors
  are interpreted from the supplied board, not an official color specification.
- Four stages instead of six: Sources, Check & Prepare, Filters, Export.
  Template choice sits next to source selection. Validation and combining share
  a preparation stage, with distinct simulated progress phases.
- Compact branding and quiet step navigation leave more room for data. Each step
  has a visible state/reason, and the fixed footer explains the next action or
  why it is unavailable. The sample-data disclaimer remains in the header.
- Source selection, template marking, exclusion and an expandable selected-file
  preview share one panel. Optional performance settings are collapsed by default
  and retain their expanded state; recommended settings can be restored together.
- Filters and result preview sit side by side when their workspace is at least
  900 pixels wide, and stack below that width without rebuilding controls.
  Export settings and preview use the same pattern. No settings are lost on resize.
- Navigation, progress/elapsed/ETA and Cancel stay outside the scrolling content.
  Settings and navigation are locked while a demo operation is active. A stopping
  state precedes cancellation completion. Idle status is compact; the progress
  bar/details/cancel controls appear during processing. Preparation shows a file
  counter; simulated export identifies the intended output, not a source file.
- Different worksheet names, extra columns and header/footer settings have inline
  explanations. Header/footer row fields only appear when the option is checked.
- Searchable category checkboxes, editable filter strips and an immediate sample
  preview. Prefix search is case-insensitive by default; Contains is optional.
  Select matches, Clear matches and Invert affect all search matches, preserving
  values outside that search. Include/Exclude selected values controls whether
  the checked group is kept or removed. Search and action controls stay outside
  the scrolling list; Apply/Cancel stay at the fixed dialog footer.
- The filter dialog previews the matching sample-row count before Apply, including
  other active filters. Apply is explicit; cancelling does not change the result.
  Undo restores the last filter add/edit/remove/clear in the current prepared-data
  session. Source/layout changes clear that undo snapshot.
- Category rendering starts at 250 values with Show more, rather than creating
  thousands of checkbox widgets. Bulk actions include not-yet-rendered matches.
  The selection count, hidden-selection count and sample of checked values make
  it explicit what will be applied. No source reread is needed for search.
- CSV-Unique text column choices appear immediately under the format selector.
  Format and text-column preferences survive navigation within this session.
- Preview row limits are 5, 10 or 25 and survive page navigation. Preview rows
  can be selected and copied with column names using the button or Ctrl+C;
  changing the preview limit does not limit the export. Preview remains synthetic.
- Explicit saved/unsaved state, Close without export beside Finish, sample export
  history, and another export with an incremented name and no sample-data reload.
- Closing with an unsaved prepared result asks for confirmation on Filters as
  well as Export. A filter referencing a removed column shows remediation and
  blocks output; it is not silently ignored, including in exclusion mode.

## Keyboard Behaviour

- Alt+N advances/runs the primary action when permitted; Alt+B goes back.
- Ctrl+F opens a filter on the Filters page, or focuses search in its dialog.
- Enter/Down from value search focuses the matches; Space toggles a focused value.
- Ctrl+Enter applies a filter; Escape cancels its dialog without applying edits.
- Enter activates focused buttons and sets the template from a selected source row.
- Ctrl+C in a result preview copies selected rows with headers.

These are tested interaction paths, not a complete screen-reader audit.

## Suggested Review Journey

1. Choose a template and exclude/restore a sample source.
2. Enable header/footer handling, then turn it off to see the fields disappear.
3. Start preparation, cancel, retry and continue to Filters.
4. Add a filter, choose Branch, and type Wa. Select matches to check Waltham,
   Walnut Creek, Watford and Waverley. Include selected keeps 12 sample rows;
   Exclude selected keeps the other six. Try changing searches, clearing/inverting
   matches and editing the saved filter; selections outside the search stay kept.
5. Select CSV-Unique text and choose Customer ID directly below the format.
6. Simulate export, then change filters and export again using retained data.
7. Try a 720 x 560 window: scroll page content while the footer/progress stays put.
8. Close with an unsaved result and choose Keep working.

## Boundaries and Next Phase

This is not feature parity: there is no real folder/file picker, engine execution,
disk export, actual memory check, real error classification, persistent settings,
audit generation or output-opening action. The sample settings demonstrate UI
visibility/state invalidation; they do not parse worksheets or scan quality.
The model does not implement the production engine's matching/schema semantics.

After workflow approval, adapt the prototype to the shared engine using a
background-task controller. Keep engine logic in `mergeguru_engine.py` so Lite
and Pro continue to share processing behavior. Re-run integrity/recovery suites
and add real-data integration tests before any release migration.

## Checks

```powershell
.\.venv\Scripts\python.exe tools\lite_prototype_check.py
```

This checks the sample model plus mapped Tk windows. It briefly shows the test
window, checks three window sizes and uses synthetic tasks. It is not a benchmark,
accessibility certification or validation at every Windows DPI setting.

Workspace refinement verification: 37 tests passed (three brand/color tests, eight
sample-model tests, five selection-model tests and 21 window tests), covering
720 x 560, 900 x 640 and 1060 x 780 layouts. Filter checks cover prefix/contains
matching, include/exclude results, hidden-selection persistence, editing, empty
matches, blank values, mode/column switching and fixed actions in a 420 x 500
dialog. Additional checks cover wide/stacked workspaces, source preview, advanced
settings, recommendations, undo, draft result counts, preview limits and copied
rows, idle/active progress layout, checkbox wrapping, keyboard selection and
unsaved-close confirmation before Export. Clipboard calls are mocked in tests
so tests do not overwrite the user's clipboard. A 20,000-value synthetic
fixture verifies paged rendering and that bulk
selection includes all 10,000 matched values. This is not a production-data
benchmark. Color/layout checks cover text/background contrast targets, gradient
endpoints, distinct semantic colors and header fit. Syntax compilation passed;
no Tk callback errors were recorded. Production Lite's EXE remains unchanged.

The initial branded Sources screen was inspected using a live screenshot. A
subsequent live Preparation-screen review of the compact refinement caught an
initial checkbox-wrap issue; it was fixed and given a regression test. The review
window was unavailable on the later refresh, so a complete visual review of every
refined screen was not completed. Display scales, screen readers, real-data
processing and usability with representative end users still need separate
review. Automated layout/color checks are not an accessibility certification.
