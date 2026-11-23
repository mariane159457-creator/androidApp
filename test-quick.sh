#!/bin/bash
# PhoneAgent Voice - Script de Teste Rápido
# Execute no Termux (Android)

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     PhoneAgent Voice - Teste Rápido (10 minutos)          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Contadores
PASS=0
FAIL=0

test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSOU${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗ FALHOU${NC}"
        FAIL=$((FAIL + 1))
    fi
    echo ""
}

# ============================================================================
# TESTE 1: Verificar Python
# ============================================================================
echo "════════════════════════════════════════════════════════════"
echo "TESTE 1: Python"
echo "════════════════════════════════════════════════════════════"
python3 --version
test_result $?

# ============================================================================
# TESTE 2: Verificar Whisper.cpp
# ============================================================================
echo "════════════════════════════════════════════════════════════"
echo "TESTE 2: Whisper.cpp"
echo "════════════════════════════════════════════════════════════"
if [ -f "$HOME/whisper.cpp/build/bin/main" ]; then
    echo "✓ Whisper.cpp compilado encontrado"
    test_result 0
elif [ -f "$HOME/whisper.cpp/main" ]; then
    echo "✓ Whisper.cpp compilado encontrado (caminho antigo)"
    test_result 0
else
    echo "✗ Whisper.cpp não encontrado"
    test_result 1
fi

# ============================================================================
# TESTE 3: Verificar modelo Whisper
# ============================================================================
echo "════════════════════════════════════════════════════════════"
echo "TESTE 3: Modelo Whisper"
echo "════════════════════════════════════════════════════════════"
if [ -f "$HOME/whisper.cpp/models/ggml-small.bin" ]; then
    echo "✓ Modelo small encontrado"
    test_result 0
elif [ -f "$HOME/whisper.cpp/models/ggml-base.bin" ]; then
    echo "✓ Modelo base encontrado"
    test_result 0
elif [ -f "$HOME/whisper.cpp/models/ggml-tiny.bin" ]; then
    echo "✓ Modelo tiny encontrado"
    test_result 0
else
    echo "✗ Nenhum modelo encontrado"
    echo "Execute: cd ~/whisper.cpp && ./models/download-ggml-model.sh base"
    test_result 1
fi

# ============================================================================
# TESTE 4: Verificar Termux:API
# ============================================================================
echo "════════════════════════════════════════════════════════════"
echo "TESTE 4: Termux:API"
echo "════════════════════════════════════════════════════════════"
if command -v termux-microphone-record &> /dev/null; then
    echo "✓ Termux:API instalado"
    test_result 0
else
    echo "✗ Termux:API não encontrado"
    echo "Instale: pkg install termux-api"
    test_result 1
fi

# ============================================================================
# TESTE 5: Teste de gravação (1 segundo)
# ============================================================================
echo "════════════════════════════════════════════════════════════"
echo "TESTE 5: Gravação de áudio"
echo "════════════════════════════════════════════════════════════"
echo "Gravando 1 segundo de teste..."
TMPDIR=${TMPDIR:-/data/data/com.termux/files/usr/tmp}
TEST_FILE="$TMPDIR/test_voice_$$.m4a"
if termux-microphone-record -f "$TEST_FILE" -l 1 2>/dev/null; then
    sleep 1.5
    if [ -f "$TEST_FILE" ] && [ -s "$TEST_FILE" ]; then
        echo "✓ Gravação funcionou"
        rm -f "$TEST_FILE"
        test_result 0
    else
        echo "✗ Arquivo vazio ou não criado"
        test_result 1
    fi
else
    echo "✗ Erro ao gravar"
    echo "Execute: pm grant com.termux.api android.permission.RECORD_AUDIO"
    test_result 1
fi

# ============================================================================
# TESTE 6: Imports Python
# ============================================================================
echo "════════════════════════════════════════════════════════════"
echo "TESTE 6: Imports Python"
echo "════════════════════════════════════════════════════════════"
cd phoneagent
python3 -c "
try:
    from voice import stt, tts, audio
    from intent_router import IntentRouter
    from music_service import MusicService
    from conversation import ConversationContext
    print('✓ Todos os módulos importados')
    exit(0)
except Exception as e:
    print(f'✗ Erro ao importar: {e}')
    exit(1)
"
test_result $?
cd ..

# ============================================================================
# TESTE 7: Roteador de Intenções (benchmark)
# ============================================================================
echo "════════════════════════════════════════════════════════════"
echo "TESTE 7: Roteador de Intenções"
echo "════════════════════════════════════════════════════════════"
cd phoneagent
python3 intent_router.py 2>/dev/null | tail -5
test_result $?
cd ..

# ============================================================================
# RESUMO
# ============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    RESUMO DOS TESTES                       ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo -e "Testes passaram: ${GREEN}$PASS${NC}"
echo -e "Testes falharam: ${RED}$FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ TODOS OS TESTES PASSARAM!${NC}"
    echo -e "${GREEN}✓ Sistema pronto para uso!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Para iniciar o assistente de voz:"
    echo "  python phoneagent/pa-voice.py"
    echo ""
else
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}⚠ ALGUNS TESTES FALHARAM${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Corrija os problemas acima antes de continuar."
    echo "Consulte: VOICE_README.md seção Troubleshooting"
    echo ""
fi
