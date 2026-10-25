#!/usr/bin/env python3
"""Functional checks for MergeGuru Lite v3."""

from __future__ import annotations

import hashlib
import os
import runpy
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import pandas as pd
from PIL import Image

from mergeguru_engine import (
    CancelledOperation,
    apply_filters,
    combine_sources,
    discover_sources,
    save_dataframe,
    validate_sources,
)
from mergeguru_lite_v3.app import MergeGuruLiteV3
from mergeguru_lite_v3.diagnostics import DiagnosticRecorder
from mergeguru_lite_v3.filter_dialog import matching_count, unique_values_limited
from mergeguru_lite_v3.preferences import DEFAULTS, load_preferences, save_preferences
from mergeguru_lite_v3.projects import (
    build_project_payload,
    load_project,
    resolve_project_inputs,
    save_project,
)
from mergeguru_lite_v3.reports import validation_report_frame, write_audit_report
from mergeguru_lite_v3.state import LITE_VERSION, LiteV3State, next_available_path
from prototypes.lite_redesign.theme import COLORS as C


ROLLBACK_EXE = os.path.join(
    "releases", "MergeGuru_Lite_v2_4_Rollback", "MergeGuru_Lite_v2_4.exe"
)
EXPECTED_STABLE_SHA256 = "7463A0662AEC0C90C3F2183E6822EC0823D860D303866EA9D207A2F7A29BCD4F"


def make_sources(folder):
    first = os.path.join(folder, "North.csv")
    second = os.path.join(folder, "West.csv")
    pd.DataFrame(
        {
            "Customer ID": ["001", "002", "003"],
            "Branch": ["Waltham", "North End", "Watford"],
            "Amount": [100, 200, 300],
        }
    ).to_csv(first, index=False)
    pd.DataFrame(
        {
            "Amount": [400, 500],
            "Branch": ["Walnut Creek", "South End"],
            "Customer ID": ["004", "005"],
            "Team": ["Retail", "Retail"],
        }
    ).to_csv(second, index=False)
    return first, second


def prepare_state(folder):
    paths = make_sources(folder)
    sources, errors = discover_sources(paths)
    state = LiteV3State()
    state.set_sources(sources, errors)
    validation = validate_sources(sources, 0, allow_extra=True)
    final, extras, memory_stats = combine_sources(
        validation["passed_sources"],
        sources[0],
        validation["reference_columns"],
        source_sheet_map=validation["source_sheet_map"],
        allow_extra=True,
        extra_columns=validation["extra_columns"],
        optimize_memory=True,
    )
    state.set_prepared(validation, final, extras, memory_stats)
    return state


class StateAndEngineChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mergeguru-v3-check-")
        self.folder = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def test_shuffled_and_extra_columns_are_combined_by_name(self):
        state = prepare_state(self.folder)
        self.assertEqual(state.total_rows, 5)
        self.assertIn("team", state.columns)
        self.assertEqual(state.columns[:3], ["customer id", "branch", "amount"])
        west = state.final_df.loc[state.final_df["customer id"] == "004"].iloc[0]
        self.assertEqual(west["branch"], "Walnut Creek")
        self.assertEqual(west["amount"], 400)

    def test_category_prefix_scenario_filters_expected_rows(self):
        state = prepare_state(self.folder)
        values = sorted(value for value in state.final_df["branch"].astype(str).unique() if value.startswith("Wa"))
        state.filters = [{"column": "branch", "mode": "category", "action": "include", "values": values}]
        result = state.apply_filters()
        self.assertEqual(set(result["branch"]), {"Waltham", "Watford", "Walnut Creek"})
        self.assertEqual(len(result), 3)

    def test_text_starts_with_filter_uses_cached_dataframe(self):
        state = prepare_state(self.folder)
        original_id = id(state.final_df)
        state.filters = [{"column": "branch", "mode": "text", "operator": "starts_with", "value": "Wa"}]
        state.apply_filters()
        self.assertEqual(id(state.final_df), original_id)
        self.assertEqual(state.result_rows, 3)

    def test_unique_value_scan_stops_at_guardrail(self):
        values, truncated = unique_values_limited(pd.Series(str(index) for index in range(20_050)))
        self.assertTrue(truncated)
        self.assertEqual(len(values), 20_001)

    def test_draft_count_does_not_materialize_filtered_frame(self):
        state = prepare_state(self.folder)
        filters = [{"column": "branch", "mode": "text", "operator": "starts_with", "value": "Wa"}]
        self.assertEqual(matching_count(state.final_df, filters), len(apply_filters(state.final_df, filters)))

    def test_validation_report_has_status_and_extra_columns(self):
        state = prepare_state(self.folder)
        report = validation_report_frame(state.validation)
        self.assertEqual(len(report), 2)
        self.assertIn("Validation Status", report.columns)
        self.assertEqual(report.iloc[1]["Validation Status"], "WARNING")
        self.assertIn("team", report.iloc[1]["Extra Columns"])

    def test_csv_unique_export_and_text_audit(self):
        state = prepare_state(self.folder)
        state.output_format = "CSV-Unique text"
        state.protected_columns = {"customer id"}
        output = os.path.join(self.folder, "protected.csv")
        state.output_path = output
        save_dataframe(
            state.filtered_df,
            output,
            state.output_format,
            unique_columns=sorted(state.protected_columns),
            validation_report_df=validation_report_frame(state.validation),
        )
        audit = write_audit_report(state, output, len(state.filtered_df), os.path.getsize(output), 0.25)
        with open(output, "r", encoding="utf-8") as stream:
            content = stream.read()
        with open(audit, "r", encoding="utf-8") as stream:
            audit_text = stream.read()
        self.assertIn("'001'", content)
        self.assertIn("Validation Summary", audit_text)
        self.assertIn("Deep blank/duplicate-row scans: Not run", audit_text)

    def test_next_available_path_never_selects_existing_file(self):
        path = os.path.join(self.folder, "output.csv")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("existing")
        self.assertEqual(next_available_path(path), os.path.join(self.folder, "output_02.csv"))

    def test_preferences_exclude_filters_and_sources(self):
        path = os.path.join(self.folder, "preferences.json")
        values = dict(DEFAULTS)
        values.update({"allow_extra": False, "preview_limit": 25})
        save_preferences(values, path)
        loaded = load_preferences(path)
        self.assertFalse(loaded["allow_extra"])
        self.assertEqual(loaded["preview_limit"], 25)
        self.assertNotIn("filters", loaded)
        self.assertNotIn("sources", loaded)

    def test_project_round_trip_preserves_rules_without_source_rows(self):
        state = prepare_state(self.folder)
        state.project_inputs = [{"kind": "folder", "path": self.folder}]
        state.filters = [
            {"column": "branch", "mode": "text", "operator": "starts_with", "value": "Wa"}
        ]
        state.output_format = "CSV-Unique text"
        state.protected_columns = {"customer id"}
        state.output_path = os.path.join(self.folder, "exports", "output.csv")
        previous_output = os.path.join(self.folder, "previous-output.csv")
        pd.DataFrame({"not": ["a source"]}).to_csv(previous_output, index=False)
        state.history = [{"path": previous_output}]
        project_path = os.path.join(self.folder, "monthly.mergeguru.json")
        saved = save_project(project_path, build_project_payload(state, LITE_VERSION))
        loaded = load_project(saved)
        paths, warnings = resolve_project_inputs(loaded)
        self.assertFalse(warnings)
        self.assertEqual(set(paths), set(make_sources(self.folder)))
        self.assertNotIn(previous_output, paths)
        self.assertEqual(loaded["filters"], state.filters)
        self.assertEqual(loaded["export"]["format"], "CSV-Unique text")
        with open(saved, "r", encoding="utf-8") as stream:
            project_text = stream.read()
        self.assertNotIn("North End", project_text)
        self.assertNotIn("Walnut Creek", project_text)

    def test_project_rejects_unsupported_schema(self):
        path = os.path.join(self.folder, "invalid.mergeguru.json")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write('{"schema_version": 999, "product": "MergeGuru Lite", "source_inputs": []}')
        with self.assertRaisesRegex(ValueError, "not supported"):
            load_project(path)

    def test_diagnostics_exclude_paths_names_columns_and_filter_values(self):
        state = prepare_state(self.folder)
        state.filters = [
            {
                "column": "branch",
                "mode": "text",
                "operator": "contains",
                "value": "CONFIDENTIAL-FILTER-VALUE",
            }
        ]
        recorder = DiagnosticRecorder(LITE_VERSION, os.path.join(self.folder, "session.log"))
        recorder.record("task_failed", task="prepare", error_type="PermissionError")
        report = recorder.build_report(
            state,
            current_step="Check & Prepare",
            task_kind="prepare",
            last_error_type="PermissionError",
        )
        self.assertNotIn(self.folder, report)
        self.assertNotIn("North.csv", report)
        self.assertNotIn("branch", report)
        self.assertNotIn("CONFIDENTIAL-FILTER-VALUE", report)
        self.assertIn("No diagnostic information is transmitted automatically", report)

    def test_hd_brand_assets_have_high_resolution_masters(self):
        with Image.open(os.path.join("assets", "MergeGuru_Mark_HD.png")) as mark:
            self.assertEqual(mark.size, (1024, 1024))
            self.assertEqual(mark.mode, "RGBA")
        with Image.open(os.path.join("assets", "MergeGuru_Brand_HD.png")) as lockup:
            self.assertEqual(lockup.size, (1600, 400))
        with Image.open(os.path.join("assets", "MergeGuru_Lite_v3_1_splash.png")) as splash:
            self.assertEqual(splash.size, (720, 360))

    def test_cancelled_atomic_export_preserves_destination(self):
        state = prepare_state(self.folder)
        destination = os.path.join(self.folder, "existing.csv")
        with open(destination, "w", encoding="utf-8") as stream:
            stream.write("KEEP")
        with self.assertRaises(Exception):
            save_dataframe(
                state.filtered_df,
                destination,
                "CSV",
                cancel_callback=lambda: True,
            )
        with open(destination, "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "KEEP")

    def test_v2_4_rollback_exe_is_intact(self):
        if not os.path.exists(ROLLBACK_EXE):
            self.skipTest("v2.4 rollback EXE is not present in this checkout")
        digest = hashlib.sha256()
        with open(ROLLBACK_EXE, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        self.assertEqual(digest.hexdigest().upper(), EXPECTED_STABLE_SHA256)

    def test_familiar_main_entry_routes_to_v3(self):
        with patch("mergeguru_lite_v3.app.MergeGuruLiteV3") as app_class:
            with self.assertRaises(SystemExit) as exit_result:
                runpy.run_path("main_gui.py", run_name="__main__")
        self.assertEqual(exit_result.exception.code, 0)
        app_class.assert_called_once_with()
        app_class.return_value.mainloop.assert_called_once_with()

    def test_familiar_main_self_test_routes_to_canonical_diagnostics(self):
        report = os.path.join(self.folder, "familiar-selftest.txt")
        arguments = ["main_gui.py", "--self-test", report]
        with patch.object(sys, "argv", arguments):
            with patch("mergeguru_diagnostics.run_self_test", return_value=0) as self_test:
                with self.assertRaises(SystemExit) as exit_result:
                    runpy.run_path("main_gui.py", run_name="__main__")
        self.assertEqual(exit_result.exception.code, 0)
        self.assertEqual(self_test.call_args.args[0], report)

    def test_canonical_launcher_routes_to_v3(self):
        import main_gui_lite_v3 as launcher

        with patch("mergeguru_lite_v3.app.MergeGuruLiteV3") as app_class:
            result = launcher.main(["main_gui_lite_v3.py"])
        self.assertEqual(result, 0)
        app_class.assert_called_once_with()
        app_class.return_value.mainloop.assert_called_once_with()

    def test_canonical_launcher_routes_packaged_self_test(self):
        import main_gui_lite_v3 as launcher

        report = os.path.join(self.folder, "selftest.txt")
        with patch("mergeguru_diagnostics.run_self_test", return_value=0) as self_test:
            split_result = launcher.main(
                ["main_gui_lite_v3.py", "--self-test", report, "--bootloader-extra"]
            )
            joined_result = launcher.main(
                ["main_gui_lite_v3.py", f"--self-test={report}"]
            )
        self.assertEqual(split_result, 0)
        self.assertEqual(joined_result, 0)
        self.assertEqual(self_test.call_count, 2)
        self.assertEqual([call.args[0] for call in self_test.call_args_list], [report, report])

    def test_canonical_launcher_accepts_packaged_self_test_environment(self):
        import main_gui_lite_v3 as launcher

        report = os.path.join(self.folder, "environment-selftest.txt")
        with patch.dict(os.environ, {"MERGEGURU_SELF_TEST_REPORT": report}):
            with patch("mergeguru_diagnostics.run_self_test", return_value=0) as self_test:
                result = launcher.main(["main_gui_lite_v3.py"])
        self.assertEqual(result, 0)
        self.assertEqual(self_test.call_args.args[0], report)


class GuiJourneyChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mergeguru-v3-ui-")
        self.folder = self.temp.name
        self.paths = make_sources(self.folder)
        self.preference_file = os.path.join(self.folder, "preferences.json")
        self.diagnostic_file = os.path.join(self.folder, "diagnostics.log")
        self.app = MergeGuruLiteV3(
            preference_file=self.preference_file,
            diagnostic_file=self.diagnostic_file,
        )
        self.app.geometry("900x640+20+20")
        self.app.update()

    def tearDown(self):
        if self.app.winfo_exists():
            self.app.destroy()
        self.temp.cleanup()

    def wait_for_task(self, timeout=20):
        deadline = time.monotonic() + timeout
        while self.app.busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.app.update()
        self.assertFalse(self.app.busy, f"Task did not finish: {self.app.task_kind}")

    def wait_until(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)
        self.app.update()
        self.assertTrue(predicate(), "Timed out waiting for the UI state")

    def test_real_gui_discover_prepare_filter_export_journey(self):
        for geometry in ("720x560", "900x640", "1060x780"):
            self.app.geometry(geometry)
            self.app.update()
            for widget in (self.app.back_button, self.app.primary_button, self.app.dock):
                bottom = widget.winfo_rooty() - self.app.winfo_rooty() + widget.winfo_height()
                self.assertTrue(widget.winfo_ismapped(), (geometry, widget))
                self.assertLessEqual(bottom, self.app.winfo_height(), (geometry, bottom))
            badge_right = (
                self.app.brand_header.preview_badge.winfo_rootx()
                - self.app.winfo_rootx()
                + self.app.brand_header.preview_badge.winfo_width()
            )
            self.assertLessEqual(badge_right, self.app.winfo_width(), geometry)
        self.app.geometry("900x640")
        self.app.update()
        self.assertEqual(self.app.brand_header.mark_image.width(), 46)
        self.assertEqual(self.app.brand_header.mark_image.height(), 46)

        def cancellable_worker(report, cancelled):
            report(30, "Test operation", "checkpoint")
            while not cancelled():
                time.sleep(0.01)
            raise CancelledOperation("Test operation cancelled.")

        self.app.start_task("test", "Test operation", cancellable_worker, lambda result: None)
        self.app.update()
        self.assertTrue(self.app.progress.winfo_ismapped())
        self.assertTrue(self.app.cancel_button.winfo_ismapped())
        self.app.cancel_task()
        self.wait_for_task()
        self.assertIn("cancel", self.app.notice_text.casefold())

        self.app.discover_paths(self.paths)
        self.wait_for_task()
        self.assertEqual(len(self.app.state.sources), 2)
        self.assertIn("v3.1 Preview", self.app.brand_header.preview_badge.cget("text"))
        self.assertIn("Use as template", self.app.template_button.cget("text"))
        self.assertEqual(self.app.template_button.cget("background"), C["star"])

        self.app.go(1)
        self.app.start_prepare()
        self.wait_for_task()
        self.assertTrue(self.app.state.prepared)
        self.assertEqual(self.app.state.total_rows, 5)

        self.app.go(2)
        cancelled_filter = {
            "column": "branch",
            "mode": "text",
            "operator": "contains",
            "value": "End",
        }
        real_apply = apply_filters

        def slow_apply(frame, filters):
            time.sleep(0.15)
            return real_apply(frame, filters)

        with patch("mergeguru_lite_v3.app.apply_engine_filters", side_effect=slow_apply):
            self.app.apply_filter_change([cancelled_filter])
            self.app.cancel_task()
            self.wait_for_task()
        self.assertEqual(self.app.state.filters, [])
        self.assertEqual(self.app.state.result_rows, 5)

        self.app.open_filter_dialog()
        dialog = self.app.filter_dialog_window
        dialog.column_var.set("branch")
        dialog.populate()
        self.wait_until(lambda: dialog.current_picker is not None)
        dialog.current_picker.search_var.set("Wa")
        dialog.current_picker.refresh()
        self.assertEqual(
            set(dialog.current_picker.visible),
            {"Waltham", "Watford", "Walnut Creek"},
        )
        dialog.current_picker.select_visible()
        dialog.apply()
        self.wait_for_task()
        self.assertEqual(self.app.state.result_rows, 3)

        self.app.go(3)
        self.app.change_export_format("CSV")
        output = os.path.join(self.folder, "gui_export.csv")
        self.app.state.output_path = output
        self.app.render()
        self.app.start_export()
        self.wait_for_task()
        self.assertTrue(os.path.exists(output))
        self.assertTrue(os.path.exists(os.path.splitext(output)[0] + ".audit.txt"))
        self.assertTrue(self.app.state.saved)
        self.assertEqual(self.app.state.history[0]["rows"], 3)

        project_path = os.path.join(self.folder, "repeat.mergeguru.json")
        payload = build_project_payload(self.app.state, LITE_VERSION)
        save_project(project_path, payload)

        loaded = load_project(project_path)
        paths, warnings = resolve_project_inputs(loaded)
        self.assertFalse(warnings)
        self.app.discover_paths(
            paths,
            project_inputs=loaded["source_inputs"],
            project_payload=loaded,
            project_path=project_path,
        )
        self.wait_for_task()
        self.assertFalse(self.app.state.prepared)
        self.assertEqual(len(self.app.state.pending_filters), 1)

        self.app.go(1)
        self.app.start_prepare()
        self.wait_for_task()
        self.assertTrue(self.app.state.prepared)
        self.assertEqual(len(self.app.state.filters), 1)
        self.assertEqual(self.app.state.result_rows, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
