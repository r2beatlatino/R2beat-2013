/* heroe_aleatorio.c — el QUINTO modo héroe: «Modo Aleatorio» (随机模式, 29-oct-2026)
 *
 *   anonimo03: «nos falta el modo random en el hock y como item; existe en el 2019». El 2013 tiene los
 *   otros cuatro (Espejo 0x18A · Niebla 0x18B · Locura 0x18C · Sin Piedras 0x278) y NO éste: en el
 *   chino es el ítem 1000851 «随机模式（HERO）» con ItemEffect 2585 (0xA19). Doc: MODO_ALEATORIO.md.
 *
 *   Cómo lo hace el 2019 (Game_autonomo.exe, leído con leer_exe.py):
 *     0xBF5CC0  arma las banderas del asiento: 0x18A -> 2 (espejo) · 0xA19 -> 0x10 (aleatorio) · ...
 *     0xBD9D20  el ARMADOR del patrón de notas: copia el de la canción y le aplica, en este orden,
 *               0x10 aleatorio (0xBDA2B0) · 0x20 · 1 · 2 espejo · 4 · 0x40
 *     0xBDA2B0  ★ el aleatorio: srand(asiento×100 + la clave de la carrera) y, nota por nota, sortea
 *               el tipo (flechas ↔ estrellas conservando cuántas hay de cada una, las largas de a
 *               pares) y le vuelve a calcular el carril. Lo porta `ha_mezclar` tal cual.
 *
 *   El 2013 tiene EL MISMO armador (0x566020, banderas 1 / 2 / 4) y el mismo lugar que junta las
 *   banderas (0x56D920, «armar las notas del asiento», thiscall(juego, asiento)). La 0x10 está libre.
 *   Lo nuestro, sin tocar un byte de código del juego más que el destino de 4 llamadas:
 *     0x56E2B3 · 0x56F513   las dos llamadas a 0x56D920   -> `ha_asiento`: anota el asiento y sigue
 *     0x56DAEE              la búsqueda del patrón por banderas (0x5660D0) -> `ha_obtener`: si el
 *                           asiento tiene el efecto 0xA19 suma 0x10 y el ASIENTO a la clave (así cada
 *                           uno tiene el suyo en la caché, que va por banderas)
 *     0x5660E6              el armador, cuando no está en la caché -> `ha_armar`: con 0x10 arma el
 *                           patrón pelado y le aplica aleatorio, 1, 2, 4 en el orden del 2019
 *     0x4FF07E              ★ el GRITO DEL HÉROE: 0x4FF020 «¿tiene algún modo héroe?» pregunta por los 4
 *                           (la llaman los dos festejos, 0x50592C y 0x50746D); su última pregunta (la de
 *                           0x278) también contesta que sí con el ítem del aleatorio -> `ha_grito`.
 *                           Como en el 2019 (0x65C7B4, el bit 0x80), cuenta el ÍTEM, no lo que fuerce la tool
 *
 *   ★ La semilla es la del 2019: asiento×100 + la clave del FF25 ([0x904210]). Todos los de la sala la
 *     conocen ⇒ todos ven las MISMAS notas al azar de cada uno. El azar es el `rand()` de MSVC con
 *     estado propio (no se toca el srand del juego).
 *   ★ La R2beat tool (herramienta.c) fuerza o saca el aleatorio de MI asiento: `ha_tool()`.
 */
#define HA_EFECTO 0xA19                 /* ItemEffect 2585, el del 2019 */
#define HA_BANDERA 0x10
#define HAV(x) (g_ha_base + ((DWORD)(x) - 0x400000))

typedef BYTE  (__thiscall *F_HA_EFECTO)(void *sala, int asiento, int efecto);   /* 0x5285D0 */
typedef void  (__thiscall *F_HA_ASIENTO)(void *juego, int asiento);              /* 0x56D920 */
typedef void *(__thiscall *F_HA_PATRON)(void *cache, int banderas);              /* 0x5660D0 / 0x566020 */
typedef void  (__thiscall *F_HA_PASO)(void *cache, void *patron);                /* 0x565C20 / 0x565550 / 0x565E50 */
typedef BYTE  (__thiscall *F_HA_CARRIL)(void *tabla, int pos);                   /* 0x4E6470 */
typedef BYTE  (__thiscall *F_HA_POS)(void *tabla, int tipo, int carril);         /* 0x4E7B10 */
typedef BYTE  (__thiscall *F_HA_POS_ITEM)(void *juego, int tipo, BYTE *item, int pos); /* 0x4E9ED0 */
typedef BYTE  (__thiscall *F_HA_RELEVO)(void *juego, int x);                     /* 0x4EE8D0 */

