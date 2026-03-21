import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import ThemeToggle from '../components/ThemeToggle'
import styles from './Landing.module.css'

export default function Landing() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className={styles.root}>
      <div className={styles.blob1} />
      <div className={styles.blob2} />
      <div className={styles.blob3} />

      <header className={`${styles.header} ${scrolled ? styles.headerScrolled : ''}`}>
        <span className={styles.brand}>Identiti.</span>
        <div className={styles.headerRight}>
          <ThemeToggle />
          <Link to="/login" className={styles.signInLink}>Sign in <ArrowIcon /></Link>
        </div>
      </header>

      {/* Hero */}
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <p className={styles.eyebrow}>Your personal memory layer</p>
          <h1 className={styles.heroHeading}>You control<br />your context.</h1>
          <p className={styles.heroSub}>
            Searchable, editable, portable context always ready to hand to any AI.
          </p>
          <div className={styles.heroCtas}>
            <Link to="/login" className={styles.ctaPrimary}>Get started free</Link>
            <a href="#features" className={styles.ctaSecondary}>See how it works</a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className={styles.section} id="features">
        <p className={styles.sectionLabel}>Features</p>
        <h2 className={styles.sectionHeading}>Everything about you, structured.</h2>
        <div className={styles.featureGrid}>
          <FeatureCard icon={<GraphIcon />} title="Memory graph" desc="Skills, goals, values, traits — every piece of you becomes a node. Relationships between them become edges. Your identity, mapped." />
          <FeatureCard icon={<ChatIcon />} title="Chat to build" desc="Just talk. Our AI asks you the right questions and builds your graph from the conversation. No forms, no friction." />
          <FeatureCard icon={<EditIcon />} title="Fully editable" desc="Add, rename, or delete any node or relationship. It's your graph. You have full control over every piece of it." />
          <FeatureCard icon={<ExportIcon />} title="Portable Memory Card" desc="Download a markdown snapshot of your entire profile. Paste it into ChatGPT, Claude, or any AI to give it instant context about you." />
          <FeatureCard icon={<KeyIcon />} title="Bring your own key" desc="Use your own API key from Groq, OpenAI, or Anthropic. Your key goes directly to the provider — we never see it." />
          <FeatureCard icon={<ShapeIcon />} title="Shape your graph" desc="Rearrange your nodes into any shape — a galaxy, a crown, a spiral. Because your identity should be beautiful too." />
        </div>
      </section>

      {/* How it works */}
      <section className={styles.section} id="how">
        <p className={styles.sectionLabel}>How it works</p>
        <h2 className={styles.sectionHeading}>Just three steps.</h2>
        <div className={styles.steps}>
          <Step n="01" title="Chat with our AI" desc="Answer a few questions. The AI extracts your skills, values, goals, and personality traits and builds your graph automatically." />
          <div className={styles.stepDivider} />
          <Step n="02" title="Explore your graph" desc="See yourself as a network. Search any node, add new ones, edit existing ones, and watch your profile grow over time." />
          <div className={styles.stepDivider} />
          <Step n="03" title="Take it anywhere" desc="Download your Memory Card and paste it into any AI. Now every AI knows who you are, what you value, and how you think." />
        </div>
      </section>

      {/* Security */}
      <section className={styles.section} id="security">
        <p className={styles.sectionLabel}>Privacy & Security</p>
        <h2 className={styles.sectionHeading}>You own your context.</h2>
        <div className={styles.securityGrid}>
          <SecurityCard icon={<KeyIcon />} title="Your key, your calls" desc="When you use BYOK, your API key is sent directly to the LLM provider from your browser. It never touches our servers." />
          <SecurityCard icon={<FingerprintIcon />} title="Your data, your control" desc="You can edit or delete any node in your graph at any time. Nothing is permanent unless you commit it." />
          <SecurityCard icon={<LockIcon />} title="End-to-end encrypted" desc="Your graph data is encrypted at rest. Only you can read it. Not us, not anyone else." />
          <SecurityCard icon={<ShieldIcon />} title="No model training" desc="Your personal data is never used to train models. What's in your graph stays in your graph." />
        </div>
      </section>

      {/* CTA */}
      <section className={styles.ctaSection}>
        <h2 className={styles.ctaHeading}>Start building your context.</h2>
        <p className={styles.ctaSub}>Free to use. No credit card required.</p>
        <Link to="/login" className={styles.ctaPrimary}>Get started</Link>
      </section>

      <footer className={styles.footer}>
        <span className={styles.footerBrand}>Identiti.</span>
        <span className={styles.footerNote}>Built by <a href="mailto:nandanadileep29@gmail.com" className={styles.footerLink}>Nandana Dileep</a></span>
      </footer>
    </div>
  )
}

