/* cielo_ancho.c — EL CIELO DE LAS PISTAS EN PANTALLA ANCHA (26-oct-2026) · documentacion/CIELO_ANCHO.md
 *
 * anonimo03: «si observas el fondo, sale con bordes negros, ya que el 2013 no fue hecho para correr en resoluciones altas;
 * revisa el de Steam, XYX o Corea, por si estiraron la textura o la completaron».
 *
 * EL CIELO NO ES UNA MALLA DE LA PISTA: es `Sky="backNN/sky.dds"` de `stage_lt.txt` (lo carga 0x528FC0 en
 * [escena+0xB8]) y lo dibuja 0x528FF0 como UN rectángulo FIJO de 4 vértices del exe — VA 0x904A38, 20 B cada uno
 * (x, y, z, u, v), `DrawPrimitiveUP(FAN, 2, …, 0x14)` con FVF 0x102:
 *        (−16000,  12000, 11800, 0, 0)   (−16000, −12000, 11800, 0, 1)
 *        ( 16000, −12000, 11800, 1, 1)   ( 16000,  12000, 11800, 1, 0)
 * 32000 × 24000 = 4:3. La cámara deja FIJO el alto y abre a lo ancho (medido en la captura de anonimo03: a 1920×1080 el
 * cielo ocupaba 1453 px = el 4:3 de 1080) ⇒ en 16:9 se ve más allá del rectángulo: los bordes negros.
 *
 * LO QUE HIZO STEAM (R2Dash, `Game_dash_1.exe`): las texturas y las pistas son IDÉNTICAS byte a byte en los cinco
 * clientes (2013, XYX, Steam, coreano moderno, r2musa); lo que cambió es el MOTOR: además de la tabla 4:3 trae una
 * ANCHA de ±22000 con la misma u de 0 a 1 ⇒ ESTIRARON la textura. Acá lo mismo, a la medida de cada pantalla:
 * medio ancho = 12000 × (ancho / alto) × 1,02 (nunca menos de 16000: en 4:3 queda como de fábrica).
 *
 * La tabla está en .data (escribible): se escribe al crear el dispositivo y en cada Reset (cambio de resolución).
 * GUARDA: sólo si y, z, u, v son los de fábrica y las x son ±algo entre 16000 y 100000 (la de fábrica o la nuestra).
 * [cielo] ancho=0 lo deja de fábrica.
 * Se INCLUYE desde d3d9_proxy.c. */

#define CIELO_VA        0x904A38
#define CIELO_MEDIO_ALTO 12000.0f

static int   g_cielo_activo = 1;
static float g_cielo_puesto = 0;          /* el medio ancho que quedó escrito (0 = todavía nada) */

static void cielo_ajustar(UINT ancho, UINT alto)
{
    if (!g_cielo_activo || !ancho || !alto) return;
    float *v = (float *)((BYTE *)GetModuleHandleA(NULL) + (CIELO_VA - 0x400000));
    /* los 4 vértices: x y z u v */
    static const float Y[4] = { 12000, -12000, -12000, 12000 }, U[4] = { 0, 0, 1, 1 }, V[4] = { 0, 1, 1, 0 };
    static const float S[4] = { -1, -1, 1, 1 };                     /* el signo de la x de cada vértice */
    for (int k = 0; k < 4; k++) {
        float *p = v + 5 * k, ax = p[0] * S[k];
        if (p[1] != Y[k] || p[2] != 11800.0f || p[3] != U[k] || p[4] != V[k] || ax < 15999.0f || ax > 100000.0f) {
            apuntar("  [cielo] ⚠ la tabla del cielo (0x%X) no es la esperada en el vértice %d (%d, %d, %d, u×100 %d,"
                    " v×100 %d): no la toco", CIELO_VA, k, (int)p[0], (int)p[1], (int)p[2], (int)(p[3] * 100),
                    (int)(p[4] * 100));
            g_cielo_activo = 0;
            return;
        }
    }
    float medio = CIELO_MEDIO_ALTO * (float)ancho / (float)alto * 1.02f;
    if (medio < 16000.0f) medio = 16000.0f;
    for (int k = 0; k < 4; k++) v[5 * k] = S[k] * medio;
    if (medio != g_cielo_puesto)
        apuntar("  [cielo] pantalla %ux%u: el cielo de las pistas a ±%d de ancho (de fábrica ±16000, 4:3)",
                ancho, alto, (int)medio);         /* (apuntar es wsprintf: sin %f) */
    g_cielo_puesto = medio;
}

static void cielo_ancho_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_cielo_activo = (int)GetPrivateProfileIntA("cielo", "ancho", 1, ini);
    if (!g_cielo_activo) apuntar("  [cielo] ancho=0: el cielo de las pistas queda de fábrica (4:3)");
}
