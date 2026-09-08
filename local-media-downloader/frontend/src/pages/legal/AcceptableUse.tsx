import { useTranslation } from "react-i18next";
import { LegalPage, LegalSection } from "./LegalPage";

export default function AcceptableUse() {
  const { i18n } = useTranslation();
  const ar = i18n.resolvedLanguage === "ar";
  return (
    <LegalPage title={ar ? "سياسة الاستخدام المقبول" : "Acceptable Use Policy"}>
      <LegalSection heading={ar ? "الاستخدام المسموح" : "Permitted use"}>
        <p>{ar ? "استخدم Loady فقط مع الوسائط التي تملكها أو لديك إذن قانوني للوصول إليها وتنزيلها ومعالجتها." : "Use Loady only with media you own or have lawful permission to access, download, and process."}</p>
      </LegalSection>
      <LegalSection heading={ar ? "الاستخدام المحظور" : "Prohibited use"}>
        <p>{ar ? "لا تستخدم الخدمة لانتهاك حقوق النشر، أو تجاوز إدارة الحقوق الرقمية أو أنظمة الدفع أو المصادقة، أو الوصول إلى محتوى خاص، أو توزيع برمجيات ضارة، أو إساءة استخدام موارد الخدمة." : "Do not use the service to infringe copyright, bypass DRM, paywalls or authentication, access private content, distribute malware, or abuse service resources."}</p>
      </LegalSection>
      <LegalSection heading={ar ? "حماية الخدمة" : "Protecting the service"}>
        <p>{ar ? "يجوز لنا تقييد أو تعليق الاستخدام الذي يهدد أمان الخدمة أو توفرها، أو ينتهك هذه السياسة أو القانون المعمول به." : "We may restrict or suspend activity that threatens service security or availability, or violates this policy or applicable law."}</p>
      </LegalSection>
    </LegalPage>
  );
}
