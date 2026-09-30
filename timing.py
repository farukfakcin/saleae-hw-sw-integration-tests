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
    """Normalize one Logic 2 analyzer data-table CSV into protocol frames."""
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        required = {"start_time", "type"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Expected Logic 2 data-table columns: {sorted(required)}")
        if "duration" not in reader.fieldnames and "end_time" not in reader.fieldnames:
            raise ValueError("Expected duration or end_time column")
        if "data" not in reader.fieldnames and "mosi" not in reader.fieldnames:
            raise ValueError("Expected data or SPI mosi/miso columns")
        frames = []
        for row in reader:
            start = float(row["start_time"])
            end = (start + float(row["duration"]) if "duration" in row
                   else float(row["end_time"]))
            kind = row["type"].strip().lower()
            if "mosi" in row:
                if kind == "result":
                    for channel in ("mosi", "miso"):
                        if row.get(channel):
                            frames.append(Frame(start, end, channel, row[channel].strip()))
                else:
                    frames.append(Frame(start, end, kind, ""))
            else:
                frames.append(Frame(start, end, kind, (row.get("data") or "").strip()))
        return frames


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


def read_samples(path, channel):
    """Read (time, voltage) samples from a raw analog CSV."""
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or channel not in reader.fieldnames:
            raise ValueError(f"Missing analog channel column: {channel}")
        time_column = next((name for name in reader.fieldnames
                            if name.lower().startswith("time")), None)
        if time_column is None:
            raise ValueError("Missing time column")
        return [(float(row[time_column]), float(row[channel])) for row in reader]


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


def assert_rise_fall(samples, low, high, max_rise, max_fall):
    """Measure 10–90% rise and 90–10% fall on analog (time, voltage) samples."""
    if low >= high or max_rise <= 0 or max_fall <= 0:
        raise ValueError("Invalid voltage or transition limits")
    bottom = low + .1 * (high - low)
    top = low + .9 * (high - low)
    rising = falling = None
    rises = falls = 0
    for (before_time, before), (time, voltage) in zip(samples, samples[1:]):
        if time <= before_time:
            raise ValueError("Analog sample times must increase")
        if before <= bottom < voltage:
            rising = time
        if rising is not None and before < top <= voltage:
            assert_range(time - rising, 0, max_rise, "rise time")
            rises += 1
            rising = None
        if before >= top > voltage:
            falling = time
        if falling is not None and before > bottom >= voltage:
            assert_range(time - falling, 0, max_fall, "fall time")
            falls += 1
            falling = None
    if not rises or not falls:
        raise AssertionError("Missing complete rise/fall transitions")


def assert_setup_hold(data_edges, clock_edges, sample_level, setup, hold):
    """Require data to stay stable around each sampling clock edge."""
    samples = [time for time, level in clock_edges[1:] if level == sample_level]
    if not samples:
        raise AssertionError("No sampling edges")
    for sample in samples:
        if any(sample - setup < time < sample + hold for time, _ in data_edges[1:]):
            raise AssertionError(f"Data changed within setup/hold window at {sample:g}s")
