/* ═══════════════════════════════════════════════════════════════════════════
 * ★★★ LA FLUIDEZ A CUALQUIER Hz  ·  03-oct-2026
 *
 *   Port a C de `herramientas/dll_d3d9/medir_fluidez/cuadros_reales.js`, el guion
 *   de Frida con el que anonimo03 dijo *«ahora está perfecto»*:
 *       carrera a 165 dibujos · 165 POSICIONES distintas · la lógica en sus 60 pasos.
 *   La historia completa, con las mediciones: `LA_MATEMATICA_DEL_MOTOR.md`.
 *
 *   Se incluye desde `d3d9_proxy.c` (una sola unidad). Lo llama `aplicar_decouple`,
 *   y SOLO si el monitor supera `hzminimo`: a 60 no aporta nada.
 *
 * ★ LAS PIEZAS
 *
 *   1. EL GATE DEL DIBUJO (0x004989B8) — lo pone `aplicar_decouple`, como siempre.
 *
 *   2. LA CUEVA POR ESCENA (0x004989E8) — reemplaza al update-gate de antes:
 *        ¿hubo paso?            -> dibujar la escena (lo de siempre)
 *        si no, ¿es la carrera? -> dibujarla igual (las piezas 4 y 5 la arreglan)
 *        si no (menús)          -> saltar el cuadro ENTERO (0x498B3E), como de fábrica
 *      ⛔ El update-gate viejo NO frenaba "el mundo": frenaba el DIBUJO DE LA ESCENA
 *        (`escena->vtbl[3]` hace Clear + BeginScene + escena + EndScene), y la capa de
 *        carteles se repintaba encima de la imagen vieja = el parpadeo de los menús.
 *
 *   3. LA ESPERA AL REFRESCO — en la carrera, el Sleep del bucle no espera al próximo
 *      PASO: lo frena el Present (vsync). Con la espera precisa una vuelta sin paso
 *      dormía HASTA el paso siguiente ⇒ 2 dibujos por paso, no X. Va dentro de
 *      `mi_sleep` (d3d9_proxy.c), que ya distingue el Sleep del gate.
 *      ⚠ La red (la lección del CBT: nunca girar libre): si la ventana está inactiva,
 *        o no hubo Present en 25 ms, o el Present no frena (< 0,8 ms), se duerme 1 ms.
 *
 *   4. EXTRAPOLAR A LOS JUGADORES — al dibujar la carrera (cGame::vtbl[3] =
 *      0x004FBF60) cada jugador se adelanta la fracción de paso transcurrida y se lo
 *      devuelve a su lugar al terminar. La lógica, el juicio y el server no se enteran.
 *        y += vy [+0x18]  ·  z += vz [+0x20]  ·  x del carril [+0x38]   (0x00502AB2)
 *      Las notas están QUIETAS en el mundo y la pista se dibuja corrida por la z del
 *      jugador ⇒ mover a los jugadores mueve TODO lo que el ojo ve.
 *      Se usa la velocidad OBSERVADA entre los dos últimos pasos, y sólo si fue PAREJA
 *      (un cambio de carril o un frenazo no se extrapola: se vería un rebote).
 *      ⚠ La animación del cuerpo [+0x24] NO: la lógica la compara contra el largo de la
 *        tabla de cuadros y extrapolada podría pasarse del final.
 *
 *   5. EL FRENO FINO — en los dibujos SIN paso de la carrera, lo que el dibujo avanza
 *      "de a uno por llamada" se devuelve: SÓLO las celdas que encontró el censo (el
 *      combo, el latido y el giro del HUD), el cuadro de los carteles, y las imágenes
 *      animadas (`0x640CC0`, +16,67 ms por Present) no avanzan.
 *      ⛔ El freno de REGIONES enteras costaba 300-400 ms de ganchos por segundo.
 *
 * ⚠ Todos los enganches verifican sus bytes ANTES: o se ponen todos o ninguno, y si
 *   falta uno se cae al update-gate de antes (`mundo`).
 */

