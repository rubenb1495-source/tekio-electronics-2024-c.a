# SPEC: Fase 2 - Logística, Compras, Guías, Recepción por Serial y Traslados en 2 Pasos - Tekio Electronics

## 1. Objetivo del Módulo
- **Qué resuelve:** Centraliza el ingreso de mercancía (compras nacionales, importaciones, inventario existente y equipos en parte de pago), el control de guías de casillero con prorrateo automático de flete, la recepción serial por serial con doble verificación y los traslados seguros en 2 pasos entre `Bodega` y sucursales.
- **Tipo de tarea:** Refactorización con mejoras (reemplaza `TEKIO · Logística`, `TEKIO · Plantilla de carga` y las pestañas de `Compras`, `Guías` y `Recepción`).
- **Código legacy de referencia:** `../tekio-erp` según `CONTEXT.md`.

## 2. Arquitectura y Alcance
- **Backend asignado:** **Python / FastAPI** (manteniendo consistencia con Fase 1 y validación estricta con Pydantic).
- **Frontend (Next.js):**
  - `/dashboard/logistica/compras`: Registro de compras e importación masiva desde Excel/CSV con vista previa.
  - `/dashboard/logistica/guias`: Gestión de guías de casillero (Miami → Venezuela) y prorrateo de flete.
  - `/dashboard/logistica/recepcion`: Recepción física por serial (compatible con lector de código de barras) y doble firma.
  - `/dashboard/logistica/traslados`: Envío desde `Bodega`/sucursal y bandeja de recepción física en destino.
  - `/dashboard/logistica/inventario`: Consulta de stock por serial (equipos) y Kardex por SKU (componentes/accesorios), más solicitud/aprobación de ajustes.
- **Base de datos (Tablas/Modelos):**
  - `terceros`, `compras`, `guias_importacion`, `guias_compras`, `equipos`, `movimientos_inventario`, `traslados`, `traslados_detalle`, `ajustes_inventario`.

## 3. Contratos de API (Endpoints)
- Compras: `POST /api/logistica/compras`, `POST /api/logistica/compras/validar-archivo`, `GET /api/logistica/compras`, `GET/POST /api/logistica/terceros`.
- Guías y Recepción: `GET/POST /api/logistica/guias`, `POST /api/logistica/guias/:id/recibir`.
- Traslados: `GET/POST /api/logistica/traslados`, `POST /api/logistica/traslados/:id/confirmar`, `POST /api/logistica/traslados/:id/anular`.
- Inventario, Trazabilidad y Ajustes: `GET /api/logistica/inventario/equipos`, `GET /api/logistica/inventario/kardex`, `GET /api/logistica/trazabilidad/:serial`, `GET/POST /api/logistica/ajustes`, `PATCH /api/logistica/ajustes/:id/revisar`.

## 4. Reglas de Negocio Clave
- Serial único en MAYÚSCULAS sin espacios (`409 Conflict` si ya existe).
- Prorrateo de flete por valor: `flete_asignado = costo_total_guia * (costo_item / suma_costos_guia)`.
- Doble verificación obligatoria: `recibido_por_id != verificado_por_id` (`400 Bad Request` si coinciden).
- Inventario existente: `costo_compra_usd`, `ubicacion_id` y `estado` obligatorios por fila.
- Bloqueo en traslados (`EN_TRANSITO`): equipos no vendibles ni en origen ni en destino hasta confirmar recepción.
- Aprobación de ajustes: solo `DIRECCION` puede aprobar/rechazar; el inventario no cambia hasta aprobación.
- Protección de costos (RBAC): ningún endpoint devuelve `costo_compra_usd`, `costo_flete_usd` ni `costo_taller_usd` a `ASESORA` o `TECNICO`.
