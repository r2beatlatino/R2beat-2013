# -*- coding: utf-8 -*-
"""antitrampa_eventos — EL REGISTRO CENTRAL del antitrampa (26-nov-2026).

Toda detección, venga de donde venga, pasa por acá y queda como UN evento en `antitrampa_eventos`:

    dll (R2AT por FF59) ─┐
    cartel (FF28) ───────┼─► antitrampa.anotar ─► registrar() ─► cola ─► hilo escritor ─► antitrampa_eventos ─► tablero
    farmeo / servidor ───┘                                                                (y antitrampa.jsonl, como antes)

Cada evento lleva: id único, usn, cuenta, apodo, sesión del juego, partida, fecha, categoría, regla, módulo que lo vio,
origen (servidor = comprobado por el server; cliente = lo declara la dll), descripción, evidencia (JSON), riesgo,
confianza, reincidencias (eventos anteriores de esa regla en esa cuenta), repeticiones (la misma detección en la misma
sesión NO crea otra fila), versiones del cliente y del antitrampa, lo que hizo el server y el estado de revisión.

⚡ Nada de esto frena el juego: `registrar` sólo arma el dict y lo mete en una cola; la base la escribe un hilo aparte.
⛔ No se guarda nada personal que no haga falta: ni la IP, ni la MAC, ni nombres de archivos del usuario fuera de los
   del propio juego. La evidencia es lo que mandó la dll (claves R2AT) y lo que midió el server.

Las ACCIONES de los administradores (tablero o chat) también viven acá: revisar, confirmar, descartar (falso positivo),
advertir, suspender, banear y deshacer. Cada una queda en `antitrampa_acciones` con quién la hizo.
"""
import datetime
import json
import queue
import threading
import time
import uuid

from .ajustes import ANTITRAMPA_CATEGORIAS, ANTITRAMPA_CLASIFICACION
from .registro import log

RIESGOS = ("informativo", "bajo", "medio", "alto", "critico")
ESTADOS = ("nuevo", "revisado", "confirmado", "descartado", "sancionado")
_SIN_CLASIFICAR = ("conducta_anormal", "bajo", 30, "servidor")

_cola = queue.Queue(maxsize=20000)
_hilo = None
_hilo_lock = threading.Lock()
_perdidos = 0                       # eventos que no entraron en la cola (llena): se dice en el tablero
_vistos = {}                        # (sesión, regla, firma) -> (evento, cuando): la misma detección = repetición
_vistos_lock = threading.Lock()
_VISTOS_MAX = 20000
_suscriptores = []                  # funciones a avisar con cada evento NUEVO (el tablero, para el tiempo real)


def clasificar(regla):
    """-> (categoría, riesgo, confianza, origen) de la regla (ajustes.ANTITRAMPA_CLASIFICACION)."""
    return ANTITRAMPA_CLASIFICACION.get(regla, _SIN_CLASIFICAR)


def ahora_txt():
    return datetime.datetime.now().isoformat(sep=" ", timespec="seconds")


