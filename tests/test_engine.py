"""compute_damage_score() için testler.

Nem artık hasar skoruna doğrudan girmiyor; korozyon katkısını büyüten bir
risk çarpanı olarak modelleniyor (bkz. auracore_engine.py docstring'i).
Bu testler formülün iki kabul kriterini doğrular:
  1. Korozyon riski yokken (c_norm≈0) nem tek başına skoru değiştirmemeli.
  2. Korozyon riski varken, nem yükseldikçe aynı korozyon seviyesi daha
     yüksek katkı üretmeli.
"""
import json
import os

import pytest

from auracore_engine import AuraCoreEngine, CONFIG_PATH


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


def _set_latest(engine, strain=0, nem=0, accel_rms=0, korozyon=0, piezo=0):
    engine.latest.update({
        'strain': strain, 'nem': nem, 'accel_rms': accel_rms,
        'korozyon': korozyon, 'piezo': piezo,
    })


def test_nem_korozyon_riski_yokken_skoru_degistirmez(engine):
    """Korozyon devresi sağlam okurken (c_norm=0), nem tek başına skoru
    yükseltmemeli — yağmurlu bir gün yapıyı hasarlı göstermemeli."""
    _set_latest(engine, strain=50, nem=10, accel_rms=50, korozyon=100, piezo=50)
    engine.compute_damage_score()
    dusuk_nem_skoru = engine.damage_score

    engine.latest['nem'] = 90
    engine.compute_damage_score()
    yuksek_nem_skoru = engine.damage_score

    assert yuksek_nem_skoru == pytest.approx(dusuk_nem_skoru)


def test_nem_korozyon_riski_varken_katkiyi_buyutur(engine):
    """Korozyon riski mevcutken (c_norm=0.5), nem arttıkça aynı korozyon
    seviyesi daha yüksek skor katkısı üretmeli."""
    _set_latest(engine, strain=50, nem=10, accel_rms=50, korozyon=50, piezo=50)
    engine.compute_damage_score()
    dusuk_nem_skoru = engine.damage_score

    engine.latest['nem'] = 90
    engine.compute_damage_score()
    yuksek_nem_skoru = engine.damage_score

    assert yuksek_nem_skoru > dusuk_nem_skoru


def test_korozyon_katkisi_1_0i_asinca_clamp_edilir(engine):
    """c_norm=1 ve nem=1 iken çarpan 1.5 verir; katkı 1.0'a clamp edilmeli,
    yani skor W_korozyon'u aşmamalı (diğer bileşenler sıfırken)."""
    _set_latest(engine, strain=0, nem=100, accel_rms=0, korozyon=0, piezo=0)
    engine.compute_damage_score()

    assert engine.damage_score == pytest.approx(engine.weights['korozyon'])


def test_tum_bilesenler_maksimumdayken_skor_bire_esittir(engine):
    """Tüm normalize girdiler 1.0 olduğunda (en kötü durum), ağırlıklar 1.0'a
    toplandığı için skor tam olarak 1.0 olmalı ve 'Kritik Hasar' sınıfına
    düşmeli."""
    _set_latest(engine, strain=100, nem=100, accel_rms=100, korozyon=0, piezo=100)
    engine.compute_damage_score()

    assert engine.damage_score == pytest.approx(1.0)
    assert engine.damage_class == "Kritik Hasar"


def test_config_dosyasinda_nem_agirligi_yok_ve_toplam_bir():
    """config/auracore_config.json'daki weights sözlüğünde artık 'nem'
    anahtarı bulunmamalı ve kalan 4 ağırlığın toplamı 1.0 olmalı."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(repo_root, CONFIG_PATH)
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    weights = config['weights']
    assert 'nem' not in weights
    assert sum(weights.values()) == pytest.approx(1.0)
    assert 'nem_etki_katsayisi' in config
