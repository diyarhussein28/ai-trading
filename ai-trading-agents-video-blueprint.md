# المخطط الكامل: فريق AI Agents لتداول عملات الميم (Memecoins) على Solana

> إعادة بناء تقنية وتحليلية لسلسلة «قررت أسوي بوت تداول بالـ AI» (الجزء 1 والجزء 2)، معدّلة لاستراتيجية **عملات الميم على Solana** (pump.fun / PumpSwap / DexScreener) بدل Binance.
> تتضمن: نصي الفيديوين بالتوقيت، وكل البيانات المقروءة من الشاشة، وتحليلاً كمياً، ومعمارية النسخة V7 النهائية (Confidence Score + تحديد حجم الصفقة)، وحل مشكلة تكلفة بيانات X، والتشغيل على السحابة 24 ساعة (Railway)، والكود، والبرومبتات، وبروتوكول اختبار الـ 100 صفقة، ومسار الانتقال للتداول الحقيقي، ودليل إنتاج الفيديو.

---

## الفهرس

0. [الخلاصة التنفيذية: ما الذي تغيّر وما الذي يجب أن تعرفه](#0)
1. [البطاقة التقنية للفيديوين](#1)
2. [نص الجزء الأول بالتوقيت (مختصر)](#2)
3. [نص الجزء الثاني بالتوقيت (كامل)](#3)
4. [تفكيك مشاهد الجزء الثاني](#4)
5. [كل البيانات المستخرجة من الشاشة (الجزآن)](#5)
6. [التحليل الكمي: ماذا تعني الأرقام فعلاً](#6)
7. [كيف يعمل سوق عملات الميم على Solana (الخلفية التقنية للاستراتيجية)](#7)
8. [معمارية النسخة V7 النهائية](#8)
9. [مواصفات البناء التفصيلية](#9)
10. [Confidence Score وتحديد حجم الصفقة](#10)
11. [طبقة بيانات X: المشكلة، والحل الذي في الفيديو، والحل الآمن](#11)
12. [الكود الهيكلي (Python)](#12)
13. [البرومبتات](#13)
14. [التشغيل 24/7 على Railway](#14)
15. [مسار الإصدارات V1 → V7 وخارطة V8](#15)
16. [بروتوكول اختبار الـ 100 صفقة](#16)
17. [الانتقال من Paper إلى أموال حقيقية](#17)
18. [دليل إعادة إنتاج الفيديو (Motion Design)](#18)
19. [المخاطر والتنبيهات](#19)
20. [قائمة التنفيذ (Checklist)](#20)

---

<a id="0"></a>
## 0. الخلاصة التنفيذية

### قصة السلسلة في سطرين
- **الجزء 1:** طلب صانع المحتوى من Claude بناء Agent يتداول العملات الرقمية. فشل الأول، فتحوّل إلى **3 Agents** (المحقق، البروفيسور، القنّاص) **لا يدخلون صفقة إلا بالإجماع**، مع فريق منافس بناه ChatGPT. بعد 7 نسخ حققت **V7 نسبة 8/10 صفقات رابحة** (80%) على أموال ورقية.
- **الجزء 2:** يكشف أن الساحة هي **«أخطر سوق بالعالم: الميم كوينز»**، ويشرح مشكلتين وحلّيهما:
  1. **بيانات X مكلفة:** البوت يسحب **2000 بوست بالساعة**، فنفد رصيد X API **مرتين خلال 12 دقيقة** (**−$40**). الحل في الفيديو: أداة تسحب من المتصفح عبر جلسة تسجيل دخول (Cookie-Editor) **من حساب منفصل لأن هذا «يخالف الشروط»**.
  2. **البوت ينام مع اللابتوب:** الحل رفعه على **Railway** ليعمل على السحابة **24 ساعة**.
  وأضاف في V7: **Confidence Score لكل فرصة يحدد حجم الصفقة**. والخطوة الحالية: **«الاختبار الحقيقي» = 100 صفقة على V7** (العدّاد وصل إلى 10/100 في الفيديو).

### ما يجب أن تعرفه قبل البناء

| النقطة | الحقيقة |
|---|---|
| السوق | Solana memecoins (إطلاقات pump.fun وما ينتقل منها إلى AMM)، والحساب بـ **SOL** |
| النتيجة | **8/10 رابحة** و**+0.0438 SOL** صافي، **ورقياً**، بحجم ~0.0205 SOL للصفقة |
| «80%» | **نسبة صفقات رابحة**، وليست 80% ربحاً على رأس المال |
| الإحصاء | فاصل ثقة 95% لنسبة 8/10 ≈ **[49%، 94%]**، وصاحب الفيديو نفسه يقول: «ما أقدر أقول إن هذي الاستراتيجية نجحت» |
| «الاختبار الحقيقي» | يعني اختبار **100 صفقة**، ولم يُذكر صراحة أنه بأموال حقيقية (في الجزء 1 قال إن المال الحقيقي **بعد** نجاح الـ 100) |
| بيانات X عبر الكوكيز | **مخالفة لشروط X** باعتراف صاحب الفيديو؛ هذا الملف يشرح ما فعله تحليلياً، ويعطيك بدائل نظامية (القسم 11) |

> ⚠️ **بخصوص هدف مشروعك («ربح لا يقل عن 80%»):** الرقم الذي في الفيديو هو نسبة إصابة على 10 صفقات. ما يجعل استراتيجية ميم رابحة فعلاً هو: **متوسط ربح الرابحة ÷ متوسط خسارة الخاسرة** و**تجنب الـ Rugs** و**الانزلاق الحقيقي**. لهذا يقيس هذا الملف النجاح بـ Profit Factor والعائد الصافي بعد التكاليف، وليس بنسبة الإصابة وحدها.

---

<a id="1"></a>
## 1. البطاقة التقنية للفيديوين

| الخاصية | الجزء 1 | الجزء 2 |
|---|---|---|
| المدة | 92.1 ث | 94.1 ث |
| الأبعاد / الإطارات | 720×1280، 30fps | 720×1280، 30fps |
| الفيديو | H.264 ~603 kbps | H.264 ~916 kbps |
| الصوت | AAC 44.1kHz، ~82 kbps، متوسط −17.1 dB | AAC 44.1kHz، ~55 kbps، متوسط −16.5 dB |
| المُرمِّز | `AVC Coding` (تصدير جوال، غالباً CapCut) | نفسه |
| التصوير | لقطة مكتب واسعة (ثوب أبيض وغترة) | سيلفي بكاميرا الجوال الأمامية، AirPods، إضاءة ليلية |
| عنوان ثابت | نعم: «قررت أسوي بوت تداول بالـ AI» | لا يوجد عنوان ثابت |

**منهجية التحليل:** استخراج 10 إطارات في الثانية لمنطقتي الترجمة، وإطارات كاملة الدقة للحظات المفصلية، وتكبير الجداول واللوحات، وقياس الألوان من البكسلات. النص مأخوذ من **الترجمة المحروقة كلمة بكلمة**؛ التفريغ الصوتي الآلي لم يكن متاحاً.

---

<a id="2"></a>
## 2. نص الجزء الأول (مختصر)

| الزمن | النص |
|---|---|
| 0–10 | «واحد عطى AI Agent ميزانية 50 دولار وقال له ادفع حق نفسك وإلا بتموت، وبعد 48 ساعة شيّك على المحفظة وإلا فيها 5000 دولار.» (الرسم يعرض $1,684) |
| 10–17 | «طبعاً لأن عجبتني الفكرة فقلت حق [Claude]: أبيك تسوي شي مقارب، لكن يتداول بسوق العملات الرقمية.» |
| 17–24 | «وبعد محاولات كلود سوّى هذا الإيجنت، وبعد ما سوّى لي صفقتين، كل الصفقتين خسرانين.» |
| 24–35 | «قلت حبيبي أبي 3 إيجنتس، كل واحد له خاصية معينة، وما ياخذون أي صفقة إلا إذا الثري إيجنتس اتفقوا.» |
| 35–44 | «ليش ما أخلي ChatGPT أيضاً يسوي 3 إيجنتس ويصير تحدي.» |
| 44–55 | «سوّينا [V1] ما عجبت النتيجة، الثاني والثالث… لين وصلنا حق النسخة السابعة.» |
| 55–63 | «النسخة السابعة حققت 80% Hit Rate، وبنسبة ربح على الصفقة ما يعادل 40%، لكن كل هذا تم Paper Money.» |
| 63–76 | «الخطوة الجاية: 100 صفقة، وإذا 80% وفوق راح أبلّش أحط فيه فلوس حقيقية.» |
| 76–92 | «الهدف مو الربح، الهدف أعرف وين وصل AI. إذا قدر يربح بأخطر سوق بالعالم، باقي الأسواق راح تكون سهلة… تفاعل مع الفيديو إذا مهتم تعرف النتيجة.» |

---

<a id="3"></a>
## 3. نص الجزء الثاني بالتوقيت (كامل)

| الزمن | النص (اللون الأخضر/الأحمر في الأصل بين علامتي **) | الجرافيك المرافق |
|---|---|---|
| 00:00–00:08 | «بعد **7** نسخ، **AI** أخيراً قدر يربح **80%** من الصفقات **بأخطر** سوق بالعالم.» | «V7» نيون كبير + صف V7 من جدول الإصدارات + كبسولات «8/10 Wins» و«80%» و«+0.0438 SOL» + سطر أحمر «بأخطر سوق بالعالم: الميم كوينز» |
| 00:08–00:14 | «خلوني أشرح لكم شصار. آخر مرة وريتكم **3 Agents** سويتهم عشان يصيدون الفرص **بالميم كوينز**.» | «3 AI Agents»: بطاقات المحقق والبروفيسور والقنّاص؛ ثم لقطة واسعة للمكتب مع نصف سفلي ضبابي |
| 00:14–00:16 | «بس واجهتني **مشكلتين**.» | لقطة سيلفي بالأبيض والأسود |
| 00:16–00:26 | «**المشكلة الأولى**: إن اثنين من الأجنتس كانوا يعتمدون على **X**. البوت كان يجر بالساعة **2000** بوست، فالكردت خلال **12** دقيقة **خلص مرتين**.» | كبسولة حمراء «المشكلة الأولى» + بطاقتا المحقق والقنّاص بخطوط متقطعة صفراء نحو X؛ ثم بطاقة «X API Credits / بوست بالساعة 2000» ببطارية خضراء 100% تفرغ إلى الأحمر، وساعة «12:00»، و«خلص مرتين» و«**−$40 في 12 دقيقة**» |
| 00:26–00:34 | «فلجأت لطريقة ثانية: حطيت **تول** يجر **X** من **المتصفح**، واستخدمت **Cookie-Editor** عشان أربط السشنز.» | نافذة متصفح `x.com/search?q=pump.fun` مع JSON مستخرج: `{"user":"@degen","text":"$PEPE2…","likes":1204}` و`{"user":"@whale","text":"new pump.fun…"}` + كبسولة «تول يسحب من المتصفح»؛ ثم صفحة إضافة **Cookie-Editor** (v1.13.0) + «Cookie-Editor · الإضافة الحقيقية» + «ربط السشن بدون API» |
| 00:35–00:41 | «وطبعاً كل هذا تم من حساب **منفصل**، وليس من الحساب الأساسي، لأن هذا **يخالف الشروط**.» | بطاقة «حساب منفصل · للتجربة ✓» وبطاقة «الحساب الأساسي · ما ينلمس ✗» + ختم أحمر «يخالف الشروط» |
| 00:41–00:47 | «والمشكلة الثانية: إذا سكّرت اللابتوب ورحت [نمت]، حصلت إن البوت **نايم** معي.» | سيلفي أبيض وأسود + «Z» |
| 00:47–00:54 | «فرفعته على **Railway** عشان يشتغل على **الكلاود 24** ساعة، حتى لو مسكّر جهازي.» | سحابة «Railway» + 3 خوادم بمؤشرات خضراء + كبسولة «على الكلاود · 24 ساعة» |
| 00:54–00:64 | «الحين نرجع للاختبارات: النسخة **الثانية** و**الثالثة** و**الرابعة** و**الخامسة** و**السادسة**، ولا واحدة منهم **أقنعتني**، لين وصلنا حق النسخة **السابعة**.» | جدول «كل النسخ · Wins»: إطار أصفر يتنقل على V3 وV4 وV6 مع تمييز عمود Wins بالأحمر، ثم علامات ✗ حمراء على V2–V6، ثم V7 بإطار أخضر وكبسولة «V7 · 8/10 Wins · 80%» |
| 00:64–00:71 | «صار **AI** يعطي كل فرصة يشوفها **Confidence Score**، ويحدد حجم الصفقة على أساسه.» | عداد نصف دائري «Confidence Score» من أحمر إلى أصفر إلى أخضر: الإبرة تتحرك 0 → 37 → 79 → 87، وتحته شريط «حجم الصفقة» يمتلئ بنسبة الدرجة |
| 00:71–00:75 | «وأول عشر صفقات، **ثمانية** منهم **رابحة**.» | «أول 10 صفقات»: 10 مربعات #1–#10، ثمانية ✓ خضراء و✗ حمراء على #4 و#8، و«8 / 10» |
| 00:75–00:78 | «بس الحين ما أقدر أقول إن هذي الاستراتيجية **نجحت**.» | سيلفي كامل الشاشة |
| 00:78–00:84 | «فالاختبار **الحقيقي** الحين: **100** صفقة على النسخة **السابعة**، وبوريكم النتيجة.» | «الاختبار الحقيقي» بعنوان أصفر + عداد دائري «0/100 → 7/100 → 10/100 صفقة» |
| 00:84–00:94 | «فتأكد **تتفاعل** مع الفيديو عشان تشوف **النتيجة**، سواء **ربح** أو **خسارة**، وبناءً عليها بنسوي الخطوة **الجاية**.» | بطاقة CTA: «تفاعل مع الفيديو / عشان الخوارزمية ترجّعك للجزء الجاي» + ❤ 💬 ➤ 🔖 + «نتيجة الـ 100 صفقة: ربح أو خسارة» |

---

<a id="4"></a>
## 4. تفكيك مشاهد الجزء الثاني (البنية السردية)

| # | المقطع | الزمن | الوظيفة |
|---|---|---|---|
| 1 | Hook بالنتيجة | 0–8 | يبدأ بالذروة: «80% بأخطر سوق» |
| 2 | Recap | 8–14 | ربط بالجزء الأول (3 Agents) |
| 3 | توتر | 14–16 | «واجهتني مشكلتين» |
| 4 | مشكلة 1 + رقم صادم | 16–26 | 2000 بوست/ساعة، −$40 في 12 دقيقة |
| 5 | حل 1 + اعتراف | 26–41 | سحب من المتصفح + «يخالف الشروط» (يرفع المصداقية) |
| 6 | مشكلة 2 + حل 2 | 41–54 | البوت ينام ← Railway 24/7 |
| 7 | المثابرة | 54–64 | النسخ 2–6 فشلت |
| 8 | الابتكار | 64–71 | Confidence Score + حجم الصفقة |
| 9 | الدليل | 71–75 | 8/10 |
| 10 | التواضع | 75–78 | «ما أقدر أقول نجحت» |
| 11 | Cliffhanger | 78–94 | 100 صفقة، النتيجة في الجزء القادم |

---

<a id="5"></a>
## 5. كل البيانات المستخرجة من الشاشة

### 5.1 صفقات V1 (رد Claude عند السؤال: `why did the agents lose twice with anon and the other coin they bought`، بعد `Worked for 3m 47s`)

> «The records show these were **paper trades**, not real SOL purchases. Both bot copies entered the same two coins at nearly the same time, so these were **duplicated bets—not four independent trades**.»

| Token | ما حدث |
|---|---|
| FILLED | Bought **0.0205 SOL** each. Both hit the **stop after about 4 minutes**. Realized loss **−0.00486 SOL each (−23.7%)** |
| ANON | Bought 0.0205 SOL each. One exited after **28 min** at **−8.8%**; the other after **29 min** at **−15.1%** |

### 5.2 جدول الإصدارات (يظهر في الجزأين)

| Version | Closed positions | Wins | Fee-adjusted P&L |
|---|---|---|---|
| V1 | — | — | — |
| V2 | 41 across four tests | 17 (41%) | −0.0209 SOL |
| V3 | 20 across two tests | 7 (35%) | −0.0213 SOL |
| V4 | 20 across two tests | 7 (35%) | −0.0229 SOL |
| V5 | 49 across baseline and continuous test | 26 (53%) | −0.0954 SOL |
| V6 | 7 of 20 planned | 4 (57%) | −0.0234 SOL |
| **V7** | **10 of 100 planned** | **8 (80%)** | **+0.0438 SOL** |

### 5.3 لوحة فريق Claude
- **الشريط العلوي:** `PAPER` · `PnL today +0 SOL` · `launches seen 14258` · `uptime 1045m`
- **THE DETECTIVE** (المحقق) · SCOUT · community on X · `SCANNING` · «Working the room. Listening on X for pump.fun coins people whisper about.»
  - Latest lesson: «A 3-reel dump correlated with volume spike is not a reliable bearish signal on its own (STARS/SPARK/GMU dumped as expected, but KitchMity with similar red flags still mooned) – the pattern needs confirmation from liquidity/holder data…»
- **THE PROFESSOR** (البروفيسور) · ANALYST · on-chain data, **final call** · `IDLE` + `VOTE` · «Examined 72 new tokens on DexScreener. 0 show real momentum.»
- **THE SNIPER** (القنّاص) · HUNTER · big accounts & news · `IDLE` · «Connecting to X accounts…»
  - Latest lesson: «Even the rare case where a PASS token went slightly positive (RWNTK +3%) doesn't justify loosening criteria – the risk/reward of chasing unconfirmed volume spikes remains heavily skewed toward losses, so patience for a clean narrative-driv[en]…»
- **العدادات:** thoughts · ✅ · ❌ · lessons
- `TEAM BLACKBOARD – EVERY TOKEN THE AGENTS DISCUSSED` (مثال: `SHUHDOG · ANALYST · DexScreener momentum · 10m ago`) · `OPEN POSITIONS – No open positions`

### 5.4 لوحة فريق ChatGPT (INDEPENDENT PAPER TEAM – separate from Claude)
- `PAPER ONLY` · `PnL +0.0000 SOL` · `Uptime 315m`
- **Wallet Performance Scout** (Profitable wallets on candidate tokens) · «profitability is never inferred from price alone»
- **Volume & Momentum Analyst** (DEX volume, liquidity, buyers and price structure) · «STARTUP: 5m volume $2,397; 19 buys / 22 sells»
- **Pump.fun Prospect Scout** (migrated prospects, distribution and safety) · `BLOCKED` · «HTTP Error 429: Too Many Requests»
- العدادات: Launch profiles seen **22661** · Candidates **160** · Safety blocked **27**
- **فلتر السوق المكشوف:** Liquidity ≥ **$10k** · 5m volume ≥ **$5k** · buyers lead by ≥ **1.2×** · فحص أمان إلزامي · «**Entries require all three votes**»

### 5.5 صفقات V7 وV6

| # | COIN | VER | HELD | RETURN |
|---|---|---|---|---|
| 1–2 | HOLDOWEEN ×2 | V7 | 3.9m / 3.8m | +42.38% |
| 3 | USA | V7 | 1.8m | −1.00% |
| 4–5 | Grok ×2 | V7 | 4.5m / 4.4m | +40.73% |
| 6–7 | Holy Rugg ×2 | V7 | 6.8m / 6.7m | +42.77% |
| 8 | ATFS | V7 | 4.0m | +4.25% |
| 9 | HERMES | V7 | 6.6m | +25.29% |
| 10 | darwin | V7 | 6.3m | −51.17% |
| 11–12 | STARBUCKS ×2 | V7 | 7.5m / 7.4m | +44.43% |
| 13–14 | RAM ×2 | V7 | 8.1m / 8.0m | +40.67% |
| 15–16 | ZuckAI ×2 | V7 | 9.0m / 8.9m | +42.60% |
| 17 | Elonhotdog | V6 | 2.2m | +14.18% |
| 18 | MICKIEY | V6 | 1.5m | +12.61% |
| 19 | darwin | V6 | 1.9m | −55.43% |
| 20 | FOMO | V6 | 1.5m | −39.94% |

### 5.6 بيانات الجزء الثاني الجديدة

| العنصر | القيمة |
|---|---|
| حجم سحب X | **2000 بوست بالساعة** |
| استهلاك الرصيد | نفد **مرتين خلال 12 دقيقة** |
| التكلفة | **−$40 في 12 دقيقة** (≈ $200/ساعة لو استمر) |
| بديل البيانات | سحب نتائج بحث `x.com/search?q=pump.fun` من متصفح بجلسة مسجّلة (Cookie-Editor v1.13.0)، من **حساب منفصل** |
| الاستضافة | **Railway**، «على الكلاود · 24 ساعة» |
| Confidence Score | مقياس 0–100 (أمثلة معروضة: 37 أحمر، 79، 87 أخضر)، وشريط «حجم الصفقة» يتناسب معه |
| أول 10 صفقات (V7) | 8 ✓ و2 ✗ (الرسم يضع الخسارتين على #4 و#8، وهو توضيحي على الأرجح) |
| الاختبار الحقيقي | 100 صفقة على V7، العداد 10/100 |

---

<a id="6"></a>
## 6. التحليل الكمي: ماذا تعني الأرقام فعلاً

### 6.1 إزالة التكرار
الصفوف 1–16 تمثل **10 عملات فريدة**، لأن نسختين من البوت كانتا تعملان معاً (نفس خطأ V1). وهذا يطابق «10 of 100 planned».

### 6.2 المقاييس (على الصفقات الفريدة)

| المقياس | القيمة |
|---|---|
| Hit Rate | 8/10 = **80%** |
| متوسط العائد لكل صفقة | **+23.1%** |
| متوسط الرابحة | **+35.4%** |
| متوسط الخاسرة | **−26.1%** |
| Profit Factor | **≈ 5.4** |
| تحقق من الربح | 10 × 0.0205 × 23.1% ≈ 0.047 SOL قبل الرسوم ← **+0.0438** بعدها ✓ |
| فاصل Wilson 95% (10 صفقات) | **[49%، 94%]** |
| فاصل Wilson 95% لو بقيت 80% على 100 صفقة | **[71%، 87%]** |

### 6.3 قواعد الخروج المستنتجة
- **TP حوالي +40%:** ست رابحات من ثمانٍ بين +40.7% و+44.4%.
- **خروج زمني أو تتبعي:** ATFS (+4.25%) وHERMES (+25.29%).
- **SL بين −20% و−25%** (V1 ضرب الوقف عند −23.7%)، لكن darwin (−51%) وFOMO (−40%) تجاوزاه بسبب **الفجوات وسحب السيولة**.
- **V7 احتفظت أطول** (3.8–9 دقائق) من V6 (1.5–2.2 دقيقة).

### 6.4 أثر Confidence Score (الجزء 2)
الحجم متغير في V7 بحسب الدرجة، لكن الربح المعروض (+0.0438) يتطابق تقريباً مع حجم ثابت 0.0205. **الاستنتاج المرجّح:** إما أن الدرجات كانت متقاربة، أو أن الحجم يتغير ضمن مدى صغير حول القاعدة. ولا يمكن من 10 صفقات معرفة هل الدرجة الأعلى تعني فعلاً احتمالاً أعلى للربح، وهذا ما يجب قياسه في اختبار الـ 100 (معايرة الدرجة، القسم 10.4).

### 6.5 اقتصاديات البيانات (لماذا مشكلة X خطيرة)
- **−$40 في 12 دقيقة** مقابل ربح V7 كاملاً **+0.0438 SOL** (بضعة دولارات). **تكلفة البيانات كانت أكبر من الأرباح بعشرات المرات.**
- الدرس الهندسي: **لا تسحب بيانات اجتماعية إلا للعملات التي اجتازت الفلتر الرقمي.** فريق ChatGPT رأى 22,661 إطلاقاً، ومرّ منها 160 مرشحاً فقط (~0.7%). سحب X لهؤلاء فقط يخفض الحجم بأكثر من 99%.

---

<a id="7"></a>
## 7. كيف يعمل سوق عملات الميم على Solana

> هذه خلفية ضرورية لفهم لماذا صُممت الاستراتيجية بهذا الشكل. الأرقام الدقيقة للرسوم والعتبات تتغير، فتحقق منها في وثائق كل منصة قبل التشغيل.

### 7.1 دورة حياة عملة pump.fun
1. **الإطلاق (Launch):** أي شخص يُنشئ عملة بتكلفة ضئيلة، فتبدأ على **منحنى ربط (Bonding Curve)**: السعر يرتفع آلياً مع كل شراء، ولا يوجد مجمّع سيولة تقليدي بعد.
2. **مرحلة المنحنى:** آلاف الإطلاقات يومياً (14,258 و22,661 «launch seen» في اللوحتين)، وأغلبها يموت خلال دقائق.
3. **التخرّج (Migration/Graduation):** عندما يكتمل المنحنى، تنتقل السيولة إلى **AMM** (حالياً PumpSwap، وتاريخياً Raydium). هنا تظهر العملة على DexScreener بزوج تداول وسيولة حقيقية.
4. **ما بعد التخرّج:** الحركة الكبرى (+40% في دقائق) أو الانهيار. **هذه هي المنطقة التي يصطاد فيها البوت**؛ فلتر السيولة ≥ $10k يعني عملياً عملات متخرجة أو قريبة من التخرج.

### 7.2 أنواع الخسائر الكارثية (يجب أن يكشفها النظام)

| النوع | الوصف | الفحص |
|---|---|---|
| Rug pull | المطور أو الحيتان يبيعون أو يسحبون السيولة | تركّز أعلى 10 حاملين، نسبة محفظة المطور، حالة السيولة (محروقة/مقفلة) |
| Mint authority | المطور يستطيع طباعة عملات جديدة | يجب أن تكون **revoked** |
| Freeze authority | المطور يستطيع تجميد محفظتك | يجب أن تكون **revoked** |
| Bundled snipers | المطور يشتري بمحافظ متعددة في نفس الكتلة | عدد المشترين في أول كتلة/ثوانٍ، ونسبة ما يملكونه |
| Wash trading | حجم وهمي لجذب البوتات | نسبة المحافظ الفريدة إلى عدد الصفقات، وتكرار نفس الأحجام |
| Shill campaigns | حسابات X جديدة تنشر نصاً متطابقاً | عمر الحسابات، وتكرار النص |
| MEV / Sandwich | تُشترى قبلك ويُباع بعدك | Slippage محدود، وإرسال عبر مسار محمي (عند التداول الحقيقي) |

### 7.3 لماذا الإجماع 3/3 يناسب هذا السوق
الإشارة الخاطئة هنا مكلفة جداً (−50%)، والفرص كثيرة جداً. لذلك **تفويت فرصة أرخص بكثير من دخول خاطئ**. الإجماع وفيتو البروفيسور يجعلان النظام «صعب الإقناع»، وهو المطلوب.

---

<a id="8"></a>
## 8. معمارية النسخة V7 النهائية

> 🟢 = ظاهر في الفيديو، 🟡 = استنتاج هندسي مرجّح

```
 ┌─────────────────────────── Railway (24/7, 1 replica) 🟢 ──────────────────────────┐
 │                                                                                    │
 │  DISCOVERY                                                                         │
 │  🟢 pump.fun launches/migrations (PumpPortal WS)   🟢 DexScreener profiles/pairs     │
 │                         │                                                          │
 │                         ▼                                                          │
 │  🟢 HARD FILTER (code, no LLM, no X calls)                                          │
 │     liquidity ≥ $10k · 5m vol ≥ $5k · buys/sells ≥ 1.2 · 🟡 age/holders/authorities │
 │                         │  (~0.7% of launches pass)                                │
 │                         ▼                                                          │
 │  🟡 SAFETY GATE: mint/freeze revoked · top10 % · dev % · LP status · bundles        │
 │     any API failure → BLOCK 🟢                                                      │
 │                         │                                                          │
 │                         ▼                                                          │
 │  🟢 SOCIAL FETCH (only for survivors, budgeted & cached) 🟡                          │
 │                         │                                                          │
 │        ┌────────────────┼────────────────┐                                         │
 │        ▼                ▼                ▼                                         │
 │  🕵️ DETECTIVE      🎯 SNIPER        🧪 PROFESSOR (final call)                        │
 │  X community       big accts/news   on-chain + DexScreener                          │
 │  vote + score      vote + score     vote + score + veto                             │
 │        └────────────────┼────────────────┘                                         │
 │                         ▼                                                          │
 │  🟢 CONSENSUS 3/3  →  🟢 CONFIDENCE SCORE (0–100)  →  🟢 POSITION SIZE               │
 │                         │                                                          │
 │                         ▼                                                          │
 │  🟢 PAPER BROKER (SOL) · 🟡 TP +40% · SL ~−22% · trailing · time stop · rug exit     │
 │                         │                                                          │
 │                         ▼                                                          │
 │  🟢 JOURNAL · BLACKBOARD · LESSONS · VERSION TABLE · 100-TRADE COUNTER              │
 │  🟢 WEB DASHBOARD                                                                    │
 └────────────────────────────────────────────────────────────────────────────────────┘
```

---

<a id="9"></a>
## 9. مواصفات البناء التفصيلية

### 9.1 التقنيات

| الطبقة | الاختيار | ملاحظة |
|---|---|---|
| اللغة | Python 3.11+ (asyncio) | |
| LLM | Anthropic API (فريق Claude)، OpenAI API (الفريق المنافس، اختياري) | استخدم نموذجاً سريعاً للتصويت ونموذجاً أقوى للـ Post-mortem |
| الإطلاقات | PumpPortal Data API (WebSocket): `subscribeNewToken`، `subscribeMigration`، `subscribeTokenTrade` | بث مجاني للأحداث |
| السوق | DexScreener API: `/token-profiles/latest/v1`، `/latest/dex/tokens/{mint}` | التزم بحدود المعدل (ظهر خطأ 429 في الفيديو) |
| الأمان | RugCheck API + قراءة on-chain (Solana RPC: Helius/QuickNode) للـ mint/freeze authority وأكبر الحاملين | |
| X | X API الرسمي بميزانية محكومة (القسم 11) | |
| التخزين | Postgres على Railway (أو SQLite على Volume دائم) | |
| الواجهة | FastAPI + HTML/JS | |
| الاستضافة | Railway، نسخة واحدة (1 replica) | |

### 9.2 قاعدة البيانات

```sql
CREATE TABLE tokens (
  mint TEXT PRIMARY KEY, symbol TEXT, name TEXT, creator TEXT,
  first_seen_at BIGINT, migrated_at BIGINT, source TEXT
);
CREATE TABLE snapshots (
  id BIGSERIAL PRIMARY KEY, mint TEXT, ts BIGINT,
  price_usd DOUBLE PRECISION, liquidity_usd DOUBLE PRECISION,
  vol_m5 DOUBLE PRECISION, vol_h1 DOUBLE PRECISION,
  buys_m5 INT, sells_m5 INT, price_change_m5 DOUBLE PRECISION,
  fdv DOUBLE PRECISION, age_min DOUBLE PRECISION, raw JSONB
);
CREATE TABLE safety_reports (
  mint TEXT, ts BIGINT, mint_authority_revoked BOOL, freeze_authority_revoked BOOL,
  top10_pct DOUBLE PRECISION, dev_pct DOUBLE PRECISION, lp_status TEXT,
  bundle_pct DOUBLE PRECISION, rug_score DOUBLE PRECISION, ok BOOL, raw JSONB
);
CREATE TABLE candidates (                 -- "CANDIDATE BOARD"
  id BIGSERIAL PRIMARY KEY, mint TEXT, ts BIGINT, passed BOOL, reasons TEXT[]
);
CREATE TABLE social_cache (
  query TEXT PRIMARY KEY, fetched_at BIGINT, posts JSONB, cost_units INT
);
CREATE TABLE votes (
  id BIGSERIAL PRIMARY KEY, team TEXT, version TEXT, mint TEXT, ts BIGINT,
  agent TEXT, vote TEXT, score INT, reason TEXT, red_flags TEXT[]
);
CREATE TABLE decisions (
  id BIGSERIAL PRIMARY KEY, team TEXT, version TEXT, mint TEXT, ts BIGINT,
  consensus BOOL, confidence INT, size_sol DOUBLE PRECISION, taken BOOL
);
CREATE TABLE positions (
  id BIGSERIAL PRIMARY KEY, team TEXT, version TEXT, mint TEXT, symbol TEXT,
  decision_id BIGINT, confidence INT, size_sol DOUBLE PRECISION,
  opened_at BIGINT, closed_at BIGINT, entry_price DOUBLE PRECISION,
  exit_price DOUBLE PRECISION, peak_return_pct DOUBLE PRECISION,
  return_pct DOUBLE PRECISION, fees_sol DOUBLE PRECISION, pnl_sol DOUBLE PRECISION,
  exit_reason TEXT, mode TEXT DEFAULT 'paper'
);
CREATE UNIQUE INDEX one_open_per_token ON positions(team, mint) WHERE closed_at IS NULL;
CREATE TABLE lessons (
  id BIGSERIAL PRIMARY KEY, team TEXT, agent TEXT, ts BIGINT, mint TEXT,
  lesson TEXT, active BOOL DEFAULT TRUE
);
CREATE TABLE blackboard (
  id BIGSERIAL PRIMARY KEY, team TEXT, ts BIGINT, mint TEXT, symbol TEXT,
  agent TEXT, topic TEXT, note TEXT
);
CREATE TABLE spend_ledger (               -- tracks X / LLM / RPC costs
  id BIGSERIAL PRIMARY KEY, ts BIGINT, service TEXT, units INT, usd DOUBLE PRECISION
);
```

### 9.3 إعدادات V7

```yaml
version: V7
mode: paper
chain: solana
quote: SOL

sizing:
  base_size_sol: 0.0205          # seen in the video
  min_confidence_to_trade: 70    # inferred
  size_multiplier:               # linear map confidence -> multiplier (inferred)
    at_70: 0.5
    at_85: 1.0
    at_100: 1.5
  max_size_sol: 0.035
  max_open_positions: 3
  max_daily_loss_sol: 0.06

filters:
  min_liquidity_usd: 10000
  min_volume_m5_usd: 5000
  min_buy_sell_ratio_m5: 1.2
  min_age_minutes: 3             # avoid first-seconds sniper chaos (inferred)
  max_age_minutes: 180
  max_price_change_m5_pct: 150   # already parabolic = late

safety:
  require_mint_authority_revoked: true
  require_freeze_authority_revoked: true
  max_top10_holders_pct: 30
  max_dev_holding_pct: 5
  max_bundle_pct: 20
  block_on_api_error: true

consensus:
  rule: unanimous
  professor_veto: true
  weights: {professor: 0.45, sniper: 0.30, detective: 0.25}

exits:
  take_profit_pct: 40
  stop_loss_pct: -22
  trailing: {activate_at_pct: 20, trail_pct: 12}
  time_stop_minutes: 10
  rug_liquidity_drop_pct: 50     # liquidity falls 50% from entry -> exit immediately

costs:
  fee_pct_per_side: 1.0
  slippage_pct_per_side: 2.0
  network_fee_sol: 0.0001

social:
  enabled: true
  max_posts_per_token: 25
  cache_minutes: 10
  hourly_budget_usd: 2.0
  daily_budget_usd: 20.0
  on_budget_exhausted: detective_and_sniper_vote_pass_with_reason

runtime:
  price_poll_seconds: 3
  single_instance: true
```

---

<a id="10"></a>
## 10. Confidence Score وتحديد حجم الصفقة

### 10.1 الفكرة (من الجزء 2)
«صار AI يعطي كل فرصة يشوفها Confidence Score، ويحدد حجم الصفقة على أساسه.» العداد في الفيديو 0–100 بتدرج أحمر/أصفر/أخضر، وشريط «حجم الصفقة» يمتلئ بنسبة الدرجة.

### 10.2 التصميم المقترح (مرجّح)
1. كل Agent يعيد `vote` (BUY/PASS) و`score` (0–100).
2. **البوابة:** الثلاثة BUY (إجماع) والبروفيسور لم يستخدم الفيتو.
3. **الدرجة المركّبة** = متوسط موزون: البروفيسور 0.45، القنّاص 0.30، المحقق 0.25، **مع خصم** 10 نقاط لكل علامة حمراء أمنية بسيطة.
4. **الحد الأدنى للتداول:** 70. تحته لا صفقة حتى لو وُجد إجماع.
5. **الحجم:** خطي من 0.5× عند 70، إلى 1.0× عند 85، إلى 1.5× عند 100، بحد أقصى ثابت.

```python
def composite_score(votes: dict, weights: dict, penalties: int = 0) -> int:
    s = sum(votes[a]["score"] * w for a, w in weights.items())
    return max(0, min(100, round(s - 10 * penalties)))

def size_for(score: int, cfg: dict) -> float:
    m = cfg["sizing"]["size_multiplier"]
    if score < cfg["sizing"]["min_confidence_to_trade"]:
        return 0.0
    if score <= 85:
        mult = m["at_70"] + (score - 70) / 15 * (m["at_85"] - m["at_70"])
    else:
        mult = m["at_85"] + (score - 85) / 15 * (m["at_100"] - m["at_85"])
    return min(cfg["sizing"]["base_size_sol"] * mult, cfg["sizing"]["max_size_sol"])
```

### 10.3 لماذا لا تثق بالدرجة مباشرة
درجات النماذج اللغوية **غير معايَرة** افتراضياً: «87» لا تعني احتمال ربح 87%. لذلك يجب ربط الدرجة بالنتائج الفعلية.

### 10.4 المعايرة (Calibration): إلزامية خلال اختبار الـ 100
قسّم الصفقات حسب الدرجة واحسب الإصابة الفعلية:

| فئة الدرجة | عدد الصفقات | الإصابة الفعلية | متوسط العائد |
|---|---|---|---|
| 70–79 | … | … | … |
| 80–89 | … | … | … |
| 90–100 | … | … | … |

**قاعدة القبول:** إذا لم تكن الفئات الأعلى أفضل فعلاً (إصابة أعلى وعائد أعلى)، فالدرجة لا تضيف شيئاً، وعندها **ارجع لحجم ثابت**. ورصد أيضاً Brier score للاحتمال المستنتج من الدرجة.

---

<a id="11"></a>
## 11. طبقة بيانات X: المشكلة، والحل الذي في الفيديو، والحل الآمن

### 11.1 المشكلة كما شُرحت
- المحقق والقنّاص يعتمدان على X.
- البوت كان يسحب **2000 بوست/ساعة** بغض النظر عن جودة العملة.
- رصيد X API نفد **مرتين خلال 12 دقيقة**، أي **−$40**.

### 11.2 ما فعله صاحب الفيديو (للعلم فقط)
أداة تفتح نتائج البحث في متصفح بجلسة تسجيل دخول منقولة عبر إضافة Cookie-Editor، وتستخرج المنشورات إلى JSON، من **حساب منفصل** لأن ذلك **يخالف شروط X**.

> ⛔ **لا يتضمن هذا الملف تنفيذاً لهذه الطريقة.** هي مخالفة صريحة لشروط الخدمة، وتعرّض الحساب للإيقاف، وقد تعرضك لتبعات قانونية. كذلك: البوت يتوقف فجأة عند انتهاء الجلسة أو حظر الحساب، وهذا يكسر الاختبار في منتصفه ويُفسد إحصاءات الـ 100 صفقة.

### 11.3 الحل الآمن والأرخص: سحب ذكي بدل سحب كثيف
السبب الحقيقي للمشكلة **تصميمي**: السحب يحدث قبل الفلترة. الإصلاح:

| الإجراء | الأثر |
|---|---|
| **اسحب X فقط للعملات التي اجتازت الفلتر الرقمي والأمان** | من آلاف العملات إلى عشرات يومياً (−99%) |
| حد أقصى 25 منشوراً لكل عملة، وفلتر `-is:retweet` | −80% من الحجم لكل استعلام |
| كاش 10 دقائق لكل رمز/عنوان | لا تكرار للسحب |
| **حارس ميزانية بالكود** (ساعة/يوم) يوقف السحب عند الحد | لا مفاجآت مثل −$40 |
| عند نفاد الميزانية: المحقق والقنّاص يصوتان PASS مع السبب | أمان افتراضي، ويُسجَّل للتحليل |
| مصادر اجتماعية بديلة مسموحة: روابط X/Telegram/الموقع في ملف DexScreener، وعمر الحساب وعدد المتابعين عبر API رسمي، ومزودو بيانات مرخّصون | تقليل الاعتماد على البحث المفتوح |

**حساب مثال:** لو مرّ 15 مرشحاً في الساعة × 25 منشوراً = **375 منشوراً/ساعة** بدل 2000، وأغلبها من الكاش. **التكلفة تنخفض بأكثر من 80% قبل الكاش.**

```python
# app/sources/budget.py
import time

class SpendGuard:
    def __init__(self, db, hourly_usd, daily_usd):
        self.db, self.h, self.d = db, hourly_usd, daily_usd

    def allow(self, service: str, est_usd: float) -> bool:
        now = int(time.time())
        spent_h = self.db.spend_since(service, now - 3600)
        spent_d = self.db.spend_since(service, now - 86400)
        return spent_h + est_usd <= self.h and spent_d + est_usd <= self.d

    def record(self, service: str, units: int, usd: float):
        self.db.insert_spend(service, units, usd)
```

---

<a id="12"></a>
## 12. الكود الهيكلي (Python)

> هيكل عملي في وضع Paper. **لا يحتوي على تنفيذ أوامر حقيقية.**

### 12.1 هيكل المشروع
```
memecoin-agents/
├── Dockerfile
├── railway.json
├── requirements.txt
├── config/v7.yaml
├── app/
│   ├── main.py            # orchestrator + single-instance guard
│   ├── db.py
│   ├── sources/
│   │   ├── pumpportal.py  # launches & migrations (WebSocket)
│   │   ├── dexscreener.py # market snapshots (rate-limited)
│   │   ├── safety.py      # authorities, holders, rugcheck
│   │   ├── social.py      # budgeted, cached X fetch (official API)
│   │   └── budget.py
│   ├── filters.py
│   ├── agents/{base,detective,sniper,professor}.py
│   ├── sizing.py          # composite_score + size_for (section 10.2)
│   ├── consensus.py       # 3/3 + composite score + sizing
│   ├── paper_broker.py
│   ├── lessons.py
│   ├── metrics.py         # version table, Wilson CI, calibration
│   └── web.py             # FastAPI dashboard + /health
```

### 12.2 الإطلاقات والسوق
```python
# app/sources/pumpportal.py
import asyncio, json, websockets

async def stream(queue: asyncio.Queue):
    uri = "wss://pumpportal.fun/api/data"
    backoff = 1
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                await ws.send(json.dumps({"method": "subscribeMigration"}))
                backoff = 1
                async for raw in ws:
                    d = json.loads(raw)
                    if "mint" in d:
                        await queue.put({"mint": d["mint"], "symbol": d.get("symbol"),
                                         "event": d.get("txType", "migrate")})
        except Exception:
            await asyncio.sleep(backoff); backoff = min(backoff * 2, 60)
```

```python
# app/sources/dexscreener.py
import asyncio, time, httpx

class DexScreener:
    BASE = "https://api.dexscreener.com"
    def __init__(self, concurrency=4):
        self.c = httpx.AsyncClient(timeout=10); self.sem = asyncio.Semaphore(concurrency)

    async def _get(self, path):
        async with self.sem:
            for i in range(5):
                r = await self.c.get(self.BASE + path)
                if r.status_code == 429:
                    await asyncio.sleep(2 ** i); continue
                r.raise_for_status(); return r.json()
        raise RuntimeError("DexScreener rate-limited")

    async def snapshot(self, mint):
        data = await self._get(f"/latest/dex/tokens/{mint}")
        pairs = [p for p in (data.get("pairs") or []) if p.get("chainId") == "solana"]
        if not pairs: return None
        p = max(pairs, key=lambda x: (x.get("liquidity") or {}).get("usd", 0))
        m5 = (p.get("txns") or {}).get("m5", {})
        created = p.get("pairCreatedAt") or 0
        return {
            "mint": mint, "symbol": p["baseToken"]["symbol"], "ts": int(time.time()),
            "price_usd": float(p.get("priceUsd") or 0),
            "liquidity_usd": (p.get("liquidity") or {}).get("usd", 0),
            "vol_m5": (p.get("volume") or {}).get("m5", 0),
            "vol_h1": (p.get("volume") or {}).get("h1", 0),
            "buys_m5": m5.get("buys", 0), "sells_m5": m5.get("sells", 0),
            "price_change_m5": (p.get("priceChange") or {}).get("m5", 0),
            "age_min": (time.time() * 1000 - created) / 60000 if created else None,
            "socials": (p.get("info") or {}).get("socials", []),
            "url": p.get("url"),
        }
```

### 12.3 الفلتر والأمان
```python
# app/filters.py
def market_filter(s, cfg):
    f, r = cfg["filters"], []
    if s["liquidity_usd"] < f["min_liquidity_usd"]: r.append("low liquidity")
    if s["vol_m5"] < f["min_volume_m5_usd"]:         r.append("low 5m volume")
    if s["buys_m5"] / max(s["sells_m5"], 1) < f["min_buy_sell_ratio_m5"]:
        r.append("buyers do not lead")
    if s["age_min"] is not None and not (f["min_age_minutes"] <= s["age_min"] <= f["max_age_minutes"]):
        r.append("age out of window")
    if s["price_change_m5"] > f["max_price_change_m5_pct"]: r.append("already parabolic")
    return not r, r

def safety_gate(rep, cfg):
    s, r = cfg["safety"], []
    if rep is None:
        return (False, ["BLOCK: safety data unavailable"]) if s["block_on_api_error"] else (True, [])
    if s["require_mint_authority_revoked"] and not rep["mint_authority_revoked"]: r.append("mint authority active")
    if s["require_freeze_authority_revoked"] and not rep["freeze_authority_revoked"]: r.append("freeze authority active")
    if rep["top10_pct"] > s["max_top10_holders_pct"]: r.append("top10 concentrated")
    if rep["dev_pct"] > s["max_dev_holding_pct"]: r.append("dev holds too much")
    if rep.get("bundle_pct", 0) > s["max_bundle_pct"]: r.append("bundled launch")
    return not r, r
```

### 12.4 الـ Agent بدرجة ثقة
```python
# app/agents/base.py
import json, os
from anthropic import AsyncAnthropic
client = AsyncAnthropic()
MODEL = os.environ["CLAUDE_VOTE_MODEL"]

SCHEMA = ('Return ONLY JSON: {"vote":"BUY"|"PASS","score":0-100,'
          '"reason":"<=40 words","red_flags":["..."]}. '
          'score = your confidence that this trade reaches +40% before -22%.')

class Agent:
    name = system = ""
    def __init__(self, lessons): self.lessons = lessons

    async def vote(self, ctx):
        sys = (self.system + "\n\nLESSONS:\n" +
               "\n".join("- " + l for l in self.lessons.active(self.name, 10)) + "\n\n" + SCHEMA)
        m = await client.messages.create(model=MODEL, max_tokens=300, temperature=0.2, system=sys,
              messages=[{"role": "user", "content": json.dumps(ctx, ensure_ascii=False, default=str)}])
        try:
            o = json.loads(m.content[0].text)
            assert o["vote"] in ("BUY", "PASS") and 0 <= int(o["score"]) <= 100
            o["score"] = int(o["score"])
        except Exception:
            o = {"vote": "PASS", "score": 0, "reason": "invalid output", "red_flags": []}
        return o
```

### 12.5 الإجماع والحجم
```python
# app/consensus.py
import asyncio
from .sizing import composite_score, size_for   # functions from section 10.2

async def decide(agents, ctx, cfg, db):
    res = await asyncio.gather(*(a.vote(ctx) for a in agents))
    votes = {a.name: v for a, v in zip(agents, res)}
    for n, v in votes.items():
        db.save_vote(n, ctx["mint"], v); db.blackboard(n, ctx, v["reason"])
    unanimous = all(v["vote"] == "BUY" for v in votes.values())
    if cfg["consensus"]["professor_veto"] and votes["professor"]["vote"] == "PASS":
        unanimous = False
    score = composite_score(votes, cfg["consensus"]["weights"], penalties=ctx.get("minor_flags", 0))
    size = size_for(score, cfg) if unanimous else 0.0
    db.save_decision(ctx["mint"], unanimous, score, size, taken=size > 0)
    return size, score, votes
```

### 12.6 الوسيط الورقي (مع كشف Rug)
```python
# app/paper_broker.py
import asyncio, time

class PaperBroker:
    def __init__(self, cfg, db, dex):
        self.cfg, self.db, self.dex = cfg, db, dex
        c = cfg["costs"]; self.k = (c["fee_pct_per_side"] + c["slippage_pct_per_side"]) / 100

    async def open(self, snap, size_sol, score):
        if self.db.has_open(snap["mint"]) or self.db.open_count() >= self.cfg["sizing"]["max_open_positions"]:
            return None
        if self.db.realized_today() <= -self.cfg["sizing"]["max_daily_loss_sol"]:
            return None
        return self.db.insert_position(mint=snap["mint"], symbol=snap["symbol"],
            version=self.cfg["version"], confidence=score, size_sol=size_sol,
            entry_price=snap["price_usd"] * (1 + self.k), entry_liq=snap["liquidity_usd"],
            opened_at=int(time.time()))

    async def monitor(self, pos):
        ex, peak = self.cfg["exits"], 0.0
        while True:
            s = await self.dex.snapshot(pos["mint"])
            if s is None or s["liquidity_usd"] < pos["entry_liq"] * (1 - ex["rug_liquidity_drop_pct"] / 100):
                px = (s["price_usd"] if s else pos["entry_price"] * 0.3) * (1 - self.k * 3)
                return self.close(pos, px, "RUG")
            bid = s["price_usd"] * (1 - self.k)
            ret = (bid / pos["entry_price"] - 1) * 100; peak = max(peak, ret)
            held = (time.time() - pos["opened_at"]) / 60
            if ret >= ex["take_profit_pct"]: return self.close(pos, bid, "TP", peak)
            if ret <= ex["stop_loss_pct"]:  return self.close(pos, bid, "SL", peak)
            t = ex["trailing"]
            if peak >= t["activate_at_pct"] and ret <= peak - t["trail_pct"]:
                return self.close(pos, bid, "TRAIL", peak)
            if held >= ex["time_stop_minutes"]: return self.close(pos, bid, "TIME", peak)
            await asyncio.sleep(self.cfg["runtime"]["price_poll_seconds"])

    def close(self, pos, px, reason, peak=None):
        r = px / pos["entry_price"] - 1
        pnl = pos["size_sol"] * r - 2 * self.cfg["costs"]["network_fee_sol"]
        return self.db.close_position(pos["id"], px, r * 100, pnl, reason, peak, int(time.time()))
```

### 12.7 المقاييس والمعايرة
```python
# app/metrics.py
from math import sqrt

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z*z/n; c = (p + z*z/(2*n)) / d
    m = z * sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (c - m, c + m)

def summary(trades):
    n = len(trades); wins = [t for t in trades if t["return_pct"] > 0]
    gw = sum(t["return_pct"] for t in wins)
    gl = -sum(t["return_pct"] for t in trades if t["return_pct"] <= 0)
    return {"n": n, "hit": len(wins) / n if n else 0, "ci95": wilson(len(wins), n),
            "pnl_sol": sum(t["pnl_sol"] for t in trades),
            "profit_factor": gw / gl if gl else None,
            "worst": min((t["return_pct"] for t in trades), default=0)}

def calibration(trades, buckets=((70, 79), (80, 89), (90, 100))):
    return {f"{a}-{b}": summary([t for t in trades if a <= t["confidence"] <= b])
            for a, b in buckets}
```

### 12.8 حماية النسخة الواحدة على السحابة
على Railway لا يكفي قفل ملف محلي إذا وُجدت نسختان. استخدم **قفلاً في قاعدة البيانات**:
```python
# app/main.py (excerpt) - Postgres advisory lock
async def acquire_singleton(conn):
    ok = await conn.fetchval("SELECT pg_try_advisory_lock(424242)")
    if not ok:
        raise SystemExit("Another instance holds the lock - exiting (prevents duplicate bets).")
```

---

<a id="13"></a>
## 13. البرومبتات

### 13.1 System Prompts (مع الدرجة)

**THE DETECTIVE**
```
You are THE DETECTIVE (SCOUT), reading the X community around a Solana memecoin.
Input: market snapshot + up to 25 recent posts (author age, followers, text, likes).
BUY only if chatter is organic, growing, from many distinct aged accounts, and mentions a reason
(meme, event, narrative). Copy-paste shilling or brand-new accounts = PASS.
If social data is missing or budget-exhausted, vote PASS with score 0 and say so.
Score = confidence the token hits +40% before -22% within 10 minutes.
```

**THE SNIPER**
```
You are THE SNIPER (HUNTER): big accounts and news.
BUY only for a fresh (<60 min) narrative-driven catalyst confirmed by a credible large account
or a real news item. Unconfirmed volume spikes are not catalysts. Patience beats chasing.
Score = confidence the token hits +40% before -22% within 10 minutes.
```

**THE PROFESSOR**
```
You are THE PROFESSOR (ANALYST) with the FINAL CALL and a veto.
Input: DexScreener snapshot, safety report (authorities, top10%, dev%, LP, bundles), colleagues' votes.
BUY only with real momentum (rising 5m volume, buyers leading), healthy liquidity, clean safety,
and price not already parabolic. Most tokens show no real momentum; PASS is normal.
Score honestly: 70 = barely acceptable, 85 = strong, 95+ = exceptional and rare.
```

### 13.2 برومبتات Claude Code لإعادة مسار الجزء 2

**إصلاح تكلفة X:**
```
Our X API credits ran out twice in 12 minutes (~2000 posts/hour, -$40).
Refactor so social data is fetched ONLY for tokens that passed the market filter and safety gate.
Add: per-token cap of 25 posts, 10-minute cache, a SpendGuard with hourly and daily USD budgets
recorded in spend_ledger, and a safe fallback (Detective/Sniper vote PASS when budget is exhausted).
Show me the expected posts/hour before and after.
```

**النقل للسحابة:**
```
Prepare this bot for Railway: Dockerfile, railway.json with 1 replica and restart on failure,
Postgres instead of SQLite, a /health endpoint, structured logs, env-based config,
and a Postgres advisory lock so only one instance can trade.
```

**Confidence Score (V7):**
```
Each agent must now return a 0-100 score (confidence of +40% before -22% within 10 minutes).
Compute a weighted composite (Professor 0.45, Sniper 0.30, Detective 0.25), trade only if
unanimous and composite >= 70, and size the position linearly 0.5x-1.5x of base 0.0205 SOL.
Store confidence on every position and add a calibration report by score bucket.
```

**مراجعة كل 10 صفقات:**
```
Here are the last 10 closed V7 trades with votes, scores, exit reasons and peak returns.
Do NOT change parameters. Report: hit rate with Wilson CI, profit factor, worst trade,
calibration by score bucket, duplicated trades, and any rug/slippage anomalies.
```

---

<a id="14"></a>
## 14. التشغيل 24/7 على Railway

### 14.1 لماذا
«إذا سكرت اللابتوب… البوت نايم معي». أي توقف يُفسد اختبار الـ 100 صفقة (صفقات مفتوحة بلا مراقبة، وفرص ضائعة غير مسجلة).

### 14.2 الملفات
```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "app.main"]
```

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "DOCKERFILE" },
  "deploy": {
    "numReplicas": 1,
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### 14.3 نقاط إلزامية
- **نسخة واحدة فقط** (`numReplicas: 1`) + قفل Postgres (12.8). هذا يمنع تكرار الصفقات الذي ظهر في V1 وV7.
- المفاتيح (Anthropic، X، RPC) في **Variables**، وليست في الكود.
- **عند إعادة التشغيل:** يقرأ البوت المراكز المفتوحة من قاعدة البيانات ويستأنف مراقبتها.
- تنبيه (Telegram/Discord webhook) عند: فتح أو إغلاق صفقة، نفاد ميزانية، خطأ 429 متكرر، توقف تيار PumpPortal أكثر من دقيقتين.
- راقب تكلفة Railway نفسها ضمن `spend_ledger`.

---

<a id="15"></a>
## 15. مسار الإصدارات V1 → V7 وخارطة V8

| الإصدار | النتيجة | التغيير (ظاهر/مرجّح) | الدرس |
|---|---|---|---|
| V1 | 2 خسارة (مكررة) | Agent واحد | نسختان متزامنتان، ووقف −23.7% خلال 4 دقائق |
| V2 | 41 · 41% · −0.0209 | 3 Agents + إجماع | الإجماع وحده لا يكفي |
| V3 | 20 · 35% · −0.0213 | تشديد | أسوأ |
| V4 | 20 · 35% · −0.0229 | تعديلات مصادر | لا تحسن |
| V5 | 49 · 53% · −0.0954 | اختبار مستمر | إصابة أعلى وخسارة أكبر: الـ Rugs تأكل كل شيء |
| V6 | 7 · 57% · −0.0234 | فلاتر أشد | احتفاظ قصير جداً، وخسائر −40% و−55% |
| **V7** | **10 · 80% · +0.0438** | 🟢 Confidence Score + حجم متغير، 🟢 Railway، 🟢 حل مشكلة X، 🟡 TP +40% واحتفاظ أطول | أول نسخة رابحة، والعينة صغيرة |

**أفكار V8 (اختبرها واحدة تلو الأخرى بعد انتهاء الـ 100):**
1. **خروج جزئي:** بيع 50% عند +40% وترك الباقي بوقف تتبعي (تشير ذروة العوائد إلى أن بعضها يتجاوز +40%).
2. **فلتر Rug أقوى:** رفض أي عملة يملك أكبر 10 حاملين فيها أكثر من 25%، أو فيها Bundle > 10%.
3. **Wallet Performance Scout** من فريق ChatGPT كـ Agent رابع استشاري (وجود محافظ رابحة تاريخياً بين المشترين).
4. **نافذة توقيت:** تحليل أداء الصفقات حسب ساعة اليوم.

> القاعدة الذهبية: **تغيير واحد لكل إصدار، وعدد صفقات محدد مسبقاً، وجدول إصدارات واحد.**

---

<a id="16"></a>
## 16. بروتوكول اختبار الـ 100 صفقة

### 16.1 قبل البدء
- **جمّد** كل الإعدادات والبرومبتات (Git tag `v7-test-100`).
- الدروس تُسجَّل فقط ولا تُحقن أثناء الاختبار، **أو** تُحقن بشكل ثابت من البداية. اختر واحداً ولا تغيّر في المنتصف.
- عدّ **الصفقات الفريدة** فقط.

### 16.2 شروط النجاح (كلها مطلوبة)
| الشرط | الحد |
|---|---|
| الحد الأدنى لفاصل Wilson 95% للإصابة | أعلى من نقطة التعادل الفعلية `avg_loss / (avg_win + avg_loss)` |
| Profit Factor بعد التكاليف | ≥ 1.5 |
| أكبر تراجع | ≤ 25% من رأس المال الورقي |
| تركّز الربح | لا تزيد أي صفقة واحدة عن 30% من الربح |
| المعايرة | الفئة 80+ أفضل من الفئة 70–79 |
| تكاليف التشغيل (LLM + X + RPC + Railway) | أقل من الربح الورقي |

### 16.3 نقاط تفتيش
كل 10 صفقات: تقرير (13.2 «مراجعة كل 10 صفقات») **بدون تعديل**. أوقف مبكراً فقط إذا: Profit Factor < 0.8 بعد 40 صفقة، أو تراجع > 35%.

---

<a id="17"></a>
## 17. الانتقال من Paper إلى أموال حقيقية

> يبدأ فقط بعد اجتياز القسم 16. ليس نصيحة مالية.

### 17.1 طبقة التنفيذ (نظرة عامة)
- **التوجيه:** مجمّع مثل Jupiter (Quote ثم Swap)، أو واجهة تداول pump.fun/PumpSwap عبر مزود مثل PumpPortal، أو بناء المعاملة محلياً وتوقيعها بمحفظتك.
- **Priority fee** وإرسال محمي من MEV (مثل bundles عبر Jito) لتقليل الـ Sandwich.
- **Slippage أقصى** محدد (مثلاً 3–5%)؛ إذا تجاوز السعرُ الحدَّ تُلغى الصفقة بدل الشراء بأي سعر.
- **التحقق بعد التنفيذ:** سعر الدخول الفعلي مقابل المفترض، وتسجيل الفرق.

### 17.2 قواعد السلامة
1. **محفظة ساخنة منفصلة** لا تحوي إلا مبلغ الاختبار. المفتاح الخاص في Railway Variables فقط، وليس في Git أبداً.
2. نفس الحجم الصغير (~0.02 SOL) لأول **50 صفقة حقيقية**.
3. قارن **الانزلاق الحقيقي** بالمفترض (2% لكل اتجاه في الإعدادات). إذا كان الفعلي أعلى بكثير، فقد تختفي ميزة الاستراتيجية بالكامل.
4. مفاتيح إيقاف: 3 خسائر متتالية ≤ −20% تعني توقف 24 ساعة؛ خسارة يومية ≥ الحد تعني توقفاً لليوم؛ فشل أي مصدر أمان يعني لا دخول.
5. `mode: live` يتطلب متغير بيئة صريحاً إضافياً (`ALLOW_LIVE=yes`) حتى لا يُفعَّل بالخطأ.

---

<a id="18"></a>
## 18. دليل إعادة إنتاج الفيديو (Motion Design)

### 18.1 الفرق بين الجزأين

| العنصر | الجزء 1 | الجزء 2 |
|---|---|---|
| التصوير | لقطة مكتب واسعة | سيلفي قريب بالجوال (أكثر حميمية وسرعة) |
| العنوان الثابت | كبسولة نيون أعلى الشاشة | لا يوجد |
| التخطيط الأساسي | جرافيك أعلى + ترجمة + فيديو المتحدث بإطار مستدير | نفس الشيء بدون عنوان |
| اللقطات الخاصة | لقطة كبيرة مع نصف سفلي ضبابي | سيلفي كامل الشاشة + ومضات أبيض وأسود + لقطة مكتب واسعة مع نصف ضبابي |

### 18.2 التخطيط (720×1280)
```
y≈0–640    منطقة الجرافيك (بطاقات، عدادات، جداول)
y≈690–770  الترجمة (1–3 كلمات، خط ~44–48px، كلمة مفتاحية ملوّنة)
y≈790–1205 فيديو المتحدث في إطار بزوايا ~16px، هامش ~26px
بديل: سيلفي كامل الشاشة، والترجمة عند y≈900–960
```

### 18.3 الألوان (مقاسة من الإطارات)
| الاستخدام | اللون |
|---|---|
| الخلفية | `#0B0C11` (توهج أخضر خفيف `#0C1516`) |
| أخضر نيون (إيجابي، أرقام) | `#20C878` |
| أحمر (مشكلة، خسارة، «يخالف الشروط») | `#F85860` |
| أصفر/برتقالي (عناوين تنبيه، «الاختبار الحقيقي»، إطار الصف المختار) | `#F0B840` |
| برتقالي Claude | `#E08858` |
| أبيض النص | `#FFFFFF` مع ظل ناعم |

### 18.4 الخطوط
عربي عريض جداً قريب من **Cairo Black / Alexandria** (الخط الأصلي غير مؤكد)، ولاتيني عريض للأرقام.

### 18.5 مكتبة حركات الجزء 2
1. **«V7» نيون** يتوهج + صف جدول + 3 كبسولات إحصاء تظهر تباعاً.
2. **3 بطاقات شخصيات** تدخل بـ Pop، ثم تُبعد البطاقة الوسطى لإبراز المعتمدين على X مع **خطوط متقطعة صفراء**.
3. **كبسولة مشكلة حمراء** («المشكلة الأولى»).
4. **بطارية رصيد** خضراء 100% تفرغ إلى الأحمر، مع **ساعة دائرية** يمتلئ قطاعها، وعدّاد «بوست بالساعة» يعدّ إلى 2000، ثم «**−$40**» أحمر متوهج «في 12 دقيقة».
5. **نافذة متصفح وهمية** (نقاط macOS الثلاث) مع منشورات رمادية وتيار JSON أخضر على اليمين.
6. **لقطة صفحة حقيقية** (Cookie-Editor) مع إطار أصفر متوهج على العنوان.
7. **بطاقتا حساب** (✓ أخضر / ✗ أحمر) + **ختم مائل «يخالف الشروط»**.
8. **سحابة + 3 خوادم** بنقاط خضراء تومض (نشاط) + كبسولة «على الكلاود · 24 ساعة».
9. **جدول الإصدارات** مع إطار أصفر متنقل ومربع أحمر على عمود Wins، ثم **✗ حمراء** تتساقط على الصفوف، ثم إطار **أخضر** على V7.
10. **عداد Confidence Score** نصف دائري بتدرج أحمر ← أصفر ← أخضر، والإبرة تتحرك (0 ← 37 ← 79 ← 87)، و**شريط «حجم الصفقة»** يمتلئ بالتوازي.
11. **شبكة 10 مربعات** (✓/✗) + «8 / 10» كبير.
12. **حلقة تقدم دائرية** «الاختبار الحقيقي n/100».
13. **بطاقة CTA** بأيقونات ❤ 💬 ➤ 🔖 + «نتيجة الـ 100 صفقة: خسارة أو ربح».
14. **ومضات أبيض وأسود** على الكلمات الثقيلة («مشكلتين»، «نايم»، «أقنعتني»).

### 18.6 الإيقاع وخط الإنتاج
- تغيير بصري كل 1.5–3 ث، والترجمة تتغير كل 0.3–0.6 ث.
- Hook بالنتيجة في أول 8 ثوانٍ، وCliffhanger في النهاية.
- الإنتاج: تصوير سيلفي، ثم الأنيميشن في After Effects أو Remotion أو قوالب CapCut، ثم Auto Captions مع تلوين يدوي، ثم تصدير 1080×1920، 30fps، H.264، AAC، وذروة صوت حوالي −1 dB.

---

<a id="19"></a>
## 19. المخاطر والتنبيهات

- **ليست نصيحة مالية.** عملات الميم من أعلى الأصول مخاطرة، وأغلبها يذهب إلى الصفر. لا تتداول إلا بمبلغ تتحمل خسارته بالكامل.
- **النتيجة غير مثبتة:** 10 صفقات ورقية، وصاحب الفيديو نفسه يقول إنه لا يستطيع الجزم.
- **الانزلاق الحقيقي** في السيولة المنخفضة قد يمحو هامش V7 بالكامل.
- **خسارة Rug واحدة (−50%)** تحتاج ربحين بـ+40% لتعويضها.
- **التكاليف التشغيلية** (X، وLLM، وRPC، وRailway) قد تتجاوز الأرباح؛ الجزء 2 أثبت ذلك (−$40 في 12 دقيقة).
- **سحب X عبر الكوكيز** مخالف للشروط: إيقاف الحساب، ومخاطر قانونية، وتوقف مفاجئ يفسد الاختبار.
- **الأمان:** محفظة منفصلة، ومفاتيح في متغيرات البيئة فقط، وحد يومي للخسارة، و`ALLOW_LIVE` صريح.
- **الضرائب:** في ألمانيا، أرباح العملات الرقمية المحتفظ بها أقل من سنة تُعامل كدخل خاضع للضريبة (مع حد إعفاء سنوي من نوع Freigrenze: إذا تجاوزته يُحسب الربح كله)، والتداول الآلي الكثيف يولّد سجلاً ضخماً. احتفظ بسجل كامل للصفقات واستشر مختصاً.

---

<a id="20"></a>
## 20. قائمة التنفيذ (Checklist)

**الأساس**
- [ ] مستودع + `config/v7.yaml` + `.env`
- [ ] Postgres + الجداول (مع `spend_ledger` و`decisions` و`confidence`)
- [ ] قفل النسخة الواحدة (Advisory lock) + فهرس «مركز واحد لكل عملة»

**البيانات**
- [ ] PumpPortal WebSocket مع إعادة اتصال
- [ ] DexScreener مع Semaphore وBackoff
- [ ] بوابة الأمان: mint/freeze authority، top10، dev، LP، bundles، وأي فشل = BLOCK
- [ ] X عبر API الرسمي: بعد الفلتر فقط + حد 25 منشوراً + كاش + SpendGuard

**القرار**
- [ ] 3 Agents بمخرجات JSON (vote + score)
- [ ] إجماع 3/3 + فيتو البروفيسور
- [ ] درجة مركّبة + حد 70 + حجم 0.5×–1.5×
- [ ] Lessons + Post-mortem (بسياسة ثابتة أثناء الاختبار)

**التنفيذ الورقي**
- [ ] رسوم وانزلاق واقعيان
- [ ] TP +40% / SL −22% / Trailing / Time 10m / Rug exit
- [ ] حد خسارة يومي

**التشغيل**
- [ ] Dockerfile + railway.json (1 replica) + `/health`
- [ ] استئناف المراكز بعد إعادة التشغيل
- [ ] تنبيهات Telegram/Discord

**القياس**
- [ ] جدول الإصدارات + Wilson CI + Profit Factor + Max DD
- [ ] تقرير المعايرة حسب فئات الدرجة
- [ ] عدّاد 100 صفقة فريدة

**الواجهة**
- [ ] بطاقات الشخصيات والحالات، Blackboard، Candidate board، Open positions
- [ ] عداد Confidence Score وشريط الحجم لكل صفقة
- [ ] لوحة التكاليف (X/LLM/RPC/Railway) مقابل PnL

**قبل المال الحقيقي**
- [ ] اجتياز كل شروط القسم 16.2
- [ ] محفظة منفصلة + `ALLOW_LIVE` + Slippage أقصى + حماية MEV
- [ ] 50 صفقة حقيقية صغيرة ومقارنة الانزلاق

---

*أُعدّ من تحليل إطارات الفيديوين (10 إطارات/ثانية لمناطق الترجمة)، وقراءة مكبّرة للوحات والجداول، وقياس الألوان، وحساب المقاييس من البيانات المعروضة. البنود المعلّمة بـ«مرجّح» أو 🟡 استنتاجات هندسية، وليست مما صرّح به صاحب الفيديو.*
