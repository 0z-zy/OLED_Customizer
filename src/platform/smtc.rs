use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, RwLock,
};
use std::thread;
use std::time::{Duration, Instant};

use windows::Media::Control::{
    GlobalSystemMediaTransportControlsSessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus,
};
use windows::Storage::Streams::{Buffer, DataReader, InputStreamOptions};
use windows::Win32::System::Com::{CoInitializeEx, CoUninitialize, COINIT_MULTITHREADED};

use crate::oled::views::player::MediaSource;
use crate::services::signalrgb::extract_dominant_colors;

#[derive(Clone, Debug)]
pub struct MediaState {
    pub active: bool,
    pub playing: bool,
    pub title: String,
    pub artist: String,
    pub album: String,
    pub source: Option<MediaSource>,
    pub position_ms: u64,
    pub position_updated_at: Option<Instant>,
    pub playback_rate: f64,
    pub duration_ms: u64,
    pub cover_bytes: Option<Vec<u8>>,
    pub cover_colors: Vec<String>,
}

impl Default for MediaState {
    fn default() -> Self {
        Self {
            active: false,
            playing: false,
            title: String::new(),
            artist: String::new(),
            album: String::new(),
            source: None,
            position_ms: 0,
            position_updated_at: None,
            playback_rate: 1.0,
            duration_ms: 0,
            cover_bytes: None,
            cover_colors: Vec::new(),
        }
    }
}

