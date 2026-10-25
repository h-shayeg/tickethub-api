from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 30


settings = Settings()
