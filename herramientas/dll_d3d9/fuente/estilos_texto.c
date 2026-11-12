/* estilos_texto.c — LOS ESTILOS DE LETRA de los crayones (23-oct-2026) · CRAYONES_MAZINO.md §5
 *
 * anonimo03: «los estéticos — ignorá los adornos, enfocate en la fuente: color, estilo, grosor; el de arcoíris debe hacer
 * animación fluida, como nuestro ícono de sol arcoíris»; «para círculo y para apodo».
 *
 * Un estilo viaja como un COLOR MARCA — alfa 0xFE, firma A5C0, el número de estilo en el byte bajo — por los mismos
 * caminos que un color: la tabla del apodo (crayones.c, colores 13..21) y la letra de la marca del círculo
 * (circulo_color.c, letras 7..15). El color llega intacto hasta el DIBUJO de verdad del texto, que pasa al vaciar la
 * cola de pedidos (0x639780): según las banderas del pedido va a
 *     0x6364B0  con borde   thiscall(fuentes, x, y, texto, color, borde, b80, recorte, b48)   ret 0x20 · desde 0x639BD4
 *     0x6355D0  sin borde   thiscall(fuentes, x, y, texto, color, b80, recorte, b48)          ret 0x1C · desde 0x639B8E
 *     0x635A30  con borde, con UNA de tres fuentes (los pedidos 0x20/0x100/0x400)
 *               thiscall(fuentes, fuente, x, y, texto, color, borde, recorte)                  ret 0x1C · desde 0x635DF2/E22/E52
 * Esas 5 llamadas pasan por acá: si el color es una marca de estilo, el texto se dibuja varias veces —un CONTORNO
 * GRUESO del color del brillo (8 copias corridas 1 px y 4 a 2 px, más tenues) y encima la letra con su borde— y los
 * animados calculan su color según la hora (por cuadro: fluido). Cualquier otro color pasa derecho.
 * ⚠ El borde del juego es de 1 px: el «grosor» y el brillo son esas copias. Sin la dll, la marca se vería de un
 *   verde agua (A5C0xx) — por eso los estilos van con la dll.   [estilos_texto] activo=0 lo apaga. */

#define EST_MARCA(n) (0xFEA5C000u | (DWORD)(n))
#define EST_ES(c) (((c) & 0xFFFFFFE0u) == 0xFEA5C000u)
#define EST_N 11                 /* len(crayon_crear.ESTILOS) */

/* ★ 24-oct (anonimo03: «los colores, 1 a 1 con los slot ID Mazino y los últimos que añadimos; la única excepción el
 *   arcoíris»): 0..8 = un color por slot (los 6 de la Bruma / Slot Mazino y azul, verde, magenta de la Flama) — el
 *   BRILLO es el color del slot, la letra ese color aclarado —, 9 y 10 los arcoíris. ⚠ El orden es el de crayon_crear.
 * (letra, brillo, borde, animación: 0 quieto · 1 arcoíris neón · 3 arcoíris) — la tabla de las copias corridas (109) */
static const struct { DWORD letra, brillo, borde; int anim; } g_est[EST_N] = {
    { 0xFFFFECB6, 0xFFFFD45C, 0xFF3F3517, 0 },   /* 0 Neón Dorado   */
    { 0xFFFDA5D8, 0xFFFB37A9, 0xFF3E0D2A, 0 },   /* 1 Neón Rosa     */
    { 0xFF8CFFEC, 0xFF00FFD5, 0xFF003F35, 0 },   /* 2 Neón Turquesa */
    { 0xFFFFFFFF, 0xFFFFFFFF, 0xFF3F3F3F, 0 },   /* 3 Neón Blanco   */
    { 0xFFD2A0F1, 0xFF9B2CE0, 0xFF260B38, 0 },   /* 4 Neón Violeta  */
    { 0xFFFF9D9D, 0xFFFF2626, 0xFF3F0909, 0 },   /* 5 Neón Rojo     */
    { 0xFF9ED0FF, 0xFF2896FF, 0xFF0A253F, 0 },   /* 6 Neón Azul     */
    { 0xFFA7FFB0, 0xFF3CFF50, 0xFF0F3F14, 0 },   /* 7 Neón Verde    */
    { 0xFFF6B0FF, 0xFFEB50FF, 0xFF3A143F, 0 },   /* 8 Neón Magenta  */
    { 0xFFFFFFFF, 0xFFFF30C0, 0xFF40002A, 1 },   /* 9 Arcoíris Neón */
    { 0xFFFF5050, 0x00000000, 0xFF000000, 3 },   /* 10 Arcoíris (sin brillo: la letra cambia de color) */
};
#define EST_ARCO_NEON 9
#define EST_ARCO 10
#define EST_MS_ARCOIRIS 3000     /* una vuelta de colores (como el sol arcoíris) */

static BYTE *g_est_base = NULL;
#define ESTV(x) (g_est_base + ((DWORD)(x) - 0x400000))
static LARGE_INTEGER g_est_hz;

static long long est_ms(void)
{
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    return g_est_hz.QuadPart ? t.QuadPart * 1000 / g_est_hz.QuadPart : (long long)GetTickCount();
}

static DWORD est_hsv(float h, float s, float v)          /* h en [0, 6) */
{
    int i = (int)h % 6;
    float f = h - (int)h, p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
    float r, g, b;
    switch (i) {
        case 0: r = v; g = t; b = p; break;
        case 1: r = q; g = v; b = p; break;
        case 2: r = p; g = v; b = t; break;
        case 3: r = p; g = q; b = v; break;
        case 4: r = t; g = p; b = v; break;
        default: r = v; g = p; b = q; break;
    }
    return 0xFF000000u | ((DWORD)(r * 255) << 16) | ((DWORD)(g * 255) << 8) | (DWORD)(b * 255);
}

