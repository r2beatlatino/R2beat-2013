# -*- coding: utf-8 -*-
"""gacha — las máquinas de cápsulas: qué premios tiene cada una y cuál sale.

★★★★★ DE DÓNDE SALE TODO ESTO: **de una tabla del CLIENTE**, `gacha_machine.txt`
  (`rnr_script/`), copiada a `documentacion/tablas-cliente/`. **No se inventó nada acá**: las 52
  máquinas, los 267 premios y sus probabilidades ya venían escritos en el juego. Lo único que hace
  este módulo es leerlos y tirar el dado.

  ⚠ Y ES LA MISMA TABLA QUE USA EL CLIENTE PARA DIBUJAR. La máquina en pantalla muestra los
    premios que están acá; si el server sorteara de otra lista, el jugador vería seis cosas y
    ganaría una séptima que no está en la vitrina.

──────────────────────────────────────────────────────────────────────────────────────────────
LO QUE SE MIDIÓ ANTES DE ESCRIBIR (2026-09-08) — cada número está contado, no supuesto
──────────────────────────────────────────────────────────────────────────────────────────────

★ **`Chance` es una rifa de 10.000 boletos.** 13 de las 52 máquinas lo traen, y en **las 13 la
  suma da exactamente 10000**. Por eso se lee como "diezmilésimos" y no como un número suelto.
  Las otras 39 (la ropa) no lo traen: ahí el reparto es **parejo**, que es lo único que la tabla
  banca. Ponerle porcentajes nosotros sería inventar.

★ **El campo `Type` marca "esto NO es una prenda".** Se cruzó premio por premio contra el
  catálogo real de la tienda (`shop_lt.txt`, 2.866 ítems):

      · 178 premios SIN `Type`  ->  los 178 están en el catálogo   (son ítems)
      · 51 premios CON `Type`   ->  NINGUNO está en el catálogo    (son monedas/EXP)

  Cero excepciones en los dos sentidos. **Ese cruce es la razón** por la que acá se decide qué
  entregar mirando el `Type` y no el nombre del premio.

★ **`Type` viene `MONEDA|CLASE`** y lo que importa es la CLASE:
      NORMAL / (sin Type) = un ítem     ·  MONEY = RCoin     ·  EXP = experiencia
      SEED = semillas                   ·  CHARGACHA = ⛔ ver abajo

⛔ **`CHARGACHA` NO SE PUEDE ENTREGAR, y esto está medido, no supuesto.** Son personajes
  (`139026` "Observador(H)", `119203` "Eros", `119261` "R2 Chico rojo"…). Se buscó cada uno de
  esos ids en TODAS las tablas del cliente y **aparecen sólo en `gacha_machine.txt`**. El control
  que lo prueba: un premio normal como el `130026` figura en **cinco** (`shop_lt.txt`, `shop.bin`,
  `hero.txt`, `spec.txt` y la del gacha). O sea que el cliente **no tiene ficha** de los
  CHARGACHA: darlos sería mandarle un ítem que no sabe dibujar.
  ⇒ Las 4 máquinas que los contienen se rechazan enteras. Ver `MAQUINAS_INCOMPLETAS`.

  ⚠⚠ Y NO se resuelve "sorteando sólo los premios que sí sabemos dar": eso **cambia las
     probabilidades en silencio** y el jugador nunca se entera de que le sacamos algo del bombo.
     Un rechazo honesto es peor experiencia y mejor trato.

★ **SEED se paga en RCoin.** Decisión de anonimo03, 2026-09-08: *"el seed no importa, toda nuestra
  tienda vale rcoin"*. El `Value` del premio se acredita tal cual en RCoin (600 SEED -> 600
  RCoin). Es una decisión de ECONOMÍA nuestra, no algo que diga la tabla: queda escrita acá para
  que dentro de seis meses no parezca un descuido. Sin ella, dos máquinas más quedaban muertas.
"""
import os
import random
import re
import threading

from . import shop_catalog

from .ajustes import GACHA_FAMILIAS_QUE_SOBREVIVEN
from .ajustes import GACHA_PJ_CON_ROPA
from .ajustes import GACHA_SIN_REPETIDOS as SIN_REPETIDOS
from .registro import log

# La tabla del cliente, copiada al repo igual que `wing.txt` y `face.txt`.
# ★ Vive en `servidor/tablas-cliente/` desde el 2026-09-16. Antes estaba en `documentacion/`, que
#   es el lugar equivocado: esto NO es documentación, se lee **en caliente** durante una partida —
#   y de esa misma carpeta salen además `hero.txt` y `spec.txt`, por el `dirname(TABLA)` de abajo.
#   ⛔ Con la red del orden de deploy: prod todavía la tiene en `documentacion/tablas-cliente/`.
#     Sin la tabla, el gacha entrega cualquier cosa o nada. Se va cuando prod esté migrado.
_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ_P = os.path.dirname(_AQUI)
TABLA = os.environ.get("R2_GACHA_TABLA") or next(
    (p for p in (os.path.join(_AQUI, "tablas-cliente", "gacha_machine.txt"),
                 os.path.join(_RAIZ_P, "documentacion", "tablas-cliente", "gacha_machine.txt"),
                 os.path.join(_RAIZ_P, "tablas-cliente", "gacha_machine.txt"))
     if os.path.isfile(p)), os.path.join(_AQUI, "tablas-cliente", "gacha_machine.txt"))

