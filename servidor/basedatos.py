# -*- coding: utf-8 -*-
"""basedatos — chars_db.json: personajes, inventario, equipo, misiones

Cortado de `server_login2013.py`. El código es el MISMO, movido tal cual.
"""
import datetime
import hashlib
import json
import os
import secrets
from . import shop_catalog
import struct
import time

from . import almacen
from .ajustes import (
    DATE_WIRE_OFFSET_DAYS,
    SESION_VIVAS,
    PERM_SENTINEL,
    RCOIN,
    SESION_PASO,
    SESION_PASOS_MAX,
    SESION_TTL_H,
)
from .registro import (
    log,
)

# ★ La raíz del proyecto, capturada ANTES de la reasignación de abajo. Tiene que quedar acá:
#   después de esa línea, `__file__` ya no apunta a este archivo y el cálculo da un nivel de más.
#   (Es exactamente el error que cometí al escribir el default de `CHARS_DB`.)
import threading

# ★ El candado de `sesiones.json`. Ver `sesion_abrir`.
_SES_LOCK = threading.Lock()

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# El módulo se lee con rutas relativas a la RAÍZ del proyecto, no a
# `servidor/`. Viene de cuando todo era un archivo solo; sacarlo rompe la
# lectura de las tablas del cliente (wing.txt / face.txt).
__file__ = os.path.join(RAIZ, "server_login2013.py")   # rutas relativas como en el original

SESIONES = os.environ.get("R2_SESIONES") or os.path.join(RAIZ, "sesiones.json")


def sesion_valida(usn, vcode):
    """¿El par `(usn, vcode)` corresponde a una sesión que abrió NUESTRO launcher?

    ★★★★★ ES EL LOGIN NATIVO. El cliente 2013 manda `FF01 [usn:u32][vcode:u64]` y los dos salen de
    su LÍNEA DE COMANDOS (`argv[1]` y `argv[2]`): quien lanza el exe decide quién dice ser. Sin esta
    validación, cualquiera que corra el juego a mano entra como el usn que se le antoje.

    ⚠ **SIN ARCHIVO SE DEJA PASAR.** Si `sesiones.json` no existe, esto devuelve `True` y lo avisa
    en el log. Es a propósito: lanzar el exe a mano (sin launcher) tiene que seguir funcionando
    mientras se prueba. En cuanto el launcher escribe el archivo, la validación pasa a ser real.

    ★ TOLERANCIA `+10`: se acepta `vcode + SESION_PASO*n`. En el CBT está medido que el cliente le
      suma 10 al token en cada re-login, y con 8 canales los re-logins son constantes. Acá **no
      está confirmado** (ver `SESION_PASO` en `ajustes.py`); si este cliente no suma, `n` sale
      siempre 0 y no cambia nada.

    ⛔ Y se rechaza el vcode que pertenece a OTRO usn: es la suplantación que el CBT sufrió en
       producción (un jugador recibió la sesión de otro).
    """
    if not os.path.isfile(SESIONES):
        log("LOGIN", f"  ⚠ LOGIN ABIERTO: no existe {os.path.basename(SESIONES)}, "
                     f"entra cualquiera. Lanzá con `launcher2013.py` para que valide de verdad.")
        return True
    try:
        with open(SESIONES, "r", encoding="utf-8") as f:
            ses = json.load(f)
    except Exception as e:
        log("LOGIN", f"  ⚠ no pude leer las sesiones ({e!r}) -> RECHAZO por las dudas")
        return False

    usn, vcode = int(usn), int(vcode)
    s = ses.get(str(usn))
    if not s:
        # ¿El vcode es de otro? Distinguirlo cambia el mensaje de "no abriste sesión" a
        # "estás usando la sesión ajena", que es un síntoma completamente distinto.
        _de = next((u for u, d in ses.items() if _mismo_vcode(d.get("vcode"), vcode)), None)
        log("LOGIN", f"  ⛔ usn={usn} no tiene sesión abierta"
                     + (f" — y ese vcode es del usn={_de} (¿suplantación?)" if _de else ""))
        return False
    # ★ Vale CUALQUIERA de los vcodes vigentes de esa cuenta (ver `sesion_abrir`): con uno solo,
    #   abrir un segundo cliente dejaba al primero afuera en cuanto cambiaba de canal.
    _vivos = list(s.get("vcodes") or ([s["vcode"]] if s.get("vcode") is not None else []))
    if not any(_mismo_vcode(v, vcode) for v in _vivos):
        log("LOGIN", f"  ⛔ usn={usn}: el vcode no coincide (llegó {vcode}, "
                     f"tenemos {len(_vivos)} vigente(s): {_vivos})")
        return False
    _abierta = float(s.get("abierta", 0) or 0)
    if _abierta and (time.time() - _abierta) > SESION_TTL_H * 3600:
        log("LOGIN", f"  ⛔ usn={usn}: la sesión venció (más de {SESION_TTL_H} h). Relanzá el launcher.")
        return False
    return True


CUENTAS = os.environ.get("R2_CUENTAS") or os.path.join(RAIZ, "cuentas.json")