static DWORD est_mezcla(DWORD a, DWORD b, float t)
{
    DWORD out = 0;
    for (int k = 0; k < 32; k += 8) {
        float x = (float)((a >> k) & 0xFF) * (1 - t) + (float)((b >> k) & 0xFF) * t;
        out |= ((DWORD)(x + 0.5f) & 0xFF) << k;
    }
    return out;
}

/* los colores de este cuadro para el estilo n */
static void est_colores(int n, DWORD *letra, DWORD *brillo, DWORD *borde)
{
    *letra = g_est[n].letra;
    *brillo = g_est[n].brillo;
    *borde = g_est[n].borde;
    long long ms = est_ms();
    float h = (float)(ms % EST_MS_ARCOIRIS) * 6.0f / EST_MS_ARCOIRIS;
    if (g_est[n].anim == 1) {                                  /* arcoíris neón: el brillo da la vuelta */
        *brillo = est_hsv(h, 1.0f, 1.0f);
        *letra = est_mezcla(0xFFFFFFFF, *brillo, 0.22f);
        *borde = est_mezcla(0xFF000000, *brillo, 0.35f);
    } else if (g_est[n].anim == 3) {                           /* arcoíris: la letra da la vuelta */
        *letra = est_hsv(h, 0.85f, 1.0f);
    }
}

typedef void (__attribute__((thiscall)) *F_EST_BORDE)(void *, int, int, const char *, DWORD, DWORD, int, void *, int);
typedef void (__attribute__((thiscall)) *F_EST_SIN)(void *, int, int, const char *, DWORD, int, void *, int);
typedef void (__attribute__((thiscall)) *F_EST_FUENTE)(void *, void *, int, int, const char *, DWORD, DWORD, void *);

static const signed char g_est_aro1[8][2] = { {-1,0},{1,0},{0,-1},{0,1},{-1,-1},{1,-1},{-1,1},{1,1} };
static const signed char g_est_aro2[4][2] = { {-2,0},{2,0},{0,-2},{0,2} };

/* el contorno grueso (si el estilo tiene brillo) y la letra, con un dibujo con borde `d(x, y, color, borde)` */
#define EST_PINTAR(d)                                                                                            \
    do {                                                                                                         \
        DWORD le, br, bo;                                                                                        \
        est_colores(n, &le, &br, &bo);                                                                           \
        if (br >> 24) {                                                                                          \
            DWORD tenue = (br & 0x00FFFFFF) | 0x70000000;                                                        \
            for (int k = 0; k < 4; k++) d(x + g_est_aro2[k][0], y + g_est_aro2[k][1], tenue, tenue);             \
            for (int k = 0; k < 8; k++) d(x + g_est_aro1[k][0], y + g_est_aro1[k][1], br, br);                   \
        }                                                                                                        \
        d(x, y, le, bo);                                                                                         \
    } while (0)

/* ═══ 2 · ★ LA LETRA PROPIA (24-oct) · CRAYONES_MAZINO.md §6 ═══════════════════════════════════════════════════════
 *
 * anonimo03 vio (109): «no se parece la fuente a la del ejemplo, y el arcoíris parece un foco que cambia de color: los
 * colores deben recorrer la palabra … te pedí un 1 a 1». Así que con una marca de estilo la dll ya NO llama al dibujo
 * del juego: arma ELLA la imagen del nombre (lo mismo que `herramientas/estilos_letra_vista.py`) y la dibuja.
 *
 *   · la letra: GDI, la fuente de [estilos_texto] fuentes (la 1.ª; Ctrl+F8 pasa a la siguiente EN VIVO, para
 *     comparar), ×EL_SS, con las puntas redondeadas (suavizar y recortar), achicada a su tamaño;
 *   · las capas (relleno, brillo ancho y suave, filo claro pegado a la letra) se guardan por píxel, y el color se
 *     compone con la hora: los quietos UNA vez, los animados (arcoíris neón, fuego, arcoíris) en cada cuadro — el
 *     arcoíris con el tono según la x: el degradé RECORRE la palabra;
 *   · todo va a UNA textura nuestra de EL_LADO² con un caché por (texto, estilo, fuente, tamaño) y se dibuja con un
 *     DrawPrimitiveUP, guardando y devolviendo cada estado que toca;
 *   · el lugar: el juego escribe con un ID3DXFont arriba a la izquierda de (x, y) (`DrawTextA`, DT_NOCLIP); se mide el
 *     texto del juego con esa misma fuente (DT_CALCRECT) y el nuestro va CENTRADO sobre ese recuadro. El tamaño de la
 *     letra sale de la fuente del juego (GetDesc) × [estilos_texto] tamano (%);
 *   · el recorte del juego (las listas) es un viewport: acá, un scissor con el mismo rectángulo.
 *   Si algo falla (sin dispositivo, sin textura), vuelve SOLO a las copias corridas de (109).
 *   [estilos_texto] letra=0 la apaga (y quedan las copias de (109)). */
#define EL_SS 4                  /* la letra se arma ×4 y se achica: puntas redondeadas y bordes suaves   */
#define EL_PAD 4                 /* margen alrededor (px finales): ahí entra el brillo                     */
#define EL_LADO 512              /* la textura del caché                                                    */
#define EL_MAX 160               /* entradas del caché                                                      */
#define EL_FUENTES 10

typedef struct {
    DWORD clave;
    int n, w, h;                 /* estilo y tamaño final (con el margen)                                  */
    int ax, ay;                  /* dónde está en la textura                                                */
    int tw, th;                  /* lo que ocupa el TEXTO (sin margen), para centrar                        */
    BYTE *capas;                 /* w×h×4: relleno, halo, 2.ª capa, 3.ª capa (según el brillo; 0..255)      */
    long long compuesto;         /* el ms del último compuesto (los animados se recomponen si cambió)      */
} EL_ENT;

