# -*- coding: utf-8 -*-
"""esquema — el SQLite del server 2013. El del CBT, más lo que este juego tiene y aquél no.

POR QUE SQLITE Y NO LOS DOS JSON
--------------------------------
`db_save()` reescribe `chars_db.json` ENTERO en cada guardado, sin archivo temporal ni `rename`
atómico. Con un jugador no se nota; con cien:

  1. dos guardados a la vez SE PISAN — el último gana y el otro pierde su progreso;
  2. un corte a mitad de escritura deja el JSON roto y se pierde **todo**, no una fila;
  3. el costo crece con la cantidad de jugadores, no con lo que cambió.

El CBT resolvió esto hace meses y su base está andando con 5.376 cuentas. Se reusa **el esquema**,
que es lo que el usuario pidió — *"no quisiera volverla a inventar"*.

⛔ **NO SE TRAEN LAS CUENTAS DE PRODUCCION.** Pedido explícito: *"tráete el sqlite pero no las
   cuentas… nuestras cuentas locales y las que jalamos, solamente ésas estén en local"*. Acá vive
   sólo lo que ya está en `cuentas.json` / `chars_db.json`.

QUE ES DEL CBT Y QUE ES NUESTRO
-------------------------------
Del CBT, tal cual: `users`, `chars`, `wear`, `inventory`, `sessions`, `friends`, `couples`,
`anillos`, `circulos`, `circulo_miembros`.

Nuestro, porque este juego lo tiene y el CBT no:
  · columnas extra en `chars`: `licencia`, `rpoint`, `monedas_gorila`, `leccion_max`,
    `misiones_todas`, `age`, `bio`, `guild`
  · tablas propias para lo que hoy son listas y diccionarios adentro del JSON:
    `mision_nibbles`, `misiones_hechas`, `misiones_grado`, `misiones_mascaras`,
    `premios`, `lecciones`
  · `record`: los contadores del perfil y de las medallas (24-sep)
  · `circulo_solicitudes`: los pedidos de entrar a un círculo (24-sep, `circulos.py`)
  · `circulo_economia`: nivel, EXP, dinero y marca de cada círculo (24-sep, el `FFD4`)

⛔⛔ `parts` NO son las 4 columnas `hair/top/bottom/skates` del CBT. Eso parecía —54 de nuestros
   58 personajes traen exactamente 4— pero **es una lista de largo variable y sin posición fija**:
   hay uno con 2 piezas, dos con 7 y uno con 8, y **el primer elemento no siempre es el pelo**
   (en dos casos arranca con la ropa de arriba, en otro con las alas).
   ⇒ Lo descubrió la comprobación de ida y vuelta de `migrar_a_sqlite.py`, que devolvía 4 piezas
     donde el JSON tenía 8. Sin esa comprobación, tres personajes habrían perdido la mitad de la
     ropa en silencio.
   ⇒ **La verdad vive en `wear`**, que es justamente la tabla que el CBT tiene para esto:
     una fila por prenda, con `role_id` = la POSICIÓN en la lista, para conservar el orden.
   ⇒ `hair/top/bottom/skates` quedan en el esquema porque son del CBT, pero **nosotros las
     dejamos en 0**: rellenarlas con las primeras cuatro sería inventar un significado que
     nuestros datos no tienen.
⛔ ACÁ DECÍA *"`gender` no se guarda aparte: sale de `char_id & 1`"*, y desde el gacha es FALSO.
  **`gender` es la columna que dice quién es el jugador**, y manda ella. Al equipar un personaje
  del gacha se pisa el `char_id`, y ese número deja de decir el sexo (`130029` y `110275` son
  impares y de HOMBRE, lo dice `hero.txt` del cliente). Mientras esta nota siguió diciendo que el
  dato era derivable, `char_a_filas` lo derivaba — y **le daba vuelta el sexo al jugador en cada
  guardado**. Hubo que reparar dos cuentas a mano el 2026-09-09.
  ⇒ Se lee y se escribe tal cual. Ver `almacen._genero_para_guardar` y `pruebas/probar_genero.py`.
"""

