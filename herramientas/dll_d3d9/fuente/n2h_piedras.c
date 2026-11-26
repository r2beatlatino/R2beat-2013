/* n2h_piedras.c — Personalización · Piedras (25-nov-2026): la galería de piedras del ritmo
 *
 *   La galería (6 × 4 por página), «Instalar piedras…», «Instalar una carpeta…», «Quitar» y «Carpeta…», como en el
 *   ToolBit 0.6.40. La primera casilla es «De fábrica». Al elegir una, se carga y piedras.c la pone en el juego (al
 *   momento si estás corriendo; si no, en la próxima carrera). Se incluye desde n2h_ventana.c (usa sus ayudantes).
 */

#define PIE_MAX 240
#define PIE_COLS 6
#define PIE_FILAS 3                     /* ★ 26-nov: 3 filas, para que el booster entre debajo */
#define PIE_POR_PAG (PIE_COLS * PIE_FILAS)
#define PIE_CELDA 52
#define PIE_MINI 44

enum { B_PIE_INSTALAR = 70, B_PIE_CARPETA_INST, B_PIE_QUITAR, B_PIE_ABRIR, B_PIE_ANT, B_PIE_SIG };

static wchar_t g_pie_nombre[PIE_MAX][MAX_PATH];
static HBITMAP g_pie_mini[PIE_MAX];             /* 44 × 44, 32 bits premultiplicado (AlphaBlend) */
static int     g_pie_n = 0, g_pie_pag = 0, g_pie_sel = 0, g_pie_hover = -1;   /* sel 0 = de fábrica; i ≥ 1 = nombre[i-1] */
static HWND    g_pie_gal = NULL;
static wchar_t g_pie_txt[160], g_pie_estado[400];

/* miniatura: la 1.ª casilla de la hoja (el cuarto de arriba a la izquierda), a 44 × 44 */
static HBITMAP pie_miniatura(const DWORD *px, int lado)
{
    BITMAPINFO bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = PIE_MINI;
    bi.bmiHeader.biHeight = -PIE_MINI;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP b = CreateDIBSection(NULL, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (!b || !bits) return NULL;
    DWORD *d = (DWORD *)bits;
    int casilla = lado / 4;
    for (int y = 0; y < PIE_MINI; y++)
        for (int x = 0; x < PIE_MINI; x++) {
            /* de la casilla 0 (0..casilla) muestreada al centro */
            DWORD c = pdr_muestra(px, lado, lado, ((x + 0.5f) / PIE_MINI) * casilla / lado, ((y + 0.5f) / PIE_MINI) * casilla / lado);
            DWORD a = c >> 24;
            d[y * PIE_MINI + x] = (a << 24) | ((((c >> 16) & 0xFF) * a / 255) << 16) | ((((c >> 8) & 0xFF) * a / 255) << 8)
                                  | ((c & 0xFF) * a / 255);
        }
    return b;
}

static int pie_es_imagen(const wchar_t *n)
{
    int l = lstrlenW(n);
    return l > 4 && (!lstrcmpiW(n + l - 4, L".tga") || !lstrcmpiW(n + l - 4, L".png"));
}

/* relee la carpeta (y las miniaturas) */
static void pie_listar(void)
{
    for (int i = 0; i < g_pie_n; i++) if (g_pie_mini[i]) { DeleteObject(g_pie_mini[i]); g_pie_mini[i] = NULL; }
    g_pie_n = 0;
    wchar_t r[MAX_PATH], q[MAX_PATH];
    pdr_carpeta(r);
    lstrcpyW(q, r); lstrcatW(q, L"*.*");
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(q, &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || !pie_es_imagen(fd.cFileName) || g_pie_n >= PIE_MAX) continue;
            /* en orden alfabético (inserción) */
            int k = g_pie_n;
            while (k > 0 && lstrcmpiW(g_pie_nombre[k - 1], fd.cFileName) > 0) { lstrcpyW(g_pie_nombre[k], g_pie_nombre[k - 1]); k--; }
            lstrcpyW(g_pie_nombre[k], fd.cFileName);
            g_pie_n++;
        } while (FindNextFileW(h, &fd));
        FindClose(h);
    }
    for (int i = 0; i < g_pie_n; i++) {
        wchar_t a[MAX_PATH * 2];
        lstrcpyW(a, r); lstrcatW(a, g_pie_nombre[i]);
        int w = 0, hh = 0;
        DWORD *px = pdr_cargar(a, &w, &hh);
        if (px && w == hh && w >= 64) g_pie_mini[i] = pie_miniatura(px, w);
        if (px) HeapFree(GetProcessHeap(), 0, px);
    }
    /* la elegida, por su nombre */
    g_pie_sel = 0;
    if (g_pdr_elegida[0]) for (int i = 0; i < g_pie_n; i++) if (!lstrcmpiW(g_pie_nombre[i], g_pdr_elegida)) g_pie_sel = i + 1;
    int pags = (g_pie_n + 1 + PIE_POR_PAG - 1) / PIE_POR_PAG;
    if (g_pie_pag >= pags) g_pie_pag = pags - 1;
    if (g_pie_pag < 0) g_pie_pag = 0;
}

