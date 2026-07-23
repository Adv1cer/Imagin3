import pytest
from imagin.config import load_settings, MissingConfigError

REQUIRED_VARS = ["DATABASE_URL", "OBJECT_STORE_ROOT", "COMFYUI_BASE_URL", "UTCC_OFFICIAL_DOMAIN"]


def test_load_settings_reads_all_required_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://imagin:imagin@postgres:5432/imagin")
    monkeypatch.setenv("OBJECT_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("COMFYUI_BASE_URL", "http://dgx-host:8188")
    monkeypatch.setenv("UTCC_OFFICIAL_DOMAIN", "utcc.ac.th")

    settings = load_settings()

    assert settings.database_url == "postgresql+psycopg2://imagin:imagin@postgres:5432/imagin"
    assert settings.object_store_root == str(tmp_path)
    assert settings.comfyui_base_url == "http://dgx-host:8188"
    assert settings.utcc_official_domain == "utcc.ac.th"


@pytest.mark.parametrize("missing_var", REQUIRED_VARS)
def test_load_settings_raises_when_var_missing(monkeypatch, tmp_path, missing_var):
    for var in REQUIRED_VARS:
        monkeypatch.setenv(var, "placeholder" if var != "OBJECT_STORE_ROOT" else str(tmp_path))
    monkeypatch.delenv(missing_var)

    with pytest.raises(MissingConfigError):
        load_settings()
