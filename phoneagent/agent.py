#!/usr/bin/env python3
"""phoneagent v4 (root): agente de IA que controla o Android via ROOT/su (Termux, sem ADB) usando Ollama.

Uso:
  python agent.py "faca a atividade aberta no busuu"
  python agent.py                      # modo interativo
  python agent.py --doctor             # confere dependencias
  python agent.py --test-audio         # testa gravacao + transcricao (toque um audio)

Versao root: toques, teclas, tela, apps e permissoes rodam via su (nada de adb). shell aceita "root":true.

Novidades da v2:
  * Audio: grava o MICROFONE *antes* de dar play (nao perde audios curtos), espera o audio terminar,
    converte e transcreve com whisper.cpp (local, gratis, offline). Legenda ao vivo vira so plano B.
  * Detecta video/audio com autoplay: espera acabar e repete do inicio.
  * Textos longos: acao read_all rola a tela sozinha e devolve o texto completo.
  * Telas sem arvore de UI (Flutter, jogos, video): screenshot com GRADE (A1..F12) para tocar com precisao.
  * zoom em regioes pequenas, scroll mais natural, JSON mais tolerante, keep_alive no Ollama.
  * Terminal: shell, read_file, write_file, send_file (comandos e arquivos do Termux, sem depender da tela).
Novidades da v4 (como um Claude Code para o celular):
  * Roda de QUALQUER pasta (comando `phoneagent`/`pa`): a pasta atual e o diretorio de trabalho; le PHONEAGENT.md/AGENTS.md/CLAUDE.md.
  * SEGURANCA POR CODIGO: so apaga/sobrescreve o que o proprio agente criou; arquivos alheios exigem OK do humano (force nao burla).
  * Pasta temporaria propria ($PA_TMP) apagada sozinha no fim + faxina de temporarios criados: nada de arquivos soltos.
  * Internet: web_search, web_fetch, download (com retomada). Pesquisa e baixa sozinho.
  * Honestidade: relatorio final MEDIDO pelo sistema (arquivos reais, tamanhos); done com deliverables e verificado.
  * Mais rapido: shell em lote (cmds), prompt enxuto p/ terminal, sem espera apos comandos, raciocinio leve nos passos simples.
Somente biblioteca padrao do Python (Pillow opcional, mas recomendado).
"""
import argparse
import base64
import glob
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import signal
import zipfile
import atexit
import struct
import subprocess
import sys
import textwrap
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain  # v6: atalhos de intencao, diagnostico de erros, licoes persistentes (arquivo brain.py, ao lado deste)

HOME = os.path.expanduser("~")
os.makedirs(HOME, exist_ok=True)
HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
if "://" not in HOST:  # OLLAMA_HOST=IP:11434 (sem http://) tambem vale
    HOST = "http://" + HOST
if not HOST.startswith("http"):
    HOST = "http://" + HOST
