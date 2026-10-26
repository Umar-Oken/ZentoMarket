from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.models import Category, Product, Seller, Store, User


CATEGORIES = (
    ("Elektronika", "Elektronika mahsulotlari va zamonaviy qurilmalar."),
    ("Kiyim-kechak", "Erkaklar, ayollar va bolalar uchun kiyimlar."),
    ("Oyoq kiyim", "Kundalik, sport va klassik oyoq kiyimlar."),
    ("Uy va oshxona", "Uy-ro‘zg‘or va oshxona uchun qulay mahsulotlar."),
    ("Go‘zallik va kosmetika", "Parvarish, kosmetika va atirlar."),
    ("Oziq-ovqat", "Kundalik iste’mol uchun sifatli oziq-ovqatlar."),
    ("Sport va fitness", "Sport, mashg‘ulot va sog‘lom turmush mahsulotlari."),
    ("Bolalar mahsulotlari", "Bolalar uchun o‘yinchoq, kiyim va o‘quv buyumlari."),
    ("Avtomobil mahsulotlari", "Avtomobil parvarishi va salon aksessuarlari."),
    ("Kitoblar va kanselyariya", "Kitob, daftar va yozuv qurollari."),
    ("Telefon aksessuarlari", "Telefonlar uchun g‘ilof, zaryadlagich va aksessuarlar."),
    ("Uy hayvonlari uchun mahsulotlar", "Uy hayvonlari ozuqasi va parvarish buyumlari."),
)

STORES = (
    ("Mega Market", "Turli kategoriyalardagi kundalik xaridlar do‘koni."),
    ("Smart Shop", "Elektronika va texnologiya mahsulotlari."),
    ("Fashion House", "Zamonaviy kiyim-kechak va oyoq kiyimlar."),
    ("Home Store", "Uy va oshxona mahsulotlari."),
    ("Beauty Market", "Go‘zallik va parvarish mahsulotlari."),
    ("Sport Shop", "Sport va fitness anjomlari."),
    ("Kids World", "Bolalar mahsulotlari va o‘yinchoqlar."),
    ("Book Store", "Kitoblar va kanselyariya mahsulotlari."),
    ("Auto Market", "Avtomobil mahsulotlari va aksessuarlar."),
    ("Food Market", "Oziq-ovqat va ichimliklar."),
)

