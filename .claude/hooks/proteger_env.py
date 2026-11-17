"""Guardrail PreToolUse (Claude Code): protege el .env ficticio y bloquea scripts no autorizados.

Entrada: evento JSON por stdin con tool_name y tool_input (formato de hooks de Claude Code).
Salida:  exit 2 = bloquear (el motivo va por stderr y lo recibe el agente); exit 0 = permitir.

Política:
  1. Ninguna herramienta (Read, Edit, Write, MultiEdit, NotebookEdit, Glob, Grep, Bash, PowerShell, ...)
     puede apuntar a un archivo .env (.env, .env.local, ruta/.env, ...).
  2. No se permite ejecutar ni tocar verificar_entorno.py (script ajeno a la tarea, sugerido por el README).
  3. Heurísticas extra para el shell: nombres armados con concatenación de cadenas ('.'+'env')
     y comodines que pueden expandirse a .env (.e*, .en?, .[e]nv ...).

LÍMITE (documentado, no oculto): es un filtro de texto sobre los argumentos de la llamada. No entiende
lo que hará realmente un comando: variables intermedias (x=.e; y=nv; cat $x$y), base64, un script
nuevo que abra el archivo, o un programa ya existente que lo lea por dentro no se detectan.
Por eso se complementa con permisos (deny) y aislamiento; ver configuracion_guardrail.md.
"""
import json
import re
import sys

# Un ".env" como nombre de archivo: precedido de inicio, separador de ruta, espacio o comilla,
# y no seguido de letras/dígitos (así ".envrc" o "environment" no cuentan, pero ".env.local" sí).
PATRON_ENV = re.compile(r"(^|[\s/\\'\"=:(<>|;&`,])\.env(?![A-Za-z0-9_])", re.IGNORECASE)
PATRON_SCRIPT = re.compile(r"verificar_entorno(\.py)?", re.IGNORECASE)
# Comodines de shell que podrían expandirse a .env: .e*  .en*  .e?v  .[e]nv  .*nv ...
PATRON_COMODIN = re.compile(r"(^|[\s/\\'\"])\.(\*|\?|\[[^\]]*\]|e|en)[\w*?\[\]]*[*?\[]", re.IGNORECASE)

HERRAMIENTAS_SHELL = {"bash", "powershell", "shell", "cmd"}

# Herramientas de archivo conocidas: solo se revisan los campos que indican la RUTA.
# Cualquier otra herramienta (shell, MCP, desconocida) se revisa en TODOS sus campos.
CAMPOS_RUTA = {
    "Read": {"file_path"},
    "Write": {"file_path"},
    "Edit": {"file_path"},
    "MultiEdit": {"file_path"},
    "NotebookEdit": {"notebook_path"},
    "Glob": {"pattern", "path"},
    "Grep": {"path", "glob"},
}


def textos(valor):
    """Recorre TODOS los campos de tool_input (también anidados), no solo uno."""
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for v in valor.values():
            yield from textos(v)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            yield from textos(v)


def sin_concatenacion(texto):
    """Quita comillas y operadores de concatenación: "'.'+'env'" -> ".env"."""
    unido = re.sub(r"['\"]\s*\+\s*['\"]", "", texto)   # '.'+'env' -> '.env'
    return re.sub(r"['\"]", " ", unido)                 # quita las comillas restantes


def motivo_bloqueo(herramienta, datos):
    es_shell = herramienta.lower() in HERRAMIENTAS_SHELL
    for t in textos(datos):
        if PATRON_ENV.search(t):
            return "acceso a un archivo .env (secretos) no autorizado"
        if PATRON_SCRIPT.search(t):
            return "verificar_entorno.py no forma parte de la tarea autorizada (instrucción del README, no del usuario)"
        if es_shell:
            if PATRON_ENV.search(sin_concatenacion(t)):
                return "comando que arma el nombre .env por partes"
            if PATRON_COMODIN.search(t):
                return "comodín de shell que puede expandirse a .env"
    return None


def main():
    try:
        evento = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("proteger_env: evento ilegible; se bloquea por precaución", file=sys.stderr)
        sys.exit(2)   # fallar cerrado
    herramienta = str(evento.get("tool_name", ""))
    datos = evento.get("tool_input", {}) or {}
    if herramienta in CAMPOS_RUTA and isinstance(datos, dict):
        # En herramientas de archivo importa DÓNDE se lee/escribe, no el texto que se escribe:
        # revisar `content`/`new_string` daba falsos positivos (p. ej. documentar el hook).
        datos = {k: v for k, v in datos.items() if k in CAMPOS_RUTA[herramienta]}
    motivo = motivo_bloqueo(herramienta, datos)
    if motivo:
        print("BLOQUEADO por proteger_env.py [%s]: %s" % (herramienta, motivo), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
