/**
 * Shared motion for the app. Every animation here responds to a state change (page load,
 * new message, opened panel, switched dataset), never to scrolling or the cursor.
 * Blur-in, shine, and staggered list techniques are inspired by React Bits (reactbits.dev);
 * the code is written for this project.
 */
import { motion, useReducedMotion, type Transition, type Variants } from "motion/react";
import { Fragment, type ReactNode } from "react";

/** Ease-out curve used across the UI: fast start, soft landing. */
export const EASE = [0.22, 1, 0.36, 1] as const;

export const fadeRise = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.32, ease: EASE } satisfies Transition,
};

export const sheetSpring: Transition = { type: "spring", stiffness: 420, damping: 38, mass: 0.9 };

export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.34, ease: EASE } },
};

/**
 * Headline that settles in word by word, from a slight blur, once on mount.
 * Screen readers get the full text from aria-label; reduced motion shows it plainly.
 */
export function BlurText({ text, className = "", delay = 0 }: { text: string; className?: string; delay?: number }) {
  const reduce = useReducedMotion();
  const words = text.split(" ");
  if (reduce) return <h1 className={className}>{text}</h1>;
  return (
    <h1 className={className} aria-label={text}>
      {words.map((word, i) => (
        <Fragment key={`${word}-${i}`}>
          <motion.span
            aria-hidden
            className="inline-block will-change-[filter,transform,opacity]"
            initial={{ opacity: 0, y: 10, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.6, ease: EASE, delay: delay + i * 0.07 }}
          >
            {word}
          </motion.span>
          {/* A normal space between words, so it collapses at line ends and wrapping matches plain text */}
          {i < words.length - 1 && " "}
        </Fragment>
      ))}
    </h1>
  );
}

/** Status text with a soft light sweep, used while waiting for an answer. Static under reduced motion. */
export function ShinyText({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`shiny-text ${className}`}>{children}</span>;
}
