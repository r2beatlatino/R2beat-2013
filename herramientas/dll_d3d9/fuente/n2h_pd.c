/* n2h_pd.c — Personalización · Panel PD (25-nov-2026): el panel PD de la carrera (calculadora.c, el del 2019)
 *
 *   Lo que antes sólo se hacía con teclas dentro de la carrera, y lo nuevo (ideas del ToolBit 0.6.40):
 *     · mostrar / esconder (F9) · fijar posición y tamaño · tamaño (75..200 %) · volver a la posición de fábrica
 *     · ★ opacidad (20..100 %) · ★ color (tiñe el panel y sus números) · ★ quieto: no se aparta con el impulsor
 *   Los cambios del hilo del juego van como PEDIDOS (g_calc_ped_*, se cumplen en el próximo cuadro del panel).
 *   Se incluye desde n2h_ventana.c (usa sus ayudantes).
 */

/* ⚠ 26-nov: empezaban en 100 y chocaban con los del booster (B_BO_ARR = 100…): «Mostrar / esconder» movía el botón
 *   del booster. Ahora desde 120. */
enum { B_PD_VER = 120, B_PD_FIJAR, B_PD_MENOS, B_PD_MAS, B_PD_OP_MENOS, B_PD_OP_MAS, B_PD_COLOR, B_PD_SIN_COLOR,
       B_PD_FABRICA, B_PD_QUIETO,
       B_PD_FONDO_IMG, B_PD_FONDO_QUITAR, B_PD_FONDO_COLOR, B_PD_FONDO_FAB, B_PD_FOP_MENOS, B_PD_FOP_MAS, B_PD_NUM_COLOR,
       B_FJ_FONDO_MENOS, B_FJ_FONDO_MAS };                       /* ★ 26-nov: el fondo del panel del Far (pestaña Far) */
static wchar_t g_fj_txt_fondo[40];

static wchar_t g_pd_txt_estado[120], g_pd_txt_tam[40], g_pd_txt_op[40], g_pd_aviso[200], g_pd_txt_fop[40];
static int     g_pd_quieto_ui = 0;

static void pd_textos(void)
{
    wchar_t a[120], b[40], c[40];
    wsprintfW(a, TR(L"Panel %s · %s%s"), g_calc_oculto ? TR(L"escondido (F9)") : TR(L"a la vista"),
              g_calc_fijo ? L"fijado" : TR(L"se puede mover"), g_calc_quieto ? TR(L" · quieto con el impulsor") : L"");
    wsprintfW(b, TR(L"Tamaño %d %%"), g_calc_escala);
    wsprintfW(c, TR(L"Opacidad %d %%"), g_calc_opacidad);
    wchar_t d[40], e[40];
    wsprintfW(d, TR(L"Fondo %d %%"), g_pdn_fondo_op);
    wsprintfW(e, TR(L"Fondo del panel %d %%"), g_fj_fondo);
    if (lstrcmpW(e, g_fj_txt_fondo)) { lstrcpyW(g_fj_txt_fondo, e); if (g_n2_pag[6]) InvalidateRect(g_n2_pag[6], NULL, FALSE); }
    int cambio = lstrcmpW(a, g_pd_txt_estado) || lstrcmpW(b, g_pd_txt_tam) || lstrcmpW(c, g_pd_txt_op) || lstrcmpW(d, g_pd_txt_fop);
    lstrcpyW(g_pd_txt_estado, a); lstrcpyW(g_pd_txt_tam, b); lstrcpyW(g_pd_txt_op, c); lstrcpyW(g_pd_txt_fop, d);
    if (g_pd_quieto_ui != g_calc_quieto) { g_pd_quieto_ui = g_calc_quieto; cambio = 1; }
    if (cambio && g_n2_pag[N2P_PD]) InvalidateRect(g_n2_pag[N2P_PD], NULL, FALSE);
}

