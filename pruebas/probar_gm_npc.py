#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_gm_npc — las cuentas «GM NPC» del Coordinador (`servidor/gm_npc.py`, 27-nov-2026).

Contra bases TEMPORALES (datos.db y panel.db), con Cuenta Eñeños de mentira:
    §1 crear: la cuenta, el apodo «GM-King», el traje PUESTO, las campanas, sin Rcoin, con licencia; a la auditoría
       a nombre del moderador y ⛔ sin la clave                 ⟲ un NPC que no existe: 400 y no se crea nada
    §2 la consola: SUS comandos sí                              ⟲ los de GM de más, los de desarrollo y el mismo
       jugador sin la marca, no; cada comando queda auditado
    §3 una sesión: cambiar de canal NO la cierra, irse SÍ; cerrada no entra; el apodo queda libre
                                                                 ⟲ un doble login (reemplazada) no la cierra
    §4 sin usar en `SIN_USAR_H` horas: vencida                   ⟲ un jugador cualquiera nunca está «cerrada»
    §5 los topes: la GM NPC no le suma a la IP del moderador      ⟲ una cuenta normal sí
    §6 la campana: la GM NPC no alimenta al antitrampa           ⟲ un jugador sí
    §7 la ruta del Coordinador: sin ficha 404; lista, crear, cerrar ⟲ cerrar una cuenta normal: 404
    §8 con `R2_LOGIN=pase`: la cuenta nace en Cuenta Eñeños (con el hash de la clave) y al cerrarse se le pide
       «baneada»                                                 ⟲ si Cuenta Eñeños la rechaza: 502 y nada en el juego
    §9 los enganches de `lobby.py` (que existen y en su lugar)

    python pruebas/probar_gm_npc.py
