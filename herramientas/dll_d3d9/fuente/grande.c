/* grande.c — la CARRERA GRANDE: más de 6 corredores en la misma pista (el 6vs6, 10-oct-2026)
 *
 *   anonimo03: «12 en una misma pista · el juego sabe manejar huecos · por eso existe en el coreano · no cortar y pegar,
 *   pero sí examinar el motor y entenderlo». Investigación: documentacion/MODO_6VS6.md §7.
 *
 *   ★ CÓMO LO HACE EL COREANO (medido con Frida): con su bandera de «carrera en grupo» (cGame+0x10B8) el bucle que
 *     crea los corredores hace 25 en vez de 6, y los bucles que los recorren van hasta N en vez de 6. Los arreglos
 *     fijos de 6 de cGame NO los toca (ninguno de esos bucles los usa: sólo el vector de corredores, que crece).
 *
 *   ⇒ ACÁ, lo mismo con NUESTRA bandera: el server manda N en el campo 3 del FF25 (`corredores` u8, ver
 *     documentacion/FF25_LOADGAME_BYTES.md) y antes de que la carga arme los corredores se cambia el 6 por N en:
 *       · la CREACIÓN de los corredores (0x4FA1D2) y los 34 bucles «del 0 al 5» que recorren el vector
 *         (la lista la DERIVA herramientas/carrera_grande.py del exe prístino → grande_datos.h)
 *       · el reparto a lo ancho: `(asiento - 3.0 + 0.5) * 223.5` (la largada y el carril) pasa a
 *         `(asiento - N/2 + 0.5) * (223.5 * 6 / N)`: los N entran en el ancho de la pista de siempre (el coreano
 *         usa una pista ANCHA, la 50 «Flexible»; el 2013 no la tiene).
 *     Con N ausente (o 0, o fuera de 7..12) todo vuelve a 6: una carrera normal no cambia en nada.
 *
 *   El campo 3 lo lee el salto del FF25 de obstaculos.c (el mismo camino, a continuación del campo 2).
 *   [grande] activo=0 lo apaga · forzar=N (prueba sin server) · dejar=0x4F3A20,... (bucles que quedan en 6, para
 *   bisecar si algo se rompe).
 */
#include "grande_datos.h"

#define GRV(x) (g_gr_base + ((DWORD)(x) - 0x400000))
#define GR_TOPE 12

static BYTE  *g_gr_base = NULL;
static int    g_gr_activo = 0;
static BYTE   g_gr_n = 0;                  /* el campo 3 del FF25 de ESTA carrera (0 = normal) */
static volatile DWORD g_gr_carreras = 0;   /* sube con cada FF25: el cartel de 12 sabe de qué carrera son sus datos */
static volatile BYTE g_gr_sala = 0;        /* el 4.º campo de la cola del FF13 (panel_sala.c): 12 = la sala de 12 */
static volatile BYTE g_gr_equipos = 0;     /* ★ 15-oct: el 5.º campo (panel_sala.c): 4 = la sala de 12 es de 4 EQUIPOS */
static int    g_gr_forzar = 0;
static int    g_gr_puesto = 6;             /* lo que está escrito ahora en el exe */
static double g_gr_mitad = 3.0;            /* los f-op del reparto leen ESTOS (redirigidos al iniciar) */
static double g_gr_paso = 223.5;
static DWORD  g_gr_dejar[16];

/* ★ PRUEBA 1 (anonimo03, 10-oct): «la carrera empezó, todos muy apegados, pero sólo fuimos 6». Los 12 corredores se
 *   CREARON (el log lo dice) pero la carga sólo le da jugador a 6. Dos razones, en la carga (0x4FA3F4…0x4FA719),
 *   que recorre el padrón de la sala (el std::map de [0x931660], clave = asiento en nodo+0xC):
 *     · `cmp eax,6` / `mov [esp+0x54],6` (0x4FA4E1 / 0x4FA4EA): el asiento más alto se recorta a 6
 *     · `cmp byte [nodo+0xC3],0` (0x4FA5E8): el que tiene la marca de MIRÓN no corre. Esa marca la pone el alta de
 *       un ocupante (0x528C52: `cmp byte [esi],6 · jb`): todo asiento ≥ 6 entra como espectador.
 *   ⇒ los dos 6 de la carga van a N, y al llegar el FF25 se le borra la marca a los asientos 6..N-1. */
