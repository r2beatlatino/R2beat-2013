# -*- coding: utf-8 -*-
"""despacho — la tabla de ruteo del `handle_inner`.

Es la MISMA cadena de condiciones del archivo original, en el MISMO orden.
Se evalúa de arriba abajo y gana la primera que da verdadera, igual que un
`if/elif`. Partirla en una lista, en vez de un dict por comando, es a propósito:
hay ramas con condiciones compuestas (`cmd == 0x40 and data[0] == 0x21`) y
otras que atrapan varios comandos, y un dict cambiaría el resultado.

★ ES EL ÍNDICE DE ENTRADA DEL SERVER. Si buscás quién atiende un comando, buscá su
  `FFxx` acá: cada ruta tiene al costado el comando en hexadecimal (como lo nombra
  `documentacion/FF_HANDLERS.md` y como sale en el log) y el módulo donde vive el
  handler. El `cmd ==` va en decimal porque es lo que llega por el cable.

  El número del medio en `h_02_ff136` es el orden que tenía la rama en el `if/elif`
  original y no significa nada hoy; lo que importa es el `ffXXX` del final.
"""
from .ajustes import (
    RESPONDER_COMO_EL_REAL,
)
from .lobby_menu import (
    h_00_ff03,
    h_01_ff04,
    h_02_ff136,
    h_03_ff8c,
    h_04_ff97,
    h_05_ff77,
    h_05b_ff78,
    h_86_ff86,
    h_d2_ffd2,
    h_06_ff06,
    h_07_ff08,
    h_14_ff40,
    h_ff40_circulo,
    h_circulo_datos,
    h_circulo_donar,
    h_circulo_subir,
    h_circulo_tienda,
    h_ffac_mision_circulo,
    h_17_ff49,
    h_32_ff3a,
    h_41_ff45,
    h_44_ff94,
    h_ff138_preferidas,
    h_ff13b_popular,
    h_ffe2_referido,
    h_ff158_cupon,
    h_ff118_mision_hoy,
    h_ff73_conjuntos,
    h_ff6f_preferidos,
    h_ff52_invitar,
    h_ff40_invitar_amigo,
    h_ff72_entrada_rapida,
    h_ff98_espectador_datos,
    h_sin_handler,
)
from .lobby_pareja import (
    h_ff40_ficha,
    h_ff47_tirar_recuerdo,
    h_ff7b_baile_de_pareja,
    h_ff60_gesto_de_uso,
    h_ffc2_confesion,
    h_ff4a_datos_pareja,
    h_ff40_pareja,
)
from .lobby_alma import (
    h_ff40_alma,
    h_ff40_alma_popup,
)
from .lobby_campana import h_ffa8_campana
from .lobby_social import (
    h_ff40_amigos,
    h_ff40_megafono,
    h_ff42_lista_de_amigos,
)
from .lobby_salas import (
    h_08_ff6e,
    h_09_ff10,
    h_15_ff65,
    h_18_ff11,
    h_19_ff13,
    h_20_ff0c,
    h_22_ff17,
    h_25_ff4b,
    h_26_ffbd,
    h_29_ff1c,
    h_ff41_info_de_sala,
    h_ff79_seleccionando,
    h_33_ff12,
    h_45_ff6b,
    h_46_ff6c,
    h_47_ff18,
    h_48_ff9b,
    h_ff20_expulsar,
    h_ff175_ceder_capitan,
    h_ff87_cerrar_slot,
    h_ff99_cambiar_de_puesto,
    h_ffc9_dificultad,
)
from .lobby_carrera import (
    h_21_ff28,
    h_23_ff23,
    h_24_ff59,
    h_27_ff139,
    h_28_ff1b,
    h_30_ff24,
    h_31_ff25,
    h_38_ff10f,
    h_39_ff10e,
    h_40_ff57,
    h_43_ff63,
)
from .puzzle import h_ffac as h_ffac_puzzle, h_ffae as h_ffae_puzzle, h_ffaf as h_ffaf_puzzle
from .puzzle import h_ffb0 as h_ffb0_puzzle, h_ffb1 as h_ffb1_puzzle, h_ffb2 as h_ffb2_puzzle, h_ffb5 as h_ffb5_puzzle
from .lobby_tienda import (
    h_ff119_canje_gorila,
    h_10_ff111,
    h_11_ffab,
    h_12_ff125,
    h_13_ff81,
    h_16_ffaf,
    h_34_ffc8,
    h_35_ff2a,
    h_36_ff50,
    h_ff69_abrir_capsula,
    h_ff19_equipar_personaje,
    h_37_ff1a,
    h_ff7f_vestir_varios,
    h_42_ff51,
)

