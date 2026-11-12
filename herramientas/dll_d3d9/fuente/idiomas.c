/* idiomas.c — (126) chino, coreano y español en el MISMO juego, con cualquier Windows (28-oct-2026, IDIOMAS.md)
 *
 * ★ POR QUÉ: el exe no elige ninguna página de códigos. Cada texto que dibuja pasa por
 *   `MultiByteToWideChar(CP_ACP, …)` (31 llamadas, casi todas con 0 = «la de este Windows») y por Verdana
 *   con ANSI_CHARSET (`0x5300F0` devuelve 0: los que lo tradujeron apagaron la elección). O sea que el MISMO
 *   byte se lee distinto en cada PC: en un Windows en español (1252) «¡» es A1, en el de anonimo03 (949, coreano)
 *   A1 es la mitad de un hangul. Y el catálogo de música ya está mezclado: hay títulos en 1252, en 949 y en
 *   GBK. Ningún jugador los ve todos bien.
 *
 * ★ LA REGLA (la nuestra): los bytes del juego se leen como **UTF-8 si lo son**, y si no como **1252**.
 *   - UTF-8 tiene TODO (chino, coreano, japonés, Δ, ♪, ∶) ⇒ lo nuevo se escribe en UTF-8.
 *   - Lo viejo sigue andando: un texto en 1252 con «ñ» o «á» casi nunca es UTF-8 válido (F1 suelto no lo es).
 *   - Al revés (lo que el juego ESCRIBE: lo tipeado, el chat, el apodo) va en **1252 si entra**, y si no en UTF-8.
 *     Así el server de hoy —que habla 1252— recibe lo de siempre, y sólo lo que no entra viaja en UTF-8.
 *   - Un texto cortado por bytes (`[:30]` del server, el globo del chat) puede dejar media letra al final o al
 *     principio: se descarta esa media letra, SIEMPRE que haya al menos una letra UTF-8 entera (si no, «PERÚ»
 *     —DA al final— perdería la Ú).
 *
 * ★ CÓMO: la tabla de importaciones del exe (lo mismo que `Sleep` y `ChangeDisplaySettingsA`): no se escribe
 *   una sola instrucción. Se cambian SÓLO los pedidos con página 0 (CP_ACP) o 3 (CP_THREAD_ACP) que vienen del
 *   código del JUEGO (`0x401000..0x74F000`) o del D3DX que trae adentro (`0x78E000..0x792000`: el `DrawText` del
 *   ID3DXFont es `0x79060F` y convierte en `0x7906A4`/`0x7906D8` — MEDIDO el 28-oct: sin este tramo el título de la
 *   sala «¡Bienvenido!» salía «좲ienvenido!» y «Ítem» «?em»). El CRT y lo demás siguen con la de Windows (rutas).
 *   Las de GDI con «A» (medir, cortar, escribir) pasan a sus «W» con la misma regla: así el ancho medido es el
 *   del texto que se ve, y el corte por bytes cae entre dos letras.
 *
 *   [idiomas] activo=0 lo apaga entero · diag=1 anota en el log quién convierte textos con letras de más de 127.
 */

#ifndef ID_JUEGO_DESDE                /* el banco (`banco/banco_idiomas.c`) los cambia: allá el «juego» es él mismo */
#define ID_JUEGO_DESDE 0x401000u
#define ID_JUEGO_HASTA 0x74F000u      /* desde acá empieza el CRT (0x74F8E6 delete, 0x74FF1F _invalid_parameter) */
#define ID_D3DX_DESDE  0x78E000u      /* el D3DX enlazado en el exe: LOGFONTA->W (0x78E88A) y DrawTextA (0x7906A4/D8) */
#define ID_D3DX_HASTA  0x792000u
#endif
#define ID_PILA        1024           /* letras que se convierten sin pedir memoria */

typedef int  (WINAPI *ID_MB2WC)(UINT, DWORD, LPCSTR, int, LPWSTR, int);
typedef int  (WINAPI *ID_WC2MB)(UINT, DWORD, LPCWSTR, int, LPSTR, int, LPCSTR, LPBOOL);
typedef BOOL (WINAPI *ID_MEDIR)(HDC, LPCSTR, int, LPSIZE);
typedef BOOL (WINAPI *ID_MEDIREX)(HDC, LPCSTR, int, int, LPINT, LPINT, LPSIZE);
typedef BOOL (WINAPI *ID_ESCRIBIR)(HDC, int, int, UINT, const RECT *, LPCSTR, UINT, const INT *);

