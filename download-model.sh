#!/data/data/com.termux/files/usr/bin/bash
# Script para baixar modelo Whisper (Whisper.cpp já está compilado)

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Download de Modelo Whisper - PhoneAgent          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Verificar se whisper.cpp existe
if [ ! -d "$HOME/whisper.cpp" ]; then
    echo "❌ Erro: whisper.cpp não encontrado em ~/whisper.cpp"
    exit 1
fi

# Verificar se já está compilado
if [ -f "$HOME/whisper.cpp/build/bin/main" ]; then
    echo "✓ Whisper.cpp já está compilado"
elif [ -f "$HOME/whisper.cpp/main" ]; then
    echo "✓ Whisper.cpp já está compilado (caminho antigo)"
else
    echo "❌ Erro: Whisper.cpp não está compilado"
    echo ""
    echo "Execute para compilar:"
    echo "  cd ~/whisper.cpp"
    echo "  make"
    exit 1
fi
echo ""

# Verificar se já tem modelos
echo "📋 Verificando modelos existentes..."
if [ -f "$HOME/whisper.cpp/models/ggml-base.bin" ]; then
    SIZE=$(du -h "$HOME/whisper.cpp/models/ggml-base.bin" | cut -f1)
    echo "✓ Modelo BASE já existe ($SIZE)"
    HAS_BASE=1
else
    echo "  Modelo BASE não encontrado"
    HAS_BASE=0
fi

if [ -f "$HOME/whisper.cpp/models/ggml-tiny.bin" ]; then
    SIZE=$(du -h "$HOME/whisper.cpp/models/ggml-tiny.bin" | cut -f1)
    echo "✓ Modelo TINY já existe ($SIZE)"
    HAS_TINY=1
else
    echo "  Modelo TINY não encontrado"
    HAS_TINY=0
fi
echo ""

# Se já tem ambos, perguntar se quer baixar outro
if [ $HAS_BASE -eq 1 ] && [ $HAS_TINY -eq 1 ]; then
    echo "════════════════════════════════════════════════════════════"
    echo "✅ Todos os modelos já estão instalados!"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "Modelos disponíveis:"
    echo "  • ~/whisper.cpp/models/ggml-base.bin"
    echo "  • ~/whisper.cpp/models/ggml-tiny.bin"
    echo ""
    read -p "Deseja baixar outro modelo? [N/s]: " RESPOSTA
    if [ "$RESPOSTA" != "s" ] && [ "$RESPOSTA" != "S" ]; then
        echo ""
        echo "✓ Pronto para usar!"
        exit 0
    fi
fi

# Menu de seleção
echo "📥 Escolha o modelo para baixar:"
echo ""
echo "  1) tiny  - Rápido, ~75MB, latência ~0.5s"
echo "             (Recomendado para testes e uso diário)"
echo ""
echo "  2) base  - Melhor qualidade, ~150MB, latência ~1.5s"
echo "             (Melhor transcrição, mais lento)"
echo ""
echo "  3) small - Alta qualidade, ~500MB, latência ~3s"
echo "             (Uso avançado)"
echo ""

if [ $HAS_TINY -eq 0 ]; then
    DEFAULT=1
elif [ $HAS_BASE -eq 0 ]; then
    DEFAULT=2
else
    DEFAULT=1
fi

read -p "Opção [$DEFAULT]: " OPCAO
OPCAO=${OPCAO:-$DEFAULT}

case $OPCAO in
    1)
        MODEL="tiny"
        ;;
    2)
        MODEL="base"
        ;;
    3)
        MODEL="small"
        ;;
    *)
        echo "❌ Opção inválida"
        exit 1
        ;;
esac

# Baixar modelo
echo ""
echo "📥 Baixando modelo $MODEL..."
echo "   (Isso pode demorar alguns minutos dependendo da internet)"
echo ""

cd ~/whisper.cpp/models

if bash ./download-ggml-model.sh $MODEL; then
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "✅ MODELO INSTALADO COM SUCESSO"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "Modelo instalado:"
    ls -lh ggml-$MODEL.bin
    echo ""
    echo "📊 Espaço usado pelos modelos:"
    du -sh ~/whisper.cpp/models/*.bin 2>/dev/null | grep -v for-tests || echo "  Apenas modelos de teste"
    echo ""
    echo "🧪 Próximo passo:"
    echo "   cd ~/Phone-Agent"
    echo "   bash test-quick.sh"
    echo ""
else
    echo ""
    echo "❌ Erro ao baixar modelo"
    echo ""
    echo "Tente manualmente:"
    echo "  cd ~/whisper.cpp/models"
    echo "  bash ./download-ggml-model.sh $MODEL"
    exit 1
fi
