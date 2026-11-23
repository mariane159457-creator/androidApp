# PhoneAgent Voice Assistant

Sistema de assistente de voz local para Android, similar à Alexa, mas completamente offline e integrado ao PhoneAgent.

## 🎯 Características

- ✅ **100% Offline**: Whisper.cpp + Ollama local + Android TTS nativo
- ✅ **Português nativo**: Otimizado para PT-BR
- ✅ **Rápido**: <3s para música, <0.5s para volume
- ✅ **Privado**: Nenhum dado enviado para a nuvem
- ✅ **Integrado**: Usa toda a infraestrutura do PhoneAgent

## 🚀 Início Rápido

### 1. Instalação

```bash
cd Phone-Agent
chmod +x phoneagent/pa-voice.py
```

As dependências já estão instaladas pelo `setup.sh` original:
- ✅ whisper.cpp (compilado)
- ✅ Termux:API
- ✅ ffmpeg
- ✅ Python 3

### 2. Uso Básico

```bash
# Iniciar assistente de voz
python phoneagent/pa-voice.py

# Com modelo mais rápido (tiny)
python phoneagent/pa-voice.py --model tiny

# Gravar por mais tempo (10 segundos)
python phoneagent/pa-voice.py --duration 10

# Em inglês
python phoneagent/pa-voice.py --lang en
```

### 3. Comandos de Exemplo

```
🎤 "Toque Love For You da LOVELI LORI"
   → Busca e toca música no YouTube Music

🎤 "Aumente o volume"
   → Aumenta volume de mídia

🎤 "Próxima música"
   → Pula para próxima faixa

🎤 "Coloque um alarme às 7 da manhã"
   → Cria alarme verificado

🎤 "Ligue o WiFi"
   → Ativa WiFi

🎤 "Aumente o brilho"
   → Aumenta brilho da tela
```

## 📁 Arquitetura

```
phoneagent/
├── voice/
│   ├── __init__.py       # Interface pública do módulo
│   ├── stt.py            # Speech-to-Text (Whisper.cpp)
│   ├── tts.py            # Text-to-Speech (Android TTS)
│   └── audio.py          # Captura e reprodução de áudio
├── intent_router.py      # Roteador rápido de intenções
├── music_service.py      # Serviço otimizado de música
├── conversation.py       # Contexto de conversa
├── pa-voice.py          # Interface CLI principal
└── brain.py             # Core existente (comandos, parsers)
```

## 🎵 Fluxo de Execução

```
VOZ → STT (Whisper) → ROTEADOR DE INTENÇÕES
                              ↓
        ┌─────────────────────┴──────────────┬────────────┐
        ↓                                    ↓            ↓
    MÚSICA (<3s)                        VOLUME (<0.5s)  ALARME (<2s)
        ↓                                    ↓            ↓
    MusicService                        Brain.do_volume  Brain.do_alarm
        ↓                                    ↓            ↓
        └────────────────────────────────────┴────────────┘
                              ↓
                    TTS (Android) → FALA
```

## ⚡ Performance

| Comando | Meta | Componentes |
|---------|------|-------------|
| Música | <3s | Intent direto + verificação de sessão |
| Volume | <0.5s | Comando direto via `cmd` |
| Alarme | <2s | Intent + verificação no app Relógio |
| STT | <1.5s | Whisper.cpp base model |
| TTS | <0.5s | Android TTS nativo |

## 🧠 Roteamento Inteligente

O `IntentRouter` classifica comandos em <100ms sem usar LLM:

1. **Rotas rápidas** (sem modelo):
   - Música: regex + parser existente
   - Volume: detecção de padrões numéricos
   - Alarmes: parse de horários
   - Dispositivo: liga/desliga WiFi, BT, etc.

2. **Fallback conversacional**:
   - Perguntas complexas → LLM (Ollama)

## 🎤 Speech-to-Text

### Whisper.cpp (Padrão)
- ✅ Offline
- ✅ Alta precisão em PT-BR
- ✅ Já instalado pelo setup.sh
- ⚡ ~1-2s para frases curtas (modelo base)

```python
from phoneagent.voice import transcribe_audio

text = transcribe_audio("audio.wav", language="pt", model="base")
```

### Modelos Disponíveis
- `tiny`: Mais rápido, menor precisão (~500ms)
- `base`: Balanceado (padrão, ~1.5s)
- `small`: Maior precisão (~3s)

## 🔊 Text-to-Speech

### Android TTS (Padrão)
- ✅ Voz natural
- ✅ Rápido (<0.5s)
- ✅ Offline (voz PT-BR já instalada no Android)

```python
from phoneagent.voice import speak

speak("Olá, como posso ajudar?")
```

