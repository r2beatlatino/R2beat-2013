/* invitar.c — «Invitar a los del vestíbulo» para TODOS (12-oct-2026).
 *
 * El cartel « %d Número (%s) Sala le ha enviado una invitación» (FF52, RX 0x5CFD60) tiene una última compuerta:
 *
 *   005CFECF  mov  ecx, [0x9314E0]          ; la cuenta
 *   005CFED5  push 1
 *   005CFED7  call 0x488830                 ; ¿tiene OTORGADA la máscara 0x0001? (= la misión «Tutorial»)
 *   005CFEDC  test al, al
 *   005CFEDE  je   0x5CFF31                 ; ⛔ si no: el cartel no sale, sin aviso
 *
 * Medido el 12-oct con dos clientes: el server le mandó el FF52 a jugador5 (en el vestíbulo, mismo canal) y no le
 * salió nada — su login trae los nibbles de misiones en 0, o sea la máscara 1 sin otorgar. En nuestro server
 * cualquiera entra a cualquier sala (anonimo03), así que el `je` se apaga: 74 51 -> 90 90.
 * ⚠ No se otorga la máscara desde el server: le marcaría el Tutorial como jugado en el panel de misiones.
 * Ver documentacion/INVITAR_VESTIBULO.md §3. Se INCLUYE desde d3d9_proxy.c (después de `escribir_bytes`).
 */

static void invitar_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("invitar", "todos", 1, ini)) {
        apuntar("  [invitar] apagado ([invitar] todos=0): la invitación sólo le sale al que hizo el Tutorial");
        return;
    }
    static const BYTE esp[8] = { 0xE8, 0x54, 0x89, 0xEB, 0xFF, 0x84, 0xC0, 0x74 };   /* call 0x488830 · test · je */
    static const BYTE esp_je[2] = { 0x74, 0x51 };
    static const BYTE nue_je[2] = { 0x90, 0x90 };
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    if (!base || memcmp(base + (0x005CFED7 - 0x400000), esp, 8) != 0) {
        apuntar("  [invitar] ⛔ en 0x005CFED7 no está la compuerta esperada: no se toca nada");
        return;
    }
    if (escribir_bytes(0x005CFEDE, esp_je, nue_je, 2, "invitar a todos"))
        apuntar("  [invitar] ★ puesto: el cartel de invitación le sale a todos (sin pedir el Tutorial)");
}
