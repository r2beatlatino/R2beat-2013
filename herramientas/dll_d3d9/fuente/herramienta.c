/* ═══════════════════════════════════════════════════════════════════════════
 * herramienta.c — «R2beat tool»: NUESTRA herramienta de jugador, dentro de la d3d9
 *
 *   Reemplaza a ToolBit (una herramienta ajena, .NET, que abre el proceso desde
 *   afuera). Ésta vive ADENTRO del juego: la d3d9 ya está cargada antes del bucle,
 *   ya engancha funciones con guarda, y no hace falta abrir el proceso ni permisos.
 *   La historia, el inventario y las pruebas: documentacion/R2BEAT_TOOL.md.
 *
 *   ★ CÓMO SE PRENDE
 *     · `[herramienta] activo=1` en d3d9_proxy.ini (lo escribe el botón R2BEAT TOOL del
 *       launcher ANTES de lanzar). Se lee al arrancar: no depende de que el launcher siga
 *       vivo — vale con «mantener launcher abierto» marcado o no.
 *     · Si el juego ya está abierto, el launcher avisa con el evento con nombre
 *       `Local\R2beatTool.<pid>`: la dll relee `activo` y muestra (o apaga) la ventana.
 *     · Adentro del juego: F12 (`[herramienta] tecla`) muestra / oculta la ventana.
 *
 *   ★ REGLAS (las de toda la dll, y una más)
 *     · Toda escritura al exe va con GUARDA: si no está lo esperado no se toca, y se
 *       deja dicho en d3d9_proxy.log. La opción queda en gris («no disponible»).
 *     · Se escribe lo MÍNIMO: casi todas las opciones cambian UN byte (atómico). Las
 *       que cambian varios, frenan un instante el hilo del juego y comprueban que no
 *       esté parado justo adentro de lo que se reescribe.
 *     · Nada de esto es copia de ToolBit: se leyó cómo funciona para UBICAR los sitios
 *       (como con el PD Valofe, TOOLBIT_PD_VALOFE.md §5); los parches, el gancho de las
 *       notas y la ventana son nuestros. Varios bytes nuevos son DISTINTOS a los suyos.
 *     · Estrella <-> Obstáculo NO es el de ToolBit: el suyo pinta el modelo y deja que
 *       el juego le sume +6 al «corazón» de la pareja (§ el gancho de las notas).
 *
 *   ★ 04-oct: «Configuración de Teclado» (dos juegos de teclas a la vez, § 4b), las teclas
 *     de los atajos se asignan APRETÁNDOLAS (clic en el botón y la tecla), y la ventana es
 *     nuestra de punta a punta (dibujada a mano, con los colores del launcher web).
 *
 *   ⚠ Se INCLUYE desde d3d9_proxy.c (después de fluidez.c): usa `apuntar()` y
 *     `g_carpeta`, y — si la calculadora está prendida — `calc_escribiendo()`.
 * ═══════════════════════════════════════════════════════════════════════════ */

#define HT_TC __attribute__((thiscall))
#define HT_VA(x) (g_ht_base + ((DWORD)(x) - 0x400000))

/* ★ anonimo03 decide qué se permite (R2BEAT_TOOL.md §5, «las que pueden ser trampa»).
 *   Poner un 0 acá deja la opción EN GRIS (ni casilla ni atajo): no se aplica nunca,
 *   diga lo que diga el ini. Hoy están todas permitidas: la decisión no es mía. */
#define HT_PERMITIR_SUPR       1    /* Locura/Niebla/Sin Piedra/Espejo «Supr»          */
#define HT_PERMITIR_AUTOCTRL   1    /* AutoCtrl                                        */
#define HT_PERMITIR_OPACIDAD   1    /* Opacidad obstáculos                             */
#define HT_PERMITIR_FAR        1    /* Far Vision                                      */
#define HT_PERMITIR_RESULTADOS 1    /* Resultados rápido                               */

/* ── el mapa (✔ leído del exe, igual en R2Beat_local.exe y en el de prod) ───── */
#define HT_SALA        0x00931660   /* el administrador de asientos ([+0x40] = mi asiento) */
#define HT_PARTIDA     0x009314C8   /* cGame ([+0x0C] banderas del modo)               */
#define HT_TABLA_MOD   0x009D4414   /* la tabla de modelos de las notas (block.txt + …) */
#define HT_F_MODELO    0x004E6740   /* tabla->modelo_de(tipo): el 1er índice con ese tipo */
#define HT_F_NOTA      0x005010E0   /* jugador->retocar_nota(nota): estrella o CORAZÓN */
#define HT_F_EFECTO    0x005285D0   /* sala->tiene_efecto(asiento, efecto) (cupones FF80) */
#define HT_LLAMADA_ESPEJO 0x0056D9C6 /* la única llamada que decide el espejo al largar */
#define HT_FAR_A       0x009D45E0   /* hasta dónde se ve (float, lo arma el exe al iniciar) */
#define HT_FAR_B       0x009D45D8   /* su pareja de cerca (float)                         */

/* los tipos de nota (el `Type` de block.txt; la tabla los repite: ver el doc §2) */
#define HT_OBST_IZQ   0x12
#define HT_OBST_DER   0x13
#define HT_ESTR_IZQ   0x1A
#define HT_ESTR_DER   0x1B
#define HT_EFECTO_ESPEJO 0x18A      /* 1000206 Modo Espejo (los otros: 0x18B niebla, 0x18C locura, 0x278 sin piedras) */

typedef WORD (HT_TC *HT_FMODELO)(void *tabla, int tipo);
typedef void (HT_TC *HT_FNOTA)(void *jugador, BYTE *nota);
typedef int  (HT_TC *HT_FEFECTO)(void *sala, int asiento, int efecto);

static BYTE *g_ht_base = NULL;
static char  g_ht_ini[MAX_PATH];
static volatile DWORD g_ht_hilo_juego = 0;  /* el hilo que juzga las notas (= el del bucle)  */
static volatile LONG  g_ht_arrancada = 0;   /* ganchos + ventana: una sola vez               */
static volatile int   g_ht_apagada = 0;     /* el launcher la apagó en vivo                   */
static HANDLE g_ht_evento = NULL;
static HWND   g_ht_ven = NULL;
static volatile int g_ht_mostrar_pedido = 0;
static CRITICAL_SECTION g_ht_cs;            /* escrituras al exe y al ini, de a una          */

static HT_FNOTA   g_ht_nota_real = NULL;
static HT_FMODELO g_ht_f_modelo = NULL;     /* = 0x4E6740 (puntero: así el banco lo puede simular) */
static void     **g_ht_tabla_mod = NULL;    /* = &[0x9D4414]                                    */
static HT_FEFECTO g_ht_efecto_real = NULL;
static int g_ht_gancho_notas = 0, g_ht_gancho_espejo = 0;

/* ═══ 1 · ESCRIBIR AL EXE, CON GUARDA ═══════════════════════════════════════════
 *   `esp` y `nue` tienen el mismo largo: la guarda compara TODO (contexto incluido) y
 *   se escriben sólo los bytes que cambian. Si cambia uno, es atómico. Si cambian
 *   varios, se frena el hilo del juego y se mira que su EIP no esté adentro del tramo
 *   (si lo está, se suelta, se espera 1 ms y se vuelve a probar). */
/* ¿esa memoria existe y se puede leer (o escribir)? Con otro exe — más chico, o reubicado —
 * leer HT_VA(...) a ciegas sería una violación de acceso: la guarda tiene que poder MIRAR. */
static int ht_memoria_ok(const void *p, int n, int escribir)
{
    MEMORY_BASIC_INFORMATION mi;
    const BYTE *a = (const BYTE *)p;
    while (n > 0) {
        if (!VirtualQuery(a, &mi, sizeof(mi)) || mi.State != MEM_COMMIT) return 0;
        DWORD pr = mi.Protect & 0xFF;
        if ((mi.Protect & PAGE_GUARD) || pr == PAGE_NOACCESS) return 0;
        if (escribir && !(pr == PAGE_READWRITE || pr == PAGE_WRITECOPY
                          || pr == PAGE_EXECUTE_READWRITE || pr == PAGE_EXECUTE_WRITECOPY)) return 0;
        int resto = (int)(((const BYTE *)mi.BaseAddress + mi.RegionSize) - a);
        if (resto <= 0) return 0;
        a += resto; n -= resto;
    }
    return 1;
}

static int ht_escribir(DWORD va, const BYTE *esp, const BYTE *nue, int n, const char *que)
{
    BYTE *s = HT_VA(va);
    int d0 = -1, d1 = -1;
    if (!ht_memoria_ok(s, n, 0)) {
        apuntar("  [tool] ⛔ %s: 0x%08X no existe en este exe. NO SE TOCA.", que, va);
        return 0;
    }
    for (int i = 0; i < n; i++) {
        if (s[i] != esp[i]) {
            char hex[64]; hex[0] = 0;
            for (int j = 0; j < n && j < 12; j++) wsprintfA(hex + lstrlenA(hex), "%02X ", s[j]);
            apuntar("  [tool] ⛔ %s: en 0x%08X hay [%s] y esperaba otra cosa. NO SE TOCA.", que, va, hex);
            return 0;
        }
        if (esp[i] != nue[i]) { if (d0 < 0) d0 = i; d1 = i; }
    }
    if (d0 < 0) return 1;
    EnterCriticalSection(&g_ht_cs);
    DWORD viejo = 0;
    if (!VirtualProtect(s, n, PAGE_EXECUTE_READWRITE, &viejo)) {
        LeaveCriticalSection(&g_ht_cs);
        apuntar("  [tool] ⛔ %s: no pude abrir la memoria en 0x%08X", que, va);
        return 0;
    }
    HANDLE th = NULL;
    if (d1 > d0 && g_ht_hilo_juego && g_ht_hilo_juego != GetCurrentThreadId())
        th = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT, FALSE, g_ht_hilo_juego);
    for (int intento = 0; th; intento++) {
        if (SuspendThread(th) == (DWORD)-1) { CloseHandle(th); th = NULL; break; }
        CONTEXT c;
        ZeroMemory(&c, sizeof(c));
        c.ContextFlags = CONTEXT_CONTROL;
        DWORD eip = GetThreadContext(th, &c) ? c.Eip : 0;
        if (eip > (DWORD)(ULONG_PTR)(s + d0) && eip <= (DWORD)(ULONG_PTR)(s + d1)) {
            ResumeThread(th);
            if (intento >= 200) {               /* 200 veces justo ahí: no se arriesga, se deja como estaba */
                CloseHandle(th);
                VirtualProtect(s, n, viejo, &viejo);
                LeaveCriticalSection(&g_ht_cs);
                apuntar("  [tool] ⚠ %s: el juego está parado justo en 0x%08X; NO SE TOCA (probar de nuevo)", que, va);
                return -1;                      /* pasajero: NO es «exe distinto» */
            }
            Sleep(1);
            continue;
        }
        break;                                  /* frenado, y no está adentro del tramo */
    }
    for (int i = d0; i <= d1; i++) s[i] = nue[i];
    VirtualProtect(s, n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, n);
    if (th) { ResumeThread(th); CloseHandle(th); }
    LeaveCriticalSection(&g_ht_cs);
    return 1;
}

/* ═══ 2 · LAS OPCIONES ═══════════════════════════════════════════════════════
 *   Un parche = un tramo con su guarda (antes) y lo nuevo. Los tramos llevan bytes de
 *   CONTEXTO (iguales en las dos columnas) para que la guarda sea más estricta que el
 *   byte que se cambia. Cada uno está explicado en R2BEAT_TOOL.md §1. */
typedef struct { DWORD va; BYTE n; BYTE antes[8]; BYTE ahora[8]; } HT_TRAMO;

/* Cámara fija — 0x4FE3A0 mueve la cámara del jugador local en cada paso: que vuelva al entrar */
static const HT_TRAMO T_CAMARA[] = { { 0x004FE3A0, 5, {0xA1,0xC8,0x14,0x93,0x00}, {0xC3,0xC8,0x14,0x93,0x00} } };
/* Efecto booster — 0x531510 dibuja el efecto del impulsor (thiscall, 1 arg): `ret 4` al entrar */
static const HT_TRAMO T_BOOSTER[] = { { 0x00531510, 4, {0x53,0x56,0x8B,0x74}, {0xC2,0x04,0x00,0x74} } };
/* Efecto Ghost — las dos ramas que encienden el «fantasma» con el combo ≥ 40: siempre saltearlas */
static const HT_TRAMO T_GHOST[] = {
    { 0x0050BF76, 6, {0x0F,0x85,0xE6,0x02,0x00,0x00}, {0xE9,0xE7,0x02,0x00,0x00,0x90} },
    { 0x0050C146, 6, {0x0F,0x85,0x14,0x01,0x00,0x00}, {0xE9,0x15,0x01,0x00,0x00,0x90} } };
/* AutoCtrl — 0x4EB210: «si Ctrl está apretado, mandar la acción» -> «si NO lo está» */
static const HT_TRAMO T_AUTOCTRL[] = { { 0x004EB20E, 4, {0x85,0xC0,0x74,0x18}, {0x85,0xC0,0x75,0x18} } };
/* Apagar obstáculos de los carriles — el atajo «todos los jugadores» (0x9040C0) se anula: `jne +0` */
static const HT_TRAMO T_CARRILES[] = { { 0x00503F82, 2, {0x75,0x11}, {0x75,0x00} } };
/* Resultados rápido — el reloj del cartel final (SetTimer 0x96) con 0 ms: `sub eax,eax` */
static const HT_TRAMO T_RESULTADOS[] = { { 0x004ED5FF, 4, {0x1B,0xC0,0x23,0xC7}, {0x1B,0xC0,0x2B,0xC0} } };
/* Locura (modo héroe 0x18C) — forzar: `jne` -> `jmp` al «sí» · Supr: el «sí» devuelve 0 */
static const HT_TRAMO T_LOCURA[]  = { { 0x00571BB8, 4, {0x84,0xC0,0x75,0x11}, {0x84,0xC0,0xEB,0x11} } };
static const HT_TRAMO T_LOCURA_S[] = { { 0x00571BCD, 5, {0xB8,0x01,0x00,0x00,0x00}, {0xB8,0x00,0x00,0x00,0x00} } };
/* Niebla (modo héroe 0x18B) — igual que la Locura, en su función gemela */
static const HT_TRAMO T_NIEBLA[]  = { { 0x00571B58, 4, {0x84,0xC0,0x75,0x11}, {0x84,0xC0,0xEB,0x11} } };
static const HT_TRAMO T_NIEBLA_S[] = { { 0x00571B6D, 5, {0xB8,0x01,0x00,0x00,0x00}, {0xB8,0x00,0x00,0x00,0x00} } };
/* Sin Piedra (modo héroe 0x278) — forzar: el `je` «no lo tiene» salta +0 y el `jne` del
 * otro sitio pasa a `jmp` · Supr: `test al,al` -> `cmp al,al` (siempre «no lo tiene») y el
 * `jne` salta +0 */
static const HT_TRAMO T_PIEDRA[] = {
    { 0x0054F318, 8, {0x84,0xC0,0x0F,0x84,0xD3,0x00,0x00,0x00}, {0x84,0xC0,0x0F,0x84,0x00,0x00,0x00,0x00} },
    { 0x00550B2F, 4, {0x84,0xC0,0x75,0x4D}, {0x84,0xC0,0xEB,0x4D} } };
static const HT_TRAMO T_PIEDRA_S[] = {
    { 0x0054F318, 8, {0x84,0xC0,0x0F,0x84,0xD3,0x00,0x00,0x00}, {0x38,0xC0,0x0F,0x84,0xD3,0x00,0x00,0x00} },
    { 0x00550B2F, 4, {0x84,0xC0,0x75,0x4D}, {0x84,0xC0,0x75,0x00} } };
/* Ocultar nombres — 0x500C40: «si el asiento NO es el mío, dibujar su apodo»: nunca */
static const HT_TRAMO T_NOMBRES[] = { { 0x00500C40, 5, {0x3A,0x56,0x49,0x74,0x26}, {0x3A,0x56,0x49,0xEB,0x26} } };
/* Efecto velocidad — 0x4E9F61 (las líneas): volver al entrar · 0x4FBE1C (el modo de
 * dibujo con el impulsor, [+0x860]): saltearlo siempre */
static const HT_TRAMO T_VELOCIDAD[] = {
    { 0x004E9F61, 3, {0x53,0xBB,0x01}, {0xC3,0xBB,0x01} },
    { 0x004FBE1B, 3, {0x57,0x74,0x16}, {0x57,0xEB,0x16} } };
/* Opacidad de los obstáculos — los cuatro `0xFF` del alfa (crear, fundido y sus topes).
 * ⚠ el fundido sube de a 0x11 y compara con `==`: el tope TIENE que ser múltiplo de 17,
 *   si no, nunca lo alcanza y da la vuelta. Por eso los 15 escalones. */
static const DWORD T_ALFA[4] = { 0x004FFF05, 0x00507EFD, 0x00507F11, 0x00507FEC };
static const BYTE  T_ALFA_PREF[4][3] = { {0xC6,0x42,0x0A}, {0xC6,0x41,0x0A}, {0x80,0x7A,0x0A}, {0x80,0x78,0x0A} };

enum {
    O_ESTR_OBST, O_OBST_ESTR,
    O_LOCURA, O_LOCURA_S, O_PIEDRA, O_PIEDRA_S, O_NIEBLA, O_NIEBLA_S, O_ESPEJO, O_ESPEJO_S, O_ALEATORIO, O_ALEATORIO_S,
    O_OPACIDAD, O_FAR, O_CAMARA,
    O_VELOCIDAD, O_BOOSTER, O_GHOST, O_CARRILES, O_NOMBRES, O_RESULTADOS,
    O_AUTOCTRL, O_TECLADO, O_ANCLAR, O_HOTKEYS,
    O_N
};

typedef struct {
    const char    *clave;      /* en [herramienta] */
    const wchar_t *texto;
    int            pareja;     /* la que se excluye con ésta (-1 ninguna) */
    const HT_TRAMO *t; int nt; /* los tramos (NULL = especial) */
    int            permitida;
    int            con_tecla;  /* lleva atajo */
    const wchar_t *ayuda;      /* lo que dice el globito al pasar el mouse */
    volatile int   quiere;
    int            puesta;
    int            rota;       /* la guarda falló: en gris */
    int            tecla;      /* VK del atajo (0 = ninguno) */
} HT_OP;

#define NT(x) x, (int)(sizeof(x) / sizeof(x[0]))
static HT_OP g_op[O_N] = {
    { "estrella_obst",    L"Star -> Obst",          -1, NULL, 0,             1, 1,
      L"Las estrellas se ven como obstáculos (con pareja también). Vale desde la próxima carrera." },
    { "obst_estrella",    L"Obst -> Star",          -1, NULL, 0,             1, 1,
      L"Los obstáculos se ven como estrellas, o corazones si hay pareja. Vale desde la próxima carrera." },
    { "locura",           L"Locura",       O_LOCURA_S, NT(T_LOCURA),         1, 1,
      L"El Modo Locura, sin el cupón." },
    { "locura_supr",      L"Supr",         O_LOCURA,   NT(T_LOCURA_S),       HT_PERMITIR_SUPR, 1,
      L"Saca el Modo Locura aunque lo tengas puesto." },
    { "piedra",           L"Sin Piedra",   O_PIEDRA_S, NT(T_PIEDRA),         1, 1,
      L"El Modo Sin Piedras, sin el cupón." },
    { "piedra_supr",      L"Supr",         O_PIEDRA,   NT(T_PIEDRA_S),       HT_PERMITIR_SUPR, 1,
      L"Saca el Sin Piedras aunque lo tengas puesto." },
    { "niebla",           L"Niebla",       O_NIEBLA_S, NT(T_NIEBLA),         1, 1,
      L"El Modo Niebla, sin el cupón." },
    { "niebla_supr",      L"Supr",         O_NIEBLA,   NT(T_NIEBLA_S),       HT_PERMITIR_SUPR, 1,
      L"Saca el Modo Niebla aunque lo tengas puesto." },
    { "espejo",           L"Espejo",       O_ESPEJO_S, NULL, 0,              1, 1,
      L"El Modo Espejo, sin el cupón. Vale desde la próxima carrera." },
    { "espejo_supr",      L"Supr",         O_ESPEJO,   NULL, 0,              HT_PERMITIR_SUPR, 1,
      L"Saca el Modo Espejo aunque lo tengas puesto. Vale desde la próxima carrera." },
    /* ★ 29-oct: el quinto modo héroe, el del 2019 — lo hace heroe_aleatorio.c (ha_tool) */
    { "aleatorio",        L"Aleatorio",    O_ALEATORIO_S, NULL, 0,           1, 1,
      L"El Modo Aleatorio, sin el cupón: flechas y estrellas al azar. Vale desde la próxima carrera." },
    { "aleatorio_supr",   L"Supr",         O_ALEATORIO, NULL, 0,             HT_PERMITIR_SUPR, 1,
      L"Saca el Modo Aleatorio aunque lo tengas puesto. Vale desde la próxima carrera." },
    { "opacidad",         L"Opacidad obstáculos", -1, NULL, 0,               HT_PERMITIR_OPACIDAD, 0,
      L"Obstáculos transparentes. El nivel, con la barra de abajo." },
    { "far",              L"Far Vision",            -1, NULL, 0,             HT_PERMITIR_FAR, 0,
      L"Ver más lejos. La escala (x0.50 a x3.00), con la barra de abajo." },
    { "camara_fija",      L"Cámara Fija",           -1, NT(T_CAMARA),        1, 1,
      L"La cámara no acompaña los movimientos." },
    { "efecto_velocidad", L"Efecto Velocidad",      -1, NT(T_VELOCIDAD),     1, 0,
      L"Marcado = sin las líneas de velocidad." },
    { "efecto_booster",   L"Efecto booster",        -1, NT(T_BOOSTER),       1, 0,
      L"Marcado = sin el efecto del impulsor." },
    { "efecto_ghost",     L"Efecto Ghost",          -1, NT(T_GHOST),         1, 0,
      L"Marcado = sin el «fantasma» del combo." },
    { "carriles",         L"Apagar Obs. Carriles",  -1, NT(T_CARRILES),      1, 0,
      L"Sólo tu carril tiene obstáculos." },
    { "ocultar_nombres",  L"Ocultar Nombres",       -1, NT(T_NOMBRES),       1, 1,
      L"Sin los apodos de los demás en la pista." },
    { "resultados",       L"Resultados Rápido",     -1, NT(T_RESULTADOS),    HT_PERMITIR_RESULTADOS, 0,
      L"El cartel de resultados se va solo, al toque." },
    { "autoctrl",         L"AutoCtrl",              -1, NT(T_AUTOCTRL),      HT_PERMITIR_AUTOCTRL, 1,
      L"El impulsor (Ctrl) se manda solo." },
    { "teclado",          L"Configuración de Teclado", -1, NULL, 0,          1, 0,
      L"Prendida: en la carrera juegan las DOS filas de teclas a la vez. Apagada: sólo las de fábrica." },
    { "anclar",           L"ANCLAR",                -1, NULL, 0,             1, 0,
      L"La ventana queda encima aunque cambies de programa." },
    { "hotkeys",          L"ATAJOS",                -1, NULL, 0,             1, 0,
      L"Prende las teclas de atajo de cada opción (las que muestran los botoncitos)." },
};