### Configuração
```python
from phoneagent.voice import set_voice_config

set_voice_config(
    engine='android',  # ou 'pyttsx3'
    speed=1.1,         # Velocidade (0.1 a 2.0)
    pitch=1.0,         # Tom de voz (0.1 a 2.0)
    language='pt-BR',  # Idioma
    volume=0.8         # Volume (0.0 a 1.0)
)
```

## 🎵 Serviço de Música Otimizado

O `MusicService` substitui navegação visual por intents diretos:

**Antes (10-30s)**:
- Abrir app → Buscar → Clicar → Verificar

**Agora (<3s)**:
- Intent `MEDIA_PLAY_FROM_SEARCH` → Verificação de sessão

```python
from phoneagent.music_service import MusicService

music = MusicService(brain._sh, brain.pkgs)

# Tocar música
success, msg, time = music.play("Love For You", "LOVELI LORI")

# Controlar reprodução
success, msg = music.control("pause")
success, msg = music.control("next")
```

## 💬 Contexto de Conversa

O sistema mantém histórico para resolver referências:

```python
# Primeira interação
🎤 "Toque música X"
💭 "Tocando música X"

# Continuação (com contexto)
🎤 "Coloque outra"
💭 Entende: trocar para música diferente

🎤 "Aumente"
💭 Entende: aumentar volume (último contexto de áudio)
```

```python
from phoneagent.conversation import ConversationContext

ctx = ConversationContext(max_turns=5, ttl_seconds=300)

# Adicionar turno
ctx.add_turn(user_input, agent_response, intent_type, params)

# Resolver referências
resolved_params = ctx.resolve_reference(text, intent_type, params)
```

## 🐛 Debug e Testes

### Testar STT
```bash
cd phoneagent/voice
python stt.py  # Testa transcrição
```

### Testar TTS
```bash
cd phoneagent/voice
python tts.py  # Testa síntese de voz
```

### Testar Roteador
```bash
cd phoneagent
python intent_router.py  # Benchmark de routing
```

### Testar Música
```bash
cd phoneagent
python music_service.py  # Benchmark de serviço
```

## 🔧 Configuração Avançada

### Whisper.cpp

Modelos ficam em `~/whisper.cpp/models/`:
```bash
# Baixar modelo tiny (mais rápido)
cd ~/whisper.cpp
./models/download-ggml-model.sh tiny

# Usar modelo tiny no assistente
python phoneagent/pa-voice.py --model tiny
```

### TTS Fallback (pyttsx3)

Se Android TTS não funcionar:
```bash
pkg install espeak
pip install pyttsx3
```

Depois configure no código:
```python
set_voice_config(engine='pyttsx3')
```

## 📊 Métricas de Sucesso

- ✅ Música: <3s (meta atingida com intent direto)
- ✅ Volume: <0.5s (meta atingida com comando direto)
- ✅ STT: <1.5s (Whisper base)
- ✅ TTS: <0.5s (Android nativo)
- ✅ Roteamento: <100ms (sem LLM)

## 🚧 Limitações Conhecidas

1. **Palavra de ativação**: Ainda não implementada (usar botão/Enter)
2. **Conversas complexas**: Fallback para LLM ainda básico
3. **Execução em background**: Android pode matar processo (usar wakelock)
4. **Microfone em Termux**: Pode precisar permissão manual

## 🛠️ Troubleshooting

### "Whisper model not found"
```bash
cd ~/whisper.cpp
./models/download-ggml-model.sh base
```

### "Failed to record audio"
```bash
# Verificar permissão
pm grant com.termux.api android.permission.RECORD_AUDIO

# Testar Termux:API
termux-microphone-record -f test.wav -l 3
```

### "TTS not working"
```bash
# Verificar TTS nativo
am start -a android.intent.action.TTS_SERVICE

# Fallback para pyttsx3
pkg install espeak
pip install pyttsx3
```

### "Music service not available"
Certifique-se de que `brain.py` está carregado:
```python
from phoneagent.brain import Brain
brain = Brain()
```

## 🔮 Próximos Passos

- [ ] Palavra de ativação (Porcupine/Snowboy)
- [ ] Integração completa com LLM para conversas
- [ ] App Android wrapper (foreground service)
- [ ] Streaming de áudio (reconhecimento contínuo)
- [ ] Feedback por beep (início/fim de gravação)
- [ ] Configuração via arquivo (config.json)

## 📝 Changelog

### v1.0.0 (2026-10-29)
- ✅ Sistema de voz completo (STT + TTS)
- ✅ Roteador de intenções otimizado
- ✅ Serviço de música com cache
- ✅ Contexto de conversa
- ✅ Interface CLI interativa
- ✅ Documentação completa

## 📄 Licença

Parte do projeto PhoneAgent - Mesmo licenciamento do projeto principal.

## 🤝 Contribuindo

1. Leia `AUDITORIA_VOZ.md` para contexto completo
2. Teste no dispositivo Android real
3. Reporte bugs e sugestões
4. Mantenha compatibilidade com brain.py existente
