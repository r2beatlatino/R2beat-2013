/* obstaculos.c — los OBSTÁCULOS de una pista, aparte de la pista (08-oct-2026)
 *
 *   anonimo03, mirando el cliente coreano de hoy (que tiene «맵» y «장애물» por separado): poder correr en una
 *   pista con los obstáculos de OTRA. Investigación: documentacion/PISTA_OBSTACULOS_VICTORIA.md.
 *
 *   En el 2013 la pista y sus obstáculos ya son DOS archivos distintos, y los carga una sola función:
 *
 *     0x4E8D50(pista)   la llama la carga de la carrera (0x4FAA2A) con la pista del FF25
 *                       (`[+0x8B0] xor [0x904210]`, la clave de la carrera)
 *       0x4E7220        el fondo: la entrada de `rnr_script/stage_lt.txt` (Model, Sky, Fog, Finish...)
 *       0x4E8DFD        sprintf(buf, "rnr_script/stage/back%03d.txt", pista)   <- los OBSTÁCULOS (<Block>)
 *
 *   ⇒ Desviando ese sprintf, la pista queda y los obstáculos salen de otro `backNNN.txt`. Todos traen los
 *     mismos tipos de bloque (UP_S, LEFT_L1, FLY...; algunos sin LEFTRIGHT/UPDOWN, como ya pasa con sus
 *     propias pistas) y los modelos van con ruta completa (`back11/object/...`), que se leen de cualquier pak.
 *
 *   ✅ ETAPA 1 (anonimo03, 08-oct: «se veía bien»): pista 99 con los obstáculos de la 4, carrera entera.
 *
 *   ★ ETAPA 2 — LOS MANDA EL SERVER, POR JUGADOR: el campo 2 del FF25 (`obstaculos` u16, ver
 *     documentacion/FF25_LOADGAME_BYTES.md), pegado después de la `pd_valofe`. Lo lee el MISMO camino que
 *     la pd: el cave `perilla` del exe (0x7E6330, lo pone aplicar_parches.py) pide su byte del flujo y
 *     vuelve al handler con `mov eax,[esp+0x18] · mov ecx,[0x9314E4] · jmp 0x5EAA4B` (cave+0x1C). Esas dos
 *     instrucciones se cambian por un salto a un trocito nuestro que pide 2 bytes MÁS y hace lo mismo.
 *     ⚠ Pone el destino en 0 ANTES de pedirlo: con un server viejo el lector no lo toca y queda 0 = los
 *       de la pista (la regla del registro: la ausencia es «apagado»).
 *   `[obstaculos] forzar=N` queda como perilla de prueba: si está, gana al server.
 */
#define OBV(x) (g_ob_base + ((DWORD)(x) - 0x400000))

static BYTE *g_ob_base = NULL;
static int   g_ob_forzar = 0;            /* [obstaculos] forzar=N: los obstáculos de la pista N */
static WORD  g_ob_srv = 0;               /* los que mandó el server en el FF25 de ESTA carrera (0 = ninguno) */
/* ★ la PRÁCTICA no pasa por el server (FF3A, sin FF25): lo que eligió ahí lo anota panel_sala.c acá.
 *   0xFFFF = los de la pista · 0 = aleatorios · N */
static WORD  g_ob_practica = 0xFFFF;
static BYTE *g_ob_salto = NULL;

/* las pistas que traen `rnr_script/stage/backNNN.txt` en el cliente (rnr_script.pak, 08-oct) */
static const WORD OB_CON_OBSTACULOS[] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20, 21,
                                          22, 25, 58, 63, 66, 94, 99, 100, 101, 102, 103 };

/* ★ 11-nov — los «ALEATORIOS» de la PRÁCTICA salen de las mismas 22 que el server (`ajustes.OBSTACULOS_DEL_SORTEO`,
 *   (167)): las 9 restantes (13, 17, 18, 20, 25, 100..103) traen backNNN.txt pero no son ninguna pista que se corra.
 *   El arreglo del 09-nov quedó sólo en el server; la práctica no pasa por él y seguía sorteando entre las 31. */
static const WORD OB_DEL_SORTEO[] = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 19, 21, 22, 58, 63, 66, 94, 99 };

static int ob_existe(int n)
{
    for (int i = 0; i < (int)(sizeof(OB_CON_OBSTACULOS) / sizeof(OB_CON_OBSTACULOS[0])); i++)
        if (OB_CON_OBSTACULOS[i] == n) return 1;
    return 0;
}

