# 🧪 PhoneAgent Voice - Plano de Testes

**Versão:** 1.0.0  
**Data:** 2026-10-29  
**Status:** Pronto para execução

---

## 📋 Pré-requisitos

### Hardware
- ✓ Dispositivo Android (testado em Termux)
- ✓ Microfone funcional
- ✓ Alto-falante ou fone de ouvido
- ✓ Root access (para controle total)

### Software
- ✓ Termux instalado
- ✓ Termux:API instalado (app + pacote)
- ✓ Python 3.x
- ✓ Whisper.cpp compilado
- ✓ PhoneAgent Voice instalado

### Verificação Rápida
```bash
# No Termux
cd ~/Phone-Agent
bash install-voice.sh
```

---

## 🎯 Testes Unitários

### Teste 1: Captura de Áudio
**Objetivo:** Verificar se o microfone captura áudio corretamente

```bash
cd phoneagent/voice
python -c "
from audio import record_audio
print('Gravando 3 segundos...')
file = record_audio(duration=3)
print(f'Áudio salvo em: {file}')
"
```

**Resultado esperado:**
- ✓ Gravação sem erro
- ✓ Arquivo .wav criado
- ✓ Tamanho > 0 bytes

**Possíveis problemas:**
- ❌ Permissão negada → Execute: `pm grant com.termux.api android.permission.RECORD_AUDIO`
- ❌ Termux:API não encontrado → Instale: `pkg install termux-api`

---

### Teste 2: Speech-to-Text (Whisper)
**Objetivo:** Verificar transcrição de áudio

```bash
cd phoneagent/voice
python -c "
from stt import start_listening
print('Fale algo por 5 segundos...')
text, audio_file = start_listening(duration=5, model='base')
print(f'Transcrito: {text}')
"
```

**Frases de teste:**
- "Olá, teste de voz"
- "Toque música do artista"
- "Coloque um alarme"

**Resultado esperado:**
- ✓ Transcrição correta (>80% precisão)
- ✓ Tempo <2s para modelo base
- ✓ Acentos preservados

**Possíveis problemas:**
- ❌ Modelo não encontrado → Baixe: `cd ~/whisper.cpp && ./models/download-ggml-model.sh base`
- ❌ Muito lento → Use modelo tiny: `model='tiny'`

---

### Teste 3: Text-to-Speech (TTS)
**Objetivo:** Verificar síntese de voz

```bash
cd phoneagent/voice
python -c "
from tts import speak, test_tts
print('Testando TTS...')
test_tts()
"
```

**Resultado esperado:**
- ✓ Voz em português audível
- ✓ Sem distorções
- ✓ Volume adequado

**Possíveis problemas:**
- ❌ Sem som → Verifique volume do sistema
- ❌ Erro de TTS → Use fallback: `set_voice_config(engine='pyttsx3')`

---

### Teste 4: Roteador de Intenções
**Objetivo:** Verificar classificação rápida

```bash
cd phoneagent
python intent_router.py
```

**Resultado esperado:**
```
<100ms | music           | toque love for you da loveli lori
<100ms | volume          | aumente o volume
<100ms | alarm           | coloque um alarme às 7 da manhã
<100ms | music_control   | próxima música
<100ms | toggle          | ligue o wifi
<100ms | conversation    | qual a previsão do tempo?

Average: <50ms
Max: <100ms
```

**Critério de sucesso:**
- ✓ Média <100ms
- ✓ Todos os comandos classificados corretamente

---

### Teste 5: Serviço de Música
**Objetivo:** Verificar reprodução otimizada

```bash
cd phoneagent
python music_service.py
```

**Resultado esperado:**
```
Success: True
Message: Tocando Love For You - LOVELI LORI (confirmado)
Time: 2.500s (total: 2.503s)
Target: <3s ✓
```

**Critério de sucesso:**
- ✓ Tempo <3s
- ✓ Reprodução verificada

---

