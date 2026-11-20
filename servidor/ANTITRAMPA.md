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

**El cierre del juego.** Si la revisión 3 encuentra un gancho, la dll manda el aviso, espera a que salga
(hasta 10 s), muestra el cartel «Ñ2-AntiCheat» y **cierra el juego** (a los 20 s como mucho, aunque
nadie toque el cartel). `[antitrampa] cerrar=0` en `d3d9_proxy.ini` lo apaga.

**La pantalla de prevención.** Al abrir el juego la dll muestra «Ñ2-AntiCheat · Verificando el juego… N %»
abajo a la derecha (`antitrampa_pantalla.bmp` junto a la dll; `pantalla_centro=1` la centra,
`pantalla=0` la apaga).

### 2.1 Ganchos conocidos (medidos en el juego con Ñ2Hock, 19-nov-2026)

| Nombre (`gancho=`) | Dirección | Bytes originales | Qué función lo pone | Regla |
|---|---|---|---|---|
| `automatico` | `0x005080B5` (R2Beat.exe+0x1080B5) | `6A 00 8D 44 24` | «Juego automático» (con Azar / Precisión) | `juego_automatico` |
| `sala` | `0x005AEDD4` (+0x1AEDD4) | `8B 0D D4 14 93 00` | «Auto Listo / Inicio», «Anfitrión: al azar», «Misma canción» | `sala_automatica` |
| `relevo` | `0x00505340` (+0x105340) | (el gancho de relevo de nuestra dll) | «Auto Relevo» — con nuestra dll Ñ2Hock no lo puede poner | `relevo_automatico` |

Con la casilla desmarcada los bytes vuelven a los originales: **usar Ñ2Hock sin sus funciones
automáticas no se detecta como trampa**. Una dll vieja (sin `gancho=`) los manda como `codigo=` con esa
misma dirección, y el server los reconoce igual (`ANTITRAMPA_GANCHOS` en `ajustes.py`).

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
| `modulo_prohibido` | expulsar | dll | Tiene cargado un módulo de trampas (ToolBit, R2Mods, Cheat Engine…) |
| `proceso_prohibido` | expulsar | dll | Tiene abierto un programa de trampas |
| `farmeo` | expulsar | farmeo | Dos o más señales de farmeo distintas en la misma sesión (`ANTITRAMPA_FARMEO_SENALES`) |
| `combo_imposible` | retener | cartel | Más combo que notas tiene la canción |
| `porcentaje_imposible` | retener | cartel | PD o estrellas por encima de 100 |
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
| `expulsar` | Lo anterior + **la escalera** (§ 6): mensaje al jugador, anuncio público, se corta la conexión |

## 6. La escalera (las expulsiones, por cuenta)

| Falta | Qué pasa | Mensaje al jugador | Anuncio a los demás (`ANTITRAMPA_ANUNCIO_PUBLICO`) |
|---|---|---|---|
| 1.ª | Expulsado | «Fuiste expulsado por el antitrampa (`regla`).» | «`nick` ha sido detectado por usar trampas en el cliente.» |
| 2.ª | Expulsado con **advertencia** | «ADVERTENCIA: fuiste expulsado por el antitrampa (`regla`) por 2.ª vez. La próxima, tu cuenta queda baneada para siempre.» | igual |
| 3.ª (`ANTITRAMPA_BANEO_EN`) | **Baneo permanente** | «… Es la 3.ª vez: tu cuenta quedó BANEADA PERMANENTEMENTE.» | «`nick` ha sido baneado permanentemente por usar trampas en el cliente.» |

- Las faltas son de la **cuenta** (no del personaje: crear otro no las limpia) y se guardan en la base.
- **Una falta por sesión del juego** (de que se abre a que se cierra): con dos funciones prendidas llegan
  dos ganchos en el mismo segundo y cuentan como una.
- Sin bloqueo por tiempo: `ANTITRAMPA_BLOQUEO_S = 0` (con `600`, 10 min sin poder entrar, como antes).
  Lo que queda de esa sesión no cobra; al volver a abrir el juego limpio, sí.
- `ANTITRAMPA_BANEO_EN = 0` = nunca banea.

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

Para el historial, leer `antitrampa.jsonl` línea por línea (filtrar por `usn`, `regla`, `accion` o fecha).
`usn` → cuenta: `users.uid` (casillero 1) o `cuenta_personajes.uid` (casilleros 2–4).

⚠ La base tiene las contraseñas (hasheadas) de los jugadores: el panel tiene que ir detrás de un login de
GM y nunca mostrar `pass_hash`, sólo si empieza con `BANNED:`.

## 9. Ajustes (`ajustes.py`)

| Ajuste | Hoy | Qué es |
|---|---|---|
| `ANTITRAMPA` | `True` | prende o apaga todo |
| `ANTITRAMPA_REGLAS` | § 4 | la acción de cada regla |
| `ANTITRAMPA_BANEO_EN` | `3` | en qué falta se banea (0 = nunca) |
| `ANTITRAMPA_BLOQUEO_S` | `0` | segundos sin poder entrar tras una expulsión |
| `ANTITRAMPA_ANUNCIO_PUBLICO` | `True` | el anuncio a todos (False = sólo a los GM) |
| `ANTITRAMPA_ANUNCIO` / `ANTITRAMPA_ANUNCIO_BANEO` | textos | `{nick}` = el apodo |
| `ANTITRAMPA_GANCHOS` | § 2.1 | dirección → nombre del gancho |
| `ANTITRAMPA_EXE_MD5` | 2 md5 | los R2Beat.exe aceptados |
| `ANTITRAMPA_FARMEO_SENALES` | `2` | señales distintas para «farmeo» |
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

En la dll (`d3d9_proxy.ini`, sección `[antitrampa]`): `activo` (1), `cerrar` (1), `pantalla` (1),
`pantalla_centro` (0).
