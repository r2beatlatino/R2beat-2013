/* n2h_booster.c — Personalización · Booster (25-nov-2026)
 *   El botón del booster sin carga / lleno / un marco encima (PNG, TGA, GIF animado o BMP), teñirlo y moverlo en X/Y
 *   (booster.c lo pone en el juego). Se incluye desde n2h_ventana.c (usa sus ayudantes).
 */

enum { B_BO_LLENO = 90, B_BO_LLENO_Q, B_BO_VACIO, B_BO_VACIO_Q, B_BO_TENIR, B_BO_TENIR_Q, B_BO_MARCO, B_BO_MARCO_Q,
       B_BO_IZQ, B_BO_DER, B_BO_ARR, B_BO_ABA, B_BO_CENTRO };

static HWND    g_bo_vista = NULL;
static wchar_t g_bo_estado[300], g_bo_pos_txt[60];
static HBITMAP g_bo_mini[3];                    /* 81 × 81 premultiplicado (1.er cuadro), para la vista */
static int     g_bo_cuadros[3];                 /* cuántos cuadros tiene cada una (para decir «animado») */

static void bo_aviso(const wchar_t *t)
{
    lstrcpynW(g_bo_estado, t, 300);
    if (g_n2_pag[N2P_PIEDRAS]) InvalidateRect(g_n2_pag[N2P_PIEDRAS], NULL, FALSE);
    if (g_bo_vista) InvalidateRect(g_bo_vista, NULL, FALSE);
}

static void bo_pos_texto(void)
{
    wsprintfW(g_bo_pos_txt, L"Posición: X %+d · Y %+d px", g_bo_dx, g_bo_dy);
    if (g_n2_pag[N2P_PIEDRAS]) InvalidateRect(g_n2_pag[N2P_PIEDRAS], NULL, FALSE);
}

static void bo_mini_armar(int k)
{
    if (g_bo_mini[k]) { DeleteObject(g_bo_mini[k]); g_bo_mini[k] = NULL; }
    g_bo_cuadros[k] = 0;
    wchar_t r[MAX_PATH * 2];
    BO_ANIM a;
    if (!bo_ruta(k, r) || !bo_anim_cargar(r, &a)) return;
    g_bo_cuadros[k] = a.n;
    BITMAPINFO bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = 81; bi.bmiHeader.biHeight = -81; bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32;
    void *bits = NULL;
    HBITMAP b = CreateDIBSection(NULL, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (b && bits) {
        DWORD *d = (DWORD *)bits;
        for (int y = 0; y < 81; y++)
            for (int x = 0; x < 81; x++) {
                DWORD c = pdr_muestra(a.px[0], a.w, a.h, (x + 0.5f) / 81, (y + 0.5f) / 81), al = c >> 24;
                d[y * 81 + x] = (al << 24) | ((((c >> 16) & 0xFF) * al / 255) << 16) | ((((c >> 8) & 0xFF) * al / 255) << 8) | ((c & 0xFF) * al / 255);
            }
        g_bo_mini[k] = b;
    } else if (b) DeleteObject(b);
    bo_anim_soltar(&a);
}

static void bo_elegir(int k)
{
    typedef BOOL (WINAPI *F_ABRIR)(OPENFILENAMEW *);
    static const wchar_t *TIT[3] = { L"El botón del booster SIN CARGA (81 x 81)", L"El botón del booster LLENO (81 x 81)",
                                     L"Un marco para el botón (con transparencia; se ajusta al botón)" };
    static const wchar_t *NOM[3] = { L"sin_carga", L"lleno", L"marco" };
    HMODULE cd = LoadLibraryW(L"comdlg32.dll");
    F_ABRIR f = cd ? (F_ABRIR)(void *)GetProcAddress(cd, "GetOpenFileNameW") : NULL;
    if (!f) return;
    wchar_t archivo[MAX_PATH] = L"";
    OPENFILENAMEW o;
    ZeroMemory(&o, sizeof(o));
    o.lStructSize = sizeof(o);
    o.hwndOwner = g_n2_per ? g_n2_per : g_ht_ven;
    o.lpstrFilter = L"Imágenes (PNG, TGA, GIF, BMP)\0*.png;*.tga;*.gif;*.bmp\0";
    o.lpstrTitle = TIT[k];
    o.lpstrFile = archivo; o.nMaxFile = MAX_PATH;
    o.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!f(&o)) return;
    BO_ANIM a;
    if (!bo_anim_cargar(archivo, &a) || a.w < 16 || a.h < 16) {
        if (a.n) bo_anim_soltar(&a);
        bo_aviso(L"No se pudo abrir esa imagen (o es muy chica).");
        return;
    }
    wchar_t d[MAX_PATH * 2], viejo[MAX_PATH * 2];
    bo_carpeta(d);
    CreateDirectoryW(d, NULL);
    while (bo_ruta(k, viejo)) DeleteFileW(viejo);
    int n = lstrlenW(archivo);
    int es_tga = n > 4 && !lstrcmpiW(archivo + n - 4, L".tga");
    lstrcatW(d, NOM[k]);
    lstrcatW(d, es_tga ? L".tga" : L".png");               /* GIF/BMP también: GDI+ lee la firma, no la extensión */
    if (!CopyFileW(archivo, d, FALSE)) { bo_anim_soltar(&a); bo_aviso(L"No se pudo escribir en la carpeta del booster."); return; }
    int cuadros = a.n, w = a.w, h = a.h;
    bo_poner(k, &a);
    bo_mini_armar(k);
    static const wchar_t *QUE[3] = { L"el botón sin carga", L"el botón lleno", L"el marco" };
    wchar_t t[200];
    wsprintfW(t, L"Puesto %s (%d x %d%s).%s", QUE[k], w, h, cuadros > 1 ? L", animado" : L"",
              g_bo_activo ? L" Se ve en la carrera." : L" ⚠ El cambio del booster no está enganchado (mira d3d9_proxy.log).");
    bo_aviso(t);
}

