"""contenido_interno — ★ 20-nov-2026: lo que el COORDINADOR Eñeños edita del launcher de ESTE juego, por la red de adentro.

anonimo03: *«zona de contenido dinámico del launcher nuevo, para cada juego: premios de las casillas de asistencia, premios
de la ruleta, nuevos avisos…»* y *«una pastilla de Novedades: noticias (el acordeón que abre hacia abajo) y parches (el
que abre hacia la izquierda)»*. Todo eso YA vive acá (`launcher_contenido` en datos.db, `tira_anuncios`): el
Coordinador no guarda una copia, edita ESTO — así el launcher no cambia y no hay dos verdades.

    GET  /api/interno/contenido                       todo lo editable + metadatos (quién y cuándo lo cambió)
    GET  /api/interno/contenido/items?q=              buscar ítems del catálogo (para los premios de la asistencia)
    POST /api/interno/contenido {clave, valor, quien} guardar: noticias | asistencia | ruleta | tira
    POST /api/interno/contenido/previa {clave, valor} validar SIN guardar (+ el mes resuelto, si es la asistencia)

⛔ Sólo con `X-Ficha-Interna` (= R2_CUENTAS_FICHA_INTERNA, la misma de la presencia): sin ella, 404 como si no existiera.
   Caddy además corta `/api/interno` desde afuera. ⛔ QUIÉN puede (admin, moderador con ese juego) lo decide el
   Coordinador; acá se valida el DATO con las MISMAS funciones que el panel viejo, y queda en su auditoría.
"""
import calendar
import json
from datetime import date

from . import almacen

CLAVES = ("noticias", "asistencia", "ruleta", "tira")
ITEMS_MAX = 40


def _meta():
    """{clave: {quien, cambiado}} de lo que ya se guardó alguna vez (lo que nunca se tocó es el de fábrica)."""
    from . import launcher_contenido as LC
    with almacen._lock:
        filas = LC._con().execute("SELECT clave, quien, cambiado FROM launcher_contenido").fetchall()
    return {r["clave"]: {"quien": r["quien"] or "", "cambiado": int(r["cambiado"] or 0)} for r in filas}


def mes_asistencia(cfg, anio=None, mes=None):
    """El mes como lo vería un jugador: lo que paga cada día, de qué regla sale y qué paga si pide racha y no la hay."""
    from . import asistencia as A
    h = A.hoy()
    anio, mes = int(anio or h.year), int(mes or h.month)
    dias = []
    for i in range(1, calendar.monthrange(anio, mes)[1] + 1):
        d = date(anio, mes, i)
        reglas = A.reglas_de(d, cfg)
        principal, origen = reglas[0]
        dias.append({"fecha": d.isoformat(), "dia": i, "dow": A._dow(d), "origen": origen,
                     "premios": A._con_nombres(principal["premios"]), "titulo": principal.get("titulo", ""),
                     "racha": bool(principal.get("racha")),
                     "si_no": A._con_nombres(A.regla_de(d, cfg, False)["premios"]) if principal.get("racha") else None,
                     "hoy": d == h})
    return {"anio": anio, "mes": mes, "hoy": h.isoformat(), "dias": dias}


def todo():
    from . import asistencia, launcher_contenido as LC, ruleta, tira
    from .ajustes import TIRA_TEXTO_MAX, TIRA_TOTAL_MAX
    asis = asistencia.config()
    return {
        "version": 1, "claves": list(CLAVES), "cambiado": _meta(),
        "noticias": LC.leer("noticias"), "etiquetas": list(LC.ETIQUETAS), "juegos_noticias": list(LC.JUEGOS),
        "etiquetas_general": list(LC.ETIQUETAS_GENERAL),
        "noticias_max": LC.NOTICIAS_MAX, "noticia_texto_max": LC.NOTICIA_TEXTO_MAX,
        "asistencia": asis, "asistencia_mes": mes_asistencia(asis),
        "ruleta": ruleta.config(), "ruleta_resumen": ruleta.resumen(), "ruleta_mayor_total": len(ruleta.mayor()),
        "tira": tira.lista_panel(), "tira_texto_max": TIRA_TEXTO_MAX, "tira_total_max": TIRA_TOTAL_MAX,
    }


def buscar_items(q, limite=ITEMS_MAX):
    """Ítems del catálogo por número o por parte del nombre (sin distinguir mayúsculas)."""
    from . import shop_catalog
    shop_catalog._ensure()
    q = str(q or "").strip().lower()
    if not q:
        return []
    if q.isdigit():
        it = shop_catalog.get(int(q))
        return [{"item": int(q), "nombre": it.get("name") or f"ítem {q}"}] if it else []
    out = []
    for idx, it in shop_catalog.CATALOG.items():
        nombre = str(it.get("name") or "")
        if q in nombre.lower():
            out.append({"item": int(idx), "nombre": nombre})
            if len(out) >= limite:
                break
    return out


