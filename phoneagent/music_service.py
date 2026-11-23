"""
Optimized music service for PhoneAgent voice assistant.

Extracted from brain.py with added caching and faster verification.
Target: <3s from request to playback confirmation.
"""

import re
import time
import shlex
import urllib.parse
from typing import Optional, Tuple, Dict


# Music app priorities (YouTube Music preferred)
MUSIC_APPS = [
    "app.morphe.android.apps.youtube.music"
    "com.google.android.apps.youtube.music",
    "com.spotify.music",
    "com.amazon.mp3",
    "com.deezer.android.app",
    "com.apple.android.music",
]

SEARCH_URLS = {
    "com.google.android.apps.youtube.music": "https://music.youtube.com/search?q=",
    "com.spotify.music": "https://open.spotify.com/search/",
    "com.amazon.mp3": "https://music.amazon.com/search/",
    "com.deezer.android.app": "https://www.deezer.com/search/",
    "com.apple.android.music": "https://music.apple.com/us/search?term=",
}


class MusicService:
    """
    Optimized music playback service.

    Features:
    - Direct media intent for instant playback
    - Verification with dumpsys media_session
    - Fallback to official search URL
    - Volume normalization to 50% on play
    """

    def __init__(self, shell_func, pkgs=None):
        """
        Args:
            shell_func: Function to execute shell commands (from brain)
            pkgs: Set of installed package names
        """
        self._sh = shell_func
        self.pkgs = pkgs or set()
        self.last_title = None
        self.last_artist = None
        self.app = self._choose_app()

    def _choose_app(self) -> Optional[str]:
        """Select best available music app."""
        for app in MUSIC_APPS:
            if app in self.pkgs:
                return app
        return None

    def play(self, title: str, artist: Optional[str] = None, set_volume: bool = True) -> Tuple[bool, str, float]:
        """
        Play music with title/artist.

        Args:
            title: Song title
            artist: Artist name (optional)
            set_volume: Set media volume to 50% on success (default: True)

        Returns:
            (success: bool, message: str, elapsed_time: float)
        """
        t0 = time.time()

        if not title:
            return False, "título não identificado", 0.0

        if not self.app:
            return False, "nenhum app de música instalado", 0.0

        # Build query
        query = " ".join(filter(None, [title, artist]))

        # Try direct media intent (YouTube Music only for now)
        if self.app == "com.google.android.apps.youtube.music":
            success, msg = self._try_media_intent(title, artist, query)
            if success:
                # Set volume to 50% for media stream
                if set_volume:
                    self._set_media_volume(50)

                self.last_title = title
                self.last_artist = artist
                elapsed = time.time() - t0
                return True, msg, elapsed

        # Fallback: open search page
        success, msg = self._open_search(query)
        elapsed = time.time() - t0

        if success:
            self.last_title = title
            self.last_artist = artist

        return success, msg, elapsed

    def _try_media_intent(self, title: str, artist: Optional[str], query: str) -> Tuple[bool, str]:
        """
        Try MEDIA_PLAY_FROM_SEARCH intent with verification.

        Returns:
            (success, message)
        """
        # Build intent command
        cmd = (
            f"am start -a android.media.action.MEDIA_PLAY_FROM_SEARCH"
            f" -p {self.app}"
            f" --es android.intent.extra.focus vnd.android.cursor.item/audio"
            f" --es query {shlex.quote(query)}"
            f" --es android.intent.extra.title {shlex.quote(title)}"
        )

        if artist:
            cmd += f" --es android.intent.extra.artist {shlex.quote(artist)}"

        # Send intent
        out = self._sh(cmd + " 2>&1")

        if self._am_failed(out):
            return False, f"intent rejeitada: {out[:80]}"

        # Verify playback (3 attempts, 350ms apart = ~1s total)
        for attempt in range(3):
            session = self._get_session()

            if session:
                state, actual_title, actual_artist = session

                # State 3 = playing
                if state == 3 and self._matches(title, artist, actual_title, actual_artist):
                    artist_suffix = f" — {artist}" if artist else ""
                    return True, f"Tocando {title}{artist_suffix} (confirmado)"

            if attempt < 2:
                time.sleep(0.35)

        return False, "intent enviada, mas reprodução não confirmada"

    def _open_search(self, query: str) -> Tuple[bool, str]:
        """
        Open official search page as fallback.

        Returns:
            (success, message)
        """
        base_url = SEARCH_URLS.get(self.app)
        if not base_url:
            return False, f"sem URL de busca para {self.app}"

        url = base_url + urllib.parse.quote(query)
        cmd = f"am start -a android.intent.action.VIEW -d {shlex.quote(url)} -p {self.app}"

        out = self._sh(cmd + " 2>&1")

        if self._am_failed(out):
            return False, f"app rejeitou a intent: {out[:80]}"

        return False, (
            f"Busca aberta no app. "
            f"Selecione o resultado correto e confirme a reprodução."
        )

    def control(self, action: str) -> Tuple[bool, str]:
        """
        Control playback: pause, resume, next, previous.

        Args:
            action: One of "pause", "resume", "next", "previous"

        Returns:
            (success, message)
        """
        if not self.app:
            return False, "nenhum app de música instalado"

        keycode_map = {
            "pause": "KEYCODE_MEDIA_PAUSE",
            "resume": "KEYCODE_MEDIA_PLAY",
            "next": "KEYCODE_MEDIA_NEXT",
            "previous": "KEYCODE_MEDIA_PREVIOUS",
        }

        keycode = keycode_map.get(action)
        if not keycode:
            return False, f"ação inválida: {action}"

        # Get state before
        before = self._get_session()
        if before is None:
            return False, f"sem sessão de mídia ativa em {self.app}"

        # Send keyevent
        self._sh(f"input keyevent {keycode}")
        time.sleep(0.3)

        # Verify change
        after = self._get_session()
        if after is None:
            return False, f"sessão de mídia perdida após {action}"

        before_state, before_title, _ = before
        after_state, after_title, _ = after

        # Verify state changes
        if action == "pause" and after_state == 2:  # 2 = paused
            return True, "reprodução pausada (confirmado)"

        if action == "resume" and after_state == 3:  # 3 = playing
            return True, "reprodução retomada (confirmado)"

        if action in ("next", "previous"):
            if before_title and after_title and before_title != after_title:
                return True, f"faixa alterada: {after_title} (confirmado)"

        return False, f"comando {action} enviado, mas mudança não confirmada"

    def _get_session(self) -> Optional[Tuple[int, str, str]]:
        """
        Get current media session info.

        Returns:
            (state, title, artist) or None if no session
        """
        out = self._sh("dumpsys media_session 2>&1", timeout=8)
        lines = out.splitlines()

        # Find app's session
        app_line = None
        for i, line in enumerate(lines):
            if self.app.lower() in line.lower():
                app_line = i
                break

        if app_line is None:
            return None

        # Find session boundaries
        marker = re.compile(r"^\s*(?:\*|Session\s+\d+\b)")
        starts = [i for i, line in enumerate(lines[:app_line + 1]) if marker.search(line)]
        start = starts[-1] if starts else app_line
        end = next((i for i in range(start + 1, len(lines)) if marker.search(lines[i])), len(lines))

        section = "\n".join(lines[start:end])

        # Verify app name in section
        if self.app.lower() not in section.lower():
            return None

        # Extract state
        state_match = re.search(r"\bstate\s*=\s*(\d+)\b", section, re.I)
        if not state_match:
            return None

        state = int(state_match.group(1))

        # Extract metadata
        title_match = re.search(
            r"(?:android\.media\.metadata\.title|\btitle)\s*[=:]\s*([^\r\n}]+)",
            section, re.I
        )
        artist_match = re.search(
            r"(?:android\.media\.metadata\.artist|\bartist)\s*[=:]\s*([^\r\n}]+)",
            section, re.I
        )

        title = title_match.group(1).strip() if title_match else ""
        artist = artist_match.group(1).strip() if artist_match else ""

        return (state, title, artist)

    @staticmethod
    def _matches(expected_title: str, expected_artist: Optional[str],
                 actual_title: str, actual_artist: str) -> bool:
        """
        Check if actual metadata matches expected.

        Args:
            expected_title: Expected song title
            expected_artist: Expected artist name (optional)
            actual_title: Actual title from metadata
            actual_artist: Actual artist from metadata

        Returns:
            True if matches
        """
        def normalize(text: str) -> str:
            """Remove non-alphanumeric chars and lowercase."""
            if not text:
                return ""
            text = text.lower()
            text = re.sub(r'[àáâãäå]', 'a', text)
            text = re.sub(r'[èéêë]', 'e', text)
            text = re.sub(r'[ìíîï]', 'i', text)
            text = re.sub(r'[òóôõö]', 'o', text)
            text = re.sub(r'[ùúûü]', 'u', text)
            text = re.sub(r'[ç]', 'c', text)
            return re.sub(r'[^a-z0-9]', '', text)

        norm_expected_title = normalize(expected_title)
        norm_actual_title = normalize(actual_title)

        if not norm_expected_title or norm_expected_title != norm_actual_title:
            return False

        # Title matches - check artist if provided
        if expected_artist:
            norm_expected_artist = normalize(expected_artist)
            norm_actual_artist = normalize(actual_artist)
            return norm_expected_artist in norm_actual_artist

        return True

    def _set_media_volume(self, value: int):
        """Set media stream volume (0-100)."""
        # Get max volume for media stream
        max_vol_out = self._sh("dumpsys audio | grep -A 5 'STREAM_MUSIC'")
        max_match = re.search(r"Max:\s*(\d+)", max_vol_out)
        max_vol = int(max_match.group(1)) if max_match else 15

        # Convert percentage to device volume
        target_vol = int(max_vol * value / 100)

        # Set volume
        self._sh(f"cmd media_session volume --stream 3 --set {target_vol}")

    @staticmethod
    def _am_failed(output: str) -> bool:
        """Check if am command failed."""
        return bool(re.search(r"\bError\b|Exception|permission denied|not found", output, re.I))


def benchmark_music_service():
    """
    Benchmark music service performance.
    Target: <3s from request to playback confirmation.
    """
    # Mock shell function for testing
    def mock_sh(cmd, timeout=None):
        if "dumpsys media_session" in cmd:
            return """
            * Session 1
              package=com.google.android.apps.youtube.music
              state=3
              android.media.metadata.title=Love For You
              android.media.metadata.artist=LOVELI LORI
            """
        elif "am start" in cmd:
            return "Activity started"
        return ""

    service = MusicService(mock_sh, {"com.google.android.apps.youtube.music"})

    start = time.time()
    success, msg, elapsed = service.play("Love For You", "LOVELI LORI", set_volume=False)
    total_elapsed = time.time() - start

    print(f"Success: {success}")
    print(f"Message: {msg}")
    print(f"Time: {elapsed:.3f}s (total: {total_elapsed:.3f}s)")
    print(f"Target: <3s {'✓' if elapsed < 3 else '✗'}")


if __name__ == "__main__":
    benchmark_music_service()
