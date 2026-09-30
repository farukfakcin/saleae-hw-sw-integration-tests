"""UART decoded-frame and sampled waveform assertions."""

from timing import assert_sequence, level_at


class UARTValidator:
    def __init__(self, frames):
        self.frames = list(frames)

    def validate(self, expected, *, baud_rate, data_bits=8, parity="none",
                 stop_bits=1, tolerance=0.05):
        if parity not in ("none", "even", "odd") or data_bits not in range(5, 10):
            raise ValueError("Unsupported UART format")
        if baud_rate <= 0 or stop_bits not in (1, 2) or not 0 <= tolerance < 1:
            raise ValueError("Invalid UART timing parameters")
        values = []
        for frame in self.frames:
            if frame.kind not in ("data", "error", "parity_error", "framing_error"):
                raise AssertionError(f"Unexpected UART frame: {frame.kind}")
            if frame.kind != "data":
                raise AssertionError(f"UART {frame.kind}: {frame.data}")
            values.append(int(frame.data, 0))
            if values[-1] >= 1 << data_bits or values[-1] < 0:
                raise AssertionError("UART value does not fit configured data bits")
        assert_sequence(values, expected, "UART bytes")

    @staticmethod
    def validate_signals(edges, expected, *, baud_rate, data_bits=8,
                         parity="none", stop_bits=1, tolerance=0.05):
        """Sample each bit center; check start, optional parity and all stop bits."""
        if baud_rate <= 0 or parity not in ("none", "even", "odd") or not 0 <= tolerance < 1:
            raise ValueError("Invalid UART configuration")
        if data_bits not in range(5, 10) or stop_bits not in (1, 2):
            raise ValueError("Invalid UART frame format")
        if not edges or edges[0][1] != 1:
            raise AssertionError("UART line must initially be idle high")
        bit_time = 1 / baud_rate
        starts = [time for (_, before), (time, after) in zip(edges, edges[1:])
                  if before == 1 and after == 0]
        decoded = []
        next_frame_end = edges[0][0]
        for start in starts:
            if start < next_frame_end:
                continue
            if level_at(edges, start + bit_time / 2) != 0:
                raise AssertionError("Invalid UART start bit")
            value = sum(level_at(edges, start + (1.5 + bit) * bit_time) << bit
                        for bit in range(data_bits))
            position = 1 + data_bits
            if parity != "none":
                received = level_at(edges, start + (position + 0.5) * bit_time)
                expected_bit = (value.bit_count() % 2) ^ (parity == "odd")
                if received != expected_bit:
                    raise AssertionError("UART parity error")
                position += 1
            for bit in range(stop_bits):
                if level_at(edges, start + (position + bit + 0.5) * bit_time) != 1:
                    raise AssertionError("UART framing error: stop bit low")
            frame_bits = position + stop_bits
            for time, _ in edges[1:]:
                elapsed = (time - start) / bit_time
                if 0 < elapsed < frame_bits:
                    if abs(elapsed - round(elapsed)) > tolerance:
                        raise AssertionError("UART bit transition violates baud tolerance")
            next_frame_end = start + frame_bits * bit_time * (1 - tolerance)
            decoded.append(value)
        assert_sequence(decoded, expected, "UART sampled bytes")
