/* n2h_booster.c — Personalización · Booster (25-nov-2026)
 *   El botón del booster sin carga / lleno / un marco encima (PNG, TGA, GIF animado o BMP), teñirlo y moverlo en X/Y
 *   (booster.c lo pone en el juego). Se incluye desde n2h_ventana.c (usa sus ayudantes).
 */

enum { B_BO_LLENO = 90, B_BO_LLENO_Q, B_BO_VACIO, B_BO_VACIO_Q, B_BO_TENIR, B_BO_TENIR_Q, B_BO_MARCO, B_BO_MARCO_Q,
       B_BO_IZQ, B_BO_DER, B_BO_ARR, B_BO_ABA, B_BO_CENTRO,
       B_BO_AURA, B_BO_AURA_Q, B_BO_TENIR_IMG, B_BO_AURA_MENOS, B_BO_AURA_MAS,
       B_BO_ANIM_MENOS, B_BO_ANIM_MAS };   /* ★ 28-nov */

/* ★ 28-nov (anonimo03): el booster en su pestaña, con lo del AutoCtrl del ToolBit: el lleno que parpadea (lleno_2), el
 *   marco grande y el AURA alrededor del botón, TEÑIR CON IMAGEN y las listas de EJEMPLOS
 *   (<juego>\n2hock_booster\ejemplos\{Boton,Marcos,Aura,Tenir}\; un botón = <nombre>_sin_carga + _lleno [+ _lleno_2]). */
static HWND    g_bo_vista = NULL;
static wchar_t g_bo_estado[300], g_bo_pos_txt[60], g_bo_aura_txt[40], g_bo_anim_txt[48];
static HBITMAP g_bo_mini[BO_N];                 /* 81 × 81 premultiplicado (1.er cuadro), para la vista */
static int     g_bo_cuadros[BO_N];              /* cuántos cuadros tiene cada una (para decir «animado») */
#define BO_EJ_MAX 48
static wchar_t g_bo_ej[4][BO_EJ_MAX][64];       /* los ejemplos de cada lista (el nombre del archivo o del botón) */
static int     g_bo_ej_n[4];
static const wchar_t *const BO_EJ_SUB[4] = { L"Boton", L"Marcos", L"Aura", L"Tenir" };

static void bo_aviso(const wchar_t *t)
{
    lstrcpynW(g_bo_estado, t, 300);
    if (g_n2_pag[N2P_BO]) InvalidateRect(g_n2_pag[N2P_BO], NULL, FALSE);
    if (g_bo_vista) InvalidateRect(g_bo_vista, NULL, FALSE);
}

