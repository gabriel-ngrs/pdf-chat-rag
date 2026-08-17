"""Configuração da aplicação, lida do ambiente.

Espelha exatamente o conjunto de variáveis de `.env.example` — sem sobra e sem
falta —, para que o arquivo de exemplo continue sendo a documentação real do
que o processo lê.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Valores de configuração do processo.

    `gemini_api_key` tem default vazio de propósito: se fosse obrigatória no
    import, `import app.main` explodiria sem `.env` e nenhum teste rodaria. A
    ausência é validada no adapter, no momento em que a chave é usada.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    # `gemini-2.5-flash` saiu do ar para chaves novas durante a FEAT-0002: o
    # provedor responde `404 NOT_FOUND` dizendo, com essas palavras, para usar
    # `gemini-3.6-flash`. O modelo continua listado em `models.list()`, então a
    # falha só aparece na primeira geração — e apareceu no gate da fase A.4.
    gemini_chat_model: str = "gemini-3.6-flash"
    gemini_thinking_budget: int = 0

    max_upload_mb: int = 25
    max_pdf_pages: int = 20
    max_extracted_chars: int = 60000

    chunk_size: int = 500
    chunk_overlap: int = 100

    embedding_batch_size: int = 16

    retrieval_top_k: int = 5
    similarity_threshold: float = 0.55
    history_window: int = 6
    chat_timeout_seconds: int = 60
    condense_timeout_seconds: int = 5

    postgres_user: str = "talkdoc"
    postgres_password: str = "talkdoc"
    postgres_db: str = "talkdoc"
    database_url: str = "postgresql://talkdoc:talkdoc@localhost:5432/talkdoc"

    @property
    def max_upload_bytes(self) -> int:
        """Limite de upload em bytes, que é a unidade em que ele é aplicado."""
        return self.max_upload_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devolve a configuração do processo, resolvida uma única vez.

    O cache existe para que o `.env` seja lido no primeiro acesso e não a cada
    requisição; testes que precisam de outros valores limpam o cache.
    """
    return Settings()