static int g_id_activo = 1;
static int g_id_diag = 0;
static int g_id_diag_n = 0;
static int g_id_diag_letras = 0;
static ID_MB2WC g_id_mb2wc;      /* las de kernel32/gdi32 DE VERDAD, tomadas antes de tocar la tabla */
static ID_WC2MB g_id_wc2mb;
static ID_MEDIR g_id_medir;
static ID_MEDIREX g_id_medirex;
static ID_ESCRIBIR g_id_escribir;

/* ── ¿estos bytes son UTF-8? ───────────────────────────────────────────────────────────────────
 * 1 = sí. `*ini`/`*fin`: lo que se lee (sin la media letra del principio ni la del final).
 * ⚠ Las reglas de validez son las del estándar (sin sobrelargas ni sustitutos): un 1252 con «Ã»
 *   seguido de un símbolo podría pasar por UTF-8, y cuanto más estricto, menos pasa. */
static int id_es_utf8(const BYTE *s, int n, int *ini, int *fin)
{
    int i = 0, enteras = 0, cortada = 0;
    while (i < n && i < 3 && (s[i] & 0xC0) == 0x80) i++;             /* media letra al principio */
    *ini = i;
    *fin = n;
    while (i < n) {
        BYTE c = s[i];
        if (c < 0x80) { i++; continue; }
        int k;
        BYTE lo = 0x80, hi = 0xBF;                                    /* el rango del 2.º byte */
        if (c >= 0xC2 && c <= 0xDF) k = 1;
        else if (c >= 0xE0 && c <= 0xEF) { k = 2; if (c == 0xE0) lo = 0xA0; if (c == 0xED) hi = 0x9F; }
        else if (c >= 0xF0 && c <= 0xF4) { k = 3; if (c == 0xF0) lo = 0x90; if (c == 0xF4) hi = 0x8F; }
        else return 0;
        int j;
        for (j = 1; j <= k; j++) {
            if (i + j >= n) { cortada = 1; break; }                    /* se acabó el texto: media letra al final */
            BYTE t = s[i + j];
            if (j == 1 ? (t < lo || t > hi) : ((t & 0xC0) != 0x80)) return 0;
        }
        if (cortada) { *fin = i; break; }
        enteras++;
        i += k + 1;
    }
    return enteras > 0;
}

/* ── bytes del juego -> UTF-16 ─────────────────────────────────────────────────────────────────
 * Devuelve las WCHAR escritas (cap suficiente: nunca hay más WCHAR que bytes).
 * `fin_de`[w] (si no es NULL) = el byte donde TERMINA la letra w: para devolverle al juego medidas en bytes. */
static int id_leer(const BYTE *s, int n, WCHAR *w, int *fin_de)
{
    int ini, fin, nw = 0;
    if (n <= 0) return 0;
    if (!id_es_utf8(s, n, &ini, &fin)) {
        nw = g_id_mb2wc(1252, 0, (LPCSTR)s, n, w, n);
        if (fin_de) { int k; for (k = 0; k < nw; k++) fin_de[k] = k + 1; }
        return nw;
    }
    int i = ini;
    while (i < fin) {
        BYTE c = s[i];
        UINT cp;
        int k;
        if (c < 0x80) { cp = c; k = 0; }
        else if (c < 0xE0) { cp = c & 0x1F; k = 1; }
        else if (c < 0xF0) { cp = c & 0x0F; k = 2; }
        else { cp = c & 0x07; k = 3; }
        int j;
        for (j = 1; j <= k; j++) cp = (cp << 6) | (s[i + j] & 0x3F);
        i += k + 1;
        if (cp >= 0x10000) {                                           /* fuera del plano básico: dos WCHAR */
            cp -= 0x10000;
            w[nw] = (WCHAR)(0xD800 + (cp >> 10));
            if (fin_de) fin_de[nw] = i;
            nw++;
            w[nw] = (WCHAR)(0xDC00 + (cp & 0x3FF));
        } else {
            w[nw] = (WCHAR)cp;
        }
        if (fin_de) fin_de[nw] = i;
        nw++;
    }
    return nw;
}

