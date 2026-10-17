"""How the tests find the corpus: tests/corpus_paths.py.

The corpus is private, so no published file names where it lives. A machine
that has it says so in its Git configuration, `zij.corpusDir`: the global one,
which every clone reads, or a repository's own, which overrides it but does
not travel with a clone. The CORPUS_DIR variable overrides both; with neither
the corpus is absent, as on CI. Each case runs corpus_paths.py from a copy in a scratch repository, in a
fresh interpreter, so the run's own settings do not leak in.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent


def _resolve(folder: Path, corpus_dir: str | None, global_config: Path | None = None) -> tuple[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "CORPUS_DIR" and not k.startswith("GIT_")}
    env["GIT_CEILING_DIRECTORIES"] = str(folder.parent)      # no repository above the scratch one
    env["GIT_CONFIG_GLOBAL"] = str(global_config) if global_config else os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    if corpus_dir is not None:
        env["CORPUS_DIR"] = corpus_dir
    out = subprocess.run([sys.executable, "-c", "import corpus_paths as c; print(c.CORPUS_DIR); print(c.CORPUS_SOURCE)"],
                         cwd=folder / "tests", env=env, capture_output=True, text=True, check=True).stdout
    where, how = out.splitlines()
    return where, how


@pytest.fixture
def clone(tmp_path):
    root = tmp_path / "clone"
    (root / "tests").mkdir(parents=True)
    shutil.copy(TESTS / "corpus_paths.py", root / "tests" / "corpus_paths.py")
    subprocess.run(["git", "init", "-q", str(root)], check=True,
                   env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull))
    corpus = tmp_path / "the corpus"
    corpus.mkdir()
    return root, corpus


def _set_key(root: Path, value: str) -> None:
    subprocess.run(["git", "-C", str(root), "config", "zij.corpusDir", value], check=True,
                   env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull))


def test_the_clones_key_finds_the_corpus(clone):
    root, corpus = clone
    _set_key(root, str(corpus))
    assert _resolve(root, None) == (str(corpus), "git config")


def test_with_no_key_the_corpus_is_absent(clone):
    root, _ = clone
    where, how = _resolve(root, None)
    assert how == "absent" and not Path(where).exists()


def test_corpus_dir_overrides_the_key(clone, tmp_path):
    root, corpus = clone
    _set_key(root, str(corpus))
    other = tmp_path / "another checkout"
    assert _resolve(root, str(other)) == (str(other), "CORPUS_DIR")


def test_an_empty_corpus_dir_means_absent_not_the_working_folder(clone):
    root, corpus = clone
    _set_key(root, str(corpus))
    where, how = _resolve(root, "")
    assert how == "CORPUS_DIR" and not Path(where).exists()


def test_outside_any_repository_the_corpus_is_absent(tmp_path):
    root = tmp_path / "unpacked"
    (root / "tests").mkdir(parents=True)
    shutil.copy(TESTS / "corpus_paths.py", root / "tests" / "corpus_paths.py")
    where, how = _resolve(root, None)
    assert how == "absent" and not Path(where).exists()


def test_no_published_test_names_where_the_corpus_lives():
    """The rule's own file carries no default folder: only the key."""
    text = (TESTS / "corpus_paths.py").read_text(encoding="utf-8")
    assert "Path.home()" not in text and "Desktop" not in text


# ---------------------------------------------------------------- the key in the global configuration
#
# A repository's own configuration does not travel with `git clone`, so a key
# set only there leaves every clone skipping the corpus tests green. Set once
# in the global configuration, every clone and worktree reads it.

def _git(*args, global_config=os.devnull, cwd=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=str(global_config), GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", *args], check=True, capture_output=True, cwd=cwd, env=env)


@pytest.fixture
def plain_clone(tmp_path):
    """A repository whose own configuration holds the key, and a plain
    `git clone` of it; plus an empty global configuration file."""
    origin = tmp_path / "origin"
    (origin / "tests").mkdir(parents=True)
    shutil.copy(TESTS / "corpus_paths.py", origin / "tests" / "corpus_paths.py")
    corpus = tmp_path / "the corpus"
    corpus.mkdir()
    _git("init", "-q", str(origin))
    _git("-C", str(origin), "add", "-A")
    _git("-C", str(origin), "commit", "-qm", "x")
    _git("-C", str(origin), "config", "zij.corpusDir", str(corpus))
    clone = tmp_path / "work" / "clone"
    _git("clone", "-q", "--no-local", str(origin), str(clone))
    glob_cfg = tmp_path / "global.gitconfig"
    glob_cfg.write_text("")
    return origin, clone, corpus, glob_cfg


def test_a_repositorys_own_key_does_not_reach_a_clone(plain_clone):
    origin, clone, corpus, glob_cfg = plain_clone
    assert _resolve(origin, None, glob_cfg) == (str(corpus), "git config")
    where, how = _resolve(clone, None, glob_cfg)
    assert how == "absent" and not Path(where).exists()


def test_a_key_in_the_global_configuration_is_found_by_a_plain_clone(plain_clone):
    _, clone, corpus, glob_cfg = plain_clone
    _git("config", "--global", "zij.corpusDir", str(corpus), global_config=glob_cfg)
    assert _resolve(clone, None, glob_cfg) == (str(corpus), "git config")


def test_a_repositorys_own_key_overrides_the_global_one(plain_clone, tmp_path):
    _, clone, corpus, glob_cfg = plain_clone
    _git("config", "--global", "zij.corpusDir", str(tmp_path / "the global one"), global_config=glob_cfg)
    _git("-C", str(clone), "config", "zij.corpusDir", str(corpus), global_config=glob_cfg)
    assert _resolve(clone, None, glob_cfg) == (str(corpus), "git config")


def test_corpus_dir_overrides_the_repository_and_the_global_keys(plain_clone, tmp_path):
    _, clone, corpus, glob_cfg = plain_clone
    _git("config", "--global", "zij.corpusDir", str(tmp_path / "the global one"), global_config=glob_cfg)
    _git("-C", str(clone), "config", "zij.corpusDir", str(corpus), global_config=glob_cfg)
    other = tmp_path / "another checkout"
    assert _resolve(clone, str(other), glob_cfg) == (str(other), "CORPUS_DIR")
    where, how = _resolve(clone, "", glob_cfg)
    assert how == "CORPUS_DIR" and not Path(where).exists()
