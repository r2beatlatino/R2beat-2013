/* far_juego_dibujo.c — EL PANEL DEL FAR (Y DE LA VELOCIDAD) DENTRO DEL JUEGO: dibujo transparente y mouse (26-nov-2026)
 *
 *   El panel del boceto de anonimo03, en la carrera, arriba a la derecha (bajo la rueda del booster):
 *       Far                                  auto · 17.0
 *       [x] Far Vision        [x] AutoFar
 *       ────────●──────────────────────────
 *       Velocidad                                  65 %      ← sólo en PRÁCTICA
 *       [x] Activar velocidad
 *       ────●──────────────────────────────
 *   · clic en las casillas: prende / apaga · las barras se arrastran (con AutoFar prendido manda AutoFar: su barra se
 *     ve apagada) · el título se arrastra para mover el panel (se guarda). Sin teclas (anonimo03: «ya es mucho»).
 *   TRANSPARENTE: el panel se arma con GDI dos veces (sobre negro y sobre blanco) y de la diferencia sale el alfa de
 *   cada píxel: textos y controles opacos con bordes suaves, el fondo translúcido. Una textura propia y UN
 *   DrawPrimitiveUP (pb_quad_tam, de pausa_barra.c), en el cuadro del HUD de carrera (ht_por_cuadro).
 *   Los cambios los aplica la ventana (fj_tick y n2_e_tick): acá sólo se piden.
 */

#define FJ_W 236
#define FJ_H_FAR 68
#define FJ_H_VEL 134
#define FJ_TW 256
#define FJ_TH 256

static void  *g_fj_tex = NULL, *g_fj_dev = NULL;
static int    g_fj_pool = 1, g_fj_fallo = 0;
static HDC    g_fj_dc = NULL;
static DWORD *g_fj_gdi = NULL;
static HFONT  g_fj_f = NULL, g_fj_fb = NULL;
static DWORD  g_fj_px[FJ_TW * FJ_TH];
static DWORD  g_fj_firma = 0, g_fj_visto = 0;
static DWORD  g_fj_base[FJ_TW * FJ_TH];                      /* ★ el panel SIN letras (el arcoíris las repinta) */
static DWORD  g_fj_anim_t = 0;
static int    g_fj_px0 = 0, g_fj_py0 = 0, g_fj_h = FJ_H_FAR;   /* el panel en pantalla (del último cuadro) */
static int    g_fj_arr = 0, g_fj_arr_dx = 0, g_fj_arr_dy = 0;   /* 1 moviendo el panel, 2 la barra del Far, 3 la de velocidad */
static int    g_fj_hover = -1, g_fj_practica = 0;

/* las piezas, en coordenadas del panel. ★ 28-nov: se arman según lo que se ve (Personalización · Panel Far):
 *   una parte escondida no deja hueco; sin casillas ni barra queda sólo «Far 16.5». */
static const RECT FJ_TITULO = { 0, 0, FJ_W, 20 };
static RECT FJ_CHK_FAR, FJ_CHK_AUTO, FJ_BARRA, FJ_TIT_VEL, FJ_CHK_VEL, FJ_BARRA_VEL, FJ_LINEA;
static int g_fj_hay_chk, g_fj_hay_barra, g_fj_hay_vel;
static void fj_poner(RECT *r, int l, int t, int ri, int b) { r->left = l; r->top = t; r->right = ri; r->bottom = b; }
/* -> el alto del panel */
static int fj_maquetar(int practica)
{
    int y = 20;
    g_fj_hay_chk = g_fj_ver_chk; g_fj_hay_barra = g_fj_ver_barra; g_fj_hay_vel = practica && g_fj_ver_vel;
    SetRectEmpty(&FJ_CHK_FAR); SetRectEmpty(&FJ_CHK_AUTO); SetRectEmpty(&FJ_BARRA);
    SetRectEmpty(&FJ_TIT_VEL); SetRectEmpty(&FJ_CHK_VEL); SetRectEmpty(&FJ_BARRA_VEL); SetRectEmpty(&FJ_LINEA);
    if (g_fj_hay_chk) { fj_poner(&FJ_CHK_FAR, 8, y + 4, 116, y + 22); fj_poner(&FJ_CHK_AUTO, 124, y + 4, 228, y + 22); y += 24; }
    if (g_fj_hay_barra) { fj_poner(&FJ_BARRA, 10, y + 4, 226, y + 18); y += 22; }
    if (!g_fj_hay_vel) return y + 2;
    fj_poner(&FJ_LINEA, 8, y, FJ_W - 8, y + 1);
    fj_poner(&FJ_TIT_VEL, 0, y + 4, FJ_W, y + 24);
    fj_poner(&FJ_CHK_VEL, 8, y + 26, 200, y + 44);
    fj_poner(&FJ_BARRA_VEL, 10, y + 48, 226, y + 62);
    return y + 68;
}
/* los colores elegidos (o los de fábrica) */
static COLORREF fj_c(DWORD v, COLORREF fab) { return v > 0xFFFFFF ? fab : RGB(v >> 16 & 255, v >> 8 & 255, v & 255); }
static COLORREF fj_acento(void) { return fj_c(g_fj_acento, RGB(255, 0, 128)); }
static COLORREF fj_titulo(void)
{
    if (g_fj_acento > 0xFFFFFF) return RGB(255, 40, 150);
    COLORREF a = fj_acento();                                     /* un poco más claro que las casillas */
    return RGB(GetRValue(a) + (255 - GetRValue(a)) * 15 / 100, GetGValue(a) + (255 - GetGValue(a)) * 15 / 100,
               GetBValue(a) + (255 - GetBValue(a)) * 15 / 100);
}
static COLORREF fj_numero(void) { return fj_c(g_fj_numcol, RGB(250, 204, 21)); }

