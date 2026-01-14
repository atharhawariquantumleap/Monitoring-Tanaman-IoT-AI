import paho.mqtt.client as mqtt
import json
import joblib
import time

# === 1. KONFIGURASI ===
BROKER = "broker.hivemq.com"
TOPIC_SUB = "plant/data"      
TOPIC_PUB = "plant/perintah"  
MODEL_FILE = "model_tanaman.pkl"

# === 2. LOAD MODEL ===
try:
    model = joblib.load(MODEL_FILE)
    print("✅ Model ML berhasil dimuat.")
except:
    model = None
    print("⚠️ Model tidak ditemukan, menggunakan logika manual.")

# === 3. CALLBACKS ===
def on_connect(client, userdata, flags, rc):
    print(f"✅ Backend terhubung ke {BROKER}")
    client.subscribe(TOPIC_SUB)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        suhu = data.get('suhu', 0)
        cahaya = data.get('cahaya_ldr', 0)

        # Logika Prediksi ML
        if model:
            pred = model.predict([[suhu, cahaya]])[0]
            perintah = "LED_ON" if pred == 1 else "LED_OFF"
        else:
            perintah = "LED_ON" if cahaya < 1000 else "LED_OFF"

        # Overwrite jika suhu terlalu tinggi
        if suhu > 35:
            # Tetap kirim status suhu tinggi (bisa ditangkap Dashboard)
            client.publish(TOPIC_PUB, "SUHU_TINGGI")
        else:
            client.publish(TOPIC_PUB, perintah)
            
        print(f"[PROCESS] Suhu: {suhu} | Cahaya: {cahaya} | Sent: {perintah}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

# === 4. RUN ===
client = mqtt.Client("Plant_AI_Backend")
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883, 60)
client.loop_forever()