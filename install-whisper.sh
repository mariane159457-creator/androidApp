#!/data/data/com.termux/files/usr/bin/bash
# Script de instalação do Whisper.cpp para Termux
# Execute: bash install-whisper.sh

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        Instalação Whisper.cpp - PhoneAgent Voice          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Verificar se já existe
if [ -f "$HOME/whisper.cpp/main" ]; then
    echo "✓ Whisper.cpp já está instalado"
    echo ""

    # Verificar modelos
    if [ -f "$HOME/whisper.cpp/models/ggml-tiny.bin" ] || [ -f "$HOME/whisper.cpp/models/ggml-base.bin" ]; then
        echo "✓ Modelo já baixado"
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "✅ TUDO PRONTO!"
        echo "════════════════════════════════════════════════════════════"
        exit 0
    else
        echo "⚠ Modelo não encontrado, vou baixar..."
    fi
else
    echo "📦 Instalando dependências..."
    pkg install -y git make clang 2>&1 | grep -E "Installing|Upgrading|done" || true
    echo ""

    echo "📥 Clonando Whisper.cpp..."
    cd ~
    if [ -d "whisper.cpp" ]; then
        rm -rf whisper.cpp
    fi
    git clone --depth 1 https://github.com/ggerganov/whisper.cpp
    echo ""

    echo "🔨 Compilando Whisper.cpp (pode demorar 2-3 minutos)..."
    cd whisper.cpp
    make -j$(nproc)
    echo ""

    if [ ! -f "main" ]; then
        echo "❌ Erro: compilação falhou"
        exit 1
    fi

    echo "✓ Whisper.cpp compilado com sucesso"
    echo ""
fi

# Baixar modelo
cd ~/whisper.cpp

echo "📥 Baixando modelo Whisper..."
echo ""
echo "Escolha o modelo:"
echo "  1) tiny  - Rápido, ~75MB  (recomendado para testes)"
echo "  2) base  - Melhor, ~150MB (melhor qualidade)"
echo ""
read -p "Opção [1]: " OPCAO
OPCAO=${OPCAO:-1}

if [ "$OPCAO" = "2" ]; then
    MODEL="base"
else
    MODEL="tiny"
fi

echo ""
echo "Baixando modelo $MODEL..."
bash ./models/download-ggml-model.sh $MODEL

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ INSTALAÇÃO CONCLUÍDA"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Arquivos instalados:"
echo "  • Executável: ~/whisper.cpp/main"
echo "  • Modelo: ~/whisper.cpp/models/ggml-$MODEL.bin"
echo ""
echo "📊 Espaço usado:"
du -sh ~/whisper.cpp
echo ""
echo "🧪 Teste rápido:"
echo "   cd ~/Phone-Agent"
echo "   bash test-quick.sh"
echo ""
