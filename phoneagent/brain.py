"""brain.py - o "cerebro" do phoneagent v6. Fica ao lado do agent.py. So biblioteca padrao.

O que resolve (tudo por CODIGO, nao depende do modelo "lembrar de fazer certo"):
  1. ATALHOS DE INTENCAO: pedidos claros ("coloque um alarme as 9", "timer de 10 min", "volume 40%", "ligue o wifi", "abra o youtube")
     sao entendidos por um parser PT-BR/EN e executados direto por intents do Android via root, com VERIFICACAO. Sem modelo, sem Termux:API,
     sem tocar na tela. Se falhar, o agente continua normalmente, mas ja sabendo o que deu errado.
  2. DIAGNOSTICO DE ERROS: cada resultado com erro ganha um [DIAGNOSIS] concreto (causa provavel + o que fazer), a tela ganha
     "SCREEN FINDINGS" (erro visivel, campo vazio, dialogo travado), e abordagens que falharam 2x viram BECOS SEM SAIDA bloqueados.
  3. APRENDIZADO: licoes persistentes em ~/.phoneagent_lessons.json (erro -> o que funcionou). Entram no prompt das proximas tarefas
     parecidas. /learn, /lessons e /forget controlam a memoria.
  4. TERMUX:API MORTO: se um termux-* trava/falha, o agente passa a usar os equivalentes de root (am/cmd/settings/dumpsys) sozinho.
  5. RESGATE: tela parada ha varios passos e o pedido tem atalho (ex.: alarme) -> o codigo executa o atalho em vez de ficar tocando.
"""
import json
import os
import re
import shlex
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

_log = lambda *a, **k: None


def set_logger(fn):
    global _log
    _log = fn


def fold(s):
    """minusculas sem acento, MESMO tamanho do original (indices valem nos dois)."""
    out = []
    for ch in unicodedata.normalize("NFC", str(s)):
        d = unicodedata.normalize("NFD", ch)
        out.append(d[0] if d else ch)
    return "".join(out).lower()


# ====================================================================== 1) PARSER DE INTENCOES (PT-BR / EN)
NUMW = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
        "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14, "quinze": 15, "dezesseis": 16,
        "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12}
_NW = "|".join(sorted(NUMW, key=len, reverse=True))
DAY_IDX = {"domingo": 1, "segunda": 2, "terca": 3, "quarta": 4, "quinta": 5, "sexta": 6, "sabado": 7,
           "sunday": 1, "monday": 2, "tuesday": 3, "wednesday": 4, "thursday": 5, "friday": 6, "saturday": 7,
           "sun": 1, "mon": 2, "tue": 3, "wed": 4, "thu": 5, "fri": 6, "sat": 7, "dom": 1, "seg": 2, "ter": 3, "qua": 4, "qui": 5,
           "sex": 6, "sab": 7}
DAY_NAMES_PT = {1: "dom", 2: "seg", 3: "ter", 4: "qua", 5: "qui", 6: "sex", 7: "sáb"}
_DAYW = "domingos?|segundas?(?:-feiras?)?|tercas?(?:-feiras?)?|quartas?(?:-feiras?)?|quintas?(?:-feiras?)?|sextas?(?:-feiras?)?|sabados?"

ALARM_RE = re.compile(r"\b(alarmes?|despertador|alarm|acorde|acorde-me|acordar|acordem|desperte|desperte-me|despertar|wake\s*me)\b")
MUSIC_RE = re.compile(r"\b(m[úu]sica|music|song|can[cç][aã]o|faixa|track|playlist|album|play)\b")
CODE_RE = re.compile(r"\b(script|codigo|programa|python|bash|funcao|classe|scrape|bot|crie\s+um\s+(?:app|programa|site)|app\s+(?:que|para)|aplicativo\s+(?:que|para))\b")
TIMER_RE = re.compile(r"\b(timers?|temporizador|contagem\s+regressiva|countdown)\b")
REMIND_RE = re.compile(r"\b(me\s+avis\w+|avis\w+-?me|me\s+lembr\w+|lembr\w+-?me|me\s+chame|remind\s+me)\b")
NEG_RE = re.compile(r"\b(apag\w*|delet\w*|remov\w*|cancel\w*|exclu\w*|desativ\w*|desligu?\w*|desabilit\w*|pare|parar|silenci\w*|"
                    r"turn\s+off|disable|stop|dismiss|snooze)\b")
MULTI_RE = re.compile(r"\b(depois|em\s+seguida|e\s+entao|apos|alem\s+disso|tambem|and\s+then|then|afterwards)\b|[;]")
SHOW_RE = re.compile(r"\b(no|pelo|do|nesse|neste|dentro\s+do)\s+(app|aplicativo|relogio|clock)\b|\b(abra|abrir|open)\b.{0,25}\b(relogio|clock|app)\b|"
                     r"\b(mostre|mostrando|na\s+tela|pela\s+interface|show\s+it|visualmente)\b")
LIST_RE = re.compile(r"\b(mostre|abra|veja|liste|listar|ver|exiba|show|list|open)\b.{0,30}\b(alarmes|timers|temporizadores)\b")


MUSIC_APPS = {
    "youtube music": "com.google.android.apps.youtube.music",
    "youtube music premium": "com.google.android.apps.youtube.music",
    "music": "com.google.android.apps.youtube.music",
    "spotify": "com.spotify.music",
    "amazon music": "com.amazon.mp3",
    "deezer": "com.deezer.android",
    "apple music": "com.apple.android.music",
}


def clean_music_name(text):
    return re.sub(r"\s+", " ", (text or "").strip(" \t\r\n\"'.,;!?()[]{}"))


def parse_music_request(f):
    """Analisa pedidos de musica em PT-BR/EN e retorna (title, artist, action)."""
    task = unicodedata.normalize("NFC", f or "")
    low = fold(task)
    if re.search(r"\b(?:bot[ãa]o|button|login|arquivo|file|download|downloads|pasta|folder|campo|tela|app|aplicativo|site|pagina|link|janela|menu|texto)\b", low):
        if not re.search(r"\b(?:m[úu]sica|music|song|can[cç][aã]o|faixa|track|playlist|album|lofi|podcast)\b", low):
            return None, None, None
    if re.search(r"\b(?:pause|pausar|parar|stop|silenciar)\b", low):
        return None, None, "pause"
    if re.search(r"\b(?:continua|continue|retomar|resume|volta\s+a\s+tocar|play\s+again|toca\s+de\s+novo)\b", low):
        return None, None, "resume"
    if re.search(r"\b(?:pr[oó]xima|next|seguinte|proximo|proxima)\b", low):
        return None, None, "next"
    if re.search(r"\b(?:anterior|previous|faixa\s+anterior)\b", low):
        return None, None, "previous"
    for pat in [
        r"(?:m[úu]sica|music|song|can[cç][aã]o|faixa|track)\s*(?:de|da|do)?\s*(?P<title>.+?)(?:\s*(?:da|de|do|por|by|feat\.?|feat|ft\.?|with)\s+(?P<artist>.+?))?(?:$|[.;!?])",
        r"(?:toque|toca|coloque|coloca|reproduz|reproduce|play|start)\s+(?P<title>.+?)(?:\s*(?:da|de|do|por|by|feat\.?|feat|ft\.?|with)\s+(?P<artist>.+?))?(?:$|[.;!?])",
    ]:
        m = re.search(pat, low)
        if not m:
            continue
        title = clean_music_name(m.group("title"))
        artist = clean_music_name(m.group("artist") or "")
        if not title:
            continue
        # remove leading action words and trailing noise
        title = re.sub(r"^(?:coloque|coloca|toque|toca|reproduz|reproduce|play|start|a|o|as|os)\s+", "", title)
        title = title.strip(" -:–")
        if artist:
            artist = artist.strip(" -:–")
        if re.search(r"\b(?:bot[ãa]o|button|login|arquivo|file|download|downloads|pasta|folder|campo|tela|app|aplicativo|site|pagina|link|janela|menu|texto)\b", title + " " + artist):
            return None, None, None
        return title, artist, "play"
    return None, None, None


def choose_music_app(pkgs):
    pkgs = pkgs or set()
    for name, pkg in MUSIC_APPS.items():
        if pkg in pkgs:
            return pkg
    # fallback: known names by short string in package list
    for p in sorted(pkgs):
        low = p.lower()
        if "spotify" in low or "youtube" in low and "music" in low or "deezer" in low or "amazon" in low:
            return p
    return None


def _num(tok):
    tok = tok.strip()
    return int(tok) if tok.isdigit() else NUMW.get(tok)


def _minutes_word(s):
    """'meia', '15', 'quinze', 'quarenta e cinco', 'um quarto' -> minutos."""
    s = s.strip()
    if s in ("meia", "meio"):
        return 30
    if s in ("um quarto",):
        return 15
    if s.isdigit():
        return int(s)
    parts = [p for p in re.split(r"\s+e\s+|\s+", s) if p]
    if parts and all(p in NUMW for p in parts):
        return sum(NUMW[p] for p in parts)
    return None


def parse_duration(f):
    """Duracao em segundos de um texto (ja sem acento/minusculo): '10 minutos', '1h30', 'uma hora e meia', 'meia hora'."""
    m = re.search(r"\b(\d{1,2})\s*h(?:oras?|rs?)?\s*(?:e\s*)?(\d{1,2})(?!\d)(?!\s*(?:seg|sec|s\b|h\b|horas?|hours?))", f)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    total, found = 0, False
    if re.search(r"\bmeia\s+hora\b|\bhalf\s+an?\s+hour\b", f):
        total, found = total + 1800, True
    for m in re.finditer(r"(\d+(?:[.,]\d+)?|" + _NW + r")\s*(horas?|hrs?|hours?|h|minutos?|minutes?|mins?|min|segundos?|seconds?|segs?|secs?|seg)\b", f):
        raw, unit = m.group(1), m.group(2)
        try:
            v = float(raw.replace(",", ".")) if re.match(r"\d", raw) else float(NUMW[raw])
        except (ValueError, KeyError):
            continue
        mult = 3600 if unit.startswith(("h", "hora", "hour")) else (60 if unit.startswith("min") else 1)
        total, found = total + v * mult, True
        if mult == 3600 and re.match(r"\s*e\s+meia\b", f[m.end():]):
            total += 1800
        if mult == 60 and re.match(r"\s*e\s+meio\b", f[m.end():]):
            total += 30
    return int(total) if found and total > 0 else None


_MINTAIL = r"(?:\s+e\s+(meia|um\s+quarto|\d{1,2}(?!\d)|(?:" + _NW + r")(?:\s+e\s+(?:" + _NW + r"))?))?"


