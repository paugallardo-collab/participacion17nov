"""Regresiones del guardrail: eventos inertes; no ejecuta sus herramientas."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "proteger_env.py"


class PruebasGuardrail(unittest.TestCase):
    def ejecutar_hook(self, entrada):
        return subprocess.run(
            [sys.executable, str(HOOK)], input=entrada,
            capture_output=True, text=True, check=False,
        )

    def comprobar_bloqueo(self, entrada):
        resultado = self.ejecutar_hook(entrada)
        self.assertEqual(resultado.returncode, 2, resultado.stderr)
        self.assertTrue(resultado.stderr.strip())

    def test_rechaza_json_invalido(self):
        for entrada in ("", "{"):
            with self.subTest(entrada=entrada):
                self.comprobar_bloqueo(entrada)

    def test_rechaza_raices_que_no_son_objetos(self):
        for evento in ([], None, True, 123, "texto"):
            with self.subTest(evento=evento):
                self.comprobar_bloqueo(json.dumps(evento))

    def test_rechaza_herramienta_ausente_o_invalida(self):
        eventos = [{"tool_input": {}}]
        eventos += [{"tool_name": nombre, "tool_input": {}}
                    for nombre in (None, [], 123, "", "   ")]
        for evento in eventos:
            with self.subTest(evento=evento):
                self.comprobar_bloqueo(json.dumps(evento))

    def test_rechaza_tool_input_ausente_o_invalido(self):
        eventos = [{"tool_name": "Read"}]
        eventos += [{"tool_name": "Read", "tool_input": datos}
                    for datos in (None, [], "calculadora.py", 123)]
        for evento in eventos:
            with self.subTest(evento=evento):
                self.comprobar_bloqueo(json.dumps(evento))

    def test_bloquea_operaciones_directas_sobre_env(self):
        for herramienta in ("Read", "Write", "Edit", "MultiEdit"):
            with self.subTest(herramienta=herramienta):
                self.comprobar_bloqueo(json.dumps({
                    "tool_name": herramienta,
                    "tool_input": {"file_path": ".env"},
                }))

    def test_permite_documentar_la_politica(self):
        entradas = [
            {"tool_name": "Write", "tool_input": {
                "file_path": "configuracion_guardrail.md",
                "content": "Bloquear .env y verificar_entorno.py",
            }},
            {"tool_name": "Edit", "tool_input": {
                "file_path": "respuestas.md", "old_string": "politica",
                "new_string": "politica sobre .env y verificar_entorno.py",
            }},
        ]
        for evento in entradas:
            with self.subTest(herramienta=evento["tool_name"]):
                resultado = self.ejecutar_hook(json.dumps(evento))
                self.assertEqual(resultado.returncode, 0, resultado.stderr)


if __name__ == "__main__":
    unittest.main()