#define GR_PADRON_CMP 0x4FA4E3                 /* el 6 de `cmp eax,6` */
#define GR_PADRON_MOV 0x4FA4EE                 /* el 6 (DWORD) de `mov dword [esp+0x54],6` */
static const BYTE GR_BUSCAR_BYTES[8] = { 0x83, 0xEC, 0x10, 0x53, 0x8B, 0x5C, 0x24, 0x1C };   /* el comienzo de 0x436240 */
typedef struct { DWORD cont; BYTE *nodo; } GR_ITER;
typedef void (__fastcall *F_GR_BUSCAR)(void *mapa, void *nada, GR_ITER *out, BYTE *clave);   /* 0x436240, thiscall */
static int    g_gr_ndejar = 0;

/* ★ PRUEBA 2 (anonimo03, 10-oct): «ahora sí cargaron los 12» — y la lista de la izquierda dibujó tarjetas de más con
 *   basura («Bono Rc», textos en coreano, estrellas). La tarjeta de cada corredor es 0x55A9C0(a0, posición, ASIENTO)
 *   y adentro usa arreglos del HUD de 6 por asiento: el texto del nombre `[hud + asiento*0xD0 + 0x4CC]` (6 × 0xD0,
 *   0x559C67) y el corte `asiento + 4` (1P..6P). Con el asiento 6..11 ESCRIBE el nombre fuera del arreglo (pisa
 *   otros textos del HUD: por eso salían) ⇒ ⛔ no se puede dejar así. Por ahora sólo se dibujan las tarjetas de los
 *   asientos 0..5; los 3 llamadores (0x4F308D, 0x4F30C7, 0x4F314C) pasan por acá. */
typedef void (__fastcall *F_GR_TARJETA)(void *hud, void *nada, int a0, int pos, int asiento);
static const DWORD GR_TARJETA_LLAMA[3] = { 0x4F308D, 0x4F30C7, 0x4F314C };
static int g_gr_tarjetas_saltadas = 0;

/* ★ PRUEBA 3 (anonimo03, 10-oct): «los nombres sobre la cabeza salen sólo en 6» (en carrera y en el podio). Los nombres
 *   NO se escriben cada cuadro: al cargar, 0x4F1B90 los pinta UNA vez en una textura de 128×256 (cGame+0x1C, un
 *   c2DImage), una fila de 20 px por asiento: el nombre en las filas 0..5 (cortes 0..5) y la 2.ª línea (el título,
 *   0x44F100) en las 6..11 (cortes 6..11). Y el que los dibuja sobre la cabeza (0x4EDF20 / 0x4EE1A0) usa el corte
 *   «asiento» y «asiento + 6». Con 12: la textura a 128×512, los dos bucles a 12 filas y el «+6» a «+12».
 *     · 0x4F1C2A  push 0x100 (el alto de la textura)                    → 0x200
 *     · 0x4F1E89  add edi,0x14 · inc ebx · cmp edi,0x78 · jl  (13 B)    → cueva: cmp edi,[g_gr_fila]
 *     · 0x4F1E96  xor ebx,ebx · lea edi,[ebx+0x78]            (5 B)     → cueva: mov edi,[g_gr_fila]
 *       (los dos llevan un imm8 con signo: 0xF0 no entra, por eso van por cueva)
 *     · 0x4F1F28  el 0xF0 (imm32) de `cmp edi,0xF0`                      → 2·N·0x14
 *     · 0x4EE00E / 0x4EE25F  el 6 de `add edi,6`                         → N */
#define GR_NOM_ALTO   0x4F1C2B
#define GR_NOM_FIN1   0x4F1E89
#define GR_NOM_INI2   0x4F1E96
#define GR_NOM_FIN2   0x4F1F28
static const DWORD GR_NOM_MAS6[2] = { 0x4EE00E, 0x4EE25F };
static const BYTE GR_NOM_FIN1_BYTES[13] = { 0x83, 0xC7, 0x14, 0x43, 0x83, 0xFF, 0x78, 0x0F, 0x8C, 0xAA, 0xFE, 0xFF, 0xFF };
static const BYTE GR_NOM_INI2_BYTES[5] = { 0x33, 0xDB, 0x8D, 0x7B, 0x78 };
static DWORD  g_gr_fila = 0x78;            /* N·0x14: dónde termina el 1.er bucle y empieza el 2.º */
static int    g_gr_nombres = 0;            /* 1 = las cuevas están puestas */

