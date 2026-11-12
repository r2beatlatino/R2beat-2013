/* aura_suelo.c — LAS AURAS DE SUELO (`<AuraWing>` de VFUN): un efecto en bucle a los pies (29-oct-2026)
 *
 *   anonimo03 (29-oct), con una captura que le pasaron (un personaje sobre un disco de luz con notas): «el de verdad».
 *   El exe 2013 no lee `<AuraWing>`. Doc: AURA_DE_SUELO.md. Los datos (ítem, roomfx, animap) y la tabla de abajo los
 *   arma `herramientas/aura_suelo_crear.py` (aura_suelo_datos.h: {ItemEffect, Fx} por aura).
 *
 *   Cómo pone las ALAS el 2013 (medido en el exe, 29-oct):
 *     0x4B1740  thiscall(guion [0x9316D4], personaje, x, y, z)        las MÍAS: recorre wing.txt y, por cada ala,
 *               si 0x489160([0x9314E0], ItemEffect) («¿tengo puesto un ítem con este efecto?») la CREA con
 *               0x4B06C0(personaje, Fx, x, y, z, 0) y si no la SACA con 0x4AF880(personaje, Fx). 11 llamadores
 *               (Mi Casa, la tienda, la sala, la charla…), casi todos con (0, 0, 0).
 *     0x4B1960  thiscall(guion, personaje, x, y, z, WingId)           las de OTRO: lo mismo, por el Wing Id que
 *               manda el server en la cola del FF0C (catalogo.wing_id). 3 llamadores.
 *   El aura es lo mismo con otra tabla y SIN la carrera: cada llamada a esas dos pasa primero por la original (las alas
 *   como siempre) y después por la nuestra, que pone o saca cada aura con las MISMAS 0x4B06C0 / 0x4AF880.
 *
 *   ★ 1.ª vuelta: el aura PROPIA (por el inventario, como 0x4B1740). Las de los otros esperan el Wing Id
 *     «empaquetado» del server (2.ª vuelta: Wing Id | aura << 16); hasta entonces a los otros se les sacan.
 *   ★ En la carrera, nunca (como VFUN): ahí se SACAN.
 *   [aura] activo=0 la apaga · [aura] alto=N sube o baja el aura N unidades (para medirla).
 *
 *   ★ (145) 31-oct: LOS EFECTOS DE SET (setavatareffect.xml de VFUN). Un aura sin ítem: con TODAS las piezas del set
 *     puestas, el server manda en el mismo byte un número de 0xF0 para arriba (catalogo.aura_de_set) y acá se busca en
 *     AS_TABLA. Gana el aura de ítem (lo decide el server). El muñequito propio (0x4B1740, por el inventario) NO lo
 *     muestra: su lista de lo puesto no trae la ropa (medido). Doc: SET_ESCOLAR.md.
 */
#include "aura_suelo_datos.h"

#define AUV(x) (g_au_base + ((DWORD)(x) - 0x400000))
#define AU_ITEMS   0x009314E0           /* el objeto de «¿tengo puesto…?» (0x489160) */
#define AU_APP     0x009311F4           /* como herramienta.c: app+0xAFFC == cGame ⇒ carrera */
#define AU_PARTIDA 0x009314C8

typedef void (__attribute__((thiscall)) *F_AU_MIAS)(void *guion, void *pj, float x, float y, float z);          /* 0x4B1740 */
typedef void (__attribute__((thiscall)) *F_AU_OTRO)(void *guion, void *pj, float x, float y, float z, int id);  /* 0x4B1960 */
typedef BYTE (__attribute__((thiscall)) *F_AU_TIENE)(void *items, int efecto);                                   /* 0x489160 */
typedef void (__attribute__((thiscall)) *F_AU_PONER)(void *pj, int fx, float x, float y, float z, float w);      /* 0x4B06C0 */
typedef void (__attribute__((thiscall)) *F_AU_SACAR)(void *pj, int fx);                                         /* 0x4AF880 */

