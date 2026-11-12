/* cajanegra.c — la CAJA NEGRA: anota desde DÓNDE se cierra el juego cuando se cierra solo (12-oct-2026).
 *
 * El cliente tiene 12.501 comprobaciones de rango (los `std::vector` con iteradores comprobados del MSVC): si un
 * índice se pasa, llaman a `_invalid_parameter_noinfo` (0x0074FF1F) -> 0x74FEF9 -> TerminateProcess. **No hay
 * excepción ni volcado**: el jugador ve que el juego desaparece y el server ve que la conexión se muere. Es lo que le
 * pasa al ESPECTADOR al arrancar una carrera de RELEVOS (prod 10/11-oct: 11 de 18 arranques, contra 12 de 216 en el
 * resto; [GM]jugador52 se cayó 12 veces en el torneo). Ver documentacion/MODO_ESPECTADOR.md §8.
 *
 * El enganche: los 5 bytes de la entrada (`xor eax,eax · push eax ×3`) saltan a una cueva que guarda los registros,
 * llama a `cn_anotar(pila)` y vuelve a hacer lo mismo que hacía (el juego se cierra igual: esto sólo MIRA).
 * `cn_anotar` escribe en d3d9_proxy.log el llamador y las direcciones de código que haya en la pila (la cadena de
 * llamadas aproximada), más mi asiento. [cajanegra] activo=0 en d3d9_proxy.ini lo apaga.
 * Se INCLUYE desde d3d9_proxy.c (después de `escribir_bytes`).
 */

#define CN_SITIO   0x0074FF1F
#define CN_VUELTA  0x0074FF24
static BYTE *g_cn_base;
static int g_cn_veces;

static DWORD cn_va(DWORD a) { return a - (DWORD)g_cn_base + 0x400000; }
static int cn_es_codigo(DWORD a) { DWORD v = cn_va(a); return v >= 0x401000 && v < 0x872800; }

static void __cdecl cn_anotar(DWORD *pila)
{
    if (++g_cn_veces > 3) return;
    DWORD llamador = pila[0] - 5;
    apuntar("⛔⛔ [cajanegra] EL JUEGO SE CIERRA (_invalid_parameter: un índice fuera de rango) — llamado desde 0x%08X",
            cn_va(llamador));
    char linea[400];
    int n = 0, k = 0;
    linea[0] = 0;
    for (int i = 1; i < 160 && k < 14; i++) {
        DWORD v = pila[i];
        if (cn_es_codigo(v)) {
            n += wsprintfA(linea + n, "%08X ", cn_va(v));
            k++;
        }
    }
    apuntar("   [cajanegra] direcciones de código en la pila (de la más cercana a la más lejana): %s", linea);
    BYTE *yo = *(BYTE **)(g_cn_base + (0x00931660 - 0x400000));
    if (yo) apuntar("   [cajanegra] mi asiento ([0x931660]+0x40) = %d", (int)yo[0x40]);
}

