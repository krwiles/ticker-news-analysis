"""scripts/init-secrets.sh, exercised end to end in a throwaway directory -- see docs/plans/0040-*.md."""

import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "init-secrets.sh"


def _run(tmp_path, *args, stdin=""):
    # Runs the real script, pointed at a throwaway secrets dir and .env instead of the repo's own.
    env = {"SECRETS_DIR": str(tmp_path / "secrets"), "ENV_FILE": str(tmp_path / ".env"), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        ["bash", str(SCRIPT), *args], input=stdin, capture_output=True, text=True, env=env, cwd=tmp_path
    )


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_from_env_moves_keys_into_files_strips_them_and_never_prints_them(tmp_path):
    # Arrange: a .env holding real-looking keys alongside non-secret config.
    (tmp_path / ".env").write_text(
        "POSTGRES_USER=ticker\nPOSTGRES_PASSWORD=pw-zq81\nFINNHUB_API_KEY=fh-zq82\n"
        "OPENAI_API_KEY=oa-zq83\nGOOGLE_CLIENT_ID=abc\n"
    )

    # Act.
    result = _run(tmp_path, "--from-env")

    # Assert: each secret landed in its own file, owner-only, with no trailing newline.
    secrets = tmp_path / "secrets"
    assert (secrets / "finnhub_api_key").read_text() == "fh-zq82"
    assert (secrets / "openai_api_key").read_text() == "oa-zq83"
    assert (secrets / "postgres_password").read_text() == "pw-zq81"
    assert _mode(secrets / "finnhub_api_key") == 0o600
    assert _mode(secrets) == 0o700
    # Assert: the three keys are gone from .env, non-secret lines kept, and the feature flag written.
    env_text = (tmp_path / ".env").read_text()
    assert "zq8" not in env_text
    assert "POSTGRES_USER=ticker" in env_text and "GOOGLE_CLIENT_ID=abc" in env_text
    assert "SENTIMENT_CONFIGURED=true" in env_text
    # Assert: no secret value ever reached the terminal.
    assert "zq8" not in result.stdout + result.stderr


def test_rerunning_is_idempotent_and_never_overwrites_an_existing_secret(tmp_path):
    # Arrange: one completed run.
    (tmp_path / ".env").write_text("FINNHUB_API_KEY=first\nPOSTGRES_PASSWORD=pw\n")
    _run(tmp_path, "--from-env")

    # Act: run again, with a different value now sitting in .env.
    (tmp_path / ".env").write_text((tmp_path / ".env").read_text() + "FINNHUB_API_KEY=second\n")
    _run(tmp_path, "--from-env")

    # Assert: the existing file wins, untouched.
    assert (tmp_path / "secrets" / "finnhub_api_key").read_text() == "first"


def test_openai_key_is_optional_and_turns_the_sentiment_flag_off(tmp_path):
    # Arrange: only the required secrets exist anywhere.
    (tmp_path / ".env").write_text("FINNHUB_API_KEY=fh\nPOSTGRES_PASSWORD=pw\n")

    # Act: the interactive OpenAI prompt is answered with a bare Enter.
    _run(tmp_path, "--from-env", stdin="\n")

    # Assert: an empty file exists (Compose needs the file), and the flag says sentiment is off.
    assert (tmp_path / "secrets" / "openai_api_key").read_text() == ""
    assert "SENTIMENT_CONFIGURED=false" in (tmp_path / ".env").read_text()


def test_rotate_replaces_just_the_named_secret(tmp_path):
    # Arrange: a finished setup.
    (tmp_path / ".env").write_text("FINNHUB_API_KEY=old\nPOSTGRES_PASSWORD=pw\nOPENAI_API_KEY=oa\n")
    _run(tmp_path, "--from-env")

    # Act: rotate only the Finnhub key, typing the new value at the prompt.
    _run(tmp_path, "--rotate", "finnhub_api_key", stdin="new-key\n")

    # Assert: that file changed; the others did not.
    assert (tmp_path / "secrets" / "finnhub_api_key").read_text() == "new-key"
    assert (tmp_path / "secrets" / "openai_api_key").read_text() == "oa"
    assert (tmp_path / "secrets" / "postgres_password").read_text() == "pw"


def test_a_required_secret_cannot_be_left_empty(tmp_path):
    # Arrange: no .env, and the Finnhub prompt gets a bare Enter.
    # Act: the Postgres prompt takes its dev default, then Finnhub is left empty.
    result = _run(tmp_path, stdin="\n\n")

    # Assert: refuses, and leaves no empty required file behind.
    assert result.returncode != 0
    assert not (tmp_path / "secrets" / "finnhub_api_key").exists()