static void pie_textos(void)
{
    int pags = (g_pie_n + 1 + PIE_POR_PAG - 1) / PIE_POR_PAG;
    wchar_t n[MAX_PATH];
    if (g_pie_sel == 0) lstrcpyW(n, L"De fábrica (la del juego)");
    else {
        lstrcpynW(n, g_pie_nombre[g_pie_sel - 1], MAX_PATH);
        int l = lstrlenW(n);
        if (l > 4) n[l - 4] = 0;
    }
    wsprintfW(g_pie_txt, L"%s  ·  %d/%d", n, g_pie_pag + 1, pags < 1 ? 1 : pags);
    if (g_pie_gal) InvalidateRect(g_pie_gal, NULL, FALSE);
    if (g_n2_pag[N2P_PIEDRAS]) InvalidateRect(g_n2_pag[N2P_PIEDRAS], NULL, FALSE);
}

static void pie_aviso(const wchar_t *t)
{
    lstrcpynW(g_pie_estado, t, 400);
    if (g_n2_pag[N2P_PIEDRAS]) InvalidateRect(g_n2_pag[N2P_PIEDRAS], NULL, FALSE);
}

/* elegir la casilla i (0 = de fábrica) */
static void pie_elegir(int i)
{
    if (i < 0 || i > g_pie_n) return;
    if (i == 0) {
        pdr_poner(NULL, 0);
        g_pdr_elegida[0] = 0;
        g_pie_sel = 0;
        pie_aviso(L"Piedra de fábrica.");
    } else {
        wchar_t a[MAX_PATH * 2], por[200], t[400];
        pdr_carpeta(a);
        lstrcatW(a, g_pie_nombre[i - 1]);
        int w = 0, h = 0;
        DWORD *px = pdr_cargar(a, &w, &h);
        if (pdr_validar(px, w, h, por)) {
            if (px) HeapFree(GetProcessHeap(), 0, px);
            wsprintfW(t, L"«%s» %s.", g_pie_nombre[i - 1], por);
            pie_aviso(t);
            return;
        }
        pdr_poner(px, w);
        lstrcpyW(g_pdr_elegida, g_pie_nombre[i - 1]);
        g_pie_sel = i;
        if (!g_pdr_activo) pie_aviso(L"Elegida, pero el cambio de piedra no está enganchado al juego (mira d3d9_proxy.log).");
        else pie_aviso(L"Puesta. Si estás corriendo se ve al momento; si no, en la próxima carrera.");
    }
    ht_pedir_guardar();
    pie_textos();
}

