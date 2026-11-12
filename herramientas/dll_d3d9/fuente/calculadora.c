/* ═══════════════════════════════════════════════════════════════════════════
 * calculadora.c — LA CALCULADORA DEL CLIENTE 2019, dentro de nuestra DLL
 *
 *   El panel que el 2019 muestra abajo a la izquierda durante la carrera: el PD con
 *   tres decimales, los siete contadores por nota (99/90/80/70/60/50/40~0), la racha
 *   de 99, F9 para esconderlo, y el esconderse con el impulsor.
 *
 *   ★ LA ESPECIFICACION es la sonda de Frida que se probo en vivo el 22-sep:
 *       herramientas/calculadora/sonda_panel.py   (repo «Servidor R2Beat 2013»)
 *     Esto hace EXACTAMENTE lo mismo, sin Frida. La historia, las direcciones y el porque
 *     de cada decision: documentacion/CALCULADORA_2019_EN_EL_2013.md de ese repo.
 *
 *   ⚠ Se INCLUYE desde d3d9_proxy.c (despues de `escribir_bytes`) para compartir
 *     `apuntar()` y `g_carpeta`. No se compila suelta.
 *   ⚠ Necesita `rnr_calculadora.pak` (la figurita) en la carpeta del juego. Sin el pak
 *     no revienta: el motor carga null.bmp, esto lo anota y no dibuja.
 *   ⚠ Perilla: [calculadora] activo=0 en d3d9_proxy.ini la apaga entera (ni engancha).
 *
 *   ⛔ Las trampas que ya se pagaron, en una linea cada una:
 *     · enganchar el MEDIO de una funcion mato al cliente: aca todo va en el BORDE
 *     · los NPC tambien se juzgan: se cuenta solo [obj+0x49] == [[0x9314C8]+0x5d]
 *     · achicar la figurita la deja borrosa: todo se dibuja 1:1
 *     · GetAsyncKeyState no sabe de chats: se mira el cursor del campo de texto
 * ═══════════════════════════════════════════════════════════════════════════ */

#include "calculadora_datos.h"

#define TC __attribute__((thiscall))

/* ── las funciones del juego (todas medidas; ver el doc §1 y §7) ─────────── */
typedef int   (TC *F_JUICIO)(void *self, int juicio, int desvio, int extra);   /* ret 0xc  */
typedef int   (TC *F_HUD)(void *self, int a, int b);                           /* ret 8    */
typedef int   (TC *F_IMPULSO)(void *self);                                     /* ret      */
typedef int   (TC *F_TEXTO_MSG)(void *self, int a, int msg, int wp, int lp);   /* ret 0x10 */
typedef void *(TC *F_C2D_CREAR)(void *self);
typedef int   (TC *F_C2D_CARGAR)(void *self, const char *ruta, const char *prefijo);
typedef void  (TC *F_C2D_RECORTE)(void *self, float x, float y, int u, int v, int w, int h,
                                  float z);
typedef void  (TC *F_C2D_POS)(void *self, int n, int x, int y);
typedef void  (TC *F_C2D_COLOR)(void *self, int n, DWORD argb);
typedef void  (TC *F_C2D_DIBUJAR)(void *self, int n, int banderas);
/* ⚠ cdecl y VARIADICA: declararla de otra forma descuadra la pila (se pago el 14-sep) */
typedef int   (__cdecl *F_PINTAR)(void *obj, int x, int y, int color, int estilo,
                                  const char *fmt, ...);

static BYTE *g_calc_base = NULL;
#define CVA(x) (g_calc_base + ((DWORD)(x) - 0x400000))

static F_JUICIO    g_calc_juicio_real;
static F_HUD       g_calc_hud_real;
static F_IMPULSO   g_calc_impulso_real;
static F_TEXTO_MSG g_calc_texto_real;

/* ── el estado ────────────────────────────────────────────────────────────── */
static char   g_calc_ini[MAX_PATH];
static int    g_calc_caj[11];                   /* indice = puntos/10; el 99 cae en el 10 */
static int    g_calc_notas, g_calc_seguidas, g_calc_mejor;
static long long g_calc_suma;

static BYTE   g_calc_img[0x100];                /* el c2DImage (la clase ocupa 0x40) */
static int    g_calc_img_estado = 0;            /* 0 sin cargar · 1 cargada · -1 fallo */

static double g_calc_x = 0, g_calc_y = 0;
static int    g_calc_oculto = 0;
static int    g_calc_res_w = 0, g_calc_res_h = 0;
static double g_calc_vis = 0, g_calc_ult_cuadro = 0;
static double g_calc_impulso_hasta = 0;
static double g_calc_ult_parpadeo = 0, g_calc_ult_letra = 0;
static double g_calc_moviendo_desde = 0;
static int    g_calc_movio = 0;
static LARGE_INTEGER g_calc_frec;
/* ★ 14-oct · la calculadora del ESPECTADOR (globo_combo.c, PAQUETES_ESPECTADOR.md): el que corre avisa cada nota; el que
 *   mira muestra la del corredor que sigue (la arma con lo que llega) y su conteo propio queda apagado */
static void (*g_calc_al_juzgar)(int p, int reinicio) = NULL;
static void (*g_calc_antes_de_dibujar)(void) = NULL;
static int g_calc_ajena = 0;

#define CALC_ANCHO 131
#define CALC_ALTO  196
#define CALC_ALTO_TOTAL (CALC_CARTEL_1 + CALC_FILA_H)
#define CALC_ANIM_MS 350.0                      /* fundido en su lugar, duracion FIJA */
#define CALC_ANIM_PX 28.0
#define CALC_IMPULSO_MS 2000.0                  /* la receta del 2019: 120 cuadros */
#define CALC_VENTANA_CHAT_MS 700.0
#define CALC_DIGW 7                             /* ancho de un digito de la fuente del juego */

/* los recortes de la figurita — IGUALES a los de armar_textura.py / la sonda */
enum { F_PANEL = 0, F_FILA = 1, F_VER = 2, F_DIG = 3, F_PUNTO = 13, F_PORC = 14, F_TOTAL = 15 };
static const int CALC_DIGX[10] = { 10, 31, 53, 75, 98, 121, 143, 165, 187, 210 };

static double calc_ahora(void)
{
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    return (double)t.QuadPart * 1000.0 / (double)g_calc_frec.QuadPart;
}

static int calc_redondear(double v) { return (int)(v < 0 ? v - 0.5 : v + 0.5); }

static int calc_pantalla(int desplazamiento)   /* +4 ancho, +8 alto */
{
    BYTE *p = *(BYTE **)CVA(0x931498);
    if (!p) return desplazamiento == 4 ? 1024 : 768;
    return *(int *)(p + desplazamiento);
}