/* ★ Para los módulos de ESTA dll que dibujan con GDI (TOP 5, el cartel de 12, el selector, los estilos de letra):
 *   el mismo contrato que `MultiByteToWideChar(pág, 0, s, -1, w, cap)` —devuelve las WCHAR con el 0 final, 0 si no
 *   hay nada— pero con la regla del juego (UTF-8 o 1252). Antes usaban 1252 (o 949) fijo: «Δ-VoID» salía «ï¿-VoID»
 *   en el título de la ventana TOP 5 (28-oct). Anda aunque [idiomas] esté apagado (va directo a kernel32). */
static int id_a_ancho(const char *s, WCHAR *w, int cap)
{
    if (!s || !w || cap < 2) return 0;
    int n = lstrlenA(s);
    if (n > cap - 1) n = cap - 1;                       /* nunca hay más WCHAR que bytes */
    if (!g_id_mb2wc) g_id_mb2wc = (ID_MB2WC)GetProcAddress(GetModuleHandleA("kernel32.dll"), "MultiByteToWideChar");
    int nw = id_leer((const BYTE *)s, n, w, NULL);
    w[nw] = 0;
    return nw + 1;
}

/* ¿hay algún byte de más de 127? Si no, no hay nada que decidir: va directo (y no cuesta nada). */
static int id_hay_altas(const char *s, int n)
{
    int i;
    for (i = 0; n < 0 ? s[i] != 0 : i < n; i++)
        if ((BYTE)s[i] >= 0x80) return 1;
    return 0;
}

static int id_del_juego(void *volver)
{
    DWORD a = (DWORD)volver;
    return (a >= ID_JUEGO_DESDE && a < ID_JUEGO_HASTA) || (a >= ID_D3DX_DESDE && a < ID_D3DX_HASTA);
}

/* diag=1: quién convierte qué (sólo los textos con letras altas, los primeros 300). Va en ASCII: el log se lee
 * desde una consola en cp949 y un byte raro la rompe. */
static void id_anotar(const char *que, void *volver, const BYTE *s, int n, int cambio)
{
    if (!g_id_diag || g_id_diag_n >= 300) return;
    char hex[3 * 40 + 1];
    int i, m = n < 0 ? lstrlenA((const char *)s) : n;
    if (m > 40) m = 40;
    for (i = 0; i < m; i++) wsprintfA(hex + 3 * i, "%02X ", s[i]);
    hex[3 * m] = 0;
    g_id_diag_n++;
    apuntar("  [idiomas] %s desde 0x%08lX (%d B)%s: %s", que, (unsigned long)(DWORD)volver, n,
            cambio ? "" : " SIN TOCAR", hex);
}

/* ── MultiByteToWideChar del juego ─────────────────────────────────────────────────────────────── */
static int WINAPI id_mb2wc(UINT pag, DWORD banderas, LPCSTR s, int n, LPWSTR w, int cap)
{
    void *volver = __builtin_return_address(0);
    if (!g_id_activo || (pag != CP_ACP && pag != CP_THREAD_ACP) || !s || n == 0 || !id_hay_altas(s, n)) {
        return g_id_mb2wc(pag, banderas, s, n, w, cap);
    }
    int mio = id_del_juego(volver);
    id_anotar("MB->W", volver, (const BYTE *)s, n, mio);
    if (!mio) return g_id_mb2wc(pag, banderas, s, n, w, cap);

    int largo = n < 0 ? lstrlenA(s) + 1 : n;                           /* -1 = con el 0 del final */
    int cero = largo > 0 && s[largo - 1] == 0;
    int util = cero ? largo - 1 : largo;
    WCHAR pila[ID_PILA], *tmp = util + 1 <= ID_PILA ? pila : (WCHAR *)HeapAlloc(GetProcessHeap(), 0, (util + 1) * sizeof(WCHAR));
    if (!tmp) return g_id_mb2wc(pag, banderas, s, n, w, cap);
    int nw = id_leer((const BYTE *)s, util, tmp, NULL);
    if (cero) tmp[nw++] = 0;
    int r;
    if (cap == 0) r = nw;                                              /* sólo pregunta cuánto mide */
    else if (cap < nw) { SetLastError(ERROR_INSUFFICIENT_BUFFER); r = 0; }
    else { CopyMemory(w, tmp, nw * sizeof(WCHAR)); r = nw; }
    if (tmp != pila) HeapFree(GetProcessHeap(), 0, tmp);
    return r;
}

