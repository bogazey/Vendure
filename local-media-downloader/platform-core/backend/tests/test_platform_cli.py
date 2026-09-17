"""Mission 17: the operator-facing `platform product ...` / `platform
oauth-client ...` CLI (`app/scripts/platform_cli.py`). Exercises `main()`
itself (not just the underlying service functions, which are already
covered elsewhere) so a broken argparse wiring would actually be caught."""
from __future__ import annotations

from app.database.models import OAuthClient, Product
from app.scripts.platform_cli import main
from app.security import passwords


def test_product_create_inspect_update_verify_cycle(db_session, capsys):
    rc = main([
        "product", "create", "--slug", "cli-prod-a", "--name", "CLI Prod A",
        "--domain", "cli-prod-a.example", "--redirect-uri", "https://cli-prod-a.example/callback",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "CLIENT_SECRET=" in out

    rc = main(["product", "inspect", "--slug", "cli-prod-a"])
    assert rc == 0
    inspect_out = capsys.readouterr().out
    assert '"id": "cli-prod-a"' in inspect_out
    assert '"is_active": true' in inspect_out

    rc = main(["product", "verify", "--slug", "cli-prod-a"])
    assert rc == 0  # a freshly-created product from `create` passes every check
    verify_out = capsys.readouterr().out
    assert '"has_at_least_one_plan": true' in verify_out

    rc = main(["product", "update", "--slug", "cli-prod-a", "--name", "CLI Prod A Renamed"])
    assert rc == 0
    product = db_session.get(Product, "cli-prod-a")
    db_session.refresh(product)
    assert product.name == "CLI Prod A Renamed"


def test_product_inspect_unknown_product_exits_nonzero(capsys):
    rc = main(["product", "inspect", "--slug", "does-not-exist-cli"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "does-not-exist-cli" in err


def test_product_verify_reports_failure_for_a_product_with_no_client(db_session, capsys):
    if db_session.get(Product, "cli-verify-empty") is None:
        db_session.add(Product(id="cli-verify-empty", name="Empty", domain="empty.example", status="planned"))
        db_session.commit()

    rc = main(["product", "verify", "--slug", "cli-verify-empty"])
    assert rc == 1  # no OAuth client registered yet - the checklist is honest about it


def test_product_disable_then_enable_round_trip(db_session, capsys):
    main([
        "product", "create", "--slug", "cli-prod-b", "--name", "CLI Prod B",
        "--domain", "cli-prod-b.example", "--redirect-uri", "https://cli-prod-b.example/callback",
    ])
    capsys.readouterr()

    rc = main(["product", "disable", "--slug", "cli-prod-b"])
    assert rc == 0
    product = db_session.get(Product, "cli-prod-b")
    db_session.refresh(product)
    assert product.is_active is False

    rc = main(["product", "enable", "--slug", "cli-prod-b"])
    assert rc == 0
    db_session.refresh(product)
    assert product.is_active is True


def test_oauth_client_create_rotate_disable_enable(db_session, capsys):
    if db_session.get(Product, "cli-client-product") is None:
        db_session.add(Product(id="cli-client-product", name="P", domain="p.example", status="live"))
        db_session.commit()

    rc = main([
        "oauth-client", "create", "--client-id", "cli-client-x", "--name", "CLI Client X",
        "--product", "cli-client-product", "--redirect-uri", "https://p.example/callback",
    ])
    assert rc == 0
    create_out = capsys.readouterr().out
    first_secret = [line for line in create_out.splitlines() if line.startswith("  CLIENT_SECRET=")][0].split("=", 1)[1]
    client = db_session.get(OAuthClient, "cli-client-x")
    assert passwords.verify_password(first_secret, client.client_secret_hash)

    rc = main(["oauth-client", "rotate-secret", "--client-id", "cli-client-x"])
    assert rc == 0
    rotate_out = capsys.readouterr().out
    new_secret = [line for line in rotate_out.splitlines() if line.startswith("  CLIENT_SECRET=")][0].split("=", 1)[1]
    assert new_secret != first_secret
    db_session.refresh(client)
    assert passwords.verify_password(new_secret, client.client_secret_hash)
    assert not passwords.verify_password(first_secret, client.client_secret_hash)  # old one is dead

    rc = main(["oauth-client", "disable", "--client-id", "cli-client-x"])
    assert rc == 0
    db_session.refresh(client)
    assert client.is_active is False

    rc = main(["oauth-client", "enable", "--client-id", "cli-client-x"])
    assert rc == 0
    db_session.refresh(client)
    assert client.is_active is True


def test_oauth_client_rotate_secret_unknown_client_exits_nonzero(capsys):
    rc = main(["oauth-client", "rotate-secret", "--client-id", "does-not-exist-cli-client"])
    assert rc == 1
