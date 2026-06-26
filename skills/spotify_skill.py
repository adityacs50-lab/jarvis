"""Spotify control skill using Spotipy (Spotify Web API).

Exposes simple methods that each return a short, speakable status string.
All Spotify errors (no active device, auth, network) are caught and turned
into a spoken explanation rather than a crash.
"""
import logging

import config

log = logging.getLogger("jarvis.spotify")

SCOPE = "user-read-playback-state user-modify-playback-state"

# Tool schema given to Claude for music intent + parameter extraction.
MUSIC_CONTROL_TOOL = {
    "name": "music_control",
    "description": (
        "Control Spotify music playback. Use this whenever the user wants to "
        "play music, pause, resume, skip tracks, change the volume, or ask "
        "what is currently playing. Do NOT use it for general conversation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "play",
                    "pause",
                    "resume",
                    "next",
                    "previous",
                    "set_volume",
                    "now_playing",
                ],
                "description": "The playback action to perform.",
            },
            "query": {
                "type": "string",
                "description": (
                    "For 'play': what to play — a song, artist, and/or album, "
                    "e.g. 'Bohemian Rhapsody', 'Arctic Monkeys', "
                    "'Abbey Road by The Beatles'. Omit for other actions."
                ),
            },
            "volume_level": {
                "type": "integer",
                "description": (
                    "For 'set_volume': target volume 0-100. If the user says "
                    "'louder'/'quieter' without a number, omit this and the "
                    "skill adjusts relative to the current volume."
                ),
            },
            "volume_direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": (
                    "For 'set_volume' when no explicit level is given: whether "
                    "to raise or lower the volume."
                ),
            },
        },
        "required": ["action"],
    },
}


class SpotifySkill:
    def __init__(self):
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        missing = [
            name
            for name, val in (
                ("SPOTIPY_CLIENT_ID", config.SPOTIPY_CLIENT_ID),
                ("SPOTIPY_CLIENT_SECRET", config.SPOTIPY_CLIENT_SECRET),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                "Spotify is not configured. Missing: " + ", ".join(missing)
            )

        auth = SpotifyOAuth(
            client_id=config.SPOTIPY_CLIENT_ID,
            client_secret=config.SPOTIPY_CLIENT_SECRET,
            redirect_uri=config.SPOTIPY_REDIRECT_URI,
            scope=SCOPE,
            cache_path=config.SPOTIPY_CACHE_PATH,
            open_browser=True,
        )
        self.sp = spotipy.Spotify(auth_manager=auth)
        log.info("Spotify skill initialized.")

    # -- dispatch ----------------------------------------------------------
    def handle(self, tool_input):
        """Route a music_control tool call to the right method.

        Returns a short spoken-status string. Never raises.
        """
        action = tool_input.get("action")
        try:
            if action == "play":
                return self.play(tool_input.get("query"))
            if action == "pause":
                return self.pause()
            if action == "resume":
                return self.resume()
            if action == "next":
                return self.next_track()
            if action == "previous":
                return self.previous_track()
            if action == "set_volume":
                return self.set_volume(
                    tool_input.get("volume_level"),
                    tool_input.get("volume_direction"),
                )
            if action == "now_playing":
                return self.now_playing()
            return "I'm not sure how to do that with Spotify."
        except Exception as e:  # pragma: no cover - graceful catch-all
            return self._explain_error(e)

    # -- actions -----------------------------------------------------------
    def play(self, query):
        if not query:
            # No query: just resume whatever was loaded.
            return self.resume()

        results = self.sp.search(q=query, type="track", limit=1)
        items = results.get("tracks", {}).get("items", [])
        if not items:
            return f"I couldn't find anything for {query} on Spotify."

        track = items[0]
        uri = track["uri"]
        device_id = self._active_device_id()
        self.sp.start_playback(device_id=device_id, uris=[uri])
        name = track["name"]
        artist = track["artists"][0]["name"] if track["artists"] else ""
        return f"Playing {name}" + (f" by {artist}." if artist else ".")

    def pause(self):
        self.sp.pause_playback(device_id=self._active_device_id())
        return "Paused."

    def resume(self):
        self.sp.start_playback(device_id=self._active_device_id())
        return "Resuming playback."

    def next_track(self):
        self.sp.next_track(device_id=self._active_device_id())
        return "Skipping to the next track."

    def previous_track(self):
        self.sp.previous_track(device_id=self._active_device_id())
        return "Going back to the previous track."

    def set_volume(self, level, direction=None):
        if level is None:
            # Relative adjustment based on current volume.
            current = self._current_volume()
            step = 15 if direction != "down" else -15
            level = max(0, min(100, current + step))
        level = max(0, min(100, int(level)))
        self.sp.volume(level, device_id=self._active_device_id())
        return f"Volume set to {level} percent."

    def now_playing(self):
        current = self.sp.current_playback()
        if not current or not current.get("item"):
            return "Nothing is playing right now."
        item = current["item"]
        name = item["name"]
        artist = item["artists"][0]["name"] if item["artists"] else "someone"
        state = "Playing" if current.get("is_playing") else "Paused"
        return f"{state}: {name} by {artist}."

    # -- helpers -----------------------------------------------------------
    def _active_device_id(self):
        """Return an active device id, raising a friendly error if none."""
        devices = self.sp.devices().get("devices", [])
        if not devices:
            raise NoActiveDeviceError()
        for d in devices:
            if d.get("is_active"):
                return d["id"]
        # No active device but one exists — use the first one.
        return devices[0]["id"]

    def _current_volume(self):
        current = self.sp.current_playback()
        if current and current.get("device"):
            return current["device"].get("volume_percent", 50)
        return 50

    def _explain_error(self, e):
        import spotipy

        if isinstance(e, NoActiveDeviceError):
            return (
                "I don't see an active Spotify device. Open Spotify on your "
                "phone or computer and start playing something, then try again."
            )
        if isinstance(e, spotipy.SpotifyException):
            if e.http_status == 404:
                return (
                    "I couldn't find an active Spotify device. Make sure "
                    "Spotify is open and playing somewhere."
                )
            if e.http_status in (401, 403):
                return (
                    "Spotify denied that request. This usually needs a Premium "
                    "account, or I may need to be re-authorized."
                )
            log.warning("Spotify error: %s", e)
            return "Sorry, Spotify gave me an error on that one."
        log.warning("Unexpected Spotify error: %s", e)
        return "Something went wrong talking to Spotify."


class NoActiveDeviceError(Exception):
    """Raised when there is no Spotify device to control."""