BOLETOS_POR_MAQUINA = 10000        # medido: las 13 máquinas con `Chance` suman esto exacto

# Las clases de premio que sabemos entregar. `None` = el premio no traía `Type` (es un ítem).
CLASE_ITEM = "NORMAL"
CLASES_QUE_SABEMOS = {None, "NORMAL", "MONEY", "EXP", "SEED"}

MAQUINAS = {}                      # capsula -> [premio, ...]
MAQUINAS_INCOMPLETAS = {}          # capsula -> {clases que no sabemos dar}
_lock = threading.RLock()


def _clase(tipo):
    """`'RCOIN|MONEY'` -> `'MONEY'`. `None` si el premio no traía `Type` (o sea: es un ítem)."""
    if not tipo:
        return None
    return tipo.split("|")[-1].strip().upper() or None


def cargar(path=None, verbose=False):
    """Parsea `gacha_machine.txt` -> `MAQUINAS`. Idempotente: se puede llamar de nuevo.

    ⚠ La tabla es XML del juego, en `euc-kr` declarado pero con los nombres ya traducidos al
      español en bytes de una sola letra. Se lee como `cp1252` a propósito: con `euc-kr` los
      acentos de "Profecía" o "Demonio Rojo" revientan el decodificador. Los nombres son sólo para
      el log —lo que decide es el `index`—, así que un acento mal leído no cambia ningún premio.
    """
    p = path or TABLA
    with _lock:
        MAQUINAS.clear()
        MAQUINAS_INCOMPLETAS.clear()
        if not os.path.exists(p):
            log("SHOP", f"  ⚠⚠ NO está la tabla del gacha ({p}): las cápsulas no van a abrir. "
                        f"Se copia de `rnr_script/gacha_machine.txt` del cliente.")
            return MAQUINAS
        with open(p, encoding="cp1252", errors="replace") as fh:
            texto = fh.read()
        for cap, cuerpo in re.findall(r'<machine[^>]*Capsule="(\d+)"[^>]*>(.*?)</machine>',
                                      texto, re.S):
            premios = []
            faltan = set()
            for crudo in re.findall(r"<item([^>]*)>", cuerpo):
                m = re.search(r'index="(\d+)"', crudo)
                if not m:
                    continue
                cl = _clase((re.search(r'Type="([^"]*)"', crudo) or [None, None])[1]
                            if re.search(r'Type="([^"]*)"', crudo) else None)
                if cl not in CLASES_QUE_SABEMOS:
                    faltan.add(cl)
                premios.append({
                    "item": int(m.group(1)),
                    "nombre": (re.search(r'Name="([^"]*)"', crudo) or ["", "?"])[1],
                    "clase": cl,
                    "valor": int((re.search(r'Value="(\d+)"', crudo) or [0, 0])[1]),
                    "boletos": int((re.search(r'Chance="(\d+)"', crudo) or [0, 0])[1]),
                })
            if premios:
                MAQUINAS[int(cap)] = premios
                if faltan:
                    MAQUINAS_INCOMPLETAS[int(cap)] = faltan
        _con = sum(1 for pr in MAQUINAS.values() if any(p["boletos"] for p in pr))
        log("SHOP", f"  ★ GACHA: {len(MAQUINAS)} máquinas, "
                    f"{sum(len(v) for v in MAQUINAS.values())} premios "
                    f"({_con} con probabilidades escritas, {len(MAQUINAS) - _con} a reparto parejo)"
                    + (f" · {len(MAQUINAS_INCOMPLETAS)} que NO se pueden entregar: "
                       f"{sorted(MAQUINAS_INCOMPLETAS)}" if MAQUINAS_INCOMPLETAS else ""))
        if verbose:
            for cap, pr in sorted(MAQUINAS.items()):
                print(f"  cápsula {cap}: {len(pr)} premios")
        return MAQUINAS


def premios_de(capsula):
    """La lista de premios de esa máquina, o `[]` si no existe."""
    if not MAQUINAS:
        cargar()
    with _lock:
        return list(MAQUINAS.get(int(capsula)) or [])


