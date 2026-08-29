import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from auracore_engine import AuraCoreEngine


@pytest.fixture
def engine(tmp_path):
    """0-100 aralığında basit, öngörülebilir kalibrasyonlu bir motor.

    Gerçek config'teki (config/auracore_config.json) kalibrasyon
    değerleri yerine 0-100 aralığı kullanılır ki normalize sonuçları
    (e, m, a, c, p) elle hesaplanabilsin."""
    eng = AuraCoreEngine(
        output_csv=str(tmp_path / "test_kayit.csv"),
        config_path=str(tmp_path / "olmayan_config.json"),
    )
    eng.sensor_ranges = {
        'strain':   {'min': 0, 'max': 100},
        'nem':      {'min': 0, 'max': 100},
        'korozyon': {'min': 0, 'max': 100},
        'piezo':    {'min': 0, 'max': 100},
        'accel':    {'min': 0, 'max': 100},
    }
    eng.weights = {
        'strain': 0.3125, 'accel': 0.25, 'korozyon': 0.25, 'piezo': 0.1875,
    }
    eng.nem_etki_katsayisi = 0.5
    return eng
