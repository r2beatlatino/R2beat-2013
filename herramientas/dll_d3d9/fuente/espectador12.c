/* espectador12.c — EL ESPECTADOR EN LA SALA DE 12 (14-oct-2026, documentacion/ESPECTADOR_12.md)
 *
 *   anonimo03: «QA de 12 jugadores con 6 espectadores» → (la sala de 12 no admitía espectadores) → «intenta armarlo».
 *
 *   1 · ENTRAR. El FF11 (manejador 0x5CD150) lleva el lugar y los errores en el MISMO byte: `cmp al,0x0C · jb → entra`
 *       (0x5CD263), y 0x0C..0x11 son carteles. En la sala de 12 los doce lugares son corredores ⇒ el server manda un
 *       código propio, 0x30 + k (ESPECTADOR12_CODIGO), y acá se lo convierte en el lugar 12 + k ANTES del cmp: se
 *       escribe en el byte que lee el camino de entrar ([esp+0x18], 0x5CD1B4) y se salta a 0x5CD196. Los demás valores,
 *       como siempre.
 *   ⏳ Lo que falta: medir qué se rompe con el lugar 12+ (la caja negra anota cada cierre) — ESPECTADOR_12.md §2.
 *   [espectador12] activo=0 lo apaga.
 */
#include "espectador12_datos.h"
#define E12V(x) (g_e12_base + ((DWORD)(x) - 0x400000))
static BYTE *g_e12_base = NULL;