static int fj_dentro(const RECT *r, int x, int y) { return x >= r->left && x < r->right && y >= r->top && y < r->bottom; }

/* ¿es una carrera de PRÁCTICA? (cGame+0x0C & 0x7F == 8, como el motor de Entreno) */
static int fj_en_practica(void)
{
    BYTE **pg = (BYTE **)HT_VA(HT_PARTIDA);
    if (!ht_memoria_ok(pg, 4, 0) || !*pg || !ht_memoria_ok(*pg + 0xC, 2, 0)) return 0;
    return (*(WORD *)(*pg + 0xC) & 0x7F) == 8;
}

static int fj_gdi(void)
{
    if (g_fj_dc) return 1;
    HDC dc = CreateCompatibleDC(NULL);
    if (!dc) return 0;
    BITMAPINFO bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = FJ_W; bi.bmiHeader.biHeight = -FJ_H_VEL; bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (!bmp || !bits) { DeleteDC(dc); return 0; }
    SelectObject(dc, bmp);
    /* ★ 26-nov (anonimo03: «Far Vision también con la letra de crayón Mazino, una que no lo haga ver feo»): la letra
     *   de los crayones ([estilos_texto] fuentes: Segoe UI Semibold), con su borde oscuro y el degradé (fj_txt_pegar) */
    SetBkMode(dc, TRANSPARENT);
    g_fj_dc = dc;
    g_fj_gdi = (DWORD *)bits;
    return 1;
}
/* ★ 28-nov: las letras (la elegida en Personalización · Panel Far, o la de los crayones); se rehacen al cambiarla */
static LONG g_fj_letra_hecha = -1;
static int fj_fuentes(void)
{
    LONG ver = g_fj_letra_ver;
    if (g_fj_f && g_fj_fb && ver == g_fj_letra_hecha) return 1;
    if (g_fj_f) { DeleteObject(g_fj_f); g_fj_f = NULL; }
    if (g_fj_fb) { DeleteObject(g_fj_fb); g_fj_fb = NULL; }
    int peso = 600;
    const char *nf = calc_fuente_crayon(&peso);
    if (!nf || !nf[0]) nf = "Segoe UI";
    if (peso < 500) peso = 600;
    wchar_t elegida[64];
    lstrcpynW(elegida, g_fj_letra, 64);
    if (elegida[0] && elegida[0] != L'(') {                       /* «(La de los crayones)» = la de siempre */
        g_fj_f = CreateFontW(-12, 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                             ANTIALIASED_QUALITY, DEFAULT_PITCH, elegida);
        g_fj_fb = CreateFontW(-14, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                              ANTIALIASED_QUALITY, DEFAULT_PITCH, elegida);
    } else {
        g_fj_f = CreateFontA(-12, 0, 0, 0, peso, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                             ANTIALIASED_QUALITY, DEFAULT_PITCH, nf);
        g_fj_fb = CreateFontA(-14, 0, 0, 0, peso + 100 > 900 ? 900 : peso + 100, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS,
                              CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, nf);
    }
    g_fj_letra_hecha = ver;
    g_fj_firma = 0;                                              /* rearmar el panel con la letra nueva */
    return g_fj_f && g_fj_fb;
}

