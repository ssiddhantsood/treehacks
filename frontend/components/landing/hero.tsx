import Link from "next/link";
import { Button } from "@/components/ui/button";

const transformations = [
  { from: "Base Creative", to: "New York", scene: "Urban skyline" },
  { from: "Base Creative", to: "Miami", scene: "Beachfront" },
  { from: "Base Creative", to: "Denver", scene: "Mountain trail" },
];

export function Hero() {
  return (
    <section className="mx-auto flex min-h-screen max-w-7xl flex-col justify-center px-6 pt-14">
      <div className="max-w-3xl">
        <p className="text-sm uppercase tracking-wide text-muted">
          AI-Powered Ad Localization
        </p>
        <h1 className="mt-4 text-5xl font-bold leading-tight tracking-tight text-foreground sm:text-6xl">
          Your ad. <br />
          Every audience. <br />
          One upload.
        </h1>
        <p className="mt-6 max-w-lg text-lg leading-relaxed text-muted">
          Transform a single video ad into dozens of localized variants. 
          AI adjusts backgrounds, scenery, and context for any market.
        </p>
        <div className="mt-10 flex items-center gap-4">
          <Link href="/login">
            <Button size="lg">Start for free</Button>
          </Link>
          <Link
            href="#features"
            className="text-sm text-muted transition-colors hover:text-foreground"
          >
            See how it works →
          </Link>
        </div>
      </div>

      <div className="mt-20 grid gap-6 sm:grid-cols-3">
        {transformations.map((t, i) => (
          <div key={i} className="border-t border-border pt-6">
            <div className="aspect-video bg-foreground/5 border border-border" />
            <div className="mt-4 flex items-center justify-between">
              <span className="text-sm font-medium text-foreground">{t.to}</span>
              <span className="text-xs text-muted">{t.scene}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
