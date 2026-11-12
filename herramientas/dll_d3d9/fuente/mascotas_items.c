/* mascotas_items.c — (147) CUALQUIER MASCOTA da 2 casilleros en la carrera de ítems (31-oct-2026)
 *
 *   anonimo03: «camino B para las mascotas … que en modo item las mascotas sí den-acumulen 2 items». Doc:
 *   MASCOTAS_DOS_ITEMS.md. Hoy sólo las mascotas con ItemEffect 1 («Habrá más muescas para ítems», 140) dan el
 *   segundo casillero; las otras ~130 (las de pareja, las Mong, la de cibercafé, los Gorilas…) tienen su propio
 *   ItemEffect y no. ⇒ en la carrera de ítems, la MASCOTA PUESTA cuenta como si tuviera el efecto 1. Sin tocar sus
 *   textos ni sus funciones: el ítem sigue siendo el mismo, sólo cambia la respuesta a UNA pregunta en UN lugar.
 *
 *   Lo medido en R2Beat.exe (0x50D0xx…0x50D515, la función que arma cada cPlayer para la carrera — corre UNA VEZ POR
 *   ASIENTO: anota `[cPlayer+0x49] = asiento` (0x50D16E) y crea la mascota de ese asiento (0x50D1E4)):
 *     0x50D440  mov byte [esi+0x50],1          los casilleros de ítem: 1
 *     0x50D46F  [[0x9314C8]+0xC] & 1           la carrera de ÍTEMS
 *     0x50D485  call 0x5285D0 (asiento, 1)     ★ «¿tiene puesto algo con el efecto 1?» ← ACÁ
 *     0x50D49A  call 0x5285D0 (asiento, 0x107) …o el 263 (cibercafé)  ⇒  0x50D4A3 mov byte [esi+0x50],2
 *     0x50D511  con el flag 0x400 (cooperativo): 2 siempre
 *   La caja (0x5045D0) compara lo que tenés encima con [esi+0x50].
 *
 *   ¿Hay mascota en el asiento? La misma función la crea así (0x50D1BF…0x50D1E4):
 *     p = [0x931660]->0x44F180(asiento)   = &nodo+0x54 del padrón (0 si no hay nadie)
 *     [p+0x1C] = la prenda de la RANURA 6 = el ítem de la MASCOTA (0 = ninguna) → 0x525DB0 (cPet)
 *   Como `selector.c` (que también la lee de la ranura 6). Y además tiene que ser de las mascotas (6xxxxx, la 0505):
 *   si algún día la ranura 6 trae otra cosa, no se regala el casillero.
 *
 *   Lo nuestro: SÓLO el destino del `call` de 0x50D485 (como `heroe_aleatorio.c`). `mi_efecto1` pregunta lo de siempre
 *   y, si contesta que no, contesta que sí cuando el asiento tiene mascota. Corre para los 6 (o 12) asientos, así que
 *   vale para el jugador local y para los otros. El flag 2 y el cibercafé quedan como estaban.
 *   ⚠ La guarda: los 0x6B bytes de 0x50D440…0x50D4AA tienen que ser los de fábrica, y 0x44F180 / 0x5285D0 empezar
 *     como las conocemos. Si no, no se toca nada.
 *   [mascotas_items] activo=0 lo apaga · log=1 anota cada asiento (con y sin mascota).
 */
#define MI_V(x) (g_mi_base + ((DWORD)(x) - 0x400000))
#define MI_SITIO 0x50D485                       /* el call 0x5285D0 (asiento, 1) */
#define MI_EFECTO_MASCOTA 1                     /* «Habrá más muescas para ítems» */

typedef BYTE  (__fastcall *F_MI_EFECTO)(void *sala, void *nada, int asiento, int efecto);   /* 0x5285D0, thiscall ret 8 */
typedef BYTE *(__fastcall *F_MI_NODO)(void *sala, void *nada, int asiento);                 /* 0x44F180, thiscall ret 4 */

static BYTE *g_mi_base = NULL;
static int g_mi_activo = 0, g_mi_log = 0;

