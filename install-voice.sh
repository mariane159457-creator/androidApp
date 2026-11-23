#!/bin/bash
# PhoneAgent Voice Assistant - Quick Start Script
# Execute no Termux (Android)

set -e

echo "🎤 PhoneAgent Voice Assistant - Instalação Rápida"
echo "=================================================="
echo ""

# Verificar se está no diretório correto
if [ ! -f "phoneagent/pa-voice.py" ]; then
    echo "❌ Erro: Execute este script na raiz do projeto Phone-Agent"
    exit 1
fi

echo "✓ Diretório correto encontrado"
echo ""

# 1. Verificar Python
echo "📦 Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python não encontrado. Instalando..."
    pkg install python -y
else
    echo "✓ Python instalado: $(python3 --version)"
fi
echo ""

# 2. Verificar Termux:API
echo "📦 Verificando Termux:API..."
if ! command -v termux-microphone-record &> /dev/null; then
    echo "⚠️  Termux:API não encontrado"
    echo "   Instale manualmente: pkg install termux-api"
    echo "   E instale o app: https://f-droid.org/en/packages/com.termux.api/"
else
    echo "✓ Termux:API instalado"
fi
echo ""

# 3. Verificar Whisper.cpp
echo "📦 Verificando Whisper.cpp..."
if [ ! -f "$HOME/whisper.cpp/main" ]; then
    echo "⚠️  Whisper.cpp não encontrado"
    echo "   Execute o setup.sh original do PhoneAgent primeiro"
else
    echo "✓ Whisper.cpp compilado"

    # Verificar modelo base
    if [ ! -f "$HOME/whisper.cpp/models/ggml-base.bin" ]; then
        echo "📥 Baixando modelo Whisper base..."
        cd ~/whisper.cpp
        ./models/download-ggml-model.sh base
        cd -
        echo "✓ Modelo base baixado"
    else
        echo "✓ Modelo base disponível"
    fi
fi
echo ""

# 4. Verificar ffmpeg
echo "📦 Verificando ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ ffmpeg não encontrado. Instalando..."
    pkg install ffmpeg -y
else
    echo "✓ ffmpeg instalado"
fi
echo ""

# 5. Verificar permissões
echo "🔐 Verificando permissões..."
echo "   Executando: termux-setup-storage"
termux-setup-storage || echo "   ⚠️  Conceda permissão de armazenamento se solicitado"

# Verificar permissão de áudio
if pm list packages | grep -q com.termux.api; then
    echo "   Concedendo permissão de áudio..."
    pm grant com.termux.api android.permission.RECORD_AUDIO 2>/dev/null || echo "   ⚠️  Execute como root se necessário"
fi
echo ""

# 6. Tornar pa-voice executável
echo "⚙️  Configurando executável..."
chmod +x phoneagent/pa-voice.py
echo "✓ pa-voice.py configurado"
echo ""

# 7. Teste rápido
echo "🧪 Teste rápido de componentes..."

# Testar Python imports
python3 -c "import sys; print(f'✓ Python {sys.version.split()[0]}')" 2>/dev/null || echo "⚠️  Erro ao importar Python"

# Testar gravação (opcional, se Termux:API disponível)
if command -v termux-microphone-record &> /dev/null; then
    echo "   Testando gravação de áudio (1s)..."
    timeout 2 termux-microphone-record -f /tmp/test_audio.wav -l 1 2>/dev/null && rm -f /tmp/test_audio.wav && echo "✓ Gravação funcionando" || echo "⚠️  Erro na gravação (conceda permissões)"
fi

echo ""
echo "=================================================="
echo "✅ INSTALAÇÃO CONCLUÍDA"
echo "=================================================="
echo ""
echo "🚀 Para iniciar o assistente de voz:"
echo ""
echo "   python3 phoneagent/pa-voice.py"
echo ""
echo "📖 Opções disponíveis:"
echo ""
echo "   --model tiny      # Modelo mais rápido"
echo "   --model base      # Modelo padrão (melhor qualidade)"
echo "   --lang pt         # Português (padrão)"
echo "   --lang en         # Inglês"
echo "   --duration 5      # Duração da gravação (segundos)"
echo ""
echo "💡 Exemplo:"
echo ""
echo "   python3 phoneagent/pa-voice.py --model tiny --duration 3"
echo ""
echo "📚 Documentação completa em: VOICE_README.md"
echo ""
