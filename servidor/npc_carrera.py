# -*- coding: utf-8 -*-
"""npc_carrera — LOS NPC QUE JUEGAN (10/11-oct-2026, la carrera de 12). ⛔ SÓLO LOCAL.

anonimo03: «necesito que los NPC jueguen un poco al menos, para que su posición en la carrera simule a la de jugadores
reales, y también que sus resultados lleguen al cartel».

CÓMO SE MUEVE UN CORREDOR AJENO (leído en el exe, 11-oct)
---------------------------------------------------------
Cada cliente avisa su avance con el evento `0x05` del `FF4E` (el anunciador `0x5039C0`, rama `0x503B05`):
    A = float  · su TIEMPO de carrera [cPlayer+0x18] — avanza 1 por cuadro ([+0x1C] = 1), no es una distancia
    B = (secuencia << 16) | (asiento << 8) | (1 si su combo ≥ 40)        — la secuencia es su contador [cPlayer+0x68]
Medido (asiento 2): A = 61 · 122 · 183 · 244 … con secuencia 61 · 122 · 183 · 244 … ⇒ A = secuencia, uno por segundo.
El que lo RECIBE (`0x4FCAD0` caso 5 → `0x56D7F0` → `0x572F40`) hace `destino = A + (su contador − secuencia)`, saca la
posición en la pista de ese tiempo y lo CLAVA ahí (`0x4FE030`: [+0x18] y [+0x20], sin suavizar). Entre aviso y aviso,
cada cliente lo mueve solo (`0x5029E0`: tiempo += 1, posición += [+0x58]). Y el bit del combo pone su combo en 40 (el
fuego, `0x4FEE20`).
⛔ LA 1.ª VERSIÓN (10-oct) mandaba «tiempo × ritmo» (0,86…1,04): un corredor que el cliente movía a velocidad normal y
cada segundo tiraba para atrás de un golpe ~8 cuadros ⇒ *«se teletransportan»* (anonimo03, 11-oct).

LO QUE HACE AHORA
-----------------
Cada NPC manda su aviso COMO UN JUGADOR: con la MISMA secuencia que el humano que acaba de avisar, y `A = secuencia +
su VENTAJA`. La ventaja cambia de a poco (sólo con el impulsor y los tropezones) ⇒ el clavado de cada segundo es de
uno o dos cuadros y no se ve.
- **juega notas**: `NPC_NOTAS_SEG` por segundo, cada una la acierta según su nivel (`NPC_ACIERTO`); si falla, el combo
  vuelve a 0 y pierde `NPC_TROPEZON` cuadros.
- **el impulsor automático**: cada 40 de combo manda lo mismo que un jugador (`FF4E 0x01` efecto 5 sobre sí mismo,
  B = 100) y gana `NPC_IMPULSO` cuadros, repartidos en los 360 que dura (el cliente también lo acelera solo: +5 por
  segundo, medido; arranca en el aviso en que se manda el efecto, para que los dos empiecen juntos).
- al cartel le van filas con su precisión (aciertos/notas), su combo máximo y la llegada según su ventaja final.
⚠ `NPC_IMPULSO` es una ESTIMACIÓN: lo que gana de verdad un impulsor sale de medir (`[carrera12] medir=1` en la dll).

★★ LOS ÍTEMS (11-oct, anonimo03: «¿los NPC podrían activar los ítems? se activan con control, igual que el impulsor»)
------------------------------------------------------------------------------------------------------------------
En la carrera ÍTEM (sin `MODE_VELOCIDAD`) los NPC agarran cajas, sortean y usan ítems COMO UN JUGADOR, y les afecta lo
que les tiran. Todo leído en el exe — documentacion/ITEMS_SORTEO.md:
- **las cajas**: ⛔ MEDIDO en la 1.ª prueba (11-oct): el `FF4E 0x66` («agarré una caja») NO viaja en solo ni en
  equipo — sólo en RELEVO (`0x5047C5`: `flags & 0x40`; el otro `0x503920` de `0x504848` lo anota en la lista local
  `[cPlayer+0x2DC]`, no en la red). ⇒ cada NPC agarra una caja cada `NPC_CAJA_CADA` cuadros (al azar ±40 %), si
  acierta esa nota. En relevo, si llegan los `0x66` del humano, se usan ésos (la misma caja cuando su tiempo llega).
- **el sorteo**: el mismo de `0x4F4CB0` con la MISMA tabla que usa la d3d9 (`items_tabla.py`; ★ 26-oct la del 2013, antes la del CBT con el
  R-coin apagado): su puesto, el nivel, las 4 distancias, y las máscaras de jugadores/equipo/avance/primero/último.
- **usarlo** = el mismo aviso que manda un jugador con Control: `FF4E 0x01`, `A = (destino<<24)|(emisor<<16)|(id<<8)`,
  `B = 0` (MEDIDO: es lo que manda el humano con cada ítem; el `B = 100` es sólo el del impulsor de la barra). Los que pegan a TODOS (hielo 8, terremoto 9,
  tortuga de equipo 18) los aplica cada cliente a su propio jugador (`0x4E9A30` grupo 1); los de un blanco (2 4 6 14)
  van al de adelante.
- **lo que les tiran**: el `0x01` de un humano (o de otro NPC) a un NPC le baja la ventaja / le hace fallar notas.
★ 2.ª prueba (anonimo03, 11-oct): *«en un momento están en un sitio y al otro aparecen un tramo más adelante»* (y quizá
  para atrás). Era la ventaja de varios ítems JUNTOS: tres impulsores encimados suman +15/s y el cliente sólo lo
  acelera +5/s; cinco tortugas encimadas, −30/s que el cliente no ve. Cada aviso lo clavaba. ⇒ lo que se MANDA
  (`v_env`) sigue a la ventaja de verdad, pero cada aviso se corre como mucho `NPC_FRENO_MAX` por segundo más allá
  de lo que el cliente ya lo mueve solo (+5/s con un impulsor andando). Lo que no alcanza, lo alcanza después.
★★ 4.ª prueba — MEDIDO con DOS humanos (anonimo03, 11-oct; `_trabajo/logs/ff4e_carrera.jsonl`, `anotar_ff4e`):
  · el ítem no pega al tirarlo: VUELA (`0x4F4BBC`: 120 cuadros, el terremoto 60, la tortuga de equipo 110). Medido:
    el golpe llega 2,0 s después del `0x01`.
  · el que recibe el HIELO manda `FF4E 0x06` con `A = (8 << 16) | (asiento << 8)` y `B = su secuencia` («me pegó el
    hielo»: así los demás lo ven congelado), y DEJA DE AVISAR su avance (`0x05`) ~2,6 s. Pierde 76-82 cuadros (4 de 4).
  · la tortuga de equipo: sin `0x06`, deja de avisar ~4,5 s y pierde 18 (3 de 3). El terremoto: no perdió nada (4 de 4).
  ⇒ un NPC golpeado hace LO MISMO: a los 120 cuadros del tiro manda el `0x06` (si es hielo), se calla esos segundos,
    y vuelve con lo perdido ya descontado (sin el suavizado: el cliente lo tenía quieto). Lo que no se midió (la
    tortuga sola, la bomba) va como la tortuga de equipo / estimado.
★★ EL RELEVO (anonimo03, 11-oct: «son 3 por equipo, pero por tramo corre 1; nunca los 3 a la vez»). Leído en el exe
  (documentacion/MODO_RELEVO.md §2.3): el orden de tramos es el ORDEN DE ASIENTOS de cada equipo, y la posta la
  avisa el que termina su tramo con `FF4E 0x64`: `A = (aguja << 16) | (asiento << 8) | grado`, `B = secuencia + 1`.
  ⇒ en relevo sólo corre (avisa, juega notas, agarra y usa ítems) el NPC que tiene la posta; al llegar al final de
    su tramo manda el `0x64` y el siguiente de su equipo arranca desde ahí. Si el siguiente es un humano, su juego
    arranca solo con ese aviso; si un humano le pasa la posta a un NPC (`al_posta`), el NPC sigue desde donde quedó.
  ⛔ 2.ª prueba del relevo: la posta NO la avisa el que llega: la avisa el que RECIBE, con SU asiento (lo dice §2.3-
    quater del doc: el que juega la aguja es el que entra; si no aprieta, grado 3). El NPC avisaba con el asiento
    del que llegaba y seguía corriendo ⇒ a anonimo03 le quedó «Pasar la batuta» en pantalla mientras el NPC seguía de
    largo. ⇒ el que llega se FRENA en el final de su tramo; si recibe un NPC, a los 0,4-1,3 s el server avisa el
    `0x64` con el asiento del NPC; si recibe un humano, lo avisa su juego (`al_posta`).
  ⚠ EL LARGO DEL TRAMO: la carrera dura Σ Δcoord × 300 / BPM del chart (medido en 2 canciones: 5.382 contra 5.396
    de la llegada real en la 867) y se parte en partes iguales (DEDUCIDO: «tramos iguales»).
  ⚠ Y el humano que ESPERA su tramo puede no avisar nada: un reloj (`_reloj`) sigue moviendo a los NPC con la hora
    del server si en 1,5 s no llegó ningún aviso de un humano.
  ⛔ 1.ª prueba del relevo (11-oct): anonimo03 en el 3.er tramo ⇒ su juego NO MANDÓ NI UN AVISO (sólo dos `0xB4`) y la
    simulación, que arrancaba con el primer aviso de un humano, no arrancó nunca: se quedó esperando la posta del
    NPC 2 en «Pasar la batuta». ⇒ arranca con el `FF24 GO` (`al_arrancar`, desde `dar_el_go`), y el reloj de la
    carrera empieza `NPC_ARRANQUE_S` después (MEDIDO: el 1.er aviso de un humano, secuencia 61, llega 12,6 s después
    del GO en 2 de 2 carreras ⇒ la secuencia 0 es GO + 11,6 s).
⚠⚠ CUÁNTO FRENA CADA ÍTEM era una ESTIMACIÓN (`NPC_ITEM_EFECTO`): se mide con el medidor de la dll mirando al humano
   cuando le pega el hielo de un NPC. Y el 13 (diablo) y el 17 no se sabe qué hacen: se usan sin efecto propio.
⚠ Va atado a `CHASE_NPC_REALISTA` (= la consola de GM de LOCAL): prod no tiene NPC y esto no corre ni por accidente.
⚠ No cobran nada: sus filas van con `usn = None` (el pago las saltea).
"""
import math
import random
import struct
import threading

