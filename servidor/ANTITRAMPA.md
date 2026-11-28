# Antitrampa — referencia para el panel web

Todo lo que hace el antitrampa (la dll del cliente y el servidor), qué datos deja y dónde, para armar
un panel web encima. El catálogo de reglas también está en JSON, listo para el panel:
[`antitrampa_catalogo.json`](antitrampa_catalogo.json).

- Código del servidor: [`antitrampa.py`](antitrampa.py) · ajustes: [`ajustes.py`](ajustes.py) (`ANTITRAMPA_*`)
- Código de la dll: [`../herramientas/dll_d3d9/fuente/antitrampa.c`](../herramientas/dll_d3d9/fuente/antitrampa.c)
- Pruebas: `pruebas/probar_antitrampa.py` (server) · `herramientas/dll_d3d9/probar_antitrampa.py` (dll)

---

## 1. Cómo funciona, de punta a punta

```
 d3d9.dll (en el juego)                     servidor                                 panel web
 ──────────────────────                     ────────                                 ─────────
 revisa cada 5 s ──► «R2AT …» por FF59 ──►  antitrampa.al_ff59 ─► regla ─► acción ──►  datos/antitrampa.jsonl
                                            el cartel FF28 ─────► regla ─┘            tabla antitrampa_faltas
                                            señales de farmeo ──► regla ─┘            users.pass_hash (BANNED:)
```

1. La **dll** mira el juego desde adentro y manda lo que encuentra como renglones `R2AT clave=valor …`
   (§ 3), de a uno por segundo, por el reporte de errores del juego (`FF59`).
2. El **servidor** también mira por su cuenta: el cartel de fin de carrera (`FF28`) y el comportamiento
   (señales de farmeo).
3. Cada cosa encontrada es una **regla** (§ 4) con una **acción** (§ 5). Todo queda anotado en
   `datos/antitrampa.jsonl` (§ 7), sea cual sea la acción.
4. ★ 24-nov · **Modo silencioso** (`ANTITRAMPA_SILENCIOSO = True`, de fábrica, § 5b): lo que «expulsa» no echa a
   nadie al momento. El jugador no se entera; sus carreras dejan de cobrar y la detección queda **pendiente**
   hasta que un GM aplica la **tanda** de sanciones (`.sanciones aplicar`). Así el tramposo no sabe qué lo delató.
5. ★ 26-nov · **Registro central y tablero** (§ 10): toda detección es un EVENTO en `antitrampa_eventos` (categoría,
   riesgo, confianza, sesión, partida, versiones, reincidencias, estado de revisión) que se ve en vivo en el tablero
   (`tablero_antitrampa.py`), donde los admins revisan, descartan, advierten, suspenden y banean.

## 2. Qué revisa la dll

| # | Revisión | Cada | Renglón que manda | Regla en el server |
|---|---|---|---|---|
| 1 | Al arrancar: md5 del exe, y si alguien tocó el exe **antes** que la dll | una vez | `R2AT v=1 exe=<md5> previo=<n> [previo_va=0x…]` | `exe_desconocido`, `codigo_previo` |
| 2 | Páginas de código del exe escritas desde afuera (como un trainer) | 5 s | `R2AT codigo=0x<va> paginas=<n> bytes=<8 bytes>` | `codigo_modificado` |
| 3 | **Ganchos conocidos** de herramientas de farmeo (§ 2.1) | 5 s | `R2AT gancho=<nombre> va=0x<va> bytes=<8 bytes>` | `juego_automatico`, `sala_automatica`, `relevo_automatico` |
| 4 | Módulos cargados con nombre de trampa (§ 2.2) | 15 s | `R2AT modulo=<archivo>` | `modulo_prohibido` |
| 5 | Memoria ejecutable que no es de ningún módulo (código inyectado) | 30 s | `R2AT memoria=0x<va> regiones=<n>` | `memoria_ajena` |
| 6 | Teclas mandadas por un programa (`SendInput`/`keybd_event`) | 60 s | `R2AT teclas=<n> inyectadas=<n>` | `teclas_inyectadas` |
| 7 | Hilos que arrancan en memoria inyectada | 10 s | `R2AT hilo=0x<va>` | `hilo_ajeno` |
| 8 | Procesos de trampas abiertos a la vez que el juego (§ 2.2) | 30 s | `R2AT proceso=<exe>` | `proceso_prohibido` |
| 9 | Depurador pegado al juego | 5 s | `R2AT depurador=1` | `depurador` |

**El cierre del juego** (★ 24-nov: **apagado de fábrica**, por el modo silencioso: la dll sólo informa).
Con `[antitrampa] cerrar=1` en `d3d9_proxy.ini`, si la revisión 3 encuentra un gancho, la dll manda el aviso,
espera a que salga (hasta 10 s), muestra el cartel «Ñ2-AntiCheat» y **cierra el juego** (a los 20 s como mucho,
aunque nadie toque el cartel).