/* ── el mapa (✔ visto en el código, igual en R2Beat_local.exe y el de PROD) ── */
#define F_APP        0x009311F4   /* puntero a la aplicación                         */
#define F_GAME       0x009314C8   /* puntero a cGame (la escena de carrera)          */
#define F_ULTIMO     0x009D43B4   /* ¿hubo paso de lógica en esta vuelta?            */
#define F_INACTIVA   0x009D43BC   /* la ventana no tiene el foco                     */
#define F_PEND       0x00931580   /* pasos pendientes de la tanda                    */
#define F_HECHOS     0x00931584   /* pasos fabricados desde el último resync         */
#define F_INICIO     0x00931588   /* timeGetTime() del último resync                 */
#define F_GLOB1      0x009D4C88   /* el latido del HUD   (+0,03 por dibujo)          */
#define F_GLOB2      0x009D4C90   /* el giro del HUD     (+1,57 por dibujo)          */

#define FV(x)  (g_flu_base + ((DWORD)(x) - 0x400000))
#define TCF    __attribute__((thiscall))

static BYTE *g_flu_base = NULL;
/* `g_fluidez` ([motor] fluidez, ★ prendida de fábrica) se declara en d3d9_proxy.c:
 * la lee el cargador del ini, que va antes de este archivo */
static int   g_flu_activa = 0;        /* 1 = los enganches están puestos y valen   */
static void *g_flu_cueva = NULL;

/* el estado de la vuelta (todo en el hilo del juego: no hace falta sincronizar) */
static int f_paso = 0, f_anotado = 0, f_carrera = 0, f_era_carrera = 0;
static double f_ult_present = 0, f_dur_present = 4.0;

/* contadores para el log */
static long f_c_dibujos = 0, f_c_pos = 0, f_c_pasos = 0, f_c_informes = 0;
static double f_c_desde = 0;
static DWORD f_ultimo_z = 0;

/* ── los enganches: en el BORDE, con trampolín, verificando antes ─────────── */
typedef struct { DWORD va; BYTE espera[12]; int n; void *destino; void **real; const char *que; } FLU_GANCHO;

static int flu_verificar(const FLU_GANCHO *g)
{
    BYTE *s = FV(g->va);
    for (int i = 0; i < g->n; i++)
        if (s[i] != g->espera[i]) {
            char hex[48]; hex[0] = 0;
            for (int j = 0; j < g->n && j < 12; j++) wsprintfA(hex + lstrlenA(hex), "%02X ", s[j]);
            apuntar("  [fluidez] ⛔ %s: en 0x%08X hay [%s] y esperaba otra cosa", g->que, g->va, hex);
            return 0;
        }
    return 1;
}

static int flu_enganchar(const FLU_GANCHO *g)
{
    BYTE *s = FV(g->va);
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return 0;
    /* el trampolín: las instrucciones enteras del borde (ninguna es un salto relativo:
     * comprobado para las cinco) + un salto de vuelta al resto de la función */
    CopyMemory(t, s, g->n);
    t[g->n] = 0xE9;
    *(DWORD *)(t + g->n + 1) = (DWORD)((s + g->n) - (t + g->n + 5));
    DWORD viejo = 0;
    if (!VirtualProtect(s, g->n, PAGE_EXECUTE_READWRITE, &viejo)) { VirtualFree(t, 0, MEM_RELEASE); return 0; }
    *g->real = t;                       /* ⚠ ANTES del salto: el gancho puede correr ya */
    s[0] = 0xE9;
    *(DWORD *)(s + 1) = (DWORD)((BYTE *)g->destino - (s + 5));
    for (int i = 5; i < g->n; i++) s[i] = 0x90;
    VirtualProtect(s, g->n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, g->n);
    return 1;
}

typedef int (*F_COMPUERTA)(void);
typedef int (TCF *F_THIS)(void *self);
static F_COMPUERTA g_f_compuerta_real = NULL;
static F_THIS g_f_render_real = NULL, g_f_carteles_real = NULL, g_f_anim_real = NULL, g_f_present_real = NULL;

static inline BYTE *flu_app(void)  { return *(BYTE **)FV(F_APP); }
static inline BYTE *flu_game(void) { return *(BYTE **)FV(F_GAME); }

/* ── los jugadores de la carrera: el vector cGame+0xA14 / +0xA18 ───────────── *
 * ★ 15-oct: el tope era 8 («if (n > 8) return 0») ⇒ en la carrera de 12 (1 + 11 NPC) devolvía 0 y se apagaba la
 *   extrapolación de TODOS: la carrera volvía a 60 pasos/s dibujando a 165 (anonimo03: «con 1 + 5 NPC va fluido a 165;
 *   con 1 + 11 la fluidez se pierde»). Ahora 16 (la de 12 + margen), con todo dimensionado por FLU_TOPE. */
