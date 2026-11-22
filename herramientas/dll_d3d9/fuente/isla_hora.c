/* isla_hora.c — la isla del lobby de DÍA o de NOCHE según la hora de la PC del jugador
 *               (17-nov-2026, la isla de Navidad en dos variantes; documentacion/ISLA_DIA_Y_NOCHE.md)
 *
 * ★ LA IDEA: las dos islas viajan en dos paks que pisan la MISMA ruta (`rnr_ui_bg/front/`):
 *       rnr_ui_bg_isla_hw.pak        → la NOCHE (el nombre de la isla de temporada que ya está en prod)
 *       rnr_ui_bg_isla_hx_dia.pak    → el DÍA   (sólo texturas; carga DESPUÉS por nombre ⇒ si se ve, gana)
 *   De noche este módulo hace que el juego NO VEA el del día ⇒ gana el de noche. De día no hace nada.
 *
 * ★ LO MEDIDO en R2Beat/R2Beat.exe (sólo lectura, pefile + capstone, 17-nov):
 *   · 0x407180 (el montaje de paks): abre `rnr_script.pak` aparte (0x407187) y llama TRES veces a 0x406DE0 con
 *     el comodín "*.pak" (0x8740A0) y la carpeta ".\" (0x8740A8), "rnr_music\" (0x874094) y "rnr_bg\" (0x87408C).
 *   · 0x406DE0 ENUMERA la carpeta: FindFirstFileA (IAT 0x873184, llamada en 0x406EFF) y FindNextFileA
 *     (IAT 0x873188, en 0x40700F). Cada `cFileName` (WIN32_FIND_DATAA+0x2C: el dato está en esp+0xBC y el nombre
 *     se lee de esp+0xE8) se arma «carpeta + nombre» (0x4038D0) y se guarda en un std::set<string> (0x4055B0) ⇒
 *     queda ORDENADO por nombre. Después lo recorre en orden y monta cada uno con 0x67AE70(ruta, 0), salteando
 *     los que contienen "rnr_script.pak" (strstr 0x750500). Por eso «gana el último por nombre»: "..._hw" < "..._hx".
 *   · Si FindFirstFileA devuelve INVALID_HANDLE_VALUE, 0x406DE0 limpia y vuelve sin montar nada (0x406F07): el
 *     juego tolera una carpeta sin paks. Y un pak que no aparece en la lista simplemente no se monta: nadie lo pide
 *     por nombre (las únicas referencias a "rnr_script.pak" son esas dos; no hay otra lista fija).
 *   · La otra llamada a FindFirstFileA del exe (0x49877F) mira "C:\earlyover" y no tiene que ver: como el filtro
 *     es por NOMBRE EXACTO de archivo, no la toca.
 *   ⇒ EL GANCHO: FindFirstFileA y FindNextFileA por la TABLA DE IMPORTACIONES del exe (parchear_iat, como
 *     ChangeDisplaySettingsA): de noche, la entrada `rnr_ui_bg_isla_hx_dia.pak` se saltea. No se escribe una sola
 *     instrucción del juego, y los otros módulos (mss32, d3d9 del sistema…) tienen su propia tabla: no se tocan.
 *   ⚠ El montaje corre en el WinMain del juego; esto se engancha en el DllMain de la dll ⇒ siempre llega antes.
 *
 * ★ LA HORA: GetLocalTime (la hora local de la PC), UNA vez al arrancar. ⚠ El cambio día/noche se ve al ABRIR el
 *   juego: los paks se montan una sola vez y no se vuelven a leer. El que juega de 18:50 a 20:00 sigue con el día.
 *
 * ★ EL INI (d3d9_proxy.ini, al lado de la dll):
 *       [isla_hora]
 *       activo=1          ; 0 lo apaga: se ven los dos paks y gana el del día (el de fábrica de la carga por nombre)
 *       dia_desde=7       ; hora (0..23) en que EMPIEZA el día, incluida
 *       dia_hasta=19      ; hora (0..24) en que TERMINA el día, excluida ⇒ 7..18:59 día, 19..6:59 noche
 *       forzar=           ; vacío = según el reloj · dia · noche  (para probar sin esperar)
 *   desde > hasta da vuelta la medianoche (p. ej. 20 y 6 = día de 20 a 5:59). desde = hasta: siempre día.
 *   Un valor fuera de rango vuelve al de fábrica (7 / 19) y lo dice el log.
 *
 * ★ La lógica que decide (ih_* de abajo, sin ganchos) se prueba en un banco de C SIN abrir el juego:
 *   herramientas/dll_d3d9/banco/banco_isla_hora.c, lo arma y lo corre pruebas/probar_isla_hora.py. */

