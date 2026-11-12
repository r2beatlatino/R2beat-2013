/* ropero.c — los SETS del armario en 2 columnas de 5: SET1..SET10 (12-oct-2026)
 *
 *   anonimo03: «son 4 espacios, ¿podés hacer que sean 10? — dos columnas». Doc: documentacion/ARMARIO_CONJUNTOS.md §5.
 *
 *   El desplegable lo dibuja el exe por código, con la hoja rnr_ui/myroom/myroom_btn2 ([armario+0x451C], dibujar =
 *   0x683FB0 thiscall (x, y, corte, 0)), en DOS funciones con la misma lógica y distinta esquina:
 *     A · 0x4CB13A..0x4CB243 (el armario de siempre): caja en (cx−0x185, cy−0xA2), rótulo en (cx−0x185, cy−0xB8)
 *     B · 0x4CC7A7..0x4CC894 (recibe la esquina): caja en (edi+0xA, ebp+0x31), rótulo en (edi+0xA, [esp+0x10])
 *   y en las dos: corte 12 = la caja de 4, 13 = el marco del renglón bajo el mouse (+2, +3 + h·15), 50 = la marca de
 *   «vacío» (+3, +5 + i·15) si el set NO está en el mapa del jugador ([player+0x138], buscar 0x48A3F0), y el rótulo =
 *   corte set+8 (8..11 = SET1..SET4). El clic: 0x4CBE17..0x4CBEA1 del manejador 0x4CBC80(x0, y0, clic): 4 renglones
 *   de 47×17 desde (x0, y0); con clic elige ([+0x4898]) y cierra ([+0x489B] = 0, y el botón con 0x685D90), sin clic
 *   sólo marca el renglón ([+0x489A]).
 *   ⇒ Las tres se desvían a nuestro C (cuevas al BORDE de cada bloque: entrar donde el exe pregunta «¿abierto?» y
 *     volver a su salida, con los registros como estaban) con la caja de 2×5 y los rótulos SET1..SET10 de nuestra hoja
 *     (rnr_ui_ropero.pak, cortes 59..69, ver herramientas/ropero_crear.py).
 *   El tope en memoria NO existe: los sets del jugador son un mapa por número (0x48A3F0 / 0x491CB0), sin arreglo de 4.
 *   ⛔ Sin el pak no se engancha (pedirle el corte 59 a la hoja de fábrica, que tiene 59, es leer fuera).
 *   [ropero] activo=0 lo apaga.
 */
#include "ropero_datos.h"

#define RPV(x) (g_rp_base + ((DWORD)(x) - 0x400000))

static BYTE *g_rp_base = NULL;
static BYTE *g_rp_cuevas = NULL;
static int   g_rp_listo = 0;

typedef void  (TCK *F_RP_DIB)(void *spr, int x, int y, int corte, int z);                 /* 0x683FB0, ret 0x10 */
typedef void *(TCK *F_RP_BUSCAR)(void *mapa, void *it, const void *clave);                 /* 0x48A3F0, ret 8 */
typedef void  (TCK *F_RP_BOTON7)(void *b, void *spr, int a, int c, int d, int e, const char *f, int g); /* 0x685D90 */
typedef void  (TCK *F_RP_Z)(void *spr, int corte, float z);                                /* 0x683F60, ret 8 */
static void *g_rp_spr_z = NULL;                  /* la hoja a la que ya se le puso la z (se recrea con la escena) */

#define RP_DIB_A    0x4CB13A     /* cmp byte [esi+0x489B],0 · je 0x4CB213   (13 B)  → vuelve a 0x4CB243 */
#define RP_DIB_A_FIN 0x4CB243
#define RP_DIB_B    0x4CC7A7     /* cmp byte [esi+0x489B],0 · je 0x4CC877   (13 B)  → vuelve a 0x4CC894 */
#define RP_DIB_B_FIN 0x4CC894
#define RP_CLIC     0x4CBE17     /* cmp byte [esi+0x489B],0 · mov eax,[0x93156C] (12 B) → vuelve a 0x4CBEA1 */
#define RP_CLIC_FIN 0x4CBEA1
static const BYTE RP_DIB_A_BYTES[13] = { 0x80, 0xBE, 0x9B, 0x48, 0x00, 0x00, 0x00, 0x0F, 0x84, 0xCC, 0x00, 0x00, 0x00 };
static const BYTE RP_DIB_B_BYTES[13] = { 0x80, 0xBE, 0x9B, 0x48, 0x00, 0x00, 0x00, 0x0F, 0x84, 0xC3, 0x00, 0x00, 0x00 };
static const BYTE RP_CLIC_BYTES[12] = { 0x80, 0xBE, 0x9B, 0x48, 0x00, 0x00, 0x00, 0xA1, 0x6C, 0x15, 0x93, 0x00 };
static const BYTE RP_FIN_A[4] = { 0x5F, 0x5E, 0x5D, 0x5B };        /* pop edi/esi/ebp/ebx: la salida de A y de B */

