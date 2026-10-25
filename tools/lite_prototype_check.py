"""Sample-model and mapped-window checks for the isolated Lite prototype."""

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prototypes.lite_redesign.app import LitePrototype
from prototypes.lite_redesign.state import DemoState, Filter, SAMPLE_FILES
from prototypes.lite_redesign.brand import blend
from prototypes.lite_redesign.theme import COLORS as C
from prototypes.lite_redesign.selection import ValueSelection
from prototypes.lite_redesign.category_picker import CategoryPicker


class ValueSelectionChecks(unittest.TestCase):
    def test_prefix_matching_is_case_insensitive_and_not_substring(self):
        selection = ValueSelection(("Water", "Waverley", "waterproof", "AWater", "Other"))
        self.assertEqual(selection.matches(" wa "), ("Water", "waterproof", "Waverley"))
        self.assertEqual(selection.matches("Wa", "Contains"), ("AWater", "Water", "waterproof", "Waverley"))

    def test_hidden_selection_survives_bulk_actions_and_no_results(self):
        selection = ValueSelection(("Water", "Waverley", "West", "North"), ("North",))
        matches = selection.matches("Wa")
        selection.select(matches)
        self.assertEqual(selection.selected, {"North", "Water", "Waverley"})
        selection.clear(selection.matches("unmatched"))
        self.assertEqual(len(selection.selected), 3)
        selection.clear(matches)
        self.assertEqual(selection.selected, {"North"})
        selection.invert(matches)
        self.assertEqual(selection.selected, {"North", "Water", "Waverley"})
        selection.invert(matches)
        self.assertEqual(selection.result(), ("North",))

    def test_blank_value_can_be_included_or_excluded(self):
        selection = ValueSelection(("", "Retail"), ("",))
        self.assertEqual(selection.result(), ("",))
        self.assertTrue(Filter("Team", "is one of", ("",)).matches({"Team": ""}))
        self.assertFalse(Filter("Team", "is not one of", ("",)).matches({"Team": ""}))

    def test_exclude_prefix_group_keeps_other_values(self):
        state = DemoState()
        selection = ValueSelection(str(row["Branch"]) for row in state.rows())
        selection.select(selection.matches("Wa"))
        state.filters = [Filter("Branch", "is not one of", selection.result())]
        self.assertEqual(len(state.filtered_rows()), 6)
        self.assertEqual({row["Branch"] for row in state.filtered_rows()}, {"North Central", "West End"})

    def test_large_selection_actions_cover_all_matches(self):
        selection = ValueSelection([f"Wa{index:05d}" for index in range(10000)] + [f"Ze{index:05d}" for index in range(10000)])
        selection.select(selection.matches("Wa"))
        self.assertEqual(len(selection.selected), 10000)
        selection.clear(selection.matches("Ze"))
        self.assertEqual(len(selection.selected), 10000)


class BrandThemeChecks(unittest.TestCase):
    def test_gradient_endpoints_and_clamping(self):
        self.assertEqual(blend(C["blue"], C["cyan"], 0), C["blue"])
        self.assertEqual(blend(C["blue"], C["cyan"], 1), C["cyan"])
        self.assertEqual(blend(C["blue"], C["cyan"], -1), C["blue"])
        self.assertEqual(blend(C["blue"], C["cyan"], 2), C["cyan"])

    def test_text_contrast_target(self):
        def luminance(hex_value):
            channels = [int(hex_value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
            return sum(weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), linear))
        for foreground, background in (("ink", "paper"), ("muted", "paper"),
                                      ("surface", "blue"), ("cyan", "navy"),
                                      ("amber", "amber_wash"), ("green", "green_wash")):
            values = sorted((luminance(C[foreground]), luminance(C[background])))
            self.assertGreaterEqual((values[1] + 0.05) / (values[0] + 0.05), 4.5, (foreground, background))

    def test_semantic_colors_remain_distinct(self):
        self.assertNotEqual(C["blue"], C["green"])
        self.assertNotEqual(C["blue"], C["amber"])
        self.assertNotEqual(C["blue"], C["star"])