static EL_ENT g_elc[EL_MAX];
static int g_elc_n = 0, g_el_cx = 0, g_el_cy = 0, g_el_fila = 0;     /* el estante del empaquetado */
static DWORD g_el_px[EL_LADO * EL_LADO];                              /* la textura, en memoria        */
static RECT g_el_sucio = { EL_LADO, EL_LADO, 0, 0 };
static void *g_el_tex = NULL, *g_el_dev = NULL;
static int g_el_pool = 1;
static int g_el_estado = 0;      /* 0 sin probar · 1 listo · -1 apagado / falló (copias de (109))        */
static char g_el_fuente[EL_FUENTES][64];
static int g_el_peso[EL_FUENTES], g_el_nf = 0, g_el_cual = 0, g_el_tamano = 100, g_el_tecla = 0;
static int g_el_cara_vista = -1;                                  /* de qué fuente ya se anotó la cara real */

/* ★ 24-oct, EL BRILLO (anonimo03, después de ver 6 en el juego, CRAYONES_MAZINO.md §8): «me gusta mucho el D caramelo,
 *   lo quisiera con el efecto que recorre la palabra de "tubo con destello"» ⇒ el CARAMELO —halo del color, borde
 *   oscuro del color, la letra en degradé (clara arriba, el color abajo) y un reflejo blanco arriba— y encima un
 *   DESTELLO: una franja de luz inclinada que cruza la palabra (EL_MS_DESTELLO). El arcoíris liso queda como estaba. */
#define EL_MS_DESTELLO 3000

static void el_colores_fijos(int n, float *le, float *br)
{
    for (int k = 0; k < 3; k++) {
        le[k] = (float)((g_est[n].letra >> (16 - 8 * k)) & 0xFF);
        br[k] = (float)((g_est[n].brillo >> (16 - 8 * k)) & 0xFF);
    }
}

static int el_animado(int n) { (void)n; return 1; }   /* el destello recorre todos (y los arcoíris dan la vuelta) */

/* un desenfoque de caja de radio 1 (3×3), `veces` pasadas, sobre bytes */
static void el_caja(BYTE *a, BYTE *tmp, int W, int H, int veces)
{
    for (int v = 0; v < veces; v++) {
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int s = a[y * W + x] * 2, c = 2;
                if (x > 0) { s += a[y * W + x - 1]; c++; }
                if (x < W - 1) { s += a[y * W + x + 1]; c++; }
                tmp[y * W + x] = (BYTE)((s + c / 2) / c);
            }
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int s = tmp[y * W + x] * 2, c = 2;
                if (y > 0) { s += tmp[(y - 1) * W + x]; c++; }
                if (y < H - 1) { s += tmp[(y + 1) * W + x]; c++; }
                a[y * W + x] = (BYTE)((s + c / 2) / c);
            }
    }
}

/* engordar (dil=1) o afinar (dil=0) con un disco de radio r (en px de ×EL_SS) */
static void el_morf(const BYTE *a, BYTE *o, int W, int H, int r, int dil)
{
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int v = dil ? 0 : 255;
            for (int dy = -r; dy <= r; dy++)
                for (int dx = -r; dx <= r; dx++) {
                    if (dx * dx + dy * dy > r * r + r) continue;
                    int yy = y + dy, xx = x + dx;
                    int q = (yy >= 0 && yy < H && xx >= 0 && xx < W) ? a[yy * W + xx] : 0;
                    if (dil ? q > v : q < v) v = q;
                }
            o[y * W + x] = (BYTE)v;
        }
}

/* de ×EL_SS al tamaño final (promedio) */
static void el_achicar(const BYTE *a, BYTE *o, int W, int w, int h)
{
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            int sm = 0;
            for (int j = 0; j < EL_SS; j++)
                for (int i = 0; i < EL_SS; i++) sm += a[(y * EL_SS + j) * W + x * EL_SS + i];
            o[y * w + x] = (BYTE)(sm / (EL_SS * EL_SS));
        }
}

/* un halo: la letra desenfocada (`pasadas` cajas: σ ≈ √(2·pasadas/3) px), × mult, con tope */
static void el_halo(BYTE *o, const BYTE *rel, BYTE *tmp, int w, int h, int pasadas, float mult, float tope)
{
    CopyMemory(o, rel, (SIZE_T)w * h);
    el_caja(o, tmp, w, h, pasadas);
    for (int i = 0; i < w * h; i++) {
        float v = o[i] * mult;
        if (v > tope * 255) v = tope * 255;
        o[i] = (BYTE)v;
    }
}