def es_maquina(capsula):
    """¿Este ítem es una máquina de gacha, sí o no? **Sin opinar sobre si sabemos abrirla.**

    ★★ Existe SEPARADA de `se_puede_abrir` a propósito, y la diferencia costó un crash:
      `se_puede_abrir` contesta `False` en DOS casos que no son el mismo —
        · *"no es una máquina de gacha"*  ⇒ el `FF69` no era "abrí": era **"¿cuántos tengo?"**
        · *"es una máquina, pero tiene premios que no sabemos dar"* ⇒ ahí sí hay que decir que no
      Tratarlos igual fue lo que mató al cliente el 2026-09-12 al comprar la Esmeralda de la
      Amistad: le contestábamos un resultado de sorteo a una pregunta de inventario.
    ⇒ Ver `lobby_tienda.h_ff69_abrir_capsula`.
    """
    if not MAQUINAS:
        cargar()
    with _lock:
        return int(capsula) in MAQUINAS


def se_puede_abrir(capsula):
    """`(True, "")` si sabemos entregar TODOS sus premios; `(False, motivo)` si no.

    ★ Es a nivel de MÁQUINA y no de premio a propósito: si se filtrara premio por premio, el
      bombo quedaría con menos bolillas de las que la vitrina muestra y nadie se enteraría.
    """
    cap = int(capsula)
    if not MAQUINAS:
        cargar()
    with _lock:
        if cap not in MAQUINAS:
            return False, "esa cápsula no es una máquina de gacha"
        faltan = MAQUINAS_INCOMPLETAS.get(cap)
    if faltan:
        return False, ("tiene premios de tipo " + "/".join(sorted(str(f) for f in faltan))
                       + ", que todavía no sabemos entregar")
    return True, ""


def sortear(capsula, premios=None):
    """Devuelve el premio que salió (un dict de `premios_de`) o `None`.

    ★ `premios` = el bombo, si hay que acotarlo (los que al jugador todavía le sirven). Cuando va
      en `None` se usa la máquina entera, que es el caso de siempre. Ver `pool_para`.
    ⚠ Los boletos se leen del subconjunto: si se sacan premios del bombo, los que quedan se
      reparten el total entre ellos. Es lo mismo que hacía el filtro viejo y sigue siendo correcto
      —nadie queda con probabilidad cero—, pero conviene tenerlo dicho.

    ★ **Dos repartos, y el que manda es la tabla**:
        · con `Chance` -> rifa ponderada sobre los boletos que están escritos;
        · sin `Chance` -> **parejo** entre todos los premios de esa máquina.
      Las máquinas de ropa (39 de 52, la 577 entre ellas) están en el segundo caso.

    ⚠ Si una máquina trae `Chance` en ALGUNOS premios y no en otros, los que no lo traen quedarían
      con cero boletos —o sea, nunca saldrían—. Eso **no pasa en esta tabla** (se contó: las 13
      máquinas con `Chance` lo tienen en el 100% de sus premios), pero si alguien la edita mal, acá
      se cae al reparto parejo en vez de dejar premios inalcanzables sin avisar.
    """
    premios = premios_de(capsula) if premios is None else list(premios)
    if not premios:
        return None
    boletos = [p["boletos"] for p in premios]
    if all(b > 0 for b in boletos):
        total = sum(boletos)
        dado = random.randrange(total)
        acum = 0
        for p in premios:
            acum += p["boletos"]
            if dado < acum:
                return p
        return premios[-1]          # por si el redondeo dejara un borde suelto
    if any(b > 0 for b in boletos):
        log("SHOP", f"  ⚠ la máquina {capsula} tiene `Chance` en unos premios y en otros no "
                    f"({sum(1 for b in boletos if b)}/{len(boletos)}): se reparte PAREJO para que "
                    f"ninguno quede inalcanzable. Revisar la tabla.")
    return random.choice(premios)


def resumen():
    """Un texto corto para el arranque y para las pruebas."""
    if not MAQUINAS:
        cargar()
    return (f"{len(MAQUINAS)} máquinas · "
            f"{sum(len(v) for v in MAQUINAS.values())} premios · "
            f"{len(MAQUINAS_INCOMPLETAS)} sin poder entregar")


# ── LOS PERSONAJES QUE UNO TIENE (la pestaña «Personaje» del armario) ────────────────────────
PERSONAJES = set()                 # los personajes del gacha: `spec.txt` ∩ `hero.txt`


