"""Launch Miqueias's reference server without changing its operational code.

Run this with a Windows Python that has MetaTrader5 installed. The script
imports the reference repo, patches only runtime wiring (MT5 path / portable
mode / HTTP port), and serves the original FastAPI app.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


DEFAULT_REPO = os.environ.get(
    "MIQUEIAS_REPO",
    r"C:\Users\brenoperucchi\devs\miqueias\miqueias-wdowin-reference",
)
DEFAULT_MT5_PATH = os.environ.get(
    "MIQUEIAS_MT5_PATH",
    r"E:\MetaTraders\MT5-Python\Ticks\terminal64.exe",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Miqueias reference FastAPI server on a comparison port."
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Path to Miqueias repo")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--mt5-path", default=DEFAULT_MT5_PATH)
    parser.add_argument(
        "--portable",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass portable=True to mt5.initialize via runtime monkeypatch",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Import and patch the reference app, then exit without starting uvicorn",
    )
    return parser.parse_args(argv)


def _prepare_import_path(repo: Path) -> None:
    repo = repo.resolve()
    if not (repo / "server.py").exists():
        raise SystemExit(f"Miqueias repo not found or missing server.py: {repo}")

    # The launcher lives in our repo; ensure `import core.*` resolves to the
    # reference repo, never to WDOWIN's local core package.
    launcher_root = Path(__file__).resolve().parents[1]
    sys.path[:] = [
        p for p in sys.path
        if p and Path(p).resolve() != launcher_root
    ]
    sys.path.insert(0, str(repo))
    os.chdir(repo)


def _patch_mt5_runtime(server_module, *, mt5_path: str, portable: bool) -> None:
    import MetaTrader5 as mt5
    import core.config as ref_config
    import core.mt5_client as ref_mt5_client

    ref_config.MT5_PATH = mt5_path
    ref_mt5_client.MT5_PATH = mt5_path
    server_module.MT5_PATH = mt5_path

    if not portable:
        return

    def connect_mt5_portable() -> bool:
        if mt5.terminal_info() is not None:
            return True

        kwargs = {"timeout": 10000}
        if mt5_path:
            kwargs["path"] = mt5_path
            print(f"[MT5-REF] Conectando ao terminal: {mt5_path}")
        kwargs["portable"] = True

        if not mt5.initialize(**kwargs):
            print(f"[MT5-REF] Falha ao inicializar: {mt5.last_error()}")
            return False

        info = mt5.terminal_info()
        print(f"[MT5-REF] Conectado — {info.name} | path: {info.path}")
        for sym in [ref_config.SYMBOL_A, ref_config.SYMBOL_B, ref_config.DI_SYMBOL]:
            mt5.symbol_select(sym, True)
        print(
            "[MT5-REF] Symbols ativados: "
            f"{ref_config.SYMBOL_A}, {ref_config.SYMBOL_B}, {ref_config.DI_SYMBOL}"
        )
        return True

    ref_mt5_client.connect_mt5 = connect_mt5_portable
    server_module.connect_mt5 = connect_mt5_portable


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo = Path(args.repo)
    _prepare_import_path(repo)

    print(f"[REF] Importing server.py from {repo}", flush=True)
    import server as miqueias_server
    print("[REF] server.py imported", flush=True)

    _patch_mt5_runtime(
        miqueias_server,
        mt5_path=args.mt5_path,
        portable=bool(args.portable),
    )
    print("[REF] runtime patches applied", flush=True)

    if args.check_only:
        routes = [
            getattr(route, "path", "")
            for route in getattr(miqueias_server.app, "routes", [])
        ]
        print("[REF] check-only OK", flush=True)
        print(f"[REF] routes: {', '.join(sorted(routes))}", flush=True)
        return 0

    import uvicorn

    print("=" * 72)
    print("  Miqueias reference server — headless comparison mode")
    print(f"  repo:      {repo}")
    print(f"  mt5_path:  {args.mt5_path}")
    print(f"  portable:  {bool(args.portable)}")
    print(f"  v2:        http://localhost:{args.port}/api/v2/regime")
    print(f"  di:        http://localhost:{args.port}/api/di-regime")
    print("=" * 72)
    uvicorn.run(miqueias_server.app, host=args.host, port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
