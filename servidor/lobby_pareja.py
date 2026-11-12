# -*- coding: utf-8 -*-
r"""lobby_pareja — **PROPONER, ACEPTAR, RECHAZAR y ROMPER** (FF40 sub `0x0A`).

Todo lo que hay acá sale del mapa medido: `documentacion/ANILLOS_2013_MAPA_AGENTE.md` §2, con
`SOCIAL_MAPA_2013.md` §2.4 detrás. Los bytes son los del 2013, **no los del CBT**.

★★ EL PAQUETE REAL, capturado el 2026-09-12 cuando anonimo03 apretó «Proponer» tres veces:

    inner FF40 len=15 : 0a 00 08 "jugador34"    78 8d 00 00
    inner FF40 len=18 : 0a 00 0b "jugador2" 78 8d 00 00
                        ^^ ^^ ^^  ^^^^^^^^^^^   ^^^^^^^^^^^
                       sub sub2 len   nick      chargeId

⇒ `[0x0A][0x00][u8 len][nick][u32 chargeId]`, **exactamente** lo que decía el mapa. **[M]**

★★★★★ Y EL CHARGEID **NO SE CALCULA** — la trampa que el CBT nos dejó anotada y que casi
  repetimos. Con las dos primeras muestras parecía `Index + 6000`:

      Index 30216 -> ChargeId 36216      Index 30478 -> ChargeId 36478

  pero `rnr_script/ring.txt` tiene la tabla completa y **el Anillo de corazón la rompe**:

      Index 30027 -> ChargeId **31027**   ← +1000, no +6000

  ⇒ Es un número escrito a mano, anillo por anillo. Programar la "fórmula" habría hecho fallar
    ese anillo, y el síntoma habría sido *"la propuesta no llega"*, sin ninguna pista.
  ⇒ Acá se LEE de `ring.txt` (`anillos.chargeid_de`). Ver [[no-deducir-de-un-nombre]].
"""
import struct
import time

from .ajustes import (
    FF0C_ENLACE_PAREJA,
    PAREJA_ACEPTAR,
    PAREJA_CAMBIAR_COMO_ORIGINAL,
    PAREJA_PROPUESTA_VENCE,
    PAREJA_ANILLO_AL_QUE_ACEPTA,
    PAREJA_ANIMACION,
    PAREJA_ANUNCIO_GLOBAL,
    PAREJA_MISMO_GENERO,
    PAREJA_PRESENCIA,
    PAREJA_REGISTRO_ANILLOS,
    PAREJA_TOPE_DIARIO,
)
from .basedatos import (
    db_add_inventory,
    db_anillo_de_pareja,
    db_anillos_de,
    db_borrar_recuerdo,
    db_get_char,
    db_poner_anillo,
    db_poner_confesion,
    db_pareja_de,
    db_poner_pareja,
    db_romper_pareja,
    db_uids_por_nick,
)
from .registro import log
from .salas import CONEXIONES

# ── Los códigos de error, y el texto que saca cada uno ────────────────────────────────────────
#   S2C `[0x0A][0x02][u8 a=0][u8 code]` y el cliente muestra `system.csv[140 + code]`. **[M]**
#   ★ Idénticos al CBT, mismo índice base — de lo poquito que se porta tal cual.
ERR_NO_CONECTADO   = 0     # 140 "Puede enviar su propuesta únicamente a usuarios conectados"
ERR_TOPE_DIARIO    = 1     # 141 "Puede enviar su propuesta 10 veces al día"
ERR_YA_PROPUSO     = 2     # 142 "Ya ha enviado una propuesta. Cancele su propuesta pendiente…"
ERR_MISMO_GENERO   = 3     # 143 "No puede enviar una propuesta a usuarios del mismo género."
ERR_YA_UNIDOS      = 4     # 144 "Ya está unido a este usuario."
ERR_DESCONECTADO   = 5     # 145 "%s está actualmente desconectado…"   (lleva nombre)
ERR_A_SI_MISMO     = 6     # 146 "No puede enviarse una propuesta a usted mismo."
ERR_SIN_ANILLO     = 7     # 147 ★ "No tiene un anillo válido."
ERR_DB             = 8     # 148 "Ha ocurrido un error DB"

# Propuestas vivas: ver `PENDIENTES` más abajo (varias por destino, desde el 23-sep).
#   ⚠ En memoria a propósito: una propuesta no sobrevive a un reinicio, igual que en el CBT.
#   ★ Y ahora VENCEN (`PAREJA_PROPUESTA_VENCE`): antes quedaban colgadas, que es justo lo que
#     esta nota advertía.
# ⛔⛔ EL TOPE DEL NOMBRE DE ANIMACIÓN DEL `FF7B`. **Medido en 0x5D2581**: el cliente escribe el
#   NUL en `buffer + largo`, y con 16 o más pisa la cookie de pila y **se mata solo**. No es una
#   defensa preventiva: es el número exacto a partir del cual el cliente muere.
ANI_MAX = 16

# destino_uid -> {proponente_uid: {"chargeid", "cuando"}}  (VARIAS por destino, UNA por proponente)
PENDIENTES = {}
# uid -> (fecha, cuántas mandó ESE día)  (para el tope del cartel #141)
_ENVIADAS = {}


def _pendientes_vivas(destino):
    """`{de_uid: propuesta}` con las propuestas abiertas PARA `destino`. ★ Las vencidas se borran.

    ★★ Son VARIAS (2026-09-23): el panel de mensajería del cliente lista las «Propuesta recibida»
      una por renglón, cada una con su OK/No, y el OK/No trae el uid de quién propuso. ⛔ Hasta
      hoy guardábamos UNA por destino y al segundo que proponía le decíamos que esperara.
    ⛔ Y antes no vencían nunca: en prod una propuesta sin contestar bloqueó a jugador35 durante días
      (todo el que le proponía recibía el error 2). Ver `PAREJA_PROPUESTA_VENCE`.
    """
    _todas = PENDIENTES.get(destino) or {}
    for _de, _p in list(_todas.items()):
        if PAREJA_PROPUESTA_VENCE > 0 and time.time() - float(_p.get("cuando", 0)) > PAREJA_PROPUESTA_VENCE:
            _todas.pop(_de, None)
            log("LOBBY", f"  · PAREJA: venció la propuesta de uid={_de} a uid={destino}")
    if not _todas:
        PENDIENTES.pop(destino, None)
    return _todas


def _saliente_viva(de):
    """El destino de la propuesta que `de` tiene abierta (sin vencer), o `None`.
    ★ Cada uno puede tener UNA sola saliente: es lo que dice str#142."""
    for _d in list(PENDIENTES):
        if int(de) in _pendientes_vivas(_d):
            return _d
    return None


def _enviadas_hoy(uid):
    _f, _n = _ENVIADAS.get(uid, (None, 0))
    return _n if _f == time.strftime("%Y-%m-%d") else 0


def olvidar_propuestas_de(uid):
    """★ Al desconectarse alguien, se cierran las propuestas donde es parte — Y SE AVISA, o el
    renglón del panel de la otra punta queda colgado para siempre.
      · las que RECIBÍA: a cada proponente, str#145 *"%s está actualmente desconectado, su
        propuesta pendiente ha sido cancelada"* — el texto del juego para exactamente esto;
      · las que MANDÓ: al destino, str#150 *"%s ha cancelado la propuesta"* (sub2 5).
    """
    _nk = _nick_de(int(uid))
    for _de in list(PENDIENTES.pop(int(uid), {}) or {}):
        _mandar(_de, _s2c_error(ERR_DESCONECTADO, _nk),
                f"FF40/0x0A/02 «{_nk} está desconectado, tu propuesta se canceló» (str#145)")
    for _d in list(PENDIENTES):
        if (PENDIENTES.get(_d) or {}).pop(int(uid), None) is not None:
            _mandar(_d, _s2c_cancelada(int(uid), _nk),
                    f"FF40/0x0A/05 «{_nk} ha cancelado la propuesta» (se desconectó)")
        if not PENDIENTES.get(_d):
            PENDIENTES.pop(_d, None)


def _nick_de(uid):
    return str((db_get_char(uid) or {}).get("nick", "") or "")


def _sexo_de(uid):
    """El género del personaje.

    ⛔ La clave es **`gender`**, no `sexo`: lo escribí mal y el banco lo cazó antes de la primera
      prueba. Con la clave equivocada `.get()` devolvía `None` para TODOS ⇒ todos el mismo género
      ⇒ **cada propuesta habría salido rechazada** con el cartel #143, sin ninguna pista de por qué.
    ★ Es el mismo molde del `KeyError('uid')` de amigos: **deducir el nombre de un campo en vez de
      abrir el registro**. Ver [[no-deducir-de-un-nombre]].
    ⚠ Y NO se deriva del uid ni del char_id: eso ya costó caro aparte
      (ver [[un-dato-derivado-se-esparce]]).
    """
    return int((db_get_char(uid) or {}).get("gender", 0) or 0)


def _str8(s):
    b = str(s or "").encode("cp1252", "replace")[:0x1E]
    return bytes([len(b)]) + b


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Los paquetes S2C
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _s2c_error(code, nick=""):
    """`[0x0A][0x02][u8 a=0][u8 code]` → el cliente saca `system.csv[140+code]`. **[M]**

    ⚠ El código **5** (*"%s está desconectado"*) lleva `%s`: sin el nombre detrás el cliente lo
    formatea con lo que haya en el buffer. Por eso ese caso agrega el nick.
    """
    p = bytes([0x0A, 0x02, 0x00, code & 0xFF])
    if code == ERR_DESCONECTADO:
        p += _str8(nick)
    return p


def _s2c_acuse(veces, uid, nick):
    """`[0x0A][0x01][u8 veces][u32 uid][str8 nick]` → str#149. **[M]**

    ★ El byte `veces` **es el `%d`** del texto (*"…es de %d veces"*): son las que le QUEDAN.
    """
    return bytes([0x0A, 0x01, veces & 0xFF]) + struct.pack("<I", uid & 0xFFFFFFFF) + _str8(nick)


def _s2c_popup(uid, nick, chargeid):
    """`[0x0A][0x06][u32 uid][u8 len][nick][u32 chargeId]` → `0x4215E0`, el diálogo Sí/No. **[M]**

    ★★ Esto **no existía en el CBT**, donde el diálogo estaba enredado con otra cosa y fue el
    callejón más caro de aquel server. Acá es un paquete suelto. Ver el informe §1.1.
    """
    return (bytes([0x0A, 0x06]) + struct.pack("<I", uid & 0xFFFFFFFF)
            + _str8(nick) + struct.pack("<I", chargeid & 0xFFFFFFFF))


def _s2c_cancelada(uid, nick):
    """`[0x0A][0x05][u32 uid][str8 nick]` → str#150 *"%s ha cancelado la propuesta"*, al DESTINO.
    **[M]** (`0x5F077F`, lecturas `4,1,str`). ★ Es lo que le saca el renglón «Propuesta recibida»."""
    return bytes([0x0A, 0x05]) + struct.pack("<I", uid & 0xFFFFFFFF) + _str8(nick)


def _s2c_cancele(quedan):
    """`[0x0A][0x0C][u8 quedan]` → str#152 *"Usted ha cancelado la propuesta. El número de
    oportunidades… es de %d veces"*, al que CANCELA. **[M]** (`0x5F08F7`, una lectura de 1).
    ★ Es lo que le saca su renglón «Propuesta entregada»."""
    return bytes([0x0A, 0x0C, quedan & 0xFF])


def _s2c_rechazo(uid, nick):
    """`[0x0A][0x03][u32 uid][str8 nick]` → str#151 *"%s ha rechazado la propuesta"*. **[M]**"""
    return bytes([0x0A, 0x03]) + struct.pack("<I", uid & 0xFFFFFFFF) + _str8(nick)


