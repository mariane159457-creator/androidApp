#!/data/data/com.termux/files/usr/bin/bash
# Script para testar gravação de microfone interativamente no Termux
# Execute este script DENTRO do Termux (não via ADB)

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Teste de Microfone - Modo Interativo             ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Verificar se Termux:API está instalado
if ! command -v termux-microphone-record &> /dev/null; then
    echo "❌ Termux:API não encontrado"
    echo "   Instale: pkg install termux-api"
    exit 1
fi

echo "✓ Termux:API encontrado"
echo ""

# Testar permissão
echo "📋 Testando permissão de microfone..."
TEST_FILE="/tmp/test_mic_$(date +%s).wav"

echo "   Tentando gravar 2 segundos..."
echo "   (Arquivo: $TEST_FILE)"
echo ""

# Gravar com timeout de 5 segundos (2s de gravação + margem)
timeout 5 termux-microphone-record -f "$TEST_FILE" -l 2

RESULT=$?

echo ""
echo "════════════════════════════════════════════════════════════"

if [ $RESULT -eq 0 ]; then
    if [ -f "$TEST_FILE" ] && [ -s "$TEST_FILE" ]; then
        SIZE=$(du -h "$TEST_FILE" | cut -f1)
        echo "✅ SUCESSO!"
        echo "   Arquivo criado: $SIZE"
        ls -lh "$TEST_FILE"
        rm -f "$TEST_FILE"
        echo ""
        echo "🎉 Microfone está funcionando!"
        echo "   Você pode usar o PhoneAgent Voice agora."
        exit 0
    else
        echo "❌ FALHOU: Arquivo vazio ou não criado"
        RESULT=1
    fi
elif [ $RESULT -eq 124 ]; then
    echo "❌ TIMEOUT: Comando travou"
    echo ""
    echo "Possíveis causas:"
    echo "1. Permissão de microfone não concedida"
    echo "2. Termux:API app não está instalado/atualizado"
    RESULT=1
else
    echo "❌ ERRO: Código de saída $RESULT"
    RESULT=1
fi

# Se falhou, dar instruções
if [ $RESULT -ne 0 ]; then
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "📝 SOLUÇÃO:"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "1. Verifique se Termux:API app está instalado:"
    echo "   - Abra F-Droid"
    echo "   - Busque \"Termux:API\""
    echo "   - Instale ou atualize"
    echo ""
    echo "2. Conceda permissão de microfone:"
    echo "   - Configurações → Apps → Termux:API"
    echo "   - Permissões → Microfone → Permitir"
    echo ""
    echo "3. Teste novamente:"
    echo "   bash test-mic-interactive.sh"
    echo ""
fi

exit $RESULT