def cargar_personajes(path=None, hero_path=None):
    """Los personajes del gacha = los ids que están en `spec.txt` **Y** en `hero.txt`.

    ⚠ `spec.txt` solo es condición NECESARIA: `0x46F4E0` busca cada id ahí y si no está escribe
      `[GACHA] Spec data error : %u` y lo descarta.
    ⛔⛔ Pero NO es la lista de personajes: es la tabla de STATS (`Grade VelUI TimeUI JudgeUI
      DelayUI` = "Velocidad de booster 30…" del cartel de la tienda), y la tienen también patines,
      cápsulas y zapatos. Hasta el 2026-09-26 se tomaba entera: de 648, **447 no eran personajes**
      (371 patines 0304/0404, 41 cápsulas 1301…) y a jugador4 le llegaba el patín 520185 en la lista
      — y `_aplicar_personaje` le dejaba "ponérselo" como cuerpo. El cliente lo filtraba solo (anonimo03
      no vio nada roto): el error era del server, que decía otra cosa que el juego.
      Lo que hace a un id PERSONAJE es `hero.txt` (su modelo de cuerpo entero): 201 en los dos
      = los 181 de la pestaña 1401 + 20 de la 0501.
    ★ Y explica algo que parecía un bug: el personaje BASE (el `char_id`, p.ej. 130900) **no está**
      en `spec.txt`. La pestaña no es "mis personajes": es **los que ganaste en el gacha**.
    """
    p = path or os.path.join(os.path.dirname(TABLA), "spec.txt")
    ph = hero_path or os.path.join(os.path.dirname(p), "hero.txt")
    with _lock:
        PERSONAJES.clear()
        if not os.path.exists(p):
            log("SHOP", f"  ⚠ no está `spec.txt` ({p}): la pestaña de personajes va a ir vacía")
            return PERSONAJES
        with open(p, encoding="cp1252", errors="replace") as fh:
            spec = {int(x) for x in re.findall(r'<Spec\s+Index="(\d+)"', fh.read())}
        if not os.path.exists(ph):
            # sin hero.txt no hay forma de separar: se queda como antes (spec entera), con aviso
            PERSONAJES.update(spec)
            log("SHOP", f"  ⚠ no está `hero.txt` ({ph}): personajes = spec.txt ENTERA ({len(spec)}), "
                        f"incluye patines y cápsulas")
            return PERSONAJES
        with open(ph, encoding="cp1252", errors="replace") as fh:
            hero = {int(x) for x in re.findall(r'<Char\s+Index\s*=\s*"(\d+)"', fh.read())}
        PERSONAJES.update(spec & hero)
        log("SHOP", f"  ★ personajes del gacha (spec.txt ∩ hero.txt): {len(PERSONAJES)} "
                    f"(spec {len(spec)} · hero {len(hero)})")
        return PERSONAJES


def es_personaje(item_id):
    """`True` si ese id es un personaje del gacha (está en `spec.txt` y en `hero.txt`)."""
    if not PERSONAJES:
        cargar_personajes()
    with _lock:
        return int(item_id) in PERSONAJES


def personajes_de(char):
    """Los personajes del gacha que tiene ese jugador, en el orden del inventario.

    Recibe el dict del personaje (el de `db_get_char`) para no depender de la base acá.
    """
    if not PERSONAJES:
        cargar_personajes()
    fuera = []
    for e in (char or {}).get("inventory") or []:
        _id = int(e["id"] if isinstance(e, dict) else e)
        if _id in PERSONAJES and _id not in fuera:
            fuera.append(_id)
    return fuera


def personaje_base(char):
    """El personaje ORIGINAL del jugador (el de la creación). Nunca es uno del gacha.

    ★ El cliente lo calcula solo con `cAccount::GetDefaultCharID` (`0x487E70`): es el registro cuyo
      id termina en **900/901**, y si no encuentra ninguno usa `130900`. Por eso lo guardamos en
      del `gender` guardado: al equipar un personaje del gacha se pisa el `char_id`, y ese número
      **deja de decir quién es el jugador** (los del gacha no codifican el sexo).
    """
    ch = char or {}
    # ⛔⛔ ACÁ SE LEÍA PRIMERO UN CAMPO `char_base` QUE **NUNCA SE GUARDÓ** — lo inventé el
    #   2026-09-08 para recordar el personaje original y jamás lo agregué al esquema (`chars` no
    #   tiene esa columna). Se escribía en memoria y se evaporaba **en silencio**: sin excepción,
    #   sin aviso, andando toda la sesión y rompiéndose al reloguear.
    #   ⇒ Y lo que rompía no era menor: sin él, el default era `130900` (el base MASCULINO), así
    #     que **toda jugadora que se pusiera un personaje del gacha y se lo sacara quedaba hombre**
    #     — y el guardado le reescribía el `gender` en la base. Le pasó a jugador34.
    #   ★ El dato bueno estaba guardado desde siempre: la columna `gender`. No hacía falta una
    #     columna nueva; hacía falta leer la que había.
    #   ⚠ Se saca la lectura de `char_base` entera. Un campo que no persiste es peor que no tenerlo:
    #     el código parece correcto y falla sólo después de reiniciar.
    actual = int(ch.get("char_id") or 0)
    # ⛔⛔ SIN PERSONAJE NO HAY BASE — y devolver `130900` acá ROMPIÓ LA CREACIÓN DE PERSONAJE.
    #   Reportado por anonimo03 el 2026-09-09: *"creé una cuenta y se saltó la creación de personaje"*.
    #   Una cuenta recién registrada llega con `{}`, y esta función le inventaba el `130900`. Con
    #   eso `registros_ff49` armaba una lista de un personaje y el `FF03` del login mandaba un
    #   `FF49` diciéndole al cliente *"ya tenés el 130900"* — así que se saltaba la pantalla de
    #   creación y entraba al lobby sin personaje.
    #   ★ Antes de que yo tocara el `FF49` (2026-09-08) el guard estaba en el handler
    #     (`_cid = int(ch.get("char_id") or 0)` y `if _cid:`), y al mover el cálculo acá me lo
    #     comí. El 0 tenía un significado —"todavía no hay"— y este default se lo tapó.
    #   ⇒ **0 = esta cuenta NO tiene personaje.** Los que llaman tienen que mirarlo; es el mismo
    #     0 que el handler ya miraba.
    if not actual:
        return 0
    if not es_personaje(actual):
        return actual
    # ⛔ ACÁ SE DEVOLVÍA 130900 SIEMPRE, y eso convertía en HOMBRE a toda jugadora que se pusiera un
    #   personaje del gacha y después se lo sacara. `char_base` **no se persiste** (no es columna),
    #   así que al reloguear siempre valía None y este default decidía.
    #   ★ El dato bueno estaba guardado todo el tiempo: la columna `gender`. Ahora se usa.
    return 130901 if int(ch.get("gender") or 0) & 1 else 130900


