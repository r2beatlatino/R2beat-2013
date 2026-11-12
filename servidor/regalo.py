# -*- coding: utf-8 -*-
"""regalo — «Enviar regalo» de la tienda: el `FF53` que viaja CIFRADO dentro del sobre `FF4F` (12-oct).

★ anonimo03: *«intenté enviar un cabello a jugadora_prueba»*. Llegaban tres `?? cmd 0x4f` de 56 B y nadie los abría.
  Doc: `documentacion/REGALO.md` · prueba: `pruebas/probar_regalo.py`.

EL SOBRE (todo leído del exe 2013)
  · el emisor del regalo (`0x5CAB20`) arma el `FF53` normal (`ff 53 [u16 largo] [cuerpo]`, con un 9 de relleno si queda
    impar) y lo cifra con `0x5C3B30(0, salida, entrada, largo, clave)`; manda `FF4F` con la salida (4 × el largo)
    y avanza el MISMO reloj que el FF55 (`[sesión+0x21B5C]`, nuestro `recv_counter`);
  · la CLAVE = `"%d%d%d" % ([sesión+0x21B58], [jugador+0x7C], reloj)` — medido: `"0" + usn + reloj`
    (cuenta_admin, reloj 32: `"0109632"`); el `[jugador+0x7C]` es el usn que trae la respuesta del login (`0x5C4D05`);
  · el CIFRADO es un Blowfish CASERO (`0x5C0CC0` llave · `0x5C0B80` bloque · `0x5C3A10` datos):
      - las S-cajas son las de siempre (π) y en el orden de siempre (el cliente las tiene cruzadas en la pila y las
        vuelve a cruzar al copiarlas: medido contra las del exe, iguales);
      - la P NO arranca con π: arranca en CERO (el contexto se pone en 0 en `0x5C3AA0`) y se le hace XOR la clave;
      - el bloque es el estándar;
      - cada BYTE del paquete se pasa a un dword CON SIGNO y se cifran pares de dwords ⇒ un descifrado bueno da
        dwords en −128..127 (así se reconoce la clave buena sin saberla de antemano).

EL REGALO (`FF53`)
  C→S cuerpo: `[u8 largo][apodo][u32 código de compra]` — el código es el de siempre (`0x50E050`): el ÍTEM con el
  PLAZO en el dígito de los miles (`36562` = el 30562 de uso único, `229548` = el 220548 permanente).
  S→C (`0x5CFF50`): `[u8 resultado][u8 largo][apodo][u32 ítem][u32 saldo]` — 0 «¡Entrega lista! … cuando se conecte»
  (y el saldo pasa al cliente), 2 «No hay suficientes Rcoin», 3 «el sobrenombre no existe», 4 «no puede usar este
  ítem», 5 «ya tiene este ítem», 6 «No puede enviarse regalos a usted mismo», 7 «bajo el nivel 8», otro «error».
  El que paga es el que regala (el precio de ese plazo, como el FF2A); el ítem va al inventario del otro.
"""
import struct

from .ajustes import REGALO_AVISOS
from .registro import hx, log

# ── el Blowfish del cliente ─────────────────────────────────────────────────────────────────────────────────────────
_S = None


def _cajas():
    """Las 4 S-cajas estándar (los dígitos hexadecimales de π que siguen a los 18 de la P)."""
    global _S
    if _S is not None:
        return _S
    n = 18 + 4 * 256
    bits = n * 32 + 64
    uno = 1 << bits

    def arctan_inv(x):
        s, t, k, x2 = 0, uno // x, 0, x * x
        while t:
            s += t // (2 * k + 1) if k % 2 == 0 else -(t // (2 * k + 1))
            t //= x2
            k += 1
        return s
    frac = (16 * arctan_inv(5) - 4 * arctan_inv(239) - 3 * uno) >> 64
    w = [(frac >> (32 * (n - 1 - i))) & 0xFFFFFFFF for i in range(n)]
    S = [w[18 + 256 * k:18 + 256 * (k + 1)] for k in range(4)]
    assert w[0] == 0x243F6A88 and S[0][0] == 0xD1310BA6
    _S = S
    return _S


