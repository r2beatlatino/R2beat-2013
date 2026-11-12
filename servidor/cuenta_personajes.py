# -*- coding: utf-8 -*-
"""cuenta_personajes — hasta CUATRO personajes por cuenta (anonimo03, 21-oct: la landing de r2portable, «Elegir personaje»).

LA DECISIÓN DE ANONIMO03 (21-oct)
-----------------------------
  · **Cada personaje va APARTE**: su apodo, su nivel, su Rcoin, su ropa, sus amigos, su círculo y su ranking.
    Comparten sólo el usuario y la contraseña.
  · **El personaje que la cuenta ya tiene es el casillero 1.** Nadie pierde nada, y el launcher de Windows sigue
    entrando con ése.

CÓMO
----
  · Cada personaje es un `usn` propio, así que TODO el server (que identifica por `usn`) lo trata como siempre, sin
    tocar una línea. El casillero 1 es el `usn` de la cuenta (`users.uid`); el 2, el 3 y el 4 reservan un `usn` nuevo
    en `cuenta_personajes` (y `basedatos.cuenta_crear` los cuenta como usados: `almacen.uids_usados`).
  · El diálogo va por el LoginServer con el MISMO framing que el launcher (`FF <cmd> <len:u16>`), así sirve igual
    desde el puente del navegador que desde cualquier launcher. Toda orden trae `[ulen][usuario][hlen][sha256]` y se
    verifica con `cuenta_verificar`:

        FFF1 LISTA     [cuenta]                                  -> [st][n] n × [ranura][usn:u32][sexo][nlen][apodo]
                                                                                [nivel:u8][np] np × [id:u32]
        FFF2 CREAR     [cuenta][ranura][sexo][nlen][apodo][np] np × [id:u32]
                                                                 -> [st][usn:u32][mlen][mensaje]
        FFF3 ENTRAR    [cuenta][ranura]                          -> [st][usn:u32][4 ceros][len][vcode HEX]  (como FF01)
        FFF4 OPCIONES  (nada: es el catálogo, público)           -> 2 × [sexo] 4 × [n] n × [id:u32]  (las A, B, C)
        FFF5 BORRAR    [cuenta][ranura]                          -> [st][mlen][mensaje]

    `sexo`: 1 chico · 2 chica (el de `shop.bin`). `st`: 0 bien · 1 el apodo ya existe · 2 cualquier otro error.

    ★ 25-oct: FFF6..FFFA, las del selector ADENTRO DEL JUEGO (la dll): se autentican con la SESIÓN, no con la
      contraseña. Ver «EL SELECTOR ADENTRO DEL JUEGO», más abajo.

★ BORRAR (24-oct, anonimo03: el botón «删除角色» del selector chino, `rnr_ui/charselect/charselect_newui.rui`): NO borra de
  la base — el personaje deja de mostrarse y su casillero queda libre (`almacen.ocultar_ranura`: la fila pasa a
  `personajes_borrados`), «para posibles recuperaciones manuales». Todo lo suyo en `chars` queda; su apodo sigue
  tomado. ⛔ El casillero 1 NO se borra: es la cuenta misma (`users.uid`), con el que entra el launcher de Windows.
  La web pide la contraseña otra vez para confirmar (como el cartel chino `del_user.rui`): el hash viaja en [cuenta].

⚠ Lo que NO tienen los casilleros 2-4: un `username` propio. Lo que mire al jugador por su LOGIN (p. ej. `gm.txt`)
  sólo reconoce al casillero 1.
"""
import struct

from . import almacen
from .basedatos import cuenta_verificar, db_get_char, db_uids_por_nick, sesion_abrir, sesion_valida
from .cifrado import frame
from .misiones import db_create_char
from .progresion import nivel_de_exp
from .registro import log

