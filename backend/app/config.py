from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    data_dir: str = "data"
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