/* copia una imagen a la carpeta de piedras si sirve. 1 = instalada */
static int pie_instalar_una(const wchar_t *origen, wchar_t *por)
{
    int w = 0, h = 0;
    DWORD *px = pdr_cargar(origen, &w, &h);
    int malo = pdr_validar(px, w, h, por);
    if (px) HeapFree(GetProcessHeap(), 0, px);
    if (malo) return 0;
    wchar_t d[MAX_PATH * 2];
    pdr_carpeta(d);
    CreateDirectoryW(d, NULL);
    const wchar_t *nombre = origen;
    for (const wchar_t *p = origen; *p; p++) if (*p == L'\\' || *p == L'/') nombre = p + 1;
    lstrcatW(d, nombre);
    if (!CopyFileW(origen, d, FALSE)) { lstrcpyW(por, L"no se pudo escribir en la carpeta de piedras"); return 0; }
    return 1;
}

static void pie_informe(int ok, int malos, const wchar_t *primer_malo, const wchar_t *por)
{
    wchar_t t[400];
    if (!malos) wsprintfW(t, L"Instalada(s): %d.", ok);
    else wsprintfW(t, L"Instalada(s): %d. No sirven: %d (por ejemplo «%s»: %s).", ok, malos, primer_malo, por);
    pie_listar();
    pie_textos();
    pie_aviso(t);
}

static void pie_instalar(void)
{
    typedef BOOL (WINAPI *F_ABRIR)(OPENFILENAMEW *);
    HMODULE cd = LoadLibraryW(L"comdlg32.dll");
    F_ABRIR f = cd ? (F_ABRIR)(void *)GetProcAddress(cd, "GetOpenFileNameW") : NULL;
    if (!f) return;
    static wchar_t buf[32768];
    buf[0] = 0;
    OPENFILENAMEW o;
    ZeroMemory(&o, sizeof(o));
    o.lStructSize = sizeof(o);
    o.hwndOwner = g_n2_per ? g_n2_per : g_ht_ven;
    o.lpstrFilter = L"Piedras (TGA o PNG)\0*.tga;*.png\0";
    o.lpstrTitle = L"Instalar piedras del ritmo (256 x 256, con el fondo transparente)";
    o.lpstrFile = buf; o.nMaxFile = 32768;
    o.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_ALLOWMULTISELECT | OFN_EXPLORER;
    if (!f(&o)) return;
    int ok = 0, malos = 0;
    wchar_t malo[MAX_PATH] = L"", por[200] = L"", por1[200] = L"";
    const wchar_t *dir = buf, *p = buf + lstrlenW(buf) + 1;
    if (!*p) {                                         /* uno solo: buf es la ruta entera */
        if (pie_instalar_una(buf, por)) ok++; else { malos++; lstrcpynW(malo, buf, MAX_PATH); lstrcpyW(por1, por); }
    } else {
        for (; *p; p += lstrlenW(p) + 1) {
            wchar_t a[MAX_PATH * 2];
            lstrcpynW(a, dir, MAX_PATH); lstrcatW(a, L"\\"); lstrcatW(a, p);
            if (pie_instalar_una(a, por)) ok++;
            else { if (!malos) { lstrcpynW(malo, p, MAX_PATH); lstrcpyW(por1, por); } malos++; }
        }
    }
    pie_informe(ok, malos, malo, por1);
}

