/* pareja_poses.c — LAS POSES DE PAREJA (`coupleaction.xml` del 2019 / VFUN) en la carrera del 2013 (30-oct-2026)
 *
 *   anonimo03 (30-oct): «poses de entrada en las que las parejas hacen la animación juntas antes de correr». Doc:
 *   PAREJA_POSES.md. Los datos (3 ítems, 127 animaciones, 18 Fx, la tabla `pareja_poses_datos.h`) los arma
 *   `herramientas/poses_pareja_crear.py`. El reversing del 2019: `_trabajo/pareja_poses/RE_2019_coupleaction.md`.
 *
 *   Cómo lo hace el 2019 (MEDIDO): cada cliente decide solo, sin paquete. `CoupleAction(fase)` (0x6670C0) corre en dos
 *   momentos: el READY de cada corredor (cGame WARMING → cHero::PlayReady) y la pose de RESULTADO (el resolvedor de
 *   movimientos, ids de resultado). Mira el ítem de pareja de los dos (`GetCoupleItem` = efecto del ítem puesto, sólo
 *   cuerpos chicos 0x1FF54/0x1FF55), y es SINCRONIZADA (`s`) si la pareja corre en el asiento de al lado con el MISMO
 *   ítem; si no, SEPARADA (`n`). Arma `couple_<ready|win|lose>_<s|n><l|n>_<Id>[_l|_r]` (PlayAni le pega el cuerpo),
 *   encola la siguiente y crea el objeto (Fx) del ítem.
 *
 *   En el 2013 (la MISMA maquinaria, medida):
 *     0x507430  cHero::PlayReady  thiscall(hero) → al. Es la que hace la ceremonia de largada (0x505800) y devuelve 1;
 *               con pose de pareja hacemos lo mismo: la pose y 1. (83 EC 10 53 56: trampolín de 5 bytes)
 *     0x506BA0  el resolvedor de movimientos  thiscall(hero, id, buf) ret 8. Los ids 0x33..0x38 son el RESULTADO (0x38 =
 *               perdió: lo decidió el juego, también por equipos). Devolver 0 = «no reproduzcas nada» (como su rama
 *               [+0x31C]: `[hero+0x48] = id`). ⚠ Se llama también desde 0x572CDD (otro contexto): sólo actuamos si el
 *               llamador es PlayMotion (vuelve a 0x50AD02). (53 55 56 57 8B F9: trampolín de 6 bytes)
 *     0x5035A0  PlayAni(hero, nombre, 1) — ya arma «%s_%s» con el cuerpo · 0x503960 / 0x505C20(7, nombre, 1) la cola
 *     0x4FDDB0  crea un Fx sobre el corredor (hero, fx, x, y, z, w)
 *     [0x931660] el administrador de asientos: 0x500860 la pareja (0xFF = ninguna) · 0x436380 el personaje ·
 *               0x5285D0 «¿tiene puesto un ítem con este efecto?» (sirve para cualquier asiento)
 *     [0x9314C8]+0xC  los flags del modo (word): 0x100 práctica, 0x08 / 0x20 especiales (sin poses, como el 2019),
 *               0x40 equipos de a dos (nunca sincronizada, como el 2019)
 *   Diferencias con el 2019, a propósito:
 *     · la pose POR DEFECTO (Id 0, sin ítem): en el 2019 sale sólo en su modo 0x400, y en el 2013 el 0x400 es el
 *       COOPERATIVO (CalcGameFlags = 0x413). ★ 30-oct, anonimo03 «adelante»: sale para toda pareja que corre junta sin ítem
 *       (ninguno de los dos), en cualquier modo de los que tienen poses. [pareja_poses] por_defecto=0 la apaga.
 *     · el ready tipo 3 vuelve a «예고루프» (la pose de preparados del 2013) y no a «준비».
 *     · el 2019 espera a la pareja para la pose de resultado (hero+0x330, que el 2013 no tiene): acá, si la pareja
 *       todavía no llegó, la pose sale SEPARADA.
 *   [pareja_poses] activo=0 lo apaga · log=1 anota cada pose.
 */
