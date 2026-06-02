from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "MotoServicio Timón V2"
    app_version: str = "2.0.0"
    debug: bool = False

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "root"
    mysql_database: str = "motoservicio"

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_session_ttl: int = 1800

    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_conversaciones_collection: str = "conversaciones"
    qdrant_conocimiento_collection: str = "conocimiento"
    qdrant_vector_size: int = 768

    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "text-embedding-004"

    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"

    celery_broker_url: str = "amqp://guest:guest@rabbitmq:5672//"

    rate_limit_max_requests: int = 10
    rate_limit_window_seconds: int = 60

    max_message_length: int = 4096
    tool_timeout: int = 10
    max_agent_cycles: int = 5
    reflection_max_attempts: int = 2
    rag_threshold: float = 0.75
    rag_oversample_factor: int = 3
    episodic_threshold: float = 0.70

    log_level: str = "INFO"

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
