# `servidor/tablas-cliente/` — lo que el servidor lee del juego

Hay dos clases de archivo acá:

| | qué | de dónde |
|---|---|---|
| `*.txt`, `*.xml` | tablas **del juego**: caras, alas, anillos, medallas, mascotas, misiones del día, la lista de canciones… | las saca `herramientas/extraer_datos.py` de **tu** `rnr_script.pak`. No vienen en el repositorio: son de Softnyx |
| `*.json` | tablas **nuestras**: qué ítem lleva aura, cuáles flotan, las monturas, las duraciones medidas de las animaciones de tropezar, cuántos efectos tiene cada canción | vienen en el repositorio |

★ Las del juego se copian **byte por byte**. El servidor las lee igual que el cliente: si cambiás
una a mano, cambiala también en el `.pak`, o el juego y el servidor van a pensar cosas distintas.

`shop_lt.txt` (la tienda) no está acá sino un nivel más arriba, en `servidor/shop_lt.txt`.