/* ── WideCharToMultiByte del juego: 1252 si entra, UTF-8 si no ─────────────────────────────────── */
static int WINAPI id_wc2mb(UINT pag, DWORD banderas, LPCWSTR w, int n, LPSTR s, int cap,
                           LPCSTR por_defecto, LPBOOL uso_defecto)
{
    void *volver = __builtin_return_address(0);
    if (!g_id_activo || (pag != CP_ACP && pag != CP_THREAD_ACP) || !w || n == 0 || !id_del_juego(volver))
        return g_id_wc2mb(pag, banderas, w, n, s, cap, por_defecto, uso_defecto);
    BOOL falta = FALSE;
    g_id_wc2mb(1252, WC_NO_BEST_FIT_CHARS, w, n, NULL, 0, NULL, &falta);
    if (!falta) return g_id_wc2mb(1252, banderas, w, n, s, cap, por_defecto, uso_defecto);
    if (uso_defecto) *uso_defecto = FALSE;
    int r = g_id_wc2mb(CP_UTF8, 0, w, n, s, cap, NULL, NULL);
    if (g_id_diag && g_id_diag_n < 300 && r > 0 && s && cap) id_anotar("W->MB utf8", volver, (const BYTE *)s, r, 1);
    return r;
}

/* ── GDI: medir y escribir con la misma regla ──────────────────────────────────────────────────── */
static BOOL WINAPI id_medir(HDC dc, LPCSTR s, int n, LPSIZE sz)
{
    if (!g_id_activo || !s || n <= 0 || n > ID_PILA || !id_hay_altas(s, n)) return g_id_medir(dc, s, n, sz);
    WCHAR w[ID_PILA];
    int nw = id_leer((const BYTE *)s, n, w, NULL);
    return GetTextExtentPoint32W(dc, w, nw, sz);
}

/* El «cuánto entra en tanto ancho» que usa el juego para cortar (el globo del chat, `0x441A96`, `0x636424`):
 * las cuentas vuelven en BYTES, como espera el juego, y caen siempre entre dos letras. */
static BOOL WINAPI id_medirex(HDC dc, LPCSTR s, int n, int maximo, LPINT entran, LPINT pasos, LPSIZE sz)
{
    if (!g_id_activo || !s || n <= 0 || n > ID_PILA || !id_hay_altas(s, n))
        return g_id_medirex(dc, s, n, maximo, entran, pasos, sz);
    WCHAR w[ID_PILA];
    int fin_de[ID_PILA], pw[ID_PILA], ew = 0;
    int nw = id_leer((const BYTE *)s, n, w, fin_de);
    if (!GetTextExtentExPointW(dc, w, nw, maximo, entran ? &ew : NULL, pasos ? pw : NULL, sz)) return FALSE;
    if (entran) {
        while (ew > 0 && ew < nw && (w[ew] & 0xFC00) == 0xDC00) ew--;   /* no partir un par sustituto */
        *entran = ew > 0 ? fin_de[ew - 1] : 0;
    }
    if (pasos) {
        int b = 0, k;
        for (k = 0; k < nw; k++)
            for (; b < fin_de[k] && b < n; b++) pasos[b] = pw[k];
        for (; b < n; b++) pasos[b] = nw ? pw[nw - 1] : 0;
    }
    return TRUE;
}