def _s2c_aceptado(sub2, uid, nick, item, nick2=""):
    """`sub2=4` (al que propuso, str#153) y `sub2=8` (al que aceptó, str#154).

    ★ **Los dos leen exactamente lo mismo**, así que un solo builder sirve — igual que en el CBT.

    Lecturas medidas con `lay13.py` (`0x5F0975` y `0x5F0B5B`): `4, 1, str, 4, 7, 1, 1, str, 1, 1, 4`

        [0x0A][sub2][u32 uid][str8 nick][u32 itemAnillo][7 B fecha]
                    [u8 ?][str8 nick2][u8 ?][u8 ?][u32 ?]

    ⚠⚠ **DOS COSAS SIN MEDIR, y van en CERO a propósito:**
      · **los 7 bytes de fecha**. En el CBT era un `u64` y acá es un bloque de 7. La [H] del
        informe es `[u16 año][u8 mes][u8 día][u8 h][u8 min][u8 seg]`, **sin confirmar**. ⛔ Y es
        *"el campo que más veces se equivocó el proyecto"* — no lo llenes sin medirlo.
      · **el segundo nombre**, que el CBT no tenía. **[NM]** si es el mío o el de la pareja.

    ★ Lo que SÍ importa y está garantizado es **el TAMAÑO**: mientras los bytes estén, el cliente
      lee corrido y no se desincroniza. Un valor en cero dibuja mal; un byte de menos rompe la
      conexión. Por eso se manda completo aunque no sepamos qué va adentro.
    """
    return (bytes([0x0A, sub2 & 0xFF]) + struct.pack("<I", uid & 0xFFFFFFFF) + _str8(nick)
            + struct.pack("<I", item & 0xFFFFFFFF)
            + bytes(7)                       # [NM] la fecha
            + bytes([0]) + _str8(nick2)      # [NM] el byte y el 2º nombre
            + bytes([0, 0]) + struct.pack("<I", 0))


# ══════════════════════════════════════════════════════════════════════════════════════════════
def _s2c_cartel_global(chargeid, n1, n2, flag=0):
    """`FF40 [0x12][u32 anillo][str8 n1][str8 n2][u8 flag]` — **el anuncio para TODO el server**.

    ★★ Es el único builder de pareja del CBT que se copia **sin tocar un byte**: el handler del
    2013 (`0x5F15F4`) es el mismo, rama por rama, y los textos están en los mismos índices.

    ⛔⛔ LA TRAMPA, heredada del CBT y anotada allá con todas las letras: **el `flag` elige qué
      dice el cartel**, y allá mandaban `1` en la boda, que es la rama equivocada.

        flag == 1  ->  "La pareja ha cambiado el anillo de pareja."   (str#408)
                       ★ y el cliente traduce Index -> ChargeId ÉL SOLO
        flag != 1  ->  "Ha nacido una pareja"                          (str#161)
                       ⛔ y NO traduce: hay que mandarle el ChargeId ya traducido

    ⇒ Para la boda va **`flag=0`** y **el ChargeId**, no el Index. Si se manda el Index, el cartel
      sale pero `notice.xml` no encuentra el dibujo del anillo y aparece vacío.
    ★ Nosotros ya tenemos el ChargeId de arriba: viene en la propuesta, que es de donde el propio
      cliente lo sacó de `ring.txt`. No hay que traducir nada.
    """
    return (bytes([0x12]) + struct.pack("<I", chargeid & 0xFFFFFFFF)
            + _str8(n1) + _str8(n2) + bytes([flag & 0xFF]))


def _anunciar_boda(chargeid, n1, n2):
    """Manda el cartel a todo el que esté conectado.

    ⚠ Es un BROADCAST: con 44 jugadores son 44 paquetes. Hoy es barato, pero si alguna vez el
      server crece, esto es lo primero que hay que mirar. Perilla: `PAREJA_ANUNCIO_GLOBAL`.
    """
    if not PAREJA_ANUNCIO_GLOBAL:
        return
    _p = _s2c_cartel_global(chargeid, n1, n2, flag=0)
    _n = 0
    for _c in list(CONEXIONES.values()):
        if _c is None or getattr(_c, "cerrado", False):
            continue
        _c.send_ff55(0x40, _p, name=f"FF40/0x12 ★ «Ha nacido una pareja»: {n1} & {n2}")
        _n += 1
    log("LOBBY", f"  ★★★ CARTEL GLOBAL: «Ha nacido una pareja» {n1!r} & {n2!r} "
                 f"(anillo chargeId={chargeid}) -> {_n} jugador(es)")


def _s2c_ficha_pareja(uid, sel=1):
    """S2C `FF40 [0x06][...]` — **la ficha que llena el panel «Mi Pareja»**. Handler `0x5F0050`.

    ⛔ EL SÍNTOMA que lo destapó (2026-09-12): el panel mostraba *"Servidor: No conectado ·
      Ubicación: No conectado"* con la pareja conectada al lado. En el log, el cliente pedía
      `FF40 [06][u32 uid]` **47 veces, una cada 3 segundos**, y nosotros no contestábamos nada.
      No era un dato mal puesto: era que no existía la respuesta.

    ★★ EL SELECTOR TIENE GATE — medido en `0x5F006B`:
        `cmp al,1 / cmp al,3 / cmp al,4 / cmp al,5` → sólo esos cuatro entran a llenar la ficha;
        con cualquier otro se va por `0x4584E0(uid)` y **limpia el panel**.
      ⇒ mandar `sel` fuera de {1,3,4,5} es exactamente igual que no contestar.

    Layout, leído con `campos13.py` sobre `0x5F0050` (los `read` terminan en `@+44`):

        [u8 sel][u32 uid][u8 len][nick]
        [u32 A][u16 B][u32 C][u16 D][u16 E][u32 F][u32 G][u8 H][u8 len2][str2][u8 I]

    ★ El handler llama a **`0x484A40`**, que es **la misma cascada del ícono de licencia** que ya
      medimos para la ficha del amigo (`AMIGOS_2013.md` §4-bis.4) ⇒ este panel es pariente de
      aquél, y lo que se aprendió allá aplica acá.

    ★★★★★ 2026-09-12 — **A · B · D · E RESUELTOS, Y NO POR PROBAR: POR MEDICIÓN.**
      anonimo03 pidió *"revisar el estado de mi pareja, si está off/on, parecido a amigos"*. Resultó
      ser **literalmente** lo de amigos: esta ficha **desemboca en la MISMA función que la del
      amigo**, así que los centinelas que ya medimos allá valen acá **sin volver a medirlos**.

      La cadena, eslabón por eslabón:

        0x5f01a2  call 0x44DBE0(buf, A, B, D, E, C)      ← nuestro paquete
        0x44dc5b  push arg4 ; push arg5
        0x44dc5e  call 0x44D480                          ★ la MISMA de la ficha del amigo
        0x459277  call 0x44D480  ←  el sitio del amigo, donde ya estaba medido:
                    0x459267  edx = word [amigo+0x08]    = la SALA      (se apila 1º)
                    0x45926b  eax = word [amigo+0x0a]    = el SERVIDOR  (se apila 2º = arg1)

      ⇒ `arg1 = servidor`, `arg2 = sala`. Y en `0x44DBE0` el `arg1` sale de **arg4** y el `arg2`
        de **arg5** ⇒ **D = SERVIDOR · E = SALA**, en ese orden. Con los centinelas de siempre
        (`AMIGOS_2013.md` §4-bis), que son los mismos **porque es la misma función**:

            servidor 0xFFFF -> "No conectado."   ·   sala 0xFFFF -> "vestíbulo"
                                                     sala 0xFFFE -> "Juego Personal"

      ★★ Y de yapa, por el mismo camino: `0x44dc2b call 0x4848D0(arg2)` y
        `0x44dc47 call 0x484A40(arg3, arg2, arg6)` — el par **exp + grupo de licencia** que la
        ficha del amigo ya manda en ese mismo orden (`lobby_social._s2c_ficha`) ⇒
        **A = EXP · B = GRUPO DE LICENCIA**. `C` es el tercer argumento del ícono: **[NM]**, en 0.

    ★ **El indicador de que esto anda** no es que el panel se vea lindo: es que **el cliente DEJE
      de pedirlo cada 3 segundos**. Si sigue repitiendo, el paquete no le sirvió.
    """
    # ⚠ Import adentro: `lobby_social` y `lobby_pareja` son hermanos y se importan cruzado.
    from .lobby_social import _sala_de, _servidor_de
    from .paquetes import grupo_de_licencia
    _ch = db_get_char(uid) or {}
    _nb = _nick_de(uid).encode("cp1252", "replace")[:0x1E]
    return (bytes([0x06, sel & 0xFF]) + struct.pack("<I", uid & 0xFFFFFFFF)
            + bytes([len(_nb)]) + _nb
            + struct.pack("<I", int(_ch.get("exp", 0) or 0) & 0xFFFFFFFF)          # A  exp
            + struct.pack("<H", grupo_de_licencia(_ch.get("licencia", 0)) & 0xFFFF)  # B  licencia
            + struct.pack("<I", 0)                                  # C  [NM] 3er arg del ícono
            + struct.pack("<H", _servidor_de(uid) & 0xFFFF)         # D  ★ SERVIDOR (presencia)
            + struct.pack("<H", _sala_de(uid) & 0xFFFF)             # E  ★ SALA (ubicación)
            + struct.pack("<I", 0)          # F  [NM]
            + struct.pack("<I", 0)          # G  [NM]
            + bytes([0])                    # H  [NM]
            + bytes([0])                    # str2: largo 0
            + bytes([0]))                   # I  [NM]


def _pedir_ficha(st, data):
    """C2S `FF40 [0x06][u32 uid]` — *"mostrame la ficha de este jugador"*. **[M]**, del log."""
    # ⛔ ACÁ PUSE 6 Y SON 5: `[u8 sub][u32 uid]` = 1 + 4. El paquete real del log es
    #   `06 59 2a 00 00`, cinco bytes ⇒ con el chequeo en 6 los descartaba TODOS en silencio.
    #   ★ Y el log lo cantó sin ambigüedad: **45 pedidos, 0 respuestas**, y ni un "SIN handler"
    #     (la ruta sí los agarraba). Contar mal un largo se ve igual que no tener el handler.
    if len(data) < 5:
        log("LOBBY", f"  ⚠ FF40/0x06 de {len(data)} byte(s), esperaba 5: {data.hex(' ')}")
        return
    _uid = struct.unpack_from("<I", data, 1)[0]
    if not (db_get_char(_uid) or {}):
        log("LOBBY", f"  ⚠ FF40/0x06: me piden la ficha de uid={_uid}, que no existe")
        return
    st.send_ff55(0x40, _s2c_ficha_pareja(_uid),
                 name=f"FF40/0x06 ficha de {_nick_de(_uid)!r} (panel «Mi Pareja»)")
    log("LOBBY", f"  ★★ FF40/0x06 ficha de uid={_uid} ({_nick_de(_uid)!r}) -> contestada. "
                 f"⚠ si el cliente la sigue pidiendo cada 3 s, el paquete no le sirvió")


def _s2c_animacion(sub, nombre_a, nombre_b, item=0):
    """`FF46` — **la propuesta ANIMADA con voz**, aparte del popup. Handler `0x5CF140`.

    ★★★ Esto es lo que anonimo03 recordaba del CBT (*"aceptarías mi anillo", "sé mi amante"*): no es
    un adorno del cliente, **lo dispara el server** y nosotros no lo mandábamos nunca.

        sub 0 → el proponente se ARRODILLA + voz `valen_<sexo>` (5 tomas varón / 3 mujer)
        sub 1 → asiente + voz `nod_<sexo>`     ★ el SÍ
        sub 2 → el "no quiero"                 ★ el NO

    La animación es `rnr_ani/stand_<sexo>_propose.ani` y la voz sale de `rnr_script/voice.txt`
    (`프로포즈b` → `valen_boy`, 5 tomas). Todo medido en `0x593B30`.

    Layout **[M]**, releído byte a byte en `0x5CF140`:

        [u8 sub] · (SÓLO si sub==1) [u32 itemAnillo] · [u8 len][nombreA] · [u8 len][nombreB]

    ⛔⛔ **LOS DOS NOMBRES VAN SIEMPRE**, en los tres subs. Mandar uno solo no es "mandar de
      menos": el cliente lee igual y escribe un cero en un offset arbitrario de su propio marco.
      Es la gemela de la trampa del `FF48` que ya teníamos anotada.

    ⚠ **[NM] cuál nombre va en cuál posición.** Por analogía con el CBT: el sub 0 usa el primero,
      los subs 1 y 2 el segundo. **No está verificado byte a byte** — se ve en una corrida mirando
      sobre quién se arrodilla. Por eso los dos van llenos y con los nombres de verdad: así el
      peor caso es "se arrodilla el que no era", no un paquete corrido.

    ★ La voz se elige con **el género del OCUPANTE de la sala** (`0x593EF2` → `0x436380`), no con
      el del que manda el paquete ⇒ si el género del `FF0C` estuviera mal, sonaría la voz del sexo
      equivocado. El nuestro ya está medido (`cola[41]`).
    """
    p = bytes([sub & 0xFF])
    if sub == 1:
        p += struct.pack("<I", item & 0xFFFFFFFF)
    return p + _str8(nombre_a) + _str8(nombre_b)


