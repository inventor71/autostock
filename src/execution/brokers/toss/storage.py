"""Private local storage shared by setup, token refresh and order reconciliation."""
from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from src.core.exceptions import BrokerError


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostock/toss"


def state_dir() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "autostock/toss"


def private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise BrokerError(f"Toss storage directory must be owned by you with mode 0700: {path}")


def _check_file(fd: int) -> None:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise BrokerError("Toss private files must be owned by you with mode 0600")


def read_json(path: Path) -> dict:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return {}
    except OSError:
        raise BrokerError("Cannot securely open Toss private file") from None
    with os.fdopen(fd, "r") as stream:
        _check_file(stream.fileno())
        try:
            value = json.load(stream)
        except (ValueError, UnicodeError):
            raise BrokerError("Toss private file is invalid; restore it before continuing") from None
    if not isinstance(value, dict):
        raise BrokerError("Toss private file must contain an object")
    return value


def write_json(path: Path, value: dict) -> None:
    private_dir(path.parent)
    if path.is_symlink():
        raise BrokerError("Refusing a symlink for Toss private storage")
    fd, temporary = tempfile.mkstemp(prefix=".toss-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(path: Path):
    private_dir(path.parent)
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    except OSError:
        raise BrokerError("Cannot securely open Toss lock file") from None
    with os.fdopen(fd, "a+") as stream:
        _check_file(stream.fileno())
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