#define FLU_TOPE 16
static int flu_jugadores(BYTE **out)
{
    BYTE *g = flu_game();
    if (!g) return 0;
    BYTE **b = *(BYTE ***)(g + 0xA14), **e = *(BYTE ***)(g + 0xA18);
    if (!b || !e || e < b) return 0;
    int n = (int)(e - b), k = 0;
    if (n > FLU_TOPE) return 0;
    for (int i = 0; i < n; i++) if (b[i]) out[k++] = b[i];
    return k;
}

/* ── la historia de los tres últimos pasos de cada jugador ─────────────────── */
static const int F_CAMPOS[3] = { 0x18, 0x20, 0x38 };     /* y · z · x del carril */
typedef struct { BYTE *p; float a[3], b[3], c[3]; int n; } FLU_HIST;
static FLU_HIST f_hist[FLU_TOPE];
static int f_hist_rr = 0;

static FLU_HIST *flu_hist(BYTE *p, int crear)
{
    for (int i = 0; i < FLU_TOPE; i++) if (f_hist[i].p == p) return &f_hist[i];
    if (!crear) return NULL;
    for (int i = 0; i < FLU_TOPE; i++) if (!f_hist[i].p) { f_hist[i].p = p; f_hist[i].n = 0; return &f_hist[i]; }
    FLU_HIST *h = &f_hist[(f_hist_rr++ & 0x7FFFFFFF) % FLU_TOPE];
    h->p = p; h->n = 0;
    return h;
}

static void flu_anotar_paso(void)
{
    BYTE *js[FLU_TOPE];
    int n = flu_jugadores(js);
    for (int i = 0; i < n; i++) {
        FLU_HIST *h = flu_hist(js[i], 1);
        for (int j = 0; j < 3; j++) {
            h->c[j] = h->b[j]; h->b[j] = h->a[j];
            h->a[j] = *(float *)(js[i] + F_CAMPOS[j]);
        }
        if (h->n < 3) h->n++;
    }
}

/* ── la fracción de paso transcurrida desde el último paso ─────────────────────
 *   El reloj del motor es timeGetTime (ms enteros): se le agregan los decimales del
 *   QPC, con un desfase que sólo sube (y baja lentísimo) para no saltar. */
static double f_off = 0; static int f_off_ok = 0;
static double flu_fraccion(void)
{
    if (!g_timeGetTime) return 0;
    double q = ms_fino(), t = (double)g_timeGetTime();
    double o = t - q;
    if (!f_off_ok || o > f_off) { f_off = o; f_off_ok = 1; } else f_off -= 0.0005;
    double ahora = q + f_off;
    DWORD inicio = *(volatile DWORD *)FV(F_INICIO);
    DWORD hechos = *(volatile DWORD *)FV(F_HECHOS);
    DWORD pend   = *(volatile DWORD *)FV(F_PEND);
    double hecho = (double)hechos - (pend > 1 ? (double)(pend - 1) : 0.0);  /* los que YA corrieron */
    double f = (ahora - (double)inicio) * 0.06 - hecho;
    if (!(f >= 0)) f = 0;            /* también atrapa NaN */
    if (f > 1.25) f = 1.25;
    return f;
}

static float flu_abs(float v) { return v < 0 ? -v : v; }

/* ══ ★ 17-oct · EL LATIDO SUAVE (sólo en el que MIRA) ════════════════════════════════════════════════════════════
 * anonimo03: «el vecino que juntaba combos hacía un salto o teletransportación, de atrás hacia su posición real… no debe ser
 *   de red (latencia 0): es del diseño del espectador». MEDIDO (sonda en el que mira, 12 corren con BREAK al azar):
 *   en plena canción el reloj [+0x18] / la distancia [+0x20] de un corredor remoto saltan −21, −48 y +25 de un cuadro
 *   al otro. Es el LATIDO (tipo 5, ~1/s): 0x56D7F0 → 0x572F40 → 0x4FE030 PISA reloj y distancia con los del corredor
 *   real; si la copia local (las teclas re-juzgadas) se desvió —un tropiezo que no se reprodujo igual— lo teletransporta.
 * ⇒ La LÓGICA queda igual (el latido manda: juicios y teclas exactos). Sólo el DIBUJO: al llegar el latido se guarda
 *   cuánto lo corrió, y al dibujar se le suma esa diferencia, que se va a 0 en `suave_ms` ⇒ se DESLIZA a su lugar.
 *   Saltos > 150 no se suavizan (no son de este tipo). [latido] activo=0 / suave_ms en el ini. */
