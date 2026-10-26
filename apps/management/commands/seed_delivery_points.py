from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.models import DeliveryPoint


REGIONAL_POINTS = {
    "Qoraqalpog‘iston Respublikasi": [
        ("Nukus", "Berdaq ko‘chasi", 42.4602, 59.6166),
        ("Qo‘ng‘irot", "Qoraqalpog‘iston ko‘chasi", 43.0400, 58.8450),
        ("Xo‘jayli", "Amudaryo ko‘chasi", 42.4000, 59.4500),
        ("Beruniy", "Al-Beruniy ko‘chasi", 41.7000, 60.7500),
        ("To‘rtko‘l", "Qoraqalpoq ko‘chasi", 41.5500, 60.6200),
    ],
    "Andijon viloyati": [
        ("Andijon", "Boburshoh ko‘chasi", 40.7821, 72.3442),
        ("Asaka", "Mustaqillik ko‘chasi", 40.6415, 72.2387),
        ("Shahrixon", "Istiqlol ko‘chasi", 40.7136, 72.0571),
        ("Marhamat", "Navoiy ko‘chasi", 40.4800, 72.3100),
        ("Xonobod", "Do‘stlik ko‘chasi", 40.8000, 72.0000),
    ],
    "Buxoro viloyati": [
        ("Buxoro", "Bahouddin Naqshband ko‘chasi", 39.7681, 64.4556),
        ("G‘ijduvon", "Ulug‘bek ko‘chasi", 40.1000, 64.6833),
        ("Kogon", "Buxoro yo‘li ko‘chasi", 39.7200, 64.5500),
        ("Vobkent", "Alisher Navoiy ko‘chasi", 40.0300, 64.5150),
        ("Romitan", "Yangi hayot ko‘chasi", 39.9300, 64.3800),
    ],
    "Jizzax viloyati": [
        ("Jizzax", "Sharof Rashidov ko‘chasi", 40.1158, 67.8422),
        ("G‘allaorol", "Samarqand ko‘chasi", 40.0300, 67.5800),
        ("Zomin", "Mustaqillik ko‘chasi", 39.9600, 68.4000),
        ("Paxtakor", "Do‘stlik ko‘chasi", 40.3200, 67.9500),
        ("Do‘stlik", "Yangi O‘zbekiston ko‘chasi", 40.5200, 68.0300),
    ],
    "Qashqadaryo viloyati": [
        ("Qarshi", "Nasaf ko‘chasi", 38.8610, 65.7847),
        ("Shahrisabz", "Amir Temur ko‘chasi", 39.0500, 66.8300),
        ("Koson", "O‘zbekiston ko‘chasi", 39.0400, 65.5900),
        ("Kitob", "Ipak yo‘li ko‘chasi", 39.1200, 66.8800),
        ("Chiroqchi", "Oqtepa ko‘chasi", 39.0300, 66.5700),
    ],
    "Navoiy viloyati": [
        ("Navoiy", "Alisher Navoiy ko‘chasi", 40.0844, 65.3792),
        ("Zarafshon", "Zarafshon ko‘chasi", 41.5700, 64.2000),
        ("Karmana", "Amir Temur ko‘chasi", 40.1400, 65.3800),
        ("Nurota", "Sardoba ko‘chasi", 40.5600, 65.6900),
        ("Qiziltepa", "Yoshlik ko‘chasi", 40.0300, 64.8500),
    ],
    "Namangan viloyati": [
        ("Namangan", "A. Navoiy ko‘chasi", 41.0003, 71.6726),
        ("Chust", "Koshg‘ariy ko‘chasi", 41.0000, 71.2300),
        ("Chortoq", "Sohil ko‘chasi", 41.0700, 71.8200),
        ("Pop", "Farg‘ona yo‘li ko‘chasi", 40.8700, 71.1000),
        ("Kosonsoy", "Istiqlol ko‘chasi", 41.2600, 71.5500),
    ],
    "Samarqand viloyati": [
        ("Samarqand", "Registon ko‘chasi", 39.6542, 66.9597),
        ("Kattaqo‘rg‘on", "Navoiy ko‘chasi", 39.9000, 66.2600),
        ("Urgut", "Alisher Navoiy ko‘chasi", 39.4000, 67.2400),
        ("Jomboy", "Samarqand ko‘chasi", 39.7000, 67.0900),
        ("Bulung‘ur", "Mustaqillik ko‘chasi", 39.7600, 67.2700),
    ],
    "Sirdaryo viloyati": [
        ("Guliston", "O‘zbekiston ko‘chasi", 40.4897, 68.7842),
        ("Yangiyer", "Do‘stlik ko‘chasi", 40.2750, 68.8200),
        ("Shirin", "Yangi hayot ko‘chasi", 40.2300, 69.0000),
        ("Boyovut", "Guliston ko‘chasi", 40.4300, 68.7000),
        ("Sayxunobod", "Istiqlol ko‘chasi", 40.5500, 68.7200),
    ],
    "Surxondaryo viloyati": [
        ("Termiz", "At-Termiziy ko‘chasi", 37.2242, 67.2783),
        ("Denov", "Sadriddin Ayniy ko‘chasi", 38.2700, 67.8900),
        ("Sherobod", "Amir Temur ko‘chasi", 37.6700, 67.0000),
        ("Boysun", "O‘zbekiston ko‘chasi", 38.2000, 67.2000),
        ("Jarqo‘rg‘on", "Tinchlik ko‘chasi", 37.5000, 67.4500),
    ],
    "Toshkent viloyati": [
        ("Nurafshon", "Toshkent ko‘chasi", 41.0400, 69.3500),
        ("Chirchiq", "Amir Temur ko‘chasi", 41.4700, 69.5800),
        ("Angren", "Navoiy ko‘chasi", 41.0100, 70.0850),
        ("Olmaliq", "Metallurglar ko‘chasi", 40.8500, 69.6000),
        ("Bekobod", "Sirdaryo ko‘chasi", 40.2200, 69.2700),
    ],
    "Farg‘ona viloyati": [
        ("Farg‘ona", "Alisher Navoiy ko‘chasi", 40.3864, 71.7864),
        ("Qo‘qon", "Navoiy ko‘chasi", 40.5286, 70.9425),
        ("Marg‘ilon", "Turkiston ko‘chasi", 40.4723, 71.7246),
        ("Quva", "Istiqlol ko‘chasi", 40.5200, 72.0700),
        ("Rishton", "Kulolchilik ko‘chasi", 40.3600, 71.2800),
    ],
    "Xorazm viloyati": [
        ("Urganch", "Al-Xorazmiy ko‘chasi", 41.5500, 60.6300),
        ("Xiva", "Ichan qal’a ko‘chasi", 41.3783, 60.3639),
        ("Hazorasp", "Amudaryo ko‘chasi", 41.3200, 61.0800),
        ("Shovot", "Guliston ko‘chasi", 41.6600, 60.3000),
        ("Gurlan", "Beruniy ko‘chasi", 41.8400, 60.3900),
    ],
}


