interface BadgeProps {
  children: React.ReactNode;
  className?: string;
}

export function Badge({ children, className = "" }: BadgeProps) {
  return (
    <span
      className={`font-mono text-[10px] uppercase tracking-widest text-muted ${className}`}
    >
      {children}
    </span>
  );
}
