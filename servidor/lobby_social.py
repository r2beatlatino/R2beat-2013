# -*- coding: utf-8 -*-
r"""
lobby_social.py — AMIGOS (paso 1 del sistema social).

★★★ POR QUÉ EXISTE, Y POR QUÉ AHORA
================================================================================
En el log de prod había **509 solicitudes de amistad sin contestar**, con el nick en claro
adentro del paquete:

    inner FF40 len=13 : 1d 00 00 00 00 07 4a 55 47 41 44 4f 52     "JUGADOR"     ×40
    inner FF40 len=12 : 1d 00 00 00 00 06 4a 55 47 41 44 41        "JUGADA"    ×31
    inner FF40 SIN handler

★ Las repeticiones son la misma persona haciendo clic una y otra vez porque no pasa nada.
⚠ Y notar que **el `uid` llega en CERO**: el cliente no lo sabe. **El nick es lo que vale.**

El mapa completo del subsistema está en `documentacion/SOCIAL_MAPA_2013.md`.

⛔⛔ LO QUE **NO** SE PUEDE HACER: COPIAR EL `lobby_social.py` DEL CBT
================================================================================
El cliente 2013 es un superconjunto del CBT (55 subtipos de FF40 contra 39), pero **trece
subtipos cambiaron de forma**. Los que nos tocan acá:

| S2C | CBT | 2013 | ⚠ |
|---|---|---|---|
| `0x01` | acciones 3/4/8 van **sin nick** | acciones 2,3,4,8,9,0xA **leen `[u8 len][nick]`** | ⛔ mandar `[01][04]` pelado deja al cliente leyendo basura |
| `0x1D` | `[u32 uid][u8 tipo][u8 len][nick]` | **igual** | ✅ |
| `0x1E` | `[u8 acción][u8 len][nick]` | **`[u32]` ADELANTE** | ⛔ +4 bytes |
| `0x1F` | `[u8 flag][u32 uid]` | **igual** | ✅ |
| `FF42` | `[u16 count]` + amigos | **TRES listas**: BUDDYGROUP, BLOCK, y recién ahí los amigos | ⛔ el del CBT desincroniza en la 1ª entrada |

⇒ Del CBT se porta **la lógica** (quién avisa a quién, el alta mutua, los códigos de error
   confirmados en vivo). Los **bytes** son los del 2013, medidos.

★ El orden de los subtipos NO significa lo mismo en las dos direcciones. Ya mordió dos veces en
  el CBT. Acá cada builder dice explícitamente si es C2S o S2C.
"""
import struct

from .ajustes import (
    MEGAFONO_ACTIVO,
    MEGAFONO_LARGO_MAX,
    AMIGOS_AVISO_DE_SALA,
    AMIGOS_BYTE_ESTADO,
    AMIGOS_EMPUJAR_LISTA,
    AMIGOS_LISTA_EN_FF42,
    AMIGOS_MANDAR_SERVIDOR,
    AMIGOS_SERVIDOR_DESCONECTADO,
    AMIGOS_TOPE,
    CANALES_2013,
    SALA_VESTIBULO,
)
from .basedatos import (
    db_agregar_amigo,
    db_amigos,
    db_borrar_amigo,
    db_get_char,
    db_son_amigos,
    db_uid_por_nick,
    db_uids_por_nick,
)
from .paquetes import grupo_de_licencia
from .registro import log
from .salas import CONEXIONES, SALAS_VIVAS


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Ayudas
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _txt(s):
    """Al cable los nombres van en cp1252, como en todo el resto del server (`FF08`, `FF77`, …)."""
    return (s or "").encode("cp1252", "replace")[:0xFF]


def _txt2(s):
    """Igual que `_txt` pero para el MENSAJE, cuyo largo viaja en u16 (no en u8)."""
    return (s or "").encode("cp1252", "replace")[:0xFFFF]


def _nick_de(usn):
    return (db_get_char(usn) or {}).get("nick", "") or f"P{usn}"


def _mi_usn(st):
    return int(getattr(st, "usn", 0) or 0)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# S2C — los paquetes que mandamos. Layouts MEDIDOS sobre el cliente 2013.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _s2c_resultado(accion, nick=""):
    """FF40 `0x01` — resultado de una operación de amistad. Handler `0x5EF4B3`.

    `[u8 acción]`, y según la acción:
        1                    -> `[u32 uid][u8 len][nick]`   (alta completa, con ficha)
        2, 3, 4, 8, 9, 0x0A  -> `[u8 len][nick]`
        cualquier otra       -> nada más

    ⚠⚠ ACÁ ESTÁ LA DIFERENCIA CON EL CBT. Allá las acciones de error (3/4/8) se mandaban
       **peladas** (`[01][04]`). En el 2013 esas acciones **leen un nick detrás**, así que un
       paquete pelado deja al parser leyendo lo que venga después en el buffer.
       ⇒ Por eso esta función pide `nick` siempre que la acción no sea "muda".

    Códigos, confirmados en vivo en el CBT (los textos son del `string_lt`):
        1     alta OK, aparece en la lista
        3     "no puede registrar más de 100 amigos"   (MI lista llena)
        4     "el usuario ya está en su lista de amigos"
        8     "no puede registrar a más amigos"        (la lista del OTRO llena)
        0x58  cae en el genérico: "no existe o está desconectado"
    """
    n = _txt(nick)
    if accion == 1:
        # el uid va sólo en la acción 1; el resto identifica por nombre
        raise ValueError("usá _s2c_alta() para la acción 1")
    if accion in (2, 3, 4, 8, 9, 0x0A):
        return bytes([0x01, accion & 0xFF, len(n)]) + n
    return bytes([0x01, accion & 0xFF])


def _s2c_alta(uid, nick):
    """FF40 `0x01` acción 1 — el amigo entra en la lista, con su ficha. `[01][01][u32 uid][u8 len][nick]`."""
    n = _txt(nick)
    return bytes([0x01, 0x01]) + struct.pack("<I", uid & 0xFFFFFFFF) + bytes([len(n)]) + n


def _s2c_evento(uid, nick, tipo=1):
    """FF40 `0x1D` — evento asíncrono. Handler `0x5EF1C9`. `[1D][u32 uid][u8 tipo][u8 len][nick]`.

    ★★ LOS TIPOS, LEÍDOS RAMA POR RAMA (tabla `0x5F31E4`, el índice es **`tipo − 1`**):

        tipo 1  `0x5EF22A`  ⚠ **DOS COSAS según el estado del cliente**:
                              ¿ya está en su lista? (`0x45C770`)
                                 NO -> `0x45B8F0` = ★ el cartel **«Sé Mi Amigo»** (Añadir/No)
                                 SÍ -> texto #105 *"%s ha sido registrado como amigo."*
                            ⇒ **es el cartel de SOLICITUD**, no un insert silencioso.
        tipo 2  `0x5EF2A8`
        tipo 5  `0x5EF2FE`  sólo dibuja: texto #416 *"%s está listo en la lista de amigos."*
        tipo 6, 7           no-op (saltan al epílogo)

    ⛔ Acá decía que el tipo 1 *"inserta sin cartel"*. **Falso, y costó el bug de la solicitud
      repetida** (2026-09-11): mandarlo al aceptar le volvía a preguntar al que ya había dicho
      que sí. Saber a qué dirección salta un tipo **no es** saber qué hace: hay que leer la rama.
    """
    n = _txt(nick)
    return bytes([0x1D]) + struct.pack("<I", uid & 0xFFFFFFFF) + bytes([tipo & 0xFF, len(n)]) + n


def _s2c_respuesta(uid, accion, nick):
    """FF40 `0x1E` — respuesta a una solicitud. Handler `0x5EF381`.

    ⛔ **`[1E][u32][u8 acción][u8 len][nick]`** — el 2013 lee **un `u32` ADELANTE** que el CBT no
       tiene. Con el layout viejo el cliente toma el 1er byte del uid como la acción.
    Acciones vistas: 6, 7, 9. La 9 es la del cartel *"%s ha rechazado unirse como su amigo"*.
    """
    n = _txt(nick)
    return (bytes([0x1E]) + struct.pack("<I", uid & 0xFFFFFFFF)
            + bytes([accion & 0xFF, len(n)]) + n)


def _s2c_quitar(uid):
    """FF40 `0x1F` — sacar a alguien de mi lista. Handler `0x5EF177`.

    `[1F][u8 flag][u32 uid]` — ★ el flag va **ANTES** del uid, al revés que el C2S `0x1F`.
    Sirven el flag 1 y el 3. ✅ Idéntico al CBT.
    """
    return bytes([0x1F, 0x01]) + struct.pack("<I", uid & 0xFFFFFFFF)