static void bo_pos_texto(void)
{
    wsprintfW(g_bo_pos_txt, TR(L"Posición: X %+d · Y %+d px"), g_bo_dx, g_bo_dy);
    wsprintfW(g_bo_aura_txt, TR(L"Aura %d %%"), g_bo_aura_pct);
    wsprintfW(g_bo_anim_txt, TR(L"Animación %d %%"), g_bo_anim_pct);
    if (g_n2_pag[N2P_BO]) InvalidateRect(g_n2_pag[N2P_BO], NULL, FALSE);
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

static const wchar_t *const BO_NOM[BO_N] = { L"sin_carga", L"lleno", L"marco", L"lleno_2", L"aura", L"tenir" };
static const wchar_t *const BO_QUE[BO_N] = { L"el botón sin carga", L"el botón lleno", L"el marco", L"el 2.º cuadro del lleno",
                                             L"el aura", L"el teñido con imagen" };

/* copia `archivo` como la pieza k y la pone. 1 = bien. `callado`: sin aviso */
static int bo_instalar(int k, const wchar_t *archivo, int callado)
{
    BO_ANIM a;
    if (!bo_anim_cargar(archivo, &a) || a.w < 16 || a.h < 16) {
        if (a.n) bo_anim_soltar(&a);
        if (!callado) bo_aviso(L"No se pudo abrir esa imagen (o es muy chica).");
        return 0;
    }
    wchar_t d[MAX_PATH * 2], viejo[MAX_PATH * 2];
    bo_carpeta(d);
    CreateDirectoryW(d, NULL);
    while (bo_ruta(k, viejo)) DeleteFileW(viejo);
    int n = lstrlenW(archivo);
    int es_tga = n > 4 && !lstrcmpiW(archivo + n - 4, L".tga");
    lstrcatW(d, BO_NOM[k]);
    lstrcatW(d, es_tga ? L".tga" : L".png");               /* GIF/BMP también: GDI+ lee la firma, no la extensión */
    if (!CopyFileW(archivo, d, FALSE)) { bo_anim_soltar(&a); if (!callado) bo_aviso(L"No se pudo escribir en la carpeta del booster."); return 0; }
    int cuadros = a.n, w = a.w, h = a.h;
    bo_poner(k, &a);
    bo_mini_armar(k);
    if (k == 1) {                                          /* ★ 28-nov: «…_lleno» con su «…_lleno_2» al lado = parpadea */
        wchar_t dos[MAX_PATH];
        lstrcpynW(dos, archivo, MAX_PATH - 4);
        int m = lstrlenW(dos);
        while (m > 0 && dos[m - 1] != L'.' && dos[m - 1] != L'\\') m--;
        int hay2 = 0;
        if (m > 1 && dos[m - 1] == L'.') {
            wchar_t ext[16];
            lstrcpynW(ext, dos + m - 1, 16);
            dos[m - 1] = 0;
            lstrcatW(dos, L"_2"); lstrcatW(dos, ext);
            hay2 = GetFileAttributesW(dos) != INVALID_FILE_ATTRIBUTES && bo_instalar(3, dos, 1);
        }
        if (!hay2) { wchar_t r[MAX_PATH * 2]; while (bo_ruta(3, r)) DeleteFileW(r); bo_poner(3, NULL); bo_mini_armar(3); }
    }
    if (!callado) {
        wchar_t t[220];
        wsprintfW(t, TR(L"Puesto %s (%d x %d%s).%s"), TR(BO_QUE[k]), w, h, cuadros > 1 ? TR(L", animado") : L"",
                  g_bo_activo ? TR(L" Se ve en la carrera.") : TR(L" ⚠ El cambio del booster no está enganchado (mira d3d9_proxy.log)."));
        bo_aviso(t);
    }
    return 1;
}

/* ★ 28-nov: la pieza k se cambió a mano o se quitó: su lista vuelve a «(elige un ejemplo)» */
static void bo_ej_olvidar(int k)
{
    int tipo = k <= 1 || k == 3 ? 0 : k == 2 ? 1 : k == 4 ? 2 : 3;
    if (!g_bo_ej_puesto[tipo][0]) return;
    g_bo_ej_puesto[tipo][0] = 0;
    ht_pedir_guardar();
    for (int i = 0; i < g_n2n; i++)
        if (g_n2c[i].ref == L_BO_BOTON + tipo && g_n2c[i].tipo == C_COMBO && g_n2c[i].h) SendMessageW(g_n2c[i].h, CB_SETCURSEL, 0, 0);
}

static void bo_elegir(int k)
{
    typedef BOOL (WINAPI *F_ABRIR)(OPENFILENAMEW *);
    static const wchar_t *TIT[BO_N] = { L"El botón del booster SIN CARGA (81 x 81)", L"El botón del booster LLENO (81 x 81)",
                                        L"Un marco para el botón (con transparencia; de más de 100 px va por afuera)", L"",
                                        L"Un aura alrededor del botón (con transparencia; GIF animado)",
                                        L"Teñir el botón con una imagen (multiplica sus colores)" };
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
    if (bo_instalar(k, archivo, 0)) bo_ej_olvidar(k);
}

static void bo_quitar(int k)
{
    wchar_t r[MAX_PATH * 2];
    while (bo_ruta(k, r)) DeleteFileW(r);
    bo_poner(k, NULL);
    bo_mini_armar(k);
    if (k == 1) { while (bo_ruta(3, r)) DeleteFileW(r); bo_poner(3, NULL); bo_mini_armar(3); }
    bo_ej_olvidar(k);
    static const wchar_t *T[BO_N] = { L"El botón sin carga vuelve a ser el del juego.", L"El botón lleno vuelve a ser el del juego.",
                                      L"Sin marco.", L"", L"Sin aura.", L"Sin teñido con imagen." };
    bo_aviso(T[k]);
}

/* ── ★ 28-nov · los EJEMPLOS: <juego>\n2hock_booster\ejemplos\<Boton|Marcos|Aura|Tenir>\ ── */
static void bo_ej_carpeta(int tipo, wchar_t *r)
{
    bo_carpeta(r);
    lstrcatW(r, L"ejemplos\\"); lstrcatW(r, BO_EJ_SUB[tipo]); lstrcatW(r, L"\\");
}
static int bo_ej_imagen(const wchar_t *n)
{
    int l = lstrlenW(n);
    return l > 4 && (!lstrcmpiW(n + l - 4, L".png") || !lstrcmpiW(n + l - 4, L".gif") || !lstrcmpiW(n + l - 4, L".tga"));
}
static void bo_ej_llenar(HWND cb, int tipo)
{
    g_bo_ej_n[tipo] = 0;
    if (!cb) return;
    SendMessageW(cb, CB_RESETCONTENT, 0, 0);
    wchar_t q[MAX_PATH * 2];
    bo_ej_carpeta(tipo, q);
    lstrcatW(q, L"*.*");
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(q, &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || !bo_ej_imagen(fd.cFileName) || g_bo_ej_n[tipo] >= BO_EJ_MAX) continue;
            wchar_t nom[64];
            lstrcpynW(nom, fd.cFileName, 64);
            int l = lstrlenW(nom);
            while (l > 0 && nom[l - 1] != L'.') l--;
            if (l > 0) nom[l - 1] = 0;                            /* sin la extensión */
            if (tipo == 0) {                                      /* un botón: «<nombre>_sin_carga» */
                l = lstrlenW(nom);
                if (l <= 10 || lstrcmpiW(nom + l - 10, L"_sin_carga")) continue;
                nom[l - 10] = 0;
            }
            lstrcpyW(g_bo_ej[tipo][g_bo_ej_n[tipo]], tipo == 0 ? nom : fd.cFileName);
            wchar_t vis[64];
            lstrcpynW(vis, nom, 64);
            for (wchar_t *c = vis; *c; c++) if (*c == L'_') *c = L' ';
            LRESULT k = SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)vis);
            if (k >= 0) SendMessageW(cb, CB_SETITEMDATA, (WPARAM)k, (LPARAM)g_bo_ej_n[tipo]);
            g_bo_ej_n[tipo]++;
        } while (FindNextFileW(h, &fd));
        FindClose(h);
    }
    LRESULT k = SendMessageW(cb, CB_INSERTSTRING, 0, (LPARAM)TR(g_bo_ej_n[tipo] ? L"(elige un ejemplo)" : L"(no hay ejemplos)"));
    if (k >= 0) SendMessageW(cb, CB_SETITEMDATA, (WPARAM)k, (LPARAM)-1);
    int sel = 0;
    if (g_bo_ej_puesto[tipo][0]) {
        int n = (int)SendMessageW(cb, CB_GETCOUNT, 0, 0);
        for (int i = 1; i < n; i++) {
            int j = (int)SendMessageW(cb, CB_GETITEMDATA, (WPARAM)i, 0);
            if (j >= 0 && j < g_bo_ej_n[tipo] && !lstrcmpiW(g_bo_ej[tipo][j], g_bo_ej_puesto[tipo])) { sel = i; break; }
        }
    }
    SendMessageW(cb, CB_SETCURSEL, (WPARAM)sel, 0);
}
/* la lista `tipo` eligió su renglón `k` (n2_lista_cambio) */
static void bo_ejemplo(int tipo, int k)
{
    HWND cb = NULL;
    for (int i = 0; i < g_n2n; i++) if (g_n2c[i].ref == L_BO_BOTON + tipo && g_n2c[i].tipo == C_COMBO) cb = g_n2c[i].h;
    int j = cb && k >= 0 ? (int)SendMessageW(cb, CB_GETITEMDATA, (WPARAM)k, 0) : -1;
    if (j < 0 || j >= g_bo_ej_n[tipo]) return;
    wchar_t d[MAX_PATH * 2];
    bo_ej_carpeta(tipo, d);
    if (tipo == 0) {                                         /* el botón: sin carga + lleno (+ lleno_2) */
        static const wchar_t *EXT[3] = { L".png", L".gif", L".tga" };
        int puestos = 0;
        for (int q = 0; q < 2; q++)
            for (int e = 0; e < 3; e++) {
                wchar_t a[MAX_PATH * 2];
                lstrcpyW(a, d); lstrcatW(a, g_bo_ej[0][j]); lstrcatW(a, q ? L"_lleno" : L"_sin_carga"); lstrcatW(a, EXT[e]);
                if (GetFileAttributesW(a) != INVALID_FILE_ATTRIBUTES) { puestos += bo_instalar(q, a, 1); break; }
            }
        wchar_t t[200];
        wsprintfW(t, TR(L"Botón «%s» puesto%s."), g_bo_ej[0][j], g_bo_img[3].n ? TR(L" (el lleno parpadea)") : L"");
        bo_aviso(puestos ? t : TR(L"No se pudo poner ese botón."));
        if (!puestos) { if (cb) SendMessageW(cb, CB_SETCURSEL, 0, 0); return; }
    } else {
        static const int PIEZA[4] = { 0, 2, 4, 5 };
        lstrcatW(d, g_bo_ej[tipo][j]);
        if (!bo_instalar(PIEZA[tipo], d, 0)) { if (cb) SendMessageW(cb, CB_SETCURSEL, 0, 0); return; }
    }
    lstrcpynW(g_bo_ej_puesto[tipo], g_bo_ej[tipo][j], 64);   /* ★ 28-nov: la lista se queda mostrando el puesto */
    ht_pedir_guardar();
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
    case B_BO_AURA: bo_elegir(4); return 1;
    case B_BO_TENIR_IMG: bo_elegir(5); return 1;
    case B_BO_LLENO_Q: bo_quitar(1); return 1;
    case B_BO_VACIO_Q: bo_quitar(0); return 1;
    case B_BO_MARCO_Q: bo_quitar(2); return 1;
    case B_BO_AURA_Q: bo_quitar(4); return 1;
    case B_BO_TENIR: {
        COLORREF c = g_bo_tenir == CLR_INVALID ? RGB(255, 255, 255) : g_bo_tenir;
        if (n2_elegir_color(&c)) { bo_poner_tenir(c); ht_pedir_guardar(); bo_aviso(L"Botón teñido (multiplica sus colores)."); }
        return 1;
    }
    case B_BO_TENIR_Q: {
        bo_poner_tenir(CLR_INVALID); ht_pedir_guardar();
        wchar_t r[MAX_PATH * 2];
        while (bo_ruta(5, r)) DeleteFileW(r);
        bo_poner(5, NULL); bo_mini_armar(5);
        bo_ej_olvidar(5);
        bo_aviso(L"Sin teñir.");
        return 1;
    }
    case B_BO_AURA_MENOS: case B_BO_AURA_MAS: {
        int v = g_bo_aura_pct + (ref == B_BO_AURA_MAS ? 10 : -10);
        g_bo_aura_pct = v < 100 ? 100 : v > 400 ? 400 : v;
        ht_pedir_guardar(); bo_pos_texto();
        return 1;
    }
    case B_BO_ANIM_MENOS: case B_BO_ANIM_MAS: {
        int v = g_bo_anim_pct + (ref == B_BO_ANIM_MAS ? 10 : -10);
        g_bo_anim_pct = v < 10 ? 10 : v > 300 ? 300 : v;
        ht_pedir_guardar(); bo_pos_texto();
        return 1;
    }
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
    static const int K[4] = { 0, 1, 2, 4 };
    static const wchar_t *T[4] = { L"Sin carga", L"Lleno", L"Marco", L"Aura" };
    for (int i = 0; i < 4; i++) {
        int k = K[i], x = 2 + i * 82, y = 4;
        wchar_t tt[48];
        const wchar_t *extra = k == 1 && g_bo_mini[3] ? TR(L" ×2") : k == 2 && bo_marco_afuera() ? TR(L" (grande)")
                              : g_bo_cuadros[k] > 1 ? TR(L" (GIF)") : L"";
        wsprintfW(tt, L"%s%s", TR(T[i]), extra);
        RECT r = { x, y, x + 81, y + 18 };
        SetTextColor(dc, RGB(200, 206, 220));
        DrawTextW(dc, tt, -1, &r, DT_CENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
        RECT caja = { x, y + 20, x + 81, y + 20 + 81 };
        HBRUSH bc = CreateSolidBrush(RGB(28, 31, 50)); FillRect(dc, &caja, bc); DeleteObject(bc);
        HBITMAP capas[2] = { g_bo_mini[k], k < 2 && !bo_marco_afuera() ? g_bo_mini[2] : NULL };
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
            DrawTextW(dc, TR(k < 2 ? L"la del\njuego" : k == 2 ? L"sin\nmarco" : L"sin\naura"), -1, &caja, DT_CENTER | DT_WORDBREAK);
        }
        if (k < 2) {                                         /* el teñido: la imagen (en tira) o el color */
            RECT t = { caja.left, caja.bottom + 4, caja.right, caja.bottom + 10 };
            if (g_bo_mini[5]) {
                HDC m2 = CreateCompatibleDC(dc);
                HGDIOBJ om = SelectObject(m2, g_bo_mini[5]);
                BLENDFUNCTION bf = { AC_SRC_OVER, 0, 255, AC_SRC_ALPHA };
                GdiAlphaBlend(dc, t.left, t.top, 81, 6, m2, 0, 37, 81, 6, bf);
                SelectObject(m2, om); DeleteDC(m2);
            } else if (g_bo_tenir != CLR_INVALID) { HBRUSH bt = CreateSolidBrush(g_bo_tenir); FillRect(dc, &t, bt); DeleteObject(bt); }
        }
    }
    SelectObject(dc, of);
    BitBlt(d0, 0, 0, c.right, c.bottom, dc, 0, 0, SRCCOPY);
    SelectObject(dc, ob); DeleteObject(bm); DeleteDC(dc);
    EndPaint(h, &ps);
    return 0;
}