**La pantalla de prevención.** Al abrir el juego la dll muestra «Ñ2-AntiCheat · Verificando el juego… N %»
abajo a la derecha (`antitrampa_pantalla.bmp` junto a la dll; `pantalla_centro=1` la centra,
`pantalla=0` la apaga).

### 2.1 Ganchos conocidos (medidos en el juego con Ñ2Hock, 19-nov-2026)

| Nombre (`gancho=`) | Dirección | Bytes originales | Qué función lo pone | Regla |
|---|---|---|---|---|
| `automatico` | `0x005080B5` (R2Beat.exe+0x1080B5) | `6A 00 8D 44 24` | «Juego automático» (con Azar / Precisión) | `juego_automatico` |
| `sala` | `0x005AEDD4` (+0x1AEDD4) | `8B 0D D4 14 93 00` | «Auto Listo / Inicio», «Anfitrión: al azar», «Misma canción» | `sala_automatica` |
| `relevo` | `0x00505340` (+0x105340) | (el gancho de relevo de nuestra dll) | «Auto Relevo» — con nuestra dll Ñ2Hock no lo puede poner | `relevo_automatico` |
| `tick_meta` | `0x0050A170` (+0x10A170) | (los de fábrica) | Lab: «Automático Normal» y «Simular llegada» | `juego_automatico` |
| `auto_normal` | `0x00509130` (+0x109130) | (los de fábrica) | Lab: auxiliar del «Automático Normal» | `juego_automatico` |
| `pd0` | `0x005003D0` (+0x1003D0) | (los de fábrica) | Lab: «Automático PD0 silencioso» (la consulta del ítem devuelve activo) | `juego_automatico` |
| `larga_a` | `0x005060B5` (+0x1060B5) | `0F 85 DC 00 00 00` | Lab: las largas A se juegan solas (6 NOP) | `juego_automatico` |
| `larga_b` | `0x005064F6` (+0x1064F6) | `0F 85 E2 00 00 00` | Lab: las largas B se juegan solas (6 NOP) | `juego_automatico` |
| `item_auto` | `0x0050CAB6` (+0x10CAB6) | `FF 8E 34 03 00 00` | Lab: el activador del ítem automático 1000659 | `juego_automatico` |
| `resultado` | `0x00501458` (+0x101458) | (los de fábrica) | Lab: «Precisión / Combo personalizados» en el FF28 | `resultado_alterado` |
| `resultado_solo` | `0x005C887B` (+0x1C887B) | (los de fábrica) | Lab: precisión personalizada en Juego Solo | `resultado_alterado` |

Las de «Lab» salen de `INFORME_LABORATORIO.md` (R2AutoRouteLab2013, 24-nov-2026). Ni nuestra dll ni las
funciones permitidas de Ñ2Hock tocan esas direcciones: si cambian, es una trampa. La dll compara con los
bytes que tenía el exe al cargarse.

Con la casilla desmarcada los bytes vuelven a los originales: **usar Ñ2Hock sin sus funciones
automáticas no se detecta como trampa**. Una dll vieja (sin `gancho=`) los manda como `codigo=` con esa
misma dirección, y el server los reconoce igual (`ANTITRAMPA_GANCHOS` en `ajustes.py`).

### 2.1b Programas externos (INFORME_DEFENSA_CANDY0503.md, 24-nov-2026)

Candy («一颗糖», `Candy0503.exe`, md5 `09f983f84a55e77a4b4c5c0fe5bcf79f`) dice «no necesita inyectarse»: abre el
juego y escribe su memoria desde afuera. La dll lo mira de tres formas:

| Qué | Cada cuánto | Renglón | Regla |
|---|---|---|---|
| El nombre del proceso (`candy`, `r2autoroutelab` en la lista de § 2.2) | 30 s | `R2AT proceso=<exe>` | `proceso_prohibido` |
| La firma del exe aunque lo renombren: VersionInfo `ProductName`/`FileDescription` «Candy…», o el md5 (sólo si el tamaño es el de una muestra conocida) | 30 s, una vez por proceso | `R2AT proceso=<exe> firma=<producto_candy\|descripcion_candy\|md5_xxxxxxxx>` | `proceso_prohibido` |
| Quién tiene abierto el juego con permiso de **escribir** su memoria o **crearle hilos** (tabla de handles del sistema; csrss, lsass, svchost, Defender… no cuentan) | 30 s, una vez por programa | `R2AT manija=<exe> acceso=0x<permisos>` | `manija_escritura` |

### 2.2 Nombres que se buscan

- **Módulos** (`modulo=`): `toolbit`, `r2mods`, `d3dref9` (no el de la carpeta de Windows), `r2tr.`,
  `n2hock`, `speedhack`, `cheatengine`, `vehdebug`, `dbk32`, `dbk64` (contiene el texto, sin importar
  mayúsculas). **Menos** `toolbitpracticeengine…`: el motor de práctica de Ñ2Hock (Entreno), que no es trampa.
- **Procesos** (`proceso=`): `cheatengine`, `toolbit`, `r2tr.exe`, `gearnt`, `speedgear`, `speederxp`,
  `artmoney`, `wpepro`, `x32dbg`, `ollydbg`.