#include "pareja_poses_datos.h"

#define PARV(x) (g_par_base + ((DWORD)(x) - 0x400000))

typedef BYTE (__fastcall *F_PAR_READY)(BYTE *hero, void *nada);
typedef char *(__fastcall *F_PAR_RESOLVER)(BYTE *hero, void *nada, DWORD id, char *buf);
typedef void (__attribute__((thiscall)) *F_PAR_ANI)(BYTE *hero, const char *nombre, int flag);           /* 0x5035A0 */
typedef void (__attribute__((thiscall)) *F_PAR_COLA_LIMPIAR)(BYTE *cola);                                 /* 0x503960 */
typedef void (__attribute__((thiscall)) *F_PAR_COLA_PONER)(BYTE *cola, int tipo, const char *nombre, int flag);   /* 0x505C20 */
typedef void (__attribute__((thiscall)) *F_PAR_FX)(BYTE *hero, int fx, float x, float y, float z, float w);   /* 0x4FDDB0 */
typedef BYTE (__attribute__((thiscall)) *F_PAR_PAREJA)(void *mgr, BYTE slot);                             /* 0x500860 */
typedef DWORD (__attribute__((thiscall)) *F_PAR_CHAR)(void *mgr, BYTE slot);                              /* 0x436380 */
typedef BYTE (__attribute__((thiscall)) *F_PAR_TIENE)(void *mgr, BYTE slot, WORD efecto);                 /* 0x5285D0 */
typedef BYTE (__attribute__((thiscall)) *F_PAR_PUESTO)(void *mgr, BYTE slot);                             /* 0x48A380 */
typedef void *(__attribute__((thiscall)) *F_PAR_CEREMONIA)(void *guion, int lugar, BYTE slot);           /* 0x4B23A0 */

static const char PAR_PREPARADOS[] = "\xBF\xB9\xB0\xED\xB7\xE7\xC7\xC1";   /* 예고루프 (0x87D9CC) */

static BYTE *g_par_base = NULL;
static int g_par_activo = 0, g_par_log = 0, g_par_defecto = 1;
static void *g_par_orig_ready = NULL, *g_par_orig_resolver = NULL;
/* la pose de resultado se hace UNA vez por corredor y carrera: el update por cuadro vuelve a pedir el movimiento */
static BYTE *g_par_hecho[16];
static BYTE g_par_hecho_id[16];

static void *par_mgr(void) { return *(void **)PARV(0x931660); }
static WORD par_modo(void)
{
    BYTE *g = *(BYTE **)PARV(0x9314C8);
    return g ? *(WORD *)(g + 0xC) : 0;
}

/* GetCoupleItem (0x62D210 del 2019): la fila de la tabla del ítem de pareja que tiene puesto el de ese asiento, o -1 */
static int par_fila_de(BYTE slot)
{
    if (slot == 0xFF) return -1;
    void *m = par_mgr();
    if (!m) return -1;
    DWORD ch = ((F_PAR_CHAR)PARV(0x436380))(m, slot);
    if (ch != 0x1FF54 && ch != 0x1FF55) return -1;               /* sólo los cuerpos chicos: las poses son de b/g */
    for (int i = 0; i < PAR_FILAS; i++)
        if (PAR_TABLA[i].efecto && ((F_PAR_TIENE)PARV(0x5285D0))(m, slot, (WORD)PAR_TABLA[i].efecto))
            return i;
    return -1;
}

