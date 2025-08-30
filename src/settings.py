from typing import Optional
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


class Redis(Environment):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[SecretStr] = None


class Bot(Environment):
    TOKEN: SecretStr = SecretStr("8496902188:AAHq-QGmeiKHBPhlCNWAJT_KA6nfrwjH544") 


class Settings(Bot, Redis):
    USER_ID: int = 0


settings = Settings()
