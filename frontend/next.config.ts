import type { NextConfig } from "next";

/**
 * `output: "standalone"` é um modo de saída para SELF-HOST (imagem Docker
 * enxuta com o server do Next embutido). Na Netlify o build é consumido pelo
 * adapter do Next runtime, que espera o output padrão — ver
 * docs/adr/0004-deploy-hostinger-netlify.md.
 *
 * Fica atrás de uma flag em vez de ser removido para que voltar a hospedar o
 * frontend em container continue sendo um `BUILD_TARGET=docker npm run build`,
 * sem precisar redescobrir esta configuração.
 */
const nextConfig: NextConfig = {
  ...(process.env.BUILD_TARGET === "docker" ? { output: "standalone" as const } : {}),
};

export default nextConfig;
