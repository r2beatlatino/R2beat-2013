# -*- coding: utf-8 -*-
"""El servidor 2013 de R2Beat.

Para arrancarlo:  py startserver.py
Para saber qué archivo abrir:  servidor/MAPA.md

⚠ Este `__init__` NO re-exporta nada a propósito. Antes hacía `from .lobby import *`, y
  eso, combinado con arrancar `lobby.py` como script, dejaba DOS copias del módulo con
  globals distintos: el arranque llenaba una y los armadores de paquetes leían la otra.
  Así llegó el picker de música vacío el 2026-09-02. Cada módulo se importa por su
  nombre (`from servidor import notas`), que además dice de dónde sale cada cosa.
"""
