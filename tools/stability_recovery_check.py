"""Exercise actual Lite controls through cancellation, failed saves, and retry."""

import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lite_ux_check import wait_idle
import main_gui as lite
import mergeguru_engine as engine


def main():
    app = lite.MergeGuruApp()
    app.withdraw()
    errors = []
    app.report_callback_exception = lambda *args: errors.append(args)
    try:
        with tempfile.TemporaryDirectory(prefix="mergeguru_recovery_") as temporary:
            folder = Path(temporary)
            paths = [folder / f"source_{index}.csv" for index in range(2)]
            for index, path in enumerate(paths):
                numbers = range(index * 10001, (index + 1) * 10001)
                pd.DataFrame({"id": [f"{value:012d}" for value in numbers], "amount": list(numbers)}).to_csv(path, index=False)
            app.folder = temporary
            app.all_sources = engine.discover_sources([str(path) for path in paths])[0]
            app.nav_to(1)
            app.nav_to(2)
            app.nav_to(3)
            app._run_validation()
            wait_idle(app)
            app.nav_to(4)
            app._fast_combine_var.set(True)
            second_started, release = threading.Event(), threading.Event()
            active, waiting_states = [], []
            original = lite.prepare_source_frame
            def slow_read(source, *args, **kwargs):
                if source is app.all_sources[1]:
                    active.append(True)
                    second_started.set()
                    assert release.wait(5)
                    active.clear()
                else:
                    assert second_started.wait(5)
                    def cancel():
                        app._cancel_active_operation()
                        waiting_states.append(app._operation_running and bool(active))
                        app.after(150, release.set)
                    app.after(0, cancel)
                return original(source, *args, **kwargs)
            with patch.object(lite, "check_memory_before_combine", return_value=(True, "", 8, 1)):
                with patch.object(lite, "prepare_source_frame", side_effect=slow_read):
                    try:
                        app._start_combine()
                        wait_idle(app)
                    finally:
                        release.set()
                assert waiting_states == [True]
                assert not active and app.final_df is None
                assert str(app._combine_start_btn.cget("state")) == "normal"
                app._start_combine()
                wait_idle(app)
            assert len(app.final_df) == 20002
            print("PASS: Parallel combine stays busy until readers finish, then retries successfully", flush=True)

            app.nav_to(5)
            app._export_fmt_var.set("CSV")
            destination = folder / "output.csv"
            destination.write_bytes(b"previous completed export")
            app._out_var.set(str(destination))
            captured_errors = []
            with patch.object(lite.messagebox, "askyesno", return_value=True), patch.object(app, "_show_error_with_details", side_effect=lambda *args, **kwargs: captured_errors.append(args)), patch.object(engine, "_write_dataframe", side_effect=OSError("Simulated disk-full failure")):
                app._run_export()
                wait_idle(app)
            assert captured_errors and not app._operation_running
            assert app.final_df is not None and not app._export_history
            assert destination.read_bytes() == b"previous completed export"
            assert not list(folder.glob(".mergeguru-*"))
            print("PASS: Failed export preserves the old file and restores retry controls", flush=True)

            original_write = engine._write_dataframe
            def cancel_during_write(*args):
                arguments = list(args)
                original_progress = arguments[6]
                requested = []
                def progress(percent, message):
                    original_progress(percent, message)
                    if percent < 100 and not requested:
                        requested.append(True)
                        acknowledged = threading.Event()
                        def cancel():
                            app._cancel_active_operation()
                            acknowledged.set()
                        app.after(0, cancel)
                        assert acknowledged.wait(5)
                arguments[6] = progress
                return original_write(*arguments)
            with patch.object(lite.messagebox, "askyesno", return_value=True), patch.object(engine, "_write_dataframe", side_effect=cancel_during_write):
                app._run_export()
                wait_idle(app)
            assert destination.read_bytes() == b"previous completed export"
            assert not app._export_history and app.final_df is not None
            assert not list(folder.glob(".mergeguru-*"))
            print("PASS: Cancelled overwrite preserves output and cached data", flush=True)

            with patch.object(lite.messagebox, "askyesno", return_value=True), patch.object(app, "_show_export_success_dialog"):
                app._run_export()
                wait_idle(app)
            assert len(pd.read_csv(destination)) == 20002
            assert (folder / "output.audit.txt").exists()
            assert app._has_current_export() and len(app._export_history) == 1
            assert str(app._run_export_btn.cget("state")) == "normal"
            assert not errors, errors
            print("PASS: Retry exports all rows, creates audit, and marks the current result saved", flush=True)
        print("Stability recovery check: 4 scenarios passed; no Tk callback errors", flush=True)
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
