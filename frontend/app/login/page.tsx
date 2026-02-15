"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/ui/logo";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { setToken } from "@/lib/auth";
import Link from "next/link";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const authFn = mode === "register" ? api.auth.register : api.auth.login;
      const res = await authFn(email, password);
      setToken(res.token);
      router.push("/console");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="mb-12 flex justify-center">
          <Logo />
        </div>
        <div className="border-t border-border pt-8">
          <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
            {mode === "login" ? "Sign in" : "Create account"}
          </span>
          <p className="mt-3 text-sm text-muted">
            {mode === "login"
              ? "Enter your credentials to access the console."
              : "Create an account to start generating ads."}
          </p>
          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-6">
            <Input
              label="Email"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <Input
              label="Password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {error && (
              <p className="text-sm text-red-400">{error}</p>
            )}
            <Button type="submit" disabled={loading} className="mt-2 w-full">
              {loading
                ? "Loading..."
                : mode === "login"
                  ? "Sign in"
                  : "Create account"}
            </Button>
          </form>
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="font-mono text-[11px] uppercase tracking-widest text-muted transition-colors hover:text-foreground cursor-pointer"
            >
              {mode === "login"
                ? "Create an account →"
                : "Sign in instead →"}
            </button>
          </div>
        </div>
        <div className="mt-12 text-center">
          <Link
            href="/"
            className="font-mono text-[11px] uppercase tracking-widest text-muted transition-colors hover:text-foreground"
          >
            ← Back
          </Link>
        </div>
      </div>
    </div>
  );
}
