# 🧪 Guia de Testes Rápido - PhoneAgent Voice

**Como testar o sistema em 10-15 minutos**

---

## 📱 PASSO 1: Preparar o Ambiente (no Android/Termux)

### 1.1. Copiar arquivos para o Termux
```bash
# Se ainda não copiou
cd ~
# Copie a pasta Phone-Agent para o Termux
```

### 1.2. Executar teste rápido automático
```bash
cd Phone-Agent
bash test-quick.sh
```

**Este script testa:**
- ✓ Python instalado
- ✓ Whisper.cpp compilado
- ✓ Modelo Whisper disponível
- ✓ Termux:API instalado
- ✓ Gravação de áudio funciona
- ✓ Módulos Python importam
- ✓ Roteador de intenções (<100ms)

**Resultado esperado:** "✓ TODOS OS TESTES PASSARAM"

---

## 🎤 PASSO 2: Teste de Voz Básico (2 minutos)

### 2.1. Iniciar assistente
```bash
python phoneagent/pa-voice.py --duration 3
```

### 2.2. Testar comando simples
```
💬 Pressione Enter para falar...
[FALE AGORA]: "Olá teste de voz"
```

**Validar:**
- ✓ Grava áudio (3 segundos)
- ✓ Transcreve corretamente
- ✓ Responde por voz

---

## 🎵 PASSO 3: Teste de Música (3 minutos)

### 3.1. Comando de música
```
[FALE]: "Toque Love For You da LOVELI LORI"
```

**Medir tempo com cronômetro do momento que você termina de falar até a música começar**

**Validar:**
- ✓ Intent identificado como "music"
- ✓ Música toca (ou abre busca)
- ✓ Tempo: idealmente <3s (aceitável até 10s no primeiro comando)
- ✓ Volume automático 50%

### 3.2. Controle de música
```
[FALE]: "Pause"
[FALE]: "Continue"
[FALE]: "Próxima"
```

**Validar:**
- ✓ Cada comando executa rapidamente (<2s)
- ✓ Ações verificadas (confirma mudança de estado)

---

## 🔊 PASSO 4: Teste de Volume (1 minuto)

```
[FALE]: "Aumente o volume"
[FALE]: "Volume cinquenta"
[FALE]: "Volume máximo"
```

**Validar:**
- ✓ Cada comando executa em <1s
- ✓ Volume realmente muda

---

## ⏰ PASSO 5: Teste de Alarme (2 minutos)

```
[FALE]: "Coloque um alarme às sete da manhã"
```

**Validar:**
- ✓ Alarme criado
- ✓ App Relógio abre para confirmar
- ✓ Alarme aparece LIGADO
- ✓ Tempo <4s

**IMPORTANTE:** Verifique manualmente no app se o alarme está LIGADO (não desligado)

---

## 📱 PASSO 6: Teste de Dispositivo (1 minuto)

```
[FALE]: "Ligue o WiFi"
[AGUARDE]
[FALE]: "Desligue o WiFi"
```

**Validar:**
- ✓ WiFi liga/desliga
- ✓ Rápido (<1s cada)

---

## 💬 PASSO 7: Teste de Contexto (2 minutos)

```
Turno 1: "Toque música da LOVELI LORI"
[AGUARDE música tocar]

Turno 2: "Coloque outra"
[VALIDAR: música diferente toca]

Turno 3: "Aumente"
[VALIDAR: volume aumenta - contexto de áudio]
```

---

## 📊 PASSO 8: Reportar Resultados

### Copie e preencha este template:

