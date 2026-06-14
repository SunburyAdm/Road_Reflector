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

// Usa el voltaje real que mediste.
// Si cambias alimentación, mide otra vez 3V3 real.
const float NTC_SUPPLY_VOLTAGE = 3.13;

// -------------------- Timing --------------------
const uint32_t SENSOR_INTERVAL_MS = 20;   // 20 ms = 50 Hz output
const uint32_t NTC_INTERVAL_MS = 1000;    // NTC cada 1 segundo

uint32_t lastSensorReadMs = 0;
uint32_t lastNTCReadMs = 0;

float lastTemperatureC = NAN;

Adafruit_LIS3DH lis = Adafruit_LIS3DH();

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

  lis.setRange(LIS3DH_RANGE_16_G);

  // Para verificar cambios rápido.
  // Puedes probar 100, 200 o 400 Hz.
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

  // Header CSV
  Serial.println("time_ms,temp_c,accel_x,accel_y,accel_z,accel_mag");
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
    Serial.println(mag, 4);
  }
}