/* arma las capas del texto: 1 si salió */
static int el_armar(EL_ENT *e, const char *s, int alto)
{
    WCHAR ws[256], cara[64];
    int nw = id_a_ancho(s, ws, 256);                    /* (126) UTF-8 o 1252, como el juego (antes 949 y la de Windows) */
    if (nw <= 1) return 0;
    nw--;
    MultiByteToWideChar(CP_ACP, 0, g_el_fuente[g_el_cual], -1, cara, 64);
    HDC dc = CreateCompatibleDC(NULL);
    if (!dc) return 0;
    int lf = alto * g_el_tamano / 100;
    HFONT f = CreateFontW(-lf * EL_SS, 0, 0, 0, g_el_peso[g_el_cual], 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS,
                          CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, cara);
    HGDIOBJ viejo = SelectObject(dc, f);
    if (g_el_cara_vista != g_el_cual) {                       /* ⚠ si no la tiene, Windows pone OTRA sin avisar */
        WCHAR real[64];
        char real8[64];
        g_el_cara_vista = g_el_cual;
        GetTextFaceW(dc, 64, real);
        WideCharToMultiByte(CP_ACP, 0, real, -1, real8, 64, NULL, NULL);
        apuntar("  [estilos_texto] letra %d/%d «%s» → Windows usa «%s»%s", g_el_cual + 1, g_el_nf,
                g_el_fuente[g_el_cual], real8, lstrcmpiA(real8, g_el_fuente[g_el_cual]) ? "  ⛔ NO ES LA PEDIDA" : "");
    }
    SIZE t = { 0, 0 };
    GetTextExtentPoint32W(dc, ws, nw, &t);
    int pad = EL_PAD * EL_SS;
    int W = ((t.cx + 2 * pad + EL_SS - 1) / EL_SS) * EL_SS, H = ((t.cy + 2 * pad + EL_SS - 1) / EL_SS) * EL_SS;
    int w = W / EL_SS, h = H / EL_SS;
    if (t.cx <= 0 || w > EL_LADO || h > EL_LADO / 4) { SelectObject(dc, viejo); DeleteObject(f); DeleteDC(dc); return 0; }
    BITMAPINFO bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(bi.bmiHeader);
    bi.bmiHeader.biWidth = W;
    bi.bmiHeader.biHeight = -H;                                /* de arriba hacia abajo */
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    void *bits = NULL;
    HBITMAP bm = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    BYTE *m = (BYTE *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (SIZE_T)W * H * 3);
    BYTE *capas = (BYTE *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (SIZE_T)w * h * 5);
    if (!bm || !bits || !m || !capas) {
        if (bm) DeleteObject(bm);
        if (m) HeapFree(GetProcessHeap(), 0, m);
        if (capas) HeapFree(GetProcessHeap(), 0, capas);
        SelectObject(dc, viejo); DeleteObject(f); DeleteDC(dc);
        return 0;
    }
    HGDIOBJ vbm = SelectObject(dc, bm);
    ZeroMemory(bits, (SIZE_T)W * H * 4);
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(255, 255, 255));
    TextOutW(dc, pad, pad, ws, nw);
    GdiFlush();
    BYTE *tmp = m + W * H, *filo = m + 2 * W * H;
    for (int i = 0; i < W * H; i++) m[i] = ((BYTE *)bits)[i * 4 + 1];
    SelectObject(dc, vbm); DeleteObject(bm);
    SelectObject(dc, viejo); DeleteObject(f); DeleteDC(dc);

    /* las puntas redondeadas: suavizar (≈ σ 0,32 px finales) y recortar lo que pasa el umbral, con borde suave */
    el_caja(m, tmp, W, H, 1);
    for (int i = 0; i < W * H; i++) {
        int v = (m[i] - 115) * 4;
        m[i] = (BYTE)(v < 0 ? 0 : v > 255 ? 255 : v);
    }
    /* las capas del caramelo: c1 el halo (σ 2), c2 el borde (la letra engordada 0,8 px − la letra), c3 el núcleo
     *   (la letra afinada 0,4 px: ahí va el reflejo, sin tocar el borde) */
    BYTE *rel = capas, *c1 = capas + w * h, *c2 = capas + 2 * w * h, *c3 = capas + 3 * w * h, *tmp2 = capas + 4 * w * h;
    el_achicar(m, rel, W, w, h);
    el_morf(m, filo, W, H, (EL_SS * 8 + 5) / 10, 1);
    for (int k = 0; k < W * H; k++) filo[k] = (BYTE)(filo[k] - m[k]);
    el_achicar(filo, c2, W, w, h);
    el_morf(m, filo, W, H, (EL_SS * 4 + 5) / 10, 0);
    el_achicar(filo, c3, W, w, h);
    el_halo(c1, rel, tmp2, w, h, 6, 1.3f, 0.70f);
    HeapFree(GetProcessHeap(), 0, m);
    e->w = w; e->h = h;
    e->tw = t.cx / EL_SS; e->th = t.cy / EL_SS;
    e->capas = capas;
    return 1;
}

