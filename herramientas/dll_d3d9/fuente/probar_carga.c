/* Cargador minimo de 32 bits: comprueba que el proxy ARRANCA de verdad.
 *
 * Ejercita DllMain (cargar el d3d9 real de System32, leer el ini, abrir el log,
 * parchear la IAT) y Direct3DCreate9. No llega a CreateDevice: eso lo prueba el juego.
 *
 * ⚠ Este exe NO importa d3d9.dll en su tabla, asi que `parchear_iat` devuelve NULL y
 *   el log dice "NO enganchado todavia". Eso es lo ESPERADO aca; en el juego tiene que
 *   decir lo contrario, y esa diferencia es justamente lo que prueba que el enganche
 *   depende del exe y no de la suerte.
 *
 *   ../_zig/zig-x86_64-windows-0.16.0/zig.exe cc -target x86-windows-gnu -O2 \
 *       -o probar_carga.exe probar_carga.c -lkernel32 -luser32
 */
#include <windows.h>
#include <stdio.h>

typedef void *(WINAPI *CREAR9)(UINT);

int main(void)
{
    /* sin barras: el cargador de Windows busca primero en la carpeta del exe, que es
     * donde esta la dll que queremos probar (y NO la de System32). */
    HMODULE m = LoadLibraryA("d3d9.dll");
    if (!m) {
        printf("[X] no cargo la dll (error %lu)\n", GetLastError());
        return 1;
    }
    printf("[OK] DllMain corrio sin matar el proceso\n");

    CREAR9 f = (CREAR9)GetProcAddress(m, "Direct3DCreate9");
    if (!f) {
        printf("[X] no exporta Direct3DCreate9\n");
        return 1;
    }
    printf("[OK] exporta Direct3DCreate9 (sin decorar)\n");

    void *fab = f(32);
    printf("%s Direct3DCreate9(32) -> %p\n", fab ? "[OK]" : "[X]", fab);
    return fab ? 0 : 1;
}
