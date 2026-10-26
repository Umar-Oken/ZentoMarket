from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.models import Brand, Category, Product, ProductVariant, Seller, User


CATEGORIES = (
    ("Elektronika", "elektronika", None, "electronics,technology"),
    ("Smartfonlar", "smartfonlar", "elektronika", "smartphone,mobile"),
    ("Noutbuklar", "noutbuklar", "elektronika", "laptop,computer"),
    ("Audio", "audio", "elektronika", "headphones,speaker"),
    ("Uy va maishiy texnika", "uy-va-maishiy-texnika", None, "home,appliances"),
    ("Oshxona texnikasi", "oshxona-texnikasi", "uy-va-maishiy-texnika", "kitchen,appliance"),
    ("Aqlli uy", "aqlli-uy", "uy-va-maishiy-texnika", "smart-home,interior"),
    ("Moda", "moda", None, "fashion,clothes"),
    ("Erkaklar kiyimi", "erkaklar-kiyimi", "moda", "mens-fashion,clothes"),
    ("Ayollar kiyimi", "ayollar-kiyimi", "moda", "womens-fashion,dress"),
    ("Oyoq kiyim", "oyoq-kiyim", "moda", "sneakers,shoes"),
    ("Go'zallik", "gozallik", None, "beauty,cosmetics"),
    ("Parvarish va atirlar", "parvarish-va-atirlar", "gozallik", "skincare,perfume"),
    ("Sport", "sport", None, "sports,fitness"),
    ("Sport anjomlari", "sport-anjomlari", "sport", "fitness,equipment"),
    ("Kitoblar", "kitoblar", None, "books,reading"),
    ("Bolalar", "bolalar", None, "children,toys"),
    ("O'yinchoqlar", "oyinchoqlar", "bolalar", "toys,children"),
)


SELLERS = (
    ("Zento Electronics", "Toshkent, Yunusobod tumani", "+998 71 200 10 01", "4.92"),
    ("Smart Life Store", "Toshkent, Chilonzor tumani", "+998 71 200 10 02", "4.86"),
    ("Urban Style", "Toshkent, Shayxontohur tumani", "+998 71 200 10 03", "4.79"),
    ("Beauty House", "Toshkent, Mirzo Ulug'bek tumani", "+998 71 200 10 04", "4.88"),
    ("Sport Pro", "Samarqand, Registon ko'chasi", "+998 66 200 10 05", "4.83"),
    ("Book & Kids", "Toshkent, Yakkasaroy tumani", "+998 71 200 10 06", "4.75"),
)


