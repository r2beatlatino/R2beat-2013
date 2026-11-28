/* pausa_barra.c — A/B en la barra, con el juego en PAUSA (25-nov-2026)
 *
 *   anonimo03, comparando el Entrenamiento de Ñ2Hock con el del ToolBitDLL 0.6.40 (D:\r2beat\rnr_plugin): «A/B en la
 *   barra». El ToolBit, en la Pausa de la práctica, pone una barra de la canción donde se arrastran A y B, un clic
 *   lleva al personaje a ese punto y el clic derecho pone el final ahí. Acá, lo mismo, con NUESTRO motor
 *   (n2h_entreno.c) y las cajas Desde/Hasta de la ventana de Ñ2Hock:
 *
 *     · clic en la barra ............ ir a ese segundo (ne_mover: sólo a segundos YA tocados, hay foto por segundo)
 *     · arrastrar A o B ............. mover el inicio o el final del tramo (las cajas Desde/Hasta se escriben solas;
 *                                     con «Repetir un tramo» prendido, el bucle se reconfigura al soltar)
 *     · clic derecho ................ el final (B) ahí
 *     · Mayús + clic ................ el inicio (A) ahí
 *     · Esc ......................... sigue la carrera (lo de siempre de la Pausa; si se está arrastrando, lo cancela)
 *
 *   DÓNDE: justo ENCIMA de la barra de progreso del juego y con su mismo ancho (centro ± 389 px, la del ToolBit:
 *   [0x904084] - 0x185), así A y B caen sobre la misma escala de tiempo que ve el jugador.
 *   CÓMO SE DIBUJA: una textura nuestra (GDI en memoria, A8R8G8B8 premultiplicada) y UN DrawPrimitiveUP, guardando y
 *   devolviendo cada estado que toca (el mismo camino que estilos_texto.c). Se llama desde el dibujo de la Pausa
 *   (pau_dibujar, 0x41B2B3), así que sólo existe mientras la Pausa está en pantalla.
 *   LOS HILOS: este archivo corre en el hilo del juego (dibujo y WndProc). El motor y las cajas son del hilo de la
 *   ventana: se le dejan pedidos (g_pb_ped_*) y se lee la foto que saca n2_pb_tick (n2h_ventana.c) cada 50 ms.
 *
 *   ⛔ [pausa] barra=0 lo apaga. Necesita el dibujo de la Pausa enganchado ([pausa] repetir=1, el de fábrica) y la
 *     ventana de Ñ2Hock viva ([herramienta] activo=1).
 *   ⚠ Se incluye DESPUÉS de estilos_texto.c (usa sus typedefs D_* del dispositivo) y de pausa.c.
 */

#define PB_TW 1024                       /* la textura */
#define PB_TH 256                        /* ★ 26-nov: 256, por los tramos */
#define PB_ALTO 84                       /* el panel */
#define PB_MARGEN 18                     /* de los bordes del panel a la barra */
#define PB_BARRA_Y0 34                   /* la barra, en el panel */
#define PB_BARRA_Y1 50
#define PB_AGARRE 9                      /* px alrededor de A/B que los agarran */
/* ★ 26-nov: los tramos de velocidad (A→B, B→C…), debajo, SÓLO en la Pausa de la práctica (anonimo03) */
#define PB_ALTO_TR 172                   /* el panel con los tramos */
#define PB_TR_LINEA 70
#define PB_TR_TIT 76                     /* el título y el botón Activar */
#define PB_TR_Y0 112                     /* la barra de los tramos */
#define PB_TR_Y1 130
#define PB_TR_BOT_W 150

static DWORD  g_pb_quad_color = 0xFFFFFFFF;               /* ★ 26-nov: el color del quad (premultiplicado) */
static int    g_pb_activo = -1;          /* -1 sin leer el ini · 0 apagado · 1 prendido */
static void  *g_pb_tex = NULL, *g_pb_dev = NULL;
static int    g_pb_pool = 1, g_pb_fallo = 0;
static HDC    g_pb_dc = NULL;
static DWORD *g_pb_gdi = NULL;
static HFONT  g_pb_f = NULL, g_pb_fb = NULL;
static HDC    g_pb_mdc = NULL;                            /* ★ 26-nov: la hojita de los textos crayón */
static DWORD *g_pb_mpx = NULL;
static DWORD  g_pb_firma = 0;
static int    g_pb_x = 0, g_pb_y = 0, g_pb_w = 0;          /* el panel en pantalla (del último cuadro) */
static int    g_pb_hover = -1;                             /* x del mouse en el panel, -1 fuera */
static int    g_pb_arr = 0, g_pb_arr_ms = 0;               /* 1 arrastrando A, 2 arrastrando B */
static int    g_pb_tragar_esc = 0;
static DWORD  g_pb_dibujado = 0;                           /* GetTickCount del último cuadro con el panel */
static int    g_pb_alto = PB_ALTO, g_pb_tramos = 0;        /* ★ 26-nov: con los tramos (en práctica) es más alto */
static int    g_pb_zona = 0;                               /* el mouse: 0 nada · 1 la barra A/B · 2 los tramos · 3 el botón */
static int    g_pt_arr = 0, g_pt_arr_de = 0, g_pt_arr_ms = 0, g_pt_arr_min = 0, g_pt_arr_max = 0;   /* arrastrando un borde */
static LONG   g_pb_msj_visto = -1;
static DWORD  g_pb_msj_t = 0;                              /* cuándo llegó el último mensaje (se ve 6 s) */
static int fj_en_practica(void);                           /* far_juego_dibujo.c */

static int pb_quiere_ventana(void)
{
    if (g_pb_activo < 0) {
        char ini[MAX_PATH];
        lstrcpyA(ini, g_carpeta);
        lstrcatA(ini, "d3d9_proxy.ini");
        g_pb_activo = GetPrivateProfileIntA("pausa", "barra", 1, ini) ? 1 : 0;
        apuntar("  [pausa_barra] %s", g_pb_activo ? "ok: A/B en la barra con la Pausa abierta (si Ñ2Hock está vivo)"
                                                  : "apagada ([pausa] barra=0)");
    }
    return g_pb_activo;
}

