"""Focused data-integrity regression tests for the shared engine and Lite export."""

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mergeguru_engine as engine
import main_gui as lite


class Widget(dict):
    def __init__(self, value=None):
        super().__init__()
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def configure(self, **kwargs):
        self.update(kwargs)

    config = configure


class InlineThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


class HighRiskQA(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mergeguru_qa_")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, path):
        return engine.discover_sources([str(path)])[0][0]

    def lite_combine_app(self, sources, columns):
        app = SimpleNamespace(
            all_sources=sources, passed_srcs=sources, ref_idx=0,
            ref_columns=columns, selected_sheet=None, _source_sheet_map={},
            fast_combine_enabled=False, allow_extra_columns=True,
            extra_columns_found=[], optimize_memory_enabled=False,
            _cancel_combine_requested=False, final_df=None, outcome=None,
        )
        app.after = lambda delay, callback: callback()
        app._get_layout_read_options = lambda: {"header_row": 1, "footer_rows": 0}
        app._source_size = engine.source_size
        app._operation_file_activity = lambda *args: None
        app._format_size = str
        app._result_signature = lambda: (0, ())
        app._format_time = str
        app._build_data_quality_summary = lambda frame: {}
        for name in ("_record_perf", "_set_status", "_update_combine_progress", "_invalidate_filtered_cache"):
            setattr(app, name, lambda *args, **kwargs: None)
        app._combine_done = lambda: setattr(app, "outcome", "done")
        app._combine_failed_done = lambda error: setattr(app, "outcome", error)
        app._combine_cancelled_done = lambda: setattr(app, "outcome", "cancelled")
        def combine():
            with patch.object(lite, "check_memory_before_combine", return_value=(True, "", 8, 1)):
                lite.MergeGuruApp._combine_bg_impl(app)
        app._combine_bg_impl = combine
        return app

    def test_filter_error_never_exports_unfiltered_data(self):
        frame = pd.DataFrame({"secret": ["should not export"]})
        app = SimpleNamespace(
            _export_fmt_var=Widget("CSV"), _out_var=Widget(str(self.root / "out.csv")),
            passed_srcs=[{}], final_df=frame, filters=[{"column": "secret"}],
            _exp_prog=Widget(), _exp_pct=Widget(), _filter_stats_cache=[],
            _export_history=[], _step_prog=Widget(), _btn_next=Widget(),
        )
        app.after = lambda delay, callback: callback()
        for name in ("_update_export_details", "_set_export_running", "_log",
                     "_set_status", "_record_perf", "_redraw_export_history",
                     "_stop_overall_timer", "_show_export_success_dialog",
                     "_show_error_with_details"):
            setattr(app, name, lambda *args, **kwargs: None)
        app._compute_filtered_result = lambda: (_ for _ in ()).throw(ValueError("invalid filter"))
        app._format_size = str
        app._write_audit_report = lambda *args: None
        app._result_signature = lambda: (0, ())
        with patch.object(lite.threading, "Thread", InlineThread), patch.object(lite, "save_dataframe") as save:
            lite.MergeGuruApp._run_export(app)
        save.assert_not_called()
        self.assertEqual(app._export_history, [])

    def test_invalid_regex_is_rejected(self):
        with self.assertRaises(ValueError):
            engine.build_filter_mask(pd.DataFrame({"id": ["a"]}),
                {"mode": "text", "column": "id", "operator": "contains", "value": "["})

    def test_csv_identifiers_survive_reading(self):
        path = self.root / "ids.csv"
        path.write_text("id,big,amount\n00123,12345678901234567890,12.5\n00001,98765432109876543210,25\n", encoding="utf-8")
        frame = engine.read_full(self.source(path))
        self.assertEqual(frame["id"].tolist(), ["00123", "00001"])
        self.assertEqual(frame["big"].tolist(), ["12345678901234567890", "98765432109876543210"])
        self.assertEqual(frame["amount"].tolist(), [12.5, 25])

    def test_excel_text_identifiers_survive_reading(self):
        path = self.root / "ids.xlsx"
        pd.DataFrame({"id": ["00123", "00001"], "amount": [2, 3]}).to_excel(path, index=False)
        frame = engine.read_full(self.source(path), sheet="Sheet1")
        self.assertEqual(frame["id"].tolist(), ["00123", "00001"])

    def test_zipped_identifiers_survive_reading(self):
        path = self.root / "ids.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("nested/ids.csv", "id,amount\n00123,5\n")
        frame = engine.read_full(self.source(path))
        self.assertEqual(frame["id"].tolist(), ["00123"])
        self.assertEqual(frame["amount"].tolist(), [5])

    def test_unique_text_handles_nulls_without_nan_text(self):
        path = self.root / "protected.csv"
        engine.save_dataframe(pd.DataFrame({"id": ["00123", None], "amount": [1, 2]}),
                              str(path), "CSV-Unique text", unique_columns=["id"])
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        self.assertEqual(frame["id"].tolist(), ["'00123'", ""])
        self.assertEqual(frame["amount"].tolist(), ["1", "2"])

    def test_excel_header_row_limit(self):
        path = self.root / "too_many.xlsx"
        frame = pd.DataFrame(index=pd.RangeIndex(engine.EXCEL_HARD_ROW_LIMIT), columns=["id"])
        with patch.object(engine, "_write_dataframe", side_effect=AssertionError("Oversized data reached writer")):
            with self.assertRaisesRegex(ValueError, "row limit"):
                engine.save_dataframe(frame, str(path), "Excel")
        self.assertFalse(path.exists())

    def test_excel_column_limit(self):
        with patch.object(engine, "_write_dataframe", side_effect=AssertionError("Oversized data reached writer")):
            with self.assertRaisesRegex(ValueError, "column limit"):
                engine.save_dataframe(pd.DataFrame(columns=range(16385)), str(self.root / "wide.xlsx"), "Excel")

    def test_lite_excel_header_limit_switches_format(self):
        app = SimpleNamespace(_run_on_ui_thread_sync=lambda fn, **kwargs: fn())
        with patch.object(lite.messagebox, "askyesnocancel", return_value=True) as prompt:
            result = lite.MergeGuruApp._resolve_excel_export_format(app, engine.EXCEL_HARD_ROW_LIMIT)
        self.assertEqual(result, "CSV")
        self.assertEqual(prompt.call_args.args[0], "Excel row limit exceeded")

    def test_excel_last_valid_data_row_passes_guard(self):
        path = self.root / "limit.xlsx"
        frame = pd.DataFrame(index=pd.RangeIndex(engine.EXCEL_HARD_ROW_LIMIT - 1), columns=["id"])
        def fake_write(frame, temporary, *args):
            Path(temporary).write_bytes(b"boundary guard accepted")
        with patch.object(engine, "_write_dataframe", side_effect=fake_write):
            engine.save_dataframe(frame, str(path), "Excel")
        self.assertEqual(path.read_bytes(), b"boundary guard accepted")

    def test_cancel_csv_preserves_existing_destination(self):
        path = self.root / "existing.csv"
        original = b"original completed export"
        path.write_bytes(original)
        cancelled = [False]
        with self.assertRaises(engine.CancelledOperation):
            engine.save_dataframe(pd.DataFrame({"id": range(20001)}), str(path), "CSV",
                cancel_callback=lambda: cancelled[0],
                progress_callback=lambda *args: cancelled.__setitem__(0, True))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["existing.csv"])

    def test_cancel_csv_leaves_no_new_output(self):
        path = self.root / "new.csv"
        with self.assertRaises(engine.CancelledOperation):
            engine.save_dataframe(pd.DataFrame({"id": [1]}), str(path), "CSV", cancel_callback=lambda: True)
        self.assertFalse(path.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cancel_excel_before_commit(self):
        path = self.root / "existing.xlsx"
        path.write_bytes(b"original")
        cancelled = [False]
        with self.assertRaises(engine.CancelledOperation):
            engine.save_dataframe(pd.DataFrame({"id": [1, 2]}), str(path), "Excel",
                cancel_callback=lambda: cancelled[0],
                progress_callback=lambda *args: cancelled.__setitem__(0, True))
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_cancel_excel_between_chunks_preserves_destination(self):
        path = self.root / "existing.xlsx"
        path.write_bytes(b"original")
        cancelled = [False]
        with self.assertRaises(engine.CancelledOperation):
            engine.save_dataframe(pd.DataFrame({"id": range(10001)}), str(path), "Excel",
                cancel_callback=lambda: cancelled[0],
                progress_callback=lambda *args: cancelled.__setitem__(0, True))
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_cancel_parquet_after_writer_returns(self):
        path = self.root / "existing.parquet"
        path.write_bytes(b"original")
        cancelled = [False]
        def fake_write(temporary, **kwargs):
            Path(temporary).write_bytes(b"unfinished")
            cancelled[0] = True
        frame = pd.DataFrame({"id": [1]})
        with patch.object(pd.DataFrame, "to_parquet", side_effect=fake_write):
            with self.assertRaises(engine.CancelledOperation):
                engine.save_dataframe(frame, str(path), "Parquet", cancel_callback=lambda: cancelled[0])
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_progress_complete_only_after_destination_committed(self):
        path = self.root / "out.csv"
        progress = []
        def report(percent, message):
            progress.append(percent)
            if percent == 100:
                self.assertTrue(path.exists())
                self.assertEqual(pd.read_csv(path)["id"].tolist(), [1, 2])
        engine.save_dataframe(pd.DataFrame({"id": [1, 2]}), str(path), "CSV", progress_callback=report)
        self.assertEqual(progress[-1], 100)
        self.assertTrue(all(percent < 100 for percent in progress[:-1]))

    def test_write_failure_preserves_destination(self):
        path = self.root / "existing.csv"
        path.write_bytes(b"original")
        with patch.object(pd.DataFrame, "to_csv", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                engine.save_dataframe(pd.DataFrame({"id": [1]}), str(path), "CSV")
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_source_file_collision_preserves_business_data(self):
        path = self.root / "source.csv"
        pd.DataFrame({"id": [1], "source_file": ["business-value"],
                      "mergeguru_source_file": ["another-value"]}).to_csv(path, index=False)
        source = self.source(path)
        validation = engine.validate_sources([source], 0)
        frame, _, _ = engine.combine_sources([source], source, validation["reference_columns"])
        self.assertEqual(frame["source_file"].tolist(), ["business-value"])
        self.assertEqual(frame["mergeguru_source_file"].tolist(), ["another-value"])
        self.assertEqual(frame.iloc[0, -1], "source.csv")
        self.assertTrue(frame.columns.is_unique)

    def test_source_changed_after_validation_is_rejected(self):
        path = self.root / "source.csv"
        pd.DataFrame({"id": [1], "amount": [2]}).to_csv(path, index=False)
        source = self.source(path)
        validation = engine.validate_sources([source], 0)
        pd.DataFrame({"id": [999]}).to_csv(path, index=False)
        with self.assertRaisesRegex(ValueError, "changed|missing"):
            engine.combine_sources([source], source, validation["reference_columns"])

    def test_missing_schema_rejected_without_snapshot(self):
        path = self.root / "source.csv"
        pd.DataFrame({"id": [1]}).to_csv(path, index=False)
        source = self.source(path)
        with self.assertRaisesRegex(ValueError, "missing"):
            engine.combine_sources([source], source, ["id", "amount"])

    def test_source_data_changed_with_same_schema_is_rejected(self):
        path = self.root / "source.csv"
        path.write_text("id,amount\n1,2\n", encoding="utf-8")
        source = self.source(path)
        validation = engine.validate_sources([source], 0)
        path.write_text("id,amount\n1000,2000\n", encoding="utf-8")
        with self.assertRaisesRegex(engine.SourceChangedError, "changed"):
            engine.combine_sources([source], source, validation["reference_columns"])

    def test_source_changed_during_read_is_rejected(self):
        path = self.root / "source.csv"
        path.write_text("id,amount\n1,2\n", encoding="utf-8")
        source = self.source(path)
        def changed_read(*args, **kwargs):
            path.write_text("id\n999999\n", encoding="utf-8")
            return pd.DataFrame({"id": [1], "amount": [2]})
        with patch.object(engine, "read_full", side_effect=changed_read):
            with self.assertRaisesRegex(engine.SourceChangedError, "changed while reading"):
                engine.prepare_source_frame(source, ["id", "amount"])

    def test_lite_source_file_collision_preserves_business_data(self):
        path = self.root / "source.csv"
        pd.DataFrame({"id": [1], "source_file": ["business-value"]}).to_csv(path, index=False)
        app = self.lite_combine_app([self.source(path)], ["id", "source_file"])
        lite.MergeGuruApp._combine_bg(app)
        self.assertEqual(app.outcome, "done")
        self.assertEqual(app.final_df["source_file"].tolist(), ["business-value"])
        self.assertEqual(app.final_df["mergeguru_source_file"].tolist(), ["source.csv"])

    def test_lite_changed_source_stops_combine(self):
        path = self.root / "source.csv"
        path.write_text("id,amount\n1,2\n", encoding="utf-8")
        source = self.source(path)
        validation = engine.validate_sources([source], 0)
        path.write_text("id\n999999\n", encoding="utf-8")
        app = self.lite_combine_app([source], validation["reference_columns"])
        lite.MergeGuruApp._combine_bg(app)
        self.assertIn("changed", app.outcome)
        self.assertIsNone(app.final_df)

    def test_combine_cancel_at_final_file_does_not_publish_result(self):
        path = self.root / "source.csv"
        path.write_text("id\n1\n", encoding="utf-8")
        source = self.source(path)
        cancelled = [False]
        with self.assertRaises(engine.CancelledOperation):
            engine.combine_sources([source], source, ["id"],
                progress_callback=lambda *args: cancelled.__setitem__(0, True),
                cancel_callback=lambda: cancelled[0])

    def test_pro_filter_error_never_exports_stale_results(self):
        import main_gui_pro as pro
        frame = pd.DataFrame({"id": ["secret"]})
        app = SimpleNamespace(busy=False, final_df=frame, filtered_df=frame,
            filters=[{"mode": "text", "column": "id", "operator": "contains", "value": "["}])
        with patch.object(pro.QMessageBox, "critical") as error, patch.object(engine, "save_dataframe") as save:
            pro.MergeGuruPro._run_export(app)
        error.assert_called_once()
        save.assert_not_called()

    def test_successful_excel_report_roundtrip(self):
        path = self.root / "out.xlsx"
        engine.save_dataframe(pd.DataFrame({"id": [1, 2]}), str(path), "Excel",
            validation_report_df=pd.DataFrame({"File": ["a.csv"], "Status": ["PASS"]}))
        with pd.ExcelFile(path) as book:
            self.assertEqual(book.sheet_names, ["Data", "Validation Report"])
            self.assertEqual(pd.read_excel(book, sheet_name="Data")["id"].tolist(), [1, 2])

    def test_excel_chunks_do_not_repeat_or_drop_headers(self):
        path = self.root / "chunked.xlsx"
        engine.save_dataframe(pd.DataFrame({"id": range(10001)}), str(path), "Excel")
        frame = pd.read_excel(path)
        self.assertEqual(frame["id"].tolist(), list(range(10001)))

    def test_parquet_roundtrip_preserves_identifiers(self):
        path = self.root / "out.parquet"
        frame = pd.DataFrame({"id": ["00123", "00001"], "amount": [1.25, 2.5]})
        engine.save_dataframe(frame, str(path), "Parquet")
        pd.testing.assert_frame_equal(pd.read_parquet(path), frame)


if __name__ == "__main__":
    unittest.main(verbosity=2)