def hash_pass(clave):
    """SHA-256 en HEX MAYÚSCULA. Es lo único que viaja y lo único que se guarda: la contraseña
    en claro no toca ni el disco ni el cable."""
    return hashlib.sha256(clave.encode("utf-8")).hexdigest().upper()


# ★★★ 2026-09-05 — LAS CUENTAS Y LOS PERSONAJES VIVEN EN SQLITE (`datos.db`), NO EN LOS JSON.
#   La forma de los diccionarios NO cambió: `cuentas_load()` devuelve lo mismo que devolvía
#   `json.load(cuentas.json)` y `db_load()` lo mismo que `chars_db.json`. Por eso las otras ~26
#   funciones de este archivo y sus 11 consumidores siguen igual, sin tocarles una línea.
#   El porqué del cambio está en `servidor/almacen.py`; el esquema, en `servidor/esquema.py`.
#   ⚠ Los `.json` quedan en disco como respaldo de la migración. YA NO SE LEEN NI SE ESCRIBEN.
def cuentas_load():
    return almacen.leer_cuentas()


def cuentas_save(d):
    almacen.guardar_cuentas(d)


def cuenta_verificar(usuario, pass_hash):
    """El `usn` de esa cuenta si la clave coincide, o `None`.

    ⛔ ACÁ DECÍA "el usuario NO distingue mayúsculas" y bajaba a minúsculas. **Cambiado el
      2026-09-05: ahora compara EXACTO, como el CBT.** No es un cambio de gusto — en el CBT
      `Junior` y `junior` son dos cuentas distintas, y hay 60 pares así (122 cuentas, 71 con
      partidas de verdad). Comparar en minúsculas las fusiona y borra una de cada par en silencio.
      ⚠ El costo asumido: quien se equivoque de mayúscula no entra. Es como funciona hoy el CBT.
      Ver la nota larga de `almacen.leer_cuentas`.
    """
    c = almacen.cuenta_de((usuario or "").strip())   # ★ 29-sep: UNA fila, no las 5.400 (`almacen.cuenta_de`)
    if not c:
        return None
    return int(c["usn"]) if str(c.get("pass", "")).upper() == str(pass_hash).upper() else None


def cuenta_crear(usuario, pass_hash, usn=None):
    """Crea la cuenta y devuelve `(usn, None)`, o `(None, motivo)`.

    El `usn` se asigna solo: el siguiente libre mirando **las cuentas Y los personajes**, para no
    pisar un char que ya existe (los personajes viven en `chars_db.json`, indexados por usn).
    """
    # ⛔ Ya NO se baja a minúsculas: el login es sensible a mayúsculas (ver `cuenta_verificar`).
    #   Se guarda tal como lo escribió, y con eso mismo va a tener que entrar.
    u = (usuario or "").strip()
    if not (3 <= len(u) <= 16) or not u.replace("_", "").isalnum():
        return None, "el usuario tiene que ser de 3 a 16 caracteres alfanuméricos"
    if len(str(pass_hash)) != 64:
        return None, "la clave llegó mal"
    d = cuentas_load()
    if u in d:
        return None, "ese usuario ya existe"
    if usn is None:
        _usados = {int(v["usn"]) for v in d.values()}
        # ★ 2026-09-05: acá sí hacen falta TODOS los uid, pero no los personajes enteros.
        #   Era `db_load()`, que arma los 4806 con su inventario y su ropa para tirarlos.
        _usados |= set(almacen.uids_usados())
        usn = max(_usados) + 1 if _usados else 1
    d[u] = {"usn": int(usn), "pass": str(pass_hash).upper(), "creada": time.time()}
    cuentas_save(d)
    return int(usn), None


