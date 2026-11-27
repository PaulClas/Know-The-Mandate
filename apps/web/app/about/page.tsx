import type { Metadata } from "next";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DEFINITION } from "@/lib/site";

export const metadata: Metadata = {
  title: "About KYM: what it is, its philosophy, risks and critics",
  description: `${DEFINITION} Read the principles, the risks the authors disclose, and twelve critic objections with where the critics are right.`,
  alternates: { canonical: "/about" },
};

const REPO = "https://github.com/PaulClas/Know-The-Mandate/blob/main";

const FAQ: [string, string][] = [
  ["What is KYM?", DEFINITION],
  ["How is KYM different from OAuth and Rich Authorization Requests?", "OAuth/RAR is the carrier; KYM supplies the state and the per-request decision. A static grant cannot track cumulative budgets, instant mandate revocation, single-use approvals or delegation lineage. In the project's red-team comparison, scopes plus static RAR stopped 3 of 10 applicable attacks, while KYM blocked 22 of 22 applicable attacks."],
  ["Does a valid access token authorize a payment in KYM?", "No. A valid token is only technical permission. The mandate is checked on every request, so a valid token with payments.initiate is still denied for a beneficiary the mandate does not permit."],
  ["Can KYM stop an AI agent from making mistakes?", "No. It limits damage to what the mandate allows. A wrong action that stays inside the mandate is allowed and cannot be detected by mandate enforcement; this is a documented, tested limitation."],
  ["Who made KYM and how do I ask a question?", "KYM is an independent project by Paul Clas, a machine learning developer (not a bank, payments-security or legal professional). Questions, critiques and offers to review the design are welcome at clas.paul@gmail.com or as GitHub issues."],
  ["Is KYM a standard, compliant or production-ready?", "No. The vocabulary, controlled language and authorization-details type are experimental proposals. The demo uses synthetic data and sandbox security, claims no compliance or certification, and has not been externally audited."],
  ["Is the evidence ledger a blockchain?", "No. It is a signed, hash-chained, append-only log with signed checkpoints. It is tamper-evident, not tamper-proof."],
];

const PRINCIPLES = [
  "Authority is not identity and not permission: they are kept apart.",
  "The agent proposes, the mandate authorizes, the bank enforces, the ledger remembers: no component authorizes itself.",
  "Enforce observable facts, not intentions: the bank need not know whether the agent hallucinated or was injected.",
  "Deny by default: ontologies explain and validate; they never decide.",
  "Authority only attenuates when delegated; revoking a parent disables its children.",
  "Evidence must be checkable by someone who does not trust the bank (with pinned keys); it does not decide liability.",
  "Humans approve exact operations, once; approval never widens a mandate.",
  "Honesty is a feature: simulated things are labelled and gaps are published.",
];

const RISKS = [
  "Approval fatigue and consent theatre; customers misreading mandates.",
  "Overly broad mandates; false sense of security; in-mandate harm.",
  "Insider abuse by bank operators; compromised hosts and plaintext demo keys.",
  "Coverage gaps when payments bypass the account-holding bank; standards absorbing the idea.",
  "Legal non-recognition; blame-shifting through consent receipts.",
  "No external audit or real-world pilot: the project is self-assessed.",
];

export default function AboutPage() {
  const ld = [
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      name: "KYM (Know Your Mandate)",
      alternateName: ["Know Your Mandate"],
      description: DEFINITION,
      applicationCategory: "Financial technology; authorization; AI agent governance",
      operatingSystem: "Any (Python 3.12+, Node 20+)",
      codeRepository: "https://github.com/PaulClas/Know-The-Mandate",
      softwareVersion: "0.1.0",
      isAccessibleForFree: true,
      author: { "@type": "Person", name: "Paul Clas" },
    },
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: FAQ.map(([q, a]) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
    },
  ];
  return (
    <article className="max-w-3xl space-y-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld).replace(/</g, "\\u003c") }} />
      <header>
        <h1 className="text-xl font-semibold">About KYM — Know Your Mandate</h1>
        <p className="mt-2 text-[14px]">{DEFINITION}</p>
        <p className="mt-2 text-xs text-muted">Experimental, synthetic-data proof of concept. Not compliant, certified or legal advice. Not related to “Know Your Meme”. Last updated 2026-11-26.</p>
      </header>

      <Card>
        <CardHeader title="Frequently asked questions" />
        <CardBody className="space-y-4">
          {FAQ.map(([q, a]) => (
            <section key={q}>
              <h2 className="text-[14px] font-semibold">{q}</h2>
              <p className="text-[13px]">{a}</p>
            </section>
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Philosophy" description="Why KYM is built this way" />
        <CardBody>
          <ol className="list-decimal space-y-1 pl-5 text-[13px]">{PRINCIPLES.map((p) => <li key={p}>{p}</li>)}</ol>
          <p className="mt-3 text-[13px]">Full argument with twelve steelmanned critic objections and where each critic is right: <a className="text-accent underline" href={`${REPO}/docs/philosophy/README.md`}>docs/philosophy</a>.</p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Risks the authors disclose" description="Not exhaustive; see the register" />
        <CardBody>
          <ul className="list-disc space-y-1 pl-5 text-[13px]">{RISKS.map((r) => <li key={r}>{r}</li>)}</ul>
          <p className="mt-3 text-[13px]">
            <a className="text-accent underline" href={`${REPO}/docs/risk/risk-register.md`}>Risk register</a> · <a className="text-accent underline" href={`${REPO}/docs/security/security-review.md`}>Security review</a> · <a className="text-accent underline" href="/proof">Run the attacks yourself</a> · <a className="text-accent underline" href="/llms.txt">llms.txt</a>
          </p>
        </CardBody>
      </Card>
    </article>
  );
}
