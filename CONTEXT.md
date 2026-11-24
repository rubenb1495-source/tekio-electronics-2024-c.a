# CONTEXT.md - Sistema Administrativo Tekio Electronics

## 1. Resumen y Objetivo
- **Empresa:** TEKIO ELECTRONICS 2024, C.A. (RIF: `J-50637518-4`).
- **Qué hace:** Sistema administrativo integral para la gestión operativa, inventario por serial, logística de importación, taller, ventas multimoneda, caja chica, bancos, conciliación y comisiones.
- **Usuario final:** Dirección, Administración, Logística, Taller y Asesoras de ventas (8 roles: Dirección, Administración, Compras, Supervisor, Asesor, Caja, Depósito, Taller).
- **Estado actual:** Auditoría inicial completada; migración y refactorización desde el sistema heredado (`../tekio-erp` / Google Sheets) hacia aplicación web centralizada (`tekio-admin`).

## 2. Stack Tecnológico

### Sistema actual heredado (`../tekio-erp`)
- **Frontend:** React `19.1.0` + Vite `6.3.5` + TypeScript `5.8.3` (`strict: false`) + Tailwind CSS `4.1.7` (`@tailwindcss/vite`) + Recharts `2.15.3` + `lucide-react` `0.511.0`.
- **Backend:** Monolito en Node.js `22` (ESM) con Express `5.1.0`, `cors` `2.8.5`, `multer` `1.4.5-lts.2` y `xlsx` `0.18.5` (en JavaScript plano, sin TypeScript ni validación de esquemas). **No existe backend en Python/FastAPI todavía.**
- **Base de datos y ORM/ODM:** SQLite nativo (`node:sqlite` / `DatabaseSync` en modo WAL) en `../tekio-erp/data/tekio_erp.db` (~393 KB, 28 tablas). Sin ORM ni motor de migraciones.
- **Gestor de paquetes:** `npm` (`package-lock.json`).
- **Infraestructura / Deploy:** Dockerfile multi-etapa (`node:22-alpine`) desplegado en Render (`render.yaml`, plan `free` sin disco persistente) sirviendo SPA estática + API en el puerto `3002`/`10000`.

### Arquitectura objetivo (`tekio-admin`)
- **Frontend:** Next.js `15.5` + React `19.1` + TypeScript `5.8` (`strict: true`) + Tailwind CSS `4.1` + `lucide-react` (`npm`).
- **Backend / Servicios:** Python `3.15` + FastAPI `0.165` + SQLAlchemy `2.1` + Pydantic `2.14` + PyJWT + `psycopg` (`venv`/`pip`, listo para despliegue en Vercel). Node.js reservado para servicios futuros en `/backend-node`.
- **Base de datos:** PostgreSQL (Vercel Postgres / Neon vía `URL_BASE_DATOS` o `POSTGRES_URL`, con respaldo SQLite local en desarrollo cuando la variable está vacía).
- **Infraestructura / Deploy:** Vercel (frontend + API Python) y `docker-compose.yml` opcional para PostgreSQL/VPS.
- **Gestor de paquetes:** `npm` para JS/TS y `venv`/`pip` para Python (actualizado según entorno local aprobado).

## 3. Estructura Clave

### Repositorio nuevo (`C:\Users\HomePC\.gemini\antigravity\scratch\tekio-admin`)
- `/frontend`: Aplicación Next.js (App Router + TypeScript estricto) con 24 rutas:
  - Fase 1: `/login`, `/dashboard/usuarios`, `/dashboard/tasas`, `/dashboard/catalogo` y barra superior global de tasas.
  - Fase 2: `/dashboard/logistica/compras`, `/dashboard/logistica/guias`, `/dashboard/logistica/recepcion`, `/dashboard/logistica/traslados`, `/dashboard/logistica/inventario`.
  - Fase 3: `/dashboard/taller/preparaciones`, `/dashboard/taller/casos`, `/dashboard/taller/repuestos`, `/dashboard/taller/mi-resumen`.
  - Fase 4: `/dashboard/ventas/nueva`, `/dashboard/ventas`, `/dashboard/devoluciones`, `/dashboard/finanzas/pagos`, `/dashboard/finanzas/cashea`, `/dashboard/finanzas/conciliacion`, `/dashboard/finanzas/comisiones`.
