# -*- coding: utf-8 -*-
"""monturas — SUBIRSE, BAJARSE y UNIRSE a una montura en la sala (142, 1 a 1 con el 2019). Ver
`documentacion/MONTURAS.md` y el reversing en `documentacion/MONTURAS_COMO_LO_HACE_EL_2019.md`.

CÓMO LO HACE EL 2019 (medido, ver el documento)
    · invocar la montura = aparece el objeto donde estás parado (`cCall_ObjectUI`, paquete 0x26 → el RoomInfo lo trae);
    · CLIC sobre el objeto (cCall_Object::Process 0x52B840) → `SendGuildRoomAction(ítem, modo, id)`:
        1 = subirse a la propia · 5 = la propia si tiene AniChange · 2 / 6 = unirse a la de la PAREJA;
      clic estando arriba → bajarse (modo 0). El server contesta a TODA la sala con `0xF4 [slot][ítem][modo]`
      (CmdGuildRoomAction → cRoom 0xA1F090), y cada cliente sienta / baja al jugador.
    · el subibaja y la perla (11000622 / 11000640) tienen un asiento de chico y uno de chica: si el de tu sexo ya está
      ocupado, el aviso 0x7B1 (string.csv 1969: «没有当前性别可乘坐的位置。»).

CÓMO LO HACEMOS EN EL 2013
    · invocar = tenerla MARCADA en el inventario (familia `montura`): el objeto sale en todas las salas;
    · el clic lo ve la dll (`monturas.c`) y lo pide por el canal de la sesión (el mismo del selector):
          C→S  FFFB  [usn:u32][vcode:u64][accion:u8][casillero:u8]   0 bajar · 1 la propia · 2 la del casillero
          S→C  FFFB  [resultado:u8][byte:u8]                         0 = ok (byte = el nuevo byte alto del Wing Id)
    · ★ DIFERENCIA A PROPÓSITO (anonimo03: «que las de 2 sean usables por 2 personas»): el 2019 sólo deja unirse a la
      PAREJA; acá a CUALQUIERA de la sala, con un lugar libre (dos arriba como mucho) y el 0x7B1 del 2019.
    · el estado viaja como el 0xF4 pero en el byte de arriba del Wing Id (`wing_id_con_aura`), con un FF15 a toda la
      sala: cada dll lo lee y sienta / baja al jugador.

EL BYTE (el de arriba del Wing Id; 1..4 siguen siendo flotar):
    0x80 | 0x40 (tiene montura propia) | modo << 4 | k      modo 0 parado · 1 en la propia
    0x80 | 2 << 4 | casillero del dueño                      modo 2: en la de otro (la propia no se ve mientras tanto)
    ej.: 0xC0 banco invocado · 0xD0 sentado en su banco · 0xA3 sentado en la del casillero 3.
    ★ (144) la 17.ª (el tigre, k = 16) no entra en 4 bits: con 0x40 puesto el modo es 0 ó 1 (el 2 va SIN 0x40), así que
      el bit 0x20 está libre y lleva el 5.º bit de k: 0x80 | 0x40 | modo << 4 | (k & 0x10) << 1 | (k & 0x0F)  (k ≤ 31).
      ej.: 0xE0 tigre invocado · 0xF0 montado en su tigre. Ver `codificar` / `decodificar`.
"""
import struct
import threading

from .cifrado import frame
from .registro import log

# usn -> (sala, modo, dueño)   — el modo vale sólo en la sala donde se puso (al cambiar de sala se baja, como el 2019);
#   `dueño` = el usn de la montura en la que va (él mismo en modo 1; el otro en modo 2)
ESTADO = {}
_lock = threading.Lock()

BAJAR, SUBIR, UNIRSE = 0, 1, 2
# ★ el aviso 0x7B1 del 2019 (string.csv 1969: «没有当前性别可乘坐的位置。»), en castellano
AVISO_SIN_LUGAR = "No hay lugar para tu sexo en esta montura."
AVISO_OCUPADA = "Esa montura ya tiene a dos arriba."
ITEMS_POR_SEXO = (11000622, 11000640)          # el subibaja y la perla: un asiento de chico y uno de chica (0x52B9C3)


def _sala_de(usn):
    from .salas import CONEXIONES                                          # noqa: PLC0415
    st = CONEXIONES.get(int(usn or 0))
    return (st, getattr(st, "room_id", None)) if st is not None else (None, None)


def _estado(usn):
    """(modo, dueño) de ESTA sala (si se fue a otra, (0, 0))."""
    if not usn:
        return 0, 0
    with _lock:
        e = ESTADO.get(int(usn))
    if not e:
        return 0, 0
    _st, rid = _sala_de(usn)
    return (e[1], e[2]) if rid is not None and rid == e[0] else (0, 0)


def modo_de(usn):
    """0 / 1 / 2 — el modo de ESTA sala (si se fue a otra, 0)."""
    return _estado(usn)[0]


