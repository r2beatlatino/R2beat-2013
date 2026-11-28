/* booster.c — EL BOTÓN DEL BOOSTER propio (25-nov-2026)
 *
 *   ToolBit 0.6.40, «AutoCtrl en la carrera (el botón del booster)»: el botón lleno y sin carga, un marco encima,
 *   animados (GIF), teñirlo, y moverlo en X/Y (con el de equipo y el fuego).
 *
 *   EN EL JUEGO (R2BeatMultiTest.exe; el R2Beat.exe del ToolBit tiene los MISMOS bytes en todos estos sitios):
 *     0x54FA70  thiscall(HUD, …): dibuja el botón. Dos c2DImage DENTRO del HUD, con 2 cortes cada uno:
 *               HUD+0xD50: corte 9 = el botón sin carga · corte 10 = la carga, recortada desde abajo de (335, 0, 81, 81)
 *               HUD+0x18 : corte 11 = el botón sin carga · corte 12 = la carga, de (281, 248, 81, 81)
 *     c2DImage: [img+4] = handle de la textura · [img+0x18]..[img+0x1C] = los cortes (0x50 B cada uno):
 *               +0x08/+0x0C la posición · +0x14/+0x18 el tamaño · +0x1C..+0x28 u0, v0, u1, v1 (normalizados).
 *     0x55C1F0  thiscall(HUD), sin argumentos: TODA la columna del booster (el botón, el de equipo, el fuego…).
 *     0x554CA0  thiscall(cola, entrada): mete en la cola 2D una COPIA del corte (el juego ya le suma ahí su propio
 *               desplazamiento [cola+0x158/+0x15C] a +0x08/+0x0C/+0x38/+0x3C). Lo engancha también el ToolBit.
 *
 *   ⇒ IMÁGENES: enganchamos la entrada de 0x54FA70 (5 B: mov eax,[0x9314C8]) y reescribimos ESOS rectángulos de la hoja
 *     (nivel 0): la imagen elegida (o la original), el marco encima (ajustado al botón) y el tinte. Con un GIF animado
 *     se reescribe al cambiar de cuadro. Lo original se guarda la primera vez y vuelve al quitar.
 *   ⇒ MOVER: 0x55C1F0 se envuelve (una bandera mientras corre) y en 0x554CA0, con la bandera puesta, se corre la
 *     COPIA (nunca el corte original: no se acumula de un cuadro al otro).
 *
 *   Archivos: <juego>\n2hock_booster\{sin_carga,lleno,marco}.{png,tga} (un .png puede ser en realidad GIF: GDI+ mira
 *   la firma). Ajustes: [herramienta] booster_tenir=#RRGGBB · booster_x · booster_y (px del juego).
 *   ⛔ [booster] activo=0 lo apaga entero. ⏳ No hecho: el aura que gira AFUERA del botón (acá el marco va adentro).
 */

#define BO_MAX_CUADROS 64

typedef struct { int n, w, h, total; DWORD **px; int *ms; } BO_ANIM;     /* n = 0: no hay */
typedef struct { void *tex; RECT r; DWORD *orig; LONG version; int c_img, c_marco, c_tinte; int malo; UINT fmt, nivel;
                 int es_lleno; } BO_SLOT;

/* ★ 28-nov (medido en el cliente de anonimo03): la hoja del botón es de 16 bits, A1R5G5B5 (formato 25), no de 32: el
 *   booster se salteaba el botón sin decir nada. Se lee y se escribe en el formato de la hoja: 21/22 (32 bits), 25
 *   A1R5G5B5, 26 A4R4G4B4, 23 R5G6B5 y 24 X1R5G5B5. */
static int bo_fmt_ok(UINT f) { return f == 21 || f == 22 || (f >= 23 && f <= 26); }
static int bo_fmt_bytes(UINT f) { return f == 21 || f == 22 ? 4 : 2; }
static DWORD bo_leer_px(UINT f, const BYTE *p)
{
    if (f == 21) return *(const DWORD *)p;
    if (f == 22) return *(const DWORD *)p | 0xFF000000u;
    WORD w = *(const WORD *)p;
    DWORD a, r, g, b;
    if (f == 26) { a = (w >> 12) & 15; r = (w >> 8) & 15; g = (w >> 4) & 15; b = w & 15; a *= 17; r *= 17; g *= 17; b *= 17; }
    else if (f == 23) { a = 255; r = (w >> 11) & 31; g = (w >> 5) & 63; b = w & 31; r = r * 255 / 31; g = g * 255 / 63; b = b * 255 / 31; }
    else { a = f == 25 ? ((w & 0x8000) ? 255 : 0) : 255; r = (w >> 10) & 31; g = (w >> 5) & 31; b = w & 31;
           r = r * 255 / 31; g = g * 255 / 31; b = b * 255 / 31; }
    return (a << 24) | (r << 16) | (g << 8) | b;
}
static void bo_poner_px(UINT f, BYTE *p, DWORD c)
{
    DWORD a = c >> 24, r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, b = c & 0xFF;
    if (f == 21) { *(DWORD *)p = c; return; }
    if (f == 22) { *(DWORD *)p = c | 0xFF000000u; return; }
    WORD w;
    if (f == 26) w = (WORD)(((a >> 4) << 12) | ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4));
    else if (f == 23) w = (WORD)(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
    else w = (WORD)((f == 25 && a >= 128 ? 0x8000 : f == 24 ? 0x8000 : 0) | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3));
    *(WORD *)p = w;
}

static CRITICAL_SECTION g_bo_cs;
static int     g_bo_cs_lista = 0, g_bo_activo = 0, g_bo_mover_activo = 0;
/* ★ 28-nov (anonimo03, con los ejemplos del AutoCtrl del ToolBit): + 3 = el 2.º cuadro del LLENO (parpadea con el 1.º)
 *   · 4 = el AURA (alrededor del botón, afuera) · 5 = TEÑIR CON IMAGEN (multiplica, como el color). Un marco de más de
 *   100 px es «grande»: va afuera del botón, como el aura (booster_dibujo.c). */
