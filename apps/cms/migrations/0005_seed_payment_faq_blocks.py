from django.db import migrations


# Секции, перенесённые из пользовательского соглашения (/terms) на страницу «Оплата».
PAYMENT_BLOCKS = (
    {
        'sort_order': 10,
        'title_ru': 'Цена и способы оплаты',
        'title_kz': 'Баға және төлем әдістері',
        'title_en': 'Prices and payment methods',
        'content_ru': (
            'Цены указаны в тенге Республики Казахстан и могут быть изменены магазином в '
            'одностороннем порядке; цена уже оплаченного заказа изменению не подлежит.\n'
            'Доступные способы и порядок оплаты указаны в разделе «Оплата». Оплата возможна '
            'наличными при получении или безналичным расчётом.\n'
            'При безналичной оплате обязанность покупателя считается исполненной с момента '
            'зачисления средств на счёт магазина.'
        ),
        'content_kz': (
            'Бағалар Қазақстан Республикасының теңгесінде көрсетілген және дүкенмен біржақты '
            'өзгертілуі мүмкін; төленген тапсырыстың бағасы өзгертілмейді.\n'
            'Қолжетімді төлем әдістері мен тәртібі «Төлем» бөлімінде көрсетілген. Төлем алу '
            'кезінде қолма-қол немесе қолма-қол ақшасыз есеп айырысу арқылы жасалады.\n'
            'Қолма-қол ақшасыз төлемде сатып алушының міндеті қаражат дүкен шотына түскен '
            'сәттен бастап орындалған болып саналады.'
        ),
        'content_en': (
            'Prices are shown in Kazakhstani tenge and may be changed by the store unilaterally; '
            'the price of an order already paid for is not subject to change.\n'
            'Available payment methods are shown in the Payment section. Payment can be made in '
            'cash on delivery or by bank transfer.\n'
            'For bank transfers, the customer’s obligation is fulfilled once the funds are '
            'credited to the store’s account.'
        ),
    },
    {
        'sort_order': 20,
        'title_ru': 'Оплата банковскими картами',
        'title_kz': 'Банк карталарымен төлеу',
        'title_en': 'Card payments',
        'content_ru': (
            'К оплате принимаются карты VISA и MasterCard. Ввод данных карты выполняется на '
            'защищённой платёжной странице FreedomPay с использованием шифрования.\n'
            'Для подтверждения платежа покупатель перенаправляется на страницу банка для ввода '
            'кода 3DSecure из СМС.\n'
            'Данные банковской карты передаются только в зашифрованном виде и не сохраняются на '
            'сервере магазина.'
        ),
        'content_kz': (
            'Төлемге VISA және MasterCard карталары қабылданады. Карта деректерін енгізу шифрлау '
            'қолданылатын FreedomPay қорғалған төлем бетінде орындалады.\n'
            'Төлемді растау үшін сатып алушы СМС-тегі 3DSecure кодын енгізу үшін банк бетіне '
            'бағытталады.\n'
            'Банк картасының деректері тек шифрланған түрде беріледі және дүкен серверінде '
            'сақталмайды.'
        ),
        'content_en': (
            'VISA and MasterCard are accepted. Card details are entered on the secure FreedomPay '
            'payment page using encryption.\n'
            'To confirm the payment, the customer is redirected to their bank’s page to enter the '
            '3DSecure code sent by SMS.\n'
            'Card details are transmitted only in encrypted form and are not stored on the '
            'store’s server.'
        ),
    },
    {
        'sort_order': 30,
        'title_ru': 'Доставка и получение заказа',
        'title_kz': 'Жеткізу және тапсырысты алу',
        'title_en': 'Delivery and receiving orders',
        'content_ru': (
            'Доступны самовывоз, доставка магазином и доставка перевозчиком; способ выбирается '
            'при оформлении заказа.\n'
            'Право собственности и риск случайной гибели или повреждения товара переходят к '
            'покупателю в момент передачи товара покупателю, его представителю или перевозчику.\n'
            'Срок поставки товара составляет не более 30 календарных дней. При получении '
            'покупатель проверяет соответствие, количество и комплектность товара.'
        ),
        'content_kz': (
            'Өзін-өзі алып кету, дүкеннің жеткізуі және тасымалдаушының жеткізуі қолжетімді; әдіс '
            'тапсырыс рәсімдеу кезінде таңдалады.\n'
            'Меншік құқығы мен тауардың кездейсоқ жойылу немесе зақымдану тәуекелі тауар сатып '
            'алушыға, оның өкіліне немесе тасымалдаушыға берілген сәтте өтеді.\n'
            'Тауарды жеткізу мерзімі 30 күнтізбелік күннен аспайды. Алу кезінде сатып алушы '
            'тауардың сәйкестігін, санын және жиынтықтылығын тексереді.'
        ),
        'content_en': (
            'Pickup, store delivery, and courier delivery are available; the method is chosen at '
            'checkout.\n'
            'Ownership and the risk of accidental loss or damage pass to the customer when the '
            'product is handed over to the customer, their representative, or the carrier.\n'
            'The delivery period does not exceed 30 calendar days. On receipt, the customer '
            'checks the product against the order for condition, quantity, and completeness.'
        ),
    },
)


