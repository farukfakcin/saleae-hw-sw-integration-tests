"""SPI byte/frame and CPOL/CPHA timing assertions."""

from timing import assert_range, assert_sequence, assert_setup_hold, level_at


class SPIValidator:
    def __init__(self, frames):
        self.frames = list(frames)

    def validate(self, expected_mosi, expected_miso=None):
        """Compare decoded MOSI/MISO bytes, rejecting missing or extra bytes."""
        if not self.frames:
            raise AssertionError("No SPI frames captured")
        mosi = []
        miso = []
        selected = False
        has_cs = any(frame.kind in ("enable", "disable") for frame in self.frames)
        for frame in self.frames:
            if frame.kind == "enable":
                if selected:
                    raise AssertionError("Repeated SPI chip-select assertion")
                selected = True
            elif frame.kind == "disable":
                if not selected:
                    raise AssertionError("SPI chip-select deasserted without assertion")
                selected = False
            elif frame.kind == "mosi":
                if has_cs and not selected:
                    raise AssertionError("MOSI byte outside chip-select window")
                mosi.append(int(frame.data, 0))
            elif frame.kind == "miso":
                if has_cs and not selected:
                    raise AssertionError("MISO byte outside chip-select window")
                miso.append(int(frame.data, 0))
            else:
                raise AssertionError(f"Unexpected SPI frame type: {frame.kind}")
        if selected:
            raise AssertionError("SPI chip select never deasserted")
        assert_sequence(mosi, expected_mosi, "MOSI")
        if expected_miso is not None:
            assert_sequence(miso, expected_miso, "MISO")
        if expected_miso is not None and len(mosi) != len(miso):
            raise AssertionError("MOSI/MISO transfer counts differ")
        if expected_miso is not None:
            mosi_frames = [frame for frame in self.frames if frame.kind == "mosi"]
            miso_frames = [frame for frame in self.frames if frame.kind == "miso"]
            if any(tx.start != rx.start for tx, rx in zip(mosi_frames, miso_frames)):
                raise AssertionError("MOSI/MISO bytes are not synchronized")
        for previous, current in zip(self.frames, self.frames[1:]):
            if previous.start > current.start:
                raise AssertionError("SPI frames are not chronological")

    @staticmethod
    def validate_signals(clock, cs, mosi, miso, *, mode, min_half_period,
                         max_half_period, setup=0, hold=0):
        """Assert active-low CS window, clock idle polarity and sampled-data stability."""
        if mode not in range(4):
            raise ValueError("SPI mode must be 0, 1, 2 or 3")
        cpol, cpha = divmod(mode, 2)
        if not clock or clock[0][1] != cpol:
            raise AssertionError("SPI clock idle polarity does not match mode")
        windows = [(start, end) for (start, level), (end, _) in zip(cs, cs[1:])
                   if level == 0]
        if not windows:
            raise AssertionError("No complete active-low chip-select window")
        for start, end in windows:
            if level_at(clock, start) != cpol or level_at(clock, end) != cpol:
                raise AssertionError("Clock must be idle at CS boundaries")
            active_clock = [(time, level) for time, level in clock if start < time < end]
            if not active_clock:
                raise AssertionError("No clock transitions while CS asserted")
            for (first, _), (second, _) in zip(active_clock, active_clock[1:]):
                assert_range(second - first, min_half_period, max_half_period,
                             "SPI half-period")
            sample_level = cpol ^ (1 - cpha)
            sample_edges = [(time, level) for time, level in active_clock
                            if level == sample_level]
            if not sample_edges:
                raise AssertionError("No clock sampling edges")
            for data_edges in (mosi, miso):
                if data_edges is not None:
                    assert_setup_hold(data_edges, [clock[0], *sample_edges],
                                      sample_level, setup, hold)