PRODUCTS = (
    ("Elektronika", "iPhone 15", "Apple iPhone 15, 128 GB xotirali zamonaviy smartfon.", 12990000),
    ("Elektronika", "Samsung Galaxy S24", "Samsung Galaxy S24 smartfoni, tiniq ekran va kuchli kamera bilan.", 11990000),
    ("Elektronika", "MacBook Air M2", "Yengil va uzoq vaqt ishlaydigan Apple MacBook Air M2.", 14990000),
    ("Elektronika", "Redmi Note 13", "Kundalik foydalanish uchun qulay Redmi Note 13 smartfoni.", 2899000),
    ("Elektronika", "Sony WH-1000XM5", "Shovqinni kamaytiruvchi simsiz Sony quloqchinlari.", 4599000),
    ("Kiyim-kechak", "Erkaklar futbolkasi", "Paxtali matodan tikilgan qulay erkaklar futbolkasi.", 149000),
    ("Kiyim-kechak", "Ayollar ko‘ylagi", "Kundalik va bayram uchun mos ayollar ko‘ylagi.", 499000),
    ("Kiyim-kechak", "Erkaklar jinsi shim", "Mustahkam denim matodan tikilgan klassik jinsi shim.", 399000),
    ("Kiyim-kechak", "Qishki kurtka", "Sovuq kunlar uchun issiq va suv o‘tkazmaydigan kurtka.", 899000),
    ("Kiyim-kechak", "Ayollar kardigani", "Yumshoq trikotaj matodan tayyorlangan kardigan.", 349000),
    ("Oyoq kiyim", "Nike Air Max", "Yugurish va kundalik yurish uchun Nike Air Max.", 1699000),
    ("Oyoq kiyim", "Adidas Superstar", "Klassik dizayndagi Adidas Superstar krossovkasi.", 1299000),
    ("Oyoq kiyim", "Erkaklar klassik tuflisi", "Rasmiy kiyimlar uchun charm klassik tufli.", 699000),
    ("Oyoq kiyim", "Ayollar krossovkasi", "Yengil va qulay ayollar sport krossovkasi.", 549000),
    ("Oyoq kiyim", "Bolalar krossovkasi", "Faol bolalar uchun yengil va chidamli krossovka.", 329000),
    ("Uy va oshxona", "Elektr choynak", "Tez qaynaydigan 1.7 litrli elektr choynak.", 249000),
    ("Uy va oshxona", "Qahva mashinasi", "Uy sharoitida espresso va kapuchino tayyorlash uchun mashina.", 1899000),
    ("Uy va oshxona", "Yopishmaydigan tova", "Mustahkam qoplamali 28 sm oshxona tovasi.", 219000),
    ("Uy va oshxona", "Idishlar to‘plami", "6 kishilik 24 dona chinni idishlar to‘plami.", 799000),
    ("Uy va oshxona", "Mikroto‘lqinli pech", "Ovqatni tez isitish uchun ixcham mikroto‘lqinli pech.", 1099000),
    ("Go‘zallik va kosmetika", "Yuz kremi", "Namlagich va kundalik parvarish uchun yuz kremi.", 129000),
    ("Go‘zallik va kosmetika", "Shampun", "Sochni yumshoq tozalash uchun parvarish shampuni.", 89000),
    ("Go‘zallik va kosmetika", "Dior Sauvage atiri", "Erkaklar uchun uzoq saqlanadigan nafis atir.", 1599000),
    ("Go‘zallik va kosmetika", "Lab bo‘yog‘i", "Yorqin rangli, namlovchi lab bo‘yog‘i.", 119000),
    ("Go‘zallik va kosmetika", "Quyoshdan himoya kremi", "SPF 50 himoyali yengil yuz kremi.", 179000),
    ("Oziq-ovqat", "Sutli shokolad", "Kakao va sutdan tayyorlangan shirin shokolad.", 28000),
    ("Oziq-ovqat", "Donli qahva", "Xushbo‘y 100% Arabica donli qahva.", 89000),
    ("Oziq-ovqat", "Qora choy", "Kundalik ichimlik uchun xushbo‘y qora choy.", 26000),
    ("Oziq-ovqat", "Spagetti makaron", "Bug‘doy unidan tayyorlangan sifatli spagetti.", 18000),
    ("Oziq-ovqat", "Sariyog‘li pechenye", "Choy bilan iste’mol qilish uchun mazali pechenye.", 24000),
    ("Sport va fitness", "Futbol to‘pi", "Mashg‘ulot va havaskor o‘yinlar uchun futbol to‘pi.", 189000),
    ("Sport va fitness", "Sport sumkasi", "Mashg‘ulot kiyimlari uchun keng sport sumkasi.", 249000),
    ("Sport va fitness", "Yoga gilami", "Sirpanmaydigan, yumshoq yoga gilami.", 179000),
    ("Sport va fitness", "Gantel 5 kg", "Uy mashg‘ulotlari uchun bir juft 5 kg gantel.", 229000),
    ("Sport va fitness", "Fitnes rezinkalari to‘plami", "Turli qarshilikdagi besh dona fitnes rezinkasi.", 149000),
    ("Bolalar mahsulotlari", "Bolalar o‘yinchog‘i", "Rivojlantiruvchi rangli bolalar o‘yinchog‘i.", 99000),
    ("Bolalar mahsulotlari", "Lego konstruktori", "Ijodkorlikni rivojlantiruvchi Lego konstruktori.", 299000),
    ("Bolalar mahsulotlari", "Bolalar kiyimi", "Yumshoq matodan tayyorlangan bolalar kiyim to‘plami.", 189000),
    ("Bolalar mahsulotlari", "Maktab ryukzagi", "Maktab o‘quvchilari uchun ergonomik ryukzak.", 249000),
    ("Bolalar mahsulotlari", "Yumshoq ayiqcha", "Bolalar uchun xavfsiz yumshoq o‘yinchoq.", 119000),
    ("Avtomobil mahsulotlari", "Avtomobil moyi", "Benzin dvigatellari uchun sintetik motor moyi.", 429000),
    ("Avtomobil mahsulotlari", "Telefon ushlagich", "Avtomobil paneli uchun mahkam telefon ushlagich.", 99000),
    ("Avtomobil mahsulotlari", "Avtomobil gilamchasi", "Salon uchun oson tozalanadigan rezina gilamcha.", 349000),
    ("Avtomobil mahsulotlari", "Avtomobil zaryadlagichi", "Ikki portli tezkor avtomobil zaryadlagichi.", 89000),
    ("Avtomobil mahsulotlari", "Havo kompressori", "Shinalarni to‘ldirish uchun ixcham kompressor.", 299000),
    ("Kitoblar va kanselyariya", "Dasturlash kitobi", "Python dasturlash asoslari bo‘yicha amaliy kitob.", 149000),
    ("Kitoblar va kanselyariya", "Ingliz tili kitobi", "Ingliz tilini mustaqil o‘rganish uchun darslik.", 129000),
    ("Kitoblar va kanselyariya", "Qalin daftar", "Universitet va maktab uchun 96 varaqli daftar.", 18000),
    ("Kitoblar va kanselyariya", "Ruchka", "Silliq yozadigan ko‘k siyohli sharikli ruchka.", 5000),
    ("Kitoblar va kanselyariya", "Qalamlar to‘plami", "Chizmachilik va yozuv uchun rangli qalamlar.", 29000),
    ("Telefon aksessuarlari", "iPhone g‘ilofi", "iPhone uchun zarbaga chidamli shaffof g‘ilof.", 79000),
    ("Telefon aksessuarlari", "USB-C zaryadlagich", "Tezkor quvvatlashni qo‘llab-quvvatlovchi zaryadlagich.", 149000),
    ("Telefon aksessuarlari", "Simsiz quloqchin", "Telefon bilan mos ishlaydigan Bluetooth quloqchin.", 199000),
    ("Telefon aksessuarlari", "Himoya oynasi", "Smartfon ekrani uchun mustahkam himoya oynasi.", 35000),
    ("Telefon aksessuarlari", "Powerbank 20000 mAh", "Safarda telefonni quvvatlash uchun kuchli powerbank.", 299000),
    ("Uy hayvonlari uchun mahsulotlar", "Itlar uchun yem", "Katta itlar uchun muvozanatli quruq yem.", 169000),
    ("Uy hayvonlari uchun mahsulotlar", "Mushuklar uchun yem", "Mushuklar uchun vitaminlarga boy quruq yem.", 99000),
    ("Uy hayvonlari uchun mahsulotlar", "Hayvonlar o‘yinchog‘i", "It va mushuklar uchun xavfsiz rezina o‘yinchoq.", 59000),
    ("Uy hayvonlari uchun mahsulotlar", "Hayvonlar uchun idish", "Oziq-ovqat va suv uchun zanglamaydigan idish.", 69000),
    ("Uy hayvonlari uchun mahsulotlar", "Mushuklar uchun qum", "Hidni kamaytiruvchi tabiiy mushuk qumi.", 89000),
)


