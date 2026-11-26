/* n2h_ventana.c — ★ 19-nov · LA VENTANA DE Ñ2HOCK, HECHA DE CERO CON CONTROLES DE WINDOWS
 *
 *   anonimo03: «no se parece en nada» / «hazlo todo desde 0». La ventana dibujada a mano (§ 7 de
 *   herramienta.c) no se sentía como Ñ2Hock.exe, que es WinForms con el modo oscuro de .NET 9.
 *   ⇒ Ésta es una COPIA de esa ventana con los MISMOS controles de Windows (pestañas, combos, botones,
 *     cajas de texto) y las MISMAS medidas y colores, sacados de su código fuente:
 *       · Form1.Personal.cs (la cáscara 330 x 671, Juego y Controles), Training*.cs, Chat*.cs.
 *       · Palette.cs (los colores del modo oscuro), FlatSlider.cs (la barra).
 *     Las casillas, los recuadros con título rosa y la barra se pintan acá (como hace WinForms).
 *   ⚠ Los controles «nuevos» de Windows (comctl32 v6) necesitan un manifiesto: el exe del juego no lo
 *     trae, así que el hilo de la ventana activa uno propio (n2_contexto_v6) antes de crear nada.
 *   La LÓGICA es la de siempre (g_op, ht_cambiar, ht_tick, el ini): acá sólo está la cara.
 *   Entreno / Tramos / Chat: por ahora la misma cara, apagada («Próximamente»).
 *
 *   Se incluye dentro de herramienta.c (usa sus ht_*), justo antes de ht_armar_ventana. */

#include <commctrl.h>
#include <commdlg.h>

/* ── los colores (Palette.cs, oscuro) ─────────────────────────────────────── */
#define N2_VENTANA   RGB(24, 24, 27)
#define N2_PAGINA    RGB(32, 32, 36)
#define N2_TEXTO     RGB(229, 231, 235)
#define N2_SUAVE     RGB(209, 213, 219)
#define N2_AVISO     RGB(251, 191, 36)
#define N2_BIEN      RGB(94, 234, 212)
#define N2_ERROR     RGB(251, 146, 60)
#define N2_RIEL      RGB(63, 63, 70)
#define N2_APAGADO   RGB(82, 82, 91)
#define N2_PERILLA   RGB(39, 39, 42)
#define N2_CAJA      RGB(45, 45, 48)
#define N2_CAJA_ACT  RGB(70, 70, 78)
static COLORREF g_n2_acento = RGB(255, 0, 128);  /* el color de los títulos y de la barra (Personalización · Color…) */
#define N2_ACENTO_FAB RGB(255, 0, 128)         /* #FF0080, el del ToolBitPersonal de anonimo03 */
#define N2_ACENTO    (g_n2_acento)
#define N2_C_ACENTO  0x01000000u               /* «el color del acento», para los textos que lo siguen */
#define N2_MARCO     RGB(204, 204, 204)         /* los recuadros y las cajas */
#define N2_TILDE     RGB(46, 134, 222)          /* la casilla marcada */
#define N2_GRIS_TX   RGB(128, 128, 134)         /* el texto apagado */

#define N2_W 330
#define N2_H 761                                /* ★ 26-nov (boceto de anonimo03): +90 para el Idioma abajo */
#define N2_PAGS 5                               /* las de la ventana principal */
#define N2_PAGS_TOT 9                           /* + las 4 de Personalización (5 Ventana con AutoFar · 6 Far · 7 Piedras y booster · 8 PD) */
#define N2P_PIEDRAS 7                           /* ★ 26-nov (boceto de anonimo03): piedras y booster en UNA pestaña */
#define N2P_AUTOFAR 5                           /* ★ y AutoFar debajo de la Personalización, en Ventana (AF_Y0) */
#define N2P_PD      8
#define WM_N2H_SYNC_ (WM_N2H_SYNC)

enum { C_CHK, C_TECLA, C_COMBO, C_BOTON, C_SLIDER, C_EDIT, C_LISTA };
enum { B_CONECTAR = 1, B_RESTAURAR, B_PERSONAL, B_NADA, B_FONDO, B_QUITAR, B_COLOR, B_RESTABLECER,
       B_IND_COLOR, B_IND_PROBAR, B_IND_FABRICA, B_IND_GUARDAR };
enum { L_LETRA = 1, L_TEMA, L_IND_LETRA, L_IDIOMA, L_CUENTA, L_CANAL, L_COD };
#define N2_TRAMOS 12                       /* ★ 26-nov: las filas de la pestaña Tramos (antes 6; se ven de a 6) */
enum { B_CHAT_VACIAR = 40, B_E_REINICIAR, B_E_GUARDAR, B_E_BORRAR_TODO, B_E_BORRAR0, B_E_MOVER0 = B_E_BORRAR0 + N2_TRAMOS,
       B_E_MAPA = B_E_MOVER0 + 4, B_E_TR_PAG };
enum { L_TRAMO_VEL = 20 };
/* ★ Entreno y Tramos (n2h_entreno.c): lo que muestra y guarda la ventana */
enum { E_TK_VEL, E_TK_MENOS, E_TK_MAS, E_TK_BUCLE, E_TK_A, E_TK_B, E_TK_REIN, E_TK_TRAMOS, E_TK_MARCA, E_TK_MOVER0, E_TK_N = E_TK_MOVER0 + 4 };
typedef struct {
    int confirmo, habilitar, anticaida, vel_on, vel_pct, bucle_on, tramos_on;
    int tk[E_TK_N];
    wchar_t desde[16], hasta[16], cuenta[8], sin[8], tde[N2_TRAMOS][16], tha[N2_TRAMOS][16];
    int tvel[N2_TRAMOS];
} N2_ENTRENO;
static N2_ENTRENO g_e = { 0, 0, 0, 0, 55, 0, 0,
                          { VK_F2, '1', '2', VK_F1, VK_INSERT, VK_DELETE, VK_END, 0, 0, 0, 0, 0, 0 },
                          L"00:20", L"00:40", L"3", L"2", { { 0 } }, { { 0 } }, { 100, 100, 100, 100, 100, 100 } };
static wchar_t g_e_tx[NE_TX_N][320], g_e_pct_txt[16];
static int  g_e_lbl[NE_TX_N] = { -1, -1, -1, -1, -1 }, g_e_tx_err[NE_TX_N];
static HWND g_e_ed_desde, g_e_ed_hasta, g_e_ed_cuenta, g_e_ed_sin, g_e_ed_tde[N2_TRAMOS], g_e_ed_tha[N2_TRAMOS], g_e_cb_tvel[N2_TRAMOS];
static HWND g_e_bt_tx[N2_TRAMOS], g_e_bt_pag;            /* ★ 26-nov: los ✕ de cada fila y el botón de 1–6 / 7–12 */
static int  g_e_tr_pag = 0;                              /* 0: filas 1–6 · 1: filas 7–12 */
static wchar_t g_e_num[6][4] = { L"1", L"2", L"3", L"4", L"5", L"6" };
/* el Chat (n2h_chat.c) */
static int  g_n2_vel_en_juego = 1, g_n2_capa_es_vel = 0;   /* ★ «VEL 75 %» encima del juego, como el Far */
static int  g_n2_chat_diez = 0, g_n2_chat_en_juego = 1, g_n2_chat_solo = 1, g_n2_chat_cod = 0, g_n2_chat_lbl = -1;
static HWND g_n2_chat_canal, g_n2_chat_lista;
static wchar_t g_n2_chat_estado[160];
static COLORREF g_n2_chat_estado_c = RGB(229, 231, 235);
typedef struct { BYTE tipo, pag, falso; HWND h; int ref; int *pvk; int *pbool; RECT r; } N2_CTL;
typedef struct { BYTE pag; RECT r; const wchar_t *t; const wchar_t *dyn; COLORREF c; UINT fmt; } N2_LBL;
typedef struct { BYTE pag; RECT r; const wchar_t *t; } N2_GRP;

#define N2_MAXC 280
static N2_CTL g_n2c[N2_MAXC]; static int g_n2n;
static N2_LBL g_n2l[160];     static int g_n2nl;
static N2_GRP g_n2g[16];      static int g_n2ng;
static HWND   g_n2_pag[N2_PAGS_TOT], g_n2_tabs, g_n2_per, g_n2_per_tabs, g_n2_vista;
static HFONT  g_n2_f, g_n2_fb, g_n2_fchico, g_n2_ftab;
static HBRUSH g_n2_br_ven, g_n2_br_pag, g_n2_br_caja;
static BYTE   g_n2_p = 0xFF;                    /* dónde se está armando: 0..4 una pestaña, 0xFF la ventana */
static int    g_n2_ox, g_n2_oy;                 /* el origen (lienzo o recuadro) */
static wchar_t g_ht_far_n2h_txt[16], g_n2_alfa_txt[16];
static int    g_n2_arrastre = 0;

static HWND n2_padre(void) { return g_n2_p == 0xFF ? g_ht_ven : g_n2_pag[g_n2_p]; }

/* ── Personalización (Form1.Appearance.cs / FarIndicatorEditor.cs): lo que se guarda en [herramienta] ── */
static wchar_t g_n2_letra[64] = L"Sitka Text Semibold";  /* la «Letra» de anonimo03 en su Ñ2Hock */
static int     g_n2_velo = 70, g_n2_opac = 100;
static wchar_t g_n2_velo_txt[16], g_n2_opac_txt[16], g_n2_tam_txt[16], g_n2_dura_txt[16], g_n2_ind_estado[96];
static char    g_n2_apodo[40];
static HDC     g_n2_cache_dc[N2_PAGS_TOT + 1];       /* lo que pintó cada página (y [8] la ventana): el fondo de sus controles */
static HBITMAP g_n2_cache_bm[N2_PAGS_TOT + 1];
static int     g_n2_cache_w[N2_PAGS_TOT + 1], g_n2_cache_h[N2_PAGS_TOT + 1];
static HDC     g_n2_fondo_dc;  static HBITMAP g_n2_fondo_bm;      /* la imagen + el velo, del tamaño de la ventana */
static void n2_per_comando(int ref);
static void n2_lista_cambio(int ref, HWND h);
static void n2_per_abrir(void);
static void n2_apodo_tick(void);
static void n2_e_cambio(int *pb);
static void n2_e_tick(void);
static COLORREF n2_e_color(int lbl, COLORREF c);
static void n2_e_leer(void);
static void n2_e_guardar(HT_BUF *x, const char *eol);
static void n2_e_falta_confirmo(void);
static HWND g_n2m_barra;
static void n2_chat_tick(void);
static void n2_capa_tick(void);
static int  g_n2_capa_firma;
static int  g_n2i_arco = 1;            /* ★ 26-nov: el cartel del Far con el estilo crayón y el arcoíris que lo recorre */
static void n2_en(BYTE p, int ox, int oy) { g_n2_p = p; g_n2_ox = ox; g_n2_oy = oy; }
static void n2_lienzo(BYTE p) { n2_en(p, 3, 3); }    /* TabPage Padding(3) */

static void n2_grupo(const wchar_t *t, int y, int h)  /* Group(): (2, y, 292, h) del lienzo */
{
    if (g_n2ng >= 16) return;
    N2_GRP *g = &g_n2g[g_n2ng++];
    g->pag = g_n2_p; g->t = t;
    SetRect(&g->r, 3 + 2, 3 + y, 3 + 2 + 292, 3 + y + h);
    g_n2_ox = g->r.left; g_n2_oy = g->r.top;
}

static void n2_grupo_xy(const wchar_t *t, int x, int y, int w, int h)   /* ★ 26-nov: en la ventana principal */
{
    if (g_n2ng >= 16) return;
    N2_GRP *g = &g_n2g[g_n2ng++];
    g->pag = g_n2_p; g->t = t;
    SetRect(&g->r, x, y, x + w, y + h);
    g_n2_ox = g->r.left; g_n2_oy = g->r.top;
}

static void n2_lbl(int x, int y, int w, int h, const wchar_t *t, COLORREF c, UINT fmt)
{
    if (g_n2nl >= 160) return;
    N2_LBL *l = &g_n2l[g_n2nl++];
    l->pag = g_n2_p; l->t = t; l->dyn = NULL; l->c = c; l->fmt = fmt;
    SetRect(&l->r, g_n2_ox + x, g_n2_oy + y, g_n2_ox + x + w, g_n2_oy + y + h);
}
#define N2_IZQ  (DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX)
#define N2_CEN  (DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX)
#define N2_ABAJO (DT_LEFT | DT_BOTTOM | DT_SINGLELINE | DT_NOPREFIX)
#define N2_PARR (DT_LEFT | DT_WORDBREAK | DT_NOPREFIX)

/* los temas oscuros de Windows (uxtheme): SetWindowTheme y, si están, los ordinales del modo oscuro */
typedef HRESULT (WINAPI *N2_SETTHEME)(HWND, LPCWSTR, LPCWSTR);
typedef BOOL (WINAPI *N2_ALLOWDARK)(HWND, BOOL);
static N2_SETTHEME g_n2_settheme; static N2_ALLOWDARK g_n2_allowdark;
static void n2_oscuro(HWND h, const wchar_t *tema)
{
    if (g_n2_allowdark) g_n2_allowdark(h, TRUE);
    if (g_n2_settheme) g_n2_settheme(h, tema, NULL);
}

static N2_CTL *n2_ctl(BYTE tipo, const wchar_t *clase, const wchar_t *txt, DWORD est, int x, int y, int w, int h, int ref)
{
    if (g_n2n >= N2_MAXC) return NULL;
    int i = g_n2n++;
    N2_CTL *c = &g_n2c[i];
    ZeroMemory(c, sizeof(*c));
    c->tipo = tipo; c->pag = g_n2_p; c->ref = ref;
    SetRect(&c->r, g_n2_ox + x, g_n2_oy + y, g_n2_ox + x + w, g_n2_oy + y + h);
    c->h = CreateWindowExW(0, clase, txt, WS_CHILD | WS_VISIBLE | WS_TABSTOP | est, c->r.left, c->r.top,
                           w, h, n2_padre(), (HMENU)(INT_PTR)(1000 + i), GetModuleHandleA(NULL), NULL);
    if (c->h) SendMessageW(c->h, WM_SETFONT, (WPARAM)g_n2_f, 0);
    return c;
}

/* una casilla de una opción (ref = O_*) o de mentira (ref = -1, apagada, `on` fijo) */
static void n2_chk(int x, int y, int w, int h, const wchar_t *t, int ref, int on)
{
    N2_CTL *c = n2_ctl(C_CHK, L"Button", t ? t : g_op[ref].texto, BS_OWNERDRAW, x, y, w, h, ref);
    if (c && ref < 0) { c->falso = (BYTE)on; EnableWindow(c->h, FALSE); }
}

static void n2_chk_b(int x, int y, int w, int h, const wchar_t *t, int *pb)
{
    N2_CTL *c = n2_ctl(C_CHK, L"Button", t, BS_OWNERDRAW, x, y, w, h, -2);
    if (c) c->pbool = pb;
}

/* un combo con su propia lista (letras, tema, idioma, la cuenta): lo llena quien lo crea */
static HWND n2_combo_lista(int x, int y, int w, int h, int ref, DWORD extra)
{
    N2_CTL *c = n2_ctl(C_COMBO, L"ComboBox", L"", CBS_DROPDOWNLIST | WS_VSCROLL | extra, x, y, w, 300, ref);
    if (!c || !c->h) return NULL;
    c->r.bottom = c->r.top + h;
    n2_oscuro(c->h, L"DarkMode_CFD");
    return c->h;
}

/* ── las teclas de los combos: la lista de HotkeyManager.cs ─────────────────── */
static const struct { const wchar_t *n; BYTE vk; } N2_EXTRA[] = {
    { L"INSERT", VK_INSERT }, { L"DELETE", VK_DELETE }, { L"HOME", VK_HOME }, { L"END", VK_END },
    { L"PGUP", VK_PRIOR }, { L"PGDN", VK_NEXT }, { L"TAB", VK_TAB }, { L"SPACE", VK_SPACE },
    { L"SHIFT", VK_SHIFT }, { L"LSHIFT", VK_LSHIFT }, { L"RSHIFT", VK_RSHIFT },
    { L"CTRL", VK_CONTROL }, { L"LCTRL", VK_LCONTROL }, { L"RCTRL", VK_RCONTROL },
    { L"ALT", VK_MENU }, { L"LALT", VK_LMENU }, { L"RALT", VK_RMENU },
};
static void n2_combo_meter(HWND cb, const wchar_t *n, int vk)
{
    LRESULT k = SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)n);
    if (k >= 0) SendMessageW(cb, CB_SETITEMDATA, (WPARAM)k, (LPARAM)vk);
}
static void n2_combo_teclas(HWND cb)
{
    wchar_t n[16];
    n2_combo_meter(cb, L"Not", 0);
    for (int i = 1; i <= 12; i++) { wsprintfW(n, L"F%d", i); n2_combo_meter(cb, n, VK_F1 + i - 1); }
    for (int c = 'A'; c <= 'Z'; c++) { n[0] = (wchar_t)c; n[1] = 0; n2_combo_meter(cb, n, c); }
    for (int c = '0'; c <= '9'; c++) { n[0] = (wchar_t)c; n[1] = 0; n2_combo_meter(cb, n, c); }
    for (int i = 0; i <= 9; i++) { wsprintfW(n, L"NUM%d", i); n2_combo_meter(cb, n, VK_NUMPAD0 + i); }
    for (int i = 0; i < (int)(sizeof(N2_EXTRA) / sizeof(N2_EXTRA[0])); i++) n2_combo_meter(cb, N2_EXTRA[i].n, N2_EXTRA[i].vk);
}
static void n2_combo_elegir(HWND cb, int vk)
{
    int n = (int)SendMessageW(cb, CB_GETCOUNT, 0, 0);
    for (int i = 0; i < n; i++)
        if ((int)SendMessageW(cb, CB_GETITEMDATA, (WPARAM)i, 0) == vk) {
            if ((int)SendMessageW(cb, CB_GETCURSEL, 0, 0) != i) SendMessageW(cb, CB_SETCURSEL, (WPARAM)i, 0);
            return;
        }
    wchar_t nom[32];                                   /* una tecla que no está en la lista: se agrega */
    ht_nombre_vk(vk, nom);
    n2_combo_meter(cb, nom, vk);
    n2_combo_elegir(cb, vk);
}

/* un combo de tecla de verdad (pvk = dónde vive el VK) o de mentira (pvk = NULL, apagado, con `txt`) */
static void n2_combo(int x, int y, int w, int h, int *pvk, const wchar_t *txt)
{
    N2_CTL *c = n2_ctl(C_COMBO, L"ComboBox", L"", CBS_DROPDOWNLIST | WS_VSCROLL, x, y, w, 300, 0);
    if (!c || !c->h) return;
    c->r.bottom = c->r.top + h;
    c->pvk = pvk;
    n2_oscuro(c->h, L"DarkMode_CFD");
    if (pvk) { n2_combo_teclas(c->h); n2_combo_elegir(c->h, *pvk); }
    else {
        SendMessageW(c->h, CB_ADDSTRING, 0, (LPARAM)txt);
        SendMessageW(c->h, CB_SETCURSEL, 0, 0);
        EnableWindow(c->h, FALSE);
    }
}

static void n2_boton(int x, int y, int w, int h, const wchar_t *t, int ref)
{
    N2_CTL *c = n2_ctl(C_BOTON, L"Button", t, BS_PUSHBUTTON, x, y, w, h, ref);
    if (!c || !c->h) return;
    n2_oscuro(c->h, L"DarkMode_Explorer");
    if (ref == B_NADA) EnableWindow(c->h, FALSE);
}

static void n2_slider(int x, int y, int w, int h, int ref)
{
    N2_CTL *c = n2_ctl(C_SLIDER, L"N2HSlider", L"", 0, x, y, w, h, ref);
    if (c && c->h) SetWindowLongPtrW(c->h, GWLP_USERDATA, ref);

}

static void n2_tecla(int x, int y, int w, int h, int id)
{
    n2_ctl(C_TECLA, L"Button", L"", BS_OWNERDRAW, x, y, w, h, id);
}

/* una caja de texto (de mentira): el borde blanco lo pinta la página, como WinForms oscuro */
static void n2_edit(int x, int y, int w, int h, const wchar_t *t)
{
    N2_CTL *c = n2_ctl(C_EDIT, L"Edit", t, ES_AUTOHSCROLL, x, y, w, h, 0);
    if (!c || !c->h) return;
    SetWindowPos(c->h, NULL, c->r.left + 3, c->r.top + 4, w - 6, h - 7, SWP_NOZORDER | SWP_NOACTIVATE);
    EnableWindow(c->h, FALSE);
}

static HWND n2_edit_v(int x, int y, int w, int h, const wchar_t *t)
{
    N2_CTL *c = n2_ctl(C_EDIT, L"Edit", t, ES_AUTOHSCROLL, x, y, w, h, 0);
    if (!c || !c->h) return NULL;
    SetWindowPos(c->h, NULL, c->r.left + 3, c->r.top + 4, w - 6, h - 7, SWP_NOZORDER | SWP_NOACTIVATE);
    return c->h;
}

static void n2_lista(int x, int y, int w, int h)
{
    N2_CTL *c = n2_ctl(C_LISTA, L"ListBox", L"", WS_VSCROLL | LBS_NOINTEGRALHEIGHT | LBS_NOSEL | LBS_OWNERDRAWFIXED | LBS_HASSTRINGS,
                       x, y, w, h, 0);
    if (!c || !c->h) return;
    SetWindowPos(c->h, NULL, c->r.left + 2, c->r.top + 2, w - 4, h - 4, SWP_NOZORDER | SWP_NOACTIVATE);
    n2_oscuro(c->h, L"DarkMode_Explorer");
}

