"""Multi-language (English/Farsi) user and admin help guides (Module 16).

Guides are plain rows in the database so an admin can edit or add to them at
runtime; `seed_default_guides` only inserts the built-in starter set the
first time each (slug, language) pair is missing, so it never overwrites an
admin's edits on a later restart.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.help import HelpGuide

# (slug, audience, category, order_index, title_en, content_en, title_fa, content_fa)
_GUIDES: list[tuple[str, str, str, int, str, str, str, str]] = [
    (
        "getting-started", "user", "Getting Started", 0,
        "Getting started with Soorin SOC Workbench",
        """Soorin SOC Workbench is a single workspace for processing evidence,
tracking indicators, running investigations and generating reports.

## Signing in
Use the username and password your administrator gave you. If you see
"change your password", you must set a new one before the workspace unlocks.

## Finding your way around
The left sidebar groups features by purpose:

- **Dashboard** — a live overview of recent activity.
- **Data & IoCs** — document processing, the knowledge base, indicators of
  compromise, and projects.
- **Integration Hub** — Jira, Confluence, Wiki.js and Splunk, plus a natural
  language chat that turns your question into a read-only query.
- **Intelligence** — RSS/Atom threat feeds and automation rules.
- **Reports** — assemble and export Markdown/HTML/DOCX/PDF reports.
- **Price Analyzer** — turn a contract or statement of work into an editable
  effort estimate, WBS, Gantt schedule, RACI matrix and cost breakdown.
- **Operations** — background jobs, notifications and backups.
- **Prompt Library** — reusable prompt templates for the LLM.

You will only see the sections your account has been granted. Ask an
administrator under **Access & Features** if something is missing.

## Getting help
This guide library is available in English and Farsi. Use the language
switch at the top of the Help page to change it, and the audience tabs to
see either the general user guide or (if you are an administrator) the
admin guide for the same topic.""",
        "شروع کار با میزکار سوک سورین",
        """میزکار سوک سورین یک فضای کاری یکپارچه برای پردازش شواهد، پیگیری
شاخص‌ها، انجام تحقیقات و تولید گزارش است.

## ورود به سامانه
از نام کاربری و رمز عبوری که مدیر سیستم در اختیارتان گذاشته استفاده کنید. اگر
پیام «رمز عبور خود را تغییر دهید» را دیدید، پیش از باز شدن فضای کاری باید یک
رمز جدید تعیین کنید.

## آشنایی با بخش‌ها
نوار کناری سمت چپ امکانات را بر اساس کاربرد گروه‌بندی می‌کند:

- **داشبورد** — نمایی زنده از فعالیت‌های اخیر.
- **داده‌ها و IoC** — پردازش اسناد، پایگاه دانش، شاخص‌های نفوذ و پروژه‌ها.
- **مرکز یکپارچه‌سازی** — جیرا، کانفلوئنس، ویکی‌جی‌اس و اسپلانک، به همراه یک
  گفتگوی زبان طبیعی که پرسش شما را به یک پرس‌وجوی فقط-خواندنی تبدیل می‌کند.
- **اطلاعات** — فیدهای تهدید RSS/Atom و قوانین خودکارسازی.
- **گزارش‌ها** — ساخت و خروجی گزارش در قالب Markdown/HTML/DOCX/PDF.
- **تحلیلگر قیمت** — تبدیل یک قرارداد یا شرح خدمات به برآورد تلاش قابل‌ویرایش،
  WBS، زمان‌بندی گانت، ماتریس RACI و تفکیک هزینه.
- **عملیات** — کارهای پس‌زمینه، اعلان‌ها و پشتیبان‌گیری.
- **کتابخانه پرامپت** — الگوهای قابل‌استفاده مجدد برای مدل زبانی.

فقط بخش‌هایی را می‌بینید که برای حساب شما مجاز شده‌اند. اگر بخشی از قلم افتاده
است، از مدیر سیستم زیر عنوان **دسترسی و امکانات** درخواست کنید.