static void fj_rect(const RECT *r, COLORREF c) { HBRUSH b = CreateSolidBrush(c); FillRect(g_fj_dc, r, b); DeleteObject(b); }
static void fj_marco(const RECT *r, COLORREF c) { HBRUSH b = CreateSolidBrush(c); FrameRect(g_fj_dc, r, b); DeleteObject(b); }
typedef struct { RECT r; wchar_t s[48]; HFONT f; COLORREF c; UINT al; } FJ_TX;
static FJ_TX g_fj_tx[16];
static int   g_fj_ntx = 0, g_fj_anotar = 0;                 /* g_fj_crayon: herramienta.c (★ 28-nov, se elige) */
static void fj_txt_viejo(const RECT *r, const wchar_t *s, HFONT f, COLORREF c, UINT al);
static void fj_txt(const RECT *r, const wchar_t *s, HFONT f, COLORREF c, UINT al)
{
    if (!g_fj_crayon) { fj_txt_viejo(r, s, f, c, al); return; }
    if (g_fj_anotar && g_fj_ntx < 16) {
        FJ_TX *t = &g_fj_tx[g_fj_ntx++];
        t->r = *r; lstrcpynW(t->s, s, 48); t->f = f; t->c = c; t->al = al;
    }
}
static void fj_txt_viejo(const RECT *r, const wchar_t *s, HFONT f, COLORREF c, UINT al)
{
    RECT q = *r;
    SelectObject(g_fj_dc, f);
    if (g_fj_fondo < 60) {                                     /* ★ 26-nov: con el fondo tenue, una sombra para leerla */
        RECT s1 = { q.left + 1, q.top + 1, q.right + 1, q.bottom + 1 };
        SetTextColor(g_fj_dc, RGB(0, 0, 0));
        DrawTextW(g_fj_dc, TR(s), -1, &s1, al | DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | DT_END_ELLIPSIS);
    }
    SetTextColor(g_fj_dc, c);
    DrawTextW(g_fj_dc, TR(s), -1, &q, al | DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | DT_END_ELLIPSIS);
}
static void fj_casilla(const RECT *r, const wchar_t *t, int on, int hover)
{
    RECT c = { r->left, r->top + 2, r->left + 14, r->top + 16 };
    if (on) fj_rect(&c, fj_acento());
    fj_marco(&c, hover ? RGB(255, 255, 255) : RGB(200, 206, 220));
    if (on) {
        HPEN p = CreatePen(PS_SOLID, 2, RGB(255, 255, 255));
        HGDIOBJ op = SelectObject(g_fj_dc, p);
        MoveToEx(g_fj_dc, c.left + 3, c.top + 7, NULL); LineTo(g_fj_dc, c.left + 6, c.top + 10); LineTo(g_fj_dc, c.left + 11, c.top + 3);
        SelectObject(g_fj_dc, op); DeleteObject(p);
    }
    RECT q = { c.right + 6, r->top, r->right, r->bottom };
    fj_txt(&q, t, g_fj_f, RGB(235, 238, 245), DT_LEFT);
}
/* una barra con su bolita: `pos` de 0 a 1000 */
static void fj_barra(const RECT *br, int pos, int apagada, int activa)
{
    RECT pista = { br->left, br->top + 5, br->right, br->top + 9 };
    fj_rect(&pista, apagada ? RGB(70, 74, 90) : RGB(110, 116, 136));
    int x = br->left + pos * (br->right - br->left) / 1000;
    RECT lleno = { br->left, pista.top, x, pista.bottom };
    if (!apagada) fj_rect(&lleno, fj_acento());
    HBRUSH b = CreateSolidBrush(apagada ? RGB(120, 124, 140) : activa ? RGB(255, 255, 255) : fj_acento());
    HPEN p = CreatePen(PS_SOLID, 1, RGB(255, 255, 255));
    HGDIOBJ ob = SelectObject(g_fj_dc, b), op = SelectObject(g_fj_dc, p);
    Ellipse(g_fj_dc, x - 6, br->top + 1, x + 6, br->top + 13);
    SelectObject(g_fj_dc, ob); SelectObject(g_fj_dc, op); DeleteObject(b); DeleteObject(p);
}

