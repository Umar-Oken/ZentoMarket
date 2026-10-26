from django.db import IntegrityError, transaction
from django.utils import timezone
import secrets

from .models import (
    Address,
    Cart,
    CartItem,
    Chat,
    ChatMessage,
    Category,
    Notification,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
    Seller,
    SellerOrder,
    SellerOrderStatusHistory,
    Store,
    User,
)


class CartError(Exception):
    """A user-facing cart business rule violation."""


class CheckoutError(Exception):
    """A user-facing checkout business rule violation."""


class OrderActionError(Exception):
    """A user-facing order action business rule violation."""


@transaction.atomic
def delete_store_preserving_history(store):
    seller = Seller.objects.select_for_update().filter(pk=store.seller_id).first()
    is_primary_shop = bool(seller and seller.shop_store and seller.shop_store.pk == store.pk)

    Product.objects.filter(store=store).update(store=None)
    Category.objects.filter(store=store).update(store=None)
    store.delete()

    if is_primary_shop:
        Seller.objects.filter(pk=seller.pk).update(is_active=False)
        User.objects.filter(pk=seller.user_id).update(is_active=False)


class CartService:
    @staticmethod
    def get_cart(user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    @staticmethod
    def _available_stock(product, variant):
        if (
            not product.is_active
            or not product.seller.shop_is_active
            or (variant and (not variant.is_active or variant.product_id != product.pk))
        ):
            raise CartError("Mahsulot yoki variant mavjud emas.")
        stock = product.stock
        if variant:
            stock = min(stock, variant.stock)
        if stock <= 0:
            raise CartError("Mahsulot qoldig‘i tugagan.")
        return stock

    @staticmethod
    def _product_quantity(cart, product_id, exclude_item_id=None):
        items = cart.items.filter(product_id=product_id)
        if exclude_item_id:
            items = items.exclude(pk=exclude_item_id)
        return sum(items.values_list("quantity", flat=True))

    @classmethod
    @transaction.atomic
    def add(cls, user, product_id, variant_id=None, quantity=1):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise CartError("Miqdor butun son bo‘lishi kerak.")
        if quantity < 1:
            raise CartError("Miqdor kamida 1 bo‘lishi kerak.")

        cart = cls.get_cart(user)
        try:
            product = Product.objects.select_for_update().get(pk=product_id)
        except (Product.DoesNotExist, TypeError, ValueError):
            raise CartError("Mahsulot topilmadi.")
        variant = None
        if variant_id:
            variant = ProductVariant.objects.select_for_update().filter(pk=variant_id).first()
            if not variant:
                raise CartError("Variant topilmadi.")
        limit = cls._available_stock(product, variant)
        item = (
            CartItem.objects.select_for_update()
            .filter(cart=cart, product=product, variant=variant)
            .first()
        )
        new_quantity = (item.quantity if item else 0) + quantity
        if new_quantity > limit or cls._product_quantity(cart, product.pk, item.pk if item else None) + new_quantity > product.stock:
            raise CartError(f"Qoldiqdan oshib bo‘lmaydi. Maksimal miqdor: {limit} dona.")

        if item:
            item.quantity = new_quantity
            item.save(update_fields=["quantity", "updated_at"])
        else:
            item = CartItem.objects.create(
                cart=cart,
                product=product,
                variant=variant,
                quantity=quantity,
                price=variant.final_price if variant else product.price,
            )
        return item

    @classmethod
    @transaction.atomic
    def set_quantity(cls, user, item_id, quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise CartError("Miqdor butun son bo‘lishi kerak.")
        if quantity < 1:
            raise CartError("Miqdor kamida 1 bo‘lishi kerak.")

        cart = cls.get_cart(user)
        try:
            item = (
                CartItem.objects.select_for_update()
                .get(cart=cart, pk=item_id)
            )
        except (CartItem.DoesNotExist, TypeError, ValueError):
            raise CartError("Savat qatori topilmadi.")
        item.product = Product.objects.select_for_update().get(pk=item.product_id)
        item.variant = (
            ProductVariant.objects.select_for_update().filter(pk=item.variant_id).first()
            if item.variant_id else None
        )
        limit = cls._available_stock(item.product, item.variant)
        if quantity > limit or cls._product_quantity(cart, item.product_id, item.pk) + quantity > item.product.stock:
            raise CartError(f"Qoldiqdan oshib bo‘lmaydi. Maksimal miqdor: {limit} dona.")
        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])
        return item

    @classmethod
    def remove(cls, user, item_id):
        cart = cls.get_cart(user)
        deleted, _ = cart.items.filter(pk=item_id).delete()
        if not deleted:
            raise CartError("Savat qatori topilmadi.")

    @classmethod
    def clear(cls, user):
        cls.get_cart(user).items.all().delete()

    @staticmethod
    def summary(cart):
        items = list(cart.items.select_related("product", "variant"))
        return items, sum(item.quantity for item in items), sum(
            item.price * item.quantity for item in items
        )


