const DEFAULT_PORT = 8888;

const portInput = document.getElementById('port-input');
const saveBtn = document.getElementById('save-btn');
const savedMsg = document.getElementById('saved-msg');

chrome.storage.local.get({ port: DEFAULT_PORT }).then(({ port }) => {
    portInput.value = port;
});

saveBtn.addEventListener('click', () => {
    const port = parseInt(portInput.value, 10);
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