def _animar_en_sala(st, sub, nombre_a, nombre_b, item=0):
    """Manda la animación **a toda la sala** del que propone, él incluido.

    ⚠ Si no está en una sala no se manda nada: la animación es de avatares en el salón de espera,
      y en el lobby no hay a quién animar. No es un error, es que no aplica.
    """
    if not PAREJA_ANIMACION:
        return
    _rid = getattr(st, "room_id", None)
    if _rid is None:
        return
    from .salas import mesa_de
    _p = _s2c_animacion(sub, nombre_a, nombre_b, item)
    _n = 0
    for _u in mesa_de(_rid).values():
        _c = CONEXIONES.get(int(_u))
        if _c is None or getattr(_c, "cerrado", False):
            continue
        _c.send_ff55(0x46, _p, name=f"FF46 sub{sub} animación de pareja ({nombre_a} -> {nombre_b})")
        _n += 1
    if _n:
        log("LOBBY", f"  ★★ PAREJA: animación sub{sub} ({nombre_a!r} -> {nombre_b!r}) "
                     f"a {_n} de la sala {_rid}")


def _s2c_pareja_en_sala(item, n1, n2, sub=1):
    """`FF48 [sub]` · si `sub==1` `[u32 item]` · `[str8 n1]` · si `sub!=2` `[str8 n2]`.
    Handler `0x5CF360`. **[M]**

    ★★★ ES EL CARTEL DE *"entró a la sala"*, y además **enlaza los asientos** (`0x596570` llama a
    `0x527B00` en los dos sentidos).

    ⛔⛔ EL INFORME DEL AGENTE DIJO QUE ESTE PAQUETE ERA INUSABLE — *"va a dibujar un cartel que
      dice ' & <nombre>'"*, el mismo *"cartel &"* que el CBT arrastró. **Es falso**, y se ve
      midiendo los textos que el cartel usa DE VERDAD en vez de los dos primeros:

          005965F5  #158 = (vacío)      ← el PREFIJO
          0059663C  #159 = " &"         ← el separador
          005966A4  #414 = "El anillo de pareja con ha cambiado."
          005966C3  #160 = "ha llegado."          ★ la rama que nos interesa
          005966E3  #161 = "Ha nacido una pareja"

      Son **CINCO**, y arman tres frases distintas según la rama:
          "<A> & <B> ha llegado."   ·   "<A> & <B> Ha nacido una pareja"   ·   el del cambio
      ⇒ El `#158` vacío es un prefijo vacío a propósito, **no un renglón perdido**.

    ★ Es la tercera vez en esta sesión que una etiqueta miente y hay que ir al contenido: el
      comentario que decía *"0x0C = sala de carrera"*, el título que decía *"sin resolver"*, y
      ahora un texto vacío que parecía faltante. **Mirar la frase entera, no el renglón.**
    """
    p = bytes([sub & 0xFF])
    if sub == 1:
        p += struct.pack("<I", item & 0xFFFFFFFF)
    p += _str8(n1)
    if sub != 2:
        p += _str8(n2)
    return p


def _s2c_datos_pareja(uid_pareja, nick_pareja, mi_nick, tipo=0, anillo=0):
    """S2C `FF4A` `CmdGetCoupleData` — **la línea «Mi pareja» del panel de Mensajería**.

    ⛔ EL SÍNTOMA: el panel decía *"No tiene pareja"* con la pareja hecha y funcionando. Reportado
      por anonimo03: *"tampoco hay permanencia en social, «mi pareja» desaparece, cuando tiene su línea
      dedicada ahí — casi lo mismo que un amigo en teoría"*. Tenía razón: es una línea propia, y se
      llena con su propio paquete.

    ★★★ Y ES EL PAQUETE QUE MÁS LLEGA SIN RESPUESTA EN PRODUCCIÓN: **440 pedidos por día**
      (medido en el log de prod del 2026-09-08). O sea que esto no es sólo para el banco de
      pruebas: hay gente pidiéndolo ahora mismo y no le contestamos nada.

    Layout **[M]**, leído con `campos13.py` sobre `0x5CF4D0`:

        [u32 A][u32 B][u8 len][nick1][u8 len][nick2][u8 tipo]

    ★ El `tipo` elige el cartel (medido, `SOCIAL_MAPA_2013` §2.4):
        `0x45` → str#129 *"Su relación de pareja con %s ha terminado"*
        `0x44` → str#130 *"Su relación con %s ha expirado"*
      ⇒ Para una pareja **viva** va **0**: cualquier otro valor saca un cartel de ruptura que
        nadie pidió. Es el mismo patrón del `flag` del cartel global.

    ⛔⛔⛔ **EL 2º NICK VA VACÍO, Y ÉSE ERA EL BUG** (2026-09-12). Reportado por anonimo03: *"al cambiar
      de canal el estado desapareció"*, con el panel diciendo **"No tiene pareja"** mientras el log
      mostraba el `FF4A` contestado **bien** con la pareja correcta. El paquete salía; el cliente
      lo tiraba.

      ★★★★★ LA CASCADA, MEDIDA en `0x5CF4D0` — y no es una lista de campos, es un **árbol**:

          0x5cf57f   len2 == 0 ?  --NO-->  es un CARTEL: el `tipo` elige cuál
                                            0x5cf5b1  cmp al,0x45 -> str#129 "…ha terminado"
                                            0x5cf606  cmp al,0x44 -> str#130 "…ha expirado"
                                            cualquier otro -> ⛔ `jne 0x5cf685` = SALE SIN DIBUJAR
                        |
                        +--SÍ--> 0x5cf654  el 1er nick está vacío ?
                                              SÍ -> sale  ⇒ "No tiene pareja"
                                              NO -> ★ 0x45ED80(nick1, A, B) = PONE LA PAREJA

      ⇒ Mandábamos el nick **propio** en el segundo ⇒ `len2 != 0` ⇒ el cliente lo leía como cartel
        ⇒ `tipo=0` no es 0x45 ni 0x44 ⇒ **se iba por la puerta de atrás sin tocar el panel**.
      ★ Y por eso el síntoma era *"no tiene pareja"* y no *"el nombre equivocado"*: no es que el
        dato llegara mal, es que **esa rama no dibuja nada**.

    ★★ El 2º nick es el **`%s` del cartel de ruptura** (`0x5cf5b5` lo empuja al formateador), o
      sea que sólo tiene sentido con `tipo` 0x44/0x45. Para una pareja viva **no existe**.
    ★★ **EL 2º `u32` ES UN ÍTEM — medido el 2026-09-12**, buscando por qué el corazoncito de la
      línea no se prendía (reportado por anonimo03: *"si sale off no deja susurrar"*):

          0x5cf66a  ecx = [0x9314e8]        ← el manager del panel social
          0x45edf5  push arg3 (= B)
          0x45edfd  ecx = [0x931618]        ← ★ el manager de ÍTEMS (el mismo del FF45)
          0x45ee03  call 0x50EE80  ──►  0x50EBC0(B) busca B en la TABLA DE ÍTEMS
                                        si lo encuentra: devuelve `byte [rec+0xa]`
                                        si no:           devuelve 0
          0x45ee14  mov [esp+0x17], al      ← y el resultado queda de BANDERA

      ⇒ `B` **no es un número libre: es un itemId**, y con `B = 0` la búsqueda falla siempre y la
        bandera queda en 0. ⇒ Se manda **el anillo de la pareja**.
      ⚠ Que esa bandera sea *el corazoncito* es **[H]**: lo medido es que B se busca en la tabla
        de ítems y su resultado se guarda como bandera. Confirmarlo es mirar la pantalla.

    ⚠ El 1º `u32` sigue **[NM]**: va a `0x45ED80(nick1, A, B)` y además a `0x4583D0(A)`, que
      recorre la lista de entradas del panel. Mandamos el uid de la pareja y con eso carga.
    """
    _cartel = tipo in (0x44, 0x45)
    return (struct.pack("<II", uid_pareja & 0xFFFFFFFF, anillo & 0xFFFFFFFF)
            + _str8(nick_pareja)
            # ⛔ NO poner el nick propio acá: llenarlo manda al cliente por la rama del cartel.
            + _str8(mi_nick if _cartel else "")
            + bytes([tipo & 0xFF]))


def h_ff4a_datos_pareja(st, cmd, data):
    """`FF4A` — el cliente pregunta *"¿tengo pareja?"*. Llega al entrar y al abrir el panel."""
    try:
        _yo = int(getattr(st, "usn", 0) or 0)
        _pj = db_pareja_de(_yo) if _yo else 0
        if not _pj:
            # ★ Soltero: se contesta IGUAL, con uid 0 y sin nombres. No contestar deja al cliente
            #   preguntando —son los 440/día de prod— y la línea del panel en su estado inicial.
            st.send_ff55(0x4A, _s2c_datos_pareja(0, "", _nick_de(_yo)),
                         name="FF4A CmdGetCoupleData: sin pareja")
            return
        _an = db_anillo_de_pareja(_yo)
        _conectada = _esta_conectado(_pj)
        _alt = _alternar(_pj, _conectada)
        st.send_ff55(0x4A, _s2c_datos_pareja(_alt, _nick_de(_pj), _nick_de(_yo), anillo=_an),
                     name=f"FF4A CmdGetCoupleData: tu pareja es {_nick_de(_pj)!r} (anillo {_an}, "
                          f"{'conectada' if _conectada else 'desconectada'})")
        # ★★★ Y LA PRESENCIA, que NO viaja en el FF4A: la fila nace apagada y sólo la enciende
        #   este otro paquete. Va detrás, nunca antes — la fila tiene que existir primero.
        avisar_ubicacion_de_pareja(st, _pj, " (al contestar el FF4A)")
        log("LOBBY", f"  ★★ FF4A: usn={_yo} -> su pareja es uid={_pj} ({_nick_de(_pj)!r}), "
                     f"anillo={_an}, {'CONECTADA' if _conectada else 'desconectada'}")
    except Exception as e:                                       # noqa: BLE001
        log("LOBBY", f"  ⛔ FF4A reventó: {e!r}")


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  EL `FF45` — el REGISTRO DEL ANILLO: el nombre de la pareja y la FECHA, en la mochila
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⛔ LO QUE PASABA HASTA HOY (2026-09-12), y son DOS cosas encadenadas:
#      1. `lobby_menu.h_41_ff45` contestaba `bytes(3)` = `[u16 0][u8 0]`: un ack **válido pero
#         VACÍO** ⇒ el ítem del anillo nunca llevaba ni nombre ni fecha.
#      2. `almacen.romper_pareja` hacía `DELETE` de la fila del anillo ⇒ aunque el `FF45`
#         estuviera lleno, **al romper no quedaba nada que mandar**.
#    ★ Por eso anonimo03 veía el anillo "suelto" en la mochila y sin aniversario: no era la fecha mal
#      calculada — **era que el registro no se mandaba**.
#
# ★★★★★ EL FORMATO ESTÁ MEDIDO, no deducido (`PAREJA_PENDIENTES_AGENTE.md` §3):
#
#     FF45 S2C:
#       [u16 n]
#       n × { [u8 len][nick] [u32 anillo] [7 B fechaA] [7 B fechaB] [u8 categoría] }
#       [u8 len][string]            ← ★ UNA sola string, no una segunda lista
#
# ★★ Y LA FECHA, que es *"el campo que más veces se equivocó el proyecto"*:
#
#     7 bytes = [u16 año LE][u8 mes][u8 día][u8 ?][u8 ?][u8 ?]
#
#   ⛔ **NO es `pack_date`** —ése es la expiración de los ítems— ni el unix ts crudo. El CBT
#     mandó el ts crudo una vez y el cliente mostró *"39602/123/106"*, que son los bytes del
#     entero leídos como año/mes/día. Los formateadores son `0x48BE50` (pareja) y `0x48C250`
#     (amigo del alma), y los dos leen `[+0]=año u16 · [+2]=mes · [+3]=día`.
#   ⚠ Los 3 últimos bytes **no los lee nadie**. [H] hora/min/seg. Van en cero **sin consecuencia
#     visible** — eso también está medido (no hay consumidor de `rec+0x24..0x26`).
#
# ★★ Y LA CATEGORÍA MANDA — `0x48BE50`, valor por valor, idéntica al CBT:
#      0x41            -> sólo fecha A + str#0xA2 "Registrarse como pareja con %s."
#      0x48/0x49/0x4A  -> str#0x1E2 "El anillo de pareja ha sido cambiado con %s."
#      cualquier otra  -> str#0xA3 "Terminar la relación de pareja con %s"  + imprime la FECHA B
#    ⇒ La conclusión del CBT se porta entera: *"nunca hizo falta un campo nuevo; hacía falta
#      dejar de mandar 0x41 cuando ya no son pareja"*.
CAT_PAREJA_VIVA = 0x41
CAT_PAREJA_ROTA = 0x52          # el que usaba el CBT; sirve cualquiera que no sea 0x41/0x48-0x4A