from .ajustes import CHASE_NPC_REALISTA, FF4E_FIRMA_GLOBO, FF4E_SUB_GLOBO
from .registro import log

NPC_NOTAS_SEG = 2.6             # notas por segundo (el humano medido: combo 40 a los ~16 s)
NPC_ACIERTO = (0.955, 0.997)    # probabilidad de acertar cada nota: el peor y el mejor NPC
NPC_TROPEZON = 1.2              # cuadros que pierde al cortar el combo
NPC_IMPULSO = 30.0              # ✅ MEDIDO (11-oct, el medidor de la dll): un impulsor = +5 cuadros por segundo…
NPC_IMPULSO_DURA = 360          # …durante 6 s (360 cuadros) ⇒ +30. ⛔ NO es el B = 100 del efecto (la 2.ª versión lo
                                #    repartía en 100 y el NPC daba un salto de +34 en un segundo)
NPC_COMBO_IMPULSO = 40          # el impulsor de la barra: cada 40 de combo (velocidad)
GLOBO_LATIDO = 4                # ★ 14-oct: el combo del NPC al globo, aunque no cambie, cada tantos avisos (~1,3 s)
NPC_COMBO_IMPULSO_ITEM = 80     # ★ 14-oct, MEDIDO: en la carrera ÍTEM un jugador real tira la mitad de impulsores de barra
                                #   (el Ctrl se va en tirar el ítem): 2 humanos jugando perfecto (jugador23 y jugador22, plan de
                                #   Lavie) mandaron 7 en una carrera de 12; los 10 NPC, 71 (7,1 cada uno, cada 40). Con 80, ~3,5
                                #   — y era lo que anonimo03 veía: «mucho drop de impulsores», y los NPC le ganaban al perfecto.
NPC_DERIVA = 0.4                # cuadros por segundo que puede ir ganando/perdiendo de a poco (su paso propio)
EFECTO_IMPULSOR = 5

# ★ los ítems (11-oct). id → (qué es, a quién, efecto en el que lo recibe). `a quién`: "yo" (sobre sí) · "todos" (el
#   grupo 1 de 0x4E9A30: cada cliente se lo aplica a su jugador) · "uno" (un blanco: el de adelante).
#   efecto: ("frena", cuadros perdidos, cuadros callado, cuadros de vuelo, manda el 0x06) · ("falla", ×prob. de fallar, cuadros) · ("impulso",)
#           · ("inmune", cuadros) · ("escudo",) · ("espejo",) · ("auto", cuadros) · ("curar",) · None
#   ⚠ los cuadros son ESTIMACIONES a medir (ver arriba). 2.ª prueba: a la mitad (terminaban hasta 5 s atrás).
NPC_ITEM = {
    1: ("estrella", "yo", ("inmune", 360)),
    2: ("oculta", "uno", ("falla", 4.0, 300)),
    3: ("espejo", "yo", ("espejo",)),
    4: ("interferencia", "uno", ("falla", 5.0, 300)),
    5: ("impulsor", "yo", ("impulso",)),
    6: ("tortuga", "uno", ("frena", 18, 270, 120, False)),       # como la de equipo (no medida)
    7: ("escudo", "yo", ("escudo",)),
    8: ("hielo", "todos", ("frena", 78, 160, 120, True)),        # ✅ MEDIDO 4 de 4
    9: ("terremoto", "todos", None),                              # ✅ MEDIDO: no perdió nada (4 de 4)
    10: ("auto", "yo", ("auto", 480)),
    11: ("curar", "yo", ("curar",)),
    12: ("rcoin", "yo", None),
    13: ("diablo", "yo", None),
    14: ("bomba", "uno", ("frena", 40, 120, 120, False)),        # ⚠ estimado
    15: ("imp. equipo", "yo", ("impulso",)),
    16: ("imp. invencible", "yo", ("impulso",)),
    17: ("id17", "yo", None),
    18: ("tortuga equipo", "todos", ("frena", 18, 270, 110, False)),   # ✅ MEDIDO 3 de 3
}
NPC_ITEM_ESPERA = {"yo": (60, 300), "todos": (40, 200), "uno": (40, 200)}   # cuadros entre agarrarlo y usarlo
NPC_LARGO = 5500                # cuadros de una carrera típica (para el «avance» de la caja; sólo es una máscara)
NPC_FRENO_MAX = 6.0             # ★ cuadros por segundo que puede perder un NPC frenado (el 10 % de lo que anda). Su
                                #   cliente lo sigue moviendo solo entre avisos, y cada aviso lo CLAVA: congelarlo de
                                #   golpe (perder 61 por segundo) se vería como un teletransporte para atrás. ⇒ el hielo
                                #   pierde lo mismo, pero repartido en más tiempo (90 cuadros → 15 s).
