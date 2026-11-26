/* piedras.c — PIEDRAS DEL RITMO propias (25-nov-2026)
 *
 *   anonimo03, comparando la Personalización de Ñ2Hock con la del ToolBitDLL 0.6.40: «Piedras del ritmo». La piedra es
 *   la del HUD de la carrera (la de «Sin Piedra», el modo héroe 0x278): una hoja de 4 × 4 casillas que el juego anima.
 *
 *   EN EL JUEGO (medido en R2BeatMultiTest.exe; el R2Beat.exe del ToolBit tiene los MISMOS bytes en esta zona):
 *     0x54F7F0  thiscall(HUD, color): dibuja la piedra. 0x54EEA0 da el TIPO (0..7, según el ítem de piedra que tenga
 *               el jugador: 0x32B → 4, 0x32C → 5, 0x32D → 6, 0x32A → 7, …) y la imagen es [HUD + 0x98 + tipo*4]
 *               (un c2DImage: [img+4] = el handle de su textura en el gestor [0x931570]).
 *     ⇒ Enganchamos la ENTRADA (5 B: push ebx · push esi · push edi · mov esi,ecx), anotamos el HUD y, en el hilo del
 *       juego, reescribimos los píxeles de las texturas de los 8 tipos con la piedra elegida (todos los niveles de
 *       mipmap). La original de cada textura se guarda la primera vez: «De fábrica» la devuelve.
 *
 *   EN LA VENTANA (Personalización · Piedras, n2h_ventana.c): las piedras viven en <juego>\n2hock_piedras\ (TGA o PNG
 *   con transparencia, cuadradas; 256 × 256 es la de fábrica). La elegida se guarda en [herramienta] piedra=<archivo>.
 *
 *   ⚠ Formatos de textura: A8R8G8B8 / X8R8G8B8 que se dejen bloquear (MANAGED o DYNAMIC). Si no, se avisa una vez en el
 *     registro y la piedra queda la de fábrica.
 *   ⛔ [piedras] activo=0 lo apaga (sin el gancho).
 */

#define PDR_V(x) ((BYTE *)g_ht_base + ((DWORD)(x) - 0x400000))
#define PDR_SLOTS 16

typedef struct { UINT Format, Type, Usage, Pool, MS, MSQ, Width, Height; } PDR_DESC;
typedef struct { INT Pitch; void *pBits; } PDR_LOCK;
typedef long (__stdcall *PDR_T_DESC)(void *tex, UINT nivel, PDR_DESC *d);         /* vt 17 */
typedef long (__stdcall *PDR_T_LOCK)(void *tex, UINT nivel, PDR_LOCK *r, const RECT *rc, DWORD b);   /* vt 19 */
typedef long (__stdcall *PDR_T_UNLOCK)(void *tex, UINT nivel);                  /* vt 20 */
typedef DWORD (__stdcall *PDR_T_NIVELES)(void *tex);                            /* vt 13 */
typedef BYTE *(__attribute__((thiscall)) *PDR_F_ENTRADA)(void *mgr, DWORD h);
typedef void *(__attribute__((thiscall)) *PDR_F_D3D)(void *mgr, DWORD h, int k);

typedef struct { void *tex; DWORD *orig; UINT w, h; LONG version; int malo; } PDR_SLOT;

static CRITICAL_SECTION g_pdr_cs;
static int     g_pdr_cs_lista = 0;
static int     g_pdr_activo = 0;                 /* el gancho está puesto */
static DWORD  *g_pdr_px = NULL;                  /* la piedra elegida (ARGB, alfa recto), NULL = de fábrica */
static int     g_pdr_lado = 0;
static volatile LONG g_pdr_version = 1;          /* sube con cada cambio de piedra */
static PDR_SLOT g_pdr_slot[PDR_SLOTS];
static int     g_pdr_nslot = 0;
static DWORD   g_pdr_cuadro = 0;
static volatile LONG g_pdr_aplicadas = 0;        /* cuántas texturas llevan la piedra elegida (para la ventana) */
static LONG    g_pdr_revisada = 0;               /* la versión que ya se revisó en las 8 casillas */
static int     g_pdr_cargar_ini = 1;             /* la piedra del ini se carga en el 1.er cuadro (no en DllMain: GDI+) */
static BYTE   *g_pdr_cueva = NULL;

