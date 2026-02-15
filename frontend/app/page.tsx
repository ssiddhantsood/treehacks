"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Pricing } from "@/components/landing/pricing";
import { Input } from "@/components/ui/input";
import { setToken } from "@/lib/auth";

const ads = [
  { title: "Doritos", market: "SF", year: "2026", video: "/ads/doritos_sb.webm" },
  { title: "Nike", market: "NYC", year: "2026", video: "/ads/nike_sb.webm" },
  { title: "Pepsi", market: "Miami", year: "2026", video: "/ads/pepsi_sb.webm" },
  { title: "OpenAI", market: "SF", year: "2026", video: "/ads/openai_sb.webm" },
  { title: "Taco Bell", market: "Austin", year: "2026", video: "/ads/taco_bell_sb.webm" },
  { title: "Nike", market: "London", year: "2026", video: "/ads/nike_sb.webm" },
  { title: "Pepsi", market: "Tokyo", year: "2026", video: "/ads/pepsi_sb.webm" },
  { title: "Doritos", market: "Berlin", year: "2026", video: "/ads/doritos_sb.webm" },
  { title: "OpenAI", market: "Dublin", year: "2026", video: "/ads/openai_sb.webm" },
  { title: "Taco Bell", market: "Seoul", year: "2026", video: "/ads/taco_bell_sb.webm" },
];

const CARD_WIDTH = 600;
const X_START = 50;   
const X_STEP = -16;
const Y_START = 0;
const Y_STEP = 8;
const BASE_Z = 336;

function getCardStyle(index: number, scrollOffset: number, isHovered: boolean, isScrolling: boolean) {
  const N = ads.length;
  let relativePos = (index + scrollOffset) % N;
  if (relativePos < 0) relativePos += N;
  
  const xOffset = X_START + relativePos * X_STEP;
  const yOffset = Y_START + relativePos * Y_STEP;
  
  const zIndex = BASE_Z + Math.floor(relativePos); 

  return {
    position: "absolute" as const,
    left: "50%",
    top: `calc(30% + ${yOffset}rem)`, 
    width: `${CARD_WIDTH}px`,
    aspectRatio: "16 / 10",
    zIndex,
    transform: `translateX(calc(-50% + ${xOffset}rem)) translateY(${isHovered ? "calc(-50% - 1.5rem)" : "-50%"}) skewY(10deg) scale(${isHovered ? 1.04 : 1}) translateZ(0)`,
    willChange: "transform" as const,
    pointerEvents: isScrolling ? "none" as const : "auto" as const,
    cursor: "pointer",
    backgroundColor: "transparent",
    transition: isHovered ? "transform 0.4s cubic-bezier(0.4, 0, 0.2, 1)" : "none",
  };
}