/* ★ UN CARRIL POR JUGADOR (anonimo03, 10-oct: «darle un carril a cada jugador/npc — estamos muy muy apretados»). Hasta acá
 *   los 12 entraban en el ancho de 6 (carril 111.75). `herramientas/pista_ancha.py` arma, para las pistas que tienen
 *   versión ancha, `backNN/xxx_12.bin` (el piso de 6 carriles DUPLICADO lado a lado = 12 carriles de 223.5, lo de los
 *   costados corrido afuera), un pak por pista: `R2Beat/rnr_bg/backNN_12.pak`. Acá: al cargar la pista (0x4EFAA2 lee el «Model» del
 *   <Bg> de stage_lt.txt con 0x678160), en la carrera de 12, si existe la ancha se carga ESA y el carril vuelve a 223.5
 *   (los 12 a la distancia de siempre). Sin la versión ancha, todo queda como antes (apretados en 6).
 *   [grande] ancha=0 lo apaga. */
#define GR_MODELO_LLAMA 0x4EFAA2
typedef const char *(TCK *F_GR_ATRIB)(void *nodo, void *cadena);                  /* 0x678160, ret 4 */
typedef void *(__cdecl *F_GR_ABRIR)(const char *ruta, int modo, int b);            /* 0x67A360 */
typedef void  (__cdecl *F_GR_CERRAR)(void *f);                                     /* 0x67A0A0 */
static char   g_gr_modelo[96];
static int    g_gr_ancha = 1;              /* el ini */
static int    g_gr_en_ancha = 0;           /* 1 = esta carrera corre en la pista ancha */

static const char *__fastcall gr_modelo(void *nodo, void *nada, void *cadena)
{
    (void)nada;
    const char *m = ((F_GR_ATRIB)GRV(0x678160))(nodo, cadena);
    g_gr_en_ancha = 0;
    if (!g_gr_ancha || g_gr_puesto <= 6 || !m) return m;
    int n = lstrlenA(m);
    /* «backNN/xxx.bin» → «backNN/xxx_12.bin» (el mismo nombre que arma pista_ancha.py: cada pista tiene el suyo,
     *   track08.bin, zoo_town.bin, china.bin…) */
    if (n < 5 || n > 80 || lstrcmpiA(m + n - 4, ".bin") != 0) return m;
    char ruta[128];
    lstrcpynA(g_gr_modelo, m, n - 4 + 1);
    lstrcatA(g_gr_modelo, "_12.bin");
    /* ⛔ 1.ª prueba: con «rnr_bg/» delante NO la encuentra — los paks de rnr_bg/ se montan SIN la carpeta (medido:
     *   «back11/track.bin» SÍ, «rnr_bg/back11/track.bin» no). Se pregunta como la pide el propio <Bg>. */
    lstrcpyA(ruta, g_gr_modelo);
    void *f = ((F_GR_ABRIR)GRV(0x67A360))(ruta, 0x8000, 1);
    if (!f) {
        apuntar("  [grande] ⚠ pista %s: SIN versión ancha (%s): los de afuera corren fuera del piso", m, ruta);
        return m;
    }
    ((F_GR_CERRAR)GRV(0x67A0A0))(f);
    g_gr_en_ancha = 1;
    g_gr_paso = 223.5;                     /* ★ 12 carriles de los de siempre */
    apuntar("  [grande] ★ pista ANCHA: %s → %s (carril 223.5, %d carriles)", m, g_gr_modelo, g_gr_puesto);
    return g_gr_modelo;
}

/* ★ LA META (anonimo03: «el arco de la meta necesita cubrir los extremos de los carriles»): el «Finish» del <Bg> (0x4EFE4E,
 *   el mismo 0x678160) pasa a «backNN/xxx_12.md9» si existe (pista_ancha.py lo arma con el mismo ensanche). */
#define GR_META_LLAMA 0x4EFE4E
static char g_gr_meta[96];

