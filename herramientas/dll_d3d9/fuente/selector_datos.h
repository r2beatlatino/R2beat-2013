/* selector_datos.h — GENERADO por herramientas/selector_personaje_pak.py: NO EDITAR A MANO.
 *   Los recortes y las posiciones de «Elige tu personaje» (selector.c), derivados de
 *   herramientas/selector_personaje/selector.json. Coordenadas: las del cuadro de 786×566 del chino. */
#define SP_CARPETA "rnr_ui_lt/rnr_ui/charselect_pj"
#define SP_LIENZO 1024
#define SP_W 786
#define SP_H 566
#define SP_NHOJAS 10
static const char *SP_HOJA_TGA[SP_NHOJAS] = {"rnr_ui_lt/rnr_ui/charselect_pj/character_select_01.tga", "rnr_ui_lt/rnr_ui/charselect_pj/character_select_02.tga", "rnr_ui_lt/rnr_ui/charselect_pj/character_select_03.tga", "rnr_ui_lt/rnr_ui/charselect_pj/character_select_04.tga", "rnr_ui_lt/rnr_ui/charselect_pj/character_select_05.tga", "rnr_ui_lt/rnr_ui/charselect_pj/chardelete01.tga", "rnr_ui_lt/rnr_ui/charselect_pj/chardelete02.tga", "rnr_ui_lt/rnr_ui/charselect_pj/crear.tga", "rnr_ui_lt/rnr_ui/charselect_pj/entrar.tga", "rnr_ui_lt/rnr_ui/charselect_pj/titulo.tga"};
static const int SP_HOJA_TAM[SP_NHOJAS][2] = {{512, 512}, {512, 512}, {512, 512}, {512, 512}, {512, 512}, {1024, 1024}, {512, 512}, {1024, 256}, {1024, 256}, {512, 64}};
#define SP_LIENZO_FONDO_TGA "rnr_ui_lt/rnr_ui/charselect_pj/lienzo_fondo.tga"
#define SP_LIENZO_FRENTE_TGA "rnr_ui_lt/rnr_ui/charselect_pj/lienzo_frente.tga"

/* una pieza: [hoja, u, v, w, h] (hoja -1 = no hay) */
typedef struct { int hoja, u, v, w, h; } SP_PIEZA;
/* un control: dónde va y sus estados N (normal) · U (encima) · D (apretado) */
typedef struct { int x, y, w, h; SP_PIEZA n, u, d; } SP_CONTROL;