/* ── la textura D3D de un c2DImage (como top5 / calculadora) ── */
static void *pdr_textura(BYTE *img)
{
    void *mgr = *(void **)PDR_V(0x931570);
    if (!mgr || !ht_memoria_ok(img, 8, 0)) return NULL;
    DWORD h = *(DWORD *)(img + 4);
    if (!h) return NULL;
    BYTE *ent = ((PDR_F_ENTRADA)PDR_V(0x4099E0))(mgr, h);
    if (!ent || *(DWORD *)(ent + 0x48)) return NULL;           /* animada: no es la nuestra */
    return ((PDR_F_D3D)PDR_V(0x441420))(mgr, h, 0);
}

/* muestreo bilineal de src (sw × sh, ARGB) en (u, v) ∈ [0,1) */
static DWORD pdr_muestra(const DWORD *src, int sw, int sh, float u, float v)
{
    float fx = u * sw - 0.5f, fy = v * sh - 0.5f;
    int x0 = (int)(fx < 0 ? fx - 1 : fx), y0 = (int)(fy < 0 ? fy - 1 : fy);
    float ax = fx - x0, ay = fy - y0;
    int x1 = x0 + 1, y1 = y0 + 1;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 >= sw) x1 = sw - 1;
    if (y1 >= sh) y1 = sh - 1;
    if (x0 >= sw) x0 = sw - 1;
    if (y0 >= sh) y0 = sh - 1;
    DWORD c[4] = { src[y0 * sw + x0], src[y0 * sw + x1], src[y1 * sw + x0], src[y1 * sw + x1] };
    float w[4] = { (1 - ax) * (1 - ay), ax * (1 - ay), (1 - ax) * ay, ax * ay };
    float acc[4] = { 0, 0, 0, 0 }, a = 0;
    for (int i = 0; i < 4; i++) {
        float al = (float)(c[i] >> 24) * w[i];
        a += al;
        for (int k = 0; k < 3; k++) acc[k] += (float)((c[i] >> (16 - 8 * k)) & 0xFF) * al;   /* premultiplicado: sin halos */
    }
    if (a <= 0.001f) return 0;
    DWORD r = (DWORD)(acc[0] / a + 0.5f), g = (DWORD)(acc[1] / a + 0.5f), b = (DWORD)(acc[2] / a + 0.5f);
    DWORD al = (DWORD)(a + 0.5f);
    if (r > 255) r = 255;
    if (g > 255) g = 255;
    if (b > 255) b = 255;
    if (al > 255) al = 255;
    return (al << 24) | (r << 16) | (g << 8) | b;
}

/* escribe src (sw × sh) en TODOS los niveles de la textura (w × h el nivel 0) */
static int pdr_escribir(void *tex, UINT w, UINT h, const DWORD *src, int sw, int sh)
{
    void **vt = *(void ***)tex;
    DWORD niveles = ((PDR_T_NIVELES)vt[13])(tex);
    if (niveles < 1) niveles = 1;
    for (DWORD L = 0; L < niveles; L++) {
        UINT lw = w >> L, lh = h >> L;
        if (!lw) lw = 1;
        if (!lh) lh = 1;
        PDR_LOCK b;
        if (((PDR_T_LOCK)vt[19])(tex, L, &b, NULL, 0) != 0) return L > 0;
        int igual = (int)lw == sw && (int)lh == sh;
        for (UINT y = 0; y < lh; y++) {
            DWORD *fila = (DWORD *)((BYTE *)b.pBits + y * b.Pitch);
            if (igual) CopyMemory(fila, src + y * sw, lw * 4);
            else for (UINT x = 0; x < lw; x++) fila[x] = pdr_muestra(src, sw, sh, (x + 0.5f) / lw, (y + 0.5f) / lh);
        }
        ((PDR_T_UNLOCK)vt[20])(tex, L);
    }
    return 1;
}

