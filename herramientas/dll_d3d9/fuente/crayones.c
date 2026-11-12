/* crayones.c — LOS CRAYONES DEL ID «MAZINO»: más colores de apodo que los 6 de fábrica (23-oct-2026)
 *   · CRAYONES_MAZINO.md · los ítems los arma `herramientas/crayon_crear.py`
 *
 * El color del apodo es un byte por jugador (lo manda el server: `catalogo.color_apodo_de`) que el cliente busca en
 * una tabla de 6 colores — verde, rojo, azul, gris, púrpura, naranja — SIN cota: con 7 o más lee lo que sigue en .rdata.
 * La tabla está COPIADA 10 veces (una por módulo) y la leen 22 lugares, todos `mov r, [idx*4 + tabla]` (medido el
 * 23-oct: las otras 22 apariciones de esas direcciones son el número de ANTES de la tabla — un 0x1B o pi —, no la tabla).
 *   ⇒ los 22 lectores pasan a una tabla NUESTRA de CRA_COLORES: 1..6 los de fábrica (no cambian) y 7..12 los de Mazino.
 *   Las referencias son de dos formas: a la tabla (índice = byte−1) o a la tabla−4 (índice = byte); se respeta cuál.
 *
 * Y el cliente calcula SU propio color con `0x50DFC0` (ítem → 1..6, sólo 1000349..354) y decide si un ítem es lápiz
 * del apodo con `0x50E010` (para tildarlo y para el grupo 1 de 0x485790): las dos se enganchan en la entrada para que
 * conozcan CRA_ITEM0.. (→ CRA_COLOR0..). Sin esto, el color propio (Mi Casa, el cartel propio) saldría sin crayón.
 *
 * ⚠ Los números CRA_* los compara pruebas/probar_crayones.py con crayon_crear.py.  [crayones] activo=0 lo apaga. */

#define CRA_ITEM0 1000780        /* crayon_crear.APODO0 */
#define CRA_N 6                  /* len(crayon_crear.COLORES) */
#define CRA_COLOR0 7             /* crayon_crear.COLOR_APODO0 */
/* ★ y los ESTILOS (estilos_texto.c): 13..23 = las marcas de estilo 0..10 (crayon_crear.APODO_EST0.., ocultos) */
#define CRA_EST_ITEM0 1000701    /* crayon_crear.APODO_EST0 */
#define CRA_EST_COLOR0 13        /* crayon_crear.COLOR_APODO_EST0 */
#define CRA_COLORES 23
static DWORD g_cra_tabla[CRA_COLORES + 4] = {
    0xFF7FC05C, 0xFFF36767, 0xFF50C2EC, 0xFFA9A9A9, 0xFFC175E9, 0xFFFFBF5A,      /* 1..6  los de fábrica */
    0xFFFFD45C, 0xFFFB37A9, 0xFF00FFD5, 0xFFFFFFFF, 0xFF9B2CE0, 0xFFFF2626,      /* 7..12 Mazino: dorado, rosa,
                                                                                    turquesa, blanco, violeta, rojo */
    EST_MARCA(0), EST_MARCA(1), EST_MARCA(2), EST_MARCA(3), EST_MARCA(4),       /* 13..23 los estilos */
    EST_MARCA(5), EST_MARCA(6), EST_MARCA(7), EST_MARCA(8), EST_MARCA(9), EST_MARCA(10),
    0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF };                           /* (colchón: nunca basura) */

/* los 22 lectores: dónde está el disp32, y a qué apuntaba (la tabla, o la tabla − 4) */
static const struct { DWORD va, viejo; } g_cra_sitios[] = {
    { 0x463A1A, 0x876B3C }, { 0x484E9E, 0x878264 }, { 0x4EE086, 0x87BA78 }, { 0x4EE119, 0x87BA78 },
    { 0x4F1DFF, 0x87BA78 }, { 0x4F1E52, 0x87BA78 }, { 0x500A08, 0x87D69C }, { 0x501084, 0x87D69C },
    { 0x5372B1, 0x87EA1C }, { 0x537389, 0x87EA1C }, { 0x537656, 0x87EA1C }, { 0x537727, 0x87EA1C },
    { 0x53DB90, 0x87EDFC }, { 0x53DF3B, 0x87EDFC }, { 0x577199, 0x8811E4 }, { 0x57755C, 0x8811E4 },
    { 0x592642, 0x8820FC }, { 0x59F306, 0x8820FC }, { 0x5952C9, 0x8820F8 }, { 0x5AE0C9, 0x882B08 },
    { 0x5AEB33, 0x882B04 }, { 0x5B600B, 0x882DF0 } };
/* las 10 tablas (la −4 de cada una es la misma) */
static const DWORD g_cra_tablas[10] = { 0x876B3C, 0x878268, 0x87BA7C, 0x87D6A0, 0x87EA1C, 0x87EDFC, 0x8811E4,
                                        0x8820FC, 0x882B08, 0x882DF0 };