/* los niveles de los dos deslizadores */
static int g_ht_alfa_nivel = 15;            /* 1..15 -> alfa = 17 x nivel (15 = 0xFF, el de fábrica) */
static int g_ht_alfa_puesto = 0xFF;         /* lo que quedó escrito en los cuatro sitios          */
static int g_ht_far_pct = 100;              /* % de lo que el juego trae (50..300)                 */
static float g_ht_far_orig[2]; static int g_ht_far_capturado = 0;
static float g_ht_far_escrito[2];
/* los atajos de los deslizadores (Bajar / Subir) */
static int g_ht_tk_far_menos = 0, g_ht_tk_far_mas = 0, g_ht_tk_alfa_menos = 0, g_ht_tk_alfa_mas = 0;
static int g_ht_tecla_ver = VK_F12;

/* ═══ 3 · EL GANCHO DE LAS NOTAS — Star -> Obst y Obst -> Star ════════════════
 *
 *   ★ El diagnóstico (R2BEAT_TOOL.md §2): el juego NO tiene un tipo «corazón». Arma la
 *     tabla de modelos con las 6 estrellas (0x1A izq, 0x1E, 0x1C, 0x1B der, 0x1F, 0x1D)
 *     y atrás las 6 de corazón CON LOS MISMOS TIPOS (0x4E9410..0x4E9594). Después, en
 *     0x5010E0, si el dueño del carril tiene anillo (nodo+0x50) y su pareja está en la
 *     sala (nodo+0xC4 < 6), le SUMA 6 al modelo de la estrella (0x501147).
 *   ⛔ ToolBit se mete al principio de esa función, pinta el modelo del obstáculo y deja
 *     seguir: la nota sigue siendo «estrella», el juego le suma 6 al modelo del obstáculo
 *     y queda otro bloque cualquiera de la pista. Y al revés, el obstáculo pintado de
 *     estrella nunca pasa por el +6: sale estrella común entre corazones.
 *   ★ Lo nuestro:
 *     · Obst -> Star: la nota se disfraza de estrella SÓLO mientras corre la función
 *       original, que decide estrella o corazón como con cualquier otra; después vuelve
 *       a ser obstáculo (el juicio no se entera: sólo cambia cómo se VE).
 *     · Star -> Obst: corre la original PRIMERO (corazón o no) y recién después se pinta
 *       el obstáculo, con el mismo `modelo_de` que usa el juego (0x507A79).
 *     · Sólo las estrellas COMUNES ([nota+0xE] == 0): las especiales (relevo, monedas,
 *       la de la suerte) tienen su propio dibujo y no se tocan.
 *   ★ Y deja medido en el log, por carrera, cuántas estrellas fueron corazón: es la
 *     prueba con su control (sin pareja: 0 corazones).
 */
static DWORD g_ht_ult_nota = 0;
static int g_ht_era_carrera = 0;

/* ¿la escena de esta vuelta es la carrera? (lo mismo que mira fluidez.c: app+0xAFFC == cGame) */
#define HT_APP 0x009311F4
static int ht_en_carrera(void)
{
    BYTE **pa = (BYTE **)HT_VA(HT_APP), **pg = (BYTE **)HT_VA(HT_PARTIDA);
    if (!ht_memoria_ok(pa, 4, 0) || !ht_memoria_ok(pg, 4, 0)) return 0;
    BYTE *app = *pa, *game = *pg;
    if (!app || !game || !ht_memoria_ok(app + 0xAFFC, 4, 0)) return 0;
    return *(BYTE **)(app + 0xAFFC) == game;
}
static int g_ht_c_estr, g_ht_c_cor, g_ht_c_aobst, g_ht_c_aestr, g_ht_c_dichas;

static int ht_modelo_de(int tipo)
{
    void *tabla = g_ht_tabla_mod ? *g_ht_tabla_mod : NULL;
    if (!tabla || !g_ht_f_modelo) return 0;
    return (int)(g_ht_f_modelo(tabla, tipo) & 0xFF);
}

static void ht_teclado_informe(void);
static void ht_cerrar_carrera(void)
{
    ht_teclado_informe();
    if (g_ht_c_estr || g_ht_c_aobst || g_ht_c_aestr)
        apuntar("  [tool] carrera: %d estrellas comunes (%d de CORAZÓN) · Star->Obst %d · Obst->Star %d",
                g_ht_c_estr, g_ht_c_cor, g_ht_c_aobst, g_ht_c_aestr);
    g_ht_c_estr = g_ht_c_cor = g_ht_c_aobst = g_ht_c_aestr = g_ht_c_dichas = 0;
}

static void HT_TC ht_mi_nota(void *jugador, BYTE *nota)
{
    g_ht_hilo_juego = GetCurrentThreadId();
    DWORD ahora = GetTickCount();
    /* el informe sale al SALIR de la carrera (ht_tick); esto es la red: si pasó más de un
     * minuto sin notas, seguro es otra carrera */
    if (g_ht_ult_nota && ahora - g_ht_ult_nota > 60000) ht_cerrar_carrera();
    g_ht_ult_nota = ahora;
    if (!nota) { g_ht_nota_real(jugador, nota); return; }

    BYTE tipo = nota[9];
    int comun = nota[0xE] == 0;
    int a_estr = g_op[O_OBST_ESTR].quiere && g_op[O_OBST_ESTR].puesta;
    int a_obst = g_op[O_ESTR_OBST].quiere && g_op[O_ESTR_OBST].puesta;

    if (a_estr && comun && (tipo == HT_OBST_IZQ || tipo == HT_OBST_DER)) {
        BYTE estr = tipo == HT_OBST_IZQ ? HT_ESTR_IZQ : HT_ESTR_DER;
        int m = ht_modelo_de(estr);
        if (m) {
            BYTE antes = nota[8];
            nota[9] = estr;
            nota[8] = (BYTE)m;
            g_ht_nota_real(jugador, nota);            /* ★ el juego decide: estrella o corazón */
            nota[9] = tipo;                           /* ⚠ y sigue siendo obstáculo */
            g_ht_c_aestr++;
            if (g_ht_c_dichas < 3) {
                g_ht_c_dichas++;
                apuntar("  [tool] Obst->Star: tipo %02X modelo %d -> %d%s", tipo, antes, nota[8],
                        nota[8] == m + 6 ? " (CORAZÓN)" : "");
            }
            return;
        }
    }

    g_ht_nota_real(jugador, nota);

    if (comun && (tipo == HT_ESTR_IZQ || tipo == HT_ESTR_DER)) {
        int m = ht_modelo_de(tipo);
        g_ht_c_estr++;
        if (m && nota[8] == m + 6) g_ht_c_cor++;
        if (a_obst) {
            int mo = ht_modelo_de(tipo == HT_ESTR_IZQ ? HT_OBST_IZQ : HT_OBST_DER);
            if (mo) {
                BYTE antes = nota[8];
                nota[8] = (BYTE)mo;
                g_ht_c_aobst++;
                if (g_ht_c_dichas < 3) {
                    g_ht_c_dichas++;
                    apuntar("  [tool] Star->Obst: tipo %02X modelo %d%s -> %d", tipo, antes,
                            antes == m + 6 ? " (CORAZÓN)" : "", mo);
                }
            }
        }
    }
}

/* ═══ 4 · ESPEJO — la llamada que lo decide al largar ═══════════════════════════
 *   0x56D9C6: `sala->tiene_efecto(asiento, 0x18A)`; si dice que sí, el jugador pasa a
 *   modo 2 (0x4FE020) y sus notas salen espejadas. Se cambia el DESTINO de esa sola
 *   llamada (4 bytes del `call`): para MI asiento, «Espejo» contesta que sí y «Supr»
 *   que no. Los demás asientos, lo que diga el juego. Vale desde la carrera siguiente. */
static int HT_TC ht_mi_efecto(void *sala, int asiento, int efecto)
{
    int r = g_ht_efecto_real(sala, asiento, efecto);
    if ((efecto & 0xFFFF) == HT_EFECTO_ESPEJO && sala) {
        BYTE mio = *((BYTE *)sala + 0x40);
        if ((BYTE)asiento == mio) {
            if (g_op[O_ESPEJO].puesta) r = (r & ~0xFF) | 1;     /* `puesta` ya mira permitida/rota/apagada */
            if (g_op[O_ESPEJO_S].puesta) r = r & ~0xFF;
        }
    }
    return r;
}

/* ═══ 4b · EL TECLADO — «Configuración de Teclado»: dos juegos de teclas a la vez ═══
 *
 *   ★ MEDIDO en R2Beat_local.exe (igual en el de prod) — R2BEAT_TOOL.md §1.4:
 *     · Cada vuelta del bucle (0x4985E8 -> 0x68D080 -> 0x66F350) el juego lee el teclado en
 *       0x66F220 (la llama UNA sola vez, desde 0x66F359): Acquire, copia los 256 bytes de
 *       AHORA (objeto+8) a los de ANTES (objeto+0x108), y GetDeviceState(256, objeto+8)
 *       — `IDirectInputDevice8::GetDeviceState` es vtbl+0x24. El objeto = [[0x93156C]].
 *     · La carrera (0x4EB110, que llama 0x4F7740) no pregunta por TECLAS sino por COMANDOS:
 *       0x11..0x14 = arriba / abajo / izquierda / derecha, y 4 = el impulsor. Tres switch los
 *       traducen: 0x494E10 «recién apretada» (-> 0x4948D0), 0x4950D0 «soltada» (-> 0x494900)
 *       y 0x495390 «mantenida» (lee el byte directo).
 *         direcciones = FLECHAS si [0x931318] == 0, W S A D si no ([ETC] KEYBOARD del Config.ini)
 *         impulsor    = LCtrl o RCtrl (recién apretada) · sólo LCtrl (mantenida)
 *   ★ Lo nuestro: se cambia el destino de esa única llamada. Después de que el juego lee el
 *     teclado — en la carrera, con la opción prendida y sin el chat abierto — la tecla que el
 *     juego mira para cada comando pasa a valer «alguna de las dos asignadas está apretada».
 *     Como el juego copia ESE buffer a «antes» en la vuelta siguiente, recién / soltada /
 *     mantenida salen solas, y no se le manda NADA a Windows (ni pulsaciones falsas).
 *   ⚠ Sólo en la carrera: en el lobby las flechas mueven menús y las letras se escriben.
 *   ⚠ Es una reasignación de verdad: con la opción prendida, una tecla de fábrica que no está
 *     en ninguna de las dos filas deja de contar para ese comando. */
#define HT_LLAMADA_TECLADO 0x0066F359  /* call 0x66F220: la ÚNICA llamada a la lectura del teclado */
#define HT_F_TECLADO       0x0066F220  /* teclado->leer(): copia ahora->antes y GetDeviceState    */
#define HT_KB_MODO         0x00931318  /* [ETC] KEYBOARD del Config.ini: 0 = flechas, 1 = WASD     */

typedef int (HT_TC *HT_FTECLADO)(void *teclado);
static HT_FTECLADO g_ht_teclado_real = NULL;
static int g_ht_gancho_teclado = 0;

/* las dos filas (DIK = el código de DirectInput: el de la tecla física, no el de la letra) */
static const char    *HT_KB_CLAVE[5]  = { "arriba", "izquierda", "abajo", "derecha", "ctrl" };
static const wchar_t *HT_KB_NOMBRE[5] = { L"Arriba", L"Izquierda", L"Abajo", L"Derecha", L"Booster" };
static const BYTE HT_KB_FABRICA[2][5] = { { 0x11, 0x1E, 0x1F, 0x20, 0x1D },     /* W A S D LCtrl   */
                                          { 0xC8, 0xCB, 0xD0, 0xCD, 0x9D } };   /* ↑ ← ↓ → RCtrl   */
static const BYTE HT_KB_FLECHAS[4] = { 0xC8, 0xCB, 0xD0, 0xCD };   /* lo que lee la carrera con KEYBOARD=0 */
static const BYTE HT_KB_WASD[4]    = { 0x11, 0x1E, 0x1F, 0x20 };   /* ...y con KEYBOARD=1                  */
static int  g_ht_kb[2][5] = { { 0x11, 0x1E, 0x1F, 0x20, 0x1D }, { 0xC8, 0xCB, 0xD0, 0xCD, 0x9D } };
static BYTE g_ht_kb_antes[2][5];
static volatile LONG g_ht_kb_toques[2];
static volatile LONG g_ht_kb_dicho = 0;

static int ht_escribiendo(void)
{
    /* la calculadora ya sabe si el chat está abierto (engancha el campo de texto) */
    return g_calc_base && g_calc_frec.QuadPart ? calc_escribiendo() : 0;
}
static int ht_kb_modo_wasd(void) { return *(volatile int *)HT_VA(HT_KB_MODO) != 0; }
/* punteros, para que el banco los pueda simular sin el juego */
static int (*g_ht_kb_es_carrera)(void) = ht_en_carrera;
static int (*g_ht_kb_wasd)(void) = ht_kb_modo_wasd;

/* el corazón: `est` = los 256 bytes de AHORA, recién leídos. Se toma una foto ANTES de
 * escribir, así una fila que use la tecla de otro comando no se pisa a sí misma. */
static void ht_teclado_mezclar(BYTE *est, int wasd)
{
    BYTE crudo[256];
    CopyMemory(crudo, est, 256);
    const BYTE *dst = wasd ? HT_KB_WASD : HT_KB_FLECHAS;
    for (int k = 0; k < 5; k++) {
        BYTE v = 0;
        for (int g = 0; g < 2; g++) {
            int d = g_ht_kb[g][k];
            BYTE b = (d > 0 && d < 256) ? (BYTE)(crudo[d] & 0x80) : 0;
            if (b && !g_ht_kb_antes[g][k]) InterlockedIncrement(&g_ht_kb_toques[g]);
            g_ht_kb_antes[g][k] = b;
            v |= b;
        }
        if (k < 4) est[dst[k]] = v;
        else { est[0x1D] = v; est[0x9D] = v; }   /* el impulsor: «recién» mira las dos, «mantenida» sólo LCtrl */
    }
}

static int HT_TC ht_mi_teclado(void *teclado)
{
    int r = g_ht_teclado_real(teclado);
    if (r && teclado && g_op[O_TECLADO].puesta && g_ht_kb_es_carrera() && !ht_escribiendo()) {
        int wasd = g_ht_kb_wasd();
        if (!InterlockedExchange(&g_ht_kb_dicho, 1))
            apuntar("  [tool] teclado: carrera con las DOS filas (el juego lee %s: [ETC] KEYBOARD=%d)",
                    wasd ? "W A S D" : "las FLECHAS", wasd);
        ht_teclado_mezclar((BYTE *)teclado + 8, wasd);
    }
    return r;
}

/* al terminar la carrera: cuántos toques entraron por cada fila (la medición de la prueba) */
static void ht_teclado_informe(void)
{
    if (!InterlockedExchange(&g_ht_kb_dicho, 0)) return;
    apuntar("  [tool] teclado: %d toque(s) con la fila 1 · %d con la fila 2",
            (int)InterlockedExchange(&g_ht_kb_toques[0], 0), (int)InterlockedExchange(&g_ht_kb_toques[1], 0));
}

/* ── los ganchos, puestos una vez (en DllMain si se puede: es lo más limpio) ── */
static int ht_iguales(DWORD va, const BYTE *esp, int n)
{
    const BYTE *s = HT_VA(va);
    if (!ht_memoria_ok(s, n, 0)) return 0;
    for (int i = 0; i < n; i++) if (s[i] != esp[i]) return 0;
    return 1;
}

static void ht_poner_ganchos(void)
{
    /* el de las notas: en el BORDE de 0x5010E0 (`push ebp / mov ebp,[esp+8]`), con trampolín */
    if (!g_ht_gancho_notas) {
        static const BYTE esp[5] = { 0x55, 0x8B, 0x6C, 0x24, 0x08 };
        BYTE *s = HT_VA(HT_F_NOTA);
        BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (t) {
            CopyMemory(t, esp, 5);
            t[5] = 0xE9;
            *(DWORD *)(t + 6) = (DWORD)((s + 5) - (t + 10));
            g_ht_nota_real = (HT_FNOTA)t;       /* ⚠ ANTES del salto: el gancho puede correr ya */
            BYTE nue[5];
            nue[0] = 0xE9;
            *(DWORD *)(nue + 1) = (DWORD)((BYTE *)ht_mi_nota - (s + 5));
            if (ht_escribir(HT_F_NOTA, esp, nue, 5, "el gancho de las notas (Star/Obst)") > 0) g_ht_gancho_notas = 1;
            else VirtualFree(t, 0, MEM_RELEASE);
        }
        if (!g_ht_gancho_notas) g_op[O_ESTR_OBST].rota = g_op[O_OBST_ESTR].rota = 1;
    }
    /* el del espejo: el destino de UNA llamada (E8 + rel32) */
    if (!g_ht_gancho_espejo) {
        BYTE *s = HT_VA(HT_LLAMADA_ESPEJO);
        BYTE esp[5], nue[5];
        esp[0] = 0xE8;
        *(DWORD *)(esp + 1) = (DWORD)(HT_VA(HT_F_EFECTO) - (s + 5));
        nue[0] = 0xE8;
        *(DWORD *)(nue + 1) = (DWORD)((BYTE *)ht_mi_efecto - (s + 5));
        g_ht_efecto_real = (HT_FEFECTO)HT_VA(HT_F_EFECTO);
        if (ht_escribir(HT_LLAMADA_ESPEJO, esp, nue, 5, "la llamada del espejo") > 0) g_ht_gancho_espejo = 1;
        else g_op[O_ESPEJO].rota = g_op[O_ESPEJO_S].rota = 1;
    }
    /* el del teclado: el destino de la ÚNICA llamada a 0x66F220. Antes, la guarda mira que lo
     * medido siga siendo cierto: la copia ahora->antes (+8 -> +0x108, 0x40 dwords), el lector
     * de «recién apretada» (+8 / +0x108) y la lectura del modo [0x931318]. */
    if (!g_ht_gancho_teclado) {
        static const BYTE copia[18] = { 0x8D, 0x43, 0x08, 0x8B, 0xF0, 0x8D, 0xBB, 0x08, 0x01, 0x00, 0x00,
                                        0xB9, 0x40, 0x00, 0x00, 0x00, 0xF3, 0xA5 };            /* 0x66F255 */
        static const BYTE lee[6]    = { 0x8B, 0x42, 0x24, 0x68, 0x00, 0x01 };                 /* 0x66F26C */
        static const BYTE recien[22] = { 0x0F, 0xB7, 0x44, 0x24, 0x04, 0x8B, 0x09, 0x03, 0xC1, 0xB1, 0x80,
                                         0x84, 0x88, 0x08, 0x01, 0x00, 0x00, 0x75, 0x0D, 0x84, 0x48, 0x08 }; /* 0x4948D0 */
        static const BYTE modo[7]   = { 0x83, 0x3D, 0x18, 0x13, 0x93, 0x00, 0x00 };           /* 0x494FA9 */
        if (!ht_iguales(0x0066F255, copia, 18) || !ht_iguales(0x0066F26C, lee, 6)
            || !ht_iguales(0x004948D0, recien, 22) || !ht_iguales(0x00494FA9, modo, 7)) {
            apuntar("  [tool] ⛔ teclado: la lectura del teclado no es la medida (0x66F220 / 0x4948D0 / 0x494FA9). NO SE TOCA.");
        } else {
            BYTE *s = HT_VA(HT_LLAMADA_TECLADO);
            BYTE esp[5], nue[5];
            esp[0] = 0xE8;
            *(DWORD *)(esp + 1) = (DWORD)(HT_VA(HT_F_TECLADO) - (s + 5));
            nue[0] = 0xE8;
            *(DWORD *)(nue + 1) = (DWORD)((BYTE *)ht_mi_teclado - (s + 5));
            g_ht_teclado_real = (HT_FTECLADO)HT_VA(HT_F_TECLADO);
            if (ht_escribir(HT_LLAMADA_TECLADO, esp, nue, 5, "la llamada del teclado") > 0) g_ht_gancho_teclado = 1;
        }
        if (!g_ht_gancho_teclado) g_op[O_TECLADO].rota = 1;
    }
}