/* ═══ 1 · EL CONTEO ══════════════════════════════════════════════════════════
 *   0x505340 juzga CADA nota de CADA corredor. Los puntos de la nota son la
 *   DIFERENCIA del acumulador entre antes y despues (cifrado con XOR contra 0x904210).
 *   ⛔ NO se engancha el medio (0x50544C): mato al cliente el 22-sep. */
static int calc_es_mio(BYTE *obj)
{
    BYTE *partida = *(BYTE **)CVA(0x9314C8);
    if (!partida || !obj) return 0;
    return partida[0x5d] == obj[0x49];
}

static void calc_leer_acum(BYTE *obj, DWORD *num, DWORD *den)
{
    DWORD k = *(DWORD *)CVA(0x904210);
    *num = *(DWORD *)(obj + 0x19c) ^ k;
    *den = *(DWORD *)(obj + 0x1a0) ^ k;
}

static int TC calc_mi_juicio(void *self, int juicio, int desvio, int extra)
{
    BYTE *obj = (BYTE *)self;
    int mio = calc_es_mio(obj);
    DWORD n0 = 0, d0 = 0, n1, d1;
    if (mio) calc_leer_acum(obj, &n0, &d0);
    int r = g_calc_juicio_real(self, juicio, desvio, extra);
    if (!mio) return r;
    if (g_calc_ajena && (*(BYTE **)CVA(0x9314C8))[0xC01]) return r;   /* ★ espectador: la muestra globo_combo.c */
    calc_leer_acum(obj, &n1, &d1);
    /* ★ se resetea SOLO: denominador 1 = primera nota de la cancion */
    if (d1 <= 1) {
        for (int i = 0; i < 11; i++) g_calc_caj[i] = 0;
        g_calc_notas = 0; g_calc_suma = 0; g_calc_seguidas = 0; g_calc_mejor = 0;
        if (g_calc_al_juzgar) g_calc_al_juzgar(0, 1);
    }
    if (d1 == d0 + 1) {
        int p = (int)(n1 - n0);
        int i = p >= 99 ? 10 : p / 10;
        if (i >= 0 && i <= 10) {
            g_calc_caj[i]++; g_calc_notas++; g_calc_suma += p;
            if (p >= 99) { if (++g_calc_seguidas > g_calc_mejor) g_calc_mejor = g_calc_seguidas; }
            else g_calc_seguidas = 0;
            if (g_calc_al_juzgar) g_calc_al_juzgar(p, 0);
        }
    }
    return r;
}

/* ═══ 2 · EL IMPULSOR Y EL CHAT ═════════════════════════════════════════════
 *   0x54DF70: el HUD se entera de que se disparo el impulsor -> 2 s escondido.
 *   0x65C300: cTextField recibe sus mensajes. WM_TIMER con su numero [+0xd0] = el
 *   cursor que parpadea, y SOLO le llega al campo activo (medido en dos carreras). */
static int TC calc_mi_impulso(void *self)
{
    g_calc_impulso_hasta = calc_ahora() + CALC_IMPULSO_MS;
    return g_calc_impulso_real(self);
}

static int TC calc_mi_texto(void *self, int a, int msg, int wp, int lp)
{
    if (msg == 0x102) g_calc_ult_letra = calc_ahora();                         /* WM_CHAR  */
    else if (msg == 0x113 && self && wp == *(int *)((BYTE *)self + 0xd0))      /* WM_TIMER */
        g_calc_ult_parpadeo = calc_ahora();
    return g_calc_texto_real(self, a, msg, wp, lp);
}

static int calc_escribiendo(void)
{
    double t = calc_ahora();
    return t - g_calc_ult_parpadeo < CALC_VENTANA_CHAT_MS || t - g_calc_ult_letra < CALC_VENTANA_CHAT_MS;
}

/* ═══ 3 · LA POSICION: una por resolucion, y las de fabrica ═════════════════ */
static void calc_clave_pos(char *clave) { wsprintfA(clave, "pos_%dx%d", g_calc_res_w, g_calc_res_h); }

/* cada base se lleva a PROPORCION de su pantalla; entre dos se interpola por el ALTO;
 * afuera del rango, la mas cercana. En una base da exacto lo fijado. */
static void calc_fabrica(double *x, double *y)
{
    int W = g_calc_res_w, H = g_calc_res_h;
    if (CALC_N_FABRICA == 0) { *x = 0; *y = H - CALC_ALTO_TOTAL - 10; return; }
    double fx, fy;
    const int (*b)[4] = CALC_FABRICA;
    if (CALC_N_FABRICA == 1 || H <= b[0][1]) {
        fx = (double)b[0][2] / b[0][0]; fy = (double)b[0][3] / b[0][1];
    } else if (H >= b[CALC_N_FABRICA - 1][1]) {
        const int *u = b[CALC_N_FABRICA - 1];
        fx = (double)u[2] / u[0]; fy = (double)u[3] / u[1];
    } else {
        int i = 0;
        while (b[i + 1][1] < H) i++;
        double t = (double)(H - b[i][1]) / (b[i + 1][1] - b[i][1]);
        double ax = (double)b[i][2] / b[i][0],     ay = (double)b[i][3] / b[i][1];
        double bx = (double)b[i + 1][2] / b[i + 1][0], by = (double)b[i + 1][3] / b[i + 1][1];
        fx = ax + (bx - ax) * t; fy = ay + (by - ay) * t;
    }
    *x = calc_redondear(fx * W);
    *y = calc_redondear(fy * H);
}

static int g_calc_escala;
static int g_calc_lz_w, g_calc_lz_h;
static void calc_acotar(void)
{
    int tope = CALC_FILA_W > CALC_ANCHO ? CALC_FILA_W : CALC_ANCHO;   /* la fila crece a la derecha */
    int alto = CALC_ALTO_TOTAL;
    if (g_calc_lz_w) { tope = g_calc_lz_w; alto = g_calc_lz_h; }      /* con el lienzo: botones incluidos */
    tope = tope * g_calc_escala / 100;
    alto = alto * g_calc_escala / 100;
    double mx = g_calc_res_w - tope, my = g_calc_res_h - alto;
    if (g_calc_x > mx) g_calc_x = mx;
    if (g_calc_y > my) g_calc_y = my;
    if (g_calc_x < 0) g_calc_x = 0;
    if (g_calc_y < 0) g_calc_y = 0;
}

/* ★★ GUARDAR SIN FRENAR EL JUEGO (28-sep-2026)
 *   `WritePrivateProfileStringA` reescribe el .ini ENTERO y el juego espera a que termine: en
 *   una PC con disco lento o antivirus, apretar F9 o soltar una tecla de mover daba un tirón
 *   (lo encontró la revisión por los reportes de "tirones con la calculadora", anonimo03 28-sep).
 *   ⇒ Se copia lo que hay que guardar y se escribe en OTRO hilo (el pool de Windows). Si llegan
 *     varios seguidos, sólo escribe el último (la generación), y de a uno por vez (la sección). */
