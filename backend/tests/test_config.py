from app.config import Settings


def test_configuration_loading() -> None:
    settings = Settings(database_url="sqlite:///test.db", environment="test")
    assert settings.database_url == "sqlite:///test.db"
    assert settings.environment == "test"
