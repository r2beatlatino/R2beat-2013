# -*- coding: utf-8 -*-
"""salas — el registro vivo de salas, las mesas y los ocupantes

Cortado de `server_login2013.py`. El código es el MISMO, movido tal cual.
"""
import os
import random
import struct
import threading

from .ajustes import (
    DEFAULT_ROOM_MAP,
    DESTINOS_HORNEADOS,
    EQUIPO_AL_PADRON,
    EQUIPOS,
    FF0C_ENTRADA_A_SALA,
    FF0C_JOYAS_ALMA,
    FF0C_LAYOUT_REAL,
    FF0C_YO_SIN_ROPA,
    CANALES_2013,
    FF6E_CANAL_EN_LA_LISTA,
    FF6E_CANAL_TOPE,
    FF6E_CAPACIDAD,
    FF6E_EMPUJE_RESPETA_PAGINA,
    GHOST_SLOTS,
    HOST_SLOT,
    INSTANCIAS_LUGAR_N,
    LUGAR_CAPACIDAD,
    MODE_EQUIPO,
    MODE_RELEVO,
    MODE_VELOCIDAD,
    MOSTRAR_SALAS_DEMO,
    NICK_MAX_FF0E,
    FF0E_EN_CARRERA_ESPERA,
    OCUPACION,
    FFBB_A_TODA_LA_SALA,
    ORDEN_ASIENTOS,
    ORDEN_ASIENTOS_12,
    ORDEN_ASIENTOS_12_RELEVO,
    RELEVO12_EQUIPOS,
    FF6E_SALAS_POR_PAGINA,
    SALAS_FALSAS_PAGINACION,
    SALAS_POR_CANAL,
    TIPOS_LUGAR_CHARLA,
    ESPECTADOR12_A_CORREDORES,
    ESPECTADORES_TRAS_EL_QUE_ENTRA,
)
from .gacha import parts_visibles, sexo
from .registro import (
    RESUMIR,
    log,
)
from .basedatos import (
    db_get_char,
)
from .medallas import medalla_puesta
from .paquetes import (
    build_ff0c_2013,
    build_ff0c_2013_real,
    build_ff15_2013,
)

# El módulo se lee con rutas relativas a la RAÍZ del proyecto, no a
# `servidor/`. Viene de cuando todo era un archivo solo; sacarlo rompe la
# lectura de las tablas del cliente (wing.txt / face.txt).
__file__ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server_login2013.py")   # rutas relativas como en el original

# ── TANDA 2 (medida en pantalla 2026-07-30) — CONFIRMADO ──────────────────────────────────────
#     F         = ★ el "[N]" al lado de la ocupación  ⇒ E = ocupantes TOTALES, F = los del corchete,
#                 y los que se muestran jugando son E−F. El corchete se OCULTA en coop/jefe.
#     I         = ★ BITMASK DE ICONITOS de la fila (bit0 y bit1 = insignias, bit2 = la roja)
#     L/M/N/O   = ★ EL MODO: (L=1,M=1) -> "Modo Cooperativo" · (N=1,O=1) -> "Batalla de Jefes"
#     H, A_alto = ⛔ NO dibujan nada en la grilla (descartados)
#
# ── TANDA 3 (medida en pantalla 2026-07-30) — CONFIRMADO ──────────────────────────────────────
#     M = ★ MODO COOPERATIVO   ·   O = ★ BATALLA DE JEFES   ·   N = iconito rojo de la fila
#     L, C, D = ⛔ no dibujan nada en la grilla
#     B bit2  = ★ modo ÍTEM (salió "?em" = "Ítem" con la tilde rota)  ⇒ **B ES EL byMode DE LA SALA**,
#               el mismo byte del FF4B/FFBD (ahí bit2=item, bit4=equipo). Ver r2beat-2013-modo-sala.
#
# ── TANDA 4 (medida en pantalla 2026-07-30) — CONFIRMADO: **B = byMode de la sala** ────────────
#     bit0 0x01 = 🔒 PRIVADA  ·  bit1 0x02 = EN JUEGO ("Jugando")  ·  bit2 0x04 = ÍTEM
#     bit4 0x10 = ★ EQUIPO (columna "Solo"→"Equipo")               ·  bit7 0x80 = ★ RELEVOS
#     bits 0x08/0x20/0x40 = no dibujan nada    ·    y los bits COMBINAN (0x14 = "Ítem"+"Equipo")
#     J y K = cada uno prende un ICONITO propio en la fila
#     G=20 -> "3/14"  y  E=8,F=5 -> "3/8 [5]"  ⇒ re-confirmado E−F = jugando, G−6 = capacidad, [F].
#
# ═══ RESUMEN FINAL DEL WIRE (todo medido en pantalla, nada supuesto) ═══════════════════════════
#     A  u16 : bits0-10 = Nº de sala            ·  bits11-15 = sin efecto visible
#     B  u8  : byMode (tabla de arriba)
#     C  u16 , D u16 , H u8 , L u8 : sin efecto visible en la grilla (¿se usan al ENTRAR?)
#     E  u8  : ocupantes totales                ·  F u8 : los del "[N]"  (jugando = E−F)
#     G  u8  : capacidad + 6
#     LN+nombre
#     I  u8  : bitmask de iconitos (bit0, bit1, bit2=el rojo)
#     J,K u32: un iconito cada uno
#     M  u8  : MODO COOPERATIVO   ·   N u8 : iconito rojo   ·   O u8 : BATALLA DE JEFES
# ══════════════════════════════════════════════════════════════════════════════════════════════

# ★ REGISTRO VIVO DE SALAS. Acá se anotan las salas que EXISTEN de verdad (las que crea el jugador
#   con FF10 y, más adelante, las de otros clientes). `SALAS_DEMO` son maniquíes que se dejan para
#   poder medir el ENTRAR A UNA SALA (igual que los NPC de la sala: no hay otro cliente todavía).
SALAS_VIVAS = {}                       # roomid -> dict con el layout de arriba (+ `flags` interno)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★ SALAS COMPARTIDAS (2026-08-05) — que DOS JUGADORES DE VERDAD se vean en la misma sala.
#   Antes: cada conexión armaba SU sala. Los dos creaban la sala 1 (`room_id` estaba clavado en 1),
#   al que entraba se le contestaba `HOST_SLOT` igual que al que creaba, y el `FF0C` se armaba con
#   `st` + los NPC de relleno. Resultado: los dos "en la sala 001", cada uno viéndose solo a sí
#   mismo y a un NPC, sin enterarse del otro. Faltaba lo mismo que el CBT ya tiene: un registro
#   GLOBAL de conexiones (para poder avisarle al otro) y una MESA por sala (quién está en qué slot).
#
#   ⚠ El slot del que CREA lo fija el cliente solo (`me+0x40 = 2` en CREATEROOM) ⇒ HOST_SLOT no se
#     negocia. El del que ENTRA sí: sale del byte0 de nuestra respuesta al FF11.
# ══════════════════════════════════════════════════════════════════════════════════════════════
CONEXIONES = {}                        # usn -> st  (conexiones de lobby vivas; para poder difundir)
DLL_ABANDONO = set()                   # ★ 17-oct: usn cuya dll saca al que abandona en la de 12 (ver difundir_salida)
DLL_CHART64K = set()                   # ★ 06-nov (161): usn cuya dll recibe charts de más de 4096 (notas.recortar_al_techo)
# ★★ 2026-08-05 — LOS NPC SON DE LA SALA, NO DE LA CONEXION. Antes cada cliente tenía los suyos, y
#   pasaba esto: el host arrancaba con un NPC en el slot 3, el invitado (que no lo veía) se sentaba
#   ahí mismo, y como el FF0C **inserta** en vez de reconstruir, el host se quedaba viendo al NPC
#   para siempre. Room-level ⇒ los dos ven los mismos, y el repartidor de asientos los esquiva.
NPCS_SALA  = {}                        # roomid -> [slots con NPC]
# ★★ La CARRERA en curso de cada sala. `magic` es la clave XOR de los paquetes de juego y **tiene que
#   ser la misma para todos**; `cargados` sirve para no dar el "GO" hasta que TODOS terminen de cargar
#   (si no, el que cargó primero corre contra un rival congelado — y la VM tarda mucho más que el host).
CARRERAS   = {}                        # roomid -> {"magic":u32, "cargados":{usn}, "jugadores":{usn}}
# ★★★★★ EL MARCADOR DE LA SERIE — victorias acumuladas por equipo mientras la sala vive.
#   Va SEPARADO de `CARRERAS` a propósito: ese dict se REEMPLAZA entero en cada `FF24` (arranque de
#   carrera), y el marcador tiene que sobrevivir de una partida a la otra. Se limpia cuando la sala
#   muere, igual que `NPCS_SALA`.
#   El cartel `FF28` lo muestra como **"b1 - b2"**: `b1` = victorias del equipo 1 (rojo, slots 0-2)
#   y `b2` = las del equipo 2 (azul, slots 3-5).
MARCADOR   = {}                        # roomid -> {1: victorias_eq1, 2: victorias_eq2}
# ★★★ EL PEDIDO DE INTERCAMBIO DE ASIENTO EN CURSO (`FF6B` -> `FF6C` -> `FF6B`).
#   Con esto se ordenan los TURNOS del modo RELEVO: los tramos van por posición dentro del equipo
#   (0 vs 3, después 1 vs 4, al final 2 vs 5), así que "elegir turno" = "elegir asiento".
#   Uno por sala: el cliente sólo puede tener un popup abierto a la vez.
SWAP_PENDIENTE = {}                    # roomid -> {"de": usn, "para": usn, "slot_de": s, "slot_para": s}
# ★★★ LA PISTA Y LA CANCION SON DE LA SALA, NO DE LA CONEXION (2026-09-04).
#   Vivian en `st.room_map` / `st.room_song`, o sea una copia por jugador: el host cambiaba la
#   pista y el invitado seguia con la suya, porque nunca se enteraba. Es el mismo error que ya se
#   habia pagado con los NPC (ver `NPCS_SALA`) — room-level para que los dos vean lo mismo.
#   Las dos viajan en el `FF13` (pista @14 · cancion @19), medido en `mitm_20260904_102312`.
SELECCION_SALA = {}                    # roomid -> {"pista": u16, "cancion": u16}
# ★★★★★ LA DIFICULTAD DE LA SALA — DE LA SALA, NO DE LA CONEXIÓN (2026-09-07).
#
#   ⛔ EL SÍNTOMA, reportado por el usuario: *"el interruptor de licencia de la sala libre, le hare
#     spam unas 5 veces, solo me deja hasta novato estrella"*. El cliente manda `FFC9` con la banda
#     que quiere y **nosotros no lo atendíamos**: quedaba `FFC9 SIN handler` en el log, el server
#     no contestaba nada, y el interruptor se quedaba donde estaba.
#
#   ★ LA RECETA, MEDIDA sobre el server de referencia (`mitm_20260907_183811`, 8 pedidos y 8
#     respuestas, correlación perfecta y sin una sola excepción). Al llegar el `FFC9` hace TRES
#     cosas, y hay que hacer las tres:
#         1. eco del MISMO byte al que lo pidió           (FFC9 -> 04 devuelve 04)
#         2. `FF13` a TODOS los de la sala, con el valor en `cola[41]`
#         3. un chat del sistema: "Servidor.<nick> pone la dificultad de la sala en N"
#
#   ⚠ Y el chat de ellos le pone NOMBRE al campo: es la **dificultad de la sala**, no la licencia
#     del jugador. Hoy el `FF13` saca ese byte de `licencia_actual(st.usn)`, o sea **del jugador que
#     pregunta** — con lo cual dos personas en la misma sala ven dificultades distintas. Es el mismo
#     error que ya se pagó CUATRO veces (los NPC, la pista, la canción, el anfitrión): un dato de la
#     SALA guardado por conexión. Ver la nota de `SELECCION_SALA`.
#
#   ⇒ Acá vive el valor elegido. Si la sala no eligió ninguno, `dificultad_de` devuelve None y el
#     `FF13` sigue cayendo en la banda del jugador, que es el comportamiento de antes.
DIFICULTAD_SALA = {}                   # roomid -> banda 1..8 elegida por el anfitrión
# ★★ EL MAPA FORZADO POR EL COMANDO `.oscuro` (2026-09-07). SÓLO EL ANFITRIÓN, TODA LA SALA.
#   Es un dato de LA SALA, no de la conexión — el error que este proyecto ya pagó cinco veces.
#   Muere con la sala (`desregistrar_sala`), como pidió el usuario.
#   ⏳ PENDIENTE, descartado a propósito por ahora: que un invitado se lo ponga **sólo para él**.
#     Se evaluó y **no es barato**: hoy el `FF25 LOADGAME` se arma UNA vez y se manda igual a
#     todos (`lobby_carrera`, el bucle de `_jug24`), así que un mapa por jugador obliga a armarlo
#     por destinatario. Se puede, pero es otro cambio y el usuario prefirió la versión simple.
MAPA_SALA = {}                         # roomid -> stage forzado por el anfitrión, para todos
# ★★★ «PD VALOFE» — LA TABLA DE PUNTAJE DE LA SALA (2026-09-14).
#   El R2Beat moderno (el que publica Valofe) puntúa cada nota un escalón más arriba que el de
#   2013. La sala puede elegir con cuál de las dos juega: `.pd on` / `.pd off`, y lo decide el
#   anfitrión para TODOS los de la sala.
#
#   ⚠⚠ POR QUE ES DE LA SALA Y NO DE CADA JUGADOR, que es lo primero que uno haría: porque el
#     número de precisión **sube**, y dos jugadores bajo tablas distintas dan números que no se
#     pueden comparar. El cartel del final los pone uno al lado del otro y el ranking los ordena:
#     mezclar las dos escalas sería comparar peras con manzanas en la pantalla de todos.
#     (Es la séptima vez que aparece este patrón: NPC, pista, canción, anfitrión, dificultad,
#     mapa, y ahora la tabla de puntaje. Ver `estado-de-la-conexion-vs-la-sala`.)
#
#   ★ ARRANCA PRENDIDA, como pidió anonimo03: *"pd valofe por default al crear la sala"*. Por eso el
#     valor guardado es la EXCEPCIÓN (sólo se anota cuando alguien la apaga) y `pd_valofe_de`
#     devuelve `True` si no hay nada: una sala recién creada no necesita que nadie escriba nada.
PD_VALOFE_SALA = {}                    # roomid -> bool. Ausente = prendida (el default)
PD_VALOFE_DEFAULT = True
# ★★★ EL RATE DE UNA SALA SOLA (2026-09-14) — el hermano chico del `.rate` global.
#   Pedido de anonimo03: el global vale para todo el server, *"que también sería útil tener ambos"*.
#   Sirve para premiar UNA sala (un torneo, un evento chico) sin mover la economía entera.
#
#   ⛔⛔ TAMBIÉN ES SÓLO DE GM, y eso NO es negociable aunque sea "de la sala". `.oscuro` y `.pd`
#     los puede poner el anfitrión porque cambian cómo se JUEGA; esto cambia cuánto se COBRA.
#     Si el anfitrión pudiera ponerlo, cualquiera se arma una sala y se paga x10 — o sea, no
#     sería un premio, sería la economía abierta.
#
#   ⚠ Se MULTIPLICA con el global (evento x2 + sala x2 = x4), porque es lo que uno espera cuando
#     pide "un extra encima del evento". El producto se acota igual al mismo tope, así que dos
#     descuidos no se pueden componer hasta el infinito.
#   ⚠ Y muere con la sala, como todo lo demás de acá. Un multiplicador olvidado que sobrevive es
#     exactamente lo que NO queremos.
RATE_SALA = {}                         # roomid -> {"exp": float, "coin": float}
# ★★★ LO QUE ELIGIÓ CADA JUGADOR PARA SÍ, EN ESTA SALA (2026-10-08) — pista y obstáculos.
#   ⚠ La excepción al patrón de arriba (NPC, pista, canción, anfitrión, dificultad, mapa, tabla de
#     puntaje: todo DE LA SALA). Esto es de la sala Y del jugador, y es a propósito. anonimo03, 08-oct:
#     *"si el invitado no elige la suya, la que ponga el anfitrión sigue mandando, hasta que el invitado
#     elija · lo que eligió se mantiene mientras siga en la sala; si sale y va a otra, expira"*.
#   ⇒ Se guarda por sala y se borra cuando el jugador se LEVANTA de la sala (`levantar_jugador`) o la
#     sala muere. ⛔ NO vive en la conexión: sería «la de la sala anterior» en cuanto cambie de sala,
#     que es justo lo que pidió que NO pase.
#   ⚠ Sale distinto para cada uno en el `FF25` (`cola_ff25_jugador`): hasta hoy el LOADGAME era uno
#     solo para toda la sala. Ver `documentacion/PISTA_OBSTACULOS_VICTORIA.md`.
ELECCION_JUGADOR = {}                  # roomid -> {usn: {"pista": u16, "obstaculos": u16}}
# ★★ LOS ASIENTOS QUE EL ANFITRIÓN CERRÓ (`FF87`) — 2026-09-07.
#   El anfitrión puede cerrar los asientos vacíos para que nadie se siente ahí. Es un dato de LA
#   SALA (sexta vez que aparece este patrón: NPC, pista, canción, anfitrión, dificultad, mapa).
#   ⚠ Viaja en el `open_mask` del `FF13`, que hasta hoy iba clavado en `0x3F` = los 6 abiertos.
#     Bit en 1 = asiento ABIERTO. Ver `build_ff13_2013`.
SLOTS_CERRADOS = {}                    # roomid -> set de slots cerrados
# ★★★ LOS CAPITANES DEL MODO JEFE, también de la SALA (2026-09-07). Uno por equipo: el cliente
#   los busca con `FindCaptain(equipo)` (`0x4EBBF0`), que exige `sRoomUser+0x4A == equipo` **y**
#   `+0x4B != 0`. Si devuelve `0xFF` (= no hay), el init de la carrera indexa el vector de
#   jugadores con 255 y el cliente se cae. Ver `JEFE_MIN_POR_EQUIPO` en `ajustes.py`.
CAPITANES = {}                         # roomid -> {equipo: slot}
# ★★ "A ESTA SALA LE TOCA RE-SORTEAR CUANDO VUELVAN DE LA CARRERA" — 2026-09-08.
#   ⛔ EL BUG QUE ARREGLA, reportado por el usuario: *"si el jugador 3 le cedió el puesto al 1, al
#     empezar la partida está ocurriendo sorteo — ceder jefe perdió el sentido"*. El `FF24` (START)
#     re-sorteaba SIEMPRE, así que la cesión (`FF175`) vivía hasta que alguien apretaba START y ahí
#     se pisaba. La cesión sólo tiene sentido si sobrevive hasta la carrera.
#   ⇒ La marca se pone al ARRANCAR y se consume **al volver a la sala**, que es donde el usuario
#     pidió que ocurra el sorteo: entre carrera y carrera los capitanes cambian, y desde ahí hasta
#     el START mandan las cesiones. Ver `marcar_sorteo_al_volver` / `tomar_sorteo_al_volver`.
SORTEO_AL_VOLVER = set()               # roomids con sorteo de capitanes pendiente
# ★★★★★ EL ANFITRIÓN ES DE LA SALA, NO DE LA CONEXIÓN (2026-09-05).
#   Hasta hoy no existía: el `FF13` mandaba `host_slot=HOST_SLOT` **clavado en 2**, o sea "el
#   anfitrión es el que se sienta en el asiento 2, para siempre". Con eso:
#     · "transferir anfitrión" no podía funcionar aunque atendiéramos el paquete, y
#     · cuando el anfitrión se iba, el que quedaba nunca pasaba a serlo (seguía viendo @6 = 2,
#       un asiento vacío) ⇒ sala sin dueño: nadie podía arrancar ni cambiar el modo.
#   Es exactamente el error que ya se pagó con los NPC, la pista y la canción: un dato de la SALA
#   guardado (o supuesto) por conexión. Ver la nota de `SELECCION_SALA`.
ANFITRION = {}                         # roomid -> usn del anfitrión
# ★ 29-sep: la CONTRASEÑA de cada sala (bytes tal cual los manda el cliente). Va por SALA y no en el
#   `st` del que la creó: si el anfitrión se va, la sala sigue con su candado (y sin el `st` viejo).
CLAVE_SALA = {}                        # roomid -> bytes
# ★ El aviso de traspaso que NO se pudo mandar todavía porque la sala estaba corriendo. Vive acá,
#   al lado del registro, para que muera con la sala: los roomid se REUSAN (`nuevo_roomid`), así
#   que un pendiente huérfano puede dispararse en una sala distinta con el mismo número.
#   La lógica está en `lobby_salas._avisar_anfitrion`; acá sólo el dato y su limpieza.
ANFITRION_PENDIENTE = {}               # roomid -> usn al que le falta el FF9B
_mesa_lock = threading.RLock()         # OCUPACION se toca desde el hilo de CADA jugador
LUGARES = {}                           # (tipo, numero) -> {"ocupantes": {usn: slot}}


class _NoOpLock:
    def __enter__(self): return self
    def __exit__(self, *a): return False

def registrar_conexion(st):
    if getattr(st, "usn", None) is not None:
        CONEXIONES[st.usn] = st

def mesa_de(rid):
    with _mesa_lock:
        return dict(OCUPACION.get(rid, {}))

def sentar_jugador(st, rid, slot=None, ocupados_extra=()):
    """Sienta a este jugador en la sala. `slot=None` = el primero libre. Devuelve el slot o None.

    ★ `ocupados_extra` = los slots que ya tienen un NPC. En el CBT los NPC TAMBIÉN cuentan como
      ocupados al repartir asientos, si no el que entra aterriza encima de un fantasma.
    """
    with _mesa_lock:
        mesa = OCUPACION.setdefault(rid, {})
        for s, u in list(mesa.items()):          # por si venía de otra silla
            if u == getattr(st, "usn", None):
                mesa.pop(s)
        # ★★ LOS ASIENTOS CERRADOS NO SE REPARTEN (2026-09-07). El anfitrión los cerró con el
        #   `FF87` justamente para que nadie se siente ahí. Va DENTRO del mismo lock que el
        #   reparto: mirar la lista de cerrados afuera y sentar adentro deja la ventana para que
        #   dos que entran a la vez se pisen — el tipo de carrera que en este proyecto ya costó
        #   tres días de caza.
        _cerrados = set(SLOTS_CERRADOS.get(rid) or ())
        if slot is None:
            tomados = set(mesa) | set(ocupados_extra) | _cerrados
            # ★ carrera grande (6vs6, 10-oct): los asientos 6..N-1 también son de JUGADOR (no de mirar)
            orden = orden_asientos(rid)
            slot = next((s for s in orden if s not in tomados), None)
        if slot is None or slot in mesa or slot in _cerrados:
            return None
        mesa[slot] = st.usn
        st.room_slot = slot
        # ★ Y llega SIN el listo puesto. Si no, el que viene de otra sala donde habia apretado
        #   listo entra ya marcado, y `enviar_listos` se lo repinta a todos: un listo fantasma.
        st.ready = False
        # ★★ Y DEJA DE SER ESPECTADOR. Las dos marcas son EXCLUYENTES: `room_slot` = "estoy sentado
        #   en este asiento" y `slot_espectador` = "estoy mirando desde este casillero". Que
        #   convivieran es lo que dejaba a una conexión contada de los dos lados. Ver la nota
        #   gemela en la rama de espectador del `FF11` (`lobby_salas.h_18_ff11`).
        st.slot_espectador = None
        return slot

def levantar_jugador(st, olvidar_eleccion=True):
    """Lo saca de la mesa. Devuelve (rid, quedaba_gente) para poder difundir y limpiar.

    ★ Y se olvida lo que eligió PARA SÍ en esta sala (pista, obstáculos): «si sale y va a otra, expira».
      `olvidar_eleccion=False` es para el que pasa a MIRAR sin irse de la sala (`FF99`): sigue adentro.
    """
    rid = getattr(st, "room_id", None)
    if not rid:
        return None, False
    with _mesa_lock:
        mesa = OCUPACION.get(rid, {})
        for s, u in list(mesa.items()):
            if u == getattr(st, "usn", None):
                mesa.pop(s)
                # ★ Quién dejó ese asiento: lo necesita `liberar_asiento` para poder limpiarlo en
                #   el cliente del que no se haya enterado. Ver su nota.
                ULTIMO_OCUPANTE.setdefault(rid, {})[s] = u
        queda = bool(mesa)
        if not queda:
            OCUPACION.pop(rid, None)
        if olvidar_eleccion:
            ELECCION_JUGADOR.get(rid, {}).pop(getattr(st, "usn", None), None)
    st.room_slot = None
    # ★ (142) se fue de la sala: se baja de la montura (y su pareja, si estaba en la suya), como el 2019
    try:
        from .monturas import al_salir                                     # noqa: PLC0415
        al_salir(getattr(st, "usn", None))
    except Exception:                                                      # noqa: BLE001
        pass
    return rid, queda