NPC_CASILLEROS = 2              # ítems que puede tener a la vez: 2, como un jugador con la mascota del 2.º ítem (anonimo03, 11-oct)
NPC_IMPULSO_CLIENTE = 5.0       # lo que el cliente mueve SOLO a un corredor con el impulsor andando (+5/s, medido)
NPC_ARRANQUE_S = 11.6           # ✅ MEDIDO: segundos del FF24 GO a la secuencia 0 de la carrera (2 de 2)
NPC_CAJA_CADA = 600             # ⚠ ESTIMADO: era 360 (una cada 6 s, con las cajas del CBT, ~24 por canción: el humano medido
                                #   usó 20 ítems en 8.455 cuadros, y con los dos casilleros llenos pierde las que agarra).
                                #   ★ 26-oct (120): las cajas vuelven a las del 2013 (÷900, el 60 %) ⇒ 360 × 900 / 540

_SIM = {}                       # rid -> {"magic", "npcs": {slot: perfil}, "seq", "humano": {...}}
_lock = threading.RLock()


def _perfil():
    nivel = random.random()
    return {"nivel": nivel, "acierto": NPC_ACIERTO[0] + (NPC_ACIERTO[1] - NPC_ACIERTO[0]) * nivel,
            "paso": random.uniform(-NPC_DERIVA, NPC_DERIVA) * (0.4 + nivel),
            "base": 0.0, "rampas": [], "combo": 0, "combo_max": 0, "notas": 0, "aciertos": 0,
            "tropiezos": 0, "impulsos": 0, "resto": 0.0,
            # los ítems: lo que tiene (hasta 2, como el jugador) y lo que tiene encima
            "items": [], "caja": 0, "prox_caja": None, "inmune": 0, "escudo": False, "espejo": False, "auto": 0,
            "falla": (1.0, 0), "usados": 0, "recibidos": 0}


def _impulso_andando(p, seq):
    return any(g > 0 and ini <= seq < ini + d for ini, g, d in p["rampas"])


def _ventaja_a_mandar(p, desde, seq):
    """Lo que se MANDA: sigue a la ventaja de verdad sin saltos que se vean (ver la cabecera, 2.ª prueba)."""
    v = _ventaja(p, seq)
    prev = p.get("v_env")
    if prev is None or seq <= desde:
        p["v_env"] = v
        return v
    dt = (seq - desde) / 60.0
    esperado = prev + (NPC_IMPULSO_CLIENTE * dt if _impulso_andando(p, desde) else 0.0)
    lim = NPC_FRENO_MAX * dt
    p["v_env"] = min(esperado + lim, max(esperado - lim, v))
    return p["v_env"]


def _ventaja(p, seq):
    v = p["base"]
    for ini, gana, dura in p["rampas"]:
        v += gana * min(1.0, max(0.0, (seq - ini) / dura))
    return v


def _sim_de(rid, magic, npcs):
    with _lock:
        s = _SIM.get(rid)
        if s is None or s["magic"] != magic or set(s["npcs"]) != set(npcs):
            s = {"magic": magic, "npcs": {sl: _perfil() for sl in npcs}, "seq": None,
                 "humano": {"impulsos": 0, "A_menos_seq": 0.0, "avisos": 0},
                 "humanos": {},          # asiento → su A − secuencia (para el puesto y las distancias)
                 "cajas": [],            # los tiempos en que los humanos agarraron una caja (las mismas para todos)
                 "item": False, "relevo": False, "equipos": None, "activo": {1: 0, 2: 0}, "tramo": None,
                 "t_aviso": 0.0, "t_seq": 0.0, "destinos": [], "creada": __import__("time").time()}
            _SIM[rid] = s
            threading.Thread(target=_reloj, args=(rid, s), daemon=True, name=f"npc-reloj-{rid}").start()
            log("LOBBY", "  🤖 NPC que juegan (sala %s): " % rid + " · ".join(
                f"slot {sl} acierta {p['acierto'] * 100:.1f}%" for sl, p in sorted(s["npcs"].items())))
        return s


