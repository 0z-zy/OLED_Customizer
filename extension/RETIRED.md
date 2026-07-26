# Browser Sync extension — RETIRED as of v1.7.0

Not shipped with releases any more and not referenced from the README.
The source is kept here so it can be revived without starting over.

## Why it was retired

It worked (requests returned HTTP 200) but was never reliable enough to be
worth the support burden:

- The app port had to match `discord_local_port` in `config.json`. v1.5.0 added
  auto-detection across `[8888, 1231, 2409]`, but that is still a guess.
- MV3 evicts the service worker, so the detected port is re-scanned on every
  wake-up.
- Only `https://www.youtube.com/*` is matched — `music.youtube.com` never
  worked, and the "other sites" branch in `content.js` is unreachable.
- Brave/Chrome localhost policies can block the fetches outright, with no
  visible error for the user.

Windows SMTC (`src/WindowsMedia.py`) already covers browser media, so the
extension only ever added more precise progress/metadata for YouTube.

## State when retired (v1.5.0 of the extension)

Everything here is working and fixed as of retirement:

- port auto-detection with a 15s backoff when nothing answers
- `scripting` and `tabs` permissions dropped (only `storage` remains, so no
  "read your browsing history" warning)
- homepage hover-preview videos no longer hijack the display
- `Infinity` duration on live streams is coerced to 0
- `beforeunload` send is wrapped against an invalidated extension context

## Reviving it

1. Load `extension/` unpacked, or pack it:
   `powershell -File build.ps1` (packing was removed — re-add the CRX step)
2. The app side needs no changes: `src/ExtensionReceiver.py` still listens on
   `POST /extension_data`.

> **Note:** do NOT delete `ExtensionReceiver.py`. The same HTTP server handles
> the Discord OAuth callback (`GET /?code=...`), so removing it breaks Discord
> authorization.
