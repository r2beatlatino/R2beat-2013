# `dll_d3d9/` — el fuente de nuestra `d3d9.dll`

- `fuente/d3d9_proxy.c` es la entrada: incluye a todos los demás `.c` (es una sola unidad de
  compilación). Cada `.c` arranca con un comentario que dice qué arregla y dónde se midió.
- Los `*_datos.h` son tablas generadas por herramientas (no se editan a mano).
- `compilar.py` la arma con Zig 0.16.0 y dice si da igual a la de `exe/`.

La dll compilada y qué hace cada `.ini`: [`exe/LEEME.md`](../../exe/LEEME.md).

⚠ Si cambiás el fuente, en el mismo PR va la `exe/d3d9.dll` recompilada con `compilar.py` (las
pruebas de GitHub no tienen Zig ni el juego: no la pueden armar ni probar).
