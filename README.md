# Sistema Administrativo Tekio Electronics

Sistema administrativo integral para la gestión operativa interna de **Tekio Electronics**.

## Estructura del repositorio

- `/frontend`: Aplicación web en Next.js / React con TypeScript (`pnpm`).
- `/backend-node`: Servicios en Node.js con TypeScript (`pnpm`).
- `/backend-python`: API y servicios en Python con FastAPI y Pydantic (`uv`).
- `docker-compose.yml`: Orquestación de contenedores (PostgreSQL y servicios).
- `CONTEXT.md`: Archivo maestro de contexto, reglas y decisiones de arquitectura.

## Convenciones del proyecto

- **Idioma:** Todo el código, comentarios, documentación, commits e interfaz se escriben en **español**.
- **Tipado:** TypeScript en frontend/Node.js y *type hints* + Pydantic en Python.
- **Dependencias:** Consultar antes de instalar nuevas librerías o actualizar versiones principales.

## Arranque rápido (Base de datos)

1. Copia `.env.example` a `.env` y ajusta las credenciales.
2. Levanta PostgreSQL con Docker Compose:

```bash
docker compose up -d base_datos
```