static const char *__fastcall gr_meta(void *nodo, void *nada, void *cadena)
{
    (void)nada;
    const char *m = ((F_GR_ATRIB)GRV(0x678160))(nodo, cadena);
    if (!g_gr_ancha || g_gr_puesto <= 6 || !m) return m;
    int n = lstrlenA(m);
    if (n < 5 || n > 80 || lstrcmpiA(m + n - 4, ".md9") != 0) return m;
    lstrcpynA(g_gr_meta, m, n - 4 + 1);
    lstrcatA(g_gr_meta, "_12.md9");
    void *f = ((F_GR_ABRIR)GRV(0x67A360))(g_gr_meta, 0x8000, 1);
    if (!f) {
        apuntar("  [grande] ⚠ meta %s: sin versión ancha", m);
        return m;
    }
    ((F_GR_CERRAR)GRV(0x67A0A0))(f);
    apuntar("  [grande] ★ meta ANCHA: %s → %s", m, g_gr_meta);
    return g_gr_meta;
}

/* ★ LA CÁMARA DEL FINAL (anonimo03: «al llegar a la meta cambia de sentido, de ver la espalda a ir girando hasta estar de
 *   frente · va a tener que alejarse para que se vean los 12»). Es una animación de la cámara [0x9314D4] (0x645A10,
 *   thiscall, ret 0x20): (modo, ojo final, mira final, arriba final, cuadros, control 1, control 2, tipo) — el cuadro
 *   que arma es {ojo actual, OJO NUEVO, mira actual, MIRA NUEVA, arriba actual, ARRIBA NUEVO, control 1, control 2}
 *   (+0x10/+0x1C/+0x28/+0x34/+0x40/+0x4C/+0x58/+0x64). En multijugador el final mira al CENTRO de la pista (x = 0):
 *   con 12 se veían 7. La llaman las 3 ramas de «llegué a la meta» del corredor (0x504C7B, 0x509EA4, 0x50BABB).
 *   ⇒ en la carrera de 12, el ojo final y los dos puntos de control se ALEJAN de la mira ×[grande] camara_meta
 *   (milésimas, 2100: anonimo03 probó 1800, «casi perfecto, un poquito más»). */
typedef void (TCK *F_GR_CAM_ANIM)(void *cam, int modo, float *ojo, float *mira, float *arriba, int cuadros,
                                   float *c1, float *c2, int tipo);
static const DWORD GR_CAM_META[3] = { 0x504C7B, 0x509EA4, 0x50BABB };
static float g_gr_cam_k = 2.1f;

static void gr_alejar(float *dst, const float *v, const float *mira, float k)
{
    for (int i = 0; i < 3; i++) dst[i] = mira[i] + (v[i] - mira[i]) * k;
}

static void __fastcall gr_camara_meta(void *cam, void *nada, int modo, float *ojo, float *mira, float *arriba,
                                      int cuadros, float *c1, float *c2, int tipo)
{
    (void)nada;
    float o2[3], a2[3], b2[3];
    if (g_gr_puesto > 6 && ojo && mira) {
        gr_alejar(o2, ojo, mira, g_gr_cam_k);
        if (c1) gr_alejar(a2, c1, mira, g_gr_cam_k);
        if (c2) gr_alejar(b2, c2, mira, g_gr_cam_k);
        apuntar("  [grande] cámara de la meta: ojo (%d,%d,%d) → (%d,%d,%d), mira (%d,%d,%d) ×%d/1000",
                (int)ojo[0], (int)ojo[1], (int)ojo[2], (int)o2[0], (int)o2[1], (int)o2[2],
                (int)mira[0], (int)mira[1], (int)mira[2], (int)(g_gr_cam_k * 1000));
        ((F_GR_CAM_ANIM)GRV(0x645A10))(cam, modo, o2, mira, arriba, cuadros, c1 ? a2 : NULL, c2 ? b2 : NULL, tipo);
        return;
    }
    ((F_GR_CAM_ANIM)GRV(0x645A10))(cam, modo, ojo, mira, arriba, cuadros, c1, c2, tipo);
}

static void __fastcall gr_tarjeta(void *hud, void *nada, int a0, int pos, int asiento)
{
    (void)nada;
    if ((asiento & 0xFF) >= 6) { g_gr_tarjetas_saltadas++; return; }
    ((F_GR_TARJETA)GRV(0x55A9C0))(hud, NULL, a0, pos, asiento);
}

