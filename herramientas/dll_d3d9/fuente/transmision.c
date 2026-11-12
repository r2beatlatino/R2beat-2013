/* transmision.c — el MODO TRANSMISIÓN del espectador: TODO con el mismo retraso (12-oct-2026, 2.ª vuelta).
 *
 * anonimo03: *«o todo en vivo, o todo absolutamente todo —impulsor incluido— con el mismo retraso, para que tenga
 * coherencia»*. «En vivo» no puede traer combos reales (a un rival el juego lo SIMULA: piloto automático, todo
 * PERFECT); el combo real sale de las teclas de cada corredor, y eso llega con retraso. ⇒ todo diferido.
 * Base: documentacion/ESPECTADOR_INVESTIGACION_SYNC_Y_COMBOS.md (lo de abajo, verificado en el exe):
 *
 *  1. C03 = 1 (`[cGame+0xC03]`, el modo transmisión): el que corre graba CADA TECLA como evento 0x62 (`0x564130`) y
 *     el que mira las re-juzga con el juez normal de notas → combo, golpes y tropiezos reales del asiento que mira.
 *     El único escritor del 2013 lo pone en 0 al arrancar cada carrera (`0x563C35`): ese 0 pasa a 1. (El 2019 lo
 *     prende siempre: `SetBroadcastMode(1)`.) ⚠ La prueba de las 20:37 que lo «descartó» era inválida: el que corría
 *     estaba con `.autoplay` (no aprieta teclas).
 *  2. La lista de tipos que el que mira ACEPTA con C03 (`0x563CD0`: tabla 0x904CE8, 4 tipos, que dejaba afuera los
 *     efectos y el impulsor) pasa a la del 2019: {0, 1, 5, 9, 0x0A, 0x62, 0x66, 0x63, 0x64} — `0x563CE4` (el disp32
 *     de la tabla) y `0x563CED` (el `cmp eax,4`: el tope, 4 → 9).
 *  3. Los dos tiempos: el que mira espera 4000 ms después del GO para arrancar (`0x4F0AA7 push 0xFA0`,
 *     SetTimer 0x97) y el que corre vacía su grabadora cada 2000 ms (`0x4F0AE7 push 0x7D0`, SetTimer 0x98) ⇒ la
 *     repetición iba 4 s atrás. Pasan a `espera_ms` (750) y `envio_ms` (250). Regla: espera ≥ envío + viaje + 1 cuadro.
 *  4. El CARTEL del resultado: si soy espectador, el FF28 (`0x5E8F67 push 0xFA0`, SetTimer 0x9A) lo muestra 4000 ms
 *     después (pensado para la repetición de 4 s). anonimo03: «al espectador el cartel le tardó más de 5 s». Pasa al
 *     mismo `espera_ms`.
 *  El server deja de pasarle al que mira el FF4E en vivo de quien le manda FF98 (`ESPECTADOR_DIFERIDO`).
 * [transmision] activo=0 / espera_ms / envio_ms en d3d9_proxy.ini. Se INCLUYE desde d3d9_proxy.c.
 */

static DWORD g_tx_espera_ms = 750;                   /* ★ 14-oct: el atraso del que mira (lo usa globo_combo.c) */
/* ★ 17-oct · EL QUE MIRA, «UN CORREDOR MÁS EN VIVO» (anonimo03, con dos capturas: «los corredores ven la escena como la
 *   primera imagen —el pelotón junto, con los impulsores—, el espectador como la segunda, que está totalmente mal…
 *   nuestro objetivo es que el espectador también vea las posiciones e impulsores como la primera»).
 *   Lo diferido (C03 + FF98 a 750 ms + repetición) re-juega las teclas de cada uno: exige que lleguen perfectas, y con
 *   un corredor trabado la copia pierde notas, no usa el impulsor y se queda atrás (MEDIDO: asientos 4..7 con ~1/3 de
 *   los golpes y 2 de 20 impulsores). Un corredor ve a los demás en PILOTO, con su FF4E EN VIVO (impulsor, latido) ⇒
 *   en_vivo=1: el que mira hace lo mismo — arranca con el GO, sin C03, IGNORA el FF98 (0x563CD0 → ret 0x10: si no,
 *   el impulsor y el latido llegarían dos veces) y el server le pasa el FF4E en vivo (ESPECTADOR_DIFERIDO = False).
 *   El globo y la calculadora siguen: viajan por el FF4E (sub 0x70..0x72), ahora sin atraso. en_vivo=0: lo diferido. */
static int g_tx_en_vivo = 0;
static BYTE g_tx_tipos[9] = { 0x00, 0x01, 0x05, 0x09, 0x0A, 0x62, 0x66, 0x63, 0x64 };   /* la lista del 2019 */