#define LS_LLAMA 0x0056D889                 /* call 0x572F40 (el latido) adentro de 0x56D7F0 */
typedef void (__fastcall *F_LATIDO)(void *mapa, void *edx, BYTE *jug, float t, int pasos);
static F_LATIDO g_ls_real = NULL;
static double g_ls_ms = 500.0;
static int g_ls_activo = 0, g_ls_suavizados = 0;
typedef struct { BYTE *jug; float dc, dd; double t0; } LS_OFF;
static LS_OFF g_ls[FLU_TOPE];

static float ls_resto(LS_OFF *o, double ahora)      /* cuánto queda del corrimiento: 1 → 0 en g_ls_ms */
{
    double k = 1.0 - (ahora - o->t0) / g_ls_ms;
    return k > 0 ? (float)k : 0.0f;
}

static void __fastcall ls_latido(void *mapa, void *edx, BYTE *jug, float t, int pasos)
{
    float c0 = *(float *)(jug + 0x18), d0 = *(float *)(jug + 0x20);
    g_ls_real(mapa, edx, jug, t, pasos);
    BYTE *g = flu_game();
    if (!g_ls_activo || !g || !g[0xC01]) return;                     /* sólo el que mira */
    float dc = c0 - *(float *)(jug + 0x18), dd = d0 - *(float *)(jug + 0x20);
    if (flu_abs(dc) < 0.5f || flu_abs(dc) > 150.0f) return;
    double ahora = ms_fino();
    LS_OFF *o = NULL, *libre = NULL;
    for (int i = 0; i < FLU_TOPE; i++) {
        if (g_ls[i].jug == jug) { o = &g_ls[i]; break; }
        if (!libre && (!g_ls[i].jug || ls_resto(&g_ls[i], ahora) == 0)) libre = &g_ls[i];
    }
    if (!o) { if (!libre) return; o = libre; o->jug = jug; o->dc = o->dd = 0; }
    float k = ls_resto(o, ahora);                                      /* lo que faltaba del anterior + éste */
    o->dc = o->dc * k + dc; o->dd = o->dd * k + dd; o->t0 = ahora;
    g_ls_suavizados++;
}

/* al dibujar: suma el corrimiento que queda (y guarda lo que había para devolverlo después) */
/* ★ 17-oct · la REPETICIÓN (repeticion.c, opción B) pone a cada vecino en su posición real al dibujar: la llama
 *   el dibujo DESPUÉS del latido suave (para los vecinos, la verdad le gana al suavizado) */
static int (*g_rp_dibujo)(DWORD **gp, DWORD *gv, float frac) = NULL;

static int ls_aplicar(DWORD **gp, DWORD *gv)
{
    BYTE *g = flu_game();
    if (!g_ls_activo || !g || !g[0xC01]) return 0;
    BYTE *js[FLU_TOPE];
    int nj = flu_jugadores(js), n = 0;
    double ahora = ms_fino();
    for (int i = 0; i < FLU_TOPE; i++) {
        LS_OFF *o = &g_ls[i];
        if (!o->jug) continue;
        int vivo = 0;
        for (int j = 0; j < nj; j++) if (js[j] == o->jug) { vivo = 1; break; }
        if (!vivo) { o->jug = NULL; continue; }                        /* otra carrera: el jugador se recreó */
        float k = ls_resto(o, ahora);
        if (k == 0) continue;
        float *pc = (float *)(o->jug + 0x18), *pd = (float *)(o->jug + 0x20);
        gp[n] = (DWORD *)pc; gv[n] = *(DWORD *)pc; n++;
        gp[n] = (DWORD *)pd; gv[n] = *(DWORD *)pd; n++;
        *pc += o->dc * k; *pd += o->dd * k;
    }
    return n;
}

