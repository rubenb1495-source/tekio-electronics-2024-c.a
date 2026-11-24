# SPEC: Fase 1 - Seguridad (RBAC), Tasas Diarias y Catálogo Normalizado - Tekio Electronics

## 1. Objetivo del Módulo
- **Qué resuelve:** Establece la base centralizada del sistema: control de acceso por roles (para ocultar costos a asesoras y técnicos), gestión inmutable de tasas diarias (BCV, USDT y recargo) y catálogo maestro con SKUs normalizados e historial de precios.
- **Tipo de tarea:** Refactorización con mejoras (reemplaza el archivo `TEKIO · Configuración` en Google Sheets).
- **Código legacy de referencia:** `../tekio-erp` (revisado en `CONTEXT.md`; el proyecto nuevo en `tekio-admin` parte limpio).

## 2. Arquitectura y Alcance
- **Backend asignado:** **Python / FastAPI** (con Pydantic para validación estricta y tipado), centralizando en esta Fase 1 `auth`, `usuarios`, `sucursales`, `tasas` y `catalogo` en `/backend-python`.
- **Frontend (Next.js en `/frontend`):**
  - `/login`: Inicio de sesión.
  - `/dashboard/usuarios`: Gestión de usuarios, roles y sucursal asignada (solo `DIRECCION` / `ADMINISTRACION`).
  - `/dashboard/tasas`: Panel de tasas del día (BCV, USDT, brecha y `% recargo`) e historial.
  - `/dashboard/catalogo`: Gestión de componentes, accesorios, servicios y modelos base con historial de precios.
- **Base de datos (PostgreSQL — Tablas/Modelos):**
  - `sucursales` (`id`, `nombre`, `direccion`, `estado`: `ACTIVA` | `CERRADA`, `fecha_cierre`)
  - `usuarios` (`id`, `nombre`, `correo`, `clave_hash`, `rol`, `sucursal_id`, `activo`, `creado_en`)
  - `tasas_diarias` (`id`, `fecha` [única], `tasa_bcv`, `tasa_usdt`, `recargo_porcentaje`, `origen`: `AUTOMATICO` | `MANUAL`, `publicado_por_id`, `nota`, `actualizado_en`)
  - `catalogo_articulos` (`id`, `sku` [único, normalizado], `descripcion`, `tipo`: `EQUIPO` | `COMPONENTE` | `ACCESORIO` | `SERVICIO`, `categoria`, `activo`, `creado_en`)
  - `catalogo_precios` (`id`, `articulo_id`, `precio_promo_usd`, `precio_regular_fijo_usd` [opcional], `costo_referencia_usd` [opcional], `fecha_vigencia`, `creado_por_id`)

## 3. Contratos de API (Endpoints)

### Autenticación y Usuarios
| Método | Ruta | Entrada (Body/Params) | Salida esperada |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/login` | `{ correo, clave }` | `{ token, usuario: { id, nombre, rol, sucursal } }` |
| `GET` | `/api/usuarios` | `rol`, `activo` | Lista de usuarios (solo `DIRECCION` / `ADMINISTRACION`) |
| `POST` | `/api/usuarios` | `{ nombre, correo, clave, rol, sucursal_id }` | Usuario creado (`201`) |
| `PATCH` | `/api/usuarios/:id/estado` | `{ activo, motivo }` | Usuario actualizado (`200`) |

### Tasas Diarias
| Método | Ruta | Entrada (Body/Params) | Salida esperada |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/tasas/hoy` | — | Tasa vigente de hoy + brecha `%` + bandera `permite_bolivares` |
| `GET` | `/api/tasas` | `desde`, `hasta`, `pagina` | Historial paginado de tasas |
| `POST` | `/api/tasas` | `{ fecha, tasa_bcv, tasa_usdt, recargo_porcentaje, nota }` | Tasa registrada (`201`). Bloquea edición si `fecha < hoy` |
| `PUT` | `/api/tasas/hoy` | `{ tasa_bcv?, tasa_usdt?, recargo_porcentaje?, nota? }` | Actualiza tasa de hoy y marca `origen: MANUAL` (`200`) |

