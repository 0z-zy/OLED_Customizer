import asyncio
from datetime import datetime, timezone
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus
import logging

logger = logging.getLogger("OLED Customizer.WindowsMedia")

# Only these statuses mean the session has real, active media
VALID_STATUSES = {
    GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus.PAUSED,
}

class WindowsMedia:
    def __init__(self):
        self.manager = None

    def _is_valid_session(self, session):
        """Check if an SMTC session is real and not stale/garbage.
        Returns False for dead sessions like Discord showing 0:15/0:15."""
        try:
            info = session.get_playback_info()
            if not info:
                return False
            
            status = info.playback_status
            
            # Filter 1: Only trust PLAYING or PAUSED sessions.
            # STOPPED, CLOSED, OPENED, CHANGING are dead/transitional.
            if status not in VALID_STATUSES:
                return False
            
            # Filter 2: Timeline sanity — if position == duration and not playing,
            # the track is finished/stuck (like Discord's 0:15/0:15).
            try:
                timeline = session.get_timeline_properties()
                if timeline and status != GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING:
                    pos = timeline.position
                    end = timeline.end_time
                    # Convert to seconds for comparison
                    pos_s = pos.total_seconds() if hasattr(pos, 'total_seconds') else (pos / 10_000_000 if isinstance(pos, int) else 0)
                    end_s = end.total_seconds() if hasattr(end, 'total_seconds') else (end / 10_000_000 if isinstance(end, int) else 0)
                    if end_s > 0 and abs(pos_s - end_s) < 0.5:
                        # Position is at the end — track is finished, skip it
                        return False
            except Exception as e:
                logger.debug("Timeline check failed: %s", e)  # timeline check is best-effort

            # Filter 3: Staleness — if last update was >60s ago and not playing,
            # the session is stale.
            if status != GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING:
                try:
                    timeline = session.get_timeline_properties()
                    if timeline and hasattr(timeline, 'last_updated_time') and timeline.last_updated_time:
                        age = (datetime.now(timezone.utc) - timeline.last_updated_time).total_seconds()
                        if age > 60:
                            return False
                except Exception as e:
                    logger.debug("Staleness check failed: %s", e)  # staleness check is best-effort

            return True
        except (OSError, RuntimeError):
            return False
        except Exception:
            return False

    async def _ensure_manager(self):
        if self.manager:
            return
        try:
            logger.info("Requesting MediaManager...")
            # Add timeout to prevent hang
            self.manager = await asyncio.wait_for(
                GlobalSystemMediaTransportControlsSessionManager.request_async(),
                timeout=2.0
            )
            logger.info("MediaManager obtained successfully")
        except asyncio.TimeoutError:
            logger.error("MediaManager request TIMED OUT")
        except Exception as e:
            logger.warning(f"Failed to request MediaManager: {e}")

    async def get_media_info(self):
        try:
            await self._ensure_manager()
            if not self.manager:
                return {}
            
            # Try to get ALL sessions and find the one that is actually playing.
            # This fixes the issue where Windows thinks a paused background tab is "current".
            sessions = None
            try:
                sessions = self.manager.get_sessions()
            except (OSError, RuntimeError):
                # COM threading error - manager may be stale
                self.manager = None
                return {}
            except Exception as e:
                logger.debug("Session validation failed: %s", e)

            current_session = None
            
            
            # DEBUG: Log all sessions
            session_list = list(sessions) if sessions else []
            # logger.info(f"SMTC Sessions Found: {len(session_list)}")
            
            # Priority 1: Find a PLAYING session (that passes validation)
            if sessions:
                for session in sessions:
                    try:
                        if not self._is_valid_session(session):
                            continue
                        info = session.get_playback_info()
                        if info and info.playback_status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING:
                            current_session = session
                    except (OSError, RuntimeError):
                        # Skip sessions with COM errors
                        continue
            
            # Priority 2: Fallback — find any valid PAUSED session
            if not current_session and sessions:
                for session in sessions:
                    try:
                        if self._is_valid_session(session):
                            current_session = session
                            break
                    except (OSError, RuntimeError):
                        continue
            
            # Priority 3: Fallback to system "Current" session (also validated)
            if not current_session:
                try:
                    fallback = self.manager.get_current_session()
                    if fallback and self._is_valid_session(fallback):
                        current_session = fallback
                except (OSError, RuntimeError):
                    self.manager = None
                    return {}
            
            # If still nothing, bail
            if not current_session:
                return {}

            # Now proceed with current_session...
            
            info = await current_session.try_get_media_properties_async()
            if not info:
                return {}

            timeline = current_session.get_timeline_properties()

            title = info.title
            artist = info.artist
            
            paused = True
            playback_info = current_session.get_playback_info()
            if playback_info:
                # 4 = Playing, 5 = Paused
                # We can compare against GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
                status = playback_info.playback_status
                if status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING:
                    paused = False
                    
            source = current_session.source_app_user_model_id
            
            # Timeline might be None or zeros
            # We use -1 to indicate "unknown" so we don't force-reset the player to 0.
            position = -1
            duration = 0
            
            if timeline:
                # TimeSpan in winrt is usually total seconds or similar? 
                # Actually winrt.windows.foundation.TimeSpan is usually 100ns ticks.
                # However, pywinrt usually helps convert to timedelta? 
                # Let's assume standard behavior or check properties.
                # timeline.position is a TimeSpan. in pywinrt it might be datetime.timedelta.
                pos_td = timeline.position
                end_td = timeline.end_time
                
                if hasattr(pos_td, "total_seconds"):
                    position = pos_td.total_seconds()
                elif isinstance(pos_td, int):
                    # 1 tick = 100ns. 10,000,000 ticks = 1s.
                    position = pos_td / 10_000_000
                elif hasattr(pos_td, "duration"): 
                     position = pos_td.duration / 10_000_000
                
                # EXTRAPOLATION: SMTC updates position only on state change.
                # We must add (Now - LastUpdatedTime) if playing.
                # datetime already imported at top of file
                
                # Check if we are playing
                is_playing = False
                playback_info = current_session.get_playback_info()
                if playback_info and playback_info.playback_status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING:
                    is_playing = True

                if is_playing and hasattr(timeline, "last_updated_time"):
                     last_updated = timeline.last_updated_time
                     # winrt datetime is usually aware/UTC. 
                     # We need current time in same timezone.
                     # Simplified: If last_updated is recent, difference is added.
                     
                     # Create a simple way to get 'now' compatible with whatever timeline uses
                     # Usually winrt returns a standard python datetime if pywinrt is good.
                     if last_updated:
                         # Ensure we use UTC to match usually
                         now = datetime.now(timezone.utc)
                         diff = (now - last_updated).total_seconds()
                         if diff > 0:
                             position += diff

                if hasattr(end_td, "total_seconds"):
                    duration = end_td.total_seconds()
                elif isinstance(end_td, int):
                    duration = end_td / 10_000_000
                elif hasattr(end_td, "duration"):
                     duration = end_td.duration / 10_000_000
                
                # FALLBACK: If duration is 0, check max_seek_time (common in browsers)
                if duration == 0 and hasattr(timeline, "max_seek_time"):
                    mst = timeline.max_seek_time
                    if hasattr(mst, "total_seconds"):
                         duration = mst.total_seconds()
                    elif isinstance(mst, int):
                         duration = mst / 10_000_000
            
            return {
                "title": title,
                "artist": artist,
                "paused": paused,
                "progress": int(position * 1000) if position != -1 else -1,
                "duration": int(duration * 1000) if duration > 0 else -1,
                "source": (source or "").lower()
            }

        except Exception:
            # If something fails, return empty
            return {}
