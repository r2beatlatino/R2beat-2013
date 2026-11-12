/* pista_propia.c — que el INVITADO también pueda elegir la pista (08-oct-2026, etapa 3)
 *
 *   anonimo03: *"si el invitado no elige la suya, la que ponga el anfitrión sigue mandando, hasta que el invitado
 *   elija"*. La pista de cada uno la guarda y la manda el server (salas.ELECCION_JUGADOR, el FF13 @14 y el
 *   mapa del FF25 de cada destinatario); acá sólo se le abre la puerta al invitado. Investigación:
 *   documentacion/PISTA_OBSTACULOS_VICTORIA.md §5.
 *
 *   El exe le cierra la ventana de pistas al que no es anfitrión en TRES lugares [D]:
 *
 *     0x586336  `jne` (75 31)            el clic en el recuadro «Pista» del panel: ¿mi slot == el del anfitrión?
 *     0x5883A7  `jne` (0F 85 06 02 ..)   el botón «Elija la Pista»: la misma pregunta (0x5272F0 = slot anfitrión)
 *     0x58D526  `je`  (74 18)            al CONFIRMAR (0x58D500): sólo el anfitrión manda el FF1B; el invitado
 *                                        sólo se lo anota en la ventana ([dlg+0x30])
 *
 *   ⇒ los dos primeros pasan a NOP (cualquiera abre la ventana). El tercero va a un salto nuestro (desde 0x58D520,
 *     8 bytes) que decide: en una SALA de carrera manda el FF1B (anfitrión o invitado); en la PRÁCTICA sigue el
 *     camino de siempre, local. ★ El `[cRoom+0x9574]` que pregunta 0x58D51B NO es «soy el anfitrión»: es el tipo
 *     de escena (documentacion/TIPOS_DE_SALA_Y_CANAL_2013.md §1.1): FF10/FF11 lo ponen en 0x1FEF (sala de carrera)
 *     y el botón de práctica (0x49EE4F) en 0x1FEE. O sea que en una sala el confirmar SIEMPRE mandó el FF1B, y la
 *     única que no lo manda es la práctica — ⛔ 1ª prueba de anonimo03 (08-oct): con el `jmp` fijo la práctica mandaba un FF1B,
 *     el server le contestaba con un FF13 de sala (con el modo «equipo» de la sala anterior) y la práctica ya no
 *     arrancaba. Si la ventana está en MODO OBSTÁCULOS (`g_modo_obst`, panel_sala.c) va SIEMPRE por el FF1B:
 *     ahí lo atrapa panel_sala.c, y en la práctica no lo manda (lo anota local).
 *     Los 8 llamadores de 0x58D500 están todos detrás de «la ventana está abierta» ([cRoom+0xA429]), que sólo
 *     pone el que la abrió (0x58F9B0): un invitado nunca manda un FF1B que no eligió él.
 *   ⚠ El server decide qué hace con el FF1B de un invitado (lobby_carrera.h_28_ff1b): lo anota como SU pista
 *     y le reemite el FF13 SÓLO a él. Un server viejo lo tomaría como cambio de la sala: van JUNTOS.
 *   ⛔ [pista_propia] activo=0 lo apaga (el invitado vuelve a no poder abrir la ventana).
 */
static BYTE *g_pp_base = NULL;
#define PPV(x) (g_pp_base + ((DWORD)(x) - 0x400000))
static volatile int g_modo_obst = 0;      /* 1 = la ventana de pistas está abierta para elegir OBSTÁCULOS (panel_sala.c) */
static BYTE *g_pp_cueva = NULL;

/* ¿la sala de ahora es la PRÁCTICA? [cRoom+0x9574] == 0x1FEE (el botón de práctica, 0x49EE4F; FF10/FF11 ponen 0x1FEF)
 *   y [cRoom+0x9580] == 0x1FEF (no es una sala de charla, que es la que lo cambia: 0x5EA7F1).
 *   ⛔ 3ª prueba (08-oct): con sólo +0x9580 una sala de carrera también «era práctica» y «Victoria» desaparecía. */
static int pp_es_practica(BYTE *sala)
{
    return sala && *(DWORD *)(sala + 0x9574) == 0x1FEE && *(DWORD *)(sala + 0x9580) == 0x1FEF;
}

typedef struct { DWORD va; BYTE esp[6]; BYTE nue[6]; int n; const char *que; } PP_PARCHE;

