import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Squad Digital — Reis Esteves Advocacia",
  description: "Copiloto de IA para análise de casos de Direito Digital",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
