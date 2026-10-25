"""Small deterministic sample model, deliberately separate from the real engine."""

from dataclasses import dataclass, field


SAMPLE_FILES = ("North_Jan.xlsx", "South_Jan.xlsx", "West_Jan.xlsx")
FORMATS = ("Excel", "CSV", "CSV-Unique text", "Parquet")
EXTENSIONS = {"Excel": ".xlsx", "CSV": ".csv", "CSV-Unique text": ".csv", "Parquet": ".parquet"}


@dataclass
class Filter:
    column: str
    operator: str
    values: tuple

    def matches(self, row):
        value = str(row.get(self.column, ""))
        if self.operator == "contains":
            return self.values[0].casefold() in value.casefold()
        if self.operator == "is not one of":
            return value not in self.values
        return value in self.values

    def description(self):
        joined = ", ".join(value or "(Blank)" for value in self.values[:3])[:90]
        extra = f" + {len(self.values) - 3} more" if len(self.values) > 3 else ""
        action = {"is one of": "Include", "is not one of": "Exclude", "contains": "Contains"}[self.operator]
        return f"{self.column} | {action}: {joined}{extra}"


@dataclass
class DemoState:
    sources: list = field(default_factory=lambda: list(SAMPLE_FILES))
    template: str = SAMPLE_FILES[0]
    allow_extra: bool = True
    different_sheets: bool = True
    fix_layout: bool = False
    header_row: int = 1
    footer_rows: int = 0
    optimize_memory: bool = True
    parallel: bool = False
    quality_checks: bool = False
    prepared: bool = False
    filters: list = field(default_factory=list)
    output_format: str = "Excel"
    protected: set = field(default_factory=lambda: {"Customer ID"})
    filename: str = "Merged_January_01.xlsx"
    history: list = field(default_factory=list)
    saved_signature: object = None

    def invalidate(self):
        self.prepared = False
        self.saved_signature = None

    def select_sources(self, sources):
        self.sources = list(sources)
        if self.template not in self.sources:
            self.template = self.sources[0] if self.sources else ""
        self.invalidate()

    def rows(self):
        rows = []
        for source in self.sources:
            region = source.split("_", 1)[0]
            for index in range(6):
                row = {"Customer ID": f"00{SAMPLE_FILES.index(source) + 1}{index + 1:03d}",
                       "Region": region, "Status": "Active" if index % 3 else "Pending",
                       "Branch": ("Waltham", "Walnut Creek", "Watford", "Waverley", "West End", "North Central")[index],
                       "Amount": (index + 1) * 125, "Source file": source}
                if self.allow_extra:
                    row["Team"] = "Retail" if region == "West" else ""
                rows.append(row)
        return rows

    def filtered_rows(self):
        if self.filter_problem():
            return []
        return [row for row in self.rows() if all(item.matches(row) for item in self.filters)]

    def filter_problem(self):
        columns = self.columns()
        for item in self.filters:
            if item.column not in columns:
                return f"Column '{item.column}' is unavailable. Edit or remove its filter."
        return ""

    def columns(self):
        return list(self.rows()[0]) if self.sources else []

    def signature(self):
        return (tuple(self.sources), self.template, self.allow_extra, self.different_sheets,
                self.fix_layout, self.header_row, self.footer_rows,
                tuple((item.column, item.operator, item.values) for item in self.filters),
                self.output_format, tuple(sorted(self.protected)), self.filename)

    def choose_format(self, value):
        self.output_format = value
        stem = self.filename.rsplit(".", 1)[0] or "Merged_January_01"
        self.filename = stem + EXTENSIONS[value]

    def validate_export(self):
        if self.filter_problem():
            raise ValueError(self.filter_problem())
        name = self.filename.strip()
        if not name or name in {".", ".."} or any(char in name for char in '<>:"/\\|?*'):
            raise ValueError("Enter a file name without folder separators or special characters.")
        if name != self.filename or name.endswith("."):
            raise ValueError("Remove spaces or dots at the beginning/end of the file name.")
        if not name.lower().endswith(EXTENSIONS[self.output_format]):
            raise ValueError(f"This format needs a {EXTENSIONS[self.output_format]} file name.")
        if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise ValueError("Choose another name; this name is reserved by Windows.")
        if not self.prepared:
            raise ValueError("Check & Prepare must finish before exporting.")
        if self.output_format == "CSV-Unique text" and not self.protected.intersection(self.columns()):
            raise ValueError("Choose at least one text column to preserve.")
        if not self.filtered_rows():
            raise ValueError("No sample rows match. Adjust your filters before exporting.")

    def mark_exported(self):
        self.validate_export()
        name = self.filename
        self.history.insert(0, {"name": name, "format": self.output_format,
                                "rows": len(self.filtered_rows())})
        self.saved_signature = self.signature()

    def next_filename(self):
        extension = EXTENSIONS[self.output_format]
        stem = self.filename.rsplit(".", 1)[0]
        base, _, suffix = stem.rpartition("_")
        self.filename = f"{base}_{int(suffix) + 1:02d}{extension}" if suffix.isdigit() else f"{stem}_02{extension}"

    @property
    def saved(self):
        return self.saved_signature == self.signature()
