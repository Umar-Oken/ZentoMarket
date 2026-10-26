from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.models import Category, Product, Seller, Store


# These names intentionally match the categories already present in the database.
PRODUCTS = (
    ("Avtotovarlar", "Auto Market", (
        ("Avtomobil telefon ushlagichi", "Avtomobil paneliga mahkam o‘rnatiladigan, telefonni qulay ko‘rish imkonini beruvchi ushlagich.", 99000),
        ("Avtomobil zaryadlagichi", "Telefon va boshqa qurilmalarni avtomobilda tez zaryadlash uchun ikki portli zaryadlagich.", 89000),
        ("Avtomobil gilamchasi", "Avtomobil salonini kir va namlikdan himoya qiluvchi, oson yuviladigan rezina gilamcha.", 349000),
        ("Avtomobil salon tozalagichi", "Panel, o‘rindiq va plastik qismlarni tozalash uchun samarali salon tozalagich.", 79000),
        ("Avtomobil havo xushbo‘ylantirgichi", "Salon ichida yoqimli va uzoq saqlanadigan hid beruvchi avtomobil xushbo‘ylantirgichi.", 39000),
    )),
    ("Bolalar dunyosi", "Kids World", (
        ("Bolalar o‘yinchoqlar to‘plami", "Turli yoshdagi bolalar uchun xavfsiz va rang-barang o‘yinchoqlar to‘plami.", 199000),
        ("Bolalar rivojlantiruvchi kubigi", "Mayda motorika va mantiqiy fikrlashni rivojlantiruvchi ko‘p funksiyali kubik.", 129000),
        ("Yumshoq ayiqcha o‘yinchog‘i", "Bolalar uchun yumshoq, yoqimli va xavfsiz materialdan tayyorlangan ayiqcha.", 119000),
        ("Bolalar rangli konstruktori", "Ijodkorlik va tasavvurni rivojlantirish uchun rangli konstruktiv detallar to‘plami.", 179000),
        ("Bolalar stol o‘yini", "Oila va do‘stlar bilan o‘ynash uchun qiziqarli, ta’limiy stol o‘yini.", 149000),
    )),
    ("Foto va video texnika", "Smart Shop", (
        ("Canon EOS kamera", "Yuqori sifatli surat va video olish uchun almashtiriladigan obyektivli Canon EOS kamera.", 8999000),
        ("Sony Alpha kamera", "Kontent yaratuvchilar va havaskor fotograflar uchun ixcham Sony Alpha kamera.", 10999000),
        ("Kamera tripod", "Kamera va videokamerani barqaror ushlab turuvchi, balandligi sozlanadigan tripod.", 399000),
        ("Kamera uchun yoritgich", "Foto va video tasvirlarda yorug‘likni yaxshilash uchun LED kamera yoritgichi.", 289000),
        ("Kamera xotira kartasi", "Foto va videolarni saqlash uchun tezkor 128 GB SD xotira kartasi.", 159000),
    )),
    ("Go'zallik va parvarish", "Beauty Market", (
        ("Yuz uchun namlantiruvchi krem", "Quruq va normal terini kun davomida nam saqlashga yordam beruvchi yuz kremi.", 129000),
        ("Soch uchun shampun", "Soch va bosh terisini muloyim tozalash uchun kundalik parvarish shampuni.", 89000),
        ("Soch balzami", "Sochni yumshatish, tarashni osonlashtirish va namlantirish uchun balzam.", 99000),
        ("Yuz tozalash geli", "Yuzdagi yog‘ va kundalik kirlarni muloyim tozalash uchun yengil gel.", 109000),
        ("Tana uchun loson", "Terini oziqlantirish va namlantirish uchun yoqimli hidli tana losoni.", 119000),
    )),
    ("Kiyim-kechak (ayollar)", "Fashion House", (
        ("Ayollar yozgi ko‘ylagi", "Yozgi kunlar uchun yengil va havodor matodan tikilgan ayollar ko‘ylagi.", 399000),
        ("Ayollar klassik bluzkasi", "Ofis va kundalik uslubga mos, sifatli matodan tikilgan klassik bluzka.", 299000),
        ("Ayollar jinsi shim", "Qulay fason va mustahkam denim matodan tayyorlangan ayollar jinsi shim.", 449000),
        ("Ayollar qishki kurtkasi", "Sovuq ob-havo uchun issiq astarli va shamol o‘tkazmaydigan qishki kurtka.", 899000),
        ("Ayollar sport kostyumi", "Yugurish va mashg‘ulotlar uchun qulay, elastik matoli sport kostyumi.", 499000),
    )),
    ("Kiyim-kechak (erkaklar)", "Fashion House", (
        ("Erkaklar klassik ko‘ylagi", "Ish va rasmiy uchrashuvlar uchun mos, paxtali klassik erkaklar ko‘ylagi.", 299000),
        ("Erkaklar futbolkasi", "Kundalik kiyish uchun yumshoq paxtali, qulay erkaklar futbolkasi.", 149000),
        ("Erkaklar jinsi shim", "Kundalik uslub uchun mustahkam denim matodan tikilgan erkaklar jinsi shim.", 399000),
        ("Erkaklar qishki kurtkasi", "Qishki sovuq va shamoldan himoya qiluvchi issiq erkaklar kurtkasi.", 799000),
        ("Erkaklar sport kostyumi", "Mashg‘ulot va sayr uchun qulay, nafas oluvchi matoli sport kostyumi.", 459000),
    )),
    ("Maishiy texnika", "Home Store", (
        ("Elektr choynak", "1,7 litr sig‘imli, suvni tez qaynatadigan xavfsiz elektr choynak.", 249000),
        ("Changyutgich", "Uy pol va gilamlarini tozalash uchun kuchli tortish quvvatiga ega changyutgich.", 1299000),
        ("Mikroto‘lqinli pech", "Ovqatni tez isitish va tayyorlash uchun ixcham mikroto‘lqinli pech.", 1099000),
        ("Kir yuvish mashinasi", "Kundalik kiyimlarni samarali yuvish uchun energiya tejamkor kir yuvish mashinasi.", 4299000),
        ("Elektr dazmol", "Bug‘ funksiyali va harorat sozlamalariga ega qulay elektr dazmol.", 299000),
    )),
    ("Mebel", "Home Store", (
        ("Kompyuter stoli", "Uy yoki ofis uchun monitor va aksessuarlarni joylashtirishga qulay kompyuter stoli.", 899000),
        ("Ofis kreslosi", "Uzoq ishlash vaqtida belni qo‘llab-quvvatlovchi, balandligi sozlanadigan kreslo.", 1199000),
        ("Kitob javoni", "Kitob va bezak buyumlarini tartibli saqlash uchun ko‘p tokchali javon.", 799000),
        ("Ikki kishilik divan", "Mehmonxona uchun ixcham, yumshoq va qulay ikki kishilik divan.", 3499000),
        ("Yotoqxona shkafi", "Kiyimlarni tartibli saqlash uchun keng va mustahkam yotoqxona shkafi.", 2899000),
    )),
    ("Musiqa asboblari", "Mega Market", (
        ("Klassik gitara", "Boshlovchi va havaskor musiqachilar uchun neylon torli klassik gitara.", 699000),
        ("Elektr gitara", "Rok va boshqa janrlarda ijro etish uchun kuchaytirgichga ulanadigan elektr gitara.", 1499000),
        ("Elektron pianino", "Uyda mashq qilish uchun 88 klavishli, turli tovush rejimlariga ega pianino.", 4999000),
        ("Baraban to‘plami", "Musiqa mashg‘ulotlari va sahna ijrosi uchun to‘liq baraban to‘plami.", 3599000),
        ("Mikrofon", "Qo‘shiq aytish, podkast va tadbirlar uchun tiniq ovoz beruvchi mikrofon.", 399000),
    )),
    ("Noutbuk va kompyuterlar", "Smart Shop", (
        ("Lenovo IdeaPad 5", "O‘qish, ofis ishlari va kundalik foydalanish uchun qulay Lenovo noutbuki.", 7999000),
        ("ASUS VivoBook 15", "Yengil korpus va yorqin ekranli, ish va ta’lim uchun mo‘ljallangan noutbuk.", 8499000),
        ("HP Pavilion 15", "Ko‘p vazifali ishlash va multimedia uchun unumdor HP noutbuki.", 9499000),
        ("Acer Aspire 5", "Ofis dasturlari va kundalik vazifalar uchun ishonchli Acer noutbuki.", 7499000),
        ("MacBook Air", "Yengil, jim va uzoq batareya quvvatiga ega Apple MacBook Air.", 14990000),
    )),
    ("Ofis va biznes uchun tovarlar", "Mega Market", (
        ("Printer", "Uy va kichik ofis uchun hujjatlarni tez chop etuvchi rangli printer.", 1299000),
        ("Skaner", "Hujjat va suratlarni raqamlashtirish uchun yuqori aniqlikdagi ofis skaneri.", 999000),
        ("Laminator", "Hujjatlarni namlik va shikastlanishdan himoya qilish uchun ixcham laminator.", 449000),
        ("Stol kalkulyatori", "Ofis hisob-kitoblari uchun katta tugmali va qulay stol kalkulyatori.", 69000),
        ("Hujjatlar uchun papka", "Muhim hujjatlarni tartibli saqlash uchun ko‘p bo‘limli ofis papkasi.", 49000),
    )),
    ("Oziq-ovqat", "Food Market", (
        ("Premium qora choy", "Yuqori sifatli choy barglaridan tayyorlangan xushbo‘y premium qora choy.", 39000),
        ("Tabiiy qahva", "100% Arabica donlaridan tayyorlangan xushbo‘y tabiiy qahva.", 89000),
        ("Sutli shokolad", "Kakao va sutdan tayyorlangan mayin ta’mli sutli shokolad.", 28000),
        ("Makaron", "Bug‘doy unidan tayyorlangan, kundalik taomlar uchun sifatli makaron.", 18000),
        ("Pechenye", "Choy bilan iste’mol qilish uchun mazali va mayin sariyog‘li pechenye.", 24000),
    )),
    ("Poyabzallar", "Fashion House", (
        ("Erkaklar sport krossovkasi", "Yugurish va kundalik yurish uchun yengil, qulay erkaklar krossovkasi.", 599000),
        ("Ayollar sport krossovkasi", "Faol hayot tarzi va mashg‘ulotlar uchun yumshoq taglikli ayollar krossovkasi.", 549000),
        ("Erkaklar klassik tuflisi", "Rasmiy kiyimlar bilan mos keladigan sifatli charm erkaklar tuflisi.", 699000),
        ("Ayollar klassik tuflisi", "Ofis va bayram uslubi uchun qulay poshnali klassik ayollar tuflisi.", 649000),
        ("Qishki etik", "Sovuq va nam ob-havo uchun issiq astarli, mustahkam qishki etik.", 799000),
    )),
    ("Qurilish va ta'mirlash mollari", "Mega Market", (
        ("Elektr burg‘ulash moslamasi", "Uy ta’miri va montaj ishlari uchun tezlik sozlamali elektr burg‘ulash moslamasi.", 699000),
        ("Bolg‘a", "Qurilish va maishiy ta’mirlash ishlari uchun mustahkam po‘lat boshli bolg‘a.", 89000),
        ("Tornavidalar to‘plami", "Turli o‘lchamdagi vintlar uchun magnit uchli tornavidalar to‘plami.", 149000),
        ("Ruletka", "Qurilish va o‘lchash ishlari uchun 5 metrli, mustahkam ruletka.", 59000),
        ("Qurilish qo‘lqopi", "Qo‘lni chang, tirnalish va mayda shikastlardan himoya qiluvchi ish qo‘lqopi.", 29000),
    )),
    ("Sayohat va sumkalar", "Mega Market", (
        ("Sayohat ryukzagi", "Kiyim va shaxsiy buyumlar uchun ko‘p bo‘limli, qulay sayohat ryukzagi.", 399000),
        ("Katta sayohat chamadoni", "Uzoq safarlar uchun g‘ildirakli, keng va mustahkam katta chamadon.", 899000),
        ("Sport sumkasi", "Sport kiyimlari va anjomlarini olib yurish uchun keng sport sumkasi.", 249000),
        ("Qo‘l yuki uchun sumka", "Samolyotda qo‘l yuki sifatida foydalanish uchun ixcham va yengil sumka.", 299000),
        ("Sayohat bo‘yin yostig‘i", "Uzoq yo‘lda qulay dam olish uchun yumshoq ergonomik bo‘yin yostig‘i.", 99000),
    )),
    ("Smartfonlar va gadjetlar", "Smart Shop", (
        ("iPhone 15", "Kuchli kamera, yorqin ekran va uzoq muddatli ishlashga ega zamonaviy iPhone.", 12990000),
        ("Samsung Galaxy S24", "Yuqori sifatli kamera va tezkor protsessorli zamonaviy Samsung smartfoni.", 11990000),
        ("Xiaomi Redmi Note 13", "Katta ekran va uzoq batareyaga ega kundalik foydalanish smartfoni.", 2899000),
        ("Google Pixel 8", "Toza Android tizimi va kuchli kamera imkoniyatlariga ega Google smartfoni.", 7999000),
        ("OnePlus 12", "Tezkor ishlash va sifatli displeyga ega yuqori unumdor OnePlus smartfoni.", 9999000),
    )),
    ("Sport va dam olish", "Sport Shop", (
        ("Futbol to‘pi", "Mashg‘ulot va havaskor o‘yinlar uchun chidamli, standart o‘lchamdagi futbol to‘pi.", 189000),
        ("Basketbol to‘pi", "Zal va ochiq maydonda foydalanish uchun mustahkam basketbol to‘pi.", 199000),
        ("Yoga gilami", "Yoga va fitnes mashg‘ulotlari uchun sirpanmaydigan yumshoq gilam.", 179000),
        ("Sport sumkasi", "Mashg‘ulot kiyimlari va anjomlari uchun qulay ko‘p bo‘limli sumka.", 249000),
        ("Sport suv idishi", "Mashg‘ulot paytida suv ichish uchun qayta foydalaniladigan sport idishi.", 79000),
    )),
    ("Uy va bog' anjomlari", "Home Store", (
        ("Bog‘ qaychisi", "Daraxt va buta shoxlarini kesish uchun o‘tkir va qulay bog‘ qaychisi.", 89000),
        ("Sug‘orish shlangi", "Bog‘ va hovlini sug‘orish uchun egiluvchan, mustahkam suv shlangi.", 199000),
        ("Bog‘ belkuragi", "Tuproq qazish va ko‘chat ekish uchun mustahkam metall belkurak.", 129000),
        ("O‘simlik ekish idishi", "Uy va bog‘ o‘simliklarini ekish uchun drenaj teshikli gul idishi.", 59000),
        ("Bog‘ qo‘lqopi", "Bog‘ ishlarida qo‘lni tikan va kirlanishdan himoya qiluvchi qo‘lqop.", 39000),
    )),
    ("Yuvish va tozalash vositalari", "Home Store", (
        ("Kir yuvish kukuni", "Rangli va oq kiyimlarni samarali yuvish uchun kundalik kir yuvish kukuni.", 79000),
        ("Idish yuvish vositasi", "Yog‘ va kirni tez ketkazuvchi, qo‘l terisiga yumshoq idish yuvish vositasi.", 29000),
        ("Pol tozalash vositasi", "Turli pol qoplamalarini tozalash va yoqimli hid qoldirish uchun vosita.", 39000),
        ("Oyna tozalash vositasi", "Oynada dog‘ va iz qoldirmasdan tozalash uchun maxsus suyuqlik.", 35000),
        ("Universal tozalash vositasi", "Oshxona, hammom va boshqa yuzalarni tozalash uchun ko‘p maqsadli vosita.", 45000),
    )),
    ("Zargarlik buyumlari va soatlar", "Mega Market", (
        ("Klassik qo‘l soati", "Kundalik va rasmiy uslubga mos, sodda dizayndagi klassik qo‘l soati.", 499000),
        ("Ayollar qo‘l soati", "Nozik metall brasletli, ayollar uslubiga mos nafis qo‘l soati.", 449000),
        ("Erkaklar bilaguzugi", "Kundalik kiyim bilan mos keladigan zamonaviy metall bilaguzuk.", 199000),
        ("Kumush uzuk", "925 probali kumushdan tayyorlangan sodda va nafis uzuk.", 299000),
        ("Klassik marjon", "Bayram va rasmiy liboslar uchun mos, nafis klassik marjon.", 349000),
    )),
    ("Hayvonlar uchun tovarlar (petshop)", "Mega Market", (
        ("Itlar uchun quruq yem", "Uy itlari uchun sifatli va muvozanatli tarkibga ega quruq yem.", 169000),
        ("Mushuklar uchun quruq yem", "Mushuklar uchun to‘yimli, kundalik oziqlanishga mos quruq yem.", 99000),
        ("Itlar uchun o‘yinchoq", "Itlar uchun mustahkam, xavfsiz va uzoq foydalanishga mo‘ljallangan o‘yinchoq.", 79000),
        ("Mushuklar uchun yumshoq o‘yinchoq", "Mushuklar bilan o‘ynash uchun yengil va xavfsiz yumshoq o‘yinchoq.", 59000),
        ("Uy hayvonlari uchun oziq-ovqat idishi", "It va mushuklar uchun qulay, yuvish oson bo‘lgan oziq-ovqat idishi.", 69000),
    )),
)


