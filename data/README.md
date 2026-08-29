# Veri Klasörü

Bu klasör, AuraCore-SHM donanımından/simülasyonundan toplanan ölçüm kayıtlarını
(`auracore_veriler.csv`) içerir. CSV dosyalarının kendisi `.gitignore` ile
sürüm kontrolünden hariç tutulmuştur (bkz. proje kökündeki `.gitignore`);
yalnızca bu README depoda takip edilir.

Aşağıdaki şablonu, verinin nasıl toplandığını belgelemek için doldurun.

## Veri Seti: `auracore_veriler.csv`

- **Toplama tarihi/aralığı:** _(doldurulacak, örn. 2026-01-10 – 2026-01-15)_
- **Firmware sürümü:** _(doldurulacak, örn. `auracore_firmware.ino` v1.0)_
- **Motor/analiz sürümü:** _(doldurulacak, örn. `auracore_engine.py` v1.0)_
- **Oturum sayısı:** _(doldurulacak, örn. 3 ayrı test oturumu)_
- **Toplam satır sayısı:** _(doldurulacak)_
- **Test ortamı/yapı:** _(doldurulacak — örn. hangi bina/maket, sensörlerin
  yerleşimi, ortam sıcaklığı/nemi gibi koşullar)_
- **Bilinen anomaliler/olaylar:** _(doldurulacak — örn. kasıtlı darbe testleri,
  sensör kopması, kalibrasyon sıfırlamaları gibi zaman damgalı notlar)_
- **Lisans/paylaşım kısıtı:** _(doldurulacak)_

## Şema

CSV başlığı (`AuraCoreEngine.CSV_HEADER`, bkz. `auracore_engine.py`):

```
Zaman, Tip, Strain, Piezo, Nem1, Nem2, Korozyon, Ax, Ay, Az, HasarSkoru, Sinif, KorozyonHizi, KorozyonUyari
```

Sütun açıklamaları için depo kökündeki `README.md` dosyasının "Veri Formatı"
bölümüne bakın.
