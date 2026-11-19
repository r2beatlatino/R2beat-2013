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
- Al abrir el juego muestra la pantalla «Sistema de Prevención de Hackeo» (la imagen y «Cargando juego… N %») hasta que aparece la ventana
  del juego. `[antitrampa] pantalla=0` la apaga; `imagen=` un BMP junto a la dll (de fábrica `antitrampa_pantalla.bmp`;
  sin él se dibuja una propia); `pantalla_min` / `pantalla_max` en ms (3000 / 8000).
  Sale abajo a la derecha, encima de la barra de tareas; `pantalla_centro=1` la pone en el medio.
- Informa por el `FF59` con renglones `R2AT …`; el server los juzga en `servidor/antitrampa.py`.
- `[antitrampa] activo=0` en `d3d9_proxy.ini` lo apaga (el server lo nota: no llega el «hola»).
- Prueba sin el juego (Windows, Zig o llvm-mingw): `python herramientas/dll_d3d9/probar_antitrampa.py`.

⚠ Si cambiás el fuente, en el mismo PR va la `exe/d3d9.dll` recompilada con `compilar.py` (las
pruebas de GitHub no tienen Zig ni el juego: no la pueden armar ni probar).