def sesion_abrir(usn):
    """★ Sortea el `vcode` de la sesión, lo anota y lo devuelve. **Lo emite el SERVER**, no el
    launcher: es lo que hace que la identidad no dependa de la IP y funcione detrás de un NAT.

    ★ 62 BITS Y NO 64 — trampa medida en el CBT: el cliente parsea el argumento con `_strtoi64`,
      que es CON SIGNO, así que cualquier valor por encima de 2^63-1 satura en 0x7FFF…FF. Con 64
      bits al azar fallaría **la mitad de los logins**, intermitente e indiagnosticable.

    ⛔⛔ EL BUG QUE ARREGLA EL CANDADO (2026-09-12), reportado por anonimo03: *"hice doble clic en mi
      cliente y VARIOS se quedan estancados en cargando o en cambiando de canal"*.

      Esto era un **leer-modificar-escribir del archivo ENTERO, sin candado**:

          ses = json.load(...)          # lee TODAS las sesiones
          ses[mi_usn] = {...}           # cambia la mía
          json.dump(ses, ...)           # escribe TODAS de nuevo

      Con dos logins a la vez (un doble clic alcanza), el hilo A lee, el B lee, A escribe y B
      escribe **encima con la foto vieja** ⇒ la sesión de A desaparece o queda con el vcode
      anterior. Y el síntoma **no le sale al que duplicó**: le sale a CUALQUIERA que reconecte
      después, porque el cambio de canal **revalida** — de ahí los *"cargando"* eternos.
      En el log se ve exacto: `⛔ usn=7535: el vcode no coincide (llegó X, abrimos Y)`, en tres
      cuentas distintas seguidas.

    ★★★★★ Y ES PEOR DE LO QUE PARECÍA — medido reproduciendo la versión vieja con 40 hilos:
      el archivo **no queda incompleto: queda CORRUPTO** (`JSONDecodeError: Extra data`). Dos
      `json.dump` encimados dejan un JSON que no parsea.
      ⇒ Y `sesion_valida` ante un archivo ilegible hace *"RECHAZO por las dudas"* ⇒ **TODO EL QUE
        REVALIDE QUEDA AFUERA**, no sólo los que perdieron su entrada. Eso es lo que convierte un
        doble clic de una persona en *"varios estancados en cargando"*.
      ★ El control valió más que la prueba: no confirmó el bug, lo agrandó.

    ★★ Es **el mismo bug que `chars_db.json`** ya nos había hecho, y que motivó pasar todo a
      SQLite (ver `almacen.py`): *"dos guardados a la vez se pisaban y un corte a mitad dejaba el
      archivo roto"*. Quedó vivo acá porque este archivo nunca se migró.

    ⇒ Dos arreglos, y hacen falta los dos:
      · **el candado** (`_SES_LOCK`): el único escritor es el server y usa un hilo por conexión,
        así que un lock de `threading` alcanza — el launcher **no escribe** este archivo, sólo
        pide el vcode por la red.
      · **escritura atómica** (temp + `os.replace`): si el proceso muere a mitad del `dump`, el
        archivo quedaba TRUNCADO y ahí se perdían **todas** las sesiones, no una.
    """
    vcode = secrets.randbits(62)
    with _SES_LOCK:
        try:
            with open(SESIONES, "r", encoding="utf-8") as f:
                ses = json.load(f)
        except Exception:
            ses = {}
        # ★★★★★ VARIAS SESIONES VIVAS POR CUENTA (2026-09-12) — el 2º arreglo del doble login.
        #   ⛔ Acá se guardaba UN vcode por usn, así que **el segundo login PISABA al primero**.
        #     Medido en el log: `LAUNCHER OK: jugador15` dos veces seguidas, y ocho segundos
        #     después `⛔ usn=7535: el vcode no coincide (llegó A, abrimos B)`.
        #     El primer cliente seguía jugando **hasta que cambiaba de canal** —que revalida— y
        #     ahí lo echaban: de ahí el *"estancado en cambio de canal"* que vio anonimo03.
        #   ★ Y no era la carrera del commit anterior: ese archivo estaba sano. Eran DOS bugs
        #     distintos con el mismo síntoma, y el primero tapaba al segundo.
        #   ⇒ Se guardan los últimos `SESION_VIVAS` vcodes y **vale cualquiera**. Con eso dos
        #     clientes de la misma cuenta conviven, que es lo que anonimo03 hace para probar.
        #   ⚠ La lista se acota a propósito: sin tope, un launcher en bucle la haría crecer para
        #     siempre y cada validación costaría más. Y el TTL de la sesión sigue aplicando.
        _e = ses.get(str(int(usn))) or {}
        _previos = list(_e.get("vcodes") or ([_e["vcode"]] if _e.get("vcode") is not None else []))
        _previos.append(vcode)
        ses[str(int(usn))] = {"vcode": vcode,                      # el último, por compatibilidad
                              "vcodes": _previos[-SESION_VIVAS:],  # ★ los que siguen valiendo
                              "abierta": time.time()}
        _tmp = SESIONES + ".tmp"
        with open(_tmp, "w", encoding="utf-8") as f:
            json.dump(ses, f, indent=2)
        os.replace(_tmp, SESIONES)      # atómico: o está el viejo o está el nuevo, nunca a medias
    return vcode


def _mismo_vcode(abierto, llegado):
    """`llegado` es el vcode que abrimos, o ése más `SESION_PASO` unas cuantas veces (ver arriba)."""
    if abierto is None:
        return False
    d = int(llegado) - int(abierto)
    return d == 0 or (SESION_PASO and 0 < d <= SESION_PASO * SESION_PASOS_MAX and d % SESION_PASO == 0)
# ★ La base de personajes. `startserver.py` la fija en `R2_CHARS_DB` apuntando al archivo de ESTE
#   proyecto, así que en la práctica el default casi nunca se usa.
#   ⚠⚠ Pero el default APUNTABA A `D:\R2Beat\client\Proyecto R2beat 2013\server\chars_db.json`, o
#   sea al proyecto viejo, que es material de consulta y **no se corre**. Cualquier cosa que importe
#   el server sin pasar por `startserver.py` —una prueba, un script de mantenimiento, una consulta
#   suelta— leía y **escribía** ahí, en silencio y con datos distintos.
#   Me mordió el 2026-09-05: fui a verificar un cambio de nivel, leí la DB de D: sin saberlo, y
#   reporté que "la base viva no es la del proyecto". Era al revés.
#   ⇒ El default ahora es el archivo de acá. La variable de entorno lo sigue pisando.
CHARS_DB = os.environ.get("R2_CHARS_DB") or os.path.join(RAIZ, "chars_db.json")