class _BF:
    def __init__(self, clave):
        self.C = [list(s) for s in _cajas()]
        self.P = [0] * 18                                          # ⚠ en CERO, no π
        j = 0
        for i in range(18):
            d = 0
            for _ in range(4):
                b = clave[j % len(clave)]
                d = ((d << 8) | ((b - 256 if b >= 128 else b) & 0xFFFFFFFF)) & 0xFFFFFFFF
                j += 1
            self.P[i] ^= d
        L = R = 0
        for i in range(9):
            L, R = self.bloque(L, R)
            self.P[2 * i], self.P[2 * i + 1] = L, R
        for c in range(4):
            for i in range(0, 256, 2):
                L, R = self.bloque(L, R)
                self.C[c][i], self.C[c][i + 1] = L, R

    def F(self, x):
        C = self.C
        return ((((C[0][x >> 24] + C[1][(x >> 16) & 255]) & 0xFFFFFFFF) ^ C[2][(x >> 8) & 255]) + C[3][x & 255]) & 0xFFFFFFFF

    def bloque(self, L, R):
        for i in range(16):
            L ^= self.P[i]
            L, R = R ^ self.F(L), L
        return R ^ self.P[17], L ^ self.P[16]

    def desbloque(self, a, b):
        L, R = b ^ self.P[16], a ^ self.P[17]
        for i in range(15, -1, -1):
            lp = R
            L, R = lp ^ self.P[i], L ^ self.F(lp)
        return L, R


def cifrar(datos, clave):
    """Como el cliente (`0x5C3A10`): cada byte → dword con signo, pares cifrados. -> 4 × len(datos) bytes."""
    if len(datos) % 2:
        datos = datos + b"\x09"
    bf = _BF(clave.encode("ascii"))
    dw = [(b - 256 if b >= 128 else b) & 0xFFFFFFFF for b in datos]
    out = []
    for k in range(0, len(dw), 2):
        out += bf.bloque(dw[k], dw[k + 1])
    return struct.pack("<%dI" % len(out), *out)


