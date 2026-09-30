"""Real-device fixture, enabled only with SALEAE_HARDWARE=1."""

import os

import pytest

from saleae_manager import SaleaeManager


@pytest.fixture
def stimulus():
    pytest.skip("Override the stimulus fixture with a DUT transaction callback")


@pytest.fixture
def saleae():
    if os.environ.get("SALEAE_HARDWARE") != "1":
        pytest.skip("Set SALEAE_HARDWARE=1 with Logic 2 automation enabled")
    with SaleaeManager(port=int(os.environ.get("SALEAE_PORT", "10430")),
                       device_id=os.environ.get("SALEAE_DEVICE_ID")) as device:
        yield device