- `/backend-python`: API FastAPI (`app/main.py`, `app/modelos*.py`, `app/esquemas*.py`, `app/seguridad.py`, `app/semilla*.py`, `app/servicios/pdf_nota.py`, `app/rutas/*`, `tests/test_fase1..4.py`, `vercel.json`). Dependencias: FastAPI, SQLAlchemy, Pydantic, PyJWT, `psycopg`, `openpyxl`, `pandas`, `python-multipart`, `reportlab`.
- `/backend-node`: Carpeta preparada para servicios futuros en Node.js.
- `/docs/SPEC_FASE_1.md` .. `SPEC_FASE_4.md`: Especificaciones funcionales completas de Fases 1 a 4.
- `normalizar_skus_tekio.py`, `migrar_desde_tekio_erp.py` y `/salida_limpia`: Scripts idempotentes de limpieza de SKUs y migración histórica desde `../tekio-erp/data/tekio_erp.db` (solo lectura) hacia SQLAlchemy (`--dry-run` y `--aplicar`).
- `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md`, `CONTEXT.md`: Infraestructura base y contexto maestro.

### Rutas heredadas protegidas (NO modificar durante la migración)
- `../tekio-erp/server/index.js` *(crítico / legacy)*: Monolito de 2,577 líneas con ~65 endpoints API, autenticación HMAC incompleta, lógica de negocio financiera/inventario y exportación Excel.
- `../tekio-erp/server/db.js` *(crítico / legacy)*: Esquema de 28 tablas SQLite (877 líneas), migraciones ad-hoc y semillas (`seedIfEmpty`).
- `../tekio-erp/server/templates.js` *(legacy)*: Definición y parseo de plantillas Excel para carga masiva (`xlsx`).
- `../tekio-erp/server/migrate-tekio.cjs` *(legacy)*: Script de migración de datos históricos desde Excel.
- `../tekio-erp/data/tekio_erp.db` y `../tekio-erp/data/uploads/` *(crítico — datos vivos)*: Base de datos SQLite activa y archivos subidos.
- `../tekio-erp/src/` *(legacy)*: 14 páginas (`src/pages/`) y 10 componentes (`src/components/`). Páginas huérfanas no montadas en `App.tsx`: `Deposito.tsx`, `CargaMasiva.tsx`, `NotasReportes.tsx`.
- `../tekio-control-ventas/` *(respaldo histórico — solo lectura)*: Hojas de cálculo Excel y PDFs operativos históricos de Tekio.

## 4. Reglas y Convenciones de Código
- **Idioma:** **Todo en español** (variables, funciones, rutas, componentes, comentarios, commits, documentación y mensajes de interfaz).
- **Tipado estricto:** TypeScript en frontend/Node.js y Pydantic (*type hints*) en FastAPI.
- **Normalización de SKUs:** Todos los códigos de componentes/accesorios/servicios deben almacenarse en **MAYÚSCULAS, sin espacios y sin duplicados** (resolver inconsistencias heredadas como `BAT-33YDH` vs `bat-dell33ydh`).
- **Migración segura:** No eliminar lógica heredada (`../tekio-erp`) sin confirmar que el reemplazo cumple los criterios de aceptación.
- **Dependencias:** Consultar antes de instalar librerías nuevas.

## 5. Reglas de Negocio (Dominio Tekio Electronics)

### 5.1 Principios Inmutables
- **Nada se borra:** Los cambios de precios se registran con nueva fecha de vigencia para no alterar ventas pasadas. Las ventas o movimientos erróneos se **anulan con motivo obligatorio** y se corrigen con un registro nuevo.
- **El serial es la cédula del equipo:** Cada equipo (laptops, etc.) se rastrea individualmente por número de serial único (no se puede vender un serial ya vendido). Componentes, accesorios y servicios se controlan por código/SKU y cantidad.
- **Doble control:** Recepciones de mercancía, traspasos de dinero y cierres de caja requieren validación de dos personas (quien entrega/recibe y quien verifica/supervisa).

### 5.2 Sucursales y Ubicaciones
- **Activas:**
  - `Bodega` (almacén central y recepción de compras/guías).
  - `Tekio central` (Av. Universidad, CC Free Market, locales X47-X48, Naguanagua, Valencia).
  - `Gran Bazar` (CC Gran Bazar, Centro, local ML174, Valencia).
