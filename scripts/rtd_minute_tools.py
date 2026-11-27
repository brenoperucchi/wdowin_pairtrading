# -*- coding: utf-8 -*-
"""
Ferramentas do CSV por minuto do rtdmw (RTD do Profit), somente biblioteca padrão.

O Profit só grava o `.min` do dia depois do fechamento, mas o RTD entrega ao vivo os mesmos acumulados:
  QTT (quantidade total), NEG (negócios), AGRVOLC/AGRVOLV (volume agressor comprador/vendedor, sem RLP),
  AGRNEGC/AGRNEGV (negócios agressores comprador/vendedor).
A diferença entre leituras consecutivas do CSV (rotulada pelo minuto coberto: hora da leitura menos 1 s) equivale às colunas do `.min`:
  qty_vol, trades, buy_qty, sell_qty, buy_trd, sell_trd.

Formato do CSV (uma linha por minuto, o acumulado lido por último naquele minuto):
  HH:MM;HH:MM:SS;QTT;VOL;NEG;AGRVOLC;AGRVOLV;AGRNEGC;AGRNEGV     (linhas `RESET...` são ignoradas)

Uso:
  python3 rtd_minute_tools.py m1 <arquivo_min_CSV>                       # imprime o M1 derivado
  python3 rtd_minute_tools.py compare --asset WINZ26 --date 2026-11-25   # compara com o .min real do Profit
"""
from __future__ import annotations

import argparse
import math
import os
import struct
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

RTD_DIR = os.environ.get("MW_RTD_CSV_DIR", "/home/app/rtd-csv")
PROFIT_ASSETS = os.environ.get(
    "MW_PROFIT_ASSETS_DIR",
    "/home/app/profit-wine/prefix/drive_c/users/mt5/AppData/Roaming/Nelogica/Scalper/database/assets",
)

# Layout do .min (128 bytes por barra), igual ao de core/profit_statarb_engine.py
MIN_STRUCT = struct.Struct("<ddddddd" "QII" "dd" "QQ" "II" "16x")
assert MIN_STRUCT.size == 128
FIELDS = ("qty_vol", "trades", "buy_qty", "sell_qty", "buy_trd", "sell_trd")


def minute_of(label: str) -> int:
    return int(label[:2]) * 60 + int(label[3:5])


