import { motion, useReducedMotion } from 'framer-motion'

// Fixed to the viewport (not the document) so the dot-grid + glow read as a
// whole-page backdrop -- present behind every section, not just the hero
// markup it happens to sit next to in the DOM.
export default function GradientBackdrop() {
  const reduceMotion = useReducedMotion()

  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-dot-grid opacity-70" />
      <motion.div
        className="absolute left-1/2 top-1/2 h-[44rem] w-[44rem] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl"
        style={{
          background:
            'radial-gradient(circle, color-mix(in srgb, var(--color-accent) 55%, transparent) 0%, color-mix(in srgb, var(--color-accent) 18%, transparent) 45%, transparent 72%)',
        }}
        animate={reduceMotion ? undefined : { scale: [1, 1.1, 1], opacity: [0.75, 1, 0.75] }}
        transition={{ duration: 9, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  )
}