def _servidor_de(uid):
    """El u16 que el cliente dibuja como **"Servidor N"** — o `0xFFFF` = **"No conectado."**

    ★★★★★ MEDIDO EN `0x459110` (el que arma el panel del amigo), 2026-09-10:

        ecx = 0xFFFF
        cmp word [amigo+0x0a], cx
        jne  -> texto #29 "Servidor %d"  (formateado con ese mismo u16)
        je   -> texto #77 "No conectado."

    Y el constructor de la entrada (`0x45FD50`) inicializa ese campo **justo en `0xFFFF`**:
    el propio cliente arranca a todos como desconectados. Dos fuentes independientes.

    ⛔ Lo que hacíamos antes era mandar **0**, que el cliente lee como *"Servidor 0"* ⇒ todos
      conectados siempre. Era el síntoma que reportó anonimo03.

    ★★ El NÚMERO es el índice 0-based de `CANALES_2013`, que es **el mismo `idx` con el que le
      publicamos la lista de canales** (`paquetes._entrada_canal`). Mandando índice+1 el
      renglón salía EN BLANCO: estaba en 'Libre' = 9 y le mandábamos 10, que no existe.
    """
    if not AMIGOS_MANDAR_SERVIDOR:
        return 0
    _c = CONEXIONES.get(uid)
    if _c is None or getattr(_c, "cerrado", False):
        return AMIGOS_SERVIDOR_DESCONECTADO
    _clave = getattr(_c, "canal", None)
    for _i, _cn in enumerate(CANALES_2013):
        if _cn[4] == _clave:
            return _i
    return 0        # conectado pero sin canal reconocible: mejor el 1º que "No conectado"


def _sala_de(uid):
    """El COMPAÑERO del servidor: en qué sala está el amigo. Va a `amigo+0x08`.

    ★★ Los dos viajan JUNTOS al panel (`0x459110`, el mismo que dibuja "Servidor %d"):

        0x459267   edx = word [amigo+0x08]      ← la sala
        0x45926b   eax = word [amigo+0x0a]      ← el servidor
        0x459277   call 0x44D480(servidor, sala)

    ⇒ La "ubicación" que anonimo03 vio en la captura del referente (*canal + número de sala*) es
      ESTE par. El servidor ya lo mandábamos bien desde el arreglo de la presencia; esto es
      la otra mitad.

    ★★★ LOS CENTINELAS, MEDIDOS EN `0x44C740` (el que arma el renglón), 2026-09-11:

        servidor == 0xFFFF   ->  texto #77   "No conectado."
        sala     == 0xFFFF   ->  texto #30   "vestíbulo"          ← EL LOBBY
        sala     == 0xFFFE   ->  texto #101  "Juego Personal"
        cualquier otra       ->  texto #82   "Sala No. %d"

    ⛔ MANDÁBAMOS 0, y el 0 no es ninguno de los tres ⇒ salía **"Sala No. 0"** para todo el que
      estuviera en el lobby. Lo reportó anonimo03: *"cuando X amigo está en libre sale «está en sala
      0», pero debería decir «lobby»"*.

    ⚠⚠ Y ACÁ ME EQUIVOQUÉ ANTES, vale anotarlo: puse el 0 razonando que era "el default del
      propio cliente" porque el constructor (`0x45FD50`) deja ese campo en cero. **El valor con
      el que un constructor inicializa un campo NO es el centinela del campo.** El cero nunca se
      veía sólo porque el otro centinela (servidor=0xFFFF) gana antes en la cascada. Una
      inferencia razonable y igual equivocada; la respuesta estaba en la función que dibuja.

    ★★★ 2026-09-11 — Y NO ES UN NÚMERO PELADO: es el **`A` empaquetado** de la lista de salas,
      `A = (TIPO << 11) | número`. Lo destapó el botón «Jugar Juntos», que no hacía nada.

        0x44C530   ax >> 11        -> el TIPO, contra el mío  ([0x9314c0]+0x957c ^ 0xEF)
                   eax & 0x7FF     -> el NÚMERO, contra el mío ([0x9314c0]+0x9508)
        0x44C596   cmp ax,5 / jb   -> ⛔ **el tipo 0 se descarta**: sólo los tipos 5..12 valen

    ⛔ Mandábamos el `room_id` sin el tipo ⇒ el cliente leía **tipo 0** para todos los amigos, y
      el tipo 0 cae en la rama que descarta. Por eso «Jugar Juntos» no podía funcionar nunca,
      ni siquiera con el `FF41` contestado.

    ★ Y no es una lectura nueva: es **el mismo formato** que `paquetes.build_ff6e_roomlist` arma
      desde el 2026-08-05 (`a = (roomid & 0x7FF) | (A_alto << 11)`). El dato estaba medido hace
      un mes en el módulo de al lado; acá se mandaba a medias.

    ⚠ Los tipos 5..12 son `TIPOS_LUGAR_CHARLA` — los mismos que ya creamos al arrancar. Dos
      fuentes independientes dando el mismo conjunto.
    """
    if not AMIGOS_MANDAR_SERVIDOR:
        return 0
    _c = CONEXIONES.get(uid)
    if _c is None or getattr(_c, "cerrado", False):
        return SALA_VESTIBULO
    # ★ Los lugares persistentes (charla, casa, isla…) YA guardan su `A` armado, con el tipo en
    #   los bits altos: es el mismo número que el cliente nos mandó en el `FF11` para entrar.
    #   Se usa tal cual, sin recalcularlo — ver `lobby_salas.py:379`.
    _a = getattr(_c, "lugar_a", None)
    if _a:
        return int(_a) & 0xFFFF
    try:
        _r = int(getattr(_c, "room_id", 0) or 0)
    except (TypeError, ValueError):
        _r = 0
    if not _r:
        return SALA_VESTIBULO
    # Sala de juego normal: el tipo va en `A_alto`, que hoy es 0 para todas las que creamos.
    _s = SALAS_VIVAS.get(_r) or {}
    _alto = int(_s.get("A_alto", 0) or 0) & 0x1F
    return ((_alto << 11) | (_r & 0x7FF)) & 0xFFFF


def _s2c_ficha(uid, nick, exp=0, licencia=0):
    """FF40 `0x02` — **la FICHA del amigo**, la respuesta al C2S `0x01`. Handler `0x5EF748`.

        [02][u8 sel=1][u32 uid][u8 len][nick]
            [u32][u16][u32][u16][u16][u32][u32]      ← 22 B  [NM]
            [u8][u8][u8][u8]                          ←  4 B  [NM]
            [u8 len2][str2][u8]                       ← un 2º texto, hoy vacío

    ★★ CÓMO SE ENCONTRÓ (2026-09-10). anonimo03: *"al consultar su info sale «este ya es tu amigo»,
       como si estuviera presionando otra función"*. Y tenía razón: **el botón de la ficha manda
       el sub `0x01`**, que nosotros tratábamos como "agregar por nick" y contestábamos con el
       error 4 = *"el usuario ya está en su lista de amigos"*. Ése era el cartel.

       En el log se ve clarísimo:
           21:57:01  inner FF40 : 01 0b "jugador2"
           21:57:01  ★ AMIGOS usn=11162 pidió a 'jugador2' -> YA son amigos

    ⇒ Al `0x01` hay que contestarle el `0x02`. Verificado por dos caminos que coinciden:
        · el exe (`0x5EF748`): las 17 lecturas en el orden de arriba;
        · la captura del referente que trajo anonimo03:
              02 01 a8050000 06 "asdfff" 00…
      ⚠ La captura no decide: vale porque **coincide con el binario**.

    ⚠ [NM] Los campos del medio están medidos en TAMAÑO, no en significado. Van en cero, salvo
      la exp, que es el único que sabemos. Después de esto el cliente pide el `FF77`, que ya
      contestamos — ahí va el grueso de lo que se ve en pantalla.
    """
    n = _txt(nick)
    p = bytes([0x02, 0x01]) + struct.pack("<I", uid & 0xFFFFFFFF) + bytes([len(n)]) + n
    # ★★★★★ EL ÍCONO DE LA LICENCIA — MEDIDO EL 2026-09-11 sobre `0x484A40`, la función que
    #   el propio handler de la ficha llama con TRES de estos campos:
    #
    #       0x484A40(grupo_u16, exp_u32, licencia_u8):
    #           nivel = cuántos umbrales de 0x8782A8 son <= exp      (la tabla de siempre)
    #           banda = 1
    #           nivel >= 11                                  -> 2
    #           nivel >= 20  y (licencia & 1)                -> 3    (Estrella)
    #           nivel >= 30  y grupo >= 0x0010               -> 4
    #           nivel >= 40  y grupo >= 0x0010 y (lic & 2)   -> 5    (Luna)
    #           nivel >= 60  y grupo >= 0x0100               -> 6
    #           nivel >= 70  y grupo >= 0x0100 y (lic & 4)   -> 7    (Sol)
    #
    #   ★★ Los dos umbrales —**0x0010 y 0x0100**— son EXACTAMENTE los dos valores que devuelve
    #      `paquetes.grupo_de_licencia`, que ya teníamos medido para el `FF0C` de las salas. Dos
    #      caminos independientes que caen en los mismos dos números: eso es identificación, no
    #      coincidencia. Y confirma la regla vieja: **la licencia sola no alcanza, hace falta el
    #      grupo de misión al lado** (ver `un-campo-solo-no-prueba-nada`).
    #
    #   ⛔ Los dos iban en CERO. anonimo03 mandó dos capturas del mismo perfil —el suyo y el que ve
    #      su amigo— y el ícono del 82 era **rombo rojo** en el suyo y **estrella dorada** en el
    #      del amigo. Con licencia=0 y grupo=0 la cascada se frena en la banda 2, que es
    #      justamente la estrella dorada. El síntoma cuadra byte por byte con el disasm.
    p += struct.pack("<I", exp & 0xFFFFFFFF)                          # -> arg2: la EXP
    p += struct.pack("<H", grupo_de_licencia(licencia) & 0xFFFF)      # -> arg1: el GRUPO
    # ★★ LOS DOS u16 SON LA UBICACIÓN, igual que en la lista — y van CRUZADOS respecto del
    #    orden en que se mandan: el cliente lee primero `@+76` y después `@+72`, pero guarda
    #    `@+76` -> `amigo+0x0a` (SERVIDOR) y `@+72` -> `amigo+0x08` (SALA).
    #  ⛔ La sala iba en cero acá, y esta ficha PISA lo que había mandado la lista: abrir
    #    "ver info" borraba la sala del amigo. Por eso la ubicación no cargaba aunque la lista
    #    la mandara bien (2026-09-11, síntoma de anonimo03).
    p += (struct.pack("<I", int(licencia or 0) & 0xFF)   # -> arg3: LA LICENCIA (0/1/3/7)
          + struct.pack("<H", _servidor_de(uid))      # -> amigo+0x0a  (el "Servidor N")
          + struct.pack("<H", _sala_de(uid)))         # -> amigo+0x08  (la sala)
    p += struct.pack("<I", 0) + struct.pack("<I", 0)
    p += bytes([0, 0, 0, 0])
    p += bytes([0])            # len2 = sin segundo texto
    p += bytes([0])            # ★ el byte final: se manda de más a propósito. Un paquete CORTO
                               #   deja al cliente leyendo basura; uno largo, sólo ignora el resto.
    return p