- **Cerradas (solo histórico y cobro de saldos pendientes; bloqueadas para nuevas ventas):**
  - `INFOT` (cerrada desde 08/11/2026).
  - `Free Market C13` (cerrada desde 16/11/2026).
- **Mejora obligatoria en traslados:** Implementar flujo en 2 pasos (`En tránsito` → `Recibido`) para que el inventario no quede vendible en destino hasta confirmar recepción física.

### 5.3 Tasas del Día, Monedas y Diferencial Cambiario
- **Tasas diarias:** Tasa **BCV** (6:00 am), tasa **USDT** (Binance P2P: 6:00 am, 8:00 am, 1:00 pm y 4:00 pm) y **`% de recargo del día`** (definido por Administración).
- **Bloqueo operativo:** Sin tasa del día registrada **no se pueden cobrar montos en bolívares**.
- **Congelamiento histórico:** Nunca editar tasas de días pasados; cada transacción guarda la tasa y el recargo vigentes al momento de registrarse.
- **USD Nominal vs. USD Real:**
  - `USD Nominal`: Bolívares convertidos a tasa BCV.
  - `USD Real`: Divisas tal cual + bolívares convertidos a tasa USDT.
  - `Diferencial cambiario`: Diferencia entre USD Nominal y USD Real.
- **Ganancia real USD:** Cobrado a su valor real (sin IVA ni IGTF) menos el costo total del equipo/artículo.

### 5.4 Precios, Pagos Mixtos, Cashea y Devoluciones
- **Precio Promo:** Aplica para divisas (`Efectivo USD`, `Zelle`, `Zinli`, `PayPal`, `Banesco Panamá`) y `Binance (USDT)`.
- **Precio Regular:** Aplica para bolívares (`Punto de venta Banesco`, `Pago móvil Mercantil`, `BNC Jurídico`) y `Cashea`. Fórmula: `Precio Promo × (1 + % recargo del día)` (salvo que exista un precio regular fijo o recargo especial aprobado).
- **Pagos mixtos:** El sistema debe calcular y repartir automáticamente la proporción cubierta a Promo y la cubierta a Regular sin límite de artículos ni métodos de pago por venta.
- **Cashea:** Toda venta con Cashea va a **Precio Regular**. La inicial se registra en su método de cobro; lo financiado entra en `Cashea · financiado` y genera cuenta en `Por Cobrar Cashea`. Al liquidar Cashea, se calcula a tasa BCV del día de pago, registrando traslado al banco, comisión e impuestos.
- **Parte de pago:** Método `Equipo como parte de pago` con valor reconocido en USD y serial del equipo recibido, que ingresa al inventario con origen `Parte de pago`.
- **Devoluciones y cambios (mejora):** Gestionar en módulo propio (Nota de Crédito) en lugar de cantidad `-1` en ventas, reingresando el serial al estado `Por preparar` o `Garantía`.
- **Validación de pagos digitales (mejora):** Flujo `Pendiente de verificación` → `Confirmado` por Administración para transferencias, Pago Móvil, punto y pagos digitales.

### 5.5 Logística, Taller y Garantías
- **Costo real del equipo:** `Costo de compra + flete prorrateado por valor (guía Miami) + componentes instalados en taller + pago de preparación`.
- **Estados de equipo:** `Por preparar` → `Listo` (vendible) | `Hospital` (esperando repuesto) | `Cementerio` (baja) | `Vendido`.
- **Conexión Taller-Logística (mejora):** Al pasar un equipo a `Hospital` indicando repuesto faltante, generar alerta automática en `Repuestos por comprar` y notificar al técnico al recibirlo.
- **Casos de postventa:**
  - `GT` (Garantía): Cobertura de 180 días por defectos de fábrica.
  - `ST` (Servicio Técnico): Requiere enviar presupuesto (mano de obra + repuestos).