typedef struct {
    char clave[32], valor[32];
    int borrar_pos, oculto, fijo, escala;
    LONG gen;
} CALC_GUARDADO;
static volatile LONG g_calc_gen = 0;
static CRITICAL_SECTION g_calc_cs_ini;
static int g_calc_fijo = 0;                     /* I: la calculadora no se mueve              */
static int g_calc_escala = 100;                 /* O / P: el tamaño, en %                     */

static DWORD WINAPI calc_guardar_hilo(void *p)
{
    CALC_GUARDADO *g = (CALC_GUARDADO *)p;
    EnterCriticalSection(&g_calc_cs_ini);
    if (g->gen == g_calc_gen) {                 /* si ya hay uno más nuevo, éste no escribe */
        char n[16];
        WritePrivateProfileStringA("calculadora", g->clave, g->borrar_pos ? NULL : g->valor, g_calc_ini);
        WritePrivateProfileStringA("calculadora", "oculto", g->oculto ? "1" : "0", g_calc_ini);
        WritePrivateProfileStringA("calculadora", "fijo", g->fijo ? "1" : "0", g_calc_ini);
        wsprintfA(n, "%d", g->escala);
        WritePrivateProfileStringA("calculadora", "escala", n, g_calc_ini);
    }
    LeaveCriticalSection(&g_calc_cs_ini);
    HeapFree(GetProcessHeap(), 0, g);
    return 0;
}

static void calc_guardar_ex(int borrar_pos)
{
    CALC_GUARDADO *g = (CALC_GUARDADO *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*g));
    if (!g) return;
    calc_clave_pos(g->clave);
    wsprintfA(g->valor, "%d,%d", calc_redondear(g_calc_x), calc_redondear(g_calc_y));
    g->borrar_pos = borrar_pos;
    g->oculto = g_calc_oculto;
    g->fijo = g_calc_fijo;
    g->escala = g_calc_escala;
    g->gen = InterlockedIncrement(&g_calc_gen);
    if (!QueueUserWorkItem(calc_guardar_hilo, g, WT_EXECUTEDEFAULT))
        calc_guardar_hilo(g);                   /* sin pool: se escribe acá, como antes */
}

static void calc_guardar(void) { calc_guardar_ex(0); }

static void calc_ubicar(void)
{
    char clave[32], valor[32];
    calc_clave_pos(clave);
    GetPrivateProfileStringA("calculadora", clave, "", valor, sizeof(valor), g_calc_ini);
    int x = 0, y = 0, propia = 0;
    if (valor[0]) {
        const char *c = valor;
        while (*c >= '0' && *c <= '9') x = x * 10 + (*c++ - '0');
        if (*c == ',') {
            c++;
            while (*c >= '0' && *c <= '9') y = y * 10 + (*c++ - '0');
            propia = 1;
        }
    }
    if (propia) { g_calc_x = x; g_calc_y = y; }
    else calc_fabrica(&g_calc_x, &g_calc_y);
    calc_acotar();
    apuntar("  [calculadora] %dx%d -> x=%d y=%d (%s)", g_calc_res_w, g_calc_res_h,
            calc_redondear(g_calc_x), calc_redondear(g_calc_y),
            propia ? "la que dejo el jugador" : "de fabrica");
}

/* ═══ 4 · LAS TECLAS ═══════════════════════════════════════════════════════════
 * ★ 04-oct, anonimo03: TODO en letras de la fila de abajo — Z fijar · X más grande · C más chica ·
 *   V izquierda · B derecha · N arriba · M abajo. ⛔ Los NÚMEROS (fila de arriba y numérico,
 *   incluido el 5) quedan LIBRES para el juego. El «volver a la de fábrica» (era el 0) se queda
 *   sin tecla por ahora. Antes (28-sep): I O P y 4 6 8 2 0 arriba y en el numérico. */
static int g_calc_medir = 0, g_calc_forzar_viejo = 0;     /* ver §7 · LA MEDICIÓN */
static const int CALC_VK[10][2] = {
    { VK_F9, 0 },            /* 0 esconder / mostrar */
    { 'V', 0 },              /* 1 izquierda          */
    { 'B', 0 },              /* 2 derecha            */
    { 'N', 0 },              /* 3 arriba             */
    { 'M', 0 },              /* 4 abajo              */
    { 0, 0 },                /* 5 de fabrica: SIN TECLA (era el 0; los números quedan libres) */
    { 'Z', 0 },              /* 6 fijar / soltar     */
    { 'X', 0 },              /* 7 más grande         */
    { 'C', 0 },              /* 8 más chica          */
    { VK_F10, 0 },           /* 9 SÓLO midiendo: dibujo nuevo <-> viejo */
};
#define CALC_TECLAS 10
static int g_calc_antes[CALC_TECLAS];

/* los tamaños posibles, en %: de a pasos. ⚠ lo que se ve depende de cómo se escale (ver
 * calc_dibujar); acá sólo se guarda la elección. */
static const int CALC_ESCALAS[] = { 75, 100, 125, 150, 175, 200 };
#define CALC_N_ESCALAS ((int)(sizeof(CALC_ESCALAS) / sizeof(CALC_ESCALAS[0])))
static void calc_acotar(void);
static void calc_cambiar_escala(int paso)
{
    int i = 0;
    while (i < CALC_N_ESCALAS - 1 && CALC_ESCALAS[i] < g_calc_escala) i++;
    i += paso;
    if (i < 0) i = 0;
    if (i >= CALC_N_ESCALAS) i = CALC_N_ESCALAS - 1;
    if (CALC_ESCALAS[i] == g_calc_escala) return;
    g_calc_escala = CALC_ESCALAS[i];
    calc_acotar();
    calc_guardar();
}

static int calc_baja(int t)
{
    for (int i = 0; i < 2; i++)
        if (CALC_VK[t][i] && (GetAsyncKeyState(CALC_VK[t][i]) & 0x8000)) return 1;
    return 0;
}
static int calc_recien(int t)
{
    int b = calc_baja(t), fue = g_calc_antes[t];
    g_calc_antes[t] = b;
    return b && !fue;
}

/* ★ ¿la ventana de adelante es la del juego? (anonimo03, 28-sep: "que i-o-p ignore si no tengo el
 *   foco en el juego"). GetAsyncKeyState lee el teclado de TODO Windows: escribiendo en otra
 *   ventana, una "p" achicaba la calculadora. Vale para todas las teclas del panel. */
static int calc_con_foco(void)
{
    HWND w = GetForegroundWindow();
    DWORD pid = 0;
    if (w) GetWindowThreadProcessId(w, &pid);
    return pid == GetCurrentProcessId();
}

