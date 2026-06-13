import getpass
import pytest
import questionary
import main


@pytest.fixture
def mock_getpass(monkeypatch):
    def _mock_getpass(secret_key):
        monkeypatch.setattr(getpass, "getpass", lambda prompt: secret_key)
    return _mock_getpass


@pytest.fixture
def mock_questionary(monkeypatch):
    def _mock_questionary(time_zone):
        def fake_autocomplete(*args, **kwargs):
            class Prompt:
                def ask(self):
                    return time_zone
            return Prompt()
        monkeypatch.setattr(questionary, "autocomplete", fake_autocomplete)
    return _mock_questionary


def test_main_creates_env_file(tmp_path, mock_getpass, mock_questionary, capsys):
    mock_getpass("my-secret-key")
    mock_questionary("Europe/London")

    main.main(base_dir=tmp_path)

    env_file = tmp_path / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "SECRET_KEY=my-secret-key" in content
    assert "TZ=Europe/London" in content

    captured = capsys.readouterr()
    assert "completed" in captured.out


def test_main_aborts_on_empty_secret_key(tmp_path, mock_getpass, mock_questionary):
    mock_getpass("")
    mock_questionary("UTC")

    result = main.main(base_dir=tmp_path)

    assert result is None
    assert not (tmp_path / ".env").exists()


def test_main_aborts_on_whitespace_secret_key(tmp_path, mock_getpass, mock_questionary):
    mock_getpass("   ")
    mock_questionary("UTC")

    result = main.main(base_dir=tmp_path)

    assert result is None
    assert not (tmp_path / ".env").exists()


def test_main_aborts_on_empty_timezone(tmp_path, mock_getpass, mock_questionary):
    mock_getpass("my-secret-key")
    mock_questionary(None)

    result = main.main(base_dir=tmp_path)

    assert result is None
    assert not (tmp_path / ".env").exists()