/* ═══ ★ 16-oct · LA CAJA NEGRA LLEGA AL SERVER (anonimo03: «todos los de la sala crashearon uno por uno») ════════════════
 *   En prod hubo 8 olas de caídas en salas de 12 y no había cómo saber DÓNDE: la caja negra lo anotaba en el log, y el
 *   log se PISABA al reabrir el juego. Tres piezas, todas de sólo mirar (el juego se cae igual):
 *     1 · las EXCEPCIONES graves (acceso inválido, instrucción ilegal, pila llena, división por 0) con su pila — un
 *         manejador vectorizado: las ve aunque pasen dentro de un callback de ventana (0xC000041D). Tope 3 por arranque;
 *         puede anotar alguna que el juego manejaba (dice «primera oportunidad»).
 *     2 · el log anterior NO se pisa: pasa a `d3d9_proxy.anterior.log` (empezar_log → cn_leer_anterior).
 *     3 · al volver a entrar, ya en el LOBBY (la red [0x9314D0] con su bandera +0x21B54 & 2, y el usn puesto), se le
 *         manda al server lo que la caja negra anotó la vez anterior, por el reporte de errores del propio juego
 *         (0x404440(texto) = el FF59 «USN:… TIME:… SERVER:…» + el texto, que el server ya escribe en su log). ⚠ Arma
 *         todo en 512 B SIN control: cada texto va recortado a CN_LARGO. Sólo ASCII (lo demás pasa a '_').
 *   [cajanegra] reportar=0 apaga el envío.
 *   ✅ 17-oct, probado en el server QA con un cliente: un acceso inválido forzado en el hilo del juego (Frida:
 *     PeekMessage → `mov eax,[0]`) quedó anotado con registros y pila, y al reabrir llegó al server en 3 FF59 a los
 *     15 s del lobby («CAJANEGRA de la vez anterior:» + la excepción + la pila). ⛔ La 1.ª versión lo mandaba desde los
 *     Present, que sólo se enganchan con el cartel de fps o el 9Ex ⇒ NO salía nunca; ahora va desde el Sleep del bucle. */
#define CN_LARGO 240
static char g_cn_pend[5][CN_LARGO + 1];
static int g_cn_npend, g_cn_enviados, g_cn_exc;
static DWORD g_cn_t0;

/* sin depender de la librería de C (ningún otro módulo la usa) */
static char *cn_busca(char *s, const char *sub)
{
    int m = lstrlenA(sub);
    for (; *s; s++) { int i = 0; while (i < m && s[i] == sub[i]) i++; if (i == m) return s; }
    return NULL;
}
static int cn_empieza(const char *s, const char *pre) { while (*pre) if (*s++ != *pre++) return 0; return 1; }

static DWORD cn_va_o_crudo(DWORD a)
{
    if (!g_cn_base) g_cn_base = (BYTE *)GetModuleHandleA(NULL);
    return cn_es_codigo(a) ? cn_va(a) : a;
}

static LONG WINAPI cn_excepcion(EXCEPTION_POINTERS *e)
{
    DWORD cod = e->ExceptionRecord->ExceptionCode;
    if (cod != 0xC0000005 && cod != 0xC000001D && cod != 0xC00000FD && cod != 0xC0000094 && cod != 0xC0000096)
        return EXCEPTION_CONTINUE_SEARCH;
    if (++g_cn_exc > 3) return EXCEPTION_CONTINUE_SEARCH;
    DWORD donde = (DWORD)e->ExceptionRecord->ExceptionAddress, que = 0, dir = 0;
    if (cod == 0xC0000005 && e->ExceptionRecord->NumberParameters >= 2) {
        que = (DWORD)e->ExceptionRecord->ExceptionInformation[0];
        dir = (DWORD)e->ExceptionRecord->ExceptionInformation[1];
    }
    apuntar("⛔⛔ [cajanegra] EXCEPCION 0x%08X en 0x%08X (%s 0x%08X) · primera oportunidad · eax=%08X ecx=%08X edx=%08X"
            " esi=%08X edi=%08X", cod, cn_va_o_crudo(donde), que == 1 ? "escribe" : (que == 8 ? "ejecuta" : "lee"), dir,
            e->ContextRecord->Eax, e->ContextRecord->Ecx, e->ContextRecord->Edx, e->ContextRecord->Esi,
            e->ContextRecord->Edi);
    char linea[400];
    int n = 0, k = 0;
    linea[0] = 0;
    DWORD *p = (DWORD *)e->ContextRecord->Esp;
    DWORD *tope = (DWORD *)((NT_TIB *)NtCurrentTeb())->StackBase;
    for (int i = 0; i < 200 && p + i < tope && k < 14; i++)
        if (cn_es_codigo(p[i])) { n += wsprintfA(linea + n, "%08X ", cn_va(p[i])); k++; }
    apuntar("   [cajanegra] direcciones de código en la pila (de la más cercana a la más lejana): %s", linea);
    return EXCEPTION_CONTINUE_SEARCH;
}

