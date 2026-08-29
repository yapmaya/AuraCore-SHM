"""compute_corrosion_rate() için testler.

Kapsam:
  - Yetersiz veri (< 3 okuma) durumunda hız sıfır kalır ve kalibrasyon
    geçmişine katkı yapılmaz.
  - dt=0 olan (aynı zaman damgalı) ardışık okumalar türev hesabından
    hariç tutulur.
  - Otomatik eşik kalibrasyonu (ortalama + N*sigma) ilk 50 geçerli
    okumadan önce devreye girmez, sonra devreye girer.
  - Eşik aşıldığında corrosion_alert True olur ve on_corrosion_alert
    callback'i (rate, threshold) ile çağrılır.
  - Uyarı/callback mantığının sınır durumları: eşik henüz kalibre
    edilmemişken, eşik tam 0.0 iken (falsy — kontrol tamamen atlanır),
    hız eşiğe tam eşitken, sıçrama sonrası sakin okumada, negatif
    (ani düşüş) sıçramalarda ve callback tanımlanmamışken.
"""
import pytest


def _dogrusal_veri_besle(engine, n, egim=1.0, baslangic=0.0, dt=1.0):
    """corrosion_buffer/corrosion_time_buffer'a sabit eğimli n okuma besler
    ve her adımda compute_corrosion_rate() çağırır (process_slow() ile aynı
    sırayı taklit eder: önce tampona ekle, sonra hızı hesapla)."""
    for i in range(n):
        engine.corrosion_buffer.append(baslangic + egim * i)
        engine.corrosion_time_buffer.append(i * dt)
        engine.compute_corrosion_rate()


def test_uc_okumadan_az_veride_hiz_sifir_kalir(engine):
    """corrosion_buffer'da 3'ten az okuma varken türev hesaplanamaz;
    corrosion_rate 0.0'da kalmalı ve kalibrasyon geçmişine eklenmemeli."""
    engine.corrosion_buffer.extend([10, 12])
    engine.corrosion_time_buffer.extend([0.0, 1.0])
    engine.compute_corrosion_rate()

    assert engine.corrosion_rate == 0.0
    assert len(engine._corrosion_rates_history) == 0


def test_sabit_egimli_veride_hiz_dogru_hesaplanir(engine):
    """Sabit eğimli (dc/dt = egim) bir seride hesaplanan hız, son 5
    aralığın ortalaması olduğundan eğime eşit olmalı."""
    _dogrusal_veri_besle(engine, n=6, egim=2.0)

    assert engine.corrosion_rate == pytest.approx(2.0)


def test_sifir_dt_hesaplamadan_haric_tutulur(engine):
    """Aynı zaman damgasıyla gelen ardışık okuma (dt=0) türev hesabına
    katılmamalı; geçerli tek aralık üzerinden hız hesaplanmalı."""
    engine.corrosion_buffer.extend([10, 10, 13])
    engine.corrosion_time_buffer.extend([0.0, 0.0, 1.0])
    engine.compute_corrosion_rate()

    # İlk çift dt=0 olduğundan atlanır; kalan tek geçerli aralık (13-10)/(1-0)=3
    assert engine.corrosion_rate == pytest.approx(3.0)


def test_tum_dt_sifirsa_hiz_sifir_kalir_ve_kalibrasyona_katkida_bulunmaz(engine):
    """Tüm okumalar aynı zaman damgasını taşıyorsa geçerli aralık yoktur;
    hız 0.0'da kalmalı ve kalibrasyon geçmişi güncellenmemeli."""
    engine.corrosion_buffer.extend([5, 6, 7])
    engine.corrosion_time_buffer.extend([2.0, 2.0, 2.0])
    engine.compute_corrosion_rate()

    assert engine.corrosion_rate == 0.0
    assert len(engine._corrosion_rates_history) == 0


def test_50_okumadan_once_esik_kalibre_edilmez(engine):
    """Kalibrasyon geçmişi 50 girdiye ulaşmadan corrosion_threshold None
    kalmalı (otomatik kalibrasyon henüz devreye girmemiş)."""
    _dogrusal_veri_besle(engine, n=40, egim=1.0)

    assert engine.corrosion_threshold is None
    assert engine.corrosion_alert is False