static void bo_quitar(int k)
{
    wchar_t r[MAX_PATH * 2];
    while (bo_ruta(k, r)) DeleteFileW(r);
    bo_poner(k, NULL);
    bo_mini_armar(k);
    static const wchar_t *T[3] = { L"El botón sin carga vuelve a ser el del juego.", L"El botón lleno vuelve a ser el del juego.",
                                   L"Sin marco." };
    bo_aviso(T[k]);
}

static void bo_mover(int dx, int dy)
{
    int x = g_bo_dx + dx, y = g_bo_dy + dy;
    g_bo_dx = x < -2000 ? -2000 : x > 2000 ? 2000 : x;
    g_bo_dy = y < -2000 ? -2000 : y > 2000 ? 2000 : y;
    ht_pedir_guardar();
    bo_pos_texto();
    if (!g_bo_mover_activo) bo_aviso(L"⚠ Mover no está enganchado (mira d3d9_proxy.log).");
}

static int bo_comando(int ref)
{
    int paso = (GetKeyState(VK_SHIFT) & 0x8000) ? 20 : 4;
    switch (ref) {
    case B_BO_LLENO: bo_elegir(1); return 1;
    case B_BO_VACIO: bo_elegir(0); return 1;
    case B_BO_MARCO: bo_elegir(2); return 1;
    case B_BO_LLENO_Q: bo_quitar(1); return 1;
    case B_BO_VACIO_Q: bo_quitar(0); return 1;
    case B_BO_MARCO_Q: bo_quitar(2); return 1;
    case B_BO_TENIR: {
        COLORREF c = g_bo_tenir == CLR_INVALID ? RGB(255, 255, 255) : g_bo_tenir;
        if (n2_elegir_color(&c)) { bo_poner_tenir(c); ht_pedir_guardar(); bo_aviso(L"Botón teñido (multiplica sus colores)."); }
        return 1;
    }
    case B_BO_TENIR_Q: bo_poner_tenir(CLR_INVALID); ht_pedir_guardar(); bo_aviso(L"Sin teñir."); return 1;
    case B_BO_IZQ: bo_mover(-paso, 0); return 1;
    case B_BO_DER: bo_mover(paso, 0); return 1;
    case B_BO_ARR: bo_mover(0, -paso); return 1;
    case B_BO_ABA: bo_mover(0, paso); return 1;
    case B_BO_CENTRO: g_bo_dx = g_bo_dy = 0; ht_pedir_guardar(); bo_pos_texto(); bo_aviso(L"En su sitio de siempre."); return 1;
    }
    return 0;
}