/* las piezas sobre un fondo de color `fondo` (se llama dos veces: negro y blanco) */
static void fj_piezas(COLORREF fondo, int h)
{
    RECT todo = { 0, 0, FJ_W, FJ_H_VEL };
    fj_rect(&todo, fondo);
    int fv = g_op[O_FAR].quiere, af = g_op[O_AUTOFAR].quiere, n2h = g_ht_far_n2h;
    wchar_t t[64];
    RECT r = { 8, 2, 120, 20 };
    fj_txt(&r, L"Far", g_fj_fb, fj_titulo(), DT_LEFT);
    if (!g_fj_ver_num) t[0] = 0;
    else if (af) {
        int f10 = (int)(g_ht_af_far * 10 + 0.5f);
        if (f10 > 0) wsprintfW(t, TR(L"auto · %d.%d"), f10 / 10, f10 % 10); else lstrcpyW(t, TR(L"auto"));
    } else if (fv) wsprintfW(t, L"%d.%d", n2h * 5 / 10, n2h * 5 % 10);
    else lstrcpyW(t, TR(L"el del juego"));
    RECT rv = { 90, 2, FJ_W - 8, 20 };
    if (t[0]) fj_txt(&rv, t, g_fj_fb, fj_numero(), DT_RIGHT);
    if (g_fj_hay_chk) {
        fj_casilla(&FJ_CHK_FAR, L"Far Vision", fv, g_fj_hover == 1);
        fj_casilla(&FJ_CHK_AUTO, L"AutoFar", af, g_fj_hover == 2);
    }
    if (g_fj_hay_barra) fj_barra(&FJ_BARRA, (n2h - 2) * 1000 / 42, af, g_fj_hover == 3 || g_fj_arr == 2);
    (void)h;
    if (!g_fj_hay_vel) return;
    fj_rect(&FJ_LINEA, RGB(80, 84, 100));
    RECT rt = { 8, FJ_TIT_VEL.top, 120, FJ_TIT_VEL.bottom };
    fj_txt(&rt, L"Velocidad", g_fj_fb, fj_titulo(), DT_LEFT);
    int pct = g_e.vel_pct, on = g_e.vel_on;
    wsprintfW(t, L"%d %%", pct);
    RECT rp = { 90, FJ_TIT_VEL.top, FJ_W - 8, FJ_TIT_VEL.bottom };
    if (g_fj_ver_num) fj_txt(&rp, t, g_fj_fb, on ? fj_numero() : RGB(160, 166, 180), DT_RIGHT);
    fj_casilla(&FJ_CHK_VEL, L"Activar velocidad", on, g_fj_hover == 6);
    fj_barra(&FJ_BARRA_VEL, (pct - 50) * 1000 / 100, 0, g_fj_hover == 7 || g_fj_arr == 3);
}

/* un texto «crayón» sobre g_fj_px (premultiplicado): borde oscuro y el color, más claro arriba */
static void fj_txt_pegar(const FJ_TX *t, int h)
{
    RECT a = { t->r.left - 2, t->r.top - 2, t->r.right + 2, t->r.bottom + 2 };
    if (a.left < 0) a.left = 0;
    if (a.top < 0) a.top = 0;
    if (a.right > FJ_W) a.right = FJ_W;
    if (a.bottom > h) a.bottom = h;
    for (int y = a.top; y < a.bottom; y++) for (int x = a.left; x < a.right; x++) g_fj_gdi[y * FJ_W + x] = 0;
    RECT q = t->r;
    SelectObject(g_fj_dc, t->f);
    SetTextColor(g_fj_dc, RGB(255, 255, 255));
    DrawTextW(g_fj_dc, TR(t->s), -1, &q, t->al | DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | DT_END_ELLIPSIS);
    GdiFlush();
    int y0 = -1, y1 = -1;                                        /* dónde está la letra (para el degradé) */
    for (int y = a.top; y < a.bottom; y++)
        for (int x = a.left; x < a.right; x++)
            if ((g_fj_gdi[y * FJ_W + x] >> 8 & 255) > 60) { if (y0 < 0) y0 = y; y1 = y; break; }
    if (y0 < 0) return;
    int alto = y1 - y0 + 1;
    for (int y = a.top; y < a.bottom; y++)
        for (int x = a.left; x < a.right; x++) {
            int m = g_fj_gdi[y * FJ_W + x] >> 8 & 255, b = 0;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    int xx = x + dx, yy = y + dy;
                    if (xx < a.left || yy < a.top || xx >= a.right || yy >= a.bottom) continue;
                    int v = g_fj_gdi[yy * FJ_W + xx] >> 8 & 255;
                    if (v > b) b = v;
                }
            if (!b) continue;
            DWORD *p = &g_fj_px[y * FJ_TW + x];
            DWORD d = *p;
            int da = d >> 24, dr = d >> 16 & 255, dg = d >> 8 & 255, db = d & 255;
            /* el borde: violeta muy oscuro */
            int sa = b * 85 / 100;
            dr = 16 * sa / 255 + dr * (255 - sa) / 255; dg = 8 * sa / 255 + dg * (255 - sa) / 255;
            db = 30 * sa / 255 + db * (255 - sa) / 255; da = sa + da * (255 - sa) / 255;
            if (m) {                                             /* la letra: su color, clara arriba (el caramelo) */
                int rel = (y - y0) * 100 / (alto ? alto : 1), claro = rel < 45 ? (45 - rel) : 0;
                int cr = GetRValue(t->c), cg = GetGValue(t->c), cb = GetBValue(t->c);
                if (g_fj_arco) {
                    int fase = (int)((GetTickCount() % 2600) * 360 / 2600);
                    int hh = ((x * 300 / FJ_W - fase) % 360 + 360) % 360, sec = hh / 60, f = (hh % 60) * 255 / 60;
                    int v = 255, pp = 255 * 30 / 100, q = 255 - (255 - pp) * f / 255, u = pp + (255 - pp) * f / 255;
                    switch (sec) { case 0: cr = v; cg = u; cb = pp; break; case 1: cr = q; cg = v; cb = pp; break;
                                   case 2: cr = pp; cg = v; cb = u; break; case 3: cr = pp; cg = q; cb = v; break;
                                   case 4: cr = u; cg = pp; cb = v; break; default: cr = v; cg = pp; cb = q; break; }
                }
                cr += (255 - cr) * claro / 100; cg += (255 - cg) * claro / 100; cb += (255 - cb) * claro / 100;
                dr = cr * m / 255 + dr * (255 - m) / 255; dg = cg * m / 255 + dg * (255 - m) / 255;
                db = cb * m / 255 + db * (255 - m) / 255; da = m + da * (255 - m) / 255;
            }
            *p = (DWORD)(da > 255 ? 255 : da) << 24 | (DWORD)(dr > 255 ? 255 : dr) << 16
                 | (DWORD)(dg > 255 ? 255 : dg) << 8 | (DWORD)(db > 255 ? 255 : db);
        }
}

