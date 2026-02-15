"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { clearToken } from "@/lib/auth";

export default function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();

  const handleSignOut = () => {
    clearToken();
    router.push("/");
  };

  return (
    <div className="h-screen w-full overflow-hidden bg-background flex flex-col">
      <nav className="shrink-0 z-50 bg-background">
        <div className="w-full px-8 flex items-center justify-between h-14">
          <Link
            href="/"
            className="cursor-pointer text-sm font-medium tracking-widest uppercase hover:opacity-70 transition-opacity"
          >
            ADAPT
          </Link>
          <button
            onClick={handleSignOut}
            className="cursor-pointer font-mono text-[11px] uppercase tracking-widest text-muted hover:text-foreground transition-colors"
          >
            Sign out
          </button>
        </div>
      </nav>

      <main className="flex-1 min-h-0 overflow-hidden">
        {children}
      </main>
    </div>
  );
}
