"""process_slow()'daki nem1/nem2 ortalaması için testler.

process_slow(), self.latest['nem']'i `(nem1 + nem2) / 2.0` formülüyle
hesaplar. Kapsam:
  - Temel ortalama hesabı ve iki kanalın latest sözlüğüne ayrı ayrı
    yazılması.
  - Kanallardan biri veya ikisi eksik geldiğinde sıfır varsayımının
    ortalamayı nasıl etkilediği (bkz. CLAUDE.md Fail-Safe İlkesi —
    eksik sensör verisinin sessizce 0 sayılması, ortalamayı gerçekte
    olduğundan düşük gösterebilir; bu davranış burada belgeleniyor).
  - int() dönüşümünün yuvarlama değil kesme (truncate) yapması.
  - Bölmenin float (/) olup tam sayı bölmesi (//) olmaması.
  - on_slow_data callback'ine iletilen sözlüğün hesaplanan nem değerini
    içeren, self.latest'ten bağımsız bir KOPYA olması.
"""
import pytest


def test_nem1_nem2_ortalamasi_dogru_hesaplanir(engine):
    """İki kanalın ortalaması latest['nem']'e yazılmalı; latest['nem1']
    ve latest['nem2'] ham değerleriyle ayrı ayrı saklanmalı."""
    engine.process_slow({'strain': 1000, 'nem1': 100, 'nem2': 200, 'korozyon': 50})

    assert engine.latest['nem1'] == 100
    assert engine.latest['nem2'] == 200
    assert engine.latest['nem'] == pytest.approx(150.0)


def test_nem2_eksikken_sifir_varsayilir_ortalamayi_dusurur(engine):
    """nem2 alanı veri sözlüğünde yoksa 0 varsayılır; bu, tek kanaldan
    gelen gerçek okumayı sessizce yarıya düşürür (sensör arızasını
    'düşük nem' gibi gösterme riski — fail-safe açısından not edilmeye
    değer bir davranış)."""
    engine.process_slow({'strain': 1000, 'nem1': 200, 'korozyon': 50})

    assert engine.latest['nem2'] == 0
    assert engine.latest['nem'] == pytest.approx(100.0)  # (200 + 0) / 2


def test_iki_kanal_da_eksikken_nem_sifir_olur(engine):
    """nem1 ve nem2'nin ikisi de eksikse ortalama 0.0 olur."""
    engine.process_slow({'strain': 1000, 'korozyon': 50})

    assert engine.latest['nem1'] == 0
    assert engine.latest['nem2'] == 0
    assert engine.latest['nem'] == 0.0


def test_esit_nem_degerlerinde_ortalama_kendilerine_esittir(engine):
    """İki kanal aynı değeri okuduğunda ortalama o değere eşit olmalı."""
    engine.process_slow({'strain': 1000, 'nem1': 250, 'nem2': 250, 'korozyon': 50})

    assert engine.latest['nem'] == pytest.approx(250.0)


def test_negatif_nem_degerinde_ortalama_dogru_hesaplanir(engine):
    """Ortalama formülü, karşıt işaretli değerlerde de doğru sonuç
    üretmeli (toplamın sıfırlandığı durum dahil)."""
    engine.process_slow({'strain': 1000, 'nem1': -10, 'nem2': 10, 'korozyon': 50})

    assert engine.latest['nem'] == pytest.approx(0.0)


def test_nem_degerleri_int_donusumu_ile_kesilir_yuvarlanmaz(engine):
    """nem1/nem2, int() ile dönüştürülür — bu yuvarlama değil kesmedir
    (150.9 -> 150, 250.1 -> 250)."""
    engine.process_slow({'strain': 1000, 'nem1': 150.9, 'nem2': 250.1, 'korozyon': 50})

    assert engine.latest['nem1'] == 150
    assert engine.latest['nem2'] == 250
    assert engine.latest['nem'] == pytest.approx(200.0)


def test_nem_ortalamasi_float_bolme_kullanir_kesirli_sonuc_verebilir(engine):
    """Bölme `/ 2.0` (float) olduğundan, tek sayıda toplamda kesirli bir
    sonuç üretilmeli — `// 2` (tam sayı bölmesi) gibi kırpılmamalı."""
    engine.process_slow({'strain': 1000, 'nem1': 101, 'nem2': 100, 'korozyon': 50})

    assert engine.latest['nem'] == pytest.approx(100.5)


def test_on_slow_data_callback_hesaplanan_nem_degerini_icerir(engine):
    """on_slow_data callback'i, hesaplanan nem değerini içeren bir
    latest kopyası almalı; bu kopya self.latest ile aynı nesne
    olmamalı (sonradan self.latest değişse bile callback'e iletilen
    sözlük etkilenmemeli)."""
    yakalanan = []
    engine.on_slow_data = lambda latest: yakalanan.append(latest)

    engine.process_slow({'strain': 1000, 'nem1': 120, 'nem2': 180, 'korozyon': 50})

    assert len(yakalanan) == 1
    assert yakalanan[0]['nem'] == pytest.approx(150.0)
    assert yakalanan[0] is not engine.latest
