#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// ===== 新增：设备标识相关 =====
String deviceId;  // 最终用于写入 JSON 的设备ID

// ===== LED 引脚 =====
#define LED_PIN 2  // 你的 ESP32S3 SuperMini 默认 LED 是 GPIO 2，如果不是请改

bool wifiConnected = false;
bool wsConnected = false;
bool lastSendSuccess = false;  // 数据是否成功发送
unsigned long lastBlinkTime = 0;
bool ledState = false;

// WiFi 配置
const char* ssid = "YOUR_WIFI_SSID";        // 替换为你的 WiFi 名称
const char* password = "YOUR_WIFI_PASSWORD"; // 替换为你的 WiFi 密码

// WebSocket 服务器地址和端口
const char* websocket_server = "YOUR_SERVER_IP"; // 替换为 Python 服务端 IP
const int websocket_port = 5123;              // WebSocket 端口

// WebSocket 客户端
WebSocketsClient webSocket;

// MPU6050 对象
Adafruit_MPU6050 mpu;

// I²C 引脚定义
#define I2C_SDA 4
#define I2C_SCL 5

// 看门狗配置
hw_timer_t *watchdogTimer = NULL;
#define WDT_TIMEOUT 3  // 看门狗超时时间（秒）
bool wdt_initialized = false;

// 看门狗喂狗标志
volatile bool feed_watchdog = true;

// 看门狗中断服务程序
void IRAM_ATTR resetModule() {
    ets_printf("Watchdog reboot!\\n");
    esp_restart();
}

// 初始化硬件看门狗
void initHardwareWatchdog() {
    watchdogTimer = timerBegin(0, 80, true); // 定时器0，分频80，向上计数
    timerAttachInterrupt(watchdogTimer, &resetModule, true);
    timerAlarmWrite(watchdogTimer, WDT_TIMEOUT * 1000000, false); // 设置超时时间
    timerAlarmEnable(watchdogTimer); // 启用看门狗
    wdt_initialized = true;
    Serial.println("Hardware Watchdog Initialized");
}

// 喂硬件看门狗
void feedHardwareWatchdog() {
    if (wdt_initialized) {
        timerWrite(watchdogTimer, 0); // 重置定时器
    }
}

// 软件看门狗 - 监控关键任务状态
unsigned long lastLoopTime = 0;
unsigned long lastDataSendTime = 0;
#define LOOP_TIMEOUT 5000  // 主循环超时5秒
#define DATA_TIMEOUT 10000 // 数据发送超时10秒

void checkSoftwareWatchdog() {
    unsigned long currentTime = millis();
    
    // 检查主循环是否卡住
    if (currentTime - lastLoopTime > LOOP_TIMEOUT) {
        Serial.println("Software Watchdog: Main loop timeout, restarting...");
        esp_restart();
    }
    
    // 检查数据发送是否正常
    if (currentTime - lastDataSendTime > DATA_TIMEOUT) {
        Serial.println("Software Watchdog: Data send timeout, restarting...");
        esp_restart();
    }
}

String getChipID() {
  // 使用芯片的 eFuse MAC 作为唯一ID
  uint64_t chipid = ESP.getEfuseMac();  // ESP32S3 也支持
  char idStr[17];
  sprintf(idStr, "%04X%08X",
          (uint16_t)(chipid >> 32),
          (uint32_t)chipid);
  return String(idStr);
}

