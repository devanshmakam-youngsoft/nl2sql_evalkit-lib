"""serve() checks its options before it starts anything."""
import pytest

import nl2sql_evalkit
from nl2sql_evalkit.core.exceptions import ConfigError


@pytest.fixture
def started(monkeypatch, tmp_path):
    """serve() with the server, the logging set-up and the browser stubbed out; returns what it built the app with."""
    caught = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **options: caught.update(app=app))
    monkeypatch.setattr("nl2sql_evalkit.launcher.configure_logging", lambda config: None)
    monkeypatch.setattr("nl2sql_evalkit.launcher.llm_client.load_litellm", lambda: None)

    def serve(**options):
        nl2sql_evalkit.serve(lambda question: "SELECT 1", data_dir=str(tmp_path), open_browser=False, require_login=False, **options)
        return caught["app"].state.config

    return serve


def test_the_dialect_defaults_to_postgres(started):
    assert started().dialect == "postgres"


@pytest.mark.parametrize("name, dialect", [("MySQL", "mysql"), ("SQL Server", "tsql"), ("postgresql", "postgres"), ("sqlite", "sqlite")])
def test_a_dialect_can_be_given_by_any_of_its_usual_names(started, name, dialect):
    assert started(dialect=name).dialect == dialect


def test_an_unknown_dialect_is_refused_with_the_ones_that_work(started):
    with pytest.raises(ConfigError, match="dialect='oracle'.*postgres, mysql, tsql, sqlite"):
        started(dialect="oracle")


def test_the_old_source_check_option_is_gone(started):
    with pytest.raises(TypeError):
        started(source_check_mode="keyword")
