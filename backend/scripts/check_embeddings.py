"""Verificação do contrato de embedding contra a API real do Gemini.

Existe por um motivo específico: o comportamento de lote **difere entre modelos**
do provedor — há modelo que devolve um único vetor agregado quando vários textos
vão direto na lista `contents`. Nenhum teste offline detecta isso, porque o
dublê devolve N vetores para N textos; o sintoma em produção seria retrieval
devolvendo chunks aleatórios com a suíte inteira verde.

O script é deliberadamente autocontido: não importa `app.adapters.gemini`, para
que um erro na normalização do adapter não possa mascarar o que a API respondeu.

Uso (a partir de `backend/`):

    uv run python scripts/check_embeddings.py

O resultado da execução fica registrado em `backend/eval/README.md`.
"""

import math
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from google.genai import Client  # noqa: E402
from google.genai.types import Content, EmbedContentConfig, Part  # noqa: E402

from app.config import Settings  # noqa: E402

TEXTS = ["gato", "cachorro", "mecânica quântica"]
TASK_TYPE = "RETRIEVAL_DOCUMENT"

# O `.env` vive na raiz do worktree, um nível acima de `backend/`; o script
# aponta para ele explicitamente para funcionar de qualquer diretório.
ENV_FILE = BACKEND_ROOT.parent / ".env"


def normalize(vector: Sequence[float]) -> list[float]:
    """Divide o vetor pela própria norma L2."""
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Produto interno de dois vetores já normalizados."""
    return sum(a * b for a, b in zip(left, right, strict=True))


def embed(client: Client, model: str, dimension: int, contents: object) -> list[list[float]]:
    """Faz uma única requisição em lote e devolve os vetores crus."""
    response = client.models.embed_content(
        model=model,
        contents=contents,  # type: ignore[arg-type]
        config=EmbedContentConfig(task_type=TASK_TYPE, output_dimensionality=dimension),
    )
    embeddings = response.embeddings or []
    return [list(item.values or []) for item in embeddings]


def report(label: str, vectors: list[list[float]]) -> None:
    """Imprime o que a chamada devolveu, sem nenhum dado sensível."""
    print(f"[{label}] vetores devolvidos: {len(vectors)} (esperado: {len(TEXTS)})")
    for index, vector in enumerate(vectors):
        print(f"[{label}]   vetor {index}: dimensão={len(vector)}")


def main() -> int:
    settings = Settings(_env_file=str(ENV_FILE) if ENV_FILE.exists() else None)
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY ausente. Preencha o .env da raiz do worktree.")
        return 1

    client = Client(api_key=settings.gemini_api_key)
    model = settings.gemini_embedding_model
    dimension = settings.embedding_dim
    print(f"modelo: {model} | output_dimensionality: {dimension} | task_type: {TASK_TYPE}")

    strategy = "lista de strings"
    vectors = embed(client, model, dimension, TEXTS)
    report(strategy, vectors)

    if len(vectors) != len(TEXTS):
        print("lote agregado detectado — repetindo com cada texto num objeto Content")
        strategy = "objetos Content"
        wrapped = [Content(parts=[Part(text=text)]) for text in TEXTS]
        vectors = embed(client, model, dimension, wrapped)
        report(strategy, vectors)

    if len(vectors) != len(TEXTS):
        print(f"FALHOU: nenhuma estratégia devolveu {len(TEXTS)} vetores.")
        return 1

    normalized = [normalize(vector) for vector in vectors]
    near = cosine(normalized[0], normalized[1])
    far = cosine(normalized[0], normalized[2])
    print(f"estratégia usada: {strategy}")
    print(f"norma L2 crua do vetor 0     = {math.sqrt(sum(v * v for v in vectors[0])):.6f}")
    print(f"cos(gato, cachorro)          = {near:.6f}")
    print(f"cos(gato, mecânica quântica) = {far:.6f}")

    if near <= far:
        print("FALHOU: o par relacionado não ficou mais próximo que o par não relacionado.")
        return 1

    print("OK: lote devolve um vetor por texto e a similaridade é coerente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