function FeatureCard({ icon, title, desc }) {
  return (
    <div className={styles.featureCard}>
      <div className={styles.featureIcon}>{icon}</div>
      <h3 className={styles.featureTitle}>{title}</h3>
      <p className={styles.featureDesc}>{desc}</p>
    </div>
  )
}

function Step({ n, title, desc }) {
  return (
    <div className={styles.step}>
      <span className={styles.stepN}>{n}</span>
      <h3 className={styles.stepTitle}>{title}</h3>
      <p className={styles.stepDesc}>{desc}</p>
    </div>
  )
}

function SecurityCard({ icon, title, desc }) {
  return (
    <div className={styles.securityCard}>
      <div className={styles.securityIcon}>{icon}</div>
      <h3 className={styles.securityTitle}>{title}</h3>
      <p className={styles.securityDesc}>{desc}</p>
    </div>
  )
}

function ArrowIcon() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{display:'inline',verticalAlign:'middle',marginLeft:4}}><path d="M2 6h8M6 2l4 4-4 4"/></svg>
}

function GraphIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="10" cy="10" r="2"/><circle cx="3" cy="5" r="1.5"/><circle cx="17" cy="5" r="1.5"/><circle cx="3" cy="15" r="1.5"/><circle cx="17" cy="15" r="1.5"/><line x1="4.1" y1="6.1" x2="8.3" y2="8.7"/><line x1="15.9" y1="6.1" x2="11.7" y2="8.7"/><line x1="4.1" y1="13.9" x2="8.3" y2="11.3"/><line x1="15.9" y1="13.9" x2="11.7" y2="11.3"/></svg>
}

function ChatIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H7l-4 3V5z"/></svg>
}

function EditIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 2.5a2.121 2.121 0 0 1 3 3L6 17H3v-3L14.5 2.5z"/></svg>
}

function ExportIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 14v2a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-2"/><polyline points="7 9 10 12 13 9"/><line x1="10" y1="2" x2="10" y2="12"/></svg>
}

function KeyIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="7.5" cy="10" r="4"/><path d="M11 10h8M16 8v4"/></svg>
}

function ShapeIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10 3c4 2 6 5 5 8s-4 5-8 4-5-4-4-7 3-6 7-5z"/></svg>
}

function FingerprintIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10 3a7 7 0 0 0-7 7"/><path d="M10 6a4 4 0 0 0-4 4c0 3 1.5 5 4 7"/><path d="M10 6a4 4 0 0 1 4 4c0 2-.5 4-2 6"/><path d="M10 9a1 1 0 0 1 1 1c0 2-1 4-3 6"/><path d="M13 4a7 7 0 0 1 4 6c0 2-.3 3.5-1 5"/></svg>
}

function LockIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="9" width="12" height="9" rx="2"/><path d="M7 9V6a3 3 0 0 1 6 0v3"/><circle cx="10" cy="14" r="1" fill="currentColor" stroke="none"/></svg>
}

function ShieldIcon() {
  return <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10 2L4 5v5c0 4 2.5 7 6 8 3.5-1 6-4 6-8V5l-6-3z"/><polyline points="7.5 10 9.5 12 13 8"/></svg>
}
