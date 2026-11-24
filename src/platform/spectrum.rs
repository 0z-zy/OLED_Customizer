use std::f32::consts::PI;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, RwLock,
};
use std::thread;
use std::time::Duration;

use windows::Win32::Media::Audio::{
    eMultimedia, eRender, IAudioCaptureClient, IAudioClient, IMMDeviceEnumerator,
    MMDeviceEnumerator, AUDCLNT_BUFFERFLAGS_SILENT, AUDCLNT_SHAREMODE_SHARED,
    AUDCLNT_STREAMFLAGS_LOOPBACK, WAVEFORMATEX,
};
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_ALL,
    COINIT_MULTITHREADED,
};

pub const SPECTRUM_BANDS: usize = 20;
const FFT_SIZE: usize = 512;

pub struct AudioSpectrum {
    active: Arc<AtomicBool>,
    stop_flag: Arc<AtomicBool>,
    bands: Arc<RwLock<[f32; SPECTRUM_BANDS]>>,
    peaks: Arc<RwLock<[f32; SPECTRUM_BANDS]>>,
}

impl AudioSpectrum {
    pub fn start() -> Self {
        let active = Arc::new(AtomicBool::new(false));
        let stop_flag = Arc::new(AtomicBool::new(false));
        let bands = Arc::new(RwLock::new([0.0f32; SPECTRUM_BANDS]));
        let peaks = Arc::new(RwLock::new([0.0f32; SPECTRUM_BANDS]));

        let active_c = active.clone();
        let stop_c = stop_flag.clone();
        let bands_c = bands.clone();
        let peaks_c = peaks.clone();

        thread::Builder::new()
            .name("Audio-Spectrum".to_string())
            .spawn(move || {
                unsafe {
                    let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
                }
                let hann = build_hann_window();

                while !stop_c.load(Ordering::Relaxed) {
                    if !active_c.load(Ordering::Relaxed) {
                        *bands_c.write().unwrap() = [0.0; SPECTRUM_BANDS];
                        *peaks_c.write().unwrap() = [0.0; SPECTRUM_BANDS];
                        thread::sleep(Duration::from_millis(100));
                        continue;
                    }

                    if let Err(e) = run_capture_session(&active_c, &stop_c, &bands_c, &peaks_c, &hann) {
                        log::debug!("AudioSpectrum session ended: {}", e);
                        thread::sleep(Duration::from_millis(300));
                    }
                }

                unsafe {
                    CoUninitialize();
                }
            })
            .ok();

        Self {
            active,
            stop_flag,
            bands,
            peaks,
        }
    }

    pub fn set_active(&self, on: bool) {
        self.active.store(on, Ordering::Relaxed);
    }

    pub fn read(&self) -> ([f32; SPECTRUM_BANDS], [f32; SPECTRUM_BANDS]) {
        let b = *self.bands.read().unwrap();
        let p = *self.peaks.read().unwrap();
        (b, p)
    }

    pub fn stop(&self) {
        self.stop_flag.store(true, Ordering::Relaxed);
        self.active.store(false, Ordering::Relaxed);
    }
}

impl Drop for AudioSpectrum {
    fn drop(&mut self) {
        self.stop();
    }
}

