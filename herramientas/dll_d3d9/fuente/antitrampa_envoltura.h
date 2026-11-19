/* antitrampa_envoltura.h — lo que la dll escribe en el exe, anotado en UN solo lugar (18-nov-2026).
 *
 * Los módulos parchean el exe por ~30 caminos propios, todos con VirtualProtect (abrir · escribir · cerrar). Este
 * archivo se incluye justo después de <windows.h> y cambia VirtualProtect y VirtualAlloc por envolturas:
 *   · al ABRIR una página vigilada del exe, queda «en nuestras manos» y antitrampa.c no la juzga;
 *   · al CERRARLA, se copia de nuevo: lo que escribimos nosotros pasa a ser lo esperado;
 *   · cada VirtualAlloc ejecutable queda en una lista (nuestras cuevas no son memoria ajena).
 * Quien escriba el exe sin pasar por acá (un trainer desde otro proceso, una dll inyectada) cambia una página sin
 * copia nueva, y antitrampa.c lo ve. Mientras `g_at_ini` sea NULL todo pasa directo, como antes.
 */
#ifndef ANTITRAMPA_ENVOLTURA_H
#define ANTITRAMPA_ENVOLTURA_H

#define AT_PAGINA      4096
#define AT_CUEVAS_MAX  512

static BYTE *volatile g_at_ini;              /* la base del exe; NULL = apagado              */
static DWORD g_at_paginas;                   /* páginas de la imagen                          */
static BYTE *g_at_vigila;                    /* 1 = página de una sección de sólo lectura     */
static BYTE *g_at_copia;                     /* lo esperado, página por página                */
static volatile LONG *g_at_abiertas;         /* >0 = la tenemos abierta para escribir         */
static void *g_at_cueva_base[AT_CUEVAS_MAX];
static volatile LONG g_at_ncuevas;

static int at_es_escribible(DWORD prot)
{
    return (prot & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)) != 0;
}

static BOOL WINAPI at_virtual_protect(LPVOID dir, SIZE_T largo, DWORD nueva, PDWORD vieja)
{
    BOOL ok = VirtualProtect(dir, largo, nueva, vieja);
    BYTE *ini = g_at_ini;
    if (!ok || !ini || !largo || (BYTE *)dir < ini) return ok;
    DWORD p0 = (DWORD)((BYTE *)dir - ini) / AT_PAGINA;
    DWORD p1 = (DWORD)((BYTE *)dir + largo - 1 - ini) / AT_PAGINA;
    for (DWORD p = p0; p <= p1 && p < g_at_paginas; p++) {
        if (!g_at_vigila[p]) continue;
        if (at_es_escribible(nueva)) {
            InterlockedIncrement(&g_at_abiertas[p]);
        } else {
            CopyMemory(g_at_copia + (SIZE_T)p * AT_PAGINA, ini + (SIZE_T)p * AT_PAGINA, AT_PAGINA);
            if (InterlockedDecrement(&g_at_abiertas[p]) < 0) InterlockedExchange(&g_at_abiertas[p], 0);
        }
    }
    return ok;
}

static LPVOID WINAPI at_virtual_alloc(LPVOID dir, SIZE_T largo, DWORD tipo, DWORD prot)
{
    LPVOID r = VirtualAlloc(dir, largo, tipo, prot);
    if (r && (prot & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY))) {
        LONG i = InterlockedIncrement(&g_at_ncuevas) - 1;
        if (i < AT_CUEVAS_MAX) g_at_cueva_base[i] = r;
    }
    return r;
}

#define VirtualProtect at_virtual_protect
#define VirtualAlloc   at_virtual_alloc

#endif