/* ¿el panel está en pantalla? (la Pausa se dibujó hace poco y la ventana de Ñ2Hock late) */
static int pb_visible(void)
{
    DWORD t = GetTickCount();
    return g_pb_activo == 1 && g_pb_dibujado && (LONG)(t - g_pb_dibujado) < 250 && g_pb_vivo && (LONG)(t - (DWORD)g_pb_vivo) < 1000;   /* ★ con signo: el otro hilo puede ir 1 ms adelante */
}

/* ── la escala: ms <-> x del panel ── */
static int pb_dur(void)
{
    int largo = (int)g_pb_largo, pos = (int)g_pb_pos, b = (int)g_pb_b;
    if (largo > 0) return largo;
    int lejos = pos > b ? pos : b;
    for (int i = 0; i < (int)g_pt_n && i < N2_TRAMOS; i++) if ((int)g_pt_ha[i] > lejos) lejos = (int)g_pt_ha[i];
    if ((int)g_pt_pend > lejos) lejos = (int)g_pt_pend;
    int d = (lejos + 20000) / 10000 * 10000;
    return d < 120000 ? 120000 : d;
}
static int pb_x0(void) { return PB_MARGEN; }
static int pb_x1(void) { return g_pb_w - PB_MARGEN; }
static int pb_ms_a_x(int ms)
{
    int d = pb_dur();
    if (ms < 0) ms = 0;
    if (ms > d) ms = d;
    return pb_x0() + (int)((LONGLONG)ms * (pb_x1() - pb_x0()) / d);
}
static int pb_x_a_ms(int x)
{
    int d = pb_dur(), w = pb_x1() - pb_x0();
    if (w <= 0) return 0;
    if (x < pb_x0()) x = pb_x0();
    if (x > pb_x1()) x = pb_x1();
    int ms = (int)((LONGLONG)(x - pb_x0()) * d / w);
    return (ms + 500) / 1000 * 1000;                     /* m:ss: segundos enteros, como las cajas */
}
static int pb_b_efectivo(void) { return g_pb_b > 0 ? (int)g_pb_b : pb_dur(); }

/* ── GDI ── */
static int pb_gdi(void)
{
    if (g_pb_dc) return 1;
    HDC dc = CreateCompatibleDC(NULL);
    if (!dc) return 0;
    BITMAPINFO bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = PB_TW;
    bi.bmiHeader.biHeight = -PB_TH;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (!bmp || !bits) { DeleteDC(dc); return 0; }
    SelectObject(dc, bmp);
    /* ★ 26-nov: la letra de los crayones (Segoe UI Semibold), con borde oscuro y degradé (pb_txt_crayon) */
    int peso = 600;
    const char *nf = calc_fuente_crayon(&peso);
    if (!nf || !nf[0]) nf = "Segoe UI";
    if (peso < 500) peso = 600;
    g_pb_f = CreateFontA(-13, 0, 0, 0, peso, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS,
                         ANTIALIASED_QUALITY, DEFAULT_PITCH, nf);
    g_pb_fb = CreateFontA(-14, 0, 0, 0, peso + 100 > 900 ? 900 : peso + 100, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS,
                          CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, nf);
    /* la hojita para armar cada texto aparte (blanco sobre negro) */
    {
        BITMAPINFO bm;
        ZeroMemory(&bm, sizeof(bm));
        bm.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        bm.bmiHeader.biWidth = PB_TW; bm.bmiHeader.biHeight = -32; bm.bmiHeader.biPlanes = 1; bm.bmiHeader.biBitCount = 32;
        void *mb = NULL;
        HDC md = CreateCompatibleDC(NULL);
        HBITMAP mh = md ? CreateDIBSection(md, &bm, DIB_RGB_COLORS, &mb, NULL, 0) : NULL;
        if (mh && mb) { SelectObject(md, mh); SetBkMode(md, TRANSPARENT); g_pb_mdc = md; g_pb_mpx = (DWORD *)mb; }
        else if (md) DeleteDC(md);
    }
    SetBkMode(dc, TRANSPARENT);
    g_pb_dc = dc;
    g_pb_gdi = (DWORD *)bits;
    return g_pb_f && g_pb_fb;
}

static void pb_rect(int x0, int y0, int x1, int y1, COLORREF c)
{
    RECT r = { x0, y0, x1, y1 };
    HBRUSH b = CreateSolidBrush(c);
    FillRect(g_pb_dc, &r, b);
    DeleteObject(b);
}
/* ★ 26-nov (anonimo03: «si es posible en esto más»): cada texto claro con la letra de los crayones, borde violeta
 *   oscuro y más claro arriba; los títulos (blancos, en negrita) con el ARCOÍRIS que se mueve (g_fj_arco). */
