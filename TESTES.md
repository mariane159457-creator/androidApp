# Testes

## Local

Execute a partir da raiz:

```sh
bash test-quick.sh
```

A suite verifica parser/intencoes textuais, protecoes de arquivos, loop, Ollama simulado, busca web e os limites text-only/rootless. Nao acessa o dispositivo Android.

## Android / Termux

1. Configure um endpoint Ollama acessivel e execute `bash phoneagent/setup.sh`.
2. Rode `pa --doctor`.
3. Rode `pa "liste os arquivos daqui"` e confirme que o comando termina sem pedir root.
4. Confirme que `pa --help` nao oferece flags de microfone, transcricao ou visao.
5. Uma solicitacao para abrir/operar apps, ouvir audio ou alterar ajustes Android deve ser recusada, sem tela ou audio capturado.

Os testes do ambiente local nao validam rede, desempenho do Ollama nem permissoes especificas do aparelho.
