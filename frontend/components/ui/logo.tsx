import Link from "next/link";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`font-mono text-xs uppercase tracking-widest text-foreground ${className}`}
    >
      AdApt
    </Link>
  );
}
