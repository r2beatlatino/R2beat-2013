#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_lucky_star — la LUCKY STAR (`servidor/lucky_star.py`, 27-nov-2026).

Contra una base TEMPORAL, con una conexión de mentira que guarda lo que se le manda:
    §1 ganarla: el FF28 con el byte 56 = 1 la acredita (+1 del 298) y el FFC6 [00] sale AL VOLVER, con el FF69
                                                                 ⟲ byte 56 = 0: nada · ⟲ un espectador o fuera de carrera: nada
    §2 el tope: con 10 sin abrir, FFC6 [01] y no suma            ⟲ el tope por día: FFC6 [02]
    §3 abrirla: FFC7 [llave] -> [00][llave][ícono][vence], −1 llave, −1 estrella, +Rcoin del tier, FFAB con el saldo
                                                                 ⟲ sin llave: [02] · sin estrella: [01] · una llave que no es llave: [02]
                                                                 ⟲ nada cambia en la base cuando no se abre
    §4 el tier de cada llave y la tabla (editable)              ⟲ un premio que no es Rcoin se rechaza; tier vacío: [03]
    §5 los enganches (despacho, FF28, FF13, cargas)

    python pruebas/probar_lucky_star.py
"""
import os
import random
import struct
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                # noqa: BLE001
    pass

_TMP = tempfile.mkdtemp(prefix="r2_lucky_")
os.environ["R2_BASE"] = os.path.join(_TMP, "datos.db")            # ⛔ ANTES de importar el server
os.environ["R2_LOG"] = os.path.join(_TMP, "servidor.log")
os.environ["R2_SESIONES"] = os.path.join(_TMP, "sesiones.json")

from servidor import catalogo, lucky_star as L, shop_catalog      # noqa: E402

# ★ El repo público no trae `shop_lt.txt` (es del server privado): una tienda CHICA con lo que esta prueba mira.
if not os.path.exists(shop_catalog.SHOP_LT):
    _shop = os.path.join(_TMP, "shop_lt.txt")
    with open(_shop, "w", encoding="cp1252") as _f:
        for _sh, _ix, _nm, _ef in (("0502", 293, "500 Rcoin", 0), ("0502", 294, "1,000 Rcoin", 0),
                                   ("0502", 295, "1,500 Rcoin", 0), ("0509", 298, "Lucky Star", 916),
                                   ("0509", 299, "Gold Key", 917), ("0509", 300, "Silver Key", 918),
                                   ("0509", 301, "Bronze Key", 919), ("0600", 776, "Gold Key S", 917),
                                   ("0600", 777, "Silver Key S", 918), ("0401", 220585, "Cabello", 0)):
            _f.write(f'<Item ShopIndex="{_sh}" Index="{_ix}" Name="{_nm}" ItemEffect="{_ef}" PN="3600"> </Item>' + chr(10))
    shop_catalog.load(_shop)
from servidor.basedatos import cuenta_crear, db_add_inventory, db_get_rcoin, hash_pass   # noqa: E402
from servidor.misiones import db_create_char                       # noqa: E402

FALLAS = []


def ok(cond, texto):
    print(("   ✅ " if cond else "   ❌ ") + texto)
    if not cond:
        FALLAS.append(texto)


class St:
    def __init__(self, usn, **kw):
        self.usn, self.en_carrera, self.slot_espectador, self.mandados = usn, True, None, []
        self.__dict__.update(kw)

    def send_ff55(self, cmd, data=b"", name=""):
        self.mandados.append((cmd, bytes(data)))

    def de(self, cmd):
        return [d for c, d in self.mandados if c == cmd]


def ff28(estrella):
    d = bytearray(62)
    d[L.BYTE_FF28] = 1 if estrella else 0
    return bytes(d)


def jugador(nombre):
    u, _ = cuenta_crear(nombre, hash_pass("x"))
    db_create_char(u, {"char_id": 130900, "gender": 0, "nick": nombre, "parts": []})
    return u


U = jugador("corredora")

# ═══ §1 ganarla ═══
print("§1 · ganarla")
s = St(U)
ok(L.al_fin_de_carrera(s, ff28(False)) is None and L.cuantas(U, 298) == 0, "⟲ byte 56 = 0: no se da nada")
L.al_volver(s)
ok(not s.mandados, "⟲ y al volver no sale ningún FFC6")
ok(L.al_fin_de_carrera(St(U, slot_espectador=3), ff28(True)) is None and L.cuantas(U, 298) == 0,
   "⟲ un espectador con byte 56 = 1: nada")
ok(L.al_fin_de_carrera(St(U, en_carrera=False), ff28(True)) is None and L.cuantas(U, 298) == 0,
   "⟲ fuera de una carrera: nada")
ok(L.al_fin_de_carrera(s, ff28(True)) == L.GANO_OK and L.cuantas(U, 298) == 1, "byte 56 = 1: +1 Lucky Star en la base, YA")
ok(not s.de(0xC6), "el FFC6 NO sale en el FF28 (todavía está en el cartel)")
L.al_volver(s)
ok(s.de(0xC6) == [b"\x00"], f"al volver: FFC6 [00] ({s.de(0xC6)})")
f69 = s.de(0x69)
ok(len(f69) == 1 and struct.unpack_from("<IH", f69[0], 1) == (298, 1), "y el FF69 con el TOTAL de estrellas (1)")
ok(not s.de(0xCE), "⟲ sin FFCE (el cliente ya se la sumó: la contaría dos veces)")
s.mandados.clear()
L.al_volver(s)
ok(not s.mandados, "⟲ volver otra vez no la repite")

# ═══ §2 los topes ═══
print("§2 · los topes")
U2 = jugador("llena")
db_add_inventory(U2, 298, 0, cant=10)
s2 = St(U2)
ok(L.al_fin_de_carrera(s2, ff28(True)) == L.GANO_TIENE_10 and L.cuantas(U2, 298) == 10, "con 10 sin abrir: no suma")
L.al_volver(s2)
ok(s2.de(0xC6) == [b"\x01"] and not s2.de(0x69), "FFC6 [01] («ya tenés las 10»), sin FF69")
U3 = jugador("tramposa")
_tope = L.TOPE_POR_DIA
L.TOPE_POR_DIA = 2
for _ in range(2):
    L.al_fin_de_carrera(St(U3), ff28(True))
s3 = St(U3)
ok(L.al_fin_de_carrera(s3, ff28(True)) == L.GANO_ERROR and L.cuantas(U3, 298) == 2, "⟲ pasado el tope del día: no suma")
L.al_volver(s3)
ok(s3.de(0xC6) == [b"\x02"], "FFC6 [02] (error)")
L.TOPE_POR_DIA = _tope

# ═══ §3 abrirla ═══
print("§3 · abrirla")
U4 = jugador("abridora")
r0 = db_get_rcoin(U4)
s4 = St(U4)
L.abrir(s4, struct.pack("<I", 301))
ok(s4.de(0xC7) == [struct.pack("<BII", 2, 301, 0)] and db_get_rcoin(U4) == r0, "⟲ sin llave: FFC7 [02] y nada cambia")
db_add_inventory(U4, 301, 0, cant=2)
s4.mandados.clear()
L.abrir(s4, struct.pack("<I", 301))
ok(s4.de(0xC7) == [struct.pack("<BII", 1, 301, 0)] and L.cuantas(U4, 301) == 2, "⟲ sin estrella: FFC7 [01] y la llave queda")
s4.mandados.clear()
L.abrir(s4, struct.pack("<I", 298))
ok(s4.de(0xC7)[0][:1] == b"\x02", "⟲ mandar la estrella como «llave»: [02]")
s4.mandados.clear()
L.abrir(s4, b"\x01")
ok(s4.de(0xC7)[0][:1] == b"\x02", "⟲ un paquete corto: igual contesta ([02])")
db_add_inventory(U4, 298, 0, cant=3)
s4.mandados.clear()
L.abrir(s4, struct.pack("<I", 301))
c7 = s4.de(0xC7)
esperado = L.PREMIOS_POR_DEFECTO["bronce"]
from servidor.cupon import iconos_rcoin                           # noqa: E402
icono = iconos_rcoin().get(esperado, 0)
ok(len(c7) == 1 and len(c7[0]) == 13 and struct.unpack("<BIII", c7[0])[:3] == (0, 301, icono),
   f"FFC7 [00][301][ícono {icono}][vence] ({c7[0].hex() if c7 else c7})")
ok(icono != 0, "el monto por defecto tiene su cajita de Rcoin (el popup muestra el ícono)")
ok(db_get_rcoin(U4) == r0 + esperado, f"+{esperado} Rcoin (bronce)")
ok(L.cuantas(U4, 301) == 1 and L.cuantas(U4, 298) == 2, "−1 llave y −1 estrella en la base")
ok(s4.de(0xAB) == [struct.pack("<I", r0 + esperado)], "FFAB con el saldo nuevo")
ok(sorted(struct.unpack_from("<I", d, 1)[0] for d in s4.de(0x69)) == [298, 301], "FF69 de la llave y de la estrella")
# una llave vieja SIN cargas (comprada antes) también abre, y se gasta entera
U5 = jugador("vieja")
from servidor.basedatos import db_get_char, db_save_uno           # noqa: E402
ch = db_get_char(U5)
ch["inventory"] = [{"id": 299, "exp": 0}, {"id": 298, "exp": 0, "cant": 1}]
db_save_uno(U5, ch)
r5 = db_get_rcoin(U5)
s5 = St(U5)
L.abrir(s5, struct.pack("<I", 299))
ok(s5.de(0xC7)[0][:1] == b"\x00" and L.cuantas(U5, 299) == 0 and L.cuantas(U5, 298) == 0,
   "una llave guardada SIN cargas (de antes) abre y se gasta")
ok(db_get_rcoin(U5) == r5 + L.PREMIOS_POR_DEFECTO["oro"], "y da lo del oro (299 = Gold Key)")
ok(not s5.de(0x69), "⟲ con 0 no se manda FF69 (un count 0 el cliente lo lee como 1)")

# ═══ §4 tiers y tabla ═══
print("§4 · los tiers y la tabla")
ok(L.LLAVES == {776: "oro", 777: "plata", 299: "oro", 300: "plata", 301: "bronce"}, "las 5 llaves del exe, con su tier")
_efecto = {299: "917", 300: "918", 301: "919", 776: "917", 777: "918"}
shop_catalog.get(0)
ok(all(str((shop_catalog.CATALOG.get(k) or {}).get("effect")) == _efecto[k] for k in _efecto), "el tier coincide con el ItemEffect de la tienda (917 oro · 918 plata · 919 bronce)")
L.poner_premios("plata", [{"tipo": "rcoin", "valor": 200, "chance": 1}, {"tipo": "rcoin", "valor": 20000, "chance": 0}])
ok([f["valor"] for f in L.premios("plata")] == [200, 20000] and L.sortear("plata", random.Random(1))["valor"] == 200,
   "la tabla se edita; chance 0 nunca sale")
try:
    L.poner_premios("oro", [{"tipo": "ropa", "valor": 1}])
    ok(False, "⟲ un premio que no es Rcoin tendría que rechazarse")
except ValueError:
    ok(L.PREMIOS_POR_DEFECTO["oro"] in [f["valor"] for f in L.premios("oro")], "⟲ un premio que no es Rcoin: rechazado, la tabla queda")
L.poner_premios("bronce", [])
U6 = jugador("sinpremio")
db_add_inventory(U6, 301, 0, cant=1)
db_add_inventory(U6, 298, 0, cant=1)
s6 = St(U6)
L.abrir(s6, struct.pack("<I", 301))
ok(s6.de(0xC7) == [struct.pack("<BII", 3, 301, 0)] and L.cuantas(U6, 301) == 1 and L.cuantas(U6, 298) == 1,
   "⟲ un tier sin premios: [03] (error) y no gasta nada")

# ═══ §5 los enganches ═══
print("§5 · los enganches")
src = {n: open(os.path.join(RAIZ, "servidor", n), encoding="utf-8").read()
       for n in ("despacho.py", "lobby_carrera.py", "lobby_salas.py")}
ok("cmd == 0xC7, h_ffc7_lucky_star" in src["despacho.py"], "el despacho manda el FFC7 a lucky_star")
_i = src["lobby_carrera.py"].index("def h_21_ff28")
ok("lucky_star.al_fin_de_carrera(st, data)" in src["lobby_carrera.py"][_i:_i + 6000], "el FF28 mira la estrella")
_j = src["lobby_salas.py"].index("st.en_carrera = False")
ok("lucky_star.al_volver(st)" in src["lobby_salas.py"][_j:_j + 3000], "el FF13 de volver manda el FFC6")
ok(all(catalogo.tiene_cargas(i) for i in (298, 299, 300, 301, 776, 777)) and not catalogo.tiene_cargas(220585),
   "la estrella y las llaves van por cargas (⟲ una prenda no)")

# ═══ §6 la bandera de la pista (FF0C cola[18]) ═══
print("§6 · la bandera de la pista (FF0C)")
from servidor import paquetes as P                                 # noqa: E402
ok(P.FF0C_NOTAS_ESPECIALES is False, "⟲ de fábrica APAGADA (falta medir la sala en vivo con el byte de más)")
_occ = {"char_id": 130900, "slot": 1, "parts": [220585], "nick": "corredora", "exp": 0}
_sin = P.build_ff0c_2013_real(_occ)
P.FF0C_NOTAS_ESPECIALES = True
_con = P.build_ff0c_2013_real(_occ)
P.FF0C_NOTAS_ESPECIALES = False
_i = next((k for k in range(min(len(_sin), len(_con))) if _sin[k] != _con[k]), None)
ok(len(_con) == len(_sin) + 1, "prendida: el FF0C crece UN byte (el que el cliente lee detrás de la bandera)")
ok(_i is not None and _con[_i:_i + 2] == b"\x01\x00" and _sin[_i] == 0, "la bandera en 1 y el byte de más en 0")
ok(_i is not None and _con[:_i] == _sin[:_i] and _con[_i + 2:] == _sin[_i + 1:],
   "todo lo de antes y lo de después, idéntico (nada se corre para el cliente)")
ok(_i is not None and len(_sin) - _i == 48 - 18, "y cae en la cola, en el byte 18 (la cola mide 48 sin joyas ni texto)")
ok(P.build_ff0c_2013_real(_occ) == _sin, "⟲ apagada otra vez: el FF0C de siempre")

print()
if FALLAS:
    print(f"❌ {len(FALLAS)} falla(s)")
    sys.exit(1)
print("✅ TODO BIEN")
