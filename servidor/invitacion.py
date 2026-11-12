# -*- coding: utf-8 -*-
"""invitacion — «Invitar a los del vestíbulo» (`FF52`, `CmdRandomInvite`) e «Invitar a un amigo» (`FF40 0x07`), 12-oct.

El anfitrión toca «invitar» en la sala y el cliente manda un `FF52` VACÍO. En prod caía en «SIN handler»: 6.336
veces del 25 al 28-sep y 5.625 del 29-sep al 11-oct (`FF_PENDIENTES.md`). Doc: `documentacion/INVITAR_VESTIBULO.md`.

  C→S `FF52` (vacío; emisor `0x5CA9A0`, desde la sala `0x5AA214`)
  S→C `FF52` (RX `0x5CFD60`), dos formas según el 1.er byte:
    [00]                                        → al que invitó: texto 167 «Ha enviado una invitación para usuarios
                                                  en el vestíbulo.» (sólo si no está en la escena del lobby)
    [01][u16 A][u8 modo][u8 x][u8 coop][u8 jefe][u32 uid]
                                                → a los del vestíbulo: texto 166 « %d Número (%s) Sala le ha enviado
                                                  una invitación. Clic en OK para proceder.» con OK → entra
      A    = la sala empaquetada como en la lista (`FF6E`): número & 0x7FF | tipo << 11 — el OK llama a `0x4A8150(A)`,
             el mismo camino que «entrar»; la clave y el cupo los sigue controlando el `FF11` de siempre
      modo = el texto de `%s` (`0x46BCA0`): bit0 Ítem (si no, Velocidad) · bit1 Equipo (si no, Solo) · bit2 Relevo ·
             bit3 «Original»
      x    = bit2 en 1 → usa el texto 611 (vacío en este build) en vez del 166: va en 0
      coop = ≠0 → el `%s` dice el nombre del cooperativo · jefe = ≠0 → «MODO JEFE»
      uid  = el que invita: el cliente NO muestra el cartel si lo tiene bloqueado (`0x45B030` del manager social)
    El cartel sale sólo si el que lo recibe está en el lobby, sin otro cartel abierto y con la opción de invitaciones
    prendida (`[0x9040A8]`): el resto lo descarta el propio cliente.
  El referente mandaba `01 06 68 00 00 01 00 49 00 00 00` (captura del 02-sep: sala 6 de tipo 13, coop, uid 73) y el
  jugador entraba con un `FF11` enseguida.

★ «INVITAR A UN AMIGO A MI SALA» = `FF40` sub `0x07` (`SendInviteFriend`; 608 «SIN handler» en prod en 12 días):
  C→S `[07][u32 usn del amigo][u32 ?][u8 largo][texto][u8]` (emisor `0x5C9510`, desde la sala `0x5977AC`). En prod el
      2.º u32 vale 0..7 (casi siempre 5) y el texto llega vacío: no se usa — la sala y el canal los sabe el server.
  S→C `FF40 [07][u8 sel][u32 uid]…` (RX `0x5F028C`):
    sel 1 → al que invita: texto 100 «Ha enviado la invitación.» · sel 6 → texto 653 «El usuario no puede ser invitado»
    sel 0 → al amigo: `[u16 servidor][u16 A][u32][u8 largo][apodo][u8 largo][texto]` → `0x45B550` → texto 106 «%s le ha
            enviado una invitación. Haga clic para unirse.» con OK = `0x4A72E0(servidor, A)` (el camino de «Jugar
            Juntos»: si el amigo está en otro canal, se muda). `servidor` y `A` son los MISMOS de la presencia de amigos
            (`lobby_social._servidor_de` / `_sala_de`). El texto 2 sólo se usa para Mi Sala (tipo 11).
            El cliente no lo muestra si tiene bloqueado al que invita (`0x45AF80` por apodo, `0x45B030` por uid).
"""
import struct
import time

from .registro import log

ESPERA_S = 15          # ⚠ una invitación por sala cada tanto: en prod los anfitriones lo tocan sin parar
_ULTIMA = {}           # roomid -> time.monotonic() de la última invitación difundida


def armar_aviso(sala, uid_anfitrion):
    """El `FF52 [01]…` para los del vestíbulo, desde la fila de `SALAS_VIVAS` (la misma de la lista de salas)."""
    rid = int(sala.get("roomid", 0) or 0)
    a = (rid & 0x7FF) | ((int(sala.get("A_alto", 0) or 0) & 0x1F) << 11)
    b = int(sala.get("B", 0) or 0)                # el byMode de la lista: 0x04 ítem · 0x10 equipo · 0x80 relevo
    modo = (1 if b & 0x04 else 0) | (2 if b & 0x10 else 0) | (4 if b & 0x80 else 0)
    return (bytes([1]) + struct.pack("<H", a)
            + bytes([modo, 0, 1 if sala.get("M") else 0, 1 if sala.get("O") else 0])
            + struct.pack("<I", int(uid_anfitrion) & 0xFFFFFFFF))


ESPERA_AMIGO_S = 3     # el mismo pedido llega 2-3 veces en el mismo segundo (prod, 13:18:47-48)
_ULTIMA_AMIGO = {}     # (quién, a quién) -> time.monotonic()


def armar_ff40_07_aviso(uid_invita, nick_invita, servidor, sala_a):
    """`FF40 [07][00]…` para el amigo invitado (RX `0x5F028C`, sel 0)."""
    n = str(nick_invita or "").encode("cp1252", "replace")[:0x1E]
    return (bytes([0x07, 0]) + struct.pack("<IHHI", int(uid_invita) & 0xFFFFFFFF, int(servidor) & 0xFFFF,
                                           int(sala_a) & 0xFFFF, 0)
            + bytes([len(n)]) + n + bytes([0]))