static BYTE *g_ha_base = NULL;
static int   g_ha_asiento = -1;         /* el que se está armando ahora (dentro de 0x56D920) */
static int   g_ha_activo = 0;

/* lo que dice la tool para MI asiento: 1 forzar · 0 sacar · -1 lo que diga el ítem (herramienta.c,
 * incluida antes; `puesta` ya mira permitida / rota / apagada) */
static int ha_tool(void)
{
    if (g_op[O_ALEATORIO].puesta) return 1;
    if (g_op[O_ALEATORIO_S].puesta) return 0;
    return -1;
}

/* ¿el asiento tiene el ítem puesto? (el FF80 de la carrera, como los otros cuatro) */
static int ha_item(int asiento)
{
    BYTE *sala = *(BYTE **)HAV(0x931660);
    if (!sala || asiento < 0) return 0;
    return ((F_HA_EFECTO)HAV(0x5285D0))(sala, asiento & 0xFF, HA_EFECTO) ? 1 : 0;
}

static int ha_quiere(int asiento)
{
    BYTE *sala = *(BYTE **)HAV(0x931660);
    if (!sala || asiento < 0) return 0;
    int r = ha_item(asiento);
    if ((BYTE)asiento == sala[0x40]) {
        int t = ha_tool();
        if (t >= 0) r = t;
    }
    return r;
}

/* el `rand()` de MSVC (0x343FD / 0x269EC3), con su propio estado */
static DWORD g_ha_azar;
static int ha_rand(void)
{
    g_ha_azar = g_ha_azar * 0x343FD + 0x269EC3;
    return (int)((g_ha_azar >> 16) & 0x7FFF);
}

/* ★ 11-nov — EL NIVEL NORMAL DE CADA TIPO (los OBSTÁCULOS ESPECIALES). anonimo03, por el reclamo de un jugador: «el modo
 *   aleatorio está activando ese obstáculo… en modo aleatorio debe seguir desactivado, como ya estaba».
 *   La «posición» de la nota (+4) es el ÍNDICE del bloque del `backNNN.txt` que se dibuja; `carril()` (0x4E6470) da
 *   su Level, y `pos(tipo, carril)` (0x4E7B10) busca el bloque de ese TIPO y ese LEVEL (si no hay, cualquiera de ese
 *   tipo). Los charts piden cada tipo con UN nivel (medido en los 3.681 .bin: UP_S/DOWN_S 3, LEFT_S/RIGHT_S 2,
 *   UPLEFT/UPRIGHT 5, DOWNLEFT/DOWNRIGHT 4, estrellas 1), y las pistas traen además bloques «especiales» que casi
 *   nadie pide: LEFT_S/RIGHT_S de nivel 1 (`object_left20` / `right20` / `left_c`, la barrita de colores, en 18
 *   pistas; los piden 6 charts). El port del 2019 conservaba el nivel VIEJO al cambiar el tipo ⇒ una ESTRELLA (nivel 1)
 *   que salía flecha izquierda caía justo en LEFT_S nivel 1 = el especial; y una flecha arriba (3) que salía
 *   izquierda no encontraba LEFT_S 3 y caía en cualquiera, el especial incluido.
 *   ⇒ si el tipo CAMBIÓ, se busca el bloque con el nivel normal del tipo nuevo; si no cambió, el del chart (los 6
 *   charts que piden el especial lo siguen teniendo). Inventario: `_trabajo/obst_pista11/especiales.py`. */
static BYTE ha_nivel_normal(BYTE t, BYTE carril)
{
    switch (t) {
    case 0x10: case 0x11: return 3;                               /* UP_S · DOWN_S            */
    case 0x12: case 0x13: return 2;                               /* LEFT_S · RIGHT_S          */
    case 0x14: case 0x15: return 5;                               /* UPLEFT_S · UPRIGHT_S      */
    case 0x16: case 0x17: return 4;                               /* DOWNLEFT_S · DOWNRIGHT_S  */
    case 0x1A: case 0x1B: return 1;                               /* las estrellas             */
    }
    return carril;                                                /* las largas: sólo nivel 5  */
}