#define BO_N 6
static BO_ANIM g_bo_img[BO_N];                  /* 0 = sin carga · 1 = lleno · 2 = marco · 3 = lleno_2 · 4 = aura · 5 = tenir */
static int g_bo_aura_pct = 190;                 /* el aura, en % del lado del botón ([herramienta] booster_aura) */
/* ★ 28-nov (anonimo03: «el aura y el marco son muy rápidos, ponlo más lento»): la velocidad de TODAS las animaciones
 *   del booster (GIF), en %: 100 = la del archivo. De fábrica, la mitad. [herramienta] booster_anim */
static int g_bo_anim_pct = 50;
/* ★ 28-nov (anonimo03: «¿no debería salir algo cuando está lleno, para darme cuenta?»): con el botón propio ya no se ve
 *   el corredor amarillo, y el destello del juego se esconde si el botón está movido. Ñ2Hock pone su BRILLO: late
 *   detrás del botón mientras el impulsor está lleno (dorado, o el color del teñido). [herramienta] booster_brillo */
static int g_bo_brillo = 1;
/* ★ 28-nov (anonimo03: «el aura sólo cuando esté completo el booster, y el teñido sólo cuando se llena»): de fábrica,
 *   las dos cosas sólo con el impulsor LLENO. [herramienta] booster_aura_lleno · booster_tenir_lleno */
static int g_bo_aura_lleno = 1, g_bo_tenir_lleno = 1;
/* ★ 28-nov (anonimo03: «elijo el ejemplo, el booster cambia, pero la lista sigue en (elige un ejemplo)»): el ejemplo
 *   puesto de cada lista (botón, marco, aura, teñido), para mostrarlo. [herramienta] booster_ej_boton … booster_ej_tenir */
static wchar_t g_bo_ej_puesto[4][64];
static const char *const BO_EJ_INI[4] = { "booster_ej_boton", "booster_ej_marco", "booster_ej_aura", "booster_ej_tenir" };
static volatile DWORD g_bo_lleno_t;             /* la última vez que el juego dibujó la carga entera o el «listo» */
/* dónde quedó el botón en la pantalla (lo anota la cola 2D, abajo): x, y, lado y cuándo */
static volatile float g_bo_bx, g_bo_by, g_bo_bw, g_bo_bh;
static volatile DWORD g_bo_bt;
static float g_bo_uv[2][4];                     /* u0 v0 u1 v1 del botón «sin carga» de cada c2DImage (para reconocerlo) */
static float g_bo_uvc[2][4];                    /* ★ 28-nov: y los de la CARGA (cortes 10 / 12): lleno, el juego dibuja ésa */
static volatile LONG g_bo_uv_ok;
static COLORREF g_bo_tenir = CLR_INVALID;       /* CLR_INVALID = sin teñir */
static volatile int g_bo_dx = 0, g_bo_dy = 0;   /* mover, en px del juego */
static volatile BYTE g_bo_en_columna = 0;
static volatile LONG g_bo_version = 1;
static LONG    g_bo_revisada = 0;
static BO_SLOT g_bo_slot[48];                  /* ★ 28-nov: + los niveles de mipmap (hasta 6 por cuadro) */
static int     g_bo_nslot = 0;
static DWORD   g_bo_cuadro = 0;
static int     g_bo_cargar_ini = 1;

static void bo_carpeta(wchar_t *r)
{
    MultiByteToWideChar(CP_ACP, 0, g_carpeta, -1, r, MAX_PATH - 24);
    lstrcatW(r, L"n2hock_booster\\");
}

/* la ruta de sin_carga / lleno / marco que exista (png o tga); 0 si no hay */
static int bo_ruta(int cual, wchar_t *r)
{
    static const wchar_t *N[BO_N] = { L"sin_carga", L"lleno", L"marco", L"lleno_2", L"aura", L"tenir" };
    static const wchar_t *E[2] = { L".png", L".tga" };
    for (int e = 0; e < 2; e++) {
        bo_carpeta(r);
        lstrcatW(r, N[cual]); lstrcatW(r, E[e]);
        if (GetFileAttributesW(r) != INVALID_FILE_ATTRIBUTES) return 1;
    }
    return 0;
}

static void bo_anim_soltar(BO_ANIM *a)
{
    for (int i = 0; i < a->n; i++) if (a->px[i]) HeapFree(GetProcessHeap(), 0, a->px[i]);
    if (a->px) HeapFree(GetProcessHeap(), 0, a->px);
    if (a->ms) HeapFree(GetProcessHeap(), 0, a->ms);
    ZeroMemory(a, sizeof(*a));
}