RANURAS = (1, 2, 3, 4)
# el char_id de la creación por sexo (medido: 130900 = hombre, 130901 = mujer; ajustes.py)
CHAR_ID = {1: 130900, 2: 130901}
# ★ LO QUE SE PUEDE ELEGIR al crear: las filas «Cabello / Parte superior / Parte inferior / Patines», con sus
#   opciones A, B, C, EN EL ORDEN DEL EXE: la tabla de `.rdata` 0x881BE8 (2 sexos × 4 filas × 3, la lee cCharSelect;
#   repo Fuente `documentacion/CREACION.md` §3). Leída igual en el prístino, el de prod y el local.
#   ⚠ NO es el orden de `shop_lt.txt`: ahí la chica arranca 220584 y en el exe la A es 220585 (220584 es la B).
#   Son las MISMAS 24 prendas que `catalogo.basicas_por_parte` (lo comprueba pruebas/probar_cuenta_personajes.py
#   §6, junto con la tabla contra el exe).
OPCIONES_EXE = {
    1: [[210566, 210565, 210567], [310565, 310564, 310566], [410491, 410493, 410492], [510430, 510429, 510431]],
    2: [[220585, 220584, 220586], [320566, 320565, 320567], [420528, 420529, 420527], [520438, 520437, 520439]],
}
VA_OPCIONES = 0x881BE8


def leer_cuenta(p):
    """`[ulen][usuario][hlen][hash]` -> (usuario, hash, resto) o (None, None, b"")."""
    try:
        ul = p[0]
        u = p[1:1 + ul].decode("ascii")
        hl = p[1 + ul]
        h = p[2 + ul:2 + ul + hl].decode("ascii")
        return u, h, p[2 + ul + hl:]
    except (IndexError, UnicodeDecodeError):
        return None, None, b""


def ranuras_de(usuario):
    """{ranura: usn} de la cuenta: la 1 es la cuenta misma; las otras, las reservadas (o MUDADAS desde otra cuenta:
    `almacen.mover_personaje`). Una cuenta fusionada en otra no tiene ninguna."""
    e = almacen.cuenta_estado(usuario)
    return e["ranuras"] if e else {}


def _sexo(ch):
    return 2 if int(ch.get("gender", int(ch.get("char_id", 0)) & 1)) & 1 else 1


def lista(usuario):
    """[(ranura, usn, sexo, apodo, nivel, [prendas])] de los casilleros CON personaje.

    ★ 25-oct: las prendas son las que se DIBUJAN (`gacha.apariencia`), no las de la base. Con un cuerpo del gacha
      (un cuerpo entero: 110149…) y la ropa común encima, la copia del muñeco del selector (`0x4940B0`) tumbaba el
      juego (_invalid_parameter en 0x65041F). El armario y la sala nunca reciben esa ropa: tampoco el selector."""
    from .gacha import apariencia
    out = []
    for r, usn in sorted(ranuras_de(usuario).items()):
        ch = db_get_char(usn)
        if not ch or not ch.get("nick"):
            continue
        out.append((r, usn, _sexo(ch), ch["nick"], nivel_de_exp(int(ch.get("exp", 0) or 0)),
                    [int(x) for x in apariencia(ch)[1] if x]))
    return out


def opciones(sexo):
    """[[A, B, C] de cabello, superior, inferior, patines] de la creación de ese sexo (el orden del exe)."""
    return OPCIONES_EXE[sexo]


def prenda_valida(sexo, fila, item):
    """¿Se puede elegir `item` en esa fila al crear? Sólo las A, B, C de la creación."""
    return int(item) in opciones(sexo)[fila]