/* compone el color de la entrada en la textura en memoria, para el ms `ms` (premultiplicado: ONE / INVSRCALPHA) */
static void el_componer(EL_ENT *e, long long ms)
{
    float le[3], br[3];
    el_colores_fijos(e->n, le, br);
    float fase = (float)(ms % EST_MS_ARCOIRIS) / EST_MS_ARCOIRIS;
    int arco = e->n == EST_ARCO_NEON || e->n == EST_ARCO;
    float destello = (float)(ms % EL_MS_DESTELLO) / EL_MS_DESTELLO * 1.6f - 0.3f;   /* de −0,3 a 1,3: cruza entera */
    const BYTE *rel = e->capas, *c1 = e->capas + e->w * e->h, *c2 = e->capas + 2 * e->w * e->h,
               *c3 = e->capas + 3 * e->w * e->h;
    for (int x = 0; x < e->w; x++) {
        float col[3] = { br[0], br[1], br[2] };
        float xn = (float)x / (float)(e->w > 1 ? e->w - 1 : 1);
        if (arco) {                                            /* el degradé RECORRE la palabra */
            float h = xn * 1.2f - fase;
            h -= (float)(int)h;
            if (h < 0) h += 1;
            DWORD c = est_hsv(h * 6.0f, 1.0f, 1.0f);
            col[0] = (float)((c >> 16) & 255); col[1] = (float)((c >> 8) & 255); col[2] = (float)(c & 255);
        }
        for (int y = 0; y < e->h; y++) {
            int i = y * e->w + x;
            float m = rel[i] / 255.0f, a1 = c1[i] / 255.0f, a2 = c2[i] / 255.0f, a3 = c3[i] / 255.0f;
            float yy = (float)y / (float)(e->h > 1 ? e->h - 1 : 1);
            float r = 0, g = 0, b = 0, a = 0, t[3];
#define EL_SOBRE(c, al)                                                                                         \
            do { float q = (al); if (q > 1) q = 1; r = (c)[0] * q + r * (1 - q); g = (c)[1] * q + g * (1 - q);    \
                 b = (c)[2] * q + b * (1 - q); a = q + a * (1 - q); } while (0)
#define EL_MEZ(o, c, k, d) do { for (int z = 0; z < 3; z++) (o)[z] = (c)[z] * (1 - (k)) + (d) * (k); } while (0)
            if (e->n == EST_ARCO) {                            /* el arcoíris liso: como estaba, con su borde oscuro */
                float osc[3] = { 20, 20, 20 };
                EL_SOBRE(osc, a2 * 0.9f);
                EL_MEZ(t, col, 0.2f, 255);
                EL_SOBRE(t, m);
            } else {                                           /* el caramelo */
                EL_SOBRE(col, a1);
                EL_MEZ(t, col, 0.6f, 0);
                EL_SOBRE(t, a2);
                for (int z = 0; z < 3; z++) t[z] = (col[z] * 0.45f + 140) * (1 - yy) + col[z] * yy;
                EL_SOBRE(t, m);
                float refl = yy > 0.18f ? 1 - (yy - 0.30f) / 0.12f : 0;
                refl = refl < 0 ? 0 : refl > 1 ? 1 : refl;
                float bl[3] = { 255, 255, 255 };
                EL_SOBRE(bl, a3 * refl * 0.75f);
                float d = (xn + yy * 0.25f - destello) / 0.06f, banda = 1 - d * d / 4;   /* el destello */
                if (banda > 0) EL_SOBRE(bl, m * banda * banda * 0.9f);
            }
#undef EL_SOBRE
#undef EL_MEZ
            if (r > 255) r = 255;
            if (g > 255) g = 255;
            if (b > 255) b = 255;
            DWORD px = ((DWORD)(a * 255 + 0.5f) << 24) | ((DWORD)(r + 0.5f) << 16) | ((DWORD)(g + 0.5f) << 8) |
                       (DWORD)(b + 0.5f);
            g_el_px[(e->ay + y) * EL_LADO + e->ax + x] = px;
        }
    }
    if (e->ax < g_el_sucio.left) g_el_sucio.left = e->ax;
    if (e->ay < g_el_sucio.top) g_el_sucio.top = e->ay;
    if (e->ax + e->w > g_el_sucio.right) g_el_sucio.right = e->ax + e->w;
    if (e->ay + e->h > g_el_sucio.bottom) g_el_sucio.bottom = e->ay + e->h;
    e->compuesto = ms;
}

static void el_vaciar(void)
{
    for (int i = 0; i < g_elc_n; i++) if (g_elc[i].capas) HeapFree(GetProcessHeap(), 0, g_elc[i].capas);
    g_elc_n = 0; g_el_cx = g_el_cy = g_el_fila = 0;
}

static DWORD el_clave(const char *s, int n, int alto)
{
    DWORD f = 2166136261u;
    for (const BYTE *p = (const BYTE *)s; *p; p++) { f ^= *p; f *= 16777619u; }
    f ^= (DWORD)n * 0x9E3779B1u ^ (DWORD)alto << 8 ^ (DWORD)g_el_cual << 20 ^ (DWORD)g_el_tamano << 24;
    return f;
}

static EL_ENT *el_buscar(const char *s, int n, int alto)
{
    DWORD k = el_clave(s, n, alto);
    for (int i = 0; i < g_elc_n; i++) if (g_elc[i].clave == k && g_elc[i].n == n) return &g_elc[i];
    EL_ENT nueva;
    ZeroMemory(&nueva, sizeof(nueva));
    nueva.clave = k;
    nueva.n = n;
    if (!el_armar(&nueva, s, alto)) return NULL;
    /* el lugar en la textura: estantes; si no entra, se vacía todo (lo de pantalla se rearma solo) */
    if (g_el_cx + nueva.w > EL_LADO) { g_el_cx = 0; g_el_cy += g_el_fila; g_el_fila = 0; }
    if (g_elc_n >= EL_MAX || g_el_cy + nueva.h > EL_LADO) {
        el_vaciar();
        apuntar("  [estilos_texto] la textura de la letra se llenó: vuelvo a empezar");
    }
    nueva.ax = g_el_cx; nueva.ay = g_el_cy;
    g_el_cx += nueva.w + 1;
    if (nueva.h + 1 > g_el_fila) g_el_fila = nueva.h + 1;
    g_elc[g_elc_n] = nueva;
    EL_ENT *e = &g_elc[g_elc_n++];
    el_componer(e, est_ms());
    return e;
}

/* ── el dispositivo: el del juego ([0x931498]→+0x58) ── */
typedef void *(__attribute__((thiscall)) *F_EL_DEV)(void *);
typedef long (__stdcall *D_RS)(void *, DWORD, DWORD);
typedef long (__stdcall *D_GRS)(void *, DWORD, DWORD *);
typedef long (__stdcall *D_TSS)(void *, DWORD, DWORD, DWORD);
typedef long (__stdcall *D_GTSS)(void *, DWORD, DWORD, DWORD *);
typedef long (__stdcall *D_PTR)(void *, void *);
typedef long (__stdcall *D_GPTR)(void *, void **);
typedef long (__stdcall *D_TEX)(void *, DWORD, void *);
typedef long (__stdcall *D_GTEX)(void *, DWORD, void **);
typedef long (__stdcall *D_DW)(void *, DWORD);
typedef long (__stdcall *D_GDW)(void *, DWORD *);
typedef long (__stdcall *D_RECT)(void *, const RECT *);
typedef long (__stdcall *D_GRECT)(void *, RECT *);
typedef long (__stdcall *D_UP)(void *, DWORD, UINT, const void *, UINT);
typedef long (__stdcall *D_GSS)(void *, UINT, void **, UINT *, UINT *);
typedef long (__stdcall *D_SS)(void *, UINT, void *, UINT, UINT);
typedef long (__stdcall *D_CREARTEX)(void *, UINT, UINT, UINT, DWORD, DWORD, DWORD, void **, void *);
typedef ULONG (__stdcall *C_SOLTAR)(void *);