def _s2c_lista_amigos(usn):
    """FF40 `0x03` — **LA LISTA DE AMIGOS, empujada por el server**. Handler `0x5EF992`.

    ★★★ POR QUÉ ES ÉSTE Y NO EL `FF42` — MEDIDO EL 2026-09-10, EN EL LOG.
        anonimo03 probó y la lista no se poblaba. Contando en el log de la sesión entera:

            FF42 pedido por el cliente:  **0 veces**

        El `FF42` es un cargador perezoso que en el 2013 **no se dispara** en los caminos que la
        gente usa. ⇒ Si el server no empuja la lista, **nadie le dice nunca al cliente quiénes
        son sus amigos**, por más que estén guardados en la base. Eso explica el síntoma exacto:
        el alta funcionaba, la base quedaba bien, y la ventana seguía vacía.

    LAYOUT — cada `read()` verificado instrucción por instrucción sobre `0x5EF992`:

        [u16 cabecera]
        [u8 cuantos]
            por cada amigo:
                [u32 uid][u8 ?][u8 ?][u32 exp][u8 len][nick]
                [u8 ?][u16 ?][u16 ?][u8 ?][u8 ?][u8 ?][u16 ?][u8 ?]
        [u8 countB]          ← segunda lista (0x5EFB6E)
        [u8 countC]          ← tercera lista

    ⚠ [NM] Los campos marcados `?` están medidos **en tamaño, no en significado**. Van en cero.
      En el CBT los equivalentes eran "color/online", "exp" y "ubicación", así que alguno de
      éstos probablemente sea el punto verde de conectado — pero **no está comprobado**, y un
      número inventado es peor que un cero: se vuelve un dato falso que después nadie cuestiona.

    ⚠⚠ Y el aviso serio: hoy mismo un paquete mal armado **mató al cliente** (el techo de 4096 del
      `FF57`). Este paquete se arma con los tamaños leídos del binario, pero si algo sale raro
      **se apaga con `AMIGOS_EMPUJAR_LISTA = False`** y se vuelve al estado anterior.
    """
    amigos = db_amigos(usn) if AMIGOS_EMPUJAR_LISTA else []
    amigos = amigos[:0xFF]                       # el contador es de 1 byte

    p = bytes([0x03])
    p += struct.pack("<H", 0)                    # cabecera [NM]
    p += bytes([len(amigos)])
    for ch in amigos:
        n = _txt(ch.get("nick", ""))
        _uid_amigo = int(ch.get("uid", 0))
        # ★★ EL EXPERIMENTO DE LOS DOS BYTES (2026-09-10). anonimo03 probó y la lista YA SE VE, pero
        #    al pedir la ficha sale el cartel equivocado y **el susurro no manda nada**: el cliente
        #    ni siquiera emite el paquete. Eso significa que decide LOCALMENTE que no se puede —
        #    y el sospechoso son estos dos bytes, que hasta ahora iban en cero.
        #    En el CBT el byte de esta posición era "color/online" de la fila.
        #  ⇒ Mandamos **1 al que está conectado** y 0 al que no. Es un dato REAL, no un relleno:
        #    si acierta, el susurro y la ficha se destraban solos; si no, no empeora nada.
        #  ⚠ Cuál de los dos bytes es, NO está medido. `AMIGOS_BYTE_ESTADO` elige: 1 = el primero,
        #    2 = el segundo, 3 = los dos, 0 = ninguno (vuelve al comportamiento anterior).
        _con = 1 if _uid_amigo in CONEXIONES else 0
        _b1 = _con if AMIGOS_BYTE_ESTADO in (1, 3) else 0
        _b2 = _con if AMIGOS_BYTE_ESTADO in (2, 3) else 0
        p += struct.pack("<I", _uid_amigo & 0xFFFFFFFF)
        p += bytes([_b1, _b2])
        p += struct.pack("<I", int(ch.get("exp", 0)) & 0xFFFFFFFF)    # exp: el único que sí sabemos
        p += bytes([len(n)]) + n
        # ★★★★★ EL PRIMER u16 DE ACÁ ES LA PRESENCIA (medido 2026-09-10). Va a `amigo+0x0a`, y
        #    `0xFFFF` es lo que hace salir **"No conectado."** en vez de *"Servidor N"*.
        #    Ver `_servidor_de` para las dos mediciones que lo prueban.
        #  ⚠ Los reads de este handler son de DOS bytes, no de uno: arranca con `mov ebp,2`
        #    (`0x5ef992`) y `push ebp` son 2. Son 22+nick por amigo. Si alguien "corrige" esto a
        #    19+nick creyendo que ebp vale 1, la lista se desfasa del 2º amigo en adelante.
        p += bytes([0])
        p += struct.pack("<H", _servidor_de(_uid_amigo))              # ★ presencia -> amigo+0x0a
        # ⚠ Este u16 el cliente lo lee en el MISMO hueco de pila que el de abajo y después lo
        #   PISA: al guardar toma el segundo. O sea que lo que se mande acá no llega a ningún
        #   lado. Va en cero y así queda anotado, para que nadie lo use creyendo que sirve.
        p += struct.pack("<H", 0) + bytes([0, 0, 0])                  # [NM]
        p += struct.pack("<H", _sala_de(_uid_amigo)) + bytes([0])     # ★ la sala -> amigo+0x08
    # ★★★★★ LA SEGUNDA LISTA ES LA DE LOS AMIGOS DEL ALMA — 2026-09-15.
    #
    #   ⛔ Iba en CERO desde siempre, con el comentario *"la segunda lista, vacía"*. Y era **la
    #     forma nativa** de poblar «Amigo de Alma» que anonimo03 insistió en que tenía que existir:
    #     *"si la maquinaria ya funciona en vivo, hay forma nativa de lograrlo"*. Tenía razón.
    #
    #   ★★ SIN CARTEL, que es lo que la hace la buena. El insertador de esta lista es `0x45F240`,
    #     y **no llama a `0x4214C0`** (el que dibuja el cartel) — al revés que los subtipos
    #     `0x02`/`0x24` del `FF40 0x3B`, que lo arrastran pegado a la rama.
    #
    #   ★★★ Y TRAE LAS DOS COSAS QUE FALTABAN, medidas en `0x45F240`:
    #
    #         0045f315  mov  ecx, [esi-4]        ; ★ LA JOYA
    #         0045f31f  call 0x50F4B0            ;   ¿existe en la tabla de ítems?
    #         0045f328  je   0x45f3c0            ;   ⛔ si NO -> se va SIN insertar la fila
    #         0045f32e  cmp  byte [esi], 0       ; ★ el ESTADO
    #         0045f334  sete dl
    #         0045f337  add  dl, 0xf             ; ★★ dl = 15 si ≠0 · 16 si ==0
    #         0045f348  call 0x45FD50            ;   crea la entrada con ESA categoría
    #         0045f36e  add  ecx, 0x988          ;   la MISMA lista donde vive el alma
    #
    #     y **15 y 16 son exactamente las dos categorías del amigo del alma** (`0x45F430` usa las
    #     mismas). ⇒ el 15 es *"conectado"*, y encima está en la lista de valores que destraban
    #     el susurro (`{1,3,4,5,6,15,24}`) — el 16 no.
    #
    #   ★ El parser de esta lista (`0x5EFBA7`) arma el struct con **`0x5C5140`**, que es el MISMO
    #     constructor que usan las ramas del `0x3B`. Ésa es la prueba de que las dos rutas llenan
    #     la misma estructura: no es parecido, es la misma.
    #
    #   ⚠⚠ EL CAMPO DE ESTADO ES CONDICIONAL: `0x5EFC13 cmp byte […],1 / jne` ⇒ **si va en 1 hay
    #     que mandar TRES campos más** (`[u8][u8][u32]`), y si va en 0 **no**. Mandar de más o de
    #     menos corre todo lo que el cliente lee después.
    try:
        from .ajustes import AMIGO_DEL_ALMA
        from .basedatos import db_almas_de
        _almas = list(db_almas_de(usn) or []) if AMIGO_DEL_ALMA else []
    except Exception:                                                 # noqa: BLE001
        _almas = []
    p += bytes([len(_almas) & 0xFF])                                  # countB
    for _al in _almas:
        _ou = int(_al.get("otro_uid") or 0)
        _on = _nick_de(_ou).encode("cp1252", "replace")[:0x1E]
        _vivo = 1 if CONEXIONES.get(_ou) is not None else 0
        p += struct.pack("<I", _ou & 0xFFFFFFFF)     # struct+0x00  [NM] — va el uid
        p += bytes([len(_on)]) + _on                 # struct+0x04  ★ el NOMBRE
        p += bytes([0xFF])                           # struct+0x34  [NM] — `0x5C5140` lo deja en 0xFF
        # ⚠ La JOYA tiene que ir de verdad: `0x45F328` descarta la fila si el ítem no existe en
        #   la tabla del cliente. Con 0 no se inserta nada, **y sin ningún aviso**.
        p += struct.pack("<I", int(_al.get("joya") or 0) & 0xFFFFFFFF)  # ★★ LA JOYA
        p += bytes([_vivo])                          # ★★★ 1 -> categoría 15 (encendido)
        if _vivo:
            p += bytes([0, 0]) + struct.pack("<I", 0)  # [NM] — sólo existen si el estado es 1
    p += bytes([0])          # countC — la tercera, vacía
    return p