/* ── la maqueta (las coordenadas de Ñ2Hock, tal cual) ─────────────────────── */
static void n2_maquetar(void)
{
    /* la conexión (fila 1 del TableLayoutPanel: 8 de padding + 3 de margen) */
    n2_en(0xFF, 11, 11);
    {
        HWND cb = n2_combo_lista(4, 4, 146, 23, L_CUENTA, 0);
        if (cb) { SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)L"Este juego"); SendMessageW(cb, CB_SETCURSEL, 0, 0); }
    }
    n2_chk(6, 32, 70, 20, L"Hotkey", O_HOTKEYS, 0);
    n2_chk(80, 32, 70, 20, L"Anclar", O_ANCLAR, 0);
    n2_boton(156, 3, 136, 25, L"Conectar", B_CONECTAR);
    n2_boton(156, 30, 136, 25, L"Restaurar", B_RESTAURAR);
    /* ★ 26-nov (boceto de anonimo03): el IDIOMA abajo, entre las pestañas y Personalización, y el botón más grande */
    n2_en(0xFF, 0, 0);
    n2_grupo_xy(L"Idioma", 11, 638, 308, 72);
    n2_lbl(8, 20, 70, 22, L"Idioma", N2_C_ACENTO, N2_IZQ);
    {
        HWND cb = n2_combo_lista(82, 19, 200, 22, L_IDIOMA, 0);
        if (cb) { SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)L"Español"); SendMessageW(cb, CB_SETCURSEL, 0, 0); }
    }
    n2_lbl(8, 46, 290, 20, L"Por ahora la herramienta está sólo en español.", N2_SUAVE, N2_IZQ);
    n2_en(0xFF, 13, 718);
    n2_boton(0, 0, 304, 30, L"Personalización…", B_PERSONAL);

    /* ── Juego ── */
    n2_lienzo(0);
    n2_grupo(L"Modos", 2, 175);
    n2_chk(8, 20, 78, 20, NULL, O_AUTOCTRL, 0);
    n2_combo(88, 19, 66, 22, &g_op[O_AUTOCTRL].tecla, NULL);
    {
        static const int M[5] = { O_LOCURA, O_PIEDRA, O_NIEBLA, O_ESPEJO, O_ALEATORIO };
        for (int i = 0; i < 5; i++) {
            int y = 45 + i * 25, m = M[i], s = M[i] + 1;
            n2_chk(8, y, 78, 20, NULL, m, 0);
            n2_combo(88, y - 1, 66, 22, &g_op[m].tecla, NULL);
            n2_chk(160, y, 48, 20, L"Supr", s, 0);
            n2_combo(210, y - 1, 72, 22, &g_op[s].tecla, NULL);
        }
    }
    n2_lienzo(0);
    n2_grupo(L"Visual", 183, 140);
    {
        static const int I[5] = { O_RESULTADOS, O_CARRILES, O_NOMBRES, O_ESTR_OBST, O_GHOST };
        static const wchar_t *IT[5] = { L"Resultados rápidos", L"Obs. carriles", L"Ocultar Nombres", L"Star -> Obst", L"Efecto Ghost" };
        static const int D[4] = { O_VELOCIDAD, O_CAMARA, O_BOOSTER, O_OBST_ESTR };
        static const wchar_t *DT[4] = { L"Efecto Velocidad", L"Cámara fija", L"Efecto booster", L"Obst -> Star" };
        for (int i = 0; i < 5; i++) {
            n2_chk(8, 20 + i * 23, 140, 20, IT[i], I[i], 0);
            if (i < 4) n2_chk(152, 20 + i * 23, 132, 20, DT[i], D[i], 0);
        }
    }

    /* ── Controles ── */
    n2_lienzo(1);
    n2_grupo(L"Far", 2, 104);
    n2_chk(8, 20, 95, 20, NULL, O_FAR, 0);
    n2_chk(200, 20, 82, 20, NULL, O_AUTOFAR, 0);
    n2_slider(6, 44, 210, 24, 1);
    n2_lbl(220, 45, 62, 23, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_ht_far_n2h_txt;
    n2_lbl(8, 75, 35, 20, L"Bajar", N2_TEXTO, N2_IZQ);
    n2_combo(43, 74, 90, 22, &g_ht_tk_far_menos, NULL);
    n2_lbl(150, 75, 35, 20, L"Subir", N2_TEXTO, N2_IZQ);
    n2_combo(186, 74, 96, 22, &g_ht_tk_far_mas, NULL);
    n2_lienzo(1);
    n2_grupo(L"Obstáculos", 112, 104);
    n2_chk(8, 20, 180, 20, NULL, O_OPACIDAD, 0);
    n2_slider(6, 44, 210, 24, 0);
    n2_lbl(220, 45, 62, 23, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_n2_alfa_txt;
    n2_lbl(8, 75, 35, 20, L"Bajar", N2_TEXTO, N2_IZQ);
    n2_combo(43, 74, 90, 22, &g_ht_tk_alfa_menos, NULL);
    n2_lbl(150, 75, 35, 20, L"Subir", N2_TEXTO, N2_IZQ);
    n2_combo(186, 74, 96, 22, &g_ht_tk_alfa_mas, NULL);
    n2_lienzo(1);
    n2_grupo(L"Teclado", 222, 122);
    {
        static const POINT P[5] = { { 58, 20 }, { 14, 44 }, { 58, 44 }, { 102, 44 }, { 58, 68 } };
        static const int K[5] = { 0, 1, 2, 3, 4 };       /* W A S D LCtrl = arriba izq abajo der ctrl */
        for (int i = 0; i < 5; i++) {
            n2_tecla(P[i].x, P[i].y, 40, 21, K_KB(0, K[i]));
            n2_tecla(P[i].x + 140, P[i].y, 40, 21, K_KB(1, K[i]));
        }
    }
    n2_chk(8, 94, 270, 20, NULL, O_TECLADO, 0);

    /* ── ★ Entreno (n2h_entreno.c: el motor de práctica de Ñ2Hock, adentro) — Form1.Training.cs ── */
    n2_lienzo(2);
    n2_chk_b(6, 4, 170, 20, L"Confirmo práctica offline", &g_e.confirmo);
    n2_chk_b(196, 4, 90, 20, L"Habilitar", &g_e.habilitar);
    n2_chk_b(6, 27, 90, 20, L"Anticaída", &g_e.anticaida);
    n2_lbl(98, 28, 190, 18, NULL, N2_SUAVE, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_e_tx[NE_TX_ANTICAIDA];
    n2_lbl(6, 50, 286, 30, L"Solo entrenamiento y misiones offline; nunca en partidas puntuables.", N2_AVISO, N2_PARR);
    n2_grupo(L"Velocidad", 82, 140);
    n2_chk_b(8, 20, 150, 20, L"Activar velocidad", &g_e.vel_on);
    n2_combo(190, 19, 92, 22, &g_e.tk[E_TK_VEL], NULL);
    n2_slider(6, 48, 210, 24, 2);
    n2_lbl(220, 50, 62, 20, NULL, N2_TEXTO, N2_CEN); g_n2l[g_n2nl - 1].dyn = g_e_pct_txt;
    n2_lbl(8, 78, 274, 30, NULL, N2_AVISO, N2_PARR); g_e_lbl[NE_TX_VELOCIDAD] = g_n2nl - 1; g_n2l[g_n2nl - 1].dyn = g_e_tx[NE_TX_VELOCIDAD];
    n2_lbl(8, 111, 34, 20, L"−5 %", N2_TEXTO, N2_IZQ);
    n2_combo(44, 110, 94, 22, &g_e.tk[E_TK_MENOS], NULL);
    n2_lbl(150, 111, 34, 20, L"+5 %", N2_TEXTO, N2_IZQ);
    n2_combo(186, 110, 96, 22, &g_e.tk[E_TK_MAS], NULL);
    n2_lienzo(2);
    n2_grupo(L"Repetir un tramo", 228, 198);
    n2_chk_b(8, 20, 150, 20, L"Activar", &g_e.bucle_on);
    n2_combo(190, 19, 92, 22, &g_e.tk[E_TK_BUCLE], NULL);
    n2_lbl(8, 48, 38, 20, L"Desde", N2_TEXTO, N2_IZQ);            g_e_ed_desde = n2_edit_v(46, 47, 60, 22, g_e.desde);
    n2_lbl(120, 48, 36, 20, L"Hasta", N2_TEXTO, N2_IZQ);          g_e_ed_hasta = n2_edit_v(158, 47, 124, 22, g_e.hasta);
    n2_lbl(8, 76, 88, 20, L"Cuenta atrás (s)", N2_TEXTO, N2_IZQ); g_e_ed_cuenta = n2_edit_v(96, 75, 44, 23, g_e.cuenta);
    n2_lbl(158, 76, 76, 20, L"Sin notas (s)", N2_TEXTO, N2_IZQ);  g_e_ed_sin = n2_edit_v(236, 75, 46, 23, g_e.sin);
    n2_lbl(8, 104, 56, 20, L"Inicio (A)", N2_TEXTO, N2_IZQ);      n2_combo(64, 103, 74, 22, &g_e.tk[E_TK_A], NULL);
    n2_lbl(150, 104, 52, 20, L"Final (B)", N2_TEXTO, N2_IZQ);     n2_combo(202, 103, 80, 22, &g_e.tk[E_TK_B], NULL);
    n2_lbl(8, 132, 56, 20, L"Reiniciar", N2_TEXTO, N2_IZQ);       n2_combo(64, 131, 74, 22, &g_e.tk[E_TK_REIN], NULL);
    n2_boton(150, 130, 132, 25, L"Reiniciar tramo", B_E_REINICIAR);
    n2_lbl(8, 160, 274, 30, NULL, N2_BIEN, N2_PARR); g_e_lbl[NE_TX_BUCLE] = g_n2nl - 1; g_n2l[g_n2nl - 1].dyn = g_e_tx[NE_TX_BUCLE];
    n2_lienzo(2);
    n2_boton(2, 432, 131, 26, L"Guardar ajustes", B_E_GUARDAR);

    /* ── ★ Tramos (Form1.TrainingZones.cs / TrainingSeek.cs) ── */
    n2_lienzo(3);
    n2_grupo(L"Velocidad por tramos", 2, 336);
    n2_chk_b(8, 20, 150, 20, L"Activar tramos", &g_e.tramos_on);
    n2_combo(190, 19, 92, 22, &g_e.tk[E_TK_TRAMOS], NULL);
    n2_lbl(8, 46, 274, 30, L"Cada tramo usa su velocidad. Fuera de ellos sigue la de Entreno (o 100 %).", N2_SUAVE, N2_PARR);
    n2_lbl(30, 78, 64, 20, L"Desde", N2_TEXTO, N2_IZQ);
    n2_lbl(104, 78, 64, 20, L"Hasta", N2_TEXTO, N2_IZQ);
    n2_lbl(178, 78, 70, 20, L"Velocidad", N2_TEXTO, N2_IZQ);
    n2_boton(254, 76, 28, 22, L"»", B_E_TR_PAG);               /* ★ 26-nov: ver las filas 7–12 */
    g_e_bt_pag = g_n2c[g_n2n - 1].h;
    {
        for (int i = 0; i < 6; i++) { n2_lbl(6, 101 + i * 28, 20, 20, NULL, N2_TEXTO, N2_CEN); g_n2l[g_n2nl - 1].dyn = g_e_num[i]; }
        for (int i = 0; i < N2_TRAMOS; i++) {
            int y = 100 + (i % 6) * 28;
            g_e_ed_tde[i] = n2_edit_v(30, y, 64, 22, g_e.tde[i]);
            g_e_ed_tha[i] = n2_edit_v(104, y, 64, 22, g_e.tha[i]);
            g_e_cb_tvel[i] = n2_combo_lista(178, y, 70, 22, L_TRAMO_VEL, 0);
            for (int p = 50; g_e_cb_tvel[i] && p <= 150; p += 5) {
                wchar_t t[12]; wsprintfW(t, L"%d %%", p);
                SendMessageW(g_e_cb_tvel[i], CB_ADDSTRING, 0, (LPARAM)t);
            }
            if (g_e_cb_tvel[i]) SendMessageW(g_e_cb_tvel[i], CB_SETCURSEL, (WPARAM)((g_e.tvel[i] - 50) / 5), 0);
            n2_boton(254, y - 1, 28, 24, L"✕", B_E_BORRAR0 + i);
            g_e_bt_tx[i] = g_n2c[g_n2n - 1].h;
            if (i >= 6) {                                          /* las filas 7–12 empiezan escondidas */
                HWND hs[4] = { g_e_ed_tde[i], g_e_ed_tha[i], g_e_cb_tvel[i], g_e_bt_tx[i] };
                for (int k = 0; k < 4; k++) if (hs[k]) ShowWindow(hs[k], SW_HIDE);
            }
        }
    }
    n2_lbl(8, 271, 80, 20, L"Marcar punto", N2_TEXTO, N2_IZQ);
    n2_combo(90, 270, 92, 22, &g_e.tk[E_TK_MARCA], NULL);
    n2_boton(190, 269, 92, 25, L"Borrar todo", B_E_BORRAR_TODO);
    n2_lbl(8, 300, 274, 30, NULL, N2_BIEN, N2_PARR); g_e_lbl[NE_TX_TRAMOS] = g_n2nl - 1; g_n2l[g_n2nl - 1].dyn = g_e_tx[NE_TX_TRAMOS];
    n2_lienzo(3);
    n2_grupo(L"Moverse en la canción", 342, 104);
    {
        static const wchar_t *T[4] = { L"« 5 s", L"‹ 1 s", L"1 s ›", L"5 s »" };
        for (int i = 0; i < 4; i++) {
            n2_boton(8 + i * 69, 18, 64, 25, T[i], B_E_MOVER0 + i);
            n2_combo(8 + i * 69, 47, 64, 22, &g_e.tk[E_TK_MOVER0 + i], NULL);
        }
    }
    n2_lbl(8, 72, 274, 30, NULL, N2_SUAVE, N2_PARR); g_e_lbl[NE_TX_MOVER] = g_n2nl - 1; g_n2l[g_n2nl - 1].dyn = g_e_tx[NE_TX_MOVER];
    n2_lienzo(3);
    n2_boton(2, 452, 131, 26, L"Guardar ajustes", B_E_GUARDAR);
    n2_boton(139, 452, 155, 26, L"Mapa de la canción…", B_E_MAPA);

    /* ── Chat ── */
    /* ★ 19-nov: el Chat de verdad (n2h_chat.c: lee el chat del juego, sólo lectura) */
    n2_lienzo(4);
    n2_chk_b(4, 4, 286, 20, L"Conservar últimas 10 entradas", &g_n2_chat_diez);
    n2_lbl(4, 28, 286, 18, L"Canal", N2_TEXTO, N2_ABAJO);
    g_n2_chat_canal = n2_combo_lista(4, 47, 286, 22, L_CANAL, 0);
    n2_lbl(4, 74, 286, 18, L"Texto del juego", N2_TEXTO, N2_ABAJO);
    {
        HWND cb = n2_combo_lista(4, 93, 286, 22, L_COD, 0);
        const wchar_t *nom[16];
        int n = nc_codificaciones(nom, 16);
        for (int i = 0; cb && i < n; i++) SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)nom[i]);
        if (g_n2_chat_cod < 0 || g_n2_chat_cod >= n) g_n2_chat_cod = 0;
        if (cb) SendMessageW(cb, CB_SETCURSEL, (WPARAM)g_n2_chat_cod, 0);
        nc_elegir_codificacion(g_n2_chat_cod);
    }
    n2_lbl(4, 119, 286, 30, NULL, N2_TEXTO, N2_PARR); g_n2_chat_lbl = g_n2nl - 1; g_n2l[g_n2_chat_lbl].dyn = g_n2_chat_estado;
    n2_lista(4, 152, 286, 174);
    g_n2_chat_lista = g_n2c[g_n2n - 1].h;
    n2_chk_b(4, 330, 286, 20, L"Ver el chat dentro del juego", &g_n2_chat_en_juego);
    n2_chk_b(22, 352, 160, 22, L"Solo durante la carrera", &g_n2_chat_solo);
    n2_boton(196, 351, 94, 24, L"Mover", B_NADA);
    n2_chk_b(4, 378, 286, 20, L"Ver el % de velocidad dentro del juego", &g_n2_vel_en_juego);
    n2_boton(4, 408, 140, 26, L"Vaciar historial", B_CHAT_VACIAR);
    nc_conservar_diez(g_n2_chat_diez);
    nc_en_juego(g_n2_chat_en_juego, g_n2_chat_solo);
    n2_lbl(4, 438, 286, 58, L"Incluye las entradas enviadas y recibidas que muestra el juego. Un mensaje largo puede ocupar "
                            L"varias líneas. Solo se leen, se conservan durante esta sesión y no se guardan en ningún archivo.",
           N2_SUAVE, N2_PARR);
}

/* ── el estado: lo que cambió por un atajo, el ini o el launcher ──────────── */
static void n2_textos(void)
{
    wsprintfW(g_n2_velo_txt, L"%d %%", g_n2_velo);
    wsprintfW(g_n2_opac_txt, L"%d %%", g_n2_opac);
    wsprintfW(g_n2_tam_txt, L"%d", g_n2i.tam);
    wsprintfW(g_n2_dura_txt, L"%d.%d s", g_n2i.dura / 1000, g_n2i.dura / 100 % 10);
    if (g_op[O_AUTOFAR].quiere) lstrcpyW(g_ht_far_n2h_txt, L"auto");
    else { int d = g_ht_far_n2h * 5; wsprintfW(g_ht_far_n2h_txt, L"%d.%d", d / 10, d % 10); }
    wsprintfW(g_n2_alfa_txt, L"%d", g_ht_alfa_nivel);
}

static void n2_estado(wchar_t *s)                     /* s: 320 */
{
    static const wchar_t *PAG[N2_PAGS] = { NULL, NULL, L"Entreno: velocidad y repetición nativas",
                                           L"Tramos: la velocidad cambia sola en cada tramo",
                                           L"Chat: historial de esta sesión, solo lectura" };
    wchar_t n[32];
    if (g_ht_aviso[0]) { lstrcpyW(s, g_ht_aviso); return; }
    if (g_ht_pag >= 0 && g_ht_pag < N2_PAGS && PAG[g_ht_pag]) { lstrcpyW(s, PAG[g_ht_pag]); return; }
    ht_nombre_vk(g_ht_tecla_ver, n);
    if (g_ht_apagada) wsprintfW(s, L"Parches restaurados · desconectado · %s mostrar / ocultar", n);
    else wsprintfW(s, L"Conectado · %s mostrar / ocultar", n);
}

static void n2_sincronizar(void)
{
    n2_textos();
    for (int i = 0; i < g_n2n; i++) {
        N2_CTL *c = &g_n2c[i];
        if (!c->h) continue;
        if (c->tipo == C_COMBO && c->pvk) n2_combo_elegir(c->h, *c->pvk);
        else if (c->tipo == C_CHK || c->tipo == C_TECLA || c->tipo == C_SLIDER) InvalidateRect(c->h, NULL, FALSE);
    }
    for (int p = 0; p < N2_PAGS_TOT; p++) if (g_n2_pag[p]) InvalidateRect(g_n2_pag[p], NULL, FALSE);
    if (g_n2_vista) InvalidateRect(g_n2_vista, NULL, FALSE);
    if (g_ht_ven) {
        RECT r = { 11 + 4, 11 + 57, 11 + 4 + 288, 11 + 57 + 20 };
        InvalidateRect(g_ht_ven, &r, TRUE);
    }
}

/* ── pintar ───────────────────────────────────────────────────────────────── */
static void n2_texto(HDC dc, const RECT *r, const wchar_t *t, HFONT f, COLORREF c, UINT fmt)
{
    RECT q = *r;
    SelectObject(dc, f);
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, c);
    DrawTextW(dc, t, -1, &q, fmt);
}

static void n2_rect(HDC dc, const RECT *r, COLORREF fondo, COLORREF borde)
{
    HBRUSH b = CreateSolidBrush(fondo);
    HPEN p = CreatePen(PS_SOLID, 1, borde);
    HGDIOBJ ob = SelectObject(dc, b), op = SelectObject(dc, p);
    Rectangle(dc, r->left, r->top, r->right, r->bottom);
    SelectObject(dc, ob); SelectObject(dc, op);
    DeleteObject(b); DeleteObject(p);
}

static void n2_linea(HDC dc, int x0, int y0, int x1, int y1, COLORREF c)
{
    HPEN p = CreatePen(PS_SOLID, 1, c);
    HGDIOBJ op = SelectObject(dc, p);
    MoveToEx(dc, x0, y0, NULL); LineTo(dc, x1, y1);
    SelectObject(dc, op); DeleteObject(p);
}

/* la tarjeta translúcida debajo de un recuadro (FillCard de Ñ2Hock: radio 12, Card con alfa 200) */
static void n2_tarjeta(HDC dc, const RECT *r)
{
    int w = r->right - r->left, h = r->bottom - r->top;
    if (w <= 0 || h <= 0) return;
    HDC m = CreateCompatibleDC(dc);
    HBITMAP b = CreateCompatibleBitmap(dc, w, h);
    HGDIOBJ ob = SelectObject(m, b);
    RECT q = { 0, 0, w, h };
    HBRUSH br = CreateSolidBrush(N2_VENTANA); FillRect(m, &q, br); DeleteObject(br);
    HRGN rg = CreateRoundRectRgn(r->left, r->top, r->right + 1, r->bottom + 1, 12, 12);
    SelectClipRgn(dc, rg);
    BLENDFUNCTION bf = { AC_SRC_OVER, 0, 200, 0 };
    GdiAlphaBlend(dc, r->left, r->top, w, h, m, 0, 0, w, h, bf);
    SelectClipRgn(dc, NULL); DeleteObject(rg);
    SelectObject(m, ob); DeleteObject(b); DeleteDC(m);
}

/* lo que pinta una página (o la ventana, pag = 0xFF): fondo, recuadros, textos, marcos de las cajas */
static void n2_pintar_pag(HDC dc, BYTE pag, const RECT *todo, HWND h)
{
    if (g_n2_fondo_dc && (pag == 0xFF || pag < N2_PAGS)) {          /* la imagen de fondo, con su velo */
        POINT o = { 0, 0 };
        if (pag != 0xFF) MapWindowPoints(h, g_ht_ven, &o, 1);
        BitBlt(dc, 0, 0, todo->right, todo->bottom, g_n2_fondo_dc, o.x, o.y, SRCCOPY);
        for (int i = 0; i < g_n2ng; i++) if (g_n2g[i].pag == pag) n2_tarjeta(dc, &g_n2g[i].r);
    } else FillRect(dc, todo, pag == 0xFF ? g_n2_br_ven : g_n2_br_pag);
    for (int i = 0; i < g_n2ng; i++) {
        N2_GRP *g = &g_n2g[i];
        if (g->pag != pag) continue;
        SIZE tz;
        SelectObject(dc, g_n2_fb);
        GetTextExtentPoint32W(dc, g->t, lstrlenW(g->t), &tz);
        int ym = g->r.top + tz.cy / 2, xt = g->r.left + 8;
        n2_linea(dc, g->r.left, ym, xt - 2, ym, N2_MARCO);
        n2_linea(dc, xt + tz.cx + 2, ym, g->r.right - 1, ym, N2_MARCO);
        n2_linea(dc, g->r.left, ym, g->r.left, g->r.bottom - 1, N2_MARCO);
        n2_linea(dc, g->r.right - 1, ym, g->r.right - 1, g->r.bottom - 1, N2_MARCO);
        n2_linea(dc, g->r.left, g->r.bottom - 1, g->r.right, g->r.bottom - 1, N2_MARCO);
        RECT rt = { xt, g->r.top, xt + tz.cx + 1, g->r.top + tz.cy };
        n2_texto(dc, &rt, g->t, g_n2_fb, N2_ACENTO, DT_LEFT | DT_TOP | DT_SINGLELINE | DT_NOPREFIX);
    }
    for (int i = 0; i < g_n2nl; i++) {
        N2_LBL *l = &g_n2l[i];
        if (l->pag == pag) n2_texto(dc, &l->r, l->dyn ? l->dyn : l->t, g_n2_f,
                                    i == g_n2_chat_lbl ? g_n2_chat_estado_c : n2_e_color(i, l->c), l->fmt);
    }
    for (int i = 0; i < g_n2n; i++) {
        N2_CTL *c = &g_n2c[i];
        if (c->pag == pag && (c->tipo == C_EDIT || c->tipo == C_LISTA)) n2_rect(dc, &c->r, N2_CAJA, N2_MARCO);
    }
    if (pag == 0xFF) {
        wchar_t s[320];
        RECT r = { 11 + 4, 11 + 57 + 6, 11 + 4 + 288, 11 + 57 + 20 };
        n2_estado(s);
        n2_texto(dc, &r, s, g_n2_fchico, N2_TEXTO, DT_LEFT | DT_TOP | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS);
    }
}

/* pinta la página entera en su caché (el fondo de sus controles) y la pasa a la pantalla */
static void n2_pintar_cache(HWND h, HDC dc, BYTE pag)
{
    int k = pag == 0xFF ? N2_PAGS_TOT : pag;
    RECT r; GetClientRect(h, &r);
    if (!g_n2_cache_dc[k] || g_n2_cache_w[k] != r.right || g_n2_cache_h[k] != r.bottom) {
        if (g_n2_cache_dc[k]) { DeleteDC(g_n2_cache_dc[k]); DeleteObject(g_n2_cache_bm[k]); }
        g_n2_cache_dc[k] = CreateCompatibleDC(dc);
        g_n2_cache_bm[k] = CreateCompatibleBitmap(dc, r.right > 0 ? r.right : 1, r.bottom > 0 ? r.bottom : 1);
        SelectObject(g_n2_cache_dc[k], g_n2_cache_bm[k]);
        g_n2_cache_w[k] = r.right; g_n2_cache_h[k] = r.bottom;
    }
    n2_pintar_pag(g_n2_cache_dc[k], pag, &r, h);
    BitBlt(dc, 0, 0, r.right, r.bottom, g_n2_cache_dc[k], 0, 0, SRCCOPY);
}

static int n2_vivo(int ref)
{
    return ref >= 0 && ref < O_N && g_op[ref].permitida && !g_op[ref].rota;
}

static void n2_nombre_dik(int dik, wchar_t *s)             /* como Ñ2Hock: W, UP, LCTRL… */
{
    int vk = ht_dik_a_vk(dik);
    switch (vk) {
    case VK_UP: lstrcpyW(s, L"UP"); return;       case VK_DOWN: lstrcpyW(s, L"DOWN"); return;
    case VK_LEFT: lstrcpyW(s, L"LEFT"); return;   case VK_RIGHT: lstrcpyW(s, L"RIGHT"); return;
    case VK_LCONTROL: lstrcpyW(s, L"LCTRL"); return; case VK_RCONTROL: lstrcpyW(s, L"RCTRL"); return;
    case VK_LSHIFT: lstrcpyW(s, L"LSHIFT"); return;  case VK_RSHIFT: lstrcpyW(s, L"RSHIFT"); return;
    }
    if (!dik) { s[0] = 0; return; }
    ht_nombre_dik(dik, s);
    CharUpperW(s);
}

