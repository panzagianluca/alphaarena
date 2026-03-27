"use client";

import React, { useEffect, useState, useMemo } from "react";

interface BlurTextProps {
  text: string;
  className?: string;
  delay?: number;
  wordDelay?: number;
}

export default function BlurText({
  text,
  className = "",
  delay = 0,
  wordDelay: _wordDelay,
}: BlurTextProps) {
  const [isAnimating, setIsAnimating] = useState(false);

  const words = useMemo(() => {
    const splitWords = text.split(" ");
    const totalWords = splitWords.length;

    return splitWords.map((word, index) => {
      const progress = index / totalWords;
      const exponentialDelay = Math.pow(progress, 0.8) * 0.4;
      const baseDelay = index * 0.06;

      return {
        text: word,
        duration: 1.8 + Math.cos(index * 0.3) * 0.2,
        delay: delay + baseDelay + exponentialDelay,
        blur: 12 + ((index * 7 + 3) % 6),
        scale: 0.92 + Math.sin(index * 0.2) * 0.04,
      };
    });
  }, [text, delay]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsAnimating(true);
    }, 200);
    return () => clearTimeout(timer);
  }, []);

  return (
    <span className={className}>
      {words.map((word, index) => (
        <span
          key={index}
          className={`inline-block transition-all ${isAnimating ? "opacity-100" : "opacity-0"}`}
          style={{
            transitionDuration: `${word.duration}s`,
            transitionDelay: `${word.delay}s`,
            transitionTimingFunction: "cubic-bezier(0.25, 0.46, 0.45, 0.94)",
            filter: isAnimating
              ? "blur(0px) brightness(1)"
              : `blur(${word.blur}px) brightness(0.6)`,
            transform: isAnimating
              ? "translateY(0) scale(1) rotateX(0deg)"
              : `translateY(16px) scale(${word.scale}) rotateX(-12deg)`,
            marginRight: "0.3em",
            willChange: "filter, transform, opacity",
            transformStyle: "preserve-3d",
            backfaceVisibility: "hidden",
            textShadow: isAnimating
              ? "0 2px 8px rgba(255,255,255,0.08)"
              : "0 0 30px rgba(255,255,255,0.3)",
          }}
        >
          {word.text}
        </span>
      ))}
    </span>
  );
}