void setup() {
    // 初始化串口
    Serial.begin(115200);
    // LED 初始化
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, HIGH);  // 默认常亮（等待连接）
    Serial.println("System Starting...");

    deviceId = getChipID();
    Serial.print("Device ID: ");
    Serial.println(deviceId);

    // 初始化硬件看门狗（尽早初始化）
    initHardwareWatchdog();

    // 连接 WiFi
    Serial.println("Connecting to WiFi...");
    WiFi.begin(ssid, password);
    
    unsigned long wifiStartTime = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(1000);
        Serial.println("Connecting...");
        feedHardwareWatchdog(); // WiFi连接期间也要喂狗
        
        // WiFi连接超时检查
        if (millis() - wifiStartTime > 30000) { // 30秒超时
            Serial.println("WiFi connection timeout, restarting...");
            esp_restart();
        }
    }
    wifiConnected = true;
    Serial.println("WiFi connected! IP: " + WiFi.localIP().toString());
    digitalWrite(LED_PIN, HIGH);  // WiFi连上，但还没WS连接，仍然常亮

    // 初始化 MPU6050
    Wire.begin(I2C_SDA, I2C_SCL);
    if (!mpu.begin()) {
        Serial.println("Failed to find MPU6050 chip");
        // 看门狗会处理这种情况
        while (1) {
            delay(1000);
            feedHardwareWatchdog(); // 即使失败也要喂狗
        }
    }
    Serial.println("MPU6050 Found!");

    // 配置 MPU6050 参数
    mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
    mpu.setGyroRange(MPU6050_RANGE_250_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

    // 初始化 WebSocket
    webSocket.begin(websocket_server, websocket_port, "/");
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(500); // 断开500ms后重连

    // 初始化时间标记
    lastLoopTime = millis();
    lastDataSendTime = millis();
    
    Serial.println("Setup completed successfully");
}

unsigned long lastSend = 0;
const unsigned long sendInterval = 500; // 每500ms发送一次

void sendSensorData() {
    sensors_event_t a, g, temp;
    
    // 读取传感器数据
    if (!mpu.getEvent(&a, &g, &temp)) {
        Serial.println("Failed to read sensor data");
        return;
    }

    StaticJsonDocument<256> doc;  // 稍微加大一点容量
    doc["device_id"] = deviceId;  // 新增：设备唯一ID

    doc["acceleration_x"] = a.acceleration.x;
    doc["acceleration_y"] = a.acceleration.y;
    doc["acceleration_z"] = a.acceleration.z;
    doc["gyro_x"] = g.gyro.x;
    doc["gyro_y"] = g.gyro.y;
    doc["gyro_z"] = g.gyro.z;
    doc["temperature"] = temp.temperature;
    doc["watchdog"] = "alive";

    String payload;
    serializeJson(doc, payload);
    
    // 发送数据并检查结果
    bool sendResult = webSocket.sendTXT(payload);
    lastSendSuccess = sendResult;

    if (sendResult) {
        lastDataSendTime = millis(); 
        Serial.print("Send success: ");
    } else {
        Serial.print("Send failed: ");
        digitalWrite(LED_PIN, HIGH);  // 失败时常亮
    }
    Serial.println(payload);
}

void loop() {
    // 更新主循环时间标记
    lastLoopTime = millis();
    
    // 处理WebSocket事件
    webSocket.loop();
    
    // 检查软件看门狗
    checkSoftwareWatchdog();
    
    // 定时发送传感器数据
    if (millis() - lastSend > sendInterval) {
        lastSend = millis();
        sendSensorData();
    }
    
    // 喂硬件看门狗（每次循环都喂）
    feedHardwareWatchdog();
    
      // ===== LED 控制逻辑 =====
    if (wifiConnected && wsConnected && lastSendSuccess) {
        // 已连接 + 已成功发送 → 闪烁
        if (millis() - lastBlinkTime > 500) { // 闪烁周期 500ms
        lastBlinkTime = millis();
        ledState = !ledState;
        digitalWrite(LED_PIN, ledState ? HIGH : LOW);
        }
    } else {
        // 未连接或发送失败 → 常亮
        digitalWrite(LED_PIN, HIGH);
    }

    // 短暂延时，避免过于频繁的循环
    delay(10);
}

// WebSocket 事件处理
void webSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {

    case WStype_DISCONNECTED:
      wsConnected = false;
      Serial.println("WebSocket Disconnected");
      digitalWrite(LED_PIN, HIGH);  // 常亮，表示掉线
      break;

    case WStype_CONNECTED:
      wsConnected = true;
      Serial.println("WebSocket Connected");
      digitalWrite(LED_PIN, HIGH); // 连接成功，但发送前保持常亮
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