static int e12_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(E12V(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(E12V(va), b, n);
    VirtualProtect(E12V(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), E12V(va), n);
    return 1;
}

static void espectador12_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("espectador12", "activo", 1, ini)) {
        apuntar("  [espectador12] apagado ([espectador12] activo=0)");
        return;
    }
    g_e12_base = (BYTE *)GetModuleHandleA(NULL);
    /* 0x5CD263: cmp al,0x0C · jb 0x5CD196 */
    static const BYTE e_ff11[8] = { 0x3C, 0x0C, 0x0F, 0x82, 0x2B, 0xFF, 0xFF, 0xFF };
    if (memcmp(E12V(0x5CD263), e_ff11, 8) != 0) {
        apuntar("  [espectador12] ⛔ el FF11 (0x5CD263) no es el esperado: no se toca");
        return;
    }
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return;
    int i = 0, a_orig1, a_orig2;
    k[i++] = 0x3C; k[i++] = 0x30;                                   /* cmp al,0x30 */
    k[i++] = 0x72; a_orig1 = i++;                                   /* jb orig */
    k[i++] = 0x3C; k[i++] = 0x36;                                   /* cmp al,0x36 */
    k[i++] = 0x73; a_orig2 = i++;                                   /* jae orig */
    k[i++] = 0x2C; k[i++] = 0x24;                                   /* sub al,0x24   (0x30 → 12) */
    k[i++] = 0x88; k[i++] = 0x44; k[i++] = 0x24; k[i++] = 0x18;     /* mov [esp+0x18],al */
    k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)E12V(0x5CD196) - (DWORD)(k + i + 4)); i += 4;   /* jmp entrar */
    int orig = i;
    k[i++] = 0x3C; k[i++] = 0x0C;                                   /* cmp al,0x0C (de fábrica) */
    k[i++] = 0x0F; k[i++] = 0x82; *(int *)(k + i) = (int)((DWORD)E12V(0x5CD196) - (DWORD)(k + i + 4)); i += 4;
    k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)E12V(0x5CD26B) - (DWORD)(k + i + 4)); i += 4;
    k[a_orig1] = (BYTE)(orig - (a_orig1 + 1));
    k[a_orig2] = (BYTE)(orig - (a_orig2 + 1));
    BYTE s[8] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)k - ((DWORD)E12V(0x5CD263) + 5));
    e12_escribir(0x5CD263, s, 8);
    apuntar("  [espectador12] ★ el FF11 acepta 0x30+k = espectador en el lugar 12+k (sala de 12)");

    /* 2 · ★ MEDIDO (1.ª carrera, la caja negra): se cerró al cargar, vector fuera de rango desde 0x556DE1 con «sigo a»
     *   ([cGame+0x5D]) = 12. Para el espectador, 0x4F7520 hace [5D] = [cGame+0xC02], y C02 lo sortea 0x4F7230 sobre el
     *   PADRÓN — que en la sala de 12 incluye al propio espectador (lugar 12) ⇒ puede elegirse a sí mismo. Acá: si el
     *   elegido no es un corredor que existe ([cGame+0xA14..A18]), sigue al 0 (y C02 también, para la transmisión).
     *   0x4F7540: mov al,[eax+0xC02] · mov [esi+0x5D],al · jmp 0x4F7557  (11 bytes) */
    static const BYTE e_sigo[11] = { 0x8A, 0x80, 0x02, 0x0C, 0x00, 0x00, 0x88, 0x46, 0x5D, 0xEB, 0x0C };
    /* ★ 3.er medido (0x4FC00C con [5D] = 12): al armar la carrera C01 todavía es 0 y va por la OTRA rama (0x4F754B:
     *   mov ecx,[0x931660] · mov dl,[ecx+0x40] · mov [esi+0x5D],dl) ⇒ las DOS ramas pasan por la misma cueva.
     *   ⚠ `mov al,[eax+0xC02]` le cambia el byte bajo a eax: la cueva escribe con esi (= cGame, 0x4F752A). */
    static const BYTE e_rama[12] = { 0x8B, 0x0D, 0x60, 0x16, 0x93, 0x00, 0x8A, 0x51, 0x40, 0x88, 0x56, 0x5D };
    if (memcmp(E12V(0x4F7540), e_sigo, 11) == 0 && memcmp(E12V(0x4F754B), e_rama, 12) == 0) {
        BYTE *c = (BYTE *)VirtualAlloc(NULL, 96, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (c) {
            int j = 0, a_ok, cuerpo;
            c[j++] = 0x8A; c[j++] = 0x80; c[j++] = 0x02; c[j++] = 0x0C; c[j++] = 0x00; c[j++] = 0x00;   /* mov al,[eax+0xC02] */
            cuerpo = j;                                                                            /* ← la otra rama entra acá */
            c[j++] = 0x8B; c[j++] = 0x8E; *(DWORD *)(c + j) = 0xA18; j += 4;                       /* mov ecx,[esi+0xA18] */
            c[j++] = 0x2B; c[j++] = 0x8E; *(DWORD *)(c + j) = 0xA14; j += 4;                       /* sub ecx,[esi+0xA14] */
            c[j++] = 0xC1; c[j++] = 0xF9; c[j++] = 0x02;                                           /* sar ecx,2 */
            c[j++] = 0x0F; c[j++] = 0xB6; c[j++] = 0xD0;                                           /* movzx edx,al */
            c[j++] = 0x39; c[j++] = 0xCA;                                                          /* cmp edx,ecx */
            c[j++] = 0x72; a_ok = j++;                                                             /* jb ok */
            c[j++] = 0x30; c[j++] = 0xC0;                                                          /* xor al,al */
            c[j++] = 0x88; c[j++] = 0x86; *(DWORD *)(c + j) = 0xC02; j += 4;                       /* mov [esi+0xC02],al */
            c[a_ok] = (BYTE)(j - (a_ok + 1));
            c[j++] = 0x88; c[j++] = 0x46; c[j++] = 0x5D;                                           /* ok: mov [esi+0x5D],al */
            c[j++] = 0xE9; *(int *)(c + j) = (int)((DWORD)E12V(0x4F7557) - (DWORD)(c + j + 4)); j += 4;
            /* la otra rama: mov ecx,[0x931660] · mov al,[ecx+0x40] · jmp cuerpo */
            BYTE *tr = c + 64;
            int t = 0;
            tr[t++] = 0x8B; tr[t++] = 0x0D; *(DWORD *)(tr + t) = (DWORD)E12V(0x931660); t += 4;
            tr[t++] = 0x8A; tr[t++] = 0x41; tr[t++] = 0x40;
            tr[t++] = 0xE9; *(int *)(tr + t) = (int)((DWORD)(c + cuerpo) - (DWORD)(tr + t + 4)); t += 4;
            BYTE s2[11] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
            *(int *)(s2 + 1) = (int)((DWORD)c - ((DWORD)E12V(0x4F7540) + 5));
            e12_escribir(0x4F7540, s2, 11);
            BYTE s3[12] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
            *(int *)(s3 + 1) = (int)((DWORD)tr - ((DWORD)E12V(0x4F754B) + 5));
            e12_escribir(0x4F754B, s3, 12);
            apuntar("  [espectador12] ★ «sigo a» (las dos ramas de 0x4F7520): si no es un corredor, el 0");
        }
    } else
        apuntar("  [espectador12] ⚠ 0x4F7540/0x4F754B no son los esperados: «sigo a» queda de fábrica");

    /* 3 · ★ MEDIDO (2.ª carrera, la caja negra, el mismo 0x556DE1): ahí el juego usa «mi lugar» (12) cuando todavía no
     *   figura como espectador (C01 = 0 en ese momento) — y se cierra con el índice fuera de rango. En ese sitio, el
     *   cierre (call 0x74FF1F, 5 bytes) pasa a «usar el corredor 0» (xor edi,edi · 3 NOP): sólo actúa en el caso que hoy
     *   CIERRA el juego; con un índice válido el salto de antes ni llega acá. */
    static const BYTE e_556[9] = { 0x3B, 0xF8, 0x72, 0x05, 0xE8, 0x39, 0x91, 0x1F, 0x00 };
    if (memcmp(E12V(0x556DDD), e_556, 9) == 0) {
        static const BYTE n_556[5] = { 0x31, 0xFF, 0x90, 0x90, 0x90 };
        e12_escribir(0x556DE1, n_556, 5);
        apuntar("  [espectador12] ★ 0x556DE1: con «mi lugar» fuera de los corredores, el 0 (no se cierra)");
    } else
        apuntar("  [espectador12] ⚠ 0x556DDD no es el esperado: queda de fábrica");

    /* 5 · ★ 5.º medido (0x563806, a los 18 s): las FILAS DE LA TRANSMISIÓN ([cGame+0xC04], una por corredor) las crea
     *   0x563ED0 al armar la carrera con un contador FIJO: `mov dword [esp+0x14], 6` (0x563EF9) — seis filas con doce
     *   corredores. Pasa a 12 (en la carrera de 6 sobran 6 filas vacías que nadie usa). */
    static const BYTE e_filas[8] = { 0xC7, 0x44, 0x24, 0x14, 0x06, 0x00, 0x00, 0x00 };
    if (memcmp(E12V(0x563EF9), e_filas, 8) == 0) {
        BYTE doce = 12;
        e12_escribir(0x563EFD, &doce, 1);
        apuntar("  [espectador12] ★ las filas de la transmisión (0x563ED0): 12 en vez de 6");
    } else
        apuntar("  [espectador12] ⚠ 0x563EF9 no es el esperado: las filas quedan en 6");

    /* 4 · ★ los mismos «mi lugar fuera de rango» en TODO el exe (2.º medido: 0x558915) — la tabla la arma
     *   herramientas/espectador12_sitios.py: cada `call 0x74FF1F` del chequeo → `xor R,R · 3 NOP` (el corredor 0) */
    int hechos = 0;
    for (int n = 0; n < E12_SITIOS; n++) {
        const E12_SITIO *t = &E12_TABLA[n];
        if (memcmp(E12V(t->va), t->e, 5) != 0) continue;
        BYTE x[5] = { 0x31, (BYTE)(0xC0 | (t->r << 3) | t->r), 0x90, 0x90, 0x90 };   /* xor r,r */
        hechos += e12_escribir(t->va, x, 5);
    }
    apuntar("  [espectador12] ★ %d de %d sitios con «mi lugar» fuera de los corredores: el 0 en vez de cerrarse",
            hechos, E12_SITIOS);
}
