import { type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Input({ label, className = "", id, ...props }: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="flex flex-col gap-2">
      {label && (
        <label
          htmlFor={inputId}
          className="font-mono text-[10px] uppercase tracking-widest text-muted"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full border-b border-border bg-transparent px-0 py-2 text-sm text-foreground placeholder:text-muted/50 outline-none transition-colors focus:border-foreground ${className}`}
        {...props}
      />
    </div>
  );
}
