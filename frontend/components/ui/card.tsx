import { type HTMLAttributes } from "react";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`border-t border-border pt-6 ${className}`}
      {...props}
    />
  );
}