class Command(BaseCommand):
    help = "Universal katalog kategoriyalari, do‘konlari va 60 ta mahsulotni takrorlanmasdan yaratadi."

    @transaction.atomic
    def handle(self, *args, **options):
        categories = {}
        for name, description in CATEGORIES:
            category, _ = Category.objects.update_or_create(
                slug=slugify(name),
                defaults={"name": name, "description": description, "is_active": True},
            )
            categories[name] = category

        stores = {}
        for name, description in STORES:
            store, _ = Store.objects.update_or_create(
                slug=slugify(name),
                defaults={"name": name, "description": description},
            )
            stores[name] = store

        user, created = User.objects.get_or_create(
            email="catalog@zento.uz",
            defaults={"role": User.Role.SELLER, "is_active": True},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=("password",))
        seller, _ = Seller.objects.get_or_create(
            user=user,
            defaults={"store_name": "Zento Catalog", "description": "Universal katalog demo sotuvchisi.", "is_active": True},
        )

        for index, (category_name, name, description, price) in enumerate(PRODUCTS, start=1):
            Product.objects.update_or_create(
                sku=f"CAT-{index:03d}",
                defaults={
                    "seller": seller,
                    "category": categories[category_name],
                    "store": stores[("Smart Shop" if category_name in {"Elektronika", "Telefon aksessuarlari"} else
                                     "Fashion House" if category_name in {"Kiyim-kechak", "Oyoq kiyim"} else
                                     "Home Store" if category_name == "Uy va oshxona" else
                                     "Beauty Market" if category_name == "Go‘zallik va kosmetika" else
                                     "Food Market" if category_name == "Oziq-ovqat" else
                                     "Sport Shop" if category_name == "Sport va fitness" else
                                     "Kids World" if category_name == "Bolalar mahsulotlari" else
                                     "Auto Market" if category_name == "Avtomobil mahsulotlari" else
                                     "Book Store" if category_name == "Kitoblar va kanselyariya" else
                                     "Mega Market" if category_name == "Uy hayvonlari uchun mahsulotlar" else "Mega Market")],
                    "name": name,
                    "slug": f"{slugify(name)}-{index}",
                    "description": description,
                    "price": Decimal(price),
                    "stock": 25,
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"{len(categories)} kategoriya, {len(stores)} do‘kon va {len(PRODUCTS)} mahsulot tayyor."
        ))
