"""Enlaza las filas existentes de `users` en `datos.db` con su Eñeños ID de Cuenta Eñeños.

Uso (los dos pasos del juego el día del reemplazo, en este orden):
    python -m servidor.enlazar_cuentas                  anota en cada cuenta su Eñeños ID
    python -m servidor.enlazar_cuentas vaciar-claves    después: borra de la base del juego las contraseñas (ver `vaciar_claves`)

Usa `R2_CUENTAS_URL` y `R2_CUENTAS_FICHA_INTERNA` (pide `GET /cuentas/interno/enlaces`).
Idempotente: si ya tiene el mismo `enenos_id`, no toca la fila; si hay conflicto, falla explícito;
nunca imprime nombres de usuario ni contraseñas; devuelve código != 0 si queda alguna fila sin enlazar
o si falla el pedido HTTP.
"""
import sys

from . import almacen, pase


def enlazar(timeout=5.0):
    """Enlaza `users.enenos_id` comparando `username` EXACTO (`COLLATE BINARY`).
    -> `{"enlazadas": int, "ya_enlazadas": int, "sin_enlazar": int}`."""
    res = pase.enlaces_internos(timeout=timeout)
    if res.get("estado") != "ok":
        raise RuntimeError(f"no pude pedir enlaces a Cuenta Eñeños: {res.get('error') or res.get('codigo')}")
    datos = res.get("datos") or {}
    cuentas = datos.get("cuentas")
    if not isinstance(cuentas, list):
        raise RuntimeError("respuesta inválida de Cuenta Eñeños: falta 'cuentas'")

    mapa = {}
    for item in cuentas:
        if not isinstance(item, dict):
            raise RuntimeError("elemento inválido en 'cuentas'")
        usuario = str(item.get("usuario") or "")
        uid_val = item.get("uid")
        if isinstance(uid_val, bool):
            raise RuntimeError("enenos_id inválido en respuesta")
        try:
            eid = int(uid_val)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("enenos_id inválido en respuesta") from exc
        if not usuario or eid <= 0:
            raise RuntimeError("enlace incompleto en respuesta")
        if usuario in mapa and mapa[usuario] != eid:
            raise ValueError(f"conflicto en enlaces de Cuenta Eñeños: dos IDs distintos ({mapa[usuario]} y {eid})")
        mapa[usuario] = eid

    enlazadas = 0
    ya_enlazadas = 0
    sin_enlazar = 0
    actualizaciones = []

    with almacen._lock:
        c = almacen.conectar()
        filas = c.execute("SELECT uid AS fila, uid, username, enenos_id FROM users ORDER BY uid").fetchall()
        por_eid = {}
        for f in filas:
            if f["enenos_id"] is not None:
                eid_actual = int(f["enenos_id"])
                rowid_actual = int(f["fila"])
                if eid_actual in por_eid and por_eid[eid_actual] != rowid_actual:
                    raise ValueError(f"conflicto: enenos_id={eid_actual} repetido en users")
                por_eid[eid_actual] = rowid_actual

        for f in filas:
            rowid = int(f["fila"])
            usuario = str(f["username"] or "")
            actual = int(f["enenos_id"]) if f["enenos_id"] is not None else None
            esperado = mapa.get(usuario)
            if esperado is None:
                if actual is None:
                    sin_enlazar += 1
                else:
                    ya_enlazadas += 1
                continue
            if actual is not None:
                if actual == esperado:
                    ya_enlazadas += 1
                    continue
                raise ValueError(f"conflicto en uid={int(f['uid'])}: tiene enenos_id={actual}, distinto de {esperado}")
            otro_rowid = por_eid.get(esperado)
            if otro_rowid is not None and otro_rowid != rowid:
                raise ValueError(f"conflicto: enenos_id={esperado} ya pertenece a otra fila (rowid={otro_rowid})")
            por_eid[esperado] = rowid
            actualizaciones.append((esperado, rowid))
            enlazadas += 1

        if actualizaciones:
            with c:
                for eid, rowid in actualizaciones:
                    c.execute("UPDATE users SET enenos_id = ? WHERE uid = ?", (eid, rowid))

    return {"enlazadas": enlazadas, "ya_enlazadas": ya_enlazadas, "sin_enlazar": sin_enlazar}