## 3. Formato de los renglones `R2AT`

Un renglón por mensaje: `R2AT` y pares `clave=valor` separados por espacios (sin espacios adentro de un
valor). Los bytes van como hex separados por `_`: `E9_46_81_A9_03_90_90_6A`. El server los lee con
`antitrampa.al_ff59` (la regex `R2AT((?: \w+=\S+)+)`).

## 4. Las reglas

`origen`: **dll** = la manda la dll · **cartel** = el server la ve en el `FF28` de fin de carrera ·
**farmeo** = el server la ve en el comportamiento (varias carreras).

| Regla | Acción hoy | Origen | Qué significa |
|---|---|---|---|
| `juego_automatico` | expulsar | dll | El «juego automático» de Ñ2Hock/ToolBit (gancho `automatico`) |
| `sala_automatica` | expulsar | dll | Auto Listo / Inicio, Anfitrión al azar o Misma canción (gancho `sala`) |
| `relevo_automatico` | expulsar | dll | Alguien pisó el gancho del relevo (Auto Relevo) |
| `resultado_alterado` | expulsar | dll | El armado del resultado (FF28 o Juego Solo) reescrito: precisión o combo personalizados |
| `modulo_prohibido` | expulsar | dll | Tiene cargado un módulo de trampas (ToolBit, R2Mods, Cheat Engine…) |
| `proceso_prohibido` | ★ avisar | dll | Tiene abierto un programa de trampas. **Solo no prueba nada** (26-nov): ver `manipulacion_correlacionada` (§ 10) |
| `farmeo` | expulsar | farmeo | Dos o más señales de farmeo distintas en la misma sesión (`ANTITRAMPA_FARMEO_SENALES`) |
| `combo_imposible` | retener | cartel | Más combo que notas tiene la canción |
| `porcentaje_imposible` | retener | cartel | PD o estrellas por encima de 100 |
| `precision_imposible` | retener | cartel | Milésimas > 999, o 100 % con milésimas (el tope es 100.000) |
| `manija_escritura` | registrar | dll | Un programa tiene abierto el juego con permiso de escribir su memoria (Candy, R2AutoRouteLab: no se inyectan). El sistema no cuenta |
| `manija_conocida` | registrar | dll | ★ 28-nov: lo mismo, pero el launcher que abrió el juego, una superposición (Discord, Steam, OBS…) o un antivirus (`ANTITRAMPA_MANIJAS_CONOCIDAS`). No correlaciona |
| `trampa_conocida` | expulsar | dll | ★ 28-nov: la dirección tocada es, según el catálogo `antitrampa_firmas.py`, una trampa que NO es de Ñ2Hock (los automáticos, el resultado falso de R2AutoRouteLab). El detalle dice «usa: programa · función» |
| `n2hock_permitido` | registrar | dll | ★ 28-nov: la dirección tocada es una función de Ñ2Hock (sin piedra, Supr, niebla, obstáculos, autoimpulso, teclado, precisión, cámara, Far, práctica…). **Todo lo de Ñ2Hock está permitido**: no retiene ni correlaciona |
| `arranque_restaurado` | registrar | dll | ★ 28-nov: el punto de entrada del exe lo tocó un inyector/launcher al abrir el juego y ya está de fábrica |
| `llegada_anticipada` | avisar | cartel | Llegó a la meta en menos del 75 % de lo que tarda esa canción (mediana de sus llegadas limpias): «Simular llegada» |
| `codigo_modificado` | avisar | dll | El exe fue tocado desde afuera (otros parches de Ñ2Hock: far, teclado…) |
| `codigo_previo` | avisar | dll | El exe ya estaba tocado antes de que arrancara la dll |
| `reloj_rapido` | avisar | cartel | El reloj del juego corrió más que el tiempo real desde el GO (speedhack) |
| `reloj_lento` | avisar | cartel | El reloj del juego corrió bastante menos que el tiempo real (juego frenado) |
| `animaciones_tocadas` | avisar | cartel | Las animaciones de tropezar no coinciden con las del server |
| `teclas_inyectadas` | avisar | dll | Teclas mandadas por un programa (cuenta como señal de farmeo) |
| `hilo_ajeno` | avisar | dll | Un hilo del juego arranca en código inyectado |
| `listo_automatico` | avisar | farmeo | «Listo»/«Iniciar» siempre al mismo instante tras la carrera |
| `carreras_sin_hablar` | avisar | farmeo | Muchas carreras seguidas sin una línea de chat |
| `misma_cancion` | avisar | farmeo | La misma canción muchas veces seguidas |
| `campanas_automaticas` | avisar | farmeo | Tocó campana en cada ronda, muchas rondas seguidas |
| `combo_repetido` | avisar | farmeo | El mismo combo en canciones distintas (fallar a propósito al llegar a N) |
| `precision_constante` | avisar | farmeo | La misma precisión en canciones de niveles muy distintos |
| `modulo_permitido` | registrar | dll | Un módulo con nombre «de trampa» que no lo es: el motor de práctica de Ñ2Hock, `ToolBitPracticeEngine_<hash>.dll` (`ANTITRAMPA_MODULOS_PERMITIDOS`) |
| `exe_desconocido` | registrar | dll | El R2Beat.exe no es uno de los aceptados (`ANTITRAMPA_EXE_MD5`) |
| `memoria_ajena` | registrar | dll | Hay código inyectado (Ñ2Hock lo tiene siempre: por eso sólo se registra) |
| `depurador` | registrar | dll | Un depurador pegado al juego |
| `sin_antitrampa` | registrar | cartel | Terminó una carrera sin que su dll mandara el «hola» |
| `expulsa_espectadores` | registrar | farmeo | El anfitrión echa espectadores en serie |

