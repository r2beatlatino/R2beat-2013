# -*- coding: utf-8 -*-
r"""gm — quiénes son GM, leído de un ARCHIVO y no del código.

POR QUE UN ARCHIVO Y NO UNA LISTA EN EL `.py`
---------------------------------------------
Es como lo hacía el CBT (`R2_ADMIN_UIDS` en un `admin.conf` de systemd), y las tres razones
siguen valiendo enteras:

    1. el código se puede publicar sin publicar quién manda
    2. agregar o sacar un GM NO es un cambio de código: no hay diff, no hay deploy, no hay
       riesgo de arrastrar otra cosa
    3. cada instalación tiene su lista, y la de local no es la de prod

★ Y una mejora sobre el CBT: **allá había que reiniciar el proceso** para que tomara la lista
  nueva, *"y eso echa a TODOS los conectados"*. Acá el archivo se **relee solo** cuando cambia
  (se mira la fecha del archivo), así que agregar un GM es editar un renglón y listo.

⛔⛔ EL MODO DE FALLA QUE HAY QUE EVITAR — la lección cara del CBT
------------------------------------------------------------------
De `SUBIR_A_PROD_20260802.md`: *"si el server se arranca sin esa variable la lista queda VACÍA
y los comandos **se comportan como chat normal, sin ningún error**"*. Y peor: un comando de la
misma familia seguía andando, que es la peor pista posible.

El arreglo de allá no fue tocar la puerta: fue **hacerla hablar al arrancar**. Acá se hace lo
mismo, y es obligatorio:

    ⇒ `resumen()` se imprime en el log de arranque, SIEMPRE, diga lo que diga.
      Una puerta que no anuncia su configuración no se puede auditar.

EL FORMATO DEL ARCHIVO
----------------------
Un GM por renglón. Se acepta lo que un humano tiene a mano:

    6697            un uid (todo números)
    jugador18     un login (como entra al juego)
    @ElApodo        un apodo del personaje (con @ adelante)
    # esto es un comentario

⚠ El login es **sensible a mayúsculas**, igual que el login del juego: en el CBT `Junior` y
  `junior` son dos cuentas distintas (60 pares así). Bajar todo a minúsculas las fusionaría.

DONDE VIVE
----------
    `R2_GM_ARCHIVO` si está definida, si no `gm.txt` al lado del server.
⛔ **Está en `.gitignore`**: tiene nombres de cuentas reales y no se versiona.
"""
import os
import threading

from .basedatos import db_uids_por_nick
from .registro import log

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ★ `gm.txt` se mudó a `servidor/` el 2026-09-16, con el resto de los datos del server: así lo que
#   se sube a prod es una carpeta sola y no hay archivos sueltos que olvidar.
#   ⚠ Se sigue mirando la raíz como SEGUNDA opción: en prod el archivo viejo puede seguir ahí hasta
#     el próximo deploy, y quedarse sin lista de GM es mudo (nadie tiene permisos y nadie avisa).
_AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA = os.environ.get("R2_GM_ARCHIVO") or next(
    (p for p in (os.path.join(_AQUI, "gm.txt"), os.path.join(RAIZ, "gm.txt"))
     if os.path.isfile(p)), os.path.join(_AQUI, "gm.txt"))

_lock = threading.Lock()
_estado = {"uids": frozenset(), "fecha": None, "renglones": 0, "sin_resolver": []}


def _uid_por_login(login):
    """El uid de una cuenta por su login. `None` si no existe.

    ⚠ Consulta directa y pidiendo SÓLO el uid: `cargar_cuentas()` traería las 4.800 cuentas
      **con su `pass_hash`**, y no hay ningún motivo para tener eso en memoria por una lista de
      cinco GMs.
    """
    from . import almacen
    try:
        with almacen._lock:                                  # noqa: SLF001
            fila = almacen.conectar().execute(
                "SELECT uid FROM users WHERE username = ?", (login,)).fetchone()
        return int(fila[0]) if fila else None
    except Exception as e:                                   # noqa: BLE001
        log("GM   ", f"  ⚠ no pude buscar el login {login!r}: {e!r}")
        return None


