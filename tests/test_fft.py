"""compute_fft() için testler.

Kapsam:
  - piezo_buffer, fft_window_size'a ulaşmadan hesaplama yapılmaz.
  - Bilinen bir sinüs sinyalinin baskın frekansı doğru tespit edilir.
  - Sabit (DC) bir sinyalde ortalama çıkarma sonrası spektral enerji
    sıfıra iner.
  - rfftfreq çıktısı fft_sample_rate/fft_window_size ile tutarlıdır
    (Nyquist frekansı = sample_rate / 2).
  - Enerji kayma-ortalaması anomalisi ilk 10 hesaplamadan önce devreye
    girmez, ani bir enerji sıçramasında devreye girer.
  - Enerji eşiği yeniden kalibrasyonu: _energy_history maxlen=100'lük bir
    KAYMA penceresidir — kalıcı bir rejim değişimi birkaç tekrardan sonra
    'normal' olarak özümsenir, pencere tamamen dolunca eski taban tamamen
    unutulur, ve std≈0 iken bant çok dar olduğundan küçük sapmalar bile
    yakalanır.
"""
import numpy as np
import pytest


def _piezo_sinus_doldur(engine, frekans, genlik=1000.0, ofset=0.0):
    """piezo_buffer'ı tamamen, verilen frekans/genlikte bir sinüs dalgasıyla
    doldurur (fft_window_size uzunluğunda, fft_sample_rate örnekleme hızıyla)."""
    t = np.arange(engine.fft_window_size) / engine.fft_sample_rate
    degerler = ofset + genlik * np.sin(2 * np.pi * frekans * t)
    engine.piezo_buffer.clear()
    engine.piezo_buffer.extend(degerler)


def test_pencere_dolmadan_hesaplama_yapilmaz(engine):
    """piezo_buffer, fft_window_size'ın altındayken compute_fft() erken
    dönmeli; fft sonuçları ve enerji geçmişi başlatılmamalı."""
    for _ in range(engine.fft_window_size - 1):
        engine.piezo_buffer.append(0.0)

    yakalanan = []
    engine.on_fft_update = lambda freqs, mags, dom: yakalanan.append(dom)
    engine.compute_fft()

    assert engine.fft_freqs.size == 0
    assert engine.spectral_energy == 0.0
    assert not hasattr(engine, '_energy_history')
    assert yakalanan == []


def test_bilinen_sinus_sinyalinde_baskin_frekans_dogru_tespit_edilir(engine):
    """5 Hz'lik saf bir sinüs sinyali için baskın frekans 5 Hz olarak
    tespit edilmeli (fft_sample_rate=20Hz, fft_window_size=128 ile
    frekans çözünürlüğü 20/128=0.15625 Hz; 5 Hz tam bir bine denk gelir)."""
    _piezo_sinus_doldur(engine, frekans=5.0, genlik=1000.0)
    engine.compute_fft()

    assert engine.dominant_freq == pytest.approx(5.0)


def test_dc_bileseni_cikarilir_sabit_sinyalde_enerji_sifirdir(engine):
    """Tamamen sabit (AC bileşeni olmayan) bir sinyalde ortalama çıkarma
    sonrası tüm örnekler sıfırlanmalı; spektral enerji sıfır olmalı."""
    engine.piezo_buffer.clear()
    engine.piezo_buffer.extend([500.0] * engine.fft_window_size)
    engine.compute_fft()

    assert engine.spectral_energy == pytest.approx(0.0)


def test_frekans_ekseni_ornekleme_hizi_ile_tutarlidir(engine):
    """rfftfreq çıktısının uzunluğu N/2+1 olmalı ve son değer Nyquist
    frekansına (sample_rate/2) eşit olmalı."""
    _piezo_sinus_doldur(engine, frekans=2.0)
    engine.compute_fft()

    assert len(engine.fft_freqs) == engine.fft_window_size // 2 + 1
    assert engine.fft_freqs[-1] == pytest.approx(engine.fft_sample_rate / 2)


def test_on_fft_update_callback_dogru_degerlerle_cagrilir(engine):
    """Hesaplama başarılı olduğunda on_fft_update callback'i
    (freqs, magnitudes, dominant_freq) ile tetiklenmeli."""
    yakalanan = []
    engine.on_fft_update = lambda freqs, mags, dom: yakalanan.append(
        (freqs, mags, dom)
    )
    _piezo_sinus_doldur(engine, frekans=5.0)
    engine.compute_fft()

    assert len(yakalanan) == 1
    freqs, mags, dom = yakalanan[0]
    assert dom == pytest.approx(engine.dominant_freq)
    assert np.array_equal(freqs, engine.fft_freqs)
    assert np.array_equal(mags, engine.fft_magnitudes)


def test_enerji_anomalisi_ilk_10_hesaplamadan_once_tetiklenmez(engine):
    """Enerji kayma-ortalaması anomali tespiti, geçmişte 10'dan fazla
    kayıt birikene kadar aktif olmamalı (ilk hesaplamada _energy_history
    oluşturulur, fft_anomaly False'a sabitlenir)."""
    _piezo_sinus_doldur(engine, frekans=5.0)

    for _ in range(11):
        engine.compute_fft()

    # 11 kayıt aynı sinyalden geldiğinden std=0; enerji ortalamaya eşit
    # olduğundan (> değil) anomali tetiklenmemeli.
    assert engine.fft_anomaly == False  # noqa: E712 (np.bool_ değeri)


