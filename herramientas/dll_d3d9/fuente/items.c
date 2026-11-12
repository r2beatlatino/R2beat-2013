/* items.c — el BALANCE del modo ítem: qué sale de la caja «?» y cuántas cajas hay (11-oct-2026)
 *
 *   anonimo03: «en el 2013 salen muchos hielos o ítems sin sentido; el CBT 2011 es perfecto» → «arrancá con el
 *   plan y dejá el rcoin apagado». Toda la investigación: documentacion/ITEMS_SORTEO.md.
 *
 *   El ítem lo sortea el CLIENTE del que agarra la caja (0x5045D0 → el sorteador 0x4F4CB0), sumando filas de
 *   una tabla de pesos FIJA del exe (0x87B458, 87 filas × 18 ítems). El 2013 y el CBT tienen el mismo código
 *   y distinta tabla. Dos cambios, los dos sin tocar el exe en disco:
 *
 *     1 · LA TABLA   se pisa al arrancar con la del CBT (con la forma del 2013: las filas de 9★ y 10★ copian la
 *                    de 8★) y el ítem R-coin (12) en 0, apagado como hoy. La arma items_sorteo.py --datos
 *                    (items_datos.h). El jefe NO la usa: tiene su tabla aparte (0x87AF58), queda para después.
 *     2 · LAS CAJAS  el 2013 pone una cada <item frequency="900"> de groupracingcontrol.xml (0x4FAF05: lee
 *                    [[0x9D4420]+0x14]); el CBT, una cada 540 fijo (0x4AF5B0). ⇒ el 2013 pone el 60 %.
 *                    Se cambia ESA lectura por `mov esi,540`: es el camino de la carrera ítem (y del jefe, que
 *                    también es ítem); el cooperativo lee el XML por otro lado (0x56E20C) y queda igual.
 *
 *   ⚠ Como cada cliente sortea su propia caja y pone las cajas de todos con la misma semilla (la del FF25),
 *     TODOS tienen que tener la misma dll: si uno queda con la vieja, ve otras cajas que los demás.
 *   Perillas: [items] activo=1 · tabla=1 (0 = la del 2013) · cajas=540 (0 = las del XML) · doce=1 (ver 3).
 *
 *     3 · ★ LA CARRERA DE 12 (14-oct, anonimo03: «balancear el ítem en equipo/solo con el 12: veo mucho drop de
 *                    impulsores; el hielo está bien que salga con mucha, mucha desventaja; tipo Mario Kart»).
 *                    El sorteador lee cuántos corren ([cGame+0xADC] → [esp+0x24]) y tu puesto (0x4EB670 − 1 →
 *                    [esp+0x16]), y el switch de 0x4F4E7C sólo tiene fila de puesto para 6/5/4/3: con 12 NO sabe
 *                    en qué puesto vas (sólo las distancias), y la máscara de jugadores (0x42 + n, 0x4F51A3) cae
 *                    en una fila de «avance». ⇒ ahí, con más de 6, el sorteo ve «son 6» y el puesto escalado
 *                    (1.º-2.º → 1.º …), y la tabla de 0x87B458 pasa a ITEMS_DOCE (la arma items_sorteo.py
 *                    tabla_doce(); simulada con items_balance.py). Con 6 o menos, la del CBT como siempre.
 *                    Las distancias (al de adelante, al puntero…) siguen siendo las reales.
 *                    ★ Y EN EQUIPO el hielo sólo sale si TU EQUIPO VA PERDIENDO la carrera a 3 (la regla de victoria
 *                    de la sala de 12: gana el primero que mete 3 en la meta). anonimo03 (14-oct): «el azul obtuvo hielos
 *                    aun estando ganando» — MEDIDO: 2 de 9 hielos eran de azules rezagados con su equipo adelante.
 *                    Se hace con ITEMS_DOCE_EQ (= la de 12 con el hielo apagado en la máscara de «son 6», 0x48, que el
 *                    sorteo siempre suma porque el gancho le dice 6).
 *     4 · ★ EL JEFE (14-oct, anonimo03: «hacé esa corrección a las otras tablas… modo jefe, por si tuvieran el mismo
 *                    problema»). Su tabla aparte (máscaras 0x87B348, las copia 0x4E99E0 a cGame+0xFD0 al empezar) deja
 *                    el hielo al COMPAÑERO DEL EQUIPO QUE GANA (máscara del rol 1 en 1, y suma 2). Se apaga: el byte
 *                    del hielo de esa fila a 0 (guarda: la fila entera en 1, la de fábrica). [items] jefe=0 lo deja.
 *                    (El equipo de 6 no lo necesita: la máscara «equipo extra» del CBT ya apaga el hielo salvo que
 *                    TODO tu equipo vaya detrás de todos — 0x4EDCB0, leído.)
 *
 *   ★★ 26-oct (120) — VUELVE EL BALANCE DEL 2013. anonimo03: «los usuarios quieren de vuelta el sistema de balance viejo
 *      2013, no les gustó el del 2011» · «las cajas del 2013» · «la de 12, armada sobre el 2013» · «el jefe, dejar el
 *      arreglo». ⇒ de fábrica: tabla=0 (con 6 o menos la del exe TAL CUAL; la de 12 = ITEMS_DOCE, armada sobre la del
 *      2013) · cajas=0 (las del XML, una cada 900) · doce=1 · jefe=1. La del CBT sigue entera con tabla=1 (y su de 12,
 *      ITEMS_DOCE_CBT) y cajas=540. Lo de arriba (1 y 2) queda como historia de lo que corrió del 16 al 26-oct.
 *   Perillas hoy: [items] activo=1 · tabla=0 (1 = la del CBT) · cajas=0 (0 = las del XML; 540 = las del CBT) · doce=1 ·
 *      jefe=1.
 */
