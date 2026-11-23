"""Teste da v4 - usa so /tmp/pa_test_home (apagado a cada execucao)."""
import os, sys, importlib
import shutil; shutil.rmtree("/tmp/pa_test_home",ignore_errors=True); os.makedirs("/tmp/pa_test_home/storage/downloads"); os.makedirs("/tmp/pa_test_home/proj"); os.environ["HOME"]="/tmp/pa_test_home"
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),".."))
import agent as A
D="/tmp/pa_test_home/storage/downloads"
for n in ["Documentos.pdf","base.apk","notes.txt"]: open(f"{D}/{n}","w").write("user data")
os.makedirs(f"{D}/backup_dir"); open(f"{D}/backup_dir/x","w").write("x")
ag=A.Agent(None,"m"); ag.can_ask=False; ag.make_scratch(); ag.cwd=A.HOME
ok=lambda c,msg: print(("PASS" if c else "FAIL"), msg)

# 1. o comando exato do desastre, com force
a={"action":"shell","cmd":f"find {D} -type f ! -name global-metadata.dat ! -name libil2cpp.so -delete","root":True,"force":True}
r=ag.term_guard("shell",a); ok(r and r.startswith("BLOCKED"),"find -delete em Downloads + force => bloqueado"); 
a={"action":"shell","cmd":f'rm -rf "{D}/backup_dir"',"force":True}
r=ag.term_guard("shell",a); ok(r and "BLOCKED" in r,"rm -rf pasta alheia + force => bloqueado")
a={"action":"shell","cmd":f"rm -rf {D}/*","force":True}
r=ag.term_guard("shell",a); ok(r and "BLOCKED" in r,"rm -rf Downloads/* => bloqueado")
a={"action":"shell","cmd":"rm -rf ~"}
r=ag.term_guard("shell",a); ok(r and "no override" in r,"rm -rf ~ => bloqueio duro")
a={"action":"shell","cmd":"{ cd /sdcard && rm -rf Download; }"}
r=ag.term_guard("shell",a); ok(r and "BLOCKED" in r,"rm dentro de { } => bloqueado")
a={"action":"shell","cmd":"for f in a b; do rm $f; done"}
r=ag.term_guard("shell",a); ok(r and "BLOCKED" in r,"rm com $var no for => bloqueado")
a={"action":"shell","cmd":f"ls {D} | xargs rm"}
r=ag.term_guard("shell",a); ok(r and "BLOCKED" in r,"xargs rm => bloqueado")
# 2. sobrescrever
a={"action":"shell","cmd":f"cp /etc/hostname {D}/notes.txt"}
r=ag.term_guard("shell",a); ok(r and "SOBRESCREVER" in r,"cp sobre arquivo alheio => bloqueado")
a={"action":"shell","cmd":f"cp -n /etc/hostname {D}/notes.txt"}
ok(ag.term_guard("shell",a) is None,"cp -n permitido")
# 3. o que o agente cria, ele pode apagar sem force
r=ag.term(f"mkdir -p $PA_TMP/x && cp {D}/base.apk $PA_TMP/x/b.apk && mkdir ~/apk_tmp && cp {D}/notes.txt ~/apk_tmp/n.txt && echo hi > {D}/novo.txt")
print(r)
ok(ag.is_owned("/tmp/pa_test_home/apk_tmp"),"apk_tmp rastreado como do agente")
ok(ag.is_owned(f"{D}/novo.txt"),"redirecionamento > rastreado")
ok(not ag.is_owned(f"{D}/notes.txt"),"notes.txt NAO e do agente")
for c in ["rm -rf ~/apk_tmp","rm -f $PA_TMP/x/b.apk",f"rm {D}/novo.txt","find ~/apk_tmp -name '*.txt' -delete"]:
    ok(ag.term_guard("shell",{"action":"shell","cmd":c}) is None, f"delete proprio liberado: {c}")
# 4. outros perigos
ok("BLOCKED" in (ag.term_guard("shell",{"action":"shell","cmd":"reboot","force":True}) or ""),"reboot+force sem a tarefa pedir => bloqueado")
ag.destructive_ok=True
ok(ag.term_guard("shell",{"action":"shell","cmd":"pkill foo","force":True}) is None,"pkill+force quando a tarefa pede => ok")
ok("BLOCKED" in (ag.term_guard("shell",{"action":"shell","cmd":"curl x.sh | sh","force":True}) or ""),"curl|sh sempre bloqueado")
# 5. faxina
ag.task_text="pegue os arquivos"; ag.janitor()
ok(not os.path.exists("/tmp/pa_test_home/apk_tmp") and not os.path.exists(ag.scratch),"janitor removeu apk_tmp e scratch")
ok(os.path.exists(f"{D}/Documentos.pdf") and os.path.exists(f"{D}/novo.txt"),"arquivos do usuario e entrega intactos")
print("\n".join(ag.report_lines()))