def mesas_del_usn(usn):
    """TODAS las salas donde ese `usn` figura sentado. Normalmente es una; el bug es que sean más."""
    if usn is None:
        return []
    with _mesa_lock:
        return [rid for rid, mesa in OCUPACION.items() if usn in mesa.values()]


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# ★★★★★ EL BARRIDO DE MESAS HUÉRFANAS — LAS SALAS FANTASMA (2026-09-15).
#
#   ⛔ EL BUG, reportado por anonimo03 (*"hay salas fantasmas con un mismo jugador"*) y MEDIDO en el
#     log de producción del 12-sep. El retrato es de manual:
#
#         usn 6671, slot 2:   sentado en la sala 19, en la 22 **y** en la 27, al mismo tiempo
#         12-sep 20:13:13     `conexión usn=6671 dada de baja`
#         15-sep 17:20        las TRES siguen publicadas — 3 días después
#
#     Y no era decorativo: ~1000 entradas de jugadores REALES por sala, entrando a esperar a
#     alguien que se fue hace tres días.
#
#   ★ LA CAUSA, que es de una línea: **`levantar_jugador` limpia UNA sola sala** — la de
#     `st.room_id`. Pero nada saca al jugador de su mesa ANTERIOR cuando se sienta en otra:
#     ni `CREATEROOM` (`h_09_ff10`) ni `ENTERROOM` (`h_18_ff11`) lo hacen, los dos confían en
#     que el cliente mande primero un `FF12 EXITROOM`. Cuando ese `FF12` no llega —doble clic en
#     Crear, reintento del cliente, «Jugar Juntos», un crash— `st.room_id` **se pisa** con la sala
#     nueva y la vieja queda con su `usn` sentado para siempre. Como `desregistrar_rid` sólo borra
#     la sala **si no queda NADIE**, ese fantasma la vuelve inmortal.
#
#     MEDIDO, el disparador más común (8 veces en 3 días): el cliente manda el MISMO `FF10` dos
#     veces seguidas y le creamos dos salas.
#         23:14:21  recv_ctr=97  FF10 'en live tiktok'  -> roomid=9
#         23:14:21  recv_ctr=98  FF10 'en live tiktok'  -> roomid=16   ← y la 9 queda huérfana
#
#   ⇒ EL ARREGLO VA EN DOS CAPAS, a propósito:
#       1. LA PUERTA (`lobby_salas.sacar_de_la_sala_anterior`): al crear o entrar, se lo levanta
#          de donde estuviera. Ataca la CAUSA.
#       2. ESTE BARRIDO: la red de abajo. Ataca **las mesas que ya quedaron mal** —incluidas las
#          de prod, sin reiniciar— y cubre cualquier camino que no hayamos previsto.
#     La capa 1 sola no limpia lo que ya está roto; la 2 sola deja el bug creando basura nueva.
# ─────────────────────────────────────────────────────────────────────────────────────────────────
_BARRIDO_SOSPECHOSOS = {}              # (rid, usn) -> cuántas pasadas seguidas viene raro
_BARRIDO_PRIMERA = True                # ★ para que la 1ª pasada se anuncie aunque no limpie nada


def barrer_mesas_huerfanas():
    """Saca de las mesas a los que ya no están, y borra las salas que quedan sin nadie.

    Devuelve `(asientos_liberados, salas_borradas)`.

    ★★ LAS DOS REGLAS, Y POR QUÉ SON DISTINTAS:

      **(a) sin conexión viva** (`CONEXIONES[usn]` no existe) ⇒ se saca EN EL ACTO. No hay carrera
      posible: `registrar_conexion` lo anota al loguear y sólo `olvidar_conexion` lo borra, así que
      un `usn` sentado sin conexión es un fantasma y punto. Es el caso exacto de prod (el 6671).

      **(b) conectado, pero su `st.room_id` apunta a OTRA sala** ⇒ se espera a verlo **dos pasadas
      seguidas** antes de sacarlo. ⚠ Y esto no es timidez: hay una ventana real en la que un
      jugador legítimo se ve así. `h_18_ff11` llama a `sentar_jugador` **antes** de escribir
      `st.room_id`, o sea que entre las dos líneas el jugador está sentado en una sala que todavía
      no es la suya. Sacarlo ahí lo dejaría invisible en su propia sala — que es el mismo daño que
      este arreglo viene a evitar, cometido por el arreglo. Con la segunda pasada, esa ventana de
      microsegundos no llega nunca a dos vueltas del reloj.
    """
    _libres, _borradas = 0, []
    with _mesa_lock:
        _rids = list(OCUPACION)
    for rid in _rids:
        for slot, usn in mesa_de(rid).items():
            _c = CONEXIONES.get(usn)
            if _c is None:
                _motivo = "no tiene conexión viva"
            elif getattr(_c, "room_id", None) != rid:
                # regla (b): hace falta verlo dos veces
                _n = _BARRIDO_SOSPECHOSOS.get((rid, usn), 0) + 1
                _BARRIDO_SOSPECHOSOS[(rid, usn)] = _n
                if _n < 2:
                    continue
                _motivo = f"está conectado pero en la sala {getattr(_c, 'room_id', None)}"
            else:
                _BARRIDO_SOSPECHOSOS.pop((rid, usn), None)
                continue
            _BARRIDO_SOSPECHOSOS.pop((rid, usn), None)
            with _mesa_lock:
                _mesa = OCUPACION.get(rid, {})
                if _mesa.get(slot) != usn:        # se movió mientras mirábamos: no es asunto nuestro
                    continue
                _mesa.pop(slot, None)
                ULTIMO_OCUPANTE.setdefault(rid, {})[slot] = usn
                if not _mesa:
                    OCUPACION.pop(rid, None)
            _libres += 1
            log("SALA", f"  ★★ BARRIDO: usn={usn} FANTASMA en el asiento {slot} de la sala {rid} "
                        f"({_motivo}) -> liberado")
        if not mesa_de(rid) and SALAS_VIVAS.get(rid) is not None:
            _borradas.append(rid)
            desregistrar_rid(rid)
    # ★★ Y LAS PUBLICADAS QUE NO TIENEN MESA NI SIQUIERA VACÍA — el bucle de arriba no las ve,
    #   porque recorre `OCUPACION` y ahí no figuran. Hoy no debería pasar (`h_09_ff10` sienta
    #   ANTES de publicar), pero es exactamente la misma clase de fantasma y taparlo sale gratis.
    #   ⚠ Con la regla de las DOS pasadas, por el mismo motivo que la (b): si algún camino nuevo
    #     publicara la sala una línea antes de sentar al creador, borrarla en el acto le voltearía
    #     la sala recién hecha.
    #   ⚠⚠ Y NO SE TOCA UNA SALA QUE TIENE GENTE MIRANDO. Una sala puede quedarse sin nadie
    #     sentado y seguir teniendo espectadores conectados: para ellos la sala existe, y
    #     borrársela de abajo sería el mismo bug con otra ropa.
    for rid in [r for r in list(SALAS_VIVAS) if not mesa_de(r) and not espectadores_de(r)]:
        _n = _BARRIDO_SOSPECHOSOS.get((rid, None), 0) + 1
        _BARRIDO_SOSPECHOSOS[(rid, None)] = _n
        if _n < 2:
            continue
        _BARRIDO_SOSPECHOSOS.pop((rid, None), None)
        log("SALA", f"  ★★ BARRIDO: la sala {rid} está publicada y NO tiene a nadie sentado")
        _borradas.append(rid)
        desregistrar_rid(rid)
    if _borradas:
        log("SALA", f"  ★★★ BARRIDO: {len(_borradas)} sala(s) FANTASMA sacada(s) de la lista: "
                    f"{_borradas} — quedan {len(SALAS_VIVAS)}")
        difundir_roomlist()
    # ★★★★ LA PRIMERA PASADA HABLA SIEMPRE, AUNQUE NO ENCUENTRE NADA — 2026-09-15.
    #   ⛔ El agujero que tapa, y lo destapó probar el arreglo en local: el barrido sólo logueaba
    #     cuando limpiaba algo ⇒ en un server sano **no dice nada**, exactamente igual que si el
    #     hilo se hubiera muerto al arrancar. Y yo ya había escrito en la guía de deploy *"si no
    #     dice nada en 2 minutos, el hilo no arrancó"*: **un consejo imposible de seguir**.
    #   ★ Es la misma lección que la puerta de GM (`gm.resumen()`, que se anuncia sin `if`): una
    #     red de seguridad que no se puede auditar no sirve como red. Una línea, una sola vez.
    global _BARRIDO_PRIMERA
    if _BARRIDO_PRIMERA:
        _BARRIDO_PRIMERA = False
        log("SALA", f"  ★ BARRIDO vivo (1ª pasada): {len(OCUPACION)} mesa(s) · "
                    f"{len(SALAS_VIVAS)} sala(s) publicada(s) · {_libres} asiento(s) liberado(s) · "
                    f"{len(_borradas)} sala(s) borrada(s)")
    return _libres, _borradas


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# ★★★★ EL ANFITRIÓN DE LA SALA — ver la nota de `ANFITRION` arriba.
#
#   El cliente NO guarda un flag "soy el anfitrión": lo DEDUCE comparando dos bytes del gestor
#   `[0x931660]` —  `+0x40` = MI asiento  ·  `+0x41` = el asiento del ANFITRIÓN — y `+0x41` lo
#   escribe **el `@6` del `FF13`** (`0x59D0E6`). O sea que acá el server es la única autoridad:
#   cambiar de anfitrión = re-emitir el `FF13` con otro `@6`. Nada más.
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def poner_anfitrion(rid, usn):
    """Anota quién manda en la sala. Devuelve el usn anotado (o None).

    ★ Y le saca el LISTO, porque **el anfitrión no tiene botón de listo**: tiene el de empezar.
      Lo destapó una pregunta del usuario armando las pruebas — *"¿y si el que quedó listo pasa a
      ser master?"*. Si hereda la sala con `ready` puesto, `enviar_listos` le repinta a todos un
      LISTO que él **no puede sacar**, porque no tiene el botón. Un cartel fantasma para siempre.
    """
    if rid is None or usn is None:
        return None
    with _mesa_lock:
        ANFITRION[rid] = usn
    _c = CONEXIONES.get(usn)
    if _c is not None and getattr(_c, "ready", False):
        _c.ready = False
        log("LOBBY", f"  ★ usn={usn} pasa a ser anfitrión de la sala {rid}: se le saca el LISTO "
                     f"(el anfitrión no tiene ese botón)")
    return usn

def anfitrion_de(rid):
    """El usn del anfitrión de la sala, o None."""
    if rid is None:
        return None
    with _mesa_lock:
        return ANFITRION.get(rid)

def slot_anfitrion(rid):
    """El ASIENTO del anfitrión = lo que viaja en el `@6` del `FF13`.

    ⚠ Se resuelve por la MESA, no se guarda: el asiento cambia solo con el `FF6B` (intercambio),
      y guardar una segunda copia del mismo dato es como se despegan las dos. Ver
      `intercambiar_asientos`, que ya paga ese precio con `st.room_slot`.
    ★ Si la sala no tiene anfitrión anotado (o el anotado ya no está sentado) se elige uno acá
      mismo: es lo que salva las salas que venían de antes de que esto existiera.
    """
    if rid is None:
        return HOST_SLOT
    mesa = mesa_de(rid)
    if not mesa:
        return HOST_SLOT
    usn = anfitrion_de(rid)
    for s, u in mesa.items():
        if u == usn:
            return s
    nuevo = elegir_anfitrion(rid)
    for s, u in mesa.items():
        if u == nuevo:
            return s
    return HOST_SLOT

def elegir_anfitrion(rid, excluir=None):
    """Elige y anota al anfitrión entre los que quedan sentados. Devuelve el usn (o None).

    ★ Gana el primero según `ORDEN_ASIENTOS` (2, 3, 1, 4, 0, 5), que es el mismo orden en que se
      reparten las sillas ⇒ **hereda el que entró antes**. Dos decisiones acá, las dos a propósito:
        · NO es al azar (el CBT usa `random.choice`): con sorteo la misma prueba da distinto cada
          vez y no se puede decir "tenía que quedar en el 3" leyendo el log.
        · NO es "el número de asiento más chico": con este reparto el segundo en entrar se sienta
          en el **3** y el tercero en el **1**, así que ordenar por número le daría la sala al que
          llegó último.
    """
    _orden = {s: i for i, s in enumerate(orden_asientos(rid))}
    with _mesa_lock:
        mesa = dict(OCUPACION.get(rid, {}))
        # ★ 17-oct (PROD): el COLGADO de la carrera (ver `lobby_carrera`, el reloj del cartel) hereda ÚLTIMO — en la
        #   sala 2 se le dio el mando a uno colgado y nadie pudo arrancar hasta que se le cortó la conexión
        libres = sorted(((s, u) for s, u in mesa.items() if u != excluir),
                        key=lambda su: (bool(getattr(CONEXIONES.get(su[1]), "carrera_colgada", False)),
                                        _orden.get(su[0], 99), su[0]))
        if not libres:
            ANFITRION.pop(rid, None)
            return None
        ANFITRION[rid] = libres[0][1]
        return libres[0][1]


def intercambiar_asientos(rid, slot_a, slot_b):
    """Permuta dos asientos de la mesa. Devuelve `(usn_que_estaba_en_a, usn_que_estaba_en_b)`.

    `slot_b` puede estar VACÍO: entonces no es un intercambio sino una mudanza, y el que estaba en
    `slot_a` se pasa al hueco. Las dos formas las resuelve el MISMO paquete `FF6B`, porque el
    applier del cliente (`cRoom::UserSetChangeSlot`, `0x5A0900`) se ramifica solo: si el segundo
    asiento no está en el mapa de ocupantes llama a su propio mover (`0x5A0590`).
    ★ Esto es una diferencia REAL con el CBT, donde ese camino no existía y había que mandar un
      comando distinto (allá el `FF37`) para mudarse a un hueco. Acá no hace falta.
    """
    with _mesa_lock:
        mesa = OCUPACION.setdefault(rid, {})
        ua, ub = mesa.get(slot_a), mesa.get(slot_b)
        # ★ anotar quién deja cada asiento, para `liberar_asiento` (ver su nota)
        _ant = ULTIMO_OCUPANTE.setdefault(rid, {})
        if ua is not None:
            _ant[slot_a] = ua
        if ub is not None:
            _ant[slot_b] = ub
        mesa.pop(slot_a, None)
        mesa.pop(slot_b, None)
        if ua is not None:
            mesa[slot_b] = ua
        if ub is not None:
            mesa[slot_a] = ub
    # ★★ `st.room_slot` es la OTRA copia del mismo dato: la que cada conexión cree suya. La leen el
    #   FF0C (el "me-detect" del cliente), el FF17 del listo y el reparto de la carrera. Moverla en
    #   la mesa y no acá deja al cliente creyendo que sigue en su asiento viejo — que es exactamente
    #   el bug que el CBT pagó con avatares superpuestos.
    for usn, nuevo in ((ua, slot_b), (ub, slot_a)):
        if usn is None:
            continue
        conn = CONEXIONES.get(usn)
        if conn is not None:
            conn.room_slot = nuevo
    return ua, ub


def difundir_ocupante(rid, usn, menos=None):
    """★★★ Le avisa a la sala de **UN SOLO** ocupante, no de todos.

    ⛔⛔ EL BUG QUE ARREGLA (2026-09-12), y lo vio anonimo03 jugando: *"hay 5 jugadores, entra 1 nuevo,
      el nombre del que entró —SÓLO el de él— debería aparecer en el chat"*. Lo que pasaba:

          entra jugador2  ->  a CADA uno de los 4 que ya estaban le mandábamos los 5 ocupantes

      Medido en el log (`ctr=226..230` y `246..250`): cinco `FF0C` por destinatario, cuatro de
      ellos de gente que ese cliente **ya tenía**.
      ⇒ Y el cliente saca *"%s ha entrado a la sala de juego."* por cada uno que procesa ⇒ el
        jugador ve **una lista de carteles con nombres de otros**, que es justo lo que reportó:
        *"sale el nombre de otro, no del que entra"*.

    ★ Con esto se manda **un** paquete por persona en vez de N, y el cartel sale una sola vez y con
      el nombre correcto. De paso, el tráfico de entrar a una sala baja de N² a N.

    ⚠ Se conserva `difundir_userlist` (la lista entera) porque hay caminos donde SÍ hace falta
      —cambios que afectan a varios asientos a la vez—; acá se elige el chico a propósito.
    """
    _ocu = None
    for otro in conexiones_en_sala(rid):
        if otro is None or getattr(otro, "cerrado", False):
            continue
        if _ocu is None:
            _sl = next((s for s, u in mesa_de(rid).items() if int(u) == int(usn)), None)
            if _sl is None:
                return 0
            _ocu = _ocupante_de(int(usn), int(_sl))
            # ★★ (140) 30-oct: y SU ceremonia de entrar a la sala, que sólo viaja en este FF0C (ver `FF0C_ENTRADA_A_SALA`)
            if FF0C_ENTRADA_A_SALA:
                try:
                    from .catalogo import entrada_de_sala                     # noqa: PLC0415
                    _ocu["entrada_sala"] = entrada_de_sala((db_get_char(int(usn)) or {}).get("parts"))
                except Exception as _e_ent:                                   # noqa: BLE001
                    log("SALA ", f"  ⚠ no pude leer la entrada a la sala de usn={usn}: {_e_ent!r}")
        if otro is menos:
            continue
        # ★★★★★ AL QUE TODAVÍA CARGA LA SALA NO SE LE MANDA NADA SUELTO (2026-09-23).
        #   anonimo03, metiendo 6 clientes a la vez: *"jugador3 no recibió el asiento de jugadora_prueba"*. La sonda:
        #       14:57:20  slot 1 (cuenta_admin) -> SOLTERO   ← este FF0C, con jugador3 todavía cargando y
        #                                                  jugadora_prueba TODAVÍA no en la sala: correcto… ahí
        #       14:57:22  slot 4 (jugadora_prueba)   -> pareja 1  ← llega jugadora_prueba: SU lado queda bien
        #       14:57:22  slots 0, 2, 3                 ← la lista de jugador3: cuenta_admin YA EXISTÍA ⇒ el
        #                                                  cliente no lo re-aplica (create-if-absent)
        #   ⇒ Los avisos sueltos a un cliente que carga crean personajes con datos de ESE instante,
        #     y la foto buena (su lista) ya no los corrige. Y el `FF48` que antes lo tapaba, a un
        #     cliente que carga, BORRABA enlaces (busca por nombre gente que ahí no existe).
        #   ★ El que carga no necesita nada de esto: su lista, que se arma cuando la pide, trae a
        #     TODOS con su pareja y sus joyas al día. "Ya tiene la sala" lo marca `enviar_userlist`.
        if getattr(otro, "sala_poblada", None) != rid:
            log("SALA ", f"  · a usn={getattr(otro, 'usn', '?')} no le va el ocupante {usn} suelto: "
                         f"todavía carga la sala (le llega en su propia lista)")
            continue
        try:
            # ★★★ `k=1`, NO 2 — y esto costó una prueba fallida (2026-09-12).
            #   El byte 1 del `FF0C` es la POSICIÓN EN LA TANDA: `1` = el primero, `2` = el resto.
            #   `enviar_userlist` manda k=1 en el primero y k=2 en los demás.
            #   ⛔ Yo mandaba un ocupante SOLO con `k=2`, o sea marcado como *"continuación de una
            #     tanda"* cuando es **el primero y único**. Síntoma reportado por anonimo03: *"entró
            #     jugador6 pero jugador2 no recibió el mensaje en el chat; lo recibió jugador6"*.
            #   ⇒ Un ocupante solo es siempre el primero de su tanda: `k=1`.
            otro.send_ff55(0x0C, build_ff0c_2013_real(_ocu, 1),
                           name=f"FF0C ocupante slot={_ocu['slot']} (sólo el que cambió, k=1)")
            # ★★★★★ Y EL ENLACE DE PAREJA **EN LA LÍNEA SIGUIENTE**, no antes (2026-09-12).
            #
            #   ⛔⛔ EL BUG QUE ESTO ARREGLA ERA MÍO, Y NO ERA "FALTA ALGO": **ERA DESTRUCTIVO.**
            #     El `FF48` sub 1 lleva el enlace (`0x596570` → `0x527B00` ×2) y yo lo mandaba en
            #     el `ENTERROOM`, o sea ANTES del `FF0C` que dibuja al recién llegado. Medido en
            #     el log, paquetes consecutivos: `ctr=242 FF48` y recién `ctr=243 FF0C slot=3`.
            #     El `FF48` busca a la gente **por nombre** (`0x4EBCB0`); al que entra todavía no
            #     lo encuentra y **devuelve 0xFF**. Entonces `0x527B00(slotViejo, item, 0xFF)`
            #     **sí encuentra al que ya estaba** y le estampa `nodo+0xC4 = 0xFF` = *soltero*.
            #   ⇒ El paquete no se perdía: **borraba el enlace de los que ya estaban**, en todas
            #     las conexiones de la sala. Eso explica el síntoma exacto que reportó anonimo03: ni
            #     la pareja ni los terceros lo veían, y sólo el que entra —que recibe a todos de
            #     cero— lo veía bien.
            #
            #   ★★ Acá el nombre YA resuelve, porque el `FF0C` de arriba acaba de dibujarlo.
            #   ★ Y `0x596570` enlaza **antes** de su gate, así que el enlace no depende del
            #     cartel; el gate sólo protege el cartel. Además dispara `0x5B1100` ×2, que es
            #     **[H]** el efecto sobre las cabezas ⇒ un paquete cubre las dos cosas.
            #   ⇒ Sin `FF15`, o sea **sin pisar el color del equipo y sin parpadeo**, que es
            #     justo lo que anonimo03 marcó como "no nativo".
            # ★★★★★ Y SÓLO A LOS QUE YA TERMINARON DE CARGAR LA SALA (2026-09-23).
            #   ⛔ anonimo03: *"el asiento de la pareja sale mal cuando voy metiendo todos los clientes
            #     a la vez"*. La sonda lo cazó en el cliente de jugador1, que TODAVÍA CARGABA:
            #         slot 5 -> pareja 4          ← el FF0C de Luis*A: enlace bien puesto
            #         «sí» (0x596570)             ← este FF48
            #         slot 5 -> pareja SOLTERO    ← busca «jugador1» POR NOMBRE (0x4EBCB0) y en su
            #                                        propia pantalla todavía no existe ⇒ 255 ⇒
            #                                        le estampa soltero a Luis*A
            #     y cuando después carga el resto, Luis*A ya existe y el FF0C no se re-aplica.
            #   ⇒ El que todavía carga NO lo necesita: su propia lista (el FF0C de cada ocupante
            #     trae la pareja en `cola[12]`) los enlaza al CREARLOS, sin buscar por nombre.
            #   ★ Y "terminó de cargar" lo dice el propio cliente: pide la lista (`h_20_ff0c`).
            _poblado = getattr(otro, "sala_poblada", None) == rid
            try:
                from .basedatos import db_pareja_de, db_anillo_de_pareja
                from .lobby_pareja import _s2c_pareja_en_sala
                _pj2 = db_pareja_de(int(usn))
                if not _poblado and _pj2:
                    log("SALA ", f"  · FF48 de pareja NO va a usn={getattr(otro, 'usn', '?')}: todavía "
                                 f"carga la sala (el enlace le llega en su propia lista)")
                if _poblado and _pj2 and any(int(u) == int(_pj2) for u in mesa_de(rid).values()):
                    _n1 = (_ocu.get("nick") or "")
                    _n2 = str((db_get_char(_pj2) or {}).get("nick", "") or "")
                    otro.send_ff55(0x48, _s2c_pareja_en_sala(db_anillo_de_pareja(int(usn)), _n1, _n2),
                                   name=f"FF48 enlace+cartel «{_n1} & {_n2}» (detrás del FF0C)")
            except Exception as _e48:                            # noqa: BLE001
                log("SALA ", f"  ⚠ no pude mandar el enlace de pareja: {_e48!r}")
            # ★★ Y LAS JOYAS DE LOS QUE YA ESTABAN (2026-09-23). Con el recién llegado, la lista
            #   de sus amigos del alma presentes CRECE (una joya más), pero el cliente no los
            #   redibuja solo ⇒ se los recrea, sólo a ellos y sólo en ESTE cliente. Va DETRÁS del
            #   `FF0C` del que entra, por el mismo motivo que el enlace de pareja de arriba.
            if FF0C_JOYAS_ALMA and _poblado:
                actualizar_ocupantes(rid, almas_presentes(usn, rid), destinos=[otro],
                                     motivo=" (llegó su amigo del alma)")
            # ★★★ (92) 18-oct · Y LOS QUE MIRAN, OTRA VEZ, DETRÁS DEL QUE ENTRA. anonimo03 lo vio: *«cuando un jugador nuevo
            #   entra, la lista de espectadores se vacía; antes estaba poblada»*. Medido con la sonda (la sala de jugador52
            #   recreada 1 a 1): el FF0C k=1 de arriba («principio de lista», el que hace falta para el cartel «X ha
            #   entrado») le BORRA a este cliente los casilleros 6..11 de la sala Y del padrón. Al que mira le borra su
            #   PROPIA ficha ⇒ al largar no se encuentra (0x4440A0 = 0), se cree corredor en el lugar 6/7 y se cierra
            #   (prod 17-oct: jugador52, jugador10, jugador51; caja negra 0x4851C5 desde 0x563162).
            #   ⇒ Acá mismo, su FF0C ESPECTADOR con k=2 (continuación de la tanda: sin cartel). Como el k=1 los acaba de
            #     borrar, el «crear si está libre» del cliente los vuelve a crear con la marca. Nativo: no se rearma nada.
            if ESPECTADORES_TRAS_EL_QUE_ENTRA and _poblado:
                try:
                    from .lobby_salas import _ocupante_espectador          # import perezoso: el ciclo de siempre
                    for _ce in espectadores_de(rid):
                        _oe = _ocupante_espectador(_ce, incluir12=getattr(otro, "slot_espectador", None) is not None
                                                   or ESPECTADOR12_A_CORREDORES)
                        if _oe is None:
                            continue
                        otro.send_ff55(0x0C, build_ff0c_2013_real(_oe, 2),
                                       name=f"FF0C ESPECTADOR slot={_oe['slot']} {_oe['nick']!r} (repuesto tras el que entra)")
                except Exception as _e_re:                               # noqa: BLE001
                    log("SALA ", f"  ⚠ no pude reponer los espectadores tras el que entra: {_e_re!r}")
        except Exception as e:                                   # noqa: BLE001
            log("SALA ", f"  ⚠ no pude avisar del ocupante {usn}: {e!r}")
    return 1 if _ocu is not None else 0


