const portInput = document.getElementById('port-input');
const saveBtn = document.getElementById('save-btn');
const savedMsg = document.getElementById('saved-msg');

// null / empty means auto-detect (see CANDIDATE_PORTS in background.js)
chrome.storage.local.get({ port: null }).then(({ port }) => {
    portInput.value = port || '';
});

saveBtn.addEventListener('click', () => {
    const raw = portInput.value.trim();

    if (raw === '') {                       // back to auto-detect
        chrome.storage.local.set({ port: null }).then(() => {
            savedMsg.textContent = 'Auto-detect ✓';
            savedMsg.style.color = '#00ff00';
            setTimeout(() => { savedMsg.textContent = ''; }, 2000);
        });
        return;
    }

    const port = parseInt(raw, 10);
    if (!port || port < 1 || port > 65535) {
        savedMsg.textContent = 'Invalid port';
        savedMsg.style.color = '#e74c3c';
        return;
    }
    chrome.storage.local.set({ port }).then(() => {
        savedMsg.textContent = 'Saved ✓';
        savedMsg.style.color = '#00ff00';
        setTimeout(() => { savedMsg.textContent = ''; }, 2000);
    });
});

document.getElementById('github-btn').addEventListener('click', () => {
    window.open('https://github.com/0z-zy/OLED_Customizer', '_blank');
});
