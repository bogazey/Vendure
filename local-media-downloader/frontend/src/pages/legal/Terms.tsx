import { LegalPage, LegalSection } from "./LegalPage";
import { useTranslation } from "react-i18next";

export default function Terms() {
  const { i18n } = useTranslation();
  const ar = i18n.resolvedLanguage === "ar";
  if (ar) return (
    <LegalPage title="شروط الخدمة">
      <LegalSection heading="الخدمة"><p>Loady أداة لاستيراد وحفظ وتحويل ومعالجة الوسائط التي تملكها أو لديك تصريح بتنزيلها. لا تمنحك الخدمة حقوقاً في محتوى الغير.</p></LegalSection>
      <LegalSection heading="مسؤولياتك"><p>أنت مسؤول عن امتلاك الحقوق أو الأذونات اللازمة وعن الالتزام بالقانون وشروط المنصة المصدر.</p></LegalSection>
      <LegalSection heading="الاستخدام المحظور"><p>يُحظر تجاوز إدارة الحقوق الرقمية أو أنظمة الدفع أو المصادقة، والوصول غير المصرح به إلى المحتوى الخاص، وإساءة استخدام الخدمة أو الإضرار بها.</p></LegalSection>
      <LegalSection heading="الخطط والفوترة"><p>تُدفع الخطط المدفوعة مقدماً شهرياً أو سنوياً عبر Paddle. يمكنك إدارة التغيير أو الإلغاء من صفحة الفوترة وفق الشروط المعروضة هناك.</p></LegalSection>
      <LegalSection heading="التوفر والتغييرات"><p>قد تتغير المنصات الخارجية أو تتوقف عن العمل. قد نحدّث الخدمة أو هذه الشروط، وسننشر النسخة المحدّثة وتاريخ سريانها.</p></LegalSection>
    </LegalPage>
  );
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
