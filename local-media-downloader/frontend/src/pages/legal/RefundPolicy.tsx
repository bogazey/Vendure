import { useTranslation } from "react-i18next";
import { LegalPage, LegalSection } from "./LegalPage";

export default function RefundPolicy() {
  const { i18n } = useTranslation();
  const ar = i18n.resolvedLanguage === "ar";
  return (
    <LegalPage title={ar ? "سياسة الفوترة والاسترداد" : "Billing & Refund Policy"}>
      <LegalSection heading={ar ? "الاشتراكات" : "Subscriptions"}>
        <p>{ar ? "تُحصّل الاشتراكات المدفوعة مقدماً كل شهر أو سنة بواسطة Paddle. تظهر الأسعار والفترة والمبلغ الإجمالي قبل تأكيد الدفع." : "Paid subscriptions are charged in advance monthly or annually by Paddle. The price, billing interval, and total are shown before payment is confirmed."}</p>
      </LegalSection>
      <LegalSection heading={ar ? "الإلغاء وتغيير الخطة" : "Cancellation and plan changes"}>
        <p>{ar ? "يمكنك إدارة خطتك من صفحة الفوترة. يسري الإلغاء في نهاية الفترة الحالية ما لم توضّح شاشة الفوترة خلاف ذلك." : "You can manage your plan from Billing. Cancellation takes effect at the end of the current period unless the billing screen states otherwise."}</p>
      </LegalSection>
      <LegalSection heading={ar ? "طلبات الاسترداد" : "Refund requests"}>
        <p>
          {ar ? (
            <>
              تخضع طلبات الاسترداد للقانون المعمول به وشروط Paddle وظروف عملية الشراء. تواصل معنا عبر البريد
              الإلكتروني{" "}
              <a href="mailto:support@loady.cc" dir="ltr" className="font-medium text-brand-aqua transition-colors hover:text-brand-purple">
                support@loady.cc
              </a>{" "}
              مع معرّف المعاملة؛ ولا ترسل بيانات البطاقة.
            </>
          ) : (
            <>
              Refund requests are assessed under applicable law, Paddle&apos;s terms, and the circumstances of the
              purchase. Contact us at{" "}
              <a href="mailto:support@loady.cc" className="font-medium text-brand-aqua transition-colors hover:text-brand-purple">
                support@loady.cc
              </a>{" "}
              with the transaction ID; never send card details.
            </>
          )}
        </p>
      </LegalSection>
    </LegalPage>
  );
}