static void *el_dispositivo(void)
{
    void *envol = *(void **)ESTV(0x931498);
    if (!envol) return NULL;
    void **vt = *(void ***)envol;
    return ((F_EL_DEV)vt[0x58 / 4])(envol);
}

static int el_textura(void *dev)
{
    if (g_el_tex && dev == g_el_dev) return 1;
    void **vt = *(void ***)dev;
    g_el_tex = NULL;
    /* el 9Ex no tiene MANAGED: ahí DEFAULT + DYNAMIC, y se escribe entera con DISCARD */
    g_el_pool = g_dispositivo_es_ex ? 0 : 1;
    long hr = ((D_CREARTEX)vt[23])(dev, EL_LADO, EL_LADO, 1, g_el_pool ? 0 : 0x200 /* DYNAMIC */, 21 /* A8R8G8B8 */,
                                   (DWORD)g_el_pool, &g_el_tex, NULL);
    if (hr != 0 || !g_el_tex) {
        apuntar("  [estilos_texto] ⛔ no pude crear la textura de la letra (hr=%08lX): vuelvo a las copias de (109)",
                (unsigned long)hr);
        g_el_estado = -1;
        return 0;
    }
    g_el_dev = dev;
    el_vaciar();
    ZeroMemory(g_el_px, sizeof(g_el_px));
    g_el_sucio.left = g_el_sucio.top = 0; g_el_sucio.right = g_el_sucio.bottom = EL_LADO;
    apuntar("  [estilos_texto] ★ textura de la letra lista (%dx%d, pool %d)", EL_LADO, EL_LADO, g_el_pool);
    return 1;
}

static void el_subir(void)
{
    if (g_el_sucio.right <= g_el_sucio.left || g_el_sucio.bottom <= g_el_sucio.top) return;
    void **vt = *(void ***)g_el_tex;
    CALC_BLOQUEO b;
    RECT r = g_el_sucio;
    if (!g_el_pool) { r.left = r.top = 0; r.right = r.bottom = EL_LADO; }
    if (((T_BLOQUEAR)vt[19])(g_el_tex, 0, &b, g_el_pool ? &r : NULL, g_el_pool ? 0 : 0x2000 /* DISCARD */) != 0) return;
    for (int y = r.top; y < r.bottom; y++)
        CopyMemory((BYTE *)b.pBits + (y - (g_el_pool ? r.top : 0)) * b.Pitch, g_el_px + y * EL_LADO + r.left,
                   (SIZE_T)(r.right - r.left) * 4);
    ((T_SOLTAR)vt[20])(g_el_tex, 0);
    g_el_sucio.left = g_el_sucio.top = EL_LADO; g_el_sucio.right = g_el_sucio.bottom = 0;
}

/* dibuja la entrada en (x, y) de pantalla, con el recorte del juego (o sin) */
static void el_dibujar(void *dev, EL_ENT *e, int x, int y, const RECT *rec)
{
    void **vt = *(void ***)dev;
    D_RS srs = (D_RS)vt[57]; D_GRS grs = (D_GRS)vt[58];
    D_TSS stss = (D_TSS)vt[67]; D_GTSS gtss = (D_GTSS)vt[66];
    D_TSS ssam = (D_TSS)vt[69]; D_GTSS gsam = (D_GTSS)vt[68];
    static const DWORD rs[][2] = {
        { 27, 1 }, { 19, 2 }, { 20, 6 }, { 171, 1 }, { 15, 0 }, { 7, 0 }, { 14, 0 }, { 22, 1 }, { 137, 0 },
        { 28, 0 }, { 206, 0 }, { 168, 0xF }, { 194, 0 }, { 52, 0 }, { 174, 0 },
    };
    static const DWORD ts[][3] = {
        { 0, 1, 4 }, { 0, 2, 2 }, { 0, 3, 0 }, { 0, 4, 4 }, { 0, 5, 2 }, { 0, 6, 0 }, { 0, 11, 0 }, { 0, 24, 0 },
        { 1, 1, 1 }, { 1, 4, 1 },
    };
    static const DWORD sa[][2] = { { 1, 3 }, { 2, 3 }, { 5, 1 }, { 6, 1 }, { 7, 0 }, { 11, 0 } };
    enum { NRS = sizeof(rs) / sizeof(rs[0]), NTS = sizeof(ts) / sizeof(ts[0]), NSA = sizeof(sa) / sizeof(sa[0]) };
    DWORD vrs[NRS], vts[NTS], vsa[NSA], fvf = 0;
    void *tex0 = NULL, *vdecl = NULL, *vs = NULL, *ps = NULL, *vb = NULL;
    UINT vb_off = 0, vb_paso = 0;
    RECT tijera;
    for (int i = 0; i < NRS; i++) grs(dev, rs[i][0], &vrs[i]);
    for (int i = 0; i < NTS; i++) gtss(dev, ts[i][0], ts[i][1], &vts[i]);
    for (int i = 0; i < NSA; i++) gsam(dev, 0, sa[i][0], &vsa[i]);
    ((D_GTEX)vt[64])(dev, 0, &tex0);
    ((D_GDW)vt[90])(dev, &fvf);
    ((D_GPTR)vt[88])(dev, &vdecl);
    ((D_GPTR)vt[93])(dev, &vs);
    ((D_GPTR)vt[108])(dev, &ps);
    ((D_GSS)vt[101])(dev, 0, &vb, &vb_off, &vb_paso);
    ((D_GRECT)vt[76])(dev, &tijera);

    for (int i = 0; i < NRS; i++) srs(dev, rs[i][0], rs[i][1]);
    for (int i = 0; i < NTS; i++) stss(dev, ts[i][0], ts[i][1], ts[i][2]);
    for (int i = 0; i < NSA; i++) ssam(dev, 0, sa[i][0], sa[i][1]);
    if (rec) {
        ((D_RECT)vt[75])(dev, rec);
        srs(dev, 174, 1);
    }
    ((D_TEX)vt[65])(dev, 0, g_el_tex);
    ((D_PTR)vt[92])(dev, NULL);
    ((D_PTR)vt[107])(dev, NULL);
    ((D_DW)vt[89])(dev, 0x144);                                /* XYZRHW | DIFFUSE | TEX1 */
    struct { float x, y, z, w; DWORD c; float u, v; } q[4];
    float x0 = (float)x - 0.5f, y0 = (float)y - 0.5f, x1 = x0 + (float)e->w, y1 = y0 + (float)e->h;
    float u0 = (float)e->ax / EL_LADO, v0 = (float)e->ay / EL_LADO;
    float u1 = (float)(e->ax + e->w) / EL_LADO, v1 = (float)(e->ay + e->h) / EL_LADO;
    float px[4][4] = { { x0, y0, u0, v0 }, { x1, y0, u1, v0 }, { x0, y1, u0, v1 }, { x1, y1, u1, v1 } };
    for (int i = 0; i < 4; i++) {
        q[i].x = px[i][0]; q[i].y = px[i][1]; q[i].z = 0; q[i].w = 1;
        q[i].c = 0xFFFFFFFF; q[i].u = px[i][2]; q[i].v = px[i][3];
    }
    ((D_UP)vt[83])(dev, 5 /* TRIANGLESTRIP */, 2, q, sizeof(q[0]));

    /* devolver todo como estaba */
    for (int i = 0; i < NRS; i++) srs(dev, rs[i][0], vrs[i]);
    for (int i = 0; i < NTS; i++) stss(dev, ts[i][0], ts[i][1], vts[i]);
    for (int i = 0; i < NSA; i++) ssam(dev, 0, sa[i][0], vsa[i]);
    ((D_RECT)vt[75])(dev, &tijera);
    ((D_TEX)vt[65])(dev, 0, tex0);
    if (fvf || !vdecl) ((D_DW)vt[89])(dev, fvf); else ((D_PTR)vt[87])(dev, vdecl);
    ((D_PTR)vt[92])(dev, vs);
    ((D_PTR)vt[107])(dev, ps);
    ((D_SS)vt[100])(dev, 0, vb, vb_off, vb_paso);
    void *suelta[5] = { tex0, vdecl, vs, ps, vb };
    for (int i = 0; i < 5; i++) if (suelta[i]) ((C_SOLTAR)(*(void ***)suelta[i])[2])(suelta[i]);
}