class Command(BaseCommand):
    help = "Mavjud 20 ta bo‘sh kategoriyaga 5 tadan mahsulot qo‘shadi."

    @transaction.atomic
    def handle(self, *args, **options):
        sellers = list(Seller.objects.filter(is_active=True).order_by("pk"))
        stores = {store_name: Store.objects.filter(name=store_name).first() for _, store_name, _ in PRODUCTS}
        missing_stores = sorted(name for name, store in stores.items() if store is None)
        if missing_stores:
            raise CommandError(
                "Quyidagi mavjud do‘konlar topilmadi: " + ", ".join(missing_stores)
            )
        if not sellers:
            raise CommandError("Mahsulot uchun faol Seller topilmadi; mavjud ma’lumotlar o‘zgartirilmadi.")

        created_total = 0
        skipped_total = 0
        for category_name, store_name, products in PRODUCTS:
            category = Category.objects.filter(name=category_name).first()
            if category is None:
                raise CommandError(
                    f"'{category_name}' kategoriyasi topilmadi; yangi kategoriya yaratilmaydi."
                )

            existing_count = category.products.count()
            if existing_count >= 5:
                skipped_total += len(products)
                self.stdout.write(
                    f"{category.name} — {existing_count} ta jami "
                    "(5 yoki undan ko‘p mavjud, o‘zgartirilmadi)"
                )
                continue

            created_count = 0
            skipped_count = 0
            for index, (name, description, price) in enumerate(products, start=1):
                if Product.objects.filter(name=name, category=category).exists():
                    skipped_count += 1
                    continue
                if category.products.count() >= 5:
                    break

                base_slug = slugify(f"{category.slug}-{name}")
                product_slug = base_slug
                suffix = 2
                while Product.objects.filter(slug=product_slug).exists():
                    product_slug = f"{base_slug}-{suffix}"
                    suffix += 1

                Product.objects.create(
                    seller=sellers[(created_total + created_count) % len(sellers)],
                    category=category,
                    store=stores[store_name],
                    name=name,
                    slug=product_slug,
                    sku=f"EMPTY-CATEGORY-{category.pk}-{index}",
                    description=description,
                    price=Decimal(price),
                    stock=25,
                    is_active=True,
                )
                created_count += 1

            created_total += created_count
            skipped_total += skipped_count
            self.stdout.write(
                f"{category.name} — {category.products.count()} ta jami "
                f"(yangi: {created_count}, mavjud: {skipped_count})"
            )

        self.stdout.write(self.style.SUCCESS(
            f"Jami yangi mahsulotlar: {created_total}. "
            f"Duplicate sabab o‘tkazib yuborilgan: {skipped_total}."
        ))