/* GIF (o cualquier imagen) con todos sus cuadros, por GDI+. 0 = no se pudo */
static int bo_gdip_anim(const wchar_t *ruta, BO_ANIM *a)
{
    typedef struct { UINT32 ver; void *cb; BOOL sin_hilo, sin_codecs; } BO_GIN;
    typedef struct { UINT Width, Height; INT Stride; INT PixelFormat; void *Scan0; UINT_PTR Reserved; } BO_BD;
    typedef struct { INT X, Y, Width, Height; } BO_RC;
    typedef struct { DWORD id; ULONG length; WORD type; void *value; } BO_PROP;
    typedef int (WINAPI *F_INI)(ULONG_PTR *, const BO_GIN *, void *);
    typedef int (WINAPI *F_ABRIR)(const WCHAR *, void **);
    typedef int (WINAPI *F_MEDIDA)(void *, UINT *);
    typedef int (WINAPI *F_LOCK)(void *, const BO_RC *, UINT, INT, BO_BD *);
    typedef int (WINAPI *F_UNLOCK)(void *, BO_BD *);
    typedef int (WINAPI *F_LIB)(void *);
    typedef int (WINAPI *F_DIMS)(void *, UINT *);
    typedef int (WINAPI *F_DIMLIST)(void *, GUID *, UINT);
    typedef int (WINAPI *F_FCOUNT)(void *, const GUID *, UINT *);
    typedef int (WINAPI *F_FSEL)(void *, const GUID *, UINT);
    typedef int (WINAPI *F_PSIZE)(void *, DWORD, UINT *);
    typedef int (WINAPI *F_PROP)(void *, DWORD, UINT, BO_PROP *);
    static ULONG_PTR token = 0;
    HMODULE g = LoadLibraryW(L"gdiplus.dll");
    if (!g) return 0;
#define BO_GP(t, n) t n = (t)(void *)GetProcAddress(g, #n)
    BO_GP(F_INI, GdiplusStartup); BO_GP(F_ABRIR, GdipCreateBitmapFromFile); BO_GP(F_MEDIDA, GdipGetImageWidth);
    BO_GP(F_MEDIDA, GdipGetImageHeight); BO_GP(F_LOCK, GdipBitmapLockBits); BO_GP(F_UNLOCK, GdipBitmapUnlockBits);
    BO_GP(F_LIB, GdipDisposeImage); BO_GP(F_DIMS, GdipImageGetFrameDimensionsCount);
    BO_GP(F_DIMLIST, GdipImageGetFrameDimensionsList); BO_GP(F_FCOUNT, GdipImageGetFrameCount);
    BO_GP(F_FSEL, GdipImageSelectActiveFrame); BO_GP(F_PSIZE, GdipGetPropertyItemSize); BO_GP(F_PROP, GdipGetPropertyItem);
#undef BO_GP
    if (!GdiplusStartup || !GdipCreateBitmapFromFile || !GdipGetImageWidth || !GdipGetImageHeight || !GdipBitmapLockBits ||
        !GdipBitmapUnlockBits || !GdipDisposeImage) return 0;
    if (!token) { BO_GIN in = { 1, NULL, FALSE, FALSE }; if (GdiplusStartup(&token, &in, NULL) != 0) { token = 0; return 0; } }
    void *img = NULL;
    if (GdipCreateBitmapFromFile(ruta, &img) != 0 || !img) return 0;
    UINT W = 0, H = 0, n = 1, nd = 0;
    GUID dim;
    int con_dim = 0;
    if (GdipImageGetFrameDimensionsCount && GdipImageGetFrameDimensionsList && GdipImageGetFrameCount && GdipImageSelectActiveFrame &&
        GdipImageGetFrameDimensionsCount(img, &nd) == 0 && nd >= 1 && GdipImageGetFrameDimensionsList(img, &dim, 1) == 0 &&
        GdipImageGetFrameCount(img, &dim, &n) == 0 && n >= 1) con_dim = 1;
    if (n > BO_MAX_CUADROS) n = BO_MAX_CUADROS;
    if (GdipGetImageWidth(img, &W) != 0 || GdipGetImageHeight(img, &H) != 0 || !W || !H || W > 1024 || H > 1024) { GdipDisposeImage(img); return 0; }
    /* los tiempos (PropertyTagFrameDelay 0x5100, en centésimas) */
    LONG *demoras = NULL;
    UINT tam = 0;
    BO_PROP *prop = NULL;
    if (n > 1 && GdipGetPropertyItemSize && GdipGetPropertyItem && GdipGetPropertyItemSize(img, 0x5100, &tam) == 0 && tam) {
        prop = (BO_PROP *)HeapAlloc(GetProcessHeap(), 0, tam);
        if (prop && GdipGetPropertyItem(img, 0x5100, tam, prop) == 0) demoras = (LONG *)prop->value;
    }
    a->px = (DWORD **)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, n * sizeof(DWORD *));
    a->ms = (int *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, n * sizeof(int));
    a->w = (int)W; a->h = (int)H; a->n = 0; a->total = 0;
    for (UINT f = 0; a->px && a->ms && f < n; f++) {
        if (con_dim && n > 1 && GdipImageSelectActiveFrame(img, &dim, f) != 0) break;
        BO_RC r = { 0, 0, (INT)W, (INT)H };
        BO_BD d;
        if (GdipBitmapLockBits(img, &r, 1, 0x26200A, &d) != 0) break;
        DWORD *px = (DWORD *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)W * H * 4);
        if (px) for (UINT y = 0; y < H; y++) CopyMemory(px + y * W, (BYTE *)d.Scan0 + (INT)y * d.Stride, W * 4);
        GdipBitmapUnlockBits(img, &d);
        if (!px) break;
        int ms = demoras && prop && (f + 1) * 4 <= prop->length ? (int)demoras[f] * 10 : 100;
        if (ms < 20) ms = 100;                                   /* como los navegadores: 0 o 1 centésima = 100 ms */
        a->px[a->n] = px; a->ms[a->n] = ms; a->total += ms; a->n++;
    }
    if (prop) HeapFree(GetProcessHeap(), 0, prop);
    GdipDisposeImage(img);
    if (!a->n) { bo_anim_soltar(a); return 0; }
    return 1;
}

/* cualquier imagen → BO_ANIM (un TGA es un cuadro) */
static int bo_anim_cargar(const wchar_t *ruta, BO_ANIM *a)
{
    ZeroMemory(a, sizeof(*a));
    int n = lstrlenW(ruta);
    if (n > 4 && !lstrcmpiW(ruta + n - 4, L".tga")) {
        int w = 0, h = 0;
        DWORD *px = pdr_cargar(ruta, &w, &h);
        if (!px) return 0;
        a->px = (DWORD **)HeapAlloc(GetProcessHeap(), 0, sizeof(DWORD *));
        a->ms = (int *)HeapAlloc(GetProcessHeap(), 0, sizeof(int));
        if (!a->px || !a->ms) { HeapFree(GetProcessHeap(), 0, px); bo_anim_soltar(a); return 0; }
        a->px[0] = px; a->ms[0] = 100; a->n = 1; a->w = w; a->h = h; a->total = 100;
        return 1;
    }
    return bo_gdip_anim(ruta, a);
}

