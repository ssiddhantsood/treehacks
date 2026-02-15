const steps = [
  {
    title: "Upload your base creative",
    description:
      "Drop in a single video ad. ADAPT analyzes the composition, subjects, and scene structure automatically.",
  },
  {
    title: "Define your audiences",
    description:
      "Set target demographics and regions — or let our AI cluster your audience profiles for you.",
  },
  {
    title: "Ship localized variants",
    description:
      "AI regenerates backgrounds and contextual elements per locale. NYC gets the skyline, Miami gets the coast.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="border-t border-border">
      <div className="mx-auto max-w-7xl px-6 py-24">
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          How it works
        </h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
          Three steps from a single creative to dozens of localized variants.
        </p>
        <div className="mt-14 grid gap-10 sm:grid-cols-3 sm:gap-16">
          {steps.map((step) => (
            <div key={step.title}>
              <h3 className="text-base font-semibold text-foreground">
                {step.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