static void pie_instalar_carpeta(void)
{
    typedef struct { HWND owner; void *raiz; LPWSTR nombre; LPCWSTR titulo; UINT flags; void *cb; LPARAM lp; int img; } PIE_BI;
    typedef void *(WINAPI *F_BUSCAR)(PIE_BI *);
    typedef BOOL (WINAPI *F_RUTA)(void *, LPWSTR);
    typedef void (WINAPI *F_LIBERAR)(void *);
    HMODULE sh = LoadLibraryW(L"shell32.dll"), ole = LoadLibraryW(L"ole32.dll");
    F_BUSCAR buscar = sh ? (F_BUSCAR)(void *)GetProcAddress(sh, "SHBrowseForFolderW") : NULL;
    F_RUTA ruta = sh ? (F_RUTA)(void *)GetProcAddress(sh, "SHGetPathFromIDListW") : NULL;
    F_LIBERAR liberar = ole ? (F_LIBERAR)(void *)GetProcAddress(ole, "CoTaskMemFree") : NULL;
    if (!buscar || !ruta) return;
    wchar_t nombre[MAX_PATH], dir[MAX_PATH];
    PIE_BI bi = { g_n2_per ? g_n2_per : g_ht_ven, NULL, nombre, L"Instalar todas las piedras de una carpeta (.tga y .png)",
                  0x1 /* BIF_RETURNONLYFSDIRS */, NULL, 0, 0 };
    void *pidl = buscar(&bi);
    if (!pidl) return;
    BOOL bien = ruta(pidl, dir);
    if (liberar) liberar(pidl);
    if (!bien) return;
    wchar_t q[MAX_PATH * 2];
    lstrcpyW(q, dir); lstrcatW(q, L"\\*.*");
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(q, &fd);
    int ok = 0, malos = 0, vistas = 0;
    wchar_t malo[MAX_PATH] = L"", por[200] = L"", por1[200] = L"";
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || !pie_es_imagen(fd.cFileName)) continue;
            vistas++;
            wchar_t a[MAX_PATH * 2];
            lstrcpyW(a, dir); lstrcatW(a, L"\\"); lstrcatW(a, fd.cFileName);
            if (pie_instalar_una(a, por)) ok++;
            else { if (!malos) { lstrcpynW(malo, fd.cFileName, MAX_PATH); lstrcpyW(por1, por); } malos++; }
        } while (FindNextFileW(h, &fd));
        FindClose(h);
    }
    if (!vistas) { pie_aviso(L"En esa carpeta no hay ningún .tga ni .png."); return; }
    pie_informe(ok, malos, malo, por1);
}

static void pie_quitar(void)
{
    if (g_pie_sel <= 0 || g_pie_sel > g_pie_n) { pie_aviso(L"Elige primero una piedra tuya (la de fábrica no se quita)."); return; }
    wchar_t t[MAX_PATH + 80], a[MAX_PATH * 2 + 2];
    wsprintfW(t, L"¿Quitar la piedra «%s»? Va a la papelera.", g_pie_nombre[g_pie_sel - 1]);
    if (MessageBoxW(g_n2_per ? g_n2_per : g_ht_ven, t, L"Ñ2Hock · Piedras", MB_YESNO | MB_ICONQUESTION) != IDYES) return;
    pdr_carpeta(a);
    lstrcatW(a, g_pie_nombre[g_pie_sel - 1]);
    a[lstrlenW(a) + 1] = 0;                            /* doble cero de SHFileOperation */
    typedef int (WINAPI *F_OP)(SHFILEOPSTRUCTW *);
    HMODULE sh = LoadLibraryW(L"shell32.dll");
    F_OP op = sh ? (F_OP)(void *)GetProcAddress(sh, "SHFileOperationW") : NULL;
    SHFILEOPSTRUCTW s;
    ZeroMemory(&s, sizeof(s));
    s.hwnd = g_n2_per; s.wFunc = FO_DELETE; s.pFrom = a;
    s.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT;
    int bien = op && op(&s) == 0 && !s.fAnyOperationsAborted;
    if (!bien) { pie_aviso(L"No se pudo quitar (¿está abierta en otro programa?)."); return; }
    pie_elegir(0);                                     /* era la puesta: vuelve la de fábrica */
    pie_listar();
    pie_textos();
    pie_aviso(L"Quitada (está en la papelera). Vuelve la piedra de fábrica.");
}