static BYTE *g_cra_base = NULL;
#define CRAV(x) (g_cra_base + ((DWORD)(x) - 0x400000))
static void *g_cra_orig_color = NULL, *g_cra_orig_es = NULL;

typedef int (__stdcall *F_CRA_ITEM)(DWORD item);

static int __stdcall cra_color(DWORD item)               /* 0x50DFC0: ítem → color del apodo (0 = ninguno) */
{
    if (item >= CRA_ITEM0 && item < CRA_ITEM0 + CRA_N) return CRA_COLOR0 + (int)(item - CRA_ITEM0);
    if (item >= CRA_EST_ITEM0 && item < CRA_EST_ITEM0 + EST_N) return CRA_EST_COLOR0 + (int)(item - CRA_EST_ITEM0);
    return ((F_CRA_ITEM)g_cra_orig_color)(item) & 0xFF;
}

static int __stdcall cra_es_lapiz(DWORD item)            /* 0x50E010: ¿es lápiz del apodo? */
{
    if (item >= CRA_ITEM0 && item < CRA_ITEM0 + CRA_N) return 1;
    if (item >= CRA_EST_ITEM0 && item < CRA_EST_ITEM0 + EST_N) return 1;
    return ((F_CRA_ITEM)g_cra_orig_es)(item) & 0xFF;
}

static void *cra_enganchar(DWORD va, void *nuestra, const char *que)
{
    static const BYTE e[9] = { 0x8B, 0x44, 0x24, 0x04, 0x3D, 0x9D, 0x43, 0x0F, 0x00 };   /* mov eax,[esp+4] · cmp eax,1000349 */
    if (memcmp(CRAV(va), e, 9) != 0) return NULL;
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return NULL;
    CopyMemory(t, CRAV(va), 9);
    t[9] = 0xE9;
    *(int *)(t + 10) = (int)((DWORD)CRAV(va + 9) - (DWORD)(t + 14));
    BYTE s[9] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)nuestra - ((DWORD)CRAV(va) + 5));
    return escribir_bytes(va, e, s, 9, que) ? t : NULL;
}

static void crayones_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_cra_base = (BYTE *)GetModuleHandleA(NULL);
    if (!GetPrivateProfileIntA("crayones", "activo", 1, ini)) {
        apuntar("  [crayones] APAGADO ([crayones] activo=0): sólo los 6 colores de apodo de fábrica");
        return;
    }
    /* guarda: las 10 tablas son las de fábrica y los 22 lectores apuntan a donde se espera — si no, no se toca nada */
    for (int i = 0; i < 10; i++)
        if (memcmp(CRAV(g_cra_tablas[i]), g_cra_tabla, 6 * 4) != 0) {
            apuntar("  [crayones] ⛔ la tabla 0x%06X no es la de fábrica: no se toca nada", g_cra_tablas[i]);
            return;
        }
    int n = (int)(sizeof(g_cra_sitios) / sizeof(g_cra_sitios[0]));
    for (int i = 0; i < n; i++)
        if (*(DWORD *)CRAV(g_cra_sitios[i].va) != g_cra_sitios[i].viejo) {
            apuntar("  [crayones] ⛔ el lector 0x%06X no apunta a 0x%06X: no se toca nada", g_cra_sitios[i].va,
                    g_cra_sitios[i].viejo);
            return;
        }
    int ok = 0;
    for (int i = 0; i < n; i++) {
        int es_base = 0;
        for (int k = 0; k < 10; k++) es_base |= (g_cra_sitios[i].viejo == g_cra_tablas[k]);
        DWORD nuevo = (DWORD)g_cra_tabla - (es_base ? 0 : 4);
        BYTE esp[4], nue[4];
        CopyMemory(esp, &g_cra_sitios[i].viejo, 4);
        CopyMemory(nue, &nuevo, 4);
        ok += escribir_bytes(g_cra_sitios[i].va, esp, nue, 4, "crayones: lector de la tabla del apodo");
    }
    g_cra_orig_color = cra_enganchar(0x50DFC0, (void *)cra_color, "crayones: ítem → color (0x50DFC0)");
    g_cra_orig_es = cra_enganchar(0x50E010, (void *)cra_es_lapiz, "crayones: ¿es lápiz? (0x50E010)");
    apuntar("  [crayones] ★ %d colores de apodo (%d de %d lectores a la tabla nueva; ítems %d..%d → %d..%d; enganches %d %d)",
            CRA_COLORES, ok, n, CRA_ITEM0, CRA_ITEM0 + CRA_N - 1, CRA_COLOR0, CRA_COLOR0 + CRA_N - 1,
            !!g_cra_orig_color, !!g_cra_orig_es);
}
