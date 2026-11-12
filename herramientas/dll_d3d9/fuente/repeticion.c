/* repeticion.c — EL QUE MIRA REPITE LA POSICIÓN REAL DE CADA CORREDOR (17-oct-2026)
 *
 * anonimo03: «si el espectador usara las mismas reglas de los corredores, sin serlo, todo se vería sincronizado… hemos
 * estado tratando de corregir un modo espectador que en sí estaba incompleto» → la opción B: el que mira NO simula a
 * los vecinos (piloto + un latido por segundo que los teletransporta), REPITE lo que pasó en cada juego.
 *
 * Lo medido (sonda en el que mira, 12 corren con BREAK e impulsor):
 *   · a los vecinos el juego los mueve en piloto y los corrige con el LATIDO (tipo 5): +3 en casi cada latido, y si
 *     el corredor no manda latidos (con el impulsor puesto: huecos de 7–10 s) se desfasa hasta ±50 y salta;
 *   · el latido lo anuncia el corredor cada 60 pasos (0x50A2A5 → 0x5039C0, caso tipo 5 en 0x503B05):
 *       t = reloj [+0x18] · a = el mismo reloj (bits) · b = ((paso [+0x68] + 1) << 16) | (asiento << 8) | (combo ≥ 40)
 *     y sale por los DOS caminos: la grabadora del FF98 (0x5641A0) y el en vivo (0x5C7FB0, FF26 a los corredores).
 *
 * Las dos piezas:
 *   1 · EL CORREDOR: en su paso (0x50A28D, cada cPlayer) si es el local y alguien mira ([cGame+0xC1C]) graba cada
 *       `cada` pasos (15 = 4/s) un tipo 5 SÓLO en la grabadora (0x5641A0): al que mira le llega la posición seguido,
 *       también con el impulsor, y a los otros corredores no les suma tráfico.
 *   2 · EL QUE MIRA: guarda los tipo 5 apenas llegan (el llamador único 0x5D5212 de 0x563CD0) y, en el paso de cada
 *       VECINO (no el que mira: ése se repite con sus teclas y se ve bien), lo pone donde estaba el real en ESE paso
 *       (interpola entre las dos posiciones que lo rodean) con la misma función del latido (0x572F40 → reloj y
 *       distancia por el mapa de BPM). Si todavía no llegó la que viene, sigue con el último ritmo (hasta 30 pasos).
 *   [repeticion] activo=0 / cada=15 en d3d9_proxy.ini. Se INCLUYE desde d3d9_proxy.c.
 */

#define RP_PASO_SITIO   0x0050A28D      /* mov al,[esi+0x6D] · test al,al  (5 B) — el paso de cada cPlayer */
#define RP_PASO_VUELTA  0x0050A292
#define RP_RECIBE_LLAMA 0x005D5212      /* call 0x563CD0: cada registro del FF98 que le llega al que mira */
#define RP_TOPE 64

typedef void (__fastcall *F_RP_RECIBE)(void *self, void *edx, float t, DWORD tipo, DWORD a, DWORD b);
typedef void (__fastcall *F_RP_LATIDO)(void *mapa, void *edx, BYTE *jug, float t, int pasos);
typedef void (__fastcall *F_RP_GRABA)(BYTE *jug, void *edx, float t, DWORD tipo, DWORD a, DWORD b);

static BYTE *g_rp_base;
static F_RP_RECIBE g_rp_recibe_real;
static int g_rp_activo = 0, g_rp_cada = 15;
static long g_rp_grabados = 0, g_rp_recibidos = 0, g_rp_puestos = 0;
typedef struct { int n; WORD paso[RP_TOPE]; float reloj[RP_TOPE]; } RP_SERIE;
static RP_SERIE g_rp[16];

#define RPV(va) (g_rp_base + ((DWORD)(va) - 0x400000))

static BYTE *rp_game(void) { return *(BYTE **)RPV(0x009314C8); }