def descifrar(sobre, clave):
    """-> los bytes, o None si con esa clave no salen bytes con signo (clave equivocada)."""
    if len(sobre) % 8:
        return None
    bf = _BF(clave.encode("ascii"))
    d = struct.unpack("<%dI" % (len(sobre) // 4), sobre)
    out = []
    for k in range(0, len(d), 2):
        out += bf.desbloque(d[k], d[k + 1])
    if not all(x <= 0x7F or x >= 0xFFFFFF80 for x in out):
        return None
    return bytes(x & 0xFF for x in out)


def abrir_sobre(sobre, usn, reloj, key_base=0, margen=(-2, 12)):
    """Prueba la clave con el reloj esperado y sus vecinos (el reloj del cliente avanza con FF55 que pudimos no ver).
    -> (cmd, cuerpo, reloj_usado) o None."""
    for d in range(margen[0], margen[1] + 1):
        r = (reloj + d) & 0xFFFFFFFF
        for a in ((0, key_base) if key_base else (0,)):
            plano = descifrar(sobre, "%d%d%d" % (a, usn, r))
            if plano and len(plano) >= 4 and plano[0] == 0xFF:
                cmd = plano[1]
                largo = struct.unpack_from("<H", plano, 2)[0]
                if 4 + largo <= len(plano):
                    return cmd, plano[4:4 + largo], r
    return None


# ── el regalo ───────────────────────────────────────────────────────────────────────────────────────────────────────
OK, SIN_SALDO, NO_EXISTE, NO_PUEDE, YA_TIENE, A_SI_MISMO, ERROR = 0, 2, 3, 4, 5, 6, 8


def armar_ff53(res, apodo, item, saldo):
    a = str(apodo or "").encode("cp1252", "replace")[:30]
    return bytes([res & 0xFF, len(a)]) + a + struct.pack("<II", int(item) & 0xFFFFFFFF, int(saldo) & 0xFFFFFFFF)


def leer_ff53(cuerpo):
    if len(cuerpo) < 1 or len(cuerpo) < 1 + cuerpo[0] + 4:
        return None
    n = cuerpo[0]
    return cuerpo[1:1 + n].decode("cp1252", "replace"), struct.unpack_from("<I", cuerpo, 1 + n)[0]


def _destino(apodo, yo):
    from .basedatos import db_get_char, db_uids_por_nick
    from .salas import CONEXIONES
    todos = [u for u in db_uids_por_nick(apodo)]
    if not todos:
        return None
    if yo in todos and len(todos) == 1:
        return yo
    otros = [u for u in todos if u != yo]
    vivos = [u for u in otros if u in CONEXIONES]
    if vivos:
        return vivos[0]
    return max(otros, key=lambda u: int((db_get_char(u) or {}).get("exp", 0) or 0))


def regalar(st, cuerpo):
    """`FF53` C→S (ya descifrado): cobra al que regala y le deja el ítem al otro."""
    from . import shop_catalog
    from .basedatos import compute_expiry, db_get_char, db_get_rcoin, inv_ids
    from .catalogo import entregar_compra, tiene_cargas
    from .lobby_tienda import cobrar
    yo = int(getattr(st, "usn", 0) or 0)
    leido = leer_ff53(cuerpo)
    if leido is None:
        log("LOBBY", f"  ⚠ FF53 que no cierra de usn={yo}: {hx(cuerpo)}")
        return
    apodo, raw = leido
    saldo = db_get_rcoin(yo)

    def contestar(res, item=0, por=""):
        st.send_ff55(0x53, armar_ff53(res, apodo, item, db_get_rcoin(yo)), name=f"FF53 regalo res={res} a {apodo!r}")
        log("LOBBY", f"  🎁 FF53 REGALO usn={yo} -> {apodo!r} código={raw} -> res={res}{(' (' + por + ')') if por else ''}")

    dest = _destino(apodo, yo)
    if dest is None:
        return contestar(NO_EXISTE, por="no existe ese apodo")
    if dest == yo:
        return contestar(A_SI_MISMO, por="a sí mismo")
    plazo = shop_catalog.period_code(raw)
    item = shop_catalog.normalize_id(raw)
    if item is None:
        return contestar(NO_PUEDE, por="el código no está en el catálogo")
    from .ajustes import REGALO_NO_SE_REGALA
    from .catalogo import desempacar_pack
    if item in REGALO_NO_SE_REGALA or desempacar_pack(item)[0] in REGALO_NO_SE_REGALA:
        return contestar(NO_PUEDE, item, por=f"el {item} no se regala (REGALO_NO_SE_REGALA: las campanas)")
    ch = db_get_char(dest) or {}
    if (item in inv_ids(ch) or item in ch.get("parts", [])) and not tiene_cargas(item) and not shop_catalog.es_set(item):
        return contestar(YA_TIENE, item, por=f"ya tiene el {item}")
    # ★ 28-oct (132) anonimo03: «lo enviado debe cumplir la lista de F o M»: una prenda de chica no se le regala a un chico
    #   (ni al revés). «%s no puede usar este ítem» es justo el cartel de fábrica para esto.
    from .ajustes import REGALO_MISMO_SEXO
    sx = shop_catalog.sexo_de(item)
    if REGALO_MISMO_SEXO and sx is not None and sx != (int(ch.get("gender") or 0) & 1):
        return contestar(NO_PUEDE, item, por=f"el {item} es de {'chica' if sx else 'chico'} y el otro no")
    alcanza, precio, saldo = cobrar(st, item, plazo, "FF53 regalo")
    if not alcanza:
        return contestar(SIN_SALDO, item, por=f"cuesta {precio}, tiene {saldo}")
    vence = compute_expiry(plazo)
    entregado = entregar_compra(dest, item, vence)
    st.send_ff55(0x53, armar_ff53(OK, apodo, item, saldo), name=f"FF53 regalo OK a {apodo!r}")
    yo_nick = str((db_get_char(yo) or {}).get("nick", "") or "")
    vivo = avisar_en_vivo(dest, piezas(item, vence, entregado), de=yo_nick, item=item)
    from .preferidos import sacar_regalado
    pref = sacar_regalado(dest, item)
    from .preferidos import sacar_comprado
    sacar_comprado(st, item)                        # ★ (132) y sale del carrito del que lo regaló
    log("LOBBY", f"  🎁★ FF53 REGALO usn={yo} le regaló a {apodo!r} (uid={dest}) el ítem {item} plazo {plazo} "
                 f"(código {raw}) por {precio} Rcoin · saldo {saldo} — {vivo} {pref}")


# ── ★ EN VIVO (12-oct, 2.ª vuelta; anonimo03: «existía un sistema para enviar regalos en vivo, jugador a jugador y GM a
#    jugador, con un popup de "X te envió un regalo" y el regalo ya en el inventario») ──────────────────────────────
#   El paquete es el `FFCE` = `CmdAddItem` (RX `0x5D84D0`, log «Get Coupon Item : %u»):
#     [u32 ítem][u32 vence][u16 cant][u32 Rcoin][u32 ?][u8 tipo][u32 ?][u32 → jugador+0xD1C si ≠ 0][u32 SEED]
#   SIEMPRE mete el ítem en el inventario en vivo (`0x48F720(ítem, vence, cant, 0)` + redibujo `0x48DF80`), y según
#   el tipo: 0 = «Ha recibido %d Rcoin» (si viene Rcoin) · 5/6/10 = el popup con el ÍCONO del ítem y «¡Felicitaciones!
#   Premios de Evento han llegado» (texto 725, `0x4218B0`) · 11 = ese popup + el NOMBRE del ítem («%s\n%s»).
#   ⚠ El último u32 PISA la moneda SEED del jugador (`0x485330`: [jugador+0x2E8] = v ^ 0x1FEF): va el SEED de siempre.
#   El popup no puede decir quién lo manda (el texto es fijo): eso va en una línea del chat, firmada SERVER.
#   El texto 178 «Un regalo de '%s' '%s' ha llegado» existe pero el exe no lo usa en ningún lado (era de la web).
#   En carrera no se manda nada (un paquete a destiempo mata a las máquinas lentas): queda el refresco de después.
POPUP_CON_NOMBRE = 11
SIN_POPUP = 0                 # tipo 0 sin Rcoin: el FFCE sólo mete el ítem en el inventario (el aviso va en el FF54)

# ★★ 12-oct, 3.ª vuelta (anonimo03: «el popup entre jugadores era de OTRO color, diciendo QUIÉN mandó el regalo»). Es el
#   `FF54` (RX `0x5D0130`) — el cliente lo PIDE vacío al entrar al lobby (le contestábamos `00`, copiado del referente):
#     S→C [u8 n] × ( [u8 largo][apodo][u32 ÍTEM][u32 —][u32 RCOIN] )
#   ⚠ 4.ª vuelta (anonimo03: «Ha recibido [(null)] de jugadora_prueba», sin imagen): el orden lo había leído MAL ([rcoin][ítem]). Contada
#     la pila de nuevo (0x5D0184..0x5D01CD): el 1.º u32 va a [X+0xC] = el ítem (arg 1 de 0x423920), el 2.º a [X+0x10] no
#     se usa, el 3.º a [X+8] = el Rcoin (arg 3). Con el ítem en 0, el nombre y la imagen salían vacíos.
#   y por cada uno `0x423920(ítem, apodo, rcoin)` abre el POPUP 20 (celeste, `rnr_ui/popup/no_item_0`, con la IMAGEN
#   del ítem): texto 326 «Ha recibido [%s] de %s.» · 327 «… y %d Rcoin de %s.» · 328 «Ha recibido %d Rcoin de %s.»
#   (con el ítem 1200073 sale la variante 4: la verde de `popup_present_pause`, «선물이 도착했어요!», sin traducir).
#   El FF54 NO mete nada en el inventario: para eso va antes el FFCE con tipo 0 (sin popup).
#   ⇒ Conectado y fuera de carrera: FFCE silencioso + FF54. Si no: el aviso se guarda (`regalos_avisos`) y sale en
#     el FF54 que pide al entrar al lobby.


def armar_ff54(avisos):
    """S→C `FF54`: [(apodo de quién, ítem, rcoin)] -> [n]([largo][apodo][u32 ítem][u32 0][u32 rcoin])…"""
    p = bytes([len(avisos) & 0xFF])
    for de, item, rcoin in avisos:
        a = str(de or "").encode("cp1252", "replace")[:30]
        p += bytes([len(a)]) + a + struct.pack("<III", int(item) & 0xFFFFFFFF, 0, int(rcoin) & 0xFFFFFFFF)
    return p


def avisos_al_entrar(st):
    """El `FF54` que el cliente pide al entrar al lobby: los avisos de regalo pendientes (o `00`, como siempre)."""
    from . import almacen
    avisos = almacen.sacar_avisos_regalo(int(getattr(st, "usn", 0) or 0)) if REGALO_AVISOS else []
    st.send_ff55(0x54, armar_ff54(avisos), name=f"FF54 avisos de regalo ({len(avisos)})")
    if avisos:
        log("LOBBY", f"  🎁 FF54 a usn={getattr(st, 'usn', 0)}: {len(avisos)} aviso(s) de regalo pendientes {avisos}")


def armar_ffce(item, vence_wire, cant=1, tipo=POPUP_CON_NOMBRE):
    from .ajustes import SEED
    return struct.pack("<IIHIIBIII", int(item) & 0xFFFFFFFF, int(vence_wire) & 0xFFFFFFFF, max(1, int(cant)) & 0xFFFF,
                       0, 0, tipo & 0xFF, 0, 0, int(SEED) & 0xFFFFFFFF)


def piezas(item, vence, entregado, cant=1):
    """Lo que quedó en el inventario por `entregar_compra(…) -> entregado`: [(ítem, vence, cantidad)]."""
    from . import shop_catalog
    from .basedatos import compute_expiry
    if shop_catalog.es_set(item):
        return [(it, compute_expiry(shop_catalog.period_code(c)), 1) for it, c in (shop_catalog.contenido_de_set(item) or [])] * max(1, cant)
    dentro, n = entregado if entregado else (item, 0)
    if dentro != item and n:
        return [(dentro, vence, n * max(1, cant))]
    return [(item, vence, max(1, n, cant))]


def avisar_en_vivo(dest, lista, de="", motivo="regalo", item=None):
    """`lista` = lo que quedó en el inventario [(ítem, vence, cant)]; `item` = lo que se regaló (lo que muestra el popup).
    Conectado y fuera de carrera: cada pieza con su `FFCE` silencioso (entra al inventario) y el `FF54` celeste
    «Ha recibido [ítem] de X». Si no, el aviso queda guardado para el FF54 de cuando entre.
    -> "en vivo" · "en carrera" (aviso guardado) · "desconectado" (aviso guardado)."""
    from . import almacen
    from .basedatos import _exp_to_wire
    from .salas import CONEXIONES
    mostrar = item if item is not None else (lista[0][0] if lista else 0)
    c = CONEXIONES.get(int(dest))
    if c is None or getattr(c, "cerrado", False) or getattr(c, "en_carrera", False):
        if de and mostrar and REGALO_AVISOS:
            almacen.aviso_regalo(dest, de, mostrar)
        if c is not None and getattr(c, "en_carrera", False):
            c.buy_needs_refresh = True
            return "en carrera"
        return "desconectado"
    from .basedatos import db_get_char, db_get_rcoin, inv_cant
    from .catalogo import tiene_cargas
    cargas = inv_cant(db_get_char(int(dest)) or {})
    for it, vence, cant in lista:
        c.send_ff55(0xCE, armar_ffce(it, _exp_to_wire(vence), cant, tipo=SIN_POPUP if (de and REGALO_AVISOS) else POPUP_CON_NOMBRE),
                    name=f"FFCE {motivo} en vivo: {it} x{cant}")
        # ★ 12-oct (anonimo03: «regalé un pack de 10 y el regalo recibido no marca las cargas»): el cliente dibuja la
        #   cantidad desde el FF69 (`myrecord.enviar_ff69_cargas`), no desde el FFCE. Con el TOTAL que tiene ahora.
        if (tiene_cargas(it) or cant > 1) and cargas.get(it, 0) > 0:
            c.send_ff55(0x69, bytes([1]) + struct.pack("<IHI", it & 0xFFFFFFFF, cargas[it] & 0xFFFF,
                                                         db_get_rcoin(int(dest)) & 0xFFFFFFFF),
                        name=f"FF69 cargas del regalo: {cargas[it]} del {it}")
    if de and mostrar and REGALO_AVISOS:
        c.send_ff55(0x54, armar_ff54([(de, mostrar, 0)]), name=f"FF54 «Ha recibido [{mostrar}] de {de}»")
    return "en vivo"


def dar_item(uid, iid, dias=0, cant=1, de="GM", motivo="panel"):
    """Da un ítem como una compra de la tienda (`catalogo.entregar_compra`: abre packs y sets, y lo de pareja le llega
    a la pareja) y avisa EN VIVO (`avisar_en_vivo`). Lo que va por CARGAS recibe `cant` cargas. `dias` 0 = permanente.
    ★ 15-oct: era el cuerpo de `panel_admin._dar_item`; ahora lo comparten el panel y el cupón (`cupon.py`).
    `de` = quién firma el aviso («GM»: FFCE silencioso + FF54 celeste «Ha recibido [ítem] de GM»; "" = el popup
    amarillo del FFCE «¡Felicitaciones! Premios de Evento han llegado», sin decir quién)."""
    import time as _t
    from . import shop_catalog
    from .basedatos import db_add_inventory
    from .catalogo import desempacar_pack, entregar_compra, tiene_cargas
    vence = int(_t.time() + dias * 86400) if dias else 0
    # ⛔ Un PACK («Pack megáfono x5») también da `tiene_cargas`: por eso primero se pregunta si es un envase.
    #   Un envase va SIEMPRE por la entrega de la tienda (lo abre), `cant` veces; guardarlo crudo es el
    #   bug que ya tuvo la tienda (el ítem muerto en el inventario, ver `catalogo.entregar_compra`).
    envase = desempacar_pack(iid)[1] > 0 or shop_catalog.es_set(iid)
    if envase:
        lista = []
        for _ in range(min(cant, 50)):
            lista += piezas(iid, vence, entregar_compra(uid, iid, vence))
    elif tiene_cargas(iid):
        db_add_inventory(uid, iid, vence, cant=cant)
        lista = [(iid, vence, cant)]
    else:
        lista = piezas(iid, vence, entregar_compra(uid, iid, vence))
    vivo = avisar_en_vivo(uid, lista, de=de, motivo=motivo, item=iid)
    return {"item": iid, "nombre": (shop_catalog.get(iid) or {}).get("name", ""), "dias": dias,
            "cant": cant if (envase or tiene_cargas(iid)) else None, "en_vivo": vivo}


def atender_sobre(st, payload):
    """El `FF4F` de afuera: se abre con el reloj del FF55 y se despacha lo de adentro."""
    yo = int(getattr(st, "usn", 0) or 0)
    reloj = int(getattr(st, "recv_counter", 0) or 0)
    r = abrir_sobre(bytes(payload), yo, reloj, getattr(st, "key_base", 0) or 0)
    if r is None:
        log("LOBBY", f"  ⚠ FF4F de usn={yo} que no abre (reloj {reloj}, {len(payload)} B)")
        return
    cmd, cuerpo, usado = r
    st.recv_counter = (usado + 1) & 0xFFFFFFFF                     # el cliente avanzó su reloj con este sobre
    log("LOBBY", f"  🔓 FF4F de usn={yo} abierto (reloj {usado}): FF{cmd:02X} {hx(cuerpo)}")
    if cmd == 0x53:
        regalar(st, cuerpo)
    else:
        log("LOBBY", f"  ⚠ FF4F con un FF{cmd:02X} adentro: no lo atendemos")
