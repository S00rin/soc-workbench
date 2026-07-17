import { useState } from "react";
import SorinGraph from "../components/SorinGraph";
import { sorinCategories, sorinOfferings } from "../data/sorin";
import type { SorinOffering } from "../data/sorin";
import "./AboutSorin.css";

export default function AboutSorin() {
  const [selected, setSelected] = useState<SorinOffering>(sorinOfferings[0]);

  const selectOffering = (offering: SorinOffering) => {
    setSelected(offering);
    if (window.matchMedia("(max-width: 900px)").matches) {
      requestAnimationFrame(() => document.getElementById("sorin-detail")?.scrollIntoView({ behavior: "smooth" }));
    }
  };

  return (
    <div className="sorin-page" dir="rtl" lang="fa">
      <section className="sorin-hero">
        <div className="sorin-hero-copy">
          <span className="sorin-eyebrow">S00RIN · CYBER DEFENSE</span>
          <h1>امنیت، وقتی معنا پیدا می‌کند که به تصمیم تبدیل شود.</h1>
          <p>
            سورین مجموعه‌ای متمرکز بر امنیت سایبری است؛ جایی که تخصص انسانی، اطلاعات تهدید و
            اتوماسیون کنار هم قرار می‌گیرند تا تیم‌های امنیتی سریع‌تر ببینند، دقیق‌تر تحلیل کنند
            و با اطمینان پاسخ دهند.
          </p>
          <div className="sorin-principles" aria-label="رویکردهای سورین">
            <span>دفاع داده‌محور</span>
            <span>طراحی انسان‌محور</span>
            <span>کنترل محلی داده</span>
          </div>
        </div>
        <div className="sorin-signal" aria-hidden="true">
          <span className="signal-ring ring-a" />
          <span className="signal-ring ring-b" />
          <span className="signal-core">S</span>
          <span className="signal-label">SECURITY<br />IN MOTION</span>
        </div>
      </section>

      <section className="sorin-intro">
        <div>
          <span className="section-kicker">نقشه توانمندی‌ها</span>
          <h2>خدمات و محصولات سورین را کشف کنید</h2>
        </div>
        <p>روی هر گره انتهایی کلیک کنید تا شرح، ارزش و خروجی آن را ببینید.</p>
      </section>

      <section className="sorin-explorer">
        <div className="sorin-map-panel">
          <div className="sorin-map-legend" aria-label="راهنمای گراف">
            <span><i className="legend-dot service" /> خدمت</span>
            <span><i className="legend-dot product" /> محصول</span>
            <span className="legend-hint">تمام مسیرها در یک نگاه</span>
          </div>
          <SorinGraph categories={sorinCategories} selectedId={selected.id} onSelect={selectOffering} />
        </div>

        <aside className="sorin-detail" id="sorin-detail" aria-live="polite">
          <div className="detail-accent" style={{ background: selected.accent }} />
          <div className="detail-meta">
            <span className={`offering-kind ${selected.kind}`}>
              {selected.kind === "product" ? "محصول سورین" : "خدمت تخصصی"}
            </span>
            <span>{selected.category}</span>
          </div>
          <h2>{selected.title}</h2>
          <p className="detail-lead">{selected.summary}</p>
          <p className="detail-body">{selected.description}</p>
          <div className="detail-outcomes">
            <h3>خروجی‌های کلیدی</h3>
            <ul>{selected.outcomes.map((outcome) => <li key={outcome}>{outcome}</li>)}</ul>
          </div>
          <div className="detail-index">
            {sorinOfferings.map((offering, index) => (
              <button
                key={offering.id}
                className={offering.id === selected.id ? "active" : ""}
                onClick={() => selectOffering(offering)}
                aria-label={`مشاهده ${offering.title}`}
              >
                {String(index + 1).padStart(2, "0")}
              </button>
            ))}
          </div>
        </aside>
      </section>

      <section className="sorin-footer-note">
        <span>یک تصویر واحد از ریسک تا پاسخ</span>
        <p>توانمندی‌های سورین مستقل نیستند؛ هر بخش، داده و زمینه لازم برای بخش بعدی را کامل می‌کند.</p>
      </section>
    </div>
  );
}