static int bo_anim_cuadro(const BO_ANIM *a, DWORD t)
{
    if (a->n <= 1 || a->total <= 0) return 0;
    t = (DWORD)((unsigned long long)t * (unsigned)g_bo_anim_pct / 100u);   /* ★ 28-nov: más lento o más rápido */
    int m = (int)(t % (DWORD)a->total);
    for (int i = 0; i < a->n; i++) { if (m < a->ms[i]) return i; m -= a->ms[i]; }
    return a->n - 1;
}

/* la ventana: poner una imagen (a NULL = quitar). Se queda con el contenido de a. */
static void bo_poner(int cual, BO_ANIM *a)
{
    if (!g_bo_cs_lista) { if (a) bo_anim_soltar(a); return; }
    EnterCriticalSection(&g_bo_cs);
    bo_anim_soltar(&g_bo_img[cual]);
    if (a) { g_bo_img[cual] = *a; ZeroMemory(a, sizeof(*a)); }
    InterlockedIncrement(&g_bo_version);
    LeaveCriticalSection(&g_bo_cs);
}
static void bo_poner_tenir(COLORREF c)
{
    if (!g_bo_cs_lista) return;
    EnterCriticalSection(&g_bo_cs);
    g_bo_tenir = c;
    InterlockedIncrement(&g_bo_version);
    LeaveCriticalSection(&g_bo_cs);
}

static void bo_tenir_ini(void)
{
    char t[32];
    GetPrivateProfileStringA("herramienta", "booster_tenir", "", t, sizeof(t), g_ht_ini);
    if (t[0] == '#' && lstrlenA(t) == 7) {
        DWORD v = 0;
        for (int i = 1; i < 7; i++) {
            char ch = t[i];
            int d = ch >= '0' && ch <= '9' ? ch - '0' : ch >= 'a' && ch <= 'f' ? ch - 'a' + 10 : ch >= 'A' && ch <= 'F' ? ch - 'A' + 10 : -1;
            if (d < 0) { v = 0xFFFFFFFF; break; }
            v = v * 16 + (DWORD)d;
        }
        if (v != 0xFFFFFFFF) g_bo_tenir = RGB((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF);
    }
    int au = (int)GetPrivateProfileIntA("herramienta", "booster_aura", 190, g_ht_ini);   /* ★ 28-nov */
    g_bo_aura_pct = au < 100 ? 100 : au > 400 ? 400 : au;
    g_bo_brillo = GetPrivateProfileIntA("herramienta", "booster_brillo", 1, g_ht_ini) != 0;
    g_bo_aura_lleno = GetPrivateProfileIntA("herramienta", "booster_aura_lleno", 1, g_ht_ini) != 0;
    for (int i = 0; i < 4; i++) {
        char u[200];
        GetPrivateProfileStringA("herramienta", BO_EJ_INI[i], "", u, sizeof(u), g_ht_ini);
        if (!MultiByteToWideChar(CP_UTF8, 0, u, -1, g_bo_ej_puesto[i], 64)) g_bo_ej_puesto[i][0] = 0;
    }
    g_bo_tenir_lleno = GetPrivateProfileIntA("herramienta", "booster_tenir_lleno", 1, g_ht_ini) != 0;
    int an = (int)GetPrivateProfileIntA("herramienta", "booster_anim", 50, g_ht_ini);
    g_bo_anim_pct = an < 10 ? 10 : an > 300 ? 300 : an;
    int x = (int)GetPrivateProfileIntA("herramienta", "booster_x", 0, g_ht_ini);
    int y = (int)GetPrivateProfileIntA("herramienta", "booster_y", 0, g_ht_ini);
    g_bo_dx = x < -2000 ? -2000 : x > 2000 ? 2000 : x;
    g_bo_dy = y < -2000 ? -2000 : y > 2000 ? 2000 : y;
}

/* las imágenes: en el 1.er cuadro del botón (no en DllMain: GDI+) */
static void bo_cargar_ini(void)
{
    for (int k = 0; k < BO_N; k++) {
        wchar_t r[MAX_PATH * 2];
        BO_ANIM a;
        if (bo_ruta(k, r) && bo_anim_cargar(r, &a)) bo_poner(k, &a);
    }
}

/* un rectángulo de corte en píxeles (desde sus u/v). 0 si no se puede */
static int bo_rect_corte(BYTE *img, int n, UINT tw, UINT th, RECT *r)
{
    if (!ht_memoria_ok(img + 0x18, 8, 0)) return 0;
    BYTE *a = *(BYTE **)(img + 0x18), *b = *(BYTE **)(img + 0x1C);
    if (!a || b <= a || (DWORD)(b - a) / 0x50 <= (DWORD)n) return 0;
    BYTE *c = a + n * 0x50;
    if (!ht_memoria_ok(c + 0x1C, 16, 0)) return 0;
    float u0 = *(float *)(c + 0x1C), v0 = *(float *)(c + 0x20), u1 = *(float *)(c + 0x24), v1 = *(float *)(c + 0x28);
    if (!(u0 >= 0 && v0 >= 0 && u1 <= 1.001f && v1 <= 1.001f && u1 > u0 && v1 > v0)) return 0;
    SetRect(r, (int)(u0 * tw + 0.5f), (int)(v0 * th + 0.5f), (int)(u1 * tw + 0.5f), (int)(v1 * th + 0.5f));
    return r->right - r->left >= 16 && r->bottom - r->top >= 16;
}

static BO_SLOT *bo_slot(void *tex, const RECT *r, UINT fmt, UINT nivel)
{
    for (int i = 0; i < g_bo_nslot; i++)
        if (g_bo_slot[i].tex == tex && g_bo_slot[i].nivel == nivel && EqualRect(&g_bo_slot[i].r, r)) return &g_bo_slot[i];
    if (g_bo_nslot >= 48) return NULL;
    BO_SLOT *s = &g_bo_slot[g_bo_nslot++];
    ZeroMemory(s, sizeof(*s));
    s->tex = tex; s->r = *r; s->c_img = s->c_marco = -1; s->fmt = fmt; s->nivel = nivel;
    int w = r->right - r->left, h = r->bottom - r->top;
    void **vt = *(void ***)tex;
    PDR_LOCK b;
    s->orig = (DWORD *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h * 4);
    if (!s->orig || ((PDR_T_LOCK)vt[19])(tex, nivel, &b, r, 0x10 /* READONLY */) != 0) { s->malo = 1; return s; }
    int pb = bo_fmt_bytes(fmt);
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) s->orig[y * w + x] = bo_leer_px(fmt, (BYTE *)b.pBits + y * b.Pitch + x * pb);
    ((PDR_T_UNLOCK)vt[20])(tex, nivel);
    return s;
}