/* ¿el jugador tiene guardado el set `n`? (el mismo buscar que usa el exe; el mapa es [player+0x138], el fin +0x150) */
static int rp_guardado(int n)
{
    BYTE *jug = *(BYTE **)RPV(0x9314E0);
    if (!jug) return 0;
    DWORD it[2] = { 0, 0 };
    DWORD clave = (DWORD)(n & 0xFF);
    ((F_RP_BUSCAR)RPV(0x48A3F0))(jug + 0x138, it, &clave);
    return it[1] != *(DWORD *)(jug + 0x150);
}

/* la caja de 2×5, el marco y las marcas, y el rótulo del elegido. (bx, by) = la esquina de la caja, (lx, ly) = el rótulo */
static void rp_dibujar(BYTE *arm, int bx, int by, int lx, int ly)
{
    void *spr = *(void **)(arm + 0x451C);
    if (!spr) return;
    /* ★ 2.ª vuelta (anonimo03: «las alas se ponen delante y tapan las columnas»): la z es de CADA corte, y el armario,
     *   apenas carga la hoja (0x4CAD7B..0x4CADD2), les pone al 12, al 13 y al 50 la de [0x87495C] con 0x683F60 —
     *   la que los deja delante del muñeco—; los nuestros (59..69) quedaban con la de siempre, detrás. */
    if (spr != g_rp_spr_z) {
        float z = *(float *)RPV(0x87495C);
        for (int c = RP_CORTE_CAJA; c < RP_CORTES_HOJA; c++)
            ((F_RP_Z)RPV(0x683F60))(spr, c, z);
        g_rp_spr_z = spr;
        apuntar("  [ropero] la z de la caja de fábrica (%d/1000) a los cortes %d..%d", (int)(z * 1000), RP_CORTE_CAJA,
                RP_CORTES_HOJA - 1);
    }
    F_RP_DIB dib = (F_RP_DIB)RPV(0x683FB0);
    if (arm[0x489B]) {
        dib(spr, bx, by, RP_CORTE_CAJA, 0);
        int h = arm[0x489A];
        if (h < RP_SETS)
            dib(spr, bx + 2 + (h / RP_FILAS) * RP_COL_W, by + 3 + (h % RP_FILAS) * RP_PASO, RP_CORTE_MARCO, 0);
        for (int i = 0; i < RP_SETS; i++)
            if (!rp_guardado(i))
                dib(spr, bx + 3 + (i / RP_FILAS) * RP_COL_W, by + 5 + (i % RP_FILAS) * RP_PASO, RP_CORTE_GUARDADO, 0);
    }
    int s = arm[0x4898];
    dib(spr, lx, ly, s < RP_SETS ? RP_CORTE_ROTULO0 + s : s + 8, 0);
}

static void __cdecl rp_dib_a(BYTE *arm)
{
    int cx = *(int *)RPV(0x904084), cy = *(int *)RPV(0x904088);
    rp_dibujar(arm, cx - 0x185, cy - 0xA2, cx - 0x185, cy - 0xB8);
}

/* B: pila = el esp que tenía el exe en 0x4CC7A7 (el rótulo va en y = [esp+0x10]) */
static void __cdecl rp_dib_b(BYTE *arm, int edi, int ebp, BYTE *pila)
{
    rp_dibujar(arm, edi + 0xA, ebp + 0x31, edi + 0xA, *(int *)(pila + 0x10));
}

/* el clic: pila = el esp del manejador 0x4CBC80 en 0x4CBE17 → sus argumentos (x0, y0, clic) en +0xC4/+0xC8/+0xCC */
static void __cdecl rp_clic(BYTE *arm, BYTE *pila)
{
    if (!arm[0x489B]) return;
    int x0 = *(int *)(pila + 0xC4), y0 = *(int *)(pila + 0xC8), clic = *(int *)(pila + 0xCC);
    BYTE *m = *(BYTE **)RPV(0x93156C);
    if (!m) return;
    int mx = *(int *)(m + 4), my = *(int *)(m + 8);
    arm[0x489A] = 0xFF;
    if (mx <= x0 || mx >= x0 + RP_CAJA_W || my <= y0 || my >= y0 + RP_CAJA_H) return;
    int col = (mx - x0) / RP_COL_W, fila = (my - y0 - 3) / RP_PASO;
    if (col > 1) col = 1;
    if (fila < 0) fila = 0;
    if (fila >= RP_FILAS) fila = RP_FILAS - 1;
    int n = col * RP_FILAS + fila;
    if (clic) {
        arm[0x4898] = (BYTE)n;
        arm[0x489B] = 0;
        ((F_RP_BOTON7)RPV(0x685D90))(arm + 0x3F68, *(void **)(arm + 0x451C), 0xE, 0xF, 0x10, 0,
                                      (const char *)RPV(0x873C99), -1);
    } else {
        arm[0x489A] = (BYTE)n;
    }
}