static void pb_txt_crayon(int x, int y, int w, const wchar_t *s, HFONT f, COLORREF c, UINT al)
{
    int W = w + 4, H = 26;
    if (W > PB_TW) W = PB_TW;
    for (int yy = 0; yy < H; yy++) for (int xx = 0; xx < W; xx++) g_pb_mpx[yy * PB_TW + xx] = 0;
    RECT r = { 2, 2, 2 + w, 22 };
    SelectObject(g_pb_mdc, f);
    SetTextColor(g_pb_mdc, RGB(255, 255, 255));
    DrawTextW(g_pb_mdc, TR(s), -1, &r, al | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS);
    GdiFlush();
    int y0 = -1, alto = 0;
    for (int yy = 0; yy < H; yy++)
        for (int xx = 0; xx < W; xx++)
            if ((g_pb_mpx[yy * PB_TW + xx] >> 8 & 255) > 60) { if (y0 < 0) y0 = yy; alto = yy - y0 + 1; break; }
    if (y0 < 0) return;
    int arco = g_fj_arco && f == g_pb_fb && GetRValue(c) > 220 && GetGValue(c) > 220 && GetBValue(c) > 220;
    int fase = (int)((GetTickCount() % 2600) * 360 / 2600);
    for (int yy = 0; yy < H; yy++) {
        int gy = y - 2 + yy;
        if (gy < 0 || gy >= PB_TH) continue;
        int rel = (yy - y0) * 100 / (alto ? alto : 1), claro = rel < 45 ? 45 - (rel < 0 ? 0 : rel) : 0;
        for (int xx = 0; xx < W; xx++) {
            int gx = x - 2 + xx;
            if (gx < 0 || gx >= PB_TW) continue;
            int m = g_pb_mpx[yy * PB_TW + xx] >> 8 & 255, b = 0;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    int u = xx + dx, v = yy + dy;
                    if (u < 0 || v < 0 || u >= W || v >= H) continue;
                    int k = g_pb_mpx[v * PB_TW + u] >> 8 & 255;
                    if (k > b) b = k;
                }
            if (!b) continue;
            DWORD *p = &g_pb_gdi[gy * PB_TW + gx];
            int dr = *p >> 16 & 255, dg = *p >> 8 & 255, db = *p & 255, sa = b * 85 / 100;
            dr = (16 * sa + dr * (255 - sa)) / 255; dg = (8 * sa + dg * (255 - sa)) / 255; db = (30 * sa + db * (255 - sa)) / 255;
            if (m) {
                int cr = GetRValue(c), cg = GetGValue(c), cb = GetBValue(c);
                if (arco) {
                    int hh = ((gx * 300 / (g_pb_w ? g_pb_w : 1) - fase) % 360 + 360) % 360, sec = hh / 60, fr = (hh % 60) * 255 / 60;
                    int vv = 255, pp = 255 * 30 / 100, q = 255 - (255 - pp) * fr / 255, uu = pp + (255 - pp) * fr / 255;
                    switch (sec) { case 0: cr = vv; cg = uu; cb = pp; break; case 1: cr = q; cg = vv; cb = pp; break;
                                   case 2: cr = pp; cg = vv; cb = uu; break; case 3: cr = pp; cg = q; cb = vv; break;
                                   case 4: cr = uu; cg = pp; cb = vv; break; default: cr = vv; cg = pp; cb = q; break; }
                }
                cr += (255 - cr) * claro / 100; cg += (255 - cg) * claro / 100; cb += (255 - cb) * claro / 100;
                dr = (cr * m + dr * (255 - m)) / 255; dg = (cg * m + dg * (255 - m)) / 255; db = (cb * m + db * (255 - m)) / 255;
            }
            *p = (DWORD)(dr << 16 | dg << 8 | db);
        }
    }
}
static void pb_txt(int x, int y, int w, const wchar_t *s, HFONT f, COLORREF c, UINT al)
{
    s = TR(s);                                         /* ★ 26-nov: el idioma */
    if (g_pb_mpx && GetRValue(c) + GetGValue(c) + GetBValue(c) > 200) { pb_txt_crayon(x, y, w, s, f, c, al); return; }
    RECT r = { x, y, x + w, y + 20 };
    SelectObject(g_pb_dc, f);
    SetTextColor(g_pb_dc, c);
    DrawTextW(g_pb_dc, TR(s), -1, &r, al | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS);
}
static void pb_txt_centrado(int cx, int y, const wchar_t *s, HFONT f, COLORREF c)
{
    SIZE z;
    SelectObject(g_pb_dc, f);
    GetTextExtentPoint32W(g_pb_dc, s, lstrlenW(s), &z);
    int x = cx - z.cx / 2;
    if (x < 4) x = 4;
    if (x + z.cx > g_pb_w - 4) x = g_pb_w - 4 - z.cx;
    pb_txt(x, y, z.cx + 2, s, f, c, DT_LEFT);
}
static void pb_bandera(int x, const wchar_t *letra, COLORREF c)
{
    pb_rect(x - 1, PB_BARRA_Y0 - 14, x + 1, PB_BARRA_Y1 + 3, c);
    pb_rect(x - 8, PB_BARRA_Y0 - 16, x + 8, PB_BARRA_Y0 - 3, c);
    pb_txt_centrado(x, PB_BARRA_Y0 - 18, letra, g_pb_fb, RGB(12, 14, 20));
}