def _solo_el_estado(pass_hash):
    """`BANNED:FUSIONADA:<hash>` -> `BANNED:FUSIONADA:`. Devuelve `(lo que queda, tenía algo más que el estado)`."""
    resto, estado = str(pass_hash or ""), ""
    if resto.startswith("BANNED:"):
        estado, resto = estado + "BANNED:", resto[7:]
    if resto.startswith(almacen.FUSIONADA):
        estado, resto = estado + almacen.FUSIONADA, resto[len(almacen.FUSIONADA):]
    return estado, bool(resto)


def vaciar_claves(timeout=5.0):
    """★ 15-nov · El ÚLTIMO paso de la forma nueva: la base del juego deja de guardar contraseñas.

    En la versión nueva sólo Cuenta Eñeños guarda contraseñas (envueltas). Después de copiar y enlazar, el SHA-256
    que queda en `users.pass_hash` ya no lo lee nadie y es justo lo que no conviene tener en la base del juego: se
    borra, dejando sólo la marca de estado que el juego sí usa (`BANNED:` y `FUSIONADA:`).
    ⛔ No tiene vuelta atrás sobre ESTA base (con `R2_LOGIN` vacío ya no entra nadie): la vuelta atrás es el respaldo
      de antes. Por eso sólo corre si TODAS las cuentas están enlazadas y Cuenta Eñeños confirma que las tiene.
    -> `{"vaciadas": n, "ya_vacias": m}`. Se puede correr dos veces."""
    res = pase.enlaces_internos(timeout=timeout)
    if res.get("estado") != "ok":
        raise RuntimeError(f"no pude preguntarle a Cuenta Eñeños: {res.get('error') or res.get('codigo')}")
    alla = set()
    for item in (res.get("datos") or {}).get("cuentas") or []:
        try:
            alla.add(int(item.get("uid")))
        except (AttributeError, TypeError, ValueError):
            raise RuntimeError("respuesta inválida de Cuenta Eñeños") from None
    with almacen._lock:
        c = almacen.conectar()
        filas = c.execute("SELECT uid, pass_hash, enenos_id FROM users").fetchall()
        sueltas = sum(1 for f in filas if f["enenos_id"] is None)
        if sueltas:
            raise RuntimeError(f"hay {sueltas} cuenta(s) sin Eñeños ID: primero enlazar; no vacío nada")
        faltan = sum(1 for f in filas if int(f["enenos_id"]) not in alla)
        if faltan:
            raise RuntimeError(f"Cuenta Eñeños no tiene {faltan} cuenta(s) del juego: no vacío nada")
        cambios = []
        for f in filas:
            estado, tenia_mas = _solo_el_estado(f["pass_hash"])
            if tenia_mas:
                cambios.append((estado, int(f["uid"])))
        if cambios:
            with c:
                c.executemany("UPDATE users SET pass_hash = ? WHERE uid = ?", cambios)
        # Un UPDATE no borra los bytes viejos del ARCHIVO: quedan en el WAL y en las páginas libres hasta que se
        # reescriba. Se asienta el WAL y se rearma la base (`VACUUM`), para que el SHA-256 no siga en el disco.
        # (Con el juego apagado, que es como se corre esto. Si otro proceso la tiene abierta, avisa y no rompe.)
        compactada = True
        try:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.execute("VACUUM")
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:                                        # noqa: BLE001
            compactada = False
    return {"vaciadas": len(cambios), "ya_vacias": len(filas) - len(cambios), "compactada": compactada}


def main(args=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass
    args = sys.argv[1:] if args is None else list(args)
    if args[:1] == ["vaciar-claves"]:
        try:
            v = vaciar_claves()
        except Exception as exc:                                 # noqa: BLE001
            print(f"⛔ vaciar-claves: {exc}", file=sys.stderr)
            return 1
        print(f"✔ vaciar-claves: vaciadas={v['vaciadas']}, ya_vacias={v['ya_vacias']}"
              + ("" if v["compactada"] else "  ⚠ NO se pudo rearmar el archivo (¿el juego está prendido?): "
                                            "los bytes viejos siguen en el disco hasta correrlo de nuevo con el juego apagado"))
        return 0 if v["compactada"] else 1
    if args:
        print("uso: python -m servidor.enlazar_cuentas [vaciar-claves]", file=sys.stderr)
        return 2
    try:
        res = enlazar()
    except Exception as exc:                                     # noqa: BLE001
        print(f"⛔ enlazar_cuentas: {exc}", file=sys.stderr)
        return 1
    print(f"✔ enlazar_cuentas: enlazadas={res['enlazadas']}, "
          f"ya_enlazadas={res['ya_enlazadas']}, sin_enlazar={res['sin_enlazar']}")
    return 1 if res["sin_enlazar"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