## دریافت راهنما
این کتابخانه راهنما به دو زبان انگلیسی و فارسی در دسترس است. برای تغییر زبان
از کلید زبان در بالای صفحه راهنما استفاده کنید و برای دیدن راهنمای مدیریتی
همان موضوع (در صورت داشتن نقش مدیر) از تب مخاطب استفاده کنید.""",
    ),
    (
        "data-and-iocs", "user", "Workspace", 1,
        "Processing documents, knowledge and indicators",
        """The **Data & IoCs** hub has four tabs.

## Processing
Upload a file (PDF, DOCX, XLSX, PPTX, HTML, Markdown, CSV, JSON or text) or
paste text/a URL. The pipeline extracts readable text, masks sensitive data
(names, emails, IPs, etc. depending on the protection mode you pick),
optimizes it for the token budget you choose, and produces a quick summary.
Review every stage before saving or sending anything to the LLM.

## Knowledge base
Save processed content as searchable notes with tags and a source
reference, so analysts can find prior findings quickly.

## IoCs
Track indicators of compromise (IP, domain, hash, etc.) with confidence,
severity, related malware/actor/incident/customer, and a false-positive flag.

## Projects
Group an investigation's risks, issues, milestones, action items and notes
under one record, with a health indicator and a progress percentage. Link a
project to a Jira project key or Splunk environment for quick reference. A
Price Analyzer contract can also be linked to a project, and its scheduled
milestones can be pushed into the project's milestone list.""",
        "پردازش اسناد، دانش و شاخص‌ها",
        """مرکز **داده‌ها و IoC** چهار تب دارد.

## پردازش
یک فایل (PDF، DOCX، XLSX، PPTX، HTML، Markdown، CSV، JSON یا متن) بارگذاری
کنید یا متن/آدرس اینترنتی را جای‌گذاری کنید. خط پردازش متن قابل‌خواندن را
استخراج می‌کند، داده‌های حساس را بر اساس حالت حفاظتی انتخابی شما پنهان
می‌کند، آن را برای سقف توکن انتخابی بهینه می‌کند و یک خلاصه سریع می‌سازد. پیش
از ذخیره یا ارسال هرچیزی به مدل زبانی، هر مرحله را بازبینی کنید.

## پایگاه دانش
محتوای پردازش‌شده را به‌صورت یادداشت‌های قابل‌جست‌وجو همراه با برچسب و منبع
ذخیره کنید تا تحلیل‌گران بتوانند یافته‌های قبلی را سریع پیدا کنند.

## شاخص‌های نفوذ (IoC)
شاخص‌ها (IP، دامنه، هش و غیره) را همراه با میزان اطمینان، شدت، بدافزار/عامل/
حادثه/مشتری مرتبط و پرچم مثبت-کاذب پیگیری کنید.

## پروژه‌ها
ریسک‌ها، مسائل، نقاط عطف، اقدامات و یادداشت‌های یک تحقیق را زیر یک رکورد
گروه‌بندی کنید، همراه با نشانگر سلامت و درصد پیشرفت. یک پروژه را برای مراجعه
سریع به کلید پروژه جیرا یا محیط اسپلانک متصل کنید. یک قرارداد تحلیلگر قیمت
نیز می‌تواند به یک پروژه متصل شود و نقاط عطف زمان‌بندی‌شده آن به فهرست نقاط
عطف پروژه ارسال شود.""",
    ),
    (
        "price-analyzer", "user", "Workspace", 2,
        "Estimating and pricing a contract",
        """The **Price Analyzer** turns a Persian or English contract/SOW into
an editable estimate.

1. **Upload or paste** the contract (file or text). It is extracted the same
   way as in Data & IoCs processing.
2. **Analyze** — the LLM (or, with no LLM configured, a built-in heuristic)
   splits the document into scope sections, each with a suggested category,
   discipline/role and person-hour estimate.
3. **Edit** — adjust each section's hours, role, or hourly-rate override, add
   notes, or add/remove sections by hand. Nothing here is final until you say so.
4. **Coefficients** — set your hourly rate per role, overhead %, contingency
   %, tax % and discount % once per contract; costs recompute live.
5. **Generate WBS & Gantt** — builds a 3-level work breakdown structure
   (Project → Phase → Task) and schedules tasks sequentially from a start
   date you choose, using hours-per-day from your coefficients. Dates,
   % complete and assignee are editable per WBS item afterwards.
6. **RACI matrix** — a starter Responsible/Accountable/Consulted/Informed
   assignment is suggested per task; add participants and edit every cell.
7. **Export** — download the full analysis (cost breakdown, WBS, Gantt and
   RACI) as PDF or Excel, or push a summary into Reports, or link the
   contract to a Project.""",
        "برآورد و قیمت‌گذاری یک قرارداد",
        """**تحلیلگر قیمت** یک قرارداد یا شرح خدمات فارسی یا انگلیسی را به یک
برآورد قابل‌ویرایش تبدیل می‌کند.

۱. **بارگذاری یا جای‌گذاری** قرارداد (فایل یا متن). استخراج آن مشابه بخش
   پردازش در داده‌ها و IoC انجام می‌شود.
۲. **تحلیل** — مدل زبانی (یا در نبود مدل زبانی، یک روش اکتشافی داخلی) سند را
   به بخش‌های دامنه کار تقسیم می‌کند؛ هر بخش با دسته، تخصص/نقش پیشنهادی و
   برآورد نفر-ساعت.
۳. **ویرایش** — ساعت هر بخش، نقش یا نرخ ساعتی جایگزین را تنظیم کنید، یادداشت
   اضافه کنید یا بخش‌ها را دستی اضافه/حذف کنید. تا زمانی که تأیید نکنید هیچ‌چیز
   نهایی نیست.
۴. **ضرایب** — نرخ ساعتی هر نقش، درصد سربار، درصد پیش‌بینی‌نشده، درصد مالیات و
   درصد تخفیف را یک‌بار برای هر قرارداد تنظیم کنید؛ هزینه‌ها به‌صورت زنده
   بازمحاسبه می‌شوند.
۵. **ساخت WBS و گانت** — یک ساختار شکست کار سه‌سطحی (پروژه ← فاز ← وظیفه)
   می‌سازد و وظایف را به‌ترتیب از تاریخ شروع انتخابی شما، با استفاده از
   ساعت-در-روزِ ضرایب شما، زمان‌بندی می‌کند. تاریخ‌ها، درصد پیشرفت و مسئول هر
   مورد WBS پس از آن قابل‌ویرایش هستند.
۶. **ماتریس RACI** — یک تخصیص اولیه مسئول/پاسخگو/مشورت‌شونده/مطلع برای هر
   وظیفه پیشنهاد می‌شود؛ شرکت‌کننده اضافه کنید و هر سلول را ویرایش کنید.
۷. **خروجی** — تحلیل کامل (تفکیک هزینه، WBS، گانت و RACI) را به‌صورت PDF یا
   Excel دانلود کنید، یا خلاصه‌ای را به گزارش‌ها ارسال کنید، یا قرارداد را به
   یک پروژه متصل کنید.""",
    ),
    (
        "integration-hub", "user", "Workspace", 3,
        "Jira, Confluence, Wiki.js and Splunk",
        """The **Integration Hub** connects Jira, Confluence, Wiki.js and
Splunk. Each connection is scoped to your tenant and encrypted at rest.

Use the **prompt chat** to ask a question in plain language; it generates a
read-only query (JQL, CQL, GraphQL or SPL), shows it to you for review, and
lets you edit it before running. Every run is saved to a redacted history so
you (and admins, for audit) can see what was asked and returned.

Bulk operations (where enabled) are rate-limited and require confirmation
before they touch more than one issue.""",
        "جیرا، کانفلوئنس، ویکی‌جی‌اس و اسپلانک",
        """**مرکز یکپارچه‌سازی** جیرا، کانفلوئنس، ویکی‌جی‌اس و اسپلانک را متصل
می‌کند. هر اتصال به مستأجر شما محدود است و در حالت سکون رمزگذاری می‌شود.

از **گفتگوی پرامپتی** برای پرسیدن سؤال به زبان ساده استفاده کنید؛ این ابزار
یک پرس‌وجوی فقط-خواندنی (JQL، CQL، GraphQL یا SPL) می‌سازد، آن را برای
بازبینی نشان می‌دهد و امکان ویرایش پیش از اجرا را می‌دهد. هر اجرا در یک
تاریخچه ویرایش‌شده ذخیره می‌شود تا شما (و مدیران، برای ممیزی) بتوانید ببینید
چه چیزی پرسیده و بازگردانده شده است.

عملیات دسته‌ای (در صورت فعال بودن) نرخ‌محدود هستند و پیش از اثرگذاری بر بیش
از یک مورد نیاز به تأیید دارند.""",
    ),
    (
        "reports", "user", "Workspace", 4,
        "Assembling and exporting reports",
        """Choose a report type (daily/weekly/monthly activity, threat digest,
incident, executive, etc.), a language (English or Farsi), a detail level,
and the data sources to pull from (knowledge base, intelligence, IoCs,
analyses, plus manual notes). Generation builds a skeleton first, and — if
an LLM is configured — refines it into prose that only uses the data you
provided; it never invents figures. Edit the result inline (every edit is
versioned) and export to Markdown, HTML, DOCX or PDF.""",
        "ساخت و خروجی گزارش‌ها",
        """نوع گزارش (فعالیت روزانه/هفتگی/ماهانه، خلاصه تهدید، حادثه، مدیریتی و
غیره)، زبان (انگلیسی یا فارسی)، سطح جزئیات و منابع داده (پایگاه دانش،
اطلاعات، IoCها، تحلیل‌ها، به‌علاوه یادداشت دستی) را انتخاب کنید. تولید ابتدا
یک اسکلت می‌سازد و — در صورت پیکربندی مدل زبانی — آن را به متنی روان تبدیل
می‌کند که فقط از داده‌های ارائه‌شده شما استفاده می‌کند و هرگز عددی را
اختراع نمی‌کند. نتیجه را درون‌خطی ویرایش کنید (هر ویرایش نسخه‌بندی می‌شود) و
به Markdown، HTML، DOCX یا PDF خروجی بگیرید.""",
    ),
    (
        "intelligence", "user", "Workspace", 5,
        "Threat feeds and automation",
        """The Intelligence module pulls and normalizes RSS/Atom threat feeds
and lets you configure automation rules for recurring collection and
scoring. Use it alongside IoCs to keep your indicator set current.""",
        "فیدهای تهدید و خودکارسازی",
        """ماژول اطلاعات فیدهای تهدید RSS/Atom را دریافت و یکپارچه می‌کند و
امکان پیکربندی قوانین خودکارسازی برای جمع‌آوری و امتیازدهی دوره‌ای را
می‌دهد. از آن در کنار IoCها برای به‌روز نگه‌داشتن مجموعه شاخص‌های خود استفاده
کنید.""",
    ),
    (
        "operations-and-prompts", "user", "Workspace", 6,
        "Jobs, notifications and the prompt library",
        """Long-running work (document analysis, feed refresh, backups) runs
as a background job under **Operations → Jobs**, with progress and status.
**Notifications** shows the in-app feed of job and system events.

**Prompt Library** stores reusable system/user prompt templates with
variables, so you and your team reuse a vetted instruction instead of
retyping it for every LLM call.""",
        "کارها، اعلان‌ها و کتابخانه پرامپت",
        """کارهای طولانی (تحلیل سند، به‌روزرسانی فید، پشتیبان‌گیری) به‌صورت یک
کار پس‌زمینه زیر **عملیات ← کارها** با نمایش پیشرفت و وضعیت اجرا می‌شود.
**اعلان‌ها** فید درون‌برنامه‌ای رویدادهای کاری و سیستمی را نشان می‌دهد.

**کتابخانه پرامپت** الگوهای سیستمی/کاربری قابل‌استفاده مجدد را همراه با
متغیر ذخیره می‌کند تا شما و تیمتان به‌جای بازنویسی هر بار، از یک دستورالعمل
بررسی‌شده دوباره استفاده کنید.""",
    ),
    (
        "admin-access-control", "admin", "Administration", 0,
        "Users, module access and feature policies",
        """Under **Access & Features** (admin-only):

## Users
Create local accounts with a role (admin/analyst/viewer) and the exact set
of modules they may open (`dashboard`, `data`, `integrations`,
`intelligence`, `reports`, `price_analyzer`, `operations`, `prompts`,
`settings`). Admin accounts implicitly get every module. New accounts start
with `must_change_password` set, so the first login forces a password reset.

## Feature policies
Every module (and some finer-grained features like `integration.jira` or
`ai.processing`) has a policy: enabled/disabled, an optional start/expiry
window, and an optional role restriction. This lets you trial a module for
a limited time, restrict it to certain roles, or kill-switch it instantly
without touching code.

## Activity history
Every mutating API call is logged with actor, module, path, status and
duration, filterable by actor/module/action/status — use it for audits.

## Rolling out new modules (e.g. Price Analyzer)
A new user only sees a module once you add its key to their
`module_permissions`. If a module's feature policy is disabled or expired,
even users with the module key will be blocked until you re-enable it.""",
        "کاربران، دسترسی به ماژول‌ها و سیاست‌های امکانات",
        """زیر عنوان **دسترسی و امکانات** (فقط مدیر):

## کاربران
حساب‌های محلی را با یک نقش (مدیر/تحلیل‌گر/بیننده) و مجموعه دقیقی از ماژول‌هایی
که می‌توانند باز کنند بسازید (`dashboard`، `data`، `integrations`،
`intelligence`، `reports`، `price_analyzer`، `operations`، `prompts`،
`settings`). حساب‌های مدیر به‌طور ضمنی به همه ماژول‌ها دسترسی دارند. حساب‌های
جدید با فعال بودن `must_change_password` شروع می‌شوند، بنابراین اولین ورود
تعویض رمز عبور را الزامی می‌کند.

## سیاست‌های امکانات
هر ماژول (و برخی امکانات دقیق‌تر مانند `integration.jira` یا `ai.processing`)
یک سیاست دارد: فعال/غیرفعال، یک بازه شروع/انقضای اختیاری و یک محدودیت نقش
اختیاری. این به شما امکان می‌دهد یک ماژول را برای مدت محدود آزمایش کنید، آن
را به نقش‌های خاصی محدود کنید یا بدون تغییر کد فوراً آن را خاموش کنید.

## تاریخچه فعالیت
هر فراخوانی API که تغییری ایجاد می‌کند همراه با عامل، ماژول، مسیر، وضعیت و
مدت‌زمان ثبت می‌شود و بر اساس عامل/ماژول/عملیات/وضعیت قابل‌فیلتر است — از آن
برای ممیزی استفاده کنید.

## معرفی ماژول‌های جدید (مثلاً تحلیلگر قیمت)
یک کاربر جدید فقط زمانی یک ماژول را می‌بیند که کلید آن را به
`module_permissions` او اضافه کرده باشید. اگر سیاست امکان یک ماژول غیرفعال یا
منقضی باشد، حتی کاربرانی که کلید ماژول را دارند تا زمان فعال‌سازی مجدد شما
مسدود می‌مانند.""",
    ),
    (
        "admin-settings-and-llm", "admin", "Administration", 1,
        "LLM providers, secrets and encrypted storage",
        """Under **Settings**, configure the LLM provider (Anthropic, an
OpenAI-compatible endpoint, or the local Claude Code CLI), model, token
limits and timeout. API keys are encrypted at rest (Fernet key derived from
`SECRET_KEY`) and only ever shown masked. Change `ADMIN_PASSWORD` and
`SECRET_KEY` from their defaults before exposing the app to a network — see
`SECURITY.md`.

Sensitive-data patterns (regex or literal) used by the tokenizer/masking
step can be added, edited and toggled here too; every value tokenized this
way is stored encrypted and is never sent to an LLM.""",
        "ارائه‌دهندگان مدل زبانی، اسرار و ذخیره‌سازی رمزنگاری‌شده",
        """زیر عنوان **تنظیمات**، ارائه‌دهنده مدل زبانی (آنتروپیک، یک نقطه پایانی
سازگار با OpenAI، یا CLI محلی Claude Code)، مدل، محدودیت توکن و زمان انتظار
را پیکربندی کنید. کلیدهای API در حالت سکون رمزگذاری می‌شوند (کلید Fernet
مشتق‌شده از `SECRET_KEY`) و همیشه فقط به‌صورت پنهان‌شده نمایش داده می‌شوند.
پیش از در دسترس قرار دادن برنامه روی شبکه، `ADMIN_PASSWORD` و `SECRET_KEY` را
از مقادیر پیش‌فرض تغییر دهید — به `SECURITY.md` مراجعه کنید.

الگوهای داده حساس (عبارت باقاعده یا لفظی) که در مرحله توکن‌سازی/پنهان‌سازی
استفاده می‌شوند نیز از همین‌جا قابل افزودن، ویرایش و فعال/غیرفعال‌سازی هستند؛
هر مقداری که به این شکل توکن شود رمزگذاری‌شده ذخیره می‌شود و هرگز به مدل
زبانی ارسال نمی‌شود.""",
    ),
    (
        "admin-price-analyzer-setup", "admin", "Administration", 2,
        "Rolling out the Price Analyzer to your team",
        """1. Grant the `price_analyzer` module to the roles/users who need it,
   under **Access & Features**.
2. Optionally set a feature policy on `module.price_analyzer` (start/expiry
   window, role restriction) if you want a time-boxed rollout.
3. Set sane default coefficients (hourly rates per role, overhead,
   contingency, tax) — analysts can still override them per contract.
4. Make sure an LLM provider is configured under Settings for automatic
   contract section-splitting; without one, the analyzer still works using
   a built-in heuristic split, just less precisely.
5. For Farsi contracts, install a Persian-capable font (e.g. Vazirmatn or
   Noto Naskh Arabic) under `/usr/share/fonts` on the server so PDF exports
   render Farsi glyphs correctly; Excel export has no such requirement.""",
        "معرفی تحلیلگر قیمت به تیم شما",
        """۱. ماژول `price_analyzer` را برای نقش‌ها/کاربرانی که نیاز دارند، زیر
   **دسترسی و امکانات** اعطا کنید.
۲. در صورت تمایل به معرفی زمان‌بندی‌شده، یک سیاست امکان روی
   `module.price_analyzer` (بازه شروع/انقضا، محدودیت نقش) تنظیم کنید.
۳. ضرایب پیش‌فرض معقول (نرخ ساعتی هر نقش، سربار، پیش‌بینی‌نشده، مالیات) تعیین
   کنید — تحلیل‌گران همچنان می‌توانند آن‌ها را برای هر قرارداد بازنویسی کنند.
۴. مطمئن شوید یک ارائه‌دهنده مدل زبانی زیر تنظیمات برای تقسیم خودکار بخش‌های
   قرارداد پیکربندی شده است؛ بدون آن، تحلیلگر همچنان با یک روش اکتشافی داخلی
   کار می‌کند، فقط با دقت کمتر.
۵. برای قراردادهای فارسی، یک قلم دارای پشتیبانی فارسی (مانند Vazirmatn یا
   Noto Naskh Arabic) را زیر `/usr/share/fonts` روی سرور نصب کنید تا خروجی
   PDF حروف فارسی را درست نمایش دهد؛ خروجی Excel چنین نیازی ندارد.""",
    ),
]


def seed_default_guides(db: Session) -> None:
    for slug, audience, category, order_index, title_en, content_en, title_fa, content_fa in _GUIDES:
        for language, title, content in (("en", title_en, content_en), ("fa", title_fa, content_fa)):
            exists = db.query(HelpGuide).filter(
                HelpGuide.slug == slug, HelpGuide.language == language,
            ).first()
            if exists is not None:
                continue
            db.add(HelpGuide(
                slug=slug, language=language, audience=audience, category=category,
                order_index=order_index, title=title,
                summary=content.strip().splitlines()[0][:200] if content.strip() else "",
                content=content, is_builtin=True, updated_by="system",
            ))
    db.commit()
