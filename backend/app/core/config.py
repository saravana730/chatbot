from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DocChat"
    app_env: str = "development"
    debug: bool = True
    cors_origins: str = "http://localhost:5173"
    secure_cookies: bool = False

    bootstrap_email: str = "admin@docchat.com"
    bootstrap_password: str = "password"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    csrf_secret: str = "change-me-csrf"

    database_url: str = "postgresql+asyncpg://docchat:docchat@localhost:5432/docchat"
    database_url_sync: str = "postgresql+psycopg2://docchat:docchat@localhost:5432/docchat"
    redis_url: str = "redis://localhost:6379"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "document_chunks_v2"

    upload_dir: str = "uploads"
    max_upload_bytes: int = 52_428_800

    chunk_size: int = 700
    chunk_overlap: int = 100

    embedding_provider: str = "openrouter"
    embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    embedding_dim: int = 2048
    embedding_batch_size: int = 8

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    ocr_confidence_threshold: float = 0.5
    pdf_min_native_chars: int = 40

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    llm_context_window: int = 8192
    llm_output_reserve: int = 1024
    llm_prompt_reserve: int = 512
    llm_max_retries: int = 3
    llm_rpm_limit: int = 30
    llm_tpm_limit: int = 6000

    semantic_top_k: int = 10
    bm25_top_k: int = 10
    rerank_candidates: int = 20
    final_context_chunks: int = 5
    chat_history_turns: int = 10  # full recent turns; older turns are summarized
    relevance_threshold: float = 0.2
    faqs_per_document: int = 2
    compare_per_doc_chunks: int = 3
    compare_max_docs: int = 5
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_enabled: bool = False  # local CrossEncoder OOMs easily; fusion ranks when off
    rrf_k: int = 60

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_input_budget(self) -> int:
        return max(
            256,
            self.llm_context_window - self.llm_output_reserve - self.llm_prompt_reserve,
        )

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_less_than_size(cls, v: int, info) -> int:
        size = info.data.get("chunk_size", 700)
        if v >= size:
            raise ValueError("CHUNK_OVERLAP must be less than CHUNK_SIZE")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
