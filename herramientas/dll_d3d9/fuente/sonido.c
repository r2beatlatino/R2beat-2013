/* sonido.c — (98) MÁS LUGAR PARA LOS SONIDOS: los canales de Miles de 2000 a 6000 (22-oct-2026)
 *
 * ★ POR QUÉ (la caja negra 0x5738E7, `documentacion/CAJAS_NEGRAS_2026-10-22.md` §2.2-§2.3): el COOPERATIVO carga de una
 *   el BGM y TODOS los `<EFFECT>` de sus 3 canciones como samples de Miles. El juego abre Miles con 2000 canales
 *   (= samples que se pueden reservar): de sobra para las canciones de fábrica (mediana 6 sonidos), pero las importadas
 *   traen uno por nota («Luz de Luna» 685 = 756) y con eso el BGM de la canción siguiente queda con handle 0 y la sala
 *   entera se cae en 0x5738D0. Reproducido en local con la sala de prod (6 de 6 caídos) y medido con una sonda.
 *
 *   El juego, al armar el sonido (0x6431B0, cuando arranca, DESPUÉS de este DllMain):
 *       0x6431C4  68 D0 07 00 00   push 0x7D0          ← 2000 canales
 *       0x6431C9  6A 01            push 1              (DIG_MIXER_CHANNELS)
 *       0x6431CB  FF 15 EC 34 87 00 call AIL_set_preference
 *       ...       AIL_open_digital_driver(44100, 16, 2, 0)
 *   ⇒ se cambia el inmediato por [sonido] canales (6000 por defecto). Como d3d9.dll es un import FIJO del exe, esto
 *     corre antes de que el juego abra el sonido: no hay que cerrar ni reabrir el driver.
 *   ★ El otro server (SpaceWander, `rnr_plugin/Extra.dll`, `[Sonido] Canales`) usa el mismo número, 6000, pero
 *     reabriendo el driver ya abierto. El 2019 sin optimizar también abre con 2000 (0xF0F608).
 *   Peor caso con 6000: tres canciones de 756 + sus BGM + lo del lobby ≈ 5000. El tope del server (97,
 *   `CHASE_EFECTOS_TOPE`) sigue de red para los clientes con la dll vieja.
 *
 *   [sonido] canales=6000 en d3d9_proxy.ini (2000..14000; 0 = como de fábrica). */

static void sonido_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    int n = (int)GetPrivateProfileIntA("sonido", "canales", 6000, ini);
    if (n == 0) {
        apuntar("  [sonido] canales=0: Miles con los 2000 canales de fábrica");
        return;
    }
    if (n < 2000) n = 2000;
    if (n > 14000) n = 14000;
    static const BYTE esperado[5] = { 0x68, 0xD0, 0x07, 0x00, 0x00 };
    BYTE nuevo[5] = { 0x68, (BYTE)n, (BYTE)(n >> 8), 0x00, 0x00 };
    if (escribir_bytes(0x6431C4, esperado, nuevo, 5, "sonido: canales de Miles"))
        apuntar("  [sonido] ★ Miles con %d canales (de fábrica 2000): el cooperativo no se queda sin lugar", n);
}
