// Gera a versão pública do painel 5176 (link do túnel) em dist-publico/.
// Usa a mesma configuração do modo development (.env.development, que tem o Firebase) e só acrescenta:
//   VITE_API_BASE=""          → API em caminhos relativos (/api/...), servidos por scripts/painel_publico.py
//   VITE_FORCE_WALLS_FLOW="1" → modo Walls & Fluxo (5176) sem depender da porta
// Uso: node build-publico.mjs
import { build, loadEnv } from "vite";

process.env.NODE_ENV = "development"; // mantém o caminho de leitura via API (o build de produção lê do Firebase)
const env = loadEnv("development", process.cwd(), "VITE_");
for (const [k, v] of Object.entries(env)) process.env[k] = v;
process.env.VITE_API_BASE = "";
process.env.VITE_FORCE_WALLS_FLOW = "1";
process.env.VITE_MANUAL_ONLY = "1";

await build({ mode: "development", build: { outDir: "dist-publico", emptyOutDir: true, chunkSizeWarningLimit: 4000 }, logLevel: "warn" });
console.log("versão pública gerada em dist-publico/");
