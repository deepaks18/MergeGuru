#!/usr/bin/env python3
"""Headless workflow/state check for MergeGuru Pro."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import mergeguru_engine as engine  # noqa: E402
from main_gui_pro import FilterDialog, MergeGuruPro  # noqa: E402


def main():
    work = Path(tempfile.mkdtemp(prefix="mergeguru_pro_"))
    app = QApplication.instance() or QApplication([])
    try:
        settings = QSettings("MergeGuru", "MergeGuru Pro")
        for key in [
            "pref_auto_match_sheet",
            "pref_layout_fix",
            "pref_header_row",
            "pref_footer_rows",
            "pref_allow_extra",
            "pref_fast_combine",
            "pref_optimize_memory",
            "pref_export_format",
        ]:
            settings.remove(key)
        reference = work / "reference.csv"
        second = work / "second.csv"
        pd.DataFrame(
            [
                {"id": 1, "region": "South", "amount": 100},
                {"id": 2, "region": "North", "amount": 200},
            ]
        ).to_csv(reference, index=False)
        pd.DataFrame(
            [
                {"amount": 300, "region": "South", "id": 3},
                {"amount": 400, "region": "West", "id": 4},
            ]
        )[["amount", "region", "id"]].to_csv(second, index=False)

        window = MergeGuruPro()
        window.source_folder = str(work)
        window._discover([str(reference), str(second)])
        assert len(window.sources) == 2
        assert window.next_button.isEnabled()
        assert window.max_unlocked_step == 1
        assert not window._can_enter(2), "future steps must remain locked"
        window.sources_table.item(1, 0).setCheckState(Qt.Unchecked)
        assert len(window._included_sources()) == 1
        window.sources_table.item(1, 0).setCheckState(Qt.Checked)
        assert len(window._included_sources()) == 2
        assert window.sources_table.cellWidget(0, 1).isChecked()
        window._set_reference_row(1)
        assert window.reference_index == 1
        assert window.sources_table.cellWidget(1, 1).isChecked()
        window._set_reference_row(0)
        assert window.reference_index == 0
        assert not window.filter_section_buttons[1].isEnabled()

        window._next()
        window._next()
        assert window.current_step == 2
        assert window._reference_ready()
        assert "reference.csv" in window.reference_summary_source.text()
        assert window.layout_options.isHidden()
        window.layout_fix.setChecked(True)
        assert not window.layout_options.isHidden()
        window.layout_fix.setChecked(False)
        assert window.layout_options.isHidden()
        signature = window._current_validation_signature()
        settings = {
            "reference_index": 0,
            "reference_source": window.sources[0],
            "selected_sheet": None,
            "header_row": 1,
            "footer_rows": 0,
            "allow_extra": False,
        }
        validation = engine.validate_sources(window.sources, 0)
        window._validation_done(validation, signature, settings)
        assert window.validation is not None
        assert window._can_enter(4)
        assert window.validation_pass_chip.text() == "2 PASS"

        window.header_row.setValue(2)
        window.layout_fix.setChecked(True)
        assert window.validation is None, "layout change must invalidate validation"
        assert window.final_df is None

        window.layout_fix.setChecked(False)
        signature = window._current_validation_signature()
        validation = engine.validate_sources(window.sources, 0)
        window._validation_done(validation, signature, settings)
        combined, extras, memory = engine.combine_sources(
            validation["passed_sources"],
            window.sources[0],
            validation["reference_columns"],
            optimize_memory=True,
        )
        window._combine_done((combined, extras, memory))
        assert window.final_df is not None
        assert window.add_filter_button.isEnabled()
        assert window.filter_section_stack.currentIndex() == 1
        assert window.filter_section_buttons[2].isEnabled()
        assert "Format:" in window.export_readiness.text()
        assert window.unique_column.isHidden()
        window.export_format.setCurrentText("CSV-Unique text")
        assert not window.unique_column.isHidden()
        assert window.unique_column.count() >= 2
        window.unique_column.item(0).setSelected(True)
        window.unique_column.item(1).setSelected(True)
        assert len(window._selected_unique_columns()) == 2
        window.export_format.setCurrentText("Excel")
        assert window.unique_column.isHidden()

        window._push_filter_history()
        window.filters = [{
            "column": "region",
            "mode": "text",
            "operator": "equals",
            "value": "South",
        }]
        window._apply_filters()
        assert len(window.filtered_df) == 2
        assert window.filters_table.rowCount() == 1
        assert window.preview_model.rowCount() == 2
        assert window.undo_button.isEnabled()
        window._undo_filters()
        assert len(window.filters) == 0
        window._redo_filters()
        assert len(window.filters) == 1
        assert window._can_enter(5)

        date_dialog = FilterDialog(
            list(window.final_df.columns),
            window.final_df.assign(report_date="2026-01-01"),
            parent=window,
        )
        date_dialog.mode.setCurrentIndex(date_dialog.mode.findData("date"))
        assert date_dialog.date1.calendarPopup()
        date_dialog.close()

        window._show_step(5)
        window.allow_extra.setChecked(True)
        assert window.validation is None
        assert window.current_step == 3
        assert window.attention_step == 3
        assert not window.toast.isHidden()
        print(f"pro workflow check ok: {work}")
        window.source_folder = ""
        window.last_export_folder = ""
        window.close()
    finally:
        app.processEvents()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