static void pie_abrir_carpeta(void)
{
    wchar_t r[MAX_PATH];
    pdr_carpeta(r);
    CreateDirectoryW(r, NULL);
    typedef HINSTANCE (WINAPI *F_EXEC)(HWND, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, INT);
    HMODULE sh = LoadLibraryW(L"shell32.dll");
    F_EXEC ex = sh ? (F_EXEC)(void *)GetProcAddress(sh, "ShellExecuteW") : NULL;
    if (ex) ex(g_n2_per, L"open", r, NULL, NULL, SW_SHOWNORMAL);
    pie_aviso(L"Lo que dejes en esa carpeta (TGA o PNG) sale en la galería al volver a esta pestaña.");
}

/* ── la galería ── */
static int pie_celda_en(int x, int y)              /* el índice (0 = de fábrica) o -1 */
{
    int c = x / PIE_CELDA, f = y / PIE_CELDA;
    if (c < 0 || c >= PIE_COLS || f < 0 || f >= PIE_FILAS) return -1;
    int i = g_pie_pag * PIE_POR_PAG + f * PIE_COLS + c;
    return i <= g_pie_n ? i : -1;
}

static LRESULT CALLBACK pie_gal_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    switch (m) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
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
        for (int k = 0; k < PIE_POR_PAG; k++) {
            int i = g_pie_pag * PIE_POR_PAG + k;
            if (i > g_pie_n) break;
            int x = (k % PIE_COLS) * PIE_CELDA, y = (k / PIE_COLS) * PIE_CELDA;
            RECT r = { x + 2, y + 2, x + PIE_CELDA - 2, y + PIE_CELDA - 2 };
            HBRUSH b = CreateSolidBrush(i == g_pie_hover ? RGB(44, 48, 72) : RGB(28, 31, 50));
            FillRect(dc, &r, b);
            DeleteObject(b);
            if (i == 0) {
                SetTextColor(dc, RGB(200, 206, 220));
                DrawTextW(dc, L"De\nfábrica", -1, &r, DT_CENTER | DT_WORDBREAK | DT_NOPREFIX);
            } else if (g_pie_mini[i - 1]) {
                HDC m2 = CreateCompatibleDC(dc);
                HGDIOBJ om = SelectObject(m2, g_pie_mini[i - 1]);
                BLENDFUNCTION bf = { AC_SRC_OVER, 0, 255, AC_SRC_ALPHA };
                int o = (PIE_CELDA - PIE_MINI) / 2;
                GdiAlphaBlend(dc, x + o, y + o, PIE_MINI, PIE_MINI, m2, 0, 0, PIE_MINI, PIE_MINI, bf);
                SelectObject(m2, om);
                DeleteDC(m2);
            } else {
                SetTextColor(dc, RGB(251, 146, 60));
                DrawTextW(dc, L"?", -1, &r, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            }
            if (i == g_pie_sel) {
                HPEN p = CreatePen(PS_SOLID, 2, N2_ACENTO);
                HGDIOBJ op = SelectObject(dc, p), obr = SelectObject(dc, GetStockObject(NULL_BRUSH));
                Rectangle(dc, r.left, r.top, r.right + 1, r.bottom + 1);
                SelectObject(dc, op); SelectObject(dc, obr); DeleteObject(p);
            }
        }
        SelectObject(dc, of);
        BitBlt(d0, 0, 0, c.right, c.bottom, dc, 0, 0, SRCCOPY);
        SelectObject(dc, ob); DeleteObject(bm); DeleteDC(dc);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_MOUSEMOVE: {
        int i = pie_celda_en((short)LOWORD(lp), (short)HIWORD(lp));
        if (i != g_pie_hover) {
            g_pie_hover = i;
            TRACKMOUSEEVENT t = { sizeof(t), TME_LEAVE, h, 0 };
            TrackMouseEvent(&t);
            InvalidateRect(h, NULL, FALSE);
        }
        return 0;
    }
    case WM_MOUSELEAVE: g_pie_hover = -1; InvalidateRect(h, NULL, FALSE); return 0;
    case WM_LBUTTONDOWN: {
        int i = pie_celda_en((short)LOWORD(lp), (short)HIWORD(lp));
        if (i >= 0) pie_elegir(i);
        return 0;
    }
    case WM_MOUSEWHEEL: {
        int pags = (g_pie_n + 1 + PIE_POR_PAG - 1) / PIE_POR_PAG;
        g_pie_pag += (short)HIWORD(wp) > 0 ? -1 : 1;
        if (g_pie_pag >= pags) g_pie_pag = pags - 1;
        if (g_pie_pag < 0) g_pie_pag = 0;
        pie_textos();
        return 0;
    }
    }
    return DefWindowProcW(h, m, wp, lp);
}