def _fecha7(ts):
    """Los 7 bytes de fecha del registro. `ts` unix, o 0 = todo en cero.

    ⚠ El 0 NO se traduce a 1970: se mandan **siete ceros**, que es lo que el cliente espera para
      *"esta fecha no aplica"* (la fecha B de una pareja vigente). Convertirlo daría *1/1/1970*
      impreso en la mochila, que es peor que nada.
    """
    if not ts:
        return bytes(7)
    import datetime
    d = datetime.datetime.fromtimestamp(int(ts))
    return struct.pack("<HBB", d.year & 0xFFFF, d.month, d.day) + bytes(3)


def _s2c_registro_anillos(uid):
    """S2C `FF45` — **un registro por relación**: la vigente y los recuerdos de las rotas."""
    _filas = db_anillos_de(uid)
    p = struct.pack("<H", len(_filas) & 0xFFFF)
    for f in _filas:
        _vivo = f["estado"] == 1
        p += (_str8(_nick_de(f["partner_uid"]))
              + struct.pack("<I", f["item_id"] & 0xFFFFFFFF)
              + _fecha7(f["desde"])                                   # A = el casamiento
              + _fecha7(0 if _vivo else f["hasta"])                   # B = la ruptura
              + bytes([CAT_PAREJA_VIVA if _vivo else CAT_PAREJA_ROTA]))
    # ★ La string final: **una sola**, y va vacía. [NM] para qué es (va a `[0x931628]`); [H] el
    #   mensaje de propuesta personalizado. Vacía no molesta — es lo que mandábamos hasta hoy.
    return p + bytes([0])


def mandar_registro_anillos(st, motivo=""):
    """Le manda el `FF45` a `st`. Se llama al pedirlo **y** después de casarse o romper: si no,
    el ítem de la mochila sigue mostrando el estado anterior hasta el próximo login.

    ⚠ Es el mismo cuidado que el enlace de la sala: **el dato en la base no se dibuja solo**."""
    try:
        _yo = int(getattr(st, "usn", 0) or 0)
        if not _yo:
            return
        _f = db_anillos_de(_yo)
        st.send_ff55(0x45, _s2c_registro_anillos(_yo),
                     name=f"FF45 registro de anillos ({len(_f)}){motivo}")
        if _f:
            log("LOBBY", f"  ★★ FF45: usn={_yo} -> {len(_f)} anillo(s): "
                         + ", ".join(f"{x['item_id']}"
                                     f"{'/en uso' if x['estado'] == 1 else '/recuerdo'}"
                                     for x in _f) + motivo)
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⛔ FF45 reventó: {e!r}")


def _esta_conectado(uid):
    """`True` si ese uid tiene una conexión viva. Misma regla que `lobby_social._servidor_de`."""
    _c = CONEXIONES.get(int(uid or 0))
    return _c is not None and not getattr(_c, "cerrado", False)


def _alternar(uid_pareja, conectada):
    """El 1er `u32` del `FF4A` — **medido: es el UID de la fila, y va siempre**.

    ⛔⛔ ACÁ ME EQUIVOQUÉ, y vale anotarlo (2026-09-12). Medí que `0x4583D0(A)` **alterna** el
      estado de las filas cuyo uid sea A (`0x457620`: `0<->1 · 0x0F<->0x10 · 6<->7 · 0x19<->0x18`)
      y deduje que A era *"a quién alternar"* ⇒ probé mandarlo sólo cuando hacía falta.
      **No cambió nada**, y el binario explica por qué:

          0x45ef26   mov [eax+0x1c], ecx      ← ★ A es el **uid** de la entrada
          0x45ef3b   mov byte [eax+0x48], 6   ← la categoría nace en 6, CONSTANTE

      ⇒ A cumple **las dos funciones a la vez**: es el uid de la fila *y* la clave del interruptor.
        Mandando 0, la fila nace con uid 0 **y el interruptor busca uid 0** ⇒ encuentra esa misma
        fila y la alterna igual. **Los dos caminos terminan en el mismo estado.**

    ★★ La lección: *medir qué hace una función no dice para qué sirve su argumento*. El toggle era
      real; la conclusión sobre A, no. Lo que lo cerró fue seguir leyendo **quince líneas más**.
    ⇒ Va el uid, siempre. La presencia viaja por otro lado: ver `avisar_ubicacion_de_pareja`.
    """
    return int(uid_pareja or 0)


def avisar_ubicacion_de_pareja(dest, uid_otro, motivo=""):
    """Le manda a `dest` el **`FF40/0x04`** («fulano se movió») **de su pareja**.

    ★★★★★ ÉSTA ES LA PIEZA QUE PRENDE EL CORAZÓN, y estaba escrita desde el 2026-09-12 para amigos.
      El camino, medido de punta a punta:

          0x45ef65   la fila de la pareja se crea con **`0x45FD50`**, que es el **constructor de
                     entrada de AMIGO** — el mismo que ya teníamos documentado en
                     `lobby_social._servidor_de`: *"inicializa ese campo justo en 0xFFFF"*.

      ⇒ **La fila de la pareja NACE DESCONECTADA**, y el `FF4A` no trae ningún campo que la
        cambie: el paquete que escribe la presencia de una entrada es el de amigos. Como la
        pareja no está en la lista de amigos, nadie se la escribía **nunca**.

    ★ Y el `FF40/0x04` sirve tal cual: lleva `[u32 uid]…[u16 servidor][u16 sala]` y su bit de
      flags `0x10` deja el estado en **15**, *"uno de los siete valores que destraban el susurro"*
      — que es exactamente lo que anonimo03 describió: *"si sale off, no deja susurrar"*.
    """
    if not PAREJA_PRESENCIA:
        return
    try:
        from .lobby_social import _s2c_ubicacion, _sala_de, _servidor_de
        _serv, _sala = _servidor_de(uid_otro), _sala_de(uid_otro)
        dest.send_ff55(0x40, _s2c_ubicacion(uid_otro, _nick_de(uid_otro), _serv, _sala),
                       name=f"FF40/0x04 presencia de la pareja {_nick_de(uid_otro)!r} "
                            f"(servidor={_serv} sala=0x{_sala:04X}){motivo}")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⛔ avisar_ubicacion_de_pareja reventó: {e!r}")


def avisar_a_mi_pareja(st, motivo=""):
    """Le re-manda el `FF4A` a **mi pareja, si está conectada**, para que su línea se actualice.

    ★★ Es exactamente el mismo razonamiento que `lobby_social.avisar_a_mis_amigos`, y por el mismo
      motivo que anonimo03 vio allá: *"la lista se empujaba una sola vez, al entrar, y nunca más"* ⇒
      cada cliente mostraba **el estado congelado del instante en que él entró**.
      La pareja tenía el mismo agujero: el `FF4A` sólo salía **cuando el cliente lo pedía**, así
      que si el otro se conectaba o se iba después, la línea no se enteraba nunca.

    ⚠ Se llama al ENTRAR y al SALIR. Es un paquete chico y va a UNA sola persona.
    """
    try:
        _yo = int(getattr(st, "usn", 0) or 0)
        _pj = db_pareja_de(_yo) if _yo else 0
        if not _pj:
            return
        _c = CONEXIONES.get(int(_pj))
        if _c is None or getattr(_c, "cerrado", False) or _c is st:
            return
        # ★ El paquete se arma desde la PAREJA hacia MÍ: el que lo recibe es `_pj`, así que su
        #   "pareja" soy yo. Invertirlo acá es el error de copiar-pegar que más caro sale.
        # ★ Desde la vista de la PAREJA: el que mira es `_pj` y el que se movió soy yo, así que
        #   la presencia que hay que contarle es **la mía**, y en este momento ya está decidida.
        _yo_conectado = _esta_conectado(_yo) and motivo != "se fue"
        _c.send_ff55(0x4A, _s2c_datos_pareja(_alternar(_yo, _yo_conectado),
                                             _nick_de(_yo), _nick_de(_pj),
                                             anillo=db_anillo_de_pareja(_pj)),
                     name=f"FF4A a la pareja: {_nick_de(_yo)!r} {motivo}")
        avisar_ubicacion_de_pareja(_c, _yo, f" ({motivo})")
        log("LOBBY", f"  ★ PAREJA usn={_yo} {motivo}: avisado a su pareja uid={_pj}")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⛔ avisar_a_mi_pareja reventó: {e!r}")


def refrescar_registro(uids, motivo=""):
    """El `FF45` a varios, por uid. Se usa al casarse y al romper.

    ★★ **El dato en la base no se dibuja solo** — es la misma lección que el enlace de la sala y
      que el cartel: sin este empujón, el ítem de la mochila sigue mostrando el estado anterior
      hasta que el jugador vuelva a entrar. Y al romper eso es peor que feo: seguiría diciendo
      *"Registrarse como pareja"* de alguien que ya no lo es.
    ⚠ Al que esté desconectado no se le manda nada y **no es un error**: cuando entre, el cliente
      pide el `FF45` solo.
    """
    if not PAREJA_REGISTRO_ANILLOS:
        return
    for _u in uids:
        _c = CONEXIONES.get(int(_u))
        if _c is not None and not getattr(_c, "cerrado", False):
            mandar_registro_anillos(_c, motivo)


def _s2c_anillo_cambiado(uid_pareja, item, caso=0):
    """S2C `FF40 [0x0A][0x0E]` — **«El anillo de pareja con %s ha cambiado.»** (str#410).

    ★★★★★ LAYOUT MEDIDO en `0x5F0E27` (el handler del sub2 `0x0E`), campo por campo:

        [u32 A][u32 B][u8 CASO][u8 ?][u8 ?][u32 ?]

      · **`CASO` es un SELECTOR** con tabla de saltos en `0x5F3250` y **sólo 5 casos (0..4)**:
        `0x5f0ea3 cmp eax,4 / ja 0x5f3089` ⇒ cualquier otro valor **se va sin hacer nada**.
        El **0** es el que muestra el texto y actualiza la fila.
      · Y en el caso 0 (`0x5F0EB3`) se ve qué es cada `u32`:

            [esp+0x1c] = A  ->  0x45B9C0(A)  busca la FILA DEL PANEL   ⇒ A = el UID de la pareja
                                y su resultado es el **%s** del texto
            [esp+0x2c] = B  ->  0x48FDA0(B)  sobre el manager de ÍTEMS ⇒ B = el ANILLO nuevo
                                0x458A90(A, buf, B) = actualizar la fila con ese anillo

    ⚠ Los dos `u8` y el `u32` del final quedan **[NM]**, en cero. **Ocupan igual**: un byte de
      menos desincroniza la conexión. Es la misma regla del paquete del casamiento.
    """
    return (bytes([0x0A, 0x0E]) + struct.pack("<II", uid_pareja & 0xFFFFFFFF, item & 0xFFFFFFFF)
            + bytes([caso & 0xFF, 0, 0]) + struct.pack("<I", 0))