def registros_ff49(char):
    """`(select_key, [(key, parts), ...])` — la lista de personajes para el `FF49`.

    ⛔⛔ EL BUG QUE ESTO ARREGLA (2026-09-08). Reportado: *"apareció como 'usando', pero se veía mi
      ropa normal"*. El personaje del gacha **no estaba en la lista del cliente**, y `0x487F40`
      —el que lo busca— **cuando no encuentra NO falla: devuelve el PRIMERO** (`0x487F91` salta a
      `0x487FF5` y `0x488024 mov eax, esi`). Por eso sonaba, salía el aura y el cuerpo era el mismo:
      el cliente obedecía… con el personaje equivocado.

    ★★ Y la lista es del **`FF49`** (`0x5E0440`), no del MyRecord: ese handler la **vacía**
      (`0x48BD30`) y la vuelve a llenar. El bucle de personajes del MyRecord sólo AGREGA.

    ⚠ Los personajes del gacha van **SIN ROPA** (`parts` vacío): traen su propio cuerpo entero. Es
      lo que describió anonimo03 del juego original — *"al activar o desactivar volvía a la ropa
      normal"*.
    ⚠ El `key` de cada registro debe ser ≠ 0 o el cliente descarta la fila.
    """
    ch = char or {}
    base = personaje_base(ch)
    # ⛔ CUENTA SIN PERSONAJE -> LISTA VACÍA, y el handler NO manda el `FF49`. Mandarlo con un
    #   personaje inventado le dice al cliente que ya tiene uno y **se saltea la creación**
    #   (2026-09-09). Ver `personaje_base`, que es donde está el porqué entero.
    if not base:
        return 0, []
    _ropa = list(ch.get("parts") or [])
    regs = [(base, _ropa)]
    for pj in personajes_de(ch):
        if pj != base:
            # ⚠⚠ EXPERIMENTO EN CURSO (2026-09-08, idea de anonimo03: *"¿probar offsets no sería una
            #   buena idea? las primeras veces aparecía con vida"*).
            #   Acá iba `[]` — las 11 ranuras en CERO — porque el personaje del gacha trae su
            #   cuerpo entero. Y es el ÚNICO registro que va así: el del personaje base lleva la
            #   ropa. La sospecha es que ese vacío deja sin crear el objeto que después el
            #   temporizador del agotamiento lee nulo y revienta (`[timer+0x490]`, medido nulo en
            #   todos los ticks).
            #   ★ El dato que lo sugiere es de anonimo03: cuando el personaje aparecía en la pestaña
            #     **antes** de que yo lo agregara a este paquete, se veía con la vida entera.
            #   ⏳ Si con la ropa puesta deja de crashear, el vacío era la causa — y ahí habrá que
            #     ver cómo se oculta la ropa sin mandar ranuras vacías. Si crashea igual, esta
            #     hipótesis también se cae y se vuelve al parche del exe.
            regs.append((pj, list(_ropa) if GACHA_PJ_CON_ROPA else []))
    # el seleccionado = lo que tenga puesto ahora; si quedó en algo que no está en la lista, el base
    sel = int(ch.get("char_id") or 0) or base
    if sel not in {k for k, _ in regs}:
        sel = base
    return sel, regs


