# Saleae Logic Pro 16 integration tests

Python/pytest automation for **one physical Logic Pro 16** using the [Logic 2 automation API](https://support.saleae.com/logic-software/automation). Decoded I2C, SPI and UART data-table CSVs drive transaction assertions; raw digital/analog CSVs support independent signal timing assertions. Hardware is optional for the offline unit tests.

## Setup

1. Install Logic 2 and connect the Logic Pro 16 to the test host. Enable **Automation** in Logic 2 (default localhost port `10430`). Logic 2 must be running during hardware tests. Use a supported device firmware and capture sample rate for the selected channels.
2. Wire **ground to DUT ground** and connect the required digital inputs: I2C SCL/SDA to channels `0/1`, SPI CLK/MOSI/MISO/CS to `2/3/4/5`, UART TX to `6` in the examples. Check voltage compatibility, logic thresholds, idle polarity and sample rate before capturing. These inputs **observe** traffic; they cannot drive your DUT.
3. From the repository root, install dependencies in a virtual environment:

   ```sh
   python -m venv .venv
   . .venv/bin/activate
   python -m pip install -r requirements.txt
   python -m pytest -q
   ```

   Offline tests pass without a device. Hardware examples skip unless `SALEAE_HARDWARE=1`; they also require a `stimulus` fixture supplied by your DUT test harness. Never run hardware examples as CI checks without a connected host/DUT.

## Capturing traffic

```python
from saleae_manager import SaleaeManager
from timing import read_edges
from i2c_validator import I2CValidator

with SaleaeManager() as saleae:
    saleae.start_capture([0, 1], duration_seconds=2, sample_rate=10_000_000)
    trigger_your_dut_transaction()  # supply this in your own test
    saleae.add_i2c(scl=0, sda=1)
    files = saleae.export("captures/i2c_case")
    raw = files["raw"] / "digital.csv"
    I2CValidator.from_signals(read_edges(raw, "Channel 0"),
                              read_edges(raw, "Channel 1")).validate(0x48, [0xA5])
```

The first analyzer waits for the timed capture to finish; trigger the DUT **after** starting capture and before adding analyzers/exporting. `export()` writes `<label>.csv` and raw `digital.csv` (and `analog.csv` if analog channels were enabled) under `raw/`. `close()` releases the capture and connection; the context manager does this even on failure. Select a specific physical device with `SaleaeManager(device_id="...")` if more than one is attached. Analyzer labels must be unique Python identifiers other than `raw`.

For SPI: `saleae.add_spi(clock=2, mosi=3, miso=4, enable=5)` and `SPIValidator(read_frames(files["spi"])).validate([0x9a], [0x55])`. For UART: `saleae.add_uart(channel=6, bit_rate=115200)` and `UARTValidator(read_frames(files["uart"])).validate([0x35], baud_rate=115200)`. Add multiple analyzers to **the same capture** before export for simultaneous protocol traffic; include all their input channels in `start_capture()`.

## API / assertions

| API | Purpose |
| --- | --- |
| `SaleaeManager(port=10430, device_id=None)` | Connect/close, enumerate physical devices, reject ambiguous device selection. |
| `start_capture(channels, duration_seconds, sample_rate=10_000_000, analog_channels=(), analog_sample_rate=None)` | Timed digital capture; optional analog sampling for rise/fall measurements. |
| `add_i2c(scl, sda)`, `add_spi(clock, mosi, miso, enable)`, `add_uart(channel, bit_rate)` | Add Logic 2 built-in analyzers; optional `label=` on each. SPI defaults to 8 bits per transfer; adjust settings in the wrapper for a different DUT format. |
| `export(directory)` | Wait, export each analyzer's decoded CSV plus raw channel CSVs; returns paths by label and `raw`. |
| `read_frames(path)` | Normalize Logic 2 analyzer CSV fields (`start_time`, `duration` or `end_time`, and protocol data) to `Frame(start,end,kind,data)` objects. SPI `result` rows produce one frame per present direction. |
| `I2CValidator.from_signals(scl, sda)` / `I2CValidator(frames).validate(address, expected_data, allow_nack=False)` | Decode one 7-bit-address transaction from raw edges, then assert START/address/ACK/data/ACK/STOP and bytes. For repeated starts or multiple transactions, split the signal capture first. |
| `SPIValidator(frames).validate(expected_mosi, expected_miso=None)` | Match ordered byte sequences in each direction. |
| `UARTValidator(frames).validate(expected, baud_rate=..., parity="none", data_bits=8, stop_bits=1)` | Reject error frames and assert received bytes fit the data width. Baud/parity/stop **electrical** compliance requires `validate_signals`, below. |
| `read_edges(path, channel)` / `read_samples(path, channel)` | Read raw `digital.csv` transitions / raw `analog.csv` samples; choose the exported column name (e.g. `"Channel 0"`). |
| `assert_range(value, minimum, maximum, name)`, `assert_sequence(actual, expected)`, `assert_pulse_widths(edges, level, minimum, maximum)` | Reusable timing, data and pulse-width checks. |
| `assert_rise_fall(samples, low, high, max_rise, max_fall)` | 10–90% analog rise / 90–10% fall measurement. Analog sample spacing limits resolution; choose an adequate analog rate. |
| `I2CValidator.validate_signals(scl, sda, min_high=..., max_high=..., min_low=..., max_low=..., setup=0, hold=0)` | Verify SCL pulses, SDA START/STOP while SCL high, data stability near SCL rising edges. |
| `SPIValidator.validate_signals(clock, cs, mosi, miso, mode=0, min_half_period=..., max_half_period=..., setup=0, hold=0)` | Assert CS window, clock idle level/CPOL, CPHA sampling edges, half-period and MOSI/MISO setup/hold. `miso` may be `None`. |
| `UARTValidator.validate_signals(edges, expected, baud_rate=..., parity="none", data_bits=8, stop_bits=1, tolerance=.05)` | Sample bit centers and assert start/data/parity/stop bits plus bit-transition timing. |

All times are **seconds**, sample rate is samples/second and raw digital levels are `0`/`1`. `read_frames` expects numeric timestamps (`iso8601_timestamp=False`); the wrapper requests hexadecimal decoded bytes. The I2C data-table shape has not been verified against a Logic 2 fixture, so the examples use raw SCL/SDA decoding instead. Decoded formats can vary by Logic 2/analyzer version; inspect the exported files before adapting the parser to a different format. Validators fail on missing/mismatched frames rather than silently accepting empty data.

For a timeout/response-latency check, compare timestamps: `assert_range(response.start - request.end, 0, 0.01, "response latency")`. For setup/hold or pulse-width assertions, use raw transitions from `read_edges`; decoded timestamps alone do not prove electrical timing. I2C `allow_nack=True` is appropriate for a deliberate NACK/error test. Never use it for transactions expected to be acknowledged.

## Hardware example tests

`tests/test_hardware.py` contains three independent, opt-in scenarios. Override its `stimulus` fixture with a callable that drives **the selected DUT transaction during the two-second capture**. Supply expected bytes as comma-separated integers (hex or decimal), plus an I2C 7-bit address:

```sh
SALEAE_HARDWARE=1 I2C_ADDRESS=0x48 I2C_EXPECT=0xa5 python -m pytest -q tests/test_hardware.py::test_i2c_device
SALEAE_HARDWARE=1 SPI_MOSI_EXPECT=0x9a SPI_MISO_EXPECT=0x55 python -m pytest -q tests/test_hardware.py::test_spi_device
SALEAE_HARDWARE=1 UART_EXPECT=0x35 UART_BAUD=115200 python -m pytest -q tests/test_hardware.py::test_uart_device
```

As shipped these tests **skip** because no project-specific DUT driver exists. Replace the default `stimulus` fixture in `tests/conftest.py` with one that returns a callable driving your DUT before expecting a passing hardware run. Set `SALEAE_PORT` or `SALEAE_DEVICE_ID` if needed. Put additional DUT assertions and raw-timing checks after `export()`; do not treat synthetic offline tests as hardware validation.

## Troubleshooting

- **Connection refused / no devices:** Start Logic 2, enable its automation server, confirm port and USB connection; make sure no other application owns the device. Simulation devices are intentionally excluded.
- **No decoded bytes:** Check analyzer channels, DUT ground, signal thresholds, SPI mode/bit order, I2C pull-ups and UART baud/format. Ensure stimulation happens before the timed capture ends and a suitable sample rate is supported.
- **Wrong CSV header or radix:** Inspect the exported `<label>.csv` / `raw/digital.csv` and adapt the reader to the Logic 2 version or export configuration. The validators consume numeric bytes (`0x..` or decimal) and default English analyzer frame types.
- **Timing assertion fails:** Ensure all times use seconds, raw channel names match the CSV headers, and the sample rate resolves the required setup/hold or transition limit. Digital-only captures cannot measure analog rise/fall times.
- **Tests skip:** Offline tests should run without hardware. To run device tests set `SALEAE_HARDWARE=1`, expected values and a DUT `stimulus` fixture.
