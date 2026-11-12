/* tienda.c — el BUSCADOR y el CARRITO de la tienda (28-oct-2026)
 *
 *   anonimo03: *«un buscador de prendas en la tienda, abajo a la izquierda: si escribo letras, va filtrando la pestaña en la
 *   que estoy · a la derecha el carrito, que se vayan acumulando, con flechas si son muchos, y "comprar todo" al final»*,
 *   y después *«las ropas del carrito con una "x" arriba a la derecha»* y *«al dar "comprar todo", un cartel de
 *   confirmación con el cobro, y que las prendas pasen al inventario en vivo»*. Doc: documentacion/TIENDA_BUSCADOR.md.
 *
 *   Todo MEDIDO con Frida sobre la tienda abierta (§1 del doc). Lo que el exe ya tiene y se usa tal cual:
 *
 *     LA LISTA      cada pestaña es un objeto con un vector de fichas en [lista+0xC .. +0x10]; ficha: +0x00 la ruta del
 *                   ícono (std::string, «rnr_item/<id>.tga»), +0x38 el NOMBRE (std::string), +0x60 el id, +0x64 a la
 *                   venta. La página la arma 0x4D5AF0 (o 0x4D6320 si [tienda+0x3396] = 0) (lista, inicio, forzar): guarda
 *                   la lista en [tienda+0x3204] y de ahí salen el número de páginas y los botones 1..5.
 *                   ⇒ EL BUSCADOR le pasa una lista FILTRADA (sólo las fichas cuyo nombre tiene lo escrito) y el juego
 *                     arma solo las tarjetas y las páginas. No se dibuja nada dentro de la grilla.
 *     EL CARRITO    el de «Mis preferidos»: un vector de ids en [[0x9314E0]+0x12C .. +0x130] (el cliente pone el tope de
 *                   24). Sacar uno = SendRemoveWishList (0x5D19C0, FF70) — el mismo de la pestaña «Mis Selecciones».
 *     EL PRECIO     el de la tarjeta: 0x512310 toma el PRIMER plazo con precio de la ficha (+0x74, o +0x98 si [+0x67]);
 *                   el casillero k del plazo pasa al dígito de compra con la tabla de 0x4DDC14 (4,7,1,2,3,8,9,6,5), que
 *                   va en las MILÉSIMAS del id (10220994 permanente = 10229994).
 *     LA COMPRA     SendBuyDress (0x5C84F0, FF2A) de cada prenda, como el botón «Comprar» de la ventana nativa: el server
 *                   cobra y contesta su FF2A de siempre ⇒ el JUEGO mete la prenda al inventario y baja el saldo él solo,
 *                   en vivo. El server además la saca del carrito (FF71 con la lista nueva, sin cartel).
 *     EL SALDO      el Rcoin: [[0x9314E0]+0x2D8] ^ 0x1FEF (lo escribe el FFAB, 0x5D6D40). ⚠ +0x2DC es el CASH (0x485320).
 *
 *   EL DIBUJO     la receta de top5.c: una hoja con las piezas (rnr_ui_tienda.pak, herramientas/tienda_buscador.py) y
 *                 dos lienzos que se reescriben en memoria SÓLO cuando algo cambia (la franja y el cartel), con los
 *                 íconos de las prendas copiados de su textura y los textos con GDI. Se cuelga del «cada cuadro» de la
 *                 tienda (0x4D3F90, sus dos colas `jmp 0x4D1AA0`). La franja se ancla al CENTRO de la pantalla como la
 *                 tienda ([0x904084]/[0x904088]). z 0.9 la franja y 0.3 el cartel: las dos que usa la escena (medido).
 *   EL MOUSE Y EL TECLADO  el WndProc de d3d9_proxy.c nos pasa los mensajes ANTES que al juego (tienda_mensaje).
 *
 *   ⛔ [tienda] activo=0 lo apaga entero. Perillas: z, z_cartel (milésimas).
 */
#include "tienda_datos.h"

#define TNV(x) (g_tn_base + ((DWORD)(x) - 0x400000))
#define TN_ICONOS 32
#define TN_TEXTO_MAX 32

static BYTE *g_tn_base = NULL;
static int   g_tn_activo = 0;
static int   g_tn_raton = 1;                        /* [tienda] raton=0: no toma mensajes (diagnóstico) */
static float g_tn_z = 0.9f, g_tn_z_cartel = 0.3f;

/* ── la tienda (la del último cuadro) ── */
static BYTE *g_tn_tienda = NULL;
static volatile DWORD g_tn_visto = 0;
/* ★ ¿la tienda tiene el mouse? (28-oct, anonimo03: «el OK de Ajustes no hace nada… ¿el buscador cubre más espacio, como un
 *   elemento invisible?»). SÍ: con otra ventana del juego ENCIMA (Opción, un cartel), la tienda se sigue DIBUJANDO
 *   (60/s) pero su lector de botones 0x4D3FE0 NO corre (medido: 0/s con Opción abierta, 60/s cerrada) — y nuestra franja
 *   se quedaba con los clics de su rectángulo: el OK de Opción cae justo sobre «Comprar todo». ⇒ se engancha la entrada
 *   de 0x4D3FE0 y la franja sólo toma el mouse y el teclado si corrió hace menos de 200 ms. */
static volatile DWORD g_tn_entrada = 0;
static void __stdcall tn_marca_entrada(void) { g_tn_entrada = GetTickCount(); }
static int tn_tiene_entrada(void) { return GetTickCount() - g_tn_entrada < 200; }

/* ★ el mouse en píxeles del JUEGO (28-oct, anonimo03: «en 800 funciona, cambié a 1024 y los clics sobre la grilla o Ajustes
 *   no funcionan»). Cambiar la resolución DESDE el juego no pasa por nuestro Reset (el log no dice «Reset OK»): g_ancho /
 *   g_alto quedaban en 800×600, el clic se achicaba y «Ajustes» (838,738) caía en (654,576), DENTRO de la franja: nos lo
 *   quedábamos. ⇒ El tamaño es el del juego: el doble de su centro de pantalla ([0x904084]/[0x904088]), el mismo con el
 *   que se ubica la franja. */
static int tn_escalar(HWND h, POINT p, int *x, int *y)
{
    RECT r;
    int w = 2 * *(int *)TNV(0x904084), al = 2 * *(int *)TNV(0x904088);
    if (!GetClientRect(h, &r) || r.right <= 0 || r.bottom <= 0 || w <= 0 || al <= 0) return 0;
    *x = (int)((LONGLONG)p.x * w / r.right);
    *y = (int)((LONGLONG)p.y * al / r.bottom);
    return 1;
}

static int tn_a_juego(HWND h, LPARAM lp, int de_pantalla, int *x, int *y)
{
    POINT p;
    p.x = (short)LOWORD(lp);
    p.y = (short)HIWORD(lp);
    if (de_pantalla && !ScreenToClient(h, &p)) return 0;      /* la ruedita viene en coordenadas de PANTALLA */
    return tn_escalar(h, p, x, y);
}

static int tn_raton(int *x, int *y)
{
    POINT p;
    if (!g_ventana || !GetCursorPos(&p) || !ScreenToClient(g_ventana, &p)) return 0;
    return tn_escalar(g_ventana, p, x, y);
}
static int   g_tn_x0 = -9999, g_tn_y0 = -9999;      /* la franja en pantalla */
static int   g_tn_cx0 = -9999, g_tn_cy0 = -9999;    /* el cartel en pantalla */

/* ── el buscador ── */
static char  g_tn_texto[TN_TEXTO_MAX + 1] = "";
static int   g_tn_foco = 0;
static volatile int g_tn_refrescar = 0;
static void *g_tn_original = NULL;                  /* la lista de la pestaña, tal cual la pasó el juego */
typedef struct { DWORD a, b, c; void **ini, **fin, **cap; DWORD resto[8]; } TN_LISTA;
static TN_LISTA g_tn_filtrada;
static void **g_tn_fichas = NULL;
static int   g_tn_fichas_cap = 0, g_tn_hallados = 0;

/* ── el carrito ── */
static DWORD g_tn_carro[64];
static int   g_tn_n = 0, g_tn_scroll = 0;
static int   g_tn_apretado = -1;                    /* el control apretado (TNC_…) */
/* el cartel: 0 cerrado · 1 confirmar la compra · 2 no alcanza · 3 nada es para tu personaje · 4 el regalo */
enum { TNK_NADA, TNK_COMPRAR, TNK_NO_ALCANZA, TNK_NINGUNA, TNK_REGALO };
static int   g_tn_cartel = TNK_NADA;
static int   g_tn_capretado = -1;
static int   g_tn_total = 0, g_tn_saldo = 0;
static int   g_tn_van = 0, g_tn_omitidas = 0;        /* las que se compran / regalan y las que no (de otro sexo) */
static int   g_tn_sexo_lista = 0;                   /* el regalo: 0 = la lista de chico · 1 = la de chica */
static char  g_tn_para[24] = "";                    /* el regalo: el apodo del que lo recibe */
static int   g_tn_foco_para = 0;
enum { TNC_CAMPO, TNC_BORRAR, TNC_IZQ, TNC_DER, TNC_BOTON, TNC_REGALO, TNC_EQUIS0 = 16,
       TNC_SI = 64, TNC_NO, TNC_PARA, TNC_CHICA, TNC_CHICO };