def _anunciar_cambio(item, n1, n2):
    """El cartel a TODO el server: *"La pareja ha cambiado el anillo de pareja."* (str#408)."""
    if not PAREJA_ANUNCIO_GLOBAL:
        return 0
    _p = _s2c_cartel_global(item, n1, n2, flag=1)
    _n = 0
    for _c in list(CONEXIONES.values()):
        if _c is not None and not getattr(_c, "cerrado", False):
            _c.send_ff55(0x40, _p, name=f"FF40/0x12 «cambiaron el anillo» {n1!r} & {n2!r}")
            _n += 1
    log("LOBBY", f"  ★★★ CARTEL GLOBAL: «cambiaron el anillo» {n1!r} & {n2!r} "
                 f"(anillo Index={item}) -> {_n} jugador(es)")
    return _n


def _cambiar_anillo(st, data):
    """C2S `FF40 [0x0A][0x0F][u32 chargeId][u8 len][str]` — **cambiar el anillo sin romper**.

    ★★ EL PAQUETE REAL, capturado el 2026-09-12 cuando anonimo03 apretó «Cambiar anillos de pareja»:

        0a 0f  d2 8e 00 00  00
               ^^^^^^^^^^^  ^^ una string vacía
               u32 = 36562 = el **ChargeId** del anillo elegido (`ring.txt`: Index 30562)

    ★ Es la misma moneda que la propuesta de casamiento: por el cable viaja el **ChargeId**, y el
      que dibuja quiere el **Index**. La traducción es `catalogo.anillo_por_charge`.

    ⚠⚠ **ESTA VERSIÓN CAMBIA EL ANILLO DE UNA, SIN PEDIRLE PERMISO A LA PAREJA.** Los textos del
      cliente dicen que existe un apretón de manos (#406 *"¿desea rechazar el cambio?"*, #407, #409
      *"%s ha rechazado cambiar el anillo"*), pero **cuál sub2 lo acepta y lo rechaza NO está
      medido**. ⇒ Se hace lo que sí está medido, y el resto lo va a cantar el log cuando anonimo03
      apriete los botones — que es exactamente como salió el `FF47`.
    """
    _yo = int(getattr(st, "usn", 0) or 0)
    _pj = db_pareja_de(_yo) if _yo else 0
    if not _pj:
        st.send_ff55(0x40, _s2c_error(ERR_YA_UNIDOS), name="FF40/0x0A/0F sin pareja")
        return
    if len(data) < 6:
        log("LOBBY", f"  ⚠ FF40/0x0A/0F corto ({len(data)} B): {data.hex(' ')}")
        return
    _charge = struct.unpack_from("<I", data, 2)[0]
    from .catalogo import anillo_por_charge
    _item = anillo_por_charge(_charge)
    if not _item:
        log("LOBBY", f"  ⛔ CAMBIO DE ANILLO: el chargeId={_charge} no está en ring.txt")
        st.send_ff55(0x40, _s2c_error(ERR_SIN_ANILLO), name="FF40/0x0A/0F anillo desconocido")
        return
    # ★★ LA CONFESIÓN viaja PEGADA al cambio: `[u8 len][texto]` detrás del ChargeId. anonimo03, 27-sep:
    #   *"intenté poner texto pero no se guarda"* — llegaba y se tiraba. Medido en el log:
    #       0a 0f  99 8f 00 00  0e "siempre juntos"
    #   Se guarda ANTES del chequeo de "mismo anillo": escribir la confesión sin cambiar de anillo
    #   también tiene que quedar. ⚠ Con largo 0 no se pisa: el cambio de anillo sin texto (el de
    #   siempre, `…00`) no le borra la confesión a nadie. Tope 128: el cliente la guarda en 132 B.
    _largo = data[6] if len(data) > 6 else 0
    if _largo and len(data) >= 7 + _largo:
        _txt = data[7:7 + min(_largo, 128)].decode("cp1252", "replace").replace("\x00", "")
        db_poner_confesion(_yo, _txt)
        log("LOBBY", f"  ★ CONFESIÓN de usn={_yo}: {_txt!r}")
    _actual = db_anillo_de_pareja(_yo)
    if _item == _actual:
        # ★ str#411 *"Está usando el mismo anillo de pareja."* — y el propio cliente lo chequea
        #   comparando los dos u32 del paquete de la ventana (`0x5f1098 cmp`). Acá se corta antes.
        log("LOBBY", f"  ⚠ CAMBIO DE ANILLO: usn={_yo} eligió el que ya tiene ({_item})")
        return
    db_poner_anillo(_yo, _item, _pj)
    # ★ El aviso a los DOS, cada uno con el uid del OTRO: el cliente busca esa fila en su panel
    #   y de ahí saca el nombre para el texto. Mandarle su propio uid no encontraría nada.
    st.send_ff55(0x40, _s2c_anillo_cambiado(_pj, _item),
                 name=f"FF40/0x0A/0E «el anillo con {_nick_de(_pj)!r} cambió» -> {_item}")
    _mandar(_pj, _s2c_anillo_cambiado(_yo, _item),
            f"FF40/0x0A/0E «el anillo con {_nick_de(_yo)!r} cambió» -> {_item}")
    log("LOBBY", f"  ★★★ CAMBIO DE ANILLO: usn={_yo} y uid={_pj} pasan de {_actual} a {_item} "
                 f"(chargeId {_charge})")
    # ★★ Y EL ADORNO DE LA SALA. ⛔ Reportado por anonimo03: *"tampoco se actualizó en la sala, sólo
    #   al volver cambió al nuevo"*. Es el mismo agujero que al romper: con `PAREJA_REFRESCO_FF15`
    #   apagado, el refresco sólo repinta equipos y nada redibuja el anillo.
    #   ★★★ Acá SÍ va el `FF15`, forzado. Medido por qué no sirve el atajo del `FF48`:
    #       sub 0 -> 0x527B00 x2 (el enlace) + **0x5B10F0 = efecto 0xFF = APAGADO**
    #       sub 1 -> 0x527B00 x2 + 0x5B1100 x2 (el efecto) … pero **arrastra el cartel**
    #     y ese cartel está guardado por un chequeo DEL CLIENTE (`0x5965d8 cmp / jne`), no por un
    #     campo del paquete ⇒ no se puede apagar desde el server.
    #   ⇒ El `FF15` reescribe al ocupante, que es **exactamente lo que cambió**. La perilla se
    #     apagó porque mandarlo en CADA ENTRADA parpadeaba; un cambio de anillo es un evento raro.
    try:
        from .lobby_salas import refrescar_enlaces_de_pareja
        for _u in (_yo, _pj):
            _c = CONEXIONES.get(int(_u))
            _r = getattr(_c, "room_id", None) if _c is not None else None
            if _r is not None:
                refrescar_enlaces_de_pareja(_r, " (cambiaron el anillo)", forzar=(_yo, _pj),
                                            forzar_ff15=True)
    except Exception as _e:                                          # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude refrescar el adorno tras el cambio: {_e!r}")
    # ★★★★★ Y EL ANUNCIO GLOBAL, que también existe para el cambio. ⛔ anonimo03: *"faltó el anuncio
    #   global, también existe cuando es cambio de anillo"*. Tenía razón, y la respuesta ya estaba
    #   escrita en nuestro propio `_s2c_cartel_global` desde que se portó del CBT:
    #       flag == 1 -> str#408 "La pareja ha cambiado el anillo de pareja."
    #                    ★ y en ESA rama el cliente traduce Index -> ChargeId **él solo**
    #       flag != 1 -> str#161 "Ha nacido una pareja"  (la boda, y ahí hay que mandar el ChargeId)
    #   ⇒ Para el cambio va **flag=1 y el INDEX**, no el ChargeId. Es la trampa al revés de la boda.
    _anunciar_cambio(_item, _nick_de(_yo), _nick_de(_pj))
    # ★ Y el registro de la mochila: el ítem del anillo nuevo tiene que llevar el nombre y la fecha.
    refrescar_registro((_yo, _pj), " (cambiaron el anillo)")


CUPON_CONFESION = 219          # «Cupón Cambio de confesión» (0506, PN 3600) — el 0xDB del handler


def h_ffc2_confesion(st, cmd, data):
    """C2S `FFC2` `CmdUpdateProposeMsg` — el botón «Ingresar» de «Info Pareja → Mi confesión».

    ★ EL PAQUETE REAL (27-sep, jugador5): `00 00 00 00 | 00 | 06 "testas"` = `[u32 ?][u8 ?][u8 len][texto]`.
      Hasta hoy caía en "SIN handler" y la confesión no se guardaba.

    ★★ LA RESPUESTA, leída del handler S2C `0x5DD0A0`: `[u8 tipo]` y
          tipo 0 -> `[u8 len][texto]` -> el cliente lo copia a SU ficha (`player+0x544`) y lo muestra
          tipo 2 -> lo mismo, y ADEMÁS se descuenta el ítem `0xDB` = 219 él solo (`0x48FDA0`)
          tipo 1 -> un cartel de error (str#677: en nuestro system.csv es un texto de Twitter ⇒ NO se usa)
       y al final prende/apaga el botón según tenga o no el 219 (`0x48AAE0` + `setne`).

    ★ LA REGLA, de anonimo03: *"el primer cambio de confesión es gratis, luego sí se usa el ítem — ya
      que la confesión inicial no había sido puesta, luego se deshabilita hasta comprar cupón y
      usarlo"*. ⇒ sin confesión previa: gratis (tipo 0). Con una: gasta un 219 (tipo 2). Sin cupón:
      no se guarda (el propio cliente ya deja el botón apagado).
    """
    _yo = int(getattr(st, "usn", 0) or 0)
    if not _yo or len(data) < 6:
        log("LOBBY", f"  ⚠ FFC2 corto o sin usuario ({len(data)} B): {data.hex(' ')}")
        return
    _largo = data[5]
    if len(data) < 6 + _largo:
        log("LOBBY", f"  ⚠ FFC2: dice {_largo} B de texto y trae {len(data) - 6}: {data.hex(' ')}")
        return
    _txt = data[6:6 + min(_largo, 128)].decode("cp1252", "replace").replace("\x00", "")
    from .basedatos import db_del_inventory, db_hay_confesion
    if not db_hay_confesion(_yo):
        _tipo = 0
        _como = "la PRIMERA: gratis"
    elif db_del_inventory(_yo, CUPON_CONFESION):
        _tipo = 2
        _como = f"gastó 1 cupón {CUPON_CONFESION}"
    else:
        log("LOBBY", f"  ⛔ CONFESIÓN de usn={_yo}: ya tenía una y NO tiene el cupón {CUPON_CONFESION} "
                     f"-> no se guarda ({_txt!r})")
        return
    db_poner_confesion(_yo, _txt)
    _t = _txt.encode("cp1252", "replace")[:128]
    st.send_ff55(0xC2, bytes([_tipo, len(_t)]) + _t,
                 name=f"FFC2 tipo {_tipo}: confesión guardada ({_como})")
    log("LOBBY", f"  ★ CONFESIÓN de usn={_yo} ({_como}): {_txt!r}")


