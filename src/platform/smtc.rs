use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, RwLock,
};
use std::thread;
use std::time::Duration;

use windows::Media::Control::{
    GlobalSystemMediaTransportControlsSessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus,
};
use windows::Storage::Streams::{Buffer, DataReader, InputStreamOptions};
use windows::Win32::System::Com::{CoInitializeEx, CoUninitialize, COINIT_MULTITHREADED};

use crate::oled::views::player::MediaSource;
use crate::services::signalrgb::extract_dominant_colors;

#[derive(Clone, Debug, Default)]
pub struct MediaState {
    pub active: bool,
    pub playing: bool,
    pub title: String,
    pub artist: String,
    pub album: String,
    pub source: Option<MediaSource>,
    pub position_ms: u64,
    pub duration_ms: u64,
    pub cover_bytes: Option<Vec<u8>>,
    pub cover_colors: Vec<String>,
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
                                        if let Ok(tl) = sess.GetTimelineProperties() {
                                            if let Ok(pos) = tl.Position() {
                                                pos_ms = (pos.Duration / 10_000).max(0) as u64;
                                            }
                                            if let Ok(end) = tl.EndTime() {
                                                dur_ms = ((end.Duration / 10_000).max(1)) as u64;
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