def db_load():
    """⚠⚠⚠ LEE LA BASE ENTERA. Es CARÍSIMA: `leer_todos` hace una consulta por personaje y
    `filas_a_char` DOS más por cada uno. Con los 4806 personajes de producción, una sola llamada
    son **~9.600 consultas** y 4806 diccionarios construidos.

    Medido con py-spy el 2026-09-05, en producción: el **92% del CPU** del servidor entero estaba
    acá dentro, entrando por dos caminos que sólo querían UN personaje —`db_expire` (67%) y
    `db_equip` (25%)—. El núcleo quedaba clavado en 90% con 10 jugadores.

    ⇒ Si necesitás UN personaje, usá `db_get_char(usn)` y `db_save_uno(usn, ch)`.
      `db_load()` sólo tiene sentido cuando de verdad hace falta el padrón completo."""
    return almacen.leer_todos()

def db_save(d):
    # ★ `guardar_todos` escribe SOLO los personajes que cambiaron: dos jugadores guardando a la
    #   vez ya no se pisan entero, como pasaba con el JSON. Ver el aviso de `almacen.py`.
    # ⚠ Ojo igual: para saber cuáles cambiaron compara contra la base, o sea que pasarle el dict
    #   COMPLETO cuesta otras ~9.600 consultas. Para un solo jugador está `db_save_uno`.
    try:
        almacen.guardar_todos(d)
    except Exception as e:
        log("DB", f"save err: {e}")

def db_save_uno(usn, ch):
    """Guarda UN personaje. `guardar_todos` recorre las claves que le pasás y **no borra las que
    faltan** (sólo reescribe las que cambiaron), así que un dict de un elemento es seguro."""
    try:
        almacen.guardar_todos({str(usn): ch})
    except Exception as e:
        log("DB", f"save err (usn={usn}): {e}")

def db_get_char(usn):
    # ★ una consulta por su `uid`, no leer la base entera y buscar. Con 56 daba igual; con 5.000
    #   es la diferencia entre O(1) y O(n) en la función MÁS llamada de todo el server.
    return almacen.leer_char(usn)


def db_char_por_nick(nick):
    """El personaje que se llama así, o `None`. Para el `FF78` (ver info de otro jugador),
    que llega con el APODO y no con el usn."""
    return almacen.char_por_nick(nick) if nick else None


# ── ★ AMIGOS (FF40 sub 0x01/0x1D/0x1E/0x1F + FF42) — estrenado el 2026-09-10 ────────────────────
# La tabla `friends` estaba en el esquema desde el 05-sep y no la usaba nadie. El disparador fue el
# log de prod: **509 solicitudes de amistad** llegando sin respuesta, con el nick en claro adentro
# del paquete y la misma persona reintentando hasta 40 veces.
def db_amigos(usn):
    return almacen.amigos_de(usn)


def db_uid_por_nick(nick):
    """El uid del que se llama así. ⚠ NO uses `db_char_por_nick(...)["uid"]`: ese diccionario
    **no trae el uid** (ver `almacen.uid_por_nick`, que existe justamente por ese error).
    ⚠⚠ Y ojo: si el apodo está repetido devuelve **uno cualquiera**. Para elegir bien, `db_uids_por_nick`."""
    return almacen.uid_por_nick(nick)


def db_nicks_de(uids):
    """{uid: apodo} de muchos, en UNA consulta (ver `almacen.nicks_de`)."""
    return almacen.nicks_de(uids)


def db_uids_por_nick(nick):
    """TODOS los uid con ese apodo. El apodo **no es único**: 203 repetidos sobre 4807 personajes."""
    return almacen.uids_por_nick(nick)


def db_pareja_de(usn):
    """El uid de la pareja de `usn`, o 0 si está soltero."""
    return almacen.pareja_de(usn)


def db_pareja_desde(usn):
    return almacen.pareja_desde(usn)


def db_poner_pareja(usn, otro):
    return almacen.poner_pareja(usn, otro)


def db_romper_pareja(usn):
    """Los separa por los dos lados. Devuelve el uid del ex, o 0."""
    return almacen.romper_pareja(usn)


def db_poner_anillo(usn, item_id, partner):
    return almacen.poner_anillo(usn, item_id, partner)


def db_anillo_de_pareja(usn):
    """El item_id del anillo de pareja que lleva puesto, o 0."""
    return almacen.anillo_de_pareja(usn)


def db_poner_confesion(usn, texto):
    """La confesión de pareja (el texto que viaja con el cambio de anillo)."""
    return almacen.poner_confesion(usn, texto)


def db_confesion_de(usn):
    return almacen.confesion_de(usn)


def db_hay_confesion(usn):
    return almacen.hay_confesion(usn)


def db_borrar_recuerdo(usn, item_id):
    """Tira el recuerdo roto de ese anillo. Devuelve cuántas filas se fueron."""
    return almacen.borrar_recuerdo(usn, item_id)