/* ★ 26-nov: los tramos de velocidad — A→B, B→C… (la foto de pb_tramos_tick) */
static int pt_mover(int ms) { return g_pt_arr && ms == g_pt_arr_de ? g_pt_arr_ms : ms; }
static COLORREF pt_color(int pc, int on)
{
    COLORREF c = pc < 100 ? RGB(56, 189, 248) : pc > 100 ? RGB(251, 113, 133) : RGB(148, 163, 184);
    if (on) return c;
    return RGB((GetRValue(c) + 46 * 2) / 3, (GetGValue(c) + 52 * 2) / 3, (GetBValue(c) + 68 * 2) / 3);   /* apagados: opacos */
}
static void pb_armar_tramos(int pos)
{
    wchar_t t[64];
    int w = g_pb_w, bx0 = pb_x0(), bx1 = pb_x1(), n = (int)g_pt_n, on = (int)g_pt_on;
    if (n > N2_TRAMOS) n = N2_TRAMOS;
    pb_rect(10, PB_TR_LINEA, w - 10, PB_TR_LINEA + 1, RGB(46, 52, 68));
    pb_txt(10, PB_TR_TIT, w - PB_TR_BOT_W - 30,
           n ? L"TRAMOS DE VELOCIDAD" : L"TRAMOS DE VELOCIDAD   ·   clic en la barra para marcar A, después B, C…",
           g_pb_fb, RGB(235, 238, 245), DT_LEFT);
    /* el botón «Activar tramos» */
    int b0 = w - PB_TR_BOT_W - 10;
    pb_rect(b0, PB_TR_TIT - 2, w - 10, PB_TR_TIT + 18, on ? RGB(34, 160, 110) : g_pb_zona == 3 ? RGB(78, 86, 108) : RGB(60, 66, 84));
    pb_txt(b0, PB_TR_TIT, PB_TR_BOT_W, on ? L"Tramos: activos ✓" : L"Tramos: apagados", g_pb_fb, RGB(245, 247, 250), DT_CENTER);
    /* la barra */
    pb_rect(bx0, PB_TR_Y0, bx1, PB_TR_Y1, RGB(46, 52, 68));
    for (int ms = 30000; ms < pb_dur(); ms += 30000) {
        int x = pb_ms_a_x(ms);
        pb_rect(x, PB_TR_Y1 - 4, x + 1, PB_TR_Y1, RGB(140, 150, 170));
    }
    for (int i = 0; i < n; i++) {
        int x0 = pb_ms_a_x(pt_mover((int)g_pt_de[i])), x1 = pb_ms_a_x(pt_mover((int)g_pt_ha[i])), pc = (int)g_pt_pc[i];
        if (x1 <= x0) continue;
        pb_rect(x0, PB_TR_Y0, x1, PB_TR_Y1, pt_color(pc, on));
        if (x1 - x0 >= 84) wsprintfW(t, L"%c→%c  %d %%", L'A' + i, L'B' + i, pc);
        else if (x1 - x0 >= 40) wsprintfW(t, L"%d %%", pc);
        else if (x1 - x0 >= 22) wsprintfW(t, L"%d", pc);
        else t[0] = 0;
        if (t[0]) pb_txt(x0, PB_TR_Y0 + 1, x1 - x0, t, g_pb_f, RGB(12, 14, 20), DT_CENTER);
    }
    for (int i = 0; i < n; i++) {                                 /* los bordes y sus letras */
        int x0 = pb_ms_a_x(pt_mover((int)g_pt_de[i])), x1 = pb_ms_a_x(pt_mover((int)g_pt_ha[i]));
        pb_rect(x0 - 1, PB_TR_Y0 - 4, x0 + 1, PB_TR_Y1 + 3, RGB(245, 247, 250));
        pb_rect(x1 - 1, PB_TR_Y0 - 4, x1 + 1, PB_TR_Y1 + 3, RGB(245, 247, 250));
        wchar_t l[2] = { (wchar_t)(L'A' + i), 0 }, l2[2] = { (wchar_t)(L'B' + i), 0 };
        pb_txt_centrado(x0, PB_TR_Y0 - 19, l, g_pb_fb, RGB(203, 213, 225));
        pb_txt_centrado(x1, PB_TR_Y0 - 19, l2, g_pb_fb, RGB(203, 213, 225));
    }
    if ((int)g_pt_pend >= 0) {                                   /* un inicio sin final: la línea amarilla */
        int x = pb_ms_a_x((int)g_pt_pend);
        pb_rect(x - 1, PB_TR_Y0 - 4, x + 2, PB_TR_Y1 + 3, RGB(250, 204, 21));
        wchar_t l[2] = { (wchar_t)(L'A' + n), 0 };
        pb_txt_centrado(x, PB_TR_Y0 - 19, l, g_pb_fb, RGB(250, 204, 21));
    }
    if (pos >= 0) {                                              /* tu posición */
        int x = pb_ms_a_x(pos);
        pb_rect(x - 1, PB_TR_Y0 - 2, x + 2, PB_TR_Y1 + 2, RGB(250, 204, 21));
    }
    if (g_pt_arr) {
        ne_texto_de_posicion(g_pt_arr_ms, t);
        pb_txt_centrado(pb_ms_a_x(g_pt_arr_ms), PB_TR_Y1 + 2, t, g_pb_fb, RGB(235, 238, 245));
    } else if (g_pb_zona == 2 && g_pb_hover >= bx0 && g_pb_hover <= bx1) {
        ne_texto_de_posicion(pb_x_a_ms(g_pb_hover), t);
        pb_rect(g_pb_hover, PB_TR_Y0, g_pb_hover + 1, PB_TR_Y1, RGB(235, 238, 245));
        pb_txt_centrado(g_pb_hover, PB_TR_Y1 + 2, t, g_pb_f, RGB(235, 238, 245));
    }
}