typedef int (__cdecl *F_OB_SPRINTF)(char *buf, const char *fmt, ...);

/* 0x4E8DFD: sprintf(buf, "rnr_script/stage/back%03d.txt", pista) */
static int __cdecl ob_sprintf(char *buf, const char *fmt, int pista)
{
    int usar = pista;
    const char *de = "";
    BYTE *sala = *(BYTE **)OBV(0x9314C0);
    int practica = sala && *(DWORD *)(sala + 0x9574) == 0x1FEE && *(DWORD *)(sala + 0x9580) == 0x1FEF;  /* pista_propia.c */
    if (g_ob_forzar && ob_existe(g_ob_forzar)) { usar = g_ob_forzar; de = " (forzar del ini)"; }
    else if (practica) {
        int n = g_ob_practica;
        if (n == 0) n = OB_DEL_SORTEO[GetTickCount() % (sizeof(OB_DEL_SORTEO) / sizeof(OB_DEL_SORTEO[0]))];
        if (n != 0xFFFF && ob_existe(n)) { usar = n; de = g_ob_practica ? " (práctica: los que eligió)" : " (práctica: aleatorios)"; }
        else de = " (práctica)";
    }
    else if (g_ob_srv && ob_existe(g_ob_srv)) { usar = g_ob_srv; de = " (los eligió en la sala)"; }
    apuntar("  [obstaculos] carrera en la pista %d con los obstáculos de la %d%s%s", pista, usar,
            usar == pista ? "" : "  ★", de);
    if (!practica && g_ob_srv && !ob_existe(g_ob_srv))
        apuntar("  [obstaculos] ⚠ el server mandó la %d, que no trae backNNN.txt: van los de la pista", g_ob_srv);
    return ((F_OB_SPRINTF)OBV(0x74F4BA))(buf, fmt, usar);
}

/* el campo 2 del FF25: después de la `pd_valofe` que lee el cave del exe, 2 bytes más */
static void ob_enganchar_ff25(void)
{
    /* el cave `perilla` de aplicar_parches.py, tal cual (43 B en 0x7E6330) */
    static const BYTE PERILLA[43] = {
        0xC6, 0x05, 0x40, 0x6B, 0xA1, 0x00, 0x00, 0x60, 0x6A, 0x01, 0x68, 0x40, 0x6B, 0xA1, 0x00, 0x8B, 0x8C, 0x24,
        0x64, 0x00, 0x00, 0x00, 0xE8, 0xB5, 0x6E, 0xE9, 0xFF, 0x61, 0x8B, 0x44, 0x24, 0x18, 0x8B, 0x0D, 0xE4, 0x14,
        0x93, 0x00, 0xE9, 0xF0, 0x46, 0xE0, 0xFF };
    if (memcmp(OBV(0x7E6330), PERILLA, 43) != 0) {
        apuntar("  [obstaculos] ⚠ el exe no trae el cave de la PD Valofe (0x7E6330): los obstáculos del server no se leen"
                " (sigue andando el resto)");
        return;
    }
    g_ob_salto = (BYTE *)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_ob_salto) { apuntar("  [obstaculos] ⛔ sin memoria para el salto del FF25"); return; }
    BYTE *k = g_ob_salto;
    int i = 0;
    k[i++] = 0x66; k[i++] = 0xC7; k[i++] = 0x05; *(DWORD *)(k + i) = (DWORD)&g_ob_srv; i += 4;   /* mov word [g_ob_srv],0 */
    k[i++] = 0x00; k[i++] = 0x00;
    k[i++] = 0xC6; k[i++] = 0x05; *(DWORD *)(k + i) = (DWORD)&g_gr_n; i += 4; k[i++] = 0x00;      /* mov byte [g_gr_n],0 */
    k[i++] = 0x60;                                                                                /* pushad */
    k[i++] = 0x6A; k[i++] = 0x02;                                                                 /* push 2 */
    k[i++] = 0x68; *(DWORD *)(k + i) = (DWORD)&g_ob_srv; i += 4;                                 /* push &g_ob_srv */
    k[i++] = 0x8B; k[i++] = 0x8C; k[i++] = 0x24; *(DWORD *)(k + i) = 0x64; i += 4;               /* mov ecx,[esp+0x64] */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)OBV(0x67D200) - (DWORD)(k + i + 5)); i += 5; /* call el lector */
    /* ★ el campo 3 (`corredores` u8, grande.c), a continuación: la carrera grande del 6vs6 (10-oct) */
    k[i++] = 0x6A; k[i++] = 0x01;                                                                 /* push 1 */
    k[i++] = 0x68; *(DWORD *)(k + i) = (DWORD)&g_gr_n; i += 4;                                   /* push &g_gr_n */
    k[i++] = 0x8B; k[i++] = 0x8C; k[i++] = 0x24; *(DWORD *)(k + i) = 0x64; i += 4;               /* mov ecx,[esp+0x64] */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)OBV(0x67D200) - (DWORD)(k + i + 5)); i += 5; /* call el lector */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)grande_tras_ff25 - (DWORD)(k + i + 5)); i += 5; /* call grande */
    k[i++] = 0x61;                                                                                /* popad */
    k[i++] = 0x8B; k[i++] = 0x44; k[i++] = 0x24; k[i++] = 0x18;                                   /* mov eax,[esp+0x18] */
    k[i++] = 0x8B; k[i++] = 0x0D; *(DWORD *)(k + i) = 0x9314E4 - 0x400000 + (DWORD)g_ob_base; i += 4; /* mov ecx,[0x9314E4] */
    k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)OBV(0x5EAA4B) - (DWORD)(k + i + 5)); i += 5; /* jmp 0x5EAA4B */
    BYTE n[10] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90 };
    *(int *)(n + 1) = (int)((DWORD)g_ob_salto - ((DWORD)OBV(0x7E634C) + 5));
    DWORD viejo = 0;
    if (!VirtualProtect(OBV(0x7E634C), 10, PAGE_EXECUTE_READWRITE, &viejo)) { apuntar("  [obstaculos] ⛔ VirtualProtect (FF25)"); return; }
    CopyMemory(OBV(0x7E634C), n, 10);
    VirtualProtect(OBV(0x7E634C), 10, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), OBV(0x7E634C), 10);
    apuntar("  [obstaculos] el FF25 trae los obstáculos de cada jugador: enganchado después de la PD (0x7E634C)");
}

