"""O arquivo usado pelos testes da versão Cloudflare (JavaScript) precisa
refletir as regras atuais da versão Python."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "cloudflare" / "test"))
from gerar_esperado import gerar  # noqa: E402


def test_esperado_json_esta_atualizado():
    salvo = json.loads((RAIZ / "cloudflare" / "test" / "esperado.json").read_text(encoding="utf-8"))
    assert salvo == gerar(), "Rode: python cloudflare/test/gerar_esperado.py"