static BOOL WINAPI id_escribir(HDC dc, int x, int y, UINT op, const RECT *rc, LPCSTR s, UINT n, const INT *dx)
{
    if (!g_id_activo || (op & ETO_GLYPH_INDEX) || !s || n == 0 || n > ID_PILA || !id_hay_altas(s, (int)n))
        return g_id_escribir(dc, x, y, op, rc, s, n, dx);
    WCHAR w[ID_PILA];
    int fin_de[ID_PILA], dw[ID_PILA];
    int nw = id_leer((const BYTE *)s, (int)n, w, fin_de);
    if (dx) {                                                          /* el paso de cada letra = la suma de sus bytes */
        int b = 0, k;
        for (k = 0; k < nw; k++) {
            dw[k] = 0;
            for (; b < fin_de[k]; b++) dw[k] += dx[b];
        }
    }
    return ExtTextOutW(dc, x, y, op, rc, w, (UINT)nw, dx ? dw : NULL);
}

/* ═══ LA LETRA DE RESPALDO ═════════════════════════════════════════════════════════════════════════
 * ★ POR QUÉ (medido el 28-oct en el picker, con la lectura ya andando): lo que Verdana no tiene sale en CUADRITO —
 *   «Sub-bass Boom□» (！), «□SixOneNine» (こ), «Spring Camp (□□)» (春游), «Time:2□□□» (分秒).
 * ★ DÓNDE (medido con Frida, no deducido — la 1.ª idea, el «número de glifo», era FALSA y se tiró): el D3DX del exe
 *   arma cada letra nueva con UNISCRIBE, que carga solo con `GetProcAddress(usp10, …)` y guarda en .data:
 *       [0xA093F8] ScriptStringAnalyse  ·  [0xA093FC] ScriptStringOut  ·  [0xA09408] ScriptString_pSize
 *       [0xA09400] ScriptStringFree
 *   Analiza la letra suelta con `SSA_GLYPHS | SSA_FALLBACK | SSA_LINK` (0x10A0, en 0x7902E2), la mide (pSize) y la
 *   dibuja (Out, 0x790393). El respaldo de Uniscribe para chino/coreano/japonés sale de las letras ENLAZADAS a la
 *   fuente en el registro (FontLink\SystemLink): Tahoma y Segoe UI las tienen, **Verdana no** ⇒ cuadrito.
 * ★ CÓMO: cuando el D3DX pide esas cuatro a `GetProcAddress`, se le dan las nuestras. Si la letra analizada tiene algo
 *   que la fuente del DC no trae, se anota (DC, texto, medida con la de respaldo); al medir se da esa medida y al
 *   dibujar se dibuja con la de respaldo (mismo alto y grosor, línea de base alineada con la del juego). Lo demás va
 *   directo a Uniscribe: lo latino sigue siendo Verdana, píxel por píxel. Ni registro ni otra fuente para todo el juego.
 * Las de respaldo, en orden (la primera que TENGA la letra): hangul, hanzi, kana, y símbolos. */
static const WCHAR *const g_id_respaldo[] = {
    L"Malgun Gothic", L"Microsoft YaHei", L"Yu Gothic", L"MS Gothic", L"Gulim", L"SimSun",
    L"Segoe UI Symbol", L"Segoe UI", L"Arial Unicode MS",
};
#define ID_NRESPALDO ((int)(sizeof(g_id_respaldo) / sizeof(g_id_respaldo[0])))

static BYTE g_id_de_letra[65536];          /* letra -> 1 + respaldo que la tiene (0 = no se buscó, 0xFF = ninguna) */
static CRITICAL_SECTION g_id_cs;

/* La de respaldo `cual`, del mismo alto/grosor/calidad que la que tiene el DC. Se guardan las últimas 16. */
static HFONT id_respaldo_para(HDC dc, int cual)
{
    /* ⚠ la clave lleva alto y grosor, no sólo el HFONT: si el D3DX borra una fuente, Windows reusa el número */
    static struct { HFONT base; LONG alto, grosor; int cual; HFONT f; } cache[16];
    static int prox = 0;
    HFONT base = (HFONT)GetCurrentObject(dc, OBJ_FONT);
    LOGFONTW lf;
    if (!base || !GetObjectW(base, sizeof(lf), &lf)) return NULL;
    int i;
    for (i = 0; i < 16; i++)
        if (cache[i].f && cache[i].base == base && cache[i].cual == cual && cache[i].alto == lf.lfHeight
            && cache[i].grosor == lf.lfWeight) return cache[i].f;
    lstrcpynW(lf.lfFaceName, g_id_respaldo[cual], LF_FACESIZE);
    lf.lfCharSet = DEFAULT_CHARSET;
    HFONT f = CreateFontIndirectW(&lf);
    if (!f) return NULL;
    if (cache[prox].f) DeleteObject(cache[prox].f);
    cache[prox].base = base;
    cache[prox].alto = lf.lfHeight;
    cache[prox].grosor = lf.lfWeight;
    cache[prox].cual = cual;
    cache[prox].f = f;
    prox = (prox + 1) % 16;
    return f;
}

