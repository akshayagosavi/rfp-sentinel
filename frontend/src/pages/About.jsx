import { Scale, ShieldCheck, UserCog } from 'lucide-react'
import Nav from '../components/Nav'
import GradientBackdrop from '../components/GradientBackdrop'
import Container from '../components/Container'
import Footer from '../components/Footer'

export default function About() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <GradientBackdrop />
      <Nav />
      <Container className="flex-1">
        <main className="max-w-2xl py-16">
          <h1 className="text-3xl font-semibold tracking-tight text-ink">About RFP Sentinel</h1>
          <p className="mt-4 text-sm leading-relaxed text-subtle">
            RFP Sentinel is a bid-evaluation co-pilot for GeM (Government e-Marketplace) procurement in the
            Electronics category, built around the buyer/evaluator's workflow — checking an RFP against real
            government procurement norms before it's published, and checking bidder submissions against the
            RFP's own approved criteria once bidding closes.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-subtle">
            Bidders get real value here too: a clear summary of each published tender, and exactly which
            documents to submit and how to name them, so a submission is never invalidated by an avoidable
            mistake. The evaluator's side is where the deepest checks happen, but the platform is useful to
            both sides of the same tender.
          </p>

          <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-3">
            <div className="rounded-card border border-line bg-elevated p-5">
              <Scale size={18} className="text-accent" />
              <h3 className="mt-3 text-sm font-semibold text-ink">Grounded in real norms</h3>
              <p className="mt-1 text-xs text-subtle">Every check maps to an actual procurement rule, with a citation.</p>
            </div>
            <div className="rounded-card border border-line bg-elevated p-5">
              <UserCog size={18} className="text-accent" />
              <h3 className="mt-3 text-sm font-semibold text-ink">Human in the loop</h3>
              <p className="mt-1 text-xs text-subtle">Every flag is a suggestion for a person to review, never an automatic decision.</p>
            </div>
            <div className="rounded-card border border-line bg-elevated p-5">
              <ShieldCheck size={18} className="text-accent" />
              <h3 className="mt-3 text-sm font-semibold text-ink">Auditable by design</h3>
              <p className="mt-1 text-xs text-subtle">Deterministic scoring, real citations — decisions that hold up to review.</p>
            </div>
          </div>
        </main>
      </Container>
      <Footer />
    </div>
  )
}
