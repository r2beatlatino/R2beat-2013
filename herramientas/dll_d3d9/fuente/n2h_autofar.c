/* n2h_autofar.c — Personalización · AutoFar (25-nov-2026): la curva Far según el BPM, editable
 *
 *   Como el ToolBit 0.6.40 («AutoFar: el Far según el BPM»): puntos «BPM Far», en línea recta entre dos puntos y,
 *   fuera de los extremos, el Far del extremo. La de fábrica es la de Ñ2Hock (148 → 18 · 180 → 17 · 277 → 11).
 *   El motor (ht_af_curva, herramienta.c) la usa al momento; se guarda en [herramienta] autofar_curva.
 *   Se incluye desde n2h_ventana.c (usa sus ayudantes).
 */

enum { B_AF_APLICAR = 80, B_AF_FABRICA };

static HWND    g_af_ed = NULL, g_af_graf = NULL;
static wchar_t g_af_estado[300];

static void af_aviso(const wchar_t *t)
{
    lstrcpynW(g_af_estado, t, 300);
    if (g_n2_pag[N2P_AUTOFAR]) InvalidateRect(g_n2_pag[N2P_AUTOFAR], NULL, FALSE);
    if (g_af_graf) InvalidateRect(g_af_graf, NULL, FALSE);
}

static void af_caja_desde_motor(void)
{
    char a[1200];
    wchar_t w[1200];
    if (g_ht_af_np < 0) ht_af_leer_ini();
    ht_af_texto(a, 1);
    MultiByteToWideChar(CP_ACP, 0, a, -1, w, 1200);
    if (g_af_ed) SetWindowTextW(g_af_ed, w);
}

static void af_aplicar(void)
{
    wchar_t t[1200], err[200];
    float pb[HT_AF_MAX], pf[HT_AF_MAX];
    int n = 0;
    if (!g_af_ed) return;
    GetWindowTextW(g_af_ed, t, 1200);
    if (ht_af_parsear(t, pb, pf, &n, err)) { af_aviso(err); return; }
    ht_af_poner(pb, pf, n);
    af_caja_desde_motor();                           /* ordenada y limpia */
    ht_pedir_guardar();
    wchar_t m[120];
    wsprintfW(m, TR(L"Curva puesta (%d puntos). Con AutoFar prendido se usa en la próxima lectura del BPM."), n);
    af_aviso(m);
}

static void af_fabrica(void)
{
    wchar_t w[64], err[200];
    float pb[HT_AF_MAX], pf[HT_AF_MAX];
    int n = 0;
    MultiByteToWideChar(CP_ACP, 0, HT_AF_FABRICA, -1, w, 64);
    if (ht_af_parsear(w, pb, pf, &n, err)) return;
    ht_af_poner(pb, pf, n);
    af_caja_desde_motor();
    ht_pedir_guardar();
    af_aviso(L"La curva de fábrica: 148 BPM → 18 · 180 → 17 · 277 → 11.");
}

static int af_comando(int ref)
{
    if (ref == B_AF_APLICAR) { af_aplicar(); return 1; }
    if (ref == B_AF_FABRICA) { af_fabrica(); return 1; }
    return 0;
}

