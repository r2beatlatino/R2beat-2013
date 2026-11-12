# R2Beat 2013 — servidor abierto

Un servidor para **R2Beat Latino 2013**, el juego de patinar y apretar flechas al ritmo de la música
de Softnyx. Armás tu propio servidor, apuntás el cliente a tu computadora y andás.

No hay nada que comprar, ni ítems, ni VIP, ni ventajas pagas. No las hay porque no las va a haber:
es la idea del proyecto, no una promesa de marketing.

```
                 tu PC                              la PC de un amigo
    ┌──────────────────────────┐                ┌──────────────────────┐
    │  correr_servidor.py      │ ◄────────────► │   R2Beat.exe 2013    │
    │  (esto, en Python)       │   red local    │   (abierto con       │
    └──────────────────────────┘   o internet   │    jugar.py)         │
                                                └──────────────────────┘
```

---

## Empezá por acá

Si nunca programaste, no importa: **[EMPEZAR.md](EMPEZAR.md)** es un paso a paso sin jerga, desde
cero hasta jugar.

El resumen, para el apurado:

```bash
python herramientas/extraer_datos.py    "C:\ruta\al\juego"
python herramientas/parchar_cliente.py  "C:\ruta\al\juego"  192.168.1.50
python correr_servidor.py
python jugar.py                          # en otra consola
```

No hay que instalar librerías: alcanza con **Python 3.10 o más nuevo**.

---

## De dónde bajar el cliente

Este repositorio es **sólo el servidor**. El cliente original no se distribuye acá: es de Softnyx y
de VALOFE. Para preservación, el instalador del 23-05-2013 está alojado en Internet Archive:

**[Softnyx R2Beat 23052013](https://archive.org/details/softnyx-r2beat23052013)**

⚠ **Tiene que ser ése.** `parchar_cliente.py` comprueba el `R2Beat.exe` byte por byte (md5
`b8f2517f…`) y, si es otro, no toca nada.

---

## Qué hay acá adentro

```
correr_servidor.py      ← esto es lo que se ejecuta
jugar.py                ← esto abre el juego (no abras R2Beat.exe a mano)

servidor/               el servidor, cortado por tema. ★ Empezá por servidor/MAPA.md:
                        dice qué archivo abrir para cada cosa.
  ajustes.py              todos los números y las banderas. Ningún otro archivo tiene constantes.
  despacho.py             la tabla «comando del cliente → función que lo atiende»
  lobby.py                la conexión y el arranque
  lobby_*.py              los manejadores, por tema (menú, salas, carrera, tienda, pareja…)
  notas.py                las flechas de cada canción (FF57)
  …                       ~55 módulos: círculos, gacha, misiones, medallas, cupones, campanas…
  tablas-cliente/         lo que el server lee del juego (lo llena extraer_datos.py) y lo nuestro
  notes/                  los charts de las canciones (los arma el importador)

herramientas/
  extraer_datos.py        saca del cliente las tablas que el servidor necesita
  parchar_cliente.py      apunta el cliente a tu servidor + le aplica la receta de arreglos
  receta_exe.py           la receta: 40 cambios chicos al R2Beat.exe, cada uno con su porqué
  pak.py                  lee los .pak del juego (sin r2pak.exe)
  importador2013/         arma las notas de las canciones desde las fuentes que tengas
  dll_d3d9/               el fuente de nuestra d3d9.dll y cómo se compila

exe/                      nuestra d3d9.dll ya compilada (va al lado de R2Beat.exe) y sus .ini
pruebas/                  las pruebas que corre GitHub en cada PR (también se corren a mano)
despliegue/               Docker para un VPS: prod (master) y prueba (develop)

datos/                    vacío al bajar. Acá va TU base de datos, el log y las sesiones.
```

---

## Lo que este repositorio NO trae

**El juego.** Ni el cliente, ni los `.pak`, ni la música, ni los gráficos, ni las notas de las
canciones. Nada de eso es nuestro. Ver [AVISO-LEGAL.md](AVISO-LEGAL.md).

**Las notas, en particular.** El cliente 2013 no las trae: se las pedía al servidor. Sin ellas el
servidor arranca, pero las salas no tienen canciones para correr. El importador las arma desde
las fuentes que tengas: [herramientas/importador2013/LEEME.md](herramientas/importador2013/LEEME.md).

**Lo de administración del servidor original:** el panel web, la API de la página, el launcher con
ruleta, los respaldos automáticos. Esto es el juego.

---

## Los GM

Un archivo `servidor/gm.txt`, una cuenta por renglón (el número de usuario, el login, o `@apodo`).
Se relee solo cuando cambia: no hace falta reiniciar. Al arrancar, el log dice cuántos GM hay —
si dice "VACÍA", ningún comando de GM va a andar.

`servidor/admin.txt` y `servidor/streamers.txt`, mismo formato: por ahora sirven para poder ponerle
clave a una sala.

Los tres están en `.gitignore`: son nombres de cuentas de tu gente.

---

## Estado

Anda y se juega: es el mismo servidor del proyecto R2Beat Latino 2013, sin la parte de
administración. Crear cuenta y personaje (hasta 4 por cuenta), el menú, los canales por licencia,
salas, chat, susurros, amigos, pareja, círculos, la tienda y el armario, el gacha, misiones,
medallas, la carrera de hasta 12 con relevo y equipos, el espectador, las campanas, los cupones…

Hay cosas a medio hacer y errores conocidos; están anotados como comentarios en el código, ahí
donde importan. Los comentarios son la bitácora del proyecto: largos, con fechas y con lo que se
midió. Se dejaron a propósito.

★ Algunas cosas necesitan además nuestra `d3d9.dll` (la herramienta en el juego, la sala de 12 por
la interfaz, varios efectos): está en [`exe/`](exe/LEEME.md), con su fuente en
`herramientas/dll_d3d9/`. Sin ella el servidor anda igual y esas partes simplemente no se ven.

---

## Para ayudar

Las ramas: **`develop`** (por defecto, ahí van los PR) y **`master`** (lo estable, lo fusiona el
dueño). Cómo mandar un arreglo: [CONTRIBUIR.md](CONTRIBUIR.md).

---

## Licencia

**AGPL-3.0.** En criollo: hacé lo que quieras con esto, pero si levantás un servidor con él, tus
jugadores tienen derecho a ver tu versión del código, con tus cambios incluidos. No se puede tomar
esto, mejorarlo y quedarse con las mejoras.

Ver [LICENSE](LICENSE).
