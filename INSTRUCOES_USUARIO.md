# 🎯 INSTRUÇÕES PARA O USUÁRIO

## ⚠️ IMPORTANTE: Teste Manual Necessário

Após várias tentativas de teste via ADB, identifiquei que:

✅ **O QUE JÁ ESTÁ CORRETO:**
- Whisper.cpp compilado em `~/whisper.cpp/build/bin/main`
- Código corrigido para usar o caminho correto
- Termux:API instalado
- Permissões de microfone CONCEDIDAS (verificado via dumpsys)

❌ **O PROBLEMA:**
- `termux-microphone-record` **trava quando executado via ADB/su**
- Este é um comportamento conhecido do Android 14 com microfone
- A gravação precisa ser iniciada de dentro do app Termux interativamente

---

## 📝 O QUE VOCÊ PRECISA FAZER

### PASSO 1: Abrir Termux no Celular

1. Abra o app **Termux** no seu celular
2. Digite:
   ```bash
   cd ~/Phone-Agent
   bash test-mic-direct.sh
   ```

3. **Observe o resultado:**
   - ✅ Se mostrar "SUCESSO! Microfone funcionando" → **PRONTO!**
   - ❌ Se travar ou dar timeout → vá para PASSO 2

---

### PASSO 2: Se Der Problema

Execute no Termux:

```bash
termux-microphone-record -f /tmp/test.wav -l 2
ls -lh /tmp/test.wav
rm /tmp/test.wav
```

**Possíveis problemas:**

#### Problema A: Comando não encontrado
```bash
pkg install termux-api
```

#### Problema B: Trava/Timeout

Isso significa que a permissão não foi concedida corretamente.

**Solução:**

1. No celular: **Configurações** → **Apps** → **Termux:API**
2. Toque em **Permissões**
3. Toque em **Microfone**
4. Selecione **"Permitir apenas ao usar o app"** ou **"Perguntar sempre"**
5. Volte para o Termux e teste novamente

**OU use o app Termux:API uma vez:**
- Abra o app Termux:API (ícone na gaveta de apps)
- O Android pode pedir permissão neste momento
- Conceda e teste novamente

---

### PASSO 3: Depois que Funcionar

Quando `test-mic-direct.sh` mostrar "SUCESSO":

```bash
cd ~/Phone-Agent
bash test-quick.sh
```

**Resultado esperado:**
```
Testes passaram: 7
Testes falharam: 0
✓ TODOS OS TESTES PASSARAM!
```

Se ainda faltar o modelo Whisper (Teste 3 falha):

```bash
bash download-model.sh
```
- Escolha opção **1** (tiny - mais rápido)
- Aguarde download (~75MB, 2-5 minutos)

---

### PASSO 4: Usar o Assistente

```bash
cd ~/Phone-Agent
python3 phoneagent/pa-voice.py --model tiny --duration 3
```

**Pressione Enter** quando ver "Pressione Enter para falar..."

**Comandos para testar:**
- "aumente o volume"
- "diminua o volume"  
- "toque música da loveli lori"

---

## 🔍 Por Que Via ADB Não Funciona?

**Android 14 tem restrições de segurança:**
- Microfone só pode ser acessado por apps em primeiro plano
- Comandos via ADB/su são considerados "background"
- Por isso `termux-microphone-record` trava indefinidamente
- É um comportamento esperado, não um bug

**Solução:**
- Executar os testes **dentro do app Termux** diretamente
- Depois que funcionar uma vez, o PhoneAgent Voice funcionará normalmente

---

## 📊 Status Atual do Sistema

| Componente | Status | Notas |
|------------|--------|-------|
| Python 3.14.8 | ✅ OK | Verificado |
| Whisper.cpp | ✅ OK | Compilado em build/bin/main |
| Modelo Whisper | ❓ Desconhecido | Verificar com download-model.sh |
| Termux:API | ✅ OK | Instalado |
| Permissão Mic | ✅ OK | Concedida via pm grant |
| Código PhoneAgent | ✅ OK | Caminhos corrigidos |
| Teste via ADB | ❌ Trava | Limitação do Android 14 |
| **Teste Interativo** | **❓ PENDENTE** | **Você precisa testar** |

---

## 💬 Me Avise o Resultado

Depois de testar no Termux, me avise:

1. **Se funcionou:**
   - "Funcionou! Todos os testes passaram"
   - Eu marco como concluído ✅

2. **Se deu erro:**
   - Copie e cole a mensagem de erro exata
   - Eu analiso e corrijo

---

## 📁 Arquivos Importantes

Todos criados/atualizados hoje:

```
~/Phone-Agent/
├── test-mic-direct.sh       ← NOVO - teste interativo
├── test-quick.sh            ← Atualizado - testa tudo
├── download-model.sh        ← NOVO - só baixa modelo
├── fix-permissions.sh       ← Para conceder permissões
├── diagnose.sh              ← Diagnóstico completo
├── COMECE_AQUI.md          ← Guia atualizado
├── INSTRUCOES_USUARIO.md   ← ESTE ARQUIVO
└── phoneagent/
    └── voice/
        └── stt.py          ← Corrigido - caminho whisper
```

---

## ⏱️ Tempo Estimado

- PASSO 1 (teste microfone): **1 minuto**
- PASSO 2 (corrigir permissões se necessário): **2 minutos**
- PASSO 3 (download modelo, se necessário): **2-5 minutos**
- PASSO 4 (testar assistente): **2 minutos**

**TOTAL: 5-10 minutos**

---

**Criado:** 2026-10-29 21:32 UTC  
**Versão:** 1.0.3 - Correção final com instruções de teste interativo