def previa(d):
    """Valida sin guardar. -> (código, datos)."""
    from . import asistencia, launcher_contenido as LC
    clave, valor = d.get("clave"), d.get("valor")
    if clave not in ("noticias", "asistencia", "ruleta"):
        return 400, {"error": "clave: noticias · asistencia · ruleta"}
    try:
        limpio = LC.validar(clave, valor)
    except (ValueError, KeyError) as e:
        return 400, {"error": str(e)}
    out = {"ok": True, "valor": limpio}
    if clave == "asistencia":
        try:
            anio, mes = (int(x) for x in str(d.get("mes") or "").split("-")) if d.get("mes") else (None, None)
        except ValueError:
            anio = mes = None
        out["mes"] = mes_asistencia(asistencia.validar_config(limpio), anio, mes)
    return 200, out


def guardar(d):
    """-> (código, datos). Mismas reglas que el panel viejo (`launcher_contenido.validar` / `tira.guardar_panel`)."""
    from . import launcher_contenido as LC, panel_admin, tira
    clave = d.get("clave")
    quien = " ".join(str(d.get("quien") or "").split())[:60] or "coordinador"
    if clave not in CLAVES:
        return 400, {"error": "clave: " + " · ".join(CLAVES)}
    if clave == "tira":
        antes = tira.lista_panel()
        error, resumen = tira.guardar_panel(d.get("valor"), quien=quien)
        if error:
            return 400, {"error": error}
        panel_admin.auditar_externo(quien, "tira", {"antes": [(f["id"], f["texto"], f["vence"], f["activo"]) for f in antes],
                                                    "resumen": resumen})
        return 200, {"ok": True, "resumen": resumen, **todo()}
    antes = LC.leer(clave)
    error, limpio = LC.guardar(clave, d.get("valor"), quien)
    if error:
        return 400, {"error": error}
    panel_admin.auditar_externo(quien, "launcher/" + clave, {"antes": antes, "despues": limpio})
    return 200, {"ok": True, **todo()}


def atender_panel(h, metodo, partes, cuerpo=b""):
    """★ 20-nov FASE C: `/api/interno/panel/<ruta del panel viejo>` — la MISMA ruta de `/api/admin/…`, corrida como el
    actor externo (`panel_admin.con_externo`). Cabeceras: `X-Coordinador-Quien` (para la auditoría) y
    `X-Coordinador-Admin: 1` si en el Coordinador es ADMIN (si no, el modo invisible le esconde igual que a un GM).
    ⛔ La ficha primero; sin ella, 404. ⛔ Qué rutas puede pedir cada uno lo decide el Coordinador (lista cerrada)."""
    from . import panel_admin, presencia
    if not presencia.ficha_ok(h.headers.get("X-Ficha-Interna")):
        return h._mandar(404, {"error": "no existe"})
    if not partes or partes[0] in ("streamer", "respaldo", "logs"):       # (lo que NO se hace desde afuera, ni por error)
        return h._mandar(404, {"error": "no existe"})
    quien = h.headers.get("X-Coordinador-Quien") or "coordinador"
    admin = h.headers.get("X-Coordinador-Admin") == "1"
    if partes[0] == "gmnpc":                # ★ 27-nov: las cuentas GM NPC — SÓLO por acá (el panel viejo no las tiene)
        from . import gm_npc
        return panel_admin.con_externo(quien, admin, lambda: gm_npc.atender(h, metodo, partes, cuerpo, quien))
    if metodo == "GET":
        return panel_admin.con_externo(quien, admin, lambda: panel_admin.atender_get(h, partes))
    return panel_admin.con_externo(quien, admin, lambda: panel_admin.atender_post(h, partes, cuerpo))


def atender(h, metodo, partes, cuerpo=b""):
    """`partes` = lo que sigue a /api/interno/contenido. ⛔ La ficha se mira ANTES que nada."""
    from . import presencia
    if not presencia.ficha_ok(h.headers.get("X-Ficha-Interna")):
        return h._mandar(404, {"error": "no existe"})
    privado = "private, no-store"
    if metodo == "GET":
        if partes == []:
            return h._mandar(200, todo(), cache=privado)
        if partes == ["items"]:
            import urllib.parse
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(h.path).query).get("q", [""])[0]
            return h._mandar(200, {"items": buscar_items(q)}, cache=privado)
        return h._mandar(404, {"error": "no existe"})
    try:
        d = json.loads(cuerpo.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return h._mandar(400, {"error": "cuerpo inválido"})
    if not isinstance(d, dict):
        return h._mandar(400, {"error": "cuerpo inválido"})
    if partes == []:
        return h._mandar(*guardar(d), cache=privado)
    if partes == ["previa"]:
        return h._mandar(*previa(d), cache=privado)
    return h._mandar(404, {"error": "no existe"})