def parse_clock_time(f, now=None):
    """-> (hora, minuto, nota) ou None. f = texto sem acento, minusculo. Trata 7h30, 07:30, as 7 e meia, 7 da noite, meio-dia, daqui a 20 min..."""
    now = now or datetime.now()
    # ---- relativo: "daqui a 20 minutos", "em 1 hora e meia"
    m = re.search(r"\b(?:daqui\s+a|dentro\s+de|em|in)\s+((?:\d+(?:[.,]\d+)?|" + _NW + r"|meia)\s*(?:horas?|hrs?|hours?|h|minutos?|minutes?|mins?|min|segundos?|seg)\b.*?)"
                  r"(?=$|[,.;!?]|\s+(?:para|pra|chamad\w*|com|de\s+nome)\b)", f)
    if m:
        secs = parse_duration(m.group(1))
        if secs:
            t = now + timedelta(seconds=secs)
            if t.second >= 30:
                t += timedelta(minutes=1)
            return t.hour, t.minute, f"daqui a {fmt_duration(secs)} = {t.hour:02d}:{t.minute:02d}"
    h = mi = None
    colon = False
    mm = re.search(r"\bmeio[\s-]?dia\b(?:\s+e\s+(meia|\d{1,2}|quinze))?", f)
    if mm:
        h, mi = 12, (_minutes_word(mm.group(1)) if mm.group(1) else 0)
    else:
        mm = re.search(r"\bmeia[\s-]?noite\b(?:\s+e\s+(meia|\d{1,2}|quinze))?", f)
        if mm:
            h, mi = 0, (_minutes_word(mm.group(1)) if mm.group(1) else 0)
    if h is None:
        mm = re.search(r"(?<![\d:.,])(\d{1,2})\s*:\s*(\d{2})(?!\d)", f)
        if mm:
            h, mi, colon = int(mm.group(1)), int(mm.group(2)), True
    if h is None:
        mm = re.search(r"(?<![\d:.,])(\d{1,2})\s*h\s*(\d{2})(?!\d)", f)
        if mm:
            h, mi = int(mm.group(1)), int(mm.group(2))
    if h is None:
        mm = re.search(r"(?<![\d:.,])(\d{1,2}|" + _NW + r")\s*(?:hs|horas?|h)\b" + _MINTAIL, f)
        if mm:
            h, mi = _num(mm.group(1)), (_minutes_word(mm.group(2)) if mm.group(2) else 0)
    if h is None:
        mm = re.search(r"\bas\s+(\d{1,2}|" + _NW + r")\b(?:\s*(?:horas?|h|hs)\b)?" + _MINTAIL, f)
        if mm:
            h, mi = _num(mm.group(1)), (_minutes_word(mm.group(2)) if mm.group(2) else 0)
    if h is None:
        mm = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\b", f)
        if mm:
            h, mi = int(mm.group(1)), int(mm.group(2) or 0)
    if h is None:
        mm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(?:am|pm|a\.m\.|p\.m\.)", f)
        if mm:
            h, mi = int(mm.group(1)), int(mm.group(2) or 0)
    if h is None:
        mm = re.search(r"\b(\d{1,2}|" + _NW + r")\s*(?:horas?\s*)?(?:da|de|na|pela|in\s+the)\s+(?:manha|tarde|noite|madrugada|morning|evening|night)\b", f)
        if mm:
            h, mi = _num(mm.group(1)), 0
    if h is None or mi is None or h < 0 or h > 23 or mi < 0 or mi > 59:
        return None
    pm = bool(re.search(r"\b(?:da|de|na|pela|a)\s+(?:tarde|noite)\b|(?<![a-z])pm\b|\bp\.m\.|\bin\s+the\s+(?:evening|afternoon)\b|\btonight\b", f))
    am = bool(re.search(r"\b(?:da|de|na|pela)\s+(?:manha|madrugada)\b|(?<![a-z])am\b|\ba\.m\.|\bin\s+the\s+morning\b", f))
    note = ""
    if pm and 1 <= h < 12:
        h += 12
    elif pm and h == 12 and re.search(r"\b12\b.{0,10}\bnoite\b", f):
        h = 0
    elif am and h == 12:
        h = 0
    elif not pm and not am and 1 <= h <= 11 and not colon and "meio" not in f:
        note = f"interpretei \"{h}\" como {h:02d}:{mi:02d} (manhã). Para {(h + 12) % 24:02d}:{mi:02d} diga \"da tarde\" ou \"da noite\""
    return h, mi, note


def count_times(f):
    """Quantos horarios diferentes o pedido cita (as 7, as 8, 07:30, 7h...)."""
    n = len(re.findall(r"(?<![\d:.,])\d{1,2}\s*(?::\s*\d{2}|h(?:\s*\d{2}|oras?\b|\b))", f))
    n += len(re.findall(r"\bas\s+(?:\d{1,2}|" + _NW + r")\b(?!\s*(?:h|horas?|:))", f))
    return n


def fmt_duration(secs):
    secs = int(secs)
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    out = []
    if h:
        out.append(f"{h} h")
    if m:
        out.append(f"{m} min")
    if s and not h:
        out.append(f"{s} s")
    return " ".join(out) or "0 s"


def parse_days(f):
    """Dias da semana na convencao Calendar do Android (1=domingo..7=sabado) ou None (= so uma vez)."""
    if re.search(r"\btodos?\s+os\s+dias\b|\btodo\s+dia\b|\bdiariamente\b|\bevery\s*day\b|\bdaily\b", f):
        return [1, 2, 3, 4, 5, 6, 7]
    if re.search(r"\bdias?\s+uteis\b|\bweekdays?\b|\bseg\w*\s*(?:a|-|ate)\s*sex\w*|\bde\s+segunda\s+a\s+sexta\b", f):
        return [2, 3, 4, 5, 6]
    if re.search(r"\bfins?\s+de\s+semana\b|\bweekends?\b|\bsabado\s+e\s+domingo\b", f):
        return [7, 1]
    m = re.search(r"\b(" + _DAYW + r")\s*(?:a|ate)\s*(" + _DAYW + r")\b", f)
    order = [2, 3, 4, 5, 6, 7, 1]
    if m:
        a, b = DAY_IDX.get(re.sub(r"s?(-feiras?)?$", "", m.group(1))), DAY_IDX.get(re.sub(r"s?(-feiras?)?$", "", m.group(2)))
        if a and b:
            i, out = order.index(a), []
            while True:
                out.append(order[i])
                if order[i] == b or len(out) > 7:
                    break
                i = (i + 1) % 7
            return sorted(out)
    days = []
    for w in re.findall(r"\b(" + _DAYW + r")\b", f):
        k = DAY_IDX.get(re.sub(r"s?(-feiras?)?$", "", w))
        if k and k not in days:
            days.append(k)
    return sorted(days) or None


def parse_label(orig, f):
    """Rotulo explicito: chamado X / nome X / "entre aspas" / para X (so no fim, curto)."""
    m = re.search(r"[\"“”'‘’]([^\"“”'‘’]{1,60})[\"“”'‘’]", orig)
    if m:
        return m.group(1).strip()
    cut = r"\s+(?:de\s+segunda|todos?\s+os|todo\s+dia|dias?\s+uteis|nos?\s+fins?|aos?\s+(?:sabados|domingos)|as\s+\d)"
    m = re.search(r"\b(?:chamad[oa]|nome|nomead[oa]|rotulo|etiqueta|label|descricao|called|named)\s*(?:de|do|da)?\s*:?\s*(.+)$", f)
    if m:
        s, e = m.start(1), m.end(1)
        k = re.search(cut, f[s:e])
        if k:
            e = s + k.start()
        return orig[s:e].strip(" .,!?\"'")[:60] or None
    m = re.search(r"\b(?:para|pra|to)\s+((?:ir|fazer|tomar|estudar|acordar|ligar|treinar|sair|buscar|pegar|ver|lembrar|o\s|a\s)\w*.{0,40})$", f)
    if m and len(m.group(1).split()) <= 8 and not re.search(r"\b(as|a)\s+\d", m.group(1)):
        return orig[m.start(1):m.end(1)].strip(" .,!?\"'")[:60] or None
    return None


DEVICE_TOGGLES = [
    ("wifi", r"\bwi-?\s?fi\b"),
    ("bluetooth", r"\bbluetooth\b"),
    ("data", r"\bdados\s+moveis\b|\bmobile\s+data\b|\bdados\s+celulares?\b|\binternet\s+movel\b"),
    ("airplane", r"\bmodo\s+avi[aã]o\b|\bmodo\s+aviao\b|\bairplane\b|\bflight\s+mode\b"),
    ("dnd", r"\bnao\s+perturbe\b|\bnao\s+incomode\b|\bdo\s+not\s+disturb\b|\bdnd\b"),
    ("rotation", r"\brotacao\s+(?:automatica|da\s+tela)\b|\bauto[- ]?rotate\b|\bgirar\s+tela\b"),
]
ON_RE = re.compile(r"\b(ativ\w*|lig\w+|habilit\w*|acion\w*|coloq\w+|ponha|ative|turn\s+on|enable|switch\s+on)\b|\b(?:on|ligado|ativado)\b")
OFF_RE = re.compile(r"\b(desativ\w*|deslig\w*|desabilit\w*|tire|retire|turn\s+off|disable|switch\s+off)\b|\b(?:off|desligado|desativado)\b")
STREAMS = {"media": 3, "ring": 2, "alarm": 4, "notification": 5, "call": 0, "system": 1}
STREAM_PT = {"midia": "media", "musica": "media", "som": "media", "video": "media", "toque": "ring", "campainha": "ring",
             "alarme": "alarm", "notificacao": "notification", "notificacoes": "notification", "chamada": "call", "ligacao": "call"}


class Intent(dict):
    """kind: alarm|timer|show_alarms|show_timers|volume|brightness|toggle|open_app; demais campos em chaves."""

    @property
    def kind(self):
        return self["kind"]

    def summary(self):
        k = self.kind
        if k == "alarm":
            d = self.get("days")
            when = f"{self['hour']:02d}:{self['minute']:02d}"
            if d:
                names = "todos os dias" if len(d) == 7 else " ".join(DAY_NAMES_PT[x] for x in d)
                when += f" ({names})"
            return "alarme " + when + (f" «{self['label']}»" if self.get("label") else "")
        if k == "timer":
            return "timer de " + fmt_duration(self["seconds"]) + (f" «{self['label']}»" if self.get("label") else "")
        if k == "show_alarms":
            return "mostrar alarmes"
        if k == "show_timers":
            return "mostrar timers"
        if k == "music":
            q = self.get("title") or "música"
            if self.get("artist"):
                q += f" — {self['artist']}"
            return f"música {q}"
        if k == "music_control":
            return f"música: {self.get('action', 'play')}"
        if k == "volume":
            return f"volume {self.get('stream', 'media')} → {self.get('value')}"
        if k == "brightness":
            return f"brilho → {self.get('value')}"
        if k == "toggle":
            return f"{self['setting']} → {'ligado' if self['on'] else 'desligado'}"
        if k == "open_app":
            return f"abrir {self['app']}"
        return k


