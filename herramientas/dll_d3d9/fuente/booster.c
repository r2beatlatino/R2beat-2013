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
typedef struct { void *tex; RECT r; DWORD *orig; LONG version; int c_img, c_marco; int malo; } BO_SLOT;

static CRITICAL_SECTION g_bo_cs;
static int     g_bo_cs_lista = 0, g_bo_activo = 0, g_bo_mover_activo = 0;
static BO_ANIM g_bo_img[3];                     /* 0 = sin carga · 1 = lleno · 2 = marco */
static COLORREF g_bo_tenir = CLR_INVALID;       /* CLR_INVALID = sin teñir */
static volatile int g_bo_dx = 0, g_bo_dy = 0;   /* mover, en px del juego */
static volatile BYTE g_bo_en_columna = 0;
static volatile LONG g_bo_version = 1;
static LONG    g_bo_revisada = 0;
static BO_SLOT g_bo_slot[8];
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
    static const wchar_t *N[3] = { L"sin_carga", L"lleno", L"marco" };
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
    int x = (int)GetPrivateProfileIntA("herramienta", "booster_x", 0, g_ht_ini);
    int y = (int)GetPrivateProfileIntA("herramienta", "booster_y", 0, g_ht_ini);
    g_bo_dx = x < -2000 ? -2000 : x > 2000 ? 2000 : x;
    g_bo_dy = y < -2000 ? -2000 : y > 2000 ? 2000 : y;
}

/* las imágenes: en el 1.er cuadro del botón (no en DllMain: GDI+) */
static void bo_cargar_ini(void)
{
    for (int k = 0; k < 3; k++) {
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

static BO_SLOT *bo_slot(void *tex, const RECT *r)
{
    for (int i = 0; i < g_bo_nslot; i++)
        if (g_bo_slot[i].tex == tex && EqualRect(&g_bo_slot[i].r, r)) return &g_bo_slot[i];
    if (g_bo_nslot >= 8) return NULL;
    BO_SLOT *s = &g_bo_slot[g_bo_nslot++];
    ZeroMemory(s, sizeof(*s));
    s->tex = tex; s->r = *r; s->c_img = s->c_marco = -1;
    int w = r->right - r->left, h = r->bottom - r->top;
    void **vt = *(void ***)tex;
    PDR_LOCK b;
    s->orig = (DWORD *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h * 4);
    if (!s->orig || ((PDR_T_LOCK)vt[19])(tex, 0, &b, r, 0x10 /* READONLY */) != 0) { s->malo = 1; return s; }
    for (int y = 0; y < h; y++) CopyMemory(s->orig + y * w, (BYTE *)b.pBits + y * b.Pitch, (SIZE_T)w * 4);
    ((PDR_T_UNLOCK)vt[20])(tex, 0);
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

static void bo_escribir(BO_SLOT *s, const BO_ANIM *img, int ci, const BO_ANIM *marco, int cm)
{
    int w = s->r.right - s->r.left, h = s->r.bottom - s->r.top;
    void **vt = *(void ***)s->tex;
    PDR_LOCK b;
    if (((PDR_T_LOCK)vt[19])(s->tex, 0, &b, &s->r, 0) != 0) { s->malo = 1; return; }
    for (int y = 0; y < h; y++) {
        DWORD *fila = (DWORD *)((BYTE *)b.pBits + y * b.Pitch);
        for (int x = 0; x < w; x++) {
            float u = (x + 0.5f) / w, v = (y + 0.5f) / h;
            DWORD c = img->n ? pdr_muestra(img->px[ci], img->w, img->h, u, v) : s->orig[y * w + x];
            if (marco->n) c = bo_sobre(c, pdr_muestra(marco->px[cm], marco->w, marco->h, u, v));
            if (g_bo_tenir != CLR_INVALID) {                    /* teñir: multiplica los colores */
                DWORD r = ((c >> 16) & 0xFF) * GetRValue(g_bo_tenir) / 255, g = ((c >> 8) & 0xFF) * GetGValue(g_bo_tenir) / 255,
                      bb = (c & 0xFF) * GetBValue(g_bo_tenir) / 255;
                c = (c & 0xFF000000u) | (r << 16) | (g << 8) | bb;
            }
            fila[x] = c;
        }
    }
    ((PDR_T_UNLOCK)vt[20])(s->tex, 0);
}

/* ── el hilo del juego: la entrada de 0x54FA70 ── */
static void __cdecl bo_hud(BYTE *hud)
{
    if (g_bo_cargar_ini) { g_bo_cargar_ini = 0; bo_cargar_ini(); }
    LONG v = g_bo_version;
    int animado = g_bo_img[0].n > 1 || g_bo_img[1].n > 1 || g_bo_img[2].n > 1;
    if (!animado && (++g_bo_cuadro & 31) && v == g_bo_revisada) return;
    if (!hud || !ht_memoria_ok(hud, 0xD80, 0) || !TryEnterCriticalSection(&g_bo_cs)) return;
    DWORD t = GetTickCount();
    int cm = bo_anim_cuadro(&g_bo_img[2], t);
    static const struct { DWORD off; int corte; int lx, ly; } P[2] = { { 0xD50, 9, 335, 0 }, { 0x18, 11, 281, 248 } };
    for (int k = 0; k < 2; k++) {
        BYTE *img = hud + P[k].off;
        void *tex = pdr_textura(img);
        if (!tex) continue;
        PDR_DESC d;
        void **vt = *(void ***)tex;
        if (((PDR_T_DESC)vt[17])(tex, 0, &d) != 0 || (d.Format != 21 && d.Format != 22)) continue;
        RECT r[2];
        int hay[2];
        hay[0] = bo_rect_corte(img, P[k].corte, d.Width, d.Height, &r[0]);
        SetRect(&r[1], P[k].lx, P[k].ly, P[k].lx + 81, P[k].ly + 81);
        hay[1] = (UINT)r[1].right <= d.Width && (UINT)r[1].bottom <= d.Height;
        for (int q = 0; q < 2; q++) {
            if (!hay[q]) continue;
            BO_SLOT *s = bo_slot(tex, &r[q]);
            if (!s || s->malo) continue;
            int ci = bo_anim_cuadro(&g_bo_img[q], t);
            if (s->version == v && s->c_img == ci && s->c_marco == cm) continue;
            bo_escribir(s, &g_bo_img[q], ci, &g_bo_img[2], cm);
            s->version = v; s->c_img = ci; s->c_marco = cm;
        }
    }
    g_bo_revisada = v;
    LeaveCriticalSection(&g_bo_cs);
}

/* ── mover: 0x554CA0 con la bandera puesta corre la COPIA del corte ── */
static void __cdecl bo_desplazar(BYTE *e)
{
    if (!e) return;
    float dx = (float)g_bo_dx, dy = (float)g_bo_dy;
    *(float *)(e + 0x08) += dx; *(float *)(e + 0x0C) += dy;
    *(float *)(e + 0x38) += dx; *(float *)(e + 0x3C) += dy;
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
    c[k++] = 0xFF; c[k++] = 0x74; c[k++] = 0x24; c[k++] = 0x28;                                        /* push [esp+0x28] */
    c[k] = 0xE8; *(DWORD *)(c + k + 1) = (DWORD)bo_desplazar - (DWORD)(c + k + 5); k += 5;
    c[k++] = 0x83; c[k++] = 0xC4; c[k++] = 0x04;
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
