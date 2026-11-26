"""Arma fuente/traducciones.h desde los .json de esta carpeta (★ 26-nov, los idiomas de Ñ2Hock).

  textos.json   {id: texto en español, TAL CUAL está en el .c (con sus %d, \\n…)}
  pt.json ko.json zh.json ja.json   {id: traducción}
  extras.json   {texto en español: [pt, ko, zh, ja]}  (los textos partidos en varias comillas y los nuevos)

Uso:  python armar_tabla.py      (lo corre también compilar.py antes de compilar, si existe)
"""
import json, os, re

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, '..', 'fuente', 'traducciones.h')
IDIOMAS = ['pt', 'ko', 'zh', 'ja']
PH = re.compile(r'%[-+#0]*\d*(?:\.\d+)?(?:l|h)?[diouxXcsSp%]')


def tipos(t):
    """los % de un formato, sin el ancho ni la precisión (%.0s = un %s que no se escribe: el plural del español)"""
    return [re.sub(r'[\d.]', '', p) for p in PH.findall(t)]


def leer(n):
    return json.load(open(os.path.join(AQUI, n), encoding='utf-8'))


def c_literal(t):
    """el texto ya viene con los escapes de C (\\n, \\\\): sólo cuidar las comillas sueltas"""
    t = re.sub(r'(?<!\\)"', r'\\"', t)
    return 'L"' + t + '"'


def main():
    es = leer('textos.json')
    tr = {i: leer(i + '.json') for i in IDIOMAS}
    filas = {}
    for k, t in es.items():
        filas[t] = [tr[i].get(k, '') for i in IDIOMAS]
    for t, v in leer('extras.json').items():
        filas[t] = v
    malos = 0
    for t, v in filas.items():
        for i, x in zip(IDIOMAS, v):
            if x and tipos(x) != tipos(t):
                print('  (!) %s: los %% no coinciden: %r -> %r' % (i, t, x))
                v[IDIOMAS.index(i)] = ''
                malos += 1
    with open(SALIDA, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('/* traducciones.h — GENERADO por herramientas/dll_d3d9/traducciones/armar_tabla.py: no editar a mano */\n')
        f.write('#define TR_N %d\n' % len(filas))
        f.write('static const wchar_t *const TR_TABLA[TR_N][TR_N_IDIOMAS] = {\n')
        for t, v in filas.items():
            f.write('    { ' + ', '.join([c_literal(t)] + [c_literal(x) if x else 'NULL' for x in v]) + ' },\n')
        f.write('};\n')
    print('traducciones.h: %d textos (%d sin traducir por los %%)' % (len(filas), malos))


if __name__ == '__main__':
    main()
