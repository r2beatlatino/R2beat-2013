/* chart_grande.c — el chart del FF57 ya no tiene techo de 4096 bytes (06-nov-2026, (161))
 *
 *   El handler del FF57 (0x5D01F0) copia la partitura en una caja de la PILA de 4096 bytes sin mirar el largo que
 *   manda el server: un chart de 4097 pisa la cookie /GS y Windows mata el proceso sin rastro
 *   (documentacion/CHART_TECHO_4096.md). Hasta hoy se esquivaba recomprimiendo con zopfli; «Chikyuu no Ura» difícil
 *   (1882 notas) queda en 4238 B con cualquier ajuste y no entra.
 *
 *   ★ La caja de la pila se usa en DOS lugares, y nada más (desarmado entero, 0x5D01F0..0x5D02CE):
 *       0x5D024B  lea ecx,[esp+0x18] · push ecx · mov ecx,esi · call 0x67D200   ← la llena (lee `largo` bytes)
 *       0x5D026E  lea ecx,[esp+0x1C] · push ecx                                  ← se la pasa a 0x56F6F0 (las notas)
 *     0x56F6F0 → 0x56EF40 la lee en el momento (la infla y arma sus vectores): nadie se queda con el puntero.
 *   ⇒ Se cambian esos dos pedazos por `push <caja de la dll>`, del MISMO largo (12 y 5 bytes): la caja de la pila
 *     ya no se toca, y la cookie tampoco. La caja nuestra es de 64 KB = lo que entra en el largo (u16).
 *       0x5D024B  68 <caja> · 8B CE · E8 <0x67D200>       (12 bytes)
 *       0x5D026E  68 <caja>                                (5 bytes)
 *   El FF57 llega por el hilo del juego, uno a la vez: una caja sola alcanza.
 *
 *   ★ El server tiene que SABER que esta dll lo tiene (a una vieja, un chart de más de 4096 la mata): se lo dice
 *     cajanegra.c en la misma línea «R2DLL …» del FF59 que ya usa el abandono de la de 12 (` chart64k=1`).
 *
 *   Perillas: [chart_grande] activo=1
 *   Doc: documentacion/CHART_TECHO_4096.md §7
 */
#define CG_VA(x) (g_cg_base + ((DWORD)(x) - 0x400000))

static BYTE *g_cg_base = NULL;
static BYTE g_cg_caja[65536];
static int g_cg_activo = 0;                    /* lo lee cajanegra.c para avisarle al server */

static int cg_pisar(DWORD va, const void *nuevo, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(CG_VA(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(CG_VA(va), nuevo, n);
    VirtualProtect(CG_VA(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), CG_VA(va), n);
    return 1;
}

static void chart_grande_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("chart_grande", "activo", 1, ini)) {
        apuntar("  [chart_grande] apagado ([chart_grande] activo=0): el chart del FF57 sigue con techo de 4096");
        return;
    }
    g_cg_base = (BYTE *)GetModuleHandleA(NULL);
    /* lo de fábrica, entero: la reserva del marco, los dos pedazos y lo que los rodea */
    static const BYTE e_marco[5] = { 0xB8, 0x10, 0x10, 0x00, 0x00 };                  /* mov eax,0x1010 */
    static const BYTE e_llena[12] = { 0x8D, 0x4C, 0x24, 0x18, 0x51, 0x8B, 0xCE,       /* lea ecx,[esp+18] · push ecx */
                                      0xE8, 0xA9, 0xCF, 0x0A, 0x00 };                  /* mov ecx,esi · call 67D200 */
    static const BYTE e_pasa[10] = { 0x8D, 0x4C, 0x24, 0x1C, 0x51,                    /* lea ecx,[esp+1C] · push ecx */
                                     0x8B, 0x0D, 0xC8, 0x14, 0x93 };                   /* mov ecx,[0x9314C8] */
    if (memcmp(CG_VA(0x5D01F0), e_marco, 5) || memcmp(CG_VA(0x5D024B), e_llena, 12)
        || memcmp(CG_VA(0x5D026E), e_pasa, 10)) {
        apuntar("  [chart_grande] ⛔ el handler del FF57 (0x5D01F0) no es el de fábrica: el techo de 4096 sigue");
        return;
    }
    BYTE llena[12] = { 0x68, 0, 0, 0, 0, 0x8B, 0xCE, 0xE8, 0, 0, 0, 0 };
    *(DWORD *)(llena + 1) = (DWORD)g_cg_caja;
    *(int *)(llena + 8) = (int)((DWORD)CG_VA(0x67D200) - ((DWORD)CG_VA(0x5D024B) + 12));
    BYTE pasa[5] = { 0x68, 0, 0, 0, 0 };
    *(DWORD *)(pasa + 1) = (DWORD)g_cg_caja;
    if (!cg_pisar(0x5D024B, llena, 12)) return;
    if (!cg_pisar(0x5D026E, pasa, 5)) {
        cg_pisar(0x5D024B, e_llena, 12);                        /* los dos o ninguno */
        return;
    }
    g_cg_activo = 1;
    apuntar("  [chart_grande] ok: el chart del FF57 va a una caja de 64 KB (sin el techo de 4096 de la pila)");
}