def crear(usuario, ranura, sexo, apodo, prendas):
    """-> (st, usn, mensaje)."""
    if ranura not in RANURAS:
        return 2, 0, "casillero inválido"
    if sexo not in CHAR_ID:
        return 2, 0, "sexo inválido"
    apodo = (apodo or "").strip()
    if not (2 <= len(apodo) <= 12):
        return 2, 0, "el apodo tiene que tener de 2 a 12 caracteres"
    if len(prendas) != 4 or not all(prenda_valida(sexo, i, p) for i, p in enumerate(prendas)):
        return 2, 0, "la ropa elegida no es de la creación"
    ya = ranuras_de(usuario)
    if ranura in ya and (db_get_char(ya[ranura]) or {}).get("nick"):
        return 2, 0, "ese casillero ya tiene personaje"
    if db_uids_por_nick(apodo):
        return 1, 0, "ese apodo ya existe"
    usn = ya.get(ranura) or almacen.reservar_ranura(usuario, ranura)
    db_create_char(usn, {"char_id": CHAR_ID[sexo], "gender": 1 if sexo == 2 else 0, "nick": apodo,
                         "parts": list(prendas)})
    # lo mismo que el FF04 del juego (lobby_menu.h_01_ff04): «¿Quién te invitó?» y el set básico guardado
    from .referido import al_crear
    from .catalogo import asegurar_basico
    al_crear(usn)
    asegurar_basico(usn)
    log("LOGIN", f"  ★★ PERSONAJE CREADO desde la web: {usuario!r} casillero {ranura} -> usn={usn} {apodo!r} "
                 f"({'chica' if sexo == 2 else 'chico'}, {prendas})")
    return 0, usn, "personaje creado"


def borrar(usuario, ranura):
    """-> (st, mensaje). Oculta el personaje del casillero (no lo borra de la base: ver arriba)."""
    if ranura == 1:
        return 2, "el personaje 1 es el de la cuenta: no se puede borrar"
    if ranura not in RANURAS:
        return 2, "casillero inválido"
    usn = ranuras_de(usuario).get(ranura)
    ch = db_get_char(usn) if usn else None
    if not ch or not ch.get("nick"):
        return 2, "ese casillero no tiene personaje"
    almacen.ocultar_ranura(usuario, ranura, ch["nick"])
    log("LOGIN", f"  ★★ PERSONAJE BORRADO (oculto) desde la web: {usuario!r} casillero {ranura} -> usn={usn} "
                 f"{ch['nick']!r} — sigue en la base: personajes_borrados")
    return 0, "personaje borrado"


def responder(cmd, payload, cmd_respuesta=None):
    """El paquete de respuesta (con su marco) a FFF1 / FFF2 / FFF3 / FFF4 / FFF5. (`cmd_respuesta`: con otro número
    de orden, para que FFF7/FFF9 del selector del juego reusen la lista y el borrado.)"""
    if cmd == 0xF4:                    # las opciones de la creación: públicas (el catálogo), sin cuenta
        p = bytearray()
        for sexo in (1, 2):
            p += bytes([sexo])
            for fila in opciones(sexo):
                p += bytes([len(fila)]) + b"".join(struct.pack("<I", x) for x in fila)
        return frame(0xF4, bytes(p))
    usuario, h, resto = leer_cuenta(payload)
    cuenta_ok = usuario and cuenta_verificar(usuario, h) is not None
    if cmd == 0xF1:
        if not cuenta_ok:
            return frame(cmd_respuesta or 0xF1, b"\x02\x00")
        filas = lista(usuario)
        p = bytearray([0, len(filas)])
        for r, usn, sexo, apodo, nivel, prendas in filas:
            a = apodo.encode("cp1252", "replace")[:32]
            p += bytes([r]) + struct.pack("<I", usn) + bytes([sexo, len(a)]) + a + bytes([min(nivel, 255), len(prendas[:32])])
            p += b"".join(struct.pack("<I", x) for x in prendas[:32])
            if cmd_respuesta == 0xF7:
                # ★ 25-oct: el selector del JUEGO dibuja el muñeco de cada tarjeta (selector.c) y necesita el CUERPO:
                #   los del gacha (130029…) no son el 130900/130901 del sexo. Va al FINAL de cada personaje, así el
                #   FFF1 de la web (el mismo armado) no cambia.
                p += struct.pack("<I", int((db_get_char(usn) or {}).get("char_id") or 0))
        return frame(cmd_respuesta or 0xF1, bytes(p))
    if cmd == 0xF2:
        if not cuenta_ok:
            st, usn, msg = 2, 0, "usuario o contraseña incorrectos"
        else:
            try:
                ranura, sexo, nl = resto[0], resto[1], resto[2]
                apodo = resto[3:3 + nl].decode("cp1252")
                n = resto[3 + nl]
                prendas = [struct.unpack_from("<I", resto, 4 + nl + 4 * i)[0] for i in range(n)]
                st, usn, msg = crear(usuario, ranura, sexo, apodo, prendas)
            except (IndexError, struct.error, UnicodeDecodeError):
                st, usn, msg = 2, 0, "pedido mal formado"
        m = msg.encode("utf-8")[:200]
        return frame(0xF2, bytes([st]) + struct.pack("<I", usn) + bytes([len(m)]) + m)
    if cmd == 0xF5:
        if not cuenta_ok:
            st, msg = 2, "contraseña incorrecta"
        elif not resto:
            st, msg = 2, "pedido mal formado"
        else:
            st, msg = borrar(usuario, resto[0])
        m = msg.encode("utf-8")[:200]
        return frame(cmd_respuesta or 0xF5, bytes([st, len(m)]) + m)
    # FFF3 ENTRAR
    usn = ranuras_de(usuario).get(resto[0] if resto else 0) if cuenta_ok else None
    if not usn or not (db_get_char(usn) or {}).get("nick"):
        return _sin_sesion(0xF3)
    return _sesion_para(0xF3, usn, f"{usuario!r} casillero {resto[0]}")


