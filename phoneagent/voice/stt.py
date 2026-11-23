"""
Speech-to-Text module using Whisper.cpp for offline transcription.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from .audio import record_audio, cleanup_temp_audio


# Whisper.cpp paths
# Use absolute path for Termux (expanduser doesn't work reliably via su)
WHISPER_BASE = os.environ.get('HOME', '/data/data/com.termux/files/home')
WHISPER_CLI = os.path.join(WHISPER_BASE, "whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL_BASE = os.path.join(WHISPER_BASE, "whisper.cpp/models/ggml-base.bin")
WHISPER_MODEL_TINY = os.path.join(WHISPER_BASE, "whisper.cpp/models/ggml-tiny.bin")
WHISPER_MODEL_SMALL = os.path.join(WHISPER_BASE, "whisper.cpp/models/ggml-small.bin")


def transcribe_audio(audio_file: str, language: str = "pt", model: str = "base") -> str:
    """
    Transcribe audio file to text using Whisper.cpp.

    Args:
        audio_file: Path to audio file (wav, m4a, mp3, etc.)
        language: Language code (default: "pt" for Portuguese)
        model: Model size - "tiny", "base", or "small" (default: "base")

    Returns:
        Transcribed text

    Raises:
        RuntimeError: If transcription fails
    """
    # Select model
    if model == "small":
        model_path = WHISPER_MODEL_SMALL
    elif model == "base":
        model_path = WHISPER_MODEL_BASE
    else:
        model_path = WHISPER_MODEL_TINY

    if not os.path.exists(model_path):
        raise RuntimeError(
            f"Whisper model not found at {model_path}. "
            f"Run setup.sh to download models."
        )

    if not os.path.exists(WHISPER_CLI):
        raise RuntimeError(
            f"Whisper CLI not found at {WHISPER_CLI}. "
            f"Run setup.sh to build whisper.cpp."
        )

    # Convert to WAV if needed (Whisper.cpp requires WAV)
    wav_file = audio_file
    needs_conversion = not audio_file.endswith('.wav')

    if needs_conversion:
        tmpdir = os.environ.get('TMPDIR', '/data/data/com.termux/files/usr/tmp')
        # Generate unique filename based on input file
        import time
        base_name = os.path.splitext(os.path.basename(audio_file))[0]
        wav_file = os.path.join(tmpdir, f'whisper_input_{base_name}_{int(time.time())}.wav')

        try:
            # Convert m4a/mp3 to 16kHz mono WAV for Whisper
            result = subprocess.run([
                'ffmpeg', '-y', '-i', audio_file,
                '-ar', '16000',  # 16kHz sample rate
                '-ac', '1',       # mono
                '-c:a', 'pcm_s16le',  # 16-bit PCM
                wav_file
            ], capture_output=True, text=True, timeout=10)

            if result.returncode != 0 or not os.path.exists(wav_file):
                raise RuntimeError(f"Failed to convert audio: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Audio conversion timed out")

    # Build whisper command
    cmd = [
        WHISPER_CLI,
        '-m', model_path,
        '-l', language,
        '-t', '4',  # 4 threads
        '--no-timestamps',
        '-f', wav_file
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode != 0:
            raise RuntimeError(f"Whisper failed: {result.stderr[-400:]}")

        # Extract transcription from output
        # Whisper outputs format: [timestamp] text
        # We want just the text part
        text = result.stdout.strip()

        # Remove timestamps if present
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if not line or line.startswith('['):
                continue
            # Remove leading timestamp markers like "[00:00:00.000 --> 00:00:05.000]"
            if '-->' in line:
                line = line.split(']', 1)[-1].strip()
            lines.append(line)

        return ' '.join(lines).strip()

    except subprocess.TimeoutExpired:
        raise RuntimeError("Whisper transcription timed out")
    except Exception as e:
        raise RuntimeError(f"Transcription error: {e}")
    finally:
        # Cleanup temporary WAV file
        if needs_conversion and os.path.exists(wav_file):
            try:
                os.remove(wav_file)
            except:
                pass


def start_listening(duration: int = 5, language: str = "pt", model: str = "base") -> Tuple[str, str]:
    """
    Record audio and transcribe in one step.

    Args:
        duration: Recording duration in seconds (default: 5)
        language: Language code (default: "pt")
        model: Whisper model size (default: "base")

    Returns:
        Tuple of (transcribed_text, audio_file_path)

    Raises:
        RuntimeError: If recording or transcription fails
    """
    audio_file = None
    try:
        # Record audio
        audio_file = record_audio(duration=duration)

        # Transcribe
        text = transcribe_audio(audio_file, language=language, model=model)

        return text, audio_file

    except Exception as e:
        # Cleanup on error
        if audio_file:
            cleanup_temp_audio(audio_file)
        raise


def transcribe_from_android_intent() -> Optional[str]:
    """
    Alternative: use Android's built-in speech recognition via intent.
    This requires online connection but is faster and uses Google's STT.

    Returns:
        Transcribed text or None if failed
    """
    try:
        # Use Termux:API speech-to-text
        result = subprocess.run(
            ['termux-speech-to-text'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def get_available_models() -> list:
    """
    Check which Whisper models are available.

    Returns:
        List of available model names
    """
    models_dir = os.path.expanduser("~/whisper.cpp/models")
    available = []

    model_files = {
        'tiny': 'ggml-tiny.bin',
        'base': 'ggml-base.bin',
        'small': 'ggml-small.bin',
        'medium': 'ggml-medium.bin',
    }

    for name, filename in model_files.items():
        if os.path.exists(os.path.join(models_dir, filename)):
            available.append(name)

    return available