/* la gráfica: BPM 60..320 (x) · Far 1..22 (y), la curva, los puntos y el BPM de ahora */
static LRESULT CALLBACK af_graf_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    if (m == WM_ERASEBKGND) return 1;
    if (m == WM_TIMER) { InvalidateRect(h, NULL, FALSE); return 0; }
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
    int L = 30, R = c.right - 8, T = 8, B = c.bottom - 20;
    #define AF_X(b) (L + (int)(((b) - 60.0f) * (R - L) / 260.0f))
    #define AF_Y(f) (B - (int)(((f) - 1.0f) * (B - T) / 21.0f))
    for (int f = 2; f <= 22; f += 4) {
        n2_linea(dc, L, AF_Y(f), R, AF_Y(f), RGB(36, 40, 58));
        wchar_t t[8]; wsprintfW(t, L"%d", f);
        RECT r = { 0, AF_Y(f) - 8, L - 4, AF_Y(f) + 8 };
        SetTextColor(dc, RGB(130, 140, 160)); DrawTextW(dc, TR(t), -1, &r, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
    }
    for (int b = 80; b <= 320; b += 40) {
        n2_linea(dc, AF_X(b), T, AF_X(b), B, RGB(36, 40, 58));
        wchar_t t[8]; wsprintfW(t, L"%d", b);
        RECT r = { AF_X(b) - 20, B + 2, AF_X(b) + 20, B + 18 };
        DrawTextW(dc, TR(t), -1, &r, DT_CENTER | DT_SINGLELINE);
    }
    /* la curva, muestreada con el motor */
    HPEN p = CreatePen(PS_SOLID, 2, N2_ACENTO);
    HGDIOBJ op = SelectObject(dc, p);
    for (int x = L; x <= R; x++) {
        float b = 60.0f + (float)(x - L) * 260.0f / (R - L);
        int y = AF_Y(ht_af_curva(b));
        if (x == L) MoveToEx(dc, x, y, NULL); else LineTo(dc, x, y);
    }
    SelectObject(dc, op); DeleteObject(p);
    /* los puntos */
    EnterCriticalSection(&g_ht_cs);
    int n = g_ht_af_np;
    float pb[HT_AF_MAX], pf[HT_AF_MAX];
    if (n > 0) { CopyMemory(pb, g_ht_af_pb, n * sizeof(float)); CopyMemory(pf, g_ht_af_pf, n * sizeof(float)); }
    LeaveCriticalSection(&g_ht_cs);
    HBRUSH bp = CreateSolidBrush(RGB(235, 238, 245));
    for (int i = 0; i < n; i++) {
        RECT r = { AF_X(pb[i]) - 3, AF_Y(pf[i]) - 3, AF_X(pb[i]) + 4, AF_Y(pf[i]) + 4 };
        FillRect(dc, &r, bp);
    }
    DeleteObject(bp);
    /* el BPM de la canción que corre */
    float bpm = g_ht_af_bpm;
    if (bpm >= 60.0f && bpm <= 320.0f) {
        n2_linea(dc, AF_X(bpm), T, AF_X(bpm), B, RGB(250, 204, 21));
        wchar_t t[40];
        int f10 = (int)(ht_af_curva(bpm) * 10 + 0.5f);
        wsprintfW(t, TR(L"%d BPM → Far %d.%d"), (int)(bpm + 0.5f), f10 / 10, f10 % 10);
        RECT r = { L + 4, T, R, T + 16 };
        SetTextColor(dc, RGB(250, 204, 21)); DrawTextW(dc, TR(t), -1, &r, DT_LEFT | DT_SINGLELINE);
    }
    #undef AF_X
    #undef AF_Y
    SelectObject(dc, of);
    BitBlt(d0, 0, 0, c.right, c.bottom, dc, 0, 0, SRCCOPY);
    SelectObject(dc, ob); DeleteObject(bm); DeleteDC(dc);
    EndPaint(h, &ps);
    return 0;
}

/* lo arma n2_per_maquetar (página 9) */
static void af_maquetar(void)
{
    static int registrada = 0;
    if (!registrada) {
        WNDCLASSEXW wc;
        ZeroMemory(&wc, sizeof(wc));
        wc.cbSize = sizeof(wc); wc.hInstance = GetModuleHandleA(NULL); wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
        wc.lpfnWndProc = af_graf_proc; wc.lpszClassName = L"N2HCurvaFar";
        RegisterClassExW(&wc);
        registrada = 1;
    }
    /* ★ 26-nov (boceto de anonimo03): debajo de la Personalización, en la pestaña Ventana */
    n2_lienzo(N2P_AUTOFAR);
    const int Y0 = 214;
    n2_lbl(8, Y0 + 6, 330, 20, L"AutoFar: el Far según el BPM de la canción", N2_C_ACENTO, N2_IZQ);
    n2_lbl(8, Y0 + 26, 330, 50, L"Un punto por línea: «BPM Far» (por ejemplo 170 17 o 185 16.5). Entre dos puntos va "
                                L"en línea recta; fuera de los extremos, el Far del extremo.", N2_SUAVE, N2_PARR);
    g_af_graf = CreateWindowExW(0, L"N2HCurvaFar", L"", WS_CHILD | WS_VISIBLE, 3 + 8, 3 + Y0 + 72, 330, 160,
                                g_n2_pag[N2P_AUTOFAR], NULL, GetModuleHandleA(NULL), NULL);
    if (g_af_graf) SetTimer(g_af_graf, 1, 500, NULL);  /* el BPM de ahora */
    {
        N2_CTL *c = n2_ctl(C_EDIT, L"Edit", L"", ES_MULTILINE | ES_AUTOVSCROLL | ES_WANTRETURN | WS_VSCROLL, 8, Y0 + 240,
                           150, 150, 0);
        g_af_ed = c ? c->h : NULL;
        if (g_af_ed) SetWindowPos(g_af_ed, NULL, c->r.left + 3, c->r.top + 3, 150 - 6, 150 - 6, SWP_NOZORDER | SWP_NOACTIVATE);
    }
    n2_boton(170, Y0 + 240, 168, 26, L"Aplicar", B_AF_APLICAR);
    n2_boton(170, Y0 + 272, 168, 26, L"De fábrica", B_AF_FABRICA);
    n2_lbl(170, Y0 + 304, 168, 86, NULL, N2_SUAVE, N2_PARR); g_n2l[g_n2nl - 1].dyn = g_af_estado;
    lstrcpyW(g_af_estado, TR(L"«Aplicar» la pone al momento y la guarda. Se usa con AutoFar prendido (pestaña General)."));
    af_caja_desde_motor();
}