def montura_de(usn):
    """k de la montura MARCADA (o None) — de lo puesto en la base, no de lo visible."""
    from .basedatos import db_get_char                                     # noqa: PLC0415
    from .catalogo import monturas                                         # noqa: PLC0415
    char = db_get_char(int(usn or 0)) or {}
    for p in char.get("parts") or []:
        try:
            k = monturas().get(int(p))
        except (TypeError, ValueError):
            continue
        if k is not None:
            return k
    return None


def _slot_de(usn):
    st, _rid = _sala_de(usn)
    return getattr(st, "room_slot", None) if st is not None else None


K_MAX = 31


def codificar(k, modo=0):
    """el byte de una montura PROPIA k (0..31) en el modo 0 (parado) ó 1 (montado en la suya)."""
    k = int(k)
    if not 0 <= k <= K_MAX or modo not in (0, 1):
        raise ValueError(f"montura k={k} modo={modo}: fuera de lo que entra en el byte")
    return 0x80 | 0x40 | (modo << 4) | ((k & 0x10) << 1) | (k & 0x0F)


def decodificar(b):
    """(k, modo, casillero del dueño) de un byte — lo MISMO que hace la dll (`mo_decodificar`, monturas.c).
    k = None si no tiene la suya; casillero sólo en el modo 2."""
    if b is None or b < 0 or not (b & 0x80):
        return None, 0, None
    if b & 0x40:
        return ((b & 0x20) >> 1) | (b & 0x0F), (b >> 4) & 1, None
    modo = (b >> 4) & 3
    if modo == UNIRSE:
        return None, UNIRSE, b & 0x0F
    return None, 0, None


def byte_de(usn, k=None):
    """el byte alto del Wing Id de este jugador (0 = nada de monturas). `k` = su montura propia (None = sin)."""
    m, dueno = _estado(usn) if usn else (0, 0)
    if m == UNIRSE:
        sl = _slot_de(dueno)
        if sl is not None:
            return 0x80 | (UNIRSE << 4) | (int(sl) & 0x0F)
        m = 0
    if k is None:                                    # sin montura (o se la sacó estando arriba): nada
        return 0
    return codificar(k, m)


def _pareja_en_sala(usn, rid):
    from .basedatos import db_pareja_de                                    # noqa: PLC0415
    from .salas import mesa_de                                             # noqa: PLC0415
    pj = int(db_pareja_de(int(usn)) or 0)
    if not pj or rid is None:
        return 0
    return pj if pj in {int(u) for u in mesa_de(rid).values()} else 0


def _poner(usn, rid, modo, dueno=0):
    with _lock:
        if modo:
            ESTADO[int(usn)] = (rid, modo, int(dueno or usn))
        else:
            ESTADO.pop(int(usn), None)


def _arriba_de(dueno, rid):
    """los usn que van en la montura de `dueno` en la sala `rid` (él incluido si está montado)."""
    with _lock:
        return [u for u, e in ESTADO.items() if e[0] == rid and e[2] == int(dueno)]


def _sexo(usn):
    from .basedatos import db_get_char                                     # noqa: PLC0415
    from .gacha import sexo                                                # noqa: PLC0415
    return sexo((db_get_char(int(usn)) or {}).get("char_id", 0))


_PLAN = None


def _item2019(k):
    """el ítem del 2019 de la montura k (para los casos por código del 2019) — de monturas.json."""
    global _PLAN
    if _PLAN is None:
        _PLAN = {}
        try:
            import json                                                    # noqa: PLC0415
            import os                                                      # noqa: PLC0415
            from .ajustes import _DIR_SERVIDOR                             # noqa: PLC0415
            for v in json.load(open(os.path.join(_DIR_SERVIDOR, "tablas-cliente", "monturas.json"))).values():
                if isinstance(v, dict) and "item2019" in v:
                    _PLAN[int(v["k"])] = int(v["item2019"])
        except Exception:                                                  # noqa: BLE001
            _PLAN = {}
    return _PLAN.get(k, 0)


def accion(usn, que, dueno_slot=None):
    """Aplica `que` (0 bajar · 1 subirse a la propia · 2 unirse a la de OTRO: la del casillero `dueno_slot`; sin
    casillero, la de la pareja). -> (ok, motivo, aviso)."""
    from .catalogo import montura_flags                                    # noqa: PLC0415
    from .salas import mesa_de                                             # noqa: PLC0415
    st, rid = _sala_de(usn)
    if st is None or rid is None:
        return False, "no está en una sala", None
    actual = modo_de(usn)
    if que == BAJAR:
        _poner(usn, rid, 0)
        return True, "se baja" if actual else "ya estaba parado", None
    if actual:
        return False, "ya está montado (primero se baja: el clic de arriba es bajarse)", None
    if que == SUBIR:
        if montura_de(usn) is None:
            return False, "no tiene ninguna montura marcada", None
        _poner(usn, rid, SUBIR, usn)
        return True, "se sube a la suya", None
    if que == UNIRSE:
        if dueno_slot is None:
            dueno = _pareja_en_sala(usn, rid)
        else:
            dueno = int(mesa_de(rid).get(int(dueno_slot), 0) or 0)
        if not dueno or dueno == int(usn):
            return False, f"no hay otro jugador en el casillero {dueno_slot}", None
        kp = montura_de(dueno)
        if kp is None:
            return False, f"usn={dueno} no tiene montura", None
        if not montura_flags(kp).get("pareja"):
            return False, f"la montura {kp} es de uno solo (Couple=0)", None
        arriba = [u for u in _arriba_de(dueno, rid) if u != int(usn)]
        if any(u != dueno for u in arriba):
            return False, f"la montura {kp} de usn={dueno} ya tiene a dos arriba", AVISO_OCUPADA
        if _item2019(kp) in ITEMS_POR_SEXO and dueno in arriba and _sexo(dueno) == _sexo(usn):
            return False, f"0x7B1: el asiento de su sexo ya lo usa el dueño (usn={dueno})", AVISO_SIN_LUGAR
        _poner(usn, rid, UNIRSE, dueno)
        return True, f"se une a la montura {kp} de usn={dueno}", None
    return False, f"acción desconocida {que}", None