def enviar_lista_de_amigos(st, motivo=""):
    """Le empuja al cliente su lista de amigos. Se llama al entrar y cada vez que cambia."""
    if not AMIGOS_EMPUJAR_LISTA:
        return
    _usn = _mi_usn(st)
    _p = _s2c_lista_amigos(_usn)
    st.send_ff55(0x40, _p, name=f"FF40/0x03 lista de amigos: {_p[3]}"
                              + (f" ({motivo})" if motivo else ""))
    log("LOBBY", f"  ★★ AMIGOS lista empujada a usn={_usn}: {_p[3]} amigo(s)"
                 + (f" — {motivo}" if motivo else ""))


def presencia_al_entrar(st, motivo="al entrar"):
    """Me empuja mi lista y le avisa a mis amigos que estoy. **Idempotente por conexión.**

    ★★★ POR QUÉ EXISTE — MEDIDO EL 2026-09-11, con el síntoma de anonimo03:
        *"cuando mi amigo cambia de canal, aparece como desconectado"*.

        01:10:56   ★ AMIGOS — "un amigo se fue"     ← el aviso de baja SÍ sale
        01:10:56   conexión usn=5980 dada de baja
        01:10:57   conexión nueva -> canal 'Libre'  ← volvió, en otro canal
                   ⛔ y no hay NINGÚN aviso de alta. Queda desconectado para siempre.

    La causa: el alta colgaba **sólo del `FF03`**, y al cambiar de canal **el cliente no lo
    manda**. En esa reconexión mandó `FF06`, `FF8C`, `FF97`, `FF6E`, `FF49`, `FFAF`… y `FF03`
    nunca. (El `FF03` que aparece en el log de esa reconexión es un **TX nuestro**, detrás del
    `FF49`; no es el del cliente. Confundir la dirección acá cuesta el diagnóstico entero.)

    ⇒ Ahora cuelga también del **`FF06`** (`CmdJoinChannel` = *entré al canal*), que es el que
      llega en LOS DOS casos: login normal y cambio de canal.

    ⚠ Idempotente a propósito: en el login normal llegan los dos (`FF03` y después `FF06`), y
      sin la guarda mandaríamos la lista dos veces y avisaríamos dos altas por cada entrada.
      La bandera va en la CONEXIÓN, no en el usuario: una conexión nueva —que es exactamente
      lo que pasa al cambiar de canal— vuelve a anunciar, que es lo que queremos.
    """
    if getattr(st, "_amigos_anunciado", False):
        return
    st._amigos_anunciado = True
    enviar_lista_de_amigos(st, motivo)
    avisar_a_mis_amigos(st, "entró")
    # ★★ Y a la PAREJA, que tenía el mismo agujero que tuvieron los amigos: su línea sólo se
    #   llenaba cuando el cliente la pedía ⇒ si el otro entraba después, no se enteraba nunca.
    #   ⚠ Import adentro: `lobby_pareja` y `lobby_social` son hermanos.
    from .lobby_pareja import avisar_a_mi_pareja
    avisar_a_mi_pareja(st, "entró")
    # ★★ Y a los AMIGOS DEL ALMA, que tienen el mismo agujero por el mismo motivo: su fila la
    #   crea `0x45FD50`, el MISMO constructor de entrada de amigo, y nace apagada.
    #   ⇒ Tres sistemas que comparten la fila del panel comparten también cómo se enciende.
    from .lobby_alma import avisar_a_mis_almas, repoblar_almas
    # ⚠ PRIMERO la fila, DESPUÉS el foquito: la presencia enciende una fila que tiene que
    #   existir. Al revés no se rompe nada, pero el aviso cae en el vacío — que es la misma
    #   trampa de orden que nos mordió toda la sesión de pareja.
    repoblar_almas(st, " (al entrar)")
    avisar_a_mis_almas(st, "entró")
    # ★ Y al CÍRCULO (24-sep): mis compañeros me ven conectado. El GuildInfo PROPIO no va acá:
    #   el cliente lo pide solo (`FF40 0x21`) al entrar a cada canal.
    from .circulos import presencia
    presencia(_mi_usn(st), entro=True)


def avisar_a_mis_amigos(st, motivo=""):
    """Le re-manda la lista a **cada amigo mío que esté conectado**, para que mi estado se actualice.

    ★★ POR QUÉ (2026-09-10). anonimo03 lo vio jugando: *"sólo jugador2 se ve verde, el otro con fuente
       de color normal"*. La lista se empujaba **una sola vez, al entrar**, y nunca más. ⇒ cada
       cliente mostraba el estado **congelado del instante en que él entró**: el que se conectó
       después simplemente no figuraba como conectado, para siempre.

    ⇒ Se llama al ENTRAR y al SALIR. Es barato: un paquete chico, y sólo a los amigos que están
      online — a nadie más le cambia nada.

    ⚠ Le mandamos la lista entera en vez de un "fulano entró". Hay subtipos para el aviso puntual
      (el `0x04` del mapa), pero su layout **cambió respecto del CBT** y todavía no está medido.
      Re-mandar la lista es más caro y **es correcto**: deja el estado en un solo lugar, la base.
    """
    if not AMIGOS_EMPUJAR_LISTA:
        return
    _yo = _mi_usn(st)
    if not _yo:
        return
    _avisados = 0
    for _a in db_amigos(_yo):
        _c = CONEXIONES.get(int(_a.get("uid", 0)))
        if _c is not None and _c is not st:
            enviar_lista_de_amigos(_c, f"un amigo {motivo}")
            _avisados += 1
    if _avisados:
        log("LOBBY", f"  ★ AMIGOS usn={_yo} {motivo}: avisado a {_avisados} amigo(s) conectado(s)")


def _s2c_ubicacion(uid, nick, servidor, sala):
    """S2C FF40 `0x04` — **«este amigo se movió»**, el aviso puntual de UN amigo.

    ★★ Es la forma NATIVA de avisar un cambio de lugar: el cliente 2019 tiene un comando dedicado
    (`FF034 CmdUpdateFriendPlace`) y acá el camino vivo es este subtipo. Re-mandar la lista entera
    —lo que veníamos haciendo— es un atajo nuestro, no el diseño.

    ★★★ LAYOUT MEDIDO en `0x5EFD59`, quince campos, cada destino verificado (`AMIGOS_2013.md` §5.1):

        [u8 flags][u32 uid][u8][u8 len][strA ⚠ el cliente lo DESCARTA][u8][u8][u8][u32]
        [u8 len][strB = nick][u16 servidor][u16 sala][u8][u8]

    ⚠ **6 de los 15 campos son [NM]**: sé dónde están y cuánto miden, no qué significan. Van en
      CERO. No los llenes con datos plausibles sin medir: el primer byte tiene al menos un bit con
      efecto conocido (ver abajo) y los demás no se miraron.

    ★ `flags` bit `0x10` pone el estado del amigo en **15**, uno de los siete valores que destraban
      el susurro (medido). Se manda prendido para que el que se movió siga siendo "escribible":
      con 0 el estado quedaría en otro valor y podría cerrarse la compuerta del susurro.

    ⛔ El `strA` va VACÍO a propósito: está medido que el cliente lo lee y lo tira. Mandar algo ahí
      sería inventar un campo que no se usa, y alargar el paquete sin razón.
    """
    _nb = str(nick or "").encode("cp1252", "replace")[:0x1E]
    p = bytes([0x04, 0x10])                      # subtipo + flags (bit 0x10 = estado 15)
    p += struct.pack("<I", int(uid) & 0xFFFFFFFF)
    p += bytes([0])                              # [NM]
    p += bytes([0])                              # strA: largo 0 — el cliente lo descarta
    p += bytes([0, 0, 0])                        # [NM] x3
    p += struct.pack("<I", 0)                    # [NM]
    p += bytes([len(_nb)]) + _nb
    p += struct.pack("<HH", int(servidor) & 0xFFFF, int(sala) & 0xFFFF)
    p += bytes([0, 0])                           # [NM] x2
    return p