static int gr_se_deja(DWORD a)
{
    for (int i = 0; i < g_gr_ndejar; i++)
        if (g_gr_dejar[i] == a || g_gr_dejar[i] == a - 2) return 1;
    return 0;
}

static int gr_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(GRV(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(GRV(va), b, n);
    VirtualProtect(GRV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), GRV(va), n);
    return 1;
}

/* pone N en los 35 «6» y el reparto a lo ancho para N corredores */
static void gr_aplicar(int n)
{
    if (n < 7 || n > GR_TOPE) n = 6;
    int dejados = 0;
    for (int i = 0; i < (int)(sizeof(GR_SEIS) / sizeof(GR_SEIS[0])); i++) {
        BYTE v = (BYTE)n;
        if (i > 0 && gr_se_deja(GR_SEIS[i])) { v = 6; dejados++; }
        gr_escribir(GR_SEIS[i], &v, 1);
    }
    {
        BYTE b = (BYTE)n;
        DWORD d = (DWORD)n;
        gr_escribir(GR_PADRON_CMP, &b, 1);
        gr_escribir(GR_PADRON_MOV, &d, 4);
    }
    if (g_gr_nombres) {                    /* los nombres de la cabeza: una fila por corredor */
        DWORD alto = n > 6 ? 0x200 : 0x100, fin2 = 2u * n * 0x14;
        BYTE mas = (BYTE)n;
        g_gr_fila = (DWORD)n * 0x14;
        gr_escribir(GR_NOM_ALTO, &alto, 4);
        gr_escribir(GR_NOM_FIN2, &fin2, 4);
        for (int i = 0; i < 2; i++) gr_escribir(GR_NOM_MAS6[i], &mas, 1);
    }
    g_gr_mitad = n / 2.0;
    /* ★ con pista ancha, el carril de siempre YA desde el FF25. ⛔ 1.ª versión: lo cambiaba gr_modelo al cargar la
     *   pista, pero los obstáculos (back%03d.txt) se arman ANTES: los corredores quedaban cada uno en su carril y los
     *   obstáculos de los 12 apretados en el medio (anonimo03, 10-oct, la autopista). Las 26 pistas tienen su versión
     *   ancha (pista_ancha.py); si a alguna le faltara, gr_modelo lo avisa en el log. */
    g_gr_paso = (n > 6 && g_gr_ancha) ? 223.5 : 223.5 * 6.0 / n;
    int mirones = 0;
    if (n > 6) {
        /* los asientos 6..n-1 dejan de ser «mirones» para la carga: corren */
        BYTE *mgr = *(BYTE **)GRV(0x931660);
        if (mgr) {
            BYTE *cabeza = *(BYTE **)(mgr + 0x18);
            for (int s = 6; s < n; s++) {
                GR_ITER it = { 0, NULL };
                BYTE clave = (BYTE)s;
                ((F_GR_BUSCAR)GRV(0x436240))(mgr, NULL, &it, &clave);
                if (it.nodo && it.nodo != cabeza && it.nodo[0xC3]) { it.nodo[0xC3] = 0; mirones++; }
            }
        }
    }
    if (n != g_gr_puesto || n != 6)
        apuntar("  [grande] carrera de %d corredores: creación + %d bucles + la carga a %d%s · %d mirones pasan a correr"
                " · reparto mitad=%d/10 carril=%d/100",
                n, (int)(sizeof(GR_SEIS) / sizeof(GR_SEIS[0])) - 1 - dejados, n,
                dejados ? " (algunos dejados en 6 por el ini)" : "", mirones,
                (int)(g_gr_mitad * 10), (int)(g_gr_paso * 100));
    g_gr_puesto = n;
}

/* la llama el salto del FF25 (obstaculos.c), dentro de un pushad, después de leer el campo 3 */
static void __cdecl grande_tras_ff25(void)
{
    g_gr_carreras++;
    if (!g_gr_activo) return;
    gr_aplicar(g_gr_forzar ? g_gr_forzar : g_gr_n);
}

