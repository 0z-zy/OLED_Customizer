use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, RwLock,
};
use std::thread;
use std::time::Duration;

use serde::Serialize;

#[derive(Clone, Debug, Default)]
pub struct BroadcastPayload {
    pub playing: bool,
    pub title: String,
    pub artist: String,
    pub album: String,
    pub cover_bytes: Option<Vec<u8>>,
    pub cover_mime: String,
}

#[derive(Serialize)]
struct MediaJson<'a> {
    playing: bool,
    title: &'a str,
    artist: &'a str,
    album: &'a str,
    cover: String,
}

fn encode_base64(bytes: &[u8]) -> String {
    const TBL: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity((bytes.len() + 2) / 3 * 4);
    for chunk in bytes.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = if chunk.len() > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as u32 } else { 0 };
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(TBL[((n >> 18) & 0x3F) as usize] as char);
        out.push(TBL[((n >> 12) & 0x3F) as usize] as char);
        out.push(if chunk.len() > 1 {
            TBL[((n >> 6) & 0x3F) as usize] as char
        } else {
            '='
        });
        out.push(if chunk.len() > 2 {
            TBL[(n & 0x3F) as usize] as char
        } else {
            '='
        });
    }
    out
}

pub struct BroadcastServer {
    stop_flag: Arc<AtomicBool>,
    pub port: u16,
}

impl BroadcastServer {
    pub fn start(port: u16, state: Arc<RwLock<BroadcastPayload>>) -> Option<Self> {
        let addr = format!("127.0.0.1:{}", port);
        let listener = match TcpListener::bind(&addr) {
            Ok(l) => l,
            Err(e) => {
                log::warn!("SMTC Broadcast bind failed on {}: {}", addr, e);
                return None;
            }
        };
        let _ = listener.set_nonblocking(true);
        let stop_flag = Arc::new(AtomicBool::new(false));
        let stop_clone = stop_flag.clone();

        thread::Builder::new()
            .name("SMTC-Broadcast".to_string())
            .spawn(move || {
                log::info!("SMTC Broadcast server listening on http://{}", addr);
                while !stop_clone.load(Ordering::Relaxed) {
                    match listener.accept() {
                        Ok((mut stream, _)) => {
                            let mut buf = [0u8; 1024];
                            let _ = stream.set_read_timeout(Some(Duration::from_millis(200)));
                            if let Ok(n) = stream.read(&mut buf) {
                                let req = String::from_utf8_lossy(&buf[..n]);
                                let mut parts = req
                                    .lines()
                                    .next()
                                    .unwrap_or("")
                                    .split_whitespace();
                                let method = parts.next().unwrap_or("GET");
                                let path = parts.next().unwrap_or("/");

                                if method == "OPTIONS" {
                                    let _ = stream.write_all(
                                        b"HTTP/1.1 204 No Content\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type\r\nContent-Length: 0\r\n\r\n",
                                    );
                                } else if path.starts_with("/cover") {
                                    let guard = state.read().unwrap();
                                    if let Some(ref bytes) = guard.cover_bytes {
                                        let hdr = format!(
                                            "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nAccess-Control-Allow-Origin: *\r\nCache-Control: no-cache, no-store, must-revalidate\r\nContent-Length: {}\r\n\r\n",
                                            guard.cover_mime,
                                            bytes.len()
                                        );
                                        let _ = stream.write_all(hdr.as_bytes());
                                        let _ = stream.write_all(bytes);
                                    } else {
                                        let _ = stream.write_all(
                                            b"HTTP/1.1 404 Not Found\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: 0\r\n\r\n",
                                        );
                                    }
                                } else {
                                    let guard = state.read().unwrap();
                                    let cover = guard
                                        .cover_bytes
                                        .as_deref()
                                        .map(|b| {
                                            format!("data:{};base64,{}", guard.cover_mime, encode_base64(b))
                                        })
                                        .unwrap_or_default();
                                    let json = serde_json::to_string(&MediaJson {
                                        playing: guard.playing,
                                        title: &guard.title,
                                        artist: &guard.artist,
                                        album: &guard.album,
                                        cover,
                                    })
                                    .unwrap_or_else(|_| "{}".to_string());
                                    let resp = format!(
                                        "HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nAccess-Control-Allow-Origin: *\r\nCache-Control: no-cache\r\nContent-Length: {}\r\n\r\n{}",
                                        json.len(),
                                        json
                                    );
                                    let _ = stream.write_all(resp.as_bytes());
                                }
                            }
                        }
                        Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                            thread::sleep(Duration::from_millis(25));
                        }
                        Err(_) => {
                            thread::sleep(Duration::from_millis(50));
                        }
                    }
                }
            })
            .ok()?;

        Some(Self { stop_flag, port })
    }

    pub fn stop(&self) {
        self.stop_flag.store(true, Ordering::Relaxed);
    }
}

impl Drop for BroadcastServer {
    fn drop(&mut self) {
        self.stop();
    }
}