def difundir_userlist(rid, menos=None, por_salida=False):
    """Re-manda el FF0C a todos los de la sala (menos a uno). Es como se entera el que ya estaba.

    ★ 16-oct · `por_salida=True` (los caminos donde alguien SE VA): si la sala está EN CARRERA no se manda nada.
      ⛔ Medido con 6 clientes en cooperativo: la lista entera a mitad de carrera sale en pantalla como
      «jugador17 ha entrado a la sala de juego» (de uno que nunca se fue). Lo que borra al que se fue es el `FF0E`
      (`difundir_salida`), que se sigue mandando; la lista era «para dejarla consistente» (heredado del CBT) y en
      la sala de espera se deja igual. Mismo cartel falso que ya se había sacado al ENTRAR (`FF0C_SOLO_EL_QUE_ENTRA`).

    ★★ Y "todos" son los sentados **y los que miran** (2026-09-08). ⛔ El bug que arregla, medido
      en pantalla: *"si entra alguien desde la lista de salas, los espectadores no reciben la
      actualización: siguen viendo ese asiento como libre"*. Recorría `mesa_de` = los SENTADOS, y
      el que miraba se quedaba con la foto del momento en que entró.
      Es la misma familia que el chat, el modo, el arranque, la salida y el `open_mask` — van
      **siete**. Cuando algo de la sala no le llega al espectador, empezar por acá: la pregunta no
      es "¿qué le falta al espectador?" sino "¿esta difusión usa `mesa_de` o `conexiones_en_sala`?".
    """
    if por_salida and any(getattr(CONEXIONES.get(_u), "en_carrera", False) for _u in mesa_de(rid).values()):
        log("LOBBY", f"  · sala {rid} EN CARRERA: tras la salida va sólo el FF0E (sin la lista: saldría «X ha entrado»)")
        return
    for otro in conexiones_en_sala(rid):
        usn = getattr(otro, "usn", None)
        if otro is None or otro is menos or getattr(otro, "cerrado", False):
            continue
        try:
            enviar_userlist(otro)
            enviar_ready_npcs(otro, " (re-sync por cambio de ocupantes)")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude re-mandar el FF0C a usn={usn}: {e!r}")

# ─────────────────────────────────────────────────────────────────────────────────────────────────
# ★ NPCs de sala — "spawnear un jugador" = agregar una ENTRADA MAS al FF0C USERLIST (no hay comando
#   de spawn en el protocolo). Se factoriza acá para poder re-emitir la lista EN VIVO desde el
#   comando de chat `.npc` (ver FF08), no solo cuando el cliente pide el FF0C al entrar a la sala.
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def seleccion_de(rid):
    """`{"pista": …, "cancion": …}` de una sala. Nunca None: si no hay sala, los defaults."""
    with _mesa_lock:
        s = SELECCION_SALA.get(rid) or {}
    # ★ 08-oct: el 0 («Aleatoria») se CONSERVA — antes `or DEFAULT_ROOM_MAP` lo volvía 11 y la sala corría siempre
    #   la misma. El default va sólo si nadie eligió. El sorteo lo hace `pista_de_carrera`, al arrancar.
    return {"pista": int(s["pista"]) if "pista" in s else DEFAULT_ROOM_MAP,
            "cancion": int(s.get("cancion", 0) or 0),
            # ★ la mascara de bandas del picker; `None` = nadie la toco todavia
            "filtro": s.get("filtro"),
            # ★ la MANERA DE LISTA del anfitrión (29-sep, `picker.MODOS_FF1C`); `None` = nadie eligió
            "modo": s.get("modo"),
            # ★ la pista del COOPERATIVO (09-oct): aparte de la normal, así la que quedó de una carrera normal no le
            #   pisa la fija al chase. `None` = nadie la eligió (corre `CHASE_MAP_FIJO`)
            "pista_coop": s.get("pista_coop")}


def poner_seleccion(rid, pista=None, cancion=None, filtro=None, modo=None, pista_coop=None):
    """Guarda la pista, la cancion y/o el FILTRO DE BANDAS de la sala. Devuelve como quedo.

    ★★ `filtro` = `byMusicLevelFilter`, el ultimo byte del `FF1C`: **la mascara de las bandas
      encendidas en el picker** (la fila de iconos de arriba). Lo manda el propio cliente y hasta
      el 2026-09-09 lo tirabamos.
      Visto en el log: `00 63 03 00 0c` -> `0x0c` = bits 2 y 3 = DOS bandas prendidas.
    ⚠ Es una MASCARA, no un numero de banda: no se puede mandar de vuelta con el `FFC9`, que
      toma **una** banda y adentro le aplica `LevelToMask` (un solo bit). Se guarda igual, porque
      es el dato que hace falta y sin guardarlo no hay forma de saber que tenia puesto.
    """
    if rid is None:
        return {"pista": DEFAULT_ROOM_MAP, "cancion": 0, "filtro": None, "modo": None}
    with _mesa_lock:
        s = SELECCION_SALA.setdefault(rid, {})
        if pista is not None:
            s["pista"] = int(pista) & 0xFFFF
        if cancion is not None:
            s["cancion"] = int(cancion) & 0xFFFF
        if filtro is not None:
            s["filtro"] = int(filtro) & 0xFF
        if modo is not None:
            s["modo"] = str(modo)
        if pista_coop is not None:
            s["pista_coop"] = int(pista_coop) & 0xFFFF
    return seleccion_de(rid)


def mapa_de_sala(rid):
    """El stage que forzó el anfitrión con `.oscuro`, o `None` si nadie lo tocó."""
    if rid is None:
        return None
    with _mesa_lock:
        return MAPA_SALA.get(rid)


def poner_mapa_sala(rid, mp):
    """Fija (o borra, con `None`) el stage de TODA la sala. Sólo lo llama el anfitrión."""
    if rid is None:
        return None
    with _mesa_lock:
        if mp is None:
            MAPA_SALA.pop(rid, None)
        else:
            MAPA_SALA[rid] = int(mp) & 0xFFFF
        return MAPA_SALA.get(rid)


def pd_valofe_de(rid):
    """¿Esta sala juega con la tabla de puntaje del cliente moderno? Por defecto SÍ.

    ⚠ `rid is None` (un jugador sin sala) también devuelve el default: si algún día se pudiera
      correr sin sala, correría con la misma regla que todos, y no con una silenciosamente
      distinta. Un default que cambia según el camino es de los que se cobran en tres meses.
    """
    if rid is None:
        return PD_VALOFE_DEFAULT
    with _mesa_lock:
        return bool(PD_VALOFE_SALA.get(rid, PD_VALOFE_DEFAULT))


def poner_pd_valofe(rid, prendida):
    """Fija la tabla de puntaje de TODA la sala. Sólo lo llama el anfitrión, por `.pd on/off`."""
    if rid is None:
        return PD_VALOFE_DEFAULT
    with _mesa_lock:
        PD_VALOFE_SALA[rid] = bool(prendida)
        return PD_VALOFE_SALA[rid]


def eleccion_de(rid, usn, que):
    """Lo que ese jugador eligió PARA SÍ en esa sala (`que` = "pista" | "obstaculos"), o `None`."""
    if rid is None or usn is None:
        return None
    with _mesa_lock:
        return ELECCION_JUGADOR.get(rid, {}).get(usn, {}).get(que)


def poner_eleccion(rid, usn, que, valor):
    """Anota (o borra, con `None`) lo que ese jugador eligió para sí en esa sala."""
    if rid is None or usn is None:
        return None
    with _mesa_lock:
        mio = ELECCION_JUGADOR.setdefault(rid, {}).setdefault(usn, {})
        if valor is None:
            mio.pop(que, None)
        else:
            mio[que] = int(valor) & 0xFFFF
        return mio.get(que)


def obstaculos_elegidos(rid, usn):
    """Lo que manda para ESE jugador: lo suyo; si no eligió, lo del anfitrión; si tampoco, `None`.
    ⚠ `0` NO es «nada»: es «aleatorios» (la «Aleatoria» de la ventana, elegida en modo obstáculos)."""
    propio = eleccion_de(rid, usn, "obstaculos")
    if propio is not None:
        return propio
    return eleccion_de(rid, anfitrion_de(rid), "obstaculos")


def obstaculos_para(rid, usn):
    """Los obstáculos con los que corre ESE jugador: los suyos; si no eligió, los del anfitrión; si
    tampoco, 0 (= los de la pista, como siempre). La regla de anonimo03, 08-oct.
    ⚠ Si lo elegido es «aleatorios» también da 0: el sorteo lo hace `cola_ff25_jugador`, en cada START."""
    return obstaculos_elegidos(rid, usn) or 0


# ★ LA CONDICIÓN DE VICTORIA de una sala por equipos (etapa 5, 08-oct): 0 = normal · 1 = 2 de los 3 primeros
#   puestos · 2 = llega el equipo completo. ⏳ Por ahora sólo viaja y se dibuja; el resultado es la etapa 5.
VICTORIA_SALA = {}                     # roomid -> 0/1/2. Ausente = 0 (normal)


def victoria_de(rid):
    with _mesa_lock:
        return VICTORIA_SALA.get(rid, 0)


# ⚠ cuántos bytes NUESTROS van al final de cada FF13 (obstáculos u16 · victoria u8 · pista u16). Lo usan las pruebas
#   que miran el final del paquete del juego (la dificultad, las campanas): lo del juego termina ANTES de esto.
COLA_FF13_NUESTRA = struct.calcsize("<HBHBB")  # obstáculos · victoria · pista · ★ asientos (10-oct) · ★ equipos (15-oct)


def cola_ff13_jugador(st):
    """La cola NUESTRA del `FF13` (08-oct): va DESPUÉS de todo lo que lee el cliente (su última lectura es
    0x5CD514) y la lee la d3d9 (`panel_sala.c`, en 0x5CD519). Un cliente viejo no la mira.

      `obstaculos` u16 — lo que ve en su recuadro «Obstáculos»: 0xFFFF = nadie eligió (los de la pista) ·
                         0 = aleatorios · N = los de la pista N
      `victoria`   u8  — 0xFF = la sala NO es por equipos (no se dibuja el recuadro) · si no, 0/1/2
      `pista`      u16 — (09-oct) la pista con la que corre: en el COOPERATIVO la del mini-panel (la suya, o la de la
                         sala, o la fija); en una sala normal la suya o la de la sala. 0 = aleatoria.
      `asientos`   u8  — (10-oct) ★ la sala de 12 (el 6vs6): 12 = la d3d9 (`sala12_vista.c`) dibuja la sala estilo
                         coreano (12 tarjetas + la tarjeta grande); 0 = la sala de siempre.
      `equipos`    u8  — (15-oct) ★ 4 = la sala de 12 es de 4 EQUIPOS (relevo de 12 o equipo de 4, EQUIPOS_4.md): la
                         d3d9 pinta 4 colores, abre las 4 banderas y deja arrancar con equipos de a 3; 0 = lo de antes.
      ⛔ El orden es un contrato (se lee de corrido, como el FF25): lo nuevo va AL FINAL.
    """
    rid, usn = getattr(st, "room_id", None), getattr(st, "usn", None)
    ob = obstaculos_elegidos(rid, usn)
    por_equipos = bool(getattr(st, "room_mode", 0) & MODE_EQUIPO)
    if getattr(st, "room_colab", False):
        pi = pista_propia_de(rid, usn, coop=True)
        if pi is None:
            pi = pista_coop_de_sala(rid)
    else:
        pi = pista_propia_de(rid, usn)
        if pi is None:
            pi = seleccion_de(rid)["pista"]
    return struct.pack("<HBHBB", 0xFFFF if ob is None else ob & 0xFFFF, victoria_de(rid) if por_equipos else 0xFF,
                       pi & 0xFFFF, grande_de(rid) & 0xFF, 4 if es_cuatro12(rid) else 0)


def pista_de_carrera(pista):
    """La pista que se CORRE: la elegida, o —si es la 0, «Aleatoria»— una sorteada entre `PISTAS_DEL_SORTEO`.
    Se llama en cada START: la sala sortea una para todos los que no eligieron, y el que eligió «Aleatoria»
    para sí tiene su propio sorteo."""
    if pista:
        return int(pista)
    from .ajustes import PISTAS_DEL_SORTEO
    return random.choice(PISTAS_DEL_SORTEO)


def pista_propia_de(rid, usn, coop=False):
    """La pista que ese jugador eligió PARA SÍ en esa sala, o `None` si no eligió (= manda la de la sala).
    `coop=True`: la del COOPERATIVO, que va aparte (09-oct).

    ⚠ El anfitrión NO tiene pista propia: lo que él elige ES la de la sala (`h_28_ff1b` le borra la suya).
    """
    if usn is not None and usn == anfitrion_de(rid):
        return None
    return eleccion_de(rid, usn, "pista_coop" if coop else "pista")


def pista_coop_de_sala(rid):
    """La pista con la que corre el COOPERATIVO de la sala (sin las propias): el `.oscuro` si lo hay, si no la que
    eligió el anfitrión en el mini-panel, si no la fija (`CHASE_MAP_FIJO`). Es la MISMA cuenta que el START."""
    from .ajustes import CHASE_MAP_FIJO, CHASE_USAR_MAP_FIJO, DEFAULT_ROOM_MAP
    osc = mapa_de_sala(rid)
    if osc is not None:
        return osc
    elegida = seleccion_de(rid).get("pista_coop")
    if elegida is not None:
        return elegida
    return CHASE_MAP_FIJO if CHASE_USAR_MAP_FIJO else DEFAULT_ROOM_MAP


# ★ LA CARRERA GRANDE (el 6vs6, 10-oct-2026): cuántos corredores arma el cliente en esta sala.
#   0 = lo normal (6). Lo lee la d3d9 (`grande.c`) en el campo 3 del FF25 y, ANTES de que la carga arme los
#   corredores, pasa a N la creación y los 34 bucles «del 0 al 5» del motor (documentacion/MODO_6VS6.md §7-§8).
#   Vive en la SALA (la regla de [[estado-de-la-conexion-vs-la-sala]]). Por ahora sólo lo prende `.grande N`.
GRANDE_SALA = {}                       # roomid -> N (7..12)
GRANDE_TOPE = 12
RELEVO12 = set()                       # ★ 14-oct: las salas de 12 que son RELEVO de 4 equipos (RELEVO_12.md)
# ★ 15-oct · LOS 4 EQUIPOS FUERA DEL RELEVO (anonimo03: «que el modo de 4 equipos también funcione en ítem y velocidad
#   "equipo"», EQUIPOS_4.md): las salas de 12 con 4 equipos de 3 en lugares fijos — el relevo de 12 Y la batalla en
#   equipo de 4. Lo de la SALA (lugares fijos, banderas, flechita, el arranque, el marcador de 4) mira esto; lo de la
#   POSTA (planteles, cartel unificado) sigue mirando `es_relevo12`.
CUATRO12 = set()


def poner_relevo12(rid, si):
    """Marca (o desmarca) la sala como relevo de 12: 4 equipos de 3 en lugares fijos."""
    with _mesa_lock:
        (RELEVO12.add if si else RELEVO12.discard)(rid)
        if si:                                       # el relevo de 12 siempre es de 4; sacarle el relevo no le saca los 4
            CUATRO12.add(rid)


def poner_cuatro12(rid, si):
    """★ 15-oct: marca (o desmarca) la sala de 12 como de 4 EQUIPOS (relevo o batalla en equipo)."""
    with _mesa_lock:
        (CUATRO12.add if si else CUATRO12.discard)(rid)
        if not si:
            RELEVO12.discard(rid)


def es_relevo12(rid):
    with _mesa_lock:
        return rid in RELEVO12 and GRANDE_SALA.get(rid, 0) == 12


def es_cuatro12(rid):
    """★ 15-oct: ¿sala de 12 con 4 equipos de 3 (relevo de 12 o equipo de 4)?"""
    with _mesa_lock:
        return (rid in CUATRO12 or rid in RELEVO12) and GRANDE_SALA.get(rid, 0) == 12


def grande_de(rid):
    """N de la carrera grande de esa sala, o 0 si es una sala normal (6)."""
    if rid is None:
        return 0
    with _mesa_lock:
        return int(GRANDE_SALA.get(rid, 0) or 0)


def poner_grande(rid, n):
    """Prende (7..12) o apaga (0) la carrera grande de la sala. Devuelve lo que quedó."""
    n = int(n or 0)
    if not (7 <= n <= GRANDE_TOPE):
        n = 0
    with _mesa_lock:
        if n:
            GRANDE_SALA[rid] = n
        else:
            GRANDE_SALA.pop(rid, None)
            RELEVO12.discard(rid)
            CUATRO12.discard(rid)
    return n


def asientos_de_la_sala(rid):
    """Cuántos asientos de CORREDOR tiene la sala: 6, o N si es carrera grande."""
    return grande_de(rid) or 6


def orden_asientos(rid):
    """En qué orden se reparten los asientos de la sala (y quién hereda el anfitrión).

    La sala de 12 tiene el suyo (`ORDEN_ASIENTOS_12`: alterna rojo/azul); otra N grande, el de siempre + 6..N-1."""
    n = asientos_de_la_sala(rid)
    if n == 12:
        return list(ORDEN_ASIENTOS_12_RELEVO if es_cuatro12(rid) else ORDEN_ASIENTOS_12)
    return list(ORDEN_ASIENTOS) + list(range(6, n))


def cola_ff25_jugador(rid, usn):
    """Los campos del `FF25` que son de CADA destinatario. Van pegados al final, después de los de la
    sala (ver `documentacion/FF25_LOADGAME_BYTES.md`, campos 2 y 3).

      campo 2 · `obstaculos` u16 — de qué pista salen sus obstáculos (0 = los de la pista que corre).
                Lo lee la d3d9 (`obstaculos.c`) y lo usa en la carga de `backNNN.txt`.
      campo 3 · `corredores` u8  — ★ la carrera grande: cuántos corredores arma el cliente (0 = 6, lo de
                siempre). Lo lee la d3d9 (`grande.c`). Es de la sala, pero va acá porque el orden es uno solo.
    """
    ob = obstaculos_elegidos(rid, usn)
    if ob == 0:                               # «aleatorios»: un sorteo por jugador y por carrera
        from .ajustes import OBSTACULOS_DEL_SORTEO
        ob = random.choice(OBSTACULOS_DEL_SORTEO)
    return struct.pack("<HB", (ob or 0) & 0xFFFF, grande_de(rid) & 0xFF)


def avisar_a_uno(st, texto):
    """Una línea de chat firmada SERVER, **sólo para esta conexión**.

    ★ Vive acá y no en `chat.py` porque la usan tres módulos distintos y ya había tres copias del
      mismo armado de bytes dando vueltas. Tres copias de una cosa es donde empiezan los bugs:
      alguien arregla una y las otras dos siguen mal.

    ⚠ No revienta si la conexión se murió justo ahora: el que avisa casi nunca está en condiciones
      de hacer algo útil con esa excepción, y dejarla subir corta el resto del trabajo.
    """
    if st is None or getattr(st, "cerrado", False):
        return False
    _rb = str(texto).encode("cp1252", "replace")[:0xFF]
    _nk = b"SERVER"
    try:
        st.send_ff55(0x08, bytes([len(_nk)]) + _nk + bytes([len(_rb)]) + _rb + bytes([2, 0]),
                     name=f"FF08 aviso {texto!r}")
        return True
    except Exception as e:                                   # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude avisarle a usn={getattr(st, 'usn', None)}: {e!r}")
        return False


def avisar_a_la_sala(rid, texto):
    """Una línea firmada SERVER a TODOS los de la sala. Devuelve a cuántos llegó.

    ★ Vive acá y no en `chat.py` porque ya la usan dos módulos: los comandos y el cambio de modo
      de sala. Cuando algo lo necesitan dos, se mueve; si no, aparece la tercera copia.
    """
    return sum(bool(avisar_a_uno(CONEXIONES.get(u), texto)) for u in mesa_de(rid).values())


def contar_estado_de_sala(st, rid, es_anfitrion=False):
    """Le cuenta al que ACABA DE ENTRAR (o de CREAR) con qué reglas se juega en esta sala.

    ⛔ POR QUE EXISTE, reportado por anonimo03: *"cuando cambiamos el pd, el jugador que ya está en la
      sala es notificado, pero el que recién entró no se entera del estado del pd"*. Y tiene razón:
      el aviso salía **en el momento del cambio**, así que el que llegaba después jugaba con una
      regla que nadie le dijo. Se enteraba mirando un número raro en el cartel, que es la peor
      forma de enterarse de nada.

    ⚠ Se dice SIEMPRE, no sólo cuando está en el valor raro. Dos motivos:
      · el default es "PD Valofe", o sea que lo normal ES lo distinto — callarlo cuando está en el
        default dejaría sin avisar justo en el caso más común;
      · y es cómo un jugador nuevo se entera de que la perilla existe.

    ⚠ Va SÓLO a esta conexión. Repetírselo a los que ya estaban sería ruido en el chat cada vez
      que entra alguien.

    ★★ `es_anfitrion` ADEMÁS le dice CÓMO cambiarlo, y es idea de anonimo03: *"al crear la sala el
      master, al crearse la sala recibe el primer estado del pd + apagar/prender .pd off-on"*.
      Tiene todo el sentido: el único que puede tocar la perilla es él, y hasta ahora no había
      forma de enterarse de que existía salvo leyendo `.ayuda`.

    ⛔ Y ES LO QUE FALTABA, medido en pantalla el 14-sep: el que ENTRA sí recibía la línea, pero
      el que CREA la sala no — porque crear va por `CREATEROOM` (`FF10`) y entrar por `FF11`, que
      son dos caminos distintos. O sea que **al anfitrión, justo el que decide, nunca le llegaba**.

    ⚠ La pista va en renglón aparte y NO pegada al estado, para que la línea de estado siga siendo
      **exactamente la misma** en todos lados (la del comando, la del que entra y la del que crea).
      Si fueran distintas parecerían cosas distintas.
    """
    if rid is None:
        return
    # ⚠ "PD Normal" con N MAYÚSCULA, pedido de anonimo03: va al lado de "PD Valofe" y con la n
    #   chica parecía de otra familia. Las dos líneas tienen que verse hermanas.
    avisar_a_uno(st, "PD Valofe" if pd_valofe_de(rid) else "PD Normal")

    # ★★ EL MARCADOR, A TODOS LOS QUE ENTRAN — 2026-09-14, segundo pedido de anonimo03: *"también el
    #   score debe anunciarse a los que entran en sala, AUNQUE NO HUBIERA HABIDO UNA PARTIDA
    #   aún"*. Por eso no se pregunta si hay algo que mostrar: un `Score 0 - 0` también es
    #   información — dice que la serie arranca de cero, que es justo lo que uno quiere saber
    #   al sentarse.
    # ⚠ SÓLO en salas por equipos: en solo/cooperativo el marcador ni existe.
    _eq = sala_por_equipos(st)
    if _eq:
        avisar_a_uno(st, texto_marcador(rid))

    # ★ Y recién ahora las pistas del master. Van DESPUÉS del estado a propósito: primero lo que
    #   le importa a cualquiera, después lo que sólo él puede hacer.
    #
    #   ★★ TODAS EN UN RENGLÓN, pedido de anonimo03: *"al master mandamos 4 líneas, 2 para explicar
    #     algo que podríamos ponerlo en un mensaje"*. Y tiene razón — el chat del juego es angosto
    #     y cuatro renglones de golpe tapan lo que estaban hablando.
    #
    #   ⚠ SE ARMA COMO LISTA, no concatenando a mano, porque anonimo03 ya avisó que va a querer
    #     agregar otro. Con la lista, sumar un comando es UN renglón y el separador se acomoda
    #     solo; concatenando, cada agregado es una oportunidad de dejar un " -- " colgando.
    if es_anfitrion:
        # ⚠ "Master sala" y no "anfitrión": es como le dice anonimo03 y como le dicen los jugadores.
        #   El código sigue hablando de anfitrión adentro (`anfitrion_de`), pero lo que se muestra
        #   en pantalla usa la palabra de la gente.
        _suyos = [".pd off/on"]
        if _eq:
            _suyos.append(".reset score")       # sólo donde el marcador existe
        avisar_a_uno(st, "Master sala " + " -- ".join(_suyos))


def marcador_de(rid):
    """El marcador de la serie de esta sala: `(victorias_eq1, victorias_eq2)`."""
    if rid is None:
        return (0, 0)
    with _mesa_lock:
        m = MARCADOR.get(rid) or {}
        return (int(m.get(1, 0)), int(m.get(2, 0)))


