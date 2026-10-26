from os.path import splitext

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.fields import EmailField
from django.utils import timezone
from django.utils.text import slugify
from apps.managers import UserManager


def dated_media_upload_path(instance, filename):
    today = timezone.now()
    return f"{today:%Y/%m/%d}/{filename}"


def category_image_upload_path(instance, filename):
    extension = splitext(filename)[1].lower() or ".jpg"
    category_slug = slugify(instance.slug or instance.name)[:130] or "category"
    return f"categories/{category_slug}{extension}"


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Mijoz"
        SELLER = "seller", "Sotuvchi"

    username = None
    phone = models.CharField(max_length=30, blank=True)
    email = EmailField(unique=True)
    avatar = models.ImageField(upload_to=dated_media_upload_path, blank=True, null=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.get_full_name() or self.email


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SellerApplication(TimeStampedModel):
    """A customer's request to open a seller account.

    Keeping the application separate from ``Seller`` makes approval explicit: only
    approved applications create an active seller profile.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        APPROVED = "approved", "Tasdiqlandi"
        REJECTED = "rejected", "Rad etildi"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_applications")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    store_name = models.CharField(max_length=150)
    category = models.ForeignKey("Category", on_delete=models.SET_NULL, null=True, blank=True, related_name="seller_applications")
    estimated_product_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewer_note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="pending"),
                name="one_pending_seller_application_per_user",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.store_name} ({self.get_status_display()})"


class Seller(TimeStampedModel):
    class Meta:
        permissions = [
            ("manage_shop_dashboard", "Can access and manage the linked shop dashboard"),
        ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_profile")
    store_name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    logo = models.ImageField(upload_to=dated_media_upload_path, blank=True, null=True)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:
            self.code = f"SHOP-{self.pk:04d}"
            self.save(update_fields=["code", "updated_at"])

    @property
    def shop_is_active(self):
        shop = self.shop_store
        return self.is_active and shop is not None and shop.is_active

    @property
    def shop_store(self):
        stores = self.shop_stores.all()
        return (
            stores.filter(shop_code=self.code).first()
            or stores.filter(name=self.store_name).first()
            or (stores.first() if stores.count() == 1 else None)
        )

    def __str__(self):
        return self.store_name


class Category(TimeStampedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    store = models.ForeignKey(
        "Store",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="categories",
    )
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    image = models.ImageField(upload_to=category_image_upload_path, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Store(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    shop_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    seller = models.ForeignKey(
        Seller,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shop_stores",
    )

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
        if self.seller_id and not self.shop_code:
            preferred_code = self.seller.code or f"SHOP-{self.pk:04d}"
            self.shop_code = preferred_code
            suffix = 2
            while Store.objects.filter(shop_code=self.shop_code).exclude(pk=self.pk).exists():
                self.shop_code = f"SHOP-{self.pk:04d}-{suffix}"
                suffix += 1
            self.save(update_fields=["shop_code", "updated_at"])

    def __str__(self):
        return self.name


class Brand(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    logo = models.ImageField(upload_to=dated_media_upload_path, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        INACTIVE = "inactive", "Faol emas"
        OUT_OF_STOCK = "out_of_stock", "Tugagan"

    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, null=True, blank=True, related_name="products")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    sku = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    old_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return round((self.old_price - self.price) / self.old_price * 100)
        return 0

    @property
    def status(self):
        if not self.is_active:
            return self.Status.INACTIVE
        if self.stock == 0:
            return self.Status.OUT_OF_STOCK
        return self.Status.ACTIVE

    @property
    def status_display(self):
        return self.Status(self.status).label

    @property
    def installment_price(self):
        return self.price / 12

    def __str__(self):
        return self.name


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=120, help_text="Masalan: Qora, 8/256 GB yoki L o‘lcham")
    sku = models.CharField(max_length=100, unique=True)
    extra_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    @property
    def final_price(self):
        return self.product.price + self.extra_price

    @property
    def installment_price(self):
        return self.final_price / 12

    def __str__(self):
        return f"{self.product.name} — {self.name}"


class Cart(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "product", "variant"], name="unique_cart_product_variant")]


class Wishlist(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist_items")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_product")]


class Address(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    title = models.CharField(max_length=50, default="Uy")
    city = models.CharField(max_length=100)
    street = models.CharField(max_length=255)
    house_number = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=30)
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="unique_default_address_per_user",
            ),
        ]


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        CONFIRMED = "confirmed", "Qabul qilindi"
        PROCESSING = "processing", "Tayyorlanmoqda"
        SHIPPED = "shipped", "Yetkazib berilmoqda"
        READY_FOR_PICKUP = "ready_for_pickup", "Punktga yetib keldi"
        DELIVERED = "delivered", "Yetkazib berildi"
        CANCELLED = "cancelled", "Bekor qilingan"
        RETURNED = "returned", "Qaytarilgan"

    class DeliveryType(models.TextChoices):
        ADDRESS = "address", "Manzilga yetkazish"
        PICKUP = "pickup", "Topshirish punktidan olish"

    class PaymentType(models.TextChoices):
        CARD = "card", "Karta orqali"
        CASH = "cash", "Naqd pul"
        INSTALLMENT = "installment", "Muddatli to‘lov"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    order_number = models.CharField(max_length=30, unique=True)
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    delivery_point = models.ForeignKey(
        "DeliveryPoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    delivery_type = models.CharField(max_length=20, choices=DeliveryType.choices, default=DeliveryType.ADDRESS)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, default=PaymentType.CARD)
    notes = models.TextField(blank=True)


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    seller = models.ForeignKey(Seller, on_delete=models.PROTECT, related_name="order_items")
    product_name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    @property
    def subtotal(self):
        return self.price * self.quantity


class SellerOrder(TimeStampedModel):
    """A shop's independently managed fulfillment for one customer order."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="seller_orders")
    seller = models.ForeignKey(Seller, on_delete=models.PROTECT, related_name="seller_orders")
    status = models.CharField(max_length=20, choices=Order.Status.choices, default=Order.Status.NEW)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["order", "seller"], name="unique_seller_order_per_shop"),
        ]

    @property
    def items(self):
        return self.order.items.filter(seller_id=self.seller_id)

    def __str__(self):
        return f"{self.order.order_number} — {self.seller.store_name}"