#include "items_datos.h"

#define ITV(x) (g_it_base + ((DWORD)(x) - 0x400000))
#define ITEMS_JEFE_MASCARA 0x87B348      /* las 15 filas-máscara del jefe (rol 0..5, avance 6..14); items_sorteo.py jefe */

static BYTE *g_it_base = NULL;
static int it_pisar(DWORD va, const void *nuevo, int n, const char *que);
static int g_it_doce_puesta = 0;    /* qué tabla hay en 0x87B458: 0 = la de 6 · 1 = la de 12 · 2 = la de 12 sin hielo */
/* ★ 26-oct: las tres tablas de la base elegida ([items] tabla): 0 = la del 2013 (de fábrica) · 1 = la del CBT */
static const void *g_it_seis = ITEMS_2013, *g_it_12 = ITEMS_DOCE, *g_it_12_eq = ITEMS_DOCE_EQ;
static int g_it_doce_anotadas = 0;

typedef BYTE (__attribute__((thiscall)) *F_IT_EQUIPO)(void *padron, int asiento);    /* 0x4EC970 (carrera12.c) */

/* En equipo: el equipo que VA GANANDO la carrera a 3 — recorre el ranking (cGame+0xAD8, en orden; nodo +0xD = asiento,
 * el mismo que lee carrera12.c) y gana el primero que junta 3. Si nadie junta 3, el del 1.º. 0 si no se sabe. */
static int it_lider_a3(BYTE *g)
{
    void *padron = *(void **)ITV(0x931660);
    BYTE *cab = *(BYTE **)(g + 0xAD8);
    if (!padron || !cab) return 0;
    int cuenta[5] = { 0, 0, 0, 0, 0 }, primero = 0, n = 0;                   /* ★ 15-oct: hasta 4 equipos */
    for (BYTE *x = *(BYTE **)cab; x && x != cab && !x[0xF] && n < 12; x = c12_siguiente(x), n++) {
        int e = ((F_IT_EQUIPO)ITV(0x4EC970))(padron, x[0xD]);
        if (e < 1 || e > 4) continue;
        if (!primero) primero = e;
        if (++cuenta[e] == 3) return e;
    }
    return primero;
}

/* Lo llama la cueva de 0x4F4E7C con cada caja, antes del switch del puesto. pn/ppuesto = las variables del sorteador;
 * g = cGame (esi); asiento = el del que agarró la caja ([esp+0xD0] del sorteador). */
static void __cdecl it_doce(BYTE *pn, BYTE *ppuesto, int n, BYTE *g, int asiento)
{
    int doce = n > 6, p = *ppuesto, p6 = p, cual = 0, lider = 0, mio = 0;
    if (doce) {
        p6 = p * 6 / n;
        if (p6 > 5) p6 = 5;
        *ppuesto = (BYTE)p6;
        *pn = 6;
        cual = 1;
        if (g && (*(WORD *)(g + 0xC) & 4) && !(*(WORD *)(g + 0xC) & 0x40)) {    /* equipo (no relevo) */
            lider = it_lider_a3(g);
            void *padron = *(void **)ITV(0x931660);
            mio = padron ? ((F_IT_EQUIPO)ITV(0x4EC970))(padron, asiento) : 0;
            if (lider && mio == lider) cual = 2;                                /* tu equipo gana: sin hielo */
        }
    }
    if (cual != g_it_doce_puesta) {
        CopyMemory(ITV(ITEMS_TABLA_VA), cual == 2 ? g_it_12_eq : cual == 1 ? g_it_12 : g_it_seis, sizeof(ITEMS_NUEVA));
        g_it_doce_puesta = cual;
    }
    if (g_it_doce_anotadas < 600) {
        g_it_doce_anotadas++;
        apuntar("  [items] caja del asiento %d: %d corren, va %d.º%s%s", asiento, n, p + 1,
                doce ? (p6 == 0 ? " → como 1.º de 6" : p6 == 1 ? " → como 2.º de 6" : p6 == 2 ? " → como 3.º de 6" :
                        p6 == 3 ? " → como 4.º de 6" : p6 == 4 ? " → como 5.º de 6" : " → como 6.º de 6") : "",
                cual == 2 ? " · su equipo gana la carrera a 3: SIN hielo" :
                lider ? " · su equipo pierde la carrera a 3" : "");
    }
}