## 6. Decisiones de Arquitectura
- `2026-11-24` - Inicio del archivo maestro de contexto para coordinar la refactorización entre Gemini (diseño/planificación) y Antigravity (ejecución en código).
- `2026-11-24` - Centralización de las Fases 1 a 4 en **Python / FastAPI** (`/backend-python`) con SQLAlchemy + Pydantic y **Next.js 15 + TypeScript estricto** (`/frontend`), usando `npm` y `venv`/`pip` (ajustado al entorno local disponible) y `reportlab` para Notas de Entrega en PDF.
- `2026-11-24` - Despliegue objetivo en **Vercel** con PostgreSQL (`POSTGRES_URL` / `URL_BASE_DATOS`) y respaldo SQLite local automático para pruebas cuando la variable está vacía.
- `2026-11-24` - Unificación de alias de SKUs confirmados del catálogo histórico (`BAT-DELL33YDH` → `BAT-33YDH` y `BAT-DELL6MT4T` → `BAT-6MT4T`), reduciendo la hoja `Catálogo` a **27 SKUs canónicos únicos**.
- `2026-11-24` - Catálogo definitivo de **14 instrumentos financieros** aprobado y sincronizado en `app/semilla_finanzas.py` (`Efectivo divisas`, `Binance (USDT)`, `Zelle`, `Zinli`, `PayPal`, `Banesco Panamá`, `Bancamiga (USD)`, `Punto de venta Banesco (Bs)`, `Pago móvil Mercantil (Bs)`, `BNC Jurídico (Bs)`, `Bancamiga (Bs)`, `Cashea · financiado`, `Equipo como parte de pago`, `Cuenta por cobrar`).

## 7. Estado Actual (Handoff)

### Módulos funcionales identificados en el sistema heredado (`../tekio-erp`)
1. **Autenticación, Usuarios y Sedes:** `LoginPortal.tsx`, `UsuariosSedes.tsx`, `/api/auth/*`, `/api/usuarios`, `/api/sedes`.
2. **Tablero Gerencial y Tasas:** `Dashboard.tsx`, `/api/dashboard`, `/api/tasas`, `/api/parametros`, `/api/logo`.
3. **Ventas / POS y Cobranzas (CxC / Cashea / Parte de pago):** `Ventas.tsx`, `CobroAbonosModal.tsx`, `QuickDocWhatsApp.tsx`, `/api/ventas`, `/api/cxc/*`, `/api/pagos/liquidar-cashea`.
4. **Inventario por Seriales, Depósito y Despachos:** `Inventario.tsx`, `DespachosAlmacen.tsx`, `Deposito.tsx` *(huérfana)*, `/api/inventario`, `/api/trazabilidad/:serial`, `/api/despachos`, `/api/deposito/*`.
5. **Compras, Importaciones y Tracking Courier:** `ComprasTracking.tsx`, `ComprasCaja.tsx`, `/api/compras`, `/api/trackings`, `/api/guias`, `/api/pagos/pagar-proveedor`.
6. **Caja, Bancos y Conciliación Bancaria:** `ComprasCaja.tsx`, `LibroBancoConciliacion.tsx`, `/api/caja`, `/api/instrumentos`, `/api/estados-cuenta`, `/api/conciliacion*`.
7. **Cambios de Divisas (Bs ↔ USD/USDT/Zelle):** `CambiosDivisas.tsx`, `CambioVoucherModal.tsx`, `/api/cambios*`.
8. **Gastos, Arqueo de Caja, Cierres y Comisiones:** `GastosCierres.tsx`, `ParametrosComisiones.tsx`, `MiMetaComisiones.tsx`, `/api/gastos`, `/api/cierre-caja`, `/api/cierres/*`, `/api/comisiones`, `/api/asesores-comisiones`, `/api/personal`.
9. **Libros Administrativos y Auditoría:** `LibrosAdmin.tsx`, `/api/libros`, `/api/bitacora`.
10. **Taller Técnico y Garantías:** `Taller.tsx`, `RecepcionGarantias.tsx`, `/api/taller*`, `/api/garantia/verificar/:serial`.
11. **Supervisión, Reportes y Carga Masiva Excel:** `SupervisorHub.tsx`, `DepartmentBulkUpload.tsx`, `CargaMasiva.tsx` *(huérfana)*, `NotasReportes.tsx` *(huérfana)*, `/api/supervisor/*`, `/api/bulk/*`.

