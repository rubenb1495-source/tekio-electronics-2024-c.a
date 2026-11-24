# SPEC: Fase 4 - Ventas Multimoneda, Pagos Mixtos, Cashea, Devoluciones, Conciliación y Comisiones - Tekio Electronics

## 1. Objetivo del Módulo
- **Qué resuelve:** Ciclo comercial y financiero completo: POS multimoneda con pagos mixtos (Promo vs. Regular), Cashea y cuentas por cobrar, Nota de Entrega PDF y reporte WhatsApp, Devoluciones (Notas de Crédito), verificación de pagos digitales, conciliación bancaria por CSV/Excel, comisiones por rol y cierre de mes inmutable.
- **Backend:** Python / FastAPI (`app/modelos_finanzas.py`, `app/esquemas_finanzas.py`, `app/servicios/pdf_nota.py`, `app/rutas/ventas.py`, `app/rutas/finanzas.py`).
- **Frontend:** Next.js (`/dashboard/ventas/nueva`, `/dashboard/ventas`, `/dashboard/devoluciones`, `/dashboard/finanzas/pagos`, `/dashboard/finanzas/cashea`, `/dashboard/finanzas/conciliacion`, `/dashboard/finanzas/comisiones`).
- **Tablas nuevas:** `instrumentos_financieros`, `ventas`, `ventas_detalle`, `pagos`, `notas_credito`, `cuentas_por_cobrar`, `extractos_bancarios`, `cierres_mensuales`.

## 2. Reglas de Negocio Clave
- Sucursales cerradas (`INFOT`, `Free Market C13`) bloqueadas para nuevas ventas (`403 Forbidden`).
- Bloqueo de pagos en `BS` o `Cashea` si no existe tasa del día.
- Reparto exacto de pagos mixtos (Divisas/USDT a Promo; Bs/Cashea a Regular; con Cashea toda la venta va a Regular).
- Serial único en estado `LISTO` en la misma sucursal de la venta (`400` si ya vendido o en otra sucursal).
- Parte de pago crea compra `PARTE_DE_PAGO` y equipo en `POR_PREPARAR`.
- Nota de Entrega PDF con RIF `J-50637518-4` y garantía de 180 días.
- Devoluciones en `notas_credito` sin modificar venta original, reingresando serial a `POR_PREPARAR`/`GARANTIA`/`LISTO`.
- Comisiones sobre Precio Promo (excluyendo anuladas): Asesor `1%`, Líder `1% + 0.5%`, Técnico `50%` servicios + `1%` ventas + preparaciones.
- Cierre de mes bloquea crear/anular/editar en ese período (`403`).
- RBAC: ningún endpoint expone costos ni utilidad real a `ASESORA` o `TECNICO`.
