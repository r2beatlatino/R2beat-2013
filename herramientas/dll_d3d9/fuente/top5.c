/* top5.c — «TOP 5 RANK» en el picker (09-oct-2026)
 *
 *   anonimo03, con el picker del cliente coreano de hoy: *"al hacer clic en TOP 5 RANK se abre esta lista de ranking de
 *   esa canción … la lista llega hasta 10, se puede escrolear · esos datos ya los tenemos en el server/db · falta
 *   fabricar el botón y el popup"*. Doc: documentacion/TOP5_RANK.md.
 *
 *   El 2013 no tiene esta ventana en ningún lado (ni el botón, ni el .rui, ni el paquete). Así que es toda nuestra:
 *
 *     LOS DATOS   viajan PEGADOS al FF139 («Mi record»: el cliente lo pide solo, con el cursor quieto ~1,5 s sobre
 *                 una canción). Detrás de las milésimas (que entonces van siempre) el server pone la cola «T5»
 *                 (`servidor/picker.py`, `cola_top5`). La lee un salto nuestro en el cave de las milésimas del exe
 *                 (0x835485, `aplicar_parches.py`/record_decimales), con el MISMO lector del juego (0x67D200).
 *     EL BOTÓN    un c2DImage de `top5.tga` en el cuadro de la info, debajo de «Duración». Se dibuja en el Render
 *                 de la lista del picker (pk_lista, picker.c).
 *     LA VENTANA  el «lienzo» de la calculadora: una textura del pak que reescribimos en memoria (el fondo del
 *                 coreano + los textos, con GDI) SÓLO cuando algo cambia, y se dibuja de una vez. Mientras está
 *                 abierta la lista del picker NO se dibuja: sus títulos asomarían por encima.
 *     EL MOUSE    el juego lo lee de los mensajes de la ventana (0x647650, el objeto de 0x9313E8: WM_MOUSEMOVE,
 *                 WM_LBUTTONDOWN… WM_MOUSEWHEEL). Nuestro WndProc va ANTES: con la ventana abierta se queda con
 *                 los clics, la ruedita y el Esc ⇒ no se elige una canción de abajo sin querer.
 *
 *   ⛔ [top5] activo=0 lo apaga entero. Perillas sin recompilar: [top5] boton_x/boton_y, ventana_x/ventana_y, z.
 *   ⚠ Se incluye DESPUÉS de picker.c (usa pk_raton, PKV…) y sólo se prende si el picker quedó enganchado.
 */
#include "top5_datos.h"

#define T5V(x) (g_t5_base + ((DWORD)(x) - 0x400000))
#define T5_MAX 16

typedef struct { char apodo[24]; WORD combo; DWORD pd; DWORD fecha; BYTE allc; DWORD frame; } T5_FILA;

static BYTE *g_t5_base = NULL;
static int   g_t5_activo = 0;

/* ── lo que mandó el server (la última cola «T5» leída) ── */
static WORD    g_t5_cancion = 0;
static int     g_t5_n = 0;
static T5_FILA g_t5_f[T5_MAX];
static int     g_t5_puesto = 0;               /* el mío; 0 = nunca la terminé */
static T5_FILA g_t5_mio;
static DWORD   g_t5_serie = 0;                /* sube con cada cola leída */
static BYTE    g_t5_crudo[1024];
static BYTE   *g_t5_salto = NULL;

/* ── la ventana ── */
static volatile int   g_t5_abierto = 0;
static volatile DWORD g_t5_visto = 0;         /* GetTickCount del último cuadro del picker */
static WORD  g_t5_panel_cancion = 0;          /* la canción del panel (del último cuadro) */
static char  g_t5_panel_titulo[128];
static WORD  g_t5_abierta_cancion = 0;        /* la canción con la que se abrió */
static char  g_t5_titulo[128];
static int   g_t5_scroll = 0;
static int   g_t5_x_apretada = 0, g_t5_boton_apretado = 0, g_t5_arrastre = 0, g_t5_arrastre_dy = 0;
static int   g_t5_bx = -9999, g_t5_by = -9999;   /* el botón en pantalla (del último cuadro) */
static int   g_t5_vx = -9999, g_t5_vy = -9999;   /* la ventana en pantalla */
static int   g_t5_boton_dx = 0, g_t5_boton_dy = 0, g_t5_ventana_dx = 0, g_t5_ventana_dy = 0;
/* ⛔⛔ LA PROFUNDIDAD (medido 09-oct con el diagnóstico de abajo): en z 0 NO se ve NADA. Todo lo visible del picker
 *   va en z > 0 (los íconos de la lista 0.32, los fondos 0.9, la banda de arriba 0.1); lo nuestro era lo único en 0.
 *   Lo mismo que el BPM de la sala (0 no, 0.32 sí). ⛔ Y 0.05 TAMPOCO se vio (2ª prueba de anonimo03): no es «> 0»,
 *   son los valores que el juego YA usa ⇒ 0.32, la de los íconos de la lista (= la de la portada en la sala). */
static float g_t5_z = 0.32f;
/* ★ la VENTANA va en 0.1 (la de la banda de arriba, el valor más chico que el juego usa en el picker: adelante de
 *   los íconos de la lista, que van en 0.32). Así la lista se sigue viendo DETRÁS, como en el coreano (anonimo03,
 *   09-oct: «al abrir este popup la info de atrás no desaparece, en el nuestro sí»). [top5] z_ventana, en milésimas.
 *   Si algún texto asomara por encima: [top5] ocultar_lista=1 vuelve a no dibujar la lista mientras está abierta. */
static float g_t5_z_ventana = 0.1f;
static int   g_t5_ocultar_lista = 0;

/* ── las imágenes ── */
static BYTE   g_t5_hoja[0x100], g_t5_lz[0x100];  /* los c2DImage (la clase ocupa 0x40) */
static int    g_t5_img_estado = 0;               /* 0 sin cargar · 1 lista · -1 no se usa */
static DWORD *g_t5_atlas = NULL;
static int    g_t5_atlas_w = 0, g_t5_atlas_h = 0;
static DWORD  g_t5_px[T5_W * T5_H];              /* la ventana armada en memoria */
static DWORD  g_t5_firma = 0;
static void  *g_t5_lz_tex = NULL;

