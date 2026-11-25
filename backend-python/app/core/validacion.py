from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic import BaseModel, model_validator
from pydantic_core import PydanticUndefined


def _acepta_none(anotacion: Any) -> bool:
    if anotacion is None or anotacion is type(None):
        return True
    origen = get_origin(anotacion)
    if origen is not None:
        return type(None) in get_args(anotacion)
    return False


def limpiar_vacios_para_modelo(cls: type[BaseModel], valores: Any) -> Any:
    """
    Convierte strings vacíos ("") en None para campos que aceptan None,
    o al valor por defecto cuando el campo tiene default (ej. Decimal("0"), int 1),
    y convierte None en "" cuando el campo es str con default "", evitando 422
    cuando un formulario envía "" o null en campos opcionales.
    """
    if not isinstance(valores, dict):
        return valores
    resultado = dict(valores)
    for nombre, campo in cls.model_fields.items():
        if nombre not in resultado:
            continue
        val = resultado[nombre]
        acepta_none = _acepta_none(campo.annotation)
        es_obligatorio = campo.is_required()
        if isinstance(val, str):
            recortado = val.strip()
            if recortado == "":
                if acepta_none:
                    resultado[nombre] = None
                elif not es_obligatorio:
                    if campo.default is not PydanticUndefined:
                        resultado[nombre] = campo.default
                    elif campo.default_factory is not None:
                        resultado[nombre] = campo.default_factory()
        elif val is None and not acepta_none and not es_obligatorio:
            if campo.default is not PydanticUndefined:
                resultado[nombre] = campo.default
            elif campo.default_factory is not None:
                resultado[nombre] = campo.default_factory()
    return resultado


class ModeloEntradaLimpio(BaseModel):
    """BaseModel que sanea strings vacíos en campos opcionales antes de validar."""

    @model_validator(mode="before")
    @classmethod
    def _sanear_campos_vacios(cls, valores: Any) -> Any:
        return limpiar_vacios_para_modelo(cls, valores)


def formatear_error_validacion_es(errores: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Traduce los errores 422 de FastAPI/Pydantic a mensajes claros en español."""
    detalles: list[dict[str, Any]] = []
    mensajes: list[str] = []

    for err in errores:
        loc = [str(p) for p in err.get("loc", []) if str(p) not in {"body", "query", "path"}]
        campo = ".".join(loc) if loc else "solicitud"
        tipo = str(err.get("type") or "")
        msg_orig = str(err.get("msg") or "Valor inválido")

        if tipo == "missing":
            msg = f"El campo '{campo}' es obligatorio."
        elif "int_parsing" in tipo or "float_parsing" in tipo or "decimal_parsing" in tipo:
            msg = f"El campo '{campo}' debe ser un número válido."
        elif "date" in tipo:
            msg = f"El campo '{campo}' debe tener una fecha válida (YYYY-MM-DD)."
        elif "enum" in tipo or "literal" in tipo:
            msg = f"El valor indicado en '{campo}' no es una opción válida."
        elif "greater_than_equal" in tipo:
            msg = f"El campo '{campo}' no puede ser negativo."
        elif "greater_than" in tipo:
            msg = f"El campo '{campo}' debe ser mayor que 0."
        elif "string_too_short" in tipo:
            msg = f"El campo '{campo}' es demasiado corto o está vacío."
        elif "string_pattern_mismatch" in tipo:
            msg = f"El formato del campo '{campo}' no es válido."
        elif "email" in tipo:
            msg = f"El campo '{campo}' debe ser un correo electrónico válido."
        else:
            msg = f"Error en '{campo}': {msg_orig}"

        detalles.append({"campo": campo, "mensaje": msg, "tipo": tipo})
        mensajes.append(msg)

    resumen = " ".join(mensajes[:3]) if mensajes else "Datos inválidos en la solicitud."
    if len(mensajes) > 3:
        resumen += f" (y {len(mensajes) - 3} error(es) adicional(es))."
    return resumen, detalles
