/* panel_sala.c — el panel de la sala con «Obstáculos» (y «Victoria») — 08-oct-2026, etapa 4
 *
 *   anonimo03, con su maqueta: dos recuadros debajo de «Pista», uno para elegir los obstáculos (con la misma ventana
 *   que la pista) y otro para la condición de victoria (sólo en salas por equipos). Investigación y medidas:
 *   documentacion/PISTA_OBSTACULOS_VICTORIA.md §7. El arte: herramientas/panel_sala.py -> R2Beat/rnr_ui_sala.pak
 *   (gr_1 con el corte 9 de 201×402 y el corte 18 = «Victoria») + panel_sala_datos.h.
 *
 *   El panel lo dibuja 0x58F360 (lo llama 0x5AEEBE) con TODO en posiciones fijas: el corte 9 en y 0xB4, la portada
 *   en 0xD4, sus insignias en 0x102, las estrellas en 0x10B, la imagen de la pista en 0x143, el Rcoin con
 *   0x58D670(x, 0xB4) [D]. Y los clics en el panel (0x586270, lo llama 0x5A6FEF): la música en y 0xD3..0x120 y la
 *   pista en 0x142..0x18F. ⇒ el panel nuevo SUBE `PS_SUBE` px y el Rcoin BAJA `PS_ALTO_NUEVO`:
 *
 *     · una tabla de 30 inmediatos (push imm32 / cmp edi,imm32), cada uno con su valor de siempre como guarda.
 *       ⚠ En el COOPERATIVO ([cRoom+0x9564] == 4) el panel es otro (gr_01) y comparte el final de la función: ahí
 *       cada uno lleva SU corrimiento (`delta_coop`: «Modo Cooperativo» sube, el Rcoin baja, para que entre el
 *       mini-panel en el medio — la maqueta de anonimo03 del 09-oct). Se reescriben sólo cuando cambia el modo.
 *     · 0x58F74F (el Rcoin, lo último del panel): después, la imagen de los obstáculos en su marco y, si la sala
 *       es por equipos, el recuadro de «Victoria» (corte 18).
 *     · 0x5A6FEF (los clics): un clic en el marco de «Obstáculos» abre la ventana de pistas (0x58F9B0) en MODO
 *       OBSTÁCULOS; al confirmar, el FF1B (0x5C7880, en 0x58D552 y 0x5B389E) sale con el bit 0x8000: el server
 *       lo anota como los obstáculos de ese jugador (lobby_carrera.h_28_ff1b) y le reemite el FF13.
 *     · 0x5CD519 (el final de la lectura del FF13): 3 bytes más, la COLA DEL FF13 que pone el server:
 *       `obstaculos` u16 (0xFFFF = los de la pista · 0 = aleatorios · N) y `victoria` u8 (0xFF = sala sin equipos).
 *       Con un server viejo no llegan: se ponen en 0xFFFF / 0xFF antes de pedirlos (= nada que mostrar).
 *   ★ EL COOPERATIVO (09-oct, anonimo03: «igual que en las salas»): su panel es otro y no se toca; se dibuja un MINI-PANEL
 *     (corte 19) arriba de la moneda gorila con «Pista» y «Obstáculos». Un clic abre la ventana NORMAL de pistas: en
 *     el cooperativo `[cRoom+0x10E94]` apunta a la del chase (`+0x10E9C`, 0x58E700), así que mientras está abierta se
 *     la cambia por la normal (`+0x10E98`) y al cerrarla se le devuelve. El server guarda esa pista aparte
 *     (`pista_coop`) y la manda en la cola del FF13 (3er campo, u16) para dibujarla.
 *     ⚠ Mientras la ventana está abierta, el recuadro «Modo Cooperativo» muestra «Aleatoria» (le pregunta la pista
 *       a la ventana normal, que contesta 0): se arregla solo al cerrarla.
 *   ⛔ [panel_sala] activo=0 lo apaga entero (sin el pak, el corte 9 viejo mide 310 y el panel queda roto: van JUNTOS).
 */
#include "panel_sala_datos.h"

#define PSV(x) (g_ps_base + ((DWORD)(x) - 0x400000))
#define TCS __attribute__((thiscall))

