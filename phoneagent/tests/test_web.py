"""Teste da v4 - usa so /tmp/pa_test_home (apagado a cada execucao)."""
import os, sys, threading, http.server, socketserver, hashlib
import shutil; shutil.rmtree("/tmp/pa_test_home",ignore_errors=True); os.makedirs("/tmp/pa_test_home/storage/downloads"); os.makedirs("/tmp/pa_test_home/proj"); os.environ["HOME"]="/tmp/pa_test_home"
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),".."))
import agent as A
ok=lambda c,m: print(("PASS" if c else "FAIL"),m)
BIN=os.urandom(3_000_000)
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path=="/page":
            b=b'<html><head><title>x</title><style>.a{}</style></head><body><nav>menu</nav><h1>Releases</h1><p>Baixe <a href="/files/tool.zip">tool.zip</a> agora</p><script>bad()</script></body></html>'
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.end_headers(); self.wfile.write(b)
        elif self.path.startswith("/files/"):
            rng=self.headers.get("Range")
            start=int(rng.split("=")[1].split("-")[0]) if rng else 0
            self.send_response(206 if rng else 200)
            self.send_header("Content-Type","application/zip")
            self.send_header("Content-Disposition",'attachment; filename="tool v1.zip"')
            self.send_header("Content-Length",str(len(BIN)-start)); self.end_headers(); self.wfile.write(BIN[start:])
        elif self.path=="/fake.apk":
            self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers(); self.wfile.write(b"<html>consent</html>")
        else: self.send_response(404); self.end_headers()
srv=socketserver.TCPServer(("127.0.0.1",0),H); port=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
B=f"http://127.0.0.1:{port}"
ag=A.Agent(None,"m"); ag.make_scratch(); ag.cwd="/tmp/pa_test_home/proj"
r=ag.web_fetch({"url":B+"/page","links":True}); print(r)
ok("Releases" in r and "bad()" not in r and "menu" not in r and f"{B}/files/tool.zip" in r,"web_fetch: texto limpo + links absolutos")
r=ag.download({"url":B+"/files/x","path":"/tmp/pa_test_home/proj/"}); print(r)
p="/tmp/pa_test_home/proj/tool v1.zip"
ok(os.path.exists(p) and hashlib.sha256(open(p,"rb").read()).hexdigest()==hashlib.sha256(BIN).hexdigest(),"download: nome do Content-Disposition, hash ok")
ok(ag.is_owned(p),"download registrado como do agente")
r=ag.download({"url":B+"/files/x","path":"/tmp/pa_test_home/proj/"}); ok("tool v1_1.zip" in r,"download nao sobrescreve (nome livre)")
r=ag.download({"url":B+"/fake.apk","path":"/tmp/pa_test_home/proj/"}); print(r); ok("PAGINA HTML" in r and not os.path.exists("/tmp/pa_test_home/proj/fake.apk"),"HTML disfarcado recusado e sem lixo")
r=ag.download({"url":B+"/nada","path":"/tmp/pa_test_home/proj/"}); ok("HTTP 404" in r,"404 tratado")
r=ag.download({"url":"file:///etc/passwd"}); ok(r.startswith("error"),"file:// recusado")
# retomada
part="/tmp/pa_test_home/proj/resume.zip.part"; open(part,"wb").write(BIN[:1000])
# (download_file reinicia por nome novo; testa Range direto)
import urllib.request
rq=urllib.request.Request(B+"/files/x",headers={"Range":"bytes=1000-"}); d=urllib.request.urlopen(rq).read(); ok(BIN[:1000]+d==BIN,"servidor de teste suporta Range")
# parsers de busca
ddg='''<div class="result"><h2 class="result__title"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fgithub.com%2Fx%2Fy&amp;rut=abc">X &amp; Y <b>tool</b></a></h2>
<a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fgithub.com%2Fx%2Fy">Great <b>tool</b> for apk</a></div>
<div class="result"><a class="result__a" href="https://example.org/two">Two</a><a class="result__snippet" href="x">second snippet</a></div>'''
res=A.parse_ddg(ddg); print(res)
ok(res[0]==("X & Y tool","https://github.com/x/y","Great tool for apk") and res[1][1]=="https://example.org/two","parse_ddg")
import base64
u="a1"+base64.urlsafe_b64encode(b"https://real.site/p").decode().rstrip("=")
bing=f'<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&amp;u={u}&amp;ntb=1">Real <strong>Site</strong></a></h2><p>desc here</p></li>'
res=A.parse_bing(bing); print(res); ok(res[0][1]=="https://real.site/p","parse_bing (url desembrulhada)")