/* La de respaldo para la letra `c` (-1 si ninguna la tiene). `dc` tiene puesta la letra del juego. */
static int id_respaldo_de(HDC dc, WCHAR c)
{
    BYTE b = g_id_de_letra[c];
    if (b) return b == 0xFF ? -1 : b - 1;
    int r, cual = -1;
    for (r = 0; r < ID_NRESPALDO; r++) {
        HFONT f = id_respaldo_para(dc, r);
        if (!f) continue;
        HGDIOBJ vieja = SelectObject(dc, f);
        WORD g = 0xFFFF;
        /* ⚠ NO se compara el nombre: en un Windows coreano «Malgun Gothic» se llama «맑은 고딕» (medido el 28-oct, la
         *   descartaba siempre). Si no está instalada Windows pone otra, y si ESA tiene la letra, sirve igual. */
        GetGlyphIndicesW(dc, &c, 1, &g, GGI_MARK_NONEXISTING_GLYPHS);
        SelectObject(dc, vieja);
        if (g != 0xFFFF) { cual = r; break; }
    }
    g_id_de_letra[c] = cual < 0 ? 0xFF : (BYTE)(cual + 1);
    if (g_id_diag && g_id_diag_letras < 200) {                /* su propio contador: las conversiones gastan el otro */
        g_id_diag_letras++;
        apuntar("  [idiomas] letra U+%04X -> respaldo %d", (unsigned)c, cual);
    }
    return cual;
}

/* ── Uniscribe del D3DX ───────────────────────────────────────────────────────────────────────────── */
typedef HRESULT (WINAPI *ID_SSANALIZAR)(HDC, const void *, int, int, int, DWORD, int, void *, void *, const int *,
                                        void *, const BYTE *, void **);
typedef HRESULT (WINAPI *ID_SSDIBUJAR)(void *, int, int, UINT, const RECT *, int, int, BOOL);
typedef const SIZE *(WINAPI *ID_SSMEDIDA)(void *);
typedef HRESULT (WINAPI *ID_SSLIBERAR)(void **);
typedef FARPROC (WINAPI *ID_PEDIR)(HMODULE, LPCSTR);
static ID_SSANALIZAR g_id_ss_analizar;
static ID_SSDIBUJAR g_id_ss_dibujar;
static ID_SSMEDIDA g_id_ss_medida;
static ID_SSLIBERAR g_id_ss_liberar;
static ID_PEDIR g_id_pedir;

#define ID_ANOTADAS 32
#define ID_LETRAS   16
static struct {
    void *ssa;                     /* el análisis de Uniscribe que es nuestro (NULL = libre) */
    HDC dc;
    int n;
    WCHAR letra[ID_LETRAS];
    signed char cual[ID_LETRAS];   /* -1 = la del juego */
    SIZE medida;
} g_id_anot[ID_ANOTADAS];

static int id_anotada(void *ssa)
{
    int i;
    for (i = 0; i < ID_ANOTADAS; i++) if (g_id_anot[i].ssa == ssa) return i;
    return -1;
}