def parse_intent(task, now=None):
    """Entende pedidos CLAROS e curtos. Retorna Intent ou None (None = deixa o modelo decidir). Conservador de proposito."""
    if not task or not task.strip():
        return None
    orig = unicodedata.normalize("NFC", task.strip())
    f = fold(orig)
    if len(f) != len(orig):
        orig = f
    if CODE_RE.search(f):
        return None
    if len(f.split()) > 30 or "\n" in orig.strip() or MULTI_RE.search(f):
        return None
    now = now or datetime.now()
    has_alarm, has_timer = bool(ALARM_RE.search(f)), bool(TIMER_RE.search(f))
    # ---- listar alarmes/timers
    if LIST_RE.search(f) and not re.search(r"\d", f):
        return Intent(kind="show_timers" if re.search(r"timers|temporizadores", f) else "show_alarms")
    # ---- alarme / timer
    if (has_alarm or has_timer or REMIND_RE.search(f)) and not re.search(r"\b(volume|brilho|brightness)\b", f):
        if NEG_RE.search(f):
            return None
        show = bool(SHOW_RE.search(f))
        dur = parse_duration(f)
        is_timer = has_timer or (REMIND_RE.search(f) and not has_alarm and dur and not re.search(r"\b(as|a)\s+\d|\d\s*[:h]\s*\d", f))
        if is_timer and not has_alarm:
            if not dur or dur < 1 or dur > 86400:
                return None
            label = parse_label(orig, f)
            if not label:
                m = re.search(r"\b(?:de|pra|para)\s+(?!\d)(.{3,40})$", f)
                if m and REMIND_RE.search(f) and not re.search(r"\d", m.group(1)):
                    label = orig[m.start(1):m.end(1)].strip(" .,!?")
            return Intent(kind="timer", seconds=dur, label=label, show=show)
        if has_alarm or (REMIND_RE.search(f) and ALARM_RE.search(f)):
            ct = parse_clock_time(f, now)
            if not ct:
                return None
            if count_times(f) > 1 and not re.search(r"\bdaqui\b", f):
                return None  # varios horarios no mesmo pedido: o modelo cria um por vez
            h, mi, note = ct
            return Intent(kind="alarm", hour=h, minute=mi, label=parse_label(orig, f), days=parse_days(f), show=show, note=note)
    # ---- musica / controles simples
    music_like = bool(MUSIC_RE.search(f) or re.search(r"\b(?:toque|toca|reproduz|reproduce|play|start|pausa|pause|resume|continua|continue|next|pr[oó]xima|anterior)\b", f))
    app_play = bool(re.search(r"\b(?:abrir|abra|abre|inicie|launch|open)\b.*\b(?:youtube|spotify|chrome|app|aplicativo|site|browser)\b", f) and re.search(r"\b(?:toque|toca|reproduz|reproduce|play|start)\b", f))
    if app_play:
        return None
    file_noise = bool(re.search(r"\b(?:download|downloads|copi|copiar|salvar|guardar|arquivo|arquivos|pasta|folder|dir)\b", f))
    if file_noise and not music_like:
        return None
    if music_like:
        title, artist, action = parse_music_request(f)
        if action in ("pause", "resume", "next", "previous"):
            return Intent(kind="music_control", action=action)
        if title:
            return Intent(kind="music", title=title, artist=artist, action=action)
    if re.search(r"\be\b|\bcom\b|\bmas\b|\band\b|\bthen\b", f) and not has_alarm:
        simple_conj = True  # dispositivo/volume/brilho: "ligue o wifi e abra o chrome" tem 2 pedidos -> modelo
    else:
        simple_conj = False
    # ---- volume
    if simple_conj and re.search(r"\b(volume|brilho|wi-?fi|bluetooth|dados|aviao|perturbe|rotacao)\b", f):
        return None
    if re.search(r"\bvolume\b", f) or re.search(r"\b(aument\w+|aumentar|suba|subir|abaix\w+|diminu\w+|baix\w+)\b.{0,12}\b(som|volume)\b", f):
        stream = "media"
        for k, v in STREAM_PT.items():
            if re.search(r"\b" + k + r"\b", f):
                stream = v
                break
        mm = re.search(r"\b(\d{1,3})\s*(?:%|por\s*cento)?", f)
        if re.search(r"\b(maximo|maxima|max|full)\b", f):
            return Intent(kind="volume", stream=stream, value="max")
        if re.search(r"\b(mudo|silenc\w+|mute|zero|minimo|minima)\b", f):
            return Intent(kind="volume", stream=stream, value=0 if "mute" not in f and "mudo" not in f else "mute")
        if mm:
            v = int(mm.group(1))
            if 0 <= v <= 100:
                return Intent(kind="volume", stream=stream, value=v)
        if re.search(r"\b(aument\w+|aumentar|suba|subir|mais\s+alto|up|raise)\b", f):
            return Intent(kind="volume", stream=stream, value="+")
        if re.search(r"\b(abaix\w+|diminu\w+|baix\w+|mais\s+baixo|down|lower)\b", f):
            return Intent(kind="volume", stream=stream, value="-")
        return None
    # ---- brilho
    if re.search(r"\b(brilho|brightness)\b", f):
        if re.search(r"\bautomatic\w*|\bauto\b", f):
            return Intent(kind="brightness", value="auto")
        if re.search(r"\b(maximo|maxima|max)\b", f):
            return Intent(kind="brightness", value=100)
        if re.search(r"\b(minimo|minima|min)\b", f):
            return Intent(kind="brightness", value=1)
        mm = re.search(r"\b(\d{1,3})\s*(?:%|por\s*cento)?", f)
        if mm and 0 <= int(mm.group(1)) <= 100:
            return Intent(kind="brightness", value=int(mm.group(1)))
        return None
    # ---- liga/desliga (wifi, bluetooth, dados, aviao, nao perturbe, rotacao)
    for setting, rx in DEVICE_TOGGLES:
        if re.search(rx, f):
            off, on = bool(OFF_RE.search(f)), bool(ON_RE.search(f))
            if off == on:
                return None
            return Intent(kind="toggle", setting=setting, on=on and not off)
    # ---- "abra o youtube" (pedido inteiro = so abrir um app)
    m = re.match(r"^\s*(?:por\s+favor\s*,?\s*)?(?:abra|abrir|abre|inicie|iniciar|execute|open|launch|start)\s+(?:o\s+|a\s+|the\s+)?(?:app\s+|aplicativo\s+)?(?:do\s+|da\s+)?([a-z0-9][a-z0-9 .+_-]{1,30}?)\s*[.!]?\s*$", f)
    if m and not re.search(r"\b(e|com|para|pra|no|na|and|with|site|pagina|url|http|www)\b", m.group(1)):
        return Intent(kind="open_app", app=orig[m.start(1):m.end(1)].strip(" ."))
    return None


# ----------------------------------------------------------------------- comandos Android (root)
CLOCK_PKGS = ("com.google.android.deskclock", "com.android.deskclock", "com.sec.android.app.clockpackage", "com.oneplus.deskclock",
              "com.coloros.alarmclock", "com.oplus.alarmclock", "com.huawei.deskclock", "com.motorola.blur.alarmclock",
              "com.asus.deskclock", "com.lge.clock", "com.sonymobile.clock", "com.htc.android.worldclock", "com.miui.clock")


def clock_pkg(pkgs):
    for p in CLOCK_PKGS:
        if p in (pkgs or ()):
            return p
    for p in sorted(pkgs or ()):
        if re.search(r"deskclock|alarmclock|clockpackage", p):
            return p
    return None


def alarm_cmd(hour, minute, label="", days=None, show=False, pkg=None):
    parts = ["am start -a android.intent.action.SET_ALARM",
             f"--ei android.intent.extra.alarm.HOUR {int(hour)}", f"--ei android.intent.extra.alarm.MINUTES {int(minute)}"]
    if label:
        parts.append("--es android.intent.extra.alarm.MESSAGE " + shlex.quote(str(label)[:60]))
    if days:
        parts.append("--eial android.intent.extra.alarm.DAYS " + ",".join(str(int(d)) for d in sorted(set(days))))
    if not show:
        parts.append("--ez android.intent.extra.alarm.SKIP_UI true")
    if pkg:
        parts.append("-p " + pkg)
    return " ".join(parts) + " 2>&1"


def timer_cmd(seconds, label="", show=False, pkg=None):
    parts = ["am start -a android.intent.action.SET_TIMER", f"--ei android.intent.extra.alarm.LENGTH {int(seconds)}"]
    if label:
        parts.append("--es android.intent.extra.alarm.MESSAGE " + shlex.quote(str(label)[:60]))
    if not show:
        parts.append("--ez android.intent.extra.alarm.SKIP_UI true")
    if pkg:
        parts.append("-p " + pkg)
    return " ".join(parts) + " 2>&1"


def am_failed(out):
    """True se a saida do 'am start' indica que a intent NAO foi entregue."""
    o = (out or "").lower()
    return bool(re.search(r"error:|exception|unable to resolve|not started|does not exist|permission denial|securityexception|bad component|"
                          r"no activity found|unknown option|unknown command", o)) and "brought to the front" not in o


def time_regex(h, m):
    """Casa 9:00 / 09:00 / 9:00 AM / 21:00 / 9:00 PM no texto da tela."""
    h12 = h % 12 or 12
    alts = {f"0?{h}:{m:02d}"}
    if h12 != h:
        alts.add(f"0?{h12}:{m:02d}")
    return re.compile(r"(?<![\d:])(?:" + "|".join(sorted(alts)) + r")(?![\d:])", re.I)


def next_alarm_matches(s, h, m):
    if not s or s.strip().lower() in ("null", "", "none"):
        return False
    rx = time_regex(h, m)
    mt = rx.search(s)
    if not mt:
        return False
    ampm = re.search(r"\b(am|pm)\b", s, re.I)
    if ampm and h != 0 and h12_period(h) != ampm.group(1).lower():
        return False
    return True


def h12_period(h):
    return "pm" if h >= 12 else "am"


def find_alarm_in_ui(xml, h, m):
    """(achou, ligado|None) procurando o horario na lista de alarmes do app Relogio (texto ou content-desc)."""
    i = xml.find("<") if xml else -1
    if i < 0:
        return False, None
    try:
        root = ET.fromstring(xml[i:])
    except ET.ParseError:
        return False, None
    rx = time_regex(h, m)
    parent = {c: p for p in root.iter() for c in p}
    hit_nodes = [n for n in root.iter("node") if rx.search(n.attrib.get("text", "")) or rx.search(n.attrib.get("content-desc", ""))]
    if not hit_nodes:
        return False, None
    for n in hit_nodes:
        cur = n
        for _ in range(4):
            cur = parent.get(cur)
            if cur is None:
                break
            for c in cur.iter("node"):
                if c.attrib.get("checkable") == "true" or "Switch" in c.attrib.get("class", ""):
                    return True, c.attrib.get("checked") == "true"
    return True, None


def timer_visible(xml):
    """Algum contador regressivo visivel (ex. 09:58 / 1:00:00) no app Relogio?"""
    return bool(re.search(r'text="\d{1,2}:\d{2}(?::\d{2})?"', xml or ""))


# ====================================================================== 2) DIAGNOSTICO DE ERROS
ANDROID_TOOLS = {"am", "pm", "cmd", "dumpsys", "settings", "svc", "input", "wm", "service", "monkey", "screencap", "uiautomator", "getprop",
                 "setprop", "appops", "content", "media", "logcat", "ime", "locksettings", "device_config"}
PY_PKGS = {"PIL": "pkg install python-pillow", "numpy": "pkg install python-numpy", "cv2": "pkg install opencv-python",
           "yaml": "pip install pyyaml", "bs4": "pip install beautifulsoup4", "sklearn": "pip install scikit-learn",
           "scipy": "pkg install python-scipy", "pandas": "pkg install python-pandas (or pip install pandas)", "lxml": "pkg install python-lxml",
           "Crypto": "pip install pycryptodome", "dotenv": "pip install python-dotenv", "serial": "pip install pyserial"}

TERMUX_ROOT_EQUIV = {
    "termux-volume": "root: `cmd media_session volume --stream 3 --set N` (or the device action)",
    "termux-brightness": "root: `settings put system screen_brightness N` (0-255) (or the device action)",
    "termux-wifi-enable": "root: `svc wifi enable|disable` (or the device action)",
    "termux-wifi-connectioninfo": "root: `dumpsys wifi | grep -E 'SSID|mWifiInfo' | head -3`",
    "termux-wifi-scaninfo": "root: `dumpsys wifi | grep -i scan | head`",
    "termux-battery-status": "root: `dumpsys battery`",
    "termux-torch": "no clean root equivalent; open the Quick Settings flashlight tile through the screen",
    "termux-vibrate": "root: `cmd vibrator_manager synced oneshot 500 255` (Android 13+) or skip it",
    "termux-notification": "root: `cmd notification post -S bigtext -t 'Title' tag 'text'`",
    "termux-open-url": "the open_url action (or `am start -a android.intent.action.VIEW -d URL`)",
    "termux-open": "root: `am start -a android.intent.action.VIEW -d URI`",
    "termux-location": "root: `dumpsys location | grep -i -m3 'last location'`",
    "termux-telephony-call": "root: `am start -a android.intent.action.DIAL -d tel:NUMBER` (opens the dialer; the user presses call)",
    "termux-sms-send": "root: `am start -a android.intent.action.SENDTO -d sms:NUMBER --es sms_body 'text'` then tap Send on screen",
    "termux-camera-photo": "root: `am start -a android.media.action.IMAGE_CAPTURE` then tap the shutter on screen",
    "termux-job-scheduler": "NOT an alarm. For alarms use set_alarm; for delayed shell work use `sleep N && cmd &` or `at`",
}
TERMUX_API_OK = {"termux-setup-storage", "termux-wake-lock", "termux-wake-unlock", "termux-change-repo", "termux-reload-settings",
                 "termux-info", "termux-fix-shebang", "termux-reset", "termux-notification", "termux-share"}
