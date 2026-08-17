"""Configuração: carrega sem `.env` e é publicada tal como o servidor a aplica."""

import httpx
import pytest

from app.config import Settings, get_settings
from app.main import create_app


def test_settings_carregam_sem_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem chave no ambiente o import precisa continuar funcionando.

    Se a chave fosse obrigatória, importar o app sem `.env` derrubaria a suíte
    inteira em vez de falhar no ponto em que a chave é usada.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(_env_file=None)

    assert settings.gemini_api_key == ""
    assert settings.embedding_dim == 768


def test_limite_de_upload_em_bytes() -> None:
    settings = Settings(_env_file=None, max_upload_mb=25)

    assert settings.max_upload_bytes == 25 * 1024 * 1024


@pytest.mark.asyncio
async def test_config_publica_os_tres_limites() -> None:
    app = create_app()
    settings = Settings(
        _env_file=None, max_upload_mb=7, max_pdf_pages=11, max_extracted_chars=13
    )
    app.dependency_overrides[get_settings] = lambda: settings

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {
        "max_upload_mb": 7,
        "max_pdf_pages": 11,
        "max_extracted_chars": 13,
    }