def test_50_okumadan_sonra_esik_otomatik_kalibre_edilir(engine):
    """Kalibrasyon geçmişi 50 girdiye ulaştığında corrosion_threshold
    ortalama + calib_sigma*std formülüyle otomatik belirlenmeli. Sabit
    eğimli veri kullanıldığından std=0 ve eşik doğrudan eğime eşit olur."""
    _dogrusal_veri_besle(engine, n=55, egim=1.0)

    assert engine.corrosion_threshold is not None
    assert engine.corrosion_threshold == pytest.approx(1.0)


def test_esik_asilinca_uyari_tetiklenir_ve_callback_cagrilir(engine):
    """Kalibrasyon sonrası eşiğin çok üzerinde ani bir sıçrama gelirse
    corrosion_alert True olmalı ve on_corrosion_alert(rate, threshold)
    callback'i tetiklenmeli."""
    yakalanan = []
    engine.on_corrosion_alert = lambda rate, threshold: yakalanan.append(
        (rate, threshold)
    )

    _dogrusal_veri_besle(engine, n=60, egim=1.0)
    assert engine.corrosion_alert is False
    assert yakalanan == []

    # Ani sıçrama: eşiğin (≈1.0) çok üzerinde bir korozyon okuması
    son_zaman = 59 * 1.0
    engine.corrosion_buffer.append(1000.0)
    engine.corrosion_time_buffer.append(son_zaman + 1.0)
    engine.compute_corrosion_rate()

    assert engine.corrosion_alert is True
    assert len(yakalanan) == 1
    assert yakalanan[0][0] == pytest.approx(engine.corrosion_rate)
    assert yakalanan[0][1] == pytest.approx(engine.corrosion_threshold)


# ─────────────────────────────────────────────────────
#  UYARI/CALLBACK SINIR DURUMLARI
# ─────────────────────────────────────────────────────
def test_esik_kalibre_olmadan_ani_sicrama_uyari_tetiklemez(engine):
    """corrosion_threshold henüz None iken (50 okumaya ulaşılmadan), çok
    büyük bir sıçrama gelse bile uyarı kontrolü tamamen atlanır — alert
    False'da kalır, callback tetiklenmez."""
    yakalanan = []
    engine.on_corrosion_alert = lambda rate, threshold: yakalanan.append(
        (rate, threshold)
    )

    _dogrusal_veri_besle(engine, n=10, egim=1.0)
    assert engine.corrosion_threshold is None

    engine.corrosion_buffer.append(100000.0)
    engine.corrosion_time_buffer.append(10.0)
    engine.compute_corrosion_rate()

    assert engine.corrosion_threshold is None
    assert engine.corrosion_alert is False
    assert yakalanan == []


def test_esik_sifirken_uyari_durumu_guncellenmez(engine):
    """corrosion_threshold tam olarak 0.0 olduğunda (falsy — `if threshold
    and threshold > 0` koşulu False), uyarı kontrolü tamamen atlanır.
    Bu, corrosion_alert'in ÖNCEKİ (bayat) değerinde donup kalabileceği
    anlamına gelir — büyük bir hız değişimi olsa bile yeniden
    değerlendirilmez."""
    yakalanan = []
    engine.on_corrosion_alert = lambda rate, threshold: yakalanan.append(
        (rate, threshold)
    )
    # Kalibrasyon geçmişi 50'nin altında tutuluyor ki eşik yeniden
    # hesaplanmasın; eşik manuel olarak 0.0'a ve alert True'ya (önceki
    # bir uyarıdan kalma bayat durum) sabitleniyor.
    engine.corrosion_threshold = 0.0
    engine.corrosion_alert = True

    engine.corrosion_buffer.extend([0.0, 0.0, 100.0])
    engine.corrosion_time_buffer.extend([0.0, 1.0, 2.0])
    engine.compute_corrosion_rate()

    assert engine.corrosion_rate == pytest.approx(50.0)  # hız gerçekten hesaplandı
    assert engine.corrosion_threshold == 0.0
    assert engine.corrosion_alert is True  # bayat durum korunuyor, güncellenmedi
    assert yakalanan == []