def apariencia(char):
    """`(char_id, parts)` — **lo que hay que DIBUJAR** de ese jugador.

    ⛔ EL BUG QUE ARREGLA (2026-09-08). Reportado: *"al crear una sala mi personaje salió con su
      ropa normal, pero al equipar y desequipar sí se equipó"*, y *"no aparece en el minichar de
      mi info"*. Le mandábamos el personaje del gacha **con la ropa puesta encima**, y la ropa
      gana: el cuerpo especial quedaba tapado en todos lados menos donde el cliente lo aplicaba a
      mano.

    ★ Un personaje del gacha **es un cuerpo entero**: cabeza, torso y piernas vienen en su modelo
      (`hero.txt`: `<Char Index="130030" Model="rnr_char/SP/SP0030A/SP0030A.md9">`). Por eso el
      juego original *"volvía a la ropa normal"* al sacarlo: mientras está puesto, la ropa **no
      se muestra**.

    ⚠ La ropa NO se pierde ni se toca: sigue en `parts` de la base. Acá sólo se decide qué se
      MANDA para dibujar. Sacarse el personaje la devuelve entera.
    """
    ch = char or {}
    cid = int(ch.get("char_id") or 0)
    # ★ El MARCO DE ASIENTO no es una prenda: se dibuja por su número (`catalogo.marco_puesto`,
    #   `FF0C cola[10]` / `FF15 #11`). Es categoría 10, la misma ranura del worn que las alas y
    #   los impulsores, así que en la lista de prendas sólo podría pisar a otro (2026-09-23).
    #   Lo mismo la TARJETA DE NOMBRE («Slot para Game id …»): viaja por su índice en el `FF78`.
    _parts = [p for p in (ch.get("parts") or [])
              if shop_catalog.family(p) not in ("slot_pack", "namecard", "hero_mode", "prophecy")]
    if cid and es_personaje(cid):
        # ★★★ PERO LOS ACCESORIOS SE QUEDAN (2026-09-10). anonimo03, estrenando el premio del canje:
        #   *"al usar un personaje gacha, la mascota se de-equipa"*.
        #   El cuerpo del gacha reemplaza pelo/top/bottom/zapatillas — **no** la mascota ni lo que
        #   se lleva en la mano. Ya estaba escrito en `paquetes.py`: *«la mascota y los accesorios
        #   no son piezas de avatar»*, con las 7 ranuras (`5 = pet`, `7 = wand`).
        #   ⇒ Sobreviven SÓLO las familias de `GACHA_FAMILIAS_QUE_SOBREVIVEN` (ajustes.py, que
        #     explica el porqué): **manos, mascota y alas**. Lo eligió anonimo03 mirando la pantalla,
        #     en dos pasos: primero probó dejando todos los accesorios y después lo acotó a estas
        #     tres. Es lista BLANCA: lo que no esté declarado se tapa, así una familia nueva no
        #     puede aparecer encima del cuerpo del gacha por descuido.
        return cid, [p for p in _parts
                     if shop_catalog.family(p) in GACHA_FAMILIAS_QUE_SOBREVIVEN]
    return cid, _parts


def parts_visibles(char):
    """Sólo las prendas que hay que dibujar (`[]` si tiene puesto un personaje del gacha)."""
    return apariencia(char)[1]


# ── EL SEXO DE CADA PERSONAJE (de `hero.txt` del cliente) ────────────────────────────────────
GENERO = {}                        # char_id -> 0 (hombre) / 1 (mujer)


def cargar_generos(path=None):
    """`hero.txt`: `<Char Index="130030" ... Gender="0">`. 0 = hombre · 1 = mujer."""
    p = path or os.path.join(os.path.dirname(TABLA), "hero.txt")
    with _lock:
        GENERO.clear()
        if not os.path.exists(p):
            log("SHOP", f"  ⚠ no está `hero.txt` ({p}): el gacha va a repartir sin mirar el sexo")
            return GENERO
        with open(p, encoding="cp1252", errors="replace") as fh:
            for m in re.finditer(r'<Char\s+Index\s*=\s*"(\d+)"[^>]*Gender="(\d+)"', fh.read()):
                GENERO[int(m.group(1))] = int(m.group(2))
        log("SHOP", f"  ★ sexo de {len(GENERO)} personajes (hero.txt)")
        return GENERO


def genero_de(item_id):
    """0/1 si es un personaje con sexo declarado, `None` si no lo es (una prenda, una moneda…)."""
    if not GENERO:
        cargar_generos()
    with _lock:
        return GENERO.get(int(item_id))


