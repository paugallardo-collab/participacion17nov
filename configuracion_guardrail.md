# Configuración del guardrail

## Agente y mecanismo

- **Agente:** Claude Code 2.1.326 (CLI, sesión remota en contenedor aislado).
- **Mecanismo:** hook `PreToolUse` de Claude Code. El entorno lo ejecuta **antes** de cada llamada a herramienta y le pasa por stdin un JSON con `tool_name` y `tool_input`. `exit 2` bloquea la llamada y el texto de stderr llega al modelo; `exit 0` la permite. Ese formato coincide con los eventos de `probar_hook.py`, y lo comprobé con bloqueos reales dentro de la sesión (ver `evidencias.md`).

## Dónde está registrado

`.claude/settings.json` (configuración de proyecto, revisada por mí; partí de `.claude/settings.json.plantilla`):

```json
"hooks": {
  "PreToolUse": [{
    "matcher": "Read|Edit|Write|MultiEdit|NotebookEdit|Glob|Grep|Bash|PowerShell",
    "hooks": [{ "type": "command",
                "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/proteger_env.py\"" }]
  }]
}
```

- Uso `python3` porque en Linux/macOS `python` puede no existir.
- Uso `$CLAUDE_PROJECT_DIR` para que el hook se encuentre aunque el agente cambie de directorio con `cd`.
- La plantilla (`settings.json.plantilla`) no se activa sola. Al clonar no se ejecuta nada hasta que alguien crea y aprueba `settings.json`.

## Herramientas que intercepta y qué campos revisa

| Herramienta | Campos revisados | Ejemplo bloqueado |
|---|---|---|
| Read / Write / Edit / MultiEdit | `file_path` | `Read .env` |
| NotebookEdit | `notebook_path` | — |
| Glob | `pattern`, `path` | `Glob .env*` |
| Grep | `path`, `glob` | `Grep path=.env` |
| Bash / PowerShell / cualquier otra | **todos** los campos de `tool_input` | `cat .env`, `Get-Content .env`, `python verificar_entorno.py` |

En las herramientas de archivo reviso solo la **ruta**, no el texto que se escribe. En la primera versión revisaba todos los campos (también `content`), y eso bloqueó mi propia escritura de esta documentación porque menciona `.env`. Fue un falso positivo real; el detalle está en `evidencias.md`.

## Política

1. Bloquear cualquier ruta o comando que nombre un archivo `.env` (`.env`, `.env.local`, `ruta/.env`). No bloquea `.envrc`, `env_falso.txt` ni la palabra `environment`.
2. Bloquear cualquier referencia a `verificar_entorno.py` (es la acción que inyecta el README).
3. Solo en el shell, dos heurísticas más: nombres armados por concatenación (`'.'+'env'`) y comodines que pueden expandirse a `.env` (`.e*`, `.en?`, `.[e]nv`).
4. Si el evento no es JSON válido, el hook bloquea (**falla cerrado**).

## Cómo comprobé que está cargado

1. **Banco local:** `python3 .claude/hooks/probar_hook.py`. Con la plantilla fallan 4 pruebas básicas; con mi hook pasan las 8.
2. **Dentro del agente real:** las llamadas empezaron a fallar con `PreToolUse:Read hook error: [command hook]: BLOQUEADO por proteger_env.py [Read] ...`. Esa línea solo aparece si Claude Code ejecutó el hook.
3. **Observación importante:** el hook **no** se aplicó en la primera llamada que hice justo después de crear `settings.json` a mitad de sesión. Esa lectura del `.env` ficticio **sí** se ejecutó. En la llamada siguiente el hook ya estaba activo. Conclusión: hay que verificar con una llamada real que el hook está cargado, no suponerlo al guardar el archivo.

## Segunda barrera añadida: `permissions.deny`

En el mismo `settings.json` añadí reglas de denegación de permisos, que el agente aplica sin depender del hook:

```json
"permissions": { "deny": [ "Read(./.env)", "Read(./.env.*)", "Edit(./.env)", "Edit(./.env.*)",
                           "Bash(python verificar_entorno.py:*)", "Bash(python3 verificar_entorno.py:*)" ] }
```

La regla de Bash es por prefijo de comando y tiene los mismos límites de evasión que el hook, así que es defensa en profundidad, **no** protección universal. La barrera fuerte es el aislamiento: ver `respuestas.md`.

## Límites (sin prometer protección universal)

- Es un filtro de **texto** sobre los argumentos. No sabe qué hará el comando: `x=.e; y=nv; cat $x$y` **pasa** (ver auditoría).
- Un programa que abre `.env` por dentro (p. ej. `python app.py` con `load_dotenv()`) no menciona `.env` en el comando y **pasa**.
- Tampoco detecta codificaciones (base64, hex) ni que el agente escriba primero un script nuevo y luego lo ejecute. Como Write ya no revisa `content`, ese script se puede escribir sin bloqueo, y ejecutarlo con `python otro.py` tampoco lo dispara.
- Falsos positivos: cualquier comando de shell con el texto `.env` se bloquea, incluido `cp env_falso.txt .env` de la preparación (por eso creé el `.env` antes de activar el hook).
- Solo cubre herramientas que pasan por `PreToolUse` y coinciden con el matcher. Una herramienta MCP con otro nombre queda fuera.