/* el que mira: llegó un registro del FF98 */
static void __fastcall rp_recibe(void *self, void *edx, float t, DWORD tipo, DWORD a, DWORD b)
{
    if ((tipo & 0xFF) == 5) {
        BYTE s = (BYTE)(b >> 8);
        WORD p = (WORD)(b >> 16);
        if (s < 16) {
            RP_SERIE *r = &g_rp[s];
            if (r->n && (WORD)(p - r->paso[r->n - 1]) > 0x8000) r->n = 0;     /* paso para atrás: otra carrera */
            if (!r->n || p != r->paso[r->n - 1]) {
                if (r->n == RP_TOPE) {                                         /* corre la ventana */
                    MoveMemory(r->paso, r->paso + 16, (RP_TOPE - 16) * sizeof(WORD));
                    MoveMemory(r->reloj, r->reloj + 16, (RP_TOPE - 16) * sizeof(float));
                    r->n -= 16;
                }
                r->paso[r->n] = p;
                r->reloj[r->n] = *(float *)&a;
                r->n++;
                g_rp_recibidos++;
            }
        }
    }
    g_rp_recibe_real(self, edx, t, tipo, a, b);
}

/* ★ 17-oct (anonimo03: «los que llegaban al podio retroceden… y el podio sólo muestra al que miro»): al LLEGAR el corredor
 *   deja de transmitir (el juego le apaga [cGame+0xC1C]); la repetición sigue al último ritmo para que cruce la meta en
 *   el que mira, y apenas el juego lo da por llegado lo SUELTA para que el podio lo acomode. «Llegado» = lo mismo que
 *   mira el exe para no aplicarle más latidos (0x56D81D / 0x56D844): [+0x54] ≠ 0 o el estado [+0x2A0] = 0x50AEE0 /
 *   0x50B180. */
static int rp_suelto(BYTE *jug)
{
    DWORD est = *(DWORD *)(jug + 0x2A0);
    return *(DWORD *)(jug + 0x54) != 0 || est == (DWORD)RPV(0x0050AEE0) || est == (DWORD)RPV(0x0050B180);
}

/* el reloj real del asiento `s` en el paso `x` (con fracción): interpola entre las dos posiciones que lo rodean; si
 *   la que viene todavía no llegó, sigue con el último ritmo (hasta 30 pasos). 0 = no hay con qué. */
static int rp_reloj(BYTE s, float x, float *c)
{
    RP_SERIE *r = &g_rp[s];
    if (r->n < 2) return 0;
    WORD L = (WORD)x;
    float fr = x - (float)L;
    int k0, k1;
    if ((short)(r->paso[r->n - 1] - L) <= 0) {
        k1 = r->n - 1; k0 = r->n - 2;
        if ((short)(L - r->paso[k1]) > 600) return 0;          /* ★ hasta 10 s: al llegar a la meta deja de mandar */
    } else {
        k1 = 0;
        while ((short)(r->paso[k1] - L) <= 0) k1++;
        if (k1 == 0) return 0;
        k0 = k1 - 1;
    }
    int dp = (short)(r->paso[k1] - r->paso[k0]);
    if (dp <= 0) { *c = r->reloj[k1]; return 1; }
    float u = ((float)(short)(L - r->paso[k0]) + fr) / (float)dp;
    *c = r->reloj[k0] + (r->reloj[k1] - r->reloj[k0]) * u;
    return 1;
}

/* en el paso de cada cPlayer (desde la cueva de 0x50A28D) */
static void __stdcall rp_paso(BYTE *jug)
{
    BYTE *g = rp_game();
    if (!g || !jug) return;
    BYTE s = jug[0x49];
    WORD L = *(WORD *)(jug + 0x68);
    if (!g[0xC01]) {
        /* ── el corredor: la posición seguido, sólo por la grabadora ── */
        BYTE *red = *(BYTE **)RPV(0x00931660);
        if (!red || s != red[0x40] || !g[0xC1C]) return;
        if (L == 0 || L % g_rp_cada) return;                          /* en la intro (paso 0) no */
        float reloj = *(float *)(jug + 0x18);
        DWORD combo = ((DWORD)(*(WORD *)(jug + 0x190) ^ *(WORD *)RPV(0x00904210)) >= 0x28) ? 1 : 0;
        DWORD b = ((DWORD)(WORD)(L + 1) << 16) | ((DWORD)s << 8) | combo;
        ((F_RP_GRABA)RPV(0x005641A0))(jug, NULL, reloj, 5, *(DWORD *)&reloj, b);
        g_rp_grabados++;
        return;
    }
    /* ── el que mira: el vecino donde estaba el real en este paso ── */
    if (s >= 16 || s == g[0xC02] || rp_suelto(jug)) return;
    float c;
    if (!rp_reloj(s, (float)L, &c)) return;
    ((F_RP_LATIDO)RPV(0x00572F40))(g + 0xA20, NULL, jug, c, L);
    g_rp_puestos++;
}