Las acciones se cambian en `ANTITRAMPA_REGLAS` (`ajustes.py`), una por regla.

## 5. Las acciones

| Acción | Qué hace |
|---|---|
| `apagado` | Nada (ni se anota) |
| `registrar` | Sólo queda en `antitrampa.jsonl` |
| `avisar` | Lo anterior + mensaje a los GM conectados |
| `retener` | Lo anterior + esa carrera no paga EXP ni Rcoin (si es una regla de la dll, ninguna carrera de esa sesión) |
| `expulsar` | Lo anterior + **la escalera** (§ 6): mensaje al jugador, anuncio público, se corta la conexión. ★ Con `ANTITRAMPA_SILENCIOSO` (de fábrica): nada de eso al momento, ver § 5b |

### 5b. El modo silencioso y la tanda (24-nov-2026)

Con `ANTITRAMPA_SILENCIOSO = True`, una regla `expulsar`:

1. **No** echa al jugador, **no** le manda ningún mensaje y **no** sale ningún anuncio. La dll tampoco cierra
   el juego (§ 2). El jugador no tiene forma de saber qué lo detectó, ni cuándo.
2. Desde ese momento, hasta que cierre el juego, **ninguna carrera le paga** (ni EXP, ni Rcoin, ni récord, ni
   medallas, ni misiones), igual que `retener`.
3. Los GM conectados ven `ANTITRAMPA <regla>: <nick> detectado en silencio (premio retenido, sancion pendiente #N)`.
4. Queda una fila en `antitrampa_pendientes` (§ 7.2c): una por regla distinta y por sesión del juego.
5. **La tanda**: un GM escribe `.sanciones aplicar` y cada cuenta con detecciones de más de
   `ANTITRAMPA_TANDA_DEMORA_H` horas (12) recibe **una** falta de la escalera (§ 6), junte las que junte. Si está
   conectado, ahí sí se lo saca con su mensaje; el anuncio público sale en ese momento. Con el Coordinador, el
   aviso al Coordinador también sale en la tanda.

| Comando (GM) | Qué hace |
|---|---|
| `.sanciones` | Quién tiene detecciones pendientes, qué reglas, desde cuándo y si ya entran en la tanda |
| `.sanciones aplicar` | La escalera a las que ya esperaron `ANTITRAMPA_TANDA_DEMORA_H` horas |
| `.sanciones aplicar ya` | La escalera a todas, sin esperar |
| `.sanciones perdonar <apodo\|usn\|cuenta>` | Descarta sus pendientes (falso positivo): no suman falta |

Con `ANTITRAMPA_SILENCIOSO = False` vuelve la expulsión al instante de siempre.

## 6. La escalera (las expulsiones, por cuenta)

| Falta | Qué pasa | Mensaje al jugador | Anuncio a los demás (`ANTITRAMPA_ANUNCIO_PUBLICO`) |
|---|---|---|---|
| 1.ª | Expulsado | «Fuiste expulsado por el antitrampa (`regla`).» | «`nick` ha sido detectado por usar trampas en el cliente.» |
| 2.ª | Expulsado con **advertencia** | «ADVERTENCIA: fuiste expulsado por el antitrampa (`regla`) por 2.ª vez. La próxima, tu cuenta queda baneada para siempre.» | igual |
| 3.ª (`ANTITRAMPA_BANEO_EN`) | **Baneo permanente** | «… Es la 3.ª vez: tu cuenta quedó BANEADA PERMANENTEMENTE.» | «`nick` ha sido baneado permanentemente por usar trampas en el cliente.» |

- **Con pases (`R2_LOGIN=pase`) + Coordinador (`R2_CUENTAS_URL` y `R2_CUENTAS_FICHA_INTERNA`):** el servidor del juego
  **no** suma faltas en su `datos.db` ni escribe `BANNED:` en `users.pass_hash`. Sólo detecta, expulsa de la partida y
  avisa al Coordinador (`POST /cuentas/interno/antitrampa`, timeout 3 s) con `{enenos_id, juego, regla, detalle, nick}`.
  La escalera la decide y guarda el **Coordinador** (`antitrampa_faltas` y `baneos` en `portero.db`, regida por
  `R2_ANTITRAMPA_BANEO_EN`): el baneo queda en un solo lugar, se ve en el panel del Coordinador con motivo y autor
  `antitrampa`, y desbanear desde ahí reinicia las faltas a 0. Si el Coordinador no contesta, el juego sólo expulsa
  (como 1.ª falta) y **nunca** banea localmente.
