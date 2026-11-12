# El server de R2Beat 2013 en un contenedor (Linux). Sólo el server: el juego corre en Windows, en la
# PC de cada jugador.
#
#   docker compose -p r2b-prueba --env-file /opt/r2b2013/prueba.env -f despliegue/docker-compose.yml up -d --build
#
# ⛔ Las tablas y las notas del juego (de Softnyx) NO van en la imagen: se montan en /r2b/juego
#    (ver despliegue/LEEME.md). Las cuentas van en /r2b/datos, AFUERA del contenedor.
FROM python:3.12-slim

WORKDIR /r2b
COPY servidor/ servidor/
COPY correr_servidor.py ./
COPY pruebas/ pruebas/
COPY despliegue/arrancar.sh ./

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    R2_GM_ARCHIVO=/r2b/datos/gm.txt

# ¿anda? = el server arranca y una cuenta de prueba entra por la red, como el juego (con sus reveses).
# Si falla, la imagen no se arma, y el contenedor que andaba sigue andando.
RUN python pruebas/probar_login.py > /tmp/prueba.txt 2>&1 || (cat /tmp/prueba.txt; exit 1)

# ¿contesta? = el puerto de login abre
HEALTHCHECK --interval=1m --timeout=10s --start-period=30s \
    CMD python -c "import os,socket; socket.create_connection(('127.0.0.1', int(os.environ.get('R2_LOGIN_PUERTO') or 48004 + int(os.environ.get('R2_PUERTOS') or 0))), 5).close()"

CMD ["bash", "/r2b/arrancar.sh"]