static HRESULT WINAPI id_ss_analizar(HDC dc, const void *s, int n, int glifos, int juego, DWORD banderas, int ancho,
                                     void *ctl, void *est, const int *dx, void *tab, const BYTE *clase, void **ssa)
{
    HRESULT r = g_id_ss_analizar(dc, s, n, glifos, juego, banderas, ancho, ctl, est, dx, tab, clase, ssa);
    /* juego -1 = el texto viene en WCHAR (es lo que pide el D3DX) */
    if (!g_id_activo || r != S_OK || juego != -1 || !s || n <= 0 || n > ID_LETRAS || !ssa || !*ssa) return r;
    const WCHAR *w = (const WCHAR *)s;
    WORD g[ID_LETRAS];
    if (GetGlyphIndicesW(dc, w, n, g, GGI_MARK_NONEXISTING_GLYPHS) == GDI_ERROR) return r;
    int i, falta = 0;
    for (i = 0; i < n; i++) if (g[i] == 0xFFFF && w[i] >= 0x80 && (w[i] & 0xF800) != 0xD800) falta = 1;
    if (!falta) return r;
    EnterCriticalSection(&g_id_cs);
    int k = id_anotada(NULL);                                  /* un lugar libre */
    if (k >= 0) {
        TEXTMETRICW tm;
        GetTextMetricsW(dc, &tm);
        g_id_anot[k].ssa = *ssa;
        g_id_anot[k].dc = dc;
        g_id_anot[k].n = n;
        g_id_anot[k].medida.cx = 0;
        g_id_anot[k].medida.cy = tm.tmHeight;
        for (i = 0; i < n; i++) {
            int cual = (g[i] == 0xFFFF && w[i] >= 0x80) ? id_respaldo_de(dc, w[i]) : -1;
            HGDIOBJ vieja = cual >= 0 ? SelectObject(dc, id_respaldo_para(dc, cual)) : NULL;
            SIZE sz = {0, 0};
            GetTextExtentPoint32W(dc, &w[i], 1, &sz);
            if (vieja) SelectObject(dc, vieja);
            g_id_anot[k].letra[i] = w[i];
            g_id_anot[k].cual[i] = (signed char)cual;
            g_id_anot[k].medida.cx += sz.cx;
        }
    }
    LeaveCriticalSection(&g_id_cs);
    return r;
}

static HRESULT WINAPI id_ss_dibujar(void *ssa, int x, int y, UINT op, const RECT *rc, int sel0, int sel1, BOOL apagado)
{
    EnterCriticalSection(&g_id_cs);
    int k = (g_id_activo && ssa) ? id_anotada(ssa) : -1;
    if (k < 0) {
        LeaveCriticalSection(&g_id_cs);
        return g_id_ss_dibujar(ssa, x, y, op, rc, sel0, sel1, apagado);
    }
    HDC dc = g_id_anot[k].dc;
    TEXTMETRICW base;
    GetTextMetricsW(dc, &base);
    int i;
    for (i = 0; i < g_id_anot[k].n; i++) {
        WCHAR c = g_id_anot[k].letra[i];
        int cual = g_id_anot[k].cual[i], yy = y;
        HGDIOBJ vieja = NULL;
        if (cual >= 0) {
            vieja = SelectObject(dc, id_respaldo_para(dc, cual));
            TEXTMETRICW tm;
            if (GetTextMetricsW(dc, &tm)) yy += base.tmAscent - tm.tmAscent;   /* la misma línea de base */
        }
        SIZE sz = {0, 0};
        GetTextExtentPoint32W(dc, &c, 1, &sz);
        ExtTextOutW(dc, x, yy, op & ETO_OPAQUE, i == 0 ? rc : NULL, &c, 1, NULL);
        if (vieja) SelectObject(dc, vieja);
        x += sz.cx;
    }
    LeaveCriticalSection(&g_id_cs);
    return S_OK;
}

static const SIZE *WINAPI id_ss_medida(void *ssa)
{
    EnterCriticalSection(&g_id_cs);
    int k = (g_id_activo && ssa) ? id_anotada(ssa) : -1;
    const SIZE *r = k >= 0 ? &g_id_anot[k].medida : NULL;
    LeaveCriticalSection(&g_id_cs);
    return r ? r : g_id_ss_medida(ssa);
}

static HRESULT WINAPI id_ss_liberar(void **ssa)
{
    if (ssa && *ssa) {
        EnterCriticalSection(&g_id_cs);
        int k = id_anotada(*ssa);
        if (k >= 0) g_id_anot[k].ssa = NULL;
        LeaveCriticalSection(&g_id_cs);
    }
    return g_id_ss_liberar(ssa);
}