## 🎤 Testes de Integração

### Teste 6: Interface Completa
**Objetivo:** Validar loop completo de voz

```bash
python phoneagent/pa-voice.py --model base --duration 5
```

**Sequência de testes:**

#### 6.1. Teste de Música
```
INPUT: "Toque love for you da loveli lori"
EXPECTED:
  🎯 Intent: music
  🎵 Tocando: Love For You - LOVELI LORI
     Tempo: <3s ✓
  💭 Resposta: "Tocando Love For You..."
  🔊 TTS reproduz resposta
```

#### 6.2. Teste de Volume
```
INPUT: "Aumente o volume"
EXPECTED:
  🎯 Intent: volume
     Tempo: <0.5s ✓
  💭 Resposta: "Volume aumentado"
```

#### 6.3. Teste de Controle
```
INPUT: "Próxima música"
EXPECTED:
  🎯 Intent: music_control
     Tempo: <1s ✓
  💭 Resposta: "Faixa alterada..."
```

#### 6.4. Teste de Alarme
```
INPUT: "Coloque um alarme às 7 da manhã"
EXPECTED:
  🎯 Intent: alarm
     Tempo: <2s ✓
  💭 Resposta: "Alarme criado para 07:00..."
```

#### 6.5. Teste de Dispositivo
```
INPUT: "Ligue o WiFi"
EXPECTED:
  🎯 Intent: toggle
     Tempo: <1s ✓
  💭 Resposta: "WiFi ativado"
```

---

## 🔄 Testes de Contexto

### Teste 7: Referências
**Objetivo:** Validar resolução de contexto

```
Turno 1:
  INPUT: "Toque uma música da LOVELI LORI"
  VERIFY: Música toca

Turno 2:
  INPUT: "Coloque outra"
  VERIFY: Música diferente toca

Turno 3:
  INPUT: "Aumente"
  VERIFY: Volume aumenta (contexto de áudio)
```

**Critério de sucesso:**
- ✓ "outra" resolve para música diferente
- ✓ "aumente" resolve para volume
- ✓ Contexto mantido por 5 minutos

---

## ⚡ Testes de Performance

### Teste 8: Latência End-to-End

**Método:**
1. Pressionar Enter
2. Falar comando
3. Medir até início da ação

**Comandos para medir:**

| Comando | Meta | Real | Status |
|---------|------|------|--------|
| "Toque música X" | <5s total | ___ | ___ |
| "Aumente volume" | <2s total | ___ | ___ |
| "Próxima" | <2s total | ___ | ___ |
| "Alarme 7h" | <4s total | ___ | ___ |

**Breakdown esperado:**
- Gravação: 5s (fixo)
- STT: 1-2s
- Roteamento: <0.1s
- Execução: 0.5-2s
- TTS: 0.5s

**Total:** 7-10s para primeiro comando, 2-4s para comandos seguintes

---

## 🔧 Testes de Resiliência

### Teste 9: Comandos Inválidos

```
INPUT: "blá blá blá sem sentido"
EXPECTED: "Desculpe, não entendi"

INPUT: "" (silêncio)
EXPECTED: "Nenhuma fala detectada"

INPUT: "toque música" (incompleto)
EXPECTED: Fallback para conversação ou erro claro
```

### Teste 10: Interrupção (Ctrl+C)

```bash
python phoneagent/pa-voice.py
# Durante execução, pressionar Ctrl+C
```

**EXPECTED:**
- ✓ Mensagem "Encerrando..."
- ✓ TTS: "Até logo"
- ✓ Sem processos zumbis
- ✓ Cleanup de arquivos temporários

---

## 📊 Checklist de Validação

### Funcionalidades Core
- [ ] Captura de áudio funciona
- [ ] Whisper.cpp transcreve PT-BR
- [ ] Android TTS fala em PT-BR
- [ ] Roteamento <100ms
- [ ] Música toca em <3s
- [ ] Volume muda em <0.5s
- [ ] Alarmes criam em <2s
- [ ] Dispositivo controla (WiFi, BT, etc)