class CheckoutService:
    PAYMENT_STATES = {
        Order.PaymentType.CARD: ("demo_card", "demo_authorized"),
        Order.PaymentType.CASH: ("cash_on_delivery", "cash_pending"),
        Order.PaymentType.INSTALLMENT: ("zento_pay_demo", "installment_pending"),
    }

    @staticmethod
    def _order_number():
        return f"ZT-{secrets.token_hex(6).upper()}"

    @classmethod
    @transaction.atomic
    def place_order(cls, user, cleaned):
        cart = Cart.objects.select_for_update().get(user=user)
        cart_items = list(
            CartItem.objects.select_for_update()
            .filter(cart=cart)
            .order_by("product_id", "variant_id", "pk")
        )
        if not cart_items:
            raise CheckoutError("Savat bo‘sh. Buyurtma berish uchun mahsulot qo‘shing.")

        product_ids = sorted({item.product_id for item in cart_items})
        products = {
            product.pk: product
            for product in Product.objects.select_for_update()
            .select_related("seller")
            .filter(pk__in=product_ids)
        }
        variant_ids = sorted({item.variant_id for item in cart_items if item.variant_id})
        variants = {
            variant.pk: variant
            for variant in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids)
        }

        quantities_by_product = {}
        quantities_by_variant = {}
        total = 0
        for item in cart_items:
            product = products.get(item.product_id)
            variant = variants.get(item.variant_id) if item.variant_id else None
            if not product or not product.is_active:
                raise CheckoutError(f"{item.product.name} endi mavjud emas.")
            if item.variant_id and (
                not variant or not variant.is_active or variant.product_id != product.pk
            ):
                raise CheckoutError(f"{item.product.name} varianti endi mavjud emas.")

            available = product.stock
            if variant:
                available = min(available, variant.stock)
            if item.quantity > available:
                raise CheckoutError(
                    f"{product.name} uchun qoldiq yetarli emas. Mavjud: {available} dona."
                )
            quantities_by_product[product.pk] = quantities_by_product.get(product.pk, 0) + item.quantity
            if variant:
                quantities_by_variant[variant.pk] = quantities_by_variant.get(variant.pk, 0) + item.quantity
            current_price = variant.final_price if variant else product.price
            total += current_price * item.quantity

        for product_id, quantity in quantities_by_product.items():
            product = products[product_id]
            if quantity > product.stock:
                raise CheckoutError(
                    f"{product.name} uchun qoldiq yetarli emas. Mavjud: {product.stock} dona."
                )
        for variant_id, quantity in quantities_by_variant.items():
            variant = variants[variant_id]
            if quantity > variant.stock:
                raise CheckoutError(
                    f"{variant.name} varianti uchun qoldiq yetarli emas. Mavjud: {variant.stock} dona."
                )

        address = cleaned.get("address")
        if cleaned["delivery_type"] == Order.DeliveryType.ADDRESS and not address:
            address = Address.objects.create(
                user=user,
                title="Checkout",
                city=cleaned["city"],
                street=cleaned["street"],
                house_number=cleaned["house_number"],
                phone=cleaned["phone"],
                is_default=False,
            )
        delivery_point = cleaned.get("delivery_point")
        if cleaned["delivery_type"] == Order.DeliveryType.PICKUP:
            if not delivery_point or not delivery_point.is_active:
                raise CheckoutError("Tanlangan topshirish punkti mavjud emas.")
            address = None
        else:
            delivery_point = None

        order_data = {
            "user": user,
            "address": address,
            "delivery_point": delivery_point,
            "total": total + cleaned["delivery_fee"],
            "delivery_fee": cleaned["delivery_fee"],
            "delivery_type": cleaned["delivery_type"],
            "payment_type": cleaned["payment_type"],
            "notes": cleaned["notes"],
        }
        for _ in range(5):
            order_number = cls._order_number()
            try:
                with transaction.atomic():
                    order = Order.objects.create(order_number=order_number, **order_data)
                break
            except IntegrityError:
                if Order.objects.filter(order_number=order_number).exists():
                    continue
                raise
        else:
            raise CheckoutError("Buyurtma raqamini yaratib bo‘lmadi. Qayta urinib ko‘ring.")

        order_items = []
        for item in cart_items:
            product = products[item.product_id]
            variant = variants.get(item.variant_id) if item.variant_id else None
            price = variant.final_price if variant else product.price
            order_items.append(OrderItem(
                order=order,
                product=product,
                variant=variant,
                seller=product.seller,
                product_name=product.name,
                price=price,
                quantity=item.quantity,
            ))
        OrderItem.objects.bulk_create(order_items)
        SellerOrder.objects.bulk_create([
            SellerOrder(order=order, seller_id=seller_id)
            for seller_id in sorted({item.seller_id for item in order_items})
        ])

        for product_id, quantity in quantities_by_product.items():
            product = products[product_id]
            product.stock -= quantity
            product.save(update_fields=["stock", "updated_at"])
        for variant_id, quantity in quantities_by_variant.items():
            variant = variants[variant_id]
            variant.stock -= quantity
            variant.save(update_fields=["stock", "updated_at"])

        provider, status = cls.PAYMENT_STATES[cleaned["payment_type"]]
        Payment.objects.create(
            order=order,
            provider=provider,
            transaction_id=f"DEMO-{order_number}",
            amount=order.total,
            status=status,
            paid_at=timezone.now() if cleaned["payment_type"] == Order.PaymentType.CARD else None,
        )
        cart.items.all().delete()
        return order


