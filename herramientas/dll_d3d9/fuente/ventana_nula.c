/* ventana_nula.c — (99) «Crear Sala» antes de que el lobby termine de armarse: no cerrar una ventana que no existe
 *                   (la caja negra 0x6584E1, 22-oct-2026, CAJAS_NEGRAS_2026-10-22.md §2.4)
 *
 * ★ POR QUÉ: 89 cajas negras de 77 jugadores en prod (17→22-oct), «escribe 0xAC» en 0x6584E1, casi todas entre 4 y
 *   13 s después de entrar al canal. El botón «Crear Sala» de la pantalla Carreras (objeto con [obj]=0x4A7620 y
 *   [obj+4]=0x4A51B0; el clic lo atiende 0x4A3D30) llama a 0x4A15B0, que ANTES de abrir el diálogo cierra la ventana
 *   [[0x9314C4]+0x13E44] con 0x6584D0 (0x647C90(ventana, 0) y [ventana+0xAC] = 0). Esa ventana la arma la escena del
 *   lobby cuando termina de cargar su interfaz: medido en local, NULA desde los 3 s hasta los 15-27 s del arranque.
 *   En una máquina lenta la pantalla Carreras ya responde y la ventana todavía no existe ⇒ 0x6584D0(NULL) ⇒ cierre.
 *   Ninguno de los 8 lectores de +0x13E44 mira si es nula; los devs la dieron por armada.
 *
 *   Los dos `call 0x6584D0` que la toman de la escena (los otros 6 lectores son métodos de la propia escena, que sólo
 *   corren con ella armada):
 *       0x4A15CD  (0x4A15B0: «Crear Sala»)          mov ecx, [[0x9314C4]+0x13E44]; call 0x6584D0
 *       0x4A341A  (el mismo patrón en la misma pantalla)
 *   ⇒ van a vn_cerrar: si la ventana es nula no hay nada que cerrar y se sigue (el diálogo de Crear Sala se abre igual);
 *     si no, la de fábrica.  [ventana_nula] activo=0 lo apaga. */

typedef void (__attribute__((thiscall)) *F_VN_CERRAR)(void *ventana);                                   /* 0x6584D0 */
static BYTE *g_vn_base = NULL;
static int   g_vn_salvadas = 0;

static void __fastcall vn_cerrar(void *ventana, void *nada)
{
    (void)nada;
    if (!ventana) {
        if (g_vn_salvadas++ < 5)
            apuntar("  [ventana_nula] ★ la ventana a cerrar todavía no existe (el lobby se está armando): no se cierra"
                    " nada y se sigue (sin esto: la caja negra 0x6584E1)");
        return;
    }
    ((F_VN_CERRAR)(g_vn_base + (0x6584D0 - 0x400000)))(ventana);
}

static void ventana_nula_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("ventana_nula", "activo", 1, ini)) {
        apuntar("  [ventana_nula] APAGADO ([ventana_nula] activo=0)");
        return;
    }
    g_vn_base = (BYTE *)GetModuleHandleA(NULL);
    static const DWORD SITIOS[2] = { 0x4A15CD, 0x4A341A };
    int ok = 1;
    for (int i = 0; i < 2 && ok; i++) {
        DWORD va = SITIOS[i];
        BYTE esp[5] = { 0xE8 }, nue[5] = { 0xE8 };
        DWORD r1 = 0x6584D0 - (va + 5);
        DWORD r2 = (DWORD)vn_cerrar - (DWORD)(g_vn_base + (va - 0x400000) + 5);
        for (int k = 0; k < 4; k++) { esp[1 + k] = (BYTE)(r1 >> (8 * k)); nue[1 + k] = (BYTE)(r2 >> (8 * k)); }
        ok = escribir_bytes(va, esp, nue, 5, "ventana_nula: cerrar la ventana del lobby");
    }
    if (ok) apuntar("  [ventana_nula] ★ «Crear Sala» ya no se cae si el lobby todavía se está armando (0x4A15CD, 0x4A341A)");
}