- **Sin pases (servidor local o cuentas viejas sin Eñeños ID):** las faltas se guardan en la base local (`antitrampa_faltas`)
  y en `ANTITRAMPA_BANEO_EN` se marca `BANNED:` en `users.pass_hash`, como antes (`ANTITRAMPA_BANEO_EN = 0` = nunca banea).
- **Una falta por sesión del juego** (de que se abre a que se cierra): con dos funciones prendidas llegan
  dos ganchos en el mismo segundo y cuentan como una.
- Sin bloqueo por tiempo: `ANTITRAMPA_BLOQUEO_S = 0` (con `600`, 10 min sin poder entrar, como antes).
  Lo que queda de esa sesión no cobra; al volver a abrir el juego limpio, sí.

## 7. Dónde quedan los datos

### 7.1 `datos/antitrampa.jsonl` — cada marca, una línea JSON

```json
{"cuando": "2026-11-19T04:15:30", "regla": "juego_automatico", "accion": "expulsar", "usn": 10,
 "nick": "papusts", "sala": null, "detalle": "gancho «automatico» en 0x005080B5: E9 46 81 B8 03 90 90 6A"}
```

| Campo | Tipo | Qué es |
|---|---|---|
| `cuando` | texto ISO (hora local del server) | cuándo |
| `regla` | texto | la regla (§ 4) |
| `accion` | texto | la acción que tenía la regla en ese momento (§ 5) |
| `usn` | entero | el personaje (`chars.uid`) |
| `nick` | texto | su apodo |
| `sala` | entero o null | la sala, si estaba en una |
| `detalle` | texto | explicación para un humano |
| `cancion`, `frame`, `combo`, `pd`, `star` | enteros | sólo en las reglas del cartel |
| `exe` | texto | sólo en `exe_desconocido` |

Ruta: `R2_ANTITRAMPA` (por defecto `datos/antitrampa.jsonl`). Sólo se agrega al final.

### 7.2 Tabla `antitrampa_faltas` (SQLite, `datos/datos.db`)

```sql
CREATE TABLE antitrampa_faltas (
    username TEXT PRIMARY KEY,          -- la cuenta (users.username)
    faltas INTEGER NOT NULL DEFAULT 0,  -- cuántas expulsiones lleva
    ultima_regla TEXT,                  -- por qué fue la última
    ultima TEXT);                       -- cuándo (hora local, 'YYYY-MM-DD HH:MM:SS')
```

### 7.2b Tabla `antitrampa_llegadas` (cuánto tarda cada canción)

```sql
CREATE TABLE antitrampa_llegadas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cancion INTEGER NOT NULL,           -- el id de la canción
    frame INTEGER NOT NULL,             -- en qué cuadro llegó (60 por segundo)
    cuando TEXT);                       -- hora local
```

Sólo entran las llegadas LIMPIAS (sin ninguna marca, carrera suelta, con meta y combo). Quedan las últimas
200 por canción. Para el panel: `SELECT cancion, COUNT(*), AVG(frame)/60.0 AS segundos FROM antitrampa_llegadas GROUP BY cancion`.

### 7.2c Tabla `antitrampa_pendientes` (modo silencioso, § 5b)

```sql
CREATE TABLE antitrampa_pendientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usn INTEGER NOT NULL,               -- el personaje
    cuenta TEXT,                        -- users.username (la escalera es por cuenta)
    nick TEXT,
    regla TEXT NOT NULL,
    detalle TEXT,
    cuando TEXT NOT NULL,               -- hora local de la detección
    estado TEXT NOT NULL DEFAULT 'pendiente',   -- pendiente | sancionada | perdonada
    resuelta TEXT,                      -- cuándo se aplicó la tanda o se perdonó
    quien TEXT);                        -- qué GM ('usn N')
```

La tanda también deja una línea `"accion": "sancion_en_tanda"` en `antitrampa.jsonl` con `faltas` y `baneada`.

### 7.3 El baneo: `users.pass_hash`

Una cuenta baneada tiene `BANNED:` delante de su `pass_hash` (la marca de siempre del servidor). Todo
login (juego, web, launcher) la rechaza.

## 8. Consultas para el panel

```sql
-- las cuentas con faltas, la peor primero
SELECT f.username, f.faltas, f.ultima_regla, f.ultima,
       u.pass_hash LIKE 'BANNED:%' AS baneada
FROM antitrampa_faltas f JOIN users u ON u.username = f.username
ORDER BY f.faltas DESC, f.ultima DESC;

-- PERDONAR una cuenta (sacarle las faltas y el baneo)
DELETE FROM antitrampa_faltas WHERE username = :cuenta;
UPDATE users SET pass_hash = substr(pass_hash, 8)
 WHERE username = :cuenta AND pass_hash LIKE 'BANNED:%';

-- banear a mano
UPDATE users SET pass_hash = 'BANNED:' || pass_hash
 WHERE username = :cuenta AND pass_hash NOT LIKE 'BANNED:%';
```

