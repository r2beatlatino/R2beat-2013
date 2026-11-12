# `servidor/notes/` — las flechas de cada canción

Viene **vacía a propósito**. Acá va un `.bin` por canción (el chart que el servidor le manda al
juego cuando empieza la carrera) y, al lado, en `servidor/notes_map_2013.json`, qué chart le toca a
cada canción.

El cliente 2013 **no trae** las notas: en el juego original las servía el servidor. Y no las
podemos repartir acá: son de Softnyx (ver [AVISO-LEGAL.md](../../AVISO-LEGAL.md)).

Se arman con el importador: [herramientas/importador2013/LEEME.md](../../herramientas/importador2013/LEEME.md).

**Sin notas el servidor arranca igual**, pero la lista de canciones de las salas sale vacía: no
hay con qué correr. Es a propósito: ofrecer una canción sin chart cierra el juego del jugador.