static void latido_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("latido", "activo", 1, ini)) { apuntar("  [latido] apagado ([latido] activo=0)"); return; }
    g_ls_ms = (double)GetPrivateProfileIntA("latido", "suave_ms", 500, ini);
    if (g_ls_ms < 50) g_ls_ms = 50;
    BYTE *c = FV(LS_LLAMA);
    if (c[0] != 0xE8 || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)FV(0x00572F40)) {
        apuntar("  [latido] ⚠ el latido (0x56D889) no es el esperado: el que mira sigue con saltos");
        return;
    }
    g_ls_real = (F_LATIDO)FV(0x00572F40);
    BYTE nue[5] = { 0xE8, 0, 0, 0, 0 };
    *(int *)(nue + 1) = (int)((DWORD)ls_latido - ((DWORD)c + 5));
    if (escribir_bytes(LS_LLAMA, c, nue, 5, "latido suave")) {
        g_ls_activo = 1;
        apuntar("  [latido] ★ el que mira: la corrección del latido se desliza en %d ms (no teletransporta)", (int)g_ls_ms);
    }
}

/* ── 5 · el freno fino: las celdas del censo (03-oct), relativas a la aplicación ── */
static const DWORD F_FINO_APP[6] = { 0x17A4 + 0x9D0, 0x17A4 + 0xC18, 0x17A4 + 0xC1C,
                                     0x17A4 + 0xC20, 0xE90, 0xE94 };
#define F_FINO_CARTEL (0x35CC + 0x63C8)

/* ══ los cuatro ganchos ════════════════════════════════════════════════════ */

/* la compuerta del motor (0x00410420): ¿esta vuelta trae paso? ¿estamos en carrera? */
static int flu_mi_compuerta(void)
{
    f_anotado = 0;
    BYTE *app = flu_app(), *g = flu_game();
    void *esc = app ? *(void **)(app + 0xAFFC) : NULL;
    f_carrera = (g && esc == (void *)g);
    if (f_carrera != f_era_carrera) {
        /* al entrar o salir de una carrera la historia no vale: otra pista, otros jugadores */
        ZeroMemory(f_hist, sizeof(f_hist));
        f_era_carrera = f_carrera;
    }
    f_paso = 0;
    int r = g_f_compuerta_real();
    if (r == 1) { f_paso = 1; if (f_carrera) f_c_pasos++; }
    return r;
}