```sql
-- ★ modo silencioso: las detecciones que esperan la tanda, por cuenta
SELECT cuenta, COUNT(*) AS detecciones, GROUP_CONCAT(DISTINCT regla) AS reglas, MIN(cuando) AS desde
FROM antitrampa_pendientes WHERE estado = 'pendiente'
GROUP BY cuenta ORDER BY desde;
```

Para el historial, leer `antitrampa.jsonl` línea por línea (filtrar por `usn`, `regla`, `accion` o fecha).
`usn` → cuenta: `users.uid` (casillero 1) o `cuenta_personajes.uid` (casilleros 2–4).

⚠ La base tiene las contraseñas (hasheadas) de los jugadores: el panel tiene que ir detrás de un login de
GM y nunca mostrar `pass_hash`, sólo si empieza con `BANNED:`.

## 9. Ajustes (`ajustes.py`)

| Ajuste | Hoy | Qué es |
|---|---|---|
| `ANTITRAMPA` | `True` | prende o apaga todo |
| `ANTITRAMPA_REGLAS` | § 4 | la acción de cada regla |
| `ANTITRAMPA_SILENCIOSO` | `True` | ★ «expulsar» queda pendiente para la tanda (§ 5b); False = al instante |
| `ANTITRAMPA_TANDA_DEMORA_H` | `12` | horas que espera una detección antes de entrar en la tanda |
| `ANTITRAMPA_BANEO_EN` | `3` | en qué falta se banea (0 = nunca) |
| `ANTITRAMPA_BLOQUEO_S` | `0` | segundos sin poder entrar tras una expulsión |
| `ANTITRAMPA_ANUNCIO_PUBLICO` | `True` | el anuncio a todos (False = sólo a los GM) |
| `ANTITRAMPA_ANUNCIO` / `ANTITRAMPA_ANUNCIO_BANEO` | textos | `{nick}` = el apodo |
| `ANTITRAMPA_GANCHOS` | § 2.1 | dirección → nombre del gancho |
| `ANTITRAMPA_EXE_MD5` | 2 md5 | los R2Beat.exe aceptados |
| `ANTITRAMPA_FARMEO_SENALES` | `2` | señales distintas para «farmeo» |
| `ANTITRAMPA_LLEGADA_MUESTRAS` | `5` | llegadas limpias guardadas antes de juzgar «llegada_anticipada» |
| `ANTITRAMPA_LLEGADA_HISTORIA` | `30` | cuántas de las últimas se usan para la mediana |
| `ANTITRAMPA_LLEGADA_FACTOR` | `0.75` | debajo de este tanto de la mediana, marca |
| `ANTITRAMPA_LISTO_MUESTRAS` / `_LISTO_DESVIO_S` | `8` / `0.25` | listo automático |
| `ANTITRAMPA_SIN_HABLAR` | `40` | carreras sin chat |
| `ANTITRAMPA_MISMA_CANCION` | `15` | carreras con la misma canción |
| `ANTITRAMPA_CAMPANAS_SEGUIDAS` | `6` | rondas con campana |
| `ANTITRAMPA_COMBO_VECES` / `_COMBO_MINIMO` | `4` / `50` | combo repetido |
| `ANTITRAMPA_PRECISION_CARRERAS` / `_NIVELES` / `_RANGO` | `10` / `6` / `1` | precisión constante |
| `ANTITRAMPA_EXPULSIONES` / `_EXPULSIONES_S` | `5` / `600` | echar espectadores |
| `ANTITRAMPA_RELOJ_TOLERANCIA` / `_RELOJ_MARGEN_S` | `0.05` / `3.0` | reloj rápido |
| `ANTITRAMPA_LENTO_FACTOR` / `_LENTO_MARGEN_S` | `0.85` / `8.0` | reloj lento |
| `ANTITRAMPA_FF3D0_MIN` | `3` | animaciones tocadas |

En la dll (`d3d9_proxy.ini`, sección `[antitrampa]`): `activo` (1), `cerrar` (★ 0: no cierra), `pantalla` (1),
`pantalla_centro` (0).

## 10. ★ 26-nov · El registro central, la telemetría y el tablero

Hecho tras una auditoría completa (dll + servidor). Lo que cambió y por qué:

### 10.1 Un evento por detección (`antitrampa_eventos.py`)

Todas las reglas (dll, cartel, FF3D, farmeo, telemetría, correlación) pasan por `antitrampa.anotar`, que ahora deja un
**evento** en la tabla `antitrampa_eventos` (además del renglón de siempre en `antitrampa.jsonl`, con el mismo id):

