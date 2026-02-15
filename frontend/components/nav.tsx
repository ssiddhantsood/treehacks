import Link from "next/link";
import { Logo } from "@/components/ui/logo";

export function Nav() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <Logo />
        <nav className="flex items-center gap-8">
          <Link
            href="/#how-it-works"
            className="font-mono text-[11px] uppercase tracking-widest text-muted transition-colors hover:text-foreground"
          >
            How it works
          </Link>
          <Link
            href="/#pricing"
            className="font-mono text-[11px] uppercase tracking-widest text-muted transition-colors hover:text-foreground"
          >
            Pricing
          </Link>
          <Link
            href="/login"
            className="font-mono text-[11px] uppercase tracking-widest text-foreground transition-colors hover:text-white"
          >
            Get started →
          </Link>
        </nav>
      </div>
    </header>
  );
}