/* el fondo de un control pintado por nosotros: lo que pintó su página ahí (imagen, velo, recuadro) */
static void n2_fondo_de(HDC dc, const N2_CTL *c, const RECT *r)
{
    int k = c->pag == 0xFF ? N2_PAGS_TOT : c->pag;
    if (k >= 0 && k <= N2_PAGS_TOT && g_n2_cache_dc[k]) {
        BitBlt(dc, r->left, r->top, r->right - r->left, r->bottom - r->top, g_n2_cache_dc[k], c->r.left + r->left, c->r.top + r->top, SRCCOPY);
        return;
    }
    FillRect(dc, r, c->pag == 0xFF ? g_n2_br_ven : g_n2_br_pag);
}

static void n2_dibujar(const DRAWITEMSTRUCT *d)
{
    int i = (int)d->CtlID - 1000;
    if (i < 0 || i >= g_n2n) return;
    N2_CTL *c = &g_n2c[i];
    HDC dc = d->hDC;
    RECT r = d->rcItem;
    n2_fondo_de(dc, c, &r);
    if (c->tipo == C_TECLA) {
        wchar_t n[32];
        int *p = ht_tecla_de(c->ref);
        n2_rect(dc, &r, g_ht_esperando == c->ref ? N2_CAJA_ACT : N2_CAJA, N2_MARCO);
        if (g_ht_esperando == c->ref) lstrcpyW(n, L"…");
        else n2_nombre_dik(p ? *p : 0, n);
        n2_texto(dc, &r, n, g_n2_f, N2_TEXTO, N2_CEN);
        return;
    }
    /* la casilla: 13 x 13, como la de WinForms oscuro */
    int vivo = c->pbool ? 1 : c->ref >= 0 ? n2_vivo(c->ref) : 0;
    int on = c->pbool ? *c->pbool : c->ref >= 0 ? g_op[c->ref].quiere : c->falso;
    int y = r.top + (r.bottom - r.top - 13) / 2;
    RECT b = { r.left + 1, y, r.left + 14, y + 13 };
    HBRUSH br = CreateSolidBrush(on ? (vivo || c->ref < 0 && on ? N2_TILDE : N2_APAGADO) : N2_PAGINA);
    HPEN pe = CreatePen(PS_SOLID, 1, on ? (vivo || c->ref < 0 ? N2_TILDE : N2_APAGADO) : (vivo ? RGB(160, 160, 170) : N2_APAGADO));
    HGDIOBJ ob = SelectObject(dc, br), op = SelectObject(dc, pe);
    RoundRect(dc, b.left, b.top, b.right, b.bottom, 4, 4);
    SelectObject(dc, ob); SelectObject(dc, op); DeleteObject(br); DeleteObject(pe);
    if (on) {
        HPEN t = CreatePen(PS_SOLID, 2, RGB(255, 255, 255));
        op = SelectObject(dc, t);
        MoveToEx(dc, b.left + 3, b.top + 6, NULL);
        LineTo(dc, b.left + 5, b.top + 9);
        LineTo(dc, b.left + 10, b.top + 3);
        SelectObject(dc, op); DeleteObject(t);
    }
    RECT rt = { r.left + 18, r.top, r.right, r.bottom };
    {
        wchar_t t[128];
        GetWindowTextW(d->hwndItem, t, 128);
        n2_texto(dc, &rt, t, g_n2_f, vivo || (c->ref < 0 && on) ? N2_TEXTO : N2_GRIS_TX, N2_IZQ | DT_END_ELLIPSIS);
    }
}

/* ── la barra (FlatSlider.cs) ─────────────────────────────────────────────── */
static void n2_slider_rango(int ref, int *mn, int *mx, int *v)
{
    if (ref == 0) { *mn = 1; *mx = 15; *v = g_ht_alfa_nivel; }
    else if (ref == 1) { *mn = 2; *mx = 44; *v = g_ht_far_n2h; }
    else if (ref == 3) { *mn = 0; *mx = 90; *v = g_n2_velo; }
    else if (ref == 4) { *mn = 60; *mx = 100; *v = g_n2_opac; }
    else if (ref == 5) { *mn = 16; *mx = 120; *v = g_n2i.tam; }
    else if (ref == 6) { *mn = 3; *mx = 50; *v = g_n2i.dura / 100; }
    else { *mn = 50; *mx = 150; *v = g_e.vel_pct; }
}
static void n2_fondo_componer(void);
static void n2_opacidad_aplicar(void);
static void n2_e_textos(void);
static void n2_todo_repintar(void);

static void n2_slider_poner(int ref, int v)
{
    int mn, mx, ant;
    n2_slider_rango(ref, &mn, &mx, &ant);
    if (v < mn) v = mn;
    if (v > mx) v = mx;
    if (v == ant) return;
    if (ref == 0) { g_ht_alfa_nivel = v; ht_alfa_aplicar(); }
    else if (ref == 1) { g_ht_far_n2h = v; ht_far_aplicar(); }
    else if (ref == 3) { g_n2_velo = v; n2_fondo_componer(); n2_todo_repintar(); }
    else if (ref == 4) { g_n2_opac = v; n2_opacidad_aplicar(); }
    else if (ref == 5) { g_n2i.tam = v; }
    else if (ref == 6) { g_n2i.dura = v * 100; }
    else if (ref == 2) { g_e.vel_pct = (v + 2) / 5 * 5; ne_velocidad_poner(g_e.vel_pct); n2_e_textos(); }
    else return;
    ht_refrescar();
    ht_pedir_guardar();
}

static LRESULT CALLBACK n2_slider_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    int ref = (int)GetWindowLongPtrW(h, GWLP_USERDATA);
    switch (m) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc0 = BeginPaint(h, &ps);
        RECT r; GetClientRect(h, &r);
        int W = r.right, H = r.bottom;
        /* al doble y achicado: bordes suaves sin GDI+ */
        HDC dc = CreateCompatibleDC(dc0);
        HBITMAP bm = CreateCompatibleBitmap(dc0, W * 2, H * 2);
        HGDIOBJ obm = SelectObject(dc, bm);
        RECT r2 = { 0, 0, W * 2, H * 2 };
        {   /* el fondo: lo que pintó la página debajo (al doble) */
            int i = GetDlgCtrlID(h) - 1000;
            int k = (i >= 0 && i < g_n2n) ? (g_n2c[i].pag == 0xFF ? N2_PAGS_TOT : g_n2c[i].pag) : -1;
            if (k >= 0 && g_n2_cache_dc[k]) {
                SetStretchBltMode(dc, COLORONCOLOR);
                StretchBlt(dc, 0, 0, W * 2, H * 2, g_n2_cache_dc[k], g_n2c[i].r.left, g_n2c[i].r.top, W, H, SRCCOPY);
            } else FillRect(dc, &r2, g_n2_br_pag);
        }
        int mn, mx, v;
        n2_slider_rango(ref, &mn, &mx, &v);
        int vivo = ref == 0 ? n2_vivo(O_OPACIDAD) : ref == 1 ? n2_vivo(O_FAR) : ref >= 2;
        COLORREF ac = vivo ? N2_ACENTO : N2_APAGADO;
        const int T = 16;
        float cx = T / 2.0f + (mx == mn ? 0 : (float)(v - mn) / (mx - mn) * (W - T));
        int y0 = H - 4, rx0 = T, rx1 = (W - T / 2) * 2;           /* coordenadas al doble */
        HPEN np = (HPEN)GetStockObject(NULL_PEN);
        HGDIOBJ op = SelectObject(dc, np);
        HBRUSH b = CreateSolidBrush(N2_RIEL); HGDIOBJ ob = SelectObject(dc, b);
        RoundRect(dc, rx0, y0, rx1, y0 + 8, 8, 8);
        SelectObject(dc, ob); DeleteObject(b);
        b = CreateSolidBrush(ac); ob = SelectObject(dc, b);
        if ((int)(cx * 2) > rx0) RoundRect(dc, rx0, y0, (int)(cx * 2), y0 + 8, 8, 8);
        SelectObject(dc, ob); DeleteObject(b);
        HPEN pp = CreatePen(PS_SOLID, 4, ac);
        SelectObject(dc, pp);
        b = CreateSolidBrush(N2_PERILLA); ob = SelectObject(dc, b);
        int k0 = (int)((cx - T / 2.0f + 1) * 2) + 2, kt = H - T + 2 + 2;
        Ellipse(dc, k0, kt, k0 + (T - 2) * 2 - 4, kt + (T - 2) * 2 - 4);
        SelectObject(dc, ob); DeleteObject(b);
        SelectObject(dc, op); DeleteObject(pp);
        SetStretchBltMode(dc0, HALFTONE);
        SetBrushOrgEx(dc0, 0, 0, NULL);
        StretchBlt(dc0, 0, 0, W, H, dc, 0, 0, W * 2, H * 2, SRCCOPY);
        SelectObject(dc, obm); DeleteObject(bm); DeleteDC(dc);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_LBUTTONDOWN: case WM_MOUSEMOVE: {
        if (m == WM_MOUSEMOVE && GetCapture() != h) return 0;
        if (m == WM_LBUTTONDOWN) { SetCapture(h); g_n2_arrastre = 1; }
        RECT r; GetClientRect(h, &r);
        int mn, mx, v, x = (short)LOWORD(lp), T = 16;
        n2_slider_rango(ref, &mn, &mx, &v);
        if (r.right <= T) return 0;
        float q = (float)(x - T / 2) / (float)(r.right - T);
        if (q < 0) q = 0;
        if (q > 1) q = 1;
        n2_slider_poner(ref, mn + (int)(q * (mx - mn) + 0.5f));
        return 0;
    }
    case WM_LBUTTONUP:
        if (GetCapture() == h) ReleaseCapture();
        g_n2_arrastre = 0;
        return 0;
    case WM_MOUSEWHEEL: {
        int mn, mx, v;
        n2_slider_rango(ref, &mn, &mx, &v);
        n2_slider_poner(ref, v + (GET_WHEEL_DELTA_WPARAM(wp) > 0 ? 1 : -1));
        return 0;
    }
    case WM_SETCURSOR:
        SetCursor(LoadCursorW(NULL, (LPCWSTR)IDC_HAND));
        return TRUE;
    }
    return DefWindowProcW(h, m, wp, lp);
}

/* ── lo común de la ventana y de las páginas: colores de los controles, casillas, clics ── */
static void n2_menu_personal(HWND h)
{
    HMENU m = CreatePopupMenu();
    if (!m) return;
    AppendMenuW(m, MF_STRING | (g_op[O_FAR_IND].quiere ? MF_CHECKED : 0), 1, L"Indicador Far (en la carrera)");
    AppendMenuW(m, MF_SEPARATOR, 0, NULL);
    AppendMenuW(m, MF_STRING, 2, L"Teclado de fábrica");
    AppendMenuW(m, MF_STRING, 3, L"Apagar todo");
    POINT p; GetCursorPos(&p);
    int r = (int)TrackPopupMenu(m, TPM_RETURNCMD | TPM_RIGHTBUTTON, p.x, p.y, 0, h, NULL);
    DestroyMenu(m);
    if (r == 1) ht_cambiar(O_FAR_IND, !g_op[O_FAR_IND].quiere);
    else if (r == 2) { ht_teclado_de_fabrica(); ht_refrescar(); }
    else if (r == 3) { ht_apagar_todo(); ht_avisar(0, 3000, L"Todo apagado: el juego quedó de fábrica"); }
}

static int n2_comun(HWND h, UINT m, WPARAM wp, LPARAM lp, LRESULT *res)
{
    (void)h;
    switch (m) {
    case WM_CTLCOLOREDIT: case WM_CTLCOLORLISTBOX:
        SetTextColor((HDC)wp, N2_TEXTO); SetBkColor((HDC)wp, N2_CAJA);
        *res = (LRESULT)g_n2_br_caja; return 1;
    case WM_CTLCOLORSTATIC:                            /* las cajas apagadas */
        SetTextColor((HDC)wp, N2_GRIS_TX); SetBkColor((HDC)wp, N2_CAJA);
        *res = (LRESULT)g_n2_br_caja; return 1;
    case WM_CTLCOLORBTN:
        *res = (LRESULT)(h == g_ht_ven ? g_n2_br_ven : g_n2_br_pag); return 1;
    case WM_DRAWITEM: {
        const DRAWITEMSTRUCT *d = (const DRAWITEMSTRUCT *)lp;
        if (d->CtlType == ODT_LISTBOX) {                /* una línea del chat, con su color */
            FillRect(d->hDC, &d->rcItem, g_n2_br_caja);
            if ((int)d->itemID >= 0) {
                wchar_t t[512];
                LRESULT n = SendMessageW(d->hwndItem, LB_GETTEXTLEN, d->itemID, 0);
                if (n >= 0 && n < 512) {
                    SendMessageW(d->hwndItem, LB_GETTEXT, d->itemID, (LPARAM)t);
                    RECT r = d->rcItem; r.left += 2;
                    n2_texto(d->hDC, &r, t, g_n2_f, nc_color_legible((COLORREF)d->itemData, N2_CAJA, N2_TEXTO), N2_IZQ);
                }
            }
        } else n2_dibujar(d);
        *res = TRUE; return 1;
    }
    case WM_MEASUREITEM:
        ((MEASUREITEMSTRUCT *)lp)->itemHeight = 15;
        *res = TRUE; return 1;
    case WM_COMMAND: {
        int i = (int)LOWORD(wp) - 1000, code = HIWORD(wp);
        if (i < 0 || i >= g_n2n) return 0;
        N2_CTL *c = &g_n2c[i];
        if (c->tipo == C_CHK && (code == BN_CLICKED || code == BN_DOUBLECLICKED)) {
            if (c->pbool) {
                *c->pbool = !*c->pbool; InvalidateRect(c->h, NULL, FALSE); ht_pedir_guardar(); n2_sincronizar();
                if (c->pbool == &g_n2_chat_diez) nc_conservar_diez(g_n2_chat_diez);
                n2_e_cambio(c->pbool);
                if (c->pbool == &g_n2_chat_en_juego || c->pbool == &g_n2_chat_solo) nc_en_juego(g_n2_chat_en_juego, g_n2_chat_solo);
            }
            else if (c->ref >= 0) ht_cambiar(c->ref, !g_op[c->ref].quiere);
        } else if (c->tipo == C_TECLA && (code == BN_CLICKED || code == BN_DOUBLECLICKED)) {
            wchar_t que[64];
            if (g_ht_esperando == c->ref) ht_cancelar_espera(L"Cancelado");
            else {
                g_ht_esperando = c->ref;
                ht_que_es(c->ref, que);
                ht_avisar(0, 0, L"Pulsa la tecla para «%s» · Esc cancela", que);
            }
            SetFocus(g_ht_ven);
            n2_sincronizar();
        } else if (c->tipo == C_COMBO && code == CBN_SELCHANGE && !c->pvk) {
            n2_lista_cambio(c->ref, c->h);
        } else if (c->tipo == C_COMBO && code == CBN_SELCHANGE && c->pvk) {
            int k = (int)SendMessageW(c->h, CB_GETCURSEL, 0, 0);
            int vk = k >= 0 ? (int)SendMessageW(c->h, CB_GETITEMDATA, (WPARAM)k, 0) : 0;
            if (c->pvk == &g_ht_tecla_ver && !vk) { vk = VK_F12; n2_combo_elegir(c->h, vk); }   /* la ventana siempre tiene tecla */
            *c->pvk = vk;
            if (vk > 0 && vk < 256) g_ht_antes[vk] = 1;    /* que no se dispare sola */
            ht_pedir_guardar();
        } else if (c->tipo == C_BOTON && code == BN_CLICKED) {
            if (c->ref == B_CONECTAR || c->ref == B_RESTAURAR) {
                g_ht_apagada = c->ref == B_RESTAURAR;
                if (g_ht_apagada) { ne_apagar_todo(); g_e.habilitar = g_e.anticaida = g_e.vel_on = g_e.bucle_on = g_e.tramos_on = 0; }
                for (int k = 0; k < O_N; k++) ht_aplicar(k);
                ht_avisar(0, 3000, g_ht_apagada ? L"Parches restaurados · desconectado" : L"Conectado: opciones aplicadas");
                ht_refrescar();
            } else if (c->ref == B_PERSONAL) n2_per_abrir();
            else n2_per_comando(c->ref);
        }
        *res = 0; return 1;
    }
    }
    return 0;
}

static LRESULT CALLBACK n2_pag_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    LRESULT res;
    if (n2_comun(h, m, wp, lp, &res)) return res;
    switch (m) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        BYTE p = (BYTE)GetWindowLongPtrW(h, GWLP_USERDATA);
        n2_pintar_cache(h, dc, p);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_LBUTTONDOWN:
        if (g_ht_esperando >= 0) ht_cancelar_espera(L"Cancelado: queda la tecla que estaba");
        return 0;
    }
    return DefWindowProcW(h, m, wp, lp);
}

static void n2_ver_pag(int p)
{
    if (p < 0 || p >= N2_PAGS) p = 0;
    g_ht_pag = p;
    for (int i = 0; i < N2_PAGS; i++) if (g_n2_pag[i]) ShowWindow(g_n2_pag[i], i == p ? SW_SHOW : SW_HIDE);
    n2_sincronizar();
}

static LRESULT CALLBACK n2_wndproc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    LRESULT res;
    if (n2_comun(h, m, wp, lp, &res)) return res;
    switch (m) {
    case WM_ERASEBKGND: {
        RECT r; GetClientRect(h, &r);
        FillRect((HDC)wp, &r, g_n2_br_ven);
        return 1;
    }
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        n2_pintar_cache(h, dc, 0xFF);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_PRINTCLIENT: {
        RECT r; GetClientRect(h, &r);
        FillRect((HDC)wp, &r, g_n2_br_ven);
        return 0;
    }
    case WM_NOTIFY: {
        const NMHDR *n = (const NMHDR *)lp;
        if (n->hwndFrom == g_n2_tabs && n->code == TCN_SELCHANGE)
            n2_ver_pag((int)SendMessageW(g_n2_tabs, TCM_GETCURSEL, 0, 0));
        return 0;
    }
    case WM_N2H_SYNC_:
        n2_sincronizar();
        return 0;
    case WM_LBUTTONDOWN:
        if (g_ht_esperando >= 0) ht_cancelar_espera(L"Cancelado: queda la tecla que estaba");
        return 0;
    case WM_KEYDOWN: case WM_SYSKEYDOWN:
        if (g_ht_esperando >= 0) {
            ht_tecla_apretada((int)wp, (int)((lp >> 16) & 0xFF), (int)((lp >> 24) & 1));
            n2_sincronizar();
            return 0;
        }
        break;
    case WM_CHAR: case WM_SYSCHAR:
        if (g_ht_esperando >= 0) return 0;
        break;
    case WM_ACTIVATE:
        if (LOWORD(wp) == WA_INACTIVE) ht_cancelar_espera(NULL);
        break;
    case WM_TIMER:
        ht_tick();
        n2_apodo_tick();
        n2_chat_tick();
        n2_capa_tick();
        n2_e_tick();
        return 0;
    case WM_HT_MOSTRAR:
        g_ht_apagada = 0;
        for (int i = 0; i < O_N; i++) ht_aplicar(i);
        ht_mostrar(1);
        n2_sincronizar();
        return 0;
    case WM_HT_APAGAR:
        g_ht_apagada = 1;
        ne_apagar_todo();
        for (int i = 0; i < O_N; i++) ht_aplicar(i);
        ht_mostrar(0);
        apuntar("  [tool] apagada desde el launcher: parches sacados, ventana oculta");
        return 0;
    case WM_EXITSIZEMOVE:
        ht_pedir_guardar();
        return 0;
    case WM_CLOSE:
        ht_mostrar(0);                              /* la X esconde; F12 la vuelve a mostrar */
        return 0;
    }
    return DefWindowProcW(h, m, wp, lp);
}

/* ═══ ★ PERSONALIZACIÓN · Ñ2Hock (19-nov) — Form1.Personalization.cs / Form1.Appearance.cs / FarIndicatorEditor.cs ═══
 *   Una ventana aparte (368 x 580) con las pestañas Ventana, Far e Idioma, como la de Ñ2Hock.
 *   ⚠ «En el juego» (instalar su dinput8) no va: la dll YA está dentro del juego.
 *   Se guarda todo en [herramienta] (n2_*, far_ind_*, tecla) por ht_guardar → g_ht_guardar_mas. */

static void n2_todo_repintar(void)
{
    if (g_ht_ven) InvalidateRect(g_ht_ven, NULL, TRUE);
    for (int p = 0; p < N2_PAGS_TOT; p++) if (g_n2_pag[p]) InvalidateRect(g_n2_pag[p], NULL, TRUE);
    for (int i = 0; i < g_n2n; i++) if (g_n2c[i].h) InvalidateRect(g_n2c[i].h, NULL, TRUE);
    if (g_n2_vista) InvalidateRect(g_n2_vista, NULL, FALSE);
}

/* la letra (8.25 / 7.5 pt) de la familia elegida, en todos los controles */
static void n2_fuentes_crear(void)
{
    HFONT v[4] = { g_n2_f, g_n2_fb, g_n2_fchico, g_n2_ftab };
    g_n2_f      = CreateFontW(-11, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, g_n2_letra);
    g_n2_fb     = CreateFontW(-11, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, g_n2_letra);
    g_n2_fchico = CreateFontW(-10, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, g_n2_letra);
    g_n2_ftab   = CreateFontW(-10, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, g_n2_letra);
    for (int i = 0; i < g_n2n; i++) if (g_n2c[i].h) SendMessageW(g_n2c[i].h, WM_SETFONT, (WPARAM)g_n2_f, TRUE);
    if (g_n2_tabs) SendMessageW(g_n2_tabs, WM_SETFONT, (WPARAM)g_n2_ftab, TRUE);
    if (g_n2_per_tabs) SendMessageW(g_n2_per_tabs, WM_SETFONT, (WPARAM)g_n2_ftab, TRUE);
    for (int i = 0; i < 4; i++) if (v[i]) DeleteObject(v[i]);
    n2_todo_repintar();
}

/* la transparencia de toda la ventana (60..100 %) */
static void n2_opacidad_aplicar(void)
{
    if (!g_ht_ven) return;
    LONG ex = GetWindowLongW(g_ht_ven, GWL_EXSTYLE);
    if (g_n2_opac >= 100) { if (ex & WS_EX_LAYERED) SetWindowLongW(g_ht_ven, GWL_EXSTYLE, ex & ~WS_EX_LAYERED); }
    else {
        if (!(ex & WS_EX_LAYERED)) SetWindowLongW(g_ht_ven, GWL_EXSTYLE, ex | WS_EX_LAYERED);
        SetLayeredWindowAttributes(g_ht_ven, 0, (BYTE)(g_n2_opac * 255 / 100), LWA_ALPHA);
    }
}

/* ── el fondo: una imagen (PNG/JPG/BMP/GIF, con GDI+) copiada a la carpeta del juego ── */
static void n2_fondo_ruta(wchar_t *r)                                 /* r: MAX_PATH */
{
    MultiByteToWideChar(CP_ACP, 0, g_carpeta, -1, r, MAX_PATH - 24);
    lstrcatW(r, L"n2hock_fondo.img");
}

static HBITMAP g_n2_imagen;                                          /* la imagen tal cual */
static int g_n2_img_w, g_n2_img_h;

