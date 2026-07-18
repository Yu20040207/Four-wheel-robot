/*
 * ESP32 24V 电池电压测试程序
 *
 * 分压电路：24V+ ── 100kΩ ──┬── 15kΩ ── GND
 *                            └── GPIO36 (VP)
 *
 * 串口监视器：115200，每秒输出一行电压
 * 接线完成后用万用表对比，调整 BATTERY_CAL_FACTOR
 */

#define BATTERY_ADC_PIN 36
#define BATTERY_R1_OHM 100000.0f
#define BATTERY_R2_OHM 15000.0f
#define BATTERY_CAL_FACTOR 1.0f   // 标定：真实电压 / 程序读数

#define BATTERY_SAMPLE_COUNT 32
#define BATTERY_PRINT_INTERVAL_MS 1000

const float BATTERY_DIVIDER_RATIO = (BATTERY_R1_OHM + BATTERY_R2_OHM) / BATTERY_R2_OHM;

unsigned long lastPrintMs = 0;

float readBatteryVoltage() {
    uint32_t sum = 0;
    for (int i = 0; i < BATTERY_SAMPLE_COUNT; i++) {
        sum += (uint32_t)analogRead(BATTERY_ADC_PIN);
        delayMicroseconds(150);
    }

    float adcRaw = sum / (float)BATTERY_SAMPLE_COUNT;
    float vAdc = adcRaw * 3.3f / 4095.0f;
    return vAdc * BATTERY_DIVIDER_RATIO * BATTERY_CAL_FACTOR;
}

void setup() {
    Serial.begin(115200);
    delay(500);

    analogReadResolution(12);
    analogSetPinAttenuation(BATTERY_ADC_PIN, ADC_11db);

    Serial.println();
    Serial.println("=== ESP32 Battery Voltage Test ===");
    Serial.printf("ADC pin: GPIO%d\n", BATTERY_ADC_PIN);
    Serial.printf("Divider: %.0fk + %.0fk (ratio %.2f)\n",
                  BATTERY_R1_OHM / 1000.0f,
                  BATTERY_R2_OHM / 1000.0f,
                  BATTERY_DIVIDER_RATIO);
    Serial.printf("Cal factor: %.3f\n", BATTERY_CAL_FACTOR);
    Serial.println("Format: ADC_raw, Vadc, Vbat");
    Serial.println("--------------------------------");
}

void loop() {
    unsigned long now = millis();
    if (now - lastPrintMs < BATTERY_PRINT_INTERVAL_MS) {
        return;
    }
    lastPrintMs = now;

    uint32_t sum = 0;
    for (int i = 0; i < BATTERY_SAMPLE_COUNT; i++) {
        sum += (uint32_t)analogRead(BATTERY_ADC_PIN);
        delayMicroseconds(150);
    }
    float adcRaw = sum / (float)BATTERY_SAMPLE_COUNT;
    float vAdc = adcRaw * 3.3f / 4095.0f;
    float vBat = vAdc * BATTERY_DIVIDER_RATIO * BATTERY_CAL_FACTOR;

    Serial.printf("ADC=%4.0f  Vadc=%.3fV  Vbat=%.2fV\n", adcRaw, vAdc, vBat);

    if (vBat < 10.0f) {
        Serial.println("  [提示] Vbat<10V，请检查分压接线或 GPIO36 是否接对");
    }
}