# Остальные секции соглашения адаптированы под формат «вопрос — ответ» страницы FAQ.
FAQ_BLOCKS = (
    {
        'sort_order': 10,
        'title_ru': 'Как пользоваться сайтом?',
        'title_kz': 'Сайтты қалай пайдаланамын?',
        'title_en': 'How do I use the website?',
        'content_ru': (
            'Используя сайт, покупатель просматривает каталог, добавляет товары в корзину и '
            'оформляет заказы через доступные интерфейсы.\n'
            'Информация о товарах, наличии и характеристиках может обновляться по данным магазина.'
        ),
        'content_kz': (
            'Сайтты пайдалана отырып, сатып алушы каталогты қарайды, тауарларды себетке қосады '
            'және қолжетімді интерфейстер арқылы тапсырыс рәсімдейді.\n'
            'Тауарлар, қолжетімділік және сипаттамалар туралы ақпарат дүкен деректеріне қарай '
            'жаңартылуы мүмкін.'
        ),
        'content_en': (
            'The website allows customers to browse products, add items to the cart, and place '
            'orders through the available interfaces.\n'
            'Product information and availability may change as store data is updated.'
        ),
    },
    {
        'sort_order': 20,
        'title_ru': 'Что такое договор-оферта и как он заключается?',
        'title_kz': 'Шарт-оферта дегеніміз не және ол қалай жасалады?',
        'title_en': 'What is the public offer and how is it concluded?',
        'content_ru': (
            'Настоящее соглашение является публичной офертой ТОО «Sara Milan» в соответствии со '
            'статьями 395, 396 и 447 Гражданского кодекса Республики Казахстан.\n'
            'Оформляя заказ на сайте, покупатель безоговорочно и в полном объёме принимает '
            'условия оферты. Договор считается заключённым с момента оформления заказа.\n'
            'Магазин вправе изменять условия соглашения; актуальная редакция публикуется на сайте.'
        ),
        'content_kz': (
            'Осы келісім Қазақстан Республикасы Азаматтық кодексінің 395, 396 және 447-баптарына '
            'сәйкес «Sara Milan» ЖШС-нің жария офертасы болып табылады.\n'
            'Сайтта тапсырыс рәсімдей отырып, сатып алушы оферта шарттарын сөзсіз әрі толық '
            'көлемде қабылдайды. Шарт тапсырыс рәсімделген сәттен бастап жасалған болып саналады.\n'
            'Дүкен келісім шарттарын өзгертуге құқылы; өзекті редакция сайтта жарияланады.'
        ),
        'content_en': (
            'These terms constitute a public offer by Sara Milan LLP under Articles 395, 396, and '
            '447 of the Civil Code of the Republic of Kazakhstan.\n'
            'By placing an order on the website, the customer unconditionally accepts these terms '
            'in full. The agreement takes effect when the order is placed.\n'
            'The store may amend these terms; the current version is published on the website.'
        ),
    },
    {
        'sort_order': 30,
        'title_ru': 'Какие обязанности у покупателя?',
        'title_kz': 'Сатып алушының қандай міндеттері бар?',
        'title_en': 'What are the customer’s obligations?',
        'content_ru': (
            'Покупатель отвечает за достоверность данных, указанных при оформлении заказа, и их '
            'чистоту от претензий третьих лиц.\n'
            'Отметка о согласии с условиями договора при оформлении заказа подтверждает принятие '
            'соглашения.\n'
            'Товары приобретаются для личных, семейных и домашних нужд, не связанных с '
            'предпринимательской деятельностью; пользование сайтом является безвозмездным.'
        ),
        'content_kz': (
            'Сатып алушы тапсырыс рәсімдеу кезінде көрсетілген деректердің дұрыстығына және '
            'олардың үшінші тұлғалардың талаптарынан тазалығына жауап береді.\n'
            'Тапсырыс рәсімдеу кезінде шарт талаптарымен келісу белгісі келісімнің қабылданғанын '
            'растайды.\n'
            'Тауарлар кәсіпкерлік қызметпен байланысты емес жеке, отбасылық және тұрмыстық '
            'қажеттіліктер үшін сатып алынады; сайтты пайдалану тегін.'
        ),
        'content_en': (
            'The customer is responsible for the accuracy of the information provided at checkout '
            'and for keeping it free of third-party claims.\n'
            'Confirming the terms at checkout constitutes acceptance of this agreement.\n'
            'Products are purchased for personal, family, and household use unrelated to business '
            'activity; use of the website is free of charge.'
        ),
    },
    {
        'sort_order': 40,
        'title_ru': 'Насколько точна информация о товарах на сайте?',
        'title_kz': 'Сайттағы тауар туралы ақпарат қаншалықты дәл?',
        'title_en': 'How accurate is the product information on the site?',
        'content_ru': (
            'Изображения-образцы и описания на сайте носят справочный характер и могут не в полной '
            'мере передавать цвет, размер и иные характеристики товара.\n'
            'По вопросам о свойствах товара покупатель может обратиться к специалисту магазина до '
            'оформления заказа.\n'
            'Товары, указанные в счёте отдельными позициями, не являются комплектом.'
        ),
        'content_kz': (
            'Сайттағы үлгі суреттер мен сипаттамалар анықтамалық сипатта болады және тауардың '
            'түсін, өлшемін және басқа сипаттамаларын толық көлемде жеткізе алмауы мүмкін.\n'
            'Тауардың қасиеттері туралы сұрақтар бойынша сатып алушы тапсырыс рәсімдеуге дейін '
            'дүкен маманына хабарласа алады.\n'
            'Шотта жеке позициялармен көрсетілген тауарлар жинақ болып табылмайды.'
        ),
        'content_en': (
            'Sample images and descriptions on the website are for reference and may not fully '
            'convey the color, size, or other characteristics of a product.\n'
            'For questions about a product, the customer may contact the store before placing an '
            'order.\n'
            'Products listed as separate line items on an invoice do not constitute a set.'
        ),
    },
    {
        'sort_order': 50,
        'title_ru': 'Как оформляется заказ, оплата и доставка?',
        'title_kz': 'Тапсырыс, төлем және жеткізу қалай рәсімделеді?',
        'title_en': 'How are orders, payment, and delivery handled?',
        'content_ru': (
            'Заказ считается оформленным после заполнения необходимых данных и подтверждения '
            'через оплату.\n'
            'Оплата и доставка зависят от выбранного способа.\n'
            'Условия возврата и обмена должны уточняться по актуальной политике магазина.'
        ),
        'content_kz': (
            'Тапсырыс қажетті деректер толтырылып, төлем арқылы расталғаннан кейін рәсімделген '
            'болып саналады.\n'
            'Төлем мен жеткізу таңдалған әдіске байланысты.\n'
            'Қайтару және айырбастау шарттарын дүкеннің өзекті саясаты бойынша нақтылау керек.'
        ),
        'content_en': (
            'An order is considered placed after the required information is completed and payment '
            'is confirmed.\n'
            'Payment and delivery depend on the selected method.\n'
            'Contact the store to confirm current return and exchange terms.'
        ),
    },
    {
        'sort_order': 60,
        'title_ru': 'Какая гарантия на товар?',
        'title_kz': 'Тауарға қандай кепілдік беріледі?',
        'title_en': 'What warranty applies to products?',
        'content_ru': (
            'Гарантийный срок на товар составляет 14 дней с момента передачи товара покупателю '
            'или его представителю, если иное не предусмотрено дополнительным соглашением.\n'
            'Гарантия не распространяется на товары, использованные не по назначению или с '
            'нарушением правил эксплуатации.'
        ),
        'content_kz': (
            'Тауарға кепілдік мерзімі, егер қосымша келісімде өзгеше көзделмесе, тауар сатып '
            'алушыға немесе оның өкіліне берілген сәттен бастап 14 күнді құрайды.\n'
            'Кепілдік мақсатына сай емес немесе пайдалану ережелерін бұзып қолданылған тауарларға '
            'қолданылмайды.'
        ),
        'content_en': (
            'The warranty period is 14 days from the handover of the product to the customer or '
            'their representative, unless otherwise agreed.\n'
            'The warranty does not cover products used improperly or in breach of operating rules.'
        ),
    },
    {
        'sort_order': 70,
        'title_ru': 'Как вернуть или обменять товар?',
        'title_kz': 'Тауарды қалай қайтаруға немесе айырбастауға болады?',
        'title_en': 'How can I return or exchange a product?',
        'content_ru': (
            'Покупатель вправе отказаться от товара до его передачи, а после передачи — в течение '
            '14 календарных дней в порядке, предусмотренном ЗРК «О защите прав потребителей».\n'
            'Возврат товара надлежащего качества возможен при сохранении товарного вида, '
            'потребительских свойств и документа, подтверждающего покупку. Товары с '
            'индивидуально-определёнными свойствами возврату не подлежат.\n'
            'При оплате картой возврат средств производится на банковскую карту в течение 21 '
            'рабочего дня с момента получения заявления о возврате на sara_milan.kz@mail.ru.'
        ),
        'content_kz': (
            'Сатып алушы тауарды беруге дейін, ал берілгеннен кейін — «Тұтынушылардың құқықтарын '
            'қорғау туралы» ҚР Заңында көзделген тәртіппен 14 күнтізбелік күн ішінде бас тартуға '
            'құқылы.\n'
            'Сапалы тауарды қайтару оның тауарлық түрі, тұтынушылық қасиеттері және сатып алуды '
            'растайтын құжат сақталса мүмкін. Жеке-дара анықталған қасиеттері бар тауарлар '
            'қайтарылмайды.\n'
            'Картамен төлеген жағдайда қаражат қайтару туралы өтініш sara_milan.kz@mail.ru '
            'мекенжайына түскеннен кейін 21 жұмыс күні ішінде банк картасына жүргізіледі.'
        ),
        'content_en': (
            'The customer may decline a product before handover and, after handover, within 14 '
            'calendar days under the Law of the Republic of Kazakhstan “On Consumer Protection”.\n'
            'A return of a product of proper quality is possible if its presentation, consumer '
            'properties, and proof of purchase are preserved. Products with individually defined '
            'properties are non-returnable.\n'
            'For card payments, refunds are made to the bank card within 21 business days of '
            'receiving the refund request at sara_milan.kz@mail.ru.'
        ),
    },
    {
        'sort_order': 80,
        'title_ru': 'Как обрабатываются персональные данные?',
        'title_kz': 'Дербес деректер қалай өңделеді?',
        'title_en': 'How is personal data processed?',
        'content_ru': (
            'Оформляя заказ и регистрируясь, покупатель даёт согласие на обработку персональных '
            'данных в целях исполнения соглашения в соответствии с Законом РК «О персональных '
            'данных и их защите».\n'
            'Порядок обработки и защиты данных описан в Политике конфиденциальности магазина.'
        ),
        'content_kz': (
            'Тапсырыс рәсімдеу және тіркелу арқылы сатып алушы «Дербес деректер және оларды '
            'қорғау туралы» ҚР Заңына сәйкес келісімді орындау мақсатында дербес деректерді '
            'өңдеуге келісім береді.\n'
            'Деректерді өңдеу және қорғау тәртібі дүкеннің Құпиялылық саясатында сипатталған.'
        ),
        'content_en': (
            'By placing an order and registering, the customer consents to the processing of '
            'personal data to perform this agreement, in accordance with the Law of the Republic '
            'of Kazakhstan “On Personal Data and Its Protection”.\n'
            'How data is processed and protected is described in the store’s Privacy Policy.'
        ),
    },
    {
        'sort_order': 90,
        'title_ru': 'Как решаются споры и кто несёт ответственность?',
        'title_kz': 'Даулар қалай шешіледі және кім жауапты?',
        'title_en': 'How are disputes resolved and who is liable?',
        'content_ru': (
            'Стороны несут ответственность в соответствии с законодательством Республики '
            'Казахстан и освобождаются от неё на время действия обстоятельств непреодолимой силы.\n'
            'Споры решаются путём переговоров, а при недостижении согласия — в судебных органах '
            'Республики Казахстан по месту нахождения магазина.'
        ),
        'content_kz': (
            'Тараптар Қазақстан Республикасының заңнамасына сәйкес жауапкершілік көтереді және '
            'еңсерілмейтін күш жағдайлары әрекет еткен уақытта одан босатылады.\n'
            'Даулар келіссөздер арқылы шешіледі, ал келісімге қол жеткізілмесе — дүкеннің '
            'орналасқан жері бойынша Қазақстан Республикасының сот органдарында шешіледі.'
        ),
        'content_en': (
            'The parties are liable under the laws of the Republic of Kazakhstan and are released '
            'from liability during force majeure events.\n'
            'Disputes are resolved through negotiation and, failing agreement, in the courts of '
            'the Republic of Kazakhstan at the store’s location.'
        ),
    },
    {
        'sort_order': 100,
        'title_ru': 'Каковы реквизиты продавца?',
        'title_kz': 'Сатушының деректемелері қандай?',
        'title_en': 'What are the seller’s details?',
        'content_ru': (
            'ТОО «Sara Milan», юридический адрес: г. Алматы, ул. Мендикулова, дом 84. '
            'БИН: 200940011821.\n'
            'Контакты: sara_milan.kz@mail.ru, +7 775 207 5443. Банк: АО «Kaspi Bank», '
            'БИК CASPKZKA, счёт KZ27722S000007860818.'
        ),
        'content_kz': (
            '«Sara Milan» ЖШС, заңды мекенжайы: Алматы қ., Меңдіқұлов көшесі, 84-үй. '
            'БСН: 200940011821.\n'
            'Байланыс: sara_milan.kz@mail.ru, +7 775 207 5443. Банк: «Kaspi Bank» АҚ, '
            'БСК CASPKZKA, шот KZ27722S000007860818.'
        ),
        'content_en': (
            'Sara Milan LLP, registered address: Almaty, Mendikulov St., 84. BIN: 200940011821.\n'
            'Contact: sara_milan.kz@mail.ru, +7 775 207 5443. Bank: Kaspi Bank JSC, '
            'BIC CASPKZKA, account KZ27722S000007860818.'
        ),
    },
)


