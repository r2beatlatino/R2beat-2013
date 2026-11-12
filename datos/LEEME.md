# La carpeta `datos/`

Viene **vacía a propósito**. Acá escribe el servidor todo lo que es **tuyo**, de tu instalación:

| archivo | qué es |
|---|---|
| `datos.db` | la base: cuentas, personajes, inventario, amigos, círculos… **Es lo único irreemplazable de tu servidor.** Hacele copias (con el servidor apagado, o con `sqlite3 datos.db ".backup copia.db"`: copiar el archivo con el servidor prendido puede dejar una copia rota). |
| `sesiones.json` | las sesiones abiertas |
| `servidor.log` | el log. El de la corrida anterior queda al lado, con la fecha |
| `status.json` | quién está online, cada 3 segundos |
| `juego.json` | dónde está tu juego (lo escribe `extraer_datos.py`) |
| `importador2013/` | la carpeta de trabajo del importador de notas |

⛔ **`datos.db` tiene las contraseñas de tu gente** (hasheadas, pero igual). No la subas nunca a
ningún lado. Todo `datos/` está en `.gitignore`.
