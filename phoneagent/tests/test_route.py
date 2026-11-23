"""v5 - roteamento terminal x tela, sem HOME, sem planejador/auditor em consulta simples, type com foco, open_url. So usa /tmp/pa_test_home2."""
import os, sys, json, io, contextlib, shutil
shutil.rmtree("/tmp/pa_test_home2", ignore_errors=True)
os.makedirs("/tmp/pa_test_home2/proj")
os.environ["HOME"] = "/tmp/pa_test_home2"; os.environ["NO_ANIM"] = "1"; os.environ["NO_COLOR"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import agent as A
from PIL import Image

OK = 0
def check(name, cond, extra=""):
    global OK
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        sys.exit(1)
    OK += 1

def png():
    b = io.BytesIO(); Image.new("RGB", (1080, 2400), (240, 240, 240)).save(b, "PNG"); return b.getvalue()

XML = ('<hierarchy><node index="0" text="" resource-id="com.android.chrome:id/url_bar" class="android.widget.EditText" package="com.android.chrome" '
       'content-desc="" clickable="true" enabled="true" focused="false" scrollable="false" bounds="[0,0][1080,2400]">'
       '</node><node index="1" text="" resource-id="com.android.chrome:id/url_bar" class="android.widget.EditText" package="com.android.chrome" '
       'content-desc="" clickable="true" enabled="true" focused="false" scrollable="false" bounds="[100,100][900,200]"/>'
       '<node index="2" text="Pagar multa" resource-id="" class="android.widget.Button" package="com.android.chrome" content-desc="" clickable="true" '
       'enabled="true" focused="false" scrollable="false" bounds="[100,300][900,400]"/></hierarchy>')

class Dev:
    su = None
    def __init__(self, shots=True):
        self.cmds, self.shots, self.allow_shot = [], 0, shots
    def sh(self, c, **k):
        self.cmds.append(c); return ""
    def argv(self, c): return ["sh", "-c", c]
    def dump(self): return XML
    def screenshot(self):
        self.shots += 1
        if not self.allow_shot: raise AssertionError("screenshot em tarefa de terminal")
        return png()

def run(task, steps, mode="auto", shots=True, text_model="gpt-t"):
    calls, steps = [], list(steps)
    def fake(path, body=None, timeout=0):
        m = body["messages"][-1]["content"]
        if "Plan the TASK" in m:
            calls.append(("plan", body["model"], False, "")); return {"message": {"content": json.dumps({"goals": ["a", "b"], "constraints": [], "deliverables": [], "question": None})}}
        if "QA auditor" in m:
            calls.append(("audit", body["model"], False, "")); return {"message": {"content": json.dumps({"complete": True, "missing": []})}}
        calls.append(("step", body["model"], bool(body["messages"][-1].get("images")), body["messages"][0]["content"]))
        return {"message": {"content": json.dumps(steps.pop(0))}}
    A.ollama = fake
    dev = Dev(shots)
    ag = A.Agent(dev, "gemma-v", vision=True, delay=0.0, home=True)
    ag.mode, ag.text_model, ag.can_ask, ag.notify_on = mode, text_model, False, False
    os.chdir("/tmp/pa_test_home2/proj")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = ag.run(task, 0)
    return ok, calls, dev, buf.getvalue(), ag

# ---- 1) o caso do log: "liste os arquivos daqui" -> terminal, rapido, sem HOME, sem screenshot, so modelo de texto, sem plano/auditor
check("kind: liste os arquivos daqui = terminal", A.task_kind("liste os arquivos daqui") == "terminal")
check("kind: musica com artista = tela", A.task_kind("Toque Love For You da Lovely Lori") == "screen")
ok, calls, dev, out, ag = run("liste os arquivos daqui", [
    {"thought": "listar", "action": "shell", "cmd": "ls -la"},
    {"thought": "pronto", "action": "done", "message": "a.txt\nb.txt\nc.txt"}])
check("terminal simples conclui", ok)
check("nunca apertou HOME", not any("keyevent 3" in c for c in dev.cmds), dev.cmds)
check("nenhum screenshot", dev.shots == 0)
check("so o modelo de texto decidiu", all(c[1] == "gpt-t" for c in calls), calls)
check("sem planejador e sem auditor", not any(c[0] in ("plan", "audit") for c in calls), calls)
check("prompt de terminal", "TERMINAL" in calls[0][3] or "Termux terminal of a ROOTED" in calls[0][3])
check("resposta final completa (3 linhas)", all(x in out for x in ("a.txt", "b.txt", "c.txt")), out)

# ---- 2) modelo tenta sair do terminal: bloqueado
ok, calls, dev, out, ag = run("liste os arquivos daqui", [
    {"action": "home"}, {"action": "shell", "cmd": "ls"}, {"action": "done", "message": "ok"}])
check("home em tarefa de terminal = BLOQUEADO", "BLOCKED" in out and not any("keyevent 3" in c for c in dev.cmds), out)

# ---- 3) terminal que precisa da tela: escala para o gemma sozinho e volta ao Termux no fim
ok, calls, dev, out, ag = run("compacte a pasta fotos e envie no drive", [
    {"thought": "abrir drive", "action": "open_app", "app": "chrome"},
    {"thought": "tocar", "action": "tap", "index": 2},
    {"thought": "ok", "action": "done", "message": "enviado", "force": True}], shots=True)
steps = [c for c in calls if c[0] == "step"]
check("1o passo (sem tela) = modelo de texto", steps[0][1] == "gpt-t" and not steps[0][2], steps[0][:3])
check("depois de escalar, a tela vai para o gemma", steps[1][1] == "gemma-v" and steps[1][2], steps[1][:3])
check("prompt de tela apos escalar", "from the Termux terminal" in steps[1][3], steps[1][3][:80])
check("voltou ao Termux no fim (tarefa era de terminal)", any("com.termux/com.termux.app.TermuxActivity" in c for c in dev.cmds), dev.cmds[-4:])

# ---- 4) tarefa de tela (a do TSE): gemma decide, prompt enxuto, sem HOME, type com foco automatico + Enter
task = "entre no site onde eu posso pagar a multa por nao ter votado, logue e gere o boleto, meu nome e Matheus"
check("kind: TSE = tela", A.task_kind(task) == "screen")
ok, calls, dev, out, ag = run(task, [
    {"thought": "buscar", "action": "type", "text": "pagar multa eleitoral TSE", "submit": True},
    {"thought": "fim", "action": "done", "message": "feito", "force": True}])
steps = [c for c in calls if c[0] == "step"]
check("tarefa de tela: gemma com imagem", all(c[1] == "gemma-v" and c[2] for c in steps), steps)
check("prompt de tela enxuto (nao o de licoes)", "from the Termux terminal" in steps[0][3] and "SELECT / HIGHLIGHT" not in steps[0][3])
check("tela nao aperta HOME no inicio", not any(c.strip() == "input keyevent 3" for c in dev.cmds), dev.cmds)
i_tap = next(i for i, c in enumerate(dev.cmds) if c.startswith("input tap"))
i_txt = next(i for i, c in enumerate(dev.cmds) if c.startswith("input text"))
i_ent = next(i for i, c in enumerate(dev.cmds) if c == "input keyevent 66")
check("type: toca no campo, digita e da Enter (nessa ordem)", i_tap < i_txt < i_ent, dev.cmds)
check("tarefa de tela NAO volta ao Termux a forca", not any("TermuxActivity" in c for c in dev.cmds))
ok, calls, dev, out, ag = run("faca a licao do busuu", [{"action": "done", "message": "ok", "force": True}])
check("licao usa o prompt completo", "SELECT / HIGHLIGHT" in [c for c in calls if c[0] == "step"][0][3])

# ---- 5) open_url esperto, open_app termux = no-op, show_result sem cabecalho
ag.term_only = False
dev.cmds.clear()
ag.act({"action": "open_url", "url": "multa eleitoral tse"})
check("open_url: palavras soltas viram busca no Google", "google.com/search?q=multa+eleitoral+tse" in dev.cmds[-1], dev.cmds)
ag.act({"action": "open_url", "url": "www.tse.jus.br/servicos"})
check("open_url: dominio ganha https://", "https://www.tse.jus.br/servicos" in dev.cmds[-1], dev.cmds)
n = len(dev.cmds)
r = ag.act({"action": "open_app", "app": "termux"}) if hasattr(ag, "resolve_app") else ""
check("open_app termux = no-op", "ALREADY inside Termux" in r or "error" in r, r)
class DuplicateResultDev(Dev):
    def dump(self):
        return ('<hierarchy><node index="0" text="" class="android.widget.FrameLayout" package="com.google.android.apps.youtube.music" '
            'content-desc="" clickable="false" enabled="true" focused="false" scrollable="false" bounds="[0,0][1080,2400]">'
            '<node index="1" text="Love For You" class="android.widget.TextView" package="com.google.android.apps.youtube.music" '
                'content-desc="" clickable="true" enabled="true" focused="false" scrollable="false" bounds="[10,100][500,180]"/>'
            '<node index="2" text="Love For You" class="android.widget.TextView" package="com.google.android.apps.youtube.music" '
            'content-desc="" clickable="true" enabled="true" focused="false" scrollable="false" bounds="[10,220][500,300]"/>'
            '</node></hierarchy>')
dup_dev = DuplicateResultDev(); dup_agent = A.Agent(dup_dev, "m", vision=False)
r = dup_agent.tap_text({"text": "Love For You"})
check("resultado visual duplicado não toca no primeiro automaticamente", r.startswith("error:") and not any(c.startswith("input tap") for c in dup_dev.cmds), (r, dup_dev.cmds))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    A.show_result("[cwd /x] [exit 0]\nfoo\nbar")
check("show_result sem cabecalho [cwd]", "[cwd" not in buf.getvalue() and "foo" in buf.getvalue(), buf.getvalue())

# ---- 6) classificador
for t, k in [("pesquise na internet o preco do dolar", "terminal"), ("abra o youtube e procure lofi", "screen"),
             ("instale o python e rode o script", "terminal"), ("mande oi no whatsapp para a Ana", "screen"),
             ("quantos arquivos tem aqui", "terminal"), ("faca login no gov.br e emita o boleto", "screen")]:
    check(f"kind[{t[:40]}] = {k}", A.task_kind(t) == k, A.task_kind(t))

# ---- 7) loops and interruption cleanup
loop_agent = A.Agent(None, "m", vision=False)
cycle = [("tap A", "screen A", None, "tap"), ("back", "screen B", None, "back")] * 3
check("detecta ciclo repetido de ação e tela", loop_agent.detect_loop(cycle) == (2, ["tap A", "back"]))
progress = [("tap", f"screen {i}", None, "tap") for i in range(6)]
check("não acusa loop quando a tela progride", loop_agent.detect_loop(progress) is None)
cleaned = []
loop_agent._run = lambda task, limit: (_ for _ in ()).throw(KeyboardInterrupt())
loop_agent.safe_janitor = lambda: cleaned.append(True)
try:
    loop_agent.run("interromper", 1)
except KeyboardInterrupt:
    pass
check("Ctrl+C executa faxina e propaga interrupção", cleaned == [True])
print(f"\n{OK} verificacoes ok")
