/*
 * AuraCore — Yapisal Saglik Izleme Firmware (ESP32) v1.0
 * 
 * Sensorler: MPU6050 (ivme), ADS1115 (nem/korozyon), HX711 (gerinim), Piezo (darbe)
 * Veri Akisi: delay() YOK, millis() tabanli dual-loop
 *   Hizli Hat (50ms/20Hz+): MPU6050 + Piezo
 *   Yavas Hat (1000ms/1Hz): HX711 + ADS1115
 * Cikti: JSON -> Seri Port (115200 baud)
 */

#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADS1X15.h>
#include <HX711.h>
#include <ArduinoJson.h>

// --- PIN KONFIGURASYONU ---
#define HX711_DOUT_PIN  18
#define HX711_SCK_PIN   19
#define PIEZO_PIN       36

// --- ZAMANLAMA ---
#define FAST_INTERVAL_MS   50
#define SLOW_INTERVAL_MS  1000

// --- SENSOR NESNELERI ---
Adafruit_MPU6050 mpu;
Adafruit_ADS1115 ads;
HX711 scale;

unsigned long lastFastTime = 0;
unsigned long lastSlowTime = 0;

#define HX711_CALIBRATION_FACTOR  1.0

void setup() {
    Serial.begin(115200);
    while (!Serial) { ; }
    Wire.begin();

    // MPU6050
    if (!mpu.begin()) {
        Serial.println("{\"error\":\"MPU6050 bulunamadi!\"}");
        while (1) { ; }
    }
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

    // ADS1115
    if (!ads.begin()) {
        Serial.println("{\"error\":\"ADS1115 bulunamadi!\"}");
        while (1) { ; }
    }
    ads.setGain(GAIN_ONE);

    // HX711
    scale.begin(HX711_DOUT_PIN, HX711_SCK_PIN);
    scale.set_scale(HX711_CALIBRATION_FACTOR);
    scale.tare();

    // Piezo
    analogReadResolution(12);
    pinMode(PIEZO_PIN, INPUT);

    Serial.println("{\"status\":\"AuraCore firmware baslatildi\",\"version\":\"1.0\"}");
    lastFastTime = millis();
    lastSlowTime = millis();
}

void loop() {
    unsigned long currentTime = millis();

    // HIZLI HAT (20Hz+): MPU6050 + Piezo
    if (currentTime - lastFastTime >= FAST_INTERVAL_MS) {
        lastFastTime = currentTime;

        sensors_event_t a, g, temp;
        mpu.getEvent(&a, &g, &temp);

        int piezoSum = 0;
        for (int i = 0; i < 4; i++) {
            piezoSum += analogRead(PIEZO_PIN);
        }

        StaticJsonDocument<256> doc;
        doc["type"]  = "fast";
        doc["ts"]    = millis();
        doc["ax"]    = roundf(a.acceleration.x * 100) / 100;
        doc["ay"]    = roundf(a.acceleration.y * 100) / 100;
        doc["az"]    = roundf(a.acceleration.z * 100) / 100;
        doc["piezo"] = piezoSum / 4;
        serializeJson(doc, Serial);
        Serial.println();
    }

    // YAVAS HAT (1Hz): HX711 + ADS1115
    if (currentTime - lastSlowTime >= SLOW_INTERVAL_MS) {
        lastSlowTime = currentTime;

        long strainValue = 0;
        if (scale.is_ready()) {
            strainValue = scale.get_units(5);
        }

        int16_t nem1Value     = ads.readADC_SingleEnded(0);
        int16_t nem2Value     = ads.readADC_SingleEnded(1);
        int16_t korozyonValue = ads.readADC_SingleEnded(2);

        StaticJsonDocument<256> doc;
        doc["type"]     = "slow";
        doc["ts"]       = millis();
        doc["strain"]   = strainValue;
        doc["nem1"]     = nem1Value;
        doc["nem2"]     = nem2Value;
        doc["korozyon"] = korozyonValue;
        serializeJson(doc, Serial);
        Serial.println();
    }
}