/* ★ 26-nov · LA HOJA FINAL (w × h, la de la textura): las NOTAS salen de la piedra elegida, pero la ESQUINA de abajo a
 *   la izquierda (fila 3, casillas 0 y 1 de la grilla de 4 × 4) queda la del juego: en tlight / tlight_2 / tlight_3 ahí
 *   están los NÚMEROS del combo («12345678 90»), y las hojas de soles y estrellas (tlight_5*, tlight_6*) traen otra cosa.
 *   Sin esto, elegir una estrella borraba los números del combo. `orig` = la original (w × h). Pura (la usan las pruebas). */
static int pdr_en_esquina(int x, int y, int w, int h) { return x < w / 2 && y >= h - h / 4; }

static void pdr_componer(DWORD *dst, int w, int h, const DWORD *src, int sw, int sh, const DWORD *orig)
{
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++)
            dst[y * w + x] = orig && pdr_en_esquina(x, y, w, h) ? orig[y * w + x]
                           : (sw == w && sh == h) ? src[y * sw + x]
                           : pdr_muestra(src, sw, sh, (x + 0.5f) / w, (y + 0.5f) / h);
}

/* la textura nueva para nosotros: se guarda la original (nivel 0) */
static PDR_SLOT *pdr_slot(void *tex)
{
    for (int i = 0; i < g_pdr_nslot; i++) if (g_pdr_slot[i].tex == tex) return &g_pdr_slot[i];
    if (g_pdr_nslot >= PDR_SLOTS) return NULL;
    PDR_SLOT *s = &g_pdr_slot[g_pdr_nslot++];
    ZeroMemory(s, sizeof(*s));
    s->tex = tex;
    void **vt = *(void ***)tex;
    PDR_DESC d;
    if (((PDR_T_DESC)vt[17])(tex, 0, &d) != 0) { s->malo = 1; return s; }
    if ((d.Format != 21 && d.Format != 22) || d.Width < 8 || d.Height < 8 || d.Width > 2048 || d.Height > 2048) {
        apuntar("  [piedras] ⚠ una textura de la piedra es formato %u (%ux%u): no se puede cambiar", d.Format, d.Width, d.Height);
        s->malo = 1;
        return s;
    }
    s->w = d.Width; s->h = d.Height;
    s->orig = (DWORD *)HeapAlloc(GetProcessHeap(), 0, d.Width * d.Height * 4);
    PDR_LOCK b;
    if (!s->orig || ((PDR_T_LOCK)vt[19])(tex, 0, &b, NULL, 0x10 /* READONLY */) != 0) {
        apuntar("  [piedras] ⚠ la textura de la piedra (%ux%u, pool %u) no se deja leer: queda la de fábrica", d.Width, d.Height, d.Pool);
        s->malo = 1;
        return s;
    }
    for (UINT y = 0; y < d.Height; y++) {
        CopyMemory(s->orig + y * d.Width, (BYTE *)b.pBits + y * b.Pitch, d.Width * 4);
        if (d.Format == 22) for (UINT x = 0; x < d.Width; x++) s->orig[y * d.Width + x] |= 0xFF000000u;
    }
    ((PDR_T_UNLOCK)vt[20])(tex, 0);
    apuntar("  [piedras] textura de la piedra %d: %ux%u, %u nivel(es), pool %u", g_pdr_nslot, d.Width, d.Height,
            ((PDR_T_NIVELES)vt[13])(tex), d.Pool);
    return s;
}

static void pdr_cargar_elegida(void);