"""
import hashlib
import json
import os
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                # noqa: BLE001
    pass

_TMP = tempfile.mkdtemp(prefix="r2_gmnpc_")
os.environ["R2_BASE"] = os.path.join(_TMP, "datos.db")            # ⛔ ANTES de importar el server
os.environ["R2_LOG"] = os.path.join(_TMP, "servidor.log")
os.environ["R2_SESIONES"] = os.path.join(_TMP, "sesiones.json")
os.environ["R2_PANEL_DB"] = os.path.join(_TMP, "panel.db")
os.environ["R2_GM_ARCHIVO"] = os.path.join(_TMP, "gm.txt")
os.environ["R2_STREAMERS_ARCHIVO"] = os.path.join(_TMP, "streamers.txt")
os.environ["R2_CUENTAS_FICHA_INTERNA"] = "ficha-de-prueba"
for _v in ("R2_CONSOLA_GM", "R2_COMANDOS_TODOS", "R2_LOGIN"):
    os.environ.pop(_v, None)
open(os.environ["R2_GM_ARCHIVO"], "w").close()

try:
    from servidor import panel_admin                              # noqa: E402  (privado: el panel)
except ImportError:
    print("· se salta: la GM NPC usa el panel (`panel_admin`, privado), que este repo no trae")
    sys.exit(0)
from servidor import chat, gm_npc as G, lobby_campana, multicuenta, pase   # noqa: E402
from servidor.basedatos import cuenta_crear, db_get_char, hash_pass                    # noqa: E402
from servidor.misiones import db_create_char                                           # noqa: E402

FALLAS = []
MOD = "coordinador:moderadora"


def ok(cond, texto):
    print(("   ✅ " if cond else "   ❌ ") + texto)
    if not cond:
        FALLAS.append(texto)


class St:
    def __init__(self, usn, ip="10.20.30.41", **kw):
        self.usn, self.addr, self.room_id = usn, (ip, 5555), None
        self.__dict__.update(kw)

    def send_ff55(self, *a, **k):
        pass


class H:
    def __init__(self, ficha="ficha-de-prueba"):
        self.headers = {"X-Ficha-Interna": ficha, "X-Coordinador-Quien": MOD}
        self.path, self.r = "/", None

    def _mandar(self, cod, d, cache=None):
        self.r = (cod, d)
        return self.r


def auditoria(accion=None):
    q = "SELECT * FROM auditoria" + (" WHERE accion = ?" if accion else "") + " ORDER BY id"
    return [dict(r) for r in panel_admin._pdb().execute(q, (accion,) if accion else ()).fetchall()]


def inv(usn):
    return {(e["id"] if isinstance(e, dict) else e): (e.get("cant", 0) if isinstance(e, dict) else 0)
            for e in (db_get_char(usn) or {}).get("inventory") or []}


# ═══ §1 crear ═══
print("§1 · crear")
n_aud = len(auditoria())
cod, d = G.preparar("dragon", MOD)
ok(cod == 400 and not G.lista() and len(auditoria()) == n_aud, "⟲ un NPC que no existe: 400, sin cuenta ni auditoría")
cod, d = G.preparar("King", MOD)
ok(cod == 200 and d["usuario"].startswith("gmnpc_") and len(d["clave"]) >= 10 and d["nick"] == "GM-King",
   f"King: 200, usuario gmnpc_…, clave de {len(d.get('clave', ''))} y apodo {d.get('nick')!r}")
U1 = d["usn"]
CLAVE1 = d["clave"]
ch = db_get_char(U1)
ok(ch["char_id"] == 10110901 and int(ch.get("gender", 9)) == 0, "con el traje de King PUESTO (char_id) y de chico")
ok(10110901 in inv(U1) and all(inv(U1).get(i) == c for i, c in G.CAMPANAS), "el traje y las 4 campanas en el inventario")
ok(int(ch.get("rcoin", -1)) == 0 and int(ch.get("licencia", 0)) == G.LICENCIA, "sin Rcoin (no compra ni regala) y con licencia SOL")
a = auditoria("gmnpc/creada")
ok(len(a) == 1 and a[0]["actor_nick"] == MOD and a[0]["uid"] == U1 and a[0]["actor_uid"] == panel_admin.externo_uid(MOD),
   "la creación queda a nombre de la MODERADORA (su uid del Coordinador) sobre la cuenta GM NPC")
ok(CLAVE1 not in json.dumps(auditoria(), ensure_ascii=False) and CLAVE1 not in open(os.environ["R2_LOG"], encoding="utf-8").read()
   and CLAVE1 not in json.dumps(G.lista()), "⛔ la clave no está ni en la auditoría, ni en el log, ni en la lista")
cod, d2 = G.preparar("king", MOD)
ok(cod == 200 and d2["nick"] == "GM-King2", f"otra King mientras la 1ª sigue abierta: {d2.get('nick')!r}")
U2 = d2["usn"]
cod, d3 = G.preparar("sue", MOD)
ok(cod == 200 and db_get_char(d3["usn"])["char_id"] == 10120906 and int(db_get_char(d3["usn"])["gender"]) == 1,
   "Sue: el traje de chica y de chica")
U3 = d3["usn"]

# ═══ §2 la consola ═══
print("§2 · la consola")
S1 = St(U1)
G.al_entrar(S1, U1)
ok(G.de(S1) and G.de(S1)["usn"] == U1, "al entrar queda marcada la conexión")
for c in G.COMANDOS:
    ok(chat.puede_usar_consola(S1, c), f"la GM NPC puede .{c}")
for c in ("sanciones", "maquina", "autoplay", "record", "campana", "tira", "map", "libre", "pulso"):
    ok(not chat.puede_usar_consola(S1, c), f"⟲ la GM NPC NO puede .{c}")
ok(chat.puede_usar_consola(S1, "oscuro"), "los del juego (sin GM) siguen abiertos")
sin_marca = St(U1)
ok(not chat.puede_usar_consola(sin_marca, "rate") and not chat.puede_usar_consola(sin_marca, "npc"),
   "⟲ la misma cuenta SIN la marca de la conexión no tiene ni .rate ni .npc")
n = len(auditoria("gmnpc/comando"))
r = chat.comando_chat(S1, ".rate")
a = auditoria("gmnpc/comando")
ok(r and len(a) == n + 1 and json.loads(a[-1]["detalle"])["texto"] == ".rate" and a[-1]["actor_nick"] == MOD,
   "un .rate anda y queda auditado a nombre de la moderadora")
n = len(auditoria("gmnpc/comando"))
ok(chat.comando_chat(S1, ".sanciones") is None and len(auditoria("gmnpc/comando")) == n,
   "⟲ un comando que no puede va como chat normal y NO se audita como hecho")

# ═══ §3 una sesión ═══
print("§3 · una sesión")
S1.cambio_canal = True
G.al_salir(S1)
ok(G.cerrada(U1) is None and not G.info(U1)["cerrado"], "cambiar de canal NO la cierra")
S1b = St(U1)
G.al_entrar(S1b, U1)
S1b.reemplazada = True
G.al_salir(S1b)
ok(G.cerrada(U1) is None, "⟲ una conexión reemplazada por un doble login no la cierra")
S1c = St(U1)
G.al_entrar(S1c, U1)
G.al_salir(S1c)
ok(G.cerrada(U1) and G.info(U1)["cerrado"], f"irse SÍ la cierra: {G.cerrada(U1)!r}")
ok(db_get_char(U1)["nick"] == f"gmnpc{U1}", "y su apodo queda libre (pasa a gmnpc<usn>)")
ok(any(x["uid"] == U1 for x in auditoria("gmnpc/cerrada")), "el cierre queda auditado")
ok(any(x["uid"] == U1 for x in auditoria("gmnpc/entro")) and len([x for x in auditoria("gmnpc/entro") if x["uid"] == U1]) == 1,
   "la entrada se anota UNA vez (no en cada cambio de canal)")
cod, d4 = G.preparar("king", MOD)
ok(cod == 200 and d4["nick"] == "GM-King", f"la próxima King vuelve a ser {d4.get('nick')!r}")
U4 = d4["usn"]
ok(not G.cerrar(U1, "otra vez"), "cerrar dos veces no hace nada")

# ═══ §4 vencida ═══
print("§4 · sin usar")
panel_admin._pdb().execute("UPDATE gm_npc SET creado = ? WHERE usn = ?", (time.time() - (G.SIN_USAR_H + 1) * 3600, U2))
ok(G.lista()[[x["usn"] for x in G.lista()].index(U2)]["estado"] == "vencida", "la lista la muestra vencida")
ok(G.cerrada(U2) and G.info(U2)["cerrado"], "y no entra (y queda cerrada)")
u_normal, _ = cuenta_crear("jugadora_normal", hash_pass("x"))
db_create_char(u_normal, {"char_id": 130901, "gender": 1, "nick": "Normal", "parts": []})
ok(G.cerrada(u_normal) is None and not G.es_cuenta(u_normal) and G.cerrada(0) is None,
   "⟲ una cuenta cualquiera nunca está «cerrada» (ni la 0)")

# ═══ §5 los topes ═══
print("§5 · los topes")
IP = "10.20.30.40"
mod = St(u_normal, ip=IP)
gmc = St(U3, ip=IP)
G.al_entrar(gmc, U3)
ok(len(multicuenta.cuentas_de_ip(IP, {u_normal: mod, U3: gmc}, multicuenta.cuenta_de)) == 1,
   "con la moderadora y su GM NPC conectadas desde la misma IP cuenta UNA")
ok(len(multicuenta.cuentas_de_ip(IP, {u_normal: mod, U3: St(U3, ip=IP)}, multicuenta.cuenta_de)) == 2,
   "⟲ la misma conexión sin la marca GM NPC cuenta como otra")

# ═══ §6 la campana ═══
print("§6 · la campana")
import struct                                                     # noqa: E402
from servidor import antitrampa                                   # noqa: E402
vistos = []
orig = antitrampa.al_campana
antitrampa.al_campana = lambda st: vistos.append(st.usn)
paq = struct.pack("<I", 181) + struct.pack("<fff", 1.0, 2.0, 0.0)
lobby_campana.h_ffa8_campana(gmc, 0xA8, paq)                      # (fuera de sala: corta después del antitrampa)
lobby_campana.h_ffa8_campana(mod, 0xA8, paq)
antitrampa.al_campana = orig
ok(vistos == [u_normal], f"la GM NPC no alimenta al antitrampa de campanas; un jugador sí ({vistos})")

# ═══ §7 la ruta del Coordinador ═══
print("§7 · la ruta")
from servidor import contenido_interno as CI                     # noqa: E402
h = H(ficha="otra")
CI.atender_panel(h, "GET", ["gmnpc"])
ok(h.r[0] == 404, "⟲ sin la ficha: 404")
h = H()
CI.atender_panel(h, "GET", ["gmnpc"])
ok(h.r[0] == 200 and len(h.r[1]["npcs"]) == 6 and any(x["usn"] == U4 for x in h.r[1]["cuentas"])
   and all("clave" not in x for x in h.r[1]["cuentas"]), "GET: los 6 NPC y las cuentas (sin clave)")
h = H()
CI.atender_panel(h, "POST", ["gmnpc"], b"{}")
ok(h.r[0] == 400, "⟲ POST sin NPC: 400")
h = H()
CI.atender_panel(h, "POST", ["gmnpc"], json.dumps({"npc": "nari"}).encode())
ok(h.r[0] == 200 and h.r[1]["clave"] and h.r[1]["nick"] == "GM-Nari", "POST {npc: nari}: crea y devuelve la clave UNA vez")
U5 = h.r[1]["usn"]
ok(G.info(U5)["creado_por"] == MOD, "la crea a nombre de quien dice el Coordinador")
h = H()
CI.atender_panel(h, "POST", ["gmnpc", "cerrar"], json.dumps({"usn": U5}).encode())
ok(h.r[0] == 200 and G.info(U5)["cerrado"] and any(x["uid"] == U5 and "por" in json.loads(x["detalle"])
                                                   for x in auditoria("gmnpc/cerrada")),
   "cerrar desde el Coordinador: cerrada, y auditado con quién")
h = H()
CI.atender_panel(h, "POST", ["gmnpc", "cerrar"], json.dumps({"usn": u_normal}).encode())
ok(h.r[0] == 404 and db_get_char(u_normal)["nick"] == "Normal", "⟲ «cerrar» una cuenta normal: 404 y no se toca")
h = H()
CI.atender_panel(h, "POST", ["gmnpc", "otra"], b"{}")
ok(h.r[0] == 404, "⟲ una sub-ruta que no existe: 404")

# ═══ §8 con pase ═══
print("§8 · con R2_LOGIN=pase")
pedidos, estados = [], []
_mp, _cc, _pe = pase.modo_pase, pase.crear_cuenta_interna, pase.poner_estado_interno
pase.modo_pase = lambda: True
pase.crear_cuenta_interna = lambda u, h_: (pedidos.append((u, h_)) or {"estado": "ok", "datos": {"uid": 900001}, "error": ""})
pase.poner_estado_interno = lambda eid, e, motivo="": (estados.append((eid, e)) or {"estado": "ok", "error": ""})
cod, d6 = G.preparar("marie", MOD)
ok(cod == 200 and pedidos and pedidos[-1] == (d6["usuario"], hashlib.sha256(d6["clave"].encode()).hexdigest().upper()),
   "nace en Cuenta Eñeños con SU usuario y el hash de la clave")
ok(G.info(d6["usn"])["enenos_id"] == 900001, "y la fila del juego queda enlazada a ese Eñeños ID")
G.cerrar(d6["usn"], "prueba")
for _ in range(50):
    if estados:
        break
    time.sleep(0.05)
ok(estados == [(900001, "baneada")], f"al cerrarse se le pide «baneada» a Cuenta Eñeños ({estados})")
n = len(G.lista())
pase.crear_cuenta_interna = lambda u, h_: {"estado": "rechazado", "datos": None, "error": "usuario tomado"}
cod, d7 = G.preparar("marie", MOD)
ok(cod == 502 and len(G.lista()) == n, "⟲ si Cuenta Eñeños la rechaza: 502 y nada en el juego")
pase.modo_pase, pase.crear_cuenta_interna, pase.poner_estado_interno = _mp, _cc, _pe

# ═══ §9 los enganches de lobby.py ═══
print("§9 · los enganches")
src = open(os.path.join(RAIZ, "servidor", "lobby.py"), encoding="utf-8").read()
i3d = src.index("st.cambio_canal = True")
ok(0 < src.index("st.cerrado = True", i3d) - i3d < 200, "el FF3D marca cambio_canal justo antes de cortar")
ok(src.count("gm_npc.cerrada(") == 3, f"los TRES logins preguntan si está cerrada ({src.count('gm_npc.cerrada(')})")
ok("if not gm_npc.es_cuenta(_u) and (multicuenta.rechazar_por_tope" in src, "el FF02 la exime de los topes")
fin = src.index("gm_npc.al_salir(st)")
ok(src.index("if getattr(st, \"reemplazada\", False):", src.rindex("finally:", 0, fin)) < fin,
   "al_salir va en el finally, después del corte de las reemplazadas")

print()
print("✅ TODO BIEN" if not FALLAS else f"❌ {len(FALLAS)} FALLA(S):\n  - " + "\n  - ".join(FALLAS))
sys.exit(1 if FALLAS else 0)
