#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#include <Adafruit_LIS3DH.h>
#include <Adafruit_Sensor.h>

// -------------------- Pins --------------------
#define NTC_ADC_PIN      3
#define NTC_POWER_PIN    2

#define I2C_SDA_PIN      0
#define I2C_SCL_PIN      1

#define PIEZO_ADC_PIN    4

// -------------------- NTC Parameters --------------------
const float SERIES_RESISTOR = 100000.0;
const float NOMINAL_RESISTANCE = 100000.0;
const float NOMINAL_TEMPERATURE = 25.0;
const float BETA_COEFFICIENT = 3950.0;

// Use your measured voltage from the GPIO power pin.
const float NTC_SUPPLY_VOLTAGE = 3.13;

// -------------------- Timing --------------------
const uint32_t SENSOR_INTERVAL_MS = 5;       // 200 Hz target
const uint32_t PRINT_INTERVAL_MS  = 20;      // 50 Hz serial output
const uint32_t NTC_INTERVAL_MS    = 1000;    // NTC every 1 second

uint32_t lastSensorReadMs = 0;
uint32_t lastPrintMs = 0;
uint32_t lastNTCReadMs = 0;
uint32_t lastPiezoPeakResetMs = 0;

float lastTemperatureC = NAN;

// -------------------- LIS3DH --------------------
Adafruit_LIS3DH lis = Adafruit_LIS3DH();

// Gravity / vibration processing
float gravityMagEstimate = 9.81;
float peakDynamic = 0.0;
const float GRAVITY_ALPHA = 0.01;

// -------------------- Piezo Processing --------------------
float piezoBaselineMv = 0.0;
float piezoSignalMv = 0.0;
float piezoPeakMv = 0.0;

// Adjust after testing.
// Start low, then tune based on real noise.
const float PIEZO_EVENT_THRESHOLD_MV = 80.0;

// Smaller alpha = slower baseline tracking.
// This helps remove slow drift and keep fast impacts.
const float PIEZO_BASELINE_ALPHA = 0.02;

float calculateNTCTemperatureC(float resistance)
{
  float steinhart = resistance / NOMINAL_RESISTANCE;
  steinhart = log(steinhart);
  steinhart /= BETA_COEFFICIENT;
  steinhart += 1.0 / (NOMINAL_TEMPERATURE + 273.15);
  steinhart = 1.0 / steinhart;
  steinhart -= 273.15;

  return steinhart;
}

float readNTCTemperatureC()
{
  pinMode(NTC_POWER_PIN, OUTPUT);
  digitalWrite(NTC_POWER_PIN, HIGH);

  delay(20);

  const int samples = 10;
  uint32_t mvSum = 0;

  for (int i = 0; i < samples; i++) {
    mvSum += analogReadMilliVolts(NTC_ADC_PIN);
    delay(2);
  }

  float voltage = (mvSum / (float)samples) / 1000.0;

  digitalWrite(NTC_POWER_PIN, LOW);
  pinMode(NTC_POWER_PIN, INPUT);

  if (voltage <= 0.01 || voltage >= NTC_SUPPLY_VOLTAGE - 0.01) {
    return NAN;
  }

  float ntcResistance = SERIES_RESISTOR * (voltage / (NTC_SUPPLY_VOLTAGE - voltage));
  return calculateNTCTemperatureC(ntcResistance);
}

void setupLIS3DH()
{
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  if (!lis.begin(0x18)) {
    if (!lis.begin(0x19)) {
      Serial.println("ERROR,LIS3DH_NOT_FOUND");
      while (1) {
        delay(1000);
      }
    }
  }

  // Use ±2g for small vibration tests.
  // Later, for vehicle impact testing, try ±8g or ±16g.
  lis.setRange(LIS3DH_RANGE_2_G);

  // Fast enough for vibration testing.
  lis.setDataRate(LIS3DH_DATARATE_400_HZ);
}

