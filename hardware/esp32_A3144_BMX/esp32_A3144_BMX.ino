#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// ===== Device ID =====
String deviceId;

// ===== LED Pin =====
#define LED_PIN 2

bool wifiConnected = false;
bool wsConnected = false;
bool lastSendSuccess = false;
unsigned long lastBlinkTime = 0;
bool ledState = false;

// ===== WiFi Config =====
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// ===== WebSocket Config =====
const char* websocket_server = "YOUR_SERVER_IP";
const int websocket_port = 5123;

WebSocketsClient webSocket;

// ===== Hall Sensor =====
#define HALL_PIN 5
volatile unsigned long pulseCount = 0;
unsigned long lastPulseCount = 0;

void IRAM_ATTR hallISR() {
  pulseCount++;
}

// ===== Hardware Watchdog =====
hw_timer_t *watchdogTimer = NULL;
#define WDT_TIMEOUT 3
bool wdt_initialized = false;

void IRAM_ATTR resetModule() {
  ets_printf("Watchdog reboot!\n");
  esp_restart();
}

void initHardwareWatchdog() {
  watchdogTimer = timerBegin(0, 80, true);
  timerAttachInterrupt(watchdogTimer, &resetModule, true);
  timerAlarmWrite(watchdogTimer, WDT_TIMEOUT * 1000000, false);
  timerAlarmEnable(watchdogTimer);
  wdt_initialized = true;
  Serial.println("Hardware Watchdog Initialized");
}

void feedHardwareWatchdog() {
  if (wdt_initialized) {
    timerWrite(watchdogTimer, 0);
  }
}

// ===== Software Watchdog =====
unsigned long lastLoopTime = 0;
unsigned long lastDataSendTime = 0;
#define LOOP_TIMEOUT 5000
#define DATA_TIMEOUT 10000

void checkSoftwareWatchdog() {
  unsigned long currentTime = millis();

  if (currentTime - lastLoopTime > LOOP_TIMEOUT) {
    Serial.println("Software Watchdog: Main loop timeout, restarting...");
    esp_restart();
  }

  if (currentTime - lastDataSendTime > DATA_TIMEOUT) {
    Serial.println("Software Watchdog: Data send timeout, restarting...");
    esp_restart();
  }
}

// ===== Device ID from eFuse MAC =====
String getChipID() {
  uint64_t chipid = ESP.getEfuseMac();
  char idStr[17];
  sprintf(idStr, "%04X%08X",
          (uint16_t)(chipid >> 32),
          (uint32_t)chipid);
  return String(idStr);
}

// ===== Setup =====
void setup() {
  Serial.begin(115200);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  Serial.println("Hall Sensor System Starting...");

  deviceId = getChipID();
  Serial.print("Device ID: ");
  Serial.println(deviceId);

  initHardwareWatchdog();

  pinMode(HALL_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(HALL_PIN), hallISR, CHANGE);
  Serial.println("Hall Sensor initialized on GPIO " + String(HALL_PIN));

  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);

  unsigned long wifiStartTime = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting...");
    feedHardwareWatchdog();

    if (millis() - wifiStartTime > 30000) {
      Serial.println("WiFi connection timeout, restarting...");
      esp_restart();
    }
  }
  wifiConnected = true;
  Serial.println("WiFi connected! IP: " + WiFi.localIP().toString());
  digitalWrite(LED_PIN, HIGH);

  webSocket.begin(websocket_server, websocket_port, "/");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(500);

  lastLoopTime = millis();
  lastDataSendTime = millis();

  Serial.println("Setup completed successfully");
}

// ===== Data Sending =====
unsigned long lastSend = 0;
const unsigned long sendInterval = 500;

void sendSensorData() {
  unsigned long currentPulseCount;
  noInterrupts();
  currentPulseCount = pulseCount;
  interrupts();

  unsigned long deltaPulses = currentPulseCount - lastPulseCount;
  lastPulseCount = currentPulseCount;

  int hallValue = digitalRead(HALL_PIN);

  // deltaPulses / 2 = revolutions (CHANGE triggers on both rising and falling edges)
  // revs per send interval -> revs per minute
  float rpm = (deltaPulses / 2.0) * (60000.0 / sendInterval);

  StaticJsonDocument<256> doc;
  doc["device_id"] = deviceId;
  doc["hall_value"] = hallValue;
  doc["pulse_count"] = currentPulseCount;
  doc["rpm"] = rpm;
  doc["watchdog"] = "alive";

  String payload;
  serializeJson(doc, payload);

  bool sendResult = webSocket.sendTXT(payload);
  lastSendSuccess = sendResult;

  if (sendResult) {
    lastDataSendTime = millis();
    Serial.print("Send success: ");
  } else {
    Serial.print("Send failed: ");
    digitalWrite(LED_PIN, HIGH);
  }
  Serial.println(payload);
}

// ===== Main Loop =====
void loop() {
  lastLoopTime = millis();

  webSocket.loop();

  checkSoftwareWatchdog();

  if (millis() - lastSend > sendInterval) {
    lastSend = millis();
    sendSensorData();
  }

  feedHardwareWatchdog();

  if (wifiConnected && wsConnected && lastSendSuccess) {
    if (millis() - lastBlinkTime > 500) {
      lastBlinkTime = millis();
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState ? HIGH : LOW);
    }
  } else {
    digitalWrite(LED_PIN, HIGH);
  }

  delay(10);
}

// ===== WebSocket Event Handler =====
void webSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      wsConnected = false;
      Serial.println("WebSocket Disconnected");
      digitalWrite(LED_PIN, HIGH);
      break;

    case WStype_CONNECTED:
      wsConnected = true;
      Serial.println("WebSocket Connected");
      digitalWrite(LED_PIN, HIGH);
      delay(300);
      break;

    case WStype_TEXT:
      Serial.printf("Message: %s\n", payload);
      break;

    case WStype_ERROR:
      wsConnected = false;
      Serial.println("WebSocket Error");
      digitalWrite(LED_PIN, HIGH);
      break;

    case WStype_PING:
      Serial.println("Received PING");
      break;

    case WStype_PONG:
      Serial.println("Received PONG");
      break;
  }

  feedHardwareWatchdog();
}