class SellerOrderStatusHistory(models.Model):
    seller_order = models.ForeignKey(
        SellerOrder,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    old_status = models.CharField(max_length=20, choices=Order.Status.choices)
    new_status = models.CharField(max_length=20, choices=Order.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seller_order_status_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at", "pk"]


class Review(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "order", "product"],
                condition=models.Q(order__isnull=False),
                name="unique_review_per_order_product",
            ),
        ]


class ReturnRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Ko‘rib chiqilmoqda"
        APPROVED = "approved", "Qabul qilindi"
        REJECTED = "rejected", "Rad etildi"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="return_request")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="return_requests")
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)


class DeliveryPoint(TimeStampedModel):
    name = models.CharField(max_length=150)
    region = models.CharField(max_length=100, default="")
    city = models.CharField(max_length=100, default="")
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True)
    working_hours = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Payment(TimeStampedModel):
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="payment")
    provider = models.CharField(max_length=50)
    transaction_id = models.CharField(max_length=150, unique=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=30, default="pending")
    paid_at = models.DateTimeField(null=True, blank=True)


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, default="general")
    is_read = models.BooleanField(default=False)


class ContactMessage(TimeStampedModel):
    SUBJECT_CHOICES = (
        ("order", "Buyurtma bo‘yicha"),
        ("return", "Qaytarish"),
        ("seller", "Hamkorlik"),
        ("other", "Boshqa"),
    )

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=30, choices=SUBJECT_CHOICES, default="other")
    message = models.TextField()
    is_answered = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.full_name} — {self.subject}"


class Chat(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chats")
    seller = models.ForeignKey(Seller, on_delete=models.SET_NULL, null=True, blank=True, related_name="chats")
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="chats")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="chats")
    subject = models.CharField(max_length=200, blank=True)


class ChatMessage(TimeStampedModel):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_messages")
    text = models.TextField()
    is_read = models.BooleanField(default=False)