# sku, category slug, name, brand, price, old price, stock, image search, variants
PRODUCTS = (
    ("PH-APL-15P", "smartfonlar", "Apple iPhone 15 Pro 256GB", "Apple", 15499000, 16999000, 24, "iphone,smartphone", ("Natural Titanium / 256GB", "Blue Titanium / 256GB", "Black Titanium / 512GB")),
    ("PH-SAM-S24U", "smartfonlar", "Samsung Galaxy S24 Ultra 12/256GB", "Samsung", 13999000, 14999000, 31, "samsung,smartphone", ("Titanium Gray / 256GB", "Titanium Black / 256GB", "Titanium Violet / 512GB")),
    ("PH-XIA-14", "smartfonlar", "Xiaomi 14 12/512GB", "Xiaomi", 9799000, 10499000, 38, "xiaomi,smartphone", ("Black / 512GB", "White / 512GB", "Green / 512GB")),
    ("PH-GOO-P8P", "smartfonlar", "Google Pixel 8 Pro 12/128GB", "Google", 10999000, 11999000, 17, "google-pixel,smartphone", ("Obsidian / 128GB", "Porcelain / 128GB", "Bay / 256GB")),
    ("PH-HON-M6P", "smartfonlar", "Honor Magic6 Pro 12/512GB", "Honor", 11999000, 12999000, 22, "honor,smartphone", ("Black / 512GB", "Green / 512GB", "Purple / 512GB")),
    ("NB-APL-MBA-M3", "noutbuklar", "Apple MacBook Air 13 M3 16/512GB", "Apple", 17999000, 18999000, 14, "macbook,laptop", ("Midnight / 16GB / 512GB", "Starlight / 16GB / 512GB", "Space Gray / 24GB / 512GB")),
    ("NB-LEN-X1C", "noutbuklar", "Lenovo ThinkPad X1 Carbon Gen 12", "Lenovo", 21499000, 22999000, 11, "business-laptop,computer", ("Core Ultra 5 / 16GB / 512GB", "Core Ultra 7 / 32GB / 1TB", "Core Ultra 7 / 32GB / 2TB")),
    ("NB-ASU-G14", "noutbuklar", "ASUS ROG Zephyrus G14 RTX 4060", "ASUS", 23999000, 25499000, 9, "gaming-laptop,computer", ("16GB / 1TB / RTX 4060", "32GB / 1TB / RTX 4060", "32GB / 2TB / RTX 4070")),
    ("NB-HP-SPX", "noutbuklar", "HP Spectre x360 14 OLED", "HP", 18799000, 19999000, 13, "hp-laptop,computer", ("Ultra 5 / 16GB / 512GB", "Ultra 7 / 16GB / 1TB", "Ultra 7 / 32GB / 1TB")),
    ("AU-APL-APP2", "audio", "Apple AirPods Pro 2 USB-C", "Apple", 3199000, 3499000, 46, "airpods,earphones", ("USB-C", "USB-C + MagSafe g'ilof", "USB-C + himoya g'ilofi")),
    ("AU-SNY-XM5", "audio", "Sony WH-1000XM5", "Sony", 4599000, 4999000, 28, "sony,headphones", ("Black", "Silver", "Midnight Blue")),
    ("AU-JBL-770", "audio", "JBL Tune 770NC", "JBL", 1299000, 1499000, 63, "jbl,headphones", ("Black", "Blue", "White")),
    ("AU-BOS-SL2", "audio", "Bose SoundLink Flex", "Bose", 2199000, 2399000, 34, "portable-speaker,audio", ("Black", "Stone Blue", "Chilled Lilac")),
    ("KT-PHI-AFXL", "oshxona-texnikasi", "Philips Airfryer XXL HD9650", "Philips", 3299000, 3699000, 19, "airfryer,kitchen", ("7.3 litr", "7.3 litr + grill to'plami", "7.3 litr + pishirish to'plami")),
    ("KT-DLG-MEVO", "oshxona-texnikasi", "DeLonghi Magnifica Evo", "DeLonghi", 7299000, 7899000, 12, "coffee-machine,kitchen", ("ECAM290.21.B", "ECAM290.61.B", "ECAM290.81.TB")),
    ("KT-KEN-KMX", "oshxona-texnikasi", "Kenwood kMix KMX750", "Kenwood", 4399000, 4799000, 16, "stand-mixer,kitchen", ("Red", "Black", "Cream")),
    ("KT-TEF-CY75", "oshxona-texnikasi", "Tefal Turbo Cuisine CY754", "Tefal", 1999000, 2299000, 25, "multicooker,kitchen", ("5 litr", "5 litr + idish", "5 litr + aksessuarlar")),
    ("SH-XIA-AP4P", "aqlli-uy", "Xiaomi Smart Air Purifier 4 Pro", "Xiaomi", 3599000, 3899000, 29, "air-purifier,home", ("EU versiya", "EU + zaxira filtr", "EU + 2 zaxira filtr")),
    ("SH-ROB-S8", "aqlli-uy", "Roborock S8 robot changyutgich", "Roborock", 7499000, 8199000, 18, "robot-vacuum,home", ("White", "Black", "White + Auto-Empty Dock")),
    ("SH-PHI-HUE", "aqlli-uy", "Philips Hue Starter Kit E27", "Philips", 1899000, 2099000, 37, "smart-light,home", ("White Ambiance", "White and Color Ambiance", "Color Ambiance + Dimmer")),
    ("MF-LEV-501", "erkaklar-kiyimi", "Levi's 501 Original jinsi", "Levi's", 1099000, 1299000, 55, "mens-jeans,fashion", ("W30 / L32", "W32 / L32", "W34 / L34")),
    ("MF-TNF-NUP", "erkaklar-kiyimi", "The North Face 1996 Retro Nuptse", "The North Face", 3899000, 4299000, 20, "mens-puffer-jacket,fashion", ("Black / M", "Black / L", "Blue / XL")),
    ("MF-PUM-HOD", "erkaklar-kiyimi", "Puma Essentials Logo Hoodie", "Puma", 699000, 849000, 72, "mens-hoodie,fashion", ("Gray / M", "Black / L", "Navy / XL")),
    ("WF-ZAR-DRS", "ayollar-kiyimi", "Zara Midi Satin Dress", "Zara", 899000, 1099000, 41, "womens-dress,fashion", ("Emerald / S", "Black / M", "Burgundy / L")),
    ("WF-MNG-COAT", "ayollar-kiyimi", "Mango Classic Wool Coat", "Mango", 1899000, 2199000, 27, "womens-coat,fashion", ("Camel / S", "Black / M", "Gray / L")),
    ("WF-UNQ-CARD", "ayollar-kiyimi", "Uniqlo Merino Cardigan", "Uniqlo", 749000, 899000, 49, "womens-cardigan,fashion", ("Beige / S", "Navy / M", "Red / L")),
    ("SH-NIK-AM270", "oyoq-kiyim", "Nike Air Max 270", "Nike", 1699000, 1899000, 44, "nike-sneakers,shoes", ("Black / 41", "White / 42", "Red / 43")),
    ("SH-ADI-UBL", "oyoq-kiyim", "Adidas Ultraboost Light", "Adidas", 1799000, 1999000, 39, "adidas-running-shoes,sneakers", ("Core Black / 40", "Cloud White / 42", "Solar Red / 43")),
    ("SH-NBL-574", "oyoq-kiyim", "New Balance 574 Core", "New Balance", 1399000, 1599000, 51, "new-balance,sneakers", ("Gray / 40", "Navy / 42", "Black / 43")),
    ("SH-TIM-6IN", "oyoq-kiyim", "Timberland Premium 6-Inch Boot", "Timberland", 2399000, 2699000, 23, "timberland-boots,shoes", ("Wheat / 41", "Black / 42", "Dark Brown / 43")),
    ("BT-DIO-SAUV", "parvarish-va-atirlar", "Dior Sauvage Eau de Parfum", "Dior", 1899000, 2099000, 32, "dior-sauvage,perfume", ("60 ml", "100 ml", "200 ml")),
    ("BT-LRP-CICA", "parvarish-va-atirlar", "La Roche-Posay Cicaplast Baume B5+", "La Roche-Posay", 249000, 289000, 84, "skincare-cream,cosmetics", ("40 ml", "100 ml", "100 ml x 2")),
    ("BT-CER-FC", "parvarish-va-atirlar", "CeraVe Foaming Cleanser", "CeraVe", 219000, 259000, 91, "facial-cleanser,skincare", ("236 ml", "473 ml", "1 litr")),
    ("BT-DYS-AIR", "parvarish-va-atirlar", "Dyson Airwrap Complete Long", "Dyson", 7499000, 7999000, 15, "hair-styler,beauty", ("Nickel / Copper", "Blue / Blush", "Ceramic Pink / Rose Gold")),
    ("SP-ADI-EU24", "sport-anjomlari", "Adidas Fussballliebe Pro futbol to'pi", "Adidas", 1699000, 1899000, 36, "football,soccer-ball", ("5-o'lcham", "5-o'lcham + nasos", "Match Ball to'plami")),
    ("SP-WIL-PS14", "sport-anjomlari", "Wilson Pro Staff 97 v14", "Wilson", 3299000, 3599000, 21, "tennis-racket,sports", ("Grip 2", "Grip 3", "Grip 4")),
    ("SP-TRE-MAR7", "sport-anjomlari", "Trek Marlin 7 Gen 3", "Trek", 10999000, 11999000, 10, "mountain-bike,bicycle", ("M / Matte Navy", "L / Galactic Gray", "XL / Pennyflake")),
    ("BK-CLE-ATOM", "kitoblar", "Atomic Habits — James Clear", "Penguin Random House", 179000, 219000, 76, "atomic-habits,book", ("Inglizcha / Paperback", "Inglizcha / Hardcover", "Ruscha / Hardcover")),
    ("BK-HAR-SAPI", "kitoblar", "Sapiens — Yuval Noah Harari", "Harper", 189000, 229000, 68, "sapiens,book", ("Inglizcha / Paperback", "Inglizcha / Hardcover", "Ruscha / Paperback")),
    ("BK-ROW-HP1", "kitoblar", "Harry Potter and the Philosopher's Stone", "Bloomsbury", 149000, 179000, 82, "harry-potter,book", ("Paperback", "Hardcover", "Illustrated Edition")),
)