/* el comando de un botón de la pestaña. 1 = era nuestro */
static int pie_comando(int ref)
{
    int pags = (g_pie_n + 1 + PIE_POR_PAG - 1) / PIE_POR_PAG;
    switch (ref) {
    case B_PIE_INSTALAR: pie_instalar(); return 1;
    case B_PIE_CARPETA_INST: pie_instalar_carpeta(); return 1;
    case B_PIE_QUITAR: pie_quitar(); return 1;
    case B_PIE_ABRIR: pie_abrir_carpeta(); return 1;
    case B_PIE_ANT: if (g_pie_pag > 0) g_pie_pag--; pie_textos(); return 1;
    case B_PIE_SIG: if (g_pie_pag < pags - 1) g_pie_pag++; pie_textos(); return 1;
    }
    return 0;
}

/* lo arma n2_per_maquetar (página 8) */
static void pie_maquetar(void)
{
    static int registrada = 0;
    if (!registrada) {
        WNDCLASSEXW wc;
        ZeroMemory(&wc, sizeof(wc));
        wc.cbSize = sizeof(wc); wc.hInstance = GetModuleHandleA(NULL); wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_HAND);
        wc.lpfnWndProc = pie_gal_proc; wc.lpszClassName = L"N2HPiedras";
        RegisterClassExW(&wc);
        registrada = 1;
    }
    n2_lienzo(N2P_PIEDRAS);
    n2_lbl(8, 6, 330, 20, L"Piedras del ritmo (el dibujo de las notas)", N2_C_ACENTO, N2_IZQ);
    g_pie_gal = CreateWindowExW(0, L"N2HPiedras", L"", WS_CHILD | WS_VISIBLE, 3 + 14, 3 + 28, PIE_COLS * PIE_CELDA,
                                PIE_FILAS * PIE_CELDA, g_n2_pag[N2P_PIEDRAS], NULL, GetModuleHandleA(NULL), NULL);
    int y = 28 + PIE_FILAS * PIE_CELDA + 6;
    n2_lbl(14, y, 250, 22, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_pie_txt;
    n2_boton(268, y - 1, 34, 24, L"◄", B_PIE_ANT);
    n2_boton(304, y - 1, 34, 24, L"►", B_PIE_SIG);
    y += 28;
    n2_boton(14, y, 158, 26, L"Instalar piedras...", B_PIE_INSTALAR);
    n2_boton(180, y, 158, 26, L"Instalar una carpeta...", B_PIE_CARPETA_INST);
    y += 30;
    n2_boton(14, y, 158, 26, L"Quitar", B_PIE_QUITAR);
    n2_boton(180, y, 158, 26, L"Carpeta...", B_PIE_ABRIR);
    y += 30;
    n2_lbl(14, y, 324, 34, NULL, N2_SUAVE, N2_PARR); g_n2l[g_n2nl - 1].dyn = g_pie_estado;
    if (!g_pie_estado[0]) lstrcpyW(g_pie_estado, L"TGA o PNG con transparencia, de 256 x 256 px (4 x 4 casillas).");
    pie_listar();
    pie_textos();
}