# (regex, codigo, conselho). A primeira que casar vem primeiro; no maximo 2 conselhos por resultado.
DIAG_RULES = [
    (r"unable to resolve intent|activity not started|error type 3|activitynotfound|no activity found|bad component name|(?:activity|component|package|class|intent)[^\n]{0,50}does not exist",
     "intent_unresolved", "That activity/intent does not exist on this phone (wrong action, package or component). Do NOT retry it: find the real one: "
     "`cmd package resolve-activity --brief PKG` or `pm dump PKG | grep -i -A3 'filter'`, `pm list packages | grep -i NAME`; or use the screen."),
    (r"securityexception|permission denial|requires android\.permission|not allowed to (start|send)",
     "permission_denied_android", "Android refused for lack of permission. Run it with \"root\":true (root bypasses it), or grant it: `pm grant PKG PERMISSION`."),
    (r"permission denied|operation not permitted|eacces|read-only file system",
     "permission_denied", "Not allowed here. For /data, /sdcard/Android/*, system paths or Android tools use \"root\":true; for ~/storage run termux-setup-storage once. "
     "Do not chmod the world: change the path or run as root."),
    (r"no such file or directory|cannot open|cannot access|not a directory|enoent",
     "path_missing", "The path does not exist. `ls -la` its PARENT to see the real name (case matters; ~/storage/downloads needs a trailing slash; "
     "root sees /sdcard/Download). Use find_path before guessing again."),
    (r"unable to locate package|e: package .* has no installation candidate|no matching distribution|could not find a version|no such package",
     "pkg_missing", "Package name is wrong or the repo index is stale. `pkg update` once, then `pkg search NAME`; Python libs: `pip download` name may differ "
     "(PIL=pillow, cv2=opencv-python, yaml=pyyaml). Never retry the same name."),
    (r"modulenotfounderror: no module named '([^']+)'|importerror: no module named ([\w.]+)",
     "py_module", "Python module missing: install the right package (see hint) then re-run only the failing script."),
    (r"syntaxerror|indentationerror|nameerror|typeerror|attributeerror|keyerror|valueerror|traceback \(most recent call last\)",
     "script_error", "The script itself is broken. Read the LAST 3 lines of the traceback (file:line + message), open that line, fix THAT, re-run. "
     "Do not rewrite the whole file."),
    (r"could not resolve host|temporary failure in name resolution|network is unreachable|connection (refused|timed out|reset)|\bssl\b|certificate|"
     r"failed to connect|operation timed out",
     "network", "Network problem, not a command problem. Check `ping -c1 1.1.1.1`, VPN/Wi-Fi state (root: `dumpsys connectivity | head`). Retry ONCE after "
     "fixing connectivity; try another mirror/URL if only this host fails."),
    (r"no space left on device|disk quota|enospc",
     "disk_full", "Disk is full: `df -h ~ /sdcard | head`, find what is big with `du -sh * | sort -h | tail`, and only clean files YOU created ($PA_TMP)."),
    (r"\bkilled\b|out of memory|cannot allocate memory|\boom\b",
     "oom", "Process killed (memory). Lower parallelism (-j1), process in chunks, or kill nothing else; do not retry the identical command."),
    (r"waiting for.*lock|could not get lock|dpkg: error|dpkg was interrupted",
     "dpkg_lock", "Another package process holds the lock or dpkg was interrupted: wait, then `dpkg --configure -a`; do not start a second installer."),
    (r"uiautomator.*(error|exception)|null root node|could not get ui hierarchy",
     "ui_dump", "UI dump failed (animation/secure screen). Wait 2s and retry once; if the app blocks dumps use the screenshot with tap_cell."),
    (r"inject_events|injecting to another application requires|input.*not found",
     "input_blocked", "Input injection blocked: run it as root (\"root\":true) and make sure the target window is in front."),
]
_DIAG = [(re.compile(rx, re.I | re.S), code, adv) for rx, code, adv in DIAG_RULES]


def split_exit(res):
    m = re.search(r"\[exit (-?\d+)\]", str(res))
    return int(m.group(1)) if m else None


RC1_OK = {"grep", "egrep", "fgrep", "rg", "diff", "cmp", "test", "[", "pgrep", "which", "command", "type", "cmp"}
BAN_CODES = {"intent_unresolved", "termux_api_missing", "termux_api_hang", "pkg_missing", "cmd_not_found", "android_tool_no_root"}


def benign_failure(cmd, res):
    """grep/diff/test saem com 1 quando 'nao achou': isso e uma resposta, nao um erro."""
    if split_exit(res) != 1:
        return False
    m = re.search(r"(?:^|[;&|]\s*|&&\s*)((?:\w|[-./\[])+)", (cmd or "").strip())
    last = (re.split(r"[|;&]+", (cmd or "").strip()) or [""])[-1].strip().split()
    w1 = os.path.basename(m.group(1)) if m else ""
    w2 = os.path.basename(last[0]) if last else ""
    body = re.sub(r"^\[cwd [^\]]*\] \[exit 1\]\n?", "", str(res)).strip()
    return (w1 in RC1_OK or w2 in RC1_OK) and len(body) < 400 and "no such file" not in body.lower()


def result_failed(res):
    r = str(res)
    rc = split_exit(r)
    if rc is not None:
        return rc != 0
    low = r.lower().lstrip()
    return low.startswith("error") or "[timeout" in r


def diagnose(cmd, res, root=False):
    """-> lista de (codigo, conselho) para um resultado com falha. cmd = comando shell (ou '' para acoes)."""
    r = str(res)
    low = r.lower()
    cmd = cmd or ""
    out = []
    rc = split_exit(r)
    first = re.search(r"(?:^|[;&|(]\s*|&&\s*)((?:\w|[-./])+)", cmd.strip())
    word = os.path.basename(first.group(1)) if first else ""
    # comando nao encontrado
    m = re.search(r"(?:^|\n)(?:sh: \d+: |/system/bin/sh: |bash: |sh: )?([\w./+-]+): (?:inaccessible or )?not found|command not found:? ?([\w./+-]*)", r)
    if rc == 127 or m:
        name = os.path.basename((m.group(1) or m.group(2) or word) if m else word) or word
        if name.startswith("termux-"):
            out.append(("termux_api_missing", f"`{name}` not found: the Termux:API package/app is not installed (pkg install termux-api + the Termux:API app). "
                        f"Do not depend on it. Root equivalent: {TERMUX_ROOT_EQUIV.get(name, 'use root:true with am/cmd/settings/dumpsys/input')}."))
        elif name in ANDROID_TOOLS and not root:
            out.append(("android_tool_no_root", f"`{name}` is an ANDROID tool: it is only in PATH with \"root\":true. Repeat the same command with root:true."))
        else:
            out.append(("cmd_not_found", f"`{name}` is not installed. `pkg search {name}` / `pkg install <pkg>`; or `command -v {name}` to see if it is another name. "
                        "Do not guess flags of a tool you have not confirmed exists."))
    elif rc == 126:
        out.append(("not_executable", "Found but not executable: `chmod +x FILE` or run it through its interpreter (`python FILE`, `sh FILE`). A file in ~/storage cannot be executed: copy it to $HOME first."))
    elif rc == 124 or "[timeout" in r:
        if "termux-" in cmd:
            out.append(("termux_api_hang", "A termux-* command HUNG: the Termux:API app is missing, not allowed to run in background, or battery-optimised. "
                        "Stop using termux-* for this; use the root equivalent (am/cmd/settings/dumpsys) or a dedicated action (set_alarm/set_timer/device)."))
        else:
            out.append(("timeout", "The command hung or was too slow. Do not just repeat it: run it in the background with a log (`cmd > $PA_TMP/o.log 2>&1 &`) "
                        "and poll, reduce its scope, or add a smaller timeout/flag. Interactive programs hang too (stdin is closed)."))
    for rx, code, adv in _DIAG:
        mm = rx.search(r)
        if not mm:
            continue
        if code == "py_module":
            mod = (mm.group(1) or mm.group(2) or "").split(".")[0]
            adv = adv + f" Hint: `{PY_PKGS.get(mod, 'pip install ' + mod.lower().replace('_', '-'))}`."
        if code == "script_error" and "traceback" in low:
            tail = [l for l in r.strip().splitlines() if l.strip()][-1:]
            adv += f" Last line: {tail[0][:140]}" if tail else ""
        if all(c != code for c, _ in out):
            out.append((code, adv))
        if len(out) >= 2:
            break
    if not out and rc not in (None, 0):
        tail = [l for l in r.strip().splitlines() if l.strip() and not l.startswith("[cwd")][-2:]
        out.append(("exit_nonzero", f"Exit {rc} with no known pattern. Read the LAST lines of the output ({' | '.join(t[:90] for t in tail) or 'empty'}) before changing "
                    "anything; if empty, rerun with `-v`/`set -x` or `2>&1`. Change ONE thing at a time."))
    return out[:2]


UI_ERR_RE = re.compile(r"\b(erro|error|falha|failed|falhou|n[aã]o foi poss[ií]vel|couldn.?t|unable to|tente novamente|try again|inv[aá]lid[oa]|invalid|"
                       r"obrigat[oó]ri[oa]|required|n[aã]o est[aá] respondendo|isn.?t responding|keeps stopping|sem conex[aã]o|no connection|"
                       r"permiss[aã]o negada|permission denied)\b", re.I)
CLOCK_PKG_RE = re.compile(r"deskclock|clockpackage|alarmclock|\.clock\b", re.I)
PICKER_RE = re.compile(r"selecionar hor[aá]rio|set time|select time|definir hor[aá]rio|definir alarme|enter time", re.I)


def screen_findings(els, pkg=""):
    """Achados calculados pelo CODIGO sobre a tela atual: erro visivel, campo obrigatorio vazio, dialogo travado, ANR."""
    out = []
    if not els:
        return out
    errs = [e["text"] or e["desc"] for e in els if (e["text"] or e["desc"]) and UI_ERR_RE.search(e["text"] or e["desc"]) and len(e["text"] or e["desc"]) < 140]
    if errs:
        out.append("visible error/warning text: " + " | ".join(dict.fromkeys(x.strip() for x in errs[:3])))
    if any(re.search(r"(n[aã]o est[aá] respondendo|isn.?t responding|keeps stopping|parou de funcionar|has stopped)", e["text"], re.I) for e in els):
        out.append("an app crashed / is not responding: tap 'Fechar app'/'Close app' or 'Aguardar'/'Wait' (whichever is there), then reopen it")
    editable = [e for e in els if "editable" in e["line"]]
    empties = [e for e in editable if not e["text"]]
    picker = any(PICKER_RE.search(e["text"] or e["desc"]) for e in els)
    if picker:
        out.append("a TIME PICKER dialog is open (Hora/Minuto). Use time_picker_set {hour,minute}: it fills both fields with 2 digits, verifies and taps OK. "
                   "Never press OK with an empty field" + (f" (EMPTY now: {len(empties)} field(s))" if empties else ""))
    elif empties and any(re.search(r"^(ok|salvar|save|confirmar|continuar|continue|enviar|submit)$", (e["text"] or e["desc"]).strip(), re.I) for e in els):
        out.append(f"{len(empties)} text field(s) on this screen are EMPTY and a confirm button exists: fill every required field before pressing it")
    return out


