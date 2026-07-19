from pathlib import Path

from scripts.package_smoke import environment_executables


def test_package_smoke_uses_posix_virtual_environment_commands() -> None:
    python, command = environment_executables(Path("venv"), os_name="posix")

    assert python == Path("venv/bin/python")
    assert command == Path("venv/bin/context-loom")


def test_package_smoke_uses_windows_virtual_environment_commands() -> None:
    python, command = environment_executables(Path("venv"), os_name="nt")

    assert python == Path("venv/Scripts/python.exe")
    assert command == Path("venv/Scripts/context-loom.exe")
