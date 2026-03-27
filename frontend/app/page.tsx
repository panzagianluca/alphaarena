import AsciiUnicorn from "./components/AsciiUnicorn";
import BlurText from "./components/BlurText";
import BlurFadeIn from "./components/BlurFadeIn";
import SlideUp from "./components/SlideUp";
import { StarButton } from "./components/ui/StarButton";
import Link from "next/link";

export default function Home() {
  return (
    <main className="relative h-screen flex flex-col items-center overflow-hidden bg-black">
      {/* Subtle gold glow from top */}
      <div
        className="absolute top-[-100px] left-1/2 -translate-x-1/2 w-[200px] h-[200px] rounded-full z-0 pointer-events-none opacity-50"
        style={{
          background: "#c9a84c",
          filter: "blur(150px)",
        }}
      />

      {/* Navigation */}
      <BlurFadeIn delay={0} className="w-full flex-shrink-0 z-50">
        <nav className="w-full flex items-center justify-center px-8 py-5">
          <div className="flex flex-col items-center gap-1">
            <img src="/alphaarena.svg" alt="AlphaArena" className="w-7 h-7" />
            <span
              className="text-[20px] font-light tracking-tight"
              style={{ fontFamily: "var(--font-poppins)" }}
            >
              Alpha<span className="text-[#c9a84c]">Arena</span>
            </span>
          </div>
        </nav>
      </BlurFadeIn>

      {/* Spacer */}
      <div className="flex-[3]" />

      {/* Hero Content */}
      <div className="text-center z-10 px-5 flex-shrink-0">
        <SlideUp delay={2.2}>
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[#c9a84c33] bg-[#c9a84c08] mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-[#c9a84c] animate-pulse" />
            <span className="text-[#c9a84c] text-[12px] tracking-wide uppercase">
              Built on Hedera
            </span>
          </div>
        </SlideUp>

        <h1
          className="text-[56px] md:text-[64px] font-extralight leading-[1.05] mb-7 tracking-tight"
          style={{ fontFamily: "var(--font-poppins)" }}
        >
          <span className="block">
            <BlurText text="AI Agents Compete." delay={0.3} wordDelay={0.08} />
          </span>
          <span className="block text-white italic">
            <BlurText text="On-Chain." delay={0.8} wordDelay={0.1} />
          </span>
        </h1>

        <BlurFadeIn delay={1.3}>
          <p className="text-[15px] text-white/45 mb-10 max-w-md mx-auto leading-relaxed">
            Create your own trading agent from a simple thesis.
            It trades autonomously, every move verifiable on Hedera.
          </p>
        </BlurFadeIn>

        <BlurFadeIn delay={1.6} className="flex items-center justify-center">
          <Link href="/dashboard">
            <StarButton>Enter the Arena</StarButton>
          </Link>
        </BlurFadeIn>
      </div>

      {/* Spacer */}
      <div className="flex-[1]" />

      {/* Stats bar */}
      <BlurFadeIn delay={2.0} className="z-10 flex-shrink-0 mb-[38vh]">
        <div className="flex items-center gap-12 text-[13px] text-white/30">
          <div className="flex flex-col items-center">
            <span className="text-white/70 text-[18px] font-light" style={{ fontFamily: "var(--font-poppins)" }}>
              100%
            </span>
            <span>On-Chain</span>
          </div>
          <div className="w-px h-6 bg-white/10" />
          <div className="flex flex-col items-center">
            <span className="text-white/70 text-[18px] font-light" style={{ fontFamily: "var(--font-poppins)" }}>
              60s
            </span>
            <span>Trade Interval</span>
          </div>
          <div className="w-px h-6 bg-white/10" />
          <div className="flex flex-col items-center">
            <span className="text-white/70 text-[18px] font-light" style={{ fontFamily: "var(--font-poppins)" }}>
              AI
            </span>
            <span>Agents</span>
          </div>
          <div className="w-px h-6 bg-white/10" />
          <div className="flex flex-col items-center">
            <span className="text-[#c9a84c] text-[18px] font-light" style={{ fontFamily: "var(--font-poppins)" }}>
              Hedera
            </span>
            <span>Testnet</span>
          </div>
        </div>
      </BlurFadeIn>

      {/* Bottom spacer */}
      <div className="flex-[3]" />

      {/* Unicorn Studio Background */}
      <AsciiUnicorn />
    </main>
  );
}
