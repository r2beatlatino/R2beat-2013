# R2Beat 2013 — servidor abierto

Servidor para **R2Beat Latino 2013**, el juego de ritmo de Softnyx, escrito desde cero en Python.
El servicio oficial cerró; esto permite volver a jugarlo en tu propia computadora o en un servidor.

Es el hermano del [servidor abierto del CBT 2011](https://github.com/r2beatlatino/R2beat-CBT-2011),
para el cliente de 2013.

- **Guía completa:** [LEEME.md](LEEME.md)
- **Paso a paso desde cero:** [EMPEZAR.md](EMPEZAR.md)
- **Qué archivo del servidor abrir para cada cosa:** [servidor/MAPA.md](servidor/MAPA.md)
- **Para ayudar (ramas, PR, pruebas):** [CONTRIBUIR.md](CONTRIBUIR.md)
- **En un VPS, con Docker:** [despliegue/LEEME.md](despliegue/LEEME.md)
- **Aviso legal:** [AVISO-LEGAL.md](AVISO-LEGAL.md)
- **Licencia:** [AGPL-3.0](LICENSE)

## El cliente no está acá

Este repositorio contiene **sólo el servidor**. El cliente, los `.pak`, la música, los gráficos y
las notas de las canciones son de Softnyx/VALOFE y no se distribuyen acá.

Para preservación, el instalador del cliente 2013 está en Internet Archive:

**[Softnyx R2Beat 23052013](https://archive.org/details/softnyx-r2beat23052013)**

Es un `.exe` de unos 1,5 GB. Descargalo, instalá el juego y después seguí [EMPEZAR.md](EMPEZAR.md).
El enlace es externo y puede dejar de estar disponible.

## Resumen rápido

```bash
python herramientas/extraer_datos.py   "C:\ruta\al\juego"
python herramientas/parchar_cliente.py "C:\ruta\al\juego" 192.168.1.50
python correr_servidor.py
python jugar.py
```

Requiere **Python 3.10 o más nuevo**. El servidor no necesita dependencias externas: alcanza con lo
que trae Python.