/* ═══ 5 · APLICAR una opción (desde cualquier hilo) ═══════════════════════════ */
static void ht_far_aplicar(void);
static void ht_alfa_aplicar(void);
static void ht_nombre_dik(int dik, wchar_t *s);

static void ht_teclado_log(int prendida)
{
    char filas[2][96];
    for (int g = 0; g < 2; g++) {
        wchar_t w[96]; w[0] = 0;
        for (int k = 0; k < 5; k++) {
            wchar_t n[32];
            ht_nombre_dik(g_ht_kb[g][k], n);
            if (k) lstrcatW(w, L" ");
            lstrcatW(w, n);
        }
        if (!WideCharToMultiByte(CP_UTF8, 0, w, -1, filas[g], sizeof(filas[g]), NULL, NULL)) filas[g][0] = 0;
    }
    apuntar("  [tool] teclado %s · fila 1: %s · fila 2: %s", prendida ? "PRENDIDA" : "apagada", filas[0], filas[1]);
}

static void ht_aplicar(int i)
{
    HT_OP *o = &g_op[i];
    int quiere = o->quiere && o->permitida && !o->rota && !g_ht_apagada;
    if (i == O_FAR) { ht_far_aplicar(); return; }
    if (i == O_OPACIDAD) { ht_alfa_aplicar(); return; }
    if (!o->t) {                                     /* las que viven en un gancho o en la ventana */
        if (quiere != o->puesta && i != O_ANCLAR && i != O_HOTKEYS) {
            if (i == O_TECLADO) ht_teclado_log(quiere);
            else apuntar("  [tool] %s %s", o->clave, quiere ? "PRENDIDA" : "apagada");
        }
        o->puesta = quiere;
        return;
    }
    if (quiere == o->puesta) return;
    char que[64];
    wsprintfA(que, "%s=%d", o->clave, quiere);
    int ok = 1, hechos = 0;
    for (int k = 0; k < o->nt; k++) {
        const HT_TRAMO *t = &o->t[k];
        ok = quiere ? ht_escribir(t->va, t->antes, t->ahora, t->n, que)
                    : ht_escribir(t->va, t->ahora, t->antes, t->n, que);
        if (ok <= 0) break;
        hechos++;
    }
    if (ok <= 0) {
        /* deshacer lo que alcanzó a ponerse: o todos los tramos o ninguno */
        for (int k = hechos - 1; k >= 0; k--) {
            const HT_TRAMO *t = &o->t[k];
            if (quiere) ht_escribir(t->va, t->ahora, t->antes, t->n, que);
            else        ht_escribir(t->va, t->antes, t->ahora, t->n, que);
        }
        if (ok < 0) { o->quiere = o->puesta; return; }   /* pasajero: queda como estaba */
        o->rota = 1;
        apuntar("  [tool] ⛔ «%s» queda NO DISPONIBLE (el exe no es el esperado)", o->clave);
        return;
    }
    o->puesta = quiere;
    apuntar("  [tool] %s %s", o->clave, quiere ? "PRENDIDA" : "apagada");
}

/* la opacidad: los cuatro inmediatos, con su guarda (prefijo + el valor que DEBE haber) */
static void ht_alfa_aplicar(void)
{
    HT_OP *o = &g_op[O_OPACIDAD];
    int quiere = o->quiere && o->permitida && !o->rota && !g_ht_apagada;
    int nivel = g_ht_alfa_nivel < 1 ? 1 : (g_ht_alfa_nivel > 15 ? 15 : g_ht_alfa_nivel);
    int alfa = quiere ? 17 * nivel : 0xFF;
    /* la guarda de los cuatro, aunque no haya nada que cambiar (nivel 15 = el de fábrica):
     * si el exe no es el esperado, la opción tiene que quedar en gris igual */
    for (int k = 0; k < 4; k++) {
        BYTE *s = HT_VA(T_ALFA[k]);
        if (!ht_memoria_ok(s, 4, 0) || s[0] != T_ALFA_PREF[k][0] || s[1] != T_ALFA_PREF[k][1]
            || s[2] != T_ALFA_PREF[k][2] || s[3] != (BYTE)g_ht_alfa_puesto) {
            if (!o->rota) apuntar("  [tool] ⛔ opacidad: 0x%08X no es lo esperado. NO SE TOCA.", T_ALFA[k]);
            o->rota = 1; o->puesta = 0;
            return;
        }
    }
    if (alfa == g_ht_alfa_puesto) { o->puesta = quiere; return; }
    for (int k = 0; k < 4; k++) {
        BYTE esp[4], nue[4];
        CopyMemory(esp, T_ALFA_PREF[k], 3); esp[3] = (BYTE)g_ht_alfa_puesto;
        CopyMemory(nue, T_ALFA_PREF[k], 3); nue[3] = (BYTE)alfa;
        if (ht_escribir(T_ALFA[k], esp, nue, 4, "opacidad") <= 0) {
            for (int j = k - 1; j >= 0; j--) {          /* volver los que ya se escribieron */
                CopyMemory(esp, T_ALFA_PREF[j], 3); esp[3] = (BYTE)alfa;
                CopyMemory(nue, T_ALFA_PREF[j], 3); nue[3] = (BYTE)g_ht_alfa_puesto;
                ht_escribir(T_ALFA[j], esp, nue, 4, "opacidad (vuelta)");
            }
            o->rota = 1;
            return;
        }
    }
    g_ht_alfa_puesto = alfa;
    o->puesta = quiere;
}

/* Far Vision: los dos float que el juego arma AL INICIAR (después de que carga la dll) */
static void ht_far_aplicar(void)
{
    HT_OP *o = &g_op[O_FAR];
    int quiere = o->quiere && o->permitida && !o->rota && !g_ht_apagada;
    volatile float *a = (volatile float *)HT_VA(HT_FAR_A), *b = (volatile float *)HT_VA(HT_FAR_B);
    if (!ht_memoria_ok((const void *)a, 4, 1) || !ht_memoria_ok((const void *)b, 4, 1)) {
        if (!o->rota) apuntar("  [tool] ⛔ far: 0x%08X / 0x%08X no existen en este exe", HT_FAR_A, HT_FAR_B);
        o->rota = 1; o->puesta = 0;
        return;
    }
    if (!g_ht_far_capturado) {
        if (!quiere) { o->puesta = 0; return; }
        float va = *a, vb = *b;
        if (!(va > 0.0f && va < 1.0e6f && vb > 0.0f && vb < 1.0e6f)) return;  /* todavía no: el timer reintenta */
        g_ht_far_orig[0] = va; g_ht_far_orig[1] = vb;
        g_ht_far_escrito[0] = va; g_ht_far_escrito[1] = vb;
        g_ht_far_capturado = 1;
        apuntar("  [tool] far: el juego trae %d.%03d / %d.%03d", (int)va, (int)(va * 1000) % 1000,
                (int)vb, (int)(vb * 1000) % 1000);
    }
    /* si el juego los rehizo (no son ni los suyos ni los nuestros), mandan los de ahora */
    if (*a != g_ht_far_escrito[0] && *a != g_ht_far_orig[0]) g_ht_far_orig[0] = *a;
    if (*b != g_ht_far_escrito[1] && *b != g_ht_far_orig[1]) g_ht_far_orig[1] = *b;
    float f = quiere ? (float)g_ht_far_pct / 100.0f : 1.0f;
    g_ht_far_escrito[0] = g_ht_far_orig[0] * f;
    g_ht_far_escrito[1] = g_ht_far_orig[1] * f;
    *a = g_ht_far_escrito[0];
    *b = g_ht_far_escrito[1];
    o->puesta = quiere;
}

/* ═══ 6 · EL INI — sección [herramienta], SIN reescribir lo demás ═════════════
 *   ⛔ No con WritePrivateProfileString: el ini trae comentarios UTF-8 (★ ⛔ ñ) y la API
 *     lo relee con la codepage del sistema y lo reescribe entero (lección del launcher,
 *     `_tocar_ini`). Acá se cambian sólo las líneas de nuestras claves. */
typedef struct { char *b; int n, cap; } HT_BUF;

static int ht_buf_reservar(HT_BUF *x, int n)
{
    if (n <= x->cap) return 1;
    int cap = n + 4096;
    char *nb = (char *)HeapAlloc(GetProcessHeap(), 0, cap);
    if (!nb) return 0;
    if (x->b) { CopyMemory(nb, x->b, x->n); HeapFree(GetProcessHeap(), 0, x->b); }
    x->b = nb; x->cap = cap;
    return 1;
}

static int ht_buf_meter(HT_BUF *x, int pos, int borrar, const char *s, int ls)
{
    if (!ht_buf_reservar(x, x->n - borrar + ls)) return 0;
    MoveMemory(x->b + pos + ls, x->b + pos + borrar, x->n - pos - borrar);
    CopyMemory(x->b + pos, s, ls);
    x->n += ls - borrar;
    return 1;
}

static int ht_es_blanco(char c) { return c == ' ' || c == '\t'; }

/* pone `clave=valor` en la sección `sec` («[herramienta]», «[picker]»…) del buffer */
static void ht_buf_poner_sec(HT_BUF *x, const char *sec, const char *clave, const char *valor, const char *eol)
{
    int lc = lstrlenA(clave), ls = lstrlenA(sec);
    int en_sec = 0, sec_fin = -1, hay_sec = 0;
    int p = 0;
    while (p < x->n) {
        int ini = p, fin = p;
        while (fin < x->n && x->b[fin] != '\n') fin++;
        int sig = fin < x->n ? fin + 1 : fin;
        int a = ini, z = fin;
        if (z > a && x->b[z - 1] == '\r') z--;
        while (a < z && ht_es_blanco(x->b[a])) a++;
        if (a < z && x->b[a] == '[') {
            if (en_sec) break;                                     /* terminó la nuestra */
            en_sec = (z - a >= ls && CompareStringA(LOCALE_INVARIANT, NORM_IGNORECASE, x->b + a, ls, sec, ls) == CSTR_EQUAL);
            if (en_sec) { hay_sec = 1; sec_fin = sig; }
        } else if (en_sec && a < z) {
            if (x->b[a] != ';' && x->b[a] != '#') {
                int k = a;
                while (k < z && x->b[k] != '=') k++;
                int kz = k;
                while (kz > a && ht_es_blanco(x->b[kz - 1])) kz--;
                if (k < z && kz - a == lc
                    && CompareStringA(LOCALE_INVARIANT, NORM_IGNORECASE, x->b + a, lc, clave, lc) == CSTR_EQUAL) {
                    ht_buf_meter(x, k + 1, z - (k + 1), valor, lstrlenA(valor));
                    return;
                }
            }
            sec_fin = sig;
        }
        p = sig;
    }
    char linea[160];
    wsprintfA(linea, "%s=%s%s", clave, valor, eol);
    if (hay_sec) {
        /* al final de la sección (después de su última línea con algo) */
        if (sec_fin > 0 && sec_fin <= x->n && x->b[sec_fin - 1] != '\n') {
            ht_buf_meter(x, sec_fin, 0, eol, lstrlenA(eol)); sec_fin += lstrlenA(eol);
        }
        ht_buf_meter(x, sec_fin, 0, linea, lstrlenA(linea));
    } else {
        char cab[64];
        int pos = x->n;
        if (pos > 0 && x->b[pos - 1] != '\n') { ht_buf_meter(x, pos, 0, eol, lstrlenA(eol)); pos = x->n; }
        wsprintfA(cab, "%s%s%s", eol, sec, eol);
        ht_buf_meter(x, pos, 0, cab, lstrlenA(cab));
        ht_buf_meter(x, x->n, 0, linea, lstrlenA(linea));
    }
}

static void ht_buf_poner(HT_BUF *x, const char *clave, const char *valor, const char *eol)
{
    ht_buf_poner_sec(x, "[herramienta]", clave, valor, eol);
}

static int g_ht_tema;                           /* (definida con la tabla de temas, § 7) */
static void ht_guardar(void)
{
    EnterCriticalSection(&g_ht_cs);
    HT_BUF x = { NULL, 0, 0 };
    HANDLE h = CreateFileA(g_ht_ini, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        DWORD tam = GetFileSize(h, NULL), leidos = 0;
        if (tam != INVALID_FILE_SIZE && tam < (1u << 20) && ht_buf_reservar(&x, (int)tam + 1)) {
            if (ReadFile(h, x.b, tam, &leidos, NULL)) x.n = (int)leidos;
        }
        CloseHandle(h);
    }
    if (!ht_buf_reservar(&x, 64)) { LeaveCriticalSection(&g_ht_cs); return; }
    const char *eol = "\r\n";
    for (int i = 0; i + 1 < x.n; i++) if (x.b[i] == '\n') { eol = (i > 0 && x.b[i - 1] == '\r') ? "\r\n" : "\n"; break; }
    char v[32], k[48];
    for (int i = 0; i < O_N; i++) {
        ht_buf_poner(&x, g_op[i].clave, g_op[i].quiere ? "1" : "0", eol);
        if (g_op[i].con_tecla) {
            wsprintfA(k, "tk_%s", g_op[i].clave); wsprintfA(v, "%d", g_op[i].tecla);
            ht_buf_poner(&x, k, v, eol);
        }
    }
    wsprintfA(v, "%d", g_ht_alfa_nivel); ht_buf_poner(&x, "opacidad_nivel", v, eol);
    wsprintfA(v, "%d", g_ht_far_pct);    ht_buf_poner(&x, "far_pct", v, eol);
    wsprintfA(v, "%d", g_ht_tk_far_menos);  ht_buf_poner(&x, "tk_far_menos", v, eol);
    wsprintfA(v, "%d", g_ht_tk_far_mas);    ht_buf_poner(&x, "tk_far_mas", v, eol);
    wsprintfA(v, "%d", g_ht_tk_alfa_menos); ht_buf_poner(&x, "tk_opacidad_menos", v, eol);
    wsprintfA(v, "%d", g_ht_tk_alfa_mas);   ht_buf_poner(&x, "tk_opacidad_mas", v, eol);
    wsprintfA(v, "%d", g_ht_tema);          ht_buf_poner(&x, "tema", v, eol);
    /* las dos filas del teclado: el DIK (código de tecla de DirectInput) en decimal; 0 = ninguna */
    for (int g = 0; g < 2; g++)
        for (int kk = 0; kk < 5; kk++) {
            wsprintfA(k, "kb%d_%s", g + 1, HT_KB_CLAVE[kk]); wsprintfA(v, "%d", g_ht_kb[g][kk]);
            ht_buf_poner(&x, k, v, eol);
        }
    if (g_ht_ven) {
        RECT r;
        if (GetWindowRect(g_ht_ven, &r)) {
            wsprintfA(v, "%d", (int)r.left); ht_buf_poner(&x, "x", v, eol);
            wsprintfA(v, "%d", (int)r.top);  ht_buf_poner(&x, "y", v, eol);
        }
    }
    h = CreateFileA(g_ht_ini, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        DWORD esc = 0;
        WriteFile(h, x.b, (DWORD)x.n, &esc, NULL);
        CloseHandle(h);
    }
    HeapFree(GetProcessHeap(), 0, x.b);
    LeaveCriticalSection(&g_ht_cs);
}

static void ht_leer(void)
{
    for (int i = 0; i < O_N; i++) {
        g_op[i].quiere = (int)GetPrivateProfileIntA("herramienta", g_op[i].clave, 0, g_ht_ini) != 0;
        if (g_op[i].con_tecla) {
            char k[48];
            wsprintfA(k, "tk_%s", g_op[i].clave);
            g_op[i].tecla = (int)GetPrivateProfileIntA("herramienta", k, 0, g_ht_ini) & 0xFF;
        }
    }
    g_ht_alfa_nivel = (int)GetPrivateProfileIntA("herramienta", "opacidad_nivel", 15, g_ht_ini);
    if (g_ht_alfa_nivel < 1 || g_ht_alfa_nivel > 15) g_ht_alfa_nivel = 15;
    g_ht_far_pct = (int)GetPrivateProfileIntA("herramienta", "far_pct", 100, g_ht_ini);
    if (g_ht_far_pct < 50 || g_ht_far_pct > 300) g_ht_far_pct = 100;
    g_ht_tk_far_menos  = (int)GetPrivateProfileIntA("herramienta", "tk_far_menos", 0, g_ht_ini) & 0xFF;
    g_ht_tk_far_mas    = (int)GetPrivateProfileIntA("herramienta", "tk_far_mas", 0, g_ht_ini) & 0xFF;
    g_ht_tk_alfa_menos = (int)GetPrivateProfileIntA("herramienta", "tk_opacidad_menos", 0, g_ht_ini) & 0xFF;
    g_ht_tk_alfa_mas   = (int)GetPrivateProfileIntA("herramienta", "tk_opacidad_mas", 0, g_ht_ini) & 0xFF;
    g_ht_tecla_ver = (int)GetPrivateProfileIntA("herramienta", "tecla", VK_F12, g_ht_ini) & 0xFF;
    g_ht_tema = (int)GetPrivateProfileIntA("herramienta", "tema", 1, g_ht_ini);
    if (g_ht_tema < 1 || g_ht_tema > 4) g_ht_tema = 1;
    if (!g_ht_tecla_ver) g_ht_tecla_ver = VK_F12;
    for (int g = 0; g < 2; g++)
        for (int kk = 0; kk < 5; kk++) {
            char k[32];
            wsprintfA(k, "kb%d_%s", g + 1, HT_KB_CLAVE[kk]);
            g_ht_kb[g][kk] = (int)GetPrivateProfileIntA("herramienta", k, HT_KB_FABRICA[g][kk], g_ht_ini) & 0xFF;
        }
    /* las exclusivas: si el ini trae las dos, gana la primera */
    for (int i = 0; i < O_N; i++)
        if (g_op[i].pareja > i && g_op[i].quiere && g_op[g_op[i].pareja].quiere) g_op[g_op[i].pareja].quiere = 0;
    for (int i = 0; i < O_N; i++) if (!g_op[i].permitida) g_op[i].quiere = 0;
    /* ★ 04-oct, anonimo03: la pastilla verde de arriba ya NO es un botón («sólo apaga y prende la luz»):
     *   los atajos van SIEMPRE prendidos y la pastilla queda como aviso, en verde */
    g_op[O_HOTKEYS].quiere = 1;
}

/* ═══ 7 · LA VENTANA (su propio hilo: no depende del bucle del juego) ═════════
 *
 *   ★ 04-oct — «como si fueras diseñador» (anonimo03: «la tool está algo feíta»):
 *     · Toda la ventana se DIBUJA A MANO: nada de los controles grises de Windows. Los
 *       colores son los del launcher web (fondo #140e1e / #1b1229, tarjetas #2a1f40, rosa
 *       #ff7ab8, celeste #8fe7ff, y verde = prendido, como sus botones ENCENDIDO).
 *     · Dos capas: las FORMAS se dibujan al doble de tamaño y se achican (bordes suaves,
 *       GDI solo no los suaviza) y el TEXTO va encima, al tamaño real (nítido).
 *     · Las teclas se asignan APRETÁNDOLAS: clic en el botoncito y la próxima tecla queda.
 *       Clic derecho la BORRA · Esc CANCELA · las que usa el juego o la tool NO se dejan
 *       (y se dice por qué abajo, en rojo).
 *     · Dos columnas, 728 x 512: entra en una pantalla de 1366 x 768 sin tapar todo.
 */
#define WM_HT_MOSTRAR (WM_APP + 1)
#define WM_HT_APAGAR  (WM_APP + 2)

/* ★★ 04-oct (pedido de anonimo03): CUATRO estilos para elegir, cada uno una fila de esta tabla.
 *   Se elige con `[herramienta] tema=1..4` (o con el botón TEMA de la cabecera, que los recorre
 *   y lo guarda). ⚠ Ninguno es el definitivo hasta que anonimo03 elija: después queda uno y el botón
 *   se va. launcher2013.py tiene la MISMA tabla (TEMAS), para que los dos hagan juego. */
typedef struct {
    const wchar_t *nombre;
    COLORREF fondo, cabeza, tarjeta, borde, hueco, hueco_b, muerto, texto, suave, gris, apagado,
             rosa, rosa_f, rosa_osc, celeste, verde, verde_osc, verde_led, verde_tx, rojo, tilde, globo;
    BYTE radio, radio_chip, radio_pill;   /* esquinas: tarjeta, botoncito, pastillas              */
    BYTE grosor;                          /* borde de las tarjetas (0 = sin borde)                */
    BYTE estilo_on;                       /* 0 casilla con tilde · 1 interruptor · 2 bloque       */
    BYTE fila;                            /* alto de una fila: la densidad                        */
    BYTE tira;                            /* la tirita rosa -> celeste de arriba                  */
    BYTE cabecera;                        /* título de tarjeta: 0 barrita · 1 en acento · 2 bloque y línea · 3 chico espaciado */
    BYTE espaciado;                       /* entre letras de los títulos de tarjeta               */
    const wchar_t *letra, *letra_titulo;
    int tam_texto, peso_titulo, tam_titulo;
    const wchar_t *titulo1, *titulo2;
    int tam_chip;                         /* la letra de los botoncitos de tecla               */
} HT_TEMA;