static DWORD bo_sobre(DWORD abajo, DWORD arriba)              /* «arriba» sobre «abajo», alfa recto */
{
    DWORD a = arriba >> 24;
    if (a == 0) return abajo;
    if (a == 255) return arriba;
    DWORD b = abajo >> 24, ra = a * 255 + b * (255 - a);       /* ×255 */
    if (!ra) return 0;
    DWORD c = 0;
    for (int k = 0; k < 3; k++) {
        DWORD x = (arriba >> (8 * k)) & 0xFF, y = (abajo >> (8 * k)) & 0xFF;
        c |= ((x * a * 255 + y * b * (255 - a)) / ra) << (8 * k);
    }
    return c | ((ra / 255) << 24);
}

/* ★ 28-nov: ¿el marco es «grande» (va afuera del botón)? */
static int bo_marco_afuera(void) { return g_bo_img[2].n && (g_bo_img[2].w > 100 || g_bo_img[2].h > 100); }

static void bo_escribir(BO_SLOT *s, const BO_ANIM *img, int ci, const BO_ANIM *marco, int cm, const BO_ANIM *tinte, int ct)
{
    int w = s->r.right - s->r.left, h = s->r.bottom - s->r.top;
    void **vt = *(void ***)s->tex;
    PDR_LOCK b;
    if (((PDR_T_LOCK)vt[19])(s->tex, s->nivel, &b, &s->r, 0) != 0) { s->malo = 1; return; }
    int pb = bo_fmt_bytes(s->fmt);
    for (int y = 0; y < h; y++) {
        BYTE *fila = (BYTE *)b.pBits + y * b.Pitch;
        for (int x = 0; x < w; x++) {
            float u = (x + 0.5f) / w, v = (y + 0.5f) / h;
            DWORD c = img->n ? pdr_muestra(img->px[ci], img->w, img->h, u, v) : s->orig[y * w + x];
            if (marco && marco->n) c = bo_sobre(c, pdr_muestra(marco->px[cm], marco->w, marco->h, u, v));
            if (tinte && tinte->n && (!g_bo_tenir_lleno || s->es_lleno)) {   /* ★ 28-nov: teñir con una imagen */
                DWORD q = pdr_muestra(tinte->px[ct], tinte->w, tinte->h, u, v), qa = q >> 24;
                DWORD tr = 255 - (255 - ((q >> 16) & 0xFF)) * qa / 255, tg = 255 - (255 - ((q >> 8) & 0xFF)) * qa / 255,
                      tb = 255 - (255 - (q & 0xFF)) * qa / 255;
                c = (c & 0xFF000000u) | ((((c >> 16) & 0xFF) * tr / 255) << 16) | ((((c >> 8) & 0xFF) * tg / 255) << 8)
                    | ((c & 0xFF) * tb / 255);
            }
            if (g_bo_tenir != CLR_INVALID && (!g_bo_tenir_lleno || s->es_lleno)) {   /* teñir: multiplica los colores */
                DWORD r = ((c >> 16) & 0xFF) * GetRValue(g_bo_tenir) / 255, g = ((c >> 8) & 0xFF) * GetGValue(g_bo_tenir) / 255,
                      bb = (c & 0xFF) * GetBValue(g_bo_tenir) / 255;
                c = (c & 0xFF000000u) | (r << 16) | (g << 8) | bb;
            }
            bo_poner_px(s->fmt, fila + x * pb, c);
        }
    }
    ((PDR_T_UNLOCK)vt[20])(s->tex, s->nivel);
}