/* ── el hilo del juego: la entrada de 0x54F7F0 ── */
static void __cdecl pdr_hud(BYTE *hud)
{
    if (g_pdr_cargar_ini) { g_pdr_cargar_ini = 0; pdr_cargar_elegida(); }
    LONG v = g_pdr_version;
    if ((++g_pdr_cuadro & 31) && v == g_pdr_revisada) return;          /* cada 32 cuadros o al cambiar */
    if (!hud || !ht_memoria_ok(hud + 0x98, 32, 0) || !TryEnterCriticalSection(&g_pdr_cs)) return;
    LONG aplicadas = 0;
    for (int i = 0; i < 8; i++) {
        BYTE *img = *(BYTE **)(hud + 0x98 + i * 4);
        if (!img) continue;
        void *tex = pdr_textura(img);
        if (!tex) continue;
        PDR_SLOT *s = pdr_slot(tex);
        if (!s || s->malo) continue;
        if (s->version != v) {
            int bien;
            if (g_pdr_px) {                                     /* la elegida, con la esquina de los números del juego */
                DWORD *hoja = (DWORD *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)s->w * s->h * 4);
                if (!hoja) continue;
                pdr_componer(hoja, (int)s->w, (int)s->h, g_pdr_px, g_pdr_lado, g_pdr_lado, s->orig);
                bien = pdr_escribir(tex, s->w, s->h, hoja, (int)s->w, (int)s->h);
                HeapFree(GetProcessHeap(), 0, hoja);
            } else bien = pdr_escribir(tex, s->w, s->h, s->orig, (int)s->w, (int)s->h);
            if (bien) s->version = v;
            else s->malo = 1;
        }
        if (g_pdr_px && s->version == v) aplicadas++;
    }
    g_pdr_revisada = v;
    g_pdr_aplicadas = aplicadas;
    LeaveCriticalSection(&g_pdr_cs);
}

/* ── la ventana: poner la piedra (px NULL = de fábrica). Se queda con px. ── */
static void pdr_poner(DWORD *px, int lado)
{
    if (!g_pdr_cs_lista) { if (px) HeapFree(GetProcessHeap(), 0, px); return; }
    EnterCriticalSection(&g_pdr_cs);
    if (g_pdr_px) HeapFree(GetProcessHeap(), 0, g_pdr_px);
    g_pdr_px = px; g_pdr_lado = px ? lado : 0;
    InterlockedIncrement(&g_pdr_version);
    LeaveCriticalSection(&g_pdr_cs);
}

/* ── cargar una imagen: TGA (2/10, 24/32 bits) o, con GDI+, PNG/BMP/GIF. ARGB de arriba abajo, alfa recto. ── */
static DWORD *pdr_tga(const BYTE *b, DWORD n, int *w, int *h)
{
    if (n < 18) return NULL;
    int idlen = b[0], cmap = b[1], tipo = b[2], bpp = b[16], desc = b[17];
    int W = b[12] | (b[13] << 8), H = b[14] | (b[15] << 8);
    if (cmap || (tipo != 2 && tipo != 10) || (bpp != 24 && bpp != 32) || W <= 0 || H <= 0 || W > 4096 || H > 4096) return NULL;
    DWORD *px = (DWORD *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)W * H * 4);
    if (!px) return NULL;
    DWORD p = 18 + idlen, k = 0, total = (DWORD)W * H;
    int bytes = bpp / 8;
    while (k < total) {
        int cuenta = 1, crudo = 1;
        if (tipo == 10) {
            if (p >= n) break;
            BYTE c = b[p++];
            cuenta = (c & 0x7F) + 1;
            crudo = !(c & 0x80);
        }
        for (int i = 0; i < cuenta && k < total; i++) {
            if ((crudo || i == 0) && p + bytes > n) { k = total + 1; break; }
            const BYTE *q = b + p;
            DWORD c = ((DWORD)q[2] << 16) | ((DWORD)q[1] << 8) | q[0] | (bytes == 4 ? (DWORD)q[3] << 24 : 0xFF000000u);
            px[k++] = c;
            if (crudo || i == cuenta - 1) p += bytes;
        }
    }
    if (k != total) { HeapFree(GetProcessHeap(), 0, px); return NULL; }
    if (!(desc & 0x20)) {                                        /* de abajo arriba: dar vuelta */
        for (int y = 0; y < H / 2; y++)
            for (int x = 0; x < W; x++) { DWORD t = px[y * W + x]; px[y * W + x] = px[(H - 1 - y) * W + x]; px[(H - 1 - y) * W + x] = t; }
    }
    *w = W; *h = H;
    return px;
}

