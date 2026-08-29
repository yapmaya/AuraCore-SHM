# AuraCore-SHM

AuraCore-SHM, TEKNOFEST başvurusu için geliştirilen bir **Yapı Sağlığı İzleme**
(*Structural Health Monitoring / SHM*) sistemidir. Bir binadaki/yapıdaki ivme,
gerinim, nem ve korozyon sensörlerinden gelen verileri gerçek zamanlı toplar,
işler ve ağırlıklı bir "hasar skoru" ile yapının durumunu sınıflandırır:
**Sağlıklı** / **Yorulma Başlangıcı** / **Kritik Hasar**.

## Mimari

```
                    ┌─────────────────────────────────────────┐
                    │        ESP32 (auracore_firmware.ino)     │
                    │  millis() tabanlı dual-loop, delay() yok │
                    │                                           │
                    │  Hızlı Hat (50ms / 20Hz+)                │
                    │    MPU6050 (ax, ay, az) + Piezo (darbe)  │
                    │                                           │
                    │  Yavaş Hat (1000ms / 1Hz)                │
                    │    HX711 (strain) + ADS1115               │
                    │    (nem1, nem2, korozyon)                │
                    └───────────────────┬───────────────────────┘
                                        │ JSON, 115200 baud, Seri Port
                                        │ {"type":"fast", ...}
                                        │ {"type":"slow", ...}
                                        ▼
                    ┌─────────────────────────────────────────┐
                    │     AuraCoreEngine (auracore_engine.py)   │
                    │                                           │
                    │  process_fast() ── FFT (Hanning, 128nk)  │
                    │  process_slow() ── dC/dt korozyon analizi │
                    │       │                                   │
                    │       ▼                                   │
                    │  compute_damage_score() ── damage_score   │
                    │       │                                   │
                    │       ├──▶ data/auracore_veriler.csv      │
                    │       └──▶ callback'ler (on_fast_data,    │
                    │            on_slow_data, on_score_update, │
                    │            on_corrosion_alert,             │
                    │            on_fft_update)                 │
                    └───────────────────┬───────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────┐
                    │  AuraCoreDashboard (auracore_dashboard.py)│
                    │  CustomTkinter + matplotlib arayüzü       │
                    │  gauge / göstergeler / grafikler / FFT /  │
                    │  korozyon trendi (periyodik güncelleme)   │
                    └─────────────────────────────────────────┘
```

## Donanım

| Bileşen    | Görev                                    |
|------------|-------------------------------------------|
| ESP32      | Ana mikrodenetleyici, sensör okuma + JSON çıktı |
| MPU6050    | 3 eksen ivme (+ gyro) ölçümü               |
| HX711      | Gerinim ölçer (strain gauge) amplifikatörü |
| ADS1115    | 16-bit ADC — nem1, nem2, korozyon kanalları |
| Piezo sensör | Darbe / titreşim algılama (dahili ADC)   |

### Pin Bağlantı Tablosu

| Sensör             | Pin(ler)                                 | Not                                   |
|--------------------|-------------------------------------------|----------------------------------------|
| HX711 (gerinim)    | DOUT: GPIO18, SCK: GPIO19                 | `HX711_CALIBRATION_FACTOR = 1.0`      |
| Piezo (darbe)      | GPIO36 (ADC1_CH0 / VP)                    | 12-bit çözünürlük, 4 örnek ortalaması |
| MPU6050 (ivme)     | I2C — SDA: GPIO21, SCL: GPIO22 (ESP32 varsayılan `Wire.begin()`) | ±8g aralık, ±500°/s gyro, 21Hz filtre bandı |
| ADS1115 (nem/korozyon) | I2C — SDA: GPIO21, SCL: GPIO22 (MPU6050 ile paylaşılan bus) | Kanal 0: Nem1, Kanal 1: Nem2, Kanal 2: Korozyon, Gain: 1x |

## Kurulum

```bash
pip install -r requirements.txt
```

## Çalıştırma

```bash
# Gerçek donanımla çalıştır (seri port otomatik algılanır:
# Linux'ta /dev/ttyUSB*/ttyACM*, Windows'ta COM5 varsayılan)
python auracore_dashboard.py

# Belirli bir port ile
python auracore_dashboard.py --port /dev/ttyUSB0

# Donanım olmadan simülasyon modu (mevcut CSV'den veri oynatır)
python auracore_dashboard.py --simulate
python auracore_dashboard.py --simulate --csv data/auracore_veriler.csv
```

## Veri Formatı

### JSON Paket Şeması (Seri Port)

**Hızlı hat** (50ms / 20Hz+):

```json
{"type": "fast", "ts": 123456, "ax": 0.12, "ay": -9.81, "az": 0.05, "piezo": 15820}
```

| Alan    | Tip    | Açıklama                              |
|---------|--------|-----------------------------------------|
| `type`  | string | Her zaman `"fast"`                     |
| `ts`    | int    | ESP32 `millis()` zaman damgası          |
| `ax`    | float  | X ekseni ivmesi (m/s²)                 |
| `ay`    | float  | Y ekseni ivmesi (m/s²)                 |
| `az`    | float  | Z ekseni ivmesi (m/s²)                 |
| `piezo` | int    | Piezo ADC okuması (4 örnek ortalaması) |

**Yavaş hat** (1000ms / 1Hz):

```json
{"type": "slow", "ts": 123456, "strain": 92150, "nem1": 14020, "nem2": 13980, "korozyon": 17105}
```

| Alan       | Tip    | Açıklama                              |
|------------|--------|-----------------------------------------|
| `type`     | string | Her zaman `"slow"`                     |
| `ts`       | int    | ESP32 `millis()` zaman damgası          |
| `strain`   | int    | HX711 gerinim ölçümü                   |
| `nem1`     | int    | ADS1115 kanal 0 — nem sensörü 1        |
| `nem2`     | int    | ADS1115 kanal 1 — nem sensörü 2        |
| `korozyon` | int    | ADS1115 kanal 2 — korozyon sensörü     |

### CSV Sütunları (`data/auracore_veriler.csv`)

| Sütun          | Açıklama                                                    |
|-----------------|--------------------------------------------------------------|
| `Zaman`         | Python tarafında kaydedilen zaman damgası (ms hassasiyetli) |
| `Tip`           | `Hizli` veya `Yavas`                                         |
| `Strain`        | Gerinim değeri (yalnızca `Yavas` satırlarda; diğerlerinde `-`) |
| `Piezo`         | Piezo ADC değeri (yalnızca `Hizli` satırlarda)               |
| `Nem1`, `Nem2`  | Nem sensörü kanalları (yalnızca `Yavas` satırlarda)          |
| `Korozyon`      | Korozyon sensörü ham değeri (yalnızca `Yavas` satırlarda)    |
| `Ax`, `Ay`, `Az`| İvme eksenleri (yalnızca `Hizli` satırlarda)                 |
| `HasarSkoru`    | O anki ağırlıklı hasar skoru (0-1)                           |
| `Sinif`         | Hasar sınıfı: `Sağlıklı` / `Yorulma Başlangıcı` / `Kritik Hasar` |
| `KorozyonHizi`  | Korozyon dC/dt türevi                                        |
| `KorozyonUyari` | Korozyon hızlanma uyarısı (`True`/`False`)                   |

## Bilinen Sınırlamalar

_(bu bölüm doldurulacak)_
