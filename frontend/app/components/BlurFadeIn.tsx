"use client";

import { motion } from "framer-motion";
import { ReactNode } from "react";

interface BlurFadeInProps {
  children: ReactNode;
  delay?: number;
  className?: string;
}

export default function BlurFadeIn({
  children,
  delay = 0,
  className = "",
}: BlurFadeInProps) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, filter: "blur(10px)" }}
      animate={{ opacity: 1, filter: "blur(0px)" }}
      transition={{
        duration: 0.8,
        delay,
        ease: [0.22, 1, 0.36, 1],
      }}
    >
      {children}
    </motion.div>
  );
}