### En progreso
- [x] Auditoría inicial y diagnóstico técnico del sistema heredado (`../tekio-erp`).
- [x] Integración de las reglas de negocio oficiales del dominio Tekio Electronics.
- [x] **Fase 1 completada:** Seguridad (RBAC con JWT), Tasas Diarias inmutables y Catálogo Normalizado con historial de precios.
- [x] **Fase 2 completada:** Logística, Compras (manual y Excel/CSV), Guías con prorrateo automático de flete, Recepción por serial con doble verificación, Traslados en 2 pasos, Inventario/Kardex/Trazabilidad y Ajustes con aprobación de Dirección.
- [x] **Fase 3 completada:** Taller, Preparaciones por Serial, conexión `HOSPITAL` ↔ `repuestos_solicitados`, Casos `GT`/`ST` y Resumen Mensual del Técnico sin costos.
- [x] **Fase 4 completada:** Ventas Multimoneda (POS pagos mixtos y Cashea), Nota de Entrega PDF (`reportlab`), Devoluciones (Notas de Crédito), Verificación de Pagos/CxC, Conciliación Bancaria CSV/Excel, Comisiones exactas y Cierre Mensual inmutable (`pytest` 14/14 y `next build` 24/24 en verde).
- [x] **Normalización de SKUs ejecutada:** `normalizar_skus_tekio.py` procesó `TEKIO · Configuración.xlsx` (`32` filas → `27` SKUs canónicos limpios en `./salida_limpia`).
- [x] **Migración histórica completada e idempotente (`migrar_desde_tekio_erp.py --aplicar`):** migrados `27` SKUs, `146` terceros, `51` tasas, `144` equipos (`103` `LISTO`, `33` `VENDIDO`, `8` `CEMENTERIO`), `149` ventas (`172` líneas detalle, `\$28,555.38` Promo exacto), `145` pagos y `45` CxC (`\$747.00` clientes exacto; `\$5,169.88` Cashea por redondeo de `+\$0.02` desde `REAL`). Segunda pasada verificada con `0` duplicados y `pytest` 14/14 en verde.
- [x] **Despliegue en producción verificado en Vercel + Neon PostgreSQL:**
  - Repositorio GitHub: `https://github.com/rubenb1495-source/tekio-electronics-2024-c.a.git` (`main`).
  - Frontend (`tekio-admin`): `https://tekio-admin-two.vercel.app` (login y dashboard verificados extremo a extremo).
  - Backend (`tekio-admin-api`): `https://tekio-admin-api.vercel.app` (`/api/salud` -> `200 OK`).
  - Base de datos: Neon Serverless Postgres (`tekio-admin-db`) conectada vía `POSTGRES_URL`.
- [x] **Migración histórica aplicada en producción (Neon PostgreSQL `tekio-admin-db`):** `migrar_desde_tekio_erp.py --aplicar` ejecutado y confirmado atómicamente contra Neon (`27` SKUs, `146` terceros, `51` tasas, `144` equipos, `149` ventas / `172` líneas por `\$28,555.38` Promo, `149` pagos, `45` CxC con `\$747.00` clientes y `\$5,169.88` Cashea). Verificado en vivo en `https://tekio-admin-api.vercel.app` (`/api/catalogo` → `27`, `/api/logistica/inventario/equipos` → `144`, `/api/finanzas/cuentas-por-cobrar` → `45`, `/api/tasas` → `51`, `/api/finanzas/tablero` → `cashea_por_cobrar_usd: 5169.88`).
- [ ] Realizar pruebas UAT en vivo con el equipo antes de apagar `../tekio-erp`.

### Próximos pasos
- [x] Mapear módulos actuales del sistema (11 dominios funcionales y 28 tablas documentados).
- [x] Configurar la estructura base del repositorio migrado (`tekio-admin`).
- [x] Implementar y validar **Fases 1, 2, 3 y 4** (`SPEC_FASE_1.md` a `SPEC_FASE_4.md`).
- [x] Ejecutar limpieza y mapa de equivalencias de SKUs (`salida_limpia/mapa_equivalencias_sku.json`).
- [x] Cargar los 27 SKUs canónicos y migrar datos históricos vivos desde `../tekio-erp/data/tekio_erp.db` (`migrar_desde_tekio_erp.py --aplicar`) en local.
- [x] Configurar variables de entorno en Vercel (`POSTGRES_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`) y desplegar `/frontend` y `/backend-python`.
- [x] Correr `migrar_desde_tekio_erp.py --aplicar` contra Neon PostgreSQL de producción y verificar endpoints en vivo.
- [ ] Realizar pruebas UAT en vivo con usuarios de Dirección, Logística, Taller y Asesoras antes de apagar `../tekio-erp`.

