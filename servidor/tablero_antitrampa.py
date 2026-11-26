# -*- coding: utf-8 -*-
"""tablero_antitrampa — EL TABLERO del antitrampa, en tiempo real (26-nov-2026).

    R2_TABLERO_PUERTO=8765                       el puerto (sin esto, NO arranca)
    R2_TABLERO_HOST=127.0.0.1                    dónde escucha (de fábrica sólo la PC del server: ponerlo detrás de
                                                 Caddy/un túnel si se quiere usar desde afuera; nunca directo a internet)
    R2_TABLERO_ADMINS="ana:clave-larga,beto:otra-clave"   quién entra (clave de 12 caracteres o más). Cada acción queda
                                                 en `antitrampa_acciones` con el nombre de quien la hizo.

Lo que se ve: jugadores conectados y el estado del antitrampa de cada uno (activo, sin antitrampa, callado, apagado),
las detecciones en vivo (cada 3 s, sólo lo nuevo), filtros por jugador / categoría / regla / fecha / riesgo / estado,
el historial de cada cuenta (faltas, suspensión, baneo, eventos, acciones), estadísticas, alertas críticas, el detalle
con la evidencia y el registro de acciones administrativas. Las acciones: revisar, confirmar, descartar (falso
positivo: perdona sus pendientes de la tanda), advertir, suspender, levantar la suspensión, banear y desbanear.

⛔ Seguridad: sesión con cookie HttpOnly + SameSite=Strict, token CSRF en cada POST, intentos de login con tope por IP,
   CSP con nonce, nada de `pass_hash` ni IPs en las respuestas. Todo dato del juego se pinta como TEXTO (sin innerHTML).
"""
import hmac
import json
import os
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .registro import log

SESION_S = 12 * 3600
_sesiones = {}                      # token -> {"admin", "csrf", "vence"}
_sesiones_lock = threading.Lock()
_intentos = {}                      # ip -> [time.time() de los fallos]
_INTENTOS_MAX, _INTENTOS_S = 8, 600


def admins():
    """{nombre: clave} de R2_TABLERO_ADMINS (las claves de menos de 12 caracteres no valen)."""
    out = {}
    for par in (os.environ.get("R2_TABLERO_ADMINS") or "").split(","):
        if ":" in par:
            n, c = par.split(":", 1)
            n, c = n.strip(), c.strip()
            if n and len(c) >= 12:
                out[n] = c
    return out


def _login(nombre, clave, ip):
    t = time.time()
    fallos = [x for x in _intentos.get(ip, []) if t - x < _INTENTOS_S]
    _intentos[ip] = fallos
    if len(fallos) >= _INTENTOS_MAX:
        return None, "demasiados intentos: espera unos minutos"
    esperada = admins().get(str(nombre or ""))
    if not esperada or not hmac.compare_digest(str(clave or ""), esperada):
        fallos.append(t)
        return None, "usuario o clave incorrectos"
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with _sesiones_lock:
        for k in [k for k, v in _sesiones.items() if v["vence"] < t]:
            _sesiones.pop(k, None)
        _sesiones[token] = {"admin": nombre, "csrf": csrf, "vence": t + SESION_S}
    from . import almacen
    try:
        almacen.at_accion(nombre, "entrar_tablero", detalle="")
    except Exception:                                                 # noqa: BLE001
        pass
    return (token, csrf), None


def _sesion(token):
    if not token:
        return None
    with _sesiones_lock:
        s = _sesiones.get(token)
        if s and s["vence"] > time.time():
            return s
        _sesiones.pop(token, None)
    return None


# ═══ LOS DATOS (también los usan las pruebas, sin HTTP) ═══════════════════════════════════════════════════════════
def conectados():
    """Los jugadores conectados ahora y el estado del antitrampa de cada uno."""
    from . import almacen, antitrampa
    from .salas import CONEXIONES
    out = []
    for usn, st in list(CONEXIONES.items()):
        if st is None or getattr(st, "cerrado", False):
            continue
        try:
            cuenta = almacen.cuenta_de_uid(usn)[0]
        except Exception:                                             # noqa: BLE001
            cuenta = None
        e = antitrampa.estado_de(usn)
        out.append({"usn": usn, "nick": antitrampa._nick(usn), "cuenta": cuenta, "sala": getattr(st, "room_id", None),
                    "jugando": bool(getattr(st, "at_go", None)), **e})
    out.sort(key=lambda x: (x.get("estado") == "activo", x.get("nick") or ""))
    return out


