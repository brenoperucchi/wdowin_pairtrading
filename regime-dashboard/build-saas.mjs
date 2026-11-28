// Gera a versão SaaS Cloud em dist-saas/ (para Cloudflare Pages).
// Ativa autenticação JWT + Sessão Única + Termos Clickwrap + Watermark Forense (VITE_SAAS_AUTH=1).
// Uso: node build-saas.mjs
import { build, loadEnv } from "vite";

process.env.NODE_ENV = "production";
const env = loadEnv("production", process.cwd(), "VITE_");
for (const [k, v] of Object.entries(env)) process.env[k] = v;
if (process.env.VITE_API_BASE === undefined) {
    process.env.VITE_API_BASE = "";
}
process.env.VITE_SAAS_AUTH = "1";
process.env.VITE_FORCE_WALLS_FLOW = "1";
process.env.VITE_MANUAL_ONLY = "1";

await build({
    mode: "production",
    // base absoluta: as telas têm caminho próprio (/admin/marketing...), então os assets não podem ser relativos.
    // Se o app passar a morar sob um prefixo (ex.: "/app/"), é só mudar aqui; src/routes.js lê o mesmo valor.
    base: "/",
    build: { outDir: "dist-saas", emptyOutDir: true, chunkSizeWarningLimit: 4000 },
    logLevel: "warn",
});
console.log("versão SaaS Cloud gerada em dist-saas/");
