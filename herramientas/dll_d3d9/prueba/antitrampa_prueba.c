/* antitrampa_prueba.c — antitrampa.c sin el juego: el programa se vigila a SÍ MISMO (lo arma probar_antitrampa.py).
 *   · algo tocado ANTES de iniciar          -> «previo=1»
 *   · lo que escribimos con VirtualProtect  -> nada (es nuestro)
 *   · lo que se escribe por fuera (WriteProcessMemory, como un trainer) -> «codigo=…» con los bytes
 *   · memoria ejecutable propia / ajena     -> nada / «memoria=…»
 *   · un módulo «toolbit…» cargado          -> «modulo=…»
 * Sale con 0 si todo dio lo esperado. */
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include "../fuente/antitrampa_envoltura.h"

static char g_carpeta[MAX_PATH];
static void apuntar(const char *formato, ...)
{
    char linea[512];
    va_list a;
    va_start(a, formato);
    wvsprintfA(linea, formato, a);
    va_end(a);
    printf("    log: %s\n", linea);
}

#include "../fuente/antitrampa.c"

__attribute__((aligned(4096))) static const volatile BYTE g_previo[AT_PAGINA] = { 1 };
__attribute__((aligned(4096))) static const volatile BYTE g_ajeno[AT_PAGINA] = { 2 };
__attribute__((aligned(4096))) static const volatile BYTE g_propio[AT_PAGINA] = { 3 };

static int g_mal;
static void ok(int cond, const char *que) { printf("  %s %s\n", cond ? "ok  " : "MAL ", que); if (!cond) g_mal++; }

static int cola_tiene(const char *texto)
{
    int si = 0;
    EnterCriticalSection(&g_at_cs);
    for (int i = g_at_cola_ini; i != g_at_cola_fin; i = (i + 1) % AT_RENGLONES)
        if (at_busca(g_at_cola[i], (char *)texto)) si = 1;
    LeaveCriticalSection(&g_at_cs);
    return si;
}

/* como un trainer (ToolBit): VirtualProtectEx + WriteProcessMemory, sin pasar por la envoltura */
static int escribir_por_fuera(const volatile BYTE *donde, const BYTE *bytes, SIZE_T n)
{
    SIZE_T escritos = 0;
    DWORD viejo;
    HANDLE yo = GetCurrentProcess();
    if (!VirtualProtectEx(yo, (LPVOID)donde, n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    WriteProcessMemory(yo, (LPVOID)donde, bytes, n, &escritos);
    VirtualProtectEx(yo, (LPVOID)donde, n, viejo, &viejo);
    return escritos == n;
}

int main(int argc, char **argv)
{
    static const BYTE gancho[5] = { 0xE9, 0x11, 0x22, 0x33, 0x44 };
    char esperado[64];
    GetTempPathA(MAX_PATH, g_carpeta);
    if (argc > 1 && !lstrcmpA(argv[1], "limpio")) {
        antitrampa_iniciar();
        ok(g_at_previo == 0, "revés: sin tocar nada, el exe en memoria es igual al del disco");
        return g_mal ? 1 : 0;
    }
    ok(escribir_por_fuera(g_previo + 16, gancho, 5), "escribo «antes que nosotros», como un trainer");
    antitrampa_iniciar();
    ok(g_at_ini != NULL, "se inició y vigila el exe");
    ok(g_at_previo == 1, "previo: UNA página distinta del disco");
    ok(g_at_previo_va == (int)(DWORD)(g_previo + 16), "previo: en la dirección tocada");

    DWORD viejo;
    VirtualProtect((LPVOID)g_propio, 8, PAGE_EXECUTE_READWRITE, &viejo);
    ((BYTE *)g_propio)[8] = 0x90;
    VirtualProtect((LPVOID)g_propio, 8, viejo, &viejo);
    at_revisar_codigo();
    at_revisar_codigo();
    ok(!cola_tiene("codigo="), "revés: lo escrito con VirtualProtect (nuestro) no se informa");

    ok(escribir_por_fuera(g_ajeno + 100, gancho, 5), "escribo por fuera, como un trainer");
    at_revisar_codigo();
    ok(!cola_tiene("codigo="), "una sola pasada distinta todavía no se informa");
    at_revisar_codigo();
    wsprintfA(esperado, "codigo=0x%08X paginas=1 bytes=E9_11_22_33_44", (DWORD)(g_ajeno + 100));
    ok(cola_tiene(esperado), "lo escrito por fuera se informa con dirección y bytes");
    at_revisar_codigo();
    int n = 0;
    for (int i = g_at_cola_ini; i != g_at_cola_fin; i = (i + 1) % AT_RENGLONES) n += !!at_busca(g_at_cola[i], "codigo=");
    ok(n == 1, "y una sola vez");

    at_revisar_memoria();
    int antes = g_at_ajenas_informadas;
    VirtualAlloc(NULL, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);      /* la envoltura: nuestra */
    at_revisar_memoria();
    ok(g_at_ajenas_informadas == antes, "revés: una cueva nuestra no es memoria ajena");
#undef VirtualAlloc
    BYTE *ajena = (BYTE *)VirtualAlloc(NULL, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    at_revisar_memoria();
    ok(ajena && g_at_ajenas_informadas == antes + 1 && cola_tiene("memoria="), "una reserva ajena se informa");

    if (argc > 1) {
        ok(LoadLibraryA(argv[1]) != NULL, "cargo el módulo de prueba");
        at_revisar_modulos();
        ok(cola_tiene("modulo=toolbit_prueba.dll"), "un módulo «toolbit» se informa");
    }
    printf(g_mal ? "\n%d MAL\n" : "\ntodo bien\n", g_mal);
    return g_mal ? 1 : 0;
}