```markdown
## 🧪 Resultado dos Testes - PhoneAgent Voice

**Data:** 2026-10-29
**Dispositivo:** [MODELO DO SEU ANDROID]
**Android:** [VERSÃO]
**Termux:** [VERSÃO]

### Teste Automático (test-quick.sh)
- [ ] Passou / [ ] Falhou
- Problemas: ___

### Teste de Voz Básico
- [ ] Passou / [ ] Falhou
- Transcrição correta: [ ] Sim / [ ] Não
- TTS funcionou: [ ] Sim / [ ] Não
- Problemas: ___

### Teste de Música
- [ ] Passou / [ ] Falhou
- Tempo até tocar: ___ segundos (meta: <3s)
- Música tocou: [ ] Sim / [ ] Abriu busca / [ ] Erro
- Volume 50% automático: [ ] Sim / [ ] Não
- Controles (pause/next): [ ] Sim / [ ] Não
- Problemas: ___

### Teste de Volume
- [ ] Passou / [ ] Falhou
- Tempo de resposta: ___ segundos (meta: <0.5s)
- Volume mudou: [ ] Sim / [ ] Não
- Problemas: ___

### Teste de Alarme
- [ ] Passou / [ ] Falhou
- Alarme criado: [ ] Sim / [ ] Não
- Alarme LIGADO: [ ] Sim / [ ] Não / [ ] Não sei
- Tempo: ___ segundos (meta: <2s)
- Problemas: ___

### Teste de Dispositivo
- [ ] Passou / [ ] Falhou
- WiFi liga/desliga: [ ] Sim / [ ] Não
- Problemas: ___

### Teste de Contexto
- [ ] Passou / [ ] Falhou
- "Outra" funcionou: [ ] Sim / [ ] Não
- "Aumente" funcionou: [ ] Sim / [ ] Não
- Problemas: ___

### Performance Geral
- Latência média: ___ segundos
- Dentro das metas: [ ] Sim / [ ] Não
- STT preciso: [ ] Sim / [ ] Não (___% de acerto)
- TTS natural: [ ] Sim / [ ] Não

### Bugs Encontrados
1. ___
2. ___
3. ___

### Logs de Erro (se houver)
```
[COLE AQUI]
```

### Conclusão Geral
- [ ] Sistema funcionou perfeitamente
- [ ] Sistema funcionou com pequenos problemas
- [ ] Sistema não funcionou

### Recomendações
- ___
```

---

## 📤 Como Me Enviar os Resultados

### Opção 1: Cole o template preenchido aqui no chat

### Opção 2: Salve em arquivo
```bash
# No Termux
nano ~/resultado_testes.txt
# Cole o template preenchido
# Ctrl+X para sair, Y para salvar
```

Depois me envie o conteúdo.

---

## 🚨 Se Algo Falhar

### Erro: "Whisper model not found"
```bash
cd ~/whisper.cpp
./models/download-ggml-model.sh base
```

### Erro: "Failed to record audio"
```bash
pm grant com.termux.api android.permission.RECORD_AUDIO
termux-microphone-record -f test.wav -l 2
```

### Erro: "TTS not working"
```bash
# Teste TTS nativo
am start -a android.intent.action.TTS_SERVICE

# Se não funcionar, instale fallback
pkg install espeak
pip install pyttsx3
```

### Módulo não importa
```bash
cd Phone-Agent
ls -la phoneagent/voice/
# Verifique se os arquivos existem
```

---

## ⏱️ Tempo Estimado

- Teste automático: 2 min
- Voz básico: 2 min
- Música: 3 min
- Volume: 1 min
- Alarme: 2 min
- Dispositivo: 1 min
- Contexto: 2 min
- Preencher relatório: 3 min

**Total: ~15 minutos**

---

## 🎯 O Que Eu Preciso Saber

### CRÍTICO (preciso saber)
1. ✅ O sistema funciona? (Sim/Não)
2. ✅ Quais comandos falharam?
3. ✅ Tempos reais vs metas
4. ✅ Bugs encontrados

### IMPORTANTE (gostaria de saber)
5. Qualidade da transcrição (% de acerto)
6. Qualidade do TTS (natural/robótico)
7. Facilidade de uso
8. Sugestões de melhoria

### OPCIONAL (se tiver tempo)
9. Logs de erro completos
10. Screenshots de problemas
11. Testes adicionais

---

## 💡 Dicas

1. **Use ambiente silencioso** para STT funcionar melhor
2. **Fale claramente** mas naturalmente
3. **Aguarde o "🎤 Ouvindo..."** antes de falar
4. **Anote tempos** com cronômetro do celular
5. **Tire screenshots** de erros se aparecerem

---

**Boa sorte com os testes! 🚀**

Qualquer problema, me envie:
- Mensagem de erro
- O que você falou
- O que aconteceu