def _f2u(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def _jugar(p, sl, desde, hasta, eventos, cada=NPC_COMBO_IMPULSO):
    """Las notas de `desde` a `hasta` (cuadros). Devuelve nada; anota impulsos en `eventos`."""
    dt = hasta - desde
    if dt <= 0:
        return
    p["base"] += p["paso"] * dt / 60.0
    esperado = NPC_NOTAS_SEG * dt / 60.0 + p["resto"]
    n = int(esperado)
    p["resto"] = esperado - n
    falla = 1.0 - p["acierto"]
    if p["falla"][1] > hasta:
        falla = min(0.5, falla * p["falla"][0])
    if p["auto"] > hasta:
        falla = 0.0
    for k in range(n):
        p["notas"] += 1
        if random.random() >= falla:
            p["aciertos"] += 1
            p["combo"] += 1
            p["combo_max"] = max(p["combo_max"], p["combo"])
            if p["combo"] % cada == 0:
                p["rampas"].append((hasta, NPC_IMPULSO, NPC_IMPULSO_DURA))   # empieza con el efecto que se manda ahora
                p["impulsos"] += 1
                eventos.append(sl)
        else:
            if p["combo"]:
                p["tropiezos"] += 1
                p["base"] -= NPC_TROPEZON
            p["combo"] = 0


def _tramo_estimado(rid, n):
    """El largo de un tramo de relevo (cuadros), del chart: la carrera dura Σ Δcoord × 300 / BPM (los BPM vienen en
    la cabecera del chart) — MEDIDO en 2 canciones (6305: 8.356 calculado; 867: 5.382 contra 5.396 de la llegada)."""
    try:
        import zlib
        from . import notas
        from .salas import CARRERAS
        d = notas.chart_de((CARRERAS.get(rid) or {}).get("cancion"))
        k = struct.unpack_from("<i", d, 0)[0]
        marcas = sorted(struct.unpack_from("<if", d, 4 + 8 * j) for j in range(k))
        crudo = zlib.decompress(d[4 + k * 8:])
        ultima = max(struct.unpack_from("<H", crudo, i)[0] for i in range(0, len(crudo) - len(crudo) % 6, 6))
        total, puntos = 0.0, marcas + [(ultima, None)]
        for (c0, bpm), (c1, _) in zip(puntos, puntos[1:]):
            if c1 > c0 and bpm:
                total += (c1 - c0) * 300.0 / bpm
        return (total + 20) / max(1, n)
    except Exception:                                        # noqa: BLE001
        return 8000.0 / max(1, n)


def _armar_relevo(s, rid, humanos):
    """Los planteles de cada equipo en orden de tramo (= orden de asientos, MODO_RELEVO.md §2.3)."""
    from .salas import equipo_de
    todos = sorted(set(humanos) | set(s["npcs"]))
    # ★ 14-oct: los equipos que haya (2, o hasta 4 en el relevo de 12 — RELEVO_12.md), cada uno en orden de asientos
    eqs = sorted({equipo_de(rid, x) for x in todos})
    s["equipos"] = {e: [x for x in todos if equipo_de(rid, x) == e] for e in eqs}
    s["activo"] = {e: 0 for e in eqs}
    s["aprieta"] = {}                                        # equipo → (cuadro en que el NPC que recibe aprieta, desde)
    s["humanos_set"] = set(humanos)
    n = max([len(v) for v in s["equipos"].values()] + [1])
    s["tramo"] = _tramo_estimado(rid, n)
    log("LOBBY", "  🤖 RELEVO: " + " · ".join(f"equipo {e} {s['equipos'][e]}" for e in eqs)
                 + f" · tramo ≈ {s['tramo']:.0f} cuadros (del chart)")


def _corriendo(s):
    """Los asientos que están en la pista: todos, o en relevo el que tiene la posta de cada equipo."""
    if not s.get("relevo") or not s.get("equipos"):
        return None
    out = set()
    for eq, plantel in s["equipos"].items():
        i = s["activo"].get(eq, 0)
        if i < len(plantel):
            out.add(plantel[i])
    return out


def _postas(s, seq):
    """Relevo — la posta, como la juega el cliente (MODO_RELEVO.md §2.3-quater, MEDIDO): el que llega al final de su
    tramo se FRENA ahí, y el que RECIBE juega la aguja y avisa `FF4E 0x64` con SU asiento:
    `A = (aguja << 16) | (asiento del que recibe << 8) | grado`. Si el que recibe es un humano, su juego le muestra
    «Pasar la batuta» y avisa él (o se le vence la aguja: grado 3). Si es un NPC, lo avisa el server."""
    salida = []
    if not s.get("relevo") or not s.get("equipos"):
        return salida
    for eq, plantel in s["equipos"].items():
        i = s["activo"].get(eq, 0)
        if i >= len(plantel) - 1:
            continue                                         # el último corre hasta la meta
        corre, recibe = plantel[i], plantel[i + 1]
        fin = (i + 1) * s["tramo"]
        p = s["npcs"].get(corre)
        if p is not None:
            if p.get("pausa_hasta", 0) > seq or seq + _ventaja(p, seq) < fin:
                continue
            if p.get("fin") is None:
                p["fin"] = fin                               # se frena en el final de su tramo y espera
                log("LOBBY", f"  🤖 RELEVO t={seq}: el NPC {corre} llegó al final del tramo {i + 1} (t={fin:.0f}); "
                             f"espera que {recibe} agarre la posta")
        else:
            t = seq + s["humanos"].get(corre, -1e9)          # un humano: llegó cuando su tiempo alcanza el final
            if t < fin - 15:
                continue
        q = s["npcs"].get(recibe)
        if q is None:
            continue                                         # recibe un humano: lo avisa su juego (al_posta)
        if eq not in s["aprieta"]:
            s["aprieta"][eq] = seq + random.randint(25, 80)  # lo que tarda en apretar Ctrl
            continue
        if seq < s["aprieta"][eq]:
            continue
        del s["aprieta"][eq]
        grado = 1 if random.random() < 0.4 + 0.5 * q["nivel"] else random.choice((2, 2, 3))
        aguja = random.randint(160, 200) if grado == 1 else random.randint(100, 240)
        salida.append((0x64, (aguja << 16) | (recibe << 8) | grado, (seq + 1) & 0xFFFF, f"posta al NPC {recibe}"))
        _pasar(s, eq, recibe, fin, seq)
    return salida


def _pasar(s, eq, recibe, t_inicio, seq):
    """La posta pasó a `recibe`: es el que corre ahora, desde `t_inicio` (el final del tramo anterior)."""
    plantel = s["equipos"][eq]
    i = plantel.index(recibe)
    s["activo"][eq] = i
    s["aprieta"].pop(eq, None)
    if i > 0 and plantel[i - 1] in s["npcs"]:
        s["npcs"][plantel[i - 1]]["fin"] = None
    q = s["npcs"].get(recibe)
    if q is not None:                                       # el NPC que la recibe sigue desde ahí
        q["base"], q["rampas"], q["v_env"], q["combo"] = t_inicio - seq, [], None, 0
        q["prox_caja"], q["items"], q["fin"] = None, [], None
    log("LOBBY", f"  🤖 RELEVO t={seq}: la posta la tiene {recibe} (equipo {eq}, tramo {i + 1}, desde t={t_inicio:.0f})")


def al_posta(st, A, B):
    """Lo llama `lobby.py` con el `FF4E sub=0x64` de un humano: AGARRÓ la posta (el asiento del `A` es el suyo, el que
    recibe — medido, MODO_RELEVO.md §2.3-quater)."""
    if not CHASE_NPC_REALISTA:
        return
    rid = getattr(st, "room_id", None)
    sl = (A >> 8) & 0xFF
    with _lock:
        s = _SIM.get(rid)
        if not s or not s.get("equipos"):
            return
        eq = next((e for e, pl in s["equipos"].items() if sl in pl), None)
        if eq is None:
            return
        plantel = s["equipos"][eq]
        i = plantel.index(sl)
        seq = s["seq"] or 0
        de = plantel[i - 1] if i > 0 else None
        p = s["npcs"].get(de)
        t_ini = p["fin"] if p is not None and p.get("fin") is not None else (
            seq + _ventaja(p, seq) if p is not None else seq + s["humanos"].get(de, 0.0))
        log("LOBBY", f"  🤖 RELEVO: el humano {sl} agarró la posta de {de} (grado {A & 0xFF}, aguja {(A >> 16) & 0xFFFF}) "
                     f"en t≈{t_ini:.0f} (el tramo estimado terminaba en {i * s['tramo']:.0f})")
        _pasar(s, eq, sl, t_ini, seq)


def _reloj(rid, s):
    """Mueve a los NPC con la hora del server cuando ningún humano avisa (el que espera su tramo, en relevo)."""
    import time
    while True:
        time.sleep(1.0)
        with _lock:
            if not CHASE_NPC_REALISTA or _SIM.get(rid) is not s or time.time() - s["creada"] > 1200:
                return
            # ★ 3.ª prueba del relevo: terminada la carrera seguía mandando a un juego cerrado. Si ya no queda nadie
            #   a quien mandarle (o la sala corre otra carrera), se para solo.
            vivos = [c for c in s["destinos"] if not getattr(c, "cerrado", False) and getattr(c, "room_id", rid) == rid]
            if s["destinos"] and not vivos:
                _SIM.pop(rid, None)
                log("LOBBY", f"  🤖 sala {rid}: no queda nadie en la carrera — los NPC se paran")
                return
            if s["seq"] is None or time.time() - s["t_aviso"] < 1.5:
                continue
            seq = int(s["seq"] + (time.time() - s["t_seq"]) * 60)
            s["por_reloj"] = True
        try:
            _avanzar(s, seq, list(s["destinos"]))
        except Exception as e:                               # noqa: BLE001
            log("LOBBY", f"  ⚠ el reloj de los NPC: {e!r}")


def al_avance(st, A, B, destinos):
    """Lo llama `lobby.py` con cada `FF4E sub=0x05` de un humano. Manda el `0x05` de cada NPC a `destinos`."""
    if not CHASE_NPC_REALISTA:
        return
    from .salas import CARRERAS, _mesa_lock, npcs_de
    rid = getattr(st, "room_id", None)
    if rid is None or getattr(st, "room_colab", False) or getattr(st, "room_boss", False):
        return
    npcs = [s for s in (npcs_de(rid) or []) if s != getattr(st, "room_slot", None)]
    if not npcs:
        return
    t = struct.unpack("<f", struct.pack("<I", A & 0xFFFFFFFF))[0]
    seq = (B >> 16) & 0xFFFF
    with _mesa_lock:
        magic = (CARRERAS.get(rid) or {}).get("magic")
    s = _sim_de(rid, magic, npcs)
    with _lock:
        if s.get("por_reloj") and s["seq"] is not None:
            est = s["seq"] + (__import__("time").time() - s["t_seq"]) * 60
            log("LOBBY", f"  🤖 el humano {getattr(st, 'room_slot', '?')} avisa: su secuencia {seq} contra el reloj "
                         f"{est:.0f} (diferencia {seq - est:+.0f} cuadros)")
            if seq < s["seq"]:
                s["seq"] = seq - 20                     # ★ manda el humano: el reloj se había adelantado
        s["por_reloj"] = False
        h = s["humano"]
        h["A_menos_seq"] = t - seq
        h["avisos"] += 1
        s["humanos"][getattr(st, "room_slot", None)] = t - seq
        _el_modo(s, st, rid)
        s["t_aviso"], s["destinos"] = __import__("time").time(), list(destinos)
    _avanzar(s, seq, destinos)


def _el_modo(s, st, rid):
    from .ajustes import MODE_VELOCIDAD, MODE_RELEVO
    s["item"] = not (getattr(st, "room_mode", 0) & MODE_VELOCIDAD)
    s["rid"], s["modo"] = rid, getattr(st, "room_mode", 0)
    s["relevo"] = bool(getattr(st, "room_mode", 0) & MODE_RELEVO)
    if s["relevo"] and s["equipos"] is None:
        from .salas import mesa_de
        _armar_relevo(s, rid, list(mesa_de(rid)))


def al_arrancar(rid, st, destinos):
    """Lo llama `dar_el_go` con el `FF24 GO`: la simulación arranca YA, sin esperar el aviso de un humano (el que espera
    su tramo de relevo no avisa nada, medido). El reloj la mueve desde la secuencia 0 = GO + NPC_ARRANQUE_S."""
    if not CHASE_NPC_REALISTA or st is None:
        return
    import time
    from .salas import CARRERAS, _mesa_lock, npcs_de, mesa_de
    if getattr(st, "room_colab", False) or getattr(st, "room_boss", False):
        return
    humanos = set(mesa_de(rid))
    npcs = [x for x in (npcs_de(rid) or []) if x not in humanos]
    if not npcs:
        return
    with _mesa_lock:
        magic = (CARRERAS.get(rid) or {}).get("magic")
    s = _sim_de(rid, magic, npcs)
    with _lock:
        _el_modo(s, st, rid)
        s["seq"], s["t_seq"], s["t_aviso"] = 0, time.time() + NPC_ARRANQUE_S, 0.0
        s["destinos"] = list(destinos)
    log("LOBBY", f"  🤖 los NPC arrancan con el GO (la carrera, en {NPC_ARRANQUE_S:g} s)"
                 + (" · RELEVO" if s["relevo"] else "") + (" · ÍTEM" if s["item"] else ""))


def _avanzar(s, seq, destinos):
    """Un tramo de la simulación (lo dispara el aviso de un humano, o el reloj si nadie avisa)."""
    impulsos = []
    with _lock:
        h = s["humano"]
        # con varios humanos llegan avisos de todos: se juega una vez por tramo (el reloj es la secuencia)
        if s["seq"] is not None and seq < s["seq"] + 20:
            return
        desde = s["seq"] if s["seq"] is not None else 0
        s["seq"], s["t_seq"] = seq, __import__("time").time()
        corren = _corriendo(s)                          # en relevo, sólo los que tienen la posta
        salida = []
        efectos = []
        globos = []
        for sl, p in sorted(s["npcs"].items()):
            if (corren is None or sl in corren) and p.get("fin") is None:
                _jugar(p, sl, desde, seq, impulsos, NPC_COMBO_IMPULSO_ITEM if s["item"] else NPC_COMBO_IMPULSO)
        if s["item"]:
            efectos = _items(s, seq) + _golpes(s, seq)  # antes del avance: lo que les pegó ya cuenta en este aviso
        efectos += _postas(s, seq)
        corren = _corriendo(s)
        for sl, p in sorted(s["npcs"].items()):
            if corren is not None and sl not in corren:
                continue                                # relevo: espera su tramo, no avisa nada
            if p.get("pausa_hasta", 0) > seq:               # golpeado: se calla, como un jugador (medido)
                p["callado"] = True
                continue
            if p.pop("callado", False):
                p["v_env"] = None                           # vuelve con lo perdido entero: el cliente lo tenía quieto
            if p.get("fin") is not None:                    # relevo: frenado en el final de su tramo, esperando
                a = p["fin"]
                p["base"], p["rampas"], p["v_env"] = p["fin"] - seq, [], p["fin"] - seq
            else:
                a = max(0.0, seq + _ventaja_a_mandar(p, desde, seq))
            salida.append((sl, _f2u(a), ((seq & 0xFFFF) << 16) | ((sl & 0xFF) << 8) | (1 if p["combo"] >= 40 else 0)))
            # ★ 14-oct · el GLOBO DEL COMBO (globo_combo.c): en el relevo, el NPC que corre manda su combo como un
            #   jugador (si cambió, o cada GLOBO_LATIDO avisos: si no, el globo del que mira se apaga)
            # ★ 15-oct · y FUERA del relevo también, pero sólo a los ESPECTADORES (abajo): el que mira un NPC no tiene
            #   teclas que re-juzgar (el NPC no transmite) y veía 0 — el globo usa este combo (ESPECTADOR_12.md §5)
            if p.get("fin") is None:
                p["globo_n"] = p.get("globo_n", 0) + 1
                if p["combo"] != p.get("globo_env") or p["globo_n"] >= GLOBO_LATIDO:
                    p["globo_env"], p["globo_n"] = p["combo"], 0
                    globos.append((sl, p["combo"]))
        if h["avisos"] % 10 == 1:
            log("LOBBY", f"  🤖 t={seq} humano A−seq={h['A_menos_seq']:+.1f} · NPC ventaja: " + " ".join(
                f"{sl}:{_ventaja(p, seq):+.0f}c{p['combo']}" for sl, p in sorted(s["npcs"].items())))
    if salida or efectos:
        _anotar_npc(salida, efectos)
    relevo = s.get("relevo") and s.get("equipos")
    mirones = set()
    if globos and not relevo:
        try:
            from .salas import espectadores_de
            mirones = {id(x) for x in espectadores_de(s["rid"])}
        except Exception:                                  # noqa: BLE001
            mirones = set()
    for c in destinos:
        for sl, a, b in salida:
            try:
                c.send_ff4e(0x05, a, b, name=f"avance del NPC slot {sl}")
            except Exception as e:                         # noqa: BLE001
                log("LOBBY", f"  ⚠ no pude mandar el avance del NPC {sl}: {e!r}")
        for sl in impulsos:                                # el impulsor automático, igual que un jugador
            try:
                c.send_ff4e(0x01, (sl << 24) | (sl << 16) | (EFECTO_IMPULSOR << 8), 100,
                            name=f"impulsor del NPC slot {sl}")
            except Exception as e:                         # noqa: BLE001
                log("LOBBY", f"  ⚠ no pude mandar el impulsor del NPC {sl}: {e!r}")
        for sl, combo in (globos if (relevo or id(c) in mirones) else ()):   # ★ el globo: relevo, o al que mira
            try:
                c.send_ff4e(FF4E_SUB_GLOBO, FF4E_FIRMA_GLOBO | (sl & 0xFF), combo, name=f"combo del NPC slot {sl}")
            except Exception as e:                         # noqa: BLE001
                log("LOBBY", f"  ⚠ no pude mandar el combo del NPC {sl}: {e!r}")
        for sub, a, b, nom in efectos:                     # ★ los ítems de los NPC y sus golpes, igual que un jugador
            try:
                c.send_ff4e(sub, a, b, name=nom)
            except Exception as e:                         # noqa: BLE001
                log("LOBBY", f"  ⚠ no pude mandar el ítem del NPC: {e!r}")
    if impulsos:
        log("LOBBY", f"  🤖 t={seq} impulsor de los NPC {impulsos}")


def al_efecto(st, A, B):
    """Lo llama `lobby.py` con cada `FF4E sub=0x01` de un humano: cuenta SUS impulsores (para comparar la llegada)."""
    if not CHASE_NPC_REALISTA:
        return
    rid = getattr(st, "room_id", None)
    sl = getattr(st, "room_slot", None)
    if rid is None or sl is None:
        return
    # ⚠ los nombres de antes estaban al revés: el byte alto es el DESTINO y el siguiente el EMISOR (0x503A7D)
    destino, emisor, ef = (A >> 24) & 0xFF, (A >> 16) & 0xFF, (A >> 8) & 0xFF
    with _lock:
        s = _SIM.get(rid)
        if not s:
            return
        if ef == EFECTO_IMPULSOR and destino == sl and emisor == sl:
            s["humano"]["impulsos"] += 1
        if s.get("item") and ef in NPC_ITEM and ef != EFECTO_IMPULSOR:
            log("LOBBY", f"  🎁 el humano (slot {emisor}) usó {NPC_ITEM[ef][0]} ({ef}) → destino {destino} · B={B}")
            if s["seq"] is not None:
                _recibir(s, emisor, destino, ef, s["seq"])


def al_caja(st, A, B):
    """Lo llama `lobby.py` con cada `FF4E sub=0x66` de un humano (agarró una caja «?»): las cajas son las mismas para
    todos, así que cada NPC agarra ESA cuando su tiempo llegue al del humano."""
    if not CHASE_NPC_REALISTA:
        return
    rid = getattr(st, "room_id", None)
    with _lock:
        s = _SIM.get(rid)
        if not s or s["seq"] is None:
            return
        t = s["seq"] + s["humanos"].get(getattr(st, "room_slot", None), 0.0)
        if all(abs(t - x) > 15 for x in s["cajas"]):         # con varios humanos, la misma caja se ve varias veces
            s["cajas"].append(t)
            s["cajas"].sort()
        log("LOBBY", f"  🎁 el humano (slot {getattr(st, 'room_slot', '?')}) agarró una caja en t≈{t:.0f} "
                     f"(A=0x{A & 0xFFFFFFFF:08X} B=0x{B & 0xFFFFFFFF:08X})")


# ── ★ los ítems de los NPC ────────────────────────────────────────────────────────────────────────────────────────
def _corredores(s, seq):
    """[(tiempo, asiento)] de todos, del que va adelante al último."""
    corren = _corriendo(s)
    out = [(seq + v, sl) for sl, v in s["humanos"].items() if sl is not None and (corren is None or sl in corren)]
    out += [(seq + _ventaja(p, seq), sl) for sl, p in s["npcs"].items() if corren is None or sl in corren]
    return sorted(out, reverse=True)


def _rival(s, a, b):
    from .ajustes import MODE_EQUIPO, MODE_RELEVO
    if not (s.get("modo", 0) & (MODE_EQUIPO | MODE_RELEVO)):
        return a != b
    from .salas import equipo_de
    return equipo_de(s["rid"], a) != equipo_de(s["rid"], b)


def _equipo(s, sl):
    from .salas import equipo_de
    return equipo_de(s["rid"], sl)


def _lider_a3(s, orden):
    """El equipo que va ganando la carrera a 3 (gana el primero que mete 3): recorre `orden` (del 1.º al último)."""
    cuenta = {}
    for _, x in orden:
        e = _equipo(s, x)
        cuenta[e] = cuenta.get(e, 0) + 1
        if cuenta[e] == 3:
            return e
    return _equipo(s, orden[0][1]) if orden else None


def _sortear(s, sl, seq, t_caja):
    """El sorteo de 0x4F4CB0 (documentacion/ITEMS_SORTEO.md §2) con la tabla de la d3d9, para el NPC `sl`."""
    from .ajustes import MODE_EQUIPO, MODE_RELEVO
    from .items_tabla import TABLA, TABLA_DOCE, TABLA_DOCE_EQ
    orden = _corredores(s, seq)
    n = len(orden)
    i = next(k for k, (_, x) in enumerate(orden) if x == sl)
    yo = orden[i][0]
    # ★ 14-oct: con más de 6, lo mismo que la d3d9 (items.c, 3): «son 6», el puesto escalado y la tabla de 12
    nn, ii, T = (6, min(5, i * 6 // n), TABLA_DOCE) if n > 6 else (n, i, TABLA)
    #   y en EQUIPO, si su equipo va GANANDO la carrera a 3 (la regla de victoria de la de 12), sin hielo (como la d3d9)
    if n > 6 and (s.get("modo", 0) & MODE_EQUIPO) and not (s.get("modo", 0) & MODE_RELEVO):
        if _lider_a3(s, orden) == _equipo(s, sl):
            T = TABLA_DOCE_EQ

    def esc(d):
        d = int(abs(d))
        return 0 if d == 0 else min(9, d // 15 + 1)
    filas = []
    if nn in (6, 5, 4, 3):
        filas.append({6: 0, 5: 6, 4: 11, 3: 15}[nn] + ii)
    filas.append(0x12 + (10 - 1) // 2)                                     # nivel: 5★ (el server no lo sabe acá)
    filas += [0x1C + esc(orden[i - 1][0] - yo if i > 0 else 0), 0x26 + esc(yo - orden[i + 1][0] if i < n - 1 else 0),
              0x30 + esc(orden[0][0] - yo), 0x3A + esc(yo - orden[-1][0])]
    filas.append(0x42 + max(nn, 2))
    equipo = bool(s.get("modo", 0) & MODE_EQUIPO) and not (s.get("modo", 0) & MODE_RELEVO)
    filas.append(0x49 if equipo else 0x4A)
    filas.append(0x4A + min(9, int(9 * t_caja / NPC_LARGO) + 1))
    if i == 0 and (n < 2 or orden[1][0] < yo):
        filas.append(0x54)
    elif i == n - 1 and n > 1 and orden[-2][0] > yo:
        filas.append(0x55)
    if s.get("modo", 0) & (MODE_EQUIPO | MODE_RELEVO):
        filas.append(0x56)
    peso, vivo = [0] * 18, [True] * 18
    for f in filas:
        if f >= len(T):
            continue
        for k in range(18):
            if f >= 0x44:
                vivo[k] = vivo[k] and T[f][k] != 0
            else:
                peso[k] += T[f][k]
    bolsa = [k + 1 for k in range(18) if vivo[k] and peso[k] > 0 for _ in range(peso[k])]
    return random.choice(bolsa) if bolsa else EFECTO_IMPULSOR


def _recibir(s, emisor, destino, ef, seq):
    """Un ítem usado (por un humano o por un NPC): lo que les hace a los NPC. Devuelve los rebotes del espejo."""
    nom, aquien, efecto = NPC_ITEM.get(ef, ("?", "yo", None))
    if aquien == "yo":
        blancos = [emisor] if emisor in s["npcs"] else []
    elif aquien == "todos":
        blancos = [x for x in s["npcs"] if x != emisor and _rival(s, x, emisor)]
    else:
        blancos = [destino] if destino in s["npcs"] else []
    rebotes = []
    for b in blancos:
        p = s["npcs"][b]
        if efecto is None:
            continue
        que = efecto[0]
        if aquien != "yo":                                  # un ataque: ¿lo para algo?
            if p["inmune"] > seq:
                log("LOBBY", f"  🤖 NPC {b}: {nom} de {emisor} — inmune, no le hace nada")
                continue
            if p["escudo"]:
                p["escudo"] = False
                log("LOBBY", f"  🤖 NPC {b}: {nom} de {emisor} — lo paró el escudo")
                continue
            if p["espejo"] and aquien == "uno":
                p["espejo"] = False
                rebotes.append((b, emisor, ef))
                log("LOBBY", f"  🤖 NPC {b}: {nom} de {emisor} — ¡lo devolvió el espejo!")
                continue
            p["recibidos"] += 1
        if que == "frena":                                  # pega cuando llega (el vuelo), ver _golpes
            p.setdefault("golpes", []).append({"en": seq + efecto[3], "perdida": float(efecto[1]),
                                               "pausa": efecto[2], "aviso": efecto[4], "id": ef})
        elif que == "falla":
            p["falla"] = (efecto[1], seq + efecto[2])
        elif que == "impulso":
            p["rampas"].append((seq, NPC_IMPULSO, NPC_IMPULSO_DURA))
            if ef == 16:
                p["inmune"] = max(p["inmune"], seq + NPC_IMPULSO_DURA)
        elif que == "inmune":
            p["inmune"] = seq + efecto[1]
        elif que == "escudo":
            p["escudo"] = True
        elif que == "espejo":
            p["espejo"] = True
        elif que == "auto":
            p["auto"] = seq + efecto[1]
        elif que == "curar":
            # corta lo que lo está frenando AHORA (lo ya perdido no se devuelve) y la interferencia
            p["rampas"] = [r if r[1] > 0 or seq - r[0] >= r[2] else
                           (r[0], r[1] * max(0, seq - r[0]) / r[2], max(1, seq - r[0])) for r in p["rampas"]]
            p["falla"] = (1.0, 0)
        if aquien != "yo":
            log("LOBBY", f"  🤖 NPC {b}: le pegó {nom} de {emisor}")
    return rebotes


def _golpes(s, seq):
    """Los ítems que LLEGAN en este tramo (ya volaron): lo que pierde, el silencio y el `0x06` del hielo, como un
    jugador (medido, ver la cabecera). Devuelve [(sub, A, B, nombre)]."""
    salida = []
    for sl, p in sorted(s["npcs"].items()):
        quedan = []
        for g in p.get("golpes", []):
            if g["en"] > seq:
                quedan.append(g)
                continue
            p["rampas"].append((g["en"], -g["perdida"], 1))
            p["pausa_hasta"] = max(p.get("pausa_hasta", 0), g["en"] + g["pausa"])
            if g["aviso"]:
                salida.append((0x06, (g["id"] << 16) | (sl << 8), seq & 0xFFFF, f"al NPC {sl} le pegó el ítem {g['id']}"))
            log("LOBBY", f"  🤖 NPC {sl}: llegó el {NPC_ITEM[g['id']][0]} (−{g['perdida']:.0f}, callado "
                         f"{g['pausa'] / 60:.1f} s{', manda 0x06' if g['aviso'] else ''})")
        p["golpes"] = quedan
    return salida


def _items(s, seq):
    """Un tramo de los ítems de los NPC: agarrar las cajas que ya alcanzaron, y usar lo que tienen listo.
    Devuelve los `FF4E 0x01` a mandar: [(0x01, A, B, nombre)]."""
    salida = []
    corren = _corriendo(s)
    for sl, p in sorted(s["npcs"].items()):
        if (corren is not None and sl not in corren) or p.get("fin") is not None:
            continue                                        # relevo: el que espera no agarra ni usa nada
        t = seq + _ventaja(p, seq)
        cajas = []
        if s["cajas"]:                                      # relevo: las cajas que avisó el humano (0x66)
            while p["caja"] < len(s["cajas"]) and s["cajas"][p["caja"]] <= t:
                cajas.append(s["cajas"][p["caja"]])
                p["caja"] += 1
        else:                                               # solo / equipo: el 0x66 no viaja ⇒ a su ritmo
            if p["prox_caja"] is None:
                p["prox_caja"] = t + NPC_CAJA_CADA * random.uniform(0.3, 1.0)
            while p["prox_caja"] <= t:
                cajas.append(p["prox_caja"])
                p["prox_caja"] += NPC_CAJA_CADA * random.uniform(0.6, 1.4)
        for t_caja in cajas:
            if random.random() >= p["acierto"]:
                continue                                    # falló esa nota: se la perdió, como un jugador
            ef = _sortear(s, sl, seq, t_caja)
            if len(p["items"]) >= NPC_CASILLEROS:
                p["items"].pop(0)                           # lleno: se pierde el más viejo (0x504664)
            lo, hi = NPC_ITEM_ESPERA[NPC_ITEM.get(ef, ("", "yo"))[1]]
            p["items"].append({"id": ef, "listo": seq + random.randint(lo, hi)})
            log("LOBBY", f"  🤖 NPC {sl} agarró una caja: {NPC_ITEM.get(ef, ('?',))[0]} ({ef})")
        if p["items"] and p["items"][0]["listo"] <= seq:
            ef = p["items"].pop(0)["id"]
            p["usados"] += 1
            aquien = NPC_ITEM.get(ef, ("", "yo"))[1]
            destino = sl
            if aquien == "uno":
                orden = _corredores(s, seq)
                i = next(k for k, (_, x) in enumerate(orden) if x == sl)
                adelante = [x for _, x in orden[:i][::-1] if _rival(s, x, sl)]
                atras = [x for _, x in orden[i + 1:] if _rival(s, x, sl)]
                destino = (adelante or atras or [sl])[0]
            salida.append((0x01, (destino << 24) | (sl << 16) | (ef << 8), 0, f"ítem {ef} del NPC {sl} a {destino}"))
            log("LOBBY", f"  🤖 NPC {sl} usó {NPC_ITEM.get(ef, ('?',))[0]} ({ef})"
                         + (f" contra {destino}" if aquien == "uno" else " (a todos)" if aquien == "todos" else ""))
            for de, a, r in _recibir(s, sl, destino, ef, seq):     # el espejo de un NPC le devuelve el ítem al que lo tiró
                salida.append((0x01, (a << 24) | (de << 16) | (r << 8), 0, f"espejo del NPC {de} a {a}"))
    return salida


def filas_del_cartel(rid, ya, fila_ref):
    """Las filas de los NPC para el cartel. La llegada: la del humano corrida por la diferencia de ventaja (la suya =
    lo que mandó de más en A, o sus impulsores × NPC_IMPULSO si su A es puro tiempo). `ya` = asientos con fila."""
    if not CHASE_NPC_REALISTA:
        return []
    with _lock:
        s = _SIM.get(rid)
        if not s:
            return []
        perfiles = dict(s["npcs"])
        h = dict(s["humano"])
        seq = s["seq"] or 0
    v_hum = h["A_menos_seq"] if abs(h["A_menos_seq"]) > 5 else h["impulsos"] * NPC_IMPULSO
    out = []
    for sl, p in sorted(perfiles.items()):
        if sl in ya:
            continue
        frame = max(1, int(round(fila_ref["frame"] + v_hum - _ventaja(p, seq + NPC_IMPULSO_DURA))))
        # la precisión es el JUICIO de cada nota (perfecto/genial…), no el acierto: la del humano medido fue 79,5 %
        # con combo 96 ⇒ va por su nivel, 72…98 %, y cada corte de combo resta un poco
        pd = max(60.0, min(99.9, 72 + 26 * p["nivel"] + random.gauss(0, 2) - 0.4 * p["tropiezos"]))
        out.append({"slot": sl, "frame": frame, "combo": max(1, p["combo_max"]), "pd": int(pd),
                    "star": max(0, min(100, int(pd) + random.randint(-6, 2))),
                    "coin": 20 + 8 * p["impulsos"] + random.randint(0, 10),
                    "exp": max(1, int(fila_ref.get("exp", 1000) * (0.8 + 0.25 * p["nivel"]))),
                    "perdio": False, "usn": None, "fallo": False,
                    "milesimas": int((pd - math.floor(pd)) * 1000)})
    if out:
        log("LOBBY", f"  🤖 NPC en el cartel (humano: {h['impulsos']} impulsores, A−seq {h['A_menos_seq']:+.1f}): "
            + " · ".join(f"slot {f['slot']} frame {f['frame']} pd {f['pd']} combo {f['combo']}" for f in out))
    return out


_CAPTURA = None


def anotar_ff4e(st, sub, A, B):
    """⛔ LOCAL: cada FF4E de un jugador en carrera a `_trabajo/logs/ff4e_carrera.jsonl` (para medir qué manda un
    cliente cuando le pega un ítem). Una línea por aviso: hora, sala, asiento, sub, A, B (y A como float)."""
    global _CAPTURA
    if not CHASE_NPC_REALISTA:
        return
    import json
    import os
    import time
    from .ajustes import _DIR_SERVIDOR
    if _CAPTURA is None:
        d = os.path.join(os.path.dirname(_DIR_SERVIDOR), "_trabajo", "logs")
        os.makedirs(d, exist_ok=True)
        _CAPTURA = os.path.join(d, "ff4e_carrera.jsonl")
    fila = {"t": round(time.time(), 3), "sala": getattr(st, "room_id", None), "slot": getattr(st, "room_slot", None),
            "sub": sub, "A": A & 0xFFFFFFFF, "B": B & 0xFFFFFFFF,
            "Af": round(struct.unpack("<f", struct.pack("<I", A & 0xFFFFFFFF))[0], 2)}
    with _lock:
        with open(_CAPTURA, "a", encoding="utf-8") as f:
            f.write(json.dumps(fila) + "\n")


def _anotar_npc(salida, efectos):
    """⛔ LOCAL: lo que el server manda por los NPC, a la misma captura que los humanos (con "npc": true)."""
    import json
    import time
    if _CAPTURA is None:
        return
    t = round(time.time(), 3)
    filas = [{"t": t, "npc": True, "slot": sl, "sub": 5, "A": a, "B": b,
              "Af": round(struct.unpack("<f", struct.pack("<I", a))[0], 2)} for sl, a, b in salida]
    filas += [{"t": t, "npc": True, "slot": (a >> 8) & 0xFF if sub in (0x06, 0x64) else (a >> 16) & 0xFF,
               "sub": sub, "A": a, "B": b} for sub, a, b, n in efectos]
    try:
        with open(_CAPTURA, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in filas))
    except Exception:                                        # noqa: BLE001
        pass


def olvidar(rid):
    with _lock:
        _SIM.pop(rid, None)