def _label_minus_one_second(hms: str) -> str:
    """HH:MM:SS -> HH:MM do instante um segundo antes (o minuto que a leitura acabou de cobrir)."""
    total = int(hms[:2]) * 3600 + int(hms[3:5]) * 60 + int(hms[6:8]) - 1
    total = max(total, 0)
    return "%02d:%02d" % (total // 3600, (total % 3600) // 60)


def read_rtd_minute_csv(path: str) -> List[Tuple[str, List[int]]]:
    """[(HH:MM do minuto COBERTO, [QTT, VOL, NEG, AGRVOLC, AGRVOLV, AGRNEGC, AGRNEGV])] na ordem do arquivo.

    A segunda coluna do CSV e a hora da leitura (acumulado ate aquele segundo). Uma leitura em 09:02:00 contem
    o que aconteceu ate 09:01:59, entao o minuto coberto e 09:01. Validado contra o export de ticks do Profit
    (25/11, WIN): sem esse ajuste a correlacao por barra e ~0,05; com ele passa de 0,99.
    """
    rows: List[Tuple[str, List[int]]] = []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            f = line.strip().split(";")
            if len(f) < 9 or f[0].startswith("RESET"):
                continue
            try:
                rows.append((_label_minus_one_second(f[1]), [int(float(x)) for x in f[2:9]]))
            except (ValueError, IndexError):
                continue
    return rows


def derive_m1(rows: List[Tuple[str, List[int]]]) -> Dict[str, dict]:
    """Deltas por minuto coberto. Leituras no mesmo minuto somam. `gap=True` se faltou minuto entre duas leituras
    (o delta junta varios minutos e fica no rotulo da ultima leitura)."""
    out: Dict[str, dict] = {}
    prev: Optional[Tuple[str, List[int]]] = None
    for label, v in rows:
        if prev is not None:
            pm, pv = prev
            if minute_of(label) >= minute_of(pm):
                d = {
                    "qty_vol": v[0] - pv[0],
                    "trades": v[2] - pv[2],
                    "buy_qty": v[3] - pv[3],
                    "sell_qty": v[4] - pv[4],
                    "buy_trd": v[5] - pv[5],
                    "sell_trd": v[6] - pv[6],
                }
                gap = minute_of(label) - minute_of(pm) > 1
                cur = out.get(label)
                if cur is None:
                    out[label] = dict(d, gap=gap)
                else:
                    for k in FIELDS:
                        cur[k] += d[k]
                    cur["gap"] = cur["gap"] or gap
        prev = (label, v)
    return out


def find_min_file(asset: str) -> Optional[str]:
    folder = os.path.join(PROFIT_ASSETS, asset + "_F_0")
    if not os.path.isdir(folder):
        return None
    for name in sorted(os.listdir(folder)):
        if name.endswith(".min") and "_0_1_1_1_1_0_" in name:
            return os.path.join(folder, name)
    return None


def read_min_day(path: str, day: str) -> Dict[str, dict]:
    """Barras M1 do .min do Profit para a data YYYY-MM-DD, indexadas por HH:MM."""
    epoch = datetime(1899, 12, 30)
    out: Dict[str, dict] = {}
    with open(path, "rb") as fh:
        data = fh.read()
    for i in range(len(data) // 128):
        rec = MIN_STRUCT.unpack_from(data, i * 128)
        dt, close = rec[0], rec[5]
        if not (40000.0 < dt < 60000.0) or close <= 0:
            continue
        when = epoch + timedelta(days=dt)
        when = (when + timedelta(seconds=30)).replace(second=0, microsecond=0)
        if when.strftime("%Y-%m-%d") != day:
            continue
        out[when.strftime("%H:%M")] = {
            "qty_vol": rec[7],
            "trades": rec[8],
            "buy_qty": rec[12],
            "sell_qty": rec[13],
            "buy_trd": rec[14],
            "sell_trd": rec[15],
            "open": rec[2], "high": rec[3], "low": rec[4], "close": rec[5],
        }
    return out


def pearson(a: List[float], b: List[float]) -> Optional[float]:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def compare(asset: str, day: str, csv_path: Optional[str] = None, min_path: Optional[str] = None) -> str:
    dd, mm, yy = day[8:10], day[5:7], day[0:4]
    csv_path = csv_path or os.path.join(RTD_DIR, f"{asset}_min_{dd}_{mm}_{yy}.csv")
    min_path = min_path or find_min_file(asset)
    lines = [f"== {asset} {day}: RTD (rtdmw) x .min do Profit =="]
    if not os.path.exists(csv_path):
        return "\n".join(lines + [f"sem CSV do rtdmw: {csv_path}"])
    if not min_path or not os.path.exists(min_path):
        return "\n".join(lines + [f"sem .min do Profit para {asset}"])
    rtd = derive_m1(read_rtd_minute_csv(csv_path))
    real = read_min_day(min_path, day)
    if not real:
        return "\n".join(lines + ["o .min ainda nao tem barras desse dia (o Profit grava depois do fechamento)"])
    common = sorted(m for m in rtd if m in real)
    clean = [m for m in common if not rtd[m]["gap"]]
    lines.append(f"minutos: rtd={len(rtd)} .min={len(real)} em comum={len(common)} sem lacuna={len(clean)}")
    for k in FIELDS:
        xs = [float(rtd[m][k]) for m in clean]
        ys = [float(real[m][k]) for m in clean]
        sx, sy = sum(xs), sum(ys)
        exact = sum(1 for x, y in zip(xs, ys) if abs(x - y) <= max(1.0, 0.01 * abs(y)))
        corr = pearson(xs, ys)
        lines.append(
            "  %-9s RTD=%12d  .min=%12d  RTD/.min=%s  corr=%s  barras iguais(+-1%%)=%d/%d"
            % (k, sx, sy, ("%.4f" % (sx / sy)) if sy else "n/a", ("%.4f" % corr) if corr is not None else "n/a", exact, len(clean))
        )
    delta_rtd = [rtd[m]["buy_qty"] - rtd[m]["sell_qty"] for m in clean]
    delta_min = [real[m]["buy_qty"] - real[m]["sell_qty"] for m in clean]
    c = pearson([float(x) for x in delta_rtd], [float(x) for x in delta_min])
    lines.append("  delta (buy_qty - sell_qty) por barra: corr=%s" % (("%.4f" % c) if c is not None else "n/a"))
    return "\n".join(lines)


def aggregate_trade_export(path: str) -> Dict[str, dict]:
    """Agrega o export de ticks do Profit (Exportacao de Dados Historicos, intervalo Trade) por minuto.
    Colunas: Ativo;Data;Hora;Comprador;Preco;Quantidade;Vendedor;Tipo (latin-1, milhar com ponto).
    Tipo Comprador/Vendedor e a agressao; RLP, Leilao e Direto entram so em qty_vol e trades."""
    per: Dict[str, dict] = {}
    with open(path, encoding="latin-1") as fh:
        next(fh)
        for line in fh:
            f = line.rstrip("\n").split(";")
            if len(f) < 8:
                continue
            q = int(f[5].replace(".", ""))
            d = per.setdefault(f[2][:5], dict.fromkeys(FIELDS, 0))
            d["qty_vol"] += q
            d["trades"] += 1
            if f[7] == "Comprador":
                d["buy_qty"] += q
                d["buy_trd"] += 1
            elif f[7] == "Vendedor":
                d["sell_qty"] += q
                d["sell_trd"] += 1
    return per


def compare_with_trade_export(asset: str, csv_path: str, trade_path: str) -> str:
    rtd = derive_m1(read_rtd_minute_csv(csv_path))
    real = aggregate_trade_export(trade_path)
    clean = sorted(m for m in rtd if m in real and not rtd[m]["gap"])
    lines = [f"== {asset}: RTD (rtdmw) x export de ticks do Profit ==",
             f"minutos: rtd={len(rtd)} export={len(real)} comparaveis(sem lacuna)={len(clean)}"]
    for k in FIELDS:
        xs = [float(rtd[m][k]) for m in clean]
        ys = [float(real[m][k]) for m in clean]
        sx, sy = sum(xs), sum(ys)
        exact = sum(1 for x, y in zip(xs, ys) if abs(x - y) <= max(1.0, 0.01 * abs(y)))
        corr = pearson(xs, ys)
        lines.append("  %-9s RTD=%11d export=%11d razao=%s corr=%s barras iguais(+-1%%)=%d/%d" % (
            k, sx, sy, ("%.4f" % (sx / sy)) if sy else "n/a", ("%.4f" % corr) if corr is not None else "n/a", exact, len(clean)))
    c = pearson([float(rtd[m]["buy_qty"] - rtd[m]["sell_qty"]) for m in clean],
                [float(real[m]["buy_qty"] - real[m]["sell_qty"]) for m in clean])
    lines.append("  delta (buy_qty - sell_qty) por barra: corr=%s" % (("%.4f" % c) if c is not None else "n/a"))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("m1")
    p1.add_argument("csv")
    p2 = sub.add_parser("compare")
    p2.add_argument("--asset", action="append")
    p2.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p2.add_argument("--csv")
    p2.add_argument("--min")
    p3 = sub.add_parser("compare-export", help="compara o CSV do rtdmw com o export de ticks (Trade) do Profit")
    p3.add_argument("--asset", required=True)
    p3.add_argument("--csv", required=True)
    p3.add_argument("--trade", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "compare-export":
        print(compare_with_trade_export(args.asset, args.csv, args.trade))
        return 0
    if args.cmd == "m1":
        m1 = derive_m1(read_rtd_minute_csv(args.csv))
        print("minuto;qty_vol;trades;buy_qty;sell_qty;buy_trd;sell_trd;gap")
        for label in sorted(m1):
            r = m1[label]
            print(";".join([label] + [str(r[k]) for k in FIELDS] + [str(int(r["gap"]))]))
        return 0
    for asset in (args.asset or ["WINZ26", "WDOZ26"]):
        print(compare(asset, args.date, args.csv, args.min))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