/* lo arma n2_per_maquetar: ★ 28-nov, en su pestaña (N2P_BO) */
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
    n2_lienzo(N2P_BO);
    const int Y0 = 8;
    n2_lbl(8, Y0, 330, 20, L"El botón del booster (AutoCtrl) en la carrera", N2_C_ACENTO, N2_IZQ);
    g_bo_vista = CreateWindowExW(0, L"N2HBooster", L"", WS_CHILD | WS_VISIBLE, 3 + 8, 3 + Y0 + 22, 332, 118,
                                 g_n2_pag[N2P_BO], NULL, GetModuleHandleA(NULL), NULL);
    int y = Y0 + 146;
    static const wchar_t *EJ[4] = { L"Botón", L"Marco", L"Aura", L"Teñido" };
    for (int t = 0; t < 4; t++, y += 28) {
        n2_lbl(14, y + 2, 60, 22, EJ[t], N2_TEXTO, N2_IZQ);
        bo_ej_llenar(n2_combo_lista(78, y, 260, 22, L_BO_BOTON + t, 0), t);
    }
    y += 4;
    n2_boton(14, y, 78, 26, L"Sin carga...", B_BO_VACIO);
    n2_boton(96, y, 78, 26, L"Lleno...", B_BO_LLENO);
    n2_boton(178, y, 78, 26, L"Marco...", B_BO_MARCO);
    n2_boton(260, y, 78, 26, L"Aura...", B_BO_AURA);
    y += 28;
    n2_boton(14, y, 78, 24, L"Quitar", B_BO_VACIO_Q);
    n2_boton(96, y, 78, 24, L"Quitar", B_BO_LLENO_Q);
    n2_boton(178, y, 78, 24, L"Quitar", B_BO_MARCO_Q);
    n2_boton(260, y, 78, 24, L"Quitar", B_BO_AURA_Q);
    y += 30;
    n2_boton(14, y, 106, 26, L"Teñir (color)...", B_BO_TENIR);
    n2_boton(124, y, 110, 26, L"Teñir (imagen)...", B_BO_TENIR_IMG);
    n2_boton(238, y, 100, 26, L"Sin teñir", B_BO_TENIR_Q);
    y += 30;
    n2_lbl(14, y + 3, 150, 22, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_bo_aura_txt;
    n2_boton(180, y, 76, 26, L"Menos", B_BO_AURA_MENOS);
    n2_boton(262, y, 76, 26, L"Más", B_BO_AURA_MAS);
    y += 30;
    n2_chk_b(14, y + 2, 324, 20, L"Brillo cuando el impulsor está lleno", &g_bo_brillo);   /* ★ 28-nov */
    y += 24;
    n2_chk_b(14, y + 2, 160, 20, L"Aura sólo lleno", &g_bo_aura_lleno);
    n2_chk_b(180, y + 2, 160, 20, L"Teñir sólo el lleno", &g_bo_tenir_lleno);
    y += 26;
    n2_lbl(14, y + 3, 160, 22, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_bo_anim_txt;   /* ★ 28-nov */
    n2_boton(180, y, 76, 26, L"Menos", B_BO_ANIM_MENOS);
    n2_boton(262, y, 76, 26, L"Más", B_BO_ANIM_MAS);
    y += 30;
    n2_lbl(14, y + 3, 150, 22, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_bo_pos_txt;
    n2_boton(166, y, 34, 26, L"◄", B_BO_IZQ);
    n2_boton(202, y, 34, 26, L"►", B_BO_DER);
    n2_boton(238, y, 34, 26, L"▲", B_BO_ARR);
    n2_boton(274, y, 34, 26, L"▼", B_BO_ABA);
    n2_boton(310, y, 28, 26, L"0", B_BO_CENTRO);
    y += 30;
    n2_lbl(14, y, 324, 60, NULL, N2_SUAVE, N2_PARR); g_n2l[g_n2nl - 1].dyn = g_bo_estado;
    if (!g_bo_estado[0])
        lstrcpyW(g_bo_estado, TR(L"El botón se ajusta a 81 x 81. Un marco de más de 100 px y el aura van por afuera del botón. "
                              L"Un «…_lleno» con su «…_lleno_2» parpadea. Mover lleva también el de equipo y el fuego "
                              L"(4 px; con Mayús, 20; «0» = centrar)."));
    for (int k = 0; k < BO_N; k++) bo_mini_armar(k);
    bo_pos_texto();
}
