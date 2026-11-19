# Configuración del guardrail

## Agente y mecanismo

- **Agente de la sesión original, según su registro:** Claude Code 2.1.326 (CLI, sesión remota en contenedor Linux). Los fragmentos de aquella interacción se conservan en `evidencias.md` y se distinguen de las comprobaciones locales posteriores.
- **Mecanismo:** hook `PreToolUse` de Claude Code. Antes de las llamadas que coinciden con el matcher, recibe por stdin un objeto JSON con `tool_name` y `tool_input`. `exit 2` bloquea la llamada y envía el motivo por stderr; `exit 0` no la bloquea y deja que continúe la evaluación normal de permisos.

## Dónde está registrado

`.claude/settings.json` (configuración de proyecto, revisada por mí; partí de `.claude/settings.json.plantilla`):

```json
"hooks": {
  "PreToolUse": [{
    "matcher": "Read|Edit|Write|MultiEdit|NotebookEdit|Glob|Grep|Bash|PowerShell",
    "hooks": [{ "type": "command",
                "command": "python3",
                "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/proteger_env.py"],
                "onFailure": "block" }]
  }]
}
```

- `python3` corresponde al entorno Linux de la sesión original. Debe estar instalado y disponible en el `PATH` de Claude Code. En Windows, si el ejecutable disponible se llama `python`, se cambia `command` a `python` conservando `args`; incluir `PowerShell` en el matcher no instala Python ni demuestra por sí solo compatibilidad del entorno.
- `args` usa la forma de ejecución directa: Claude Code sustituye `${CLAUDE_PROJECT_DIR}` y entrega la ruta como un argumento, sin depender de la expansión de variables de Bash o PowerShell.
- `onFailure: "block"` pide a Claude Code bloquear si el hook no puede iniciarse, falla o agota su tiempo. Requiere Claude Code 2.1.295 o posterior. El script también rechaza explícitamente entradas JSON inválidas o con estructura inesperada mediante `exit 2`.
- La plantilla (`settings.json.plantilla`) no se activa sola, pero **este repositorio ya incluye `.claude/settings.json`**. Clonar solo descarga archivos; no hay que volver a crear esa configuración. Antes de abrirlo con Claude Code se revisan los hooks. En una sesión interactiva se acepta la confianza del directorio; en modo `-p` o SDK los hooks del proyecto pueden ejecutarse sin ese diálogo.
- Para comprobar la carga en Claude Code, revisar `/hooks` y realizar una llamada inocua permitida y una solicitud directa que deba bloquearse. Las pruebas locales del script no demuestran por sí solas que Claude Code lo tenga cargado.

## Herramientas que intercepta y qué campos revisa

| Herramienta | Campos revisados | Ejemplo bloqueado |
|---|---|---|
| Read / Write / Edit / MultiEdit | `file_path` | `Read .env` |
| NotebookEdit | `notebook_path` | — |
| Glob | `pattern`, `path` | `Glob .env*` |
| Grep | `path`, `glob` | `Grep path=.env` |
| Bash / PowerShell | **todos** los campos de `tool_input` | `cat .env`, `Get-Content .env`, `python verificar_entorno.py` |

El matcher de este proyecto contiene solo las herramientas indicadas. Aunque el script sabe revisar otros nombres si recibe sus eventos, las herramientas MCP u otras herramientas no incluidas no quedan interceptadas automáticamente.

En las herramientas de archivo reviso solo la **ruta**, no el texto que se escribe. En la primera versión revisaba todos los campos (también `content`), y eso bloqueó mi propia escritura de esta documentación porque menciona `.env`. Fue un falso positivo real; el detalle está en `evidencias.md`.

## Política