/* ★★ 17-oct · EL QUE ABANDONA EN LA DE 12 (anonimo03: «jugador13 cae, los demás viven, pero su char sigue saliendo en la
 *   partida… el juego tiene una forma nativa de removerlo»). La forma nativa ES el FF0E: en carrera lo atiende
 *   0x4FC6E0 (cGame vtbl+0x2C), que lo saca del plantel (0x4F24C0) y, SÓLO SI SU ASIENTO ES < 6 (`cmp bl,6` en
 *   0x4FC979), saca su personaje de la pista (0x50A140: [+0x54] = 1 y lo da de baja). En la de 12 el de los asientos
 *   6..11 quedaba borrado del plantel pero corriendo ⇒ los demás se caían al dibujar su nombre (AV en 0x635362, prod
 *   16-oct: la sala de jugador16; jugador13 estaba en el asiento 11). Sin el FF0E (el arreglo 80 del server) quedaba de
 *   fantasma hasta el final.
 *   ⇒ Se compara contra el TAMAÑO REAL del vector de corredores [esi+0xA08] (6 en la normal, 12 en la grande): en la de 6
 *     queda igual que de fábrica (el que mira, en 6..11, sigue sin tocarse), en la de 12 sale el que se fue. */
#define GR_ABANDONO 0x004FC979
static int g_gr_abandono = 0;
static void gr_abandono(void)
{
    static const BYTE esp[5] = { 0x80, 0xFB, 0x06, 0x73, 0x16 };     /* cmp bl,6 · jae 0x4FC994 */
    if (memcmp(GRV(GR_ABANDONO), esp, 5) != 0 || memcmp(GRV(0x4FC97E), "\x0F\xB6\xC3", 3) != 0) {
        apuntar("  [grande] ⚠ el abandono en carrera (0x4FC979) no es el esperado: el de los asientos 6..11 no sale");
        return;
    }
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return;
    int i = 0;
    k[i++] = 0x0F; k[i++] = 0xB6; k[i++] = 0xC3;                                     /* movzx eax,bl          */
    k[i++] = 0x8B; k[i++] = 0x96; *(DWORD *)(k + i) = 0xA08 + 0x10; i += 4;           /* mov edx,[esi+0xA18]   */
    k[i++] = 0x2B; k[i++] = 0x96; *(DWORD *)(k + i) = 0xA08 + 0x0C; i += 4;           /* sub edx,[esi+0xA14]   */
    k[i++] = 0xC1; k[i++] = 0xFA; k[i++] = 0x02;                                     /* sar edx,2  (= tamaño) */
    k[i++] = 0x3B; k[i++] = 0xC2;                                                    /* cmp eax,edx           */
    k[i++] = 0x0F; k[i++] = 0x83; *(int *)(k + i) = (int)((DWORD)GRV(0x4FC994) - (DWORD)(k + i + 4)); i += 4;  /* jae */
    k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)GRV(0x4FC97E) - (DWORD)(k + i + 5)); i += 5;              /* jmp */
    BYTE s[5] = { 0xE9, 0, 0, 0, 0 };
    *(int *)(s + 1) = (int)((DWORD)k - ((DWORD)GRV(GR_ABANDONO) + 5));
    g_gr_abandono = gr_escribir(GR_ABANDONO, s, 5);
    if (g_gr_abandono)
        apuntar("  [grande] ★ el que abandona en carrera sale de la pista en cualquier asiento (0x4FC979: < corredores, no < 6)");
}

