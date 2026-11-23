#!/data/data/com.termux/files/usr/bin/sh
set -eu

pkg install -y python git curl
HERE="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$HERE/agent.py"
mkdir -p "$PREFIX/bin"
for name in phoneagent pa; do
  printf '#!%s/bin/sh\nexec python "%s/agent.py" "$@"\n' "$PREFIX" "$HERE" > "$PREFIX/bin/$name"
  chmod +x "$PREFIX/bin/$name"
done

printf '\nPhoneAgent textual instalado: phoneagent / pa\n'
printf 'Sem root, microfone ou controle de tela. Configure OLLAMA_HOST se o Ollama estiver em outro dispositivo.\n'
printf 'Diagnostico: phoneagent --doctor\n'
printf 'Exemplo: pa "liste os arquivos desta pasta"\n'