#define AU_TODAS (AU_CANT + AS_CANT)    /* 0..AU_CANT-1 auras de ítem · AU_CANT.. efectos de set */

static BYTE *g_au_base = NULL;
static float g_au_alto = 0.0f;
static int   g_au_avisos = 0;

static int au_leible(const void *p, SIZE_T n)
{
    MEMORY_BASIC_INFORMATION mi;
    if (!p || !VirtualQuery(p, &mi, sizeof mi) || mi.State != MEM_COMMIT) return 0;
    if (mi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return 0;
    return (BYTE *)p + n <= (BYTE *)mi.BaseAddress + mi.RegionSize;
}

static int au_en_carrera(void)
{
    BYTE **pa = (BYTE **)AUV(AU_APP), **pg = (BYTE **)AUV(AU_PARTIDA);
    if (!au_leible(pa, 4) || !au_leible(pg, 4) || !*pa || !*pg || !au_leible(*pa + 0xAFFC, 4)) return 0;
    return *(BYTE **)(*pa + 0xAFFC) == *pg;
}

static int au_fx(int k) { return k < AU_CANT ? AU_TABLA[k][1] : AS_TABLA[k - AU_CANT][1]; }

/* pone el aura `cual` (0..AU_TODAS-1, o -1 = ninguna) y saca las demás */
static void au_aplicar(void *pj, float x, float y, float z, int cual, const char *quien)
{
    if (!pj) return;
    for (int k = 0; k < AU_TODAS; k++) {
        int fx = au_fx(k);
        if (!fx) continue;                                       /* AS_TABLA vacía: { 0, 0 } */
        if (k == cual) {
            ((F_AU_PONER)AUV(0x4B06C0))(pj, fx, x, y + g_au_alto, z, 0.0f);
            if (g_au_avisos < 16) {
                g_au_avisos++;
                if (k < AU_CANT)
                    apuntar("  [aura] %s: el aura del efecto %d (Fx %d) a los pies de %p (%d, %d, %d)", quien,
                            AU_TABLA[k][0], fx, pj, (int)x, (int)(y + g_au_alto), (int)z);
                else
                    apuntar("  [aura] %s: el efecto del SET 0x%02X (Fx %d) a los pies de %p (%d, %d, %d)", quien,
                            AS_TABLA[k - AU_CANT][0], fx, pj, (int)x, (int)(y + g_au_alto), (int)z);
            }
        } else {
            ((F_AU_SACAR)AUV(0x4AF880))(pj, fx);
        }
    }
}

/* las MÍAS: por el inventario, como hace 0x4B1740 con las alas */
static void __fastcall au_mias(void *guion, void *nada, void *pj, float x, float y, float z)
{
    (void)nada;
    ((F_AU_MIAS)AUV(0x4B1740))(guion, pj, x, y, z);
    int cual = -1;
    void **items = (void **)AUV(AU_ITEMS);
    if (!au_en_carrera() && au_leible(items, 4) && *items)
        for (int k = 0; k < AU_CANT && cual < 0; k++)
            if (((F_AU_TIENE)AUV(0x489160))(*items, AU_TABLA[k][0])) cual = k;
    /* (145) el efecto de SET no sale en el muñequito propio: la lista de lo puesto que mira 0x489160 ([0x9314E0]+0x118)
     *   trae sólo los 1000xxx/1200xxx (efectos, joyas, monturas), NO la ropa — medido el 31-oct con jugadora_prueba
     *   («11 de 11: 1200160 1200164 1200156 1000861 …», sin ninguna de las 5 piezas). Ver SET_ESCOLAR.md §2. */
    au_aplicar(pj, x, y, z, cual, "mía");
}

/* las de OTRO: el Wing Id viene «empaquetado» (Wing Id | (aura + 1) << 16) */
static void __fastcall au_otro(void *guion, void *nada, void *pj, float x, float y, float z, int id)
{
    (void)nada;
    ((F_AU_OTRO)AUV(0x4B1960))(guion, pj, x, y, z, id & 0xFFFF);
    int b = (int)(((unsigned)id >> 16) & 0xFF);                 /* ★ 30-oct: el byte de arriba es FLOTAR (flotar.c) */
    int cual = b - 1;
    if (b >= 0xF0) {                                            /* (145) un efecto de SET (catalogo.aura_de_set) */
        cual = -1;
        for (int j = 0; j < AS_CANT; j++)
            if (AS_TABLA[j][0] == b && AS_TABLA[j][1]) cual = AU_CANT + j;
    } else if (cual >= AU_CANT) cual = -1;
    if (au_en_carrera()) cual = -1;
    au_aplicar(pj, x, y, z, cual, "de otro");
    if (!au_en_carrera())
        fl_desde_alas(pj, (int)(((unsigned)id >> 24) & 0xFF));
}

static const DWORD AU_MIAS[] = { 0x4CECEA, 0x4CF0EA, 0x4D008C, 0x4D8017, 0x4D8F39, 0x5A0CF9, 0x5B3637,
                                 0x61CAB5, 0x62586A, 0x62894D, 0x630EA8 };
static const DWORD AU_OTROS[] = { 0x451BCF, 0x59230B, 0x5B3610 };

/* la guarda de un `call` (E8 rel32): ¿apunta a `destino`? */
static int au_es_llamada(DWORD sitio, DWORD destino)
{
    BYTE *s = AUV(sitio);
    return s[0] == 0xE8 && (DWORD)(s + 5 + *(int *)(s + 1)) == (DWORD)AUV(destino);
}

static void au_escribir(DWORD sitio, void *nuevo)
{
    BYTE *s = AUV(sitio);
    DWORD viejo = 0;
    VirtualProtect(s + 1, 4, PAGE_EXECUTE_READWRITE, &viejo);
    *(int *)(s + 1) = (int)((DWORD)nuevo - ((DWORD)s + 5));
    VirtualProtect(s + 1, 4, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, 5);
}

static void aura_suelo_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("aura", "activo", 1, ini)) {
        apuntar("  [aura] apagada ([aura] activo=0)");
        return;
    }
    g_au_alto = (float)(int)GetPrivateProfileIntA("aura", "alto", 0, ini);
    g_au_base = (BYTE *)GetModuleHandleA(NULL);
    /* ⚠ las 14 guardas ANTES de escribir la primera: o van todas o ninguna */
    for (int i = 0; i < (int)(sizeof AU_MIAS / sizeof *AU_MIAS); i++)
        if (!au_es_llamada(AU_MIAS[i], 0x4B1740)) {
            apuntar("  [aura] ⛔ la llamada de 0x%06X no va a «poner mis alas» (0x4B1740): no se toca nada", AU_MIAS[i]);
            return;
        }
    for (int i = 0; i < (int)(sizeof AU_OTROS / sizeof *AU_OTROS); i++)
        if (!au_es_llamada(AU_OTROS[i], 0x4B1960)) {
            apuntar("  [aura] ⛔ la llamada de 0x%06X no va a «poner las alas de otro» (0x4B1960): no se toca nada", AU_OTROS[i]);
            return;
        }
    for (int i = 0; i < (int)(sizeof AU_MIAS / sizeof *AU_MIAS); i++) au_escribir(AU_MIAS[i], au_mias);
    for (int i = 0; i < (int)(sizeof AU_OTROS / sizeof *AU_OTROS); i++) au_escribir(AU_OTROS[i], au_otro);
    apuntar("  [aura] ok: %d auras de suelo + %d efectos de set, enganchadas en las %d llamadas de las alas (alto %d)", AU_CANT, AS_CANT,
            (int)(sizeof AU_MIAS / sizeof *AU_MIAS + sizeof AU_OTROS / sizeof *AU_OTROS), (int)g_au_alto);
}
