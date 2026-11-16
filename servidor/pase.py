# -*- coding: utf-8 -*-
"""pase — verificación única de pases Ed25519 emitidos por Cuenta Eñeños.

Cuando `R2_LOGIN=pase`, ni el juego (`lobby.py`, `cuenta_personajes.py`), ni la web (`api_web.py`),
ni el launcher (`launcher_api.py`) aceptan usuario + contraseña: todo ingreso presenta un pase JWT
firmado con Ed25519 por Cuenta Eñeños (`servidor/portero.py`).

Qué comprueba `verificar_pase(pase_txt, aud)`:
  1. Firma Ed25519 válida con la clave pública de Cuenta Eñeños (`comprobar_firma` de acá + `firma_ed25519`);
  2. `aud` coincide con la pieza que recibe el pase (`"r2beat2013"`, `"web"` o `"parches"`);
  3. No venció (`exp`);
  4. `sub` es un `uid` entero positivo;
  5. No fue usado antes: recuerda cada `jti` hasta su vencimiento (`exp`), con tope `MAX_PASES_RECORDADOS`.

⛔ Regla: verificar un pase NUNCA llama a Cuenta Eñeños por cada login. La clave pública sale de
`R2_CUENTAS_CLAVE_PUBLICA` o se pide UNA sola vez al arrancar a `R2_CUENTAS_URL` (`/clave-publica`) y
queda en memoria.
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import firma_ed25519 as ed
from .registro import log

# ★ 15-nov: el juego comprueba el pase SOLO, sin `portero.py` (que es Cuenta Eñeños, otra pieza y otra imagen:
#   el server del repo público no lo trae). Es el mismo modelo que `portero.comprobar_pase`, igual que hace EDA.
EMISOR = "r2beat-portero"                     # el `iss` que pone Cuenta Eñeños (`portero.EMISOR`)

MAX_PASES_RECORDADOS = 50_000
CACHE_NOMBRES_TTL = 300.0
MAX_NOMBRES_CACHE = 10_000

_lock = threading.Lock()
_clave_pub = None            # bytes (32) o None
_clave_env_vista = None      # último valor visto de R2_CUENTAS_CLAVE_PUBLICA
_url_intentada = None        # último R2_CUENTAS_URL al que ya se le pidió /clave-publica
_aviso_sin_clave = False
_usados = {}                 # jti -> exp (epoch en segundos)
_cache_nombres = {}          # (url, ficha, uid) -> (ts, usuario)


def modo_pase():
    """True cuando `R2_LOGIN=pase`; False si está vacía o vale `clave` (modo histórico)."""
    return (os.environ.get("R2_LOGIN") or "").strip().lower() == "pase"


def parsear_clave_publica(valor):
    """Convierte base64url, hex de 64 chars o JSON JWKS (`/clave-publica`) en 32 bytes de clave pública, o None."""
    if isinstance(valor, (bytes, bytearray)):
        return bytes(valor) if len(valor) == 32 else None
    txt = (valor or "").strip()
    if not txt:
        return None
    if txt.startswith("{"):
        try:
            d = json.loads(txt)
            if isinstance(d.get("keys"), list) and d["keys"]:
                txt = str(d["keys"][0].get("x") or "").strip()
            elif d.get("x"):
                txt = str(d["x"]).strip()
        except Exception:                                                # noqa: BLE001
            return None
    if len(txt) == 64:
        try:
            b = bytes.fromhex(txt)
            if len(b) == 32:
                return b
        except ValueError:
            pass
    try:
        b = _de_b64u(txt)
        if len(b) == 32:
            return b
    except Exception:                                                    # noqa: BLE001
        return None
    return None


def _rutas_cuenta(url_base, sufijo):
    base = (url_base or "").strip().rstrip("/")
    if not base:
        return []
    if base.endswith("/cuentas"):
        return [base + sufijo, base[:-len("/cuentas")] + sufijo]
    return [base + sufijo, base + "/cuentas" + sufijo]


def cargar_clave_desde_url(url_base, timeout=3.0):
    """Pide `/clave-publica` una vez a `url_base`. -> `(pub_bytes, kid)` o `(None, None)`."""
    for u in _rutas_cuenta(url_base, "/clave-publica"):
        try:
            req = urllib.request.Request(u, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    continue
                d = json.loads(r.read().decode("utf-8"))
                k = (d.get("keys") or [{}])[0]
                pub = parsear_clave_publica(k.get("x") or "")
                if pub:
                    return pub, str(k.get("kid") or "")
        except Exception:                                                # noqa: BLE001
            continue
    return None, None


def inicializar(timeout=3.0):
    """Carga la clave pública al arrancar (de `R2_CUENTAS_CLAVE_PUBLICA` o una vez de `R2_CUENTAS_URL`).
    Si `R2_LOGIN=pase` y no consigue clave, deja aviso claro en el log y no lanza."""
    global _clave_pub, _clave_env_vista, _url_intentada, _aviso_sin_clave
    with _lock:
        env_k = (os.environ.get("R2_CUENTAS_CLAVE_PUBLICA") or "").strip()
        _clave_env_vista = env_k
        if env_k:
            pub = parsear_clave_publica(env_k)
            _clave_pub = pub
            if pub:
                _aviso_sin_clave = False
                log("MAIN", "🔑 R2_LOGIN=pase: clave pública Ed25519 cargada de R2_CUENTAS_CLAVE_PUBLICA")
                return pub
            log("MAIN", "⚠ R2_LOGIN=pase: R2_CUENTAS_CLAVE_PUBLICA no es una clave Ed25519 válida de 32 bytes")
        url = (os.environ.get("R2_CUENTAS_URL") or "").strip()
        _url_intentada = url
        if url:
            pub, kid = cargar_clave_desde_url(url, timeout=timeout)
            _clave_pub = pub
            if pub:
                _aviso_sin_clave = False
                log("MAIN", f"🔑 R2_LOGIN=pase: clave pública Ed25519 obtenida de {url} (kid={kid})")
                return pub
        _clave_pub = None
        if modo_pase():
            _aviso_sin_clave = True
            log("MAIN", "⚠ R2_LOGIN=pase: sin clave pública (ni R2_CUENTAS_CLAVE_PUBLICA ni responde R2_CUENTAS_URL); "
                        "se rechazarán todos los logins hasta tener clave")
        return None


def poner_clave_publica(pub):
    """Fija en memoria la clave pública (para pruebas o configuración directa)."""
    global _clave_pub, _clave_env_vista, _aviso_sin_clave
    with _lock:
        _clave_pub = parsear_clave_publica(pub)
        _clave_env_vista = (os.environ.get("R2_CUENTAS_CLAVE_PUBLICA") or "").strip()
        if _clave_pub:
            _aviso_sin_clave = False
        return _clave_pub


def clave_publica():
    """Devuelve los 32 bytes de clave pública en memoria, o None.
    ⛔ Nunca llama por red en cada login: a `R2_CUENTAS_URL` sólo se le pregunta una vez por configuración."""
    global _clave_pub, _clave_env_vista, _url_intentada, _aviso_sin_clave
    env_k = (os.environ.get("R2_CUENTAS_CLAVE_PUBLICA") or "").strip()
    url = (os.environ.get("R2_CUENTAS_URL") or "").strip()
    with _lock:
        if env_k != _clave_env_vista:
            _clave_env_vista = env_k
            _clave_pub = parsear_clave_publica(env_k) if env_k else None
            if not env_k:
                _url_intentada = None
        if _clave_pub is not None:
            return _clave_pub
        if not env_k and url and _url_intentada != url:
            _url_intentada = url
            pub, kid = cargar_clave_desde_url(url)
            if pub:
                _clave_pub = pub
                _aviso_sin_clave = False
                log("MAIN", f"🔑 R2_LOGIN=pase: clave pública Ed25519 obtenida de {url} (kid={kid})")
                return _clave_pub
        if modo_pase() and not _aviso_sin_clave:
            _aviso_sin_clave = True
            log("MAIN", "⚠ R2_LOGIN=pase: sin clave pública disponible; se rechazan los logins con pase")
        return None


def _de_b64u(s):
    s = s.encode("ascii") if isinstance(s, str) else s
    return base64.urlsafe_b64decode(s + b"=" * (-len(s) % 4))


def comprobar_firma(pase, pub, juego, ahora=None, tolerancia=30):
    """Firma EdDSA, emisor, `aud`, `jti` presente y vencimiento. -> la carga o None. (= `portero.comprobar_pase`;
    el `jti` repetido lo mira `verificar_pase`.)"""
    try:
        a, b, c = pase.split(".")
        cab = json.loads(_de_b64u(a))
        carga = json.loads(_de_b64u(b))
        if cab.get("alg") != "EdDSA" or not ed.verificar(pub, f"{a}.{b}".encode("ascii"), _de_b64u(c)):
            return None
    except (ValueError, TypeError, AttributeError):
        return None
    ahora = time.time() if ahora is None else ahora
    if not isinstance(carga, dict) or carga.get("iss") != EMISOR or carga.get("aud") != juego or not carga.get("jti"):
        return None
    if not isinstance(carga.get("exp"), int) or carga["exp"] + tolerancia < ahora:
        return None
    return carga


def verificar_pase(pase_txt, aud, ahora=None, tolerancia=0):
    """Comprueba firma Ed25519, `aud`, vencimiento (`exp`), `sub` entero positivo y uso único (`jti`).
    -> el dict de la carga si el pase vale, o `None` si rebota."""
    if not isinstance(pase_txt, str) or not pase_txt or not aud:
        return None
    pub = clave_publica()
    if not pub:
        return None
    ahora_i = int(time.time() if ahora is None else ahora)
    carga = comprobar_firma(pase_txt, pub, aud, ahora=ahora_i, tolerancia=tolerancia)
    if not carga:
        return None
    try:
        uid = int(carga.get("sub"))
    except (TypeError, ValueError):
        return None
    if uid <= 0:
        return None
    jti = str(carga.get("jti") or "")
    if not jti:
        return None
    vence = int(carga["exp"]) + max(0, int(tolerancia))
    with _lock:
        if _usados:
            for k in [k for k, exp_k in _usados.items() if exp_k < ahora_i]:
                del _usados[k]
        if jti in _usados:
            return None
        if len(_usados) >= MAX_PASES_RECORDADOS:
            del _usados[min(_usados, key=_usados.get)]
        _usados[jti] = vence
    return carga


def nombre_usuario_interno(uid, ahora=None, timeout=2.0):
    """Consulta a Cuenta Eñeños el nombre de `uid` para mostrárselo al ADMIN en el panel (`R2_CUENTAS_URL` +
    `R2_CUENTAS_FICHA_INTERNA`), con caché en memoria. Si no está configurado o no contesta, devuelve `str(uid)`."""
    try:
        u_int = int(uid)
    except (TypeError, ValueError):
        return str(uid or "")
    url = (os.environ.get("R2_CUENTAS_URL") or "").strip().rstrip("/")
    ficha = (os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip()
    if not url or not ficha:
        return str(u_int)
    ahora_f = float(time.time() if ahora is None else ahora)
    clave = (url, ficha, u_int)
    with _lock:
        hit = _cache_nombres.get(clave)
        if hit and ahora_f - hit[0] < CACHE_NOMBRES_TTL:
            return hit[1]
    for ruta in _rutas_cuenta(url, f"/interno/cuenta/{u_int}"):
        try:
            req = urllib.request.Request(
                ruta,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {ficha}",
                    "X-Ficha-Interna": ficha,
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    continue
                d = json.loads(r.read().decode("utf-8"))
                nombre = str(d.get("usuario") or "").strip()
                if nombre:
                    with _lock:
                        if len(_cache_nombres) >= MAX_NOMBRES_CACHE:
                            _cache_nombres.clear()
                        _cache_nombres[clave] = (ahora_f, nombre)
                    return nombre
        except Exception:                                                # noqa: BLE001
            continue
    return str(u_int)


def _pedido_interno(metodo, sufijo, cuerpo=None, timeout=2.0):
    """Habla con un pedido `/interno/...` de Cuenta Eñeños (`R2_CUENTAS_URL` + `R2_CUENTAS_FICHA_INTERNA`).
    Devuelve `{"estado": "ok" | "rechazado" | "sin_respuesta", "datos": dict | None, "error": str, "codigo": int}`."""
    url = (os.environ.get("R2_CUENTAS_URL") or "").strip().rstrip("/")
    ficha = (os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip()
    if not url or not ficha:
        return {"estado": "sin_respuesta", "datos": None, "codigo": 0,
                "error": "Cuenta Eñeños no está configurado (R2_CUENTAS_URL / R2_CUENTAS_FICHA_INTERNA)."}
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {ficha}",
        "X-Ficha-Interna": ficha,
    }
    data = None
    if metodo == "POST":
        headers["Content-Type"] = "application/json; charset=utf-8"
        headers["X-R2"] = "1"
        data = json.dumps(cuerpo or {}, ensure_ascii=False).encode("utf-8")
    ultimo_err = "No pude comunicarme con Cuenta Eñeños."
    rechazo = None
    for ruta in _rutas_cuenta(url, sufijo):
        try:
            req = urllib.request.Request(ruta, data=data, headers=headers, method=metodo)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8") or "{}")
                if r.status == 200:
                    return {"estado": "ok", "datos": d, "error": "", "codigo": 200}
                ultimo_err = str((d or {}).get("error") or f"HTTP {r.status}")
                return {"estado": "rechazado", "datos": d, "error": ultimo_err, "codigo": int(r.status)}
        except urllib.error.HTTPError as e:
            cuerpo_err = b""
            try:
                cuerpo_err = e.read()
            except Exception:                                            # noqa: BLE001
                pass
            if e.code >= 500:
                ultimo_err = f"HTTP {e.code}"
                continue
            try:
                d = json.loads(cuerpo_err.decode("utf-8") or "{}")
                msg = str(d.get("error") or f"HTTP {e.code}")
            except Exception:                                            # noqa: BLE001
                d, msg = None, f"HTTP {e.code}"
            rechazo = {"estado": "rechazado", "datos": d, "error": msg, "codigo": int(e.code)}
            if e.code == 404 and msg == "no existe":
                continue                                                 # probar con/sin el prefijo /cuentas
            return rechazo
        except Exception as e:                                           # noqa: BLE001
            ultimo_err = str(e) or repr(e)
            continue
    return rechazo or {"estado": "sin_respuesta", "datos": None, "error": ultimo_err, "codigo": 0}


def _uid_positivo(uid):
    if isinstance(uid, bool):
        return None
    try:
        u_int = int(uid)
    except (TypeError, ValueError):
        return None
    return u_int if u_int > 0 else None


def _cuenta_invalida():
    return {"estado": "rechazado", "datos": None, "error": "Cuenta inválida.", "codigo": 400}


def cuenta_interna(uid, timeout=2.0):
    """GET `/cuentas/interno/cuenta/<uid>` -> `{estado, datos, error, codigo}`."""
    u_int = _uid_positivo(uid)
    if u_int is None:
        return _cuenta_invalida()
    return _pedido_interno("GET", f"/interno/cuenta/{u_int}", timeout=timeout)


def buscar_usuario_interno(usuario, timeout=2.0):
    """GET `/cuentas/interno/usuario/<usuario>` (exacto) -> `{estado, datos, error, codigo}`."""
    u = str(usuario or "").strip()
    if not u:
        return {"estado": "rechazado", "datos": None, "error": "Usuario vacío.", "codigo": 400}
    return _pedido_interno("GET", f"/interno/usuario/{urllib.parse.quote(u, safe='')}", timeout=timeout)


def poner_estado_interno(uid, estado, motivo="", timeout=2.0):
    """POST `/cuentas/interno/cuenta/<uid>/estado` `{estado, motivo}` -> `{estado, datos, error, codigo}`."""
    u_int = _uid_positivo(uid)
    if u_int is None:
        return _cuenta_invalida()
    return _pedido_interno("POST", f"/interno/cuenta/{u_int}/estado",
                           {"estado": str(estado or "").strip().lower(), "motivo": str(motivo or "")},
                           timeout=timeout)


def poner_clave_interna(uid, pass_sha256_upper, timeout=2.0):
    """POST `/cuentas/interno/cuenta/<uid>/clave` `{pass_sha256_upper}` -> `{estado, datos, error, codigo}`."""
    u_int = _uid_positivo(uid)
    if u_int is None:
        return _cuenta_invalida()
    return _pedido_interno("POST", f"/interno/cuenta/{u_int}/clave",
                           {"pass_sha256_upper": str(pass_sha256_upper or "").strip().upper()},
                           timeout=timeout)


def comprobar_clave_interna(uid, pass_sha256_upper, timeout=3.0):
    """POST `/cuentas/interno/cuenta/<uid>/comprobar-clave` -> `{estado, datos, error, codigo}`.
    `estado == "ok"`: es la contraseña de esa cuenta. `"rechazado"`: no (o hay freno: `codigo == 429`).
    `"sin_respuesta"`: Cuenta Eñeños no contestó (no se sabe: NO es un «sí»)."""
    u_int = _uid_positivo(uid)
    if u_int is None:
        return _cuenta_invalida()
    return _pedido_interno("POST", f"/interno/cuenta/{u_int}/comprobar-clave",
                           {"pass_sha256_upper": str(pass_sha256_upper or "").strip().upper()},
                           timeout=timeout)


def enlaces_internos(timeout=5.0):
    """GET `/cuentas/interno/enlaces` -> `{estado, datos: {"cuentas": [{usuario, uid}]}, error, codigo}`."""
    return _pedido_interno("GET", "/interno/enlaces", timeout=timeout)


def crear_cuenta_interna(usuario, pass_sha256_upper, timeout=2.0):
    """POST `/cuentas/interno/cuenta` `{usuario, pass_sha256_upper}` -> `{estado, datos: {uid, usuario, estado}, error, codigo}`."""
    return _pedido_interno("POST", "/interno/cuenta", {
        "usuario": str(usuario or "").strip(),
        "pass_sha256_upper": str(pass_sha256_upper or "").strip().upper(),
    }, timeout=timeout)


def limpiar_usados():
    """Vacía la memoria de pases ya usados (para pruebas)."""
    with _lock:
        _usados.clear()


def limpiar_cache_nombres():
    """Vacía la caché de nombres consultados a Cuenta Eñeños (para pruebas)."""
    with _lock:
        _cache_nombres.clear()


def reiniciar():
    """Limpia clave en memoria, pases usados y caché de nombres (para pruebas)."""
    global _clave_pub, _clave_env_vista, _url_intentada, _aviso_sin_clave
    with _lock:
        _clave_pub = None
        _clave_env_vista = None
        _url_intentada = None
        _aviso_sin_clave = False
        _usados.clear()
        _cache_nombres.clear()
