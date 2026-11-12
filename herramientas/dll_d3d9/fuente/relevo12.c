/* relevo12.c — EL RELEVO DE 12: el motor del relevo del cliente, de 2 equipos a 4 (14-oct-2026)
 *
 *   anonimo03: «modo relevo con el 12 prendido, su propia sala, hasta cuatro banderas (rojo, azul, verde, naranja), cada
 *   equipo con sus 3 jugadores completos». Investigación y plan: documentacion/RELEVO_12.md.
 *
 *   El relevo del cliente piensa en «MI equipo contra el rival»: 2 planteles (`vector<u8>` de 0x18, los asientos en
 *   orden de tramo) en cGame+0xBC0 (el rival) y +0xBD8 (el mío), y 2 «corredor activo» en +0xBF0 / +0xBF1 (0xFF =
 *   ese equipo terminó). Pegados: no hay lugar para un 3.º ni un 4.º. Lo que se hace acá:
 *
 *     1 · LA MUDANZA: cGame es uno solo (vive en el objeto de la aplicación), así que sus 81 accesos a ese estado se
 *         reescriben EN EL LUGAR, con el mismo largo, contra un bloque de la dll (g_r12): 4 planteles + 4 activos.
 *         Lo genera herramientas/relevo12_mudanza.py (relevo12_datos.h); el constructor y el destructor de los
 *         planteles cuentan 4. Vale para TODOS los modos: con 2 equipos los planteles 2 y 3 quedan vacíos.
 *     2 · EL ÍNDICE DEL EQUIPO: 0x4ED230(asiento) — «¿es de mi equipo?» → 1 / 0, lo usan sólo el traspaso, el siguiente
 *         y el abandono como ÍNDICE — en el relevo de 12 devuelve 0..3: mi equipo 1, los rivales 0, 2 y 3 (por número
 *         de equipo). El armado (0x4F6230) llama a 0x4ED370 + setne: se cambia la llamada por la nuestra y el setne
 *         por NOP, y su «asiento < 6» por «< 12».
 *     3 · LOS QUE MIRAN «LOS 2»: 0x4F2F50 («¿este corredor espera su tramo?») se reemplaza por una que mira los 4; el
 *         bucle de 0x4F7520 con la misma pregunta escrita a mano (0x4F76C8) llama a la nuestra; 0x4F6130 (ubica a los
 *         que esperan en el arranque de su tramo, el rival 0 y el mío) se llama una vez más por cada rival extra con
 *         el plantel cambiado de lugar un momento (sólo el arreglo de datos: el «proxy» del vector no se mueve).
 *     4 · EL ARMADO: antes vacía los planteles 2 y 3 (los de 0 y 1 los vacía el juego); después pone en 0xFF el
 *         activo de los planteles vacíos (un equipo que no está «ya terminó») y en 0 el de los que tienen gente.
 *
 *     5 · EL INICIO DE LA SALA (0x592B50, el guard del START): cuenta «equipo 1» contra «todos los demás» y pide que
 *         sean iguales (3 contra 9 = «equipos disparejos»). En una sala de RELEVO ([cRoom+0x9568] = 2) con 9 o más:
 *         alcanza con que los dos números sean múltiplos de 3 (los equipos completos los exige el server, con su
 *         cartel: lobby_carrera.relevo_puede_arrancar). Con 6 (el 3 contra 3 de siempre) sigue como de fábrica.
 *
 *     6 · EL CARRIL (anonimo03, 14-oct: «el 1.er corredor del 1.er equipo el carril 1, el 2.º el 2, el 3.º el 3; el 2.º equipo
 *         el 4…» · «veo que los NPC van apilados»): 0x501690(asiento) en el relevo pone el carril POR EQUIPO — equipo 1
 *         → 2, cualquier otro → 3 (`cmp al,1 · setne · add 2`): los equipos 2, 3 y 4 compartían carril. Con más de 6
 *         corredores va al camino de siempre: carril = asiento (rojo 1-3, azul 4-6, verde 7-9, naranja 10-12).
 *
 *   ⚠ La guarda: cada sitio tiene que tener sus bytes de fábrica; si UNO no calza, no se toca NADA (la mudanza a
 *     medias rompería el relevo de siempre). [relevo12] activo=0 lo apaga entero.
 */