static void calc_teclado(double dt)
{
    if (!calc_con_foco()) {
        for (int t = 0; t < CALC_TECLAS; t++) calc_recien(t);           /* se consumen los flancos */
        g_calc_moviendo_desde = 0;
        if (g_calc_movio) { g_calc_movio = 0; calc_guardar(); }
        return;
    }
    if (calc_recien(0)) { g_calc_oculto = !g_calc_oculto; calc_guardar(); }
    if (calc_recien(9) && g_calc_medir) {
        g_calc_forzar_viejo = !g_calc_forzar_viejo;
        apuntar("  [medir] F10 -> dibujo %s", g_calc_forzar_viejo ? "VIEJO (17 dibujos)" : "NUEVO (lienzo)");
    }
    /* con el chat abierto los numeros son TEXTO: se consumen los flancos y nada se mueve */
    if (calc_escribiendo()) {
        for (int t = 1; t < CALC_TECLAS; t++) calc_recien(t);
        g_calc_moviendo_desde = 0;
        if (g_calc_movio) { g_calc_movio = 0; calc_guardar(); }
        return;
    }
    /* I: fijar / soltar. Fija la POSICIÓN y el TAMAÑO (anonimo03, 28-sep): con la calculadora
     * fija no hacen nada las teclas de mover, el 0, ni O / P. */
    if (calc_recien(6)) { g_calc_fijo = !g_calc_fijo; calc_guardar(); }
    /* O / P: más grande / más chica, de a un paso */
    {
        int mas = calc_recien(7), menos = calc_recien(8);         /* las dos, siempre: flancos */
        if (mas != menos && !g_calc_fijo) calc_cambiar_escala(mas ? +1 : -1);
    }
    if (g_calc_fijo) {
        for (int t = 1; t < 6; t++) calc_recien(t);
        g_calc_moviendo_desde = 0;
        return;
    }
    if (calc_recien(5)) {
        calc_fabrica(&g_calc_x, &g_calc_y);
        calc_acotar();
        calc_guardar_ex(1);                                                   /* olvidar la propia */
    }
    int dx = calc_baja(2) - calc_baja(1);
    int dy = calc_baja(4) - calc_baja(3);
    if (dx || dy) {
        double t = calc_ahora();
        if (!g_calc_moviendo_desde) { g_calc_moviendo_desde = t; g_calc_x += dx; g_calc_y += dy; }
        else {
            double v = (t - g_calc_moviendo_desde > 330 ? 240.0 : 60.0) * dt / 1000.0;
            g_calc_x += dx * v; g_calc_y += dy * v;
        }
        calc_acotar();
        g_calc_movio = 1;
    } else {
        g_calc_moviendo_desde = 0;
        if (g_calc_movio) { g_calc_movio = 0; calc_guardar(); }
    }
}

/* ═══ 5 · EL DIBUJO: la figurita del 2019, por el motor del 2013 (c2DImage) ═══ */
static void calc_cargar_figurita(void)
{
    static const int cortes_fijos[3][4] = {
        { 7, 7, CALC_ANCHO, CALC_ALTO },
        { CALC_FILA_X, CALC_FILA_Y, CALC_FILA_W, CALC_FILA_H },
        { CALC_VER_X,  CALC_VER_Y,  CALC_FILA_W, CALC_FILA_H },
    };
    ((F_C2D_CREAR)CVA(0x64E560))(g_calc_img);
    if (!((F_C2D_CARGAR)CVA(0x64E1E0))(g_calc_img, "rnr_game/image/calculadora.tga", NULL)) {
        g_calc_img_estado = -1;
        apuntar("  [calculadora] ⛔ no encontre la figurita (falta rnr_calculadora.pak): no dibujo");
        return;
    }
    F_C2D_RECORTE rec = (F_C2D_RECORTE)CVA(0x64EC40);
    for (int i = 0; i < 3; i++)
        rec(g_calc_img, 0, 0, cortes_fijos[i][0], cortes_fijos[i][1], cortes_fijos[i][2],
            cortes_fijos[i][3], 0.5f);
    for (int d = 0; d < 10; d++) rec(g_calc_img, 0, 0, CALC_DIGX[d], 395, 14, 23, 0.5f);
    rec(g_calc_img, 0, 0, 231, 405, 12, 12, 0.5f);          /* el punto */
    rec(g_calc_img, 0, 0, 249, 396, 25, 22, 0.5f);          /* el %     */
    int n = (int)((*(DWORD *)(g_calc_img + 0x1c) - *(DWORD *)(g_calc_img + 0x18)) / 0x50);
    g_calc_img_estado = (n == F_TOTAL) ? 1 : -1;
    apuntar("  [calculadora] figurita cargada: %d recortes (esperados %d)%s", n, F_TOTAL,
            n == F_TOTAL ? "" : "  ⛔ NO DIBUJO");
}

static void calc_figura(int n, int x, int y, DWORD argb)
{
    ((F_C2D_POS)CVA(0x64D990))(g_calc_img, n, x, y);
    ((F_C2D_COLOR)CVA(0x64E710))(g_calc_img, n, argb);      /* alfa < 255 prende la mezcla */
    ((F_C2D_DIBUJAR)CVA(0x64EE40))(g_calc_img, n, 0);
}

/* ═══ 5-bis · ★★ EL LIENZO: el panel entero en UNA figurita (28-sep-2026) ═══════════
 *
 *   ⛔ POR QUÉ. anonimo03: jugadores con PC modestas tienen TIRONES con la calculadora visible.
 *     Con el panel a la vista se le sumaban al motor ~17 dibujos por cuadro: el cuadro, 6-7
 *     dígitos del PD, la fila de carteles (figuritas, 1 DrawPrimitiveUP cada una) y 8 conteos
 *     con `pintar`, que es lo MÁS caro: cada texto abre y cierra un ID3DXSprite que GUARDA y
 *     DEVUELVE todo el estado del dispositivo (medido: 0x6355D0).
 *   ★ AHORA: la figurita del atlas se lee UNA vez a memoria; cuando algo cambia (una nota,
 *     fijar), el panel se arma en memoria y se copia al "lienzo" (otra textura del pak); en
 *     cada cuadro se dibuja SOLO el lienzo: 1 dibujo. Y el tamaño (O / P) es el del lienzo.
 *   Medido en el exe para esto (ver documentacion/CALCULADORA_2019_EN_EL_2013.md §9):
 *     · textura de un c2DImage: [img+4] = handle -> 0x4099E0(mgr=[0x931570], h) -> entrada
 *       (+0x48 != 0 = animada) -> 0x441420(mgr, h, 0) = IDirect3DTexture9*. El motor la crea
 *       MANAGED, 1 nivel, y él mismo le hace LockRect al cargar.
 *     · tamaño en pantalla: 0x64DB90(this, n, ancho, alto); filtro: 0x64DC00(this, n, 1) =
 *       LINEAR (por defecto el motor dibuja en POINT: por eso "achicar" se veía comido).
 *   ⚠ Si algo de esto falla (formato, bloqueo, lo que sea), se vuelve SOLO al dibujo de antes. */
