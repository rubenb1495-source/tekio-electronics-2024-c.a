from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.modelos import Usuario
from app.modelos_admin_finanzas import AuditoriaSistema


def _serializar_seguro(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _serializar_seguro(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializar_seguro(v) for v in obj]
    return obj


def registrar_auditoria(
    bd: Session,
    usuario: Usuario | None,
    modulo: str,
    accion: str,
    entidad_id: int | str = "",
    detalle_anterior: dict[str, Any] | None = None,
    detalle_nuevo: dict[str, Any] | None = None,
) -> AuditoriaSistema:
    """Inserta un registro inmutable en `auditoria_sistema` sin alterar el commit actual."""
    registro = AuditoriaSistema(
        usuario_id=usuario.id if usuario else None,
        usuario_nombre=usuario.nombre if usuario else "Sistema",
        usuario_rol=usuario.rol if usuario else "SISTEMA",
        modulo=modulo.strip().upper(),
        accion=accion.strip().upper(),
        entidad_id=str(entidad_id) if entidad_id is not None else "",
        detalle_anterior_json=json.dumps(
            _serializar_seguro(detalle_anterior or {}), ensure_ascii=False
        ),
        detalle_nuevo_json=json.dumps(
            _serializar_seguro(detalle_nuevo or {}), ensure_ascii=False
        ),
    )
    bd.add(registro)
    return registro