FIRST_NAMES = (
    "Aziz", "Madina", "Jasur", "Dilnoza", "Bekzod", "Nilufar", "Sardor", "Shahnoza", "Akmal", "Malika",
    "Oybek", "Zarina", "Farrux", "Sevara", "Temur", "Mohira", "Sherzod", "Lola", "Bobur", "Nodira",
    "Sanjar", "Aziza", "Ulug'bek", "Feruza", "Kamron",
)
LAST_NAMES = (
    "Karimov", "Rahimova", "Tursunov", "Abdullayeva", "Yusupov", "Ergasheva", "Nazarov", "Rasulova",
    "Qodirov", "Ismoilova", "Saidov", "Hamidova", "Mirzayev", "Umarova", "Aliyev", "Sultonova",
    "Oripov", "Jalilova", "Xolmatov", "Salimova",
)


def image_search_url(query, width=1200, height=900):
    params = urlencode({
        "q": query,
        "w": width,
        "h": height,
        "c": 7,
        "rs": 1,
        "pid": "1.7",
        "mkt": "en-US",
    })
    return f"https://tse1.mm.bing.net/th?{params}"


def download_image(job):
    last_error = None
    for _ in range(3):
        request = Request(job["url"], headers={"User-Agent": "ZentoMarketSeed/1.0"})
        try:
            with urlopen(request, timeout=35) as response:
                content_type = response.headers.get_content_type()
                data = response.read(8 * 1024 * 1024)
            if not content_type.startswith("image/") or len(data) < 1024:
                raise ValueError("server did not return a valid image")
            return job, data
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            last_error = exc
    return job, last_error