#define CALC_LZ 256
typedef struct { UINT Format, Type, Usage, Pool, MSType, MSQuality, Width, Height; } CALC_DESC;
typedef struct { INT Pitch; void *pBits; } CALC_BLOQUEO;
typedef long (__stdcall *T_DESC)(void *tex, UINT nivel, CALC_DESC *d);                 /* vt 17 */
typedef long (__stdcall *T_BLOQUEAR)(void *tex, UINT nivel, CALC_BLOQUEO *r, const RECT *rc,
                                     DWORD banderas);                                  /* vt 19 */
typedef long (__stdcall *T_SOLTAR)(void *tex, UINT nivel);                            /* vt 20 */
typedef BYTE *(TC *F_TEX_ENTRADA)(void *mgr, DWORD h);
typedef void *(TC *F_TEX_D3D)(void *mgr, DWORD h, int cual);
typedef void  (TC *F_C2D_TAMANO)(void *self, int n, int ancho, int alto);
typedef void  (TC *F_C2D_FILTRO)(void *self, int n, BYTE lineal);

static DWORD *g_calc_atlas = NULL;              /* la figurita, A8R8G8B8, leída una vez */
static int    g_calc_atlas_w = 0, g_calc_atlas_h = 0;
static BYTE   g_calc_lz[0x100];                 /* el c2DImage del lienzo */
static int    g_calc_lz_estado = 0;             /* 0 sin cargar · 1 listo · -1 no se usa */
static DWORD  g_calc_lz_px[CALC_LZ * CALC_LZ];  /* el panel armado en memoria */
static DWORD  g_calc_lz_firma = 0;              /* lo que tiene el lienzo AHORA */
static void  *g_calc_lz_tex = NULL;             /* si la textura cambia (Reset), se rearma */
static int    g_calc_lz_w = 0, g_calc_lz_h = 0; /* lo usado del lienzo (para acotar) */

static void *calc_textura(BYTE *img)
{
    void *mgr = *(void **)CVA(0x931570);
    DWORD h = *(DWORD *)(img + 4);
    if (!mgr || !h) return NULL;
    BYTE *ent = ((F_TEX_ENTRADA)CVA(0x4099E0))(mgr, h);
    if (!ent || *(DWORD *)(ent + 0x48)) return NULL;          /* ⚠ 0x441420 no mira el NULL */
    return ((F_TEX_D3D)CVA(0x441420))(mgr, h, 0);
}

static int calc_desc(void *tex, CALC_DESC *d)
{
    void **vt = tex ? *(void ***)tex : NULL;
    return vt && ((T_DESC)vt[17])(tex, 0, d) == 0;
}