def al_salir(usn, otros_tambien=True):
    """Se fue de la sala: se baja; y los que iban en SU montura también (el objeto se va con él), con su FF15."""
    if not usn:
        return
    with _lock:
        e = ESTADO.get(int(usn))
    _poner(usn, None, 0)
    if otros_tambien and e:
        for u in _arriba_de(int(usn), e[0]):
            if u != int(usn):
                _poner(u, None, 0)
                _repintar(u, f"se fue el dueño de la montura (usn={usn})")


def responder(payload):
    """FFFB: `[usn][vcode][accion][casillero del dueño]` -> `FFFB [resultado][byte]`. Repinta a toda la sala si
    cambió algo. El casillero sólo cuenta para unirse (2); 0xFF o ausente = la pareja."""
    from .basedatos import sesion_valida                                   # noqa: PLC0415
    if len(payload) < 13:
        return frame(0xFB, b"\x01\x00")
    usn, vcode, que = struct.unpack_from("<IQB", payload)
    dueno_slot = payload[13] if len(payload) >= 14 and payload[13] != 0xFF else None
    if not sesion_valida(usn, vcode):
        log("SALA", f"  ⛔ MONTURA: sesión inválida usn={usn}")
        return frame(0xFB, b"\x01\x00")
    antes = _estado(usn)
    ok, motivo, aviso = accion(usn, que, dueno_slot)
    if aviso:
        try:
            from .lobby_carrera import aviso_sistema                       # noqa: PLC0415
            st, _rid = _sala_de(usn)
            if st is not None:
                aviso_sistema(st, aviso)
        except Exception:                                                  # noqa: BLE001
            pass
    k = montura_de(usn)
    b = byte_de(usn, k)
    log("SALA", f"  🐴 MONTURA usn={usn} acción={que} casillero={dueno_slot} -> {'ok' if ok else 'NO'} ({motivo});"
                f" byte=0x{b:02X}")
    if ok and _estado(usn) != antes:
        _repintar(usn, motivo)
    return frame(0xFB, bytes([0 if ok else 1, b]))


def _repintar(usn, motivo):
    """El FF15 (CmdRoomUserInfo: «actualizar a quien YA está en la sala») de este jugador a toda la sala — el 2019
    manda el 0xF4 a todos. ⛔ NO el repintado de la ropa (FF0E + FF0C + FF15): ése lo SACA y lo vuelve a crear, y la
    sala lo saluda otra vez («X ha entrado a la sala de juego» + el gesto de saludo encima de la montura; medido el
    30-oct con jugadora_prueba y cuenta_admin)."""
    try:
        from .salas import CONEXIONES, _ocupante_de, ff15_de, mesa_de      # noqa: PLC0415
        st = CONEXIONES.get(int(usn))
        rid = getattr(st, "room_id", None) if st is not None else None
        slot = getattr(st, "room_slot", None) if st is not None else None
        if rid is None or slot is None:
            return
        occ = _ocupante_de(int(usn), slot)
        try:
            from .basedatos import db_anillo_de_pareja, db_pareja_de         # noqa: PLC0415
            pj = int(db_pareja_de(int(usn)) or 0)
            sp = next((int(s) for s, u in mesa_de(rid).items() if int(u) == pj), None) if pj else None
            if sp is not None:
                occ["pareja_slot"] = sp
                occ["anillo"] = db_anillo_de_pareja(int(usn))
        except Exception:                                                  # noqa: BLE001
            pass
        p = ff15_de(occ, rid)
        n = 0
        for u in mesa_de(rid).values():
            c = CONEXIONES.get(int(u))
            if c is not None and not getattr(c, "cerrado", False):
                c.send_ff55(0x15, p, name=f"FF15 montura de usn={usn} ({motivo})")
                n += 1
        log("SALA", f"  🐴 MONTURA: FF15 de usn={usn} a {n} de la sala {rid}")
    except Exception as e:                                                 # noqa: BLE001
        log("SALA", f"  ⚠ MONTURA: no pude avisar a la sala (usn={usn}): {e!r}")