def test_ani_enerji_sicramasi_anomaliyi_tetikler(engine):
    """Kayma-ortalaması istikrar kazandıktan sonra genliği çok büyük bir
    sinyal gelirse fft_anomaly True olmalı."""
    _piezo_sinus_doldur(engine, frekans=5.0, genlik=1000.0)
    for _ in range(11):
        engine.compute_fft()
    assert engine.fft_anomaly == False  # noqa: E712 (np.bool_ değeri)

    _piezo_sinus_doldur(engine, frekans=5.0, genlik=1_000_000.0)
    engine.compute_fft()

    assert engine.fft_anomaly == True  # noqa: E712 (np.bool_ değeri)


# ─────────────────────────────────────────────────────
#  ENERJİ EŞİĞİ YENİDEN KALİBRASYONU (KAYMA PENCERESİ)
# ─────────────────────────────────────────────────────
def test_kalici_seviye_degisimi_birkac_tekrardan_sonra_normal_sayilir(engine):
    """_energy_history sabit bir eşik değil, kayma bir penceredir: enerji
    sıçraması tek seferlik değil sürekli tekrar ederse (kalıcı bir rejim
    değişimi), kayma ortalaması/std yeni seviyeyi birkaç tekrardan sonra
    'normal' olarak özümser ve fft_anomaly False'a döner — sıçrama devam
    ediyor olsa bile."""
    for _ in range(15):
        _piezo_sinus_doldur(engine, frekans=5.0, genlik=100.0)
        engine.compute_fft()
    assert engine.fft_anomaly == False  # noqa: E712 (np.bool_ değeri)

    _piezo_sinus_doldur(engine, frekans=5.0, genlik=500.0)
    engine.compute_fft()
    assert engine.fft_anomaly == True  # noqa: E712 (ilk sıçrama yakalanır)

    for _ in range(6):
        _piezo_sinus_doldur(engine, frekans=5.0, genlik=500.0)
        engine.compute_fft()

    # Aynı seviye sürekli tekrar ettiğinden pencere buna alışır.
    assert engine.fft_anomaly == False  # noqa: E712 (np.bool_ değeri)


def test_pencere_100_kayitla_sinirli_eski_taban_tamamen_unutulur(engine):
    """_energy_history deque'i maxlen=100'dür. Pencere tamamen yeni bir
    enerji seviyesiyle dolduğunda eski taban tamamen tahliye edilir ve
    anomali sınırı sadece yeni seviyeye göre yeniden kalibre olur — eski
    tabana göre çok yüksek sayılacak bir ara-değer bile artık anomali
    sayılmaz."""
    dusuk_genlik, yuksek_genlik, ara_genlik = 100.0, 500.0, 300.0

    for _ in range(100):
        _piezo_sinus_doldur(engine, frekans=5.0, genlik=dusuk_genlik)
        engine.compute_fft()
    dusuk_enerji = engine.spectral_energy
    assert len(engine._energy_history) == 100

    for _ in range(100):
        _piezo_sinus_doldur(engine, frekans=5.0, genlik=yuksek_genlik)
        engine.compute_fft()
    yuksek_enerji = engine.spectral_energy

    # Pencere (maxlen=100) artık tamamen yeni seviyeyle dolu; eski düşük
    # taban tamamen tahliye edilmiş olmalı.
    assert len(engine._energy_history) == 100
    assert min(engine._energy_history) == pytest.approx(yuksek_enerji)
    assert max(engine._energy_history) == pytest.approx(yuksek_enerji)

    # Eski tabana göre çok yüksek sayılacak ara-seviye bir değer, yeni
    # (yüksek) tabana göre ARTIK anomali sayılmıyor.
    _piezo_sinus_doldur(engine, frekans=5.0, genlik=ara_genlik)
    engine.compute_fft()
    ara_enerji = engine.spectral_energy

    assert dusuk_enerji < ara_enerji < yuksek_enerji
    assert engine.fft_anomaly == False  # noqa: E712 (np.bool_ değeri)


def test_sabit_tabanda_std_sifira_yakinken_kucuk_sapma_bile_yakalanir(engine):
    """Enerji geçmişi uzun süre neredeyse sabit kaldığında (std≈0), eşik
    bandı çok dar olur; bu durumda genlikte yalnızca %1'lik bir artış bile
    anomali olarak işaretlenmeli."""
    for _ in range(50):
        _piezo_sinus_doldur(engine, frekans=5.0, genlik=100.0)
        engine.compute_fft()
    assert engine.fft_anomaly == False  # noqa: E712 (np.bool_ değeri)

    _piezo_sinus_doldur(engine, frekans=5.0, genlik=101.0)
    engine.compute_fft()

    assert engine.fft_anomaly == True  # noqa: E712 (np.bool_ değeri)
