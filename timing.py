"""Shared assertions and CSV readers for Saleae data and digital transitions."""

import csv
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    start: float
    end: float
    kind: str
    data: str


def read_frames(path):
    """Read one Logic 2 analyzer data-table CSV (start_time/end_time/type/data)."""
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        required = {"start_time", "end_time", "type", "data"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Expected Logic 2 data-table columns: {sorted(required)}")
        return [Frame(float(row["start_time"]), float(row["end_time"]),
                      row["type"].strip().lower(), row["data"].strip())
                for row in reader]


def read_edges(path, channel):
    """Read timestamp/level pairs from a raw digital CSV; retain only transitions."""
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or channel not in reader.fieldnames:
            raise ValueError(f"Missing digital channel column: {channel}")
        time_column = next((name for name in reader.fieldnames
                            if name.lower().startswith("time")), None)
        if time_column is None:
            raise ValueError("Missing time column")
        edges = []
        for row in reader:
            level = int(row[channel])
            time = float(row[time_column])
            if level not in (0, 1) or (edges and time <= edges[-1][0]):
                raise ValueError("Digital levels must be 0/1 with increasing timestamps")
            if not edges or level != edges[-1][1]:
                edges.append((time, level))
        return edges


def assert_range(value, minimum, maximum, name):
    if minimum > maximum or not minimum <= value <= maximum:
        raise AssertionError(f"{name}: {value:g}s outside [{minimum:g}, {maximum:g}]s")


def assert_sequence(actual, expected, name="data"):
    actual, expected = list(actual), list(expected)
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")


def level_at(edges, time):
    """Return sampled level after the latest transition at or before time."""
    if not edges or time < edges[0][0]:
        raise ValueError("No sampled level at requested time")
    level = edges[0][1]
    for timestamp, state in edges[1:]:
        if timestamp > time:
            break
        level = state
    return level


def assert_pulse_widths(edges, level, minimum, maximum):
    widths = [end - start for (start, state), (end, _) in zip(edges, edges[1:])
              if state == level]
    if not widths:
        raise AssertionError(f"No complete level-{level} pulses")
    for width in widths:
        assert_range(width, minimum, maximum, f"level-{level} pulse width")


def assert_setup_hold(data_edges, clock_edges, sample_level, setup, hold):
    """Require data to stay stable around each sampling clock edge."""
    samples = [time for time, level in clock_edges[1:] if level == sample_level]
    if not samples:
        raise AssertionError("No sampling edges")
    for sample in samples:
        if any(sample - setup < time < sample + hold for time, _ in data_edges[1:]):
            raise AssertionError(f"Data changed within setup/hold window at {sample:g}s")
