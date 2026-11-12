/* campanas.c — las campanas NUEVAS (778 «Oro Luminoso+», 783 «Plata Celeste+») funcionan como campanas (06-nov-2026, (160))
 *
 *   anonimo03 las probó y salió «Su personaje actual no puede hacer el movimiento particular». Medido en el cliente vivo:
 *   ⇒ EL EXE TIENE SUS 6 CAMPANAS ESCRITAS A MANO. 0x445280 (llamada una vez, desde 0x496F96, sobre [0x931674]) arma
 *     la lista (texto de system.csv, código, 0 oro / 1 plata) con 0x444520 + 0x47E3A0:
 *         181 oro · 183 oro · 297 plata · 304 plata · 774 oro · 775 plata
 *     y todo lo de campana la consulta: el comando del chat (0x444060 «¿es de oro?» / 0x444080 «¿es de plata?»), el
 *     candado «otro usuario ya la hizo sonar», el cartel. Un código que no está ahí cae al camino de los GESTOS
 *     (0x4B1D80), que pide tener puesto algo con ese ItemEffect (0x5285D0: la ropa puesta y la lista de joyas/marcos;
 *     en memoria, 2227/2228 = 0) ⇒ el texto 333 «movimiento particular». La 774/775 de fábrica funcionan por eso: están
 *     en la lista, no por su fila de emoticon2.
 *   1 · LA LISTA. Se envuelve la llamada de 0x496F96: corre la de fábrica y después se agregan 778 y 783 con el mismo
 *       0x444520 + 0x47E3A0 (y se libera el texto temporal como lo hace el exe). El nombre tiene que ser IGUAL al Name
 *       de su fila de emoticon2 (lo que se escribe en el chat). Si la dll llega tarde (la lista ya está armada), se
 *       agregan en el momento. Nunca dos veces.
 *   2 · EL CARTEL. 0x430420 «normaliza» toda campana a 181/183 (oro) o 297/304 (plata) antes de buscar el fondo en
 *       notice.xml ⇒ con la lista la 778 saldría con el cartel de la 183. En 0x430445 (mov ecx,[0x931674], 6 bytes)
 *       una cueva: si el código es 778 o 783 salta a 0x430490 (la búsqueda) con el código tal cual ⇒ notice.xml
 *       `G 778 -> img 120`, `P 783 -> img 121`. Es el mismo atajo que hizo el amigo en su exe (`.bellui`), sólo para
 *       las nuevas. La letra G/P elige el texto (oro/plata).
 *   Perillas: [campanas] activo=1 · cartel=1
 *   Doc: documentacion/CAMPANAS_PLUS_NUEVAS.md
 */
#define CPV(x) (g_cp_base + ((DWORD)(x) - 0x400000))

typedef void *(__fastcall *F_CP_ENTRADA)(void *self, void *edx, const char *nombre, DWORD item, DWORD tipo);
typedef void (__fastcall *F_CP_AGREGAR)(void *lista, void *edx, void *entrada);
typedef void (__fastcall *F_CP_ARMAR)(void *lista, void *edx);
typedef void (__cdecl *F_CP_LIBERAR)(void *p);

static BYTE *g_cp_base = NULL;
static const struct { const char *nombre; DWORD item, tipo; } CP_NUEVAS[] = {
    { "/Campana de Oro Luminoso+", 778, 0 },
    { "/Campana de Plata Celeste+", 783, 1 },
};

static int cp_esta(BYTE *lista, DWORD item)
{
    BYTE *p = *(BYTE **)(lista + 0xC), *fin = *(BYTE **)(lista + 0x10);
    if (!p || !fin || fin < p) return 0;
    for (; p + 0x24 <= fin; p += 0x24)
        if (*(DWORD *)(p + 0x1C) == item) return 1;
    return 0;
}

static int cp_agregar_nuevas(BYTE *lista)
{
    int n = 0;
    if (!lista) return 0;
    for (int i = 0; i < (int)(sizeof(CP_NUEVAS) / sizeof(CP_NUEVAS[0])); i++) {
        if (cp_esta(lista, CP_NUEVAS[i].item)) continue;
        BYTE tmp[0x24];
        ZeroMemory(tmp, sizeof(tmp));
        ((F_CP_ENTRADA)CPV(0x444520))(tmp, NULL, CP_NUEVAS[i].nombre, CP_NUEVAS[i].item, CP_NUEVAS[i].tipo);
        ((F_CP_AGREGAR)CPV(0x47E3A0))(lista, NULL, tmp);
        if (*(DWORD *)(tmp + 0x18) >= 0x10) ((F_CP_LIBERAR)CPV(0x74F8E6))(*(void **)(tmp + 4));   /* como el exe */
        n++;
    }
    return n;
}