PAGE_TITLES = {
    'payment': {'title_ru': 'Оплата', 'title_kz': 'Төлем', 'title_en': 'Payment'},
    'faq': {
        'title_ru': 'Частые вопросы',
        'title_kz': 'Жиі қойылатын сұрақтар',
        'title_en': 'FAQ',
    },
}


def _seed_blocks(apps, slug, blocks):
    StaticPage = apps.get_model('cms', 'StaticPage')
    StaticPageBlock = apps.get_model('cms', 'StaticPageBlock')

    page, _ = StaticPage.objects.get_or_create(
        slug=slug,
        defaults={
            **PAGE_TITLES[slug],
            'content_ru': '',
            'content_kz': '',
            'content_en': '',
            'is_active': True,
        },
    )
    for block in blocks:
        StaticPageBlock.objects.get_or_create(
            page=page,
            title_ru=block['title_ru'],
            defaults={
                'title_kz': block['title_kz'],
                'title_en': block['title_en'],
                'content_ru': block['content_ru'],
                'content_kz': block['content_kz'],
                'content_en': block['content_en'],
                'sort_order': block['sort_order'],
                'is_active': True,
            },
        )


def seed(apps, schema_editor):
    _seed_blocks(apps, 'payment', PAYMENT_BLOCKS)
    _seed_blocks(apps, 'faq', FAQ_BLOCKS)


def unseed(apps, schema_editor):
    StaticPage = apps.get_model('cms', 'StaticPage')
    StaticPageBlock = apps.get_model('cms', 'StaticPageBlock')

    for slug, blocks in (('payment', PAYMENT_BLOCKS), ('faq', FAQ_BLOCKS)):
        page = StaticPage.objects.filter(slug=slug).first()
        if not page:
            continue
        StaticPageBlock.objects.filter(
            page=page,
            title_ru__in=[block['title_ru'] for block in blocks],
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0004_infodoc'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
