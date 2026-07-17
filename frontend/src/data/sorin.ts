export type SorinOfferingKind = "service" | "product";

export type SorinOffering = {
  id: string;
  title: string;
  shortTitle: string;
  kind: SorinOfferingKind;
  category: string;
  summary: string;
  description: string;
  scope: string[];
  deliverables: string[];
  journey: string[];
  measures: string[];
  technologies: string[];
  accent: string;
};

export type SorinCategory = {
  id: string;
  index: string;
  title: string;
  shortTitle: string;
  summary: string;
  accent: string;
  offerings: SorinOffering[];
};

const service = (
  category: string,
  accent: string,
  offering: Omit<SorinOffering, "kind" | "category" | "accent">,
): SorinOffering => ({ ...offering, kind: "service", category, accent });

const product = (
  category: string,
  accent: string,
  offering: Omit<SorinOffering, "kind" | "category" | "accent">,
): SorinOffering => ({ ...offering, kind: "product", category, accent });

export const sorinCategories: SorinCategory[] = [
  {
    id: "assessment-roadmap",
    index: "01",
    title: "ارزیابی، بلوغ و نقشه‌راه",
    shortTitle: "ارزیابی و نقشه‌راه",
    summary: "شروع از شواهد واقعی، شناخت شکاف‌ها و تبدیل آن‌ها به برنامه اجرایی قابل سنجش.",
    accent: "#22b8b5",
    offerings: [
      service("ارزیابی، بلوغ و نقشه‌راه", "#22b8b5", {
        id: "soc-assessment",
        title: "ارزیابی جامع مرکز عملیات امنیت",
        shortTitle: "SOC Assessment",
        summary: "ارزیابی شواهد‌محور حاکمیت، افراد، فرآیند، فناوری، داده، تشخیص، اتوماسیون و شاخص‌ها.",
        description: "سورین وضعیت موجود SOC را فقط با پرسش‌نامه امتیازدهی نمی‌کند. مصاحبه، معماری، داشبورد، لاگ، یوزکیس، تیکت و گزارش رخداد بررسی می‌شوند تا تصویر قابل دفاعی از بلوغ فعلی، ریسک‌های غالب و اولویت‌های سرمایه‌گذاری شکل بگیرد.",
        scope: ["حاکمیت، منشور SOC، SLA/KPI و RACI", "نقش‌ها، شیفت، ظرفیت و مهارت تیم", "کیفیت داده، پوشش لاگ و آمادگی CIM", "پوشش MITRE ATT&CK، کیفیت Rule و False Positive", "آمادگی SOAR، Playbook و پاسخ به رخداد"],
        deliverables: ["داشبورد بلوغ و Executive Scorecard", "ماتریس پوشش منابع داده و ATT&CK", "دفتر ثبت شواهد و شکاف‌های فنی", "Backlog آماده Jira با اولویت ۳۰/۹۰/۱۸۰ روز", "نقشه‌راه ۱۲ و ۲۴ ماهه"],
        journey: ["تعریف دامنه و ذی‌نفعان", "جمع‌آوری شواهد و مصاحبه", "امتیازدهی و تحلیل ریشه شکاف", "اولویت‌بندی ریسک و Quick Win", "تحویل Roadmap و Service Charter"],
        measures: ["پوشش لاگ و Crown Jewel", "نرخ FP و Ruleهای بازبینی‌شده", "MTTD/MTTR و نقض SLA", "Playbookهای تست‌شده", "سن بلوغ هر دامنه"],
        technologies: ["Splunk ES", "Elastic", "MITRE ATT&CK", "Jira", "Confluence"],
      }),
      service("ارزیابی، بلوغ و نقشه‌راه", "#22b8b5", {
        id: "ir-readiness",
        title: "ارزیابی آمادگی پاسخ به رخداد",
        shortTitle: "IR Readiness",
        summary: "سنجش آمادگی واقعی سازمان برای تصمیم‌گیری، مهار و بازیابی در شرایط حادثه.",
        description: "مسیرهای تماس، سطح اختیار، شواهد موردنیاز، Playbookها، آمادگی فارنزیک و هماهنگی میان SOC، زیرساخت، حقوقی و مدیریت بررسی می‌شوند. هدف، تبدیل سندهای ایستا به یک مدل عملیاتی قابل تمرین است.",
        scope: ["ساختار CSIRT و زنجیره فرماندهی", "Escalation و کانال‌های ارتباطی", "آمادگی Endpoint، Network و Memory Forensics", "سناریوهای باج‌افزار، حساب نفوذشده و نشت داده"],
        deliverables: ["IR Plan و Contact Matrix", "Playbookهای اولویت‌دار", "جدول اختیار و Approval Gate", "برنامه Tabletop و آزمون بازیابی"],
        journey: ["مرور رخدادهای گذشته", "بررسی اسناد و دسترسی‌ها", "اجرای Tabletop", "ثبت شکاف‌ها", "Retest آمادگی"],
        measures: ["زمان فعال‌سازی Incident Bridge", "زمان تصمیم مهار", "درصد تماس‌های اعتبارسنجی‌شده", "پوشش سناریوهای اولویت‌دار"],
        technologies: ["EDR", "SIEM", "SOAR", "Jira", "Forensic Tooling"],
      }),
    ],
  },
  {
    id: "engineering-integration",
    index: "02",
    title: "مهندسی، یکپارچه‌سازی و تشخیص",
    shortTitle: "مهندسی و تشخیص",
    summary: "ساخت زیرساخت داده و محتوای تشخیص پایدار؛ از معماری Splunk تا Detection Factory.",
    accent: "#4d8dff",
    offerings: [
      service("مهندسی، یکپارچه‌سازی و تشخیص", "#4d8dff", {
        id: "siem-splunk-engineering",
        title: "معماری و مهندسی Splunk Enterprise Security",
        shortTitle: "Splunk / SIEM Engineering",
        summary: "طراحی HLD/LLD، جمع‌آوری داده، CIM، Data Model، ES و قابلیت اطمینان عملیاتی.",
        description: "سورین لایه‌های Collection، Indexing، Search و Enterprise Security را متناسب با حجم، Retention، دسترس‌پذیری و سناریوهای تشخیص طراحی و پیاده‌سازی می‌کند. هر منبع داده دارای مالک، Data Contract، معیار پذیرش و Health Search خواهد بود.",
        scope: ["Index Strategy، Sizing و معماری توزیع‌شده", "Forwarder، Syslog، HEC و API Integration", "Parsing، Field Extraction و CIM Mapping", "Data Model Acceleration و ES Content", "Performance، License و Retention Optimization"],
        deliverables: ["HLD/LLD و نقشه جریان داده", "Data Source Plan و Data Contract", "داشبورد سلامت و Freshness", "CIM/Data Model Mapping", "گزارش UAT و انتقال دانش"],
        journey: ["Discovery و Capacity Planning", "طراحی معماری", "Onboarding و نرمال‌سازی", "فعال‌سازی ES و Content", "UAT، Tune و Handover"],
        measures: ["Latency کمتر از SLA", "Parsing و CIM Coverage", "Skipped Search و Data Loss", "License Utilization", "Source Freshness"],
        technologies: ["Splunk Enterprise", "Splunk ES", "CIM", "ESCU", "UBA", "HEC"],
      }),
      service("مهندسی، یکپارچه‌سازی و تشخیص", "#4d8dff", {
        id: "detection-factory",
        title: "Detection Factory، RBA و مهندسی یوزکیس",
        shortTitle: "Detection Factory",
        summary: "تبدیل رفتار مهاجم به تشخیص‌های تست‌شده، دارای مالک، قابل Tune و قابل اندازه‌گیری.",
        description: "هر تشخیص در سورین یک دارایی عملیاتی است، نه صرفاً یک Query. مدل تهدید، وابستگی داده، SPL، Risk Score، تست، Runbook، مالک و تاریخ بازبینی در یک Detection Card ثبت می‌شود تا چرخه عمر Rule قابل نگهداری باشد.",
        scope: ["Threat Modeling و ATT&CK Mapping", "Correlation Search و Risk-Based Alerting", "Identity/Endpoint/Network Use Case", "Ransomware، Phishing و Privileged Abuse", "Hypervisor، Storage و Backup Detection"],
        deliverables: ["Detection Specification و SPL", "Risk Model و Analytic Story", "Triage Runbook و SOAR Enrichment", "Test Evidence و Tuning Note", "Jira Workflow و Confluence Article"],
        journey: ["Threat Model", "Data Check", "Build و Risk Scoring", "Atomic/Purple Test", "Deploy، Tune و Review"],
        measures: ["True/False Positive Rate", "ATT&CK و Data-Source Coverage", "Rule Review Age", "Performance Cost", "Analyst Acceptance"],
        technologies: ["Splunk SPL", "RBA", "UEBA", "MITRE ATT&CK", "Atomic Red Team"],
      }),
      service("مهندسی، یکپارچه‌سازی و تشخیص", "#4d8dff", {
        id: "soar-case-management",
        title: "مهندسی SOAR و مدیریت Case",
        shortTitle: "SOAR & Case Management",
        summary: "غنی‌سازی، تصمیم و پاسخ کنترل‌شده همراه با Evidence، Approval، Rollback و Audit Trail.",
        description: "اتوماسیون از Runbook دستی تا Bounded Autonomy به‌صورت مرحله‌ای توسعه پیدا می‌کند. اتصال SIEM، EDR، Threat Intelligence، Vulnerability، Jira و Confluence باعث می‌شود هر Case شواهد، مالک، اقدام اصلاحی و Lesson Learned مشخص داشته باشد.",
        scope: ["Enrichment دارایی، هویت، IOC و آسیب‌پذیری", "Playbookهای Phishing و Compromised Account", "Host Isolation، Token Revocation و Block", "Error Path، Approval Gate و Rollback", "Jira/Confluence Operating Model"],
        deliverables: ["Playbook Design و Connector Setup", "Test Case و Error Handling", "Jira Issue Types و Workflow", "Runbook/KB Catalogue", "گزارش منفعت اتوماسیون"],
        journey: ["انتخاب Use Case", "طراحی Runbook", "پیاده‌سازی Connector", "Test و Approval", "پایش و بهبود"],
        measures: ["زمان صرفه‌جویی‌شده", "Automation Success Rate", "Playbook Failure Rate", "زمان Enrichment", "درصد Caseهای مستند"],
        technologies: ["SOAR", "n8n", "Jira", "Confluence", "EDR", "TIP"],
      }),
    ],
  },
  {
    id: "managed-operations",
    index: "03",
    title: "عملیات مدیریت‌شده SOC، MSSP و MDR",
    shortTitle: "عملیات مدیریت‌شده",
    summary: "پایش، تریاژ، تحقیق، Escalation و گزارش‌دهی مبتنی بر SLA به‌صورت ۲۴×۷ یا منعطف.",
    accent: "#18c6d8",
    offerings: [
      service("عملیات مدیریت‌شده SOC، MSSP و MDR", "#18c6d8", {
        id: "managed-soc",
        title: "SOC / MSSP / MDR مدیریت‌شده",
        shortTitle: "Managed SOC 24×7",
        summary: "عملیات چندسطحی L1/L2/L3 برای کشف، تریاژ، تحقیق، Escalation و پاسخ هدایت‌شده.",
        description: "تیم سورین سلامت SIEM و سنسورها را پایش می‌کند، هشدارها را با زمینه دارایی و هویت غنی می‌سازد، Timeline می‌سازد و Case را تا تعیین مالک و اقدام پیگیری می‌کند. مدل خدمت می‌تواند ۲۴×۷ یا ۵×۸، از راه دور یا ترکیبی باشد.",
        scope: ["پایش SIEM، EDR و سلامت منابع داده", "Triage اولیه و کاهش Noise", "تحقیق T2/T3 و Timeline", "Escalation تلفنی/Jira طبق شدت", "بهبود پیوسته Use Case"],
        deliverables: ["Shift Handover و گزارش روزانه", "Incident Ticket همراه Evidence", "گزارش هفتگی Tuning و Backlog", "گزارش ماهانه KPI و ریسک", "Quarterly Business Review"],
        journey: ["Alert Intake", "Context و Evidence Pivot", "تصمیم TP/FP/Benign/Gap", "Escalation و Action", "Closure و Lesson Learned"],
        measures: ["Median Time to Triage", "MTTD/MTTR", "SLA Breach", "Backlog Age", "Noise Ratio"],
        technologies: ["Splunk ES", "EDR/NDR", "SOAR", "Jira", "Threat Intelligence"],
      }),
      service("عملیات مدیریت‌شده SOC، MSSP و MDR", "#18c6d8", {
        id: "telemetry-assurance",
        title: "تضمین کیفیت داده و سلامت Telemetry",
        shortTitle: "Telemetry Assurance",
        summary: "پایش Freshness، Parsing، CIM، حجم، Time Sync و Integrity منابع داده.",
        description: "جمع‌آوری همه لاگ‌ها به‌تنهایی بلوغ نیست. هر منبع باید Use Case، مالک، هزینه، Retention و معیار پذیرش داشته باشد. سورین شکاف داده را به اثر مستقیم آن بر پوشش تشخیص و ریسک کسب‌وکار متصل می‌کند.",
        scope: ["Freshness و Latency", "Parsing و Required Field", "CIM/Data Model Coverage", "Volume Baseline و Anomaly", "Duplicate، Loss و Time Sync"],
        deliverables: ["Source Inventory", "Health Search و Dashboard", "Data Quality Incident", "Monthly Quality Report", "Corrective Action و ETA"],
        journey: ["Baseline", "Health Monitoring", "SLA Violation", "Root Cause", "Corrective Action"],
        measures: ["Source Availability", "Null Field Rate", "CIM Compliance", "Event Loss", "Correction Lead Time"],
        technologies: ["Splunk Monitoring Console", "CIM", "Data Models", "Jira"],
      }),
      service("عملیات مدیریت‌شده SOC، MSSP و MDR", "#18c6d8", {
        id: "reporting-improvement",
        title: "گزارش مدیریتی و بهبود مستمر",
        shortTitle: "Reporting & QBR",
        summary: "تبدیل فعالیت روزمره SOC به تصمیم: چه ریسکی افزایش یافته، چه اقدامی لازم است و مالک آن کیست.",
        description: "مدل گزارش‌دهی سورین از Shift Report تا QBR را پوشش می‌دهد. تمرکز بر شمارش Alert نیست؛ روند ریسک، کیفیت تشخیص، وضعیت SLA، پوشش ATT&CK و تصمیم‌های باز مدیریت نمایش داده می‌شود.",
        scope: ["Daily/Shift Operational Report", "Weekly Noise & Tuning Board", "Monthly KPI و Risk Trend", "Quarterly Roadmap Review", "Post-Incident Report"],
        deliverables: ["Executive Dashboard", "KPI Pack", "Top Risk Register", "Improvement Backlog", "QBR Presentation"],
        journey: ["Collect", "Validate", "Trend", "Decide", "Track"],
        measures: ["Top Risk Trend", "Detection Quality", "Coverage Improvement", "Action Closure Rate", "SLA Trend"],
        technologies: ["Splunk Dashboards", "Jira", "Confluence", "BI"],
      }),
    ],
  },
  {
    id: "hunt-response-validation",
    index: "04",
    title: "شکار تهدید، پاسخ و اعتبارسنجی",
    shortTitle: "شکار و پاسخ",
    summary: "کشف فعال تهدید، مهار قابل دفاع و آزمون مستمر اثربخشی کنترل‌ها.",
    accent: "#9478ff",
    offerings: [
      service("شکار تهدید، پاسخ و اعتبارسنجی", "#9478ff", {
        id: "managed-hunting",
        title: "شکار تهدید مدیریت‌شده",
        shortTitle: "Managed Threat Hunting",
        summary: "Hunt فرضیه‌محور، Intelligence-led و Crown-Jewel برای کشف فعالیت‌های پنهان.",
        description: "تیم شکار سورین با فرضیه‌ای مشخص و داده موردنیاز شروع می‌کند، جست‌وجو و Timeline را می‌سازد و خروجی را به Detection جدید، Data Gap و اقدام قابل پیگیری تبدیل می‌کند. Hunt بدون Backlog بهبود، کامل محسوب نمی‌شود.",
        scope: ["Hypothesis/Intelligence/Anomaly-led Hunt", "Retrospective و Incident-led Hunt", "Domain Controller، PKI و PAM", "VMware/ESXi، SAN/NAS و Backup", "Identity Abuse Path و Crown Jewel"],
        deliverables: ["Hunt Hypothesis و SPL Pack", "Evidence Timeline", "ATT&CK Mapping", "Detection Proposal", "Jira Action و Hunt Report"],
        journey: ["Hypothesis Workshop", "Data Validation", "Search Execution", "Evidence Review", "Detection و Backlog Follow-up"],
        measures: ["Hypothesis Coverage", "New Detection Yield", "Data Gap Closure", "Dwell-time Insight", "Backlog Closure"],
        technologies: ["Splunk", "EDR", "NDR", "MITRE ATT&CK", "Threat Intelligence"],
      }),
      service("شکار تهدید، پاسخ و اعتبارسنجی", "#9478ff", {
        id: "csirt-forensics",
        title: "CSIRT، پاسخ به رخداد و فارنزیک",
        shortTitle: "Incident Response",
        summary: "آمادگی، تحلیل، مهار، پاکسازی، بازیابی و یادگیری همراه با حفظ زنجیره شواهد.",
        description: "سورین از فعال‌سازی Incident Bridge و تعیین دامنه تا توصیه مهار، تحلیل ریشه، بازیابی امن و Post-Incident Review کنار سازمان می‌ماند. اقدامات حساس با Approval Gate و هماهنگی مالک کسب‌وکار انجام می‌شوند.",
        scope: ["Endpoint/Network/Memory Forensics", "Timeline و Adversary Path", "Containment Recommendation", "Root Cause و Remediation", "Recovery Validation"],
        deliverables: ["Incident Timeline", "Forensic Evidence Register", "Containment و Recovery Plan", "RCA Report", "Lessons Learned Backlog"],
        journey: ["Prepare", "Detect & Analyze", "Contain", "Eradicate", "Recover و Learn"],
        measures: ["Time to Scope", "Containment Decision Time", "Evidence Completeness", "Recovery Validation", "Repeat-Incident Rate"],
        technologies: ["EDR", "PCAP/Flow", "SIEM", "Forensic Tooling", "Jira"],
      }),
      service("شکار تهدید، پاسخ و اعتبارسنجی", "#9478ff", {
        id: "purple-team",
        title: "Purple Team و اعتبارسنجی مستمر",
        shortTitle: "Purple Team",
        summary: "شبیه‌سازی مهاجم، مشاهده عملکرد SOC، اندازه‌گیری و تبدیل نتیجه آزمون به بهبود واقعی.",
        description: "Atomic Test، Replay داده و سناریوهای تهدید برای سنجش Telemetry، Rule، Triage و Playbook اجرا می‌شوند. هر تمرین باید شکاف، مالک، اقدام اصلاحی و Retest داشته باشد؛ گزارش به‌تنهایی خروجی کافی نیست.",
        scope: ["Detection Validation", "Threat Actor Emulation", "SOAR Error Path و Rollback", "Ransomware/Recovery Tabletop", "Hypervisor و Storage Exercise"],
        deliverables: ["Test Plan و Evidence", "MTTD/MTTR Observation", "Coverage Gap", "Improvement Backlog", "Retest Report"],
        journey: ["Plan", "Execute", "Observe", "Measure", "Improve و Retest"],
        measures: ["Detection Rate", "Time to Triage", "Playbook Success", "Gap Closure", "Retest Pass Rate"],
        technologies: ["Atomic Red Team", "Purple Team Tooling", "SIEM", "SOAR", "EDR"],
      }),
    ],
  },
  {
    id: "products-enablement",
    index: "05",
    title: "محصولات و توانمندسازی سورین",
    shortTitle: "محصولات سورین",
    summary: "محصولات بومی برای دید دارایی، اطلاعات تهدید، اشتراک هشدار و توسعه توان انسانی.",
    accent: "#f4b44b",
    offerings: [
      product("محصولات و توانمندسازی سورین", "#f4b44b", {
        id: "soorin-asset-intelligence",
        title: "Soorin Asset Intelligence",
        shortTitle: "Asset Intelligence",
        summary: "کشف فعال و غیرفعال دارایی، Asset–User Graph، Rogue Asset و Context عملیاتی برای SOC.",
        description: "یک مخزن متمرکز و به‌روز از تجهیزات، کاربران، سیستم‌عامل‌ها، سرویس‌ها، پورت‌ها و ارتباطات شبکه. محصول با Passive/Active Discovery، SNMP و LDAP داده‌ها را هم‌بسته می‌کند و برای RBA، مدیریت آسیب‌پذیری و پاسخ به رخداد Context قابل اعتماد می‌سازد.",
        scope: ["Passive و Active Scan بدون Agent", "OS Fingerprinting و Service/Port Discovery", "LDAP/Active Directory و User–Asset Relation", "ML Anomaly و Long-Lived Connection", "Relationship Graph و Rogue Asset"],
        deliverables: ["Asset Inventory متمرکز", "داشبورد User/OS/Service/Port", "Asset Relationship Graph", "API برای SIEM/SOC", "گزارش تغییر و ناهنجاری"],
        journey: ["Scope و Sensor Design", "Discovery Integration", "Correlation و Validation", "Dashboard و Graph", "Operational Handover"],
        measures: ["Unknown Asset Reduction", "Inventory Freshness", "Discovery Coverage", "Context Completeness", "Unauthorized Change Detection"],
        technologies: ["Passive Sensor", "Active Scan", "SNMP", "LDAP/AD", "REST API", "ML"],
      }),
      product("محصولات و توانمندسازی سورین", "#f4b44b", {
        id: "soorin-threat-intelligence",
        title: "Soorin Threat Intelligence",
        shortTitle: "Threat Intelligence",
        summary: "مدیریت IOC/IOA و TTP، غنی‌سازی، Retro Hunt و اتصال مستقیم به Splunk و Elastic.",
        description: "پلتفرم اطلاعات تهدید سورین داده‌های تهدید را جمع‌آوری، هم‌بسته و قابل اقدام می‌کند. Dashboard لحظه‌ای، مدیریت TTP، تعریف Rule و IOC Correlation به تیم SOC کمک می‌کند کمپین و تهدید مرتبط را سریع‌تر تشخیص دهد.",
        scope: ["IOC/IOA و Feed Management", "Real-time Threat Visibility", "TTP و MITRE ATT&CK", "Rule Definition و Scheduling", "Historical Search و IOC Correlation"],
        deliverables: ["Threat Dashboard", "Curated Feed", "IOC/TTP Catalogue", "SIEM Integration", "Campaign/Actor Context"],
        journey: ["Connect Sources", "Normalize و Enrich", "Score و Correlate", "Publish to SIEM", "Retro Hunt و Tune"],
        measures: ["Feed Freshness", "Relevant IOC Rate", "Correlation Hit", "False Positive Rate", "Time to Operationalize"],
        technologies: ["Splunk", "Elastic", "STIX/TAXII", "MITRE ATT&CK", "REST API"],
      }),
      product("محصولات و توانمندسازی سورین", "#f4b44b", {
        id: "soorin-alert-sharing",
        title: "Soorin Alert Sharing",
        shortTitle: "Alert Sharing",
        summary: "اشتراک کنترل‌شده هشدار و رخداد با نهادهای همکار در قالب‌های استاندارد IODEF و STIX.",
        description: "Alert Sharing گزارش رخداد را از SIEM دریافت، به قالب استاندارد تبدیل و برای گیرندگان مجاز ارسال می‌کند. تاریخچه، سطح شدت، ATT&CK، وضعیت تکمیل، محدودیت IP و مدیریت مقصد، تبادل قابل ممیزی و سریع را فراهم می‌سازند.",
        scope: ["SIEM Information و Initial Log", "Automatic IODEF/STIX Maker", "Recipient و Node Management", "IP Allowlist و Access Control", "History، Severity و Completion Dashboard"],
        deliverables: ["Sharing Workflow", "Standardized Incident Package", "Recipient Registry", "Audit History", "Operational Dashboard"],
        journey: ["Connect to SIEM", "Map Fields", "Preview & Confirm", "Secure Delivery", "Track Completion"],
        measures: ["Sharing Lead Time", "Delivery Success", "Format Compliance", "Recipient Acknowledgement", "Audit Completeness"],
        technologies: ["IODEF", "STIX", "SIEM API", "Microservices", "Docker", "Redis"],
      }),
      product("محصولات و توانمندسازی سورین", "#f4b44b", {
        id: "soorin-attack-detection",
        title: "Soorin Attack Detection",
        shortTitle: "Attack Detection",
        summary: "کشف و تحلیل حملات با هم‌بستگی داده، رفتار و قواعد تشخیص قابل تنظیم.",
        description: "محصول Attack Detection برای شناسایی سناریوهای حمله و رفتارهای مشکوک طراحی شده است و با Context دارایی و اطلاعات تهدید، هشدارهای قابل‌تحقیق‌تر برای تیم SOC تولید می‌کند.",
        scope: ["Behavior و Rule-based Detection", "Asset/TI Enrichment", "Attack Scenario Correlation", "Severity و Risk Prioritization", "SIEM/SOC Integration"],
        deliverables: ["Detection Catalogue", "Attack Dashboard", "Risk-ranked Alert", "Integration Connector", "Tuning Baseline"],
        journey: ["Onboard Telemetry", "Activate Detection Pack", "Baseline", "Tune", "Operate"],
        measures: ["Detection Precision", "Noise Reduction", "Coverage", "Triage Speed", "Rule Health"],
        technologies: ["SIEM", "Detection Engine", "Threat Intelligence", "Asset Context"],
      }),
      product("محصولات و توانمندسازی سورین", "#f4b44b", {
        id: "sector-seconline",
        title: "SECTOR و آزمایشگاه SecOnline",
        shortTitle: "SECTOR / SecOnline",
        summary: "آموزش تعاملی، کمپین آگاهی‌رسانی، آزمون، گواهی و آزمایشگاه آماده سناریوهای دفاع سایبری.",
        description: "SECTOR محتوای گام‌به‌گام، آزمون، رتبه‌بندی و گزارش ریسک انسانی را ارائه می‌کند. SecOnline نیز محیط آزمایشگاهی تحت وب با سیستم‌عامل، ابزار و سرویس‌های آماده است تا تمرین‌های SOC/CERT بدون هزینه ساخت آزمایشگاه فیزیکی اجرا شوند.",
        scope: ["Interactive Learning Path", "Awareness Campaign و Phishing", "Quiz، Certificate و Skill Ranking", "Browser-based Cyber Lab", "Scenario و Lab Isolation"],
        deliverables: ["Learning Programme", "Campaign Dashboard", "Assessment Report", "Lab Scenario", "Certificate و Skill Matrix"],
        journey: ["Assess Audience", "Assign Path", "Learn و Practice", "Test", "Measure و Improve"],
        measures: ["Completion Rate", "Assessment Score", "Risky Behavior Trend", "Lab Success", "Skill Improvement"],
        technologies: ["SECTOR", "SecOnline", "Web Lab", "LMS", "Simulation"],
      }),
    ],
  },
];

export const sorinOfferings = sorinCategories.flatMap((category) => category.offerings);
