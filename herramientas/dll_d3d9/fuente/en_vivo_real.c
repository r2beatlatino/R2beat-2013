/* ═══════════════════════════════════════════════════════════════════════════
 * en_vivo_real.c — EL EN VIVO REAL: las fallas de los rivales se ven como fueron (26-nov-2026)
 *
 *   El pedido (Eñeños): «el otro server logró un en vivo real y el nuestro aún tenía carencias» → y después: «que se
 *   vea en vivo para todos, en todos los modos». Medido en el server de prueba local, con el cliente 1 a 1
 *   (documentacion/ESPECTADOR_COMO_LO_HACE_RBIT.md §6-§7, repo «Servidor R2Beat 2013»):
 *     · a los RIVALES (en el que mira y en los que corren) el juego los lleva en PILOTO: la rutina de rivales
 *       0x5080B0 juzga cada nota suya con el juez 0x505340 desde 0x5081EF, SIEMPRE con juicio 0 (acierto). Las
 *       fallas reales no viajan: el combo del rival no se corta nunca, no hay MISS.
 *     · el choque (la animación) SÍ viaja: el corredor manda un FF4E sub 0 (A = id de animación << 24 | asiento << 16).
 *     · el que mira juzga cada nota ~14 ms ANTES que el corredor ⇒ el juicio real llega SIEMPRE tarde (el ping).
 *
 *   Lo que hace (idea de RBit, código nuestro):
 *     1 · EL QUE CORRE: cada nota SUYA que no es acierto (juicio ≠ 0) la avisa por el FF4E con un sub nuestro, 0x73:
 *           A = 'J' << 24 | asiento << 16 | clave (16 bits)       clave = *(u32)(nota + 0x14) (el tiempo de la nota
 *           B = juicio | desvío << 8 | combo << 16                   en el chart ×3: el mismo en todos los clientes)
 *     2 · EL SERVER lo reenvía a TODA la sala (los que corren y los que miran).
 *     3 · CADA CLIENTE, para cada rival:
 *           · si el aviso llegó ANTES de que su piloto juzgue esa nota → le cambia el juicio en el juez (el juego corta
 *             el combo y hace lo suyo: medido, 91/91 cortes);
 *           · si llegó TARDE (lo normal) → le pone el combo real (el del aviso + los aciertos que el piloto contó
 *             después), sin volver a juzgar la nota (no se cuenta dos veces en el PD).
 *
 *   Se engancha en el juez de calculadora.c (g_calc_antes_juicio / g_calc_despues_juicio), manda desde gc_jugador y
 *   recibe en gc_ff4e (globo_combo.c).
 *
 *   ★ PERILLAS en d3d9_proxy.ini (Eñeños: «igual para todos + que sea una opción prendible/apagable en la dll»):
 *       [en_vivo_real]
 *       activo=1        0 = TODO apagado (ni manda, ni corrige, ni dibuja): el juego queda como de fábrica
 *       globos=1        el globo del combo sobre CADA rival, también para los que corren y en todos los modos
 *       pd_tarjetas=1   el PD (96.524%) en la tarjeta de cada corredor
 *       log=0           1 = evr_<pid>.txt con los contadores, cada 3 s · 2 = y evr_rastro_<pid>.txt (el globo, cada 100 ms)
 *     El que mira y los que corren usan el MISMO mecanismo (sin atraso): la falla llega con el ping (~200 ms medido).
 *   ⚠ Se INCLUYE desde d3d9_proxy.c después de globo_combo.c. No se compila suelta.
 * ═══════════════════════════════════════════════════════════════════════════ */

#define EVR_SUB 0x73
#define EVR_FIRMA 0x4Au                                 /* 'J' en el byte alto de A */
#define EVR_N 64                                        /* por asiento: lo que se recuerda */
static int g_evr_n_pil_total = 0;
#define EVR_VIGENCIA 4000                               /* ms que espera un aviso a que el piloto llegue a esa nota */