_FILTROS = ("jugador", "cuenta", "usn", "regla", "categoria", "riesgo", "riesgo_min", "estado", "desde", "hasta",
            "despues_de", "sesion", "evento")


def eventos(q, limite=200):
    from . import almacen
    filtros = {k: q[k] for k in _FILTROS if q.get(k)}
    filas = almacen.ev_listar(filtros, limite)
    for f in filas:
        try:
            f["evidencia"] = json.loads(f.get("evidencia") or "{}")
        except ValueError:
            pass
    return filas


def jugador(q):
    from . import almacen
    cuenta = q.get("cuenta")
    if not cuenta and q.get("usn"):
        cuenta = almacen.cuenta_de_uid(int(q["usn"]))[0]
    if not cuenta:
        return {"error": "no encuentro esa cuenta"}
    return {"resumen": almacen.ev_resumen_cuenta(cuenta), "eventos": eventos({"cuenta": cuenta}, 300),
            "acciones": almacen.at_acciones(100, cuenta=cuenta)}


def resumen():
    from . import almacen, antitrampa_eventos
    hoy = time.strftime("%Y-%m-%d")
    criticas = almacen.ev_listar({"riesgo_min": "alto", "estado": "nuevo"}, 50)
    return {"conectados": conectados(), "hoy": almacen.ev_estadisticas({"desde": hoy}),
            "total": almacen.ev_estadisticas({}), "alertas": criticas, "registro": antitrampa_eventos.estado_registro(),
            "categorias": antitrampa_eventos.categorias()}


def accion(admin, d):
    """Una acción del tablero. -> (ok, mensaje)."""
    from . import antitrampa_eventos as ev
    a = d.get("accion")
    evento, cuenta = d.get("evento") or None, d.get("cuenta") or None
    if evento and not cuenta:
        from . import almacen
        f = almacen.ev_listar({"evento": evento}, 1)
        cuenta = f[0]["cuenta"] if f else None
    if a in ("revisar", "confirmar"):
        return ev.revisar(admin, evento, "revisado" if a == "revisar" else "confirmado", d.get("nota"))
    if not cuenta:
        return False, "falta la cuenta"
    if a == "descartar":
        return ev.descartar(admin, evento=evento, cuenta=None if evento else cuenta, nota=d.get("nota"))
    if a == "advertir":
        return ev.advertir(admin, cuenta, d.get("texto"), evento)
    if a == "suspender":
        return ev.suspender(admin, cuenta, d.get("horas"), d.get("motivo", ""), evento)
    if a == "levantar":
        return ev.levantar(admin, cuenta)
    if a == "banear":
        return ev.banear(admin, cuenta, d.get("motivo", ""), evento)
    if a == "desbanear":
        return ev.desbanear(admin, cuenta)
    return False, f"acción desconocida: {a}"


