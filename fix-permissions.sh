#!/data/data/com.termux/files/usr/bin/bash
# Script de correção de permissões para PhoneAgent Voice
# Execute: bash fix-permissions.sh

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Correção de Permissões - PhoneAgent Voice         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 1. Verificar se tem root
echo "1. Verificando acesso root..."
if su -c "echo '✓ Root disponível'" 2>/dev/null; then
    HAS_ROOT=1
    echo ""
else
    echo "⚠ Root não disponível (tentarei métodos alternativos)"
    HAS_ROOT=0
    echo ""
fi

# 2. Conceder permissão RECORD_AUDIO
echo "2. Concedendo permissão de microfone..."
if [ $HAS_ROOT -eq 1 ]; then
    su -c "pm grant com.termux android.permission.RECORD_AUDIO" 2>/dev/null && echo "✓ Permissão RECORD_AUDIO concedida" || echo "⚠ Falha (pode já estar concedida)"
else
    echo "⚠ Sem root - conceda manualmente:"
    echo "   Configurações → Apps → Termux:API → Permissões → Microfone"
fi
echo ""

# 3. Conceder permissão de armazenamento
echo "3. Concedendo permissão de armazenamento..."
termux-setup-storage 2>/dev/null && echo "✓ Comando executado (aceite o popup se aparecer)" || echo "⚠ Falha"
echo ""

# 4. Verificar Termux:API app
echo "4. Verificando app Termux:API..."
if pm list packages | grep -q com.termux.api; then
    echo "✓ App Termux:API instalado"

    # Verificar versão
    VERSION=$(pm dump com.termux.api | grep versionName | head -1 | cut -d= -f2)
    echo "  Versão: $VERSION"
else
    echo "❌ App Termux:API NÃO INSTALADO"
    echo ""
    echo "   Instale de: https://f-droid.org/en/packages/com.termux.api/"
    echo "   OU via F-Droid app"
fi
echo ""

# 5. Testar permissões
echo "5. Testando permissões..."
echo ""

# Teste de gravação com timeout
echo "   Testando gravação (3 segundos máximo)..."
TEST_FILE="/tmp/permission_test.wav"
rm -f "$TEST_FILE"

timeout 3 termux-microphone-record -f "$TEST_FILE" -l 1 2>/dev/null &
PID=$!

sleep 2

if kill -0 $PID 2>/dev/null; then
    kill $PID 2>/dev/null
    echo "   ❌ FALHOU - Gravação travou (PERMISSÃO NEGADA)"
    echo ""
    echo "   SOLUÇÃO:"
    echo "   1. Abra Configurações do Android"
    echo "   2. Apps → Termux:API"
    echo "   3. Permissões → Microfone → PERMITIR"
    echo ""
    exit 1
else
    wait $PID 2>/dev/null
    if [ -f "$TEST_FILE" ] && [ -s "$TEST_FILE" ]; then
        SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || stat -f%z "$TEST_FILE" 2>/dev/null || echo "?")
        echo "   ✅ SUCESSO - Gravação funcionou ($SIZE bytes)"
        rm -f "$TEST_FILE"
    else
        echo "   ❌ FALHOU - Arquivo não criado"
        exit 1
    fi
fi
echo ""

# 6. Testar TTS
echo "6. Testando TTS..."
if command -v termux-tts-speak &>/dev/null; then
    echo "   Falando texto de teste..."
    termux-tts-speak "Teste de voz" 2>/dev/null && echo "   ✓ TTS funcionou" || echo "   ⚠ TTS falhou"
else
    echo "   ⚠ termux-tts-speak não disponível"
fi
echo ""

# Resumo
echo "════════════════════════════════════════════════════════════"
echo "✅ PERMISSÕES VERIFICADAS"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Próximo passo:"
echo "   cd ~/Phone-Agent"
echo "   bash test-quick.sh"
echo ""