/* ── las imágenes ── */
static BYTE   g_tn_hoja[0x100], g_tn_lz[0x100], g_tn_cz[0x100];
static int    g_tn_img = 0;                         /* 0 sin cargar · 1 lista · -1 no se usa */
static DWORD *g_tn_atlas = NULL;
static int    g_tn_aw = 0, g_tn_ah = 0;
static DWORD  g_tn_px[TN_W * TN_H];
static DWORD  g_tn_cpx[TN_CARTEL_W * TN_CARTEL_H];
static DWORD  g_tn_firma = 0, g_tn_cfirma = 0;
static void  *g_tn_lz_tex = NULL, *g_tn_cz_tex = NULL;
typedef struct { DWORD id; int estado; BYTE img[0x100]; DWORD px[TN_ICONO * TN_ICONO]; } TN_ICONO_C;
static TN_ICONO_C g_tn_ic[TN_ICONOS];
static int g_tn_ic_n = 0;

/* ── GDI ── */
#define TN_GDI_W 512
#define TN_GDI_H 32
static HDC    g_tn_dc = NULL;
static DWORD *g_tn_gdi = NULL;
static HFONT  g_tn_letra = NULL, g_tn_letra_g = NULL;

typedef void  (TCK *F_TN_LLENAR)(void *tienda, void *lista, DWORD inicio, DWORD forzar);   /* 0x4D5AF0, ret 0xC */
typedef BYTE *(TCK *F_TN_FICHA)(void *catalogo, DWORD id);                                 /* 0x510660, ret 4 */
typedef void  (TCK *F_TN_COMPRAR)(void *red, DWORD a, DWORD raw, DWORD b, DWORD c);         /* 0x5C84F0, ret 0x10 */
typedef void  (TCK *F_TN_SACAR)(void *red, DWORD id);                                      /* 0x5D19C0, ret 4 */
typedef void  (TCK *F_TN_REGALAR)(void *red, const char *apodo, int largo, DWORD raw);      /* 0x5CAB20, ret 0xC */
typedef void *(TCK *F_TN_CREAR)(void *self);
typedef int   (TCK *F_TN_CARGAR)(void *self, const char *ruta, const char *prefijo);
typedef void  (TCK *F_TN_RECORTE)(void *self, float x, float y, int u, int v, int w, int h, float z);

/* ═══ 1 · LO QUE SE LEE DEL JUEGO ═══════════════════════════════════════════════════════════════════════════════ */
static const char *tn_cadena(BYTE *s)               /* un std::string de MSVC (SSO de 16) */
{
    return *(DWORD *)(s + 0x18) >= 16 ? *(const char **)(s + 4) : (const char *)(s + 4);
}

static BYTE *tn_ficha(DWORD id)
{
    void *cat = *(void **)TNV(0x931618);
    return cat ? ((F_TN_FICHA)TNV(0x510660))(cat, id) : NULL;
}

/* el precio de la tarjeta (0x512310) y el id con el plazo, listo para el FF2A. 0 = no tiene precio */
static int tn_precio(DWORD id, DWORD *raw)
{
    static const int DIGITO[9] = { 4, 7, 1, 2, 3, 8, 9, 6, 5 };    /* la tabla de 0x4DDC14 */
    BYTE *f = tn_ficha(id);
    if (!f) return 0;
    const DWORD *p = (const DWORD *)(f + (f[0x67] ? 0x98 : 0x74));
    int k = 0;
    while (k < 9 && !p[k]) k++;
    if (k == 9 && f[0x67]) { p = (const DWORD *)(f + 0x74); k = 0; while (k < 9 && !p[k]) k++; }
    if (k == 9) return 0;
    if (raw) *raw = id - ((id / 1000) % 10) * 1000 + (DWORD)DIGITO[k] * 1000;
    return (int)p[k];
}

static int tn_leer_carro(void)
{
    BYTE *cta = *(BYTE **)TNV(0x9314E0);
    g_tn_n = 0;
    if (!cta) return 0;
    DWORD *b = *(DWORD **)(cta + 0x12C), *e = *(DWORD **)(cta + 0x130);
    if (!b || e < b) return 0;
    for (DWORD *p = b; p < e && g_tn_n < 64; p++) g_tn_carro[g_tn_n++] = *p;
    return g_tn_n;
}

/* ★ el SEXO (anonimo03, 28-oct: «el carrito deja añadir ropa F y M: el cartel debe avisar que no se pueden comprar x piezas
 *   y omitirlas»). El del personaje: [[0x9314E0]+0x80] (0 chico · 1 chica) — lo que copia la tienda al abrirse para
 *   elegir su botón ♂/♀ (0x4D919E). El de la prenda: la regla de servidor/shop_catalog.sexo_de, por el dígito de las
 *   decenas de mil del id base (en la ropa coincide 100 % con la tienda 03xx/04xx): 1/4 chico · 2/5 chica · lo demás
 *   (0, 3: consumibles, alas, anillos…) es de los dos. */
static int tn_sexo_jugador(void)
{
    BYTE *cta = *(BYTE **)TNV(0x9314E0);
    return cta ? (cta[0x80] & 1) : 0;
}

static int tn_sexo_prenda(DWORD id)                  /* 0 chico · 1 chica · -1 los dos */
{
    int d = (int)((id % 1000000) / 10000 % 10);
    return d == 1 || d == 4 ? 0 : d == 2 || d == 5 ? 1 : -1;
}

static int tn_va(DWORD id, int sexo) { int s = tn_sexo_prenda(id); return s < 0 || s == sexo; }

static int tn_leer_saldo(void)
{
    BYTE *cta = *(BYTE **)TNV(0x9314E0);
    return cta ? (int)(*(DWORD *)(cta + 0x2D8) ^ 0x1FEF) : 0;   /* el RCOIN (lo escribe el FFAB, 0x5D6D40); +0x2DC es el Cash */
}

/* ═══ 2 · EL BUSCADOR: la lista filtrada ═════════════════════════════════════════════════════════════════════════
 *   Se compara sin mayúsculas ni tildes, en 1252 o en UTF-8 (las dos pueden venir del catálogo). */
static int tn_plano(unsigned char c)
{
    static const char *LAT = "aaaaaaaceeeeiiiidnooooooouuuuyty";        /* 0xE0..0xFF */
    if (c >= 'A' && c <= 'Z') return c + 32;
    if (c >= 0xC0 && c <= 0xDE && c != 0xD7) c = (unsigned char)(c + 32);
    if (c >= 0xE0) return c == 0xF7 ? c : LAT[c - 0xE0];
    return c;
}

static int tn_normal(const char *s, char *d, int cap)
{
    int n = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p && n < cap - 1; p++) {
        unsigned char c = *p;
        if ((c == 0xC2 || c == 0xC3) && (p[1] & 0xC0) == 0x80) {     /* UTF-8 de 2 bytes -> latin-1 */
            c = (unsigned char)(((c & 0x1F) << 6) | (p[1] & 0x3F));
            p++;
        }
        d[n++] = (char)tn_plano(c);
    }
    d[n] = 0;
    return n;
}

static int tn_coincide(const char *nombre, const char *buscado)
{
    char a[256];
    tn_normal(nombre, a, sizeof(a));
    return strstr(a, buscado) != NULL;
}

static void *tn_filtrar(void *lista)
{
    char b[TN_TEXTO_MAX * 2 + 2];
    tn_normal(g_tn_texto, b, sizeof(b));
    void **ini = *(void ***)((BYTE *)lista + 0xC), **fin = *(void ***)((BYTE *)lista + 0x10);
    int n = (ini && fin > ini) ? (int)(fin - ini) : 0;
    if (n > g_tn_fichas_cap) {
        void **nuevo = (void **)HeapAlloc(GetProcessHeap(), 0, (n + 64) * sizeof(void *));
        if (!nuevo) return lista;
        if (g_tn_fichas) HeapFree(GetProcessHeap(), 0, g_tn_fichas);
        g_tn_fichas = nuevo;
        g_tn_fichas_cap = n + 64;
    }
    int k = 0;
    for (int i = 0; i < n; i++) {
        BYTE *f = (BYTE *)ini[i];
        if (f && f[0x64] && tn_coincide(tn_cadena(f + 0x38), b)) g_tn_fichas[k++] = f;
    }
    ZeroMemory(&g_tn_filtrada, sizeof(g_tn_filtrada));
    g_tn_filtrada.ini = g_tn_fichas;
    g_tn_filtrada.fin = g_tn_fichas + k;
    g_tn_filtrada.cap = g_tn_fichas + k;
    g_tn_hallados = k;
    return &g_tn_filtrada;
}

/* la llama el salto de 0x4D5AF0 / 0x4D6320, con sus argumentos: devuelve la lista que se usa de verdad */
static void *__stdcall tn_lista(BYTE *tienda, void *lista, DWORD inicio, DWORD forzar)
{
    (void)inicio; (void)forzar;
    g_tn_tienda = tienda;
    if (!lista || lista == &g_tn_filtrada) return lista;          /* pasar de página dentro de lo buscado */
    g_tn_original = lista;                                        /* otra pestaña (o la misma de nuevo) */
    if (!g_tn_texto[0]) return lista;
    return tn_filtrar(lista);
}

static void tn_aplicar_busqueda(BYTE *tienda)
{
    g_tn_refrescar = 0;
    if (!g_tn_original) return;
    *(int *)(tienda + 0x338C) = 0;                                 /* a la página 1 */
    F_TN_LLENAR llenar = (F_TN_LLENAR)TNV(tienda[0x3396] ? 0x4D5AF0 : 0x4D6320);
    llenar(tienda, g_tn_original, 0, 1);                          /* pasa por tn_lista: ahí se filtra */
    apuntar("  [tienda] buscar «%s»: %d de la pestaña", g_tn_texto, g_tn_texto[0] ? g_tn_hallados : -1);
}