ESQUEMA = """
-- ═══ DEL CBT, SIN CAMBIOS ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    uid INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    pass_hash TEXT NOT NULL,
    reg_time TEXT, last_ip TEXT, last_time TEXT);

CREATE TABLE IF NOT EXISTS chars (
    uid INTEGER PRIMARY KEY,
    nickname TEXT NOT NULL,
    gender   INTEGER NOT NULL DEFAULT 0,   -- ★ 0 = hombre · 1 = mujer. NO se deriva del char_id:
                                           --   es el dato bueno cuando hay un personaje encima
    char_id  INTEGER NOT NULL DEFAULT 0,
    hair     INTEGER DEFAULT 0,
    top      INTEGER DEFAULT 0,
    bottom   INTEGER DEFAULT 0,
    skates   INTEGER DEFAULT 0,
    exp INTEGER DEFAULT 0, coin INTEGER DEFAULT 0, cash INTEGER DEFAULT 0,
    mission INTEGER DEFAULT 0,
    created_at TEXT,
    -- ── nuestras, que el CBT no tiene ──
    licencia        INTEGER DEFAULT 0,     -- máscara de 3 bits: 1 estrella · 2 luna · 4 sol
    rpoint          INTEGER DEFAULT 0,
    monedas_gorila  INTEGER DEFAULT 0,
    leccion_max     INTEGER DEFAULT 0,
    misiones_todas  INTEGER DEFAULT 0,     -- la escapatoria del nibble del grupo 1
    age             INTEGER DEFAULT 0,
    bio             TEXT DEFAULT '',
    guild           TEXT DEFAULT '');

CREATE TABLE IF NOT EXISTS wear (
    uid INTEGER NOT NULL, role_id INTEGER DEFAULT 0, item_id INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS inventory (
    uid      INTEGER NOT NULL,
    item_id  INTEGER NOT NULL,
    end_time INTEGER DEFAULT 0,            -- 0 = permanente
    in_use   INTEGER DEFAULT 0,
    count    INTEGER DEFAULT 0,
    get_time INTEGER DEFAULT 0,
    storage  INTEGER DEFAULT 0,
    UNIQUE(uid, item_id));

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY, uid INTEGER NOT NULL, ip TEXT,
    valid_time TEXT, created_at TEXT);

CREATE TABLE IF NOT EXISTS friends (
    uid INTEGER NOT NULL, friend_uid INTEGER NOT NULL, added_at TEXT,
    UNIQUE(uid, friend_uid));

CREATE TABLE IF NOT EXISTS couples (
    uid INTEGER PRIMARY KEY, partner_uid INTEGER NOT NULL, since TEXT);

CREATE TABLE IF NOT EXISTS anillos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL, item_id INTEGER NOT NULL,
    estado INTEGER NOT NULL DEFAULT 0,     -- 0 sin usar · 1 en uso · 2 roto
    partner_uid INTEGER DEFAULT 0, desde INTEGER DEFAULT 0, hasta INTEGER DEFAULT 0);

-- ★★ EL AMIGO DEL ALMA / JOYA DE LA AMISTAD (FF40 sub 0x3B) — 2026-09-15
--   Es como `friends` y NO como `couples`: se puede tener MÁS DE UNO (str#896 habla de un
--   "máximo"), así que no lleva PRIMARY KEY sobre el uid. El tope lo pone `ajustes.ALMA_TOPE`.
--   ⚠ `joya` es el Index de `ring.txt` (<Friend>), y NO puede quedar en 0: el cliente lo busca
--     en su tabla de ítems y, si no lo encuentra, **no agrega la fila al panel** (0x45F430).
-- ★ LA CONFESIÓN DE PAREJA — 2026-09-27. El texto que el jugador escribe en «Mi Pareja → Anillos
--   de pareja» y que viaja pegado al cambio de anillo (`FF40 0A/0F [u32 ChargeId][u8 len][texto]`).
--   Se ve en «Ver perfil → Info Pareja → Mi confesión» (el 1er texto del bloque de pareja del
--   `FF77`/`FF78`, 132 B en el cliente). Una por jugador: es SU confesión, no la de la pareja.
CREATE TABLE IF NOT EXISTS confesiones (
    uid INTEGER PRIMARY KEY, texto TEXT DEFAULT '', cuando INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS almas (
    uid INTEGER NOT NULL, otro_uid INTEGER NOT NULL,
    joya INTEGER DEFAULT 0, desde INTEGER DEFAULT 0,
    UNIQUE(uid, otro_uid));

-- ★★ EL RÉCORD DEL JUGADOR y LAS MEDALLAS — 2026-09-24. Ver `documentacion/MEDALLAS_Y_RECORD.md`.
--   Una fila por personaje, que se crea en la primera carrera cobrada. Los contadores los lee el
--   cliente del `FF77` (el perfil y la pestaña «Mis Medallas»): él decide qué medallas tenés
--   comparándolos con su `medal_lt.txt`. `medalla` = la puesta (0 = ninguna), la elige con el `FFD2`.
--   ⛔ Tabla propia y NO columnas en `chars`: `rpoint` enseñó lo que pasa con una columna suelta.
CREATE TABLE IF NOT EXISTS record (
    uid INTEGER PRIMARY KEY,
    ganadas   INTEGER DEFAULT 0, perdidas  INTEGER DEFAULT 0, empates INTEGER DEFAULT 0,
    pd97      INTEGER DEFAULT 0, allcombo  INTEGER DEFAULT 0,
    exp_max   INTEGER DEFAULT 0, rcoin_max INTEGER DEFAULT 0,
    medalla   INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS circulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL, aviso TEXT DEFAULT '',
    lider_uid INTEGER DEFAULT 0, creado_at TEXT);

CREATE TABLE IF NOT EXISTS circulo_miembros (
    uid INTEGER PRIMARY KEY, circulo_id INTEGER NOT NULL,
    rango INTEGER DEFAULT 0, desde TEXT);

-- ★ El pedido de entrar a un círculo (24-sep). Uno por persona: pedir en otro pisa el anterior.
--   En el original esto era la página `CircleRequest.aspx` de la web de Softnyx.
CREATE TABLE IF NOT EXISTS circulo_solicitudes (
    uid INTEGER PRIMARY KEY, circulo_id INTEGER NOT NULL, fecha TEXT);

-- ★ La «economía» del círculo (24-sep): lo que viaja en el `FFD4`. Tabla aparte (y no columnas en
--   `circulos`) para no tener que hacer ALTER sobre la tabla que ya existe en prod.
-- ★ Lo que donó cada uno a SU círculo (25-sep): la columna «Rcoin donados» y el ranking de
--   donación. Por (uid, círculo): si se va y vuelve a otro, lo del anterior no lo sigue.
CREATE TABLE IF NOT EXISTS circulo_donaciones (
    uid INTEGER NOT NULL, circulo_id INTEGER NOT NULL,
    total INTEGER DEFAULT 0, ultima TEXT,
    PRIMARY KEY (uid, circulo_id));

-- ★ El INVENTARIO del círculo (25-sep): lo comprado en la tienda del círculo. Es del CÍRCULO, no
--   del que lo compró. Viaja en el registro de 60 B del `FFD7`/`FFDA` (`circulo_tienda.armar_registro`).
--   `clave` = el serial que el cliente usa para todo (upsert, extender, colocar).
CREATE TABLE IF NOT EXISTS circulo_items (
    clave INTEGER PRIMARY KEY AUTOINCREMENT,
    circulo_id INTEGER NOT NULL,
    item INTEGER NOT NULL,          -- el Index de circleshop.xml, SIN el dígito del periodo
    vence INTEGER DEFAULT 0,        -- UNIX; 0 = permanente
    estado INTEGER DEFAULT 88,      -- 'X' (88) = guardado; '0'+n = colocado (n = orientación)
    x INTEGER DEFAULT 0, y INTEGER DEFAULT 0, z INTEGER DEFAULT 0,
    padre INTEGER DEFAULT 0, enganche INTEGER DEFAULT 0,
    comprado_por INTEGER DEFAULT 0, fecha TEXT);

-- ★ El ESTILO DEL CHAT de cada jugador (25-sep): el globo y el crayón (color de letra) que tildó en
--   Mi Casa. Aparte de `parts` a propósito: lo puesto viaja en el FF0C, y esto no es ropa.
CREATE TABLE IF NOT EXISTS estilo_chat (
    uid INTEGER PRIMARY KEY, globo INTEGER DEFAULT 0, crayon INTEGER DEFAULT 0);

-- ★ El LÁPIZ del APODO (25-sep): el color del nombre en el asiento y sobre la cabeza. Tabla aparte
--   (y no una columna más en `estilo_chat`) porque aquélla ya existe y el server no hace ALTER.
CREATE TABLE IF NOT EXISTS color_apodo (uid INTEGER PRIMARY KEY, lapiz INTEGER DEFAULT 0);

-- ★ El CRAYÓN DE CÍRCULO (23-oct, CRAYONES_MAZINO.md): el color del NOMBRE DEL CÍRCULO, por jugador. Igual que el
--   lápiz del apodo; viaja como una marca al principio del nombre del círculo (paquetes._marca_circulo).
CREATE TABLE IF NOT EXISTS color_circulo (uid INTEGER PRIMARY KEY, lapiz INTEGER DEFAULT 0);

-- ★ LOS AVISOS DE REGALO pendientes (12-oct, `regalo.py`): «Ha recibido [ítem] de X» — van en el FF54 que el cliente
--   pide al entrar al lobby (el que no estaba conectado, o estaba en carrera, cuando se lo mandaron).
CREATE TABLE IF NOT EXISTS regalos_avisos (
    uid INTEGER NOT NULL, de TEXT NOT NULL, item INTEGER NOT NULL, rcoin INTEGER DEFAULT 0, cuando REAL);

-- ★ «MIS PREFERIDOS» DE LA TIENDA (12-oct, `preferidos.py`): el carrito/favoritos, hasta 24 por cuenta.
CREATE TABLE IF NOT EXISTS preferidos_tienda (
    uid INTEGER NOT NULL, item INTEGER NOT NULL, PRIMARY KEY (uid, item));

-- ★ LOS SETS DEL ARMARIO (12-oct, `conjuntos.py`, `documentacion/ARMARIO_CONJUNTOS.md`): SET1..SET4 = conjunto 0..3,
--   `items` = los ids separados por coma, en el orden en que los mandó el cliente.
CREATE TABLE IF NOT EXISTS conjuntos (
    uid INTEGER NOT NULL, conjunto INTEGER NOT NULL, items TEXT NOT NULL, cuando REAL,
    PRIMARY KEY (uid, conjunto));

-- ★ «¿QUIÉN TE INVITÓ?» (11-oct, `referido.py`, `documentacion/REFERIDO.md`): una fila por cuenta que CREÓ su
--   personaje con esto andando. invitador NULL = la ventana está pendiente · 0 = omitió · >0 = el uid que cobró.
CREATE TABLE IF NOT EXISTS referidos (
    uid INTEGER PRIMARY KEY, creado REAL NOT NULL, invitador INTEGER, apodo TEXT,
    cuando REAL, rcoin INTEGER DEFAULT 0, ip TEXT);

-- ★ EL PICKER (29-sep, `picker.py`, `documentacion/PICKER_SISTEMA.md`):
--   las PREFERIDAS de cada jugador (el ícono de la fila; C→S FF138 agrega · FF13A quita · S→C FF137);
CREATE TABLE IF NOT EXISTS preferidas (
    uid INTEGER NOT NULL, cancion INTEGER NOT NULL, PRIMARY KEY (uid, cancion));
--   «Mi record» por canción (FF139): veces TERMINADA, mejor combo, mejor precisión ×1000 (pd*1000 +
--   milésimas), si alguna vez fue all combo, y cuándo;
CREATE TABLE IF NOT EXISTS record_cancion (
    uid INTEGER NOT NULL, cancion INTEGER NOT NULL, veces INTEGER DEFAULT 0,
    mejor_combo INTEGER DEFAULT 0, mejor_pd INTEGER DEFAULT 0, allcombo INTEGER DEFAULT 0,
    ultima INTEGER DEFAULT 0, PRIMARY KEY (uid, cancion));
--   ★ TOP 5 RANK (09-oct, `picker.cola_top5`): CUÁNDO se hizo el récord de (uid, canción) y en qué TIEMPO llegó
--   a la meta (el `frame` del FF28 C→S: pasos de la lógica, la unidad de `Time` de music_lt = 1/60 s). `ultima`
--   es la última vez que la terminó, no la del récord. Tabla aparte porque el server no hace ALTER. Los récords
--   de antes no tienen fila: el ranking muestra su `ultima` y el tiempo «-» (anonimo03, 09-oct: aceptado).
--   (Se llamó `record_fecha` unas horas, sólo en local: si quedó en una base, no la lee nadie.)
CREATE TABLE IF NOT EXISTS record_mejor (
    uid INTEGER NOT NULL, cancion INTEGER NOT NULL, fecha INTEGER DEFAULT 0, frame INTEGER DEFAULT 0,
    PRIMARY KEY (uid, cancion));
--   y las jugadas por DÍA de cada canción, para la POPULARIDAD («Canal popular N° lugar», FF13B, TOP 20).
CREATE TABLE IF NOT EXISTS jugadas_dia (
    dia TEXT NOT NULL, cancion INTEGER NOT NULL, veces INTEGER DEFAULT 0, PRIMARY KEY (dia, cancion));

-- ★ La PRESENTACIÓN PERSONAL (29-sep, `presentacion.py`): la LETRA de «Buscar amigos» (Y sale en la
--   lista · N no sale · X ya contestó el cartel · Z todavía no tenía nivel 6 · '' nunca contestó ⇒ el
--   cliente pregunta en cada entrada), la edad y el texto. Tabla aparte porque el server no hace ALTER;
--   `chars.age`/`chars.bio` quedan como lo viejo (se leen si no hay fila).
CREATE TABLE IF NOT EXISTS presentacion (
    uid INTEGER PRIMARY KEY, marca TEXT DEFAULT '', edad INTEGER DEFAULT 0,
    texto TEXT DEFAULT '', fecha INTEGER DEFAULT 0);

-- ★ La TIRA DE ANUNCIOS de arriba del lobby (29-sep, `tira.py`, FFBF): cada fila es un anuncio.
--   `hasta` = epoch de vencimiento (0 = para siempre). Se edita en vivo con `.tira` y se difunde a todos.
CREATE TABLE IF NOT EXISTS tira_anuncios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT NOT NULL, hasta INTEGER DEFAULT 0,
    activo INTEGER DEFAULT 1, quien TEXT DEFAULT '', creado INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS circulo_economia (
    circulo_id INTEGER PRIMARY KEY,
    nivel  INTEGER DEFAULT 1,     -- 1..10 (el cliente lo deduce del TOPE que le mandamos)
    exp    INTEGER DEFAULT 0,     -- la EXP del círculo (sube donando: 1 Rcoin = 1 EXP)
    dinero INTEGER DEFAULT 0,     -- el «dinero de círculo» (100 Rcoin donados = 1)
    marca  INTEGER DEFAULT 0);    -- (logo << 16) | fondo

-- ═══ NUESTRAS: lo que hoy son listas y dicts adentro del JSON ════════════════
-- El nibble es AVANCE MAXIMO por grupo, no una cantidad. Ver mapeo_misiones.md §3.
CREATE TABLE IF NOT EXISTS mision_nibbles (
    uid INTEGER PRIMARY KEY, n0 INTEGER DEFAULT 0, n1 INTEGER DEFAULT 0, n2 INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS misiones_hechas (
    uid INTEGER NOT NULL, grupo INTEGER NOT NULL, mision INTEGER NOT NULL,
    UNIQUE(uid, grupo, mision));

CREATE TABLE IF NOT EXISTS misiones_grado (
    uid INTEGER NOT NULL, mision INTEGER NOT NULL, grado TEXT NOT NULL,
    UNIQUE(uid, mision));

CREATE TABLE IF NOT EXISTS misiones_mascaras (
    uid INTEGER NOT NULL, mascara INTEGER NOT NULL, UNIQUE(uid, mascara));

-- `tipo` = 'items' o 'rcoin': un premio se cobra UNA vez por mision y por tipo.
CREATE TABLE IF NOT EXISTS premios (
    uid INTEGER NOT NULL, mision INTEGER NOT NULL, tipo TEXT NOT NULL,
    UNIQUE(uid, mision, tipo));

CREATE TABLE IF NOT EXISTS lecciones (
    uid INTEGER NOT NULL, leccion INTEGER NOT NULL, UNIQUE(uid, leccion));

-- ★ 21-oct (la landing de r2portable, anonimo03): hasta 4 PERSONAJES por cuenta, cada uno APARTE (su propio uid en
--   `chars`). El casillero 1 es la cuenta misma (`users.uid`) y no lleva fila; acá van los 2, 3 y 4
--   (`cuenta_personajes.py`). `username` respeta mayúsculas, como `users`.
CREATE TABLE IF NOT EXISTS cuenta_personajes (
    username TEXT NOT NULL, ranura INTEGER NOT NULL, uid INTEGER NOT NULL UNIQUE,
    PRIMARY KEY (username, ranura));
-- ★ 24-oct (anonimo03): «borrar» un personaje desde el selector NO lo borra de la base — deja de mostrarse, para poder
--   recuperarlo A MANO. Su fila de `cuenta_personajes` pasa acá (el casillero queda libre) y TODO lo suyo en `chars`,
--   `inventory`, `wear`… queda intacto. Recuperarlo: volver a insertar (username, ranura, uid) en `cuenta_personajes`
--   (con el casillero libre) y borrar la fila de acá.
CREATE TABLE IF NOT EXISTS personajes_borrados (
    uid INTEGER PRIMARY KEY, username TEXT NOT NULL, ranura INTEGER NOT NULL, apodo TEXT, cuando TEXT NOT NULL);
-- ★ 25-oct (anonimo03: «fusionar, separar cuentas… control total», desde el panel): un personaje se MUDA de cuenta sin
--   copiarse ni borrarse — es el mismo uid, con su Rcoin, EXP, inventario y todo. Cada mudanza queda anotada acá
--   (de dónde a dónde) y así se DESHACE. La cuenta que se queda sin su casillero 1 queda BLOQUEADA: `FUSIONADA:`
--   delante de su `pass_hash` (como el `BANNED:` del ban: reversible). `almacen.mover_personaje` y compañía.
CREATE TABLE IF NOT EXISTS movimientos_personajes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
    de_cuenta TEXT, de_ranura INTEGER, a_cuenta TEXT, a_ranura INTEGER,
    motivo TEXT NOT NULL, actor INTEGER DEFAULT 0, cuando TEXT NOT NULL, deshecho INTEGER DEFAULT 0);

CREATE INDEX IF NOT EXISTS ix_inv_uid   ON inventory(uid);
CREATE INDEX IF NOT EXISTS ix_chars_nk  ON chars(nickname);
-- ★ 29-sep (optimización para el VPS, `documentacion/BANCO_VPS.md` §5): `wear` NO tenía índice, y cada
--   lectura de un personaje (`almacen.filas_a_char`, cientos por minuto: la sala, el MyRecord, el panel) y
--   cada guardado (el `DELETE … WHERE uid=?`) RECORRÍA sus ~20.000 filas enteras. Era lo más caro del server.
--   Mismo resultado (`probar_optimizaciones.py` §7); lo crea el server solo al arrancar (~20 ms).
CREATE INDEX IF NOT EXISTS ix_wear_uid  ON wear(uid, role_id);
-- ★ 09-oct (TOP 5 RANK): el ranking de UNA canción se pide en cada FF139 (el cursor quieto 1,5 s). La llave de
--   `record_cancion` es (uid, canción): sin esto cada pedido recorrería la tabla entera.
CREATE INDEX IF NOT EXISTS ix_record_top ON record_cancion(cancion, mejor_pd, mejor_combo);
"""
