"""Regressoes para o contrato textual, sem root e sem acesso a apps/tela/audio."""
import os
import subprocess
import sys
import tempfile

HOME = tempfile.mkdtemp(prefix="pa_text_only_")
os.environ["HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent as A


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    if not condition:
        raise SystemExit(1)


class Dev:
    su = None

    def sh(self, command, **kwargs):
        raise AssertionError(f"acao bloqueada executou shell: {command}")

    def argv(self, command):
        return ["sh", "-c", command]


agent = A.Agent(Dev(), "text-model", vision=False)
check("tarefas sobre apps continuam no modo terminal", A.task_kind("abra o YouTube") == "terminal")
check("prompt usa contrato text-only", "Never use root" in agent.prompt_for("abra um app"))
check("prompt nao oferece captura de audio", "play_and_read {" not in agent.prompt_for("tarefa"))
check("TermuxDevice nao usa su", A.TermuxDevice.argv(None, "id") == ["sh", "-c", "id"])
real_geteuid = A.os.geteuid
A.os.geteuid = lambda: 0
try:
    try:
        A.TermuxDevice()
        rejected_root_process = False
    except RuntimeError:
        rejected_root_process = True
finally:
    A.os.geteuid = real_geteuid
check("recusa iniciar com UID 0", rejected_root_process)

for command in ("su -c id", "sudo id", "tsu id"):
    result = agent.term_guard("shell", {"cmd": command, "force": True})
    check(f"bloqueia escalada: {command}", bool(result and result.startswith("BLOCKED")))
check("root:true bloqueado mesmo com force", agent.term_guard("shell", {"cmd": "id", "root": True, "force": True}).startswith("BLOCKED"))
check("execucao privilegiada bloqueada diretamente", agent.term("id", root=True).startswith("BLOCKED"))
check("captura direta de audio bloqueada", agent.capture_audio(None).startswith("BLOCKED"))

for action in ("listen", "play_and_read", "tap", "open_app", "open_url", "send_file", "device", "set_alarm"):
    result = agent.act({"action": action})
    check(f"acao {action} bloqueada", result.startswith("BLOCKED"))

help_text = subprocess.run(
    [sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent.py"), "--help"],
    capture_output=True, text=True, check=True,
).stdout
check("CLI nao expoe flags de voz ou visao", all(flag not in help_text for flag in ("--test-audio", "--audio-lang", "--vision")))
print("\nContrato text-only validado.")
