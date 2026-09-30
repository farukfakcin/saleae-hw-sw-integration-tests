import csv

import pytest

from i2c_validator import I2CValidator
from saleae_manager import SaleaeManager
from spi_validator import SPIValidator
from timing import Frame, assert_pulse_widths, read_edges, read_frames
from uart_validator import UARTValidator


def frames(*entries):
    return [Frame(index * .001, (index + 1) * .001, kind, value)
            for index, (kind, value) in enumerate(entries)]


def test_i2c_transaction():
    captured = frames(("start", ""), ("address", "0x48"), ("ack", ""),
                      ("data", "0xA5"), ("ack", ""), ("stop", ""))
    I2CValidator(captured).validate(0x48, [0xA5])
    with pytest.raises(AssertionError, match="address mismatch"):
        I2CValidator(captured).validate(0x50, [0xA5])
    with pytest.raises(AssertionError, match="ACK"):
        I2CValidator(captured[:4] + frames(("nack", ""), ("stop", ""))).validate(
            0x48, [0xA5])


def test_i2c_waveform():
    scl = [(0, 1), (1, 0), (2, 1), (3, 0), (4, 1), (5, 0), (6, 1)]
    sda = [(0, 1), (.5, 0), (1.2, 1), (3.2, 0), (6.5, 1)]
    I2CValidator.validate_signals(scl, sda, min_high=.5, max_high=2,
                                  min_low=.5, max_low=2, setup=.1, hold=.1)
    with pytest.raises(AssertionError, match="pulse width"):
        assert_pulse_widths(scl, 0, 1.1, 2)


def test_spi_transfer_and_mode():
    captured = frames(("mosi", "0x9a"), ("miso", "0x55"))
    SPIValidator(captured).validate([0x9a], [0x55])
    with pytest.raises(AssertionError, match="MISO"):
        SPIValidator(captured).validate([0x9a], [0x56])
    clock = [(0, 0), (1, 1), (2, 0), (3, 1), (4, 0)]
    cs = [(0, 1), (.5, 0), (4.5, 1)]
    data = [(0, 0), (2.5, 1)]
    SPIValidator.validate_signals(clock, cs, data, None, mode=0,
                                  min_half_period=.9, max_half_period=1.1,
                                  setup=.1, hold=.1)
    with pytest.raises(AssertionError, match="polarity"):
        SPIValidator.validate_signals(clock, cs, data, None, mode=2,
                                      min_half_period=.9, max_half_period=1.1)


def test_uart_data_parity_and_stop():
    rate = 1000
    value = 0x35
    levels = [0, *[(value >> bit) & 1 for bit in range(8)], 0, 1]
    edges = [(0, 1)]
    for index, level in enumerate(levels):
        if level != edges[-1][1]:
            edges.append(((index + 1) / rate, level))
    UARTValidator.validate_signals(edges, [value], baud_rate=rate, parity="even")
    UARTValidator(frames(("data", hex(value)))).validate(
        [value], baud_rate=11000, parity="even")
    with pytest.raises(AssertionError, match="parity"):
        UARTValidator.validate_signals(edges, [value], baud_rate=rate, parity="odd")


def test_csv_readers(tmp_path):
    table = tmp_path / "table.csv"
    with table.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerows([["name", "start_time", "end_time", "type", "data"],
                          ["i2c", "0.1", "0.2", "data", "0x12"]])
    assert read_frames(table) == [Frame(.1, .2, "data", "0x12")]
    raw = tmp_path / "raw.csv"
    with raw.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerows([["Time [s]", "Channel 0"], ["0", "1"],
                          [".1", "1"], [".2", "0"]])
    assert read_edges(raw, "Channel 0") == [(0, 1), (.2, 0)]


def test_capture_setup_with_fake_sdk(monkeypatch, tmp_path):
    class Device:
        device_id = "pro16"
        is_simulation = False

    class Capture:
        def add_analyzer(self, name, **kwargs):
            return name

        def wait(self):
            pass

        def export_data_table(self, path, analyzers):
            assert analyzers
            open(path, "w").close()

        def export_raw_data_csv(self, path):
            assert path

        def close(self):
            pass

    class Manager:
        def get_devices(self):
            return [Device()]

        def start_capture(self, **kwargs):
            assert kwargs["device_id"] == "pro16"
            return Capture()

        def close(self):
            pass

    monkeypatch.setattr("saleae_manager.automation.Manager.connect", lambda **kw: Manager())
    device = SaleaeManager()
    with pytest.raises(ValueError, match="channels"):
        device.start_capture([], 1)
    with device:
        device.start_capture([0, 1], 1)
        device.add_i2c(0, 1)
        with pytest.raises(ValueError, match="label"):
            device.add_i2c(0, 1)
        assert device.export(tmp_path)["i2c"].exists()
