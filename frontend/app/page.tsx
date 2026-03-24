"use client";

import { motion, type Transition } from "framer-motion";
import { FileText, Scale, Users, ArrowRight, Shield, AlertTriangle, TrendingUp } from "lucide-react";

const defaultTransition: Transition = { duration: 0.6, ease: "easeOut" };

const fadeIn = {
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: defaultTransition,
};

// ------------------------------------------------------------------
// Nav
// ------------------------------------------------------------------
function Nav() {
  return (
    <nav className="fixed top-0 z-50 w-full border-b border-border bg-cream/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <span className="font-serif text-2xl font-bold tracking-tight text-dark">
          LegiX
        </span>
        <div className="flex items-center gap-6">
          <a
            href="#"
            className="text-sm font-medium text-muted transition-colors hover:text-dark"
          >
            Connexion
          </a>
          <a
            href="#"
            className="rounded-full bg-dark px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            Demander une demo
          </a>
        </div>
      </div>
    </nav>
  );
}

// ------------------------------------------------------------------
// Hero
// ------------------------------------------------------------------
function Hero() {
  return (
    <section className="relative pt-32 pb-20">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          {...fadeIn}
          className="mx-auto max-w-3xl text-center"
        >
          <h1 className="font-serif text-5xl font-bold leading-tight tracking-tight text-dark md:text-6xl lg:text-7xl">
            Arretez de dechiffrer la legislation.{" "}
            <span className="text-warm">Commencez a l&apos;influencer.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted">
            LegiX surveille chaque texte, analyse l&apos;impact sur votre
            entreprise, et vous dit exactement quoi faire. En temps reel.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a
              href="#"
              className="inline-flex items-center gap-2 rounded-full bg-dark px-8 py-3.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
            >
              Demander une demo
              <ArrowRight className="h-4 w-4" />
            </a>
            <a
              href="#"
              className="inline-flex items-center gap-2 rounded-full border border-dark/20 px-8 py-3.5 text-sm font-medium text-dark transition-colors hover:border-dark/40"
            >
              Voir en action
            </a>
          </div>
        </motion.div>

        {/* Mock dashboard preview */}
        <motion.div
          {...fadeIn}
          transition={{ ...defaultTransition, delay: 0.2 }}
          className="mx-auto mt-16 max-w-4xl"
        >
          <div className="overflow-hidden rounded-2xl border border-border bg-white p-6 shadow-lg shadow-dark/5">
            {/* Header bar */}
            <div className="mb-6 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-3 w-3 rounded-full bg-threat" />
                <span className="text-sm font-semibold text-dark">
                  3 alertes critiques
                </span>
              </div>
              <span className="text-xs text-muted">
                Mis a jour il y a 2 min
              </span>
            </div>

            {/* Threat cards */}
            <div className="grid gap-4 md:grid-cols-3">
              <DashboardCard
                severity="critical"
                title="Projet de loi Finance 2026"
                tag="Impact fiscal"
                score="92%"
                impact="-2.4M EUR"
              />
              <DashboardCard
                severity="warning"
                title="Directive EU Cybersecurite"
                tag="Mise en conformite"
                score="78%"
                impact="6 mois"
              />
              <DashboardCard
                severity="info"
                title="Amendement Senat #4521"
                tag="Opportunite"
                score="45%"
                impact="+120K EUR"
              />
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function DashboardCard({
  severity,
  title,
  tag,
  score,
  impact,
}: {
  severity: "critical" | "warning" | "info";
  title: string;
  tag: string;
  score: string;
  impact: string;
}) {
  const colors = {
    critical: { dot: "bg-threat", badge: "bg-threat/10 text-threat" },
    warning: { dot: "bg-warning", badge: "bg-warning/10 text-warning" },
    info: { dot: "bg-info", badge: "bg-info/10 text-info" },
  };
  const c = colors[severity];

  return (
    <div className="rounded-xl border border-border bg-cream/40 p-4">
      <div className="mb-3 flex items-center gap-2">
        <div className={`h-2 w-2 rounded-full ${c.dot}`} />
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${c.badge}`}>
          {tag}
        </span>
      </div>
      <p className="text-sm font-semibold text-dark">{title}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        <span>Adoption : {score}</span>
        <span className="font-semibold text-dark">{impact}</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Features
// ------------------------------------------------------------------
function Features() {
  const features = [
    {
      icon: FileText,
      title: "Lit chaque texte. Comprend ce qu\u2019il fait reellement.",
      description:
        "17 sources surveillees 24/7. Classification IA automatique. Resume en langage clair.",
    },
    {
      icon: Scale,
      title: "Ce qu\u2019un avocat a 500\u20AC/h vous dirait. Instantanement.",
      description:
        "Impact financier chiffre. Score de probabilite d\u2019adoption. Plan d\u2019action personnalise.",
    },
    {
      icon: Users,
      title: "Chaque depute. Ce qu\u2019il porte. Toujours a jour.",
      description:
        "577 fiches completes. Votes nominatifs. Contacts directs et collaborateurs.",
    },
  ];

  return (
    <section className="py-24">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-8 md:grid-cols-3">
          {features.map((f, i) => (
            <motion.div
              key={i}
              {...fadeIn}
              transition={{ ...defaultTransition, delay: i * 0.1 }}
              className="rounded-2xl border border-border bg-white p-8"
            >
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-cream">
                <f.icon className="h-6 w-6 text-warm" />
              </div>
              <h3 className="font-serif text-xl font-semibold leading-snug text-dark">
                {f.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                {f.description}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------
// Process
// ------------------------------------------------------------------
function Process() {
  const steps = [
    {
      number: "01",
      title: "Nous vous apprenons",
      description:
        "Uploadez vos positions, vos donnees sectorielles, vos contacts. LegiX apprend votre ADN reglementaire.",
      icon: Shield,
    },
    {
      number: "02",
      title: "Nous surveillons tout",
      description:
        "Assemblee, Senat, JORF, EUR-Lex, regulateurs. Pas un texte ne passe sans analyse.",
      icon: AlertTriangle,
    },
    {
      number: "03",
      title: "Nous allons en profondeur",
      description:
        "Pas juste une alerte. Un briefing complet : impact, actions, contacts, documents prets.",
      icon: TrendingUp,
    },
  ];

  return (
    <section className="border-t border-border py-24">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div {...fadeIn} className="mb-16">
          <h2 className="font-serif text-4xl font-bold text-dark">
            Notre processus
          </h2>
        </motion.div>

        <div className="grid gap-12 md:grid-cols-3">
          {steps.map((s, i) => (
            <motion.div
              key={i}
              {...fadeIn}
              transition={{ ...defaultTransition, delay: i * 0.1 }}
            >
              <span className="font-serif text-5xl font-bold text-border">
                {s.number}
              </span>
              <h3 className="mt-4 font-serif text-xl font-semibold text-dark">
                {s.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                {s.description}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------
// Comparison
// ------------------------------------------------------------------
function Comparison() {
  return (
    <section className="py-24">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div {...fadeIn} className="mb-16 text-center">
          <h2 className="font-serif text-4xl font-bold text-dark">
            L&apos;ancienne methode vs LegiX
          </h2>
        </motion.div>

        <motion.div
          {...fadeIn}
          transition={{ ...defaultTransition, delay: 0.1 }}
          className="grid overflow-hidden rounded-2xl border border-border md:grid-cols-2"
        >
          {/* Old way */}
          <div className="bg-cream-dark/60 p-10">
            <p className="mb-8 text-xs font-semibold uppercase tracking-widest text-muted">
              Methode traditionnelle
            </p>
            <ul className="space-y-6">
              {[
                "Veille manuelle",
                "Alertes generiques",
                "Reaction tardive",
              ].map((item, i) => (
                <li
                  key={i}
                  className="flex items-center gap-3 text-muted"
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted/10 text-xs text-muted">
                    x
                  </span>
                  <span className="text-base">{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* LegiX way */}
          <div className="bg-dark p-10 text-white">
            <p className="mb-8 text-xs font-semibold uppercase tracking-widest text-white/60">
              Avec LegiX
            </p>
            <ul className="space-y-6">
              {[
                "IA dediee a votre secteur",
                "Impact chiffre en euros",
                "Plan d\u2019action instantane",
              ].map((item, i) => (
                <li
                  key={i}
                  className="flex items-center gap-3"
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-xs text-white">
                    &#10003;
                  </span>
                  <span className="text-base">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------
// CTA
// ------------------------------------------------------------------
function CtaSection() {
  return (
    <section className="border-t border-border py-24">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          {...fadeIn}
          className="mx-auto max-w-2xl text-center"
        >
          <h2 className="font-serif text-3xl font-bold leading-snug text-dark md:text-4xl">
            Nous construisons l&apos;IA pour proteger les entreprises du risque
            reglementaire.
          </h2>
          <div className="mt-10">
            <a
              href="#"
              className="inline-flex items-center gap-2 rounded-full bg-dark px-8 py-3.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
            >
              Demander une demo
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------
// Footer
// ------------------------------------------------------------------
function Footer() {
  return (
    <footer className="border-t border-border py-12">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 sm:flex-row">
        <span className="font-serif text-lg font-bold text-dark">LegiX</span>
        <p className="text-xs text-muted">
          &copy; 2026 LegiX. Tous droits reserves.
        </p>
        <div className="flex gap-6">
          <a
            href="#"
            className="text-xs text-muted transition-colors hover:text-dark"
          >
            Politique de confidentialite
          </a>
          <a
            href="#"
            className="text-xs text-muted transition-colors hover:text-dark"
          >
            Mentions legales
          </a>
        </div>
      </div>
    </footer>
  );
}

// ------------------------------------------------------------------
// Page
// ------------------------------------------------------------------
export default function LandingPage() {
  return (
    <div className="min-h-screen bg-cream">
      <Nav />
      <Hero />
      <Features />
      <Process />
      <Comparison />
      <CtaSection />
      <Footer />
    </div>
  );
}