def stuck_ladder(unchanged, pkg=""):
    """Escada de estrategias quando a tela nao muda: cada degrau e DIFERENTE do anterior."""
    if unchanged < 3:
        return ""
    steps = ["1) pick a DIFFERENT element (tap_text / tap_cell / another index) - not the same one again",
             "2) ask the system what is really on screen: shell root:true `dumpsys activity top | head -30` and `dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'`",
             "3) skip the UI: do the same thing through an intent/command (am start -a ..., settings put ..., cmd ...) or a dedicated action (set_alarm, set_timer, device)",
             "4) press back once to close a stuck dialog/keyboard, then re-enter the flow from its beginning",
             "5) if the sub-step is optional, skip it and say so; otherwise call fail with the exact blocker"]
    k = min(len(steps), max(1, unchanged - 2))
    return "STUCK LADDER (screen unchanged x%d). Do step %d now, then the next ones only if it fails:\n" % (unchanged, k) + "\n".join(steps[:k][-2:])


# ====================================================================== 3) PLAYBOOKS (conhecimento fixo por dominio)
DOMAINS = [("alarm", r"\balarm|despertador|\bacorde\b|\bacordar\b|\bdesperte\b|wake me"), ("timer", r"timer|temporizador|contagem regress|countdown|cronometro"),
           ("clock", r"relogio|\bclock\b"), ("volume", r"\bvolume\b|\bsom\b"), ("brightness", r"brilho|brightness"),
           ("wifi", r"wi-?fi"), ("bluetooth", r"bluetooth"), ("airplane", r"aviao|airplane"), ("dnd", r"perturbe|incomode|do not disturb"),
           ("data", r"dados moveis|mobile data"), ("rotation", r"rotacao|auto-?rotate")]
CLOCK_PLAYBOOK = (
    "CLOCK / ALARM / TIMER PLAYBOOK (learned the hard way on this phone):\n"
    "- Alarms and timers are created with set_alarm / set_timer (real Clock-app alarm via Android intent, works with the phone locked, verified by the code). "
    "NEVER use Termux:API, sleep, cron, termux-job-scheduler or notifications as an \"alarm\"; they do not ring like one. If the user says \"in the app\", "
    "still use set_alarm with \"show\":true (the app opens on the new alarm) instead of tapping through the Clock UI.\n"
    "- List/open alarms: set_alarm is not needed: shell root:true `am start -a android.intent.action.SHOW_ALARMS`.\n"
    "- Turn an existing alarm on/off: tap its switch (state \"checked\" = on). To delete: open it, tap the bin/Delete.\n"
    "- If you ARE inside the Set-time dialog (fields Hora/Minuto, buttons Cancelar/OK): call time_picker_set {hour,minute}. Both fields need 2 digits; an empty "
    "Minute field blocks OK. The clock icon at the bottom-left switches keyboard/dial mode. Landscape/keyboard may hide OK: hide_keyboard first.\n"
    "- Hours: 24h unless the user says da tarde/noite/pm. After creating, state the time you used.")
DEVICE_PLAYBOOK = (
    "DEVICE SETTINGS PLAYBOOK: use the device action (verified) or root commands; NOT Termux:API (often missing/slow). wifi: `svc wifi enable|disable`; "
    "bluetooth: `svc bluetooth enable|disable`; mobile data: `svc data enable|disable`; airplane: `cmd connectivity airplane-mode enable|disable`; "
    "DND: `cmd notification set_dnd on|off`; brightness: `settings put system screen_brightness N` (0-255, after `screen_brightness_mode 0`); "
    "volume: `cmd media_session volume --stream 3 --set N` (3=media 2=ring 4=alarm 5=notif). Verify with `settings get ...` before saying done.")
GENERAL_RULES = (
    "WORKING RULES (code-enforced): (1) every failed result carries a [DIAGNOSIS]: obey it before trying anything else; (2) an approach that failed twice is "
    "listed under DEAD ENDS and blocked: pick a DIFFERENT method, not a variant; (3) prefer Android/root tools (am, cmd, settings, dumpsys, pm, input) over "
    "Termux:API; (4) once a dedicated action exists (set_alarm, set_timer, device, open_url, download, zip_items) use it instead of simulating it with taps.")


def domain_of(task, intent=None):
    if intent:
        k = intent.kind if hasattr(intent, "kind") else intent.get("kind")
        if k in ("alarm", "show_alarms"):
            return "alarm"
        if k in ("timer", "show_timers"):
            return "timer"
        if k == "toggle":
            return intent["setting"]
        if k in ("volume", "brightness"):
            return k
    f = fold(task or "")
    for name, rx in DOMAINS:
        if re.search(rx, f):
            return name
    return "generic"


def playbook_for(domain, pkg=""):
    out = []
    if domain in ("alarm", "timer", "clock") or CLOCK_PKG_RE.search(pkg or ""):
        out.append(CLOCK_PLAYBOOK)
    if domain in ("volume", "brightness", "wifi", "bluetooth", "airplane", "dnd", "data", "rotation"):
        out.append(DEVICE_PLAYBOOK)
    return "\n".join(out)


# ====================================================================== 4) LICOES PERSISTENTES
STOP = set("""a o os as um uma uns umas de do da dos das e em no na nos nas para por com sem que se ao aos entre sobre the and for with from into that this
then also use using app apps baixe baixar abra abrir faca fazer tarefa task quero want please favor tambem ate ver veja mande envie me meu minha
voce voces eu ele ela isso esse essa este esta aqui ali la""".split())


def tokens(text):
    out = []
    for t in re.findall(r"[a-z0-9]{3,}", fold(text)):
        if t not in STOP and t not in out:
            out.append(t)
    return out[:14]


def _jacc(a, b):
    a, b = set(a), set(b)
    return len(a & b) / max(1, len(a | b))


class LessonStore:
    """JSON simples em ~/.phoneagent_lessons.json. Cada licao: {id, tags, domain, text, hits, misses, created, last}."""
    MAX = 150

    def __init__(self, path=None):
        self.path = path or os.path.join(os.path.expanduser("~"), ".phoneagent_lessons.json")
        self.items = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.items = [x for x in d.get("lessons", []) if isinstance(x, dict) and x.get("text")]
        except (OSError, ValueError):
            self.items = []

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "lessons": self.items}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError as e:
            _log(f"    (nao consegui salvar licoes: {e})")

    def add(self, text, tags=None, domain="generic", source="auto"):
        """Retorna a licao (nova ou a existente reforcada). Duplicatas (>=70% de palavras iguais) apenas reforcam."""
        text = re.sub(r"\s+", " ", str(text or "")).strip()[:260]
        if len(text) < 12:
            return None
        tt = tokens(text)
        for it in self.items:
            if _jacc(tokens(it["text"]), tt) >= 0.7:
                it["hits"] = it.get("hits", 0) + 1
                it["last"] = int(time.time())
                for t in tags or []:
                    if t not in it["tags"]:
                        it["tags"].append(t)
                it["tags"] = it["tags"][:16]
                self.save()
                return it
        nid = max([x.get("id", 0) for x in self.items] + [0]) + 1
        it = {"id": nid, "tags": list(dict.fromkeys((tags or []) + tt))[:16], "domain": domain, "text": text, "hits": 0, "misses": 0,
              "source": source, "created": int(time.time()), "last": int(time.time())}
        self.items.append(it)
        if len(self.items) > self.MAX:  # tira as piores (mais erros, menos usos, mais antigas)
            self.items.sort(key=lambda x: (x.get("hits", 0) - 2 * x.get("misses", 0), x.get("last", 0)))
            self.items = self.items[len(self.items) - self.MAX:]
        self.save()
        return it

    def match(self, task, domain="generic", k=4):
        tk = set(tokens(task))
        scored = []
        for it in self.items:
            ov = len(tk & set(it.get("tags", [])))
            sc = ov + (3 if domain != "generic" and it.get("domain") == domain else 0) + min(it.get("hits", 0), 3) * 0.2 - it.get("misses", 0) * 0.5
            if (ov >= 2 or (domain != "generic" and it.get("domain") == domain)) and sc > 0:
                scored.append((sc, it.get("last", 0), it))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [x[2] for x in scored[:k]]

    def mark(self, ids, ok):
        for it in self.items:
            if it.get("id") in ids:
                if ok:
                    it["hits"] = it.get("hits", 0) + 1
                else:
                    it["misses"] = it.get("misses", 0) + 1
                it["last"] = int(time.time())
        self.items = [x for x in self.items if not (x.get("misses", 0) >= 3 and x.get("hits", 0) == 0)]
        self.save()

    def forget(self, ident):
        n = len(self.items)
        if str(ident).lower() == "all":
            self.items = []
        else:
            self.items = [x for x in self.items if str(x.get("id")) != str(ident)]
        self.save()
        return n - len(self.items)

    def block(self, task, domain="generic"):
        ms = self.match(task, domain)
        if not ms:
            return "", []
        return ("LESSONS LEARNED ON THIS PHONE (from past runs: apply them, do not rediscover):\n" + "\n".join("- " + x["text"] for x in ms),
                [x["id"] for x in ms])


REFLECT_PROMPT = ("You are the memory of an Android phone agent. Extract at most 3 REUSABLE lessons from this run so the next run does not repeat the mistakes.\n"
                  "TASK: {task}\nOUTCOME: {outcome}\nFAILED ATTEMPTS (approach -> diagnosed cause):\n{fails}\nWHAT WORKED / LAST ACTIONS:\n{events}\n"
                  "Rules: each lesson is ONE imperative sentence (max 200 chars), concrete and general enough for similar tasks: "
                  "\"When X, do Y (command/action); do not Z (it fails because ...)\". Mention real commands/actions. No story, no task-specific values "
                  "(times, names, paths) unless they are the point. If nothing is worth keeping, return an empty list. "
                  'Reply JSON {{"lessons":[{{"tags":["3-6 lowercase keywords in the task language and English"],"lesson":"..."}}]}}')


