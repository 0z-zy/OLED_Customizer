# 🎹 OLED Customizer

**The ultimate music and system dashboard for your SteelSeries Keyboard.**

![Version](https://img.shields.io/badge/version-1.2.15-blue?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey?style=for-the-badge)

OLED Customizer transforms your keyboard's small screen into a powerful, high-contrast information hub. Whether it's tracking your rhythm on Spotify/YouTube or monitoring your PC's vitals during a gaming session, OLED Customizer does it with style and zero flicker.

---

## � Table of Contents
- [�🚀 Key Highlights](#-key-highlights)
- [🛠️ Quick Setup](#️-quick-setup)
- [🎵 Spotify API Setup](#-spotify-api-setup)
- [🌐 Browser Sync](#-browser-sync-installation)
- [🎨 Advanced Customization](#-advanced-customization)
- [📚 Acknowledgments](#-acknowledgments)

---

## 🚀 Key Highlights

### 🎵 Dynamic Media Dashboard
*   **Spotify & YouTube Support**: Real-time integration with Spotify (via API) and Browser media (via SMTC).
*   **Intelligent Switching**: Seamlessly transitions between music info and the clock.
*   **Pixel-Perfect Icons**: Custom YouTube and Media icons designed specifically for the 128x40 display.

````carousel
![Spotify Player](content/demos/demo_player.gif)
<!-- slide -->
![YouTube Player](content/demos/demo_player_youtube.gif)
<!-- slide -->
![System Media](content/demos/demo_player_generic.gif)
````

### 🌡️ Ghost-Monitor (Hardware Stats)
*   **Instant Peek**: Tap **INS (Insert)** to summon your system stats over any screen.
*   **Thermal Guard**: High-accuracy monitoring for CPU & GPU (Usage & Temps).
*   **Memory Tracking**: See exactly how much RAM you have left at a glance.
*   **Custom Art**: Unique 12x12 pixel art icons for a premium look.

![HW Monitor Demo](content/demos/demo_hw_monitor.gif)

### 🔊 Reimagined Volume Control
*   **Adaptive Icons**: Visual feedback changes with your volume level.
*   **Discord Sync**: A microphone icon appears automatically when you're in Discord.
*   **Global Mute**: Press **PAUSE** to mute your system mic and see status update instantly.

![Volume Demo](content/demos/demo_volume.gif)

---

## 🛠️ Quick Setup

> [!IMPORTANT]
> **Admin Access Required**: The application must be run as Administrator to read hardware sensors (CPU/GPU temperatures).

### 1. Requirements
*   **SteelSeries GG**: Ensure Engine 3 or GG is running.
*   **Windows 10/11**: Fully optimized for modern Windows environments.
*   **Spotify Account**: Only needed if you want Spotify-specific features.

### 2. Getting Started
1. Download the latest **`OLED-Customizer.exe`** from [Releases](https://github.com/0z-zy/OLED_Customizer/releases).
2. Run the application (it will sit quietly in your System Tray).
3. **Right-Click the Tray Icon** to access settings.

---

## 🎵 Spotify API Setup

To sync with Spotify, you need to create a free application on the Spotify Developer portal.

> [!TIP]
> This only takes 2 minutes and is much more stable than standard Windows media detection.

### Step 1: Create Your App
1. Visit the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Click **"Create app"** and use these settings:
    - **Redirect URIs**: `http://127.0.0.1:2408/callback`
    - **API/SDK**: Select **"Web API"**.

### Step 2: Configure Credentials
1. Copy your **Client ID** and **Client Secret**.
2. In the **OLED Customizer Settings**:
    - Enable **"Spotify Integration"**.
    - Paste your credentials and set the port to `2408`.
3. Click **SAVE** and restart the app.

---

## 🌐 Browser Sync Installation

To get high-precision data from YouTube and other web players:

1. Open your browser's **Extensions** page.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select the `extension` folder from this repo.

> [!NOTE]
> Browser Sync bypasses Windows SMTC limitations, providing accurate progress bars for YouTube videos.

---

## 🎨 Advanced Customization

Access `%APPDATA%/OLED Customizer/config.json` or use the **Settings GUI** to adjust:

- **Clock Designs**: Analog, Big Timer, Date Focused, and more.
- **Scrollbar Margin**: Adjusts the horizontal width and padding.
- **Text Indentation**: Shifts titles to avoid overlapping app icons.

### 🕰️ Clock Gallery

| Style | Preview |
| :--- | :--- |
| **Standard** | ![Standard](content/demos/demo_clock.gif) |
| **Analog** | ![Analog](content/demos/demo_clock_analog.gif) |
| **Big Timer** | ![Big](content/demos/demo_clock_big.gif) |
| **Date Focused** | ![Date](content/demos/demo_clock_date.gif) |

---

## 📚 Acknowledgments

OLED Customizer is a highly evolved rebrand, inspired by the foundations of [SteelSeries-Spotify-Linker](https://github.com/0z-zy/OLED_Customizer).

- **Backend**: GameSense™ SDK
- **Sensors**: LibreHardwareMonitor
- **UI**: Hand-crafted 128x40 iconography

---

**Crafted for enthusiasts. Rebranded and Enhanced by [0z-zy](https://github.com/0z-zy).**

