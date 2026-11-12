/* dados12.c — 12 + ÍTEM: la COLA DE DADOS de las cajas tiene lugar para 6 (13-oct-2026)
 *
 *   anonimo03: «que el modo ítem funcione en solo + ítem / equipo + ítem con el modo 12 prendido». Antes: «empieza sin
 *   audio y crashea a los segundos» (MODO_6VS6.md §11). REPRODUCIDO con el panel (2 humanos + 10 NPC, sala de 12 con
 *   ítem): los dos juegos cayeron juntos en el paso 434 —
 *       access-violation en 0x52E058 leyendo 0xAA75BAB2  ← ★ el MAGIC de esa carrera
 *       pila 0x4F54FD ← 0x504716 ← 0x5084E2 ← 0x50C52A ← 0x4EAFAF ← 0x4F7893 ← 0x498625
 *
 *   cGame tiene `std::vector<u32> dados[6]` en +0xB08 (de a 0x18: lo arma 0x4F9AD2, lo destruye 0x4F88E8, lo vacía al
 *   terminar el bucle de 6 de 0x4F2C07). Tres funciones SACAN el último dado del asiento y, si la cola está vacía,
 *   usan `rand()` (0x750598, el de la CRT) — el resultado va a `dado % cuántos` para sortear el ítem:
 *       A · 0x4ED850  (función entera, asiento = byte [esp+4])
 *       B · 0x4F54C3  (asiento = byte [esp+0xD0]) → vacía: 0x4F54F1
 *       C · 0x4F6F4C  (asiento = [esp+0x30])      → vacía: 0x4F6F71
 *   Con el asiento 6..11, `cGame + 0xB08 + asiento*0x18` cae en OTROS campos de cGame (ya lo había avisado
 *   ITEMS_SORTEO.md §2): su «tamaño» sale distinto de 0 y desreferencia basura (el magic) → caída.
 *
 *   ⇒ para el asiento ≥ 6, la cola se trata como VACÍA: el camino de fábrica del rand(). Con 6 o menos no cambia nada
 *     (nunca hay asiento ≥ 6). Las tres van por cueva y con guarda (los bytes de fábrica, si no: no se toca nada).
 *   [dados12] activo=0 lo apaga.
 */

/* Pone una cueva: copia `cuerpo` (n bytes), completa sus rel32 (pares en/destino VA del exe) y, si el sitio tiene
 * los bytes de fábrica, lo reemplaza por `jmp cueva` + NOP hasta `largo`. Devuelve 1 si quedó puesta. */
static int dados12_poner(DWORD va, const BYTE *espera, int largo, const BYTE *cuerpo, int n,
                         const int *en, const DWORD *destino, int nrel, const char *que)
{
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    BYTE *sitio = base + (va - 0x400000);
    if (memcmp(sitio, espera, largo) != 0) {
        apuntar("  [dados12] ⛔ %s (0x%06X) no es el de fábrica: no se toca", que, va);
        return 0;
    }
    BYTE *c = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!c) return 0;
    CopyMemory(c, cuerpo, n);
    for (int k = 0; k < nrel; k++)
        escribir_u32(c + en[k], (DWORD)((base + (destino[k] - 0x400000)) - (c + en[k] + 4)));
    BYTE salto[16];
    salto[0] = 0xE9;
    escribir_u32(salto + 1, (DWORD)(c - (sitio + 5)));
    for (int k = 5; k < largo; k++) salto[k] = 0x90;
    DWORD viejo = 0;
    if (!VirtualProtect(sitio, largo, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(sitio, salto, largo);
    VirtualProtect(sitio, largo, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), sitio, largo);
    return 1;
}

static void dados12_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("dados12", "activo", 1, ini)) {
        apuntar("  [dados12] apagado ([dados12] activo=0)");
        return;
    }
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    DWORD juego = (DWORD)(base + (0x9314C8 - 0x400000));
    int ok = 0;

    /* A · 0x4ED850 (5 B): movzx eax,byte [esp+4] · cmp eax,6 · jb +8 · call rand · ret 4 · jmp 0x4ED855 */
    {
        static const BYTE esp_[5] = { 0x0F, 0xB6, 0x44, 0x24, 0x04 };
        BYTE c[24] = { 0x0F, 0xB6, 0x44, 0x24, 0x04,  0x83, 0xF8, 0x06,  0x72, 0x08,
                       0xE8, 0, 0, 0, 0,  0xC2, 0x04, 0x00,  0xE9, 0, 0, 0, 0 };
        static const int en[2] = { 11, 19 };
        static const DWORD dst[2] = { 0x750598, 0x4ED855 };
        ok += dados12_poner(0x4ED850, esp_, 5, c, 23, en, dst, 2, "A");
    }
    /* B · 0x4F54C3 (14 B): movzx eax,byte [esp+0xD0] · cmp eax,6 · jb +5 · jmp 0x4F54F1 (vacía)
     *                      · mov ecx,[cGame*] · jmp 0x4F54D1 */
    {
        static const BYTE esp_[14] = { 0x0F, 0xB6, 0x84, 0x24, 0xD0, 0x00, 0x00, 0x00, 0x8B, 0x0D, 0xC8, 0x14, 0x93, 0x00 };
        BYTE c[32] = { 0x0F, 0xB6, 0x84, 0x24, 0xD0, 0x00, 0x00, 0x00,  0x83, 0xF8, 0x06,  0x72, 0x05,
                       0xE9, 0, 0, 0, 0,  0x8B, 0x0D, 0, 0, 0, 0,  0xE9, 0, 0, 0, 0 };
        escribir_u32(c + 20, juego);
        static const int en[2] = { 14, 25 };
        static const DWORD dst[2] = { 0x4F54F1, 0x4F54D1 };
        ok += dados12_poner(0x4F54C3, esp_, 14, c, 29, en, dst, 2, "B");
    }
    /* C · 0x4F6F4C (9 B): mov edi,[esp+0x30] · cmp edi,6 · jb +5 · jmp 0x4F6F71 (vacía) · mov eax,[cGame*] · jmp 0x4F6F55 */
    {
        static const BYTE esp_[9] = { 0x8B, 0x7C, 0x24, 0x30, 0xA1, 0xC8, 0x14, 0x93, 0x00 };
        BYTE c[32] = { 0x8B, 0x7C, 0x24, 0x30,  0x83, 0xFF, 0x06,  0x72, 0x05,
                       0xE9, 0, 0, 0, 0,  0xA1, 0, 0, 0, 0,  0xE9, 0, 0, 0, 0 };
        escribir_u32(c + 15, juego);
        static const int en[2] = { 10, 20 };
        static const DWORD dst[2] = { 0x4F6F71, 0x4F6F55 };
        ok += dados12_poner(0x4F6F4C, esp_, 9, c, 24, en, dst, 2, "C");
    }
    apuntar("  [dados12] %s la cola de dados de las cajas, asientos 6..11 → rand() de fábrica (%d de 3 sitios)",
            ok == 3 ? "★ puesta:" : "⚠ a medias:", ok);
}
