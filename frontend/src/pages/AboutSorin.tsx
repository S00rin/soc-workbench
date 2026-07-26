import { useMemo, useState } from "react";
import "@fontsource-variable/vazirmatn/wght.css";
import SorinGraph from "../components/SorinGraph";
import { sorinCategories, sorinOfferings } from "../data/sorin";
import type { SorinCategory, SorinOffering } from "../data/sorin";
import "./AboutSorin.css";

type DetailTab = "scope" | "deliverables" | "journey" | "measures";

const detailTabs: Array<{ id: DetailTab; label: string }> = [
  { id: "scope", label: "دامنه خدمت" },
  { id: "deliverables", label: "تحویل‌دادنی‌ها" },
  { id: "journey", label: "مسیر اجرا" },
  { id: "measures", label: "شاخص‌های سنجش" },
];

const engagementModels = [
  {
    title: "Foundation",
    subtitle: "ساخت پایه قابل اتکا",
    text: "برای سازمانی که به ارزیابی، معماری هدف، کنترل کیفیت داده و آماده‌سازی تیم و فرآیند نیاز دارد.",
  },
  {
    title: "Advanced",
    subtitle: "توسعه و بهبود ظرفیت دفاع",
    text: "برای توسعه Detection Factory، مهندسی SOAR، شکار تهدید و سنجش اثربخشی کنترل‌ها.",
  },
  {
    title: "Elite",
    subtitle: "عملیات مدیریت‌شده و مستمر",
    text: "برای پایش ۲۴×۷، MDR، پاسخ به رخداد، گزارش مدیریتی و چرخه بهبود مبتنی بر SLA و KPI.",
  },
];