# ═══ HTTP ══════════════════════════════════════════════════════════════════════════════════════════════════════════
class _Manejador(BaseHTTPRequestHandler):
    server_version = "tablero"

    def log_message(self, *_a):
        pass

    def _cookie(self):
        for parte in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = parte.strip().partition("=")
            if k == "at_sesion":
                return v
        return None

    def _json(self, codigo, obj, cookie=None):
        cuerpo = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        if url.path in ("/", "/index.html"):
            nonce = secrets.token_urlsafe(16)
            cuerpo = PAGINA.replace("{{NONCE}}", nonce).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{nonce}'; "
                             f"style-src 'nonce-{nonce}'; connect-src 'self'; img-src 'self' data:; "
                             "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        s = _sesion(self._cookie())
        if not s:
            return self._json(401, {"error": "sin sesión"})
        try:
            if url.path == "/api/yo":
                return self._json(200, {"admin": s["admin"], "csrf": s["csrf"]})
            if url.path == "/api/resumen":
                return self._json(200, resumen())
            if url.path == "/api/conectados":
                return self._json(200, conectados())
            if url.path == "/api/eventos":
                return self._json(200, eventos(q, int(q.get("limite") or 200)))
            if url.path == "/api/jugador":
                return self._json(200, jugador(q))
            if url.path == "/api/estadisticas":
                from . import almacen
                return self._json(200, almacen.ev_estadisticas({k: q[k] for k in _FILTROS if q.get(k)}))
            if url.path == "/api/acciones":
                from . import almacen
                return self._json(200, almacen.at_acciones(int(q.get("limite") or 200), cuenta=q.get("cuenta")))
            if url.path == "/api/catalogo":
                from .ajustes import ANTITRAMPA_CATEGORIAS, ANTITRAMPA_CLASIFICACION, ANTITRAMPA_REGLAS
                return self._json(200, {"categorias": ANTITRAMPA_CATEGORIAS, "reglas": {
                    r: {"accion": a, "categoria": ANTITRAMPA_CLASIFICACION[r][0], "riesgo": ANTITRAMPA_CLASIFICACION[r][1],
                        "confianza": ANTITRAMPA_CLASIFICACION[r][2], "origen": ANTITRAMPA_CLASIFICACION[r][3]}
                    for r, a in ANTITRAMPA_REGLAS.items()}})
        except Exception as e:                                         # noqa: BLE001
            log("TRAMP", f"  ⚠ tablero {url.path}: {e!r}")
            return self._json(500, {"error": "error interno"})
        return self._json(404, {"error": "no existe"})

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > 20000:
            return self._json(413, {"error": "demasiado grande"})
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(d, dict):
                raise ValueError
        except ValueError:
            return self._json(400, {"error": "JSON inválido"})
        if url.path == "/api/login":
            par, err = _login(d.get("usuario"), d.get("clave"), self.client_address[0])
            if not par:
                return self._json(403, {"error": err})
            token, csrf = par
            return self._json(200, {"admin": d.get("usuario"), "csrf": csrf},
                              cookie=f"at_sesion={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESION_S}")
        s = _sesion(self._cookie())
        if not s:
            return self._json(401, {"error": "sin sesión"})
        if not hmac.compare_digest(self.headers.get("X-CSRF") or "", s["csrf"]):
            return self._json(403, {"error": "falta el token CSRF"})
        if url.path == "/api/salir":
            with _sesiones_lock:
                _sesiones.pop(self._cookie(), None)
            return self._json(200, {"ok": True}, cookie="at_sesion=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        if url.path == "/api/accion":
            try:
                ok, msj = accion(s["admin"], d)
            except Exception as e:                                     # noqa: BLE001
                log("TRAMP", f"  ⚠ tablero acción {d.get('accion')}: {e!r}")
                return self._json(500, {"error": "error interno"})
            log("TRAMP", f"  🛡 tablero: {s['admin']} {d.get('accion')} {d.get('cuenta') or d.get('evento')}: {msj}")
            return self._json(200 if ok else 400, {"ok": ok, "mensaje": msj})
        return self._json(404, {"error": "no existe"})


def arrancar(puerto=None, host=None):
    """Arranca el tablero (sólo con R2_TABLERO_PUERTO y al menos un admin en R2_TABLERO_ADMINS). -> el server o None.
    `puerto=0` explícito (las pruebas) = un puerto libre cualquiera."""
    if puerto is None:
        puerto = int(os.environ.get("R2_TABLERO_PUERTO") or 0)
        if not puerto:
            log("MAIN", "tablero del antitrampa: apagado (sin R2_TABLERO_PUERTO)")
            return None
    if not admins():
        log("MAIN", "⚠ tablero del antitrampa: R2_TABLERO_PUERTO sin R2_TABLERO_ADMINS (nombre:clave de 12+): no arranca")
        return None
    host = host or os.environ.get("R2_TABLERO_HOST") or "127.0.0.1"
    srv = ThreadingHTTPServer((host, puerto), _Manejador)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="tablero-antitrampa").start()
    log("MAIN", f"tablero del antitrampa: http://{host}:{srv.server_address[1]}/ ({len(admins())} admin(s))")
    return srv