/* la figurita del atlas, a memoria (una vez) */
static int calc_leer_atlas(void)
{
    void *tex = calc_textura(g_calc_img);
    CALC_DESC d;
    if (!tex || !calc_desc(tex, &d) || d.Format != 21 /* A8R8G8B8 */) {
        apuntar("  [calculadora] lienzo: no pude leer la figurita (tex=%p fmt=%u) -> dibujo de antes",
                tex, tex ? d.Format : 0);
        return 0;
    }
    void **vt = *(void ***)tex;
    CALC_BLOQUEO b;
    if (((T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, 0x10 /* READONLY */) != 0) {
        apuntar("  [calculadora] lienzo: la figurita no se deja leer (pool %u) -> dibujo de antes", d.Pool);
        return 0;
    }
    g_calc_atlas = (DWORD *)HeapAlloc(GetProcessHeap(), 0, d.Width * d.Height * 4);
    if (g_calc_atlas)
        for (UINT y = 0; y < d.Height; y++)
            CopyMemory(g_calc_atlas + y * d.Width, (BYTE *)b.pBits + y * b.Pitch, d.Width * 4);
    ((T_SOLTAR)vt[20])(tex, 0);
    if (!g_calc_atlas) return 0;
    g_calc_atlas_w = (int)d.Width;
    g_calc_atlas_h = (int)d.Height;
    return 1;
}

static void calc_cargar_lienzo(void)
{
    g_calc_lz_estado = -1;
    if (!calc_leer_atlas()) return;
    ((F_C2D_CREAR)CVA(0x64E560))(g_calc_lz);
    if (!((F_C2D_CARGAR)CVA(0x64E1E0))(g_calc_lz, "rnr_game/image/calculadora_lienzo.tga", NULL)) {
        apuntar("  [calculadora] lienzo: el pak no trae calculadora_lienzo.tga -> dibujo de antes");
        return;
    }
    ((F_C2D_RECORTE)CVA(0x64EC40))(g_calc_lz, 0, 0, 0, 0, CALC_LZ, CALC_LZ, 0.5f);
    void *tex = calc_textura(g_calc_lz);
    CALC_DESC d;
    if (!tex || !calc_desc(tex, &d) || d.Format != 21 || d.Width != CALC_LZ || d.Height != CALC_LZ) {
        apuntar("  [calculadora] lienzo: la textura no es la esperada -> dibujo de antes");
        return;
    }
    g_calc_lz_estado = 1;
    apuntar("  [calculadora] ★ lienzo listo: el panel se dibuja en UNA figurita (pool %u)", d.Pool);
}

/* pegar un recorte del atlas {x,y,w,h} en el lienzo, mezclando por alfa (src over dst) */
static void calc_pegar(int sx, int sy, int w, int h, int dx, int dy)
{
    for (int j = 0; j < h; j++) {
        int yy = dy + j, ys = sy + j;
        if (yy < 0 || yy >= CALC_LZ || ys < 0 || ys >= g_calc_atlas_h) continue;
        for (int i = 0; i < w; i++) {
            int xx = dx + i, xs = sx + i;
            if (xx < 0 || xx >= CALC_LZ || xs < 0 || xs >= g_calc_atlas_w) continue;
            DWORD s = g_calc_atlas[ys * g_calc_atlas_w + xs];
            DWORD sa = s >> 24;
            if (!sa) continue;
            DWORD *p = &g_calc_lz_px[yy * CALC_LZ + xx];
            if (sa == 255) { *p = s; continue; }
            DWORD dcol = *p, da = dcol >> 24;
            DWORD ra = sa + da * (255 - sa) / 255;
            if (!ra) continue;
            DWORD r = 0;
            for (int sh = 0; sh < 24; sh += 8) {
                DWORD sc = (s >> sh) & 255, dc = (dcol >> sh) & 255;
                DWORD c = (sc * sa + dc * da * (255 - sa) / 255) / ra;
                r |= (c > 255 ? 255 : c) << sh;
            }
            *p = r | (ra << 24);
        }
    }
}
static void calc_pegar_p(const int *p4, int dx, int dy) { calc_pegar(p4[0], p4[1], p4[2], p4[3], dx, dy); }

/* la columna de botones (anonimo03, 28-sep, la maqueta «B»): pegada al borde DERECHO del cuadro,
 * alineada con su borde de abajo. ⛔ Encima de la F9 ya no se puede: con la fila compacta la F9
 * queda debajo del cuadro, y la columna se metía adentro (lo vio anonimo03 en la maqueta). */
#define CALC_BOT_X (CALC_ANCHO + 2)
#define CALC_BOT_DY (CALC_P_TECLA_I[3] + 2)
#define CALC_BOT_Y0 (CALC_ALTO - 3 * CALC_BOT_DY)

/* arma el panel en memoria (lo MISMO que dibujaba calc_dibujar, pero pegado) */
static void calc_armar_lienzo(void)
{
    ZeroMemory(g_calc_lz_px, sizeof(g_calc_lz_px));
    calc_pegar(7, 7, CALC_ANCHO, CALC_ALTO, 0, 0);                        /* el cuadro */
    /* el PD: la misma cuenta que calc_numero_pd */
    char s[16];
    if (!g_calc_notas) lstrcpyA(s, "0.000");
    else {
        long long t = g_calc_suma * 1000 / g_calc_notas;
        wsprintfA(s, "%d.%03d", (int)(t / 1000), (int)(t % 1000));
    }
    int w = 22;
    for (char *c = s; *c; c++) w += (*c == '.') ? 8 : 12;
    int x = 127 - w;
    for (char *c = s; *c; c++) {
        if (*c == '.') { calc_pegar(231, 405, 12, 12, x - 2, CALC_PD_Y + 12); x += 8; }
        else { calc_pegar(CALC_DIGX[*c - '0'], 395, 14, 23, x, CALC_PD_Y); x += 12; }
    }
    calc_pegar(249, 396, 25, 22, x - 1, CALC_PD_Y + 1);
    /* los 8 conteos: donde los ponía `pintar` (borde derecho 125, 7 px por dígito) */
    int bajo = g_calc_caj[0] + g_calc_caj[1] + g_calc_caj[2] + g_calc_caj[3] + g_calc_caj[4];
    int vals[8] = { g_calc_mejor, g_calc_caj[10], g_calc_caj[9], g_calc_caj[8],
                    g_calc_caj[7], g_calc_caj[6], g_calc_caj[5], bajo };
    for (int i = 0; i < 8; i++) {
        int n = wsprintfA(s, "%d", vals[i]);
        int xx = 125 - n * CALC_DIGW, yy = 43 + calc_redondear(i * 18.7) - 1;
        for (int k = 0; k < n; k++)
            calc_pegar(CALC_P_DIG_BLANCO[0] + (s[k] - '0') * (CALC_P_DIG_BLANCO[2] + 1), CALC_P_DIG_BLANCO[1],
                       CALC_P_DIG_BLANCO[2], CALC_P_DIG_BLANCO[3], xx + k * CALC_DIGW - 1, yy);
    }
    /* ★ los botones nuevos (anonimo03, 28-sep): I fijar · O agrandar · P achicar */
    const int *teclas[3] = { CALC_P_TECLA_I, CALC_P_TECLA_O, CALC_P_TECLA_P };
    const int *rotulos[3] = { g_calc_fijo ? CALC_P_ROT_FIJADO : CALC_P_ROT_FIJAR,
                              CALC_P_ROT_AGRANDAR, CALC_P_ROT_ACHICAR };
    int ancho = CALC_FILA_W > CALC_ANCHO ? CALC_FILA_W : CALC_ANCHO;
    for (int i = 0; i < 3; i++) {
        int y = CALC_BOT_Y0 + i * CALC_BOT_DY;                        /* arriba de la tecla */
        calc_pegar_p(teclas[i], CALC_BOT_X, y);
        calc_pegar_p(rotulos[i], CALC_BOT_X + teclas[i][2] + 2, y - (rotulos[i][3] - teclas[i][3]) / 2);
        int fin = CALC_BOT_X + teclas[i][2] + 2 + rotulos[i][2];
        if (fin > ancho) ancho = fin;
    }
    calc_pegar(CALC_FILA_X, CALC_FILA_Y, CALC_FILA_W, CALC_FILA_H, 0, CALC_CARTEL_1);   /* la fila */
    g_calc_lz_w = ancho > CALC_LZ ? CALC_LZ : ancho;
    g_calc_lz_h = CALC_ALTO_TOTAL;
}

/* un resumen de todo lo que se ve: si no cambió, no se toca la textura */
static DWORD calc_firma(void)
{
    DWORD f = 2166136261u;
    int v[16] = { g_calc_notas, (int)g_calc_suma, (int)(g_calc_suma >> 32), g_calc_mejor, g_calc_fijo };
    for (int i = 0; i < 11; i++) v[5 + i] = g_calc_caj[i];
    for (int i = 0; i < 16; i++) { f ^= (DWORD)v[i]; f *= 16777619u; }
    return f | 1;                                                  /* nunca 0 = "vacío" */
}

/* sube el panel al lienzo SÓLO si cambió algo (o si la textura se rehízo) */
static int calc_actualizar_lienzo(void)
{
    void *tex = calc_textura(g_calc_lz);
    if (!tex) return 0;
    DWORD f = calc_firma();
    if (f == g_calc_lz_firma && tex == g_calc_lz_tex) return 1;
    CALC_DESC d;
    if (!calc_desc(tex, &d)) return 0;
    calc_armar_lienzo();
    void **vt = *(void ***)tex;
    CALC_BLOQUEO b;
    /* MANAGED (lo normal): se bloquea y listo; DEFAULT (el modo 9Ex del proxy la deja DYNAMIC):
     * sólo con DISCARD, reescribiendo todo — que es lo que hacemos igual */
    DWORD banderas = d.Pool == 0 ? 0x2000 /* DISCARD */ : 0;
    if (((T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, banderas) != 0) {
        static int dicho = 0;
        if (!dicho) { dicho = 1; apuntar("  [calculadora] ⛔ lienzo: no se deja escribir (pool %u) -> dibujo de antes", d.Pool); }
        g_calc_lz_estado = -1;
        return 0;
    }
    for (int y = 0; y < CALC_LZ; y++)
        CopyMemory((BYTE *)b.pBits + y * b.Pitch, g_calc_lz_px + y * CALC_LZ, CALC_LZ * 4);
    ((T_SOLTAR)vt[20])(tex, 0);
    g_calc_lz_firma = f;
    g_calc_lz_tex = tex;
    return 1;
}

/* una figurita de un c2DImage, al tamaño `esc` % (con filtro suave si no es 1:1) */
static void calc_figura_esc(BYTE *img, int n, int w, int h, int x, int y, DWORD argb, int esc)
{
    ((F_C2D_TAMANO)CVA(0x64DB90))(img, n, w * esc / 100, h * esc / 100);
    ((F_C2D_FILTRO)CVA(0x64DC00))(img, n, (BYTE)(esc != 100));
    ((F_C2D_POS)CVA(0x64D990))(img, n, x, y);
    ((F_C2D_COLOR)CVA(0x64E710))(img, n, argb);
    ((F_C2D_DIBUJAR)CVA(0x64EE40))(img, n, 0);
}

/* el PD con los digitos del 2019 A TAMAÑO REAL, alineado a la derecha contra el borde */
static void calc_numero_pd(int x0, int y0, DWORD col)
{
    char s[16];
    if (!g_calc_notas) lstrcpyA(s, "0.000");
    else {
        long long t = g_calc_suma * 1000 / g_calc_notas;
        wsprintfA(s, "%d.%03d", (int)(t / 1000), (int)(t % 1000));
    }
    int w = 22;
    for (char *c = s; *c; c++) w += (*c == '.') ? 8 : 12;
    int x = x0 + 127 - w;
    for (char *c = s; *c; c++) {
        if (*c == '.') { calc_figura(F_PUNTO, x - 2, y0 + CALC_PD_Y + 12, col); x += 8; }
        else { calc_figura(F_DIG + (*c - '0'), x, y0 + CALC_PD_Y, col); x += 12; }
    }
    calc_figura(F_PORC, x - 1, y0 + CALC_PD_Y + 1, col);
}

static void calc_dibujar(void)
{
    double t = calc_ahora();
    double dt = g_calc_ult_cuadro ? t - g_calc_ult_cuadro : 16;
    /* ★ si el HUD no corrio por mas de 1 s es una cancion NUEVA: entra con su animacion */
    if (dt > 1000) { g_calc_vis = 0; dt = 16; }
    g_calc_ult_cuadro = t;

    if (!g_calc_img_estado) calc_cargar_figurita();
    int W = calc_pantalla(4), H = calc_pantalla(8);
    if (W != g_calc_res_w || H != g_calc_res_h) {   /* al empezar, o si cambio la resolucion */
        g_calc_res_w = W; g_calc_res_h = H;
        calc_ubicar();
    }
    calc_teclado(dt);

    int por_impulso = t < g_calc_impulso_hasta;
    int quiere = !g_calc_oculto && !por_impulso;
    double paso = dt / CALC_ANIM_MS;
    g_calc_vis = quiere ? (g_calc_vis + paso > 1 ? 1 : g_calc_vis + paso)
                        : (g_calc_vis - paso < 0 ? 0 : g_calc_vis - paso);
    if (g_calc_img_estado != 1) return;

    int X = calc_redondear(g_calc_x), Y = calc_redondear(g_calc_y);
    double e = 1 - (1 - g_calc_vis) * (1 - g_calc_vis);    /* frena al llegar */
    int x0 = calc_redondear(g_calc_x - (1 - e) * CALC_ANIM_PX);
    DWORD a = (DWORD)calc_redondear(255 * e);
    DWORD col = (a << 24) | 0xFFFFFF;

    /* ★ el lienzo: UN dibujo, al tamaño elegido. Si no está (o falla), el camino de antes. */
    if (g_calc_lz_estado == 0) calc_cargar_lienzo();
    int esc = g_calc_escala;
    if (g_calc_lz_estado == 1 && !g_calc_forzar_viejo) {
        if (g_calc_vis > 0 && calc_actualizar_lienzo())
            calc_figura_esc(g_calc_lz, 0, CALC_LZ, CALC_LZ, x0, Y, col, esc);
        if (g_calc_vis == 0 && g_calc_oculto && !por_impulso)
            calc_figura_esc(g_calc_img, F_VER, CALC_FILA_W, CALC_FILA_H,
                            X, Y + CALC_CARTEL_1 * esc / 100, 0xFFFFFFFF, esc);
        if (g_calc_lz_estado == 1) return;
    }

    if (g_calc_vis > 0) {
        calc_figura(F_PANEL, x0, Y, col);
        calc_numero_pd(x0, Y, col);
        int bajo = g_calc_caj[0] + g_calc_caj[1] + g_calc_caj[2] + g_calc_caj[3] + g_calc_caj[4];
        int vals[8] = { g_calc_mejor, g_calc_caj[10], g_calc_caj[9], g_calc_caj[8],
                        g_calc_caj[7], g_calc_caj[6], g_calc_caj[5], bajo };
        void *obj = *(void **)CVA(0x93149C);
        F_PINTAR pintar = (F_PINTAR)CVA(0x63A640);
        for (int i = 0; i < 8; i++) {
            char s[16];
            int n = wsprintfA(s, "%d", vals[i]);
            if (obj) pintar(obj, x0 + 125 - n * CALC_DIGW, Y + 43 + calc_redondear(i * 18.7),
                            (int)col, 0, "%s", s);
        }
        calc_figura(F_FILA, x0, Y + CALC_CARTEL_1, col);
    }
    /* "F9 Ver PD" en el lugar de la F9, con el panel escondido por F9 (no por el impulsor) */
    if (g_calc_vis == 0 && g_calc_oculto && !por_impulso)
        calc_figura(F_VER, X, Y + CALC_CARTEL_1, 0xFFFFFFFF);
}

/* 0x54A480 dibuja la precision en carrera, una vez por cuadro: el panel va DESPUES */
static int TC calc_mi_hud(void *self, int a, int b)
{
    int r = g_calc_hud_real(self, a, b);
    if (g_calc_antes_de_dibujar) g_calc_antes_de_dibujar();
    calc_dibujar();
    return r;
}

/* ═══ 7 · LA MEDICIÓN (28-sep-2026) — ¿cuánto le cuesta el panel a la PC? ═══════════════
 *   anonimo03: "aún no medimos si los dibujados ya no afectarían a PC modestas". Se cronometra
 *   0x639780, el vaciado de la cola 2D (lo llama 0x498AF5 con ecx=[0x93149C], sin argumentos,
 *   y termina en `ret`): ahí se dibuja TODO lo 2D del cuadro — el HUD y la calculadora. Cada
 *   5 s se anota el promedio y el peor cuadro, y en qué MODO estaba el panel:
 *       NUEVO = el lienzo (1 dibujo) · VIEJO = los ~17 de antes (F10) · OCULTO = sin panel (F9)
 *   La diferencia contra OCULTO es lo que cuesta el panel. En una PC rápida los números son
 *   chicos: lo que vale es la PROPORCIÓN nuevo/viejo, que en una PC modesta se mantiene.
 *   ⚠ Sólo con `[calculadora] medir=1` en d3d9_proxy.ini: si no, ni se engancha. */
typedef void (TC *F_VACIAR)(void *self);
static F_VACIAR g_calc_vaciar_real;
static double g_med_suma = 0, g_med_max = 0, g_med_desde = 0;
static int    g_med_n = 0, g_med_modo = -1;
static const char *CALC_MODOS[3] = { "OCULTO", "VIEJO ", "NUEVO " };

static void calc_med_anotar(void)
{
    if (g_med_n && g_med_modo >= 0)
        apuntar("  [medir] %s  capa 2D: %4d us promedio · peor %5d us · %d cuadros",
                CALC_MODOS[g_med_modo], calc_redondear(g_med_suma / g_med_n),
                calc_redondear(g_med_max), g_med_n);
    g_med_suma = g_med_max = 0;
    g_med_n = 0;
}

static void TC calc_mi_vaciar(void *self)
{
    double t0 = calc_ahora();
    g_calc_vaciar_real(self);
    double us = (calc_ahora() - t0) * 1000.0;
    if (t0 - g_calc_ult_cuadro > 250) {                 /* fuera de carrera: no cuenta */
        if (g_med_n) calc_med_anotar();
        g_med_modo = -1;
        return;
    }
    int modo = g_calc_vis <= 0 ? 0 : (g_calc_lz_estado == 1 && !g_calc_forzar_viejo ? 2 : 1);
    if (modo != g_med_modo || t0 - g_med_desde > 5000) {
        calc_med_anotar();
        g_med_modo = modo;
        g_med_desde = t0;
    }
    g_med_suma += us;
    if (us > g_med_max) g_med_max = us;
    g_med_n++;
}

/* ═══ 6 · LOS ENGANCHES — en el BORDE, con trampolin, verificando antes ══════ */
typedef struct {
    DWORD va; BYTE espera[12]; int n; void *destino; void **real; const char *que;
} CALC_ENGANCHE;

static int calc_verificar(const CALC_ENGANCHE *e)
{
    BYTE *sitio = CVA(e->va);
    for (int i = 0; i < e->n; i++)
        if (sitio[i] != e->espera[i]) {
            char hex[48]; hex[0] = 0;
            for (int j = 0; j < e->n && j < 12; j++) wsprintfA(hex + lstrlenA(hex), "%02X ", sitio[j]);
            apuntar("  [calculadora] ⛔ %s: en 0x%08X hay [%s] y esperaba otra cosa",
                    e->que, e->va, hex);
            return 0;
        }
    return 1;
}

static int calc_enganchar(const CALC_ENGANCHE *e)
{
    BYTE *sitio = CVA(e->va);
    BYTE *tramp = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!tramp) return 0;
    /* el trampolin: los bytes originales (instrucciones enteras, sin saltos relativos:
     * comprobado para los cuatro) + un salto de vuelta al resto de la funcion */
    CopyMemory(tramp, sitio, e->n);
    tramp[e->n] = 0xE9;
    *(DWORD *)(tramp + e->n + 1) = (DWORD)((sitio + e->n) - (tramp + e->n + 5));
    DWORD viejo = 0;
    if (!VirtualProtect(sitio, e->n, PAGE_EXECUTE_READWRITE, &viejo)) {
        VirtualFree(tramp, 0, MEM_RELEASE);
        return 0;
    }
    sitio[0] = 0xE9;
    *(DWORD *)(sitio + 1) = (DWORD)((BYTE *)e->destino - (sitio + 5));
    for (int i = 5; i < e->n; i++) sitio[i] = 0x90;
    VirtualProtect(sitio, e->n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), sitio, e->n);
    *e->real = tramp;
    return 1;
}