#define IH_PAK_DIA       "rnr_ui_bg_isla_hx_dia.pak"
#define IH_PAK_NOCHE     "rnr_ui_bg_isla_hw.pak"
/* ★ 18-nov: el DÍA viaja como .r2b: el juego sólo monta «*.pak», así que con la dll de PROD no se ve nunca
 * (el launcher no borra lo que sobra: el que probó el test server y volvió a prod se quedaba con la Navidad de día).
 * De día ESTA dll lo agrega al final de la lista de la raíz; el std::set lo ordena después de «..._hw.pak». */
#define IH_R2B_DIA       "rnr_ui_bg_isla_hx_dia.r2b"
#define IH_DESDE_FABRICA 7
#define IH_HASTA_FABRICA 19

typedef HANDLE (WINAPI *IH_PRIMERO)(LPCSTR, LPWIN32_FIND_DATAA);
typedef BOOL   (WINAPI *IH_SIGUIENTE)(HANDLE, LPWIN32_FIND_DATAA);

static int          g_ih_esconder = 0;       /* 1 = es de noche: el pak del día no se ve */
static long         g_ih_escondidos = 0;
static int          g_ih_agregar = 0;        /* 1 = es de día y está el .r2b: se agrega a la lista de la raíz */
static HANDLE       g_ih_raiz = NULL;        /* la búsqueda «.\*.pak» que está corriendo */
static int          g_ih_pendiente = 0;
static int          g_ih_patrones = 0;
static IH_PRIMERO   g_ih_primero_real = NULL;
static IH_SIGUIENTE g_ih_siguiente_real = NULL;

/* ── la lógica pura (la prueba el banco) ─────────────────────────────────── */

/* ¿la hora `hora` (0..23) es de día, con el día de `desde` (incluida) a `hasta` (excluida)? */
static int ih_es_de_dia(int hora, int desde, int hasta)
{
    if (desde == hasta) return 1;                          /* sin noche */
    if (desde < hasta) return hora >= desde && hora < hasta;
    return hora >= desde || hora < hasta;                  /* da vuelta la medianoche */
}

/* `forzar=`: 0 = según el reloj (vacío), 1 = día, 2 = noche, -1 = no lo entiendo (se usa el reloj) */
static int ih_forzado(const char *s)
{
    if (!s) return 0;
    while (*s == ' ' || *s == '\t') s++;
    if (!*s) return 0;
    if (lstrcmpiA(s, "dia") == 0 || lstrcmpiA(s, "d\xC3\xAD" "a") == 0 || lstrcmpiA(s, "d\xED" "a") == 0) return 1;
    if (lstrcmpiA(s, "noche") == 0) return 2;
    return -1;
}

/* ¿hay que esconder el pak del día? (1 = sí, es de noche) */
static int ih_hay_que_esconder(int activo, int forzado, int hora, int desde, int hasta)
{
    if (!activo) return 0;
    if (forzado == 1) return 0;
    if (forzado == 2) return 1;
    return !ih_es_de_dia(hora, desde, hasta);
}

static int ih_es_el_del_dia(const char *nombre)
{
    return nombre && lstrcmpiA(nombre, IH_PAK_DIA) == 0;
}

/* ¿es la búsqueda de los paks de la RAÍZ? (0x406DE0 con ".\\" y "*.pak"; las de rnr_music\ y rnr_bg\ no) */
static int ih_es_la_raiz(const char *patron)
{
    return patron && (lstrcmpiA(patron, ".\\*.pak") == 0 || lstrcmpiA(patron, "*.pak") == 0);
}

/* ── los ganchos ──────────────────────────────────────────────────────────── */

static void ih_contar(void)
{
    if (g_ih_escondidos++ == 0)
        apuntar("  [isla_hora] es de noche: %s no se monta (gana %s)", IH_PAK_DIA, IH_PAK_NOCHE);
}

static HANDLE WINAPI ih_primero(LPCSTR patron, LPWIN32_FIND_DATAA fd)
{
    HANDLE h = g_ih_primero_real(patron, fd);
    if (g_ih_patrones < 4) { g_ih_patrones++; apuntar("  [isla_hora] el juego busca «%s»", patron ? patron : "(nulo)"); }
    if (g_ih_agregar && h != INVALID_HANDLE_VALUE && ih_es_la_raiz(patron)) { g_ih_raiz = h; g_ih_pendiente = 1; }
    if (h == INVALID_HANDLE_VALUE || !g_ih_esconder) return h;
    while (ih_es_el_del_dia(fd->cFileName)) {
        ih_contar();
        if (!g_ih_siguiente_real(h, fd)) {
            /* era el ÚNICO que coincidía: para el juego, la carpeta no tiene ninguno */
            FindClose(h);
            SetLastError(ERROR_FILE_NOT_FOUND);
            return INVALID_HANDLE_VALUE;
        }
    }
    return h;
}