static DWORD *pdr_gdip(const wchar_t *ruta, int *w, int *h)
{
    typedef struct { UINT32 ver; void *cb; BOOL sin_hilo, sin_codecs; } PDR_GIN;
    typedef struct { UINT Width, Height; INT Stride; INT PixelFormat; void *Scan0; UINT_PTR Reserved; } PDR_BD;
    typedef struct { INT X, Y, Width, Height; } PDR_RC;
    typedef int (WINAPI *F_INI)(ULONG_PTR *, const PDR_GIN *, void *);
    typedef int (WINAPI *F_ABRIR)(const WCHAR *, void **);
    typedef int (WINAPI *F_MEDIDA)(void *, UINT *);
    typedef int (WINAPI *F_LOCK)(void *, const PDR_RC *, UINT, INT, PDR_BD *);
    typedef int (WINAPI *F_UNLOCK)(void *, PDR_BD *);
    typedef int (WINAPI *F_LIB)(void *);
    static ULONG_PTR token = 0;
    HMODULE g = LoadLibraryW(L"gdiplus.dll");
    if (!g) return NULL;
    F_INI ini = (F_INI)(void *)GetProcAddress(g, "GdiplusStartup");
    F_ABRIR abrir = (F_ABRIR)(void *)GetProcAddress(g, "GdipCreateBitmapFromFile");
    F_MEDIDA ancho = (F_MEDIDA)(void *)GetProcAddress(g, "GdipGetImageWidth");
    F_MEDIDA alto = (F_MEDIDA)(void *)GetProcAddress(g, "GdipGetImageHeight");
    F_LOCK lock = (F_LOCK)(void *)GetProcAddress(g, "GdipBitmapLockBits");
    F_UNLOCK unlock = (F_UNLOCK)(void *)GetProcAddress(g, "GdipBitmapUnlockBits");
    F_LIB lib = (F_LIB)(void *)GetProcAddress(g, "GdipDisposeImage");
    if (!ini || !abrir || !ancho || !alto || !lock || !unlock || !lib) return NULL;
    if (!token) { PDR_GIN in = { 1, NULL, FALSE, FALSE }; if (ini(&token, &in, NULL) != 0) { token = 0; return NULL; } }
    void *img = NULL;
    if (abrir(ruta, &img) != 0 || !img) return NULL;
    UINT W = 0, H = 0;
    DWORD *px = NULL;
    if (ancho(img, &W) == 0 && alto(img, &H) == 0 && W && H && W <= 4096 && H <= 4096) {
        PDR_RC r = { 0, 0, (INT)W, (INT)H };
        PDR_BD d;
        if (lock(img, &r, 1 /* READ */, 0x26200A /* 32bppARGB */, &d) == 0) {
            px = (DWORD *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)W * H * 4);
            if (px) for (UINT y = 0; y < H; y++) CopyMemory(px + y * W, (BYTE *)d.Scan0 + (INT)y * d.Stride, W * 4);
            unlock(img, &d);
        }
    }
    lib(img);
    if (px) { *w = (int)W; *h = (int)H; }
    return px;
}