def _sesion_para(cmd, usn, quien):
    """La respuesta «como el FF01»: abre la sesión de `usn` -> [st 0][usn:u32][4 ceros][len][vcode HEX]."""
    vcode = sesion_abrir(usn)
    t = f"{int(vcode):016X}".encode("ascii")
    log("LOGIN", f"  ★★ SESIÓN para usn={usn}: {quien}")
    return frame(cmd, bytes([0x00]) + struct.pack("<I", usn) + bytes(4) + bytes([len(t)]) + t)


def _sin_sesion(cmd):
    return frame(cmd, bytes([0x01]) + struct.pack("<I", 0) + bytes(4) + bytes([0]))


# ═══ ★★ EL SELECTOR ADENTRO DEL JUEGO (25-oct, anonimo03: «ocupando el lugar de creación») ══════════════════
#
#   El exe 2013 no tiene selector de casilleros: lo dibuja NUESTRA dll encima de la escena de creación
#   (cCharSelect), 1 a 1 con la web. La dll no conoce la contraseña: se autentica con la SESIÓN que le dio el
#   launcher (el `usn` y el `vcode` de su línea de comandos) — `[sesion] = [usn:u32][vcode:u64]`.
#
#       FFF6 HOLA      [sesion]                        -> [st]   «este juego TIENE selector» (la dll, al arrancar)
#       FFF7 LISTA     [sesion]                        -> lo mismo que el FFF1
#       FFF8 ELEGIR    [sesion][ranura][crear:u8]      -> como el FFF3: la sesión del personaje de ese casillero
#       FFF9 BORRAR    [sesion][ranura][hlen][sha256]  -> como el FFF5 (la contraseña OTRA VEZ, como el chino)
#       FFFA VOLVER    [sesion]                        -> como el FFF3, con la CUENTA («Cambiar de personaje»)
#
#   EL MODO ELEGIR: tras el HOLA, la cuenta queda en `ELIGIENDO` y su ficha (`build_myrecord`) sale VACÍA: el
#   juego, sin personaje, abre la creación — y ahí está el selector. Al ELEGIR sale de `ELIGIENDO`; la dll pone
#   el usn/vcode del elegido en el juego y lo reconecta: login, lobby y la ficha del de verdad.
#   ⚠ Sin el HOLA nada cambia: un cliente sin la dll nueva (prod) sigue entrando como siempre.
#   `documentacion/SELECTOR_PERSONAJE.md`.
ELIGIENDO = set()
# ★ los usn RECIÉN ELEGIDOS: el juego vuelve a entrar con ellos desde la creación. MEDIDO (25-oct, Frida): el `FFC9`
#   que va detrás de su ficha revienta al cliente (0x684107: el picker, `[0x9314EC]`, tiene un botón sin imagen
#   después de pasar por la creación). Ese FFC9 se guarda y sale ya en el lobby (lobby_salas.h_08_ff6e).
RECIEN_ELEGIDOS = set()