def db_anillos_de(usn):
    """Todos sus anillos —el puesto y los recuerdos— para armar el `FF45`."""
    return almacen.anillos_de(usn)


def db_son_amigos(usn, otro):
    return almacen.son_amigos(usn, otro)


def db_agregar_amigo(usn, otro):
    return almacen.agregar_amigo(usn, otro)


def db_borrar_amigo(usn, otro):
    return almacen.borrar_amigo(usn, otro)


# ── ★★ EL AMIGO DEL ALMA (la Joya de la Amistad) — ver `lobby_alma.py` ────────────────────────
def db_almas_de(usn):
    return almacen.almas_de(usn)


def db_son_almas(usn, otro):
    return almacen.son_almas(usn, otro)


def db_agregar_alma(usn, otro, joya=0):
    return almacen.agregar_alma(usn, otro, joya)


def db_borrar_alma(usn, otro):
    return almacen.borrar_alma(usn, otro)


def db_poner_joya_alma(usn, otro, joya):
    return almacen.poner_joya_alma(usn, otro, joya)

# ── ★★ EL RÉCORD Y LAS MEDALLAS (24-sep) — ver `medallas.py` ───────────────────────────────────
def db_record_de(usn):
    return almacen.record_de(usn)


def db_puesto_por_exp(usn):
    return almacen.puesto_por_exp(usn)


def db_sumar_record(usn, sumas=None, maximos=None, poner=None):
    """Devuelve `(viejo, nuevo)`."""
    return almacen.sumar_record(usn, sumas=sumas, maximos=maximos, poner=poner)

# ── ★★ LOS CÍRCULOS (24-sep) — las reglas en `circulos.py` ───────────────────────────────────
def db_circulo_de(usn):
    return almacen.circulo_de(usn)


def db_circulo_por_nombre(nombre):
    return almacen.circulo_por_nombre(nombre)


def db_circulo_por_id(cid):
    return almacen.circulo_por_id(cid)


def db_miembros_circulo(cid):
    return almacen.miembros_circulo(cid)


def db_crear_circulo(usn, nombre, ahora):
    return almacen.crear_circulo(usn, nombre, ahora)


def db_agregar_miembro(usn, cid, ahora, tope):
    return almacen.agregar_miembro(usn, cid, ahora, tope)


def db_quitar_miembro(usn):
    return almacen.quitar_miembro(usn)


def db_poner_rango_circulo(usn, rango):
    return almacen.poner_rango_circulo(usn, rango)


def db_poner_lider_circulo(cid, usn):
    return almacen.poner_lider_circulo(cid, usn)


def db_poner_aviso_circulo(cid, aviso):
    return almacen.poner_aviso_circulo(cid, aviso)


def db_borrar_circulo(cid):
    return almacen.borrar_circulo(cid)


def db_pedir_circulo(usn, cid, ahora):
    return almacen.pedir_circulo(usn, cid, ahora)


def db_solicitud_de(usn):
    return almacen.solicitud_de(usn)


def db_solicitudes_circulo(cid):
    return almacen.solicitudes_circulo(cid)


def db_borrar_solicitud(usn):
    return almacen.borrar_solicitud(usn)


def db_economia_circulo(cid):
    return almacen.economia_circulo(cid)


def db_poner_economia_circulo(cid, **campos):
    return almacen.poner_economia_circulo(cid, **campos)


def db_donar_a_circulo(uid, cid, monto, tope_de, ahora, exp_bruta=None, dinero=None):
    return almacen.donar_a_circulo(uid, cid, monto, tope_de, ahora, exp_bruta, dinero)


def db_items_circulo(cid):
    return almacen.items_circulo(cid)


def db_comprar_item_circulo(cid, item, precio, dias, uid, ahora_ts, ahora, clave=0):
    return almacen.comprar_item_circulo(cid, item, precio, dias, uid, ahora_ts, ahora, clave)


def db_acomodar_items_circulo(cid, filas):
    return almacen.acomodar_items_circulo(cid, filas)


def db_subir_nivel_circulo(cid, costo_de, tope_de, regalos, vence_ts, ahora):
    return almacen.subir_nivel_circulo(cid, costo_de, tope_de, regalos, vence_ts, ahora)


def db_poner_marca_circulo(cid, marca, item_logo, item_fondo):
    return almacen.poner_marca_circulo(cid, marca, item_logo, item_fondo)


def db_insignia_circulo(uid):
    return almacen.insignia_circulo(uid)


def db_estilo_chat(uid):
    return almacen.estilo_chat(uid)


def db_poner_estilo_chat(uid, campo, item):
    return almacen.poner_estilo_chat(uid, campo, item)


def db_lapiz_apodo(uid):
    return almacen.lapiz_apodo(uid)


def db_poner_lapiz_apodo(uid, item):
    return almacen.poner_lapiz_apodo(uid, item)


def db_lapiz_circulo(uid):
    return almacen.lapiz_circulo(uid)


def db_poner_lapiz_circulo(uid, item):
    return almacen.poner_lapiz_circulo(uid, item)


def db_tira_anuncios():
    return almacen.tira_anuncios()


