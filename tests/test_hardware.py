"""Opt-in templates: provide a stimulus fixture that drives your own DUT."""

import os

import pytest

from i2c_validator import I2CValidator
from spi_validator import SPIValidator
from timing import read_edges, read_frames
from uart_validator import UARTValidator


def _expected(name):
    value = os.environ.get(name)
    if value is None:
        pytest.skip(f"Set {name} to a comma-separated list of bytes")
    return [int(part.strip(), 0) for part in value.split(",") if part.strip()]


def test_i2c_device(saleae, stimulus, tmp_path):
    expected = _expected("I2C_EXPECT")
    if "I2C_ADDRESS" not in os.environ:
        pytest.skip("Set I2C_ADDRESS to the target 7-bit address")
    address = int(os.environ["I2C_ADDRESS"], 0)
    saleae.start_capture([0, 1], duration_seconds=2)
    stimulus()
    saleae.add_i2c(scl=0, sda=1)
    paths = saleae.export(tmp_path)
    raw = paths["raw"] / "digital.csv"
    I2CValidator.from_signals(read_edges(raw, "Channel 0"),
                              read_edges(raw, "Channel 1")).validate(address, expected)


def test_spi_device(saleae, stimulus, tmp_path):
    expected_mosi = _expected("SPI_MOSI_EXPECT")
    expected_miso = _expected("SPI_MISO_EXPECT")
    saleae.start_capture([2, 3, 4, 5], duration_seconds=2)
    stimulus()
    saleae.add_spi(clock=2, mosi=3, miso=4, enable=5)
    paths = saleae.export(tmp_path)
    SPIValidator(read_frames(paths["spi"])).validate(expected_mosi, expected_miso)


def test_uart_device(saleae, stimulus, tmp_path):
    expected = _expected("UART_EXPECT")
    rate = int(os.environ.get("UART_BAUD", "115200"))
    saleae.start_capture([6], duration_seconds=2)
    stimulus()
    saleae.add_uart(channel=6, bit_rate=rate)
    paths = saleae.export(tmp_path)
    UARTValidator(read_frames(paths["uart"])).validate(expected, baud_rate=rate)