static int g_evr_activo = 0, g_evr_log = 0;

/* ★ 26-nov · EL GLOBO DE CADA RIVAL, PARA LOS QUE CORREN: el combo del rival que lleva el piloto no sirve (medido: no se
 *   corta y se traba en ~40). Se arma acá, por asiento: +1 con cada nota que juzga su piloto, el real con cada falla que
 *   llega (0x73), y un PUNTO DE CONTROL cada EVR_CONTROL_CADA ms (el mismo 0x73 con juicio 0: «mi última nota y mi
 *   combo») para que no se descuadre aunque no haya fallas. */
#define EVR_CONTROL_CADA 500
/* ★ medido 26-nov: cuando el corredor CHOCA, las notas que pasan mientras está en el piso NO se juzgan (ni acierto ni
 *   falla: no sale ningún aviso) y el piloto del rival las sigue contando (+1 cada una) → el globo decía 6-16 con el real
 *   en 0. Por eso el punto de control sale SIEMPRE cada EVR_CONTROL_CADA ms: si llega con la MISMA última nota que el
 *   anterior, ese corredor no está juzgando → el globo queda QUIETO en su combo real hasta que vuelva a juzgar. */
static int g_evr_parado[16], g_evr_ctl_ultima[16];
static int g_evr_globos = 1;
static int g_evr_combo[16];
static DWORD g_evr_combo_t[16];                         /* cuándo se movió (0 = sin datos) */
static WORD g_evr_mi_clave = 0;
static int g_evr_mi_combo = 0, g_evr_mi_hay = 0, g_evr_ctl_clave = -1;
static DWORD g_evr_ctl_t = 0;
/* ★ 26-nov (tanda de modos): en el RELEVO, el que terminó su tramo seguía mandando el punto de control con su último
 *   combo (4) y los demás le veían el globo vivo y viejo, mientras su juego ya mostraba el del equipo (333). En el relevo,
 *   sin juzgar una nota propia en EVR_RELEVO_CALLA ms, se deja de mandar: el globo se apaga solo (choques más cortos que
 *   eso siguen quietos como siempre). */
#define EVR_RELEVO_CALLA 2000
static DWORD g_evr_mi_t = 0;                            /* cuándo juzgué mi última nota */
static int g_evr_n_ctl = 0, g_evr_n_ctl_rec = 0, g_evr_n_cortes = 0;

/* ★ 26-nov · EL PD EN CADA TARJETA (Eñeños: «si puedes dibujar su porcentaje 96.524 en cada tarjeta, sería hermoso»):
 *   cada corredor manda su PD (las notas y la suma de puntos que lleva calculadora.c) cada EVR_PD_CADA ms por el sub 0x74:
 *     A = 'P' << 24 | asiento << 16 | notas      B = suma de puntos (0..100 por nota)
 *   y cada cliente lo escribe junto a la tarjeta de ese corredor (0x55A9C0, la columna de la izquierda en carrera). */
#define EVR_SUB_PD 0x74
#define EVR_FIRMA_PD 0x50u                              /* 'P' */
#define EVR_PD_CADA 500
static int g_evr_pd = 1, g_evr_pd_dx = 102, g_evr_pd_dy = -1;
static DWORD g_evr_pd_color = 0xFFFFFFFF;
static int g_evr_pd_notas[16];
static DWORD g_evr_pd_suma[16], g_evr_pd_t[16];
static DWORD g_evr_pd_env_t = 0;
static int g_evr_pd_env_notas = -1;
typedef void (TCK *F_EVR_TARJETA)(void *hud, int puesto, int pos, int asiento);   /* 0x55A9C0, ret 0xC */
static F_EVR_TARJETA g_evr_tarjeta_real = NULL;
static BYTE *g_evr_obj[16];                             /* el corredor de cada asiento (lo anota gc_jugador) */
static BYTE *g_evr_juego = NULL;