static void __fastcall cp_armar(void *lista, void *edx)
{
    (void)edx;
    ((F_CP_ARMAR)CPV(0x445280))(lista, NULL);                         /* las 6 de fábrica */
    int n = cp_agregar_nuevas((BYTE *)lista);
    apuntar("  [campanas] lista de campanas: +%d (778 Oro Luminoso+, 783 Plata Celeste+)", n);
}

static int cp_pisar(DWORD va, const void *nuevo, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(CPV(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(CPV(va), nuevo, n);
    VirtualProtect(CPV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), CPV(va), n);
    return 1;
}

static void cp_lista_poner(void)
{
    BYTE *call = CPV(0x496F96);
    static const BYTE e_lea[6] = { 0x8D, 0x8E, 0xA8, 0xAF, 0x00, 0x00 };   /* lea ecx,[esi+0xAFA8] */
    static const BYTE e_armar[3] = { 0x6A, 0xFF, 0x68 };                    /* push -1 · push … */
    static const BYTE e_entrada[3] = { 0x6A, 0xFF, 0x68 };
    static const BYTE e_agregar[5] = { 0x83, 0xEC, 0x08, 0x53, 0x56 };
    if (memcmp(CPV(0x496F90), e_lea, 6) || call[0] != 0xE8
        || (DWORD)(call + 5 + *(int *)(call + 1)) != (DWORD)CPV(0x445280) || memcmp(CPV(0x445280), e_armar, 3)
        || memcmp(CPV(0x444520), e_entrada, 3) || memcmp(CPV(0x47E3A0), e_agregar, 5)
        || *(DWORD *)CPV(0x4453DE) != 0x306 || *(DWORD *)CPV(0x445425) != 0x307) {
        apuntar("  [campanas] ⛔ la lista de campanas (0x445280) no es la de fábrica: las nuevas NO funcionan");
        return;
    }
    /* la dll llegó tarde: la lista ya está armada */
    BYTE *lista = *(BYTE **)CPV(0x931674);
    if (lista && *(BYTE **)(lista + 0xC) && *(BYTE **)(lista + 0x10) > *(BYTE **)(lista + 0xC)) {
        int n = cp_agregar_nuevas(lista);
        apuntar("  [campanas] ok: la lista ya estaba armada, +%d", n);
        return;
    }
    BYTE s[5] = { 0xE8, 0, 0, 0, 0 };
    *(int *)(s + 1) = (int)((DWORD)cp_armar - ((DWORD)CPV(0x496F96) + 5));
    if (cp_pisar(0x496F96, s, 5))
        apuntar("  [campanas] ok: 778 y 783 entran a la lista de campanas cuando el exe la arme");
}

static void cp_cartel_poner(void)
{
    /* 0x430445 mov ecx,[0x931674] (8B 0D 74 16 93 00) · 0x43044B push edi · 0x430490 lea ecx,[esp+0x18] (la búsqueda) */
    static const BYTE e[7] = { 0x8B, 0x0D, 0x74, 0x16, 0x93, 0x00, 0x57 };
    static const BYTE e_busca[4] = { 0x8D, 0x4C, 0x24, 0x18 };
    if (memcmp(CPV(0x430445), e, 7) || memcmp(CPV(0x430490), e_busca, 4)) {
        apuntar("  [campanas] ⛔ el cartel (0x430445) no es el de fábrica: las nuevas salen con el cartel de la 183/304");
        return;
    }
    BYTE *c = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!c) return;
    int i = 0;
    for (int k = 0; k < 2; k++) {                                       /* cmp edi,código · je → la búsqueda */
        c[i++] = 0x81; c[i++] = 0xFF; *(DWORD *)(c + i) = CP_NUEVAS[k].item; i += 4;
        c[i++] = 0x0F; c[i++] = 0x84; *(int *)(c + i) = (int)((DWORD)CPV(0x430490) - (DWORD)(c + i + 4)); i += 4;
    }
    CopyMemory(c + i, e, 6); i += 6;                                    /* mov ecx,[0x931674] (lo pisado) */
    c[i++] = 0xE9; *(int *)(c + i) = (int)((DWORD)CPV(0x43044B) - (DWORD)(c + i + 4)); i += 4;
    BYTE s[6] = { 0xE9, 0, 0, 0, 0, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)c - ((DWORD)CPV(0x430445) + 5));
    if (cp_pisar(0x430445, s, 6))
        apuntar("  [campanas] ok: el cartel de 778/783 sale con su código (notice.xml), sin pasar a 181/297");
}

static void campanas_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("campanas", "activo", 1, ini)) {
        apuntar("  [campanas] apagado ([campanas] activo=0): 778/783 no funcionan como campanas");
        return;
    }
    g_cp_base = (BYTE *)GetModuleHandleA(NULL);
    cp_lista_poner();
    if (GetPrivateProfileIntA("campanas", "cartel", 1, ini)) cp_cartel_poner();
}
