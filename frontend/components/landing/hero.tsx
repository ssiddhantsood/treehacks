import Link from "next/link";
import { Button } from "@/components/ui/button";

function MockConsole() {
  return (
    <div className="border border-border bg-surface shadow-sm">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <div className="h-1.5 w-1.5 rounded-full bg-border" />
        <div className="h-1.5 w-1.5 rounded-full bg-border" />
        <div className="h-1.5 w-1.5 rounded-full bg-border" />
        <span className="ml-3 font-mono text-[10px] uppercase tracking-widest text-muted">
          adapt — console
        </span>
      </div>
      <div className="p-5">
        <div className="flex items-center gap-3">
          <div className="h-2 w-2 rounded-full bg-emerald-500" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
            3 variants generated
          </span>
        </div>
        <div className="mt-5 flex flex-col gap-0">
          {[
            { region: "New York", status: "Deployed", scene: "Urban skyline" },
            { region: "Miami", status: "Deployed", scene: "Beachfront" },
            { region: "Denver", status: "Processing", scene: "Mountain trail" },
          ].map((row) => (
            <div
              key={row.region}
              className="grid grid-cols-3 gap-4 border-t border-border py-3"
            >
              <span className="text-xs font-medium text-foreground">
                {row.region}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                {row.scene}
              </span>
              <span
                className={`text-right font-mono text-[10px] uppercase tracking-widest ${row.status === "Deployed" ? "text-emerald-600" : "text-amber-600"}`}
              >
                {row.status}
              </span>
            </div>
          ))}
          <div className="border-t border-border" />
        </div>
        <div className="mt-5 grid grid-cols-3 gap-3">
          {["NYC — 16:9", "MIA — 16:9", "DEN — 16:9"].map((label) => (
            <div key={label} className="border border-border bg-background p-3">
              <div className="mb-2 aspect-video bg-border/50" />
              <span className="font-mono text-[9px] uppercase tracking-widest text-muted">
                {label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Hero() {
  return (
    <section className="mx-auto flex min-h-screen max-w-7xl flex-col justify-center px-6 pt-14">
      <div className="grid items-center gap-16 lg:grid-cols-2">
        <div>
          <h1 className="text-4xl font-bold leading-tight tracking-tight text-foreground sm:text-5xl">
            One ad. Every market.
            <br />
            <span className="text-muted">AI-localized in seconds.</span>
          </h1>
          <p className="mt-6 max-w-md text-sm leading-relaxed text-muted">
            AdApt transforms a single base creative into hyper-localized ad
            variants — adjusting backgrounds, scenery, and context to match any
            demographic, anywhere.
          </p>
          <div className="mt-8 flex items-center gap-4">
            <Link href="/login">
              <Button>Start creating</Button>
            </Link>
            <Link
              href="#how-it-works"
              className="font-mono text-[11px] uppercase tracking-widest text-muted transition-colors hover:text-foreground"
            >
              Learn more ↓
            </Link>
          </div>
        </div>
        <div className="hidden lg:block">
          <MockConsole />
        </div>
      </div>
    </section>
  );
}