/* CoupleAction (0x6670C0 del 2019). fase 0 = ready · 1 = ganó · 2 = perdió. 1 = hizo la pose */
static int par_pose(BYTE *h, int fase)
{
    WORD modo = par_modo();
    if (modo & (0x08 | 0x20 | 0x100)) return 0;
    void *m = par_mgr();
    if (!m || *(DWORD *)(h + 0x54)) return 0;                    /* el que mira no posa */
    BYTE slot = h[0x49];
    int yo = par_fila_de(slot);
    BYTE pareja = ((F_PAR_PAREJA)PARV(0x500860))(m, slot);
    int ella = pareja != 0xFF ? par_fila_de(pareja) : -1;
    if (yo < 0) {
        /* ★ la pose POR DEFECTO (la fila Id 0, la de toda pareja): ninguno de los dos tiene ítem y la pareja corre. Como el
         *   2019 (0x6670C0): si el otro tiene ítem y yo no, nada. Sus animaciones están para los 4 cuerpos. */
        if (!g_par_defecto || pareja == 0xFF || ella >= 0) return 0;
        /* ⛔ y sin tapar una CEREMONIA elegida: la fila de specialentrance (GameStart 0 / GameEnd 1) de ese asiento */
        void *guion = *(void **)PARV(0x9316D4);
        int lugar = fase == 0 ? 0 : 1;
        if (!guion || ((F_PAR_CEREMONIA)PARV(0x4B23A0))(guion, lugar, slot)) return 0;
        if (((F_PAR_CEREMONIA)PARV(0x4B23A0))(guion, lugar, pareja)) ella = -2;   /* la pareja hace su ceremonia: separada */
        for (yo = 0; yo < PAR_FILAS && PAR_TABLA[yo].id != 0; yo++) {}
        if (yo >= PAR_FILAS) return 0;
        if (ella != -2) ella = yo;                               /* los dos sin ítem = «el mismo» */
    }
    const PAR_FILA *f = &PAR_TABLA[yo];
    int sync = pareja != 0xFF && (slot + 1 == pareja || pareja + 1 == slot) && ella == yo && !(modo & 0x40);
    if (sync && fase) {                                          /* ★ el resultado juntos sólo si la pareja ya llegó */
        BYTE p = ((F_PAR_PUESTO)PARV(0x48A380))(m, pareja);
        if (p == 0) sync = 0;
    }
    int estado = fase == 0 ? 0 : fase == 1 ? 2 : 4;
    int col = estado + (sync ? 0 : 1);
    int tipo = f->tipo[col];
    char clave[64], siguiente[64];
    siguiente[0] = 0;
    wsprintfA(clave, "couple_%s_%c", fase == 0 ? "ready" : fase == 1 ? "win" : "lose", sync ? 's' : 'n');
    if (tipo == 2) {
        wsprintfA(siguiente, "%sl_%d", clave, f->id);
        wsprintfA(clave + lstrlenA(clave), "n_%d", f->id);
    } else {
        wsprintfA(clave + lstrlenA(clave), "l_%d", f->id);
        if (tipo == 3) {
            if (!f->simetria && sync) lstrcatA(clave, slot < pareja ? "_l" : "_r");
            lstrcpyA(siguiente, PAR_PREPARADOS);
        }
    }
    int fx = f->fx[((F_PAR_CHAR)PARV(0x436380))(m, slot) == 0x1FF55 ? 1 : 0][col];
    if (fx) {
        float dx = (fase == 0 && sync) ? (slot > pareja ? -111.75f : 111.75f) : 0.0f;
        ((F_PAR_FX)PARV(0x4FDDB0))(h, fx, dx, 0.0f, 0.0f, 0.0f);
    }
    ((F_PAR_ANI)PARV(0x5035A0))(h, clave, 1);
    ((F_PAR_COLA_LIMPIAR)PARV(0x503960))(h + 0x2FC);
    if (siguiente[0]) ((F_PAR_COLA_PONER)PARV(0x505C20))(h + 0x2FC, 7, siguiente, 1);
    if (g_par_log)
        apuntar("  [pareja_poses] pid %lu asiento %d (pareja %d, fila %d/%d): «%s» → «%s» · Fx %d", GetCurrentProcessId(),
                slot, pareja, yo, ella,
                clave, siguiente[0] ? (siguiente[0] == 'c' ? siguiente : "예고루프") : "-", fx);
    return 1;
}

static BYTE __fastcall par_ready(BYTE *h, void *nada)
{
    if (g_par_activo && h) {
        for (int i = 0; i < 16; i++)
            if (g_par_hecho[i] == h) g_par_hecho[i] = NULL;        /* carrera nueva: se olvida el resultado anterior */
        if (par_pose(h, 0)) return 1;                             /* como la ceremonia: el llamador (0x4F0CC4) marca +0x129 */
    }
    return ((F_PAR_READY)g_par_orig_ready)(h, nada);
}

