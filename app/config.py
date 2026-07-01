from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    gitops_repo_path: str = "./gitops-repo"

    provision_delay_min: int = 8
    provision_delay_max: int = 15

    model_config = {"env_file": ".env"}


settings = Settings()