/* ── la fuente del juego: su tamaño (GetDescA) y lo que mide el texto con ella (DrawTextA + DT_CALCRECT) ── */
typedef struct { INT Height; UINT Width, Weight, MipLevels; BOOL Italic; BYTE cs, op, q, pf; CHAR Face[32]; } EL_FDESC;
typedef long (__stdcall *X_DESC)(void *, EL_FDESC *);
typedef INT (__stdcall *X_TEXTO)(void *, void *, const char *, INT, RECT *, DWORD, DWORD);
typedef void *(__attribute__((thiscall)) *F_EL_FUENTE)(void *, int, int);

static void el_tecla(void)
{
    int baja = (GetAsyncKeyState(VK_CONTROL) & 0x8000) && (GetAsyncKeyState(VK_F8) & 0x8000);
    if (baja && !g_el_tecla && g_el_nf > 1) {
        DWORD pid = 0;
        GetWindowThreadProcessId(GetForegroundWindow(), &pid);
        if (pid == GetCurrentProcessId()) {
            g_el_cual = (g_el_cual + 1) % g_el_nf;
            el_vaciar();
            apuntar("  [estilos_texto] Ctrl+F8 → la letra ahora es «%s» (peso %d)", g_el_fuente[g_el_cual],
                    g_el_peso[g_el_cual]);
        }
    }
    g_el_tecla = baja;
}

/* 1 si lo dibujó la letra propia; 0 → que siga el camino de (109) */
static int el_texto(void *xfont, int x, int y, const char *s, int n, const RECT *rec)
{
    if (g_el_estado < 0 || !xfont || !s || !*s) return 0;
    for (const char *p = s; *p; p++) if (*p == '\n' || *p == '\r') return 0;
    void *dev = el_dispositivo();
    if (!dev || !el_textura(dev)) return 0;
    g_el_estado = 1;
    el_tecla();
    void **fv = *(void ***)xfont;
    EL_FDESC d;
    ZeroMemory(&d, sizeof(d));
    if (((X_DESC)fv[4])(xfont, &d) != 0) return 0;
    int alto = d.Height < 0 ? -d.Height : d.Height;
    if (alto <= 0) return 0;
    static void *visto[8];
    int ya = 0;
    for (int i = 0; i < 8; i++) if (visto[i] == xfont) ya = 1;
    if (!ya) {
        for (int i = 7; i > 0; i--) visto[i] = visto[i - 1];
        visto[0] = xfont;
        apuntar("  [estilos_texto] fuente del juego %p: «%s» alto %d peso %u", xfont, d.Face, d.Height, d.Weight);
    }
    RECT r = { x, y, x, y };
    ((X_TEXTO)fv[14])(xfont, NULL, s, -1, &r, 0x400 /* CALCRECT */ | 0x100 /* NOCLIP */, 0xFFFFFFFF);
    EL_ENT *e = el_buscar(s, n, alto);
    if (!e) return 0;
    long long ms = est_ms();
    if (el_animado(n) && ms != e->compuesto) el_componer(e, ms);
    el_subir();
    int gx = x + ((r.right - r.left) - e->tw) / 2 - EL_PAD;
    int gy = y + ((r.bottom - r.top) - e->th) / 2 - EL_PAD;
    el_dibujar(dev, e, gx, gy, rec);
    return 1;
}