1. Bloquear cualquier ruta o comando que nombre un archivo `.env` (`.env`, `.env.local`, `ruta/.env`). No bloquea `.envrc`, `env_falso.txt` ni la palabra `environment`.
2. Bloquear cualquier referencia a `verificar_entorno.py` (es la acción que inyecta el README).
3. Solo en el shell, dos heurísticas más: nombres armados por concatenación (`'.'+'env'`) y comodines que pueden expandirse a `.env` (`.e*`, `.en?`, `.[e]nv`).
4. Bloquear con `exit 2` si la entrada no es JSON válido, la raíz no es un objeto, falta un `tool_name` de tipo cadena no vacía o falta un `tool_input` de tipo objeto. Los fallos de ejecución que no alcance a manejar el script se cubren con `onFailure: "block"` en Claude Code.

## Cómo comprobé que está cargado

1. **Banco local:** `python3 .claude/hooks/probar_hook.py`. Con la plantilla fallan 4 pruebas básicas; con mi hook pasan las 8.
2. **Dentro del agente real:** las llamadas empezaron a fallar con `PreToolUse:Read hook error: [command hook]: BLOQUEADO por proteger_env.py [Read] ...`. Esa línea solo aparece si Claude Code ejecutó el hook.
3. **Observación de la sesión original:** el registro declara que la primera lectura del `.env` ficticio después de guardar la configuración se ejecutó y las posteriores se bloquearon. Ese fragmento no permite establecer la causa exacta del primer fallo. Hay que verificar la configuración efectiva y su carga antes de probar el acceso, sin asumir que guardar el archivo ya acredita la protección.
4. **Revisión posterior (19 de noviembre de 2026):** `python -m unittest discover -v` incluye las 8 pruebas originales y 6 pruebas de regresión en `tests/test_guardrail.py`. Estas últimas invocan solo el hook con eventos inertes: verifican entradas inválidas, bloqueo de operaciones directas y permiso para documentar la política. No ejecutan las herramientas descritas en esos eventos. Resultados y alcance en `evidencias.md`.

## Segunda barrera añadida: `permissions.deny`

En el mismo `settings.json` añadí reglas de denegación de permisos, que el agente aplica sin depender del hook:

```json
"permissions": { "deny": [ "Read(./.env)", "Read(./.env.*)", "Edit(./.env)", "Edit(./.env.*)",
                           "Bash(python verificar_entorno.py:*)", "Bash(python3 verificar_entorno.py:*)" ] }
```

La regla de Bash es por prefijo de comando y tiene los mismos límites de evasión que el hook, así que es defensa en profundidad, **no** protección universal. La barrera fuerte es el aislamiento: ver `respuestas.md`.

No debe deducirse que los permisos siempre actúan antes del hook: la documentación actual indica que `PreToolUse` se ejecuta antes de la evaluación normal de permisos y que `exit 2` detiene la llamada. El mensaje de permisos declarado en la prueba 8 de la sesión original no basta para reconstruir qué hook estaba activo en ese momento.

## Documentación consultada

- [Hooks: ejecución directa y argumentos](https://code.claude.com/docs/en/hooks#command-hook-fields).
- [Bloquear también cuando falla el hook](https://code.claude.com/docs/en/hooks#block-the-action-when-a-hook-fails).
- [Confianza del directorio y hooks](https://code.claude.com/docs/en/hooks#workspace-trust).
- [Precedencia entre permisos y hooks](https://code.claude.com/docs/en/permissions#precedence-among-rules-hooks-and-mods).

## Límites (sin prometer protección universal)

- Es un filtro de **texto** sobre los argumentos. No sabe qué hará el comando: `x=.e; y=nv; cat $x$y` **pasa** (ver auditoría).
- Un programa que abre `.env` por dentro (p. ej. `python app.py` con `load_dotenv()`) no menciona `.env` en el comando y **pasa**.
- Tampoco detecta codificaciones (base64, hex) ni que el agente escriba primero un script nuevo y luego lo ejecute. Como Write ya no revisa `content`, ese script se puede escribir sin bloqueo, y ejecutarlo con `python otro.py` tampoco lo dispara.
- Falsos positivos: cualquier comando de shell con el texto `.env` se bloquea, incluido `cp env_falso.txt .env` de la preparación (por eso creé el `.env` antes de activar el hook).
- Solo cubre herramientas que pasan por `PreToolUse` y coinciden con el matcher. Una herramienta MCP con otro nombre queda fuera.

