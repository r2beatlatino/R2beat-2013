/* antitrampa.c — el cliente mira si alguien le tocó el exe y se lo dice al server (18-nov-2026).
 *
 * Qué mira (todo de sólo leer; nunca cierra el juego ni toca nada):
 *   1 · LO PREVIO: al cargarse, cada página de sólo lectura del exe (código, constantes, la tabla de importaciones)
 *       contra el R2Beat.exe del disco. Una diferencia = alguien lo cambió ANTES que nosotros (otra dll de arranque).
 *   2 · EL CÓDIGO: cada 5 s, cada página contra su copia. Lo nuestro se re-copia en antitrampa_envoltura.h; lo que
 *       cambie sin pasar por ahí (un trainer externo con WriteProcessMemory, una dll inyectada) se ve dos pasadas
 *       seguidas y se informa con la dirección y los bytes (p. ej. el `E9` de un gancho).
 *   3 · MÓDULOS conocidos de trampas cargados en el proceso (ToolBit, R2Mods, Cheat Engine…).
 *   4 · MEMORIA EJECUTABLE privada que no reservamos nosotros (las cuevas de un trainer). Puede dar falsos positivos
 *       (superposiciones, controladores): el server sólo lo REGISTRA por defecto.
 *   5 · un DEPURADOR enganchado.
 * Y el md5 del R2Beat.exe del disco, para que el server lo compare con el de la receta.
 *
 * El informe va por el mismo camino que la caja negra: el reporte de errores del juego (0x404440 → FF59), una línea
 * «R2AT …» por hallazgo, desde el hilo del juego, ya en el lobby. ⚠ Es un informe, no una prueba: un cliente
 * recompilado puede mentir. Lo que no se puede falsear lo comprueba el server solo (servidor/antitrampa.py).
 * [antitrampa] activo=0 en d3d9_proxy.ini lo apaga (y el server lo ve: no llega el «hola»).
 * Se INCLUYE desde d3d9_proxy.c (antes de cajanegra.c, que llama a at_enviar_pendiente).
 */
#include <tlhelp32.h>

#define AT_RENGLONES 16
#define AT_LARGO     180

static CRITICAL_SECTION g_at_cs;
static char g_at_cola[AT_RENGLONES][AT_LARGO];
static int g_at_cola_ini, g_at_cola_fin;
static BYTE *g_at_sospecha;                  /* 1 = distinta en la pasada anterior        */
static BYTE *g_at_informada;                 /* 1 = ya se le dijo al server               */
static int g_at_previo = -1, g_at_previo_va;
static char g_at_md5[33];
static DWORD g_at_ultimo_envio;
static char g_at_modulos_vistos[512];

static const char *const AT_MODULOS[] = {
    "toolbit", "r2mods", "d3dref9", "r2tr.", "n2hock", "speedhack", "cheatengine", "vehdebug", "dbk32", "dbk64",
};

static char *at_busca(char *s, const char *sub)
{
    int m = lstrlenA(sub);
    for (; *s; s++) { int i = 0; while (i < m && s[i] == sub[i]) i++; if (i == m) return s; }
    return NULL;
}

/* cuántos bytes iguales hay al principio (AT_PAGINA = la página entera) */
static SIZE_T at_iguales(const BYTE *a, const BYTE *b)
{
    const DWORD *x = (const DWORD *)a, *y = (const DWORD *)b;
    SIZE_T i = 0;
    while (i < AT_PAGINA / 4 && x[i] == y[i]) i++;
    i *= 4;
    while (i < AT_PAGINA && a[i] == b[i]) i++;
    return i;
}