#define C_(r, g, b) RGB(0x##r, 0x##g, 0x##b)
static const HT_TEMA HT_TEMAS[4] = {
    /* 1 · NEÓN — el del launcher web tal cual: violeta, rosa y celeste, tilde verde, tirita arriba */
    { L"Neón",
      C_(1b,12,29), C_(14,0e,1e), C_(2a,1f,40), C_(3b,2d,58), C_(1b,12,29), C_(4a,3d,66), C_(24,1b,36),
      C_(f3,ef,fa), C_(b3,a8,cc), C_(8a,7f,a3), C_(5c,50,75), C_(ff,7a,b8), C_(e8,4a,92), C_(3d,1d,3f),
      C_(8f,e7,ff), C_(2f,bf,63), C_(1f,6b,3a), C_(6d,ff,9c), C_(ea,ff,f0), C_(ff,6b,81), C_(ff,ff,ff), C_(10,0b,19),
      12, 6, 13, 1, 0, 28, 1, 0, 2, L"Segoe UI", L"Segoe UI", 13, FW_BLACK, 22, L"Ñ2H", L"ock", 12 },
    /* 2 · SAKURA — clara: papel lila, tarjetas blancas, lo prendido es ROSA (interruptores), aireada */
    { L"Sakura",
      C_(f6,f0,fa), C_(ff,ff,ff), C_(ff,ff,ff), C_(e6,da,ef), C_(f4,ee,f9), C_(cd,bf,dc), C_(f1,ec,f5),
      C_(2a,1f,40), C_(4f,42,68), C_(8a,7f,a3), C_(c2,b7,d1), C_(e0,47,8a), C_(e0,47,8a), C_(ff,e3,ef),
      C_(1d,86,ad), C_(e0,47,8a), C_(ff,e3,ef), C_(e0,47,8a), C_(a3,24,5f), C_(d6,33,4f), C_(ff,ff,ff), C_(ff,ff,ff),
      14, 8, 13, 1, 1, 30, 0, 1, 1, L"Segoe UI", L"Segoe UI Semibold", 13, FW_SEMIBOLD, 22, L"Ñ2H", L"ock", 12 },
    /* 3 · ARCADE — negro y neón, todo cuadrado, letra de terminal, lo prendido = bloque celeste, densa */
    { L"Arcade",
      C_(07,05,0c), C_(07,05,0c), C_(0c,09,14), C_(1f,5f,6e), C_(07,05,0c), C_(2b,4a,55), C_(0c,09,14),
      C_(e6,fb,ff), C_(9c,c7,d3), C_(5d,7c,88), C_(2e,3b,42), C_(ff,3f,a4), C_(ff,3f,a4), C_(3a,0b,25),
      C_(3f,f0,ff), C_(3f,f0,ff), C_(0e,3b,44), C_(3f,f0,ff), C_(e6,fb,ff), C_(ff,40,60), C_(07,05,0c), C_(07,05,0c),
      0, 0, 0, 1, 2, 26, 0, 2, 1, L"Consolas", L"Consolas", 12, FW_BOLD, 22, L"Ñ2H", L"ock", 10 },
    /* 4 · MEDIANOCHE — azul noche y lavanda, tarjetas sin borde, todo redondo, interruptores verdes */
    { L"Medianoche",
      C_(10,0c,1f), C_(0c,09,18), C_(1b,15,33), C_(1b,15,33), C_(26,20,46), C_(3a,31,66), C_(1f,1a,3a),
      C_(ff,ff,ff), C_(cf,c6,ea), C_(8f,87,b3), C_(4d,46,73), C_(b9,9c,ff), C_(8f,6d,f5), C_(2c,23,57),
      C_(8f,e7,ff), C_(34,c7,73), C_(1d,5c,3d), C_(7d,ff,b0), C_(ea,ff,f0), C_(ff,7a,8a), C_(ff,ff,ff), C_(1b,15,33),
      18, 11, 13, 0, 1, 30, 0, 3, 3, L"Segoe UI", L"Segoe UI Light", 13, FW_LIGHT, 26, L"Ñ2H", L"ock", 12 },
};
#undef C_
static int g_ht_tema = 1;                       /* 1..4: [herramienta] tema */
static const HT_TEMA *g_tm = &HT_TEMAS[0];

#define HT_C_FONDO     (g_tm->fondo)
#define HT_C_CABEZA    (g_tm->cabeza)
#define HT_C_TARJETA   (g_tm->tarjeta)
#define HT_C_BORDE     (g_tm->borde)
#define HT_C_HUECO     (g_tm->hueco)
#define HT_C_HUECO_B   (g_tm->hueco_b)
#define HT_C_MUERTO    (g_tm->muerto)
#define HT_C_TEXTO     (g_tm->texto)
#define HT_C_SUAVE     (g_tm->suave)
#define HT_C_GRIS      (g_tm->gris)
#define HT_C_APAGADO   (g_tm->apagado)
#define HT_C_ROSA      (g_tm->rosa)
#define HT_C_ROSA_F    (g_tm->rosa_f)
#define HT_C_ROSA_OSC  (g_tm->rosa_osc)
#define HT_C_CELESTE   (g_tm->celeste)
#define HT_C_VERDE     (g_tm->verde)
#define HT_C_VERDE_OSC (g_tm->verde_osc)
#define HT_C_VERDE_LED (g_tm->verde_led)
#define HT_C_VERDE_TX  (g_tm->verde_tx)
#define HT_C_ROJO      (g_tm->rojo)
#define HT_C_TILDE     (g_tm->tilde)
#define HT_C_GLOBO     (g_tm->globo)

/* ── 7.1 · las teclas: nombres, DIK <-> VK, y cuáles NO se pueden asignar ────────── */
#define K_ALFM 100                    /* Opacidad · bajar   */
#define K_ALFP 101                    /* Opacidad · subir   */
#define K_FARM 102                    /* Far · bajar        */
#define K_FARP 103                    /* Far · subir        */
#define K_KB(g, k) (200 + (g) * 5 + (k))   /* las dos filas del teclado (guardan DIK, no VK) */

static int ht_es_dik(int id) { return id >= 200 && id < 210; }

static int *ht_tecla_de(int id)
{
    if (id >= 0 && id < O_N) return &g_op[id].tecla;
    if (id == K_ALFM) return &g_ht_tk_alfa_menos;
    if (id == K_ALFP) return &g_ht_tk_alfa_mas;
    if (id == K_FARM) return &g_ht_tk_far_menos;
    if (id == K_FARP) return &g_ht_tk_far_mas;
    if (ht_es_dik(id)) return &g_ht_kb[(id - 200) / 5][(id - 200) % 5];
    return NULL;
}

/* la opción de la que depende cada botoncito (si está rota, el botoncito también) */
static int ht_tecla_opcion(int id)
{
    if (id >= 0 && id < O_N) return id;
    if (id == K_ALFM || id == K_ALFP) return O_OPACIDAD;
    if (id == K_FARM || id == K_FARP) return O_FAR;
    return O_TECLADO;
}
static int ht_tecla_viva(int id) { int i = ht_tecla_opcion(id); return g_op[i].permitida && !g_op[i].rota; }

static void ht_que_es(int id, wchar_t *s)                       /* s: 64 */
{
    if (id >= 0 && id < O_N) {
        if (g_op[id].pareja >= 0 && g_op[id].pareja < id) wsprintfW(s, L"%s · Supr", g_op[g_op[id].pareja].texto);
        else lstrcpyW(s, g_op[id].texto);
    } else if (id == K_ALFM) lstrcpyW(s, L"Opacidad · bajar");
    else if (id == K_ALFP) lstrcpyW(s, L"Opacidad · subir");
    else if (id == K_FARM) lstrcpyW(s, L"Far Vision · bajar");
    else if (id == K_FARP) lstrcpyW(s, L"Far Vision · subir");
    else if (ht_es_dik(id)) wsprintfW(s, L"fila %d · %s", (id - 200) / 5 + 1, HT_KB_NOMBRE[(id - 200) % 5]);
    else s[0] = 0;
}

static void ht_nombre_vk(int vk, wchar_t *s)                    /* s: 32 */
{
    static const struct { BYTE vk; const wchar_t *n; } T[] = {
        { VK_INSERT, L"Insert" }, { VK_DELETE, L"Supr" }, { VK_HOME, L"Inicio" }, { VK_END, L"Fin" },
        { VK_PRIOR, L"RePág" }, { VK_NEXT, L"AvPág" }, { VK_DIVIDE, L"Num /" }, { VK_MULTIPLY, L"Num *" },
        { VK_SUBTRACT, L"Num -" }, { VK_ADD, L"Num +" }, { VK_DECIMAL, L"Num ." }, { VK_PAUSE, L"Pausa" },
        { VK_SCROLL, L"BloqDespl" }, { VK_UP, L"↑" }, { VK_DOWN, L"↓" }, { VK_LEFT, L"←" }, { VK_RIGHT, L"→" },
        { VK_CONTROL, L"Ctrl" }, { VK_LCONTROL, L"LCtrl" }, { VK_RCONTROL, L"RCtrl" },
        { VK_SHIFT, L"Shift" }, { VK_LSHIFT, L"LShift" }, { VK_RSHIFT, L"RShift" },
        { VK_MENU, L"Alt" }, { VK_LMENU, L"LAlt" }, { VK_RMENU, L"AltGr" },
        { VK_LWIN, L"LWin" }, { VK_RWIN, L"RWin" }, { VK_APPS, L"Menú" }, { VK_SPACE, L"Espacio" },
        { VK_RETURN, L"Enter" }, { VK_ESCAPE, L"Esc" }, { VK_TAB, L"Tab" }, { VK_BACK, L"Borrar" },
        { VK_CAPITAL, L"BloqMayús" }, { VK_NUMLOCK, L"BloqNum" }, { VK_SNAPSHOT, L"ImprPant" },
    };
    if (vk <= 0 || vk > 255) { lstrcpyW(s, L"—"); return; }
    if (vk >= VK_F1 && vk <= VK_F24) { wsprintfW(s, L"F%d", vk - VK_F1 + 1); return; }
    if (vk >= VK_NUMPAD0 && vk <= VK_NUMPAD9) { wsprintfW(s, L"Num %d", vk - VK_NUMPAD0); return; }
    if ((vk >= 'A' && vk <= 'Z') || (vk >= '0' && vk <= '9')) { s[0] = (wchar_t)vk; s[1] = 0; return; }
    for (int i = 0; i < (int)(sizeof(T) / sizeof(T[0])); i++)
        if (T[i].vk == vk) { lstrcpyW(s, T[i].n); return; }
    UINT c = MapVirtualKeyW((UINT)vk, 2 /* MAPVK_VK_TO_CHAR */) & 0x7FFF;
    if (c > 32) { s[0] = (wchar_t)c; s[1] = 0; return; }
    wsprintfW(s, L"VK %02X", vk);
}

/* DIK = el código de la tecla FÍSICA que usa DirectInput: el scan code, +0x80 si es «extendida» */
static int ht_dik_a_vk(int dik)
{
    static const BYTE NUM[13] = { VK_NUMPAD7, VK_NUMPAD8, VK_NUMPAD9, VK_SUBTRACT, VK_NUMPAD4, VK_NUMPAD5,
                                  VK_NUMPAD6, VK_ADD, VK_NUMPAD1, VK_NUMPAD2, VK_NUMPAD3, VK_NUMPAD0, VK_DECIMAL };
    if (dik <= 0 || dik > 255) return 0;
    if (dik >= 0x47 && dik <= 0x53) return NUM[dik - 0x47];     /* el numérico (sin E0) */
    if (dik == 0xB5) return VK_DIVIDE;
    if (dik == 0x37) return VK_MULTIPLY;
    if (dik == 0x9C) return VK_RETURN;                          /* el Enter del numérico */
    if (dik == 0xC5) return VK_PAUSE;
    if (dik == 0x45) return VK_NUMLOCK;
    UINT sc = (UINT)(dik & 0x7F) | ((dik & 0x80) ? 0xE000u : 0u);
    return (int)MapVirtualKeyW(sc, 3 /* MAPVK_VSC_TO_VK_EX */);
}

static int ht_vk_a_dik(int vk)
{
    static const BYTE NUM[10] = { 0x52, 0x4F, 0x50, 0x51, 0x4B, 0x4C, 0x4D, 0x47, 0x48, 0x49 };
    if (vk <= 0 || vk > 255) return 0;
    if (vk >= VK_NUMPAD0 && vk <= VK_NUMPAD9) return NUM[vk - VK_NUMPAD0];
    switch (vk) {
    case VK_DECIMAL: return 0x53;   case VK_SUBTRACT: return 0x4A;  case VK_ADD: return 0x4E;
    case VK_MULTIPLY: return 0x37;  case VK_DIVIDE: return 0xB5;    case VK_PAUSE: return 0xC5;
    case VK_NUMLOCK: return 0x45;   case VK_CONTROL: return 0x1D;   case VK_SHIFT: return 0x2A;
    case VK_MENU: return 0x38;
    /* ⚠ MEDIDO en el banco: MapVirtualKey(VK_UP, VK_TO_VSC_EX) devuelve 0x48 SIN el E0, o sea el
     *   8 del numérico. Las «extendidas» van a mano (son las de dinput.h: DIK_UP = 0xC8…). */
    case VK_UP: return 0xC8;        case VK_DOWN: return 0xD0;      case VK_LEFT: return 0xCB;
    case VK_RIGHT: return 0xCD;     case VK_INSERT: return 0xD2;    case VK_DELETE: return 0xD3;
    case VK_HOME: return 0xC7;      case VK_END: return 0xCF;       case VK_PRIOR: return 0xC9;
    case VK_NEXT: return 0xD1;      case VK_RCONTROL: return 0x9D;  case VK_RMENU: return 0xB8;
    case VK_LWIN: return 0xDB;      case VK_RWIN: return 0xDC;      case VK_APPS: return 0xDD;
    case VK_SNAPSHOT: return 0xB7;
    }
    UINT sc = MapVirtualKeyW((UINT)vk, 4 /* MAPVK_VK_TO_VSC_EX */);
    if (!sc) return 0;
    return (int)((sc & 0x7F) | (((sc >> 8) & 0xFF) == 0xE0 ? 0x80 : 0));
}

static void ht_nombre_dik(int dik, wchar_t *s)
{
    if (dik <= 0 || dik > 255) { lstrcpyW(s, L"—"); return; }
    if (dik == 0x9C) { lstrcpyW(s, L"Num Enter"); return; }
    int vk = ht_dik_a_vk(dik);
    if (vk) ht_nombre_vk(vk, s);
    else wsprintfW(s, L"DIK %02X", dik);
}

static void ht_nombre_tecla(int id, int valor, wchar_t *s)
{
    if (ht_es_dik(id)) ht_nombre_dik(valor, s); else ht_nombre_vk(valor, s);
}

/* la calculadora: F9 / F10 y Z X C V B N M — calculadora.c CALC_VK (04-oct: los números quedan libres) */
static int ht_dik_calculadora(int d)
{
    return d == 0x43 || d == 0x44 || (d >= 0x2C && d <= 0x32);
}
/* las que usa el juego por su cuenta (medido: los 21 comandos de 0x494E10): Esc, Enter, Tab,
 * Espacio, LShift (en la carrera), Alt, y F1-F5 (las frases rápidas, 0x4986D3…) */
static int ht_dik_juego(int d)
{
    return d == 0x01 || d == 0x1C || d == 0x9C || d == 0x0F || d == 0x39 || d == 0x2A
        || d == 0x38 || d == 0xB8 || (d >= 0x3B && d <= 0x3F);
}

static int ht_misma_tecla(int id_a, int a, int id_b, int b)
{
    if (!a || !b) return 0;
    int da = ht_es_dik(id_a) ? a : ht_vk_a_dik(a), db = ht_es_dik(id_b) ? b : ht_vk_a_dik(b);
    if (da && db) return da == db;
    int va = ht_es_dik(id_a) ? ht_dik_a_vk(a) : a, vb = ht_es_dik(id_b) ? ht_dik_a_vk(b) : b;
    return va && va == vb;
}

/* ★ 16-oct · TECLAS TOTALMENTE LIBRES (anonimo03: «que permita asignar cualquier tecla en todas las opciones; hoy no deja
 *   algunas porque ya están en uso o reservadas para el gameplay, pero los usuarios igual lo piden»).
 *   Antes esto BLOQUEABA (§1.5 de R2BEAT_TOOL.md): F12, la calculadora, las del juego, las del chat y las repetidas.
 *   Ahora NADA se bloquea: `ht_bloqueada` sólo arma una NOTA para el cartel (en amarillo) si la tecla también la usa
 *   otra cosa, y devuelve 0. La única que no se puede asignar es Esc, porque es la que CANCELA la espera.
 *   Una tecla que ya tenía OTRA pieza de la tool se le SACA a esa (`ht_soltar_repetida`): si no, una misma tecla haría
 *   dos cosas de la tool a la vez sin que se vea en ningún botoncito. */
static int ht_bloqueada(int id, int valor, wchar_t *por)        /* por: 160 · ★ ya no bloquea: 0 siempre */
{
    wchar_t n[32];
    int dik = ht_es_dik(id) ? valor : ht_vk_a_dik(valor);
    int vk = ht_es_dik(id) ? ht_dik_a_vk(valor) : valor;
    por[0] = 0;
    if (!valor) return 0;
    ht_nombre_tecla(id, valor, n);
    if (vk == g_ht_tecla_ver || (dik && dik == ht_vk_a_dik(g_ht_tecla_ver)))
        wsprintfW(por, L"ojo: %s también abre y cierra esta ventana", n);
    else if (ht_dik_calculadora(dik) || vk == VK_F9 || vk == VK_F10)
        wsprintfW(por, L"ojo: %s también es de la calculadora", n);
    else if (ht_dik_juego(dik) || vk == VK_RETURN || vk == VK_TAB || vk == VK_SPACE || vk == VK_SHIFT
             || vk == VK_LSHIFT || vk == VK_MENU || vk == VK_LMENU || vk == VK_RMENU || (vk >= VK_F1 && vk <= VK_F5))
        wsprintfW(por, L"ojo: %s también la usa el juego", n);
    else if (!ht_es_dik(id) && (dik == 0xC8 || dik == 0xCB || dik == 0xD0 || dik == 0xCD || dik == 0x1D || dik == 0x9D
                                || vk == VK_CONTROL || vk == VK_LCONTROL || vk == VK_RCONTROL))
        wsprintfW(por, L"ojo: %s también mueve / es el booster", n);
    return 0;
}

/* la tecla `valor` sale de toda OTRA pieza de la tool que la tuviera; `que` = de cuál salió (vacío si de ninguna) */
static void ht_soltar_repetida(int id, int valor, wchar_t *que)        /* que: 64 */
{
    que[0] = 0;
    for (int g = 0; g < 2; g++)
        for (int k = 0; k < 5; k++)
            if (K_KB(g, k) != id && ht_misma_tecla(id, valor, K_KB(g, k), g_ht_kb[g][k])) {
                ht_que_es(K_KB(g, k), que); g_ht_kb[g][k] = 0;
            }
    for (int i = 0; i < O_N; i++)
        if (g_op[i].con_tecla && i != id && ht_misma_tecla(id, valor, i, g_op[i].tecla)) {
            ht_que_es(i, que); g_op[i].tecla = 0;
        }
    for (int s = K_ALFM; s <= K_FARP; s++)
        if (s != id && ht_misma_tecla(id, valor, s, *ht_tecla_de(s))) {
            ht_que_es(s, que); *ht_tecla_de(s) = 0;
        }
}

/* ── 7.2 · el estado de la ventana ───────────────────────────────────────────── */
enum { E_OPCION, E_TECLA, E_SLIDER, E_VALOR, E_PILL, E_BOTON, E_CERRAR, E_FIJO, E_TITULO, E_AVISO };
/* ★ 04-oct (el editor): cada pieza tiene un ID ESTABLE (§ 7.3b, ht_id_el) y puede estar OCULTA o con
 *   otro texto: eso lo pone el archivo de disposición. La ACCIÓN no cambia nunca: va por tipo y ref. */
typedef struct { BYTE tipo; short x, y, w, h; int ref; const wchar_t *texto, *ayuda; BYTE oculto; } HT_EL;
typedef struct { short x, y, w, h; const wchar_t *titulo, *nota; const char *id; BYTE oculto; } HT_CARTA;
typedef struct { short x, y, w, h; const wchar_t *texto; BYTE fuente; COLORREF color; UINT fmt; const char *id; BYTE oculto; } HT_TX;
enum { F_TEXTO, F_CHICO, F_TITULO, F_CARTA, F_CHIP, F_PILL, F_N };

