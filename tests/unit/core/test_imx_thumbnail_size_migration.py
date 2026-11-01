"""One-time migration of stored IMX thumbnail size ID 5 to 6."""

import configparser
import os

import pytest

from src.core.image_host_config import migrate_imx_thumbnail_size_ids
from src.utils.paths import get_config_path

pytestmark = pytest.mark.unit


@pytest.fixture
def ini_path():
    path = get_config_path()
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _write(path, sections):
    cfg = configparser.ConfigParser()
    for section, values in sections.items():
        cfg[section] = values
    with open(path, "w", encoding="utf-8") as f:
        cfg.write(f)


def _read(path):
    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8")
    return cfg


def test_image_hosts_5_becomes_6(ini_path):
    _write(ini_path, {"IMAGE_HOSTS": {"imx_thumbnail_size": "5"}})
    assert migrate_imx_thumbnail_size_ids() is True
    assert _read(ini_path).get("IMAGE_HOSTS", "imx_thumbnail_size") == "6"


def test_defaults_section_5_becomes_6(ini_path):
    _write(ini_path, {"DEFAULTS": {"thumbnail_size": "5"}})
    assert migrate_imx_thumbnail_size_ids() is True
    assert _read(ini_path).get("DEFAULTS", "thumbnail_size") == "6"


def test_3_is_untouched(ini_path):
    _write(ini_path, {"IMAGE_HOSTS": {"imx_thumbnail_size": "3"}, "DEFAULTS": {"thumbnail_size": "3"}})
    assert migrate_imx_thumbnail_size_ids() is False
    cfg = _read(ini_path)
    assert cfg.get("IMAGE_HOSTS", "imx_thumbnail_size") == "3"
    assert cfg.get("DEFAULTS", "thumbnail_size") == "3"


def test_runs_once(ini_path):
    _write(ini_path, {"IMAGE_HOSTS": {"imx_thumbnail_size": "5"}})
    assert migrate_imx_thumbnail_size_ids() is True

    cfg = _read(ini_path)
    cfg.set("IMAGE_HOSTS", "imx_thumbnail_size", "5")
    with open(ini_path, "w", encoding="utf-8") as f:
        cfg.write(f)

    assert migrate_imx_thumbnail_size_ids() is False
    assert _read(ini_path).get("IMAGE_HOSTS", "imx_thumbnail_size") == "5"


def test_marker_set_even_when_nothing_to_rewrite(ini_path):
    _write(ini_path, {"IMAGE_HOSTS": {"imx_thumbnail_size": "3"}})
    migrate_imx_thumbnail_size_ids()
    assert _read(ini_path).get("IMAGE_HOSTS", "imx_thumbnail_size_ids_migrated") == "true"


def test_missing_ini_gets_only_the_marker(ini_path):
    assert not os.path.exists(ini_path)
    assert migrate_imx_thumbnail_size_ids() is False
    cfg = _read(ini_path)
    assert cfg.sections() == ["IMAGE_HOSTS"]
    assert dict(cfg.items("IMAGE_HOSTS")) == {"imx_thumbnail_size_ids_migrated": "true"}


def test_fresh_install_cover_size_survives_next_start(ini_path):
    from src.core.image_host_config import save_image_host_setting

    assert migrate_imx_thumbnail_size_ids() is False  # first start, no INI yet
    save_image_host_setting("imx", "thumbnail_size", 5)  # user picks 600x600 (Cover)
    assert migrate_imx_thumbnail_size_ids() is False  # next start
    assert _read(ini_path).get("IMAGE_HOSTS", "imx_thumbnail_size") == "5"


def test_other_content_preserved(ini_path):
    _write(ini_path, {
        "IMAGE_HOSTS": {"imx_thumbnail_size": "5", "turbo_thumbnail_size": "300"},
        "DEFAULTS": {"thumbnail_size": "5", "max_retries": "3"},
        "CREDENTIALS": {"username": "someone"},
    })
    migrate_imx_thumbnail_size_ids()
    cfg = _read(ini_path)
    assert cfg.get("IMAGE_HOSTS", "turbo_thumbnail_size") == "300"
    assert cfg.get("DEFAULTS", "max_retries") == "3"
    assert cfg.get("CREDENTIALS", "username") == "someone"


def test_unwritable_ini_is_logged_and_does_not_raise(ini_path):
    # A directory where the INI should be: reading finds nothing, writing fails
    os.makedirs(ini_path)
    try:
        assert migrate_imx_thumbnail_size_ids() is False
    finally:
        os.rmdir(ini_path)


def test_unreadable_ini_is_logged_and_does_not_raise(ini_path):
    _write(ini_path, {"IMAGE_HOSTS": {"imx_thumbnail_size": "5"}})
    with pytest.MonkeyPatch.context() as mp:
        def boom(self, *a, **k):
            raise OSError("locked")
        mp.setattr(configparser.ConfigParser, "read", boom)
        assert migrate_imx_thumbnail_size_ids() is False


def test_cli_size_choices_include_cover_size_and_150():
    """bbdrop.py --size must accept 5 (600 px cover size) and 6 (150 px)."""
    import ast
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with open(os.path.join(root, "bbdrop.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument"
                and node.args and getattr(node.args[0], "value", None) == "--size"):
            kwargs = {k.arg: k.value for k in node.keywords}
            assert ast.literal_eval(kwargs["choices"]) == [1, 2, 3, 4, 5, 6]
            assert "5=600x600" in ast.literal_eval(kwargs["help"])
            return
    pytest.fail("--size argument not found in bbdrop.py")
