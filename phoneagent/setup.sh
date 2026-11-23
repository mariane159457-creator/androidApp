#!/data/data/com.termux/files/usr/bin/sh
# Instala dependencias do phoneagent no Termux (versao ROOT: sem adb)
set -e
dpkg --configure -a 2>/dev/null || true  # conserta dpkg interrompido (builds mortos por timeout)
pkg update -y && pkg upgrade -y  # upgrade COMPLETO antes: instalar so 1 pacote novo causa 'library libplacebo not found' no ffmpeg
dpkg --configure -a 2>/dev/null || true
pkg install -y python python-pillow termux-api ffmpeg git cmake clang make curl
[ -d "$HOME/storage" ] || termux-setup-storage
chmod +x "$(dirname "$0")/agent.py"
HERE="$(cd "$(dirname "$0")" && pwd)"
# comando global (como o Claude Code): rode "phoneagent" ou "pa" de QUALQUER pasta; a pasta atual vira o diretorio de trabalho
for n in phoneagent pa; do
  printf '#!%s/bin/sh\nexec python "%s/agent.py" "$@"\n' "$PREFIX" "$HERE" > "$PREFIX/bin/$n" && chmod +x "$PREFIX/bin/$n"
done
echo "comando instalado: phoneagent / pa  (roda de qualquer pasta)"
cd "$HOME"  # git/cmake falham se a pasta atual estiver em ~/storage/shared

# whisper.cpp: transcricao offline dos audios (compila uma vez, pode demorar)
W="$HOME/whisper.cpp"
[ -d "$W" ] || git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$W"
[ -x "$W/build/bin/whisper-cli" ] || (cd "$W" && cmake -B build && cmake --build build -j2 --config Release)
[ -f "$W/models/ggml-base.bin" ] || (cd "$W" && sh ./models/download-ggml-model.sh base)

# root: faz o que antes precisava do adb (permissoes do Termux:API e nao deixar o Android matar o Termux)
set +e
SU=""
for p in /system/bin/su /system/xbin/su /sbin/su /debug_ramdisk/su /data/adb/ksu/bin/su /data/adb/magisk/su "$(command -v su)"; do
  [ -n "$p" ] && [ -x "$p" ] && SU="$p" && break
done
echo
if [ -n "$SU" ] && [ "$("$SU" -c 'unset LD_PRELOAD; id -u' 2>/dev/null)" = "0" ]; then
  echo "root: ok ($SU)"
  "$SU" -c 'unset LD_PRELOAD; pm grant com.termux.api android.permission.RECORD_AUDIO; pm grant com.termux.api android.permission.POST_NOTIFICATIONS; dumpsys deviceidle whitelist +com.termux; dumpsys deviceidle whitelist +com.termux.api' 2>&1 | tail -n 4
else
  echo "ATENCAO: root nao liberado. Abra o Magisk/KernelSU > Superusuario, permita o Termux e rode: su -c id"
fi
echo
echo "Modelos de nuvem (opcional, melhores p/ terminal): ollama signin && ollama pull gpt-oss:120b-cloud"
echo "Depois: python agent.py --pick-models   (escolhe modelo de tela + modelo de texto)"
echo "Falta so: app Termux:API instalado (mesma fonte do Termux) e o Ollama acessivel (export OLLAMA_HOST=IP:11434)."
echo "Teste: python agent.py --doctor"
echo "Uso:   cd ~/qualquer/pasta && pa \"baixe o ultimo release do X aqui e confira o hash\"   (usuario normal, NAO dentro do tsu)"
echo "       pa  (sem argumentos = modo interativo)   |   /init cria um PHONEAGENT.md com instrucoes da pasta"