def texto_marcador(rid):
    """★ 15-oct: la línea del marcador para el chat. Con 4 equipos (EQUIPOS_4.md) van los 4 — `Score 1 - 0` hablaba
    sólo del rojo y el azul."""
    if rid is not None and es_cuatro12(rid):
        with _mesa_lock:
            m = MARCADOR.get(rid) or {}
            v = [int(m.get(e, 0)) for e in (1, 2, 3, 4)]
        return "Score %d - %d - %d - %d" % tuple(v)          # rojo - azul - verde - naranja (corto: el chat corta)
    m1, m2 = marcador_de(rid)
    return f"Score {m1} - {m2}"


def reiniciar_marcador(rid):
    """El marcador vuelve a 0 - 0. Lo llama `.score reset`, del master de la sala.

    ⛔ POR QUE HACÍA FALTA, reportado por anonimo03: el marcador **no se reiniciaba nunca**, ni solo
      ni a mano. Sube con cada partida de equipo y sólo se borra cuando la sala muere — o sea que
      una sala que se queda abierta toda la tarde termina mostrando `7 - 5` de partidas que ya
      nadie recuerda, y no había forma de empezar de nuevo sin cerrar la sala y volver a armarla.

    ⚠ Se BORRA la entrada en vez de dejarla en `{1:0, 2:0}`: el cartel sólo dibuja el marcador
      cuando alguno de los dos no es cero, así que una sala sin entrada y una en 0-0 se ven igual.
      Menos estado colgado, mismo resultado.
    """
    if rid is None:
        return (0, 0)
    with _mesa_lock:
        MARCADOR.pop(rid, None)
    return (0, 0)


def rate_sala_de(rid, que=None):
    """El multiplicador de ESTA sala. Sin `que`, el diccionario entero.

    ⚠ 1.0 quiere decir "esta sala no agrega nada", NO "sin rate": el global sigue valiendo.
    """
    if rid is None:
        return 1.0 if que else {}
    with _mesa_lock:
        d = dict(RATE_SALA.get(rid) or {})
    if que is None:
        return d
    return float(d.get(str(que).lower(), 1.0))


def poner_rate_sala(rid, que, valor):
    """Fija el multiplicador de una sala. `valor` en 1.0 lo borra (para no dejar basura).

    ⛔ El que llama tiene que haber comprobado que es GM. Acá no se pregunta: esta función es el
      cajón, no la cerradura.
    """
    if rid is None:
        return 1.0
    k = str(que).lower()
    with _mesa_lock:
        d = RATE_SALA.setdefault(rid, {})
        if float(valor) == 1.0:
            d.pop(k, None)
            if not d:
                RATE_SALA.pop(rid, None)
            return 1.0
        d[k] = float(valor)
        return d[k]


def limpiar_rate_sala(rid):
    """Todos los multiplicadores de la sala vuelven a 1.0."""
    if rid is None:
        return
    with _mesa_lock:
        RATE_SALA.pop(rid, None)


def dificultad_de(rid):
    """La banda que eligió la sala, o `None` si nadie tocó el interruptor.

    `None` NO es un error: es "esta sala no eligió", y el `FF13` sigue cayendo en la banda del
    jugador, que es como venía funcionando. Así el cambio no altera ninguna sala existente.
    """
    if rid is None:
        return None
    with _mesa_lock:
        return DIFICULTAD_SALA.get(rid)


def poner_dificultad(rid, banda):
    """Guarda la dificultad elegida EN LA SALA. Devuelve la banda si se aceptó, o `None`.

    ⚠ SÓLO 1..8, y el rango está medido, no elegido por gusto: `LevelToMask` (`0x5BA360`) sólo
      devuelve un bit para ese rango, y el `FFC9` con un byte FUERA de 1..8 significa otra cosa
      (`0x58CEF0` -> categoría 13 = LIBRE, el picker sin filtro). Un valor de más no se guarda: se
      informa y se ignora, para que si algún día aparece uno lo veamos en el log en vez de que
      entre en silencio.
    """
    if rid is None:
        return None
    try:
        b = int(banda)
    except (TypeError, ValueError):
        return None
    if not 1 <= b <= 8:
        return None
    with _mesa_lock:
        DIFICULTAD_SALA[rid] = b
    return b


# ★★★★★ LAS 3 CANCIONES DEL COOPERATIVO — DE LA SALA, NO DE LA CONEXIÓN (2026-09-05).
#
#   ⛔ Dos bugs que reportó el usuario, y los dos salían de que el sorteo vivía en `st.chase_songs`
#      y **sólo se hacía en el handler del `FF4B`** (el cambio de modo):
#
#      1. *"al crear la sala YA en cooperativo y dar START, se carga 1 música en vez de 3, y
#         siempre la misma"* — creando la sala en cooperativo el `FF4B` **nunca corre**, así que
#         `chase_songs` no existía y el `FF25` caía al `[song]` de una sola canción (la default).
#         Por eso funcionaba si cambiabas a otro modo y volvías: ahí sí pasaba por el `FF4B`.
#      2. *"al volver a la sala y empezar otra partida se repiten las 3, el sorteo no vuelve a
#         ocurrir"* — mismo motivo: sin cambio de modo, nadie volvía a sortear.
#
#   ⇒ Ahora vive acá (room-level, como `SELECCION_SALA`) y se sortea **en cada START**.
#     Ver también el aviso de [[estado-de-la-conexion-vs-la-sala]]: es la quinta vez que aparece
#     el mismo error en este server.
CANCIONES_CHASE = {}                   # roomid -> [songid, …]


def canciones_chase(rid):
    """Las canciones sorteadas para esa sala, o `None` si todavía no se sortearon."""
    if rid is None:
        return None
    with _mesa_lock:
        v = CANCIONES_CHASE.get(rid)
    return list(v) if v else None


def poner_canciones_chase(rid, canciones):
    """Guarda el sorteo EN LA SALA. Devuelve la lista guardada."""
    if rid is None or not canciones:
        return list(canciones or [])
    with _mesa_lock:
        CANCIONES_CHASE[rid] = list(canciones)
    return list(canciones)


def npcs_de(rid):
    """Slots con NPC de una sala. Vive en la sala, no en la conexion (ver NPCS_SALA)."""
    with _mesa_lock:
        return list(NPCS_SALA.get(rid, []))

def poner_npcs(rid, slots):
    with _mesa_lock:
        NPCS_SALA[rid] = list(slots)

def slots_npc(st):
    """Slots de NPC vigentes. Si estoy en una sala, son LOS DE LA SALA (los mismos para todos).

    ★ Las salas ahora nacen SIN NPC (`NPC_IN_ROOM = False`): se invocan con `.npc N` / `.npc full`,
      como en el CBT. Antes cada sala arrancaba con uno y era lo que rompía el multijugador.
    """
    rid = getattr(st, "room_id", None)
    if rid is not None and rid in NPCS_SALA:
        return npcs_de(rid)
    if not getattr(st, "ghost", False):
        return []
    sl = getattr(st, "ghost_slots", None)
    return list(GHOST_SLOTS) if sl is None else list(sl)

def sala_por_equipos(st):
    """¿Esta sala reparte a la gente en equipos? Misma regla que usa el CLIENTE.

    ★ No la inventamos: `0x58BFF0` del cliente contesta exactamente esto, y es la función que
      consulta el guard del START (`0x592B50`) para decidir si exige equipos parejos:

        0058bff0  mov eax,[cRoom+0x9568]       ; CooperationMode
        0058bff6  test eax,eax / je -> sí      ;   0 = EQUIPO
        0058bffa  cmp eax,2    / je -> sí      ;   2 = RELEVO
        0058bfff  cmp [cRoom+0x9564],5 / je    ;   GameMode 5 = ★ JEFE
                  else -> no                   ;   SOLO / cooperativo: no aplica

    ⚠ El **jefe** entra por acá aunque su `room_mode` no traiga ningún bit de equipo: ese modo
      viaja en la cola del `FF13` (`+44`), no en el byMode. Es la razón por la que `enviar_equipos`
      —que se guarda con `MODE_EQUIPO | MODE_RELEVO`— se saltea el jefe entero.
    """
    return bool(getattr(st, "room_mode", 0) & (MODE_EQUIPO | MODE_RELEVO)) \
        or bool(getattr(st, "room_boss", False))


def equipo_para_ff0c(st, slot):
    """El valor del `rel12` del `FF0C` para ese asiento: el equipo, o **0** si la sala no los usa.

    ⚠ Esto llena el `rel12` del paquete y nada más. **El PADRÓN del cliente no se toca por acá**
      (ver la nota de `build_ff0c_2013_real`): a `sRoomUser+0x4A` se llega con el `FF37`, y de eso
      se ocupa `enviar_equipos`. Los dos hacen falta y no son intercambiables.

    ★★ POR QUÉ EL 0 EN SOLO — y la razón es del CLIENTE, no del server de referencia:

    1. `0x58BFF0` (la función de arriba) dice que en solo/cooperativo **la sala no es por
       equipos**. Es la misma que consulta el guard del START para decidir si exige equipos
       parejos: si el cliente no considera que haya equipos, mandarle uno es inventarle un
       estado que su propio código dice que no existe.
    2. Y por eso `enviar_equipos` ya se negaba a pintar en solo desde antes de todo esto: es la
       misma regla, aplicada a la otra estructura (el asiento en vez del padrón).
    3. (Apoyo heredado, NO re-verificado el 07-sep: la nota de `equipo_por_defecto` dice que el
       applier del `FF4B` `0x5971F0` tiene dos bloques cableados distintos, `0x597324` para
       equipo/cooperativo y `0x5972DA` para solo. Si alguna vez hace falta pelearla, hay que
       volver a leerla.)

    El corpus del referente **coincide** (148 de sus 234 ocupantes van en 0), pero eso es
    corroboración, no el fundamento: ese server tiene 81 code caves y lo que hace no es la ley.

    Ver la nota larga en `paquetes.build_ff0c_2013_real`.
    """
    if not sala_por_equipos(st):
        return 0
    rid = getattr(st, "room_id", None)
    return equipo_de(rid, slot) if rid is not None else equipo_por_defecto(slot)


# ★★★ SONDA DEL `FF0C` — para bisecar EN VIVO de qué campo sale el ícono de licencia (2026-09-07).
#
#   ⛔ EL SÍNTOMA, que lleva días: en la sala TODOS salen con el ícono de "Novato Estrella", sea
#     cual sea su licencia. Y no es sólo cosmético — lo confirmó el usuario probando el interruptor:
#     *"es por que mi slot no se dibujó con mi licencia luna, sino novato estrella"*. El CLIENTE
#     decide qué dificultades te deja elegir mirando el ícono que él mismo dibujó, así que un ícono
#     mal puesto te deja sin las bandas de arriba.
#
#   ⚠ Ya se descartaron TRES candidatos probándolos en pantalla (`rel6` del FF0C, `@20` del FF13 y
#     `rel18`), y los tres tenían a favor un calce de valores perfecto contra el referente. La
#     lección quedó escrita: **que los valores calcen no prueba qué dibuja el campo**.
#
#   ⇒ Por eso esto no es un arreglo: es un BANCO DE PRUEBAS. Se pisa un campo del `FF0C` desde el
#     chat (`.lic <campo> <valor>`), se re-emite la lista y se mira la pantalla. Vacío = todo
#     normal, así que si nadie lo usa el server se comporta exactamente igual que antes.
SONDA_FF0C = {}                        # campo del FF0C -> valor forzado (herramienta, no arreglo)

# ★★★★★★ EL ÍCONO DE LICENCIA DE LA SALA — RESUELTO (2026-09-07). SON **DOS** CAMPOS, NO UNO.
#
#   ⛔ EL SÍNTOMA, que llevaba días: en la sala TODOS salían con el ícono de "Novato Estrella".
#     Y no era cosmético: el CLIENTE decide qué dificultades te deja elegir mirando el ícono que él
#     mismo dibujó, así que un ícono mal puesto también te dejaba sin las bandas de arriba.
#
#   ⛔⛔ POR QUÉ SE ESCAPÓ TRES VECES. El `rel6` se había probado solo (04-sep y 07-sep) y "no
#     movía nada", así que se descartó. **Estaba bien identificado desde el principio**: lo que
#     fallaba es que solo NO ALCANZA. Con el `rel4` en 0 el cliente ni llega a leerlo. Hacen falta
#     LOS DOS, y probar de a un campo por vez no podía encontrarlo nunca.
#     ⇒ Regla que deja: si un campo "no hace nada", puede que le falte el compañero.
#
#   ★ LA TABLA, MEDIDA DOS VECES Y DE DOS MANERAS INDEPENDIENTES:
#
#     (a) 247 ocupantes de 46 capturas del referente dan **exactamente 6 combinaciones**, ni una más:
#            mision   rel6   jugadores
#            0x0000     0        3
#            0x0000     1        4
#            0x0010     1       22
#            0x0010     3        1
#            0x0100     3        8
#            0x0100     7       15
#
#     (b) y el usuario las verificó EN PANTALLA con la sonda `.lic`, que es lo que las tres veces
#         anteriores faltó:
#            (0x0010, 1) -> "Novato Luna"     ·  (0x0010, 3) -> ★ "Luna"
#            (0x0100, 3) -> "Novato Solar"    ·  (0x0020/0x0030, ·) -> no cambian nada
#         Y los que no cambian confirman el mapeo: `0x0020` es "Nuevos retos" y `0x0030` es
#         "Revancha con King" — no son licencias. Ver `documentacion/mapeo_misiones.md`.
#
#   ⇒ LOS DOS CAMPOS HACEN COSAS DISTINTAS:
#        · `rel4` (mision) = el GRUPO      0 -> estrella · 0x0010 -> lunar · 0x0100 -> solar
#        · `rel6`          = LA LICENCIA, y es **literalmente nuestra columna `chars.licencia`**:
#                            los mismos 0/1/3/7, sin conversión.
#     Se ve solo en la prueba: con el grupo lunar puesto, `rel6=7` NO sube a Sol — Luna es el techo
#     de ese grupo. Por eso hay que mover los dos juntos.
#
#   ⚠ El `rel4` real del referente es el AVANCE de misiones del jugador, que puede ir por delante
#     de su licencia (22 de sus ocupantes tienen licencia Estrella pero ya la misión lunar hecha, y
#     se ven "Novato Luna"). Nosotros mandamos el MÍNIMO que dibuja la licencia que la cuenta tiene
#     de verdad: es lo correcto para nuestra base, donde `mission` vale 0 en las 4.806 cuentas.
#   ⇒ La cuenta vive en `paquetes.mision_para_icono`, o sea en el ÚNICO sitio que construye el
#     `FF0C`. Acá sólo se le pasan los datos crudos del personaje. La primera versión la calculaba
#     en esta función y la prueba lo destapó: hay otros caminos que arman un `FF0C` (el de cambiar
#     ropa) y por ésos el ícono se habría perdido en silencio.


def joyas_alma_de(usn, mesa):
    """Los `Id` de ring.txt <Friend> que dibuja el personaje de `usn`: la joya de CADA amigo del
    alma que esté sentado en `mesa`. Va en el `FF0C` como `cola[40]` + N bytes
    (ver `FF0C_JOYAS_ALMA`).

    ★ UNA sola función para los DOS armadores del ocupante: `armar_ocupantes` (al poblar la sala)
      y `_ocupante_de` (los redibujos: ropa, personaje, joyas). Es la lección del CBT que ya está
      escrita para la pareja: *"dos consumidores del mismo dato y uno solo calculándolo"* da
      *"a veces sí y a veces no"*. ⚠ Sin esto, cambiarse de ropa en la sala borraba las joyas.
    """
    try:
        from .basedatos import db_almas_de
        from .catalogo import anillo_de
        _presentes = {int(u) for u in (mesa or {}).values()}
        _ids = []
        for _f in (db_almas_de(int(usn)) or []):
            if int(_f.get("otro_uid") or 0) in _presentes:
                _jid = int(anillo_de(int(_f.get("joya") or 0)).get("id") or 0)
                if 0 < _jid < 0xFF:
                    _ids.append(_jid)
        return _ids
    except Exception as _e:                                      # noqa: BLE001
        log("SALA ", f"  ⚠ no pude armar las joyas del alma de usn={usn}: {_e!r}")
        return []


def almas_presentes(usn, rid):
    """Los amigos del alma de `usn` que están SENTADOS en la sala `rid` (sin contarlo a él)."""
    try:
        from .basedatos import db_almas_de
        _mesa = {int(u) for u in (mesa_de(rid) or {}).values()} if rid is not None else set()
        return [int(f.get("otro_uid") or 0) for f in (db_almas_de(int(usn)) or [])
                if int(f.get("otro_uid") or 0) in _mesa and int(f.get("otro_uid") or 0) != int(usn)]
    except Exception:                                            # noqa: BLE001
        return []


def ff15_de(occ, rid, pareja_slot=None):
    """El `FF15` de un ocupante, con TODO lo que su cola lleva: equipo, capitán, pareja y joyas.

    ★ UNA sola forma de armarlo para los que lo mandan (ropa, personaje, enlace de pareja,
      joyas). Si cada uno lo armara a mano, el que se olvide del equipo lo borra del padrón — que
      es literalmente lo que pasaba hasta hoy (ver `paquetes.build_ff15_2013`).
    """
    from .catalogo import face_id, wing_id, wing_id_con_aura
    _sl = int(occ.get("slot", 0))
    _prt = occ.get("parts") or []
    _eq = occ.get("equipo")
    if _eq is None:
        _cx = CONEXIONES.get(int(occ.get("usn", 0) or 0))
        _eq = equipo_para_ff0c(_cx, _sl) if _cx is not None else 0
    _ps = occ.get("pareja_slot") if pareja_slot is None else pareja_slot
    return build_ff15_2013(_sl, int(occ["char_id"]), [occ["char_id"]] + [p for p in _prt if p],
                           next((f for f in (face_id(p) for p in _prt) if f), 0),
                           wing_id_con_aura(_prt, occ.get("usn")),  # ★ 30-oct: + el aura de suelo · (142) la montura
                           0xFF if _ps is None else _ps,
                           equipo=_eq,
                           capitan=bool(_eq) and capitanes_de(rid).get(_eq) == _sl,
                           joyas=occ.get("joyas_alma") or (),
                           marco=int(occ.get("marco", 0) or 0),
                           tarjeta=int(occ.get("tarjeta", 0) or 0),
                           medalla=int(occ.get("medalla", 0) or 0),
                           color_apodo=int(occ.get("color_apodo", 0) or 0))


def actualizar_ocupantes(rid, usns, motivo="", destinos=None):
    """El `FF15` de cada `usn` a cada destino (por defecto, toda la sala). Devuelve a cuántos.

    ★★★ EL CAMINO NATIVO para cambiar algo de alguien que YA está en la sala (2026-09-23).
      anonimo03, sobre recrear al ocupante: *"eso sólo es esconder un síntoma; durante el desarrollo
      se propuso repintar varias veces cuando existía una forma nativa"*. La hay: el `FF15` es
      `CmdRoomUserInfo` (nombre del cliente 2019) y su handler redibuja las joyas sobre el
      ocupante existente (`0x5F3E01` -> `0x5B0AA0`), sin sacarlo ni volver a ponerlo.
      Hasta hoy no servía porque nuestro `FF15` no llegaba a la cola donde viaja la lista.
    """
    _hechos = 0
    try:
        _mesa = mesa_de(rid) if rid is not None else {}
        _slot_de = {int(u): int(s) for s, u in (_mesa or {}).items()}
        _dest = list(destinos) if destinos is not None else list(conexiones_en_sala(rid))
        _paqs = []
        for _u in usns or ():
            if int(_u) not in _slot_de:
                continue                      # ⛔ un FF15 de alguien que no está: nada que actualizar
            _o = _ocupante_de(int(_u), _slot_de[int(_u)])
            _paqs.append((_o, ff15_de(_o, rid)))
        if not _paqs:
            return 0
        for _c in _dest:
            if _c is None or getattr(_c, "cerrado", False):
                continue
            for _o, _p in _paqs:
                _c.send_ff55(0x15, _p, name=f"FF15 {_o.get('nick')!r} slot {_o.get('slot')} "
                                            f"joyas={_o.get('joyas_alma') or []}{motivo}")
            _hechos += 1
        log("SALA ", f"  ★★ ALMA: FF15 de {[o.get('nick') for o, _p in _paqs]} a "
                     f"{_hechos} cliente(s) de la sala {rid}{motivo}")
    except Exception as _e:                                      # noqa: BLE001
        # ⚠ Es un adorno: no puede romper la entrada ni la salida de una sala.
        log("SALA ", f"  ⚠ no pude actualizar ocupantes {list(usns or ())}: {_e!r}")
    return _hechos


def _insignia(usn, char):
    """`(marca, nivel)` del círculo, sólo si tiene uno (una consulta); si no, `(0, 0)`."""
    if not char.get("guild"):
        return (0, 0)
    try:
        from .basedatos import db_insignia_circulo                    # noqa: PLC0415
        return db_insignia_circulo(usn)
    except Exception:                                                  # noqa: BLE001
        return (0, 0)


def _color_apodo(usn, char):
    try:
        from .catalogo import color_apodo_de                          # noqa: PLC0415
        return color_apodo_de(usn, char)
    except Exception:                                                  # noqa: BLE001
        return 0


def _ocupante_de(usn, slot):
    """Una entrada del FF0C a partir del personaje REAL de esa cuenta.

    ★ `identity` = el slot del ocupante. El cliente se reconoce comparando identity contra SU slot
      (`me+0x40`), así que la misma lista sirve para los dos jugadores: cada uno se ve a sí mismo
      como local y al otro como remoto, sin armar un paquete distinto por espectador.
    """
    char = db_get_char(usn) or {}
    cid = char.get("char_id", 0x0001FF54)
    # ★ `mision` (el `rel4`) NO se ponía, así que `build_ff0c_2013_real` lo mandaba en 0 SIEMPRE.
    #   Es el campo donde el referente trae 0x0010 / 0x0100 según la licencia del jugador, y en
    #   este juego la licencia se GANA haciendo misiones — de ahí la sospecha. Ahora sale de la
    #   base; hoy vale 0 en las 4.806 cuentas, así que por sí solo no cambia nada todavía.
    occ = {"usn": usn, "char_id": cid, "parts": parts_visibles(char),
           "nick": char.get("nick", ""), "guild": char.get("guild", ""),
           # ★ el CÍRCULO al lado del nombre (`<círculo> apodo`, `FF0C cola[4]`, 24-sep)
           "texto_cabeza": char.get("guild", ""),
           "identity": slot, "slot": slot,
           # ★ la MARCA y el NIVEL del círculo en la tarjeta de la sala (`FF0C cola[32..39]`, 25-sep)
           "circulo_insignia": _insignia(usn, char),
           "color_apodo": _color_apodo(usn, char),     # ★ el lápiz del apodo (`cola[13]`, 25-sep)
           "exp": int(char.get("exp", 0) or 0), "gender": sexo(cid),
           "mision": int(char.get("mission", 0) or 0),
           "licencia": int(char.get("licencia", 0) or 0)}
    # ★ Los nibbles van CRUDOS: la máscara del ícono la calcula `paquetes.mision_para_icono`.
    occ["mision_nibbles"] = list(char.get("mision_nibbles") or [])
    # ★★ EL MARCO DE ASIENTO sale de lo PUESTO de verdad (`parts` de la base), no de las prendas
    #   visibles: no es ropa, y un personaje del gacha no lo tapa (2026-09-23).
    from .catalogo import marco_puesto, tarjeta_puesta                     # noqa: PLC0415
    occ["marco"] = marco_puesto(char.get("parts"))[0]
    occ["tarjeta"] = tarjeta_puesta(char.get("parts"))
    # ★ La medalla puesta (24-sep): va arriba de la cabeza, `cola[29..32]` del FF0C. Ver `medallas.py`.
    occ["medalla"] = medalla_puesta(usn)
    # ★★★★★ Y LOS CAMPOS DE PAREJA (2026-09-12). ⛔ NO ESTABAN, y eso hacía que **cualquier
    #   camino que re-dibujara al ocupante le estampara "soltero"**.
    #   Lo destapó anonimo03 probando una acción de pareja: *"al intentar la acción el slot se
    #   despinta, porque el FF o respuesta actual no es la indicada"*. El log dio la secuencia:
    #
    #       FF1A  EQUIP item=30562 fam=ring_couple   ← el cliente EQUIPA el anillo para la acción
    #       FF0C  "apariencia nueva"  +  FF15 reload ← y nosotros contestamos como si fuera ropa
    #
    #   Ese `FF0C` re-escribe la entrada entera del ocupante, y como acá no venía ni el asiento de
    #   la pareja (`cola[12]`) ni el anillo (`cola[0..3]`), salía con `0xFF` = soltero.
    #   ⇒ Se llenan **en el origen**, no con un paquete extra detrás: así lo arregla para TODOS
    #     los caminos que usan esta función, no sólo para el que lo destapó.
    #   ★ Es la misma familia del equipo (`rel12`) y del color del slot, que ya nos mordió seis
    #     veces: **este paquete no “agrega” — reemplaza**. Lo que no se pone, se borra.
    try:
        from .basedatos import db_pareja_de, db_anillo_de_pareja
        _pj = db_pareja_de(int(usn))
        if _pj:
            # ★ La sala sale de la CONEXIÓN del jugador, que es donde vive el `room_id`.
            #   ⚠ Y el asiento de la pareja se busca en la mesa de ESA sala: si no está sentada
            #     ahí, no hay enlace que dibujar y se deja soltero — que es lo correcto.
            _cx = CONEXIONES.get(int(usn))
            _rid = getattr(_cx, "room_id", None) if _cx is not None else None
            _mesa = mesa_de(_rid) if _rid is not None else {}
            _sl = next((int(s2) for s2, u2 in (_mesa or {}).items() if int(u2) == int(_pj)), None)
            if _sl is not None:
                occ["pareja_slot"] = _sl
                occ["anillo"] = db_anillo_de_pareja(int(usn))
    except Exception:                                            # noqa: BLE001
        pass                                                     # sin pareja dibujada, como antes
    # ★★ Y LAS JOYAS DEL ALMA, por la misma razón que la pareja: este `FF0C` REEMPLAZA la entrada
    #   entera, así que lo que no venga acá se borra (2026-09-23).
    try:
        _cx2 = CONEXIONES.get(int(usn))
        _rid2 = getattr(_cx2, "room_id", None) if _cx2 is not None else None
        _jo = joyas_alma_de(usn, mesa_de(_rid2) if _rid2 is not None else {})
        if _jo:
            occ["joyas_alma"] = _jo
    except Exception:                                            # noqa: BLE001
        pass
    occ.update(SONDA_FF0C)             # la sonda manual pisa al final, si se usó
    return occ

