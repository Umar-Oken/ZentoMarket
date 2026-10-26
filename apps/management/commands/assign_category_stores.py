from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.models import Category, Product, Store


CATEGORY_STORES = (
    ("Avtomobil mahsulotlari", "Zento Auto"),
    ("Avtotovarlar", "Zento Auto Parts"),
    ("Bolalar dunyosi", "Zento Kids"),
    ("Bolalar mahsulotlari", "Zento Kids Store"),
    ("Elektronika", "Zento Electronics"),
    ("Foto va video texnika", "Zento Photo"),
    ("Go‘zallik va kosmetika", "Zento Beauty"),
    ("Go'zallik va parvarish", "Zento Care"),
    ("Hayvonlar uchun tovarlar (petshop)", "Zento PetShop"),
    ("Kitoblar va kanselyariya", "Zento Books"),
    ("Kiyim-kechak", "Zento Fashion"),
    ("Kiyim-kechak (ayollar)", "Zento Women"),
    ("Kiyim-kechak (erkaklar)", "Zento Men"),
    ("Maishiy texnika", "Zento Appliances"),
    ("Mebel", "Zento Furniture"),
    ("Musiqa asboblari", "Zento Music"),
    ("Noutbuk va kompyuterlar", "Zento Computers"),
    ("Ofis va biznes uchun tovarlar", "Zento Office"),
    ("Oziq-ovqat", "Zento Food"),
    ("Oyoq kiyim", "Zento Shoes"),
    ("Qurilish va ta'mirlash mollari", "Zento Build"),
    ("Sayohat va sumkalar", "Zento Travel"),
    ("Smartfonlar va gadjetlar", "Zento Gadgets"),
    ("Sport va dam olish", "Zento Sport"),
    ("Sport va fitness", "Zento Fitness"),
    ("Telefon aksessuarlari", "Zento Mobile"),
    ("Uy va bog' anjomlari", "Zento Garden"),
    ("Uy va oshxona", "Zento Home"),
    ("Uy hayvonlari uchun mahsulotlar", "Zento Pet Food"),
    ("Yuvish va tozalash vositalari", "Zento Clean"),
    ("Zargarlik buyumlari va soatlar", "Zento Jewelry"),
)


class Command(BaseCommand):
    help = "Har bir ko‘rsatilgan kategoriyaga alohida Store biriktiradi va mahsulotlarini yangilaydi."

    @transaction.atomic
    def handle(self, *args, **options):
        updated_products = 0
        created_stores = []
        mapping = []

        for category_name, store_name in CATEGORY_STORES:
            category = Category.objects.filter(name=category_name).first()
            if category is None:
                raise CommandError(
                    f"'{category_name}' kategoriyasi topilmadi; yangi kategoriya yaratilmaydi."
                )

            store, created = Store.objects.get_or_create(
                name=store_name,
                defaults={
                    "slug": slugify(store_name),
                    "description": f"{store_name} — {category_name} mahsulotlari do‘koni.",
                },
            )
            if created:
                created_stores.append(store.name)

            if category.store_id != store.pk:
                category.store = store
                category.save(update_fields=["store", "updated_at"])

            changed = Product.objects.filter(category=category).exclude(store=store).update(store=store)
            updated_products += changed
            mapping.append((category.name, store.name, changed))

        self.stdout.write(self.style.SUCCESS(
            f"{len(created_stores)} ta yangi Store yaratildi; "
            f"{updated_products} ta Product yangilandi."
        ))
        if created_stores:
            self.stdout.write("Yaratilgan Store'lar: " + ", ".join(created_stores))
        for category_name, store_name, changed in mapping:
            self.stdout.write(f"{category_name} -> {store_name} ({changed} ta Product yangilandi)")
