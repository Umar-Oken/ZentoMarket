from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify

from .models import Order, OrderItem, ReturnRequest, Review, Seller, SellerApplication, SellerOrder, Store, User
from .services import NotificationService
from .store_emails import store_email_for_seller


SHOP_ADMIN_GROUP = "ShopAdmin"
SUPER_ADMIN_GROUP = "SuperAdmin"


def _shop_store_defaults(seller):
    base_name = seller.store_name.strip() or f"Shop {seller.pk}"
    name = base_name[:255]
    suffix = 2
    while Store.objects.filter(name__iexact=name).exclude(seller=seller).exists():
        tail = f" ({suffix})"
        name = f"{base_name[:255 - len(tail)]}{tail}"
        suffix += 1

    base_slug = slugify(name)[:160] or f"shop-{seller.pk}"
    slug = base_slug
    suffix = 2
    while Store.objects.filter(slug=slug).exclude(seller=seller).exists():
        tail = f"-{suffix}"
        slug = f"{base_slug[:170 - len(tail)]}{tail}"
        suffix += 1

    return {
        "name": name,
        "slug": slug,
        "description": seller.description,
        "email": seller.user.email,
        "is_active": seller.is_active,
    }


def _shop_admin_group(using="default"):
    group, _ = Group.objects.using(using).get_or_create(name=SHOP_ADMIN_GROUP)
    permission_codenames = (
        "manage_shop_dashboard",
        "view_product",
        "add_product",
        "change_product",
        "delete_product",
        "view_sellerorder",
        "change_sellerorder",
    )
    permissions = Permission.objects.using(using).filter(
        content_type__app_label="apps",
        codename__in=permission_codenames,
    )
    group.permissions.add(*permissions)
    return group


@receiver(post_migrate)
def provision_shop_admin_groups(sender, using, **kwargs):
    if sender.label != "apps":
        return
    group = _shop_admin_group(using)
    super_admin_group, _ = Group.objects.using(using).get_or_create(name=SUPER_ADMIN_GROUP)
    for seller in Seller.objects.using(using).select_related("user"):
        seller.user.groups.add(group)
    for superuser in User.objects.using(using).filter(is_superuser=True):
        superuser.groups.add(super_admin_group)


@receiver(post_save, sender=Seller)
def provision_seller_shop(sender, instance, **kwargs):
    defaults = _shop_store_defaults(instance)
    stores = Store.objects.using(instance._state.db).filter(seller=instance)
    store = stores.filter(shop_code=instance.code).first() or stores.filter(name=instance.store_name).first()
    if store is None:
        store = Store.objects.using(instance._state.db).create(seller=instance, **defaults)
        created = True
    else:
        created = False
    if not created:
        update_fields = []
        for field in ("name", "slug", "description", "email", "is_active"):
            value = defaults[field]
            if getattr(store, field) != value:
                setattr(store, field, value)
                update_fields.append(field)
        if update_fields:
            update_fields.append("updated_at")
            store.save(update_fields=update_fields)
    instance.user.groups.add(_shop_admin_group(instance._state.db))


@receiver(post_save, sender=User)
def sync_shop_admin_email(sender, instance, **kwargs):
    if instance.is_superuser:
        super_admin_group, _ = Group.objects.using(instance._state.db).get_or_create(name=SUPER_ADMIN_GROUP)
        instance.groups.add(super_admin_group)
    seller = Seller.objects.using(instance._state.db).filter(user=instance).first()
    if seller is None:
        return
    for store in Store.objects.using(instance._state.db).filter(seller=seller):
        email = store_email_for_seller(seller, store)
        if store.email != email:
            Store.objects.using(instance._state.db).filter(pk=store.pk).update(email=email)


@receiver(pre_save, sender=Order)
def remember_previous_order_status(sender, instance, **kwargs):
    """Keep the persisted status so every normal Order.save() is observable."""
    instance._previous_status = None
    if instance.pk:
        instance._previous_status = (
            sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )


@receiver(post_save, sender=Order)
def order_notification(sender, instance, created, **kwargs):
    if created:
        NotificationService.order_created(instance)
    elif instance._previous_status is not None:
        NotificationService.order_status_changed(instance, instance._previous_status)


@receiver(post_save, sender=OrderItem)
def create_seller_order(sender, instance, created, **kwargs):
    if created:
        SellerOrder.objects.get_or_create(
            order=instance.order,
            seller=instance.seller,
            defaults={"status": instance.order.status},
        )


@receiver(pre_save, sender=SellerApplication)
def remember_previous_application_status(sender, instance, **kwargs):
    instance._previous_status = None
    if instance.pk:
        instance._previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()


@receiver(post_save, sender=SellerApplication)
def seller_application_notification_and_approval(sender, instance, created, **kwargs):
    if created:
        NotificationService.seller_application_submitted(instance)
        return
    if instance._previous_status == instance.status:
        return
    NotificationService.seller_application_status_changed(instance)
    if instance.status == SellerApplication.Status.APPROVED:
        Seller.objects.get_or_create(
            user=instance.user,
            defaults={"store_name": instance.store_name, "phone": instance.phone},
        )
        if instance.user.role != User.Role.SELLER:
            instance.user.role = User.Role.SELLER
            instance.user.save(update_fields=["role"])


@receiver(post_save, sender=Review)
def review_created_notification(sender, instance, created, **kwargs):
    if created:
        NotificationService.review_created(instance)


@receiver(post_save, sender=ReturnRequest)
def return_requested_notification(sender, instance, created, **kwargs):
    if created:
        NotificationService.return_requested(instance)
