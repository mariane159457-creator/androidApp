"""v6 - atalhos de intencao, diagnostico, becos sem saida, Termux:API morto, licoes, seletor de horario. So usa /tmp/pa_test_home3."""
import os, sys, json, io, contextlib, shutil, re
shutil.rmtree("/tmp/pa_test_home3", ignore_errors=True)
os.makedirs("/tmp/pa_test_home3/proj")
os.environ["HOME"] = "/tmp/pa_test_home3"; os.environ["NO_ANIM"] = "1"; os.environ["NO_COLOR"] = "1"; os.environ["PA_NO_REFLECT"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import agent as A
import brain as B

OK = 0
A.time.sleep = lambda s: None
def check(name, cond, extra=""):
    global OK
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        sys.exit(1)
    OK += 1

# ---------------------------------------------------------------- parser
def P(t):
    return B.parse_intent(t)
check("YouTube Music preferido quando instalado", B.choose_music_app({"com.spotify.music", "com.google.android.apps.youtube.music"}) == "com.google.android.apps.youtube.music")
i = P("coloque um alarme às 9")
check("alarme as 9 -> 09:00", i and i.kind == "alarm" and (i["hour"], i["minute"]) == (9, 0))
i = P("alarme às 9 da noite"); check("9 da noite -> 21:00", i["hour"] == 21)
i = P("me acorde às 7 e meia"); check("7 e meia -> 07:30", (i["hour"], i["minute"]) == (7, 30))
i = P("alarme 07:30 de segunda a sexta chamado academia")
check("dias uteis + rotulo", i["days"] == [2, 3, 4, 5, 6] and i["label"] == "academia", dict(i))
i = P("crie um alarme no app às 9"); check("'no app' -> show", i["show"] is True)
i = P("timer de 10 minutos"); check("timer 600s", i.kind == "timer" and i["seconds"] == 600)
i = P("timer 1h30"); check("timer 1h30", i["seconds"] == 5400)
i = P("set an alarm for 7pm"); check("7pm -> 19", i["hour"] == 19)
check("varios horarios -> modelo", P("alarme às 7, às 8 e às 9") is None)
check("apagar alarme -> modelo", P("desative o alarme das 7") is None)
check("script com alarme -> modelo", P("escreva um script python de alarme às 7") is None)
check("2 pedidos -> modelo", P("ligue o wifi e abra o chrome") is None)
check("lição busuu -> modelo", P("faça a lição do busuu") is None)
i = P("coloque a música Love For You da Lovely Lori"); check("música com artista", i.kind == "music" and i["title"] == "love for you" and i["artist"] == "lovely lori")
i = P("toque no botão"); check("toque sem música -> modelo", i is None)
i = P("toque o botão de login"); check("botão de UI -> modelo", i is None)
i = P("toque em um arquivo mp3"); check("arquivo mp3 -> modelo", i is None)
i = P("open youtube and play lofi"); check("app + play -> modelo", i is None)
i = P("pause a música"); check("pause", i.kind == "music_control" and i["action"] == "pause")
i = P("continue tocando"); check("resume", i.kind == "music_control" and i["action"] == "resume")
i = P("reproduza a próxima música"); check("next", i.kind == "music_control" and i["action"] == "next")
i = P("volume 40%"); check("volume 40", i.kind == "volume" and i["value"] == 40)
i = P("ligue o wifi"); check("wifi on", i.kind == "toggle" and i["on"] is True)
i = P("desligue o bluetooth"); check("bt off", i["on"] is False)
i = P("abra o youtube"); check("abrir app", i.kind == "open_app")
check("abrir + procurar -> modelo", P("abra o youtube e procure lofi") is None)

# ---------------------------------------------------------------- diagnostico
d = B.diagnose("termux-volume", "[cwd /x] [exit 127]\nsh: termux-volume: not found")
check("termux-* ausente", d and d[0][0] == "termux_api_missing" and "cmd media_session" in d[0][1], d)
d = B.diagnose("am start -a FOO", "[cwd /x] [exit 1]\nError: Activity not started, unable to resolve Intent { act=FOO }", root=True)
check("intent nao resolvida", d[0][0] == "intent_unresolved", d)
d = B.diagnose("settings get global wifi_on", "[cwd /x] [exit 127]\nsh: settings: inaccessible or not found")
check("ferramenta android sem root", d[0][0] == "android_tool_no_root", d)
d = B.diagnose("python x.py", "[cwd /x] [exit 1]\nModuleNotFoundError: No module named 'cv2'")
check("modulo python", d[0][0] == "py_module" and "opencv" in d[0][1], d)
d = B.diagnose("termux-battery-status", "[cwd /x] [exit -9]\n\n[timeout 30s: command killed]")
check("termux hang", d[0][0] == "termux_api_hang", d)
check("grep sem resultado nao e erro", B.benign_failure("grep foo x.txt", "[cwd /x] [exit 1]\n"))

# ---------------------------------------------------------------- achados de tela
def el(text="", desc="", line=None):
    return {"text": text, "desc": desc, "line": line or f'[0] TextView "{text}"', "cx": 0, "cy": 0}
fs = B.screen_findings([el("Selecionar horário"), el("", line="[1] EditText \"\" (editable,focused)")])
check("achado: seletor de horario + campo vazio", any("TIME PICKER" in x and "EMPTY" in x for x in fs), fs)
check("achado: erro visivel", any("error" in x for x in B.screen_findings([el("Erro: tente novamente")])))
check("escada nao aparece cedo", B.stuck_ladder(2) == "" and "STUCK LADDER" in B.stuck_ladder(4))

# ---------------------------------------------------------------- licoes
st = B.LessonStore("/tmp/pa_test_home3/l.json")
st.add("Para alarme use set_alarm e nao termux-api", tags=["alarme", "relogio"], domain="alarm")
st.add("Para alarme use set_alarm e nao termux-api!!", tags=["alarme"], domain="alarm")
check("duplicata reforca, nao duplica", len(st.items) == 1 and st.items[0]["hits"] == 1)
st2 = B.LessonStore("/tmp/pa_test_home3/l.json")
check("persiste em disco", len(st2.items) == 1)
txt, ids = st2.block("coloque um alarme às 9", "alarm")
check("licao entra no prompt da tarefa parecida", "set_alarm" in txt and ids)
check("licao NAO entra em tarefa sem relacao", st2.block("liste os arquivos daqui", "generic")[0] == "")
check("forget remove", st2.forget(st2.items[0]["id"]) == 1 and not st2.items)

# ---------------------------------------------------------------- agente com dispositivo falso
class Dev:
    su = None
    def __init__(self, picker=None):
        self.cmds, self.picker = [], picker
        self.alarm_list_xml = ('<hierarchy><node text="09:00" class="android.widget.TextView" package="com.google.android.deskclock" bounds="[0,100][500,300]" '
                               'clickable="false" enabled="true" focused="false" scrollable="false" content-desc=""/>'
                               '<node text="" class="android.widget.Switch" package="com.google.android.deskclock" checkable="true" checked="true" '
                               'bounds="[600,100][700,300]" clickable="true" enabled="true" focused="false" scrollable="false" content-desc=""/></hierarchy>')
    def argv(self, c): return ["sh", "-c", c]
    def sh(self, c, **k):
        self.cmds.append(c)
        if c.startswith("pm list packages"): return "package:com.google.android.deskclock\npackage:com.termux\n"
        if "next_alarm_formatted" in c: return "null\n"
        if c.startswith("am start -a android.intent.action.SET_ALARM"): return "Starting: Intent { act=android.intent.action.SET_ALARM }\n"
        if c.startswith("am start -a android.intent.action.SET_TIMER"): return "Starting: Intent { act=android.intent.action.SET_TIMER }\n"
        if self.picker is not None:
            return self.picker.handle(c)
        return ""
    def dump(self):
        return self.picker.xml() if self.picker is not None else self.alarm_list_xml
    def screenshot(self): return None

def make(dev, task, mode="auto"):
    calls = []
    def fake(path, body=None, timeout=0):
        calls.append(body["messages"][-1]["content"][:60])
        raise AssertionError("o atalho nao deveria chamar o modelo")
    A.ollama = fake
    ag = A.Agent(dev, "gemma-v", vision=False, delay=0.0, home=True)
    ag.mode, ag.can_ask, ag.notify_on = mode, False, False
    os.chdir("/tmp/pa_test_home3/proj")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = ag.run(task, 0)
    return ok, calls, dev, buf.getvalue(), ag

# o caso do usuario: "coloque um alarme" NAO pode ir para o Termux:API nem chamar o modelo
dev = Dev()
ok, calls, dev, out, ag = make(dev, "coloque um alarme às 9 chamado remédio")
check("alarme: concluido pelo atalho", ok, out)
check("alarme: nenhuma chamada de modelo", not calls)
sa = [c for c in dev.cmds if c.startswith("am start -a android.intent.action.SET_ALARM")]
check("alarme: intent SET_ALARM com hora, minuto, rotulo e SKIP_UI",
      sa and "HOUR 9" in sa[0] and "MINUTES 0" in sa[0] and "SKIP_UI true" in sa[0] and "remédio" in sa[0] and "-p com.google.android.deskclock" in sa[0], sa)
check("alarme: nunca usou termux-*", not any("termux-" in c for c in dev.cmds))
flat = " ".join(out.split())
check("alarme: confirmou no app Relogio", "Confirmado no app Relógio" in flat and "LIGADO" in flat, out)

# no app: show (sem SKIP_UI) e nada de toques na tela
dev = Dev()
ok, calls, dev, out, ag = make(dev, "crie um alarme no app às 9")
sa = [c for c in dev.cmds if c.startswith("am start -a android.intent.action.SET_ALARM")]
check("no app: sem SKIP_UI, sem input tap", ok and sa and "SKIP_UI" not in sa[0] and not any(c.startswith("input tap") for c in dev.cmds), (sa, dev.cmds))

# timer
dev = Dev()
ok, calls, dev, out, ag = make(dev, "timer de 10 minutos")
check("timer: intent com LENGTH 600", ok and any("LENGTH 600" in c for c in dev.cmds), dev.cmds)

# intent recusada -> o atalho nao conclui e o agente continua com fato/aviso (aqui sem modelo: so checa o retorno)
class DevBad(Dev):
    def sh(self, c, **k):
        if c.startswith("am start -a android.intent.action.SET_ALARM"):
            self.cmds.append(c); return "Error: Activity not started, unable to resolve Intent\n"
        return super().sh(c, **k)
dev = DevBad()
ag = A.Agent(dev, "m", vision=False, delay=0.0)
ag.pkgs = {"com.google.android.deskclock"}
ok_, msg = ag.do_alarm(9, 0)
check("intent recusada = falha honesta", not ok_ and "recusou" in msg, msg)

class DevNoAlarmEvidence(Dev):
    def sh(self, c, **k):
        self.cmds.append(c)
        if "next_alarm_formatted" in c: return "null\n"
        if "SET_ALARM" in c or "SHOW_ALARMS" in c: return "Starting: Intent { act=android.intent.action.SET_ALARM }\n"
        return ""
    def dump(self): return ""

dev = DevNoAlarmEvidence(); ag = A.Agent(dev, "m", vision=False, delay=0.0)
ag.pkgs = {"com.google.android.deskclock"}
ok_, msg = ag.do_alarm(9, 0)
check("alarme sem evidência específica não é concluído", not ok_ and "não consegui confirmar" in msg, msg)

class DevExistingAlarm(Dev):
    def sh(self, c, **k):
        if "next_alarm_formatted" in c:
            self.cmds.append(c); return "09:00\n"
        return super().sh(c, **k)

dev = DevExistingAlarm(); ag = A.Agent(dev, "m", vision=False, delay=0.0)
ag.pkgs = {"com.google.android.deskclock"}
ok_, msg = ag.do_alarm(9, 0)
check("alarme preexistente no mesmo horário não prova criação", not ok_ and "já existia antes" in msg, msg)

class DevAlarmOff(DevNoAlarmEvidence):
    def dump(self): return self.alarm_list_xml.replace('checked="true"', 'checked="false"')

dev = DevAlarmOff(); ag = A.Agent(dev, "m", vision=False, delay=0.0)
ag.pkgs = {"com.google.android.deskclock"}
ok_, msg = ag.do_alarm(9, 0)
check("alarme visível mas desligado não é sucesso", not ok_ and "DESLIGADO" in msg, msg)

# volume/wifi verificados
class DevSet(Dev):
    def __init__(self): super().__init__(); self.vol, self.wifi = 7, "0"
    def sh(self, c, **k):
        self.cmds.append(c)
        if "media_session volume --stream 3 --get" in c: return f"volume is {self.vol} in range [0..15]\n"
        m = re.search(r"media_session volume --stream 3 --set (\d+)", c)
        if m: self.vol = int(m.group(1)); return ""
        if c.startswith("svc wifi enable"): self.wifi = "1"; return ""
        if "get global wifi_on" in c: return self.wifi + "\n"
        return super().sh(c, **k)
dev = DevSet(); ag = A.Agent(dev, "m", vision=False, delay=0.0)
r = ag.do_volume("media", 40); check("volume 40% -> 6/15 confirmado", r[0] and dev.vol == 6, r)
r = ag.do_toggle("wifi", True); check("wifi on confirmado", r[0] and "confirmado" in r[1], r)

class MusicDev(Dev):
    def __init__(self, state=3, title="Love For You", artist="Lovely Lori"):
        super().__init__(); self.state, self.title, self.artist = state, title, artist
    def sh(self, c, **k):
        self.cmds.append(c)
        if c == "dumpsys media_session 2>&1":
            return (f"Sessions Stack:\n  * com.spotify.music\n    package=com.spotify.music\n"
                    f"    PlaybackState {{state={self.state}, position=100}}\n    title={self.title}\n    artist={self.artist}\n")
        if c.startswith("input keyevent KEYCODE_MEDIA_"):
            action = c.rsplit("_", 1)[-1]
            self.state = {"PAUSE": 2, "PLAY": 3, "PLAY_PAUSE": 2, "NEXT": 3, "PREVIOUS": 3}.get(action, self.state)
            if action == "NEXT": self.title = "Different Song"
            if action == "PREVIOUS": self.title = "Previous Song"
            return ""
        return ""

dev = MusicDev(); ag = A.Agent(dev, "m", vision=False, delay=0.0); ag.pkgs = {"com.spotify.music"}
r = ag.do_music(action="pause")
check("pause envia tecla de mídia e confirma estado", r[0] and any("KEYCODE_MEDIA_PAUSE" in c for c in dev.cmds) and "confirmado" in r[1], (r, dev.cmds))
dev = MusicDev(state=2); ag = A.Agent(dev, "m", vision=False, delay=0.0); ag.pkgs = {"com.spotify.music"}
r = ag.do_music(action="resume")
check("retomar envia tecla e confirma reprodução", r[0] and any("KEYCODE_MEDIA_PLAY" in c for c in dev.cmds) and "reproduzindo" in r[1], (r, dev.cmds))
dev = MusicDev(); ag = A.Agent(dev, "m", vision=False, delay=0.0); ag.pkgs = {"com.spotify.music"}
r = ag.do_music(action="next")
check("próxima faixa só confirma com metadado alterado", r[0] and any("KEYCODE_MEDIA_NEXT" in c for c in dev.cmds) and "Different Song" in r[1], (r, dev.cmds))
class MultiSessionDev(Dev):
    def sh(self, c, **k):
        if c == "dumpsys media_session 2>&1":
            return ("  * com.other.player/Service\n    package=com.other.player\n    PlaybackState {state=2}\n    title=Other\n"
                    "  * com.spotify.music/Service\n    package=com.spotify.music\n    PlaybackState {state=3}\n    title=Love For You\n")
        return ""
dev = MultiSessionDev(); ag = A.Agent(dev, "m", vision=False, delay=0.0)
check("estado de mídia pertence ao app selecionado", ag._music_session("com.spotify.music") == (3, "Love For You", ""))

class FastYouTubeMusicDev(MusicDev):
    def sh(self, c, **k):
        if "MEDIA_PLAY_FROM_SEARCH" in c:
            self.cmds.append(c); self.state = 3; return "Starting: Intent { act=android.media.action.MEDIA_PLAY_FROM_SEARCH }"
        if c == "dumpsys media_session 2>&1":
            self.cmds.append(c)
            return (f"Sessions Stack:\n  * com.google.android.apps.youtube.music/Service\n"
                    f"    package=com.google.android.apps.youtube.music\n"
                    f"    PlaybackState {{state={self.state}, position=100}}\n    title={self.title}\n    artist={self.artist}\n")
        return super().sh(c, **k)

dev = FastYouTubeMusicDev(); ag = A.Agent(dev, "m", vision=False, delay=0.0)
ag.pkgs = {"com.google.android.apps.youtube.music"}
r = ag.do_music("Love For You", "Lovely Lori")
check("intent rápida confirma faixa e artista no YouTube Music", r[0] and "iniciou" in r[1].lower() and any("MEDIA_PLAY_FROM_SEARCH" in c for c in dev.cmds), (r, dev.cmds))
dev = FastYouTubeMusicDev(artist="Different Artist"); ag = A.Agent(dev, "m", vision=False, delay=0.0)
ag.pkgs = {"com.google.android.apps.youtube.music"}
r = ag.do_music("Love For You", "Lovely Lori")
check("intent rápida rejeita artista diferente e cai para busca", not r[0] and "Pesquisa oficial" in r[1] and any("VIEW" in c for c in dev.cmds), (r, dev.cmds))
dev = Dev(); ag = A.Agent(dev, "m", vision=False, delay=0.0); ag.pkgs = set()
r = ag.do_music("Love For You", "Lovely Lori")
check("sem app de música não afirma reprodução", not r[0] and "instalado" in r[1], r)
dev = Dev(); ag = A.Agent(dev, "m", vision=False, delay=0.0); ag.pkgs = {"com.spotify.music"}
r = ag.do_music("Love For You", "Lovely Lori")
check("busca oficial preserva título e artista sem afirmar playback",
    not r[0] and ag.left_term and "Love%20For%20You%20Lovely%20Lori" in " ".join(dev.cmds) and "confirme a reprodução" in r[1], (r, dev.cmds))

# ---------------------------------------------------------------- guardas
dev = Dev(); ag = A.Agent(dev, "m", vision=False, delay=0.0)
ag.brain_reset("coloque um alarme às 9 e fale comigo")
g = ag.guard({"action": "shell", "cmd": "termux-notification --title alarme"}, 1)
check("termux-* em tarefa de alarme = bloqueado com a saida certa", g and "set_alarm" in g, g)
ag.brain_reset("quanto de bateria tem")
r = ag.brain_post({"action": "shell", "cmd": "termux-battery-status"}, "shell", "[cwd /x] [exit -9]\n\n[timeout 30s: command killed]", 1)
check("hang do termux-api gera diagnostico", "[DIAGNOSIS termux_api_hang]" in r and ag.api_dead == 1, r)
g = ag.guard({"action": "shell", "cmd": "termux-volume"}, 2)
check("depois do hang, termux-* e bloqueado com equivalente root", g and "BLOCKED" in g and "media_session" in g, g)
check("force libera", ag.guard({"action": "shell", "cmd": "termux-volume", "force": True}, 3) is None or "FILE" in str(ag.guard({"action": "shell", "cmd": "termux-volume", "force": True}, 3)))
# beco sem saida: intent inexistente 2x
ag.brain_reset("faca algo")
for n in (1, 2):
    ag.brain_post({"action": "shell", "cmd": "am start -a FOO.BAR", "root": True}, "shell", "[cwd /x] [exit 1]\nError: Activity not started, unable to resolve Intent", n)
check("2 falhas da mesma familia = beco sem saida", "FOO.BAR" in " ".join(ag.dead_ends), ag.dead_ends)
g = ag.guard({"action": "shell", "cmd": "am start -a FOO.BAR --es x y", "root": True}, 3)
check("variante da mesma familia e bloqueada", g and "DEAD ENDS" in g, g)
check("beco aparece no prompt", "DEAD ENDS" in ag.brain_context())
# erro de script NAO bane a familia python (o usuario conserta e roda de novo)
ag.brain_reset("rode o script")
for n in (1, 2, 3):
    ag.brain_post({"action": "shell", "cmd": "python x.py"}, "shell", "[cwd /x] [exit 1]\nTraceback (most recent call last):\nNameError: x", n)
check("python com erro de script nao e banido", ag.guard({"action": "shell", "cmd": "python x.py"}, 4) is None)

# ---------------------------------------------------------------- aprendizado: falha -> o que funcionou
ag.brain_reset("mude o volume do celular")
ag.brain_post({"action": "shell", "cmd": "termux-volume music 5"}, "shell", "[cwd /x] [exit 127]\nsh: termux-volume: not found", 1)
ag.brain_post({"action": "device", "setting": "volume", "value": "30"}, "device", "ok: Volume de mídia em 5/15 (confirmado).", 2)
with contextlib.redirect_stdout(io.StringIO()):
    made = ag.learn_from_run("mude o volume do celular", True, [])
check("licao gravada por pareamento", made and "termux-volume" in made[0] and "device" in made[0], made)
ag.brain_reset("ajuste o volume do celular para 20")
check("licao volta na tarefa parecida", "termux-volume" in ag.lesson_text, ag.lesson_text)

# ---------------------------------------------------------------- seletor de horario (dialogo do print) com dispositivo simulado
class Picker:
    """Simula o dialogo 'Selecionar horario' do print: Hora=09, Minuto vazio. Teclas/toques alteram o estado."""
    def __init__(self):
        self.hour, self.minute, self.focus, self.done = "09", "", "min", False
    def xml(self):
        n = lambda t, b, cls="android.widget.EditText", extra="": (f'<node text="{t}" class="{cls}" package="com.google.android.deskclock" content-desc="" '
                                                                  f'clickable="true" enabled="true" focused="false" scrollable="false" bounds="{b}" {extra}/>')
        return ('<hierarchy><node text="" class="android.widget.FrameLayout" package="com.google.android.deskclock" content-desc="" clickable="false" enabled="true" focused="false" scrollable="false" bounds="[0,0][720,1612]"/>' + '<node text="Selecionar horário" class="android.widget.TextView" package="com.google.android.deskclock" content-desc="" clickable="false" enabled="true" focused="false" scrollable="false" bounds="[170,380][500,420]"/>'
                + n(self.hour, "[171,445][339,584]") + n(self.minute, "[381,445][549,584]")
                + n("Cancelar", "[300,690][450,720]", "android.widget.Button") + n("OK", "[480,690][560,720]", "android.widget.Button") + '</hierarchy>')
    def handle(self, c):
        m = re.match(r"input tap (\d+) (\d+)", c)
        if m:
            x, y = int(m.group(1)), int(m.group(2))
            if y < 600: self.focus = "hour" if x < 360 else "min"
            elif x > 470: self.done = True
        if c.startswith("input keyevent 123"):
            for _ in c.split().count("67") * [0]:
                if self.focus == "hour": self.hour = self.hour[:-1]
                else: self.minute = self.minute[:-1]
        m = re.match(r"input text (\d+)", c)
        if m:
            if self.focus == "hour": self.hour += m.group(1)
            else: self.minute += m.group(1)
        return ""

pk = Picker(); dev = Dev(pk); ag = A.Agent(dev, "m", vision=False, delay=0.0)
ag.tap = lambda xy: dev.sh(f"input tap {xy[0]} {xy[1]}")
r = ag.act({"action": "time_picker_set", "hour": 9, "minute": 0})
check("time_picker_set fica desativado na edicao textual", r.startswith("BLOCKED") and not pk.done, r)

print(f"\n{OK} verificacoes ok")