#include "relevo12_datos.h"

#define R12V(x) (g_r12_base + ((DWORD)(x) - 0x400000))

static BYTE *g_r12_base = NULL;
static BYTE g_r12[0x80] __attribute__((aligned(16)));    /* 4 planteles (de a 0x18) + 4 activos en +0x60 */
static int g_r12_activo = 0;
static int g_r12_armados = 0;
static void *g_r12_orig_idx = NULL;                      /* trampolín de 0x4ED230 */
static void *g_r12_orig_ubicar = NULL;                   /* trampolín de 0x4F6130 */

#define R12_PLANTEL(t) (g_r12 + (t) * 0x18)
#define R12_ACT (g_r12 + 0x60)

typedef BYTE (TCK *F_R12_EQUIPO)(void *padron, int asiento);     /* 0x4EC970 */
typedef BYTE (TCK *F_R12_MI_EQUIPO)(void *padron);               /* 0x48A320 */
typedef BYTE (TCK *F_R12_IDX)(void *g, int asiento);             /* 0x4ED230 / 0x4ED370, ret 4 */
typedef void (TCK *F_R12_ARMAR)(void *g);                        /* 0x4F6230 */
typedef void (TCK *F_R12_UBICAR)(void *g, int k);                /* 0x4F6130, ret 4 */

static int r12_n(int t)                                  /* cuántos tiene el plantel t */
{
    BYTE *v = R12_PLANTEL(t);
    BYTE *a = *(BYTE **)(v + 0xC), *b = *(BYTE **)(v + 0x10);
    return a && b > a ? (int)(b - a) : 0;
}

static int r12_asiento(int t, int i)                     /* el asiento i del plantel t */
{
    return (*(BYTE **)(R12_PLANTEL(t) + 0xC))[i];
}

static int r12_es_doce(BYTE *g)                          /* ¿carrera de relevo de 12? */
{
    return g && (*(WORD *)(g + 0xC) & 0x40) && g_gr_puesto > 6;
}

/* el índice de plantel del asiento en el relevo de 12: mi equipo 1; los rivales 0, 2, 3 en orden de número de equipo
 * (el «mi equipo» como lo mira 0x4ED230: el del asiento de referencia [cGame+0xC02] si hay uno, si no el mío) */
static int r12_indice(BYTE *g, int asiento)
{
    void *padron = *(void **)R12V(0x931660);
    if (!padron) return 0;
    BYTE ref = g[0xC02];
    int mio = ref != 0xFF ? ((F_R12_EQUIPO)R12V(0x4EC970))(padron, ref) : ((F_R12_MI_EQUIPO)R12V(0x48A320))(padron);
    int e = ((F_R12_EQUIPO)R12V(0x4EC970))(padron, asiento);
    if (e == mio) return 1;
    int r = 0;
    for (int x = 1; x < e && x <= 4; x++) if (x != mio) r++;
    return r == 0 ? 0 : (r + 1 > 3 ? 3 : r + 1);
}

/* 0x4ED230 (thiscall, ret 4): con el relevo de 12 (y sin espectador: ése sigue su camino), el índice 0..3 */
static BYTE __fastcall r12_idx(BYTE *g, void *nada, int asiento)
{
    (void)nada;
    if (g_r12_activo && r12_es_doce(g) && !g[0xC01]) return (BYTE)r12_indice(g, asiento & 0xFF);
    return ((F_R12_IDX)g_r12_orig_idx)(g, asiento);
}

/* la llamada del armado (0x4F62FF, era 0x4ED370 + setne): el índice ya hecho */
static BYTE __fastcall r12_idx_armado(BYTE *g, void *nada, int asiento)
{
    (void)nada;
    if (g_r12_activo && r12_es_doce(g)) return (BYTE)r12_indice(g, asiento & 0xFF);
    return ((F_R12_IDX)R12V(0x4ED370))(g, asiento) != 0;
}

/* ¿el corredor k lleva la posta de algún equipo? */
static int r12_corre(int k)
{
    for (int t = 0; t < 4; t++) {
        int a = R12_ACT[t];
        if (a != 0xFF && a < r12_n(t) && r12_asiento(t, a) == k) return 1;
    }
    return 0;
}