/* ── el hilo del juego: la entrada de 0x54FA70 ── */
static void __cdecl bo_hud(BYTE *hud)
{
    /* ★ 28-nov (el video de anonimo03: el aura y el marco salían un cuadro sí y otro no): se dibujan ACÁ, cuando el juego
     *   dibuja el botón (antes de su cola 2D: quedan detrás del botón, como un aura), y no en el cuadro del HUD. */
    bod_dibujar();
    if (g_bo_cargar_ini) {
        g_bo_cargar_ini = 0; bo_cargar_ini();
    }
    LONG v = g_bo_version;
    int animado = g_bo_img[0].n > 1 || g_bo_img[1].n > 1 || g_bo_img[2].n > 1 || g_bo_img[3].n || g_bo_img[5].n > 1;
    if (!animado && (++g_bo_cuadro & 31) && v == g_bo_revisada) return;
    if (!hud || !ht_memoria_ok(hud, 0xD80, 0) || !TryEnterCriticalSection(&g_bo_cs)) return;
    DWORD t = GetTickCount();
    const BO_ANIM *marco = bo_marco_afuera() ? NULL : &g_bo_img[2];
    int cm = marco ? bo_anim_cuadro(marco, t) : -1;
    int ct = bo_anim_cuadro(&g_bo_img[5], t);
    int parpadeo = g_bo_img[3].n && ((t / 400) & 1);     /* ★ 28-nov: el lleno y su 2.º cuadro, de a 400 ms */
    static const struct { DWORD off; int corte; int lx, ly; } P[2] = { { 0xD50, 9, 335, 0 }, { 0x18, 11, 281, 248 } };
    /* ★ 28-nov (anonimo03, después de varias carreras: el botón volvía al de fábrica): cada carrera el juego arma hojas
     *   NUEVAS y los lugares de las viejas no se soltaban nunca; a los 48 no se escribía más. Se sueltan los de las hojas
     *   que ya no son las del HUD. */
    {
        void *ahora0 = pdr_textura(hud + P[0].off), *ahora1 = pdr_textura(hud + P[1].off);
        int j = 0;
        for (int i = 0; i < g_bo_nslot; i++) {
            if (g_bo_slot[i].tex == ahora0 || g_bo_slot[i].tex == ahora1) { g_bo_slot[j++] = g_bo_slot[i]; continue; }
            if (g_bo_slot[i].orig) HeapFree(GetProcessHeap(), 0, g_bo_slot[i].orig);
        }
        g_bo_nslot = j;
    }
    for (int k = 0; k < 2; k++) {
        BYTE *img = hud + P[k].off;
        void *tex = pdr_textura(img);
        if (!tex) continue;
        PDR_DESC d;
        void **vt = *(void ***)tex;
        if (((PDR_T_DESC)vt[17])(tex, 0, &d) != 0 || !bo_fmt_ok(d.Format)) {
            static int dicho[2];
            if (!dicho[k]++) apuntar("  [booster] ⚠ imagen %d: textura con formato %d (no sé escribirlo)", k, d.Format);
            continue;
        }
        RECT r[10];
        int hay[10], tipo[10] = { 0, 1 }, nr = 2;           /* tipo: 0 = sin carga · 1 = carga / lleno / listo */
        hay[0] = bo_rect_corte(img, P[k].corte, d.Width, d.Height, &r[0]);
        if (hay[0] && !(g_bo_uv_ok & (2 << k))) {         /* ★ 28-nov: para reconocer el botón en la cola 2D */
            BYTE *c0 = *(BYTE **)(img + 0x18) + P[k].corte * 0x50;
            for (int i = 0; i < 4; i++) g_bo_uv[k][i] = *(float *)(c0 + 0x1C + 4 * i);
            RECT rc;
            if (bo_rect_corte(img, P[k].corte + 1, d.Width, d.Height, &rc)) {
                BYTE *c1 = *(BYTE **)(img + 0x18) + (P[k].corte + 1) * 0x50;
                for (int i = 0; i < 4; i++) g_bo_uvc[k][i] = *(float *)(c1 + 0x1C + 4 * i);
                InterlockedOr(&g_bo_uv_ok, 8 << k);
            }
            InterlockedOr(&g_bo_uv_ok, 1 | (2 << k));
        }
        SetRect(&r[1], P[k].lx, P[k].ly, P[k].lx + 81, P[k].ly + 81);
        hay[1] = (UINT)r[1].right <= d.Width && (UINT)r[1].bottom <= d.Height;
        /* ★ 28-nov (la hoja volcada del cliente de anonimo03): la hoja del botón normal trae OCHO variantes, en dos filas:
         *     y=248: azul (equipo) · rojo (equipo) · amarillo (la carga, r[1]) · gris (sin carga, r[0])
         *     y=334: azul · rosa · amarillo (el botón LISTO, con el impulsor lleno: lo medido en la cola) · gris
         *   Las de color llevan la imagen del lleno; las grises, la del sin carga. Sólo si la hoja es ésa (r[0] en 368,248). */
        if (hay[0] && r[0].left == 368 && r[0].top == 248) {
            static const int EX[6][3] = { { 113, 248, 1 }, { 198, 248, 1 }, { 14, 334, 1 }, { 99, 334, 1 }, { 182, 334, 1 },
                                          { 273, 334, 0 } };
            for (int j = 0; j < 6 && nr < 10; j++, nr++) {
                SetRect(&r[nr], EX[j][0], EX[j][1], EX[j][0] + 81, EX[j][1] + 81);
                hay[nr] = (UINT)r[nr].right <= d.Width && (UINT)r[nr].bottom <= d.Height;
                tipo[nr] = EX[j][2];
            }
        }
        /* ★ 28-nov (medido: «escrito» y el botón seguía de fábrica): la hoja tiene MIPMAPS y la tarjeta puede dibujar
         *   uno más chico. Se escribe el cuadro en CADA nivel (el rectángulo, dividido por 2 en cada uno). */
        typedef UINT (__stdcall *T_NIVELES)(void *);
        UINT niveles = ((T_NIVELES)vt[13])(tex);
        if (niveles < 1 || niveles > 12) niveles = 1;
        for (int qq = 0; qq < nr * (int)niveles; qq++) {
            int cual = qq % nr, q = tipo[cual];             /* q: 0 = sin carga · 1 = la carga (el lleno) */
            UINT nv = (UINT)(qq / nr);
            if (!hay[cual]) continue;
            RECT rn = { r[cual].left >> nv, r[cual].top >> nv, r[cual].right >> nv, r[cual].bottom >> nv };
            if (rn.right - rn.left < 2 || rn.bottom - rn.top < 2) continue;
            BO_SLOT *s = bo_slot(tex, &rn, d.Format, nv);
            if (!s || s->malo) continue;
            s->es_lleno = q == 1;
            const BO_ANIM *im = q == 1 && parpadeo ? &g_bo_img[3] : &g_bo_img[q];
            int ci = bo_anim_cuadro(im, t), clave = ci | (q == 1 && parpadeo ? 0x10000 : 0);
            if (s->version == v && s->c_img == clave && s->c_marco == cm && s->c_tinte == ct) continue;
            bo_escribir(s, im, ci, marco, cm, &g_bo_img[5], ct);
            s->version = v; s->c_img = clave; s->c_marco = cm; s->c_tinte = ct;
        }
    }
    g_bo_revisada = v;
    LeaveCriticalSection(&g_bo_cs);
}