/* lo que mandé y todavía no salió (el que corre) */
typedef struct { WORD clave; BYTE j; signed char d; WORD combo; } EVR_AVISO;
static EVR_AVISO g_evr_cola[32];
static unsigned g_evr_cola_i = 0, g_evr_cola_f = 0;

/* lo que llegó de cada rival y todavía no aplicó su piloto */
typedef struct { DWORD t; WORD clave; BYTE j; signed char d; WORD combo; BYTE vivo; } EVR_REAL;
static EVR_REAL g_evr_real[16][EVR_N];
static unsigned g_evr_real_f[16];

/* lo que ya juzgó el piloto de cada rival: la clave, en orden (para el aviso que llega tarde) */
static WORD g_evr_pil[16][EVR_N];
static unsigned g_evr_pil_f[16];

static void evr_informe(void);
static int g_evr_n_env = 0, g_evr_n_rec = 0, g_evr_n_a_tiempo = 0, g_evr_n_tarde = 0, g_evr_n_vencidos = 0;

static void evr_limpiar(void)
{
    ZeroMemory(g_evr_real, sizeof g_evr_real); ZeroMemory(g_evr_real_f, sizeof g_evr_real_f);
    ZeroMemory(g_evr_pil, sizeof g_evr_pil); ZeroMemory(g_evr_pil_f, sizeof g_evr_pil_f);
    ZeroMemory(g_evr_obj, sizeof g_evr_obj);
    g_evr_cola_i = g_evr_cola_f = 0;
    ZeroMemory(g_evr_pd_notas, sizeof g_evr_pd_notas); ZeroMemory(g_evr_pd_t, sizeof g_evr_pd_t);
    g_evr_pd_env_notas = -1;
    ZeroMemory(g_evr_combo, sizeof g_evr_combo); ZeroMemory(g_evr_combo_t, sizeof g_evr_combo_t);
    ZeroMemory(g_evr_parado, sizeof g_evr_parado);
    for (int i = 0; i < 16; i++) g_evr_ctl_ultima[i] = -1;
    g_evr_mi_hay = 0; g_evr_ctl_clave = -1;
}

/* la clave de la nota (el 3.er argumento del juez apunta a la nota). ⚠ NO se mira quién llamó al juez: con Frida, Ñ2Hock o
 *   ToolBit enganchados ahí, la dirección de vuelta es la de SU trampolín (medido 26-nov: el panel del QA la cambiaba). Se
 *   comprueba que el puntero se pueda leer; 0 = no es una nota. */
static int evr_clave(int extra, WORD *clave)
{
    if ((DWORD)extra < 0x10000 || (DWORD)extra >= 0x7FFF0000u || IsBadReadPtr((BYTE *)extra + 0x08, 0x10)) return 0;
    *clave = (WORD)(*(DWORD *)((BYTE *)extra + 0x14));
    return 1;
}

static void evr_poner_combo(BYTE *p, int c)             /* como gc_sembrar: el combo que se ve y su pareja */
{
    DWORD k = *(DWORD *)GCV(0x904210);
    if (c < 0) c = 0;
    *(DWORD *)(p + 0x190) = (DWORD)c ^ k;
    *(DWORD *)(p + 0x254) = (DWORD)c ^ k;
}