class NotificationService:
    @staticmethod
    def create(user, title, message, notification_type="general"):
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        return Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
        )

    @staticmethod
    def unread_count(user):
        if user is None or not getattr(user, "is_authenticated", False):
            return 0
        return Notification.objects.filter(user=user, is_read=False).count()

    @staticmethod
    def mark_read(user, notification_id=None):
        if user is None or not getattr(user, "is_authenticated", False):
            return 0
        queryset = Notification.objects.filter(user=user)
        if notification_id is not None:
            queryset = queryset.filter(pk=notification_id)
        return queryset.update(is_read=True)

    @staticmethod
    def order_created(order):
        return NotificationService.create(
            order.user,
            "Buyurtma yaratildi",
            f"Buyurtma {order.order_number} muvaffaqiyatli yaratildi.",
            "order",
        )

    @staticmethod
    def order_status_changed(order, old_status):
        if old_status == order.status:
            return None
        return NotificationService.create(
            order.user,
            "Buyurtma holati o‘zgardi",
            f"Buyurtma {order.order_number} holati {order.get_status_display()} bo‘ldi.",
            "order",
        )

    @staticmethod
    def seller_application_submitted(application):
        return NotificationService.create(
            application.user,
            "Sotuvchi arizasi yuborildi",
            f"{application.store_name} do‘koni uchun arizangiz qabul qilindi.",
            "seller_application",
        )

    @staticmethod
    def seller_application_status_changed(application):
        return NotificationService.create(
            application.user,
            "Sotuvchi arizasi yangilandi",
            f"{application.store_name} do‘koni arizasi: {application.get_status_display()}.",
            "seller_application",
        )

    @staticmethod
    def review_created(review):
        title = "Sharh qoldirildi"
        message = f"{review.product.name} mahsuloti uchun sharhingiz saqlandi."
        return NotificationService.create(review.user, title, message, "review")

    @staticmethod
    def return_requested(return_request):
        return NotificationService.create(
            return_request.user,
            "Qaytarish so‘rovi yuborildi",
            f"Buyurtma {return_request.order.order_number} uchun qaytarish so‘rovi qabul qilindi.",
            "return",
        )


class ChatService:
    MAX_MESSAGE_LENGTH = 4000

    @staticmethod
    def get_user_chat(user, chat_id):
        return Chat.objects.filter(user=user, pk=chat_id).select_related("seller", "order", "product").first()

    @staticmethod
    def create_chat(user, subject="Zento yordam", seller=None, order=None, product=None):
        chat = Chat.objects.create(
            user=user,
            seller=seller,
            order=order,
            product=product,
            subject=subject or "Zento yordam",
        )
        return chat

    @staticmethod
    def send_message(chat, sender, text):
        text = text.strip()
        if not text:
            raise ValueError("Bo‘sh xabar yuborib bo‘lmaydi.")
        if len(text) > ChatService.MAX_MESSAGE_LENGTH:
            raise ValueError("Xabar 4000 belgidan oshmasligi kerak.")
        message = ChatMessage.objects.create(chat=chat, sender=sender, text=text)
        Chat.objects.filter(pk=chat.pk).update(updated_at=timezone.now())
        return message

    @staticmethod
    def mark_received_messages_read(chat, user):
        """Mark messages from the other participant as read for this chat owner."""
        return chat.messages.exclude(sender=user).filter(is_read=False).update(is_read=True)