/* el dibujo de la carrera (cGame::vtbl[3] = 0x004FBF60): extrapolar + freno fino */
static int TCF flu_mi_render(void *self)
{
    if (!g_flu_activa || !f_carrera) {
        DWORD *lp[4 * FLU_TOPE]; DWORD lv[4 * FLU_TOPE];
        int nl = f_carrera ? ls_aplicar(lp, lv) : 0;
        if (f_carrera && g_rp_dibujo) nl += g_rp_dibujo(lp + nl, lv + nl, 0.0f);
        int r0 = g_f_render_real(self);
        for (int i = nl - 1; i >= 0; i--) *lp[i] = lv[i];
        return r0;
    }

    if (f_paso && !f_anotado) { flu_anotar_paso(); f_anotado = 1; }

    /* el freno fino: foto de las celdas ANTES del dibujo (sólo en los dibujos sin paso) */
    DWORD fino_v[8]; DWORD *fino_p[8]; int nf = 0;
    BYTE *app = flu_app();
    if (!f_paso && app) {
        for (int i = 0; i < 6; i++) { fino_p[nf] = (DWORD *)(app + F_FINO_APP[i]); fino_v[nf] = *fino_p[nf]; nf++; }
        fino_p[nf] = (DWORD *)FV(F_GLOB1); fino_v[nf] = *fino_p[nf]; nf++;
        fino_p[nf] = (DWORD *)FV(F_GLOB2); fino_v[nf] = *fino_p[nf]; nf++;
    }

    /* extrapolar */
    DWORD *gp[3 * FLU_TOPE]; DWORD gv[3 * FLU_TOPE]; int ng = 0;
    BYTE *js[FLU_TOPE];
    int nj = flu_jugadores(js);
    float f = (float)flu_fraccion();
    for (int i = 0; i < nj; i++) {
        FLU_HIST *h = flu_hist(js[i], 0);
        if (!h || h->n < 3) continue;
        for (int j = 0; j < 3; j++) {
            float v1 = h->a[j] - h->b[j], v0 = h->b[j] - h->c[j];
            if (v1 == 0) continue;
            if ((v1 > 0) != (v0 > 0)) continue;
            float m = flu_abs(v1) > flu_abs(v0) ? flu_abs(v1) : flu_abs(v0);
            if (flu_abs(v1 - v0) > 0.5f * m + 1e-4f) continue;
            float *p = (float *)(js[i] + F_CAMPOS[j]);
            if (flu_abs(*p - h->a[j]) > 1e-3f) continue;        /* alguien lo movió: no tocar */
            gp[ng] = (DWORD *)p; gv[ng] = *(DWORD *)p; ng++;
            *p = *p + v1 * f;
        }
    }

    /* para el log: ¿la posición del jugador LOCAL cambió en este dibujo? */
    BYTE *g = flu_game();
    if (g) {
        BYTE idx = *(g + 0x5D);
        if (idx < nj) { DWORD z = *(DWORD *)(js[idx] + 0x20); if (z != f_ultimo_z) { f_c_pos++; f_ultimo_z = z; } }
    }
    f_c_dibujos++;

    /* ★ el latido suave (DESPUÉS de anotar la historia y de extrapolar; se devuelve ANTES que la extrapolación) */
    DWORD *lp[4 * FLU_TOPE]; DWORD lv[4 * FLU_TOPE];
    int nl = ls_aplicar(lp, lv);
    if (g_rp_dibujo) nl += g_rp_dibujo(lp + nl, lv + nl, f);

    int r = g_f_render_real(self);

    for (int i = nl - 1; i >= 0; i--) *lp[i] = lv[i];
    for (int i = 0; i < ng; i++) *gp[i] = gv[i];
    for (int i = 0; i < nf; i++) *fino_p[i] = fino_v[i];
    return r;
}

/* la capa de carteles (0x00419B70): su cuadro de animación, frenado en la carrera */
static int TCF flu_mi_carteles(void *self)
{
    if (!g_flu_activa || !f_carrera || f_paso) return g_f_carteles_real(self);
    BYTE *app = flu_app();
    if (!app) return g_f_carteles_real(self);
    DWORD *p = (DWORD *)(app + F_FINO_CARTEL), v = *p;
    int r = g_f_carteles_real(self);
    *p = v;
    return r;
}

/* las imágenes animadas (0x00640CC0): +16,67 ms POR PRESENT ⇒ en la carrera, sólo
 * en las vueltas con paso: 60 por segundo, como de fábrica */
static int TCF flu_mi_anim(void *self)
{
    if (g_flu_activa && f_carrera && !f_paso) return 0;
    return g_f_anim_real(self);
}

/* el Present del juego (0x0064A8D0): cuándo fue el último y cuánto tardó (vsync) */
static int TCF flu_mi_present(void *self)
{
    double t0 = ms_fino();
    int r = g_f_present_real(self);
    double t1 = ms_fino();
    f_dur_present = f_dur_present * 0.9 + (t1 - t0) * 0.1;
    f_ult_present = t1;

    /* ★ el informe: cada 30 s de carrera una línea, hasta 12 (para cruzar con lo que se ve) */
    if (f_carrera) {
        if (f_c_desde == 0) { f_c_desde = t1; f_c_dibujos = f_c_pos = f_c_pasos = 0; }
        else if (t1 - f_c_desde >= 30000.0 && f_c_informes < 12) {
            double s = (t1 - f_c_desde) / 1000.0;
            BYTE *gm = flu_game();
            apuntar("  [fluidez] carrera (pid %lu, %s): %d dibujos/s · %d POSICIONES/s · %d pasos/s · Present %d.%d ms",
                    GetCurrentProcessId(), gm && gm[0xC01] ? "mirando" : "corriendo",
                    (int)(f_c_dibujos / s), (int)(f_c_pos / s), (int)(f_c_pasos / s),
                    (int)f_dur_present, (int)(f_dur_present * 10) % 10);
            f_c_informes++;
            f_c_desde = t1; f_c_dibujos = f_c_pos = f_c_pasos = 0;
        }
    } else f_c_desde = 0;
    return r;
}