static HBITMAP n2_gdip_cargar(const wchar_t *ruta, int *w, int *h)
{
    typedef struct { UINT32 ver; void *cb; BOOL sin_hilo, sin_codecs; } N2_GDIP_IN;
    typedef int (WINAPI *F_INI)(ULONG_PTR *, const N2_GDIP_IN *, void *);
    typedef int (WINAPI *F_ABRIR)(const WCHAR *, void **);
    typedef int (WINAPI *F_HBM)(void *, HBITMAP *, DWORD);
    typedef int (WINAPI *F_LIB)(void *);
    static ULONG_PTR token = 0;
    HMODULE g = LoadLibraryW(L"gdiplus.dll");
    if (!g) return NULL;
    F_INI ini = (F_INI)(void *)GetProcAddress(g, "GdiplusStartup");
    F_ABRIR abrir = (F_ABRIR)(void *)GetProcAddress(g, "GdipCreateBitmapFromFile");
    F_HBM hbm = (F_HBM)(void *)GetProcAddress(g, "GdipCreateHBITMAPFromBitmap");
    F_LIB lib = (F_LIB)(void *)GetProcAddress(g, "GdipDisposeImage");
    if (!ini || !abrir || !hbm || !lib) return NULL;
    if (!token) { N2_GDIP_IN in = { 1, NULL, FALSE, FALSE }; if (ini(&token, &in, NULL) != 0) { token = 0; return NULL; } }
    void *img = NULL; HBITMAP b = NULL;
    if (abrir(ruta, &img) != 0 || !img) return NULL;
    if (hbm(img, &b, 0xFF000000) != 0) b = NULL;
    lib(img);
    if (b) { BITMAP bm; GetObjectW(b, sizeof(bm), &bm); *w = bm.bmWidth; *h = bm.bmHeight; }
    return b;
}

/* la imagen tapando la ventana (como BackgroundImage «cover») + el velo: Card con alfa velo % */
static void n2_fondo_componer(void)
{
    if (g_n2_fondo_dc) { DeleteDC(g_n2_fondo_dc); DeleteObject(g_n2_fondo_bm); g_n2_fondo_dc = NULL; g_n2_fondo_bm = NULL; }
    if (!g_n2_imagen || !g_ht_ven || g_n2_img_w <= 0 || g_n2_img_h <= 0) return;
    HDC v = GetDC(g_ht_ven);
    g_n2_fondo_dc = CreateCompatibleDC(v);
    g_n2_fondo_bm = CreateCompatibleBitmap(v, N2_W, N2_H);
    SelectObject(g_n2_fondo_dc, g_n2_fondo_bm);
    HDC m = CreateCompatibleDC(v);
    HGDIOBJ om = SelectObject(m, g_n2_imagen);
    float e = (float)N2_W / g_n2_img_w; if ((float)N2_H / g_n2_img_h > e) e = (float)N2_H / g_n2_img_h;
    int w = (int)(g_n2_img_w * e), h = (int)(g_n2_img_h * e);
    SetStretchBltMode(g_n2_fondo_dc, HALFTONE); SetBrushOrgEx(g_n2_fondo_dc, 0, 0, NULL);
    StretchBlt(g_n2_fondo_dc, (N2_W - w) / 2, (N2_H - h) / 2, w, h, m, 0, 0, g_n2_img_w, g_n2_img_h, SRCCOPY);
    SelectObject(m, om);
    if (g_n2_velo > 0) {
        HBITMAP s = CreateCompatibleBitmap(v, 1, 1);
        om = SelectObject(m, s);
        SetPixel(m, 0, 0, N2_VENTANA);
        BLENDFUNCTION bf = { AC_SRC_OVER, 0, (BYTE)(g_n2_velo * 255 / 100), 0 };
        GdiAlphaBlend(g_n2_fondo_dc, 0, 0, N2_W, N2_H, m, 0, 0, 1, 1, bf);
        SelectObject(m, om); DeleteObject(s);
    }
    DeleteDC(m);
    ReleaseDC(g_ht_ven, v);
}

static void n2_fondo_cargar(void)
{
    wchar_t r[MAX_PATH];
    if (g_n2_imagen) { DeleteObject(g_n2_imagen); g_n2_imagen = NULL; }
    n2_fondo_ruta(r);
    if (GetFileAttributesW(r) != INVALID_FILE_ATTRIBUTES) g_n2_imagen = n2_gdip_cargar(r, &g_n2_img_w, &g_n2_img_h);
    n2_fondo_componer();
    n2_todo_repintar();
}

static void n2_fondo_elegir(void)
{
    typedef BOOL (WINAPI *F_ABRIR)(OPENFILENAMEW *);
    HMODULE cd = LoadLibraryW(L"comdlg32.dll");
    F_ABRIR f = cd ? (F_ABRIR)(void *)GetProcAddress(cd, "GetOpenFileNameW") : NULL;
    if (!f) return;
    wchar_t archivo[MAX_PATH] = L"", destino[MAX_PATH];
    OPENFILENAMEW o;
    ZeroMemory(&o, sizeof(o));
    o.lStructSize = sizeof(o);
    o.hwndOwner = g_n2_per ? g_n2_per : g_ht_ven;
    o.lpstrFilter = L"Imágenes\0*.png;*.jpg;*.jpeg;*.bmp;*.gif\0";
    o.lpstrFile = archivo; o.nMaxFile = MAX_PATH;
    o.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!f(&o)) return;
    n2_fondo_ruta(destino);
    if (!CopyFileW(archivo, destino, FALSE)) { ht_avisar(0, 4000, L"No se pudo copiar la imagen (%u)", (unsigned)GetLastError()); return; }
    n2_fondo_cargar();
    if (!g_n2_imagen) ht_avisar(0, 4000, L"Esa imagen no se pudo abrir");
}

static void n2_fondo_quitar(void)
{
    wchar_t r[MAX_PATH];
    n2_fondo_ruta(r);
    DeleteFileW(r);
    n2_fondo_cargar();
}

/* el selector de color de Windows */
static int n2_elegir_color(COLORREF *c)
{
    typedef BOOL (WINAPI *F_COLOR)(CHOOSECOLORW *);
    static COLORREF propios[16];
    HMODULE cd = LoadLibraryW(L"comdlg32.dll");
    F_COLOR f = cd ? (F_COLOR)(void *)GetProcAddress(cd, "ChooseColorW") : NULL;
    if (!f) return 0;
    CHOOSECOLORW x;
    ZeroMemory(&x, sizeof(x));
    x.lStructSize = sizeof(x);
    x.hwndOwner = g_n2_per ? g_n2_per : g_ht_ven;
    x.rgbResult = *c; x.lpCustColors = propios;
    x.Flags = CC_FULLOPEN | CC_RGBINIT;
    if (!f(&x)) return 0;
    *c = x.rgbResult;
    return 1;
}

