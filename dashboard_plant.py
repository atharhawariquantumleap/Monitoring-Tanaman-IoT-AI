import streamlit as st
import paho.mqtt.client as mqtt
import json
import joblib
import pandas as pd
import time
import requests
from datetime import datetime
import queue

# === 1. KONFIGURASI SISTEM ===
BROKER = "broker.hivemq.com"
TOPIC_SUB = "plant/data"
TOPIC_PUB = "plant/perintah"
MODEL_FILE = "model_tanaman.pkl"
OWM_API_KEY = "4b031f7ed240d398ab4b7696d2361d97"
CITY_NAME = "Sukabumi"

# Variabel Global untuk komunikasi antar-thread (Thread-safe)
if 'mqtt_queue' not in st.session_state:
    st.session_state.mqtt_queue = queue.Queue()

# Flag koneksi global tetap dipertahankan di latar belakang untuk logika publish
if 'mqtt_status_global' not in globals():
    mqtt_status_global = [False]

# === 2. INISIALISASI SESSION STATE ===
if 'sensor_data' not in st.session_state:
    st.session_state.sensor_data = {"suhu": 0, "kelembaban": 0, "cahaya_ldr": 0, "led_status": "OFF"}
if 'log_history' not in st.session_state:
    st.session_state.log_history = pd.DataFrame(columns=['Waktu', 'Suhu (°C)', 'Kelembaban (%)', 'Cahaya', 'Status LED'])
if 'last_weather_update' not in st.session_state:
    st.session_state.last_weather_update = 0
if 'weather_full_data' not in st.session_state:
    st.session_state.weather_full_data = {"temp": 0, "humidity": 0, "wind_speed": 0, "description": "N/A", "status": "Memuat..."}
if 'ai_prediction' not in st.session_state:
    st.session_state.ai_prediction = "Normal"

# === 3. MQTT CALLBACKS ===
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        mqtt_status_global[0] = True
        client.subscribe(TOPIC_SUB)
    else:
        mqtt_status_global[0] = False

def on_disconnect(client, userdata, rc):
    mqtt_status_global[0] = False

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)
        userdata['queue'].put(data)
    except:
        pass

# --- SINGLETON MQTT CONNECTION ---
@st.cache_resource
def get_mqtt_client():
    client_id = f"plant_monitor_{int(time.time())}"
    client = mqtt.Client(client_id, userdata={'queue': st.session_state.mqtt_queue})
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, 1883, 60)
        client.loop_start()
        return client
    except:
        return None

mqtt_client = get_mqtt_client()

# === 4. LOAD MODEL ML ===
@st.cache_resource
def load_ml_model():
    try:
        return joblib.load(MODEL_FILE)
    except:
        return None

model = load_ml_model()

# === 5. FUNGSI CUACA ===
def update_weather_data(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=id"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            st.session_state.weather_full_data = {
                "temp": data['main']['temp'],
                "humidity": data['main']['humidity'],
                "wind_speed": data['wind']['speed'],
                "description": data['weather'][0]['description'].capitalize(),
                "status": "Sukses"
            }
            st.session_state.last_weather_update = time.time()
    except:
        pass

# === 6. PROSES DATA DARI QUEUE (MAIN THREAD) ===
while not st.session_state.mqtt_queue.empty():
    data = st.session_state.mqtt_queue.get()
    st.session_state.sensor_data = data
    
    if model:
        try:
            pred = model.predict([[data['suhu'], data['cahaya_ldr']]])[0]
            perintah = "LED_ON" if pred == 1 else "LED_OFF"
            ai_res = "Cahaya Kurang" if pred == 1 else "Normal"
        except:
            perintah = "LED_OFF"
            ai_res = "Error Prediksi"
    else:
        perintah = "LED_ON" if data['cahaya_ldr'] < 1000 else "LED_OFF"
        ai_res = "Cahaya Kurang" if data['cahaya_ldr'] < 1000 else "Normal"
        
    if data['suhu'] > 35:
        perintah = "LED_OFF"
        ai_res = "Suhu Tinggi - Pindahkan!"
        
    st.session_state.ai_prediction = ai_res
    
    if mqtt_client and mqtt_status_global[0]:
        mqtt_client.publish(TOPIC_PUB, perintah)

    new_entry = {
        'Waktu': datetime.now().strftime("%H:%M:%S"),
        'Suhu (°C)': data['suhu'],
        'Kelembaban (%)': data['kelembaban'],
        'Cahaya': data['cahaya_ldr'],
        'Status LED': data.get('led_status', 'N/A')
    }
    st.session_state.log_history = pd.concat([pd.DataFrame([new_entry]), st.session_state.log_history], ignore_index=True).head(100)

# === 7. TAMPILAN DASHBOARD ===
st.set_page_config(page_title="Plant Monitoring AI", layout="wide")

if time.time() - st.session_state.last_weather_update > 600:
    update_weather_data(CITY_NAME)

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Info & Kontrol")
    
    # Bagian Status MQTT telah dihapus sesuai permintaan
    
    st.info(f"📍 Lokasi: **{CITY_NAME}**")
    st.markdown("### 🌦️ Cuaca Sekitar")
    w = st.session_state.weather_full_data
    if w["status"] == "Sukses":
        st.write(f"**Kondisi:** {w['description']}")
        st.write(f"**Temp:** {w['temp']} °C | **Hum:** {w['humidity']}%")
    
    st.divider()
    if not st.session_state.log_history.empty:
        csv = st.session_state.log_history.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Unduh Log CSV", data=csv, file_name="plant_log.csv", mime="text/csv")

# --- MAIN UI ---
st.title("🌱 Smart Planting System")
st.markdown(f"Integrasi **Decision Tree AI** & OpenWeatherMap")

pred_ui = st.session_state.ai_prediction
if pred_ui == "Suhu Tinggi - Pindahkan!":
    st.error(f"⚠️ **Rekomendasi AI:** Pindahkan tanaman! Suhu terlalu panas.")
elif pred_ui == "Cahaya Kurang":
    st.warning("⚠️ **Rekomendasi AI:** Cahaya Gelap. Lampu LED telah dinyalakan.")
else:
    st.success("✅ **Status AI:** Kondisi Tanaman Saat Ini Optimal.")

col1, col2, col3, col4 = st.columns(4)
sd = st.session_state.sensor_data
col1.metric("🌡️ Suhu (Lokal)", f"{sd['suhu']} °C")
col2.metric("💧 Hum (Lokal)", f"{sd['kelembaban']} %")
col3.metric("☀️ Cahaya", f"{sd['cahaya_ldr']}")
col4.metric("💡 Status LED", sd['led_status'])

st.divider()
st.subheader("📈 Tren Sensor & 📋 Riwayat")
tab1, tab2 = st.tabs(["Grafik Garis", "Tabel Log"])

with tab1:
    if not st.session_state.log_history.empty:
        chart_data = st.session_state.log_history.set_index('Waktu').sort_index()
        st.line_chart(chart_data[['Suhu (°C)', 'Kelembaban (%)', 'Cahaya']])
with tab2:
    st.dataframe(st.session_state.log_history, width='stretch')

time.sleep(1.5)
st.rerun()