static BYTE *g_ps_base = NULL;
static void __cdecl s12v_tras_ff13(void);              /* sala12_vista.c (va después) */
static volatile WORD g_ps_obst = 0xFFFF;    /* la cola del FF13: los obstáculos que ve este jugador */
static volatile BYTE g_ps_vict = 0xFF;      /* ...y la condición de victoria (0xFF = la sala no es por equipos) */
static volatile WORD g_ps_pista = 0xFFFF;   /* ...y la pista con la que corre (en el cooperativo, la del mini-panel) */
static int   g_ps_cambiada = 0;             /* 1 = en el cooperativo, [cRoom+0x10E94] apunta a la ventana NORMAL */
static int   g_ps_modo = -1;                /* -1 sin escribir · si no, la disposición (PS_SALA, PS_COOP, PS_SALA_C, PS_COOP_C) */
/* g_modo_obst (1 = la ventana de pistas está abierta PARA ELEGIR OBSTÁCULOS) vive en pista_propia.c */
static WORD  g_ps_snap_pista = 0;           /* lo que mostraba la ventana antes de abrirla en modo obstáculos */
static DWORD g_ps_snap_i364 = 0, g_ps_snap_i368 = 0;
static int   g_ps_snap = 0;
static BYTE *g_ps_cueva = NULL;

/* ★★ CUATRO DISPOSICIONES (09-oct): sala o cooperativo × pantalla ANCHA o ANGOSTA. En 800×600 las tarjetas de los
 *   asientos 5 y 6 bajan hasta y≈182 justo encima del panel y los botones de abajo empiezan en ≈535: ahí va la versión
 *   COMPACTA (corte 20, que no sube; anonimo03: «versión compacta de toda esa interface sólo para 800»). Angosta = el panel
 *   (ancho - 0xD2) cae debajo de las tarjetas: ancho < PS_ANGOSTA. */
enum { PS_SALA = 0, PS_COOP = 1, PS_SALA_C = 2, PS_COOP_C = 3 };
static const char *PS_NOMBRE[4] = { "sala (subido, con «Obstáculos»)", "cooperativo (con el mini-panel)",
                                    "sala COMPACTO (pantalla angosta)", "cooperativo COMPACTO (pantalla angosta)" };