/* el panel: dos pasadas (negro, blanco) -> alfa por píxel; encima de un velo translúcido. Premultiplicado. */
static void fj_armar(int h)
{
    static DWORD negro[FJ_W * FJ_H_VEL];
    g_fj_ntx = 0;
    g_fj_anotar = 1;
    fj_piezas(RGB(0, 0, 0), h);
    g_fj_anotar = 0;
    GdiFlush();
    CopyMemory(negro, g_fj_gdi, sizeof(negro));
    fj_piezas(RGB(255, 255, 255), h);
    GdiFlush();
    const int VELO = g_fj_fondo * 235 / 100;                    /* ★ 26-nov: Personalización · Far */
    const DWORD FR = 14, FG = 16, FB = 26;
    ZeroMemory(g_fj_px, sizeof(g_fj_px));
    for (int y = 0; y < h; y++)
        for (int x = 0; x < FJ_W; x++) {
            DWORD k = negro[y * FJ_W + x], w = g_fj_gdi[y * FJ_W + x];
            int a = 255 - (int)(((w >> 8) & 0xFF) - ((k >> 8) & 0xFF));      /* por el verde: el alfa de lo dibujado */
            if (a < 0) a = 0;
            if (a > 255) a = 255;
            DWORD cr = (k >> 16) & 0xFF, cg = (k >> 8) & 0xFF, cb = k & 0xFF;  /* sobre negro = color × alfa */
            int fa = VELO * (255 - a) / 255;
            int dx = x < 5 ? 5 - x : x > FJ_W - 6 ? x - (FJ_W - 6) : 0, dy = y < 5 ? 5 - y : y > h - 6 ? y - (h - 6) : 0;
            if (dx * dx + dy * dy > 25) fa = 0;                           /* esquinas redondeadas */
            DWORD oa = (DWORD)(a + fa), orr = cr + FR * fa / 255, og = cg + FG * fa / 255, ob = cb + FB * fa / 255;
            if (oa > 255) oa = 255;
            if (orr > 255) orr = 255;
            if (og > 255) og = 255;
            if (ob > 255) ob = 255;
            g_fj_px[y * FJ_TW + x] = (oa << 24) | (orr << 16) | (og << 8) | ob;
        }
    CopyMemory(g_fj_base, g_fj_px, sizeof(g_fj_base));
    for (int i = 0; i < g_fj_ntx; i++) fj_txt_pegar(&g_fj_tx[i], h);
}
/* ★ 26-nov: el arcoíris se mueve: sólo se repintan las letras sobre el panel guardado */
static void fj_letras_de_nuevo(int h)
{
    CopyMemory(g_fj_px, g_fj_base, sizeof(g_fj_px) < sizeof(g_fj_base) ? sizeof(g_fj_px) : sizeof(g_fj_base));
    for (int i = 0; i < g_fj_ntx; i++) fj_txt_pegar(&g_fj_tx[i], h);
}

static int fj_textura(void *dev)
{
    if (g_fj_tex && dev == g_fj_dev) return 1;
    if (g_fj_fallo) return 0;
    void **vt = *(void ***)dev;
    g_fj_tex = NULL;
    g_fj_pool = g_dispositivo_es_ex ? 0 : 1;
    long hr = ((D_CREARTEX)vt[23])(dev, FJ_TW, FJ_TH, 1, g_fj_pool ? 0 : 0x200, 21, (DWORD)g_fj_pool, &g_fj_tex, NULL);
    if (hr != 0 || !g_fj_tex) {
        apuntar("  [far_juego] ⛔ no pude crear la textura (hr=%08lX): sin panel", (unsigned long)hr);
        g_fj_fallo = 1;
        return 0;
    }
    g_fj_dev = dev;
    g_fj_firma = 0;
    return 1;
}