fn run_capture_session(
    active: &AtomicBool,
    stop: &AtomicBool,
    bands_out: &RwLock<[f32; SPECTRUM_BANDS]>,
    peaks_out: &RwLock<[f32; SPECTRUM_BANDS]>,
    hann: &[f32; FFT_SIZE],
) -> Result<(), String> {
    unsafe {
        let enumerator: IMMDeviceEnumerator =
            CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL)
                .map_err(|e| format!("enumerator: {e}"))?;
        let device = enumerator
            .GetDefaultAudioEndpoint(eRender, eMultimedia)
            .map_err(|e| format!("endpoint: {e}"))?;
        let client: IAudioClient = device
            .Activate(CLSCTX_ALL, None)
            .map_err(|e| format!("activate: {e}"))?;

        let fmt_ptr: *mut WAVEFORMATEX = client
            .GetMixFormat()
            .map_err(|e| format!("mixformat: {e}"))?;
        if fmt_ptr.is_null() {
            return Err("null mix format".into());
        }

        let channels = (*fmt_ptr).nChannels.max(1) as usize;
        let sample_rate = (*fmt_ptr).nSamplesPerSec.max(8000) as f32;
        let bits_per_sample = (*fmt_ptr).wBitsPerSample;
        let format_tag = (*fmt_ptr).wFormatTag;

        let init_res = client.Initialize(
            AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_LOOPBACK,
            500_000, // 50ms buffer
            0,
            fmt_ptr,
            None,
        );
        CoTaskMemFree(Some(fmt_ptr as *const std::ffi::c_void));
        init_res.map_err(|e| format!("initialize: {e}"))?;

        let capture: IAudioCaptureClient = client
            .GetService()
            .map_err(|e| format!("capture service: {e}"))?;
        client.Start().map_err(|e| format!("start: {e}"))?;

        let mut ring = [0.0f32; FFT_SIZE];
        let mut ring_pos = 0usize;
        let mut smooth_bands = [0.0f32; SPECTRUM_BANDS];
        let mut peak_caps = [0.0f32; SPECTRUM_BANDS];
        let mut agc_peak = 0.04f32;

        // Precompute logarithmic band bin ranges (~45 Hz to ~14 kHz)
        let bin_hz = sample_rate / FFT_SIZE as f32;
        let band_edges = compute_band_edges(bin_hz);

        while active.load(Ordering::Relaxed) && !stop.load(Ordering::Relaxed) {
            let mut got_audio = false;

            loop {
                let Ok(packet_frames) = capture.GetNextPacketSize() else {
                    let _ = client.Stop();
                    return Err("GetNextPacketSize failed".into());
                };
                if packet_frames == 0 {
                    break;
                }

                let mut data_ptr: *mut u8 = std::ptr::null_mut();
                let mut num_frames = 0u32;
                let mut flags = 0u32;
                if capture
                    .GetBuffer(&mut data_ptr, &mut num_frames, &mut flags, None, None)
                    .is_err()
                {
                    let _ = client.Stop();
                    return Err("GetBuffer failed".into());
                }

                let silent = (flags & (AUDCLNT_BUFFERFLAGS_SILENT.0 as u32)) != 0 || data_ptr.is_null();
                if silent {
                    for _ in 0..num_frames {
                        ring[ring_pos] = 0.0;
                        ring_pos = (ring_pos + 1) % FFT_SIZE;
                    }
                } else {
                    got_audio = true;
                    let is_float = bits_per_sample == 32 && (format_tag == 3 || format_tag == 0xFFFE);
                    if is_float {
                        let samples = std::slice::from_raw_parts(
                            data_ptr as *const f32,
                            (num_frames as usize) * channels,
                        );
                        for frame in samples.chunks_exact(channels) {
                            let mono = frame.iter().copied().sum::<f32>() / channels as f32;
                            ring[ring_pos] = mono;
                            ring_pos = (ring_pos + 1) % FFT_SIZE;
                        }
                    } else if bits_per_sample == 16 {
                        let samples = std::slice::from_raw_parts(
                            data_ptr as *const i16,
                            (num_frames as usize) * channels,
                        );
                        for frame in samples.chunks_exact(channels) {
                            let mono = frame.iter().map(|&s| s as f32 / 32768.0).sum::<f32>()
                                / channels as f32;
                            ring[ring_pos] = mono;
                            ring_pos = (ring_pos + 1) % FFT_SIZE;
                        }
                    }
                }

                let _ = capture.ReleaseBuffer(num_frames);
            }

            // Compute 512-pt FFT
            let mut re = [0.0f32; FFT_SIZE];
            let mut im = [0.0f32; FFT_SIZE];
            for i in 0..FFT_SIZE {
                let s = ring[(ring_pos + i) % FFT_SIZE];
                re[i] = s * hann[i];
            }
            fft_radix2(&mut re, &mut im);

            let mut raw_bands = [0.0f32; SPECTRUM_BANDS];
            let mut frame_max = 0.0f32;
            for (b, &(b0, b1)) in band_edges.iter().enumerate() {
                let mut sum_sq = 0.0f32;
                let mut cnt = 0usize;
                for k in b0..=b1 {
                    let mag = (re[k] * re[k] + im[k] * im[k]).sqrt() / (FFT_SIZE as f32 * 0.5);
                    sum_sq += mag;
                    cnt += 1;
                }
                let avg = if cnt > 0 { sum_sq / cnt as f32 } else { 0.0 };
                // Perceptual high-frequency tilt so mids/highs dance alongside bass
                let tilt = 1.0 + (b as f32) * 0.14;
                let v = (avg * tilt).sqrt();
                raw_bands[b] = v;
                if v > frame_max {
                    frame_max = v;
                }
            }

            // Smooth AGC + noise gate
            if !got_audio || frame_max < 0.008 {
                agc_peak = (agc_peak * 0.99).max(0.04);
                for b in 0..SPECTRUM_BANDS {
                    smooth_bands[b] *= 0.72;
                    peak_caps[b] = (peak_caps[b] - 0.03).max(smooth_bands[b]);
                }
            } else {
                if frame_max > agc_peak {
                    agc_peak = agc_peak * 0.65 + frame_max * 0.35;
                } else {
                    agc_peak = (agc_peak * 0.985).max(0.045);
                }

                for b in 0..SPECTRUM_BANDS {
                    let norm = (raw_bands[b] / agc_peak).clamp(0.0, 1.0);
                    if norm > smooth_bands[b] {
                        smooth_bands[b] = smooth_bands[b] * 0.35 + norm * 0.65;
                    } else {
                        smooth_bands[b] = smooth_bands[b] * 0.76 + norm * 0.24;
                    }
                    if smooth_bands[b] >= peak_caps[b] {
                        peak_caps[b] = smooth_bands[b];
                    } else {
                        peak_caps[b] = (peak_caps[b] - 0.025).max(smooth_bands[b]);
                    }
                }
            }

            *bands_out.write().unwrap() = smooth_bands;
            *peaks_out.write().unwrap() = peak_caps;

            thread::sleep(Duration::from_millis(20));
        }

        let _ = client.Stop();
        Ok(())
    }
}

