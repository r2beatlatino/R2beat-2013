# -*- coding: utf-8 -*-
"""lobby — la conexión, el reparto de comandos y el arranque del server.

Qué queda acá, y sólo esto:
  · `LobbyConn`      el estado de una conexión: contadores del cifrado, sala, lugar
  · `handle_login`   el handshake del LoginServer
  · `handle_lobby`   el bucle de un cliente conectado
  · `handle_inner`   reparte cada `FFxx` según `despacho.RUTAS`
  · `listener`       un socket por canal
  · `main`           prende todo (lo llama `startserver.py`)

Lo demás salió a su propio archivo: `notas`, `misiones`, `myrecord`, `carrera`, `chat`,
y los lugares de charla se fueron a `salas`. Si buscás quién atiende un comando, mirá
`despacho.py`; si buscás qué archivo abrir, `MAPA.md`.

⚠ `main()` tiene que correr en el módulo IMPORTADO, nunca como script. Ver su docstring:
  arrancarlo como `__main__` deja dos copias del módulo con globals distintos y el
  servidor sirve paquetes armados con la mitad del estado vacío.

"""
import os
from . import shop_catalog
import select                          # ★ 14-oct: los cosméticos se mandan sólo si el destino puede recibir YA
import socket
import struct
import sys
import threading
import time                              # ⚠ lo usa el resumen por minuto del FF3D (handle_inner)
from . import gacha
from . import autoplay_gm
from . import notas

from .ajustes import (
    REGALO_ACTIVO,
    ESPECTADOR_DIFERIDO,
    BIND_IP,
    CANAL_CAPACIDAD,
    TOPE_ENVIO_MS,
    BARRIDO_MESAS_SEG,
    DOBLE_LOGIN_ECHA_AL_ANTERIOR,
    CANALES_2013,
    CANAL_POR_CLAVE,
    CANAL_POR_PUERTO,
    CERRAR_LOBBY_EN_SWITCH,
    CERRAR_LOGIN_EN_RELOGIN,
    CERRAR_LOGIN_TRAS_HANDOFF,
    CHALLENGE_XOR,
    CRUDOS_MUESTRA,
    FF4E_SUBS_SIEMPRE,
    FF4E_SUB_GLOBO,
    FF4E_COSMETICOS,
    FF4E_COSMETICOS_POR_S,
    MODE_RELEVO,
    FF4E_DESPEJA_LA_CLAVE,
    FF4E_LARGO,
    FF4E_LOG,
    FF4E_SALTO_MAXIMO,
    FF55_DESPEJA_LA_CLAVE,
    INSTANCIAS_LUGAR_N,
    KEY_BASE,
    LICENCIA_EN_LOGIN,
    LOBBY_B,
    LOBBY_PORT,
    LOG,
    LOGIN_PORT,
    LUGAR_CAPACIDAD,
    LICENCIA_CLIENTE_AL_TOPE,
    MISIONES_POR_REPLAY,
    MULTICANAL,
    MURO_POR_CANJE_DE_CAT,
    OWNED_SONGS_2013,
    PUBLIC_IP,
    PWD,
    RELOGIN_ESPERA,
    RESYNC_VENTANA,
    TIPOS_LUGAR_CHARLA,
    TOKEN_CFG90,
    _HIFREQ,
    _RESUMIR_RX,
)
from .registro import (
    RESUMIR,
    guardar_log_anterior,
    hx,
    log,
    puerta_paso,
    resumir,
)
from .cifrado import (
    decrypt_ff55,
    encrypt_ff55,
    frame,
    leer_challenge_ff02,
    parse_ff55_inner,
    parse_frames,
    xor14,
)
from .basedatos import (
    db_get_char,
    db_get_nibbles,
    cuenta_crear,
    cuenta_verificar,
    sesion_abrir,
    sesion_valida,
)
from .progresion import (
    cargar_umbrales_exp,
    char_para_banda,
    codigo_cliente,
    licencia_actual,
    nibble_historia,
    nibbles_a_campoE,
    nivel_de_exp,
)
from .paquetes import (
    _entrada_canal,
    resp3_checkver_ack,
    resp4_lobby_login_ok,
)
from .salas import (
    CONEXIONES,
    actualizar_ocupantes_sala,
    crear_lugares_persistentes,
    desregistrar_sala,
    difundir_salida,
    difundir_userlist,
    espectadores_de,
    levantar_jugador,
    mesa_de,
    olvidar_conexion,
    registrar_conexion,
)
from .carrera import (
    anotar_avance,
    anotar_efecto,
    cargar_impulsor_jefe,
    efecto_del_jefe,
    enviar_ff4b,
)

# El módulo se lee con rutas relativas a la RAÍZ del proyecto, no a
# `servidor/`. Viene de cuando todo era un archivo solo; sacarlo rompe la
# lectura de las tablas del cliente (wing.txt / face.txt).
__file__ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server_login2013.py")   # rutas relativas como en el original