def recien_elegido(usn):
    """¿Esta ficha es la de un personaje recién elegido en el selector? (se consume: una sola vez)"""
    try:
        RECIEN_ELEGIDOS.remove(int(usn or 0))
        return True
    except KeyError:
        return False


def eligiendo(usn):
    """¿La ficha de este `usn` tiene que salir vacía (el juego está en el selector)?"""
    return int(usn or 0) in ELIGIENDO


def leer_sesion(p):
    """`[usn:u32][vcode:u64]` -> (usn, cuenta, ranura, resto) si la sesión vale; (None, None, 0, b"") si no."""
    if len(p) < 12:
        return None, None, 0, b""
    usn, vcode = struct.unpack_from("<IQ", p)
    if not sesion_valida(usn, vcode):
        return None, None, 0, b""
    cuenta, ranura = almacen.cuenta_de_uid(usn)
    return (usn, cuenta, ranura, p[12:]) if cuenta else (None, None, 0, b"")


def _cuenta_de_confianza(cuenta, pass_hash=None):
    """El `[cuenta]` de las órdenes viejas, para reusarlas. Sin `pass_hash` va el guardado (la sesión ya probó
    quién es); con él, el que tipeó el jugador (BORRAR: se verifica de nuevo, como en el chino)."""
    h = pass_hash if pass_hash is not None else almacen.cuenta_de(cuenta)["pass"]
    u, hb = cuenta.encode("ascii", "replace"), h.encode("ascii", "replace")
    return bytes([len(u)]) + u + bytes([len(hb)]) + hb


def responder_sesion(cmd, payload):
    """El paquete de respuesta a FFF6..FFFA (las órdenes del selector del juego)."""
    usn, cuenta, ranura_propia, resto = leer_sesion(payload)
    if cmd == 0xF6:                                          # HOLA
        if not usn or ranura_propia != 1:
            return frame(0xF6, b"\x02")
        ELIGIENDO.add(usn)
        log("LOGIN", f"  ★★ SELECTOR: el juego de {cuenta!r} (usn={usn}) tiene selector -> su ficha sale vacía")
        return frame(0xF6, b"\x00")
    if cmd == 0xF7:                                          # LISTA
        return responder(0xF1, _cuenta_de_confianza(cuenta), 0xF7) if usn else frame(0xF7, b"\x02\x00")
    if cmd == 0xFA:                                          # VOLVER (cambiar de personaje)
        if not usn:
            return _sin_sesion(0xFA)
        cu = int(almacen.cuenta_de(cuenta)["usn"])
        ELIGIENDO.add(cu)
        return _sesion_para(0xFA, cu, f"{cuenta!r} VUELVE al selector")
    if cmd == 0xF8:                                          # ELEGIR
        if not usn or len(resto) < 2 or resto[0] not in RANURAS:
            return _sin_sesion(0xF8)
        r, crear = resto[0], resto[1] == 1
        destino = ranuras_de(cuenta).get(r)
        tiene = bool(destino and (db_get_char(destino) or {}).get("nick"))
        if not tiene:
            if not crear:
                return _sin_sesion(0xF8)
            destino = destino or almacen.reservar_ranura(cuenta, r)
        ELIGIENDO.discard(int(almacen.cuenta_de(cuenta)["usn"]))
        RECIEN_ELEGIDOS.add(int(destino))
        return _sesion_para(0xF8, destino, f"{cuenta!r} ELIGE el casillero {r}" + ("" if tiene else " (A CREAR)"))
    if cmd == 0xF9:                                          # BORRAR
        if not usn or len(resto) < 2:
            return frame(0xF9, bytes([2, 0]))
        r, hl = resto[0], resto[1]
        h = resto[2:2 + hl].decode("ascii", "replace")
        return responder(0xF5, _cuenta_de_confianza(cuenta, h) + bytes([r]), 0xF9)
    return frame(cmd, b"\x02")