static void obstaculos_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("obstaculos", "activo", 1, ini)) {
        apuntar("  [obstaculos] apagado ([obstaculos] activo=0)");
        return;
    }
    g_ob_base = (BYTE *)GetModuleHandleA(NULL);
    g_ob_forzar = GetPrivateProfileIntA("obstaculos", "forzar", 0, ini);
    /* la guarda: el texto del formato, el `push 0x87AF38` y la llamada al sprintf de siempre */
    static const char FMT[] = "rnr_script/stage/back%03d.txt";
    static const BYTE e_push[5] = { 0x68, 0x38, 0xAF, 0x87, 0x00 };
    BYTE e_call[5] = { 0xE8 };
    *(int *)(e_call + 1) = (int)((DWORD)OBV(0x74F4BA) - ((DWORD)OBV(0x4E8DFD) + 5));
    if (lstrcmpA((const char *)OBV(0x87AF38), FMT) != 0 || memcmp(OBV(0x4E8DF7), e_push, 5) != 0 ||
        memcmp(OBV(0x4E8DFD), e_call, 5) != 0) {
        apuntar("  [obstaculos] ⛔ la carga de los obstáculos (0x4E8DFD) no es la esperada: no se toca nada");
        return;
    }
    BYTE n_call[5] = { 0xE8 };
    *(int *)(n_call + 1) = (int)((DWORD)ob_sprintf - ((DWORD)OBV(0x4E8DFD) + 5));
    DWORD viejo = 0;
    if (!VirtualProtect(OBV(0x4E8DFD), 5, PAGE_EXECUTE_READWRITE, &viejo)) {
        apuntar("  [obstaculos] ⛔ VirtualProtect falló");
        return;
    }
    CopyMemory(OBV(0x4E8DFD), n_call, 5);
    VirtualProtect(OBV(0x4E8DFD), 5, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), OBV(0x4E8DFD), 5);
    ob_enganchar_ff25();
    apuntar("  [obstaculos] ok: enganchada la carga (0x4E8DFD) · forzar=%d%s", g_ob_forzar,
            g_ob_forzar && !ob_existe(g_ob_forzar) ? "  ⚠ esa pista NO tiene backNNN.txt: se ignora" : "");
}
