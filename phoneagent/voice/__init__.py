"""
Voice module for PhoneAgent - Speech-to-Text and Text-to-Speech functionality.

This module provides voice interaction capabilities:
- STT (Speech-to-Text) via Whisper.cpp
- TTS (Text-to-Speech) via Android native TTS
- Audio capture and playback utilities
"""

from .stt import transcribe_audio, start_listening
from .tts import speak, set_voice_config
from .audio import record_audio, play_audio

__all__ = [
    'transcribe_audio',
    'start_listening',
    'speak',
    'set_voice_config',
    'record_audio',
    'play_audio',
]