static void at_encolar(const char *formato, ...)
{
    char linea[AT_LARGO];
    va_list args;
    va_start(args, formato);
    int n = wvsprintfA(linea, formato, args);
    va_end(args);
    if (n <= 0) return;
    apuntar("  [antitrampa] %s", linea);
    EnterCriticalSection(&g_at_cs);
    int sig = (g_at_cola_fin + 1) % AT_RENGLONES;
    if (sig != g_at_cola_ini) {                                  /* llena: se pierde la más nueva, no la «hola» */
        lstrcpynA(g_at_cola[g_at_cola_fin], linea, AT_LARGO);
        g_at_cola_fin = sig;
    }
    LeaveCriticalSection(&g_at_cs);
}

/* (hilo del juego, desde cn_enviar_pendiente) de a un renglón por segundo, ya en el lobby */
static void at_enviar_pendiente(void)
{
    if (!g_at_ini || g_at_cola_ini == g_at_cola_fin) return;
    if (GetTickCount() - g_at_ultimo_envio < 1000) return;
    BYTE *base = g_at_ini;
    BYTE *red = *(BYTE **)(base + (0x009314D0 - 0x400000));
    BYTE *cuenta = *(BYTE **)(base + (0x009314E0 - 0x400000));
    if (!red || !cuenta || (*(DWORD *)(red + 0x21B54) & 2) != 2 || !*(DWORD *)(cuenta + 0x7C)) return;
    char linea[AT_LARGO];
    EnterCriticalSection(&g_at_cs);
    lstrcpyA(linea, g_at_cola[g_at_cola_ini]);
    g_at_cola_ini = (g_at_cola_ini + 1) % AT_RENGLONES;
    LeaveCriticalSection(&g_at_cs);
    g_at_ultimo_envio = GetTickCount();
    ((void (__cdecl *)(const char *))(base + (0x00404440 - 0x400000)))(linea);
}

static IMAGE_NT_HEADERS32 *at_cabecera(BYTE *img)
{
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)img;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;
    IMAGE_NT_HEADERS32 *nt = (IMAGE_NT_HEADERS32 *)(img + dos->e_lfanew);
    return nt->Signature == IMAGE_NT_SIGNATURE ? nt : NULL;
}

static BYTE *at_leer_archivo(const char *ruta, DWORD *tam)
{
    HANDLE h = CreateFileA(ruta, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return NULL;
    *tam = GetFileSize(h, NULL);
    BYTE *b = (*tam && *tam != INVALID_FILE_SIZE) ? (BYTE *)HeapAlloc(GetProcessHeap(), 0, *tam) : NULL;
    DWORD leidos = 0;
    if (b && (!ReadFile(h, b, *tam, &leidos, NULL) || leidos != *tam)) { HeapFree(GetProcessHeap(), 0, b); b = NULL; }
    CloseHandle(h);
    return b;
}

/* 1 · las páginas vigiladas contra el exe del disco, armado como lo arma el cargador. -1 si no se pudo comparar. */
static int at_comparar_con_disco(BYTE *archivo, DWORD tam, int *primera_va)
{
    IMAGE_NT_HEADERS32 *nt = at_cabecera(archivo), *nt_mem = at_cabecera(g_at_ini);
    if (!nt || !nt_mem || nt->OptionalHeader.SizeOfImage != nt_mem->OptionalHeader.SizeOfImage) return -1;
    if ((DWORD)g_at_ini != nt->OptionalHeader.ImageBase) return -1;          /* reubicado: no se compara */
    IMAGE_DATA_DIRECTORY iat = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IAT];
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    int distintas = 0;
    BYTE pagina[AT_PAGINA];
    for (DWORD p = 0; p < g_at_paginas; p++) {
        if (!g_at_vigila[p]) continue;
        DWORD rva = p * AT_PAGINA;
        if (iat.Size && rva + AT_PAGINA > iat.VirtualAddress && rva < iat.VirtualAddress + iat.Size) continue;
        ZeroMemory(pagina, AT_PAGINA);
        for (int i = 0; i < nt->FileHeader.NumberOfSections; i++) {
            /* el cargador copia hasta el final de la página de la sección, con el relleno del archivo incluido */
            DWORD alin = (s[i].Misc.VirtualSize + AT_PAGINA - 1) & ~(DWORD)(AT_PAGINA - 1);
            DWORD crudo = s[i].SizeOfRawData < alin ? s[i].SizeOfRawData : alin;
            if (rva < s[i].VirtualAddress || rva >= s[i].VirtualAddress + crudo) continue;
            DWORD desde = rva - s[i].VirtualAddress, n = crudo - desde;
            if (n > AT_PAGINA) n = AT_PAGINA;
            if (s[i].PointerToRawData + desde + n <= tam) CopyMemory(pagina, archivo + s[i].PointerToRawData + desde, n);
        }
        SIZE_T igual = at_iguales(pagina, g_at_ini + rva);
        if (igual != AT_PAGINA && !distintas++) *primera_va = (int)(0x400000 + rva + igual);
    }
    return distintas;
}

