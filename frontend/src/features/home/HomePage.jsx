import ThemeLamp from '../../components/ThemeLamp'
import Header from './Header'
import Hero from './Hero'
import Features from './Features'
import HowItWorks from './HowItWorks'
import Demo from './Demo'
import Proof from './Proof'
import Faq from './Faq'
import Cta from './Cta'
import Footer from './Footer'

// The public home page at "/": the sections, top to bottom, in the order listed below. Each one is a single file in this
// folder, built step by step; for now every section except the header is only a name. The page paints its own background: white in light mode (`bg-surface` is
// #ffffff there) and dark in dark mode. It has to paint it itself: the <body> sits outside the theme wrapper, so it
// would stay cream (paper) in light mode and light in dark mode.
export default function HomePage() {
  return (
    <div className="home-page min-h-full bg-surface text-ink">
      {/* the same dark-mode lamp as on every other page; z-[60] keeps it (and its cord) above the fixed header (z-50) */}
      <ThemeLamp className="fixed right-6 top-0 z-[60] md:right-12" />
      <Header />
      <main id="main">
        <Hero />
        <Features />
        <HowItWorks />
        <Proof />
        <Demo/>
        <Faq />
        <Cta />
      </main>
      <Footer />
    </div>
  )
}