/* arma el panel en g_pb_gdi (w × g_pb_alto) */
static void pb_armar(void)
{
    wchar_t t[260], x1[16], x2[16];
    int w = g_pb_w;
    pb_rect(0, 0, PB_TW, PB_TH, RGB(0, 0, 0));
    pb_rect(0, 0, w, g_pb_alto, RGB(17, 21, 31));
    pb_rect(0, 0, w, 2, RGB(255, 0, 128));                                        /* el acento de Ñ2Hock */
    int pos = (int)g_pb_pos, a = (int)g_pb_a, b = pb_b_efectivo();
    if (g_pb_arr == 1) a = g_pb_arr_ms;
    if (g_pb_arr == 2) b = g_pb_arr_ms;
    /* el título y el estado */
    ne_texto_de_posicion(a, x1);
    if (g_pb_b > 0 || g_pb_arr == 2) ne_texto_de_posicion(b, x2); else lstrcpyW(x2, L"final");
    const wchar_t *est = !g_pb_bucle ? L"repetición apagada"
                       : !g_pb_bucle_real ? L"armado: en la próxima carrera corres hasta A"
                       : g_pb_estado == 1 ? L"esperando A" : g_pb_estado == 3 ? L"cuenta atrás"
                       : g_pb_estado == 4 ? L"antes de A, sin notas" : g_pb_estado == 6 ? L"error en el tramo" : L"repitiendo";
    if (g_pb_bucle && g_pb_vueltas > 0) wsprintfW(t, TR(L"TRAMO DE PRÁCTICA   A %s → B %s   ·   %s (vuelta %ld)"), x1, x2, est, g_pb_vueltas);
    else wsprintfW(t, TR(L"TRAMO DE PRÁCTICA   A %s → B %s   ·   %s"), x1, x2, est);
    pb_txt(10, 5, w - 20, t, g_pb_fb, RGB(235, 238, 245), DT_LEFT);
    if (pos >= 0) {
        wchar_t p[16], l[16];
        ne_texto_de_posicion(pos, p);
        ne_texto_de_posicion(pb_dur(), l);
        wsprintfW(t, L"%s / %s", p, l);
        pb_txt(10, 5, w - 20, t, g_pb_fb, RGB(250, 204, 21), DT_RIGHT);
    }
    /* la barra: la pista, el tramo A–B, las marcas de cada 30 s */
    int bx0 = pb_x0(), bx1 = pb_x1();
    pb_rect(bx0, PB_BARRA_Y0, bx1, PB_BARRA_Y1, RGB(46, 52, 68));
    int xa = pb_ms_a_x(a), xb = pb_ms_a_x(b);
    if (xb > xa) pb_rect(xa, PB_BARRA_Y0, xb, PB_BARRA_Y1, g_pb_bucle_real ? RGB(34, 160, 110) : RGB(58, 110, 96));
    for (int ms = 30000; ms < pb_dur(); ms += 30000) {
        int x = pb_ms_a_x(ms);
        pb_rect(x, PB_BARRA_Y1 - 4, x + 1, PB_BARRA_Y1, RGB(140, 150, 170));
    }
    /* tu posición */
    if (pos >= 0) {
        int x = pb_ms_a_x(pos);
        pb_rect(x - 1, PB_BARRA_Y0 - 4, x + 2, PB_BARRA_Y1 + 4, RGB(250, 204, 21));
    }
    pb_bandera(xa, L"A", RGB(74, 222, 128));
    pb_bandera(xb, L"B", RGB(248, 113, 113));
    /* el tiempo bajo el mouse (o el que se arrastra) */
    if (g_pb_arr) {
        ne_texto_de_posicion(g_pb_arr_ms, t);
        pb_txt_centrado(pb_ms_a_x(g_pb_arr_ms), PB_BARRA_Y1 + 3, t, g_pb_fb, RGB(235, 238, 245));
    } else if (g_pb_zona == 1 && g_pb_hover >= bx0 && g_pb_hover <= bx1) {
        ne_texto_de_posicion(pb_x_a_ms(g_pb_hover), t);
        pb_rect(g_pb_hover, PB_BARRA_Y0, g_pb_hover + 1, PB_BARRA_Y1, RGB(235, 238, 245));
        pb_txt_centrado(g_pb_hover, PB_BARRA_Y1 + 3, t, g_pb_f, RGB(235, 238, 245));
    }
    if (g_pb_tramos) pb_armar_tramos(pos);
    /* la ayuda o lo último que dijo el motor (6 s) */
    int ay = g_pb_alto - 19;
    if (g_pb_msj[0] && GetTickCount() - g_pb_msj_t < 6000)
        pb_txt(10, ay, w - 20, g_pb_msj, g_pb_f, g_pb_msj_err ? RGB(251, 146, 60) : RGB(94, 234, 212), DT_LEFT);
    else if (g_pb_tramos && (g_pb_zona >= 2 || g_pt_arr))
        pb_txt(10, ay, w - 20, L"Clic: marcar A, B, C…   ·   Arrastra los bordes   ·   Rueda o clic en un tramo: ±5 %   ·   Clic derecho: quitarlo",
               g_pb_f, RGB(150, 160, 180), DT_LEFT);
    else if (!g_pb_prep && pos < 0)
        pb_txt(10, ay, w - 20, L"Para ir a un segundo, habilita Entreno en Ñ2Hock (pestaña Entrenamiento).", g_pb_f,
               RGB(251, 146, 60), DT_LEFT);
    else
        pb_txt(10, ay, w - 20, L"Clic: ir ahí   ·   Arrastra A y B   ·   Clic derecho: B ahí   ·   Mayús+clic: A ahí   ·   Esc: seguir",
               g_pb_f, RGB(150, 160, 180), DT_LEFT);
    GdiFlush();
    /* el alfa: el panel al 92 %, esquinas redondeadas; premultiplicado */
    for (int y = 0; y < PB_TH; y++)
        for (int x = 0; x < PB_TW; x++) {
            DWORD *p = g_pb_gdi + y * PB_TW + x;
            int al = (x < w && y < g_pb_alto) ? 235 : 0;
            if (al) {
                int dx = x < 6 ? 6 - x : x > w - 7 ? x - (w - 7) : 0, dy = y < 6 ? 6 - y : y > g_pb_alto - 7 ? y - (g_pb_alto - 7) : 0;
                if (dx * dx + dy * dy > 36) al = 0;
            }
            DWORD c = *p;
            DWORD r = ((c >> 16) & 0xFF) * al / 255, g = ((c >> 8) & 0xFF) * al / 255, bb = (c & 0xFF) * al / 255;
            *p = ((DWORD)al << 24) | (r << 16) | (g << 8) | bb;
        }
}

/* ── D3D ── */
static void *pb_dispositivo(void)
{
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    void *envol = *(void **)(base + (0x931498 - 0x400000));
    if (!envol) return NULL;
    void **vt = *(void ***)envol;
    return ((F_EL_DEV)vt[0x58 / 4])(envol);
}

static int pb_textura(void *dev)
{
    if (g_pb_tex && dev == g_pb_dev) return 1;
    if (g_pb_fallo) return 0;
    void **vt = *(void ***)dev;
    g_pb_tex = NULL;
    g_pb_pool = g_dispositivo_es_ex ? 0 : 1;                /* el 9Ex no tiene MANAGED: DEFAULT + DYNAMIC */
    long hr = ((D_CREARTEX)vt[23])(dev, PB_TW, PB_TH, 1, g_pb_pool ? 0 : 0x200, 21 /* A8R8G8B8 */, (DWORD)g_pb_pool,
                                   &g_pb_tex, NULL);
    if (hr != 0 || !g_pb_tex) {
        apuntar("  [pausa_barra] ⛔ no pude crear la textura (hr=%08lX): sin barra", (unsigned long)hr);
        g_pb_fallo = 1;
        return 0;
    }
    g_pb_dev = dev;
    g_pb_firma = 0;
    return 1;
}

static int pb_subir(void)
{
    void **vt = *(void ***)g_pb_tex;
    CALC_BLOQUEO b;
    if (((T_BLOQUEAR)vt[19])(g_pb_tex, 0, &b, NULL, g_pb_pool ? 0 : 0x2000 /* DISCARD */) != 0) return 0;
    for (int y = 0; y < PB_TH; y++) CopyMemory((BYTE *)b.pBits + y * b.Pitch, g_pb_gdi + y * PB_TW, PB_TW * 4);
    ((T_SOLTAR)vt[20])(g_pb_tex, 0);
    return 1;
}

/* un quad con la textura `tex` (w × h en pantalla, de una textura tw × th). ★ 26-nov: también lo usa el panel del Far */
/* ★ 28-nov: para dibujar AGRANDADO o achicado (el panel del Far): el tamaño de lo pintado en la textura (0 = el
 *   mismo que en pantalla) y el filtro suave. Se ponen justo antes de pb_quad_tam y él los vuelve a 0. */
