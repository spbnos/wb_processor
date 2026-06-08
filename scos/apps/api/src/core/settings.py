from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
APP_NAME: str = "SCOS API"
APP_ENV: str = "dev"
APP_DEBUG: bool = True

```
POSTGRES_HOST: str = "localhost"
POSTGRES_PORT: int = 5432
POSTGRES_DB: str = "scos"
POSTGRES_USER: str = "scos"
POSTGRES_PASSWORD: str = "scos"

REDIS_HOST: str = "localhost"
REDIS_PORT: int = 6379

LOG_LEVEL: str = "INFO"

model_config = SettingsConfigDict(
    env_file=".env",
    extra="ignore"
)

@property
def database_url(self) -> str:
    return (
        f"postgresql+psycopg2://"
        f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
        f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}"
        f"/{self.POSTGRES_DB}"
    )
```

settings = Settings()