/* (llamada desde empezar_log, ANTES de pisar el log) lo que la caja negra anotó la vez anterior → g_cn_pend, y el log
 *   anterior pasa a d3d9_proxy.anterior.log */
static void cn_leer_anterior(const char *ruta)
{
    HANDLE h = CreateFileA(ruta, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        static char buf[65536];
        DWORD tam = GetFileSize(h, NULL), leidos = 0;
        if (tam != INVALID_FILE_SIZE && tam > sizeof(buf) - 1) SetFilePointer(h, (LONG)(tam - (sizeof(buf) - 1)), NULL, FILE_BEGIN);
        ReadFile(h, buf, sizeof(buf) - 1, &leidos, NULL);
        CloseHandle(h);
        buf[leidos] = 0;
        /* la ÚLTIMA vez que la caja negra anotó algo: desde su «⛔⛔ [cajanegra]» hasta 2 renglones «   [cajanegra]» */
        char *ult = NULL;
        for (char *s = buf; (s = cn_busca(s, "[cajanegra] E")) != NULL; s++) {
            char *ini = s;
            while (ini > buf && ini[-1] != '\n') ini--;
            if (cn_empieza(s + 12, "EL JUEGO SE CIERRA") || cn_empieza(s + 12, "EXCEPCION")) ult = ini;
        }
        if (ult) {
            g_cn_npend = 0;
            lstrcpynA(g_cn_pend[g_cn_npend++], "CAJANEGRA de la vez anterior:", CN_LARGO);
            char *s = ult;
            for (int i = 0; i < 3 && *s && g_cn_npend < 5; i++) {
                char *fin = s;
                while (*fin && *fin != '\n') fin++;
                int largo = (int)(fin - s);
                if (!*fin) fin = NULL;
                if (i > 0 && !cn_empieza(s, "   [cajanegra]")) break;
                char *d = g_cn_pend[g_cn_npend++];
                int k = 0;
                for (int j = 0; j < largo && k < CN_LARGO; j++) {
                    unsigned char ch = (unsigned char)s[j];
                    if (ch == '\r') continue;
                    d[k++] = (ch >= 32 && ch < 127) ? (char)ch : '_';
                }
                d[k] = 0;
                if (!fin) break;
                s = fin + 1;
            }
        }
    }
    char ant[MAX_PATH];
    lstrcpyA(ant, g_carpeta);
    lstrcatA(ant, "d3d9_proxy.anterior.log");
    MoveFileExA(ruta, ant, MOVEFILE_REPLACE_EXISTING);
}

/* (desde el Sleep del bucle —mi_sleep— y los dos Present: el hilo del juego) si hay algo de la vez anterior y ya estoy
 *   en el lobby, se manda de a un renglón por vuelta */
