import { useEffect, useState } from 'react'
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
          <a href="/login" className={styles.signInLink}>Sign in →</a>
        </div>
      </header>

      {/* Hero */}
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <p className={styles.eyebrow}>Your personal memory layer</p>
          <h1 className={styles.heroHeading}>You control<br />your context.</h1>
          <p className={styles.heroSub}>
            Identiti turns everything you know about yourself into a living knowledge graph —
            searchable, editable, portable, and always ready to hand to any AI.
          </p>
          <div className={styles.heroCtas}>
            <a href="/login" className={styles.ctaPrimary}>Get started free</a>
            <a href="#features" className={styles.ctaSecondary}>See how it works</a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className={styles.section} id="features">
        <p className={styles.sectionLabel}>Features</p>
        <h2 className={styles.sectionHeading}>Everything about you, structured.</h2>
        <div className={styles.featureGrid}>
          <FeatureCard
            icon="✦"
            title="Memory graph"
            desc="Skills, goals, values, traitsevery piece of you becomes a node. Relationships between them become edges. Your identity, mapped."
          />
          <FeatureCard
            icon="◎"
            title="Chat to build"
            desc="Just talk. Our AI asks you the right questions and builds your graph from the conversation. No forms, no friction."
          />
          <FeatureCard
            icon="⬡"
            title="Fully editable"
            desc="Add, rename, or delete any node or relationship. It's your graph. You have full control over every piece of it."
          />
          <FeatureCard
            icon="↗"
            title="Portable Memory Card"
            desc="Download a markdown snapshot of your entire profile. Paste it into ChatGPT, Claude, or any AI to give it instant context about you."
          />
          <FeatureCard
            icon="⌘"
            title="Bring your own key"
            desc="Use your own API key from Groq, OpenAI, or Anthropic. Your key goes directly to the providerwe never see it."
          />
          <FeatureCard
            icon="◈"
            title="Shape your graph"
            desc="Rearrange your nodes into any shapea galaxy, a crown, a spiral. Because your identity should be beautiful too."
          />
        </div>
      </section>

      {/* How it works */}
      <section className={styles.section} id="how">
        <p className={styles.sectionLabel}>How it works</p>
        <h2 className={styles.sectionHeading}>Three steps to your second brain.</h2>
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
        <h2 className={styles.sectionHeading}>You own your memory.</h2>
        <div className={styles.securityGrid}>
          <SecurityCard
            icon="🔑"
            title="Your key, your calls"
            desc="When you use BYOK, your API key is sent directly to the LLM provider from your browser. It never touches our servers."
          />
          <SecurityCard
            icon="🫆"
            title="Your data, your control"
            desc="You can edit or delete any node in your graph at any time. Nothing is permanent unless you commit it."
          />
          <SecurityCard
            icon="🔐"
            title="End-to-end encrypted"
            desc="Your graph data is encrypted at rest. Only you can read it. Not us, not anyone else."
          />
          <SecurityCard
            icon="🔒"
            title="No model training"
            desc="Your personal data is never used to train models. What's in your graph stays in your graph."
          />
        </div>
      </section>

      {/* CTA */}
      <section className={styles.ctaSection}>
        <h2 className={styles.ctaHeading}>Start building your memory graph.</h2>
        <p className={styles.ctaSub}>Free to use. No credit card required.</p>
        <a href="/login" className={styles.ctaPrimary}>Get started →</a>
      </section>

      <footer className={styles.footer}>
        <span className={styles.footerBrand}>Identiti.</span>
        <span className={styles.footerNote}>Built by Nandana Dileep</span>
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
