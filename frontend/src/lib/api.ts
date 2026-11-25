/**
 * Utilidades centralizadas de manejo de errores HTTP / FastAPI 422
 * y saneamiento de payloads de formularios para Tekio Electronics.
 */

interface ErrorValidacionFastApi {
  loc?: Array<string | number>;
  msg?: string;
  mensaje?: string;
  campo?: string;
  type?: string;
}

function formatearItemValidacion(item: unknown): string | null {
  if (typeof item === "string") {
    const limpio = item.trim();
    return limpio || null;
  }
  if (!item || typeof item !== "object") return null;

  const obj = item as ErrorValidacionFastApi;
  if (typeof obj.mensaje === "string" && obj.mensaje.trim()) {
    return obj.mensaje.trim();
  }
  if (typeof obj.msg === "string" && obj.msg.trim()) {
    const partes = Array.isArray(obj.loc)
      ? obj.loc
          .map((p) => String(p))
          .filter((p) => p !== "body" && p !== "query" && p !== "path")
      : [];
    const campo = obj.campo || partes.join(".");
    return campo ? `Campo '${campo}': ${obj.msg.trim()}` : obj.msg.trim();
  }
  return null;
}

/**
 * Extrae un mensaje legible en español desde cualquier error (ErrorApi, Error,
 * cuerpo JSON de FastAPI con `detail` string, array 422 o `errores`).
 * Nunca devuelve "[object Object]".
 */
export function extraerMensajeError(
  error: unknown,
  fallback = "Ocurrió un error inesperado al procesar la solicitud."
): string {
  if (!error) return fallback;

  if (typeof error === "string") {
    const limpio = error.trim();
    return limpio && limpio !== "[object Object]" ? limpio : fallback;
  }

  if (error instanceof Error) {
    const msg = error.message?.trim();
    if (msg && msg !== "[object Object]") return msg;
    return fallback;
  }

  if (typeof error === "object") {
    const rec = error as Record<string, unknown>;

    if (typeof rec.detail === "string" && rec.detail.trim()) {
      return rec.detail.trim();
    }

    if (Array.isArray(rec.detail)) {
      const mensajes = rec.detail
        .map(formatearItemValidacion)
        .filter((m): m is string => Boolean(m));
      if (mensajes.length > 0) {
        return mensajes.slice(0, 3).join(" ");
      }
    }

    if (Array.isArray(rec.errores)) {
      const mensajes = rec.errores
        .map(formatearItemValidacion)
        .filter((m): m is string => Boolean(m));
      if (mensajes.length > 0) {
        return mensajes.slice(0, 3).join(" ");
      }
    }

    if (rec.detail && typeof rec.detail === "object") {
      const anidado = extraerMensajeError(rec.detail, "");
      if (anidado) return anidado;
    }

    if (typeof rec.message === "string" && rec.message.trim()) {
      return rec.message.trim();
    }
    if (typeof rec.mensaje === "string" && rec.mensaje.trim()) {
      return rec.mensaje.trim();
    }
  }

  return fallback;
}

/**
 * Sanea recursivamente un objeto de formulario antes de enviarlo por JSON:
 * recorta espacios en strings y convierte strings vacíos "" en `null` para claves
 * opcionales especificadas (o cuando `convertirTodosVaciosANull` es true).
 */
export function limpiarPayloadFormulario<T extends Record<string, unknown>>(
  payload: T,
  clavesOpcionalesANull?: readonly string[]
): Record<string, unknown> {
  const conjuntoOpcionales = clavesOpcionalesANull
    ? new Set(clavesOpcionalesANull)
    : null;
  const resultado: Record<string, unknown> = {};

  for (const [clave, valor] of Object.entries(payload)) {
    if (typeof valor === "string") {
      const recortado = valor.trim();
      if (recortado === "" && (!conjuntoOpcionales || conjuntoOpcionales.has(clave))) {
        resultado[clave] = null;
      } else {
        resultado[clave] = recortado;
      }
    } else if (Array.isArray(valor)) {
      resultado[clave] = valor.map((el) =>
        el && typeof el === "object" && !Array.isArray(el)
          ? limpiarPayloadFormulario(
              el as Record<string, unknown>,
              clavesOpcionalesANull
            )
          : el
      );
    } else if (valor && typeof valor === "object") {
      resultado[clave] = limpiarPayloadFormulario(
        valor as Record<string, unknown>,
        clavesOpcionalesANull
      );
    } else {
      resultado[clave] = valor;
    }
  }

  return resultado;
}
