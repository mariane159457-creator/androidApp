"""
Text-to-Speech module using Android native TTS.
"""

import os
import subprocess
import time
from typing import Optional


# TTS configuration
_tts_config = {
    'engine': 'android',  # 'android' or 'pyttsx3'
    'speed': 1.0,
    'pitch': 1.0,
    'language': 'pt-BR',
    'volume': 0.8,
}


def speak(text: str, wait: bool = True) -> bool:
    """
    Speak text using Text-to-Speech.

    Args:
        text: Text to speak
        wait: Wait for speech to finish (default: True)

    Returns:
        True if speech started successfully
    """
    if not text or not text.strip():
        return False

    engine = _tts_config['engine']

    # Try Android TTS first (preferred)
    if engine == 'android' or engine == 'termux':
        success = _speak_android(text, wait)
        if success:
            return True

    # Fallback to pyttsx3
    if engine == 'pyttsx3' or not success:
        return _speak_pyttsx3(text)

    return False


def _speak_android(text: str, wait: bool = True) -> bool:
    """
    Speak using Android TTS via Termux:API.

    Args:
        text: Text to speak
        wait: Wait for speech to finish

    Returns:
        True if successful
    """
    try:
        # Method 1: termux-tts-speak (preferred)
        cmd = ['termux-tts-speak']

        # Add language
        lang = _tts_config.get('language', 'pt-BR')
        cmd.extend(['-l', lang])

        # Add speed (0.1 to 2.0)
        speed = _tts_config.get('speed', 1.0)
        if speed != 1.0:
            cmd.extend(['-r', str(speed)])

        # Add pitch (0.1 to 2.0)
        pitch = _tts_config.get('pitch', 1.0)
        if pitch != 1.0:
            cmd.extend(['-p', str(pitch)])

        # Add text
        cmd.append(text)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            if wait:
                # Estimate speech duration (rough: 150 words per minute)
                words = len(text.split())
                duration = max(1, words / 150 * 60 / speed)
                time.sleep(duration)
            return True

    except Exception as e:
        pass

    # Method 2: Direct intent (root required)
    try:
        cmd = [
            'am', 'start',
            '-a', 'android.intent.action.TTS_SERVICE',
            '--es', 'text', text,
            '--es', 'language', _tts_config.get('language', 'pt-BR')
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=5)
        return result.returncode == 0

    except Exception:
        pass

    return False


def _speak_pyttsx3(text: str) -> bool:
    """
    Speak using pyttsx3 (espeak backend).

    Args:
        text: Text to speak

    Returns:
        True if successful
    """
    try:
        import pyttsx3

        engine = pyttsx3.init()

        # Set voice properties
        engine.setProperty('rate', int(150 * _tts_config.get('speed', 1.0)))
        engine.setProperty('volume', _tts_config.get('volume', 0.8))

        # Try to set Portuguese voice
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'portuguese' in voice.name.lower() or 'brazil' in voice.name.lower():
                engine.setProperty('voice', voice.id)
                break

        engine.say(text)
        engine.runAndWait()
        return True

    except Exception as e:
        return False


def set_voice_config(
    engine: Optional[str] = None,
    speed: Optional[float] = None,
    pitch: Optional[float] = None,
    language: Optional[str] = None,
    volume: Optional[float] = None
) -> None:
    """
    Configure TTS settings.

    Args:
        engine: TTS engine - 'android' or 'pyttsx3'
        speed: Speech speed (0.1 to 2.0, default: 1.0)
        pitch: Voice pitch (0.1 to 2.0, default: 1.0)
        language: Language code (default: 'pt-BR')
        volume: Volume level (0.0 to 1.0, default: 0.8)
    """
    if engine is not None:
        _tts_config['engine'] = engine
    if speed is not None:
        _tts_config['speed'] = max(0.1, min(2.0, speed))
    if pitch is not None:
        _tts_config['pitch'] = max(0.1, min(2.0, pitch))
    if language is not None:
        _tts_config['language'] = language
    if volume is not None:
        _tts_config['volume'] = max(0.0, min(1.0, volume))


def get_voice_config() -> dict:
    """
    Get current TTS configuration.

    Returns:
        Dictionary with current TTS settings
    """
    return _tts_config.copy()


def test_tts() -> bool:
    """
    Test TTS functionality.

    Returns:
        True if TTS is working
    """
    test_phrases = [
        "Olá, teste de voz.",
        "Hello, voice test.",
    ]

    for phrase in test_phrases:
        if speak(phrase, wait=True):
            return True

    return False