TASHKENT_CITY_POINTS = [
    ("Toshkent Chilonzor", "Chilonzor tumani", "Bunyodkor ko‘chasi", 41.2850, 69.2030),
    ("Toshkent Yunusobod", "Yunusobod tumani", "Amir Temur shoh ko‘chasi", 41.3650, 69.2880),
    ("Toshkent Shayxontohur", "Shayxontohur tumani", "Beruniy ko‘chasi", 41.3250, 69.2350),
    ("Toshkent Mirzo Ulug‘bek", "Mirzo Ulug‘bek tumani", "Buyuk Ipak Yo‘li ko‘chasi", 41.3350, 69.3450),
    ("Toshkent Yakkasaroy", "Yakkasaroy tumani", "Bobur ko‘chasi", 41.2850, 69.2550),
    ("Toshkent Sergeli", "Sergeli tumani", "Sergeli ko‘chasi", 41.2150, 69.2200),
    ("Toshkent Olmazor", "Olmazor tumani", "Qorasaroy ko‘chasi", 41.3450, 69.2250),
    ("Toshkent Mirobod", "Mirobod tumani", "Oybek ko‘chasi", 41.2950, 69.2700),
    ("Toshkent Bektemir", "Bektemir tumani", "Farg‘ona yo‘li ko‘chasi", 41.2350, 69.3350),
    ("Toshkent Uchtepa", "Uchtepa tumani", "Lutfiy ko‘chasi", 41.2850, 69.1750),
]


def point_specs():
    specs = []
    for region, points in REGIONAL_POINTS.items():
        for city, street, latitude, longitude in points:
            specs.append({
                "name": f"{city} yetkazib berish punkti",
                "region": region,
                "city": city,
                "address": f"{region}, {city}, {street}, 12-uy (demo punkt)",
                "latitude": Decimal(str(latitude)),
                "longitude": Decimal(str(longitude)),
            })
    for name, city, street, latitude, longitude in TASHKENT_CITY_POINTS:
        specs.append({
            "name": name,
            "region": "Toshkent shahri",
            "city": city,
            "address": f"Toshkent shahri, {city}, {street}, 12-uy (demo punkt)",
            "latitude": Decimal(str(latitude)),
            "longitude": Decimal(str(longitude)),
        })
    return specs


class Command(BaseCommand):
    help = "Create or update the 75 Uzbekistan delivery points."

    def handle(self, *args, **options):
        specs = point_specs()
        if len(specs) != 75:
            raise CommandError(f"Seed data 75 ta emas: {len(specs)}")

        with transaction.atomic():
            names = {spec["name"] for spec in specs}
            DeliveryPoint.objects.exclude(name__in=names).update(is_active=False)
            for index, spec in enumerate(specs, start=1):
                DeliveryPoint.objects.update_or_create(
                    name=spec["name"],
                    defaults={
                        **spec,
                        "phone": f"+998 90 700 {index // 100:02d} {index % 100:02d}",
                        "working_hours": "Har kuni 09:00–21:00",
                        "is_active": True,
                    },
                )

        active_count = DeliveryPoint.objects.filter(is_active=True).count()
        if active_count != 75:
            raise CommandError(f"Faol punktlar soni 75 emas: {active_count}")

        self.stdout.write(self.style.SUCCESS(f"{active_count} ta faol delivery point yaratildi/yangilandi."))
        for region in list(REGIONAL_POINTS) + ["Toshkent shahri"]:
            count = DeliveryPoint.objects.filter(is_active=True, region=region).count()
            self.stdout.write(f"{region}: {count} ta")