/* los inmediatos que se corren: (sitio, offset, tamaño, el de siempre, cuánto en cada disposición) */
typedef struct { DWORD va; BYTE off; BYTE tam; DWORD orig; int d[4]; const char *que; } PS_IMM;
#define S  (-PS_SUBE)
#define CS (-PS_COOP_SUBE)
#define CP (-PS_C_PISTA_SUBE)
static const PS_IMM PS_T[] = {
    /*                          sala      coop             sala compacta        coop compacto */
    { 0x58F3C2, 1, 1, 9,     { 0,        0,               PS_C_CORTE - 9,      0 }, "el corte del panel (9 -> el compacto)" },
    { 0x58F3C4, 1, 4, 0xB4,  { S,        0,               0,                   0 }, "el panel (corte 9)" },
    { 0x58F39C, 1, 4, 0x122, { 0,        CS,              0,                   CS }, "«Modo Cooperativo» (groupracing_gr_01 corte 1)" },
    { 0x58F411, 1, 4, 0xD4,  { S, 0, 0, 0 }, "portada" }, { 0x58F43D, 1, 4, 0xD4, { S, 0, 0, 0 }, "portada" },
    { 0x58F48B, 1, 4, 0xD4,  { S, 0, 0, 0 }, "portada" }, { 0x58F4FF, 1, 4, 0xD4, { S, 0, 0, 0 }, "portada" },
    { 0x58F522, 1, 4, 0xD4,  { S, 0, 0, 0 }, "portada" }, { 0x58F53B, 1, 4, 0xD4, { S, 0, 0, 0 }, "portada" },
    { 0x58F569, 1, 4, 0xD4,  { S, 0, 0, 0 }, "portada" }, { 0x58F587, 1, 4, 0xD4, { S, 0, 0, 0 }, "portada" },
    { 0x58F59D, 1, 4, 0xD4,  { S, 0, 0, 0 }, "portada" }, { 0x58F5DB, 1, 4, 0xD4, { S, 0, 0, 0 }, "portada" },
    { 0x58F64F, 1, 4, 0xD4,  { S, 0, 0, 0 }, "portada" },
    { 0x58F4A9, 1, 4, 0x102, { S, 0, 0, 0 }, "insignia" }, { 0x58F4BF, 1, 4, 0x102, { S, 0, 0, 0 }, "insignia" },
    { 0x58F5F9, 1, 4, 0x102, { S, 0, 0, 0 }, "insignia" }, { 0x58F60F, 1, 4, 0x102, { S, 0, 0, 0 }, "insignia" },
    { 0x58F4E4, 1, 4, 0x10B, { S, 0, 0, 0 }, "estrellas" }, { 0x58F63A, 1, 4, 0x10B, { S, 0, 0, 0 }, "estrellas" },
    { 0x58F67F, 1, 4, 0x143, { S,        CS,              CP,                  CS }, "«seleccionando»" },
    { 0x58F6DA, 1, 4, 0x143, { S,        CS,              CP,                  CS }, "la pista (en el cooperativo, la del chase)" },
    { 0x58F6FE, 1, 4, 0x143, { S,        CS,              CP,                  CS }, "la pista (2)" },
    { 0x58F71B, 1, 4, 0x107, { S,        CS,              0,                   CS }, "la marca de la música" },
    { 0x58F737, 1, 4, 0x1A0, { 0,        PS_COOP_RCOIN,   0,                   PS_C_COOP_RCOIN }, "la caja del Rcoin (sólo el cooperativo la dibuja aparte)" },
    { 0x58F747, 1, 4, 0xB4,  { PS_ALTO_NUEVO - PS_SUBE, PS_COOP_RCOIN, PS_C_RCOIN, PS_C_COOP_RCOIN }, "el Rcoin y la EXP" },
    { 0x5862CA, 2, 4, 0xD3,  { S, 0, 0, 0 }, "clic: música (desde)" }, { 0x5862D2, 2, 4, 0x120, { S, 0, 0, 0 }, "clic: música (hasta)" },
    { 0x586338, 2, 4, 0x142, { S, 0, CP, 0 }, "clic: pista (desde)" }, { 0x586340, 2, 4, 0x18F, { S, 0, CP, 0 }, "clic: pista (hasta)" },
};
#undef S
#undef CS
#undef CP
#define PS_NT ((int)(sizeof(PS_T) / sizeof(PS_T[0])))

static void ps_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    BYTE *s = PSV(va);
    if (!VirtualProtect(s, n, PAGE_EXECUTE_READWRITE, &viejo)) return;
    CopyMemory(s, b, n);
    VirtualProtect(s, n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, n);
}

static int ps_ancho_pantalla(void)
{
    BYTE *p = *(BYTE **)PSV(0x931498);
    return p ? *(int *)(p + 4) : 0;
}

static int ps_es_coop(int m) { return m == PS_COOP || m == PS_COOP_C; }
static int ps_es_compacto(int m) { return m == PS_SALA_C || m == PS_COOP_C; }

static void ps_poner_modo(BYTE *sala)
{
    int coop = sala && *(int *)(sala + 0x9564) == 4;
    int angosta = ps_ancho_pantalla() < PS_ANGOSTA;
    int nuevo = coop ? (angosta ? PS_COOP_C : PS_COOP) : (angosta ? PS_SALA_C : PS_SALA);
    if (nuevo == g_ps_modo) return;
    for (int i = 0; i < PS_NT; i++) {
        DWORD v = PS_T[i].orig + PS_T[i].d[nuevo];
        ps_escribir(PS_T[i].va + PS_T[i].off, &v, PS_T[i].tam);
    }
    g_ps_modo = nuevo;
    apuntar("  [panel_sala] panel: %s (pantalla de %d px de ancho)", PS_NOMBRE[nuevo], ps_ancho_pantalla());
}

