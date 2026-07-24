import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import {
  Building2,
  Handshake,
  Settings2,
  ShieldCheck,
  UploadCloud,
  ScanSearch,
  UserCheck,
  CheckCircle2,
  Scale,
  UserCog,
  FileSearch,
} from 'lucide-react'
import Nav from '../components/Nav'
import GradientBackdrop from '../components/GradientBackdrop'

const ROLES = [
  {
    name: 'Buyers',
    icon: Building2,
    description:
      'Upload an RFP, get it checked against government procurement norms, and publish it with confidence.',
    comingSoon: false,
  },
  {
    name: 'Bidders',
    icon: Handshake,
    description: 'See published RFPs and exactly which documents you need to submit for each one.',
    comingSoon: false,
  },
  {
    name: 'Admins',
    icon: Settings2,
    description: 'Manage the norm knowledge base and user access across the platform.',
    comingSoon: true,
  },
]

const STEPS = [
  { icon: UploadCloud, title: 'Upload RFP', description: 'Buyer uploads the tender PDF.' },
  {
    icon: ScanSearch,
    title: 'Checked against norms',
    description:
      'Validated against six government procurement norms (GFR 2017, GeM GTC, Make-in-India, MeitY CRS, BIS CRS, MSME policy).',
  },
  {
    icon: UserCheck,
    title: 'Human checkpoint',
    description: 'Evaluator reviews and approves the extracted criteria.',
  },
  {
    icon: CheckCircle2,
    title: 'Publish with confidence',
    description: 'Compliant RFPs are published and stored; issues are flagged with reasons.',
  },
]

const FEATURES = [
  {
    icon: Scale,
    title: 'Grounded in real norms',
    description: 'Every check maps to an actual procurement rule, not a guess.',
  },
  {
    icon: UserCog,
    title: 'Built for the evaluator',
    description: 'A co-pilot for the assigned Technical Evaluator, not the bidder side.',
  },
  {
    icon: FileSearch,
    title: 'Auditable by design',
    description: 'Deterministic, rule-referenced decisions with human checkpoints, so every call is defensible.',
  },
]

const heroContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12 } },
}
const heroItem = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } },
}

function SectionHeading({ title, subtitle, reduceMotion }) {
  return (
    <motion.div
      initial={reduceMotion ? undefined : { opacity: 0, y: 16 }}
      whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.5 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="mx-auto max-w-xl text-center"
    >
      <h2 className="text-2xl font-semibold tracking-tight text-ink">{title}</h2>
      {subtitle && <p className="mt-2 text-sm text-subtle">{subtitle}</p>}
    </motion.div>
  )
}

