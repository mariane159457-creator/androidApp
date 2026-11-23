# phoneagent v6

Agente de IA no Termux (root) que age como um "Claude Code" do celular: terminal + internet + tela.

## Uso (de qualquer pasta)
    cd ~/storage/downloads && pa "baixe o ultimo release do X aqui e confira o hash"
    pa                      # modo interativo (/cd /pwd /init /model /text /mode ...)
    pa "resuma @notas.txt"  # @arquivo vira o caminho absoluto
    echo "tarefa" | pa      # sem supervisao (nao pergunta nada)

A pasta atual e o diretorio de trabalho. `PHONEAGENT.md` / `AGENTS.md` / `CLAUDE.md` (na pasta ou acima) e
`~/.phoneagent/PHONEAGENT.md` (global) sao lidos em toda tarefa.

## v6: mais inteligente (brain.py, tem que ficar na mesma pasta do agent.py)
- **Atalhos de intencao (sem modelo, sem Termux:API):** "coloque um alarme as 9", "me acorde 7h30 de seg a sex chamado academia", "timer de 10 min",
  "volume 40%", "ligue o wifi", "brilho no maximo", "abra o youtube" sao entendidos por um parser PT-BR/EN e executados por intents do Android via root
  (`am start -a SET_ALARM ...`), **verificados** (lista do app Relogio / `settings get`). "no app" abre o Relogio ja no alarme criado. Pedidos
  ambiguos ou com 2 tarefas ("ligue o wifi e abra o chrome") continuam com o modelo. `--no-fast` ou `/fast off` desliga.
- **Acoes novas para o modelo:** `set_alarm`, `set_timer`, `device` (wifi/bluetooth/dados/aviao/nao perturbe/rotacao/brilho/volume), `time_picker_set`
  (preenche o dialogo "Selecionar horario": Hora e Minuto com 2 digitos, confere e aperta OK; foi onde o agente travava).
- **Musica:** detecta titulo + artista e controles simples sem planejar com LLM. Prefere YouTube Music; tenta primeiro o intent Android `MEDIA_PLAY_FROM_SEARCH` e so confirma com a sessao ativa do app,
  titulo e artista correspondentes. Se o intent nao iniciar a faixa certa, abre a busca oficial para selecao visual; abrir a busca, sozinho, NAO significa que a musica comecou.
  Pausa/retomada/proxima faixa usam teclas de midia e so confirmam com estado/metadado observado.
- **Acha erros:** todo resultado com falha ganha `[DIAGNOSIS]` (comando nao existe, precisa de root, intent inexistente, modulo Python, rede, disco, timeout...).
  A tela ganha `SCREEN FINDINGS` (erro visivel, campo obrigatorio vazio, seletor de horario aberto, app travado).
- **Aprende com eles:** abordagem que falhou 2x vira *beco sem saida* bloqueado (`force` libera). Termux:API que trava/nao existe = `termux-*` bloqueado
  e o agente usa os equivalentes de root. Tela parada: escada de estrategias diferentes + resgate por codigo (seletor de horario).
- **Memoria entre tarefas:** `~/.phoneagent_lessons.json`. Tarefa dificil -> o modelo de texto extrai ate 3 licoes; senao o codigo pareia
  "o que falhou -> o que funcionou". Licoes parecidas entram no prompt. `/lessons`, `/learn TEXTO`, `/forget N|all`, `--learn`, `--lessons`.
  `PA_NO_REFLECT=1` desliga a reflexao por modelo.
- Teste: `python tests/test_brain.py`

## v5: quem decide o que (o que mudou)
- **Terminal por padrao.** O pedido e classificado antes de comecar (`task_kind`): so vira "tela" se falar claramente de app, site,
  login, toque etc. Empate = terminal. `/mode terminal|screen` (ou `--mode`) forca.
- **Tarefa de terminal** (listar, ler, baixar, instalar, zipar, pesquisar...): so o **modelo de texto** (ex.: gpt-oss) decide, sem screenshot,
  e o agente **nunca sai do Termux** (home/back sao bloqueados, nada de `open_app termux`). A saida do comando aparece completa (ate 30 linhas)
  e a resposta final traz o conteudo de verdade.
- **Consulta curta so de leitura** ("liste os arquivos daqui", "qual a versao do python"): modo rapido, sem planejador e sem auditor.
- **Tarefa de tela** (app/site): o **modelo de visao** (ex.: gemma) decide, com um prompt enxuto. Nao aperta HOME antes: vai direto
  com `open_url` (palavras soltas viram busca no Google) ou `open_app`.
- **Escalada automatica:** se uma tarefa de terminal precisar mesmo da tela (ex.: enviar no Drive), o primeiro toque/open_app passa o
  controle para o modelo de visao sozinho; ao terminar, o Termux volta para a frente.
- `type` agora aceita `"index"` (toca no campo antes), `"submit":true` (Enter no fim) e acha sozinho o campo de texto se nada estiver em foco
  (antes digitava no vazio e repetia em loop).
- Visual simples: uma linha por passo (`● Acao(args)  modelo 2s`), sem caixas; resultado final sem corte.

## Seguranca (por codigo, o modelo nao consegue burlar)
- So apaga/sobrescreve o que o PROPRIO agente criou. Arquivo alheio = pergunta `[s/N]` ao humano (sem resposta = nao).
  `force` nao vale para isso. `rm -rf ~`, `/sdcard`, `/data`... sao bloqueados sempre.
- Temporarios vao em `$PA_TMP` (apagado sozinho no fim, mesmo com Ctrl+C/erro). Sobras `*_tmp`/`*extracted*` criadas por ele tambem.
- `done` com `deliverables` e verificado; o relatorio final mostra arquivos reais e tamanhos.
- Nunca paga, instala/desinstala ou apaga dados sem o pedido dizer isso. Senha/captcha/codigo SMS = pergunta ao humano.

## Ollama automatico
Se o Ollama nao estiver rodando, o `pa` sobe o `ollama serve` sozinho e ENCERRA ao terminar (so se foi ele que subiu; um Ollama seu nunca e derrubado; com varios `pa` abertos, cai quando o ultimo sai).
`--keep-ollama` deixa rodando, `--no-ollama-start` desliga o autostart. Log: ~/.phoneagent_logs/ollama-serve.log

## Flags
`--no-ask` (nunca perguntar: nega pedidos sobre arquivos alheios), `--keep-tmp` (nao apagar $PA_TMP, para depurar),
`--route hybrid` (visao so descreve, texto decide; o `auto` ja usa texto no terminal e visao na tela), `--pick-models` (trocar modelos).
Busca web usa DuckDuckGo/Bing; com `OLLAMA_API_KEY` usa a busca da Ollama primeiro.

## Testes
    python tests/test_guards.py && python tests/test_web.py && python tests/test_loop.py && python tests/test_ollama.py && python tests/test_route.py && python tests/test_brain.py
Usam so /tmp/pa_test_home* (nao tocam no seu celular). `test_route` cobre o roteamento terminal x tela, sem HOME, sem screenshot em
terminal, escalada para o gemma, `type` com foco e `open_url`.