### Catálogo y Precios
| Método | Ruta | Entrada (Body/Params) | Salida esperada |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/catalogo` | `busqueda`, `tipo`, `categoria`, `pagina` | Lista con precio vigente (`costo_referencia_usd` **omitido** si rol es `ASESORA` o `TECNICO`) |
| `POST` | `/api/catalogo` | `{ sku, descripcion, tipo, categoria, precio_promo_usd, precio_regular_fijo_usd? }` | Artículo + precio inicial creados (`201`) |
| `POST` | `/api/catalogo/:id/precios` | `{ precio_promo_usd, precio_regular_fijo_usd?, costo_referencia_usd?, fecha_vigencia }` | Nueva versión de precio registrada (`201`) |
| `GET` | `/api/catalogo/:id/precios` | — | Historial completo de precios del artículo |

## 4. Reglas de Negocio Clave
- **Roles válidos (RBAC):** `DIRECCION`, `ADMINISTRACION`, `LOGISTICA`, `LIDER`, `ASESORA`, `TECNICO`.
- **Protección de costos en Backend:** El campo `costo_referencia_usd` (y cualquier costo futuro) debe **filtrarse en el esquema de respuesta del backend** según el rol del JWT; nunca confiar solo en ocultarlo en el frontend.
- **Sucursales precargadas (Seed):** `Bodega`, `Tekio central`, `Gran Bazar` (`ACTIVA`); `INFOT` (cierre `2026-11-08`) y `Free Market C13` (cierre `2026-11-16`) en estado `CERRADA`.
- **Inmutabilidad de tasas:** Nunca permitir modificar ni eliminar tasas de fechas pasadas. Si no existe registro para la fecha actual, `GET /api/tasas/hoy` debe devolver `permite_bolivares: false` y una alerta visible. Si no se carga `% recargo`, heredar automáticamente el del último día registrado.
- **Normalización estricta de SKU:** Al crear o buscar un SKU, transformar automáticamente con `trim()`, convertir a **MAYÚSCULAS** y reemplazar espacios internos por guiones (`-`). Rechazar con `409 Conflict` cualquier SKU duplicado.
- **Inmutabilidad de precios:** Para cambiar un precio nunca se sobrescribe el registro anterior; se inserta una nueva fila en `catalogo_precios` con `fecha_vigencia`. El precio vigente es el más reciente cuya `fecha_vigencia <= hoy`.
- **Cálculo de Precio Regular:** Si `precio_regular_fijo_usd` es nulo, calcular en vivo: `precio_promo_usd * (1 + recargo_porcentaje / 100)`.
- **Idioma:** Todo en español (tablas, columnas, rutas, variables, mensajes de error).

## 5. Interfaz y Componentes (Next.js)
- **Barra superior global (Layout):** Mostrar siempre la tasa BCV, tasa USDT y `% recargo` de hoy (o alerta roja *"Sin tasa del día — Cobros en Bs bloqueados"* si falta).
- **Vista `/dashboard/tasas`:** Tarjetas de resumen del día (BCV, USDT, Brecha %, Recargo %), formulario rápido de carga/actualización manual (solo `DIRECCION`/`ADMINISTRACION`) y tabla histórica.
- **Vista `/dashboard/catalogo`:** Buscador instantáneo por SKU o descripción, filtros por tipo/categoría, tabla con columnas `SKU`, `Descripción`, `Promo USD`, `Regular USD`, `Regular Bs` (calculado con tasa BCV de hoy), modal de creación y modal de *"Actualizar precio"* con historial visible.
- **Estados obligatorios:** *Skeleton* de carga, estado vacío con acción rápida, alertas de error de red y validación de formularios en español.

## 6. Criterios de Aceptación (Definición de Terminado)
- [ ] Seed inicial creado con las 5 sucursales reales de Tekio y un usuario `DIRECCION` de prueba.
- [ ] Un usuario con rol `ASESORA` o `TECNICO` no recibe ningún campo de costo en el JSON de `/api/catalogo` ni puede acceder a `/dashboard/usuarios`.
- [ ] Intentar crear un SKU duplicado (ej. `bat-33ydh` cuando existe `BAT-33YDH`) devuelve error `409` en español.
- [ ] Intentar modificar una tasa de ayer o anterior devuelve error `403` o `400`.
- [ ] Cambiar el precio de un artículo conserva el precio anterior en su historial.
- [ ] Frontend conectado al backend real sin datos quemados, sin errores de compilación TypeScript ni advertencias en consola.
- [ ] `CONTEXT.md` actualizado marcando el avance de la Fase 1.

## 7. Restricciones para Antigravity
- **No tocar:** Módulos de ventas, inventario o taller fuera del alcance de esta Fase 1.
- **No borrar datos:** Implementar borrado lógico (`activo: false`) en usuarios y catálogo.
- **Dependencias:** Usar las librerías ya presentes en el repositorio; consultar antes de agregar paquetes nuevos.