/* ★ 0xBDA2B0 del 2019, al 2013. Las notas: 12 bytes, +4 la posición, +5 el tipo, +8 el ítem. */
static void ha_mezclar(BYTE *patron, int asiento)
{
    BYTE *ini = *(BYTE **)(patron + 0xC), *fin = *(BYTE **)(patron + 0x10);
    int n = ini && fin > ini ? (int)((fin - ini) / 12) : 0;
    void *tabla = *(void **)HAV(0x9D4414), *juego = *(void **)HAV(0x9314C8);
    if (!n || !tabla || !juego) return;
    /* lo del relevo, como el espejo del 2013 (0x565550): el ítem 0xF1 en relevo no se recalcula */
    int relevo = (((BYTE *)juego)[0xC] & 0x40) && ((F_HA_RELEVO)HAV(0x4EE8D0))(juego, 1);
    g_ha_azar = (DWORD)(asiento * 100) + *(DWORD *)HAV(0x904210);
    int estrellas = 0, flechas = 0;
    for (int i = 0; i < n; i++) {
        BYTE t = ini[i * 12 + 5];
        if (t == 0x1A || t == 0x1B) estrellas++;
        else if (t >= 0x10 && t <= 0x13) flechas++;
    }
    BYTE base = 0, en_larga = 0;
    int cambiadas = 0, normalizadas = 0;
    for (int i = 0; i < n; i++) {
        BYTE *nota = ini + i * 12;
        BYTE t = nota[5], t_chart = t;
        BYTE carril = ((F_HA_CARRIL)HAV(0x4E6470))(tabla, nota[4]);
        if ((t >= 0x10 && t <= 0x13) || t == 0x1A || t == 0x1B) {
            if (nota[8] == 0) {                                   /* con ítem encima no se toca */
                int estrella = ha_rand() & 1;
                if (flechas < estrellas) estrella = 1;
                else if (estrellas == 0) estrella = 0;
                if (estrella) { estrellas--; t = (ha_rand() & 1) ? 0x1A : 0x1B; }
                else { flechas--; t = (BYTE)(0x10 + (ha_rand() & 3)); }
                nota[5] = t;
            }
        } else if (t >= 0x14 && t <= 0x17) {
            t = (BYTE)(0x14 + (ha_rand() & 3)); nota[5] = t;
        } else if (t == 0x80 || t == 0x83) {                      /* larga de a dos: el comienzo */
            base = (BYTE)(0x80 + 3 * (ha_rand() & 1)); t = base; nota[5] = t; en_larga = 1;
        } else if (t == 0x82 || t == 0x85) {                      /* ... y el final */
            t = (BYTE)(base + 2); nota[5] = t; en_larga = 0;
        } else if (t == 0x86 || t == 0x89 || t == 0x8C || t == 0x8F) {   /* larga de a cuatro */
            base = (BYTE)(0x86 + 3 * (ha_rand() & 3)); t = base; nota[5] = t; en_larga = 1;
        } else if (t == 0x88 || t == 0x8B || t == 0x8E || t == 0x91) {
            t = (BYTE)(base + 2); nota[5] = t; en_larga = 0;
        } else if (en_larga) {                                    /* el medio de la larga */
            t = (BYTE)(base + 1); nota[5] = t;
        }
        if (nota[8] && !(nota[8] == 0xF1 && relevo))
            nota[4] = ((F_HA_POS_ITEM)HAV(0x4E9ED0))(juego, t, nota + 8, nota[4]);
        else {
            if (t != t_chart) {                                   /* ★ tipo nuevo: su nivel normal, no el viejo */
                BYTE nv = ha_nivel_normal(t, carril);
                if (nv != carril) normalizadas++;
                carril = nv;
            }
            nota[4] = ((F_HA_POS)HAV(0x4E7B10))(tabla, t, carril);
        }
        cambiadas++;
    }
    apuntar("  [aleatorio] asiento %d: %d notas al azar, %d con el nivel normal de su tipo nuevo (semilla %u)",
            asiento, cambiadas, normalizadas, (unsigned)(asiento * 100) + *(DWORD *)HAV(0x904210));
}

/* 0x5660E6: el armador, cuando el patrón de esas banderas no está en la caché */
static void *__fastcall ha_armar(void *cache, void *nada, int banderas)
{
    F_HA_PATRON armar = (F_HA_PATRON)HAV(0x566020);
    (void)nada;
    if (!(banderas & HA_BANDERA)) return armar(cache, banderas);
    void *p = armar(cache, 0);                                    /* la copia pelada de la canción */
    if (!p) return p;
    ha_mezclar((BYTE *)p, (banderas >> 8) & 0xFF);
    /* después, lo demás en el orden del 2019 (0xBD9D20): 1 · 2 espejo · 4 */
    if (banderas & 1) ((F_HA_PASO)HAV(0x565C20))(cache, p);
    if (banderas & 2) ((F_HA_PASO)HAV(0x565550))(cache, p);
    if (banderas & 4) ((F_HA_PASO)HAV(0x565E50))(cache, p);
    return p;
}