# ====================================================================== 5) MIXIN DO AGENTE
class BrainMixin:
    """Metodos que o Agent herda. Usa self.dev (root), self.act, self.finish_box, self.post_chat, self.tm, self.facts, self.advice..."""

    def brain_init(self):
        self.lessons = LessonStore()
        self.fast_enabled = True
        self.reflect_enabled = not os.environ.get("PA_NO_REFLECT")
        self.api_dead = 0
        self.brain_reset("")

    def brain_reset(self, task):
        self.fam_fail, self.dead_ends, self.banned = {}, [], set()
        self.fail_log, self.succ_log, self.new_lessons = [], [], []
        self.hard = 0
        self.intent = parse_intent(task) if task else None
        self.domain = domain_of(task, self.intent)
        self.intent_tried = False
        self.rescue_n = 0
        self.lesson_text, self.used_ids = self.lessons.block(task, self.domain) if task else ("", [])

    # ---------------------------------------------------------------- 5a) atalhos de intencao
    def _sh(self, cmd, timeout=15):
        return self.dev.sh(cmd, timeout=timeout) or ""

    def fast_path(self, task):
        """True/False = tarefa resolvida/falhou de vez pelo atalho; None = segue o fluxo normal (o atalho nao resolveu ou nao se aplica)."""
        if not self.fast_enabled or not self.intent:
            return None
        it = self.intent
        self.intent_tried = True
        _log(f"  ⚡ atalho: {it.summary()}  (sem modelo, sem Termux:API)")
        try:
            ok, msg = self.run_intent(it)
        except Exception as e:
            ok, msg = False, f"erro no atalho: {e}"
        if ok:
            if it.get("note"):
                msg += "\n(" + it["note"] + ")"
            self.final_msg = msg
            self.plan = [{"goal": it.summary(), "done": True}]
            self.finish_box(True, 1, msg)
            return True
        self.facts.append(f"fast intent '{it.summary()}' did NOT work: {msg[:200]} (step 0)")
        self.advice = ("The direct Android-intent shortcut failed (" + msg[:140] + "). Check the current state first (list alarms/timers or `settings get ...`) "
                       "before creating anything again, to avoid duplicates; then use the set_alarm/set_timer/device action or the screen.")
        self.hard += 1
        _log(f"  ! atalho não confirmou ({msg[:120]}); sigo com o agente")
        return None

    def run_intent(self, it):
        k = it.kind
        if k == "alarm":
            return self.do_alarm(it["hour"], it["minute"], it.get("label") or "", it.get("days"), bool(it.get("show")))
        if k == "timer":
            return self.do_timer(it["seconds"], it.get("label") or "", bool(it.get("show")))
        if k in ("show_alarms", "show_timers"):
            act = "SHOW_ALARMS" if k == "show_alarms" else "SHOW_TIMERS"
            out = self._sh(f"am start -a android.intent.action.{act}" + self._pkg_arg() + " 2>&1")
            self.left_term = True
            return (not am_failed(out)), ("Abri a lista de " + ("alarmes" if k == "show_alarms" else "timers") + " no app Relógio." if not am_failed(out) else out[:200])
        if k == "music":
            return self.do_music(it.get("title"), it.get("artist"), it.get("action", "play"))
        if k == "music_control":
            return self.do_music(action=it.get("action", "play"))
        if k == "volume":
            return self.do_volume(it.get("stream", "media"), it["value"])
        if k == "brightness":
            return self.do_brightness(it["value"])
        if k == "toggle":
            return self.do_toggle(it["setting"], bool(it["on"]))
        if k == "open_app":
            return self.do_open_app(it["app"])
        return False, "intenção desconhecida"

    def _pkg_arg(self):
        p = clock_pkg(getattr(self, "pkgs", None) or set())
        return f" -p {p}" if p else ""

    def do_music(self, title=None, artist=None, action="play"):
        """Uses media controls with state checks, or opens an official search for visual selection."""
        app = choose_music_app(getattr(self, "pkgs", None) or set())
        if action in ("pause", "resume", "next", "previous"):
            if not app:
                return False, "nenhum aplicativo de música instalado foi encontrado"
            key = {"pause": "PAUSE", "resume": "PLAY", "next": "NEXT", "previous": "PREVIOUS"}[action]
            before = self._music_session(app)
            if before is None:
                return False, f"não encontrei uma sessão de mídia verificável para {app}"
            self._sh(f"input keyevent KEYCODE_MEDIA_{key}")
            after = self._music_session(app)
            if after is None:
                return False, f"enviei {action}, mas não consegui verificar a sessão de mídia"
            if action == "pause" and after[0] == 2:
                return True, f"reprodução pausada em {app} (estado confirmado)."
            if action == "resume" and after[0] == 3:
                return True, f"música reproduzindo em {app} (estado confirmado)."
            if action in ("next", "previous") and before[1] and after[1] and before[1] != after[1]:
                return True, f"faixa alterada em {app}: {after[1]} (metadado confirmado)."
            return False, f"enviei {action}, mas o estado/metadado da sessão não confirmou a mudança"
        if not title:
            return False, "titulo da música não identificado"
        if not app:
            return False, "nenhum aplicativo de música compatível está instalado"
        query = " ".join(x for x in (title, artist) if x)
        if app == "com.google.android.apps.youtube.music":
            fast_cmd = ("am start -a android.media.action.MEDIA_PLAY_FROM_SEARCH"
                        f" -p {app} --es android.intent.extra.focus vnd.android.cursor.item/audio"
                        f" --es query {shlex.quote(query)} --es android.intent.extra.title {shlex.quote(title)}")
            if artist:
                fast_cmd += f" --es android.intent.extra.artist {shlex.quote(artist)}"
            fast_out = self._sh(fast_cmd + " 2>&1")
            if not am_failed(fast_out):
                for attempt in range(3):
                    session = self._music_session(app)
                    if session and session[0] == 3 and self._music_matches(session[1], session[2], title, artist):
                        self.left_term = True
                        return True, f"Iniciou {title}{(' — ' + artist) if artist else ''} no YouTube Music (reprodução e metadados confirmados)."
                    if attempt < 2:
                        time.sleep(0.35)
        if app == "com.spotify.music":
            url = "https://open.spotify.com/search/" + urllib.parse.quote(query)
        elif app == "com.google.android.apps.youtube.music":
            url = "https://music.youtube.com/search?q=" + urllib.parse.quote(query)
        elif app == "com.amazon.mp3":
            url = "https://music.amazon.com/search/" + urllib.parse.quote(query)
        elif "deezer" in app.lower():
            url = "https://www.deezer.com/search/" + urllib.parse.quote(query)
        elif "apple" in app.lower():
            url = "https://music.apple.com/us/search?term=" + urllib.parse.quote(query)
        else:
            return False, f"não há uma busca oficial configurada para {app}"
        cmd = f"am start -a android.intent.action.VIEW -d {shlex.quote(url)}"
        cmd += f" -p {app}"
        out = self._sh(cmd + " 2>&1")
        if am_failed(out):
            return False, "a app de música não aceitou a intenção: " + out[:180]
        self.left_term = True
        return False, (f"Pesquisa oficial aberta em {app} para {title}{(' — ' + artist) if artist else ''}. "
                       "Selecione apenas o resultado que corresponde ao título e artista; confirme a reprodução pela tela antes de concluir.")

    def _music_session(self, app):
        """Returns (PlaybackState, title) only when dumpsys identifies this app's session."""
        out = self._sh("dumpsys media_session 2>&1", timeout=8)
        lines = out.splitlines()
        app_line = next((i for i, line in enumerate(lines) if app.lower() in line.lower()), None)
        if app_line is None:
            return None
        marker = re.compile(r"^\s*(?:\*|Session\s+\d+\b)")
        starts = [i for i, line in enumerate(lines[:app_line + 1]) if marker.search(line)]
        start = starts[-1] if starts else app_line
        end = next((i for i in range(start + 1, len(lines)) if marker.search(lines[i])), len(lines))
        section = "\n".join(lines[start:end])
        if app.lower() not in section.lower():
            return None
        state = re.search(r"\bstate\s*=\s*(\d+)\b", section, re.I)
        if not state:
            return None
        title = re.search(r"(?:android\.media\.metadata\.title|\btitle)\s*[=:]\s*([^\r\n}]+)", section, re.I)
        artist = re.search(r"(?:android\.media\.metadata\.artist|\bartist)\s*[=:]\s*([^\r\n}]+)", section, re.I)
        return (int(state.group(1)), title.group(1).strip() if title else "",
            artist.group(1).strip() if artist else "")

    @staticmethod
    def _music_matches(actual_title, actual_artist, title, artist):
        normalize = lambda value: re.sub(r"[^a-z0-9]", "", fold(value or ""))
        expected_title, got_title = normalize(title), normalize(actual_title)
        expected_artist, got_artist = normalize(artist), normalize(actual_artist)
        return bool(expected_title and got_title == expected_title and (not expected_artist or expected_artist in got_artist))

    # ---- alarme
    def do_alarm(self, hour, minute, label="", days=None, show=False):
        hour, minute = int(hour), int(minute)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return False, f"horário inválido {hour}:{minute}"
        pkg = clock_pkg(getattr(self, "pkgs", None) or set())
        before = self._sh("settings get system next_alarm_formatted 2>&1").strip()
        out = self._sh(alarm_cmd(hour, minute, label, days, show, pkg))
        if am_failed(out) and pkg:  # pacote errado/sem a intent: tenta sem -p
            out = self._sh(alarm_cmd(hour, minute, label, days, show, None))
        if am_failed(out):
            return False, "o Android recusou a intent de alarme: " + " ".join(out.split())[:160]
        time.sleep(1.4)
        when = f"{hour:02d}:{minute:02d}"
        if days:
            when += " (" + ("todos os dias" if len(days) == 7 else " ".join(DAY_NAMES_PT[d] for d in sorted(days))) + ")"
        what = f"Alarme criado para {when}" + (f" com o nome «{label}»" if label else "") + "."
        ver, how = self.verify_alarm(hour, minute, before, show)
        if ver is False:
            return False, f"enviei a intent, mas o alarme {hour:02d}:{minute:02d} não foi confirmado ativo no app Relógio" + (f": {how}" if how else ".")
        if ver is None:
            return False, f"intent aceita para {hour:02d}:{minute:02d}, mas não consegui confirmar que esse alarme foi configurado" + (f": {how}" if how else ".")
        if show:
            self.left_term = True
        return True, what + (f" {how}" if how else "")

    def verify_alarm(self, h, m, before, show):
        """-> (True|False|None, texto). None = nao deu para confirmar. Rola a lista do app Relogio ate achar (ela e longa)."""
        nxt = self._sh("settings get system next_alarm_formatted 2>&1").strip()
        if next_alarm_matches(before, h, m) and next_alarm_matches(nxt, h, m) and nxt == before:
            return None, f"o próximo alarme {nxt} já existia antes do pedido; não prova a criação de outro"
        if next_alarm_matches(nxt, h, m) and nxt != before:
            return True, f"Confirmado pelo sistema: próximo alarme «{nxt}»."
        self._sh("am start -a android.intent.action.SHOW_ALARMS" + self._pkg_arg() + " 2>&1")
        self.left_term = True
        time.sleep(1.6)
        W, H = getattr(self, "W", 1080) or 1080, getattr(self, "H", 2400) or 2400
        seen_pages, xml, in_clock = set(), "", False
        for _ in range(8):
            try:
                xml = self.dev.dump()
            except Exception:
                xml = ""
            if not xml or "<hierarchy" not in xml:
                break
            found, enabled = find_alarm_in_ui(xml, h, m)
            if found:
                if enabled is True:
                    return True, "Confirmado no app Relógio: aparece LIGADO."
                if enabled is False:
                    return False, "o horário aparece no app Relógio, mas está DESLIGADO"
                return None, "o horário aparece no app Relógio, mas não consegui verificar se está ligado"
            in_clock = in_clock or bool(re.search(r"deskclock|clockpackage|alarmclock|clock", xml, re.I))
            page = re.sub(r"\s+", "", xml)[:4000]
            if page in seen_pages:
                break  # chegou no fim da lista
            seen_pages.add(page)
            self._sh(f"input swipe {W // 2} {int(H * 0.72)} {W // 2} {int(H * 0.30)} 350")
            time.sleep(0.7)
        if in_clock and len(seen_pages) >= 1:
            return False, ""
        return None, ""

    # ---- timer
    def do_timer(self, seconds, label="", show=False):
        seconds = int(seconds)
        if not 1 <= seconds <= 86400:
            return False, "duração fora do limite do Android (1 s a 24 h)"
        pkg = clock_pkg(getattr(self, "pkgs", None) or set())
        out = self._sh(timer_cmd(seconds, label, show, pkg))
        if am_failed(out) and pkg:
            out = self._sh(timer_cmd(seconds, label, show, None))
        if am_failed(out):
            return False, "o Android recusou a intent de timer: " + " ".join(out.split())[:160]
        time.sleep(1.3)
        what = f"Timer de {fmt_duration(seconds)} iniciado" + (f" («{label}»)" if label else "") + "."
        self._sh("am start -a android.intent.action.SHOW_TIMERS" + self._pkg_arg() + " 2>&1")
        time.sleep(1.4)
        try:
            xml = self.dev.dump()
        except Exception:
            xml = ""
        seen = timer_visible(xml)
        self.left_term = True
        return True, what + (" Confirmado: contagem visível no app Relógio." if seen else " (enviado; não consegui confirmar na tela.)")

    # ---- volume / brilho / liga-desliga
    def do_volume(self, stream, value):
        sid = STREAMS.get(stream, 3)
        nm = {"media": "mídia", "ring": "toque", "alarm": "alarme", "notification": "notificações", "call": "chamada"}.get(stream, stream)
        if value in ("+", "-"):
            key = 24 if value == "+" else 25
            self._sh(f"for i in 1 2 3; do input keyevent {key}; done")
            return True, f"Volume de {nm} {'aumentado' if value == '+' else 'diminuído'} (3 toques de tecla)."
        if value == "mute":
            self._sh("input keyevent 164")
            return True, "Som silenciado (tecla mudo)."
        got = self._sh(f"cmd media_session volume --stream {sid} --get 2>&1")
        mm = re.search(r"volume is (\d+) in range \[(\d+)\.\.(\d+)\]", got)
        if not mm:
            return False, "não consegui ler o volume atual (cmd media_session): " + " ".join(got.split())[:100]
        lo, hi = int(mm.group(2)), int(mm.group(3))
        idx = hi if value == "max" else round(lo + (hi - lo) * int(value) / 100)
        out = self._sh(f"cmd media_session volume --stream {sid} --set {idx} 2>&1")
        after = self._sh(f"cmd media_session volume --stream {sid} --get 2>&1")
        m2 = re.search(r"volume is (\d+)", after)
        if m2 and int(m2.group(1)) == idx:
            return True, f"Volume de {nm} em {idx}/{hi} (confirmado)."
        return False, f"pedi volume {idx}/{hi} mas o sistema reporta {m2.group(1) if m2 else '?'}: " + " ".join(out.split())[:100]

    def do_brightness(self, value):
        if value == "auto":
            self._sh("settings put system screen_brightness_mode 1")
            ok = self._sh("settings get system screen_brightness_mode").strip() == "1"
            return ok, "Brilho automático ligado." if ok else "não consegui ligar o brilho automático"
        v = max(1, min(255, round(255 * int(value) / 100)))
        self._sh(f"settings put system screen_brightness_mode 0; settings put system screen_brightness {v}")
        got = self._sh("settings get system screen_brightness").strip()
        ok = got == str(v)
        return ok, (f"Brilho em {value}% ({v}/255, confirmado)." if ok else f"pedi brilho {v} mas o sistema reporta {got or '?'}")

    TOGGLE_CMDS = {
        "wifi": ("svc wifi {x}", "settings get global wifi_on", "wi-fi"),
        "bluetooth": ("svc bluetooth {x}", "settings get global bluetooth_on", "bluetooth"),
        "data": ("svc data {x}", "settings get global mobile_data", "dados móveis"),
        "airplane": ("cmd connectivity airplane-mode {x}", "settings get global airplane_mode_on", "modo avião"),
        "dnd": ("cmd notification set_dnd {d}", "settings get global zen_mode", "não perturbe"),
        "rotation": ("settings put system accelerometer_rotation {n}", "settings get system accelerometer_rotation", "rotação automática"),
    }

    def do_toggle(self, setting, on):
        spec = self.TOGGLE_CMDS.get(setting)
        if not spec:
            return False, f"configuração desconhecida: {setting}"
        cmd, probe, nm = spec
        self._sh(cmd.format(x="enable" if on else "disable", d="on" if on else "off", n=1 if on else 0) + " 2>&1")
        if setting == "airplane":
            time.sleep(1.0)
        want_on = lambda v: (v.strip() not in ("", "0", "null")) if setting == "dnd" else (v.strip() == "1")
        got = ""
        for _ in range(6):
            time.sleep(1.0)
            got = self._sh(probe + " 2>&1")
            if want_on(got) == on and got.strip() not in ("", "null"):
                return True, f"{nm.capitalize()} {'ligado' if on else 'desligado'} (confirmado)."
        if got.strip() in ("", "null"):
            return True, f"Comando de {nm} enviado; este Android não informa o estado, não consegui confirmar."
        return False, f"pedi {nm} {'ligado' if on else 'desligado'} mas o estado continua '{got.strip()}'"

    APP_ALIASES = {"relogio": list(CLOCK_PKGS), "clock": list(CLOCK_PKGS), "calculadora": ["com.google.android.calculator", "com.android.calculator2"],
                   "calendario": ["com.google.android.calendar"], "galeria": ["com.google.android.apps.photos", "com.sec.android.gallery3d"],
                   "fotos": ["com.google.android.apps.photos"], "contatos": ["com.google.android.contacts", "com.android.contacts"],
                   "telefone": ["com.google.android.dialer", "com.android.dialer"], "mensagens": ["com.google.android.apps.messaging"],
                   "ajustes": ["com.android.settings"], "configuracoes": ["com.android.settings"], "drive": ["com.google.android.apps.docs"],
                   "arquivos": ["com.google.android.apps.nbu.files", "com.android.documentsui"]}

    def do_open_app(self, app):
        key = fold(app).strip()
        pkg = None
        for c in self.APP_ALIASES.get(key, []):
            if c in (getattr(self, "pkgs", None) or set()):
                pkg = c
                break
        pkg = pkg or self.resolve_app(app)
        if not pkg:
            return False, f"não achei o app «{app}» instalado"
        r = self.act({"action": "open_app", "app": pkg})
        if str(r).startswith("error"):
            return False, str(r)[:160]
        if "ALREADY inside Termux" in str(r):
            return True, "Você já está no Termux."
        time.sleep(1.0)
        foc = self._sh("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -3")
        self.left_term = True
        if pkg in foc:
            return True, f"{app} aberto ({pkg}), confirmado em primeiro plano."
        return True, f"{app} aberto ({pkg}); não consegui confirmar o primeiro plano."

    # ---------------------------------------------------------------- 5b) acoes novas para o modelo
    def _days_arg(self, d):
        if not d:
            return None
        if isinstance(d, (str, int)):
            d = [d]
        out = []
        for x in d:
            s = fold(str(x)).strip()
            k = int(s) if s.isdigit() and 1 <= int(s) <= 7 else DAY_IDX.get(re.sub(r"s?(-feira)?$", "", s)) or DAY_IDX.get(s[:3])
            if k and k not in out:
                out.append(k)
        return sorted(out) or None

    def act_set_alarm(self, a):
        h, m = a.get("hour"), a.get("minute", 0)
        if h is None and a.get("time"):
            mt = re.match(r"^\s*(\d{1,2})[:h](\d{2})?", str(a["time"]))
            if mt:
                h, m = int(mt.group(1)), int(mt.group(2) or 0)
        try:
            h, m = int(h), int(m or 0)
        except (TypeError, ValueError):
            return 'error: set_alarm precisa de "hour" (0-23) e "minute" (0-59), ou "time":"HH:MM"'
        ok, msg = self.do_alarm(h, m, str(a.get("label") or ""), self._days_arg(a.get("days")), bool(a.get("show")))
        self.act_kind = "set_alarm_ui" if a.get("show") else "set_alarm"
        return ("ok: " if ok else "error: ") + msg

    def act_set_timer(self, a):
        try:
            secs = int(float(a.get("seconds") or 0) + 60 * float(a.get("minutes") or 0) + 3600 * float(a.get("hours") or 0))
        except (TypeError, ValueError):
            return 'error: set_timer precisa de "minutes" ou "seconds"'
        ok, msg = self.do_timer(secs, str(a.get("label") or ""), bool(a.get("show")))
        self.act_kind = "set_alarm_ui" if a.get("show") else "set_alarm"
        return ("ok: " if ok else "error: ") + msg

    def act_device(self, a):
        s = fold(str(a.get("setting") or a.get("name") or "")).strip()
        val = fold(str(a.get("value", ""))).strip()
        alias = {"wi-fi": "wifi", "dados": "data", "mobile_data": "data", "aviao": "airplane", "airplane_mode": "airplane",
                 "naoperturbe": "dnd", "do_not_disturb": "dnd", "rotacao": "rotation", "brilho": "brightness"}
        s = alias.get(s, s)
        self.act_kind = "set_alarm"
        if s in self.TOGGLE_CMDS:
            if val in ("on", "true", "1", "ligar", "ligado", "enable", "ativar"):
                ok, msg = self.do_toggle(s, True)
            elif val in ("off", "false", "0", "desligar", "desligado", "disable", "desativar"):
                ok, msg = self.do_toggle(s, False)
            else:
                return 'error: device precisa de "value":"on" ou "off" para ' + s
        elif s == "brightness":
            ok, msg = self.do_brightness("auto" if val == "auto" else int(float(val or 50)))
        elif s == "volume":
            stream = fold(str(a.get("stream") or "media"))
            stream = STREAM_PT.get(stream, stream)
            v = val if val in ("max", "mute", "+", "-") else int(float(val or 50))
            ok, msg = self.do_volume(stream if stream in STREAMS else "media", v)
        else:
            return "error: setting desconhecido (wifi|bluetooth|data|airplane|dnd|rotation|brightness|volume)"
        return ("ok: " if ok else "error: ") + msg

    # ---- seletor de horario (dialogo Material "Selecionar horario")
    def act_time_picker(self, a, parse_ui, ET_=None):
        try:
            h, m = int(a.get("hour")), int(a.get("minute", 0))
        except (TypeError, ValueError):
            return 'error: time_picker_set precisa de "hour" e "minute"'
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return "error: horário inválido"
        sh = self.dev.sh

        def read():
            pkg, W, H, els = parse_ui(self.dev.dump())
            return els

        els = read()
        fields = lambda es: sorted([e for e in es if "editable" in e["line"]], key=lambda e: (e["cy"] // 40, e["cx"]))
        ed = fields(els)
        if len(ed) < 2:  # modo ponteiro: alterna para o teclado (icone do canto)
            tog = next((e for e in els if re.search(r"(text input|keyboard|teclado|entrada de texto|modo de entrada|input mode)", (e["desc"] or "") + " " + (e["text"] or ""), re.I)), None)
            if tog:
                self.tap((tog["cx"], tog["cy"]))
                time.sleep(0.8)
                els = read()
                ed = fields(els)
        if len(ed) < 2:
            return ("error: não achei os campos Hora/Minuto (o seletor está aberto?). Use set_alarm com hour/minute: é mais confiável que o seletor.")
        hour_f, min_f = ed[0], ed[1]
        twelve = any((e["text"] or "").strip().upper() == "AM" for e in els) and any((e["text"] or "").strip().upper() == "PM" for e in els)
        hh = (h % 12 or 12) if twelve else h
        for fld, val in ((hour_f, f"{hh:02d}"), (min_f, f"{m:02d}")):
            self.tap((fld["cx"], fld["cy"]))
            time.sleep(0.45)
            sh("input keyevent 123 " + "67 " * 5)
            sh("input text " + val)
            time.sleep(0.4)
        if twelve:
            want = "PM" if h >= 12 else "AM"
            tgt = next((e for e in read() if (e["text"] or "").strip().upper() == want), None)
            if tgt:
                self.tap((tgt["cx"], tgt["cy"]))
                time.sleep(0.4)
        els = read()
        vals = [e["text"].strip() for e in fields(els)[:2]]
        if vals != [f"{hh:02d}", f"{m:02d}"]:
            return f"error: os campos ficaram {vals} em vez de {[f'{hh:02d}', f'{m:02d}']}. Toque no campo vazio e use type com 2 dígitos, ou desista do seletor e use set_alarm."
        ok_btn = next((e for e in els if re.match(r"^(ok|confirmar|salvar|definir|set|save)$", (e["text"] or e["desc"] or "").strip(), re.I)), None)
        if not ok_btn:
            sh("input keyevent 4")  # teclado cobrindo o OK
            time.sleep(0.6)
            els = read()
            ok_btn = next((e for e in els if re.match(r"^(ok|confirmar|salvar|definir|set|save)$", (e["text"] or e["desc"] or "").strip(), re.I)), None)
        if not ok_btn:
            return "error: preenchi Hora/Minuto mas não vejo o botão OK (teclado/landscape?). Use hide_keyboard e toque em OK."
        self.tap((ok_btn["cx"], ok_btn["cy"]))
        time.sleep(1.0)
        return f"ok: horário {hh:02d}:{m:02d} preenchido, verificado e confirmado com OK. Confira na lista de alarmes."

    # ---------------------------------------------------------------- 5c) guardas e diagnostico
    @staticmethod
    def family(a):
        k = str(a.get("action", "")).lower()
        if k in ("shell", "sh", "bash", "cmd", "exec", "run", "terminal"):
            c = str(a.get("cmd") or a.get("command") or (" && ".join(map(str, a["cmds"])) if isinstance(a.get("cmds"), list) else "")).strip()
            c = re.sub(r"^(?:cd\s+\S+\s*&&\s*)", "", c)
            tk = c.split()
            if not tk:
                return "sh:"
            if tk[0] == "am" and "-a" in tk:
                return "sh:am -a " + tk[tk.index("-a") + 1] if tk.index("-a") + 1 < len(tk) else "sh:am"
            if tk[0] in ("pip", "pip3", "pkg", "apt", "apt-get") and len(tk) > 2:
                return "sh:" + " ".join(tk[:3])
            return "sh:" + tk[0] + (" " + tk[1] if tk[0] in ("settings", "cmd", "svc", "dumpsys", "pm", "git", "npm") and len(tk) > 1 else "")
        return k

    def brain_guard(self, kind, a):
        """Bloqueios inteligentes antes de executar. Retorna texto BLOCKED ou None. 'force' libera (exceto Termux:API sem app)."""
        if kind not in ("shell",):
            return None
        cmd = str(a.get("cmd") or a.get("command") or (" && ".join(map(str, a["cmds"])) if isinstance(a.get("cmds"), list) else ""))
        names = re.findall(r"\b(termux-[a-z0-9-]+)\b", cmd)
        alarm_names = [n for n in names if n not in ("termux-setup-storage", "termux-wake-lock", "termux-wake-unlock")]
        names = [n for n in names if n not in TERMUX_API_OK]
        if alarm_names and self.domain in ("alarm", "timer", "clock") and not a.get("force"):
            return ("BLOCKED (not executed): Termux:API/sleep/cron are NOT alarms. Use set_alarm {hour,minute,label,days} or set_timer {minutes}: real Clock-app "
                    "alarms created through the Android intent, verified by the system. (Add \"show\":true to see it in the app.)")
        if names and self.api_dead >= 1 and not a.get("force"):
            n = names[0]
            return (f"BLOCKED (not executed): `{n}` already hung/failed earlier in this session (Termux:API is not responding). Do not call termux-* again. "
                    f"Use: {TERMUX_ROOT_EQUIV.get(n, 'root:true with am/cmd/settings/dumpsys/input (Android tools)')}.")
        if self.domain in ("alarm", "timer", "clock") and not a.get("force") and re.search(r"\b(sleep\s+\d|crontab|at\s+now|job-scheduler)\b", cmd):
            return ("BLOCKED (not executed): delayed shell commands are not alarms/timers. Use set_alarm / set_timer.")
        fam = self.family(a)
        if fam in self.banned and not a.get("force"):
            info = self.fam_fail.get(fam, [0, "", ""])
            return (f"BLOCKED (not executed): this approach (`{fam}`) already failed {info[0]}x ({info[1]}). It is under DEAD ENDS: choose a DIFFERENT method "
                    "(another tool/route), not a variant of the same call. \"force\":true only if you changed the cause (installed/fixed something).")
        return None

    def brain_post(self, a, kind, res, n):
        """Anexa [DIAGNOSIS], registra falhas/sucessos (para aprender) e atualiza becos sem saida. Retorna o resultado (com diagnostico)."""
        res = str(res)
        tk = kind
        cmd = ""
        if tk == "shell":
            cmd = str(a.get("cmd") or a.get("command") or "")
        failed = result_failed(res) and not (tk == "shell" and benign_failure(cmd, res))
        fam = self.family(a)
        if res.startswith("BLOCKED"):
            self.hard += 1
            return res
        if not failed:
            if "termux-" in cmd and split_exit(res) == 0:
                self.api_dead = 0
            if tk in ("shell", "set_alarm", "set_timer", "device", "time_picker_set") and not re.match(r"^sh:(ls|cd|echo|pwd|cat|head|tail|sleep|true|command|which|test)\b", fam):
                self.succ_log.append((n, fam, (cmd or tk + " " + json.dumps({k: v for k, v in a.items() if k not in ("thought", "notes", "action", "fact", "plan", "done_goals")}, ensure_ascii=False))[:120]))
                del self.succ_log[:-12]
            return res
        self.hard += 1
        dg = diagnose(cmd, res, bool(a.get("root"))) if tk == "shell" else self._diag_action(tk, res)
        if any(c in ("termux_api_hang", "termux_api_missing") for c, _ in dg) or ("termux-" in cmd and "[timeout" in res):
            self.api_dead += 1
        code = dg[0][0] if dg else "error"
        ent = self.fam_fail.setdefault(fam, [0, code, ""])
        ent[0] += 1
        ent[1] = code
        ent[2] = res.strip().splitlines()[-1][:120] if res.strip() else ""
        self.fail_log.append((n, fam, code, (cmd or tk)[:120]))
        del self.fail_log[:-12]
        if tk == "shell" and code in BAN_CODES and fam not in self.banned and (ent[0] >= 2 or code in ("cmd_not_found", "termux_api_missing", "pkg_missing")):
            self.banned.add(fam)
            self.dead_ends.append(f"`{fam}` failed {ent[0]}x ({code}: {ent[2]})")
            del self.dead_ends[:-6]
            _log(f"  ! beco sem saída: {fam} falhou {ent[0]}x ({code}); bloqueado")
        if dg:
            txt = "\n".join(f"[DIAGNOSIS {c}] {adv}" for c, adv in dg)
            _log("  ↳ diagnóstico: " + dg[0][1][:130])
            return res + "\n" + txt
        return res

    @staticmethod
    def _diag_action(kind, res):
        low = str(res).lower()
        if "indice invalido" in low or "invalid index" in low:
            return [("bad_index", "Indexes change EVERY turn: use an index from the CURRENT SCREEN list, or tap_text with the visible text.")]
        if "app nao encontrado" in low:
            return [("app_missing", "No installed app matches that name. Search it: shell root:true `pm list packages | grep -i NAME`; if absent, say so (do not install without being asked).")]
        if "sem atividade" in low:
            return [("no_launcher", "The package has no launcher activity. Find one: `cmd package resolve-activity --brief PKG`, then `am start -n PKG/ACTIVITY` (root).")]
        if "no text field" in low:
            return [("no_field", "No text field here: open the page/dialog that has one first (tap the search icon / the field), then type.")]
        if "horário inválido" in low or "campos" in low:
            return []
        return []

    # ---------------------------------------------------------------- 5d) contexto para o prompt
    def brain_context(self, pkg=""):
        parts = []
        pb = playbook_for(self.domain, pkg or getattr(self, "cur_pkg", ""))
        if pb:
            parts.append(pb)
        if self.lesson_text:
            parts.append(self.lesson_text)
        if self.dead_ends:
            parts.append("DEAD ENDS in this task (blocked, do NOT retry; pick a different method):\n" + "\n".join("- " + d for d in self.dead_ends))
        if self.api_dead:
            parts.append("TERMUX:API is NOT responding on this phone: never call termux-* commands; use root equivalents (am/cmd/settings/dumpsys/input).")
        return "\n".join(parts)

    def brain_warn(self, els, pkg, unchanged):
        out = []
        fs = screen_findings(els, pkg)
        if fs:
            out.append("SCREEN FINDINGS (computed by the system, trust them): " + " | ".join(fs))
        sl = stuck_ladder(unchanged, pkg)
        if sl:
            out.append(sl)
        return ("\n" + "\n".join(out)) if out else ""

    # ---------------------------------------------------------------- 5e) resgate e aprendizado
    def rescue(self, task, n, unchanged, els, pkg):
        """Tela parada >=3 acoes. Se o dialogo aberto e o seletor de horario e o pedido traz UM horario, o CODIGO preenche e confirma
        (em vez de o modelo continuar digitando em campo vazio). Retorna o texto do resultado (para o historico) ou None."""
        if unchanged < 3 or getattr(self, "rescue_n", 0) >= 2 or not els:
            return None
        picker = any(PICKER_RE.search((e["text"] or "") + " " + (e["desc"] or "")) for e in els)
        if not picker:
            return None
        f = fold(self.task_text or task)
        if count_times(f) > 1:
            return None
        ct = parse_clock_time(f)
        if not ct:
            return None
        self.rescue_n = getattr(self, "rescue_n", 0) + 1
        h, m, _ = ct
        _log(f"  ⚡ resgate: seletor de horário travado; preencho {h:02d}:{m:02d} pelo código")
        from_agent = getattr(self, "_parse_ui", None)
        if not from_agent:
            return None
        res = self.act_time_picker({"hour": h, "minute": m}, from_agent)
        self.lessons.add("In the Clock 'Set time' dialog never leave the Minute field empty: use time_picker_set {hour,minute} (or skip the dialog with set_alarm).",
                         tags=["alarme", "alarm", "relogio", "clock", "horario", "picker"], domain="alarm", source="rescue")
        return res

    def learn_from_run(self, task, ok, hist_events):
        """Fim da tarefa: grava licoes (reflexao do modelo quando a tarefa foi dificil; senao pareamento falha->sucesso por codigo)."""
        made = []
        hard = self.hard >= 2 or bool(self.fail_log and not ok) or bool(self.dead_ends)
        if self.used_ids:
            self.lessons.mark(self.used_ids, ok)
        if not (self.fail_log or self.dead_ends or (not ok and self.hard)):
            return made
        if self.reflect_enabled and hard:
            try:
                fails = "\n".join(f"- {c[:100]} -> {code}" for _, _, code, c in self.fail_log[-6:]) or "(none)"
                worked = "\n".join(f"- {t}" for _, _, t in self.succ_log[-4:]) or "(nothing confirmed)"
                ev = "\n".join(hist_events[-14:])
                p = REFLECT_PROMPT.format(task=task[:300], outcome="SUCCESS" if ok else "FAILED", fails=fails, events=(worked + "\n" + ev)[:1800])
                d = self.parse_json_safe(self.post_chat([{"role": "user", "content": p}], True, timeout=90, predict=500, model=self.tm()))
                for ls in (d or {}).get("lessons", [])[:3] if isinstance(d, dict) else []:
                    if isinstance(ls, dict) and ls.get("lesson"):
                        tags = [fold(t) for t in ls.get("tags", []) if isinstance(t, str)][:6]
                        it = self.lessons.add(ls["lesson"], tags=tags + tokens(task)[:4], domain=self.domain, source="reflect")
                        if it:
                            made.append(it["text"])
            except Exception as e:
                _log(f"    (reflexão falhou: {str(e)[:80]})")
        if not made and ok and self.fail_log and self.succ_log:  # plano B por codigo: o que falhou -> o que funcionou depois
            n0, ffam, code, fcmd = self.fail_log[-1]
            nxt = next(((n, fam, t) for n, fam, t in self.succ_log if n > n0 and fam != ffam), None)
            if nxt:
                txt = f"For '{' '.join(tokens(task)[:4])}': `{fcmd[:70]}` fails ({code}); what worked instead: `{nxt[2][:90]}`."
                it = self.lessons.add(txt, tags=tokens(task)[:6], domain=self.domain, source="pair")
                if it:
                    made.append(it["text"])
        for t in made:
            _log(f"  ✎ aprendi: {t[:150]}")
        self.new_lessons = made
        return made

    @staticmethod
    def parse_json_safe(s):
        try:
            m = re.search(r"\{.*\}", s, re.S)
            return json.loads(m.group(0)) if m else None
        except ValueError:
            return None
