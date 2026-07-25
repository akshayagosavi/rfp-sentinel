import { motion, useReducedMotion } from 'framer-motion'

// One KPI card: big number, label, small context/trend line, icon. Used in
// a 4-up row at the top of every dashboard. `context` should say plainly
// where a value comes from when it isn't a hard count (e.g. "across all
// published RFPs") -- never a fabricated number dressed up as real.
export function KpiCard({ icon: Icon, label, value, context, index = 0 }) {
  const reduceMotion = useReducedMotion()
  return (
    <motion.div
      initial={reduceMotion ? undefined : { opacity: 0, y: 10 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05, ease: 'easeOut' }}
      className="rounded-card border border-line bg-elevated p-5"
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
        <Icon size={16} />
      </span>
      <p className="mt-3 text-2xl font-semibold text-ink">{value}</p>
      <p className="mt-0.5 text-sm text-subtle">{label}</p>
      {context && <p className="mt-1 text-xs text-subtle/70">{context}</p>}
    </motion.div>
  )
}

export function KpiStrip({ children }) {
  return <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">{children}</div>
}