/* 0x4F2F50 (thiscall, ret 4): ¿espera su tramo? = relevo y no lleva la posta de ningún equipo (era: de los 2) */
static int __fastcall r12_espera(BYTE *g, void *nada, int k)
{
    (void)nada;
    if (!(*(WORD *)(g + 0xC) & 0x40)) return 0;
    return !r12_corre(k & 0xFF);
}

/* el bucle de 0x4F7520 (0x4F76C8): ebx = el corredor; 1 si lleva la posta (sigue en 0x4F770E), 0 si no (0x4F7734) */
static int __cdecl r12_es_activo(int k)
{
    return r12_corre(k & 0xFF);
}

/* 0x4F769A → el armado: vaciar 2 y 3 antes, y los activos después */
static void __fastcall r12_armar(BYTE *g, void *nada)
{
    (void)nada;
    for (int t = 2; t < 4; t++) {
        BYTE *v = R12_PLANTEL(t);
        *(DWORD *)(v + 0x10) = *(DWORD *)(v + 0xC);                              /* clear (vector<u8>: sin destructores) */
    }
    ((F_R12_ARMAR)R12V(0x4F6230))(g);
    for (int t = 0; t < 4; t++)
        if (!r12_n(t)) R12_ACT[t] = 0xFF;                                         /* ese equipo no está: «terminó» */
        else if (t >= 2) R12_ACT[t] = 0;
    if (g_r12_armados++ < 20 && (*(WORD *)(g + 0xC) & 0x40)) {
        char s[4][40];
        for (int t = 0; t < 4; t++) {
            int n = 0;
            s[t][0] = 0;
            for (int i = 0; i < r12_n(t) && n < 34; i++) n += wsprintfA(s[t] + n, "%d ", r12_asiento(t, i));
        }
        apuntar("  [relevo12] planteles: rival0 [%s] · mío [%s] · rival2 [%s] · rival3 [%s] · activos %d %d %d %d", s[0], s[1],
                s[2], s[3], R12_ACT[0], R12_ACT[1], R12_ACT[2], R12_ACT[3]);
    }
}

/* 0x4F6130 (thiscall, ret 4): ubica a los que esperan; en el de 12, una vez más por cada rival extra (2 y 3) con su
 * plantel puesto un momento en el lugar del 0 — sólo los datos (+0xC..+0x17), el proxy del vector queda */
static void r12_cambiar(int a, int b)
{
    BYTE t[12], *va = R12_PLANTEL(a) + 0xC, *vb = R12_PLANTEL(b) + 0xC;
    CopyMemory(t, va, 12);
    CopyMemory(va, vb, 12);
    CopyMemory(vb, t, 12);
}

static void __fastcall r12_ubicar(BYTE *g, void *nada, int k)
{
    (void)nada;
    ((F_R12_UBICAR)g_r12_orig_ubicar)(g, k);
    if (!(g_r12_activo && r12_es_doce(g))) return;
    for (int t = 2; t < 4; t++) {
        if (!r12_n(t)) continue;
        r12_cambiar(0, t);
        ((F_R12_UBICAR)g_r12_orig_ubicar)(g, k);
        r12_cambiar(0, t);
    }
}

/* ── la instalación ─────────────────────────────────────────────────────────────────────────────────────────────── */
static int r12_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(R12V(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(R12V(va), b, n);
    VirtualProtect(R12V(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), R12V(va), n);
    return 1;
}

static void *r12_trampolin(DWORD va, int n)              /* copia n bytes de fábrica + jmp de vuelta */
{
    BYTE *c = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!c) return NULL;
    CopyMemory(c, R12V(va), n);
    c[n] = 0xE9;
    *(int *)(c + n + 1) = (int)((DWORD)R12V(va + n) - (DWORD)(c + n + 5));
    return c;
}

static void r12_saltar(DWORD va, void *a, int largo)     /* jmp a + NOP hasta `largo` */
{
    BYTE s[16];
    s[0] = 0xE9;
    *(int *)(s + 1) = (int)((DWORD)a - ((DWORD)R12V(va) + 5));
    for (int i = 5; i < largo; i++) s[i] = 0x90;
    r12_escribir(va, s, largo);
}