def db_agregar_tira(texto, hasta=0, quien="", ahora=0):
    return almacen.agregar_tira(texto, hasta, quien, ahora)


def db_editar_tira(id_, texto, hasta=0, activo=1):
    return almacen.editar_tira(id_, texto, hasta, activo)


def db_quitar_tira(id_=None):
    return almacen.quitar_tira(id_)


def db_preferidas_de(uid):
    return almacen.preferidas_de(uid)


def db_cambiar_preferidas(uid, agregar=(), quitar=()):
    return almacen.cambiar_preferidas(uid, agregar, quitar)


def db_record_cancion_de(uid, cancion):
    return almacen.record_cancion_de(uid, cancion)


def db_anotar_record_cancion(uid, cancion, combo, pd_x1000, allcombo, frame=0):
    return almacen.anotar_record_cancion(uid, cancion, combo, pd_x1000, allcombo,
                                         time.strftime("%Y-%m-%d"), time.time(), frame)


def db_top_cancion(cancion, n, uid=0):
    return almacen.top_cancion(cancion, n, uid)


def db_jugadas_por_cancion(desde_dia, hasta_dia):
    return almacen.jugadas_por_cancion(desde_dia, hasta_dia)


def db_presentacion_de(uid):
    return almacen.presentacion_de(uid)


def db_poner_presentacion(uid, marca, edad, texto):
    return almacen.poner_presentacion(uid, marca, edad, texto, time.time())


def db_puesto_circulo(cid):
    return almacen.puesto_circulo(cid)


def db_donaciones_circulo(cid):
    return almacen.donaciones_circulo(cid)

# ── ★ PROGRESO DE MISIONES, por usuario y en la DB (calca del CBT: `chars.mission`) ────────────
def db_get_mission(usn=0):
    return int((db_get_char(usn) or {}).get("mission", 0) or 0)

# ★★★ NIBBLES DE MISIONES-HISTORIA (2026-07-30) — LA PIEZA QUE FALTABA PARA QUE PERSISTAN.
#   El campo **E (u16) del RESP-1 de login** va a `0x48B720`, que decodifica **3 NIBBLES** y por cada
#   uno llama `0x488FD0` (= OTORGAR) sobre el vector de licencias/misiones `[player+0x3c]`:
#       nibble0 = E & 0xF        -> for i=1..n0 : otorga la máscara  i          (grupo 1: 1..8)
#       nibble1 = (E>>4) & 0xF   -> for i=1..n1 : otorga la máscara  i<<4       (grupo 2: 0x10,0x20,0x30)
#       nibble2 = (E>>8) & 0xF   -> for i=1..n2 : otorga la máscara  i<<8       (grupo 3: 0x100,...)
#   Es el gemelo exacto del `0x455A00` del CBT, y los 3 grupos coinciden con los 3 grupos de máscaras
#   que volcamos del vector. ⚠ **SIN esto, al reloguear la misión vuelve a "reto" y no desbloquea la
#   siguiente**: el MyRecord sólo restaura el CONTADOR de lecciones, no el "hecha" por-misión.
def db_get_nibbles(usn=0):
    v = (db_get_char(usn) or {}).get("mision_nibbles") or [0, 0, 0]
    return [max(0, min(int(x or 0), 0xF)) for x in (list(v) + [0, 0, 0])[:3]]

def db_get_rcoin(usn=0):
    ch = db_get_char(usn) or {}
    return int(ch.get("rcoin", RCOIN) or 0)

def db_add_rcoin(usn, delta):
    """Suma (o resta) Rcoin y devuelve el saldo nuevo. Es lo que contesta el FFAB."""
    # ★ 2026-09-05: era `db_load()` + `db_save(d)` = los 4806 personajes DOS veces por moneda.
    ch = db_get_char(usn)
    if not ch:
        return db_get_rcoin(usn)
    nuevo = max(0, int(ch.get("rcoin", RCOIN) or 0) + int(delta))
    ch["rcoin"] = nuevo; db_save_uno(usn, ch)
    return nuevo

# ★ RPOINT (2026-09-02). Las cajas del gorila reparten RCoin **y** RPoint (`type=2` del sub 6),
#   asi que el punto tambien tiene que persistir o al reloguear no existio. Campo `rpoint`, que
#   arranca en 0 para las cuentas viejas: no hay valor por defecto tipo `RCOIN` porque el punto
#   no se regala al crear el personaje.
def db_get_rpoint(usn=0):
    ch = db_get_char(usn) or {}
    return int(ch.get("rpoint", 0) or 0)

def db_add_rpoint(usn, delta):
    """Suma (o resta) RPoint y devuelve el saldo nuevo."""
    ch = db_get_char(usn)
    if not ch:
        return db_get_rpoint(usn)
    nuevo = max(0, int(ch.get("rpoint", 0) or 0) + int(delta))
    ch["rpoint"] = nuevo; db_save_uno(usn, ch)
    return nuevo

def db_add_exp(usn, delta):
    ch = db_get_char(usn) if delta else None
    if not ch:
        return int((db_get_char(usn) or {}).get("exp", 0) or 0)
    nuevo = max(0, int(ch.get("exp", 0) or 0) + int(delta))
    ch["exp"] = nuevo; db_save_uno(usn, ch)
    return nuevo

