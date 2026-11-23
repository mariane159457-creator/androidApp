"""Testa o autostart/stop do Ollama com um binario falso (nao toca no seu Ollama real; porta 11999)."""
import os, sys, subprocess, time, shutil
os.environ["HOME"]="/tmp/pa_test_h5"; shutil.rmtree("/tmp/pa_test_h5",ignore_errors=True); os.makedirs("/tmp/pa_test_h5")
os.environ["OLLAMA_HOST"]="127.0.0.1:11999"; HERE=os.path.dirname(os.path.abspath(__file__)); os.makedirs("/tmp/pa_fakebin",exist_ok=True); shutil.copy(HERE+"/fake_ollama","/tmp/pa_fakebin/ollama"); os.environ["PATH"]="/tmp/pa_fakebin:"+os.environ["PATH"]
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),".."))
import agent as A
ok=lambda c,m: print(("PASS" if c else "FAIL"),m)
ok(A.HOST=="http://127.0.0.1:11999","HOST sem http:// normalizado")
ok(not A.ollama_up(1),"comeca desligado")
r=A.ensure_ollama(); print(r); ok(r[0] and "iniciado" in r[1] and A.ollama_up(),"sobe sozinho")
pid=int(open(A.RUN_DIR+"/ollama.pid").read())
kids=subprocess.run(["pgrep","-g",str(pid)],capture_output=True,text=True).stdout.split(); ok(len(kids)>=2,f"servidor + filho no mesmo grupo {kids}")
# 2a instancia viva usando
other=subprocess.Popen(["sleep","30"]); open(f"{A.RUN_DIR}/users/{other.pid}","w").close()
A._stop_ollama_if_last(); ok(A.ollama_up(),"outra instancia viva => NAO derruba")
other.kill(); other.wait()
A._stop_ollama_if_last(); time.sleep(0.5)
ok(not A.ollama_up(1),"ultima a sair => derruba"); 
ok(subprocess.run(["pgrep","-g",str(pid)],capture_output=True).returncode!=0,"filho tambem morreu")
ok(not os.path.exists(A.RUN_DIR+"/ollama.pid"),"pid file limpo")
# Interrupt the grace-period wait: the owned process group must still be killed and bookkeeping removed.
r=A.ensure_ollama(); ok(r[0] and "iniciado" in r[1],"reinicia instancia propria para teste de Ctrl+C")
pid=int(open(A.RUN_DIR+"/ollama.pid").read())
real_sleep=time.sleep
def interrupt_wait(_): raise KeyboardInterrupt()
A.time.sleep=interrupt_wait
try:
	A._stop_ollama_if_last()
finally:
	A.time.sleep=real_sleep
ok(not A.ollama_up(1),"Ctrl+C durante espera nao deixa Ollama proprio orfao")
ok(not os.path.exists(A.RUN_DIR+"/ollama.pid"),"Ctrl+C limpa pid file")
# ja rodando por conta do usuario: nao e nosso, nao derruba
srv=subprocess.Popen(["ollama","serve"],start_new_session=True); time.sleep(1.5)
r=A.ensure_ollama(); ok(r==(True,"ja estava rodando"),"ja rodando => reutiliza")
A._stop_ollama_if_last(); ok(A.ollama_up(),"Ollama do usuario NAO e derrubado")
import signal; os.killpg(srv.pid,signal.SIGKILL)
# keep / sem autostart / binario ausente
time.sleep(.5); r=A.ensure_ollama(autostart=False); ok(not r[0],"--no-ollama-start respeita")
os.environ["PATH"]="/usr/bin:/bin"; r=A.ensure_ollama(); print(r); ok(not r[0] and "pkg install ollama" in r[1],"sem binario => mensagem clara")