static void transmision_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("transmision", "activo", 1, ini)) {
        apuntar("  [transmision] apagada ([transmision] activo=0): el que mira, 4 s atrás y sin combos");
        return;
    }
    g_tx_en_vivo = GetPrivateProfileIntA("transmision", "en_vivo", 1, ini);
    DWORD espera = (DWORD)GetPrivateProfileIntA("transmision", "espera_ms", 750, ini);
    DWORD envio = (DWORD)GetPrivateProfileIntA("transmision", "envio_ms", 250, ini);
    if (envio < 50) envio = 50;
    if (espera < envio + 200) espera = envio + 200;          /* la regla: si no, el que mira se queda sin datos */
    g_tx_espera_ms = espera;
    if (g_tx_en_vivo) {
        static const BYTE rx_esp[5] = { 0xA1, 0xC8, 0x14, 0x93, 0x00 };             /* 0x563CD0  mov eax,[0x9314C8] */
        static const BYTE rx_nue[5] = { 0xC2, 0x10, 0x00, 0x90, 0x90 };             /*           ret 0x10 */
        static const BYTE e4000[5] = { 0x68, 0xA0, 0x0F, 0x00, 0x00 };
        BYTE ya[5] = { 0x68, 0x01, 0x00, 0x00, 0x00 };                              /* push 1 (ms) */
        g_tx_espera_ms = 0;
        int ok = escribir_bytes(0x00563CD0, rx_esp, rx_nue, 5, "en vivo: sin FF98")
              && escribir_bytes(0x004F0AA7, e4000, ya, 5, "en vivo: arranca con el GO")
              && escribir_bytes(0x005E8F67, e4000, ya, 5, "en vivo: el cartel ya");
        apuntar(ok ? "  [transmision] ★ EN VIVO: el que mira ve la carrera como un corredor más (piloto + FF4E en vivo, sin FF98)"
                   : "  [transmision] ⛔ en vivo: los sitios no son los esperados (queda a medias: revisar)");
        return;
    }

    static const BYTE c03_esp[7] = { 0xC6, 0x86, 0x03, 0x0C, 0x00, 0x00, 0x00 };   /* mov byte [esi+0xC03], 0 */
    static const BYTE c03_nue[7] = { 0xC6, 0x86, 0x03, 0x0C, 0x00, 0x00, 0x01 };   /*                     , 1 */
    static const BYTE tab_esp[6] = { 0x3A, 0x90, 0xE8, 0x4C, 0x90, 0x00 };          /* cmp dl, [eax+0x904CE8] */
    BYTE tab_nue[6] = { 0x3A, 0x90, 0, 0, 0, 0 };
    escribir_u32(tab_nue + 2, (DWORD)g_tx_tipos);
    static const BYTE tope_esp[3] = { 0x83, 0xF8, 0x04 };                            /* cmp eax, 4 */
    static const BYTE tope_nue[3] = { 0x83, 0xF8, 0x09 };                            /* cmp eax, 9 */
    static const BYTE esp_esp[5] = { 0x68, 0xA0, 0x0F, 0x00, 0x00 };                 /* push 4000 */
    static const BYTE env_esp[5] = { 0x68, 0xD0, 0x07, 0x00, 0x00 };                 /* push 2000 */
    static const BYTE car_esp[5] = { 0x68, 0xA0, 0x0F, 0x00, 0x00 };                 /* push 4000 (el cartel) */
    BYTE esp_nue[5] = { 0x68, 0, 0, 0, 0 }, env_nue[5] = { 0x68, 0, 0, 0, 0 };
    escribir_u32(esp_nue + 1, espera);
    escribir_u32(env_nue + 1, envio);

    /* las seis o ninguna: medio modo deja al que mira descartando todo (lo que pasó a las 20:37) */
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
#define TXV(va) (base + ((va) - 0x400000))
    if (memcmp(TXV(0x563C35), c03_esp, 7) || memcmp(TXV(0x563CE4), tab_esp, 6) || memcmp(TXV(0x563CED), tope_esp, 3)
            || memcmp(TXV(0x4F0AA7), esp_esp, 5) || memcmp(TXV(0x4F0AE7), env_esp, 5)
            || memcmp(TXV(0x5E8F67), car_esp, 5)) {
        apuntar("  [transmision] ⛔ los sitios no son los esperados: no se toca nada");
        return;
    }
#undef TXV
    int ok = escribir_bytes(0x00563C35, c03_esp, c03_nue, 7, "transmision C03")
          && escribir_bytes(0x00563CE4, tab_esp, tab_nue, 6, "transmision tipos")
          && escribir_bytes(0x00563CED, tope_esp, tope_nue, 3, "transmision tope")
          && escribir_bytes(0x004F0AA7, esp_esp, esp_nue, 5, "transmision espera")
          && escribir_bytes(0x004F0AE7, env_esp, env_nue, 5, "transmision envio")
          && escribir_bytes(0x005E8F67, car_esp, esp_nue, 5, "transmision cartel");
    if (ok)
        apuntar("  [transmision] ★ puesta: el que mira ve TODO (teclas, combos, impulsor, efectos) %u ms atrás; "
                "los que corren mandan cada %u ms", (unsigned)espera, (unsigned)envio);
}
