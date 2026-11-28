"""Regressão: o motor de GEX do ks4 não pode ficar atrás do commit que vai para produção.

Em 28/11/2026 as Walls do app divergiam das do Miqueias porque os 12 arquivos do motor no ks4
(gex/engine/*, core/gex_live_dealer_engine.py, core/profit_mt5_flow_engine.py) estavam uma versão
atrás do repositório e o deploy.sh não olhava para eles. Estes testes garantem que:
  - o detector (deploy/ks4/engine_drift.py) acha arquivo diferente, ausente e sobrando;
  - ele compara com o commit (git), não com o que está solto na pasta;
  - o deploy.sh chama a checagem antes de qualquer deploy e oferece o alvo `engine`.
"""
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SH = ROOT / "deploy" / "ks4" / "deploy.sh"


def _load():
    spec = importlib.util.spec_from_file_location("engine_drift", ROOT / "deploy" / "ks4" / "engine_drift.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ed = _load()


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)})


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "gex" / "engine").mkdir(parents=True)
    (tmp_path / "gex" / "engine" / "sub").mkdir()
    (tmp_path / "core").mkdir()
    (tmp_path / "gex" / "engine" / "walls_calculator.py").write_text("v1\n")
    (tmp_path / "gex" / "engine" / "sub" / "fora.py").write_text("nao entra\n")
    (tmp_path / "gex" / "engine" / "leia.txt").write_text("nao entra\n")
    (tmp_path / "core" / "flow.py").write_text("v1\n")
    (tmp_path / "cloud_saas.py").write_text("nao entra\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "a")
    return tmp_path


def test_local_hashes_only_engine_py_files_of_the_commit(repo):
    h = ed.local_hashes(repo, "HEAD")
    assert sorted(h) == ["core/flow.py", "gex/engine/walls_calculator.py"]


def test_local_hashes_come_from_the_commit_not_the_working_tree(repo):
    (repo / "core" / "flow.py").write_text("editado e nao commitado\n")
    committed = ed.local_hashes(repo, "HEAD")["core/flow.py"]
    assert committed == ed.sha256_text("v1\n")


def test_identical_engine_has_no_drift(repo):
    h = ed.local_hashes(repo, "HEAD")
    r = ed.compare(h, dict(h))
    assert not r.has_drift
    assert r.to_sync == []


def test_stale_remote_file_is_reported_as_different(repo):
    remote = ed.local_hashes(repo, "HEAD")  # o ks4 ficou no commit A
    (repo / "gex" / "engine" / "walls_calculator.py").write_text("v2 corrigido\n")
    _git(repo, "commit", "-qam", "b")  # o repositório avançou (como o 2bf56ca do Miqueias)
    r = ed.compare(ed.local_hashes(repo, "HEAD"), remote)
    assert r.has_drift
    assert r.different == ["gex/engine/walls_calculator.py"]
    assert r.to_sync == ["gex/engine/walls_calculator.py"]


def test_file_missing_on_remote_is_drift(repo):
    local = ed.local_hashes(repo, "HEAD")
    remote = {k: v for k, v in local.items() if k != "core/flow.py"}
    r = ed.compare(local, remote)
    assert r.missing_remote == ["core/flow.py"]
    assert r.to_sync == ["core/flow.py"]


def test_extra_remote_file_is_reported_but_never_synced(repo):
    local = ed.local_hashes(repo, "HEAD")
    remote = dict(local, **{"core/so_no_servidor.py": "x" * 64})
    r = ed.compare(local, remote)
    assert r.extra_remote == ["core/so_no_servidor.py"]
    assert r.to_sync == []  # nunca apagamos nada no servidor


def test_parse_sha256sum_output():
    out = f"{'a' * 64}  gex/engine/main.py\n{'b' * 64} *core/x.py\n\n"
    assert ed.parse_sha256sum(out) == {"gex/engine/main.py": "a" * 64, "core/x.py": "b" * 64}


def test_real_repo_engine_files_are_covered_by_the_globs():
    h = ed.local_hashes(ROOT, "HEAD")
    for must in ("gex/engine/walls_calculator.py", "gex/engine/b3_parser.py", "gex/engine/main.py",
                 "core/profit_mt5_flow_engine.py", "core/gex_live_dealer_engine.py"):
        assert must in h, f"{must} ficou fora da checagem de drift"


# ---- o deploy.sh precisa usar a checagem ----

def test_deploy_sh_is_valid_bash():
    subprocess.run(["bash", "-n", str(DEPLOY_SH)], check=True)


def test_deploy_sh_checks_engine_drift_before_tests_and_deploy():
    txt = DEPLOY_SH.read_text()
    flow = txt[txt.index("# ---------- fluxo ----------"):]
    assert "check_engine_drift" in flow, "o fluxo do deploy não chama check_engine_drift"
    assert flow.index("check_engine_drift") < flow.index("run_tests"), "a checagem tem de vir antes dos testes e do envio"


def test_deploy_sh_has_engine_target_and_refuses_drift_without_force():
    txt = DEPLOY_SH.read_text()
    assert re.search(r"server\|front\|engine\|all", txt), "falta o alvo `engine` nos argumentos"
    fn = txt[txt.index("check_engine_drift() {"):]
    fn = fn[: fn.index("\n}\n")]
    assert "die " in fn and "FORCE" in fn, "com drift o deploy deve parar, salvo --force"
