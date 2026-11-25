from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.modelos_contabilidad import (
    AsientoContable,
    AsientoLinea,
    PlanCuenta,
    TipoCuentaContable,
)


class ErrorPartidaDoble(ValueError):
    """Se lanza cuando un asiento contable no cumple estrictamente sum(debe) == sum(haber)."""


# Plan de Cuentas Base (estándar comercial Venezuela · Tekio Electronics)
CUENTAS_BASE_TEKIO: list[tuple[str, str, TipoCuentaContable]] = [
    ("1.1.01", "Caja y Bancos", TipoCuentaContable.ACTIVO),
    ("1.1.02", "Cuentas por Cobrar Clientes", TipoCuentaContable.ACTIVO),
    ("1.1.03", "Cashea por Cobrar", TipoCuentaContable.ACTIVO),
    ("1.1.04", "Inventario de Equipos", TipoCuentaContable.ACTIVO),
    ("1.1.05", "Inventario de Componentes", TipoCuentaContable.ACTIVO),
    ("2.1.01", "Cuentas por Pagar Proveedores", TipoCuentaContable.PASIVO),
    ("2.1.02", "Obligaciones Fiscales por Pagar", TipoCuentaContable.PASIVO),
    ("2.1.03", "Préstamos por Pagar", TipoCuentaContable.PASIVO),
    ("3.1.01", "Capital Social", TipoCuentaContable.PATRIMONIO),
    ("3.1.02", "Resultados Acumulados", TipoCuentaContable.PATRIMONIO),
    ("4.1.01", "Ingresos por Ventas de Equipos y Componentes", TipoCuentaContable.INGRESO),
    ("4.1.02", "Ingresos por Servicios Técnicos y Taller", TipoCuentaContable.INGRESO),
    ("4.2.01", "Ganancia por Diferencial Cambiario", TipoCuentaContable.INGRESO),
    ("5.1.01", "Costo de Ventas", TipoCuentaContable.COSTO),
    ("6.1.01", "Gastos de Comisiones", TipoCuentaContable.GASTO),
    ("6.2.01", "Gastos Operativos Administrativos", TipoCuentaContable.GASTO),
    ("6.2.02", "Gastos de Nómina", TipoCuentaContable.GASTO),
    ("6.3.01", "Intereses Financieros", TipoCuentaContable.GASTO),
    ("6.3.02", "Pérdida por Diferencial Cambiario", TipoCuentaContable.GASTO),
    ("6.3.03", "Comisiones Financieras Cashea", TipoCuentaContable.GASTO),
    ("3.1.03", "Utilidades Distribuidas a Socios", TipoCuentaContable.PATRIMONIO),
]


def _q2(valor: Decimal | float | int | str) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def asegurar_plan_cuentas(bd: Session) -> dict[str, PlanCuenta]:
    """Garantiza que existan las cuentas base en `plan_cuentas` y devuelve un mapa código -> PlanCuenta."""
    existentes = {c.codigo: c for c in bd.query(PlanCuenta).all()}
    creadas = False
    for codigo, nombre, tipo in CUENTAS_BASE_TEKIO:
        if codigo not in existentes:
            cuenta = PlanCuenta(
                codigo=codigo,
                nombre=nombre,
                tipo=tipo.value,
                activa=True,
            )
            bd.add(cuenta)
            existentes[codigo] = cuenta
            creadas = True
    if creadas:
        bd.flush()
    return existentes


def registrar_asiento(
    bd: Session,
    *,
    fecha: date,
    referencia: str,
    modulo_origen: str,
    entidad_id: int | str,
    descripcion: str,
    lineas: list[dict[str, Any]],
    creado_por_id: int | None = None,
) -> AsientoContable:
    """
    Registra un asiento contable por partida doble exigiendo estrictamente
    `sum(debe_usd) == sum(haber_usd)` (> 0). Si no cuadra, ejecuta `bd.rollback()`
    y lanza `ErrorPartidaDoble`.

    Cada elemento de `lineas` debe contener:
    - `codigo_cuenta`: str (ej. "1.1.01") o `cuenta_id`: int
    - `debe_usd`: Decimal/float (default 0)
    - `haber_usd`: Decimal/float (default 0)
    - `descripcion`: str (opcional)
    """
    if not lineas or len(lineas) < 2:
        bd.rollback()
        raise ErrorPartidaDoble(
            "Un asiento contable requiere al menos 2 líneas de partida doble."
        )

    cuentas_por_codigo = asegurar_plan_cuentas(bd)
    cuentas_por_id = {c.id: c for c in cuentas_por_codigo.values() if c.id is not None}

    total_debe = Decimal("0.00")
    total_haber = Decimal("0.00")
    lineas_normalizadas: list[tuple[int, Decimal, Decimal, str]] = []

    for item in lineas:
        debe = _q2(item.get("debe_usd", 0) or 0)
        haber = _q2(item.get("haber_usd", 0) or 0)
        if debe < 0 or haber < 0:
            bd.rollback()
            raise ErrorPartidaDoble(
                "Los montos de Debe y Haber en un asiento contable no pueden ser negativos."
            )
        if debe == 0 and haber == 0:
            continue

        cuenta_obj: PlanCuenta | None = None
        if item.get("codigo_cuenta"):
            cuenta_obj = cuentas_por_codigo.get(str(item["codigo_cuenta"]).strip())
        elif item.get("cuenta_id"):
            cid = int(item["cuenta_id"])
            cuenta_obj = cuentas_por_id.get(cid) or bd.query(PlanCuenta).filter(PlanCuenta.id == cid).first()

        if cuenta_obj is None:
            bd.rollback()
            raise ErrorPartidaDoble(
                f"Cuenta contable no encontrada: {item.get('codigo_cuenta') or item.get('cuenta_id')}"
            )

        total_debe += debe
        total_haber += haber
        lineas_normalizadas.append(
            (cuenta_obj.id, debe, haber, str(item.get("descripcion") or "")[:255])
        )

    total_debe = _q2(total_debe)
    total_haber = _q2(total_haber)

    if len(lineas_normalizadas) < 2 or total_debe <= Decimal("0.00"):
        bd.rollback()
        raise ErrorPartidaDoble(
            "El asiento contable debe tener al menos dos líneas con montos mayores a cero."
        )

    if total_debe != total_haber:
        bd.rollback()
        raise ErrorPartidaDoble(
            f"Asiento descuadrado: Debe ({total_debe:.2f} USD) != Haber ({total_haber:.2f} USD). "
            "Operación revertida por regla estricta de partida doble."
        )

    asiento = AsientoContable(
        fecha=fecha,
        referencia=str(referencia or "")[:80],
        modulo_origen=modulo_origen.strip().upper()[:40],
        entidad_id=str(entidad_id or "")[:60],
        descripcion=str(descripcion or "")[:500],
        creado_por_id=creado_por_id,
    )
    bd.add(asiento)
    bd.flush()

    for cuenta_id, debe, haber, desc_linea in lineas_normalizadas:
        bd.add(
            AsientoLinea(
                asiento_id=asiento.id,
                cuenta_id=cuenta_id,
                debe_usd=debe,
                haber_usd=haber,
                descripcion=desc_linea,
            )
        )
    bd.flush()
    return asiento