class OrderService:
    CANCELLABLE_STATUSES = (Order.Status.NEW, Order.Status.CONFIRMED)

    @classmethod
    @transaction.atomic
    def cancel(cls, user, order_number):
        order = (
            Order.objects.select_for_update()
            .filter(user=user)
            .get(order_number=order_number)
        )
        if order.status not in cls.CANCELLABLE_STATUSES:
            raise OrderActionError("Bu statusdagi buyurtmani bekor qilib bo‘lmaydi.")
        if order.seller_orders.exclude(status__in=cls.CANCELLABLE_STATUSES).exclude(
            status=Order.Status.CANCELLED
        ).exists():
            raise OrderActionError("Kamida bitta do‘kon buyurtmasi allaqachon jo‘natilgan.")

        cancelled_seller_ids = order.seller_orders.filter(
            status=Order.Status.CANCELLED,
        ).values_list("seller_id", flat=True)
        items = list(
            order.items.exclude(seller_id__in=cancelled_seller_ids)
            .select_for_update()
            .order_by("product_id", "variant_id", "pk")
        )
        product_ids = sorted({item.product_id for item in items})
        products = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
        }
        variant_ids = sorted({item.variant_id for item in items if item.variant_id})
        variants = {
            variant.pk: variant
            for variant in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")
        }

        for item in items:
            product = products.get(item.product_id)
            if product:
                product.stock += item.quantity
                product.save(update_fields=["stock", "updated_at"])
            if item.variant_id and item.variant_id in variants:
                variant = variants[item.variant_id]
                variant.stock += item.quantity
                variant.save(update_fields=["stock", "updated_at"])

        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        for seller_order in order.seller_orders.exclude(status=Order.Status.CANCELLED):
            old_status = seller_order.status
            seller_order.status = Order.Status.CANCELLED
            seller_order.save(update_fields=["status", "updated_at"])
            SellerOrderStatusHistory.objects.create(
                seller_order=seller_order,
                old_status=old_status,
                new_status=seller_order.status,
                changed_by=user,
            )
        return order

    @classmethod
    @transaction.atomic
    def reorder(cls, user, order_number):
        order = Order.objects.filter(user=user).get(order_number=order_number)
        items = list(order.items.select_related("product", "variant").order_by("product_id", "variant_id", "pk"))
        added = []
        skipped = []

        for item in items:
            product = Product.objects.get(pk=item.product_id)
            variant = None
            if item.variant_id:
                variant = (
                    ProductVariant.objects
                    .filter(pk=item.variant_id, product_id=product.pk)
                    .first()
                )
            available = product.stock
            if variant:
                available = min(available, variant.stock)
            if (
                not product.is_active
                or not product.seller.shop_is_active
                or (item.variant_id and (not variant or not variant.is_active))
            ):
                available = 0

            quantity = min(item.quantity, available)
            if quantity < 1:
                skipped.append(item.product_name)
                continue
            try:
                CartService.add(user, product.pk, variant.pk if variant else None, quantity)
            except CartError:
                skipped.append(item.product_name)
            else:
                added.append(item.product_name)

        return added, skipped