static void it_doce_poner(void)
{
    static const BYTE esp_[8] = { 0x8A, 0x44, 0x24, 0x24, 0x3C, 0x06, 0x75, 0x07 };   /* mov al,[esp+24] · cmp al,6 · jne */
    BYTE *sitio = ITV(0x4F4E7C);
    if (memcmp(sitio, esp_, 8) != 0) {
        apuntar("  [items] ⛔ el switch del puesto (0x4F4E7C) no es el esperado: la carrera de 12 queda como hoy");
        return;
    }
    /* la tabla queda escribible: la cueva la cambia entre la de 6 y la de 12 (es .rdata, sólo datos) */
    DWORD viejo = 0;
    if (!VirtualProtect(ITV(ITEMS_TABLA_VA), sizeof(ITEMS_NUEVA), PAGE_READWRITE, &viejo)) {
        apuntar("  [items] ⛔ la tabla no quedó escribible: la carrera de 12 queda como hoy");
        return;
    }
    /* pushad · movzx eax,byte[esp+0xF0] (el asiento, [esp+0xD0]) · push eax · push esi (cGame) ·
     * movzx eax,byte[esp+0x4C] (n) · push eax · lea eax,[esp+0x42] (&puesto) · push eax · lea eax,[esp+0x54] (&n) ·
     * push eax · call it_doce · add esp,0x14 · popad · mov al,[esp+0x24] · cmp al,6 ·
     * jmp 0x4F4E82 (el jne de fábrica, con las banderas del cmp) */
    BYTE c[48] = { 0x60, 0x0F, 0xB6, 0x84, 0x24, 0xF0, 0x00, 0x00, 0x00, 0x50, 0x56,
                   0x0F, 0xB6, 0x44, 0x24, 0x4C, 0x50, 0x8D, 0x44, 0x24, 0x42, 0x50, 0x8D, 0x44, 0x24, 0x54, 0x50,
                   0xE8, 0, 0, 0, 0, 0x83, 0xC4, 0x14, 0x61, 0x8A, 0x44, 0x24, 0x24, 0x3C, 0x06,
                   0xE9, 0, 0, 0, 0 };
    BYTE *cueva = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!cueva) return;
    CopyMemory(cueva, c, 47);
    escribir_u32(cueva + 28, (DWORD)((BYTE *)it_doce - (cueva + 32)));
    escribir_u32(cueva + 43, (DWORD)(ITV(0x4F4E82) - (cueva + 47)));
    BYTE salto[6] = { 0xE9, 0, 0, 0, 0, 0x90 };
    escribir_u32(salto + 1, (DWORD)(cueva - (sitio + 5)));
    if (it_pisar(0x4F4E7C, salto, 6, "doce"))
        apuntar("  [items] ok: carrera de 12 — el sorteo ve «son 6» con el puesto escalado y la tabla de 12");
}

static int it_pisar(DWORD va, const void *nuevo, int n, const char *que)
{
    DWORD viejo = 0;
    if (!VirtualProtect(ITV(va), n, PAGE_EXECUTE_READWRITE, &viejo)) {
        apuntar("  [items] ⛔ VirtualProtect falló (%s)", que);
        return 0;
    }
    CopyMemory(ITV(va), nuevo, n);
    VirtualProtect(ITV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), ITV(va), n);
    return 1;
}

