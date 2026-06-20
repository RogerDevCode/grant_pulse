# Resumen de acciones realizadas hoy (2026-06-19)

## Contexto
Se está trabajando en el proyecto GrantPulse, un sistema de monitoreo de fondos de financiamiento gubernamentales chilenos.
Se intenta levantar los servicios mediante Docker Compose, específicamente el servicio de API.

## Problema principal
El contenedor de la API falla al iniciar con el error:
```
[FATAL tini (7)] exec /app/.venv/bin/uvicorn failed: No such file or directory
```

## Acciones realizadas

1. **Revisión del Dockerfile y pyproject.toml**:
   - Se confirmó que el Dockerfile utiliza una construcción multietapa (builder/runtime) con `uv` para la gestión de dependencias.
   - Se verificó que el `pyproject.toml` define los scripts de entrada (`grantpulse-api`, etc.) bajo `[project.scripts]`.

2. **Intento de corregir la falta de scripts de entrada**:
   - Se añadió `[tool.uv] package = true` al `pyproject.toml` para que `uv` instale los puntos de entrada definidos en `[project.scripts]`.
   - Se reconstruyó la imagen de la API después de este cambio.

3. **Verificación de la existencia de los binarios**:
   - Se comprobó que el binario `uvicorn` existe dentro del entorno virtual de la imagen (`/app/.venv/bin/uvicorn`) y que tiene los permisos de ejecución.
   - Se confirmó que el `shebang` del script `uvicorn` apunta al intérprete de Python correcto dentro del entorno virtual.

4. **Prueba directa del binario**:
   - Se ejecutó el contenedor de la API de forma aislada y se verificó que `/app/.venv/bin/uvicorn --version` funciona correctamente cuando se invoca mediante `/app/.venv/bin/python`.

5. **Análisis del punto de entrada (Entrypoint)**:
   - El contenedor utiliza `tini` como proceso inicial (PID 1) y luego intenta ejecutar el comando especificado.
   - El error indica que `tini` no puede encontrar o ejecutar `/app/.venv/bin/uvicorn`, a pesar de que el archivo existe y es ejecutable.

6. **Hipótesis considerada**:
   - Posible problema de arquitectura binaria o de enlaces dinámicos faltantes dentro del entorno mínimo de `python:3.13-slim`.
   - Sin embargo, al ejecutar el binario directamente dentro del contenedor (con `docker run`) funciona, lo que sugiere que el problema podría estar en cómo se está invocando el comando mediante `tini` o en la configuración del `CMD` en el Dockerfile vs. el `command` en el `docker-compose.yml`.

7. **Ajustes en docker-compose.yml**:
   - Se eliminó la sobrescritura del `command` en el servicio `api` para permitir que se use el `CMD` definido en el Dockerfile (que es `/app/.venv/bin/grantpulse-api`).
   - Cuando eso falló (mismo error pero con `grantpulse-api`), se volvió a usar un `command` explícito para ejecutar `uvicorn` directamente.
   - Se intentó eliminar el montaje de volúmenes (`.:/app:cached`) para descartar problemas de permisos o de sistema de archivos montado, pero el error persistió.

8. **Estado actual**
- El servicio de la base de datos (`db`) está saludable y en ejecución.
- El servicio de la API (`api`) está corriendo correctamente y respondiendo de forma saludable (HTTP 200) tras solucionar la colisión de entornos virtuales.

## Diagnóstico y Solución
El problema se debía a que `docker-compose.yml` montaba el directorio del host `.` directamente en `/app` del contenedor mediante `.:/app:cached`. Este montaje sobrescribía el entorno virtual `.venv` interno que Docker construye e instala durante la fase de build. 
El archivo `.venv/bin/uvicorn` del host contenía un shebang absoluto local (`#!/home/manager/Sync/python_proyects/grant_pulse/.venv/bin/python`), el cual no existía dentro del contenedor, provocando que `tini` retornara el error `No such file or directory` (código de salida 127).

**Solución aplicada:**
Se agregaron montajes de volúmenes anónimos en los servicios `api` y `worker` del archivo `docker-compose.yml` para evitar que el directorio `.venv` local del host pise al del contenedor:
```yaml
    volumes:
      - .:/app:cached
      - /app/.venv
```

## Próximos pasos
1. Monitorear los logs en desarrollo para asegurar que no ocurran otros problemas derivados de diferencias de librerías.
2. Confirmar que el `worker` también funciona correctamente ejecutando comandos a través del CLI en el contenedor.

## Conclusión
La separación física del entorno virtual del host y del contenedor mediante volúmenes anónimos solucionó el error de ejecución de `uvicorn` (y por consiguiente de `grantpulse-api`). El backend se encuentra completamente operacional y conectando a la base de datos PostgreSQL.
