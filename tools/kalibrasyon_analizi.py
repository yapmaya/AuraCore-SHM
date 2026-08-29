"""
AuraCore — Sensör Normalizasyon Kalibrasyon Analizi

data/auracore_veriler.csv içindeki gerçek ölçüm verisinden her kanal için
istatistik (min, max, ortalama, std, p1, p5, p50, p95, p99) hesaplar ve
aykırı değerlere dayanıklı [p1, p99] normalizasyon aralığı önerir.

Kullanım:
  python tools/kalibrasyon_analizi.py [csv_yolu]
  (csv_yolu verilmezse data/auracore_veriler.csv kullanılır)

Çıktı:
  - Ekrana kanal başına istatistik tablosu
  - config/sensor_ranges_onerilen.json
"""

import csv
import json
import os
import sys

import numpy as np

CSV_YOLU_VARSAYILAN = "data/auracore_veriler.csv"
JSON_CIKTI_YOLU = "config/sensor_ranges_onerilen.json"

# "Hizli" satırlarda dolu olan kanallar, "Yavas" satırlarda dolu olanlar.
HIZLI_KANALLAR = ["Piezo", "Ax", "Ay", "Az"]
YAVAS_KANALLAR = ["Strain", "Korozyon"]
# Eski şema tekli "Nem", yeni şema "Nem1"/"Nem2" — ikisi de "Yavas" satırında.


def _sayisal(deger):
    """CSV hücresini float'a çevir; boş/"-"/parse edilemeyen değerlerde None döner."""
    if deger is None:
        return None
    deger = deger.strip()
    if deger in ("", "-"):
        return None
    try:
        return float(deger)
    except ValueError:
        return None


def veriyi_oku(csv_yolu):
    """CSV'yi okuyup kanal başına değer listeleri döndürür."""
    kanal_degerleri = {
        "strain": [], "nem": [], "korozyon": [], "piezo": [], "accel": [],
    }

    with open(csv_yolu, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        alanlar = reader.fieldnames or []
        nem_ayrik = "Nem1" in alanlar and "Nem2" in alanlar

        for row in reader:
            tip = row.get("Tip", "")

            if tip == "Hizli":
                piezo = _sayisal(row.get("Piezo"))
                if piezo is not None:
                    kanal_degerleri["piezo"].append(piezo)

                ax = _sayisal(row.get("Ax"))
                ay = _sayisal(row.get("Ay"))
                az = _sayisal(row.get("Az"))
                if ax is not None and ay is not None and az is not None:
                    accel_rms = (ax ** 2 + ay ** 2 + az ** 2) ** 0.5
                    kanal_degerleri["accel"].append(accel_rms)

            elif tip == "Yavas":
                strain = _sayisal(row.get("Strain"))
                if strain is not None:
                    kanal_degerleri["strain"].append(abs(strain))

                korozyon = _sayisal(row.get("Korozyon"))
                if korozyon is not None:
                    kanal_degerleri["korozyon"].append(korozyon)

                if nem_ayrik:
                    nem1 = _sayisal(row.get("Nem1"))
                    nem2 = _sayisal(row.get("Nem2"))
                    if nem1 is not None and nem2 is not None:
                        kanal_degerleri["nem"].append((nem1 + nem2) / 2.0)
                else:
                    nem = _sayisal(row.get("Nem"))
                    if nem is not None:
                        kanal_degerleri["nem"].append(nem)

    return kanal_degerleri


def istatistik_hesapla(degerler):
    """Bir kanalın değer listesinden istatistik sözlüğü üretir."""
    arr = np.array(degerler, dtype=np.float64)
    return {
        "n": int(arr.size),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "p1": float(np.percentile(arr, 1)),
        "p5": float(np.percentile(arr, 5)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
    }


def tabloyu_yazdir(kanal_istatistikleri):
    baslik = f"{'Kanal':<10}{'n':>8}{'min':>12}{'max':>12}{'ortalama':>12}{'std':>12}{'p1':>12}{'p5':>12}{'p50':>12}{'p95':>12}{'p99':>12}"
    print(baslik)
    print("-" * len(baslik))
    for kanal, ist in kanal_istatistikleri.items():
        print(
            f"{kanal:<10}{ist['n']:>8}{ist['min']:>12.2f}{ist['max']:>12.2f}"
            f"{ist['mean']:>12.2f}{ist['std']:>12.2f}{ist['p1']:>12.2f}"
            f"{ist['p5']:>12.2f}{ist['p50']:>12.2f}{ist['p95']:>12.2f}"
            f"{ist['p99']:>12.2f}"
        )
    print()
    print(f"{'Kanal':<10}{'Önerilen aralık [p1, p99]':>30}")
    print("-" * 40)
    for kanal, ist in kanal_istatistikleri.items():
        aralik_str = "[{:.2f}, {:.2f}]".format(ist["p1"], ist["p99"])
        print(f"{kanal:<10}{aralik_str:>30}")


def main():
    csv_yolu = sys.argv[1] if len(sys.argv) > 1 else CSV_YOLU_VARSAYILAN
    if not os.path.exists(csv_yolu):
        print(f"HATA: CSV dosyası bulunamadı: {csv_yolu}")
        sys.exit(1)

    print(f"Okunuyor: {csv_yolu}\n")
    kanal_degerleri = veriyi_oku(csv_yolu)

    kanal_istatistikleri = {}
    for kanal, degerler in kanal_degerleri.items():
        if not degerler:
            print(f"UYARI: '{kanal}' kanalı için veri bulunamadı, atlanıyor.")
            continue
        kanal_istatistikleri[kanal] = istatistik_hesapla(degerler)

    tabloyu_yazdir(kanal_istatistikleri)

    onerilen_aralik = {
        kanal: {"min": ist["p1"], "max": ist["p99"]}
        for kanal, ist in kanal_istatistikleri.items()
    }

    os.makedirs(os.path.dirname(JSON_CIKTI_YOLU), exist_ok=True)
    with open(JSON_CIKTI_YOLU, "w", encoding="utf-8") as f:
        json.dump(
            {
                "kaynak_csv": csv_yolu,
                "sensor_ranges_onerilen": onerilen_aralik,
                "istatistikler": kanal_istatistikleri,
            },
            f, ensure_ascii=False, indent=2,
        )
    print(f"\nÖnerilen aralıklar yazıldı: {JSON_CIKTI_YOLU}")


if __name__ == "__main__":
    main()