static void at_md5(const BYTE *datos, DWORD tam)
{
    typedef BOOL (WINAPI *ACQ)(ULONG_PTR *, LPCSTR, LPCSTR, DWORD, DWORD);
    typedef BOOL (WINAPI *CRE)(ULONG_PTR, UINT, ULONG_PTR, DWORD, ULONG_PTR *);
    typedef BOOL (WINAPI *DAT)(ULONG_PTR, const BYTE *, DWORD, DWORD);
    typedef BOOL (WINAPI *PAR)(ULONG_PTR, DWORD, BYTE *, DWORD *, DWORD);
    typedef BOOL (WINAPI *DES)(ULONG_PTR);
    typedef BOOL (WINAPI *REL)(ULONG_PTR, DWORD);
    lstrcpyA(g_at_md5, "?");
    HMODULE a = LoadLibraryA("advapi32.dll");
    if (!a) return;
    ACQ acq = (ACQ)GetProcAddress(a, "CryptAcquireContextA");
    CRE cre = (CRE)GetProcAddress(a, "CryptCreateHash");
    DAT dat = (DAT)GetProcAddress(a, "CryptHashData");
    PAR par = (PAR)GetProcAddress(a, "CryptGetHashParam");
    DES des = (DES)GetProcAddress(a, "CryptDestroyHash");
    REL rel = (REL)GetProcAddress(a, "CryptReleaseContext");
    ULONG_PTR prov = 0, hash = 0;
    if (acq && cre && dat && par && des && rel && acq(&prov, NULL, NULL, 1 /*PROV_RSA_FULL*/, 0xF0000000 /*VERIFYCONTEXT*/)) {
        BYTE r[16];
        DWORD n = sizeof(r);
        if (cre(prov, 0x8003 /*CALG_MD5*/, 0, 0, &hash)) {
            if (dat(hash, datos, tam, 0) && par(hash, 2 /*HP_HASHVAL*/, r, &n, 0) && n == 16)
                for (int i = 0; i < 16; i++) wsprintfA(g_at_md5 + 2 * i, "%02x", r[i]);
            des(hash);
        }
        rel(prov, 0);
    }
}

/* 2 · el código: dos pasadas seguidas distinta y sin estar en nuestras manos = alguien la tocó */
static void at_revisar_codigo(void)
{
    int nuevas = 0, primera = 0;
    char bytes[3 * 8 + 1];
    bytes[0] = 0;
    BYTE *fin_region = NULL;
    int legible = 0;
    for (DWORD p = 0; p < g_at_paginas; p++) {
        if (!g_at_vigila[p]) continue;
        BYTE *mem = g_at_ini + (SIZE_T)p * AT_PAGINA;
        if (mem >= fin_region) {
            MEMORY_BASIC_INFORMATION mbi;
            if (!VirtualQuery(mem, &mbi, sizeof(mbi))) return;
            fin_region = (BYTE *)mbi.BaseAddress + mbi.RegionSize;
            legible = mbi.State == MEM_COMMIT && !(mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD));
        }
        if (!legible || g_at_abiertas[p] > 0) continue;
        BYTE *esp = g_at_copia + (SIZE_T)p * AT_PAGINA;
        SIZE_T igual = at_iguales(esp, mem);
        if (igual == AT_PAGINA) { g_at_sospecha[p] = 0; g_at_informada[p] = 0; continue; }
        if (!g_at_sospecha[p]) { g_at_sospecha[p] = 1; continue; }
        if (g_at_informada[p] || g_at_abiertas[p] > 0) continue;
        g_at_informada[p] = 1;
        if (!nuevas++) {
            primera = (int)(0x400000 + p * AT_PAGINA + igual);
            int k = 0;
            for (int i = 0; i < 8 && igual + i < AT_PAGINA; i++)
                k += wsprintfA(bytes + k, i ? "_%02X" : "%02X", mem[igual + i]);
        }
    }
    if (nuevas) at_encolar("R2AT codigo=0x%08X paginas=%d bytes=%s", primera, nuevas, bytes);
}

