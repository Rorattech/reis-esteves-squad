"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/cases", label: "Casos" },
  { href: "/pesquisa", label: "Pesquisa jurídica" },
  { href: "/revisoes", label: "Revisões pendentes" },
  { href: "/configuracoes", label: "Configurações" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-60 flex-shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="px-4 py-5">
        <p className="text-sm font-semibold text-slate-900">Squad Digital</p>
        <p className="text-xs text-slate-500">Reis Esteves Advocacia</p>
      </div>
      <nav className="flex-1 space-y-1 px-2">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-md px-3 py-2 text-sm font-medium ${
                active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
