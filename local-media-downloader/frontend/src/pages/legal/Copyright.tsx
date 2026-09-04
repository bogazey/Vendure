import { LegalPage, LegalSection } from "./LegalPage";

export default function Copyright() {
  return (
    <LegalPage title="Copyright Policy">
      <LegalSection heading="Authorized use only">
        <p>
          This service is intended only for downloading content you own or are otherwise authorized to access and
          download - for example, your own uploads, content licensed to you, or content whose source platform and
          rights holder permit downloading. It does not support and will not add support for circumventing DRM,
          bypassing paywalls, or accessing private or restricted content without authorization.
        </p>
      </LegalSection>
      <LegalSection heading="Your responsibility">
        <p>
          You are responsible for ensuring your use of downloaded content complies with applicable copyright law and
          the terms of the platform it came from.
        </p>
      </LegalSection>
      <LegalSection heading="Reporting a copyright concern">
        <p>
          If you believe this service is being used to infringe your copyright, contact us with details of the
          content and your claim. (Placeholder - a dedicated contact channel and formal takedown process will be
          published here before this product is publicly available.)
        </p>
      </LegalSection>
    </LegalPage>
  );
}