| Campo | Qué es |
|---|---|
| `evento` | id único (hex de 32), el mismo en el jsonl |
| `usn`, `cuenta`, `nick` | el personaje, la cuenta (la escalera es por cuenta) y el apodo |
| `sesion`, `partida` | la corrida del juego (de «hola» a «hola») · `sala:corrida` (`room_id:game_magic`) |
| `cuando`, `ultimo` | la primera vez y la última vez que se vio |
| `categoria`, `regla`, `modulo`, `origen` | la categoría del tablero (§ 10.2), la regla, quién la vio (dll, cartel, ff3d, farmeo, telemetria, correlacion, servidor) y si lo **comprobó el server** o lo **declara la dll** |
| `descripcion`, `evidencia` | el texto y la evidencia (JSON: el renglón R2AT, lo medido) |
| `riesgo`, `confianza` | informativo · bajo · medio · alto · crítico, y 0-100 (`ANTITRAMPA_CLASIFICACION`) |
| `reincidencias`, `repeticiones` | eventos anteriores de esa regla en esa cuenta · la MISMA detección repetida en la misma sesión (no crea otra fila) |
| `version_cliente`, `version_antitrampa` | el md5 del exe · la versión del protocolo y el md5 (12) de la dll |
| `accion`, `pendiente` | lo que hizo el server · el `antitrampa_pendientes.id` si quedó para la tanda |
| `estado`, `revisado_por`, `revisado_cuando`, `nota` | nuevo · revisado · confirmado · descartado · sancionado |

⚡ El juego no espera: `registrar()` mete el evento en una cola y lo escribe un hilo aparte.
⛔ No se guarda la IP, la MAC ni nada personal que no haga falta.

Otras tablas: `antitrampa_acciones` (cada acción de un admin, con su nombre) y `antitrampa_suspensiones` (suspensión
con fecha de fin; el login y el lobby la rechazan mientras dure).

### 10.2 Categorías

Cheat Engine y herramientas de memoria · Auto play · Auto perfect · Bots · Macros · Speed hack · DLL no autorizadas ·
Alteraciones de memoria · Archivos protegidos · Integridad del antitrampa · Comportamiento anormal · Manipulación de
paquetes · Resultados imposibles · Interrupciones de la telemetría (`ANTITRAMPA_CATEGORIAS`, `ANTITRAMPA_CLASIFICACION`).

### 10.3 Reglas nuevas

| Regla | Acción | Qué |
|---|---|---|
| `manipulacion_correlacionada` | expulsar (→ tanda) | una herramienta (proceso, manija con escritura, depurador) **y** una alteración comprobada del juego en la misma sesión |
| `telemetria_interrumpida` | avisar | la dll dijo que late (`lat=`) y lleva `ANTITRAMPA_LATIDO_TOPE_S` sin latir con el juego conectado |
| `telemetria_inundada` | registrar | más de `ANTITRAMPA_R2AT_POR_MINUTO` renglones por minuto: los de más se descartan |
| `telemetria_repetida` | avisar | un renglón con una secuencia (`s=`) ya vista: se descarta |
| `reloj_cliente` | avisar | el reloj de la PC entre latidos (`t=`, al mandar) corrió ±15 % distinto que el del server, 2 veces seguidas |
| `antitrampa_apagado` | registrar | la dll avisa que la apagaron en su ini (antes callaba) |
| `vigia_parado` | avisar | el hilo del antitrampa dejó de correr (lo avisa el hilo del juego) |

### 10.4 Lo que se corrigió

- **El FF02 del lobby no validaba la sesión**: se podía entrar con el usn de otro, echarlo y mandar R2AT a su nombre.
  Ahora un usn entra al lobby sólo si hizo un FF01 válido (con su vcode) desde la misma IP en `LOBBY_EXIGE_LOGIN_H`.
- **Un «hola» fabricado lavaba la retención**: ya no, mientras la cuenta tenga detecciones pendientes.
- **Sólo se leía el primer R2AT de cada FF59** y los valores se cortaban en el espacio: ahora todos, enteros.
- **Inundación**: tope por minuto y por jugador; avisos a los GM con tope y una vez por regla y sesión.
- **Cheat Engine abierto = expulsión** → avisa; lo que sanciona es la correlación.
- **«farmeo» con dos señales débiles** (callado + teclado en pantalla) → hace falta al menos una fuerte.
- **La tanda perdía la falta** si el Coordinador no contestaba (y marcaba «sancionada»): ahora queda pendiente.
- **La tanda sancionaba con la 1.ª regla alfabética**: ahora con la más grave.
- **Un pendiente por cada «hola»**: ahora uno por cuenta y regla mientras espere la tanda.
- **El jsonl crecía sin fin**: rota a `.1` al pasar `ANTITRAMPA_JSONL_MAX_MB`. La memoria por jugador se olvida a las 6 h.
- **dll**: desborde de pila en `at_encolar` con nombres largos; la deduplicación por subcadena («a.dll» = «toolbit_a.dll»).

### 10.5 La telemetría de la dll (nuevo en `antitrampa.c`)

