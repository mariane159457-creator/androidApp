"""Teste da v4 - usa so /tmp/pa_test_home (apagado a cada execucao)."""
import os, sys, json
import shutil; shutil.rmtree("/tmp/pa_test_home",ignore_errors=True); os.makedirs("/tmp/pa_test_home/storage/downloads"); os.makedirs("/tmp/pa_test_home/proj"); os.environ["HOME"]="/tmp/pa_test_home"; os.environ["NO_ANIM"]="1"
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),".."))
import agent as A
D="/tmp/pa_test_home/storage/downloads"; SRC="/tmp/pa_test_home/fakeapp"
os.makedirs(SRC,exist_ok=True); open(f"{SRC}/libil2cpp.so","w").write("ELF"); open(f"{SRC}/global-metadata.dat","w").write("META")
for n in ["Documentos.pdf","base.apk","backup.zip"]: open(f"{D}/{n}","w").write("DADOS DO USUARIO")
open("/tmp/pa_test_home/proj/PHONEAGENT.md","w").write("Entregas finais sempre em ~/storage/downloads/")
S=[]
steps=[
 {"thought":"extrair","action":"shell","cmds":["mkdir -p $PA_TMP/ex","cp "+SRC+"/* $PA_TMP/ex/","ls -l $PA_TMP/ex"],"done_goals":[1]},
 {"thought":"entregar","action":"shell","cmd":f"cp $PA_TMP/ex/libil2cpp.so $PA_TMP/ex/global-metadata.dat {D}/"},
 {"thought":"limpar tudo (BUG do modelo)","action":"shell","cmd":f"find {D} -type f ! -name global-metadata.dat ! -name libil2cpp.so -delete","force":True},
 {"thought":"mkdir sujo","action":"shell","cmd":"mkdir -p ~/apk_tmp && cp "+SRC+"/libil2cpp.so ~/apk_tmp/"},
 {"thought":"blefe","action":"done","message":"tudo pronto","deliverables":[D+"/libil2cpp.so",D+"/arquivo_que_nao_existe.dat"]},
 {"thought":"agora certo","action":"done","message":"copiei os 2","deliverables":[D+"/libil2cpp.so",D+"/global-metadata.dat"]},
]
seen=[]
def fake(path, body=None, timeout=0):
    m=body["messages"][-1]["content"]
    if "Plan the TASK" in m:
        return {"message":{"content":json.dumps({"goals":["copiar os 2 arquivos para Downloads"],"constraints":["nao deixar arquivos soltos (so os MEUS temporarios)"],"deliverables":["libil2cpp.so e global-metadata.dat em Downloads"],"question":None})}}
    if "QA auditor" in m:
        seen.append(("audit",m)); return {"message":{"content":json.dumps({"complete":True,"missing":[]})}}
    seen.append(("step",body["messages"][0]["content"][:30],m,body.get("think")))
    return {"message":{"content":json.dumps(steps.pop(0))}}
A.ollama=fake
class Dev:
    su=None
    def sh(self,c,**k): return ""
    def argv(self,c): return ["sh","-c",c]
os.chdir("/tmp/pa_test_home/proj")
ag=A.Agent(Dev(),"mock-model",vision=False,delay=1.0,home=False); ag.mode="terminal"; ag.can_ask=False; ag.notify_on=False
import time; t=time.time()
ok=ag.run("pegue libil2cpp.so e global-metadata.dat e coloque em Downloads, nao faca bagunca nem deixe arquivos soltos",0)
print("\nRESULT ok=",ok,"tempo=%.1fs"%(time.time()-t))
ls=sorted(os.listdir(D)); print("Downloads:",ls)
assert ok and set(["Documentos.pdf","base.apk","backup.zip","libil2cpp.so","global-metadata.dat"])<=set(ls), "ARQUIVOS DO USUARIO FORAM TOCADOS"
assert not os.path.exists("/tmp/pa_test_home/apk_tmp"), "apk_tmp ficou"
assert not any(d.startswith("run-") for d in os.listdir(A.WORK)), "scratch ficou"
print("sistema do 1o passo:",seen[0][1],"| think:",[x[3] for x in seen if x[0]=="step"])
u=seen[0][2]; print("ENV no prompt:", "WORKING DIRECTORY: /tmp/pa_test_home/proj" in u, "PHONEAGENT" in u, "CONSTRAINTS" in u, "FILES HERE" in u)