/* ── mover: 0x554CA0 con la bandera puesta corre la COPIA del corte ── */
static LONG g_bo_visto_log;
static void __cdecl bo_desplazar(BYTE *e, BYTE *cola)
{
    if (!e) return;
    /* ★ 28-nov (anonimo03: con el botón corrido 180 px, el destello amarillo del impulsor lleno quedaba ~360 más abajo,
     *   en los videos): el juego YA pone el destello (la pieza grande, 205 x 205, con la textura entera: u0 v0 = 0, 0)
     *   donde está el botón, que nosotros corrimos; si además se lo corre a él, queda al doble. Ése no se corre. */
    /*   … y sin correrlo queda donde estaba el botón: el juego lo dibuja con zoom y su lugar no sigue un corrimiento
     *   simple. Con el botón MOVIDO, el destello se esconde (tamaño 0); en su sitio de siempre, sale como siempre. */
    if (*(float *)(e + 0x14) >= 120 && *(float *)(e + 0x1C) < 0.001f && *(float *)(e + 0x20) < 0.001f) {
        if (g_bo_dx || g_bo_dy) { *(float *)(e + 0x14) = 0; *(float *)(e + 0x18) = 0; }
        return;
    }
    {   /* ★ 28-nov: ¿está lleno? el «listo» (la fila de abajo de la hoja, v0 = 334/512) o la carga entera (81 de alto) */
        float w0 = *(float *)(e + 0x14), h0 = *(float *)(e + 0x18), u0 = *(float *)(e + 0x1C), v0 = *(float *)(e + 0x20);
        int listo = w0 > 76 && w0 < 86 && v0 > 0.650f && v0 < 0.655f;
        int carga = w0 > 76 && w0 < 86 && h0 > 78 && u0 > 0.548f && u0 < 0.552f;
        if (listo || carga) g_bo_lleno_t = GetTickCount() | 1;
    }
    float dx = (float)g_bo_dx, dy = (float)g_bo_dy;
    *(float *)(e + 0x08) += dx; *(float *)(e + 0x0C) += dy;
    *(float *)(e + 0x38) += dx; *(float *)(e + 0x3C) += dy;
    /* ★ 28-nov: ¿es el botón «sin carga»? (sus u/v) → su lugar en pantalla, para el aura y el marco grande. La cola le
     *   suma después su propio desplazamiento ([cola+0x158/+0x15C]). */
    if (!g_bo_uv_ok) return;
    const float *u = (const float *)(e + 0x1C);
#define BO_CERCA(a, b) ((a) - (b) < 0.002f && (b) - (a) < 0.002f)
    for (int kk = 0; kk < 4; kk++) {
        int k = kk & 1, carga = kk >> 1;
        if (!(g_bo_uv_ok & ((carga ? 8 : 2) << k))) continue;
        const float *w = carga ? g_bo_uvc[k] : g_bo_uv[k];
        /* el botón: los 4 iguales · la carga (lleno o cargándose): mismas u y el mismo borde de abajo */
        if (!BO_CERCA(u[0], w[0]) || !BO_CERCA(u[2], w[2]) || !BO_CERCA(u[3], w[3]) || (!carga && !BO_CERCA(u[1], w[1]))) continue;
        if (carga && *(float *)(e + 0x18) < 2) continue;
        /* ★ 28-nov (medido en las capturas de anonimo03): el HUD tiene OTRA pieza con el mismo recorte, a la izquierda
         *   (debajo de la tarjeta), y el aura se iba ahí. El botón de verdad está en la mitad derecha (sin contar lo
         *   que se lo movió) y mide más de 48 px. */
        float px0 = *(float *)(e + 0x08) - (float)g_bo_dx, pw = *(float *)(e + 0x14), ph = *(float *)(e + 0x18);
        if (pw < 48 || (!carga && ph < 48) || (g_ancho && px0 + pw / 2 < (float)g_ancho / 2)) continue;
        /* ★ 28-nov: el juego pone otra copia del botón FUERA de la pantalla (x 1644 en 1600): ésa no */
        if (g_ancho && *(float *)(e + 0x08) + pw > (float)g_ancho + 2) continue;
        float ox = 0, oy = 0;
        if (cola && ht_memoria_ok(cola + 0x158, 8, 0) && cola[0x160]) { ox = *(float *)(cola + 0x158); oy = *(float *)(cola + 0x15C); }
        g_bo_bx = *(float *)(e + 0x08) + ox; g_bo_bw = *(float *)(e + 0x14);
        /* la carga se recorta desde abajo: el botón entero es un cuadrado que termina donde termina ella */
        g_bo_by = *(float *)(e + 0x0C) + oy + (carga ? *(float *)(e + 0x18) - pw : 0);
        g_bo_bh = carga ? pw : *(float *)(e + 0x18);
        g_bo_bt = GetTickCount() | 1;
        if (!g_bo_visto_log++)
            apuntar("  [booster] el botón en pantalla: (%d, %d) %dx%d · cola +(%d, %d)", (int)g_bo_bx, (int)g_bo_by,
                    (int)g_bo_bw, (int)g_bo_bh, (int)ox, (int)oy);
        return;
    }
}

