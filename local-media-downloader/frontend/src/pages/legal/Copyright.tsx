import { LegalPage, LegalSection } from "./LegalPage";
import { useTranslation } from "react-i18next";

export default function Copyright() {
  const { i18n } = useTranslation();
  const ar = i18n.resolvedLanguage === "ar";
  if (ar) return (
    <LegalPage title="سياسة حقوق النشر">
      <LegalSection heading="الاستخدام المصرّح به فقط"><p>استخدم Loady فقط مع المحتوى الذي تملكه أو لديك إذن بتنزيله. لا تدعم الخدمة تجاوز الحماية أو الوصول إلى محتوى خاص أو مقيّد دون تصريح.</p></LegalSection>
      <LegalSection heading="مسؤوليتك"><p>أنت مسؤول عن الامتثال لقانون حقوق النشر وشروط المنصة المصدر عند تنزيل المحتوى واستخدامه.</p></LegalSection>
      <LegalSection heading="الإبلاغ عن مشكلة"><p>يمكن لصاحب الحقوق إرسال تفاصيل المحتوى والحقوق والطلب عبر قناة الدعم المنشورة للخدمة. سنراجع الطلبات المكتملة ونتخذ الإجراء المناسب.</p></LegalSection>
    </LegalPage>
  );
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
          Rights holders can submit the content location, identification of the protected work, contact details,
          and a good-faith statement through the service's published support channel. We will review complete
          notices and take appropriate action.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
