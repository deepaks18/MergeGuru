"""Fault/recovery checks that complement the high-risk data-integrity suite."""

import sys
import os
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from high_risk_qa import HighRiskQA, InlineThread, Widget
import mergeguru_engine as engine
import main_gui as lite
from types import SimpleNamespace


class StabilityFaultChecks(HighRiskQA):
    # Inherit the fixture helpers without rerunning the previous suite.
    def test_parallel_cancel_does_not_unlock_before_readers_finish(self):
        paths = [self.root / f"source_{index}.csv" for index in range(2)]
        for path in paths:
            path.write_text("id\n1\n", encoding="utf-8")
        sources = [self.source(path) for path in paths]
        app = self.lite_combine_app(sources, ["id"])
        app.fast_combine_enabled = True
        app._choose_combine_workers = lambda total: 2
        started = threading.Event()
        release = threading.Event()
        active = []
        observed = []
        def read(source, *args, **kwargs):
            if source is sources[1]:
                active.append(True)
                started.set()
                if not release.wait(5):
                    raise TimeoutError("Fixture failed to release its reader")
                active.clear()
            else:
                if not started.wait(5):
                    raise TimeoutError("Second reader did not start")
                app._cancel_combine_requested = True
            return pd.DataFrame({"id": [1]})
        app._combine_cancelled_done = lambda: observed.append(len(active))
        worker = threading.Thread(target=lambda: lite.MergeGuruApp._combine_bg(app))
        with patch.object(lite, "prepare_source_frame", side_effect=read):
            worker.start()
            self.assertTrue(started.wait(5))
            # Return the first result while the second remains in its read.
            threading.Event().wait(0.1)
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(observed, [0], "Cancellation enabled retry while a reader was still running")

    def test_memory_optimization_preserves_float_values_exactly(self):
        frame = pd.DataFrame({"amount": [0.123456789012345, 123.456789123456, float("nan")]})
        expected = frame.copy(deep=True)
        optimized, _ = engine.optimize_dataframe_memory(frame)
        pd.testing.assert_frame_equal(optimized, expected, check_exact=True)

    def test_export_pre_save_exception_restores_idle_state(self):
        states, errors = [], []
        app = SimpleNamespace(
            _export_fmt_var=Widget("Excel"), _out_var=Widget(str(self.root / "out.xlsx")),
            passed_srcs=[{}], final_df=pd.DataFrame({"id": [1]}), filters=[],
            _exp_prog=Widget(), _exp_pct=Widget(), _filter_stats_cache=[], _export_history=[],
            _operation_running=False,
        )
        app.after = lambda delay, fn: fn()
        app._result_signature = lambda: (0, ())
        app._compute_filtered_result = lambda: app.final_df
        app._set_export_running = lambda state: states.append(state)
        app._export_failed_done = lambda error: (states.append(False), errors.append(error))
        app._resolve_excel_export_format = lambda rows: (_ for _ in ()).throw(TimeoutError("UI response expired"))
        for name in ("_update_export_details", "_set_status", "_log", "_record_perf"):
            setattr(app, name, lambda *args, **kwargs: None)
        with patch.object(lite.threading, "Thread", InlineThread):
            lite.MergeGuruApp._run_export(app)
        self.assertEqual(states, [True, False])
        self.assertIn("expired", errors[0])

    def test_actual_locked_destination_preserves_completed_output(self):
        if os.name != "nt":
            self.skipTest("This check exercises Windows file sharing/rename semantics")
        path = self.root / "locked.csv"
        path.write_bytes(b"original completed output")
        with path.open("rb"):
            with self.assertRaises(PermissionError):
                engine.save_dataframe(pd.DataFrame({"id": [1]}), str(path), "CSV")
        self.assertEqual(path.read_bytes(), b"original completed output")
        self.assertFalse(list(self.root.glob(".mergeguru-*")))

    def test_forced_worker_exit_preserves_previous_export(self):
        path, ready = self.root / "crash.csv", self.root / "ready.txt"
        path.write_bytes(b"original completed output")
        worker = subprocess.Popen([sys.executable, str(Path(__file__).with_name("stability_crash_worker.py")), str(path), str(ready)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15
            while not ready.exists() and worker.poll() is None and time.monotonic() < deadline:
                threading.Event().wait(0.05)
            self.assertTrue(ready.exists(), "Fixture did not reach a write checkpoint")
        finally:
            if worker.poll() is None:
                worker.terminate()
            worker.communicate(timeout=5)
        self.assertEqual(path.read_bytes(), b"original completed output")
        # A hard kill cannot execute finally; leftovers stay visibly temporary.
        self.assertTrue(list(self.root.glob(".mergeguru-*")))

    def test_modal_user_wait_is_not_treated_as_ui_hang(self):
        ready, release = threading.Event(), threading.Event()
        errors, values, ui_threads = [], [], []
        def user_question():
            ready.set()
            release.wait(3)
            return "answer"
        def after(delay, fn):
            ui_thread = threading.Thread(target=fn)
            ui_threads.append(ui_thread)
            ui_thread.start()
        app = SimpleNamespace(after=after)
        def wait_for_answer():
            try:
                values.append(lite.MergeGuruApp._run_on_ui_thread_sync(app, user_question, allow_user_wait=True))
            except Exception as exc:
                errors.append(exc)
        with patch.object(lite.time, "monotonic", side_effect=[0, 100, 200, 300]):
            worker = threading.Thread(target=wait_for_answer)
            worker.start()
            self.assertTrue(ready.wait(2))
            threading.Event().wait(0.55)
            release.set()
            worker.join(3)
        for ui_thread in ui_threads:
            ui_thread.join(3)
        self.assertFalse(errors)
        self.assertEqual(values, ["answer"])


if __name__ == "__main__":
    suite = unittest.TestSuite(StabilityFaultChecks(name) for name in (
        "test_parallel_cancel_does_not_unlock_before_readers_finish",
        "test_memory_optimization_preserves_float_values_exactly",
        "test_export_pre_save_exception_restores_idle_state",
        "test_actual_locked_destination_preserves_completed_output",
        "test_forced_worker_exit_preserves_previous_export",
        "test_modal_user_wait_is_not_treated_as_ui_hang",
    ))
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not outcome.wasSuccessful())