/* cada 50 ms desde n2_e_tick: los textos siguen a lo que hagan las teclas en la carrera */
static void pd_fondo_cargar(const wchar_t *ruta);
static void pd_tick(void)
{
    static DWORD ult = 0;
    static int cargado = 0;
    if (!cargado) { cargado = 1; if (g_pdn_fondo_ruta[0]) pd_fondo_cargar(g_pdn_fondo_ruta); }   /* el fondo guardado */
    if (GetTickCount() - ult < 300) return;
    ult = GetTickCount();
    pd_textos();
}

static void pd_aviso(const wchar_t *t)
{
    lstrcpynW(g_pd_aviso, t, 200);
    if (g_n2_pag[N2P_PD]) InvalidateRect(g_n2_pag[N2P_PD], NULL, FALSE);
}

/* ★ 26-nov: la imagen de fondo del panel nuevo */
static void pd_carpeta(wchar_t *r)                    /* r: MAX_PATH, termina en '\' */
{
    MultiByteToWideChar(CP_ACP, 0, g_carpeta, -1, r, MAX_PATH - 24);
    lstrcatW(r, L"n2hock_pd\\");
}
static void pd_fondo_cargar(const wchar_t *ruta)
{
    int w = 0, h = 0;
    DWORD *px = pdr_cargar(ruta, &w, &h);
    if (!px) { pd_aviso(L"No se pudo abrir la imagen de fondo guardada."); return; }
    pdn_poner_fondo(px, w, h);
    HeapFree(GetProcessHeap(), 0, px);
}
static void pd_fondo_elegir(void)
{
    typedef BOOL (WINAPI *F_ABRIR)(OPENFILENAMEW *);
    HMODULE cd = LoadLibraryW(L"comdlg32.dll");
    F_ABRIR f = cd ? (F_ABRIR)(void *)GetProcAddress(cd, "GetOpenFileNameW") : NULL;
    if (!f) return;
    wchar_t archivo[MAX_PATH] = L"";
    OPENFILENAMEW o;
    ZeroMemory(&o, sizeof(o));
    o.lStructSize = sizeof(o);
    o.hwndOwner = g_n2_per ? g_n2_per : g_ht_ven;
    o.lpstrFilter = L"Imágenes (PNG, JPG, TGA, BMP, GIF)\0*.png;*.jpg;*.jpeg;*.tga;*.bmp;*.gif\0";
    o.lpstrTitle = L"La imagen de fondo del panel PD (se ajusta sola: 200 x 252 se ve perfecto)";
    o.lpstrFile = archivo; o.nMaxFile = MAX_PATH;
    o.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!f(&o)) return;
    int w = 0, h = 0;
    DWORD *px = pdr_cargar(archivo, &w, &h);
    if (!px || w < 8 || h < 8) { if (px) HeapFree(GetProcessHeap(), 0, px); pd_aviso(L"No se pudo abrir esa imagen."); return; }
    /* una copia en n2hock_pd\ (así no depende de dónde estaba) */
    wchar_t d[MAX_PATH * 2];
    pd_carpeta(d);
    CreateDirectoryW(d, NULL);
    int n = lstrlenW(archivo);
    const wchar_t *ext = n > 4 && !lstrcmpiW(archivo + n - 4, L".tga") ? L"fondo.tga" : L"fondo.img";
    lstrcatW(d, ext);
    if (!CopyFileW(archivo, d, FALSE)) lstrcpynW(d, archivo, MAX_PATH);
    lstrcpynW(g_pdn_fondo_ruta, d, MAX_PATH);
    pdn_poner_fondo(px, w, h);
    HeapFree(GetProcessHeap(), 0, px);
    if (g_pdn_fondo_op < 60) g_pdn_fondo_op = 94;
    ht_pedir_guardar();
    pd_textos();
    pd_aviso(L"Fondo puesto: se ve en la carrera (el panel nuevo).");
}

