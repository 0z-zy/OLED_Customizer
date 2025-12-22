import time
import json
import os
import sys
import psutil
import requests
import math

# --- AYARLAR ---
CORE_PROPS_PATH = "C:\\ProgramData\\SteelSeries\\SteelSeries Engine 3\\coreProps.json"
NOW_PLAYING_FILE = "nowplaying.json"  # Senin YT/Spotify verisinin yazıldığı dosya
APP_NAME = "OLED_CUSTOMIZER_ULTIMATE"

# --- STEELSERIES BAĞLANTI ---
def get_address():
    try:
        with open(CORE_PROPS_PATH, "r") as f:
            data = json.load(f)
            return f"http://{data['address']}"
    except:
        print("SteelSeries Engine bulunamadı!")
        return None

BASE_URL = get_address()

# --- SDK KAYIT VE RENK AYARLARI (RGB + OLED) ---
def register_app():
    if not BASE_URL: return
    
    # Uygulamayı tanıt
    game_metadata = {
        "game": APP_NAME,
        "game_display_name": "Spotify & System Monitor",
        "developer": "User"
    }
    requests.post(f"{BASE_URL}/game_metadata", json=game_metadata)

    # EVENT 1: Şarkı İlerlemesi (F Tuşları için RGB)
    # 0 ile 100 arasında bir değer alır, F1-F12 tuşlarını soldan sağa boyar.
    bind_progress = {
        "game": APP_NAME,
        "event": "SONG_PROGRESS",
        "min_value": 0,
        "max_value": 100,
        "icon_id": 15,
        "handlers": [
            {
                "device-type": "keyboard",
                "zone": "function-keys", # F1, F2... sırası
                "mode": "percent",       # Yüzdeye göre doldur
                "color": {
                    "gradient": {
                        "zero": {"red": 0, "green": 0, "blue": 0},    # Boşken sönük
                        "hundred": {"red": 0, "green": 255, "blue": 0} # Doluyken Yeşil
                    }
                }
            }
        ]
    }
    requests.post(f"{BASE_URL}/bind_game_event", json=bind_progress)

    # EVENT 2: OLED Ekran (Metin Yazdırma)
    bind_oled = {
        "game": APP_NAME,
        "event": "OLED_TEXT",
        "handlers": [{
            "device-type": "screened",
            "mode": "screen",
            "zone": "one",
            "datas": [
                {"lines": [{"has-text": True, "context-frame-key": "first-line"}]},
                {"lines": [{"has-text": True, "context-frame-key": "second-line"}]},
                {"lines": [{"has-text": True, "context-frame-key": "third-line"}]}
            ]
        }]
    }
    requests.post(f"{BASE_URL}/bind_game_event", json=bind_oled)

# --- YARDIMCI: PROGRESS BAR ÇİZİMİ (Metin Olarak) ---
def create_text_bar(percent, length=10):
    filled = int(length * percent / 100)
    bar = "I" * filled + "-" * (length - filled)
    return bar

# --- ANA DÖNGÜ ---
def main():
    print("Ultimate Manager Başlatılıyor... >:D")
    register_app()
    
    last_state = "init"
    
    while True:
        try:
            # 1. Müzik Verisini Oku
            data = None
            if os.path.exists(NOW_PLAYING_FILE):
                try:
                    with open(NOW_PLAYING_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except:
                    pass

            # Veri var mı ve güncel mi? (Pause değilse)
            is_playing = False
            if data:
                # Veri boş değilse ve duraklatılmamışsa
                if data.get("title") and not data.get("paused", True):
                    is_playing = True
            
            # --- DURUM 1: MÜZİK ÇALIYOR ---
            if is_playing:
                title = data.get("title", "")[:18] # Ekrana sığsın diye kırp
                artist = data.get("artist", "")[:18]
                
                # Progress Hesapla
                curr = data.get("progress_ms", 0)
                dur = data.get("duration_ms", 1)
                percent = min(100, max(0, int((curr / dur) * 100)))
                
                # OLED Güncelle
                oled_payload = {
                    "game": APP_NAME,
                    "event": "OLED_TEXT",
                    "data": {
                        "first-line": title,
                        "second-line": artist,
                        "third-line": f"{create_text_bar(percent, 12)} %{percent}"
                    }
                }
                requests.post(f"{BASE_URL}/game_event", json=oled_payload)
                
                # RGB Klavye (F Tuşları) Güncelle
                rgb_payload = {
                    "game": APP_NAME,
                    "event": "SONG_PROGRESS",
                    "data": {"value": percent}
                }
                requests.post(f"{BASE_URL}/game_event", json=rgb_payload)
                
                last_state = "music"

            # --- DURUM 2: SİSTEM MODU (Müzik Yoksa) ---
            else:
                # CPU ve RAM verisi al
                cpu_usage = int(psutil.cpu_percent())
                ram_usage = int(psutil.virtual_memory().percent)
                
                # OLED'e Sistem Bilgisi Bas
                oled_payload = {
                    "game": APP_NAME,
                    "event": "OLED_TEXT",
                    "data": {
                        "first-line": f"CPU: {create_text_bar(cpu_usage, 6)} {cpu_usage}%",
                        "second-line": f"RAM: {create_text_bar(ram_usage, 6)} {ram_usage}%",
                        "third-line": "SYSTEM MONITOR"
                    }
                }
                requests.post(f"{BASE_URL}/game_event", json=oled_payload)
                
                # Klavyedeki F tuşlarını söndür (veya CPU'ya göre yakabilirsin)
                # Şimdilik 0 gönderip söndürüyoruz ki müzik bittiği anlaşılsın.
                rgb_payload = {
                    "game": APP_NAME,
                    "event": "SONG_PROGRESS",
                    "data": {"value": 0} 
                }
                requests.post(f"{BASE_URL}/game_event", json=rgb_payload)
                
                last_state = "system"

            time.sleep(1) # 1 saniyede bir güncelle

        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()