static void items_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("items", "activo", 1, ini)) {
        apuntar("  [items] apagado ([items] activo=0): el sorteo y las cajas del 2013 tal cual");
        return;
    }
    g_it_base = (BYTE *)GetModuleHandleA(NULL);
    int tabla = GetPrivateProfileIntA("items", "tabla", 0, ini);     /* ★ 26-oct: 0 = la del 2013 (de fábrica) */
    int cajas = GetPrivateProfileIntA("items", "cajas", 0, ini);     /* ★ 26-oct: 0 = las del XML (900), como el 2013 */
    if (tabla) {
        g_it_seis = ITEMS_NUEVA;
        g_it_12 = ITEMS_DOCE_CBT;
        g_it_12_eq = ITEMS_DOCE_CBT_EQ;
    }

    /* 1 · la tabla. La guarda: el sorteador la lee de donde decimos (suma en 0x4F53A4, máscara en 0x4F536E)
     *     y lo que hay ahí es la del 2013, byte por byte. Si algo no cuadra, no se toca nada (ni la de 12). */
    static const BYTE e_suma[8] = { 0x0F, 0xBE, 0x8C, 0x46, 0x58, 0xB4, 0x87, 0x00 };
    static const BYTE e_masc[8] = { 0x80, 0xBC, 0x56, 0x58, 0xB4, 0x87, 0x00, 0x00 };
    int ok = 0;
    if (memcmp(ITV(0x4F53A4), e_suma, 8) != 0 || memcmp(ITV(0x4F536E), e_masc, 8) != 0 ||
        memcmp(ITV(ITEMS_TABLA_VA), ITEMS_2013, sizeof(ITEMS_2013)) != 0)
        apuntar("  [items] ⛔ el sorteador o su tabla (0x%X) no son los esperados: la tabla NO se toca", ITEMS_TABLA_VA);
    else if (!tabla) {
        apuntar("  [items] ok: la tabla del sorteo es la del 2013 tal cual (la de fábrica; [items] tabla=1 = la del CBT)");
        ok = 1;
    } else if (it_pisar(ITEMS_TABLA_VA, ITEMS_NUEVA, sizeof(ITEMS_NUEVA), "tabla")) {
        apuntar("  [items] ok: la tabla del sorteo es la del CBT 2011 (R-coin apagado) en 0x%X ([items] tabla=1)",
                ITEMS_TABLA_VA);
        ok = 1;
    }
    /* 3 · la carrera de 12, armada sobre la base elegida (al volver a 6 o menos repone ésa) */
    if (ok) {
        if (GetPrivateProfileIntA("items", "doce", 1, ini))
            it_doce_poner();
        else
            apuntar("  [items] la carrera de 12 sin tabla propia ([items] doce=0)");
    }

    /* 4 · el jefe: el compañero del equipo que gana, sin hielo (rol 1 de las máscaras de 0x87B348, columna 8) */
    if (GetPrivateProfileIntA("items", "jefe", 1, ini)) {
        static const BYTE e_rol1[18] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1 };
        static const BYTE cero = 0;
        if (memcmp(ITV(ITEMS_JEFE_MASCARA + 18), e_rol1, 18) != 0)
            apuntar("  [items] ⛔ la máscara del jefe (rol 1) no es la de fábrica: el jefe queda como está");
        else if (it_pisar(ITEMS_JEFE_MASCARA + 18 + (8 - 1), &cero, 1, "jefe"))
            apuntar("  [items] ok: jefe — el compañero del equipo que gana ya no saca hielo");
    }

    /* 2 · las cajas: 0x4FAF05  mov ecx,[0x9D4420] · mov esi,[ecx+0x14]  →  mov esi,N · 4 nop.
     *     ecx se vuelve a cargar en la instrucción siguiente (lea ecx,[ebp+0x928]), así que no se extraña. */
    static const BYTE e_cajas[9] = { 0x8B, 0x0D, 0x20, 0x44, 0x9D, 0x00, 0x8B, 0x71, 0x14 };
    static const BYTE e_sigue[6] = { 0x8D, 0x8D, 0x28, 0x09, 0x00, 0x00 };
    if (cajas <= 0)
        apuntar("  [items] las cajas del XML tal cual, como el 2013 (una cada 900; [items] cajas=540 = las del CBT)");
    else if (cajas < 60)
        apuntar("  [items] ⛔ cajas=%d es demasiado poco (una caja cada %d): se dejan las del XML", cajas, cajas);
    else if (memcmp(ITV(0x4FAF05), e_cajas, 9) != 0 || memcmp(ITV(0x4FAF0E), e_sigue, 6) != 0)
        apuntar("  [items] ⛔ la lectura de la frecuencia (0x4FAF05) no es la esperada: las cajas NO se tocan");
    else {
        BYTE n[9] = { 0xBE, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90 };
        *(DWORD *)(n + 1) = (DWORD)cajas;
        if (it_pisar(0x4FAF05, n, 9, "cajas"))
            apuntar("  [items] ok: una caja cada %d en la carrera ítem (el XML dice 900; el CBT, 540)", cajas);
    }
}