/* ── 3 · la espera al refresco: la consulta `mi_sleep` en el Sleep del gate ──────
 *   devuelve 1 si se encargó (y entonces mi_sleep no hace la espera precisa) */
/* ★ 14-oct (anonimo03: «con 12 clientes vuelvo a sentir lag — mantené la fluidez»): la ventana que NO está al frente no
 *   necesita 165 cuadros (nadie la mira): dibuja a 60 — al ritmo de los pasos, como de fábrica — y la del frente sigue
 *   con la fluidez. Se mira cada 250 ms (GetForegroundWindow es barato, pero no hace falta 165 veces por segundo).
 *   [motor] fondo60=0 lo apaga (todas a la frecuencia del monitor). */
static int flu_al_frente(void)
{
    static DWORD t = 0;
    static int frente = 1;
    DWORD ahora = GetTickCount();
    if (ahora - t >= 250) {
        t = ahora;
        DWORD pid = 0;
        HWND f = GetForegroundWindow();
        if (f) GetWindowThreadProcessId(f, &pid);
        frente = pid == GetCurrentProcessId();
    }
    return frente;
}

static int flu_espera(void)
{
    if (!g_flu_activa || !f_carrera) return 0;
    if (g_flu_fondo60 && !flu_al_frente()) return 0;       /* ★ de fondo: el paso marca el ritmo (60) */
    if (*(volatile DWORD *)FV(F_INACTIVA) != 0 || (ms_fino() - f_ult_present) > 25.0
        || f_dur_present < 0.8)
        g_sleep_real(1);
    return 1;
}

/* ── 2 · la cueva por escena, en 0x004989E8 ────────────────────────────────── */
static int flu_poner_cueva(void)
{
    g_flu_cueva = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_flu_cueva) return 0;
    BYTE *c = (BYTE *)g_flu_cueva;
    DWORD C = (DWORD)(ULONG_PTR)c;
    int i = 0;
    /* +0  cmp dword [ULTIMO],0            ¿hubo paso?                         */
    c[i++] = 0x83; c[i++] = 0x3D; escribir_u32(c + i, F_ULTIMO - 0x400000 + (DWORD)(ULONG_PTR)g_flu_base); i += 4; c[i++] = 0x00;
    /* +7  jne normal (+23)                                                   */
    c[i++] = 0x75; c[i++] = 23 - 9;
    /* +9  mov eax,[ebp+0xAFFC]            la escena de esta vuelta            */
    c[i++] = 0x8B; c[i++] = 0x85; c[i++] = 0xFC; c[i++] = 0xAF; c[i++] = 0x00; c[i++] = 0x00;
    /* +15 cmp eax,[GAME]                  ¿es la carrera?                     */
    c[i++] = 0x3B; c[i++] = 0x05; escribir_u32(c + i, F_GAME - 0x400000 + (DWORD)(ULONG_PTR)g_flu_base); i += 4;
    /* +21 jne fabrica (+34)                                                  */
    c[i++] = 0x75; c[i++] = 34 - 23;
    /* +23 normal: mov ecx,[ebp+0xAFFC]    (lo que reemplazamos en el sitio)   */
    c[i++] = 0x8B; c[i++] = 0x8D; c[i++] = 0xFC; c[i++] = 0xAF; c[i++] = 0x00; c[i++] = 0x00;
    /* +29 jmp 0x004989EE                  dibujar la escena                   */
    c[i++] = 0xE9; escribir_u32(c + i, (DWORD)(ULONG_PTR)FV(0x004989EE) - (C + 29 + 5)); i += 4;
    /* +34 fabrica: jmp 0x00498B3E         saltar el cuadro ENTERO, como de fábrica */
    c[i++] = 0xE9; escribir_u32(c + i, (DWORD)(ULONG_PTR)FV(0x00498B3E) - (C + 34 + 5)); i += 4;

    BYTE esp[6] = { 0x8B, 0x8D, 0xFC, 0xAF, 0x00, 0x00 };
    BYTE nue[6];
    nue[0] = 0xE9;
    escribir_u32(nue + 1, C - ((DWORD)(ULONG_PTR)FV(0x004989E8) + 5));
    nue[5] = 0x90;
    if (!escribir_bytes(0x004989E8, esp, nue, 6, "cueva por escena")) {
        VirtualFree(g_flu_cueva, 0, MEM_RELEASE);
        g_flu_cueva = NULL;
        return 0;
    }
    return 1;
}