/* ═══ 1 · EL JUEZ (calculadora.c lo llama para TODOS los corredores) ═══════════════════════════════════════════════ */
static DWORD g_evr_vistas[8]; static int g_evr_n_vistas = 0;
static void evr_antes_juicio(BYTE *obj, int *juicio, int *desvio, int extra, DWORD vuelta)
{
    BYTE *g = gc_juego();
    {   int i; for (i = 0; i < g_evr_n_vistas && g_evr_vistas[i] != vuelta; i++) ;
        if (i == g_evr_n_vistas && g_evr_n_vistas < 8) g_evr_vistas[g_evr_n_vistas++] = vuelta; }
    if (!g_evr_activo || !g || !obj) return;
    int k = obj[0x49];
    if (k >= 16 || (!g[0xC01] && k == gc_mi_asiento())) return;          /* un RIVAL (para el que mira, todos) */
    WORD clave;
    if (!evr_clave(extra, &clave)) return;
    g_evr_pil[k][g_evr_pil_f[k]++ % EVR_N] = clave;      /* el piloto pasó por esta nota */
    g_evr_n_pil_total++;
    DWORD ahora = GetTickCount();
    int real = -1;                                      /* el combo real después de esta nota, si llegó a tiempo */
    for (int i = 0; i < EVR_N; i++) {
        EVR_REAL *r = &g_evr_real[k][i];
        if (!r->vivo || r->clave != clave) continue;
        r->vivo = 0;
        if (ahora - r->t > EVR_VIGENCIA) { g_evr_n_vencidos++; continue; }
        real = r->combo;
        if (r->j == 0) break;                           /* un punto de control: el piloto ya la da por acertada */
        *juicio = r->j;                                 /* ★ a tiempo: el juez del juego hace el resto */
        *desvio = r->d;
        g_evr_n_a_tiempo++;
        if (g_evr_log && g_evr_n_a_tiempo <= 5)
            apuntar("  [en_vivo_real] a tiempo: asiento %d nota %u juicio %d", k, (unsigned)clave, r->j);
        break;
    }
    /* el combo del globo: el real si llegó; si no, el piloto (+1, o 0 si la nota quedó como falla) */
    if (real >= 0 || !g_evr_parado[k])                  /* parado (chocado): el piloto no suma */
        g_evr_combo[k] = real >= 0 ? real : *juicio == 0 ? g_evr_combo[k] + 1 : 0;
    g_evr_combo_t[k] = ahora | 1;
}

static void evr_despues_juicio(BYTE *obj, int juicio, int desvio, int extra, DWORD vuelta)
{
    BYTE *g = gc_juego();
    (void)vuelta;
    if (!g_evr_activo || !g || !obj || g[0xC01]) return;
    if (obj[0x49] != gc_mi_asiento()) return;
    WORD clave;
    if (!evr_clave(extra, &clave)) return;
    g_evr_mi_clave = clave;                             /* para el punto de control */
    g_evr_mi_combo = gc_combo_de(obj);
    g_evr_mi_hay = 1;
    g_evr_mi_t = GetTickCount();
    if (juicio == 0) return;
    if (g_evr_cola_f - g_evr_cola_i >= 32) g_evr_cola_i++;            /* llena: se pierde la más vieja */
    EVR_AVISO *a = &g_evr_cola[g_evr_cola_f++ % 32];
    a->clave = clave;
    a->j = (BYTE)juicio;
    a->d = (signed char)(desvio < -128 ? -128 : desvio > 127 ? 127 : desvio);
    int c = g_evr_mi_combo;
    a->combo = (WORD)(c < 0 ? 0 : c > 0xFFFF ? 0xFFFF : c);
}

