# -*- coding: utf-8 -*-
"""maquina — la PC desde la que entra cada cuenta (el «HWID»).

En el `FF02` de la lobby el cliente manda, al final, la MAC de su placa de red (`cifrado.leer_challenge_ff02`
documenta el layout). Con eso, al entrar al lobby (`lobby.handle_lobby`):

  · si esa PC está baneada (`maquinas_baneadas`), no entra;
  · si con esta cuenta la PC pasaría `MAX_CUENTAS_POR_MAQUINA` cuentas a la vez, no entra (el tope por IP de
    `multicuenta.py` no ve al que pone cada cliente detrás de otra VPN; éste sí);
  · si entra, queda anotado que esa cuenta usó esa PC (`.maquina <apodo>` lo muestra a un GM, y banear la cuenta
    banea esas PC: `almacen.banear_cuenta`).

★ PRIVACIDAD: la MAC NO se guarda ni se escribe en el log. Se guarda una huella = HMAC-SHA256(clave, MAC), y la
  clave es del server (`R2_SAL_MAQUINA`, o `datos.maquina.key` al lado de la base, que se crea sola y no se sube).
  Sin la clave, la huella no sirve para buscar una MAC. Lo que no se vio en `MAQUINA_GUARDAR_DIAS` se olvida.
⚠ SEÑAL BLANDA: la MAC la manda el cliente. Un cliente tocado la puede cambiar o mandar vacía; sin MAC válida no
  se aplica nada (salvo `MAQUINA_EXIGIR`). Frena al que no se toma el trabajo, no al decidido.
"""
import hashlib
import hmac
import os
import re
import secrets
import threading

from .ajustes import MAQUINA_EXIGIR, MAQUINA_GUARDAR_DIAS, MAX_CUENTAS_POR_MAQUINA
from .registro import log

_MAC = re.compile(r"^[0-9A-F]{2}(?:[-:]?[0-9A-F]{2}){5}$")
_NULAS = {"000000000000", "FFFFFFFFFFFF"}


def leer_mac_ff02(payload):
    """La MAC del `FF02` de la lobby, normalizada a 12 hex en mayúsculas, o None si no hay una válida.
    Camina los campos largo-prefijados igual que `leer_challenge_ff02` y exige que la MAC cierre JUSTO el paquete."""
    try:
        i = 4 + 5                       # usn + Location/Age/Gender/relleno
        for _ in range(4):              # IP local, dos campos vacíos, y la cuenta
            i += 1 + payload[i]
        i += 4                          # el challenge
        n = payload[i]
        if i + 1 + n != len(payload):
            return None
        crudo = bytes(payload[i + 1:i + 1 + n]).decode("ascii").strip().upper()
    except (IndexError, TypeError, UnicodeDecodeError):
        return None
    if not _MAC.match(crudo):
        return None
    mac = crudo.replace("-", "").replace(":", "")
    return None if mac in _NULAS else mac


def sin_mac(payload):
    """El `FF02` sin la MAC (para el log): corta antes de su largo. Si no se puede caminar, sólo los primeros 9 bytes."""
    try:
        i = 4 + 5
        for _ in range(4):
            i += 1 + payload[i]
        i += 4
        if i + 1 + payload[i] == len(payload):
            return payload[:i]
    except (IndexError, TypeError):
        pass
    return payload[:9]


_clave = None
_clave_lock = threading.Lock()


def _ruta_clave():
    from . import almacen
    return os.path.splitext(almacen.BASE)[0] + ".maquina.key"


def clave():
    """La clave del HMAC: `R2_SAL_MAQUINA`, o la del archivo al lado de la base (se crea la primera vez)."""
    global _clave
    with _clave_lock:
        if _clave is None:
            env = os.environ.get("R2_SAL_MAQUINA", "").strip()
            if env:
                _clave = env.encode("utf-8")
            else:
                ruta = _ruta_clave()
                try:
                    with open(ruta, "r", encoding="ascii") as f:
                        _clave = f.read().strip().encode("ascii")
                except FileNotFoundError:
                    _clave = b""
                if not _clave:
                    _clave = secrets.token_hex(32).encode("ascii")
                    with open(ruta, "w", encoding="ascii") as f:
                        f.write(_clave.decode("ascii"))
                    log("LOBBY", f"  🔑 clave nueva de huellas de máquina en {ruta} (no la pierdas: sin ella las "
                                 f"huellas guardadas dejan de coincidir)")
        return _clave


def huella(mac, k=None):
    """HMAC-SHA256(clave, MAC normalizada), en hex (32 caracteres). None si no hay MAC."""
    if not mac:
        return None
    return hmac.new(k if k is not None else clave(), mac.encode("ascii"), hashlib.sha256).hexdigest()[:32]


