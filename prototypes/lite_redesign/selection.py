"""Search affects visibility, never the persistent category selection."""


class ValueSelection:
    def __init__(self, values, selected=()):
        self.values = tuple(sorted(set(values), key=lambda value: (value.casefold(), value)))
        self.normalized = tuple(value.casefold() for value in self.values)
        self.selected = set(selected).intersection(self.values)

    def matches(self, query="", mode="Starts with"):
        query = query.strip().casefold()
        if not query:
            return self.values
        if mode == "Contains":
            return tuple(value for value, normalized in zip(self.values, self.normalized) if query in normalized)
        return tuple(value for value, normalized in zip(self.values, self.normalized) if normalized.startswith(query))

    def select(self, visible):
        self.selected.update(visible)

    def clear(self, visible):
        self.selected.difference_update(visible)

    def invert(self, visible):
        self.selected.symmetric_difference_update(visible)

    def toggle(self, value):
        self.selected.symmetric_difference_update((value,))

    def result(self):
        return tuple(value for value in self.values if value in self.selected)
