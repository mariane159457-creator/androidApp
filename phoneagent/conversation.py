"""
Conversation context manager for PhoneAgent voice assistant.

Maintains conversation history for reference resolution and context-aware responses.
"""

import time
from typing import Optional, List, Dict, Any
from collections import deque


class ConversationContext:
    """
    Manages conversation history and context.

    Features:
    - Buffer of last N interactions
    - Reference resolution ("outra música", "aumente")
    - Context expiration (TTL)
    - Topic change detection
    """

    def __init__(self, max_turns: int = 5, ttl_seconds: int = 300):
        """
        Args:
            max_turns: Maximum number of turns to keep (default: 5)
            ttl_seconds: Time-to-live for context in seconds (default: 300 = 5min)
        """
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.history = deque(maxlen=max_turns)
        self.last_entities = {
            'music_title': None,
            'music_artist': None,
            'volume_stream': 'media',
            'alarm_time': None,
            'topic': None,
        }

    def add_turn(self, user_input: str, agent_response: str, intent_type: str, params: Dict[str, Any]):
        """
        Add a conversation turn.

        Args:
            user_input: User's input text
            agent_response: Agent's response
            intent_type: Classified intent type
            params: Intent parameters
        """
        turn = {
            'timestamp': time.time(),
            'user': user_input,
            'agent': agent_response,
            'intent': intent_type,
            'params': params,
        }

        self.history.append(turn)

        # Update last entities for reference resolution
        self._update_entities(intent_type, params)

    def _update_entities(self, intent_type: str, params: Dict[str, Any]):
        """Update tracked entities from intent params."""
        if intent_type == "music":
            self.last_entities['music_title'] = params.get('title')
            self.last_entities['music_artist'] = params.get('artist')
            self.last_entities['topic'] = 'music'

        elif intent_type in ("volume", "music_control"):
            if 'stream' in params:
                self.last_entities['volume_stream'] = params['stream']
            self.last_entities['topic'] = 'music'

        elif intent_type in ("alarm", "timer"):
            if 'hour' in params and 'minute' in params:
                self.last_entities['alarm_time'] = f"{params['hour']:02d}:{params['minute']:02d}"
            self.last_entities['topic'] = 'time'

        elif intent_type in ("brightness", "toggle"):
            self.last_entities['topic'] = 'device'

        elif intent_type == "conversation":
            # Topic might change
            pass

    def resolve_reference(self, text: str, intent_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve references in user input using context.

        Args:
            text: User input text
            intent_type: Current intent type
            params: Current intent params (may be incomplete)

        Returns:
            Updated params with resolved references
        """
        text_lower = text.lower()

        # "outra música" / "outra" -> different music
        if intent_type == "music" and any(word in text_lower for word in ["outra", "outro", "diferente"]):
            # Signal to skip last song (handler will implement)
            params['skip_last'] = True

        # "aumente" / "diminua" without explicit target -> assume last volume stream
        if intent_type == "volume" and not params.get('stream'):
            params['stream'] = self.last_entities.get('volume_stream', 'media')

        # "essa" / "aquela" -> last music/alarm
        if any(word in text_lower for word in ["essa", "este", "isso", "aquela", "aquele", "aquilo"]):
            if self.last_entities.get('topic') == 'music':
                if intent_type == "music" and not params.get('title'):
                    params['title'] = self.last_entities.get('music_title')
                    params['artist'] = self.last_entities.get('music_artist')

        return params

    def get_recent_context(self, n: int = 3) -> List[Dict[str, Any]]:
        """
        Get recent conversation turns.

        Args:
            n: Number of recent turns to get (default: 3)

        Returns:
            List of recent turns (newest first)
        """
        # Filter out expired turns
        now = time.time()
        valid_turns = [
            turn for turn in self.history
            if now - turn['timestamp'] < self.ttl_seconds
        ]

        return list(reversed(valid_turns[-n:]))

    def get_last_entity(self, entity_type: str) -> Optional[Any]:
        """
        Get last value of tracked entity.

        Args:
            entity_type: Entity type (e.g., 'music_title', 'volume_stream')

        Returns:
            Last entity value or None
        """
        return self.last_entities.get(entity_type)

    def clear_old_context(self):
        """Remove expired context."""
        now = time.time()

        # Remove expired turns
        while self.history and now - self.history[0]['timestamp'] > self.ttl_seconds:
            self.history.popleft()

    def clear(self):
        """Clear all context."""
        self.history.clear()
        self.last_entities = {k: None for k in self.last_entities}

    def is_continuation(self, text: str) -> bool:
        """
        Check if input is a continuation of previous topic.

        Args:
            text: User input

        Returns:
            True if appears to be continuation
        """
        if not self.history:
            return False

        text_lower = text.lower()

        # Continuation markers
        continuation_words = [
            "também", "e", "agora", "depois", "outra", "outro",
            "essa", "esse", "isso", "aquela", "aquele",
            "mais", "menos", "aumenta", "diminui"
        ]

        # Short input with continuation word likely references context
        if len(text.split()) <= 3:
            return any(word in text_lower for word in continuation_words)

        return False

    def get_summary(self) -> str:
        """
        Get summary of current context.

        Returns:
            Human-readable summary
        """
        if not self.history:
            return "Nenhum contexto ativo."

        recent = self.get_recent_context(n=3)
        lines = ["Contexto recente:"]

        for i, turn in enumerate(reversed(recent), 1):
            intent = turn['intent']
            user_text = turn['user'][:50]
            lines.append(f"  {i}. [{intent}] {user_text}")

        topic = self.last_entities.get('topic')
        if topic:
            lines.append(f"\nTópico atual: {topic}")

        return "\n".join(lines)


def test_conversation_context():
    """Test conversation context functionality."""
    ctx = ConversationContext(max_turns=5, ttl_seconds=300)

    print("=== Test 1: Basic context ===")
    ctx.add_turn(
        "toque love for you da loveli lori",
        "Tocando Love For You - LOVELI LORI",
        "music",
        {"title": "Love For You", "artist": "LOVELI LORI"}
    )
    print(ctx.get_summary())
    print()

    print("=== Test 2: Reference resolution ===")
    params = ctx.resolve_reference("coloque outra", "music", {})
    print(f"Resolved params: {params}")
    print()

    print("=== Test 3: Implicit volume ===")
    ctx.add_turn("aumente o volume", "Volume aumentado", "volume", {"stream": "media", "value": "+"})
    params = ctx.resolve_reference("diminua", "volume", {"value": "-"})
    print(f"Resolved stream: {params.get('stream')}")
    print()

    print("=== Test 4: Continuation detection ===")
    print(f"'outra música' is continuation: {ctx.is_continuation('outra música')}")
    print(f"'qual a previsão' is continuation: {ctx.is_continuation('qual a previsão')}")
    print()

    print("=== Test 5: Context summary ===")
    ctx.add_turn("próxima", "Próxima música", "music_control", {"action": "next"})
    print(ctx.get_summary())


if __name__ == "__main__":
    test_conversation_context()
