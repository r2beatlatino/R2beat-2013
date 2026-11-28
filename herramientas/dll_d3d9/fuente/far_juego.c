/* far_juego.c — EL PANEL DEL FAR (Y DE LA VELOCIDAD) DENTRO DEL JUEGO: el estado y los pedidos (26-nov-2026)
 *
 *   anonimo03 (con su boceto): «esto del Far se puede poner dentro del juego, para que la gente vea su Far, y que sea
 *   manejable y modificarlo desde ahí — claro que sería transparente». Después: «sin la parte de los teclados» y
 *   «también el apartado de velocidad en práctica — que sólo aparezca en práctica».
 *
 *   Un panel en la carrera (arriba a la derecha, bajo la rueda del booster):
 *     · Far: el de ahora, Far Vision, AutoFar y la barra del Far (en cualquier carrera);
 *     · Velocidad: «Activar velocidad» y su barra (50..150 %), SÓLO en práctica.
 *   Dos partes:
 *     · ESTO (dentro de herramienta.c, antes de la ventana): lo compartido y `fj_tick` (lo del Far), que corre en el hilo
 *       de la ventana (n2_e_tick, cada 50 ms) con las MISMAS funciones de la ventana. Lo de la velocidad lo aplica
 *       n2_e_tick mismo (usa g_e y n2_e_cambio, de n2h_ventana.c).
 *     · far_juego_dibujo.c (en d3d9_proxy.c, después de estilos_texto.c): el dibujo (transparente) y el mouse, en el
 *       hilo del juego; deja pedidos acá (Interlocked). Nada se cambia desde el hilo del juego.
 *   Se muestra/oculta en Personalización · Far («El panel del Far en la carrera») — [herramienta] far_juego=1.
 */

/* g_fj_mostrar, g_fj_x, g_fj_y: en herramienta.c (antes de guardar el ini) */
static volatile LONG g_fj_ped_far = 0, g_fj_ped_auto = 0;   /* 1 = alternar */
static volatile LONG g_fj_ped_valor = -1;              /* la barra del Far pedida (2..44), -1 nada */
static volatile LONG g_fj_ped_vel = 0;                 /* 1 = alternar «Activar velocidad» */
static volatile LONG g_fj_ped_pct = -1;                /* la velocidad pedida (50..150), -1 nada */
static volatile LONG g_fj_guardar = 0;                 /* se movió: guardar la posición */

/* (hilo de la ventana, cada 50 ms) lo del Far que pidió el panel del juego */
static void fj_tick(void)
{
    if (InterlockedExchange(&g_fj_ped_far, 0)) ht_cambiar(O_FAR, !g_op[O_FAR].quiere);
    if (InterlockedExchange(&g_fj_ped_auto, 0)) ht_cambiar(O_AUTOFAR, !g_op[O_AUTOFAR].quiere);
    LONG v = InterlockedExchange(&g_fj_ped_valor, -1);
    if (v >= 2 && v <= 44 && v != g_ht_far_n2h) {
        g_ht_far_n2h = (int)v;
        if (!g_op[O_FAR].quiere && !g_op[O_AUTOFAR].quiere) ht_cambiar(O_FAR, 1);   /* mover la barra = usar el Far */
        ht_far_aplicar();
        ht_refrescar();
        ht_pedir_guardar();
    }
    if (InterlockedExchange(&g_fj_guardar, 0)) ht_pedir_guardar();
}

/* «FF0080» -> 0xFF0080; lo que no sea un color (o «FFFFFFFF») = de fábrica */
static DWORD fj_hex(const char *t)
{
    DWORD v = 0;
    int n = 0;
    for (; t && *t; t++, n++) {
        char c = *t;
        int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
        if (d < 0 || n >= 8) return 0xFFFFFFFF;
        v = v << 4 | (DWORD)d;
    }
    return n && v <= 0xFFFFFF ? v : 0xFFFFFFFF;
}

static void fj_leer_ini(void)
{
    g_fj_mostrar = GetPrivateProfileIntA("herramienta", "far_juego", 1, g_ht_ini) != 0;
    int x = (int)GetPrivateProfileIntA("herramienta", "far_juego_x", -1, g_ht_ini);
    int y = (int)GetPrivateProfileIntA("herramienta", "far_juego_y", -1, g_ht_ini);
    int fo = (int)GetPrivateProfileIntA("herramienta", "far_juego_fondo", 0, g_ht_ini);
    g_fj_fondo = fo < 0 ? 0 : fo > 100 ? 100 : fo;
    g_fj_arco = GetPrivateProfileIntA("herramienta", "far_juego_arcoiris", 1, g_ht_ini) != 0;
    int tk = (int)GetPrivateProfileIntA("herramienta", "far_juego_tecla", VK_F7, g_ht_ini);
    g_fj_tecla = tk >= 0 && tk < 256 ? tk : VK_F7;
    g_fj_x = x >= 0 && x <= 1000 ? x : -1;
    g_fj_y = y >= 0 && y <= 1000 ? y : -1;
    /* ★ 28-nov: Personalización · Panel Far */
    int es = (int)GetPrivateProfileIntA("herramienta", "far_juego_tamano", 100, g_ht_ini);
    g_fj_escala = es < 70 ? 70 : es > 200 ? 200 : es;
    g_fj_fijo = GetPrivateProfileIntA("herramienta", "far_juego_fijo", 0, g_ht_ini) != 0;
    g_fj_crayon = GetPrivateProfileIntA("herramienta", "far_juego_crayon", 1, g_ht_ini) != 0;
    char t[200];
    GetPrivateProfileStringA("herramienta", "far_juego_color", "FFFFFFFF", t, sizeof(t), g_ht_ini);
    g_fj_acento = fj_hex(t);
    GetPrivateProfileStringA("herramienta", "far_juego_color_numero", "FFFFFFFF", t, sizeof(t), g_ht_ini);
    g_fj_numcol = fj_hex(t);
    GetPrivateProfileStringA("herramienta", "far_juego_partes", "1111", t, sizeof(t), g_ht_ini);
    if (lstrlenA(t) >= 4) {
        g_fj_ver_num = t[0] != '0'; g_fj_ver_chk = t[1] != '0'; g_fj_ver_barra = t[2] != '0'; g_fj_ver_vel = t[3] != '0';
    }
    GetPrivateProfileStringA("herramienta", "far_juego_letra", "", t, sizeof(t), g_ht_ini);
    if (!MultiByteToWideChar(CP_UTF8, 0, t, -1, g_fj_letra, 64)) g_fj_letra[0] = 0;
    InterlockedIncrement(&g_fj_letra_ver);
}
