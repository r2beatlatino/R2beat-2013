/* cuadros_nulos.c — (100) la tabla de cuadros de un dibujo que todavía no cargó: la protección que le faltaba a la
 *                    hermana de 0x6840D0 (la caja negra 0x684107, 22-oct-2026, CAJAS_NEGRAS_2026-10-22.md §2.5)
 *
 * ★ POR QUÉ: 34 cajas negras en prod (17→22-oct), «lee 0x6C» en 0x684107 con ecx = 0. Casi todas: el jugador ENTRA a
 *   una sala y en 1-20 s el anfitrión cambia la canción ⇒ FF1C (0x5CDD40) ⇒ 0x5BEAC0 busca el botón
 *   «Button_play_sequence» del panel de música y le pone los cuadros 13/14/15 (0x688940 → 0x6852C0), que pide dos datos
 *   del cuadro a la tabla del dibujo: 0x6840D0 y 0x6840F0. Si el dibujo todavía no cargó, [dibujo+0x40] = 0.
 *   La primera (0x6840D0) YA tiene la protección en el exe de prod desde el 16-sep (`jecxz` en 0x6840E7 → la salida
 *   «fuera de rango» que el juego ya tenía, DEPLOY_2026-09-16_CAMPANAS.md §3); la segunda NO ⇒ se cae en 0x684107.
 *
 *       0x6840F0  mov eax,[esp+4] · cmp [ecx+0xA0],eax · ja 0x684104
 *       0x6840FC  mov eax,1 · ret 4                       ← la salida «fuera de rango» de fábrica
 *       0x684104  mov ecx,[ecx+0x40]
 *       0x684107  mov eax,[ecx+eax*8+4] · ret 4 · int3 int3   (8B 44 C1 04  C2 04 00  CC CC)
 *   ⇒ en 0x684107 va  jecxz 0x6840FC  (E3 F3) y se corre el resto 2 bytes, sobre el relleno: igual que el 16-sep.
 *   [cuadros_nulos] activo=0 lo apaga. (El server además ya no le manda el FF1C al que carga la sala, (100).)
 *
 * ★ (101) la caja negra 0x6840E9 (26 en prod, 17→22-oct, §2.6): la MISMA lectura, pero con la tabla NO nula sino BASURA
 *   ([dibujo+0x40] = 0x42200000, 0x41000000, 0x42B40000… son floats: el dibujo ya fue LIBERADO y su memoria la usa otro
 *   objeto). Casi siempre el FFC9 del cambio de canal: 0x5D8490 → 0x58E4D0 → 0x5BFA30 (el «Reset» del panel de búsqueda
 *   de canciones, [0x9314EC]) → 0x688940 sobre «Button_View» → 0x6852C0 → 0x6840D0; y 5 por otro camino del mismo
 *   panel (0x5BA096). Un `jecxz` no la ve (no es cero), y mirar si la memoria se puede leer en CADA llamada cuesta en
 *   todos los cuadros. ⇒ un atrapador de excepciones (VEH, primero en la fila) que sólo actúa si el fallo es EXACTAMENTE
 *   en una de estas dos lecturas: contesta lo que contesta el juego para un cuadro fuera de rango (eax = 1) y vuelve
 *   (`ret 4`). En el camino normal no cuesta nada: sin excepción no corre.
 *   ⚠ El dibujo sigue liberado: si el juego lo DIBUJA después, se caerá en otro lado — se mide en las cajas negras. Quién
 *     lo libera no se encontró: en la máquina rápida el cambio de canal no lo libera (sonda, 22-oct).
 *   [cuadros_nulos] liberados=0 lo apaga. */

static DWORD g_cn_lecturas[2];                        /* las dos `mov eax,[ecx+eax*8(+4)]` que pueden fallar */
static int   g_cn_salvados = 0;