/* las medidas de la disposición de ahora: la y del panel y los marcos */
static int ps_panel_y(void) { return g_ps_modo == PS_SALA ? 0xB4 - PS_SUBE : 0xB4; }
static void ps_marco_obst(int r[4])
{
    static const int w[4] = { PS_OBST }, c[4] = { PS_C_OBST };
    const int *o = ps_es_compacto(g_ps_modo) ? c : w;
    for (int i = 0; i < 4; i++) r[i] = o[i];
}
static void ps_marcos_coop(int p[4], int o[4])
{
    static const int wp[4] = { PS_COOP_PISTA }, wo[4] = { PS_COOP_OBST }, cp[4] = { PS_C_COOP_PISTA }, co[4] = { PS_C_COOP_OBST };
    int c = ps_es_compacto(g_ps_modo);
    for (int i = 0; i < 4; i++) { p[i] = c ? cp[i] : wp[i]; o[i] = c ? co[i] : wo[i]; }
}

/* ── lo que se llama ── */
typedef void  (TCS *F_PS_PANEL)(void *sala, int a);                       /* 0x58F360, ret 4 */
typedef int   (TCS *F_PS_CLIC)(void *sala, int x, int y, int clic);       /* 0x586270, ret 0xC */
typedef void  (TCS *F_PS_RCOIN)(void *sala, int x, int y, int a);         /* 0x58D670, ret 0xC */
typedef void  (TCS *F_PS_FF1B)(void *red, int pista);                     /* 0x5C7880, ret 4 */
typedef void  (TCS *F_PS_VENTANA)(void *sala);                            /* 0x58F9B0 */
typedef BYTE *(TCS *F_PS_PISTA)(void *cat, int pista);                    /* 0x40E410, ret 4 */
typedef void  (TCS *F_PS_CORTE)(void *spr, int x, int y, int corte, int banderas);   /* 0x683FB0 */

static void ps_devolver_chase(BYTE *sala);

static void TCS ps_panel(void *sala, int a)
{
    ps_poner_modo((BYTE *)sala);
    if (sala && !*((BYTE *)sala + 0xA429)) {                                       /* la ventana está cerrada */
        g_modo_obst = 0;
        ps_devolver_chase((BYTE *)sala);
    }
    ((F_PS_PANEL)PSV(0x58F360))(sala, a);
}

/* el cooperativo: la ventana de pistas NORMAL en lugar de la del chase, mientras está abierta */
static void ps_devolver_chase(BYTE *sala)
{
    if (!g_ps_cambiada || !sala) return;
    BYTE *chase = *(BYTE **)(sala + 0x10E9C);
    if (chase) *(BYTE **)(sala + 0x10E94) = chase;
    g_ps_cambiada = 0;
}

static int ps_panel_x(void)
{
    BYTE *p = *(BYTE **)PSV(0x931498);
    return p ? *(int *)(p + 4) - 0xD2 : 0;                    /* 0x58F363: [[0x931498]+4] - 0xD2 */
}

/* dibuja la imagen de la pista `n` (la del catálogo de pistas) dentro de un marco, achicada */
static void ps_imagen_pista(int n, int x, int y, int w, int h)
{
    void *cat = *(void **)PSV(0x9314DC);
    if (!cat) return;
    BYTE *p = ((F_PS_PISTA)PSV(0x40E410))(cat, n);
    BYTE *img = p ? *(BYTE **)(p + 4) : NULL;
    if (!img) return;
    BYTE *v0 = *(BYTE **)(img + 0x18), *v1 = *(BYTE **)(img + 0x1C);
    if (!v0 || v1 < v0 + 2 * 0x50) return;
    BYTE *e = v0 + 0x50;                                         /* el recorte 1, el que usa la caja de «Pista» */
    float w0 = *(float *)(e + 0x14), h0 = *(float *)(e + 0x18);
    ((F_PK_C2D_TAMANO)PSV(0x64DB90))(img, 1, w, h);
    ((F_PK_C2D_POS)PSV(0x64D990))(img, 1, x, y);
    ((F_PK_C2D_COLOR)PSV(0x64E710))(img, 1, 0xFFFFFFFF);
    ((F_PK_C2D_DIBUJAR)PSV(0x64EE40))(img, 1, 0);                /* la cola se COPIA la entrada (0x554D30) ... */
    *(float *)(e + 0x14) = w0;                                   /* ... así que se le devuelve el tamaño ya */
    *(float *)(e + 0x18) = h0;
}

