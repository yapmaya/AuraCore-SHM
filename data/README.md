# Veri Klasörü

Bu klasör, AuraCore-SHM donanımından/simülasyonundan toplanan ölçüm kayıtlarını
(`auracore_veriler.csv`) içerir. CSV dosyalarının kendisi `.gitignore` ile
sürüm kontrolünden hariç tutulmuştur (bkz. proje kökündeki `.gitignore`);
yalnızca bu README depoda takip edilir.

Aşağıdaki şablonu, verinin nasıl toplandığını belgelemek için doldurun.

## Veri Seti: `auracore_veriler.csv`

> ⚠️ **ŞÜPHELİ KAYNAK — GERÇEK DONANIM VERİSİ OLMAYABİLİR.** 2026-08-29'da yapılan
> bir incelemede bu dosyanın gerçek sensörlerden değil, uygulamanın kendi
> `--simulate` rastgele veri üretecinden (`AuraCoreEngine._simulate_random`)
> geldiğine dair güçlü kanıt bulundu:
> - CSV'deki `Nem` değerleri (17663-17665) ve korozyon "yüksek küme" modu
>   (~17674-17681) ile piezo modu (~15800), deponun ilk commit'indeki
>   (`adb8bbe`) `_simulate_random()` fonksiyonunun sabit Gauss parametreleriyle
>   (`nem~N(17665,5)`, `korozyon~N(17678,3)`, `piezo~N(15800,100)`) neredeyse
>   birebir örtüşüyor.
> - `auracore_firmware.ino`'da piezo, ilk commit'ten beri `analogReadResolution(12)`
>   ile 0-4095 aralığında okunuyor; ama CSV'deki piezo değerlerinin **%73.6'sı
>   4095'in üzerinde** (bazıları -32768'e kadar iniyor) — yani bu firmware'in
>   hiçbir sürümünden üretilemez.
> - Korozyon ve piezo'da ayrıca ikinci bir "düşük küme" var (0'a yakın/negatif,
>   bazen -7808 gibi tekrarlayan tam değerler ve "128" değeri anormal sıklıkta) —
>   bu da yukarıdaki dar Gauss dağılımlarından (std=3, std=100) istatistiksel
>   olarak gelemez; kaynağı belirlenemedi (muhtemelen ayrı/hatalı bir üretim yolu
>   ya da hata/sentinel kodu enjeksiyonu).
>
> Sonuç: bu dosyaya dayanan `SENSOR_RANGES`/`config/auracore_config.json`
> kalibrasyonu (bkz. `tools/kalibrasyon_analizi.py`) gerçek sensör fiziğini
> yansıtmıyor olabilir. Gerçek donanımdan yeni veri toplanana kadar bu
> kalibrasyonu **sadece demo/simülasyon amaçlı** güvenilir sayın; gerçek
> donanım entegrasyonu öncesi yeniden kalibre edilmelidir.

- **Toplama tarihi/aralığı:** _(doldurulacak, örn. 2026-01-10 – 2026-01-15) — yukarıdaki notu okuyun, muhtemelen simülatör çıktısı_
- **Firmware sürümü:** _(doldurulacak, örn. `auracore_firmware.ino` v1.0)_
- **Motor/analiz sürümü:** _(doldurulacak, örn. `auracore_engine.py` v1.0)_
- **Oturum sayısı:** _(doldurulacak, örn. 3 ayrı test oturumu)_
- **Toplam satır sayısı:** 69.541
- **Test ortamı/yapı:** _(doldurulacak — örn. hangi bina/maket, sensörlerin
  yerleşimi, ortam sıcaklığı/nemi gibi koşullar)_
- **Bilinen anomaliler/olaylar:** Yukarıdaki "ŞÜPHELİ KAYNAK" notuna bakın —
  korozyon/piezo kanallarında kaynağı belirsiz, tekrarlayan "düşük küme" değerleri var.
- **Lisans/paylaşım kısıtı:** _(doldurulacak)_

## Şema

CSV başlığı (`AuraCoreEngine.CSV_HEADER`, bkz. `auracore_engine.py`):

```
Zaman, Tip, Strain, Piezo, Nem1, Nem2, Korozyon, Ax, Ay, Az, HasarSkoru, Sinif, KorozyonHizi, KorozyonUyari
```

Sütun açıklamaları için depo kökündeki `README.md` dosyasının "Veri Formatı"
bölümüne bakın.