def h_ff7b_baile_de_pareja(st, cmd, data):
    """`FF7B` `CmdCoupleDance` — **el baile/gesto de a dos** (`/rosas`, `/besar`, `/abrazo`…).

    ⛔ EL SÍNTOMA: anonimo03 apretaba el gesto y *"los charts no hacen el gesto de pareja"*. Y no era
      el chat: el `/rosas` del chat es sólo el texto. **El gesto es este comando aparte**, y nos
      llegaba como *"FF7B SIN handler"*.

    ★★★★★ Y POR QUÉ NO PASABA NADA NI EN LA PANTALLA DEL QUE LO APRETÓ — del `GESTOS.md` del CBT,
      que lo dejó medido: la función que reproduce el baile **tiene UN SOLO LLAMADOR: el handler
      de RECEPCIÓN**. ⇒ **el baile depende del eco del servidor.** Sin relay no baila nadie, ni
      siquiera el emisor. Eso explica el síntoma exacto, palabra por palabra.

    ★★ EL LAYOUT, MEDIDO EN NUESTRO CLIENTE (handler `0x5D2540`, ubicado por la tabla de registro
      del cliente: bloque `0x203E0 + cmd*0x10`, el handler en `+8`):

        C2S  [u32 ItemCode][u8 largo][Ani][f32][f32][u8 slotPareja][u8 miSlot][f32][f32][f32]
        S2C  ..............[u8 largo][Ani][f32][f32][u8 slotPareja][u8 miSlot][f32][f32][f32]

      ⇒ **El eco es el paquete recibido SIN LOS 4 PRIMEROS BYTES**, a todos los ocupantes de la
        sala **incluido el emisor**. Comprobado con el paquete real de anonimo03: C2S de 34 B, y el
        handler lee exactamente 30.
      ⚠ El 2013 lleva **tres floats más** que el CBT (allá eran sólo dos, el punto medio). Por eso
        no se copia el largo de allá: se reenvía **lo que vino**, sin recortar ni rellenar.

    ⛔⛔⛔ Y EL FRENO QUE NO ES OPCIONAL: **UN `Ani` LARGO MATA AL CLIENTE.**

        0x5d2540  sub esp, 0x34                ← el frame
        0x5d2573  movzx eax, byte [esp+7]      ← el LARGO, que viene del paquete
        0x5d2581  mov byte [esp+eax+0x2c], 0   ← el NUL, a buffer + largo

      Con `largo >= 16` ese cero **pisa la cookie de pila** y el proceso se mata solo. El CBT lo
      midió allá (*"los dos se cerraron en el mismo segundo, sin popup"*) y acá da **el mismo
      tope**. ⇒ Se valida en el SERVER: ningún `Ani` largo puede llegar a un cliente.
      ★ Y por eso tampoco se ecoa el paquete crudo: el cliente tomaría el primer byte del
        `ItemCode` como largo (0x62 = 98) y escribiría el cero muy por encima de su frame.

    ★ Diagnóstico gratis, del CBT: el cliente **valida el `ItemCode` contra su inventario ANTES
      de emitir**. Si un gesto no sale y acá **no aparece nada**, le falta el ítem. Si el paquete
      aparece y no baila, el problema es nuestro.
    """
    try:
        _yo = int(getattr(st, "usn", 0) or 0)
        _rid = getattr(st, "room_id", None)
        if _rid is None and getattr(st, "lugar_clave", None) is None:
            log("LOBBY", f"  ⚠ FF7B de usn={_yo} fuera de una sala -> ignoro")
            return
        if len(data) < 6:
            log("LOBBY", f"  ⚠ FF7B corto ({len(data)} B): {data.hex(' ')}")
            return
        _item = struct.unpack_from("<I", data, 0)[0]
        _largo = data[4]
        if _largo >= ANI_MAX or len(data) < 5 + _largo:
            # ⛔ NO se reenvía. Es la única validación que, si falta, **mata clientes**.
            log("LOBBY", f"  ⛔⛔ FF7B con Ani de {_largo} byte(s) (tope {ANI_MAX - 1}): "
                         f"NO se reenvía — pisaría la cookie de pila y cerraría a todos")
            return
        _ani = data[5:5 + _largo].decode("cp949", "replace")
        _eco = bytes(data[4:])                      # ★ sin los 4 del ItemCode
        try:                                        # ★ 15-oct: misión de hoy 4002 sala / 4001 charla
            from . import mision_hoy
            mision_hoy.sumar(_yo, 4002 if _rid is not None else 4001, motivo="baile de pareja (FF7B)")
        except Exception as _e_mh:                  # noqa: BLE001
            log("LOBBY", f"  ⚠ misión de hoy (baile): {_e_mh!r}")
        # ★★ En la SALA DE CONVERSACIÓN (24-sep): a los de la estancia (`charla.py`).
        if _rid is None:
            from .charla import reenviar_ff7b
            _n7b = reenviar_ff7b(st, _eco)
            log("LOBBY", f"  ★★★ GESTO DE PAREJA en la charla: usn={_yo} baila {_ani!r} -> {_n7b} cliente(s)")
            return
        from .salas import conexiones_en_sala
        _dest = [c for c in (conexiones_en_sala(_rid) or [])
                 if c is not None and not getattr(c, "cerrado", False)]
        for _c in _dest:
            _c.send_ff55(0x7B, _eco, name=f"FF7B baile de pareja {_ani!r} (ítem {_item})")
        log("LOBBY", f"  ★★★ GESTO DE PAREJA: usn={_yo} ({_nick_de(_yo)!r}) baila {_ani!r} "
                     f"con el ítem {_item} -> {len(_dest)} cliente(s) de la sala {_rid}")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⛔ FF7B reventó: {e!r}")


FF60_ANI_MAX = 64


def h_ff60_gesto_de_uso(st, cmd, data):
    """`FF60` — **el gesto de un CUPÓN DE ANIMACIÓN** (`/comiste`, `/show`, `/saludo`…: los ítems
    1010xxx/1020xxx de la pestaña Acción, «쿠폰애니N»/«쿠폰N»). 28-sep, traídos de XYX.

    ⛔ EL SÍNTOMA (anonimo03, en la sala): el gesto no hacía nada. El cliente equipa el ítem (`FF1A`),
      dice el comando (`FF08`) y manda ESTE paquete, que llegaba como *"FF60 SIN handler"*. Es el
      mismo caso que el `FF7B`: la animación la pone el handler de RECEPCIÓN.

    ★★ EL LAYOUT, MEDIDO EN NUESTRO CLIENTE (handler `0x5D08E0`, registrado en `0x5F60FD` =
      `this + 0x203E0 + 0x60*0x10 + 8`, la misma tabla que ubicó el FF7B):

        C2S                [u32 ItemCode][u8 largo][Ani]                (el de anonimo03: 10 B, «쿠폰3»)
        S2C  [u8 asiento]  [u32 ItemCode][u8 largo][Ani]  [u8 marca]

      Con el asiento busca al personaje en la escena (`0x593480` -> `0x587A50`, el mapa de
      `sala+0x9C`) y le pone la animación. Si `marca != 0` Y el asiento es el MÍO, además llama a
      `0x48FDA0(ItemCode)`, que recorre el inventario: el «gastar el cupón» de los que van por
      USOS. ⇒ Va **0**: los nuestros van por TIEMPO (P7/P30), no se gastan.
    ⚠ El Ani va a un búfer de pila de ~0x100 con el NUL a `búfer + largo` (como el FF7B): se corta
      en `FF60_ANI_MAX`, lejos del borde.
    """
    try:
        _yo = int(getattr(st, "usn", 0) or 0)
        if len(data) < 6 or data[4] >= FF60_ANI_MAX or len(data) < 5 + data[4]:
            log("LOBBY", f"  ⛔ FF60 raro de usn={_yo} ({len(data)} B): {data[:24].hex(' ')} -> NO se reenvía")
            return
        _item = struct.unpack_from("<I", data, 0)[0]
        _ani = data[5:5 + data[4]].decode("cp949", "replace")
        _rid = getattr(st, "room_id", None)
        if _rid is not None:
            from .salas import conexiones_en_sala
            _slot = getattr(st, "room_slot", None)
            _dest = [c for c in (conexiones_en_sala(_rid) or []) if c is not None and not getattr(c, "cerrado", False)]
        elif getattr(st, "lugar_clave", None) is not None:
            from . import charla
            _slot = charla.mi_slot(st)
            _dest = charla.destinos(st, con_yo=True) or [st]
        else:
            log("LOBBY", f"  ⚠ FF60 de usn={_yo} fuera de una sala -> ignoro")
            return
        if _slot is None:
            log("LOBBY", f"  ⚠ FF60 de usn={_yo}: no sé su asiento -> ignoro")
            return
        _eco = bytes([_slot & 0xFF]) + bytes(data[:5 + data[4]]) + b"\x00"
        try:                                                         # ★ 15-oct: misión de hoy 4002 sala / 4001 charla
            from . import mision_hoy
            mision_hoy.sumar(_yo, 4002 if _rid is not None else 4001, motivo="gesto (FF60)")
        except Exception as _e_mh:                                   # noqa: BLE001
            log("LOBBY", f"  ⚠ misión de hoy (gesto): {_e_mh!r}")
        for _c in _dest:
            _c.send_ff55(0x60, _eco, name=f"FF60 gesto {_ani!r} (ítem {_item}, asiento {_slot})")
        log("LOBBY", f"  ★★ GESTO DE CUPÓN: usn={_yo} ({_nick_de(_yo)!r}) hace {_ani!r} con el ítem {_item} "
                     f"-> {len(_dest)} cliente(s), asiento {_slot}")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⛔ FF60 reventó: {e!r}")


def apagar_enlace_en_sala(rid, nicks, motivo=""):
    """Apaga el adorno de pareja de `nicks` en la sala `rid`. **La forma nativa, sin repintar.**

    ⛔ EL SÍNTOMA (2026-09-12, anonimo03): *"rompí con mi pareja, la escena no se actualizó"* — los dos
      seguían con los arcos de flores y los corazones puestos. Y su aviso, que es la regla de la
      casa: *"buscamos la forma nativa, no un repintado que oculte algo"*.

    ⚠ La causa: con `PAREJA_REFRESCO_FF15=False` —el A/B que cerramos para sacar el parpadeo— el
      refresco **saltea el `FF15`** y sólo repinta equipos. El enlace lo dibuja el `FF48` al entrar,
      y al romper **no salía ningún paquete que lo apagara**. No era un bug del A/B: era que nunca
      habíamos buscado el "apagar".

    ★★★★★ Y EXISTE, MEDIDO EN EL PROPIO `FF48` (`0x5CF360`), que tiene **cuatro** subtipos y
      nosotros usábamos uno:

          sub 1  -> 0x596570                      el enlace (el que ya mandábamos)
          sub 2  -> 0x595210 -> 0x5B1110 -> 0x5B1070(0, **0xFE**)
          sub 5  -> 0x5951D0 -> 0x5B10F0 -> 0x5B1070(0, **0xFF**)   ← ★ "ninguno"
          sub 6  -> 0x595190 -> 0x5B1110 -> 0x5B1070(0, 0xFE)

      `0x5B1070` guarda ese byte en `[this+0x1DC]` y **lo compara con `0xFF`** (`0x5b10be`). Es el
      mismo centinela de *"esto no aplica"* que ya medimos en el asiento de la pareja (`cola[12]`)
      y en la presencia (`0xFFFF`). ⇒ **`sub 5` es el apagar.**
    ★ Los tres buscan al jugador **por nombre** (`0x591C80`), igual que el sub 1.

    ⚠ Y el enlace del asiento se apaga por el camino ya medido en esta misma sesión: el `sub 1`
      con el segundo nombre **vacío** — *"si no lo encuentra por nombre devuelve 0xFF y le estampa
      soltero"*. Lo que antes nos mordió sin querer, acá se usa a propósito.
    """
    if not FF0C_ENLACE_PAREJA or rid is None:
        return 0
    try:
        from .salas import CONEXIONES as _CX, mesa_de
        _mesa = mesa_de(rid) or {}
        _dest = [_CX.get(int(u)) for u in _mesa.values()]
        _dest = [c for c in _dest if c is not None and not getattr(c, "cerrado", False)]
        _n = 0
        for _nk in nicks:
            if not _nk:
                continue
            for _c in _dest:
                # ★★★ el asiento: **sub 0**, no sub 1.
                #   ⛔ Con el sub 1 salía el cartel «X & Y ha llegado.» al ROMPER, y encima con el
                #     anillo básico (mandamos item 0). Reportado por anonimo03: *"al romper sale un
                #     anuncio de entrada a sala, de otro anillo, el básico"*.
                #   ★ MEDIDO: el `FF48` tiene un sub 0 que es el HERMANO del 1, sin el extra:
                #         sub 0 -> 0x5939B0(n2, n1)
                #         sub 1 -> 0x596570(n2, n1, **1**)   ← ese 1 de más es el que anuncia
                #     Los dos buscan por nombre con `0x4EBCB0`. ⇒ el sub 0 enlaza y NO anuncia.
                _c.send_ff55(0x48, _s2c_pareja_en_sala(0, _nk, "", sub=0),
                             name=f"FF48/0 {_nk!r} queda SOLTERO (sin cartel){motivo}")
                # ★ y el efecto sobre la cabeza: sub 5 = 0xFF = ninguno
                _c.send_ff55(0x48, _s2c_pareja_en_sala(0, _nk, "", sub=5),
                             name=f"FF48/5 apagar el efecto de {_nk!r}{motivo}")
            _n += 1
        if _n:
            log("LOBBY", f"  ★★ PAREJA: apagado el adorno de {_n} en la sala {rid} "
                         f"a {len(_dest)} cliente(s){motivo}")
        return _n
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⛔ apagar_enlace_en_sala reventó: {e!r}")
        return 0


