# 🎹 OLED Customizer
**The ultimate music and system dashboard for your SteelSeries Keyboard.**

OLED Customizer transforms your keyboard's small screen into a powerful, high-contrast information hub. Whether it's tracking your rhythm on Spotify/YouTube or monitoring your PC's vitals during a gaming session, OLED Customizer does it with style and zero flicker.

---

## 🚀 Key Highlights

### 🎵 Dynamic Media Dashboard
*   **Spotify & YouTube Support**: Real-time integration with Spotify (via API) and Browser media (via SMTC).
*   **Intelligent Switching**: Seamlessly transitions between music info and the clock.
*   **Pixel-Perfect Icons**: Custom YouTube and Media icons designed specifically for the 128x40 display.

![Player Demo](content/demos/demo_player.gif)

### 🌡️ Ghost-Monitor (Hardware Stats)
*   **Instant Peek**: Tap **INS (Insert)** to summon your system stats over any screen.
*   **Thermal Guard**: High-accuracy monitoring for CPU & GPU (Usage & Temps).
*   **Memory Tracking**: See exactly how much RAM you have left at a glance.
*   **Custom Art**: Unique 12x12 pixel art icons for a premium look.

![HW Monitor Demo](content/demos/demo_hw_monitor.gif)

### 🔊 Reimagined Volume Control
*   **Adaptive Icons**: Visual feedback changes with your volume level.
*   **Discord Sync**: A microphone icon appears automatically when you're in Discord.
*   **Global Mute**: Press **PAUSE** to mute your system mic and see the status update instantly on your OLED.

![Volume Demo](content/demos/demo_volume.gif)

### 🌐 Browser Sync (Optional)
*   **Precision Timeline**: Bypass Windows SMTC limitations with our dedicated browser extension.
*   **Enhanced Metadata**: Scrapes accurate YouTube titles and durations for a seamless display.
*   **Zero-Config**: Just install the extension and it automatically talks to the OLED Customizer app.

![Browser Sync](content/assets/icons/youtube-18.png)

---

## 🛠️ Quick Setup

### 1. Requirements
*   **SteelSeries GG**: Ensure Engine 3 or GG is running.
*   **Python 3.10+**: Only needed if you are running from source.
*   **Admin Access**: Required for hardware sensor readings.

### 2. Getting Started
1. Download the latest **`Launcher.exe`**.
2. Run the application (it will sit quietly in your System Tray).
3. **Right-Click the Tray Icon** to access settings.
4. Go to the **Spotify** tab to link your account.

---

## 🎵 Spotify API Setup
To sync with Spotify, you need to create a "key" on the Spotify Developer portal.

### Step 1: Create Your App
1. Visit the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Click **"Create app"**.
3. Use these settings:
    - **Redirect URIs**: `http://127.0.0.1:2408/callback`
    - **API/SDK**: Select **"Web API"**.

### Step 2: Configure Credentials
1. In your Spotify App settings, copy the **Client ID** and **Client Secret**.
2. In the **OLED Customizer Settings GUI**:
    - Paste your **Client ID** and **Client Secret**.
    - Set the **Redirect URI** to `http://127.0.0.1:2408/callback`.
    - Set the **Port** to `2408`.
3. Click **SAVE** and restart the app.

---

## 🌐 Browser Sync Installation
To get high-precision data from YouTube and other web players:
1. Open your browser's **Extensions** page (e.g., `chrome://extensions`).
2. Enable **Developer mode**.
3. Click **Load unpacked** and select the `extension` folder from this repo.


---

## 🎨 Advanced Customization
The app is built for those who like to tweak. Access `%APPDATA%/OLED Customizer/config.json` or use the **Settings GUI** to adjust:
- **Clock Designs**: Analog, Big Timer, Date Focused, and more.
- **Scrollbar Margin (px)**: Adjusts the horizontal width and padding of the music progress bar.
- **Text Indentation (px)**: Controls the starting position of song titles to ensure they don't overlap the app icons.
- **Sync**: Match your OLED behavior with your keyboard's RGB profile.

![Clock Demo](content/demos/demo_clock.gif)

---

## 📚 Acknowledgments
OLED Customizer is a highly evolved rebrand, inspired by the foundations of [SteelSeries-Spotify-Linker](https://github.com/0z-zy/OLED_Customizer).

- **Backend Logic**: Based on GameSense™ SDK.
- **Sensors**: Powered by LibreHardwareMonitor.
- **Browser Integration**: Custom WebExtension for precision syncing.
- **Icons**: Hand-crafted for OLED Customizer.

---

**Crafted for enthusiasts. Rebranded and Enhanced by [0z-zy](https://github.com/0z-zy).**
