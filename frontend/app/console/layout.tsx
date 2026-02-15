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
    <div className="min-h-screen bg-background">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-background">
        <div className="mx-auto max-w-7xl px-8 flex items-center justify-between h-14">
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

      <main className="pt-8">
        {children}
      </main>
    </div>
  );
}