def armar_ocupantes(st):
    """Los JUGADORES REALES de la sala + un NPC por cada slot vigente que quede libre."""
    rid  = getattr(st, "room_id", None)
    mesa = mesa_de(rid) if rid else {}
    if not mesa:
        # Sala sin mesa (un maniquí de SALAS_DEMO, o el arranque antes de sentarse): como siempre.
        # ⛔ BUG DE `or` CON EL SLOT 0 (cazado 2026-08-05). Acá decía `... or HOST_SLOT`, y en Python
        #   **`0 or 2` es 2**: al jugador que estaba en el SLOT 0 lo sentábamos en el 2.
        #   En las salas de carrera nunca se notó porque el creador cae en el slot 2 igual. En los
        #   LUGARES ESPECIALES (charla / casa) el primero entra en el **slot 0** ⇒ el `FF61` le decía
        #   al cliente "sos el slot 0" y el `FF0C` lo listaba en el 2 ⇒ **el cliente no se encontraba
        #   a sí mismo** (me-detect por `[0x931660]+0x40`) y quedaba sin poder moverse.
        #   ★ Es el MISMO tipo de bug que ya nos mordió con el `@6` del FF13: un valor válido que
        #     resulta ser falsy. Con offsets y slots, usar `is None`, nunca `or`.
        _sl0 = getattr(st, "room_slot", None)
        mesa = {(HOST_SLOT if _sl0 is None else _sl0): getattr(st, "usn", 0)}
    ocupantes = [_ocupante_de(u, s) for s, u in sorted(mesa.items())]
    # ★ EL EQUIPO (`rel12` del FF0C) — 0 si la sala no usa equipos. Ver `equipo_para_ff0c`.
    for _o in ocupantes:
        _o["equipo"] = equipo_para_ff0c(st, _o["slot"])
    # ★★★★★ EL ENLACE DE PAREJA — los corazones entre los dos asientos (2026-09-12).
    #   El cliente dibuja **los corazones, el fondo del slot Y el efecto del anillo él solo**: el
    #   `SlotBackId` y el `RoomFx` son frames/efectos de SUS propios archivos (`ring.txt`). Lo
    #   único que necesita del server son dos datos, y viajan en el FF0C:
    #       · en qué asiento está mi pareja   (`0xFF` = soltero)
    #       · qué anillo llevamos            (para buscar su fila en `ring.txt`)
    #   ⇒ Por eso los tres pendientes de anonimo03 (corazones, color del slot y efecto de sala) son
    #     **un solo cambio**, no tres.
    #
    #   ★ Esto el CBT lo resolvió al final y quedó escrito: *"el enlace de asientos VIAJA EN EL
    #     FF0C, y sin cartel"*. Allá se descubrió después de meses de pelear con otro paquete.
    #   ⚠ Sólo se enlaza si **los dos están en esta sala**: el recuadro es entre dos asientos.
    try:
        from .basedatos import db_pareja_de, db_anillo_de_pareja
        _por_usn = {int(_u): int(_s) for _s, _u in mesa.items()}
        for _o in ocupantes:
            _mio = int(_por_usn and next((u for u, sl in _por_usn.items() if sl == _o["slot"]), 0))
            _pj = db_pareja_de(_mio) if _mio else 0
            if _pj and _pj in _por_usn:
                _o["pareja_slot"] = _por_usn[_pj]
                _o["anillo"] = db_anillo_de_pareja(_mio)
    except Exception as _e:                                      # noqa: BLE001
        # ⚠ Un problema acá NO puede romper el armado de la sala: el enlace es un adorno.
        log("SALA ", f"  ⚠ no pude armar el enlace de pareja: {_e!r}")
    # ★★★★★ LA JOYA DE LA AMISTAD — misma idea que el anillo, y la ayuda del juego lo dice con
    #   todas las letras: *"La joya que tienes equipado aparece **cuando estés junto a tu amigo
    #   del alma**"*. ⇒ igual que el recuadro de pareja, **sólo si los dos están en esta sala**.
    #   ⚠ Va en `cola[33..36]` del `FF0C`, NO en el `worn`: la joya es categoría 12 y el arreglo
    #     del cliente tiene 11 ranuras. Ver la nota larga en `paquetes.build_ff0c`.
    try:
        from .basedatos import db_almas_de
        _por_usn2 = {int(_u): int(_s) for _s, _u in mesa.items()}
        for _o in ocupantes:
            _mio = next((u for u, sl in _por_usn2.items() if sl == _o["slot"]), 0)
            if not _mio:
                continue
            # ★★★★★ LA LISTA DE JOYAS (2026-09-23): el `Id` de ring.txt <Friend> de la joya de
            #   CADA amigo del alma presente. Es lo que dibuja el cliente (`cola[40]` + N bytes;
            #   ver `FF0C_JOYAS_ALMA`). Lo de abajo (`joya_alma`/`texto_cabeza`) es el intento
            #   viejo del 15-sep, con sus dos perillas apagadas.
            _ids = joyas_alma_de(_mio, mesa)
            if _ids:
                _o["joyas_alma"] = _ids
            for _f in (db_almas_de(_mio) or []):
                if int(_f.get("otro_uid") or 0) in _por_usn2:
                    # ★ La primera que encuentre presente. ⏳ La ayuda dice que *"si tenés más
                    #   amigos del alma, las joyas también aumentan"* ⇒ con dos presentes deberían
                    #   verse dos. El segundo campo candidato es `desc+0x54`, todavía sin mapear.
                    _o["joya_alma"] = int(_f.get("joya") or 0)
                    # ⏳ LA APUESTA DEL TEXTO: al encender la joya salió `(null)` sobre la cabeza,
                    #   así que ese renglón espera algo. Se prueba con **el nombre del amigo del
                    #   alma**, que es lo que más sentido tiene al lado de la joya compartida.
                    #   ⚠ Es [NM]: si sale en otro lado, o si el juego esperaba el nombre del
                    #     círculo, la pantalla lo dice en una corrida. Perilla:
                    #     `FF0C_TEXTO_DE_CABEZA`.
                    #   ⛔ (24-sep) Ya NO se pone: esa string es el CÍRCULO (probado en pantalla,
                    #     ver `FF0C_TEXTO_DE_CABEZA`) y ahora la llena `_ocupante_de` con el de verdad.
                    break
    except Exception as _e:                                      # noqa: BLE001
        log("SALA ", f"  ⚠ no pude armar la joya del alma: {_e!r}")
    char = db_get_char(getattr(st, "usn", 0)) or {}
    # ⛔⛔ BUG ARREGLADO 2026-08-04 (lo cazó el usuario): acá estaba **`"exp": 20000` CLAVADO A MANO**,
    #   y 20000 son exactamente **nivel 5**. Es el MISMO número mágico del bug de las cuentas nuevas
    #   que se arregló el 2026-07-31 en `db_create_char` — había quedado vivo en el paquete de SALA.
    #   Síntoma: en el lobby y en "mi info" salías con tu nivel real (40, Luna), pero **adentro de la
    #   sala eras nivel 5**, porque el `occ0` del FF0C es la EXP del ocupante y el cliente deriva el
    #   nivel de ahí con la tabla de umbrales.
    #   ★ LECCIÓN: cuando un valor de prueba se clava "por ahora", queda. Buscar `20000` antes de
    #     jurar que un nivel viene mal de la DB.
    _exp = int(char.get("exp", 0) or 0)
    _cid = char.get("char_id", 0x0001FF54)
    # ★ NPC/FANTASMA (2026-07-11): identity=slot (≠ host) -> el me-detect falla -> avatar REMOTO.
    #   Les damos la exp del host para que se vean como pares (ya reusan su char y su ropa).
    #   ★★ 2026-08-05: SALTEAR los slots donde hay un JUGADOR DE VERDAD — si no, el NPC lo pisa.
    for i, sl in enumerate(slots_npc(st)):
        if sl in mesa:
            continue
        ocupantes.append({"char_id": _cid, "parts": char.get("parts", []), "nick": f"NPC{i+1}",
                          # ★ los NPC reusan el char del anfitrión, así que también les toca
                          #   `gacha.sexo` y no el último dígito (2026-09-09). Sexto sitio.
                          "identity": sl, "slot": sl, "exp": _exp, "gender": sexo(_cid),
                          "equipo": equipo_para_ff0c(st, sl)})
    return ocupantes

def enviar_userlist(st):
    # ★★★ YA TIENE LA SALA ENTERA (2026-09-23): desde acá recibe los avisos sueltos de la sala
    #   (`difundir_ocupante`); antes, no — le crearían gente con datos viejos que esta lista, al
    #   llegar después, ya no corrige (el cliente sólo aplica el FF0C al CREAR).
    #   ★ Va ACÁ y no en el handler del pedido: los jugadores la PIDEN (`h_20_ff0c`), pero a los
    #     ESPECTADORES se la manda el server al entrar, sin pedido — marcando en el handler, un
    #     espectador no habría vuelto a ver entrar a nadie.
    #   ⚠ ANTES de armar la lista, no después: si alguien entra mientras se arma, su aviso tiene que
    #     llegarle. Con la marca después, ese jugador quedaría INVISIBLE para éste.
    st.sala_poblada = getattr(st, "room_id", None)
    ocupantes = armar_ocupantes(st)
    sl = [s for s in slots_npc(st) if s not in mesa_de(getattr(st, "room_id", None) or -1)]
    if FF0C_LAYOUT_REAL:
        # ★ El REFERENTE manda UN PAQUETE POR OCUPANTE (k=1 el primero de la tanda, 2 el resto).
        for _i, _o in enumerate(ocupantes):
            # ★★★★★ 2026-09-01 — LA ROPA PROPIA **NO** VA EN TU PROPIO FF0C.
            #   Síntoma que lo destapó: las alas se ven en PRÁCTICA pero no en la sala multiplayer.
            #   Medido en el wire del REFERENTE, en DOS secuencias distintas (crear sala y entrar
            #   a una llena): la entrada del PROPIO jugador siempre llega con **itemcount=1, sólo el
            #   CUERPO** (99 B), mientras que las de los demás traen la lista completa de prendas.
            #     · al crear:  TunTunSahur slot 2 -> 1 ítem
            #     · al entrar: TunTunSahur slot 5 -> 1 ítem, y los otros 5 con 5/6/7 ítems
            #   ⇒ tu avatar en la sala lo dibuja el cliente con SUS datos locales (el MyRecord, que
            #     es el mismo camino que usa el modo práctica — y ahí las alas SÍ se ven). Al
            #     mandarte tu propia ropa en el FF0C lo obligábamos a RE-VESTIRTE por la vía de la
            #     sala, que aparentemente no aplica el aura/summon ⇒ se perdían las alas.
            _yo = (_o.get("usn") is not None and _o.get("usn") == getattr(st, "usn", None))
            # ★ (142) sin ropa, PERO con su Wing Id entero: el byte de arriba (flotar / montura) lo lee la dll de la
            #   ficha en sRoomUser::Init. Sin esto uno mismo no se veía flotando ni montado (intento 1, 30-oct).
            from .catalogo import wing_id_con_aura                        # noqa: PLC0415
            _oc = (dict(_o, parts=[], wid=wing_id_con_aura(_o.get("parts") or [], _o.get("usn")))
                   if (FF0C_YO_SIN_ROPA and _yo) else _o)
            st.send_ff55(0x0C, build_ff0c_2013_real(_oc, 1 if _i == 0 else 2),
                         name=f"FF0C ocupante slot={_oc.get('slot')} {_oc.get('nick')!r} "
                              + ("(YO: sólo el cuerpo, como el REFERENTE)" if _yo and FF0C_YO_SIN_ROPA
                                 else f"({len(_oc.get('parts') or [])} prendas + cuerpo)"))
        # ★★★★ Y LOS QUE MIRAN, EN SUS CASILLEROS 6..11 — 2026-09-08.
        #   ⛔ Reportado: *"al regresar a la sala 1 la lista de espectadores no se armó"*. Al
        #     volver de la carrera el cliente RECONSTRUYE la sala y vuelve a pedir la lista
        #     (`inner FF0C len=1 : 00`), y esta función le contestaba **sólo con los sentados** ⇒
        #     la sección de espectadores quedaba vacía aunque siguieran ahí.
        #   ⇒ La lista de la sala son los seis asientos **y** los casilleros de mirar. Es el mismo
        #     `FF0C`, que inserta por slot; lo único que cambia es de dónde sale el ocupante.
        #   ⚠ Import perezoso a propósito: `lobby_salas` importa este módulo, y traerlo arriba
        #     arma el ciclo. Mismo criterio que `traspasar_anfitrion_al_salir` en `lobby.py`.
        _rid_ul = getattr(st, "room_id", None)
        _esp_ul = []
        if _rid_ul is not None:
            try:
                from .lobby_salas import _ocupante_espectador
                for _ce_ul in espectadores_de(_rid_ul):
                    _oe = _ocupante_espectador(_ce_ul, incluir12=getattr(st, "slot_espectador", None) is not None
                                               or ESPECTADOR12_A_CORREDORES)   # ★ 17-oct (87): a los corredores también
                    if _oe is None:
                        continue
                    st.send_ff55(0x0C, build_ff0c_2013_real(_oe, 2),
                                 name=f"FF0C ESPECTADOR slot={_oe['slot']} {_oe['nick']!r}")
                    _esp_ul.append(_oe)
            except Exception as _e_ul:
                log("LOBBY", f"  ⚠ no pude reponer la lista de espectadores: {_e_ul!r}")
        log("LOBBY", f"  ★ FF0C (layout real) -> {len(ocupantes)} paquete(s): "
                     + ", ".join(f"slot {o['slot']}={o['nick']!r}" for o in ocupantes)
                     + (f"  ★ + {len(_esp_ul)} mirando: "
                        + ", ".join(f"slot {o['slot']}={o['nick']!r}" for o in _esp_ul)
                        if _esp_ul else "")
                     + f" · sala={_rid_ul} para usn={getattr(st, 'usn', None)}")   # ★ 16-oct: la lista no lo nombra a él
        # ★★ Y DETRÁS DE LA LISTA, EL "LISTO" DE LOS QUE YA LO ESTABAN — 2026-09-08.
        #   Va acá y no en los llamadores porque **el `FF0C` es el que borra la marca**: repintar la
        #   lista sin reponer el listo es lo que obligaba a la sala entera a apretar de nuevo cada
        #   vez que alguien entraba. Ver `enviar_listos`.
        enviar_listos(st, _rid_ul, motivo=" (detrás del FF0C)")
        return ocupantes
    st.send_ff55(0x0C, build_ff0c_2013(ocupantes),
                 name=f"FF0C USERLIST {len(ocupantes)} ocupante(s) (yo slot "
                      f"{getattr(st, 'room_slot', None) or HOST_SLOT}" +
                      (f" + NPC slots {sl}" if sl else "") + ")")
    log("LOBBY", f"  ★ FF0C -> {len(ocupantes)} ocupante(s): "
                 + ", ".join(f"slot {o['slot']}={o['nick']!r}" for o in ocupantes))
    return ocupantes

def enviar_listos(st, rid, motivo=""):
    r"""Le repinta a `st` el cartel **LISTO** de cada jugador que ya lo estaba.

    ⛔⛔ EL BUG QUE ESTO ARREGLA — reportado desde producción el 2026-09-08:
      *"el listo falla, y se les tiene que pedir que vuelvan a ponerse listos; cosa que no debería
      pasar"*. El usuario lo atribuyó a los clientes lentos; **es peor que eso: pasa siempre**.

      El `FF17` es un AVISO EN VIVO: cuando alguien aprieta listo se difunde `[slot][1]` y cada
      cliente pinta `occupant[slot].ready = 1`. Pero esa marca vive **en el ocupante del cliente**,
      y el `FF0C` **reconstruye la lista de ocupantes** — o sea que **cada vez que alguien entra o
      sale de la sala, a TODOS se les borra el LISTO de todos**, porque `difundir_userlist` les
      re-manda la lista entera.

      Y del lado del server el dato existía y no lo usaba nadie: `st.ready` se escribía en
      `h_22_ff17` y **no lo leía ninguna función**. Teníamos la información y no la repartíamos.

    ★ La prueba de que éste es el camino: para los NPC ya estaba hecho, en `enviar_ready_npcs`, con
      esta nota escrita al lado — *"hay que RE-mandarlo tras cada cambio de modo: el cliente rearma
      los slots y los NPC vuelven a 'no listo'"*. Lo mismo pasaba con los jugadores de verdad y a
      nadie se le ocurrió que también les tocaba.

    ⚠ Va DESPUÉS del `FF0C`, siempre: el cliente sólo puede marcar listo a un ocupante que ya tiene.
    """
    if rid is None:
        return 0
    _n = 0
    for _slot, _usn in sorted(mesa_de(rid).items()):
        _c = CONEXIONES.get(_usn)
        if _c is None or getattr(_c, "cerrado", False):
            continue
        if not getattr(_c, "ready", False):
            continue
        try:
            st.send_ff55(0x17, bytes([_slot & 0xFF, 1]),
                         name=f"FF17 READY repuesto (slot={_slot}){motivo}")
            _n += 1
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude reponer el FF17 del slot {_slot}: {e!r}")
    if _n:
        log("LOBBY", f"  ★ FF17 x{_n}: repuesto el LISTO de los que ya lo estaban{motivo}")
    return _n


def enviar_ready_npcs(st, motivo=""):
    """FF17 [slot][ready=1] por cada NPC. Hay que RE-mandarlo tras cada cambio de modo: el cliente
       rearma los slots y los NPC vuelven a 'no listo' (lo reporto el usuario).
       ★ Solo por los slots que siguen siendo NPC: los de jugadores reales mandan su propio FF17."""
    ocupados = mesa_de(getattr(st, "room_id", None) or -1)
    # ★ sólo los asientos de siempre (0..5): un FF17 por un asiento ≥ 6 (los NPC de la carrera grande, que la sala
    #   todavía dibuja como mirones) sacaba «No se puede participar en la carrera con el carácter que tiene 0
    #   energía» (anonimo03, 10-oct)
    #   ★ (10-oct) en la sala de 12 van TODOS los asientos de corredor (0..11): anonimo03, «el LISTO de los NPC del equipo
    #     azul no se ve». Si vuelve el cartel de «0 energía», la causa es la marca de mirón del cliente (MODO_6VS6 §12).
    _rid17 = getattr(st, "room_id", None)
    _tope17 = asientos_de_la_sala(_rid17) if _rid17 is not None else 6
    sl = [s for s in slots_npc(st) if s not in ocupados and s < _tope17]
    for s in sl:
        st.send_ff55(0x17, bytes([s & 0xFF, 1]), name=f"FF17 NPC READY (slot={s}){motivo}")
    if sl:
        log("LOBBY", f"  ★ FF17 -> NPC slots {sl} LISTOS{motivo}")


# ══════════════════════════════════════════════════════════════════════════════
# LUGARES DE CHARLA Y ALTA/BAJA DE SALAS
# Vivían en `lobby.py`, que ya tenía ocho temas adentro. Son estado de sala, que es
# exactamente lo que hace este módulo.
#
# Un "lugar" (Sala de Conversación, charla de círculo) NO es una sala de carrera: se
# crean todos al arrancar el server y viven hasta que se lo baje; entrar es UNIRSE a uno
# que ya existe, no crearlo.
# ══════════════════════════════════════════════════════════════════════════════
# ── TANDA 1 (medida en pantalla 2026-07-30) — CONFIRMADO ───────────────────────────────────────
#     A & 0x7FF = ★ Nº DE SALA (la columna "No.": salió 001/002/003)
#     E − F     = ★ JUGADORES ACTUALES      ·   G − 6 = ★ CAPACIDAD   (salió 3/8, 1/6, 6/8 exacto)
#     B bit0    = ★ SALA PRIVADA (candado)  ·   B bit1 = ★ PARTIDA EN CURSO ("Jugando" vs "Espera")
#   Sin cerrar: la columna MODO, la columna "Solo", y el "[2]/[3]" al lado de la ocupación.
#
# ── TANDA 2 — una fila por variable, todo lo demás en el mismo baseline ────────────────────────
def _sala(n, nombre, **kw):
    base = dict(roomid=n, nombre=nombre, A_alto=0, B=0x00, C=0, D=0, E=3, F=0, G=14,
                H=0, I=0, J=0, K=0, L=0, M=0, N=0, O=0)
    base.update(kw)
    return base
SALAS_DEMO = [
    _sala(900, "Sala de prueba", E=0, F=0, G=14, L=1,
          B=0x00, flags=MODE_VELOCIDAD),                 # 0x00 = velocidad + solo
    _sala(901, "Prueba EQUIPO",  E=0, F=0, G=14, L=1,
          B=0x10, flags=MODE_VELOCIDAD | MODE_EQUIPO),   # 0x10 = EQUIPO en byMode
]
# ⛔ SACADO EL 2026-09-09 — era `{id(socket): True}` y NO SE LIMPIABA NUNCA.
#   `id()` en Python es la DIRECCIÓN DE MEMORIA, y las direcciones se REUTILIZAN: al liberarse un
#   socket, el siguiente podía caer en la misma y heredar el `True` del anterior. Con eso un
#   re-login parecía un login normal, no se cerraba el socket del LoginServer, y el cliente se
#   quedaba con su bandera de "sesión de login abierta" prendida — que es la que le hace
#   DESCARTAR EN SILENCIO todos los clics del selector de canales.
#   ⇒ Ahora es una variable local de `lobby.handle_login`, que es donde vive el dato: una
#     conexión. Ver la nota larga allá. **No lo devuelvas a un diccionario global.**
_lugar_lock = threading.RLock()


def crear_lugares_persistentes():
    """Se llama UNA vez al arrancar. Las instancias existen desde entonces, con o sin gente."""
    with _lugar_lock:
        for tipo in TIPOS_LUGAR_CHARLA:
            for num in range(INSTANCIAS_LUGAR_N):
                LUGARES[(tipo, num)] = {"ocupantes": {}}
        # el número 965 y compañía son los que el cliente pide desde los botones por defecto
        for tipo, num in DESTINOS_HORNEADOS:
            LUGARES.setdefault((tipo, num), {"ocupantes": {}})
    return len(LUGARES)


def lugar_de(tipo, numero):
    """Devuelve la instancia, creándola si el cliente pide una que no teníamos (p.ej. una casa)."""
    with _lugar_lock:
        return LUGARES.setdefault((tipo, numero), {"ocupantes": {}})


def entrar_lugar(st, tipo, numero):
    """Sienta al jugador en la instancia. -> slot 0..39, o None si está llena."""
    lg = lugar_de(tipo, numero)
    with _lugar_lock:
        salir_de_lugar(st, _ya_bloqueado=True)          # nunca en dos lugares a la vez
        ocupados = set(lg["ocupantes"].values())
        slot = next((s for s in range(LUGAR_CAPACIDAD) if s not in ocupados), None)
        if slot is None:
            return None
        lg["ocupantes"][getattr(st, "usn", 0)] = slot
        st.lugar_clave = (tipo, numero)
        return slot


def salir_de_lugar(st, _ya_bloqueado=False):
    clave = getattr(st, "lugar_clave", None)
    if clave is None:
        return None
    ctx = _lugar_lock if not _ya_bloqueado else _NoOpLock()
    with ctx:
        lg = LUGARES.get(clave)
        if lg:
            lg["ocupantes"].pop(getattr(st, "usn", 0), None)
        st.lugar_clave = None
    return clave


def gente_en(tipo, numero):
    with _lugar_lock:
        lg = LUGARES.get((tipo, numero))
        return len(lg["ocupantes"]) if lg else 0