def registrar(regla, descripcion, *, usn=None, cuenta=None, nick="", sesion=None, partida=None, modulo="servidor",
              accion="registrar", evidencia=None, version_cliente=None, version_antitrampa=None, firma=""):
    """Un evento del antitrampa. Barato (no toca la base). -> (id único del evento, es_nuevo).

    `firma` distingue detecciones de la misma regla que NO son la misma cosa (p. ej. dos programas distintos); la misma
    (sesión, regla, firma) otra vez es una REPETICIÓN del evento anterior, no uno nuevo."""
    clave = (sesion or f"usn:{usn}", regla, str(firma)[:120])
    t = ahora_txt()
    with _vistos_lock:
        previo = _vistos.get(clave)
        if previo is not None:
            _vistos[clave] = (previo[0], time.monotonic())
            evento = previo[0]
        else:
            evento = uuid.uuid4().hex
            _vistos[clave] = (evento, time.monotonic())
            if len(_vistos) > _VISTOS_MAX:                     # los más viejos afuera (una sesión vieja ya no repite)
                for k, _v in sorted(_vistos.items(), key=lambda kv: kv[1][1])[:_VISTOS_MAX // 4]:
                    _vistos.pop(k, None)
    if previo is not None:
        _meter(("repetir", evento, t))
        return evento, False
    categoria, riesgo, confianza, origen = clasificar(regla)
    ev = {"evento": evento, "cuando": t, "ultimo": t, "usn": int(usn) if usn else None, "cuenta": cuenta,
          "nick": nick or "", "sesion": sesion, "partida": partida, "categoria": categoria, "regla": regla,
          "modulo": modulo, "origen": origen, "descripcion": str(descripcion)[:1000],
          "evidencia": json.dumps(evidencia or {}, ensure_ascii=False, default=str)[:8000],
          "riesgo": riesgo, "confianza": int(confianza), "version_cliente": version_cliente,
          "version_antitrampa": version_antitrampa, "accion": accion, "estado": "nuevo"}
    _meter(("insertar", ev))
    return evento, True


def poner_pendiente(evento, pendiente_id, accion="pendiente"):
    """El evento quedó para la tanda (`antitrampa_pendientes.id`)."""
    if evento and pendiente_id:
        _meter(("pendiente", evento, int(pendiente_id), accion))


def suscribir(f):
    """`f(evento_dict)` con cada evento NUEVO, ya guardado (en el hilo escritor: que sea rápida)."""
    _suscriptores.append(f)


def _meter(op):
    global _perdidos
    _arrancar()
    try:
        _cola.put_nowait(op)
    except queue.Full:
        _perdidos += 1


def _arrancar():
    global _hilo
    if _hilo is not None and _hilo.is_alive():
        return
    with _hilo_lock:
        if _hilo is None or not _hilo.is_alive():
            _hilo = threading.Thread(target=_escritor, daemon=True, name="antitrampa-eventos")
            _hilo.start()


def _escritor():
    from . import almacen
    while True:
        op = _cola.get()
        try:
            if op[0] == "insertar":
                ev = dict(op[1])
                ev["id"] = almacen.ev_insertar(ev)
                for f in list(_suscriptores):
                    try:
                        f(ev)
                    except Exception as e:                       # noqa: BLE001
                        log("TRAMP", f"  ⚠ suscriptor del registro: {e!r}")
            elif op[0] == "repetir":
                almacen.ev_repetir(op[1], op[2])
            elif op[0] == "pendiente":
                almacen.ev_poner_pendiente(op[1], op[2])
        except Exception as e:                                   # noqa: BLE001 — el hilo no se puede morir
            log("TRAMP", f"  ⚠ registro central: no pude guardar {op[0]}: {e!r}")
        finally:
            _cola.task_done()


def esperar(timeout=5.0):
    """Hasta que el hilo escritor vació la cola (pruebas y tablero). True si quedó vacía."""
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if _cola.unfinished_tasks == 0:
            return True
        time.sleep(0.01)
    return _cola.unfinished_tasks == 0


def estado_registro():
    return {"en_cola": _cola.qsize(), "perdidos": _perdidos, "vivo": bool(_hilo and _hilo.is_alive())}


# ═══ LAS ACCIONES DE LOS ADMINISTRADORES ═══════════════════════════════════════════════════════════════════════════
#   Todas: (admin, …) -> (ok, mensaje). Cada una queda en `antitrampa_acciones`. ⛔ Ninguna le muestra al jugador
#   detalles técnicos de la detección (qué regla, qué dirección, qué programa).
AVISO_AL_JUGADOR = ("Aviso del equipo de moderación: detectamos actividad irregular en tu cuenta. "
                    "Si continúa, la cuenta puede ser sancionada.")


def _conexiones_de_cuenta(cuenta):
    """Las conexiones vivas de los personajes de esa cuenta."""
    from . import almacen
    from .salas import CONEXIONES
    out = []
    for usn, c in list(CONEXIONES.items()):
        if c is None or getattr(c, "cerrado", False):
            continue
        try:
            if almacen.cuenta_de_uid(usn)[0] == cuenta:
                out.append(c)
        except Exception:                                        # noqa: BLE001
            pass
    return out


def _cuenta_de_evento(evento):
    from . import almacen
    fs = almacen.ev_listar({"evento": evento}, 1)
    return fs[0] if fs else None


def revisar(admin, evento, estado="revisado", nota=None):
    """Marca un evento como revisado / confirmado (lo vio un humano)."""
    from . import almacen
    if estado not in ("revisado", "confirmado", "nuevo"):
        return False, f"estado inválido: {estado}"
    ev = _cuenta_de_evento(evento)
    if not ev:
        return False, "no existe ese evento"
    n = almacen.ev_marcar(eventos=[evento], estado=estado, por=admin, nota=nota)
    almacen.at_accion(admin, estado, ev.get("cuenta"), ev.get("usn"), evento, nota or "")
    return bool(n), f"evento {estado}" if n else "ya estaba descartado o sancionado"


def descartar(admin, evento=None, cuenta=None, nota=None):
    """Falso positivo: el evento (o TODO lo abierto de la cuenta) queda descartado y sus pendientes de la tanda se
    perdonan (no suman falta)."""
    from . import almacen
    if evento:
        ev = _cuenta_de_evento(evento)
        if not ev:
            return False, "no existe ese evento"
        cuenta = ev.get("cuenta")
        evs = [evento]
        pendientes = [ev["pendiente"]] if ev.get("pendiente") else []
    elif cuenta:
        abiertos = [e for e in almacen.ev_listar({"cuenta": cuenta}, 2000) if e["estado"] in ("nuevo", "revisado", "confirmado")]
        evs = [e["evento"] for e in abiertos]
        pendientes = [e["pendiente"] for e in abiertos if e.get("pendiente")]
        pendientes += [f["id"] for f in almacen.antitrampa_pendientes(0) if f.get("cuenta") == cuenta]
    else:
        return False, "falta el evento o la cuenta"
    n = almacen.ev_marcar(eventos=evs, estado="descartado", por=admin, nota=nota) if evs else 0
    p = almacen.antitrampa_resolver(sorted(set(pendientes)), "perdonada", admin) if pendientes else 0
    almacen.at_accion(admin, "descartar", cuenta, None, evento, f"{n} evento(s), {p} pendiente(s) perdonado(s). {nota or ''}")
    return True, f"descartado: {n} evento(s), {p} pendiente(s) de la tanda perdonado(s)"


def advertir(admin, cuenta, texto=None, evento=None):
    """Un aviso al jugador (si está conectado) y queda anotado. Texto genérico: sin detalles técnicos."""
    from . import almacen
    from .salas import avisar_a_uno
    texto = (texto or AVISO_AL_JUGADOR).strip()[:200]
    conns = _conexiones_de_cuenta(cuenta)
    for c in conns:
        try:
            avisar_a_uno(c, texto)
        except Exception as e:                                   # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude advertir a {cuenta!r}: {e!r}")
    almacen.at_accion(admin, "advertir", cuenta, None, evento, f"{texto} (conectado: {bool(conns)})")
    if evento:
        almacen.ev_marcar(eventos=[evento], estado="confirmado", por=admin, nota="advertido")
    return True, "advertencia enviada" if conns else "advertencia anotada (no está conectado: la verá en el registro)"


def _echar(cuenta, motivo):
    from . import antitrampa
    for c in _conexiones_de_cuenta(cuenta):
        antitrampa.cerrar_conexion(c, motivo)


def suspender(admin, cuenta, horas, motivo="", evento=None):
    from . import almacen
    try:
        horas = float(horas)
    except (TypeError, ValueError):
        return False, "horas inválidas"
    if not (0 < horas <= 24 * 365):
        return False, "entre 1 hora y un año"
    if not almacen.cuenta_estado(cuenta):
        return False, f"no existe la cuenta {cuenta!r}"
    hasta = almacen.suspender_cuenta(cuenta, horas, motivo, admin)
    _echar(cuenta, f"suspendida hasta {hasta}")
    almacen.at_accion(admin, "suspender", cuenta, None, evento, f"{horas:g} h, hasta {hasta}. {motivo}")
    if evento:
        almacen.ev_marcar(eventos=[evento], estado="sancionado", por=admin, nota=f"suspendida {horas:g} h")
    return True, f"suspendida hasta {hasta}"


def levantar(admin, cuenta):
    from . import almacen
    ok = almacen.levantar_suspension(cuenta)
    almacen.at_accion(admin, "levantar_suspension", cuenta, None, None, "")
    return ok, "suspensión levantada" if ok else "no estaba suspendida"


def banear(admin, cuenta, motivo="", evento=None):
    """Baneo MANUAL permanente (`BANNED:`, el mismo de siempre: todo login lo rechaza)."""
    from . import almacen
    if not almacen.cuenta_estado(cuenta):
        return False, f"no existe la cuenta {cuenta!r}"
    cambio = almacen.banear_cuenta(cuenta)
    _echar(cuenta, "baneada")
    almacen.at_accion(admin, "banear", cuenta, None, evento, motivo)
    if evento:
        almacen.ev_marcar(eventos=[evento], estado="sancionado", por=admin, nota="baneada")
    return True, "cuenta baneada" if cambio else "ya estaba baneada"


def desbanear(admin, cuenta):
    from . import almacen
    ok = almacen.desbanear_cuenta(cuenta)
    almacen.at_accion(admin, "desbanear", cuenta, None, None, "")
    return ok, "baneo levantado" if ok else "no estaba baneada"


def categorias():
    return dict(ANTITRAMPA_CATEGORIAS)