float readPiezoMv()
{
  const int samples = 4;
  uint32_t mvSum = 0;

  for (int i = 0; i < samples; i++) {
    mvSum += analogReadMilliVolts(PIEZO_ADC_PIN);
  }

  return mvSum / (float)samples;
}

void setup()
{
  delay(3000);

  Serial.begin(115200);
  delay(1000);

  analogReadResolution(12);

  analogSetPinAttenuation(NTC_ADC_PIN, ADC_11db);
  analogSetPinAttenuation(PIEZO_ADC_PIN, ADC_11db);

  pinMode(NTC_POWER_PIN, INPUT);
  pinMode(PIEZO_ADC_PIN, INPUT);

  setupLIS3DH();

  // Initialize piezo baseline
  delay(100);
  piezoBaselineMv = readPiezoMv();

  Serial.println("time_ms,temp_c,ax,ay,az,mag,dynamic_mag,peak_dynamic,piezo_mv,piezo_signal_mv,piezo_peak_mv,piezo_event");
}

void loop()
{
  uint32_t nowMs = millis();

  if (nowMs - lastNTCReadMs >= NTC_INTERVAL_MS) {
    lastNTCReadMs = nowMs;
    lastTemperatureC = readNTCTemperatureC();
  }

  if (nowMs - lastSensorReadMs >= SENSOR_INTERVAL_MS) {
    lastSensorReadMs = nowMs;

    // -------------------- LIS3DH Read --------------------
    sensors_event_t event;
    lis.getEvent(&event);

    float ax = event.acceleration.x;
    float ay = event.acceleration.y;
    float az = event.acceleration.z;

    float mag = sqrt((ax * ax) + (ay * ay) + (az * az));

    gravityMagEstimate =
      (1.0 - GRAVITY_ALPHA) * gravityMagEstimate +
      GRAVITY_ALPHA * mag;

    float dynamicMag = fabs(mag - gravityMagEstimate);

    if (dynamicMag > peakDynamic) {
      peakDynamic = dynamicMag;
    }

    // -------------------- Piezo Read --------------------
    float piezoMv = readPiezoMv();

    piezoBaselineMv =
      (1.0 - PIEZO_BASELINE_ALPHA) * piezoBaselineMv +
      PIEZO_BASELINE_ALPHA * piezoMv;

    piezoSignalMv = fabs(piezoMv - piezoBaselineMv);

    if (piezoSignalMv > piezoPeakMv) {
      piezoPeakMv = piezoSignalMv;
    }

    bool piezoEvent = piezoSignalMv >= PIEZO_EVENT_THRESHOLD_MV;

    // -------------------- Print CSV --------------------
    if (nowMs - lastPrintMs >= PRINT_INTERVAL_MS) {
      lastPrintMs = nowMs;

      Serial.print(nowMs);
      Serial.print(",");

      if (isnan(lastTemperatureC)) {
        Serial.print("nan");
      } else {
        Serial.print(lastTemperatureC, 2);
      }

      Serial.print(",");
      Serial.print(ax, 4);
      Serial.print(",");
      Serial.print(ay, 4);
      Serial.print(",");
      Serial.print(az, 4);
      Serial.print(",");
      Serial.print(mag, 4);
      Serial.print(",");
      Serial.print(dynamicMag, 4);
      Serial.print(",");
      Serial.print(peakDynamic, 4);
      Serial.print(",");
      Serial.print(piezoMv, 2);
      Serial.print(",");
      Serial.print(piezoSignalMv, 2);
      Serial.print(",");
      Serial.print(piezoPeakMv, 2);
      Serial.print(",");
      Serial.println(piezoEvent ? 1 : 0);
    }

    // Reset peaks every second
    if (nowMs - lastPiezoPeakResetMs >= 1000) {
      lastPiezoPeakResetMs = nowMs;
      peakDynamic = 0.0;
      piezoPeakMv = 0.0;
    }
  }
}