static int g_pb_quad_sw = 0, g_pb_quad_sh = 0, g_pb_quad_suave = 0;
static void pb_quad_tam(void *dev, void *tex, int x, int y, int w, int h, int tw, int th)
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
    DWORD sa[][2] = { { 1, 3 }, { 2, 3 }, { 5, 1 }, { 6, 1 }, { 7, 0 }, { 11, 0 } };
    if (g_pb_quad_suave) { sa[2][1] = 2; sa[3][1] = 2; }        /* ★ 28-nov: LINEAR al escalar */
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
    ((D_TEX)vt[65])(dev, 0, tex);
    ((D_PTR)vt[92])(dev, NULL);
    ((D_PTR)vt[107])(dev, NULL);
    ((D_DW)vt[89])(dev, 0x144);                                /* XYZRHW | DIFFUSE | TEX1 */
    struct { float x, y, z, w; DWORD c; float u, v; } q[4];
    float x0 = (float)x - 0.5f, y0 = (float)y - 0.5f, xx = x0 + (float)w, yy = y0 + (float)h;
    float u1 = (float)(g_pb_quad_sw ? g_pb_quad_sw : w) / tw, v1 = (float)(g_pb_quad_sh ? g_pb_quad_sh : h) / th;
    g_pb_quad_sw = g_pb_quad_sh = g_pb_quad_suave = 0;
    float px[4][4] = { { x0, y0, 0, 0 }, { xx, y0, u1, 0 }, { x0, yy, 0, v1 }, { xx, yy, u1, v1 } };
    for (int i = 0; i < 4; i++) {
        q[i].x = px[i][0]; q[i].y = px[i][1]; q[i].z = 0; q[i].w = 1;
        q[i].c = g_pb_quad_color; q[i].u = px[i][2]; q[i].v = px[i][3];
    }
    ((D_UP)vt[83])(dev, 5 /* TRIANGLESTRIP */, 2, q, sizeof(q[0]));

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

/* ── cada cuadro de la Pausa (lo llama pau_dibujar) ── */
/* ★ 26-nov: la Pausa NO se dibuja en todos los cuadros (anonimo03: «esta barra parpadea mucho»). Entonces
 *   pau_dibujar sólo avisa «la Pausa está abierta» y el panel se pinta en CADA cuadro desde ht_por_cuadro (como el
 *   panel del Far, que no parpadea). Si ht_por_cuadro no llegara a correr, pau_dibujar lo pinta igual. */
static DWORD g_pb_pausa_t = 0;                                  /* GetTickCount del último dibujo de la Pausa del juego */
/* ★ 26-nov (diagnóstico del parpadeo): cuántas veces pasa cada cosa, al registro cada 2 s (15 líneas como mucho) */
static int g_pbd_pau, g_pbd_cuadro, g_pbd_pintar, g_pbd_vivo, g_pbd_dev, g_pbd_armar, g_pbd_subir_mal, g_pbd_quad, g_pbd_chico, g_pbd_lineas;
static DWORD g_pbd_t;
static void pbd_contar(void)
{
    DWORD t = GetTickCount();
    if (!g_pbd_t) g_pbd_t = t;
    if (t - g_pbd_t < 2000 || g_pbd_lineas >= 2) return;
    g_pbd_lineas++;
    apuntar("  [pausa_barra] diag 2s: pausa %d · cuadro %d · pintar %d · sin_vivo %d · sin_dev %d · armar %d · subir_mal %d · dibujos %d · chico %d · pos %ld",
            g_pbd_pau, g_pbd_cuadro, g_pbd_pintar, g_pbd_vivo, g_pbd_dev, g_pbd_armar, g_pbd_subir_mal, g_pbd_quad, g_pbd_chico, (long)g_pb_pos);
    g_pbd_pau = g_pbd_cuadro = g_pbd_pintar = g_pbd_vivo = g_pbd_dev = g_pbd_armar = g_pbd_subir_mal = g_pbd_quad = g_pbd_chico = 0;
    g_pbd_t = t;
}
static void pb_pintar(void);
static void pb_dibujar(void)
{
    g_pb_pausa_t = GetTickCount() | 1;
    g_pbd_pau++;
    if (!g_pb_dibujado || (LONG)(GetTickCount() - g_pb_dibujado) > 60) pb_pintar();
}
static void pb_por_cuadro(void)
{
    if (g_pb_pausa_t && (LONG)(GetTickCount() - g_pb_pausa_t) < 350) { g_pbd_cuadro++; pb_pintar(); pbd_contar(); }
}
static void pb_pintar(void)
{
    g_pb_visto = (LONG)(GetTickCount() | 1);                    /* la ventana de Ñ2Hock lee la posición sólo con esto */
    if (g_pb_activo < 0) pb_quiere_ventana();                   /* ★ 26-nov: con alt+enter, enganchar_ventana no lo llegaba a leer */
    g_pbd_pintar++;
    if (g_pb_activo != 1 || !g_pb_vivo || (LONG)(GetTickCount() - (DWORD)g_pb_vivo) > 1000) { g_pbd_vivo++; return; }   /* ★ con signo (el parpadeo) */
    if (!g_ancho || !g_alto || !pb_gdi()) return;
    void *dev = pb_dispositivo();
    if (!dev || !pb_textura(dev)) { g_pbd_dev++; return; }
    /* centro ± 389 px (la barra de progreso del juego), encima de ella */
    int cx = (int)g_ancho / 2, w = 778;
    if (w > (int)g_ancho - 16) w = (int)g_ancho - 16;
    if (w > PB_TW) w = PB_TW;
    g_pb_w = w;
    g_pb_x = cx - w / 2;
    g_pb_tramos = fj_en_practica();                              /* ★ 26-nov: los tramos, sólo en práctica */
    g_pb_alto = g_pb_tramos ? PB_ALTO_TR : PB_ALTO;
    g_pb_y = (int)g_alto - 66 - 10 - g_pb_alto;
    if (g_pb_msj_serie != g_pb_msj_visto) { g_pb_msj_visto = g_pb_msj_serie; g_pb_msj_t = GetTickCount(); }
    if (g_pb_y < 0) g_pb_y = 0;
    DWORD firma = (DWORD)g_pb_pos / 250 * 2654435761u ^ (DWORD)g_pb_largo * 40503u ^ (DWORD)g_pb_a * 7u
                  ^ (DWORD)g_pb_b * 13u ^ (DWORD)g_pb_bucle << 3 ^ (DWORD)g_pb_bucle_real << 4 ^ (DWORD)g_pb_estado << 5 ^ (DWORD)g_pb_vueltas << 9
                  ^ (DWORD)g_pb_msj_serie << 17 ^ (DWORD)(g_pb_hover + 1) << 11 ^ (DWORD)g_pb_arr << 1
                  ^ (DWORD)g_pb_arr_ms * 31u ^ (DWORD)w << 20 ^ (DWORD)g_pb_prep
                  ^ (DWORD)g_pt_serie * 2246822519u ^ (DWORD)g_pb_tramos << 30 ^ (DWORD)g_pt_arr << 31 ^ (DWORD)g_pt_arr_ms * 977u
                  ^ (DWORD)g_pb_zona << 26 ^ (DWORD)(GetTickCount() - g_pb_msj_t < 6000) << 28
                  ^ (g_fj_arco ? (GetTickCount() / 40) * 2654435761u : 0) ^ (DWORD)g_tr_idi << 29;   /* ★ el arcoíris de los títulos se mueve */
    if (firma != g_pb_firma) {
        pb_armar();
        g_pbd_armar++;
        if (pb_subir()) g_pb_firma = firma; else g_pbd_subir_mal++;
    }
    if (!g_pb_tramos) g_pbd_chico++;
    g_pbd_quad++;
    pb_quad_tam(dev, g_pb_tex, g_pb_x, g_pb_y, g_pb_w, g_pb_alto, PB_TW, PB_TH);
    if (!g_pb_dibujado) apuntar("  [pausa_barra] ★ primera vez en pantalla: %dx%d en (%d,%d), backbuffer %ux%u",
                                g_pb_w, g_pb_alto, g_pb_x, g_pb_y, g_ancho, g_alto);
    g_pb_dibujado = GetTickCount() | 1;
}

