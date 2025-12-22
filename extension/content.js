/**
 * OLED Customizer - Content Script
 * Scrapes media info from the page and sends it to the local app.
 */

let lastSentData = null;

function scrapeMediaInfo() {
    const video = document.querySelector('video');
    if (!video) return null;

    // Site-specific logic (currently YouTube)
    let title = "";
    let artist = "";

    if (window.location.host.includes('youtube.com')) {
        // YouTube Title - More robust selectors
        const titleEl = document.querySelector('h1.ytd-video-primary-info-renderer yc-video-title') ||
            document.querySelector('ytd-watch-metadata h1') ||
            document.querySelector('.ytp-title-link');
        title = titleEl ? titleEl.innerText : document.title.replace(" - YouTube", "");

        // YouTube Channel (Artist)
        const channelEl = document.querySelector('ytd-video-owner-renderer #channel-name a') ||
            document.querySelector('#upload-info #channel-name a') ||
            document.querySelector('.ytp-ce-channel-title');
        artist = channelEl ? channelEl.innerText : "YouTube Video";
    }

    return {
        title: title || "Unknown Title",
        artist: artist || "Unknown Artist",
        duration: video.duration || 0,
        progress: video.currentTime || 0,
        playing: !video.paused,
        source: "YouTube (Extension)"
    };
}

async function sendData() {
    const data = scrapeMediaInfo();
    if (!data) return;

    // Only send if significant change (e.g., metadata changed or playing state changed)
    // Always send progress every few seconds
    const dataString = JSON.stringify({ ...data, progress: 0 }); // Ignore progress for 'id' comparison
    const lastDataString = lastSentData ? JSON.stringify({ ...lastSentData, progress: 0 }) : "";

    // Send if metadata changed, OR if 2 seconds passed, OR if playing state changed
    const playingChanged = lastSentData ? (data.playing !== lastSentData.playing) : true;

    if (dataString !== lastDataString || !lastSentData || playingChanged || (Math.abs(data.progress - lastSentData.progress) >= 2)) {
        try {
            await fetch('http://127.0.0.1:2408/extension_data', {
                method: 'POST',
                mode: 'no-cors',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            lastSentData = data;
        } catch (e) {
            // Silently fail if app isn't running
        }
    }
}

// Start polling
setInterval(sendData, 500);

// Event Listeners for immediate updates
document.addEventListener('play', sendData, true);
document.addEventListener('pause', sendData, true);
document.addEventListener('seeked', sendData, true);

console.log("OLED Customizer Extension Active (Low Latency Mode)");
