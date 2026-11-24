use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc::{self, Sender},
    Arc, RwLock,
};
use std::thread;
use std::time::{Duration, Instant};

use windows::Win32::Media::Audio::{
    eCapture, eCommunications, eMultimedia, eRender, Endpoints::IAudioEndpointVolume,
    IMMDeviceEnumerator, MMDeviceEnumerator, DEVICE_STATE_ACTIVE,
};
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_ALL, COINIT_APARTMENTTHREADED,
};

#[derive(Clone, Debug)]
pub struct AudioState {
    pub speaker_vol: u8,
    pub speaker_muted: bool,
    pub mic_muted: Option<bool>,
    pub last_change: Option<Instant>,
    pub has_speaker: bool,
}

impl Default for AudioState {
    fn default() -> Self {
        Self {
            speaker_vol: 50,
            speaker_muted: false,
            mic_muted: None,
            last_change: None,
            has_speaker: false,
        }
    }
}

pub enum AudioCommand {
    ToggleMicMute,
    SetMicMute(bool),
}

pub fn start_audio_poller(
    shared: Arc<RwLock<AudioState>>,
    stop: Arc<AtomicBool>,
) -> Sender<AudioCommand> {
    let (tx, rx) = mpsc::channel::<AudioCommand>();

    thread::Builder::new()
        .name("Audio-Worker".to_string())
        .spawn(move || {
            unsafe {
                let _ = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
            }
            let started = Instant::now();
            let mut last_vol: Option<u8> = None;
            let mut last_spk_mute: Option<bool> = None;
            let mut last_mic_mute: Option<bool> = None;

            while !stop.load(Ordering::Relaxed) {
                let mut toggle_requested = false;
                let mut explicit_mute: Option<bool> = None;
                while let Ok(cmd) = rx.try_recv() {
                    match cmd {
                        AudioCommand::ToggleMicMute => toggle_requested = true,
                        AudioCommand::SetMicMute(m) => explicit_mute = Some(m),
                    }
                }

                unsafe {
                    if let Ok(enumerator) = CoCreateInstance::<_, IMMDeviceEnumerator>(
                        &MMDeviceEnumerator,
                        None,
                        CLSCTX_ALL,
                    ) {
                        if let Some(new_mute) = explicit_mute {
                            if set_all_capture_mics(&enumerator, new_mute) {
                                last_mic_mute = Some(new_mute);
                                if let Ok(mut w) = shared.write() {
                                    w.mic_muted = Some(new_mute);
                                    w.last_change = Some(Instant::now());
                                }
                            }
                        } else if toggle_requested {
                            let new_mute = !last_mic_mute.unwrap_or(false);
                            if set_all_capture_mics(&enumerator, new_mute) {
                                last_mic_mute = Some(new_mute);
                                if let Ok(mut w) = shared.write() {
                                    w.mic_muted = Some(new_mute);
                                    w.last_change = Some(Instant::now());
                                }
                            }
                        }

                        // Poll default speaker
                        let mut cur_vol = last_vol.unwrap_or(0);
                        let mut cur_spk_mute = last_spk_mute.unwrap_or(false);
                        let mut has_spk = false;

                        if let Ok(dev) = enumerator.GetDefaultAudioEndpoint(eRender, eMultimedia) {
                            if let Ok(ep) = dev.Activate::<IAudioEndpointVolume>(CLSCTX_ALL, None) {
                                has_spk = true;
                                if let Ok(v) = ep.GetMasterVolumeLevelScalar() {
                                    cur_vol = (v * 100.0).round().clamp(0.0, 100.0) as u8;
                                }
                                if let Ok(m) = ep.GetMute() {
                                    cur_spk_mute = m.as_bool();
                                }
                            }
                        }

                        // Poll default mic
                        let mut cur_mic_mute = None;
                        for role in [eCommunications, eMultimedia] {
                            if let Ok(dev) = enumerator.GetDefaultAudioEndpoint(eCapture, role) {
                                if let Ok(ep) =
                                    dev.Activate::<IAudioEndpointVolume>(CLSCTX_ALL, None)
                                {
                                    if let Ok(m) = ep.GetMute() {
                                        cur_mic_mute = Some(m.as_bool());
                                        break;
                                    }
                                }
                            }
                        }

                        let changed = (last_vol.is_some() && last_vol != Some(cur_vol))
                            || (last_spk_mute.is_some() && last_spk_mute != Some(cur_spk_mute))
                            || (last_mic_mute.is_some()
                                && cur_mic_mute.is_some()
                                && last_mic_mute != cur_mic_mute);

                        last_vol = Some(cur_vol);
                        last_spk_mute = Some(cur_spk_mute);
                        if cur_mic_mute.is_some() {
                            last_mic_mute = cur_mic_mute;
                        }

                        if let Ok(mut w) = shared.write() {
                            w.speaker_vol = cur_vol;
                            w.speaker_muted = cur_spk_mute;
                            w.mic_muted = cur_mic_mute;
                            w.has_speaker = has_spk;
                            if changed && started.elapsed() > Duration::from_secs(2) {
                                w.last_change = Some(Instant::now());
                            }
                        }
                    }
                }

                thread::sleep(Duration::from_millis(120));
            }

            unsafe {
                CoUninitialize();
            }
        })
        .expect("spawn Audio-Worker");

    tx
}

unsafe fn set_all_capture_mics(enumerator: &IMMDeviceEnumerator, muted: bool) -> bool {
    let mut updated = 0;
    if let Ok(collection) = enumerator.EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE) {
        if let Ok(count) = collection.GetCount() {
            for i in 0..count {
                if let Ok(dev) = collection.Item(i) {
                    if let Ok(ep) = dev.Activate::<IAudioEndpointVolume>(CLSCTX_ALL, None) {
                        if ep.SetMute(muted, std::ptr::null()).is_ok() {
                            updated += 1;
                        }
                    }
                }
            }
        }
    }
    updated > 0
}