def _leer(ruta=None):
    """Lee el archivo y resuelve cada renglón a un uid. Devuelve (uids, cuántos, no_resueltos).
    Sin `ruta`, el de los GM; `admin.txt` y `streamers.txt` usan el mismo formato."""
    ruta = ruta or RUTA
    if not os.path.isfile(ruta):
        return frozenset(), 0, []
    uids, n, feos = set(), 0, []
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for cruda in f:
            linea = cruda.split("#", 1)[0].strip()
            if not linea:
                continue
            n += 1
            if linea.isdigit():                              # un uid, directo
                uids.add(int(linea))
                continue
            if linea.startswith("@"):                        # un apodo
                hallados = db_uids_por_nick(linea[1:]) or []
                if not hallados:
                    feos.append(f"{linea} (no hay personaje con ese apodo)")
                elif len(hallados) > 1:
                    # ⚠ El apodo NO es único: 203 repetidos sobre 4.807 personajes. Dar permisos
                    #   de GM "a uno cualquiera" es exactamente como se regala una cuenta ajena.
                    feos.append(f"{linea} (ese apodo lo tienen {len(hallados)} personajes: "
                                f"{hallados[:5]} — usá el uid)")
                else:
                    uids.add(int(hallados[0]))
                continue
            u = _uid_por_login(linea)                        # un login
            if u is None:
                feos.append(f"{linea} (no existe esa cuenta)")
            else:
                uids.add(u)
    return frozenset(uids), n, feos


def recargar(motivo=""):
    """Relee el archivo ahora mismo. Devuelve el conjunto de uids."""
    with _lock:
        uids, n, feos = _leer()
        _estado.update(uids=uids, renglones=n, sin_resolver=feos,
                       fecha=os.path.getmtime(RUTA) if os.path.isfile(RUTA) else None)
    if motivo:
        log("GM   ", f"lista de GM releída{motivo}: {len(uids)} uid(s)")
    return uids


def _al_dia():
    """Relee si el archivo cambió desde la última vez. Barato: mira la fecha, no el contenido."""
    fecha = os.path.getmtime(RUTA) if os.path.isfile(RUTA) else None
    if fecha != _estado["fecha"]:
        recargar(" (el archivo cambió)")
    return _estado["uids"]


def uids():
    """Los uid que son GM, al día."""
    return _al_dia()


def es_gm(st):
    """¿La conexión `st` es de un GM?

    ⚠ Un `usn` de 0 o None NO es GM. Parece obvio; es exactamente el default de una conexión
      recién abierta, y un `in` contra un conjunto que contenga 0 la dejaría pasar.
    """
    u = int(getattr(st, "usn", 0) or 0)
    return u > 0 and u in _al_dia()


def resumen():
    """La línea que va al log de ARRANQUE. ⛔ Se imprime siempre, diga lo que diga.

    Es la lección del CBT: una puerta que falla en silencio no es auditable. Si la lista está
    vacía hay que poder verlo en el log, no descubrirlo porque un comando "no hace nada".
    """
    _al_dia()
    e = _estado
    if not os.path.isfile(RUTA):
        return (f"GM: ⚠ NO existe {RUTA} -> lista VACÍA, ningún comando de GM va a funcionar. "
                f"Creá el archivo con un uid o un login por renglón.")
    partes = [f"GM: {len(e['uids'])} uid(s) desde {RUTA}"]
    if e["uids"]:
        partes.append(f"-> {sorted(e['uids'])}")
    else:
        partes.append("-> ⚠ VACÍA: ningún comando de GM va a funcionar")
    if e["sin_resolver"]:
        partes.append(f"⚠ {len(e['sin_resolver'])} renglón(es) que NO pude resolver: "
                      + " · ".join(e["sin_resolver"][:5]))
    return "  ".join(partes)


# ── LOS OTROS DOS ROLES: admin y streamer ──────────────────────────────────────────────────────────
#   Mismo formato que `gm.txt` y al lado de él: `admin.txt` y `streamers.txt`. Hoy sirven para una sola
#   cosa en el juego: quién puede ponerle CLAVE a una sala (`CLAVE_DE_SALA_ROLES`). Se releen solos.
_otros = {}


def _lista(nombre):
    ruta = os.path.join(os.path.dirname(RUTA), nombre)
    fecha = os.path.getmtime(ruta) if os.path.isfile(ruta) else None
    with _lock:
        guardado = _otros.get(nombre)
        if guardado is None or guardado[0] != fecha:
            guardado = (fecha, _leer(ruta)[0])
            _otros[nombre] = guardado
    return guardado[1]


def admins():
    return _lista("admin.txt")


def streamers():
    return _lista("streamers.txt")


def rol_de(uid):
    """'admin' · 'gm' · 'streamer' · None. Un uid 0/None nunca tiene rol. El orden manda: admin > gm > streamer."""
    u = int(uid or 0)
    if u <= 0:
        return None
    if u in admins():
        return "admin"
    if u in uids():
        return "gm"
    if u in streamers():
        return "streamer"
    return None
