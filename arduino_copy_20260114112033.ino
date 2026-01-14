#include <Wire.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_GFX.h>
#include "DHT.h"
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// === 1. KONFIGURASI PIN ===
#define OLED_SCL_PIN 26   
#define OLED_SDA_PIN 25   
#define LED_PIN      33   
#define DHTPIN       32   
#define LDR_PIN      35   

#define DHTTYPE DHT11

// === KONFIGURASI OLED ===
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

DHT dht(DHTPIN, DHTTYPE);

// === KONFIGURASI WIFI & MQTT ===
const char* ssid = "12";
const char* password = "11111111";
const char* mqtt_server = "broker.hivemq.com";
const char* mqtt_topic_pub = "plant/data";
const char* mqtt_topic_sub = "plant/perintah";

WiFiClient espClient;
PubSubClient client(espClient);

// Variabel Global
String statusAI = "Normal";
String statusLED = "OFF";
unsigned long lastMsg = 0;

// === 2. PERUBAHAN PENTING PADA CALLBACK ===
void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  Serial.println("\n[MQTT] Pesan Terbaca: " + message);

  // Pemetaan pesan dari Backend ke Aksi & Status Tampilan
  if (message == "LED_ON") {
    digitalWrite(LED_PIN, HIGH);
    statusLED = "ON";
    statusAI = "Cahaya Kurang";
  } 
  else if (message == "LED_OFF") {
    digitalWrite(LED_PIN, LOW);
    statusLED = "OFF";
    statusAI = "Optimal";
  } 
  else if (message == "SUHU_TINGGI") {
    // Saat suhu tinggi, biasanya LED dimatikan untuk mengurangi panas tambahan
    digitalWrite(LED_PIN, LOW); 
    statusLED = "OFF";
    statusAI = "Suhu Panas!";
  }
}

void setup_wifi() {
  delay(10);
  Serial.print("\nMenghubungkan ke "); Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); 
    Serial.print(".");
  }
  Serial.println("\nWiFi Terhubung!");
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Mencoba koneksi MQTT...");
    String clientId = "ESP32_Plant_" + String(random(0, 999));
    if (client.connect(clientId.c_str())) {
      Serial.println(" TERHUBUNG!");
      client.subscribe(mqtt_topic_sub);
    } else {
      Serial.print(" Gagal, rc="); Serial.print(client.state());
      Serial.println(" Mencoba lagi dalam 5 detik...");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  pinMode(LDR_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN); 
  dht.begin();

  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("OLED Gagal!"));
    for(;;);
  }
  
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(1);
  display.setCursor(20, 25);
  display.println("SISTEM DIMULAI");
  display.display();

  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > 3000) { 
    lastMsg = now;

    float suhu = dht.readTemperature();
    float hum = dht.readHumidity();
    
    // ADC 12-bit (0-4095). Balik nilai: Gelap (4095) jadi 0, Terang (0) jadi 4095
    int rawLDR = analogRead(LDR_PIN);
    int cahayaSesuai = 4095 - rawLDR;

    if (isnan(suhu) || isnan(hum)) {
      Serial.println("Sensor Error!");
      return;
    }

    // Tampilan OLED
    display.clearDisplay();
    display.setCursor(0, 0);
    display.println("PLANT MONITOR AI");
    display.drawLine(0, 10, 128, 10, WHITE);
    
    display.setCursor(0, 18);
    display.print("Suhu : "); display.print(suhu, 1); display.println(" C");
    display.print("Hum  : "); display.print(hum, 1); display.println(" %");
    display.print("Light: "); display.println(cahayaSesuai);

    display.setCursor(0, 45);
    display.println("AI STATUS:");
    display.setCursor(0, 55);
    display.print("> "); display.print(statusAI);
    
    display.display();

    // Kirim JSON ke MQTT
    StaticJsonDocument<200> doc;
    doc["suhu"] = suhu;
    doc["kelembaban"] = hum;
    doc["cahaya_ldr"] = cahayaSesuai;
    doc["led_status"] = statusLED;

    char buffer[200];
    serializeJson(doc, buffer);
    client.publish(mqtt_topic_pub, buffer);

    Serial.println("--------------------------------");
    Serial.print("Suhu       : "); Serial.print(suhu); Serial.println(" °C");
    Serial.print("Kelembaban : "); Serial.print(hum); Serial.println(" %");
    Serial.print("Cahaya LDR : "); Serial.println(cahayaSesuai);
    Serial.print("Status LED : "); Serial.println(statusLED);
    Serial.print("Pesan MQTT : "); Serial.println(buffer); // Menampilkan JSON yang dikirim
    Serial.println("--------------------------------");
  }
}