/* ── el ini ── */
static COLORREF n2_hex(const char *s, COLORREF def)
{
    if (!s || s[0] != '#' || lstrlenA(s) != 7) return def;
    DWORD v = 0;
    for (int i = 1; i < 7; i++) {
        char c = s[i]; int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
        if (d < 0) return def;
        v = v * 16 + (DWORD)d;
    }
    return RGB((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF);
}

static void n2_per_leer(void)
{
    char t[96];
    GetPrivateProfileStringA("herramienta", "n2_acento", "#FF0080", t, sizeof(t), g_ht_ini);
    g_n2_acento = n2_hex(t, N2_ACENTO_FAB);
    if (GetPrivateProfileStringA("herramienta", "n2_letra", "", t, sizeof(t), g_ht_ini) && t[0])
        MultiByteToWideChar(CP_UTF8, 0, t, -1, g_n2_letra, 64);
    g_n2_velo = (int)GetPrivateProfileIntA("herramienta", "n2_velo", 70, g_ht_ini);
    if (g_n2_velo < 0 || g_n2_velo > 90) g_n2_velo = 70;
    g_n2_opac = (int)GetPrivateProfileIntA("herramienta", "n2_ventana", 100, g_ht_ini);
    if (g_n2_opac < 60 || g_n2_opac > 100) g_n2_opac = 100;
    g_n2i.animar   = GetPrivateProfileIntA("herramienta", "far_ind_animar", 1, g_ht_ini) != 0;
    g_n2i.conectar = GetPrivateProfileIntA("herramienta", "far_ind_conectar", 1, g_ht_ini) != 0;
    g_n2i.ronda    = GetPrivateProfileIntA("herramienta", "far_ind_ronda", 1, g_ht_ini) != 0;
    g_n2i.negrita  = GetPrivateProfileIntA("herramienta", "far_ind_negrita", 1, g_ht_ini) != 0;
    g_n2i_arco     = GetPrivateProfileIntA("herramienta", "far_ind_arcoiris", 1, g_ht_ini) != 0;
    g_n2i.tam  = (int)GetPrivateProfileIntA("herramienta", "far_ind_tam", 48, g_ht_ini);
    if (g_n2i.tam < 16 || g_n2i.tam > 120) g_n2i.tam = 48;
    g_n2i.dura = (int)GetPrivateProfileIntA("herramienta", "far_ind_dura", 900, g_ht_ini);
    if (g_n2i.dura < 300 || g_n2i.dura > 5000) g_n2i.dura = 900;
    g_n2i.x = (int)GetPrivateProfileIntA("herramienta", "far_ind_x", 500, g_ht_ini);
    g_n2i.y = (int)GetPrivateProfileIntA("herramienta", "far_ind_y", 450, g_ht_ini);
    if (g_n2i.x < 0 || g_n2i.x > 1000) g_n2i.x = 500;
    if (g_n2i.y < 0 || g_n2i.y > 1000) g_n2i.y = 450;
    GetPrivateProfileStringA("herramienta", "far_ind_color", "#FACC15", t, sizeof(t), g_ht_ini);
    g_n2i.color = n2_hex(t, RGB(0xFA, 0xCC, 0x15));
    if (GetPrivateProfileStringA("herramienta", "far_ind_letra", "", t, sizeof(t), g_ht_ini) && t[0])
        MultiByteToWideChar(CP_UTF8, 0, t, -1, g_n2i.letra, 64);
    g_n2_chat_diez     = GetPrivateProfileIntA("herramienta", "chat_diez", 0, g_ht_ini) != 0;
    g_n2_chat_en_juego = GetPrivateProfileIntA("herramienta", "chat_en_juego", 1, g_ht_ini) != 0;
    g_n2_chat_solo     = GetPrivateProfileIntA("herramienta", "chat_solo_carrera", 1, g_ht_ini) != 0;
    g_n2_chat_cod      = (int)GetPrivateProfileIntA("herramienta", "chat_codificacion", 0, g_ht_ini);
    g_n2_vel_en_juego  = GetPrivateProfileIntA("herramienta", "vel_en_juego", 1, g_ht_ini) != 0;
    n2_e_leer();
}

/* ═══ ★ ENTRENO Y TRAMOS: la ventana ↔ el motor (n2h_entreno.c) ═══ */
static const char *E_TK_CLAVE[E_TK_N] = { "e_tk_vel", "e_tk_menos", "e_tk_mas", "e_tk_bucle", "e_tk_a", "e_tk_b", "e_tk_rein",
                                          "e_tk_tramos", "e_tk_marca", "e_tk_mover1", "e_tk_mover2", "e_tk_mover3", "e_tk_mover4" };

static void n2_e_ini_txt(const char *k, wchar_t *dst, int n)
{
    char t[40];
    if (GetPrivateProfileStringA("herramienta", k, "\x01", t, sizeof(t), g_ht_ini) && t[0] != 1)
        MultiByteToWideChar(CP_ACP, 0, t, -1, dst, n);
}
static void n2_e_leer(void)
{
    char k[32];
    for (int i = 0; i < E_TK_N; i++) g_e.tk[i] = (int)GetPrivateProfileIntA("herramienta", E_TK_CLAVE[i], g_e.tk[i], g_ht_ini) & 0xFF;
    g_e.vel_pct = (int)GetPrivateProfileIntA("herramienta", "e_velocidad", 55, g_ht_ini);
    if (g_e.vel_pct < 50 || g_e.vel_pct > 150) g_e.vel_pct = 75;
    g_e.vel_pct = g_e.vel_pct / 5 * 5;
    n2_e_ini_txt("e_desde", g_e.desde, 16); n2_e_ini_txt("e_hasta", g_e.hasta, 16);
    n2_e_ini_txt("e_cuenta", g_e.cuenta, 8); n2_e_ini_txt("e_sin_notas", g_e.sin, 8);
    for (int i = 0; i < N2_TRAMOS; i++) {
        wsprintfA(k, "e_tramo%d_desde", i + 1); n2_e_ini_txt(k, g_e.tde[i], 16);
        wsprintfA(k, "e_tramo%d_hasta", i + 1); n2_e_ini_txt(k, g_e.tha[i], 16);
        wsprintfA(k, "e_tramo%d_vel", i + 1);
        g_e.tvel[i] = (int)GetPrivateProfileIntA("herramienta", k, 100, g_ht_ini);
        if (g_e.tvel[i] < 50 || g_e.tvel[i] > 150) g_e.tvel[i] = 100;
        g_e.tvel[i] = g_e.tvel[i] / 5 * 5;
    }
    ne_velocidad_poner(g_e.vel_pct);
}
static void n2_e_leer_cajas(void)
{
    if (!g_e_ed_desde) return;
    GetWindowTextW(g_e_ed_desde, g_e.desde, 16); GetWindowTextW(g_e_ed_hasta, g_e.hasta, 16);
    GetWindowTextW(g_e_ed_cuenta, g_e.cuenta, 8); GetWindowTextW(g_e_ed_sin, g_e.sin, 8);
    for (int i = 0; i < N2_TRAMOS; i++) {
        GetWindowTextW(g_e_ed_tde[i], g_e.tde[i], 16); GetWindowTextW(g_e_ed_tha[i], g_e.tha[i], 16);
        int k = (int)SendMessageW(g_e_cb_tvel[i], CB_GETCURSEL, 0, 0);
        g_e.tvel[i] = k >= 0 ? 50 + 5 * k : 100;
    }
}
static void n2_e_ini_poner(HT_BUF *x, const char *k, const wchar_t *w, const char *eol)
{
    char v[40];
    if (!WideCharToMultiByte(CP_ACP, 0, w, -1, v, sizeof(v), NULL, NULL)) v[0] = 0;
    for (char *p = v; *p; p++) if (*p == '\r' || *p == '\n') *p = ' ';
    ht_buf_poner(x, k, v, eol);
}
static void n2_e_guardar(HT_BUF *x, const char *eol)
{
    char k[32], v[16];
    for (int i = 0; i < E_TK_N; i++) { wsprintfA(v, "%d", g_e.tk[i]); ht_buf_poner(x, E_TK_CLAVE[i], v, eol); }
    wsprintfA(v, "%d", g_e.vel_pct); ht_buf_poner(x, "e_velocidad", v, eol);
    n2_e_ini_poner(x, "e_desde", g_e.desde, eol); n2_e_ini_poner(x, "e_hasta", g_e.hasta, eol);
    n2_e_ini_poner(x, "e_cuenta", g_e.cuenta, eol); n2_e_ini_poner(x, "e_sin_notas", g_e.sin, eol);
    for (int i = 0; i < N2_TRAMOS; i++) {
        wsprintfA(k, "e_tramo%d_desde", i + 1); n2_e_ini_poner(x, k, g_e.tde[i], eol);
        wsprintfA(k, "e_tramo%d_hasta", i + 1); n2_e_ini_poner(x, k, g_e.tha[i], eol);
        wsprintfA(k, "e_tramo%d_vel", i + 1); wsprintfA(v, "%d", g_e.tvel[i]); ht_buf_poner(x, k, v, eol);
    }
}

static void n2_e_textos(void)
{
    wsprintfW(g_e_pct_txt, L"%d %%", g_e.vel_pct);
}

static COLORREF n2_e_color(int lbl, COLORREF c)
{
    for (int k = 0; k < NE_TX_N; k++)
        if (g_e_lbl[k] == lbl) return g_e_tx_err[k] ? N2_ERROR : (k == NE_TX_VELOCIDAD ? N2_AVISO : k == NE_TX_MOVER ? N2_SUAVE : N2_BIEN);
    return c == N2_C_ACENTO ? N2_ACENTO : c;
}

static void n2_e_falta_confirmo(void)
{
    lstrcpyW(g_e_tx[NE_TX_VELOCIDAD], L"Conecta una cuenta y confirma que estás en práctica offline.");
    g_e_tx_err[NE_TX_VELOCIDAD] = 1;
    if (g_n2_pag[2]) InvalidateRect(g_n2_pag[2], NULL, FALSE);
}

static int n2_e_segundos(const wchar_t *t, int def)
{
    int v = 0, hay = 0;
    for (; *t; t++) { if (*t >= L'0' && *t <= L'9') { v = v * 10 + (*t - L'0'); hay = 1; } else if (*t != L' ') return def; }
    return hay && v <= 30 ? v : def;
}

/* el bucle con lo que dicen las cajas */
static int n2_e_bucle_configurar(void)
{
    n2_e_leer_cajas();
    int a = ne_posicion_de_texto(g_e.desde), b = g_e.hasta[0] ? ne_posicion_de_texto(g_e.hasta) : 0;
    if (a < 0 || b < 0) {
        lstrcpyW(g_e_tx[NE_TX_BUCLE], L"Escribe Desde y Hasta como m:ss (por ejemplo 0:20).");
        g_e_tx_err[NE_TX_BUCLE] = 1;
        return 0;
    }
    ne_bucle_tiempos(a, b);
    ne_bucle_opciones(n2_e_segundos(g_e.cuenta, 3), n2_e_segundos(g_e.sin, 2));
    return 1;
}

/* ★ 26-nov: qué filas de la pestaña Tramos se ven: 1–6 (p 0) o 7–12 (p 1) */
static void n2_e_tr_pagina(int p)
{
    p = p ? 1 : 0;
    g_e_tr_pag = p;
    for (int i = 0; i < N2_TRAMOS; i++) {
        int ver = (i / 6) == p;
        HWND hs[4] = { g_e_ed_tde[i], g_e_ed_tha[i], g_e_cb_tvel[i], g_e_bt_tx[i] };
        for (int k = 0; k < 4; k++) if (hs[k]) ShowWindow(hs[k], ver ? SW_SHOW : SW_HIDE);
    }
    for (int i = 0; i < 6; i++) wsprintfW(g_e_num[i], L"%d", p * 6 + i + 1);
    if (g_e_bt_pag) SetWindowTextW(g_e_bt_pag, p ? L"«" : L"»");
    if (g_n2_pag[3]) InvalidateRect(g_n2_pag[3], NULL, TRUE);
}

/* los tramos con lo que dicen las filas */
static int n2_e_tramos_poner(int on)
{
    int de[N2_TRAMOS], ha[N2_TRAMOS], pc[N2_TRAMOS];
    n2_e_leer_cajas();
    for (int i = 0; i < N2_TRAMOS; i++) {
        de[i] = g_e.tde[i][0] ? ne_posicion_de_texto(g_e.tde[i]) : -1;
        ha[i] = g_e.tha[i][0] ? ne_posicion_de_texto(g_e.tha[i]) : -1;
        pc[i] = g_e.tvel[i];
    }
    return ne_tramos(on, de, ha, pc, N2_TRAMOS);
}

/* una casilla de Entreno / Tramos cambió: se la pide al motor y queda lo que el motor dice */
static void n2_e_cambio(int *pb)
{
    if (pb == &g_e.confirmo) {
        if (!g_e.confirmo) { ne_apagar_todo(); g_e.habilitar = g_e.anticaida = g_e.vel_on = g_e.bucle_on = g_e.tramos_on = 0; }
    } else if (pb == &g_e.habilitar || pb == &g_e.anticaida || pb == &g_e.vel_on || pb == &g_e.bucle_on || pb == &g_e.tramos_on) {
        int quiere = *pb;
        if (quiere && !g_e.confirmo) { *pb = 0; n2_e_falta_confirmo(); n2_sincronizar(); return; }
        if (pb == &g_e.habilitar) { ne_preparar(quiere); g_e.habilitar = ne_preparado(); }
        else if (pb == &g_e.anticaida) { ne_anticaida(quiere); g_e.anticaida = ne_anticaida_activa(); }
        else if (pb == &g_e.vel_on) { ne_velocidad_poner(g_e.vel_pct); ne_velocidad_activar(quiere); g_e.vel_on = ne_velocidad_activa(); }
        else if (pb == &g_e.bucle_on) {
            if (quiere && !n2_e_bucle_configurar()) g_e.bucle_on = 0;
            else { ne_bucle_activar(quiere); g_e.bucle_on = ne_bucle_activo(); }
        } else if (pb == &g_e.tramos_on) { n2_e_tramos_poner(quiere); g_e.tramos_on = ne_tramos_activos(); }
    } else return;
    n2_sincronizar();
}

/* las cajas Desde / Hasta después de marcar A o B, y las filas después de «Marcar punto» */
static void n2_e_cajas_del_motor(int bucle, int tramos)
{
    wchar_t t[16];
    if (bucle) {
        int a, b, c, s;
        ne_bucle_leer(&a, &b, &c, &s);
        if (a >= 0) { ne_texto_de_posicion(a, t); SetWindowTextW(g_e_ed_desde, t); }
        if (b > 0) { ne_texto_de_posicion(b, t); SetWindowTextW(g_e_ed_hasta, t); }
    }
    if (tramos) {
        int de[N2_TRAMOS], ha[N2_TRAMOS], pc[N2_TRAMOS];
        ne_tramos_filas(de, ha, pc);
        for (int i = 0; i < N2_TRAMOS; i++) {
            if (de[i] >= 0) ne_texto_de_posicion(de[i], t); else t[0] = 0;
            SetWindowTextW(g_e_ed_tde[i], t);
            if (ha[i] >= 0) ne_texto_de_posicion(ha[i], t); else t[0] = 0;
            SetWindowTextW(g_e_ed_tha[i], t);
            if (pc[i] >= 50 && pc[i] <= 150) SendMessageW(g_e_cb_tvel[i], CB_SETCURSEL, (WPARAM)((pc[i] - 50) / 5), 0);
        }
    }
}

/* ═══ ★ 25-nov: A/B EN LA BARRA DE LA PAUSA (la idea del ToolBit 0.6.40) ═════════════════════════════════════
 *   pausa_barra.c dibuja la barra y lee el mouse en el HILO DEL JUEGO; el motor y las cajas son de ESTE hilo. Así que
 *   no se tocan entre ellos: el juego deja pedidos (Interlocked) y lee una foto que se saca acá cada 50 ms. */
static volatile LONG g_pb_vivo = 0;                       /* GetTickCount del último n2_e_tick (0 = nunca)          */
static volatile LONG g_pb_visto = 0;                      /* GetTickCount del último dibujo de la Pausa (pausa.c)   */
static volatile LONG g_pb_pos = -1, g_pb_largo = -1;      /* ms en la canción y su largo (-1 = no se sabe)          */
static volatile LONG g_pb_a = 0, g_pb_b = 0;              /* el tramo de las cajas Desde/Hasta (b 0 = hasta el final) */
static volatile LONG g_pb_bucle = 0, g_pb_bucle_real = 0, g_pb_prep = 0, g_pb_estado = 0, g_pb_vueltas = 0;
static volatile LONG g_pb_msj_serie = 0, g_pb_msj_err = 0;
static wchar_t g_pb_msj[200];
static volatile LONG g_pb_ped_a = -1, g_pb_ped_b = -1, g_pb_ped_ir = -1;   /* ms; b: 0 = hasta el final; -1 nada */
/* ★ 26-nov: los tramos de velocidad (A→B, B→C…) en la Pausa de la práctica: la foto (de pb_tramos_tick) y los pedidos */
static volatile LONG g_pt_n = 0, g_pt_pend = -1, g_pt_on = 0, g_pt_serie = 0;
static volatile LONG g_pt_de[N2_TRAMOS], g_pt_ha[N2_TRAMOS], g_pt_pc[N2_TRAMOS], g_pt_fila[N2_TRAMOS];
static volatile LONG g_pt_ped_punto = -1;                /* ms: el siguiente punto (A, B, C…) */
static volatile LONG g_pt_ped_borde = -1;                /* (de en s) << 16 | (a en s): mover un borde */
static volatile LONG g_pt_ped_vel = -1;                  /* fila << 8 | pct */
static volatile LONG g_pt_ped_quitar = -1;               /* fila (1..6) */
static volatile LONG g_pt_ped_onoff = 0;                 /* 1 = alternar «Activar tramos» */

static void n2_pb_aviso(int que)
{
    wchar_t t[320];
    int err = ne_texto(que, t, 320);
    if (!t[0]) return;
    lstrcpynW(g_pb_msj, t, 200);
    g_pb_msj_err = err;
    InterlockedIncrement(&g_pb_msj_serie);
}

static void n2_pb_tick(void)
{
    LONG a = InterlockedExchange(&g_pb_ped_a, -1), b = InterlockedExchange(&g_pb_ped_b, -1);
    LONG ir = InterlockedExchange(&g_pb_ped_ir, -1);
    wchar_t t[16];
    if ((a >= 0 || b >= 0) && g_e_ed_desde) {
        if (a >= 0) { ne_texto_de_posicion((int)a, t); SetWindowTextW(g_e_ed_desde, t); }
        if (b >= 0) { if (b > 0) ne_texto_de_posicion((int)b, t); else t[0] = 0; SetWindowTextW(g_e_ed_hasta, t); }
        if (n2_e_bucle_configurar() && g_e.bucle_on) { ne_bucle_activar(1); g_e.bucle_on = ne_bucle_activo(); }
        n2_pb_aviso(NE_TX_BUCLE);
        if (!g_pb_msj_err) {
            wchar_t x[16], y[16];
            int da, db, dc, ds;
            ne_bucle_leer(&da, &db, &dc, &ds);
            ne_texto_de_posicion(da, x);
            if (db > 0) ne_texto_de_posicion(db, y); else lstrcpyW(y, L"el final");
            wsprintfW(g_pb_msj, L"Tramo: A %s → B %s%s", x, y, g_e.bucle_on ? L" (repitiendo)" : L" · actívalo con «Repetir un tramo»");
            InterlockedIncrement(&g_pb_msj_serie);
        }
        n2_sincronizar();
    }
    if (ir >= 0) {
        int pos = ne_tiempo_ms();
        if (pos < 0) {
            lstrcpyW(g_pb_msj, L"No sé en qué segundo de la canción estás: habilita Entreno en Ñ2Hock.");
            g_pb_msj_err = 1; InterlockedIncrement(&g_pb_msj_serie);
        } else {
            int d = (int)ir - pos;
            d = d >= 0 ? (d + 500) / 1000 : -((-d + 500) / 1000);
            if (d > 600) d = 600;
            if (d < -600) d = -600;
            if (d) { ne_mover(d); n2_pb_aviso(NE_TX_MOVER); }
        }
    }
    /* la foto para el hilo del juego */
    if (g_e_ed_desde) {
        wchar_t de[16], ha[16];
        GetWindowTextW(g_e_ed_desde, de, 16); GetWindowTextW(g_e_ed_hasta, ha, 16);
        int pa = de[0] ? ne_posicion_de_texto(de) : 0, pb = ha[0] ? ne_posicion_de_texto(ha) : 0;
        g_pb_a = pa < 0 ? 0 : pa;
        g_pb_b = pb < 0 ? 0 : pb;
    }
    /* la posición sólo con la Pausa a la vista (fuera de la sesión, ne_tiempo_ms lee el juego entero) */
    if ((LONG)(GetTickCount() - (DWORD)g_pb_visto) > 1500) { g_pb_vivo = (LONG)(GetTickCount() | 1); return; }
    int est = 0, vue = 0;
    ne_bucle_estado(&est, &vue, NULL, NULL);
    g_pb_estado = est; g_pb_vueltas = vue;
    g_pb_bucle = ne_bucle_activo();
    g_pb_bucle_real = g_ne_q_bucle;
    g_pb_prep = ne_preparado();
    g_pb_pos = ne_tiempo_ms();
    g_pb_largo = ne_largo_ms();
    g_pb_vivo = (LONG)(GetTickCount() | 1);
}

/* cada 50 ms: el latido del motor, las teclas de Entreno / Tramos y los textos de estado */
static void pd_tick(void);
static void pb_tramos_tick(void);
static void n2_e_tick(void)
{
    static BYTE antes[E_TK_N];
    ne_tick();
    n2_pb_tick();
    pb_tramos_tick();                                /* ★ 26-nov: los tramos desde la Pausa de la práctica */
    pd_tick();
    fj_tick();                                       /* ★ 26-nov: lo que pidió el panel del Far del juego */
    if (InterlockedExchange(&g_fj_ped_vel, 0)) { g_e.vel_on = !g_e.vel_on; n2_e_cambio(&g_e.vel_on); }
    {
        LONG pct = InterlockedExchange(&g_fj_ped_pct, -1);
        if (pct >= 50 && pct <= 150 && pct != g_e.vel_pct) {
            g_e.vel_pct = (int)pct;
            ne_velocidad_poner(g_e.vel_pct);
            n2_sincronizar();
            ht_pedir_guardar();
        }
    }
    /* las teclas (con Hotkey, el juego delante, sin escribir en una caja y con «Confirmo») */
    int sirve = g_op[O_HOTKEYS].quiere && ht_con_foco() && !g_ht_apagada && g_ht_esperando < 0 && g_e.confirmo
                && GetForegroundWindow() != g_ht_ven && GetForegroundWindow() != g_n2_per;
    for (int i = 0; i < E_TK_N; i++) {
        int vk = g_e.tk[i];
        int b = vk > 0 && vk < 256 && (GetAsyncKeyState(vk) & 0x8000) != 0;
        int flanco = b && !antes[i];
        antes[i] = (BYTE)b;
        if (!flanco || !sirve) continue;
        switch (i) {
        case E_TK_VEL: g_e.vel_on = !g_e.vel_on; n2_e_cambio(&g_e.vel_on); break;
        case E_TK_MENOS: case E_TK_MAS:
            g_e.vel_pct += i == E_TK_MAS ? 5 : -5;
            if (g_e.vel_pct < 50) g_e.vel_pct = 50;
            if (g_e.vel_pct > 150) g_e.vel_pct = 150;
            ne_velocidad_poner(g_e.vel_pct);
            break;
        case E_TK_BUCLE: g_e.bucle_on = !g_e.bucle_on; n2_e_cambio(&g_e.bucle_on); break;
        case E_TK_A: if (ne_bucle_marcar_a()) n2_e_cajas_del_motor(1, 0); break;
        case E_TK_B: if (ne_bucle_marcar_b()) n2_e_cajas_del_motor(1, 0); break;
        case E_TK_REIN: ne_bucle_reiniciar(); break;
        case E_TK_TRAMOS: g_e.tramos_on = !g_e.tramos_on; n2_e_cambio(&g_e.tramos_on); break;
        case E_TK_MARCA: if (ne_marcar_punto()) { n2_e_cajas_del_motor(0, 1); if (g_n2m_barra) InvalidateRect(g_n2m_barra, NULL, FALSE); } break;
        default: { static const int D[4] = { -5, -1, 1, 5 }; ne_mover(D[i - E_TK_MOVER0]); } break;
        }
    }
    /* lo que dice el motor: los textos y si cada cosa quedó prendida (se puede apagar sola) */
    int cambio = 0;
    for (int k = 0; k < NE_TX_N; k++) {
        wchar_t t[320];
        int err = ne_texto(k, t, 320);
        if (k == NE_TX_VELOCIDAD && !t[0] && !g_e_tx[k][0]) { lstrcpyW(t, L"Motor nativo · conecta una cuenta e inicia práctica offline."); }
        if (k == NE_TX_ANTICAIDA && !t[0]) lstrcpyW(t, L"el choque del Latino");
        if (k == NE_TX_TRAMOS && !t[0]) lstrcpyW(t, L"Tramos desactivados.");
        if (k == NE_TX_MOVER && !t[0]) lstrcpyW(t, L"Vuelve a un segundo ya tocado para ver dónde poner un tramo lento.");
        if (!t[0]) continue;
        if (lstrcmpW(t, g_e_tx[k]) || err != g_e_tx_err[k]) { lstrcpyW(g_e_tx[k], t); g_e_tx_err[k] = err; cambio = 1; }
    }
    int h = ne_preparado(), a = ne_anticaida_activa(), v = ne_velocidad_activa(), bu = ne_bucle_activo(), tr = ne_tramos_activos();
    if (h != g_e.habilitar || a != g_e.anticaida || v != g_e.vel_on || bu != g_e.bucle_on || tr != g_e.tramos_on) {
        g_e.habilitar = h; g_e.anticaida = a; g_e.vel_on = v; g_e.bucle_on = bu; g_e.tramos_on = tr;
        cambio = 1;
    }
    {
        static int pct_visto = -1;
        if (g_e.vel_pct != pct_visto) { pct_visto = g_e.vel_pct; n2_e_textos(); cambio = 1; }
    }
    {   /* ★ el cartel «VEL 75 %» (FarIndicatorSettings.Text de Ñ2Hock, pero de la velocidad): al cambiar la que corre,
         *   a mano o por un tramo. Con el mismo estilo que el del Far (Personalización · Far). */
        static int vel_vista = 100;
        int ap = (g_e.vel_on || g_e.tramos_on) ? ne_velocidad_aplicada() : 100;
        if (ap != vel_vista) {
            vel_vista = ap;
            if (g_n2_vel_en_juego && !g_ht_apagada && (g_e.vel_on || g_e.tramos_on)) {
                wsprintfA(g_ht_ind_txt, "VEL %d %%", ap);
                g_n2_capa_es_vel = 1;
                g_n2_capa_firma = 0;
                g_ht_ind_hasta = GetTickCount() + (DWORD)g_n2i.dura;
            }
        }
    }
    if (cambio) n2_sincronizar();
}

static int n2m_abs(int v) { return v < 0 ? -v : v; }
/* ═══ ★ EL MAPA DE LA CANCIÓN (Form1.SongMap.cs + SongTimeline.cs de Ñ2Hock) ═══
 *   Una ventana ancha con la barra de la canción: clic en la barra = el siguiente punto (A, B, C…: cada tramo nuevo
 *   empieza donde termina el anterior); clic en un tramo = su velocidad o quitarlo; los bordes se arrastran. El
 *   triángulo verde es la posición en la canción (la del motor). Todo escribe en las filas de la pestaña Tramos. */
#define N2M_PAD  14
#define N2M_GRIP 5
static HWND g_n2m, g_n2m_cerrar;
static wchar_t g_n2m_msj[160];
static int  g_n2m_msj_err;
static int  g_n2m_dur = 120000, g_n2m_pos = -1, g_n2m_hover = -1;
static int  g_n2m_arr = 0, g_n2m_arr_de, g_n2m_arr_ms, g_n2m_arr_min, g_n2m_arr_max;
static int  g_n2m_arr_fila[2 * N2_TRAMOS], g_n2m_arr_ini[2 * N2_TRAMOS], g_n2m_arr_n;      /* qué bordes se arrastran (fila, 1 = inicio) */

typedef struct { int n, de, ha, pc; } N2M_TRAMO;
static int n2m_tramos(N2M_TRAMO *t)                  /* las filas completas y en orden: los tramos del mapa */
{
    int n = 0;
    n2_e_leer_cajas();
    for (int i = 0; i < N2_TRAMOS; i++) {
        int a = g_e.tde[i][0] ? ne_posicion_de_texto(g_e.tde[i]) : -1, b = g_e.tha[i][0] ? ne_posicion_de_texto(g_e.tha[i]) : -1;
        if (a >= 0 && b > a) { t[n].n = i + 1; t[n].de = a; t[n].ha = b; t[n].pc = g_e.tvel[i]; n++; }
    }
    return n;
}
static int n2m_pendiente(void)                       /* un «Desde» sin «Hasta»: la línea amarilla */
{
    int p = -1;
    for (int i = 0; i < N2_TRAMOS; i++)
        if (!g_e.tha[i][0] && g_e.tde[i][0]) { int a = ne_posicion_de_texto(g_e.tde[i]); if (a >= 0) p = a; }
    return p;
}
static void n2m_poner(HWND ed, int ms) { wchar_t t[16]; if (ms < 0) t[0] = 0; else ne_texto_de_posicion(ms, t); SetWindowTextW(ed, t); }
static void n2m_aviso(int err, const wchar_t *f, ...)
{
    va_list a; va_start(a, f); wvsprintfW(g_n2m_msj, f, a); va_end(a);
    g_n2m_msj_err = err;
}
static void n2m_editado(void)                        /* como OnZoneRowsEdited: con los tramos activos, el motor los toma ya */
{
    n2_e_leer_cajas();
    if (g_e.tramos_on) { n2_e_tramos_poner(1); g_e.tramos_on = ne_tramos_activos(); }
    n2_sincronizar();
    if (g_n2m_barra) InvalidateRect(g_n2m_barra, NULL, FALSE);
    if (g_n2m) InvalidateRect(g_n2m, NULL, FALSE);
}

/* AddZonePoint: A, B, C… de izquierda a derecha */
static void n2m_punto(int ms)
{
    wchar_t p[16]; ne_texto_de_posicion(ms, p);
    int ultimo = -1;
    n2_e_leer_cajas();
    for (int i = 0; i < N2_TRAMOS; i++) if (g_e.tde[i][0]) ultimo = i;
    if (ultimo >= 0) {
        const wchar_t *ant = g_e.tha[ultimo][0] ? g_e.tha[ultimo] : g_e.tde[ultimo];
        int antes = ne_posicion_de_texto(ant);
        if (antes >= 0 && ms <= antes) { n2m_aviso(1, L"Marca los puntos en orden: el siguiente debe ir después de %s.", ant); return; }
    }
    if (ultimo >= 0 && !g_e.tha[ultimo][0]) {
        n2m_poner(g_e_ed_tha[ultimo], ms);
        n2m_aviso(0, L"Tramo %d: final en %s.", ultimo + 1, p);
    } else if (ultimo + 1 < N2_TRAMOS) {
        int f = ultimo + 1;
        if (f / 6 != g_e_tr_pag) n2_e_tr_pagina(f / 6);     /* que se vea la fila nueva */
        if (ultimo >= 0) {
            SetWindowTextW(g_e_ed_tde[f], g_e.tha[ultimo]);
            n2m_poner(g_e_ed_tha[f], ms);
            n2m_aviso(0, L"Tramo %d: %s → %s.", f + 1, g_e.tha[ultimo], p);
        } else {
            n2m_poner(g_e_ed_tde[f], ms);
            n2m_aviso(0, L"Tramo 1: inicio en %s. Marca otra vez en el final.", p);
        }
    } else { n2m_aviso(1, L"Ya no caben más tramos (máximo %d).", N2_TRAMOS); return; }
    n2m_editado();
}

/* ★ 26-nov: lo que pidió la barra de la Pausa (pausa_barra.c) con los tramos, y la foto para dibujarlos.
 *   Usa lo mismo que el Mapa de la canción: todo termina en las filas de la pestaña Tramos. */
static void pb_tramos_tick(void)
{
    LONG punto = InterlockedExchange(&g_pt_ped_punto, -1), borde = InterlockedExchange(&g_pt_ped_borde, -1);
    LONG vel = InterlockedExchange(&g_pt_ped_vel, -1), quitar = InterlockedExchange(&g_pt_ped_quitar, -1);
    LONG onoff = InterlockedExchange(&g_pt_ped_onoff, 0);
    int hubo = punto >= 0 || borde >= 0 || vel >= 0 || quitar >= 0 || onoff;
    if (hubo && (!g_e_ed_tde[N2_TRAMOS - 1] || !g_e_ed_tha[N2_TRAMOS - 1] || !g_e_cb_tvel[N2_TRAMOS - 1])) {
        lstrcpyW(g_pb_msj, L"Los tramos no están listos: abre una vez la pestaña Tramos de Ñ2Hock.");
        g_pb_msj_err = 1; InterlockedIncrement(&g_pb_msj_serie);
        return;
    }
    if (hubo) {
        g_n2m_msj[0] = 0;
        if (punto >= 0) n2m_punto((int)punto);
        if (borde >= 0) {
            int de = (int)(borde >> 16) * 1000, a = (int)(borde & 0xFFFF) * 1000, k = 0;
            N2M_TRAMO tr[N2_TRAMOS];
            int n = n2m_tramos(tr);
            for (int i = 0; i < n; i++) {
                if (tr[i].de == de) { n2m_poner(g_e_ed_tde[tr[i].n - 1], a); k++; }
                if (tr[i].ha == de) { n2m_poner(g_e_ed_tha[tr[i].n - 1], a); k++; }
            }
            if (k) { wchar_t t[16]; ne_texto_de_posicion(a, t); n2m_aviso(0, L"Borde movido a %s.", t); n2m_editado(); }
        }
        if (vel >= 0) {
            int f = (int)(vel >> 8) - 1, pc = (int)(vel & 0xFF);
            if (f >= 0 && f < N2_TRAMOS && pc >= 50 && pc <= 150) {
                pc = pc / 5 * 5;
                SendMessageW(g_e_cb_tvel[f], CB_SETCURSEL, (WPARAM)((pc - 50) / 5), 0);
                n2m_aviso(0, L"Tramo %d a %d %%.", f + 1, pc);
                n2m_editado();
            }
        }
        if (quitar >= 1 && quitar <= N2_TRAMOS) {
            int f = (int)quitar - 1;
            SetWindowTextW(g_e_ed_tde[f], L""); SetWindowTextW(g_e_ed_tha[f], L""); SendMessageW(g_e_cb_tvel[f], CB_SETCURSEL, 10, 0);
            n2m_aviso(0, L"Tramo %d quitado.", (int)quitar);
            n2m_editado();
        }
        if (onoff) {
            int quiere = !g_e.tramos_on;
            g_e.tramos_on = quiere;
            n2_e_cambio(&g_e.tramos_on);
            if (quiere && !g_e.tramos_on)
                n2m_aviso(1, L"No se activaron los tramos: habilita Entreno en Ñ2Hock y marca al menos un tramo.");
            else n2m_aviso(0, g_e.tramos_on ? L"Tramos activados: la velocidad cambia en cada tramo." : L"Tramos apagados.");
        }
        if (g_n2m_msj[0]) {
            lstrcpynW(g_pb_msj, g_n2m_msj, 200);
            g_pb_msj_err = g_n2m_msj_err;
            InterlockedIncrement(&g_pb_msj_serie);
        }
    }
    /* la foto, sólo con la Pausa a la vista */
    if (!hubo && (LONG)(GetTickCount() - (DWORD)g_pb_visto) > 1500) return;
    static DWORD antes = 0xFFFFFFFF;
    N2M_TRAMO tr[N2_TRAMOS];
    int n = n2m_tramos(tr), pend = n2m_pendiente();
    DWORD h = (DWORD)n * 7u + (DWORD)pend * 31u + (DWORD)g_e.tramos_on * 1000003u;
    for (int i = 0; i < n; i++) {
        g_pt_de[i] = tr[i].de; g_pt_ha[i] = tr[i].ha; g_pt_pc[i] = tr[i].pc; g_pt_fila[i] = tr[i].n;
        h = h * 131u + (DWORD)tr[i].de * 3u + (DWORD)tr[i].ha * 5u + (DWORD)tr[i].pc + (DWORD)tr[i].n * 17u;
    }
    g_pt_n = n; g_pt_pend = pend; g_pt_on = g_e.tramos_on;
    if (h != antes) { antes = h; InterlockedIncrement(&g_pt_serie); }
}

static RECT n2m_rect(HWND h) { RECT c; GetClientRect(h, &c); RECT r = { N2M_PAD, 24, c.right - N2M_PAD, c.bottom - 24 }; if (r.right <= r.left) r.right = r.left + 1; return r; }
static int n2m_x(const RECT *b, int ms) { if (ms < 0) ms = 0; if (ms > g_n2m_dur) ms = g_n2m_dur; return b->left + (int)((double)ms / g_n2m_dur * (b->right - b->left) + 0.5); }
static int n2m_ms(const RECT *b, int x)
{
    double v = (double)(x - b->left) / (b->right - b->left) * g_n2m_dur / 1000.0;
    int ms = (int)(v + 0.5) * 1000;
    return ms < 0 ? 0 : ms > g_n2m_dur ? g_n2m_dur : ms;
}
static COLORREF n2m_color(int pc) { return pc < 100 ? RGB(56, 189, 248) : pc > 100 ? RGB(251, 113, 133) : RGB(148, 163, 184); }
static COLORREF n2m_mezcla(COLORREF a, COLORREF b, int al)
{
    return RGB((GetRValue(a) * al + GetRValue(b) * (255 - al)) / 255, (GetGValue(a) * al + GetGValue(b) * (255 - al)) / 255,
               (GetBValue(a) * al + GetBValue(b) * (255 - al)) / 255);
}
static void n2m_formato(int ms, wchar_t *s) { int seg = ms < 0 ? 0 : ms / 1000; wsprintfW(s, L"%d:%02d", seg / 60, seg % 60); }
static void n2m_centrado(HDC dc, const wchar_t *t, int x, int y, const RECT *b, COLORREF c)
{
    SIZE z; GetTextExtentPoint32W(dc, t, lstrlenW(t), &z);
    int l = x - z.cx / 2;
    if (l < b->left - N2M_PAD + 2) l = b->left - N2M_PAD + 2;
    if (l > b->right + N2M_PAD - 2 - z.cx) l = b->right + N2M_PAD - 2 - z.cx;
    SetTextColor(dc, c); TextOutW(dc, l, y, t, lstrlenW(t));
}

static void n2m_pintar(HWND h, HDC d0)
{
    RECT c; GetClientRect(h, &c);
    HDC dc = CreateCompatibleDC(d0);
    HBITMAP bm = CreateCompatibleBitmap(d0, c.right, c.bottom);
    HGDIOBJ ob = SelectObject(dc, bm);
    HBRUSH br = CreateSolidBrush(RGB(6, 12, 28)); FillRect(dc, &c, br); DeleteObject(br);
    RECT b = n2m_rect(h);
    COLORREF barra = RGB(2, 14, 38);
    br = CreateSolidBrush(barra); FillRect(dc, &b, br); DeleteObject(br);
    HFONT f = CreateFontW(-10, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, g_n2_letra);
    HFONT fb = CreateFontW(-11, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, g_n2_letra);
    HGDIOBJ of = SelectObject(dc, f);
    SetBkMode(dc, TRANSPARENT);
    /* las marcas de tiempo */
    static const int PASOS[6] = { 5000, 10000, 15000, 30000, 60000, 120000 };
    int paso = 300000, w = b.right - b.left;
    for (int i = 0; i < 6; i++) if (PASOS[i] * (double)w / g_n2m_dur >= 56) { paso = PASOS[i]; break; }
    int menor = paso >= 30000 ? paso / 3 : paso / 2;
    wchar_t t[48];
    for (int ms = menor; ms < g_n2m_dur; ms += menor) {
        int x = n2m_x(&b, ms), mayor = ms % paso == 0;
        if (mayor) n2_linea(dc, x, b.top + 1, x, b.bottom - 1, RGB(96, 110, 138));
        else for (int y = b.top + 1; y < b.bottom - 1; y += 3) SetPixel(dc, x, y, RGB(52, 72, 104));
        if (mayor) { n2m_formato(ms, t); n2m_centrado(dc, t, x, 4, &b, RGB(200, 210, 225)); }
    }
    n2m_centrado(dc, L"0:00", b.left, 4, &b, RGB(200, 210, 225));
    n2m_formato(g_n2m_dur, t); n2m_centrado(dc, t, b.right, 4, &b, RGB(200, 210, 225));
    /* los tramos (mientras se arrastra, con el borde movido) */
    N2M_TRAMO tr[N2_TRAMOS];
    int n = n2m_tramos(tr);
    SelectObject(dc, fb);
    for (int i = 0; i < n; i++) {
        int de = tr[i].de, ha = tr[i].ha;
        for (int k = 0; g_n2m_arr && k < g_n2m_arr_n; k++)
            if (g_n2m_arr_fila[k] == tr[i].n) { if (g_n2m_arr_ini[k]) de = g_n2m_arr_ms; else ha = g_n2m_arr_ms; }
        int l = n2m_x(&b, de), r = n2m_x(&b, ha);
        if (r - l < 2) r = l + 2;
        COLORREF col = n2m_color(tr[i].pc);
        RECT z = { l, b.top + 3, r, b.bottom - 3 };
        br = CreateSolidBrush(n2m_mezcla(col, barra, 120)); FillRect(dc, &z, br); DeleteObject(br);
        HPEN p = CreatePen(PS_SOLID, 2, col); HGDIOBJ op = SelectObject(dc, p);
        MoveToEx(dc, l, b.top + 1, NULL); LineTo(dc, l, b.bottom - 1);
        MoveToEx(dc, r, b.top + 1, NULL); LineTo(dc, r, b.bottom - 1);
        SelectObject(dc, op); DeleteObject(p);
        SIZE sz;
        wsprintfW(t, L"%d · %d %%", tr[i].n, tr[i].pc);
        GetTextExtentPoint32W(dc, t, lstrlenW(t), &sz);
        if (sz.cx + 4 > r - l) { wsprintfW(t, L"%d%%", tr[i].pc); GetTextExtentPoint32W(dc, t, lstrlenW(t), &sz); }
        if (sz.cx + 2 <= r - l) { SetTextColor(dc, RGB(255, 255, 255)); DrawTextW(dc, t, -1, &z, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX); }
    }
    SelectObject(dc, f);
    /* el punto pendiente (amarillo, punteado) */
    int pend = n2m_pendiente();
    if (pend >= 0) {
        int x = n2m_x(&b, pend);
        HPEN p = CreatePen(PS_DASH, 1, RGB(250, 204, 21)); HGDIOBJ op = SelectObject(dc, p);
        MoveToEx(dc, x, b.top + 1, NULL); LineTo(dc, x, b.bottom - 1);
        MoveToEx(dc, x + 1, b.top + 1, NULL); LineTo(dc, x + 1, b.bottom - 1);
        SelectObject(dc, op); DeleteObject(p);
        POINT tri[3] = { { x, b.top + 2 }, { x + 9, b.top + 6 }, { x, b.top + 10 } };
        br = CreateSolidBrush(RGB(250, 204, 21)); HGDIOBJ obr = SelectObject(dc, br); HGDIOBJ op2 = SelectObject(dc, GetStockObject(NULL_PEN));
        Polygon(dc, tri, 3); SelectObject(dc, obr); SelectObject(dc, op2); DeleteObject(br);
    }
    /* el marco */
    {
        HPEN p = CreatePen(PS_SOLID, 1, RGB(118, 128, 148)); HGDIOBJ op = SelectObject(dc, p); HGDIOBJ obr = SelectObject(dc, GetStockObject(NULL_BRUSH));
        Rectangle(dc, b.left, b.top, b.right + 1, b.bottom + 1);
        SelectObject(dc, op); SelectObject(dc, obr); DeleteObject(p);
    }
    /* la posición en la canción: línea amarilla y triángulo verde */
    if (g_n2m_pos >= 0) {
        int x = n2m_x(&b, g_n2m_pos);
        HPEN p = CreatePen(PS_SOLID, 2, RGB(250, 204, 21)); HGDIOBJ op = SelectObject(dc, p);
        MoveToEx(dc, x, b.top, NULL); LineTo(dc, x, b.bottom);
        SelectObject(dc, op); DeleteObject(p);
        POINT tri[3] = { { x - 7, b.top - 11 }, { x + 7, b.top - 11 }, { x, b.top - 1 } };
        br = CreateSolidBrush(RGB(74, 222, 128)); p = CreatePen(PS_SOLID, 1, RGB(20, 60, 30));
        HGDIOBJ obr = SelectObject(dc, br); op = SelectObject(dc, p);
        Polygon(dc, tri, 3);
        SelectObject(dc, obr); SelectObject(dc, op); DeleteObject(br); DeleteObject(p);
        wchar_t q[20]; n2m_formato(g_n2m_pos, q); wsprintfW(t, L"▲ %s", q);
        n2m_centrado(dc, t, c.right - N2M_PAD - 30, b.bottom + 5, &b, RGB(74, 222, 128));
    }
    if (g_n2m_arr) { n2m_formato(g_n2m_arr_ms, t); n2m_centrado(dc, t, n2m_x(&b, g_n2m_arr_ms), b.bottom + 5, &b, RGB(220, 230, 240)); }
    else if (g_n2m_hover >= b.left && g_n2m_hover <= b.right) { n2m_formato(n2m_ms(&b, g_n2m_hover), t); n2m_centrado(dc, t, g_n2m_hover, b.bottom + 5, &b, RGB(220, 230, 240)); }
    SelectObject(dc, of); DeleteObject(f); DeleteObject(fb);
    BitBlt(d0, 0, 0, c.right, c.bottom, dc, 0, 0, SRCCOPY);
    SelectObject(dc, ob); DeleteObject(bm); DeleteDC(dc);
}

/* el borde más cercano (± N2M_GRIP px): todos los bordes en ese mismo ms */
static int n2m_borde(HWND h, int x)
{
    RECT b = n2m_rect(h);
    N2M_TRAMO tr[N2_TRAMOS];
    int n = n2m_tramos(tr), mejor = N2M_GRIP + 1, val = -1;
    for (int i = 0; i < n; i++) {
        int d1 = n2m_abs(n2m_x(&b, tr[i].de) - x), d2 = n2m_abs(n2m_x(&b, tr[i].ha) - x);
        if (d1 < mejor) { mejor = d1; val = tr[i].de; }
        if (d2 < mejor) { mejor = d2; val = tr[i].ha; }
    }
    if (val < 0) return 0;
    g_n2m_arr_n = 0;
    for (int i = 0; i < n; i++) {
        if (tr[i].de == val) { g_n2m_arr_fila[g_n2m_arr_n] = tr[i].n; g_n2m_arr_ini[g_n2m_arr_n++] = 1; }
        if (tr[i].ha == val) { g_n2m_arr_fila[g_n2m_arr_n] = tr[i].n; g_n2m_arr_ini[g_n2m_arr_n++] = 0; }
    }
    g_n2m_arr_de = g_n2m_arr_ms = val; g_n2m_arr_min = 0; g_n2m_arr_max = g_n2m_dur;
    for (int i = 0; i < n; i++) {
        int mio = 0;
        for (int k = 0; k < g_n2m_arr_n; k++) if (g_n2m_arr_fila[k] == tr[i].n) {
            mio = 1;
            if (g_n2m_arr_ini[k]) { if (tr[i].ha - 1000 < g_n2m_arr_max) g_n2m_arr_max = tr[i].ha - 1000; }
            else if (tr[i].de + 1000 > g_n2m_arr_min) g_n2m_arr_min = tr[i].de + 1000;
        }
        if (mio) continue;
        if (tr[i].ha <= val && tr[i].ha > g_n2m_arr_min) g_n2m_arr_min = tr[i].ha;
        if (tr[i].de >= val && tr[i].de < g_n2m_arr_max) g_n2m_arr_max = tr[i].de;
    }
    return 1;
}

/* ShowZoneMenu: la velocidad del tramo o quitarlo */
static void n2m_menu(HWND h, const N2M_TRAMO *z)
{
    HMENU m = CreatePopupMenu();
    if (!m) return;
    wchar_t t[64], a[16], b2[16];
    n2m_formato(z->de, a); n2m_formato(z->ha, b2);
    wsprintfW(t, L"Tramo %d: %s → %s", z->n, a, b2);
    AppendMenuW(m, MF_STRING | MF_GRAYED, 0, t);
    for (int p = 50; p <= 150; p += 5) { wsprintfW(t, L"%d %%", p); AppendMenuW(m, MF_STRING | (p == z->pc ? MF_CHECKED : 0), (UINT_PTR)p, t); }
    AppendMenuW(m, MF_SEPARATOR, 0, NULL);
    AppendMenuW(m, MF_STRING, 1, L"Quitar tramo");
    POINT q; GetCursorPos(&q);
    int r = (int)TrackPopupMenu(m, TPM_RETURNCMD | TPM_RIGHTBUTTON, q.x, q.y, 0, h, NULL);
    DestroyMenu(m);
    int f = z->n - 1;
    if (r >= 50 && r <= 150) {
        SendMessageW(g_e_cb_tvel[f], CB_SETCURSEL, (WPARAM)((r - 50) / 5), 0);
        n2m_aviso(0, L"Tramo %d a %d %%.", z->n, r);
        n2m_editado();
    } else if (r == 1) {
        SetWindowTextW(g_e_ed_tde[f], L""); SetWindowTextW(g_e_ed_tha[f], L""); SendMessageW(g_e_cb_tvel[f], CB_SETCURSEL, 10, 0);
        n2m_aviso(0, L"Tramo %d quitado.", z->n);
        n2m_editado();
    }
}

static LRESULT CALLBACK n2m_barra_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    switch (m) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: { PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps); n2m_pintar(h, dc); EndPaint(h, &ps); return 0; }
    case WM_LBUTTONDOWN: case WM_RBUTTONDOWN: {
        int x = (short)LOWORD(lp), y = (short)HIWORD(lp);
        RECT b = n2m_rect(h);
        if (y < b.top - 12 || y > b.bottom + 4 || x < b.left - N2M_GRIP || x > b.right + N2M_GRIP) return 0;
        if (m == WM_LBUTTONDOWN && n2m_borde(h, x)) { g_n2m_arr = 1; SetCapture(h); InvalidateRect(h, NULL, FALSE); return 0; }
        N2M_TRAMO tr[N2_TRAMOS];
        int n = n2m_tramos(tr), ms = (int)((double)(x - b.left) / (b.right - b.left) * g_n2m_dur);
        for (int i = 0; i < n; i++) if (ms >= tr[i].de && ms < tr[i].ha) { n2m_menu(h, &tr[i]); return 0; }
        if (m == WM_LBUTTONDOWN) n2m_punto(n2m_ms(&b, x));
        return 0;
    }
    case WM_MOUSEMOVE: {
        int x = (short)LOWORD(lp);
        RECT b = n2m_rect(h);
        g_n2m_hover = x;
        if (!g_n2m_arr) {
            TRACKMOUSEEVENT t = { sizeof(t), TME_LEAVE, h, 0 }; TrackMouseEvent(&t);
        } else {
            int ms = n2m_ms(&b, x);
            g_n2m_arr_ms = ms < g_n2m_arr_min ? g_n2m_arr_min : ms > g_n2m_arr_max ? g_n2m_arr_max : ms;
        }
        InvalidateRect(h, NULL, FALSE);
        return 0;
    }
    case WM_SETCURSOR: {
        POINT p; GetCursorPos(&p); ScreenToClient(h, &p);
        RECT b = n2m_rect(h);
        int arr = g_n2m_arr, n = g_n2m_arr_n, fi[12], in[12], de = g_n2m_arr_de, ms = g_n2m_arr_ms, mn = g_n2m_arr_min, mx = g_n2m_arr_max;
        CopyMemory(fi, g_n2m_arr_fila, sizeof(fi)); CopyMemory(in, g_n2m_arr_ini, sizeof(in));
        int borde = !arr && n2m_borde(h, p.x);
        g_n2m_arr_n = n; g_n2m_arr_de = de; g_n2m_arr_ms = ms; g_n2m_arr_min = mn; g_n2m_arr_max = mx;
        CopyMemory(g_n2m_arr_fila, fi, sizeof(fi)); CopyMemory(g_n2m_arr_ini, in, sizeof(in));
        SetCursor(LoadCursorW(NULL, arr || borde ? (LPCWSTR)IDC_SIZEWE : PtInRect(&b, p) ? (LPCWSTR)IDC_HAND : (LPCWSTR)IDC_ARROW));
        return TRUE;
    }
    case WM_MOUSELEAVE: g_n2m_hover = -1; InvalidateRect(h, NULL, FALSE); return 0;
    case WM_LBUTTONUP:
        if (!g_n2m_arr) return 0;
        g_n2m_arr = 0; ReleaseCapture();
        if (g_n2m_arr_ms != g_n2m_arr_de) {
            for (int k = 0; k < g_n2m_arr_n; k++)
                n2m_poner(g_n2m_arr_ini[k] ? g_e_ed_tde[g_n2m_arr_fila[k] - 1] : g_e_ed_tha[g_n2m_arr_fila[k] - 1], g_n2m_arr_ms);
            wchar_t t[16]; n2m_formato(g_n2m_arr_ms, t);
            n2m_aviso(0, L"Borde movido a %s.", t);
            n2m_editado();
        }
        InvalidateRect(h, NULL, FALSE);
        return 0;
    }
    return DefWindowProcW(h, m, wp, lp);
}