/* ── el mouse (lo llama el WndProc de d3d9_proxy.c ANTES que al juego; 1 = el juego no lo ve) ── */
static int pb_a_juego(HWND h, LPARAM lp, int *x, int *y)
{
    POINT p;
    RECT r;
    p.x = (short)LOWORD(lp);
    p.y = (short)HIWORD(lp);
    if (!GetClientRect(h, &r) || r.right <= 0 || r.bottom <= 0) return 0;
    *x = g_ancho ? (int)((LONGLONG)p.x * (LONGLONG)g_ancho / r.right) : p.x;
    *y = g_alto ? (int)((LONGLONG)p.y * (LONGLONG)g_alto / r.bottom) : p.y;
    return 1;
}

/* ★ 26-nov: ¿hay un borde de tramo cerca de lx? Prepara el arrastre (como n2m_borde del Mapa) */
static int pt_borde(int lx)
{
    int n = (int)g_pt_n, mejor = PB_AGARRE + 1, val = -1;
    if (n > N2_TRAMOS) n = N2_TRAMOS;
    for (int i = 0; i < n; i++) {
        int d1 = lx - pb_ms_a_x((int)g_pt_de[i]), d2 = lx - pb_ms_a_x((int)g_pt_ha[i]);
        if (d1 < 0) d1 = -d1;
        if (d2 < 0) d2 = -d2;
        if (d1 < mejor) { mejor = d1; val = (int)g_pt_de[i]; }
        if (d2 < mejor) { mejor = d2; val = (int)g_pt_ha[i]; }
    }
    if (val < 0) return 0;
    int mn = 0, mx = pb_dur();
    for (int i = 0; i < n; i++) {
        int de = (int)g_pt_de[i], ha = (int)g_pt_ha[i];
        if (de == val || ha == val) {
            if (de == val && ha - 1000 < mx) mx = ha - 1000;
            if (ha == val && de + 1000 > mn) mn = de + 1000;
            continue;
        }
        if (ha <= val && ha > mn) mn = ha;
        if (de >= val && de < mx) mx = de;
    }
    g_pt_arr_de = g_pt_arr_ms = val; g_pt_arr_min = mn; g_pt_arr_max = mx;
    return 1;
}
static int pt_tramo_en(int ms)                                   /* el índice del tramo en ms, -1 ninguno */
{
    for (int i = 0; i < (int)g_pt_n && i < N2_TRAMOS; i++) if (ms >= (int)g_pt_de[i] && ms < (int)g_pt_ha[i]) return i;
    return -1;
}
static void pt_pedir_vel(int i, int paso)
{
    int pc = (int)g_pt_pc[i] + paso;
    if (pc < 50) pc = 50;
    if (pc > 150) pc = 150;
    if (pc != (int)g_pt_pc[i]) InterlockedExchange(&g_pt_ped_vel, (LONG)(g_pt_fila[i] << 8 | pc));
}
static int pt_ms_exacto(int lx)
{
    int w = pb_x1() - pb_x0();
    if (w <= 0) return 0;
    if (lx < pb_x0()) lx = pb_x0();
    if (lx > pb_x1()) lx = pb_x1();
    return (int)((LONGLONG)(lx - pb_x0()) * pb_dur() / w);
}

