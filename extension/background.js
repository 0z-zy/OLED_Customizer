// Ports the OLED Customizer receiver is known to use. 8888 is the current
// app default; 1231 is the legacy value still present in older config.json
// files. The port is auto-detected so the extension works on a fresh install
// AND on an existing setup without the user configuring anything.
const CANDIDATE_PORTS = [8888, 1231, 2409];

// Secondary consumer (e.g. MuteSync) that also wants the same payload.
const EXTRA_PORT = 2409;

// Last port that actually accepted a POST. Cached in memory so we don't
// re-scan on every message; MV3 may evict the worker, which just means the
// next wake-up re-detects.
let activePort = null;

// When nothing answers (app closed) don't re-scan every candidate on every
// media update — the content script fires ~2x/sec, which would mean a steady
// stream of failed fetches. Back off and retry occasionally instead.
const RESCAN_COOLDOWN_MS = 15000;
let nextScanAllowed = 0;

async function post(port, body, headers) {
    const res = await fetch(`http://127.0.0.1:${port}/extension_data`, {
        method: 'POST', headers, body
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return port;
}

async function sendToApp(body, headers) {
    const { port } = await chrome.storage.local.get({ port: null });

    // An explicit port from the popup always wins - no scanning.
    if (port) {
        try { await post(port, body, headers); } catch { /* app not running */ }
        return;
    }

    // Fast path: keep using the port that worked last time.
    if (activePort) {
        try {
            await post(activePort, body, headers);
            return;
        } catch { activePort = null; }      // app moved or closed -> rescan
    }

    if (Date.now() < nextScanAllowed) return;

    for (const candidate of CANDIDATE_PORTS) {
        try {
            activePort = await post(candidate, body, headers);
            return;
        } catch { /* try the next one */ }
    }
    nextScanAllowed = Date.now() + RESCAN_COOLDOWN_MS;   // nothing is listening
}

chrome.runtime.onMessage.addListener((message) => {
    if (message.action !== 'sendMediaData') return;

    const body = JSON.stringify(message.data);
    const headers = { 'Content-Type': 'application/json' };

    sendToApp(body, headers);

    // Fire-and-forget to the secondary app, unless it's already the target.
    if (activePort !== EXTRA_PORT) {
        fetch(`http://127.0.0.1:${EXTRA_PORT}/extension_data`, {
            method: 'POST', headers, body
        }).catch(() => { /* not running, ignore */ });
    }
});
