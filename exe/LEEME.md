# `exe/` — nuestra `d3d9.dll`

Lo único binario del repo, y es **nuestro**: el fuente está en
[`herramientas/dll_d3d9/fuente/`](../herramientas/dll_d3d9/fuente/) y se compila con
[`herramientas/dll_d3d9/compilar.py`](../herramientas/dll_d3d9/compilar.py) (da exactamente este archivo).

Se pone **al lado de `R2Beat.exe`**. Windows la carga antes que el D3D9 del sistema, y se mete en el
medio sin tocar un byte del juego: más cuadros por segundo y un bucle que duerme menos (el juego se
siente más fluido), MSAA, alt+enter, y los arreglos de pantalla del server (carteles de la sala de 12,
picker, estilos de texto…). Para sacarla, se borra.

| archivo | qué es |
|---|---|
| `d3d9.dll` | la dll compilada |
| `d3d9_proxy.ini` | su configuración (video, motor, métricas). Va al lado de la dll |
| `d3d9_caras.ini` | las caras por sexo (sólo sirve si tu cliente tiene esas carpetas de caras) |

⚠ Algunas partes de la dll dibujan cosas que sólo existen en un cliente con contenido agregado (caras,
monturas, auras). En un cliente de fábrica esas partes no encuentran nada y no hacen nada; lo demás anda.