static void TCS ps_rcoin(void *sala, int x, int y, int a)
{
    ((F_PS_RCOIN)PSV(0x58D670))(sala, x, y, a);
    if (!sala) return;
    BYTE *s = (BYTE *)sala;
    if (ps_es_coop(g_ps_modo) && *(int *)(s + 0x9564) == 4) {    /* ★ el cooperativo: el mini-panel */
        int cp[4], co[4];
        ps_marcos_coop(cp, co);
        void *spr = *(void **)(s + 0x1CC);
        if (spr) ((F_PS_CORTE)PSV(0x683FB0))(spr, x, PS_COOP_Y, ps_es_compacto(g_ps_modo) ? PS_C_CORTE + 2 : PS_CORTE_COOP, 0);
        int pi = g_ps_pista, ob = g_ps_obst;
        if (pi != 0xFFFF)
            ps_imagen_pista(pi, x + cp[0] + PS_INSET, PS_COOP_Y + cp[1] + PS_INSET,
                            cp[2] - cp[0] + 1 - 2 * PS_INSET, cp[3] - cp[1] + 1 - 2 * PS_INSET);
        if (ob == 0xFFFF) ob = pi;
        if (ob != 0xFFFF)
            ps_imagen_pista(ob, x + co[0] + PS_INSET, PS_COOP_Y + co[1] + PS_INSET,
                            co[2] - co[0] + 1 - 2 * PS_INSET, co[3] - co[1] + 1 - 2 * PS_INSET);
        return;
    }
    if (ps_es_coop(g_ps_modo)) return;
    int py = ps_panel_y();
    int ob[4];
    ps_marco_obst(ob);
    int practica = pp_es_practica(s);
    int n = practica ? g_ob_practica : g_ps_obst;                /* la práctica no recibe FF13: lo suyo es local */
    if (n == 0xFFFF) {                                           /* nadie eligió: los de la pista que se ve */
        BYTE *dlg = *(BYTE **)(s + 0x10E94);
        n = dlg ? *(WORD *)(dlg + 0x358) : 0;                    /* 0x58F6B8: la pista que dibuja la caja grande */
    }
    ps_imagen_pista(n, x + ob[0] + PS_INSET, py + ob[1] + PS_INSET,
                    ob[2] - ob[0] + 1 - 2 * PS_INSET, ob[3] - ob[1] + 1 - 2 * PS_INSET);
    /* ★ ¿la sala es por EQUIPOS? Se le pregunta al CLIENTE (CooperationMode [cRoom+0x9568] == 0, como 0x58BFF0, sin el
     *   relevo ni el jefe), no a la cola del FF13: el cambio de modo viaja en el FF4B y el server NO reemite el FF13 ahí
     *   (lo borraría, lobby_salas.h_ff4b). ⛔ 09-oct: con la cola, «equipo» -> «solo» dejaba «Victoria» puesto. */
    int por_equipos = *(int *)(s + 0x9568) == 0 && *(int *)(s + 0x9564) != 5 && *(int *)(s + 0x9564) != 4;
    if (!practica && por_equipos) {                              /* sala por equipos: el recuadro de «Victoria» */
        static const int vxy[2] = { PS_VICT_XY }, cxy[2] = { PS_C_VICT_XY };
        int c = ps_es_compacto(g_ps_modo);
        void *spr = *(void **)(s + 0x1CC);                       /* gr_1.spr (0x59A077) */
        if (spr) ((F_PS_CORTE)PSV(0x683FB0))(spr, x + (c ? cxy[0] : vxy[0]), py + (c ? cxy[1] : vxy[1]),
                                             c ? PS_C_CORTE + 1 : PS_CORTE_VICT, 0);
    }
}

static void ps_foto_ventana(BYTE *sala)
{
    BYTE *dlg = *(BYTE **)(sala + 0x10E94);
    g_ps_snap = dlg != NULL;
    if (dlg) {
        g_ps_snap_pista = *(WORD *)(dlg + 0x358);
        g_ps_snap_i364 = *(DWORD *)(dlg + 0x364);
        g_ps_snap_i368 = *(DWORD *)(dlg + 0x368);
    }
}