static void grande_iniciar(void)
{
    char ini[MAX_PATH], dejar[256];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("grande", "activo", 1, ini)) {
        apuntar("  [grande] apagado ([grande] activo=0)");
        return;
    }
    g_gr_base = (BYTE *)GetModuleHandleA(NULL);
    g_gr_forzar = GetPrivateProfileIntA("grande", "forzar", 0, ini);
    GetPrivateProfileStringA("grande", "dejar", "", dejar, sizeof(dejar), ini);
    for (char *p = dejar; *p && g_gr_ndejar < 16;) {
        while (*p == ' ' || *p == ',') p++;
        if (!*p) break;
        g_gr_dejar[g_gr_ndejar++] = strtoul(p, &p, 16);
    }
    /* la guarda: cada «6» tiene que ser un 6 y cada f-op tiene que leer el 3.0 / el 223.5 de siempre */
    for (int i = 0; i < (int)(sizeof(GR_SEIS) / sizeof(GR_SEIS[0])); i++) {
        BYTE *b = GRV(GR_SEIS[i]);
        if (b[0] != 6 || b[-2] != 0x83) {
            apuntar("  [grande] ⛔ el exe no es el esperado en 0x%06X (%02X %02X %02X): no se toca nada",
                    GR_SEIS[i] - 2, b[-2], b[-1], b[0]);
            return;
        }
    }
    if (*GRV(GR_PADRON_CMP) != 6 || *GRV(GR_PADRON_CMP - 2) != 0x83 || *(DWORD *)GRV(GR_PADRON_MOV) != 6 ||
        *GRV(GR_PADRON_MOV - 4) != 0xC7 || memcmp(GRV(0x436240), GR_BUSCAR_BYTES, 8) != 0) {
        apuntar("  [grande] ⛔ la carga de los corredores (0x4FA4E1) o la búsqueda del padrón no son las esperadas");
        return;
    }
    for (int i = 0; i < (int)(sizeof(GR_MITAD) / sizeof(GR_MITAD[0])); i++)
        if (*(DWORD *)GRV(GR_MITAD[i] + 2) != GR_DIR_TRES - 0x400000 + (DWORD)g_gr_base) {
            apuntar("  [grande] ⛔ el reparto (0x%06X) no lee el 3.0: no se toca nada", GR_MITAD[i]);
            return;
        }
    for (int i = 0; i < (int)(sizeof(GR_PASO) / sizeof(GR_PASO[0])); i++)
        if (*(DWORD *)GRV(GR_PASO[i] + 2) != GR_DIR_PASO - 0x400000 + (DWORD)g_gr_base) {
            apuntar("  [grande] ⛔ el carril (0x%06X) no lee el 223.5: no se toca nada", GR_PASO[i]);
            return;
        }
    for (int i = 0; i < 3; i++) {
        BYTE *c = GRV(GR_TARJETA_LLAMA[i]);
        if (c[0] != 0xE8 || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)GRV(0x55A9C0)) {
            apuntar("  [grande] ⛔ la tarjeta del HUD (0x%06X) no llama a 0x55A9C0: no se toca nada", GR_TARJETA_LLAMA[i]);
            return;
        }
    }
    for (int i = 0; i < 3; i++) {
        int rel = (int)((DWORD)gr_tarjeta - ((DWORD)GRV(GR_TARJETA_LLAMA[i]) + 5));
        gr_escribir(GR_TARJETA_LLAMA[i] + 1, &rel, 4);
    }
    /* los nombres de la cabeza: las dos cuevas (con g_gr_fila = 0x78 hacen lo mismo que el original) */
    if (*(DWORD *)GRV(GR_NOM_ALTO) == 0x100 && *GRV(GR_NOM_ALTO - 1) == 0x68 && *(DWORD *)GRV(GR_NOM_FIN2) == 0xF0 &&
        memcmp(GRV(GR_NOM_FIN1), GR_NOM_FIN1_BYTES, 13) == 0 && memcmp(GRV(GR_NOM_INI2), GR_NOM_INI2_BYTES, 5) == 0 &&
        *GRV(GR_NOM_MAS6[0]) == 6 && *GRV(GR_NOM_MAS6[1]) == 6 && *GRV(GR_NOM_MAS6[0] - 2) == 0x83 &&
        *GRV(GR_NOM_MAS6[1] - 2) == 0x83) {
        BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (k) {
            int i = 0;
            BYTE *c1 = k;
            k[i++] = 0x83; k[i++] = 0xC7; k[i++] = 0x14;                                    /* add edi,0x14 */
            k[i++] = 0x43;                                                                  /* inc ebx */
            k[i++] = 0x3B; k[i++] = 0x3D; *(DWORD *)(k + i) = (DWORD)&g_gr_fila; i += 4;    /* cmp edi,[g_gr_fila] */
            k[i++] = 0x0F; k[i++] = 0x8C; *(int *)(k + i) = (int)((DWORD)GRV(0x4F1D40) - (DWORD)(k + i + 4)); i += 4;
            k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)GRV(0x4F1E96) - (DWORD)(k + i + 5)); i += 5;
            BYTE *c2 = k + i;
            k[i++] = 0x33; k[i++] = 0xDB;                                                   /* xor ebx,ebx */
            k[i++] = 0x8B; k[i++] = 0x3D; *(DWORD *)(k + i) = (DWORD)&g_gr_fila; i += 4;    /* mov edi,[g_gr_fila] */
            k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)GRV(0x4F1E9B) - (DWORD)(k + i + 5)); i += 5;
            BYTE s1[13] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
            *(int *)(s1 + 1) = (int)((DWORD)c1 - ((DWORD)GRV(GR_NOM_FIN1) + 5));
            BYTE s2[5] = { 0xE9, 0, 0, 0, 0 };
            *(int *)(s2 + 1) = (int)((DWORD)c2 - ((DWORD)GRV(GR_NOM_INI2) + 5));
            g_gr_nombres = gr_escribir(GR_NOM_FIN1, s1, 13) && gr_escribir(GR_NOM_INI2, s2, 5);
        }
    } else
        apuntar("  [grande] ⚠ la textura de los nombres (0x4F1B90) no es la esperada: los nombres quedan en 6");
    /* la pista ancha: el «Model» del <Bg> */
    g_gr_ancha = GetPrivateProfileIntA("grande", "ancha", 1, ini);
    {
        BYTE *c = GRV(GR_MODELO_LLAMA);
        if (c[0] == 0xE8 && (DWORD)(c + 5 + *(int *)(c + 1)) == (DWORD)GRV(0x678160)) {
            int rel = (int)((DWORD)gr_modelo - ((DWORD)c + 5));
            gr_escribir(GR_MODELO_LLAMA + 1, &rel, 4);
        } else {
            g_gr_ancha = 0;
            apuntar("  [grande] ⚠ la carga de la pista (0x4EFAA2) no es la esperada: sin pista ancha");
        }
    }
    {
        BYTE *c = GRV(GR_META_LLAMA);
        if (g_gr_ancha && c[0] == 0xE8 && (DWORD)(c + 5 + *(int *)(c + 1)) == (DWORD)GRV(0x678160)) {
            int rel = (int)((DWORD)gr_meta - ((DWORD)c + 5));
            gr_escribir(GR_META_LLAMA + 1, &rel, 4);
        } else if (g_gr_ancha)
            apuntar("  [grande] ⚠ la carga de la meta (0x4EFE4E) no es la esperada: la meta queda de 6");
    }
    /* la cámara del final */
    g_gr_cam_k = GetPrivateProfileIntA("grande", "camara_meta", 2100, ini) / 1000.0f;
    for (int i = 0; i < 3; i++) {
        BYTE *c = GRV(GR_CAM_META[i]);
        if (c[0] == 0xE8 && (DWORD)(c + 5 + *(int *)(c + 1)) == (DWORD)GRV(0x645A10)) {
            int rel = (int)((DWORD)gr_camara_meta - ((DWORD)c + 5));
            gr_escribir(GR_CAM_META[i] + 1, &rel, 4);
        } else
            apuntar("  [grande] ⚠ la cámara del final (0x%06X) no es la esperada: no se aleja", GR_CAM_META[i]);
    }
    /* el reparto lee NUESTROS dobles desde ya (valen 3.0 y 223.5 hasta que venga una carrera grande) */
    for (int i = 0; i < (int)(sizeof(GR_MITAD) / sizeof(GR_MITAD[0])); i++) {
        DWORD d = (DWORD)&g_gr_mitad;
        gr_escribir(GR_MITAD[i] + 2, &d, 4);
    }
    for (int i = 0; i < (int)(sizeof(GR_PASO) / sizeof(GR_PASO[0])); i++) {
        DWORD d = (DWORD)&g_gr_paso;
        gr_escribir(GR_PASO[i] + 2, &d, 4);
    }
    gr_abandono();
    g_gr_activo = 1;
    apuntar("  [grande] listo: %d «6» del motor esperando el campo 3 del FF25 · forzar=%d · dejar=%d · nombres=%d"
            " · ancha=%d", (int)(sizeof(GR_SEIS) / sizeof(GR_SEIS[0])), g_gr_forzar, g_gr_ndejar, g_gr_nombres,
            g_gr_ancha);
}
