export type SorinOfferingKind = "service" | "product";

export type SorinOffering = {
  id: string;
  title: string;
  shortTitle: string;
  kind: SorinOfferingKind;
  category: string;
  summary: string;
  description: string;
  outcomes: string[];
  accent: string;
};

export type SorinCategory = {
  id: string;
  title: string;
  shortTitle: string;
  summary: string;
  accent: string;
  offerings: SorinOffering[];
};

// The copy is centralized so approved company content can be updated without
// touching the visualization component.
export const sorinCategories: SorinCategory[] = [
  {
    id: "security-operations",
    title: "عملیات و پایش امنیت",
    shortTitle: "عملیات امنیت",
    summary: "کشف، تحلیل و پاسخ ساختاریافته به رخدادهای امنیتی.",
    accent: "#35d0ba",
    offerings: [
      {
        id: "soc-mdr", title: "مرکز عملیات امنیت و MDR", shortTitle: "SOC و MDR", kind: "service",
        category: "عملیات و پایش امنیت", accent: "#35d0ba",
        summary: "پایش مستمر، اولویت‌بندی هشدارها و هدایت پاسخ به رخداد.",
        description: "سورین داده‌های امنیتی را از منابع مختلف گردآوری و هم‌بسته می‌کند تا تیم‌های دفاعی بتوانند روی هشدارهای مهم تمرکز کنند و رخدادها را با یک فرایند روشن از کشف تا مهار پیش ببرند.",
        outcomes: ["کاهش زمان تشخیص و پاسخ", "تریاژ و اولویت‌بندی هشدارها", "گزارش مدیریتی و فنی قابل پیگیری"],
      },
      {
        id: "incident-response", title: "پاسخ به رخداد و جرم‌یابی دیجیتال", shortTitle: "پاسخ به رخداد", kind: "service",
        category: "عملیات و پایش امنیت", accent: "#35d0ba",
        summary: "مهار رخداد، حفظ شواهد و بازگردانی امن سرویس‌ها.",
        description: "در زمان رخداد، تیم پاسخ با تمرکز بر حفظ شواهد، تحلیل دامنه نفوذ، مهار تهدید و تدوین اقدامات اصلاحی به سازمان کمک می‌کند چرخه حادثه را کنترل کند.",
        outcomes: ["برنامه واکنش قابل اجرا", "تحلیل ریشه رخداد", "درس‌آموخته و برنامه اصلاحی"],
      },
    ],
  },
  {
    id: "threat-intelligence",
    title: "اطلاعات و شکار تهدید",
    shortTitle: "اطلاعات تهدید",
    summary: "تبدیل داده‌های پراکنده تهدید به تصمیم عملیاتی.",
    accent: "#6ea8ff",
    offerings: [
      {
        id: "threat-intel", title: "اطلاعات تهدید سایبری", shortTitle: "Threat Intelligence", kind: "service",
        category: "اطلاعات و شکار تهدید", accent: "#6ea8ff",
        summary: "جمع‌آوری، غنی‌سازی و تحلیل شاخص‌های تهدید مرتبط با کسب‌وکار.",
        description: "داده‌های منابع باز و داخلی پالایش، امتیازدهی و با دارایی‌های سازمان مرتبط می‌شوند تا خروجی اطلاعات تهدید مستقیماً در کشف و تصمیم‌گیری امنیتی قابل استفاده باشد.",
        outcomes: ["خوراک IoC قابل اعتماد", "پروفایل تهدیدهای مرتبط", "گزارش روندها و کمپین‌ها"],
      },
      {
        id: "threat-hunting", title: "شکار پیش‌دستانه تهدید", shortTitle: "Threat Hunting", kind: "service",
        category: "اطلاعات و شکار تهدید", accent: "#6ea8ff",
        summary: "جست‌وجوی فرضیه‌محور برای فعالیت‌های پنهان مهاجم.",
        description: "با استفاده از فرضیه‌های مبتنی بر ریسک، تله‌متری سازمان و چارچوب MITRE ATT&CK، نشانه‌هایی بررسی می‌شوند که ممکن است از کنترل‌های خودکار عبور کرده باشند.",
        outcomes: ["فرضیه‌های قابل تکرار", "افزایش پوشش تشخیص", "کشف شکاف‌های تله‌متری"],
      },
    ],
  },
  {
    id: "assessment",
    title: "ارزیابی و بهبود امنیت",
    shortTitle: "ارزیابی امنیت",
    summary: "شناخت واقع‌بینانه سطح حمله و اولویت‌بندی اصلاحات.",
    accent: "#bc8cff",
    offerings: [
      {
        id: "penetration-testing", title: "تست نفوذ و ارزیابی آسیب‌پذیری", shortTitle: "تست نفوذ", kind: "service",
        category: "ارزیابی و بهبود امنیت", accent: "#bc8cff",
        summary: "ارزیابی کنترل‌شده شبکه، وب، API و زیرساخت.",
        description: "ارزیابی با سناریوهای متناسب با سطح ریسک انجام می‌شود و یافته‌ها همراه با شواهد، اثر کسب‌وکاری و راهکار اصلاحی اولویت‌بندی‌شده تحویل داده می‌شوند.",
        outcomes: ["یافته‌های قابل بازتولید", "اولویت‌بندی مبتنی بر ریسک", "آزمون مجدد اصلاحات"],
      },
      {
        id: "security-architecture", title: "معماری و بلوغ امنیت", shortTitle: "معماری امنیت", kind: "service",
        category: "ارزیابی و بهبود امنیت", accent: "#bc8cff",
        summary: "طراحی نقشه راه امنیت متناسب با فناوری و اهداف سازمان.",
        description: "وضعیت موجود کنترل‌ها، فرایندها و معماری بررسی می‌شود تا یک نقشه راه مرحله‌ای، قابل سنجش و هم‌راستا با ریسک‌های واقعی سازمان شکل بگیرد.",
        outcomes: ["معماری هدف", "نقشه راه اجرایی", "شاخص‌های سنجش بلوغ"],
      },
    ],
  },
  {
    id: "products-automation",
    title: "محصولات و اتوماسیون",
    shortTitle: "محصولات سورین",
    summary: "ابزارهایی برای یکپارچه‌سازی دانش، داده و گردش‌کار امنیتی.",
    accent: "#ffb45c",
    offerings: [
      {
        id: "soc-workbench", title: "محصول SOC Workbench", shortTitle: "SOC Workbench", kind: "product",
        category: "محصولات و اتوماسیون", accent: "#ffb45c",
        summary: "فضای کار یکپارچه تحلیل‌گر برای اسناد، IoC، پروژه و گزارش.",
        description: "SOC Workbench داده‌ها و مستندات تحقیق را در یک محیط self-hosted کنار هم قرار می‌دهد و با پردازش اسناد، مخزن IoC، گزارش‌سازی و تحلیل کمک‌گرفته از هوش مصنوعی، کار روزمره تحلیل‌گر را منسجم می‌کند.",
        outcomes: ["دانش متمرکز تحقیق", "گردش‌کار سریع‌تر تحلیل", "کنترل محلی داده‌های حساس"],
      },
      {
        id: "security-automation", title: "اتوماسیون گردش‌کار امنیتی", shortTitle: "Security Automation", kind: "product",
        category: "محصولات و اتوماسیون", accent: "#ffb45c",
        summary: "اتصال منابع، غنی‌سازی داده و اجرای خودکار وظایف تکراری.",
        description: "گردش‌کارهای قابل تنظیم، جمع‌آوری داده، غنی‌سازی شاخص‌ها، اعلان و ثبت خروجی را به هم متصل می‌کنند تا زمان تحلیل‌گر صرف تصمیم‌های مهم‌تر شود.",
        outcomes: ["کاهش کار دستی", "فرایندهای قابل ممیزی", "یکپارچگی با ابزارهای موجود"],
      },
    ],
  },
];

export const sorinOfferings = sorinCategories.flatMap((category) => category.offerings);
