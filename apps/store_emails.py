from django.utils.text import slugify


def store_email_for_seller(seller, store, shop_code=None):
    primary_store = seller.shop_store
    if primary_store and primary_store.pk == store.pk:
        return seller.user.email

    local, separator, domain = seller.user.email.rpartition("@")
    if not separator:
        return seller.user.email

    code = shop_code or store.shop_code or f"SHOP-{store.pk:04d}"
    tag = slugify(code) or f"shop-{store.pk}"
    local = local[: max(1, 64 - len(tag) - 1)]
    return f"{local}+{tag}@{domain}"