def avisar_mi_ubicacion(st, motivo=""):
    """Avisa a mis amigos conectados que **cambié de lugar** (entré o salí de una sala).

    ★★ POR QUÉ EXISTE (2026-09-12): la ubicación sólo se actualizaba al entrar o salir de un
    CANAL. Al entrar a una SALA nadie se enteraba, así que para los demás yo seguía en el
    vestíbulo — y el cliente **esconde el botón «Jugar Juntos» de quien está en el vestíbulo**
    (`0x44D480`). Ése era el *"funciona una o dos veces"* que reportó anonimo03.

    ⚠ `AMIGOS_AVISO_DE_SALA` elige el camino, y `"lista"` es la vuelta atrás probada.
    """
    if not AMIGOS_AVISO_DE_SALA:
        return
    _yo = _mi_usn(st)
    if not _yo:
        return
    _serv, _sala = _servidor_de(_yo), _sala_de(_yo)
    _nick = _nick_de(_yo)
    _n = 0
    for _a in db_amigos(_yo):
        _c = CONEXIONES.get(int(_a.get("uid", 0)))
        if _c is None or _c is st or getattr(_c, "cerrado", False):
            continue
        if AMIGOS_AVISO_DE_SALA == "fino":
            _c.send_ff55(0x40, _s2c_ubicacion(_yo, _nick, _serv, _sala),
                         name=f"FF40/0x04 {_nick!r} se movió (servidor={_serv} sala=0x{_sala:04X})")
        else:
            # ★ La red de seguridad: el camino viejo, más caro pero probado desde el 2026-09-10.
            enviar_lista_de_amigos(_c, f"un amigo {motivo}")
        _n += 1
    if _n:
        log("LOBBY", f"  ★★ AMIGOS usn={_yo} {motivo}: avisada la ubicación a {_n} amigo(s) "
                     f"(servidor={_serv} sala=0x{_sala:04X}, modo={AMIGOS_AVISO_DE_SALA!r})")


def _ff42_listas(usn):
    """`FF42` (`CmdGetAllFriendlist`) — la respuesta al pedido de "dame todo". Handler `0x5E73E0`.

    ★★ Son **TRES listas**, y los nombres salen de los logs del propio exe:

        [u8 nA]   nA × 26 bytes                       "[BUDDYGROUP] size:%u"
        [u8 nB]   nB × [u32 uid][u8 len][nick]        "[BLOCK] size:%u"
        [u16 n]   n  × [u32 uid][u8 len][nick]
                       [u8][u8][u32][u8][u32]         "CmdGetAllFriendlist size : %d"

    ⇒ El del CBT (`[u16 count]` y a los amigos de una) se lee acá como `[u8 nBuddyGroup]` y
      **desincroniza en la primera entrada**. Por eso no se porta.

    Hoy mandamos **BUDDYGROUP y BLOCK vacíos** (nA=0, nB=0): los grupos de amigos y los
    bloqueados son los pasos 8 y 9 del plan, y una lista vacía es válida y no dibuja nada.

    ⚠ [NM] Los **11 bytes de cola** de cada amigo (`u8, u8, u32, u8, u32`) están medidos en
      TAMAÑO pero no en SIGNIFICADO. Van en cero: el paquete queda bien formado y el cliente lee
      lo que corresponde. Si alguno resulta ser "está conectado" o "su nivel", se llena después
      sin cambiar el resto. **No inventar valores**: un cero es un dato honesto, un número
      inventado es una mentira que después cuesta encontrar.
    """
    p = bytes([0])          # nA — BUDDYGROUP vacío
    p += bytes([0])         # nB — BLOCK vacío

    amigos = db_amigos(usn) if AMIGOS_LISTA_EN_FF42 else []
    amigos = amigos[:0xFFFF]
    p += struct.pack("<H", len(amigos))
    for ch in amigos:
        n = _txt(ch.get("nick", ""))
        p += struct.pack("<I", int(ch.get("uid", 0)) & 0xFFFFFFFF)
        p += bytes([len(n)]) + n
        p += bytes([0, 0]) + struct.pack("<I", 0) + bytes([0]) + struct.pack("<I", 0)   # [NM]
    return p


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# C2S — lo que llega
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _s2c_susurro(uid_emisor, nick_emisor, msg, color=1):
    """FF40 `0x05` sub 1 — **el susurro que le llega al destinatario**. Handler `0x5EFEF7`.

        [05][u8 sub][u32 uid][u8 len][nick]        ← la parte común, leída del exe
             si sub == 1:  + [u16 len][mensaje][u8 color]

    ★ Verificado por DOS caminos independientes que coinciden:
        · el exe: `0x5EFEF7` lee `read(1) sub · read(4) · read(1) len · read(len)`, y para el
          sub 1 sigue con `[u16][str][u8]`;
        · la captura del servidor de referencia que trajo anonimo03, byte por byte:
              05 01 0d000000 0b "TunTunSahur" 0400 "aaaa" 01
      ⚠ La captura **no decide** nada (es otro server privado, no la verdad). Vale porque
        **coincide con el binario**: si se contradijeran, mandaría el exe.

    El `uid` y el `nick` son los del **que manda**, no los del que recibe.
    """
    n = _txt(nick_emisor)
    m = _txt2(msg)
    return (bytes([0x05, 0x01]) + struct.pack("<I", uid_emisor & 0xFFFFFFFF)
            + bytes([len(n)]) + n
            + struct.pack("<H", len(m)) + m
            + bytes([color & 0xFF]))


def _s2c_susurro_falla(uid, nick, sub=3):
    """FF40 `0x05` con sub ≠ 1 — la línea de sistema. `[05][u8 sub][u32 uid][u8 len][nick]`.

    `sub 3` → texto **#507** (`push 0x1fb` en `0x5EFF48`) = *"está desconectado"*.
    `sub 2` → texto #471 = palabra no permitida.
    """
    n = _txt(nick)
    return bytes([0x05, sub & 0xFF]) + struct.pack("<I", uid & 0xFFFFFFFF) + bytes([len(n)]) + n


def _susurrar(st, destino_uid, msg, nick_destino=None):
    """C2S `0x04` `[04][u32 uid][u16 len][msg]` — susurrarle a alguien de mi lista.

    ⛔⛔ CÓMO CASI NO LLEGO ACÁ (2026-09-10). Yo di por hecho que *"el cliente no manda nada"*
       porque busqué en el log y no vi el paquete — y me fui a desensamblar las compuertas del
       susurro durante media hora. **El paquete SÍ llegaba.** Lo que pasó fue que el arreglo del
       byte de estado (el de la lista) destrabó la compuerta, el cliente empezó a emitir… y yo
       nunca volví a mirar el log: seguí trabajando sobre la medición VIEJA.
       ⇒ Cuando un arreglo cambia el sistema, **hay que volver a medir desde cero.**
       (El desensamblado igual sirvió: dejó escrito que la compuerta es
        `byte [amigo+0x48] ∈ {1,3,4,5,6,15,24}` — y explica por qué antes no salía.)
    """
    yo = _mi_usn(st)
    mi_nick = _nick_de(yo)
    conn = CONEXIONES.get(destino_uid)
    _sn = nick_destino or _nick_de(destino_uid)

    if conn is None:
        st.send_ff55(0x40, _s2c_susurro_falla(destino_uid, _sn, sub=3),
                     name=f"FF40/0x05 sub3: {_sn!r} está desconectado")
        log("LOBBY", f"  ★ SUSURRO usn={yo} -> uid={destino_uid} ({_sn!r}): está OFFLINE")
        return

    conn.send_ff55(0x40, _s2c_susurro(yo, mi_nick, msg),
                   name=f"FF40/0x05 susurro de {mi_nick!r}")
    log("LOBBY", f"  ★★ SUSURRO usn={yo} ({mi_nick!r}) -> uid={destino_uid} ({_sn!r}): {msg!r}")


ERR_NO_ESTA = 0x58      # cae en el cartel genérico "no existe o está desconectado"


