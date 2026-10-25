# MergeGuru Lite Usability Update

## Changes

- A progress strip above the footer stays visible while the page scrolls. It
  shows elapsed time, percentage, estimated remaining time, and a Cancel button
  during validation, combine, and export. Its timer updates twice a second using
  existing progress information; it does not reread files or scan data rows.
- An additional animated activity bar continues moving while a single large file
  is being read or written. The strip shows active filenames, distinguishes
  waiting for the first progress milestone from measured completion, and explains
  long gaps between updates. Cancellation changes the state to Stopping safely.
  Animation indicates an active operation; it does not guarantee that a file read
  is making forward progress or detect a hung worker.
- Template header reading runs in the validation worker so it no longer blocks
  the UI before progress is shown. Cancelling validation clears partial approval
  and lets the user retry. Active file reads may delay cancellation.
- Controls that could change the running operation are disabled and restored
  afterward. Performance options are frozen once data has been combined, with
  an explanation of how to apply different settings.
- Step 5 has an explicit Combine Files action. Users can choose performance
  settings before processing starts. Auto-next continues to start combine
  automatically for unattended workflows. Recommended settings and hover help
  explain memory optimization, parallel reading, and optional quality checks.
- Category filters use visible checked/unchecked rows. A single click or Space
  toggles a value; no Ctrl/Cmd combination is required. Select visible, Clear
  visible, and Invert visible leave hidden selections intact. A short summary
  shows selected values.
- Filter dialogs resize and scroll, with fixed footer actions and Escape to
  cancel. Invalid date ranges, invalid dates, and malformed filter expressions
  are rejected before a filter is saved. Date defaults use the current year and
  date instead of a hardcoded year.
- Mouse-wheel routing is scoped to each window. Lists and tables keep their own
  scrolling; nested column pickers scroll themselves; other content scrolls its
  enclosing page. Global bind_all handlers are no longer installed.
- Export paths expand to the available width. The CSV-Unique text hint sits
  below the format row, and its column picker appears directly afterward.
  Format and protected-column preferences survive navigation within the session.
- Preview supports 10, 25, or 100 rows, includes all columns, has horizontal and
  vertical scrollbars, and copies selected preview rows with column names.
  Preview uses cached combined data and does not reread sources. The first filter
  evaluation can still take time on large datasets.
- An export-state message distinguishes an unsaved result, a saved result, and
  changes since the last export. Finish checks the current data/filter state;
  a previous export does not satisfy later unsaved changes. Close Without Export
  remains beside Finish and asks for confirmation when appropriate.
- Closing the window during processing offers to cancel while leaving the window
  open until the operation stops safely. Optional automatic opening follows a
  successful export. File-check rows can be double-clicked for remediation and
  expandable technical detail.
- Keyboard shortcuts: Ctrl+O browses for a folder on Step 1; Alt+N advances when
  permitted; Alt+B goes back; Escape closes a filter dialog; Ctrl+C copies
  selected preview rows.

## Verification

The automated hidden-window check in tools/lite_ux_check.py covers validation
cancellation/retry, explicit combine and settings states, category selection
persistence, invalid date ranges, full-width preview/copy, minimum-size footer
layout, protected-column placement/preferences, current-result save state, and
activity animation during long periods without a progress milestone.

The focused 29-test data-integrity regression suite remains applicable. Hidden
widget checks do not certify visual appearance, screen-reader support, every
display scale, or multi-GB performance. The subsequent stability pass verified
packaged Lite initialization and exports on this development machine; it does
not replace a clean-machine startup check.

These interface changes apply to Lite. The shared engine and Pro interface retain
the preceding integrity fixes. Lite has now been rebuilt and its packaged
self-test passed; Pro has not been rebuilt. See STABILITY_PASS_REPORT.md for
the cancellation, precision and export-recovery fixes and remaining rollout checks.
