# Empezar de cero

Esta guía es para alguien que **nunca programó**. No hay que saber nada: se copian y pegan unos
comandos.

Al final vas a tener el juego andando contra tu propia computadora.

---

## Lo que necesitás tener antes

**1. El juego instalado.** Este repositorio no lo trae (no es nuestro). El instalador del
23-05-2013 está preservado en Internet Archive:
[Softnyx R2Beat 23052013](https://archive.org/details/softnyx-r2beat23052013).
Instalalo y anotá en qué carpeta quedó (la que tiene `R2Beat.exe`).

> ⚠ Tiene que ser **ese** instalador. La preparación del paso 2 comprueba el ejecutable byte por
> byte y no toca uno que no conoce.

**2. Python.** Bajalo de [python.org/downloads](https://www.python.org/downloads/) e instalalo.

> ⚠ En Windows, cuando el instalador te pregunte, **marcá la casilla "Add Python to PATH"**. Si no
> la marcás, los comandos de abajo no van a andar.

No hace falta nada más: ni `r2pak.exe`, ni librerías.

---

## Paso 0 — Abrir una consola en la carpeta correcta

- **Windows:** abrí la carpeta de este proyecto en el Explorador. Hacé clic en la barra de
  dirección de arriba, escribí `cmd` y apretá Enter.

Para comprobar que Python quedó bien:

```bash
python --version
```

Tiene que responder algo como `Python 3.12.1`.

---

## Paso 1 — Sacar los datos del juego

El servidor necesita saber qué hay en la tienda, qué caras, alas y anillos existen y cuáles son las
canciones. Todo eso está adentro del juego que ya tenés:

```bash
python herramientas/extraer_datos.py "C:\Juegos\R2Beat"
```

Cambiá la ruta por la tuya. **Las comillas hacen falta** si tiene espacios. Si salió bien, vas a
ver una lista de `[ok]`, una por tabla.

---

## Paso 2 — Preparar el juego

**Primero averiguá la dirección de tu computadora en tu red:** en una consola escribí `ipconfig` y
buscá "Dirección IPv4". Es algo como `192.168.1.50`. Después:

```bash
python herramientas/parchar_cliente.py "C:\Juegos\R2Beat" 192.168.1.50
```

Le aplica al `R2Beat.exe` los mismos 40 arreglos con los que se juega en el proyecto. Los dos que
más se notan:

- **color de 32 bits** en vez de 16: el juego pedía 16, que Windows moderno emula lentísimo. Con
  esto **no hace falta** el modo de compatibilidad de Windows XP ni ejecutar como administrador;
- el arreglo de las **placas de video viejas**, que se caían al entrar al lobby.

Es todo o nada: si algo no coincide, no escribe nada y te avisa. Antes de tocar deja una copia
intacta (`R2Beat.exe.original`). Para ver cómo está, o volver atrás:

```bash
python herramientas/parchar_cliente.py "C:\Juegos\R2Beat" --ver
python herramientas/parchar_cliente.py "C:\Juegos\R2Beat" --restaurar
```

> ⚠ **No pongas `127.0.0.1`**, aunque el servidor vaya a correr en la misma computadora que el
> juego. Usá siempre la IP de tu red.

---

## Paso 3 — Las notas de las canciones

El cliente 2013 **no trae las flechas** de las canciones: en el juego original las mandaba el
servidor. Sin ellas el servidor arranca, pero no hay canciones con qué correr.

Se arman con el importador, desde las fuentes de charts que tengas:
[herramientas/importador2013/LEEME.md](herramientas/importador2013/LEEME.md).

---

## Paso 4 — Prender el servidor

```bash
python correr_servidor.py
```

Vas a ver el arranque, con líneas como:

```
[MAIN ] catalogo tienda: 10978 items
[MAIN ] picker de música: 805 canciones con chart
[MAIN ] LoginServer :48004  +  10 CANALES
[MAIN ] listo. Para entrar: python jugar.py
```

**Dejá esa ventana abierta.** Mientras esté abierta, el servidor está prendido. Para apagarlo,
`Ctrl+C` ahí adentro.

---

## Paso 5 — Entrar al juego

En **otra** consola (dejá la del servidor abierta):

```bash
python jugar.py
```

Se abre una ventanita. La primera vez:

1. Poné la IP de tu servidor (la del paso 2).
2. Apretá **«Carpeta del juego…»** y elegí la carpeta de `R2Beat.exe` (si corriste el paso 1, ya
   la sabe).
3. Escribí un usuario y una contraseña y apretá **«Crear cuenta»**.
4. Apretá **«Entrar»**. El juego te va a pedir crear tu personaje.

> ⚠ **No abras `R2Beat.exe` directamente.** El juego no tiene pantalla de login propia: espera que
> alguien lo abra ya autenticado. Eso es lo que hace `jugar.py`.

---

## Hacerte GM

Creá el archivo `servidor/gm.txt` con tu usuario adentro (uno por renglón). No hace falta
reiniciar: se relee solo.

---

## Si algo no anda

**El juego abre pero se queda cargando para siempre.**
No llega al servidor. Revisá, en este orden:

1. ¿La ventana del servidor sigue abierta?
2. ¿La IP es la correcta? Volvé a correr `ipconfig`: en muchas redes la IP cambia sola.
3. El firewall de Windows. La primera vez suele preguntar si permitís que Python use la red: hay
   que decir que sí.

**"python no se reconoce como un comando".**
Python no está instalado, o te faltó marcar "Add Python to PATH". Reinstalalo marcando esa casilla.

**`parchar_cliente.py` dice que el exe "no es el que esta receta conoce".**
Tu `R2Beat.exe` no es el del instalador del 23-05-2013 (o ya lo tocó otra herramienta). Reinstalá
desde ese instalador.

**El servidor dice `falta servidor/shop_lt.txt`.**
Te falta el paso 1.

**En las salas no aparece ninguna canción.**
Te falta el paso 3.

**"Address already in use".**
Ya hay un servidor corriendo. Cerrá la otra ventana.

**Quiero que entren amigos por internet, no sólo por mi red.**
Hay que abrir en el router el puerto **48004** y los de los canales (48005, 48015, 48025… hasta
48095), y usar tu IP de internet. Para dejarlo prendido las 24 horas conviene un servidor
alquilado con Linux: el servidor corre igual ahí.
