import { LegalPage, LegalSection } from "./LegalPage";

export default function Terms() {
  return (
    <LegalPage title="Terms of Service">
      <LegalSection heading="What this service is">
        <p>
          This service is a media utility for importing, saving, converting, organizing, and processing media that
          you own or are otherwise authorized to access and download. It is not a tool for accessing content you
          don't have the rights to, and it is not marketed or intended as a way to bypass copy protection, DRM, or
          paywalls.
        </p>
      </LegalSection>
      <LegalSection heading="Your responsibilities">
        <p>
          You are solely responsible for making sure you have the legal right to download and use any content you
          process through this service, including compliance with the terms of service of the platform the content
          comes from and applicable copyright law in your jurisdiction.
        </p>
      </LegalSection>
      <LegalSection heading="No rights granted to third-party content">
        <p>
          Using this service does not grant you any rights to content owned by others. We do not claim ownership of,
          and grant no license to, any media you download using this service.
        </p>
      </LegalSection>
      <LegalSection heading="Prohibited use">
        <p>
          You may not use this service to circumvent digital rights management (DRM), bypass paywalls or
          authentication systems, or access private or restricted content you are not authorized to view.
        </p>
      </LegalSection>
      <LegalSection heading="Plans and billing">
        <p>
          Paid plans are billed in advance on a monthly or annual cadence through our payment processor. You can
          change or cancel your plan at any time from the Billing page; changes take effect as described there.
        </p>
      </LegalSection>
      <LegalSection heading="Changes">
        <p>We may update these terms from time to time. Continued use of the service after a change constitutes acceptance of the updated terms.</p>
      </LegalSection>
    </LegalPage>
  );
}
