#!/usr/bin/env python3
"""Detecta se o motor de GEX do ks4 está atrás do commit que vai para produção.

Compara o sha256 dos arquivos do motor (ENGINE_GLOBS) no commit com os do servidor.
Contexto: em 28/11/2026 as Walls do app divergiam das do Miqueias porque 12 arquivos do motor no ks4
estavam uma versão atrás do repositório e nada avisava (o deploy.sh só levava a cloud_saas).

Uso (a partir da raiz do repositório):
  python3 deploy/ks4/engine_drift.py check [--host app@ks4] [--rev HEAD]   # sai 1 se houver drift
  python3 deploy/ks4/engine_drift.py check --list                          # só imprime o que precisa subir

Só lê: nunca altera o servidor. Quem envia é `deploy.sh engine`.
"""
import argparse
import fnmatch
import hashlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Arquivos do motor que rodam no mt5-a (um nível de pasta, só .py).
ENGINE_GLOBS = ("gex/engine/*.py", "core/*.py")
REMOTE_ROOT = "/home/app/mt5-wine-lab/prefix-a/drive_c/magicwalls"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _matches(path: str) -> bool:
    # fnmatch deixa "*" casar "/" também, então exige a mesma profundidade do padrão.
    return any(fnmatch.fnmatch(path, g) and path.count("/") == g.count("/") for g in ENGINE_GLOBS)


def local_hashes(root, rev: str = "HEAD") -> dict:
    """sha256 dos arquivos do motor como estão no commit `rev` (não na pasta de trabalho)."""
    root = str(root)
    names = subprocess.run(["git", "ls-tree", "-r", "--name-only", rev], cwd=root, check=True,
                           capture_output=True, text=True).stdout.splitlines()
    out = {}
    for name in names:
        if not _matches(name):
            continue
        blob = subprocess.run(["git", "show", f"{rev}:{name}"], cwd=root, check=True, capture_output=True).stdout
        out[name] = hashlib.sha256(blob).hexdigest()
    return out


def parse_sha256sum(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, path = line.partition(" ")
        out[path.lstrip(" *")] = digest
    return out


def remote_hashes(host: str, remote_root: str = REMOTE_ROOT) -> dict:
    find = " -o ".join(f"-path './{g}'" for g in ENGINE_GLOBS)
    cmd = f"cd {remote_root} && find . -maxdepth 3 \\( {find} \\) -type f | sed 's#^\\./##' | sort | xargs -r sha256sum"
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, cmd],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"não consegui ler o motor em {host}: {r.stderr.strip() or r.returncode}")
    return {p: h for p, h in parse_sha256sum(r.stdout).items() if _matches(p)}


@dataclass
class Drift:
    different: list = field(default_factory=list)
    missing_remote: list = field(default_factory=list)
    extra_remote: list = field(default_factory=list)

    @property
    def to_sync(self) -> list:
        return sorted(self.different + self.missing_remote)

    @property
    def has_drift(self) -> bool:
        # Arquivo sobrando no servidor é só aviso (nunca apagamos nada lá).
        return bool(self.to_sync)


def compare(local: dict, remote: dict) -> Drift:
    return Drift(
        different=sorted(p for p in local if p in remote and local[p] != remote[p]),
        missing_remote=sorted(p for p in local if p not in remote),
        extra_remote=sorted(p for p in remote if p not in local),
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--host", default="app@ks4")
    c.add_argument("--rev", default="HEAD")
    c.add_argument("--remote-root", default=REMOTE_ROOT)
    c.add_argument("--list", action="store_true", help="imprime só os caminhos a sincronizar (um por linha)")
    args = ap.parse_args(argv)

    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True).stdout.strip()
    drift = compare(local_hashes(Path(root), args.rev), remote_hashes(args.host, args.remote_root))
    if args.list:
        print("\n".join(drift.to_sync))
        return 1 if drift.has_drift else 0
    if not drift.has_drift:
        print(f"motor do {args.host} igual ao commit {args.rev} ({len(local_hashes(Path(root), args.rev))} arquivos)")
        for p in drift.extra_remote:
            print(f"  aviso: só existe no servidor (não será mexido): {p}")
        return 0
    print(f"MOTOR DESATUALIZADO em {args.host} em relação a {args.rev}:")
    for p in drift.different:
        print(f"  diferente: {p}")
    for p in drift.missing_remote:
        print(f"  ausente no servidor: {p}")
    for p in drift.extra_remote:
        print(f"  aviso: só existe no servidor (não será mexido): {p}")
    print("Sincronize com: deploy/ks4/deploy.sh engine")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        sys.exit(2)