def sortear_para(capsula, genero, tiene=()):
    r"""El sorteo de una máquina. **NO filtra por sexo** — se reparte entre todos sus premios.

    ⛔⛔⛔ ACÁ HABÍA UN FILTRO POR SEXO Y ERA UNA INVENCIÓN MÍA. LO SAQUÉ EL 2026-09-09.

      Lo puse el día anterior porque anonimo03 reportó *"esta cuenta era F, pero recibió el gacha de
      M"*, y lo di por bueno sin ir a ver cómo lo resolvía el juego. **Salió mucho peor que lo que
      arreglaba**, porque hay máquinas con UN SOLO premio del sexo del jugador:

          la 577 tiene 6 premios y **uno solo es de mujer** (`Observador(M)`)
          ⇒ para una jugadora la máquina dejaba de sortear: era una expendedora

      MEDIDO EN PRODUCCIÓN, sobre las 536 tiradas del 2026-09-09:
          usn=5850  cápsula 577  ->  130027 x7    ← pagó SIETE cápsulas por el mismo personaje
          usn=5822  cápsula 749  ->  120208 x6
          usn=5822  cápsula 692  ->  150153 x3
          usn=9825  cápsula 577  ->  130027 x3
          … 29 cápsulas pagadas con UN SOLO resultado posible, 9 jugadoras. Todas mujeres.

    ★★★ CÓMO LO RESOLVÍA EL JUEGO DE VERDAD — el sexo lo elige **el jugador al elegir la máquina**,
      y el aviso está **en el nombre de la cápsula**:

          Mitología Griega (H)        ·  Mitología Griega (M)
          Cápsula Latino Bobby (H)    ·  Cápsula Latino Barby (M)
          Cápsula 2do Aniversario (H) ·  Cápsula 2do Aniversario (M)
          1er aniversario chicos      ·  1er aniversario chicas
          Serie Chico Dulce           ·  Serie chica linda

      24 de las 39 máquinas con personajes son de un solo sexo, y van en pares. Las MIXTAS lo son
      a propósito: la 577 trae `Observador(H)` **y** `Observador(M)` juntos.

    ★★ Y NO HAY NINGÚN CAMPO DE SEXO EN LOS DATOS DE LA MÁQUINA — buscado, no supuesto:
        · `gacha_machine.txt` -> `Modelid`, `Capsule`, `MachineTexture`; por premio `index`,
          `Name`, `DescIndex`, `Stamina`, `StaminaRcoin`. **Nada de sexo.**
        · `spec.txt`          -> sólo estadísticas (`Grade`, `VelUI`…)
        · `gacha/Machine/*.xml` -> trayectorias de CÁMARA
        · `hero.txt`          -> el ÚNICO que trae `Gender`, y es **por personaje**, no por máquina
      ⇒ el sexo de una máquina no está declarado: **se deduce de lo que tiene adentro**.

    ★★ Y EL CLIENTE TAMPOCO FILTRA. Su handler del premio (`0x5D9320`, el `FF122`) hace
      `0x50E200` (resolver ítem) -> `0x46C8B0` (¿es prenda?) -> `0x48F5D0` (al armario) ->
      `0x4D3970` (animación). **No lee el sexo en ninguna parte.** Acepta lo que le mandemos, así
      que el reparto es responsabilidad entera del server — por eso este filtro no lo corregía
      nadie del otro lado.

    ★ LOS REPETIDOS TAMPOCO SE EVITABAN, Y ES A PROPÓSITO. El padrón del cliente (`[0x934354]`) es
      un **`std::map` con el id de personaje como clave** (`0x46F320` es la búsqueda en el árbol y
      `0x46F4E0` el "buscá o insertá" que después escribe la vida en `[+0x10]`): sacar dos veces el
      mismo **no crea otra entrada, le reescribe la VIDA**. Y eso cierra con el resto de la tabla:
      `Stamina="100" StaminaRcoin="300"`, más `[GACHA] CmdDecreasCharacterHP` y
      `[GACHA] Stamina Charge Cmd`. Los personajes **se gastan con el uso** y se recargan pagando.
      ⇒ **el repetido era el premio de consuelo**: te rellena el que ya tenés.

    ⚠ El parámetro `genero` se conserva para no tocar a quien llama, y porque si algún día se
      quiere volver a filtrar, el dato ya está donde hace falta. **Hoy no se usa a propósito.**
      ⇒ Lo que SÍ hay que hacer está del lado del cliente: 11 máquinas de un solo sexo tienen un
        nombre que no lo avisa (`Cápsula Egipcia`, `Cápsula Oriental`, `Serie de Vampiros`…).
        Se etiquetan con `(H)`/`(M)` en `shop_lt.txt`, siguiendo la convención del propio juego.
        Ver `GACHA_CAPSULAS.md`.

    ★★ `tiene` = lo que el jugador YA posee. Los premios repetidos se sacan del bombo, y esto sí
      es una decisión NUESTRA — el original los permitía. Ver `pool_para` acá abajo, donde está
      el porqué, y `GACHA_SIN_REPETIDOS` en `ajustes.py` para apagarlo.
    """
    return sortear(capsula, pool_para(capsula, tiene))