static void pista_propia_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("pista_propia", "activo", 1, ini)) {
        apuntar("  [pista_propia] apagada ([pista_propia] activo=0)");
        return;
    }
    g_pp_base = (BYTE *)GetModuleHandleA(NULL);
    static const PP_PARCHE P[] = {
        { 0x586336, { 0x75, 0x31 }, { 0x90, 0x90 }, 2, "clic en el recuadro «Pista» (sólo anfitrión)" },
        { 0x5883A7, { 0x0F, 0x85, 0x06, 0x02, 0x00, 0x00 }, { 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 }, 6,
          "botón «Elija la Pista» (sólo anfitrión)" },
    };
    const int NP = (int)(sizeof(P) / sizeof(P[0]));
    for (int i = 0; i < NP; i++)
        if (memcmp(PPV(P[i].va), P[i].esp, P[i].n) != 0) {
            apuntar("  [pista_propia] ⛔ %s (0x%08X) no tiene los bytes esperados: no se toca nada", P[i].que, P[i].va);
            return;
        }
    /* el 3er sitio: 0x58D520 `mov eax,[ecx+0x368]` (6) + `je 0x58D540` (2) -> jmp al salto (5) + 3 nop */
    static const BYTE e_conf[8] = { 0x8B, 0x81, 0x68, 0x03, 0x00, 0x00, 0x74, 0x18 };
    if (memcmp(PPV(0x58D520), e_conf, 8) != 0) {
        apuntar("  [pista_propia] ⛔ el confirmar (0x58D520) no tiene los bytes esperados: no se toca nada");
        return;
    }
    g_pp_cueva = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_pp_cueva) { apuntar("  [pista_propia] ⛔ sin memoria"); return; }
    /* esi = la sala · ecx = la ventana · los flags = (¿sala de carrera?) del `xor eax,0x1fef` de 0x58D51B ([+0x9574])
     *   mov eax,[ecx+0x368] · je MANDAR · cmp [g_modo_obst],0 · jne MANDAR · cmp [esi+0x9580],0x1fef · je LOCAL
     *   MANDAR: jmp 0x58D540 · LOCAL: jmp 0x58D528 */
    BYTE *k = g_pp_cueva;
    int i = 0;
    k[i++] = 0x8B; k[i++] = 0x81; *(DWORD *)(k + i) = 0x368; i += 4;                     /* mov eax,[ecx+0x368] */
    k[i++] = 0x74; int j_mandar1 = i++;                                                    /* je MANDAR */
    k[i++] = 0x83; k[i++] = 0x3D; *(DWORD *)(k + i) = (DWORD)&g_modo_obst; i += 4; k[i++] = 0x00;  /* cmp [g_modo_obst],0 */
    k[i++] = 0x75; int j_mandar2 = i++;                                                    /* jne MANDAR */
    k[i++] = 0x81; k[i++] = 0xBE; *(DWORD *)(k + i) = 0x9580; i += 4; *(DWORD *)(k + i) = 0x1FEF; i += 4;  /* cmp [esi+0x9580],0x1fef */
    k[i++] = 0x74; int j_local = i++;                                                      /* je LOCAL */
    int mandar = i;
    k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)PPV(0x58D540) - (DWORD)(k + i + 5)); i += 5;
    int local = i;
    k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)PPV(0x58D528) - (DWORD)(k + i + 5)); i += 5;
    k[j_mandar1] = (BYTE)(mandar - (j_mandar1 + 1));
    k[j_mandar2] = (BYTE)(mandar - (j_mandar2 + 1));
    k[j_local] = (BYTE)(local - (j_local + 1));
    int ok = 1;
    {
        BYTE n[8] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90 };
        *(int *)(n + 1) = (int)((DWORD)k - ((DWORD)PPV(0x58D520) + 5));
        DWORD viejo = 0;
        if (VirtualProtect(PPV(0x58D520), 8, PAGE_EXECUTE_READWRITE, &viejo)) {
            CopyMemory(PPV(0x58D520), n, 8);
            VirtualProtect(PPV(0x58D520), 8, viejo, &viejo);
            FlushInstructionCache(GetCurrentProcess(), PPV(0x58D520), 8);
        } else ok = 0;
    }
    for (int i = 0; i < NP; i++) {
        DWORD viejo = 0;
        BYTE *s = PPV(P[i].va);
        if (!VirtualProtect(s, P[i].n, PAGE_EXECUTE_READWRITE, &viejo)) { ok = 0; continue; }
        CopyMemory(s, P[i].nue, P[i].n);
        VirtualProtect(s, P[i].n, viejo, &viejo);
        FlushInstructionCache(GetCurrentProcess(), s, P[i].n);
    }
    apuntar(ok ? "  [pista_propia] ok: el invitado puede abrir la ventana de pistas y su elección va al server (FF1B); la práctica, local"
               : "  [pista_propia] ⛔ VirtualProtect falló a mitad");
}