#define HT_MAX_EL 96
static HT_EL    g_el[HT_MAX_EL];  static int g_nel;
static HT_CARTA g_carta[6];       static int g_ncarta;
static HT_TX    g_tx[20];         static int g_ntx;
static int g_ht_w = 728, g_ht_h = 512;
static int g_ht_hover = -1, g_ht_arrastre = -1;
static int g_ht_esperando = -1;                 /* el botoncito que espera una tecla (-1 ninguno) */
static wchar_t g_ht_aviso[320];                 /* el cartel de abajo (vacío = el estado) */
static COLORREF g_ht_aviso_color;
static DWORD g_ht_aviso_hasta;
static HFONT g_ht_f[F_N];
static HDC g_ht_dc2, g_ht_dc1;                  /* las dos capas: formas al doble, y la final */
static HBITMAP g_ht_bm2, g_ht_bm1;
static HWND g_ht_globo; static int g_ht_globo_el = -1;
static int g_ht_visto_juego = 0;                /* ms con la ventana del juego a la vista */
static int g_ht_guardar_en = 0;                 /* GetTickCount en que hay que guardar (0 = nada) */
static wchar_t g_ht_sub[48];                    /* «F12 · mostrar / ocultar» */
static wchar_t g_ht_tema_txt[16];               /* «TEMA 1/4» */

static const wchar_t *HT_AYUDA_TECLA = L"Clic y apretá una tecla · clic derecho: borrarla · Esc: cancelar";

static void ht_avisar(COLORREF c, int ms, const wchar_t *formato, ...)
{
    va_list a;
    va_start(a, formato);
    wvsprintfW(g_ht_aviso, formato, a);
    va_end(a);
    g_ht_aviso_color = c;
    g_ht_aviso_hasta = ms ? GetTickCount() + (DWORD)ms : 0;
    if (g_ht_ven) InvalidateRect(g_ht_ven, NULL, FALSE);
}

/* ── 7.3 · la maqueta: dónde va cada cosa (una sola vez) ─────────────────────── */
static int ht_el(BYTE tipo, int x, int y, int w, int h, int ref, const wchar_t *texto, const wchar_t *ayuda)
{
    if (g_nel >= HT_MAX_EL) return -1;
    HT_EL *e = &g_el[g_nel];
    e->tipo = tipo; e->x = (short)x; e->y = (short)y; e->w = (short)w; e->h = (short)h;
    e->ref = ref; e->texto = texto; e->ayuda = ayuda; e->oculto = 0;
    return g_nel++;
}
static void ht_carta(const char *id, int x, int y, int w, int h, const wchar_t *t, const wchar_t *nota)
{
    HT_CARTA *c = &g_carta[g_ncarta++];
    c->x = (short)x; c->y = (short)y; c->w = (short)w; c->h = (short)h; c->titulo = t; c->nota = nota;
    c->id = id; c->oculto = 0;
}
static void ht_tx(const char *id, int x, int y, int w, int h, const wchar_t *t, int f, COLORREF c, UINT fmt)
{
    HT_TX *e = &g_tx[g_ntx++];
    e->x = (short)x; e->y = (short)y; e->w = (short)w; e->h = (short)h; e->texto = t;
    e->fuente = (BYTE)f; e->color = c; e->fmt = fmt; e->id = id; e->oculto = 0;
}

#define HT_M    14          /* margen                              */
#define HT_CW   344         /* ancho de una columna                */
#define HT_PAD  14          /* adentro de una tarjeta              */
#define HT_CAB  34          /* el título de una tarjeta            */
#define HT_FILA ((int)g_tm->fila)          /* depende del tema: la densidad */
#define HT_DY   ((HT_FILA - 24) / 2)        /* una opción (24 de alto) centrada en su fila */
#define HT_DYC  ((HT_FILA - 22) / 2)        /* un botoncito (22) centrado en su fila       */
#define HT_DX   (g_tm->estilo_on == 1 ? 34 : 22)   /* dónde empieza el texto de una opción */
#define HT_CHIP 42          /* el botoncito de la tecla            */

/* una opción con su botoncito de tecla a la derecha (si lleva) */
static void ht_op_con_tecla(int i, int x, int y, int w)
{
    if (g_op[i].con_tecla) {
        ht_el(E_OPCION, x, y + HT_DY, w - HT_CHIP - 4, 24, i, g_op[i].texto, g_op[i].ayuda);
        ht_el(E_TECLA, x + w - HT_CHIP, y + HT_DYC, HT_CHIP, 22, i, NULL, HT_AYUDA_TECLA);
    } else ht_el(E_OPCION, x, y + HT_DY, w, 24, i, g_op[i].texto, g_op[i].ayuda);
}