static void r12_llamar(DWORD va, void *a)                /* el call de `va` → a */
{
    int rel = (int)((DWORD)a - ((DWORD)R12V(va) + 5));
    r12_escribir(va + 1, &rel, 4);
}

/* ── ★ F4 · LA LISTA DE LA CARRERA EN EL RELEVO DE 12 (la llama c12_lista) ───────────────────────────────────────
 *   La de fábrica (0x4F2FC0) pone primero los 3 del equipo que va adelante y después los 3 del otro: con 4 equipos
 *   serían 12. anonimo03: «vamos a tener que meter una fila más y quizá hacer esos elementos más chicos». ⇒ UNA tarjeta
 *   por equipo — el que corre ahora — ordenadas por cómo van los equipos (1ST..4TH: la tarjeta pone el puesto), y
 *   debajo de cada una una fila CHICA con sus 3 corredores en orden de tramo (los marcadores de la barra, del color
 *   del equipo): el que corre, entero; el que espera, un poco apagado; el que ya corrió, más apagado. */
typedef BYTE (TCK *F_R12_PUESTO)(void *g, int asiento);         /* 0x4EB670: el puesto (1..), ret 4 */
typedef void (TCK *F_R12_TINTE)(void *spr, int n, DWORD argb);  /* 0x64E710 */
static void r12_lista(BYTE *g)
{
    int orden[4], slot[4], cual[4], n = 0;
    for (int t = 0; t < 4; t++) {
        int m = r12_n(t);
        if (!m) continue;
        int a = R12_ACT[t];
        slot[n] = r12_asiento(t, a != 0xFF && a < m ? a : m - 1);              /* terminó: su último corredor */
        cual[n] = (((F_R12_PUESTO)R12V(0x4EB670))(g, slot[n]) & 0xFF) | (a == 0xFF ? 0 : 0x100);
        orden[n++] = t;
    }
    for (int i = 0; i < n; i++)                                                /* por puesto (los que terminaron, antes) */
        for (int j = i + 1; j < n; j++)
            if (cual[j] < cual[i]) {
                int x = cual[i]; cual[i] = cual[j]; cual[j] = x;
                x = orden[i]; orden[i] = orden[j]; orden[j] = x;
                x = slot[i]; slot[i] = slot[j]; slot[j] = x;
            }
    void *hud = *(void **)R12V(0x931670);
    if (!hud) return;
    for (int p = 0; p < n; p++) {
        int t = orden[p], m = r12_n(t), a = R12_ACT[t];
        g_c12_asiento = slot[p];
        g_c12_puesto = p;
        int y0 = p == 0 ? 0xF : *(int *)R12V(0x904BF0);                    /* la tarjeta 0 lo pone en 0xF */
        ((F_C12_TARJETA)R12V(0x55A9C0))(hud, p, p, slot[p]);
        g_c12_asiento = g_c12_puesto = g_c12_redirigido = -1;
        /* el puesto chico del equipo en las tarjetas que no son la grande (la grande ya trae el suyo) */
        BYTE yo = g[0xC01] || (*(WORD *)(g + 0xC) & 0x40) ? g[0x5D] : (*(BYTE **)R12V(0x931660))[0x40];
        if (slot[p] != yo) c12_puesto_chico(p, y0);
        /* la fila chica, pegada debajo de la tarjeta (la tarjeta ya corrió [0x904BF0] a la siguiente) */
        int *yy = (int *)R12V(0x904BF0);
        int y = *yy - 0xE + 1, x0 = 0x15 - *(int *)((BYTE *)hud + 0xA1C) + 4;
        for (int i = 0; i < m && i < 6; i++) {
            int k = r12_asiento(t, i), c = c12_marca(k);
            DWORD tinte = (a == 0xFF || i < a) ? 0x60FFFFFF : i == a ? 0xFFFFFFFF : 0xB0FFFFFF;
            ((F_R12_TINTE)R12V(0x64E710))(g_c12_hoja, c, tinte);
            ((F_C12_POS)R12V(0x64D990))(g_c12_hoja, c, x0 + i * 23, y);
            ((F_C12_DIB)R12V(0x64EE40))(g_c12_hoja, c, 0);
            ((F_R12_TINTE)R12V(0x64E710))(g_c12_hoja, c, 0xFFFFFFFF);
        }
        *yy += 24;
    }
}

