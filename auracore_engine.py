"""
AuraCore — Veri Analiz ve Hasar Skoru Motoru v1.0

Modüller:
  - FFT sinyal işleme (ivme + piezo)
  - Korozyon erken uyarı sistemi (dC/dt otomatik kalibrasyon)
  - Hasar skoru formülasyonu ve sınıflandırma
  - Seri port veri okuyucu

Kullanım:
  from auracore_engine import AuraCoreEngine
  engine = AuraCoreEngine(port='COM5')
  engine.start()
"""

import numpy as np
from scipy.fft import rfft, rfftfreq
from collections import deque
from datetime import datetime
import serial
import json
import csv
import threading
import time
import os

# ═══════════════════════════════════════════════════════════
#  NORMALİZASYON ARALIKLARINI CSV VERİSİNDEN KALİBRE EDİLDİ
# ═══════════════════════════════════════════════════════════
SENSOR_RANGES = {
    'strain':   {'min': 80000, 'max': 110000},
    'nem':      {'min': 13000, 'max': 15000},
    'korozyon': {'min': 16900, 'max': 17300},
    'piezo':    {'min': 15600, 'max': 16800},
    'accel':    {'min': 0,     'max': 100},      # RMS m/s²
}

# Hasar skoru ağırlıkları
WEIGHTS = {
    'strain':   0.25,   # ε
    'nem':      0.20,   # M
    'accel':    0.20,   # A
    'korozyon': 0.20,   # C
    'piezo':    0.15,   # P
}

# Sınıflandırma eşikleri
CLASSES = [
    (0.35, "Sağlıklı",          "#00E676"),
    (0.65, "Yorulma Başlangıcı", "#FF9100"),
    (1.00, "Kritik Hasar",       "#FF1744"),
]

# FFT ayarları
FFT_WINDOW_SIZE = 128
FFT_SAMPLE_RATE = 20.0  # Hz (hızlı hat frekansı)

# Korozyon dC/dt ayarları
CORROSION_WINDOW = 30          # Son N okuma
CORROSION_CALIB_SIGMA = 2.0    # Otomatik kalibrasyon: ortalama + N*sigma