static char *__fastcall par_resolver(BYTE *h, void *nada, DWORD id, char *buf)
{
    BYTE i8 = (BYTE)id;
    if (g_par_activo && h && i8 >= 0x33 && i8 <= 0x38
        && (DWORD)__builtin_return_address(0) == (DWORD)PARV(0x50AD02)) {
        int libre = -1;
        for (int i = 0; i < 16; i++) {
            if (g_par_hecho[i] == h && g_par_hecho_id[i] == i8) {  /* ya posa: el update lo vuelve a pedir */
                h[0x48] = i8;
                return NULL;
            }
            if (!g_par_hecho[i] && libre < 0) libre = i;
        }
        if (par_pose(h, i8 == 0x38 ? 2 : 1)) {
            if (libre >= 0) { g_par_hecho[libre] = h; g_par_hecho_id[libre] = i8; }
            h[0x48] = i8;                                        /* como la rama [+0x31C] del propio 0x506BA0 */
            return NULL;
        }
    }
    return ((F_PAR_RESOLVER)g_par_orig_resolver)(h, nada, id, buf);
}

static void *par_trampolin(DWORD va, const BYTE *esperado, int n, void *mio)
{
    if (memcmp(PARV(va), esperado, n) != 0) return NULL;
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return NULL;
    CopyMemory(t, esperado, n);                                  /* lo de fábrica + jmp de vuelta */
    t[n] = 0xE9;
    *(int *)(t + n + 1) = (int)((DWORD)PARV(va + n) - (DWORD)(t + n + 5));
    BYTE s[8] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)mio - ((DWORD)PARV(va) + 5));
    DWORD viejo;
    VirtualProtect(PARV(va), n, PAGE_EXECUTE_READWRITE, &viejo);
    CopyMemory(PARV(va), s, n);
    VirtualProtect(PARV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), PARV(va), n);
    return t;
}

static void pareja_poses_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("pareja_poses", "activo", 1, ini)) {
        apuntar("  [pareja_poses] apagado ([pareja_poses] activo=0)");
        return;
    }
    g_par_log = GetPrivateProfileIntA("pareja_poses", "log", 0, ini);
    g_par_defecto = GetPrivateProfileIntA("pareja_poses", "por_defecto", 1, ini);
    g_par_base = (BYTE *)GetModuleHandleA(NULL);
    static const BYTE e_ready[5] = { 0x83, 0xEC, 0x10, 0x53, 0x56 };
    static const BYTE e_resolver[6] = { 0x53, 0x55, 0x56, 0x57, 0x8B, 0xF9 };
    static const BYTE e_motion[5] = { 0xE8, 0x9E, 0xBE, 0xFF, 0xFF };   /* 0x50ACFD call 0x506BA0 */
    /* ⚠ todas las guardas ANTES de escribir: o va todo o nada */
    if (memcmp(PARV(0x507430), e_ready, 5) || memcmp(PARV(0x506BA0), e_resolver, 6) || memcmp(PARV(0x50ACFD), e_motion, 5)
        || lstrcmpA((const char *)PARV(0x87D9CC), PAR_PREPARADOS)) {
        apuntar("  [pareja_poses] ⛔ 0x507430 / 0x506BA0 / 0x50ACFD / «예고루프» no son los de fábrica: no se toca nada");
        return;
    }
    g_par_orig_ready = par_trampolin(0x507430, e_ready, 5, (void *)par_ready);
    g_par_orig_resolver = par_trampolin(0x506BA0, e_resolver, 6, (void *)par_resolver);
    if (!g_par_orig_ready || !g_par_orig_resolver) {
        apuntar("  [pareja_poses] ⛔ no pude armar los trampolines");
        return;
    }
    g_par_activo = 1;
    apuntar("  [pareja_poses] ok: ready (0x507430) y resultado (0x506BA0) enganchados · %d filas", PAR_FILAS);
}