def pool_para(capsula, tiene=()):
    """Los premios de esa máquina que **todavía le sirven** a ese jugador. `[]` si ya los tiene todos.

    ★★★ POR QUÉ EXISTE — pedido de anonimo03 el 2026-09-09: *"¿podemos hacer que no toquen
      repetidos?, sigue tocando repetidos"*.

    ⚠ Y ES UNA DECISIÓN NUESTRA, NO DEL ORIGINAL. El juego repartía repetidos a propósito: su
      padrón es un `std::map` por id (`0x46F4E0` busca-o-inserta y reescribe la **vida** en
      `[+0x10]`), y con `Stamina="100"` / `StaminaRcoin="300"` los personajes **se gastan con el
      uso**. Allá el repetido te **rellenaba** el que ya tenías: era el premio de consuelo.

    ★★ ACÁ ESO NO EXISTE. Nosotros mandamos la vida FIJA (`GACHA_PERSONAJE_HP = 9999`) y no hay
      handler del desgaste (`CmdDecreasCharacterHP` no lo implementamos). O sea que un repetido
      **no rellena nada y no sirve para absolutamente nada**: es una cápsula pagada a cambio de
      cero. Sacarlos del bombo es lo correcto PARA NUESTRO JUEGO, y por eso queda escrito que el
      original hacía lo otro — el día que se implemente el desgaste, esto se revisa.

    ⚠ Sólo se descartan los premios que son ÍTEMS. Las monedas y la experiencia (`MONEDA`/`CLASE`)
      no se "tienen": entran siempre, o una máquina de puro RCoin se cerraría sola tras la 1ª.
    ⚠ Devuelve `[]` cuando no le queda NADA, y el que llama **tiene que mirarlo antes de cobrar**
      la cápsula. Ver `h_ff69_abrir_capsula`, donde el chequeo va ANTES del `db_del_inventory`.
    """
    premios = premios_de(capsula)
    if not SIN_REPETIDOS or not premios:
        return premios
    _tiene = {int(x) for x in (tiene or ())}
    if not _tiene:
        return premios
    return [p for p in premios
            if p["clase"] in ("MONEY", "SEED", "EXP") or int(p["item"]) not in _tiene]


def genero_visible(char):
    """El sexo que hay que DIBUJAR de ese jugador (el ícono, el cuerpo por defecto).

    ⛔ EL BUG QUE ARREGLA (2026-09-09). Reportado con dos capturas: *"un char M, al ponerse
      personaje de M, su ícono aparece como F"*. Medido:

          110275 (el personaje puesto)  ->  último dígito IMPAR  ->  nuestra regla decía MUJER
          hero.txt                      ->  Gender="0"           ->  es HOMBRE

    ★ La regla vieja (`char_id & 1`) sale de los personajes BASE, donde sí vale: `130900` hombre,
      `130901` mujer. Pero **los del gacha no codifican el sexo en el número** — lo dice `hero.txt`,
      y ahí `130029` y `130031` son impares y de HOMBRE.
      ⇒ Al equipar uno le pisábamos el `char_id` y el ícono se daba vuelta.

    ⚠ Se cae a la regla vieja sólo si el personaje no está en `hero.txt`. Ahí el número es lo único
      que hay, y para los base es correcto.
    """
    cid = int((char or {}).get("char_id") or 0)
    g = genero_de(cid)
    return g if g is not None else (cid & 1)


def genero_del_jugador(char):
    """El sexo del jugador para el SORTEO: el de su personaje BASE, no el que tenga puesto.

    ★ Es a propósito distinto de `genero_visible`: si alguien se pone un personaje de hombre, no
      por eso deja de poder ganar los suyos. Lo que decide qué premios le sirven es **quién es**,
      no qué está usando en ese momento.
    """
    base = personaje_base(char)
    g = genero_de(base)
    return g if g is not None else (int(base) & 1)


def sexo(char_id):
    """El sexo de un personaje POR SU ID: `hero.txt` primero, y el último dígito sólo si no está.

    ★★ ES LA ÚNICA FUENTE que debe usarse para pintar el distintivo (el ícono azul/rosa). La regla
      vieja —`char_id & 1`— vale para los personajes BASE (`130900` hombre / `130901` mujer) y
      **falla para los del gacha**, cuyos números no codifican el sexo.
      Visto en pantalla el 2026-09-09 en «Ver Perfil», con el mismo jugador:
          Ice Observador   (130029, impar) -> el ícono salía ROSA   ⛔
          Assault Observ.  (130030, par)   -> salía bien, DE CASUALIDAD
      Los dos son de HOMBRE según `hero.txt`.

    ⚠ Estaba en CUATRO paquetes distintos (el ocupante de sala, «mi info», «ver perfil de otro» y
      el constructor viejo del `FF0C`) y en el armado del ocupante. Arreglar uno solo dejaba el
      ícono bien en una pantalla y mal en la de al lado — que es exactamente lo que se vio.
    """
    cid = int(char_id or 0)
    g = genero_de(cid)
    return (int(g) & 1) if g is not None else (cid & 1)
