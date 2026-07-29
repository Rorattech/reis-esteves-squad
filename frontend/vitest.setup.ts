import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

// @testing-library/react só registra a limpeza automática entre testes via
// um `afterEach` global — como vitest.config.ts roda com `globals: false`
// (imports explícitos em cada teste, sem globais ambientes), isso nunca
// acontece sozinho: sem esta chamada, o DOM de um teste vaza para o
// próximo (múltiplos elementos duplicados, mocks de estado obsoletos).
afterEach(() => {
  cleanup();
});