static LRESULT CALLBACK bo_vista_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    if (m == WM_ERASEBKGND) return 1;
    if (m != WM_PAINT) return DefWindowProcW(h, m, wp, lp);
    PAINTSTRUCT ps;
    HDC d0 = BeginPaint(h, &ps);
    RECT c; GetClientRect(h, &c);
    HDC dc = CreateCompatibleDC(d0);
    HBITMAP bm = CreateCompatibleBitmap(d0, c.right, c.bottom);
    HGDIOBJ ob = SelectObject(dc, bm);
    HBRUSH fondo = CreateSolidBrush(RGB(14, 16, 30));
    FillRect(dc, &c, fondo);
    DeleteObject(fondo);
    SetBkMode(dc, TRANSPARENT);
    HGDIOBJ of = SelectObject(dc, g_n2_f);
    static const wchar_t *T[3] = { L"Sin carga", L"Lleno", L"Marco" };
    for (int k = 0; k < 3; k++) {
        int x = 6 + k * 108, y = 6;
        wchar_t tt[40];
        wsprintfW(tt, L"%s%s", T[k], g_bo_cuadros[k] > 1 ? L" (GIF)" : L"");
        RECT r = { x, y, x + 100, y + 18 };
        SetTextColor(dc, RGB(200, 206, 220));
        DrawTextW(dc, tt, -1, &r, DT_CENTER | DT_SINGLELINE);
        RECT caja = { x + 10, y + 22, x + 10 + 81, y + 22 + 81 };
        HBRUSH bc = CreateSolidBrush(RGB(28, 31, 50)); FillRect(dc, &caja, bc); DeleteObject(bc);
        HBITMAP capas[2] = { g_bo_mini[k], k < 2 ? g_bo_mini[2] : NULL };   /* el marco, encima de los botones */
        int algo = 0;
        for (int q = 0; q < 2; q++) {
            if (!capas[q]) continue;
            HDC m2 = CreateCompatibleDC(dc);
            HGDIOBJ om = SelectObject(m2, capas[q]);
            BLENDFUNCTION bf = { AC_SRC_OVER, 0, 255, AC_SRC_ALPHA };
            GdiAlphaBlend(dc, caja.left, caja.top, 81, 81, m2, 0, 0, 81, 81, bf);
            SelectObject(m2, om); DeleteDC(m2);
            if (q == 0) algo = 1;
        }
        if (!algo) {
            SetTextColor(dc, RGB(130, 140, 160));
            DrawTextW(dc, k < 2 ? L"la del\njuego" : L"sin\nmarco", -1, &caja, DT_CENTER | DT_WORDBREAK);
        }
        if (g_bo_tenir != CLR_INVALID && k < 2) {
            RECT t = { caja.left, caja.bottom + 4, caja.right, caja.bottom + 10 };
            HBRUSH bt = CreateSolidBrush(g_bo_tenir); FillRect(dc, &t, bt); DeleteObject(bt);
        }
    }
    SelectObject(dc, of);
    BitBlt(d0, 0, 0, c.right, c.bottom, dc, 0, 0, SRCCOPY);
    SelectObject(dc, ob); DeleteObject(bm); DeleteDC(dc);
    EndPaint(h, &ps);
    return 0;
}

/* lo arma n2_per_maquetar (página 10) */
static void bo_maquetar(void)
{
    static int registrada = 0;
    if (!registrada) {
        WNDCLASSEXW wc;
        ZeroMemory(&wc, sizeof(wc));
        wc.cbSize = sizeof(wc); wc.hInstance = GetModuleHandleA(NULL); wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
        wc.lpfnWndProc = bo_vista_proc; wc.lpszClassName = L"N2HBooster";
        RegisterClassExW(&wc);
        registrada = 1;
    }
    /* ★ 26-nov (anonimo03): debajo de las piedras, en la MISMA pestaña */
    n2_lienzo(N2P_PIEDRAS);
    const int Y0 = 330;
    n2_lbl(8, Y0, 330, 20, L"El botón del booster (AutoCtrl) en la carrera", N2_C_ACENTO, N2_IZQ);
    g_bo_vista = CreateWindowExW(0, L"N2HBooster", L"", WS_CHILD | WS_VISIBLE, 3 + 8, 3 + Y0 + 22, 330, 120,
                                 g_n2_pag[N2P_PIEDRAS], NULL, GetModuleHandleA(NULL), NULL);
    int y = Y0 + 146;
    n2_boton(14, y, 104, 26, L"Sin carga...", B_BO_VACIO);
    n2_boton(124, y, 104, 26, L"Lleno...", B_BO_LLENO);
    n2_boton(234, y, 104, 26, L"Marco...", B_BO_MARCO);
    y += 28;
    n2_boton(14, y, 104, 24, L"Quitar", B_BO_VACIO_Q);
    n2_boton(124, y, 104, 24, L"Quitar", B_BO_LLENO_Q);
    n2_boton(234, y, 104, 24, L"Quitar", B_BO_MARCO_Q);
    y += 28;
    n2_boton(14, y, 158, 26, L"Teñir el botón...", B_BO_TENIR);
    n2_boton(180, y, 158, 26, L"Sin teñir", B_BO_TENIR_Q);
    y += 30;
    n2_lbl(14, y + 3, 150, 22, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_bo_pos_txt;
    n2_boton(166, y, 34, 26, L"◄", B_BO_IZQ);
    n2_boton(202, y, 34, 26, L"►", B_BO_DER);
    n2_boton(238, y, 34, 26, L"▲", B_BO_ARR);
    n2_boton(274, y, 34, 26, L"▼", B_BO_ABA);
    n2_boton(310, y, 28, 26, L"0", B_BO_CENTRO);
    y += 30;
    n2_lbl(14, y, 324, 46, NULL, N2_SUAVE, N2_PARR); g_n2l[g_n2nl - 1].dyn = g_bo_estado;
    if (!g_bo_estado[0])
        lstrcpyW(g_bo_estado, L"Las imágenes se ajustan a 81 x 81; el marco va encima. Mover lleva también el de equipo y "
                              L"el fuego (4 px; con Mayús, 20; «0» = centrar).");
    for (int k = 0; k < 3; k++) bo_mini_armar(k);
    bo_pos_texto();
}