pub fn start_smtc_poller(shared: Arc<RwLock<MediaState>>, stop: Arc<AtomicBool>) {
    thread::Builder::new()
        .name("SMTC-Poller".to_string())
        .spawn(move || {
            unsafe {
                let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
            }
            let mut manager: Option<GlobalSystemMediaTransportControlsSessionManager> = None;
            let mut last_thumb_key = String::new();
            let mut cached_cover: Option<Vec<u8>> = None;
            let mut cached_colors: Vec<String> = Vec::new();

            while !stop.load(Ordering::Relaxed) {
                if manager.is_none() {
                    if let Ok(op) = GlobalSystemMediaTransportControlsSessionManager::RequestAsync()
                    {
                        if let Ok(m) = op.get() {
                            manager = Some(m);
                        }
                    }
                }

                let mut next_state = MediaState::default();

                if let Some(ref mgr) = manager {
                    if let Ok(sessions) = mgr.GetSessions() {
                        let count = sessions.Size().unwrap_or(0);
                        let mut best_playing = None;
                        let mut best_paused = None;

                        for i in 0..count {
                            let Ok(sess) = sessions.GetAt(i) else {
                                continue;
                            };
                            let Ok(info) = sess.GetPlaybackInfo() else {
                                continue;
                            };
                            let Ok(status) = info.PlaybackStatus() else {
                                continue;
                            };
                            if status == GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing {
                                best_playing = Some(sess);
                                break;
                            } else if status == GlobalSystemMediaTransportControlsSessionPlaybackStatus::Paused && best_paused.is_none() {
                                best_paused = Some(sess);
                            }
                        }

                        let chosen = best_playing.or(best_paused);
                        if let Some(sess) = chosen {
                            if let Ok(info) = sess.GetPlaybackInfo() {
                                let status = info.PlaybackStatus().ok();
                                let playing = status
                                    == Some(
                                        GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing,
                                    );
                                let app_id = sess
                                    .SourceAppUserModelId()
                                    .map(|s| s.to_string_lossy().to_ascii_lowercase())
                                    .unwrap_or_default();
                                let source = if app_id.contains("spotify") {
                                    MediaSource::Spotify
                                } else if app_id.contains("chrome")
                                    || app_id.contains("msedge")
                                    || app_id.contains("firefox")
                                    || app_id.contains("opera")
                                    || app_id.contains("youtube")
                                {
                                    MediaSource::YouTube
                                } else {
                                    MediaSource::Generic
                                };

                                if let Ok(op) = sess.TryGetMediaPropertiesAsync() {
                                    if let Ok(props) = op.get() {
                                        let title = props
                                            .Title()
                                            .map(|s| s.to_string_lossy())
                                            .unwrap_or_default();
                                        let artist = props
                                            .Artist()
                                            .map(|s| s.to_string_lossy())
                                            .unwrap_or_default();
                                        let album = props
                                            .AlbumTitle()
                                            .map(|s| s.to_string_lossy())
                                            .unwrap_or_default();

                                        let mut pos_ms = 0u64;
                                        let mut dur_ms = 1u64;
                                        let rate = info
                                            .PlaybackRate()
                                            .ok()
                                            .and_then(|r| r.Value().ok())
                                            .filter(|r| r.is_finite() && *r > 0.0)
                                            .unwrap_or(1.0)
                                            .clamp(0.25, 4.0);

                                        if let Ok(tl) = sess.GetTimelineProperties() {
                                            if let Ok(end) = tl.EndTime() {
                                                let ms = end.Duration / 10_000;
                                                if ms > 0 {
                                                    dur_ms = ms as u64;
                                                }
                                            }
                                            if dur_ms <= 1 {
                                                if let Ok(mst) = tl.MaxSeekTime() {
                                                    let ms = mst.Duration / 10_000;
                                                    if ms > 0 {
                                                        dur_ms = ms as u64;
                                                    }
                                                }
                                            }
                                            if let Ok(pos) = tl.Position() {
                                                pos_ms = (pos.Duration / 10_000).max(0) as u64;
                                            }
                                            const UNIX_TO_FILETIME_MS: i64 = 11_644_473_600_000;
                                            if playing {
                                                if let Ok(lu) = tl.LastUpdatedTime() {
                                                    let lu_ms = lu.UniversalTime / 10_000;
                                                    let now_ft_ms = chrono::Utc::now()
                                                        .timestamp_millis()
                                                        + UNIX_TO_FILETIME_MS;
                                                    let delta_ms = now_ft_ms - lu_ms;
                                                    if lu_ms > UNIX_TO_FILETIME_MS
                                                        && delta_ms > 0
                                                        && delta_ms < 86_400_000
                                                    {
                                                        let added =
                                                            (delta_ms as f64 * rate).round() as u64;
                                                        pos_ms = pos_ms
                                                            .saturating_add(added)
                                                            .min(dur_ms);
                                                    }
                                                }
                                            }
                                        }

                                        let thumb_key = format!("{}|{}", artist, title);
                                        if thumb_key != last_thumb_key && !title.is_empty() {
                                            last_thumb_key = thumb_key;
                                            cached_cover = read_thumbnail(&props);
                                            cached_colors = cached_cover
                                                .as_deref()
                                                .map(|b| extract_dominant_colors(b, 5))
                                                .unwrap_or_default();
                                        }

                                        if !title.is_empty() {
                                            next_state = MediaState {
                                                active: true,
                                                playing,
                                                title,
                                                artist,
                                                album,
                                                source: Some(source),
                                                position_ms: pos_ms,
                                                position_updated_at: Some(Instant::now()),
                                                playback_rate: rate,
                                                duration_ms: dur_ms,
                                                cover_bytes: cached_cover.clone(),
                                                cover_colors: cached_colors.clone(),
                                            };
                                        }
                                    }
                                }
                            }
                        }
                    } else {
                        manager = None;
                    }
                }

                if let Ok(mut w) = shared.write() {
                    *w = next_state;
                }

                thread::sleep(Duration::from_millis(250));
            }

            unsafe {
                CoUninitialize();
            }
        })
        .expect("spawn SMTC-Poller");
}

fn read_thumbnail(
    props: &windows::Media::Control::GlobalSystemMediaTransportControlsSessionMediaProperties,
) -> Option<Vec<u8>> {
    let thumb_ref = props.Thumbnail().ok()?;
    let stream = thumb_ref.OpenReadAsync().ok()?.get().ok()?;
    let size = stream.Size().ok()? as u32;
    if size == 0 || size > 4 * 1024 * 1024 {
        return None;
    }
    let buf = Buffer::Create(size).ok()?;
    let _ = stream
        .ReadAsync(&buf, size, InputStreamOptions::ReadAhead)
        .ok()?
        .get()
        .ok()?;
    let reader = DataReader::FromBuffer(&buf).ok()?;
    let len = reader.UnconsumedBufferLength().ok()? as usize;
    let mut bytes = vec![0u8; len];
    reader.ReadBytes(&mut bytes).ok()?;
    Some(bytes)
}
