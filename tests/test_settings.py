"""Tests for ragin.conf settings and ragin start scaffolding."""
import os
import pytest

from ragin.conf.settings import Settings
from ragin.cli.scaffold import scaffold_project


# ── Settings tests ──────────────────────────────────────────────────


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.DATABASE_URL == "sqlite:///./ragin_dev.db"
        assert s.PROVIDER == "local"
        assert s.DEBUG is True
        assert s.HOST == "127.0.0.1"
        assert s.PORT == 8000

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("RAGIN_DATABASE_URL", "postgresql+psycopg2://x")
        monkeypatch.setenv("RAGIN_PROVIDER", "aws")
        monkeypatch.setenv("RAGIN_PORT", "3000")
        monkeypatch.setenv("RAGIN_DEBUG", "false")
        s = Settings()
        assert s.DATABASE_URL == "postgresql+psycopg2://x"
        assert s.PROVIDER == "aws"
        assert s.PORT == 3000
        assert s.DEBUG is False

    def test_legacy_db_url_env(self, monkeypatch):
        monkeypatch.setenv("RAGIN_DB_URL", "sqlite:///legacy.db")
        s = Settings()
        assert s.DATABASE_URL == "sqlite:///legacy.db"

    def test_configure_override(self):
        s = Settings()
        s.configure({"PORT": 9999})
        assert s.PORT == 9999

    def test_reset(self):
        s = Settings()
        _ = s.PORT  # trigger load
        s.reset()
        assert s._loaded is False

    def test_missing_attr_raises(self):
        s = Settings()
        with pytest.raises(AttributeError, match="NONEXISTENT"):
            _ = s.NONEXISTENT

    def test_settings_module_loading(self, tmp_path, monkeypatch):
        # Write a custom settings file
        settings_file = tmp_path / "my_settings.py"
        settings_file.write_text('DATABASE_URL = "sqlite:///custom.db"\nPORT = 4444\n')
        monkeypatch.setenv("RAGIN_SETTINGS_MODULE", "my_settings")
        monkeypatch.syspath_prepend(str(tmp_path))
        s = Settings()
        assert s.DATABASE_URL == "sqlite:///custom.db"
        assert s.PORT == 4444


# ── Scaffold tests ──────────────────────────────────────────────────


class TestScaffold:
    def test_creates_project_dir(self, tmp_path):
        target = str(tmp_path / "myapp")
        path = scaffold_project("myapp", directory=target)
        assert os.path.isfile(os.path.join(path, "main.py"))
        assert os.path.isfile(os.path.join(path, "settings.py"))

    def test_main_py_content(self, tmp_path):
        target = str(tmp_path / "demo")
        scaffold_project("demo", directory=target)
        content = open(os.path.join(target, "main.py")).read()
        assert "ServerlessApp" in content
        assert "@resource" in content

    def test_settings_py_content(self, tmp_path):
        target = str(tmp_path / "demo")
        scaffold_project("demo", directory=target)
        content = open(os.path.join(target, "settings.py")).read()
        assert "DATABASE_URL" in content
        assert "PROVIDER" in content

    def test_non_empty_dir_raises(self, tmp_path):
        target = tmp_path / "existing"
        target.mkdir()
        (target / "something.txt").write_text("x")
        with pytest.raises(FileExistsError):
            scaffold_project("existing", directory=str(target))
