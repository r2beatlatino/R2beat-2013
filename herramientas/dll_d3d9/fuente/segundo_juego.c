/* segundo_juego.c — (102) abrir el juego DOS veces: que el segundo avise «R2Beat se está ejecutando.» y no reviente
 *                    (la caja negra «índice fuera de rango desde 0x433401», 22-oct-2026, CAJAS_NEGRAS_2026-10-22.md §2.7)
 *
 * ★ POR QUÉ: 26 cajas negras en prod (17→22-oct), 23 jugadores, todas con la pila 00402D24 004085B0 00800001 …
 *   Es lo PRIMERO que hace el juego al arrancar (0x402CF0, a los ~60 ms):
 *       CreateMutexA(0, 1, "R2BEAT_ONLINE")
 *       si GetLastError() == 0xB7 (ya hay otro juego abierto):
 *           MessageBoxA(0, texto nº 1 de la tabla 0x9D50C0, "ERROR", 0)   ← «R2Beat se está ejecutando.» (system.csv)
 *           CloseHandle; return 0  (el juego se va)
 *   Pero a los 60 ms la tabla de textos todavía NO se cargó: 0x433380 la ve vacía y cierra el juego por «índice fuera
 *   de rango» (0x433401) en vez de mostrar el cartel. El segundo juego se iba a ir igual; el primero sigue jugando.
 *   Reproducido en local: un juego abierto y un segundo en la misma PC = la firma exacta de prod.
 *
 *       0x402D18  6A 01               push 1                 ← el argumento de 0x433380 (thiscall, ret 4)
 *       0x402D1A  B9 C0 50 9D 00      mov ecx, 0x9D50C0
 *       0x402D1F  E8 5C 06 03 00      call 0x433380
 *       0x402D24  50                  push eax               ← el texto para MessageBoxA
 *   ⇒ los 12 bytes de 0x402D18 pasan a  mov eax, <el texto de acá>  + 7 nop  (sin el `push 1`, que sin la llamada
 *     quedaría en la pila y el `ret` de 0x402D3B volvería a 1).  [segundo_juego] activo=0 lo apaga. */

static const char g_sj_texto[] = "R2Beat se est\xE1 ejecutando.";      /* system.csv nº 1, en la página 1252 del juego */

static void segundo_juego_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("segundo_juego", "activo", 1, ini)) {
        apuntar("  [segundo_juego] APAGADO ([segundo_juego] activo=0)");
        return;
    }
    static const BYTE esperado[12] = { 0x6A, 0x01, 0xB9, 0xC0, 0x50, 0x9D, 0x00, 0xE8, 0x5C, 0x06, 0x03, 0x00 };
    BYTE nuevo[12] = { 0xB8, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
    DWORD t = (DWORD)g_sj_texto;
    for (int k = 0; k < 4; k++) nuevo[1 + k] = (BYTE)(t >> (8 * k));
    if (escribir_bytes(0x402D18, esperado, nuevo, 12, "segundo_juego: el cartel de «ya está abierto»"))
        apuntar("  [segundo_juego] ★ abrir el juego dos veces: el segundo avisa «R2Beat se está ejecutando.» en vez de"
                " cerrarse por «índice fuera de rango» (0x402D18)");
}
