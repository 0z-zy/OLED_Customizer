chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'sendMediaData') {
        const data = message.data;
        const body = JSON.stringify(data);
        const headers = { 'Content-Type': 'application/json' };

        // Send to OLED Customizer (port 1231, as set in config.json discord_local_port)
        fetch('http://127.0.0.1:1231/extension_data', {
            method: 'POST', headers, body
        }).catch(() => { /* app not running, ignore */ });

        // Send to additional app (port 2409)
        fetch('http://127.0.0.1:2409/extension_data', {
            method: 'POST', headers, body
        }).catch(() => { /* app not running, ignore */ });
    }
});
