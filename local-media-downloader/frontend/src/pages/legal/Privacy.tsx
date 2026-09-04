import { LegalPage, LegalSection } from "./LegalPage";

export default function Privacy() {
  return (
    <LegalPage title="Privacy Policy">
      <LegalSection heading="What we collect">
        <p>
          Account information (email address, hashed password), billing status from our payment processor, and
          usage records needed to enforce plan limits (such as download counts and credits used). We do not send the
          URLs or titles of content you download to any third-party analytics provider.
        </p>
      </LegalSection>
      <LegalSection heading="How we use it">
        <p>
          To operate your account, enforce plan limits fairly, process payments through our payment processor, and
          communicate service-related emails (verification, password reset, billing notices).
        </p>
      </LegalSection>
      <LegalSection heading="Payment data">
        <p>
          Card details are handled entirely by our payment processor (Paddle) and never pass through or are stored
          on our servers.
        </p>
      </LegalSection>
      <LegalSection heading="Data retention">
        <p>You can request deletion of your account and associated data by contacting us.</p>
      </LegalSection>
    </LegalPage>
  );
}
