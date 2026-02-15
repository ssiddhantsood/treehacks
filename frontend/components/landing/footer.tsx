import { Logo } from "@/components/ui/logo";

export function Footer() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6">
        <Logo />
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
          © {new Date().getFullYear()} AdApt
        </span>
      </div>
    </footer>
  );
}