PAGINA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tablero antitrampa</title>
<style nonce="{{NONCE}}">
:root{--f:#0f1218;--p:#171b24;--p2:#1f2430;--t:#e6e9ef;--s:#9aa3b2;--a:#ff2e88;--b:#2d3340;
 --info:#6b7280;--bajo:#3b82f6;--medio:#eab308;--alto:#f97316;--critico:#ef4444;--ok:#22c55e}
*{box-sizing:border-box}body{margin:0;background:var(--f);color:var(--t);font:14px/1.45 system-ui,Segoe UI,sans-serif}
header{display:flex;gap:12px;align-items:center;padding:10px 16px;background:var(--p);border-bottom:1px solid var(--b);flex-wrap:wrap}
header h1{font-size:16px;margin:0;color:var(--a)}nav{display:flex;gap:4px;flex-wrap:wrap}
nav button,.btn{background:var(--p2);color:var(--t);border:1px solid var(--b);border-radius:6px;padding:6px 10px;cursor:pointer;font:inherit}
nav button.on{border-color:var(--a);color:var(--a)}.btn:hover,nav button:hover{border-color:var(--s)}
.btn.rojo{border-color:var(--critico);color:#fecaca}.btn.verde{border-color:var(--ok)}
main{padding:14px 16px;max-width:1400px;margin:0 auto}.oculto{display:none!important}
.tarjetas{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin-bottom:14px}
.tarjeta{background:var(--p);border:1px solid var(--b);border-radius:8px;padding:10px}.tarjeta b{font-size:22px;display:block}
.tarjeta span{color:var(--s);font-size:12px}
table{width:100%;border-collapse:collapse;background:var(--p);border:1px solid var(--b);border-radius:8px;overflow:hidden}
th,td{padding:6px 8px;border-bottom:1px solid var(--b);text-align:left;vertical-align:top}th{color:var(--s);font-weight:600;font-size:12px}
tr.clic{cursor:pointer}tr.clic:hover{background:var(--p2)}tr.nuevo td{animation:luz 2s}
@keyframes luz{from{background:#3a1d2c}to{background:transparent}}
.r{display:inline-block;padding:1px 7px;border-radius:10px;font-size:12px;color:#111;font-weight:600}
.r-informativo{background:var(--info);color:#fff}.r-bajo{background:var(--bajo);color:#fff}.r-medio{background:var(--medio)}
.r-alto{background:var(--alto)}.r-critico{background:var(--critico);color:#fff}
.est{font-size:12px;color:var(--s)}.est-activo{color:var(--ok)}.est-callado,.est-apagado{color:var(--critico)}.est-sin_antitrampa{color:var(--medio)}
.filtros{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
input,select,textarea{background:var(--p2);color:var(--t);border:1px solid var(--b);border-radius:6px;padding:6px 8px;font:inherit}
.panel{background:var(--p);border:1px solid var(--b);border-radius:8px;padding:12px;margin-bottom:12px}
pre{background:#0b0d12;border:1px solid var(--b);border-radius:6px;padding:10px;overflow:auto;max-height:320px;white-space:pre-wrap;word-break:break-all}
.dos{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:800px){.dos{grid-template-columns:1fr}}
.barra{height:8px;background:var(--a);border-radius:4px}.fila{display:flex;gap:8px;align-items:center;margin:3px 0}
.fila .n{width:220px;color:var(--s);font-size:12px}.fila .v{flex:1}#msj{min-height:20px;color:var(--medio)}
dialog{background:var(--p);color:var(--t);border:1px solid var(--b);border-radius:10px;max-width:900px;width:95%}
dialog::backdrop{background:#000a}.acciones{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.titulo{color:var(--a)}#entrar{max-width:340px;margin:12vh auto;display:flex;flex-direction:column;gap:8px}
</style></head><body>
<form id="entrar" class="panel"><h1 class="titulo">Tablero antitrampa</h1>
<input id="u" placeholder="usuario" autocomplete="username" required>
<input id="c" type="password" placeholder="clave" autocomplete="current-password" required>
<button class="btn">Entrar</button><div id="err" class="est"></div></form>
<div id="app" class="oculto">
<header><h1>Antitrampa</h1><nav id="nav">
<button data-v="vivo" class="on">En vivo</button><button data-v="conectados">Conectados</button>
<button data-v="eventos">Detecciones</button><button data-v="estad">Estadísticas</button>
<button data-v="acciones">Acciones admin</button></nav>
<span class="est" id="yo"></span><button class="btn" id="salir">Salir</button><span id="msj"></span></header>
<main>
<section id="v-vivo"><div class="tarjetas" id="tarj"></div>
<div class="panel"><b>Alertas críticas sin revisar</b> <span class="est">(riesgo alto o crítico)</span><table><thead><tr>
<th>Cuándo</th><th>Jugador</th><th>Regla</th><th>Riesgo</th><th>Conf.</th><th>Descripción</th></tr></thead><tbody id="alertas"></tbody></table></div>
<div class="panel"><b>Detecciones en tiempo real</b> <span class="est" id="vivo-est"></span><table><thead><tr>
<th>Cuándo</th><th>Jugador</th><th>Categoría</th><th>Regla</th><th>Riesgo</th><th>Conf.</th><th>Origen</th><th>Rep.</th><th>Estado</th></tr></thead>
<tbody id="vivo"></tbody></table></div></section>
<section id="v-conectados" class="oculto"><table><thead><tr><th>Jugador</th><th>Cuenta</th><th>Antitrampa</th><th>Versión</th>
<th>Último latido</th><th>Reloj</th><th>Perdidos</th><th>Retenido</th><th>Reglas en la sesión</th></tr></thead><tbody id="con"></tbody></table></section>
<section id="v-eventos" class="oculto"><div class="filtros">
<input id="f-jugador" placeholder="jugador (apodo, cuenta o usn)"><select id="f-categoria"><option value="">toda categoría</option></select>
<select id="f-riesgo"><option value="">todo riesgo</option><option value="bajo">bajo o más</option><option value="medio">medio o más</option>
<option value="alto">alto o más</option><option value="critico">crítico</option></select>
<select id="f-estado"><option value="">todo estado</option><option>nuevo</option><option>revisado</option><option>confirmado</option>
<option>descartado</option><option>sancionado</option></select>
<input id="f-desde" type="date"><input id="f-hasta" type="date"><button class="btn" id="buscar">Buscar</button></div>
<table><thead><tr><th>Cuándo</th><th>Jugador</th><th>Categoría</th><th>Regla</th><th>Riesgo</th><th>Conf.</th><th>Origen</th>
<th>Reinc.</th><th>Rep.</th><th>Estado</th></tr></thead><tbody id="evs"></tbody></table></section>
<section id="v-estad" class="oculto"><div class="dos"><div class="panel"><b>Por categoría</b><div id="e-cat"></div></div>
<div class="panel"><b>Por riesgo</b><div id="e-riesgo"></div></div><div class="panel"><b>Por regla</b><div id="e-regla"></div></div>
<div class="panel"><b>Por día (30)</b><div id="e-dia"></div></div><div class="panel"><b>Por estado de revisión</b><div id="e-estado"></div></div>
<div class="panel"><b>Por origen</b> <span class="est">servidor = comprobado por el server · cliente = lo declara la dll</span><div id="e-origen"></div></div></div></section>
<section id="v-acciones" class="oculto"><table><thead><tr><th>Cuándo</th><th>Admin</th><th>Acción</th><th>Cuenta</th><th>Detalle</th></tr></thead>
<tbody id="acc"></tbody></table></section>
</main></div>
<dialog id="dlg"><div id="dlg-c"></div><div class="acciones"><button class="btn" id="dlg-x">Cerrar</button></div></dialog>
<script nonce="{{NONCE}}">
"use strict";
let CSRF="",ULT=0,CAT={},VISTA="vivo";
const $=id=>document.getElementById(id);
function el(t,txt,cls){const e=document.createElement(t);if(txt!==undefined&&txt!==null)e.textContent=String(txt);if(cls)e.className=cls;return e}
function riesgo(r){return el("span",r,"r r-"+r)}
function fila(celdas,cls){const tr=el("tr",null,cls||"");for(const c of celdas){const td=el("td");if(c instanceof Node)td.appendChild(c);else td.textContent=c==null?"":String(c);tr.appendChild(td)}return tr}
async function api(ruta,cuerpo){const o={headers:{}};if(cuerpo){o.method="POST";o.headers["Content-Type"]="application/json";o.headers["X-CSRF"]=CSRF;o.body=JSON.stringify(cuerpo)}
 const r=await fetch(ruta,o);if(r.status===401){$("app").classList.add("oculto");$("entrar").classList.remove("oculto");throw new Error("sin sesión")}
 const d=await r.json();if(!r.ok&&!cuerpo)throw new Error(d.error||r.status);return d}
function msj(t){$("msj").textContent=t;setTimeout(()=>{if($("msj").textContent===t)$("msj").textContent=""},6000)}
$("entrar").addEventListener("submit",async e=>{e.preventDefault();const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({usuario:$("u").value,clave:$("c").value})});
 const d=await r.json();if(!r.ok){$("err").textContent=d.error;return}CSRF=d.csrf;iniciar(d.admin)});
$("salir").addEventListener("click",async()=>{await api("/api/salir",{});location.reload()});
for(const b of $("nav").querySelectorAll("button"))b.addEventListener("click",()=>ver(b.dataset.v));
function ver(v){VISTA=v;for(const b of $("nav").querySelectorAll("button"))b.classList.toggle("on",b.dataset.v===v);
 for(const s of document.querySelectorAll("main>section"))s.classList.toggle("oculto",s.id!=="v-"+v);cargar()}
function jug(e){return (e.nick||"")+(e.cuenta?" ("+e.cuenta+")":e.usn?" (usn "+e.usn+")":"")}
function filaEvento(e,nuevo,completa){const c=[e.cuando,jug(e),CAT[e.categoria]||e.categoria,e.regla,riesgo(e.riesgo),e.confianza+"%",e.origen];
 if(completa)c.push(e.reincidencias);c.push(e.repeticiones,e.estado);const tr=fila(c,"clic"+(nuevo?" nuevo":""));tr.addEventListener("click",()=>detalle(e));return tr}
async function cargar(){try{
 if(VISTA==="vivo"){const d=await api("/api/resumen");CAT=d.categorias||CAT;tarjetas(d);
  const a=$("alertas");a.textContent="";for(const e of d.alertas)a.appendChild(fila([e.cuando,jug(e),e.regla,riesgo(e.riesgo),e.confianza+"%",e.descripcion],"clic")).addEventListener("click",()=>detalle(e));
  const n=await api("/api/eventos?limite=60"+(ULT?"&despues_de="+ULT:""));const t=$("vivo");
  for(const e of n.reverse()){t.insertBefore(filaEvento(e,ULT>0),t.firstChild);ULT=Math.max(ULT,e.id)}
  while(t.children.length>200)t.removeChild(t.lastChild);
  $("vivo-est").textContent="registro: "+(d.registro.vivo?"vivo":"PARADO")+" · en cola "+d.registro.en_cola+(d.registro.perdidos?" · perdidos "+d.registro.perdidos:"")}
 else if(VISTA==="conectados"){const d=await api("/api/conectados");const t=$("con");t.textContent="";
  for(const j of d){const est=el("span",j.estado,"est est-"+j.estado);const tr=fila([j.nick+" ("+j.usn+")",j.cuenta,est,j.version?("v"+j.version+(j.dll?" · "+j.dll:"")):"—",
   j.latido_hace_s==null?"—":j.latido_hace_s+" s",j.reloj==null?"—":Math.round(j.reloj*100)+"%",j.perdidos||0,j.retenido?"sí":"no",(j.reglas||[]).join(", ")],"clic");
   tr.addEventListener("click",()=>jugador(j.cuenta));t.appendChild(tr)}}
 else if(VISTA==="eventos")buscar();
 else if(VISTA==="estad"){const s=await api("/api/estadisticas");barras("e-cat",s.categoria,CAT);barras("e-riesgo",s.riesgo);barras("e-regla",s.regla);barras("e-dia",s.dia);barras("e-estado",s.estado);barras("e-origen",s.origen)}
 else if(VISTA==="acciones"){const d=await api("/api/acciones");const t=$("acc");t.textContent="";for(const a of d)t.appendChild(fila([a.cuando,a.admin,a.accion,a.cuenta,a.detalle]))}
}catch(e){if(e.message!=="sin sesión")msj("error: "+e.message)}}
function tarjetas(d){const t=$("tarj");t.textContent="";const c=d.conectados;
 const datos=[["conectados",c.length],["sin antitrampa",c.filter(x=>x.estado==="sin_antitrampa").length],["antitrampa callado",c.filter(x=>x.estado==="callado"||x.estado==="apagado").length],
 ["detecciones hoy",d.hoy.total],["cuentas hoy",d.hoy.cuentas],["alertas críticas",d.alertas.length],["detecciones (total)",d.total.total]];
 for(const [n,v] of datos){const k=el("div",null,"tarjeta");k.appendChild(el("b",v));k.appendChild(el("span",n));t.appendChild(k)}}
function barras(id,obj,nombres){const c=$(id);c.textContent="";const ent=Object.entries(obj||{}).sort((a,b)=>b[1]-a[1]);const max=Math.max(1,...ent.map(x=>x[1]));
 for(const [k,v] of ent){const f=el("div",null,"fila");f.appendChild(el("div",(nombres&&nombres[k])||k,"n"));const w=el("div",null,"v");const b=el("div",null,"barra");b.style.width=(100*v/max)+"%";w.appendChild(b);f.appendChild(w);f.appendChild(el("div",v));c.appendChild(f)}
 if(!ent.length)c.appendChild(el("div","sin datos","est"))}
async function buscar(){const p=new URLSearchParams({limite:"300"});for(const k of ["jugador","categoria","estado","desde","hasta"]){const v=$("f-"+k).value;if(v)p.set(k,v)}
 const r=$("f-riesgo").value;if(r)p.set("riesgo_min",r);const d=await api("/api/eventos?"+p);const t=$("evs");t.textContent="";for(const e of d)t.appendChild(filaEvento(e,false,true))}
$("buscar").addEventListener("click",buscar);
function botones(cont,e,cuenta){const acc=el("div",null,"acciones");
 const b=(txt,cls,f)=>{const x=el("button",txt,"btn "+(cls||""));x.addEventListener("click",f);acc.appendChild(x)};
 const hacer=async(c)=>{const d=await api("/api/accion",c);msj((d.ok?"✔ ":"✖ ")+(d.mensaje||d.error));$("dlg").close();cargar()};
 if(e){b("Revisado","",()=>hacer({accion:"revisar",evento:e.evento}));b("Confirmar","",()=>hacer({accion:"confirmar",evento:e.evento}));
  b("Falso positivo","verde",()=>{const n=prompt("Nota (por qué es falso positivo):","");if(n!==null)hacer({accion:"descartar",evento:e.evento,nota:n})})}
 if(cuenta){b("Advertir","",()=>{const t=prompt("Aviso al jugador (sin detalles técnicos):","");if(t!==null)hacer({accion:"advertir",cuenta,evento:e&&e.evento,texto:t||undefined})});
  b("Suspender","rojo",()=>{const h=prompt("¿Cuántas horas?","24");if(!h)return;const m=prompt("Motivo:","");if(m!==null)hacer({accion:"suspender",cuenta,evento:e&&e.evento,horas:h,motivo:m})});
  b("Levantar suspensión","",()=>hacer({accion:"levantar",cuenta}));
  b("Banear","rojo",()=>{const m=prompt("BANEO PERMANENTE de "+cuenta+". Motivo:","");if(m)hacer({accion:"banear",cuenta,evento:e&&e.evento,motivo:m})});
  b("Desbanear","",()=>{if(confirm("¿Desbanear "+cuenta+"?"))hacer({accion:"desbanear",cuenta})});
  b("Historial","",()=>jugador(cuenta))}
 cont.appendChild(acc)}
function detalle(e){const c=$("dlg-c");c.textContent="";c.appendChild(el("h3",e.regla+" · "+jug(e)));
 const t=el("table");for(const [k,v] of [["evento",e.evento],["cuándo",e.cuando+(e.ultimo&&e.ultimo!==e.cuando?" (último "+e.ultimo+")":"")],["categoría",CAT[e.categoria]||e.categoria],
  ["riesgo / confianza",e.riesgo+" / "+e.confianza+"%"],["origen",e.origen+" · módulo "+e.modulo],["descripción",e.descripcion],["sesión / partida",(e.sesion||"—")+" / "+(e.partida||"—")],
  ["reincidencias / repeticiones",e.reincidencias+" / "+e.repeticiones],["versiones",(e.version_cliente||"—")+" · "+(e.version_antitrampa||"—")],["acción del server",e.accion+(e.pendiente?" (pendiente #"+e.pendiente+")":"")],
  ["estado",e.estado+(e.revisado_por?" por "+e.revisado_por+" "+(e.revisado_cuando||""):"")+(e.nota?" · "+e.nota:"")]])t.appendChild(fila([k,v]));
 c.appendChild(t);c.appendChild(el("h4","Evidencia"));c.appendChild(el("pre",JSON.stringify(e.evidencia,null,2)));
 if(e.origen==="cliente")c.appendChild(el("div","⚠ Lo declara la dll del cliente: por sí solo no prueba la trampa. Mirar si hay detecciones del servidor que lo confirmen.","est"));
 botones(c,e,e.cuenta);$("dlg").showModal()}
async function jugador(cuenta){if(!cuenta){msj("sin cuenta");return}const d=await api("/api/jugador?cuenta="+encodeURIComponent(cuenta));if(d.error){msj(d.error);return}
 const c=$("dlg-c");c.textContent="";const r=d.resumen;c.appendChild(el("h3","Cuenta "+cuenta));
 c.appendChild(el("div","Faltas de la escalera: "+(r.faltas?r.faltas.faltas+" (última: "+r.faltas.ultima_regla+", "+r.faltas.ultima+")":"0")+" · pendientes para la tanda: "+r.pendientes
  +" · "+(r.baneada?"BANEADA":r.suspension?"suspendida hasta "+r.suspension.hasta+" ("+(r.suspension.motivo||"")+")":"activa")));
 botones(c,null,cuenta);const t=el("table");t.appendChild(fila(["Cuándo","Regla","Riesgo","Conf.","Rep.","Estado","Descripción"]));
 for(const e of d.eventos){const tr=fila([e.cuando,e.regla,riesgo(e.riesgo),e.confianza+"%",e.repeticiones,e.estado,e.descripcion],"clic");tr.addEventListener("click",()=>detalle(e));t.appendChild(tr)}
 c.appendChild(el("h4","Detecciones ("+d.eventos.length+")"));c.appendChild(t);
 const a=el("table");for(const x of d.acciones)a.appendChild(fila([x.cuando,x.admin,x.accion,x.detalle]));c.appendChild(el("h4","Acciones sobre esta cuenta"));c.appendChild(a);
 if(!$("dlg").open)$("dlg").showModal()}
$("dlg-x").addEventListener("click",()=>$("dlg").close());
async function iniciar(admin){$("entrar").classList.add("oculto");$("app").classList.remove("oculto");$("yo").textContent=admin;
 const cat=await api("/api/catalogo");CAT=cat.categorias;const s=$("f-categoria");for(const [k,v] of Object.entries(CAT))s.appendChild(new Option(v,k));
 cargar();setInterval(()=>{if(VISTA==="vivo"||VISTA==="conectados")cargar()},3000)}
(async()=>{try{const d=await api("/api/yo");CSRF=d.csrf;iniciar(d.admin)}catch(e){}})();
</script></body></html>
"""