def test_hiz_esige_tam_esit_oldugunda_uyari_tetiklenmez(engine):
    """corrosion_rate, corrosion_threshold'a tam eşit olduğunda (sınır
    durum), karşılaştırma kesinlikle büyüktür (`>`) olduğundan uyarı
    tetiklenmemeli."""
    yakalanan = []
    engine.on_corrosion_alert = lambda rate, threshold: yakalanan.append(
        (rate, threshold)
    )
    engine.corrosion_threshold = 5.0

    # dc/dt = 5.0 — eşiğe tam eşit bir hız üretir.
    engine.corrosion_buffer.extend([0.0, 5.0, 10.0])
    engine.corrosion_time_buffer.extend([0.0, 1.0, 2.0])
    engine.compute_corrosion_rate()

    assert engine.corrosion_rate == pytest.approx(5.0)
    assert engine.corrosion_alert is False
    assert yakalanan == []


def test_uyari_sonrasi_sakin_okuma_alarmi_sifirlar(engine):
    """Bir sıçramadan sonra hız tekrar eşiğin altına dönerse
    corrosion_alert False'a dönmeli ve ikinci bir callback
    tetiklenmemeli."""
    yakalanan = []
    engine.on_corrosion_alert = lambda rate, threshold: yakalanan.append(
        (rate, threshold)
    )
    engine.corrosion_threshold = 1.0  # sabit eşik, kalibrasyonu atla

    engine.corrosion_buffer.extend([0.0, 1.0, 1000.0])
    engine.corrosion_time_buffer.extend([0.0, 1.0, 2.0])
    engine.compute_corrosion_rate()
    assert engine.corrosion_alert is True
    assert len(yakalanan) == 1

    # Sıçrama sonrası tampon sakin veriyle sıfırdan dolduruluyor — eski
    # sıçramanın son-5 penceresindeki kalıntı etkisi tamamen temizleniyor.
    engine.corrosion_buffer.clear()
    engine.corrosion_time_buffer.clear()
    engine.corrosion_buffer.extend([1000.0, 1001.0, 1002.0])
    engine.corrosion_time_buffer.extend([2.0, 3.0, 4.0])
    engine.compute_corrosion_rate()

    assert engine.corrosion_rate == pytest.approx(1.0)
    assert engine.corrosion_alert is False
    assert len(yakalanan) == 1  # ikinci bir uyarı tetiklenmedi


def test_negatif_ani_dususte_de_uyari_tetiklenir(engine):
    """Korozyon okuması aniden büyük ölçüde düşerse (negatif hız), abs()
    kullanıldığından yine uyarı tetiklenmeli; callback'e ham (negatif)
    hız değeri iletilmeli."""
    yakalanan = []
    engine.on_corrosion_alert = lambda rate, threshold: yakalanan.append(
        (rate, threshold)
    )
    engine.corrosion_threshold = 1.0

    engine.corrosion_buffer.extend([1000.0, 999.0, 0.0])
    engine.corrosion_time_buffer.extend([0.0, 1.0, 2.0])
    engine.compute_corrosion_rate()

    assert engine.corrosion_rate < 0
    assert engine.corrosion_alert is True
    assert len(yakalanan) == 1
    assert yakalanan[0][0] == pytest.approx(engine.corrosion_rate)
    assert yakalanan[0][0] < 0  # callback'e negatif ham değer iletildi
    assert yakalanan[0][1] == pytest.approx(1.0)


def test_callback_tanimli_degilken_hata_vermez(engine):
    """on_corrosion_alert None bırakıldığında (varsayılan), uyarı
    tetiklense bile istisna oluşmamalı; yalnızca corrosion_alert True
    olarak işaretlenmeli."""
    assert engine.on_corrosion_alert is None
    engine.corrosion_threshold = 1.0

    engine.corrosion_buffer.extend([0.0, 1.0, 1000.0])
    engine.corrosion_time_buffer.extend([0.0, 1.0, 2.0])
    engine.compute_corrosion_rate()  # istisna fırlatmamalı

    assert engine.corrosion_alert is True