fn build_hann_window() -> [f32; FFT_SIZE] {
    let mut w = [0.0f32; FFT_SIZE];
    for (i, slot) in w.iter_mut().enumerate() {
        *slot = 0.5 * (1.0 - (2.0 * PI * i as f32 / (FFT_SIZE - 1) as f32).cos());
    }
    w
}

fn compute_band_edges(bin_hz: f32) -> [(usize, usize); SPECTRUM_BANDS] {
    let min_hz = 45.0f32;
    let max_hz = 14_000.0f32;
    let ratio = (max_hz / min_hz).powf(1.0 / SPECTRUM_BANDS as f32);
    let mut edges = [(1usize, 1usize); SPECTRUM_BANDS];
    let max_bin = FFT_SIZE / 2 - 1;

    for (i, slot) in edges.iter_mut().enumerate() {
        let f0 = min_hz * ratio.powi(i as i32);
        let f1 = min_hz * ratio.powi((i + 1) as i32);
        let b0 = ((f0 / bin_hz).floor() as usize).clamp(1, max_bin);
        let b1 = ((f1 / bin_hz).ceil() as usize).clamp(b0, max_bin);
        *slot = (b0, b1);
    }
    edges
}

/// Zero-dependency in-place 512-point radix-2 Cooley-Tukey FFT.
fn fft_radix2(re: &mut [f32; FFT_SIZE], im: &mut [f32; FFT_SIZE]) {
    let n = FFT_SIZE;
    let mut j = 0usize;
    for i in 1..n {
        let mut bit = n >> 1;
        while (j & bit) != 0 {
            j ^= bit;
            bit >>= 1;
        }
        j ^= bit;
        if i < j {
            re.swap(i, j);
            im.swap(i, j);
        }
    }

    let mut len = 2usize;
    while len <= n {
        let half = len >> 1;
        let ang = -2.0 * PI / len as f32;
        let wlen_r = ang.cos();
        let wlen_i = ang.sin();
        let mut i = 0usize;
        while i < n {
            let mut wr = 1.0f32;
            let mut wi = 0.0f32;
            for k in 0..half {
                let u_r = re[i + k];
                let u_i = im[i + k];
                let v_r = re[i + k + half] * wr - im[i + k + half] * wi;
                let v_i = re[i + k + half] * wi + im[i + k + half] * wr;
                re[i + k] = u_r + v_r;
                im[i + k] = u_i + v_i;
                re[i + k + half] = u_r - v_r;
                im[i + k + half] = u_i - v_i;
                let next_wr = wr * wlen_r - wi * wlen_i;
                wi = wr * wlen_i + wi * wlen_r;
                wr = next_wr;
            }
            i += len;
        }
        len <<= 1;
    }
}
