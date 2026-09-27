import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy · SPREV Acquisition Engine",
  description: "How the SPREV Acquisition Engine handles data and Gmail access.",
};

// Public page (excluded from the site password in proxy.ts) so Google's OAuth
// consent screen can link to it.
export default function Privacy() {
  return (
    <div className="wrap" style={{ maxWidth: 760, paddingBlock: 40 }}>
      <h1 style={{ fontSize: 26, marginBottom: 4 }}>Privacy Policy</h1>
      <p style={{ color: "var(--muted)", marginTop: 0 }}>SPREV Acquisition Engine · SP Real Estate Ventures, LLC · Last updated September 27, 2026</p>

      <h2 style={{ fontSize: 17, marginTop: 28 }}>What this app is</h2>
      <p>The SPREV Acquisition Engine is a private, internal tool used by SP Real Estate Ventures, LLC to analyze residential
        properties in New Jersey and prepare purchase offers. It is not offered to the public, and access requires a password.</p>

      <h2 style={{ fontSize: 17, marginTop: 28 }}>Google account access</h2>
      <p>The app requests one Google permission: <b>gmail.send</b> (&ldquo;Send email on your behalf&rdquo;). It uses that permission only to send
        offer letters that a signed-in team member has reviewed, approved and confirmed, to the recipient that person entered.
        The app cannot read, search, modify or delete any email, contacts, files or other Google account data.</p>
      <p>The authorization token is stored as a server configuration secret, is not shared with anyone, and can be revoked at any
        time at <a href="https://myaccount.google.com/permissions" style={{ color: "var(--accent)" }}>myaccount.google.com/permissions</a>.</p>
      <p>The app&apos;s use of information received from Google APIs adheres to the{" "}
        <a href="https://developers.google.com/terms/api-services-user-data-policy" style={{ color: "var(--accent)" }}>Google API Services User Data Policy</a>,
        including the Limited Use requirements.</p>

      <h2 style={{ fontSize: 17, marginTop: 28 }}>Data the app stores</h2>
      <p>For each analysis: the property address, public property and market data from third-party providers (such as RentCast
        and the U.S. Census Bureau), the calculated underwriting results, and, for approved offers, the letter text, the
        recipient&apos;s email address, who approved it, and the Gmail message ID and time it was sent. This data is used only to run
        the business and keep a record of offers. It is not sold, shared for advertising, or used to train AI models.</p>

      <h2 style={{ fontSize: 17, marginTop: 28 }}>Contact</h2>
      <p>Questions or deletion requests: klpshustle@gmail.com.</p>
    </div>
  );
}
