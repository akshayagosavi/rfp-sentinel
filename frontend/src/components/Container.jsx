// One width system, reused on every page (public + all three dashboards) --
// ~90% of viewport on smaller screens, capped at 1280px (matches Nav.jsx's
// max-w-7xl so the navbar and page content always align), so nothing floats
// in an inconsistent narrow column from page to page.
export default function Container({ children, className = '' }) {
  return <div className={`mx-auto w-full max-w-7xl px-6 lg:px-8 ${className}`}>{children}</div>
}