# ★★ PREMIO DE UNA SOLA VEZ (2026-07-31). Las misiones se pueden REPETIR, pero el premio se cobra una
#    vez sola. El cliente ya cubre la mitad —al repetir con rank S no vuelve a ofrecer la elección de
#    set (manda `premio=0`)— pero el **`FFAB` se manda igual**, así que sin este candado el Rcoin se
#    pagaba de nuevo en cada repetición. Se lleva un flag por misión y por TIPO de premio, porque son
#    ramas alternativas del mismo reto: rank S → set · rank menor a S → Rcoin.
def db_premio_cobrado(usn, mid, tipo):
    return int(mid) in ((db_get_char(usn) or {}).get(f"premios_{tipo}", []) or [])

def db_marcar_premio(usn, mid, tipo):
    ch = db_get_char(usn)
    if not ch:
        return
    lst = ch.setdefault(f"premios_{tipo}", [])
    if int(mid) not in lst:
        lst.append(int(mid)); db_save_uno(usn, ch)

def db_get_grados(usn=0):
    return (db_get_char(usn) or {}).get("misiones_grado", {}) or {}

def db_set_mission(usn, valor):
    """MONÓTONO: nunca baja (igual que el `MAX(mission, ?)` del CBT)."""
    ch = db_get_char(usn)
    if not ch:
        return db_get_mission(usn)
    nuevo = max(int(ch.get("mission", 0) or 0), int(valor) & 0xFF)
    ch["mission"] = nuevo; db_save_uno(usn, ch)
    return nuevo
                                      #   probes (0x357EC->3/5/28→10/3/28, etc.): delta constante −54. Compensar +54.

def _exp_to_wire(exp):
    """exp UNIX (0=permanente) -> end_time de 32b que el cliente MUESTRA como fecha de vencimiento.
    Formato = fecha EMPAQUETADA: bits0-11=año, bits12-15=mes, bits16-20=día. PERO el cliente 2013 resta
    un desplazamiento fijo de 54 días al mostrar (medido con probes; delta −54 constante). Para que muestre
    la fecha REAL, codificamos (expiry + 54 días). Permanente = centinela 0xEEFFCBB8 (=31/12/3000, no expira).
    En la DB guardamos el UNIX ts (para db_expire); esto es SOLO el cable."""
    if not exp:
        return PERM_SENTINEL
    d = datetime.datetime.fromtimestamp(exp) + datetime.timedelta(days=DATE_WIRE_OFFSET_DAYS)
    return (((d.day & 0x1F) << 16) | ((d.month & 0xF) << 12) | (d.year & 0xFFF)) & 0xFFFFFFFF

def inv_pairs(ch):
    """[(id:int, exp:int)] del inventario. exp=0 = permanente. Acepta formato viejo (int plano)."""
    out = []
    for e in ch.get("inventory", []):
        if isinstance(e, dict):
            out.append((int(e["id"]), int(e.get("exp", 0))))
        else:
            out.append((int(e), 0))
    return out

def inv_ids(ch):
    return [i for i, _ in inv_pairs(ch)]

def inv_cant(ch):
    """{id: cantidad} de los CONSUMIBLES con cargas (impulsores, etc.). 0 / ausente = ropa u otro
    ítem sin cantidad. Va al campo `count:u16` del #37 del MyRecord, que hasta 2026-07-31 mandábamos
    clavado en 0 porque sólo teníamos ropa."""
    # ★ Los globos / crayones / lápices del chat (25-sep) se vendieron un tiempo COMO CARGAS (familia
    #   «megaphone») y quedaron con `cant` en la base — acá y en prod. Son por FECHA: su `cant` se
    #   ignora, así la ficha no los muestra «por usos» sin tener que tocar la base de nadie.
    try:
        from .catalogo import CRAYONES_CHAT, GLOBOS_CHAT, LAPICES_APODO   # noqa: PLC0415
        _sin = set(GLOBOS_CHAT) | set(CRAYONES_CHAT) | set(LAPICES_APODO)
    except Exception:                                                     # noqa: BLE001
        _sin = set()
    out = {}
    for e in ch.get("inventory", []):
        if isinstance(e, dict) and int(e.get("cant", 0) or 0) > 0 and int(e["id"]) not in _sin:
            out[int(e["id"])] = int(e["cant"])
    return out

def compute_expiry(period, now=None):
    """Código de período -> timestamp UNIX de expiración (0 = permanente/consumible sin expiry)."""
    days = shop_catalog.duration_days(period)
    if not days:
        return 0
    return int(now or time.time()) + days * 86400