/* al DIBUJAR (desde fluidez.c): cada vecino en su posición real en «paso + fracción»; lo que había se devuelve después */
static int rp_dibujo(DWORD **gp, DWORD *gv, float frac)
{
    BYTE *g = rp_game();
    if (!g_rp_activo || !g || !g[0xC01]) return 0;
    BYTE **b = *(BYTE ***)(g + 0xA14), **e = *(BYTE ***)(g + 0xA18);
    if (!b || !e || e <= b || e - b > 16) return 0;
    int n = 0;
    for (BYTE **p = b; p < e; p++) {
        BYTE *jug = *p;
        if (!jug) continue;
        BYTE s = jug[0x49];
        if (s >= 16 || s == g[0xC02] || rp_suelto(jug)) continue;
        float c;
        WORD L = *(WORD *)(jug + 0x68);
        if (!rp_reloj(s, (float)L + frac, &c)) continue;
        gp[n] = (DWORD *)(jug + 0x18); gv[n] = *(DWORD *)(jug + 0x18); n++;
        gp[n] = (DWORD *)(jug + 0x20); gv[n] = *(DWORD *)(jug + 0x20); n++;
        ((F_RP_LATIDO)RPV(0x00572F40))(g + 0xA20, NULL, jug, c, L);
    }
    return n;
}

static void repeticion_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("repeticion", "activo", 1, ini)) { apuntar("  [repeticion] apagada ([repeticion] activo=0)"); return; }
    if (g_tx_en_vivo) { apuntar("  [repeticion] no va: el que mira está EN VIVO (transmision.c)"); return; }
    g_rp_cada = GetPrivateProfileIntA("repeticion", "cada", 15, ini);
    if (g_rp_cada < 5) g_rp_cada = 5;
    g_rp_base = (BYTE *)GetModuleHandleA(NULL);
    static const BYTE paso_esp[5] = { 0x8A, 0x46, 0x6D, 0x84, 0xC0 };    /* mov al,[esi+0x6D] · test al,al */
    BYTE *c = RPV(RP_RECIBE_LLAMA);
    if (memcmp(RPV(RP_PASO_SITIO), paso_esp, 5) != 0 || c[0] != 0xE8
            || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)RPV(0x00563CD0)) {
        apuntar("  [repeticion] ⛔ los sitios no son los esperados: no se toca nada");
        return;
    }
    /* la cueva del paso: pushad · push esi · call rp_paso · popad · lo pisado · jmp vuelta */
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return;
    int i = 0;
    k[i++] = 0x60;                                                                  /* pushad          */
    k[i++] = 0x56;                                                                  /* push esi        */
    k[i] = 0xE8; *(int *)(k + i + 1) = (int)((DWORD)rp_paso - (DWORD)(k + i + 5)); i += 5;   /* call (stdcall) */
    k[i++] = 0x61;                                                                  /* popad           */
    for (int j = 0; j < 5; j++) k[i++] = paso_esp[j];                               /* lo pisado       */
    k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)RPV(RP_PASO_VUELTA) - (DWORD)(k + i + 5)); i += 5;
    BYTE s1[5] = { 0xE9, 0, 0, 0, 0 };
    *(int *)(s1 + 1) = (int)((DWORD)k - ((DWORD)RPV(RP_PASO_SITIO) + 5));
    g_rp_recibe_real = (F_RP_RECIBE)RPV(0x00563CD0);
    BYTE c_esp[5], s2[5] = { 0xE8, 0, 0, 0, 0 };
    CopyMemory(c_esp, c, 5);
    *(int *)(s2 + 1) = (int)((DWORD)rp_recibe - ((DWORD)c + 5));
    if (escribir_bytes(RP_PASO_SITIO, paso_esp, s1, 5, "repeticion paso")
            && escribir_bytes(RP_RECIBE_LLAMA, c_esp, s2, 5, "repeticion recibe")) {
        g_rp_activo = 1;
        g_rp_dibujo = rp_dibujo;
        apuntar("  [repeticion] ★ el que mira repite la posición REAL de los vecinos (el corredor la manda cada %d pasos)",
                g_rp_cada);
    }
}