HOST = HOST.rstrip("/")
CFG = os.path.join(HOME, ".phoneagent_model")  # legado (so o modelo principal)
CFG_JSON = os.path.join(HOME, ".phoneagent.json")  # {"vision_model": ..., "text_model": ...}
LOG_DIR = os.path.join(HOME, ".phoneagent_logs")
UI_TMP = "/data/local/tmp/pa_ui.xml"
WORK = os.path.join(HOME, ".phoneagent_tmp")
SHOTS = os.path.join(HOME, "phoneagent_shots")
BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
IME_PKG_RE = re.compile(r"inputmethod|honeyboard|swiftkey|\.ime\b|keyboard", re.I)
CHIP_SKIP_RE = re.compile(r"(continu|verificar|check|next|avan[cç]ar|mostrar|show |fechar|close|toque nas palavras|tap the words|tap words)")
IME_WIN_RE = re.compile(r"Window #\d+ Window\{[0-9a-f]+ u\d+ InputMethod\}:")
IME_NEXT_RE = re.compile(r"\n  Window #\d+ Window\{")
IME_REGION_RE = re.compile(r"touchable region=SkRegion\(\((\d+),(\d+),(\d+),(\d+)\)\)")
SKIP_GATE_RE = re.compile(r"(continu|next|avan[cç]ar|mostrar texto|show text|fechar|close|voltar|navegar|dispensar|pular|skip|verificar|check)")
# ~/storage/downloads (sem barra final) e um symlink: "ls -F ~/storage/downloads" lista o LINK, nao a pasta
STORAGE_RE = re.compile(r"((?:~|\$HOME|\$\{HOME\}|" + re.escape(HOME) + r")/storage/(?:shared|downloads|dcim|pictures|movies|music|documents))(?=[\s;|&)]|$)")
ABS_ZIP_RE = re.compile(r"^(data/data/|data/user/|storage/(emulated|self)/|sdcard/|/)")
SKIP_DIRS = {"Android", ".git", "node_modules", "__pycache__", ".cache", ".npm", "whisper.cpp"}
NOCOMPRESS = (".apk", ".zip", ".mp4", ".mkv", ".jpg", ".jpeg", ".png", ".gz", ".7z", ".mp3", ".m4a", ".webp")
SAFE_TEXT = re.compile(r"^[A-Za-z0-9 .,@_\-+=:/?!#]*$")
GRID_COLS, GRID_ROWS, COLS = 6, 12, "ABCDEF"
# exercicios "Select N words that ...": os chips ficam parados e a selecao so aparece como borda azul
NUM_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                         "fifteen sixteen seventeen eighteen nineteen twenty".split())}
NUM_WORDS.update({"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "três": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
                  "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12})
SELECT_VERB_RE = re.compile(r"\b(select|choose|pick|highlight|underline|find|identify|mark|selecione|escolha|marque|destaque|encontre)\b")
SELECT_N_RE = re.compile(r"\b(\d{1,2}|" + "|".join(sorted(NUM_WORDS, key=len, reverse=True)) + r")[\s-]+(?:words?|palavras?)\b")
SEL_RATIO = 0.55  # fracao do contorno do chip que precisa estar azul para contar como selecionado
PNG_SIG = b"\x89PNG\r\n\x1a\n"
BUILD = "2026-10-29-v6"  # mude a cada entrega para confirmar no log que o arquivo certo esta rodando
STOP_WORDS = set("""a o os as um uma de do da dos das e em no na nos nas para por com sem que se ao aos entre sobre the and for with
from into that this then also use using app apps application baixe baixar baixa download install instale instalar abra abrir abre open
entrar acesse acessar acessa ir va vai faca fazer tarefa task site pagina page quero want please favor tambem gratuito gratis free
ate ver veja verifique mande mandar envie enviar algum alguma qualquer deep""".split())
TERM_KINDS = ("shell", "read_file", "write_file", "send_file", "find_path", "zip_items", "web_search", "web_fetch", "download",
              "set_alarm", "set_timer", "device")
SKIP_OBS = ("shell", "read_file", "write_file", "find_path", "zip_items", "web_search", "web_fetch", "download", "set_alarm", "set_timer", "device")  # apos estas acoes a tela nao e capturada (mais rapido)
TERM_ALIAS = {"sh": "shell", "bash": "shell", "terminal": "shell", "cmd": "shell", "exec": "shell", "run": "shell",
              "cat": "read_file", "readfile": "read_file", "writefile": "write_file", "write": "write_file",
              "save_file": "write_file", "share": "send_file", "share_file": "send_file", "sendfile": "send_file",
              "search": "web_search", "google": "web_search", "websearch": "web_search", "fetch": "web_fetch", "browse": "web_fetch",
              "open_page": "web_fetch", "wget": "download", "dl": "download", "download_file": "download"}
DELIVERY_RE = re.compile(r"(drive|envi|send|upload|whatsapp|e-?mail|gmail|mande|compartilh|share|telegram|anex|attach)")
DANGER_RE = re.compile(r"(\b(rm|rmdir|unlink|shred|truncate|dd|mkfs\w*|reboot|shutdown|su|sudo|pkill|killall|mount|umount|setprop|resetprop|setenforce|iptables|fastboot|magisk|ksud)\b|\bkill\s+-9|-delete\b|"
                       r"\b(pm|adb)\s+(uninstall|clear|disable\S*|hide|suspend)|\bcmd\s+package\s+(uninstall|clear)|\bpkg\s+(uninstall|remove|purge)|\bapt(-get)?\s+(remove|purge)|\bchmod\s+-\w*R|"
                       r"\bchown\s+-\w*R|\b(curl|wget)\b[^|;&]*\|\s*(ba|z)?sh\b)")

# ---- deteccao de instalacao de pacotes (pkg/apt/apt-get/pip), para nao repetir instalacoes ja resolvidas na tarefa
INSTALL_RE = re.compile(r"\b(?:pkg|apt-get|apt)\s+(?:install|add)\s+((?:-\S+\s+)*[^&;|\n]+)")
PIP_INSTALL_RE = re.compile(r"\bpip[23]?\s+install\s+((?:-\S+\s+)*[^&;|\n]+)")
PKG_OK_RE = re.compile(r"already the newest version|requirement already satisfied|setting up |successfully installed|unpacking ", re.I)
PKG_MISSING_RE = re.compile(r"unable to locate package|is not available|no matching distribution|could not find a version|"
                            r"no mirror or mirror group selected", re.I)
# pacotes que o modelo tenta instalar por habito (vindo de Debian/Ubuntu) mas que nao existem/nao fazem sentido no Termux
TERMUX_PKG_HINTS = {
    "python-dev": "nao existe no Termux: os headers do Python ja vem com o pacote 'python' (o mesmo que o pip usa). Nao tente instalar isso de novo.",
    "python3-dev": "nao existe no Termux, mesmo motivo do python-dev: os headers ja vem com o pacote 'python'.",
    "pip": "o Termux proibe atualizar o pip (quebra o pacote python-pip). Use o pip como esta, sem --upgrade pip.",
    "build-essential": "nao existe no Termux (e um meta-pacote so de Debian/Ubuntu). Instale os pacotes um a um: clang make binutils.",
    "libssl-dev": "no Termux o pacote se chama 'openssl' (ja inclui os headers), nao 'libssl-dev'.",
    "libffi-dev": "no Termux o pacote se chama 'libffi', nao 'libffi-dev'.",
}

APPS = {
    "whatsapp": "com.whatsapp", "whatsapp business": "com.whatsapp.w4b",
    "chrome": "com.android.chrome", "youtube": "com.google.android.youtube",
    "instagram": "com.instagram.android", "telegram": "org.telegram.messenger",
    "gmail": "com.google.android.gm", "maps": "com.google.android.apps.maps",
    "configuracoes": "com.android.settings", "settings": "com.android.settings",
    "facebook": "com.facebook.katana", "messenger": "com.facebook.orca",
    "tiktok": "com.zhiliaoapp.musically", "spotify": "com.spotify.music",
    "play store": "com.android.vending", "x": "com.twitter.android",
    "twitter": "com.twitter.android", "camera": "com.android.camera",
    "busuu": "com.busuu.android.enc", "duolingo": "com.duolingo",
}

# elementos que parecem player de audio/video (nao inclui "progress": toda tela tem barra de progresso)
MEDIA_RE = re.compile(r"(seekbar|(?<![a-z])(play|pause|replay|audio|video|v[ií]deo|listen|ouvir|escutar|reprodu|assistir|watch|speaker|sound|player|exo_))")
# toque nestes elementos vira play_and_read automatico ("pause" fica de fora de proposito)
AUDIO_RE = re.compile(r"(?<![a-z])(play|replay|audio|listen|sound|speaker|ouvir|escutar|reprodu)")
HALLUCINATIONS = {"thank you", "thanks for watching", "you", "bye", "obrigado", "tchau", "thank you for watching",
                  "legendas pela comunidade amara org", "subtitles by the amaraorg community"}

OPEN_MEDIA_RE = re.compile(r"(show video|watch video|play video|open video|watch again|ver v[ií]deo|mostrar v[ií]deo|assistir)")
PLAY_RE = re.compile(r"(?<![a-z])(play|reproduzir|reproduce|iniciar|start)(?![a-z])")
FEEDBACK_RE = re.compile(r"^(correct|incorrect|wrong|right|great|excellent|certo|errado|correto|incorreto|muito bem|parab)")
DONE_RE = re.compile(r"(lesson (is )?complete|you('ve| have) (completed|finished)|congratulations|well done|great job|parab[eé]ns|"
                     r"li[cç][aã]o (conclu|finaliz)|conclu[ií]d[oa]|session complete|all done|you did it|lesson finished)")
LOCATE_PROMPT = (
    "This is a phone screenshot with a red grid (columns A-F, rows 1-12). Look for a media control that STARTS an audio/video "
    "that is not playing yet: a PLAY button (triangle, often in a circle) or a replay arrow. "
    'Reply JSON {"state":"play_button|already_playing|none","cell":"C11"}. '
    "state=already_playing if you see a PAUSE icon (two vertical bars) or the media is clearly playing. "
    "state=none if there is no media player/control at all, or only a button that opens a video (e.g. 'Show video') but no player. "
    "cell = grid cell containing the CENTER of the play button (only for play_button)."
)
REFINE_PROMPT = (
    "Zoomed crop of a phone screen with a red 6x6 grid (columns A-F, rows 1-6). Which single cell contains the CENTER of the "
    'PLAY button (triangle in a circle)? Reply JSON {"cell":"B3"}.'
)

TRANSCRIBE = (
    "These are phone screenshots taken a second or two apart while an audio or video was playing. "
    "Extract ONLY the text that reproduces the speech: the system Live Caption box, video subtitles, or an in-app "
    "transcript that appeared during the audio. Ignore buttons, titles, questions and answer options. "
    'Reply with JSON {"captions":["text, in chronological order, no duplicates"]}. Use an empty list if there is no such text.'
)
OCR_PROMPT = ("Transcribe ALL the readable text on this phone screenshot exactly as written, top to bottom, "
              "one block per line. Ignore the grid lines and the cell labels (A1..F12). Output only the text.")

SYSTEM = """You control a ROOTED Android phone (commands run as root through su), acting like a careful, patient human user (any app: lessons, quizzes, chats, settings, browsers, video apps...).
Each turn you receive the TASK, NOTES, SESSION MEMORY (what was already captured/done), RECENT ACTIONS and the current SCREEN (UI elements with an index, usually plus a screenshot).
Reply with ONE JSON object and nothing else: {"thought":"short reasoning","action":"<name>", ...params} — params go directly at the TOP level of the object, never nested inside a "params" key.
Optional extra fields you can add to ANY action: "done_goals":[1,2] (numbers of PLAN goals that are now finished), "fact":"short durable fact you just verified (e.g. 'Proton VPN is connected', 'Tor Browser is installed')", "plan":["goal 1","goal 2"] (replace the plan if it is wrong), "notes":"...".

Actions:
- tap {"index":N}                 tap UI element N from the list
- tap_cell {"cell":"C7"}          tap a cell of the red grid drawn on the screenshot (columns A-F, rows 1-12). Optional "fx","fy" (0-1) = position inside the cell. Use when the element is not in the list
- tap_xy {"x":0-1000,"y":0-1000}  normalized screenshot position, (0,0)=top-left. Less precise than tap_cell
- long_press {"index":N}
- type {"text":"...","clear":false}   type into the focused field (tap the field first). clear=true erases it first
- type {"file":"~/path/file.txt"}   types/pastes the WHOLE content of a file into the focused field (use for long texts: NEVER retype long text yourself)
- enter                            press Enter / search / send key
- order_words {"words":["Never","before","have","so many"]}   word-chip exercises (put the words in order / build the sentence): taps the chips in that order itself and verifies the box. YOU decide the order from the instruction and the evidence (text/audio); chip texts EXACTLY as on screen. Then press Check/Continue yourself
- select_words {"words":["my","family,","my","beliefs","my","community."]}   "Select N words ..." / highlight exercises (the chips STAY in place and a selected chip only gets a blue border): selects exactly those chips, in READING ORDER, repeated words allowed (it picks the right "my" itself), deselects wrong ones and verifies the result by reading the screen. Optional "indexes":[..] instead of words. Then press Continue/Check yourself
- hide_keyboard                    close the on-screen keyboard to see what is under it
  After typing in a field, the on-screen keyboard hides buttons below it. To submit a login/search field prefer enter (IME Next/Go key); a tap on a covered button hides the keyboard first and is not executed.
- scroll {"direction":"down|up","times":1}   direction = where you want to go in the content. "down" reveals content BELOW. Optional "index" of a scrollable element
- swipe {"direction":"up|down|left|right"}   raw finger swipe (carousels, "left" = next page). To read, use scroll
- back | home
- open_app {"app":"whatsapp"}
- open_url {"url":"https://..."}
- wait {"seconds":N}               use for loading spinners
- read_all                         scrolls through the whole screen content by itself and returns ALL its text. Leaves the screen at the END of the content
- zoom {"x1":0-1000,"y1":0-1000,"x2":0-1000,"y2":0-1000}   next turn you also get a magnified crop (small text, small images)
- play_and_read {"index":N | "cell":"B5" | "x":..,"y":..}   records the real sound from the microphone and transcribes it, until the audio ENDS (works for 1-2+ minute audios). Target = the play/replay control, OR a "Show video" button, OR the picture/video area. The tool itself finds and presses the play button if the tap only opened a player. Omit the target to only record
- listen                           record the microphone (no tap) until the sound ends and transcribe it
- speak {"text":"..."}
- shell {"cmd":"ls -la ~/storage/downloads","timeout":30}   run a command in the TERMUX terminal (sh). FAST, no screen needed. "cd" persists between calls (the result shows the cwd).
  Add "root":true to run it AS ROOT with Android tools first in PATH (pm, am, dumpsys, cmd, settings, getprop, and access to /data/...). With root:true "cd" does NOT persist (use absolute paths; "~" is still the Termux home). Never write su/sudo yourself: use root:true. Use it to navigate, list, find/grep files, cp/mv, zip/unzip, curl, run python, git, pkg... Stdin is closed: never run interactive programs (use -y and similar flags)
  pkg/apt/apt-get/pip install commands are checked automatically BEFORE they run: a package already confirmed installed earlier in this task returns "SKIPPED (not executed)" without running anything (do not repeat it); a package that already failed as unavailable returns "BLOCKED (not executed)" (find the correct package name instead of retrying the same one); a few Debian-only names that do not exist on Termux (python-dev, python3-dev, build-essential, libssl-dev, libffi-dev) are blocked immediately with the correct alternative. Trust these results and move on instead of re-checking "is X already installed?" yourself.
- find_path {"name":"jailbreak"}   locate a file/folder by name (case-insensitive, partial ok) in Termux home and phone storage; returns REAL paths. Use it instead of guessing with ls/find
- zip_items {"items":["~/phoneagent","~/btc-finder-main","~/storage/downloads/JAILBREAK"],"name":"backup"}   builds ONE zip with clean relative names, a unique timestamped name, saved in ~/storage/downloads/ (visible to the Drive picker), then verifies it. Items may be just names (case-insensitive lookup). PREFER this over the zip command
- tap_text {"text":"tiktok_mod.apk"}   re-reads the screen RIGHT NOW and taps the element whose text/description is exactly that (falls back to partial). Safer than "index" in lists that load/reorder (file pickers, search results)
- read_file {"path":"~/notes.txt","max_chars":6000}   read a text file
- write_file {"path":"~/notes.txt","content":"...","append":false}   create/write a text file. Refuses to overwrite an existing file unless append=true (or force=true)
- send_file {"path":"~/storage/downloads/doc.pdf"}   opens the Android share sheet with that file (Termux:API). Then finish with SCREEN actions: pick the app (WhatsApp...), the contact, tap Send
- screen                           capture the phone screen on the next turn (after shell/read_file/write_file the screen is NOT captured, to save time)
- ask_user {"question":"..."}      ask the human when you lack information (login, captcha, payment, ambiguous task)
- done {"message":"what was accomplished"}
- fail {"message":"why it cannot be done"}
Any action blocked by the system can be repeated with an extra "force":true, but only when you are sure it is needed.

Rules:
- Exactly one action per turn. The screen is refreshed after each action; element indexes change every turn.
- First understand the screen type (lesson, quiz, chat, form, settings...). Look at the screenshot: pictures, videos, players, icons and text inside images matter.

PRECISION (no guessing, nothing missing):
- First list for yourself EVERY deliverable the TASK needs (each folder, file, upload, recipient, setting). Each is its own goal; none may be skipped or merged.
- Never act on a guess when a cheap check exists: confirm sources exist (ls), confirm results (ls -l, unzip -l, sizes), confirm the screen shows the expected state after each critical tap.
- Archives: use zip_items (all folders of the request in ONE call, exact names from find_path). Never use the zip command with absolute paths (it stores data/data/com.termux/... inside). Read the result and fix every WARNING before going on.
- FILES YOU PREPARED lists the exact names. FILES YOU PREPARED also shows each file's FULL PATH: never guess a path, never re-copy or re-zip a file that is already listed. In file pickers (Drive upload, share, attach) select ONLY the wanted file with tap_text and its exact name: read the file name in the list/dialog BEFORE confirming. Older files with similar names (backup_*.zip, full_backup.zip...) are NOT yours. If the list is long, use the picker's search box and type the exact file name.
- Several files to upload/send: ONE AT A TIME; after each, verify it appears at the destination (Drive list, chat) by name; then the next. Never upload the same file twice. A single upload does not finish the task.
- APK of an installed app: pm path <pkg> can list several APKs (base + splits): copy ALL. If two packages match the app (e.g. X and X.go), find out which one the user uses (shell root:true: pm list packages -3; dumpsys package <pkg> | grep -E 'versionName|lastUpdateTime'); if unsure include both and say so. Big APKs (hundreds of MB) take time: wait for the upload to really complete.
- Before done: check each goal with evidence (command output or what the screen shows). In "message" list every item with its result (file name, size, destination). If something is missing, keep working or state exactly what is missing. Never claim what you did not verify: the system audits your done and rejects it when items are unproven.

ANSWERING QUESTIONS (lessons, quizzes, forms): NEVER guess.
- Before tapping an answer, your "thought" must name the EVIDENCE: a quote from the question/screen text, a captured transcript (Tn) that states the exact fact asked (name, number, opinion), or a rule you are certain of (grammar). "usually", "probably", "the context suggests" or "the transcript seems cut" is NOT evidence.
- Evidence missing: get it first (scroll, read_all, zoom, or replay the audio/video with "force":true). If the speech never states the fact, the answer is not in it.
- Still missing or ambiguous after that: call ask_user with the question and the options. Do not tap an option just because it is first, longest or sounds positive.
- An "Incorrect" screen reveals the right answer, but it counts as an error: report the final score and the errors in the done message.

KEYBOARD AND TYPED ANSWERS:
- An open keyboard hides the lower part of the screen (answer field, options, Continue). The SCREEN block says KEYBOARD OPEN. Type, then call hide_keyboard and read the screen again to VERIFY the field text before submitting. Never submit or choose on a screen you cannot fully see.
- Typed answers: the field is cleared automatically; adapt the form to the blank (plural, tense, article) and copy words exactly as in the text/audio.

LISTEN BEFORE YOU ANSWER (audio/video questions):
- A question with its own player / "Show video" / Listen control (e.g. "Create the reporting sentence", "what does X say", "match statements about the conversation") must be answered from what you HEARD for THIS question: play_and_read first, unless a transcript Tn or visible text already STATES the fact. Skip the audio only when you are CERTAIN; then quote the evidence in thought and add "force":true. If capture fails twice, ask_user.
- Word-order / sentence-building chip exercises: use order_words with the chip texts in the right order (exactly as on screen). It taps each chip, re-reads the screen after every tap and verifies the box, then you press Check. Do NOT tap chips one by one yourself (they move after each tap; tapping a word inside the box removes it).

SELECT / HIGHLIGHT EXERCISES ("Select six words that form a tricolon", "Select the nine-word noun phrase", "Select the words that show hedging"):
- The sentence is shown as chips that do NOT move. The element list marks chosen chips with [SELECTED] and a SITUATION line says how many words are required. NEVER tap them one by one (tapping a selected chip removes it) and NEVER use order_words here: use select_words ONCE with the chip texts in reading order.
- The number in the instruction is EXACT. Count your list before sending it. Chips need not be contiguous: leave out connectors (and, or, commas) when the count only fits without them.
- Decide the words from the instruction and the sentence on screen, never from audio unless the question is about it. Quick definitions:
  tricolon = three parallel items of similar form in a row (e.g. "my family, my beliefs and my community": the six words are the three repeated pairs my family / my beliefs / my community, 'and' left out); anaphora = same word(s) opening successive phrases; parallelism = same grammatical pattern repeated; noun phrase = a noun plus its determiners/modifiers/of-phrases (no finite verb of its own); relative clause = starts with who/which/that/whose/where; hedging = softeners (seems, might, tends to, arguably, to some extent); cleft = It is/was ... that/who ... or What ... is ...; fronting/inversion = a normally later element moved to the start (Never have I..., Rarely does ...); nominalisation = verb/adjective turned into a noun (decide -> decision); reporting verb = say/claim/suggest/admit...; contrast/concession markers = although, whereas, however, despite; discourse markers = on the other hand, in addition, as a result.
- After select_words says ok, tap Continue/Check, read the feedback, and move on. If the feedback is Incorrect and shows the right answer, note it and continue.

OTHER EXERCISE TYPES (identify the type FIRST, then use the matching action):
- Word order / build the sentence from a tray of chips that MOVE into an answer box -> order_words.
- Fill the blanks with chips -> tap the chips in blank order and verify every blank is filled.
- Matching two columns -> tap one item on the left, then its partner on the right, re-read the screen after each pair (matched items grey out or disappear); do not tap the same item twice.
- Multiple choice / true-false -> tap the single option, then Check/Continue.
- Typed answer -> type, hide_keyboard, verify the field, then submit.

PLAN, FACTS AND NO LOOPS (very important):
- Every turn read PLAN, FACTS and INSTALLED APPS first. Work on the NEXT PENDING GOAL only. As soon as the screen proves a goal is achieved (app shows "Open" instead of "Install", the VPN says Protected/Connected, the page loaded, the message was sent) put its number in "done_goals" and add a "fact".
- If INSTALLED APPS lists the app you need, NEVER go to the Play Store: use open_app (or tap its icon). Do not re-download or re-install anything that is already installed.
- Opening an app and seeing its main screen already satisfies an "open the app" goal. Then continue with the NEXT goal INSIDE that app or open the next app directly with open_app. Do NOT press home just to reopen the same app again, and do not "check" the same thing twice.
- Never repeat a cycle like open app -> home -> open app. If WHAT YOU ALREADY DID shows you did something, it is done: move on.
- Never invent addresses (URLs, .onion, phone numbers, emails, package names). Use a search engine, the app's own search, or a well-known official address. If an address fails twice, try another real source instead of retrying the same one.
- When every goal is done, call done immediately; the user is notified automatically.

SESSION MEMORY (read it EVERY turn before acting):
- CAPTURED TRANSCRIPTS Tn hold what was said in videos/audios you already played. WHAT YOU ALREADY DID lists your previous actions and the feedback seen (Correct/Incorrect). Do not repeat things already done.
- If a transcript already contains what the question needs, answer from it. Do NOT tap "Show video"/play again: apps often offer the same lesson video again on later questions.
- Only capture again when a NEW audio/video is needed (a new "Listen" exercise, a different video).

AUDIO / VIDEO (decide, do not hunt):
- Use play_and_read ONLY if the screenshot/list really shows a play/replay/speaker control, a video player (play triangle, progress slider), a "Show video"/"Watch" button, or the instruction says Listen/Watch AND the answer depends on the sound or video.
- NEVER search for audio on screens about a picture, grammar, vocabulary or reading text (e.g. "The houses are a symbol of ___" with a photo: first answer from the question/photo/memory; open the video only if the answer needs it and it is not in memory).
- Layout A: inline player on the question screen (play/pause + slider): play_and_read on its control (it may be autoplaying: the tool waits for the end and replays from the start).
- Layout B: a "Show video" button opens a FULL-SCREEN player that does NOT autoplay: use play_and_read on "Show video" (the tool presses play for you and records until the end). Afterwards CLOSE the player (back or the collapse icon) and answer. Never leave the player without having captured it, and never answer from a video you did not play.
- "Listen" exercises with no visible control: the audio autoplayed when the screen opened and is probably over: use play_and_read on the picture/video area to replay it.
- If a result says no audio started / silent / no speech: at most 2 retries per question, then answer with grammar, the images and common sense (pick the most plausible).
- True/False or multiple choice about audio: compare each option to the transcript. "True" only if the transcript clearly supports the statement.

READING / IMAGES / EXERCISES:
- LONG TEXT: if the text continues below the screen, call read_all BEFORE answering. Never answer a reading question from only the visible part.
- Questions about a picture: describe what you see in the screenshot; use zoom for details.
- Fill-in-the-blank with word chips: chips fill the blanks IN ORDER (first blank first). Tap chips one at a time, check in the screenshot that every blank is filled, then Check/Confirm/Continue.
- After you choose an answer, read the feedback banner (Correct/Incorrect). If Incorrect and the app shows the right answer, use it. Then tap Continue/Next. Do not leave a question half answered.

TERMINAL / FILES (prefer these over the screen whenever the task is about files, text or commands):
- Phone storage from Termux: ~/storage/shared/ (Downloads ~/storage/downloads/, Pictures ~/storage/pictures/, DCIM ~/storage/dcim/, Documents ~/storage/documents/). These are SYMLINKS: ALWAYS end them with a slash (ls ~/storage/downloads/), otherwise ls shows only the link. Names the user types may differ in case (jailbreak = JAILBREAK): use find_path or find -iname. If ~/storage is missing, tell the user to run termux-setup-storage.
- Chain steps in ONE shell call (cd x && ls | head -20). Keep output small: head, tail, grep, wc, ls -t | head. Use find to locate files (find ~/storage -iname '*name*' 2>/dev/null | head).
- Send a file: 1) shell find/ls to locate it, 2) send_file, 3) screen actions to pick the target. The target picker (My Drive, WhatsApp, a contact...) in the system share sheet SENDS IMMEDIATELY on tap — there is no separate "contact" step or "Send" button for apps like Drive. Only chat apps (WhatsApp...) need a further step: pick the conversation, then tap Send.
- Google Drive specifically: after tapping "Drive"/"My Drive" in the share sheet, Drive may show its own small dialog (account + an "Upload" button) — tap Upload once. After that the screen often returns to the home/launcher almost immediately while the upload finishes in the BACKGROUND: that is normal success, NOT a failure. Do not call send_file again for the same file just because you landed back on the launcher. Only retry if the screen actually shows an error/failure message.
- Already called send_file for this exact file once? Do NOT call it again (duplicate uploads; the system blocks it). VERIFY it instead: the file name must appear in Drive's list/Recent (read the screen). A stale "1 upload complete" notification is NOT proof: it may belong to an earlier run.
- send_file does not wait for Termux:API. If the share sheet does not show up after one {"action":"screen"}, upload from inside the destination app: open_app Drive ONCE, tap "+" (New/Novo), tap "Upload"/"Fazer upload", then in the file picker use tap_text with the EXACT file name (use the picker search icon + type first if the list is long). Selecting a file in the picker opens a confirmation dialog with the file name: check it is the right one, then tap the Upload button.
- INSIDE the system file picker (documentsui) the calling app is still running underneath: do NOT call open_app/home/back to "return" to it. Pick the file, and the app continues by itself.
- Confirm-cancel dialogs (e.g. Drive "Cancel upload?"): "Close"/"Continue"/"Keep" KEEPS the upload; only "Cancel upload"/"Discard" leaves it.
- An installed app's real APK is NOT a file in ~/storage (find will never locate it there). The phone is ROOTED: use shell with "root":true. 1) pm list packages | grep -i <name> -> package id; 2) pm path <package> -> ALL apk paths (base + splits); 3) copy each with root into a Termux folder: mkdir -p ~/apk_tmp && cp /data/app/.../base.apk ~/apk_tmp/NAME.apk (root:true); 4) then with a NORMAL shell call (no root) cp ~/apk_tmp/NAME.apk ~/storage/downloads/NAME.apk, so the Drive picker can see it. Do each copy ONCE; the [file check] line registers it in FILES YOU PREPARED with its full path: never copy it again.
- The system blocks delete/kill/uninstall/reboot/mount/su commands (also with root:true), overwriting files, and resending the same file. Use force=true ONLY if the TASK explicitly asks for it.
- After terminal actions call done as soon as the result is in the output. Do not touch the screen if the task does not need it.
- When a command FAILS: read the LAST lines of its output first (the real cause is printed at the END, not in the download progress). Never repeat the same command hoping for a different result: change something (package, flags, verbose mode like pip -v / make VERBOSE=1, a prebuilt binary) or isolate the failing step. After 2 failures with the same root cause, switch strategy completely or call fail quoting the exact error line.
- NEVER claim something is installed without verifying it (pip show X / dpkg -s X / command -v X / python -c "import X"). "Requirement already satisfied" for a DIFFERENT package proves nothing.
- Termux facts: pip cannot upgrade itself; python-dev/build-essential/libssl-dev do not exist; use "pkg search NAME" to find prebuilt packages; run root commands with "root":true (never su/sudo inside cmd); long builds are fine, the timeout is raised automatically.

PERSISTENCE (very important):
- There is no step limit: you keep going until the TASK is actually finished. Never give up after one or two failed attempts.
- If one approach to a sub-step fails repeatedly (same action not working, element not found, app misbehaving), do NOT get stuck repeating it: try a clearly different approach (another element, scroll, open_app, tap_cell, a workaround). If after several different approaches that sub-step is still impossible, SKIP it, note why in "notes", and continue with the rest of the TASK.
- Only call fail if the ENTIRE task is impossible (missing login/permission you cannot get, content does not exist, blocked by ask_user with no answer). If you completed part of the task but had to skip something, call done and say exactly what was done and what was skipped/why in "message" — do not call fail for a partial success.

FINISHING (very important):
- Before EVERY action ask: is the TASK already done? For "do the activity/lesson/quiz" tasks, it is done when the app shows the lesson-complete/results/summary screen or returns to the course map/home. Then call done IMMEDIATELY; do not start another lesson or activity unless the TASK asks for it.
- For one-shot tasks (send a message, open something, change a setting) call done as soon as the result is visible on screen.
- If a COMPLETION SIGNAL is mentioned in the hints, verify it against the TASK and call done.
- "message" in done/fail must be a clear final summary: what was accomplished, and if anything was skipped or could not be done, say what and why.

GENERAL ROBUSTNESS:
- Pop-ups, ads, rating requests, notifications, cookie banners: dismiss them (X, Not now, Skip, Later) only when they block the task. Permission dialogs: allow only if the task needs it. Login, captcha, payment: ask_user.
- App not responding / crashed / error screen: wait, then retry once; if still broken, back/reopen with open_app.
- Loading spinner or blank screen: wait 2-3s instead of tapping.
- Optional field "notes" (max 1000 chars): carry progress to the next turns (e.g. "questions done: 5; video of Cape Town captured as T1"). It replaces the previous notes.
- If the screenshot and the element list disagree, trust the screenshot. Prefer tapping listed elements; otherwise tap_cell.
- To open an app ALWAYS use open_app. The first screen is the phone home screen. If the app is com.termux you are looking at the agent's own terminal: ignore it and use open_app.
- After tapping a text field (focused / keyboard visible), your NEXT action must be type, then enter or tap Send. If the field already shows a text cursor, it is focused: do NOT tap it again, call type right away. A tap on an already focused field leaves the screen unchanged: that is normal.
- To send a long text you read from a file, use type with "file" instead of reading it again (read_file once is enough).
- Each action in RECENT ACTIONS ends with [screen changed] or [screen did NOT change]. If it did not change, the tap probably missed: use another element or tap_cell. Never repeat a failing action more than twice.
- Never make payments, delete data, install/uninstall apps or change passwords unless the TASK explicitly says so.
- Write any text for the user in the language of the TASK."""

NEW_ACTIONS = '- web_search {"query":"libX apk download official","n":6}   search the INTERNET (title + URL + snippet). Use it YOURSELF whenever you lack a fact, package name, version, download link or documentation: never guess and never ask the user for something you can look up\n- web_fetch {"url":"https://...","max_chars":6000,"links":true}   open a web page and return its readable text (links:true also lists the page\'s links with absolute URLs: use it to find the REAL download link). Also reads JSON/APIs (e.g. https://api.github.com/repos/OWNER/REPO/releases/latest)\n- download {"url":"https://...","path":"~/storage/downloads/"}   download a file by itself (resumes, checks size, refuses HTML pages disguised as files, never overwrites: picks a free name). path = folder (ends with /) or file name; default = the working directory. Prefer it over curl/wget. Verify the result (ls -l, unzip -l, file) before you report it\n'
SHELL_BATCH = '  Several steps in ONE call: {"action":"shell","cmds":["mkdir -p $PA_TMP/x","cp a $PA_TMP/x/","ls -l $PA_TMP/x"]} runs them in order and stops at the first failure. ALWAYS batch sequential steps and make searches BROAD (one find with -o patterns, one `for f in ...; do unzip -l $f | grep ...; done`): every model turn costs seconds.\n'
SAFETY = '\n\nFILE SAFETY (enforced by code; nothing here is negotiable and "force" never overrides it):\n- You may only delete or overwrite files YOU created in this task. Everything else on the phone belongs to the USER, even if it sits in the very folder you are working in (a Downloads folder full of other files is NORMAL: leave them alone). Foreign deletes/overwrites are refused unless the human approves a prompt.\n- "do not make a mess / leave no loose files / limpe depois" means: do not leave YOUR temporary files behind. It NEVER means emptying a folder or deleting the user\'s files.\n- Put ALL temporary/intermediate files (extracted APKs, downloads you only need to unpack, test files) in $PA_TMP (the SCRATCH folder shown every turn). The system deletes it automatically when the task ends, so you do not spend steps cleaning. Only the final deliverables go where the TASK says, and ONLY them.\n- Never use "force" to get past a safety block. Pick another file name, or say in the done message what could not be done.\n\nHONESTY (the system audits you with real evidence and measures the final state itself):\n- Report ONLY what you saw in a command output or on screen in THIS run. Never claim copied/installed/removed/uploaded without verifying it (ls -l, unzip -l, command -v, the screen).\n- In done, list "deliverables":["/full/path/file", ...] = every file the TASK asked for. The system checks each one exists and prints its real size next to your message. If something failed or was skipped, say so plainly.\n\nUNDERSTANDING THE TASK:\n- Read CONSTRAINTS and DELIVERABLES every turn. Do exactly what was asked, no more, no less. Resolve "here / this folder / aqui / nesta pasta" to the WORKING DIRECTORY.\n- If a word is ambiguous, choose the safest, least destructive reading and note it. Use ask_user only when a wrong guess would be costly or irreversible.\n- Research yourself with web_search / web_fetch / download for anything you do not know or must fetch. Prefer official sources (project site, GitHub releases, F-Droid, vendor docs) and verify what you downloaded.'
SYSTEM_TERM = 'You are phoneagent: an autonomous agent living in the Termux terminal of a ROOTED Android phone (think Claude Code, but for the phone). You finish the user\'s TASK end to end in as few steps as possible: research on the internet, download, run commands, create and organize files, and drive apps on screen ONLY when no terminal/web way exists.\nEach turn you get TASK, ENVIRONMENT, CONSTRAINTS, DELIVERABLES, PLAN, FACTS, RECENT ACTIONS (and a screen only if you asked for it). Reply with ONE JSON object and nothing else: {"thought":"short reasoning","action":"<name>", ...params} (params at the TOP level, never nested). Optional on any action: "done_goals":[1,2] (finished PLAN goals), "fact":"short verified fact", "plan":["..."] (replace a wrong plan), "notes":"...".\n\nActions:\n- shell {"cmd":"ls -la","timeout":30,"root":false}   run in the Termux shell (sh); "cd" persists. "root":true = as root with Android tools first in PATH (pm, am, dumpsys, settings, /data/...; "cd" does not persist there; never write su/sudo). Stdin is closed: no interactive programs, use -y flags.\n  Several steps in ONE call: {"action":"shell","cmds":["mkdir -p $PA_TMP/x","cp a $PA_TMP/x/","ls -l $PA_TMP/x"]} runs them in order and stops at the first failure. ALWAYS batch sequential steps and make searches BROAD (one find with -o patterns, one `for f in ...; do unzip -l $f | grep ...; done`): every model turn costs seconds.\n- find_path {"name":"jailbreak"}   locate a file/folder by name (case-insensitive, partial ok) in Termux home and phone storage\n- read_file {"path":"...","max_chars":6000}  |  write_file {"path":"...","content":"...","append":false}\n- web_search {"query":"libX apk download official","n":6}   search the INTERNET (title + URL + snippet). Use it YOURSELF whenever you lack a fact, package name, version, download link or documentation: never guess and never ask the user for something you can look up\n- web_fetch {"url":"https://...","max_chars":6000,"links":true}   open a web page and return its readable text (links:true also lists the page\'s links with absolute URLs: use it to find the REAL download link). Also reads JSON/APIs (e.g. https://api.github.com/repos/OWNER/REPO/releases/latest)\n- download {"url":"https://...","path":"~/storage/downloads/"}   download a file by itself (resumes, checks size, refuses HTML pages disguised as files, never overwrites: picks a free name). path = folder (ends with /) or file name; default = the working directory. Prefer it over curl/wget. Verify the result (ls -l, unzip -l, file) before you report it\n- zip_items {"items":["~/a","~/b"],"name":"backup"}   ONE clean zip (relative names, unique timestamped name) in ~/storage/downloads/, verified. Prefer it over the zip command\n- send_file {"path":"..."}   opens the Android share sheet (Termux:API); then finish with screen actions (pick the app/contact, tap Send)\n- Screen (only when needed): screen (look at the phone), tap {"index":N}, tap_text {"text":"exact text"}, tap_cell {"cell":"C7"}, type {"text":"..."}, enter, scroll {"direction":"down"}, back, home, open_app {"app":"whatsapp"}, open_url {"url":"..."}, wait {"seconds":N}, hide_keyboard\n- ask_user {"question":"..."}   only for login/captcha/payment or a costly ambiguity\n- done {"message":"what was done, per item, with evidence","deliverables":["/full/path", ...]}   |   fail {"message":"exact reason"}\n\nTerminal facts:\n- Phone storage: ~/storage/shared/ (Downloads ~/storage/downloads/, DCIM ~/storage/dcim/, Documents ~/storage/documents/): symlinks, ALWAYS end with a slash. Names may differ in case: use find_path or find -iname. Real path of Downloads for root: /sdcard/Download.\n- An installed app\'s APK is not in ~/storage: shell root:true: pm list packages | grep -i NAME -> pm path PKG (base + ALL splits) -> copy with root into $PA_TMP, then a NORMAL shell cp to the destination. Inspect archives with unzip -l APK | grep -i PATTERN over ALL splits in one command. If two packages match, say which you used.\n- When a command fails read the LAST lines of its output (the cause is printed at the end). Never repeat the same command hoping for a different result: change something or switch strategy. After 2 failures with the same cause, change approach completely or call fail quoting the exact error.\n- Never claim something is installed without verifying (command -v X, pip show X, dpkg -s X). Termux: python-dev/build-essential/libssl-dev do not exist; use "pkg search NAME"; pip cannot upgrade itself.\n- Never invent URLs, package names or paths: search (web_search) or look (ls/find). Never pipe a download into sh.\n- Not searching in circles: if two searches came back empty, widen the scope (other folders, all splits, other names, the web) instead of retrying narrower variants.\n\nPERSISTENCE: no step limit; do not give up after one or two failures: try a clearly different approach; skip a sub-step only after several different approaches and say so. Call fail only when the ENTIRE task is impossible; for partial success call done and state exactly what was and was not done.\nFINISHING: before every action ask "is the TASK already done?". When every goal is verified, call done at once. Write for the user in the language of the TASK.\n\nFILE SAFETY (enforced by code; nothing here is negotiable and "force" never overrides it):\n- You may only delete or overwrite files YOU created in this task. Everything else on the phone belongs to the USER, even if it sits in the very folder you are working in (a Downloads folder full of other files is NORMAL: leave them alone). Foreign deletes/overwrites are refused unless the human approves a prompt.\n- "do not make a mess / leave no loose files / limpe depois" means: do not leave YOUR temporary files behind. It NEVER means emptying a folder or deleting the user\'s files.\n- Put ALL temporary/intermediate files (extracted APKs, downloads you only need to unpack, test files) in $PA_TMP (the SCRATCH folder shown every turn). The system deletes it automatically when the task ends, so you do not spend steps cleaning. Only the final deliverables go where the TASK says, and ONLY them.\n- Never use "force" to get past a safety block. Pick another file name, or say in the done message what could not be done.\n\nHONESTY (the system audits you with real evidence and measures the final state itself):\n- Report ONLY what you saw in a command output or on screen in THIS run. Never claim copied/installed/removed/uploaded without verifying it (ls -l, unzip -l, command -v, the screen).\n- In done, list "deliverables":["/full/path/file", ...] = every file the TASK asked for. The system checks each one exists and prints its real size next to your message. If something failed or was skipped, say so plainly.\n\nUNDERSTANDING THE TASK:\n- Read CONSTRAINTS and DELIVERABLES every turn. Do exactly what was asked, no more, no less. Resolve "here / this folder / aqui / nesta pasta" to the WORKING DIRECTORY.\n- If a word is ambiguous, choose the safest, least destructive reading and note it. Use ask_user only when a wrong guess would be costly or irreversible.\n- Research yourself with web_search / web_fetch / download for anything you do not know or must fetch. Prefer official sources (project site, GitHub releases, F-Droid, vendor docs) and verify what you downloaded.'

SYSTEM = SYSTEM.replace("~/apk_tmp", "$PA_TMP")
_OLD_BLOCK = "- The system blocks delete/kill/uninstall/reboot/mount/su commands (also with root:true), overwriting files, and resending the same file. Use force=true ONLY if the TASK explicitly asks for it."
assert _OLD_BLOCK in SYSTEM
SYSTEM = SYSTEM.replace(_OLD_BLOCK, "- The system blocks kill/uninstall/reboot/mount/su commands (also with root:true) and resending the same file, and REFUSES to delete/overwrite files you did not create (see FILE SAFETY). \"force\":true never overrides FILE SAFETY.")
_ANCHOR = "- tap_text {\"text\":\"tiktok_mod.apk\"}"
assert _ANCHOR in SYSTEM
SYSTEM = SYSTEM.replace(_ANCHOR, NEW_ACTIONS + _ANCHOR, 1)
_ANCHOR = "\n  pkg/apt/apt-get/pip install commands are checked automatically"
assert _ANCHOR in SYSTEM
SYSTEM = SYSTEM.replace(_ANCHOR, "\n" + SHELL_BATCH.rstrip("\n") + _ANCHOR, 1)
SYSTEM = SYSTEM.replace('- done {"message":"what was accomplished"}', '- done {"message":"what was accomplished","deliverables":["/full/path/of/each/file/the TASK asked for"]}', 1)
_ANCHOR = "\n\nPRECISION (no guessing, nothing missing):"
assert _ANCHOR in SYSTEM
SYSTEM = SYSTEM.replace(_ANCHOR, SAFETY + _ANCHOR, 1)

DEVICE_DOC = (
    '- set_alarm {"hour":9,"minute":0,"label":"optional","days":["mon","tue"],"show":false}   creates a REAL Clock-app alarm through the Android alarm intent (rings with the phone locked, no tapping, the code VERIFIES it). days omitted = once; "show":true opens the Clock app on it. ALWAYS use this for alarms: never Termux:API/sleep/cron and never tap through the Clock UI\n'
    '- set_timer {"minutes":10,"label":"optional","show":false}   (or "seconds":N / "hours":N) same idea for timers\n'
    '- device {"setting":"wifi|bluetooth|data|airplane|dnd|rotation|brightness|volume","value":"on|off|0-100|max","stream":"media|ring|alarm|notification"}   quick system switches through root, verified (use it instead of termux-wifi-enable/termux-volume/...)\n'
    '- time_picker_set {"hour":9,"minute":0}   ONLY when a "Set time/Selecionar horario" dialog (Hora/Minuto fields) is already open on screen: fills both fields with 2 digits, verifies and taps OK\n'
    + brain.GENERAL_RULES + "\n")

# ---- v5: type com index/submit, open_url esperto, thought curto, terminal sem tocar na tela
TYPE_DOC = ('type {"text":"...","index":N,"submit":true,"clear":false}   types into a text field. "index" = taps that field first (omit it only when the '
            'field is already focused); "submit":true presses Enter right after (search boxes, login fields). With no focused field it taps the first '
            'text field itself. clear=true erases the field first')
OPEN_URL_DOC = ('open_url {"url":"https://..."}   open a page in the default browser. FASTEST way to reach a site: never type addresses into the '
                'browser bar. Plain words (no dots) are searched on Google')
_OLD_TYPE = '- type {"text":"...","clear":false}   type into the focused field (tap the field first). clear=true erases it first'
assert _OLD_TYPE in SYSTEM
SYSTEM = SYSTEM.replace(_OLD_TYPE, "- " + TYPE_DOC)
_OLD_URL = '- open_url {"url":"https://..."}'
assert _OLD_URL in SYSTEM
SYSTEM = SYSTEM.replace(_OLD_URL, "- " + OPEN_URL_DOC, 1)
THOUGHT_RULE = ('\n\nSTYLE: "thought" = max 15 words, in the language of the TASK. Do exactly what the TASK asks, nothing extra: no side quests, no extra '
                'checks once the result is in hand, no opening apps/sites the TASK did not mention. Never open Termux (that is the agent\'s own terminal).')
SYSTEM += THOUGHT_RULE
_ANCHOR = "\n\nPRECISION (no guessing, nothing missing):"
assert _ANCHOR in SYSTEM
SYSTEM = SYSTEM.replace(_ANCHOR, "\n" + DEVICE_DOC.rstrip("\n") + _ANCHOR, 1)

SYSTEM_SCREEN = """You control a ROOTED Android phone from the Termux terminal (commands run as root through su). Act like a careful, efficient human user: do what the TASK asks and stop.
Each turn you get TASK, ENVIRONMENT, PLAN/FACTS, RECENT ACTIONS and the SCREEN (UI elements with an index, usually plus a screenshot).
Reply with ONE JSON object and nothing else: {"thought":"max 15 words, language of the TASK","action":"<name>", ...params} (params at the TOP level). Optional on any action: "done_goals":[1], "fact":"short verified fact", "plan":["..."], "notes":"...".

Actions:
- """ + OPEN_URL_DOC + """
- web_search {"query":"...","n":6}   search the internet WITHOUT the screen (title + URL + snippet): use it to find the official site, then open_url it
- web_fetch {"url":"https://...","max_chars":6000,"links":true}   read a page as text WITHOUT the screen (links:true lists link URLs): find the right sub-page, then open_url it
- tap {"index":N} | tap_text {"text":"exact text"} | tap_cell {"cell":"C7"} (red grid A-F x 1-12 on the screenshot) | tap_xy {"x":0-1000,"y":0-1000} | long_press {"index":N}
- """ + TYPE_DOC + """
- enter | back | home | hide_keyboard | wait {"seconds":N}
- scroll {"direction":"down|up","times":1}   direction = where you want to go (down reveals content below) | swipe {"direction":"left|right|up|down"}
- read_all   scrolls through the whole page by itself and returns ALL its text (use it to read long pages, codes, barcodes, results)
- zoom {"x1":0-1000,"y1":0-1000,"x2":0-1000,"y2":0-1000}   next turn you also get a magnified crop
- open_app {"app":"whatsapp"}
- shell {"cmd":"...","timeout":30,"root":false}   run a command in Termux ("cd" persists; "root":true = root with Android tools: pm, am, dumpsys, settings). Several steps: {"action":"shell","cmds":["a","b"]}. Stdin closed: no interactive programs
- find_path {"name":"..."} | read_file {"path":"..."} | write_file {"path":"...","content":"..."} | download {"url":"...","path":"~/storage/downloads/"} | send_file {"path":"..."} (opens the share sheet)
- ask_user {"question":"..."}   ONLY for a password/login you do not have, captcha, SMS/2FA code, payment confirmation, or a costly ambiguity
- done {"message":"what was accomplished, with the concrete result","deliverables":["/full/path/of/each/file"]}   |   fail {"message":"exact reason"}

How to work:
- One action per turn. Indexes change every turn. The screen is refreshed after each action; each action in RECENT ACTIONS ends with [screen changed] or [screen did NOT change].
- Look at the screen first: which app/page is this and does it match the PLAN? Reach sites with open_url (get the real URL with web_search/web_fetch first; never invent addresses). Do not type URLs into the browser bar.
- If an action did not change the screen, do NOT repeat it: pick another element, scroll, tap_text, tap_cell, or open_url the page again. Never repeat the same action more than twice.
- Forms: use the data given in the TASK exactly (names, dates, CPF/IDs) and type it into the right field with type {"index":N,...}. Dates: follow the field's format. Digits-only fields: digits only. After filling, hide_keyboard if it covers the buttons, then press the button.
- The on-screen keyboard hides what is below it: after typing, hide_keyboard and read the screen again before submitting.
- Pop-ups, cookie banners, notifications: dismiss only when they block the task. Loading spinner/blank: wait 2-3s instead of tapping.
- If the site offers a path that only needs the data you already have, use it before asking for passwords. Ask ask_user ONLY when truly blocked (password, captcha, code sent to the user).
- Never pay, install/uninstall, delete data or change passwords unless the TASK says so. "Generate the slip/boleto/GRU so I can pay" = generate it, read the barcode/linha digitavel/PIX code/value with read_all, put them in done.message, and STOP before paying.
- Facts and PLAN: mark finished goals in done_goals as soon as the screen proves them. When every goal is done call done IMMEDIATELY with the real result (codes, values, links, file paths), in the language of the TASK.
- Do exactly what the TASK asks, nothing extra. Never open Termux (it is the agent's own terminal; the first screen may show it: ignore it). Pressing home/back just to "reset" is a waste: go straight to open_url/open_app.
- Persistence: no step limit; if an approach fails twice, change it completely. Only call fail when the ENTIRE task is impossible; for partial success call done and say what was and was not done.""" + SAFETY

assert "\n\nHow to work:" in SYSTEM_SCREEN
SYSTEM_SCREEN = SYSTEM_SCREEN.replace("\n\nHow to work:", "\n" + DEVICE_DOC.rstrip("\n") + "\n\nHow to work:", 1)

_TERM_ANCHOR = 'FINISHING: before every action ask "is the TASK already done?". When every goal is verified, call done at once. Write for the user in the language of the TASK.'
assert _TERM_ANCHOR in SYSTEM_TERM
SYSTEM_TERM = SYSTEM_TERM.replace(_TERM_ANCHOR, (
    'STAY IN THE TERMINAL: the user is watching Termux. If the TASK needs only commands, files or web text, use shell/read_file/web_search/web_fetch/download '
    'and NEVER touch the screen (no screen, home, back, open_app, tap): leaving Termux annoys the user. Never open Termux itself. Use the screen only when the TASK '
    'is about an app or a website that needs clicking; then go straight to open_url/open_app.\n'
    'ANSWERS: for list/read/show/count/find requests, put the REAL answer in done.message (the actual list, value or text, compact) - never "see the output above": '
    'the user only reads the final message. Command output is valid evidence; it is already shown in the terminal, so there is nothing to "display on the screen".\n'
    'SPEED: as few turns as possible: chain commands with && in ONE shell call, no re-checks once the answer is in the output, then call done.\n'
    'STYLE: "thought" = max 15 words, in the language of the TASK. Do exactly what was asked, nothing extra.\n' + _TERM_ANCHOR))
_OLD_TT = 'type {"text":"..."}, enter,'
assert _OLD_TT in SYSTEM_TERM
SYSTEM_TERM = SYSTEM_TERM.replace(_OLD_TT, 'type {"text":"...","index":N,"submit":true}, enter,', 1)
_OLD_OU = 'open_url {"url":"..."}, wait'
assert _OLD_OU in SYSTEM_TERM
SYSTEM_TERM = SYSTEM_TERM.replace(_OLD_OU, 'open_url {"url":"https://..."} (fastest way to a site; plain words search Google), wait', 1)
assert "\n\nTerminal facts:" in SYSTEM_TERM
SYSTEM_TERM = SYSTEM_TERM.replace("\n\nTerminal facts:", "\n" + DEVICE_DOC.rstrip("\n") + "\n\nTerminal facts:", 1)


# ---------------------------------------------------------------- SAIDA NO TERMINAL (estilo "Claude Code")
_NO_COLOR = bool(os.environ.get("NO_COLOR")) or not sys.stdout.isatty()
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


class C:
    """Codigos ANSI. Viram string vazia sozinhos se a saida nao for um terminal (ou com NO_COLOR=1) — nunca suja um log/pipe."""
    R = "" if _NO_COLOR else "\033[0m"
    DIM = "" if _NO_COLOR else "\033[2m"
    B = "" if _NO_COLOR else "\033[1m"
    RED = "" if _NO_COLOR else "\033[31m"
    GREEN = "" if _NO_COLOR else "\033[32m"
    YELLOW = "" if _NO_COLOR else "\033[33m"
    BLUE = "" if _NO_COLOR else "\033[34m"
    CYAN = "" if _NO_COLOR else "\033[36m"
    GRAY = "" if _NO_COLOR else "\033[90m"
    ORG = "" if _NO_COLOR else "\033[38;5;173m"
    IT = "" if _NO_COLOR else "\033[3m"
    WHITE = "" if _NO_COLOR else "\033[97m"


_LOCK = threading.RLock()
_SPIN = None
_LOGFILE = None
ANIM = (not _NO_COLOR) and os.environ.get("NO_ANIM") is None
GLYPHS = ["·", "✢", "✳", "✶", "✻", "✽", "✻", "✶", "✳", "✢"]
VERBS = ["Pensando"]


def log(msg):
    with _LOCK:
        if _SPIN is not None:
            _SPIN.clear()
        print(msg, flush=True)
        if _LOGFILE:
            try:
                _LOGFILE.write(_ANSI_RE.sub("", str(msg)) + "\n")
                _LOGFILE.flush()
            except Exception:
                pass


def flog(text):
    """Grava so no arquivo de log da sessao (saida completa, sem cortes)."""
    if _LOGFILE:
        try:
            _LOGFILE.write(text + "\n")
            _LOGFILE.flush()
        except Exception:
            pass


brain.set_logger(lambda m: log(m))


def _trim(s, n):
    s = str(s)
    return s if len(s) <= n else s[:max(1, n - 1)] + "…"


class Spinner:
    """Indicador animado estilo Claude Code: glifo girando, verbo com brilho passando, cronometro e (nos comandos) a ultima linha de saida."""
    def __init__(self, verbs=None, info=""):
        self.verbs, self.info = verbs or VERBS, info
        self.t0, self._stop, self._th = time.time(), threading.Event(), None

    def set(self, info):
        self.info = info

    def clear(self):
        if ANIM:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def _frame(self, k):
        el = time.time() - self.t0
        verb = self.verbs[int(el // 3) % len(self.verbs)] + "…"
        cols = shutil.get_terminal_size((70, 20)).columns
        glyph = GLYPHS[(k // 2) % len(GLYPHS)]
        line = f"{C.ORG}{glyph} {verb}{C.R} {C.GRAY}({el:.0f}s{self.info}){C.R}"
        if _vlen(line) > cols - 1:
            line = f"{C.ORG}{glyph} {verb}{C.R} {C.GRAY}({el:.0f}s){C.R}"
        return line

    def _loop(self):
        k = 0
        while not self._stop.wait(0.12):
            with _LOCK:
                if _SPIN is self:
                    sys.stdout.write("\r\033[K" + self._frame(k))
                    sys.stdout.flush()
            k += 1

    def __enter__(self):
        global _SPIN
        if ANIM and _SPIN is None:
            _SPIN = self
            sys.stdout.write("\033[?25l")
            self._th = threading.Thread(target=self._loop, daemon=True)
            self._th.start()
        return self

    def __exit__(self, *exc):
        global _SPIN
        if self._th:
            self._stop.set()
            self._th.join(1)
            with _LOCK:
                sys.stdout.write("\r\033[K\033[?25h")
                sys.stdout.flush()
                _SPIN = None
        return False


if ANIM:
    atexit.register(lambda: sys.stdout.write("\033[?25h"))


def _vlen(s):
    return len(_ANSI_RE.sub("", s))


def rule(label=""):
    """Separador discreto. Os passos nao ganham mais uma linha cada: so o final fecha com uma linha fina."""
    if label:
        return
    w = min(shutil.get_terminal_size((70, 20)).columns, 78)
    log(f"{C.GRAY}{'─' * w}{C.R}")


def banner(title, lines, color=None):
    """Caixa com resumo (abertura da sessao / resultado final)."""
    col = color or C.ORG
    w = max([_vlen(title)] + [_vlen(l) for l in lines]) + 2
    log(f"{col}╭{'─' * w}╮{C.R}")
    log(f"{col}│{C.R} {C.B}{title}{C.R}{' ' * (w - 1 - _vlen(title))}{col}│{C.R}")
    log(f"{col}├{'─' * w}┤{C.R}")
    for l in lines:
        log(f"{col}│{C.R} {l}{' ' * (w - 1 - _vlen(l))}{col}│{C.R}")
    log(f"{col}╰{'─' * w}╯{C.R}")


def result_style(res):
    """Cor + simbolo pelo conteudo do resultado de uma acao (sucesso / aviso / erro)."""
    low = res.lower()
    if low.startswith(("blocked", "error", "skipped (not executed")) or re.search(r"\bexit [1-9]\d*\b", low):
        return C.RED, "✗"
    if "warning" in low or "loop" in low or "timeout" in low:
        return C.YELLOW, "!"
    return C.GREEN, "✓"


def clip(s, n=4000):
    return s if len(s) <= n else s[:n // 2] + "\n...[output cut]...\n" + s[-n // 2:]


def tail_clip(s, n=3500):
    """Em falhas o erro de verdade esta no FIM (o comeco e so barra de progresso): mantem o final."""
    return s if len(s) <= n else "...[start of output cut; showing the LAST part]...\n" + s[-n:]


TOOL_NAMES = {"shell": "Shell", "read_file": "Ler", "write_file": "Escrever", "send_file": "Enviar", "find_path": "Buscar",
              "zip_items": "Zip", "web_search": "Pesquisar", "web_fetch": "Abrir página", "download": "Baixar", "tap": "Tocar", "tap_cell": "Tocar", "tap_xy": "Tocar", "tap_text": "Tocar", "long_press": "Segurar",
              "type": "Digitar", "open_app": "Abrir", "scroll": "Rolar", "swipe": "Deslizar", "wait": "Aguardar", "screen": "Tela",
              "read_all": "Ler tudo", "listen": "Ouvir", "play_and_read": "Ouvir", "enter": "Enter", "back": "Voltar", "home": "Inicio",
              "order_words": "Ordenar", "select_words": "Selecionar", "zoom": "Zoom", "hide_keyboard": "Teclado", "ask_user": "Perguntar",
              "done": "Concluir", "fail": "Falhar", "set_alarm": "Alarme", "set_timer": "Timer", "device": "Ajuste", "time_picker_set": "Horário"}
META_KEYS = {"thought", "notes", "done_goals", "fact", "plan", "action", "force", "root", "timeout", "deliverables"}


def tool_line(a, meta=""):
    """'● Shell(comando)  gpt-oss 2s' estilo Claude Code. meta = modelo + tempo, discreto no fim da linha."""
    k = str(a.get("action", "?"))
    k = TERM_ALIAS.get(k, k)
    if k == "shell":
        cs = a.get("cmds")
        arg = str(a.get("cmd") or a.get("command") or (" && ".join(map(str, cs)) if isinstance(cs, list) else "")).replace("\n", " ⏎ ")
    else:
        arg = ", ".join(f"{x}={v}" for x, v in a.items() if x not in META_KEYS)
    cols = min(shutil.get_terminal_size((70, 20)).columns, 110)
    tags = "".join(f" {C.GRAY}[{t}]{C.R}" for t in ("root" if a.get("root") else "", "force" if a.get("force") else "") if t)
    tail = f"  {C.GRAY}{meta}{C.R}" if meta else ""
    room = cols - len(TOOL_NAMES.get(k, k)) - 8 - (len(meta) + 2 if meta else 0)
    return (f"{C.ORG}●{C.R} {C.B}{TOOL_NAMES.get(k, k)}{C.R}{C.GRAY}({C.R}{_trim(arg, max(20, room))}{C.GRAY}){C.R}{tags}{tail}")


def short_model(m):
    """'gemma4:31b-cloud' -> 'gemma4'; 'gpt-oss:120b-cloud' -> 'gpt-oss'."""
    return str(m or "?").split(":")[0].split("/")[-1]


def show_result(res, maxl=6):
    """Resultado recolhido com '⎿' e '… +N linhas'. Em erro mostra o FINAL da saida (onde esta a causa)."""
    res = re.sub(r"^\[cwd [^\]]*\] \[exit 0\]\n?", "", str(res))  # cabecalho de sucesso e ruido; em erro ele continua visivel
    color, icon = result_style(res)
    lines = [l.rstrip() for l in str(res).splitlines() if l.strip()] or ["(sem saida)"]
    err = icon == "✗"
    cols = min(shutil.get_terminal_size((70, 20)).columns, 110) - 9
    if len(lines) > maxl:
        hidden = len(lines) - maxl
        if err:
            shown = [lines[0], f"… +{hidden} linhas acima"] + lines[-(maxl - 1):]
        else:
            shown = lines[:maxl] + [f"… +{hidden} linhas (veja ~/.phoneagent_logs)"]
    else:
        shown = lines
    for k, l in enumerate(shown):
        pre = f"  {C.GRAY}⎿{C.R}  " if k == 0 else "     "
        body = _trim(l, cols)
        if k == 0:
            log(f"{pre}{color}{icon} {body}{C.R}")
        else:
            log(f"{pre}{color if err else C.GRAY}{body}{C.R}")


TERM_HINT_RE = re.compile(
    r"\b(pkg|pip3?|apt|npm|termux|shell|bash|sh|comando|cmd|script|python3?|node|git|clang|cmake|make|gcc|adb|chmod|curl|wget|zip|unzip|tar|"
    r"list\w*|lista|ls|cat|grep|find|head|tail|wc|du|df|ps|top|pwd|echo|"
    r"arquivos?|files?|pasta|pastas|folders?|diret[oó]rios?|downloads?|apk|log|logs|"
    r"cri(e|ar)|apag\w*|delet\w*|remov\w*|mov\w*|copi\w*|renome\w*|compact\w*|extra\w*|descompact\w*|"
    r"l(eia|er)|mostre|exib\w*|conte|quantos?|quantas?|tamanho|espa[cç]o|vers[aã]o|bateria|processos?|"
    r"busq\w*|procur\w*|ach(e|ar)|encontr\w*|pesquis\w*|search|internet|url|"
    r"instal\w*|baix\w*|download\w*|compil\w*|build|dump\w*|diagn[oó]stic\w*|etapa|hash|sha256|md5|backup|"
    r"edit(e|ar)|escrev\w*|salv\w*|texto|root|offset|ip|rede|wifi|wi-fi|"
    r"alarmes?|despertador|timer|temporizador|volume|brilho|bluetooth|acorde|desperte)\b", re.I)
UI_HINT_RE = re.compile(
    r"\b(toque|toca|tocar|clique|clicar|tap|click|swipe|deslize|tela|screen|screenshot|print|"
    r"app|aplicativo|navegador|browser|chrome|site|p[aá]gina|portal|gov\.br|"
    r"login|logue|logar|loga|senha|entre\s+(?:no|na|em)|acesse|acessar|preench\w*|formul[aá]rio|captcha|cadastr\w*|"
    r"pag(?:ar|ue|amento)|boleto|gere\s+o|emit\w*|abra|abrir|open|"
    r"whatsapp|instagram|youtube|telegram|gmail|drive|tiktok|facebook|spotify|netflix|busuu|duolingo|play\s*store|"
    r"li[cç][aã]o|exerc[ií]cio|quiz|bot[aã]o|button|v[ií]deo|assista|reproduz\w*|ou[cç]a|"
    r"mande|envie|responda|digite)\b", re.I)
LESSON_RE = re.compile(r"\b(li[cç][aã]o|li[cç][oõ]es|exerc[ií]cios?|quiz|busuu|duolingo|lesson|exercise|aula|curso|course|question[aá]rio)\b", re.I)
UI_ACTIONS = {"tap", "tap_cell", "tap_xy", "tap_text", "long_press", "type", "enter", "scroll", "swipe", "back", "home", "open_app", "open_url",
              "hide_keyboard", "read_all", "zoom", "order_words", "select_words", "play_and_read", "listen",
              "click", "press", "scroll_down", "read", "readall", "time_picker_set"}
SIMPLE_WRITE_RE = re.compile(r"\b(cri(e|ar)|baix\w*|download(?:ar|e)|instal\w*|compact\w*|zip|backup|envie|mande|copi\w*|mov\w*|apag\w*|delet\w*|remov\w*|"
                             r"escrev\w*|salv\w*|renome\w*|extra\w*|descompact\w*|compil\w*|build|edit\w*|gere|gerar|clone)\b", re.I)


def task_kind(task):
    """'terminal' ou 'screen'. Padrao = TERMINAL: so vai para a tela quando o pedido fala claramente de app/site/toque.
    Empate -> terminal. (Se um pedido de terminal precisar da tela, o agente escala sozinho; ver _run.)"""
    intent = brain.parse_intent(task)
    if intent and intent.kind in ("music", "music_control"):
        return "screen"
    t, u = len(TERM_HINT_RE.findall(task)), len(UI_HINT_RE.findall(task))
    return "screen" if u > t else "terminal"


def task_is_terminal(task):
    return task_kind(task) == "terminal"


SIMPLE_READ_RE = re.compile(r"\b(list\w*|lista|mostr\w*|exib\w*|le(?:ia|r)|quantos?|quantas?|qual|quais|quanto|ve(?:ja|r)|confir\w*|cont(?:e|ar)|diga|existe|"
                            r"onde|procur\w*|ach(?:e|ar)|encontr\w*|busq\w*|pesquis\w*|verifiq\w*|check\w*|tamanho|vers[aã]o|ip|ls|cat|df|du|ps|pwd|status|"
                            r"bateria|espa[cç]o)\b", re.I)
CONSTRAINT_RE = re.compile(r"\b(n[aã]o|nunca|apenas|somente|s[oó]|sem|nem|exceto|except)\b", re.I)


def task_is_simple(task):
    """Consulta curta so de leitura (listar, mostrar, contar, ver versao...): sem planejador e sem auditor, direto ao ponto.
    Qualquer verbo que escreve/baixa/instala/envia, ou uma restricao do usuario ("nao", "so"), volta ao fluxo completo."""
    return (len(task.split()) <= 24 and bool(SIMPLE_READ_RE.search(task)) and not SIMPLE_WRITE_RE.search(task)
            and not CONSTRAINT_RE.search(task) and not DELIVERY_RE.search(task.lower()))


# ---------------------------------------------------------------- ROOT (su)
SU_PATHS = ("/system/bin/su", "/system/xbin/su", "/sbin/su", "/debug_ramdisk/su", "/data/adb/ksu/bin/su",
            "/data/adb/magisk/su", "/vendor/bin/su", "/su/bin/su")
# O Termux exporta LD_PRELOAD (termux-exec) e poe os binarios dele no PATH; isso atrapalha input/screencap/am/pm como root.
# Binarios do Android primeiro (o "am" do Termux e um wrapper que nao serve para root). HOME = home do Termux para o "~" funcionar.
ROOT_ENV = ("unset LD_PRELOAD LD_LIBRARY_PATH; umask 022; export HOME=" + shlex.quote(HOME)
            + " PATH=/system/bin:/system/xbin:/vendor/bin:/product/bin:$PATH; ")


def find_su():
    for p in SU_PATHS:
        if os.access(p, os.X_OK):
            return p
    return shutil.which("su")


class Root:
    """Controla o Android como root (su), sem ADB: input, screencap, uiautomator, pm, am e dumpsys rodam direto no aparelho."""
    def __init__(self):
        self.su = None if os.geteuid() == 0 else find_su()
        if os.geteuid() != 0 and not self.su:
            sys.exit("su nao encontrado. Confira o root (Magisk/KernelSU) e teste: su -c id")
        log("    (pedindo root; aceite no Magisk/KernelSU se aparecer o aviso)")
        if self.sh("id -u", timeout=60).strip() != "0":
            sys.exit("root negado. Abra o Magisk/KernelSU > Superusuario e permita o Termux.")

    def argv(self, cmd):
        full = ROOT_ENV + cmd
        return ["sh", "-c", full] if self.su is None else [self.su, "-c", full]

    def sh(self, cmd, binary=False, timeout=30):
        empty = b"" if binary else ""
        try:
            r = subprocess.run(self.argv(cmd), capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            log(f"    (comando root travou >{timeout}s em: {cmd[:40]})")
            return empty
        if r.returncode != 0 and b"denied" in r.stderr.lower() and not getattr(self, "warned", False):
            self.warned = True
            log("    (su negou o acesso: libere o Termux no Magisk/KernelSU)")
        return r.stdout if binary else r.stdout.decode("utf-8", "replace")

    def dump(self):
        """uiautomator trava/falha em telas animadas: apaga o arquivo antigo, limita o tempo e mata resto de processo.
        Depois de uma falha usa tentativa unica e curta (nao perde ~20s por turno)."""
        slow = getattr(self, "dump_fail", 0) >= 1
        inner = 5 if slow else 10
        cmd = (f"rm -f {UI_TMP}; if command -v timeout >/dev/null 2>&1; then timeout {inner} uiautomator dump {UI_TMP}; "
               f"else uiautomator dump {UI_TMP}; fi >/dev/null 2>&1; cat {UI_TMP} 2>/dev/null")
        for _ in range(1 if slow else 2):
            out = self.sh(cmd, timeout=inner + 8)
            if "<hierarchy" in out:
                self.dump_fail = 0
                return out
            self.sh("pkill -f uiautomator >/dev/null 2>&1; true", timeout=5)
            time.sleep(0.6)
        self.dump_fail = getattr(self, "dump_fail", 0) + 1
        return ""

    def screenshot(self):
        png = self.sh("screencap -p", binary=True, timeout=30)
        return png if png[:8] == PNG_SIG else png.replace(b"\r\n", b"\n")  # su com pty converte \n em \r\n


def parse_ui(xml_text, maxtext=400, maxels=200):
    """Retorna (pacote, W, H, elementos). Elemento: {line, cx, cy, text, desc, scroll, box}."""
    parse_ui.ime_top = None  # topo (y) da janela do teclado, se ela aparecer no dump
    i = xml_text.find("<")
    if i < 0:
        return "", 1080, 2400, []
    try:
        root = ET.fromstring(xml_text[i:])
    except ET.ParseError:
        return "", 1080, 2400, []
    W, H, pkg, els, last, last_box, ime_top = 1080, 2400, "", [], None, None, None
    first = True
    for n in root.iter("node"):
        a = n.attrib
        m = BOUNDS.match(a.get("bounds", ""))
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        if first:
            W, H, first = x2 or W, y2 or H, False
        if IME_PKG_RE.search(a.get("package", "")):  # teclas nao entram na lista; so marcam onde o teclado comeca
            if x2 > x1 and y2 > y1 and y1 < H:
                ime_top = y1 if ime_top is None else min(ime_top, y1)
            continue
        pkg = pkg or a.get("package", "")
        if x2 <= x1 or y2 <= y1 or x1 >= W or y1 >= H or x2 <= 0 or y2 <= 0:
            continue
        text = a.get("text", "").strip().replace("\n", " ")[:maxtext]
        desc = a.get("content-desc", "").strip().replace("\n", " ")[:maxtext]
        rid = a.get("resource-id", "").split("/")[-1]
        cls = a.get("class", "").split(".")[-1]
        edit = "EditText" in cls
        click = a.get("clickable") == "true" or a.get("long-clickable") == "true"
        scroll = a.get("scrollable") == "true"
        if not (text or desc or edit or scroll or (click and rid)):
            continue
        partial = y2 > H + 8 or y1 < -8 or x2 > W + 8 or x1 < -8
        flags = [f for f, on in (
            ("clickable", click), ("editable", edit), ("scrollable", scroll),
            ("checked", a.get("checked") == "true"), ("selected", a.get("selected") == "true"),
            ("focused", a.get("focused") == "true"), ("disabled", a.get("enabled") == "false"),
            ("password", a.get("password") == "true"), ("partly offscreen", partial),
        ) if on]
        line = f'{cls} "{text}"' if text else cls
        if desc:
            line += f' desc="{desc}"'
        if rid:
            line += f" id={rid}"
        if flags:
            line += " (" + ",".join(flags) + ")"
        box = (max(x1, 0), max(y1, 0), min(x2, W), min(y2, H))
        if line == last and last_box:
            ix = max(0, min(box[2], last_box[2]) - max(box[0], last_box[0]))
            iy = max(0, min(box[3], last_box[3]) - max(box[1], last_box[1]))
            area = min((box[2] - box[0]) * (box[3] - box[1]),
                       (last_box[2] - last_box[0]) * (last_box[3] - last_box[1]))
            if area and ix * iy / area >= 0.85:
                continue
        last, last_box = line, box
        cx1, cy1, cx2, cy2 = max(x1, 0), max(y1, 0), min(x2, W), min(y2, H)
        els.append({"line": line, "cx": (cx1 + cx2) // 2, "cy": (cy1 + cy2) // 2, "text": text, "desc": desc,
                    "scroll": scroll, "box": (cx1, cy1, cx2, cy2),
                    "sel": a.get("selected") == "true" or a.get("checked") == "true"})
        if len(els) >= maxels:
            break
    for k, e in enumerate(els):
        e["line"] = f"[{k}] " + e["line"]
    parse_ui.ime_top = ime_top
    return pkg, W, H, els


def is_blue(p):
    r, g, b = p[0], p[1], p[2]
    return b >= 170 and r <= 110 and 70 <= g <= 200 and b - r >= 100


def border_ratio(pix, W, H, box):
    """Fracao do contorno do chip que tem pixels azuis (borda de selecao). Olha um pouco para dentro e bem pouco para fora
    (a folga entre chips vizinhos e pequena e o vizinho pode estar selecionado). Botao com fundo azul nao conta."""
    x1, y1, x2, y2 = box
    h = max(1, y2 - y1)
    pin, pout = max(3, int(0.15 * h)), max(3, int(0.07 * h))
    mid_y = (y1 + y2) // 2
    fill = [(x1 + max(4, int(0.08 * (x2 - x1))), mid_y), (x2 - max(4, int(0.08 * (x2 - x1))), mid_y)]
    try:
        if all(is_blue(pix[min(max(x, 0), W - 1), min(max(y, 0), H - 1)]) for x, y in fill):
            return 0.0
        pts = []
        for x in range(x1 + 6, x2 - 5, 3):
            pts += [(x, y1, 0, 1), (x, y2 - 1, 0, -1)]
        for y in range(y1 + 6, y2 - 5, 3):
            pts += [(x1, y, 1, 0), (x2 - 1, y, -1, 0)]
        if not pts:
            return 0.0
        hits = 0
        for x, y, ix, iy in pts:
            for d in range(-pout, pin + 1):
                xx, yy = x + ix * d, y + iy * d
                if 0 <= xx < W and 0 <= yy < H and is_blue(pix[xx, yy]):
                    hits += 1
                    break
        return hits / len(pts)
    except Exception:
        return 0.0


def norm_word(t):
    return re.sub(r"[^\w']+", "", str(t).lower())


def reading_order(chips):
    rows = []
    for e in sorted(chips, key=lambda e: (e["cy"], e["cx"])):
        h = max(1, e["box"][3] - e["box"][1])
        if rows and abs(e["cy"] - rows[-1][0]["cy"]) < 0.5 * h:
            rows[-1].append(e)
        else:
            rows.append([e])
    return [e for r in rows for e in sorted(r, key=lambda x: x["cx"])]


def pick_span(chips, words):
    """Indices (em chips, ordem de leitura) das palavras pedidas. Palavras repetidas (my ... my ... my) resolvem-se pela
    sequencia mais compacta na ordem de leitura. None se nao achar."""
    nw = [norm_word(w) for w in words if norm_word(w)]
    keys = [norm_word(c["text"]) for c in chips]
    if not nw:
        return None
    best = None
    for st, k in enumerate(keys):
        if k != nw[0]:
            continue
        idx, j = [st], st
        for w in nw[1:]:
            j = next((t for t in range(j + 1, len(keys)) if keys[t] == w), None)
            if j is None:
                break
            idx.append(j)
        else:
            if best is None or idx[-1] - idx[0] < best[0]:
                best = (idx[-1] - idx[0], idx)
    return best[1] if best else None


def overlay_grid(im, cols=GRID_COLS, rows=GRID_ROWS):
    """Desenha grade A1.. sobre a imagem (Pillow). Modelos pequenos erram coordenadas, mas acertam celulas."""
    d = ImageDraw.Draw(im, "RGBA")
    w, h = im.size
    try:
        font = ImageFont.load_default(size=max(12, w // 40))
    except Exception:
        font = ImageFont.load_default()
    for c in range(1, cols):
        x = w * c // cols
        d.line([(x, 0), (x, h)], fill=(255, 0, 0, 120), width=1)
    for r in range(1, rows):
        y = h * r // rows
        d.line([(0, y), (w, y)], fill=(255, 0, 0, 120), width=1)
    for r in range(rows):
        for c in range(cols):
            label = f"{COLS[c]}{r + 1}"
            x0, y0 = w * c // cols + 2, h * r // rows + 2
            try:
                bb = d.textbbox((x0, y0), label, font=font)
                d.rectangle(bb, fill=(255, 255, 255, 170))
            except Exception:
                pass
            d.text((x0, y0), label, fill=(220, 0, 0, 255), font=font)


def pack(png, maxside=1280, grid=False):
    """PNG -> JPEG reduzido (se Pillow existir): bem mais leve e rapido; opcionalmente com grade."""
    if Image is None or not png:
        return png
    try:
        im = Image.open(io.BytesIO(png)).convert("RGB")
        im.thumbnail((maxside, maxside))
        if grid:
            overlay_grid(im)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        return buf.getvalue()
    except Exception:
        return png


def png_size(png):
    try:
        return struct.unpack(">II", png[16:24])
    except Exception:
        return 1080, 2400


def parse_json(s):
    """Tolerante: ignora <think>, cercas ```json e texto extra; devolve o primeiro objeto JSON valido."""
    if not s:
        return None
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S)
    s = re.sub(r"```(?:json)?", "", s).strip()
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", s):
        try:
            obj, _ = dec.raw_decode(s[m.start():])
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def has_media(els):
    return any(MEDIA_RE.search(e["line"].lower()) for e in els)


# ---------------------------------------------------------------- Ollama
def ollama(path, body=None, timeout=300):
    req = urllib.request.Request(
        HOST + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + os.environ["OLLAMA_API_KEY"]} if os.environ.get("OLLAMA_API_KEY") else {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ---- Ollama automatico: sobe o `ollama serve` se nao estiver rodando e derruba no fim (so se FOI o agente que subiu)
RUN_DIR = os.path.join(HOME, ".phoneagent_run")
os.makedirs(RUN_DIR, exist_ok=True)
_OLLAMA_KEEP = False


def ollama_up(timeout=2):
    try:
        ollama("/api/tags", timeout=timeout)
        return True
    except Exception:
        return False


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _stop_ollama_if_last():
    """Roda ao sair: tira este processo da lista e, se foi o agente que subiu o servidor e ninguem mais o usa, encerra."""
    try:
        os.remove(os.path.join(RUN_DIR, "users", str(os.getpid())))
    except OSError:
        pass
    if _OLLAMA_KEEP:
        return
    ud = os.path.join(RUN_DIR, "users")
    try:
        live = [f for f in os.listdir(ud) if f.isdigit() and _pid_alive(int(f))]
        for f in os.listdir(ud):
            if f.isdigit() and not _pid_alive(int(f)):
                os.remove(os.path.join(ud, f))
    except OSError:
        live = []
    pf = os.path.join(RUN_DIR, "ollama.pid")
    if live or not os.path.exists(pf):
        return
    try:
        pid = int(open(pf).read().strip())
        interrupted = False
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)  # o servidor foi iniciado em sessao propria: leva junto o runner dos modelos
            except (ProcessLookupError, PermissionError):
                break
            except KeyboardInterrupt:
                interrupted = True
                continue
            for _ in range(20):
                if not _pid_alive(pid):
                    break
                try:
                    time.sleep(0.25)
                except KeyboardInterrupt:
                    interrupted = True
                    break
            if not _pid_alive(pid):
                break
        os.remove(pf)
        if not interrupted:
            log(f"  {C.DIM}Ollama encerrado (foi iniciado pelo phoneagent){C.R}")
    except (OSError, ValueError, KeyboardInterrupt):
        pass


def ensure_ollama(autostart=True, keep=False):
    """Garante um Ollama respondendo. Retorna (ok, mensagem). So inicia se o host e local e o binario existe."""
    global _OLLAMA_KEEP
    _OLLAMA_KEEP = keep
    os.makedirs(os.path.join(RUN_DIR, "users"), exist_ok=True)
    open(os.path.join(RUN_DIR, "users", str(os.getpid())), "w").close()
    if not getattr(ensure_ollama, "_hooked", False):
        atexit.register(_stop_ollama_if_last)
        for sg in (signal.SIGTERM, signal.SIGHUP):  # fechar o Termux / kill tambem faz a faxina
            try:
                signal.signal(sg, lambda *_: sys.exit(143))
            except (ValueError, OSError):
                pass
        ensure_ollama._hooked = True
    if ollama_up():
        return True, "ja estava rodando"
    host = urllib.parse.urlparse(HOST).hostname or ""
    if not autostart:
        return False, "parado (autostart desligado)"
    if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return False, f"{HOST} e remoto e nao responde: ligue o Ollama la"
    exe = shutil.which("ollama")
    if not exe:
        return False, "binario 'ollama' nao encontrado (pkg install ollama)"
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        lf = open(os.path.join(LOG_DIR, "ollama-serve.log"), "ab")
        proc = subprocess.Popen([exe, "serve"], stdin=subprocess.DEVNULL, stdout=lf, stderr=lf, start_new_session=True)
    except OSError as e:
        return False, f"nao consegui iniciar: {e}"
    with open(os.path.join(RUN_DIR, "ollama.pid"), "w") as f:
        f.write(str(proc.pid))
    log(f"  {C.DIM}iniciando o Ollama...{C.R}")
    for _ in range(80):  # ate ~40s
        if ollama_up(1):
            return True, "iniciado pelo phoneagent (encerra sozinho no fim)"
        if proc.poll() is not None:
            return False, f"o 'ollama serve' fechou (veja {os.path.join(LOG_DIR, 'ollama-serve.log')})"
        time.sleep(0.5)
    return False, "o Ollama demorou mais de 40s para responder"


CLOUD_PREFS = ("gpt-oss:120b-cloud", "qwen3.5:cloud", "deepseek-v4-flash:cloud", "kimi-k2.6:cloud", "glm-5.1:cloud",
               "qwen3-coder:480b-cloud", "gpt-oss:20b-cloud")  # sugestoes: a lista de nuvem do Ollama muda (ollama.com/search?c=cloud)


def load_cfg():
    try:
        with open(CFG_JSON) as f:
            return json.load(f)
    except Exception:
        d = {}
        if os.path.exists(CFG):
            old = open(CFG).read().strip()
            if old:
                d["vision_model"] = old
        return d


def save_cfg(d):
    try:
        with open(CFG_JSON, "w") as f:
            json.dump(d, f, indent=1)
    except OSError:
        pass


def installed_models():
    try:
        return [x["name"] for x in ollama("/api/tags", timeout=10).get("models", [])]
    except Exception as e:
        sys.exit(f"Ollama inacessivel em {HOST} ({e}). Rode: ollama serve &")


def menu_model(title, allow_same=False):
    have = installed_models()
    cloud_have = [m for m in have if "cloud" in m]
    local = [m for m in have if m not in cloud_have]
    sugg = [m for m in CLOUD_PREFS if m not in have]
    opts = local + cloud_have + sugg
    log(f"\n{C.ORG}✻{C.R} {C.B}{title}{C.R}")
    for k, m in enumerate(opts, 1):
        tag = f" {C.DIM}☁ nuvem (sera registrado){C.R}" if m in sugg else (f" {C.DIM}☁ nuvem{C.R}" if m in cloud_have else "")
        log(f"  {k:>2}) {m}{tag}")
    if allow_same:
        log(f"   0) {C.DIM}usar so o modelo principal (sem roteamento){C.R}")
    while True:
        try:
            c = input("  numero ou nome do modelo: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "" if allow_same else sys.exit("cancelado")
        if allow_same and c in ("0", ""):
            return ""
        if c.isdigit() and 1 <= int(c) <= len(opts):
            return opts[int(c) - 1]
        if c and not c.isdigit():
            return c


def ensure_model(name):
    """Modelos de nuvem precisam estar registrados no Ollama (ollama signin + ollama pull NOME). Faz o pull sozinho."""
    if not name or "ollama.com" in HOST:
        return True
    try:
        have = [x["name"] for x in ollama("/api/tags", timeout=10).get("models", [])]
    except Exception:
        return True
    if name in have or name + ":latest" in have:
        return True
    log(f"  {C.DIM}registrando {name} no Ollama...{C.R}")
    try:
        ollama("/api/pull", {"model": name, "stream": False}, timeout=900)
        return True
    except Exception as e:
        log(f"  {C.YELLOW}! nao consegui registrar {name} ({e}). Rode no host do Ollama: ollama signin && ollama pull {name}{C.R}")
        return False


def pick_model(arg, key="vision_model", title="Modelo principal (visao + tela)", allow_same=False, force_menu=False):
    cfg = load_cfg()
    env = os.environ.get("OLLAMA_MODEL" if key == "vision_model" else "OLLAMA_TEXT_MODEL")
    if arg or env:
        pick = arg or env
    elif not force_menu and key in cfg:
        pick = cfg[key]
    elif not sys.stdin.isatty() and key != "vision_model":
        return None
    else:
        pick = menu_model(title, allow_same)
        cfg[key] = pick
        save_cfg(cfg)
    if pick and pick.lower() in ("same", "igual", "none", "off", "-"):
        pick = ""
    return pick or None


def model_has_vision(model):
    try:
        caps = ollama("/api/show", {"model": model}, timeout=15).get("capabilities")
        if isinstance(caps, list):
            return "vision" in caps
    except Exception:
        pass
    return bool(re.search(r"(vl|vision|llava|gemma[34]|minicpm-v|moondream|bakllava|granite3.2-vision|mistral-small3)", model.lower()))


# ---------------------------------------------------------------- Audio (whisper.cpp)
def find_whisper():
    for n in ("whisper-cli", "whisper-cpp"):
        p = shutil.which(n)
        if p:
            return p
    for p in (os.path.join(HOME, "whisper.cpp/build/bin/whisper-cli"), os.path.join(HOME, ".local/bin/whisper-cli")):
        if os.path.exists(p):
            return p
    return None


def find_whisper_model(name):
    env = os.environ.get("WHISPER_MODEL")
    if env and os.path.exists(env):
        return env
    for d in (os.path.join(HOME, "whisper.cpp/models"), os.path.join(HOME, ".cache/whisper")):
        p = os.path.join(d, f"ggml-{name}.bin")
        if os.path.exists(p):
            return p
    others = [p for p in glob.glob(os.path.join(HOME, "whisper.cpp/models/ggml-*.bin")) if "for-tests" not in p]
    return sorted(others)[0] if others else None


def clean_asr(text):
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*", " ", text)  # [BLANK_AUDIO], (music) ...
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- Agente
def task_tokens(task):
    txt = unicodedata.normalize("NFKD", task.lower()).encode("ascii", "ignore").decode()
    out = []
    for t in re.findall(r"[a-z0-9]{3,}", txt):
        if t not in STOP_WORDS and t not in out:
            out.append(t)
    return out[:12]


def pkg_matches(pkgs, tokens):
    """Pacotes instalados cujo nome casa com palavras da tarefa (tor -> org.torproject.torbrowser; vpn -> com.protonvpn.android)."""
    out = []
    for p in sorted(pkgs):
        if p.startswith(("com.termux", "com.android.providers")):
            continue
        segs = p.lower().split(".")
        segs = segs[1:] if len(segs) > 1 else segs
        for t in tokens:
            if any(sg == t or sg.startswith(t) or (len(t) >= 4 and t in sg) or (len(t) == 3 and sg.endswith(t)) for sg in segs):
                out.append(p)
                break
    return out[:15]


PLAN_PROMPT = ("Plan the TASK for an autonomous phone agent (Termux terminal + internet + screen). Split it into 3-10 ordered, concrete, ATOMIC goals, each verifiable on the screen or in \n"
               "the terminal. Rules: ONE goal per deliverable (each folder/file to create, each upload/send/recipient, each setting) - never \n"
               "merge several deliverables into one goal; add a goal to locate/confirm every source exists; for uploads/sends make one goal \n"
               "per file ('Upload X to Drive and confirm it appears there'). Do not add things the user did not ask for. If an app is \n"
               "ALREADY installed (list below), the goal is to open it, not to install it. Installed apps matching the task: {inst}\n"
               "Use the FEWEST goals that cover the TASK (a simple task = 1-3 goals). Results are reported in the terminal / in the final message: NEVER write goals like "
               "'show/display it on the phone screen' unless the user explicitly asked to see something on the phone. Do not plan screen work for a terminal task.\n"
               "ALSO extract: constraints = every explicit limit/prohibition/style demand in the user's words, faithfully (e.g. 'only these two files', "
               "'do not touch other files', 'leave nothing lying around'); deliverables = the concrete end results (file + destination, setting, message sent); "
               "question = ONE short question ONLY if the TASK cannot be executed without guessing something that matters and that cannot be found by looking or "
               "searching, otherwise null. Interpret 'do not make a mess / leave no loose files / limpe' as: remove only the temporary files the agent itself "
               "created; NEVER as deleting or emptying anything of the user's.\n"
               'Reply JSON {{"goals":["..."],"constraints":["..."],"deliverables":["..."],"question":null}} in the language of the TASK.\nTASK: {task}')
FINAL_GOAL = "Verify that EVERY item requested in the TASK is really done (check each one by name/evidence), then report"
AUDIT_PROMPT = ("You are a STRICT but FAIR QA auditor for an Android phone agent that wants to finish.\nTASK: {task}\nThe agent claims: {claimed}\n"
                "CONSTRAINTS from the user:\n{constraints}\nDELIVERABLES expected:\n{deliv}\n"
                "GOALS (x = done by the agent's own marking; unmarked goals may simply be forgotten bookkeeping: judge them by the evidence):\n{plan}\nFACTS:\n{facts}\n"
                "FILES THE AGENT PREPARED:\n{prep}\nSYSTEM LEDGER (measured by the harness, not by the agent):\n{ledger}\nACTIONS TAKEN (oldest first):\n{events}\n"
                "Command output listed in ACTIONS is valid evidence: the harness shows it to the user in the terminal. NEVER require output to be 'visible on the phone "
                "screen' or complain that a display was truncated; judge only whether what the TASK asked is really answered/done. Be lenient with wording; fail only for "
                "something REALLY missing or unproven. "
                "Check EACH item the TASK asks for, separately (every folder, file, recipient, upload, setting) and EVERY constraint. Count ONLY what the actions, "
                "the ledger or the attached screenshot prove; a claim without evidence is NOT done. Fail it if a constraint was broken (e.g. files the agent did not "
                "create were deleted/overwritten and APPROVED by nobody). A refused/BLOCKED attempt is not a violation. Temporary files in the scratch folder are "
                "deleted automatically by the system: never require manual cleanup. Look especially for: a deliverable never verified; a file picked in a picker that is not "
                "exactly the prepared file; an upload not verified at the destination; an archive with the wrong content. "
                'Reply JSON {{"complete":true|false,"missing":["specific missing or unverified items"],"how":"one sentence on how to finish/verify"}}')
REPLAN_PROMPT = ("An Android phone agent is stuck repeating the same actions: {loop}\nTASK: {task}\nGOALS (x = done):\n{plan}\n"
                 "FACTS:\n{facts}\nRECENT ACTIONS:\n{events}\n"
                 "Think about WHY it loops (usually: a goal is already achieved but the agent does not realize it, or it keeps "
                 "going back to a screen it already handled). Reply JSON "
                 '{{"goals":["only the goals STILL pending, in order"],"advice":"one short sentence: what to do differently now"}}')


# ====================================================================== v4
# Seguranca de arquivos (so apaga/sobrescreve o que o PROPRIO agente criou), ferramentas web, faxina automatica,
# relatorio verificado pelo sistema e memoria de projeto (PHONEAGENT.md). Tudo em codigo: nao depende do modelo obedecer.
import html as _html
import select as _select
import urllib.parse
from html.parser import HTMLParser

UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
DEL_NAMES = {"rm", "rmdir", "unlink", "shred"}
WRAP_NAMES = {"sudo", "command", "nohup", "time", "env", "nice", "busybox", "exec", "stdbuf"}
LEX_PUNCT = set(";&|()<>")
CTRL_NAMES = {"{", "}", "do", "then", "else", "elif", "if", "while", "until", "!"}
TEMPISH_RE = re.compile(r"(^|[_.\-])(tmp|temp|extracted?|scratch|cache|workdir|work|unpack(ed)?)($|[_.\-])", re.I)
DESTRUCTIVE_TASK_RE = re.compile(r"(apag|delet|remov|exclu|desinstal|uninstall|kill|mate\b|reinici|reboot|format|wipe|limpe a|esvazi)", re.I)
MEMORY_FILES = ("PHONEAGENT.md", "AGENTS.md", "CLAUDE.md")


def lex(cmd):
    """Tokens do shell respeitando aspas; pontuacao (; && | ( ) < >) vem como token proprio. None se as aspas estao quebradas."""
    try:
        sh = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=True)
        sh.whitespace_split = True
        return list(sh)
    except ValueError:
        return None


def shell_segments(toks):
    segs, cur = [], []
    for t in toks:
        if t and set(t) <= LEX_PUNCT:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def skip_prefix(seg):
    i = 0
    while i < len(seg):
        if seg[i] == "timeout":
            i += 2
        elif seg[i] in WRAP_NAMES or seg[i] in CTRL_NAMES or re.match(r"^[A-Za-z_]\w*=", seg[i]):
            i += 1
        else:
            break
    return i


# ---- web
def http_get(url, timeout=25, maxbytes=3_000_000, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "*/*",
                                                          "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(maxbytes + 1)
        return raw[:maxbytes], r.headers.get("Content-Type", ""), r.geturl(), len(raw) > maxbytes


def decode_body(raw, ctype):
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:3000], re.I)
    enc = (m.group(1).decode() if m and isinstance(m.group(1), bytes) else (m.group(1) if m else "utf-8"))
    try:
        return raw.decode(enc, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "template", "iframe", "nav", "footer"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "ul", "ol", "table", "pre",
             "blockquote", "dt", "dd"}

    def __init__(self, base=""):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.links, self.base, self._href = [], 0, [], base, None
        self._ltxt = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "a" and not self.skip:
            self._href = dict(attrs).get("href")
            self._ltxt = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "a" and self._href:
            txt = " ".join("".join(self._ltxt).split())[:80]
            href = urllib.parse.urljoin(self.base, self._href)
            if href.startswith("http") and len(self.links) < 400:
                self.links.append((txt, href))
            self._href = None

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)
            if self._href is not None:
                self._ltxt.append(data)


def html_to_text(html_text, base=""):
    p = _TextExtractor(base)
    try:
        p.feed(html_text)
    except Exception:
        pass
    txt = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.out))
    txt = re.sub(r"\n\s*\n+", "\n\n", txt).strip()
    return txt, p.links


def _strip_tags(s):
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", "", s)).split())


def parse_ddg(page):
    out, titles = [], list(re.finditer(r'<a\b([^>]*class="[^"]*result__a[^"]*"[^>]*)>(.*?)</a>', page, re.S))
    snips = list(re.finditer(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', page, re.S))
    for i, m in enumerate(titles):
        h = re.search(r'href="([^"]+)"', m.group(1))
        if not h:
            continue
        url = _html.unescape(h.group(1))
        if url.startswith("//"):
            url = "https:" + url
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "uddg" in q:
            url = q["uddg"][0]
        if "duckduckgo.com/y.js" in url or not url.startswith("http"):
            continue
        end = titles[i + 1].start() if i + 1 < len(titles) else len(page)
        sn = next((_strip_tags(s.group(1)) for s in snips if m.end() <= s.start() < end), "")
        out.append((_strip_tags(m.group(2)), url, sn))
    return out


def parse_bing(page):
    import base64
    out = []
    for blk in re.findall(r'<li class="b_algo".*?</li>', page, re.S):
        h = re.search(r'<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not h:
            continue
        url = _html.unescape(h.group(1))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "bing.com/ck/a" in url and q.get("u") and q["u"][0].startswith("a1"):
            try:
                b = q["u"][0][2:]
                url = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode()
            except Exception:
                pass
        sn = re.search(r'<p[^>]*>(.*?)</p>', blk, re.S)
        out.append((_strip_tags(h.group(2)), url, _strip_tags(sn.group(1)) if sn else ""))
    return out


def web_search_any(query, n=6):
    """Ollama web_search (se OLLAMA_API_KEY) -> DuckDuckGo -> Bing. Retorna (resultados, fonte)."""
    errs = []
    key = os.environ.get("OLLAMA_API_KEY")
    if key:
        try:
            raw, _, _, _ = http_get("https://ollama.com/api/web_search", 20, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                                    data=json.dumps({"query": query, "max_results": n}).encode())
            res = [(r.get("title", ""), r.get("url", ""), " ".join(str(r.get("content", "")).split())[:300]) for r in json.loads(raw).get("results", [])]
            if res:
                return res[:n], "ollama"
        except Exception as e:
            errs.append(f"ollama: {e}")
    try:
        raw, ct, _, _ = http_get("https://html.duckduckgo.com/html/", 20, data=urllib.parse.urlencode({"q": query}).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
        res = parse_ddg(decode_body(raw, ct))
        if res:
            return res[:n], "duckduckgo"
        errs.append("duckduckgo: sem resultados")
    except Exception as e:
        errs.append(f"duckduckgo: {e}")
    try:
        raw, ct, _, _ = http_get("https://www.bing.com/search?" + urllib.parse.urlencode({"q": query}), 20)
        res = parse_bing(decode_body(raw, ct))
        if res:
            return res[:n], "bing"
        errs.append("bing: sem resultados")
    except Exception as e:
        errs.append(f"bing: {e}")
    raise RuntimeError("; ".join(errs))


def safe_name(name):
    name = urllib.parse.unquote(os.path.basename(str(name or "").split("?")[0].split("#")[0])).strip().strip(".")
    name = re.sub(r"[^\w.\-+() ]", "_", name)[:120]
    return name or "download.bin"


def unique_path(p):
    if not os.path.lexists(p):
        return p
    root, ext = os.path.splitext(p)
    k = 1
    while os.path.lexists(f"{root}_{k}{ext}"):
        k += 1
    return f"{root}_{k}{ext}"


def download_file(url, dest, overwrite=False, sha256=None, progress=None, max_mb=6000, retries=4):
    """Baixa com retomada (Range), grava em .part e renomeia no fim. dest = pasta (termina em /) ou arquivo. Retorna dict."""
    if not re.match(r"^https?://", url or "", re.I):
        raise ValueError("so http/https")
    part, name, total, final, ctype = None, None, 0, None, ""
    for attempt in range(retries):
        have = os.path.getsize(part) if part and os.path.exists(part) else 0
        hdr = {"User-Agent": UA, "Accept": "*/*", **({"Range": f"bytes={have}-"} if have else {})}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=30) as r:
                ctype = r.headers.get("Content-Type", "")
                if final is None:
                    cd = r.headers.get("Content-Disposition", "")
                    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd, re.I)
                    name = safe_name(m.group(1) if m else urllib.parse.urlparse(r.geturl()).path)
                    if dest.endswith("/") or os.path.isdir(dest):
                        os.makedirs(dest, exist_ok=True)
                        final = os.path.join(dest, name)
                    else:
                        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                        final = dest
                    if not overwrite:
                        final = unique_path(final)
                    part = final + ".part"
                    have = 0
                    if os.path.exists(part):
                        os.remove(part)
                clen = int(r.headers.get("Content-Length") or 0)
                if r.status == 206:
                    total = have + clen
                else:
                    total, have = clen, 0
                if total and total > max_mb * 1e6:
                    raise ValueError(f"arquivo grande demais ({total / 1e6:.0f} MB > {max_mb} MB)")
                with open(part, "ab" if have else "wb") as f:
                    done = have
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
                if total and done < total:
                    raise OSError(f"incompleto ({done}/{total})")
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410, 401, 451):
                raise
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
        except (urllib.error.URLError, OSError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    size = os.path.getsize(part)
    if size == 0:
        os.remove(part)
        raise OSError("arquivo vazio")
    low = ctype.lower()
    if ("text/html" in low) and size < 1_500_000 and not final.lower().endswith((".html", ".htm")):
        os.remove(part)
        raise ValueError("o servidor devolveu uma PAGINA HTML (landing/consentimento/redirecionamento), nao o arquivo. "
                         "Use web_fetch com links:true para achar o link real de download")
    h = hashlib.sha256()
    with open(part, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    if sha256 and h.hexdigest().lower() != sha256.lower():
        os.remove(part)
        raise ValueError(f"sha256 nao confere (obtido {h.hexdigest()[:16]}...)")
    os.replace(part, final)
    return {"path": final, "size": size, "sha256": h.hexdigest(), "ctype": ctype}


def find_memory_files(start):
    """PHONEAGENT.md / AGENTS.md / CLAUDE.md da pasta atual para cima (ate o HOME) + global ~/.phoneagent/PHONEAGENT.md."""
    out, d = [], os.path.abspath(start)
    while True:
        for nm in MEMORY_FILES:
            p = os.path.join(d, nm)
            if os.path.isfile(p):
                out.append(p)
                break
        if d in (HOME, "/", os.path.dirname(d)) or len(out) >= 3:
            break
        d = os.path.dirname(d)
    g = os.path.join(HOME, ".phoneagent", "PHONEAGENT.md")
    if os.path.isfile(g):
        out.append(g)
    return out


def expand_mentions(task, cwd):
    """@arquivo na tarefa vira o caminho absoluto (estilo Claude Code)."""
    def rep(m):
        p = os.path.expanduser(m.group(1))
        p = p if os.path.isabs(p) else os.path.join(cwd, p)
        return os.path.abspath(p) if os.path.exists(p) else m.group(0)
    return re.sub(r"(?<!\S)@([^\s,;]+)", rep, task)


class V4Mixin:
    """Metodos novos do Agent (v4)."""

    def v4_init(self):
        try:
            self.start_cwd = os.getcwd()
        except (FileNotFoundError, OSError):
            self.start_cwd = HOME
            try:
                os.chdir(HOME)
            except OSError:
                pass
        self.owned, self.approved, self.led, self.deleted_by_janitor = set(), set(), [], []
        self.scratch, self.constraints, self.task_deliv, self.destructive_ok = "", [], [], False
        self.blocked_foreign, self.cmd_total, self.cmd_errs, self.think = 0, 0, 0, "medium"
        self.empty_streak, self.mem_text, self.last_ls_cwd, self.can_ask = 0, "", None, True
        self.keep_tmp, self.task_text, self.final_deliv = False, "", []

    # ---- caminhos / posse
    @staticmethod
    def norm(p):
        p = os.path.normpath(p)
        return os.path.join(os.path.realpath(os.path.dirname(p) or "/"), os.path.basename(p)) if os.path.basename(p) else p

    def own(self, p):
        if p:
            self.owned.add(self.norm(p))

    @staticmethod
    def _under(q, roots):
        return any(q == o or q.startswith(o.rstrip("/") + "/") for o in roots)

    def is_owned(self, p):
        return self._under(self.norm(p), self.owned)

    def can_touch(self, p):
        q = self.norm(p)
        return self._under(q, self.owned) or self._under(q, self.approved)

    def protected(self, p):
        q = self.norm(p)
        hard = {"/", "/sdcard", "/storage", "/storage/emulated", "/storage/emulated/0", "/data", "/data/data", "/data/app", "/system",
                "/vendor", "/sbin", os.environ.get("PREFIX", "/usr")}
        hard |= {self.norm(HOME), self.norm(os.path.join(HOME, "storage"))}
        home = self.norm(HOME)
        return q in hard or home.startswith(q.rstrip("/") + "/")

    def expand_target(self, tok, cwd):
        """Lista de caminhos absolutos que o token alcanca, [] se o glob nao casa, None se nao da para saber ($var, $(..))."""
        t = tok.replace("${HOME}", HOME).replace("$HOME", HOME).replace("${PA_TMP}", self.scratch).replace("$PA_TMP", self.scratch)
        if "$" in t or "`" in t:
            return None
        p = os.path.expanduser(t)
        p = p if os.path.isabs(p) else os.path.join(cwd, p)
        if any(ch in p for ch in "*?["):
            import glob as _g
            return [os.path.normpath(h) for h in _g.glob(p)]
        return [os.path.normpath(p)]

    def analyze_cmd(self, cmd):
        """Le o comando SEM executar: alvos de delete, sobrescritas, candidatos a 'novos caminhos' e o resto (para a checagem de perigo)."""
        info = {"dels": [], "unknown": False, "overwrite": [], "cand": [], "rest": cmd}
        toks = lex(cmd)
        if toks is None:
            info["unknown"] = bool(re.search(r"\b(rm|rmdir|unlink|shred)\b|-delete\b", cmd))
            return info
        cur, rest = self.cwd, []
        for seg in shell_segments(toks):
            i = skip_prefix(seg)
            if i >= len(seg):
                continue
            name, args = os.path.basename(seg[i]), seg[i + 1:]
            is_del = False
            if name == "cd":
                if args and args[0] != "-":
                    q = os.path.expanduser(args[0])
                    cur = os.path.normpath(q if os.path.isabs(q) else os.path.join(cur, q))
                elif not args:
                    cur = HOME
            elif name in DEL_NAMES:
                is_del, endopts = True, False
                for t in args:
                    if t == "--" and not endopts:
                        endopts = True
                    elif not (t.startswith("-") and not endopts):
                        info["dels"].append((t, cur, False))
            elif name == "find":
                roots = []
                for t in args:
                    if t.startswith("-") or t in ("!", "(", ")"):
                        break
                    roots.append(t)
                deleting = "-delete" in args or any(t in ("-exec", "-execdir", "-ok", "-okdir") and j + 1 < len(args)
                                                    and os.path.basename(args[j + 1]) in DEL_NAMES for j, t in enumerate(args))
                if deleting:
                    is_del = True
                    info["dels"] += [(r, cur, True) for r in (roots or ["."])]
            elif name == "xargs" and any(os.path.basename(t) in DEL_NAMES for t in args):
                is_del, info["unknown"] = True, True
            elif name in ("cp", "mv", "install") and not any(t in ("-n", "--no-clobber") for t in args):
                pos = [t for t in args if not t.startswith("-")]
                if len(pos) >= 2:
                    dst = self.expand_target(pos[-1], cur)
                    if dst and len(dst) == 1:
                        d = dst[0]
                        for s in pos[:-1]:
                            tgt = os.path.join(d, os.path.basename(s.rstrip("/"))) if os.path.isdir(d) else d
                            if os.path.isfile(tgt):
                                info["overwrite"].append(tgt)
            if not is_del:
                rest.append(" ".join(seg))
            for t in args:
                if t.startswith("-") or len(info["cand"]) >= 80:
                    continue
                t = t.lstrip(">")
                if t and ("/" in t or t.startswith(("~", ".")) or re.search(r"\.\w{1,6}$", t)):
                    ps = self.expand_target(t, cur)
                    if ps and len(ps) == 1:
                        info["cand"].append(ps[0])
        for k, t in enumerate(toks[:-1]):  # redirecionamentos: > arquivo
            if t in (">", ">>", ">|") and len(info["cand"]) < 80:
                ps = self.expand_target(toks[k + 1], self.cwd)
                if ps and len(ps) == 1:
                    info["cand"].append(ps[0])
        info["rest"] = " ; ".join(rest)
        return info

    def snap_new(self, info):
        """Antes de rodar: o que ja existe entre os caminhos citados (e dentro das pastas citadas)."""
        pre = {p: os.path.lexists(p) for p in info["cand"]}
        dirs = [p for p, ex in pre.items() if ex and os.path.isdir(p)]
        for d in dirs:
            for p in info["cand"]:
                c = os.path.join(d, os.path.basename(p))
                pre.setdefault(c, os.path.lexists(c))
        return pre

    def track_new(self, pre):
        """Depois de rodar: o que NAO existia e agora existe foi criado pelo comando => e do agente."""
        for p, existed in pre.items():
            if not existed and os.path.lexists(p):
                self.own(p)
                self.led.append(f"created {p}")

    # ---- confirmacao humana (so para tocar em arquivo que NAO e do agente)
    def ask_human(self, question, timeout=120):
        self.notify("❓ phoneagent precisa de você", question[:300], False)
        if not sys.stdin.isatty():
            return False
        with _LOCK:
            sys.stdout.write(f"\n  {C.YELLOW}{C.B}? {question}{C.R}\n  Permitir? [s/N] (sem resposta em {timeout}s = NAO): ")
            sys.stdout.flush()
        try:
            r, _, _ = _select.select([sys.stdin], [], [], timeout)
            ans = sys.stdin.readline().strip().lower() if r else ""
        except Exception:
            ans = ""
        print()
        return ans in ("s", "sim", "y", "yes")

    def delete_guard(self, cmd):
        """BLOQUEIA (mesmo com force) apagar/sobrescrever o que o agente nao criou; so segue com o OK do humano."""
        info = self.analyze_cmd(cmd)
        foreign, hard = [], []
        for tok, cwd, _sub in info["dels"]:
            ps = self.expand_target(tok, cwd)
            if ps is None:
                foreign.append(f"{tok} (caminho dinamico)")
                continue
            for p in ps:
                if self.protected(p):
                    hard.append(p)
                elif not self.can_touch(p):  # sem checar existencia: o root enxerga o que o Termux nao ve
                    foreign.append(p + ("/ (TUDO dentro, via find)" if _sub else ""))
        if info["unknown"]:
            foreign.append("(alvos vindos de pipe/xargs/aspas quebradas)")
        over = [p for p in info["overwrite"] if not self.can_touch(p)]
        if hard:
            self.blocked_foreign += 1
            self.led.append("BLOCKED hard-protected delete: " + ", ".join(hard[:4]))
            return ("BLOCKED (not executed, no override): this would delete a protected location (" + ", ".join(hard[:3])
                    + "). Delete only the specific files YOU created (inside $PA_TMP or paths you made).")
        if not foreign and not over:
            return None
        shown = lambda L: ", ".join(x if " (" in x else (os.path.basename(x.rstrip("/")) or x) for x in L[:6]) + (f" … (+{len(L) - 6})" if len(L) > 6 else "")
        parts = ([f"APAGAR {len(foreign)} item(ns) que o agente NÃO criou: {shown(foreign)}"] if foreign else []) \
            + ([f"SOBRESCREVER {len(over)} arquivo(s) que o agente NÃO criou: {shown(over)}"] if over else [])
        if self.can_ask and self.ask_human("O agente quer " + " e ".join(parts) + ".  Comando: " + _trim(cmd, 120)):
            for p in over + [x.split(" (")[0].rstrip("/") for x in foreign if x.startswith("/")]:
                self.approved.add(self.norm(p))
            for tok, cwd, sub in info["dels"]:
                if sub:
                    for r in self.expand_target(tok, cwd) or []:
                        self.approved.add(self.norm(r))
            self.led.append("user APPROVED: " + " and ".join(parts)[:200])
            return None
        self.blocked_foreign += 1
        self.led.append("BLOCKED foreign: " + " and ".join(parts)[:200])
        return ("BLOCKED (not executed; \"force\" does not apply): " + " and ".join(parts) + ". These files belong to the USER, not to you. "
                "Leave them alone. Delete only what you created (temporary files live in $PA_TMP and are removed automatically). "
                "For an overwrite, choose another file name. If the TASK truly needs it, say so in the done message instead.")

    # ---- faxina e relatorio
    def make_scratch(self):
        self.scratch = os.path.join(WORK, "run-" + time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}")
        os.makedirs(self.scratch, exist_ok=True)
        try:  # sobras de execucoes que morreram (kill/queda de energia) com mais de 1 dia
            for e in os.scandir(WORK):
                if e.is_dir() and e.name.startswith("run-") and time.time() - e.stat().st_mtime > 86400:
                    shutil.rmtree(e.path, ignore_errors=True)
        except OSError:
            pass
        self.owned = {self.norm(self.scratch)}
        self.approved, self.led, self.deleted_by_janitor = set(), [], []
        self.blocked_foreign = self.cmd_total = self.cmd_errs = self.empty_streak = 0

    def force_rm(self, p):
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.lexists(p):
                os.remove(p)
        except OSError:
            pass
        if os.path.lexists(p) and getattr(self, "dev", None):  # criado por comando root: tenta como root
            self.dev.sh("rm -rf " + shlex.quote(p), timeout=60)
        return not os.path.lexists(p)

    def janitor(self):
        """Apaga SO o que o agente criou e e temporario: o SCRATCH inteiro + criados com nome tmp/extracted que nao sao entregas."""
        if self.keep_tmp or not self.scratch:
            return
        keep = {self.norm(self.resolve_path(x)) for x in self.final_deliv + self.task_deliv if isinstance(x, str) and ("/" in x or x.startswith("~"))}
        task_l = self.task_text.lower()
        for p in sorted(self.owned, key=len, reverse=True):
            if p == self.norm(self.scratch) or not os.path.lexists(p):
                continue
            base = os.path.basename(p.rstrip("/"))
            if TEMPISH_RE.search(base) and base.lower() not in task_l and not self._under(p, keep) \
                    and not any(k.startswith(p + "/") or k == p for k in keep):
                if self.force_rm(p):
                    self.deleted_by_janitor.append(p)
        if os.path.lexists(self.scratch) and self.force_rm(self.scratch):
            self.deleted_by_janitor.append(self.scratch)
        self.owned = {o for o in self.owned if os.path.lexists(o)}

    def report_lines(self):
        """Fatos medidos pelo SISTEMA (nao pelo modelo)."""
        lines, scr = [], self.norm(self.scratch) if self.scratch else ""
        made = [p for p in sorted(self.owned) if p != scr and not self._under(p, [scr] if scr else []) and os.path.lexists(p)]
        tops = [p for p in made if not any(p.startswith(q + "/") for q in made)]
        for p in tops[:12]:
            if os.path.isdir(p):
                lines.append(f"pasta  {p}/")
            else:
                s = os.path.getsize(p)
                lines.append(f"arquivo {p}  ({s / 1e6:.1f} MB)" if s >= 100_000 else f"arquivo {p}  ({s} bytes)")
        if len(tops) > 12:
            lines.append(f"… +{len(tops) - 12} itens")
        if self.blocked_foreign:
            lines.append(f"proteção: barrei {self.blocked_foreign} tentativa(s) de apagar/sobrescrever arquivos que não eram meus")
        if self.cmd_errs:  # so mostra o que importa: temporarios apagados e comandos ok ficam so no log
            lines.append(f"comandos: {self.cmd_total - self.cmd_errs} ok, {self.cmd_errs} com erro")
        for x in self.deleted_by_janitor[:5]:
            flog("faxina: removi " + x)
        return lines

    # ---- ferramentas web
    def web_search(self, a):
        q = str(a.get("query") or a.get("q") or "").strip()
        if not q:
            return 'error: informe "query"'
        try:
            n = max(1, min(int(a.get("n") or 6), 10))
        except (TypeError, ValueError):
            n = 6
        try:
            res, src = web_search_any(q, n)
        except Exception as e:
            return (f"error: busca falhou ({_trim(e, 200)}). Alternativas: open_url com palavras soltas abre a busca do Google no navegador; "
                    "ou web_fetch/open_url direto num site oficial que voce ja conheca (ex.: o dominio do orgao). Sem internet? curl -sI https://duckduckgo.com | head -1")
        return f"[{src}] {len(res)} resultados para: {q}\n" + "\n".join(f"{i}. {t}\n   {u}\n   {s[:220]}" for i, (t, u, s) in enumerate(res, 1))

    def web_fetch(self, a):
        url = str(a.get("url") or "").strip()
        if not re.match(r"^https?://", url, re.I):
            return "error: informe uma url http(s) completa"
        try:
            mx = max(500, min(int(a.get("max_chars") or 6000), 20000))
        except (TypeError, ValueError):
            mx = 6000
        try:
            raw, ct, final, cut = http_get(url, 25)
        except urllib.error.HTTPError as e:
            return f"error: HTTP {e.code} em {url}"
        except Exception as e:
            return f"error: nao consegui abrir ({_trim(e, 160)})"
        low = ct.lower()
        if raw[:4] in (b"PK\x03\x04", b"\x7fELF") or ("text" not in low and "json" not in low and "xml" not in low and "html" not in low and b"\0" in raw[:1024]):
            return f"binary content ({ct or 'unknown'}, {len(raw)}+ bytes) at {final}. Use the download action."
        body, links = decode_body(raw, ct), []
        if "html" in low or body.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
            body, links = html_to_text(body, final)
        out = body[:mx] + (f"\n...[cortado: {len(body)} chars; use max_chars maior]" if len(body) > mx else "")
        if a.get("links") and links:
            seen, ls = set(), []
            for t, h in links:
                if h not in seen:
                    seen.add(h)
                    ls.append(f"- {t or '(sem texto)'} -> {h}")
            out += "\n\nLINKS:\n" + "\n".join(ls[:40])
        return f"[{final}]\n{out}"

    def download(self, a):
        url = str(a.get("url") or "").strip()
        dest = os.path.expanduser(str(a.get("path") or a.get("dest") or self.cwd))
        dest = dest if os.path.isabs(dest) else os.path.join(self.cwd, dest)
        if a.get("path") and not str(a.get("path")).endswith("/") and not os.path.isdir(dest) and "." not in os.path.basename(dest):
            dest += "/"
        if os.path.exists(dest) and not os.path.isdir(dest) and not a.get("overwrite") and not self.can_touch(dest):
            dest = os.path.dirname(dest) + "/"  # nao sobrescreve arquivo alheio: baixa com nome livre
        t0 = time.time()

        def prog(d, t):
            if self.spin:
                self.spin.set(f" · {d / 1e6:.1f}" + (f"/{t / 1e6:.1f}" if t else "") + " MB")
        try:
            r = download_file(url, dest, overwrite=bool(a.get("overwrite")) and self.can_touch(dest), sha256=a.get("sha256"), progress=prog)
        except urllib.error.HTTPError as e:
            return f"error: HTTP {e.code} ao baixar. Confira o link (web_search / web_fetch links:true)"
        except Exception as e:
            return f"error: download falhou ({_trim(e, 260)})"
        self.own(r["path"])
        self.led.append(f"created {r['path']}")
        chk = self.check_file(r["path"], "")
        return f"ok: {r['path']}  {r['size'] / 1e6:.2f} MB em {time.time() - t0:.0f}s  sha256={r['sha256'][:16]}…  [{r['ctype']}]" + ("\n" + chk if chk else "")

    # ---- contexto
    def env_block(self, n):
        out = [f"ENVIRONMENT: {time.strftime('%Y-%m-%d %H:%M')} · WORKING DIRECTORY: {self.cwd} (where the user launched you; \"here\"/\"aqui\"/\"this folder\" = this) · "
               f"SCRATCH $PA_TMP={self.scratch} (all temporary files go here; auto-deleted when the task ends)"]
        if n <= 2 or self.cwd != self.last_ls_cwd:
            try:
                names = sorted(os.listdir(self.cwd))
                out.append("FILES HERE: " + ", ".join(names[:25]) + (f" … (+{len(names) - 25})" if len(names) > 25 else "") if names else "FILES HERE: (empty)")
            except OSError:
                pass
            self.last_ls_cwd = self.cwd
        if self.mem_text:
            out.append("USER/PROJECT INSTRUCTIONS (PHONEAGENT.md; follow them):\n" + self.mem_text)
        if self.constraints:
            out.append("CONSTRAINTS (the user's own limits; breaking one = failed task):\n" + "\n".join("- " + c for c in self.constraints))
        if self.task_deliv:
            out.append("DELIVERABLES (must exist/be true at the end):\n" + "\n".join("- " + d for d in self.task_deliv))
        bc = self.brain_context(self.cur_pkg)
        if bc:
            out.append(bc)
        return "\n".join(out)

    def load_memory(self):
        parts = []
        for p in find_memory_files(self.cwd):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    parts.append(f"[{p}]\n" + f.read().strip()[:3000])
            except OSError:
                pass
        self.mem_text = "\n\n".join(parts)[:6000]
        if parts:
            log(f"  {C.DIM}instruções carregadas: {', '.join(find_memory_files(self.cwd))}{C.R}")


class Agent(V4Mixin, brain.BrainMixin):
    kb_shown, kb_top = False, None  # preenchidos por observe()
    sel_n, sel_info, sel_detect = None, "", False  # exercicio "Select N words" (preenchidos por observe())

    text_model, route, mode, term_only, allow_risky, text_bad_until, last_route, spin = None, "auto", "auto", False, False, 0, "", None
    simple, left_term, last_model, screen_task = False, False, None, ""

    def prompt_for(self, task):
        """Terminal -> prompt de terminal; tela -> prompt enxuto (o completo, de licoes/quiz, so quando o pedido e uma licao)."""
        if self.term_only:
            return SYSTEM_TERM
        return SYSTEM if LESSON_RE.search(task) else SYSTEM_SCREEN

    def __init__(self, dev, model, vision=True, delay=1.0, step=False, home=True, ctx=16384, timeout=180,
                 imgmax=1280, asr_model="base", audio_lang="auto"):
        self.dev, self.model, self.vision, self.delay, self.step, self.home = dev, model, vision, delay, step, home
        self.ctx, self.timeout, self.imgmax = ctx, timeout, imgmax
        self.asr_model, self.audio_lang = asr_model, audio_lang
        self.els, self.W, self.H = [], 1080, 2400
        self.debug, self.audio = False, True
        self.transcript, self.transcript_n, self.transcript_texts = "", 0, set()
        self.cur_step, self.act_kind, self.cur_texts = 0, None, set()
        self.last_png, self.zoom_b64, self.grid_mode, self.read_step = None, None, False, -99
        self.vol_set = False
        self.cwd = HOME
        self.sent_files = {}
        self.plan, self.facts, self.advice, self.pkgs, self.pkgs_step = [], [], "", set(), -99
        self.dep_status = {}  # pacotes que NAO existem (missing); "instalado" agora e verificado de verdade (pip show / dpkg -s)
        self.dep_fail, self.cmd_fail, self.cmd_tail, self.stats, self.t_task = {}, {}, {}, {}, time.time()
        self.loop_hits, self.last_loop_step, self.loop_ban, self.loop_ban_until, self.ban_blocks = 0, -99, set(), 0, 0
        self.final_msg, self.notify_on, self.cur_pkg, self.task_toks = "", True, "", []
        self.prepared, self.log_all, self.done_rejects, self.audit_runs, self._notif = {}, [], 0, 0, []
        atexit.register(self.flush_notify)
        self.audio_max = 240
        self.tr, self.reads, self.events, self.tid_n = [], [], [], 0
        self.audio_fails, self.audio_block_until, self.player_opened = 0, 0, False
        self.last_tid, self.last_capture_step = None, -99
        self.whisper, self.wmodel = find_whisper(), find_whisper_model(asr_model)
        self.asr_ok = bool(self.whisper and self.wmodel and shutil.which("ffmpeg") and shutil.which("termux-microphone-record"))
        os.makedirs(WORK, exist_ok=True)
        self.v4_init()
        self._parse_ui = parse_ui
        self.brain_init()
        self.sys_prompt = SYSTEM

    # ---- observacao
    def shoot(self):
        try:
            png = self.dev.screenshot()
        except Exception as e:
            log(f"    (screenshot falhou: {e})")
            return None
        return png if png and png[:8] == PNG_SIG else None

    def observe(self):
        pkg, els, shot = self.observe_raw()
        # teclado aberto sem nenhum campo de texto em foco (ex.: exercicio de palavras) so esconde a tela: fecha.
        if (self.kb_shown and self.kb_top is not None and not self.focused_edit(els)
                and self.cur_step - getattr(self, "kb_hide_step", -99) > 1):
            flog("    (teclado aberto sem campo em foco: escondendo para enxergar a tela inteira)")
            self.kb_hide_step = self.cur_step
            self.dev.sh("input keyevent 4")
            time.sleep(0.8)
            pkg, els, shot = self.observe_raw()
        return pkg, els, shot

    @staticmethod
    def focused_edit(els):
        return any("editable" in e["line"] and "focused" in e["line"] for e in els)

    def observe_raw(self):
        with ThreadPoolExecutor(3) as ex:  # screenshot, dump e estado do teclado em paralelo: menos espera por turno
            f_png = ex.submit(self.shoot) if self.vision else None
            f_xml = ex.submit(self.dev.dump)
            f_kb = ex.submit(self.keyboard_state)
            xml = f_xml.result()
            png = f_png.result() if f_png else None
            kb_shown, kb_rect = f_kb.result()
        pkg, W, H, els = parse_ui(xml)
        ime_top = parse_ui.ime_top
        if png is None and len(els) < 4:
            png = self.shoot()
        shot, self.grid_mode = None, False
        if png:
            W, H = png_size(png)
            self.grid_mode = len(els) < 4
            shot = base64.b64encode(pack(png, self.imgmax, self.grid_mode)).decode()
        if not els:
            log("    (sem arvore de UI; usando screenshot com grade)")
        src = "dump" if ime_top is not None else ("dumpsys" if kb_rect else None)
        top = ime_top if ime_top is not None else (kb_rect[1] if kb_rect else None)
        self.kb_top = top if (top is not None and top >= 0.25 * H) else None
        self.kb_shown = bool(self.kb_top is not None or kb_shown)
        if self.kb_shown and getattr(self, "kb_logged", None) != (self.kb_top, src):
            self.kb_logged = (self.kb_top, src)
            flog(f"    (teclado aberto; topo y={self.kb_top} via {src or 'so mInputShown'})")
        self.els, self.W, self.H, self.last_png = els, W, H, png
        self.cur_texts = {e["text"] for e in els if len(e["text"]) > 3}
        self.sel_n, self.sel_info = None, ""
        try:
            self.sel_state(png, els, W, H)
        except Exception as e:
            log(f"    (leitura de chips selecionados falhou: {e})")
        return pkg, els, shot

    # ---- LLM
    def post_chat(self, messages, fmt=True, timeout=None, predict=1200, model=None, think=None):
        model = model or self.model
        low = model.lower()
        opts = {"temperature": 0.1, "num_ctx": self.ctx, "num_predict": predict}
        body = {"model": model, "stream": False, "messages": messages, "keep_alive": "30m", "options": opts}
        if "gpt-oss" in low:
            body["think"] = think or "medium"  # gpt-oss aceita niveis (nao true/false) e ignora "format"
        elif fmt:
            body["format"] = "json"
        if "gpt-oss" in low or "cloud" in low:
            opts["num_predict"] = max(predict, 3000)  # modelos que "pensam" gastam tokens antes da resposta
        t = time.time()
        msg = ollama("/api/chat", body, timeout=timeout or self.timeout).get("message", {})
        st = self.stats.setdefault(model, [0, 0.0])
        st[0] += 1
        st[1] += time.time() - t
        return msg.get("content", "")

    # ---- roteamento: texto -> modelo forte de texto; tela -> modelo de visao; "hybrid" = visao descreve, texto decide
    def tm(self):
        ok = self.text_model and self.route != "vision" and time.time() > self.text_bad_until
        return self.text_model if ok else self.model

    def pick_for(self, imgs):
        return self.tm() if not imgs else self.model

    def fallback_text(self, reason, permanent):
        self.text_bad_until = 1e18 if permanent else time.time() + 180
        log(f"  {C.YELLOW}! modelo de texto indisponivel ({_trim(reason, 110)}); usando {self.model} por enquanto{C.R}")
        if permanent:
            log(f"  {C.DIM}dica: modelos de nuvem pedem 'ollama signin' no host do Ollama (ou OLLAMA_API_KEY){C.R}")

    def describe(self, b64):
        p = ("Describe this phone screenshot for another AI that cannot see it: app/screen name, ALL visible text, buttons, dialogs, "
             "errors, toggles and their state, images/charts. Exact and compact (max 200 words).")
        try:
            return self.post_chat([{"role": "user", "content": p, "images": [b64]}], fmt=False, timeout=120, predict=500, model=self.model).strip()
        except Exception:
            return ""

    def chat(self, user, img):
        last, i, retry = "", 0, 2
        imgs = [x for x in (img, self.zoom_b64) if x]
        hybrid = bool(imgs and self.tm() != self.model and self.route == "hybrid")  # auto: tela = modelo de visao decide; texto puro = modelo de texto
        kind = "visão"
        if hybrid:
            notes = [("ZOOM: " if k else "") + d for k, d in enumerate(self.describe(b) for b in imgs) if d]
            if notes:
                user += "\n\nVISION NOTES (a vision model looked at the screenshot for you; trust it for what is on screen):\n" + "\n".join(notes)
                imgs, self.zoom_b64, kind = [], None, "híbrido"
        model = self.pick_for(imgs)
        self.last_model = model
        if not imgs:
            kind = kind if kind == "híbrido" else "texto"
        self.last_route = f"{kind} · {model}"
        if self.spin:
            self.spin.set(f" · {model}")
        plan = [(bool(imgs), True), (False, True), (False, False)] if model == self.model else [(False, True), (False, False)]
        while i < len(plan):
            use_img, fmt = plan[i]
            msg = {"role": "user", "content": user}
            if use_img:
                msg["images"] = imgs
            try:
                text = self.post_chat([{"role": "system", "content": self.sys_prompt}, msg], fmt, model=model, think=self.think)
            except urllib.error.HTTPError as e:
                last = e.read().decode("utf-8", "replace")[:200]
                if model != self.model and e.code in (401, 403, 404, 410):
                    self.fallback_text(f"HTTP {e.code}: {last}", True)
                    return self.chat(user, img)
                if e.code in (401, 404, 410):
                    raise RuntimeError(last)
                if e.code in (429, 502, 503, 504) and retry > 0:
                    retry -= 1
                    log(f"    (Ollama {e.code}; tentando de novo)")
                    time.sleep(3)
                    continue
                if use_img and "image" in last.lower():
                    log("    (modelo recusou imagem; seguindo so com texto)")
                    self.vision = False
                i += 1
                continue
            except Exception as e:  # timeout / rede
                last = f"Ollama inacessivel/lento: {e}"
                if retry > 0:
                    retry -= 1
                    log("    (Ollama sem resposta; tentando de novo)")
                    time.sleep(2)
                    continue
                i += 1
                continue
            self.zoom_b64 = None
            if text.strip():
                return text
            i += 1
        if model != self.model:
            self.fallback_text(last or "resposta vazia", False)
            return self.chat(user, img)
        raise RuntimeError(last or "resposta vazia do modelo")

    @staticmethod
    def norm_action(d):
        """Aceita variacoes comuns: {"tool":"tap"}, {"actions":[{...}]}. None se nao for uma acao."""
        if isinstance(d, dict) and "action" not in d:
            if isinstance(d.get("actions"), list) and d["actions"] and isinstance(d["actions"][0], dict):
                d = d["actions"][0]
            else:
                for k in ("tool", "name", "function", "next_action"):
                    if isinstance(d.get(k), str):
                        d = {**{x: v for x, v in d.items() if x != k}, "action": d[k]}
                        break
        return d if isinstance(d, dict) and isinstance(d.get("action"), str) else None

    def decide(self, user, shot):
        """Chama o modelo ate 3x no mesmo turno se a resposta nao for uma acao JSON valida (cada re-leitura de tela custa ~3s)."""
        raw = ""
        for k in range(3):
            msg = user if k == 0 else (user + '\n\nERROR: your previous reply was not ONE valid JSON object with an "action". '
                                       'Reply with ONLY: {"thought":"short","action":"...", ...params}')
            raw = self.chat(msg, shot if k < 2 else None)
            a = self.norm_action(parse_json(raw))
            if a:
                return a
            log(f"    resposta invalida ({k + 1}/3): {raw.strip()[:160]!r}")
        return None

    def ocr(self, png):
        """Le o texto de um screenshot com o modelo de visao (quando a arvore de UI nao tem texto)."""
        img = base64.b64encode(pack(png, self.imgmax, False)).decode()
        try:
            return self.post_chat([{"role": "user", "content": OCR_PROMPT, "images": [img]}], fmt=False, predict=1200)
        except Exception as e:
            log(f"    (ocr falhou: {e})")
            return ""

    # ---- coordenadas / alvos
    def element(self, a):
        try:
            return self.els[int(a["index"])]
        except Exception:
            return None

    def cell_xy(self, cell, fx=0.5, fy=0.5):
        m = re.match(r"^\s*([A-Fa-f])\s*(\d{1,2})\s*$", str(cell))
        if not m:
            return None
        c, r = COLS.index(m.group(1).upper()), int(m.group(2)) - 1
        if not 0 <= r < GRID_ROWS:
            return None
        fx, fy = min(max(float(fx), 0.05), 0.95), min(max(float(fy), 0.05), 0.95)
        x = int((c + fx) * self.W / GRID_COLS)
        y = int((r + fy) * self.H / GRID_ROWS)
        return min(x, self.W - 1), min(y, self.H - 1)

    def target_xy(self, a):
        """Alvo por index | cell | x,y. Retorna (xy|None, erro|None)."""
        if a.get("index") is not None:
            e = self.element(a)
            return ((e["cx"], e["cy"]), None) if e else (None, "error: indice invalido")
        if a.get("cell"):
            xy = self.cell_xy(a["cell"], a.get("fx", .5), a.get("fy", .5))
            return (xy, None) if xy else (None, "error: celula invalida (use A1..F12)")
        if a.get("x") is not None and a.get("y") is not None:
            nx, ny = float(a["x"]), float(a["y"])
            if not (0 <= nx <= 1000 and 0 <= ny <= 1000):
                return None, "error: x e y devem estar entre 0 e 1000"
            return (min(int(nx / 1000 * self.W), self.W - 1), min(int(ny / 1000 * self.H), self.H - 1)), None
        return None, None

    def keyboard_state(self):
        """(mostrando, retangulo|None). Le a janela InputMethod do dumpsys window: ela existe mesmo com o teclado fechado e o
        'frame' dela e a tela toda; o que vale e 'isVisible=true' + 'touchable region' (area real do teclado)."""
        head = self.dev.sh("dumpsys input_method 2>/dev/null | grep -E 'mInputShown'", timeout=10)
        win = self.dev.sh("dumpsys window windows 2>/dev/null", timeout=15)
        m = IME_WIN_RE.search(win)
        if not m:
            return "mInputShown=true" in head, None
        nxt = IME_NEXT_RE.search(win, m.end())
        blk = win[m.end():nxt.start() if nxt else m.end() + 20000]
        if "isVisible=true" not in blk:
            return False, None
        r = IME_REGION_RE.search(blk)
        rect = tuple(map(int, r.groups())) if r and int(r.group(4)) > int(r.group(2)) else None
        return rect is not None, rect

    def uncover(self, e):
        """Toque por indice usa as coordenadas do dump. Se o teclado cobre o alvo, o toque cai numa TECLA (letra extra no campo).
        Entao esconde o teclado (BACK) e acha o alvo de novo no dump novo. Retorna (elemento|None, erro|None)."""
        shown, r = self.keyboard_state()
        top = self.kb_top if self.kb_top is not None else (r[1] if r else None)
        if not (shown or self.kb_shown):
            return e, None
        if top is not None:
            if e["cy"] < top:
                return e, None
        elif "editable" in e["line"] or e["cy"] < 0.4 * self.H:  # topo desconhecido: so a parte de baixo e suspeita
            return e, None
        log("    (teclado cobre o alvo: escondendo o teclado antes de tocar)")
        self.dev.sh("input keyevent 4")
        time.sleep(0.8)
        _, _, _, els = parse_ui(self.dev.dump())
        if e["text"] or e["desc"]:
            for n in els:
                if n["text"] == e["text"] and n["desc"] == e["desc"]:
                    self.els = els
                    return n, None
        return None, ("error: the on-screen keyboard was covering that element, so I hid the keyboard and did NOT tap. "
                      "Read the new screen and tap again (scroll if the button is off-screen).")

    def tap(self, xy):
        self.dev.sh(f"input tap {xy[0]} {xy[1]}")

    # ---- audio: reproduzir + gravar o microfone + whisper.cpp
    def audio_playing(self):
        """True/False se algum app esta reproduzindo audio; None se nao der para saber."""
        out = self.dev.sh("a=$(dumpsys audio 2>/dev/null | grep -ci 'state:started'); "
                          "b=$(dumpsys media_session 2>/dev/null | grep -ci 'state=3'); echo $a $b", timeout=8).split()
        if len(out) == 2 and all(x.isdigit() for x in out):
            return int(out[0]) + int(out[1]) > 0
        return None

    def set_volume(self):
        if not self.vol_set:
            self.dev.sh("cmd media_session volume --stream 3 --set 15 >/dev/null 2>&1; "
                        "settings put system volume_music_speaker 15 >/dev/null 2>&1; true", timeout=8)
            self.vol_set = True

    def rec_stop(self):
        try:
            subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=10)
        except Exception:
            pass

    def rec_start(self, path, limit=0):
        """limit=0: sem limite (nos paramos manualmente). Tenta com e sem -r/-c."""
        for extra in (["-r", "16000", "-c", "1"], []):
            try:
                r = subprocess.run(["termux-microphone-record", "-f", path, "-l", str(int(limit)), "-e", "aac"] + extra,
                                   capture_output=True, text=True, timeout=15)
            except Exception as e:
                log(f"    (nao consegui iniciar a gravacao: {e})")
                return False
            if r.returncode == 0:
                return True
        return False

    def rec_active(self):
        try:
            r = subprocess.run(["termux-microphone-record", "-i"], capture_output=True, text=True, timeout=10)
            return bool(re.search(r'"isRecording"\s*:\s*true', r.stdout))
        except Exception:
            return True  # nao sabemos: assume que segue gravando

    def to_wav(self, src, dst):
        """-> (ok, max_volume_dB). Normaliza volume e acrescenta silencio nas pontas (ajuda audios curtos)."""
        for flt in ("adelay=600:all=1,apad=pad_dur=1,dynaudnorm", "apad=pad_dur=1,dynaudnorm", "anull"):
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ar", "16000", "-ac", "1", "-af", flt, dst],
                               capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.exists(dst):
                break
        else:
            return False, None
        vd = subprocess.run(["ffmpeg", "-i", src, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
        m = re.search(r"max_volume:\s*(-?[\d.]+) dB", vd.stderr)
        return True, float(m.group(1)) if m else None

    def run_whisper(self, wav):
        cmd = [self.whisper, "-m", self.wmodel, "-f", wav, "-nt", "-np", "-l", self.audio_lang,
               "-t", str(min(8, max(2, (os.cpu_count() or 4) // 2)))]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        return clean_asr(r.stdout)

    def capture_audio(self, xy, seconds=None):
        """Wrapper: contabiliza falhas seguidas para nao ficar 'procurando audio' onde nao existe."""
        res = self._capture_raw(xy, seconds)
        if res.startswith("transcricao"):
            self.audio_fails = 0
            self.last_capture_step = self.cur_step
        else:
            self.audio_fails += 1
            if self.audio_fails >= 3:
                self.audio_block_until = self.cur_step + 6
                self.audio_fails = 0
                res += "\nSTOP: 3 failed audio captures in a row. Do not try audio again for a while; answer from images/text/memory."
        return res

    def _capture_raw(self, xy, seconds=None):
        """Grava ANTES do play e ate o audio ACABAR (ate audio_max s). Reinicia a gravacao se o Android a derrubar.
        seconds=None -> automatico (ideal para audios de 1-2+ minutos)."""
        auto = not seconds
        maxs = self.audio_max if auto else max(5, min(int(seconds), 900))
        if not self.asr_ok:
            return self.captions_flow(xy, min(maxs, 30))
        self.set_volume()
        if xy is not None and self.audio_playing():  # autoplay em andamento: espera acabar e repete do inicio
            log("    audio ja esta tocando; esperando terminar para repetir do inicio...")
            t = time.time()
            while time.time() - t < maxs and self.audio_playing():
                time.sleep(0.5)
            time.sleep(0.8)
        self.rec_stop()
        segs = []

        def new_seg():
            p = os.path.join(WORK, f"rec_{int(time.time() * 1000)}.m4a")
            if self.rec_start(p):
                segs.append(p)
                return True
            return False

        if not new_seg():
            return self.captions_flow(xy, min(maxs, 30))
        time.sleep(0.9)  # o servico de gravacao demora um pouco para abrir o microfone
        self.player_opened, visual_play = False, False
        if xy is not None:
            self.tap(xy)
            time.sleep(1.8)
            if not self.audio_playing():  # o toque abriu um player (ex.: "Show video") ou nao tocou: acha e aperta o play de verdade
                if not self.ensure_playing():
                    self.rec_stop()
                    self.cleanup(segs)
                    return ("NO audio/video started after the tap and no play button was found. There is probably NO media here: "
                            "do not try audio again on this screen; answer from the image/text/memory.")
                visual_play = self.audio_playing() is not True
        t0, started, stop_since, detect, last_chk = time.time(), False, None, not visual_play, time.time()
        log(f"    gravando o microfone (ate o audio acabar; maximo {maxs}s)...")
        try:
            while True:
                now = time.time()
                el = now - t0
                cap = maxs if (detect or not auto) else min(maxs, 90)
                if el >= cap:
                    break
                p = self.audio_playing()
                if p is None:
                    detect = False
                elif p:
                    started, stop_since = True, None
                elif started:  # parou de tocar: so encerra se ficar parado >=4s (pausas entre falas nao contam)
                    stop_since = stop_since or now
                    if now - stop_since >= 4:
                        break
                if detect and not started and el > 10:
                    break  # nada tocou em 10s
                if now - last_chk >= 6:  # o Android pode derrubar o microfone em segundo plano
                    last_chk = now
                    if not self.rec_active():
                        log("    (microfone parou sozinho; reiniciando gravacao em novo trecho)")
                        if not new_seg():
                            break
                        time.sleep(0.5)
                if int(el) % 20 == 0 and int(el) > 0 and abs(el - int(el)) < 0.35:
                    log(f"    ... {int(el)}s gravados")
                time.sleep(0.3)
            time.sleep(2.0)  # cauda: a fala final nao pode ser cortada
        finally:
            self.rec_stop()
        time.sleep(0.8)
        dur = time.time() - t0
        texts, maxv = [], None
        log(f"    {dur:.0f}s gravados em {len(segs)} trecho(s); transcrevendo (audios longos levam um tempo)...")
        for sp in segs:
            if not os.path.exists(sp) or os.path.getsize(sp) < 800:
                continue
            wav = sp.rsplit(".", 1)[0] + ".wav"
            ok, mv = self.to_wav(sp, wav)
            if not ok:
                continue
            if mv is not None:
                maxv = mv if maxv is None else max(maxv, mv)
            try:
                t = self.run_whisper(wav)
            except Exception as e:
                log(f"    (whisper falhou num trecho: {e})")
                t = ""
            if t:
                texts.append(t)
            if self.debug:
                os.makedirs(SHOTS, exist_ok=True)
                shutil.copy(wav, os.path.join(SHOTS, os.path.basename(wav)))
            else:
                for f in (sp, wav):
                    if os.path.exists(f):
                        os.remove(f)
        if not segs or (not texts and maxv is None):
            return "error: gravacao vazia (de permissao de microfone ao Termux:API e rode setup.sh)."
        text = " ".join(texts).strip()
        silent = maxv is not None and maxv < -38
        if silent and (not text or re.sub(r"[^a-z ]", "", text.lower()).strip() in HALLUCINATIONS):
            return (f"audio gravado SILENCIOSO (pico {maxv:.0f} dB): o microfone nao captou o som. Peca ao usuario para tirar fones/aumentar "
                    "o volume ou tente play_and_read de novo (max 3 vezes).")
        if not text:
            return f"gravei {dur:.0f}s mas nao ha fala reconhecivel (pico {maxv} dB). Tente de novo ou use a transcricao do app."
        tid, dup = self.store_transcript(text, dur)
        msg = (f"transcricao COMPLETA do audio T{tid} ({dur:.0f}s)" + (" [SAME audio as an earlier capture: nothing new]" if dup else "")
               + f": {text[:8000]}")
        if self.player_opened:
            msg += "\nNOTE: a player screen was opened to play this. Close it (back / collapse icon) before answering the question."
        return msg

    # ---- memoria temporaria da sessao
    def store_transcript(self, text, dur, src=None):
        norm = lambda x: set(re.findall(r"[a-z0-9']+", x.lower()))
        nt = norm(text)
        for t in self.tr:
            if jaccard(nt, norm(t["text"])) >= 0.7:
                t["step"], self.last_tid = self.cur_step, t["id"]
                return t["id"], True
        self.tid_n += 1
        ctx = max(self.cur_texts, key=len)[:100] if self.cur_texts else ""
        self.tr.append({"id": self.tid_n, "step": self.cur_step, "dur": dur, "text": text, "ctx": ctx,
                        "src": src or ("video player screen" if self.player_opened else "inline audio/video")})
        self.last_tid = self.tid_n
        return self.tid_n, False

    def memory_block(self):
        out = []
        if self.tr:
            budget, lines = 9000, []
            for t in reversed(self.tr):
                txt = t["text"][:min(3000, budget)]
                if not txt:
                    break
                budget -= len(txt)
                lines.append(f'T{t["id"]} (step {t["step"]}, {t["dur"]:.0f}s, {t["src"]}; screen then: "{t["ctx"]}"): {txt}')
            out.append("CAPTURED AUDIO/VIDEO TRANSCRIPTS (newest first). Reuse them; do NOT re-open/replay the same video:\n" + "\n".join(lines))
        if self.reads:
            out.append("TEXTS ALREADY READ WITH read_all:\n" + "\n".join(
                f'R{r["id"]} (step {r["step"]}): {r["text"][:4500]}' for r in self.reads[-2:]))
        if self.prepared:
            out.append("FILES YOU PREPARED IN THIS TASK (exact names; in file pickers/share sheets select ONLY these, check the name before confirming):\n"
                       + "\n".join(f"- {k}: {v}" for k, v in self.prepared.items()))
        if self.events:
            out.append("WHAT YOU ALREADY DID IN THIS TASK (oldest first):\n" + "\n".join(self.events[-16:]))
        return "\n\n".join(out) if out else "(nothing yet)"

    def label_for(self, a):
        if a.get("action") == "tap_text":
            return str(a.get("text", ""))[:60]
        e = self.element(a) if a.get("index") is not None else None
        if e:
            return (e["text"] or e["desc"] or "")[:60]
        if a.get("app"):
            return str(a["app"])[:50]
        if a.get("url"):
            return str(a["url"])[:50]
        return f"cell {a['cell']}" if a.get("cell") else ""

    def log_event(self, n, a, label, res):
        kind = str(a.get("action"))
        ev = f"step {n}: {kind}" + (f' "{label}"' if label and kind != "type" else "")
        if self.cur_pkg:
            ev += f" [on {self.cur_pkg.split('.')[-1]}]"
        if kind == "type":
            ev += f" (typed {len(str(a.get('text', '')))} chars)"
        elif kind in ("play_and_read", "listen") or (kind == "tap" and res.startswith("transcricao")):
            ev += f" -> captured T{self.last_tid}" if res.startswith("transcricao") else " -> NO audio captured: " + res[:70].replace("\n", " ")
        elif kind == "read_all":
            ev += f" -> read {len(self.reads[-1]['text']) if self.reads else 0} chars (R{len(self.reads)})"
        elif TERM_ALIAS.get(kind, kind) in TERM_KINDS:
            ev += " " + str(a.get("cmd") or a.get("command") or a.get("path") or "")[:60] + " -> " + res[:70].replace("\n", " ")
        elif res.startswith(("BLOCKED", "error")):
            ev += " -> " + res[:80].replace("\n", " ")
        if kind not in ("wait",):
            self.events.append(ev[:220])
            self.log_all.append(ev[:200])
            del self.log_all[:-300]
        del self.events[:-40]

    @staticmethod
    def act_key(a):
        return json.dumps({k: v for k, v in a.items() if k not in ("thought", "notes", "done_goals", "fact", "plan")}, ensure_ascii=False)

    def guard(self, a, n):
        """Bloqueios por codigo (nao dependem do modelo obedecer): loops, video repetido, audio onde nao existe, recaptura inutil."""
        kind = str(a.get("action", "")).lower()
        bg = self.brain_guard(TERM_ALIAS.get(kind, kind), a)
        if bg:
            return bg
        if self.loop_ban and n <= self.loop_ban_until and not a.get("force") and self.act_key(a) in self.loop_ban:
            self.ban_blocks += 1
            return ("BLOCKED (not executed): this action is part of a LOOP you were caught in. Look at PLAN and FACTS: the goal behind it "
                    "is probably already achieved (mark it in done_goals) - go to the NEXT PENDING GOAL, or try a clearly different approach.")
        if kind == "tap" and not a.get("force") and getattr(self, "sel_n", None) and a.get("index") is not None:
            e = self.element(a)
            if e and "[SELECTED]" in e["line"]:
                return ("BLOCKED (not executed): this chip is already SELECTED and tapping it again would DESELECT it. Use select_words with "
                        "the full list of words you want (it fixes the selection for you), or \"force\":true to really deselect it.")
        tk = TERM_ALIAS.get(kind, kind)
        if tk in TERM_KINDS:
            return self.term_guard(tk, a)
        if kind in ("tap", "long_press", "tap_text") and not a.get("force") and self.prepared \
                and re.search(r"documentsui|apps\.nbu\.files|filemanager|filepicker", (self.cur_pkg or "").lower()):
            pe = self.element(a) if kind != "tap_text" else {"text": str(a.get("text", ""))}
            t = (pe["text"] if pe else "").strip()
            if pe and re.search(r"\.(zip|apk|xapk|apks|7z|rar|tar|gz|tgz)$", t, re.I) and t.lower() not in {k.lower() for k in self.prepared}:
                return (f'BLOCKED (not executed): "{t}" is NOT one of the files you prepared. Prepared: ' + ", ".join(self.prepared)
                        + ". Pick exactly one of those (use the picker search box with the exact name if the list is long). "
                        "\"force\":true only if the TASK really asks for that other file.")
        g2 = self.need_listen(a, n, kind)
        if g2:
            return g2
        if a.get("force") or not self.audio:
            return None
        e = self.element(a) if a.get("index") is not None and kind in ("tap", "play_and_read", "long_press") else None
        recent = [t for t in self.tr if n - t["step"] <= 15]
        if e and OPEN_MEDIA_RE.search(e["line"].lower()) and recent:
            t = recent[-1]
            return (f"BLOCKED (not executed): T{t['id']} (step {t['step']}) already holds a captured video/audio of this lesson. Use CAPTURED "
                    "TRANSCRIPTS ONLY if one states the exact fact this question asks. If not, or this screen has its own new clip, repeat with \"force\":true and listen again.")
        if kind in ("play_and_read", "listen"):
            if n < self.audio_block_until:
                return "BLOCKED: audio capture failed repeatedly. Stop looking for audio; answer from image/text/memory, or ask_user."
            if self.last_capture_step >= n - 2 and self.tr:
                return f"BLOCKED: you just captured T{self.tr[-1]['id']}; use it. (\"force\":true only if it was cut or wrong)"
        return None

    def need_listen(self, a, n, kind):
        """Tela com player/'Mostrar video' e nenhuma captura desde o inicio DESTA pergunta: bloqueia (ate 2x) responder sem ouvir."""
        if a.get("force"):  # force = o modelo declara que ja tem a evidencia: nao bloqueia de novo nesta pergunta
            self.q_blocks = 9
            return None
        if not self.audio or getattr(self, "fb_now", False) or not has_media(self.els):
            return None
        if kind not in ("tap", "tap_text", "type", "enter", "order_words") or n < self.audio_block_until:
            return None
        if re.search(r"\b[RT]\d+\b", str(a.get("thought", ""))):  # citou texto lido (Rn) ou transcricao (Tn) como evidencia
            return None
        if kind in ("tap", "tap_text"):
            if kind == "tap":
                e = self.element(a)
                line = (e["line"] if e else "").lower()
            else:
                line = str(a.get("text", "")).lower()
            if AUDIO_RE.search(line) or OPEN_MEDIA_RE.search(line) or SKIP_GATE_RE.search(line):
                return None
        if self.last_capture_step >= getattr(self, "q_start", 0) or getattr(self, "q_blocks", 0) >= 1:
            return None
        self.q_blocks = getattr(self, "q_blocks", 0) + 1
        return ("BLOCKED (not executed): this question has its own audio/video control and you have NOT listened to it for THIS question. "
                "Do play_and_read on the player / 'Show video' first and answer from what you heard. Skip it ONLY if you are CERTAIN: "
                'then repeat the same action with "force":true and quote the evidence (captured transcript Tn or visible text) in thought.')

    def cleanup(self, paths):
        for p in paths:
            for f in (p, p.rsplit(".", 1)[0] + ".wav"):
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

    # ---- achar e apertar o PLAY de verdade (player aberto por "Show video", etc.)
    def locate_play(self, png):
        """-> (estado, (x,y)|None). estado: play_button | already_playing | none. Duas etapas: celula grossa + recorte refinado."""
        if Image is None or not self.vision:
            return "none", None
        try:
            img = base64.b64encode(pack(png, self.imgmax, True)).decode()
            d = parse_json(self.post_chat([{"role": "user", "content": LOCATE_PROMPT, "images": [img]}], True, timeout=120, predict=120))
            if not isinstance(d, dict):
                return "none", None
            st = str(d.get("state", "none")).lower()
            if st == "already_playing":
                return st, None
            xy0 = self.cell_xy(d.get("cell")) if st == "play_button" else None
            if not xy0:
                return "none", None
            W, H = self.W, self.H
            cw, ch = W / GRID_COLS, H / GRID_ROWS
            box = (max(0, int(xy0[0] - 1.5 * cw)), max(0, int(xy0[1] - 1.5 * ch)), min(W, int(xy0[0] + 1.5 * cw)), min(H, int(xy0[1] + 1.5 * ch)))
            crop = Image.open(io.BytesIO(png)).convert("RGB").crop(box)
            sc = max(1.0, 700 / max(crop.width, 1))
            crop = crop.resize((int(crop.width * sc), int(crop.height * sc)))
            overlay_grid(crop, 6, 6)
            buf = io.BytesIO()
            crop.save(buf, "JPEG", quality=88)
            d2 = parse_json(self.post_chat([{"role": "user", "content": REFINE_PROMPT,
                                             "images": [base64.b64encode(buf.getvalue()).decode()]}], True, timeout=120, predict=60))
            m = re.match(r"^\s*([A-Fa-f])\s*([1-6])\s*$", str((d2 or {}).get("cell", "")))
            if not m:
                return st, xy0
            c, r = COLS.index(m.group(1).upper()), int(m.group(2)) - 1
            x = box[0] + int((c + .5) * (box[2] - box[0]) / 6)
            y = box[1] + int((r + .5) * (box[3] - box[1]) / 6)
            return st, (min(x, W - 1), min(y, H - 1))
        except Exception as e:
            log(f"    (localizar play falhou: {e})")
            return "none", None

    def ensure_playing(self):
        """Depois do toque o audio nao comecou: olha a tela, acha o botao play (arvore de UI ou visao) e aperta. True se tocando."""
        for attempt in range(2):
            try:
                self.observe()
            except Exception as e:
                log(f"    (observe falhou: {e})")
                return False
            cand = None
            for e in self.els:
                l = e["line"].lower()
                if PLAY_RE.search(l) and not OPEN_MEDIA_RE.search(l) and "clickable" in l and "pause" not in l:
                    cand = (e["cx"], e["cy"])
                    break
            st = "play_button" if cand else None
            if not cand and self.last_png:
                log("    (procurando o botao de play na tela...)")
                st, cand = self.locate_play(self.last_png)
            if st == "already_playing":
                self.player_opened = True
                return True
            if not cand:
                return False
            log(f"    apertando play em {cand[0]},{cand[1]}")
            self.tap(cand)
            self.player_opened = True
            time.sleep(2.0)
            p = self.audio_playing()
            if p or p is None:
                return True
        return False

    # plano B sem whisper: legenda ao vivo / legendas do video via screenshots
    def burst(self, seconds):
        frames, seen = [], set()
        t0 = time.time()
        last_playing, saw_audio = t0, False
        while time.time() - t0 < seconds and len(frames) < 14:
            png = self.shoot()
            if png:
                h = hashlib.md5(png).hexdigest()
                if h not in seen:
                    seen.add(h)
                    frames.append(png)
            playing = self.audio_playing()
            if playing:
                saw_audio, last_playing = True, time.time()
            if saw_audio and playing is False and time.time() - last_playing >= 5 and time.time() - t0 >= 6:
                break
            time.sleep(0.2)
        return frames

    def transcribe_frames(self, frames):
        out, step = [], (4 if Image else 2)
        for i in range(0, len(frames), step):
            msg = {"role": "user", "content": TRANSCRIBE, "images": frames[i:i + step]}
            try:
                d = parse_json(self.post_chat([msg], True, timeout=120, predict=400))
            except Exception as e:
                log(f"    (transcricao falhou: {e})")
                continue
            caps = d.get("captions", []) if isinstance(d, dict) else []
            for c in caps if isinstance(caps, list) else []:
                c = str(c).strip()
                if c and c not in out:
                    out.append(c)
        return [c for c in out if not any(c != o and c in o for o in out)]

    def captions_flow(self, xy, seconds):
        log("    (whisper/ffmpeg/termux-api indisponiveis: usando legendas na tela; rode setup.sh para audio real)")
        if xy is not None:
            self.tap(xy)
        frames = self.burst(seconds)
        text = " | ".join(self.transcribe_frames([base64.b64encode(pack(f, 1280, False)).decode() for f in frames]))
        if not text:
            return "audio tocado, mas NENHUMA legenda detectada. Instale whisper (setup.sh) ou use a transcricao do app."
        tid, dup = self.store_transcript(text, 0, "captions")
        return f"transcricao do audio T{tid} (legendas): " + text[:3000]

    # ---- rolagem e leitura de textos longos
    def do_swipe(self, direction, times=1, el=None):
        W, H = self.W, self.H
        x1, y1, x2, y2 = el["box"] if el and el.get("box") else (0, 0, W, H)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        h = y2 - y1
        if el:
            top, bot = y1 + int(h * .22), y1 + int(h * .78)
        else:
            top, bot = int(H * .28), int(H * .74)
        s = {"up": (cx, bot, cx, top), "down": (cx, top, cx, bot),
             "left": (x1 + int((x2 - x1) * .85), cy, x1 + int((x2 - x1) * .15), cy),
             "right": (x1 + int((x2 - x1) * .15), cy, x1 + int((x2 - x1) * .85), cy)}.get(direction)
        if not s:
            return False
        for _ in range(max(1, min(int(times), 10))):
            self.dev.sh("input swipe %d %d %d %d 550" % s)
            time.sleep(0.5)
        return True

    def read_all(self, max_pages=14):
        lines, seen, prev_sig, pages = [], set(), None, 0
        for pages in range(1, max_pages + 1):
            _, _, _, els = parse_ui(self.dev.dump(), maxtext=3000, maxels=400)
            page = [s for e in els for s in (e["text"], e["desc"]) if s]
            use_ocr = len(page) < 3 and self.vision
            if use_ocr:
                png = self.shoot()
                page = [l.strip() for l in self.ocr(png).splitlines() if l.strip()] if png else []
            new = [s for s in page if s not in seen]
            for s in new:
                seen.add(s)
                lines.append(s)
            sig = hashlib.md5("|".join(page).encode()).hexdigest()
            if sig == prev_sig or (not new and pages > 1):
                break
            prev_sig = sig
            self.do_swipe("up", 1)
            time.sleep(0.4)
        self.read_step = self.cur_step
        text = "\n".join(lines)
        self.reads.append({"id": len(self.reads) + 1, "step": self.cur_step, "text": text})
        return f"texto completo ({pages} telas, parou no fim do conteudo):\n{text[:6000]}" + ("\n[...cortado]" if len(text) > 6000 else "")

    def zoom(self, a):
        if Image is None or not self.last_png:
            return "error: zoom precisa do Pillow e de um screenshot (use --vision)"
        try:
            x1, y1, x2, y2 = (min(max(float(a[k]), 0), 1000) / 1000 for k in ("x1", "y1", "x2", "y2"))
            im = Image.open(io.BytesIO(self.last_png)).convert("RGB")
            W, H = im.size
            box = (int(min(x1, x2) * W), int(min(y1, y2) * H), int(max(x1, x2) * W), int(max(y1, y2) * H))
            if box[2] - box[0] < 20 or box[3] - box[1] < 20:
                return "error: area muito pequena"
            crop = im.crop(box)
            scale = max(1.0, min(1000 / crop.width, 1000 / crop.height, 4.0))
            crop = crop.resize((int(crop.width * scale), int(crop.height * scale)))
            buf = io.BytesIO()
            crop.save(buf, "JPEG", quality=88)
            self.zoom_b64 = base64.b64encode(buf.getvalue()).decode()
            return "ok: recorte ampliado sera enviado junto com a proxima tela (e a ultima imagem enviada)"
        except Exception as e:
            return f"error: zoom falhou ({e})"

    # ---- ferramentas deterministicas (sem depender do modelo acertar caminho/indice)
    def locate(self, name, maxdepth=4, limit=12, budget=10):
        """Procura arquivo/pasta por nome (sem diferenciar maiusculas) no home do Termux e no armazenamento do celular."""
        want = os.path.basename(str(name or "").rstrip("/")).lower()
        if not want:
            return []
        roots = [HOME, os.path.join(HOME, "storage", "shared")]
        exact, part, seen, t0 = [], [], set(), time.time()
        for root in roots:
            if not os.path.isdir(root):
                continue
            base = root.rstrip(os.sep).count(os.sep)
            for dp, dns, fns in os.walk(root):
                dns[:] = [d for d in dns if d not in SKIP_DIRS and not (root == HOME and dp == HOME and d == "storage")]
                if dp.count(os.sep) - base >= maxdepth:
                    dns[:] = []
                for nm in dns + fns:
                    low = nm.lower()
                    full = os.path.realpath(os.path.join(dp, nm))
                    if full in seen or want not in low:
                        continue
                    seen.add(full)
                    (exact if low == want else part).append(full)
                if time.time() - t0 > budget or len(exact) >= limit:
                    break
            if time.time() - t0 > budget:
                break
        return (exact + part)[:limit]

    def find_path(self, a):
        hits = self.locate(a.get("name") or a.get("path"))
        if not hits:
            return "no match (searched Termux home and phone storage up to 4 levels, case-insensitive)"
        out = []
        for h in hits:
            kind = "dir" if os.path.isdir(h) else (f"{os.path.getsize(h) / 1e6:.1f} MB" if os.path.exists(h) else "?")
            out.append(f"{h}  [{kind}]")
        return "found:\n" + "\n".join(out)

    def zip_items(self, a):
        """Um unico zip com nomes RELATIVOS (basename de cada item), nome unico com data/hora, gravado em .part e renomeado no fim."""
        items = a.get("items") or a.get("paths") or a.get("path")
        items = [items] if isinstance(items, str) else [i for i in (items or []) if isinstance(i, str)]
        if not items:
            return 'error: informe "items":["~/pasta1","~/pasta2"]'
        srcs, problems = [], []
        for it in items:
            p = self.resolve_path(it)
            if not os.path.exists(p):
                want = os.path.basename(str(it).rstrip("/")).lower()
                hits = [h for h in self.locate(it) if os.path.basename(h).lower() == want]
                if len(hits) == 1:
                    p = hits[0]
                elif hits:
                    problems.append(f'"{it}" is ambiguous: ' + " | ".join(hits[:4]) + " (pass the full path)")
                    continue
                else:
                    problems.append(f'"{it}" not found (try find_path)')
                    continue
            srcs.append(p)
        tops = [os.path.basename(p.rstrip("/")) for p in srcs]
        dup = {t for t in tops if tops.count(t) > 1}
        if dup:
            problems.append("two items have the same name " + ", ".join(sorted(dup)) + " (they would overwrite each other inside the zip)")
        if problems:
            return "error, nothing was created: " + "; ".join(problems)
        dest = a.get("dest") or (os.path.join(HOME, "storage", "downloads") if os.path.isdir(os.path.join(HOME, "storage", "downloads")) else HOME)
        dest = self.resolve_path(dest)
        os.makedirs(dest, exist_ok=True)
        base = re.sub(r"[^\w.\-]", "_", str(a.get("name") or "backup"))[:40]
        out = os.path.join(dest, f"{base}_{time.strftime('%Y%m%d_%H%M%S')}.zip")
        part, files, skipped, t0 = out + ".part", 0, 0, time.time()
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                def add(path, arc):
                    nonlocal files, skipped
                    if os.path.realpath(path) in (os.path.realpath(part), os.path.realpath(out)):
                        return
                    try:
                        comp = zipfile.ZIP_STORED if path.lower().endswith(NOCOMPRESS) else zipfile.ZIP_DEFLATED
                        zf.write(path, arc, compress_type=comp)
                        files += 1
                        if files % 500 == 0:
                            log(f"    ... {files} arquivos ({time.time() - t0:.0f}s)")
                    except (OSError, ValueError):
                        skipped += 1
                for src, top in zip(srcs, tops):
                    if os.path.isdir(src):
                        zf.write(src, top)
                        for dp, dns, fns in os.walk(src):
                            rel = os.path.relpath(dp, src)
                            for nm in dns + fns:
                                path = os.path.join(dp, nm)
                                arc = os.path.normpath(os.path.join(top, "" if rel == "." else rel, nm))
                                if os.path.isdir(path):
                                    try:
                                        zf.write(path, arc)
                                    except OSError:
                                        skipped += 1
                                else:
                                    add(path, arc)
                    else:
                        add(src, top)
            os.replace(part, out)
        except Exception as e:
            try:
                os.remove(part)
            except OSError:
                pass
            return f"error: zip falhou ({e})"
        chk = self.check_file(out, "")
        self.own(out)
        self.led.append(f"created {out}")
        self.facts.append(f"zip READY: {out} contains {', '.join(tops)} (step {self.cur_step})")
        del self.facts[:-30]
        return (f"ok: created {out} in {time.time() - t0:.0f}s ({files} files, {skipped} skipped/unreadable). Items: "
                + "; ".join(f"{t} <- {p}" for t, p in zip(tops, srcs)) + "\n" + chk)

    # ---- exercicios "Select N words": chips parados, selecao = borda azul
    def chip_candidates(self, els, H):
        return [e for e in els if e["text"] and len(e["text"]) <= 40 and 0.15 * H < e["cy"] < 0.95 * H
                and 0.025 * H <= (e["box"][3] - e["box"][1]) <= 0.07 * H and not CHIP_SKIP_RE.search(e["text"].lower())]

    def mark_selection(self, png, els, W, H):
        """Marca em cada chip e['sel'] (arvore OU borda azul no screenshot) e acrescenta [SELECTED] na linha. Devolve os chips em
        ordem de leitura (lista vazia se a tela nao parece ter chips)."""
        chips = self.chip_candidates(els, H)
        if len(chips) < 3:
            return []
        pix = None
        if png and Image is not None:
            try:
                im = Image.open(io.BytesIO(png)).convert("RGB")
                if im.size != (W, H):
                    W, H = im.size
                pix = im.load()
            except Exception:
                pix = None
        self.sel_detect = pix is not None
        for e in chips:
            if pix is not None and not e["sel"]:
                e["sel"] = border_ratio(pix, W, H, e["box"]) >= SEL_RATIO
            if e["sel"] and "[SELECTED]" not in e["line"]:
                e["line"] += " [SELECTED]"
        return reading_order(chips)

    def sel_state(self, png, els, W, H):
        chips = self.mark_selection(png, els, W, H)
        if not chips:
            return
        instr = next((e["text"] for e in els if len(e["text"]) > 12 and SELECT_VERB_RE.search(e["text"].lower())
                      and SELECT_N_RE.search(e["text"].lower())), "")
        m = SELECT_N_RE.search(instr.lower()) if instr else None
        if m:
            tok = m.group(1)
            self.sel_n = int(tok) if tok.isdigit() else NUM_WORDS.get(tok)
        picked = [e for e in chips if e["sel"]]
        if not (self.sel_n or picked):
            return
        idx = lambda e: (re.match(r"\[(\d+)\]", e["line"]) or [None, "?"])[1]
        sel_txt = ", ".join(f'[{idx(e)}] "{e["text"]}"' for e in picked) or "none"
        self.sel_info = ((f"SELECT-WORDS EXERCISE: the instruction asks for EXACTLY {self.sel_n} words. " if self.sel_n else "")
                         + f"Chips selected now ({len(picked)}): {sel_txt}. The chips stay in place; a selected chip has a blue border and "
                         "[SELECTED] in the list. Tapping a selected chip DESELECTS it. Use select_words (chip texts in reading order, "
                         "repeated words allowed) instead of tapping one by one, then press Continue/Check yourself.")

    def read_chips(self):
        """Dump e screenshot novos -> (chips em ordem de leitura com 'sel', detecta_pixels)."""
        xml = self.dev.dump()
        _, W, H, els = parse_ui(xml, maxels=400)
        png = self.shoot()
        if png:
            W, H = png_size(png)
        chips = self.mark_selection(png, els, W, H)
        return chips, bool(png and Image is not None)

    def select_words(self, a):
        """Marca/desmarca chips ate a selecao ser EXATAMENTE a pedida, relendo a tela (dump + pixels) depois de cada toque."""
        words = a.get("words")
        if isinstance(words, str):
            words = words.split()
        idxs = a.get("indexes")
        if not words and not idxs:
            return 'error: informe "words" (textos dos chips na ordem de leitura, repetidos incluidos) ou "indexes"'
        chips, detect = self.read_chips()
        if len(chips) < 2:
            return "error: no word chips found in the UI tree; use tap_cell/tap_xy one word at a time"
        pos = []
        if idxs:
            for i in idxs:
                e = self.element({"index": i})
                if not e:
                    return f"error: invalid index {i}"
                pos.append((e["cx"], e["cy"]))
        else:
            sel = pick_span(chips, words)
            if sel is None:
                return ("error: could not find these words in order on the screen: " + " | ".join(map(str, words))
                        + ". Chips in reading order: " + " | ".join(c["text"] for c in chips))
            pos = [(chips[i]["cx"], chips[i]["cy"]) for i in sel]
        if self.sel_n and len(pos) != self.sel_n and not a.get("force"):
            return (f"error: the instruction asks for EXACTLY {self.sel_n} words but you listed {len(pos)}. Recount (skip connectors such as "
                    "'and' or punctuation chips if the count requires it) and call select_words again. \"force\":true only if the count is not "
                    "about the number of chips.")

        def resolve(cur):
            if words and not idxs:
                r = pick_span(cur, words)
                return set(r) if r is not None else None
            return {k for k, c in enumerate(cur) if any(abs(c["cx"] - x) <= 12 and abs(c["cy"] - y) <= 12 for x, y in pos)}

        if not detect:  # sem como ver a selecao: toca cada alvo uma vez (sem verificar)
            for x, y in pos:
                self.tap((x, y))
                time.sleep(0.5)
            return "ok (UNVERIFIED: no screenshot/Pillow to see the selection): tapped " + str(len(pos)) + " chips once each. Read the screen."
        taps = {}
        for _ in range(2 * len(pos) + 8):
            goal = resolve(chips)
            if goal is None:
                return "error: the chips changed and the words are no longer on screen. Read the screen again."
            wrong = [k for k, c in enumerate(chips) if c["sel"] and k not in goal]
            miss = [k for k, c in enumerate(chips) if not c["sel"] and k in goal]
            if not wrong and not miss:
                break
            k = (wrong or miss)[0]
            c = chips[k]
            key = (c["cx"] // 10, c["cy"] // 10)
            taps[key] = taps.get(key, 0) + 1
            if taps[key] > 1:
                return (f'error: tapped "{c["text"]}" twice and its state did not change as expected; I cannot verify the selection. '
                        "Look at the screenshot and use tap_cell for that chip.")
            self.tap((c["cx"], c["cy"]))
            time.sleep(0.6)
            chips, _ = self.read_chips()
            if len(chips) < 2:
                return "error: the screen changed while selecting (chips gone). Read the screen."
        chosen = [c["text"] for c in chips if c["sel"]]
        goal = resolve(chips) or set()
        ok = bool(goal) and {k for k, c in enumerate(chips) if c["sel"]} == goal
        need = f" (instruction asks {self.sel_n})" if self.sel_n else ""
        return (("ok" if ok else "MISMATCH") + f": selected {len(chosen)} = " + " | ".join(chosen) + need
                + (". Now press Continue/Check yourself." if ok else ". Fix it: call select_words again."))

    def split_chips(self, els):
        """Chips de palavras na tela -> (caixa_da_resposta, bandeja), cada um em ordem de leitura.
        Os dois grupos sao separados por um vao vertical grande (a caixa fica em cima, a bandeja embaixo)."""
        chips = [e for e in els if e["text"] and len(e["text"]) <= 70 and 0.18 * self.H < e["cy"] < 0.95 * self.H
                 and (e["box"][3] - e["box"][1]) <= 0.07 * self.H and not CHIP_SKIP_RE.search(e["text"].lower())]
        if not chips:
            return [], []
        chips.sort(key=lambda e: (e["cy"], e["cx"]))
        rows = []
        for e in chips:
            if rows and abs(e["cy"] - rows[-1][0]["cy"]) < 30:
                rows[-1].append(e)
            else:
                rows.append([e])
        cut = next((i for i in range(1, len(rows)) if rows[i][0]["cy"] - rows[i - 1][0]["cy"] > 0.11 * self.H), None)
        flat = lambda rs: [e for r in rs for e in sorted(r, key=lambda x: x["cx"])]
        if cut is None:  # um grupo so: bandeja se estiver na metade de baixo
            mean = sum(e["cy"] for e in chips) / len(chips)
            return ([], flat(rows)) if mean > 0.5 * self.H else (flat(rows), [])
        return flat(rows[:cut]), flat(rows[cut:])

    def order_words(self, a):
        """Exercicio de montar frase com chips: toca na ordem certa, relendo a tela a cada toque (os chips mudam de lugar) e confere a caixa."""
        words = [str(w).strip() for w in (a.get("words") or []) if str(w).strip()]
        if not words:
            return 'error: informe "words": os textos dos chips na ordem certa, EXATAMENTE como aparecem na tela'
        if getattr(self, "sel_n", None):
            return ("error: this is a SELECT-words exercise (the chips stay in place, the selection is a blue border), not a word-order one. "
                    "Use select_words with the chip texts in reading order.")
        low = [w.lower() for w in words]
        txt = lambda es: [e["text"].strip() for e in es]

        def fresh():
            _, _, _, els = parse_ui(self.dev.dump(), maxels=400)
            return self.split_chips(els)

        box, tray = fresh()
        if not box and not tray:
            return "error: no word chips found in the UI tree; use tap_text/tap_cell one word at a time"
        k = 0
        while box and [t.lower() for t in txt(box)] != low[:len(box)] and k < 15:  # caixa com palavras erradas: devolve a ultima
            before = txt(box)
            self.tap((box[-1]["cx"], box[-1]["cy"]))
            time.sleep(0.7)
            k += 1
            box, tray = fresh()
            if txt(box) == before:
                return ("error: tapping the chips does not move them, so this is not a word-order exercise (maybe a SELECT-words one: "
                        "use select_words, or tap_cell). Box: " + " | ".join(before))
        if box and [t.lower() for t in txt(box)] != low[:len(box)]:
            return "error: could not empty the answer box. Box: " + " | ".join(txt(box))
        for i in range(len(box), len(words)):
            cands = [e for e in tray if e["text"].strip().lower() == low[i]]
            if not cands:
                return (f'error: stopped before word {i + 1} "{words[i]}": no such chip in the tray. Tray: ' + " | ".join(txt(tray))
                        + ". Box: " + " | ".join(txt(box)) + ". Use the chip texts exactly as shown.")
            self.tap((cands[0]["cx"], cands[0]["cy"]))
            time.sleep(0.7)
            box, tray = fresh()
        ok = [t.lower() for t in txt(box)] == low
        return (("ok" if ok else "MISMATCH") + ": box = " + " | ".join(txt(box)) + ("" if ok else "; expected = " + " | ".join(words))
                + ("; tray left = " + " | ".join(txt(tray)) if tray else "")
                + (". Press Check/Continue yourself." if ok else ". Fix it: call order_words again with the right order."))

    def tap_text(self, a):
        """Le a tela de novo e toca no elemento pelo texto (indices de listas que carregam/reordenam enganam o modelo)."""
        want = str(a.get("text", "")).strip().lower()
        if not want:
            return 'error: informe "text"'
        for attempt in range(3):
            _, _, _, els = parse_ui(self.dev.dump(), maxels=400)
            exact = [e for e in els if want in (e["text"].lower(), e["desc"].lower())]
            part = [e for e in els if want in e["text"].lower() or want in e["desc"].lower()] if not exact else []
            cand = exact or sorted(part, key=lambda e: len(e["text"] or e["desc"]))
            if len(exact) > 1 and a.get("nth") is None:
                choices = " | ".join((e["text"] or e["desc"])[:60] for e in exact[:6])
                return (f'error: "{a.get("text")}" matches {len(exact)} exact elements: {choices}. '
                        'Do not choose by position without checking artist/details; use a more specific label or set "nth" only when the order is verified.')
            if len(exact) == 1 or (cand and not exact and len(part) == 1):
                e = cand[0]
                e, err = self.uncover(e)
                if err:
                    return err
                self.tap((e["cx"], e["cy"]))
                extra = f" (WARNING: {len(exact)} elements matched exactly; tapped the first)" if len(exact) > 1 else ""
                return f'ok: tapped "{(e["text"] or e["desc"])[:60]}" at {e["cx"]},{e["cy"]}{extra}'
            if cand and a.get("nth") is not None:
                try:
                    e = cand[int(a["nth"])]
                    self.tap((e["cx"], e["cy"]))
                    return f'ok: tapped #{a["nth"]} "{(e["text"] or e["desc"])[:60]}"'
                except (IndexError, ValueError):
                    pass
            if attempt < 2:
                time.sleep(1.2)  # a lista pode ainda estar filtrando/carregando
        if len(part) > 1:
            return (f'error: "{a.get("text")}" matches {len(part)} elements (partial): ' + " | ".join((e["text"] or e["desc"])[:40] for e in part[:6])
                    + '. Use the exact text, or add "nth":0.')
        near = [e["text"] or e["desc"] for e in els if (e["text"] or e["desc"])][:8]
        return f'error: no element with text "{a.get("text")}" on screen now. Visible: ' + " | ".join(x[:40] for x in near)

    def situation(self, pkg):
        """Dica calculada pelo CODIGO sobre onde o agente esta (o modelo esquece que o seletor de arquivos pertence ao Drive)."""
        pk = (pkg or "").lower()
        if getattr(self, "sel_info", ""):
            return "SITUATION: " + self.sel_info
        if re.search(r"documentsui|apps\.nbu\.files|filepicker", pk):
            return ("SITUATION: you are INSIDE the system FILE PICKER opened by another app (Drive > Upload / share / attach). That app is still "
                    "running underneath: do NOT use open_app/home/back to 'go back' to it. Pick the file with tap_text and its EXACT name"
                    + (" (prepared: " + ", ".join(self.prepared) + ")" if self.prepared else "")
                    + ". Long list: tap the search icon, type the exact name, then tap_text.")
        if pk == "com.google.android.apps.docs":
            return ("SITUATION: Google Drive is open. To upload: tap the + (New) button, then Upload, then pick the file in the picker. "
                    "Verify delivery by seeing the EXACT file name in the Drive list.")
        return ""

    # ---- acoes
    def resolve_app(self, name):
        n = name.strip().lower()
        if "." in n:
            return n
        if n in APPS:
            return APPS[n]
        key = re.sub(r"[^a-z0-9]", "", n)
        pk = [l.split(":", 1)[1].strip() for l in self.dev.sh("pm list packages").splitlines() if ":" in l]
        hit = sorted((p for p in pk if key and key in p.replace(".", "")), key=len)
        return hit[0] if hit else None

    def type_text(self, text, clear):
        if clear:
            self.dev.sh("input keyevent 123 " + "67 " * 40)
        if not text:
            return "ok"
        if SAFE_TEXT.match(text):
            self.dev.sh("input text " + shlex.quote(text.replace(" ", "%s")))
            return "ok"
        if shutil.which("termux-clipboard-set"):
            subprocess.run(["termux-clipboard-set"], input=text.encode(), timeout=10)
            time.sleep(0.3)
            self.dev.sh("input keyevent 279")  # PASTE
            return "ok (colado via clipboard)"
        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
        plain = re.sub(r"[^A-Za-z0-9 .,@_\-+=:/?!#]", "", plain)
        self.dev.sh("input text " + shlex.quote(plain.replace(" ", "%s")))
        return "ok (sem acentos: instale termux-api para texto completo)"

    # ---- plano, fatos, apps instalados, loops, notificacao
    def refresh_pkgs(self, n, pkg):
        if n - self.pkgs_step < (2 if "vending" in (pkg or "") else 7):
            return
        out = self.dev.sh("pm list packages", timeout=15)
        got = {l.split(":", 1)[1].strip() for l in out.splitlines() if ":" in l}
        if got:
            self.pkgs, self.pkgs_step = got, n

    def installed_hint(self):
        m = pkg_matches(self.pkgs, self.task_toks) if self.pkgs else []
        return ("INSTALLED APPS matching the task words (already on the phone: NEVER reinstall them, open them with open_app): "
                + ", ".join(m)) if m else ""

    def make_plan(self, task):
        goals = []
        self.plan_question = ""
        try:
            d = parse_json(self.post_chat([{"role": "user", "content": PLAN_PROMPT.format(
                task=task, inst=", ".join(pkg_matches(self.pkgs, self.task_toks)) or "(none)")}], True, timeout=120, predict=700, model=self.tm()))
            goals = [str(g).strip()[:160] for g in (d or {}).get("goals", []) if str(g).strip()][:10]
            clean = lambda k, n: [str(x).strip()[:200] for x in ((d or {}).get(k) or []) if str(x).strip()][:n] if isinstance((d or {}).get(k), list) else []
            self.constraints, self.task_deliv = clean("constraints", 8), clean("deliverables", 8)
            q = (d or {}).get("question")
            self.plan_question = str(q).strip()[:300] if isinstance(q, str) and q.strip().lower() not in ("", "null", "none") else ""
        except Exception as e:
            log(f"    (plano automatico falhou: {e})")
        self.plan = [{"goal": g, "done": False} for g in (goals or [task[:160]])]
        self.plan.append({"goal": FINAL_GOAL, "done": False, "final": True})
        shown = [g["goal"] for g in self.plan if not g.get("final")]
        if len(shown) > 1:
            log(f"  {C.DIM}plano{C.R}")
            for i, g in enumerate(shown, 1):
                log(f"  {C.DIM}{i}.{C.R} {_trim(g, 96)}")
        flog("plano: " + " | ".join(f"{i}) {g['goal']}" for i, g in enumerate(self.plan, 1)))

    def plan_block(self):
        out = []
        if self.plan:
            out.append("PLAN (you maintain it: put finished goal numbers in \"done_goals\"; send \"plan\":[...] to replace it if it is wrong):")
            out += [f"[{'x' if g['done'] else ' '}] {i}. {g['goal']}" for i, g in enumerate(self.plan, 1)]
            nxt = next((i for i, g in enumerate(self.plan, 1) if not g["done"]), None)
            out.append(f"NEXT PENDING GOAL: {nxt}" if nxt else "ALL GOALS ARE DONE: call done now with a summary.")
        if self.facts:
            out.append("FACTS ALREADY ESTABLISHED (trust them, do not redo):\n" + "\n".join("- " + f for f in self.facts[-15:]))
        inst = self.installed_hint()
        if inst:
            out.append(inst)
        if self.advice:
            out.append("REPLAN ADVICE: " + self.advice)
        return "\n".join(out)

    def absorb_meta(self, a, n):
        """Le done_goals / fact / plan que o modelo envia junto da acao."""
        dg = a.get("done_goals")
        if isinstance(dg, (int, str)):
            dg = [dg]
        for i in dg if isinstance(dg, list) else []:
            try:
                k = int(i) - 1
                if 0 <= k < len(self.plan) and not self.plan[k]["done"]:
                    self.plan[k]["done"] = True
                    self.events.append(f"step {n}: goal {k + 1} marked DONE ({self.plan[k]['goal'][:60]})")
            except (TypeError, ValueError):
                pass
        f = a.get("fact")
        if isinstance(f, str) and f.strip():
            f = f.strip()[:160]
            if f not in self.facts:
                self.facts.append(f"{f} (step {n})")
                del self.facts[:-30]
        pl = a.get("plan")
        if isinstance(pl, list) and pl:
            old = {g["goal"]: g["done"] for g in self.plan}
            self.plan = [{"goal": str(g)[:160], "done": old.get(str(g)[:160], False)} for g in pl[:8] if str(g).strip()]

    def detect_loop(self, hist):
        """Ciclo de periodo 2-4 em (acao, tela) repetido 3 vezes: abrir app -> home -> abrir app -> home..."""
        seq = [(h[0], h[1]) for h in hist if h[3] != "auto"][-12:]
        for p in (2, 3, 4):
            if len(seq) >= 3 * p and all(seq[-k] == seq[-k - p] for k in range(1, 2 * p + 1)):
                return p, [x[0] for x in seq[-p:]]
        return None

    def replan(self, task, loop):
        try:
            d = parse_json(self.post_chat([{"role": "user", "content": REPLAN_PROMPT.format(
                loop=" -> ".join(loop)[:400], task=task,
                plan="\n".join(f"[{'x' if g['done'] else ' '}] {g['goal']}" for g in self.plan) or "(none)",
                facts="\n".join(self.facts[-10:]) or "(none)", events="\n".join(self.events[-10:]))}], True, timeout=120, predict=400, model=self.tm()))
        except Exception as e:
            log(f"    (replanejamento falhou: {e})")
            return
        if not isinstance(d, dict):
            return
        goals = [str(g).strip()[:160] for g in d.get("goals", []) if str(g).strip()][:10]
        if goals:
            self.plan = ([g for g in self.plan if g["done"] and not g.get("final")] + [{"goal": g, "done": False} for g in goals]
                         + [{"goal": FINAL_GOAL, "done": False, "final": True}])
        self.advice = str(d.get("advice", ""))[:300]
        log(f"    replanejado: {self.advice}")

    def notify(self, title, content, ok=True):
        """Notificacao do Android (Termux:API). O Termux:API pode levar 20s+ para responder: nao bloqueia, e o programa
        espera a entrega antes de sair (flush_notify)."""
        if not self.notify_on or not shutil.which("termux-notification"):
            return
        try:
            self._notif.append(subprocess.Popen(
                ["termux-notification", "--id", "phoneagent", "--title", title, "--content", (content or title)[:400],
                 "--priority", "high", "--sound", "--vibrate", "300,150,300" if ok else "600,200,600,200,600"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True))
        except Exception as e:
            log(f"    (notificacao falhou: {e})")

    def flush_notify(self, timeout=4):
        """A notificacao roda destacada (start_new_session) e sobrevive ao programa: so espera um instante, sem travar o terminal."""
        t0 = time.time()
        for p in self._notif:
            left = timeout - (time.time() - t0)
            if p.poll() is None and left > 0:
                try:
                    p.wait(timeout=left)
                except subprocess.TimeoutExpired:
                    pass
        self._notif = []

    def back_to_termux(self):
        """Se o agente saiu do Termux (app/site/share sheet), traz o terminal de volta ao terminar: o usuario ve o resultado onde pediu."""
        if not self.left_term:
            return
        self.left_term = False
        if not getattr(self, "return_term", False):  # tarefa de tela: o usuario pediu para mexer no app, fica onde terminou
            return
        try:
            self.dev.sh("am start -n com.termux/com.termux.app.TermuxActivity >/dev/null 2>&1", timeout=10)
        except Exception:
            pass

    def safe_janitor(self):
        try:
            self.janitor()
        except Exception as e:
            log(f"    (faxina falhou: {e})")

    def run(self, task, max_steps):
        """Wrapper: executa a tarefa, faz a faxina SEMPRE (ok, falha ou Ctrl+C), mostra o relatorio medido e avisa no fim."""
        self.final_msg = ""
        self.left_term = False
        try:
            ok = self._run(task, max_steps)
        except KeyboardInterrupt:
            self.safe_janitor()
            raise
        except Exception as e:
            self.final_msg = f"erro inesperado: {e}"
            self.safe_janitor()
            self.back_to_termux()
            self.notify("⚠️ phoneagent: erro", self.final_msg, False)
            raise
        self.safe_janitor()
        self.back_to_termux()
        try:
            self.learn_from_run(task, ok, list(self.log_all))
        except Exception as e:
            log(f"    (aprendizado falhou: {str(e)[:80]})")
        rep = self.report_lines()
        for l in rep:
            log(f"  {C.GRAY}{l}{C.R}")
        msg = (self.final_msg or ("Tarefa concluida." if ok else "Parei sem concluir (veja o terminal).")).strip()
        short = task if len(task) <= 70 else task[:67] + "..."
        self.notify(("✅ Concluido: " if ok else "⚠️ Nao concluido: ") + short, msg + (("\n" + rep[0]) if rep else ""), ok)
        return ok

    # ---- verificacao automatica de zips/APKs criados
    def check_file(self, p, out, existed=False):
        name = os.path.basename(p)
        try:
            size = os.path.getsize(p)
        except OSError:
            return ""
        info = f"{size / 1e6:.1f} MB" if size >= 100_000 else f"{size} bytes"
        if not zipfile.is_zipfile(p):
            self.prepared[name] = f"{p} ({info})"
            return f"[file check] {name}: {info} at {p}"
        try:
            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()
        except Exception as e:
            return f"[file check] {name}: CORRUPT/unreadable archive ({e}). Recreate it (maybe the command was killed by the timeout: raise \"timeout\")."
        files = [x for x in names if not x.endswith("/")]
        tops = sorted({x.split("/")[0] for x in names})[:8]
        warn = []
        if not files:
            warn.append("the archive is EMPTY")
        common = os.path.commonpath([x.rstrip("/") for x in names]) if names and not any(x.startswith("/") for x in names) else ""
        if any(ABS_ZIP_RE.match(x) for x in names) or common.count("/") >= 2:
            warn.append("entries are stored with FULL ABSOLUTE paths (data/data/com.termux/...). Recreate it with RELATIVE names: "
                        "cd to the parent folder and run: zip -r -q NAME_$(date +%Y%m%d_%H%M%S).zip folder1 folder2")
        if existed or re.search(r"^\s*updating:", out, re.M):
            warn.append("a file with this name ALREADY EXISTED and was modified (zip adds to / updates the old archive: stale content may remain). "
                        "Create a NEW archive with a NEW unique name")
        kind = ""
        if name.lower().endswith((".apk", ".apks", ".xapk")):
            kind = ", APK ok (AndroidManifest.xml present)" if "AndroidManifest.xml" in names else ""
            if name.lower().endswith(".apk") and not kind:
                warn.append("this does not look like an installable APK (no AndroidManifest.xml)")
        line = f"[file check] {name}: {info} at {p}, {len(files)} files, top-level {tops}{kind}"
        if warn:
            self.prepared.pop(name, None)
            return line + "\nWARNING: " + "; ".join(warn) + ". This file was NOT registered as ready."
        self.prepared[name] = f"{p} ({info}, {len(files)} files, top-level {tops}{kind})"
        return line

    def archive_dirs(self, cmd):
        dirs = {self.cwd, HOME, os.path.join(HOME, "storage/downloads"), os.path.join(HOME, "storage/shared")}
        for tok in re.findall(r"[~/][\w ./\-~]*/", cmd):
            d = self.resolve_path(tok.strip())
            if os.path.isdir(d):
                dirs.add(d)
        return dirs

    def snap_archives(self, cmd):
        pre = {}
        if not re.search(r"\b(zip|tar|7z|cp|mv|cat)\b", cmd):
            return pre
        for d in self.archive_dirs(cmd):
            try:
                for e in os.scandir(d):
                    if e.is_file() and re.search(r"\.(zip|apk|xapk|apks|7z|tgz|tar\.gz|rar)$", e.name, re.I):
                        pre[e.path] = e.stat().st_mtime
            except OSError:
                continue
        return pre

    def verify_shell(self, cmd, txt, t_start, pre=None):
        """Depois de um comando shell: confere zips/APKs criados agora (mesmo com nomes dinamicos $(date))."""
        if not re.search(r"\b(zip|cp|mv|tar|7z|cat|python|dd)\b", cmd):
            return ""
        pre = pre or {}
        found = []
        self._found_hook = lambda L: [self.own(p) for p in L if p not in pre]
        for d in self.archive_dirs(cmd):
            try:
                for e in os.scandir(d):
                    if e.is_file() and re.search(r"\.(zip|apk|xapk|apks|7z|tgz|tar\.gz|rar)$", e.name, re.I) \
                            and e.stat().st_mtime >= t_start - 1:
                        found.append(e.path)
            except OSError:
                continue
        if found:
            self._found_hook(found)
        updates = bool(re.search(r"\b(zip|tar|7z)\b", cmd))  # cp/mv sobre arquivo existente nao e "arquivo antigo atualizado"
        out = [self.check_file(p, txt, existed=(p in pre) and updates) for p in sorted(set(found))[:6]]
        if re.search(r"\bpm path\b", cmd) and txt.count("package:") > 1:
            out.append("[note] pm path lists SEVERAL APKs (base + splits): copy ALL of them (or zip them together); base.apk alone may not install.")
        if re.search(r"\bpm list packages\b", cmd) and len(re.findall(r"^package:", txt, re.M)) > 1 and re.search(r"grep", cmd):
            out.append("[note] several packages match: decide which one the user actually uses (pm list packages -3, dumpsys package <pkg> | "
                       "grep -E 'versionName|lastUpdateTime') or handle both, and say which in the final message.")
        return "\n".join(x for x in out if x)

    def exists_any(self, p):
        q = self.resolve_path(p)
        if os.path.lexists(q):
            return True
        if getattr(self, "dev", None) and q.startswith("/"):
            return self.dev.sh("test -e " + shlex.quote(q) + " && echo y", timeout=10).strip() == "y"
        return False

    def review_done(self, task, claimed, deliverables=None):
        """Portao antes do done: deliverables REAIS (medidos), arquivos preparados nunca enviados e auditoria com o livro-razao do sistema."""
        if self.done_rejects >= 3:
            return None
        dl = deliverables if isinstance(deliverables, list) else ([deliverables] if isinstance(deliverables, str) else [])
        dl = [d.strip() for d in dl if isinstance(d, str) and d.strip()]
        self.final_deliv = dl
        miss = [d for d in dl if not self.exists_any(d)]
        if miss:
            self.done_rejects += 1
            return ("DONE REJECTED by the system: these deliverables you listed do NOT exist: " + ", ".join(miss[:6])
                    + ". Find the real path (find_path / ls) and fix it, or remove the false claim. Never report what you did not verify.")
        if self.prepared and DELIVERY_RE.search(task.lower()):
            acts = " ".join(e.lower() for e in self.log_all if re.match(r"step \d+: (tap|long_press|send_file|tap_cell|type)\b", e))
            miss = [nm for nm in self.prepared if nm.lower() not in acts]
            if miss:
                self.done_rejects += 1
                return ("DONE REJECTED: these files you prepared were NEVER selected/sent in any app (no tap/send_file action mentions them): "
                        + ", ".join(miss) + ". Deliver EACH one and verify it at the destination by name; if one cannot be delivered, say why "
                        "in the done message and add \"force\":true.")
        if self.audit_runs >= 1 or self.simple:  # consulta curta de terminal: a saida do comando e a prova, nao precisa de auditor
            return None
        self.audit_runs += 1
        pend = [f"{i}. {g['goal']}" for i, g in enumerate(self.plan, 1) if not g["done"] and not g.get("final")]
        try:
            msg = {"role": "user", "content": AUDIT_PROMPT.format(
                task=task, claimed=claimed[:600],
                constraints="\n".join("- " + c for c in self.constraints) or "(none)",
                deliv="\n".join("- " + d for d in (self.task_deliv + dl)) or "(none)",
                plan="\n".join(f"[{'x' if g['done'] else ' '}] {g['goal']}" for g in self.plan) or "(none)",
                facts="\n".join(self.facts[-15:]) or "(none)",
                prep="\n".join(f"- {k}: {v}" for k, v in self.prepared.items()) or "(none)",
                ledger="\n".join(self.led[-40:]) or "(nothing recorded)",
                events="\n".join(self.log_all[-80:]) or "(none)")}
            if self.vision and self.last_png and not self.term_only:  # tarefa de terminal: print velho do Termux so confunde o auditor
                msg["images"] = [base64.b64encode(pack(self.last_png, self.imgmax, False)).decode()]
            d = parse_json(self.post_chat([msg], True, timeout=180, predict=500, model=(self.model if msg.get("images") else self.tm())))
        except Exception as e:
            log(f"    (auditoria falhou: {e})")
            if pend and self.done_rejects == 0:
                self.done_rejects += 1
                return "DONE REJECTED (not finished): these PLAN goals are not marked done: " + " | ".join(pend[:8]) + ". Verify them and mark done_goals."
            return None
        if isinstance(d, dict) and d.get("complete") is False and d.get("missing"):
            self.done_rejects += 1
            return ("DONE REJECTED by audit. Missing/unverified: " + "; ".join(str(x) for x in d["missing"][:6])
                    + (". How: " + str(d.get("how", ""))[:200] if d.get("how") else "")
                    + ". Fix it or, if impossible, say exactly why in the done message with \"force\":true.")
        for g in self.plan:  # auditoria aprovou: metas esquecidas viram feitas (acabou a burocracia que forcava o force)
            g["done"] = True
        return None

    # ---- terminal do Termux
    def resolve_path(self, p):
        p = os.path.expanduser(str(p or ""))
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(self.cwd, p))

    @staticmethod
    def _pkgs_by_mgr(cmd):
        pk, pp = [], []
        for m in INSTALL_RE.finditer(cmd):
            pk += m.group(1).split()
        for m in PIP_INSTALL_RE.finditer(cmd):
            pp += m.group(1).split()

        def clean(L):
            return [re.split(r"[=<>!\[]", t)[0] for t in L if t and not t.startswith(("-", ".")) and "/" not in t]
        return clean(pk), clean(pp)

    @classmethod
    def _install_pkgs(cls, cmd):
        a, b = cls._pkgs_by_mgr(cmd)
        return a + b

    @staticmethod
    def _installed(mgr, p):
        """Confere de verdade (nao pela memoria do agente): pip show / dpkg -s."""
        try:
            if mgr == "pip":
                return subprocess.run(["pip", "show", "-q", p], capture_output=True, timeout=30, stdin=subprocess.DEVNULL).returncode == 0
            r = subprocess.run(["dpkg", "-s", p], capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
            return r.returncode == 0 and b"install ok installed" in r.stdout
        except Exception:
            return False

    def dep_guard(self, cmd):
        """Barra pacotes inexistentes no Termux, retentativas de pacote que ja falhou 2x e pula so o que esta MESMO instalado."""
        pk, pp = self._pkgs_by_mgr(cmd)
        pkgs = pk + pp
        if not pkgs:
            return None
        bad = {p: TERMUX_PKG_HINTS[p] for p in pkgs if p in TERMUX_PKG_HINTS}
        if bad:
            return "BLOCKED (not executed): " + "; ".join(f"'{p}': {msg}" for p, msg in bad.items())
        stuck = [p for p in pkgs if self.dep_fail.get(p, (0, ""))[0] >= 2]
        if stuck:
            p = stuck[0]
            return (f"BLOCKED (not executed): installing {', '.join(stuck)} already FAILED {self.dep_fail[p][0]}x in this task. Last error lines:\n"
                    f"{self.dep_fail[p][1]}\nDo NOT retry the same install. Find the root cause in those lines (missing header/library, no wheel for "
                    "this platform, network), try 'pkg search <name>' for a prebuilt Termux package or a prebuilt binary, or call fail with the exact error.")
        failed = [p for p in pkgs if self.dep_status.get(p) == "missing"]
        if failed:
            return (f"BLOCKED (not executed): {', '.join(failed)} was reported as unavailable earlier in this task. Find the right Termux package name "
                    "(pkg search <n>) or another approach; \"force\":true only to retry anyway.")
        have = [p for p in pk if self._installed("pkg", p)] + [p for p in pp if self._installed("pip", p)]
        if len(have) == len(pkgs):
            return (f"SKIPPED (not executed): {', '.join(have)} VERIFIED installed (pip show / dpkg -s). Move on. "
                    "If importing it still fails, the problem is the import/PATH, not the installation.")
        return None

    def update_dep_status(self, cmd, txt, rc=0):
        pk, pp = self._pkgs_by_mgr(cmd)
        pkgs = pk + pp
        if not pkgs:
            return
        if rc == 0:
            for p in pkgs:
                self.dep_fail.pop(p, None)
            return
        tail = "\n".join([l for l in txt.strip().splitlines() if l.strip()][-8:])[-700:]
        missing = bool(PKG_MISSING_RE.search(txt))
        for p in pkgs:
            if p in pp and re.search(r"requirement already satisfied: " + re.escape(p) + r"(?![\w.-])", txt, re.I):
                continue  # este estava ok; o que falhou foi outro
            if missing:
                self.dep_status[p] = "missing"
            else:
                n = self.dep_fail.get(p, (0, ""))[0]
                self.dep_fail[p] = (n + 1, tail)

    def note_cmd(self, cmd, txt, rc):
        k = re.sub(r"\s+", " ", cmd.strip())
        if rc == 0:
            self.cmd_fail.pop(k, None)
            return
        self.cmd_fail[k] = self.cmd_fail.get(k, 0) + 1
        self.cmd_tail[k] = "\n".join([l for l in txt.strip().splitlines() if l.strip()][-8:])[-700:]

    def fail_guard(self, cmd):
        """Vale ate com force: o mesmo comando falhou 3x = repetir nao adianta."""
        k = re.sub(r"\s+", " ", cmd.strip())
        n = self.cmd_fail.get(k, 0)
        if n >= 3:
            return (f"BLOCKED (not executed): this exact command already failed {n}x (even force will not run it). Last error lines:\n{self.cmd_tail.get(k, '')}\n"
                    "Find the ROOT CAUSE: run the failing step verbose (pip -v, make VERBOSE=1), read the last 40 lines (| tail -40), search for the missing "
                    "header/lib/package, or choose another approach. If impossible, call fail quoting the real error line.")
        return None

    SU_WRAP_RE = re.compile(r"\b(?:su|tsu)\s+(?:0\s+sh\s+)?-c\s+(?P<q>[\"'])(?P<c>.*?)(?P=q)", re.S)

    def fix_shell(self, a):
        """su -c "X" / sudo X / tsu viram root:true automaticamente (antes o guard bloqueava e o modelo perdia passos)."""
        cmds = a.get("cmds")
        if isinstance(cmds, list) and cmds and not (a.get("cmd") or a.get("command")):
            joined = " && ".join("{ " + str(c).strip().rstrip(";") + "; }" for c in cmds if str(c).strip())
            a = {**{k: v for k, v in a.items() if k != "cmds"}, "cmd": joined}
        cmd = str(a.get("cmd") or a.get("command") or "")
        new, root = cmd, bool(a.get("root"))
        if self.SU_WRAP_RE.search(new):
            new, root = self.SU_WRAP_RE.sub(lambda m: m.group("c"), new), True
        n2 = re.sub(r"(^|[;&|]\s*)(?:sudo|tsu)\s+", r"\1", new)
        if n2 != new:
            new, root = n2, True
        if new == cmd and root == bool(a.get("root")):
            return a
        log(f"  {C.DIM}(su/sudo convertido para root:true){C.R}")
        out = {k: v for k, v in a.items() if k != "command"}
        out["cmd"], out["root"] = new, root
        return out

    def term_guard(self, kind, a):
        if kind == "send_file" and a.get("path"):
            p = self.resolve_path(a["path"])
            n = self.sent_files.get(p, 0)
            if n >= 1 and not a.get("force"):
                return (f"BLOCKED (not executed): send_file for this exact file was already triggered {n}x in this task. "
                        "Do not call it again. VERIFY the delivery: open the destination app and look for the EXACT file name in its list "
                        "(a generic 'upload complete' notification proves nothing). If it is not there, upload from inside the app "
                        "(Drive: + > Upload > tap_text with the file name). \"force\":true only to deliberately resend.")
        if kind == "shell":
            fg = self.fail_guard(str(a.get("cmd") or a.get("command") or ""))
            if fg:
                return fg
        if kind == "shell":  # arquivos alheios: nem o force passa (so o humano libera)
            cmd_s = str(a.get("cmd") or a.get("command") or "")
            dgd = self.delete_guard(cmd_s)
            if dgd:
                return dgd
            pipe_sh = re.search(r"\b(curl|wget)\b[^|;&]*\|\s*(ba|z)?sh\b", cmd_s)
            risky = DANGER_RE.search(self.analyze_cmd(cmd_s)["rest"])
            if (pipe_sh or risky) and not self.allow_risky and not (risky and not pipe_sh and a.get("force") and self.destructive_ok):
                return ("BLOCKED (not executed): destructive/risky command (kill, uninstall, reboot, mount, su, pipe-to-shell...). "
                        "For root use \"root\":true instead of su/sudo. It only runs when the TASK itself asks for something destructive.")
        if kind == "write_file" and a.get("path") and not a.get("append"):
            wp = self.resolve_path(a["path"])
            if os.path.exists(wp) and not self.can_touch(wp):
                if not (self.can_ask and self.ask_human(f"O agente quer SOBRESCREVER {wp}, que ele não criou.")):
                    self.blocked_foreign += 1
                    self.led.append(f"BLOCKED overwrite of foreign file {wp}")
                    return "BLOCKED (not executed): that file already exists and is not yours. Use append=true or another file name."
                self.approved.add(self.norm(wp))
        if a.get("force"):
            return None
        if kind == "shell":
            dg = self.dep_guard(str(a.get("cmd") or a.get("command") or ""))
            if dg:
                return dg
        return None

    HEAVY_RE = re.compile(r"\b(pip3?\s+install|pkg\s+install|apt(-get)?\s+install|npm\s+install|cargo|cmake|make|ninja|git\s+clone|wget|curl|unzip|tar|gradle)\b")

    def term(self, cmd, timeout=30, root=False, _healed=False):
        cmd = str(cmd or "").strip()
        if not cmd:
            return "error: informe cmd"
        heavy = bool(self.HEAVY_RE.search(cmd))
        try:
            timeout = max(1, min(int(float(timeout)), 1800 if heavy else 300))
        except (TypeError, ValueError):
            timeout = 30
        if heavy:  # builds/instalacoes eram mortos em 30s (exit -9) e deixavam o dpkg quebrado
            timeout = max(timeout, 900)
        cmd = STORAGE_RE.sub(r"\1/", cmd)
        pre = self.snap_archives(cmd)
        info = self.analyze_cmd(cmd)
        pre_new = self.snap_new(info)
        t_start = time.time()
        wrapped = (f"export PA_TMP={shlex.quote(self.scratch)}\ncd {shlex.quote(self.cwd)} 2>/dev/null\n{cmd}\n__rc=$?\n"
                   "echo\necho __PA_PWD__$(pwd)\nexit $__rc")
        if root:  # o "timeout" do Android mata o filho root, que o killpg do Termux nao alcanca
            wrapped = f"timeout {timeout + 2} sh -c {shlex.quote(wrapped)}"
        p = subprocess.Popen(self.dev.argv(wrapped) if root else ["sh", "-c", wrapped], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, start_new_session=True)
        buf, note = [], ""

        def pump():
            for line in iter(p.stdout.readline, b""):
                buf.append(line)
                sline = line.decode("utf-8", "replace").strip()
                if sline and self.spin:
                    self.spin.set(" · " + _trim(re.sub(r"\s+", " ", sline), 36))
        th = threading.Thread(target=pump, daemon=True)
        th.start()
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
            note = f"\n[timeout {timeout}s: command killed]"
        th.join(5)
        txt = b"".join(buf).decode("utf-8", "replace")
        if "__PA_PWD__" in txt:
            txt, _, pwd = txt.rpartition("__PA_PWD__")
            if not root and os.path.isdir(pwd.strip()):  # com root o cd nao persiste (o Termux nem enxerga /data/app)
                self.cwd = pwd.strip()
        if not _healed and "dpkg was interrupted" in txt:
            log(f"  {C.YELLOW}! dpkg interrompido: rodando 'dpkg --configure -a' e repetindo o comando{C.R}")
            try:
                subprocess.run(["dpkg", "--configure", "-a"], stdin=subprocess.DEVNULL, capture_output=True, timeout=900)
            except Exception:
                pass
            return self.term(cmd, timeout, root, True)
        rc = p.returncode
        self.cmd_total += 1
        self.cmd_errs += 1 if rc else 0
        self.empty_streak = self.empty_streak + 1 if (rc or not txt.strip()) else 0
        try:
            self.track_new(pre_new)
            if info["dels"] and not rc:
                self.led.append("deleted (allowed): " + ", ".join(t for t, _, _ in info["dels"][:6]))
        except Exception:
            pass
        self.update_dep_status(cmd, txt, rc)
        self.note_cmd(cmd, txt, rc)
        try:
            extra = self.verify_shell(cmd, txt, t_start, pre)
        except Exception as e:
            extra = f"[file check failed: {e}]"
        body = clip(txt.strip()) if rc == 0 else tail_clip(txt.strip())
        return f"[cwd {self.cwd}] [exit {rc}]\n{body}{note}" + (("\n" + extra) if extra else "")

    def act(self, a):
        name = str(a.get("action", "")).lower().strip()
        name = {"click": "tap", "press": "tap", "scroll_down": "scroll", "read": "read_all", "readall": "read_all",
                "record": "play_and_read", "play": "play_and_read", "listen_audio": "listen",
                "select": "select_words", "select_chips": "select_words", "highlight_words": "select_words",
                "choose_words": "select_words", "mark_words": "select_words",
                "alarm": "set_alarm", "create_alarm": "set_alarm", "new_alarm": "set_alarm", "timer": "set_timer", "start_timer": "set_timer",
                "set_device": "device", "toggle": "device", "setting": "device", "set_setting": "device",
                "set_time": "time_picker_set", "picker": "time_picker_set"}.get(name, name)
        name = TERM_ALIAS.get(name, name)
        if name in TERM_KINDS:
            self.act_kind = name
        sh = self.dev.sh
        if name in ("tap", "long_press"):
            e = self.element(a)
            if not e:
                return "error: indice invalido"
            e, err = self.uncover(e)
            if err:
                return err
            if name == "tap" and self.audio and AUDIO_RE.search(e["line"].lower()):
                self.act_kind = "play_and_read"
                return self.capture_audio((e["cx"], e["cy"]))
            if name == "tap":
                self.tap((e["cx"], e["cy"]))
            else:
                sh(f"input swipe {e['cx']} {e['cy']} {e['cx']} {e['cy']} 900")
            return "ok"
        if name in ("tap_cell", "tap_xy"):
            xy, err = self.target_xy(a)
            if err or not xy:
                return err or "error: informe cell ou x,y"
            self.tap(xy)
            return f"ok (toque em {xy[0]},{xy[1]})"
        if name == "order_words":
            return self.order_words(a)
        if name == "select_words":
            return self.select_words(a)
        if name == "hide_keyboard":
            if not self.kb_shown:
                return "ok (the keyboard is not open)"
            sh("input keyevent 4")
            time.sleep(0.7)
            return "ok: keyboard hidden. Read the next screen: it shows what was under the keyboard."
        if name == "type":
            # 1) "index"/"cell"/x,y: toca no campo antes de digitar. 2) sem alvo e sem campo em foco: toca no 1o campo de texto da tela.
            #    (antes digitava "no vazio" e respondia ok: o agente repetia o type em loop)
            tapped = None
            if a.get("index") is not None or a.get("cell") or a.get("x") is not None:
                xy, err = self.target_xy(a)
                if err:
                    return err
                if xy:
                    self.tap(xy)
                    tapped = xy
            elif self.els and not self.focused_edit(self.els):
                eds = [e for e in self.els if "editable" in e["line"]]
                if not eds:
                    return ("error: no text field is focused and none is visible. Tap the field first (or open the page that has one), "
                            "then type. Do not repeat this type.")
                self.tap((eds[0]["cx"], eds[0]["cy"]))
                tapped = (eds[0]["cx"], eds[0]["cy"])
            if tapped:
                time.sleep(0.6)
            clear = a.get("clear")
            if clear is None:  # campo ja com texto (resposta anterior): apaga antes, senao concatena
                clear = bool(tapped) or any("editable" in e["line"] and "focused" in e["line"] and e["text"] for e in self.els)
            clear = bool(clear)
            if a.get("file"):
                p = self.resolve_path(a["file"])
                if not os.path.isfile(p):
                    return f"error: arquivo nao encontrado: {p}"
                with open(p, encoding="utf-8", errors="replace") as f:
                    out = self.type_text(f.read()[:60000], clear)
            else:
                out = self.type_text(str(a.get("text", "")), clear)
            if a.get("submit") or a.get("enter"):
                time.sleep(0.4)
                sh("input keyevent 66")
                time.sleep(1.2)
                out += " + Enter"
            return out
        if name == "enter":
            sh("input keyevent 66")
            return "ok"
        if name == "scroll":
            d = str(a.get("direction", "down")).lower()
            finger = {"down": "up", "up": "down", "left": "right", "right": "left"}.get(d)
            if not finger:
                return "error: direcao invalida (down|up)"
            el = self.element(a) if a.get("index") is not None else None
            self.do_swipe(finger, a.get("times", 1), el)
            return "ok"
        if name == "swipe":
            d = str(a.get("direction", "up")).lower()
            if not self.do_swipe(d, a.get("times", 1)):
                return "error: direcao invalida"
            return "ok"
        if name == "back":
            sh("input keyevent 4")
            return "ok"
        if name == "home":
            sh("input keyevent 3")
            self.left_term = True
            return "ok"
        if name == "open_app":
            pkg = self.resolve_app(str(a.get("app", "")))
            if not pkg:
                return "error: app nao encontrado"
            if pkg == "com.termux" and not re.search(r"termux", getattr(self, "screen_task", "") or "", re.I):
                return ("ok: you are ALREADY inside Termux (the agent's own terminal) - nothing to open. Use shell for commands, or open_url/open_app "
                        "for the app/site the TASK needs.")
            out = sh(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1 2>&1")
            if "No activities" in out:
                return f"error: {pkg} sem atividade"
            self.left_term = True
            time.sleep(2)
            return f"ok ({pkg})"
        if name == "open_url":
            url = str(a.get("url") or a.get("query") or "").strip()
            if not url:
                return 'error: informe "url"'
            if not re.match(r"^[a-z][a-z0-9+.\-]*://", url, re.I):
                if " " not in url and re.search(r"\.[a-z]{2,}(/|$|\?)", url, re.I):
                    url = "https://" + url
                else:  # palavras soltas: pesquisa no Google (mais rapido que digitar na barra do navegador)
                    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(url)
            sh("am start -a android.intent.action.VIEW -d " + shlex.quote(url))
            self.left_term = True
            time.sleep(3)
            return f"ok ({url[:100]})"
        if name == "wait":
            time.sleep(min(float(a.get("seconds", 2)), 15))
            return "ok"
        if name == "read_all":
            return self.read_all()
        if name == "zoom":
            return self.zoom(a)
        if name == "listen":
            return self.capture_audio(None, a.get("seconds"))
        if name == "play_and_read":
            xy, err = self.target_xy(a)
            if err:
                return err
            return self.capture_audio(xy, a.get("seconds"))
        if name == "speak":
            if shutil.which("termux-tts-speak"):
                subprocess.run(["termux-tts-speak", str(a.get("text", ""))], timeout=60)
            return "ok"
        if name == "ask_user":
            self.notify("❓ phoneagent pergunta", str(a.get("question", ""))[:300], False)
            if not sys.stdin.isatty() or not self.can_ask:
                return "user not available (non-interactive run): choose the safest option yourself and say so in notes"
            return "usuario respondeu: " + input(f"  Agente pergunta: {a.get('question', '')}\n  > ").strip()
        if name == "shell":
            return self.term(a.get("cmd") or a.get("command"), a.get("timeout", 30), bool(a.get("root")))
        if name == "read_file":
            p = self.resolve_path(a.get("path"))
            if not os.path.isfile(p):
                return f"error: arquivo nao encontrado: {p}"
            try:
                n = max(200, min(int(a.get("max_chars") or 6000), 20000))
            except (TypeError, ValueError):
                n = 6000
            size = os.path.getsize(p)
            with open(p, "rb") as f:
                raw = f.read(n * 4 + 1)
            if b"\0" in raw[:2048]:
                return f"error: arquivo binario ({size} bytes): {p}"
            txt = raw.decode("utf-8", "replace")
            cut = len(txt) > n or size > len(raw)
            return txt[:n] + (f"\n...[cortado; arquivo tem {size} bytes. Use shell com head/tail/sed -n/grep para o resto]" if cut else "")
        if name == "write_file":
            if not a.get("path"):
                return "error: informe path"
            p = self.resolve_path(a["path"])
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            existed = os.path.lexists(p)
            with open(p, "a" if a.get("append") else "w", encoding="utf-8") as f:
                f.write(str(a.get("content", "")))
            if not existed:
                self.own(p)
                self.led.append(f"created {p}")
            return f"ok ({os.path.getsize(p)} bytes em {p})"
        if name == "send_file":
            p = self.resolve_path(a.get("path"))
            if not os.path.isfile(p):
                return f"error: arquivo nao encontrado: {p}"
            if not shutil.which("termux-share"):
                return "error: termux-share ausente. Rode: pkg install termux-api (e instale o app Termux:API)"
            try:  # nao espera o Termux:API (podia travar 60s por chamada): dispara e segue
                pr = subprocess.Popen(["termux-share", "-a", "send", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      start_new_session=True)
            except OSError as e:
                return f"error: termux-share falhou ({e})"
            self.sent_files[p] = self.sent_files.get(p, 0) + 1
            try:
                pr.wait(timeout=8)
            except subprocess.TimeoutExpired:
                return (f"share request for {os.path.basename(p)} sent (Termux:API is slow, no confirmation yet). Do NOT call send_file again: "
                        "use {\"action\":\"screen\"} once. If the share sheet is open, tap the target. If it is not open, upload from inside "
                        f"the destination app (Drive: + > Upload > tap_text \"{os.path.basename(p)}\").")
            time.sleep(1.5)
            self.left_term = True
            return (f"ok: share sheet opened with {os.path.basename(p)}. Tap the target ONCE (Drive/WhatsApp/etc send immediately on tap, "
                    "no extra 'Send' button, except chat apps which need a conversation picked first then Send). "
                    "Landing back on the launcher right after is normal (background upload), not a failure.")
        if name == "web_search":
            return self.web_search(a)
        if name == "web_fetch":
            return self.web_fetch(a)
        if name == "download":
            return self.download(a)
        if name == "find_path":
            return self.find_path(a)
        if name == "zip_items":
            return self.zip_items(a)
        if name == "tap_text":
            return self.tap_text(a)
        if name == "screen":
            return "ok (screen will be captured next turn)"
        if name == "set_alarm":
            return self.act_set_alarm(a)
        if name == "set_timer":
            return self.act_set_timer(a)
        if name == "device":
            return self.act_device(a)
        if name == "time_picker_set":
            return self.act_time_picker(a, parse_ui)
        return f"error: acao desconhecida '{name}'"

    def finish_box(self, ok, n, msg):
        """Resultado final sem caixa: titulo de uma linha + a mensagem COMPLETA (mantem as quebras de linha: listas nao sao cortadas)."""
        secs = time.time() - self.t_task
        rule()
        used = " · ".join(f"{short_model(m)} ×{c}" for m, (c, t) in self.stats.items()) or "-"
        col = C.GREEN if ok else C.RED
        log(f"{col}{C.B}{'✓ Concluído' if ok else '✗ Não concluído'}{C.R} {C.GRAY}· {n} passos · {secs:.0f}s · {used}{C.R}")
        width = min(shutil.get_terminal_size((70, 20)).columns, 100) - 2
        out = []
        for raw in (str(msg).strip() or "-").splitlines():
            out += textwrap.wrap(raw, width, subsequent_indent="  ") or [""]
        for l in out[:80]:
            log(f"  {l}")
        if len(out) > 80:
            log(f"  {C.DIM}… +{len(out) - 80} linhas (veja ~/.phoneagent_logs){C.R}")
        flog("RESULTADO FINAL:\n" + str(msg))

    # ---- loop principal
    def _run(self, task, max_steps):
        hist, errors, notes = [], 0, ""
        unlimited = max_steps is None or max_steps <= 0
        self.transcript, self.transcript_texts, self.read_step = "", set(), -99
        self.tr, self.reads, self.events, self.tid_n = [], [], [], 0
        self.audio_fails, self.audio_block_until, self.last_capture_step = 0, 0, -99
        self.q_start, self.q_blocks, self.fb_seen, self.fb_now = 0, 0, False, False
        self.cwd = self.start_cwd
        self.sent_files = {}
        self.plan, self.facts, self.advice, self.pkgs, self.pkgs_step = [], [], "", set(), -99
        self.dep_status = {}
        self.dep_fail, self.cmd_fail, self.cmd_tail, self.stats, self.t_task = {}, {}, {}, {}, time.time()
        self.loop_hits, self.last_loop_step, self.loop_ban, self.loop_ban_until, self.ban_blocks = 0, -99, set(), 0, 0
        self.task_toks = task_tokens(task)
        self.task_text, self.destructive_ok = task, bool(DESTRUCTIVE_TASK_RE.search(task))
        kind0 = self.mode if self.mode in ("terminal", "screen") else task_kind(task)
        self.term_only = kind0 == "terminal"
        self.simple = self.term_only and task_is_simple(task)
        self.left_term, self.screen_task, self.return_term = False, task, self.term_only
        self.last_model = None
        log(f"  {C.DIM}{'terminal · ' + short_model(self.tm()) if self.term_only else 'tela · ' + short_model(self.model) + ' (visão)'}"
            f"{' · rápido' if self.simple else ''}{C.R}")
        self.prepared, self.log_all, self.done_rejects, self.audit_runs = {}, [], 0, 0
        self.make_scratch()
        self.constraints, self.task_deliv, self.final_deliv, self.last_ls_cwd = [], [], [], None
        self.sys_prompt = self.prompt_for(task)
        self.brain_reset(task)
        if self.intent and self.fast_enabled:
            self.refresh_pkgs(0, "")
            fast = self.fast_path(task)
            if fast is not None:
                return fast
        self.load_memory()
        # sem HOME no inicio: tarefa de terminal nunca sai do terminal; tarefa de tela vai direto para o app/site (open_app/open_url)
        if not self.term_only:
            self.refresh_pkgs(0, "")
        if self.simple:  # pergunta curta de terminal: sem planejador e sem auditoria (cada um custava uma chamada de modelo)
            self.plan, self.constraints, self.task_deliv, self.plan_question = [], [], [], ""
        else:
            with Spinner(["Planejando"], f" · {short_model(self.tm())}"):
                self.make_plan(task)
        if self.constraints or self.task_deliv:
            for c in self.constraints[:5]:
                log(f"  {C.DIM}limite  {c}{C.R}")
            for d in self.task_deliv[:5]:
                log(f"  {C.DIM}entrega {d}{C.R}")
        if self.plan_question and self.can_ask and sys.stdin.isatty():
            self.notify("❓ phoneagent pergunta", self.plan_question, False)
            try:
                ans = input(f"  {C.YELLOW}? {self.plan_question}{C.R}\n  > ").strip()
            except (EOFError, KeyboardInterrupt):
                ans = ""
            if ans:
                task += "\n\nUSER CLARIFICATION: " + ans
                self.task_text = task
                with Spinner(["Replanejando"], f" · {short_model(self.tm())}"):
                    self.make_plan(task)
        n = 0
        while unlimited or n < max_steps:
            n += 1
            if n % 25 == 0:
                log(f"  {C.DIM}... ainda trabalhando (passo {n}){C.R}")
            self.cur_step, self.act_kind = n, None
            t0 = time.time()
            skip = (bool(hist) and hist[-1][3] in SKIP_OBS) or (self.term_only and not (hist and hist[-1][3] == "screen"))
            try:
                if skip:
                    pkg, els, shot, self.els = "?", [], None, []
                else:
                    with Spinner(["Lendo a tela"]):
                        pkg, els, shot = self.observe()
                errors = 0
            except Exception as e:
                errors += 1
                log(f"  {C.RED}✗ erro ao ler a tela ({errors}/5): {e}{C.R}")
                if errors >= 5:
                    log(f"\n{C.RED}✗ Resumo:{C.R} parei no passo {n} por falha repetida ao ler a tela (root/su). "
                        f"Notas da tarefa ate aqui: {notes or '(nenhuma)'}")
                    self.final_msg = "Falha repetida ao ler a tela (su negou o acesso?). " + (notes or "")[:200]
                    return False
                time.sleep(3)
                continue
            t_obs = time.time() - t0
            self.cur_pkg = pkg if pkg != "?" else self.cur_pkg
            if not self.term_only:
                self.refresh_pkgs(n, pkg)
            # assinatura sem numeros (cronometros e barras de progresso mudam sempre)
            basis = "|".join(re.sub(r"\d+", "#", e["line"]) for e in els) if els else (shot or "")
            sig = hashlib.md5(basis.encode()).hexdigest()[:8]
            if hist and not skip:
                h = hist[-1]
                hist[-1] = (h[0], h[1], h[2] + (" [screen changed]" if sig != h[1] else " [screen did NOT change]"), h[3])
            unchanged = 0
            for h in reversed(hist):
                if h[1] != sig:
                    break
                if h[3] not in ("wait", "listen", "play_and_read", "read_all", "zoom", "scroll", "done_rejected", "invalid", *SKIP_OBS):
                    unchanged += 1
            if unchanged >= 3 and not skip:
                rr = self.rescue(task, n, unchanged, els, pkg)
                if rr:
                    show_result(rr, 6)
                    hist.append(("auto-rescue time_picker_set", sig, rr, "auto"))
                    time.sleep(self.delay + 0.8)
                    continue
            if unchanged > 0 and unchanged % 3 == 0 and unchanged // 3 >= 2:  # 1o aviso (3 acoes) so avisa o modelo; depois escala
                tier = (unchanged // 3 - 2) % 3  # back -> home -> home+launcher (sair do app perde o progresso do exercicio)
                key, nm = {0: (4, "back"), 1: (3, "home"), 2: (3, "home")}[tier]
                log(f"  {C.YELLOW}! recuperacao automatica: {nm} (tela parada ha {unchanged} acoes){C.R}")
                self.dev.sh(f"input keyevent {key}")
                if tier == 2 and self.home:
                    time.sleep(0.8)
                    self.dev.sh("input keyevent 3")
                hist.append((f"auto-recovery {nm}", sig, "ok", "auto"))
                time.sleep(self.delay + 1)
                continue
            loop_warn = ""
            lp = self.detect_loop(hist)
            if not lp and self.ban_blocks >= 3:
                lp = (0, list(self.loop_ban))
            if lp and n - self.last_loop_step >= 4:
                self.last_loop_step, self.loop_hits, self.ban_blocks = n, self.loop_hits + 1, 0
                self.loop_ban, self.loop_ban_until = set(lp[1]) or self.loop_ban, n + 8
                desc = " -> ".join(x[:60] for x in lp[1])
                log(f"  {C.YELLOW}! LOOP detectado (#{self.loop_hits}): {desc}{C.R}")
                self.events.append(f"step {n}: LOOP detected ({desc[:120]})")
                if self.loop_hits >= 4:
                    log(f"\n{C.RED}{C.B}✗ Preso em loop mesmo apos replanejar. Encerrando com resumo.{C.R}")
                    done_g = [g["goal"] for g in self.plan if g["done"]]
                    self.final_msg = ("Fiquei preso em loop (" + desc[:80] + "). Feito: " + ("; ".join(done_g) or "nada confirmado")
                                      + ". Fatos: " + "; ".join(f.split(" (step")[0] for f in self.facts[-5:]))
                    return False
                if self.loop_hits == 2:
                    self.replan(task, lp[1])
            if self.loop_hits and n <= self.loop_ban_until:
                loop_warn = ("\nLOOP WARNING: you were repeating the same actions (" + " -> ".join(self.loop_ban)[:200] + ") without progress. "
                             "Re-read PLAN and FACTS: the goal behind this loop is probably ALREADY ACHIEVED (e.g. app installed or open, "
                             "VPN shows connected). Mark it in done_goals and do the NEXT PENDING GOAL. Do not go back to the launcher "
                             "just to reopen the same app.")
                if self.loop_hits >= 3:
                    loop_warn += (" FINAL WARNING: if the remaining goals cannot be done, call done NOW with a summary of what was "
                                  "achieved and what was skipped.")
            if els:
                screen = "\n".join(e["line"] for e in els)
                if self.grid_mode:
                    screen += "\n(UI tree is poor: rely on the screenshot and tap_cell)"
            else:
                screen = ("(no UI tree: the screen is probably a video/game/canvas. Use the screenshot, which has a red grid with cell "
                          "labels A1..F12; act with tap_cell)")
            if skip:
                screen = ("(screen not captured: terminal-only task. Use {\"action\":\"screen\"} only if you really need to see the phone)"
                          if self.term_only else
                          "(screen not captured: your last action was a terminal action. Use {\"action\":\"screen\"} to see the phone)")
            recent = "\n".join(f"{i}. {h[0]} -> {h[2][:400]}" for i, h in enumerate(hist[-8:], 1)) or "(none)"
            warn = ""
            if unchanged >= 15:
                warn = ("\nSTRONG WARNING: stuck on the same screen for %d actions despite automatic back/home recovery. "
                        "Stop repeating the same approach. Either try something COMPLETELY different (a different app/path/menu), "
                        "or if this part of the task is truly not achievable, SKIP it now: note it and move on to the rest of the "
                        "TASK, or call done/fail summarizing what happened." % unchanged)
            elif unchanged >= 3:
                warn = ("\nWARNING: the screen did not change after your last %d actions. This approach is not working: "
                        "try another element, scroll, open_app, tap_cell or very different coordinates. If this is a chip/selection exercise, "
                        "re-read the [SELECTED] marks: your taps may be toggling chips on and off." % unchanged)
            elif len(hist) >= 3 and hist[-1][3] != "wait" and len({h[0] for h in hist[-3:]}) == 1:
                warn = "\nWARNING: you repeated the exact same action 3 times. Choose a different action."
            if self.audio and has_media(els) and self.last_capture_step < getattr(self, "q_start", 0):
                warn += ("\nHINT: this question has a media control and you have NOT listened to it for THIS question. If the answer depends on "
                         "what is said, play it first (play_and_read); skip it only if a transcript/text already STATES the fact.")
            if self.kb_shown:
                warn += ("\nKEYBOARD OPEN" + (f" (it covers the screen from y={self.kb_top} down)" if self.kb_top else "")
                         + ": the screenshot/list may hide the answer field, options or Continue below it. After typing call hide_keyboard "
                         "and read the screen again to VERIFY the field before submitting. Never answer from a screen you cannot fully see.")
            self.fb_now = False
            for e in els:
                if FEEDBACK_RE.match(e["text"].strip().lower()) and len(e["text"]) < 60:
                    self.fb_now = True
                    ev = f'step {n}: screen shows feedback "{e["text"].strip()}"'
                    if not self.events or self.events[-1] != ev:
                        self.events.append(ev)
                    break
            if self.fb_now:
                self.fb_seen = True
            elif getattr(self, "fb_seen", False):  # saiu da tela de feedback = comecou outra pergunta
                self.fb_seen, self.q_start, self.q_blocks = False, n, 0
            dm = next((e["text"] for e in els if DONE_RE.search(e["text"].lower())), None)
            if dm:
                warn += (f'\nCOMPLETION SIGNAL on screen: "{dm[:60]}". If the TASK is now satisfied, call done immediately; '
                         "do not start another activity.")
            if any(e["scroll"] for e in els) and n - self.read_step > 5:
                warn += "\nHINT: the screen has scrollable content. If the text continues below, call read_all before answering."
            warn += loop_warn
            warn += self.brain_warn(els, pkg, unchanged)
            self.think = "low" if (self.term_only and (n > 2 or self.simple) and self.loop_hits == 0 and self.empty_streak == 0
                                   and not (hist and hist[-1][3] in ("done_rejected", "invalid"))) else "medium"
            if self.empty_streak >= 3:
                warn += ("\nSEARCH WARNING: your last %d commands failed or returned nothing. Do NOT try another narrow variant: widen the scope "
                         "(all folders / all APK splits / other names), use web_search, or change strategy." % self.empty_streak)
            user = (f"TASK: {task}\n\n{self.env_block(n)}\n\n{self.plan_block()}\n\nNOTES FROM EARLIER TURNS: {notes or '(none)'}\n\nSESSION MEMORY (temporary, this task only):\n"
                    f"{self.memory_block()}\n\nRECENT ACTIONS:\n{recent}{warn}\n\n"
                    + (self.situation(pkg) + "\n\n" if not skip and self.situation(pkg) else "") +
                    f"SCREEN (app: {pkg or '?'}, {self.W}x{self.H}):\n{screen}")
            t1 = time.time()
            try:
                with Spinner() as sp:
                    self.spin = sp
                    a = self.decide(user, shot)
                self.spin = None
            except RuntimeError as e:
                self.spin = None
                errors += 1
                log(f"  {C.RED}✗ erro do modelo ({errors}/5): {e}{C.R}")
                if errors >= 5:
                    log(f"\n{C.RED}✗ Resumo:{C.R} parei no passo {n} por falha repetida do modelo/Ollama. "
                        f"Notas da tarefa ate aqui: {notes or '(nenhuma)'}")
                    self.final_msg = "Falha repetida do modelo/Ollama. " + (notes or "")[:200]
                    return False
                time.sleep(3)
                continue
            errors = 0
            meta = f"{short_model(self.last_model or self.model)} {time.time() - t1:.0f}s"
            if not isinstance(a, dict) or "action" not in a:
                log(f"  {C.RED}✗ resposta invalida do modelo{C.R}")
                hist.append(("invalid json", sig, "error: responda so JSON valido", "invalid"))
                continue
            if isinstance(a.get("params"), dict):  # alguns modelos aninham os parametros em "params": achata
                a = {**a.get("params"), **{k: v for k, v in a.items() if k != "params"}}
            if a.get("notes"):
                notes = str(a["notes"])[:1000]
            if TERM_ALIAS.get(str(a.get("action")).lower(), str(a.get("action")).lower()) == "shell":
                a = self.fix_shell(a)
            self.absorb_meta(a, n)
            act_str = self.act_key(a)
            thought = " ".join(str(a.get("thought", "")).split())[:160]
            if thought and a["action"] not in ("done", "fail"):
                log(f"{C.ORG}✻{C.R} {C.IT}{C.DIM}{thought}{C.R}")
            if a["action"] not in ("done", "fail"):
                log(tool_line(a, meta))
            if a["action"] == "done":
                rej = None if (a.get("force") and self.done_rejects >= 1) else self.review_done(task, str(a.get("message", "")), a.get("deliverables"))
                if rej:
                    log(f"  {C.YELLOW}! {rej[:400]}{C.R}")
                    self.events.append(f"step {n}: done REJECTED -> {rej[:110]}")
                    hist.append((act_str, sig, rej, "done_rejected"))
                    continue
                self.final_msg = str(a.get("message", ""))
                self.finish_box(True, n, self.final_msg)
                return True
            if a["action"] == "fail":
                self.final_msg = str(a.get("message", ""))
                self.finish_box(False, n, self.final_msg)
                return False
            kind = a["action"]
            kl = str(kind).lower().strip()
            limit = 8 if kind == "wait" else 3
            label = self.label_for(a)
            term_block = None
            if self.term_only and kl in ("home", "back", "hide_keyboard"):
                term_block = ("BLOCKED (not executed): this is a TERMINAL task: do not leave Termux. Use shell/read_file/web_search/web_fetch/download "
                              "(their output is already shown to the user). If you already have the answer, call done now.")
            elif self.term_only and kl in UI_ACTIONS:  # o pedido precisa mesmo da tela: escala para o modelo de visao, sem avisar o usuario
                self.term_only = False
                self.sys_prompt = self.prompt_for(task)
                log(f"  {C.DIM}(precisa da tela: {short_model(self.model)} assume){C.R}")
            g = None if term_block else self.guard(a, n)
            if term_block:
                res = term_block
            elif g:
                res = g
            elif kind not in ("play_and_read", "read_all") and len(hist) >= limit and all(h[3] == kind and h[0] == act_str for h in hist[-limit:]):
                res = f"BLOCKED (not executed): you already did this exact action {limit} times in a row. Do something different."
            elif self.step and input("    executar? [Enter=sim / n=nao] ").strip().lower() == "n":
                res = "usuario recusou esta acao; proponha outra"
            else:
                try:
                    if TERM_ALIAS.get(kind, kind) in TERM_KINDS:
                        with Spinner(["Executando", "Rodando", "Processando"]) as sp:
                            self.spin = sp
                            res = self.act(a)
                        self.spin = None
                    else:
                        res = self.act(a)
                except Exception as e:
                    self.spin = None
                    res = f"error: {e}"
            res = self.brain_post(a, TERM_ALIAS.get(kl, kl), res, n)
            flog(f"[passo {n}] {act_str}\n{res}\n")
            show_result(res, 30 if (self.act_kind or kind) in ("shell", "read_file", "web_fetch", "web_search", "find_path") else 6)
            self.log_event(n, a, label, res)
            hist.append((act_str, sig, res, self.act_kind or kind))
            if (self.act_kind or kind) not in TERM_KINDS or kind == "send_file":  # comandos de terminal nao precisam esperar a UI
                time.sleep(self.delay + (0.4 if kind in ("scroll", "swipe") else 0))
        rule()
        log(f"{C.YELLOW}{C.B}! Limite de passos atingido{C.R} ({max_steps}). Notas da tarefa ate aqui: {notes or '(nenhuma)'}")
        self.final_msg = f"Limite de {max_steps} passos atingido. " + (notes or "")[:200]
        return False


def doctor():
    def row(name, ok, tip=""):
        mark = f"{C.GREEN}✓{C.R}" if ok else f"{C.RED}✗{C.R}"
        log(f"  {mark} {name}" + ("" if ok else f"  {C.DIM}-> {tip}{C.R}"))
    log(f"{C.B}Diagnostico:{C.R}")
    try:
        d = Root()
        row("root (su)", True)
        row("screencap via root", d.screenshot()[:8] == PNG_SIG, "deixe a tela ligada e desbloqueada e rode de novo")
        row("uiautomator via root", "<hierarchy" in d.dump(), "tela travada/animada? va para a tela inicial e rode de novo")
    except SystemExit as e:
        row("root (su)", False, str(e))
    row("Pillow (grade/zoom/JPEG)", Image is not None, "pkg install python-pillow")
    try:
        aud = subprocess.run(["dpkg", "--audit"], capture_output=True, timeout=20).stdout.strip()
    except Exception:
        aud = b""
    row("dpkg saudavel", not aud, "rode: dpkg --configure -a")
    row("ffmpeg", bool(shutil.which("ffmpeg")), "pkg install ffmpeg")
    row("termux-notification (aviso ao terminar)", bool(shutil.which("termux-notification")), "pkg install termux-api + app Termux:API")
    row("termux-microphone-record", bool(shutil.which("termux-microphone-record")), "pkg install termux-api + app Termux:API")
    row("termux-share (send_file)", bool(shutil.which("termux-share")), "pkg install termux-api + app Termux:API")
    try:
        http_get("https://duckduckgo.com/", 8, 20000)
        row("internet (web_search/web_fetch/download)", True)
    except Exception as e:
        row("internet (web_search/web_fetch/download)", False, f"sem acesso HTTPS ({_trim(e, 60)}); confira a rede/pkg install ca-certificates")
    row("comando 'phoneagent' no PATH (roda de qualquer pasta)", bool(shutil.which("phoneagent")), "rode ./setup.sh de novo")
    row("armazenamento (~/storage)", os.path.isdir(os.path.join(HOME, "storage")), "rode: termux-setup-storage")
    row("whisper-cli", bool(find_whisper()), "rode ./setup.sh")
    row("modelo whisper", bool(find_whisper_model("base")), "rode ./setup.sh (baixa o 'base')")
    try:
        names = [x["name"] for x in ollama("/api/tags", timeout=8).get("models", [])]
        row(f"Ollama em {HOST} ({len(names)} modelos)", True)
    except Exception as e:
        row("Ollama", False, f"ollama serve & ({e})")


def load_task_text(raw):
    """Se 'raw' for o caminho de um arquivo existente, le o conteudo dele e usa como tarefa
    (ex: 'python agent.py guia.txt'). Caso contrario, usa 'raw' como texto literal da tarefa."""
    raw = (raw or "").strip()
    if not raw:
        return raw
    p = os.path.expanduser(raw)
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                content = f.read().strip()
            if content:
                log(f"tarefa carregada do arquivo: {p} ({len(content)} chars)")
                return content
            log(f"    (arquivo de tarefa {p} esta vazio; usando texto literal)")
        except Exception as e:
            log(f"    (falha ao ler arquivo de tarefa {p}: {e}; usando texto literal)")
    return raw


def main():
    p = argparse.ArgumentParser(description="Agente de IA que controla o Android via root (su) + Ollama")
    p.add_argument("task", nargs="*", help="tarefa em linguagem natural, ou caminho de um .txt com a tarefa (vazio = modo interativo)")
    p.add_argument("--model", help="modelo principal (visao/tela). Padrao: salvo em ~/.phoneagent.json")
    p.add_argument("--text-model", help="modelo so de TEXTO para terminal/plano/auditoria, ex: gpt-oss:120b-cloud ( 'same' = desliga)")
    p.add_argument("--route", choices=["auto", "hybrid", "vision", "text"], default="auto",
                   help="auto: terminal->texto, tela->visao | hybrid: visao descreve e o modelo de texto decide | vision: so o principal")
    p.add_argument("--mode", choices=["auto", "terminal", "screen"], default="auto", help="terminal = sem screenshots (tarefas de CMD)")
    p.add_argument("--pick-models", action="store_true", help="abre o menu para trocar os modelos e salva")
    p.add_argument("--allow-risky", action="store_true", help="desliga o bloqueio de comandos destrutivos (rm, kill, mount...)")
    p.add_argument("--vision", action="store_true", help="forca enviar screenshot (padrao: automatico se o modelo tem visao)")
    p.add_argument("--no-vision", action="store_true", help="nunca enviar screenshot (so arvore de UI)")
    p.add_argument("--max-steps", type=int, default=0, help="0 = sem limite (padrao); a tarefa so para com done/fail")
    p.add_argument("--delay", type=float, default=1.0, help="espera apos cada acao (s)")
    p.add_argument("--ctx", type=int, default=16384, help="num_ctx do Ollama")
    p.add_argument("--timeout", type=int, default=180, help="timeout por resposta do modelo (s)")
    p.add_argument("--img-max", type=int, default=1280, help="maior lado do screenshot enviado (px)")
    p.add_argument("--asr-model", default="base", help="modelo whisper.cpp: tiny|base|small|medium")
    p.add_argument("--audio-lang", default="auto", help="idioma do audio para o whisper (ex: en, pt, es); auto detecta")
    p.add_argument("--audio-max", type=int, default=240, help="maximo de segundos gravados por audio (padrao 240)")
    p.add_argument("--no-ask", action="store_true", help="nunca perguntar ao humano (execucao sem supervisao): pedidos para tocar em arquivos alheios sao NEGADOS")
    p.add_argument("--keep-tmp", action="store_true", help="nao apagar a pasta temporaria ($PA_TMP) no fim (para depurar)")
    p.add_argument("--keep-ollama", action="store_true", help="nao encerrar o Ollama no fim (mesmo que o phoneagent o tenha iniciado)")
    p.add_argument("--no-ollama-start", action="store_true", help="nao iniciar o Ollama sozinho")
    p.add_argument("--step", action="store_true", help="confirmar cada acao antes de executar")
    p.add_argument("--no-home", action="store_true", help="(sem efeito desde a v5: o agente nunca aperta HOME no inicio)")
    p.add_argument("--no-audio", action="store_true", help="desliga a captura automatica de audio ao tocar em play")
    p.add_argument("--no-notify", action="store_true", help="nao enviar notificacao ao terminar a tarefa")
    p.add_argument("--test-notify", action="store_true", help="envia uma notificacao de teste e sai")
    p.add_argument("--debug", action="store_true", help="guarda os audios gravados em ~/phoneagent_shots")
    p.add_argument("--no-fast", action="store_true", help="desliga os atalhos de intencao (alarme, timer, volume, wifi...): tudo passa pelo modelo")
    p.add_argument("--learn", metavar="TEXTO", help="ensina uma licao permanente (ex.: --learn 'para alarme use set_alarm') e sai")
    p.add_argument("--lessons", action="store_true", help="lista as licoes aprendidas e sai")
    p.add_argument("--doctor", action="store_true", help="confere dependencias e sai")
    p.add_argument("--test-audio", action="store_true", help="grava 8s do microfone, transcreve e sai")
    args = p.parse_args()

    if args.doctor:
        ok, why = ensure_ollama(not args.no_ollama_start, args.keep_ollama)
        doctor()
        return
    if args.learn or args.lessons:
        st = brain.LessonStore()
        if args.learn:
            it = st.add(args.learn, tags=brain.tokens(args.learn), domain=brain.domain_of(args.learn), source="user")
            log(f"  {C.GREEN}✓{C.R} licao #{it['id']} salva" if it else "  texto curto demais (min. 12 caracteres)")
        else:
            log(lessons_text(st))
        return
    if args.test_notify:
        if not shutil.which("termux-notification"):
            sys.exit("termux-notification ausente. Rode: pkg install termux-api (e instale o app Termux:API)")
        subprocess.run(["termux-notification", "--id", "phoneagent", "--title", "✅ phoneagent: teste", "--content",
                        "Se voce viu isso, as notificacoes funcionam.", "--priority", "high", "--sound", "--vibrate", "300,150,300"])
        log("notificacao enviada. Se nao apareceu: su -c 'pm grant com.termux.api android.permission.POST_NOTIFICATIONS' "
            "(o setup.sh ja faz isso) e libere notificacoes do Termux:API nas configuracoes do Android")
        return
    dev = Root()
    if args.test_audio:
        ag = Agent(dev, None, asr_model=args.asr_model, audio_lang=args.audio_lang)
        ag.debug = True
        log("Toque um audio/video ou fale perto do microfone AGORA (gravando ~8s)...")
        log(ag.capture_audio(None, 8))
        return
    global _LOGFILE
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _LOGFILE = open(os.path.join(LOG_DIR, time.strftime("%Y%m%d-%H%M%S") + ".log"), "w", encoding="utf-8")
    except OSError:
        pass
    ok_ol, why_ol = ensure_ollama(not args.no_ollama_start, args.keep_ollama)
    if not ok_ol:
        sys.exit(f"Ollama indisponivel: {why_ol}")
    model = pick_model(args.model, force_menu=args.pick_models)
    tmodel = pick_model(args.text_model, "text_model", "Modelo de TEXTO (terminal, plano, auditoria) - nuvem recomendada",
                        allow_same=True, force_menu=args.pick_models)
    if tmodel == model:
        tmodel = None
    if tmodel:
        ensure_model(tmodel)
    if shutil.which("termux-wake-lock"):
        subprocess.run(["termux-wake-lock"])
    vision = True if args.vision else (False if args.no_vision else model_has_vision(model))
    agent = Agent(dev, model, vision, args.delay, args.step, not args.no_home, args.ctx, args.timeout, args.img_max,
                  args.asr_model, args.audio_lang)
    agent.audio, agent.debug, agent.audio_max = not args.no_audio, args.debug, args.audio_max
    agent.fast_enabled = not args.no_fast
    agent.notify_on = not args.no_notify
    agent.can_ask, agent.keep_tmp = not args.no_ask, args.keep_tmp
    agent.text_model, agent.route, agent.mode, agent.allow_risky = tmodel, args.route, args.mode, args.allow_risky
    welcome(agent, dev)
    if Image is None:
        log(f"{C.YELLOW}! dica: pkg install python-pillow (necessario para grade, zoom e screenshots leves){C.R}")
    for m in {model, tmodel} - {None}:  # pre-carrega modelos locais: evita a 1a resposta lenta/timeout
        if "cloud" in m:
            continue
        try:
            log(f"{C.DIM}carregando {m}...{C.R}")
            ollama("/api/generate", {"model": m, "keep_alive": "30m", "prompt": ""}, timeout=300)
        except Exception as e:
            log(f"  {C.YELLOW}! pre-carga de {m} falhou: {e}{C.R}")

    if not args.task and not sys.stdin.isatty():  # echo "tarefa" | phoneagent
        piped = sys.stdin.read().strip()
        if piped:
            args.task, agent.can_ask = [piped], False
    if args.task:
        try:
            ok = agent.run(expand_mentions(load_task_text(" ".join(args.task)), agent.start_cwd), args.max_steps)
        except KeyboardInterrupt:
            log("\ninterrompido")
            sys.exit(130)
        sys.exit(0 if ok else 1)
    repl(agent, args)


def welcome(agent, dev):
    tm = agent.text_model
    log(f"{C.ORG}✻{C.R} {C.B}phoneagent{C.R} {C.GRAY}{BUILD}{C.R}")
    log(f"  {C.GRAY}terminal → {short_model(tm) if tm else short_model(agent.model)}   tela → {short_model(agent.model)}"
        f"{'' if agent.vision else ' (sem visão)'}   {agent.start_cwd}{C.R}")
    log(f"  {C.GRAY}/help para comandos · @arquivo cita um arquivo{C.R}")


def lessons_text(st):
    if not st.items:
        return "  (nenhuma licao ainda: elas aparecem sozinhas depois de erros resolvidos, ou use /learn TEXTO)"
    return "\n".join(f"  #{x['id']:<3} [{x.get('domain', '-')}] {x['text']}  {C.GRAY}(+{x.get('hits', 0)}/-{x.get('misses', 0)}){C.R}" for x in st.items[-40:])


HELP = """  /learn TEXTO      ensina uma licao permanente (entra no prompt das tarefas parecidas)
  /lessons          lista o que o agente aprendeu    /forget N|all  esquece uma licao
  /fast on|off      liga/desliga os atalhos de intencao (alarme, timer, volume, wifi, abrir app)
  /cd PASTA         muda a pasta de trabalho (como no Claude Code, a pasta atual e o contexto)
  /pwd              mostra a pasta de trabalho
  /init             cria um PHONEAGENT.md aqui (instrucoes permanentes deste projeto)
  /memory           mostra os arquivos de instrucoes carregados
  /model            trocar modelo principal (tela/visao)
  /text             trocar modelo de texto (terminal, plano, auditoria) - ideal: nuvem
  /route X          auto | hybrid | vision | text
  /mode X           auto | terminal | screen
  /status           mostra a configuracao atual
  /doctor           confere dependencias
  /clear            limpa a tela
  sair              encerra"""


def handle_cmd(agent, line):
    cmd, _, arg = line.strip().partition(" ")
    arg = arg.strip()
    cfg_key = {"/model": "vision_model", "/text": "text_model"}
    if cmd in cfg_key:
        key = cfg_key[cmd]
        new = pick_model(arg or None, key, "Modelo principal (tela)" if key == "vision_model" else "Modelo de TEXTO", key == "text_model", not arg)
        if arg:
            cfg = load_cfg()
            cfg[key] = arg
            save_cfg(cfg)
        if key == "vision_model" and new:
            agent.model, agent.vision = new, model_has_vision(new)
        elif key == "text_model":
            agent.text_model = new if new != agent.model else None
            agent.text_bad_until = 0
            if agent.text_model:
                ensure_model(agent.text_model)
        log(f"  {C.GREEN}✓{C.R} tela: {agent.model} · texto: {agent.text_model or 'igual ao principal'}")
    elif cmd == "/route" and arg in ("auto", "hybrid", "vision", "text"):
        agent.route = arg
        log(f"  {C.GREEN}✓{C.R} rota: {arg}")
    elif cmd == "/mode" and arg in ("auto", "terminal", "screen"):
        agent.mode = arg
        log(f"  {C.GREEN}✓{C.R} modo: {arg}")
    elif cmd == "/status":
        log(f"  tela: {agent.model} (visao {'on' if agent.vision else 'off'}) · texto: {agent.text_model or '-'} · rota: {agent.route} · modo: {agent.mode}")
    elif cmd == "/cd":
        d = os.path.abspath(os.path.expanduser(arg or "~") if os.path.isabs(os.path.expanduser(arg or "~")) else os.path.join(agent.start_cwd, arg))
        if os.path.isdir(d):
            agent.start_cwd = d
            os.chdir(d)
            log(f"  {C.GREEN}✓{C.R} pasta: {d}")
        else:
            log(f"  {C.RED}✗{C.R} nao existe: {d}")
    elif cmd == "/pwd":
        log("  " + agent.start_cwd)
    elif cmd == "/memory":
        fl = find_memory_files(agent.start_cwd)
        log("  " + ("\n  ".join(fl) if fl else "nenhum PHONEAGENT.md/AGENTS.md/CLAUDE.md (use /init)"))
    elif cmd == "/init":
        p = os.path.join(agent.start_cwd, "PHONEAGENT.md")
        if os.path.exists(p):
            log(f"  ja existe: {p}")
        else:
            with open(p, "w", encoding="utf-8") as f:
                f.write("# Instrucoes do projeto (o phoneagent le este arquivo em toda tarefa feita nesta pasta)\n\n"
                        "- Descreva aqui o que fica nesta pasta, convencoes de nomes e o que NUNCA deve ser tocado.\n"
                        "- Ex.: \"Entregas finais vao em ./saida/\"; \"nao mexa em ./originais/\".\n")
            log(f"  {C.GREEN}✓{C.R} criado {p}")
    elif cmd == "/learn":
        it = agent.lessons.add(arg, tags=brain.tokens(arg), domain=brain.domain_of(arg), source="user") if arg else None
        log(f"  {C.GREEN}✓{C.R} licao #{it['id']} salva" if it else "  uso: /learn texto da licao (min. 12 caracteres)")
    elif cmd == "/lessons":
        log(lessons_text(agent.lessons))
    elif cmd == "/forget":
        log(f"  {C.GREEN}✓{C.R} {agent.lessons.forget(arg)} licao(oes) removida(s)" if arg else "  uso: /forget N  ou  /forget all")
    elif cmd == "/fast" and arg in ("on", "off"):
        agent.fast_enabled = arg == "on"
        log(f"  {C.GREEN}✓{C.R} atalhos: {arg}")
    elif cmd == "/doctor":
        doctor()
    elif cmd == "/clear":
        print("\033[2J\033[H", end="")
    else:
        log(HELP)


def repl(agent, args):
    try:  # historico com seta para cima, como no shell
        import readline
        hist_f = os.path.join(HOME, ".phoneagent_history")
        try:
            readline.read_history_file(hist_f)
        except OSError:
            pass
        atexit.register(lambda: readline.write_history_file(hist_f))
    except ImportError:
        pass
    while True:
        try:
            task = input(f"\n{C.ORG}❯{C.R} ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if task.lower() in ("", "sair", "exit", "quit"):
            break
        if task.startswith("/"):
            handle_cmd(agent, task)
            continue
        try:
            agent.run(expand_mentions(load_task_text(task), agent.start_cwd), args.max_steps)
        except KeyboardInterrupt:
            log("\ninterrompido")


if __name__ == "__main__":
    main()