def db_expire(usn):
    """Quita del inventario (y de lo puesto) los ítems temporales ya vencidos. Devuelve nº de vencidos."""
    # ★ 2026-09-05: era `d = db_load(); ch = d.get(str(usn))`, o sea leer los 4806 personajes para
    #   mirar el inventario de UNO. Entra por el FF03 (MyRecord), que es constante: py-spy lo midió
    #   como el **67% del CPU del servidor**. Ahora una consulta por uid.
    ch = db_get_char(usn)
    if not ch:
        return 0
    now = int(time.time())
    keep, expired = [], []
    for e in ch.get("inventory", []):
        eid = e["id"] if isinstance(e, dict) else e
        exp = (e.get("exp", 0) if isinstance(e, dict) else 0)
        if exp and exp < now:
            expired.append(eid)
        else:
            keep.append(e)
    if expired:
        ch["inventory"] = keep
        ch["parts"] = [p for p in ch.get("parts", []) if p not in expired]   # sacar los vencidos que estaban puestos
        db_save_uno(usn, ch)
        log("DB", f"expiry usn={usn}: vencieron {expired} -> quitados de inventario/parts")
    return len(expired)

def db_add_inventory(usn, item_id, exp=0, cant=0):
    """Agrega/actualiza un item comprado en el inventario (chars_db.json -> ch['inventory']).

    exp = timestamp UNIX de expiración (0 = permanente). Si el ítem ya existe, extiende la duración
    (permanente gana; si ambos temporales, el mayor). Guarda como dict {"id","exp"[,"cant"]}.
    ★ `cant` > 0 = CONSUMIBLE con cargas (impulsores): al re-recibirlo las cargas se **SUMAN**, no se
    reemplazan (a diferencia de la duración, donde gana la mayor)."""
    ch = db_get_char(usn)
    if not ch:
        return
    inv = ch.setdefault("inventory", [])
    for e in inv:                                    # ¿ya lo tiene? -> extender duración / sumar cargas
        eid = e["id"] if isinstance(e, dict) else e
        if eid == item_id:
            cur = e.get("exp", 0) if isinstance(e, dict) else 0
            new = 0 if (exp == 0 or cur == 0) else max(cur, exp)   # 0 = permanente gana
            ent = {"id": item_id, "exp": new}
            tot = (int(e.get("cant", 0) or 0) if isinstance(e, dict) else 0) + int(cant or 0)
            if tot:
                ent["cant"] = tot
            inv[inv.index(e)] = ent
            db_save_uno(usn, ch)
            log("DB", f"item {item_id} ya poseído -> exp={new}"
                      + (f" cargas={tot}" if tot else "") + f" usn={usn}")
            return
    ent = {"id": item_id, "exp": exp}
    if int(cant or 0) > 0:
        ent["cant"] = int(cant)
    inv.append(ent); db_save_uno(usn, ch)
    log("DB", f"item {item_id} (exp={exp}" + (f", cant={cant}" if cant else "")
              + f") -> inventario usn={usn} (total {len(inv)})")

def db_del_inventory(usn, item_id, cant=1):
    """Saca UNA unidad (o `cant`) del inventario. Devuelve `True` si se sacó algo.

    ★ Nació para las CÁPSULAS del gacha (2026-09-08): abrir una tiene que gastarla, y hasta hoy el
      inventario sólo sabía SUMAR. Ver `servidor/gacha.py`.

    Dos casos, y la diferencia importa:
      · el ítem tiene `cant` (consumible con cargas) -> se le restan las cargas, y sólo se borra la
        entrada cuando llega a cero;
      · el ítem NO tiene `cant` (una prenda, una cápsula suelta) -> se borra la entrada entera.

    ⚠ Devuelve `False` si no lo tiene, y el que llama TIENE que mirarlo: es lo único que impide
      abrir una cápsula que nunca se compró. No alcanza con que el cliente no muestre el botón.
    """
    ch = db_get_char(usn)
    if not ch:
        return False
    inv = ch.get("inventory") or []
    for e in list(inv):
        eid = e["id"] if isinstance(e, dict) else e
        if eid != item_id:
            continue
        cargas = int(e.get("cant", 0) or 0) if isinstance(e, dict) else 0
        if cargas > int(cant or 1):
            ent = dict(e); ent["cant"] = cargas - int(cant or 1)
            inv[inv.index(e)] = ent
            db_save_uno(usn, ch)
            log("DB", f"item {item_id}: -{cant} carga(s) -> quedan {ent['cant']} (usn={usn})")
            return True
        inv.remove(e)
        db_save_uno(usn, ch)
        log("DB", f"item {item_id} CONSUMIDO del inventario usn={usn} (quedan {len(inv)})")
        return True
    log("DB", f"⚠ item {item_id}: usn={usn} NO lo tiene, no se consume nada")
    return False


def parse_create_char(data):
    """FF04 CREATE_CHAR (wire 2013, capturado en vivo — NO del 2011):
    [u32 char_id][u8 nicklen][nick][u8 partcount][partcount × u32 part_id]."""
    i = 0
    char_id = struct.unpack_from("<I", data, i)[0]; i += 4
    nlen = data[i]; i += 1
    nick = data[i:i+nlen].decode("cp1252", "replace"); i += nlen
    pc = data[i]; i += 1
    parts = []
    for _ in range(pc):
        parts.append(struct.unpack_from("<I", data, i)[0]); i += 4
    return {"char_id": char_id, "nick": nick, "parts": parts}
