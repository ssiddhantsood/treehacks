import Link from "next/link";
import { Logo } from "@/components/ui/logo";

export function Nav() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <Link href="/">
          <Logo />
        </Link>
        <nav className="flex items-center gap-8">
          <Link
            href="/#features"
            className="text-sm text-muted transition-colors hover:text-foreground"
          >
            Features
          </Link>
          <Link
            href="/#pricing"
            className="text-sm text-muted transition-colors hover:text-foreground"
          >
            Pricing
          </Link>
          <Link
            href="/login"
            className="bg-foreground px-4 py-2 text-sm text-background transition-colors hover:bg-foreground/80"
          >
            Get started
          </Link>
        </nav>
      </div>
    </header>
  );
}
