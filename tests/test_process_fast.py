"""process_fast()'daki ivme RMS hesabı ve alan işleme için testler.

process_fast(), self.latest['accel_rms']'i `sqrt(ax^2 + ay^2 + az^2)`
formülüyle hesaplar. Kapsam:
  - RMS formülünün temel doğruluğu (3-4-5 üçgeni ve üç eksenli katkı).
  - İşaretin RMS'i etkilememesi (kareler alındığından negatif değerler
    de doğru sonuç verir).
  - Eksenlerden biri veya tümü eksik geldiğinde 0 varsayımı.
  - ax/ay/az için float(), piezo için int() dönüşümü — piezo'nun
    yuvarlama değil kesme yapması.
  - piezo_buffer ve ivme tamponlarına (accel_x/y/z_buffer) her çağrıda
    tam olarak bir örnek eklenmesi.
  - on_fast_data callback'ine iletilen sözlüğün self.latest'ten
    bağımsız bir KOPYA olması.
"""
import pytest


def test_rms_3_4_5_ucgeninde_dogru_hesaplanir(engine):
    """ax=3, ay=4, az=0 için accel_rms = sqrt(9+16+0) = 5.0 olmalı."""
    engine.process_fast({'ax': 3.0, 'ay': 4.0, 'az': 0.0, 'piezo': 100})

    assert engine.latest['accel_rms'] == pytest.approx(5.0)


def test_rms_uc_eksenin_tumu_katki_yapar(engine):
    """Her üç eksen de RMS'e karesel olarak katkı yapmalı."""
    engine.process_fast({'ax': 1.0, 'ay': 2.0, 'az': 2.0, 'piezo': 100})

    assert engine.latest['accel_rms'] == pytest.approx(3.0)  # sqrt(1+4+4)=3


def test_negatif_degerlerde_rms_isaretten_etkilenmez(engine):
    """RMS kareler üzerinden hesaplandığından, negatif eksen değerleri de
    pozitif değerlerle aynı büyüklükte sonuç üretmeli."""
    engine.process_fast({'ax': -3.0, 'ay': 4.0, 'az': 0.0, 'piezo': 100})

    assert engine.latest['accel_rms'] == pytest.approx(5.0)


def test_tum_eksenler_eksikken_rms_sifir_olur(engine):
    """ax/ay/az veri sözlüğünde yoksa 0.0 varsayılır; RMS de 0.0 olur."""
    engine.process_fast({'piezo': 100})

    assert engine.latest['ax'] == 0.0
    assert engine.latest['ay'] == 0.0
    assert engine.latest['az'] == 0.0
    assert engine.latest['accel_rms'] == 0.0


def test_bir_eksen_eksikken_sifir_varsayilir_rms_dusuk_gorunur(engine):
    """Yalnızca az eksik geldiğinde 0 varsayılır; RMS yalnızca mevcut
    eksenlerden hesaplanır (eksik eksenin gerçek değeri bilinmez)."""
    engine.process_fast({'ax': 3.0, 'ay': 4.0, 'piezo': 100})  # az yok

    assert engine.latest['az'] == 0.0
    assert engine.latest['accel_rms'] == pytest.approx(5.0)  # sqrt(9+16+0)


def test_piezo_int_donusumu_ile_kesilir_yuvarlanmaz(engine):
    """piezo, int() ile dönüştürülür — yuvarlama değil kesmedir
    (150.9 -> 150)."""
    engine.process_fast({'ax': 0.0, 'ay': 0.0, 'az': 0.0, 'piezo': 150.9})

    assert engine.latest['piezo'] == 150


def test_ax_ay_az_string_girdiler_float_e_donusturulur(engine):
    """ax/ay/az, float() ile dönüştürülür; sayısal içerikli string
    girdiler de kabul edilir."""
    engine.process_fast({'ax': '3.5', 'ay': '0', 'az': '0', 'piezo': 100})

    assert engine.latest['ax'] == pytest.approx(3.5)


def test_tamponlara_her_cagrida_tek_ornek_eklenir(engine):
    """piezo_buffer ve ivme tamponları, her process_fast() çağrısında tam
    olarak bir yeni örnekle büyümeli ve son eklenen değeri taşımalı."""
    baslangic_uzunluk = len(engine.piezo_buffer)

    engine.process_fast({'ax': 1.0, 'ay': 2.0, 'az': 3.0, 'piezo': 42})

    assert len(engine.piezo_buffer) == baslangic_uzunluk + 1
    assert engine.piezo_buffer[-1] == 42
    assert engine.accel_x_buffer[-1] == pytest.approx(1.0)
    assert engine.accel_y_buffer[-1] == pytest.approx(2.0)
    assert engine.accel_z_buffer[-1] == pytest.approx(3.0)


def test_on_fast_data_callback_hesaplanan_rms_degerini_icerir(engine):
    """on_fast_data callback'i, hesaplanan accel_rms değerini içeren bir
    latest kopyası almalı; bu kopya self.latest ile aynı nesne
    olmamalı."""
    yakalanan = []
    engine.on_fast_data = lambda latest: yakalanan.append(latest)

    engine.process_fast({'ax': 3.0, 'ay': 4.0, 'az': 0.0, 'piezo': 100})

    assert len(yakalanan) == 1
    assert yakalanan[0]['accel_rms'] == pytest.approx(5.0)
    assert yakalanan[0] is not engine.latest
