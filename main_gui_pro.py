#!/usr/bin/env python3
"""MergeGuru Pro: modern PySide6 interface using the shared MergeGuru engine."""

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QEasingCurve,
    QModelIndex,
    QObject,
    QPropertyAnimation,
    QSettings,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QSizePolicy,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QStyle,
)

import mergeguru_engine as engine


APP_VERSION = engine.APP_VERSION
STEPS = [
    ("01", "Select Data", "Choose a folder or specific files"),
    ("02", "Discover Sources", "Review files and choose a reference"),
    ("03", "Reference Sheet", "Set the expected sheet and layout"),
    ("04", "Validate Files", "Catch schema and file issues"),
    ("05", "Combine & Filter", "Combine, refine, and preview"),
    ("06", "Export", "Save output and audit report"),
]

def resource_path(relative_path):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


def load_pro_theme():
    theme_path = resource_path(Path("assets") / "mergeguru_pro.qss")
    try:
        return theme_path.read_text(encoding="utf-8")
    except OSError:
        return (
            "QWidget{background:#071018;color:#e9f1f7;font-family:'Segoe UI';}"
            "QPushButton{padding:8px;} QTableView,QTableWidget{background:#0c1b25;}"
        )


class WorkerSignals(QObject):
    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)


class StepButton(QPushButton):
    def __init__(self, number, title, subtitle, standard_icon, parent=None):
        super().__init__(parent)
        self.number = number
        self.title = title
        self.subtitle = subtitle
        self.setObjectName("stepCard")
        self.setIcon(self.style().standardIcon(standard_icon))
        self.setText(f"{number}   {title}")
        self.setProperty("state", "locked")
        self.setProperty("active", False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def set_visual_state(self, active, state):
        self.setProperty("active", active)
        self.setProperty("state", state)
        marker = "  OK" if state == "completed" else "  !" if state == "attention" else ""
        self.setText(f"{self.number}   {self.title}{marker}")
        self.style().unpolish(self)
        self.style().polish(self)


class StatusChip(QLabel):
    def __init__(self, kind, text="0", parent=None):
        super().__init__(text, parent)
        self.setObjectName("statusChip")
        self.setProperty("kind", kind)
        self.setAlignment(Qt.AlignCenter)


class DataFrameModel(QAbstractTableModel):
    def __init__(self, dataframe=None, parent=None):
        super().__init__(parent)
        self._dataframe = dataframe

    def set_dataframe(self, dataframe):
        self.beginResetModel()
        self._dataframe = dataframe
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() or self._dataframe is None:
            return 0
        return len(self._dataframe.index)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid() or self._dataframe is None:
            return 0
        return len(self._dataframe.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self._dataframe is None:
            return None
        if role == Qt.DisplayRole:
            value = self._dataframe.iat[index.row(), index.column()]
            return "" if pd.isna(value) else str(value)
        if role == Qt.TextAlignmentRole:
            return Qt.AlignLeft | Qt.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if self._dataframe is None or role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and section < len(self._dataframe.columns):
            return str(self._dataframe.columns[section])
        if orientation == Qt.Vertical:
            return str(section + 1)
        return None


class Toast(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 11, 12, 11)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        dismiss = QPushButton("Dismiss")
        dismiss.clicked.connect(self.dismiss)
        layout.addWidget(dismiss)
        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.animation = QPropertyAnimation(self.opacity, b"opacity", self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.finished.connect(self._animation_finished)
        self._hide_after_animation = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self.hide()

    def show_message(self, message, timeout_ms=4500):
        self.label.setText(message)
        self.adjustSize()
        self.show()
        self.raise_()
        self._hide_after_animation = False
        self.opacity.setOpacity(0.0)
        self.animation.stop()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()
        self.timer.start(timeout_ms)

    def dismiss(self):
        self.timer.stop()
        self.animation.stop()
        self._hide_after_animation = True
        self.animation.setStartValue(self.opacity.opacity())
        self.animation.setEndValue(0.0)
        self.animation.start()

    def _animation_finished(self):
        if self._hide_after_animation:
            self.hide()


class DropZone(QFrame):
    pathsDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.pathsDropped.emit(paths)
            event.acceptProposedAction()


class FilterDialog(QDialog):
    MAX_CATEGORY_VALUES = 20_000

    def __init__(self, columns, dataframe, existing=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Filter" if existing else "Add Filter")
        self.setMinimumSize(560, 650)
        if parent is not None:
            self.setWindowIcon(parent.windowIcon())
        self.dataframe = dataframe
        self.existing = existing
        self.config = None
        self.all_category_values = []
        self.selected_category_values = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        heading = QLabel("Choose what should remain in the export")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        help_text = QLabel(
            "Pick a column and choose the filter style that best matches the data."
        )
        help_text.setObjectName("subtitle")
        layout.addWidget(help_text)

        selector_card = QFrame(objectName="card")
        form = QFormLayout(selector_card)
        form.setContentsMargins(18, 16, 18, 16)
        self.column = QComboBox()
        self.column.addItems(columns)
        if existing:
            self.column.setCurrentText(existing["column"])
        self.column.currentTextChanged.connect(self._refresh_filter_editor)
        form.addRow("Column", self.column)
        self.mode = QComboBox()
        self.mode.addItem("Category - pick values", "category")
        self.mode.addItem("Text / ID", "text")
        self.mode.addItem("Date", "date")
        if existing:
            index = self.mode.findData(existing["mode"])
            self.mode.setCurrentIndex(max(0, index))
        self.mode.currentIndexChanged.connect(self._refresh_filter_editor)
        form.addRow("Filter type", self.mode)
        layout.addWidget(selector_card)

        self.editor_stack = QStackedWidget()
        self.editor_stack.setObjectName("filterEditor")
        self.editor_stack.addWidget(self._category_editor())
        self.editor_stack.addWidget(self._text_editor())
        self.editor_stack.addWidget(self._date_editor())
        layout.addWidget(self.editor_stack, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        add = QPushButton("Save Filter" if existing else "Add Filter")
        add.setObjectName("primary")
        add.clicked.connect(self._accept)
        actions.addWidget(add)
        layout.addLayout(actions)
        self._refresh_filter_editor()

    def _category_editor(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        self.category_action = QComboBox()
        self.category_action.addItem("Include selected values", "include")
        self.category_action.addItem("Exclude selected values", "exclude")
        layout.addWidget(self.category_action)
        self.category_search = QLineEdit()
        self.category_search.setPlaceholderText("Search available values")
        layout.addWidget(self.category_search)
        action_row = QHBoxLayout()
        select_all = QPushButton("Select Visible")
        select_all.clicked.connect(lambda: self._select_visible_categories(True))
        action_row.addWidget(select_all)
        clear = QPushButton("Clear Visible")
        clear.clicked.connect(lambda: self._select_visible_categories(False))
        action_row.addWidget(clear)
        invert = QPushButton("Invert Visible")
        invert.clicked.connect(self._invert_visible_categories)
        action_row.addWidget(invert)
        action_row.addStretch()
        self.category_count = QLabel("0 selected")
        self.category_count.setObjectName("muted")
        action_row.addWidget(self.category_count)
        layout.addLayout(action_row)
        self.category_list = QListWidget()
        self.category_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.category_list.itemSelectionChanged.connect(self._remember_category_selection)
        layout.addWidget(self.category_list, 1)
        self.category_hint = QLabel("")
        self.category_hint.setObjectName("muted")
        self.category_hint.setWordWrap(True)
        layout.addWidget(self.category_hint)
        self.category_timer = QTimer(self)
        self.category_timer.setSingleShot(True)
        self.category_timer.setInterval(150)
        self.category_timer.timeout.connect(self._render_category_values)
        self.category_search.textChanged.connect(lambda: self.category_timer.start())
        return page

    def _text_editor(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 10, 0, 0)
        self.text_operator = QComboBox()
        for label, value in [
            ("Equals", "equals"),
            ("Does not equal", "not_equals"),
            ("Contains", "contains"),
            ("Starts with", "starts_with"),
            ("Include list (comma-separated)", "paste_include"),
            ("Exclude list (comma-separated)", "paste_exclude"),
        ]:
            self.text_operator.addItem(label, value)
        form.addRow("Condition", self.text_operator)
        self.text_value = QLineEdit()
        self.text_value.setPlaceholderText("Enter one value, or a comma-separated list")
        form.addRow("Value", self.text_value)
        hint = QLabel("Contains is case-insensitive. Equals and list matching preserve exact text.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        form.addRow("", hint)
        return page

    def _date_editor(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 10, 0, 0)
        self.date_operator = QComboBox()
        for label, value in [
            ("Equals", "equals"),
            ("Before", "before"),
            ("After", "after"),
            ("Between", "between"),
        ]:
            self.date_operator.addItem(label, value)
        self.date_operator.currentIndexChanged.connect(self._toggle_second_date)
        form.addRow("Condition", self.date_operator)
        self.date1 = QDateEdit()
        self.date1.setCalendarPopup(True)
        self.date1.setDisplayFormat("yyyy-MM-dd")
        self.date1.setDate(QDate.currentDate())
        form.addRow("Date 1", self.date1)
        self.date2 = QDateEdit()
        self.date2.setCalendarPopup(True)
        self.date2.setDisplayFormat("yyyy-MM-dd")
        self.date2.setDate(QDate.currentDate())
        form.addRow("Date 2", self.date2)
        self._toggle_second_date()
        return page

    def _refresh_filter_editor(self):
        if not hasattr(self, "editor_stack"):
            return
        mode = self.mode.currentData()
        self.editor_stack.setCurrentIndex({"category": 0, "text": 1, "date": 2}[mode])
        if mode == "category":
            self._load_category_values()
        self._load_existing_values()

    def _load_existing_values(self):
        if not self.existing:
            return
        if self.existing["column"] != self.column.currentText():
            return
        mode = self.existing["mode"]
        if mode == "category":
            self.category_action.setCurrentIndex(
                max(0, self.category_action.findData(self.existing.get("action", "include")))
            )
            self.selected_category_values = set(self.existing.get("values", []))
            self._render_category_values()
        elif mode == "text":
            self.text_operator.setCurrentIndex(
                max(0, self.text_operator.findData(self.existing.get("operator", "equals")))
            )
            value = self.existing.get("value")
            if value is None:
                value = ",".join(self.existing.get("values", []))
            self.text_value.setText(value)
        elif mode == "date":
            self.date_operator.setCurrentIndex(
                max(0, self.date_operator.findData(self.existing.get("operator", "equals")))
            )
            date1 = QDate.fromString(self.existing.get("date1", ""), "yyyy-MM-dd")
            date2 = QDate.fromString(self.existing.get("date2", ""), "yyyy-MM-dd")
            if date1.isValid():
                self.date1.setDate(date1)
            if date2.isValid():
                self.date2.setDate(date2)

    def _load_category_values(self):
        current_column = self.column.currentText()
        if getattr(self, "_category_column", None) != current_column:
            if not self.existing or self.existing.get("column") != current_column:
                self.selected_category_values.clear()
            self._category_column = current_column
        try:
            self.all_category_values = sorted(
                self.dataframe[current_column]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )
        except Exception:
            self.all_category_values = []
        if len(self.all_category_values) > self.MAX_CATEGORY_VALUES:
            self.category_hint.setText(
                f"This column has {len(self.all_category_values):,} unique values. "
                "Use Text / ID instead of loading a very large pick-list."
            )
            self.category_list.clear()
            self.category_list.setEnabled(False)
        else:
            self.category_hint.setText(
                f"{len(self.all_category_values):,} unique value(s) available."
            )
            self.category_list.setEnabled(True)
            self._render_category_values()

    def _remember_category_selection(self):
        visible = {
            self.category_list.item(index).text()
            for index in range(self.category_list.count())
        }
        selected = {item.text() for item in self.category_list.selectedItems()}
        self.selected_category_values.difference_update(visible)
        self.selected_category_values.update(selected)
        self.category_count.setText(f"{len(self.selected_category_values):,} selected")

    def _render_category_values(self):
        if len(self.all_category_values) > self.MAX_CATEGORY_VALUES:
            return
        search = self.category_search.text().strip().lower()
        visible = [
            value for value in self.all_category_values
            if not search or search in value.lower()
        ]
        self.category_list.blockSignals(True)
        self.category_list.clear()
        for value in visible:
            item = QListWidgetItem(value)
            self.category_list.addItem(item)
            if value in self.selected_category_values:
                item.setSelected(True)
        self.category_list.blockSignals(False)
        self.category_count.setText(f"{len(self.selected_category_values):,} selected")

    def _select_visible_categories(self, selected):
        for index in range(self.category_list.count()):
            self.category_list.item(index).setSelected(selected)
        self._remember_category_selection()

    def _invert_visible_categories(self):
        for index in range(self.category_list.count()):
            item = self.category_list.item(index)
            item.setSelected(not item.isSelected())
        self._remember_category_selection()

    def _toggle_second_date(self):
        self.date2.setEnabled(self.date_operator.currentData() == "between")

    def _accept(self):
        column = self.column.currentText()
        mode = self.mode.currentData()
        if mode == "category":
            self._remember_category_selection()
            if not self.selected_category_values:
                QMessageBox.warning(self, "No values selected", "Select at least one value.")
                return
            self.config = {
                "column": column,
                "mode": "category",
                "action": self.category_action.currentData(),
                "values": sorted(self.selected_category_values),
            }
        elif mode == "text":
            value = self.text_value.text().strip()
            if not value:
                QMessageBox.warning(self, "Missing value", "Enter a filter value.")
                return
            operator = self.text_operator.currentData()
            self.config = {"column": column, "mode": "text", "operator": operator}
            if operator in {"paste_include", "paste_exclude"}:
                values = [part.strip() for part in value.split(",") if part.strip()]
                if not values:
                    QMessageBox.warning(self, "Empty list", "Enter at least one value.")
                    return
                self.config["values"] = values
            else:
                self.config["value"] = value
        else:
            date1 = self.date1.date().toString("yyyy-MM-dd")
            date2 = self.date2.date().toString("yyyy-MM-dd")
            self.config = {
                "column": column,
                "mode": "date",
                "operator": self.date_operator.currentData(),
                "date1": date1,
                "date2": date2,
            }
        self.accept()


class MergeGuruPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MergeGuru", "MergeGuru Pro")
        self.current_step = 0
        self.max_unlocked_step = 0
        self.selected_paths = []
        self.source_folder = ""
        self.sources = []
        self.included_source_keys = set()
        self.reference_index = 0
        self.selected_sheet = None
        self.validation = None
        self.validation_signature = None
        self.validation_settings = None
        self.final_df = None
        self.filtered_df = None
        self.filters = []
        self.extra_columns = []
        self.cancel_combine = False
        self.cancel_export = False
        self.busy = False
        self.active_operation = None
        self.attention_step = None
        self._signals = []
        self._page_animation = None
        self._filter_undo = []
        self._filter_redo = []

        self.setWindowTitle(f"MergeGuru Pro {APP_VERSION}")
        self.resize(1220, 790)
        icon = Path(__file__).with_name("assets") / "MergeGuru_v1.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setStyleSheet(load_pro_theme())
        self._build_ui()
        saved_geometry = self.settings.value("window_geometry")
        if saved_geometry:
            self.restoreGeometry(saved_geometry)
        self.source_folder = self.settings.value("last_source_folder", "", str)
        self.last_export_folder = self.settings.value("last_export_folder", "", str)
        if self.source_folder and not os.path.isdir(self.source_folder):
            self.source_folder = ""
        if self.last_export_folder and not os.path.isdir(self.last_export_folder):
            self.last_export_folder = ""
        self._load_user_preferences()
        self._install_shortcuts()
        self._show_step(0)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QFrame(objectName="topbar")
        top.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(24, 10, 24, 10)
        mark = QLabel("MG")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(mark)
        brand = QLabel("MergeGuru")
        brand.setObjectName("brand")
        top_layout.addWidget(brand)
        edition = QLabel(f"PRO  |  {APP_VERSION}")
        edition.setObjectName("chip")
        top_layout.addWidget(edition)
        top_layout.addStretch()
        self.undo_button = QToolButton()
        self.undo_button.setObjectName("headerTool")
        self.undo_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.undo_button.setToolTip("Undo filter change (Ctrl+Z)")
        self.undo_button.clicked.connect(self._undo_filters)
        self.undo_button.setEnabled(False)
        top_layout.addWidget(self.undo_button)
        self.redo_button = QToolButton()
        self.redo_button.setObjectName("headerTool")
        self.redo_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.redo_button.setToolTip("Redo filter change (Ctrl+Shift+Z)")
        self.redo_button.clicked.connect(self._redo_filters)
        self.redo_button.setEnabled(False)
        top_layout.addWidget(self.redo_button)
        local_status = QLabel("Local processing  |  No cloud upload")
        local_status.setObjectName("securityChip")
        top_layout.addWidget(local_status)
        self.status = QLabel("Choose how you want to provide the source data.")
        self.status.setObjectName("topStatus")
        top_layout.addWidget(self.status)
        outer.addWidget(top)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body = QWidget()
        body.setLayout(body_layout)
        outer.addWidget(body, 1)

        sidebar = QFrame(objectName="sidebar")
        sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 24, 0, 20)
        side.setSpacing(2)
        label = QLabel("  WORKFLOW")
        label.setObjectName("eyebrow")
        label.setContentsMargins(18, 0, 0, 10)
        side.addWidget(label)
        self.step_buttons = []
        standard_icons = [
            QStyle.SP_DirOpenIcon,
            QStyle.SP_FileDialogDetailedView,
            QStyle.SP_FileDialogListView,
            QStyle.SP_DialogApplyButton,
            QStyle.SP_BrowserReload,
            QStyle.SP_DialogSaveButton,
        ]
        for index, (number, title, subtitle) in enumerate(STEPS):
            button = StepButton(
                number, title, subtitle, standard_icons[index], sidebar
            )
            button.clicked.connect(lambda checked=False, i=index: self._request_step(i))
            side.addWidget(button)
            self.step_buttons.append(button)
        side.addStretch()
        privacy = QLabel("Files stay on this computer.\nNo API or cloud connection.")
        privacy.setObjectName("muted")
        privacy.setWordWrap(True)
        privacy.setContentsMargins(20, 0, 20, 0)
        side.addWidget(privacy)
        body_layout.addWidget(sidebar, 0)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(42, 30, 42, 22)
        content_layout.setSpacing(16)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._select_page())
        self.stack.addWidget(self._sources_page())
        self.stack.addWidget(self._reference_page())
        self.stack.addWidget(self._validation_page())
        self.stack.addWidget(self._filters_page())
        self.stack.addWidget(self._export_page())
        content_layout.addWidget(self.stack, 1)
        body_layout.addWidget(content, 1)

        footer = QFrame(objectName="footer")
        footer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(24, 8, 24, 8)
        foot.addStretch()
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self._back)
        foot.addWidget(self.back_button)
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(self._next)
        foot.addWidget(self.next_button)
        outer.addWidget(footer)
        self.toast = Toast(root)

    def _install_shortcuts(self):
        shortcuts = [
            ("Ctrl+O", self._browse_files),
            ("Ctrl+Shift+O", self._browse_folder),
            ("Ctrl+Return", self._next),
            ("Alt+Right", self._next),
            ("Alt+Left", self._back),
            ("Escape", self._cancel_active_operation),
            ("Ctrl+Z", self._undo_filters),
            ("Ctrl+Shift+Z", self._redo_filters),
            ("Ctrl+Y", self._redo_filters),
        ]
        self._shortcut_actions = []
        for sequence, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(callback)
            self.addAction(action)
            self._shortcut_actions.append(action)

    def _cancel_active_operation(self):
        if self.active_operation == "combine":
            self._cancel_combine()
        elif self.active_operation == "export":
            self._cancel_export()

    def _notify(self, message, attention_step=None):
        self.toast.show_message(message)
        self._position_toast()
        if attention_step is not None:
            self.attention_step = attention_step
        self.status.setText(message)
        self._update_navigation()

    def _position_toast(self):
        if not hasattr(self, "toast") or self.toast.isHidden():
            return
        margin = 24
        width = min(max(360, self.width() // 3), 520)
        self.toast.setFixedWidth(width)
        self.toast.adjustSize()
        self.toast.move(
            max(margin, self.centralWidget().width() - self.toast.width() - margin),
            margin,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_toast()

    def closeEvent(self, event):
        self._save_user_preferences()
        self.settings.setValue("window_geometry", self.saveGeometry())
        if self.source_folder:
            self.settings.setValue("last_source_folder", self.source_folder)
        if getattr(self, "last_export_folder", ""):
            self.settings.setValue("last_export_folder", self.last_export_folder)
        super().closeEvent(event)

    def _settings_bool(self, key, default=False):
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}

    def _settings_int(self, key, default):
        try:
            return int(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def _load_user_preferences(self):
        pairs = [
            (self.auto_match_sheet, "pref_auto_match_sheet", False),
            (self.layout_fix, "pref_layout_fix", False),
            (self.allow_extra, "pref_allow_extra", False),
            (self.fast_combine, "pref_fast_combine", False),
            (self.optimize_memory, "pref_optimize_memory", True),
        ]
        for widget, key, default in pairs:
            widget.blockSignals(True)
            widget.setChecked(self._settings_bool(key, default))
            widget.blockSignals(False)
        self.header_row.setValue(self._settings_int("pref_header_row", 1))
        self.footer_rows.setValue(self._settings_int("pref_footer_rows", 0))
        export_format = self.settings.value("pref_export_format", "Excel", str)
        if export_format in engine.EXPORT_FORMATS:
            self.export_format.setCurrentText(export_format)
        self._layout_controls_changed()
        self._update_unique_column_visibility()

    def _save_user_preferences(self):
        if not hasattr(self, "allow_extra"):
            return
        self.settings.setValue("pref_auto_match_sheet", self.auto_match_sheet.isChecked())
        self.settings.setValue("pref_layout_fix", self.layout_fix.isChecked())
        self.settings.setValue("pref_header_row", self.header_row.value())
        self.settings.setValue("pref_footer_rows", self.footer_rows.value())
        self.settings.setValue("pref_allow_extra", self.allow_extra.isChecked())
        self.settings.setValue("pref_fast_combine", self.fast_combine.isChecked())
        self.settings.setValue("pref_optimize_memory", self.optimize_memory.isChecked())
        self.settings.setValue("pref_export_format", self.export_format.currentText())

    def _heading(self, step, title, subtitle):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        eye = QLabel(f"STEP {step} OF 6")
        eye.setObjectName("eyebrow")
        layout.addWidget(eye)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        desc = QLabel(subtitle)
        desc.setObjectName("subtitle")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        return host

    def _card(self):
        card = QFrame(objectName="card")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 85))
        card.setGraphicsEffect(shadow)
        return card

    def _table(self, columns):
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def _select_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(self._heading(1, "Bring your data together",
                                       "Scan a complete folder, or select only the files needed for this run."))
        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 26, 26, 26)
        drop = DropZone()
        drop.pathsDropped.connect(self._handle_dropped_paths)
        drop_layout = QVBoxLayout(drop)
        drop_layout.setContentsMargins(24, 28, 24, 28)
        eye = QLabel("DROP FILES OR A FOLDER HERE")
        eye.setObjectName("eyebrow")
        eye.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(eye)
        self.selection_label = QLabel("No folder or files selected")
        self.selection_label.setAlignment(Qt.AlignCenter)
        self.selection_label.setWordWrap(True)
        drop_layout.addWidget(self.selection_label)
        self.source_count = QLabel("XLSX  |  CSV  |  ZIP")
        self.source_count.setObjectName("muted")
        self.source_count.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.source_count)
        helper = QLabel("Drag a folder, drag files, or choose an option below.")
        helper.setObjectName("muted")
        helper.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(helper)
        card_layout.addWidget(drop)
        actions = QHBoxLayout()
        folder = QPushButton("Browse Folder")
        folder.setObjectName("primary")
        folder.clicked.connect(self._browse_folder)
        actions.addWidget(folder)
        files = QPushButton("Select Files")
        files.clicked.connect(self._browse_files)
        actions.addWidget(files)
        card_layout.addLayout(actions)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _sources_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._heading(2, "Review discovered sources",
                                       "Choose which files to process and explicitly mark one included file as the reference."))
        self.sources_metric = QLabel("0 sources")
        self.sources_metric.setObjectName("metric")
        layout.addWidget(self.sources_metric)
        self.reference_metric = QLabel("Reference: none selected")
        self.reference_metric.setObjectName("muted")
        layout.addWidget(self.reference_metric)
        self.sources_empty = QLabel(
            "No sources discovered yet. Return to Select Data and choose files or a folder."
        )
        self.sources_empty.setObjectName("emptyState")
        self.sources_empty.setAlignment(Qt.AlignCenter)
        self.sources_empty.setWordWrap(True)
        layout.addWidget(self.sources_empty)
        self.sources_table = self._table(["Include", "Reference", "Source", "Type", "Location"])
        self.sources_table.itemChanged.connect(self._source_inclusion_changed)
        layout.addWidget(self.sources_table, 1)
        return page

    def _reference_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._heading(3, "Define the reference layout",
                                       "Choose the sheet and optionally correct header or footer rows."))
        columns = QHBoxLayout()
        columns.setSpacing(16)
        card = self._card()
        form = QFormLayout(card)
        form.setContentsMargins(28, 26, 28, 26)
        self.reference_name = QLabel("--")
        form.addRow("Reference source", self.reference_name)
        self.sheet_combo = QComboBox()
        self.sheet_combo.currentTextChanged.connect(self._validation_inputs_changed)
        form.addRow("Reference sheet", self.sheet_combo)
        self.auto_match_sheet = QCheckBox("Different sheet names, same data layout")
        self.auto_match_sheet.setToolTip(
            "Use the selected reference sheet's headers to find the matching worksheet in each Excel file."
        )
        self.auto_match_sheet.toggled.connect(self._validation_inputs_changed)
        form.addRow("", self.auto_match_sheet)
        self.layout_fix = QCheckBox("Header is not on row 1 or footer rows must be ignored")
        self.layout_fix.toggled.connect(self._layout_controls_changed)
        form.addRow("", self.layout_fix)

        self.layout_options = QWidget()
        layout_options_form = QFormLayout(self.layout_options)
        layout_options_form.setContentsMargins(18, 8, 0, 0)
        self.header_row = QSpinBox()
        self.header_row.setRange(1, 10_000)
        self.header_row.setValue(1)
        self.header_row.setEnabled(False)
        self.header_row.valueChanged.connect(self._validation_inputs_changed)
        layout_options_form.addRow("Header row", self.header_row)
        self.footer_rows = QSpinBox()
        self.footer_rows.setRange(0, 10_000)
        self.footer_rows.setEnabled(False)
        self.footer_rows.valueChanged.connect(self._validation_inputs_changed)
        layout_options_form.addRow("Footer rows to ignore", self.footer_rows)
        self.layout_options.hide()
        form.addRow("", self.layout_options)
        columns.addWidget(card, 3)

        summary_card = self._card()
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(24, 22, 24, 22)
        summary_title = QLabel("EFFECTIVE LAYOUT")
        summary_title.setObjectName("eyebrow")
        summary_layout.addWidget(summary_title)
        self.reference_summary_source = QLabel("Source: --")
        self.reference_summary_sheet = QLabel("Sheet: --")
        self.reference_summary_header = QLabel("Header row: 1")
        self.reference_summary_footer = QLabel("Footer rows ignored: 0")
        self.reference_summary_match = QLabel("Sheet matching: exact sheet name")
        self.reference_summary_columns = QLabel(
            "Detected columns become available after validation."
        )
        self.reference_summary_columns.setObjectName("muted")
        self.reference_summary_columns.setWordWrap(True)
        summary_layout.addWidget(self.reference_summary_source)
        summary_layout.addWidget(self.reference_summary_sheet)
        summary_layout.addWidget(self.reference_summary_header)
        summary_layout.addWidget(self.reference_summary_footer)
        summary_layout.addWidget(self.reference_summary_match)
        summary_layout.addSpacing(10)
        summary_layout.addWidget(self.reference_summary_columns)
        summary_layout.addStretch()
        columns.addWidget(summary_card, 2)
        layout.addLayout(columns)
        layout.addStretch()
        return page

    def _validation_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._heading(4, "Validate before combining",
                                       "Required columns, extra columns, duplicates, and read errors are checked first."))
        options = QHBoxLayout()
        self.allow_extra = QCheckBox("Allow extra columns and append them at the end")
        self.allow_extra.setToolTip(
            "Files must still contain every reference column. Extra columns are retained at the end."
        )
        self.allow_extra.toggled.connect(self._validation_inputs_changed)
        options.addWidget(self.allow_extra)
        options.addStretch()
        self.validate_button = QPushButton("Run Validation")
        self.validate_button.setObjectName("primary")
        self.validate_button.setEnabled(False)
        self.validate_button.clicked.connect(self._run_validation)
        options.addWidget(self.validate_button)
        layout.addLayout(options)
        extra_help = QLabel(
            "When enabled, files must still contain every reference column. "
            "Additional columns are retained after the reference columns."
        )
        extra_help.setObjectName("muted")
        extra_help.setWordWrap(True)
        layout.addWidget(extra_help)
        self.validation_progress = QProgressBar()
        self.validation_progress.setRange(0, 100)
        layout.addWidget(self.validation_progress)
        self.validation_summary = QLabel("Validation has not run yet.")
        self.validation_summary.setObjectName("muted")
        layout.addWidget(self.validation_summary)
        chips = QHBoxLayout()
        self.validation_pass_chip = StatusChip("success", "0 PASS")
        self.validation_warn_chip = StatusChip("warning", "0 WARN")
        self.validation_fail_chip = StatusChip("danger", "0 FAIL")
        chips.addWidget(self.validation_pass_chip)
        chips.addWidget(self.validation_warn_chip)
        chips.addWidget(self.validation_fail_chip)
        chips.addStretch()
        layout.addLayout(chips)
        self.validation_empty = QLabel(
            "Run validation to see pass, warning, and failure details for each source."
        )
        self.validation_empty.setObjectName("emptyState")
        self.validation_empty.setAlignment(Qt.AlignCenter)
        self.validation_empty.setWordWrap(True)
        layout.addWidget(self.validation_empty)
        self.validation_table = self._table(["Status", "Source", "Details"])
        self.validation_table.hide()
        layout.addWidget(self.validation_table, 1)
        return page

    def _filters_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._heading(
            5,
            "Combine, filter, and preview",
            "Move through the three focused stages below. Combined data stays loaded for repeat exports.",
        ))

        section_bar = QHBoxLayout()
        section_bar.setSpacing(8)
        self.filter_section_buttons = []
        for index, text in enumerate(("1  Combine", "2  Filters", "3  Preview")):
            button = QPushButton(text)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, section=index: self._show_filter_section(section)
            )
            section_bar.addWidget(button)
            self.filter_section_buttons.append(button)
        section_bar.addStretch()
        layout.addLayout(section_bar)

        self.filter_section_stack = QStackedWidget()
        layout.addWidget(self.filter_section_stack, 1)

        combine_page = QWidget()
        combine_layout = QVBoxLayout(combine_page)
        combine_layout.setContentsMargins(0, 8, 0, 0)
        combine_card = self._card()
        combine_card_layout = QVBoxLayout(combine_card)
        combine_card_layout.setContentsMargins(26, 24, 26, 24)
        combine_title = QLabel("Combine validated sources")
        combine_title.setObjectName("sectionTitle")
        combine_card_layout.addWidget(combine_title)
        combine_help = QLabel(
            "Load the validated files once. You can then change filters and create multiple exports without reloading."
        )
        combine_help.setObjectName("muted")
        combine_help.setWordWrap(True)
        combine_card_layout.addWidget(combine_help)
        options = QHBoxLayout()
        self.fast_combine = QCheckBox("Fast combine mode (uses more memory)")
        self.optimize_memory = QCheckBox("Optimize memory after combine")
        self.optimize_memory.setChecked(True)
        options.addWidget(self.fast_combine)
        options.addWidget(self.optimize_memory)
        options.addStretch()
        self.combine_button = QPushButton("Combine Validated Files")
        self.combine_button.setObjectName("primary")
        self.combine_button.setEnabled(False)
        self.combine_button.clicked.connect(self._run_combine)
        options.addWidget(self.combine_button)
        self.cancel_combine_button = QPushButton("Cancel")
        self.cancel_combine_button.setEnabled(False)
        self.cancel_combine_button.clicked.connect(self._cancel_combine)
        options.addWidget(self.cancel_combine_button)
        combine_card_layout.addLayout(options)
        self.combine_progress = QProgressBar()
        self.combine_progress.setRange(0, 100)
        combine_card_layout.addWidget(self.combine_progress)
        self.combine_summary = QLabel("Waiting to combine.")
        self.combine_summary.setObjectName("muted")
        combine_card_layout.addWidget(self.combine_summary)
        combine_layout.addWidget(combine_card)
        combine_layout.addStretch()
        self.filter_section_stack.addWidget(combine_page)

        filters_page = QWidget()
        filters_layout = QVBoxLayout(filters_page)
        filters_layout.setContentsMargins(0, 8, 0, 0)
        filter_actions = QHBoxLayout()
        self.add_filter_button = QPushButton("Add Filter")
        self.add_filter_button.setObjectName("primary")
        self.add_filter_button.setEnabled(False)
        self.add_filter_button.clicked.connect(self._add_filter)
        filter_actions.addWidget(self.add_filter_button)
        clear = QPushButton("Clear Filters")
        clear.clicked.connect(self._clear_filters)
        filter_actions.addWidget(clear)
        filter_actions.addStretch()
        self.filter_summary_label = QLabel("No filters")
        self.filter_summary_label.setObjectName("muted")
        filter_actions.addWidget(self.filter_summary_label)
        filters_layout.addLayout(filter_actions)

        self.filters_table = self._table(["Applied filter", "Rows remaining", "Edit", "Remove"])
        self.filters_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.filters_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.filters_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.filters_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.filters_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.filters_table.hide()
        filters_layout.addWidget(self.filters_table, 1)
        self.filters_empty = QLabel(
            "No filters applied. All combined rows will be included in the export."
        )
        self.filters_empty.setObjectName("emptyState")
        self.filters_empty.setAlignment(Qt.AlignCenter)
        filters_layout.addWidget(self.filters_empty, 1)
        self.filter_section_stack.addWidget(filters_page)

        preview_page = QWidget()
        preview_layout = QVBoxLayout(preview_page)
        preview_layout.setContentsMargins(0, 8, 0, 0)
        preview_header = QHBoxLayout()
        preview_label = QLabel("FILTERED RESULT")
        preview_label.setObjectName("eyebrow")
        preview_header.addWidget(preview_label)
        preview_header.addStretch()
        self.preview_note = QLabel("Preview becomes available after combine.")
        self.preview_note.setObjectName("muted")
        preview_header.addWidget(self.preview_note)
        preview_layout.addLayout(preview_header)
        self.preview_model = DataFrameModel(parent=self)
        self.preview_table = QTableView()
        self.preview_table.setModel(self.preview_model)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.preview_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.preview_table.setSortingEnabled(False)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        preview_layout.addWidget(self.preview_table, 1)
        self.filter_section_stack.addWidget(preview_page)
        self._show_filter_section(0)
        return page

    def _show_filter_section(self, index):
        if not hasattr(self, "filter_section_stack"):
            return
        if index > 0 and self.final_df is None:
            self._notify("Combine the validated sources before opening filters or preview.", 4)
            index = 0
        self.filter_section_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.filter_section_buttons):
            button.setChecked(button_index == index)
            button.setProperty("active", button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def _update_filter_section_controls(self):
        if not hasattr(self, "filter_section_buttons"):
            return
        for index, button in enumerate(self.filter_section_buttons):
            button.setEnabled(not self.busy and (index == 0 or self.final_df is not None))

    def _export_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._heading(6, "Export with confidence",
                                       "Save the filtered result and a local human-readable audit report."))
        ready_card = QFrame(objectName="readyCard")
        ready_layout = QVBoxLayout(ready_card)
        ready_layout.setContentsMargins(24, 18, 24, 18)
        ready_title = QLabel("READY TO EXPORT")
        ready_title.setObjectName("eyebrow")
        ready_layout.addWidget(ready_title)
        self.export_summary = QLabel("No combined dataset is ready.")
        self.export_summary.setObjectName("metric")
        ready_layout.addWidget(self.export_summary)
        self.export_readiness = QLabel("Choose an output path and format after combining.")
        self.export_readiness.setObjectName("muted")
        self.export_readiness.setWordWrap(True)
        ready_layout.addWidget(self.export_readiness)
        layout.addWidget(ready_card)

        card = self._card()
        form = QFormLayout(card)
        form.setContentsMargins(28, 26, 28, 26)
        path_row = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.textChanged.connect(self._refresh_export_readiness)
        path_row.addWidget(self.output_path, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._choose_output)
        path_row.addWidget(browse)
        form.addRow("Output file", path_row)
        self.export_format = QComboBox()
        self.export_format.addItems(engine.EXPORT_FORMATS.keys())
        self.export_format.currentTextChanged.connect(self._format_changed)
        form.addRow("Format", self.export_format)
        self.unique_column_label = QLabel("CSV text columns")
        self.unique_column = QListWidget()
        self.unique_column.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.unique_column.setMaximumHeight(120)
        self.unique_column.setEnabled(False)
        self.unique_column.setToolTip("Select one or more columns to preserve as text in CSV output.")
        self.unique_column_hint = QLabel("Select one or more columns to preserve as text. Use Ctrl or Shift for multiple.")
        self.unique_column_hint.setObjectName("muted")
        self.unique_column_hint.setWordWrap(True)
        unique_column_box = QWidget()
        unique_column_layout = QVBoxLayout(unique_column_box)
        unique_column_layout.setContentsMargins(0, 0, 0, 0)
        unique_column_layout.setSpacing(6)
        unique_column_layout.addWidget(self.unique_column_hint)
        unique_column_layout.addWidget(self.unique_column)
        self.unique_column_label.hide()
        unique_column_box.hide()
        self.unique_column.hide()
        self.unique_column_box = unique_column_box
        form.addRow(self.unique_column_label, self.unique_column_box)
        self.export_button = QPushButton("Run Export")
        self.export_button.setObjectName("primary")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._run_export)
        form.addRow("", self.export_button)
        self.cancel_export_button = QPushButton("Cancel Export")
        self.cancel_export_button.setEnabled(False)
        self.cancel_export_button.clicked.connect(self._cancel_export)
        form.addRow("", self.cancel_export_button)
        layout.addWidget(card)
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        layout.addWidget(self.export_progress)
        self.export_status = QLabel("Waiting to export.")
        self.export_status.setObjectName("muted")
        layout.addWidget(self.export_status)
        self.export_success = QFrame(objectName="successCard")
        success_layout = QVBoxLayout(self.export_success)
        self.export_success_text = QLabel("")
        self.export_success_text.setWordWrap(True)
        success_layout.addWidget(self.export_success_text)
        success_actions = QHBoxLayout()
        self.open_output_button = QPushButton("Open File")
        self.open_output_button.clicked.connect(
            lambda: self._open_local_path(getattr(self, "last_output_path", ""))
        )
        success_actions.addWidget(self.open_output_button)
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.clicked.connect(
            lambda: self._open_local_path(
                os.path.dirname(getattr(self, "last_output_path", ""))
            )
        )
        success_actions.addWidget(self.open_folder_button)
        self.open_audit_button = QPushButton("Open Audit")
        self.open_audit_button.clicked.connect(
            lambda: self._open_local_path(getattr(self, "last_audit_path", ""))
        )
        success_actions.addWidget(self.open_audit_button)
        success_actions.addStretch()
        success_layout.addLayout(success_actions)
        self.export_success.hide()
        layout.addWidget(self.export_success)
        layout.addStretch()
        return page

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder with data files", self.source_folder
        )
        if folder:
            self.source_folder = folder
            paths = [str(path) for path in Path(folder).iterdir() if path.is_file()]
            self.selection_label.setText(folder)
            self._discover(paths)

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select data files", self.source_folder,
            "Supported files (*.xlsx *.csv *.zip);;All files (*.*)"
        )
        if paths:
            try:
                self.source_folder = os.path.commonpath(
                    [os.path.dirname(path) for path in paths]
                )
            except ValueError:
                self.source_folder = os.path.dirname(paths[0])
            self.selection_label.setText(f"{len(paths)} selected file(s)")
            self._discover(paths)

    def _handle_dropped_paths(self, dropped_paths):
        paths = []
        folders = []
        for raw_path in dropped_paths:
            path = Path(raw_path)
            if path.is_dir():
                folders.append(str(path))
                paths.extend(str(item) for item in path.iterdir() if item.is_file())
            elif path.is_file():
                paths.append(str(path))
        if not paths:
            self._notify("No supported local files were found in the dropped items.")
            return
        if folders:
            self.source_folder = folders[0]
            self.selection_label.setText(f"Dropped folder: {folders[0]}")
        else:
            try:
                self.source_folder = os.path.commonpath(
                    [os.path.dirname(path) for path in paths]
                )
            except ValueError:
                self.source_folder = os.path.dirname(paths[0])
            self.selection_label.setText(f"{len(paths)} dropped file(s)")
        self._discover(paths)

    def _discover(self, paths):
        self.selected_paths = paths
        self.sources, errors = engine.discover_sources(paths)
        self.reference_index = 0
        self.included_source_keys = {
            engine.source_cache_key(source) for source in self.sources
        }
        self._reset_processing_state()
        self.source_count.setText(f"{len(self.sources)} supported source(s) discovered")
        self.status.setText(
            f"{len(self.sources)} source(s) ready"
            + (f"; {len(errors)} archive(s) could not be read" if errors else "")
        )
        self._populate_sources()
        self.max_unlocked_step = 1 if self.sources else 0
        self._update_navigation()

    def _populate_sources(self):
        self.sources_table.blockSignals(True)
        self.sources_table.setRowCount(len(self.sources))
        for row, source in enumerate(self.sources):
            location = source.get("full_path") or source.get("zip_path", "")
            include_item = QTableWidgetItem()
            include_item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
            )
            include_item.setCheckState(
                Qt.Checked
                if engine.source_cache_key(source) in self.included_source_keys
                else Qt.Unchecked
            )
            self.sources_table.setItem(row, 0, include_item)
            reference_button = QToolButton()
            reference_button.setObjectName("referenceChoice")
            reference_button.setCheckable(True)
            reference_button.setChecked(row == self.reference_index)
            reference_button.setText("Selected" if row == self.reference_index else "Use")
            reference_button.setToolTip("Use this included source as the structural reference.")
            reference_button.clicked.connect(
                lambda checked=False, source_row=row: self._set_reference_row(source_row)
            )
            self.sources_table.setCellWidget(row, 1, reference_button)
            values = [source["display_name"], source["type"].upper(), location]
            for column, value in enumerate(values, start=2):
                self.sources_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.sources_table.blockSignals(False)
        self._update_source_metric()
        self.sources_empty.setVisible(not bool(self.sources))
        self.sources_table.setVisible(bool(self.sources))

    def _included_sources(self):
        return [
            source for source in self.sources
            if engine.source_cache_key(source) in self.included_source_keys
        ]

    def _update_source_metric(self):
        included = len(self._included_sources())
        self.sources_metric.setText(
            f"{included} included  /  {len(self.sources)} discovered"
        )
        if self.sources and 0 <= self.reference_index < len(self.sources):
            self.reference_metric.setText(
                f"Reference: {self.sources[self.reference_index]['display_name']}"
            )
        else:
            self.reference_metric.setText("Reference: none selected")

    def _source_inclusion_changed(self, item):
        if item.column() != 0 or item.row() >= len(self.sources):
            return
        source = self.sources[item.row()]
        key = engine.source_cache_key(source)
        if item.checkState() == Qt.Checked:
            self.included_source_keys.add(key)
        else:
            self.included_source_keys.discard(key)
            if item.row() == self.reference_index:
                included_rows = [
                    row for row, candidate in enumerate(self.sources)
                    if engine.source_cache_key(candidate) in self.included_source_keys
                ]
                self.reference_index = included_rows[0] if included_rows else 0
                self._populate_sources()
        self._update_source_metric()
        if self.validation is not None or self.final_df is not None:
            self._invalidate_validation("Source inclusion changed. Run validation again.")
        else:
            self.status.setText("Source inclusion updated.")
            self._update_navigation()

    def _set_reference_row(self, row):
        if row < 0 or row >= len(self.sources):
            return
        source = self.sources[row]
        if engine.source_cache_key(source) not in self.included_source_keys:
            self._notify("Include this source before selecting it as the reference.", 1)
            self._populate_sources()
            return
        if row == self.reference_index:
            self._populate_sources()
            return
        self.reference_index = row
        self.selected_sheet = None
        if self.validation is not None or self.final_df is not None:
            self._invalidate_validation("Reference source changed. Run validation again.")
        else:
            self.status.setText(f"Reference selected: {source['display_name']}")
            self._update_navigation()
        self._populate_sources()

    def _reference_changed(self):
        self._set_reference_row(self.sources_table.currentRow())

    def _prepare_reference_page(self):
        if not self.sources:
            return
        reference = self.sources[self.reference_index]
        self.reference_name.setText(reference["display_name"])
        preferred_sheet = None
        if (
            self.validation_settings
            and self.validation_settings.get("reference_row_index") == self.reference_index
        ):
            preferred_sheet = self.validation_settings.get("selected_sheet")
        elif self.selected_sheet:
            preferred_sheet = self.selected_sheet
        elif self.sheet_combo.currentText():
            preferred_sheet = self.sheet_combo.currentText()
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        try:
            if reference["type"] == "xlsx":
                sheet_names = engine.get_sheet_names(reference)
                self.sheet_combo.addItems(sheet_names)
                if preferred_sheet in sheet_names:
                    self.sheet_combo.setCurrentText(preferred_sheet)
            else:
                self.sheet_combo.addItem("CSV - no worksheet")
        except Exception as exc:
            QMessageBox.critical(self, "Reference error", str(exc))
        finally:
            self.sheet_combo.blockSignals(False)
        is_excel = reference["type"] == "xlsx"
        self.auto_match_sheet.setVisible(is_excel)
        self.auto_match_sheet.setEnabled(is_excel and not self.busy)
        self._refresh_reference_summary()

    def _refresh_reference_summary(self):
        if not hasattr(self, "reference_summary_source"):
            return
        if not self.sources or self.reference_index >= len(self.sources):
            self.reference_summary_source.setText("Source: --")
            self.reference_summary_sheet.setText("Sheet: --")
            return
        reference = self.sources[self.reference_index]
        sheet = (
            self.sheet_combo.currentText()
            if reference["type"] == "xlsx"
            else "CSV - no worksheet"
        )
        self.reference_summary_source.setText(
            f"Source: {reference['display_name']}"
        )
        self.reference_summary_sheet.setText(f"Sheet: {sheet or '--'}")
        self.reference_summary_header.setText(
            f"Header row: {self.header_row.value() if self.layout_fix.isChecked() else 1}"
        )
        self.reference_summary_footer.setText(
            f"Footer rows ignored: {self.footer_rows.value() if self.layout_fix.isChecked() else 0}"
        )
        match_text = (
            "Sheet matching: by header layout"
            if reference["type"] == "xlsx" and self.auto_match_sheet.isChecked()
            else "Sheet matching: exact sheet name"
            if reference["type"] == "xlsx"
            else "Sheet matching: not applicable"
        )
        self.reference_summary_match.setText(match_text)
        columns = self.validation["reference_columns"] if self.validation else []
        if columns:
            preview = ", ".join(str(column) for column in columns[:8])
            suffix = f" and {len(columns) - 8} more" if len(columns) > 8 else ""
            self.reference_summary_columns.setText(
                f"Detected columns ({len(columns)}): {preview}{suffix}"
            )
        else:
            self.reference_summary_columns.setText(
                "Detected columns become available after validation."
            )

    def _layout_controls_changed(self):
        enabled = self.layout_fix.isChecked()
        self.layout_options.setVisible(enabled)
        self.header_row.setEnabled(enabled and not self.busy)
        self.footer_rows.setEnabled(enabled and not self.busy)
        self._refresh_reference_summary()
        self._validation_inputs_changed()

    def _validation_inputs_changed(self, *_):
        self._refresh_reference_summary()
        if self.validation is not None:
            self._invalidate_validation("Reference settings changed. Run validation again.")

    def _current_validation_signature(self):
        included_sources = self._included_sources()
        if not included_sources:
            return None
        reference = self.sources[self.reference_index]
        sheet = self.sheet_combo.currentText() if reference["type"] == "xlsx" else None
        return (
            tuple(engine.source_cache_key(source) for source in included_sources),
            engine.source_cache_key(reference),
            sheet,
            self.auto_match_sheet.isChecked() if reference["type"] == "xlsx" else False,
            self.header_row.value() if self.layout_fix.isChecked() else 1,
            self.footer_rows.value() if self.layout_fix.isChecked() else 0,
            self.allow_extra.isChecked(),
        )

    def _reset_processing_state(self):
        self.selected_sheet = None
        self.validation = None
        self.validation_signature = None
        self.validation_settings = None
        self.extra_columns = []
        self._invalidate_combined()
        if hasattr(self, "validation_table"):
            self.validation_table.setRowCount(0)
            self.validation_table.hide()
            self.validation_empty.show()
            self.validation_progress.setValue(0)
            self.validation_summary.setText("Validation has not run yet.")
            self._update_validation_chips({})

    def _update_validation_chips(self, summary):
        self.validation_pass_chip.setText(f"{summary.get('pass', 0)} PASS")
        self.validation_warn_chip.setText(f"{summary.get('warn', 0)} WARN")
        self.validation_fail_chip.setText(f"{summary.get('fail', 0)} FAIL")

    def _invalidate_validation(self, message):
        self.validation = None
        self.validation_signature = None
        self.validation_settings = None
        self.extra_columns = []
        self._invalidate_combined()
        self.validation_progress.setValue(0)
        self.validation_table.setRowCount(0)
        self.validation_table.hide()
        self.validation_empty.show()
        self.validation_summary.setText(message)
        self._update_validation_chips({})
        self._refresh_reference_summary()
        fallback_step = 3 if self.current_step >= 3 else 2
        self.max_unlocked_step = min(self.max_unlocked_step, fallback_step)
        self._notify(message, attention_step=3)
        if self.current_step > 3:
            self._show_step(3)

    def _invalidate_combined(self):
        self.final_df = None
        self.filtered_df = None
        self.filters = []
        self._filter_undo.clear()
        self._filter_redo.clear()
        if hasattr(self, "combine_progress"):
            self.combine_progress.setValue(0)
            self.combine_summary.setText("Waiting to combine validated files.")
            self.combine_button.setText("Combine Validated Files")
            self.add_filter_button.setEnabled(False)
            self.filters_table.setRowCount(0)
            self.filters_table.hide()
            self.filters_empty.show()
            self.filter_summary_label.setText("No filters")
            self.preview_model.set_dataframe(None)
            self.preview_note.setText("Preview becomes available after combine.")
            self._show_filter_section(0)
            self.export_summary.setText("No combined dataset is ready.")
            self.output_path.clear()
            self._refresh_export_readiness()
            self.unique_column.clear()
            self.unique_column.setEnabled(False)
            self._update_unique_column_visibility()
            self.export_progress.setValue(0)
            self.export_status.setText("Waiting to export.")
            self.export_success.hide()
        self.max_unlocked_step = min(self.max_unlocked_step, 4)
        self._refresh_undo_redo()

    def _run_validation(self):
        if self.busy:
            return
        if not self._reference_ready():
            QMessageBox.warning(
                self,
                "Reference sheet required",
                "Choose a valid worksheet before running validation.",
            )
            return
        self.selected_sheet = (
            self.sheet_combo.currentText()
            if self.sources[self.reference_index]["type"] == "xlsx"
            else None
        )
        pending_signature = self._current_validation_signature()
        included_sources = self._included_sources()
        reference_source = self.sources[self.reference_index]
        reference_key = engine.source_cache_key(reference_source)
        included_reference_index = next(
            index for index, source in enumerate(included_sources)
            if engine.source_cache_key(source) == reference_key
        )
        pending_settings = {
            "reference_index": included_reference_index,
            "reference_row_index": self.reference_index,
            "reference_source": reference_source,
            "included_sources": list(included_sources),
            "selected_sheet": self.selected_sheet,
            "auto_match_sheet": (
                self.auto_match_sheet.isChecked()
                if reference_source["type"] == "xlsx"
                else False
            ),
            "header_row": self.header_row.value() if self.layout_fix.isChecked() else 1,
            "footer_rows": self.footer_rows.value() if self.layout_fix.isChecked() else 0,
            "allow_extra": self.allow_extra.isChecked(),
        }
        self._invalidate_combined()
        self.validation_table.setRowCount(0)
        self.validation_table.hide()
        self.validation_empty.show()
        self.validation_progress.setValue(0)
        self._set_busy(True, "Validating source headers...", operation="validation")
        signals = self._new_signals()
        signals.progress.connect(
            lambda value, message: (
                self.validation_progress.setValue(value),
                self.validation_summary.setText(message),
            )
        )
        signals.done.connect(
            lambda result: self._validation_done(
                result, pending_signature, pending_settings
            )
        )
        signals.failed.connect(lambda message: self._operation_failed("Validation failed", message))

        def work():
            return engine.validate_sources(
                pending_settings["included_sources"],
                pending_settings["reference_index"],
                selected_sheet=pending_settings["selected_sheet"],
                auto_match_sheet=pending_settings["auto_match_sheet"],
                header_row=pending_settings["header_row"],
                footer_rows=pending_settings["footer_rows"],
                allow_extra=pending_settings["allow_extra"],
                progress_callback=lambda done, total: signals.progress.emit(
                    int(done / max(1, total) * 100), f"Validated {done} of {total} sources"
                ),
            )
        self._start_worker(work, signals)

    def _validation_done(self, result, signature, settings):
        if signature != self._current_validation_signature():
            self._set_busy(False, "Settings changed during validation. Run it again.")
            return
        self.validation = result
        self.validation_signature = signature
        self.validation_settings = settings
        self.extra_columns = result["extra_columns"]
        self.validation_table.setRowCount(len(result["results"]))
        self.validation_empty.setVisible(not bool(result["results"]))
        self.validation_table.setVisible(bool(result["results"]))
        colors = {"pass": "#55d6be", "warning": "#e7b75f", "fail": "#f06c75"}
        for row, item in enumerate(result["results"]):
            values = [item["status"].upper(), item["name"], item["detail"]]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setForeground(QColor(colors[item["status"]]))
                self.validation_table.setItem(row, column, cell)
        summary = result["summary"]
        self._update_validation_chips(summary)
        self.validation_summary.setText(
            f"Pass {summary['pass']}  |  Warnings {summary['warn']}  |  "
            f"Failed {summary['fail']}  |  {len(result['passed_sources'])} ready to combine"
        )
        self.validation_progress.setValue(100)
        self._refresh_reference_summary()
        if result["passed_sources"]:
            self.max_unlocked_step = max(self.max_unlocked_step, 4)
        self.attention_step = None
        self.toast.dismiss()
        self._set_busy(False, "Validation complete.")
        self._update_navigation()

    def _run_combine(self):
        if self.busy or not self.validation:
            return
        if self.validation_signature != self._current_validation_signature():
            self._invalidate_validation("Validation is out of date. Run validation again.")
            return
        if self.final_df is not None and self.filters:
            answer = QMessageBox.question(
                self,
                "Recombine data?",
                "Recombining will clear the current filters and preview. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self._invalidate_combined()
        self.cancel_combine = False
        self.combine_progress.setValue(0)
        self.add_filter_button.setEnabled(False)
        self._set_busy(True, "Combining validated sources...", operation="combine")
        signals = self._new_signals()
        signals.progress.connect(
            lambda value, message: (
                self.combine_progress.setValue(value),
                self.combine_summary.setText(message),
            )
        )
        signals.done.connect(self._combine_done)
        signals.failed.connect(lambda message: self._operation_failed("Combine failed", message))
        settings = dict(self.validation_settings)
        reference = settings["reference_source"]
        fast_mode = self.fast_combine.isChecked()
        optimize_memory = self.optimize_memory.isChecked()

        def work():
            return engine.combine_sources(
                self.validation["passed_sources"],
                reference,
                self.validation["reference_columns"],
                selected_sheet=settings["selected_sheet"],
                source_sheet_map=self.validation.get("source_sheet_map"),
                header_row=settings["header_row"],
                footer_rows=settings["footer_rows"],
                allow_extra=settings["allow_extra"],
                extra_columns=self.extra_columns,
                fast_mode=fast_mode,
                optimize_memory=optimize_memory,
                progress_callback=lambda done, total, bytes_done, bytes_total: signals.progress.emit(
                    min(95, int(bytes_done / max(1, bytes_total) * 100)),
                    f"Loaded {done} of {total} sources  |  {bytes_done / 1048576:.1f} MB",
                ),
                cancel_callback=lambda: self.cancel_combine,
            )
        self._start_worker(work, signals)

    def _combine_done(self, result):
        self.final_df, self.extra_columns, memory_stats = result
        self.filtered_df = self.final_df
        self.combine_progress.setValue(100)
        memory_note = ""
        if memory_stats and memory_stats.get("saved_mb") is not None:
            memory_note = f"  |  Saved {memory_stats['saved_mb']:.1f} MB"
        self.combine_summary.setText(
            f"{len(self.final_df):,} rows  |  {len(self.final_df.columns)} columns"
            f"  |  {len(self.validation['passed_sources'])} files{memory_note}"
        )
        self.combine_button.setText("Recombine Files")
        self.add_filter_button.setEnabled(True)
        self.unique_column.clear()
        self.unique_column.addItems([str(col) for col in self.final_df.columns])
        self._refresh_preview()
        self._redraw_filter_list()
        self._set_default_output()
        self._show_filter_section(1)
        self.max_unlocked_step = max(self.max_unlocked_step, 5)
        self._set_busy(False, "Combine complete. Add filters or continue to export.")
        self._update_navigation()

    def _add_filter(self):
        if self.final_df is None:
            return
        active_frame = self.filtered_df if self.filtered_df is not None else self.final_df
        if active_frame.empty:
            QMessageBox.information(
                self, "No rows available",
                "The current filters leave no rows. Remove or edit a filter first."
            )
            return
        dialog = FilterDialog(
            [str(col) for col in self.final_df.columns],
            active_frame,
            parent=self,
        )
        if dialog.exec() and dialog.config:
            self._push_filter_history()
            self.filters.append(dialog.config)
            self._apply_filters()

    def _edit_filter(self, index):
        if self.final_df is None or index < 0 or index >= len(self.filters):
            return
        other_filters = [
            config for filter_index, config in enumerate(self.filters)
            if filter_index != index
        ]
        active_frame = engine.apply_filters(self.final_df, other_filters)
        dialog = FilterDialog(
            [str(col) for col in self.final_df.columns],
            active_frame,
            existing=self.filters[index],
            parent=self,
        )
        if dialog.exec() and dialog.config:
            self._push_filter_history()
            self.filters[index] = dialog.config
            self._apply_filters()

    def _remove_filter(self, index):
        if 0 <= index < len(self.filters):
            self._push_filter_history()
            self.filters.pop(index)
            self._apply_filters()

    def _clear_filters(self):
        if not self.filters:
            return
        self._push_filter_history()
        self.filters = []
        self._apply_filters()

    def _copy_filters(self):
        copied = []
        for config in self.filters:
            item = dict(config)
            if "values" in item:
                item["values"] = list(item["values"])
            copied.append(item)
        return copied

    def _push_filter_history(self):
        self._filter_undo.append(self._copy_filters())
        if len(self._filter_undo) > 50:
            self._filter_undo.pop(0)
        self._filter_redo.clear()
        self._refresh_undo_redo()

    def _undo_filters(self):
        if not self._filter_undo or self.final_df is None:
            return
        self._filter_redo.append(self._copy_filters())
        self.filters = self._filter_undo.pop()
        self._apply_filters()
        self._refresh_undo_redo()
        self._notify("Undid the last filter change.")

    def _redo_filters(self):
        if not self._filter_redo or self.final_df is None:
            return
        self._filter_undo.append(self._copy_filters())
        self.filters = self._filter_redo.pop()
        self._apply_filters()
        self._refresh_undo_redo()
        self._notify("Restored the filter change.")

    def _refresh_undo_redo(self):
        if hasattr(self, "undo_button"):
            self.undo_button.setEnabled(bool(self._filter_undo) and not self.busy)
            self.redo_button.setEnabled(bool(self._filter_redo) and not self.busy)

    def _apply_filters(self):
        try:
            self.filtered_df = engine.apply_filters(self.final_df, self.filters)
            self.filter_summary_label.setText(
                f"{len(self.filters)} filter(s)  |  {len(self.filtered_df):,} rows"
            )
            self._redraw_filter_list()
            self._refresh_preview()
            self._set_default_output()
        except Exception as exc:
            QMessageBox.critical(self, "Filter error", str(exc))

    def _redraw_filter_list(self):
        if not hasattr(self, "filters_table"):
            return
        self.filters_table.setRowCount(len(self.filters))
        self.filters_empty.setVisible(not bool(self.filters))
        self.filters_table.setVisible(bool(self.filters))
        cumulative_mask = pd.Series(True, index=self.final_df.index)
        for row, config in enumerate(self.filters):
            cumulative_mask &= engine.build_filter_mask(self.final_df, config)
            remaining = int(cumulative_mask.sum())
            self.filters_table.setItem(row, 0, QTableWidgetItem(engine.filter_summary(config)))
            self.filters_table.setItem(row, 1, QTableWidgetItem(f"{remaining:,}"))
            edit = QPushButton("Edit")
            edit.clicked.connect(lambda checked=False, i=row: self._edit_filter(i))
            self.filters_table.setCellWidget(row, 2, edit)
            remove = QPushButton("Remove")
            remove.clicked.connect(lambda checked=False, i=row: self._remove_filter(i))
            self.filters_table.setCellWidget(row, 3, remove)
        if not self.filters:
            self.filter_summary_label.setText(
                f"No filters  |  {len(self.final_df):,} rows"
                if self.final_df is not None else "No filters"
            )

    def _refresh_preview(self):
        frame = self.filtered_df if self.filtered_df is not None else self.final_df
        if frame is None:
            return
        self.preview_model.set_dataframe(frame)
        self.preview_note.setText(
            f"{len(frame):,} rows  |  {len(frame.columns)} columns  |  lazy table rendering"
        )

    def _set_default_output(self):
        if self.filtered_df is None:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = self.source_folder or os.getcwd()
        extension = engine.EXPORT_FORMATS[self.export_format.currentText()]["extension"]
        self.output_path.setText(os.path.join(folder, f"MergeGuru_{stamp}{extension}"))
        self.export_summary.setText(
            f"{len(self.filtered_df):,} rows  |  {len(self.filtered_df.columns)} columns  |  "
            f"{len(self.filters)} filter(s)"
        )
        self._refresh_export_readiness()

    def _refresh_export_readiness(self, *_):
        if not hasattr(self, "export_readiness"):
            return
        if self.filtered_df is None:
            self.export_readiness.setText(
                "Choose an output path and format after combining."
            )
            return
        path = self.output_path.text().strip() or "Not selected"
        self.export_readiness.setText(
            f"Format: {self.export_format.currentText()}  |  Output: {path}"
        )

    def _choose_output(self):
        export_format = self.export_format.currentText()
        extension = engine.EXPORT_FORMATS[export_format]["extension"]
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save output",
            self.output_path.text() or self.last_export_folder,
            f"{export_format} (*{extension});;All files (*.*)"
        )
        if path:
            self.last_export_folder = os.path.dirname(path)
            self.output_path.setText(engine.ensure_export_extension(path, export_format))

    def _format_changed(self):
        if self.output_path.text():
            self.output_path.setText(
                engine.ensure_export_extension(
                    self.output_path.text(), self.export_format.currentText()
                )
            )
        self._update_unique_column_visibility()
        self._refresh_export_readiness()

    def _update_unique_column_visibility(self):
        if not hasattr(self, "unique_column"):
            return
        visible = self.export_format.currentText() == "CSV-Unique text"
        self.unique_column_box.setVisible(visible)
        self.unique_column.setVisible(visible)
        self.unique_column.setEnabled(visible and self.filtered_df is not None)
        if hasattr(self, "unique_column_label"):
            self.unique_column_label.setVisible(visible)

    def _selected_unique_columns(self):
        if not hasattr(self, "unique_column"):
            return []
        return [item.text() for item in self.unique_column.selectedItems()]

    def _run_export(self):
        if self.busy or self.filtered_df is None:
            return
        try:
            self.filtered_df = engine.apply_filters(self.final_df, self.filters)
        except Exception as exc:
            QMessageBox.critical(self, "Filter error", f"Export stopped. Correct or remove the invalid filter.\n\n{exc}")
            return
        raw_path = self.output_path.text().strip()
        if not raw_path:
            QMessageBox.warning(self, "No output path", "Choose an output file path.")
            return
        export_format = self.export_format.currentText()
        if export_format == "CSV-Unique text" and not self._selected_unique_columns():
            QMessageBox.warning(self, "No protected columns", "Select at least one text column to protect.")
            return
        path = engine.ensure_export_extension(raw_path, export_format)
        if os.path.exists(path):
            overwrite = QMessageBox.question(
                self,
                "Replace existing file?",
                f"This file already exists:\n{path}\n\nReplace it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if overwrite != QMessageBox.Yes:
                return
        self.output_path.setText(path)
        self.cancel_export = False
        self.export_progress.setValue(0)
        self.export_success.hide()
        self._set_busy(True, "Exporting filtered result...", operation="export")
        signals = self._new_signals()
        signals.progress.connect(
            lambda value, message: (
                self.export_progress.setValue(value),
                self.export_status.setText(message),
            )
        )
        signals.done.connect(lambda result: self._export_done(result))
        signals.failed.connect(lambda message: self._operation_failed("Export failed", message))
        frame = self.filtered_df
        unique_columns = self._selected_unique_columns()

        def work():
            started = time.time()
            engine.save_dataframe(
                frame,
                path,
                export_format,
                unique_columns=unique_columns,
                progress_callback=lambda value, message: signals.progress.emit(value, message),
                cancel_callback=lambda: self.cancel_export,
            )
            audit_path = self._write_audit(path, export_format, len(frame))
            return path, audit_path, time.time() - started
        self._start_worker(work, signals)

    def _write_audit(self, output_path, export_format, row_count):
        base, _ = os.path.splitext(output_path)
        audit_path = base + ".audit.txt"
        with open(audit_path, "w", encoding="utf-8") as stream:
            stream.write(f"MergeGuru Pro Audit Report ({APP_VERSION})\n")
            stream.write("=" * 60 + "\n")
            stream.write(f"Created: {datetime.now().isoformat(timespec='seconds')}\n")
            stream.write(f"Source location: {self.source_folder}\n")
            settings = self.validation_settings or {}
            reference = settings.get("reference_source") or self.sources[self.reference_index]
            stream.write(f"Reference: {reference['display_name']}\n")
            stream.write(f"Sheet: {settings.get('selected_sheet') or 'CSV'}\n")
            stream.write(f"Validated sources included: {len(self.validation['passed_sources'])}\n")
            stream.write(f"Output: {output_path}\n")
            stream.write(f"Format: {export_format}\n")
            stream.write(f"Rows: {row_count:,}\n")
            stream.write(f"Columns: {len(self.filtered_df.columns)}\n")
            stream.write("\nFilters\n")
            if self.filters:
                for config in self.filters:
                    stream.write(f"- {engine.filter_summary(config)}\n")
            else:
                stream.write("- None\n")
        return audit_path

    def _export_done(self, result):
        path, audit_path, elapsed = result
        self.last_output_path = path
        self.last_audit_path = audit_path
        self.last_export_folder = os.path.dirname(path)
        self.export_progress.setValue(100)
        self.export_status.setText(
            f"Export complete in {elapsed:.1f}s  |  Audit: {os.path.basename(audit_path)}"
        )
        self._set_busy(False, "Export completed successfully.")
        self.export_success_text.setText(
            f"Export created successfully.\n{path}\nAudit: {audit_path}"
        )
        self.export_success.show()
        self._notify("Export complete. Use the quick actions below to open the result.")

    def _open_local_path(self, path):
        if not path or not os.path.exists(path):
            self._notify("The selected file or folder is no longer available.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))

    def _cancel_combine(self):
        self.cancel_combine = True
        self.cancel_combine_button.setEnabled(False)
        self.status.setText("Cancel requested. Active file reads will finish safely.")

    def _cancel_export(self):
        self.cancel_export = True
        self.cancel_export_button.setEnabled(False)
        self.status.setText("Cancel requested. Export will stop at the next safe point.")

    def _new_signals(self):
        signals = WorkerSignals()
        self._signals.append(signals)
        return signals

    def _start_worker(self, function, signals):
        def run():
            try:
                signals.done.emit(function())
            except Exception as exc:
                signals.failed.emit(str(exc))
        threading.Thread(target=run, daemon=True).start()

    def _operation_failed(self, title, message):
        self._set_busy(False, message)
        if "cancel" in message.lower():
            self._notify(message)
        else:
            QMessageBox.critical(self, title, message)

    def _set_busy(self, busy, message, operation=None):
        self.busy = busy
        self.active_operation = operation if busy else None
        self.status.setText(message)
        self.sources_table.setEnabled(not busy)
        self.sheet_combo.setEnabled(not busy)
        self.auto_match_sheet.setEnabled(
            not busy
            and bool(self.sources)
            and self.sources[self.reference_index]["type"] == "xlsx"
        )
        self.layout_fix.setEnabled(not busy)
        self.header_row.setEnabled(not busy and self.layout_fix.isChecked())
        self.footer_rows.setEnabled(not busy and self.layout_fix.isChecked())
        self.allow_extra.setEnabled(not busy)
        self.validate_button.setEnabled(not busy and self._reference_ready())
        self.fast_combine.setEnabled(not busy)
        self.optimize_memory.setEnabled(not busy)
        self.combine_button.setEnabled(
            not busy and bool(self.validation and self.validation["passed_sources"])
        )
        self.export_button.setEnabled(not busy and self.filtered_df is not None)
        self.cancel_combine_button.setEnabled(busy and operation == "combine")
        self.cancel_export_button.setEnabled(busy and operation == "export")
        self.add_filter_button.setEnabled(not busy and self.final_df is not None)
        self._update_filter_section_controls()
        self._update_navigation()

    def _can_enter(self, step):
        if step > self.max_unlocked_step:
            return False
        if step == 0:
            return True
        if step == 1:
            return bool(self.sources)
        if step == 2:
            return self._has_included_reference()
        if step == 3:
            return self._reference_ready()
        if step == 4:
            return bool(self.validation and self.validation["passed_sources"])
        return self.final_df is not None

    def _has_included_reference(self):
        if not self.sources or not self._included_sources():
            return False
        reference = self.sources[self.reference_index]
        return engine.source_cache_key(reference) in self.included_source_keys

    def _reference_ready(self):
        if not self._has_included_reference():
            return False
        reference = self.sources[self.reference_index]
        if engine.source_cache_key(reference) not in self.included_source_keys:
            return False
        return reference["type"] == "csv" or bool(self.sheet_combo.currentText())

    def _request_step(self, step):
        if self.busy:
            return
        if self._can_enter(step):
            self._show_step(step)

    def _show_step(self, step):
        self.current_step = max(0, min(step, len(STEPS) - 1))
        if self.current_step == 2:
            self._prepare_reference_page()
        elif self.current_step == 4:
            self._show_filter_section(1 if self.final_df is not None else 0)
        self.stack.setCurrentIndex(self.current_step)
        page = self.stack.currentWidget()
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        self._page_animation = QPropertyAnimation(effect, b"opacity", self)
        self._page_animation.setDuration(140)
        self._page_animation.setStartValue(0.25)
        self._page_animation.setEndValue(1.0)
        self._page_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._page_animation.finished.connect(lambda: page.setGraphicsEffect(None))
        self._page_animation.start()
        next_labels = {
            0: "Review Sources",
            1: "Set Reference",
            2: "Continue to Validation",
            3: "Combine & Filter",
            4: "Continue to Export",
            5: "Done",
        }
        self.next_button.setText(next_labels[self.current_step])
        page_guidance = {
            0: "Choose a folder or select specific files.",
            1: "Select one source row as the reference structure.",
            2: "Confirm the worksheet and optional header/footer settings.",
            3: "Run validation before continuing.",
            4: "Combine once, then add, edit, or remove filters.",
            5: "Choose the output format and run export.",
        }
        if not self.busy:
            self.status.setText(page_guidance[self.current_step])
        self._update_navigation()

    def _update_navigation(self):
        if not hasattr(self, "next_button"):
            return
        self.back_button.setEnabled(not self.busy and self.current_step > 0)
        self.validate_button.setEnabled(not self.busy and self._reference_ready())
        self.combine_button.setEnabled(
            not self.busy and bool(self.validation and self.validation["passed_sources"])
        )
        self.add_filter_button.setEnabled(not self.busy and self.final_df is not None)
        self.export_button.setEnabled(not self.busy and self.filtered_df is not None)
        self.fast_combine.setEnabled(not self.busy)
        self.optimize_memory.setEnabled(not self.busy)
        self.cancel_combine_button.setEnabled(
            self.busy and self.active_operation == "combine"
        )
        self.cancel_export_button.setEnabled(
            self.busy and self.active_operation == "export"
        )
        for index, button in enumerate(self.step_buttons):
            available = self._can_enter(index)
            button.setEnabled(not self.busy and available)
            if index == self.attention_step:
                state = "attention"
            elif index < self.current_step and available:
                state = "completed"
            elif not available:
                state = "locked"
            else:
                state = "ready"
            button.set_visual_state(index == self.current_step, state)
            button.setToolTip(
                "" if available else "Complete the earlier steps to unlock this section."
            )
        can_next = {
            0: bool(self.sources),
            1: self._has_included_reference(),
            2: self._reference_ready(),
            3: bool(self.validation and self.validation["passed_sources"]),
            4: self.final_df is not None,
            5: True,
        }[self.current_step]
        self.next_button.setEnabled(not self.busy and can_next)
        missing_hint = {
            0: "Select or drop at least one supported source.",
            1: "Include at least one source and choose the reference row.",
            2: "Choose a valid reference worksheet.",
            3: "Run validation and resolve failures before continuing.",
            4: "Combine the validated sources before exporting.",
        }
        self.next_button.setToolTip(
            "" if can_next else missing_hint.get(self.current_step, "")
        )
        self.validate_button.setToolTip(
            "" if self.validate_button.isEnabled()
            else "Choose included sources, a reference source, and a valid worksheet first."
        )
        self.combine_button.setToolTip(
            "" if self.combine_button.isEnabled()
            else "Complete validation with at least one passing source first."
        )
        self.export_button.setToolTip(
            "" if self.export_button.isEnabled()
            else "Combine the validated data before exporting."
        )
        self._update_filter_section_controls()
        self._refresh_undo_redo()

    def _next(self):
        if self.current_step < len(STEPS) - 1:
            self.max_unlocked_step = max(
                self.max_unlocked_step, self.current_step + 1
            )
            self._show_step(self.current_step + 1)
        else:
            self.close()

    def _back(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MergeGuru Pro")
    window = MergeGuruPro()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
