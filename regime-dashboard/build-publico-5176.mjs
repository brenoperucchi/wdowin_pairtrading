// Gera a versão pública completa (modo 5176 — Robôs Magic Walls) em dist-publico-5176/.
// Usa a mesma configuração do modo development (.env.development) e define:
//   VITE_API_BASE=""          → API em caminhos relativos (/api/...), servidos por scripts/painel_publico.py --mode 5176
//   VITE_FORCE_WALLS_FLOW="1" → modo Walls & Fluxo (5176) sem depender da porta
//   VITE_MANUAL_ONLY="0"      → painel completo (Cockpit, Robôs, Carteira 5176, Raio-X, Stat-Arb)
// Uso: node build-publico-5176.mjs
import { build, loadEnv } from "vite";

process.env.NODE_ENV = "development";
const env = loadEnv("development", process.cwd(), "VITE_");
for (const [k, v] of Object.entries(env)) process.env[k] = v;
process.env.VITE_API_BASE = "";
process.env.VITE_FORCE_WALLS_FLOW = "1";
process.env.VITE_MANUAL_ONLY = "0";

await build({ mode: "development", build: { outDir: "dist-publico-5176", emptyOutDir: true, chunkSizeWarningLimit: 4000 }, logLevel: "warn" });
console.log("versão pública 5176 (roboswalls) gerada em dist-publico-5176/");
