/* grande_datos.h — GENERADO por herramientas/carrera_grande.py desde el exe PRÍSTINO. No editar a mano.
 *   Los «6» del motor de carrera del 2013 que grande.c pasa a N (documentacion/MODO_6VS6.md). */

/* el byte del 6 en «cmp reg, 6»: el 1.º es la CREACIÓN de los corredores, los demás los bucles */
static const DWORD GR_SEIS[42] = {
    0x4FA1D4, 0x4EA5D5, 0x4EA6B4, 0x4EB65D, 0x4EBA28, 0x4ECEC2,
    0x4ED942, 0x4EDA85, 0x4EDBE1, 0x4EDC9F, 0x4EDE84, 0x4EDF15,
    0x4EE4D7, 0x4F12F6, 0x4F136F, 0x4F174E, 0x4F1815, 0x4F19B2,
    0x4F1AE1, 0x4F3334, 0x4F3844, 0x4F3A20, 0x4F3A78, 0x4F4247,
    0x4F59CA, 0x4F5C1A, 0x4F5E0F, 0x4F7619, 0x4F7737, 0x4F7A0C,
    0x4F7C39, 0x4FD13A, 0x4FD1DC, 0x4FD22D, 0x4FDD9C, 0x54D2ED,
    0x563918, 0x56B8AD, 0x56B99F, 0x56BF59, 0x56E2ED, 0x56F54D,
};

/* los f-op que leen el 3.0 (la mitad) y el 223.5 (el carril): la dirección del operando = sitio + 2 */
static const DWORD GR_MITAD[4] = { 0x4EAC00, 0x4EAC8D, 0x5016BD, 0x5016E7, };
static const DWORD GR_PASO[6] = { 0x4EAC1D, 0x4EAC99, 0x5016C9, 0x5016F3, 0x501F18, 0x501F20, };
#define GR_DIR_TRES 0x87BC38
#define GR_DIR_PASO 0x87BC30
