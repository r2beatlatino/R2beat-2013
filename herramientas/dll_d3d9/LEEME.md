# `dll_d3d9/` — el fuente de nuestra `d3d9.dll`

- `fuente/d3d9_proxy.c` es la entrada: incluye a todos los demás `.c` (es una sola unidad de
  compilación). Cada `.c` arranca con un comentario que dice qué arregla y dónde se midió.
- Los `*_datos.h` son tablas generadas por herramientas (no se editan a mano).
- `compilar.py` la arma con Zig 0.16.0 y dice si da igual a la de `exe/`.

La dll compilada y qué hace cada `.ini`: [`exe/LEEME.md`](../../exe/LEEME.md).

## El antitrampa del cliente (`antitrampa.c`)

- `antitrampa_envoltura.h` va **antes** que cualquier módulo: cambia `VirtualProtect` y `VirtualAlloc` por envolturas
  que anotan lo que escribe la dll en el exe. Un módulo nuevo que parchee con `VirtualProtect` no tiene que hacer nada.
  ⚠ Uno que escriba el exe por otro camino (sin `VirtualProtect`) va a salir como «código tocado por fuera».
- Copia el exe al cargarse (antes del primer parche), lo compara con el del disco y, cada 5 s, cada página contra su
  copia. Busca también módulos de trampas, memoria ejecutable ajena, un depurador, hilos que arrancan en memoria
  inyectada, procesos de trampas abiertos (Cheat Engine, ToolBit, aceleradores…) y teclas inyectadas por un programa
  (un gancho de teclado `WH_KEYBOARD_LL`, sólo con el juego delante).
- Al abrir el juego muestra la pantalla «Sistema de Prevención de Hackeo» (la imagen, «Verificando el juego… N %» y una barra de colores) hasta que aparece la ventana
  del juego. `[antitrampa] pantalla=0` la apaga; `imagen=` un BMP junto a la dll (de fábrica `antitrampa_pantalla.bmp`;
  sin él se dibuja una propia); `pantalla_min` / `pantalla_max` en ms (3000 / 8000).
  Sale abajo a la derecha, encima de la barra de tareas; `pantalla_centro=1` la pone en el medio.
- Informa por el `FF59` con renglones `R2AT …`; el server los juzga en `servidor/antitrampa.py`.
- `[antitrampa] activo=0` en `d3d9_proxy.ini` lo apaga (el server lo nota: no llega el «hola»).
- Prueba sin el juego (Windows, Zig o llvm-mingw): `python herramientas/dll_d3d9/probar_antitrampa.py`.

## Cómo llega tu dll al server de prueba (sola, como EDA)

1. Cambiás el fuente y, **en el mismo PR**, va la `exe/d3d9.dll` recompilada con `compilar.py` (Zig **0.16.0**).
2. GitHub la vuelve a compilar desde el fuente (la prueba `dll`) y tiene que dar **exacto** la `exe/d3d9.dll` del
   PR, byte a byte. Si no da igual, la prueba sale en rojo: o el fuente cambió y la dll no, o la dll no salió de ese
   fuente. ⚠ Tiene que ser Zig 0.16.0: otra versión compila, pero da otros bytes.
3. Cuando se fusiona a `develop`, en unos 5 minutos el server de prueba arma una lista nueva del cliente que cambia
   **sólo la dll** (la de `exe/`, y sólo si la prueba `dll` de ese commit está en verde en GitHub). El launcher,
   con «Servidor de prueba» marcado, la baja al tocar JUGAR. Prod no se toca: prod sale de `master`.
4. Si algo salió mal: en el launcher, «Subir archivos» → volver a una versión anterior de la lista de prueba
   (se guardan la actual y 5 más). O un PR que lo arregle.

★ **La dll de prod** sale del MISMO fuente con `compilar.py --prod` (`-DR2_SIN_TEMPORADA`): igual a la de
prueba, pero sin la isla de temporada (`isla_hora.c` e `isla_fx.c` no enganchan nada). Así prod muestra la isla de
siempre aunque en la carpeta del jugador queden archivos de la Navidad del server de prueba (el launcher no borra lo
que sobra). La `exe/d3d9.dll` del repo sigue siendo la de prueba.

⚠ Lo que se fusiona en `develop` llega a la PC de todos los que juegan en el server de prueba. La prueba `dll`
asegura que es el fuente que se ve en el PR; lo que hace ese fuente lo tiene que mirar quien fusiona.