export default function Home() {
  const router = useRouter();
  const [hoveredAd, setHoveredAd] = useState<number | null>(null);
  const [scrollOffset, setScrollOffset] = useState(0); 
  const [isScrolling, setIsScrolling] = useState(false);
  const [hasLeftHero, setHasLeftHero] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [loginMode, setLoginMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const scrollAccum = useRef(0);
  const scrollTimeout = useRef<NodeJS.Timeout | null>(null);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    setLoginLoading(true);
    try {
      if (email === "demo@adapt.com" && password === "password") {
        setToken("fake-jwt-token");
        router.push("/console");
      } else {
        setLoginError("Invalid email or password");
      }
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoginLoading(false);
    }
  };

  const openLogin = () => setShowLogin(true);
  const closeLogin = () => {
    setShowLogin(false);
    setLoginError("");
    setEmail("");
    setPassword("");
  };

  useEffect(() => {
    const timer = setTimeout(() => {
        if (window.scrollY > window.innerHeight / 2) {
            setHasLeftHero(true);
        }
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      if (!hasLeftHero) {
         e.preventDefault();
         
         if (!isScrolling) setIsScrolling(true);
         if (scrollTimeout.current) clearTimeout(scrollTimeout.current);
         
         scrollTimeout.current = setTimeout(() => {
           setIsScrolling(false);
         }, 150);

         scrollAccum.current += e.deltaY * 0.005; 
         setScrollOffset(scrollAccum.current);
         return;
      }
      
      if (window.scrollY <= window.innerHeight + 50 && e.deltaY < 0) {
          e.preventDefault();
          window.scrollTo({ top: window.innerHeight, behavior: "auto" });
      }
    };

    window.addEventListener("wheel", handleWheel, { passive: false });
    return () => window.removeEventListener("wheel", handleWheel);
  }, [isScrolling, hasLeftHero]);

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      setHasLeftHero(true);
      el.scrollIntoView({ behavior: "smooth" });
    }
  };

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => {
        setHasLeftHero(false);
    }, 500);
  };

  return (
    <div className="min-h-screen bg-background overflow-x-hidden relative">
      {/* --- login modal --- */}
      {showLogin && (
        <div className="fixed inset-0 z-99999 bg-background/95 backdrop-blur-sm flex items-center justify-center">
          <div className="animate-modal-in w-full max-w-sm px-6">
            <button
              onClick={closeLogin}
              className="absolute top-6 right-8 text-muted hover:text-foreground transition-colors cursor-pointer"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M4 4l12 12M16 4L4 16" />
              </svg>
            </button>

            <div className="flex flex-col items-center text-center mb-10">
              <span className="text-sm font-medium tracking-widest uppercase">ADAPT</span>
              <h2 className="mt-6 text-2xl font-bold tracking-tight">
                {loginMode === "login" ? "Welcome back" : "Create your account"}
              </h2>
              <p className="mt-3 text-sm text-muted max-w-xs">
                {loginMode === "login"
                  ? "Sign in to access your console and campaigns."
                  : "Get started with ADAPT to localize your ads globally."}
              </p>
            </div>

            <form onSubmit={handleLoginSubmit} className="flex flex-col gap-6">
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
              {loginError && (
                <p className="text-sm text-red-400">{loginError}</p>
              )}
              <button
                type="submit"
                disabled={loginLoading}
                className="cursor-pointer mt-2 w-full px-8 py-3 bg-[#1c1c1c] text-white rounded-full text-sm font-medium hover:bg-black transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loginLoading
                  ? "Loading..."
                  : loginMode === "login"
                    ? "Sign in"
                    : "Create account"}
              </button>
            </form>

            <div className="mt-8 text-center">
              <button
                type="button"
                onClick={() => setLoginMode(loginMode === "login" ? "register" : "login")}
                className="font-mono text-[11px] uppercase tracking-widest text-muted transition-colors hover:text-foreground cursor-pointer"
              >
                {loginMode === "login"
                  ? "Create an account →"
                  : "Sign in instead →"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* --- header --- */}
      <section className="relative h-screen w-full overflow-hidden">
        <nav className="absolute top-0 left-0 right-0 z-50 flex items-center justify-between px-8 py-6 pointer-events-none">
          <button 
            onClick={scrollToTop} 
            className="text-sm font-medium tracking-widest uppercase text-foreground pointer-events-auto hover:opacity-70 transition-opacity"
          >
            ADAPT
          </button>
        </nav>
        
        <div className="min-h-screen flex items-start justify-start pt-20 sm:pt-32 absolute inset-0 px-8 sm:px-12 pointer-events-none" style={{ zIndex: 100 }}>
          <div className="flex flex-col items-start gap-5 sm:gap-6 text-left max-w-4xl pointer-events-none">
            <div className="pointer-events-none" style={{ zIndex: 10000, position: "relative" }}>
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-semibold leading-tight select-none">
                Localized ads for
                <br />
                every market.
              </h1>
            </div>

            <div className="flex items-center gap-3" style={{ zIndex: 10000, position: "relative" }}>
              <button
                onClick={openLogin}
                className="cursor-pointer px-4 py-2 sm:px-6 sm:py-2.5 bg-[#1c1c1c] text-white rounded-full text-[12px] sm:text-sm font-medium hover:bg-[#000000] transition-colors duration-200 pointer-events-auto"
              >
                Get Started
              </button>
              <button
                onClick={openLogin}
                className="cursor-pointer px-4 py-2 sm:px-6 sm:py-2.5 bg-transparent text-[#1c1c1c] border border-border rounded-full text-[12px] sm:text-sm font-medium hover:bg-[#f5f5f5] transition-colors duration-200 pointer-events-auto"
              >
                Login
              </button>
              <button
                onClick={() => scrollToSection('about')}
                className="cursor-pointer px-4 py-2 sm:px-6 sm:py-2.5 bg-transparent text-[#1c1c1c] border border-border rounded-full text-[12px] sm:text-sm font-medium hover:bg-[#f5f5f5] transition-colors duration-200 pointer-events-auto"
              >
                Learn more
              </button>
            </div>
          </div>
        </div>

        <div className="absolute bottom-6 right-8 z-40 flex items-center gap-6">
          <Link href="#" className="text-xs text-muted hover:text-foreground transition-colors">Privacy</Link>
          <Link href="#" className="text-xs text-muted hover:text-foreground transition-colors">Terms</Link>
        </div>

        <div className={`absolute inset-0 ${isScrolling ? "pointer-events-none" : ""}`}>
          {ads.map((ad, i) => {
            const isHovered = hoveredAd === i;
            const style = getCardStyle(i, scrollOffset, isHovered, isScrolling);

            return (
              <div
                key={i}
                style={style}
                onMouseEnter={() => setHoveredAd(i)}
                onMouseLeave={() => setHoveredAd(null)}
              >
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    padding: "1rem",
                    display: "flex",
                    flexDirection: "column",
                    position: "relative",
                  }}
                >
                  <div
                    style={{
                      fontFamily: "monospace",
                      fontSize: "0.5rem",
                      color: "rgb(102, 102, 102)",
                      marginBottom: "0.5rem",
                      minHeight: "0.75rem",
                      opacity: isHovered ? 1 : 0,
                      transition: "opacity 0.3s ease",
                    }}
                  >
                    {ad.title} · {ad.market}
                  </div>

                  <div
                    className="relative w-full h-full rounded-lg border border-border overflow-hidden flex items-center justify-center"
                    style={{
                      backgroundColor: i % 3 === 0
                        ? "rgba(200, 200, 200, 0.4)"
                        : i % 3 === 1
                          ? "rgba(40, 40, 40, 0.75)"
                          : "rgba(200, 200, 200, 0.25)",
                      backdropFilter: "blur(10px)",
                    }}
                  >
                    {ad.video && (
                      <video
                        src={ad.video}
                        autoPlay
                        loop
                        muted
                        playsInline
                        className="absolute inset-0 w-full h-full object-cover"
                      />
                    )}

                    {ad.video && <div className="absolute inset-0 bg-black/10" />}
                    

                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* --- about --- */}
      <section id="about" className="border-t border-border bg-background relative z-10">
        <nav className="flex items-center justify-between px-8 py-6">
          <button 
            onClick={scrollToTop} 
            className="text-sm font-medium tracking-widest uppercase text-foreground hover:opacity-70 transition-opacity"
          >
            ADAPT
          </button>
          <div className="flex items-center gap-6">
            <button onClick={() => scrollToSection('about')} className="text-xs text-muted hover:text-foreground transition-colors uppercase tracking-wider">
              About
            </button>
            <button onClick={() => scrollToSection('pricing')} className="text-xs text-muted hover:text-foreground transition-colors uppercase tracking-wider">
              Pricing
            </button>
            <button onClick={openLogin} className="cursor-pointer text-xs text-muted hover:text-foreground transition-colors uppercase tracking-wider">
              Login
            </button>
          </div>
        </nav>

        <div className="mx-auto max-w-7xl px-8 pt-10 pb-24">
          <h2 className="text-2xl font-bold tracking-tight">How it works</h2>
          <p className="mt-3 text-sm text-muted max-w-lg">
            Three steps from a single asset to hundreds of localized variants.
          </p>

          <div className="mt-16 grid lg:grid-cols-3 gap-0">
            {[
              {
                step: "01",
                title: "Upload",
                desc: "Drop a single master creative — video, image, or layered design file.",
              },
              {
                step: "02",
                title: "Configure",
                desc: "Choose target markets, demographics, and localization depth. Our AI handles the rest.",
              },
              {
                step: "03",
                title: "Export",
                desc: "Download hundreds of production-ready variants, each tuned to its audience.",
              },
            ].map((s, i) => (
              <div
                key={s.step}
                className={`py-16 ${i > 0 ? "lg:pl-16" : ""} ${i < 2 ? "border-b border-border lg:border-b-0 lg:border-r lg:pr-16" : ""}`}
              >
                <span className="font-mono text-[11px] text-muted tracking-widest">
                  {s.step}
                </span>
                <h3 className="mt-4 text-xl font-semibold">{s.title}</h3>
                <p className="mt-3 text-sm text-muted leading-relaxed">
                  {s.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* --- numbers --- */}
      <section className="border-t border-border bg-background relative z-10">
        <div className="mx-auto max-w-7xl px-8 py-20">
          <div className="grid sm:grid-cols-4 gap-8 text-center">
            {[
              { value: "200+", label: "Markets supported" },
              { value: "4.2M", label: "Variants generated" },
              { value: "<3 min", label: "Avg. processing time" },
              { value: "+41%", label: "Avg. engagement lift" },
            ].map((stat) => (
              <div key={stat.label}>
                <span className="text-3xl font-bold tracking-tight">{stat.value}</span>
                <span className="mt-1 block text-xs text-muted uppercase tracking-wider">{stat.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* --- pricing --- */}
      <div id="pricing">
        <Pricing />
      </div>

      {/* --- cta --- */}
      <section className="border-t border-border bg-background relative z-10">
        <div className="mx-auto max-w-7xl px-8 py-24 flex flex-col items-center text-center">
          <h2 className="text-3xl font-bold tracking-tight">Ready to go global?</h2>
          <p className="mt-4 text-sm text-muted max-w-md leading-relaxed">
            See how ADAPT can scale your creative across every market. Book a personalized demo with our team.
          </p>
          <div className="mt-8 flex items-center gap-4">
            <button
              onClick={openLogin}
              className="cursor-pointer px-8 py-3 bg-[#1c1c1c] text-white rounded-full text-sm font-medium hover:bg-black transition-colors"
            >
              Request a demo
            </button>
            <button
              onClick={() => scrollToSection('pricing')}
              className="cursor-pointer px-8 py-3 bg-transparent text-foreground border border-border rounded-full text-sm font-medium hover:bg-foreground/5 transition-colors"
            >
              View pricing
            </button>
          </div>
        </div>
      </section>

      {/* --- footer --- */}
      <footer className="border-t border-border bg-background relative z-10">
        <div className="mx-auto max-w-7xl px-8 py-10 flex flex-col sm:flex-row justify-between items-center gap-6">
          <span className="text-sm font-medium tracking-widest uppercase">ADAPT</span>
          <div className="flex items-center gap-8">
            <Link href="#" className="text-xs text-muted hover:text-foreground transition-colors">Privacy</Link>
            <Link href="#" className="text-xs text-muted hover:text-foreground transition-colors">Terms</Link>
            <Link href="#" className="text-xs text-muted hover:text-foreground transition-colors">Contact</Link>
          </div>
          <span className="text-xs text-muted">© 2026</span>
        </div>
      </footer>
    </div>
  );
}