class Command(BaseCommand):
    help = "ZentoMarket bazasini realistik demo users, categories, products, variants va rasmlar bilan to'ldiradi."

    def add_arguments(self, parser):
        parser.add_argument("--skip-images", action="store_true", help="Rasmlarni yuklamasdan faqat DB yozuvlarini yaratish")
        parser.add_argument(
            "--refresh-images",
            action="store_true",
            help="Seed kategoriya va mahsulot rasmlarini o'chirib, aniq nom bo'yicha qayta yuklash",
        )

    @transaction.atomic
    def create_records(self, demo_password):
        users = []
        for index in range(50):
            seller_user = index < len(SELLERS)
            prefix = "sotuvchi" if seller_user else "mijoz"
            number = index + 1 if seller_user else index - len(SELLERS) + 1
            email = f"{prefix}{number:02d}@zento.uz"
            first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
            last_name = LAST_NAMES[index % len(LAST_NAMES)]
            user, created = User.objects.update_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": f"+998 9{index % 10} {100 + index:03d} {20 + index:02d} {30 + index:02d}",
                    "role": User.Role.SELLER if seller_user else User.Role.CUSTOMER,
                    "is_active": True,
                },
            )
            if created:
                user.set_password(demo_password)
                user.save(update_fields=("password",))
            users.append(user)

        sellers = []
        for index, (name, address, phone, rating) in enumerate(SELLERS):
            seller, _ = Seller.objects.update_or_create(
                user=users[index],
                defaults={
                    "store_name": name,
                    "description": f"{name} — original mahsulotlar, rasmiy kafolat va O'zbekiston bo'ylab yetkazib berish.",
                    "address": address,
                    "phone": phone,
                    "rating": Decimal(rating),
                    "is_verified": True,
                    "is_active": True,
                },
            )
            sellers.append(seller)

        categories = {}
        for name, category_slug, parent_slug, _ in CATEGORIES:
            category, _ = Category.objects.update_or_create(
                slug=category_slug,
                defaults={"name": name, "parent": categories.get(parent_slug), "is_active": True},
            )
            categories[category_slug] = category

        products = []
        for index, item in enumerate(PRODUCTS):
            sku, category_slug, name, brand, price, old_price, stock, query, variants = item
            brand_object, _ = Brand.objects.update_or_create(
                name=brand,
                defaults={"slug": slugify(brand), "is_active": True},
            )
            product, _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "seller": sellers[index % len(sellers)],
                    "category": categories[category_slug],
                    "name": name,
                    "slug": slugify(name),
                    "brand": brand_object,
                    "description": (
                        f"{name} — {brand} brendining original mahsuloti. Sifat nazoratidan o'tgan, "
                        "ishlab chiqaruvchi tavsifiga mos komplekt va rasmiy kafolat bilan taqdim etiladi. "
                        "Toshkent bo'ylab tezkor, O'zbekiston hududlariga ishonchli yetkazib berish mavjud."
                    ),
                    "price": Decimal(price),
                    "old_price": Decimal(old_price),
                    "stock": stock,
                    "is_active": True,
                },
            )
            products.append((product, query))
            for variant_index, variant_name in enumerate(variants, start=1):
                ProductVariant.objects.update_or_create(
                    sku=f"{sku}-V{variant_index}",
                    defaults={
                        "product": product,
                        "name": variant_name,
                        "extra_price": Decimal((variant_index - 1) * max(25000, price // 25)),
                        "stock": max(1, stock // variant_index),
                        "is_active": True,
                    },
                )
        return users, categories, products

    def build_image_jobs(self, users, categories, products):
        jobs = []
        for index, user in enumerate(users, start=1):
            if not user.avatar:
                jobs.append({
                    "kind": "avatar", "object": user, "filename": f"seed-user-{user.pk}.jpg",
                    "url": f"https://i.pravatar.cc/512?img={((index - 1) % 70) + 1}",
                })
        category_queries = {slug: query for _, slug, _, query in CATEGORIES}
        for index, (slug, category) in enumerate(categories.items(), start=1):
            if not category.image:
                jobs.append({
                    "kind": "category", "object": category, "filename": f"category-{slug}.jpg",
                    "url": image_search_url(
                        f"{category_queries[slug].replace(',', ' ')} products category collection",
                        900,
                        700,
                    ),
                })
        return jobs

    def clear_seed_images(self, categories, products):
        removed = 0
        for _, category in categories.items():
            if category.image and category.image.name.rsplit("/", 1)[-1].startswith("category-"):
                category.image.delete(save=False)
                category.image = ""
                category.save(update_fields=("image",))
                removed += 1
        return removed

    def save_image(self, job, data):
        obj = job["object"]
        field = obj.avatar if job["kind"] == "avatar" else obj.image
        field.save(job["filename"], ContentFile(data), save=True)

    def handle(self, *args, **options):
        if settings.IS_PRODUCTION:
            raise CommandError("seed_market is only available outside production.")
        demo_password = os.getenv("DEMO_PASSWORD", "").strip()
        if not demo_password:
            raise CommandError("Set a local DEMO_PASSWORD environment variable before running seed_market.")

        users, categories, products = self.create_records(demo_password)
        failures = []

        if not options["skip_images"]:
            if options["refresh_images"]:
                removed = self.clear_seed_images(categories, products)
                self.stdout.write(f"{removed} ta eski seed rasmi almashtirish uchun olib tashlandi.")
            jobs = self.build_image_jobs(users, categories, products)
            if jobs:
                self.stdout.write(f"{len(jobs)} ta mos rasm yuklanmoqda...")
                completed = 0
                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = [executor.submit(download_image, job) for job in jobs]
                    for future in as_completed(futures):
                        job, result = future.result()
                        if isinstance(result, Exception):
                            failures.append((job, result))
                        else:
                            self.save_image(job, result)
                        completed += 1
                        if completed % 20 == 0 or completed == len(jobs):
                            self.stdout.write(f"  {completed}/{len(jobs)}")

        counts = {
            "users": User.objects.count(),
            "sellers": Seller.objects.count(),
            "categories": Category.objects.count(),
            "brands": Brand.objects.count(),
            "products": Product.objects.count(),
            "variants": ProductVariant.objects.count(),
        }
        self.stdout.write(self.style.SUCCESS(f"Seed yakunlandi: {counts}"))
        self.stdout.write("Demo loginlar: mijoz01@zento.uz yoki sotuvchi01@zento.uz")
        if failures:
            self.stdout.write(self.style.WARNING(f"{len(failures)} ta media fayl yuklanmadi; commandni qayta ishga tushirsangiz, faqat yetishmaganlari olinadi."))
            for job, error in failures[:10]:
                self.stdout.write(f"  - {job['filename']}: {error}")
