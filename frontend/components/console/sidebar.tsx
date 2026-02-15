"use client";

import { usePathname, useRouter } from "next/navigation";
import { Logo } from "@/components/ui/logo";
import { clearToken } from "@/lib/auth";

const links = [
  { href: "/console", label: "Campaigns" },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <aside className="flex h-screen w-52 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex h-14 items-center px-6">
        <Logo />
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 px-4 py-6">
        {links.map((link) => {
          const active = pathname === link.href;
          return (
            <a
              key={link.href}
              href={link.href}
              className={`px-2 py-1.5 font-mono text-[11px] uppercase tracking-widest transition-colors ${
                active ? "text-foreground" : "text-muted hover:text-foreground"
              }`}
            >
              {link.label}
            </a>
          );
        })}
      </nav>
      <div className="border-t border-border px-4 py-4">
        <button
          type="button"
          onClick={() => {
            clearToken();
            router.push("/login");
          }}
          className="px-2 py-1.5 font-mono text-[11px] uppercase tracking-widest text-muted transition-colors hover:text-foreground cursor-pointer"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
