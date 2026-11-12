/* cartel12.c — EL CARTEL DE RESULTADO DE LA CARRERA DE 12 (11-oct-2026). Doc: documentacion/MODO_6VS6.md §17.
 *
 *   El cartel de fábrica es de 6: con 12 filas se le encimaban (anonimo03, 11-oct, con los NPC que ya juegan). El diseño
 *   es el que eligió anonimo03, `taller/cartel12/maqueta_K_final.png`; la hoja y las medidas las arma
 *   `herramientas/cartel12_crear.py` (cartel12_datos.h + rnr_ui_cartel12.pak), con una vista para comparar.
 *
 *     LOS DATOS   viajan PEGADOS al FF28, detrás del byte del grado = lo último que lee el juego (`0x5E8F29`, en el
 *                 handler `0x5E8C40`). Desviamos esa llamada: se lee el grado como siempre y a continuación la cola
 *                 «C2» con el MISMO lector (0x67D200). El contrato está en servidor/cartel12.py.
 *     EL DIBUJO   el «dibujar» de los carteles de fábrica es la ranura +0xC de su tabla (normal 0x87ED60 → 0x5382D0,
 *                 cooperativo 0x87F0E8, ítem 0x8814C8); el juego la llama en cada cuadro con la carrera terminada
 *                 (0x4FC2D0). La nuestra llama a la de fábrica y después pone el LIENZO encima (800×600 centrado: la
 *                 interfaz no se agranda, medido con las capturas a 800×600 y 1024×768).
 *                 ★ 2.ª vuelta (anonimo03, 11-oct: «se dibuja encima del viejo; lo ideal es reemplazarlo por completo o
 *                 dejarlo invisible, y que el nuestro sea el único visible, con transparencias»): con datos de 12, la
 *                 de fábrica NO SE LLAMA. Leída entera (0x5382D0): sólo dibuja (18 llamadas a 0x64EE40, sus caritas)
 *                 y sube su fundido [+0x285] de a 15 por cuadro; la vuelta a la sala no pasa por ahí. El fundido
 *                 ahora es nuestro, al mismo ritmo, y el fondo de la hoja es translúcido (la herramienta).
 *                 `[cartel12] tapar=0` vuelve a dibujar los dos (el nuestro encima).
 *     EL LIENZO   una textura del pak que reescribimos en memoria (el fondo de la hoja + las piezas + los textos con
 *                 GDI) SÓLO cuando llegan datos nuevos — como el TOP 5.
 *   Sólo en la sala de 12 (`g_gr_puesto > 6`) y sólo con datos de ESTA carrera (`g_gr_carreras`, que sube en el FF25).
 *     EL TAMAÑO   ★ 5.ª vuelta (anonimo03, 11-oct, con capturas a 1024×768 y 1920×1080: «calculá y dale más % de cubrir
 *                 pantalla, y entre resoluciones intermedias»): el lienzo se arma a 800×600 y lo ESTIRA el motor. El
 *                 recorte de siempre (0x64EC40) llama a 0x64E9D0(x, y, ancho, alto EN PANTALLA, u0, v0, du, dv,
 *                 color, z), ret 0x28 (leído: du = w/ancho_textura…): la llamamos directo con el tamaño de pantalla.
 *                 escala = min(ancho/800, alto/600) × cubrir% (1024×768 → 983×737 · 1920×1080 → 1382×1037).
 *     LA NITIDEZ  ★ 6.ª vuelta (anonimo03, captura a 1920×1080: «se nota demasiado la baja resolución; a 800 se ve
 *                 muy detallado, a 1080 borroso»): el lienzo de 800×600 estirado ×1,7 por la placa. ⇒ la hoja va al
 *                 DOBLE (cartel12_crear.py, K12_ESC) y el cartel se ARMA a la escala de la pantalla en un lienzo de
 *                 2048×1536: las piezas re-muestreadas desde la hoja doble (bilineal premultiplicado; 4 muestras si
 *                 achica), los textos con GDI al tamaño final. El corte lo pone 1:1 en pantalla.
 *   ⛔ [cartel12] activo=0 lo apaga entero. Perillas: [cartel12] z (milésimas, 100 = 0.1) · cubrir (%, 96).
 *   ⚠ Se incluye DESPUÉS de grande.c (usa g_gr_puesto y g_gr_carreras).
 */
#include "cartel12_datos.h"

#define K12V(x) (g_k12_base + ((DWORD)(x) - 0x400000))
#define K12_SITIO_GRADO 0x5E8F29          /* call 0x67D200 = el byte del grado, lo último que lee el FF28 */

typedef void  (TCK *F_K12_LEER)(void *flujo, void *dest, int n);          /* 0x67D200, ret 8 */
typedef void  (TCK *F_K12_TABLERO)(void *t);                              /* la ranura +0xC: dibuja el cartel */
typedef void *(TCK *F_K12_CREAR)(void *self);
typedef int   (TCK *F_K12_CARGAR)(void *self, const char *ruta, const char *prefijo);
typedef void  (TCK *F_K12_RECORTE)(void *self, float x, float y, int u, int v, int w, int h, float z);
typedef void  (TCK *F_K12_RECORTE_F)(void *self, float x, float y, float w, float h, float u0, float v0, float du,
                                     float dv, int color, float z);                       /* 0x64E9D0, ret 0x28 */
typedef void  (TCK *F_K12_POS)(void *self, int n, int x, int y);
typedef void  (TCK *F_K12_COLOR)(void *self, int n, DWORD argb);
typedef void  (TCK *F_K12_DIBUJAR)(void *self, int n, int banderas);
typedef BYTE *(TCK *F_K12_TEX_ENTRADA)(void *mgr, DWORD h);
typedef void *(TCK *F_K12_TEX_D3D)(void *mgr, DWORD h, int cual);
typedef struct { UINT Format, Type, Usage, Pool, MSType, MSQuality, Width, Height; } K12_DESC;
typedef struct { INT Pitch; void *pBits; } K12_BLOQUEO;
typedef long (__stdcall *K12_T_DESC)(void *tex, UINT nivel, K12_DESC *d);
typedef long (__stdcall *K12_T_BLOQUEAR)(void *tex, UINT nivel, K12_BLOQUEO *r, const RECT *rc, DWORD b);
typedef long (__stdcall *K12_T_SOLTAR)(void *tex, UINT nivel);