/* ── GDI: los textos se escriben en blanco sobre negro en un recorte, y se pegan con el color ── */
#define T5_GDI_W 512
#define T5_GDI_H 40
static HDC    g_t5_dc = NULL;
static DWORD *g_t5_gdi = NULL;
static HFONT  g_t5_letra = NULL, g_t5_letra_titulo = NULL;

typedef void  (TCK *F_T5_LEER)(void *flujo, void *dest, int n);          /* 0x67D200, ret 8 */
typedef BYTE *(TCK *F_T5_TEX_ENTRADA)(void *mgr, DWORD h);
typedef void *(TCK *F_T5_TEX_D3D)(void *mgr, DWORD h, int cual);
typedef struct { UINT Format, Type, Usage, Pool, MSType, MSQuality, Width, Height; } T5_DESC;
typedef struct { INT Pitch; void *pBits; } T5_BLOQUEO;
typedef long (__stdcall *T5_T_DESC)(void *tex, UINT nivel, T5_DESC *d);                               /* vt 17 */
typedef long (__stdcall *T5_T_BLOQUEAR)(void *tex, UINT nivel, T5_BLOQUEO *r, const RECT *rc, DWORD b); /* vt 19 */
typedef long (__stdcall *T5_T_SOLTAR)(void *tex, UINT nivel);                                          /* vt 20 */

/* ═══ 1 · LA COLA DEL FF139 ═════════════════════════════════════════════════════════════════════════════════════
 *   El orden es un CONTRATO con servidor/picker.py (`cola_top5`):
 *     b"T5" · u16 canción · u16 largo · [largo B]: u8 n · n × FILA · u16 mi puesto · [FILA mía si el puesto ≠ 0]
 *     FILA = u8 L · apodo (L B, cp1252) · u16 combo · u32 precisión ×1000 · u32 fecha (epoch) · u8 all combo
 *            · u32 tiempo de llegada (pasos = 1/60 s, 0 = no se sabe) */
static int t5_fila(const BYTE *b, int largo, int *p, T5_FILA *f)
{
    if (*p + 1 > largo) return 0;
    int L = b[(*p)++];
    if (*p + L + 15 > largo) return 0;
    int c = L < (int)sizeof(f->apodo) - 1 ? L : (int)sizeof(f->apodo) - 1;
    CopyMemory(f->apodo, b + *p, c);
    f->apodo[c] = 0;
    *p += L;
    f->combo = *(const WORD *)(b + *p);
    f->pd = *(const DWORD *)(b + *p + 2);
    f->fecha = *(const DWORD *)(b + *p + 6);
    f->allc = b[*p + 10];
    f->frame = *(const DWORD *)(b + *p + 11);
    *p += 15;
    return 1;
}

/* la llama el salto, con el flujo del FF139 ya leído hasta las milésimas (esi) */
static void __stdcall t5_cola(void *flujo)
{
    F_T5_LEER leer = (F_T5_LEER)T5V(0x67D200);
    BYTE cab[6];
    ZeroMemory(cab, sizeof(cab));
    leer(flujo, cab, 6);                       /* ⚠ si no alcanzan los bytes, el lector NO toca el destino: queda 0 */
    if (cab[0] != 'T' || cab[1] != '5') return;  /* un server sin TOP 5 RANK: nada */
    WORD cancion = *(WORD *)(cab + 2);
    int largo = *(WORD *)(cab + 4);
    if (largo < 3 || largo > (int)sizeof(g_t5_crudo)) {
        apuntar("  [top5] ⚠ cola de %d B para la canción %u: no la leo", largo, cancion);
        return;
    }
    ZeroMemory(g_t5_crudo, sizeof(g_t5_crudo));
    leer(flujo, g_t5_crudo, largo);
    static T5_FILA f[T5_MAX];
    T5_FILA mio;
    ZeroMemory(&mio, sizeof(mio));
    int p = 0, n = g_t5_crudo[p++], guardadas = 0;
    for (int i = 0; i < n; i++) {
        T5_FILA x;
        if (!t5_fila(g_t5_crudo, largo, &p, &x)) { apuntar("  [top5] ⚠ la fila %d de la canción %u no cierra", i, cancion); return; }
        if (guardadas < T5_MAX) f[guardadas++] = x;
    }
    if (p + 2 > largo) { apuntar("  [top5] ⚠ la canción %u viene sin «mi puesto»", cancion); return; }
    int puesto = *(WORD *)(g_t5_crudo + p);
    p += 2;
    if (puesto && !t5_fila(g_t5_crudo, largo, &p, &mio)) { apuntar("  [top5] ⚠ «mi fila» de la canción %u no cierra", cancion); return; }
    CopyMemory(g_t5_f, f, sizeof(T5_FILA) * guardadas);
    g_t5_n = guardadas;
    g_t5_mio = mio;
    g_t5_puesto = puesto;
    g_t5_cancion = cancion;
    g_t5_serie++;
    static int dichas = 0;
    if (dichas < 5) {
        dichas++;
        apuntar("  [top5] la canción %u: %d en el ranking, yo %d%s", cancion, guardadas, puesto,
                dichas == 5 ? " (no anoto más)" : "");
    }
}

/* el cave de las milésimas del exe (record_decimales.py, 0x835470), TAL CUAL. Tras su lectura vuelve con
 *   `mov ecx,[esp+0xC] · mov edx,[esp+0x10] · jmp 0x5DC672` (0x835485): eso se cambia por nuestro salto. */