static int pd_comando(int ref)
{
    switch (ref) {
    case B_PD_FONDO_IMG: pd_fondo_elegir(); return 1;
    case B_FJ_FONDO_MENOS: case B_FJ_FONDO_MAS: {
        int v = g_fj_fondo + (ref == B_FJ_FONDO_MAS ? 10 : -10);
        g_fj_fondo = v < 0 ? 0 : v > 100 ? 100 : v;
        ht_pedir_guardar();
        pd_textos();
        return 1;
    }
    case B_PD_FONDO_QUITAR:
        g_pdn_fondo_ruta[0] = 0; pdn_poner_fondo(NULL, 0, 0); ht_pedir_guardar(); pd_aviso(L"Sin imagen de fondo."); return 1;
    case B_PD_FONDO_COLOR: {
        DWORD t = g_pdn_fondo_color == 0xFFFFFFFF ? 0x18467A : g_pdn_fondo_color;
        COLORREF c = RGB((t >> 16) & 0xFF, (t >> 8) & 0xFF, t & 0xFF);
        if (n2_elegir_color(&c)) {
            g_pdn_fondo_color = ((DWORD)GetRValue(c) << 16) | ((DWORD)GetGValue(c) << 8) | GetBValue(c);
            ht_pedir_guardar();
            pd_aviso(g_pdn_fondo_ruta[0] ? L"Color de fondo puesto (se ve al quitar la imagen)." : L"Color de fondo puesto.");
        }
        return 1;
    }
    case B_PD_FONDO_FAB: g_pdn_fondo_color = 0xFFFFFFFF; ht_pedir_guardar(); pd_aviso(L"Fondo azul de fábrica."); return 1;
    case B_PD_FOP_MENOS: case B_PD_FOP_MAS: {
        int v = g_pdn_fondo_op + (ref == B_PD_FOP_MAS ? 10 : -10);
        g_pdn_fondo_op = v < 0 ? 0 : v > 100 ? 100 : v;
        ht_pedir_guardar();
        pd_textos();
        return 1;
    }
    case B_PD_NUM_COLOR: {
        DWORD t = g_pdn_num_color;
        COLORREF c = RGB((t >> 16) & 0xFF, (t >> 8) & 0xFF, t & 0xFF);
        if (n2_elegir_color(&c)) {
            g_pdn_num_color = ((DWORD)GetRValue(c) << 16) | ((DWORD)GetGValue(c) << 8) | GetBValue(c);
            if (g_pdn_arco) { g_pdn_arco = 0; n2_sincronizar(); }
            ht_pedir_guardar();
            pd_aviso(L"Color del número puesto (sin arcoíris).");
        }
        return 1;
    }
    case B_PD_VER: InterlockedExchange(&g_calc_ped_oculto, !g_calc_oculto); pd_aviso(L"Hecho (se ve en la carrera)."); return 1;
    case B_PD_FIJAR: InterlockedExchange(&g_calc_ped_fijo, !g_calc_fijo); pd_aviso(L"Hecho (se ve en la carrera)."); return 1;
    case B_PD_MENOS: case B_PD_MAS:
        if (g_calc_fijo) { pd_aviso(L"Está fijado: suéltalo para cambiar el tamaño."); return 1; }
        InterlockedExchange(&g_calc_ped_escala, ref == B_PD_MAS ? 1 : -1);
        pd_aviso(L"El tamaño cambia en el próximo cuadro de la carrera.");
        return 1;
    case B_PD_OP_MENOS: case B_PD_OP_MAS: {
        int v = g_calc_opacidad + (ref == B_PD_OP_MAS ? 10 : -10);
        g_calc_opacidad = v < 20 ? 20 : v > 100 ? 100 : v;
        ht_pedir_guardar();
        pd_textos();
        return 1;
    }
    case B_PD_COLOR: {
        DWORD t = g_calc_tinte;
        COLORREF c = RGB((t >> 16) & 0xFF, (t >> 8) & 0xFF, t & 0xFF);
        if (n2_elegir_color(&c)) {
            g_calc_tinte = ((DWORD)GetRValue(c) << 16) | ((DWORD)GetGValue(c) << 8) | GetBValue(c);
            ht_pedir_guardar();
            pd_aviso(L"Color puesto: tiñe el panel y sus números (blanco = sin color).");
        }
        return 1;
    }
    case B_PD_SIN_COLOR: g_calc_tinte = 0xFFFFFF; ht_pedir_guardar(); pd_aviso(L"Sin color."); return 1;
    case B_PD_FABRICA:
        if (g_calc_fijo) { pd_aviso(L"Está fijado: suéltalo para moverlo."); return 1; }
        InterlockedExchange(&g_calc_ped_fabrica, 1);
        pd_aviso(L"Vuelve a su sitio de fábrica en el próximo cuadro de la carrera.");
        return 1;
    }
    return 0;
}