RUTAS = [
    (lambda st, cmd, data: cmd == 3, h_00_ff03),                          # FF03         lobby_menu
    (lambda st, cmd, data: cmd == 4, h_01_ff04),                          # FF04         lobby_menu
    (lambda st, cmd, data: cmd == 310, h_02_ff136),                       # FF136        lobby_menu
    (lambda st, cmd, data: cmd == 140, h_03_ff8c),                        # FF8C         lobby_menu
    (lambda st, cmd, data: cmd == 151, h_04_ff97),                        # FF97         lobby_menu
    (lambda st, cmd, data: cmd == 119, h_05_ff77),                        # FF77         lobby_menu
    (lambda st, cmd, data: cmd == 120, h_05b_ff78),                       # FF78         lobby_menu
    (lambda st, cmd, data: cmd == 134, h_86_ff86),                        # FF86         lobby_menu  (cambiar el Game id)
    (lambda st, cmd, data: cmd == 210, h_d2_ffd2),                        # FFD2         lobby_menu  (ponerse una medalla)
    (lambda st, cmd, data: cmd in (0xD4, 0xD7, 0xE3), h_circulo_datos),  # FFD4/D7/E3   lobby_menu  (la economía del círculo)
    (lambda st, cmd, data: cmd == 0xD6, h_circulo_donar),
    (lambda st, cmd, data: cmd == 0xE1, h_circulo_subir),                # FFE1         lobby_menu  (subir de nivel el círculo)
    (lambda st, cmd, data: cmd in (0xD8, 0xD9, 0xDF, 0xF4, 0xF5), h_circulo_tienda),  # FFD8/D9/DF/F4/F5 lobby_menu (arreglo, tienda, marca, muebles)
    (lambda st, cmd, data: cmd == 0xAC and len(data) >= 6 and data[5] == 1, h_ffac_mision_circulo),
    # ★ 15-oct: la TRAGAMONEDAS de las misiones de rompecabezas (`puzzle.py`, `documentacion/MISIONES_PUZZLE.md`)
    (lambda st, cmd, data: cmd == 0xAC, h_ffac_puzzle),                   # FFAC personal  armar
    (lambda st, cmd, data: cmd == 0xB0, h_ffb0_puzzle),                   # FFB0         el rodillo (sin respuesta)
    (lambda st, cmd, data: cmd == 0xB1, h_ffb1_puzzle),                   # FFB1         aceptar
    (lambda st, cmd, data: cmd == 0xAE, h_ffae_puzzle),                   # FFAE         rearmar
    (lambda st, cmd, data: cmd == 0xB2, h_ffb2_puzzle),                   # FFB2         avance / cobro
    (lambda st, cmd, data: cmd == 0xB5, h_ffb5_puzzle),                   # FFB5         abandonar  # FFAC círculo                # FFD6         lobby_menu  (donar Rcoin al círculo)
    (lambda st, cmd, data: cmd == 6, h_06_ff06),                          # FF06         lobby_menu
    (lambda st, cmd, data: cmd == 8, h_07_ff08),                          # FF08         lobby_menu
    (lambda st, cmd, data: cmd == 110, h_08_ff6e),                        # FF6E         lobby_salas
    (lambda st, cmd, data: cmd == 16, h_09_ff10),                         # FF10         lobby_salas
    (lambda st, cmd, data: cmd == 273, h_10_ff111),                       # FF111        lobby_tienda
    (lambda st, cmd, data: cmd == 171, h_11_ffab),                        # FFAB         lobby_tienda
    (lambda st, cmd, data: cmd == 293, h_12_ff125),                       # FF125        lobby_tienda
    (lambda st, cmd, data: cmd == 129, h_13_ff81),                        # FF81         lobby_tienda
    (lambda st, cmd, data: cmd == 64 and len(data) == 1 and (data[0] == 33), h_14_ff40),# FF40         lobby_menu
    # ★ CÍRCULO (24-sep): 0x22 = chat del círculo, 0x23 = el aviso desde el parlante. `circulos.py`
    (lambda st, cmd, data: cmd == 64 and len(data) >= 2 and data[0] in (0x22, 0x23), h_ff40_circulo),
    # ★★ AMIGOS (2026-09-10). ⚠ VA DETRÁS del 0x21: aquélla es más específica (GuildInfo, círculo)
    #    y si ésta se pusiera antes se la comería. El despacho evalúa EN ORDEN.
    (lambda st, cmd, data: cmd == 64 and data and data[0] in (0x01, 0x04, 0x0D, 0x1D, 0x1E, 0x1F),
     h_ff40_amigos),                                                   # FF40 amigos  lobby_social
    (lambda st, cmd, data: cmd == 66, h_ff42_lista_de_amigos),         # FF42         lobby_social
    # ★★★ PAREJA — FF40 sub 0x0A. Va detrás de amigos porque aquélla ya filtra por sus propios
    #   subtipos y no hay solapamiento: el 0x0A no está en su lista.
    (lambda st, cmd, data: cmd == 64 and data and data[0] == 0x0A,
     h_ff40_pareja),
    # ★★★★★ EL MEGÁFONO — FF40 sub 0x0B (2026-09-15). Medido con anonimo03 usándolo:
    #   `0b [u32 item] [u8 len][texto]`, con el item 1 (chico), 2 (grande) o 200 (amigos).
    #   ⚠ Va acá, JUSTO detrás de la pareja (0x0A) y del bloque de amigos: ninguno de los dos
    #     incluye el 0x0B, así que no hay solapamiento. El despacho evalúa EN ORDEN.
    (lambda st, cmd, data: cmd == 64 and data and data[0] == 0x0B,
     h_ff40_megafono),                                                 # FF40 megáfono lobby_social
    # ★★★★★ LAS CAMPANAS — FFA8 (2026-09-15). Medido con anonimo03 tocando una:
    #   `30 01 00 00 | 00 00 c8 c2 | 00 00 0c c3 | db 0f 49 40` = ítem 304 en (-100, -140) a π.
    #   ⚠ `FFA8` NO es «la campana»: es «usé este ítem», y el ítem decide. Por acá viaja también
    #     la llave de Mi Sala (572) — el propio handler de recepción del cliente (`0x5D6880`)
    #     sólo reacciona con ese 572. El filtro por ítem está DENTRO del handler, no acá, para
    #     que lo que no reconocemos quede logueado en vez de desaparecer.
    (lambda st, cmd, data: cmd == 168 and len(data) >= 16,
     h_ffa8_campana),                                                  # FFA8 campana lobby_campana
    # ★★★ EL AMIGO DEL ALMA — FF40 sub 0x3B, y su popup el 0x3F (2026-09-15).
    #   ⚠ Van detrás de todo lo anterior por la misma razón que la pareja: ninguna de las listas
    #     de arriba contiene el 0x3B ni el 0x3F, así que no hay solapamiento. El despacho evalúa
    #     EN ORDEN y la primera que engancha se lo queda.
    (lambda st, cmd, data: cmd == 64 and data and data[0] == 0x3B,
     h_ff40_alma),                                                     # FF40 alma    lobby_alma
    (lambda st, cmd, data: cmd == 64 and data and data[0] == 0x3F,
     h_ff40_alma_popup),                                               # FF40 alma    lobby_alma
    # ★ FF40 sub 0x06 = la ficha que llena el panel «Mi Pareja». El cliente la pide cada 3 s
    #   hasta que se le contesta; sin handler el panel se queda en «No conectado».
    (lambda st, cmd, data: cmd == 64 and data and data[0] == 0x06,
     h_ff40_ficha),
    # ★★★ FF4A = 0x4A = 74. `CmdGetCoupleData`: la línea «Mi pareja» del panel de Mensajería.
    #   ⚠ En PROD llega **440 veces por día** y nunca se contestó. No es sólo del banco.
    # ★★ FF47 = 0x47 = 71. `CmdDeleteCoupleHistory`: el botón de tirar el anillo roto.
    #   ⛔ Sin handler el cliente NO HACE NADA (`0x5cf2d5: cmp result,0 / je`) y el botón parece
    #     roto — que es justo lo que reportó anonimo03. Es la única salida del tercer estado.
    # ★★★ FF7B = 0x7B = 123. `CmdCoupleDance`: el gesto/baile de pareja (/rosas, /besar…).
    #   ⛔ El cliente **no baila al mandar**: la función que reproduce tiene un solo llamador, el
    #     handler de RECEPCIÓN ⇒ sin nuestro eco no baila NADIE, ni el que lo apretó.
    (lambda st, cmd, data: cmd == 123, h_ff7b_baile_de_pareja),       # FF7B         lobby_pareja
    # ★★ FF60 = 0x60 = 96. El gesto de un CUPÓN DE ANIMACIÓN (/comiste, /show…: 1010xxx/1020xxx).
    #   Igual que el FF7B: la animación la pone el handler de RECEPCIÓN (0x5D08E0) ⇒ sin eco, nada.
    (lambda st, cmd, data: cmd == 96, h_ff60_gesto_de_uso),          # FF60         lobby_pareja
    # ★ FFC2 = 0xC2 = 194. `CmdUpdateProposeMsg`: el «Ingresar» de la confesión (27-sep).
    (lambda st, cmd, data: cmd == 194, h_ffc2_confesion),             # FFC2         lobby_pareja
    (lambda st, cmd, data: cmd == 71, h_ff47_tirar_recuerdo),         # FF47         lobby_pareja
    (lambda st, cmd, data: cmd == 74, h_ff4a_datos_pareja),           # FF4A         lobby_pareja                                                    # FF40 ficha   lobby_pareja                                                   # FF40 pareja  lobby_pareja
    # ★★★ FF41 = 0x41 = 65. `CmdGetRoomInfo`: la info de UNA sala. Es el motor del «Jugar
    #   Juntos» — el cliente lo manda al llegar al canal del amigo y, si no se le contesta, se
    #   queda parado en el lobby. ⚠ No confundir con `h_41_ff45`: ese "41" es el nº de rama del
    #   `if/elif` original y atiende el FF45, no el FF41.
    (lambda st, cmd, data: cmd == 65, h_ff41_info_de_sala),            # FF41         lobby_salas
    (lambda st, cmd, data: cmd == 101, h_15_ff65),                        # FF65         lobby_salas
    # ★ 15-oct: el FFAF es la lista de MISIONES PUZZLE (antes se contestaba vacío con h_16_ffaf). Ver `puzzle.py`.
    (lambda st, cmd, data: cmd == 175, h_ffaf_puzzle),                    # FFAF         puzzle
    (lambda st, cmd, data: cmd == 73, h_17_ff49),                         # FF49         lobby_menu
    (lambda st, cmd, data: cmd == 17, h_18_ff11),                         # FF11         lobby_salas
    (lambda st, cmd, data: cmd == 19, h_19_ff13),                         # FF13         lobby_salas
    (lambda st, cmd, data: cmd == 12, h_20_ff0c),                         # FF0C         lobby_salas
    (lambda st, cmd, data: cmd == 40, h_21_ff28),                         # FF28         lobby_carrera
    (lambda st, cmd, data: cmd == 23, h_22_ff17),                         # FF17         lobby_salas
    (lambda st, cmd, data: cmd == 35, h_23_ff23),                         # FF23         lobby_carrera
    (lambda st, cmd, data: cmd == 89, h_24_ff59),                         # FF59         lobby_carrera
    (lambda st, cmd, data: cmd == 75, h_25_ff4b),                         # FF4B         lobby_salas
    (lambda st, cmd, data: cmd == 189, h_26_ffbd),                        # FFBD         lobby_salas
    (lambda st, cmd, data: cmd == 313, h_27_ff139),                       # FF139        lobby_carrera
    (lambda st, cmd, data: cmd == 27, h_28_ff1b),                         # FF1B         lobby_carrera
    (lambda st, cmd, data: cmd == 28, h_29_ff1c),                         # FF1C         lobby_salas
    (lambda st, cmd, data: cmd == 121, h_ff79_seleccionando),             # FF79         lobby_salas
    (lambda st, cmd, data: cmd == 36, h_30_ff24),                         # FF24         lobby_carrera
    (lambda st, cmd, data: cmd == 37, h_31_ff25),                         # FF25         lobby_carrera
    (lambda st, cmd, data: cmd == 58, h_32_ff3a),                         # FF3A         lobby_menu
    (lambda st, cmd, data: cmd == 18, h_33_ff12),                         # FF12         lobby_salas
    (lambda st, cmd, data: cmd == 200, h_34_ffc8),                        # FFC8         lobby_tienda
    (lambda st, cmd, data: cmd == 42, h_35_ff2a),                         # FF2A         lobby_tienda
    (lambda st, cmd, data: cmd == 80, h_36_ff50),                         # FF50         lobby_tienda
    # ★ FF69 = 0x69 = 105. "Abrí esta cápsula": llega justo después del FF50 que la compra.
    #   Sin handler, la animación del sorteo se queda esperando para siempre (2026-09-08).
    (lambda st, cmd, data: cmd == 105, h_ff69_abrir_capsula),             # FF69 gacha   lobby_tienda
    # ★ FF19 = 0x19 = 25. "Me pongo este personaje" (los que salen del gacha). Sin
    #   handler el cliente lo REPITE, y se le vieron 9 seguidos (2026-09-08).
    (lambda st, cmd, data: cmd == 25, h_ff19_equipar_personaje),          # FF19 personaje lobby_tienda
    (lambda st, cmd, data: cmd == 26, h_37_ff1a),                         # FF1A         lobby_tienda
    # ★ 11-oct: «Restaurar» del armario (y la ropa de antes al sacarse un personaje): varias prendas de una.
    (lambda st, cmd, data: cmd == 0x7F, h_ff7f_vestir_varios),            # FF7F         lobby_tienda
    (lambda st, cmd, data: cmd == 271, h_38_ff10f),                       # FF10F        lobby_carrera
    (lambda st, cmd, data: cmd == 270, h_39_ff10e),                       # FF10E        lobby_carrera
    (lambda st, cmd, data: cmd == 281, h_ff119_canje_gorila),              # FF119        lobby_tienda  ★ canje de monedas gorila
    (lambda st, cmd, data: cmd == 87, h_40_ff57),                         # FF57         lobby_carrera
    (lambda st, cmd, data: cmd in (69, 84, 29) and RESPONDER_COMO_EL_REAL, h_41_ff45),# FF45 FF54 FF1D            lobby_menu
    (lambda st, cmd, data: cmd in (81, 175, 311), h_42_ff51),             # FF51 FFAF FF137            lobby_tienda
    (lambda st, cmd, data: cmd == 99, h_43_ff63),                         # FF63         lobby_carrera
    (lambda st, cmd, data: cmd == 148, h_44_ff94),                        # FF94         lobby_menu
    # ★ EL PICKER (29-sep, `picker.py`): las PREFERIDAS (FF138 agregar · FF13A quitar) y la
    #   POPULARIDAD (FF13B). Caían en «SIN handler» — ver `documentacion/PICKER_SISTEMA.md`.
    (lambda st, cmd, data: cmd in (0x138, 0x13A), h_ff138_preferidas),    # FF138 FF13A  lobby_menu
    (lambda st, cmd, data: cmd == 0x13B, h_ff13b_popular),                # FF13B        lobby_menu
    # ★ «¿QUIÉN TE INVITÓ?» (11-oct, `referido.py`): caía en «SIN handler» y el que escribía un nombre quedaba
    #   clavado en la pantalla de crear personaje esperando la respuesta.
    (lambda st, cmd, data: cmd == 0xE2, h_ffe2_referido),                 # FFE2         lobby_menu
    # ★ 15-oct: «NUEVO · Ingresar cupón» del lobby. Caía en «SIN handler»: en prod 84 intentos sin respuesta
    #   (DULCE / TRUCO). Ver `cupon.py` y `documentacion/CUPON.md`.
    (lambda st, cmd, data: cmd == 0x158, h_ff158_cupon),                 # FF158        lobby_menu
    # ★ 15-oct: «Obten Premios» de la Misión de hoy. Ver `mision_hoy.py` y `documentacion/MISION_DE_HOY.md`.
    (lambda st, cmd, data: cmd == 0x118, h_ff118_mision_hoy),            # FF118        lobby_menu
    # ★ 12-oct: los SETS del armario (SET1..SET4: Guardar / Cargar). Ver `conjuntos.py`.
    (lambda st, cmd, data: cmd == 0x73, h_ff73_conjuntos),                # FF73         lobby_menu
    # ★ 12-oct: «Mis preferidos» de la tienda (el carrito): FF6F agregar · FF70 sacar. Ver `preferidos.py`.
    (lambda st, cmd, data: cmd in (0x6F, 0x70), h_ff6f_preferidos),       # FF6F FF70    lobby_menu
    # ★ 12-oct: «Invitar a los del vestíbulo» (el anfitrión desde la sala). Ver `invitacion.py`.
    (lambda st, cmd, data: cmd == 0x52, h_ff52_invitar),                  # FF52         lobby_menu
    # ★ 12-oct: «Invitar a un amigo a mi sala» (FF40 sub 0x07). Ver `invitacion.py`.
    (lambda st, cmd, data: cmd == 64 and data and data[0] == 0x07, h_ff40_invitar_amigo),   # FF40 0x07  lobby_menu
    # ★ 12-oct: «Ingreso Rápido» (una sala al azar que cumpla sus casillas). Ver `entrada_rapida.py`.
    (lambda st, cmd, data: cmd == 0x72, h_ff72_entrada_rapida),            # FF72         lobby_menu
    # ★ 12-oct: la TRANSMISIÓN al espectador (lo que mandan los corredores, al que mira). Ver `espectador_datos.py`.
    (lambda st, cmd, data: cmd == 0x98, h_ff98_espectador_datos),          # FF98         lobby_menu
    (lambda st, cmd, data: cmd == 107, h_45_ff6b),                        # FF6B         lobby_salas
    (lambda st, cmd, data: cmd == 108, h_46_ff6c),                        # FF6C         lobby_salas
    (lambda st, cmd, data: cmd == 24, h_47_ff18),                         # FF18         lobby_salas
    (lambda st, cmd, data: cmd == 155, h_48_ff9b),                        # FF9B         lobby_salas
    (lambda st, cmd, data: cmd == 32, h_ff20_expulsar),                    # FF20 expulsar  lobby_salas
    (lambda st, cmd, data: cmd == 201, h_ffc9_dificultad),                 # FFC9 dificultad lobby_salas
    (lambda st, cmd, data: cmd == 373, h_ff175_ceder_capitan),            # FF175=0x175 ceder capitan
    (lambda st, cmd, data: cmd == 135, h_ff87_cerrar_slot),               # FF87 cerrar asiento
    # ★ FF99 = 0x99 = 153. Llega VACÍO y es el conmutador mirar<->competir: los DOS botones
    #   mandan lo mismo y el que decide la dirección es el server (medido 2026-09-08).
    (lambda st, cmd, data: cmd == 153, h_ff99_cambiar_de_puesto),         # FF99 mirar<->competir
]

SIN_HANDLER = h_sin_handler