/* RefreshSongMap: la duración, la posición y el estado (cada 150 ms) */
static void n2m_refrescar(void)
{
    if (!g_n2m) return;
    N2M_TRAMO tr[N2_TRAMOS];
    int n = n2m_tramos(tr), lejos = n2m_pendiente();
    for (int i = 0; i < n; i++) if (tr[i].ha > lejos) lejos = tr[i].ha;
    int pos = ne_tiempo_ms(), largo = ne_largo_ms();
    g_n2m_pos = pos >= 0 && ne_preparado() ? pos : -1;
    if (g_n2m_pos > lejos) lejos = g_n2m_pos;
    if (lejos < 0) lejos = 0;
    int dur = largo > 0 ? (largo > lejos + 5000 ? largo : lejos + 5000) : ((lejos + 20000) / 10000 * 10000 > 120000 ? (lejos + 20000) / 10000 * 10000 : 120000);
    if (!g_n2m_arr) g_n2m_dur = dur < 10000 ? 10000 : dur;
    if (g_n2m_barra) InvalidateRect(g_n2m_barra, NULL, FALSE);
    RECT r; GetClientRect(g_n2m, &r); r.top = r.bottom - 34;
    InvalidateRect(g_n2m, &r, FALSE);
}

static LRESULT CALLBACK n2m_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    switch (m) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps);
        RECT c; GetClientRect(h, &c);
        FillRect(dc, &c, g_n2_br_ven);
        RECT ayuda = { 10, 6, c.right - 10, 34 };
        n2_texto(dc, &ayuda, L"Clic en la barra = siguiente punto (A, B, C…). Clic en un tramo = elegir velocidad o quitarlo. "
                             L"Arrastra un borde para moverlo. El triángulo verde es tu posición en la canción.", g_n2_f, N2_SUAVE, N2_PARR);
        /* el estado y la leyenda (lento · normal · rápido) */
        N2M_TRAMO tr[N2_TRAMOS];
        wchar_t s[240];
        int n = n2m_tramos(tr);
        if (g_n2m_msj[0]) lstrcpyW(s, g_n2m_msj); else wsprintfW(s, L"%d tramo(s).", n);
        if (g_n2m_pos < 0) lstrcatW(s, L" · Habilita Entreno en una canción de práctica para ver tu posición.");
        RECT st = { 10, c.bottom - 30, c.right - 10 - 80 - 220, c.bottom - 4 };
        n2_texto(dc, &st, s, g_n2_f, g_n2m_msj_err ? N2_ERROR : N2_BIEN, N2_IZQ | DT_END_ELLIPSIS);
        static const wchar_t *LEY[3] = { L"lento", L"normal", L"rápido" };
        static const int LPC[3] = { 70, 100, 130 };
        int x = c.right - 10 - 80 - 8;
        SelectObject(dc, g_n2_f);
        for (int i = 2; i >= 0; i--) {
            SIZE z; GetTextExtentPoint32W(dc, LEY[i], lstrlenW(LEY[i]), &z);
            x -= z.cx;
            RECT q = { x, c.bottom - 30, x + z.cx + 2, c.bottom - 4 };
            n2_texto(dc, &q, LEY[i], g_n2_f, N2_SUAVE, N2_IZQ);
            x -= 16;
            RECT cuad = { x, c.bottom - 17 - 5, x + 11, c.bottom - 17 + 6 };
            HBRUSH br = CreateSolidBrush(n2m_color(LPC[i])); FillRect(dc, &cuad, br); DeleteObject(br);
            x -= 14;
        }
        EndPaint(h, &ps);
        return 0;
    }
    case WM_SIZE: {
        int W = LOWORD(lp), H = HIWORD(lp);
        if (g_n2m_barra) SetWindowPos(g_n2m_barra, NULL, 0, 34, W, H - 34 - 34, SWP_NOZORDER | SWP_NOACTIVATE);
        if (g_n2m_cerrar) SetWindowPos(g_n2m_cerrar, NULL, W - 10 - 80, H - 30, 80, 24, SWP_NOZORDER | SWP_NOACTIVATE);
        InvalidateRect(h, NULL, FALSE);
        return 0;
    }
    case WM_GETMINMAXINFO: ((MINMAXINFO *)lp)->ptMinTrackSize.x = 480; ((MINMAXINFO *)lp)->ptMinTrackSize.y = 200; return 0;
    case WM_CTLCOLORBTN: return (LRESULT)g_n2_br_ven;
    case WM_COMMAND: if ((HWND)lp == g_n2m_cerrar) DestroyWindow(h); return 0;
    case WM_TIMER: n2m_refrescar(); return 0;
    case WM_CLOSE: DestroyWindow(h); return 0;
    case WM_DESTROY: KillTimer(h, 1); g_n2m = NULL; g_n2m_barra = NULL; g_n2m_cerrar = NULL; return 0;
    }
    return DefWindowProcW(h, m, wp, lp);
}

static void n2m_abrir(void)
{
    if (g_n2m) { SetForegroundWindow(g_n2m); return; }
    static int registrada = 0;
    HINSTANCE hi = GetModuleHandleA(NULL);
    if (!registrada) {
        WNDCLASSEXW wc; ZeroMemory(&wc, sizeof(wc));
        wc.cbSize = sizeof(wc); wc.hInstance = hi; wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
        wc.lpfnWndProc = n2m_proc;       wc.lpszClassName = L"N2HMapa";      RegisterClassExW(&wc);
        wc.lpfnWndProc = n2m_barra_proc; wc.lpszClassName = L"N2HMapaBarra"; RegisterClassExW(&wc);
        registrada = 1;
    }
    DWORD est = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_CLIPCHILDREN;
    RECT r = { 0, 0, 820, 190 };
    AdjustWindowRectEx(&r, est, FALSE, WS_EX_TOOLWINDOW);
    int w = r.right - r.left, h = r.bottom - r.top;
    RECT v; GetWindowRect(g_ht_ven, &v);
    MONITORINFO mi = { sizeof(mi) }; GetMonitorInfoW(MonitorFromWindow(g_ht_ven, MONITOR_DEFAULTTONEAREST), &mi);
    int x = v.left + (v.right - v.left - w) / 2, y = v.bottom - h - 40;
    if (x + w > mi.rcWork.right) x = mi.rcWork.right - w; if (x < mi.rcWork.left) x = mi.rcWork.left;
    if (y + h > mi.rcWork.bottom) y = mi.rcWork.bottom - h; if (y < mi.rcWork.top) y = mi.rcWork.top;
    g_n2m_msj[0] = 0; g_n2m_msj_err = 0;
    g_n2m = CreateWindowExW(WS_EX_TOOLWINDOW, L"N2HMapa", L"Mapa de la canción · Ñ2Hock", est, x, y, w, h, g_ht_ven, NULL, hi, NULL);
    if (!g_n2m) return;
    {
        typedef HRESULT (WINAPI *N2_DWM)(HWND, DWORD, LPCVOID, DWORD);
        HMODULE dm = LoadLibraryA("dwmapi.dll");
        N2_DWM f = dm ? (N2_DWM)(void *)GetProcAddress(dm, "DwmSetWindowAttribute") : NULL;
        BOOL si = TRUE; if (f) f(g_n2m, 20, &si, sizeof(si));
    }
    g_n2m_barra = CreateWindowExW(0, L"N2HMapaBarra", L"", WS_CHILD | WS_VISIBLE, 0, 34, 820, 190 - 68, g_n2m, NULL, hi, NULL);
    g_n2m_cerrar = CreateWindowExW(0, L"Button", L"Cerrar", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 730, 160, 80, 24, g_n2m, NULL, hi, NULL);
    if (g_n2m_cerrar) { SendMessageW(g_n2m_cerrar, WM_SETFONT, (WPARAM)g_n2_f, 0); n2_oscuro(g_n2m_cerrar, L"DarkMode_Explorer"); }
    { RECT c; GetClientRect(g_n2m, &c); SendMessageW(g_n2m, WM_SIZE, 0, MAKELPARAM(c.right, c.bottom)); }
    n2m_refrescar();
    SetTimer(g_n2m, 1, 150, NULL);
    ShowWindow(g_n2m, SW_SHOW);
}

static void n2_per_guardar(HT_BUF *x, const char *eol)
{
    char v[96];
    wsprintfA(v, "#%02X%02X%02X", GetRValue(g_n2_acento), GetGValue(g_n2_acento), GetBValue(g_n2_acento));
    ht_buf_poner(x, "n2_acento", v, eol);
    if (!WideCharToMultiByte(CP_UTF8, 0, g_n2_letra, -1, v, sizeof(v), NULL, NULL)) v[0] = 0;
    ht_buf_poner(x, "n2_letra", v, eol);
    wsprintfA(v, "%d", g_n2_velo); ht_buf_poner(x, "n2_velo", v, eol);
    wsprintfA(v, "%d", g_n2_opac); ht_buf_poner(x, "n2_ventana", v, eol);
    wsprintfA(v, "%d", g_ht_tecla_ver); ht_buf_poner(x, "tecla", v, eol);
    wsprintfA(v, "%d", g_n2i.animar);   ht_buf_poner(x, "far_ind_animar", v, eol);
    wsprintfA(v, "%d", g_n2i.conectar); ht_buf_poner(x, "far_ind_conectar", v, eol);
    wsprintfA(v, "%d", g_n2i.ronda);    ht_buf_poner(x, "far_ind_ronda", v, eol);
    wsprintfA(v, "%d", g_n2i.negrita);  ht_buf_poner(x, "far_ind_negrita", v, eol);
    wsprintfA(v, "%d", g_n2i_arco);     ht_buf_poner(x, "far_ind_arcoiris", v, eol);
    wsprintfA(v, "%d", g_n2i.tam);      ht_buf_poner(x, "far_ind_tam", v, eol);
    wsprintfA(v, "%d", g_n2i.dura);     ht_buf_poner(x, "far_ind_dura", v, eol);
    wsprintfA(v, "%d", g_n2i.x);        ht_buf_poner(x, "far_ind_x", v, eol);
    wsprintfA(v, "%d", g_n2i.y);        ht_buf_poner(x, "far_ind_y", v, eol);
    wsprintfA(v, "#%02X%02X%02X", GetRValue(g_n2i.color), GetGValue(g_n2i.color), GetBValue(g_n2i.color));
    ht_buf_poner(x, "far_ind_color", v, eol);
    if (!WideCharToMultiByte(CP_UTF8, 0, g_n2i.letra, -1, v, sizeof(v), NULL, NULL)) v[0] = 0;
    ht_buf_poner(x, "far_ind_letra", v, eol);
    wsprintfA(v, "%d", g_n2_chat_diez);     ht_buf_poner(x, "chat_diez", v, eol);
    wsprintfA(v, "%d", g_n2_chat_en_juego); ht_buf_poner(x, "chat_en_juego", v, eol);
    wsprintfA(v, "%d", g_n2_chat_solo);     ht_buf_poner(x, "chat_solo_carrera", v, eol);
    wsprintfA(v, "%d", g_n2_chat_cod);      ht_buf_poner(x, "chat_codificacion", v, eol);
    wsprintfA(v, "%d", g_n2_vel_en_juego);  ht_buf_poner(x, "vel_en_juego", v, eol);
    {
        char u[MAX_PATH * 3];
        if (!WideCharToMultiByte(CP_UTF8, 0, g_pdr_elegida, -1, u, sizeof(u), NULL, NULL)) u[0] = 0;
        ht_buf_poner(x, "piedra", u, eol);
        if (g_ht_af_np > 0) { ht_af_texto(u, 0); ht_buf_poner(x, "autofar_curva", u, eol); }
        if (g_bo_tenir == CLR_INVALID) u[0] = 0;
        else wsprintfA(u, "#%02X%02X%02X", GetRValue(g_bo_tenir), GetGValue(g_bo_tenir), GetBValue(g_bo_tenir));
        ht_buf_poner(x, "booster_tenir", u, eol);
        wsprintfA(u, "%d", g_bo_dx); ht_buf_poner(x, "booster_x", u, eol);
        wsprintfA(u, "%d", g_bo_dy); ht_buf_poner(x, "booster_y", u, eol);
        wsprintfA(u, "%d", g_calc_opacidad); ht_buf_poner(x, "pd_opacidad", u, eol);
        wsprintfA(u, "%d", g_calc_quieto ? 1 : 0); ht_buf_poner(x, "pd_quieto", u, eol);
        wsprintfA(u, "#%06lX", (unsigned long)(g_calc_tinte & 0xFFFFFF)); ht_buf_poner(x, "pd_tinte", u, eol);
        /* ★ 26-nov: el panel nuevo, editable */
        wsprintfA(u, "%d", g_pdn_arco ? 1 : 0); ht_buf_poner(x, "pd_arcoiris", u, eol);
        wsprintfA(u, "#%06lX", (unsigned long)(g_pdn_num_color & 0xFFFFFF)); ht_buf_poner(x, "pd_numero", u, eol);
        if (g_pdn_fondo_color == 0xFFFFFFFF) u[0] = 0; else wsprintfA(u, "#%06lX", (unsigned long)(g_pdn_fondo_color & 0xFFFFFF));
        ht_buf_poner(x, "pd_fondo_color", u, eol);
        wsprintfA(u, "%d", g_pdn_fondo_op); ht_buf_poner(x, "pd_fondo_op", u, eol);
        wsprintfA(u, "%d", g_pdn_ver_abajo); ht_buf_poner(x, "pd_ver_abajo", u, eol);
        wsprintfA(u, "%d", g_pdn_ver_teclado); ht_buf_poner(x, "pd_ver_teclado", u, eol);
        if (!WideCharToMultiByte(CP_UTF8, 0, g_pdn_fondo_ruta, -1, u, sizeof(u), NULL, NULL)) u[0] = 0;
        ht_buf_poner(x, "pd_fondo", u, eol);
    }
    n2_e_guardar(x, eol);
}