static DWORD *pdr_cargar(const wchar_t *ruta, int *w, int *h)
{
    int n = lstrlenW(ruta);
    if (n > 4 && !lstrcmpiW(ruta + n - 4, L".tga")) {
        HANDLE f = CreateFileW(ruta, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
        if (f == INVALID_HANDLE_VALUE) return NULL;
        DWORD tam = GetFileSize(f, NULL), leido = 0;
        DWORD *px = NULL;
        BYTE *b = tam && tam < 64u * 1024 * 1024 ? (BYTE *)HeapAlloc(GetProcessHeap(), 0, tam) : NULL;
        if (b && ReadFile(f, b, tam, &leido, NULL) && leido == tam) px = pdr_tga(b, tam, w, h);
        if (b) HeapFree(GetProcessHeap(), 0, b);
        CloseHandle(f);
        return px;
    }
    return pdr_gdip(ruta, w, h);
}

/* ¿sirve como piedra? 0 = sí; si no, el porqué en `por` (≥ 160) */
static int pdr_validar(const DWORD *px, int w, int h, wchar_t *por)
{
    if (!px) { lstrcpyW(por, L"no se pudo abrir (TGA de 24/32 bits o PNG)"); return 1; }
    if (w != h || w < 64) { wsprintfW(por, L"mide %d x %d (una piedra es un cuadrado de 4 x 4 casillas: 256 x 256 px)", w, h); return 1; }
    int transparente = 0;
    for (int i = 0; i < w * h; i++) if ((px[i] >> 24) < 250) { transparente = 1; break; }
    if (!transparente) { lstrcpyW(por, L"no tiene transparencia (una piedra es un TGA o PNG de 32 bits con el fondo transparente)"); return 1; }
    return 0;
}

static void pdr_carpeta(wchar_t *r)                    /* r: MAX_PATH, termina en '\' */
{
    MultiByteToWideChar(CP_ACP, 0, g_carpeta, -1, r, MAX_PATH - 24);
    lstrcatW(r, L"n2hock_piedras\\");
}

/* la piedra de [herramienta] piedra=<archivo> (vacío = de fábrica) */
static wchar_t g_pdr_elegida[MAX_PATH];
static void pdr_cargar_elegida(void)
{
    char t[MAX_PATH * 3];
    GetPrivateProfileStringA("herramienta", "piedra", "", t, sizeof(t), g_ht_ini);
    if (!MultiByteToWideChar(CP_UTF8, 0, t, -1, g_pdr_elegida, MAX_PATH)) g_pdr_elegida[0] = 0;
    if (!g_pdr_elegida[0]) return;
    wchar_t r[MAX_PATH * 2], por[200];
    pdr_carpeta(r);
    lstrcatW(r, g_pdr_elegida);
    int w = 0, h = 0;
    DWORD *px = pdr_cargar(r, &w, &h);
    if (pdr_validar(px, w, h, por)) {
        char u[400];
        WideCharToMultiByte(CP_UTF8, 0, por, -1, u, sizeof(u), NULL, NULL);
        apuntar("  [piedras] ⚠ la piedra guardada no sirve (%s): queda la de fábrica", u);
        if (px) HeapFree(GetProcessHeap(), 0, px);
        g_pdr_elegida[0] = 0;
        return;
    }
    pdr_poner(px, w);
}

/* ── el gancho ── */
static void piedras_iniciar(void)
{
    InitializeCriticalSection(&g_pdr_cs);
    g_pdr_cs_lista = 1;
    if (!GetPrivateProfileIntA("piedras", "activo", 1, g_ht_ini)) { apuntar("  [piedras] apagadas ([piedras] activo=0)"); return; }
    static const BYTE E[5] = { 0x53, 0x56, 0x57, 0x8B, 0xF1 };           /* push ebx · push esi · push edi · mov esi,ecx */
    BYTE *s = PDR_V(0x54F7F0);
    if (!ht_memoria_ok(s, 5, 0) || memcmp(s, E, 5) != 0) {
        apuntar("  [piedras] ⛔ 0x54F7F0 no tiene los bytes esperados (¿otro exe u otro plugin de piedras?): no se toca");
        return;
    }
    g_pdr_cueva = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_pdr_cueva) return;
    BYTE *c = g_pdr_cueva;
    int k = 0;
    c[k++] = 0x60; c[k++] = 0x9C; c[k++] = 0x51;                      /* pushad · pushfd · push ecx */
    c[k] = 0xE8; *(DWORD *)(c + k + 1) = (DWORD)pdr_hud - (DWORD)(c + k + 5); k += 5;
    c[k++] = 0x83; c[k++] = 0xC4; c[k++] = 0x04;                      /* add esp,4 */
    c[k++] = 0x9D; c[k++] = 0x61;                                      /* popfd · popad */
    CopyMemory(c + k, E, 5); k += 5;                                   /* lo pisado */
    c[k] = 0xE9; *(DWORD *)(c + k + 1) = (DWORD)(s + 5) - (DWORD)(c + k + 5); k += 5;
    FlushInstructionCache(GetCurrentProcess(), c, k);
    DWORD viejo = 0;
    if (!VirtualProtect(s, 5, PAGE_EXECUTE_READWRITE, &viejo)) return;
    s[0] = 0xE9; *(DWORD *)(s + 1) = (DWORD)c - (DWORD)(s + 5);
    VirtualProtect(s, 5, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, 5);
    g_pdr_activo = 1;
    apuntar("  [piedras] ok: la piedra del HUD (0x54F7F0) se puede cambiar desde Personalización · Piedras");
}