static int fj_subir(void)
{
    void **vt = *(void ***)g_fj_tex;
    CALC_BLOQUEO b;
    if (((T_BLOQUEAR)vt[19])(g_fj_tex, 0, &b, NULL, g_fj_pool ? 0 : 0x2000) != 0) return 0;
    for (int y = 0; y < FJ_TH; y++) CopyMemory((BYTE *)b.pBits + y * b.Pitch, g_fj_px + y * FJ_TW, FJ_TW * 4);
    ((T_SOLTAR)vt[20])(g_fj_tex, 0);
    return 1;
}

/* el cuadro del HUD de carrera (lo llama ht_por_cuadro) */
static void fj_dibujar(void)
{
    if (!g_fj_mostrar || !g_ht_arrancada || g_ht_apagada || !g_ancho || !g_alto || !ht_en_carrera()) return;
    if (!fj_gdi() || !fj_fuentes()) return;
    void *dev = pb_dispositivo();
    if (!dev || !fj_textura(dev)) return;
    g_fj_practica = fj_en_practica();
    int h = fj_maquetar(g_fj_practica);
    int es = g_fj_escala < 70 ? 70 : g_fj_escala > 200 ? 200 : g_fj_escala;   /* ★ 28-nov: el tamaño */
    int W = FJ_W * es / 100, H = h * es / 100;
    int x = g_fj_x >= 0 ? (int)((LONGLONG)g_fj_x * (int)g_ancho / 1000) : (int)g_ancho - W - 8;
    int y = g_fj_y >= 0 ? (int)((LONGLONG)g_fj_y * (int)g_alto / 1000) : (int)g_alto * 31 / 100;
    if (x > (int)g_ancho - W) x = (int)g_ancho - W;
    if (y > (int)g_alto - H) y = (int)g_alto - H;
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    g_fj_px0 = x; g_fj_py0 = y; g_fj_h = h;
    int f10 = (int)(g_ht_af_far * 10 + 0.5f);
    DWORD firma = ((DWORD)g_op[O_FAR].quiere | (DWORD)g_op[O_AUTOFAR].quiere << 1 | (DWORD)g_ht_far_n2h << 2
                   | (DWORD)(g_fj_hover + 1) << 8 | (DWORD)g_fj_arr << 12 | (DWORD)g_fj_practica << 14
                   | (DWORD)g_e.vel_on << 15 | (DWORD)g_e.vel_pct << 16) ^ (DWORD)f10 * 2654435761u ^ (DWORD)g_fj_fondo * 40503u;
    firma ^= (DWORD)g_fj_arco << 30 ^ (DWORD)g_tr_idi << 27;
    firma ^= (g_fj_acento * 2246822519u) ^ (g_fj_numcol * 3266489917u) ^ (DWORD)h * 668265263u   /* ★ 28-nov */
             ^ (DWORD)(g_fj_ver_num | g_fj_ver_chk << 1 | g_fj_ver_barra << 2 | g_fj_ver_vel << 3 | g_fj_crayon << 4) * 374761393u;
    if (firma != g_fj_firma) {
        fj_armar(h);
        if (fj_subir()) g_fj_firma = firma;
        g_fj_anim_t = GetTickCount() / 40;
    } else if (g_fj_arco && g_fj_crayon && GetTickCount() / 40 != g_fj_anim_t) {
        g_fj_anim_t = GetTickCount() / 40;
        fj_letras_de_nuevo(h);
        fj_subir();
    }
    g_pb_quad_sw = FJ_W; g_pb_quad_sh = h; g_pb_quad_suave = es != 100;
    pb_quad_tam(dev, g_fj_tex, x, y, W, H, FJ_TW, FJ_TH);
    if (!g_fj_visto) apuntar("  [far_juego] ★ el panel del Far en pantalla: %dx%d en (%d,%d), %d %%", W, H, x, y, es);
    g_fj_visto = GetTickCount() | 1;
}

static int fj_visible(void) { return g_fj_visto && (LONG)(GetTickCount() - g_fj_visto) < 300; }
static int fj_quiere_ventana(void) { return 1; }

/* ★ 26-nov: la letra de los crayones Mazino (estilos_texto.c), para el número del PD */
static const char *calc_fuente_crayon(int *peso)
{
    if (g_el_nf <= 0) return NULL;
    if (peso && g_el_peso[g_el_cual] > 0) *peso = g_el_peso[g_el_cual];
    return g_el_fuente[g_el_cual];
}