def _resolver_destino(nick, yo):
    """nick -> uid, **prefiriendo al que está CONECTADO**. Devuelve `(uid, cuántos coincidían)`.

    ⚠⚠ POR QUÉ HACE FALTA. Lo preguntó anonimo03 y tenía razón: **el apodo no es único.** Medido sobre
    los 4807 personajes de la base local — **203 apodos repetidos, 483 cuentas (el 10 %)**,
    `jugador40` dieciocho veces. El esquema no tiene `UNIQUE` y el `FF04` no chequea al crear.

    Con `uid_por_nick()` a secas, pedirle amistad a *jugador40* le llegaba **a uno cualquiera de los
    dieciocho**. Un bug silencioso y desagradable: no falla, le escribe a otra persona.

    ★ El criterio sale de la propia mecánica: **la solicitud sólo sirve si el otro está jugando**
      (si está offline, el cliente ya muestra "no existe o está desconectado"). Entonces, entre
      varios que se llaman igual, **el que importa es el que está conectado**. Y si hay dos
      conectados con el mismo nombre —rarísimo— se elige el de menor uid y **queda en el log**,
      que es mejor que elegir en silencio.

    ⛔ Esto NO arregla el problema de fondo: que se puedan repetir los apodos. Sólo evita que la
       amistad se vaya a la persona equivocada. Ver `documentacion/` y el pendiente de `UNIQUE`.
    """
    todos = [u for u in db_uids_por_nick(nick) if u != yo]
    if not todos:
        return None, 0
    conectados = [u for u in todos if u in CONEXIONES]
    if conectados:
        return conectados[0], len(todos)
    return todos[0], len(todos)


PERFIL_VISTO_VIGENCIA = 120      # s: el «i» de Info Pareja se toca con el perfil todavía abierto


def _info_de_pareja(st, yo, nick):
    """El uid de `nick` si el `FF40 01` es el «i» de «Info Pareja» (ver info), o `None`.

    Es «ver info» si `nick` es: yo mismo · mi pareja · la pareja del último perfil que abrí.
    ⚠ Sólo el nick EXACTO de esas personas: un apodo repetido no se resuelve "a uno cualquiera".
    """
    import time as _t
    from .basedatos import db_pareja_de
    try:
        _cand = {int(yo)}
        _pj = db_pareja_de(int(yo))
        if _pj:
            _cand.add(int(_pj))
        _visto, _cuando = getattr(st, "perfil_visto", (0, 0))
        if _visto and _t.time() - _cuando < PERFIL_VISTO_VIGENCIA:
            _pv = db_pareja_de(int(_visto))
            if _pv:
                _cand.add(int(_pv))
        for _c in _cand:
            if str((db_get_char(_c) or {}).get("nick", "")) == nick:
                return _c
    except Exception as e:                                         # noqa: BLE001
        log("LOBBY", f"  ⚠ «i» de Info Pareja: no pude resolver {nick!r}: {e!r}")
    return None


def _solicitar(st, nick):
    """C2S `0x1D` `[1D][u32 uid][u8 len][nick]` — "quiero ser tu amigo".

    ★ Esto **no da de alta a nadie**: sólo hace aparecer el cartel con el botón *Aceptar* en el
      destino. El alta ocurre cuando el otro acepta (C2S `0x1E`).
    ⚠ El `uid` que manda el cliente llega en **0** — no lo sabe. Se resuelve por nick.
    """
    yo = _mi_usn(st)
    # ⚠⚠ EL UID SE PIDE APARTE. `db_char_por_nick()` devuelve el personaje **sin `uid`** — sus
    #    claves son `nick, char_id, gender, exp, rcoin, parts, …`. Porté esto del CBT, donde el
    #    row sí lo trae, y escribí `otro["uid"]`: **`KeyError('uid')` con cada solicitud real**.
    #    Lo cazó el log de la primera prueba de anonimo03, no el banco (ver la prueba §9).
    tuid, cuantos = _resolver_destino(nick, yo)
    if cuantos > 1:
        log("LOBBY", f"  ⚠ AMIGOS el apodo {nick!r} lo usan {cuantos} cuentas; "
                     f"elegí uid={tuid} ({'está conectado' if tuid in CONEXIONES else 'ninguno conectado'})")

    if tuid is None:
        st.send_ff55(0x40, _s2c_resultado(ERR_NO_ESTA, nick),
                     name=f"FF40/0x01 amistad: {nick!r} no existe")
        log("LOBBY", f"  ★ AMIGOS usn={yo} pidió a {nick!r} -> no existe")
        return

    if db_son_amigos(yo, tuid):
        st.send_ff55(0x40, _s2c_resultado(4, nick), name=f"FF40/0x01 amistad: {nick!r} ya es amigo")
        log("LOBBY", f"  ★ AMIGOS usn={yo} pidió a {nick!r} -> YA son amigos")
        return
    if len(db_amigos(yo)) >= AMIGOS_TOPE:
        st.send_ff55(0x40, _s2c_resultado(3, nick), name="FF40/0x01 amistad: mi lista llena")
        return
    if len(db_amigos(tuid)) >= AMIGOS_TOPE:
        st.send_ff55(0x40, _s2c_resultado(8, nick), name=f"FF40/0x01 amistad: {nick!r} tiene la lista llena")
        return

    destino = CONEXIONES.get(tuid)
    if destino is None:
        # El cartel genérico dice "no existe **o está desconectado**": cubre este caso exacto.
        st.send_ff55(0x40, _s2c_resultado(ERR_NO_ESTA, nick),
                     name=f"FF40/0x01 amistad: {nick!r} está desconectado")
        log("LOBBY", f"  ★ AMIGOS usn={yo} pidió a {nick!r} (uid={tuid}) -> OFFLINE")
        return

    mi_nick = _nick_de(yo)
    destino.send_ff55(0x40, _s2c_evento(yo, mi_nick, tipo=1),
                      name=f"FF40/0x1D solicitud de amistad de {mi_nick!r}")
    log("LOBBY", f"  ★★ AMIGOS usn={yo} ({mi_nick!r}) SOLICITÓ a {nick!r} (uid={tuid}) -> cartel enviado")


def _responder(st, accion, quien):
    """C2S `0x1E` `[1E][u8 acción][u32 uid]` — la respuesta al cartel. `6` = aceptar.

    Al aceptar se da de alta **en las dos direcciones** y se le manda a **cada uno** su
    `0x01` acción 1, para que el otro le aparezca en la lista sin recargar nada.
    """
    yo = _mi_usn(st)
    otro = db_get_char(quien)
    if not otro:
        log("LOBBY", f"  ⚠ AMIGOS usn={yo} respondió a un uid={quien} que no existe")
        return

    su_nick = otro.get("nick", "") or f"P{quien}"
    mi_nick = _nick_de(yo)
    conn = CONEXIONES.get(quien)

    if accion != 6:
        # Rechazo. El que pidió se entera con el `0x1E` acción 9 ("%s ha rechazado…").
        if conn is not None:
            conn.send_ff55(0x40, _s2c_respuesta(yo, 9, mi_nick),
                           name=f"FF40/0x1E {mi_nick!r} rechazó la solicitud")
        log("LOBBY", f"  ★ AMIGOS usn={yo} RECHAZÓ a uid={quien} ({su_nick!r}) [acción=0x{accion:02X}]")
        return

    db_agregar_amigo(yo, quien)
    db_agregar_amigo(quien, yo)

    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ ACÁ ME EQUIVOQUÉ, Y LO DESTAPÓ ANONIMO03 PROBANDO — 2026-09-10
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # Mandaba `0x01` acción 1, porque el mapa lo daba como *"alta completa con ficha"* (tomado del
    # CBT). anonimo03: *"salió popup, pero luego «ha enviado solicitud de amistad» A AMBOS, en lugar
    # de la confirmación, y no lista"*.
    #
    # ★ Leyendo el handler del cliente (`0x5EF4B3`), la acción 1 hace exactamente eso:
    #       0x5ef53a   push 0x45   ; texto #69 = "Ha enviado una solicitud de amistad a %s."
    #   La acción 1 **no da de alta a nadie**: es el acuse de *"mandaste una solicitud"*.
    #   ⇒ El mapa estaba mal para el 2013. Un nombre no es una medición.
    #
    # ⛔⛔⛔ ACÁ NO VA UN `0x1D` TIPO 1. Lo mandábamos, y era **la solicitud repetida** que
    #   reportó anonimo03 el 2026-09-11: aceptaba, salía *"X está listo en la lista de amigos"*, y al
    #   darle OK **volvía a salir el cartel «Sé Mi Amigo» con Añadir / No añadir**.
    #
    #   ★★★ El log lo dejó servido: entre el "aceptar" y el cartel nuevo **el server no mandó
    #   NADA**. O sea que el cartel lo produjo un paquete que ya le habíamos mandado.
    #
    #   Y el `tipo 1` (`0x5EF22A`) hace **dos cosas distintas según el estado del cliente**:
    #
    #       0x45C770   ¿ya está en MI lista?
    #          NO  ->  0x45B8F0   ★ ABRE el cartel «Sé Mi Amigo» (Añadir / No añadir)
    #          SÍ  ->  texto #105 "%s ha sido registrado como amigo."
    #
    #   ⇒ **El tipo 1 ES el cartel de solicitud.** Mandarlo al aceptar, ANTES de que la lista
    #     inserte al amigo, le pregunta de nuevo. El duplicado era nuestro, no del cliente.
    #
    #   ⛔⛔ Y mi comentario anterior decía, acá mismo, que el tipo 1 *"inserta sin cartel"*.
    #     Era una lectura mía de la tabla de saltos **sin leer la rama**. Quedó escrito con la
    #     misma seguridad que todo lo demás y era falso. Ver [[el-binario-se-contradice]]:
    #     **saber a qué dirección salta un tipo no es saber qué hace.**
    #
    # ★ Lo que queda: el `tipo 5` (`0x5EF2FE`) —que es **sólo un cartel**, verificado: formatea
    #   el texto #416 y lo muestra, no toca la lista— y la lista entera, que es la que **de
    #   verdad inserta** (por `0x45EBC0`). Un cartel por lado y el panel al día.
    #
    # ⚠ El `0x01` acción 2 también inserta (`0x5ef638`), pero **sólo por nick, sin uid**. Se
    #   descarta a propósito: sin uid la fila queda sin identidad y no sirve para nada después.
    for _c, _uid, _nk in ((st, quien, su_nick),
                          (conn, yo, mi_nick)):
        if _c is None:
            continue
        # La lista PRIMERO: es la que inserta. Si algún día vuelve a hacer falta un `tipo 1`
        # para el cartel #105, tiene que ir DESPUÉS de esto o vuelve a preguntar.
        enviar_lista_de_amigos(_c, "recién aceptado")
        _c.send_ff55(0x40, _s2c_evento(_uid, _nk, tipo=5),
                     name=f"FF40/0x1D tipo5: «{_nk} está listo en la lista de amigos»")
    try:                                                             # ★ 15-oct: misión de hoy 3001, a los dos
        from . import mision_hoy
        mision_hoy.sumar(yo, 3001, motivo="agregó un amigo")
        mision_hoy.sumar(quien, 3001, motivo="agregó un amigo")
    except Exception as _e_mh:                                       # noqa: BLE001
        log("LOBBY", f"  ⚠ misión de hoy (amigo): {_e_mh!r}")
    log("LOBBY", f"  ★★ AMIGOS usn={yo} ({mi_nick!r}) ACEPTÓ a uid={quien} ({su_nick!r}) -> alta MUTUA"
                 f" ({'el otro está online' if conn else 'el otro está offline'})")


