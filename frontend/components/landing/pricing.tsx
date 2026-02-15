import Link from "next/link";

const tiers = [
  {
    name: "Free",
    price: "$0",
    period: "/ month",
    features: ["5 variants / month", "720p export", "Community support"],
  },
  {
    name: "Pro",
    price: "$49",
    period: "/ month",
    features: [
      "Unlimited variants",
      "4K export",
      "Priority support",
      "Custom demographics",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    features: [
      "Dedicated infrastructure",
      "SSO & SAML",
      "SLA guarantee",
      "Custom integrations",
    ],
  },
];

export function Pricing() {
  return (
    <section id="pricing" className="border-t border-border">
      <div className="mx-auto max-w-7xl px-6 py-24">
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          Pricing
        </h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
          Start free. Scale when you&apos;re ready.
        </p>
        <div className="mt-14 grid sm:grid-cols-3">
          {tiers.map((tier, i) => (
            <div
              key={tier.name}
              className={`py-10 ${i > 0 ? "sm:pl-10" : ""} ${i < tiers.length - 1 ? "border-b border-border sm:border-b-0 sm:border-r sm:pr-10" : ""}`}
            >
              <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
                {tier.name}
              </span>
              <div className="mt-4 flex items-baseline gap-1">
                <span className="text-4xl font-bold text-foreground">
                  {tier.price}
                </span>
                {tier.period && (
                  <span className="text-sm text-muted">{tier.period}</span>
                )}
              </div>
              <ul className="mt-8 flex flex-col gap-3">
                {tier.features.map((f) => (
                  <li key={f} className="text-sm text-muted">
                    {f}
                  </li>
                ))}
              </ul>
              <div className="mt-10">
                <Link
                  href="/login"
                  className="font-mono text-[11px] uppercase tracking-widest text-muted transition-colors hover:text-foreground"
                >
                  Get started →
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