static int TCS ps_clic(void *sala, int x, int y, int clic)
{
    ps_poner_modo((BYTE *)sala);
    BYTE *sl = (BYTE *)sala;
    if (clic && ps_es_coop(g_ps_modo) && sl && *(int *)(sl + 0x9564) == 4 && !sl[0xA429]) {   /* ★ el cooperativo */
        int cp[4], co[4];
        ps_marcos_coop(cp, co);
        int px = ps_panel_x(), dentro = 0;
        if (x >= px + cp[0] && x <= px + cp[2] && y >= PS_COOP_Y + cp[1] && y <= PS_COOP_Y + cp[3]) dentro = 1;
        if (x >= px + co[0] && x <= px + co[2] && y >= PS_COOP_Y + co[1] && y <= PS_COOP_Y + co[3]) dentro = 2;
        BYTE *normal = *(BYTE **)(sl + 0x10E98);
        if (dentro && normal) {
            *(BYTE **)(sl + 0x10E94) = normal;                   /* la ventana NORMAL, mientras esté abierta */
            g_ps_cambiada = 1;
            ps_foto_ventana(sl);
            g_modo_obst = dentro == 2;
            ((F_PS_VENTANA)PSV(0x58F9B0))(sala);
            apuntar("  [panel_sala] cooperativo: clic en «%s» -> la ventana de pistas normal (hoy: pista %d · obstáculos %d)",
                    dentro == 2 ? "Obstáculos" : "Pista", (int)g_ps_pista, (int)g_ps_obst);
            return 1;
        }
    }
    if (clic && !ps_es_coop(g_ps_modo) && g_ps_modo >= 0 && sala && !*((BYTE *)sala + 0xA429)) {
        int ob[4];
        ps_marco_obst(ob);
        int px = ps_panel_x(), py = ps_panel_y();
        if (x >= px + ob[0] && x <= px + ob[2] && y >= py + ob[1] && y <= py + ob[3]) {
            /* ★ lo que muestra la ventana AHORA: al confirmar se le devuelve, si no la caja de «Pista» (que dibuja
             *   [ventana+0x358]) mostraría la de los obstáculos — y en la práctica, ¡correría en ésa! */
            ps_foto_ventana((BYTE *)sala);
            g_modo_obst = 1;
            ((F_PS_VENTANA)PSV(0x58F9B0))(sala);                 /* la ventana de pistas, la del juego */
            apuntar("  [panel_sala] clic en «Obstáculos»: ventana de pistas en MODO OBSTÁCULOS");
            return 1;
        }
    }
    return ((F_PS_CLIC)PSV(0x586270))(sala, x, y, clic);
}

/* las dos llamadas que mandan el FF1B: en modo obstáculos, con el bit 0x8000 */
static void ps_devolver_ventana(void)
{
    BYTE *sala = *(BYTE **)PSV(0x9314C0);
    BYTE *dlg = sala ? *(BYTE **)(sala + 0x10E94) : NULL;
    if (!g_ps_snap || !dlg) return;
    *(WORD *)(dlg + 0x358) = g_ps_snap_pista;
    *(DWORD *)(dlg + 0x364) = g_ps_snap_i364;
    *(DWORD *)(dlg + 0x368) = g_ps_snap_i368;
    g_ps_snap = 0;
}