static int rp_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(RPV(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(RPV(va), b, n);
    VirtualProtect(RPV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), RPV(va), n);
    return 1;
}

/* una cueva: pushad · (los argumentos) · call f · add esp,N · popad · jmp vuelta */
static BYTE *rp_cueva(BYTE **k, int tipo, void *f, DWORD vuelta)
{
    BYTE *c = *k;
    int i = 0;
    c[i++] = 0x60;                                                                   /* pushad */
    if (tipo == 0) {                                                                 /* A: f(esi) */
        c[i++] = 0x56;                                                               /* push esi */
    } else if (tipo == 1) {                                                          /* B: f(esi, edi, ebp, esp0) */
        c[i++] = 0x8D; c[i++] = 0x44; c[i++] = 0x24; c[i++] = 0x20;                  /* lea eax,[esp+0x20] */
        c[i++] = 0x50; c[i++] = 0x55; c[i++] = 0x57; c[i++] = 0x56;                  /* push eax, ebp, edi, esi */
    } else {                                                                         /* clic: f(esi, esp0) */
        c[i++] = 0x8D; c[i++] = 0x44; c[i++] = 0x24; c[i++] = 0x20;                  /* lea eax,[esp+0x20] */
        c[i++] = 0x50; c[i++] = 0x56;                                                /* push eax, esi */
    }
    c[i] = 0xE8; *(int *)(c + i + 1) = (int)((DWORD)f - (DWORD)(c + i + 5)); i += 5;  /* call f */
    c[i++] = 0x83; c[i++] = 0xC4; c[i++] = (BYTE)(tipo == 0 ? 4 : tipo == 1 ? 16 : 8); /* add esp,N */
    c[i++] = 0x61;                                                                   /* popad */
    c[i] = 0xE9; *(int *)(c + i + 1) = (int)((DWORD)RPV(vuelta) - (DWORD)(c + i + 5)); i += 5;
    *k = c + ((i + 15) & ~15);
    return c;
}

static int rp_saltar(DWORD sitio, BYTE *cueva, int largo)
{
    BYTE s[16];
    memset(s, 0x90, sizeof(s));
    s[0] = 0xE9;
    *(int *)(s + 1) = (int)((DWORD)cueva - ((DWORD)RPV(sitio) + 5));
    return rp_escribir(sitio, s, largo);
}

static void ropero_iniciar(void)
{
    char ini[MAX_PATH], pak[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("ropero", "activo", 1, ini)) {
        apuntar("  [ropero] apagado ([ropero] activo=0): el desplegable de 4 sets de fábrica");
        return;
    }
    lstrcpyA(pak, g_carpeta);
    lstrcatA(pak, RP_PAK);
    if (GetFileAttributesA(pak) == INVALID_FILE_ATTRIBUTES) {
        apuntar("  [ropero] ⛔ falta %s: el desplegable queda el de 4 (sin la hoja nueva no se engancha)", RP_PAK);
        return;
    }
    g_rp_base = (BYTE *)GetModuleHandleA(NULL);
    if (memcmp(RPV(RP_DIB_A), RP_DIB_A_BYTES, 13) != 0 || memcmp(RPV(RP_DIB_B), RP_DIB_B_BYTES, 13) != 0 ||
        memcmp(RPV(RP_CLIC), RP_CLIC_BYTES, 12) != 0 || memcmp(RPV(RP_DIB_A_FIN), RP_FIN_A, 4) != 0 ||
        memcmp(RPV(RP_DIB_B_FIN), RP_FIN_A, 4) != 0) {
        apuntar("  [ropero] ⛔ los sitios del desplegable (0x%X, 0x%X, 0x%X) no son los esperados: no se toca nada",
                RP_DIB_A, RP_DIB_B, RP_CLIC);
        return;
    }
    g_rp_cuevas = (BYTE *)VirtualAlloc(NULL, 256, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_rp_cuevas) return;
    BYTE *k = g_rp_cuevas;
    BYTE *ca = rp_cueva(&k, 0, (void *)rp_dib_a, RP_DIB_A_FIN);
    BYTE *cb = rp_cueva(&k, 1, (void *)rp_dib_b, RP_DIB_B_FIN);
    BYTE *cc = rp_cueva(&k, 2, (void *)rp_clic, RP_CLIC_FIN);
    if (rp_saltar(RP_DIB_A, ca, 13) && rp_saltar(RP_DIB_B, cb, 13) && rp_saltar(RP_CLIC, cc, 12)) {
        g_rp_listo = 1;
        apuntar("  [ropero] ok: el desplegable de los sets es de 2×5 (SET1..SET%d), con la hoja de %s", RP_SETS, RP_PAK);
    }
}
