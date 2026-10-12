/**
 * Cards that pin and stack as the page scrolls, after React Bits' ScrollStack (reactbits.dev).
 * Written for this project: stacking is plain CSS `position: sticky` with a growing top offset,
 * and each card that gets covered scales down slightly. Under reduced motion the cards still
 * stack, without the scaling.
 */
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { Children, useRef, type ReactNode } from "react";

const TOP = 96; // px below the viewport top where the first card pins (clears the sticky header)
const STEP = 18; // px each later card pins below the previous one
const SCALE_STEP = 0.04; // how much a card shrinks for each card stacked on top of it

function StackCard({ children, index, total }: { children: ReactNode; index: number; total: number }) {
  const ref = useRef<HTMLLIElement>(null);
  const reduce = useReducedMotion();
  // 0 when this card reaches its pin point, 1 when the list's last card has pinned on top of it.
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const finalScale = 1 - SCALE_STEP * (total - 1 - index);
  const scale = useTransform(scrollYProgress, [0, 1], [1, finalScale]);

  return (
    <li ref={ref} className="sticky list-none" style={{ top: TOP + index * STEP }}>
      <motion.div style={reduce ? undefined : { scale, transformOrigin: "top center" }}>{children}</motion.div>
    </li>
  );
}

export function ScrollStack({ children, label }: { children: ReactNode; label: string }) {
  const items = Children.toArray(children);
  return (
    <ol aria-label={label} className="space-y-6 pb-16">
      {items.map((child, i) => (
        <StackCard key={i} index={i} total={items.length}>
          {child}
        </StackCard>
      ))}
    </ol>
  );
}

export function ScrollStackItem({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-line bg-surface p-6 shadow-[var(--shadow-mockup)] sm:p-8">{children}</div>;
}
