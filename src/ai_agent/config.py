from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    zai_api_key: str = ""
    zai_base_url: str = "https://api.z.ai/api/paas/v4"
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    gemini_api_key: str = ""
    # Client billed key — used only by paid Gemini catalog models (Paid chip).
    # Free Flash / Flash-Lite keep using gemini_api_key.
    gemini_paid_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    # When set, forces Gemini account tier: true=paid (billing on), false=free tier.
    gemini_billing_enabled: bool | None = None
    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.ai/v1"
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.io/v1"
    # Alibaba Cloud Model Studio / DashScope OpenAI-compatible
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    google_client_id: str = ""
    google_sheets_folder_id: str = ""

    wp_site_url: str = ""
    wp_user: str = "bbs-ai-builder"
    wp_app_password: str = ""
    cors_origins: str = "*"

    intake_api_key: str = "dev-local-key"
    host: str = "0.0.0.0"
    port: int = 8080
    data_dir: str = "data"

    default_copy_model: str = "gemini-3.5-flash"
    default_compose_model: str = "gemini-3.5-flash-lite"
    writer_model: str = "gemini-3.5-flash"
    verifier_model: str = "gemini-3.5-flash-lite"
    request_timeout_sec: float = 120.0

    def validate_models(self) -> None:
        from ai_agent.models.registry import REGISTRY

        for role, model_id in (
            ("writer_model", self.writer_model),
            ("verifier_model", self.verifier_model),
            ("default_copy_model", self.default_copy_model),
            ("default_compose_model", self.default_compose_model),
        ):
            if model_id and model_id not in REGISTRY:
                raise ValueError(f"{role}={model_id!r} is not a registered model")


@lru_cache
def get_settings() -> Settings:
    return Settings()