static void calculadora_iniciar(void)
{
    lstrcpyA(g_calc_ini, g_carpeta);
    lstrcatA(g_calc_ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("calculadora", "activo", 1, g_calc_ini)) {
        apuntar("  [calculadora] apagada ([calculadora] activo=0)");
        return;
    }
    g_calc_base = (BYTE *)GetModuleHandleA(NULL);
    QueryPerformanceFrequency(&g_calc_frec);
    g_calc_oculto = (int)GetPrivateProfileIntA("calculadora", "oculto", 0, g_calc_ini);
    g_calc_fijo   = (int)GetPrivateProfileIntA("calculadora", "fijo", 0, g_calc_ini);
    g_calc_escala = (int)GetPrivateProfileIntA("calculadora", "escala", 100, g_calc_ini);
    InitializeCriticalSection(&g_calc_cs_ini);

    CALC_ENGANCHE e[4] = {
        { 0x00505340, { 0x53, 0x8A, 0x5C, 0x24, 0x08 }, 5,
          (void *)calc_mi_juicio,  (void **)&g_calc_juicio_real,  "el juicio de la nota" },
        { 0x0054A480, { 0x83, 0xEC, 0x1C, 0xA1, 0x70, 0xB2, 0x91, 0x00 }, 8,
          (void *)calc_mi_hud,     (void **)&g_calc_hud_real,     "el HUD de carrera" },
        { 0x0054DF70, { 0x83, 0xEC, 0x08, 0x53, 0x55 }, 5,
          (void *)calc_mi_impulso, (void **)&g_calc_impulso_real, "el aviso del impulsor" },
        { 0x0065C300, { 0x8B, 0x44, 0x24, 0x08, 0x05, 0x00, 0xFF, 0xFF, 0xFF }, 9,
          (void *)calc_mi_texto,   (void **)&g_calc_texto_real,   "el campo de texto (chat)" },
    };
    /* ★ o se ponen LOS CUATRO o ninguno: medio panel (dibujar sin contar, contar sin
     *   saber del chat) seria peor que no tenerlo. */
    for (int i = 0; i < 4; i++)
        if (!calc_verificar(&e[i])) {
            apuntar("  [calculadora] ⛔ el exe no es el esperado: NO engancho nada");
            return;
        }
    for (int i = 0; i < 4; i++)
        if (!calc_enganchar(&e[i])) {
            apuntar("  [calculadora] ⛔ no pude enganchar %s (quedan %d puestos)", e[i].que, i);
            return;
        }
    apuntar("  [calculadora] ★ enganchada: juicio, HUD, impulsor y chat  (oculto=%d)",
            g_calc_oculto);
    /* §7 · la medición, sólo si se pide */
    g_calc_medir = (int)GetPrivateProfileIntA("calculadora", "medir", 0, g_calc_ini);
    g_calc_forzar_viejo = (int)GetPrivateProfileIntA("calculadora", "viejo", 0, g_calc_ini);
    if (g_calc_medir) {
        CALC_ENGANCHE m = { 0x00639780, { 0x81, 0xEC, 0x98, 0x01, 0x00, 0x00, 0x53 }, 7,
                            (void *)calc_mi_vaciar, (void **)&g_calc_vaciar_real, "el vaciado 2D" };
        if (calc_verificar(&m) && calc_enganchar(&m))
            apuntar("  [medir] ★ cronometrando la capa 2D (F10 = dibujo nuevo <-> viejo, F9 = oculto)");
    }
}
