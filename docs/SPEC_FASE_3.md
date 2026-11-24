# SPEC: Fase 3 - Taller, Preparaciones por Serial, Hospital/Repuestos y Casos GT/ST - Tekio Electronics

## 1. Objetivo del Módulo
- **Qué resuelve:** Flujo completo del taller técnico: preparación de equipos por serial (actualizando estado y `costo_taller_usd` sin exponer costos al técnico), conexión automática `HOSPITAL` → `Repuestos por comprar` → alerta *"Repuestos que llegaron"*, gestión de casos `GT`/`ST` con aprobación obligatoria de presupuesto y resumen mensual del técnico.
- **Backend:** Python / FastAPI (`app/modelos_taller.py`, `app/esquemas_taller.py`, `app/rutas/taller.py`).
- **Frontend:** Next.js (`/dashboard/taller/preparaciones`, `/dashboard/taller/casos`, `/dashboard/taller/repuestos`, `/dashboard/taller/mi-resumen`).
- **Tablas nuevas:** `preparaciones`, `preparaciones_componentes`, `repuestos_solicitados`, `casos_postventa`, `casos_presupuestos`, `casos_repuestos_usados`.

## 2. Reglas de Negocio Clave
- Costos invisibles para `TECNICO` y `ASESORA` en todos los endpoints `/api/taller/*`.
- Descuento automático de componentes en `Bodega` (`movimientos_inventario`, `tipo: TALLER`), prohibiendo stock negativo.
- Flujo automático `HOSPITAL` → `repuestos_solicitados (PENDIENTE)` → Logística marca `RECIBIDO` → alerta en cola del técnico.
- Casos `ST` bloqueados para pasar a `TERMINADO` sin presupuesto aprobado (`400`); descuento automático de repuestos aprobados si el técnico no los ingresa manualmente.
- Validación informativa de 180 días de garantía en casos `GT`.
- Pago estándar `$1.00 USD` por preparación estándar y `50%` en servicios técnicos.
