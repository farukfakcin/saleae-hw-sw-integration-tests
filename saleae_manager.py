"""Logic 2 automation for a single Logic Pro 16 capture."""

from pathlib import Path

from saleae import automation


class SaleaeManager:
    def __init__(self, port=10430, device_id=None):
        self.port = port
        self.device_id = device_id
        self.manager = None
        self.capture = None
        self.analyzers = {}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    def connect(self):
        if self.manager is None:
            self.manager = automation.Manager.connect(port=self.port)
        devices = [device for device in self.manager.get_devices()
                   if not device.is_simulation]
        if self.device_id is None:
            if len(devices) != 1:
                raise RuntimeError(f"Expected one physical Saleae device, found {len(devices)}")
            self.device_id = devices[0].device_id
        elif self.device_id not in {device.device_id for device in devices}:
            raise RuntimeError(f"Saleae device {self.device_id!r} not connected")
        return self

    def start_capture(self, channels, duration_seconds, sample_rate=10_000_000):
        channels = list(channels)
        if not channels or len(set(channels)) != len(channels) or any(
            not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel < 16
            for channel in channels
        ):
            raise ValueError("channels must be unique digital channels 0 through 15")
        if duration_seconds <= 0 or sample_rate <= 0:
            raise ValueError("duration_seconds and sample_rate must be positive")
        if self.capture is not None:
            raise RuntimeError("Close the current capture before starting another")
        if self.manager is None:
            self.connect()
        self.capture = self.manager.start_capture(
            device_id=self.device_id,
            device_configuration=automation.LogicDeviceConfiguration(
                enabled_digital_channels=channels, digital_sample_rate=sample_rate
            ),
            capture_configuration=automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=duration_seconds)
            ),
        )
        self.analyzers = {}
        return self.capture

    def add_i2c(self, scl, sda, label="i2c"):
        return self._add("I2C", label, {"SCL": scl, "SDA": sda})

    def add_spi(self, clock, mosi, miso, enable, label="spi"):
        return self._add("SPI", label, {
            "MOSI": mosi, "MISO": miso, "Clock": clock, "Enable": enable,
            "Bits per Transfer": "8 Bits per Transfer (Standard)"
        })

    def add_uart(self, channel, bit_rate, label="uart"):
        return self._add("Async Serial", label, {
            "Input Channel": channel, "Bit Rate (Bits/s)": bit_rate
        })

    def _add(self, name, label, settings):
        if self.capture is None:
            raise RuntimeError("Start a capture before adding analyzers")
        if not label.isidentifier() or label == "raw" or label in self.analyzers:
            raise ValueError("Analyzer label must be a unique identifier other than 'raw'")
        self.capture.wait()
        handle = self.capture.add_analyzer(name, label=label, settings=settings)
        self.analyzers[label] = handle
        return handle

    def export(self, directory):
        """Wait for the timed capture; export each analyzer table and raw digital CSVs."""
        if self.capture is None:
            raise RuntimeError("No capture to export")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.capture.wait()
        paths = {}
        for label, analyzer in self.analyzers.items():
            path = directory / f"{label}.csv"
            self.capture.export_data_table(str(path), analyzers=[analyzer])
            paths[label] = path
        raw = directory / "raw"
        raw.mkdir(exist_ok=True)
        self.capture.export_raw_data_csv(str(raw))
        paths["raw"] = raw
        return paths

    def close(self):
        try:
            if self.capture is not None:
                self.capture.close()
        finally:
            self.capture = None
            self.analyzers = {}
            if self.manager is not None:
                self.manager.close()
                self.manager = None
