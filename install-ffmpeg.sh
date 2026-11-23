#!/data/data/com.termux/files/usr/bin/bash
#
# Script para instalar ffmpeg no Termux
# Execute: bash install-ffmpeg.sh
#

echo "════════════════════════════════════════════════════════════"
echo "Instalando ffmpeg - PhoneAgent Voice"
echo "════════════════════════════════════════════════════════════"
echo ""

# Verificar se já está instalado
if command -v ffmpeg &> /dev/null; then
    echo "✓ ffmpeg já está instalado"
    ffmpeg -version | head -1
    echo ""
    echo "🎉 Pronto para usar!"
    exit 0
fi

echo "Instalando ffmpeg..."
pkg install -y ffmpeg

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ ffmpeg instalado com sucesso!"
    ffmpeg -version | head -1
    echo ""
    echo "🎉 Pronto para usar!"
else
    echo ""
    echo "❌ Erro ao instalar ffmpeg"
    echo "   Tente manualmente: pkg install ffmpeg"
    exit 1
fi