- Cada renglón lleva `s=<n>` (secuencia) y, al mandarse, `t=<GetTickCount>`.
- El «hola» dice `dll=<md5 de la dll, 12>` y `lat=60`.
- `R2AT latido=<n> perdidas=<renglones perdidos por cola llena> abiertas=<páginas abiertas>` cada 60 s.
- `R2AT vigia=parado` si el hilo del antitrampa se detiene; `R2AT apagado=1` con `[antitrampa] activo=0`.
- Compatible: una dll vieja (sin `lat=` ni `s=`) sigue funcionando y no se la marca por no latir.

### 10.6 El tablero (`tablero_antitrampa.py`)

```
R2_TABLERO_PUERTO=8765
R2_TABLERO_HOST=127.0.0.1                        # de fábrica sólo local: detrás de Caddy/túnel, nunca directo
R2_TABLERO_ADMINS="ana:una-clave-larga,beto:otra-clave-larga"   # 12+ caracteres
```

En vivo (cada 3 s): conectados y estado del antitrampa de cada uno (activo, sin antitrampa, callado, apagado, último
latido, reloj, renglones perdidos), detecciones nuevas, alertas críticas, filtros (jugador, categoría, riesgo, estado,
fechas), historial de cada cuenta, estadísticas, detalle con la evidencia y el registro de acciones. Acciones: revisar,
confirmar, falso positivo (perdona sus pendientes), advertir (texto genérico, sin detalles técnicos), suspender,
levantar, banear, desbanear. Seguridad: cookie HttpOnly + SameSite=Strict, token CSRF, tope de intentos de login por IP,
CSP con nonce, nada de `pass_hash` ni IPs, todo dato pintado como texto.

El panel del servidor de parches (`/admin`) lee la base: puede leer `antitrampa_eventos` directamente.

```sql
-- las alertas sin revisar
SELECT cuando, nick, cuenta, regla, riesgo, confianza, descripcion FROM antitrampa_eventos
WHERE estado = 'nuevo' AND riesgo IN ('alto', 'critico') ORDER BY id DESC LIMIT 50;
```

### 10.6b ★ 28-nov · Qué está usando: el catálogo de firmas (`antitrampa_firmas.py`)

Cada programa de trampas parchea siempre las mismas direcciones del exe. Con la dirección que informa la dll (`codigo=`, `gancho=`, `previo_va=`) el server dice **el programa y la función** («usa: R2AutoRouteLab2013 · Resultado personalizado») y elige la regla por la clase: `trampa` (lo que no es de Ñ2Hock) → su regla propia o `trampa_conocida`, `permitida` (Ñ2Hock) → `n2hock_permitido`, `arranque` → `arranque_restaurado` si ya está de fábrica. Lo que no está en el catálogo sigue siendo `codigo_modificado`.

Fuentes: el código de ToolBit / Ñ2Hock externo y R2AutoRouteLab2013 (también la versión «Release-next», cuyo perfil «SpaceWander» es nuestro exe y engancha el resultado en `+0x101451`; la dll lo vigila como `gancho=resultado_b`). Las direcciones se comprobaron byte por byte contra el R2Beat.exe del launcher.

⚠ La dll informa sólo la **primera** dirección distinta de cada página: si dos funciones caen en la misma página, el panel nombra la primera.

### 10.6c ★ 28-nov · «Está usando»

Cada evento guarda en su evidencia `usa` (una etiqueta corta: «Juego automático», «Auto farmeo», «Automático PD0 silencioso (R2AutoRouteLab2013)», «Programa abierto: cheatengine.exe», «Ñ2Hock: Sin piedra»…) y `usa_tipo`: `trampa` (rojo), `sospecha` (amarillo), `permitido` (verde, Ñ2Hock) o `info` (gris). La etiqueta sale de `antitrampa_firmas.usa_de` (del catálogo de firmas o, si no, de la regla); los eventos viejos se etiquetan al leerlos. La memoria ajena no se muestra (la tiene todo juego).

El tablero la muestra en una columna «Está usando» (alertas, tiempo real, detecciones), en «Conectados» (lo de la sesión) y en la ficha del jugador («Está usando:» con lo más grave primero; lo marcado como falso positivo no cuenta). `/api/eventos` y `/api/jugador` (`usando`) la devuelven para cualquier otro panel.

### 10.7 Límites (lo que esto NO resuelve)

- Todo lo que manda la dll lo **declara el cliente**: una dll recompilada puede mentir o callar. La secuencia y el
  latido sólo detectan a la que se calla o repite; por eso lo declarado nunca sanciona solo, y el tablero lo marca.
- No hay firma criptográfica de los renglones: el secreto viviría en el cliente. La identidad la da la sesión validada
  (FF01 + FF02 atados).
- No se miran la memoria escribible (puntaje, combo en el heap), los paks en disco ni drivers/macros por hardware.
- `reloj_cliente` necesita que la dll mande el latido; un speed hack que no toque GetTickCount no se ve ahí (el reloj
  del cartel, `reloj_rapido`, sigue).
