const DEFAULT_PORT = 8888; // Must match "discord_local_port" in the app's config.json
const EXTRA_PORT = 2409;   // Secondary consumer (e.g. MuteSync)

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'sendMediaData') {
        const body = JSON.stringify(message.data);
        const headers = { 'Content-Type': 'application/json' };

        chrome.storage.local.get({ port: DEFAULT_PORT }).then(({ port }) => {
            const target = parseInt(port, 10) || DEFAULT_PORT;

            fetch(`http://127.0.0.1:${target}/extension_data`, {
                method: 'POST', headers, body
            }).catch(() => { /* app not running, ignore */ });

            if (target !== EXTRA_PORT) {
                fetch(`http://127.0.0.1:${EXTRA_PORT}/extension_data`, {
                    method: 'POST', headers, body
                }).catch(() => { /* app not running, ignore */ });
            }
        });
    }
});