def nuevo_roomid():
    """Nº de sala LIBRE MAS CHICO. Va en 11 bits (`A & 0x7FF` del FF6E/FF11) ⇒ 1..2046.

    ⚠ Antes `room_id` estaba CLAVADO en 1 ⇒ los dos jugadores creaban "la sala 001" y se pisaban en
    `SALAS_VIVAS`. Se toma el menor libre (y no un contador que sube) para que, sin otras salas, la
    primera vuelva a ser la 001 — el CBT hizo el mismo cambio y por el mismo motivo.
    """
    with _mesa_lock:
        usados = set(SALAS_VIVAS) | {d["roomid"] for d in SALAS_DEMO}
        for rid in range(1, 0x7FF):
            if rid not in usados:
                return rid
    return 1

def olvidar_conexion(st):
    if CONEXIONES.get(getattr(st, "usn", None)) is st:
        CONEXIONES.pop(st.usn, None)

ULTIMO_OCUPANTE = {}                   # roomid -> {slot: usn del último que lo dejó}


def liberar_asiento(rid, slot, motivo=""):
    r"""Le manda a la sala el `FF0E` del ÚLTIMO que ocupó ese asiento, si ya no está en la sala.

    ⛔⛔ POR QUÉ EXISTE — el bug del **jugador invisible**, cerrado el 2026-09-08 con el disasm de
      los dos clientes (ver `documentacion/PENDIENTE_INVISIBLE_AL_ENTRAR.md` y el informe del
      agente):

      **El `FF0C` no actualiza: CREA si el asiento está libre, y si ya está ocupado se va sin hacer
      nada.** (`cRoom::OnRoomUser`, y el 2019 hace lo mismo.)

      ⇒ Si en la pantalla de alguien ese asiento quedó **sucio** —con un ocupante viejo que no se
      borró— el que llega después **no se dibuja NUNCA para esa persona**, y re-mandarle la lista
      **no lo arregla**: la vuelve a ignorar por el mismo motivo. Misma sala, mismo momento, unos
      lo ven y otros no, según qué tenga cada uno en su mapa.

      ⚠ Y lo único que libera un asiento en el cliente es el `FF0E`, que borra **POR NOMBRE**. O
        sea que no alcanza con "limpiar el asiento": hay que saber **qué nombre** cree el cliente
        que está ahí. Por eso `levantar_jugador` e `intercambiar_asientos` anotan en
        `ULTIMO_OCUPANTE` quién dejó cada asiento.

    ★ ES UN CINTURÓN, no un arreglo de una causa: no sabemos POR QUÉ un cliente se queda con un
      asiento sucio (se perdió un `FF0E`, quedó de una carrera, un camino que no lo manda…). Esto
      hace que **no importe**: antes de sentar a alguien nuevo se manda el `FF0E` del anterior. Si
      el cliente ya lo había borrado, el paquete no hace nada; si no, le libera la silla.

    ⚠⚠ EL GUARD QUE NO SE PUEDE SACAR: sólo se manda si el anterior **ya NO está en la mesa**. Si
      esa persona sigue en la sala en OTRO asiento (un intercambio, o pasó de mirar a jugar), el
      `FF0E` la borraría de donde está ahora — el borrado es por nombre y no distingue asiento.
    """
    if rid is None or slot is None:
        return 0
    _antes = (ULTIMO_OCUPANTE.get(rid) or {}).get(slot)
    if _antes is None:
        return 0
    if _antes in set(mesa_de(rid).values()):
        return 0                                  # sigue en la sala, en otro asiento: NO tocarlo
    nick = str((db_get_char(_antes) or {}).get("nick", "") or "")
    crudo = nick.encode("cp1252", "replace")[:NICK_MAX_FF0E]
    if not crudo:
        return 0
    _n = 0
    for _c in conexiones_en_sala(rid):
        try:
            _c.send_ff55(0x0E, bytes([len(crudo)]) + crudo,
                         name=f"FF0E liberar el asiento {slot} (estaba {nick!r})")
            _n += 1
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude liberar el asiento {slot}: {e!r}")
    if _n:
        log("LOBBY", f"  ★★ ASIENTO {slot} LIBERADO en la sala {rid}: FF0E de {nick!r} a {_n} "
                     f"cliente(s) — el que no lo hubiera borrado se quedaba sin ver al que "
                     f"entra{motivo}")
    return _n


def difundir_salida(rid, st):
    """Avisa a los que quedan que este jugador SE FUE, con el FF0E (quitar ocupante POR NOMBRE).

    ⛔⛔⛔ CORRECCIÓN IMPORTANTE — 2026-09-08, medida en LOS DOS binarios.
      Acá decía: *"El `FF0C` INSERTA (handler `0x5E89C0` -> `0x5A0530` AddOccupant: **upsert** por
      slot sobre el `std::map` de `sala+0x9c`)"*. **Las direcciones son de otro build** (`0x5E89C0`
      cae en medio del bucle del handler real) **y la palabra `upsert` es falsa.**

      Lo que hace de verdad `cRoom::OnRoomUser` (`0x59FDF0`, ranura `+0x28` de la vtable):
      **CREA SI EL ASIENTO ESTÁ LIBRE, y si ya está ocupado SE VA SIN HACER NADA.** Hace `find(slot)`
      sobre el map de `cRoom+0x9C` y, si lo encuentra, retorna. El 2019 sin optimizar hace exactamente
      lo mismo (`0x00A27980`, el contenedor en `this+0x5C8`).

      ★★ Y LA DIFERENCIA NO ES ACADÉMICA, es LA CAUSA DE UN BUG ABIERTO: con un *upsert*, re-mandar
      la lista repara cualquier desajuste y nadie puede quedar mal dibujado. Con *create-if-absent*,
      **un asiento sucio es un agujero PERMANENTE para ese cliente** — y sólo para ése, porque el que
      entró después armó la escena de cero con el map vacío. Misma sala, mismo momento, unos lo ven
      y otros no. Ver `documentacion/PENDIENTE_INVISIBLE_AL_ENTRAR.md`.

      ⇒ **Re-mandar el `FF0C` NO ARREGLA NADA si el asiento ya está tomado en ese cliente.** Lo
        único que libera un asiento es el `FF0E` de acá abajo.

    ★★★ MEDIDO en NUESTRO cliente 2013 (2026-08-05, disasm) — esta parte sigue en pie:
      · **No hay clear en todo el camino** ⇒ re-mandar el FF0C con un ocupante menos NO saca a nadie
        de la pantalla. Verificado también en vivo: el host se quedó mirando al NPC aunque le llegó
        la lista nueva.
      · `FF0E` (handler `0x5CD860` -> `0x5A5930` RemoveOccupantByName) SÍ lo saca. Payload:
            [nameLen:u8][nombre]      ← sin NUL en el cable, el cliente lo agrega
        Resuelve nombre->slot con `0x4EC2C0` y lo borra del map y de los vectores de render.
      · ⚠⚠ **`nameLen` TIENE que ser ≤ 15**: el buffer local es de 16 bytes y NO valida; con 16 o más
        el NUL que agrega el cliente pisa la cookie de stack y lo MATA en `0x74F216`. Por eso el
        recorte de abajo NO es cosmético.
    """
    nick = str((db_get_char(getattr(st, "usn", 0)) or {}).get("nick", "") or "")
    crudo = nick.encode("cp1252", "replace")[:NICK_MAX_FF0E]
    if not crudo:
        log("LOBBY", "  ⚠ FF0E: el que se va no tiene nick -> no puedo sacarlo de la pantalla del resto")
        return
    if len(nick.encode("cp1252", "replace")) > NICK_MAX_FF0E:
        log("LOBBY", f"  ⚠ FF0E: nick {nick!r} recortado a {crudo!r} (el cliente crashea con 16+)")
    payload = bytes([len(crudo)]) + crudo
    # ★★ Y TAMBIÉN A LOS QUE MIRAN — 2026-09-08. Recorría `mesa_de` = los SENTADOS, así que el que
    #   se iba (jugador o espectador) **le quedaba de fantasma en la pantalla al espectador**.
    #   Reportado: *"el que crasheó no salió de la lista de espectadores de todos los jugadores"*.
    #   Es la misma familia que el chat, el modo y el arranque: si se difunde a la sala, se difunde
    #   a los que la miran (ver `conexiones_en_sala`).
    _corre = any(getattr(CONEXIONES.get(_u), "en_carrera", False) for _u in mesa_de(rid).values())
    _doce = asientos_de_la_sala(rid) == 12
    _guardados = 0
    for otro in conexiones_en_sala(rid):
        usn = getattr(otro, "usn", None)
        if otro is None or otro is st or getattr(otro, "cerrado", False):
            continue
        # ★★ 16-oct: en plena carrera de equipos el `FF0E` MATA a los que quedan (ver
        #   `FF0E_EN_CARRERA_ESPERA`). Se le guarda y va cuando vuelve a la sala. Al que mira
        #   también: mira la misma carrera.
        # ★★ 17-oct: salvo al que trae la dll que lo saca bien de la pista (grande.c, gr_abandono: el exe sólo sacaba
        #   los asientos < 6). A ése le va YA, y el que se fue no le queda de fantasma corriendo hasta el final.
        # ⛔ 17-oct: «sala de 12», NO «por equipos»: el exe se saltea a los asientos ≥ 6, que sólo corren en la de 12, y
        #   en prod cayeron también las de 12 «todos contra todos» y «6 contra 6» (25 de 26 racimos del 16/17-oct).
        if FF0E_EN_CARRERA_ESPERA and usn not in DLL_ABANDONO and _doce and (
                getattr(otro, "en_carrera", False)
                or (_corre and getattr(otro, "slot_espectador", None) is not None)):
            _pend = getattr(otro, "ff0e_pendientes", None) or []
            if crudo not in _pend:
                _pend.append(crudo)
            otro.ff0e_pendientes = _pend
            _guardados += 1
            continue
        try:
            otro.send_ff55(0x0E, payload, name=f"FF0E quitar ocupante {crudo.decode('cp1252')!r}")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandarle el FF0E a usn={usn}: {e!r}")
    if _guardados:
        log("LOBBY", f"  ★★ FF0E de {crudo.decode('cp1252')!r} GUARDADO para {_guardados} que están en carrera "
                     f"en la sala {rid} (de 12, sin la dll nueva: el FF0E en carrera los tumba) -> va cuando vuelvan")


def soltar_ff0e_pendientes(st):
    """Le manda a `st` los `FF0E` que se le guardaron mientras corría (ver `difundir_salida`).

    Se llama cuando vuelve a la sala (su `FF13`). Al que mira, cuando ya nadie corre. Se saltea el
    que haya vuelto a entrar mientras tanto: el `FF0E` borra POR NOMBRE y lo sacaría de nuevo.
    """
    _pend = getattr(st, "ff0e_pendientes", None)
    if not _pend or getattr(st, "cerrado", False) or getattr(st, "en_carrera", False):
        return 0
    rid = getattr(st, "room_id", None)
    if getattr(st, "slot_espectador", None) is not None and any(
            getattr(CONEXIONES.get(_u), "en_carrera", False) for _u in mesa_de(rid).values()):
        return 0
    st.ff0e_pendientes = []
    _presentes = set()
    for _c in conexiones_en_sala(rid):
        _nk = str((db_get_char(getattr(_c, "usn", 0)) or {}).get("nick", "") or "")
        _presentes.add(_nk.encode("cp1252", "replace")[:NICK_MAX_FF0E])
    _n = 0
    for crudo in _pend:
        if crudo in _presentes:
            continue
        try:
            st.send_ff55(0x0E, bytes([len(crudo)]) + crudo,
                         name=f"FF0E quitar ocupante {crudo.decode('cp1252')!r} (guardado de la carrera)")
            _n += 1
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandarle el FF0E guardado a usn={getattr(st, 'usn', None)}: {e!r}")
    if _n:
        log("LOBBY", f"  ★★ {_n} FF0E guardado(s) de la carrera soltados a usn={getattr(st, 'usn', None)} (volvió a la sala)")
    return _n


def equipo_por_defecto(slot):
    """Reparto POR ASIENTO: equipo 1 = asientos 0,1,2 · equipo 2 = asientos 3,4,5.

    ★★ QUÉ COLOR ES CADA UNO — corregido el 2026-09-05 mirando una captura de pantalla con la
    sala llena en relevo: **equipo 1 = AZUL** (asientos 0-2) y **equipo 2 = ROJO** (3-5).
    ⛔ Acá decía lo contrario ("rojo = 1 · azul = 2"), y estaba anotado como *inferido* de ver al
    host —que se sienta en el 2— salir rojo. Era una inferencia sobre una sola muestra, y de las
    que se ven a simple vista en cuanto hay seis jugadores. Los NÚMEROS que mandamos nunca
    estuvieron mal; lo que estaba mal era el nombre del color en el comentario.

    ⚠⚠ ESTO ES UNA POLÍTICA NUESTRA, NO UNA LEY DEL JUEGO. Hay dos capas y conviene no confundirlas:
      · El applier del FF4B (`0x5971F0`) **sí** tiene esta tabla CABLEADA (medido: bloque `0x597324`
        para equipo/coop y `0x5972DA` para solo). Es lo que aplica el cliente solo al cambiar de modo.
      · Pero `0x5938F0(cRoom, slot, equipo)` acepta **cualquier equipo en cualquier asiento**, y el
        `0x99` deja que lo decida el SERVER. Es decir: el reparto por asiento es el default, no un
        límite.
    ⏳ El usuario recuerda —sin afirmarlo— que en el juego original **cualquiera podía elegir su
      color** (podían quedar 6 rojos), y que la partida no arrancaba hasta emparejar. Eso encaja con
      esta arquitectura. Cuando se implemente el botón de cambiar de equipo, el equipo elegido se
      guarda en `EQUIPOS[rid][slot]` y esta función queda sólo como valor inicial.
    ⚠ Que 1 sea rojo y 2 azul es INFERIDO de lo visto en pantalla (el host, en el slot 2, sale rojo).
    """
    return 1 if slot < 3 else 2