static BYTE *g_k12_base = NULL;
static int   g_k12_activo = 0;
static float g_k12_z = 0.1f;
static int   g_k12_tapar = 1;                  /* 1 = el de fábrica no se dibuja (el nuestro lo reemplaza) */
static int   g_k12_cubrir = 96;                /* % de la pantalla que cubre (por el lado que menos entra) */
static int   g_k12_tex_w = 0, g_k12_tex_h = 0; /* la textura del lienzo (puede venir agrandada) */
static int   g_k12_cortes = 0, g_k12_corte = 0, g_k12_corte_w = 0, g_k12_corte_h = 0, g_k12_corte_cw = 0;
static int   g_k12_alfa = 0;                   /* nuestro fundido: +15 por cuadro, como el de fábrica */

/* los tres carteles de fábrica: la tabla, lo que tiene que haber en +0xC, y la nuestra */
static const DWORD K12_VTABLA[3] = { 0x87ED60, 0x87F0E8, 0x8814C8 };   /* normal · cooperativo · ítem */
static const DWORD K12_RENDER[3] = { 0x5382D0, 0x53EEF0, 0x575B40 };
static F_K12_TABLERO g_k12_real[3];

/* ── lo que mandó el server (la última cola «C2») ── */
typedef struct { BYTE slot, puesto, equipo; char apodo[25]; DWORD frame, exp; WORD rank; DWORD pd; BYTE star;
                 WORD combo; DWORD rcoin; } K12_FILA;
static int      g_k12_modo = 0, g_k12_gana = 0, g_k12_m1 = 0, g_k12_m2 = 0, g_k12_nivel = 0, g_k12_pista = 0;
static int      g_k12_cuatro = 0, g_k12_m4[4];       /* ★ 14-oct: el relevo de 12 (la cola E4: el marcador de 4) */
#define K12_VERDE 0xFF52CC5C
#define K12_NARANJA 0xFFFF9A33
static DWORD k12_color(int e) { return e == 2 ? K12_AZUL : e == 3 ? K12_VERDE : e == 4 ? K12_NARANJA : K12_ROJO; }
static const char *k12_nombre(int e) { return e == 1 ? "ROJO" : e == 2 ? "AZUL" : e == 3 ? "VERDE" : e == 4 ? "NARANJA" : "-"; }
static WORD     g_k12_cancion = 0;
static char     g_k12_titulo[64];
static int      g_k12_n = 0;
static K12_FILA g_k12_f[12];
static DWORD    g_k12_serie = 0;               /* sube con cada cola leída */
static DWORD    g_k12_de_carrera = 0xFFFFFFFF; /* el g_gr_carreras de esa cola */
static BYTE     g_k12_crudo[2048];

/* ── las imágenes ── */
static BYTE   g_k12_hoja[0x100], g_k12_lz[0x100];  /* los c2DImage (la clase ocupa 0x40) */
static int    g_k12_img = 0;                       /* 0 sin cargar · 1 lista · -1 no se usa */
static DWORD *g_k12_atlas = NULL;
static int    g_k12_aw = 0, g_k12_ah = 0;
static DWORD *g_k12_px = NULL;                     /* el cartel armado (g_k12_cw × g_k12_ch, ya a escala) */
static int    g_k12_cw = 0, g_k12_ch = 0;
static double g_k12_s = 1.0;                       /* px de pantalla por px lógico, de lo armado */
static DWORD  g_k12_serie_vista = 0;               /* la serie que ya entró con su fundido */
static DWORD  g_k12_firma = 0;
static void  *g_k12_lz_tex = NULL;

/* ── GDI ── */
#define K12_GDI_W 1600
#define K12_GDI_H 192
static HDC    g_k12_dc = NULL;
static DWORD *g_k12_gdi = NULL;
static HFONT  g_k12_l10 = NULL, g_k12_l12 = NULL, g_k12_l16 = NULL, g_k12_l34 = NULL;
static HFONT  g_k12_l11b = NULL, g_k12_l10b = NULL;   /* la negrita más chica: para que un nombre largo entre */
static double g_k12_letras_s = 0;