/* GetProcAddress del exe: las cuatro de Uniscribe que el D3DX pide (0x78F0xx), se le dan las nuestras. */
static FARPROC WINAPI id_pedir(HMODULE m, LPCSTR nombre)
{
    FARPROC f = g_id_pedir(m, nombre);
    if (!g_id_activo || !f || !nombre || !HIWORD((DWORD)nombre)) return f;
    if (!lstrcmpA(nombre, "ScriptStringAnalyse")) { g_id_ss_analizar = (ID_SSANALIZAR)f; return (FARPROC)id_ss_analizar; }
    if (!lstrcmpA(nombre, "ScriptStringOut"))     { g_id_ss_dibujar = (ID_SSDIBUJAR)f;   return (FARPROC)id_ss_dibujar; }
    if (!lstrcmpA(nombre, "ScriptString_pSize"))  { g_id_ss_medida = (ID_SSMEDIDA)f;     return (FARPROC)id_ss_medida; }
    if (!lstrcmpA(nombre, "ScriptStringFree"))    { g_id_ss_liberar = (ID_SSLIBERAR)f;   return (FARPROC)id_ss_liberar; }
    return f;
}

static void idiomas_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_id_activo = (int)GetPrivateProfileIntA("idiomas", "activo", 1, ini);
    g_id_diag = (int)GetPrivateProfileIntA("idiomas", "diag", 0, ini);
    if (!g_id_activo) {
        apuntar("[idiomas] apagado ([idiomas] activo=0): los textos en la pagina de este Windows (%u)", GetACP());
        return;
    }
    /* ⚠ las de verdad se toman de las DLL de Windows ANTES de tocar la tabla: si se tomaran después nos
     *   llamaríamos a nosotros mismos (la lección de `Sleep`). */
    HMODULE k32 = GetModuleHandleA("kernel32.dll"), gdi = GetModuleHandleA("gdi32.dll");
    g_id_mb2wc = k32 ? (ID_MB2WC)GetProcAddress(k32, "MultiByteToWideChar") : NULL;
    g_id_wc2mb = k32 ? (ID_WC2MB)GetProcAddress(k32, "WideCharToMultiByte") : NULL;
    g_id_pedir = k32 ? (ID_PEDIR)GetProcAddress(k32, "GetProcAddress") : NULL;
    g_id_medir = gdi ? (ID_MEDIR)GetProcAddress(gdi, "GetTextExtentPoint32A") : NULL;
    g_id_medirex = gdi ? (ID_MEDIREX)GetProcAddress(gdi, "GetTextExtentExPointA") : NULL;
    g_id_escribir = gdi ? (ID_ESCRIBIR)GetProcAddress(gdi, "ExtTextOutA") : NULL;
    if (!g_id_mb2wc || !g_id_wc2mb || !g_id_pedir || !g_id_medir || !g_id_medirex || !g_id_escribir) {
        g_id_activo = 0;
        apuntar("[idiomas] (!) no encontre las funciones de Windows: NO se aplica");
        return;
    }
    InitializeCriticalSection(&g_id_cs);
    int ok = 0;
    ok += parchear_iat("KERNEL32.dll", "MultiByteToWideChar", (void *)id_mb2wc) != NULL;
    ok += parchear_iat("KERNEL32.dll", "WideCharToMultiByte", (void *)id_wc2mb) != NULL;
    ok += parchear_iat("GDI32.dll", "GetTextExtentPoint32A", (void *)id_medir) != NULL;
    ok += parchear_iat("GDI32.dll", "GetTextExtentExPointA", (void *)id_medirex) != NULL;
    ok += parchear_iat("GDI32.dll", "ExtTextOutA", (void *)id_escribir) != NULL;
    /* ★ la letra de respaldo: Uniscribe se pide por GetProcAddress (ver arriba) */
    ok += parchear_iat("KERNEL32.dll", "GetProcAddress", (void *)id_pedir) != NULL;
    apuntar("[idiomas] %d de 6 enganchadas: los textos del juego en UTF-8 o 1252 (Windows en la %u)%s",
            ok, GetACP(), g_id_diag ? " · diag=1" : "");
}
