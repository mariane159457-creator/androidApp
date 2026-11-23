"""
Fast intent router for PhoneAgent voice assistant.

Routes commands directly to handlers without LLM when possible.
Reduces latency from 10s+ to <2s for common commands.
"""

import re
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

try:
    from . import brain
except ImportError:
    import brain


class IntentRouter:
    """
    Fast classification and routing for voice commands.

    Routes:
    - music: play, pause, next, previous (<3s target)
    - volume: up, down, set value (<0.5s target)
    - alarm: create, list (<2s target)
    - timer: create, list (<2s target)
    - device: WiFi, Bluetooth, brightness, etc. (<1s target)
    - conversation: fallback to LLM
    """

    def __init__(self):
        self.last_music_query = None
        self.last_volume_stream = "media"
        self.conversation_context = []

    def route(self, text: str, now: Optional[datetime] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Classify intent and extract parameters quickly.

        Args:
            text: User input text
            now: Current datetime (for alarm/timer parsing)

        Returns:
            Tuple of (intent_type, params_dict)

        Intent types:
        - "music": {title, artist, action}
        - "music_control": {action: pause/resume/next/previous}
        - "volume": {stream, value}
        - "brightness": {value}
        - "alarm": {hour, minute, days, label, show}
        - "timer": {seconds, label, show}
        - "show_alarms": {}
        - "show_timers": {}
        - "toggle": {setting, on}
        - "conversation": {text, context}
        """
        if not text or not text.strip():
            return "conversation", {"text": text}

        now = now or datetime.now()

        # Try brain.py fast parser first (already optimized)
        intent = brain.parse_intent(text, now=now)

        if intent:
            # Convert Intent object to dict
            params = {
                k: v for k, v in intent.__dict__.items()
                if not k.startswith('_')
            }
            intent_type = params.pop('kind', 'unknown')

            # Store context for follow-up commands
            if intent_type == "music":
                self.last_music_query = params.get('title')
            elif intent_type == "volume":
                self.last_volume_stream = params.get('stream', 'media')

            return intent_type, params

        # If brain.py couldn't parse, fallback to conversation
        return "conversation", {"text": text, "context": self.conversation_context[-3:]}

    def should_use_model(self, intent_type: str) -> bool:
        """
        Determine if we need to invoke LLM or can handle directly.

        Args:
            intent_type: Intent type from route()

        Returns:
            True if LLM is needed, False if can handle directly
        """
        # These can be handled without LLM
        direct_handlers = {
            "music", "music_control", "volume", "brightness",
            "alarm", "timer", "show_alarms", "show_timers", "toggle"
        }

        return intent_type not in direct_handlers

    def add_context(self, user_text: str, response: str):
        """
        Add to conversation context for reference resolution.

        Args:
            user_text: User's input
            response: Agent's response
        """
        self.conversation_context.append({
            "user": user_text,
            "agent": response,
            "time": time.time()
        })

        # Keep only last 5 interactions
        if len(self.conversation_context) > 5:
            self.conversation_context.pop(0)

    def clear_context(self):
        """Clear conversation context."""
        self.conversation_context.clear()

    def resolve_reference(self, text: str) -> Optional[str]:
        """
        Resolve references like "outra", "essa", "aquela" to actual entities.

        Args:
            text: User input with potential reference

        Returns:
            Resolved text or None if no reference found
        """
        text_lower = text.lower()

        # "coloque outra" -> last music query
        if re.search(r"\b(outra|outro|diferente)\b", text_lower):
            if self.last_music_query:
                # Signal to music handler to pick different song
                return None  # Handler will know to skip last song

        # "aumente" without context -> use last volume stream
        if re.search(r"\b(aument|diminu|abai|suba|desça)\b", text_lower):
            if not re.search(r"\b(volume|som|brilho)\b", text_lower):
                # Implicit volume command
                return text + " o volume"

        return text


def benchmark_routing():
    """
    Benchmark routing performance.
    Should be <100ms for classification.
    """
    router = IntentRouter()

    test_cases = [
        "toque love for you da loveli lori",
        "aumente o volume",
        "coloque um alarme às 7 da manhã",
        "próxima música",
        "ligue o wifi",
        "qual a previsão do tempo?",
    ]

    times = []
    for text in test_cases:
        start = time.perf_counter()
        intent_type, params = router.route(text)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)
        print(f"{elapsed:.2f}ms | {intent_type:15s} | {text}")

    print(f"\nAverage: {sum(times)/len(times):.2f}ms")
    print(f"Max: {max(times):.2f}ms")


if __name__ == "__main__":
    benchmark_routing()