class SampleModelChecks(unittest.TestCase):
    def test_source_exclusion_and_template_repair(self):
        state = DemoState(prepared=True)
        state.select_sources(SAMPLE_FILES[1:])
        self.assertEqual(state.template, SAMPLE_FILES[1])
        self.assertEqual(len(state.rows()), 12)
        self.assertFalse(state.prepared)

    def test_extra_column_setting_keeps_all_rows(self):
        state = DemoState(allow_extra=False)
        self.assertEqual(len(state.rows()), 18)
        self.assertNotIn("Team", state.columns())

    def test_filters_intersect_and_keep_identifiers(self):
        state = DemoState(filters=[Filter("Region", "is one of", ("North",)),
                                  Filter("Status", "is one of", ("Active",))])
        self.assertEqual(len(state.filtered_rows()), 4)
        self.assertTrue(all(row["Customer ID"].startswith("00") for row in state.filtered_rows()))

    def test_format_preferences_and_repeat_export(self):
        state = DemoState(prepared=True)
        state.choose_format("CSV-Unique text")
        state.mark_exported()
        self.assertTrue(state.saved)
        state.next_filename()
        self.assertEqual(state.filename, "Merged_January_02.csv")
        self.assertFalse(state.saved)
        self.assertTrue(state.prepared)
        state.choose_format("Excel")
        state.choose_format("CSV-Unique text")
        self.assertEqual(state.protected, {"Customer ID"})

    def test_invalid_export_is_rejected_without_history(self):
        state = DemoState(prepared=True)
        for name in ("", " ", "CON.xlsx", "a/b.xlsx", "wrong.csv", "output.xlsx "):
            state.filename = name
            with self.assertRaises(ValueError, msg=name):
                state.mark_exported()
        self.assertFalse(state.history)

    def test_no_matching_rows_and_no_protected_columns(self):
        state = DemoState(prepared=True, filters=[Filter("Region", "contains", ("unknown",))])
        with self.assertRaises(ValueError):
            state.mark_exported()
        state.filters.clear()
        state.choose_format("CSV-Unique text")
        state.protected.clear()
        with self.assertRaises(ValueError):
            state.mark_exported()

    def test_missing_filter_column_cannot_export_unfiltered_rows(self):
        state = DemoState(prepared=True, allow_extra=False,
                          filters=[Filter("Team", "is not one of", ("Retail",))])
        self.assertTrue(state.filter_problem())
        self.assertEqual(state.filtered_rows(), [])
        with self.assertRaisesRegex(ValueError, "Team"):
            state.mark_exported()

    def test_filter_description_is_bounded_for_large_selections(self):
        item = Filter("Branch", "is not one of", tuple(f"Wa{index:05d}" for index in range(20000)))
        self.assertLess(len(item.description()), 160)
        self.assertIn("19997 more", item.description())


class WindowChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = LitePrototype()
        cls.errors = []
        cls.app.report_callback_exception = lambda *args: cls.errors.append(args)
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()
        if cls.errors:
            raise AssertionError(f"Tk callback errors: {cls.errors}")

    def setUp(self):
        app = self.app
        if app.timer:
            app.after_cancel(app.timer)
            app.timer = None
        if app.dialog and app.dialog.winfo_exists():
            app.dialog.destroy()
        app.demo = DemoState()
        app.step, app.busy, app.stopping = 0, False, False
        app.performance_open = app.source_preview_open = False
        app.preview_limit = 10
        app.filter_undo = None
        app.notice_text = ""
        app.geometry("1060x780")
        app.render()
        app.update()

    def finish_task(self):
        app = self.app
        if app.timer:
            app.after_cancel(app.timer)
            app.timer = None
        app.started -= 10
        app.tick()
        app.update()

    def test_brand_header_fits_and_mark_renders(self):
        app = self.app
        self.assertEqual((app.brand_icon.width(), app.brand_icon.height()), (64, 64))
        self.assertFalse(app.brand_icon.transparency_get(32, 56))
        for size in ("720x560", "900x640", "1060x780"):
            app.geometry(size)
            app.update()
            header = app.brand_header
            self.assertEqual(header.cget("bg"), C["navy"])
            self.assertTrue(header.mark.find_withtag("merge-mark"))
            right = header.preview_badge.winfo_rootx() - app.winfo_rootx() + header.preview_badge.winfo_width()
            self.assertLessEqual(right, app.winfo_width())
            self.assertGreater(header.band.winfo_width(), 1)

    def test_workspace_stacks_without_losing_state(self):
        app = self.app
        app.demo.prepared = True
        for step, attribute in ((2, "filter_workspace"), (3, "export_workspace")):
            app.go(step)
            app.update()
            workspace = getattr(app, attribute)
            self.assertTrue(workspace.wide)
            self.assertEqual(workspace.right.grid_info()["row"], 0)
            app.geometry("720x560")
            app.update()
            self.assertFalse(workspace.wide)
            self.assertEqual(workspace.right.grid_info()["row"], 1)
            for panel in (workspace.left, workspace.right):
                right = panel.winfo_rootx() - app.winfo_rootx() + panel.winfo_width()
                self.assertLessEqual(right, app.winfo_width())
            app.geometry("1060x780")
            app.update()
            self.assertTrue(workspace.wide)
        self.assertTrue(app.demo.prepared)
        self.assertEqual(app.demo.output_format, "Excel")

    def test_source_preview_tracks_selection(self):
        app = self.app
        self.assertIsNone(app.source_preview_table)
        app.source_preview_button.invoke()
        app.update()
        self.assertTrue(app.source_preview_table.winfo_ismapped())
        self.assertEqual(len(app.source_preview_table.get_children()), 3)
        app.source_table.selection_set(SAMPLE_FILES[1])
        app.update()
        self.assertIn(SAMPLE_FILES[1], app.source_summary.cget("text"))
        item = app.source_preview_table.get_children()[0]
        self.assertIn("South", app.source_preview_table.item(item, "values"))
        app.set_template()
        self.assertEqual(app.demo.template, SAMPLE_FILES[1])

    def test_advanced_settings_and_recommendations(self):
        app = self.app
        app.go(1)
        app.update()
        self.assertFalse(app.performance_body.winfo_ismapped())
        app.performance_button.invoke()
        app.update()
        self.assertTrue(app.performance_body.winfo_ismapped())
        app.demo.prepared = True
        app.demo.parallel, app.demo.optimize_memory, app.demo.quality_checks = True, False, True
        app.recommended_settings()
        self.assertEqual((app.demo.parallel, app.demo.optimize_memory, app.demo.quality_checks), (False, True, False))
        self.assertFalse(app.demo.prepared)
        self.assertTrue(app.performance_open)

    def test_checkbox_labels_use_available_width_on_first_render(self):
        app = self.app
        app.go(1)
        app.update()
        checkbox = app.layout_check
        self.assertGreaterEqual(int(checkbox.cget("wraplength")), checkbox.winfo_width() - 35)
        self.assertLess(checkbox.winfo_height(), 55)

    def test_filter_undo_and_draft_count(self):
        app = self.app
        app.demo.prepared = True
        app.go(2)
        app.filter_dialog()
        app.filter_column.set("Branch")
        app.filter_column_combo.event_generate("<<ComboboxSelected>>")
        app.filter_picker.search_var.set("Wa")
        app.filter_picker.select_visible()
        self.assertIn("12 of 18", app.filter_result_count.cget("text"))
        app.filter_apply()
        self.assertEqual(len(app.demo.filtered_rows()), 12)
        app.clear_filters()
        self.assertFalse(app.demo.filters)
        app.undo_filter_change()
        self.assertEqual(len(app.demo.filtered_rows()), 12)
        self.assertTrue(app.demo.prepared)
        self.assertIsNone(app.filter_undo)

    def test_preview_row_count_and_copy_without_touching_real_clipboard(self):
        app = self.app
        app.demo.prepared = True
        app.go(2)
        app.preview_count_combo.set("5")
        app.preview_count_combo.event_generate("<<ComboboxSelected>>")
        app.update()
        self.assertEqual(len(app.preview_table.get_children()), 5)
        table = app.preview_table
        table.selection_set(table.get_children()[:2])
        app.update()
        self.assertEqual(app.copy_button.cget("state"), "normal")
        with patch.object(app, "clipboard_clear") as clear, patch.object(app, "clipboard_append") as append:
            app.copy_preview(table)
        clear.assert_called_once()
        content = append.call_args.args[0]
        self.assertTrue(content.startswith("Customer ID\tRegion\t"))
        self.assertEqual(len(content.splitlines()), 3)
        app.go(3)
        self.assertEqual(app.preview_limit, 5)
        self.assertEqual(len(app.preview_table.get_children()), 5)

    def test_idle_dock_expands_only_when_processing_and_reports_locks(self):
        app = self.app
        self.assertFalse(app.progress.winfo_ismapped())
        self.assertIn("Prepare data", app.step_states[2].cget("text"))
        app.go(1)
        app.primary()
        app.update()
        self.assertTrue(app.progress.winfo_ismapped())
        self.assertTrue(app.cancel_button.winfo_ismapped())
        self.assertIn("Processing", app.next_hint.cget("text"))
        self.finish_task()
        self.assertFalse(app.progress.winfo_ismapped())
        self.assertFalse(app.cancel_button.winfo_ismapped())
        self.assertEqual(app.step_states[1].cget("text"), "Ready")

    def test_keyboard_value_selection_and_unsaved_close_before_export(self):
        app = self.app
        app.demo.prepared = True
        app.go(2)
        app.keyboard_filter()
        picker = app.filter_picker
        picker.search_var.set("No")
        picker.focus_matches()
        picker.space_value(None)
        self.assertEqual(picker.selection.selected, {"North"})
        app.filter_apply()
        app.request_close()
        self.assertTrue(app.dialog.winfo_exists())
        self.assertTrue(app.winfo_exists())
        app.dialog.destroy()

    def test_missing_filter_column_shows_remediation_and_blocks_export(self):
        app = self.app
        app.demo.prepared, app.demo.allow_extra = True, False
        app.demo.filters = [Filter("Team", "is not one of", ("Retail",))]
        app.go(2)
        self.assertEqual(app.primary_button.cget("state"), "disabled")
        self.assertIn("Team", app.next_hint.cget("text"))
        app.primary()
        self.assertEqual(app.step, 2)
        app.go(3)
        app.primary()
        self.assertFalse(app.busy)
        self.assertFalse(app.demo.history)

    def test_navigation_and_progress_stay_visible_at_small_sizes(self):
        app = self.app
        app.demo.prepared = True
        for size in ("720x560", "900x640", "1060x780"):
            app.geometry(size)
            for step in range(4):
                app.go(step)
                app.update()
                for widget in (app.primary_button, app.back_button, app.dock):
                    bottom = widget.winfo_rooty() - app.winfo_rooty() + widget.winfo_height()
                    self.assertTrue(widget.winfo_ismapped(), (size, step, widget))
                    self.assertLessEqual(bottom, app.winfo_height(), (size, step, bottom))
                right = app.steps[-1].winfo_rootx() - app.winfo_rootx() + app.steps[-1].winfo_width()
                self.assertLessEqual(right, app.winfo_width(), (size, right))

    def test_layout_fields_are_conditional(self):
        app = self.app
        app.go(1)
        app.update()
        self.assertFalse(app.layout_fields.winfo_ismapped())
        app.layout_check.invoke()
        app.update()
        self.assertTrue(app.layout_fields.winfo_ismapped())

    def test_prepare_cancel_retry_and_invalidation(self):
        app = self.app
        app.go(1)
        app.primary()
        self.assertTrue(app.busy)
        self.assertEqual(app.primary_button.cget("state"), "disabled")
        self.assertEqual(app.cancel_button.cget("state"), "normal")
        app.go(3)
        self.assertEqual(app.step, 1)
        app.cancel()
        self.assertTrue(app.busy)
        self.assertTrue(app.stopping)
        self.assertEqual(app.cancel_button.cget("state"), "disabled")
        app.after(500, app.quit)
        app.mainloop()
        self.assertFalse(app.busy)
        self.assertFalse(app.demo.prepared)
        app.primary()
        self.finish_task()
        self.assertTrue(app.demo.prepared)
        app.primary()
        self.assertEqual(app.step, 2)
        app.go(1)
        app.change_setting("parallel", True)
        self.assertFalse(app.demo.prepared)
        app.go(3)
        self.assertEqual(app.step, 1)

    def test_inline_picker_and_format_preference(self):
        app = self.app
        app.demo.prepared = True
        app.go(3)
        self.assertFalse(app.protected_picker.winfo_ismapped())
        app.format_var.set("CSV-Unique text")
        app.change_format()
        app.update()
        self.assertTrue(app.protected_picker.winfo_ismapped())
        self.assertEqual(app.protected_picker.master, app.format_combo.master)
        self.assertGreater(app.protected_picker.winfo_y(), app.format_combo.winfo_y())
        app.go(2)
        app.go(3)
        self.assertEqual(app.format_var.get(), "CSV-Unique text")
        self.assertEqual(app.demo.protected, {"Customer ID"})

    def test_filter_add_edit_and_fixed_dialog_footer(self):
        app = self.app
        app.demo.prepared = True
        app.go(2)
        app.filter_dialog()
        app.filter_picker.selection.toggle("North")
        app.filter_apply()
        self.assertEqual(len(app.demo.filtered_rows()), 6)
        app.filter_dialog(0)
        app.filter_picker.selection.toggle("North")
        app.filter_picker.selection.toggle("South")
        app.filter_apply()
        self.assertEqual(app.demo.filters[0].values, ("South",))
        app.filter_dialog()
        app.filter_column.set("Customer ID")
        app.filter_column_combo.event_generate("<<ComboboxSelected>>")
        app.dialog.geometry("420x400")
        app.update()
        button = app.filter_apply_button
        bottom = button.winfo_rooty() - app.dialog.winfo_rooty() + button.winfo_height()
        self.assertLessEqual(bottom, app.dialog.winfo_height())
        app.dialog.destroy()
        app.clear_filters()
        self.assertEqual(len(app.demo.filtered_rows()), 18)

    def test_search_select_and_exclude_matches(self):
        app = self.app
        app.demo.prepared = True
        app.go(2)
        app.filter_dialog()
        app.filter_column.set("Branch")
        app.filter_column_combo.event_generate("<<ComboboxSelected>>")
        picker = app.filter_picker
        picker.search_var.set("wa")
        picker.select_visible()  # Flushes the debounce before applying a bulk action.
        self.assertEqual(len(picker.selection.selected), 4)
        self.assertNotIn("West End", picker.selection.selected)
        app.filter_apply()
        self.assertEqual(len(app.demo.filtered_rows()), 12)
        app.filter_dialog(0)
        self.assertEqual(len(app.filter_picker.selection.selected), 4)
        app.filter_operator.set("Exclude selected values")
        app.filter_operator_combo.event_generate("<<ComboboxSelected>>")
        self.assertEqual(len(app.filter_picker.selection.selected), 4)
        app.filter_apply()
        self.assertEqual(len(app.demo.filtered_rows()), 6)
        self.assertEqual(app.demo.filters[0].operator, "is not one of")

    def test_search_preserves_hidden_selections_and_column_drafts(self):
        app = self.app
        app.demo.prepared = True
        app.go(2)
        app.filter_dialog()
        app.filter_column.set("Branch")
        app.filter_column_combo.event_generate("<<ComboboxSelected>>")
        picker = app.filter_picker
        picker.search_var.set("North")
        picker.select_visible()
        picker.search_var.set("Wa")
        picker.select_visible()
        self.assertEqual(len(picker.selection.selected), 5)
        picker.clear_visible()
        self.assertEqual(picker.selection.selected, {"North Central"})
        picker.search_var.set("no match")
        picker.refresh()
        self.assertEqual(picker.select_button.cget("state"), "disabled")
        app.filter_column.set("Status")
        app.filter_column_combo.event_generate("<<ComboboxSelected>>")
        app.filter_column.set("Branch")
        app.filter_column_combo.event_generate("<<ComboboxSelected>>")
        self.assertEqual(app.filter_picker.selection.selected, {"North Central"})
        self.assertEqual(app.filter_picker.search_var.get(), "no match")
        app.filter_apply()
        self.assertEqual(len(app.demo.filtered_rows()), 3)

    def test_paged_picker_bulk_selection_and_dialog_layout(self):
        app = self.app
        dialog = app.new_dialog("Large sample value list")
        selection = ValueSelection([f"Wa{index:05d}" for index in range(10000)] + [f"Ze{index:05d}" for index in range(10000)])
        picker = CategoryPicker(dialog, selection, app.button)
        picker.pack(fill="both", expand=True)
        picker.search_var.set("Wa")
        picker.select_visible()
        self.assertEqual(len(selection.selected), 10000)
        self.assertEqual(len(picker.tree.get_children()), 250)
        picker.show_more()
        self.assertEqual(len(picker.tree.get_children()), 500)
        picker.search_var.set("missing")
        picker.refresh()
        self.assertEqual(len(picker.tree.get_children()), 0)
        self.assertEqual(len(selection.selected), 10000)
        dialog.destroy()
        app.demo.prepared = True
        app.go(2)
        app.filter_dialog()
        app.dialog.geometry("420x500")
        app.update()
        for button in (app.filter_apply_button, app.filter_picker.select_button, app.filter_picker.clear_button, app.filter_picker.invert_button):
            right = button.winfo_rootx() - app.dialog.winfo_rootx() + button.winfo_width()
            bottom = button.winfo_rooty() - app.dialog.winfo_rooty() + button.winfo_height()
            self.assertLessEqual(right, app.dialog.winfo_width())
            self.assertLessEqual(bottom, app.dialog.winfo_height())
        self.assertGreater(app.filter_picker.tree.winfo_height(), 40)

    def test_text_mode_switch_keeps_category_draft_and_rejects_empty_text(self):
        app = self.app
        app.demo.prepared = True
        app.go(2)
        app.filter_dialog()
        app.filter_column.set("Branch")
        app.filter_column_combo.event_generate("<<ComboboxSelected>>")
        app.filter_picker.search_var.set("Wa")
        app.filter_picker.select_visible()
        app.filter_operator.set("Text contains")
        app.filter_operator_combo.event_generate("<<ComboboxSelected>>")
        app.update()
        self.assertIsNone(app.filter_picker)
        app.filter_apply()
        self.assertFalse(app.demo.filters)
        self.assertTrue(app.dialog.winfo_exists())
        app.filter_operator.set("Include selected values")
        app.filter_operator_combo.event_generate("<<ComboboxSelected>>")
        app.update()
        self.assertEqual(len(app.filter_picker.selection.selected), 4)
        self.assertEqual(app.filter_picker.search_var.get(), "Wa")
        app.filter_operator.set("Text contains")
        app.filter_operator_combo.event_generate("<<ComboboxSelected>>")
        app.filter_term.set("wa")
        app.filter_apply()
        self.assertEqual(len(app.demo.filtered_rows()), 12)

    def test_export_cancel_success_repeat_and_unsaved_close(self):
        app = self.app
        app.demo.prepared = True
        app.go(3)
        app.primary()
        app.cancel()
        app.after(500, app.quit)
        app.mainloop()
        self.assertFalse(app.demo.history)
        app.primary()
        self.finish_task()
        self.assertTrue(app.demo.saved)
        self.assertEqual(app.primary_button.cget("text"), "Finish (Close)")
        app.export_again()
        self.assertEqual(app.step, 2)
        self.assertTrue(app.demo.prepared)
        self.assertEqual(app.demo.filename, "Merged_January_02.xlsx")
        app.go(3)
        app.request_close()
        self.assertTrue(app.winfo_exists())
        self.assertTrue(app.dialog.winfo_exists())
        app.dialog.destroy()

    def test_empty_selection_and_invalid_output(self):
        app = self.app
        app.demo.select_sources([])
        app.render()
        self.assertEqual(app.primary_button.cget("state"), "disabled")
        app.primary()
        self.assertEqual(app.step, 0)
        app.reset_sources()
        app.demo.prepared = True
        app.go(3)
        app.filename_var.set("CON.xlsx")
        app.primary()
        self.assertFalse(app.busy)
        self.assertEqual(app.notice_kind, "warning")
        self.assertFalse(app.demo.history)


if __name__ == "__main__":
    unittest.main(verbosity=2)