/* 0x56DAEE: la búsqueda del patrón del asiento por banderas */
static void *__fastcall ha_obtener(void *cache, void *nada, int banderas)
{
    (void)nada;
    if (g_ha_asiento >= 0 && ha_quiere(g_ha_asiento))
        banderas |= HA_BANDERA | ((g_ha_asiento & 0xFF) << 8);
    return ((F_HA_PATRON)HAV(0x5660D0))(cache, banderas);
}

/* 0x56E2B3 / 0x56F513: «armar las notas del asiento» — sólo anota cuál es */
static void __fastcall ha_asiento(void *juego, void *nada, int asiento)
{
    (void)nada;
    g_ha_asiento = asiento & 0xFF;
    ((F_HA_ASIENTO)HAV(0x56D920))(juego, asiento);
    g_ha_asiento = -1;
}

/* 0x4FF07E: la última pregunta de «¿tiene algún modo héroe?» (la de Sin Piedras, 0x278) */
static BYTE __fastcall ha_grito(void *sala, void *nada, int asiento, int efecto)
{
    (void)nada;
    BYTE r = ((F_HA_EFECTO)HAV(0x5285D0))(sala, asiento, efecto);
    return r ? r : (BYTE)ha_item(asiento & 0xFF);
}

/* la guarda de un `call` (E8 rel32): ¿apunta a `antes`? */
static int ha_desviar(DWORD sitio, DWORD antes, const char *que)
{
    BYTE *s = HAV(sitio);
    if (s[0] != 0xE8 || (DWORD)(s + 5 + *(int *)(s + 1)) != (DWORD)HAV(antes)) {
        apuntar("  [aleatorio] ⛔ %s (0x%06X) no es la esperada: no se toca nada", que, sitio);
        return 0;
    }
    return 1;
}

static void ha_escribir(DWORD sitio, void *nuevo)
{
    BYTE *s = HAV(sitio);
    DWORD viejo = 0;
    int rel = (int)((DWORD)nuevo - ((DWORD)s + 5));
    VirtualProtect(s + 1, 4, PAGE_EXECUTE_READWRITE, &viejo);
    *(int *)(s + 1) = rel;
    VirtualProtect(s + 1, 4, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, 5);
}

static void heroe_aleatorio_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("aleatorio", "activo", 1, ini)) {
        apuntar("  [aleatorio] apagado ([aleatorio] activo=0)");
        g_op[O_ALEATORIO].rota = g_op[O_ALEATORIO_S].rota = 1;
        return;
    }
    g_ha_base = (BYTE *)GetModuleHandleA(NULL);
    /* ⚠ las cinco guardas ANTES de escribir la primera: o van todas o ninguna */
    if (!ha_desviar(0x56E2B3, 0x56D920, "la 1.ª llamada a «armar las notas del asiento»") ||
        !ha_desviar(0x56F513, 0x56D920, "la 2.ª llamada a «armar las notas del asiento»") ||
        !ha_desviar(0x56DAEE, 0x5660D0, "la búsqueda del patrón por banderas") ||
        !ha_desviar(0x5660E6, 0x566020, "el armador del patrón") ||
        !ha_desviar(0x4FF07E, 0x5285D0, "la pregunta de Sin Piedras de «¿tiene modo héroe?»") ||
        *(DWORD *)HAV(0x4FF079) != 0x278) {
        g_op[O_ALEATORIO].rota = g_op[O_ALEATORIO_S].rota = 1;           /* en gris en la tool */
        return;
    }
    ha_escribir(0x56E2B3, ha_asiento);
    ha_escribir(0x56F513, ha_asiento);
    ha_escribir(0x56DAEE, ha_obtener);
    ha_escribir(0x5660E6, ha_armar);
    ha_escribir(0x4FF07E, ha_grito);
    g_ha_activo = 1;
    apuntar("  [aleatorio] ok: el Modo Aleatorio (efecto 0x%X) enganchado en 0x56E2B3 · 0x56F513 · 0x56DAEE · 0x5660E6 · grito 0x4FF07E",
            HA_EFECTO);
}