def h_ff47_tirar_recuerdo(st, cmd, data):
    """`FF47` `CmdDeleteCoupleHistory` — **el botón de descartar el anillo roto**.

    ⛔ anonimo03, riéndose: *"intenté borrar el ítem de recuerdo = falló"*. No fallaba el botón: el
      comando caía en **«sin handler»**, y el cliente **no hace nada si no se le contesta**.

    ★★★ EL CLIENTE DEVUELVE EL REGISTRO QUE NOSOTROS LE DIMOS, tal cual. Capturado en vivo:

        0a "jugador26"  08 77 00 00  ea 07 09 0c 00 00 00  ea 07 09 0c 00 00 00
        ^^ len            ^ anillo 30472  ^ fecha A = 2026/9/12  ^ fecha B

      — o sea nuestro propio `FF45`, con **nuestra** fecha adentro. Eso es lo que hay que buscar
      y borrar, y es la **única salida del tercer estado**: el anillo roto no se va solo.

    ★★★★★ LAYOUT DE LA RESPUESTA, medido en `0x5CF260` (el handler del 2013, ubicado por la tabla
      de registro en `0x5F5F08` → bloque `+0x20850`):

          C2S       [u8 len][nick][u32 anillo][7 B fechaA][7 B fechaB]
          S2C  [u8 result][u8 len][nick][u32 anillo][7 B fechaA][7 B fechaB]

      ⛔⛔ **`result` se lee PRIMERO y con 0 el cliente se va sin tocar nada**:
          `0x5cf2d5 cmp byte [esp+7],0 / 0x5cf2da je` ⇒ contestar `0` se ve **igual que no
          contestar**. El CBT ya lo había dejado anotado y acá se confirmó en el binario del 2013.

    ⚠ Sólo se borran los **rotos** (`estado=2`). El registro de una pareja VIVA no se tira: el
      cliente no ofrece ese botón, y borrarlo dejaría la pareja sin su fecha de casamiento.
    """
    try:
        _yo = int(getattr(st, "usn", 0) or 0)
        if not _yo or len(data) < 1:
            return
        _l = data[0]
        if len(data) < 1 + _l + 4 + 14:
            log("LOBBY", f"  ⚠ FF47 corto ({len(data)} B): {data.hex(' ')}")
            return
        _nick = data[1:1 + _l].decode("cp1252", "replace")
        _item = struct.unpack_from("<I", data, 1 + _l)[0]
        _cola = data[1 + _l + 4:1 + _l + 4 + 14]          # las dos fechas, tal cual llegaron
        _n = db_borrar_recuerdo(_yo, _item)
        # ★ La respuesta ECO: el cliente vuelve a leer los mismos campos para saber QUÉ fila sacar
        #   de la mochila. Devolverlos cambiados sería pedirle que borre otra cosa.
        st.send_ff55(0x47, bytes([1 if _n else 0, _l]) + data[1:1 + _l]
                     + struct.pack("<I", _item) + _cola,
                     name=f"FF47 tirar el recuerdo de {_nick!r} (anillo {_item}) -> "
                          f"{'BORRADO' if _n else 'no habia ninguno roto'}")
        log("LOBBY", f"  ★★ FF47: usn={_yo} tira el recuerdo del anillo {_item} con {_nick!r} "
                     f"-> {_n} fila(s)")
        if _n:
            # ★ Y el registro de vuelta, para que la mochila quede al día sin salir y entrar.
            mandar_registro_anillos(st, " (tiro un recuerdo)")
    except Exception as e:                                           # noqa: BLE001
        log("LOBBY", f"  ⛔ FF47 reventó: {e!r}")


def _resolver(nick, yo):
    """El uid del destinatario. ⚠ **El apodo NO es único** (203 repetidos sobre 4807).

    ★ Entre varios con el mismo apodo se elige **al que está CONECTADO**, igual que en amigos:
      si no, la propuesta le llega en silencio a otra persona. Ya pasó con las solicitudes.
    """
    _uids = [u for u in (db_uids_por_nick(nick) or []) if int(u) != int(yo)]
    if not _uids:
        return 0
    _on = [u for u in _uids if CONEXIONES.get(int(u)) is not None]
    return int((_on or _uids)[0])


def _mandar(uid, payload, nota):
    _c = CONEXIONES.get(int(uid))
    if _c is None or getattr(_c, "cerrado", False):
        return False
    _c.send_ff55(0x40, payload, name=nota)
    return True


def _proponer(st, data):
    """C2S `[0x0A][0x00][u8 len][nick][u32 chargeId]` — el botón «Proponer». **[M]**"""
    _yo = int(getattr(st, "usn", 0) or 0)
    if len(data) < 3:
        log("LOBBY", f"  ⚠ pareja: propuesta de {len(data)} byte(s) -> la tiro: {data.hex(' ')}")
        return
    _ln = data[2]
    _nick = data[3:3 + _ln].decode("cp1252", "replace")
    _charge = struct.unpack_from("<I", data, 3 + _ln)[0] if len(data) >= 3 + _ln + 4 else 0

    def _no(code, nick=""):
        st.send_ff55(0x40, _s2c_error(code, nick),
                     name=f"FF40/0x0A/02 pareja RECHAZADA (código {code} -> texto #{140 + code})")
        log("LOBBY", f"  ⛔ PAREJA usn={_yo} -> {_nick!r}: error {code} (texto #{140 + code})")

    _otro = _resolver(_nick, _yo)
    if not _otro:
        return _no(ERR_NO_CONECTADO)
    if _otro == _yo:
        return _no(ERR_A_SI_MISMO)
    if int(db_pareja_de(_yo) or 0) == int(_otro):
        # ★ str#144 «Ya está unido a este usuario»: ÉSTE es el único caso en que el texto es cierto.
        return _no(ERR_YA_UNIDOS)
    if not PAREJA_CAMBIAR_COMO_ORIGINAL and (db_pareja_de(_yo) or db_pareja_de(_otro)):
        # ⚠ El comportamiento hasta el 23-sep. Con la perilla en True (como el original) se deja
        #   proponer, y las parejas viejas se rompen al ACEPTAR (ver `_responder`).
        return _no(ERR_YA_UNIDOS)
    if not PAREJA_MISMO_GENERO and _sexo_de(_yo) == _sexo_de(_otro):
        # ★★★ 2026-09-15 — ABIERTO POR PEDIDO DE ANONIMO03, y el comentario viejo acertó: se sacaba
        #   ACÁ y no hubo que tocar nada más. Esta línea es la ÚNICA puerta en todo el server.
        # ★★ Y NO HIZO FALTA PARCHEAR EL EXE, que era la duda razonable: el cliente **no tiene**
        #   este bloqueo. El texto #143 no está cableado en ninguna parte del `.text` (se buscó
        #   `push 0x8f` en las 342.785 instrucciones: cero apariciones) ⇒ la única forma de que
        #   ese cartel aparezca es que **nosotros** mandemos el código 3. Era regla del server.
        return _no(ERR_MISMO_GENERO)
    if not _charge:
        # ★ Sin ChargeId no hay anillo elegido. El cliente lo saca de `ring.txt`; si llega en 0
        #   es que el jugador no tiene ninguno puesto.
        return _no(ERR_SIN_ANILLO)
    if CONEXIONES.get(_otro) is None:
        return _no(ERR_DESCONECTADO, _nick)
    if _enviadas_hoy(_yo) >= PAREJA_TOPE_DIARIO:
        return _no(ERR_TOPE_DIARIO)
    if _saliente_viva(_yo) is not None:
        # ★ str#142 «Ya ha enviado una propuesta. Cancele su propuesta pendiente…» habla de la
        #   propuesta DEL QUE PROPONE. ⛔ Antes salía cuando el DESTINO tenía una abierta de otro:
        #   le echaba la culpa a quien no tenía ninguna.
        return _no(ERR_YA_PROPUSO)
    # ★ Si el destino ya tiene propuestas de OTROS, se suma una más: el cliente las lista en el
    #   panel de mensajería («Propuesta recibida»), cada una con su OK/No.
    _pendientes_vivas(_otro)
    PENDIENTES.setdefault(_otro, {})[_yo] = {"chargeid": _charge, "cuando": time.time()}
    _ENVIADAS[_yo] = (time.strftime("%Y-%m-%d"), _enviadas_hoy(_yo) + 1)
    _quedan = max(0, PAREJA_TOPE_DIARIO - _enviadas_hoy(_yo))

    _mandar(_otro, _s2c_popup(_yo, _nick_de(_yo), _charge),
            f"FF40/0x0A/06 ★ «{_nick_de(_yo)} te propone ser su pareja» (diálogo Sí/No)")
    st.send_ff55(0x40, _s2c_acuse(_quedan, _otro, _nick),
                 name=f"FF40/0x0A/01 acuse: propuesta enviada a {_nick!r} (te quedan {_quedan})")
    log("LOBBY", f"  ★★ PAREJA: usn={_yo} ({_nick_de(_yo)!r}) le propone a uid={_otro} "
                 f"({_nick!r}) con el anillo chargeId={_charge}. Le quedan {_quedan} hoy")
    # ★★★ Y LA ANIMACIÓN: el proponente se arrodilla y suena la voz, para toda la sala.
    _animar_en_sala(st, 0, _nick_de(_yo), _nick)


