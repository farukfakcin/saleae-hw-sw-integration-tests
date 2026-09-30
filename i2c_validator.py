"""I2C decoded-frame and bus timing assertions."""

from timing import assert_pulse_widths, assert_sequence, assert_setup_hold, level_at


def _byte(text):
    return int(text.strip().split()[0], 0)


class I2CValidator:
    def __init__(self, frames):
        self.frames = list(frames)

    def validate(self, address, expected_data, *, allow_nack=False):
        """Check a complete START/address/ACK/data/ACK/STOP transaction."""
        kinds = [frame.kind for frame in self.frames]
        if not kinds or kinds[0] != "start" or kinds[-1] != "stop":
            raise AssertionError("I2C transaction must begin with START and end with STOP")
        if kinds.count("start") != 1 or kinds.count("stop") != 1:
            raise AssertionError("Unexpected repeated START/STOP; validate each transaction separately")
        if len(self.frames) < 4 or self.frames[1].kind != "address":
            raise AssertionError("Missing address after START")
        if _byte(self.frames[1].data) != address:
            raise AssertionError(f"I2C address mismatch: {self.frames[1].data}")
        actual = []
        index = 2
        while index < len(self.frames) - 1:
            ack = self.frames[index]
            if ack.kind not in ("ack", "nack") or (ack.kind == "nack" and not allow_nack):
                raise AssertionError(f"Expected ACK at frame {index}")
            index += 1
            if index == len(self.frames) - 1:
                break
            data = self.frames[index]
            if data.kind != "data":
                raise AssertionError(f"Expected data byte at frame {index}")
            actual.append(_byte(data.data))
            index += 1
        assert_sequence(actual, expected_data, "I2C bytes")
        for previous, current in zip(self.frames, self.frames[1:]):
            if previous.start > previous.end or previous.end > current.start:
                raise AssertionError("Overlapping or reversed I2C frames")

    @staticmethod
    def validate_signals(scl, sda, *, min_high, max_high, min_low, max_low,
                         setup=0, hold=0):
        """Check clock widths, data setup/hold, and START/STOP transitions on SDA."""
        assert_pulse_widths(scl, 1, min_high, max_high)
        assert_pulse_widths(scl, 0, min_low, max_low)
        starts = stops = 0
        for (time, before), (next_time, after) in zip(sda, sda[1:]):
            if level_at(scl, next_time) == 1:
                if before == 1 and after == 0:
                    starts += 1
                elif before == 0 and after == 1:
                    stops += 1
        if not starts or not stops:
            raise AssertionError("Missing I2C START or STOP transition while SCL high")
        samples = [(time, level) for time, level in scl[1:] if level == 1]
        if samples:
            assert_setup_hold(sda, [scl[0], *samples], 1, setup, hold)
