from app.settings import Settings


def make_settings(**kwargs) -> Settings:
    values = {
        "_env_file": None,
        "token_secret": "0123456789abcdef0123456789abcdef",
    }
    values.update(kwargs)
    return Settings(**values)


def test_gateway_defaults_listen_on_all_interfaces():
    settings = make_settings()

    assert settings.gateway_host == "0.0.0.0"
    assert settings.gateway_http_port == 18080
    assert settings.gateway_https_port == 18088


def test_default_public_url_is_https():
    settings = make_settings()

    assert settings.public_base_url == "https://127.0.0.1:18088"


def test_default_token_ttl_is_600_seconds():
    settings = make_settings()

    assert settings.token_ttl_seconds == 600


def test_default_tls_paths():
    settings = make_settings()

    assert settings.tls_cert_file == "certs/gateway.crt"
    assert settings.tls_key_file == "certs/gateway.key"


def test_cors_origins_parse_comma_separated_values():
    settings = make_settings(
        cors_allow_origins=(
            "https://10.2.192.9:18088, "
            "https://player.test"
        )
    )

    assert settings.cors_origins == [
        "https://10.2.192.9:18088",
        "https://player.test",
    ]


def test_cors_wildcard_wins():
    settings = make_settings(
        cors_allow_origins="https://player.test,*"
    )

    assert settings.cors_origins == ["*"]