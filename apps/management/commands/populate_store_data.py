from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.models import Product, Seller, Store
from apps.store_emails import store_email_for_seller


def normalized(value):
    return " ".join((value or "").split()).casefold()


class Command(BaseCommand):
    help = (
        "Store email, seller_id va shop_code qiymatlarini mavjud seller/product "
        "bog‘lanishlaridan xavfsiz to‘ldiradi va barcha qatorlarni tekshiradi."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Hech narsa yozmasdan aniqlangan moslik va xatolarni ko‘rsatadi.",
        )
        parser.add_argument(
            "--map-store",
            action="append",
            default=[],
            metavar="STORE_ID=SELLER_ID",
            help="Bog‘lanishi aniqlanmagan store uchun tasdiqlangan seller ID.",
        )

    def handle(self, *args, **options):
        database = Store.objects.db
        stores = list(Store.objects.using(database).select_related("seller", "seller__user").order_by("pk"))
        sellers = list(Seller.objects.using(database).select_related("user").order_by("pk"))
        sellers_by_id = {seller.pk: seller for seller in sellers}

        explicit_mappings = self.parse_mappings(options["map_store"], sellers_by_id)
        product_sellers = defaultdict(set)
        for store_id, seller_id in (
            Product.objects.using(database)
            .filter(store_id__isnull=False)
            .order_by()
            .values_list("store_id", "seller_id")
            .distinct()
        ):
            product_sellers[store_id].add(seller_id)

        sellers_by_name = defaultdict(list)
        sellers_by_email = defaultdict(list)
        for seller in sellers:
            sellers_by_name[normalized(seller.store_name)].append(seller)
            sellers_by_email[normalized(seller.user.email)].append(seller)

        reserved_codes = {store.shop_code for store in stores if store.shop_code}
        planned_updates = {}
        problems = []

        for store in stores:
            evidence = product_sellers.get(store.pk, set())
            seller, resolution_error = self.resolve_seller(
                store,
                evidence,
                explicit_mappings,
                sellers_by_id,
                sellers_by_name,
                sellers_by_email,
            )
            if resolution_error:
                problems.append(f"Store #{store.pk} ({store.name}): {resolution_error}")
                seller = None

            if seller is not None and evidence and evidence != {seller.pk}:
                problems.append(
                    f"Store #{store.pk} ({store.name}): mahsulot seller ID'lari "
                    f"{sorted(evidence)}; bitta store selleriga mos emas."
                )
                seller = None

            updates = {}

            if store.seller_id is None and seller is not None:
                updates["seller_id"] = seller.pk

            if not store.shop_code:
                code = self.available_shop_code(store.pk, reserved_codes)
                reserved_codes.add(code)
                updates["shop_code"] = code

            expected_email = (
                store_email_for_seller(seller, store, updates.get("shop_code"))
                if seller
                else None
            )
            if expected_email and normalized(store.email) != normalized(expected_email):
                updates["email"] = expected_email

            if updates:
                planned_updates[store.pk] = updates

        if options["dry_run"]:
            self.stdout.write(f"Tekshirilgan store qatorlari: {len(stores)}")
            self.stdout.write(f"To‘ldirish rejalashtirilgan qatorlar: {len(planned_updates)}")
            for store_id, updates in planned_updates.items():
                self.stdout.write(f"Store #{store_id}: {updates}")
            self.report_problems(problems)
            validation_errors = self.validate(stores, planned_updates, sellers_by_id)
            self.report_problems(validation_errors, heading="Kutilayotgan validatsiya muammolari")
            if problems or validation_errors:
                raise CommandError("Dry-run: ma’lumotlar to‘liq va bir ma’noli emas; hech narsa yozilmadi.")
            self.stdout.write(self.style.SUCCESS("Dry-run muvaffaqiyatli: barcha store qatorlari to‘ldirilishi mumkin."))
            return

        with transaction.atomic(using=database):
            for store_id, updates in planned_updates.items():
                updates["updated_at"] = timezone.now()
                Store.objects.using(database).filter(pk=store_id).update(**updates)

        refreshed_stores = list(
            Store.objects.using(database).select_related("seller", "seller__user").order_by("pk")
        )
        refreshed_sellers = {
            seller.pk: seller
            for seller in Seller.objects.using(database).select_related("user")
        }
        validation_errors = self.validate(refreshed_stores, sellers_by_id=refreshed_sellers)
        self.stdout.write(f"Tekshirilgan store qatorlari: {len(refreshed_stores)}")
        self.stdout.write(f"Yangilangan store qatorlari: {len(planned_updates)}")
        self.report_problems(problems)
        self.report_problems(validation_errors, heading="Qolgan validatsiya xatolari")

        if problems or validation_errors:
            raise CommandError(
                "Aniq seller mosligi bo‘lmagan yoki qarama-qarshi ma’lumotli qatorlar bor. "
                "Ularni taxminan to‘ldirmadim; ko‘rsatilgan Store ID’lari uchun tasdiqlangan "
                "--map-store STORE_ID=SELLER_ID qiymatini bering yoki source ma’lumotini tuzating."
            )

        self.stdout.write(self.style.SUCCESS("Barcha Store qatorlari email, seller_id va shop_code bo‘yicha to‘g‘ri."))

    @staticmethod
    def parse_mappings(raw_mappings, sellers_by_id):
        mappings = {}
        for value in raw_mappings:
            try:
                store_id_text, seller_id_text = value.split("=", 1)
                store_id, seller_id = int(store_id_text), int(seller_id_text)
            except (TypeError, ValueError):
                raise CommandError(f"Noto‘g‘ri mapping: {value!r}; format STORE_ID=SELLER_ID bo‘lsin.")
            if store_id in mappings:
                raise CommandError(f"Store #{store_id} bir nechta mappingda ko‘rsatilgan.")
            if seller_id not in sellers_by_id:
                raise CommandError(f"Seller #{seller_id} mavjud emas.")
            mappings[store_id] = seller_id
        return mappings

    @staticmethod
    def resolve_seller(store, product_seller_ids, explicit_mappings, sellers_by_id, sellers_by_name, sellers_by_email):
        explicit_seller_id = explicit_mappings.get(store.pk)
        if explicit_seller_id is not None:
            if store.seller_id and store.seller_id != explicit_seller_id:
                return None, f"mavjud seller_id {store.seller_id} explicit mapping bilan ziddiyatda."
            if product_seller_ids and product_seller_ids != {explicit_seller_id}:
                return None, (
                    f"explicit seller #{explicit_seller_id} mahsulot seller ID'lari "
                    f"{sorted(product_seller_ids)} bilan mos emas."
                )
            return sellers_by_id[explicit_seller_id], None

        if store.seller_id:
            return store.seller, None

        if len(product_seller_ids) == 1:
            seller_id = next(iter(product_seller_ids))
            return sellers_by_id[seller_id], None
        if len(product_seller_ids) > 1:
            return None, f"bir nechta product seller topildi: {sorted(product_seller_ids)}."

        name_matches = sellers_by_name.get(normalized(store.name), [])
        if len(name_matches) == 1:
            return name_matches[0], None
        if len(name_matches) > 1:
            return None, "store nomiga bir nechta seller mos keladi."

        if store.email:
            email_matches = sellers_by_email.get(normalized(store.email), [])
            if len(email_matches) == 1:
                return email_matches[0], None
            if len(email_matches) > 1:
                return None, "store emailiga bir nechta seller mos keladi."

        return None, "mavjud seller, product, nom yoki email bog‘lanishidan aniq seller topilmadi."

    @staticmethod
    def available_shop_code(store_id, reserved_codes):
        base_code = f"SHOP-{store_id:04d}"
        candidate = base_code
        suffix = 2
        while candidate in reserved_codes:
            candidate = f"{base_code}-{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def validate(stores, planned_updates=None, sellers_by_id=None):
        planned_updates = planned_updates or {}
        sellers_by_id = sellers_by_id or {}
        errors = []
        codes = defaultdict(list)
        emails = defaultdict(list)
        for store in stores:
            updates = planned_updates.get(store.pk, {})
            seller_id = updates.get("seller_id", store.seller_id)
            email = updates.get("email", store.email)
            shop_code = updates.get("shop_code", store.shop_code)
            if seller_id is None:
                errors.append(f"Store #{store.pk} ({store.name}): seller_id NULL.")
            seller = sellers_by_id.get(seller_id) if seller_id is not None else None
            if seller_id is not None and seller is None:
                errors.append(f"Store #{store.pk} ({store.name}): seller_id mavjud Seller’ga mos emas.")
            if not email:
                errors.append(f"Store #{store.pk} ({store.name}): email bo‘sh.")
            elif seller is not None and normalized(email) != normalized(
                store_email_for_seller(seller, store, shop_code)
            ):
                errors.append(f"Store #{store.pk} ({store.name}): email seller/store aliasiga mos emas.")
            elif email:
                emails[normalized(email)].append(store.pk)
            if not shop_code:
                errors.append(f"Store #{store.pk} ({store.name}): shop_code bo‘sh.")
            else:
                codes[shop_code].append(store.pk)

        for code, store_ids in codes.items():
            if len(store_ids) > 1:
                errors.append(f"shop_code {code!r} duplicate: Store ID’lari {store_ids}.")
        for email, store_ids in emails.items():
            if len(store_ids) > 1:
                errors.append(f"email {email!r} duplicate: Store ID’lari {store_ids}.")
        return errors

    def report_problems(self, problems, heading="Bog‘lanish muammolari"):
        if not problems:
            return
        self.stderr.write(self.style.WARNING(f"{heading}: {len(problems)}"))
        for problem in problems:
            self.stderr.write(f"  - {problem}")
