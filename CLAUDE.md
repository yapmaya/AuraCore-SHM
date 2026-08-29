# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proje Amacı

AuraCore-SHM, TEKNOFEST başvurusu için geliştirilen bir **Yapı Sağlığı İzleme (Structural
Health Monitoring / SHM)** sistemidir. Bir binadaki/yapıdaki ivme, gerinim, nem ve korozyon
sensörlerinden gelen verileri gerçek zamanlı toplar, işler ve ağırlıklı bir "hasar skoru"
ile yapının durumunu ("Sağlıklı" / "Yorulma Başlangıcı" / "Kritik Hasar") sınıflandırır.

## Mimari ve Bileşenler

- **`auracore_firmware.ino`** — ESP32 firmware. `delay()` kullanmadan `millis()` tabanlı
  dual-loop ile çalışır:
  - **Hızlı hat (50ms / 20Hz+)**: MPU6050 (ivme, ax/ay/az) + Piezo (darbe, 4 örnek ortalaması)
  - **Yavaş hat (1000ms / 1Hz)**: HX711 (gerinim/strain) + ADS1115 (nem1, nem2, korozyon)
  - Her ölçüm satırı seri porta **JSON** olarak, `type: "fast"` veya `type: "slow"` alanıyla
    basılır. Sensör başlatma hatalarında `{"error": "..."}` yazıp sonsuz döngüde durur
    (bkz. Fail-Safe İlkesi).

- **`auracore_engine.py`** (`AuraCoreEngine` sınıfı) — Python analiz motoru:
  - Seri porttan JSON okur (ayrı thread, `_serial_reader`), veya `start_simulation()` ile
    CSV'den/rastgele üretilen veriden simülasyon yapar.
  - Piezo tamponu üzerinde pencereli **FFT** (Hanning penceresi, `FFT_WINDOW_SIZE=128`,
    `FFT_SAMPLE_RATE=20Hz`) ile baskın frekans ve spektral enerji anomali tespiti yapar.
  - Korozyon sensöründen **dC/dt** (merkezi fark türevi) hesaplar; ilk 50 okumadan sonra
    otomatik eşik kalibrasyonu yapar (`ortalama + 2σ`, ardından ağır kayma ortalamasıyla
    yumuşak güncellenir).
  - `SENSOR_RANGES` ile min-max normalize edilmiş `strain/nem/accel/korozyon/piezo`
    değerlerini `WEIGHTS` ile ağırlıklandırıp `damage_score` (0-1) üretir; `CLASSES`
    eşiklerine göre sınıflandırır.
  - Her satırı `data/auracore_veriler.csv`'ye yazar; callback'ler (`on_fast_data`,
    `on_slow_data`, `on_score_update`, `on_corrosion_alert`, `on_fft_update`) ile UI'ı besler.

- **`auracore_dashboard.py`** — CustomTkinter + matplotlib arayüzü. `AuraCoreEngine`'i
  başlatır (gerçek seri port veya `--simulate` modu), gauge/gösterge/grafik/FFT/korozyon
  trend panellerini periyodik (`after(150, ...)`) günceller.

- **`data/auracore_veriler.csv`** — 69.541+ satırlık ölçüm kaydı. **Dikkat**: dosyanın başlığı
  eski (tekli `Nem` sütunlu) şemadadır; motor artık `Nem1`/`Nem2` ayrı sütunlarını
  bekler (`CSV_HEADER`). `AuraCoreEngine._init_csv()` başlık uyuşmazlığında dosyayı
  otomatik olarak `.legacy_<timestamp>` uzantısıyla yedekleyip yeni şemayla sıfırdan
  oluşturur — veri kaybı gibi görünse de bu beklenen davranıştır.

## Veri Akışı

```
ESP32 (auracore_firmware.ino)
  │  JSON satırları, 115200 baud, Seri Port
  │  {"type":"fast", "ts", "ax","ay","az","piezo"}      (50ms)
  │  {"type":"slow", "ts", "strain","nem1","nem2","korozyon"}  (1000ms)
  ▼
AuraCoreEngine (auracore_engine.py)
  │  process_fast() / process_slow() → FFT, dC/dt, damage_score
  │  → data/auracore_veriler.csv (append)
  │  → callback'ler (on_fast_data, on_slow_data, on_score_update, ...)
  ▼
AuraCoreDashboard (auracore_dashboard.py)
     CustomTkinter/matplotlib arayüzünde gerçek zamanlı görselleştirme
```

## Kodlama Kuralları

- **Türkçe yorum satırları korunmalı.** Kod tabanındaki tüm açıklama yorumları, docstring'ler
  ve kullanıcıya gösterilen metinler (etiketler, log mesajları) Türkçedir; yeni kod eklerken
  bu dile sadık kalın.
- **Bölüm ayırıcı yorum blokları korunmalı.** Mevcut stil, dosyaları mantıksal bloklara ayırmak
  için `# ─────...` (Python) veya `// --- ... ---` (Arduino) tarzı ayırıcı yorumlar kullanır
  (örn. `# ── NORMALİZASYON ──`, `// --- PIN KONFIGURASYONU ---`). Yeni bölüm eklerken aynı
  görsel stili kullanın.
- **Python 3.10+** hedeflenmektedir.
- `auracore_engine.py`'deki `SENSOR_RANGES`, `WEIGHTS`, `CLASSES` gibi kalibrasyon
  sabitleri gerçek CSV verisinden türetilmiştir; bunları değiştirirken gerekçeyi yorum
  olarak belirtin.

## Fail-Safe İlkesi (KRİTİK)

Bu proje bir **yapı güvenliği sistemidir**. Sensör arızası veya veri eksikliği durumunda
sistem **ASLA "sağlıklı" sonucu üretmemelidir** (fail-safe ilkesi). Eksik/hatalı/varsayılan
(0 gibi) sensör verisi, düşük hasar skoruna değil, belirsiz/uyarı durumuna yol açmalıdır.
Bu alanda yapılan her değişiklik bu ilkeye göre değerlendirilmelidir.

## Test ve Çalıştırma Komutları

> Henüz proje için bir test paketi (pytest vb.) veya lint yapılandırması yok. Bu bölüm
> bunlar eklendikçe doldurulacak.

```bash
# Bağımlılıkları kur
pip install -r requirements.txt

# Dashboard'u gerçek donanımla çalıştır (seri port otomatik algılanır: Linux'ta
# /dev/ttyUSB*/ttyACM*, Windows'ta COM5 varsayılan)
python auracore_dashboard.py

# Belirli bir port ile
python auracore_dashboard.py --port /dev/ttyUSB0

# Donanım olmadan simülasyon modu (mevcut CSV'den veya rastgele veri oynatır)
python auracore_dashboard.py --simulate
python auracore_dashboard.py --simulate --csv data/auracore_veriler.csv
```
