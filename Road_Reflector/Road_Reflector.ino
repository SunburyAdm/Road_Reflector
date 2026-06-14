#include <Arduino.h>
#include <math.h>

#define NTC_ADC_PIN 4

const float SERIES_RESISTOR = 100000.0;      // 100k fixed resistor
const float NOMINAL_RESISTANCE = 100000.0;   // 100k NTC at 25°C
const float NOMINAL_TEMPERATURE = 25.0;      // 25°C
const float BETA_COEFFICIENT = 3950.0;
const float ADC_MAX = 4095.0;
const float VCC = 3.3;

float calculateTemperatureC(float resistance)
{
  float steinhart = resistance / NOMINAL_RESISTANCE;
  steinhart = log(steinhart);
  steinhart /= BETA_COEFFICIENT;
  steinhart += 1.0 / (NOMINAL_TEMPERATURE + 273.15);
  steinhart = 1.0 / steinhart;
  steinhart -= 273.15;

  return steinhart;
}

void setup()
{
  delay(3000);

  Serial.begin(115200);
  delay(1000);

  analogReadResolution(12);
  analogSetPinAttenuation(NTC_ADC_PIN, ADC_11db);

  Serial.println();
  Serial.println("ESP32-C3 NTC debug test");
}

void loop()
{
  const int samples = 30;
  uint32_t adcSum = 0;

  for (int i = 0; i < samples; i++) {
    adcSum += analogRead(NTC_ADC_PIN);
    delay(5);
  }

  float adcValue = adcSum / (float)samples;
  float voltage = (adcValue / ADC_MAX) * VCC;

  // Use this if your wiring is:
  // 3.3V -> 100k resistor -> ADC -> NTC -> GND
  float ntcResistance = SERIES_RESISTOR * (voltage / (VCC - voltage));

  float temperatureC = calculateTemperatureC(ntcResistance);

  Serial.println("-----------------------------");
  Serial.print("ADC raw: ");
  Serial.println(adcValue);

  Serial.print("Voltage: ");
  Serial.print(voltage, 3);
  Serial.println(" V");

  Serial.print("NTC resistance: ");
  Serial.print(ntcResistance, 0);
  Serial.println(" ohms");

  Serial.print("Temperature: ");
  Serial.print(temperatureC, 2);
  Serial.println(" C");

  delay(1000);
}