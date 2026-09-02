from app.settings import Settings


def test_gateway_defaults_listen_on_all_interfaces():
    settings = Settings(_env_file=None, token_secret="0123456789abcdef0123456789abcdef")
    assert settings.gateway_host == "0.0.0.0"
    assert settings.gateway_port == 18088


def test_cors_origins_parse_comma_separated_values():
    settings = Settings(
        _env_file=None,
        token_secret="0123456789abcdef0123456789abcdef",
        cors_allow_origins="http://10.2.192.8:8080, http://player.test",
    )
    assert settings.cors_origins == [
        "http://10.2.192.8:8080",
        "http://player.test",
    ]


def test_cors_wildcard_wins():
    settings = Settings(
        _env_file=None,
        token_secret="0123456789abcdef0123456789abcdef",
        cors_allow_origins="http://player.test,*",
    )
    assert settings.cors_origins == ["*"]