static BOOL WINAPI ih_siguiente(HANDLE h, LPWIN32_FIND_DATAA fd)
{
    for (;;) {
        BOOL r = g_ih_siguiente_real(h, fd);              /* al final deja ERROR_NO_MORE_FILES, como siempre */
        if (!r && g_ih_pendiente && h == g_ih_raiz) {      /* ★ de día: una entrada más, el .r2b del día */
            WIN32_FIND_DATAA d;
            HANDLE x = g_ih_primero_real(".\\" IH_R2B_DIA, &d);
            g_ih_pendiente = 0;
            if (x != INVALID_HANDLE_VALUE) {
                FindClose(x);
                *fd = d;
                apuntar("  [isla_hora] es de día: agrego %s a los paks de la raíz (gana sobre %s)", IH_R2B_DIA, IH_PAK_NOCHE);
                SetLastError(ERROR_SUCCESS);
                return TRUE;
            }
            SetLastError(ERROR_NO_MORE_FILES);
            return FALSE;
        }
        if (!r || !g_ih_esconder || !ih_es_el_del_dia(fd->cFileName)) return r;
        ih_contar();
    }
}

static int ih_existe(const char *nombre);

static int ih_existe(const char *nombre)
{
    char ruta[MAX_PATH];
    lstrcpynA(ruta, g_carpeta, MAX_PATH);
    if (lstrlenA(ruta) + lstrlenA(nombre) >= MAX_PATH) return 0;
    lstrcatA(ruta, nombre);
    return GetFileAttributesA(ruta) != INVALID_FILE_ATTRIBUTES;
}

static void isla_hora_iniciar(void)
{
    char ini[MAX_PATH], forzar[32];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    int activo = GetPrivateProfileIntA("isla_hora", "activo", 1, ini);
    int desde  = GetPrivateProfileIntA("isla_hora", "dia_desde", IH_DESDE_FABRICA, ini);
    int hasta  = GetPrivateProfileIntA("isla_hora", "dia_hasta", IH_HASTA_FABRICA, ini);
    forzar[0] = 0;
    GetPrivateProfileStringA("isla_hora", "forzar", "", forzar, sizeof(forzar), ini);
    if (!activo) {
        apuntar("  [isla_hora] APAGADO ([isla_hora] activo=0): se montan los dos paks de la isla");
        return;
    }
    if (desde < 0 || desde > 23 || hasta < 0 || hasta > 24) {
        apuntar("  [isla_hora] ⚠ horario fuera de rango (dia_desde=%d dia_hasta=%d): uso %d..%d",
                desde, hasta, IH_DESDE_FABRICA, IH_HASTA_FABRICA);
        desde = IH_DESDE_FABRICA;
        hasta = IH_HASTA_FABRICA;
    }
    int forzado = ih_forzado(forzar);
    if (forzado < 0) apuntar("  [isla_hora] ⚠ forzar=%s no lo entiendo (dia / noche / vacío): uso el reloj", forzar);
    SYSTEMTIME t;
    GetLocalTime(&t);
    g_ih_esconder = ih_hay_que_esconder(1, forzado, t.wHour, desde, hasta);
    apuntar("  [isla_hora] son las %02d:%02d (día de %d a %d)%s ⇒ isla de %s   [día: %s · noche: %s]",
            t.wHour, t.wMinute, desde, hasta,
            forzado == 1 ? ", FORZADO a día" : forzado == 2 ? ", FORZADO a noche" : "",
            g_ih_esconder ? "NOCHE" : "DÍA",
            ih_existe(IH_PAK_DIA) ? "está" : ih_existe(IH_R2B_DIA) ? "está (.r2b)" : "no está",
            ih_existe(IH_PAK_NOCHE) ? "está" : "no está");
    g_ih_agregar = !g_ih_esconder && ih_existe(IH_R2B_DIA) && !ih_existe(IH_PAK_DIA);
    if (!g_ih_esconder && !g_ih_agregar) return;           /* de día sin .r2b no se engancha nada: cero costo */

    /* los originales: lo que había en la tabla; si no se pudo, el de kernel32 (el banco no tiene tabla) */
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    void *sig = parchear_iat("KERNEL32.dll", "FindNextFileA", (void *)ih_siguiente);
    g_ih_siguiente_real = sig ? (IH_SIGUIENTE)sig : (IH_SIGUIENTE)(void *)GetProcAddress(k32, "FindNextFileA");
    void *pri = parchear_iat("KERNEL32.dll", "FindFirstFileA", (void *)ih_primero);
    g_ih_primero_real = pri ? (IH_PRIMERO)pri : (IH_PRIMERO)(void *)GetProcAddress(k32, "FindFirstFileA");
    if (sig && pri)
        apuntar("  [isla_hora] enganchados FindFirstFileA y FindNextFileA (IAT 0x873184 / 0x873188)");
    else
        apuntar("  [isla_hora] ⚠ no pude enganchar%s%s: se va a ver la isla de DÍA",
                pri ? "" : " FindFirstFileA", sig ? "" : " FindNextFileA");
    if (g_ih_agregar && !(sig && pri)) g_ih_agregar = 0;
}