/* ★ 26-nov: para el panel nuevo del PD (calculadora.c): el Far ×10, -1 si está apagado */
static int calc_far10(void)
{
    if (g_op[O_AUTOFAR].quiere) return (int)(g_ht_af_far * 10 + 0.5f);
    if (g_op[O_FAR].quiere) return g_ht_far_n2h * 5;
    return -1;
}

/* ★ 26-nov: el panel nuevo del PD con su textura propia (512²), dibujado 1:1: nítido a cualquier tamaño.
 *   `col` = el alfa (fundido × opacidad) y el tinte del panel, como antes. */
static void  *g_pdn_tex = NULL, *g_pdn_tdev = NULL;
static int    g_pdn_tpool = 1, g_pdn_tfallo = 0, g_pdn_tnueva = 0;
static DWORD  g_pdn_visto = 0;
static int pdn_dibujar(int x, int y, DWORD col)
{
    void *dev = pb_dispositivo();
    if (!dev || g_pdn_tfallo) return 0;
    if (!g_pdn_tex || dev != g_pdn_tdev) {
        void **vt = *(void ***)dev;
        g_pdn_tex = NULL;
        g_pdn_tpool = g_dispositivo_es_ex ? 0 : 1;
        long hr = ((D_CREARTEX)vt[23])(dev, PDN_LADO, PDN_LADO, 1, g_pdn_tpool ? 0 : 0x200, 21, (DWORD)g_pdn_tpool, &g_pdn_tex, NULL);
        if (hr != 0 || !g_pdn_tex) {
            apuntar("  [calculadora] ⛔ panel nuevo: no pude crear su textura (hr=%08lX) -> el de antes", (unsigned long)hr);
            g_pdn_tfallo = 1;
            return 0;
        }
        g_pdn_tdev = dev;
        g_pdn_tnueva = 1;
        apuntar("  [calculadora] ★ panel nuevo: textura propia %dx%d (pool %d), dibujo 1:1", PDN_LADO, PDN_LADO, g_pdn_tpool);
    }
    int W, H;
    if (!pdn_armar(&W, &H)) return 0;
    if (g_pdn_cambio || g_pdn_tnueva) {
        void **vt = *(void ***)g_pdn_tex;
        CALC_BLOQUEO b;
        if (((T_BLOQUEAR)vt[19])(g_pdn_tex, 0, &b, NULL, g_pdn_tpool ? 0 : 0x2000) != 0) return 0;
        for (int yy = 0; yy < H; yy++) CopyMemory((BYTE *)b.pBits + yy * b.Pitch, g_pdn_out + yy * PDN_LADO, W * 4);
        ((T_SOLTAR)vt[20])(g_pdn_tex, 0);
        g_pdn_tnueva = 0;
    }
    DWORD a = col >> 24, r = (col >> 16 & 255) * a / 255, g = (col >> 8 & 255) * a / 255, bb = (col & 255) * a / 255;
    g_pb_quad_color = a << 24 | r << 16 | g << 8 | bb;
    pb_quad_tam(dev, g_pdn_tex, x, y, W, H, PDN_LADO, PDN_LADO);
    g_pb_quad_color = 0xFFFFFFFF;
    g_pdn_visto = GetTickCount();
    return 1;
}

/* ★ 26-nov: el panel del PD se arrastra con el mouse (si no está fijado con Z) y se guarda al soltar */
static int g_cr_arr = 0, g_cr_dx = 0, g_cr_dy = 0;
static int calc_raton(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    (void)wp;
    if (msg != WM_LBUTTONDOWN && msg != WM_MOUSEMOVE && msg != WM_LBUTTONUP) return 0;
    int vivo = g_calc_estilo && g_pdn_visto && GetTickCount() - g_pdn_visto < 300 && g_calc_vis > 0.5;
    if (!vivo) { if (g_cr_arr) { g_cr_arr = 0; ReleaseCapture(); } return 0; }
    int x, y;
    if (!pb_a_juego(h, lp, &x, &y)) return 0;
    int X = calc_redondear(g_calc_x), Y = calc_redondear(g_calc_y);
    int W = g_calc_lz_w * g_calc_escala / 100, H = g_calc_lz_h * g_calc_escala / 100;
    switch (msg) {
    case WM_LBUTTONDOWN:
        if (g_calc_fijo || x < X || x >= X + W || y < Y || y >= Y + H) return 0;
        g_cr_arr = 1; g_cr_dx = x - X; g_cr_dy = y - Y;
        SetCapture(h);
        return 1;
    case WM_MOUSEMOVE:
        if (!g_cr_arr) return 0;
        g_calc_x = x - g_cr_dx; g_calc_y = y - g_cr_dy;
        calc_acotar();
        return 0;
    case WM_LBUTTONUP:
        if (!g_cr_arr) return 0;
        g_cr_arr = 0;
        ReleaseCapture();
        calc_guardar();
        return 1;
    }
    return 0;
}