#define SPF_BG1 0
#define SPF_BG2 1
#define SPF_BG3 2
#define SPF_BG4 3
#define SPF_IMGON1 4
#define SPF_IMGON2 5
#define SPF_IMGON3 6
#define SPF_IMGON4 7
static const SP_CONTROL SP_FONDO[8] = {
    /* bg1            */ {0, 1, 510, 510, {0, 1, 1, 510, 510}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* bg2            */ {510, 1, 276, 510, {1, 2, 1, 276, 510}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* bg3            */ {0, 510, 504, 57, {2, 3, 9, 504, 57}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* bg4            */ {502, 510, 284, 57, {2, 3, 72, 284, 57}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* ImgOn1         */ {16, 27, 372, 377, {2, 3, 134, 372, 377}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* ImgOn2         */ {16, 403, 372, 143, {3, 6, 7, 372, 143}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* ImgOn3         */ {399, 27, 372, 377, {2, 3, 134, 372, 377}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* ImgOn4         */ {399, 403, 372, 143, {3, 6, 7, 372, 143}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
};

#define SPC_IMG_TITLE 0
#define SPC_IMG_BAR_LEFT 1
#define SPC_ON_LEFT 2
#define SPC_IMG_BAR_RIGHT 3
#define SPC_ON_RIGHT 4
#define SPC_IMG_INFO 5
#define SPC_TXT_LEFT 6
#define SPC_TXT_RIGHT 7
#define SPC_IMG_CASE_BG 8
#define SPC_TAB_NUM_0 9
#define SPC_TAB_NUM_1 10
#define SPC_TAB_NUM_2 11
#define SPC_TAB_NUM_3 12
#define SPC_IMG_CASE 13
#define SPC_CHAR_LEFT 14
#define SPC_CHAR_RIGHT 15
#define SPC_PAGE_0 16
#define SPC_PAGE_1 17
#define SPC_BTN_LEFT 18
#define SPC_BTN_RIGHT 19
#define SPC_BTN_CREATE 20
#define SPC_BTN_JOIN 21
#define SPC_BTN_DEL0 22
#define SPC_BTN_DEL1 23
static const SP_CONTROL SP_CTL[24] = {
    /* IMG_TITLE      */ {216, -6, 354, 50, {9, 0, 0, 354, 50}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* IMG_BAR_LEFT   */ {18, 458, 268, 70, {4, 10, 9, 268, 70}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* ON_LEFT        */ {231, 471, 43, 43, {4, 287, 101, 43, 43}, {4, 287, 101, 43, 43}, {4, 287, 23, 43, 43}},
    /* IMG_BAR_RIGHT  */ {502, 458, 267, 70, {4, 0, 87, 267, 70}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* ON_RIGHT       */ {514, 471, 43, 43, {4, 287, 101, 43, 43}, {4, 287, 101, 43, 43}, {4, 287, 23, 43, 43}},
    /* IMG_INFO       */ {297, 51, 194, 46, {4, 315, 322, 194, 46}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* TXT_LEFT       */ {135, 489, 20, 20, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* TXT_RIGHT      */ {682, 489, 20, 20, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* IMG_CASE_BG    */ {308, 61, 82, 29, {4, 425, 429, 82, 29}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* TAB_NUM_0      */ {318, 65, 16, 19, {4, 322, 410, 16, 19}, {4, 322, 410, 16, 19}, {4, 322, 410, 16, 19}},
    /* TAB_NUM_1      */ {362, 65, 16, 19, {4, 338, 410, 16, 19}, {4, 338, 410, 16, 19}, {4, 338, 410, 16, 19}},
    /* TAB_NUM_2      */ {412, 65, 16, 19, {4, 356, 410, 16, 19}, {4, 356, 410, 16, 19}, {4, 356, 410, 16, 19}},
    /* TAB_NUM_3      */ {451, 65, 16, 19, {4, 372, 410, 16, 19}, {4, 372, 410, 16, 19}, {4, 372, 410, 16, 19}},
    /* IMG_CASE       */ {304, 55, 91, 40, {4, 420, 373, 91, 40}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* CHAR_LEFT      */ {23, 32, 360, 510, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* CHAR_RIGHT     */ {406, 31, 360, 510, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* PAGE_0         */ {309, 59, 83, 30, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* PAGE_1         */ {399, 59, 83, 30, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* BTN_LEFT       */ {2, 256, 31, 47, {4, 239, 322, 31, 47}, {4, 239, 372, 31, 47}, {4, 239, 422, 31, 47}},
    /* BTN_RIGHT      */ {753, 256, 31, 47, {4, 280, 322, 31, 47}, {4, 280, 372, 31, 47}, {4, 280, 422, 31, 47}},
    /* BTN_CREATE     */ {296, 419, 196, 142, {7, 0, 0, 196, 142}, {7, 196, 0, 196, 142}, {7, 392, 0, 196, 142}},
    /* BTN_JOIN       */ {277, 423, 237, 143, {8, 0, 0, 237, 143}, {8, 237, 0, 237, 143}, {8, 474, 0, 237, 143}},
    /* BTN_DEL0       */ {24, 430, 65, 30, {5, 479, 39, 65, 30}, {5, 479, 91, 65, 30}, {5, 479, 91, 65, 30}},
    /* BTN_DEL1       */ {700, 430, 65, 30, {5, 479, 39, 65, 30}, {5, 479, 91, 65, 30}, {5, 479, 91, 65, 30}},
};

#define SPB_BG 0
#define SPB_BTN_OK 1
#define SPB_BTN_NO 2
#define SPB_TEXT_ID 3
#define SPB_TEXT_PASSWORD 4
static const SP_CONTROL SP_BORRAR[5] = {
    /* BG             */ {10, 10, 425, 407, {6, 18, 12, 425, 407}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* BTN_OK         */ {95, 350, 98, 27, {6, 19, 439, 98, 27}, {6, 128, 439, 98, 27}, {6, 237, 439, 98, 27}},
    /* BTN_NO         */ {255, 350, 98, 27, {6, 19, 476, 98, 27}, {6, 128, 476, 98, 27}, {6, 237, 476, 98, 27}},
    /* TEXT_ID        */ {50, 127, 350, 26, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
    /* TEXT_PASSWORD  */ {50, 230, 136, 25, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}, {-1, 0, 0, 0, 0}},
};

