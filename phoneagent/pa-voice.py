#!/usr/bin/env python3
"""
PhoneAgent Voice Assistant - Main CLI interface.

Usage:
    pa-voice [--model tiny|base] [--lang pt|en] [--duration 5]

Interactive voice loop:
1. Listen for audio (default: 5 seconds)
2. Transcribe to text (Whisper.cpp)
3. Route and execute intent
4. Respond by voice (TTS)

Press Ctrl+C to exit.
"""

import os
import sys
import time
import signal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from phoneagent.voice import transcribe_audio, speak, record_audio, set_voice_config
from phoneagent.voice.audio import cleanup_temp_audio
from phoneagent.intent_router import IntentRouter
from phoneagent.music_service import MusicService


class VoiceAssistant:
    """
    PhoneAgent voice-enabled assistant.

    Integrates:
    - STT (Whisper.cpp)
    - TTS (Android native)
    - Intent routing
    - Command execution
    """

    def __init__(self, model="base", language="pt", duration=5):
        """
        Args:
            model: Whisper model - "tiny" or "base" (default: "base")
            language: Language code - "pt" or "en" (default: "pt")
            duration: Recording duration in seconds (default: 5)
        """
        self.model = model
        self.language = language
        self.duration = duration
        self.router = IntentRouter()
        self.running = False

        # Import brain for command execution
        try:
            from phoneagent.brain import BrainMixin
            import subprocess

            # Create minimal brain instance with just _sh method
            class MinimalBrain(BrainMixin):
                def __init__(self):
                    self.pkgs = set()

                def _sh(self, cmd):
                    """Execute shell command via su."""
                    result = subprocess.run(
                        ['su', '-c', cmd],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    return result.stdout

            self.brain = MinimalBrain()
            self.music = MusicService(self.brain._sh, self.brain.pkgs)
        except Exception as e:
            print(f"⚠️  Aviso: Brain não carregado ({e})")
            self.brain = None
            self.music = None

        # Configure TTS
        set_voice_config(
            engine='android',
            speed=1.1,
            language='pt-BR' if language == 'pt' else 'en-US',
            volume=0.8
        )

    def start(self):
        """Start interactive voice loop."""
        self.running = True

        # Setup signal handler for graceful exit
        signal.signal(signal.SIGINT, self._signal_handler)

        print("🎤 PhoneAgent Voice Assistant")
        print(f"   Modelo: {self.model} | Idioma: {self.language} | Duração: {self.duration}s")
        print("   Pressione Enter para falar (ou Ctrl+C para sair)\n")

        speak("Assistente de voz ativado.")

        while self.running:
            try:
                # Wait for user input
                input("💬 Pressione Enter para falar... ")

                # Record and transcribe
                print("🎤 Ouvindo...")
                text = self._listen()

                if not text or not text.strip():
                    print("❌ Nenhuma fala detectada.\n")
                    speak("Não entendi. Pode repetir?")
                    continue

                print(f"📝 Você disse: {text}")

                # Route and execute
                response = self._process(text)

                print(f"💭 Resposta: {response}\n")

                # Speak response
                speak(response)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Erro: {e}\n")
                speak("Desculpe, ocorreu um erro.")

        self._shutdown()

    def _listen(self) -> str:
        """
        Record audio and transcribe.

        Returns:
            Transcribed text
        """
        audio_file = None
        try:
            # Record
            audio_file = record_audio(duration=self.duration)

            # Transcribe
            print("🔄 Transcrevendo...")
            text = transcribe_audio(audio_file, language=self.language, model=self.model)

            return text.strip()

        except Exception as e:
            print(f"❌ Erro ao ouvir: {e}")
            return ""

        finally:
            if audio_file:
                cleanup_temp_audio(audio_file)

    def _process(self, text: str) -> str:
        """
        Route intent and execute command.

        Args:
            text: User input text

        Returns:
            Response message
        """
        # Route intent
        intent_type, params = self.router.route(text)

        print(f"🎯 Intent: {intent_type}")
        print(f"   Params: {params}")

        # Execute based on intent type
        if intent_type == "music":
            return self._handle_music(params)
        elif intent_type == "music_control":
            return self._handle_music_control(params)
        elif intent_type == "volume":
            return self._handle_volume(params)
        elif intent_type == "brightness":
            return self._handle_brightness(params)
        elif intent_type == "alarm":
            return self._handle_alarm(params)
        elif intent_type == "timer":
            return self._handle_timer(params)
        elif intent_type == "show_alarms":
            return self._handle_show_alarms()
        elif intent_type == "show_timers":
            return self._handle_show_timers()
        elif intent_type == "toggle":
            return self._handle_toggle(params)
        elif intent_type == "conversation":
            return self._handle_conversation(params)
        else:
            return "Desculpe, não entendi o comando."

    def _handle_music(self, params: dict) -> str:
        """Handle music playback."""
        if not self.music:
            return "Serviço de música não disponível."

        title = params.get('title')
        artist = params.get('artist')

        if not title:
            return "Não consegui identificar a música."

        print(f"🎵 Tocando: {title}" + (f" - {artist}" if artist else ""))

        success, message, elapsed = self.music.play(title, artist, set_volume=True)

        print(f"   Tempo: {elapsed:.2f}s {'✓' if elapsed < 3 else '⚠️'}")

        return message

    def _handle_music_control(self, params: dict) -> str:
        """Handle music controls (pause, resume, next, previous)."""
        if not self.music:
            return "Serviço de música não disponível."

        action = params.get('action')
        success, message = self.music.control(action)

        return message

    def _handle_volume(self, params: dict) -> str:
        """Handle volume control."""
        if not self.brain:
            return "Controle de volume não disponível."

        stream = params.get('stream', 'media')
        value = params.get('value')

        success, message = self.brain.do_volume(stream, value)

        return message if success else f"Erro: {message}"

    def _handle_brightness(self, params: dict) -> str:
        """Handle brightness control."""
        if not self.brain:
            return "Controle de brilho não disponível."

        value = params.get('value')

        success, message = self.brain.do_brightness(value)

        return message if success else f"Erro: {message}"

    def _handle_alarm(self, params: dict) -> str:
        """Handle alarm creation."""
        if not self.brain:
            return "Controle de alarmes não disponível."

        hour = params.get('hour')
        minute = params.get('minute')
        label = params.get('label', '')
        days = params.get('days')
        show = params.get('show', False)

        success, message = self.brain.do_alarm(hour, minute, label, days, show)

        return message if success else f"Erro: {message}"

    def _handle_timer(self, params: dict) -> str:
        """Handle timer creation."""
        if not self.brain:
            return "Controle de timers não disponível."

        seconds = params.get('seconds')
        label = params.get('label', '')
        show = params.get('show', False)

        success, message = self.brain.do_timer(seconds, label, show)

        return message if success else f"Erro: {message}"

    def _handle_show_alarms(self) -> str:
        """Show active alarms."""
        if not self.brain:
            return "Controle de alarmes não disponível."

        # Open alarms list
        self.brain._sh("am start -a android.intent.action.SHOW_ALARMS 2>&1")

        return "Mostrando alarmes."

    def _handle_show_timers(self) -> str:
        """Show active timers."""
        if not self.brain:
            return "Controle de timers não disponível."

        # Open timers list
        self.brain._sh("am start -a android.intent.action.SHOW_TIMERS 2>&1")

        return "Mostrando timers."

    def _handle_toggle(self, params: dict) -> str:
        """Handle device toggles (WiFi, Bluetooth, etc.)."""
        if not self.brain:
            return "Controle de dispositivo não disponível."

        setting = params.get('setting')
        on = params.get('on')

        success, message = self.brain.do_toggle(setting, on)

        return message if success else f"Erro: {message}"

    def _handle_conversation(self, params: dict) -> str:
        """Handle conversational queries (fallback to LLM)."""
        text = params.get('text', '')

        # For now, just acknowledge
        # TODO: integrate with brain's LLM agent
        return "Desculpe, ainda não posso responder perguntas conversacionais."

    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully."""
        print("\n\n👋 Encerrando...")
        self.running = False

    def _shutdown(self):
        """Clean shutdown."""
        speak("Até logo.")
        print("✓ Assistente de voz desativado.\n")


def main():
    """Parse arguments and start voice assistant."""
    import argparse

    parser = argparse.ArgumentParser(
        description="PhoneAgent Voice Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  pa-voice                    # Usar configurações padrão
  pa-voice --model tiny       # Usar modelo menor (mais rápido)
  pa-voice --lang en          # Inglês
  pa-voice --duration 10      # Gravar por 10 segundos
        """
    )

    parser.add_argument(
        '--model',
        choices=['tiny', 'base', 'small'],
        default='small',
        help='Whisper model size (default: small)'
    )

    parser.add_argument(
        '--lang',
        choices=['pt', 'en'],
        default='pt',
        help='Language (default: pt)'
    )

    parser.add_argument(
        '--duration',
        type=int,
        default=5,
        help='Recording duration in seconds (default: 5)'
    )

    args = parser.parse_args()

    # Create and start assistant
    assistant = VoiceAssistant(
        model=args.model,
        language=args.lang,
        duration=args.duration
    )

    try:
        assistant.start()
    except KeyboardInterrupt:
        print("\n👋 Interrompido pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