static int fj_valor_far(int lx) { int v = 2 + ((lx - FJ_BARRA.left) * 42 + 21) / (FJ_BARRA.right - FJ_BARRA.left); return v < 2 ? 2 : v > 44 ? 44 : v; }
static int fj_valor_vel(int lx)
{
    int v = 50 + ((lx - FJ_BARRA_VEL.left) * 100 + 50) / (FJ_BARRA_VEL.right - FJ_BARRA_VEL.left);
    v = (v + 2) / 5 * 5;
    return v < 50 ? 50 : v > 150 ? 150 : v;
}

/* el mouse (WndProc del juego, ANTES que el juego; 1 = el juego no lo ve) */
static int fj_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    (void)wp;
    if (!fj_visible()) {
        if (g_fj_arr) { g_fj_arr = 0; ReleaseCapture(); }
        g_fj_hover = -1;
        return 0;
    }
    if (msg != WM_MOUSEMOVE && msg != WM_LBUTTONDOWN && msg != WM_LBUTTONDBLCLK && msg != WM_LBUTTONUP) return 0;
    int x, y;
    if (!pb_a_juego(h, lp, &x, &y)) return 0;
    int es = g_fj_escala < 70 ? 70 : g_fj_escala > 200 ? 200 : g_fj_escala;   /* ★ 28-nov: el tamaño */
    int lx = (x - g_fj_px0) * 100 / es, ly = (y - g_fj_py0) * 100 / es;
    if (x < g_fj_px0) lx = -1;
    if (y < g_fj_py0) ly = -1;
    int dentro = lx >= 0 && lx < FJ_W && ly >= 0 && ly < g_fj_h;
    int vel = g_fj_practica;
    if (msg == WM_MOUSEMOVE) {
        if (g_fj_arr == 1) {
            int nx = x - g_fj_arr_dx, ny = y - g_fj_arr_dy;
            g_fj_x = (LONG)((LONGLONG)(nx < 0 ? 0 : nx) * 1000 / (g_ancho ? g_ancho : 1));
            g_fj_y = (LONG)((LONGLONG)(ny < 0 ? 0 : ny) * 1000 / (g_alto ? g_alto : 1));
        } else if (g_fj_arr == 2) InterlockedExchange(&g_fj_ped_valor, fj_valor_far(lx));
        else if (g_fj_arr == 3) InterlockedExchange(&g_fj_ped_pct, fj_valor_vel(lx));
        g_fj_hover = !dentro ? -1 : fj_dentro(&FJ_CHK_FAR, lx, ly) ? 1 : fj_dentro(&FJ_CHK_AUTO, lx, ly) ? 2
                   : fj_dentro(&FJ_BARRA, lx, ly) ? 3 : vel && fj_dentro(&FJ_CHK_VEL, lx, ly) ? 6
                   : vel && fj_dentro(&FJ_BARRA_VEL, lx, ly) ? 7 : 0;
        return 0;                                                /* el cursor del juego se sigue moviendo */
    }
    if (msg == WM_LBUTTONUP) {
        if (g_fj_arr) {
            if (g_fj_arr == 1) InterlockedExchange(&g_fj_guardar, 1);
            g_fj_arr = 0;
            ReleaseCapture();
            return 1;
        }
        return dentro;
    }
    if (!dentro) return 0;                                       /* fuera del panel, el clic es del juego */
    if (fj_dentro(&FJ_CHK_FAR, lx, ly)) InterlockedExchange(&g_fj_ped_far, 1);
    else if (fj_dentro(&FJ_CHK_AUTO, lx, ly)) InterlockedExchange(&g_fj_ped_auto, 1);
    else if (fj_dentro(&FJ_BARRA, lx, ly) && !g_op[O_AUTOFAR].quiere) {
        g_fj_arr = 2; SetCapture(h);
        InterlockedExchange(&g_fj_ped_valor, fj_valor_far(lx));
    } else if (vel && fj_dentro(&FJ_CHK_VEL, lx, ly)) InterlockedExchange(&g_fj_ped_vel, 1);
    else if (vel && fj_dentro(&FJ_BARRA_VEL, lx, ly)) {
        g_fj_arr = 3; SetCapture(h);
        InterlockedExchange(&g_fj_ped_pct, fj_valor_vel(lx));
    } else if (!fj_dentro(&FJ_BARRA, lx, ly) && !g_fj_fijo) {   /* ★ 26-nov: cualquier parte vacía mueve el panel */
        g_fj_arr = 1; g_fj_arr_dx = x - g_fj_px0; g_fj_arr_dy = y - g_fj_py0; SetCapture(h);   /* ★ 28-nov: fijo = no */
    }
    return 1;
}