static DWORD g_cn_cap_usn;                /* a qué usn ya le dije qué trae esta dll */
static void cn_enviar_pendiente(void)
{
    if (g_cn_enviados >= g_cn_npend && !g_gr_abandono && !g_cg_activo) return;
    if (!g_cn_base) g_cn_base = (BYTE *)GetModuleHandleA(NULL);
    if (!g_cn_t0) { g_cn_t0 = GetTickCount(); return; }
    BYTE *red = *(BYTE **)(g_cn_base + (0x009314D0 - 0x400000));
    BYTE *cuenta = *(BYTE **)(g_cn_base + (0x009314E0 - 0x400000));
    if (!red || !cuenta || (*(DWORD *)(red + 0x21B54) & 2) != 2 || !*(DWORD *)(cuenta + 0x7C)) return;
    /* ★ 17-oct: el server tiene que saber que esta dll saca de la pista al que abandona en la de 12 (grande.c,
     *   gr_abandono): a ése le manda el FF0E en el momento; al que no lo dice se lo sigue guardando (si no, se cae).
     *   Una vez por usn, en cuanto está en el lobby (no espera los 15 s: la carrera puede empezar antes). */
    DWORD usn = *(DWORD *)(cuenta + 0x7C);
    /* ★ 06-nov: (161) y que el chart del FF57 puede pasar de 4096 (chart_grande.c): a la que no lo dice, el server le
     *   manda el chart recortado al techo. Una sola línea con todo lo que trae («R2DLL abandono12=1 chart64k=1»). */
    if ((g_gr_abandono || g_cg_activo) && g_cn_cap_usn != usn) {
        char linea[96];
        g_cn_cap_usn = usn;
        lstrcpyA(linea, "R2DLL");
        if (g_gr_abandono) lstrcatA(linea, " abandono12=1");
        if (g_cg_activo) lstrcatA(linea, " chart64k=1");
        ((void (__cdecl *)(const char *))(g_cn_base + (0x00404440 - 0x400000)))(linea);
        apuntar("  [cajanegra] ★ le dije al server qué trae esta dll: «%s» (usn %lu)", linea, usn);
        return;
    }
    if (g_cn_enviados >= g_cn_npend) return;
    if (GetTickCount() - g_cn_t0 < 15000) return;                        /* que termine de entrar */
    ((void (__cdecl *)(const char *))(g_cn_base + (0x00404440 - 0x400000)))(g_cn_pend[g_cn_enviados]);
    if (++g_cn_enviados == g_cn_npend) apuntar("  [cajanegra] ★ mandé al server lo de la vez anterior (%d renglones)", g_cn_npend);
}

static void cajanegra_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("cajanegra", "activo", 1, ini)) {
        apuntar("  [cajanegra] apagada ([cajanegra] activo=0)");
        return;
    }
    g_cn_base = (BYTE *)GetModuleHandleA(NULL);
    if (!GetPrivateProfileIntA("cajanegra", "reportar", 1, ini)) g_cn_npend = 0;
    if (g_cn_npend) apuntar("  [cajanegra] la vez anterior anotó algo: %d renglones para mandar al server al llegar al lobby",
                            g_cn_npend - 1);
    if (AddVectoredExceptionHandler(0, cn_excepcion))
        apuntar("  [cajanegra] ★ también las excepciones graves (acceso inválido, etc.), con su pila");
    static const BYTE esp[5] = { 0x33, 0xC0, 0x50, 0x50, 0x50 };       /* xor eax,eax · push eax ×3 */
    BYTE *c = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!c) return;
    int i = 0;
    c[i++] = 0x60;                                                       /* pushad                    */
    c[i++] = 0x8D; c[i++] = 0x44; c[i++] = 0x24; c[i++] = 0x20;          /* lea eax,[esp+0x20] (pila) */
    c[i++] = 0x50;                                                       /* push eax                  */
    c[i] = 0xE8; *(int *)(c + i + 1) = (int)((DWORD)cn_anotar - (DWORD)(c + i + 5)); i += 5;   /* call  */
    c[i++] = 0x83; c[i++] = 0xC4; c[i++] = 0x04;                         /* add esp,4                 */
    c[i++] = 0x61;                                                       /* popad                     */
    for (int j = 0; j < 5; j++) c[i++] = esp[j];                         /* lo que pisamos            */
    c[i] = 0xE9; *(int *)(c + i + 1) = (int)((DWORD)(g_cn_base + (CN_VUELTA - 0x400000)) - (DWORD)(c + i + 5)); i += 5;
    BYTE nue[5];
    nue[0] = 0xE9;
    *(int *)(nue + 1) = (int)((DWORD)c - ((DWORD)(g_cn_base + (CN_SITIO - 0x400000)) + 5));
    if (escribir_bytes(CN_SITIO, esp, nue, 5, "caja negra"))
        apuntar("  [cajanegra] ★ puesta: si el juego se cierra por un índice fuera de rango, queda anotado desde dónde");
    else
        VirtualFree(c, 0, MEM_RELEASE);
}