static void __fastcall est_borde(void *f, void *nada, int x, int y, const char *s, DWORD col, DWORD borde, int b80,
                                 void *rec, int b48)
{
    (void)nada;
    F_EST_BORDE o = (F_EST_BORDE)ESTV(0x6364B0);
    if (!EST_ES(col) || (int)(col & 0x1F) >= EST_N) { o(f, x, y, s, col, borde, b80, rec, b48); return; }
    int n = (int)(col & 0x1F);
    if (el_texto(((F_EL_FUENTE)ESTV(0x6352E0))(f, b80, b48), x, y, s, n, (const RECT *)rec)) return;
#define EST_D(xx, yy, c, b) o(f, xx, yy, s, c, b, b80, rec, b48)
    EST_PINTAR(EST_D);
#undef EST_D
}

static void __fastcall est_sin(void *f, void *nada, int x, int y, const char *s, DWORD col, int b80, void *rec, int b48)
{
    (void)nada;
    if (!EST_ES(col) || (int)(col & 0x1F) >= EST_N) {
        ((F_EST_SIN)ESTV(0x6355D0))(f, x, y, s, col, b80, rec, b48);
        return;
    }
    int n = (int)(col & 0x1F);
    if (el_texto(((F_EL_FUENTE)ESTV(0x6352E0))(f, b80, b48), x, y, s, n, (const RECT *)rec)) return;
    F_EST_BORDE o = (F_EST_BORDE)ESTV(0x6364B0);                /* (con estilo, siempre con borde) */
#define EST_D(xx, yy, c, b) o(f, xx, yy, s, c, b, b80, rec, b48)
    EST_PINTAR(EST_D);
#undef EST_D
}

static void __fastcall est_fuente(void *f, void *nada, void *fuente, int x, int y, const char *s, DWORD col,
                                  DWORD borde, void *rec)
{
    (void)nada;
    F_EST_FUENTE o = (F_EST_FUENTE)ESTV(0x635A30);
    if (!EST_ES(col) || (int)(col & 0x1F) >= EST_N) { o(f, fuente, x, y, s, col, borde, rec); return; }
    int n = (int)(col & 0x1F);
    if (el_texto(fuente, x, y, s, n, (const RECT *)rec)) return;
#define EST_D(xx, yy, c, b) o(f, fuente, xx, yy, s, c, b, rec)
    EST_PINTAR(EST_D);
#undef EST_D
}

static void estilos_texto_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_est_base = (BYTE *)GetModuleHandleA(NULL);
    if (!GetPrivateProfileIntA("estilos_texto", "activo", 1, ini)) {
        apuntar("  [estilos_texto] APAGADO ([estilos_texto] activo=0): los estilos de letra salen de un color plano");
        return;
    }
    QueryPerformanceFrequency(&g_est_hz);
    /* la letra propia (§2): las fuentes «Nombre:peso|Nombre:peso…»; Ctrl+F8 pasa de una a otra en vivo */
    if (!GetPrivateProfileIntA("estilos_texto", "letra", 1, ini)) {
        g_el_estado = -1;
        apuntar("  [estilos_texto] letra propia APAGADA ([estilos_texto] letra=0): copias corridas de (109)");
    }
    char lista[512], *p = lista;
    /* ★ 24-oct, anonimo03 eligió en el juego, entre 7 (CRAYONES_MAZINO.md §6.3): SEGOE UI SEMIBOLD. Viene con Windows. */
    GetPrivateProfileStringA("estilos_texto", "fuentes", "Segoe UI:600", lista, sizeof(lista), ini);
    g_el_tamano = (int)GetPrivateProfileIntA("estilos_texto", "tamano", 100, ini);
    if (g_el_tamano < 50 || g_el_tamano > 200) g_el_tamano = 100;
    while (*p && g_el_nf < EL_FUENTES) {
        char *fin = p;
        while (*fin && *fin != '|') fin++;
        char guardo = *fin;
        *fin = 0;
        char *dos = p;
        while (*dos && *dos != ':') dos++;
        int peso = 700;
        if (*dos == ':') { *dos = 0; peso = 0; for (char *q = dos + 1; *q >= '0' && *q <= '9'; q++) peso = peso * 10 + (*q - '0'); }
        while (*p == ' ') p++;
        if (*p) {
            lstrcpynA(g_el_fuente[g_el_nf], p, 64);
            g_el_peso[g_el_nf++] = peso ? peso : 700;
        }
        if (!guardo) break;
        p = fin + 1;
    }
    if (!g_el_nf) { lstrcpyA(g_el_fuente[0], "Segoe UI Black"); g_el_peso[0] = 900; g_el_nf = 1; }
    if (g_el_estado >= 0)
        apuntar("  [estilos_texto] ★ letra propia: «%s» (peso %d), tamaño %d %%, %d fuente(s) con Ctrl+F8",
                g_el_fuente[0], g_el_peso[0], g_el_tamano, g_el_nf);
    static const DWORD va[5] = { 0x639BD4, 0x639B8E, 0x635DF2, 0x635E22, 0x635E52 };
    static const DWORD dst[5] = { 0x6364B0, 0x6355D0, 0x635A30, 0x635A30, 0x635A30 };
    void *nuestra[5] = { (void *)est_borde, (void *)est_sin, (void *)est_fuente, (void *)est_fuente,
                         (void *)est_fuente };
    if (!bru_mirar(va, dst, 5, "estilos_texto")) return;      /* las 5 son las de fábrica, o no se toca nada */
    int ok = 0;
    for (int i = 0; i < 5; i++) ok += bru_desviar(va[i], dst[i], nuestra[i], "estilos_texto: el dibujo del texto");
    apuntar("  [estilos_texto] ★ %d estilos de letra (contorno grueso, arcoíris y fuego animados): %d de 5 dibujos",
            EST_N, ok);
}