/* una cueva: pushad · pushfd · [push ecx] · call f · add esp,4 · popfd · popad · lo pisado · jmp sitio+n */
static int bo_enganchar_entrada(DWORD va, const BYTE *esp, int n, void *f, const char *que)
{
    BYTE *s = PDR_V(va);
    if (!ht_memoria_ok(s, n, 0) || memcmp(s, esp, n) != 0) {
        apuntar("  [booster] ⛔ %s (0x%08lX) no tiene los bytes esperados: no se toca", que, (unsigned long)va);
        return 0;
    }
    BYTE *c = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!c) return 0;
    int k = 0;
    c[k++] = 0x60; c[k++] = 0x9C; c[k++] = 0x51;
    c[k] = 0xE8; *(DWORD *)(c + k + 1) = (DWORD)f - (DWORD)(c + k + 5); k += 5;
    c[k++] = 0x83; c[k++] = 0xC4; c[k++] = 0x04;
    c[k++] = 0x9D; c[k++] = 0x61;
    CopyMemory(c + k, esp, n); k += n;
    c[k] = 0xE9; *(DWORD *)(c + k + 1) = (DWORD)(s + n) - (DWORD)(c + k + 5); k += 5;
    FlushInstructionCache(GetCurrentProcess(), c, k);
    DWORD viejo = 0;
    if (!VirtualProtect(s, n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    s[0] = 0xE9; *(DWORD *)(s + 1) = (DWORD)c - (DWORD)(s + 5);
    for (int i = 5; i < n; i++) s[i] = 0x90;
    VirtualProtect(s, n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, n);
    return 1;
}

static int bo_enganchar_mover(void)
{
    static const BYTE COL[5] = { 0x83, 0xEC, 0x10, 0x53, 0x56 };          /* sub esp,0x10 · push ebx · push esi */
    static const BYTE COLA[5] = { 0x56, 0x8B, 0x74, 0x24, 0x08 };         /* push esi · mov esi,[esp+8] */
    BYTE *col = PDR_V(0x55C1F0), *cola = PDR_V(0x554CA0);
    if (!ht_memoria_ok(col, 5, 0) || memcmp(col, COL, 5) || !ht_memoria_ok(cola, 5, 0) || memcmp(cola, COLA, 5)) {
        apuntar("  [booster] ⛔ la columna (0x55C1F0) o la cola (0x554CA0) no son las esperadas: sin mover");
        return 0;
    }
    BYTE *c = (BYTE *)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!c) return 0;
    int k = 0;
    /* — la columna: bandera = 1 · call trampolín · bandera = 0 · ret — */
    BYTE *envoltura = c + k;
    c[k++] = 0xC6; c[k++] = 0x05; *(DWORD *)(c + k) = (DWORD)&g_bo_en_columna; k += 4; c[k++] = 1;
    BYTE *llamada = c + k;
    c[k] = 0xE8; k += 5;                                                  /* destino abajo */
    c[k++] = 0xC6; c[k++] = 0x05; *(DWORD *)(c + k) = (DWORD)&g_bo_en_columna; k += 4; c[k++] = 0;
    c[k++] = 0xC3;
    BYTE *tramp = c + k;
    CopyMemory(c + k, COL, 5); k += 5;
    c[k] = 0xE9; *(DWORD *)(c + k + 1) = (DWORD)(col + 5) - (DWORD)(c + k + 5); k += 5;
    *(DWORD *)(llamada + 1) = (DWORD)tramp - (DWORD)(llamada + 5);
    /* — la cola: si la bandera está, bo_desplazar([esp+4]); después lo pisado y seguir — */
    BYTE *en_cola = c + k;
    c[k++] = 0x80; c[k++] = 0x3D; *(DWORD *)(c + k) = (DWORD)&g_bo_en_columna; k += 4; c[k++] = 0;   /* cmp byte [..],0 */
    c[k++] = 0x74; BYTE *salto = c + k; c[k++] = 0;                                                    /* je orig */
    c[k++] = 0x60; c[k++] = 0x9C;
    c[k++] = 0x51;                                                                                     /* push ecx (la cola) */
    c[k++] = 0xFF; c[k++] = 0x74; c[k++] = 0x24; c[k++] = 0x2C;                                        /* push [esp+0x2C] */
    c[k] = 0xE8; *(DWORD *)(c + k + 1) = (DWORD)bo_desplazar - (DWORD)(c + k + 5); k += 5;
    c[k++] = 0x83; c[k++] = 0xC4; c[k++] = 0x08;
    c[k++] = 0x9D; c[k++] = 0x61;
    *salto = (BYTE)((c + k) - (salto + 1));
    CopyMemory(c + k, COLA, 5); k += 5;
    c[k] = 0xE9; *(DWORD *)(c + k + 1) = (DWORD)(cola + 5) - (DWORD)(c + k + 5); k += 5;
    FlushInstructionCache(GetCurrentProcess(), c, k);
    DWORD viejo = 0;
    if (!VirtualProtect(cola, 5, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    cola[0] = 0xE9; *(DWORD *)(cola + 1) = (DWORD)en_cola - (DWORD)(cola + 5);
    VirtualProtect(cola, 5, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), cola, 5);
    if (!VirtualProtect(col, 5, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    col[0] = 0xE9; *(DWORD *)(col + 1) = (DWORD)envoltura - (DWORD)(col + 5);
    VirtualProtect(col, 5, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), col, 5);
    return 1;
}

static void booster_iniciar(void)
{
    InitializeCriticalSection(&g_bo_cs);
    g_bo_cs_lista = 1;
    bo_tenir_ini();
    if (!GetPrivateProfileIntA("booster", "activo", 1, g_ht_ini)) { apuntar("  [booster] apagado ([booster] activo=0)"); return; }
    static const BYTE E[5] = { 0xA1, 0xC8, 0x14, 0x93, 0x00 };          /* mov eax,[0x9314C8] */
    g_bo_activo = bo_enganchar_entrada(0x54FA70, E, 5, (void *)bo_hud, "el botón del booster");
    g_bo_mover_activo = bo_enganchar_mover();
    apuntar("  [booster] imágenes %s · mover %s (x %d, y %d)", g_bo_activo ? "ok (0x54FA70)" : "NO",
            g_bo_mover_activo ? "ok (0x55C1F0 + 0x554CA0)" : "NO", g_bo_dx, g_bo_dy);
}