/* ═══ 2 · EL QUE CORRE MANDA (gc_jugador, en su corredor, cada cuadro) ═══════════════════════════════════════════ */
static void evr_mandar(void *red, BYTE *p)
{
    if (!g_evr_activo) return;
    F_GC_MANDAR mandar = (F_GC_MANDAR)GCV(0x5C7FB0);
    DWORD ahora = GetTickCount();
    if (g_evr_pd && g_calc_notas > 0 && g_calc_notas != g_evr_pd_env_notas && ahora - g_evr_pd_env_t >= EVR_PD_CADA) {
        mandar(red, EVR_SUB_PD, (EVR_FIRMA_PD << 24) | ((DWORD)p[0x49] << 16) | ((DWORD)g_calc_notas & 0xFFFF),
               (DWORD)g_calc_suma);
        g_evr_pd_env_notas = g_calc_notas;
        g_evr_pd_env_t = ahora;
    }
    /* el punto de control: «mi última nota y mi combo» (juicio 0), si me moví desde el anterior */
    BYTE *g = gc_juego();
    int calla = g && (*(WORD *)(g + 0xC) & 0x40) && ahora - g_evr_mi_t > EVR_RELEVO_CALLA;   /* relevo: no es mi tramo */
    if (g_evr_mi_hay && !calla && ahora - g_evr_ctl_t >= EVR_CONTROL_CADA) {      /* siempre (ver arriba) */
        int c = g_evr_mi_combo < 0 ? 0 : g_evr_mi_combo > 0xFFFF ? 0xFFFF : g_evr_mi_combo;
        mandar(red, EVR_SUB, (EVR_FIRMA << 24) | ((DWORD)p[0x49] << 16) | g_evr_mi_clave, (DWORD)c << 16);
        g_evr_ctl_clave = g_evr_mi_clave;
        g_evr_ctl_t = ahora;
        g_evr_n_ctl++;
    }
    for (int n = 0; n < 3 && g_evr_cola_i != g_evr_cola_f; n++) {     /* hasta 3 por cuadro: no hay ráfagas */
        EVR_AVISO *a = &g_evr_cola[g_evr_cola_i++ % 32];
        mandar(red, EVR_SUB, (EVR_FIRMA << 24) | ((DWORD)p[0x49] << 16) | a->clave,
               (DWORD)a->j | ((DWORD)(BYTE)a->d << 8) | ((DWORD)a->combo << 16));
        g_evr_n_env++;
        if (g_evr_log && g_evr_n_env <= 5)
            apuntar("  [en_vivo_real] mandé: nota %u juicio %d combo %u", (unsigned)a->clave, a->j, (unsigned)a->combo);
    }
}