/* ── las letras instaladas (InstalledFontCollection) ── */
static int CALLBACK n2_letra_una(const LOGFONTW *lf, const TEXTMETRICW *tm, DWORD tipo, LPARAM lp)
{
    (void)tm; (void)tipo;
    HWND cb = (HWND)lp;
    if (lf->lfFaceName[0] == L'@') return 1;
    if (SendMessageW(cb, CB_FINDSTRINGEXACT, (WPARAM)-1, (LPARAM)lf->lfFaceName) == CB_ERR)
        SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)lf->lfFaceName);
    return 1;
}
static void n2_letras_llenar(HWND cb, const wchar_t *elegida)
{
    if (!cb) return;
    HDC dc = GetDC(NULL);
    LOGFONTW lf; ZeroMemory(&lf, sizeof(lf)); lf.lfCharSet = DEFAULT_CHARSET;
    EnumFontFamiliesExW(dc, &lf, n2_letra_una, (LPARAM)cb, 0);
    ReleaseDC(NULL, dc);
    LRESULT k = SendMessageW(cb, CB_FINDSTRINGEXACT, (WPARAM)-1, (LPARAM)elegida);
    if (k == CB_ERR) k = SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)elegida);
    SendMessageW(cb, CB_SETCURSEL, (WPARAM)k, 0);
}

/* ── la vista previa del Far (FarIndicatorPreview): la pista y el número, que se arrastra ── */
static int g_n2_vista_arr = 0;
static void n2_vista_rect(HDC dc, int W, int H, RECT *r, HFONT *f)
{
    int juego_h = 768;
    HWND j = ht_ventana_juego();
    RECT rj;
    if (j && GetClientRect(j, &rj) && rj.bottom > 100) juego_h = rj.bottom;
    int px = g_n2i.tam * H / juego_h; if (px < 6) px = 6;
    *f = CreateFontW(-px, 0, 0, 0, g_n2i.negrita ? FW_BOLD : FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, ANTIALIASED_QUALITY, 0, g_n2i.letra);
    HGDIOBJ o = SelectObject(dc, *f);
    SIZE z; GetTextExtentPoint32W(dc, L"FAR 15.5", 8, &z);
    SelectObject(dc, o);
    int cx = g_n2i.x * W / 1000, cy = g_n2i.y * H / 1000;
    SetRect(r, cx - z.cx / 2, cy - z.cy / 2, cx - z.cx / 2 + z.cx, cy - z.cy / 2 + z.cy);
}

static LRESULT CALLBACK n2_vista_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    switch (m) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC d0 = BeginPaint(h, &ps);
        RECT c; GetClientRect(h, &c);
        int W = c.right, H = c.bottom;
        HDC dc = CreateCompatibleDC(d0);
        HBITMAP bm = CreateCompatibleBitmap(d0, W, H);
        HGDIOBJ ob = SelectObject(dc, bm);
        HBRUSH b = CreateSolidBrush(RGB(14, 16, 30)); FillRect(dc, &c, b); DeleteObject(b);
        POINT pista[4] = { { W * 43 / 100, H * 30 / 100 }, { W * 57 / 100, H * 30 / 100 }, { W * 86 / 100, H }, { W * 14 / 100, H } };
        b = CreateSolidBrush(RGB(52, 50, 82));
        HGDIOBJ obr = SelectObject(dc, b), op = SelectObject(dc, GetStockObject(NULL_PEN));
        Polygon(dc, pista, 4);
        SelectObject(dc, obr); SelectObject(dc, op); DeleteObject(b);
        n2_linea(dc, W / 2, 0, W / 2, H, RGB(70, 72, 92));
        n2_linea(dc, 0, H / 2, W, H / 2, RGB(70, 72, 92));
        RECT r; HFONT f;
        n2_vista_rect(dc, W, H, &r, &f);
        if (g_op[O_FAR_IND].quiere) {
            HGDIOBJ of = SelectObject(dc, f);
            SetBkMode(dc, TRANSPARENT);
            RECT s = r; OffsetRect(&s, 1, 1);
            SetTextColor(dc, RGB(0, 0, 0)); DrawTextW(dc, L"FAR 15.5", -1, &s, DT_SINGLELINE | DT_NOPREFIX);
            SetTextColor(dc, g_n2i.color); DrawTextW(dc, L"FAR 15.5", -1, &r, DT_SINGLELINE | DT_NOPREFIX);
            SelectObject(dc, of);
        }
        DeleteObject(f);
        BitBlt(d0, 0, 0, W, H, dc, 0, 0, SRCCOPY);
        SelectObject(dc, ob); DeleteObject(bm); DeleteDC(dc);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_LBUTTONDOWN: case WM_MOUSEMOVE: {
        if (m == WM_MOUSEMOVE && !g_n2_vista_arr) return 0;
        if (m == WM_LBUTTONDOWN) { g_n2_vista_arr = 1; SetCapture(h); }
        RECT c; GetClientRect(h, &c);
        int x = (short)LOWORD(lp), y = (short)HIWORD(lp);
        if (x < 0) x = 0; if (y < 0) y = 0; if (x > c.right) x = c.right; if (y > c.bottom) y = c.bottom;
        g_n2i.x = c.right ? x * 1000 / c.right : 500;
        g_n2i.y = c.bottom ? y * 1000 / c.bottom : 450;
        wsprintfW(g_n2_ind_estado, L"Posición: %d %% · %d %%", (g_n2i.x + 5) / 10, (g_n2i.y + 5) / 10);
        InvalidateRect(h, NULL, FALSE);
        if (g_n2_pag[6]) InvalidateRect(g_n2_pag[6], NULL, FALSE);
        return 0;
    }
    case WM_LBUTTONUP:
        if (g_n2_vista_arr) { g_n2_vista_arr = 0; ReleaseCapture(); }
        return 0;
    case WM_SETCURSOR:
        SetCursor(LoadCursorW(NULL, (LPCWSTR)IDC_SIZEALL));
        return TRUE;
    }
    return DefWindowProcW(h, m, wp, lp);
}

/* ── las pestañas de Personalización ── */
#include "n2h_piedras.c"                         /* ★ 25-nov: Personalización · Piedras */
#include "n2h_autofar.c"                         /* ★ 25-nov: Personalización · AutoFar (la curva editable) */
#include "n2h_booster.c"                         /* ★ 25-nov: Personalización · Booster (el botón lleno / sin carga, teñido) */
#include "n2h_pd.c"                              /* ★ 25-nov: Personalización · Panel PD (la calculadora 2019) */