def cuentas_de_maquina(h, conexiones, cuenta_de, menos=None):
    """Las CUENTAS distintas conectadas ahora desde la PC `h`, sin contar `menos` (la que está entrando)."""
    cuentas = set()
    for st in list(conexiones.values()):
        if getattr(st, "cerrado", False) or getattr(st, "reemplazada", False):
            continue
        if not h or getattr(st, "maquina", None) != h:
            continue
        cuenta = cuenta_de(getattr(st, "usn", None))
        if cuenta != menos:
            cuentas.add(cuenta)
    return cuentas


def supera_tope(h, cuenta, conexiones, cuenta_de, tope=None):
    """True si entrar con `cuenta` desde la PC `h` pasaría el tope de cuentas a la vez. Pura (salvo `cuenta_de`)."""
    tope = MAX_CUENTAS_POR_MAQUINA if tope is None else tope
    if not tope or not h:
        return False
    return len(cuentas_de_maquina(h, conexiones, cuenta_de, menos=cuenta)) >= tope


def rechazar_al_entrar(st, usn, payload):
    """Al entrar al lobby: lee la PC, la deja en `st.maquina` y decide. True (y queda en el log) si NO entra; el
    llamador cierra. Si entra, anota que esta cuenta usó esta PC."""
    from . import almacen
    from .multicuenta import cuenta_de
    from .salas import CONEXIONES
    h = huella(leer_mac_ff02(payload))
    st.maquina = h
    cuenta = cuenta_de(usn)
    if h is None:
        if MAQUINA_EXIGIR:
            log("LOBBY", f"  ⛔ MÁQUINA: {cuenta} (usn={usn}) entró sin MAC válida y MAQUINA_EXIGIR está prendido")
            return True
        return False
    try:
        ban = almacen.maquina_baneada(h)
    except Exception as e:                    # noqa: BLE001
        log("LOBBY", f"  ⚠ MÁQUINA: no pude mirar el baneo ({e!r}); entra")
        ban = None
    if ban:
        log("LOBBY", f"  ⛔ MÁQUINA BANEADA: {cuenta} (usn={usn}) entra desde la PC {h[:8]}… baneada por "
                     f"{ban.get('cuenta')!r} ({ban.get('motivo') or 'sin motivo'}, {ban.get('cuando')})")
        return True
    if supera_tope(h, cuenta, CONEXIONES, cuenta_de):
        ya = sorted(cuentas_de_maquina(h, CONEXIONES, cuenta_de, menos=cuenta))
        log("LOBBY", f"  ⛔ MULTICUENTA (máquina): la PC {h[:8]}… ya tiene {len(ya)} cuenta(s) conectada(s) {ya} -> "
                     f"no entra {cuenta} (usn={usn}, tope {MAX_CUENTAS_POR_MAQUINA})")
        return True
    if not str(cuenta).startswith("usn:"):
        try:
            almacen.maquinas_anotar(h, cuenta, MAQUINA_GUARDAR_DIAS)
        except Exception as e:                # noqa: BLE001
            log("LOBBY", f"  ⚠ MÁQUINA: no pude anotar {cuenta} en {h[:8]}…: {e!r}")
    return False


def comando_gm(args, quien=""):
    """`.maquina <apodo>` | `.maquina perdonar <apodo>` -> las líneas para el GM."""
    from . import almacen
    if not args:
        return [".maquina <apodo>  qué cuentas entraron desde su PC | .maquina perdonar <apodo>  sacar el baneo de PC"]
    perdonar = args[0].lower() == "perdonar" and len(args) > 1
    apodo = " ".join(args[1:] if perdonar else args)
    uid = almacen.uid_por_nick(apodo)
    cuenta = almacen.cuenta_de_uid(uid)[0] if uid is not None else None
    if not cuenta:
        return [f"maquina: no encuentro a {apodo!r}"]
    if perdonar:
        n = almacen.maquinas_perdonar_de(cuenta)
        log("LOBBY", f"  🕊 {quien!r} sacó el baneo de {n} PC de {cuenta!r} ({apodo})")
        return [f"maquina: {n} PC de {apodo} desbaneada(s) (la cuenta sigue como esté: eso va aparte)"]
    huellas = almacen.maquinas_de_cuenta(cuenta)
    if not huellas:
        return [f"maquina: {apodo} no tiene PC anotada (entró sin MAC, o hace más de {MAQUINA_GUARDAR_DIAS} días)"]
    lineas = [f"maquina: {apodo} ({cuenta}) entró desde {len(huellas)} PC"]
    for h in huellas[:5]:
        otras = [c for c in almacen.maquinas_cuentas_de(h) if c[0] != cuenta]
        ban = " BANEADA" if almacen.maquina_baneada(h) else ""
        lineas.append(f"  PC {h[:8]}{ban}: " + (", ".join(f"{c} (x{v}, ult. {u[:10]})" for c, _p, u, v in otras[:8])
                                                if otras else "ninguna otra cuenta"))
    return lineas