export default function Landing() {
  const reduceMotion = useReducedMotion()

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <GradientBackdrop />
      <Nav>
        <Link
          to="/bidder/login"
          className="text-sm font-medium text-subtle transition-colors duration-200 hover:text-ink"
        >
          Bidder Login
        </Link>
        <Link
          to="/login"
          className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.03] hover:bg-accent-hover hover:shadow-[0_0_24px_-6px_var(--color-accent)]"
        >
          Buyer Login
        </Link>
      </Nav>

      <main className="mx-auto max-w-3xl px-6 pt-16 pb-12 text-center">
        <motion.div
          variants={reduceMotion ? undefined : heroContainer}
          initial={reduceMotion ? undefined : 'hidden'}
          animate={reduceMotion ? undefined : 'show'}
        >
          <motion.h1
            variants={reduceMotion ? undefined : heroItem}
            className="text-4xl font-semibold tracking-tight text-ink sm:text-5xl"
          >
            Bid evaluation, grounded in the rules that actually govern it.
          </motion.h1>
          <motion.p
            variants={reduceMotion ? undefined : heroItem}
            className="mx-auto mt-6 max-w-xl text-lg text-subtle"
          >
            RFP Sentinel checks tenders and bids against government procurement norms
            automatically, so evaluators spend their time on judgment calls, not paperwork.
          </motion.p>
          <motion.div variants={reduceMotion ? undefined : heroItem} className="mt-10">
            <Link
              to="/login"
              className="rounded-full bg-accent px-6 py-3 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:scale-[1.03] hover:bg-accent-hover hover:shadow-[0_0_28px_-6px_var(--color-accent)]"
            >
              Get started as a buyer
            </Link>
          </motion.div>
        </motion.div>
      </main>

      {/* Roles */}
      <section className="border-t border-line py-16">
        <div className="mx-auto grid max-w-5xl grid-cols-1 gap-6 px-6 sm:grid-cols-3">
          {ROLES.map((role, i) => (
            <motion.div
              key={role.name}
              initial={reduceMotion ? undefined : { opacity: 0, y: 20 }}
              whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.4, ease: 'easeOut', delay: reduceMotion ? 0 : i * 0.1 }}
              className="relative overflow-hidden rounded-card border border-line bg-elevated p-6 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-md"
            >
              <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-transparent via-accent to-transparent opacity-80" />
              <div className="flex items-center justify-between">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                  <role.icon size={18} />
                </span>
                {role.comingSoon && (
                  <span className="rounded-full border border-line bg-surface px-2 py-0.5 text-[10px] font-medium tracking-wide text-subtle uppercase">
                    Coming soon
                  </span>
                )}
              </div>
              <h3 className="mt-4 text-sm font-semibold text-ink">{role.name}</h3>
              <p className="mt-2 text-sm text-subtle">{role.description}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-line py-16">
        <div className="mx-auto max-w-5xl px-6">
          <SectionHeading
            title="How it works"
            subtitle="From upload to a published, defensible RFP."
            reduceMotion={reduceMotion}
          />
          <div className="mt-14 flex flex-col gap-10 sm:flex-row sm:items-start sm:gap-0">
            {STEPS.map((step, i) => (
              <div key={step.title} className="flex flex-1 flex-col items-center sm:flex-row sm:items-start">
                <motion.div
                  initial={reduceMotion ? undefined : { opacity: 0, y: 20 }}
                  whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.4 }}
                  transition={{ duration: 0.4, ease: 'easeOut', delay: reduceMotion ? 0 : i * 0.1 }}
                  className="flex flex-col items-center px-2 text-center"
                >
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-line bg-elevated text-accent">
                    <step.icon size={20} />
                  </span>
                  <span className="mt-3 text-xs font-medium text-subtle">Step {i + 1}</span>
                  <h3 className="mt-1 text-sm font-semibold text-ink">{step.title}</h3>
                  <p className="mt-2 max-w-[13rem] text-sm text-subtle">{step.description}</p>
                </motion.div>
                {i < STEPS.length - 1 && (
                  <div className="mx-2 mt-6 hidden h-px flex-1 border-t border-dashed border-line sm:block" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Why RFP Sentinel */}
      <section className="border-t border-line py-16">
        <div className="mx-auto max-w-5xl px-6">
          <SectionHeading title="Why RFP Sentinel" reduceMotion={reduceMotion} />
          <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-3">
            {FEATURES.map((feature, i) => (
              <motion.div
                key={feature.title}
                initial={reduceMotion ? undefined : { opacity: 0, y: 20 }}
                whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{ duration: 0.4, ease: 'easeOut', delay: reduceMotion ? 0 : i * 0.1 }}
                className="relative overflow-hidden rounded-card border border-line bg-elevated p-6 shadow-sm"
              >
                <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-transparent via-accent to-transparent opacity-80" />
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                  <feature.icon size={18} />
                </span>
                <h3 className="mt-4 text-sm font-semibold text-ink">{feature.title}</h3>
                <p className="mt-2 text-sm text-subtle">{feature.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Closing CTA band */}
      <section className="border-t border-line bg-gradient-to-r from-accent/5 via-accent/10 to-accent/5">
        <motion.div
          initial={reduceMotion ? undefined : { opacity: 0, y: 16 }}
          whileInView={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.5 }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="mx-auto max-w-3xl px-6 py-16 text-center"
        >
          <h2 className="text-2xl font-semibold tracking-tight text-ink">
            Ready to evaluate with confidence?
          </h2>
          <div className="mt-6">
            <Link
              to="/login"
              className="rounded-full bg-accent px-6 py-3 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:scale-[1.03] hover:bg-accent-hover hover:shadow-[0_0_28px_-6px_var(--color-accent)]"
            >
              Get started as a buyer
            </Link>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line bg-elevated">
        <div className="mx-auto max-w-5xl px-6 py-12">
          <div className="grid grid-cols-1 gap-10 sm:grid-cols-3">
            <div>
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                <ShieldCheck size={18} className="text-accent" />
                RFP Sentinel
              </span>
              <p className="mt-3 max-w-xs text-sm text-subtle">
                Bid evaluation, grounded in the rules that actually govern it.
              </p>
            </div>
            <div>
              <h4 className="text-xs font-semibold tracking-wide text-subtle uppercase">Product</h4>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  <a href="#" className="text-subtle transition-colors duration-200 hover:text-ink">
                    Buyers
                  </a>
                </li>
                <li>
                  <Link to="/bidder/login" className="text-subtle transition-colors duration-200 hover:text-ink">
                    Bidders
                  </Link>
                </li>
                <li>
                  <a href="#" className="text-subtle transition-colors duration-200 hover:text-ink">
                    Admins (soon)
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="text-xs font-semibold tracking-wide text-subtle uppercase">Resources</h4>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  <a href="#" className="text-subtle transition-colors duration-200 hover:text-ink">
                    About
                  </a>
                </li>
                <li>
                  <a href="#" className="text-subtle transition-colors duration-200 hover:text-ink">
                    GeM procurement norms
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="mt-10 flex flex-col items-center justify-between gap-2 border-t border-line pt-6 text-xs text-subtle sm:flex-row">
            <span>© 2026 RFP Sentinel</span>
            <span>Built for GeM Electronics procurement</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