static void TCS ps_ff1b(void *red, int pista)
{
    if (g_ps_cambiada && !g_modo_obst) {                         /* el cooperativo: la PISTA del mini-panel */
        BYTE *sala = *(BYTE **)PSV(0x9314C0);
        ps_devolver_ventana();
        ps_devolver_chase(sala);
        apuntar("  [panel_sala] cooperativo: pista %d (FF1B; el server la guarda aparte)", pista);
        ((F_PS_FF1B)PSV(0x5C7880))(red, pista);
        return;
    }
    if (g_modo_obst) {
        g_modo_obst = 0;
        BYTE *sala = *(BYTE **)PSV(0x9314C0);
        ps_devolver_ventana();
        if (pp_es_practica(sala)) {                              /* la práctica no es una sala: nada al server */
            g_ob_practica = (WORD)(pista & 0x7FFF);
            apuntar("  [panel_sala] práctica: obstáculos de la pista %d (local, sin FF1B)", pista & 0x7FFF);
            return;
        }
        apuntar("  [panel_sala] obstáculos elegidos: los de la pista %d (FF1B con 0x8000)", pista & 0x7FFF);
        pista = (pista & 0x7FFF) | 0x8000;
        ps_devolver_chase(sala);
    }
    ((F_PS_FF1B)PSV(0x5C7880))(red, pista);
}

static int ps_rel(DWORD sitio, DWORD destino) { return (int)(destino - ((DWORD)PSV(sitio) + 5)); }