/* gc_jugador lo llama por cada corredor y cada cuadro: el mapa asiento → corredor (para el aviso que llega tarde) */
static DWORD g_evr_t_diag = 0, g_evr_t_rastro = 0;
static HANDLE g_evr_rastro = INVALID_HANDLE_VALUE;
static int evr_globo(int k, int *combo, int *f);
static void evr_rastro(void)                            /* log=2: cada 100 ms, la hora (ms, como Date.now) y el globo de cada asiento */
{
    DWORD ahora = GetTickCount();
    if (g_evr_log < 2 || ahora - g_evr_t_rastro < 100) return;
    g_evr_t_rastro = ahora;
    if (g_evr_rastro == INVALID_HANDLE_VALUE) {
        char ruta[MAX_PATH];
        wsprintfA(ruta, "%sevr_rastro_%lu.txt", g_carpeta, (unsigned long)GetCurrentProcessId());
        g_evr_rastro = CreateFileA(ruta, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, 0, NULL);
        if (g_evr_rastro == INVALID_HANDLE_VALUE) { g_evr_log = 1; return; }
    }
    FILETIME ft;
    GetSystemTimeAsFileTime(&ft);
    unsigned long long ms = ((((unsigned long long)ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 10000ULL) - 11644473600000ULL;
    char t[320];                                        /* 12 asientos: la sala de 12 también se mide */
    int n = wsprintfA(t, "%lu", (unsigned long)(ms % 100000000ULL));
    for (int k = 0; k < 12; k++) {                      /* -1 = sin globo o ya apagado (lo que de verdad se ve) */
        int c, f;
        n += wsprintfA(t + n, " %d", evr_globo(k, &c, &f) && f > 0 ? c : -1);
    }
    for (int k = 0; k < 12; k++)                        /* y si el globo muestra el «BREAK» (1) */
        n += wsprintfA(t + n, " %d", g_gc_t_break[k] && GetTickCount() - g_gc_t_break[k] < GC_BREAK_MIN ? 1 : 0);
    t[n++] = 10;                                        /* fin de línea */
    DWORD e;
    WriteFile(g_evr_rastro, t, n, &e, NULL);
}
static void evr_diag(void)                              /* [en_vivo_real] log=1: evr_<pid>.txt con los contadores, cada 3 s */
{
    evr_rastro();
    DWORD ahora = GetTickCount();
    if (!g_evr_log || ahora - g_evr_t_diag < 3000) return;
    g_evr_t_diag = ahora;
    char ruta[MAX_PATH], t[768];
    wsprintfA(ruta, "%sevr_%lu.txt", g_carpeta, (unsigned long)GetCurrentProcessId());
    BYTE *g = gc_juego();
    int n = wsprintfA(t, "mi_asiento=%d espectador=%d mandados=%d recibidos=%d a_tiempo=%d tarde=%d vencidos=%d "
                      "piloto_total=%d pd_mandados=%d | piloto por asiento:",
                      gc_mi_asiento(), g ? g[0xC01] : -1, g_evr_n_env, g_evr_n_rec, g_evr_n_a_tiempo, g_evr_n_tarde,
                      g_evr_n_vencidos, g_evr_n_pil_total, g_evr_pd_env_notas);
    for (int k = 0; k < 6; k++) n += wsprintfA(t + n, " %u", g_evr_pil_f[k]);
    n += wsprintfA(t + n, " | vueltas:");
    for (int i = 0; i < g_evr_n_vistas; i++) n += wsprintfA(t + n, " %08lX", (unsigned long)g_evr_vistas[i]);
    n += wsprintfA(t + n, " | pd por asiento:");
    for (int k = 0; k < 6; k++) n += wsprintfA(t + n, " %d/%lu", g_evr_pd_notas[k], (unsigned long)g_evr_pd_suma[k]);
    n += wsprintfA(t + n, " | control mandados=%d recibidos=%d cortes=%d | globo por asiento:", g_evr_n_ctl, g_evr_n_ctl_rec, g_evr_n_cortes);
    for (int k = 0; k < 6; k++) n += wsprintfA(t + n, " %d", g_evr_combo_t[k] ? g_evr_combo[k] : -1);
    HANDLE f = CreateFileA(ruta, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, 0, NULL);
    if (f != INVALID_HANDLE_VALUE) { DWORD e; WriteFile(f, t, n, &e, NULL); CloseHandle(f); }
}

static void evr_ver_corredor(BYTE *p, BYTE *g)
{
    if (!g_evr_activo || !p || !g) return;
    evr_diag();
    if (g != g_evr_juego) { evr_informe(); g_evr_juego = g; evr_limpiar(); }
    if (p[0x49] < 16) g_evr_obj[p[0x49]] = p;
}

/* ═══ 3 · LLEGA EL AVISO DE UN RIVAL (gc_ff4e) ═══════════════════════════════════════════════════════════════════ */
static int evr_recibir(BYTE *g, int sub, DWORD a, DWORD b)
{
    if (sub == EVR_SUB_PD && (a >> 24) == EVR_FIRMA_PD) {
        int kp = (a >> 16) & 0xFF;
        if (g_evr_activo && kp < 16) { g_evr_pd_notas[kp] = (int)(a & 0xFFFF); g_evr_pd_suma[kp] = b; g_evr_pd_t[kp] = GetTickCount() | 1; }
        return 1;
    }
    if (sub != EVR_SUB || (a >> 24) != EVR_FIRMA) return 0;
    if (!g_evr_activo || !g) return 1;
    int k = (a >> 16) & 0xFF;
    if (k >= 16 || k == gc_mi_asiento()) return 1;
    WORD clave = (WORD)(a & 0xFFFF);
    BYTE j = (BYTE)(b & 0xFF);
    signed char d = (signed char)((b >> 8) & 0xFF);
    WORD combo = (WORD)(b >> 16);
    g_evr_n_rec++;
    /* ¿su piloto ya pasó por esa nota? (lo normal: el aviso llega tarde) */
    unsigned f = g_evr_pil_f[k], despues = 0;
    int ya = 0;
    for (unsigned i = 1; i <= EVR_N && i <= f; i++) {
        if (g_evr_pil[k][(f - i) % EVR_N] == clave) { ya = 1; despues = i - 1; break; }
    }
    if (j == 0) {
        g_evr_n_ctl_rec++;
        int igual = g_evr_ctl_ultima[k] == (int)clave;
        g_evr_ctl_ultima[k] = clave;
        /* ★ no juzga Y su piloto pasó notas después de la última suya = chocado: quieto en su real. Sin notas pasadas es
         *   una pausa de la canción (medido: congelar ahí atrasaba hasta 6 al que corre perfecto) */
        if (igual && ya && despues > 0) {
            g_evr_parado[k] = 1;
            g_evr_combo[k] = combo;
            g_evr_combo_t[k] = GetTickCount() | 1;
            return 1;
        }
    }
    g_evr_parado[k] = 0;                                                /* juzgó algo: vuelve a andar */
    if (ya) {
        BYTE *p = g_evr_obj[k];
        if (p) evr_poner_combo(p, (int)combo + (int)despues);         /* ★ tarde: el combo real + lo que siguió */
        g_evr_combo[k] = (int)combo + (int)despues;                     /*   y el del globo */
        g_evr_combo_t[k] = GetTickCount() | 1;
        if (j == 0) return 1;                                           /* un punto de control: nada más */
        /* ★ el corte: llegó tarde, el piloto ya contó 2-3 notas más y el número no pasa por 0 (medido: 0 de 38 cortes
         *   se veían). El «BREAK» del globo se dispara acá, a mano, aunque el número ya no sea 0 */
        if (combo == 0) {
            DWORD ah = GetTickCount();
            g_gc_t_break[k] = ah | 1;
            g_gc_ultimo[k] = g_evr_combo[k];
            g_gc_t_cambio[k] = ah;
            g_evr_n_cortes++;
        }
        g_evr_n_tarde++;
        if (g_evr_log && g_evr_n_tarde <= 5)
            apuntar("  [en_vivo_real] tarde: asiento %d nota %u juicio %d → combo %u+%u", k, (unsigned)clave, j,
                    (unsigned)combo, despues);
        return 1;
    }
    EVR_REAL *r = &g_evr_real[k][g_evr_real_f[k]++ % EVR_N];           /* a tiempo: lo usa el juez al llegar */
    r->t = GetTickCount(); r->clave = clave; r->j = j; r->d = d; r->combo = combo; r->vivo = 1;
    return 1;
}

/* ═══ 4 · LA TARJETA (0x55A9C0, una por corredor y por cuadro): después de dibujarla, su PD ═══════════════════════ */
static void __fastcall evr_tarjeta(void *hud, void *nada, int puesto, int pos, int asiento)
{
    (void)nada;
    BYTE *h = (BYTE *)hud;
    int x0 = h ? 0x15 - *(int *)(h + 0xA1C) : 0;                       /* como carrera12.c (0x55AAC8) */
    int y0 = pos == 0 ? 0xF : *(int *)GCV(0x904BF0);                    /* la tarjeta 0 va en 0xF; las demás, debajo */
    g_evr_tarjeta_real(hud, puesto, pos, asiento);
    BYTE *g = gc_juego();
    if (!g_evr_activo || !g_evr_pd || !h || !g || asiento < 0 || asiento >= 16) return;
    long long suma; int notas;
    if (!g[0xC01] && asiento == gc_mi_asiento()) { suma = g_calc_suma; notas = g_calc_notas; }   /* la mía, al día */
    else { suma = g_evr_pd_suma[asiento]; notas = g_evr_pd_notas[asiento]; }
    if (notas <= 0) return;
    int milesimas = (int)((suma * 1000 + notas / 2) / notas);           /* 96.524 = 96524 */
    void *obj = *(void **)GCV(0x93149C);
    if (!obj) return;
    char t[24];
    int n = wsprintfA(t, "%d.%03d%%", milesimas / 1000, milesimas % 1000);
    /* ★ adentro de la tarjeta, arriba a la derecha, alineado al borde (dx = el borde derecho desde el x de la tarjeta),
     *   con sombra de 1 px: se lee sobre cualquier color de tarjeta y no tapa el botón de mirar */
    int x = x0 + g_evr_pd_dx - n * CALC_DIGW, y = y0 + g_evr_pd_dy;
    F_PINTAR pintar = (F_PINTAR)GCV(0x63A640);
    pintar(obj, x + 1, y + 1, (int)0xFF000000, 0, "%s", t);
    pintar(obj, x, y, (int)g_evr_pd_color, 0, "%s", t);
}

/* ═══ 5 · EL GLOBO DE UN RIVAL (gc_etiqueta, para los que corren): su combo y la opacidad (se apaga sin noticias) ═══ */
static int evr_globo(int k, int *combo, int *f)
{
    if (!g_evr_activo || !g_evr_globos || k < 0 || k >= 16 || !g_evr_combo_t[k]) return 0;
    DWORD edad = GetTickCount() - g_evr_combo_t[k];
    *f = edad > GC_SIN_DATOS ? 256 - (int)((edad - GC_SIN_DATOS) * 256 / GC_APAGA) : 256;
    *combo = g_evr_combo[k];
    return 1;
}

static void evr_informe(void)                           /* al final de la carrera, una línea en el log */
{
    if (g_evr_n_env || g_evr_n_rec)
        apuntar("  [en_vivo_real] mandados %d · recibidos %d (a tiempo %d, tarde %d, vencidos %d) · controles %d/%d",
                g_evr_n_env, g_evr_n_rec, g_evr_n_a_tiempo, g_evr_n_tarde, g_evr_n_vencidos, g_evr_n_ctl,
                g_evr_n_ctl_rec);
}

static void en_vivo_real_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_evr_activo = GetPrivateProfileIntA("en_vivo_real", "activo", 1, ini) && g_gc_activo;
    g_evr_log = GetPrivateProfileIntA("en_vivo_real", "log", 0, ini);
    if (!g_evr_activo) { apuntar("  [en_vivo_real] apagado (o sin el globo)"); return; }
    g_calc_antes_juicio = evr_antes_juicio;
    g_calc_despues_juicio = evr_despues_juicio;
    apuntar("  [en_vivo_real] ★ las fallas de los rivales, en vivo (sub 0x%02X)", EVR_SUB);
    g_evr_globos = GetPrivateProfileIntA("en_vivo_real", "globos", 1, ini);
    apuntar("  [en_vivo_real] globos de los rivales para los que corren: %s", g_evr_globos ? "prendidos" : "apagados");
    g_evr_pd = GetPrivateProfileIntA("en_vivo_real", "pd_tarjetas", 1, ini);
    g_evr_pd_dx = GetPrivateProfileIntA("en_vivo_real", "pd_dx", 102, ini);
    g_evr_pd_dy = GetPrivateProfileIntA("en_vivo_real", "pd_dy", -1, ini);
    if (g_evr_pd) {
        CALC_ENGANCHE e = { 0x0055A9C0, { 0xA1, 0x64, 0x16, 0x93, 0x00 }, 5,
                            (void *)evr_tarjeta, (void **)&g_evr_tarjeta_real, "la tarjeta del corredor" };
        if (calc_verificar(&e) && calc_enganchar(&e))
            apuntar("  [en_vivo_real] ★ el PD en cada tarjeta (sub 0x%02X, dx=%d dy=%d)", EVR_SUB_PD, g_evr_pd_dx, g_evr_pd_dy);
        else { g_evr_pd = 0; apuntar("  [en_vivo_real] ⛔ la tarjeta no calza: sin PD en las tarjetas"); }
    }
}