export default function AboutSorin() {
  const [selectedCategory, setSelectedCategory] = useState<SorinCategory>(sorinCategories[0]);
  const [selected, setSelected] = useState<SorinOffering>(sorinCategories[0].offerings[0]);
  const [detailTab, setDetailTab] = useState<DetailTab>("scope");

  const detailItems = useMemo(() => selected[detailTab], [detailTab, selected]);

  const selectCategory = (category: SorinCategory) => {
    setSelectedCategory(category);
    setSelected(category.offerings[0]);
    setDetailTab("scope");
  };

  const selectOffering = (offering: SorinOffering) => {
    setSelected(offering);
    setDetailTab("scope");
    if (window.matchMedia("(max-width: 860px)").matches) {
      requestAnimationFrame(() => document.getElementById("sorin-detail")?.scrollIntoView({ behavior: "smooth" }));
    }
  };

  return (
    <div className="sorin-page" dir="rtl" lang="fa">
      <section className="sorin-hero">
        <div className="sorin-hero-copy">
          <span className="sorin-eyebrow">امنیت به‌صرفه، کارآمد و آگاهانه</span>
          <h1>از داده خام تا دفاع سایبری قابل مدیریت</h1>
          <p>
            سورین، شرکت دانش‌بنیان دفاع سایبری تأسیس‌شده در سال ۱۳۹۶، به سازمان‌ها کمک می‌کند مرکز عملیات امنیت را
            ارزیابی، مهندسی، راهبری و به‌طور مستمر بهبود دهند؛ از معماری و کیفیت داده تا تشخیص، شکار تهدید، پاسخ به رخداد
            و محصولات بومی امنیتی.
          </p>
          <div className="sorin-hero-tags" aria-label="حوزه‌های فعالیت سورین">
            <span>تأسیس ۱۳۹۶</span>
            <span>SOC · MSSP · MDR</span>
            <span>عملیات ۲۴×۷</span>
          </div>
        </div>

        <div className="sorin-lifecycle" aria-label="چرخه خدمات سورین">
          <div className="lifecycle-core"><strong>S</strong><span>SOORIN</span></div>
          <div className="lifecycle-step step-1"><b>01</b><span>ارزیابی</span></div>
          <div className="lifecycle-step step-2"><b>02</b><span>مهندسی</span></div>
          <div className="lifecycle-step step-3"><b>03</b><span>عملیات</span></div>
          <div className="lifecycle-step step-4"><b>04</b><span>بهبود</span></div>
        </div>
      </section>

      <section className="sorin-facts" aria-label="خلاصه توانمندی‌های سورین">
        <div><strong>۵</strong><span>خانواده خدمت</span></div>
        <div><strong>{sorinOfferings.length}</strong><span>خدمت و محصول</span></div>
        <div><strong>۴</strong><span>گام چرخه دفاع</span></div>
        <div className="facts-note"><small>مدل ارائه</small><span>Assess · Engineer · Operate · Improve</span></div>
      </section>

      <section className="sorin-section-head">
        <div>
          <span className="section-kicker">سبد خدمات و محصولات</span>
          <h2>مسیر مناسب سازمان خود را پیدا کنید</h2>
        </div>
        <p>ابتدا یک خانواده را از نمودار انتخاب کنید؛ سپس برای دیدن شرح کامل، روی خدمت یا محصول موردنظر بزنید.</p>
      </section>

      <section className="sorin-portfolio">
        <div className="sorin-map-panel">
          <div className="panel-heading">
            <div><span>نقشه توانمندی‌ها</span><strong>{selectedCategory.title}</strong></div>
            <small>{selectedCategory.index} / 05</small>
          </div>
          <SorinGraph
            categories={sorinCategories}
            selectedCategoryId={selectedCategory.id}
            onSelectCategory={selectCategory}
          />
          <div className="category-switcher" aria-label="انتخاب خانواده خدمات">
            {sorinCategories.map((category) => (
              <button
                key={category.id}
                className={category.id === selectedCategory.id ? "active" : ""}
                style={{ "--category-accent": category.accent } as React.CSSProperties}
                onClick={() => selectCategory(category)}
              >
                <b>{category.index}</b><span>{category.shortTitle}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="sorin-offering-panel">
          <div className="offering-panel-intro">
            <span>{selectedCategory.index}</span>
            <div>
              <h3>{selectedCategory.title}</h3>
              <p>{selectedCategory.summary}</p>
            </div>
          </div>
          <div className="offering-list">
            {selectedCategory.offerings.map((offering) => (
              <button
                key={offering.id}
                className={offering.id === selected.id ? "active" : ""}
                style={{ "--offering-accent": offering.accent } as React.CSSProperties}
                onClick={() => selectOffering(offering)}
                aria-pressed={offering.id === selected.id}
              >
                <span className={`offering-type ${offering.kind}`}>
                  {offering.kind === "product" ? "محصول" : "خدمت"}
                </span>
                <strong>{offering.title}</strong>
                <p>{offering.summary}</p>
                <i aria-hidden="true">←</i>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="sorin-detail" id="sorin-detail" aria-live="polite">
        <div className="detail-header">
          <div className="detail-title-wrap">
            <span className={`detail-kind ${selected.kind}`}>
              {selected.kind === "product" ? "محصول سورین" : "خدمت تخصصی"}
            </span>
            <span className="detail-category">{selected.category}</span>
            <h2>{selected.title}</h2>
            <p className="detail-lead">{selected.summary}</p>
          </div>
          <div className="detail-number">{String(sorinOfferings.findIndex((item) => item.id === selected.id) + 1).padStart(2, "0")}</div>
        </div>

        <p className="detail-description">{selected.description}</p>

        <div className="detail-technologies" aria-label="فناوری‌ها و چارچوب‌های مرتبط">
          <span>فناوری و چارچوب</span>
          <div>{selected.technologies.map((technology) => <i key={technology}>{technology}</i>)}</div>
        </div>

        <div className="detail-tabs" role="tablist" aria-label="جزئیات خدمت">
          {detailTabs.map((tab) => (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              role="tab"
              aria-selected={detailTab === tab.id}
              aria-controls="sorin-detail-panel"
              className={detailTab === tab.id ? "active" : ""}
              onClick={() => setDetailTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div
          className={`detail-tab-panel ${detailTab === "journey" ? "journey" : ""}`}
          id="sorin-detail-panel"
          role="tabpanel"
          aria-labelledby={`tab-${detailTab}`}
        >
          {detailItems.map((item, index) => (
            <div key={item}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{item}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="sorin-evidence">
        <div className="evidence-copy">
          <span className="section-kicker">نمونه تجربه تحویلی مستند</span>
          <h2>تجربه در مقیاس عملیاتی واقعی</h2>
          <p>اعداد زیر مربوط به یک نمونه پروژه SOC ثبت‌شده در گزارش تحویل سورین هستند، نه ادعای تجمیعی همه پروژه‌ها.</p>
        </div>
        <div className="evidence-metrics">
          <div><strong>۱.۲ TB</strong><span>داده روزانه</span></div>
          <div><strong>+۷۰۰</strong><span>دارایی تحت پوشش</span></div>
          <div><strong>+۱۴۰۰</strong><span>یوزکیس پیاده‌سازی‌شده</span></div>
          <div><strong>۲۴×۷</strong><span>پایش و عملیات</span></div>
        </div>
      </section>

      <section className="sorin-engagement">
        <div className="sorin-section-head compact">
          <div><span className="section-kicker">مدل همکاری</span><h2>از ساخت زیربنا تا عملیات مدیریت‌شده</h2></div>
        </div>
        <div className="engagement-grid">
          {engagementModels.map((model, index) => (
            <article key={model.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{model.title}</h3>
              <strong>{model.subtitle}</strong>
              <p>{model.text}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