def _responder(st, data, acepta):
    """C2S `0x0A/04` aceptar · `0x0A/03` rechazar — los dos `[u32 uid]`. **[D]** del informe §2.3."""
    _yo = int(getattr(st, "usn", 0) or 0)
    _vivas = _pendientes_vivas(_yo)
    # ★ El OK/No trae el uid de QUIÉN propuso: con varias abiertas es lo que dice cuál se contesta.
    _pidio = struct.unpack_from("<I", data, 2)[0] if len(data) >= 6 else 0
    if _pidio not in _vivas and len(_vivas) == 1:
        _pidio = next(iter(_vivas))          # un cliente que no lo mande: la única que hay
    _pend = _vivas.pop(_pidio, None)
    if not _vivas:
        PENDIENTES.pop(_yo, None)
    if not _pend:
        log("LOBBY", f"  ⚠ PAREJA: usn={_yo} contesta una propuesta de uid={_pidio} que no existe "
                     f"(o venció) -> ignoro")
        return
    _de, _charge = int(_pidio), int(_pend.get("chargeid", 0))

    if not acepta:
        _mandar(_de, _s2c_rechazo(_yo, _nick_de(_yo)),
                f"FF40/0x0A/03 «{_nick_de(_yo)} ha rechazado la propuesta»")
        # ★ El "no quiero" también es animado. El sub 2 es LIMPIO: no arrastra ningún cartel.
        _animar_en_sala(st, 2, _nick_de(_de), _nick_de(_yo))
        log("LOBBY", f"  ★ PAREJA: usn={_yo} RECHAZÓ la propuesta de uid={_de}")
        return

    if not PAREJA_ACEPTAR:
        log("LOBBY", f"  ⏸ PAREJA: usn={_yo} aceptó a uid={_de}, pero PAREJA_ACEPTAR=False "
                     f"-> NO se casa a nadie (el paquete del casamiento tiene campos sin medir)")
        return

    if int(db_pareja_de(_yo) or 0) == _de:
        log("LOBBY", f"  ⛔ PAREJA: usn={_yo} y uid={_de} ya son pareja -> nada que hacer")
        return
    if db_pareja_de(_yo) or db_pareja_de(_de):
        if not PAREJA_CAMBIAR_COMO_ORIGINAL:
            log("LOBBY", f"  ⛔ PAREJA: uno de los dos se casó mientras el cartel estaba abierto")
            return
        # ★★★ COMO EL ORIGINAL: casarse con otro TERMINA la relación actual (str#134 del cliente:
        #   «Al aceptar este anillo, cancelará su relación actual»). Con la MISMA ruptura de
        #   siempre: avisos a los ex, adorno de la sala borrado y recuerdo en la mochila.
        for _u in (_yo, _de):
            if db_pareja_de(_u):
                _romper_relacion(_u, " (se casó con otro)")
    # ★ Las OTRAS propuestas que tenía abiertas quedan contestadas con un «no»: si no, sus
    #   proponentes se quedarían esperando (y bloqueados por el error 2) hasta que venzan.
    for _otro_de in list(PENDIENTES.pop(_yo, {}) or {}):
        _mandar(_otro_de, _s2c_rechazo(_yo, _nick_de(_yo)),
                f"FF40/0x0A/03 «{_nick_de(_yo)} ha rechazado la propuesta» (aceptó otra)")
        log("LOBBY", f"  ★ PAREJA: la propuesta de uid={_otro_de} a usn={_yo} queda rechazada "
                     f"(aceptó la de uid={_de})")
    db_poner_pareja(_yo, _de)
    # ★★★ Y SE GUARDA QUÉ ANILLO ES. Sin esto el enlace de la sala se dibuja con ítem 0 y sale
    #   vacío: el cliente pinta los corazones, el fondo del slot y el efecto ÉL SOLO, pero
    #   necesita el número del anillo para buscar su `SlotBackId`/`RoomFx` en `ring.txt`.
    #   ⚠ Se traduce ChargeId -> Index: por el cable viaja el ChargeId, el que dibuja quiere el otro.
    from .catalogo import anillo_por_charge
    _item = anillo_por_charge(_charge)
    if _item:
        db_poner_anillo(_yo, _item, _de)
        # ★★★ Y EL ANILLO TAMBIÉN AL QUE ACEPTA (2026-09-12). ⛔ Medido antes de tocar nada: el
        #   que propuso tenía los 3 anillos y la que aceptó **ninguno** ⇒ su mochila no tenía de
        #   dónde colgar el recuerdo y el aniversario lo veía uno solo de los dos.
        #   ⚠ Al que propuso NO se le saca: el anillo **es** el recuerdo. La regla 5 de la tienda
        #     (*"no se puede reutilizar"*) la cumple el `estado` de la tabla `anillos`, no borrar
        #     el ítem — borrarlo sería borrar justo lo que esto viene a crear.
        if PAREJA_ANILLO_AL_QUE_ACEPTA:
            db_add_inventory(_yo, _item)
    else:
        log("LOBBY", f"  ⚠ PAREJA: el chargeId={_charge} no está en ring.txt -> sin anillo que "
                     f"dibujar en la sala (la pareja igual queda hecha)")
    # ★ El itemAnillo va con el chargeId de la propuesta: es el anillo que eligió el que propuso.
    _mandar(_de, _s2c_aceptado(0x04, _yo, _nick_de(_yo), _charge, _nick_de(_de)),
            f"FF40/0x0A/04 «{_nick_de(_yo)} aceptó tu propuesta»")
    st.send_ff55(0x40, _s2c_aceptado(0x08, _de, _nick_de(_de), _charge, _nick_de(_yo)),
                 name=f"FF40/0x0A/08 confirmación: ahora sos pareja de {_nick_de(_de)!r}")
    # ★★★ LA ANIMACIÓN DEL "SÍ": asiente + voz `nod_<sexo>`. Es el sub 1, el único que lleva
    #   el itemId del anillo adentro.
    #
    #   ⛔ EL INFORME DEL AGENTE DECÍA QUE ESTE SUB ERA INUSABLE porque arrastra un cartel
    #     obligatorio con `str#158` **vacío**, y que saldría *" & <nombre>"*. **Es falso**, y se ve
    #     mirando los cuatro textos juntos en vez de uno solo:
    #         158 = (vacío)   ·   159 = " &"   ·   160 = "ha llegado."
    #     El cartel se COMPONE: `"" + nombre1 + " &" + nombre2 + "ha llegado."`
    #     ⇒ **"jugador6 & jugador34 ha llegado."** El 158 vacío es un prefijo vacío a propósito, no
    #       un renglón que se perdió. ⇒ No hay que tocar el cliente ni reempacar nada.
    #   ★ La lección, otra vez la misma de la noche: **un texto vacío no es un texto faltante**;
    #     hay que mirar la frase entera antes de declarar roto un renglón.
    _animar_en_sala(st, 1, _nick_de(_de), _nick_de(_yo), item=_item)
    # ★★ Y que el enlace aparezca YA, sin tener que salir y volver a entrar a la sala.
    try:
        from .lobby_salas import refrescar_enlaces_de_pareja
        _r8 = getattr(st, "room_id", None)
        if _r8 is not None:
            refrescar_enlaces_de_pareja(_r8, " (se casaron)")
    except Exception as _e8:                                     # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude dibujar el enlace recién casado: {_e8!r}")
    # ★★ Y EL REGISTRO DEL ANILLO A LOS DOS: el ítem de la mochila pasa a mostrar el nombre de la
    #   pareja y la fecha de HOY. Sin esto sólo aparecería al próximo login.
    refrescar_registro((_yo, _de), " (se casaron)")
    log("LOBBY", f"  ★★★ PAREJA NUEVA: usn={_yo} ({_nick_de(_yo)!r}) + uid={_de} "
                 f"({_nick_de(_de)!r}), anillo chargeId={_charge}")
    # ★★ Y EL CARTEL PARA TODO EL SERVER. Va al final, después de casarlos: si algo fallara
    #   antes, no queremos haber anunciado una boda que no ocurrió.
    _anunciar_boda(_charge, _nick_de(_de), _nick_de(_yo))


def _romper(st, data):
    """C2S `0x0A/07` — romper. S2C `[0x0A][0x07][u32]` → str#155. **[M]** (§2.4 del mapa social)"""
    _romper_relacion(int(getattr(st, "usn", 0) or 0))


def _romper_relacion(_yo, motivo=" (rompieron)"):
    """Termina la pareja de `_yo`, con todo lo que eso lleva. ★ Una sola ruptura para los dos
    caminos: el botón «romper» y casarse con otro (`PAREJA_CAMBIAR_COMO_ORIGINAL`).
    Devuelve el uid del ex, o 0."""
    _ex = db_romper_pareja(_yo)
    if not _ex:
        return 0
    _p = bytes([0x0A, 0x07]) + struct.pack("<I", _yo & 0xFFFFFFFF)
    _mandar(_ex, _p, f"FF40/0x0A/07 «{_nick_de(_yo)} ha terminado la relación»{motivo}")
    _mandar(_yo, bytes([0x0A, 0x07]) + struct.pack("<I", _ex & 0xFFFFFFFF),
            f"FF40/0x0A/07 rompiste la pareja{motivo}")
    # ★★ Y HAY QUE BORRAR EL ENLACE DE LA SALA. Sin esto la base queda bien pero el recuadro y el
    #   efecto siguen dibujados: el cliente no se entera solo de que dejaron de ser pareja.
    #   Reportado por anonimo03: *"romper/terminar no funcionó"* — en el server SÍ había funcionado.
    try:
        from .lobby_salas import refrescar_enlaces_de_pareja
        for _u7 in (_yo, _ex):
            _c7 = CONEXIONES.get(int(_u7))
            _r7 = getattr(_c7, "room_id", None) if _c7 is not None else None
            if _r7 is not None:
                # ★ `forzar`: los dos ACABAN de quedar solteros, así que sin esto la función
                #   los saltearía y el enlace viejo quedaría dibujado. Ver su docstring.
                refrescar_enlaces_de_pareja(_r7, motivo, forzar=(_yo, _ex))
                # ★★★ Y EL APAGADO NATIVO, que es lo que de verdad borra el adorno: el refresco
                #   de arriba, con PAREJA_REFRESCO_FF15=False, sólo repinta equipos.
                apagar_enlace_en_sala(_r7, (_nick_de(_yo), _nick_de(_ex)), motivo)
    except Exception as _e7:                                     # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude borrar el enlace tras romper: {_e7!r}")
    # ★★ Y EL RECUERDO. La fila del anillo ya NO se borra: queda con `estado=2` y la fecha de la
    #   ruptura, así que este refresco cambia el ítem de la mochila de *"Registrarse como pareja
    #   con X"* a *"Terminar la relación de pareja con X"*, con las DOS fechas.
    refrescar_registro((_yo, _ex), motivo)
    log("LOBBY", f"  ★ PAREJA ROTA: usn={_yo} y uid={_ex} ya no son pareja{motivo}")
    return _ex


def h_ff40_pareja(st, cmd, data):
    """El despacho del `FF40` sub `0x0A` por su **sub2** (el 2º byte).

    ⚠ El `0x0A` es un sub-sub-dispatcher: 18 sub2, y el **9 no tiene handler** ni acá ni en el
      cliente. Acá se atienden los que el jugador puede disparar hoy.
    """
    _sub2 = data[1] if len(data) > 1 else 0xFF
    try:
        if _sub2 == 0x00:
            _proponer(st, data)
        elif _sub2 == 0x04:
            _responder(st, data, acepta=True)
        elif _sub2 == 0x03:
            _responder(st, data, acepta=False)
        elif _sub2 == 0x05:
            # ★ cancelar la propuesta que mandé (la X de «Propuesta entregada»). El C2S no trae a
            #   quién (`0A 05` pelado): cada uno tiene UNA saliente, así que se busca por valor.
            # ⛔ Antes sólo se borraba de la lista y NO SE AVISABA A NADIE: el renglón quedaba en
            #   los dos paneles y la X "no hacía nada" (anonimo03, 23-sep).
            _yo = int(getattr(st, "usn", 0) or 0)
            for _d in list(PENDIENTES):
                if (PENDIENTES.get(_d) or {}).pop(_yo, None) is not None:
                    _mandar(_d, _s2c_cancelada(_yo, _nick_de(_yo)),
                            f"FF40/0x0A/05 «{_nick_de(_yo)} ha cancelado la propuesta»")
                    log("LOBBY", f"  ★ PAREJA: usn={_yo} canceló su propuesta a uid={_d}")
                if not PENDIENTES.get(_d):
                    PENDIENTES.pop(_d, None)
            st.send_ff55(0x40, _s2c_cancele(max(0, PAREJA_TOPE_DIARIO - _enviadas_hoy(_yo))),
                         name="FF40/0x0A/0C «usted ha cancelado la propuesta» (str#152)")
        elif _sub2 == 0x07:
            _romper(st, data)
        elif _sub2 == 0x0F:
            # ★ «Cambiar anillos de pareja», sin romper la relación. Ver `_cambiar_anillo`.
            _cambiar_anillo(st, data)
        else:
            log("LOBBY", f"  · FF40/0x0A sub2={_sub2:#04x} sin handler todavía "
                         f"({len(data)} B): {data.hex(' ')}")
    except Exception as e:                                       # noqa: BLE001
        # ⚠ Un error acá NO puede tumbar la conexión: es una propuesta, no el login.
        log("LOBBY", f"  ⛔ PAREJA: el handler del sub2={_sub2:#04x} reventó: {e!r}")


def h_ff40_ficha(st, cmd, data):
    """El `FF40` sub `0x06`: *"dame la ficha de este jugador"*. Vive acá porque el único camino
    que lo dispara hoy es el panel «Mi Pareja» — si algún día lo pide otra pantalla, se muda."""
    try:
        _pedir_ficha(st, data)
    except Exception as e:                                       # noqa: BLE001
        log("LOBBY", f"  ⛔ FF40/0x06 (ficha) reventó: {e!r}")