/* 3 · módulos conocidos, cada uno una sola vez */
static void at_revisar_modulos(void)
{
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, 0);
    if (snap == INVALID_HANDLE_VALUE) return;
    MODULEENTRY32 m;
    m.dwSize = sizeof(m);
    for (BOOL ok = Module32First(snap, &m); ok; ok = Module32Next(snap, &m)) {
        char nombre[MAX_MODULE_NAME32 + 1];
        lstrcpynA(nombre, m.szModule, sizeof(nombre));
        CharLowerA(nombre);
        for (int i = 0; i < (int)(sizeof(AT_MODULOS) / sizeof(AT_MODULOS[0])); i++) {
            if (!at_busca(nombre, AT_MODULOS[i])) continue;
            if (at_busca(g_at_modulos_vistos, nombre)) break;
            if (lstrlenA(g_at_modulos_vistos) + lstrlenA(nombre) + 2 < (int)sizeof(g_at_modulos_vistos)) {
                lstrcatA(g_at_modulos_vistos, nombre);
                lstrcatA(g_at_modulos_vistos, "|");
            }
            for (char *c = nombre; *c; c++) if (*c == ' ' || *c == '=') *c = '_';
            at_encolar("R2AT modulo=%s", nombre);
            break;
        }
    }
    CloseHandle(snap);
}

/* 4 · memoria ejecutable privada que no es nuestra */
static int g_at_ajenas_informadas;
static void at_revisar_memoria(void)
{
    if (g_at_ncuevas > AT_CUEVAS_MAX) return;                    /* la lista se llenó: no se puede saber */
    int ajenas = 0;
    DWORD primera = 0;
    BYTE *dir = (BYTE *)0x10000;
    MEMORY_BASIC_INFORMATION mbi;
    while ((DWORD)dir < 0x7FFE0000 && VirtualQuery(dir, &mbi, sizeof(mbi))) {
        if (mbi.State == MEM_COMMIT && mbi.Type == MEM_PRIVATE
            && (mbi.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY))) {
            int nuestra = 0;
            for (LONG i = 0; i < g_at_ncuevas && !nuestra; i++)
                nuestra = g_at_cueva_base[i] == mbi.AllocationBase;
            if (!nuestra && !ajenas++) primera = (DWORD)mbi.BaseAddress;
        }
        BYTE *sig = (BYTE *)mbi.BaseAddress + mbi.RegionSize;
        if (sig <= dir) break;
        dir = sig;
    }
    if (ajenas > g_at_ajenas_informadas) {
        g_at_ajenas_informadas = ajenas;
        at_encolar("R2AT memoria=0x%08X regiones=%d", primera, ajenas);
    }
}

