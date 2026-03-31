chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'sendMediaData') {
        const data = message.data;
        fetch('http://127.0.0.1:1231/extension_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).catch(e => {
            // Silently fail if app isn't running
        });
    }
});