class AuraCoreEngine:
    """Ana analiz motoru. Seri porttan veri alır, işler, hasar skoru üretir."""

    def __init__(self, port='COM5', baud=115200, csv_file='data/auracore_veriler.csv'):
        self.port = port
        self.baud = baud
        self.csv_file = csv_file
        self.ser = None
        self.running = False

        # ── Veri Tamponları ──────────────────────────────
        self.piezo_buffer = deque(maxlen=FFT_WINDOW_SIZE)
        self.accel_x_buffer = deque(maxlen=FFT_WINDOW_SIZE)
        self.accel_y_buffer = deque(maxlen=FFT_WINDOW_SIZE)
        self.accel_z_buffer = deque(maxlen=FFT_WINDOW_SIZE)
        self.corrosion_buffer = deque(maxlen=CORROSION_WINDOW)
        self.corrosion_time_buffer = deque(maxlen=CORROSION_WINDOW)

        # ── Son Okunan Değerler ──────────────────────────
        self.latest = {
            'strain': 0, 'nem1': 0, 'nem2': 0, 'nem': 0, 'korozyon': 0,
            'piezo': 0, 'ax': 0, 'ay': 0, 'az': 0,
            'accel_rms': 0, 'timestamp': '',
        }

        # ── Analiz Sonuçları ─────────────────────────────
        self.damage_score = 0.0
        self.damage_class = "Sağlıklı"
        self.damage_color = "#00E676"
        self.corrosion_rate = 0.0
        self.corrosion_alert = False
        self.corrosion_threshold = None  # Otomatik kalibrasyon

        # FFT sonuçları
        self.fft_freqs = np.array([])
        self.fft_magnitudes = np.array([])
        self.dominant_freq = 0.0
        self.spectral_energy = 0.0
        self.fft_anomaly = False

        # Korozyon dC/dt için kalibrasyon verisi
        self._corrosion_rates_history = deque(maxlen=200)

        # Callback'ler (UI güncellemesi için)
        self.on_fast_data = None   # callback(data_dict)
        self.on_slow_data = None   # callback(data_dict)
        self.on_score_update = None  # callback(score, cls, color)
        self.on_corrosion_alert = None  # callback(rate, threshold)
        self.on_fft_update = None  # callback(freqs, mags, dominant)

        # CSV başlat
        self._init_csv()

    # ─────────────────────────────────────────────────────
    #  CSV KAYIT
    # ─────────────────────────────────────────────────────
    CSV_HEADER = [
        "Zaman", "Tip", "Strain", "Piezo", "Nem1", "Nem2",
        "Korozyon", "Ax", "Ay", "Az",
        "HasarSkoru", "Sinif", "KorozyonHizi", "KorozyonUyari"
    ]

    def _init_csv(self):
        """CSV dosyasını başlıklarla oluştur. Eski şemalı (tekli 'Nem'
        sütunlu) bir dosya varsa yedekleyip yenisini oluşturur."""
        if os.path.exists(self.csv_file):
            with open(self.csv_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            if first_line == ','.join(self.CSV_HEADER):
                return
            backup = f"{self.csv_file}.legacy_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            os.rename(self.csv_file, backup)

        with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(self.CSV_HEADER)

    def _write_csv(self, data, dtype):
        """Tek satır CSV kaydı yaz."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if dtype == "fast":
                writer.writerow([
                    ts, "Hizli", "-", data.get("piezo", ""),
                    "-", "-", "-",
                    data.get("ax", ""), data.get("ay", ""), data.get("az", ""),
                    f"{self.damage_score:.4f}", self.damage_class,
                    f"{self.corrosion_rate:.6f}", self.corrosion_alert
                ])
            else:
                writer.writerow([
                    ts, "Yavas", data.get("strain", ""),
                    "-", data.get("nem1", ""), data.get("nem2", ""),
                    data.get("korozyon", ""),
                    "-", "-", "-",
                    f"{self.damage_score:.4f}", self.damage_class,
                    f"{self.corrosion_rate:.6f}", self.corrosion_alert
                ])

    # ─────────────────────────────────────────────────────
    #  NORMALİZASYON
    # ─────────────────────────────────────────────────────
    @staticmethod
    def normalize(value, vmin, vmax):
        """Min-max normalizasyonu [0, 1] aralığına. Clamp uygulanır."""
        if vmax == vmin:
            return 0.0
        n = (value - vmin) / (vmax - vmin)
        return max(0.0, min(1.0, n))

    # ─────────────────────────────────────────────────────
    #  FFT ANALİZİ
    # ─────────────────────────────────────────────────────
    def compute_fft(self):
        """Piezo tamponu üzerinde pencereli FFT analizi."""
        if len(self.piezo_buffer) < FFT_WINDOW_SIZE:
            return

        signal = np.array(self.piezo_buffer, dtype=np.float64)
        # DC bileşeni çıkar
        signal = signal - np.mean(signal)
        # Hanning penceresi uygula
        window = np.hanning(len(signal))
        windowed = signal * window

        # FFT hesapla
        N = len(windowed)
        yf = rfft(windowed)
        xf = rfftfreq(N, 1.0 / FFT_SAMPLE_RATE)
        magnitudes = 2.0 / N * np.abs(yf)

        self.fft_freqs = xf
        self.fft_magnitudes = magnitudes

        # Baskın frekans (DC hariç)
        if len(magnitudes) > 1:
            idx = np.argmax(magnitudes[1:]) + 1
            self.dominant_freq = xf[idx]
        else:
            self.dominant_freq = 0.0

        # Spektral enerji
        self.spectral_energy = np.sum(magnitudes ** 2)

        # Anormallik tespiti: kayma ortalaması + 2σ
        # (basit threshold — ilk 10 FFT'den sonra aktif)
        if hasattr(self, '_energy_history'):
            self._energy_history.append(self.spectral_energy)
            if len(self._energy_history) > 10:
                arr = np.array(self._energy_history)
                mean_e = np.mean(arr)
                std_e = np.std(arr)
                self.fft_anomaly = self.spectral_energy > (mean_e + 2 * std_e)
        else:
            self._energy_history = deque(maxlen=100)
            self._energy_history.append(self.spectral_energy)
            self.fft_anomaly = False

        if self.on_fft_update:
            self.on_fft_update(self.fft_freqs, self.fft_magnitudes,
                               self.dominant_freq)

    # ─────────────────────────────────────────────────────
    #  KOROZYON dC/dt — OTOMATİK KALİBRASYON
    # ─────────────────────────────────────────────────────
    def compute_corrosion_rate(self):
        """Korozyon sensöründen gelen verinin zamana göre türevini hesapla."""
        if len(self.corrosion_buffer) < 3:
            self.corrosion_rate = 0.0
            return

        values = np.array(self.corrosion_buffer, dtype=np.float64)
        times = np.array(self.corrosion_time_buffer, dtype=np.float64)

        # Merkezi fark yöntemiyle düzgünleştirilmiş türev
        dt = np.diff(times)
        dc = np.diff(values)

        # Sıfır dt'leri engelle
        valid = dt > 0
        if not np.any(valid):
            self.corrosion_rate = 0.0
            return

        rates = dc[valid] / dt[valid]
        self.corrosion_rate = float(np.mean(rates[-5:]))  # Son 5'in ortalaması

        # Otomatik kalibrasyon: ilk 50 okumadan eşik belirle
        self._corrosion_rates_history.append(abs(self.corrosion_rate))

        if self.corrosion_threshold is None:
            if len(self._corrosion_rates_history) >= 50:
                arr = np.array(self._corrosion_rates_history)
                self.corrosion_threshold = float(
                    np.mean(arr) + CORROSION_CALIB_SIGMA * np.std(arr)
                )
        else:
            # Eşik güncellemesi (ağır kayma ortalaması)
            if len(self._corrosion_rates_history) >= 50:
                arr = np.array(list(self._corrosion_rates_history)[-100:])
                new_thresh = float(
                    np.mean(arr) + CORROSION_CALIB_SIGMA * np.std(arr)
                )
                # Yumuşak geçiş
                self.corrosion_threshold = (
                    0.9 * self.corrosion_threshold + 0.1 * new_thresh
                )

        # Uyarı kontrolü
        if self.corrosion_threshold and self.corrosion_threshold > 0:
            self.corrosion_alert = (
                abs(self.corrosion_rate) > self.corrosion_threshold
            )
            if self.corrosion_alert and self.on_corrosion_alert:
                self.on_corrosion_alert(
                    self.corrosion_rate, self.corrosion_threshold
                )

    # ─────────────────────────────────────────────────────
    #  HASAR SKORU HESAPLAMA
    # ─────────────────────────────────────────────────────
    def compute_damage_score(self):
        """Ağırlıklı normalize skor hesapla ve sınıflandır."""
        R = SENSOR_RANGES
        e = self.normalize(
            abs(self.latest['strain']),
            R['strain']['min'], R['strain']['max']
        )
        m = self.normalize(
            self.latest['nem'],
            R['nem']['min'], R['nem']['max']
        )
        a = self.normalize(
            self.latest['accel_rms'],
            R['accel']['min'], R['accel']['max']
        )
        c = self.normalize(
            self.latest['korozyon'],
            R['korozyon']['min'], R['korozyon']['max']
        )
        p = self.normalize(
            self.latest['piezo'],
            R['piezo']['min'], R['piezo']['max']
        )

        W = WEIGHTS
        self.damage_score = (
            e * W['strain'] +
            m * W['nem'] +
            a * W['accel'] +
            c * W['korozyon'] +
            p * W['piezo']
        )
        self.damage_score = max(0.0, min(1.0, self.damage_score))

        # Sınıflandırma
        for threshold, label, color in CLASSES:
            if self.damage_score <= threshold:
                self.damage_class = label
                self.damage_color = color
                break

        if self.on_score_update:
            self.on_score_update(
                self.damage_score, self.damage_class, self.damage_color
            )

    # ─────────────────────────────────────────────────────
    #  VERİ İŞLEME
    # ─────────────────────────────────────────────────────
    def process_fast(self, data):
        """Hızlı hat verisini işle."""
        ax = float(data.get('ax', 0))
        ay = float(data.get('ay', 0))
        az = float(data.get('az', 0))
        piezo = int(data.get('piezo', 0))

        self.latest['ax'] = ax
        self.latest['ay'] = ay
        self.latest['az'] = az
        self.latest['piezo'] = piezo
        self.latest['accel_rms'] = float(np.sqrt(ax**2 + ay**2 + az**2))
        self.latest['timestamp'] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

        # Tamponlara ekle
        self.piezo_buffer.append(piezo)
        self.accel_x_buffer.append(ax)
        self.accel_y_buffer.append(ay)
        self.accel_z_buffer.append(az)

        # FFT güncelle
        self.compute_fft()

        # Hasar skoru güncelle
        self.compute_damage_score()

        # CSV kaydet
        self._write_csv(data, "fast")

        if self.on_fast_data:
            self.on_fast_data(self.latest.copy())

    def process_slow(self, data):
        """Yavaş hat verisini işle."""
        strain = int(data.get('strain', 0))
        nem1 = int(data.get('nem1', 0))
        nem2 = int(data.get('nem2', 0))
        korozyon = int(data.get('korozyon', 0))

        self.latest['strain'] = strain
        self.latest['nem1'] = nem1
        self.latest['nem2'] = nem2
        self.latest['nem'] = (nem1 + nem2) / 2.0
        self.latest['korozyon'] = korozyon
        self.latest['timestamp'] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

        # Korozyon tamponuna ekle
        self.corrosion_buffer.append(korozyon)
        self.corrosion_time_buffer.append(time.time())

        # Korozyon hız analizi
        self.compute_corrosion_rate()

        # Hasar skoru güncelle
        self.compute_damage_score()

        # CSV kaydet
        self._write_csv(data, "slow")

        if self.on_slow_data:
            self.on_slow_data(self.latest.copy())

    # ─────────────────────────────────────────────────────
    #  SERİ PORT OKUYUCU
    # ─────────────────────────────────────────────────────
    def _serial_reader(self):
        """Arka plan thread'i: seri porttan JSON okur ve işler."""
        while self.running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8').strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    dtype = data.get('type', '')
                    if dtype == 'fast':
                        self.process_fast(data)
                    elif dtype == 'slow':
                        self.process_slow(data)
                else:
                    time.sleep(0.005)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            except serial.SerialException:
                self.running = False
                break
            except Exception:
                continue

    def start(self):
        """Seri port bağlantısı kur ve veri okumayı başlat."""
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self.running = True
            self._thread = threading.Thread(
                target=self._serial_reader, daemon=True
            )
            self._thread.start()
            return True
        except serial.SerialException as e:
            print(f"Seri port hatası: {e}")
            return False

    def stop(self):
        """Veri okumayı durdur ve portu kapat."""
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

    # ─────────────────────────────────────────────────────
    #  SİMÜLASYON MODU
    # ─────────────────────────────────────────────────────
    def start_simulation(self, csv_path=None, speed=1.0):
        """
        Gerçek sensör olmadan CSV verisinden veya rastgele
        veri üreterek simülasyon çalıştır.
        """
        self.running = True

        def _sim_loop():
            if csv_path and os.path.exists(csv_path):
                self._simulate_from_csv(csv_path, speed)
            else:
                self._simulate_random(speed)

        self._thread = threading.Thread(target=_sim_loop, daemon=True)
        self._thread.start()
        return True

    def _simulate_from_csv(self, csv_path, speed):
        """Mevcut CSV dosyasından veri oynatarak simülasyon."""
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not self.running:
                    break

                tip = row.get('Tip', '')
                if tip == 'Hizli':
                    data = {
                        'type': 'fast',
                        'piezo': int(row.get('Piezo', 0) or 0),
                        'ax': float(row.get('Ax', 0) or 0),
                        'ay': float(row.get('Ay', 0) or 0),
                        'az': float(row.get('Az', 0) or 0),
                    }
                    self.process_fast(data)
                    time.sleep(0.05 / speed)
                elif tip == 'Yavas':
                    data = {
                        'type': 'slow',
                        'strain': int(row.get('Strain', 0) or 0),
                        'nem1': int(row.get('Nem1', 0) or 0),
                        'nem2': int(row.get('Nem2', 0) or 0),
                        'korozyon': int(row.get('Korozyon', 0) or 0),
                    }
                    self.process_slow(data)
                    time.sleep(0.05 / speed)

    def _simulate_random(self, speed):
        """Rastgele veri üreterek simülasyon."""
        fast_count = 0
        while self.running:
            # Her 20 hızlı pakette 1 yavaş paket
            fast_count += 1
            # Hızlı paket
            data_fast = {
                'type': 'fast',
                'piezo': int(np.random.normal(15800, 100)),
                'ax': round(float(np.random.normal(0, 5)), 2),
                'ay': round(float(np.random.normal(-9.8, 10)), 2),
                'az': round(float(np.random.normal(0, 5)), 2),
            }
            self.process_fast(data_fast)

            if fast_count % 20 == 0:
                data_slow = {
                    'type': 'slow',
                    'strain': int(np.random.normal(90000, 3000)),
                    'nem1': int(np.random.normal(14000, 200)),
                    'nem2': int(np.random.normal(14000, 200)),
                    'korozyon': int(np.random.normal(17100, 50)),
                }
                self.process_slow(data_slow)

            time.sleep(0.05 / speed)

    def get_status(self):
        """Motor durumunu özetle."""
        return {
            'score': self.damage_score,
            'class': self.damage_class,
            'color': self.damage_color,
            'corrosion_rate': self.corrosion_rate,
            'corrosion_alert': self.corrosion_alert,
            'corrosion_threshold': self.corrosion_threshold,
            'dominant_freq': self.dominant_freq,
            'fft_anomaly': self.fft_anomaly,
            'latest': self.latest.copy(),
        }
