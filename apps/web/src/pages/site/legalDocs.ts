/**
 * Legal documents. TEMPLATES FOR LEGAL REVIEW — they describe how Resora actually works (what is stored, which
 * providers are used, how billing and refunds work) but must be reviewed by a qualified lawyer for your company and
 * jurisdictions before launch. Legal text is published in English; the English version governs.
 * Replace the placeholders in [brackets] (company name, address, contact e-mail, governing law).
 */
export type LegalSection = { heading: string; body: string[] };
export type LegalDoc = { slug: string; docTitle: string; updated: string; summary: string; sections: LegalSection[] };

/** Shown under every legal document until a lawyer has reviewed it (English only, like the documents). */
export const LEGAL_REVIEW_NOTE = "Template for legal review";

const UPDATED = "2026-11-15";

export const LEGAL_DOCS: LegalDoc[] = [
  {
    slug: "privacy",
    docTitle: "Privacy Policy",
    updated: UPDATED,
    summary: "What Resora collects, why, how long it is kept, who processes it, and the choices you have.",
    sections: [
      { heading: "Who we are", body: ["Resora is operated by [Company name], [address] (\"we\"). Contact: [privacy contact e-mail]. Where the GDPR or UK GDPR applies, we are the controller for account data and the processor for content you upload as part of a team or institution plan."] },
      { heading: "What we collect", body: [
        "Account data: your account identifier, display name and, if you give it, your e-mail address.",
        "Content you add: searches, papers you save, notes, highlights, uploaded PDFs, drafts, comments and team projects.",
        "Usage and billing: credits used per feature, plan, invoices and payment status. Card details are handled by the payment provider and never reach our servers.",
        "Website analytics: page views counted without cookies, without storing IP addresses, using a daily-rotating anonymous hash. Do Not Track and Global Privacy Control signals are honoured.",
      ] },
      { heading: "Why we use it", body: [
        "To provide the service you asked for (contract), to keep it secure and prevent abuse (legitimate interest), to bill you (contract and legal obligation), and to send product e-mails only when you opted in (consent).",
      ] },
      { heading: "AI processing", body: [
        "To summarise, translate, answer questions or read papers aloud, the relevant text is sent to the AI model selected by our AI Router. We use only providers and settings that do not train on your content, or models we host ourselves. Neural voices for listening run on our own servers.",
      ] },
      { heading: "Sharing", body: [
        "We share data only with processors who help us run Resora (hosting, database, payment provider, e-mail delivery, AI providers as described above), under data-processing agreements, and when the law requires it. We do not sell personal data.",
      ] },
      { heading: "Retention", body: [
        "Account and content data are kept while your account is active and deleted within 30 days after you delete the account, except invoices, which we must keep for [7] years. Raw analytics are aggregated after [90] days.",
      ] },
      { heading: "Your rights", body: [
        "You can access, correct, export or delete your data, object to or restrict processing, and withdraw consent at any time. Contact [privacy contact e-mail]. You may also complain to your data-protection authority.",
      ] },
      { heading: "International transfers", body: ["Where data leaves your region, we rely on adequacy decisions or Standard Contractual Clauses. [List hosting regions.]"] },
      { heading: "Children", body: ["Resora is not directed at children under 16. We do not knowingly collect their data."] },
      { heading: "Changes", body: ["We will announce material changes in the app and by e-mail where we have your address, at least 14 days before they take effect."] },
    ],
  },
  {
    slug: "terms",
    docTitle: "Terms of Service",
    updated: UPDATED,
    summary: "The agreement between you and Resora when you use the service.",
    sections: [
      { heading: "The service", body: ["Resora helps you find, read, compare, listen to and write about research. Features and limits depend on your plan, as shown on the Pricing page."] },
      { heading: "Your account", body: ["Keep your sign-in secure and tell us about unauthorised use. You are responsible for activity on your account. Team owners and admins manage who belongs to their team."] },
      { heading: "Your content", body: ["You keep all rights to content you upload or write. You give us the limited permission needed to store, process and display it to provide the service. Do not upload content you have no right to share."] },
      { heading: "AI output", body: ["Summaries, translations, answers and drafts are generated with AI and may contain mistakes. Resora shows its sources so you can check them. You are responsible for how you use the output, including academic-integrity rules of your institution."] },
      { heading: "Plans, credits and payment", body: ["Paid plans renew automatically until cancelled. Upgrades take effect immediately with a prorated charge; downgrades and cancellations take effect at the end of the paid period. Credits reset on the windows shown in the app; purchased credit packs do not expire while your account exists. Prices may change with 30 days' notice."] },
      { heading: "Acceptable use", body: ["You agree to the Acceptable Use Policy. We may suspend accounts that break it, after notice where reasonable."] },
      { heading: "Availability", body: ["We aim for high availability and publish incidents on the Status page, but the service is provided \"as is\" without a guaranteed uptime unless your contract says otherwise."] },
      { heading: "Liability", body: ["To the extent the law allows, our total liability is limited to the amount you paid us in the 12 months before the claim. Nothing limits liability that cannot be limited by law."] },
      { heading: "Ending the agreement", body: ["You can delete your account at any time. We may end the agreement for serious or repeated breaches. Sections that by their nature should survive (content ownership, liability, governing law) survive."] },
      { heading: "Governing law", body: ["These terms are governed by the laws of [jurisdiction]; courts of [venue] have jurisdiction, subject to mandatory consumer law where you live."] },
    ],
  },
  {
    slug: "cookies",
    docTitle: "Cookie Policy",
    updated: UPDATED,
    summary: "Resora uses no advertising or tracking cookies.",
    sections: [
      { heading: "What we store in your browser", body: [
        "Strictly necessary storage: your sign-in session, interface language, theme, reading and listening position, and the choice you made in the cookie notice. These are needed for the features you use and do not require consent.",
        "We do not use advertising, cross-site tracking or third-party analytics cookies. Our website analytics are cookieless (see the Privacy Policy).",
      ] },
      { heading: "Your choices", body: ["You can clear site data in your browser at any time; you will be signed out and preferences will reset. The cookie notice can be reopened from the footer of the website."] },
    ],
  },
  {
    slug: "acceptable-use",
    docTitle: "Acceptable Use Policy",
    updated: UPDATED,
    summary: "What you may not do with Resora.",
    sections: [
      { heading: "Do not", body: [
        "Break the law, infringe copyright or upload material you are not allowed to share.",
        "Attempt to access other people's accounts or data, probe or disrupt the service, or bypass credits, limits or security.",
        "Use automated means to scrape Resora or resell access without a written agreement.",
        "Use Resora to produce work you present as your own where your institution forbids AI assistance.",
        "Generate harassment, hateful content, malware or content that endangers people.",
      ] },
      { heading: "Enforcement", body: ["We may remove content, limit features or suspend accounts that break this policy, and will tell you why unless the law or safety prevents it. You can appeal through the Contact page."] },
    ],
  },
  {
    slug: "refunds",
    docTitle: "Refund Policy",
    updated: UPDATED,
    summary: "How refunds work for subscriptions and credit packs.",
    sections: [
      { heading: "Free trials", body: ["Trials are free. Cancel before the trial ends and you will not be charged."] },
      { heading: "Subscriptions", body: ["You can cancel at any time; your plan stays active until the end of the paid period. If you were charged for a renewal you did not intend, contact us within 14 days and we will refund it if you have not used paid features since the renewal."] },
      { heading: "Credit packs", body: ["Unused credit packs can be refunded within 14 days of purchase. Partly used packs are refunded for the unused share."] },
      { heading: "Consumer rights", body: ["Nothing here limits rights you have under consumer law where you live, including statutory withdrawal rights."] },
      { heading: "How to ask", body: ["Use the Contact page with the topic \"Billing\" and your invoice number."] },
    ],
  },
  {
    slug: "dpa",
    docTitle: "Data Processing Agreement (template)",
    updated: UPDATED,
    summary: "For teams and institutions that need a DPA under GDPR / UK GDPR.",
    sections: [
      { heading: "Parties and scope", body: ["This DPA applies when Resora processes personal data on behalf of a customer (\"Controller\") on a Team or Institution plan. Resora acts as \"Processor\"."] },
      { heading: "Processing details", body: ["Subject matter: providing the Resora service. Duration: the term of the subscription. Data subjects: the customer's members. Categories: account data, content uploaded by members, usage data. No special-category data is intended."] },
      { heading: "Processor obligations", body: ["Process only on documented instructions; ensure staff confidentiality; apply appropriate technical and organisational measures (encryption in transit, access control, audit logs, backups); assist with data-subject requests; notify personal-data breaches without undue delay and within 48 hours."] },
      { heading: "Sub-processors", body: ["The current list is available on request at [link]. We give 30 days' notice of new sub-processors; the customer may object."] },
      { heading: "Deletion and audits", body: ["At the end of the service we delete or return customer data within 30 days. We make available information needed to demonstrate compliance and allow audits with reasonable notice."] },
    ],
  },
];

export function legalDoc(slug: string | undefined) {
  return LEGAL_DOCS.find((doc) => doc.slug === slug) || null;
}