static int t5_enganchar_ff139(void)
{
    static const BYTE CUEVA[0x22] = {
        0x66, 0xC7, 0x44, 0x24, 0x06, 0xFF, 0xFF, 0x6A, 0x02, 0x8D, 0x44, 0x24, 0x0A, 0x50, 0x89, 0xF1, 0xE8,
        0x7B, 0x7D, 0xE4, 0xFF, 0x8B, 0x4C, 0x24, 0x0C, 0x8B, 0x54, 0x24, 0x10, 0xE9, 0xE0, 0x71, 0xDA, 0xFF };
    static const BYTE SALTO[5] = { 0xE9, 0x01, 0x8E, 0x25, 0x00 };          /* 0x5DC66A: jmp 0x835470 */
    if (memcmp(T5V(0x835470), CUEVA, sizeof(CUEVA)) != 0 || memcmp(T5V(0x5DC66A), SALTO, 5) != 0) {
        apuntar("  [top5] ⛔ el exe no trae el cave de las milésimas de «Mi record» (0x835470): sin TOP 5 RANK");
        return 0;
    }
    g_t5_salto = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_t5_salto) { apuntar("  [top5] ⛔ sin memoria para el salto"); return 0; }
    BYTE *k = g_t5_salto;
    int i = 0;
    k[i++] = 0x60;                                                                              /* pushad */
    k[i++] = 0x56;                                                                              /* push esi */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)t5_cola - (DWORD)(k + i + 5)); i += 5;      /* call t5_cola */
    k[i++] = 0x61;                                                                              /* popad */
    k[i++] = 0x8B; k[i++] = 0x4C; k[i++] = 0x24; k[i++] = 0x0C;                                 /* mov ecx,[esp+0xC] */
    k[i++] = 0x8B; k[i++] = 0x54; k[i++] = 0x24; k[i++] = 0x10;                                 /* mov edx,[esp+0x10] */
    k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)T5V(0x5DC672) - (DWORD)(k + i + 5)); i += 5; /* jmp 0x5DC672 */
    BYTE n[13] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
    *(int *)(n + 1) = (int)((DWORD)g_t5_salto - ((DWORD)T5V(0x835485) + 5));
    DWORD viejo = 0;
    if (!VirtualProtect(T5V(0x835485), 13, PAGE_EXECUTE_READWRITE, &viejo)) { apuntar("  [top5] ⛔ VirtualProtect (FF139)"); return 0; }
    CopyMemory(T5V(0x835485), n, 13);
    VirtualProtect(T5V(0x835485), 13, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), T5V(0x835485), 13);
    return 1;
}

/* ═══ 2 · LAS IMÁGENES ══════════════════════════════════════════════════════════════════════════════════════════
 *   La textura de un c2DImage (medido para la calculadora, CALCULADORA_2019_EN_EL_2013.md §9):
 *   [img+4] = handle -> 0x4099E0(mgr=[0x931570], h) -> entrada (+0x48 != 0 = animada) -> 0x441420(mgr, h, 0). */
static void *t5_textura(BYTE *img)
{
    void *mgr = *(void **)T5V(0x931570);
    DWORD h = *(DWORD *)(img + 4);
    if (!mgr || !h) return NULL;
    BYTE *ent = ((F_T5_TEX_ENTRADA)T5V(0x4099E0))(mgr, h);
    if (!ent || *(DWORD *)(ent + 0x48)) return NULL;
    return ((F_T5_TEX_D3D)T5V(0x441420))(mgr, h, 0);
}

static int t5_desc(void *tex, T5_DESC *d)
{
    void **vt = tex ? *(void ***)tex : NULL;
    return vt && ((T5_T_DESC)vt[17])(tex, 0, d) == 0;
}