### Qualidade
- [ ] Transcrição >80% precisa
- [ ] TTS natural e claro
- [ ] Sem erros de encoding
- [ ] Sem crashes
- [ ] Cleanup de arquivos temp

### Performance
- [ ] Latência total <10s primeiro comando
- [ ] Latência total <4s comandos seguintes
- [ ] Uso de memória <500MB
- [ ] CPU <50% média

### UX
- [ ] Feedback visual claro
- [ ] Mensagens de erro úteis
- [ ] Ctrl+C funciona
- [ ] Permissões solicitadas claramente

---

## 🐛 Registro de Bugs

### Template
```
BUG #___
Comando: "___"
Esperado: ___
Obtido: ___
Logs: ___
Dispositivo: ___
```

### Bugs Conhecidos (Brain.py Original)
Estes bugs já foram identificados na auditoria, mas NÃO corrigidos ainda:

1. ❌ **Alarmes:** verificação aceita alarme desligado
2. ❌ **Música:** loops de navegação entre telas
3. ❌ **Encoding:** erro ASCII em http_get
4. ❌ **KeyboardInterrupt:** não limpa Ollama

---

## 📈 Relatório de Testes

Após executar todos os testes, preencher:

```markdown
## Relatório de Testes - PhoneAgent Voice

**Data:** ___
**Dispositivo:** ___
**Android:** ___
**Termux:** ___

### Resumo
- Testes executados: ___ / 10
- Testes passados: ___
- Testes falhados: ___
- Taxa de sucesso: ___%

### Detalhes
| Teste | Status | Tempo | Notas |
|-------|--------|-------|-------|
| 1. Captura | ___ | ___ | ___ |
| 2. STT | ___ | ___ | ___ |
| 3. TTS | ___ | ___ | ___ |
| 4. Roteador | ___ | ___ | ___ |
| 5. Música | ___ | ___ | ___ |
| 6. Integração | ___ | ___ | ___ |
| 7. Contexto | ___ | ___ | ___ |
| 8. Performance | ___ | ___ | ___ |
| 9. Resiliência | ___ | ___ | ___ |
| 10. Interrupção | ___ | ___ | ___ |

### Performance Real
| Métrica | Meta | Real | Delta |
|---------|------|------|-------|
| Música | <3s | ___ | ___ |
| Volume | <0.5s | ___ | ___ |
| Alarme | <2s | ___ | ___ |
| STT | <1.5s | ___ | ___ |
| TTS | <0.5s | ___ | ___ |

### Bugs Encontrados
1. ___
2. ___

### Recomendações
- ___
- ___

### Conclusão
___
```

---

## 🚀 Próximos Passos Após Testes

### Se todos os testes passarem (✅)
1. Marcar versão 1.0.0 como estável
2. Criar release notes
3. Opcional: implementar melhorias (palavra de ativação, etc)

### Se houver falhas (❌)
1. Priorizar bugs críticos (crash, sem áudio, etc)
2. Corrigir e re-testar
3. Ajustar parâmetros (modelo, duração, etc)

### Ajustes Comuns

**Se STT muito lento:**
```bash
python phoneagent/pa-voice.py --model tiny
```

**Se TTS falha:**
```bash
pkg install espeak
pip install pyttsx3
# E configure no código: set_voice_config(engine='pyttsx3')
```

**Se captura falha:**
- Conceder permissões manualmente
- Verificar Termux:API instalado
- Testar com `termux-microphone-record` diretamente

---

## 📞 Suporte

### Logs
```bash
# Ativar debug
export DEBUG=1
python phoneagent/pa-voice.py 2>&1 | tee test.log
```

### Informações para Report
- Versão do Android
- Modelo do dispositivo
- Saída de `termux-info`
- Logs completos
- Comando que falhou

---

**Boa sorte com os testes! 🚀**