#define R12_BUCLE 0x4F76C8                               /* la pregunta «¿lleva la posta?» de 0x4F7520 */
#define R12_BUCLE_LARGO 0x46

static void relevo12_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("relevo12", "activo", 1, ini)) {
        apuntar("  [relevo12] apagado ([relevo12] activo=0): el relevo de 2 de fábrica");
        return;
    }
    g_r12_base = (BYTE *)GetModuleHandleA(NULL);
    /* la guarda: TODOS los sitios con sus bytes de fábrica, y los ganchos también */
    static const BYTE e_idx[5] = { 0x83, 0xEC, 0x08, 0x53, 0x56 };
    static const BYTE e_espera[5] = { 0x56, 0x8B, 0xF1, 0xF6, 0x46 };
    static const BYTE e_ubicar[7] = { 0x83, 0xEC, 0x10, 0x8A, 0x44, 0x24, 0x14 };
    static const BYTE e_seis[2] = { 0x3C, 0x06 };
    static const BYTE e_setne[3] = { 0x0F, 0x95, 0xC0 };
    static const BYTE e_bucle[8] = { 0x8A, 0x86, 0xF1, 0x0B, 0x00, 0x00, 0x3C, 0xFF };
    BYTE *c = g_r12_base;
    int ok = memcmp(R12V(0x4ED230), e_idx, 5) == 0 && memcmp(R12V(0x4F2F50), e_espera, 5) == 0 &&
             memcmp(R12V(0x4F6130), e_ubicar, 7) == 0 && memcmp(R12V(0x4F62F0), e_seis, 2) == 0 &&
             memcmp(R12V(0x4F6309), e_setne, 3) == 0 && memcmp(R12V(R12_BUCLE), e_bucle, 8) == 0 &&
             c[0x4F62FF - 0x400000] == 0xE8 && c[0x4F769A - 0x400000] == 0xE8 &&
             (DWORD)R12V(0x4F62FF + 5) + *(int *)R12V(0x4F62FF + 1) == (DWORD)R12V(0x4ED370) &&
             (DWORD)R12V(0x4F769A + 5) + *(int *)R12V(0x4F769A + 1) == (DWORD)R12V(0x4F6230);
    int malos = 0;
    for (int i = 0; i < R12_SITIOS; i++)
        if (memcmp(R12V(R12_TABLA[i].va), R12_TABLA[i].fab, R12_TABLA[i].largo) != 0) {
            if (malos++ < 3) apuntar("  [relevo12] ⛔ el sitio 0x%06X no es el de fábrica", R12_TABLA[i].va);
        }
    if (!ok || malos) {
        apuntar("  [relevo12] ⛔ %s: no se toca NADA (el relevo de 2 queda de fábrica)",
                malos ? "hay sitios que no son los de fábrica" : "un gancho no es el esperado");
        return;
    }
    /* 1 · la mudanza (menos lo que tapa el bucle, que se reemplaza entero) */
    int hechos = 0;
    for (int i = 0; i < R12_SITIOS; i++) {
        const R12_SITIO *s = &R12_TABLA[i];
        if (s->va >= R12_BUCLE && s->va < R12_BUCLE + R12_BUCLE_LARGO) continue;
        BYTE nb[12];
        CopyMemory(nb, s->nuevo, s->largo);
        if (s->en >= 0) *(DWORD *)(nb + s->en) = (DWORD)(g_r12 + s->mas);
        hechos += r12_escribir(s->va, nb, s->largo);
    }
    /* 2 · el índice: 0x4ED230 (con trampolín) y el armado (la llamada, el setne y el «< 6») */
    g_r12_orig_idx = r12_trampolin(0x4ED230, 5);
    g_r12_orig_ubicar = r12_trampolin(0x4F6130, 7);
    if (!g_r12_orig_idx || !g_r12_orig_ubicar) {
        apuntar("  [relevo12] ⛔ sin memoria para los trampolines");
        return;
    }
    r12_saltar(0x4ED230, (void *)r12_idx, 5);
    r12_llamar(0x4F62FF, (void *)r12_idx_armado);
    static const BYTE nops[3] = { 0x90, 0x90, 0x90 }, doce[2] = { 0x3C, 0x0C };
    r12_escribir(0x4F6309, nops, 3);
    r12_escribir(0x4F62F0, doce, 2);
    /* 3 · los que miran «los 2» */
    r12_saltar(0x4F2F50, (void *)r12_espera, 5);
    r12_saltar(0x4F6130, (void *)r12_ubicar, 7);
    {   /* push ebx · call r12_es_activo · add esp,4 · test al,al · jne 0x4F770E · jmp 0x4F7734 · NOP… */
        BYTE b[R12_BUCLE_LARGO];
        int i = 0;
        b[i++] = 0x53;
        b[i++] = 0xE8; *(int *)(b + i) = (int)((DWORD)r12_es_activo - ((DWORD)R12V(R12_BUCLE) + i + 4)); i += 4;
        b[i++] = 0x83; b[i++] = 0xC4; b[i++] = 0x04;
        b[i++] = 0x84; b[i++] = 0xC0;
        b[i++] = 0x0F; b[i++] = 0x85; *(int *)(b + i) = (int)((DWORD)R12V(0x4F770E) - ((DWORD)R12V(R12_BUCLE) + i + 4)); i += 4;
        b[i++] = 0xE9; *(int *)(b + i) = (int)((DWORD)R12V(0x4F7734) - ((DWORD)R12V(R12_BUCLE) + i + 4)); i += 4;
        while (i < R12_BUCLE_LARGO) b[i++] = 0x90;
        r12_escribir(R12_BUCLE, b, R12_BUCLE_LARGO);
    }
    /* 4 · el armado */
    r12_llamar(0x4F769A, (void *)r12_armar);
    /* 6 · el carril: 0x501690  mov eax,[cGame*] · test byte [eax+0xC],0x40 · je  →  con más de 6, al de siempre */
    {
        static const BYTE e_carril[11] = { 0xA1, 0xC8, 0x14, 0x93, 0x00, 0xF6, 0x40, 0x0C, 0x40, 0x74, 0x3F };
        BYTE *k = (BYTE *)VirtualAlloc(NULL, 48, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (k && memcmp(R12V(0x501690), e_carril, 11) == 0) {
            int i = 0;
            k[i++] = 0x83; k[i++] = 0x3D; *(DWORD *)(k + i) = (DWORD)&g_gr_puesto; i += 4; k[i++] = 0x06;   /* cmp [g_gr_puesto],6 */
            k[i++] = 0x7F; k[i++] = 0x0E;                                                                /* jg +14 */
            CopyMemory(k + i, e_carril, 9); i += 9;                                                      /* mov eax · test */
            k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)R12V(0x501699) - (DWORD)(k + i + 4)); i += 4;   /* al je de fábrica */
            k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)R12V(0x5016DA) - (DWORD)(k + i + 4)); i += 4;   /* carril = asiento */
            r12_saltar(0x501690, k, 9);
            apuntar("  [relevo12] el carril con más de 6: el asiento (el relevo ya no junta a los equipos en un carril)");
        } else
            apuntar("  [relevo12] ⚠ el carril (0x501690) no es el esperado: queda de fábrica");
    }
    /* 5 · el INICIO de la sala: 0x592CCB  xor eax,eax · cmp bl,[esp+0x13]  →  jmp cueva · nop */
    {
        static const BYTE e_fin[10] = { 0x33, 0xC0, 0x3A, 0x5C, 0x24, 0x13, 0x5F, 0x0F, 0x94, 0xC0 };
        BYTE *k = (BYTE *)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (k && memcmp(R12V(0x592CCB), e_fin, 10) == 0) {
            int i = 0, a_normal, a_ok, a_cuenta, a_n0, a_n1;
            /* cmp dword [ebp+0x9568],2 · je cuenta  (el relevo) */
            k[i++] = 0x83; k[i++] = 0xBD; *(DWORD *)(k + i) = 0x9568; i += 4; k[i++] = 0x02;
            k[i++] = 0x74; a_cuenta = i++;
            /* ★ 15-oct · el EQUIPO DE 4 (EQUIPOS_4.md): cmp dword [ebp+0x9568],0 · jne normal · cmp byte [equipos],4 · jne normal */
            k[i++] = 0x83; k[i++] = 0xBD; *(DWORD *)(k + i) = 0x9568; i += 4; k[i++] = 0x00;
            k[i++] = 0x75; a_n0 = i++;
            k[i++] = 0x80; k[i++] = 0x3D; *(DWORD *)(k + i) = (DWORD)&g_gr_equipos; i += 4; k[i++] = 0x04;
            k[i++] = 0x75; a_n1 = i++;
            k[a_cuenta] = (BYTE)(i - (a_cuenta + 1));
            a_normal = -1;
            /* movzx eax,byte [esp+0x13] · movzx ecx,bl · lea edx,[eax+ecx] · cmp edx,9 · jb normal */
            k[i++] = 0x0F; k[i++] = 0xB6; k[i++] = 0x44; k[i++] = 0x24; k[i++] = 0x13;
            k[i++] = 0x0F; k[i++] = 0xB6; k[i++] = 0xCB;
            k[i++] = 0x8D; k[i++] = 0x14; k[i++] = 0x08;
            k[i++] = 0x83; k[i++] = 0xFA; k[i++] = 0x09;
            k[i++] = 0x72; int a_n2 = i++;
            /* push ecx · xor edx,edx · mov ecx,3 · div ecx · pop ecx · test edx,edx · jnz normal  (equipo 1 % 3) */
            k[i++] = 0x51; k[i++] = 0x31; k[i++] = 0xD2; k[i++] = 0xB9; *(DWORD *)(k + i) = 3; i += 4;
            k[i++] = 0xF7; k[i++] = 0xF1; k[i++] = 0x59; k[i++] = 0x85; k[i++] = 0xD2; k[i++] = 0x75; int a_n3 = i++;
            /* mov eax,ecx · xor edx,edx · mov ecx,3 · div ecx · test edx,edx · jnz normal  (los demás % 3) */
            k[i++] = 0x89; k[i++] = 0xC8; k[i++] = 0x31; k[i++] = 0xD2; k[i++] = 0xB9; *(DWORD *)(k + i) = 3; i += 4;
            k[i++] = 0xF7; k[i++] = 0xF1; k[i++] = 0x85; k[i++] = 0xD2; k[i++] = 0x75; int a_n4 = i++;
            /* ok: xor eax,eax (ZF=1 → sete = 1 → devuelve 0 = se puede) · jmp 0x592CD1 */
            a_ok = i;
            k[i++] = 0x31; k[i++] = 0xC0;
            k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)R12V(0x592CD1) - (DWORD)(k + i + 4)); i += 4;
            /* normal: xor eax,eax · cmp bl,[esp+0x13] · jmp 0x592CD1 */
            int normal = i;
            k[i++] = 0x31; k[i++] = 0xC0; k[i++] = 0x3A; k[i++] = 0x5C; k[i++] = 0x24; k[i++] = 0x13;
            k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)R12V(0x592CD1) - (DWORD)(k + i + 4)); i += 4;
            (void)a_normal;
            k[a_n0] = (BYTE)(normal - (a_n0 + 1));
            k[a_n1] = (BYTE)(normal - (a_n1 + 1));
            k[a_n2] = (BYTE)(normal - (a_n2 + 1));
            k[a_n3] = (BYTE)(normal - (a_n3 + 1));
            k[a_n4] = (BYTE)(normal - (a_n4 + 1));
            (void)a_ok;
            r12_saltar(0x592CCB, k, 6);
            apuntar("  [relevo12] el INICIO de una sala de relevo (★ o de equipo de 4) con 9 o más: equipos de a 3 (no «1 contra los demás»)");
        } else
            apuntar("  [relevo12] ⚠ el final del guard del INICIO (0x592CCB) no es el esperado: queda de fábrica");
    }
    g_c12_lista_relevo = r12_lista;                      /* F4: la lista por equipos (carrera12.c la llama) */
    g_r12_activo = 1;
    apuntar("  [relevo12] ★ el motor del relevo a 4 equipos: %d de %d sitios mudados al bloque 0x%08X, el índice 0..3"
            " (0x4ED230 + el armado), «¿espera su tramo?» con los 4, y el ubicar por cada rival extra",
            hechos, R12_SITIOS, (DWORD)g_r12);
}