static int t5_gdi_preparar(void)
{
    g_t5_dc = CreateCompatibleDC(NULL);
    if (!g_t5_dc) return 0;
    BITMAPINFO bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = T5_GDI_W;
    bi.bmiHeader.biHeight = -T5_GDI_H;                     /* de arriba hacia abajo */
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(g_t5_dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (!bmp || !bits) return 0;
    SelectObject(g_t5_dc, bmp);
    g_t5_gdi = (DWORD *)bits;
    /* ⚠ ANTIALIASED_QUALITY y no ClearType: el borde suave tiene que ser GRIS (lo usamos de alfa) */
    g_t5_letra = CreateFontW(-13, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                             ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Segoe UI");
    g_t5_letra_titulo = CreateFontW(-16, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS,
                                    CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Segoe UI");
    SetBkMode(g_t5_dc, TRANSPARENT);
    SetTextColor(g_t5_dc, RGB(255, 255, 255));
    return g_t5_letra && g_t5_letra_titulo;
}

static void t5_cargar(void)
{
    g_t5_img_estado = -1;
    typedef void *(TCK *F_CREAR)(void *self);
    typedef int   (TCK *F_CARGAR)(void *self, const char *ruta, const char *prefijo);
    typedef void  (TCK *F_RECORTE)(void *self, float x, float y, int u, int v, int w, int h, float z);
    F_RECORTE rec = (F_RECORTE)T5V(0x64EC40);
    ((F_CREAR)T5V(0x64E560))(g_t5_hoja);
    if (!((F_CARGAR)T5V(0x64E1E0))(g_t5_hoja, T5_HOJA_TGA, NULL)) {
        apuntar("  [top5] ⛔ no encontré %s (¿falta rnr_ui_top5.pak?): sin TOP 5 RANK", T5_HOJA_TGA);
        return;
    }
    for (int i = 0; i < 3; i++)
        rec(g_t5_hoja, 0, 0, T5_BOTON_CORTE[i][0], T5_BOTON_CORTE[i][1], T5_BOTON_W, T5_BOTON_H, g_t5_z);
    /* la hoja, a memoria (una vez): de ahí sale el fondo de la ventana y la X */
    void *tex = t5_textura(g_t5_hoja);
    T5_DESC d;
    if (!tex || !t5_desc(tex, &d) || d.Format != 21 /* A8R8G8B8 */) {
        apuntar("  [top5] ⛔ no pude leer la hoja (tex=%p fmt=%u): sin TOP 5 RANK", tex, tex ? d.Format : 0);
        return;
    }
    void **vt = *(void ***)tex;
    T5_BLOQUEO b;
    if (((T5_T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, 0x10 /* READONLY */) != 0) {
        apuntar("  [top5] ⛔ la hoja no se deja leer (pool %u): sin TOP 5 RANK", d.Pool);
        return;
    }
    g_t5_atlas = (DWORD *)HeapAlloc(GetProcessHeap(), 0, d.Width * d.Height * 4);
    if (g_t5_atlas)
        for (UINT y = 0; y < d.Height; y++)
            CopyMemory(g_t5_atlas + y * d.Width, (BYTE *)b.pBits + y * b.Pitch, d.Width * 4);
    ((T5_T_SOLTAR)vt[20])(tex, 0);
    if (!g_t5_atlas) return;
    g_t5_atlas_w = (int)d.Width;
    g_t5_atlas_h = (int)d.Height;
    if (g_t5_atlas_w < T5_W || g_t5_atlas_h < T5_H) { apuntar("  [top5] ⛔ la hoja mide %dx%d", g_t5_atlas_w, g_t5_atlas_h); return; }
    /* el lienzo */
    ((F_CREAR)T5V(0x64E560))(g_t5_lz);
    if (!((F_CARGAR)T5V(0x64E1E0))(g_t5_lz, T5_LIENZO_TGA, NULL)) {
        apuntar("  [top5] ⛔ no encontré %s: sin TOP 5 RANK", T5_LIENZO_TGA);
        return;
    }
    rec(g_t5_lz, 0, 0, 0, 0, T5_W, T5_H, g_t5_z_ventana);
    tex = t5_textura(g_t5_lz);
    if (!tex || !t5_desc(tex, &d) || d.Format != 21 || d.Width < T5_W || d.Height < T5_H) {
        apuntar("  [top5] ⛔ el lienzo no es el esperado (fmt %u, %ux%u): sin TOP 5 RANK", tex ? d.Format : 0,
                tex ? d.Width : 0, tex ? d.Height : 0);
        return;
    }
    if (!t5_gdi_preparar()) { apuntar("  [top5] ⛔ GDI: no pude preparar la letra: sin TOP 5 RANK"); return; }
    g_t5_img_estado = 1;
    apuntar("  [top5] ★ listo: hoja %dx%d, lienzo (pool %u), letra Segoe UI", g_t5_atlas_w, g_t5_atlas_h, d.Pool);
}

/* ═══ 3 · ARMAR LA VENTANA EN MEMORIA ═══════════════════════════════════════════════════════════════════════════ */
static void t5_mezclar(DWORD *p, DWORD col, int a)        /* col sobre *p con alfa a (0..255) */
{
    if (a <= 0) return;
    if (a > 255) a = 255;
    DWORD d = *p;
    int da = (int)(d >> 24);
    int ra = a + da * (255 - a) / 255;
    if (ra <= 0) return;
    DWORD r = (DWORD)ra << 24;
    for (int sh = 0; sh < 24; sh += 8) {
        int sc = (int)((col >> sh) & 255), dc = (int)((d >> sh) & 255);
        int c = (sc * a + dc * da * (255 - a) / 255) / ra;
        r |= (DWORD)(c > 255 ? 255 : c) << sh;
    }
    *p = r;
}

static void t5_pegar(int sx, int sy, int w, int h, int dx, int dy)      /* de la hoja a la ventana */
{
    for (int j = 0; j < h; j++) {
        int yy = dy + j, ys = sy + j;
        if (yy < 0 || yy >= T5_H || ys < 0 || ys >= g_t5_atlas_h) continue;
        for (int i = 0; i < w; i++) {
            int xx = dx + i, xs = sx + i;
            if (xx < 0 || xx >= T5_W || xs < 0 || xs >= g_t5_atlas_w) continue;
            DWORD s = g_t5_atlas[ys * g_t5_atlas_w + xs];
            t5_mezclar(&g_t5_px[yy * T5_W + xx], s | 0xFF000000, (int)(s >> 24));
        }
    }
}

static void t5_velo(int x0, int y0, int x1, int y1, DWORD col, int a)   /* un rectángulo translúcido */
{
    for (int y = y0 < 0 ? 0 : y0; y < y1 && y < T5_H; y++)
        for (int x = x0 < 0 ? 0 : x0; x < x1 && x < T5_W; x++)
            t5_mezclar(&g_t5_px[y * T5_W + x], col, a);
}

/* un texto (cp1252, como los apodos del server y los títulos del catálogo), con borde de 1 px.
 *   alin: 0 = empieza en x · 1 = centrado en x · 2 = termina en x.  cy = el centro vertical. */
static void t5_texto(int x, int cy, int alin, HFONT letra, const char *s, int ancho_max, DWORD color, DWORD borde)
{
    WCHAR w[160];
    int n = id_a_ancho(s, w, 158);
    if (n <= 1) return;
    n--;                                                     /* sin el 0 del final */
    SelectObject(g_t5_dc, letra);
    SIZE t;
    GetTextExtentPoint32W(g_t5_dc, w, n, &t);
    if (ancho_max > 0 && t.cx > ancho_max) {                  /* «UnApodoMuyLargo…» */
        while (n > 1 && t.cx > ancho_max) {
            n--;
            w[n - 1] = 0x2026;
            GetTextExtentPoint32W(g_t5_dc, w, n, &t);
        }
    }
    ZeroMemory(g_t5_gdi, T5_GDI_W * T5_GDI_H * 4);
    TextOutW(g_t5_dc, 2, 2, w, n);
    GdiFlush();
    int x0 = alin == 0 ? x : alin == 1 ? x - t.cx / 2 : x - t.cx;
    int y0 = cy - t.cy / 2;
    int ancho = t.cx + 4 > T5_GDI_W ? T5_GDI_W : t.cx + 4, alto = t.cy + 4 > T5_GDI_H ? T5_GDI_H : t.cy + 4;
    int ba = (int)(borde >> 24), ca = (int)(color >> 24);
    for (int pasada = (ba ? 0 : 1); pasada < 2; pasada++)
        for (int j = 0; j < alto; j++) {
            int yy = y0 - 2 + j;
            if (yy < 0 || yy >= T5_H) continue;
            for (int i = 0; i < ancho; i++) {
                int xx = x0 - 2 + i;
                if (xx < 0 || xx >= T5_W) continue;
                int cob;
                if (pasada == 0) {                           /* el borde: lo más fuerte del vecindario */
                    cob = 0;
                    for (int v = -1; v <= 1; v++)
                        for (int u = -1; u <= 1; u++) {
                            int a = i + u, b = j + v;
                            if (a < 0 || b < 0 || a >= T5_GDI_W || b >= T5_GDI_H) continue;
                            int g = (int)((g_t5_gdi[b * T5_GDI_W + a] >> 8) & 255);
                            if (g > cob) cob = g;
                        }
                    t5_mezclar(&g_t5_px[yy * T5_W + xx], borde, cob * ba / 255);
                } else {
                    cob = (int)((g_t5_gdi[j * T5_GDI_W + i] >> 8) & 255);
                    t5_mezclar(&g_t5_px[yy * T5_W + xx], color, cob * ca / 255);
                }
            }
        }
}

#define T5_BLANCO   0xFFFFFFFF
#define T5_BORDE    0xFF08101E      /* el halo oscuro de los rótulos del panel (picker_bpm.HALO_OSCURO) */
#define T5_AMARILLO 0xFFFFE65A

static void t5_fecha(DWORD epoch, char *s)                   /* dd/mm/aaaa, hora local */
{
    if (!epoch) { lstrcpyA(s, "-"); return; }
    ULONGLONG t = ((ULONGLONG)epoch + 11644473600ULL) * 10000000ULL;
    FILETIME fu, fl;
    SYSTEMTIME st;
    fu.dwLowDateTime = (DWORD)t;
    fu.dwHighDateTime = (DWORD)(t >> 32);
    if (!FileTimeToLocalFileTime(&fu, &fl) || !FileTimeToSystemTime(&fl, &st)) { lstrcpyA(s, "-"); return; }
    wsprintfA(s, "%02u/%02u/%04u", st.wDay, st.wMonth, st.wYear);
}

static void t5_una_fila(int y0, int alto, int puesto, const T5_FILA *f, DWORD color_puesto)
{
    char t[40];
    int cy = y0 + alto / 2;
    wsprintfA(t, "%d", puesto);
    t5_texto(T5_COL_PUESTO, cy, 1, g_t5_letra, t, 0, color_puesto, T5_BORDE);
    t5_texto(T5_COL_APODO, cy, 1, g_t5_letra, f->apodo, T5_APODO_ANCHO, T5_BLANCO, T5_BORDE);
    wsprintfA(t, "%u", (unsigned)f->combo);
    t5_texto(T5_COL_COMBO, cy, 1, g_t5_letra, t, 0, f->allc ? T5_AMARILLO : T5_BLANCO, T5_BORDE);  /* all combo: dorado */
    wsprintfA(t, "%u.%03u%%", (unsigned)(f->pd / 1000), (unsigned)(f->pd % 1000));
    t5_texto(T5_COL_PREC, cy, 1, g_t5_letra, t, 0, T5_BLANCO, T5_BORDE);
    t5_fecha(f->fecha, t);
    t5_texto(T5_COL_FECHA, cy, 1, g_t5_letra, t, 0, T5_BLANCO, T5_BORDE);
    if (f->frame > 0 && f->frame < 60u * 60 * 60) {            /* el tiempo de llegada: pasos de 1/60 s -> m:ss */
        DWORD s = f->frame / 60;
        wsprintfA(t, "%u:%02u", (unsigned)(s / 60), (unsigned)(s % 60));
    } else lstrcpyA(t, "-");
    t5_texto(T5_COL_TIEMPO, cy, 1, g_t5_letra, t, 0, T5_BLANCO, T5_BORDE);
}

static int t5_datos_listos(void) { return g_t5_serie && g_t5_cancion == g_t5_abierta_cancion; }

static void t5_barra(int *y, int *alto)                      /* la barrita: dónde va y cuánto mide */
{
    int pista = T5_BARRA_Y1 - T5_BARRA_Y0, sobra = g_t5_n - T5_FILAS;
    int h = pista * T5_FILAS / (g_t5_n > 0 ? g_t5_n : 1);
    if (h < 20) h = 20;
    *alto = h;
    *y = T5_BARRA_Y0 + (sobra > 0 ? (pista - h) * g_t5_scroll / sobra : 0);
}

static void t5_armar(int x_estado)
{
    static const DWORD ORO[3] = { 0xFFFFD640, 0xFFDEE8F2, 0xFFECA05C };
    for (int y = 0; y < T5_H; y++)
        CopyMemory(g_t5_px + y * T5_W, g_t5_atlas + y * g_t5_atlas_w, T5_W * 4);
    t5_pegar(T5_X_CORTE[x_estado][0], T5_X_CORTE[x_estado][1], T5_X_TAM, T5_X_TAM, T5_X_X, T5_X_Y);
    /* sobre la franja verde agua: blanco con borde verde petróleo, como «Seleccionar velocidad» (10-oct) */
    t5_texto(T5_W / 2, T5_TITULO_Y, 1, g_t5_letra_titulo, g_t5_titulo, 400, T5_BLANCO, 0xFF0C4E62);
    int medio = (T5_FILA_Y[0] + T5_FILA_Y[T5_FILAS - 1] + T5_FILA_H) / 2;
    if (!t5_datos_listos()) {
        t5_texto(T5_W / 2, medio, 1, g_t5_letra, "Cargando\x85", 0, T5_BLANCO, T5_BORDE);
        return;
    }
    if (g_t5_n == 0)
        t5_texto(T5_W / 2, medio, 1, g_t5_letra, "Nadie termin\xF3 esta canci\xF3n todav\xED" "a", 0, T5_BLANCO, T5_BORDE);
    for (int i = 0; i < T5_FILAS; i++) {
        int k = g_t5_scroll + i;
        if (k >= g_t5_n) break;
        const T5_FILA *f = &g_t5_f[k];
        if (g_t5_puesto == k + 1)                             /* mi fila, aclarada */
            t5_velo(4, T5_FILA_Y[i], T5_W - 14, T5_FILA_Y[i] + T5_FILA_H, 0xFFFFFFFF, 34);
        t5_una_fila(T5_FILA_Y[i], T5_FILA_H, k + 1, f, k < 3 ? ORO[k] : T5_BLANCO);
    }
    if (g_t5_n > T5_FILAS) {
        int by, bh;
        t5_barra(&by, &bh);
        t5_velo(T5_BARRA_X, T5_BARRA_Y0, T5_BARRA_X + 6, T5_BARRA_Y1, 0xFF00303C, 120);
        t5_velo(T5_BARRA_X, by, T5_BARRA_X + 6, by + bh, 0xFFAAE1F0, 230);
    }
    if (g_t5_puesto)
        t5_una_fila(T5_MIO_Y, T5_MIO_H, g_t5_puesto, &g_t5_mio, T5_AMARILLO);
    else
        t5_texto(T5_W / 2, T5_MIO_Y + T5_MIO_H / 2, 1, g_t5_letra, "Todav\xED" "a no terminaste esta canci\xF3n", 0,
                 0xFFB4D2DC, T5_BORDE);
}

/* a la textura del lienzo (sólo lo usado: T5_W × T5_H) */
static int t5_subir(void *tex)
{
    void **vt = *(void ***)tex;
    T5_BLOQUEO b;
    if (((T5_T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, 0) != 0) return 0;
    for (int y = 0; y < T5_H; y++)
        CopyMemory((BYTE *)b.pBits + y * b.Pitch, g_t5_px + y * T5_W, T5_W * 4);
    ((T5_T_SOLTAR)vt[20])(tex, 0);
    return 1;
}

/* ═══ 4 · CADA CUADRO DEL PICKER (lo llama pk_lista) ════════════════════════════════════════════════════════════ */
typedef void (TCK *F_T5_POS)(void *self, int n, int x, int y);
typedef void (TCK *F_T5_COLOR)(void *self, int n, DWORD argb);
typedef void (TCK *F_T5_DIBUJAR)(void *self, int n, int banderas);

static void t5_figura(BYTE *img, int n, int x, int y)
{
    ((F_T5_POS)T5V(0x64D990))(img, n, x, y);
    ((F_T5_COLOR)T5V(0x64E710))(img, n, 0xFFFFFFFF);
    ((F_T5_DIBUJAR)T5V(0x64EE40))(img, n, 0);
}

static int t5_dentro(int x, int y, int x0, int y0, int w, int h)
{
    return x >= x0 && x < x0 + w && y >= y0 && y < y0 + h;
}

static int top5_abierto(void) { return g_t5_activo && g_t5_abierto; }
static int top5_tapa_lista(void) { return top5_abierto() && g_t5_ocultar_lista; }

static void top5_diag_fase(int fase);
static void t5_cuadro(BYTE *c, int dx, int dy);

static void top5_cuadro(BYTE *c, int dx, int dy)
{
    top5_diag_fase(2);
    t5_cuadro(c, dx, dy);
    top5_diag_fase(3);
}

static void t5_cuadro(BYTE *c, int dx, int dy)
{
    if (!g_t5_activo) return;
    if (g_t5_img_estado == 0) t5_cargar();
    if (g_t5_img_estado != 1) return;
    g_t5_visto = GetTickCount();
    g_t5_panel_cancion = c ? *(WORD *)(c + 0x594) : 0;
    if (c) lstrcpynA(g_t5_panel_titulo, (const char *)(c + 0x21C), sizeof(g_t5_panel_titulo));   /* el título (0x5B9145) */
    g_t5_bx = dx + T5_BOTON_DLG_X + g_t5_boton_dx;
    g_t5_by = dy + T5_BOTON_DLG_Y + g_t5_boton_dy;
    g_t5_vx = dx + T5_VENTANA_DLG_X + g_t5_ventana_dx;
    g_t5_vy = dy + T5_VENTANA_DLG_Y + g_t5_ventana_dy;
    int mx = -9999, my = -9999;
    if (!(GetForegroundWindow() == g_ventana && pk_raton(&mx, &my))) mx = my = -9999;
    if (!g_t5_abierto) {
        int est = g_t5_boton_apretado ? 2 : t5_dentro(mx, my, g_t5_bx, g_t5_by, T5_BOTON_W, T5_BOTON_H) ? 1 : 0;
        t5_figura(g_t5_hoja, est, g_t5_bx, g_t5_by);
        return;
    }
    int sobre_x = t5_dentro(mx - g_t5_vx, my - g_t5_vy, T5_X_X, T5_X_Y, T5_X_TAM, T5_X_TAM);
    int x_estado = (g_t5_x_apretada && sobre_x) ? 2 : sobre_x ? 1 : 0;
    void *tex = t5_textura(g_t5_lz);
    if (!tex) return;
    DWORD firma = (t5_datos_listos() ? g_t5_serie * 2654435761u : 1u) ^ ((DWORD)g_t5_abierta_cancion << 16)
                  ^ ((DWORD)g_t5_scroll << 4) ^ (DWORD)x_estado ^ 0x80000000u;
    if (firma != g_t5_firma || tex != g_t5_lz_tex) {        /* algo cambió (o el juego rehízo la textura) */
        t5_armar(x_estado);
        if (t5_subir(tex)) { g_t5_firma = firma; g_t5_lz_tex = tex; }
    }
    t5_figura(g_t5_lz, 0, g_t5_vx, g_t5_vy);
}

/* ═══ 5 · EL MOUSE Y EL TECLADO (lo llama el WndProc de d3d9_proxy.c ANTES que al juego) ═════════════════════════
 *   Devuelve 1 si el mensaje es nuestro (el juego no lo ve). */
static void t5_abrir(void)
{
    g_t5_abierta_cancion = g_t5_panel_cancion;
    lstrcpynA(g_t5_titulo, g_t5_panel_titulo, sizeof(g_t5_titulo));
    g_t5_scroll = 0;
    g_t5_x_apretada = g_t5_arrastre = 0;
    g_t5_firma = 0;
    g_t5_abierto = 1;
    apuntar("  [top5] abierto: canción %u «%s» (%s)", g_t5_abierta_cancion, g_t5_titulo,
            t5_datos_listos() ? "con datos" : "esperando el FF139");
}

static void t5_cerrar(const char *como)
{
    g_t5_abierto = 0;
    g_t5_x_apretada = g_t5_arrastre = 0;
    apuntar("  [top5] cerrado (%s)", como);
}

static int t5_a_juego(HWND h, LPARAM lp, int de_pantalla, int *x, int *y)
{
    POINT p;
    RECT r;
    p.x = (short)LOWORD(lp);
    p.y = (short)HIWORD(lp);
    if (de_pantalla && !ScreenToClient(h, &p)) return 0;      /* la ruedita viene en coordenadas de PANTALLA */
    if (!GetClientRect(h, &r) || r.right <= 0 || r.bottom <= 0) return 0;
    *x = g_ancho ? (int)((LONGLONG)p.x * (LONGLONG)g_ancho / r.right) : p.x;
    *y = g_alto ? (int)((LONGLONG)p.y * (LONGLONG)g_alto / r.bottom) : p.y;
    return 1;
}

static void t5_mover_scroll(int nuevo)
{
    int tope = g_t5_n - T5_FILAS;
    if (tope < 0) tope = 0;
    g_t5_scroll = nuevo < 0 ? 0 : nuevo > tope ? tope : nuevo;
}

static int g_t5_tragar_esc = 0;

static int top5_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    if (!g_t5_activo || g_t5_img_estado != 1) return 0;
    if (GetTickCount() - g_t5_visto > 300) {                  /* el picker no se está dibujando: nada nuestro */
        if (g_t5_abierto) t5_cerrar("se fue el picker");
        g_t5_boton_apretado = 0;
        return 0;
    }
    if (wp == VK_ESCAPE && (msg == WM_KEYDOWN || msg == WM_KEYUP || msg == WM_CHAR)) {
        if (g_t5_abierto && msg == WM_KEYDOWN) { t5_cerrar("Esc"); g_t5_tragar_esc = 2; return 1; }
        if (g_t5_tragar_esc && msg != WM_KEYDOWN) { g_t5_tragar_esc--; return 1; }   /* su WM_CHAR y su WM_KEYUP */
        return g_t5_abierto;
    }
    if (msg < WM_MOUSEFIRST || msg > 0x20E) return 0;
    int x, y;
    if (!t5_a_juego(h, lp, msg == WM_MOUSEWHEEL || msg == 0x20E, &x, &y)) return 0;
    if (!g_t5_abierto) {
        int en = t5_dentro(x, y, g_t5_bx, g_t5_by, T5_BOTON_W, T5_BOTON_H);
        if ((msg == WM_LBUTTONDOWN || msg == WM_LBUTTONDBLCLK) && en && g_t5_panel_cancion) {
            g_t5_boton_apretado = 1;
            return 1;
        }
        if (msg == WM_LBUTTONUP && g_t5_boton_apretado) {
            g_t5_boton_apretado = 0;
            if (en && g_t5_panel_cancion) t5_abrir();
            return 1;
        }
        return 0;
    }
    /* ABIERTA: el mouse es nuestro (salvo el movimiento, que el juego usa para su cursor) */
    int lx = x - g_t5_vx, ly = y - g_t5_vy;
    int hay_barra = t5_datos_listos() && g_t5_n > T5_FILAS;
    switch (msg) {
    case WM_MOUSEMOVE:
        if (g_t5_arrastre && hay_barra) {
            int by, bh;
            t5_barra(&by, &bh);
            int pista = T5_BARRA_Y1 - T5_BARRA_Y0 - bh;
            if (pista > 0) t5_mover_scroll(((ly - g_t5_arrastre_dy - T5_BARRA_Y0) * (g_t5_n - T5_FILAS) + pista / 2) / pista);
        }
        return 0;
    case WM_LBUTTONDOWN:
    case WM_LBUTTONDBLCLK:
        if (t5_dentro(lx, ly, T5_X_X, T5_X_Y, T5_X_TAM, T5_X_TAM)) g_t5_x_apretada = 1;
        else if (hay_barra && t5_dentro(lx, ly, T5_BARRA_X - 6, T5_BARRA_Y0, 18, T5_BARRA_Y1 - T5_BARRA_Y0)) {
            int by, bh;
            t5_barra(&by, &bh);
            if (ly >= by && ly < by + bh) { g_t5_arrastre = 1; g_t5_arrastre_dy = ly - by; }
            else t5_mover_scroll(g_t5_scroll + (ly < by ? -T5_FILAS : T5_FILAS));
        }
        return 1;
    case WM_LBUTTONUP:
        if (g_t5_x_apretada && t5_dentro(lx, ly, T5_X_X, T5_X_Y, T5_X_TAM, T5_X_TAM)) t5_cerrar("la X");
        g_t5_x_apretada = 0;
        g_t5_arrastre = 0;
        return 1;
    case WM_MOUSEWHEEL: {
        int d = (short)HIWORD(wp);
        if (hay_barra) t5_mover_scroll(g_t5_scroll + (d > 0 ? -1 : 1) * (d >= 120 || d <= -120 ? (d > 0 ? d : -d) / 120 : 1));
        return 1;
    }
    default:
        return 1;                                             /* el botón derecho, el del medio… */
    }
}

static int top5_quiere_ventana(void) { return g_t5_activo; }

/* ═══ ⏳ DIAGNÓSTICO (09-oct, 1ª prueba de anonimo03: «el botón está invisible, sí lo puedo presionar · el popup no se
 *   renderizó»). Los datos llegan y el clic anda; lo que no se ve es el DIBUJO. Se mide qué entra a la cola de
 *   dibujo del juego (0x554D30, la que llama 0x64EE40) en un cuadro del picker: las figuritas de la lista (que SÍ
 *   se ven) contra las nuestras, y si la reserva de entradas de la cola se acaba (0x554D45: sin lugar, NO dibuja
 *   y no avisa). [top5] diag=0 lo apaga. */
typedef void (TCK *F_T5_ENCOLAR)(void *cola, void *ent);
static F_T5_ENCOLAR g_t5_encolar_real = NULL;
static int   g_t5_diag = 1;
static volatile int g_t5_fase = 0;              /* 0 fuera del picker · 1 la lista · 2 lo nuestro */
static int   g_t5_grabar = 0, g_t5_gn = 0, g_t5_grabados = 0;
static BYTE  g_t5_ge[64][0x50];
static int   g_t5_gfase[64], g_t5_glibre[64];
static DWORD g_t5_cuenta = 0, g_t5_caidas = 0, g_t5_cuenta_ant = 0, g_t5_caidas_ant = 0, g_t5_ult_aviso = 0;

static void TCK t5_encolar(void *cola, void *ent)
{
    BYTE *res = *(BYTE **)((BYTE *)cola + 4) + 4;                 /* la reserva (0x554D33..0x554D40) */
    int libre = (int)((*(DWORD *)(res + 0x10) - *(DWORD *)(res + 0xC)) >> 2);
    g_t5_cuenta++;
    if (libre <= 0) g_t5_caidas++;
    static int por_fase[4];
    if (g_t5_grabar && g_t5_gn == 0) por_fase[1] = por_fase[2] = por_fase[3] = 0;
    /* de la lista y de lo de después, unas pocas (la lista sola llena la tabla); lo nuestro, todo */
    if (g_t5_grabar && g_t5_fase && g_t5_gn < 64 && (g_t5_fase == 2 || por_fase[g_t5_fase] < 16)) {
        por_fase[g_t5_fase]++;
        CopyMemory(g_t5_ge[g_t5_gn], ent, 0x50);
        g_t5_gfase[g_t5_gn] = g_t5_fase;
        g_t5_glibre[g_t5_gn] = libre;
        g_t5_gn++;
    }
    g_t5_encolar_real(cola, ent);
}

/* lo llama pk_lista al empezar (fase 1) y top5_cuadro (fase 2) */
static void top5_diag_fase(int fase)
{
    if (!g_t5_diag || !g_t5_encolar_real) return;
    if (fase == 1) {
        /* un cuadro entero = de un pk_lista al siguiente */
        g_t5_cuenta_ant = g_t5_cuenta;
        g_t5_caidas_ant = g_t5_caidas;
        g_t5_cuenta = g_t5_caidas = 0;
        DWORD t = GetTickCount();
        if (t - g_t5_ult_aviso > 5000) {
            g_t5_ult_aviso = t;
            apuntar("  [top5] diag: la cola recibió %lu figuritas en el último cuadro, %lu SIN LUGAR (abierto=%d)",
                    g_t5_cuenta_ant, g_t5_caidas_ant, g_t5_abierto);
        }
        /* graba un cuadro con el botón y otro con la ventana abierta */
        if (g_t5_grabar) {
            apuntar("  [top5] diag: %d entradas grabadas (abierto=%d). fase · libre · 20 dwords:", g_t5_gn, g_t5_abierto);
            for (int i = 0; i < g_t5_gn; i++) {
                DWORD *d = (DWORD *)g_t5_ge[i];
                char l[300];
                int n = wsprintfA(l, "    %d %4d |", g_t5_gfase[i], g_t5_glibre[i]);
                for (int k = 0; k < 20; k++) n += wsprintfA(l + n, " %08lX", d[k]);
                apuntar("%s", l);
            }
            g_t5_grabar = 0;
            g_t5_grabados++;
        } else if ((g_t5_grabados == 0 && !g_t5_abierto) || (g_t5_grabados == 1 && g_t5_abierto)) {
            g_t5_grabar = 1;
            g_t5_gn = 0;
        }
    }
    g_t5_fase = fase;
}

static void t5_enganchar_diag(void)
{
    static const BYTE E[6] = { 0x53, 0x8B, 0xD9, 0x8B, 0x43, 0x04 };   /* push ebx · mov ebx,ecx · mov eax,[ebx+4] */
    if (memcmp(T5V(0x554D30), E, 6) != 0) { apuntar("  [top5] diag: 0x554D30 no es el esperado: sin diagnóstico"); return; }
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return;
    CopyMemory(k, E, 6);
    k[6] = 0xE9; *(int *)(k + 7) = (int)((DWORD)T5V(0x554D36) - (DWORD)(k + 11));
    g_t5_encolar_real = (F_T5_ENCOLAR)k;
    BYTE n[6] = { 0xE9, 0, 0, 0, 0, 0x90 };
    *(int *)(n + 1) = (int)((DWORD)t5_encolar - ((DWORD)T5V(0x554D30) + 5));
    DWORD viejo = 0;
    if (!VirtualProtect(T5V(0x554D30), 6, PAGE_EXECUTE_READWRITE, &viejo)) { g_t5_encolar_real = NULL; return; }
    CopyMemory(T5V(0x554D30), n, 6);
    VirtualProtect(T5V(0x554D30), 6, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), T5V(0x554D30), 6);
    apuntar("  [top5] diag: la cola de dibujo (0x554D30) enganchada para medir");
}

static void top5_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("top5", "activo", 1, ini)) { apuntar("  [top5] apagado ([top5] activo=0)"); return; }
    if (!g_pk_lista_real) { apuntar("  [top5] el picker no quedó enganchado: sin TOP 5 RANK"); return; }
    g_t5_base = (BYTE *)GetModuleHandleA(NULL);
    g_t5_boton_dx = GetPrivateProfileIntA("top5", "boton_x", 0, ini);
    g_t5_boton_dy = GetPrivateProfileIntA("top5", "boton_y", 0, ini);
    g_t5_ventana_dx = GetPrivateProfileIntA("top5", "ventana_x", 0, ini);
    g_t5_ventana_dy = GetPrivateProfileIntA("top5", "ventana_y", 0, ini);
    g_t5_z = (float)GetPrivateProfileIntA("top5", "z", 320, ini) / 1000.0f;
    g_t5_z_ventana = (float)GetPrivateProfileIntA("top5", "z_ventana", 100, ini) / 1000.0f;
    g_t5_ocultar_lista = GetPrivateProfileIntA("top5", "ocultar_lista", 0, ini);
    if (!t5_enganchar_ff139()) return;
    g_t5_diag = GetPrivateProfileIntA("top5", "diag", 0, ini);
    if (g_t5_diag) t5_enganchar_diag();
    g_t5_activo = 1;
    apuntar("  [top5] ok: la cola «T5» del FF139 (0x835485), el botón y la ventana (corridos %d,%d / %d,%d)",
            g_t5_boton_dx, g_t5_boton_dy, g_t5_ventana_dx, g_t5_ventana_dy);
}
