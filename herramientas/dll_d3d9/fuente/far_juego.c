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
}