def armar_ff40_07_resultado(sel, uid):
    """`FF40 [07][sel][u32]` al que invita: 1 = «Ha enviado la invitación.» · 6 = «El usuario no puede ser invitado»."""
    return bytes([0x07, sel & 0xFF]) + struct.pack("<I", int(uid) & 0xFFFFFFFF)


def atender_amigo(st, cuerpo):
    """`FF40 0x07` (sin el sub): `[u32 usn del amigo][u32 ?][u8 largo][texto][u8]`."""
    from .ajustes import INVITAR_AMIGO
    from .basedatos import db_get_char
    from .lobby_social import _sala_de, _servidor_de
    from .salas import CONEXIONES, SALAS_VIVAS
    usn = int(getattr(st, "usn", 0) or 0)
    if len(cuerpo) < 4:
        return log("LOBBY", f"  ⚠ FF40 0x07 que no cierra de usn={usn}: {cuerpo.hex(' ')}")
    dest = struct.unpack_from("<I", cuerpo, 0)[0]
    rid = getattr(st, "room_id", None)
    c = CONEXIONES.get(dest)
    por = ""
    if not INVITAR_AMIGO:
        por = "apagado (INVITAR_AMIGO)"
    elif dest == usn:
        por = "a sí mismo"
    elif not rid or SALAS_VIVAS.get(rid) is None:
        por = f"no está en una sala (room_id={rid})"
    elif c is None or getattr(c, "cerrado", False):
        por = "no está conectado"
    elif getattr(c, "en_carrera", False):
        por = "está corriendo"
    elif getattr(c, "room_id", None) == rid:
        por = "ya está en la sala"
    if por:
        st.send_ff55(0x40, armar_ff40_07_resultado(6, dest), name="FF40/0x07 no puede ser invitado")
        return log("LOBBY", f"  📨 FF40 0x07 usn={usn} invita a uid={dest} -> NO ({por})")
    st.send_ff55(0x40, armar_ff40_07_resultado(1, dest), name="FF40/0x07 invitación enviada")
    ahora = time.monotonic()
    if ahora - _ULTIMA_AMIGO.get((usn, dest), -1e9) < ESPERA_AMIGO_S:
        return log("LOBBY", f"  📨 FF40 0x07 usn={usn} -> uid={dest}: repetido en menos de {ESPERA_AMIGO_S} s, no se reenvía")
    _ULTIMA_AMIGO[(usn, dest)] = ahora
    nick = str((db_get_char(usn) or {}).get("nick", "") or "")
    servidor, sala = _servidor_de(usn), _sala_de(usn)
    c.send_ff55(0x40, armar_ff40_07_aviso(usn, nick, servidor, sala), name=f"FF40/0x07 invitación de {nick!r}")
    log("LOBBY", f"  📨★ FF40 0x07 {nick!r} (usn={usn}) invitó a uid={dest} a su sala {rid} "
                 f"(servidor {servidor}, A=0x{sala:04X})")


def _en_el_vestibulo(c, canal):
    return (not getattr(c, "cerrado", False) and getattr(c, "usn", None)
            and not getattr(c, "room_id", None) and not getattr(c, "en_carrera", False)
            and getattr(c, "canal", None) == canal)


def atender(st):
    from .ajustes import INVITAR_VESTIBULO
    from .salas import CONEXIONES, SALAS_VIVAS
    usn = int(getattr(st, "usn", 0) or 0)
    rid = getattr(st, "room_id", None)
    sala = SALAS_VIVAS.get(rid) if rid else None
    st.send_ff55(0x52, b"\x00", name="FF52 invitación enviada (texto 167)")
    if not INVITAR_VESTIBULO:
        return log("LOBBY", f"  📨 FF52 usn={usn} invita al vestíbulo -> apagado (INVITAR_VESTIBULO)")
    if sala is None:
        return log("LOBBY", f"  📨 FF52 usn={usn} invita al vestíbulo sin estar en una sala (room_id={rid}) -> nada")
    if int(sala.get("B", 0) or 0) & 0x02:
        return log("LOBBY", f"  📨 FF52 usn={usn} sala {rid}: está EN JUEGO -> no se difunde")
    ahora = time.monotonic()
    if ahora - _ULTIMA.get(rid, -1e9) < ESPERA_S:
        return log("LOBBY", f"  📨 FF52 usn={usn} sala {rid}: ya invitó hace menos de {ESPERA_S} s -> no se repite")
    _ULTIMA[rid] = ahora
    canal = getattr(st, "canal", None)
    aviso = armar_aviso(sala, usn)
    n = 0
    for c in list(CONEXIONES.values()):
        if c is st or not _en_el_vestibulo(c, canal):
            continue
        try:
            c.send_ff55(0x52, aviso, name=f"FF52 invitación a la sala {rid}")
            n += 1
        except Exception as e:                                            # noqa: BLE001
            log("LOBBY", f"  ⚠ FF52 no pude avisarle a usn={getattr(c, 'usn', '?')}: {e!r}")
    log("LOBBY", f"  📨★ FF52 usn={usn} invitó al vestíbulo a la sala {rid} ({sala.get('nombre', '')!r}, canal {canal}) "
                 f"-> {n} jugador(es) · {aviso.hex(' ')}")