static void ht_maquetar(void)
{
    const int XL = HT_M, XR = HT_M + HT_CW + 12, W = XR + HT_CW + HT_M;
    const int IW = HT_CW - 2 * HT_PAD, MED = (IW - 8) / 2;
    int x, y;
    g_nel = g_ncarta = g_ntx = 0;
    g_ht_w = W;

    /* la cabecera */
    ht_el(E_TITULO, 18, 9, W - HT_M - 26 - 10 - 96 - 8 - 96 - 10 - 76 - 8 - 18, 34, 0, NULL, NULL);
    ht_el(E_CERRAR, W - HT_M - 26, 13, 26, 26, 0, NULL, L"Esconder (F12 la vuelve a mostrar)");
    ht_el(E_PILL, W - HT_M - 26 - 10 - 96, 13, 96, 26, O_ANCLAR, g_op[O_ANCLAR].texto, g_op[O_ANCLAR].ayuda);
    ht_el(E_PILL, W - HT_M - 26 - 10 - 96 - 8 - 96, 13, 96, 26, O_HOTKEYS, g_op[O_HOTKEYS].texto, g_op[O_HOTKEYS].ayuda);
    /* ⚠ mientras anonimo03 elige el estilo: recorre los 4 temas (y lo guarda en el ini) */
    wsprintfW(g_ht_tema_txt, L"TEMA %d/4", g_ht_tema);
    ht_el(E_BOTON, W - HT_M - 26 - 10 - 96 - 8 - 96 - 10 - 76, 15, 76, 22, 3, g_ht_tema_txt,
          L"Probar los 4 estilos: 1 Neón · 2 Sakura · 3 Arcade · 4 Medianoche. Queda guardado (sale cuando se elija uno).");

    /* ── columna izquierda: PISTA y EFECTOS ── */
    x = XL + HT_PAD; y = 60;
    ht_carta("carta.pista", XL, y, HT_CW, HT_CAB + 6 * HT_FILA + 8, L"PISTA", NULL);
    y += HT_CAB;
    {
        static const int PARES[5][2] = { { O_ESTR_OBST, O_OBST_ESTR }, { O_LOCURA, O_LOCURA_S },
                                         { O_PIEDRA, O_PIEDRA_S }, { O_NIEBLA, O_NIEBLA_S }, { O_ESPEJO, O_ESPEJO_S } };
        for (int r = 0; r < 5; r++, y += HT_FILA) {
            ht_op_con_tecla(PARES[r][0], x, y, MED);
            ht_op_con_tecla(PARES[r][1], x + MED + 8, y, MED);
        }
        ht_op_con_tecla(O_ALEATORIO, x, y, MED);
        ht_op_con_tecla(O_ALEATORIO_S, x + MED + 8, y, MED);
        /* ⚠ el cartel «Aleatorio: todavía no está hecho» queda ESCONDIDO y no se borra: las disposiciones
         *   guardadas lo nombran ([fijo.aleatorio]) y una pieza que no existe tira el archivo entero */
        g_el[ht_el(E_FIJO, x, y + HT_DY, IW, 24, 0, L"Aleatorio", NULL)].oculto = 1;
        y += HT_FILA;
    }
    y += 8 + 10;
    ht_carta("carta.efectos", XL, y, HT_CW, HT_CAB + 3 * HT_FILA + 8, L"EFECTOS", L"marcado = se apaga");
    y += HT_CAB;
    /* partida 146 / 164: «Apagar Obs. Carriles» es la más larga y con interruptor no entra en media */
    ht_op_con_tecla(O_VELOCIDAD, x, y, 146);  ht_op_con_tecla(O_BOOSTER, x + 152, y, IW - 152);  y += HT_FILA;
    ht_op_con_tecla(O_GHOST, x, y, 146);      ht_op_con_tecla(O_CARRILES, x + 152, y, IW - 152); y += HT_FILA;
    ht_op_con_tecla(O_RESULTADOS, x, y, 146); y += HT_FILA;
    y += 8 + 12;
    ht_tx("texto.pd", XL + 4, y, HT_CW, 16, L"PD Valofe: lo decide la sala (.pd on / .pd off)", F_CHICO, HT_C_GRIS, DT_LEFT);
    ht_tx("texto.panel_pd", XL + 4, y + 17, HT_CW, 16, L"Panel PD: la calculadora, F9 (Z fijar · X / C tamaño · V B N M mover)", F_CHICO, HT_C_GRIS, DT_LEFT);

    /* ── columna derecha: VISTA y TECLADO ── */
    x = XR + HT_PAD; y = 60;
    ht_carta("carta.vista", XR, y, HT_CW, HT_CAB + 4 * HT_FILA + 2 * 30 + 8, L"VISTA", NULL);
    y += HT_CAB;
    ht_el(E_OPCION, x, y + HT_DY, IW - 70, 24, O_OPACIDAD, g_op[O_OPACIDAD].texto, g_op[O_OPACIDAD].ayuda);
    ht_el(E_VALOR, x + IW - 64, y + HT_DY, 64, 24, 0, NULL, NULL);
    y += HT_FILA;
    ht_el(E_TECLA, x, y + 4, 58, 22, K_ALFM, L"−", L"Bajar la opacidad · clic y apretá una tecla · clic derecho: borrarla");
    ht_el(E_SLIDER, x + 66, y, IW - 132, 30, 0, NULL, L"Arrastrá, o la rueda del mouse");
    ht_el(E_TECLA, x + IW - 58, y + 4, 58, 22, K_ALFP, L"+", L"Subir la opacidad · clic y apretá una tecla · clic derecho: borrarla");
    y += 30;
    ht_el(E_OPCION, x, y + HT_DY, IW - 70, 24, O_FAR, g_op[O_FAR].texto, g_op[O_FAR].ayuda);
    ht_el(E_VALOR, x + IW - 64, y + HT_DY, 64, 24, 1, NULL, NULL);
    y += HT_FILA;
    ht_el(E_TECLA, x, y + 4, 58, 22, K_FARM, L"−", L"Ver más cerca · clic y apretá una tecla · clic derecho: borrarla");
    ht_el(E_SLIDER, x + 66, y, IW - 132, 30, 1, NULL, L"Arrastrá, o la rueda del mouse");
    ht_el(E_TECLA, x + IW - 58, y + 4, 58, 22, K_FARP, L"+", L"Ver más lejos · clic y apretá una tecla · clic derecho: borrarla");
    y += 30;
    /* ⚠ «Ocultar Nombres» no entra en media columna con su botoncito: va sola en su fila */
    ht_op_con_tecla(O_CAMARA, x, y, MED);
    ht_el(E_FIJO, x + MED + 8, y + HT_DY, MED, 24, 1, L"AutoFar", L"El Far según el BPM de la canción: todavía no está hecho.");
    y += HT_FILA;
    ht_op_con_tecla(O_NOMBRES, x, y, 196); y += HT_FILA;
    y += 8 + 10;

    /* ⚠ con los interruptores (temas 2 y 4) «Configuración de Teclado» y «AutoCtrl» no entran en la
     *   misma fila: la casilla va arriba con DE FÁBRICA, y AutoCtrl abajo, debajo de las filas */
    ht_carta("carta.teclado", XR, y, HT_CW, HT_CAB + HT_FILA + 18 + 30 + 30 + HT_FILA + 8, L"TECLADO", NULL);
    y += HT_CAB;
    ht_el(E_OPCION, x, y + HT_DY, IW - 100, 24, O_TECLADO, g_op[O_TECLADO].texto, g_op[O_TECLADO].ayuda);
    ht_el(E_BOTON, x + IW - 92, y + HT_DYC, 92, 22, 2, L"DE FÁBRICA", L"Vuelve las dos filas a W A S D LCtrl / ↑ ← ↓ → RCtrl");
    y += HT_FILA;
    {
        static const wchar_t *CAP[5] = { L"↑  Arriba", L"←  Izq.", L"↓  Abajo", L"→  Der.", L"Booster" };
        static const char *CAP_ID[5] = { "texto.kb_arriba", "texto.kb_izquierda", "texto.kb_abajo", "texto.kb_derecha", "texto.kb_ctrl" };
        const int X0 = x + 28, CWK = (IW - 28 - 4 * 6) / 5;
        for (int k = 0; k < 5; k++) ht_tx(CAP_ID[k], X0 + k * (CWK + 6), y, CWK, 16, CAP[k], F_CHICO, HT_C_GRIS, DT_CENTER);
        y += 18;
        for (int g = 0; g < 2; g++, y += 30) {
            ht_tx(g ? "texto.fila2" : "texto.fila1", x, y + 4, 22, 24, g ? L"2" : L"1", F_CHIP, HT_C_CELESTE, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            for (int k = 0; k < 5; k++)
                ht_el(E_TECLA, X0 + k * (CWK + 6), y + 3, CWK, 24, K_KB(g, k), NULL,
                      L"Clic y apretá una tecla · clic derecho: borrarla · Esc: cancelar · en rosa: cambiada");
        }
        ht_op_con_tecla(O_AUTOCTRL, x, y, MED);
        ht_tx("texto.kb_nota", x + MED + 8, y, MED, HT_FILA, L"las 2 filas a la vez", F_CHICO, HT_C_GRIS,
              DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
        y += HT_FILA;
    }
    y += 8;

    /* el pie */
    y += 12;
    ht_el(E_BOTON, XL, y, 136, 30, 1, L"APAGAR TODO", L"Apaga todas las opciones (vuelve todo a fábrica)");
    ht_el(E_AVISO, XL + 136 + 14, y, W - (XL + 136 + 14) - HT_M, 30, 0, NULL, NULL);
    g_ht_h = y + 30 + HT_M;
}

/* ── 7.3b · ★ LA DISPOSICIÓN: dónde va cada pieza y qué dice, desde un archivo (04-oct) ──────────
 *
 *   anonimo03 la acomoda arrastrando en el editor (herramientas/editor_tool/) y el editor guarda
 *   `r2beat_tool_disposicion.ini` al lado del exe. Formato (UTF-8, un ini simple):
 *
 *       [ventana]            ancho=728  alto=516
 *       [carta.pista]        x= y= w= h=  titulo=PISTA  nota=  oculto=0
 *       [op.locura]          x= y= w= h=  texto=Locura  oculto=0
 *       [tecla.locura] [barra.far] [pastilla.hotkeys] [boton.apagar] [texto.pd] … (ver ht_id_el)
 *
 *   · Lo que no está en el archivo queda de fábrica. Las ACCIONES no cambian nunca: el archivo sólo
 *     mueve, renombra u oculta (cada pieza conserva su tipo y su ref).
 *   · ⛔ Archivo roto (basura, una pieza que no existe, una clave rara, medidas fuera de la ventana):
 *     NO se usa NADA de él — queda la de fábrica — y el log dice por qué (una vez por versión del
 *     archivo). Nunca se cae el juego por esto.
 *   · ★ La de FÁBRICA = la maqueta de ht_maquetar + lo HORNEADO (herramienta_disposicion.h, que genera
 *     herramientas/editor_tool/hornear.py cuando anonimo03 elige la definitiva). Hoy lo horneado está vacío.
 *   · Se lee al armar la ventana y cada vez que se muestra (F12): se puede acomodar con el juego abierto.
 */
#ifdef HT_DISPOSICION_INCLUIR
#include HT_DISPOSICION_INCLUIR                      /* el banco prueba otro horneado */
#else
#include "herramienta_disposicion.h"
#endif
#define HT_DISP_ARCHIVO "r2beat_tool_disposicion.ini"
#define HT_DISP_TEXTOS  160

static wchar_t g_ht_disp_pool[HT_DISP_TEXTOS][64];      /* los textos cambiados (las piezas apuntan acá) */
static int g_ht_disp_npool;
static DWORD g_ht_disp_firma = 1;                       /* para avisar UNA vez por versión del archivo */
static int g_ht_disp_estado;                            /* 0 fábrica · 1 archivo · 2 roto (fábrica) */

/* el id estable de una pieza (no depende del texto ni del lugar) */
static void ht_id_el(const HT_EL *e, char *s)                    /* s: 48 */
{
    static const char *BOTON[4] = { "boton.?", "boton.apagar", "boton.fabrica", "boton.tema" };
    s[0] = 0;
    switch (e->tipo) {
    case E_OPCION: wsprintfA(s, "op.%s", g_op[e->ref].clave); break;
    case E_PILL:   wsprintfA(s, "pastilla.%s", g_op[e->ref].clave); break;
    case E_SLIDER: lstrcpyA(s, e->ref ? "barra.far" : "barra.opacidad"); break;
    case E_VALOR:  lstrcpyA(s, e->ref ? "valor.far" : "valor.opacidad"); break;
    case E_BOTON:  lstrcpyA(s, BOTON[e->ref & 3]); break;
    case E_CERRAR: lstrcpyA(s, "cerrar"); break;
    case E_FIJO:   lstrcpyA(s, e->ref ? "fijo.autofar" : "fijo.aleatorio"); break;
    case E_TITULO: lstrcpyA(s, "titulo"); break;
    case E_AVISO:  lstrcpyA(s, "aviso"); break;
    case E_TECLA:
        if (e->ref >= 0 && e->ref < O_N) wsprintfA(s, "tecla.%s", g_op[e->ref].clave);
        else if (e->ref == K_ALFM) lstrcpyA(s, "tecla.opacidad_menos");
        else if (e->ref == K_ALFP) lstrcpyA(s, "tecla.opacidad_mas");
        else if (e->ref == K_FARM) lstrcpyA(s, "tecla.far_menos");
        else if (e->ref == K_FARP) lstrcpyA(s, "tecla.far_mas");
        else if (ht_es_dik(e->ref)) wsprintfA(s, "tecla.kb%d_%s", (e->ref - 200) / 5 + 1, HT_KB_CLAVE[(e->ref - 200) % 5]);
        break;
    }
}

/* una pieza por id: 0 = pieza (g_el), 1 = tarjeta, 2 = texto suelto; -1 = no existe */
static int ht_buscar_id(const char *id, int *idx)
{
    char t[48];
    for (int i = 0; i < g_nel; i++) { ht_id_el(&g_el[i], t); if (!lstrcmpA(t, id)) { *idx = i; return 0; } }
    for (int i = 0; i < g_ncarta; i++) if (!lstrcmpA(g_carta[i].id, id)) { *idx = i; return 1; }
    for (int i = 0; i < g_ntx; i++) if (!lstrcmpA(g_tx[i].id, id)) { *idx = i; return 2; }
    return -1;
}

static int ht_disp_numero(const wchar_t *v, int *n)
{
    int s = 1, r = 0, hay = 0;
    while (*v == L' ' || *v == L'\t') v++;
    if (*v == L'-') { s = -1; v++; }
    for (; *v >= L'0' && *v <= L'9'; v++) { r = r * 10 + (*v - L'0'); hay = 1; if (r > 100000) return 0; }
    while (*v == L' ' || *v == L'\t') v++;
    if (!hay || *v) return 0;
    *n = s * r;
    return 1;
}

static const wchar_t *ht_disp_texto(const wchar_t *v)
{
    if (g_ht_disp_npool >= HT_DISP_TEXTOS || lstrlenW(v) > 60) return NULL;
    wchar_t *d = g_ht_disp_pool[g_ht_disp_npool++];
    lstrcpynW(d, v, 64);
    return d;
}

/* aplica `txt` (UTF-8) sobre la maqueta de ahora. Si algo está mal NO toca nada: devuelve 0 y el
 * motivo. ⚠ todo-o-nada: se trabaja sobre la maqueta viva y, si falla, se vuelve a la copia. */
static int ht_disp_aplicar_texto(const char *txt, int largo, char *motivo)    /* motivo: 160 */
{
    static HT_EL el0[HT_MAX_EL];
    static HT_CARTA ca0[6];
    static HT_TX tx0[20];
    int w0 = g_ht_w, h0 = g_ht_h, npool0 = g_ht_disp_npool, ok = 1, linea = 0, hay_ventana = 0;
    int clase = -9, idx = -1, piezas = 0;
    CopyMemory(el0, g_el, sizeof(g_el)); CopyMemory(ca0, g_carta, sizeof(g_carta)); CopyMemory(tx0, g_tx, sizeof(g_tx));
    if (largo >= 3 && (BYTE)txt[0] == 0xEF && (BYTE)txt[1] == 0xBB && (BYTE)txt[2] == 0xBF) { txt += 3; largo -= 3; }
    int nw = largo > 0 ? MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, txt, largo, NULL, 0) : 0;
    wchar_t *w = nw > 0 ? (wchar_t *)HeapAlloc(GetProcessHeap(), 0, (nw + 1) * sizeof(wchar_t)) : NULL;
    if (!w) { lstrcpyA(motivo, "vacío o no es texto UTF-8"); return 0; }
    MultiByteToWideChar(CP_UTF8, 0, txt, largo, w, nw);
    w[nw] = 0;
    motivo[0] = 0;
    for (wchar_t *p = w; ok && *p; ) {
        wchar_t *fin = p;
        while (*fin && *fin != L'\n') fin++;
        wchar_t sig = *fin;
        *fin = 0;
        linea++;
        int n = lstrlenW(p);
        while (n > 0 && (p[n - 1] == L'\r' || p[n - 1] == L' ' || p[n - 1] == L'\t')) p[--n] = 0;
        wchar_t *a = p;
        while (*a == L' ' || *a == L'\t') a++;
        if (*a && *a != L';' && *a != L'#') {
            if (*a == L'[') {
                char id[48];
                int k = 0;
                for (a++; *a && *a != L']' && k < 47; a++) id[k++] = (char)(*a < 128 ? *a : '?');
                id[k] = 0;
                if (*a != L']') { wsprintfA(motivo, "línea %d: sección sin cerrar", linea); ok = 0; }
                else if (!lstrcmpA(id, "ventana")) { clase = 9; hay_ventana = 1; }
                else if ((clase = ht_buscar_id(id, &idx)) < 0) { wsprintfA(motivo, "línea %d: no existe la pieza [%s]", linea, id); ok = 0; }
                else piezas++;
            } else {
                wchar_t *eq = a;
                while (*eq && *eq != L'=') eq++;
                if (!*eq || clase == -9) { wsprintfA(motivo, "línea %d: no es «clave=valor» dentro de una sección", linea); ok = 0; }
                else {
                    wchar_t *kf = eq;
                    while (kf > a && (kf[-1] == L' ' || kf[-1] == L'\t')) kf--;
                    *kf = 0;
                    wchar_t *v = eq + 1;
                    while (*v == L' ' || *v == L'\t') v++;
                    int num = 0, es_num = ht_disp_numero(v, &num);
                    short *px = NULL, *py = NULL, *pw = NULL, *ph = NULL;
                    BYTE *poc = NULL;
                    if (clase == 0) { HT_EL *e = &g_el[idx]; px = &e->x; py = &e->y; pw = &e->w; ph = &e->h; poc = &e->oculto; }
                    if (clase == 1) { HT_CARTA *c = &g_carta[idx]; px = &c->x; py = &c->y; pw = &c->w; ph = &c->h; poc = &c->oculto; }
                    if (clase == 2) { HT_TX *t = &g_tx[idx]; px = &t->x; py = &t->y; pw = &t->w; ph = &t->h; poc = &t->oculto; }
                    if (clase == 9 && !lstrcmpW(a, L"ancho") && es_num) g_ht_w = num;
                    else if (clase == 9 && !lstrcmpW(a, L"alto") && es_num) g_ht_h = num;
                    else if (clase != 9 && !lstrcmpW(a, L"x") && es_num) *px = (short)num;
                    else if (clase != 9 && !lstrcmpW(a, L"y") && es_num) *py = (short)num;
                    else if (clase != 9 && !lstrcmpW(a, L"w") && es_num) *pw = (short)num;
                    else if (clase != 9 && !lstrcmpW(a, L"h") && es_num) *ph = (short)num;
                    else if (clase != 9 && !lstrcmpW(a, L"oculto") && es_num && (num == 0 || num == 1)) *poc = (BYTE)num;
                    else if ((clase == 0 || clase == 2) && !lstrcmpW(a, L"texto")) {
                        const wchar_t *t = ht_disp_texto(v);
                        if (!t) { wsprintfA(motivo, "línea %d: texto demasiado largo", linea); ok = 0; }
                        else if (clase == 0) g_el[idx].texto = t;
                        else g_tx[idx].texto = t;
                    } else if (clase == 1 && (!lstrcmpW(a, L"titulo") || !lstrcmpW(a, L"nota"))) {
                        const wchar_t *t = ht_disp_texto(v);
                        if (!t) { wsprintfA(motivo, "línea %d: texto demasiado largo", linea); ok = 0; }
                        else if (a[0] == L't') g_carta[idx].titulo = t;
                        else g_carta[idx].nota = *t ? t : NULL;
                    } else { wsprintfA(motivo, "línea %d: clave o valor que no entiendo", linea); ok = 0; }
                }
            }
        }
        if (!sig) break;
        p = fin + 1;
    }
    HeapFree(GetProcessHeap(), 0, w);
    if (ok && !hay_ventana) { lstrcpyA(motivo, "falta [ventana]"); ok = 0; }
    if (ok && (g_ht_w < 300 || g_ht_w > 1600 || g_ht_h < 200 || g_ht_h > 1200)) {
        wsprintfA(motivo, "la ventana de %dx%d no va (de 300x200 a 1600x1200)", g_ht_w, g_ht_h); ok = 0;
    }
    /* todo adentro de la ventana, y con tamaño */
    for (int i = 0; ok && i < g_nel + g_ncarta + g_ntx; i++) {
        int x, y, ww, hh;
        char id[48];
        if (i < g_nel) { HT_EL *e = &g_el[i]; x = e->x; y = e->y; ww = e->w; hh = e->h; ht_id_el(e, id); }
        else if (i < g_nel + g_ncarta) { HT_CARTA *c = &g_carta[i - g_nel]; x = c->x; y = c->y; ww = c->w; hh = c->h; lstrcpyA(id, c->id); }
        else { HT_TX *t = &g_tx[i - g_nel - g_ncarta]; x = t->x; y = t->y; ww = t->w; hh = t->h; lstrcpyA(id, t->id); }
        if (x < 0 || y < 0 || ww < 4 || hh < 4 || x + ww > g_ht_w || y + hh > g_ht_h) {
            wsprintfA(motivo, "[%s] queda fuera de la ventana (%d,%d %dx%d en %dx%d)", id, x, y, ww, hh, g_ht_w, g_ht_h);
            ok = 0;
        }
    }
    if (!ok) {
        CopyMemory(g_el, el0, sizeof(g_el)); CopyMemory(g_carta, ca0, sizeof(g_carta)); CopyMemory(g_tx, tx0, sizeof(g_tx));
        g_ht_w = w0; g_ht_h = h0; g_ht_disp_npool = npool0;
        return 0;
    }
    wsprintfA(motivo, "%d pieza(s)", piezas);
    return 1;
}

/* la de FÁBRICA: la maqueta del código y, encima, lo horneado (si hay) */
static void ht_maquetar_fabrica(void)
{
    char motivo[160];
    ht_maquetar();
    g_ht_disp_npool = 0;
    g_ht_disp_estado = 0;
    if (HT_DISPOSICION_HORNEADA[0]) {
        if (!ht_disp_aplicar_texto(HT_DISPOSICION_HORNEADA, lstrlenA(HT_DISPOSICION_HORNEADA), motivo)) {
            static int dicho = 0;
            if (!dicho) { dicho = 1; apuntar("  [tool] ⛔ la disposición HORNEADA está mal (%s): queda la del código", motivo); }
        }
    }
}

/* la maqueta completa: la de fábrica y, encima, el archivo si lo hay y está sano */
static void ht_maquetar_todo(void)
{
    char motivo[160], ruta[MAX_PATH];
    DWORD firma = 2166136261u;
    ht_maquetar_fabrica();
    lstrcpyA(ruta, g_carpeta);
    lstrcatA(ruta, HT_DISP_ARCHIVO);
    HANDLE h = CreateFileA(ruta, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) {
        if (g_ht_disp_firma != 0) { g_ht_disp_firma = 0; apuntar("  [tool] disposición: la de fábrica (no hay %s)", HT_DISP_ARCHIVO); }
        return;
    }
    DWORD tam = GetFileSize(h, NULL), leidos = 0;
    char *b = (tam != INVALID_FILE_SIZE && tam < 65536) ? (char *)HeapAlloc(GetProcessHeap(), 0, tam + 1) : NULL;
    if (b && !ReadFile(h, b, tam, &leidos, NULL)) leidos = 0;
    CloseHandle(h);
    if (!b) {
        if (g_ht_disp_firma != 3) { g_ht_disp_firma = 3; apuntar("  [tool] ⚠ disposición: %s es demasiado grande: uso la de fábrica", HT_DISP_ARCHIVO); }
        g_ht_disp_estado = 2;
        return;
    }
    for (DWORD i = 0; i < leidos; i++) firma = (firma ^ (BYTE)b[i]) * 16777619u;
    if (firma < 4) firma += 4;
    int ok = ht_disp_aplicar_texto(b, (int)leidos, motivo);
    HeapFree(GetProcessHeap(), 0, b);
    g_ht_disp_estado = ok ? 1 : 2;
    if (firma != g_ht_disp_firma) {
        g_ht_disp_firma = firma;
        if (ok) apuntar("  [tool] disposición: %s (%s, ventana %dx%d)", HT_DISP_ARCHIVO, motivo, g_ht_w, g_ht_h);
        else apuntar("  [tool] ⚠ disposición: %s está mal (%s): uso la de fábrica", HT_DISP_ARCHIVO, motivo);
    }
}

/* ── 7.4 · dibujar ──────────────────────────────────────────────────────────── */
static void ht_caja(int x, int y, int w, int h, int r, COLORREF f, COLORREF b, int grosor)
{
    HBRUSH br = CreateSolidBrush(f);
    HPEN pn = CreatePen(PS_SOLID, grosor > 0 ? 2 * grosor : 1, grosor > 0 ? b : f);
    HGDIOBJ ob = SelectObject(g_ht_dc2, br), op = SelectObject(g_ht_dc2, pn);
    if (r > 0) RoundRect(g_ht_dc2, 2 * x, 2 * y, 2 * (x + w), 2 * (y + h), 4 * r, 4 * r);
    else Rectangle(g_ht_dc2, 2 * x, 2 * y, 2 * (x + w), 2 * (y + h));
    SelectObject(g_ht_dc2, ob); SelectObject(g_ht_dc2, op);
    DeleteObject(br); DeleteObject(pn);
}
static void ht_circulo(int cx, int cy, int r, COLORREF f, COLORREF b, int grosor)
{
    HBRUSH br = CreateSolidBrush(f);
    HPEN pn = CreatePen(PS_SOLID, grosor > 0 ? 2 * grosor : 1, grosor > 0 ? b : f);
    HGDIOBJ ob = SelectObject(g_ht_dc2, br), op = SelectObject(g_ht_dc2, pn);
    Ellipse(g_ht_dc2, 2 * (cx - r), 2 * (cy - r), 2 * (cx + r), 2 * (cy + r));
    SelectObject(g_ht_dc2, ob); SelectObject(g_ht_dc2, op);
    DeleteObject(br); DeleteObject(pn);
}
static void ht_trazo(const POINT *p, int n, COLORREF c, int grosor)
{
    LOGBRUSH lb = { BS_SOLID, c, 0 };
    POINT q[8];
    HPEN pn = ExtCreatePen(PS_GEOMETRIC | PS_SOLID | PS_ENDCAP_ROUND | PS_JOIN_ROUND, 2 * grosor, &lb, 0, NULL);
    HGDIOBJ op = SelectObject(g_ht_dc2, pn);
    for (int i = 0; i < n && i < 8; i++) { q[i].x = 2 * p[i].x; q[i].y = 2 * p[i].y; }
    Polyline(g_ht_dc2, q, n);
    SelectObject(g_ht_dc2, op);
    DeleteObject(pn);
}
static void ht_texto(int x, int y, int w, int h, const wchar_t *s, int f, COLORREF c, UINT fmt)
{
    RECT r = { x, y, x + w, y + h };
    SelectObject(g_ht_dc1, g_ht_f[f]);
    SetTextColor(g_ht_dc1, c);
    DrawTextW(g_ht_dc1, s, -1, &r, fmt | DT_NOPREFIX);
}

static int ht_slider_valor(int s, int *min, int *max)
{
    if (s == 0) { *min = 1; *max = 15; return g_ht_alfa_nivel; }
    *min = 10; *max = 60; return g_ht_far_pct / 5;
}

/* dónde va la etiqueta «pendiente»: después del texto (medido con la fuente de verdad) */
static int ht_x_etiqueta(const HT_EL *e)
{
    SIZE t = { 0, 0 };
    SelectObject(g_ht_dc1, g_ht_f[F_TEXTO]);
    GetTextExtentPoint32W(g_ht_dc1, e->texto, lstrlenW(e->texto), &t);
    return e->x + HT_DX + t.cx + 10;
}

/* pase 0 = formas (capa doble) · pase 1 = texto (capa final) */
/* la casilla de una opción, según el tema: tilde (1 Neón), interruptor (2 y 4), bloque (3 Arcade) */
static void ht_casilla(int x, int cy, int vive, int on, int hov)
{
    switch (g_tm->estilo_on) {
    case 1: {                                               /* interruptor 26 x 14 */
        int y = cy - 7;
        COLORREF f = !vive ? HT_C_MUERTO : on ? HT_C_VERDE : HT_C_HUECO;
        COLORREF b = !vive ? HT_C_BORDE : on ? HT_C_VERDE : hov ? HT_C_CELESTE : HT_C_HUECO_B;
        ht_caja(x, y, 26, 14, 7, f, b, 1);
        ht_circulo(on ? x + 19 : x + 7, cy, 5, !vive ? HT_C_APAGADO : on ? HT_C_TILDE : HT_C_GRIS,
                   !vive ? HT_C_APAGADO : on ? HT_C_TILDE : HT_C_GRIS, 0);
        break;
    }
    case 2: {                                               /* bloque cuadrado 14 x 14 */
        int y = cy - 7;
        if (on) {
            ht_caja(x, y, 14, 14, 0, HT_C_VERDE, HT_C_VERDE, 0);
            ht_caja(x + 4, y + 4, 6, 6, 0, HT_C_TILDE, HT_C_TILDE, 0);
        } else ht_caja(x, y, 14, 14, 0, vive ? HT_C_HUECO : HT_C_MUERTO,
                       !vive ? HT_C_BORDE : hov ? HT_C_CELESTE : HT_C_HUECO_B, 1);
        break;
    }
    default: {                                              /* casilla 16 x 16 con tilde */
        int by = cy - 8;
        if (on) {
            POINT p[3] = { { x + 4, by + 8 }, { x + 7, by + 11 }, { x + 12, by + 5 } };
            ht_caja(x, by, 16, 16, 4, HT_C_VERDE, HT_C_VERDE, 0);
            ht_trazo(p, 3, HT_C_TILDE, 2);
        } else if (vive) ht_caja(x, by, 16, 16, 4, HT_C_HUECO, hov ? HT_C_CELESTE : HT_C_HUECO_B, 1);
        else ht_caja(x, by, 16, 16, 4, HT_C_MUERTO, HT_C_BORDE, 1);
    }
    }
}

static int ht_min(int a, int b) { return a < b ? a : b; }

static void ht_pintar_el(int i, int pase)
{
    HT_EL *e = &g_el[i];
    int hov = i == g_ht_hover;
    if (e->oculto) return;
    switch (e->tipo) {
    case E_TITULO:
        if (pase == 1) {
            SIZE t, t2;
            SelectObject(g_ht_dc1, g_ht_f[F_TITULO]);
            GetTextExtentPoint32W(g_ht_dc1, g_tm->titulo1, lstrlenW(g_tm->titulo1), &t);
            GetTextExtentPoint32W(g_ht_dc1, g_tm->titulo2, lstrlenW(g_tm->titulo2), &t2);
            /* ★ 04-oct, anonimo03: el nombre es «Ñ2Hock» — las mayúsculas (y el 2) en el rosa de siempre, las
             *   minúsculas en blanco, PEGADAS (es una sola palabra) */
            int sep = 0, x2 = e->x + t.cx + sep, x3 = x2 + t2.cx + 12;
            ht_texto(e->x, e->y, e->w, e->h, g_tm->titulo1, F_TITULO, HT_C_ROSA, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
            if (x2 < e->x + e->w)
                ht_texto(x2, e->y, e->x + e->w - x2, e->h, g_tm->titulo2, F_TITULO,
                         HT_C_TEXTO, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
            if (x3 + 48 <= e->x + e->w)                   /* el «F12 · mostrar…» sólo si entra algo legible */
                ht_texto(x3, e->y + 3, e->x + e->w - x3, e->h - 3, e->texto ? e->texto : g_ht_sub, F_CHICO, HT_C_GRIS,
                         DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
        }
        break;
    case E_AVISO:
        if (pase == 1) {                            /* el cartel de abajo: un aviso (si hay) o el estado */
            wchar_t t[320];
            COLORREF c = HT_C_GRIS;
            if (g_ht_aviso[0]) { lstrcpyW(t, g_ht_aviso); c = g_ht_aviso_color; }
            else {
                int rotas = 0;
                for (int k = 0; k < O_N; k++) if (g_op[k].rota) rotas++;
                if (rotas) { wsprintfW(t, L"%d opción(es) no disponible(s) con este exe: ver el log", rotas); c = HT_C_ROSA; }
                else wsprintfW(t, L"todo enganchado · %s", g_ht_sub);
            }
            ht_texto(e->x, e->y, e->w, e->h, t, F_TEXTO, c, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
        }
        break;
    case E_OPCION: case E_FIJO: {
        int fijo = e->tipo == E_FIJO;
        HT_OP *o = fijo ? NULL : &g_op[e->ref];
        int vive = !fijo && o->permitida && !o->rota, on = vive && o->quiere;
        if (pase == 0) {
            ht_casilla(e->x, e->y + e->h / 2, vive, on, hov);
            if (fijo) ht_caja(ht_x_etiqueta(e), e->y + 5, 66, 15, ht_min(7, g_tm->radio_chip), HT_C_HUECO, HT_C_HUECO_B, 1);
        } else {
            COLORREF c = !vive ? HT_C_APAGADO : (on || hov) ? HT_C_TEXTO : HT_C_SUAVE;
            ht_texto(e->x + HT_DX, e->y, e->w - HT_DX, e->h, e->texto, F_TEXTO, c, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
            if (fijo) ht_texto(ht_x_etiqueta(e), e->y + 5, 66, 15, L"pendiente", F_CHICO, HT_C_GRIS, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }
        break;
    }
    case E_TECLA: {
        int *p = ht_tecla_de(e->ref), v = p ? *p : 0;
        int vive = ht_tecla_viva(e->ref), esp = g_ht_esperando == e->ref;
        if (pase == 0) {
            if (esp) ht_caja(e->x, e->y, e->w, e->h, g_tm->radio_chip, HT_C_ROSA_OSC, HT_C_ROSA, 1);
            else ht_caja(e->x, e->y, e->w, e->h, g_tm->radio_chip, vive ? HT_C_HUECO : HT_C_MUERTO,
                         vive && hov ? HT_C_CELESTE : HT_C_HUECO_B, 1);
        } else {
            wchar_t n[32];
            COLORREF c;
            if (esp) { lstrcpyW(n, L"tecla…"); c = HT_C_ROSA; }
            else {
                ht_nombre_tecla(e->ref, v, n);
                int activo = ht_es_dik(e->ref) ? g_op[O_TECLADO].quiere : g_op[O_HOTKEYS].quiere;
                int cambiada = ht_es_dik(e->ref) && v != HT_KB_FABRICA[(e->ref - 200) / 5][(e->ref - 200) % 5];
                c = !vive ? HT_C_APAGADO : !v ? HT_C_GRIS : cambiada ? HT_C_ROSA : activo ? HT_C_CELESTE : HT_C_SUAVE;
            }
            if (e->texto && !esp) {        /* los − / + de los deslizadores */
                ht_texto(e->x + 7, e->y, 12, e->h, e->texto, F_CHIP, vive ? HT_C_GRIS : HT_C_APAGADO, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
                ht_texto(e->x + 16, e->y, e->w - 18, e->h, n, F_CHIP, c, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
            } else ht_texto(e->x + 2, e->y, e->w - 4, e->h, n, F_CHIP, c, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
        }
        break;
    }
    case E_SLIDER: {
        int o = e->ref ? O_FAR : O_OPACIDAD, mn, mx, v = ht_slider_valor(e->ref, &mn, &mx);
        int vive = g_op[o].permitida && !g_op[o].rota, on = vive && g_op[o].quiere;
        int x0 = e->x + 8, x1 = e->x + e->w - 8, cy = e->y + e->h / 2;
        int px = x0 + (x1 - x0) * (v - mn) / (mx - mn);
        int r = g_tm->radio_chip ? 3 : 0;
        if (pase == 0) {
            ht_caja(x0 - 3, cy - 3, x1 - x0 + 6, 6, r, HT_C_HUECO, g_tm->grosor ? HT_C_HUECO_B : HT_C_HUECO, g_tm->grosor ? 1 : 0);
            ht_caja(x0 - 3, cy - 3, px - x0 + 6, 6, r, on ? HT_C_ROSA : HT_C_HUECO_B, on ? HT_C_ROSA : HT_C_HUECO_B, 0);
            if (g_tm->radio_chip) ht_circulo(px, cy, 8, vive ? HT_C_TEXTO : HT_C_APAGADO,
                                             (hov || g_ht_arrastre == i) && vive ? HT_C_ROSA : HT_C_BORDE, 2);
            else ht_caja(px - 5, cy - 9, 10, 18, 0, vive ? (on ? HT_C_ROSA : HT_C_TEXTO) : HT_C_APAGADO,
                         (hov || g_ht_arrastre == i) && vive ? HT_C_CELESTE : HT_C_FONDO, 1);
        }
        break;
    }
    case E_VALOR: {
        if (pase == 1) {
            int o = e->ref ? O_FAR : O_OPACIDAD;
            wchar_t t[24];
            if (e->ref) wsprintfW(t, L"x%d.%02d", g_ht_far_pct / 100, g_ht_far_pct % 100);
            else wsprintfW(t, L"%d%%", (100 * 17 * g_ht_alfa_nivel + 127) / 255);
            ht_texto(e->x, e->y, e->w, e->h, t, F_CHIP, g_op[o].quiere && !g_op[o].rota ? HT_C_CELESTE : HT_C_GRIS,
                     DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
        }
        break;
    }
    case E_PILL: {
        HT_OP *o = &g_op[e->ref];
        int on = o->quiere;
        int cy = e->y + e->h / 2, r = ht_min(e->h / 2, g_tm->radio_pill);
        if (pase == 0) {
            ht_caja(e->x, e->y, e->w, e->h, r, on ? HT_C_VERDE_OSC : HT_C_TARJETA,
                    on ? HT_C_VERDE : (hov ? HT_C_CELESTE : HT_C_BORDE), 1);
            if (g_tm->radio_pill) {
                if (on) ht_circulo(e->x + 16, cy, 7, HT_C_VERDE, HT_C_VERDE, 0);
                ht_circulo(e->x + 16, cy, 4, on ? HT_C_VERDE_LED : HT_C_HUECO_B, on ? HT_C_VERDE_LED : HT_C_HUECO_B, 0);
            } else ht_caja(e->x + 12, cy - 4, 8, 8, 0, on ? HT_C_VERDE_LED : HT_C_HUECO_B, on ? HT_C_VERDE_LED : HT_C_HUECO_B, 0);
        } else ht_texto(e->x + 24, e->y, e->w - 30, e->h, e->texto, F_PILL, on ? HT_C_VERDE_TX : HT_C_GRIS,
                        DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        break;
    }
    case E_BOTON: {
        int fuerte = e->ref == 1, vive = e->ref != 2 || !g_op[O_TECLADO].rota;
        int r = ht_min(e->h / 2, g_tm->radio_pill);
        if (pase == 0) {
            if (fuerte) ht_caja(e->x, e->y, e->w, e->h, r, hov ? HT_C_ROSA_OSC : HT_C_FONDO, HT_C_ROSA, 1);
            else ht_caja(e->x, e->y, e->w, e->h, r, e->ref == 3 ? HT_C_CABEZA : HT_C_TARJETA,
                         vive && hov ? HT_C_CELESTE : HT_C_HUECO_B, 1);
        } else ht_texto(e->x, e->y, e->w, e->h, e->texto, F_PILL,
                        fuerte ? HT_C_ROSA : !vive ? HT_C_APAGADO : hov ? HT_C_CELESTE : HT_C_SUAVE,
                        DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        break;
    }
    case E_CERRAR: {
        int cx = e->x + e->w / 2, cy = e->y + e->h / 2;
        if (pase == 0) {
            POINT a[2] = { { cx - 4, cy - 4 }, { cx + 4, cy + 4 } }, b[2] = { { cx + 4, cy - 4 }, { cx - 4, cy + 4 } };
            COLORREF f = hov ? HT_C_ROSA : HT_C_ROSA_F;
            if (g_tm->radio_pill) ht_circulo(cx, cy, e->w / 2, f, f, 0);
            else ht_caja(e->x, e->y, e->w, e->h, 0, f, f, 0);
            ht_trazo(a, 2, RGB(255, 255, 255), 2);
            ht_trazo(b, 2, RGB(255, 255, 255), 2);
        }
        break;
    }
    }
}

static void ht_pintar(HDC dc)
{
    const int W = g_ht_w, H = g_ht_h;
    if (!g_ht_dc2) {
        HDC pantalla = GetDC(NULL);                 /* ⚠ de la pantalla: un DC de memoria ajeno puede ser monocromo */
        g_ht_dc2 = CreateCompatibleDC(pantalla);
        g_ht_dc1 = CreateCompatibleDC(pantalla);
        g_ht_bm2 = CreateCompatibleBitmap(pantalla, 2 * W, 2 * H);
        g_ht_bm1 = CreateCompatibleBitmap(pantalla, W, H);
        ReleaseDC(NULL, pantalla);
        SelectObject(g_ht_dc2, g_ht_bm2);
        SelectObject(g_ht_dc1, g_ht_bm1);
    }
    /* ── capa doble: las formas ── */
    ht_caja(0, 0, W, H, 0, HT_C_FONDO, HT_C_FONDO, 0);
    ht_caja(0, 0, W, 52, 0, HT_C_CABEZA, HT_C_CABEZA, 0);
    if (g_tm->tira)
        for (int i = 0; i < 64; i++) {                       /* la tirita de arriba: rosa -> celeste */
            int r = 0xff + (0x8f - 0xff) * i / 63, g = 0x7a + (0xe7 - 0x7a) * i / 63, b = 0xb8 + (0xff - 0xb8) * i / 63;
            int x0 = W * i / 64, x1 = W * (i + 1) / 64;
            ht_caja(x0, 0, x1 - x0 + 1, 3, 0, RGB(r, g, b), RGB(r, g, b), 0);
        }
    ht_caja(0, 52, W, 1, 0, g_tm->cabecera == 2 ? HT_C_CELESTE : HT_C_BORDE, g_tm->cabecera == 2 ? HT_C_CELESTE : HT_C_BORDE, 0);
    for (int c = 0; c < g_ncarta; c++) {
        HT_CARTA *k = &g_carta[c];
        if (k->oculto) continue;
        ht_caja(k->x, k->y, k->w, k->h, g_tm->radio, HT_C_TARJETA, g_tm->grosor ? HT_C_BORDE : HT_C_TARJETA, g_tm->grosor);
        if (g_tm->cabecera == 0) ht_caja(k->x + HT_PAD, k->y + 13, 3, 11, 1, HT_C_ROSA, HT_C_ROSA, 0);
        if (g_tm->cabecera == 2) {
            ht_caja(k->x + HT_PAD, k->y + 11, 6, 14, 0, HT_C_ROSA, HT_C_ROSA, 0);
            ht_caja(k->x + HT_PAD, k->y + 30, k->w - 2 * HT_PAD, 1, 0, HT_C_BORDE, HT_C_BORDE, 0);
        }
    }
    for (int i = 0; i < g_nel; i++) ht_pintar_el(i, 0);

    /* ── a la capa final, achicada (eso suaviza los bordes) ── */
    SetStretchBltMode(g_ht_dc1, HALFTONE);
    SetBrushOrgEx(g_ht_dc1, 0, 0, NULL);
    StretchBlt(g_ht_dc1, 0, 0, W, H, g_ht_dc2, 0, 0, 2 * W, 2 * H, SRCCOPY);

    /* ── el texto, nítido ── */
    SetBkMode(g_ht_dc1, TRANSPARENT);
    for (int c = 0; c < g_ncarta; c++) {
        HT_CARTA *k = &g_carta[c];
        if (k->oculto) continue;
        int dx = g_tm->cabecera == 0 ? 10 : g_tm->cabecera == 2 ? 12 : 0;
        COLORREF ct = g_tm->cabecera == 0 ? HT_C_TEXTO : g_tm->cabecera == 2 ? HT_C_CELESTE : HT_C_ROSA;
        SetTextCharacterExtra(g_ht_dc1, g_tm->espaciado);
        ht_texto(k->x + HT_PAD + dx, k->y + 8, k->w - 2 * HT_PAD, 20, k->titulo, F_CARTA, ct, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
        SetTextCharacterExtra(g_ht_dc1, 0);
        if (k->nota) ht_texto(k->x + HT_PAD, k->y + 8, k->w - 2 * HT_PAD, 20, k->nota, F_CHICO, HT_C_GRIS, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
    }
    for (int i = 0; i < g_ntx; i++) {
        HT_TX *t = &g_tx[i];
        if (t->oculto) continue;
        ht_texto(t->x, t->y, t->w, t->h, t->texto, t->fuente, t->color, t->fmt);
    }
    for (int i = 0; i < g_nel; i++) ht_pintar_el(i, 1);
    /* el marco */
    {
        HGDIOBJ ob = SelectObject(g_ht_dc1, GetStockObject(NULL_BRUSH));
        HPEN pn = CreatePen(PS_SOLID, 1, HT_C_BORDE);
        HGDIOBJ op = SelectObject(g_ht_dc1, pn);
        Rectangle(g_ht_dc1, 0, 0, W, H);
        SelectObject(g_ht_dc1, op); SelectObject(g_ht_dc1, ob);
        DeleteObject(pn);
    }
    BitBlt(dc, 0, 0, W, H, g_ht_dc1, 0, 0, SRCCOPY);
}

/* ── 7.5 · el globito de ayuda (nuestro: el amarillo de Windows desentona) ─────── */
static LRESULT CALLBACK ht_globo_proc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    if (m == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        RECT r;
        GetClientRect(h, &r);
        HBRUSH f = CreateSolidBrush(HT_C_GLOBO);
        FillRect(dc, &r, f);
        DeleteObject(f);
        HBRUSH b = CreateSolidBrush(HT_C_BORDE);
        FrameRect(dc, &r, b);
        DeleteObject(b);
        wchar_t t[256];
        GetWindowTextW(h, t, 256);
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, HT_C_SUAVE);
        SelectObject(dc, g_ht_f[F_CHICO]);
        InflateRect(&r, -8, -5);
        DrawTextW(dc, t, -1, &r, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX);
        EndPaint(h, &ps);
        return 0;
    }
    if (m == WM_NCHITTEST) return HTTRANSPARENT;
    return DefWindowProcW(h, m, wp, lp);
}

static void ht_globo_ocultar(void)
{
    g_ht_globo_el = -1;
    if (g_ht_globo && IsWindowVisible(g_ht_globo)) ShowWindow(g_ht_globo, SW_HIDE);
}

static void ht_globo_mostrar(int i)
{
    if (!g_ht_globo || i < 0 || i >= g_nel || !g_el[i].ayuda) return;
    const wchar_t *t = g_el[i].ayuda;
    wchar_t extra[256];
    if (g_el[i].tipo == E_OPCION && (!g_op[g_el[i].ref].permitida || g_op[g_el[i].ref].rota)) {
        wsprintfW(extra, L"%s\n%s", t, !g_op[g_el[i].ref].permitida ? L"⛔ Apagada en esta versión de la tool."
                                                                  : L"⛔ No disponible con este exe (ver el log).");
        t = extra;
    }
    SetWindowTextW(g_ht_globo, t);
    HDC dc = GetDC(g_ht_globo);
    SelectObject(dc, g_ht_f[F_CHICO]);
    RECT r = { 0, 0, 280, 0 };
    DrawTextW(dc, t, -1, &r, DT_LEFT | DT_WORDBREAK | DT_CALCRECT | DT_NOPREFIX);
    ReleaseDC(g_ht_globo, dc);
    POINT p = { g_el[i].x, g_el[i].y + g_el[i].h + 6 };
    ClientToScreen(g_ht_ven, &p);
    SetWindowPos(g_ht_globo, HWND_TOPMOST, p.x, p.y, r.right + 16, r.bottom + 10,
                 SWP_NOACTIVATE | SWP_SHOWWINDOW);
    InvalidateRect(g_ht_globo, NULL, TRUE);
    g_ht_globo_el = i;
}

/* ── 7.6 · prender / apagar, mostrar, el reloj ──────────────────────────────── */
static void ht_refrescar(void) { if (g_ht_ven) InvalidateRect(g_ht_ven, NULL, FALSE); }

static void ht_pedir_guardar(void) { g_ht_guardar_en = (int)GetTickCount() + 400; if (!g_ht_guardar_en) g_ht_guardar_en = 1; }

/* prender / apagar una opción (desde la ventana o un atajo) */
static void ht_cambiar(int i, int valor)
{
    HT_OP *o = &g_op[i];
    if (!o->permitida || o->rota) return;
    if (i == O_HOTKEYS && !valor) return;           /* los atajos no se apagan (la pastilla es un aviso) */
    if (valor && o->pareja >= 0 && g_op[o->pareja].quiere) {
        g_op[o->pareja].quiere = 0;
        ht_aplicar(o->pareja);                      /* ⚠ primero se saca la pareja: tocan los mismos sitios */
    }
    o->quiere = valor;
    ht_aplicar(i);
    if (i == O_ANCLAR && g_ht_ven)
        SetWindowPos(g_ht_ven, valor ? HWND_TOPMOST : HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER);
    ht_refrescar();
    ht_pedir_guardar();
}

static void ht_apagar_todo(void)
{
    for (int i = 0; i < O_N; i++) {
        if (i == O_ANCLAR || i == O_HOTKEYS) continue;
        if (g_op[i].quiere) { g_op[i].quiere = 0; ht_aplicar(i); }
    }
    ht_refrescar();
    ht_pedir_guardar();
}

/* ¿la ventana de adelante es nuestra (el juego o la tool)? GetAsyncKeyState es de TODO Windows */
static int ht_con_foco(void)
{
    HWND w = GetForegroundWindow();
    DWORD pid = 0;
    if (w) GetWindowThreadProcessId(w, &pid);
    return pid == GetCurrentProcessId();
}

static BYTE g_ht_antes[256];
static int ht_recien(int vk)
{
    if (vk <= 0 || vk > 255) return 0;
    int b = (GetAsyncKeyState(vk) & 0x8000) != 0, fue = g_ht_antes[vk];
    g_ht_antes[vk] = (BYTE)b;
    return b && !fue;
}

static BOOL CALLBACK ht_buscar_juego(HWND w, LPARAM lp)
{
    DWORD pid = 0;
    GetWindowThreadProcessId(w, &pid);
    if (pid == GetCurrentProcessId() && w != g_ht_ven && w != g_ht_globo && IsWindowVisible(w) && !GetWindow(w, GW_OWNER)) {
        *(HWND *)lp = w;
        return FALSE;
    }
    return TRUE;
}

static HWND ht_ventana_juego(void)
{
    if (g_ventana && IsWindow(g_ventana)) return g_ventana;
    HWND w = NULL;
    EnumWindows(ht_buscar_juego, (LPARAM)&w);
    return w;
}

/* que no quede afuera de la pantalla (otra resolución, otro monitor) */
static void ht_acomodar(void)
{
    RECT r;
    MONITORINFO mi;
    if (!GetWindowRect(g_ht_ven, &r)) return;
    mi.cbSize = sizeof(mi);
    if (!GetMonitorInfoW(MonitorFromRect(&r, MONITOR_DEFAULTTONEAREST), &mi)) return;
    int w = r.right - r.left, h = r.bottom - r.top, x = r.left, y = r.top;
    if (x + w > mi.rcWork.right) x = mi.rcWork.right - w;
    if (y + h > mi.rcWork.bottom) y = mi.rcWork.bottom - h;
    if (x < mi.rcWork.left) x = mi.rcWork.left;
    if (y < mi.rcWork.top) y = mi.rcWork.top;
    if (x != r.left || y != r.top) SetWindowPos(g_ht_ven, NULL, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
}

/* rehace la maqueta (fábrica + archivo de disposición) y, si cambió el tamaño, la ventana */
static void ht_rehacer(void)
{
    int w0 = g_ht_w, h0 = g_ht_h;
    ht_maquetar_todo();
    g_ht_hover = -1;
    if (w0 != g_ht_w || h0 != g_ht_h) {
        if (g_ht_dc2) {
            DeleteDC(g_ht_dc2); DeleteDC(g_ht_dc1);
            DeleteObject(g_ht_bm2); DeleteObject(g_ht_bm1);
            g_ht_dc2 = g_ht_dc1 = NULL;
        }
        if (g_ht_ven) SetWindowPos(g_ht_ven, NULL, 0, 0, g_ht_w, g_ht_h, SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
    ht_refrescar();
}

static void ht_cancelar_espera(const wchar_t *por)
{
    if (g_ht_esperando < 0) return;
    g_ht_esperando = -1;
    if (por) ht_avisar(HT_C_GRIS, 2500, L"%s", por);
    ht_refrescar();
}

static void ht_mostrar(int si)
{
    if (!g_ht_ven) return;
    if (si) {
        ht_rehacer();                               /* ★ relee la disposición: se acomoda con el juego abierto */
        ht_acomodar();
        ShowWindow(g_ht_ven, SW_SHOWNOACTIVATE);
        SetWindowPos(g_ht_ven, g_op[O_ANCLAR].quiere ? HWND_TOPMOST : HWND_TOP, 0, 0, 0, 0,
                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER);
    } else {
        ht_cancelar_espera(NULL);
        ht_globo_ocultar();
        ShowWindow(g_ht_ven, SW_HIDE);
    }
}

static void ht_tick(void)
{
    int foco = ht_con_foco();
    int f12 = ht_recien(g_ht_tecla_ver);
    /* esperando una tecla: F12 se ASIGNA (y se rechaza con su motivo), no esconde la ventana */
    if (f12 && foco && !g_ht_apagada && g_ht_esperando < 0) ht_mostrar(!IsWindowVisible(g_ht_ven));
    if (g_ht_mostrar_pedido) { g_ht_mostrar_pedido = 0; ht_mostrar(1); }

    /* ⛔⛔ 03-oct, primera prueba de anonimo03: «no abre». La ventana EXISTÍA y estaba VISIBLE
     *   (medido con EnumWindows: `R2beatTool` en 24,64), pero DETRÁS del juego: los dos son
     *   ventanas normales y el juego, a 1920x1080, sube al frente en cuanto se lo toca.
     *   ⇒ Mientras el juego (o la tool) tenga el foco, la tool va SIEMPRE ENCIMA; si el jugador
     *     se va a otro programa, deja de estar encima (salvo «Anclar»).
     * ⛔⛔ 04-oct, anonimo03: «no veo la tool» — OTRA VEZ detrás. El globito de ayuda (`g_ht_globo`) es
     *   una ventana TOPMOST cuyo DUEÑO es la tool; con eso, SetWindowPos(HWND_TOPMOST) sobre la tool
     *   devuelve «ok» y NO la sube (medido en el juego vivo: el bit no se prende ni un instante).
     *   Con SWP_NOOWNERZORDER sí. ⇒ todos los cambios de orden de la tool lo llevan. */
    if (g_ht_ven && IsWindowVisible(g_ht_ven)) {
        int arriba = g_op[O_ANCLAR].quiere || foco;
        int es_top = (GetWindowLongW(g_ht_ven, GWL_EXSTYLE) & WS_EX_TOPMOST) != 0;
        if (arriba != es_top)
            SetWindowPos(g_ht_ven, arriba ? HWND_TOPMOST : HWND_NOTOPMOST, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER);
    }

    /* la primera vez que aparece el juego, la tool se muestra sola (sin robarle el foco) */
    if (g_ht_visto_juego >= 0) {
        HWND j = ht_ventana_juego();
        if (j && IsWindowVisible(j)) g_ht_visto_juego += 50; else g_ht_visto_juego = 0;
        if (g_ht_visto_juego >= 2500) {
            g_ht_visto_juego = -1;
            if (GetPrivateProfileIntA("herramienta", "ver_al_arrancar", 1, g_ht_ini) && !g_ht_apagada) {
                RECT r;
                int x = (int)GetPrivateProfileIntA("herramienta", "x", -32000, g_ht_ini);
                int y = (int)GetPrivateProfileIntA("herramienta", "y", -32000, g_ht_ini);
                if ((x == -32000 || y == -32000) && GetWindowRect(j, &r)) { x = r.left + 24; y = r.top + 64; }
                if (x != -32000 && y != -32000)
                    SetWindowPos(g_ht_ven, NULL, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
                ht_mostrar(1);
            }
        }
    }

    /* el informe de las estrellas (con y sin corazón) sale al TERMINAR cada carrera */
    {
        int c = ht_en_carrera();
        if (c != g_ht_era_carrera) {
            if (!c) ht_cerrar_carrera();
            g_ht_era_carrera = c;
        }
    }
    /* far: si el juego todavía no había armado sus valores, reintentar */
    if (g_op[O_FAR].quiere && !g_op[O_FAR].puesta) ht_far_aplicar();

    /* los atajos (con «Hotkey» marcado, con el foco en el juego, sin estar escribiendo y sin
     * estar asignando una tecla). ⚠ Los flancos se leen SIEMPRE: así una tecla que se estaba
     * apretando al prender los atajos no se dispara sola. */
    int sirve = g_op[O_HOTKEYS].quiere && foco && !g_ht_apagada && !ht_escribiendo() && g_ht_esperando < 0;
    for (int i = 0; i < O_N; i++)
        if (g_op[i].con_tecla && g_op[i].tecla && ht_recien(g_op[i].tecla) && sirve)
            ht_cambiar(i, !g_op[i].quiere);
    int far_m = ht_recien(g_ht_tk_far_menos), far_p = ht_recien(g_ht_tk_far_mas);
    int alf_m = ht_recien(g_ht_tk_alfa_menos), alf_p = ht_recien(g_ht_tk_alfa_mas);
    if (sirve && (far_m || far_p) && g_op[O_FAR].quiere) {
        g_ht_far_pct += far_p ? 10 : -10;
        if (g_ht_far_pct < 50) g_ht_far_pct = 50;
        if (g_ht_far_pct > 300) g_ht_far_pct = 300;
        ht_far_aplicar(); ht_refrescar(); ht_pedir_guardar();
    }
    if (sirve && (alf_m || alf_p) && g_op[O_OPACIDAD].quiere) {
        g_ht_alfa_nivel += alf_p ? 1 : -1;
        if (g_ht_alfa_nivel < 1) g_ht_alfa_nivel = 1;
        if (g_ht_alfa_nivel > 15) g_ht_alfa_nivel = 15;
        ht_alfa_aplicar(); ht_refrescar(); ht_pedir_guardar();
    }
    if (g_ht_aviso[0] && g_ht_aviso_hasta && (int)(GetTickCount() - g_ht_aviso_hasta) >= 0) {
        g_ht_aviso[0] = 0;
        ht_refrescar();
    }
    if (g_ht_guardar_en && (int)(GetTickCount() - (DWORD)g_ht_guardar_en) >= 0) { g_ht_guardar_en = 0; ht_guardar(); }
}

/* ── 7.7 · el mouse y el teclado de la ventana ──────────────────────────────── */
static int ht_donde(int x, int y)
{
    for (int i = g_nel - 1; i >= 0; i--) {
        HT_EL *e = &g_el[i];
        if (e->tipo == E_VALOR || e->tipo == E_TITULO || e->tipo == E_AVISO || e->oculto) continue;
        if (e->tipo == E_PILL && e->ref == O_HOTKEYS) continue;   /* el aviso verde: ni clic ni globito */
        if (x >= e->x && x < e->x + e->w && y >= e->y && y < e->y + e->h) return i;
    }
    return -1;
}

static int ht_el_vivo(int i)
{
    HT_EL *e = &g_el[i];
    switch (e->tipo) {
    case E_OPCION: case E_PILL: return g_op[e->ref].permitida && !g_op[e->ref].rota;
    case E_TECLA: return ht_tecla_viva(e->ref);
    case E_SLIDER: { int o = e->ref ? O_FAR : O_OPACIDAD; return g_op[o].permitida && !g_op[o].rota; }
    case E_BOTON: return e->ref != 2 || !g_op[O_TECLADO].rota;
    case E_CERRAR: return 1;
    }
    return 0;
}

static void ht_slider_a(int i, int mx)
{
    HT_EL *e = &g_el[i];
    int mn, mxv, x0 = e->x + 8, x1 = e->x + e->w - 8;
    ht_slider_valor(e->ref, &mn, &mxv);
    int v = mn + ((mx - x0) * (mxv - mn) + (x1 - x0) / 2) / (x1 - x0);
    if (v < mn) v = mn;
    if (v > mxv) v = mxv;
    if (e->ref == 0) { if (v == g_ht_alfa_nivel) return; g_ht_alfa_nivel = v; ht_alfa_aplicar(); }
    else { if (v * 5 == g_ht_far_pct) return; g_ht_far_pct = v * 5; ht_far_aplicar(); }
    ht_refrescar();
    ht_pedir_guardar();
}

static void ht_teclado_de_fabrica(void)
{
    for (int g = 0; g < 2; g++) for (int k = 0; k < 5; k++) g_ht_kb[g][k] = HT_KB_FABRICA[g][k];
    ht_avisar(HT_C_CELESTE, 3000, L"Teclado de juego: de fábrica (W A S D LCtrl · ↑ ← ↓ → RCtrl)");
    if (g_op[O_TECLADO].puesta) ht_teclado_log(1);
    ht_pedir_guardar();
}

/* la tecla que se apretó con un botoncito esperando */
static void ht_tecla_apretada(int vk, int sc, int ext)
{
    int id = g_ht_esperando;
    wchar_t que[64], n[32], por[200];
    if (id < 0) return;
    ht_que_es(id, que);
    if (vk == VK_ESCAPE) { ht_cancelar_espera(L"Cancelado: queda la tecla que estaba"); return; }
    int valor;
    if (ht_es_dik(id)) {
        valor = (sc & 0x7F) | (ext ? 0x80 : 0);
        if (vk == VK_PAUSE) valor = 0xC5;
        if (vk == VK_NUMLOCK) valor = 0x45;
    } else {
        valor = vk;
        /* Ctrl / Shift / Alt llegan sin lado: el lado lo dice el scan code (sólo para el nombre) */
        if (vk == VK_SHIFT) valor = sc == 0x36 ? VK_RSHIFT : VK_LSHIFT;
        if (vk == VK_CONTROL) valor = ext ? VK_RCONTROL : VK_LCONTROL;
        if (vk == VK_MENU) valor = ext ? VK_RMENU : VK_LMENU;
    }
    if (!valor) return;
    wchar_t saco[64];
    ht_bloqueada(id, valor, por);                     /* ★ 16-oct: ya no bloquea, sólo la nota */
    ht_soltar_repetida(id, valor, saco);
    *ht_tecla_de(id) = valor;
    if (!ht_es_dik(id)) g_ht_antes[valor & 0xFF] = 1;  /* que no se dispare con la tecla de recién */
    g_ht_esperando = -1;
    ht_nombre_tecla(id, valor, n);
    if (saco[0])                                      /* ★ 16-oct: se la sacó a otra pieza de la tool */
        ht_avisar(HT_C_ROSA, 6000, L"«%s» = %s · se la saqué a «%s»%s%s", que, n, saco, por[0] ? L" · " : L"", por);
    else if (por[0])                                  /* también la usa otra cosa: se avisa, no se bloquea */
        ht_avisar(HT_C_ROSA, 6000, L"«%s» = %s · %s", que, n, por);
    else
        ht_avisar(HT_C_CELESTE, 3500, L"«%s» = %s%s", que, n,
                  ht_es_dik(id) ? (g_op[O_TECLADO].quiere ? L"" : L" · prendé «Configuración de Teclado» para usarla")
                                : (g_op[O_HOTKEYS].quiere ? L"" : L" · prendé ATAJOS para usarla"));
    if (ht_es_dik(id) && g_op[O_TECLADO].puesta) ht_teclado_log(1);
    ht_pedir_guardar();
}

static void ht_tema_poner(int n);
static void ht_clic(int i, int x)
{
    HT_EL *e = &g_el[i];
    if (!ht_el_vivo(i)) return;
    switch (e->tipo) {
    case E_OPCION: case E_PILL:
        ht_cambiar(e->ref, !g_op[e->ref].quiere);
        break;
    case E_TECLA: {
        wchar_t que[64];
        if (g_ht_esperando == e->ref) { ht_cancelar_espera(L"Cancelado"); break; }
        g_ht_esperando = e->ref;
        ht_que_es(e->ref, que);
        SetFocus(g_ht_ven);
        ht_avisar(HT_C_ROSA, 0, L"Apretá la tecla para «%s» · Esc cancela · clic derecho la borra", que);
        break;
    }
    case E_SLIDER:
        g_ht_arrastre = i;
        SetCapture(g_ht_ven);
        ht_slider_a(i, x);
        break;
    case E_BOTON:
        if (e->ref == 1) { ht_apagar_todo(); ht_avisar(HT_C_CELESTE, 3000, L"Todo apagado: el juego quedó de fábrica"); }
        else if (e->ref == 3) {
            ht_tema_poner(g_ht_tema % 4 + 1);
            ht_avisar(HT_C_CELESTE, 3000, L"Tema %d: %s (queda guardado en el ini)", g_ht_tema, g_tm->nombre);
            ht_pedir_guardar();
        }
        else ht_teclado_de_fabrica();
        break;
    case E_CERRAR:
        ht_mostrar(0);
        break;
    }
    ht_refrescar();
}

static LRESULT CALLBACK ht_wndproc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    switch (m) {
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        ht_pintar(dc);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_PRINTCLIENT:
        ht_pintar((HDC)wp);
        return 0;
    case WM_ERASEBKGND:
        return 1;
    case WM_NCLBUTTONDBLCLK:
        return 0;                                    /* doble clic en la cabecera: nada (no maximizar) */
    case WM_NCHITTEST: {
        POINT p = { (short)LOWORD(lp), (short)HIWORD(lp) };
        ScreenToClient(h, &p);
        if (p.y < 52 && ht_donde(p.x, p.y) < 0) return HTCAPTION;      /* la cabecera arrastra */
        return HTCLIENT;
    }
    case WM_SETCURSOR:
        if (LOWORD(lp) == HTCLIENT && g_ht_hover >= 0 && ht_el_vivo(g_ht_hover)) {
            SetCursor(LoadCursorW(NULL, (LPCWSTR)IDC_HAND));
            return TRUE;
        }
        break;
    case WM_MOUSEMOVE: {
        int x = (short)LOWORD(lp), y = (short)HIWORD(lp);
        if (g_ht_arrastre >= 0) { ht_slider_a(g_ht_arrastre, x); return 0; }
        int i = ht_donde(x, y);
        if (i != g_ht_hover) {
            TRACKMOUSEEVENT t = { sizeof(t), TME_LEAVE, h, 0 };
            TrackMouseEvent(&t);
            g_ht_hover = i;
            ht_globo_ocultar();
            KillTimer(h, 2);
            /* ★ 04-oct, anonimo03: sin los globitos de ayuda al pasar el mouse (el globo queda armado, sin usar) */
            ht_refrescar();
        }
        return 0;
    }
    case WM_MOUSELEAVE:
        g_ht_hover = -1;
        KillTimer(h, 2);
        ht_globo_ocultar();
        ht_refrescar();
        return 0;
    case WM_LBUTTONDOWN: {
        int x = (short)LOWORD(lp), y = (short)HIWORD(lp), i = ht_donde(x, y);
        ht_globo_ocultar();
        KillTimer(h, 2);
        if (g_ht_esperando >= 0 && (i < 0 || g_el[i].tipo != E_TECLA))
            ht_cancelar_espera(L"Cancelado: queda la tecla que estaba");
        if (i >= 0) ht_clic(i, x);
        return 0;
    }
    case WM_LBUTTONUP:
        if (g_ht_arrastre >= 0) { g_ht_arrastre = -1; ReleaseCapture(); ht_refrescar(); }
        return 0;
    case WM_RBUTTONDOWN: {
        int i = ht_donde((short)LOWORD(lp), (short)HIWORD(lp));
        if (i >= 0 && g_el[i].tipo == E_TECLA && ht_el_vivo(i)) {
            wchar_t que[64];
            int *p = ht_tecla_de(g_el[i].ref);
            ht_que_es(g_el[i].ref, que);
            if (p) *p = 0;
            if (g_ht_esperando == g_el[i].ref) g_ht_esperando = -1;
            ht_avisar(HT_C_CELESTE, 3000, L"«%s»: sin tecla", que);
            if (ht_es_dik(g_el[i].ref) && g_op[O_TECLADO].puesta) ht_teclado_log(1);
            ht_pedir_guardar();
        }
        return 0;
    }
    case WM_MOUSEWHEEL: {
        POINT p = { (short)LOWORD(lp), (short)HIWORD(lp) };
        ScreenToClient(h, &p);
        int i = ht_donde(p.x, p.y);
        if (i >= 0 && g_el[i].tipo == E_SLIDER && ht_el_vivo(i)) {
            int paso = GET_WHEEL_DELTA_WPARAM(wp) > 0 ? 1 : -1;
            if (g_el[i].ref == 0) {
                int v = g_ht_alfa_nivel + paso;
                if (v >= 1 && v <= 15) { g_ht_alfa_nivel = v; ht_alfa_aplicar(); }
            } else {
                int v = g_ht_far_pct + 5 * paso;
                if (v >= 50 && v <= 300) { g_ht_far_pct = v; ht_far_aplicar(); }
            }
            ht_refrescar();
            ht_pedir_guardar();
        }
        return 0;
    }
    case WM_KEYDOWN: case WM_SYSKEYDOWN:
        if (g_ht_esperando >= 0) {
            ht_tecla_apretada((int)wp, (int)((lp >> 16) & 0xFF), (int)((lp >> 24) & 1));
            ht_refrescar();
            return 0;
        }
        break;
    case WM_CHAR: case WM_SYSCHAR:
        if (g_ht_esperando >= 0) return 0;              /* que no suene ni abra menús */
        break;
    case WM_ACTIVATE:
        if (LOWORD(wp) == WA_INACTIVE) ht_cancelar_espera(NULL);
        break;
    case WM_TIMER:
        if (wp == 2) { KillTimer(h, 2); ht_globo_mostrar(g_ht_hover); return 0; }
        ht_tick();
        return 0;
    case WM_HT_MOSTRAR:
        g_ht_apagada = 0;
        for (int i = 0; i < O_N; i++) ht_aplicar(i);
        ht_refrescar();
        ht_mostrar(1);
        return 0;
    case WM_HT_APAGAR:
        /* el launcher la apagó: se sacan los parches (sin olvidar lo elegido) y se esconde */
        g_ht_apagada = 1;
        for (int i = 0; i < O_N; i++) ht_aplicar(i);
        ht_mostrar(0);
        apuntar("  [tool] apagada desde el launcher: parches sacados, ventana oculta");
        return 0;
    case WM_EXITSIZEMOVE:
        ht_pedir_guardar();
        return 0;
    case WM_CLOSE:
        ht_mostrar(0);                              /* Alt+F4 esconde; F12 la vuelve a mostrar */
        return 0;
    }
    return DefWindowProcW(h, m, wp, lp);
}

static void ht_fuentes(void)
{
    const wchar_t *l = g_tm->letra;
    if (g_ht_dc1) SelectObject(g_ht_dc1, GetStockObject(SYSTEM_FONT));
    for (int i = 0; i < F_N; i++) if (g_ht_f[i]) { DeleteObject(g_ht_f[i]); g_ht_f[i] = NULL; }
    g_ht_f[F_TEXTO]  = CreateFontW(-g_tm->tam_texto, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, l);
    g_ht_f[F_CHICO]  = CreateFontW(-11, 0, 0, 0, FW_NORMAL,   0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, l);
    g_ht_f[F_TITULO] = CreateFontW(-g_tm->tam_titulo, 0, 0, 0, g_tm->peso_titulo, 0, 0, 0, DEFAULT_CHARSET, 0, 0,
                                   CLEARTYPE_QUALITY, 0, g_tm->letra_titulo);
    g_ht_f[F_CARTA]  = CreateFontW(-11, 0, 0, 0, FW_BOLD,     0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, l);
    g_ht_f[F_CHIP]   = CreateFontW(-g_tm->tam_chip, 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, l);
    g_ht_f[F_PILL]   = CreateFontW(-11, 0, 0, 0, FW_BOLD,     0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, l);
}

/* Windows 11: esquinas (redondas o rectas, según el tema) y el borde del color del tema (en el 10, nada) */
static void ht_dwm(void)
{
    typedef HRESULT (WINAPI *HT_DWMSET)(HWND, DWORD, LPCVOID, DWORD);
    static HT_DWMSET f = NULL;
    static int buscado = 0;
    if (!buscado) {
        HMODULE dm = LoadLibraryA("dwmapi.dll");
        f = dm ? (HT_DWMSET)(void *)GetProcAddress(dm, "DwmSetWindowAttribute") : NULL;
        buscado = 1;
    }
    if (!f || !g_ht_ven) return;
    DWORD esquina = g_tm->radio ? 2 /* DWMWCP_ROUND */ : 1 /* DWMWCP_DONOTROUND */, borde = HT_C_BORDE;
    f(g_ht_ven, 33 /* DWMWA_WINDOW_CORNER_PREFERENCE */, &esquina, sizeof(esquina));
    f(g_ht_ven, 34 /* DWMWA_BORDER_COLOR */, &borde, sizeof(borde));
}

/* cambiar de tema EN VIVO (el botón TEMA): fuentes, maqueta (la densidad cambia el alto) y capas */
static void ht_tema_poner(int n)
{
    if (n < 1 || n > 4) n = 1;
    g_ht_tema = n;
    g_tm = &HT_TEMAS[n - 1];
    if (!g_ht_ven) return;
    ht_globo_ocultar();
    ht_fuentes();
    ht_rehacer();
    ht_dwm();
    if (IsWindowVisible(g_ht_ven)) ht_acomodar();
    ht_refrescar();
}

static void ht_armar_ventana(void)
{
    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.style = CS_DROPSHADOW;
    wc.lpfnWndProc = ht_wndproc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    wc.lpszClassName = L"R2beatTool";
    RegisterClassExW(&wc);
    wc.style = CS_DROPSHADOW;
    wc.lpfnWndProc = ht_globo_proc;
    wc.lpszClassName = L"R2beatToolAyuda";
    RegisterClassExW(&wc);

    g_tm = &HT_TEMAS[(g_ht_tema >= 1 && g_ht_tema <= 4 ? g_ht_tema : 1) - 1];
    ht_fuentes();
    {
        wchar_t n[32];
        ht_nombre_vk(g_ht_tecla_ver, n);
        wsprintfW(g_ht_sub, L"%s · mostrar / ocultar", n);
    }
    ht_maquetar_todo();

    DWORD est = WS_POPUP | WS_CLIPCHILDREN;
    DWORD estx = WS_EX_TOOLWINDOW | (g_op[O_ANCLAR].quiere ? WS_EX_TOPMOST : 0);
    g_ht_ven = CreateWindowExW(estx, L"R2beatTool", L"R2beat tool", est, 80, 80,
                               g_ht_w, g_ht_h, NULL, NULL, wc.hInstance, NULL);
    if (!g_ht_ven) { apuntar("  [tool] ⛔ no pude crear la ventana (%u)", (unsigned)GetLastError()); return; }
    g_ht_globo = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE, L"R2beatToolAyuda", L"",
                                 WS_POPUP, 0, 0, 10, 10, g_ht_ven, NULL, wc.hInstance, NULL);
    ht_dwm();
    ht_refrescar();
    SetTimer(g_ht_ven, 1, 50, NULL);
}

static DWORD WINAPI ht_hilo_ventana(void *p)
{
    (void)p;
    ht_armar_ventana();
    if (!g_ht_ven) return 0;
    MSG m;
    while (GetMessageW(&m, NULL, 0, 0) > 0) {
        TranslateMessage(&m);
        DispatchMessageW(&m);
    }
    return 0;
}

/* ═══ 8 · ARRANCAR / EL AVISO DEL LAUNCHER ═══════════════════════════════════ */
static void ht_arrancar(int mostrar)
{
    if (mostrar) g_ht_mostrar_pedido = 1;
    if (InterlockedExchange(&g_ht_arrancada, 1)) {
        if (mostrar && g_ht_ven) PostMessageW(g_ht_ven, WM_HT_MOSTRAR, 0, 0);
        return;
    }
    ht_leer();
    ht_poner_ganchos();
    for (int i = 0; i < O_N; i++) ht_aplicar(i);
    HANDLE t = CreateThread(NULL, 0, ht_hilo_ventana, NULL, 0, NULL);
    if (t) CloseHandle(t);
    int n = 0;
    for (int i = 0; i < O_N; i++) if (g_op[i].quiere) n++;
    apuntar("  [tool] ★ R2beat tool cargada: ganchos notas=%d espejo=%d · %d opción(es) del ini · F%d ver/ocultar",
            g_ht_gancho_notas, g_ht_gancho_espejo, n, g_ht_tecla_ver - VK_F1 + 1);
}

static DWORD WINAPI ht_hilo_aviso(void *p)
{
    (void)p;
    for (;;) {
        if (WaitForSingleObject(g_ht_evento, INFINITE) != WAIT_OBJECT_0) return 0;
        int activo = (int)GetPrivateProfileIntA("herramienta", "activo", 0, g_ht_ini);
        apuntar("  [tool] el launcher avisa: activo=%d", activo);
        if (activo) {
            if (g_ht_arrancada) {
                if (g_ht_ven) PostMessageW(g_ht_ven, WM_HT_MOSTRAR, 0, 0);
                else g_ht_mostrar_pedido = 1;
            } else ht_arrancar(1);
        } else if (g_ht_ven) PostMessageW(g_ht_ven, WM_HT_APAGAR, 0, 0);
    }
}

/* Se llama desde DllMain: el exe ya está mapeado y su bucle todavía no arrancó. */
static void herramienta_iniciar(void)
{
    g_ht_base = (BYTE *)GetModuleHandleA(NULL);
    if (!g_ht_base || !g_carpeta[0]) return;
    lstrcpyA(g_ht_ini, g_carpeta);
    lstrcatA(g_ht_ini, "d3d9_proxy.ini");
    InitializeCriticalSection(&g_ht_cs);
    g_ht_hilo_juego = GetCurrentThreadId();
    /* ⚠ sólo si existen en este exe (con otro, el gancho de las notas no se pone igual) */
    if (ht_memoria_ok(HT_VA(HT_F_MODELO), 16, 0) && ht_memoria_ok(HT_VA(HT_TABLA_MOD), 4, 0)) {
        g_ht_f_modelo = (HT_FMODELO)HT_VA(HT_F_MODELO);
        g_ht_tabla_mod = (void **)HT_VA(HT_TABLA_MOD);
    }      /* el que carga la dll; lo corrige el gancho */

    /* el aviso del launcher: SIEMPRE, aunque hoy esté apagada (así se puede prender en vivo) */
    wchar_t nombre[64];
    wsprintfW(nombre, L"Local\\R2beatTool.%lu", (unsigned long)GetCurrentProcessId());
    g_ht_evento = CreateEventW(NULL, FALSE, FALSE, nombre);
    if (g_ht_evento) {
        HANDLE t = CreateThread(NULL, 0, ht_hilo_aviso, NULL, 0, NULL);
        if (t) CloseHandle(t);
    }
    if (GetPrivateProfileIntA("herramienta", "activo", 0, g_ht_ini)) ht_arrancar(0);
    else apuntar("  [tool] apagada ([herramienta] activo=0) · el launcher la puede prender en vivo");
}
