# importador2013 — las notas de las canciones

El cliente 2013 trae 800 y pico de canciones con su audio y su portada, pero **sin las flechas**:
en el juego original se las mandaba el servidor, una por canción (`FF57`). Este importador busca el
chart de cada canción en las fuentes que **vos** tengas y escribe `servidor/notes/<canción>.bin`
más el mapa `servidor/notes_map_2013.json`.

Ni los charts ni las fuentes vienen en este repositorio: son contenido del juego (ver
[AVISO-LEGAL.md](../../AVISO-LEGAL.md)).

## Configurar

```bash
copy herramientas\importador2013\config-ejemplo.json herramientas\importador2013\config.json
```

| clave | qué es | obligatoria |
|---|---|---|
| `cliente_2013` | la carpeta del juego 2013 (la de `R2Beat.exe`) | sí |
| `cbt_cliente` | la carpeta de un cliente **CBT 2011** instalado | sólo con `cbt_notes` |
| `cbt_notes` | una carpeta de charts `.bin` del CBT, uno por canción, con el número del CBT (`519.bin`). Es el formato que sirve el [servidor abierto del CBT](https://github.com/r2beatlatino/R2beat-CBT-2011) en su `datos/notas/` | no |
| `respaldo_charts` | una carpeta de charts **XML con `<AREA>`** (el formato de los clientes offline), con el mismo nombre de archivo que el `File` del `music_lt` | no |

Hace falta al menos una de las dos fuentes.

## Correr

```bash
python herramientas/importador2013/importar2013.py --scan                 # reporte, no escribe nada
python herramientas/importador2013/importar2013.py --apply --con-revisar  # escribe las notas y el mapa
python herramientas/importador2013/importar2013.py --verify               # relee las notas y comprueba
```

`--scan` deja `datos/importador2013/reporte.csv` con una fila por canción: de qué fuente salió el
chart, si el combo coincide y por qué se rechazó. Es lo que hay que mirar antes de aplicar.

## Cómo sabe que el chart es el de esa canción

Tres comprobaciones contra lo que el propio cliente 2013 dice de esa canción:

- el combo que la fórmula del exe saca del chart **=** el `Combo` del `music_lt`
- el último compás del chart **≈** el `<LENGTH>` de la canción
- el BPM del chart **=** el BPM de la canción

★ **El cruce con el CBT es por el `File`, nunca por el número.** De 811 canciones que coinciden,
sólo 7 tienen el mismo número en los dos clientes.

## ⛔ Dos cosas que matan al cliente sin aviso

- **Un chart de más de 4096 bytes.** El cliente lo copia a un buffer de 4096 sin mirar el largo y
  Windows lo cierra en el acto. El importador no escribe ninguno que se pase.
- **Una canción ofrecida sin chart.** Por eso el servidor arma la lista de canciones con
  `owned_songs` del mapa, y nunca con una lista escrita a mano.
