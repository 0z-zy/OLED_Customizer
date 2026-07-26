/**
 * OLED Customizer - Content Script
 * Scrapes media info from the page and sends it to the local app.
 */

let lastSentData = null;
const TAB_ID = Math.random().toString(36).substr(2, 9);

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

let lastGoodMetadata = {}; // { videoId: {title, artist} }

function getYouTubeVideoId() {
    const url = new URL(window.location.href);
    if (url.pathname.startsWith('/shorts/')) return url.pathname.split('/')[2];
    return url.searchParams.get('v');
}

function scrapeMediaInfo() {
    // Only real playback pages: homepage/channel/search hover-previews are
    // autoplaying <video>s too, and would hijack the OLED with "YouTube /
    // YouTube Video" garbage (the extension outranks SMTC in the app).
    if (window.location.host.includes('youtube.com')) {
        const p = window.location.pathname;
        if (!p.startsWith('/watch') && !p.startsWith('/shorts') && !p.startsWith('/live')) {
            return null;
        }
    }

    const video = getActiveVideo();
    if (!video) return null;

    const videoId = getYouTubeVideoId() || "unknown_video";
    let title = "";
    let artist = "";

    if (window.location.host.includes('youtube.com')) {
        // 1. Try Specific DOM Selectors (Most accurate when page is loaded)
        let domTitle = "";
        let domArtist = "";

        if (window.location.pathname.startsWith('/shorts/')) {
            const shortTitleEl = document.querySelector('ytd-reel-video-renderer[is-active] h2.title');
            const shortArtistEl = document.querySelector('ytd-reel-video-renderer[is-active] #channel-name a') || 
                                 document.querySelector('ytd-reel-video-renderer[is-active] ytd-channel-name a');
            domTitle = shortTitleEl ? (shortTitleEl.textContent || "").trim() : "";
            domArtist = shortArtistEl ? (shortArtistEl.textContent || "").trim() : "";
        } else {
            const titleEl = document.querySelector('h1.ytd-watch-metadata') || 
                           document.querySelector('yt-formatted-string.ytd-video-primary-info-renderer');
            const artistEl = document.querySelector('#owner-name a') || 
                            document.querySelector('ytd-channel-name #text');
            domTitle = titleEl ? (titleEl.textContent || "").trim() : "";
            domArtist = artistEl ? (artistEl.textContent || "").trim() : "";
        }

        // 2. Try Meta Tags (Backup / Background)
        const metaTitle = document.querySelector('meta[name="title"]') || document.querySelector('meta[property="og:title"]');
        const metaArtist = document.querySelector('meta[name="author"]') || document.querySelector('link[itemprop="name"]');
        
        title = domTitle || (metaTitle ? (metaTitle.content || "").trim() : "");
        artist = domArtist || (metaArtist ? (metaArtist.content || metaArtist.getAttribute('content') || "").trim() : "");

        // 3. Fallbacks
        if (!title || title.length < 2 || title.toLowerCase() === "youtube") {
            title = document.title.replace(" - YouTube", "").trim();
        }
        
        // Remove notification counts like (1) from title
        title = title.replace(/^\(\d+\)\s*/, "");

        if (!artist || artist.length < 2 || artist.toLowerCase() === "youtube video") {
            artist = window.location.host.includes('youtube.com') ? "YouTube Video" : "Unknown Artist";
        }

        // 3. Persistent Memory (Lock in the title if it's currently 'Unknown' but we knew it before)
        if (title && title !== "Unknown Title" && artist && artist !== "Unknown Artist") {
            lastGoodMetadata[videoId] = { title, artist };
        } else if (lastGoodMetadata[videoId]) {
            title = lastGoodMetadata[videoId].title;
            artist = lastGoodMetadata[videoId].artist;
        }
    } else {
        // General Metadata Scraper for other sites
        title = document.title.trim();
        
        // Try to find an artist/author
        const authorMeta = document.querySelector('meta[name="author"]') || 
                          document.querySelector('meta[property="article:author"]') ||
                          document.querySelector('meta[property="og:site_name"]');
        
        artist = authorMeta ? authorMeta.content : "";
        
        if (!artist) {
            // Use hostname as fallback artist
            artist = window.location.hostname.replace('www.', '');
        }

        // Clean up common suffixes
        title = title.replace(/\s*(-|\|)\s*.*$/, '').trim(); 
    }

    return {
        title: title || "Unknown Title",
        artist: artist || "Unknown Artist",
        artwork: window.location.host.includes('youtube.com') 
            ? `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg` 
            : (document.querySelector('meta[property="og:image"]')?.content || ""),
        duration: Number.isFinite(video.duration) ? video.duration : 0,
        progress: Number.isFinite(video.currentTime) ? video.currentTime : 0,
        playing: !video.paused,
        isFocused: document.visibilityState === 'visible',
        source: "YouTube (Extension)",
        tabId: TAB_ID,
        videoId: videoId
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
            chrome.runtime.sendMessage({ action: 'sendMediaData', data: data });
            lastSentData = data;
        } catch (e) {
            // Silently fail if extension context is invalidated
        }
    }
}

// Start polling
setInterval(sendData, 500);

document.addEventListener('play', sendData, true);
document.addEventListener('pause', sendData, true);
document.addEventListener('seeked', sendData, true);
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' || document.visibilityState === 'visible') {
        sendData();
    }
}, true);

window.addEventListener('beforeunload', () => {
    try {
        const data = scrapeMediaInfo();
        if (data) {
            data.playing = false;
            chrome.runtime.sendMessage({ action: 'sendMediaData', data: data });
        }
    } catch (e) {
        // Extension context may already be invalidated during unload
    }
});

console.log("OLED Customizer Extension Active (Multi-Tab Mode)");