/* ═══ 3 · LAS IMÁGENES ═══════════════════════════════════════════════════════════════════════════════════════════ */
typedef BYTE *(TCK *F_TN_TEX_ENTRADA)(void *mgr, DWORD h);
typedef void *(TCK *F_TN_TEX_D3D)(void *mgr, DWORD h, int cual);

static void *tn_textura(BYTE *img)
{
    void *mgr = *(void **)TNV(0x931570);
    DWORD h = *(DWORD *)(img + 4);
    if (!mgr || !h) return NULL;
    BYTE *ent = ((F_TN_TEX_ENTRADA)TNV(0x4099E0))(mgr, h);
    if (!ent || *(DWORD *)(ent + 0x48)) return NULL;
    return ((F_TN_TEX_D3D)TNV(0x441420))(mgr, h, 0);
}

static int tn_desc(void *tex, T5_DESC *d)
{
    void **vt = tex ? *(void ***)tex : NULL;
    return vt && ((T5_T_DESC)vt[17])(tex, 0, d) == 0;
}

/* copia una textura A8R8G8B8 / X8R8G8B8 a memoria (la hoja, los íconos). -> los px (HeapAlloc) o NULL */
static DWORD *tn_leer_textura(void *tex, int *w, int *h)
{
    T5_DESC d;
    if (!tn_desc(tex, &d) || (d.Format != 21 && d.Format != 22)) return NULL;
    void **vt = *(void ***)tex;
    T5_BLOQUEO b;
    if (((T5_T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, 0x10 /* READONLY */) != 0) return NULL;
    DWORD *px = (DWORD *)HeapAlloc(GetProcessHeap(), 0, d.Width * d.Height * 4);
    if (px)
        for (UINT y = 0; y < d.Height; y++) {
            DWORD *o = (DWORD *)((BYTE *)b.pBits + y * b.Pitch);
            for (UINT x = 0; x < d.Width; x++) px[y * d.Width + x] = d.Format == 22 ? (o[x] | 0xFF000000) : o[x];
        }
    ((T5_T_SOLTAR)vt[20])(tex, 0);
    *w = (int)d.Width;
    *h = (int)d.Height;
    return px;
}

static int tn_gdi_preparar(void)
{
    g_tn_dc = CreateCompatibleDC(NULL);
    if (!g_tn_dc) return 0;
    BITMAPINFO bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = TN_GDI_W;
    bi.bmiHeader.biHeight = -TN_GDI_H;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(g_tn_dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (!bmp || !bits) return 0;
    SelectObject(g_tn_dc, bmp);
    g_tn_gdi = (DWORD *)bits;
    g_tn_letra = CreateFontW(-12, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                             ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Segoe UI");
    g_tn_letra_g = CreateFontW(-14, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                               ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Segoe UI");
    SetBkMode(g_tn_dc, TRANSPARENT);
    SetTextColor(g_tn_dc, RGB(255, 255, 255));
    return g_tn_letra && g_tn_letra_g;
}

static int tn_imagen(BYTE *img, const char *tga, int w, int h, float z)
{
    ((F_TN_CREAR)TNV(0x64E560))(img);
    if (!((F_TN_CARGAR)TNV(0x64E1E0))(img, tga, NULL)) return 0;
    ((F_TN_RECORTE)TNV(0x64EC40))(img, 0, 0, 0, 0, w, h, z);
    return 1;
}

static void tn_cargar(void)
{
    g_tn_img = -1;
    if (!tn_imagen(g_tn_hoja, TN_HOJA_TGA, 1024, 256, g_tn_z)) {
        apuntar("  [tienda] ⛔ no encontré %s (¿falta rnr_ui_tienda.pak?): sin buscador", TN_HOJA_TGA);
        return;
    }
    void *tex = tn_textura(g_tn_hoja);
    g_tn_atlas = tex ? tn_leer_textura(tex, &g_tn_aw, &g_tn_ah) : NULL;
    if (!g_tn_atlas || g_tn_aw < 1024 || g_tn_ah < 256) { apuntar("  [tienda] ⛔ no pude leer la hoja: sin buscador"); return; }
    if (!tn_imagen(g_tn_lz, TN_LIENZO_TGA, TN_W, TN_H, g_tn_z) ||
        !tn_imagen(g_tn_cz, TN_CARTEL_TGA, TN_CARTEL_W, TN_CARTEL_H, g_tn_z_cartel)) {
        apuntar("  [tienda] ⛔ faltan los lienzos: sin buscador");
        return;
    }
    T5_DESC d;
    tex = tn_textura(g_tn_lz);
    if (!tex || !tn_desc(tex, &d) || d.Format != 21 || d.Width < TN_W || d.Height < TN_H) {
        apuntar("  [tienda] ⛔ el lienzo no es el esperado: sin buscador");
        return;
    }
    if (!tn_gdi_preparar()) { apuntar("  [tienda] ⛔ GDI: sin buscador"); return; }
    g_tn_img = 1;
    apuntar("  [tienda] ★ listo: hoja %dx%d, lienzos, letra Segoe UI", g_tn_aw, g_tn_ah);
}

/* el ícono de una prenda (su «rnr_item/<id>.tga», el de la tarjeta), achicado a TN_ICONO y guardado */
static const DWORD *tn_icono(DWORD id)
{
    for (int i = 0; i < g_tn_ic_n; i++)
        if (g_tn_ic[i].id == id) return g_tn_ic[i].estado == 1 ? g_tn_ic[i].px : NULL;
    TN_ICONO_C *c = &g_tn_ic[g_tn_ic_n < TN_ICONOS ? g_tn_ic_n++ : (int)(id % TN_ICONOS)];
    c->id = id;
    c->estado = -1;
    BYTE *f = tn_ficha(id);
    char ruta[160];
    if (f) lstrcpynA(ruta, tn_cadena(f), sizeof(ruta));
    if (!f || memcmp(ruta, "rnr_", 4) != 0) wsprintfA(ruta, "rnr_item/%lu.tga", (unsigned long)id);
    ((F_TN_CREAR)TNV(0x64E560))(c->img);
    if (!((F_TN_CARGAR)TNV(0x64E1E0))(c->img, ruta, NULL)) return NULL;
    void *tex = tn_textura(c->img);
    int w = 0, h = 0;
    DWORD *s = tex ? tn_leer_textura(tex, &w, &h) : NULL;
    if (!s) { apuntar("  [tienda] el ícono de %lu (%s) no se deja leer", (unsigned long)id, ruta); return NULL; }
    for (int y = 0; y < TN_ICONO; y++)                                /* promedio de cada bloque, con el alfa */
        for (int x = 0; x < TN_ICONO; x++) {
            int x0 = x * w / TN_ICONO, x1 = (x + 1) * w / TN_ICONO, y0 = y * h / TN_ICONO, y1 = (y + 1) * h / TN_ICONO;
            DWORD sa = 0, sr = 0, sg = 0, sb = 0, k = 0;
            for (int v = y0; v < (y1 > y0 ? y1 : y0 + 1); v++)
                for (int u = x0; u < (x1 > x0 ? x1 : x0 + 1); u++) {
                    DWORD p = s[v * w + u], a = p >> 24;
                    sa += a; sr += ((p >> 16) & 255) * a; sg += ((p >> 8) & 255) * a; sb += (p & 255) * a; k++;
                }
            c->px[y * TN_ICONO + x] = sa ? ((sa / k) << 24) | ((sr / sa) << 16) | ((sg / sa) << 8) | (sb / sa) : 0;
        }
    HeapFree(GetProcessHeap(), 0, s);
    c->estado = 1;
    return c->px;
}

/* ═══ 4 · ARMAR EN MEMORIA ═══════════════════════════════════════════════════════════════════════════════════════ */
typedef struct { DWORD *px; int w, h; } TN_LIENZO;

static void tn_pegar(TN_LIENZO *L, int sx, int sy, int w, int h, int dx, int dy)       /* de la hoja */
{
    for (int j = 0; j < h; j++) {
        int yy = dy + j, ys = sy + j;
        if (yy < 0 || yy >= L->h || ys < 0 || ys >= g_tn_ah) continue;
        for (int i = 0; i < w; i++) {
            int xx = dx + i, xs = sx + i;
            if (xx < 0 || xx >= L->w || xs < 0 || xs >= g_tn_aw) continue;
            DWORD s = g_tn_atlas[ys * g_tn_aw + xs];
            t5_mezclar(&L->px[yy * L->w + xx], s | 0xFF000000, (int)(s >> 24));
        }
    }
}

static void tn_pegar_px(TN_LIENZO *L, const DWORD *s, int w, int h, int dx, int dy)
{
    for (int j = 0; j < h; j++)
        for (int i = 0; i < w; i++) {
            int xx = dx + i, yy = dy + j;
            if (xx < 0 || yy < 0 || xx >= L->w || yy >= L->h) continue;
            DWORD p = s[j * w + i];
            t5_mezclar(&L->px[yy * L->w + xx], p | 0xFF000000, (int)(p >> 24));
        }
}

/* un texto (cp1252/UTF-8: id_a_ancho) sin borde. alin 0 = desde x · 1 = centrado · 2 = termina en x. -> el ancho */
static int tn_texto(TN_LIENZO *L, int x, int cy, int alin, HFONT letra, const char *s, int ancho_max, DWORD color)
{
    WCHAR w[96];
    int n = id_a_ancho(s, w, 94);
    if (n <= 1) return 0;
    n--;
    SelectObject(g_tn_dc, letra);
    SIZE t;
    GetTextExtentPoint32W(g_tn_dc, w, n, &t);
    while (ancho_max > 0 && t.cx > ancho_max && n > 1) {       /* lo escrito más largo que el campo: se ve el FINAL */
        MoveMemory(w, w + 1, (n - 1) * sizeof(WCHAR));
        n--;
        GetTextExtentPoint32W(g_tn_dc, w, n, &t);
    }
    ZeroMemory(g_tn_gdi, TN_GDI_W * TN_GDI_H * 4);
    TextOutW(g_tn_dc, 2, 2, w, n);
    GdiFlush();
    int x0 = alin == 0 ? x : alin == 1 ? x - t.cx / 2 : x - t.cx, y0 = cy - t.cy / 2;
    int ancho = t.cx + 4 > TN_GDI_W ? TN_GDI_W : t.cx + 4, alto = t.cy + 4 > TN_GDI_H ? TN_GDI_H : t.cy + 4;
    int ca = (int)(color >> 24);
    for (int j = 0; j < alto; j++) {
        int yy = y0 - 2 + j;
        if (yy < 0 || yy >= L->h) continue;
        for (int i = 0; i < ancho; i++) {
            int xx = x0 - 2 + i;
            if (xx < 0 || xx >= L->w) continue;
            int cob = (int)((g_tn_gdi[j * TN_GDI_W + i] >> 8) & 255);
            t5_mezclar(&L->px[yy * L->w + xx], color, cob * ca / 255);
        }
    }
    return t.cx;
}

static int tn_ancho(HFONT letra, const char *s)
{
    WCHAR w[96];
    int n = id_a_ancho(s, w, 94);
    if (n <= 1) return 0;
    SelectObject(g_tn_dc, letra);
    SIZE t;
    GetTextExtentPoint32W(g_tn_dc, w, n - 1, &t);
    return t.cx;
}

static void tn_miles(int v, char *s)                 /* 11600 -> «11.600» */
{
    char t[16];
    int n = wsprintfA(t, "%d", v < 0 ? -v : v), k = 0;
    if (v < 0) s[k++] = '-';
    for (int i = 0; i < n; i++) {
        s[k++] = t[i];
        if ((n - 1 - i) % 3 == 0 && i < n - 1) s[k++] = '.';
    }
    s[k] = 0;
}

#define TN_OSCURO 0xFF5A3214
#define TN_ROJO   0xFFC82846
#define TN_GRIS   0xFFA08C78
#define TN_VERDE  0xFF2E7D32

static int tn_dentro(int x, int y, int x0, int y0, int w, int h) { return x >= x0 && x < x0 + w && y >= y0 && y < y0 + h; }

/* qué control hay en (x, y) de la franja; -1 nada */
static int tn_control(int x, int y)
{
    if (tn_dentro(x, y, TN_BORRAR_X, TN_BORRAR_Y, TN_BORRAR_TAM, TN_BORRAR_TAM) && g_tn_texto[0]) return TNC_BORRAR;
    if (tn_dentro(x, y, TN_BUSCADOR_X, TN_BUSCADOR_Y, TN_BUSCADOR_W, TN_BUSCADOR_H)) return TNC_CAMPO;
    if (tn_dentro(x, y, TN_FLECHA_IZQ_X - 4, 0, TN_FLECHA_W + 6, TN_H)) return TNC_IZQ;
    if (tn_dentro(x, y, TN_FLECHA_DER_X - 2, 0, TN_FLECHA_W + 6, TN_H)) return TNC_DER;
    if (tn_dentro(x, y, TN_BOTON_X, TN_BOTON_Y, TN_BOTON_W, TN_BOTON_H)) return TNC_BOTON;
    if (tn_dentro(x, y, TN_REGALO_X, TN_BOTON_Y, TN_BOTON_W, TN_BOTON_H)) return TNC_REGALO;
    for (int i = 0; i < TN_CASILLAS && g_tn_scroll + i < g_tn_n; i++) {
        int cx = TN_CASILLA_X0 + i * TN_PASO;
        if (tn_dentro(x, y, cx + TN_EQUIS_DX - 2, TN_CASILLA_Y + TN_EQUIS_DY - 2, TN_EQUIS + 4, TN_EQUIS + 4))
            return TNC_EQUIS0 + i;
    }
    return -1;
}

static int tn_en_franja(int x, int y)
{
    return tn_dentro(x, y, TN_BUSCADOR_X, TN_BUSCADOR_Y, TN_BUSCADOR_W, TN_BUSCADOR_H)
        || tn_dentro(x, y, TN_TIRA_X, 0, TN_TIRA_W, TN_H);
}

static int tn_tope_scroll(void) { return g_tn_n > TN_CASILLAS ? g_tn_n - TN_CASILLAS : 0; }

static void tn_armar(int sobre, int cursor)
{
    TN_LIENZO L = { g_tn_px, TN_W, TN_H };
    ZeroMemory(g_tn_px, sizeof(g_tn_px));
    tn_pegar(&L, TN_H_FONDO_X, TN_H_FONDO_Y, TN_W, TN_H, 0, 0);
    /* el buscador */
    int cy = TN_CAMPO_Y + TN_CAMPO_H / 2;
    if (g_tn_texto[0] || g_tn_foco) {
        int w = tn_texto(&L, TN_CAMPO_X + 6, cy, 0, g_tn_letra, g_tn_texto, TN_CAMPO_W - 16, 0xFF3C2814);
        if (g_tn_foco && cursor)
            for (int y = cy - 7; y <= cy + 7; y++) L.px[y * TN_W + TN_CAMPO_X + 7 + w] = 0xFF3C2814;
    } else
        tn_texto(&L, TN_CAMPO_X + 6, cy, 0, g_tn_letra, "Buscar prenda\x85", 0, TN_GRIS);
    if (g_tn_texto[0]) {
        int e = g_tn_apretado == TNC_BORRAR ? 2 : sobre == TNC_BORRAR ? 1 : 0;
        tn_pegar(&L, TN_H_BORRAR[e][0], TN_H_BORRAR[e][1], TN_BORRAR_TAM, TN_BORRAR_TAM, TN_BORRAR_X, TN_BORRAR_Y);
    }
    /* el carrito */
    int fi = g_tn_scroll > 0 ? (g_tn_apretado == TNC_IZQ || sobre == TNC_IZQ ? 1 : 0) : 2;
    int fd = g_tn_scroll < tn_tope_scroll() ? (g_tn_apretado == TNC_DER || sobre == TNC_DER ? 1 : 0) : 2;
    tn_pegar(&L, TN_H_FLECHA_IZQ[fi][0], TN_H_FLECHA_IZQ[fi][1], TN_FLECHA_W, TN_FLECHA_H, TN_FLECHA_IZQ_X, TN_FLECHA_Y);
    tn_pegar(&L, TN_H_FLECHA_DER[fd][0], TN_H_FLECHA_DER[fd][1], TN_FLECHA_W, TN_FLECHA_H, TN_FLECHA_DER_X, TN_FLECHA_Y);
    for (int i = 0; i < TN_CASILLAS; i++) {
        int x = TN_CASILLA_X0 + i * TN_PASO, k = g_tn_scroll + i;
        tn_pegar(&L, TN_H_CASILLA[0][0], TN_H_CASILLA[0][1], TN_CASILLA, TN_CASILLA + 2, x, TN_CASILLA_Y);
        if (k >= g_tn_n) continue;
        const DWORD *ic = tn_icono(g_tn_carro[k]);
        if (ic) tn_pegar_px(&L, ic, TN_ICONO, TN_ICONO, x + 3, TN_CASILLA_Y + 4);
        else tn_texto(&L, x + TN_CASILLA / 2, TN_CASILLA_Y + TN_CASILLA / 2, 1, g_tn_letra_g, "?", 0, TN_GRIS);
        int e = g_tn_apretado == TNC_EQUIS0 + i ? 2 : sobre == TNC_EQUIS0 + i ? 1 : 0;
        tn_pegar(&L, TN_H_EQUIS[e][0], TN_H_EQUIS[e][1], TN_EQUIS, TN_EQUIS, x + TN_EQUIS_DX, TN_CASILLA_Y + TN_EQUIS_DY);
    }
    int b = !g_tn_n ? 3 : g_tn_apretado == TNC_BOTON ? 2 : sobre == TNC_BOTON ? 1 : 0;
    tn_pegar(&L, TN_H_BOTON[b][0], TN_H_BOTON[b][1], TN_BOTON_W, TN_BOTON_H, TN_BOTON_X, TN_BOTON_Y);
    int r = !g_tn_n ? 3 : g_tn_apretado == TNC_REGALO ? 2 : sobre == TNC_REGALO ? 1 : 0;
    tn_pegar(&L, TN_H_REGALO[r][0], TN_H_REGALO[r][1], TN_BOTON_W, TN_BOTON_H, TN_REGALO_X, TN_BOTON_Y);
    /* «Carrito (n)» / «Total» + la moneda / el monto, centrado entre la flecha y los botones */
    char t1[32], t3[24];
    wsprintfA(t1, "Carrito (%d)", g_tn_n);
    tn_miles(g_tn_total, t3);
    int wt = tn_ancho(g_tn_letra, "Total"), m = (TN_TEXTO_X0 + TN_TEXTO_X1) / 2;
    tn_texto(&L, m, 16, 1, g_tn_letra, t1, 0, TN_OSCURO);
    int xt = m - (wt + 3 + TN_MONEDA_TAM) / 2;
    tn_texto(&L, xt, 31, 0, g_tn_letra, "Total", 0, TN_OSCURO);
    tn_pegar(&L, TN_H_MONEDA_X, TN_H_MONEDA_Y, TN_MONEDA_TAM, TN_MONEDA_TAM, xt + wt + 3, 31 - TN_MONEDA_TAM / 2);
    tn_texto(&L, m, 46, 1, g_tn_letra, t3, 0, TN_ROJO);
}

static void tn_renglon(TN_LIENZO *L, int y, const char *rotulo, int valor, DWORD color)
{
    char t[24];
    tn_miles(valor, t);
    int x = TN_CARTEL_W / 2 + 8;
    tn_texto(L, x - 6, y, 2, g_tn_letra_g, rotulo, 0, TN_OSCURO);
    tn_pegar(L, TN_H_MONEDA_X, TN_H_MONEDA_Y, TN_MONEDA_TAM, TN_MONEDA_TAM, x, y - TN_MONEDA_TAM / 2);
    tn_texto(L, x + TN_MONEDA_TAM + 5, y, 0, g_tn_letra_g, t, 0, color);
}

/* el cartel tiene dos botones (Comprar/Enviar + Cancelar) o uno solo (Cerrar) */
static int tn_cartel_dos(void) { return g_tn_cartel == TNK_COMPRAR || g_tn_cartel == TNK_REGALO; }

static int tn_control_cartel(int lx, int ly)
{
    if (tn_cartel_dos()) {
        if (tn_dentro(lx, ly, TN_CBOTON_SI_X, TN_CBOTON_SI_Y, TN_CBOTON_W, TN_CBOTON_H)) return TNC_SI;
        if (tn_dentro(lx, ly, TN_CBOTON_NO_X, TN_CBOTON_NO_Y, TN_CBOTON_W, TN_CBOTON_H)) return TNC_NO;
    } else if (tn_dentro(lx, ly, TN_CBOTON_UNO_X, TN_CBOTON_UNO_Y, TN_CBOTON_W, TN_CBOTON_H)) return TNC_NO;
    if (g_tn_cartel == TNK_REGALO) {
        if (tn_dentro(lx, ly, TN_PARA_X, TN_PARA_Y, TN_PARA_W, TN_PARA_H)) return TNC_PARA;
        if (tn_dentro(lx, ly, TN_PASTILLAS[0][0], TN_PASTILLAS[0][1], TN_PASTILLA_W, TN_PASTILLA_H)) return TNC_CHICA;
        if (tn_dentro(lx, ly, TN_PASTILLAS[1][0], TN_PASTILLAS[1][1], TN_PASTILLA_W, TN_PASTILLA_H)) return TNC_CHICO;
    }
    return -1;
}

static int tn_contar_sexo(int sexo)                  /* cuántas del carrito van con esa lista */
{
    int k = 0;
    for (int i = 0; i < g_tn_n; i++) k += tn_va(g_tn_carro[i], sexo);
    return k;
}

static void tn_armar_cartel(int sobre, int cursor)
{
    TN_LIENZO L = { g_tn_cpx, TN_CARTEL_W, TN_CARTEL_H };
    ZeroMemory(g_tn_cpx, sizeof(g_tn_cpx));
    tn_pegar(&L, TN_H_CARTEL_X, TN_H_CARTEL_Y, TN_CARTEL_W, TN_CARTEL_H, 0, 0);
    int regalo = g_tn_cartel == TNK_REGALO;
    tn_texto(&L, TN_CARTEL_W / 2, 18, 1, g_tn_letra_g, regalo ? "Enviar regalo" : "Comprar todo", 0, 0xFFFFFFFF);
    char t[64];
    int y = 48;
    if (regalo) {
        tn_texto(&L, TN_PARA_X - 8, TN_PARA_Y + TN_PARA_H / 2, 2, g_tn_letra_g, "Para:", 0, TN_OSCURO);
        tn_pegar(&L, TN_H_CAMPO_X, TN_H_CAMPO_Y, TN_PARA_W, TN_PARA_H, TN_PARA_X, TN_PARA_Y);
        int cy = TN_PARA_Y + TN_PARA_H / 2;
        if (g_tn_para[0] || g_tn_foco_para) {
            int w = tn_texto(&L, TN_PARA_X + 6, cy, 0, g_tn_letra, g_tn_para, TN_PARA_W - 14, 0xFF3C2814);
            if (g_tn_foco_para && cursor)
                for (int yy = cy - 7; yy <= cy + 7; yy++) L.px[yy * TN_CARTEL_W + TN_PARA_X + 7 + w] = 0xFF3C2814;
        } else
            tn_texto(&L, TN_PARA_X + 6, cy, 0, g_tn_letra, "apodo del jugador", 0, TN_GRIS);
        /* las dos listas: Chica (n) · Chico (m) — la elegida resaltada, la que no tiene nada apagada */
        static const char *NOM[2] = { "Chica", "Chico" };
        for (int p = 0; p < 2; p++) {
            int sexo = p == 0 ? 1 : 0, n = tn_contar_sexo(sexo), elegida = g_tn_sexo_lista == sexo;
            int e = !n ? 2 : elegida ? 1 : 0;
            tn_pegar(&L, TN_H_PASTILLA[e][0], TN_H_PASTILLA[e][1], TN_PASTILLA_W, TN_PASTILLA_H, TN_PASTILLAS[p][0], TN_PASTILLAS[p][1]);
            wsprintfA(t, "%s (%d)", NOM[p], n);
            tn_texto(&L, TN_PASTILLAS[p][0] + TN_PASTILLA_W / 2, TN_PASTILLAS[p][1] + TN_PASTILLA_H / 2, 1, g_tn_letra, t, 0,
                     !n ? TN_GRIS : elegida ? 0xFFFFFFFF : TN_OSCURO);
        }
        y = 102;
    }
    wsprintfA(t, g_tn_van == 1 ? "1 prenda" : "%d prendas", g_tn_van);
    if (g_tn_cartel == TNK_NINGUNA) lstrcpyA(t, "Ninguna prenda es para tu personaje");
    tn_texto(&L, TN_CARTEL_W / 2, y, 1, g_tn_letra_g, t, 0, TN_OSCURO);
    y += 19;
    if (g_tn_cartel != TNK_NINGUNA) {
        tn_renglon(&L, y, "Total:", g_tn_total, TN_ROJO);
        y += 19;
        if (!regalo) { tn_renglon(&L, y, "Tu saldo:", g_tn_saldo, TN_OSCURO); y += 19; }
        if (g_tn_total > g_tn_saldo) { tn_renglon(&L, y, "Te faltan:", g_tn_total - g_tn_saldo, TN_ROJO); y += 19; }
        else if (!regalo) { tn_renglon(&L, y, "Te quedan:", g_tn_saldo - g_tn_total, TN_VERDE); y += 19; }
    }
    if (g_tn_omitidas && !(regalo && g_tn_total > g_tn_saldo)) {   /* las de otro sexo no van */
        int sexo_otro = regalo ? !g_tn_sexo_lista : !tn_sexo_jugador();
        /* ⛔ dos formatos con los MISMOS argumentos: con «1 prenda es de %s» el número caía en el %s y se leía la
         *   dirección 1 (se cayó el juego, 28-oct, cajanegra 0xC0000005 «lee 0x00000001») */
        if (g_tn_omitidas == 1) wsprintfA(t, "1 prenda es de %s: se omite", sexo_otro ? "chica" : "chico");
        else wsprintfA(t, "%d prendas son de %s: se omiten", g_tn_omitidas, sexo_otro ? "chica" : "chico");
        tn_texto(&L, TN_CARTEL_W / 2, y - 2, 1, g_tn_letra, t, 0, TN_ROJO);
    }
    if (tn_cartel_dos()) {
        int si = g_tn_capretado == TNC_SI ? 2 : sobre == TNC_SI ? 1 : 0, no = g_tn_capretado == TNC_NO ? 2 : sobre == TNC_NO ? 1 : 0;
        const int (*pz)[2] = regalo ? TN_H_CENV : TN_H_CSI;
        tn_pegar(&L, pz[si][0], pz[si][1], TN_CBOTON_W, TN_CBOTON_H, TN_CBOTON_SI_X, TN_CBOTON_SI_Y);
        tn_pegar(&L, TN_H_CNO[no][0], TN_H_CNO[no][1], TN_CBOTON_W, TN_CBOTON_H, TN_CBOTON_NO_X, TN_CBOTON_NO_Y);
    } else {
        int no = g_tn_capretado == TNC_NO ? 2 : sobre == TNC_NO ? 1 : 0;
        tn_pegar(&L, TN_H_CUNO[no][0], TN_H_CUNO[no][1], TN_CBOTON_W, TN_CBOTON_H, TN_CBOTON_UNO_X, TN_CBOTON_UNO_Y);
    }
}

static void tn_figura(BYTE *img, int x, int y)       /* t5_figura, con NUESTRA base (top5 puede estar apagado) */
{
    ((F_T5_POS)TNV(0x64D990))(img, 0, x, y);
    ((F_T5_COLOR)TNV(0x64E710))(img, 0, 0xFFFFFFFF);
    ((F_T5_DIBUJAR)TNV(0x64EE40))(img, 0, 0);
}

static int tn_subir(void *tex, const DWORD *px, int w, int h)
{
    void **vt = *(void ***)tex;
    T5_BLOQUEO b;
    if (((T5_T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, 0) != 0) return 0;
    for (int y = 0; y < h; y++) CopyMemory((BYTE *)b.pBits + y * b.Pitch, px + y * w, w * 4);
    ((T5_T_SOLTAR)vt[20])(tex, 0);
    return 1;
}

/* ═══ 5 · LA COMPRA ══════════════════════════════════════════════════════════════════════════════════════════════ */
/* el total de lo que VA con esa lista (sexo -1 = todas: el de la tira), cuántas van y cuántas se omiten */
static void tn_calcular(int sexo)
{
    g_tn_total = g_tn_van = g_tn_omitidas = 0;
    for (int i = 0; i < g_tn_n; i++) {
        if (sexo >= 0 && !tn_va(g_tn_carro[i], sexo)) { g_tn_omitidas++; continue; }
        g_tn_total += tn_precio(g_tn_carro[i], NULL);
        g_tn_van++;
    }
    g_tn_saldo = tn_leer_saldo();
}

static int tn_sexo_cartel(void)
{
    return g_tn_cartel == TNK_REGALO ? g_tn_sexo_lista : g_tn_cartel ? tn_sexo_jugador() : -1;
}

/* ★ UN solo «Transacción Completada» (anonimo03, 28-oct): cada FF2A que vuelve bien abre el cartel del juego (0x5CE5DE:
 *   el texto 0x71 a 0x4233A0). Con «Comprar todo» se callan los primeros n−1 y queda el último. Los de error salen por
 *   otro lado (0x5CE6B7) y se ven siempre. Se vence a los 10 s: una compra a mano de después no se calla nunca. */
static volatile LONG g_tn_callar = 0;
static DWORD g_tn_callar_hasta = 0;

static int __stdcall tn_callar(void)
{
    if (g_tn_callar <= 0) return 0;
    if (GetTickCount() - g_tn_callar_hasta < 0x80000000u) { g_tn_callar = 0; return 0; }   /* ya se venció */
    g_tn_callar--;
    return 1;
}

static void tn_comprar_todo(void)
{
    void *red = *(void **)TNV(0x9314D0);
    if (!red) { apuntar("  [tienda] ⛔ sin la red: no compro"); return; }
    F_TN_COMPRAR comprar = (F_TN_COMPRAR)TNV(0x5C84F0);
    int hechas = 0, sexo = tn_sexo_jugador();
    for (int i = 0; i < g_tn_n; i++) {
        DWORD raw = 0;
        if (!tn_va(g_tn_carro[i], sexo)) continue;          /* de otro sexo: se omite (el cartel lo avisó) */
        int p = tn_precio(g_tn_carro[i], &raw);
        if (!p) { apuntar("  [tienda] %lu no tiene precio: no se compra", (unsigned long)g_tn_carro[i]); continue; }
        comprar(red, 0, raw, 0, 0);
        hechas++;
    }
    g_tn_callar = hechas > 1 ? hechas - 1 : 0;
    g_tn_callar_hasta = GetTickCount() + 10000;
    apuntar("  [tienda] ★ comprar todo: %d FF2A (total %d, saldo %d, %d omitidas)", hechas, g_tn_total, g_tn_saldo,
            g_tn_omitidas);
}

/* ★ ENVIAR REGALO (anonimo03, 28-oct: «nuevo botón al lado de comprar todo: enviar regalo, bajo la mecánica de que lo
 *   enviado debe cumplir la lista de F o M»): el regalo NATIVO de cada prenda de la lista elegida (y las de los dos) —
 *   SendGift 0x5CAB20 (apodo, largo, id con plazo) = el FF53 dentro del sobre FF4F, el mismo del botón de la tarjeta. El
 *   server cobra al que regala, se lo da al otro en vivo y rechaza («no puede usar este ítem») la prenda que no es del
 *   sexo del que la recibe. De sus carteles (0x5D0114, uno por prenda) queda el último. */
static volatile LONG g_tn_callar_r = 0;
static DWORD g_tn_callar_r_hasta = 0;

static int __stdcall tn_callar_regalo(void)
{
    if (g_tn_callar_r <= 0) return 0;
    if (GetTickCount() - g_tn_callar_r_hasta < 0x80000000u) { g_tn_callar_r = 0; return 0; }
    g_tn_callar_r--;
    return 1;
}

static void tn_regalar_todo(void)
{
    void *red = *(void **)TNV(0x9314D0);
    if (!red || !g_tn_para[0]) return;
    F_TN_REGALAR regalar = (F_TN_REGALAR)TNV(0x5CAB20);
    int hechas = 0, largo = lstrlenA(g_tn_para);
    for (int i = 0; i < g_tn_n; i++) {
        DWORD raw = 0;
        if (!tn_va(g_tn_carro[i], g_tn_sexo_lista) || !tn_precio(g_tn_carro[i], &raw)) continue;
        regalar(red, g_tn_para, largo, raw);
        hechas++;
    }
    g_tn_callar_r = hechas > 1 ? hechas - 1 : 0;
    g_tn_callar_r_hasta = GetTickCount() + 10000;
    apuntar("  [tienda] ★ enviar regalo a «%s»: %d FF53 (lista de %s, total %d, %d omitidas)", g_tn_para, hechas,
            g_tn_sexo_lista ? "chica" : "chico", g_tn_total, g_tn_omitidas);
}

static void tn_sacar(DWORD id)
{
    void *red = *(void **)TNV(0x9314D0);
    if (red) ((F_TN_SACAR)TNV(0x5D19C0))(red, id);
    apuntar("  [tienda] sacar %lu del carrito (FF70)", (unsigned long)id);
}

/* ═══ 6 · CADA CUADRO DE LA TIENDA (lo llama el salto de 0x4D3F90) ═════════════════════════════════════════════ */
static void __stdcall tn_cuadro(BYTE *tienda)
{
    if (!g_tn_activo || !tienda) return;
    if (g_tn_img == 0) tn_cargar();
    if (g_tn_img != 1) return;
    DWORD ahora = GetTickCount();
    if (ahora - g_tn_visto > 1500) {                     /* se volvió a abrir: de cero */
        if (g_tn_texto[0]) { g_tn_texto[0] = 0; g_tn_refrescar = 1; }   /* la pestaña entera de nuevo */
        g_tn_foco = 0;
        g_tn_cartel = 0;
        g_tn_scroll = 0;
    }
    g_tn_visto = ahora;
    g_tn_tienda = tienda;
    if (g_tn_refrescar) tn_aplicar_busqueda(tienda);
    int cx = *(int *)TNV(0x904084), cy = *(int *)TNV(0x904088);
    g_tn_x0 = cx + TN_ANCLA_X;
    g_tn_y0 = cy + TN_ANCLA_Y;
    g_tn_cx0 = cx - TN_CARTEL_W / 2;
    g_tn_cy0 = cy - TN_CARTEL_H / 2;
    tn_leer_carro();
    if (g_tn_scroll > tn_tope_scroll()) g_tn_scroll = tn_tope_scroll();
    tn_calcular(-1);                                     /* la tira: el total de todo el carrito */
    int mx = -9999, my = -9999;
    if (!(GetForegroundWindow() == g_ventana && tn_tiene_entrada() && tn_raton(&mx, &my))) mx = my = -9999;
    if (!tn_tiene_entrada()) { g_tn_foco = 0; g_tn_foco_para = 0; }
    int sobre = g_tn_cartel ? -1 : tn_control(mx - g_tn_x0, my - g_tn_y0);
    int cursor = (ahora / 500) & 1;
    DWORD firma = 2166136261u;
#define TN_MEZCLA(v) (firma = (firma ^ (DWORD)(v)) * 16777619u)
    for (int i = 0; i < g_tn_n; i++) TN_MEZCLA(g_tn_carro[i]);
    for (const char *p = g_tn_texto; *p; p++) TN_MEZCLA((BYTE)*p);
    TN_MEZCLA(g_tn_n); TN_MEZCLA(g_tn_scroll); TN_MEZCLA(sobre); TN_MEZCLA(g_tn_apretado);
    TN_MEZCLA(g_tn_foco ? cursor + 1 : 0); TN_MEZCLA(g_tn_total);
    void *tex = tn_textura(g_tn_lz);
    if (!tex) return;
    if (firma != g_tn_firma || tex != g_tn_lz_tex) {
        tn_armar(sobre, cursor);
        if (tn_subir(tex, g_tn_px, TN_W, TN_H)) { g_tn_firma = firma; g_tn_lz_tex = tex; }
    }
    tn_figura(g_tn_lz, g_tn_x0, g_tn_y0);
    if (!g_tn_cartel) return;
    tn_calcular(tn_sexo_cartel());                       /* el cartel: sólo lo que va (de tu sexo / de la lista) */
    if (g_tn_cartel == TNK_REGALO && !g_tn_van && g_tn_n) g_tn_sexo_lista = !g_tn_sexo_lista, tn_calcular(g_tn_sexo_lista);
    int cs = tn_control_cartel(mx - g_tn_cx0, my - g_tn_cy0);
    firma = 2166136261u;
    TN_MEZCLA(g_tn_cartel); TN_MEZCLA(cs); TN_MEZCLA(g_tn_capretado); TN_MEZCLA(g_tn_total); TN_MEZCLA(g_tn_saldo);
    TN_MEZCLA(g_tn_n); TN_MEZCLA(g_tn_van); TN_MEZCLA(g_tn_sexo_lista); TN_MEZCLA(g_tn_foco_para ? cursor + 1 : 0);
    for (const char *p = g_tn_para; *p; p++) TN_MEZCLA((BYTE)*p);
    DWORD cf = firma;
    void *ct = tn_textura(g_tn_cz);
    if (!ct) return;
    if (cf != g_tn_cfirma || ct != g_tn_cz_tex) {
        tn_armar_cartel(cs, cursor);
        if (tn_subir(ct, g_tn_cpx, TN_CARTEL_W, TN_CARTEL_H)) { g_tn_cfirma = cf; g_tn_cz_tex = ct; }
    }
    tn_figura(g_tn_cz, g_tn_cx0, g_tn_cy0);
#undef TN_MEZCLA
}

/* ═══ 7 · EL MOUSE Y EL TECLADO (lo llama el WndProc de d3d9_proxy.c ANTES que al juego) ════════════════════════
 *   Devuelve 1 si el mensaje es nuestro (el juego no lo ve). */
static void tn_cambio_texto(void)
{
    g_tn_refrescar = 1;
}

/* «Comprar» / «Enviar» del cartel: sólo si hay algo que va, alcanza el saldo y (el regalo) hay a quién */
static void tn_aceptar(void)
{
    tn_calcular(tn_sexo_cartel());
    if (!g_tn_van || g_tn_total > g_tn_saldo) return;
    if (g_tn_cartel == TNK_REGALO) {
        if (!g_tn_para[0]) { g_tn_foco_para = 1; return; }
        g_tn_cartel = TNK_NADA;
        tn_regalar_todo();
    } else {
        g_tn_cartel = TNK_NADA;
        tn_comprar_todo();
    }
    g_tn_foco_para = 0;
}

static int tn_mensaje_cartel(UINT msg, int x, int y)
{
    int c = tn_control_cartel(x - g_tn_cx0, y - g_tn_cy0);
    if (msg == WM_MOUSEMOVE) return 0;
    if (msg == WM_LBUTTONDOWN || msg == WM_LBUTTONDBLCLK) {
        g_tn_capretado = c;
        g_tn_foco_para = c == TNC_PARA;
    } else if (msg == WM_LBUTTONUP) {
        int a = g_tn_capretado;
        g_tn_capretado = -1;
        if (a != c) return 1;
        if (a == TNC_SI) tn_aceptar();
        else if (a == TNC_NO) { apuntar("  [tienda] cartel %d: cancelado", g_tn_cartel); g_tn_cartel = TNK_NADA; g_tn_foco_para = 0; }
        else if ((a == TNC_CHICA || a == TNC_CHICO) && tn_contar_sexo(a == TNC_CHICA)) g_tn_sexo_lista = a == TNC_CHICA;
    }
    return 1;
}

/* abrir el cartel de la compra o el del regalo */
static void tn_abrir_cartel(int regalo)
{
    g_tn_capretado = -1;
    g_tn_foco = 0;
    if (regalo) {
        g_tn_cartel = TNK_REGALO;
        g_tn_foco_para = 1;
        /* la lista de entrada: la que más prendas tiene (a igualdad, la de tu sexo) */
        int ch = tn_contar_sexo(1), co = tn_contar_sexo(0);
        g_tn_sexo_lista = ch == co ? tn_sexo_jugador() : ch > co;
        tn_calcular(g_tn_sexo_lista);
    } else {
        tn_calcular(tn_sexo_jugador());
        g_tn_cartel = !g_tn_van ? TNK_NINGUNA : g_tn_total <= g_tn_saldo ? TNK_COMPRAR : TNK_NO_ALCANZA;
    }
    apuntar("  [tienda] %s: %d prendas van (%d omitidas), %d Rcoin, saldo %d", regalo ? "enviar regalo" : "comprar todo",
            g_tn_van, g_tn_omitidas, g_tn_total, g_tn_saldo);
}

static int tienda_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    if (!g_tn_activo || !g_tn_raton || g_tn_img != 1) return 0;
    if (GetTickCount() - g_tn_visto > 300 || !tn_tiene_entrada()) {   /* no se dibuja, u otra ventana la tapa: nada nuestro */
        g_tn_foco = 0;
        g_tn_apretado = -1;
        return 0;
    }
    /* el teclado: el cartel se cierra con Esc; con el foco en el buscador, lo escrito es nuestro */
    if (msg == WM_KEYDOWN || msg == WM_KEYUP || msg == WM_CHAR) {
        if (g_tn_cartel) {
            if (msg == WM_KEYDOWN && wp == VK_ESCAPE) { g_tn_cartel = TNK_NADA; g_tn_capretado = -1; g_tn_foco_para = 0; }
            else if (msg == WM_KEYDOWN && wp == VK_RETURN) tn_aceptar();
            else if (msg == WM_CHAR && g_tn_cartel == TNK_REGALO && g_tn_foco_para) {   /* el apodo del que lo recibe */
                int n = lstrlenA(g_tn_para);
                if (wp == 8) { if (n > 0) g_tn_para[n - 1] = 0; }
                else if (wp > 0x20 && wp != 0x7F && wp < 0x100 && n < 20) { g_tn_para[n] = (char)wp; g_tn_para[n + 1] = 0; }
            }
            return 1;
        }
        if (!g_tn_foco) return 0;
        if (msg == WM_KEYDOWN && (wp == VK_ESCAPE || wp == VK_RETURN)) g_tn_foco = 0;
        if (msg == WM_CHAR) {
            int n = lstrlenA(g_tn_texto);
            if (wp == 8) {                                   /* borrar: una letra (las dos si es UTF-8) */
                if (n > 0) {
                    n--;
                    while (n > 0 && ((BYTE)g_tn_texto[n] & 0xC0) == 0x80) n--;
                    g_tn_texto[n] = 0;
                    tn_cambio_texto();
                }
            } else if ((wp >= 0x20 && wp != 0x7F && wp < 0x100) && n < TN_TEXTO_MAX) {
                g_tn_texto[n] = (char)wp;
                g_tn_texto[n + 1] = 0;
                tn_cambio_texto();
            }
        }
        return 1;
    }
    if (msg < WM_MOUSEFIRST || msg > 0x20E) return 0;
    int x, y;
    if (!tn_a_juego(h, lp, msg == WM_MOUSEWHEEL || msg == 0x20E, &x, &y)) return 0;
    if (g_tn_cartel) return tn_mensaje_cartel(msg, x, y);
    int lx = x - g_tn_x0, ly = y - g_tn_y0, c = tn_control(lx, ly);
    switch (msg) {
    case WM_MOUSEMOVE:
        return 0;
    case WM_LBUTTONDOWN:
    case WM_LBUTTONDBLCLK:
        g_tn_foco = c == TNC_CAMPO;
        g_tn_apretado = c;
        return tn_en_franja(lx, ly);
    case WM_LBUTTONUP: {
        int a = g_tn_apretado;
        g_tn_apretado = -1;
        if (a < 0 || a != c) return tn_en_franja(lx, ly);
        if (a == TNC_BORRAR) { g_tn_texto[0] = 0; g_tn_foco = 1; tn_cambio_texto(); }
        else if (a == TNC_IZQ && g_tn_scroll > 0) g_tn_scroll--;
        else if (a == TNC_DER && g_tn_scroll < tn_tope_scroll()) g_tn_scroll++;
        else if ((a == TNC_BOTON || a == TNC_REGALO) && g_tn_n) tn_abrir_cartel(a == TNC_REGALO);
        else if (a >= TNC_EQUIS0 && a < TNC_EQUIS0 + TN_CASILLAS && g_tn_scroll + (a - TNC_EQUIS0) < g_tn_n)
            tn_sacar(g_tn_carro[g_tn_scroll + (a - TNC_EQUIS0)]);
        return 1;
    }
    case WM_MOUSEWHEEL: {
        if (!tn_dentro(lx, ly, TN_TIRA_X, 0, TN_TIRA_W, TN_H)) return 0;
        int d = (short)HIWORD(wp);
        g_tn_scroll += d > 0 ? -1 : 1;
        if (g_tn_scroll < 0) g_tn_scroll = 0;
        if (g_tn_scroll > tn_tope_scroll()) g_tn_scroll = tn_tope_scroll();
        return 1;
    }
    default:
        return tn_en_franja(lx, ly);
    }
}

static int tienda_quiere_ventana(void) { return g_tn_activo; }

/* ═══ 8 · LOS SALTOS ═════════════════════════════════════════════════════════════════════════════════════════════ */
static int tn_escribir(DWORD va, const BYTE *nuevo, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(TNV(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(TNV(va), nuevo, n);
    VirtualProtect(TNV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), TNV(va), n);
    return 1;
}

static int tn_salto(BYTE *k, int i, DWORD destino)          /* jmp rel32 en k+i -> el largo nuevo */
{
    k[i] = 0xE9;
    *(int *)(k + i + 1) = (int)(destino - (DWORD)(k + i + 5));
    return i + 5;
}

static void tienda_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("tienda", "activo", 1, ini)) { apuntar("  [tienda] apagado ([tienda] activo=0)"); return; }
    g_tn_base = (BYTE *)GetModuleHandleA(NULL);
    g_tn_z = (float)GetPrivateProfileIntA("tienda", "z", 900, ini) / 1000.0f;
    g_tn_z_cartel = (float)GetPrivateProfileIntA("tienda", "z_cartel", 300, ini) / 1000.0f;
    static const BYTE LLENAR[8] = { 0x83, 0xEC, 0x5C, 0xA1, 0x70, 0xB2, 0x91, 0x00 };   /* sub esp,5C · mov eax,[91B270] */
    static const BYTE COLA_A[5] = { 0xE9, 0xD4, 0xDA, 0xFF, 0xFF };                      /* 0x4D3FC7: jmp 0x4D1AA0 */
    static const BYTE COLA_B[5] = { 0xE9, 0xC0, 0xDA, 0xFF, 0xFF };                      /* 0x4D3FDB: jmp 0x4D1AA0 */
    static const BYTE AVISO[5] = { 0xE8, 0xBD, 0x4D, 0xE5, 0xFF };                       /* 0x5CE5DE: call 0x4233A0 */
    if (memcmp(TNV(0x4D5AF0), LLENAR, 8) || memcmp(TNV(0x4D6320), LLENAR, 8) ||
        memcmp(TNV(0x4D3FC7), COLA_A, 5) || memcmp(TNV(0x4D3FDB), COLA_B, 5) || memcmp(TNV(0x5CE5DE), AVISO, 5)) {
        apuntar("  [tienda] ⛔ el exe no es el esperado (0x4D5AF0 / 0x4D6320 / 0x4D3FC7 / 0x4D3FDB / 0x5CE5DE): sin buscador");
        return;
    }
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 512, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) { apuntar("  [tienda] ⛔ sin memoria para los saltos"); return; }
    /* el cuadro: pushad · push ecx (la tienda) · call tn_cuadro · popad · jmp 0x4D1AA0 */
    BYTE *cuadro = k;
    int i = 0;
    cuadro[i++] = 0x60;
    cuadro[i++] = 0x51;
    cuadro[i] = 0xE8; *(int *)(cuadro + i + 1) = (int)((DWORD)tn_cuadro - (DWORD)(cuadro + i + 5)); i += 5;
    cuadro[i++] = 0x61;
    i = tn_salto(cuadro, i, (DWORD)TNV(0x4D1AA0));
    /* la lista: pushad · push [esp+2C] ×3 (forzar, inicio, lista) · push ecx · call tn_lista · mov [esp+24],eax
     *   (la lista nueva en el lugar del 1.er argumento) · popad · lo pisado · jmp a la función +8 */
    BYTE *listas[2] = { k + 64, k + 128 };
    DWORD funciones[2] = { 0x4D5AF0, 0x4D6320 };
    for (int f = 0; f < 2; f++) {
        BYTE *s = listas[f];
        int j = 0;
        s[j++] = 0x60;
        for (int r = 0; r < 3; r++) { s[j++] = 0xFF; s[j++] = 0x74; s[j++] = 0x24; s[j++] = 0x2C; }
        s[j++] = 0x51;
        s[j] = 0xE8; *(int *)(s + j + 1) = (int)((DWORD)tn_lista - (DWORD)(s + j + 5)); j += 5;
        s[j++] = 0x89; s[j++] = 0x44; s[j++] = 0x24; s[j++] = 0x24;
        s[j++] = 0x61;
        s[j++] = 0x83; s[j++] = 0xEC; s[j++] = 0x5C;
        s[j++] = 0xA1; *(DWORD *)(s + j) = (DWORD)TNV(0x91B270); j += 4;
        j = tn_salto(s, j, (DWORD)TNV(funciones[f] + 8));
    }
    /* el cartel de la compra: push ecx · call tn_callar · pop ecx · test eax,eax · jz 0x4233A0 · ret 0x18 (sus 6 argumentos) */
    BYTE *aviso = k + 192;
    int a = 0;
    aviso[a++] = 0x51;
    aviso[a] = 0xE8; *(int *)(aviso + a + 1) = (int)((DWORD)tn_callar - (DWORD)(aviso + a + 5)); a += 5;
    aviso[a++] = 0x59;
    aviso[a++] = 0x85; aviso[a++] = 0xC0;
    aviso[a++] = 0x0F; aviso[a++] = 0x84; *(int *)(aviso + a) = (int)((DWORD)TNV(0x4233A0) - (DWORD)(aviso + a + 4)); a += 4;
    aviso[a++] = 0xC2; aviso[a++] = 0x18; aviso[a++] = 0x00;
    /* el del regalo (0x5D0114, la llamada única de los 8 resultados del FF53): lo mismo con tn_callar_regalo */
    BYTE *aviso_r = k + 224;
    a = 0;
    aviso_r[a++] = 0x51;
    aviso_r[a] = 0xE8; *(int *)(aviso_r + a + 1) = (int)((DWORD)tn_callar_regalo - (DWORD)(aviso_r + a + 5)); a += 5;
    aviso_r[a++] = 0x59;
    aviso_r[a++] = 0x85; aviso_r[a++] = 0xC0;
    aviso_r[a++] = 0x0F; aviso_r[a++] = 0x84; *(int *)(aviso_r + a) = (int)((DWORD)TNV(0x4233A0) - (DWORD)(aviso_r + a + 4)); a += 4;
    aviso_r[a++] = 0xC2; aviso_r[a++] = 0x18; aviso_r[a++] = 0x00;
    BYTE n[8];
    int ok = 1;
    n[0] = 0xE8;
    *(int *)(n + 1) = (int)((DWORD)aviso - ((DWORD)TNV(0x5CE5DE) + 5));
    ok &= tn_escribir(0x5CE5DE, n, 5);
    /* la llave del mouse: la entrada de 0x4D3FE0 (push ebp · push edi · mov edi,ecx · xor ebp,ebp) -> pushad · call
     *   tn_marca_entrada · popad · lo pisado · jmp 0x4D3FE6 */
    static const BYTE ENTRADA[6] = { 0x55, 0x57, 0x8B, 0xF9, 0x33, 0xED };
    if (memcmp(TNV(0x4D3FE0), ENTRADA, 6)) { apuntar("  [tienda] ⛔ 0x4D3FE0 no es el esperado: sin buscador"); return; }
    BYTE *marca = k + 256;                                  /* ⚠ la 2.ª lista ocupa 128..165 */
    a = 0;
    marca[a++] = 0x60;
    marca[a] = 0xE8; *(int *)(marca + a + 1) = (int)((DWORD)tn_marca_entrada - (DWORD)(marca + a + 5)); a += 5;
    marca[a++] = 0x61;
    CopyMemory(marca + a, ENTRADA, 6); a += 6;
    tn_salto(marca, a, (DWORD)TNV(0x4D3FE6));
    n[0] = 0xE9;
    *(int *)(n + 1) = (int)((DWORD)marca - ((DWORD)TNV(0x4D3FE0) + 5));
    n[5] = 0x90;
    ok &= tn_escribir(0x4D3FE0, n, 6);
    static const BYTE AVISO_R[5] = { 0xE8, 0x87, 0x32, 0xE5, 0xFF };                    /* 0x5D0114: call 0x4233A0 */
    if (!memcmp(TNV(0x5D0114), AVISO_R, 5)) {
        *(int *)(n + 1) = (int)((DWORD)aviso_r - ((DWORD)TNV(0x5D0114) + 5));
        ok &= tn_escribir(0x5D0114, n, 5);
    } else apuntar("  [tienda] ⚠ 0x5D0114 no es el esperado: los carteles del regalo salen todos");
    g_tn_raton = GetPrivateProfileIntA("tienda", "raton", 1, ini);
    int con_lista = GetPrivateProfileIntA("tienda", "lista", 1, ini), con_cuadro = GetPrivateProfileIntA("tienda", "cuadro", 1, ini);
    for (int f = 0; f < 2 && con_lista; f++) {
        tn_salto(n, 0, (DWORD)listas[f]);
        *(int *)(n + 1) = (int)((DWORD)listas[f] - ((DWORD)TNV(funciones[f]) + 5));
        n[5] = n[6] = n[7] = 0x90;
        ok &= tn_escribir(funciones[f], n, 8);
    }
    DWORD colas[2] = { 0x4D3FC7, 0x4D3FDB };
    for (int c = 0; c < 2 && con_cuadro; c++) {
        n[0] = 0xE9;
        *(int *)(n + 1) = (int)((DWORD)cuadro - ((DWORD)TNV(colas[c]) + 5));
        ok &= tn_escribir(colas[c], n, 5);
    }
    /* ★ sin «se ha guardado en Mis preferidos» ni «ha sido eliminado» (anonimo03, 28-oct: «que el popup de añadido o
     *   quitado no aparezca»). Las ramas de ÉXITO de las respuestas, después de tocar la lista, cargan su texto
     *   (push 0x125 / push 0x128) y van al cartel: ese push pasa a ser un salto a la salida. Los errores (repetido,
     *   lleno, no se pudo) entran por otro lado y siguen con su cartel. El server contesta igual que siempre: con una
     *   dll vieja salen los carteles de fábrica, y nada se traba (la respuesta del FF6F es la que vuelve a habilitar el
     *   botón: [cuenta+0x50C], 0x5E9015). [tienda] carteles_carrito=1 los deja. */
    if (!GetPrivateProfileIntA("tienda", "carteles_carrito", 0, ini)) {
        static const BYTE P125[5] = { 0x68, 0x25, 0x01, 0x00, 0x00 }, P128[5] = { 0x68, 0x28, 0x01, 0x00, 0x00 };
        struct { DWORD va, salida; const BYTE *espera; } C[3] = {
            { 0x5E9064, 0x5E9113, P125 }, { 0x5E90A7, 0x5E9113, P125 }, { 0x5D15CD, 0x5D15F2, P128 } };
        for (int c = 0; c < 3; c++) {
            if (memcmp(TNV(C[c].va), C[c].espera, 5)) { apuntar("  [tienda] ⚠ 0x%06lX no es el esperado: ese cartel queda", C[c].va); continue; }
            n[0] = 0xE9;
            *(int *)(n + 1) = (int)((DWORD)TNV(C[c].salida) - ((DWORD)TNV(C[c].va) + 5));
            ok &= tn_escribir(C[c].va, n, 5);
        }
    }
    if (!ok) { apuntar("  [tienda] ⛔ VirtualProtect: sin buscador"); return; }
    g_tn_activo = 1;
    apuntar("  [tienda] ok: el buscador (0x4D5AF0/0x4D6320), la franja y el carrito (0x4D3F90), z %d/%d%s%s%s",
            (int)(g_tn_z * 1000 + 0.5f), (int)(g_tn_z_cartel * 1000 + 0.5f), con_lista ? "" : " · SIN lista",
            con_cuadro ? "" : " · SIN cuadro", g_tn_raton ? "" : " · SIN ratón");
}
