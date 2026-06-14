#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#include <Adafruit_LIS3DH.h>
#include <Adafruit_Sensor.h>

// -------------------- Pins --------------------
#define NTC_ADC_PIN     3
#define NTC_POWER_PIN   2

#define I2C_SDA_PIN     0
#define I2C_SCL_PIN     1

// -------------------- NTC Parameters --------------------
const float SERIES_RESISTOR = 100000.0;
const float NOMINAL_RESISTANCE = 100000.0;
const float NOMINAL_TEMPERATURE = 25.0;
const float BETA_COEFFICIENT = 3950.0;
const float NTC_SUPPLY_VOLTAGE = 3.13;

// -------------------- Timing --------------------
const uint32_t SENSOR_INTERVAL_MS = 5;      // 5 ms = 200 Hz serial output target
const uint32_t NTC_INTERVAL_MS = 1000;      // NTC every 1 second
const uint32_t PRINT_INTERVAL_MS = 10;      // Print at 100 Hz

uint32_t lastSensorReadMs = 0;
uint32_t lastNTCReadMs = 0;
uint32_t lastPrintMs = 0;

float lastTemperatureC = NAN;

Adafruit_LIS3DH lis = Adafruit_LIS3DH();

// Low-pass gravity estimate
float gravityMagEstimate = 9.81;
float peakDynamic = 0.0;

// Larger alpha = faster gravity tracking.
// Smaller alpha = better vibration isolation.
const float GRAVITY_ALPHA = 0.01;

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

  // More sensitive for footsteps / small vibrations
  lis.setRange(LIS3DH_RANGE_2_G);

  // Fast enough for footstep and impact testing
  lis.setDataRate(LIS3DH_DATARATE_400_HZ);
}

void setup()
{
  delay(3000);

  Serial.begin(115200);
  delay(1000);

  analogReadResolution(12);
  analogSetPinAttenuation(NTC_ADC_PIN, ADC_11db);

  pinMode(NTC_POWER_PIN, INPUT);

  setupLIS3DH();

  Serial.println("time_ms,temp_c,ax,ay,az,mag,dynamic_mag,peak_dynamic");
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

    sensors_event_t event;
    lis.getEvent(&event);

    float ax = event.acceleration.x;
    float ay = event.acceleration.y;
    float az = event.acceleration.z;

    float mag = sqrt((ax * ax) + (ay * ay) + (az * az));

    // Estimate slow gravity component
    gravityMagEstimate =
      (1.0 - GRAVITY_ALPHA) * gravityMagEstimate +
      GRAVITY_ALPHA * mag;

    // Dynamic vibration component
    float dynamicMag = fabs(mag - gravityMagEstimate);

    if (dynamicMag > peakDynamic) {
      peakDynamic = dynamicMag;
    }

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
      Serial.println(peakDynamic, 4);
    }

    // Reset peak every 1 second approximately
    static uint32_t lastPeakResetMs = 0;
    if (nowMs - lastPeakResetMs >= 1000) {
      lastPeakResetMs = nowMs;
      peakDynamic = 0.0;
    }
  }
}