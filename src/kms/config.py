# config.py script
# Kod: Engelska
# Kommentarer: Svenska

"""
Central config för KMS. Alla environment-variable läsning sker här. Alla andra moduler importerar 'settings'-objektet istället
för att anropa os.environ direkt.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


# Bryter mot Python och PEP8 naming convention MEN detta är för min egen skull att ha variablerna i CAPS.
class Settings(BaseSettings):
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_HOST: str
    DB_PORT: int

    GRUNDEN_API_KEY: str  # oanvänd förrän MVP v3

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_ENDPOINT_URL: str
    S3_BUCKET_NAME: str = "kms-course-material"  # Eget default värde, min buckets namn är ej secret och bör bo hemma i min Settings class

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        """
        Builds ONE TIME, is used everywhere. Alembic, SQLAlchemy engine,
        furute scripts. No file should construct this string itself.
        """
        return (
            f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