static int k12_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(K12V(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(K12V(va), b, n);
    VirtualProtect(K12V(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), K12V(va), n);
    return 1;
}

/* ═══ 1 · LA COLA «C2» (contrato: servidor/cartel12.py) ═════════════════════════════════════════════════════════
 *   b"C2" · u16 largo · [largo]: u8 versión · u8 modo · u8 gana · u8 m1 · u8 m2 · u16 canción · u8 nivel · u16 pista
 *   · u8 L · título · u8 n · n × (u8 asiento · u8 puesto · u8 equipo · u8 L · apodo · u32 llegada · u32 exp
 *   · u16 ranking · u32 precisión×1000 · u8 estrella · u16 combo · u32 rcoin) */
static int k12_fila(const BYTE *b, int largo, int *p, K12_FILA *f)
{
    if (*p + 4 > largo) return 0;
    f->slot = b[*p]; f->puesto = b[*p + 1]; f->equipo = b[*p + 2];
    int L = b[*p + 3];
    *p += 4;
    if (*p + L + 21 > largo) return 0;
    int c = L < 24 ? L : 24;
    CopyMemory(f->apodo, b + *p, c);
    f->apodo[c] = 0;
    *p += L;
    f->frame = *(const DWORD *)(b + *p);
    f->exp = *(const DWORD *)(b + *p + 4);
    f->rank = *(const WORD *)(b + *p + 8);
    f->pd = *(const DWORD *)(b + *p + 10);
    f->star = b[*p + 14];
    f->combo = *(const WORD *)(b + *p + 15);
    f->rcoin = *(const DWORD *)(b + *p + 17);
    *p += 21;
    return f->slot < 12;
}

static void k12_cola(void *flujo)
{
    F_K12_LEER leer = (F_K12_LEER)K12V(0x67D200);
    BYTE cab[4];
    ZeroMemory(cab, sizeof(cab));
    leer(flujo, cab, 4);                       /* ⚠ si no alcanzan los bytes, el lector NO toca el destino: queda 0 */
    if (cab[0] != 'C' || cab[1] != '2') return;  /* un cartel sin la cola (sala de 6, server viejo): nada */
    int largo = *(WORD *)(cab + 2);
    if (largo < 12 || largo > (int)sizeof(g_k12_crudo)) { apuntar("  [cartel12] ⚠ cola de %d B: no la leo", largo); return; }
    ZeroMemory(g_k12_crudo, sizeof(g_k12_crudo));
    leer(flujo, g_k12_crudo, largo);
    const BYTE *b = g_k12_crudo;
    if (b[0] != 1) { apuntar("  [cartel12] ⚠ versión %d de la cola: no la conozco", b[0]); return; }
    int p = 10, L = b[p];
    if (p + 1 + L + 1 > largo) return;
    int c = L < 63 ? L : 63;
    CopyMemory(g_k12_titulo, b + p + 1, c);
    g_k12_titulo[c] = 0;
    p += 1 + L;
    int n = b[p++];
    if (n > 12) n = 12;
    K12_FILA f[12];
    for (int i = 0; i < n; i++)
        if (!k12_fila(b, largo, &p, &f[i])) { apuntar("  [cartel12] ⚠ la fila %d no cierra: descarto la cola", i); return; }
    g_k12_cuatro = 0;                                    /* ★ 14-oct: detrás de las filas, opcional, E4 + 4 victorias */
    if (p + 6 <= largo && b[p] == 'E' && b[p + 1] == '4') {
        for (int e = 0; e < 4; e++) g_k12_m4[e] = b[p + 2 + e];
        g_k12_cuatro = 1;
    }
    g_k12_modo = b[1]; g_k12_gana = b[2]; g_k12_m1 = b[3]; g_k12_m2 = b[4];
    g_k12_cancion = *(const WORD *)(b + 5); g_k12_nivel = b[7]; g_k12_pista = *(const WORD *)(b + 8);
    CopyMemory(g_k12_f, f, sizeof(f));
    g_k12_n = n;
    g_k12_de_carrera = g_gr_carreras;
    g_k12_serie++;
    apuntar("  [cartel12] ★ cola C2: %d filas · %s · gana %d · score %d-%d · canción %u «%s» nivel %d · pista %d",
            n, g_k12_modo ? "equipo" : "personal", g_k12_gana, g_k12_m1, g_k12_m2, g_k12_cancion, g_k12_titulo,
            g_k12_nivel, g_k12_pista);
}

/* el desvío de 0x5E8F29: el grado como siempre, y nuestra cola detrás */
static void __fastcall k12_grado(void *flujo, void *nada, void *dest, int n)
{
    (void)nada;
    ((F_K12_LEER)K12V(0x67D200))(flujo, dest, n);
    if (g_k12_activo) k12_cola(flujo);
}

/* ═══ 2 · LAS IMÁGENES ══════════════════════════════════════════════════════════════════════════════════════════ */
static void *k12_textura(BYTE *img)
{
    void *mgr = *(void **)K12V(0x931570);
    DWORD h = *(DWORD *)(img + 4);
    if (!mgr || !h) return NULL;
    BYTE *ent = ((F_K12_TEX_ENTRADA)K12V(0x4099E0))(mgr, h);
    if (!ent || *(DWORD *)(ent + 0x48)) return NULL;
    return ((F_K12_TEX_D3D)K12V(0x441420))(mgr, h, 0);
}

static int k12_desc(void *tex, K12_DESC *d)
{
    void **vt = tex ? *(void ***)tex : NULL;
    return vt && ((K12_T_DESC)vt[17])(tex, 0, d) == 0;
}

static HFONT k12_letra(int px, int peso, const WCHAR *familia)
{
    /* ⚠ ANTIALIASED_QUALITY y no ClearType: el borde suave tiene que ser GRIS (lo usamos de alfa) */
    return CreateFontW(-px, 0, 0, 0, peso, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                       ANTIALIASED_QUALITY, DEFAULT_PITCH, familia);
}

static int k12_gdi(void)
{
    g_k12_dc = CreateCompatibleDC(NULL);
    if (!g_k12_dc) return 0;
    BITMAPINFO bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = K12_GDI_W;
    bi.bmiHeader.biHeight = -K12_GDI_H;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(g_k12_dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (!bmp || !bits) return 0;
    SelectObject(g_k12_dc, bmp);
    g_k12_gdi = (DWORD *)bits;
    SetBkMode(g_k12_dc, TRANSPARENT);
    SetTextColor(g_k12_dc, RGB(255, 255, 255));
    return 1;
}

/* las letras de la maqueta (segoeuib 12 · seguibl 16/34 · segoeui 10) AL TAMAÑO FINAL: nítidas a cualquier escala */
static int k12_letras(double s)
{
    if (g_k12_letras_s == s && g_k12_l12) return 1;
    HFONT *l[6] = { &g_k12_l10, &g_k12_l12, &g_k12_l16, &g_k12_l34, &g_k12_l11b, &g_k12_l10b };
    for (int i = 0; i < 6; i++)
        if (*l[i]) { DeleteObject(*l[i]); *l[i] = NULL; }
    g_k12_l10 = k12_letra((int)(10 * s + 0.5), FW_NORMAL, L"Segoe UI");
    g_k12_l12 = k12_letra((int)(12 * s + 0.5), FW_BOLD, L"Segoe UI");
    g_k12_l16 = k12_letra((int)(16 * s + 0.5), FW_BLACK, L"Segoe UI Black");
    g_k12_l34 = k12_letra((int)(34 * s + 0.5), FW_BLACK, L"Segoe UI Black");
    g_k12_l11b = k12_letra((int)(11 * s + 0.5), FW_BOLD, L"Segoe UI");
    g_k12_l10b = k12_letra((int)(10 * s + 0.5), FW_BOLD, L"Segoe UI");
    g_k12_letras_s = s;
    return g_k12_l10 && g_k12_l12 && g_k12_l16 && g_k12_l34 && g_k12_l11b && g_k12_l10b;
}

static void k12_cargar(void)
{
    g_k12_img = -1;
    F_K12_RECORTE rec = (F_K12_RECORTE)K12V(0x64EC40);
    ((F_K12_CREAR)K12V(0x64E560))(g_k12_hoja);
    if (!((F_K12_CARGAR)K12V(0x64E1E0))(g_k12_hoja, K12_HOJA_TGA, NULL)) {
        apuntar("  [cartel12] ⛔ no encontré %s (¿falta rnr_ui_cartel12.pak?): queda el cartel de fábrica", K12_HOJA_TGA);
        return;
    }
    rec(g_k12_hoja, 0, 0, 0, 0, 4, 4, g_k12_z);                /* (un corte, para que el juego la suba) */
    void *tex = k12_textura(g_k12_hoja);
    K12_DESC d;
    if (!tex || !k12_desc(tex, &d) || d.Format != 21 /* A8R8G8B8 */) {
        apuntar("  [cartel12] ⛔ no pude leer la hoja (tex=%p fmt=%u)", tex, tex ? d.Format : 0);
        return;
    }
    void **vt = *(void ***)tex;
    K12_BLOQUEO bq;
    if (((K12_T_BLOQUEAR)vt[19])(tex, 0, &bq, NULL, 0x10 /* READONLY */) != 0) {
        apuntar("  [cartel12] ⛔ la hoja no se deja leer (pool %u)", d.Pool);
        return;
    }
    g_k12_atlas = (DWORD *)HeapAlloc(GetProcessHeap(), 0, d.Width * d.Height * 4);
    if (g_k12_atlas)
        for (UINT y = 0; y < d.Height; y++)
            CopyMemory(g_k12_atlas + y * d.Width, (BYTE *)bq.pBits + y * bq.Pitch, d.Width * 4);
    ((K12_T_SOLTAR)vt[20])(tex, 0);
    if (!g_k12_atlas) return;
    g_k12_aw = (int)d.Width;
    g_k12_ah = (int)d.Height;
    if (g_k12_aw < K12_W * K12_ESC || g_k12_ah < K12_H * K12_ESC) {
        apuntar("  [cartel12] ⛔ la hoja mide %dx%d (¿pak viejo, de antes de la hoja al doble?)", g_k12_aw, g_k12_ah);
        return;
    }
    ((F_K12_CREAR)K12V(0x64E560))(g_k12_lz);
    if (!((F_K12_CARGAR)K12V(0x64E1E0))(g_k12_lz, K12_LIENZO_TGA, NULL)) {
        apuntar("  [cartel12] ⛔ no encontré %s", K12_LIENZO_TGA);
        return;
    }
    rec(g_k12_lz, 0, 0, 0, 0, K12_W, K12_H, g_k12_z);              /* el corte 0 (para que el juego la suba) */
    g_k12_cortes = 1;
    g_k12_corte = 0;
    g_k12_corte_w = g_k12_corte_h = g_k12_corte_cw = 0;
    tex = k12_textura(g_k12_lz);
    if (!tex || !k12_desc(tex, &d) || d.Format != 21 || d.Width < K12_W || d.Height < K12_H) {
        apuntar("  [cartel12] ⛔ el lienzo no es el esperado (fmt %u, %ux%u)", tex ? d.Format : 0, tex ? d.Width : 0,
                tex ? d.Height : 0);
        return;
    }
    g_k12_tex_w = (int)d.Width;
    g_k12_tex_h = (int)d.Height;
    g_k12_px = (DWORD *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)g_k12_tex_w * g_k12_tex_h * 4);
    if (!g_k12_px) { apuntar("  [cartel12] ⛔ sin memoria para el lienzo"); return; }
    if (!k12_gdi()) { apuntar("  [cartel12] ⛔ GDI: no pude preparar el recorte de las letras"); return; }
    g_k12_img = 1;
    apuntar("  [cartel12] ★ listo: hoja %dx%d (al doble), lienzo %dx%d (pool %u), z %d/1000", g_k12_aw, g_k12_ah,
            g_k12_tex_w, g_k12_tex_h, d.Pool, (int)(g_k12_z * 1000));
}

/* ═══ 3 · ARMAR EL CARTEL EN MEMORIA, A LA ESCALA DE LA PANTALLA (lo mismo que `armar()` de la herramienta) ══════
 *   Todo lo de cartel12_datos.h está en px LÓGICOS (el cartel de 800×600); g_k12_s = px de pantalla por px lógico.
 *   Las piezas salen de la hoja, que está al DOBLE (K12_ESC): se re-muestrean (bilineal, alfa premultiplicado; con
 *   4 muestras por píxel si achican mucho). Los textos van con GDI al tamaño final. */
static void k12_mezclar(DWORD *p, DWORD col, int a)        /* col sobre *p con alfa a (0..255) */
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

/* una muestra bilineal de la pieza (u, v en px de la pieza, continuos), sumada PREMULTIPLICADA a acc[r,g,b,a] */
static void k12_muestra(const int *pz, double u, double v, unsigned *acc)
{
    double fx = u - 0.5, fy = v - 0.5;
    if (fx < 0) fx = 0;
    if (fy < 0) fy = 0;
    if (fx > pz[2] - 1) fx = pz[2] - 1;
    if (fy > pz[3] - 1) fy = pz[3] - 1;
    int x0 = (int)fx, y0 = (int)fy;
    int x1 = x0 + 1 < pz[2] ? x0 + 1 : x0, y1 = y0 + 1 < pz[3] ? y0 + 1 : y0;
    unsigned wx = (unsigned)((fx - x0) * 16 + 0.5), wy = (unsigned)((fy - y0) * 16 + 0.5);
    const int xs[2] = { pz[0] + x0, pz[0] + x1 }, ys[2] = { pz[1] + y0, pz[1] + y1 };
    const unsigned pw[2][2] = { { (16 - wx) * (16 - wy), wx * (16 - wy) }, { (16 - wx) * wy, wx * wy } };
    for (int j = 0; j < 2; j++)
        for (int i = 0; i < 2; i++) {
            if (!pw[j][i] || xs[i] >= g_k12_aw || ys[j] >= g_k12_ah) continue;
            DWORD t = g_k12_atlas[ys[j] * g_k12_aw + xs[i]];
            unsigned a = t >> 24, wa = pw[j][i] * a;
            if (!wa) continue;
            acc[0] += wa * ((t >> 16) & 255);
            acc[1] += wa * ((t >> 8) & 255);
            acc[2] += wa * (t & 255);
            acc[3] += wa;
        }
}

/* una pieza de la hoja {x, y, w, h} (px de la hoja) en (lx, ly) LÓGICOS */
static void k12_pegar(const int *pz, double lx, double ly)
{
    double s = g_k12_s;
    int x0 = (int)(lx * s + 0.5), y0 = (int)(ly * s + 0.5);
    int dw = (int)(pz[2] * s / K12_ESC + 0.5), dh = (int)(pz[3] * s / K12_ESC + 0.5);
    if (dw <= 0 || dh <= 0) return;
    double rx = (double)pz[2] / dw, ry = (double)pz[3] / dh;
    int fino = rx > 1.25 || ry > 1.25;                     /* achica mucho: 4 muestras por píxel */
    for (int j = 0; j < dh; j++) {
        int yy = y0 + j;
        if (yy < 0 || yy >= g_k12_ch) continue;
        DWORD *fila = g_k12_px + yy * g_k12_cw;
        for (int i = 0; i < dw; i++) {
            int xx = x0 + i;
            if (xx < 0 || xx >= g_k12_cw) continue;
            unsigned acc[4] = { 0, 0, 0, 0 };
            int n = 1;
            if (fino) {
                n = 4;
                for (int q = 0; q < 4; q++)
                    k12_muestra(pz, (i + 0.25 + 0.5 * (q & 1)) * rx, (j + 0.25 + 0.5 * (q >> 1)) * ry, acc);
            } else
                k12_muestra(pz, (i + 0.5) * rx, (j + 0.5) * ry, acc);
            if (!acc[3]) continue;
            DWORD col = 0xFF000000 | ((acc[0] / acc[3]) << 16) | ((acc[1] / acc[3]) << 8) | (acc[2] / acc[3]);
            k12_mezclar(&fila[xx], col, (int)(acc[3] / (256u * n)));
        }
    }
}
#define K12_PEGAR(P, x, y) do { static const int _p[4] = { P }; k12_pegar(_p, (x), (y)); } while (0)

/* un texto cp1252 con borde de `grosor` px LÓGICOS (0 = sin borde). alin: 0 empieza en x · 1 centrado · 2 termina en x.
 *   x, cy y ancho_max, lógicos. La letra ya viene al tamaño final (k12_letras). */
static void k12_texto(double lx, double lcy, int alin, HFONT letra, const char *s, int ancho_max, DWORD color,
                      DWORD borde, int grosor)
{
    double esc = g_k12_s;
    WCHAR w[160];
    int n = id_a_ancho(s, w, 158);
    if (n <= 1) return;
    n--;
    SelectObject(g_k12_dc, letra);
    SIZE t;
    GetTextExtentPoint32W(g_k12_dc, w, n, &t);
    int tope = (int)(ancho_max * esc + 0.5);
    if (ancho_max > 0 && t.cx > tope)
        while (n > 1 && t.cx > tope) {
            n--;
            w[n - 1] = 0x2026;
            GetTextExtentPoint32W(g_k12_dc, w, n, &t);
        }
    int g = grosor > 0 ? (int)(grosor * esc + 0.5) : 0;
    if (grosor > 0 && g < 1) g = 1;
    const int M = g + 2;                                     /* margen en el recorte, para el borde */
    ZeroMemory(g_k12_gdi, K12_GDI_W * K12_GDI_H * 4);
    TextOutW(g_k12_dc, M, M, w, n);
    GdiFlush();
    int x = (int)(lx * esc + 0.5), cy = (int)(lcy * esc + 0.5);
    int x0 = alin == 0 ? x : alin == 1 ? x - t.cx / 2 : x - t.cx;
    int y0 = cy - t.cy / 2;
    int ancho = t.cx + 2 * M > K12_GDI_W ? K12_GDI_W : t.cx + 2 * M;
    int alto = t.cy + 2 * M > K12_GDI_H ? K12_GDI_H : t.cy + 2 * M;
    int ba = (int)(borde >> 24), ca = (int)(color >> 24);
    for (int pasada = (g > 0 && ba ? 0 : 1); pasada < 2; pasada++)
        for (int j = 0; j < alto; j++) {
            int yy = y0 - M + j;
            if (yy < 0 || yy >= g_k12_ch) continue;
            for (int i = 0; i < ancho; i++) {
                int xx = x0 - M + i;
                if (xx < 0 || xx >= g_k12_cw) continue;
                int cob;
                if (pasada == 0) {                           /* el borde: lo más fuerte del vecindario (redondo) */
                    cob = 0;
                    for (int v = -g; v <= g; v++)
                        for (int u = -g; u <= g; u++) {
                            if (u * u + v * v > g * g + g) continue;
                            int a = i + u, b = j + v;
                            if (a < 0 || b < 0 || a >= K12_GDI_W || b >= K12_GDI_H) continue;
                            int gg = (int)((g_k12_gdi[b * K12_GDI_W + a] >> 8) & 255);
                            if (gg > cob) cob = gg;
                        }
                    k12_mezclar(&g_k12_px[yy * g_k12_cw + xx], borde, cob * ba / 255);
                } else {
                    cob = (int)((g_k12_gdi[j * K12_GDI_W + i] >> 8) & 255);
                    k12_mezclar(&g_k12_px[yy * g_k12_cw + xx], color, cob * ca / 255);
                }
            }
        }
}

#define K12_NEGRO  0xFF000000
#define K12_BLANCO 0xFFFFFFFF

/* un número con las cifras del coreano, alineado a la DERECHA en x; y = arriba de la caja (lógicos) */
static void k12_numero(DWORD valor, int juego, double x_der, double y)
{
    char s[12];
    wsprintfA(s, "%lu", valor);
    int n = lstrlenA(s);
    double ancho = 0, alto = 0;
    for (int i = 0; i < n; i++) {
        const int *c = K12_CIFRA[juego][s[i] - '0'];
        ancho += (double)c[2] / K12_ESC - (i ? 1 : 0);
        if ((double)c[3] / K12_ESC > alto) alto = (double)c[3] / K12_ESC;
    }
    double x = x_der - ancho;
    for (int i = 0; i < n; i++) {
        const int *c = K12_CIFRA[juego][s[i] - '0'];
        k12_pegar(c, x, y + alto - (double)c[3] / K12_ESC);
        x += (double)c[2] / K12_ESC - 1;
    }
}

/* ★ un nombre largo (la pista, la canción): primero se ACHICA la letra (12 → 11 → 10) y sólo si igual no entra se
 *   corta con «…» (anonimo03, 11-oct: salía «MARAVILLA ESPACI…») */
static void k12_texto_cabe(double lx, double lcy, const char *s, int ancho_max, DWORD color)
{
    HFONT l[3] = { g_k12_l12, g_k12_l11b, g_k12_l10b };
    WCHAR w[160];
    int n = id_a_ancho(s, w, 158);
    if (n <= 1) return;
    int tope = (int)(ancho_max * g_k12_s + 0.5), i = 0;
    for (; i < 2; i++) {
        SIZE t;
        SelectObject(g_k12_dc, l[i]);
        GetTextExtentPoint32W(g_k12_dc, w, n - 1, &t);
        if (t.cx <= tope) break;
    }
    k12_texto(lx, lcy, 0, l[i], s, ancho_max, color, K12_NEGRO, 1);
}

/* ★ el nivel del emblema y las estrellas, con la MISMA lógica que el de fábrica (0x557838): el CANAL, no la canción.
 *   cGame+0x881: 3 novato · 0 estrella · 1 luna · 13 (libre) → la banda de la sala [cRoom+0x9512] · lo demás sol.
 *   Devuelve el índice de K12_EMBLEMA (0 novato · 1 estrella · 2 luna · 3 violeta · 4 sol). */
static int k12_nivel_canal(void)
{
    BYTE *g = *(BYTE **)K12V(0x9314C8);
    BYTE *sala = *(BYTE **)K12V(0x9314C0);
    int c = g ? g[0x881] : 2;
    if (c == 3) return 0;
    if (c == 0) return 1;
    if (c == 1) return 2;
    if (c == 0xD && sala) {
        int b = sala[0x9512];
        if (b == 1) return 0;
        if (b == 2 || b == 3) return 1;
        if (b == 4 || b == 5) return 2;
    }
    return 4;
}

static int k12_yo(void)
{
    BYTE *g = *(BYTE **)K12V(0x9314C8);
    BYTE *padron = *(BYTE **)K12V(0x931660);
    if (g && g[0xC01]) return g[0x5D];                 /* en relevo o mirando: cGame+0x5D (como la tarjeta 0x55AA01) */
    return padron ? padron[0x40] : -1;
}

static void k12_armar(int yo)
{
    ZeroMemory(g_k12_px, (SIZE_T)g_k12_cw * g_k12_ch * 4);
    K12_PEGAR(K12_P_FONDO, 0, 0);
    if (g_k12_cuatro) K12_PEGAR(K12_P_PODIO_VACIO, 9, 279);              /* ★ 14-oct: el podio, aparte del fondo */
    else K12_PEGAR(K12_P_PODIO, 9, 279);
    const char *pista = (g_k12_pista >= 0 && g_k12_pista < K12_PISTAS) ? K12_PISTA[g_k12_pista] : "";
    int nv = k12_nivel_canal();
    k12_pegar(K12_EMBLEMA[nv], K12_EMBLEMA_X, K12_EMBLEMA_Y);
    k12_texto_cabe(K12_PISTA_X, K12_PISTA_CY, pista, 128, K12_AMARILLO);
    k12_texto_cabe(K12_CANCION_X, K12_CANCION_CY, g_k12_titulo, 128, K12_AMARILLO);
    for (int k = 0; k < K12_ESTRELLAS_N; k++) {            /* en MEDIAS estrellas, como el de fábrica (5 = 2 y media) */
        double x = K12_ESTRELLAS_X + k * K12_ESTRELLAS_DX;
        if (g_k12_nivel >= 2 * (k + 1)) k12_pegar(K12_ESTRELLA_LLENA[nv], x, K12_ESTRELLAS_Y);
        else if (g_k12_nivel == 2 * k + 1) k12_pegar(K12_ESTRELLA_MEDIA[nv], x, K12_ESTRELLAS_Y);
        else K12_PEGAR(K12_P_ESTRELLA_VACIA, x, K12_ESTRELLAS_Y);
    }
    /* el orden del cartel: por puesto, los que no llegaron (0) al final */
    int ord[12], n = g_k12_n;
    for (int i = 0; i < n; i++) ord[i] = i;
    for (int i = 1; i < n; i++)
        for (int j = i; j > 0; j--) {
            int a = g_k12_f[ord[j - 1]].puesto ? g_k12_f[ord[j - 1]].puesto : 99;
            int b = g_k12_f[ord[j]].puesto ? g_k12_f[ord[j]].puesto : 99;
            if (a <= b) break;
            int t = ord[j]; ord[j] = ord[j - 1]; ord[j - 1] = t;
        }
    if (g_k12_cuatro) {                                  /* ★ 14-oct · relevo de 12: el MEJOR de cada equipo, 1..4 */
        int k = 0;
        for (int i = 0; i < n && k < 4; i++) {
            const K12_FILA *f = &g_k12_f[ord[i]];
            if (!f->puesto || (f->puesto - 1) % 3 != 0) continue;           /* el 1.º de su equipo (puestos 1, 4, 7, 10) */
            double y = 287 + k * 64;
            k12_pegar(K12_PUESTO[k], 18, y);
            k12_texto(K12_PODIO_X, y + 46, 0, g_k12_l16, f->apodo, 118, k12_color(f->equipo), K12_NEGRO, 2);
            k++;
        }
    }
    for (int i = 0; i < 3 && i < n && !g_k12_cuatro; i++) {   /* el podio */
        const K12_FILA *f = &g_k12_f[ord[i]];
        DWORD col = !g_k12_modo ? K12_AMARILLO : k12_color(f->equipo);
        k12_texto(K12_PODIO_X, K12_PODIO_CY[i], 0, g_k12_l16, f->apodo, 118, col, K12_NEGRO, 2);
    }
    if (g_k12_modo && g_k12_cuatro) {                     /* ★ 14-oct · relevo de 12: el ganador y el SCORE de los 4 */
        for (int e = 0; e < 4; e++) {
            char s[24];
            wsprintfA(s, "%s %d", k12_nombre(e + 1), g_k12_m4[e]);
            k12_texto(K12_MARC_X[0] - 12 + e * 92, K12_MARC_CY, 1, g_k12_l16, s, 0, k12_color(e + 1), K12_NEGRO, 2);
        }
        k12_texto(K12_LEYENDA_X, K12_LEYENDA_CY, 1, g_k12_l10, "SCORE \xB7 victorias de la serie", 0, 0xFFDCE6DC,
                  K12_NEGRO, 1);
        k12_texto(K12_GANADOR_X, K12_GANADOR_CY, 1, g_k12_l16, k12_nombre(g_k12_gana), 0, k12_color(g_k12_gana),
                  K12_NEGRO, 2);
    } else if (g_k12_modo) {                              /* el ganador y el SCORE de la serie */
        /* lo fijo del marcador (la barra es translúcida: va acá y no en la hoja, el personal no lo lleva) */
        k12_texto(K12_MARC_X[0], K12_MARC_CY, 1, g_k12_l16, "ROJO", 0, K12_ROJO, K12_NEGRO, 2);
        k12_texto(K12_MARC_X[1], K12_MARC_CY, 1, g_k12_l16, "VS", 0, K12_BLANCO, K12_NEGRO, 2);
        k12_texto(K12_MARC_X[2], K12_MARC_CY, 1, g_k12_l16, "AZUL", 0, K12_AZUL, K12_NEGRO, 2);
        k12_texto(K12_LEYENDA_X, K12_LEYENDA_CY, 1, g_k12_l10, "SCORE \xB7 victorias de la serie", 0, 0xFFDCE6DC,
                  K12_NEGRO, 1);
        k12_texto(K12_GANADOR_X, K12_GANADOR_CY, 1, g_k12_l16, g_k12_gana == 1 ? "ROJO" : g_k12_gana == 2 ? "AZUL" : "-",
                  0, g_k12_gana == 1 ? K12_ROJO : K12_AZUL, K12_NEGRO, 2);
        char s[8];
        wsprintfA(s, "%d", g_k12_m1);
        k12_texto(K12_SCORE_XY[0][0], K12_SCORE_XY[0][1], 1, g_k12_l34, s, 0, K12_ROJO, K12_NEGRO, 2);
        wsprintfA(s, "%d", g_k12_m2);
        k12_texto(K12_SCORE_XY[1][0], K12_SCORE_XY[1][1], 1, g_k12_l34, s, 0, K12_AZUL, K12_NEGRO, 2);
    } else {                                              /* personal: sin equipos — el 1.º y MI puesto */
        if (n) k12_texto(K12_GANADOR_X, K12_GANADOR_CY, 1, g_k12_l16, g_k12_f[ord[0]].apodo, 100, K12_AMARILLO, K12_NEGRO, 2);
        for (int i = 0; i < n; i++)
            if (g_k12_f[ord[i]].slot == yo && g_k12_f[ord[i]].puesto) {
                char s[16];
                wsprintfA(s, "PUESTO %d", g_k12_f[ord[i]].puesto);
                k12_texto(540, 104, 1, g_k12_l34, s, 0, K12_AMARILLO, K12_NEGRO, 2);
            }
    }
    for (int k = 0; k < n; k++) {                         /* la lista */
        const K12_FILA *f = &g_k12_f[ord[k]];
        int y = K12_FILA_Y[k];
        if (!g_k12_modo) K12_PEGAR(K12_P_FILA_GRIS, K12_FILA_X0, y);
        else if (f->equipo == 2) K12_PEGAR(K12_P_FILA_AZUL, K12_FILA_X0, y);
        else if (f->equipo == 3) K12_PEGAR(K12_P_FILA_VERDE, K12_FILA_X0, y);         /* ★ 14-oct: relevo de 12 */
        else if (f->equipo == 4) K12_PEGAR(K12_P_FILA_NARANJA, K12_FILA_X0, y);
        else K12_PEGAR(K12_P_FILA_ROJA, K12_FILA_X0, y);
        if (f->slot == yo) K12_PEGAR(K12_P_YO, K12_FILA_X0 - 3, y - 3);
        if (f->puesto >= 1 && f->puesto <= 12) {
            /* ★ 14-oct · relevo de 12: el puesto DEL EQUIPO — los 3 del que ganó 1ST, los del 2.º 2ND… (anonimo03). El server
             *   manda 1-2-3, 4-5-6… (dentro del equipo, por su precisión: así queda el orden de las filas) */
            const int *pu = K12_PUESTO[g_k12_cuatro ? (f->puesto - 1) / 3 : f->puesto - 1];
            k12_pegar(pu, K12_FILA_X0 - (double)pu[2] / K12_ESC - 2, y + 4);
        }
        if (f->slot >= 6 && f->slot < 12 && f->equipo == 3) k12_pegar(K12_INSIG_V[f->slot - 6], K12_FILA_X0 + 4, y + 5);
        else if (f->slot >= 6 && f->slot < 12 && f->equipo == 4) k12_pegar(K12_INSIG_N[f->slot - 6], K12_FILA_X0 + 4, y + 5);
        else if (f->slot < 6 && f->equipo == 2 && g_k12_cuatro) k12_pegar(K12_INSIG_A[f->slot], K12_FILA_X0 + 4, y + 5);
        else k12_pegar(K12_INSIG[f->slot], K12_FILA_X0 + 4, y + 5);          /* ★ 15-oct: arriba, 4P..6P azules (4 equipos) */
        k12_texto(K12_FILA_X0 + 28, y + 15, 0, g_k12_l12, f->apodo, 92, K12_BLANCO, K12_NEGRO, 1);
        {   /* ★ 17-oct (anonimo03: «recuperar el tiempo de llegada individual», el del cartel de 6): mm:ss:cc */
            char ts[16];
            if (f->frame && f->frame != 0xFFFFFFFF) {
                DWORD cs = f->frame * 100 / 60;                                   /* cuadros (60/s) → centésimas */
                wsprintfA(ts, "%02lu:%02lu:%02lu", cs / 6000, cs / 100 % 60, cs % 100);
            } else lstrcpyA(ts, "--:--:--");                                      /* no llegó */
            k12_texto(K12_TIEMPO_CX, y + 15, 1, g_k12_l12, ts, 0, K12_BLANCO, K12_NEGRO, 1);
        }
        DWORD val[6] = { f->exp, f->rank, f->pd / 1000, f->star, f->combo, f->rcoin };
        for (int c = 0; c < 6; c++) {
            k12_numero(val[c], K12_COL_JUEGO[c], K12_COL_X[c], y + 7);
            if (c == 2 || c == 3) k12_texto(K12_COL_X[c] + 1, y + 15, 0, g_k12_l12, "%", 0, K12_BLANCO, K12_NEGRO, 1);
        }
    }
}

static int k12_subir(void *tex)
{
    void **vt = *(void ***)tex;
    K12_BLOQUEO b;
    if (((K12_T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, 0) != 0) return 0;
    for (int y = 0; y < g_k12_ch; y++)
        CopyMemory((BYTE *)b.pBits + y * b.Pitch, g_k12_px + y * g_k12_cw, g_k12_cw * 4);
    ((K12_T_SOLTAR)vt[20])(tex, 0);
    return 1;
}

/* ═══ 4 · CADA CUADRO DEL CARTEL DE FÁBRICA ═════════════════════════════════════════════════════════════════════ */
static void k12_dibujar(BYTE *t, int cual)
{
    if (g_k12_img == 0) k12_cargar();
    if (g_k12_img != 1) return;
    void *tex = k12_textura(g_k12_lz);
    if (!tex) return;
    BYTE *pant = *(BYTE **)K12V(0x931498);
    int W = pant ? *(int *)(pant + 4) : 1024, H = pant ? *(int *)(pant + 8) : 768;
    /* ★ el tamaño: el lado que menos entra, × cubrir%. Se ARMA a esa escala (tope: lo que entra en el lienzo; más
     *   allá, lo que falte lo estira la placa) */
    double s = (double)W / K12_W < (double)H / K12_H ? (double)W / K12_W : (double)H / K12_H;
    s = s * g_k12_cubrir / 100.0;
    if (s < 0.5) s = 0.5;
    double sa = s, tope = (double)g_k12_tex_w / K12_W < (double)g_k12_tex_h / K12_H ? (double)g_k12_tex_w / K12_W
                                                                                    : (double)g_k12_tex_h / K12_H;
    if (sa > tope) sa = tope;
    int cw = (int)(K12_W * sa), ch = (int)(K12_H * sa);
    int yo = k12_yo();
    DWORD firma = g_k12_serie * 2654435761u ^ (DWORD)(yo & 0xFF) ^ ((DWORD)cw << 12) ^ ((DWORD)k12_nivel_canal() << 8)
                  ^ 0x80000000u;
    if (firma != g_k12_firma || tex != g_k12_lz_tex) {        /* datos nuevos, otra pantalla, o textura rehecha */
        if (g_k12_serie != g_k12_serie_vista) { g_k12_alfa = 0; g_k12_serie_vista = g_k12_serie; }  /* su fundido */
        g_k12_s = sa;
        g_k12_cw = cw;
        g_k12_ch = ch;
        DWORD t0 = GetTickCount();
        if (!k12_letras(sa)) { apuntar("  [cartel12] ⛔ GDI: no pude crear las letras a escala %d/100", (int)(sa * 100)); return; }
        k12_armar(yo);
        if (k12_subir(tex)) { g_k12_firma = firma; g_k12_lz_tex = tex; }
        apuntar("  [cartel12] armado: %d filas, yo asiento %d · pantalla %dx%d → %dx%d (escala %d/100) en %lu ms",
                g_k12_n, yo, W, H, cw, ch, (int)(sa * 100), GetTickCount() - t0);
    }
    int dw = (int)(K12_W * s + 0.5), dh = (int)(K12_H * s + 0.5);
    if ((dw != g_k12_corte_w || dh != g_k12_corte_h || cw != g_k12_corte_cw) && g_k12_cortes < 32) {
        ((F_K12_RECORTE_F)K12V(0x64E9D0))(g_k12_lz, 0, 0, (float)dw, (float)dh, 0, 0, (float)cw / g_k12_tex_w,
                                          (float)ch / g_k12_tex_h, -1, g_k12_z);
        g_k12_corte = g_k12_cortes++;
        g_k12_corte_w = dw;
        g_k12_corte_h = dh;
        g_k12_corte_cw = cw;
    }
    if (g_k12_alfa < 255) g_k12_alfa = g_k12_alfa + 15 > 255 ? 255 : g_k12_alfa + 15;
    int alfa = (!g_k12_tapar && cual == 0) ? t[0x285] : g_k12_alfa;   /* el de fábrica sube igual (0x538347) */
    ((F_K12_POS)K12V(0x64D990))(g_k12_lz, g_k12_corte, (W - g_k12_corte_w) / 2, (H - g_k12_corte_h) / 2);
    ((F_K12_COLOR)K12V(0x64E710))(g_k12_lz, g_k12_corte, ((DWORD)alfa << 24) | 0xFFFFFF);
    ((F_K12_DIBUJAR)K12V(0x64EE40))(g_k12_lz, g_k12_corte, 0);
}

static void k12_tras(BYTE *t, int cual)
{
    int nuestro = g_k12_activo && g_gr_puesto > 6 && g_k12_n > 0 && g_k12_de_carrera == g_gr_carreras;
    if (nuestro && g_k12_tapar && g_k12_img != -1) {          /* ★ el nuestro REEMPLAZA al de fábrica */
        k12_dibujar(t, cual);
        if (g_k12_img == 1) return;
    }
    g_k12_real[cual](t);                                      /* (sin hoja, o tapar=0: el de fábrica como siempre) */
    if (nuestro && !g_k12_tapar) k12_dibujar(t, cual);
}
static void __fastcall k12_tablero0(BYTE *t, void *nada) { (void)nada; k12_tras(t, 0); }
static void __fastcall k12_tablero1(BYTE *t, void *nada) { (void)nada; k12_tras(t, 1); }
static void __fastcall k12_tablero2(BYTE *t, void *nada) { (void)nada; k12_tras(t, 2); }

static void cartel12_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("cartel12", "activo", 1, ini)) {
        apuntar("  [cartel12] apagado ([cartel12] activo=0)");
        return;
    }
    g_k12_base = (BYTE *)GetModuleHandleA(NULL);
    g_k12_z = GetPrivateProfileIntA("cartel12", "z", 100, ini) / 1000.0f;
    g_k12_tapar = GetPrivateProfileIntA("cartel12", "tapar", 1, ini);
    g_k12_cubrir = GetPrivateProfileIntA("cartel12", "cubrir", 96, ini);
    if (g_k12_cubrir < 50 || g_k12_cubrir > 100) g_k12_cubrir = 96;
    /* la guarda: la llamada del grado y las tres ranuras tienen que ser las de siempre */
    BYTE *c = K12V(K12_SITIO_GRADO);
    int ok = c[0] == 0xE8 && (DWORD)(c + 5 + *(int *)(c + 1)) == (DWORD)K12V(0x67D200);
    for (int i = 0; i < 3 && ok; i++)
        ok = *(DWORD *)K12V(K12_VTABLA[i] + 0xC) == (DWORD)K12V(K12_RENDER[i]);
    if (!ok) {
        apuntar("  [cartel12] ⛔ el FF28 o los carteles de fábrica no son los esperados: no se toca nada");
        return;
    }
    void *nuevos[3] = { (void *)k12_tablero0, (void *)k12_tablero1, (void *)k12_tablero2 };
    for (int i = 0; i < 3; i++) {
        g_k12_real[i] = (F_K12_TABLERO)K12V(K12_RENDER[i]);
        DWORD v = (DWORD)nuevos[i];
        if (!k12_escribir(K12_VTABLA[i] + 0xC, &v, 4)) { apuntar("  [cartel12] ⛔ no pude escribir la tabla %d", i); return; }
    }
    int rel = (int)((DWORD)k12_grado - ((DWORD)K12V(K12_SITIO_GRADO) + 5));
    k12_escribir(K12_SITIO_GRADO + 1, &rel, 4);
    g_k12_activo = 1;
    apuntar("  [cartel12] ★ enganchado: la cola C2 tras el grado del FF28 (0x%X) y los 3 carteles de fábrica · z %d/1000"
            " · %s", K12_SITIO_GRADO, (int)(g_k12_z * 1000), g_k12_tapar ? "REEMPLAZA al de fábrica" : "encima del de fábrica");
}
