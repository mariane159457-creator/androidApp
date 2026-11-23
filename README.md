# PhoneAgent

Agente textual para Termux com shell, arquivos e ferramentas web. Ele executa como o usuario normal do Termux: nao usa root e nao tenta controlar a interface Android.

## Suporte

- Comandos de texto em linguagem natural ou comandos shell
- Leitura e escrita de arquivos, busca de caminhos, downloads e pesquisa web
- Ollama local ou remoto
- Protecoes contra escalada de privilegios e operacoes destrutivas

Voz, transcricao, leitura de audio de outros apps, automacao de tela, abertura de apps, compartilhamento pela interface e alteracao de ajustes Android foram removidos/desativados. Tarefas que precisem dessas capacidades serao recusadas; o agente nao tentara usar root como alternativa.

## Instalar no Termux

Requer Termux e um endpoint Ollama acessivel. No repositorio:

```sh
bash phoneagent/setup.sh
```

Se o Ollama estiver em outro dispositivo, configure `OLLAMA_HOST`, por exemplo `export OLLAMA_HOST=192.168.1.20:11434`, e selecione um modelo textual com `pa --pick-models`. Acesso a arquivos compartilhados do Android continua sujeito as permissoes normais do Termux.

## Usar

```sh
pa "liste os arquivos daqui"
pa "pesquise a documentacao oficial do Python sobre argparse"
pa
```

O modo interativo aceita `/cd`, `/pwd`, `/model`, `/status`, `/doctor` e `/help`. A pasta atual e o diretorio de trabalho. `--no-ollama-start` pode ser usado quando o endpoint ja e gerenciado externamente.

## Validar

```sh
bash test-quick.sh
```

No dispositivo, rode `pa --doctor` e depois uma tarefa simples de leitura. Os testes locais nao substituem essa verificacao com o Ollama configurado.