def _eliminar(st, quien):
    """C2S `0x1F` `[1F][u32 uid][u8]` — sacar a alguien. Se borra de las dos listas."""
    yo = _mi_usn(st)
    su_nick = _nick_de(quien)
    db_borrar_amigo(yo, quien)
    db_borrar_amigo(quien, yo)

    st.send_ff55(0x40, _s2c_quitar(quien), name=f"FF40/0x1F sacar a {su_nick!r} de mi lista")
    conn = CONEXIONES.get(quien)
    if conn is not None:
        conn.send_ff55(0x40, _s2c_quitar(yo), name="FF40/0x1F sacarme de su lista")
    enviar_lista_de_amigos(st, "después de eliminar")
    if conn is not None:
        enviar_lista_de_amigos(conn, "después de que lo eliminaran")
    log("LOBBY", f"  ★ AMIGOS usn={yo} ELIMINÓ a uid={quien} ({su_nick!r}) -> baja en las DOS listas")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Los dos handlers que ve el despacho
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def h_ff42_lista_de_amigos(st, cmd, data):
    """`FF42` con cuerpo vacío = *"dame mi lista completa"* (`CmdGetAllFriendlist`).

    ★★ **Es la puerta de la interfaz.** El cliente lo pide UNA vez por sesión (un cargador
    perezoso) y, mientras no le contestemos, parte del panel de amigos se queda en la rama
    *"todavía no cargó"* y no reacciona. Contestarlo —aunque sea con las tres listas vacías—
    la enciende.
    """
    usn = _mi_usn(st)
    p = _ff42_listas(usn)
    n = struct.unpack_from("<H", p, 2)[0]
    st.send_ff55(0x42, p, name=f"FF42 lista de amigos: {n}")
    log("LOBBY", f"  ★★ FF42 CmdGetAllFriendlist usn={usn} -> {n} amigo(s) "
                 f"(buddygroup 0, bloqueados 0)")


def h_ff40_amigos(st, cmd, data):
    """`FF40` — el ruteo por subtipo de la parte de AMIGOS.

    ⚠ El `0x21` (GuildInfo, círculo) sigue viviendo en `lobby_menu.h_14_ff40`: es otro subsistema
      y no se toca acá. Este handler sólo se lleva los subtipos de amigos.
    """
    if not data:
        return
    sub = data[0]
    cuerpo = data[1:]
    usn = _mi_usn(st)

    try:
        if sub == 0x1D:
            # [u32 uid][u8 len][nick]  — el uid llega en 0, manda el nick
            if len(cuerpo) < 5:
                raise ValueError("cuerpo corto")
            ln = cuerpo[4]
            nick = cuerpo[5:5 + ln].decode("cp1252", "replace")
            _solicitar(st, nick)

        elif sub == 0x1E:
            # [u8 acción][u32 uid]
            if len(cuerpo) < 5:
                raise ValueError("cuerpo corto")
            _responder(st, cuerpo[0], struct.unpack_from("<I", cuerpo, 1)[0])

        elif sub == 0x1F:
            # [u32 uid][u8]
            if len(cuerpo) < 4:
                raise ValueError("cuerpo corto")
            _eliminar(st, struct.unpack_from("<I", cuerpo, 0)[0])

        elif sub == 0x04:
            # [u32 uid][u16 len][msg] — susurro a alguien de mi lista
            if len(cuerpo) < 6:
                raise ValueError("cuerpo corto")
            _u = struct.unpack_from("<I", cuerpo, 0)[0]
            _l = struct.unpack_from("<H", cuerpo, 4)[0]
            _susurrar(st, _u, cuerpo[6:6 + _l].decode("cp1252", "replace"))

        elif sub == 0x0D:
            # [u8 len][nick][u8 len][msg] — susurro POR NOMBRE, al que no está en la lista.
            # ⚠ Todavía sin ver en vivo: el cliente elige solo entre el 0x04 y éste. Se atiende
            #   igual para no dejarlo mudo, y el log dirá si alguna vez llega.
            if len(cuerpo) < 2:
                raise ValueError("cuerpo corto")
            _ln = cuerpo[0]
            _nk = cuerpo[1:1 + _ln].decode("cp1252", "replace")
            _lm = cuerpo[1 + _ln]
            _ms = cuerpo[2 + _ln:2 + _ln + _lm].decode("cp1252", "replace")
            _u, _c = _resolver_destino(_nk, usn)
            if _u is None:
                st.send_ff55(0x40, _s2c_susurro_falla(0, _nk, sub=3),
                             name=f"FF40/0x05 sub3: {_nk!r} no está")
            else:
                _susurrar(st, _u, _ms, _nk)

        elif sub == 0x01:
            # [u8 len][nick] — ★ EL MISMO PAQUETE SIRVE PARA DOS COSAS, según el contexto:
            #   · si YA somos amigos -> es el botón «ver info»  -> se contesta la FICHA (0x02)
            #   · si NO lo somos     -> es «agregar por nombre» -> mismo camino que el 0x1D
            # Medido: al tocar «ver info» el cliente manda `01 [len][nick]`, y nosotros le
            # contestábamos el error «ya está en tu lista». Ver `_s2c_ficha`.
            if not cuerpo:
                raise ValueError("cuerpo corto")
            ln = cuerpo[0]
            _nk = cuerpo[1:1 + ln].decode("cp1252", "replace")
            _u, _ = _resolver_destino(_nk, usn)
            # ★ Y si somos del mismo CÍRCULO, también es «ver info» (24-sep): la «i» del renglón
            #   del círculo en la Mensajería manda este mismo `01` (`0x466376` -> `0x5C8B30`) y se
            #   estaba contestando como solicitud de amistad. Ver `circulos.mismo_circulo`.
            from .circulos import mismo_circulo
            # ★★ Y EL «i» DE «INFO PAREJA» (27-sep): el mismo `01`, junto al nick de la pareja en el
            #   perfil. anonimo03: *"si otro presiona la «i», jugador1 recibió solicitud de amistad"*, y
            #   jugador1 tocando la suya (en el perfil de jugador5 la pareja es ELLA) recibió "no existe".
            #   El paquete no lo distingue: lo distingue el CONTEXTO. Es «ver info» si el nick es
            #   uno mismo, mi pareja, o la pareja del perfil que acabo de abrir (FF77/FF78, < 2 min).
            _pareja_i = _info_de_pareja(st, usn, _nk)
            if _pareja_i:
                _u = _pareja_i
            if _u is not None and (_pareja_i or db_son_amigos(usn, _u) or mismo_circulo(usn, _u)):
                _ch = db_get_char(_u) or {}
                st.send_ff55(0x40, _s2c_ficha(_u, _nk, int(_ch.get("exp", 0) or 0),
                                              int(_ch.get("licencia", 0) or 0)),
                             name=f"FF40/0x02 ficha de {_nk!r}")
                log("LOBBY", f"  ★ AMIGOS usn={usn} pidió la FICHA de {_nk!r} (uid={_u})")
            else:
                _solicitar(st, _nk)

        else:
            log("LOBBY", f"  · FF40 sub 0x{sub:02X} de amigos todavía sin handler ({len(cuerpo)}B)")
    except Exception as e:
        # Un paquete raro no puede tumbar la conexión de nadie.
        log("LOBBY", f"  ⚠ FF40 sub 0x{sub:02X} usn={usn}: {e!r}  datos={data.hex(' ')}")


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ EL MEGÁFONO — `FF40` sub `0x0B` (2026-09-15)
#
#   ⛔ POR QUÉ FALTABA: el cliente lo tenía entero y **nosotros no lo atendíamos**. Los ítems
#     estaban en el catálogo (`shop_catalog`, familia `megaphone`), la tienda los vendía, el
#     cliente dejaba escribir el texto… y el pedido caía en *"FF40 SIN handler"*.
#
#   ★ MEDIDO EN VIVO, con anonimo03 usando los tres megáfonos (19:47):
#
#       0b 02 00 00 00 04 "dasd"        <- megáfono GRANDE   (item 2)
#       0b 01 00 00 00 06 "asdasd"      <- megáfono CHICO    (item 1)
#       0b c8 00 00 00 08 "asdasdsa"    <- «agregar amigos»  (item 200 = 0xC8)
#
#       FF40 [0x0B][u32 item][u8 len][texto]
#
#   ★★★ Y EL `u32` ES EL ID DEL ÍTEM, que es **el mismo número** con el que `notice.xml` elige el
#     dibujo del cartel (`itemcode 1` = 작은 확성기 · `2` = 큰 확성기 · `200` = 친구 추가).
#     Por eso la respuesta se arma con ESE número y no con el centinela `0xFFFFFFFF`: así cada
#     megáfono sale con su propio dibujo, como corresponde.
#
#   ⇒ La vuelta es el mismo cartel global que ya usábamos:
#
#       FF40 [0x12][u32 item][u8 len][quién][u8 len][texto]
#
#   ⚠ Y SE COBRA EL ÍTEM. Un megáfono que no se gasta es munición infinita: el primero que lo
#     descubra le escribe a todo el server cuando quiera. Si no lo tiene, no se manda nada.
#
#   ★★★ EL BOTÓN DEL CARTEL LO DECIDE EL JUEGO, NO NOSOTROS — 2026-09-15. anonimo03 reportó que al
#     apretarlo *"se manda una solicitud de amistad directamente"* en vez de abrir la info.
#     No es cosa nuestra: `notice.xml` trae un campo `flag` por cada tipo, y su propio comentario
#     dice qué significa cada bit —
#         man 1 · woman 2 · NOTICE_TYPE_BUTTON 4 · GENDER_CHANGE_BUTTON 8 · USERINFO_BUTTON 16
#     y así están repartidos:
#         itemcode 1 (chico)   flag 0     -> SIN botón
#         itemcode 2 (grande)  flag 0     -> SIN botón
#         itemcode 200         flag 28    -> 4+8+16: botón + género + info   ← «agregar amigos»
#         itemcode 10000002    flag 64    -> el de GM (bit que el comentario no nombra)
#   ⇒ El megáfono que **sí** trae botón es el de «agregar amigos», y su botón es justamente para
#     agregar al amigo. Lo que vio es el comportamiento de fábrica de ESE megáfono.
#   ⏳ Si alguna vez se quiere el botón de «ver info» en el megáfono común, no se arregla desde
#     el server: hay que tocarle el `flag` a `notice.xml`, que es del CLIENTE. Queda anotado y
#     NO se hace: al cliente que funciona se le cambia lo mínimo.
# ═════════════════════════════════════════════════════════════════════════════════════════════════
def _s2c_cartel_megafono(item, quien, texto):
    """El cartel que ven todos. Mismo molde que el cartel global de pareja."""
    _q = str(quien).encode("cp1252", "replace")[:30]
    _t = str(texto).encode("cp1252", "replace")[:MEGAFONO_LARGO_MAX]
    return (bytes([0x12]) + struct.pack("<I", int(item) & 0xFFFFFFFF)
            + bytes([len(_q)]) + _q + bytes([len(_t)]) + _t)