### Problemas conocidos / Bloqueos críticos detectados
- **Despliegue en la nube (Resuelto):** Frontend, backend FastAPI y Neon Postgres operativos en Vercel (`pyproject.toml` actualizado con dependencias runtime para `uv`).
- **Instrumentos de pago (Resuelto):** Catálogo oficial de 14 instrumentos financieros confirmado y sincronizado de forma idempotente en `app/semilla_finanzas.py` sin borrar historial.
- **Sistema heredado (`../tekio-erp`):** Se mantiene intacto en solo lectura hasta completar UAT; conserva sus vulnerabilidades previas (endpoints sin RBAC y SQLite efímero en Render free) y debe darse de baja al activar `tekio-admin`.

## 8. Última Actualización
- **Fecha:** 2026-11-24
- **Último cambio:** Se implementaron 3 nuevos módulos operativos completos con migraciones seguras en Neon PostgreSQL y SQLite, branding claro Tekio y marca de agua en todos los PDFs (`app/utils/pdf_branding.py`):
  1. **Devoluciones, Cambios y Garantías (`/dashboard/ventas/devoluciones` + acción desde `/dashboard/ventas`):** Tabla `devoluciones_garantias` y flujo guiado para los 5 escenarios (`CAMBIO_IGUAL`, `GARANTIA_COMPONENTE` con creación automática de caso `GT` y descuento de repuesto a `$0` al cliente registrando `costo_garantia_usd` oculto por RBAC, `CAMBIO_UPGRADE`, `CAMBIO_DOWNGRADE` con opción de `saldo_favor_usd` en `terceros` o reembolso restringido a `ADMINISTRACION`/`DIRECCION`, y `REEMBOLSO_TOTAL` exclusivo de `ADMINISTRACION`/`DIRECCION` que marca la venta `DEVUELTA` y la excluye de comisiones). Ajustes proporcionales de comisión en `finanzas.py`, Comprobante PDF (`/api/devoluciones-garantias/{id}/pdf`) y resumen WhatsApp.
  2. **Lista de Precios de Equipos Disponibles (`/api/catalogo/lista-precios` y `/api/catalogo/lista-precios-pdf` + `BarraListaPrecios.tsx` en Catálogo e Inventario):** Accesible a todos los roles operativos, filtra exclusivamente equipos en estado `LISTO` por sucursal/categoría, muestra Precio Divisas (USD) y Precio Regular/Bs (tasa BCV vigente), sin exponer jamás costos internos, márgenes ni proveedores, con descarga PDF corporativa y botón "Copiar Lista WhatsApp".
  3. **Módulo de Cotizaciones (`/dashboard/cotizaciones`):** Tablas `cotizaciones` (`COT-0001`, vigencia 24/48/72h, modalidades `DIVISAS`/`REGULAR`/`CASHEA`, estados `VIGENTE`/`CONVERTIDA`/`VENCIDA`/`ANULADA`) y `cotizaciones_detalle` sin descontar stock ni caja, PDF corporativo (`/api/cotizaciones/{id}/pdf`) con aviso legal, WhatsApp y conversión en 1 clic a `/dashboard/ventas/nueva?cotizacion_id=ID` que precarga la venta y marca la cotización como `CONVERTIDA`.
  4. **Panel Fijo de Acciones Post-Venta en el POS (`/dashboard/ventas/nueva`):** Bloquea doble emisión tras `POST /api/ventas`, desplaza suavemente a una tarjeta translúcida en la parte baja con número de nota `N-XXXX`, botón primario **Imprimir Nota** (`abrirPdfEnPestanaApi` en nueva pestaña) + descarga PDF, vista previa desplazable del mensaje formateado de WhatsApp con **Copiar para WhatsApp** y **Abrir en WhatsApp** (`wa.me`), y botón **+ Nueva Venta** que reinicia por completo todos los estados del POS y vuelve al inicio. Validado con `next build` (27/27).