/* ── todo junto. Devuelve 1 si quedó puesta (si no, el llamador pone el update-gate) ── */
static int fluidez_iniciar(void)
{
    if (!g_fluidez) return 0;
    g_flu_base = (BYTE *)GetModuleHandleA(NULL);
    if (!g_flu_base) return 0;
    if (!g_qpf.QuadPart) QueryPerformanceFrequency(&g_qpf);
    if (!g_timeGetTime) {
        HMODULE wmm = LoadLibraryA("winmm.dll");
        if (wmm) g_timeGetTime = (RELOJMS)GetProcAddress(wmm, "timeGetTime");
    }
    if (!g_timeGetTime || !g_qpf.QuadPart) {
        apuntar("  [fluidez] ⛔ sin reloj (timeGetTime/QPC): NO se aplica");
        return 0;
    }
    if (!g_sleep_real) {
        /* ⚠ la espera al refresco vive en `mi_sleep`, que pone la espera precisa.
         *   Sin ella el bucle duerme el Sleep de fábrica y la carrera no pasa de ~60. */
        apuntar("  [fluidez] ⚠ sin la espera precisa ([motor] ritmo=0): NO se aplica");
        return 0;
    }

    FLU_GANCHO g[5] = {
        { 0x00410420, { 0x51, 0xFF, 0x15, 0x24, 0x34, 0x87, 0x00 }, 7,
          (void *)flu_mi_compuerta, (void **)&g_f_compuerta_real, "la compuerta del motor" },
        { 0x004FBF60, { 0x51, 0x55, 0x56, 0x57, 0x8B, 0xF1 }, 6,
          (void *)flu_mi_render, (void **)&g_f_render_real, "el dibujo de la carrera" },
        { 0x00419B70, { 0x55, 0x8B, 0xEC, 0x83, 0xE4, 0xF8 }, 6,
          (void *)flu_mi_carteles, (void **)&g_f_carteles_real, "la capa de carteles" },
        { 0x00640CC0, { 0x83, 0xEC, 0x08, 0x8B, 0x81, 0x88, 0x00, 0x00, 0x00 }, 9,
          (void *)flu_mi_anim, (void **)&g_f_anim_real, "las imagenes animadas" },
        { 0x0064A8D0, { 0x56, 0x8B, 0xF1, 0x8B, 0x0D, 0x70, 0x15, 0x93, 0x00 }, 9,
          (void *)flu_mi_present, (void **)&g_f_present_real, "el Present del juego" },
    };
    /* ⚠ y la cueva por escena reemplaza al update-gate: su sitio tiene que estar intacto */
    BYTE *ug = FV(0x004989E8);
    int ug_ok = ug[0] == 0x8B && ug[1] == 0x8D && ug[2] == 0xFC && ug[3] == 0xAF;
    if (!ug_ok) apuntar("  [fluidez] ⛔ 0x004989E8 no es el original (¿otro parche?)");
    /* ★ o se ponen TODOS o ninguno: media fluidez (extrapolar sin freno, freno sin
     *   extrapolar) es peor que la de antes */
    for (int i = 0; i < 5; i++) if (!flu_verificar(&g[i])) ug_ok = 0;
    if (!ug_ok) {
        apuntar("  [fluidez] ⛔ el exe no es el esperado: NO engancho nada (queda el update-gate)");
        return 0;
    }
    if (!flu_poner_cueva()) return 0;
    for (int i = 0; i < 5; i++)
        if (!flu_enganchar(&g[i])) {
            /* ⚠ a esta altura algunos ya están puestos: quedan inertes (g_flu_activa = 0
             *   y la cueva sigue dibujando como de fábrica en los menús) */
            apuntar("  [fluidez] ⛔ no pude poner %s: la fluidez queda APAGADA", g[i].que);
            return 1;
        }
    g_flu_activa = 1;
    latido_iniciar();
    apuntar("  [fluidez] ★ la carrera a la frecuencia del monitor: extrapolar + freno fino"
            " + espera al refresco · menús de fábrica (cueva en 0x%08X)",
            (DWORD)(ULONG_PTR)g_flu_cueva);
    return 1;
}