def equipo_de(rid, slot):
    """El equipo VIGENTE de un asiento: el que fijó el server, o el default por asiento.

    ★ La sala de 12 (6vs6, 10-oct): asientos 0..5 = equipo 1 y 6..11 = equipo 2 (la regla del coreano: «asiento < N/2»).
      Con el default de 6 (0..2 / 3..5) los 12 quedaban 3 contra 9 y el guard del START (`0x592B50`, equipos parejos)
      sacaba «El juego comenzará cuando hayan suficientes usuarios» (anonimo03, 10-oct). El equipo 1 es el aro ROJO y el
      2 el AZUL (visto en la sala de 12): coincide con las tarjetas (fila de arriba roja, la de abajo azul)."""
    with _mesa_lock:
        n = GRANDE_SALA.get(rid, 0)
        if n == 12 and (rid in RELEVO12 or rid in CUATRO12):   # ★ 14-oct: 4 equipos en lugares FIJOS (★ 15-oct: y equipo)
            return slot // 3 + 1 if 0 <= slot < 12 else 1
        por_defecto = (1 if slot < n // 2 else 2) if n else equipo_por_defecto(slot)
        return EQUIPOS.get(rid, {}).get(slot, por_defecto)


def lado_del_equipo(rid, equipo):
    """Los asientos de un equipo, del más cercano al centro al más lejano (el orden en que se ocupan).

    Sala normal: rojo (1) = 2, 1, 0 · azul (2) = 3, 4, 5. ★ Sala de 12 (10-oct): rojo = la fila de arriba 0..5 y azul =
    la de abajo 6..11, cada uno en el orden de `ORDEN_ASIENTOS_12`. ⛔ anonimo03 tocó «Elija Equipo» en la sala de 12 y el
    server lo mudaba con la regla de 6: pedía azul y caía en el 5 (rojo), y terminó en el 0."""
    n = asientos_de_la_sala(rid)
    if n == 12 and es_cuatro12(rid):                # ★ 14-oct: 4 equipos (relevo, ★ 15-oct y equipo): los 3 lugares fijos
        e = min(max(int(equipo), 1), RELEVO12_EQUIPOS)
        return (3 * (e - 1), 3 * (e - 1) + 1, 3 * (e - 1) + 2)
    if n == 12:
        return tuple(s for s in ORDEN_ASIENTOS_12 if (s < 6) == (equipo == 1))
    return (2, 1, 0) if equipo == 1 else (3, 4, 5)


def poner_equipo(rid, slot, equipo):
    """Fija el equipo de un asiento (para cuando exista el botón de cambiar de color)."""
    with _mesa_lock:
        EQUIPOS.setdefault(rid, {})[slot] = equipo & 0xFF


def capitanes_de(rid):
    """`{equipo: slot}` de los capitanes vigentes de una sala. `{}` si no se sortearon."""
    with _mesa_lock:
        return dict(CAPITANES.get(rid) or {})


def sortear_capitanes(rid):
    """Sortea UN capitán por equipo entre los asientos ocupados. Devuelve `{equipo: slot}`.

    ★ El sorteo es del SERVER, y eso no es una decisión nuestra: el `FF175` (`CmdChangeCaptain`,
      handler `0x5DFC50`) llega S→C con **los dos capitanes en un solo paquete**, y el cliente no
      tiene ninguna vía de elegirlos solo. El usuario lo describe igual: *"se selecciona
      aleatoriamente en cada equipo un capitán"*.

    ⚠ Devuelve sólo los equipos que TIENEN gente. El que llama decide si eso alcanza para
      arrancar (ver `jefe_puede_arrancar`): un equipo sin capitán es el `0xFF` que crashea.
    """
    _mesa = mesa_de(rid)
    _por_equipo = {}
    for _s in sorted(_mesa):
        _por_equipo.setdefault(equipo_de(rid, _s), []).append(_s)
    _caps = {_eq: random.choice(_sl) for _eq, _sl in _por_equipo.items()
             if _eq in (1, 2) and _sl}
    # ★ SE ANOTA ENTRE QUIÉNES SE SORTEÓ, no sólo quién salió — 2026-09-08.
    #   Reportado: *"el jefe no cambió en el equipo rojo, ¿casualidad?"*. Con el log de antes no se
    #   podía contestar: decía el ganador pero no cuántos competían, así que "salió siempre el
    #   mismo" y "era el único candidato" se veían EXACTAMENTE IGUAL. Un sorteo entre uno no es un
    #   sorteo, y esa diferencia es la que decide si hay bug o hubo suerte.
    log("LOBBY", f"  ★ SORTEO de capitanes de la sala {rid}: "
                 + " · ".join(f"equipo {_eq} entre {_sl} -> {_caps.get(_eq)}"
                              for _eq, _sl in sorted(_por_equipo.items()) if _eq in (1, 2)))
    with _mesa_lock:
        CAPITANES[rid] = dict(_caps)
    return _caps


TODOS_LOS_SLOTS = 0x3F                 # 6 asientos (0..5), todos abiertos


def espectadores_de(rid):
    """Las conexiones que están MIRANDO esa sala (entraron con el flag del `FF11`)."""
    if rid is None:
        return []
    return [c for c in list(CONEXIONES.values())
            if getattr(c, "room_id", None) == rid
            and getattr(c, "slot_espectador", None) is not None
            and not getattr(c, "cerrado", False)]


def difundir_espectadores(rid, motivo=""):
    """Manda el `FFBB` con cuántos están mirando **a los que miran**, y refresca la fila del lobby.

    El `FFBB` (`CmdUpdateMassObservers`, handler `0x5D7EC0`) lee un `u32` y con > 0 hace
    `[cRoom+0xC1C] = 1`: **prende la sección de espectadores**. Se lo mandábamos SÓLO al que
    entraba a mirar, así que los demás nunca se enteraban de que la sección tenía que existir —
    ni de que alguien se había ido.

    ⏳ Con 0 espectadores mandamos 0. **Que eso APAGUE la sección está sin medir**: el handler
      sólo tiene la rama de "> 0 -> prender". Si al irse el último el cartel queda abierto, ésta
      es la línea, y el camino es buscar el paquete que la apaga.

    ⛔⛔⛔ Y ACÁ ESTÁ EL BUG QUE ESTA FUNCIÓN CAUSÓ — leer antes de tocar (2026-09-08, 01:30).
      La primera versión mandaba el `FFBB` a **toda la sala**, sentados incluidos. Media hora
      después el usuario reportó, con la sala en 2 jugadores y los dos listos:

          *"al poner listo sale ese popup: **No puede iniciar el juego solo en Multi juego**,
            como si no reconociera que jugador21 está listo o no estuviera ahí"*

      El `FFBB` hace `[cRoom+0xC1C] = 1` en el cliente que lo recibe: le dice *"esta sala está
      en modo espectadores"*. Se lo estábamos diciendo **a los que están jugando**, y encima
      **no se apaga nunca** (el handler sólo tiene la rama de "> 0 -> prender"). El síntoma
      aparece después de que alguien entre a mirar y siga ahí aunque se vaya.
      ⇒ Vuelve a ir **sólo a los que miran**, que es como estuvo mientras andaba. La bandera es
        de la vista del espectador, no del estado de la sala.
    """
    if rid is None:
        return 0
    _n = len(espectadores_de(rid))
    _dest = conexiones_en_sala(rid) if FFBB_A_TODA_LA_SALA else espectadores_de(rid)
    for _c in _dest:
        try:
            _c.send_ff55(0xBB, struct.pack("<I", _n), name=f"FFBB espectadores={_n}")
        except Exception as e:
            log("LOBBY", f"  ⚠ no pude mandar el FFBB: {e!r}")
    actualizar_ocupantes_sala(rid)
    # ★ Y la fila del lobby, que es donde se ve el corchete `[N]`. El cliente NO re-pide la lista
    #   solo: sin este empujón el contador se queda con la foto vieja hasta que el jugador toque
    #   una pestaña. Reportado: *"el contador de espectadores aún no aparece en la lista de salas"*.
    try:
        difundir_roomlist()
    except Exception as e:
        log("LOBBY", f"  ⚠ no pude empujar la lista de salas: {e!r}")
    log("LOBBY", f"  ★ ESPECTADORES de la sala {rid}: {_n} "
                 f"(FFBB a {len(_dest)}){motivo}")
    return _n


def conexiones_en_sala(rid):
    """TODOS los de la sala: los sentados **y los que miran**.

    ⛔ EL BUG QUE ARREGLA (2026-09-08): *"no reciben el cambio de modo ni tampoco el chat"*. Todas
      las difusiones recorrían `mesa_de(rid)`, que son sólo los SENTADOS — y un espectador no está
      sentado. Quedaba mirando una sala muda: sin chat, sin cambios de modo, sin nada.
    ⇒ Lo que se difunde a la sala se difunde a los que la miran. Para eso están mirando.
    """
    if rid is None:
        return []
    fuera = []
    for u in mesa_de(rid).values():
        c = CONEXIONES.get(u)
        if c is not None and not getattr(c, "cerrado", False):
            fuera.append(c)
    return fuera + espectadores_de(rid)


def slots_cerrados(rid):
    """El conjunto de asientos que el anfitrión cerró. Vacío si no cerró ninguno."""
    if rid is None:
        return set()
    with _mesa_lock:
        return set(SLOTS_CERRADOS.get(rid) or ())


def mascara_abiertos(rid):
    """El `open_mask` del `FF13`: bit en 1 = asiento ABIERTO.

    ⚠ Un asiento OCUPADO nunca se informa cerrado, aunque esté en la lista: el cliente dibuja al
      jugador a partir del `FF0C` y un asiento cerrado con alguien adentro es un estado que no
      existe. Cerrar sólo debe impedir que ENTREN, no borrar al que ya está.
    """
    m = TODOS_LOS_SLOTS
    ocupados = set(mesa_de(rid)) if rid is not None else set()
    for s in slots_cerrados(rid):
        if 0 <= s <= 5 and s not in ocupados:
            m &= ~(1 << s)
    return m & TODOS_LOS_SLOTS


def cerrar_slot(rid, slot, cerrar=True):
    """Cierra (o abre) un asiento. Devuelve `(cerrados, cambio)`.

    ⚠ NO se puede cerrar un asiento OCUPADO: sería echar a alguien por la puerta de atrás, y el
      `FF87` no es el comando de expulsar (ése es el `FF20`, que además le avisa al que se va).
    """
    if rid is None or not (0 <= slot <= 5):
        return slots_cerrados(rid), False
    if cerrar and mesa_de(rid).get(slot) is not None:
        return slots_cerrados(rid), False
    with _mesa_lock:
        s = set(SLOTS_CERRADOS.get(rid) or ())
        antes = set(s)
        s.add(slot) if cerrar else s.discard(slot)
        SLOTS_CERRADOS[rid] = s
        return set(s), s != antes


def slot_disponible(rid, slot):
    """`True` si alguien puede sentarse ahí: ni ocupado, ni cerrado, ni con NPC."""
    if rid is None:
        return True
    return (slot not in slots_cerrados(rid)
            and mesa_de(rid).get(slot) is None
            and slot not in set(npcs_de(rid)))


def reparar_capitanes(rid):
    """Deja UN capitán válido en cada equipo que tenga gente. Devuelve `(caps, cambio)`.

    ⛔ EL BUG QUE ARREGLA (2026-09-07), reportado por el usuario: *"al pasar el jefe del equipo
      azul al rojo, el equipo azul se quedó sin jefe: no se lo cedió a otro miembro"*. Y tenía
      razón en lo que agregó — *"esto puede pasar a la inversa también"*: es simétrico, y además
      pasa por TRES caminos distintos, no sólo cambiando de equipo:

          · el capitán se pasa al otro equipo   (`FF18`)
          · el capitán se va de la sala          (`FF12`, o lo echan con el `FF20`)
          · se pierde su conexión

      Es el mismo error que ya se pagó con el ANFITRIÓN: un puesto que queda vacío y nadie hereda.

    ⚠ Y no es cosmético. Un equipo sin capitán es el `0xFF` que devuelve `FindCaptain`, y el
      cliente lo usa como índice de un vector de 6 -> `c0000005` **a todos los de la sala**. Ver
      `jefe_puede_arrancar`.

    ★ Sólo toca lo que está roto: si el capitán de un equipo sigue sentado y sigue siendo de ese
      equipo, NO se lo cambia. Así el distintivo no salta por la pantalla, que es la razón por la
      que el sorteo no se rehace en cada movimiento.
    """
    if rid is None:
        return {}, False
    mesa = mesa_de(rid)
    por_eq = {}
    for s in sorted(mesa):
        por_eq.setdefault(equipo_de(rid, s), []).append(s)
    with _mesa_lock:
        caps = dict(CAPITANES.get(rid) or {})
        cambio = False
        for eq in (1, 2):
            gente = por_eq.get(eq) or []
            actual = caps.get(eq)
            if not gente:
                if actual is not None:              # equipo vacío: no puede tener capitán
                    caps.pop(eq, None)
                    cambio = True
                continue
            if actual in gente:
                continue                            # sigue sentado y sigue siendo de este equipo
            caps[eq] = random.choice(gente)
            cambio = True
        if cambio:
            CAPITANES[rid] = dict(caps)
        return dict(caps), cambio


def poner_capitan(rid, equipo, slot):
    """Le pasa la capitanía de `equipo` al asiento `slot`. Devuelve `{equipo: slot}` o `None`.

    ★ Es lo que pide el `FF175` que manda el CLIENTE: cada capitán tiene en pantalla la opción de
      cederle el puesto a un compañero. Rechaza si el asiento está vacío o si no es de ese equipo
      — un capitán de un equipo al que no pertenece deja al suyo sin capitán, y un equipo sin
      capitán es el `0xFF` que crashea a todos (ver `jefe_puede_arrancar`).
    """
    if rid is None:
        return None
    if mesa_de(rid).get(slot) is None or equipo_de(rid, slot) != equipo:
        return None
    with _mesa_lock:
        c = dict(CAPITANES.get(rid) or {})
        c[equipo] = slot
        CAPITANES[rid] = c
        return dict(c)


def marcar_sorteo_al_volver(rid):
    """Anota que esta sala re-sortea capitanes **cuando vuelvan de la carrera**.

    Se llama al arrancar (`FF24`). No sortea nada acá: si se sorteara al arrancar, se pisaría la
    cesión del `FF175` — que es exactamente el bug que esto arregla (ver `SORTEO_AL_VOLVER`).
    """
    if rid is None:
        return False
    with _mesa_lock:
        SORTEO_AL_VOLVER.add(rid)
    return True


def tomar_sorteo_al_volver(rid):
    """¿Le toca sortear a esta sala? Devuelve `True` **una sola vez** y borra la marca.

    ⚠ Es de un solo uso a propósito: el `FF13` de "volví a la sala" lo manda CADA jugador, y sin
      esto el sorteo se rehace una vez por cada uno — el distintivo saltando por la pantalla, que
      es justo lo que se viene evitando desde el 2026-09-07.
    """
    if rid is None:
        return False
    with _mesa_lock:
        if rid not in SORTEO_AL_VOLVER:
            return False
        SORTEO_AL_VOLVER.discard(rid)
        return True


def olvidar_sorteo_al_volver(rid):
    """Borra la marca sin sortear. Para cuando la sala deja el modo jefe o se muere."""
    with _mesa_lock:
        SORTEO_AL_VOLVER.discard(rid)


def hay_capitanes(rid):
    """`True` si los dos equipos ya tienen capitán sorteado."""
    c = capitanes_de(rid)
    return len(c) >= 2 and all(v is not None for v in c.values())


def sala_usa_capitanes(rid):
    """¿Esta sala tiene capitanes? **Sólo el modo JEFE los usa.**

    ⛔⛔ EL BUG QUE ESTO ARREGLA — 2026-09-08, encontrado en el log de PRODUCCIÓN.
      Reportado con dos capturas de la misma sala: *"la sala es solo + velocidad pero los demás se
      pintan como si fuera equipo"* y *"alguien no se dibuja al entrar"*. El log, en el segundo
      exacto de las capturas (12:15:49, sala 2):

          ★ FF13 … flags=0x01 = solo + velocidad · jefe=0        ← la sala NO es de jefe
          ★★★ CAPITANES de la sala 2: equipo 1 -> slot 1 · equipo 2 -> slot 5
              [25 FF37 a 5 cliente(s)] (se fue usn=7956, era capitán)

      **25 `FF37` con equipo 1 y 2, de golpe, en una sala SOLO.** Y no es un caso raro: de las 88
      difusiones de capitanes del día, **80 las disparó alguien al IRSE**.

      La causa: `CAPITANES[rid]` **sobrevive al cambio de modo** (sólo se borraba al morir la
      sala), así que una sala que pasó por jefe y volvió a solo se queda con capitanes guardados —
      y `traspasar_anfitrion_al_salir` los repara y difunde **en todos los modos**.

    ⇒ Y el `FF37` no es inocuo: pinta el color de equipo del asiento, y con `equipo != 0` sigue
      hasta `0x5AFFD0(posición del asiento)`, un efecto que **nunca mapeamos** y que ya estaba
      anotado en `enviar_equipos` como *"el sospechoso si al entrar alguien aparece algo raro en
      los asientos"*. Las dos capturas son eso.
    """
    s = SALAS_VIVAS.get(rid) or {}
    return bool(s.get("boss", False))


def olvidar_capitanes(rid):
    """Borra los capitanes de una sala. Se llama al DEJAR el modo jefe.

    ★ Son un dato **del modo**, no de la sala: fuera del jefe no significan nada, y guardarlos es
      lo que hacía que se difundieran donde no correspondía (ver `sala_usa_capitanes`).
    """
    with _mesa_lock:
        habia = bool(CAPITANES.pop(rid, None))
        SORTEO_AL_VOLVER.discard(rid)      # y el sorteo pendiente, que era del modo jefe
    if habia:
        log("LOBBY", f"  ★ la sala {rid} deja el modo jefe: se olvidan sus capitanes")
    return habia


def enviar_ff37(st, slot, equipo, capitan):
    """`FF37` — "el asiento `slot` es del equipo `equipo` y (no) es el capitán". 4 bytes.

    ★ Es el paquete que hace **las dos cosas de una vez**, y por eso se prefiere al `FF175`.
      Layout leído del handler `0x5CE8B0` (cuatro `read(1)` seguidos):

          @0 = EQUIPO   ·   @1 = slot A   ·   @2 = slot B   ·   @3 = BANDERA DE CAPITÁN

          005ce8fe  cmp  @1, @2                 ; si son DISTINTOS…
          005ce90a  call 0x5A0590(@1, @2)       ; …INTERCAMBIA los dos asientos ⚠
          005ce923  call 0x592D90(@2, @0, @3)   ; y después aplica equipo+capitán al slot @2

      Y `0x592D90` hace exactamente las tres escrituras que hacen falta:
          00592e77  mov byte [asiento+0x157], bl   ; el equipo del ASIENTO (lo que se ve)
          00592e9e  mov byte [asiento+0x158], al   ; la bandera de capitán del asiento
          00592eab  call 0x4EC8F0                  ; ★ y el PADRÓN: sRoomUser +0x4A y +0x4B

    ⚠⚠ **`@1` y `@2` van IGUALES a propósito.** Con slots distintos el cliente los intercambia de
       asiento antes de aplicar nada. Mandar `[eq, S, S, f]` es la forma de decir "sólo aplicá".
    """
    st.send_ff55(0x37, bytes([equipo & 0xFF, slot & 0xFF, slot & 0xFF, 1 if capitan else 0]),
                 name=f"FF37 slot {slot} -> equipo {equipo}"
                      + (" ★CAPITÁN" if capitan else ""))


def difundir_capitanes(rid, caps, motivo=""):
    """Manda a TODA la sala el `FF37` de cada asiento ocupado, con su equipo y su capitanía.

    Va a todos y no sólo al anfitrión porque el padrón es de cada cliente: si uno no se entera de
    quién es el capitán, su `FindCaptain` devuelve `0xFF` y **ese** cliente es el que se cae.

    ★★★★ Y "TODOS" INCLUYE A LOS QUE MIRAN — 2026-09-08, y esto es EL CANDIDATO Nº1 DEL CRASH.
      ⛔ Reportado el mismo día: *"el cliente cargó la escena fija correcta, pero crashea"* y
        *"modo capitán: los espectadores ven quién es capitán, pero los que están en los slots de
        juego no"*. Los espectadores no recibían NINGÚN `FF37`, así que su padrón quedaba vacío —
        y la frase de arriba, que está escrita acá desde el 2026-09-07, dice exactamente qué pasa
        con un cliente cuyo `FindCaptain` no encuentra capitán: **se cae**.
      ⇒ El espectador mira la misma sala: necesita el mismo padrón. No es un extra, es el guard.
      ⏳ Si con esto el crash sigue, lo próximo a mirar es si el cliente acepta un `FF37` estando
        en modo espectador (podría rechazarlo por no tener asiento propio).
    """
    _mesa = mesa_de(rid)
    _dest = [CONEXIONES.get(u) for u in _mesa.values()]
    _dest = [c for c in _dest if c is not None and not getattr(c, "cerrado", False)]
    _dest = _dest + [c for c in espectadores_de(rid) if c not in _dest]
    _n = 0
    for _s in sorted(_mesa):
        _eq = equipo_de(rid, _s)
        _cap = (caps.get(_eq) == _s)
        for _c in _dest:
            try:
                enviar_ff37(_c, _s, _eq, _cap)
                _n += 1
            except Exception as e:
                log("LOBBY", f"  ⚠ no pude mandar el FF37 del slot {_s}: {e!r}")
    log("LOBBY", f"  ★★★ CAPITANES de la sala {rid}: "
                 + " · ".join(f"equipo {e} -> slot {s}" for e, s in sorted(caps.items()))
                 + f"  [{_n} FF37 a {len(_dest)} cliente(s)]{motivo}")
    return _n


def enviar_equipos(st, rid):
    """★★★★ Pinta el equipo de CADA asiento con el `0x99`, en vez de re-aplicar el modo entero.

    ANTES: cada vez que entraba alguien le mandábamos a todos un `FF4B` de más, sólo para que el
    applier `0x5971F0` corriera y repartiera equipos. Andaba, pero era un martillazo: re-aplicaba el
    modo de sala completo para pintar un asiento. (El usuario lo notó: *"¿lo estás forzando?"*.)

    El `0x99` es el paquete nativo de EVENTO DE ASIENTO (el cliente lo loguea como `Observe : Change`).
    Layout S->C, **5 bytes, todos u8** (medido en `0x5E5050`):
        [tipo][slotA][slotB][auxiliar][equipo]
    y lo clave: la asignación de equipo `0x5938F0(cRoom, slotB, equipo)` corre **FUERA del switch**,
    con la única condición de que el equipo **no** sea `0xFF`. Los valores neutros:
        equipo = 0xFF -> no se asigna nada        ·  slotA = 0xFF -> no se toca ese otro asiento
    ⇒ `[0x00][0xFF][slot][0xFF][equipo]` asigna el equipo a UN asiento y lo repinta (`0x595770`),
      sin intercambiar nada: con `slotA = 0xFF` el intercambiador sale en su primer `find`.

    ⚠ En modo SOLO no se pinta: los colores son otra paleta y tocarlos la estropea (misma regla que
      el CBT con su FF37).
    ⚠ SIN ACOTAR: en todos los caminos corre además `0x5B5F70(cRoom+0x10ECC, ...)`, que es UI y no se
      mapeó. Si aparece algún efecto raro al entrar alguien, ése es el primer sospechoso.
    """
    # ★★★ EL RELEVO TAMBIÉN ES POR EQUIPOS, aunque no traiga el bit de equipo puesto.
    #   El decoder del cliente (`0x46BBF0`) mira el bit de relevo ANTES que el de equipo:
    #   `byMode & 0x80 -> CooperationMode = 2`, y ese 2 gana sobre el `0x10` del equipo. O sea que
    #   en relevo el `room_mode` NO tiene `MODE_EQUIPO`, y con la compuerta vieja los asientos se
    #   quedaban sin pintar. El CBT pasó por lo mismo y lo describió como *"se veían 5 rojos y 1
    #   azul"*.
    # ★★★ 2026-09-07 — Y EL JEFE TAMBIÉN, por la misma razón elevada al cuadrado: su modo no viaja
    #   en el byMode sino en la cola del `FF13` (`+44`), así que `room_mode` no trae NINGÚN bit de
    #   equipo y esta compuerta lo dejaba afuera entero. La regla ahora es la del propio cliente
    #   (`0x58BFF0`), no una lista de bits nuestra. Ver `sala_por_equipos`.
    if not sala_por_equipos(st):
        return 0
    # ★★★★★ 2026-09-07 — HAY **DOS** LUGARES DONDE VIVE EL EQUIPO, Y HASTA HOY LLENÁBAMOS UNO.
    #
    #   El `FF99` escribe `[asiento+0x157]` = el COLOR que se ve en la grilla de la sala. Andaba, y
    #   por eso nunca se notó. Pero el cliente tiene además el **padrón** (`[0x931660]`), con el
    #   equipo de cada jugador en `sRoomUser+0x4A`, y **ésa** es la copia que consultan las
    #   decisiones. `0x4EC970` (GetTeam) devuelve ese byte y tiene **78 llamadores**.
    #
    #   ⛔⛔ Y el síntoma que lo destapó (2026-09-07, 6 jugadores, todos listos, modo jefe): el
    #      cartel *"El juego comenzará cuando hayan suficientes usuarios"* con la sala llena y
    #      3 contra 3 en pantalla. **El START ni siquiera salió del cliente** — no hay un solo
    #      `FF24` en el log. Lo cortó su propio guard `0x592B50`, cuyo bucle final es:
    #
    #          00592c46  call 0x58BFF0          ; ¿la sala es por equipos? (sí en jefe)
    #          00592c6d  call 0x4EC970(slot)    ; ★ GetTeam DEL PADRÓN, no del asiento
    #          00592c72  cmp al,1 / jne         ;   equipo 1 -> un contador · el resto -> otro
    #          00592ccd  cmp bl,[esp+0x13]      ; ★ ¿los dos contadores son IGUALES?
    #          00592cd9  and eax,3              ;   no -> devuelve 3 -> texto 74
    #
    #      Con el padrón en cero: 0 del equipo 1 contra 6 del "resto" ⇒ "equipos disparejos".
    #      El color de la pantalla decía 3v3 y el padrón decía 0v6. Dos estructuras, una llena.
    #
    #   ★★★ Y AL PADRÓN NO SE LLEGA POR EL `FF0C`. Buscados los xrefs de `0x4EC8F0` (el ÚNICO
    #      escritor de `+0x4A`/`+0x4B`): son **siete**, y el handler del `FF0C` (`0x5E82A0`) no
    #      está entre ellos — ni llama a `0x4EC8F0` ni escribe `+0x4A` por su cuenta. Los caminos
    #      que sirven son dos: el **`FF37`** (`0x592D90`) y el **`FF175`** (`0x5958A0`).
    #
    #   ⚠ Por eso el `FF37` va ACÁ y no en el START: el guard corre **client-side, antes** de que
    #     el `FF24` salga. Mandarlo al arrancar llega tarde — el cliente ya dijo que no.
    #   ⚠ El `FF37` hace las dos cosas (asiento y padrón), así que el `FF99` queda redundante. Se
    #     deja igual: es el que está probado en pantalla desde agosto y no cuesta nada. Si alguna
    #     vez molesta, el que se saca es el `FF99`, no el `FF37`.
    #   ⚠ SIN ACOTAR: el `FF37` tiene un efecto de más. Con la sala por equipos y `equipo != 0`,
    #     `0x592D90` sigue hasta `0x5AFFD0(posición del asiento)` -> `0x4B06C0`. No se mapeó qué
    #     dibuja o suena. Si al entrar alguien aparece un efecto repetido en los seis asientos,
    #     **el sospechoso es éste** y se apaga con `EQUIPO_AL_PADRON = False`.
    n = 0
    _caps_eq = capitanes_de(rid)
    for slot in sorted(mesa_de(rid)):
        _eq = equipo_de(rid, slot)
        st.send_ff55(0x99, bytes([0x00, 0xFF, slot & 0xFF, 0xFF, _eq & 0xFF]),
                     name=f"FF99 asiento {slot} -> equipo {_eq}")
        if EQUIPO_AL_PADRON:
            # La capitanía se REESPETA, no se pisa: si ya hay un capitán sorteado, este FF37 no
            # se lo baja (mandar 0 acá sería borrarlo cada vez que alguien entra a la sala).
            enviar_ff37(st, slot, _eq, _caps_eq.get(_eq) == slot)
        n += 1
    if n:
        log("LOBBY", f"  ★ FF99 x{n}: equipos pintados asiento por asiento (sin re-aplicar el modo)"
                     + (f" · ★ FF37 x{n}: y el EQUIPO al PADRÓN (+0x4A), que es de donde lo lee "
                        f"el guard del START" if EQUIPO_AL_PADRON else ""))
    return n

def buscar_sala(rid):
    """Sala publicada por su Nº (las vivas primero, después los maniquíes)."""
    s = SALAS_VIVAS.get(rid)
    if s is not None:
        return s
    return next((d for d in SALAS_DEMO if d["roomid"] == rid), None)

def salas_publicadas(canal=None):
    """Lo que se manda en el FF6E: las salas vivas + (opcional) los maniquíes y las de mentira.

    ★★ `canal` = la clave del canal del que PIDE (`st.canal`: 'all', 'sun', 'rookie'…). Cada
    canal es un PUERTO propio, así que "en qué canal está esta sala" es "por qué puerto entró el
    que la creó". Sin este filtro, la sala creada en Libre aparecía en la lista de **todos** los
    canales, y al entrar desde otro canal el cliente quedaba en una sala que no era de ahí.

    ⚠ Las salas SIN canal anotado (los maniquíes de `SALAS_DEMO` y cualquier sala que viniera de
      antes de esto) se muestran en todos lados **a propósito**: son de prueba y no tienen dueño
      ni puerto. Si algún día molestan, se les pone `canal` y caen solas en el filtro.
    """
    out = [dict(s) for s in SALAS_VIVAS.values()]
    if SALAS_POR_CANAL and canal is not None:
        out = [s for s in out if s.get("canal") in (None, canal)]
    if MOSTRAR_SALAS_DEMO:
        out += [dict(s) for s in SALAS_DEMO]
    out += salas_falsas()
    _marcar_campana_en_la_lista(out)
    _marcar_canal_en_la_lista(out)
    return out


def _marcar_canal_en_la_lista(filas):
    """`L` de cada fila del `FF6E`: **el ícono de licencia de la sala**, al lado del número.

    ★★★★★ MEDIDO EN VIVO CON ANONIMO03 (2026-09-17): con `L=3` aparece una estrella amarilla pegada
      al «No.» de la sala. Es el ícono que pidió: *"debería salir al lado de «No.» número"*.

    ★★ Y EL VALOR ES **LA BANDA QUE ELIGIÓ EL ANFITRIÓN**, no el canal donde se creó la sala. Lo
      dijo anonimo03 al verlo: *"el ícono comparte el valor con la selección de banda o canal que
      define qué músicas se pueden poner: así si el master lo tiene seleccionado en sol, afuera
      sale el icono de sol en X sala"*. O sea que es el mismo dato del diálogo «Selección del
      Canal» de adentro de la sala, el que ya guarda `DIFICULTAD_SALA` y viaja en el `FF13`.
      ⇒ El dato ya existía: `dificultad_de(rid)`. Sólo faltaba publicarlo en la lista.

    ⛔⛔ Y ACÁ VA EL ERROR QUE COSTÓ DOS CORRIDAS, escrito para no repetirlo: las dos primeras
      pruebas usaron **el código del canal donde se creó la sala**, y anonimo03 estaba en el canal
      **Libre**, cuyo código es **0** ⇒ se le mandó el mismo cero que ya iba y las dos veces «no
      salió el ícono» no probaron nada. ★ Cuando el valor de prueba se DERIVA de algo, hay que
      comprobar que en el caso de prueba no valga justo el neutro.

    ⚠⚠ EL MISMO BYTE FILTRA. `0x49E44D` lo pasa por `0x484A00(L, mi_licencia)` y si da 0 el
      cliente **esconde la sala de la lista**:
          if (L == 0)  return 1          ; sin banda elegida: la ve cualquiera
          if (mi == 8) return (L == 8)   ;
          if (L == 8)  return 1          ;
          return (mi >= L)
      ⇒ Una sala en banda alta se le esconde a quien tiene licencia baja. **Eso NO es lo que
        anonimo03 quiere**: *"para que sigamos permitiendo que cualquier persona entre a X sala de X
        licencia"*. ⏳ Si molesta en la práctica, el arreglo es un parche que haga
        `0x484A00` devolver siempre 1 — el ícono se sigue dibujando y el filtro desaparece.
        Ése es el orden que pidió él: *"primero hacer funcionar el icono y de ahí recién
        parchamos"*.
    """
    # ★★★★★ 2026-09-17 — PRENDIDO, y ya no esconde nada: al cliente se le sube su propia licencia
    #   a 6 en el login (`LICENCIA_CLIENTE_AL_TOPE`) ⇒ `0x484A00` deja pasar todo `L <= 6`.
    #   ⚠ Y por eso hay tope: `L = 7` seguiría siendo invisible para TODOS, así que esa banda se
    #     publica en 0 — se ve, sin ícono. Ver `FF6E_CANAL_TOPE` en `ajustes.py`.
    if not FF6E_CANAL_EN_LA_LISTA:
        return
    for s in filas:
        try:
            if s.get("L"):
                continue
            _b = dificultad_de(s.get("roomid"))
            if not _b:
                continue
            _b = int(_b)
            if 1 <= _b <= int(FF6E_CANAL_TOPE):
                s["L"] = _b & 0xFF
            elif _b == 8:
                s["L"] = 8                    # el comodín «sin licencia»: lo ve cualquiera, sin ícono
            else:
                # ⛔ banda por encima de lo que el cliente puede ver: se manda 0 a propósito.
                #    Esconderla sería peor que dejarla sin dibujo.
                log("SALAS", f"  ⚠ sala {s.get('roomid')}: banda {_b} > tope {FF6E_CANAL_TOPE} "
                             f"-> se publica sin ícono para que NO se esconda")
        except Exception:
            pass


def _marcar_campana_en_la_lista(filas):
    """`J` y `K` de cada fila del `FF6E`: **el itemcode de la campana que está sonando** ahí.

    ★★★ MEDIDO EN EL CORPUS DEL REFERENTE (2026-09-17) — 27 capturas MITM, 1124 paquetes `FF6E`
      parseados sin un solo fallo, 10.656 filas de sala. `J` y `K` toman **sólo** los seis
      itemcodes de `CAMPANAS`, partidos por metal y sin un cruce:

          J   0=9815  181=465  183=253  774=123      <- todos de ORO
          K   0=8399  304=1441 775=521  297=295      <- todos de PLATA

    ★★ Y no es correlación, es CAUSA. En `mitm_20260907_183811.txt`, 18:40:25:

          TX FFAA GoldenBellNotifer : sala 4, itemcode 0xB5 = 181 (oro)
            FF6E de ANTES   -> sala 4:  J = 0     K = 304
            FF6E de DESPUÉS -> sala 4:  J = 181   K = 304

      Suena el oro en la sala 4 ⇒ el `J` de esa fila pasa de 0 a 181, y el `K` (la plata que ya
      estaba sonando) no se mueve. Misma sala, mismo itemcode, mismo paquete.

    ⇒ **No es un flag de sí/no: es el itemcode.** Distingue la base de la «+» (181 vs 183,
      297 vs 304), así que la lista puede decir CUÁL campana suena, no sólo que hay una.
    ★ El ciclo de vida sale gratis: `_PENDIENTE` ya se limpia en `pagar_campana()`, así que la
      marca se apaga sola cuando la campana deja de estar activa.
    ⏳ `L` (el canal de licencia que exige la sala) es el otro campo que hoy va en 0 y que el
      referente sí usa. Va aparte y con cuidado: `0x484A00` **esconde de la lista** las salas que
      piden más licencia que la tuya, así que un `L` de más deja salas invisibles.
    """
    try:
        from .lobby_campana import campana_pendiente
    except Exception:
        return
    for s in filas:
        try:
            _rid = s.get("roomid")
            for _clave, _metal in (("J", "oro"), ("K", "plata")):
                _p = campana_pendiente(_rid, _metal)
                if _p:
                    s[_clave] = int(_p.get("canon", 0) or 0)
        except Exception:
            pass
# ★ SALAS DE MENTIRA — para probar LAS PESTAÑAS DE PÁGINA sin abrir 13 clientes.
#   No es una sonda de protocolo: son entradas normales de la lista, con el mismo layout que las
#   de verdad. Se prenden y apagan en vivo con `.salas N` desde el chat.
#   ⚠ Sus roomid arrancan en 800 para no chocar con `nuevo_roomid()` (que reparte del 1 en adelante)
#     ni con los maniquíes (900, 901). Y NO se puede entrar a ellas: no existen en `SALAS_VIVAS`,
#     así que el `FF11` contesta "sala inexistente" — que es lo correcto para una sala inventada.
SALAS_FALSAS_N = SALAS_FALSAS_PAGINACION

def poner_salas_falsas(n):
    global SALAS_FALSAS_N
    SALAS_FALSAS_N = max(0, min(int(n), 200))
    return SALAS_FALSAS_N

def n_salas_falsas():
    """Getter, no la variable. `from .salas import SALAS_FALSAS_N` se lleva una COPIA del número
    y se queda con el valor del arranque para siempre — el clásico de rebindear un global."""
    return SALAS_FALSAS_N

def salas_falsas():
    return [_sala(800 + i, f"Paginacion {i + 1:02d}", E=1, F=0, G=FF6E_CAPACIDAD,
                  B=0x00, flags=MODE_VELOCIDAD)
            for i in range(SALAS_FALSAS_N)]


def paginar_salas(salas, pagina):
    """Corta la lista en la página pedida. Devuelve `(las_de_esta_pagina, total_de_paginas)`.

    ★★★ El total de páginas es **el primer byte de la respuesta** — con >1 el cliente dibuja la
    barra de pestañas (`0x5E0850: cmp cl,1 / jbe`). Ver la nota larga en `ajustes.py`.
    ⚠ `total` es 0 cuando no hay salas: así el byte queda en 0, que es lo que el server de
      referencia manda con la lista vacía (12 muestras) y lo que veníamos mandando.
    """
    por = max(1, FF6E_SALAS_POR_PAGINA)
    total = (len(salas) + por - 1) // por
    if not salas:
        return [], 0
    pagina = max(0, min(int(pagina), total - 1))     # si piden una página que no existe, la última
    return salas[pagina * por: pagina * por + por], total

def _codigo_de_licencia(st):
    """El código de licencia del jugador (1..8), para el campo `L` de la entrada de sala.

    Se importa acá adentro a propósito: `salas` está por debajo de `progresion` en la cadena
    de módulos y traerlo arriba crearía un import circular con `basedatos`.
    """
    try:
        from .progresion import codigo_cliente, licencia_actual, nivel_de_exp
        from .basedatos import db_get_char
        usn = getattr(st, "usn", 0)
        nivel = nivel_de_exp(int((db_get_char(usn) or {}).get("exp", 0) or 0))
        return codigo_cliente(nivel, licencia_actual(usn)[2]) & 0xFF
    except Exception:
        return 1                       # novato: un código válido, nunca 0


def difundir_roomlist(tipo=1):
    """Manda la lista de salas a todos los que están en el lobby (sin sala).

    El cliente NO re-pide la lista solo: si nadie se la empuja, se queda con la foto vieja.

    ⚠⚠ EL CUERPO YA NO ES UNO SOLO PARA TODOS. Antes se armaba una vez y se repartía; con la
      lista por canal, el de Libre y el de Sol tienen que recibir cosas distintas. Se arma por
      destinatario, igual que el `FF13` (que también cambia por jugador, por la banda del picker).

    ⛔⛔⛔ ACÁ DECÍA: *"siempre se empuja la página 0 … si el jugador estaba mirando la página 3,
      **la re-pide él solo** al tocar la pestaña"*. Esa última frase era una SUPOSICIÓN mía, nunca
      medida, y es falsa. El bug que causó, reportado por anonimo03 el 12-sep:

          *"si estoy en página 2, pasan un par de segundos y me muestra la lista de la página 1"*

    ★ POR QUÉ EL CLIENTE NO SE PUEDE DEFENDER (su handler del FF6E, `0x5E0800`):
          005e08de  call 0x4A17A0   ; guarda la página actual en +0x16F0
          005e08e9  call 0x4A05A0   ; y **pone la página en 0x28**, el centinela "ninguna"
          005e08f8  mov [roomMgr+0x16FE], dl     ; el total de páginas
      La respuesta **no dice de qué página es**. El cliente dibuja lo que le llegue y se olvida de
      dónde estaba ⇒ está hecho para que el server le mande siempre la página que pidió.

    ★★ Y POR QUÉ APARECIÓ RECIÉN AHORA, si esto es de hace nueve días: hacen falta **más de 12
      salas** para que el cliente dibuje las pestañas (`0x5E0850: cmp cl,1 / jbe`). Medido en el
      log de prod, a la misma hora del día:

          antes del 12-sep:   55-78 jugadores -> 7-12 salas -> pestañas el **19%** del tiempo
          después:           92-142 jugadores -> 14-27 salas -> pestañas el **97%** del tiempo

      La proporción salas/jugador no se movió (0,15 antes y después): **no se rompió nada, cruzamos
      un umbral**. El bug estaba desde `e6232ac` (03-sep), tapado por el tamaño de la lista.
      ⇒ Queda anotado porque es una clase de bug, no un caso: los que esperan a que el server
        crezca no se encuentran leyendo el diff del día.

    ⇒ Ahora se le manda a cada uno **su** página (`st.salas_pag`, la del último `FF6E` suyo). El
      que nunca pidió nada sigue recibiendo la 0, que es lo correcto para él.
    """
    try:
        from .paquetes import build_ff6e_roomlist
    except Exception:
        return
    # ⛔ ACÁ SALTEABA A LOS QUE ESTABAN DENTRO DE UNA SALA, razonando que "no miran la lista".
    #   Era una suposición mía, sin medir, y está MAL: en la captura, 2 de los 9 `FF6E`
    #   empujados sin pedido llegaron con el jugador ADENTRO de una sala.
    #   ⛔ Y ACÁ ME EQUIVOQUÉ EN EL MOTIVO (corregido 2026-09-04). Puse que el empuje arreglaba
    #      además el modo del que crea, "porque el ROOMTYPE `[[0x9314ac]+0x1951]` se copia del
    #      byte +0x34 de la entrada de la lista". **Esa entrada es la de la lista de CANALES, no
    #      la de salas**: `0x4A7940` copia `+0x34` (tier2 del canal) a `+0x1951` y `+0x36` a
    #      `[roommgr+0x1328]` (canal seleccionado), y el gate `0x49F980` compara `+0x1951` contra
    #      5, que es una CATEGORÍA DE CANAL. Leí una lista por la otra.
    #      El modo del que crea viaja por el **@8 del FF13** (medido sobre 101 FF13 del corpus,
    #      ver `build_ff13_2013`). Lo de arriba —empujar la lista también a los que están dentro—
    #      igual está medido y sigue siendo correcto; lo falso era la explicación de más.
    from .ajustes import FF6E_EMPUJE_SIN_VACIOS
    n = 0
    _callados = 0            # ★ 26-oct: los de un canal sin salas que NO tenían salas dibujadas (sin lista vacía)
    _por_canal = {}          # canal -> (todas_las_salas, total_de_paginas)   [para el log]
    _cache = {}              # (canal, pagina_ya_acotada) -> (cuerpo, cuantas_trae)
    _paginas_usadas = {}     # pagina mostrada -> a cuantos   [para el log]
    for c in list(CONEXIONES.values()):
        if getattr(c, "cerrado", False):
            continue
        _canal = getattr(c, "canal", None)
        if _canal not in _por_canal:
            _todas = salas_publicadas(_canal)
            _por_canal[_canal] = (_todas, paginar_salas(_todas, 0)[1])
        _todas, _tot = _por_canal[_canal]
        # ★ SU página, no la 0. `paginar_salas` ya acota sola la que no existe (si cerraron salas
        #   y la 3 dejó de haber, le cae la última) — o sea exactamente lo que recibiría si la
        #   pidiera él. Se acota ACÁ ADEMÁS para que la caché no guarde dos veces lo mismo.
        # ⚠ `FF6E_EMPUJE_RESPETA_PAGINA` es el interruptor para volver al comportamiento viejo sin
        #   tocar código, por si esto destapara algo en vivo.
        _quiere = int(getattr(c, "salas_pag", 0) or 0) if FF6E_EMPUJE_RESPETA_PAGINA else 0
        _suya = max(0, min(_quiere, _tot - 1)) if _tot else 0
        _clave = (_canal, _suya)
        if _clave not in _cache:
            _pag, _ = paginar_salas(_todas, _suya)
            _cache[_clave] = (bytes([0, 0, 0]) if not _pag
                              else build_ff6e_roomlist(_pag, paginas=_tot), len(_pag))
        _cuerpo, _n_pag = _cache[_clave]
        # ★★ 26-oct (anonimo03: el popup «No hay salas disponibles» al entrar, sólo en prod): una lista VACÍA saca el popup
        #   303 encima de la isla. Sólo se le manda a quien tenía salas dibujadas (si no, se queda viendo una que ya no
        #   existe); al que nunca tuvo, nada. Ver `FF6E_EMPUJE_SIN_VACIOS` en ajustes.py.
        if not _n_pag and FF6E_EMPUJE_SIN_VACIOS and not getattr(c, "lista_con_salas", False):
            _callados += 1
            continue
        c.lista_con_salas = bool(_n_pag)
        try:
            # ★ 29-sep (optimización para el VPS, `BANCO_VPS.md` §5): SIN una línea de log por
            #   destinatario. Con 300 conectados eran el 34 % de TODAS las líneas del log (la misma
            #   frase repetida a cada uno, 2-3 veces por segundo), y la línea de abajo ya dice a
            #   cuántos, a qué página y de qué canal. Se cuenta en el resumen de cada minuto.
            c.send_ff55(0x6E, _cuerpo, name=RESUMIR)
            n += 1
            _paginas_usadas[_suya + 1] = _paginas_usadas.get(_suya + 1, 0) + 1
        except Exception:
            pass
    if n or _callados:
        # ★ El log dice A QUÉ PÁGINA fue cada uno. Sin eso, este arreglo es invisible en el log y
        #   la próxima vez habría que volver a medirlo desde cero. Ver [[una-medicion-vence]].
        _rep = " · ".join(f"pág {k}→{v}" for k, v in sorted(_paginas_usadas.items()))
        log("SALA", f"  ★ lista de salas empujada a {n} jugador(es) [{_rep}]"
                    + (f" (y a {_callados} de canales sin salas, nada: sin el popup 303)" if _callados else "") + ": "
                    + " · ".join(f"{k or 'sin canal'}={len(v[0])} sala(s) en {v[1]} pág"
                                 for k, v in sorted(_por_canal.items(), key=lambda kv: str(kv[0]))))


def registrar_sala(st):
    """Publica en la lista la sala que acaba de crear/modificar este cliente."""
    rid = getattr(st, "room_id", None)
    if not rid:
        return
    modo  = getattr(st, "room_mode", 0)
    colab = bool(getattr(st, "room_colab", False))
    # ★ Cuenta REAL: los jugadores sentados en la mesa + los NPC que queden en slots libres.
    _mesa = mesa_de(rid)
    ocupantes = max(1, len(_mesa)) + len([s for s in slots_npc(st) if s not in _mesa])
    SALAS_VIVAS[rid] = _sala(
        rid, getattr(st, "room_name", "sala"),
        # ★★★ EL MODO DE LA SALA VIAJA ACÁ, Y CON LOS FLAGS CRUDOS DEL CLIENTE (2026-09-03).
        #   ⛔ Acá se traducía el modo a la codificación del **byMode** (`0x04 item · 0x10 equipo
        #      · 0x80 relevo`), que es la del `FF4B`. La entrada de sala NO usa esa: usa los
        #      **flags tal como los manda el cliente en el `FF10`** (`0x01 velocidad · 0x02
        #      equipo · 0x10 relevo`). Son dos codificaciones distintas para lo mismo, igual que
        #      pasó con los `type` del `FF10E` y los del `bonus.xml`.
        #   El choque era peligroso, no sólo inútil: nuestro `0x10` de *equipo* se lee como
        #   **relevo** en la codificación buena.
        #
        #   MEDIDO en la captura del 2026-09-02 (`mitm_20260902_162549`): el `B` de las salas
        #   ajenas toma los valores `0x00 · 0x01 · 0x02 · 0x03 · 0x12`, que son exactamente
        #   combinaciones de los flags del cliente (`0x12` = relevo+equipo). Con la codificación
        #   que mandábamos, los valores posibles eran `0x00 · 0x04 · 0x10 · 0x14 · 0x80 · 0x94`:
        #   ni uno solo aparece en el corpus.
        #
        #   ⛔⛔ Y ME EQUIVOQUÉ: probé a mandar `B = modo & 0xFF` (los flags crudos) porque en la
        #      captura los valores de `B` eran `0x00 0x01 0x02 0x03 0x12`, que también se leen
        #      como combinaciones de flags. **Es una coincidencia de bits**, y la medición EN
        #      PANTALLA de la TANDA 4 (arriba en este mismo archivo) ya tenía la respuesta:
        #
        #          bit0 0x01 = 🔒 PRIVADA   ·   bit1 0x02 = EN JUEGO
        #          bit2 0x04 = ÍTEM  ·  bit4 0x10 = EQUIPO  ·  bit7 0x80 = RELEVOS
        #
        #      Cruzado contra la captura: los **1723** registros encajan con esa tabla, 6 de 6
        #      combinaciones sin una sola excepción (`privada=True en-curso=True -> B=0x03`,
        #      `en-curso=True + equipo -> B=0x12`, etc.). Con los flags crudos, una sala de
        #      **velocidad** (`0x01`) se habría listado como **PRIVADA**.
        #
        #   ★ Lo que sí faltaba, y se agrega ahora: los bits **privada** y **en juego**, que
        #     nunca mandábamos. Por eso ninguna sala nuestra mostraba el candado ni el "Jugando".
        # ★★ EN COOPERATIVO LOS BITS DE MODO VAN EN CERO (2026-09-03). El modo de una sala
        #   colaborativa NO viene en los flags —viene por la cola del `FF10`, en `room_colab`—
        #   así que `modo` no trae el bit de velocidad y la cuenta de abajo prendía el de
        #   **ítem**. Síntoma exacto que reportó el usuario: creaba en colaboración y al otro
        #   le aparecía **"item + solo"**.
        #   MEDIDO: en la captura, las **790** entradas con `M=1` (cooperativo) tienen `B` con
        #   los bits de ítem y equipo **siempre en cero** — sólo varían privada y "en juego".
        #   El cartel de "Modo Cooperativo" lo pone `M`, no `B`.
        B=((0 if (colab or (modo & MODE_VELOCIDAD)) else 0x04) |  # ítem = "no velocidad"
           (0 if colab else (0x10 if (modo & MODE_EQUIPO) else 0)) |   # equipo
           (0 if colab else (0x80 if (modo & MODE_RELEVO) else 0)) |   # relevos
           (0x01 if CLAVE_SALA.get(rid) else 0) |   # ★ candado (29-sep: de la SALA, no del `st`)
           (0x02 if getattr(st, "room_en_juego", False) else 0)),  # ★ "Jugando"
        # ★ `G` estaba escrito literal como `6 + 8` = 14, sin que nadie supiera por qué. La grilla
        #   muestra la capacidad como **8** cuando la sala tiene **6** asientos (el loop del FF13 es
        #   fijo de 6, medido) — que el valor sea 6+8 y la pantalla diga 8 es demasiada coincidencia.
        #   ⏳ PRUEBA EN CURSO: si con 6 la grilla pasa a "1/6", G ERA la capacidad.
        # ★ la sala de 12 (6vs6, 10-oct): G = capacidad + 6 ⇒ «x/12» en la lista
        E=ocupantes, F=0, G=(asientos_de_la_sala(rid) + 6) if grande_de(rid) else FF6E_CAPACIDAD,
        # ⛔ REVERTIDO 2026-09-03. Puse acá el CÓDIGO DE LICENCIA del creador, razonando que
        #   en la captura `L` nunca vale 0 y toma `1·3·4·5·6·7`, que es el espacio de códigos de
        #   nuestra tabla de canales. El razonamiento sobre el conjunto de valores sigue en pie,
        #   PERO la medición en pantalla de la TANDA 2 (arriba en este archivo) dice otra cosa
        #   sobre para qué lo usa la grilla:
        #
        #       (L=1, M=1) -> "Modo Cooperativo"
        #
        #   Y el síntoma encaja: con `L` variable, el usuario vio el cartel de cooperativo
        #   **una vez bien, la siguiente mal y la tercera bien**. Un valor que cambia entre
        #   salas explica exactamente esa intermitencia; el código de licencia cambia al subir
        #   de nivel, y desde hoy la exp se persiste, así que se mueve.
        #   ⚠ Las tandas 2 y 3 se contradicen: la 3 dice que `L` "no dibuja nada". Hasta que se
        #     mida de nuevo, gana la que explica el síntoma observado.
        L=1 if colab else 0,
        M=1 if getattr(st, "room_colab", False) else 0,
        O=1 if getattr(st, "room_boss",  False) else 0,
        flags=modo,                                       # interno: para reponerlo al ENTRAR (FF11)
        colab=colab,
        boss=bool(getattr(st, "room_boss", False)),
        # ★★ EL CANAL DE LA SALA = el del que la creó. Cada canal es un puerto propio, así que
        #   `st.canal` (que sale de `CANAL_POR_PUERTO`) es el dato, no una etiqueta aparte.
        #   Sin esto, la sala hecha en Libre se listaba en los 10 canales.
        canal=getattr(st, "canal", None),
    )
    # ★★★★ Y LOS QUE MIRAN, QUE ESTA FUNCIÓN ACABA DE BORRAR — 2026-09-08.
    #   ⛔ EL BUG, encontrado por `pruebas/humo_prod.py` en su primera corrida con la sala llena:
    #     esto **reconstruye la fila entera desde cero** con `E = los sentados` y `F = 0`, y no se
    #     llama sólo al crear la sala: **también en cada cambio de MODO** (`h_25_ff4b`). O sea que
    #     el anfitrión cambiaba el modo y el contador de espectadores de la lista de salas se
    #     ponía en cero, con seis personas mirando.
    #   ⇒ El recuento vive en UN solo lugar (`actualizar_ocupantes_sala`, que sabe la regla
    #     `E = sentados + mirando · F = mirando`). Se lo llama acá en vez de repetir la cuenta:
    #     dos copias de la misma regla es exactamente cómo se llegó a este bug.
    actualizar_ocupantes_sala(rid)
    log("LOBBY", f"  ★★ MATCHER: sala {rid} {getattr(st,'room_name','sala')!r} PUBLICADA "
                 f"({ocupantes} ocupante/s) — total en lista: {len(SALAS_VIVAS)}")
    # ★★★ EMPUJAR LA LISTA A LOS QUE MIRAN EL LOBBY (2026-09-03).
    #   Síntoma que lo destapó: el que crea cambia el modo de la sala y **el que está mirando
    #   la lista no se entera** — sigue viendo lo de antes hasta que pide la lista de nuevo.
    #   MEDIDO: el server de referencia MANDA el `FF6E` sin que se lo pidan. En la captura,
    #   31 respuestas contra 17 pedidos, y 9 de ellas sin ningún pedido cerca.
    #   Se manda sólo a los que NO están en una sala: al de adentro no le sirve y es ruido.
    difundir_roomlist()

def marcar_en_juego(rid, jugando):
    """Prende o apaga el **"Jugando"** de la sala en la lista del lobby (bit `0x02` del campo `B`).

    ★★ Es la mitad PREVENTIVA del arreglo de "entrar a mitad de carrera" (2026-09-06). El rechazo
    del `FF11` evita el daño; esto evita el clic: sin este bit, una sala en plena partida se ve
    igual que una esperando, y la gente entra porque no tiene cómo saberlo.

    ⚠ El bit estaba previsto desde julio (`bit1 0x02 = EN JUEGO ("Jugando")`, medido en pantalla,
      ver la TANDA 4 arriba) y `registrar_sala` lo leía de `st.room_en_juego`… que **no lo escribía
      nadie**. O sea que el campo existía, el cliente lo dibujaba, y siempre valía 0.
    """
    s = SALAS_VIVAS.get(rid)
    if s is None:
        return False
    antes = s.get("B", 0)
    s["B"] = (antes | 0x02) if jugando else (antes & ~0x02)
    if s["B"] != antes:
        log("SALA", f"  ★ sala {rid}: {'EN JUEGO' if jugando else 'vuelve a esperar'} "
                    f"(B 0x{antes:02X} -> 0x{s['B']:02X})")
        difundir_roomlist()
    return s["B"] != antes


def actualizar_ocupantes_sala(rid):
    """Refresca el contador de gente que muestra la lista del lobby (campo E del FF6E)."""
    s = SALAS_VIVAS.get(rid)
    if s is None:
        return
    # ★★★★ EL CORCHETE DE LA FILA **ES EL CONTADOR DE ESPECTADORES** — 2026-09-08.
    #   ⛔ Reportado: *"en la lista de salas, antes, había un contador parecido al de usuarios
    #     dentro — la cantidad de slots de observador. Ese contador ahora no aparece"*.
    #   No hacía falta medir nada nuevo: la regla ya estaba escrita arriba, del 2026-07-30, y
    #   nunca la habíamos podido usar porque hasta ayer no existían los espectadores:
    #       "E = ocupantes TOTALES · F = los del corchete · los que se muestran JUGANDO son E−F"
    #   Poníamos `E = los sentados` y `F` nunca se tocaba (quedaba en 0) ⇒ el corchete mostraba
    #   [0] y el cliente lo esconde. Con `E = sentados + los que miran` y `F = los que miran`, la
    #   resta del cliente sigue dando **los que juegan** y el corchete vuelve a tener qué mostrar.
    #   ⚠ El corchete se OCULTA en cooperativo y en jefe (medido el mismo día): ahí no va a salir
    #     aunque haya espectadores, y no es un bug nuestro.
    _esp = len(espectadores_de(rid))
    _sen = len(mesa_de(rid))
    s["E"] = max(1, _sen + _esp)
    s["F"] = _esp & 0xFF
    log("LOBBY", f"  ★ MATCHER: la sala {rid} pasa a mostrar {s['E']} ocupante(s)"
                 + (f" — {_sen} jugando + [{_esp}] mirando" if _esp else ""))

def desregistrar_sala(st):
    """Saca la sala de la lista. ★★ SOLO si no queda NADIE: antes la borraba el host al salir y los
    demás quedaban colgados en una sala que ya no figuraba."""
    return desregistrar_rid(getattr(st, "room_id", None))


def desregistrar_rid(rid):
    """Lo mismo, pero **por número de sala**, sin necesitar una conexión.

    ★ Existe porque el barrido de mesas huérfanas (`barrer_mesas_huerfanas`) limpia salas cuyo
      último ocupante es un fantasma: no hay ningún `st` vivo al que preguntarle el `room_id`.
      La lógica es la de siempre, movida acá enterita para que **no haya dos copias** — que es
      exactamente cómo se despegan las reglas en este repo.
    """
    if not rid:
        return
    if mesa_de(rid):
        actualizar_ocupantes_sala(rid)
        log("LOBBY", f"  ★ la sala {rid} SIGUE viva: quedan {len(mesa_de(rid))} jugador(es)")
        return
    with _mesa_lock:
        NPCS_SALA.pop(rid, None)                 # la sala se fue: sus NPC también
        MARCADOR.pop(rid, None)                  # …y el marcador de la serie arranca de cero
        SWAP_PENDIENTE.pop(rid, None)            # …y el popup de intercambio que quedó abierto
        SELECCION_SALA.pop(rid, None)            # …y la pista/canción elegidas
        DIFICULTAD_SALA.pop(rid, None)           # …y la dificultad que eligió el anfitrión
        MAPA_SALA.pop(rid, None)                 # …y el mapa forzado con `.oscuro`
        PD_VALOFE_SALA.pop(rid, None)            # …y la tabla de puntaje elegida con `.pd`
        ELECCION_JUGADOR.pop(rid, None)          # …y lo que cada uno eligió para sí (pista, obstáculos)
        VICTORIA_SALA.pop(rid, None)             # …y la condición de victoria
        GRANDE_SALA.pop(rid, None)               # …y la carrera grande (6vs6, `.grande`)
        RELEVO12.discard(rid)                    # …y sus 4 equipos (★ 15-oct)
        CUATRO12.discard(rid)
                                                 #   ⇒ la sala que reuse este rid vuelve al default
        RATE_SALA.pop(rid, None)                 # …y el multiplicador que un GM le puso a la sala
                                                 #   ⛔ ESTE es el que MÁS importa que muera: un x10
                                                 #      olvidado que le quede a un roomid reusado
                                                 #      paga de más y nadie lo mira
        SLOTS_CERRADOS.pop(rid, None)            # …y los asientos que se habían cerrado
        CANCIONES_CHASE.pop(rid, None)           # …y el sorteo de canciones del cooperativo
        CAPITANES.pop(rid, None)                 # …y los capitanes del modo jefe
        SORTEO_AL_VOLVER.discard(rid)            # …y el sorteo que quedaba pendiente
        ULTIMO_OCUPANTE.pop(rid, None)           # …y quién ocupaba cada asiento
        ANFITRION.pop(rid, None)                 # …y el dueño de la sala
        CLAVE_SALA.pop(rid, None)                # …y su contraseña: un rid reusado nace abierto
        ANFITRION_PENDIENTE.pop(rid, None)       # …y el aviso que le quedaba debiendo
    if SALAS_VIVAS.pop(rid, None) is not None:
        log("LOBBY", f"  ★★ MATCHER: sala {rid} SACADA de la lista — quedan {len(SALAS_VIVAS)}")
                                      #   El slot_mask 0x3F abre los 0-5 y el host se queda con el 2.
