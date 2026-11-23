"""
Audio capture and playback utilities for PhoneAgent voice interface.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional


def record_audio(duration: int = 5, output_file: Optional[str] = None) -> str:
    """
    Record audio from microphone using Termux API.

    Args:
        duration: Recording duration in seconds (default: 5)
        output_file: Output file path (default: temp file)

    Returns:
        Path to recorded audio file (m4a format from Termux)

    Raises:
        RuntimeError: If recording fails
    """
    if output_file is None:
        # Use Termux TMPDIR, not /tmp (doesn't exist on Termux)
        tmpdir = os.environ.get('TMPDIR', '/data/data/com.termux/files/usr/tmp')
        output_file = os.path.join(tmpdir, f'phoneagent_audio_{int(time.time())}.m4a')

    # Try termux-microphone-record first (outputs m4a format)
    try:
        cmd = [
            'termux-microphone-record',
            '-f', output_file,
            '-l', str(duration)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 5)

        # termux-microphone-record returns immediately, wait for recording to complete
        # Add extra time for file to be fully written
        time.sleep(duration + 1.0)

        # Force finalization of recording
        subprocess.run(['termux-microphone-record', '-q'], capture_output=True, timeout=5)
        time.sleep(0.5)

        if result.returncode == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            return output_file
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        pass

    # Fallback: use ffmpeg with audio input
    try:
        # On Android with Termux, use opensles or audiorecord
        cmd = [
            'ffmpeg',
            '-f', 'android_camera',  # or 'opensles' depending on setup
            '-i', '0:0',  # audio device
            '-t', str(duration),
            '-acodec', 'pcm_s16le',
            '-ar', '16000',  # 16kHz for Whisper
            '-ac', '1',  # mono
            output_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 5)

        if result.returncode == 0 and os.path.exists(output_file):
            return output_file
    except Exception as e:
        pass

    raise RuntimeError(
        f"Failed to record audio. Make sure Termux:API is installed and "
        f"RECORD_AUDIO permission is granted."
    )


def play_audio(audio_file: str) -> bool:
    """
    Play audio file using available player.

    Args:
        audio_file: Path to audio file

    Returns:
        True if playback started successfully
    """
    if not os.path.exists(audio_file):
        return False

    # Try termux-media-player
    try:
        result = subprocess.run(
            ['termux-media-player', 'play', audio_file],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    # Fallback: ffplay (from ffmpeg)
    try:
        subprocess.Popen(
            ['ffplay', '-nodisp', '-autoexit', audio_file],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        pass

    return False


def get_audio_duration(audio_file: str) -> float:
    """
    Get duration of audio file in seconds.

    Args:
        audio_file: Path to audio file

    Returns:
        Duration in seconds, or 0.0 if unable to determine
    """
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_file
            ],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass

    return 0.0


def cleanup_temp_audio(audio_file: str) -> None:
    """
    Remove temporary audio file.

    Args:
        audio_file: Path to audio file to remove
    """
    try:
        if os.path.exists(audio_file) and 'phoneagent_audio_' in audio_file:
            os.remove(audio_file)
    except Exception:
        pass