static LONG WINAPI cuadros_liberados(EXCEPTION_POINTERS *e)
{
    if (e->ExceptionRecord->ExceptionCode != 0xC0000005) return EXCEPTION_CONTINUE_SEARCH;
    DWORD eip = e->ContextRecord->Eip;
    if (eip != g_cn_lecturas[0] && eip != g_cn_lecturas[1]) return EXCEPTION_CONTINUE_SEARCH;
    DWORD *pila = (DWORD *)e->ContextRecord->Esp;
    if (g_cn_salvados++ < 5)
        apuntar("  [cuadros_nulos] ★ (101) la tabla de cuadros de un dibujo LIBERADO (tabla 0x%08X, cuadro %u,"
                " vuelve a 0x%08X): «fuera de rango» y se sigue (sin esto: la caja negra 0x%06X)",
                (DWORD)e->ContextRecord->Ecx, (DWORD)e->ContextRecord->Eax, pila[0],
                eip - (DWORD)GetModuleHandleA(NULL) + 0x400000);
    e->ContextRecord->Eax = 1;                        /* lo de 0x6840DC / 0x6840FC: cuadro fuera de rango */
    e->ContextRecord->Eip = pila[0];                  /* ret 4 */
    e->ContextRecord->Esp += 8;
    return EXCEPTION_CONTINUE_EXECUTION;
}

static int cn_igual(const BYTE *a, const BYTE *b, int n)
{
    for (int i = 0; i < n; i++) if (a[i] != b[i]) return 0;
    return 1;
}

static void cuadros_liberados_iniciar(const char *ini)
{
    if (!GetPrivateProfileIntA("cuadros_nulos", "liberados", 1, ini)) {
        apuntar("  [cuadros_nulos] (101) APAGADO ([cuadros_nulos] liberados=0)");
        return;
    }
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    /* 0x6840D0: con la guardia del 16-sep (exe de prod) la lectura está en 0x6840E9; sin ella, en 0x6840E7 */
    static const BYTE con_guardia[7] = { 0xE3, 0xF3, 0x8B, 0x04, 0xC1, 0xC2, 0x04 };
    static const BYTE de_fabrica[5]  = { 0x8B, 0x04, 0xC1, 0xC2, 0x04 };
    /* 0x6840F0: con (100) la lectura se corrió a 0x684109; sin (100), en 0x684107 */
    static const BYTE con_100[6]     = { 0xE3, 0xF3, 0x8B, 0x44, 0xC1, 0x04 };
    static const BYTE sin_100[4]     = { 0x8B, 0x44, 0xC1, 0x04 };
    BYTE *a = base + (0x6840E7 - 0x400000), *b = base + (0x684107 - 0x400000);
    g_cn_lecturas[0] = cn_igual(a, con_guardia, 7) ? (DWORD)a + 2 : (cn_igual(a, de_fabrica, 5) ? (DWORD)a : 0);
    g_cn_lecturas[1] = cn_igual(b, con_100, 6) ? (DWORD)b + 2 : (cn_igual(b, sin_100, 4) ? (DWORD)b : 0);
    if (!g_cn_lecturas[0] && !g_cn_lecturas[1]) {
        apuntar("  [cuadros_nulos] (101) ⚠ ni 0x6840E7 ni 0x684107 tienen lo esperado: no se instala");
        return;
    }
    if (AddVectoredExceptionHandler(1, cuadros_liberados))
        apuntar("  [cuadros_nulos] ★ (101) un dibujo LIBERADO ya no cierra el juego (lecturas en 0x%06X y 0x%06X)",
                g_cn_lecturas[0] ? g_cn_lecturas[0] - (DWORD)base + 0x400000 : 0,
                g_cn_lecturas[1] ? g_cn_lecturas[1] - (DWORD)base + 0x400000 : 0);
}

static void cuadros_nulos_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("cuadros_nulos", "activo", 1, ini)) {
        apuntar("  [cuadros_nulos] APAGADO ([cuadros_nulos] activo=0)");
        cuadros_liberados_iniciar(ini);
        return;
    }
    static const BYTE esperado[9] = { 0x8B, 0x44, 0xC1, 0x04, 0xC2, 0x04, 0x00, 0xCC, 0xCC };
    static const BYTE nuevo[9]    = { 0xE3, 0xF3, 0x8B, 0x44, 0xC1, 0x04, 0xC2, 0x04, 0x00 };
    if (escribir_bytes(0x684107, esperado, nuevo, 9, "cuadros_nulos: 0x6840F0 sin tabla de cuadros"))
        apuntar("  [cuadros_nulos] ★ 0x6840F0 con la protección de su hermana: un dibujo sin cargar ya no cierra el juego");
    cuadros_liberados_iniciar(ini);                   /* después del parche: mira dónde quedó la lectura */
}