# La consola de Windows es cp1252 y revienta al imprimir '★' (★) u otros no-ascii
# (UnicodeEncodeError -> mata el hilo del lobby justo en FF06). Forzamos UTF-8 tolerante.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def get_local_ip():
    """IP del adaptador por el que sale esta maquina. Calcada del server del CBT (`server-clean.py`).
    El UDP connect no manda un solo byte: solo hace que el SO elija la ruta y nos diga que IP usaria."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ★★ 2026-08-05 — LA IP NO SE CLAVA MAS. Antes era la constante "192.168.1.50" y habia que
#   re-sincronizarla a mano (o con launcher.py) cada vez que el DHCP la cambiaba: la trampa #1 del
#   proyecto. El CBT nunca tuvo ese problema porque autodetecta. `R2_IP` la fuerza si hace falta.
#   ⚠ Esto es solo el DEFAULT: el RESP-2 anuncia, por conexion, la IP POR LA QUE EL CLIENTE LLEGO
#   (`conn.getsockname()`), que es lo unico correcto cuando hay varias redes a la vez — el host por
#   Ethernet y la VM por VMnet8 necesitan direcciones DISTINTAS del mismo server.
LOBBY_IP   = os.environ.get("R2_IP") or get_local_ip()
# ═══════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ EL DIÁLOGO CON EL LAUNCHER (2026-09-05)
#   Tres piezas, y las tres viajan con el MISMO framing que usa el cliente (`FF <cmd> <len:u16>`),
#   así que el launcher habla el idioma del juego y no hace falta un puerto ni un protocolo aparte.
#       FF01 con usuario+hash  -> login del launcher   (el juego manda 12 bytes; se distingue solo)
#       FFF0                   -> registrar cuenta     (el juego nunca lo manda)
#   ⚠ La contraseña no viaja ni se guarda en claro: sólo el SHA-256 en hex.
#   Layouts calcados del CBT (`servidor/paquetes.py::parse_login`) para que el launcher de
#   producción pueda ser el mismo código contra los dos servidores.
# ═══════════════════════════════════════════════════════════════════════════════════════════
def leer_login_launcher(payload):
    """`{usuario, hash}` si esto es un login del LAUNCHER; `None` si es el del juego.

    La marca inequívoca es el hash: 64 caracteres hex. El `FF01` del juego mide 12 bytes justos y
    no tiene forma de parecerse a esto.
    """
    if len(payload) < 7:
        return None
    try:
        ulen = payload[5]
        user = payload[6:6 + ulen].decode("ascii")
        hlen = payload[6 + ulen]
        ph = payload[7 + ulen:7 + ulen + hlen].decode("ascii")
    except (IndexError, UnicodeDecodeError):
        return None
    if not user or len(ph) != 64:
        return None
    return {"usuario": user, "hash": ph}


def resp_login_launcher(usn, vcode, ok=True):
    """`[status][usn:u32][4 ceros][len][vcode en ascii HEXADECIMAL de 16 dígitos]`.

    ⛔⛔⛔ ACÁ IBA EN **DECIMAL**, Y ESO DEJÓ A TODO EL MUNDO EN "LOADING" (2026-09-05).
      El razonamiento viejo estaba escrito acá mismo y sonaba impecable: *"va como texto porque de
      ahí sale derecho a la línea de comandos del juego, y ahí es decimal (`_strtoi64` no lee
      hex)"*. Las dos mitades son ciertas — y la conclusión igual estaba mal, porque **entre el
      server y el juego está el LAUNCHER**, y el launcher hace:

          token_dec = int(token, 16)        # ← ¡BASE 16!

      Un decimal como `1644160370605045705` **es hexadecimal válido** (sólo tiene dígitos 0-9), así
      que no falla: se reinterpreta como `0x1644…` = un número de 73 bits. Eso va a la línea de
      comandos, el `_strtoi64` del cliente lo desborda, y llega **`0xFFFFFFFFFFFFFFFF`**.
      Síntoma: el launcher entra bien, el juego arranca, y se queda en LOADING para siempre.

    ★ El CBT lo emite así: `f"{secrets.randbits(62):016X}"`. Copiamos ESO, que es lo que el
      launcher compartido espera. El launcher lo pasa a decimal y recién ahí llega al cliente.

    ⇒ Y la lección: nuestro launcher andaba porque leía el token en decimal, o sea que **las dos
      puntas nuestras estaban de acuerdo entre ellas y en desacuerdo con el mundo**. Probar el
      contrato contra la herramienta de PRODUCCIÓN, no contra la propia.
    """
    if not ok:
        return frame(0x01, bytes([0x01]) + struct.pack("<I", 0) + bytes(4) + bytes([0]))
    t = f"{int(vcode):016X}".encode("ascii")
    return frame(0x01, bytes([0x00]) + struct.pack("<I", int(usn)) + bytes(4)
                 + bytes([len(t)]) + t)


def leer_registro(payload):
    """`[ulen][user][hlen][hash]` -> `(usuario, hash)`, o `(None, None)`."""
    try:
        ulen = payload[0]
        user = payload[1:1 + ulen].decode("ascii")
        hlen = payload[1 + ulen]
        ph = payload[2 + ulen:2 + ulen + hlen].decode("ascii")
        return user, ph
    except (IndexError, UnicodeDecodeError):
        return None, None


def resp_registro(usn, err):
    """`[status:u8][largo:u8][mensaje]` — el contrato del LAUNCHER COMPARTIDO con el CBT.

        status 0 = cuenta creada  ·  1 = ese usuario ya existe  ·  2 = cualquier otro error

    ⛔⛔ 2026-09-05: esto NO cumplía el contrato y se destapó probando el launcher de producción
    (`online-dist` v1.8) contra este server:
      · el ÉXITO mandaba `[00][usn:u32]`. El launcher lee el 2º byte como LARGO del mensaje, así
        que con `usn=51` creía que venían 51 bytes de texto y mostraba los 3 bytes del usn como
        basura (`'\\x00\\x00\\x00'`). Nunca reventó porque el launcher hace `msg or "cuenta creada"`,
        pero el cable estaba mal y con otro usn mostraría cualquier cosa.
      · TODO error contestaba `1` = "ese usuario ya existe", incluso "el usuario tiene que ser de
        3 a 16 caracteres". El launcher tiene un texto por defecto para el 1 y lo habría mostrado
        si el motivo viniera vacío.
    El `usn` NO hace falta en la respuesta: el launcher no lo usa al registrar — se loguea después.
    """
    if usn:
        m = "cuenta creada".encode("utf-8")
        return frame(0xF0, bytes([0x00, len(m)]) + m)
    motivo = err or "no se pudo"
    st = 0x01 if "ya existe" in motivo.lower() else 0x02
    m = motivo.encode("utf-8")[:200]
    return frame(0xF0, bytes([st, len(m)]) + m)


def resp1_login_ok(usn=0):
    """RESP-1 CmdLogin status=0. payload 0x1C=28 bytes. Eco del usn del cliente."""
    # ⛔⛔ 29-sep: era `db_get_char(usn) or {}` ⇒ en la PRIMERA entrada de una cuenta recién
    #   registrada (el personaje se crea después, ya adentro) viajaba exp 0 = NIVEL 1 y el cliente se
    #   iba solo a «Principiante», donde queda encerrado. El muro de canal ya usaba la plantilla
    #   (`char_para_banda`); acá faltaba. Antes no se notaba: la licencia Luna de la plantilla vieja
    #   lo mandaba a Luna igual.
    char = char_para_banda(usn) or {}
    # ⛔ 2026-07-31: el default era **20000**, que son justo **nivel 5** ⇒ toda cuenta RECIÉN CREADA
    #   (que no trae la clave `exp`) nacía en nivel 5 sin que nadie lo pidiera. Se veía como "la cuenta
    #   nueva empezó en nivel 5". El default correcto para un personaje virgen es **0**.
    exp  = int(char.get("exp", 0))      # ★ EXP de la DB -> campo D (cfg+0x2D0). El cliente DERIVA el nivel
                                        #   por tabla de umbrales (0x8782a0): 20000 => nivel 5 (barra 20000/21564).
    p  = b"\x00"                        # status = 0  (DEBE ser 0)
    p += struct.pack("<I", usn)         # USN u32   -> cfg+0x7C
    p += b"\x00"                        # B  u8
    p += b"\x00\x00"                    # C  u16
    p += b"\x00"                        # lenN1 = 0  (str1 vacio)
    name = b"asdasdasd"                 # nombre login -> cfg+0x170 (NO es el apodo; el apodo es MyRecord @27)
    p += bytes([len(name)]) + name      # lenN2 + nombre  (length-prefijado; layout variable, no fijo 0x1C)
    p += struct.pack("<I", exp)         # D u32 -> cfg+0x2D0 = EXP crudo (de la DB). El nivel sale del umbral.
                                        #   ⚠ niveles muy altos cambian el tier de canal (Luna/Sol) que el server
                                        #   no soporta aun -> loading hang (exp 99/70 colgaron). 20000 (nivel 5) OK.
    # ★★ 2026-07-31: el replay del FF125 sólo alcanza a las misiones CON id. Las de **id 0 de los
    #   grupos 2 y 3** (p.ej. "Licencia Canal Novato Lunar", máscara 0x0010) no tienen por dónde
    #   replayearse ⇒ para ésas el NIBBLE sigue siendo la única vía. Se manda el grupo 1 en 0 (lo
    #   cubre el replay, y ponerlo arrastraría las máscaras 1..n) y los grupos 2/3 reales.
    _nib = db_get_nibbles(usn)
    if MISIONES_POR_REPLAY and not char.get("misiones_todas"):
        # ★ 29-sep: el grupo 1 ya no va en 0 sino en su tramo CONTIGUO (`nibble_historia`): sin
        #   eso el «Anillo del Amor» (id 0) se borraba en cada login y trababa la cadena de atrás.
        _nib = [nibble_historia(char), _nib[1], _nib[2]]
    # ★★★★★ Y ACÁ SE LE SUBE LA LICENCIA AL CLIENTE, PARA QUE VEA TODAS LAS SALAS — 2026-09-17.
    #   anonimo03: *"las salas deberían listarse para todos, sin importar nivel ni licencia, y deberían
    #   salir con el ícono correcto"*. El cliente esconde de la lista toda sala de banda mayor que
    #   la suya, y la suya la calcula de la EXP con tope 2 ⇒ luna no veía las salas de sol.
    #   ★★ `nibble2 = 1` hace que `0x48AC20` otorgue el requisito `0x0100` (record 17) y con eso
    #     `0x4863C0` devuelve **6**. Una sola vuelta del bucle ⇒ **no sobre-marca ninguna otra**.
    #   ⚠ Va sobre la COPIA que viaja en el paquete, nunca sobre `mision_nibbles` de la base: el
    #     ícono del jugador (`paquetes.mision_para_icono`) tiene que seguir mostrando su avance
    #     real. Por eso `max(...)` y no una asignación: a quien ya tenga más, no se le baja.
    #   Ver `documentacion/LICENCIA_DE_SALA_Y_SU_ICONO.md` §5-ter.
    # ⛔⛔ REVERTIDO EL MISMO DÍA — y el motivo vale más que el código, así que queda escrito.
    #   Acá se subía el `nibble2` a 1 para que el cliente se creyera licencia 6 y no escondiera las
    #   salas de banda alta. Funcionaba… y le corría la licencia a TODO el servidor: anonimo03, que es
    #   **luna**, se veía como «novato sol» y el cliente lo mandaba a ese canal (`0x4A1640`, cuya
    #   rama pide `licencia == 6`). *"yo era luna XD"*.
    #   ★ Y la razón de fondo, medida: **el login sólo sabe pronunciar 2 de las 5 licencias**. Los
    #     requisitos de estrella, luna y sol (`0x0F01/02/04`) piden dos nibbles a la vez y el bucle
    #     `0x48AC20` otorga de a uno. No existe la combinación que diga «luna». ⇒ darle la más alta
    #     que el login SABE decir era darle una que no es la suya.
    #   ⇒ Se resolvió con los tres parches del ícono (`herramientas/aplicar_parches.py`), que **no
    #     tocan la licencia del jugador** y por eso no le corren ni la info ni el canal.
    #   Todo el hilo en `documentacion/LICENCIA_DE_SALA_Y_SU_ICONO.md` §5-ter.
    if LICENCIA_CLIENTE_AL_TOPE:
        _nib = [_nib[0], _nib[1], max(int(_nib[2] or 0), 1)]
    # ★ LA ESCAPATORIA `misiones_todas` (2026-09-05). El grupo 1 se apaga porque el nibble otorga
    #   las mascaras **1..n en fila** y SOBRE-MARCA misiones que el jugador no jugo. Pero para un
    #   personaje que tiene que tener TODO hecho eso deja de ser un problema: es justo lo que se
    #   quiere. Y hace falta, porque **"Anillo del Amor" (mascara 0x0004) tiene id 0**, o sea que el
    #   replay del FF125 no la alcanza (`0x48A5E0` devuelve 0 con id 0) y el nibble es su UNICA via.
    #   Con la bandera en el personaje, el resto de las cuentas sigue exactamente igual.
    p += struct.pack("<H", nibbles_a_campoE(_nib))
                                        # ★★★ E u16 -> 0x48B720 = NIBBLES DE MISIONES HECHAS.
                                        #   Es lo que RESTAURA el "hecha" por-misión al reloguear
                                        #   (el MyRecord sólo trae el contador de lecciones).
    p += struct.pack("<I", licencia_actual(usn)[2] if LICENCIA_EN_LOGIN else 0)
                                        # F u32 -> cfg+0x664 = ★ EL MISMO destino que el @19 del MyRecord.
                                        #   PROBANDO: mandar la licencia ACA (el login llega ANTES de la
                                        #   lista de canales) a ver si el cliente ya calcula su codigo con
                                        #   la licencia puesta y elige el canal correcto SIN el canje de cat.
    p += b"\x07" + b"notoken"           # lenTok=7 + "notoken" (sin auto-login)
    return frame(0x01, p)

def resp2_lobby_list(ip=LOBBY_IP, port=LOBBY_PORT, name="Novato Estrella", usn=0):
    """RESP-2 CmdLobbyServerList. Con MULTICANAL=True publica LOS 8 CANALES REALES del 2013
    (uno por puerto, como el CBT); con False, la entrada única histórica."""
    if not MULTICANAL:
        return frame(0x02, b"\x01" + _entrada_canal(0, ip, port, 0x63, name))

    # ★★ EL MURO DE CANAL, SERVER-SIDE. El cliente conecta a la entrada cuyo `cat` matchea el código
    #    que él mismo calcula (`0x486E90`), y **por NIVEL ese código nunca pasa de 2 = starchobo**:
    #    Estrella/Luna/Sol dependen de ítems y flags de licencia del objeto player, que todavía no
    #    sabemos setear. ⇒ Para mandar al jugador a la banda que le toca por nivel, se INTERCAMBIA el
    #    `cat` del canal que le corresponde con el del canal que su código matchearía. Nadie duplica
    #    cat, los 8 canales siguen existiendo, y el cliente aterriza donde queremos.
    exp    = int(char_para_banda(usn).get("exp", 0))     # ★ sin char todavía = la plantilla
    nivel  = nivel_de_exp(exp)
    clave, _tier, _lic = licencia_actual(usn)
    cat_natural = CANAL_POR_CLAVE[clave][0] if clave in CANAL_POR_CLAVE else None
    codigo      = codigo_cliente(nivel, _lic)
    cat_codigo  = next((c[0] for c in CANALES_2013 if c[3] == codigo), None)

    cats = {c[4]: c[0] for c in CANALES_2013}
    if MURO_POR_CANJE_DE_CAT and cat_natural is not None and cat_codigo is not None and cat_natural != cat_codigo:
        clave_codigo = next(c[4] for c in CANALES_2013 if c[0] == cat_codigo)
        cats[clave], cats[clave_codigo] = cat_codigo, cat_natural
        log("LOGIN", f"  ★★ MURO DE CANAL: exp={exp} -> nivel {nivel} -> banda {clave!r}. El código del "
                     f"cliente por nivel es {codigo} ({clave_codigo!r}), así que se INTERCAMBIAN los cat "
                     f"0x{cat_natural:02X} <-> 0x{cat_codigo:02X} para que aterrice en {clave!r}.")
    else:
        log("LOGIN", f"  ★ MURO DE CANAL: exp={exp} -> nivel {nivel} -> banda {clave!r} "
                     f"(licencia @19 = {_lic}; sin canje de cat — que elija el cliente).")

    # ★★★★ CUÁNTA GENTE HAY EN CADA CANAL — 2026-09-09, reportado por anonimo03: *"el estado de
    #   llenado del canal no está funcionando"*.
    #   ⛔ `_entrada_canal` tiene `users=1` por defecto y **ninguno de los dos sitios que la
    #     llamaban se lo pasaba**, así que los 8 canales decían siempre «1 de 100». La barra no
    #     estaba rota: le mandábamos un 1 clavado desde el primer día.
    #   ★ El REFERENTE sí manda los de verdad (visto en la captura del 2026-09-02):
    #       'Principiantes' 0/100 · 'Novato lunar' 10/100 · **'Libre' 52/500**
    #   ⚠ Se cuenta por `st.canal`, que es de dónde SALE cada conexión viva (`CANAL_POR_PUERTO`),
    #     y se saltean las cerradas: una conexión muerta seguiría sumando y el canal se vería
    #     lleno para siempre.
    _pobl = {}
    for _c in list(CONEXIONES.values()):
        if getattr(_c, "cerrado", False):
            continue
        _ck = getattr(_c, "canal", None)
        if _ck:
            _pobl[_ck] = _pobl.get(_ck, 0) + 1
    p = bytes([len(CANALES_2013)])
    for i, (_cat, _t1, _t2, _code, ck, nombre, puerto) in enumerate(CANALES_2013):
        p += _entrada_canal(i, ip, puerto, cats[ck], nombre,
                            users=min(_pobl.get(ck, 0), CANAL_CAPACIDAD - 1),
                            cap=CANAL_CAPACIDAD)
    if _pobl:
        log("LOGIN", f"  ★ población de los canales: "
                     + " · ".join(f"{k}={v}" for k, v in sorted(_pobl.items())))
    return frame(0x02, p)


class LobbyConn:
    """Estado por-conexion de la Lobby: buffer + crypto FF55 (pwd + contadores separados)."""
    def __init__(self, conn, addr):
        self.conn = conn; self.addr = addr; self.buf = b""
        self.pwd = PWD; self.key_base = KEY_BASE
        self.recv_counter = 0            # C->S (descifrar): espejo de [sess+0x21b5c] del cliente
        self.send_counter = 0            # S->C (cifrar):    espejo de [sess+0x21b60] del cliente
        self.crypto_ready = False        # True tras RESP-4 (ya hay pwd)
        # ★★ 2026-08-05 — CANDADO DE ENVIO. Desde que hay salas compartidas, el hilo de UN jugador le
        #   manda paquetes a OTRO (el FF0C de "entró alguien"). `send_counter` es el contador del
        #   cifrado: si dos hilos lo tocan a la vez, dos paquetes salen con el mismo contador y el
        #   cliente NO puede descifrar el segundo. Es una carrera que aparecería como
        #   "FF55 NO descifro" esporádico, o sea de las peores de diagnosticar.
        self.tx_lock = threading.Lock()
        self.hifreq = {}                 # conteo de inner de alta frecuencia (FF3D/FF00)
        self.crudos = {}                 # conteo de frames SUELTOS sin handler (gameplay: 0x4E y cia)
        self.hifreq_payloads = {}        # {cmd: {payloads ya vistos}} — para no esconder uno nuevo
        self.hifreq_ultimo = {}          # {cmd: cuándo se logueó por última vez} — 1 línea/minuto
        self.hifreq_marca_n = {}         # {cmd: conteo en esa marca}
        # ★ identidad de ESTA conexión. Se siembra con el `usn` que manda el cliente
        #   (FF01 en el login, FF02 en la lobby), que sale de `atoi(argv[1])`.
        self.usn = 0

    def send_plain(self, data, name=""):
        if getattr(self, "cerrado", False):   # ver la nota en send_ff55 (cierre por cambio de canal)
            return
        if not puerta_paso(f"{name or 'en claro'}  ({len(data)} B)", hx(data[:32])):
            return
        self.conn.sendall(data)
        log("LOBBY", f"TX {name} : {hx(data)}")

    def send_ff55(self, cmd, data=b"", name=""):
        """Envia un comando interno cifrado: FF55( enc( FF56<pad> FF<cmd><data> ) )."""
        # ★ Tras el cierre por CAMBIO DE CANAL (`FF3D`) el socket queda a medio cerrar, pero el
        #   dispatcher sigue procesando los comandos que ya venían en el buffer y alguno intenta
        #   contestar -> `BrokenPipeError 10058`, que en el log parece un bug y no lo es.
        if getattr(self, "cerrado", False):
            return
        if not puerta_paso(f"FF55(inner FF{cmd:02X})  {len(data)} B   {name}",
                           hx(data[:32]) + (" ..." if len(data) > 32 else "")):
            return
        pad = os.urandom(4)
        prefix = 0xFE if cmd >= 0x100 else 0xFF
        inner = (b"\xFF\x56" + struct.pack("<H", len(pad)) + pad
                 + bytes([prefix, cmd & 0xFF]) + struct.pack("<H", len(data)) + data)
        # ★ cifrar + numerar + mandar es UNA sola operación atómica (ver `tx_lock` en __init__).
        with self.tx_lock:
            edx = (self.key_base ^ self.send_counter) & 0xFFFFFFFF
            enc = encrypt_ff55(inner, self.pwd, edx)
            ctr = self.send_counter
            self.send_counter += 1
            self.conn.sendall(b"\xFF\x55" + struct.pack("<H", len(enc)) + enc)
        if name is RESUMIR:                  # ★ alta frecuencia: se cuenta, no se loguea uno por uno
            resumir(f"TX FF{cmd:02X}")
        else:
            log("LOBBY", f"TX FF55(inner FF{cmd:02X} {len(data)}B) send_ctr={ctr} {name}")

    def send_ff4e(self, sub, A, B, name=""):
        """Manda un inner `0x26` dentro del sobre `0x4E`, **en claro** (sin la ofuscación del magic).

        ⚠ Usa el MISMO `send_counter` que el FF55: el cliente lleva un solo contador de recepción
        para los dos. Numerarlos por separado le rompería el descifrado de todo lo demás.
        """
        if getattr(self, "cerrado", False):
            return
        inner = b"\xFF\x26" + struct.pack("<H", 9) + bytes([sub & 0xFF]) \
                + struct.pack("<I", A & 0xFFFFFFFF) + struct.pack("<I", B & 0xFFFFFFFF)
        with self.tx_lock:
            key = (self.key_base ^ self.send_counter) & 0xFFFFFFFF
            enc = xor14(inner, key)
            ctr = self.send_counter
            self.send_counter += 1
            self.conn.sendall(b"\xFF\x4E" + struct.pack("<H", len(enc)) + enc)
        if FF4E_LOG:
            log("LOBBY", f"TX FF4E(inner 0x26 sub=0x{sub:02X} A=0x{A:08X} B=0x{B:08X}) "
                         f"send_ctr={ctr} {name}")

    def send_ff4e_si_puede(self, sub, A, B):
        """★ 14-oct · PAQUETES_ESPECTADOR.md §3.2: un FF4E COSMÉTICO (globo / calculadora) que se manda sólo si se puede
        YA. Si otro hilo está mandándole a esta conexión (el candado ocupado) o su buffer TCP está lleno (red mala),
        se TIRA: un espectador lento no puede frenar el hilo del corredor que lo reenvía. Sin log."""
        if getattr(self, "cerrado", False) or not self.tx_lock.acquire(blocking=False):
            return False
        try:
            try:
                if not select.select((), (self.conn,), (), 0)[1]:
                    return False
            except (OSError, ValueError):
                return False
            inner = b"\xFF\x26" + struct.pack("<H", 9) + bytes([sub & 0xFF]) \
                + struct.pack("<I", A & 0xFFFFFFFF) + struct.pack("<I", B & 0xFFFFFFFF)
            enc = xor14(inner, (self.key_base ^ self.send_counter) & 0xFFFFFFFF)
            self.send_counter += 1
            self.conn.sendall(b"\xFF\x4E" + struct.pack("<H", len(enc)) + enc)
            return True
        finally:
            self.tx_lock.release()

    def tope_cosmetico(self):
        """★ 14-oct · PAQUETES_ESPECTADOR.md §3.6: cubeta de fichas por conexión (FF4E_COSMETICOS_POR_S, ráfaga el
        doble). False = tirar (un cliente que manda de más, por bug o trucho). Se cuenta y se avisa 1 vez por minuto."""
        ahora = time.monotonic()
        fichas = getattr(self, "_cosm_fichas", 2.0 * FF4E_COSMETICOS_POR_S)
        fichas = min(2.0 * FF4E_COSMETICOS_POR_S, fichas + (ahora - getattr(self, "_cosm_t", ahora)) * FF4E_COSMETICOS_POR_S)
        self._cosm_t = ahora
        if fichas < 1.0:
            self._cosm_fichas = fichas
            self._cosm_tirados = getattr(self, "_cosm_tirados", 0) + 1
            if ahora - getattr(self, "_cosm_aviso", 0.0) > 60:
                self._cosm_aviso = ahora
                log("LOBBY", f"  ⚠ usn={getattr(self, 'usn', '?')} manda de más cosméticos FF4E: "
                             f"{self._cosm_tirados} tirados (tope {FF4E_COSMETICOS_POR_S}/s)")
            return False
        self._cosm_fichas = fichas - 1.0
        return True

    CABECERA_FF55 = b"\xFF\x56"              # el claro con el que empieza TODO inner del FF55

    def _descifrar_ff55_por_rv(self, payload):
        """Resuelve `rv` (256 valores) en vez de adivinar el contador (4096). Exhaustivo y exacto.

        `rv` es **toda** la clave que usa este cifrado, así que probarlos todos no es un barrido a
        ciegas: es agotar el espacio entero. Se exigen los DOS bytes de la cabecera, no uno —
        con un solo byte, 256 candidatos pasarían igual, que es justo el error de antes.
        """
        if len(payload) < 2:
            return None
        pwd = self.pwd
        for rv in range(256):
            base = pwd[rv] ^ rv
            if (pwd[0] ^ base ^ payload[0]) != 0xFF or (pwd[1] ^ base ^ payload[1]) != 0x56:
                continue
            t = decrypt_ff55(payload, pwd, rv)
            #   ★ El contador ya no hace falta para descifrar, pero se lo mantiene lo más cerca
            #     posible: es el espejo del cliente y el FF4E lo usa para avisar del desfase.
            #     Sólo se corrige el byte bajo, DENTRO del bloque de 256 — jamás un salto grande.
            bajo = (self.key_base ^ rv) & 0xFF
            if (self.recv_counter & 0xFF) != bajo:
                nuevo = (self.recv_counter & 0xFFFFFF00) | bajo
                if FF4E_LOG:
                    log("LOBBY", f"  · FF55: ajusto el byte bajo del reloj {self.recv_counter} "
                                 f"-> {nuevo} (el FF4E es el que lo fija de verdad)")
                self.recv_counter = nuevo
            self.recv_counter = (self.recv_counter + 1) & 0xFFFFFFFF
            return t
        return None

    CABECERA_FF4E = b"\xFF\x26\x0A\x00"      # el texto claro que TODO FF4E del cliente trae delante

    def _abrir_ff4e(self, p):
        """Del claro de 14 B a `(sub, A, B)`. La ofuscación con el `magic` es del juego, no del sobre."""
        largo = struct.unpack("<H", p[2:4])[0]
        if largo != 10 or len(p) < 14:
            return None
        magic = getattr(self, "game_magic", 0) or 0
        sub = p[5] ^ (magic & 0xFF) ^ 0xCA
        A   = (struct.unpack("<I", p[6:10])[0]  ^ magic ^ 0xEF) & 0xFFFFFFFF
        B   = (struct.unpack("<I", p[10:14])[0] ^ magic ^ 0xAB) & 0xFFFFFFFF
        return sub, A, B

    def descifrar_ff4e(self, payload):
        """Descifra un sobre `0x4E`. Devuelve (sub, A, B) ya des-ofuscados, o None.

        ★★ NO SE ADIVINA EL CONTADOR: SE DESPEJA. El sobre es XOR con una clave de 32 bits por
        palabra, y los 4 primeros bytes del claro se conocen siempre (`FF 26 0A 00`), así que

            clave = payload[0:4] XOR CABECERA_FF4E        ctr = clave XOR key_base

        Un paso y exacto, **por grande que sea el desfase** — que es justo lo que rompía el barrido
        de antes: el hueco de prod pasa los 4096 y nunca lo alcanzaba. Ver la nota larga de
        `FF4E_DESPEJA_LA_CLAVE` en `ajustes.py` y la prueba `probar_contador_compartido.py`.

        ⚠ El despeje **no valida**: la cabecera sale por construcción, así que un sobre roto también
        "abre". Por eso el reloj sólo se mueve cuando el salto es sensato (`FF4E_SALTO_MAXIMO`):
        el paquete se entrega igual, pero un sobre roto no puede desacomodarnos el contador.
        """
        if len(payload) < FF4E_LARGO:
            return None

        if not FF4E_DESPEJA_LA_CLAVE:
            #   El barrido de antes, tal cual. Queda como vuelta atrás del interruptor.
            for salto in range(RESYNC_VENTANA):
                ctr = (self.recv_counter + salto) & 0xFFFFFFFF
                p = xor14(payload, (self.key_base ^ ctr) & 0xFFFFFFFF)
                if p[0] != 0xFF or p[1] != 0x26:
                    continue
                if salto:
                    log("LOBBY", f"  ⚠ FF4E resync: el contador saltó {salto}")
                self.recv_counter = (ctr + 1) & 0xFFFFFFFF
                return self._abrir_ff4e(p)
            return None

        clave = struct.unpack("<I", bytes(a ^ b for a, b in
                                          zip(payload[0:4], self.CABECERA_FF4E)))[0]
        abierto = self._abrir_ff4e(xor14(payload, clave))
        if abierto is None:
            return None

        ctr = (clave ^ self.key_base) & 0xFFFFFFFF
        salto = ctr - self.recv_counter
        if abs(salto) > FF4E_SALTO_MAXIMO:
            #   Ni lo descarto ni le creo el reloj: el paquete va, el contador se queda donde está.
            log("LOBBY", f"  ⚠ FF4E con contador absurdo ({ctr} vs {self.recv_counter}): "
                         f"lo entrego igual pero NO muevo el reloj")
            return abierto
        if salto:
            #   ★ ESTA LÍNEA ES EL DATO QUE FALTABA: cuánto se desacomoda el reloj, y cuándo.
            #     Es lo único que puede decirnos QUÉ abre el hueco la primera vez.
            log("LOBBY", f"  ⚠ FF4E: el contador estaba {abs(salto)} "
                         f"{'adelante' if salto < 0 else 'atrás'} ({self.recv_counter} -> {ctr})")
        self.recv_counter = (ctr + 1) & 0xFFFFFFFF
        return abierto

    def decrypt_container(self, payload):
        """Descifra un FF55 entrante probando contadores (like 2011). Devuelve inner o None.

        ★★ RESYNC ANCHO (2026-07-30). La ventana era de 12 y eso ALCANZABA en el lobby, pero NO en
        una carrera: durante el gameplay el cliente mete cientos de FF4E (movimiento) y el contador
        se le va MUY por delante del nuestro. Pasados los 12 de desfase el stream quedaba muerto
        PARA SIEMPRE y todo lo que venia despues se perdia — medido en vivo: a las 16:06 fallo una
        vez y se recupero (desfase chico), a las 16:14 se desincronizo en plena persecucion y ya
        ningun paquete volvio a descifrar, incluido el FF10E del cartel de premio (que parecia el
        culpable del cuelgue y era la VICTIMA).
        ★★★★★ Y ESE BARRIDO NO PODÍA ACERTAR — 2026-09-09. El cifrado es
        `out[i] = pwd[i%256] ^ pwd[rv] ^ rv ^ plain[i]`: lo único que interviene es **`rv`, de 8
        bits**. Medido: para el contador 1000 descifran igual de bien 232, 488, 744, 1000, 1256,
        1512… — **256 candidatos indistinguibles**. El barrido se quedaba con el más bajo y podía
        dejar el contador múltiplos de 256 fuera de lugar, matando al FF4E (que sí lo necesita
        entero). La huella en prod eran cadenas donde cada resync arrancaba justo donde aterrizó el
        anterior. Ver la nota larga de `FF55_DESPEJA_LA_CLAVE` en `ajustes.py`.

        ⇒ Ahora se resuelve **`rv`** (256 valores, exhaustivo) y descifrar deja de depender del
          contador. El contador avanza de a uno y, si el byte bajo no coincide, se corrige DENTRO
          de su bloque de 256 — nunca un salto grande. El que lo fija de verdad es el FF4E."""
        if FF55_DESPEJA_LA_CLAVE:
            return self._descifrar_ff55_por_rv(payload)
        for try_c in range(self.recv_counter, self.recv_counter + 12):
            edx = (self.key_base ^ try_c) & 0xFFFFFFFF
            t = decrypt_ff55(payload, self.pwd, edx)
            if t[:2] == b"\xFF\x56":
                self.recv_counter = try_c + 1
                return t
        base = self.recv_counter
        for try_c in range(base + 12, base + RESYNC_VENTANA):
            edx = (self.key_base ^ try_c) & 0xFFFFFFFF
            t = decrypt_ff55(payload, self.pwd, edx)
            if t[:2] == b"\xFF\x56":
                log("LOBBY", f"  ⚠ RESYNC del contador: {base} -> {try_c + 1} (salto de {try_c - base}). "
                             f"El cliente iba adelantado; sin esto el stream quedaba muerto.")
                self.recv_counter = try_c + 1
                return t
        return None

# --- Dispatch por rol ---
# ★★★★★ LOS LOGIN ABIERTOS, POR `usn` — para poder cerrarlos EN CUANTO haga falta.
#   El cliente descarta en silencio los clics del selector de canales mientras su conexión al
#   LoginServer siga abierta. Cerrarla es LA SEÑAL que lo destraba (ver la nota larga en el FF02
#   de la lobby y en `handle_login`).
#   ⚠ La clave es el **`usn`**, a propósito. La versión anterior de esto usaba `id(socket)` —la
#     dirección de memoria— y Python las RECICLA: un socket nuevo heredaba el estado del viejo y
#     el cierre no se hacía. El `usn` identifica al jugador y no se recicla.
LOGINS_ABIERTOS = {}
_LOGINS_LOCK = threading.Lock()


def cerrar_login_pendiente(usn, motivo=""):
    """Cierra el socket del LoginServer de ese jugador, si todavía hay uno. `True` si cerró algo.

    ⚠ `shutdown` y no `close`: `close` deja el `recv` del hilo de login sobre un descriptor muerto
      (OSError 10038, que en el log parece un bug y no lo es).
    ⚠ Se puede llamar de más: si no hay nada anotado, no hace nada y no se queja.
    """
    try:
        _u = int(usn or 0)
    except (TypeError, ValueError):
        return False
    if not _u:
        return False
    with _LOGINS_LOCK:
        c = LOGINS_ABIERTOS.pop(_u, None)
    if c is None:
        return False
    try:
        c.shutdown(socket.SHUT_RDWR)
        log("LOGIN", f"  ★★ login de usn={_u} CERRADO{motivo} — es lo que apaga la bandera del "
                     f"cliente y deja vivo el selector de canales")
        return True
    except OSError:
        return False


def echar_sesion_anterior(usn, nuevo_st):
    """DOBLE LOGIN: si esa cuenta ya tenia una sesion, se la cierra. Devuelve `True` si echo a alguien.

    ★★★★★ Pedido de anonimo03 el 2026-09-09: *"si el mismo usuario abre otra sesion, la anterior debe
      morir"*. Sin esto quedaban DOS conexiones vivas con el mismo `usn` y `CONEXIONES[usn]` se
      pisaba: la vieja seguia con su socket abierto, su hilo corriendo y su silla en la sala, pero
      ya no le llegaba nada — un fantasma.

    ⚠⚠ LA TRAMPA, Y ES LA PARTE QUE IMPORTA. `levantar_jugador(st)` saca de la mesa **por `usn`**,
      sin mirar QUE conexion es. Si la vieja se muriera DESPUES de que la nueva ya se sento, su
      limpieza le sacaria la silla a la nueva — y el jugador quedaria invisible en su propia sala.
      Es exactamente el mismo error que `olvidar_conexion` ya evita con su `is st`.
      ⇒ Por eso acá se hace **la limpieza AHORA, en orden, y se marca la vieja como `reemplazada`**;
        el `finally` de su hilo ve la marca y NO vuelve a tocar nada compartido.

    ⚠ El cambio de canal pasa por acá todo el tiempo (el cliente re-loguea con el mismo `usn`), y
      está bien: ahí la vieja ya está muriendo y echarla es justo lo que corresponde.
    """
    if not DOBLE_LOGIN_ECHA_AL_ANTERIOR:
        return False
    try:
        _u = int(usn or 0)
    except (TypeError, ValueError):
        return False
    if not _u:
        return False
    viejo = CONEXIONES.get(_u)
    if viejo is None or viejo is nuevo_st:
        return False

    log("LOBBY", f"  ★★★ DOBLE LOGIN de usn={_u}: ya habia una sesion abierta -> se la cierra "
                 f"(la nueva se queda)")
    # 1 · marcarla ANTES de tocar nada: si su hilo despierta en el medio, ya sabe que no le toca
    viejo.reemplazada = True
    viejo.cerrado = True                 # corta los envios que quedaran en vuelo (ver send_ff55)
    # 2 · sacarla de la sala y avisarle a los que quedan, con SUS datos, no los de la nueva
    try:
        _rid, _quedaba = levantar_jugador(viejo)
        if _rid and _quedaba:
            difundir_salida(_rid, viejo)
            difundir_userlist(_rid, menos=viejo, por_salida=True)
            actualizar_ocupantes_sala(_rid)
        if _rid:
            desregistrar_sala(viejo)
    except Exception as e:
        log("LOBBY", f"  ⚠ doble login usn={_u}: no pude limpiar su sala: {e!r}")
    # 3 · sacarla del registro SOLO si sigue siendo ella (nunca la nueva)
    olvidar_conexion(viejo)
    # 4 · y recien ahora el socket. `shutdown` y no `close`: ver la nota de `cerrar_login_pendiente`.
    try:
        viejo.conn.shutdown(socket.SHUT_RDWR)
    except Exception:
        try:
            viejo.conn.close()
        except Exception:
            pass
    return True


def handle_login(conn, addr):
    log("LOGIN", f"conexion desde {addr[0]}:{addr[1]}")
    buf = b""
    # ★ Identidad de ESTA conexión de login. La siembra el FF01 (`atoi(argv[1])` del cliente) y la usa
    #   el FF02 para armar la lista de canales con la banda/licencia del jugador correcto.
    #   Se inicializa acá para que un FF02 que llegara primero no reviente por variable sin definir.
    usn = 0
    # ★★★★★ "¿ESTA CONEXIÓN PIDIÓ EL FF02?" — UNA VARIABLE DE ESTA CONEXIÓN, NO UN DICCIONARIO.
    #   ⛔⛔ ACÁ SE USABA `_pidio_ff02[id(conn)]`, UN DICCIONARIO GLOBAL INDEXADO POR `id()` — o sea
    #     **por la dirección de memoria del socket** — Y QUE NO SE LIMPIABA NUNCA.
    #     Python **reutiliza direcciones**: cuando un socket se libera, el siguiente puede caer en
    #     la misma y **heredar el `True` del anterior**. Ahí este re-login parecía un login normal,
    #     NO cerrábamos el socket, y la bandera del cliente quedaba prendida.
    #
    #   ★ MEDIDO CON FRIDA EL 2026-09-09, con la cuenta `-gekoo-` (`frida_canal.py`):
    #         16:49:19  clic Libre     bandera=0 -> permiso 1 ✔ -> anduvo
    #         16:49:22  clic Estrella  bandera=0 -> permiso 1 ✔ -> anduvo
    #         16:49:26  clic Libre     bandera=1 -> ⛔ el clic MUERE, ni llega al permiso
    #         …y 5 clics más en 8 s, todos con la bandera en 1: **no se bajó nunca**.
    #     Reportado como *"me dejó ir a Libre y regresar un par de veces, luego ya no pudo, y
    #     tampoco salió el popup"*. No sale cartel porque el clic muere ANTES del chequeo.
    #
    #   ★★ Y LA BANDERA TIENE NOMBRE, sacado del propio cliente: la apagan dos funciones que
    #     loguean **`LoginServer : <OnClose>`** y **`LoginServer : <OnConnectionDestroyed>`**
    #     (`0x5C4860` / `0x5C4880`), y la prende `0x5C4A00` al conectar. Significa
    #     **"tengo la conexión al LoginServer abierta"**, y mientras esté en 1 el cliente
    #     descarta cualquier clic de canal (`0x4A68F0`, primera puerta).
    #     ⇒ Cerrar ese socket no es una cortesía: es **la señal** que destraba el selector.
    #
    #   ⚠ Es un bug que ya habíamos arreglado una vez y volvió por la puerta de atrás: la lógica
    #     del cierre estaba bien, lo que fallaba era **cómo se recordaba a quién le tocaba**.
    #     Con una variable local no hay colisión posible ni diccionario que crezca sin fin.
    pidio_ff02 = False
    # SIN timeout de lectura: un lobby real mantiene la conexion abierta indefinidamente.
    # (El timeout de 120s cerraba el socket estando el cliente idle en el lobby -> crash 0x555917.)
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                log("LOGIN", "cliente cerro"); return
            buf += data
            frames, buf = parse_frames(buf)
            for magic, cmd, payload in frames:
                log("LOGIN", f"RX magic=0x{magic:02x} cmd=0x{cmd:02x} len={len(payload)} : {hx(payload)}")
                if magic == 0xFF and cmd == 0x01 and leer_login_launcher(payload):
                    # ═══ EL LAUNCHER, con usuario y contraseña ═══════════════════════════════
                    #   Mismo comando que el juego, pero se distingue por el CUERPO:
                    #       juego    -> 12 bytes  `[usn:u32][vcode:u64]`
                    #       launcher -> `[0:u32][flag:u8][ulen:u8][user][hlen:u8][sha256_hex(64)]`
                    #   Es la forma del CBT (`parse_login`), a propósito: así el launcher de
                    #   producción puede ser el mismo código para los dos servidores.
                    #   ⚠ La contraseña NUNCA viaja en claro: va el SHA-256 en hex.
                    _cred = leer_login_launcher(payload)
                    _usn_cred = cuenta_verificar(_cred["usuario"], _cred["hash"])
                    if _usn_cred is None:
                        conn.sendall(resp_login_launcher(0, 0, ok=False))
                        log("LOGIN", f"  ⛔ LAUNCHER: usuario o clave incorrectos ({_cred['usuario']!r})")
                        continue
                    _vc = sesion_abrir(_usn_cred)
                    conn.sendall(resp_login_launcher(_usn_cred, _vc, ok=True))
                    log("LOGIN", f"  ★★ LAUNCHER OK: {_cred['usuario']!r} -> usn={_usn_cred}, "
                                 f"sesion abierta (vcode de {_vc.bit_length()} bits)")
                elif magic == 0xFF and cmd == 0xF0:
                    # ═══ REGISTRAR CUENTA ═══════════════════════════════════════════════════
                    #   `[ulen:u8][user][hlen:u8][sha256_hex(64)]`. Comando propio launcher↔server
                    #   (el juego no lo manda nunca), heredado del CBT para que el launcher sea
                    #   compartible.
                    _u, _h = leer_registro(payload)
                    _nuevo, _err = cuenta_crear(_u, _h) if _u else (None, "pedido mal formado")
                    conn.sendall(resp_registro(_nuevo, _err))
                    log("LOGIN", (f"  ★★ CUENTA CREADA: {_u!r} -> usn={_nuevo}" if _nuevo
                                  else f"  ⛔ registro rechazado ({_u!r}): {_err}"))
                elif magic == 0xFF and cmd in (0xF1, 0xF2, 0xF3, 0xF4, 0xF5):
                    # ═══ LOS 4 PERSONAJES DE LA CUENTA (21-oct, la landing web) ═════════════════
                    #   FFF1 lista · FFF2 crear en un casillero · FFF3 entrar con uno · FFF4 las
                    #   opciones A/B/C de la creación · FFF5 borrar (24-oct: lo OCULTA). Mismo framing
                    #   que el launcher; cada uno trae usuario + hash. Ver `cuenta_personajes.py`.
                    from . import cuenta_personajes
                    conn.sendall(cuenta_personajes.responder(cmd, payload))
                elif magic == 0xFF and cmd in (0xF6, 0xF7, 0xF8, 0xF9, 0xFA):
                    # ═══ ★★ EL SELECTOR ADENTRO DEL JUEGO (25-oct): la dll, con la SESIÓN ═════════════
                    #   FFF6 hola · FFF7 lista · FFF8 elegir · FFF9 borrar · FFFA volver. Ver
                    #   `cuenta_personajes.responder_sesion` y documentacion/SELECTOR_PERSONAJE.md.
                    from . import cuenta_personajes
                    conn.sendall(cuenta_personajes.responder_sesion(cmd, payload))
                elif magic == 0xFF and cmd == 0xFB:
                    # ═══ ★ (142) LAS MONTURAS: subirse / bajarse / unirse con un clic (la dll, con la SESIÓN) ═══
                    #   FFFB [usn][vcode][accion] -> [resultado][byte]. El 0xF4 del 2019 (CmdGuildRoomAction), en
                    #   nuestro byte del Wing Id. Ver `monturas.py` y documentacion/MONTURAS.md.
                    from . import monturas
                    conn.sendall(monturas.responder(payload))
                elif magic == 0xFF and cmd == 0x01:
                    # CmdLogin req: [usn:u32][vcode:u64].
                    usn = struct.unpack("<I", payload[:4])[0] if len(payload) >= 4 else 0
                    vcode = struct.unpack("<Q", payload[4:12])[0] if len(payload) >= 12 else 0
                    if not sesion_valida(usn, vcode):
                        log("LOGIN", f"  ⛔ RECHAZADO usn={usn} vcode={vcode}: no hay sesion abierta "
                                     f"(el launcher es el unico que reparte pares validos)")
                        try:
                            conn.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        return
                    r = resp1_login_ok(usn)
                    if puerta_paso(f"RESP-1 CmdLogin OK (usn={usn})  {len(r)} B", hx(r[:32]), handshake=True):
                        conn.sendall(r)
                        log("LOGIN", f"TX RESP-1 CmdLogin OK (usn={usn}) : {hx(r)}")
                    # ★★★★★ EL PICKER DE CANALES MORÍA DESPUÉS DEL PRIMER CAMBIO — ACÁ ESTABA.
                    #   El botón OK del selector arranca con `cmp byte [[0x9D43D8]+0x20420],0 ; jne salir`.
                    #   Ese byte = "sesión de LOGIN abierta": lo PRENDE el `FF01 LOGIN OK` y lo APAGA el
                    #   `LoginServer::OnClose` del cliente. Nosotros cerrábamos el socket **al recibir el
                    #   FF02**… pero en el RE-LOGIN de un cambio de canal el cliente **NO pide el FF02**:
                    #   va derecho al puerto del lobby. ⇒ no cerrábamos nunca más, la bandera quedaba en 1
                    #   y **todos los clics siguientes se descartaban en silencio**.
                    #   Síntoma exacto: el 1er cambio anda, del 2º en adelante suena el chime (el FF49
                    #   llega) pero no pasa nada.
                    #   ★ El mismo bug y el mismo arreglo que en el proyecto CBT (flag `RELOGIN_CLOSE`,
                    #     2026-08-02); allá la bandera vive en `[[0x769C28]+0x17780]`.
                    #   FIX: si a los `RELOGIN_ESPERA` segundos no pidió el FF02, es un re-login ⇒ cerrar
                    #   igual. ⚠ `shutdown`, no `close`: `close` deja el `recv` sobre un descriptor muerto
                    #   (OSError 10038, parece un bug y no lo es).
                    if CERRAR_LOGIN_EN_RELOGIN:
                        # ★ Queda anotado por `usn` para poder cerrarlo en cuanto el cliente
                        #   aparezca en su canal (ver el FF02 de la lobby). El temporizador de
                        #   abajo pasa a ser la RED, no el mecanismo.
                        with _LOGINS_LOCK:
                            LOGINS_ABIERTOS[int(usn or 0)] = conn

                        def _cerrar_si_es_relogin(_c=conn, _u=usn):
                            # ⚠ `pidio_ff02` se lee del ámbito de `handle_login`, o sea de ESTA
                            #   conexión y de ninguna otra. Antes era un diccionario global por
                            #   `id(socket)` y las direcciones se reciclaban — ver la nota de arriba.
                            if pidio_ff02:
                                return
                            # ★ LA RED, NO EL MECANISMO. Lo normal es que este socket ya lo haya
                            #   cerrado el FF02 de la lobby, en cuanto el cliente aparece en su
                            #   canal (+0 s). Esto sólo actúa si eso NO pasó — un cliente que se
                            #   cayó entre el login y el canal—, y ahí evita dejar el socket colgado.
                            #   ⚠ Va por `cerrar_login_pendiente` y no por `shutdown` directo para
                            #     que el registro por `usn` quede consistente: si ya se cerró, no
                            #     hace nada y no se queja.
                            if cerrar_login_pendiente(
                                    _u, f" (RE-LOGIN: no pidió el FF02 en {RELOGIN_ESPERA}s "
                                        f"— la red de seguridad)"):
                                pass
                        threading.Timer(RELOGIN_ESPERA, _cerrar_si_es_relogin).start()
                elif magic == 0xFF and cmd == 0x02:
                    # El cliente pide la lista de lobbies (FF 02 00 00).
                    # ★★ 2026-08-05 — LA IP QUE ANUNCIAMOS ES **LA QUE EL CLIENTE USÓ PARA LLEGAR**.
                    #   Antes iba la constante LOBBY_IP (la del adaptador Ethernet del host). Con un
                    #   solo jugador daba igual, pero con la VM NO: la VM vive en la red VMnet8 y para
                    #   ella el host es 192.168.182.1, no 192.168.1.50. `launcher.py` sincroniza la
                    #   IP en el host (exe + server + scripts) y a la VM no la toca — así que anunciar
                    #   una constante mandaba a la VM por el camino equivocado.
                    #   `getsockname()` se corrige solo: cada cliente recibe la punta del host que le
                    #   corresponde, y encima deja de importar el DHCP. El bind ya es 0.0.0.0.
                    pidio_ff02 = True                  # ★ login normal: el cierre lo hace el handoff
                    ip_anunciada = PUBLIC_IP or conn.getsockname()[0]
                    r = resp2_lobby_list(ip=ip_anunciada, usn=usn)
                    if puerta_paso(f"RESP-2 LobbyList -> {ip_anunciada}:{LOBBY_PORT}  {len(r)} B", hx(r[:32]), handshake=True):
                        conn.sendall(r)
                        log("LOGIN", f"TX RESP-2 LobbyList -> {ip_anunciada}:{LOBBY_PORT} : {hx(r)}")
                    # ★★★ 2026-07-31 — CERRAR EL LOGIN ES LO QUE HABILITA EL CAMBIO DE CANAL.
                    #   MEDIDO con `re/trace_clic_canal2.py`: el clic en un canal SÍ llega a
                    #   `0x4A7020(idx)`, pero muere en su PRIMERA instrucción:
                    #       0x4A7028  cmp byte [[0x9D43D8]+0x20420], 0
                    #       0x4A7032  jne salir          <- si != 0, se va sin hacer NADA
                    #   Ese byte es "sigo conectado al LoginServer": lo pone en 0 la rutina que
                    #   loguea `"LoginServer : <OnClose>"` (`0x5C4F70`, y su gemela `0x5C4F90`).
                    #   Como nosotros manteníamos el socket de login abierto toda la sesión, el flag
                    #   nunca bajaba y TODOS los clics se descartaban. Mismo diseño que el CBT, donde
                    #   el reconnect de switch también exige que el socket viejo esté CERRADO.
                    #   ⇒ el handoff al lobby TERMINA acá: se cierra y el cliente queda habilitado.
                    #   Al elegir canal el cliente vuelve a conectar al LoginServer solo (el listener
                    #   sigue arriba) y pide FF01+FF02 de nuevo; cada canal tiene su propio puerto.
                    #   ⚠ Si esto rompiera el arranque, poner el flag en False: el síntoma sería
                    #     quedarse en el loading justo después de la lista de servidores.
                    if CERRAR_LOGIN_TRAS_HANDOFF:
                        log("LOGIN", "  ★ handoff completo -> CIERRO el socket de login "
                                     "(baja [.. +0x20420] en el cliente = habilita cambiar de canal)")
                        return
                else:
                    log("LOGIN", f"!! cmd no manejado en Login: 0x{cmd:02x}")
    except socket.timeout:
        log("LOGIN", "timeout (120s sin trafico)")
    except ConnectionResetError:
        log("LOGIN", "reset por el cliente")
    except Exception as e:
        log("LOGIN", f"EXC: {e!r}")
    finally:
        conn.close()
def handle_inner(st, cmd, data):
    """Despacha un comando INTERNO (ya descifrado del FF55). Responde lo que el loading espera."""
    # ★★★★ 2026-08-05 — EL SEGUNDO FF4B QUE ACOMODA LOS SLOTS DE EQUIPO.
    #   Síntoma: al CREAR una sala en equipo el título salía bien pero los asientos quedaban
    #   dibujados como SOLO; cambiando a solo y volviendo a equipo se acomodaban.
    #   ⛔ Dos hipótesis DESCARTADAS en el disasm: el `FFBD` no habilita nada (su applier `0x5904D0`
    #      no toca ni el modo ni el layout — y mandarlo sin pedido **abre el diálogo de config**,
    #      probado en pantalla), y el `FF13` **no tiene campo de modo** (`0x5CDA80` no llama a
    #      ninguno de los appliers; lo único de slots que trae es la máscara de bloqueados).
    #   ✅ La vía compatible: **re-mandar el MISMO FF4B**. El bloque que redibuja, dentro del applier
    #      `0x5971F0`, es INCONDICIONAL y no detecta cambios ⇒ redibuja igual. Y el cartel de chat
    #      "se ha cambiado el modo" tiene guarda (`0x597366`: sólo si GameMode/CoopMode cambiaron)
    #      ⇒ mandando el MISMO modo **no sale ningún cartel**.
    #   ⚠ El timing importa: hay que esperar a estar YA DENTRO de la sala (el `Update` de cRoom pisa
    #     el layout con su estado local). Por eso se dispara con el primer paquete que manda el
    #     cliente que NO sea el `FF13` de armado. Si resultara ser todavía muy temprano, sumar el
    #     `0x0C` a la excepción de abajo.
    # ⛔ ACÁ ESTABA EL DISPARO, Y ESTABA MAL UBICADO: al ejecutarse ANTES de despachar, en el FF0C
    #   salía **antes** de mandar la lista de ocupantes — o sea con la sala todavía vacía, que es
    #   justo la condición en la que el applier no reparte equipos. Se movió al final del handler
    #   del FF0C. Red de seguridad: si por lo que sea el cliente nunca pide el FF0C, se manda igual
    #   con el primer paquete que no sea el FF13 ni el FF0C.
    # ⛔ BUG PROPIO (2026-08-05, cazado en el log): la red de seguridad disparaba con CUALQUIER
    #   paquete que no fuera FF13/FF0C — y entre medio llega el **FF3D**, que es el latido de la UI.
    #   Resultado: el FF4B pendiente se consumía ANTES del FF0C, o sea con la sala todavía vacía,
    #   que es exactamente la condición que veníamos a evitar. Se excluyen los de alta frecuencia.
    # ★★★★ SONDA: TODO LO QUE MANDA UN ESPECTADOR QUEDA MARCADO (2026-09-08).
    #   Por qué existe: el botón de **"pasar de mirar a jugar"** no funciona, y no sabemos qué
    #   paquete manda. El log normal lo mezcla con los cientos de latidos y movimientos de la sala,
    #   así que la última vez costó encontrarlo. Con esto, el usuario hace spam del botón y la
    #   línea sale sola, con el hex al lado.
    #   ⚠ Se saltean los de alta frecuencia (`FF3D` latido/canal y `FF23` movimiento): son los que
    #     tapan todo lo demás. Misma lección que `FF4E_SUBS_SIEMPRE`.
    #   ⏳ Se puede sacar cuando el camino de vuelta esté medido; mientras tanto vale su ruido.
    if getattr(st, "slot_espectador", None) is not None and cmd not in (0x3D, 0x23, 0x00):
        log("LOBBY", f"  ★★★ SONDA ESPECTADOR (casillero {st.slot_espectador}): "
                     f"FF{cmd:02X} len={len(data)} : {hx(data) if data else '(vacío)'}")
    _rep4b = getattr(st, "ff4b_repetir", None)
    if _rep4b is not None and cmd not in (0x13, 0x0C, 0x3D, 0x00):
        st.ff4b_repetir = None
        log("LOBBY", f"  ★★ FF4B repetido (red de seguridad, tras un FF{cmd:02X}: no hubo FF0C)")
        enviar_ff4b(st, *_rep4b)
    # ★★★ 2026-07-31 — `FF3D` = PEDIDO DE CAMBIO DE CANAL (no era un latido).
    #   Medido: en una sesión entera llegaron **5**, y el primero justo al clickear el canal. La nota
    #   vieja ("FF3D a 60/s = tick de UI") era de otro estado y acá NO aplica.
    #   El cliente queda en "Nos estamos conectando al servidor" y **no manda nada más ni cierra**:
    #   espera que el SERVER le cierre el socket. Es el mismo diseño que el CBT, donde el reconnect de
    #   switch está gateado por que el socket viejo esté CERRADO (si sigue abierto, se saltea el
    #   connect). Al caerse la conexión, el cliente vuelve al LoginServer y, como `[roommgr+0x1328]`
    #   (elegido) difiere de `+0x132A` (actual), conecta al puerto del canal nuevo.
    #   Payload de 1 byte: llega `00` y después `01`. Se cierra en el **`01`** siguiendo el idioma de
    #   este cliente (mismo patrón que `FF111`/`FF63`/`FF3A`: el 0 avisa, el 1 confirma).
    #   ⏳ SIN CONFIRMAR que `01` sea "confirmar": si el síntoma fuera que te desconecta solo al entrar
    #     al lobby, entonces `01` es otra cosa y hay que mirar el `00` o el contexto.
    if cmd == 0x3D and CERRAR_LOBBY_EN_SWITCH and data and data[0] == 0x01:
        log("LOBBY", f"  ★★★ FF3D switch de canal (payload={hx(data)}) -> CIERRO el socket del lobby "
                     f"para que el cliente re-loguee y aterrice en el canal elegido")
        # `shutdown` y NO `close`: cerrar de una deja al `recv` de este mismo hilo operando sobre un
        # descriptor muerto -> OSError 10038 ("no es un socket"), que ensucia el log con una traza que
        # parece un bug y no lo es. Con `shutdown` el `recv` devuelve b"" y sale por el camino normal.
        st.cerrado = True          # ★ corta los envíos que todavía queden en vuelo (ver send_ff55)
        try:
            st.conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            try:
                st.conn.close()
            except Exception as e:
                log("LOBBY", f"  ⚠ no pude cerrar el socket: {e!r}")
        return
    if cmd in _HIFREQ:
        st.hifreq[cmd] = st.hifreq.get(cmd, 0) + 1
        # ★★ 2026-07-31: NO tragarse el payload. En el CBT el `FF3D` es el PEDIDO DE CAMBIO DE CANAL,
        #   y acá lo estábamos contando como latido sin mirar qué trae. Si alguna vez llega con datos
        #   —o con datos DISTINTOS a los habituales— eso es una señal, no ruido. Se loguea cada payload
        #   nuevo una sola vez, así no ahoga el log pero tampoco esconde el cambio.
        if data:
            vistos = st.hifreq_payloads.setdefault(cmd, set())
            if bytes(data) not in vistos:
                vistos.add(bytes(data))
                log("LOBBY", f"  ★★ inner FF{cmd:02X} con PAYLOAD NUEVO ({len(data)}B): {hx(data)}")
        # ★ UNA LÍNEA POR MINUTO, con el RITMO. Antes era "cada 500", que a 60/s son siete líneas
        #   por minuto por jugador. Con el ritmo a la vista se distingue de un vistazo el goteo
        #   normal (0-20/min, que también tiene el servidor de referencia) del diluvio de verdad
        #   (~3.600/min = uno por cuadro), sin tener que contar líneas a mano.
        # ⚠ UNA SOLA marca de tiempo, que hace de "última vez que loguée" Y de "inicio de la
        #   ventana". Con dos —una para cada cosa— hay que acordarse de moverlas juntas, y al
        #   probarlo se desfasaron: el ritmo salió 159.867.596/min. Un solo dato no puede
        #   desincronizarse consigo mismo.
        # ★★ 2026-09-08 — REPUESTO. Esto se había sacado el 07-sep con el revert del panel
        #   (`1c322bf`), donde viajaba junto a los archivos sospechosos del crash de la meta. Se
        #   vuelve a poner **solo**: es el único de aquel lote que **nada más escribe en el log**,
        #   así que no puede ser el que tiraba a la gente en la meta. El registro de IP, que iba en
        #   el mismo revert, **NO** vuelve — ése sí toca el camino de la conexión.
        _ahora = time.time()
        _ult = st.hifreq_ultimo.get(cmd)
        if _ult is None:
            log("LOBBY", f"  inner FF{cmd:02X} x1 (primero) — alta frecuencia; el servidor de "
                         f"referencia también la tiene, ver el bloque del FF55 en lobby.py")
        elif _ahora - _ult >= 60.0:
            _mins = (_ahora - _ult) / 60.0
            _ritmo = (st.hifreq[cmd] - st.hifreq_marca_n.get(cmd, 0)) / _mins
            log("LOBBY", f"  inner FF{cmd:02X} x{st.hifreq[cmd]} (~{_ritmo:.0f}/min) — alta "
                         f"frecuencia; ~3.600/min es el diluvio conocido, 0-20 es el goteo normal")
        else:
            return
        st.hifreq_ultimo[cmd] = _ahora
        st.hifreq_marca_n[cmd] = st.hifreq[cmd]
        return
    if cmd in _RESUMIR_RX:
        resumir(f"RX FF{cmd:02X}")           # ★ alta frecuencia que SÍ se procesa: se cuenta, no se loguea
    else:
        log("LOBBY", f"  inner FF{cmd:02X} len={len(data)}" + (f" : {hx(data)}" if data else ""))
    # ★ FASE 2: las 46 ramas viven en lobby_salas / lobby_carrera / lobby_tienda /
    #   lobby_menu. Acá queda el ruteo, con las MISMAS condiciones en el MISMO orden.
    #   El import va adentro a propósito: los módulos por tema necesitan todo lo que
    #   define este archivo, así que se resuelve al primer paquete y no al importar.
    from .despacho import RUTAS, SIN_HANDLER
    # ★ El PANEL WEB del VPS lee un `status.json`; acá es donde se entera de en qué pantalla está
    #   cada jugador. Va ANTES del ruteo y no puede lanzar: la telemetría no voltea el server.
    from . import telemetria
    telemetria.observar(st, cmd, data)
    # (La versión abierta no trae el panel de administración web: acá no se escucha el chat.)
    for _prueba, _fn in RUTAS:
        if _prueba(st, cmd, data):
            return _fn(st, cmd, data)
    return SIN_HANDLER(st, cmd, data)

def handle_lobby(conn, addr):
    st = LobbyConn(conn, addr)
    try:                                   # ★ a QUÉ CANAL entró = el puerto por el que vino
        st.puerto = conn.getsockname()[1]
    except Exception:
        st.puerto = LOBBY_PORT
    _c = CANAL_POR_PUERTO.get(st.puerto)
    st.canal = _c[4] if _c else None
    st.libre = (st.canal == "all")         # ★ el canal LIBRE se resuelve por PUERTO, no por el cat
    log("LOBBY", f"conexion desde {addr[0]}:{addr[1]} -> canal :{st.puerto}"
                 + (f" = {_c[5]!r}" if _c else "") + (" ★ LIBRE" if st.libre else ""))
    try:
        while True:
            try:
                data = conn.recv(4096)
            except OSError as e:
                # ★ RUIDO CONOCIDO, NO ES UN BUG: cuando llega un `FF3D` de CAMBIO DE CANAL nosotros
                #   CERRAMOS el socket a propósito (es lo que hace que el cliente re-loguee y aterrice
                #   en el canal elegido). Este `recv` ya estaba esperando sobre ese socket, así que
                #   revienta con 10058/10053. Antes escupía un traceback entero y parecía una falla.
                if getattr(st, "cerrado", False) or getattr(e, "winerror", None) in (10053, 10058):
                    log("LOBBY", "  socket cerrado por nosotros (cambio de canal) — salida limpia")
                    return
                raise
            if not data:
                log("LOBBY", "cliente cerro"); return
            st.buf += data
            frames, st.buf = parse_frames(st.buf)
            for magic, cmd, payload in frames:
                # ★ Si ya cerramos por CAMBIO DE CANAL, no seguir despachando lo que quedó en el
                #   buffer: cualquier respuesta cae en un socket muerto (`BrokenPipeError 10058`).
                if getattr(st, "cerrado", False):
                    return
                if magic == 0xFF and cmd == 0x01:
                    # CmdCheckVer ver=4 -> ACK status=0.
                    _r3 = resp3_checkver_ack()
                    if puerta_paso(f"RESP-3 CheckVer ACK  {len(_r3)} B", hx(_r3[:32]), handshake=True):
                        conn.sendall(_r3)
                        log("LOBBY", "RX CheckVer -> TX RESP-3 ACK")
                elif magic == 0xFF and cmd == 0x02:
                    # Lobby-login del cliente -> RESP-4 (challenge + pwd). Arma el crypto FF55.
                    # ★★★ MEDICIÓN 2026-08-04 — EL PAYLOAD DE ESTE FF02 NO ESTÁ VACÍO Y LO TIRÁBAMOS.
                    #   ⚠ OJO con la confusión que arrastraba el proyecto: hay DOS `FF02` distintos.
                    #     · el del LOGIN  (`0x5C48A0`) = "dame la lista de lobbies" -> ese SÍ va vacío.
                    #     · el de la LOBBY (`0x5C68B0`) = el lobby-login -> **lleva payload**.
                    #   Layout esperado (del orden de escritura de `0x5C68B0`, a CONFIRMAR acá):
                    #       [usn:u32][Location:u8][Age:u16][Gender:u8][u8][lenIP][IP LOCAL del cliente]
                    #       [len][blob][len][blob][len][nombre]  [u32 anti-tamper]  [len][string ofuscado]
                    #   ★ El `usn` sale de `cfg+0x7C`, que el cliente siembra con **`atoi(argv[1])`**.
                    #     Como le pasamos `"SN"`, `atoi` da 0 — de ahí el "el cliente no manda identidad".
                    #   ★ La **IP LOCAL** que viaja acá es la que el cliente ve de sí mismo
                    #     (`gethostname`+`gethostbyname`), así que sobrevive al NAT: sirve de desempate
                    #     si dos clientes llegaran con el mismo usn.
                    #   ✅ MEDIDO EN VIVO — el layout se confirmó BYTE A BYTE (57 B):
                    #       [usn:u32][Location:u8][Age:u16][Gender:u8][u8]
                    #       [lenIP:u8]["192.168.182.1"]  [len=0][len=0]  [len:u8]["asdasdasd"]
                    #       [u32 anti-tamper]  [len=17]["00-50-56-…"]
                    #   ★★ Ese último string, que estaba sin identificar, es **la MAC de la placa de
                    #      red** (`00-50-56` = el OUI de VMware). ⇒ el cliente manda solo un
                    #      identificador ÚNICO POR MÁQUINA, que sobrevive al NAT. Sirve de desempate
                    #      si dos clientes llegaran con el mismo usn, sin tocar nada.
                    _u = struct.unpack("<I", payload[:4])[0] if len(payload) >= 4 else None
                    if _u is not None:
                        st.usn = _u                      # ★ identidad de ESTA conexión
                        # ★★ Y LA CLAVE DEL CIFRADO, que es POR CUENTA (`key_base = B + USN`).
                        #    Con varios jugadores cada conexión tiene la suya: una clave global haría
                        #    que el segundo cliente no descifre nada.
                        st.key_base = (LOBBY_B + _u) & 0xFFFFFFFF
                        # ★★ Alta en el registro GLOBAL de conexiones: es lo que le permite al server
                        #    empujarle un paquete a OTRO jugador (sin esto no hay sala compartida).
                        # ★★★ DOBLE LOGIN: la sesión anterior de esta cuenta se muere acá.
                        #   Va ANTES de `registrar_conexion` a propósito: así `CONEXIONES[usn]`
                        #   todavía apunta a la VIEJA y se la puede limpiar con sus propios datos.
                        #   Si se llamara después, el registro ya estaría pisado y estaríamos
                        #   limpiando la sala de la nueva. Ver `echar_sesion_anterior`.
                        echar_sesion_anterior(_u, st)
                        registrar_conexion(st)
                        # ★★★★★ Y ACÁ SE CIERRA EL LOGIN DE ESTE JUGADOR — LA SEÑAL, NO EL RELOJ.
                        #   El cliente descarta EN SILENCIO todos los clics del selector de canales
                        #   mientras su conexión al LoginServer siga abierta (su bandera
                        #   `[[0x9D43D8]+0x20420]`, que apagan `LoginServer : <OnClose>` y
                        #   `<OnConnectionDestroyed>`). Cerrarla es lo que lo destraba.
                        #   ⛔ Antes eso lo hacía SOLO un temporizador de `RELOGIN_ESPERA` = 2 s, y
                        #     esos 2 s eran una **ventana muerta en cada cambio de canal**: si
                        #     apretabas adentro, no pasaba nada. Reportado por anonimo03: *"algunas
                        #     veces al primer intento falla pero el segundo funciona"*. No era el
                        #     juego: era mi espera.
                        #   ★ MEDIDO en el log, 13 cambios seguidos: el cliente conecta a su canal
                        #     **en el mismo segundo** que el LOGIN OK (+0 s) y recién 2 s después
                        #     cerrábamos. O sea que el aviso bueno ya lo teníamos y no lo usábamos:
                        #     **si está acá, en el canal, el socket de login ya no le sirve para
                        #     nada.** Se cierra ahora y la ventana muerta pasa de 2 s a ~0.
                        #   ⚠ El temporizador SE QUEDA como red: si un cliente se cayera entre el
                        #     login y el canal, nadie llegaría a este punto y el socket quedaría
                        #     colgado. Ahora es el respaldo, no el mecanismo.
                        cerrar_login_pendiente(_u, " (ya conectó a su canal)")
                    log("LOBBY", f"  ★★ FF02 LOBBY-LOGIN payload len={len(payload)} : {hx(payload[:48])}"
                                 + (f"  -> usn={_u} key_base=0x{st.key_base:08X}" if _u is not None
                                    else "  (VACÍO: no es el de la lobby)"))
                    # ★★★★★ EL CHALLENGE SALE DE ESTE MISMO PAQUETE, no de una constante (ver
                    #   `leer_challenge_ff02`). Es POR MAQUINA: con el valor del host, otra PC
                    #   arma el cifrado pero RECHAZA la sesion y se va a "redireccionando".
                    _nic = leer_challenge_ff02(payload)
                    if _nic is None:
                        _nic = TOKEN_CFG90
                        log("LOBBY", "  ⚠⚠ no pude leer el challenge del FF02: uso el capturado en el "
                                     "HOST. En otra maquina esto NO va a funcionar.")
                    st.nic = _nic
                    _r4 = resp4_lobby_login_ok(token_cfg90=_nic, usn=getattr(st, "usn", 0))
                    # ⚠ Este NO se puede saltear: si no va, el cliente nunca arma el cifrado y todo lo
                    #   que siga queda ilegible. Se frena para verlo, pero se manda igual.
                    puerta_paso(f"RESP-4 lobby-login (challenge nic=0x{_nic:08x})  {len(_r4)} B  "
                                f"[no salteable]", hx(_r4[:32]), handshake=True)
                    conn.sendall(_r4)
                    st.crypto_ready = True; st.recv_counter = 0; st.send_counter = 0
                    A = (_nic ^ CHALLENGE_XOR) & 0xFFFFFFFF
                    log("LOBBY", f"RX Lobby-login -> TX RESP-4 (challenge del cliente: nic=0x{_nic:08x} "
                                 f"-> A=0x{A:08x}, pwd 256B). Crypto FF55 ARMADO.")
                elif magic == 0xFF and cmd == 0x55:
                    # Contenedor cifrado -> descifrar y despachar comandos internos.
                    dec = st.decrypt_container(payload)
                    if dec is None:
                        log("LOBBY", f"FF55 NO descifro (recv_ctr={st.recv_counter}) len={len(payload)} : {hx(payload)}")
                        continue
                    inner = parse_ff55_inner(dec)
                    # ⛔ Acá decía **"NO SILENCIAR ESTA LÍNEA"** (03-sep), y el motivo era: *"el log
                    #   no es el problema; el cliente manda 59 paquetes por segundo y callar el
                    #   síntoma sólo hace que nadie lo note"*. Era correcto **con lo que se sabía
                    #   entonces**: se creía que el diluvio de `FF3D` era una desviación NUESTRA.
                    #
                    # ★★ 2026-09-07 — LA PREMISA ERA FALSA, Y ESTÁ MEDIDA. La documentación decía
                    #   que el cliente del servidor de referencia manda *"54 `FF3D` en toda una
                    #   sesión"* contra nuestros 47.000. Contando sobre sus propias capturas:
                    #       referente: 119.256 `FF3D` en 214 min · su peor sesión **3.564/min**
                    #       nosotros:  pico medido ese día **3.624/min**
                    #   Los dos son 60/s = **uno por cuadro**, y en las dos partes es INTERMITENTE
                    #   (un jugador puntual, no todos). ⇒ No es algo que hagamos distinto: es cómo
                    #   se comporta este cliente. Perseguir esa diferencia nos costó el `FF1C` del
                    #   lobby, que resultó ser **el crash de las PC modestas** (ver `ajustes.py`).
                    #
                    # ⇒ Y lo que sí cuesta está medido: **CPU 1,3 % de promedio y 0,0 % en reposo**,
                    #   carga 0,04 — o sea nada. Lo que cuesta es el LOG: **el 88 % de las líneas**
                    #   (339.116 de 383.174) y ~1 millón de líneas por día. Ese log es donde
                    #   miramos cuando algo falla, y ya nos costó dos diagnósticos no poder leerlo.
                    #
                    # ★ Por eso NO se silencia: se RESUME. El sobre que trae sólo comandos de alta
                    #   frecuencia no imprime su línea —son todas idénticas—, pero el conteo sigue
                    #   saliendo abajo, con su ritmo, una vez por minuto. Se ve igual que antes que
                    #   está pasando; deja de verse 3.600 veces.
                    _solo_hifreq = bool(inner) and all(c in _HIFREQ or c in _RESUMIR_RX for c, _ in inner)
                    if not _solo_hifreq:
                        log("LOBBY", f"RX FF55 descifrado (recv_ctr={st.recv_counter}) -> "
                                     f"{len(inner)} cmd(s): "
                                     + ", ".join(f"FF{c:02X}" for c, _ in inner))
                    for icmd, idata in inner:
                        handle_inner(st, icmd, idata)
                elif magic == 0xFF and cmd == 0x4E:
                    # ★★★★★ SINCRONISMO DE CARRERA. Ver el bloque de xor14() para el formato.
                    #   NO se puede relevar el paquete tal cual: cada conexión tiene su propio
                    #   contador, así que hay que DESCIFRAR con el del emisor y RE-CIFRAR con el de
                    #   cada destinatario. Y la ofuscación con el `magic` es asimétrica: entra
                    #   ofuscada y sale EN CLARO.
                    _dec = st.descifrar_ff4e(payload)
                    if _dec is None:
                        log("LOBBY", f"  ⚠ FF4E NO descifró (ctr={st.recv_counter}) : {hx(payload)}")
                        continue
                    _sub, _A, _B = _dec
                    # ★ 14-oct · LOS COSMÉTICOS (globo 0x70, calculadora 0x71/0x72 — PAQUETES_ESPECTADOR.md): por acá y
                    #   nada más. Sin log, sin muestreo, sin NPC: tope por conexión y reenvío «si se puede YA».
                    #   El 0x70 también a la MESA en una sala de relevo (el que espera su tramo); lo demás sólo a los
                    #   ESPECTADORES, aun diferidos (el que salta de asiento lo siembra).
                    if _sub in FF4E_COSMETICOS:
                        if getattr(st, "slot_espectador", None) is not None or not st.tope_cosmetico():
                            continue
                        _ridc = getattr(st, "room_id", None)
                        if _ridc is None:
                            continue
                        if _sub == FF4E_SUB_GLOBO and (getattr(st, "room_mode", 0) & MODE_RELEVO):
                            for _u in mesa_de(_ridc).values():
                                _c = CONEXIONES.get(_u) if _u != getattr(st, "usn", None) else None
                                if _c is not None:
                                    _c.send_ff4e_si_puede(_sub, _A, _B)
                        for _cc in espectadores_de(_ridc):
                            _cc.send_ff4e_si_puede(_sub, _A, _B)
                        continue
                    # ★ MEDIR (11-oct, ⛔ sólo LOCAL): cada FF4E de cada jugador a `_trabajo/logs/ff4e_carrera.jsonl`, para
                    #   ver qué manda un cliente CONGELADO por un hielo (dos instancias: una tira, la otra recibe) y
                    #   copiárselo a los NPC. Ver npc_carrera.py. Prod no tiene la consola de GM: no corre.
                    try:
                        from . import npc_carrera as _npc4e
                        _npc4e.anotar_ff4e(st, _sub, _A, _B)
                    except Exception:                      # noqa: BLE001
                        pass
                    # ★ `.autoplay` (2026-09-24): el primer FF4E del jugador dice que ya terminó de
                    #   cargar la pista — recién ahí se le puede mandar el autoplay.
                    if getattr(st, "autoplay_gm", False):
                        autoplay_gm.vio_ff4e(st)
                    _rid4e = getattr(st, "room_id", None)
                    _n4e = 0
                    # ★★★★★ EL QUE MIRA NO JUEGA — 2026-09-08.
                    #   El `0x4E` es la capa de JUEGO: movimiento del corredor, efectos, combo. Si un
                    #   espectador manda uno, no puede entrar a la carrera de los demás (le movería el
                    #   corredor a alguien, o le cargaría el impulsor al jefe). Se descarta entero:
                    #   ni relevo, ni contabilidad del jefe, ni conteo del cooperativo.
                    if getattr(st, "slot_espectador", None) is not None:
                        continue
                    # ★ 14-oct · EL GLOBO DEL COMBO (sub 0x70, ver ajustes.FF4E_SUB_GLOBO): el combo del que corre.
                    #   A los SENTADOS sólo en una sala de RELEVO (al que espera su tramo o ya corrió). ★ QA 14-oct: y a
                    #   los ESPECTADORES siempre, en todos los modos: el que salta de asiento ve el combo «desde que lo
                    #   empezó a mirar» (re-juzga sólo al que sigue) y la dll le siembra el real (globo_combo.c).
                    _globo4e = False                    # ★ los cosméticos ya salieron arriba (FF4E_COSMETICOS)
                    _a_la_mesa = True
                    for _u in (mesa_de(_rid4e).values() if (_rid4e is not None and _a_la_mesa) else ()):
                        # ★ SIN eco al emisor: el handler NO tiene guard de "soy yo", así que su
                        #   propia acción se le aplicaría DOS veces (medido en el sub 0xB4).
                        if _u == getattr(st, "usn", None):
                            continue
                        _c = CONEXIONES.get(_u)
                        if _c is None or getattr(_c, "cerrado", False):
                            continue
                        try:
                            _c.send_ff4e(_sub, _A, _B, name=f"relevo de usn={st.usn}")
                            _n4e += 1
                        except Exception as e:
                            log("LOBBY", f"  ⚠ no pude relevar el FF4E a usn={_u}: {e!r}")
                    # ★★★★★ Y A LOS ESPECTADORES — 2026-09-08. ESTE ERA EL BUG DEL SYNC.
                    #   ⛔ Reportado: *"la partida empezó para todos, pero los espectadores no
                    #     recibieron el sync de los que están corriendo"*.
                    #   El `0x4E` **es** el sincronismo de la carrera: los cientos de paquetes por
                    #   corrida que mueven a cada corredor en la pista. Se relevaba sólo a
                    #   `mesa_de(rid)` = LOS SENTADOS ⇒ el espectador cargaba la pista, arrancaba, y
                    #   veía a todo el mundo congelado en la línea de largada. Miraba una carrera
                    #   MUDA, igual que antes miraba una sala muda: **es el mismo molde por sexta
                    #   vez** (ver `conexiones_en_sala`), sólo que este relevo no vive en
                    #   `lobby_carrera` sino acá, en el lazo de frames crudos, y por eso se salvó de
                    #   las cinco pasadas anteriores.
                    #   ★ Va EN CLARO como el de los jugadores: `send_ff4e` no ofusca con el `magic`
                    #     (la ofuscación es asimétrica, sólo de entrada), así que el espectador lo
                    #     lee aunque nunca le hayamos tocado su `game_magic`. Ése era el sospechoso
                    #     nº1 anotado para hoy, y queda DESCARTADO: la clave no era el problema.
                    # ★ 12-oct «todo con el mismo retraso»: si este corredor ya le manda su FF98 en ESTA carrera, al que
                    #   mira el FF4E en vivo no va (le llega reproducido, ~0,75 s atrás, y una sola vez). Ver
                    #   `ESPECTADOR_DIFERIDO` en ajustes.py.
                    _diferido4e = (ESPECTADOR_DIFERIDO and getattr(st, "ff98_magic", None) is not None
                                   and getattr(st, "ff98_magic", None) == getattr(st, "game_magic", None))
                    for _ce4e in ([] if (_diferido4e and not _globo4e) else espectadores_de(_rid4e)):
                        try:
                            _ce4e.send_ff4e(_sub, _A, _B, name=f"relevo a ESPECTADOR de usn={st.usn}")
                            _n4e += 1
                        except Exception as e:
                            log("LOBBY", f"  ⚠ no pude relevar el FF4E a un espectador: {e!r}")
                    # ★★ LOS NPC QUE JUEGAN (10-oct, SÓLO LOCAL): con el avance (`sub=0x05`) de un humano, el server
                    #   le inventa el suyo a cada NPC de la sala y se lo manda a TODOS (al que avisó también: su
                    #   cliente tiene que ver a los NPC). Ver `npc_carrera.py`.
                    if _sub == 0x05 and _rid4e is not None:
                        try:
                            from . import npc_carrera
                            _dnpc = [CONEXIONES.get(_u) for _u in mesa_de(_rid4e).values()]
                            _dnpc = [c for c in _dnpc if c is not None and not getattr(c, "cerrado", False)]
                            npc_carrera.al_avance(st, _A, _B, _dnpc + list(espectadores_de(_rid4e)))
                        except Exception as e:
                            log("LOBBY", f"  ⚠ el avance de los NPC: {e!r}")
                    elif _sub == 0x01 and _rid4e is not None:      # (sus impulsores, y los ítems que les tiran a los NPC)
                        try:
                            from . import npc_carrera
                            npc_carrera.al_efecto(st, _A, _B)
                        except Exception as e:
                            log("LOBBY", f"  ⚠ el efecto para los NPC: {e!r}")
                    elif _sub == 0x64 and _rid4e is not None:      # ★ relevo: pasó la posta (a un NPC, quizá)
                        try:
                            from . import npc_carrera
                            npc_carrera.al_posta(st, _A, _B)
                        except Exception as e:
                            log("LOBBY", f"  ⚠ la posta para los NPC: {e!r}")
                    elif _sub == 0x66 and _rid4e is not None:      # ★ agarró una caja «?»: los NPC agarran la misma (11-oct)
                        try:
                            from . import npc_carrera
                            npc_carrera.al_caja(st, _A, _B)
                        except Exception as e:
                            log("LOBBY", f"  ⚠ la caja para los NPC: {e!r}")
                    # ★★★★★ EL IMPULSOR DEL MODO JEFE (2026-09-07).
                    #   `sub = 0x32` = "mi combo llegó a otro múltiplo de 40" (`0x5050E7`). En
                    #   modo jefe el cliente **no** carga la barra solo (`0x504F85`: si es jefe,
                    #   sale sin tocar nada) ⇒ este aviso es LA señal con la que el server decide
                    #   mandarle el `FF176`. Ver el bloque de `JEFE_IMPULSOR` en `ajustes.py`.
                    #   `sub = 0x01` = "disparé un efecto", y el impulsor del jefe pasa por ahí:
                    #   nos sirve para poner el espejo en cero cuando el jugador lo gasta.
                    #   ⚠ Los dos son ADEMÁS del relevo de arriba, que sigue igual.
                    _rid32 = getattr(st, "room_id", None)
                    # ★★★★★ DÓNDE VA CADA CORREDOR EN LA PISTA — `sub = 0x05` (2026-09-10).
                    #   anonimo03 corrigió la regla del cooperativo: *"el que 'atrapó' es el que llega
                    #   a estar lo más cerca del gorila y activa el minijuego"*. Para poder
                    #   respetarla hay que saber quién iba adelante, y resulta que **el dato ya
                    #   pasaba por acá**: lo relevábamos sin mirarlo.
                    #   ★ MEDIDO en la captura del referente: `A` es un float y crece parejo a lo
                    #     largo de la carrera — 305 · 366 · 431 · 492 · 553 · 614 · 675 · 740 …
                    #     (+61 por tic). Es el AVANCE en la pista, y es el `sub` más frecuente de
                    #     todos (3.913 de ~7.400 en esa captura).
                    #   ⚠ Sólo se anota en cooperativo: en los demás modos no lo usa nadie y sería
                    #     un diccionario creciendo por gusto en el camino más caliente del server.
                    if _sub == 0x05 and _rid32 is not None and getattr(st, "room_colab", False):
                        try:
                            anotar_avance(_rid32, getattr(st, "room_slot", None),
                                          struct.unpack("<f", struct.pack("<I", _A & 0xFFFFFFFF))[0])
                        except Exception as e:
                            log("LOBBY", f"  ⚠ no pude anotar el avance: {e!r}")
                    if _sub == 0x32:
                        try:
                            cargar_impulsor_jefe(st, _rid32)
                        except Exception as e:
                            log("LOBBY", f"  ⚠ impulsor del jefe: {e!r}")
                    elif _sub == 0x01:
                        # ★ Un efecto. El `0xF3` es el impulsor del jefe disparándose (no carga,
                        #   vacía); cualquier otro es un ÍTEM usado (carga). Ver `efecto_del_jefe`.
                        # ★★ EL ID VIENE EMPAQUETADO, no es el `A` entero:
                        #    `A = (destino << 24) | (emisor << 16) | (ID << 8) | 0`  (`0x503A32`).
                        #    Lo supuse mal la primera vez y lo corrigió el log. Ver `ajustes.py`.
                        try:
                            efecto_del_jefe(st, _rid32, (_A >> 8) & 0xFF)
                        except Exception as e:
                            log("LOBBY", f"  ⚠ efecto del jefe: {e!r}")
                        # ★ Y el conteo para las tres columnas del cartel de cooperativo. Va
                        #   aparte del bloque del jefe a propósito: esto cuenta en TODOS los
                        #   modos y no decide nada, sólo anota. Ver `EFECTOS_COOP`.
                        try:
                            anotar_efecto(_rid32, (_A >> 16) & 0xFF, (_A >> 24) & 0xFF,
                                          (_A >> 8) & 0xFF)
                        except Exception as e:
                            log("LOBBY", f"  ⚠ no pude anotar el efecto: {e!r}")
                    _v4e = st.crudos.get(0x4E, 0) + 1
                    st.crudos[0x4E] = _v4e
                    # ★★ LOS SUBS DE `FF4E_SUBS_SIEMPRE` NO SE MUESTREAN. El muestreo (8 + uno cada
                    #   200) sirve para descifrar un layout, pero **esconde los eventos raros**, que
                    #   son los que importan. El `0x32` —"llegué a 40 de combo"— sale un puñado de
                    #   veces por carrera y quedaba tapado: en una carrera de jefe entera había 60
                    #   líneas de FF4E y ninguna era ésa.
                    if _sub in FF4E_SUBS_SIEMPRE:
                        # ★ El `A` de los eventos es `(cl << 24) | (dl << 16) | (al << 8) | 0`
                        #   (`0x5039C0`). Para el `sub=0x01`: al = ID del efecto · dl = quién lo
                        #   usó · cl = a quién le pegó. Se desarma acá para que el log se lea.
                        _qué = {0x32: "  ← ★ COMBO x40 (la señal del impulsor del jefe)",
                                0x01: f"  ← ★ EFECTO id={(_A >> 8) & 0xFF} "
                                      f"(usó el slot {(_A >> 16) & 0xFF}, le pegó al "
                                      f"{(_A >> 24) & 0xFF})"
                                      + ("  = ★ EL IMPULSOR DEL JEFE disparándose"
                                         if ((_A >> 8) & 0xFF) == 0xF3 else "  = un ÍTEM")
                                }.get(_sub, "")
                        log("LOBBY", f"  ★★★ FF4E #{_v4e} sub=0x{_sub:02X} de slot="
                                     f"{getattr(st, 'room_slot', '?')} usn={getattr(st, 'usn', '?')}"
                                     f" A=0x{_A:08X} B=0x{_B:08X} -> relevado a {_n4e}" + _qué)
                    elif _v4e <= CRUDOS_MUESTRA or _v4e % 200 == 0:
                        log("LOBBY", f"  ★ FF4E #{_v4e} sub=0x{_sub:02X} A=0x{_A:08X} B=0x{_B:08X}"
                                     f" -> relevado a {_n4e}")
                elif magic == 0xFF and cmd == 0x4F and REGALO_ACTIVO:
                    # ★ 12-oct: el SOBRE CIFRADO (Blowfish casero del cliente) del regalo de la tienda (FF53).
                    #   Ver `regalo.py`. Llegaba como «?? cmd 0x4f».
                    try:
                        from .regalo import atender_sobre
                        atender_sobre(st, payload)
                    except Exception as e:                                     # noqa: BLE001
                        log("LOBBY", f"  ⚠ FF4F (regalo): {e!r}")
                else:
                    # ★★ CAPTURA DE GAMEPLAY (2026-08-05). Los paquetes de carrera (el `0x4E` y
                    #   compañía) viajan FUERA del sobre cifrado y caen acá. Son CIENTOS por partida:
                    #   loguearlos todos ahoga el archivo y esconde lo demás, y no loguearlos nos deja
                    #   sin material. Se guardan los primeros CRUDOS_MUESTRA de cada comando (que es
                    #   lo que sirve para descifrar el layout) y después sólo el conteo cada 200.
                    _cnt = st.crudos.get(cmd, 0) + 1
                    st.crudos[cmd] = _cnt
                    if _cnt <= CRUDOS_MUESTRA:
                        log("LOBBY", f"?? cmd 0x{cmd:02x} #{_cnt} len={len(payload)} : {hx(payload)}")
                    elif _cnt % 200 == 0:
                        log("LOBBY", f"?? cmd 0x{cmd:02x} van {_cnt} (muestras arriba)")
    except ConnectionResetError:
        log("LOBBY", "reset por el cliente")
    except Exception as e:
        import traceback
        log("LOBBY", f"EXC: {e!r}\n{traceback.format_exc()}")
    finally:
        # ★★ Se fue (cerró, crasheó, o lo mató el keepalive): sacarlo de la mesa y del registro, y
        #    avisarle a los que quedan. Sin esto, un jugador caído ocupa su silla para siempre y la
        #    sala termina "llena" de fantasmas.
        try:
            # ★ ¿Era uno de los que MIRABAN? Se pregunta ANTES de soltarlo, porque después ya no
            #   está en `CONEXIONES` y no hay a quién preguntarle. Reportado: *"el que crasheó no
            #   salió de la lista de espectadores"* — el `FF0E` de abajo lo borra, y el `FFBB`
            #   deja el contador al día.
            # ★★ SI ESTA SESIÓN FUE REEMPLAZADA POR UN DOBLE LOGIN, ACÁ NO SE TOCA NADA.
            #   Su limpieza ya la hizo `echar_sesion_anterior`, en orden y con sus datos. Volver a
            #   hacerla ahora sería **sacarle la silla a la sesión NUEVA**: `levantar_jugador`
            #   busca por `usn` y las dos comparten el mismo. Es el mismo cuidado que el `is st`
            #   de `olvidar_conexion`, y sin él el jugador quedaría invisible en su propia sala.
            if getattr(st, "reemplazada", False):
                log("LOBBY", f"  ★ conexión usn={getattr(st, 'usn', '?')} dada de baja "
                             f"(REEMPLAZADA por un doble login — su limpieza ya se hizo)")
                return
            try:                                 # ★ 15-oct: la misión de hoy guarda el tiempo conectado de esta conexión
                from . import mision_hoy
                mision_hoy.al_salir(st)
            except Exception as _e_mh:           # noqa: BLE001
                log("LOBBY", f"  ⚠ misión de hoy al salir: {_e_mh!r}")
            _era_esp = getattr(st, "slot_espectador", None) is not None
            _rid, _quedaba = levantar_jugador(st)
            olvidar_conexion(st)
            if _rid and _quedaba:
                difundir_salida(_rid, st)        # FF0E: lo saca de la pantalla de los que quedan
                difundir_userlist(_rid, menos=st, por_salida=True)
                actualizar_ocupantes_sala(_rid)
                if _era_esp:
                    from .salas import difundir_espectadores
                    difundir_espectadores(_rid, motivo=" (se cayó uno que miraba)")
                # ★★ ¿LA SALA ESTABA ESPERÁNDOLO PARA ARRANCAR? — 2026-09-08. Si el que se fue era
                #   el único que faltaba por cargar, su `FF25` no va a llegar nunca y los demás se
                #   quedan mirando la pista. El reloj los destrabaría igual, pero tarde. Pasó en
                #   producción: `faltan [10026]` … y dos minutos después su conexión se dio de baja.
                from .lobby_carrera import revisar_arranque
                revisar_arranque(_rid)
                # ★★ Y SI EL QUE SE CAYÓ ERA EL ANFITRIÓN, la sala hereda dueño. Va acá y no sólo
                #   en el `FF12` a propósito: el que crashea o cierra el juego NO manda EXITROOM, y
                #   ése es justo el caso en el que la sala quedaba sin nadie que pudiera arrancar.
                #   Import perezoso, igual que `despacho.RUTAS`: `lobby_salas` se importa cuando ya
                #   está todo cargado, para no armar un ciclo al levantar el módulo.
                from .lobby_salas import traspasar_anfitrion_al_salir
                traspasar_anfitrion_al_salir(_rid, st)
                # ★★ Y a sus amigos del alma que quedan en la sala se les va su joya: se los
                #   manda su FF15 con la lista nueva. Igual que en el `FF12`, porque el que cierra
                #   el juego no manda EXITROOM (ver `salas.actualizar_ocupantes`).
                from .salas import actualizar_ocupantes, almas_presentes
                actualizar_ocupantes(_rid, almas_presentes(getattr(st, "usn", 0), _rid),
                                     motivo=" (se desconectó su amigo del alma)")
            if _rid:
                desregistrar_sala(st)            # solo borra la sala si quedó vacía
            # ★★ AVISARLE A MIS AMIGOS QUE ME FUI (2026-09-10).
            #   anonimo03 lo vio jugando: *"sólo jugador2 se ve verde y el otro con fuente normal"*.
            #   La lista se empujaba UNA vez al entrar y nunca más ⇒ cada uno veía el estado
            #   CONGELADO del momento en que él entró. El que se conectó después no existía.
            #   Import perezoso, igual que los de arriba, para no armar un ciclo al levantar.
            try:
                from .lobby_social import avisar_a_mis_amigos
                avisar_a_mis_amigos(st, "se fue")
                # ★★ Y a la pareja. ⚠ ACÁ, antes de sacarla de CONEXIONES: si se avisara después,
                #   `avisar_a_mi_pareja` no encontraría a nadie y el aviso se perdería en silencio
                #   — que es la misma trampa de orden que nos mordió toda la sesión de pareja.
                from .lobby_pareja import avisar_a_mi_pareja, olvidar_propuestas_de
                avisar_a_mi_pareja(st, "se fue")
                # ★ Y sus propuestas abiertas (las que mandó y la que le mandaron) se cierran: si
                #   no, quedaban colgadas y bloqueaban a la otra punta (jugador35, prod, 21-sep).
                olvidar_propuestas_de(int(getattr(st, "usn", 0) or 0))
                # ★★ Y a los amigos del alma, ACÁ MISMO y por el mismo motivo de orden: si se
                #   avisara después de sacarlo de CONEXIONES, no encontraría a nadie.
                from .lobby_alma import avisar_a_mis_almas
                avisar_a_mis_almas(st, "se fue")
                # ★ Y al CÍRCULO (24-sep): mis compañeros me ven desconectado. Mismo orden.
                from .circulos import presencia
                presencia(int(getattr(st, "usn", 0) or 0), entro=False)
                # ★ Y la SALA DE CONVERSACIÓN (24-sep): el asiento quedaba ocupado para siempre y los
                #   demás lo seguían viendo. `charla.salir` libera y manda el FF0E.
                from .charla import salir as _salir_charla
                _salir_charla(st, "se desconectó")
            except Exception as _e:
                log("LOBBY", f"  ⚠ avisando a los amigos de la baja: {_e!r}")
            log("LOBBY", f"  ★ conexión usn={getattr(st, 'usn', '?')} dada de baja"
                         + (f" (salía de la sala {_rid})" if _rid else ""))
        except Exception as e:
            log("LOBBY", f"  ⚠ limpiando la conexión: {e!r}")
        conn.close()

def activar_keepalive(conn, quien=""):
    """★ SO_KEEPALIVE (portado del CBT, memoria r2beat-fantasmas-keepalive).
    Sin esto, un cliente que desaparece EN SILENCIO (crash, corte de luz, notebook suspendida)
    deja su socket en ESTABLISHED para SIEMPRE: el kernel no tiene ningún temporizador para
    sockets que no pidieron keepalive -> el hilo del handler nunca termina, el char/sala quedan
    de fantasma y el descriptor no se libera. Con esto: ~60s de silencio -> sondeos -> muerto.
    Los sondeos los contesta el KERNEL del jugador, así que un AFK legítimo NO se lo patea.
    En Windows los TCP_KEEP* no existen en el módulo socket: se configuran por ioctl
    SIO_KEEPALIVE_VALS (on, idle_ms, intervalo_ms)."""
    try:
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):                      # Windows
            conn.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 60000, 10000))
        else:                                                          # Linux/BSD
            for opt, val in (("TCP_KEEPIDLE", 60), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 3)):
                if hasattr(socket, opt):
                    conn.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
        # ★★★★★ EL TOPE PARA UN CLIENTE QUE DEJÓ DE LEER — 2026-09-09.
        #
        #   ⛔ EL CUELGUE QUE ARREGLA, medido en prod: *"hay carreras que no están empezando ni
        #     terminando, y son varias salas"*. En el log, **cuatro salas destrabándose EN EL MISMO
        #     SEGUNDO** (20:03:15), y una de ellas era de las 19:56 — **6 minutos tarde** para un
        #     reloj de 30 s. Eso no es un reloj lento: es que estaban BLOQUEADAS y se soltaron todas
        #     juntas.
        #
        #   ★ LA CAUSA: `send_ff55` hace `sendall` **dentro del candado**, y **no había tope de
        #     envío**. Si un cliente deja de leer (colgado, red mala), su buffer se llena y el
        #     `sendall` **bloquea el hilo que lo llama** — que muchas veces es **el de OTRO jugador**
        #     haciendo una difusión (el GO, el cartel, la lista de ocupantes). Una sola PC colgada
        #     congela salas ajenas.
        #   ⚠ Y el KEEPALIVE de arriba **no cubre este caso**: sólo vigila conexiones CALLADAS.
        #     Con datos esperando confirmación manda el temporizador de retransmisión, y
        #     `tcp_retries2 = 15` en este kernel = **~15 minutos**. Los `TimeoutError [Errno 110]`
        #     del log son justamente eso: el kernel rindiéndose, tardísimo.
        #
        #   ⇒ `TCP_USER_TIMEOUT` acota **cuánto pueden quedar datos sin confirmar** antes de matar
        #     la conexión. Es del kernel, así que **no cambia el comportamiento bloqueante de
        #     Python** (a diferencia de `settimeout`, que afectaría también al `recv` — y un
        #     timeout de lectura ya nos rompió el lobby una vez, ver la nota de `handle_login`).
        #   ⚠ EL TRATO, dicho de frente: un jugador con muy mala conexión puede quedar rajado a los
        #     `TOPE_ENVIO_MS/1000` s. Hoy la alternativa es peor: **ese jugador congela salas
        #     enteras durante minutos**. Se prefiere perder uno a colgar seis.
        #   ★ En 0 se apaga y vuelve el comportamiento de antes.
        if TOPE_ENVIO_MS and hasattr(socket, "TCP_USER_TIMEOUT"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT, int(TOPE_ENVIO_MS))
    except Exception as e:
        log("MAIN", f"⚠ keepalive no activado en {quien}: {e!r}")

def listener(port, handler, role):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((BIND_IP, port)); s.listen(5)
    log(role, f"escuchando en {BIND_IP}:{port}")
    while True:
        conn, addr = s.accept()
        activar_keepalive(conn, role)
        _c = CANAL_POR_PUERTO.get(port)
        if _c:      # ★ decir A QUÉ CANAL entró: con 8 listeners iguales, si no, no se sabe cuál eligió
            log(role, f"  ★★ CANAL ELEGIDO POR EL CLIENTE: :{port} = {_c[5]!r} "
                      f"(cat=0x{_c[0]:02X}, código {_c[3]}, {_c[4]})")
        threading.Thread(target=handler, args=(conn, addr), daemon=True).start()

def main():
    """Arranca el server: carga las tablas, crea los lugares y levanta los listeners.

    ⚠⚠ ESTO TIENE QUE CORRER DENTRO DEL MODULO IMPORTADO (`servidor.lobby`), NO como un
      script suelto. `servidor/__init__.py` hace `from .lobby import *`, asi que arrancar
      este archivo con `runpy`/`python lobby.py` deja DOS copias del modulo vivas: la
      importada (de la que salen `build_myrecord`, `build_ff49` y todo lo que arma
      paquetes, porque `lobby_menu` las trae de ahi) y la del `__main__`. Los globals NO
      se comparten entre las dos.
      Asi se rompio el picker el 2026-09-02: el arranque dejaba las 814 canciones en
      `OWNED_SONGS_2013` del `__main__`, el log decia "picker de musica: 814", y el
      `MyRecord` se armaba en la otra copia leyendo la lista todavia vacia -> el cliente
      recibia el picker sin una sola cancion. Sintoma silencioso: ni error ni warning.
      Por eso `startserver.py` importa el paquete y llama a esta funcion.
    """
    _log_viejo = guardar_log_anterior()                   # ⛔ antes lo abría para escribir = lo BORRABA
    if _log_viejo:
        log("MAIN", f"el log de la corrida anterior quedó en {os.path.basename(_log_viejo)}")
    _umbrales = cargar_umbrales_exp()                     # ★ tabla NIVEL↔EXP leída DEL EXE (0x8782A0)
    if _umbrales:
        log("MAIN", f"tabla de niveles: {len(_umbrales)} umbrales del exe "
                    f"(nivel 1 = {_umbrales[0]} exp · nivel 99 = {_umbrales[-1]})")
    shop_catalog.load()                                   # Fase 0: carga shop_lt.txt (fuente de verdad)
    log("MAIN", f"catalogo tienda: {len(shop_catalog.CATALOG)} items")
    # ★ Y la tabla de las CÁPSULAS, acá y no la primera vez que alguien abra una (2026-09-08).
    #   El módulo la carga solo si hace falta, así que igual andaría — pero si el archivo NO está,
    #   con la carga perezosa nos enteramos recién cuando un jugador aprieta la máquina y no le
    #   abre. Cargándola en el arranque, el log lo dice antes de que entre nadie. Ver `gacha.py`.
    gacha.cargar()
    gacha.cargar_personajes()
    gacha.cargar_generos()
    _owned = notas.cargar()                               # ★ qué chart le toca a cada canción
    if _owned:
        # ⚠⚠ SE MUTA LA LISTA, NO SE REASIGNA (`[:]=` y no `=`). `OWNED_SONGS_2013` nace en
        #   `ajustes.py` y llega a los demás módulos por `from .x import *`, que copia el
        #   NOMBRE apuntando al MISMO objeto. Reasignarlo acá sólo cambiaba el nombre de
        #   este módulo: `lobby_menu` -que es quien arma el `FF49`- seguía viendo la lista
        #   vacía de su propia copia. Mutando en el lugar, los cuatro módulos ven las 814.
        OWNED_SONGS_2013[:] = _owned                       # picker = solo canciones que SÍ tienen chart
        log("MAIN", f"picker de música: {len(OWNED_SONGS_2013)} canciones con chart")
    # ★★ Los lugares (Sala de Conversación / charla de círculo) se crean ACÁ, al arrancar, y viven
    #   hasta que se baje el server. Entrar es UNIRSE a uno que ya existe.
    # ★ QUE SE VEA EN EL ARRANQUE si el banco de pruebas de NPC está encendido. Es una herramienta
    #   de LOCAL (va atada a `R2_CONSOLA_GM`) y silenciosa: sin esta línea, media sesión de prueba
    #   se puede ir en no entender por qué el gorila se comporta de una manera o de otra.
    try:
        from .ajustes import CHASE_NPC_REALISTA as _npc_real
        if _npc_real:
            log("MAIN", "🧪 NPC REALISTAS: ON — los NPC del gorila sacan puntajes con la forma "
                        "medida en prod (44 % de aciertos) y salen en el cartel SIN cobrar. "
                        "Sólo local: lo prende `R2_CONSOLA_GM`, que systemd no pone.")
    except Exception:
        pass
    # ⛔⛔ LA CONSOLA TAMBIÉN SE ANUNCIA SIEMPRE — 2026-09-16, y la pagó anonimo03:
    #   *"comandos gm no funcionando"*. Lo que había fallado era `.npc`, que **no es** un comando de
    #   GM sino de DESARROLLO, y pide `R2_CONSOLA_GM`. Los de GM andaban perfecto.
    #   ⚠ Pero desde afuera las dos cosas se ven **idénticas**: el comando se va como chat normal y
    #     no pasa nada. La única pista quedaba en el log del server, en una línea que hay que saber
    #     buscar — y ni siquiera decía en qué estado estaba la consola, así que no se podía saber
    #     si el problema era el permiso o la variable.
    #   ⇒ Es exactamente la lección que `gm.py` ya tenía escrita tres líneas más abajo (*"una
    #     puerta que falla en silencio no es auditable"*) y que a esta puerta le faltaba. Se emparejan.
    try:
        from .ajustes import CONSOLA_GM_TODOS as _cg_todos, CONSOLA_GM_USNS as _cg_usns
        if _cg_todos:
            _est = "ABIERTA a todos (R2_CONSOLA_GM=1) — es lo normal en LOCAL"
        elif _cg_usns:
            _est = f"abierta SÓLO a los usn {sorted(_cg_usns)} (R2_CONSOLA_GM con lista)"
        else:
            _est = ("CERRADA (no hay R2_CONSOLA_GM) — es lo normal en PROD. Los comandos de "
                    "DESARROLLO (.npc, .map, .salas…) no van a andar ni para un GM; los de GM "
                    "y los del juego sí. En local se abre arrancando con `startserver.bat`.")
        log("MAIN", f"consola de desarrollo: {_est}")
    except Exception:
        pass
    # ★★ Los lugares (Sala de Conversación / charla de círculo) se crean ACÁ, al arrancar.
    _nlug = crear_lugares_persistentes()
    log("MAIN", f"lugares persistentes: {_nlug} instancias vivas "
                f"(tipos {list(TIPOS_LUGAR_CHARLA)} x {INSTANCIAS_LUGAR_N}, capacidad {LUGAR_CAPACIDAD} c/u)")
    # ⛔⛔ LA PUERTA DE GM SE ANUNCIA SIEMPRE, DIGA LO QUE DIGA — la lección cara del CBT.
    #   De `SUBIR_A_PROD_20260802.md`: arrancar sin la lista la dejaba VACÍA y los comandos
    #   **se comportaban como chat normal, sin ningún error**. Y peor: uno de la misma familia
    #   seguía andando, que es la peor pista posible — te convence de que el problema es el
    #   comando y no la puerta.
    #   ★ El arreglo de allá no fue tocar la puerta: fue hacerla HABLAR al arrancar. Una puerta
    #     que no anuncia su configuración no se puede auditar. Por eso esta línea no tiene `if`.
    from . import gm as _gm
    log("MAIN", _gm.resumen())
    threading.Thread(target=listener, args=(LOGIN_PORT, handle_login, "LOGIN"), daemon=True).start()
    if MULTICANAL:
        # ★ Un LISTENER POR CANAL, como el CBT. El cliente elige el puerto solo: `0x4A5F60` busca la
        #   entrada cuyo (tier1,tier2) matchea su código de licencia/nivel, y conecta a ESE puerto.
        log("MAIN", f"LoginServer :{LOGIN_PORT}  +  {len(CANALES_2013)} CANALES (anuncio {LOBBY_IP})")
        for cat, _t1, _t2, code, clave, nombre, puerto in CANALES_2013:
            log("MAIN", f"  canal :{puerto}  cat=0x{cat:02X}  código={code}  {clave:<12} = {nombre}")
            threading.Thread(target=listener, args=(puerto, handle_lobby, "LOBBY"), daemon=True).start()
    else:
        log("MAIN", f"LoginServer :{LOGIN_PORT}  +  LobbyServer :{LOBBY_PORT}  (anuncio Lobby {LOBBY_IP}:{LOBBY_PORT})")
        threading.Thread(target=listener, args=(LOBBY_PORT, handle_lobby, "LOBBY"), daemon=True).start()
    # ★★★★★ EL BARRIDO DE SALAS FANTASMA — 2026-09-15. Ver `BARRIDO_MESAS_SEG` en `ajustes.py`
    #   para la medición que lo motiva (un jugador dado de baja el 12-sep seguía sentado en 3
    #   salas el 15-sep) y `salas.barrer_mesas_huerfanas` para las dos reglas que aplica.
    #   ★ Hilo propio y no "al pedir la lista": así limpia igual de noche, cuando no hay nadie
    #     pidiendo el `FF6E` — que es justo cuando las fantasma se acumulan sin que nadie mire.
    if BARRIDO_MESAS_SEG:
        from .salas import barrer_mesas_huerfanas as _barrer

        def _barrido():
            while True:
                time.sleep(BARRIDO_MESAS_SEG)
                try:
                    _barrer()
                except Exception as e:                                   # noqa: BLE001
                    # ⚠ Se traga la excepción A PROPÓSITO: este hilo no puede morirse. Si se muere,
                    #   el server sigue andando y las fantasma vuelven en silencio — el peor final.
                    log("SALA", f"  ⚠ barrido de mesas: {e!r}")

        threading.Thread(target=_barrido, daemon=True, name="barrido-mesas").start()
        log("MAIN", f"barrido de salas fantasma: cada {BARRIDO_MESAS_SEG}s")
    else:
        log("MAIN", "⚠ barrido de salas fantasma APAGADO (BARRIDO_MESAS_SEG=0)")
    # ★ 15-oct: la MISIÓN DE HOY (el tiempo conectado y lo pendiente, cada pocos segundos). Ver `mision_hoy.py`.
    try:
        from . import mision_hoy
        mision_hoy.arrancar()
    except Exception as _e_mh:                                       # noqa: BLE001
        log("MAIN", f"⚠ misión de hoy no arrancó: {_e_mh!r}")
    # ★★ EL SNAPSHOT PARA EL PANEL WEB. El panel no habla con nosotros: LEE un archivo, y si tiene
    #   más de 15 s lo da por caído. O sea que "salir en el panel" = escribir esto cada 3 s.
    from . import telemetria
    from .salas import CONEXIONES as _CONEX
    from .basedatos import db_nicks_de
    telemetria.arrancar(_CONEX, nick_de=lambda u: (db_get_char(u) or {}).get("nick", ""), nicks_de=db_nicks_de)
    log("MAIN", f"estado: status.json cada {telemetria.CADA:.0f}s -> {telemetria.RUTA}")
    # (La versión abierta no trae la API web ni el panel: sólo el juego.)
    log("MAIN", f"listo. Para entrar: python jugar.py   (Ctrl+C para parar)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        log("MAIN", "parado por el usuario")
        sys.exit(0)


if __name__ == "__main__":
    # Correr este archivo directo crearia la segunda copia del modulo que explica `main()`,
    # asi que se delega en la copia IMPORTADA, que es la unica que arma paquetes.
    import importlib

    importlib.import_module(__spec__.parent + ".lobby" if __spec__ and __spec__.parent
                            else "servidor.lobby").main()
