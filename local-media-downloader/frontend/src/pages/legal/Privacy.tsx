import { LegalPage, LegalSection } from "./LegalPage";
import { useTranslation } from "react-i18next";

export default function Privacy() {
  const { i18n } = useTranslation();
  const ar = i18n.resolvedLanguage === "ar";
  if (ar) return (
    <LegalPage title="سياسة الخصوصية">
      <LegalSection heading="البيانات التي نجمعها"><p>نجمع بيانات الحساب، وحالة الفوترة من معالج الدفع، وسجلات الاستخدام اللازمة لتطبيق حدود الخطط وتشغيل الخدمة بأمان.</p></LegalSection>
      <LegalSection heading="كيفية استخدامها"><p>نستخدم البيانات لتشغيل حسابك، وتقديم التنزيلات، ومنع إساءة الاستخدام، ومعالجة الاشتراكات، وإرسال رسائل التحقق وإعادة تعيين كلمة المرور والخدمة.</p></LegalSection>
      <LegalSection heading="الوسائط والمدفوعات"><p>تُخزّن ملفات الوسائط مؤقتاً ثم تُحذف وفق سياسة الاحتفاظ. لا نرسل روابط الوسائط أو عناوينها إلى مزود تحليلات. تتولى Paddle بيانات البطاقة ولا تمر عبر خوادمنا.</p></LegalSection>
      <LegalSection heading="خياراتك"><p>يمكنك طلب حذف حسابك والبيانات المرتبطة به عبر قناة الدعم المنشورة للخدمة، مع مراعاة السجلات التي يجب الاحتفاظ بها قانونياً أو لمنع الاحتيال.</p></LegalSection>
    </LegalPage>
  );
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
        <p>Downloaded media is temporary and removed under our retention policy. You can request deletion of your account and associated data through the service's published support channel, subject to records we must retain for legal or fraud-prevention purposes.</p>
      </LegalSection>
    </LegalPage>
  );
}