static void panel_sala_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("panel_sala", "activo", 1, ini)) {
        apuntar("  [panel_sala] apagado ([panel_sala] activo=0)");
        return;
    }
    g_ps_base = (BYTE *)GetModuleHandleA(NULL);
    /* ⛔ TODO O NADA: los 30 inmediatos, las 5 llamadas y el final de la lectura del FF13 */
    for (int i = 0; i < PS_NT; i++)
        if ((PS_T[i].tam == 1 ? *(PSV(PS_T[i].va) + PS_T[i].off) : *(DWORD *)(PSV(PS_T[i].va) + PS_T[i].off)) != PS_T[i].orig) {
            apuntar("  [panel_sala] ⛔ %s (0x%08X) no tiene el valor esperado: no se toca nada", PS_T[i].que, PS_T[i].va);
            return;
        }
    static const struct { DWORD va, destino; } LL[] = {
        { 0x5AEEBE, 0x58F360 }, { 0x5A6FEF, 0x586270 }, { 0x58F74F, 0x58D670 }, { 0x58D552, 0x5C7880 }, { 0x5B389E, 0x5C7880 } };
    for (int i = 0; i < 5; i++) {
        BYTE *s = PSV(LL[i].va);
        if (s[0] != 0xE8 || *(int *)(s + 1) != ps_rel(LL[i].va, (DWORD)PSV(LL[i].destino))) {
            apuntar("  [panel_sala] ⛔ la llamada de 0x%08X no es la esperada: no se toca nada", LL[i].va);
            return;
        }
    }
    static const BYTE e_ff13[7] = { 0x32, 0xDB, 0x33, 0xF6, 0x8D, 0x49, 0x00 };   /* xor bl,bl · xor esi,esi · lea ecx,[ecx] */
    if (memcmp(PSV(0x5CD519), e_ff13, 7) != 0) {
        apuntar("  [panel_sala] ⛔ el final de la lectura del FF13 (0x5CD519) no es el esperado: no se toca nada");
        return;
    }
    g_ps_cueva = (BYTE *)VirtualAlloc(NULL, 192, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_ps_cueva) { apuntar("  [panel_sala] ⛔ sin memoria"); return; }
    /* la cola del FF13: esi = el lector. mov word [obst],0xFFFF · mov byte [vict],0xFF · pushad · 2 lecturas · popad ·
     * lo desplazado (xor bl,bl · xor esi,esi) · jmp 0x5CD520 */
    BYTE *k = g_ps_cueva;
    int i = 0;
    k[i++] = 0x66; k[i++] = 0xC7; k[i++] = 0x05; *(DWORD *)(k + i) = (DWORD)&g_ps_obst; i += 4; k[i++] = 0xFF; k[i++] = 0xFF;
    k[i++] = 0xC6; k[i++] = 0x05; *(DWORD *)(k + i) = (DWORD)&g_ps_vict; i += 4; k[i++] = 0xFF;
    k[i++] = 0x66; k[i++] = 0xC7; k[i++] = 0x05; *(DWORD *)(k + i) = (DWORD)&g_ps_pista; i += 4; k[i++] = 0xFF; k[i++] = 0xFF;
    k[i++] = 0xC6; k[i++] = 0x05; *(DWORD *)(k + i) = (DWORD)&g_gr_sala; i += 4; k[i++] = 0x00;     /* asientos = 0 */
    k[i++] = 0xC6; k[i++] = 0x05; *(DWORD *)(k + i) = (DWORD)&g_gr_equipos; i += 4; k[i++] = 0x00;  /* equipos = 0 */
    k[i++] = 0x60;                                                                                  /* pushad */
    k[i++] = 0x6A; k[i++] = 0x02; k[i++] = 0x68; *(DWORD *)(k + i) = (DWORD)&g_ps_obst; i += 4;     /* push 2 · push &obst */
    k[i++] = 0x8B; k[i++] = 0xCE;                                                                   /* mov ecx,esi */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)PSV(0x67D200) - (DWORD)(k + i + 5)); i += 5;
    k[i++] = 0x6A; k[i++] = 0x01; k[i++] = 0x68; *(DWORD *)(k + i) = (DWORD)&g_ps_vict; i += 4;     /* push 1 · push &vict */
    k[i++] = 0x8B; k[i++] = 0xCE;                                                                   /* mov ecx,esi */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)PSV(0x67D200) - (DWORD)(k + i + 5)); i += 5;
    k[i++] = 0x6A; k[i++] = 0x02; k[i++] = 0x68; *(DWORD *)(k + i) = (DWORD)&g_ps_pista; i += 4;    /* push 2 · push &pista */
    k[i++] = 0x8B; k[i++] = 0xCE;                                                                   /* mov ecx,esi */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)PSV(0x67D200) - (DWORD)(k + i + 5)); i += 5;
    /* ★ 10-oct: el 4.º campo, `asientos` u8 (la sala de 12 del 6vs6: grande.c / sala12_vista.c) */
    k[i++] = 0x6A; k[i++] = 0x01; k[i++] = 0x68; *(DWORD *)(k + i) = (DWORD)&g_gr_sala; i += 4;     /* push 1 · push &asientos */
    k[i++] = 0x8B; k[i++] = 0xCE;                                                                   /* mov ecx,esi */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)PSV(0x67D200) - (DWORD)(k + i + 5)); i += 5;
    /* ★ 15-oct: el 5.º, `equipos` u8 (4 = la sala de 12 de 4 equipos: relevo o equipo — EQUIPOS_4.md) */
    k[i++] = 0x6A; k[i++] = 0x01; k[i++] = 0x68; *(DWORD *)(k + i) = (DWORD)&g_gr_equipos; i += 4;  /* push 1 · push &equipos */
    k[i++] = 0x8B; k[i++] = 0xCE;                                                                   /* mov ecx,esi */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)PSV(0x67D200) - (DWORD)(k + i + 5)); i += 5;
    /* ...y en el acto, lo que depende de la sala de 12 ANTES de los FF0C/FF17 que llegan detrás (sala12_vista.c) */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)s12v_tras_ff13 - (DWORD)(k + i + 5)); i += 5;
    k[i++] = 0x61;                                                                                  /* popad */
    k[i++] = 0x32; k[i++] = 0xDB; k[i++] = 0x33; k[i++] = 0xF6;                                     /* xor bl,bl · xor esi,esi */
    k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)PSV(0x5CD520) - (DWORD)(k + i + 5)); i += 5;
    BYTE n13[7] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90 };
    *(int *)(n13 + 1) = (int)((DWORD)k - ((DWORD)PSV(0x5CD519) + 5));
    ps_escribir(0x5CD519, n13, 7);
    /* las 5 llamadas */
    const DWORD mias[5] = { (DWORD)ps_panel, (DWORD)ps_clic, (DWORD)ps_rcoin, (DWORD)ps_ff1b, (DWORD)ps_ff1b };
    for (int j = 0; j < 5; j++) {
        BYTE c[5] = { 0xE8 };
        *(int *)(c + 1) = ps_rel(LL[j].va, mias[j]);
        ps_escribir(LL[j].va, c, 5);
    }
    apuntar("  [panel_sala] ok: el panel sube %d y el Rcoin baja %d · «Obstáculos» (clic + imagen) · la cola del FF13",
            PS_SUBE, PS_ALTO_NUEVO);
}