static int pb_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    if (!pb_visible()) {
        if (g_pb_arr) { g_pb_arr = 0; ReleaseCapture(); }
        if (g_pt_arr) { g_pt_arr = 0; ReleaseCapture(); }
        g_pb_hover = -1;
        g_pb_zona = 0;
        return 0;
    }
    if (wp == VK_ESCAPE && (msg == WM_KEYDOWN || msg == WM_KEYUP || msg == WM_CHAR)) {
        if (g_pt_arr && msg == WM_KEYDOWN) { g_pt_arr = 0; ReleaseCapture(); g_pb_tragar_esc = 2; return 1; }
        if (g_pb_arr && msg == WM_KEYDOWN) { g_pb_arr = 0; ReleaseCapture(); g_pb_tragar_esc = 2; return 1; }
        if (g_pb_tragar_esc && msg != WM_KEYDOWN) { g_pb_tragar_esc--; return 1; }
        return 0;
    }
    if (msg != WM_MOUSEMOVE && msg != WM_LBUTTONDOWN && msg != WM_LBUTTONDBLCLK && msg != WM_LBUTTONUP
        && msg != WM_RBUTTONDOWN && msg != WM_RBUTTONUP && msg != WM_RBUTTONDBLCLK && msg != WM_MOUSEWHEEL) return 0;
    int x, y;
    if (msg == WM_MOUSEWHEEL) {                                   /* la rueda trae la posición en la pantalla */
        POINT p = { (short)LOWORD(lp), (short)HIWORD(lp) };
        ScreenToClient(h, &p);
        if (!pb_a_juego(h, MAKELPARAM(p.x, p.y), &x, &y)) return 0;
    } else if (!pb_a_juego(h, lp, &x, &y)) return 0;
    int lx = x - g_pb_x, ly = y - g_pb_y;
    int dentro = lx >= 0 && lx < g_pb_w && ly >= 0 && ly < g_pb_alto;
    int en_barra = lx >= pb_x0() - PB_AGARRE && lx <= pb_x1() + PB_AGARRE && ly >= PB_BARRA_Y0 - 20 && ly <= PB_BARRA_Y1 + 8;
    /* ★ 26-nov: los tramos (sólo en práctica) */
    int en_tramos = g_pb_tramos && lx >= pb_x0() - PB_AGARRE && lx <= pb_x1() + PB_AGARRE && ly >= PB_TR_Y0 - 20 && ly <= PB_TR_Y1 + 8;
    int en_boton = g_pb_tramos && lx >= g_pb_w - PB_TR_BOT_W - 10 && lx < g_pb_w - 10 && ly >= PB_TR_TIT - 2 && ly < PB_TR_TIT + 18;
    if (en_tramos || en_boton || g_pt_arr) {
        switch (msg) {
        case WM_MOUSEMOVE:
            g_pb_hover = lx;
            g_pb_zona = en_boton ? 3 : 2;
            if (g_pt_arr) {
                int ms = pb_x_a_ms(lx);
                g_pt_arr_ms = ms < g_pt_arr_min ? g_pt_arr_min : ms > g_pt_arr_max ? g_pt_arr_max : ms;
            }
            return 0;
        case WM_LBUTTONDOWN:
        case WM_LBUTTONDBLCLK: {
            if (en_boton) { InterlockedExchange(&g_pt_ped_onoff, 1); return 1; }
            if (pt_borde(lx)) { g_pt_arr = 1; SetCapture(h); return 1; }
            int i = pt_tramo_en(pt_ms_exacto(lx));
            if (i >= 0) pt_pedir_vel(i, (GetKeyState(VK_SHIFT) & 0x8000) ? -5 : 5);
            else InterlockedExchange(&g_pt_ped_punto, pb_x_a_ms(lx));
            return 1;
        }
        case WM_LBUTTONUP:
            if (g_pt_arr) {
                g_pt_arr = 0;
                ReleaseCapture();
                if (g_pt_arr_ms != g_pt_arr_de && g_pt_arr_ms >= 0)
                    InterlockedExchange(&g_pt_ped_borde, (LONG)((g_pt_arr_de / 1000) << 16 | (g_pt_arr_ms / 1000)));
            }
            return 1;
        case WM_RBUTTONDOWN:
        case WM_RBUTTONDBLCLK: {
            if (!en_tramos) return 1;
            int i = pt_tramo_en(pt_ms_exacto(lx));
            if (i >= 0) InterlockedExchange(&g_pt_ped_quitar, (LONG)g_pt_fila[i]);
            return 1;
        }
        case WM_RBUTTONUP:
            return 1;
        case WM_MOUSEWHEEL: {
            if (!en_tramos) return 1;
            int i = pt_tramo_en(pt_ms_exacto(lx));
            if (i >= 0) pt_pedir_vel(i, GET_WHEEL_DELTA_WPARAM(wp) > 0 ? 5 : -5);
            return 1;
        }
        }
        return 0;
    }
    if (msg == WM_MOUSEWHEEL) return dentro;
    switch (msg) {
    case WM_MOUSEMOVE:
        g_pb_hover = dentro ? lx : -1;
        g_pb_zona = dentro ? 1 : 0;
        if (g_pb_arr) {
            int ms = pb_x_a_ms(lx);
            if (g_pb_arr == 1) { int tope = pb_b_efectivo() - 1000; if (ms > tope) ms = tope; }
            else { int piso = (int)g_pb_a + 1000; if (ms < piso) ms = piso; }
            g_pb_arr_ms = ms < 0 ? 0 : ms;
        }
        return 0;                                                 /* el juego también lo ve: mueve su cursor */
    case WM_LBUTTONDOWN:
    case WM_LBUTTONDBLCLK: {
        if (!dentro) return 0;
        if (!en_barra) return 1;
        int xa = pb_ms_a_x((int)g_pb_a), xb = pb_ms_a_x(pb_b_efectivo());
        int da = lx - xa, db = lx - xb;
        if (da < 0) da = -da;
        if (db < 0) db = -db;
        if (da <= PB_AGARRE || db <= PB_AGARRE) {
            g_pb_arr = (da <= db) ? 1 : 2;
            if (da == db && lx > xa) g_pb_arr = 2;                /* encimados: a la derecha agarra B */
            g_pb_arr_ms = g_pb_arr == 1 ? (int)g_pb_a : pb_b_efectivo();
            SetCapture(h);
            return 1;
        }
        int ms = pb_x_a_ms(lx);
        if (GetKeyState(VK_SHIFT) & 0x8000) {
            if (ms >= pb_b_efectivo() - 1000) ms = pb_b_efectivo() - 1000;
            InterlockedExchange(&g_pb_ped_a, ms < 0 ? 0 : ms);
        } else InterlockedExchange(&g_pb_ped_ir, ms);
        return 1;
    }
    case WM_LBUTTONUP:
        if (g_pb_arr) {
            int que = g_pb_arr;
            g_pb_arr = 0;
            ReleaseCapture();
            if (que == 1 && g_pb_arr_ms != (int)g_pb_a) InterlockedExchange(&g_pb_ped_a, g_pb_arr_ms);
            if (que == 2 && g_pb_arr_ms != pb_b_efectivo())
                InterlockedExchange(&g_pb_ped_b, g_pb_arr_ms >= pb_dur() && g_pb_largo > 0 ? 0 : g_pb_arr_ms);
            return 1;
        }
        return dentro;
    case WM_RBUTTONDOWN:
    case WM_RBUTTONDBLCLK:
        if (!dentro) return 0;
        if (en_barra) {
            int ms = pb_x_a_ms(lx);
            if (ms <= (int)g_pb_a + 1000) {
                lstrcpyW(g_pb_msj, TR(L"El final (B) tiene que quedar después de A."));
                g_pb_msj_err = 1;
                InterlockedIncrement(&g_pb_msj_serie);
            } else InterlockedExchange(&g_pb_ped_b, ms);
        }
        return 1;
    case WM_RBUTTONUP:
        return dentro;
    }
    return 0;
}