def h_ff40_megafono(st, cmd, data):
    """`FF40 [0x0B][u32 item][u8 len][texto]` — un jugador usó un megáfono."""
    usn = int(getattr(st, "usn", 0) or 0)
    try:
        _item = struct.unpack("<I", data[1:5])[0]
        _ln = data[5]
        _txt = data[6:6 + _ln].decode("cp1252", "replace")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⚠ MEGÁFONO: no pude leer el pedido ({e!r}) raw={data.hex(' ')}")
        return
    # ⚠⚠ LA CLAVE ES `nick`, NO `nickname`. En la BASE la columna se llama `nickname`, pero el
    #   dict que devuelve `db_get_char` la expone como **`nick`** — y pedir la que no es no da
    #   error: devuelve `None`, y el cartel salía firmado por **"?"**. Lo vio anonimo03 en pantalla.
    #   ★ Y de paso arregla el botón «ver quién lo envió» del cartel: con el nombre en blanco no
    #     tenía a quién buscar.
    _nick = str((db_get_char(usn) or {}).get("nick", "") or "?")
    log("LOBBY", f"  ★★ MEGÁFONO: usn={usn} {_nick!r} item={_item} texto={_txt!r}")

    if not MEGAFONO_ACTIVO:
        log("LOBBY", "  ⚠ MEGÁFONO apagado por perilla (MEGAFONO_ACTIVO) -> no se difunde")
        return
    if not _txt.strip():
        return

    # ★★ SE COBRA EL ÍTEM, y el resultado es la autorización.
    #   `db_del_inventory` devuelve `False` si no lo tenía, así que gastar y comprobar es **una
    #   sola operación** — no hay ventana entre "miré si lo tiene" y "se lo saqué". Es la misma
    #   nota que dejó el gacha: *"no alcanza con que el cliente no muestre el botón"*.
    from .basedatos import db_del_inventory
    if not db_del_inventory(usn, _item):
        log("LOBBY", f"  ⛔ MEGÁFONO: usn={usn} pidió usar el item {_item} y NO LO TIENE "
                     f"-> no se difunde nada (¿cliente modificado?)")
        return

    # ★★★ Y SE LE AVISA CUÁNTOS LE QUEDAN — 2026-09-15. anonimo03: *"no marca una cantidad de usos
    #   y ni desaparece luego de gastarlos"*. El inventario se le manda al LOGUEAR y nunca más,
    #   así que el ícono se quedaba con el número viejo (o sin número) hasta el próximo login.
    #   ★ El `FF69` es «¿cuántos tengo de este ítem?» y el cliente ya lo entiende — lo usamos
    #     igual para las Monedas Gorila. Mandárselo después de gastar es decirle el número nuevo.
    #   ⚠ Con 0 es cuando más importa: es lo que hace que el ítem gastado **desaparezca**.
    try:
        from .basedatos import db_get_rcoin, inv_cant
        _quedan = inv_cant(db_get_char(usn) or {}).get(_item, 0)
        st.send_ff55(0x69, (bytes([1]) + struct.pack("<I", _item & 0xFFFFFFFF)
                            + struct.pack("<H", _quedan & 0xFFFF)
                            + struct.pack("<I", db_get_rcoin(usn) & 0xFFFFFFFF)),
                     name=f"FF69 te quedan {_quedan} del megáfono {_item}")
        log("LOBBY", f"  ★ MEGÁFONO: a usn={usn} le quedan {_quedan} del item {_item} "
                     f"(avisado por FF69, si no el ícono se queda con el número viejo)")
        # ★★★★ Y SI SE ACABÓ, HAY QUE **SACARLO DE LA LISTA** — anonimo03: *"al agotarlos el ítem
        #   debería deslistarse; aún queda listado y puedo intentar usarlo"*.
        #   ⚠ NO alcanza con mandar `count = 0`: `0x5ED3D9` hace `test ax,ax / jne / mov eax,1`,
        #     o sea que **el cliente lee un 0 como 1**. Un consumible agotado no se puede apagar
        #     con un número; hay que rehacerle el inventario, y eso es el MyRecord.
        #   ★ `db_del_inventory` ya borró la entrada al llegar a cero, así que el MyRecord nuevo
        #     sale sin el ítem.
        if _quedan <= 0:
            from .myrecord import enviar_myrecord
            enviar_myrecord(st, "MyRecord refresh (se acabó el megáfono)", con_personaje=False)
            log("LOBBY", f"  ★★ MEGÁFONO: a usn={usn} se le ACABÓ el item {_item} "
                         f"-> MyRecord de refresco para que se deslíste")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⚠ MEGÁFONO: no pude avisar cuántos quedan: {e!r}")

    _pk = _s2c_cartel_megafono(_item, _nick, _txt)
    _n = 0
    for _c in list(CONEXIONES.values()):
        if _c is None or getattr(_c, "cerrado", False):
            continue
        _c.send_ff55(0x40, _pk, name=f"FF40/0x12 MEGÁFONO de {_nick!r}: {_txt[:40]!r}")
        _n += 1
    log("LOBBY", f"  ★★★ MEGÁFONO de {_nick!r} (item {_item}): {_txt!r} -> {_n} jugador(es)")
