from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_nginx_replaces_forwarded_chain_with_trusted_real_ip():
    for name in ("nginx.conf", "nginx.tls.conf"):
        config = (ROOT / "frontend" / name).read_text()
        assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
        assert "$proxy_add_x_forwarded_for" not in config


def test_tls_config_defers_csp_until_checkout_sources_are_verified():
    config = (ROOT / "frontend" / "nginx.tls.conf").read_text()
    assert "Content-Security-Policy-Report-Only" not in config
    assert "Content-Security-Policy \"" not in config
    deployment = (ROOT / "docs" / "DEPLOYMENT.md").read_text()
    assert "Candidate policy for that validation (not currently emitted)" in deployment
