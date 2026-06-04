from app.config import settings


class TestConfig:
    def test_app_name(self):
        assert settings.app_name == "MotoServicio Timón V2"

    def test_app_version(self):
        assert settings.app_version == "2.0.0"

    def test_redis_settings(self):
        assert settings.redis_host == "redis"
        assert settings.redis_port == 6379
        assert settings.redis_session_ttl == 1800

    def test_qdrant_settings(self):
        assert settings.qdrant_host == "qdrant"
        assert settings.qdrant_vector_size == 768

    def test_gemini_settings(self):
        assert settings.gemini_model == "gemini-2.5-flash-lite"
        assert settings.gemini_embedding_model == "gemini-embedding-002"

    def test_rate_limit_settings(self):
        assert settings.rate_limit_max_requests == 10
        assert settings.rate_limit_window_seconds == 60

    def test_mysql_settings(self):
        assert settings.mysql_host == "mysql"
        assert settings.mysql_port == 3306

    def test_rag_settings(self):
        assert settings.rag_threshold == 0.75
        assert settings.rag_oversample_factor == 3