/* lo de fábrica, de 0x50D440 (mov byte [esi+0x50],1) a 0x50D4A6 (mov byte [esi+0x50],2), MEDIDO en el .pristino */
static const BYTE MI_ESPERADO[0x6B] = {
    0xC6, 0x46, 0x50, 0x01, 0x8B, 0x15, 0xC8, 0x14, 0x93, 0x00, 0xB9, 0x00, 0x20, 0x00, 0x00, 0x66,
    0x85, 0x4A, 0x0C, 0x0F, 0x85, 0xBC, 0x00, 0x00, 0x00, 0x8B, 0xCE, 0xC6, 0x86, 0xBC, 0x01, 0x00,
    0x00, 0x00, 0xE8, 0x49, 0x1B, 0xFF, 0xFF, 0x84, 0xC0, 0x0F, 0x84, 0x91, 0x00, 0x00, 0x00, 0xA1,
    0xC8, 0x14, 0x93, 0x00, 0x0F, 0xB7, 0x40, 0x0C, 0xA8, 0x01, 0x74, 0x2B, 0x8B, 0x0D, 0x60, 0x16,
    0x93, 0x00, 0x6A, 0x01, 0x53, 0xE8, 0x46, 0xB1, 0x01, 0x00, 0x84, 0xC0, 0x75, 0x15, 0x8B, 0x0D,
    0x60, 0x16, 0x93, 0x00, 0x68, 0x07, 0x01, 0x00, 0x00, 0x53, 0xE8, 0x31, 0xB1, 0x01, 0x00, 0x84,
    0xC0, 0x74, 0x04, 0xC6, 0x46, 0x50, 0x02, 0x8B, 0x0D, 0xC8, 0x14,
};
static const BYTE MI_NODO_INICIO[8] = { 0x83, 0xEC, 0x08, 0x53, 0x56, 0x57, 0x8B, 0xF1 };     /* 0x44F180 */
static const BYTE MI_EFECTO_INICIO[8] = { 0x6A, 0xFF, 0x68, 0x08, 0x07, 0x85, 0x00, 0x64 };   /* 0x5285D0 */

/* el ítem de la mascota del asiento (la ranura 6 del padrón), o 0 */
static DWORD mi_mascota(void *sala, int asiento)
{
    BYTE *p = ((F_MI_NODO)MI_V(0x44F180))(sala, NULL, asiento & 0xFF);
    if (!p) return 0;
    DWORD item = *(DWORD *)(p + 0x1C);
    return (item >= 600000 && item <= 699999) ? item : 0;
}

/* 0x50D485: «¿el asiento tiene puesto algo con el efecto 1?» — y si no, ¿tiene mascota? */
static BYTE __fastcall mi_efecto1(void *sala, void *nada, int asiento, int efecto)
{
    BYTE r = ((F_MI_EFECTO)MI_V(0x5285D0))(sala, nada, asiento, efecto);
    if (r || efecto != MI_EFECTO_MASCOTA || !sala) {
        if (g_mi_log)
            apuntar("  [mascotas_items] asiento %d: efecto %d de fábrica = %d -> %d casilleros", asiento & 0xFF, efecto,
                    r, r ? 2 : 1);
        return r;
    }
    DWORD m = mi_mascota(sala, asiento);
    if (g_mi_log)
        apuntar("  [mascotas_items] asiento %d: mascota %u -> %d casilleros", asiento & 0xFF, (unsigned)m, m ? 2 : 1);
    return m ? 1 : 0;
}

static void mascotas_items_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("mascotas_items", "activo", 1, ini)) {
        apuntar("  [mascotas_items] apagado ([mascotas_items] activo=0): sólo las mascotas con efecto 1 dan 2 casilleros");
        return;
    }
    g_mi_log = GetPrivateProfileIntA("mascotas_items", "log", 0, ini);
    g_mi_base = (BYTE *)GetModuleHandleA(NULL);
    BYTE *s = MI_V(MI_SITIO);
    /* ⚠ todas las guardas ANTES de escribir */
    if (memcmp(MI_V(0x50D440), MI_ESPERADO, sizeof(MI_ESPERADO)) != 0 ||
        s[0] != 0xE8 || (DWORD)(s + 5 + *(int *)(s + 1)) != (DWORD)MI_V(0x5285D0) ||
        memcmp(MI_V(0x44F180), MI_NODO_INICIO, 8) != 0 || memcmp(MI_V(0x5285D0), MI_EFECTO_INICIO, 8) != 0) {
        apuntar("  [mascotas_items] ⛔ 0x50D440…0x50D4AA / 0x44F180 / 0x5285D0 no son los de fábrica: no se toca nada");
        return;
    }
    DWORD viejo = 0;
    int rel = (int)((DWORD)mi_efecto1 - ((DWORD)s + 5));
    VirtualProtect(s + 1, 4, PAGE_EXECUTE_READWRITE, &viejo);
    *(int *)(s + 1) = rel;
    VirtualProtect(s + 1, 4, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, 5);
    g_mi_activo = 1;
    apuntar("  [mascotas_items] ok: en la carrera de ítems, cualquier mascota (ranura 6, 6xxxxx) da 2 casilleros (0x%06X)",
            MI_SITIO);
}
