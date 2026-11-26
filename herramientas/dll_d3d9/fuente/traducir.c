/* traducir.c — ★ 26-nov (anonimo03: «agregar los idiomas: español, portugués (Brasil), coreano, chino, japonés»)
 *
 *   Los textos de Ñ2Hock siguen escritos en español en el código. TR(texto) devuelve el mismo texto en el idioma
 *   elegido (o el original si no está en la tabla): se llama donde el texto se DIBUJA o se le pone a un control
 *   (n2_texto, n2_ctl, las pestañas, la barra de la Pausa, el panel del Far…) y en los formatos de wsprintfW.
 *   Así el idioma se cambia en vivo, sin rearmar las ventanas.
 *
 *   La tabla (traducciones.h) la arma herramientas/dll_d3d9/traducciones/armar_tabla.py desde los .json de cada
 *   idioma: la clave es el texto en español TAL CUAL está en el .c (con sus %d, \n…).
 *
 *   [herramienta] idioma = 0 español · 1 português (Brasil) · 2 한국어 · 3 中文 (简体) · 4 日本語
 */

#define TR_N_IDIOMAS 5
static volatile int g_tr_idi = 0;
static const wchar_t *const TR_NOMBRES[TR_N_IDIOMAS] = {
    L"Español", L"Português (Brasil)", L"한국어", L"中文 (简体)", L"日本語"
};
/* las letras para las ventanas cuando el idioma lo pide (la elegida no siempre tiene hangul / kanji) */
static const wchar_t *const TR_LETRA[TR_N_IDIOMAS] = { NULL, NULL, L"Malgun Gothic", L"Microsoft YaHei UI", L"Yu Gothic UI" };

#include "traducciones.h"            /* static const wchar_t *const TR_TABLA[][TR_N_IDIOMAS]; TR_N */

#define TR_HASH 4096                 /* > 2 x TR_N, potencia de 2 */
static WORD g_tr_hash[TR_HASH];      /* índice + 1 en TR_TABLA; 0 = vacío */
static INIT_ONCE g_tr_once = INIT_ONCE_STATIC_INIT;

static DWORD tr_fnv(const wchar_t *s)
{
    DWORD h = 2166136261u;
    for (; *s; s++) { h ^= (DWORD)*s; h *= 16777619u; }
    return h;
}

static BOOL CALLBACK tr_armar(PINIT_ONCE o, PVOID p, PVOID *c)
{
    (void)o; (void)p; (void)c;
    for (int i = 0; i < TR_N; i++) {
        DWORD k = tr_fnv(TR_TABLA[i][0]) & (TR_HASH - 1);
        while (g_tr_hash[k]) k = (k + 1) & (TR_HASH - 1);
        g_tr_hash[k] = (WORD)(i + 1);
    }
    return TRUE;
}

/* el texto en el idioma elegido (el mismo puntero si es español o no está en la tabla) */
static const wchar_t *tr_en(int idi, const wchar_t *s)
{
    if (idi <= 0 || idi >= TR_N_IDIOMAS || !s || !s[0]) return s;
    InitOnceExecuteOnce(&g_tr_once, tr_armar, NULL, NULL);
    DWORD k = tr_fnv(s) & (TR_HASH - 1);
    for (WORD v; (v = g_tr_hash[k]) != 0; k = (k + 1) & (TR_HASH - 1)) {
        const wchar_t *const *f = TR_TABLA[v - 1];
        if (!lstrcmpW(f[0], s)) return f[idi] && f[idi][0] ? f[idi] : s;
    }
    return s;
}
static const wchar_t *TR(const wchar_t *s) { return tr_en(g_tr_idi, s); }

static void tr_leer_ini(const char *ini)
{
    int i = (int)GetPrivateProfileIntA("herramienta", "idioma", 0, ini);
    g_tr_idi = i >= 0 && i < TR_N_IDIOMAS ? i : 0;
}
