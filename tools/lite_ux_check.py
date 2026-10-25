"""Hidden-window integration checks for Lite workflow and interaction states."""

import sys
import tempfile
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main_gui as lite
import mergeguru_engine as engine


def wait_idle(app):
    expired = []
    def poll():
        if not app._operation_running:
            app.quit()
        else:
            app.after(30, poll)
    def timeout():
        expired.append(True)
        app.quit()
    timer = app.after(15000, timeout)
    app.after(30, poll)
    app.mainloop()
    app.after_cancel(timer)
    app.update()
    assert not expired, "Operation did not finish within the fixture timeout"


def main():
    app = lite.MergeGuruApp()
    app.withdraw()
    callback_errors = []
    app.report_callback_exception = lambda *args: callback_errors.append(args)
    checks = []
    def checkpoint(message):
        print(message, flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix="mergeguru_lite_ux_") as directory:
            folder = Path(directory)
            path = folder / "source.csv"
            data = pd.DataFrame({"id": ["001", "002", "003"], "region": ["East", "West", "East"],
                                 **{f"extra_{i}": [i, i + 1, i + 2] for i in range(10)}})
            data.to_csv(path, index=False)
            app.folder = directory
            app.all_sources = engine.discover_sources([str(path)])[0]
            app.nav_to(1)
            app.nav_to(2)
            app.nav_to(3)
            checkpoint("Checking activity during a long file read...")
            app._set_operation_running(True, "file check")
            app._operation_file_activity("fixture", "huge_dump.xlsx", True)
            before = float(app._operation_activity.cget("value"))
            app.after(700, app.quit)
            app.mainloop()
            assert float(app._operation_activity.cget("value")) != before
            assert "Working" in app._operation_title.cget("text")
            assert "Waiting for progress" in app._operation_title.cget("text")
            assert "huge_dump.xlsx" in app._operation_caption.cget("text")
            app._note_operation_progress(40)
            app._operation_last_progress -= 20
            app.after(550, app.quit)
            app.mainloop()
            assert "40% completed" in app._operation_title.cget("text")
            assert "several minutes" in app._operation_caption.cget("text")
            app._cancel_active_operation()
            app.after(550, app.quit)
            app.mainloop()
            assert "Stopping safely" in app._operation_title.cget("text")
            app._set_operation_running(False)
            assert not app._operation_strip.winfo_manager()
            assert not app._operation_files
            checks.append("Activity animates without new milestones and distinguishes cancellation")
            checkpoint("Checking validation cancellation...")
            app._run_validation()
            assert app._operation_strip.winfo_manager() == "pack"
            assert str(app._btn_next.cget("state")) == "disabled"
            app._cancel_active_operation()
            wait_idle(app)
            assert not app.passed_srcs
            assert str(app._btn_next.cget("state")) == "disabled"
            assert not app._operation_strip.winfo_manager()
            checks.append("Validation cancellation clears approval and restores controls")

            app._run_validation()
            wait_idle(app)
            assert len(app.passed_srcs) == 1
            app.nav_to(4)
            checkpoint("Checking combine settings...")
            assert app.final_df is None
            assert str(app._combine_start_btn.cget("state")) == "normal"
            app._recommended_performance()
            assert app._optimize_memory_var.get()
            assert not app._fast_combine_var.get()
            assert not app._deep_quality_var.get()
            with patch.object(lite, "check_memory_before_combine", return_value=(True, "", 8, 1)):
                app._start_combine()
                assert str(app._combine_start_btn.cget("state")) == "disabled"
                wait_idle(app)
            assert len(app.final_df) == 3
            assert str(app._add_filter_btn.cget("state")) == "normal"
            assert all(str(w.cget("state")) == "disabled" for w in app._advanced_body.winfo_children()
                       if isinstance(w, (tk.Checkbutton, tk.Button)))
            checks.append("Explicit combine uses selected settings and freezes applied options")

            with patch.object(tk.Toplevel, "wait_window"), patch.object(tk.Toplevel, "grab_set"):
                dialog = lite.FilterDialog(app, ["region"], app.final_df, lambda config: None)
            dialog.withdraw()
            dialog.cat_listbox.focus("0")
            dialog._toggle_category_row(SimpleNamespace(keysym="space"))
            assert dialog._persistent_selection == {"East"}
            dialog.cat_search.insert(0, "West")
            dialog._apply_category_filter()
            dialog._cat_select_all(True)
            assert dialog._persistent_selection == {"East", "West"}
            dialog._cat_select_all(False)
            assert dialog._persistent_selection == {"East"}
            dialog.cat_search.delete(0, "end")
            dialog._apply_category_filter()
            assert dialog.cat_listbox.item("0", "values")[0] == "[x]"
            dialog._cleanup()
            checks.append("Category toggles preserve hidden selections across searches")
            checkpoint("Checking date validation...")

            added = []
            with patch.object(tk.Toplevel, "wait_window"), patch.object(tk.Toplevel, "grab_set"):
                dialog = lite.FilterDialog(app, ["region"], app.final_df, added.append)
            dialog.withdraw()
            dialog.mode_var.set("date")
            dialog._refresh()
            dialog.date_op.set("between")
            dialog._toggle_date2()
            dialog.date1.delete(0, "end")
            dialog.date1.insert(0, "2026-10-03")
            dialog.date2.delete(0, "end")
            dialog.date2.insert(0, "2026-01-01")
            with patch.object(lite.messagebox, "showwarning") as warning:
                dialog._confirm()
                warning.assert_called_once()
            assert not added
            dialog._cleanup()
            checks.append("Invalid date range cannot be saved")

            app.nav_to(5)
            checkpoint("Checking export preview...")
            app.geometry("760x520")
            app.update_idletasks()
            assert app._footer_nav.winfo_reqwidth() < 520, "Footer actions consume the minimum window width"
            assert app._btn_next.winfo_manager() == "pack"
            assert app._close_without_export_btn.winfo_manager() == "pack"
            app._preview_rows_var.set("100")
            app._refresh_export_preview()
            assert len(app._preview_tree.cget("columns")) == len(app.final_df.columns)
            assert len(app._preview_tree.get_children()) == 3
            app._preview_tree.selection_set(app._preview_tree.get_children()[0])
            with patch.object(app, "clipboard_clear"), patch.object(app, "clipboard_append") as clipboard:
                app._copy_preview_rows()
                assert "region" in clipboard.call_args.args[0]
                assert "001" in clipboard.call_args.args[0]
            checks.append("Preview shows all columns and copies selected rows with headers")
            checks.append("Minimum-size layout keeps footer actions present")

            app._export_fmt_var.set("CSV-Unique text")
            checkpoint("Checking protected-column preferences...")
            assert app._unique_col_frame.winfo_manager() == "pack"
            order = app._unique_col_frame.master.pack_slaves()
            assert order.index(app._unique_col_frame) < order.index(app._export_btns_frame)
            app._unique_col_vars["id"].set(True)
            app._update_unique_column_count()
            app.nav_to(4)
            app.nav_to(5)
            assert app._export_fmt_var.get() == "CSV-Unique text"
            assert app._selected_unique_columns() == ["id"]
            checks.append("Protected-column picker stays near format and retains session preferences")

            app._out_var.set(str(folder / "output.csv"))
            checkpoint("Checking current-result export state...")
            with patch.object(app, "_show_export_success_dialog"):
                app._run_export()
                wait_idle(app)
            assert (folder / "output.csv").exists()
            assert app._has_current_export()
            app.filters.append({"mode": "text", "column": "region", "operator": "equals", "value": "West"})
            assert not app._has_current_export()
            with patch.object(lite.messagebox, "showwarning") as warning, patch.object(app, "destroy") as destroy:
                app._on_next()
                warning.assert_called_once()
                destroy.assert_not_called()
            checks.append("An earlier export does not mark changed filters as saved")

            assert not callback_errors, callback_errors
            for check in checks:
                print(f"PASS: {check}")
            print(f"Lite UX check: {len(checks)} scenarios passed; no Tk callback errors")
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