static DWORD WINAPI at_hilo(LPVOID nada)
{
    (void)nada;
    char exe[MAX_PATH];
    DWORD tam = 0;
    BYTE *archivo = GetModuleFileNameA(NULL, exe, MAX_PATH) ? at_leer_archivo(exe, &tam) : NULL;
    if (archivo) {
        at_md5(archivo, tam);
        HeapFree(GetProcessHeap(), 0, archivo);
    }
    if (g_at_previo > 0)
        at_encolar("R2AT v=1 exe=%s previo=%d previo_va=0x%08X", g_at_md5, g_at_previo, g_at_previo_va);
    else
        at_encolar("R2AT v=1 exe=%s previo=%d", g_at_md5, g_at_previo);
    int depurador = 0;
    for (DWORD vuelta = 0;; vuelta++) {
        Sleep(5000);
        at_revisar_codigo();
        if (vuelta % 3 == 0) at_revisar_modulos();
        if (vuelta % 6 == 0) at_revisar_memoria();
        if (!depurador && IsDebuggerPresent()) { depurador = 1; at_encolar("R2AT depurador=1"); }
    }
    return 0;
}

/* (DllMain, lo más temprano posible: ANTES de que cualquier módulo parchee) */
static void antitrampa_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("antitrampa", "activo", 1, ini)) {
        apuntar("  [antitrampa] apagado ([antitrampa] activo=0)");
        return;
    }
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS32 *nt = base ? at_cabecera(base) : NULL;
    if (!nt) return;
    DWORD paginas = (nt->OptionalHeader.SizeOfImage + AT_PAGINA - 1) / AT_PAGINA;
    HANDLE heap = GetProcessHeap();
    g_at_vigila = (BYTE *)HeapAlloc(heap, HEAP_ZERO_MEMORY, paginas);
    g_at_sospecha = (BYTE *)HeapAlloc(heap, HEAP_ZERO_MEMORY, paginas);
    g_at_informada = (BYTE *)HeapAlloc(heap, HEAP_ZERO_MEMORY, paginas);
    g_at_abiertas = (volatile LONG *)HeapAlloc(heap, HEAP_ZERO_MEMORY, paginas * sizeof(LONG));
    g_at_copia = (BYTE *)HeapAlloc(heap, 0, (SIZE_T)paginas * AT_PAGINA);
    if (!g_at_vigila || !g_at_sospecha || !g_at_informada || !g_at_abiertas || !g_at_copia) {
        apuntar("  [antitrampa] ⛔ sin memoria para la copia del exe: apagado");
        return;
    }
    int vigiladas = 0;
    IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
    for (int i = 0; i < nt->FileHeader.NumberOfSections; i++) {
        if (s[i].Characteristics & IMAGE_SCN_MEM_WRITE) continue;
        DWORD p0 = s[i].VirtualAddress / AT_PAGINA;
        DWORD p1 = (s[i].VirtualAddress + s[i].Misc.VirtualSize + AT_PAGINA - 1) / AT_PAGINA;
        for (DWORD p = p0; p < p1 && p < paginas; p++) {
            g_at_vigila[p] = 1;
            CopyMemory(g_at_copia + (SIZE_T)p * AT_PAGINA, base + (SIZE_T)p * AT_PAGINA, AT_PAGINA);
            vigiladas++;
        }
    }
    g_at_paginas = paginas;
    InitializeCriticalSection(&g_at_cs);
    g_at_ini = base;                                             /* desde acá la envoltura anota */
    char exe[MAX_PATH];
    DWORD tam = 0;
    BYTE *archivo = GetModuleFileNameA(NULL, exe, MAX_PATH) ? at_leer_archivo(exe, &tam) : NULL;
    if (archivo) {
        g_at_previo = at_comparar_con_disco(archivo, tam, &g_at_previo_va);
        HeapFree(heap, 0, archivo);
    }
    apuntar("  [antitrampa] ★ vigilo %d páginas de sólo lectura del exe; contra el disco: %d distintas%s",
            vigiladas, g_at_previo, g_at_previo > 0 ? " ⛔ (alguien lo tocó antes que nosotros)" : "");
    HANDLE h = CreateThread(NULL, 0, at_hilo, NULL, 0, NULL);
    if (h) CloseHandle(h);
}
