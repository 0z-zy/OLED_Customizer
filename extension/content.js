/**
 * OLED Customizer - Content Script
 * Scrapes media info from the page and sends it to the local app.
 */

let lastSentData = null;

function getActiveVideo() {
    const videos = Array.from(document.querySelectorAll('video'));
    if (videos.length === 0) return null;

    // Filter to videos that are actually playing and have valid duration
    const playingVideos = videos.filter(v => !v.paused && v.duration > 0 && v.offsetHeight > 10);

    if (playingVideos.length === 1) {
        return playingVideos[0];
    }

    // If multiple (or none playing but swiping), find the one most visible on screen
    let bestVideo = null;
    let maxVisibility = -1;

    for (let v of videos) {
        // Skip tiny/hidden videos
        if (v.offsetHeight < 10) continue;

        const rect = v.getBoundingClientRect();
        const visibleHeight = Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0));

        // Prioritize playing videos over paused ones if visibility is similar
        const score = visibleHeight + (!v.paused ? 1000 : 0);

        if (score > maxVisibility) {
            maxVisibility = score;
            bestVideo = v;
        }
    }

    return bestVideo || videos[0];
}

function scrapeMediaInfo() {
    const video = getActiveVideo();
    if (!video) return null;

    // Site-specific logic (currently YouTube)
    let title = "";
    let artist = "";

    if (window.location.host.includes('youtube.com')) {
        if (window.location.pathname.startsWith('/shorts/')) {
            // YouTube Shorts Title & Artist
            const activeReel = document.querySelector('ytd-reel-video-renderer[is-active]');
            if (activeReel) {
                const titleEl = activeReel.querySelector('h2.title yt-formatted-string');
                title = titleEl ? titleEl.innerText : document.title.replace(" - YouTube", "");

                const channelEl = activeReel.querySelector('#channel-name a') || activeReel.querySelector('ytd-channel-name a');
                artist = channelEl ? channelEl.innerText : "YouTube Shorts";
            }
        } else {
            // Normal YouTube Title - More robust selectors
            const titleEl = document.querySelector('h1.ytd-video-primary-info-renderer yc-video-title') ||
                document.querySelector('ytd-watch-metadata h1') ||
                document.querySelector('.ytp-title-link');
            title = titleEl ? titleEl.innerText : document.title.replace(" - YouTube", "");

            // Normal YouTube Channel (Artist)
            const channelEl = document.querySelector('ytd-video-owner-renderer #channel-name a') ||
                document.querySelector('#upload-info #channel-name a') ||
                document.querySelector('.ytp-ce-channel-title');
            artist = channelEl ? channelEl.innerText : "YouTube Video";
        }
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
            await fetch('http://127.0.0.1:8888/extension_data', {
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