class SellerOrderService:
    """Manage a shop's fulfillment status without exposing other shops' lines."""

    ALLOWED_TRANSITIONS = {
        Order.Status.NEW: (
            Order.Status.CONFIRMED,
            Order.Status.CANCELLED,
        ),
        Order.Status.CONFIRMED: (
            Order.Status.PROCESSING,
            Order.Status.CANCELLED,
        ),
        Order.Status.PROCESSING: (
            Order.Status.SHIPPED,
            Order.Status.CANCELLED,
        ),
        Order.Status.SHIPPED: (
            Order.Status.READY_FOR_PICKUP,
            Order.Status.DELIVERED,
            Order.Status.RETURNED,
        ),
        Order.Status.READY_FOR_PICKUP: (
            Order.Status.DELIVERED,
            Order.Status.RETURNED,
        ),
        Order.Status.DELIVERED: (Order.Status.RETURNED,),
    }

    @classmethod
    @transaction.atomic
    def update_status(cls, seller, order_number, new_status, changed_by=None):
        seller_order = SellerOrder.objects.select_for_update().filter(
            seller=seller,
            order__order_number=order_number,
            order__items__seller=seller,
        ).select_related("order").first()
        if seller_order is None:
            order = Order.objects.filter(
                order_number=order_number,
                items__seller=seller,
            ).distinct().first()
            if order is None:
                raise OrderActionError("Buyurtma topilmadi.")
            seller_ids = order.items.values_list("seller_id", flat=True).distinct()
            SellerOrder.objects.bulk_create(
                [
                    SellerOrder(order=order, seller_id=seller_id, status=order.status)
                    for seller_id in seller_ids
                ],
                ignore_conflicts=True,
            )
            seller_order = SellerOrder.objects.select_for_update().get(
                order=order,
                seller=seller,
            )
        if (
            new_status == Order.Status.READY_FOR_PICKUP
            and seller_order.order.delivery_type != Order.DeliveryType.PICKUP
        ):
            raise OrderActionError("Topshirish punktiga yetib kelish statusi faqat punkt buyurtmasi uchun ishlatiladi.")
        expected_statuses = cls.ALLOWED_TRANSITIONS.get(seller_order.status, ())
        if new_status not in expected_statuses:
            raise OrderActionError("Bu statusga o‘tish uchun ruxsat yo‘q.")

        if new_status == Order.Status.CANCELLED:
            cls._restore_stock(seller_order)

        old_status = seller_order.status
        seller_order.status = new_status
        seller_order.save(update_fields=["status", "updated_at"])
        SellerOrderStatusHistory.objects.create(
            seller_order=seller_order,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
        )
        cls._sync_order_status(seller_order.order)
        NotificationService.create(
            seller.user,
            "Buyurtma holati yangilandi",
            f"{order_number} buyurtmasi {seller_order.get_status_display()} holatiga o‘tkazildi.",
            "seller_order",
        )
        NotificationService.create(
            seller_order.order.user,
            "Buyurtma holati yangilandi",
            f"{seller_order.seller.store_name}: buyurtmangiz {seller_order.get_status_display().lower()}.",
            "order",
        )
        return seller_order

    @staticmethod
    def _restore_stock(seller_order):
        items = list(
            OrderItem.objects.select_for_update()
            .filter(order=seller_order.order, seller=seller_order.seller)
            .order_by("product_id", "variant_id", "pk")
        )
        product_ids = sorted({item.product_id for item in items})
        products = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
        }
        variant_ids = sorted({item.variant_id for item in items if item.variant_id})
        variants = {
            variant.pk: variant
            for variant in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")
        }
        for item in items:
            product = products.get(item.product_id)
            if product:
                product.stock += item.quantity
                product.save(update_fields=["stock", "updated_at"])
            variant = variants.get(item.variant_id)
            if variant:
                variant.stock += item.quantity
                variant.save(update_fields=["stock", "updated_at"])

    @staticmethod
    def _sync_order_status(order):
        statuses = list(order.seller_orders.values_list("status", flat=True))
        if not statuses:
            return

        active_statuses = [
            status for status in statuses
            if status not in (Order.Status.CANCELLED, Order.Status.RETURNED, Order.Status.DELIVERED)
        ]
        if active_statuses:
            status_order = (
                Order.Status.NEW,
                Order.Status.CONFIRMED,
                Order.Status.PROCESSING,
                Order.Status.SHIPPED,
                Order.Status.READY_FOR_PICKUP,
            )
            new_status = min(active_statuses, key=status_order.index)
        elif Order.Status.DELIVERED in statuses:
            new_status = Order.Status.DELIVERED
        elif Order.Status.RETURNED in statuses:
            new_status = Order.Status.RETURNED
        else:
            new_status = Order.Status.CANCELLED
        if order.status != new_status:
            order.status = new_status
            order.save(update_fields=["status", "updated_at"])


class AddressService:
    @staticmethod
    @transaction.atomic
    def save(user, address, cleaned_data):
        list(Address.objects.select_for_update().filter(user=user).values_list("pk", flat=True))
        address.user = user
        for field, value in cleaned_data.items():
            setattr(address, field, value)
        if address.is_default:
            Address.objects.filter(user=user).exclude(pk=address.pk).update(is_default=False)
        address.save()
        if not Address.objects.filter(user=user, is_default=True).exists():
            Address.objects.filter(user=user).exclude(pk=address.pk).update(is_default=False)
            Address.objects.filter(pk=address.pk).update(is_default=True)
        return address

    @staticmethod
    @transaction.atomic
    def delete(user, address_id):
        address = Address.objects.select_for_update().get(user=user, pk=address_id)
        was_default = address.is_default
        address.delete()
        if was_default:
            replacement = Address.objects.filter(user=user).order_by("-updated_at", "pk").first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=["is_default", "updated_at"])
