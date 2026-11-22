# -*- coding: utf-8 -*-
"""Roda as variantes de componentes (flows2) no MESMO harness da ablação (ablation.main), sem alterar ablation.py.
Uso: python research/flow_ablation/ablation2.py <VARIANTE>"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import flows2  # noqa: F401,E402  (substitui flows.make)
import ablation  # noqa: E402

if __name__ == "__main__":
    ablation.main(sys.argv[1], skip_addon="--skip-addon" in sys.argv)