/* lo arma n2_per_maquetar (página 11) */
static void pd_maquetar(void)
{
    n2_lienzo(N2P_PD);
    n2_lbl(8, 6, 330, 20, L"El panel PD de la carrera (el del cliente 2019)", N2_C_ACENTO, N2_IZQ);
    n2_lbl(14, 32, 324, 20, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_pd_txt_estado;
    n2_boton(14, 58, 158, 26, L"Mostrar / esconder", B_PD_VER);
    n2_boton(180, 58, 158, 26, L"Fijar / soltar", B_PD_FIJAR);
    n2_lbl(14, 98, 150, 22, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_pd_txt_tam;
    n2_boton(180, 96, 76, 26, L"Más chico", B_PD_MENOS);
    n2_boton(262, 96, 76, 26, L"Más grande", B_PD_MAS);
    n2_lbl(14, 132, 150, 22, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_pd_txt_op;
    n2_boton(180, 130, 76, 26, L"Menos", B_PD_OP_MENOS);
    n2_boton(262, 130, 76, 26, L"Más", B_PD_OP_MAS);
    n2_boton(14, 168, 158, 26, L"Color...", B_PD_COLOR);
    n2_boton(180, 168, 158, 26, L"Sin color", B_PD_SIN_COLOR);
    n2_chk_b(14, 204, 324, 22, L"Quieto: no se aparta con el impulsor (sólo con F9)", (int *)&g_calc_quieto);
    n2_boton(14, 236, 324, 26, L"Volver a su sitio de fábrica", B_PD_FABRICA);
    n2_lbl(14, 272, 324, 64, L"En la carrera: F9 lo esconde · Z lo fija · X / C más grande o más chico · "
                             L"V / B a la izquierda o a la derecha · N / M arriba o abajo.", N2_SUAVE, N2_PARR);
    n2_lbl(14, 340, 324, 44, NULL, N2_SUAVE, N2_PARR); g_n2l[g_n2nl - 1].dyn = g_pd_aviso;
    /* ★ 26-nov: el panel nuevo, editable */
    n2_lbl(8, 388, 330, 20, L"El panel nuevo: fondo y letras", N2_C_ACENTO, N2_IZQ);
    n2_boton(14, 412, 158, 26, L"Imagen de fondo...", B_PD_FONDO_IMG);
    n2_boton(180, 412, 158, 26, L"Quitar imagen", B_PD_FONDO_QUITAR);
    n2_boton(14, 444, 158, 26, L"Color de fondo...", B_PD_FONDO_COLOR);
    n2_boton(180, 444, 158, 26, L"Fondo de fábrica", B_PD_FONDO_FAB);
    n2_lbl(14, 478, 150, 22, NULL, N2_TEXTO, N2_IZQ); g_n2l[g_n2nl - 1].dyn = g_pd_txt_fop;
    n2_boton(180, 476, 76, 26, L"Menos", B_PD_FOP_MENOS);
    n2_boton(262, 476, 76, 26, L"Más", B_PD_FOP_MAS);
    n2_chk_b(14, 510, 324, 22, L"El número con arcoíris que se mueve", (int *)&g_pdn_arco);
    n2_boton(14, 536, 158, 26, L"Color del número...", B_PD_NUM_COLOR);
    n2_chk_b(14, 570, 324, 22, L"Mostrar Notas y Far", &g_pdn_ver_abajo);
    n2_chk_b(14, 594, 324, 22, L"Mostrar las flechas del teclado", &g_pdn_ver_teclado);
    n2_lbl(14, 620, 324, 34, L"«Fondo 0 %» deja sólo las letras. Con imagen, las letras llevan sombra para que se lean.",
           N2_SUAVE, N2_PARR);
    pd_textos();
}
