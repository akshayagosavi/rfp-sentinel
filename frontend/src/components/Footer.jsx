import { ShieldCheck } from 'lucide-react'
import Container from './Container'

// slim=true for dashboards (a thin closing line, no dead space below
// content) -- full footer only on public pages, per the design spec.
export default function Footer({ slim = false }) {
  if (slim) {
    return (
      <footer className="mt-12 border-t border-line py-6">
        <Container>
          <p className="text-center text-xs text-subtle/70">RFP Sentinel &middot; GeM procurement, Electronics category</p>
        </Container>
      </footer>
    )
  }

  return (
    <footer className="mt-16 border-t border-line py-10">
      <Container className="flex flex-col items-center gap-3 text-center sm:flex-row sm:justify-between sm:text-left">
        <div className="flex items-center gap-2 text-sm font-semibold text-ink">
          <ShieldCheck size={16} className="text-accent" />
          RFP Sentinel
        </div>
        <p className="text-xs text-subtle">A bid-evaluation co-pilot for GeM procurement, Electronics category.</p>
        <p className="text-xs text-subtle/70">&copy; {new Date().getFullYear()} RFP Sentinel</p>
      </Container>
    </footer>
  )
}