static void n2_per_maquetar(void)
{
    /* Ventana: BuildAppearanceGroup(windowPage, 6) */
    n2_lienzo(5);
    n2_grupo(L"Personalización", 6, 160);
    n2_boton(8, 18, 64, 25, L"Fondo…", B_FONDO);
    n2_boton(76, 18, 58, 25, L"Quitar", B_QUITAR);
    n2_boton(138, 18, 58, 25, L"Color…", B_COLOR);
    n2_boton(200, 18, 82, 25, L"Restablecer", B_RESTABLECER);
    n2_lbl(8, 50, 44, 20, L"Letra", N2_C_ACENTO, N2_IZQ);
    n2_letras_llenar(n2_combo_lista(56, 49, 226, 22, L_LETRA, CBS_SORT), g_n2_letra);
    n2_lbl(8, 77, 56, 20, L"Velo", N2_C_ACENTO, N2_IZQ);
    n2_slider(64, 76, 170, 24, 3);
    n2_lbl(236, 77, 46, 20, NULL, N2_C_ACENTO, DT_RIGHT | DT_VCENTER | DT_SINGLELINE); g_n2l[g_n2nl - 1].dyn = g_n2_velo_txt;
    n2_lbl(8, 103, 56, 20, L"Ventana", N2_C_ACENTO, N2_IZQ);
    n2_slider(64, 102, 170, 24, 4);
    n2_lbl(236, 103, 46, 20, NULL, N2_C_ACENTO, DT_RIGHT | DT_VCENTER | DT_SINGLELINE); g_n2l[g_n2nl - 1].dyn = g_n2_opac_txt;
    n2_lbl(8, 131, 44, 20, L"Tema", N2_C_ACENTO, N2_IZQ);
    {
        HWND cb = n2_combo_lista(56, 130, 84, 22, L_TEMA, 0);
        if (cb) { SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)L"Oscuro"); SendMessageW(cb, CB_SETCURSEL, 0, 0); }
    }
    n2_lbl(150, 131, 38, 20, L"Tecla", N2_C_ACENTO, N2_IZQ);
    n2_combo(190, 130, 92, 22, &g_ht_tecla_ver, NULL);
    n2_lienzo(5);
    n2_lbl(8, 174, 330, 34, L"Fondo, color, letra, velo y transparencia de Ñ2Hock. Se guarda solo.", N2_SUAVE, N2_PARR);

    /* Far: FarIndicatorEditor (en el lienzo, sin recuadro) */
    n2_lienzo(6);
    g_n2_vista = CreateWindowExW(0, L"N2HVista", L"", WS_CHILD | WS_VISIBLE, 3 + 14, 3 + 12, 324, 182,
                                 g_n2_pag[6], NULL, GetModuleHandleA(NULL), NULL);
    n2_chk(14, 202, 320, 20, L"Mostrar el indicador del Far", O_FAR_IND, 0);
    n2_chk_b(14, 524, 320, 20, L"El panel del Far en la carrera (y la velocidad, en práctica)", &g_fj_mostrar);
    n2_lbl(14, 552, 160, 24, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_fj_txt_fondo;   /* ★ 26-nov */
    n2_boton(180, 550, 76, 26, L"Menos", B_FJ_FONDO_MENOS);
    n2_boton(262, 550, 76, 26, L"Más", B_FJ_FONDO_MAS);
    n2_chk_b(14, 582, 320, 20, L"Arcoíris de los crayones (panel del Far y barra de la Pausa)", &g_fj_arco);
    n2_chk_b(14, 226, 320, 20, L"Con animación (salta y se desvanece)", &g_n2i.animar);
    n2_chk_b(14, 250, 320, 20, L"Mostrar al conectar con el juego", &g_n2i.conectar);
    n2_chk_b(14, 274, 320, 20, L"Mostrar al empezar cada ronda", &g_n2i.ronda);
    n2_lbl(14, 304, 70, 24, L"Tamaño", N2_TEXTO, N2_IZQ);
    n2_slider(90, 304, 190, 24, 5);
    n2_lbl(290, 304, 50, 24, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_n2_tam_txt;
    n2_lbl(14, 336, 70, 24, L"Dura", N2_TEXTO, N2_IZQ);
    n2_slider(90, 336, 190, 24, 6);
    n2_lbl(290, 336, 50, 24, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_n2_dura_txt;
    n2_lbl(14, 370, 70, 22, L"Fuente", N2_TEXTO, N2_IZQ);
    n2_letras_llenar(n2_combo_lista(90, 370, 248, 22, L_IND_LETRA, CBS_SORT), g_n2i.letra);
    n2_chk_b(14, 402, 90, 22, L"Negrita", &g_n2i.negrita);
    n2_chk_b(250, 402, 90, 22, L"Arcoíris", &g_n2i_arco);       /* ★ 26-nov: estilo crayón Mazino */
    n2_boton(140, 400, 100, 26, L"Color...", B_IND_COLOR);
    n2_boton(14, 440, 102, 26, L"Probar", B_IND_PROBAR);
    n2_boton(125, 440, 102, 26, L"Restablecer", B_IND_FABRICA);
    n2_boton(236, 440, 102, 26, L"Guardar", B_IND_GUARDAR);
    lstrcpyW(g_n2_ind_estado, L"Arrastra el número en la vista previa.");
    n2_lbl(14, 472, 324, 44, NULL, N2_SUAVE, N2_PARR); g_n2l[g_n2nl - 1].dyn = g_n2_ind_estado;

    /* ★ 26-nov (boceto de anonimo03): el Idioma va en la ventana principal (n2_maquetar) */

    /* Piedras */
    pie_maquetar();
    /* AutoFar */
    af_maquetar();
    /* Booster */
    bo_maquetar();
    /* Panel PD */
    pd_maquetar();
}

static void n2_per_ver(int p)
{
    if (5 + p == N2P_PIEDRAS) { pie_listar(); pie_textos(); }   /* las piedras: lo que haya hoy en la carpeta */
    for (int i = 5; i < N2_PAGS_TOT; i++) if (g_n2_pag[i]) ShowWindow(g_n2_pag[i], i == 5 + p ? SW_SHOW : SW_HIDE);
}

static LRESULT CALLBACK n2_per_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    LRESULT res;
    if (n2_comun(h, m, wp, lp, &res)) return res;
    switch (m) {
    case WM_ERASEBKGND: { RECT r; GetClientRect(h, &r); FillRect((HDC)wp, &r, g_n2_br_ven); return 1; }
    case WM_PRINTCLIENT: { RECT r; GetClientRect(h, &r); FillRect((HDC)wp, &r, g_n2_br_ven); return 0; }
    case WM_NOTIFY: {
        const NMHDR *n = (const NMHDR *)lp;
        if (n->hwndFrom == g_n2_per_tabs && n->code == TCN_SELCHANGE)
            n2_per_ver((int)SendMessageW(g_n2_per_tabs, TCM_GETCURSEL, 0, 0));
        return 0;
    }
    case WM_CLOSE:
        ShowWindow(h, SW_HIDE);                      /* cerrarla sólo la esconde, como en Ñ2Hock */
        return 0;
    }
    return DefWindowProcW(h, m, wp, lp);
}

static void n2_per_armar(void)
{
    HINSTANCE hi = GetModuleHandleA(NULL);
    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(wc); wc.hInstance = hi; wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    wc.lpfnWndProc = n2_per_proc;  wc.lpszClassName = L"N2HPersonal"; RegisterClassExW(&wc);
    wc.lpfnWndProc = n2_vista_proc; wc.lpszClassName = L"N2HVista";   RegisterClassExW(&wc);
    DWORD est = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_CLIPCHILDREN;
    RECT r = { 0, 0, 368, 690 };
    AdjustWindowRectEx(&r, est, FALSE, 0);
    g_n2_per = CreateWindowExW(0, L"N2HPersonal", L"Personalización · Ñ2Hock", est, 100, 100,
                               r.right - r.left, r.bottom - r.top, g_ht_ven, NULL, hi, NULL);
    if (!g_n2_per) return;
    {
        typedef HRESULT (WINAPI *N2_DWM)(HWND, DWORD, LPCVOID, DWORD);
        HMODULE dm = LoadLibraryA("dwmapi.dll");
        N2_DWM f = dm ? (N2_DWM)(void *)GetProcAddress(dm, "DwmSetWindowAttribute") : NULL;
        BOOL si = TRUE;
        if (f) f(g_n2_per, 20, &si, sizeof(si));
    }
    g_n2_per_tabs = CreateWindowExW(0, WC_TABCONTROLW, L"", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS,
                                    0, 0, 368, 690, g_n2_per, NULL, hi, NULL);
    RECT pr = { 4, 26, 364, 686 };
    if (g_n2_per_tabs) {
        static const wchar_t *T[4] = { L"Ventana", L"Far", L"Piedras y booster", L"PD" };
        SendMessageW(g_n2_per_tabs, WM_SETFONT, (WPARAM)g_n2_ftab, 0);
        SendMessageW(g_n2_per_tabs, TCM_SETPADDING, 0, MAKELPARAM(10, 4));
        for (int i = 0; i < 4; i++) {
            TCITEMW it; ZeroMemory(&it, sizeof(it));
            it.mask = TCIF_TEXT; it.pszText = (LPWSTR)T[i];
            SendMessageW(g_n2_per_tabs, TCM_INSERTITEMW, (WPARAM)i, (LPARAM)&it);
        }
        RECT a; GetClientRect(g_n2_per_tabs, &a);
        SendMessageW(g_n2_per_tabs, TCM_ADJUSTRECT, FALSE, (LPARAM)&a);
        InflateRect(&a, -2, -1); a.top -= 1;
        pr = a;
    }
    for (int i = 5; i < N2_PAGS_TOT; i++) {
        g_n2_pag[i] = CreateWindowExW(WS_EX_CONTROLPARENT, L"N2HPagina", L"", WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS,
                                      pr.left, pr.top, pr.right - pr.left, pr.bottom - pr.top, g_n2_per, NULL, hi, NULL);
        if (g_n2_pag[i]) {
            SetWindowLongPtrW(g_n2_pag[i], GWLP_USERDATA, i);
            SetWindowPos(g_n2_pag[i], HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        }
    }
    n2_per_maquetar();
    n2_per_ver(0);
}

/* al lado de la ventana de Ñ2Hock (a la derecha si entra; si no, a la izquierda) */
static void n2_per_abrir(void)
{
    if (!g_n2_per) return;
    if (!IsWindowVisible(g_n2_per)) {
        RECT v, p; MONITORINFO mi = { sizeof(mi) };
        GetWindowRect(g_ht_ven, &v); GetWindowRect(g_n2_per, &p);
        int w = p.right - p.left, h = p.bottom - p.top;
        GetMonitorInfoW(MonitorFromWindow(g_ht_ven, MONITOR_DEFAULTTONEAREST), &mi);
        int x = v.right + 8 + w <= mi.rcWork.right ? v.right + 8 : v.left - w - 8;
        if (x < mi.rcWork.left) x = mi.rcWork.left;
        int y = v.top; if (y + h > mi.rcWork.bottom) y = mi.rcWork.bottom - h; if (y < mi.rcWork.top) y = mi.rcWork.top;
        SetWindowPos(g_n2_per, HWND_TOP, x, y, 0, 0, SWP_NOSIZE);
        lstrcpyW(g_n2_ind_estado, L"Arrastra el número en la vista previa.");
        n2_sincronizar();
        ShowWindow(g_n2_per, SW_SHOW);
    }
    SetForegroundWindow(g_n2_per);
}

static void n2_e_leer_cajas(void);
static int pie_comando(int ref);
static int af_comando(int ref);
static int bo_comando(int ref);
static int pd_comando(int ref);
static void n2_per_comando(int ref)
{
    if (pie_comando(ref) || af_comando(ref) || bo_comando(ref) || pd_comando(ref)) return;
    if (ref >= B_E_BORRAR0 && ref < B_E_BORRAR0 + N2_TRAMOS) {
        int i = ref - B_E_BORRAR0;
        SetWindowTextW(g_e_ed_tde[i], L""); SetWindowTextW(g_e_ed_tha[i], L""); SendMessageW(g_e_cb_tvel[i], CB_SETCURSEL, 10, 0);
        return;
    }
    if (ref >= B_E_MOVER0 && ref < B_E_MOVER0 + 4) {
        static const int D[4] = { -5, -1, 1, 5 };
        if (!g_e.confirmo) { n2_e_falta_confirmo(); return; }
        ne_mover(D[ref - B_E_MOVER0]);
        return;
    }
    switch (ref) {
    case B_FONDO: n2_fondo_elegir(); break;
    case B_QUITAR: n2_fondo_quitar(); break;
    case B_COLOR:
        if (n2_elegir_color(&g_n2_acento)) { n2_todo_repintar(); ht_pedir_guardar(); }
        break;
    case B_RESTABLECER:                               /* el aspecto original (no la posición) */
        g_n2_acento = N2_ACENTO_FAB; g_n2_velo = 70; g_n2_opac = 100;
        lstrcpyW(g_n2_letra, L"Sitka Text Semibold");
        n2_fondo_quitar(); n2_opacidad_aplicar(); n2_fuentes_crear();
        for (int i = 0; i < g_n2n; i++)
            if (g_n2c[i].tipo == C_COMBO && g_n2c[i].ref == L_LETRA) {
                LRESULT k = SendMessageW(g_n2c[i].h, CB_FINDSTRINGEXACT, (WPARAM)-1, (LPARAM)g_n2_letra);
                if (k != CB_ERR) SendMessageW(g_n2c[i].h, CB_SETCURSEL, (WPARAM)k, 0);
            }
        ht_pedir_guardar();
        break;
    case B_IND_COLOR:
        if (n2_elegir_color(&g_n2i.color)) { if (g_n2_vista) InvalidateRect(g_n2_vista, NULL, FALSE); }
        break;
    case B_IND_PROBAR:
        g_n2i_forzar = 1;
        if (!g_ht_ind_txt[0]) lstrcpyA(g_ht_ind_txt, "FAR 15.5");
        g_ht_ind_hasta = GetTickCount() + (DWORD)g_n2i.dura;
        g_n2_capa_firma = 0;
        lstrcpyW(g_n2_ind_estado, L"Mostrando el indicador sobre el juego.");
        break;
    case B_IND_FABRICA:
        g_n2i.animar = g_n2i.conectar = g_n2i.ronda = g_n2i.negrita = 1;
        g_n2i.tam = 48; g_n2i.dura = 900; g_n2i.x = 500; g_n2i.y = 450; g_n2i.color = RGB(0xFA, 0xCC, 0x15);
        lstrcpyW(g_n2i.letra, L"Segoe UI");
        lstrcpyW(g_n2_ind_estado, L"Valores por defecto (sin guardar).");
        break;
    case B_CHAT_VACIAR:
        nc_vaciar();
        break;
    case B_E_REINICIAR: ne_bucle_reiniciar(); break;
    case B_E_MAPA: n2m_abrir(); break;
    case B_E_GUARDAR:
        n2_e_leer_cajas();
        ht_guardar();
        ht_avisar(0, 3000, L"Ajustes de entrenamiento guardados");
        break;
    case B_E_TR_PAG:
        n2_e_tr_pagina(!g_e_tr_pag);
        break;
    case B_E_BORRAR_TODO:
        for (int i = 0; i < N2_TRAMOS; i++) { SetWindowTextW(g_e_ed_tde[i], L""); SetWindowTextW(g_e_ed_tha[i], L""); SendMessageW(g_e_cb_tvel[i], CB_SETCURSEL, 10, 0); }
        break;
    case B_IND_GUARDAR:
        ht_guardar();
        lstrcpyW(g_n2_ind_estado, L"Guardado.");
        break;
    }
    n2_sincronizar();
}

static void n2_lista_cambio(int ref, HWND h)
{
    wchar_t t[64];
    int k = (int)SendMessageW(h, CB_GETCURSEL, 0, 0);
    if (k < 0 || SendMessageW(h, CB_GETLBTEXTLEN, (WPARAM)k, 0) >= 64) return;
    SendMessageW(h, CB_GETLBTEXT, (WPARAM)k, (LPARAM)t);
    if (ref == L_CANAL) { nc_elegir_canal(k); return; }
    if (ref == L_COD) { g_n2_chat_cod = k; nc_elegir_codificacion(k); ht_pedir_guardar(); return; }
    if (ref == L_LETRA) { lstrcpyW(g_n2_letra, t); n2_fuentes_crear(); ht_pedir_guardar(); }
    else if (ref == L_IND_LETRA) { lstrcpyW(g_n2i.letra, t); if (g_n2_vista) InvalidateRect(g_n2_vista, NULL, FALSE); }
}

/* el apodo de la cuenta (usuario [0x9314E0] + 0x1A8, medido en el juego vivo): en la lista y en el título */
static void n2_apodo_tick(void)
{
    static DWORD ult = 0;
    DWORD ahora = GetTickCount();
    if (ahora - ult < 1000) return;
    ult = ahora;
    BYTE *u;
    char a[40]; a[0] = 0;
    if (ht_leer_ptr(HT_VA(0x009314E0), &u) && ht_memoria_ok(u + 0x1A8, 32, 0)) {
        int i = 0;
        for (; i < 32 && u[0x1A8 + i] >= 0x20; i++) a[i] = (char)u[0x1A8 + i];
        a[i] = 0;
        if (i == 32 || u[0x1A8 + i] != 0) a[0] = 0;              /* sin su 0 final: no es un apodo */
    }
    if (!lstrcmpA(a, g_n2_apodo)) return;
    lstrcpyA(g_n2_apodo, a);
    wchar_t w[48], tit[80];
    if (!a[0] || !MultiByteToWideChar(CP_ACP, 0, a, -1, w, 48)) lstrcpyW(w, L"Este juego");
    for (int i = 0; i < g_n2n; i++)
        if (g_n2c[i].tipo == C_COMBO && g_n2c[i].ref == L_CUENTA && g_n2c[i].h) {
            SendMessageW(g_n2c[i].h, CB_RESETCONTENT, 0, 0);
            SendMessageW(g_n2c[i].h, CB_ADDSTRING, 0, (LPARAM)w);
            SendMessageW(g_n2c[i].h, CB_SETCURSEL, 0, 0);
        }
    if (a[0]) wsprintfW(tit, L"Ñ2Hock - %s", w); else lstrcpyW(tit, L"Ñ2Hock");
    SetWindowTextW(g_ht_ven, tit);
    if (a[0] && g_n2i.conectar) g_n2i_forzar = 1;                 /* «Mostrar al conectar con el juego» */
}

/* ═══ ★ EL INDICADOR DEL FAR ENCIMA DEL JUEGO (FarIndicatorForm de Ñ2Hock) ═══
 *   anonimo03: «el far se ve pequeño». El pintor del juego tiene UNA letra fija. ⇒ Como Ñ2Hock: una ventana
 *   transparente encima del juego (no recibe clics ni foco), con el texto dibujado con la letra, el tamaño, la
 *   negrita y el color elegidos, con bordes suaves (alfa por píxel) y sombra. ⚠ En pantalla completa EXCLUSIVA
 *   no se ve (ninguna ventana se ve ahí); en ventana o ventana sin bordes, sí. */
static HWND  g_n2_capa;
static char  g_n2_capa_txt[16];
static int   g_n2_capa_w, g_n2_capa_h;
static HDC   g_n2_capa_dc; static HBITMAP g_n2_capa_bm; static DWORD *g_n2_capa_px;
static BYTE *g_n2_capa_mt, *g_n2_capa_mb, *g_n2_capa_ms;   /* ★ las máscaras: letra, borde, sombra */
static int   g_n2_capa_y0, g_n2_capa_alto;                  /* dónde está la letra (el caramelo) */

/* ★ 26-nov (anonimo03: «la letra de cuando muevo el Far, ¿se puede cambiar a la de crayón Mazino arcoíris?»):
 *   sombra, borde violeta oscuro y la letra con el arcoíris que la recorre (o su color), más clara arriba. */
static void n2_capa_componer(void)
{
    int W = g_n2_capa_w, H = g_n2_capa_h;
    if (!g_n2_capa_px || !g_n2_capa_mt) return;
    int fase = (int)((GetTickCount() % 2600) * 360 / 2600);
    int R0 = GetRValue(g_n2i.color), G0 = GetGValue(g_n2i.color), B0 = GetBValue(g_n2i.color);
    for (int y = 0; y < H; y++) {
        int rel = g_n2_capa_alto ? (y - g_n2_capa_y0) * 100 / g_n2_capa_alto : 50;
        int claro = g_n2i_arco && rel < 45 ? (45 - (rel < 0 ? 0 : rel)) : 0;
        for (int x = 0; x < W; x++) {
            int i = y * W + x, t = g_n2_capa_mt[i], b = g_n2i_arco ? g_n2_capa_mb[i] : 0, sh = g_n2_capa_ms[i] * 3 / 4;
            int a = sh, r = 0, g = 0, bl = 0;                                  /* la sombra (negra) */
            if (b) {                                                           /* el borde */
                int sa = b * 92 / 100;
                r = 18 * sa / 255 + r * (255 - sa) / 255; g = 8 * sa / 255 + g * (255 - sa) / 255;
                bl = 36 * sa / 255 + bl * (255 - sa) / 255; a = sa + a * (255 - sa) / 255;
            }
            if (t) {                                                           /* la letra */
                int cr = R0, cg = G0, cb = B0;
                if (g_n2i_arco) {
                    int hh = ((x * 300 / (W ? W : 1) - fase) % 360 + 360) % 360, sec = hh / 60, f = (hh % 60) * 255 / 60;
                    int v = 255, pp = 255 * 30 / 100, q = 255 - (255 - pp) * f / 255, u = pp + (255 - pp) * f / 255;
                    switch (sec) { case 0: cr = v; cg = u; cb = pp; break; case 1: cr = q; cg = v; cb = pp; break;
                                   case 2: cr = pp; cg = v; cb = u; break; case 3: cr = pp; cg = q; cb = v; break;
                                   case 4: cr = u; cg = pp; cb = v; break; default: cr = v; cg = pp; cb = q; break; }
                    cr += (255 - cr) * claro / 100; cg += (255 - cg) * claro / 100; cb += (255 - cb) * claro / 100;
                }
                r = cr * t / 255 + r * (255 - t) / 255; g = cg * t / 255 + g * (255 - t) / 255;
                bl = cb * t / 255 + bl * (255 - t) / 255; a = t + a * (255 - t) / 255;
            }
            g_n2_capa_px[i] = (DWORD)a << 24 | (DWORD)r << 16 | (DWORD)g << 8 | (DWORD)bl;
        }
    }
}

static LRESULT CALLBACK n2_capa_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    if (m == WM_NCHITTEST) return HTTRANSPARENT;
    return DefWindowProcW(h, m, wp, lp);
}

/* arma la imagen del cartel (premultiplicada) para el texto y el estilo de ahora */
static int n2_capa_armar(const char *txt)
{
    wchar_t w[16];
    MultiByteToWideChar(CP_ACP, 0, txt, -1, w, 16);
    int firma = g_n2i.tam * 31 + g_n2i.negrita * 7 + (int)g_n2i.color + g_n2i_arco * 1009;
    for (const wchar_t *p = g_n2i.letra; *p; p++) firma = firma * 33 + *p;
    for (const char *p = txt; *p; p++) firma = firma * 33 + *p;
    if (g_n2_capa_dc && firma == g_n2_capa_firma) return 1;
    g_n2_capa_firma = firma;
    HDC pan = GetDC(NULL);
    HFONT f = CreateFontW(-g_n2i.tam, 0, 0, 0, g_n2i.negrita ? FW_BOLD : FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0,
                          ANTIALIASED_QUALITY, 0, g_n2i.letra);
    HDC m = CreateCompatibleDC(pan);
    HGDIOBJ of = SelectObject(m, f);
    SIZE z; GetTextExtentPoint32W(m, w, lstrlenW(w), &z);
    int som = g_n2i.tam / 16 + 1, bor = g_n2i.tam / 22 + 1, W = z.cx + som + 8 + 2 * bor, H = z.cy + som + 4 + 2 * bor;
    /* dos máscaras (el texto y su sombra), en blanco sobre negro: el rojo = cuánto cubre */
    BITMAPINFO bi; ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(bi.bmiHeader); bi.bmiHeader.biWidth = W; bi.bmiHeader.biHeight = -H;
    bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32;
    DWORD *a = NULL, *b = NULL;
    HBITMAP ba = CreateDIBSection(pan, &bi, DIB_RGB_COLORS, (void **)&a, NULL, 0);
    HBITMAP bb = CreateDIBSection(pan, &bi, DIB_RGB_COLORS, (void **)&b, NULL, 0);
    if (!ba || !bb) { SelectObject(m, of); DeleteObject(f); DeleteDC(m); ReleaseDC(NULL, pan); if (ba) DeleteObject(ba); if (bb) DeleteObject(bb); return 0; }
    SetBkMode(m, TRANSPARENT); SetTextColor(m, RGB(255, 255, 255));
    HGDIOBJ ob = SelectObject(m, ba); ZeroMemory(a, (SIZE_T)W * H * 4); TextOutW(m, 4 + bor, 2 + bor, w, lstrlenW(w));
    SelectObject(m, bb); ZeroMemory(b, (SIZE_T)W * H * 4); TextOutW(m, 4 + bor + som, 2 + bor + som, w, lstrlenW(w));
    SelectObject(m, ob); SelectObject(m, of); DeleteObject(f); DeleteDC(m);
    /* la imagen final */
    if (g_n2_capa_dc) { DeleteDC(g_n2_capa_dc); DeleteObject(g_n2_capa_bm); g_n2_capa_dc = NULL; }
    g_n2_capa_bm = CreateDIBSection(pan, &bi, DIB_RGB_COLORS, (void **)&g_n2_capa_px, NULL, 0);
    g_n2_capa_dc = CreateCompatibleDC(pan);
    SelectObject(g_n2_capa_dc, g_n2_capa_bm);
    ReleaseDC(NULL, pan);
    /* las máscaras (se guardan: con arcoíris el color se recompone en cada vuelta) */
    if (g_n2_capa_mt) { HeapFree(GetProcessHeap(), 0, g_n2_capa_mt); g_n2_capa_mt = NULL; }
    BYTE *mm = (BYTE *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (SIZE_T)W * H * 3);
    if (!mm) { DeleteObject(ba); DeleteObject(bb); return 0; }
    g_n2_capa_mt = mm; g_n2_capa_mb = mm + W * H; g_n2_capa_ms = mm + 2 * W * H;
    g_n2_capa_y0 = -1; g_n2_capa_alto = 0;
    for (int i = 0; i < W * H; i++) {
        g_n2_capa_mt[i] = (BYTE)((a[i] >> 16) & 0xFF);
        g_n2_capa_ms[i] = (BYTE)((b[i] >> 16) & 0xFF);
        if (g_n2_capa_mt[i] > 60) { int y = i / W; if (g_n2_capa_y0 < 0) g_n2_capa_y0 = y; g_n2_capa_alto = y - g_n2_capa_y0 + 1; }
    }
    for (int y = 0; y < H; y++)                                            /* el borde: la letra engordada */
        for (int x = 0; x < W; x++) {
            int mx = 0;
            for (int dy = -bor; dy <= bor && mx < 255; dy++)
                for (int dx = -bor; dx <= bor; dx++) {
                    int xx = x + dx, yy = y + dy;
                    if (xx < 0 || yy < 0 || xx >= W || yy >= H || dx * dx + dy * dy > bor * bor + 1) continue;
                    int v = g_n2_capa_mt[yy * W + xx];
                    if (v > mx) mx = v;
                }
            g_n2_capa_mb[y * W + x] = (BYTE)mx;
        }
    DeleteObject(ba); DeleteObject(bb);
    g_n2_capa_w = W; g_n2_capa_h = H;
    n2_capa_componer();
    return 1;
}

/* cada 50 ms: muestra / esconde / desvanece la capa según lo que decidió el HUD (ht_indicador_tick) */
static void n2_capa_tick(void)
{
    if (!g_n2_capa) return;
    DWORD ahora = GetTickCount();
    LONG resta = (LONG)(g_ht_ind_hasta - ahora);
    HWND j = ht_ventana_juego();
    if (resta <= 0 || !g_ht_ind_txt[0] || (!g_op[O_FAR_IND].quiere && !g_n2_capa_es_vel) || g_ht_apagada || !j || IsIconic(j)) {
        if (resta <= 0) g_n2_capa_es_vel = 0;
        if (IsWindowVisible(g_n2_capa)) ShowWindow(g_n2_capa, SW_HIDE);
        return;
    }
    if (!n2_capa_armar(g_ht_ind_txt)) return;
    if (g_n2i_arco) n2_capa_componer();                                /* el arcoíris se mueve */
    RECT c; POINT o = { 0, 0 };
    GetClientRect(j, &c); ClientToScreen(j, &o);
    int x = o.x + c.right * g_n2i.x / 1000 - g_n2_capa_w / 2;
    int y = o.y + c.bottom * g_n2i.y / 1000 - g_n2_capa_h / 2;
    BYTE alfa = 255;
    LONG dentro = g_n2i.dura - resta;
    if (g_n2i.animar && resta < 300) alfa = (BYTE)(255 * resta / 300);              /* se desvanece */
    if (g_n2i.animar && dentro >= 0 && dentro < 150) y -= (int)(150 - dentro) * g_n2i.tam / 600;   /* y salta al entrar */
    POINT pd = { x, y }, ps = { 0, 0 };
    SIZE sz = { g_n2_capa_w, g_n2_capa_h };
    BLENDFUNCTION bf = { AC_SRC_OVER, 0, alfa, AC_SRC_ALPHA };
    UpdateLayeredWindow(g_n2_capa, NULL, &pd, &sz, g_n2_capa_dc, &ps, 0, &bf, ULW_ALPHA);
    if (!IsWindowVisible(g_n2_capa)) ShowWindow(g_n2_capa, SW_SHOWNOACTIVATE);
    SetWindowPos(g_n2_capa, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER);
}

static void n2_capa_armar_ventana(void)
{
    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(wc); wc.hInstance = GetModuleHandleA(NULL);
    wc.lpfnWndProc = n2_capa_proc; wc.lpszClassName = L"N2HCapaFar";
    RegisterClassExW(&wc);
    g_n2_capa = CreateWindowExW(WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                                L"N2HCapaFar", L"", WS_POPUP, 0, 0, 10, 10, NULL, NULL, wc.hInstance, NULL);
    if (g_n2_capa) g_ht_ind_ventana = 1;
}

/* el Chat: lee las líneas nuevas y refresca la lista, los canales y el estado (cada 50 ms) */
static void n2_chat_tick(void)
{
    static int v_lin = -1, v_can = -1;
    static wchar_t (*nom)[NCH_NOMBRE_W] = NULL;
    nc_tick();
    wchar_t e[160];
    int tipo = nc_estado(e, 160);
    COLORREF c = tipo > 0 ? N2_BIEN : tipo < 0 ? N2_ERROR : N2_TEXTO;
    if (lstrcmpW(e, g_n2_chat_estado) || c != g_n2_chat_estado_c) {
        lstrcpyW(g_n2_chat_estado, e); g_n2_chat_estado_c = c;
        if (g_n2_pag[4]) InvalidateRect(g_n2_pag[4], NULL, FALSE);
    }
    if (g_n2_chat_canal && nc_version_canales() != v_can) {
        v_can = nc_version_canales();
        if (!nom) nom = (wchar_t (*)[NCH_NOMBRE_W])HeapAlloc(GetProcessHeap(), 0, sizeof(wchar_t) * NCH_NOMBRE_W * 32);
        if (nom) {
            int n = nc_canales(nom, 32);
            SendMessageW(g_n2_chat_canal, CB_RESETCONTENT, 0, 0);
            for (int i = 0; i < n; i++) SendMessageW(g_n2_chat_canal, CB_ADDSTRING, 0, (LPARAM)nom[i]);
            SendMessageW(g_n2_chat_canal, CB_SETCURSEL, (WPARAM)nc_canal_actual(), 0);
        }
    }
    if (g_n2_chat_lista && nc_version() != v_lin) {
        v_lin = nc_version();
        SendMessageW(g_n2_chat_lista, WM_SETREDRAW, FALSE, 0);
        SendMessageW(g_n2_chat_lista, LB_RESETCONTENT, 0, 0);
        int n = nc_lineas();
        for (int i = 0; i < n; i++) {
            wchar_t t[512]; COLORREF col = N2_TEXTO;
            if (!nc_linea(i, t, 512, &col)) continue;
            LRESULT k = SendMessageW(g_n2_chat_lista, LB_ADDSTRING, 0, (LPARAM)t);
            if (k >= 0) SendMessageW(g_n2_chat_lista, LB_SETITEMDATA, (WPARAM)k, (LPARAM)col);
        }
        if (n > 0) SendMessageW(g_n2_chat_lista, LB_SETTOPINDEX, (WPARAM)(n - 1), 0);
        SendMessageW(g_n2_chat_lista, WM_SETREDRAW, TRUE, 0);
        InvalidateRect(g_n2_chat_lista, NULL, TRUE);
    }
}

/* comctl32 v6 (los controles con estilo de Windows 10/11) para ESTE hilo: el exe no trae el manifiesto */
static void n2_contexto_v6(void)
{
    static const char MAN[] =
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<assembly xmlns=\"urn:schemas-microsoft-com:asm.v1\" manifestVersion=\"1.0\"><dependency><dependentAssembly>"
        "<assemblyIdentity type=\"win32\" name=\"Microsoft.Windows.Common-Controls\" version=\"6.0.0.0\" "
        "processorArchitecture=\"*\" publicKeyToken=\"6595b64144ccf1df\" language=\"*\"/>"
        "</dependentAssembly></dependency></assembly>";
    wchar_t ruta[MAX_PATH];
    DWORD n = GetTempPathW(MAX_PATH - 40, ruta);
    if (!n || n > MAX_PATH - 40) return;
    lstrcatW(ruta, L"n2hock_controles6.manifest");
    HANDLE f = CreateFileW(ruta, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        DWORD e = 0;
        WriteFile(f, MAN, sizeof(MAN) - 1, &e, NULL);
        CloseHandle(f);
    }
    ACTCTXW a;
    ZeroMemory(&a, sizeof(a));
    a.cbSize = sizeof(a);
    a.lpSource = ruta;
    HANDLE ctx = CreateActCtxW(&a);
    ULONG_PTR galleta = 0;
    if (ctx != INVALID_HANDLE_VALUE && ActivateActCtx(ctx, &galleta))
        apuntar("  [tool] Ñ2Hock: controles de Windows v6 activos");
    else apuntar("  [tool] ⚠ Ñ2Hock: sin controles v6 (%u): se ven clásicos", (unsigned)GetLastError());
    HMODULE cc = LoadLibraryW(L"comctl32.dll");
    typedef BOOL (WINAPI *N2_ICC)(const INITCOMMONCONTROLSEX *);
    N2_ICC icc = cc ? (N2_ICC)(void *)GetProcAddress(cc, "InitCommonControlsEx") : NULL;
    if (icc) {
        INITCOMMONCONTROLSEX x = { sizeof(x), ICC_TAB_CLASSES | ICC_STANDARD_CLASSES };
        icc(&x);
    }
    HMODULE ux = LoadLibraryW(L"uxtheme.dll");
    if (ux) {
        typedef int (WINAPI *N2_APPMODE)(int);
        g_n2_settheme = (N2_SETTHEME)(void *)GetProcAddress(ux, "SetWindowTheme");
        /* los ordinales sin nombre del modo oscuro (Windows 10 1903+ / 11): si no están, no pasa nada */
        OSVERSIONINFOW v = { sizeof(v) };
        typedef LONG (WINAPI *N2_RTLVER)(OSVERSIONINFOW *);
        N2_RTLVER rv = (N2_RTLVER)(void *)GetProcAddress(GetModuleHandleA("ntdll.dll"), "RtlGetVersion");
        if (rv && !rv(&v) && v.dwMajorVersion >= 10 && v.dwBuildNumber >= 18362) {
            N2_APPMODE modo = (N2_APPMODE)(void *)GetProcAddress(ux, MAKEINTRESOURCEA(135));
            g_n2_allowdark = (N2_ALLOWDARK)(void *)GetProcAddress(ux, MAKEINTRESOURCEA(133));
            if (modo) modo(1);                         /* AllowDark: los menús y las listas también oscuros */
        }
    }
}

static void n2_armar(void)
{
    HINSTANCE hi = GetModuleHandleA(NULL);
    n2_contexto_v6();
    g_n2_br_ven = CreateSolidBrush(N2_VENTANA);
    g_n2_br_pag = CreateSolidBrush(N2_PAGINA);
    g_n2_br_caja = CreateSolidBrush(N2_CAJA);
    /* Segoe UI 8.25 / 7.5 pt (a 96 ppp: 11 y 10 px), normal: lo que guarda ToolBitPersonal\settings.json */
    n2_per_leer();
    n2_fuentes_crear();

    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.hInstance = hi;
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    wc.lpfnWndProc = n2_wndproc;   wc.lpszClassName = L"R2beatTool";  RegisterClassExW(&wc);
    wc.lpfnWndProc = n2_pag_proc;  wc.lpszClassName = L"N2HPagina";   RegisterClassExW(&wc);
    wc.style = CS_DBLCLKS;
    wc.lpfnWndProc = n2_slider_proc; wc.lpszClassName = L"N2HSlider"; RegisterClassExW(&wc);

    DWORD est = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_CLIPCHILDREN;
    DWORD estx = g_op[O_ANCLAR].quiere ? WS_EX_TOPMOST : 0;
    RECT r = { 0, 0, N2_W, N2_H };
    AdjustWindowRectEx(&r, est, FALSE, estx);
    g_ht_ven = CreateWindowExW(estx, L"R2beatTool", L"Ñ2Hock", est, 80, 80, r.right - r.left, r.bottom - r.top,
                               NULL, NULL, hi, NULL);
    if (!g_ht_ven) { apuntar("  [tool] ⛔ no pude crear la ventana de Ñ2Hock (%u)", (unsigned)GetLastError()); return; }
    {   /* la barra del título oscura (DWMWA_USE_IMMERSIVE_DARK_MODE = 20) */
        typedef HRESULT (WINAPI *N2_DWM)(HWND, DWORD, LPCVOID, DWORD);
        HMODULE dm = LoadLibraryA("dwmapi.dll");
        N2_DWM f = dm ? (N2_DWM)(void *)GetProcAddress(dm, "DwmSetWindowAttribute") : NULL;
        BOOL si = TRUE;
        if (f) f(g_ht_ven, 20, &si, sizeof(si));
    }
    if (g_n2_allowdark) g_n2_allowdark(g_ht_ven, TRUE);

    /* las pestañas: el TabControl de Windows, claro, como el de Ñ2Hock (ItemSize 58 x 22) */
    g_n2_tabs = CreateWindowExW(0, WC_TABCONTROLW, L"", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | TCS_FIXEDWIDTH,
                                11, 95, 308, 537, g_ht_ven, (HMENU)(INT_PTR)900, hi, NULL);
    RECT pr = { 11, 95 + 26, 11 + 308 - 4, 95 + 537 - 4 };
    if (g_n2_tabs) {
        static const wchar_t *T[N2_PAGS] = { L"Juego", L"Controles", L"Entreno", L"Tramos", L"Chat" };
        SendMessageW(g_n2_tabs, WM_SETFONT, (WPARAM)g_n2_ftab, 0);
        SendMessageW(g_n2_tabs, TCM_SETITEMSIZE, 0, MAKELPARAM(58, 22));
        for (int i = 0; i < N2_PAGS; i++) {
            TCITEMW it;
            ZeroMemory(&it, sizeof(it));
            it.mask = TCIF_TEXT;
            it.pszText = (LPWSTR)T[i];
            SendMessageW(g_n2_tabs, TCM_INSERTITEMW, (WPARAM)i, (LPARAM)&it);
        }
        RECT a; GetClientRect(g_n2_tabs, &a);
        SendMessageW(g_n2_tabs, TCM_ADJUSTRECT, FALSE, (LPARAM)&a);
        OffsetRect(&a, 11, 95);
        InflateRect(&a, -2, -1);                       /* el marco claro de la página, como en Ñ2Hock */
        a.top -= 1;
        pr = a;
    }
    for (int i = 0; i < N2_PAGS; i++) {
        g_n2_pag[i] = CreateWindowExW(WS_EX_CONTROLPARENT, L"N2HPagina", L"", WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS,
                                      pr.left, pr.top, pr.right - pr.left, pr.bottom - pr.top, g_ht_ven, NULL, hi, NULL);
        if (g_n2_pag[i]) {
            SetWindowLongPtrW(g_n2_pag[i], GWLP_USERDATA, i);
            SetWindowPos(g_n2_pag[i], HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        }
    }
    n2_maquetar();
    n2_per_armar();
    g_ht_guardar_mas = n2_per_guardar;
    g_ht_por_cuadro_mas = nc_por_cuadro;
    n2_capa_armar_ventana();
    n2_fondo_cargar();
    n2_opacidad_aplicar();
    g_n2h_activa = 1;
    n2_ver_pag(g_ht_pag >= 0 && g_ht_pag < N2_PAGS ? g_ht_pag : 0);
    SetTimer(g_ht_ven, 1, 50, NULL);
    apuntar("  [tool] ★ ventana Ñ2Hock (controles de Windows): %d controles", g_n2n);
}
