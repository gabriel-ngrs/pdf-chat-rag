"""O gate de arquitetura, exercitado como gate.

Os contratos de `.importlinter` só valem alguma coisa se o comando que os lê
reprovar de verdade. Um gate que nunca reprovou nada pode estar apontando para
o config errado, para o pacote errado, ou não estar analisando arquivo nenhum —
e passaria verde para sempre sem que ninguém notasse.

Por isso são dois testes e não um: o primeiro confirma que a árvore atual está
conforme; o segundo injeta uma violação no código de produção, roda o mesmo
comando e exige que ele **falhe apontando o contrato certo**. É o AC-24.
"""

import shutil
import subprocess  # nosec B404 — rodar o gate de verdade é o objeto do teste
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = BACKEND_DIR / ".importlinter"

# O módulo violador nasce dentro de `app/core/` porque é lá que o contrato de
# núcleo puro tem algo a proteger. O prefixo `_` e o nome explícito existem para
# que, se a limpeza falhar, quem der `git status` entenda em um segundo o que é.
VIOLATION_MODULE = BACKEND_DIR / "app" / "core" / "_violacao_temporaria.py"
VIOLATION_SOURCE = '''"""Módulo temporário criado por tests/test_architecture.py.

Existe apenas durante um teste, para provar que `make arch` reprova. Se este
arquivo sobreviveu a uma execução, apague-o: ele quebra o gate de arquitetura.
"""

import asyncpg

__all__ = ["asyncpg"]
'''

PURE_CORE_CONTRACT = "Nucleo puro"
FORBIDDEN_IMPORT = "asyncpg"


def _lint_imports_executable() -> str:
    """Localiza o `lint-imports` do ambiente, que é o binário que o Makefile roda.

    Procurado ao lado do interpretador antes do `PATH` porque é o do venv do
    projeto; um `lint-imports` global testaria outra instalação.
    """
    candidate = Path(sys.executable).with_name("lint-imports")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("lint-imports")
    if found is None:  # pragma: no cover - ambiente sem a dependência de dev
        pytest.skip("lint-imports não está instalado neste ambiente")
    return found


def _run_lint_imports() -> subprocess.CompletedProcess[str]:
    """Roda o gate exatamente como `make arch`, sem cache.

    `--no-cache` não é zelo: o import-linter guarda o grafo entre execuções, e
    com cache o teste de violação injetada poderia ler a árvore anterior e
    passar verde sobre um código que já não é o do disco.
    """
    return subprocess.run(  # nosec B603 — comando fixo, sem entrada do usuário
        [_lint_imports_executable(), "--config", str(CONFIG_FILE), "--no-cache"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def modulo_violador() -> Iterator[Path]:
    """Cria o módulo que viola o núcleo puro e o remove aconteça o que acontecer.

    A remoção fica no `finally` porque um arquivo esquecido em `app/core/` faria
    todo `make arch` seguinte falhar — o teste passaria a quebrar o gate que
    existe para proteger.
    """
    VIOLATION_MODULE.write_text(VIOLATION_SOURCE, encoding="utf-8")
    try:
        yield VIOLATION_MODULE
    finally:
        VIOLATION_MODULE.unlink(missing_ok=True)


def test_arvore_atual_respeita_todos_os_contratos() -> None:
    """`make arch` passa no código como ele está hoje."""
    resultado = _run_lint_imports()

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "0 broken" in resultado.stdout


def test_gate_reprova_import_de_asyncpg_dentro_do_core(modulo_violador: Path) -> None:
    """AC-24: com `import asyncpg` em `core/`, o comando falha e diz o porquê.

    Não basta o código de saída: um gate pode falhar por config inválida ou por
    não achar o pacote, e isso não provaria nada. Por isso a saída também precisa
    nomear o contrato violado e o import proibido.
    """
    assert modulo_violador.exists()

    resultado = _run_lint_imports()

    assert resultado.returncode != 0, "o gate aceitou uma violação do núcleo puro"
    assert "1 broken" in resultado.stdout
    assert PURE_CORE_CONTRACT in resultado.stdout
    assert FORBIDDEN_IMPORT in resultado.stdout
    assert "app.core._violacao_temporaria" in resultado.stdout


def test_violacao_injetada_nao_sobrevive_ao_teste() -> None:
    """A limpeza é parte do contrato: o arquivo não pode existir fora do teste.

    Roda depois do teste anterior por ordem de arquivo e confirma que a fixture
    de fato desfez o que fez — sem isto, a suíte poderia envenenar o repositório
    e só descobrir no próximo `make arch`.
    """
    assert not VIOLATION_MODULE.exists()
