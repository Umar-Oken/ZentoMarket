from .models import Cart, Category


def navigation_categories(request):
    cart_count = 0
    unread_notification_count = 0
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            cart_count = sum(
                item.quantity for item in cart.items.only("quantity")
            )
        unread_notification_count = request.user.notifications.filter(is_read=False).count()
    compare_items = request.session.get("compare_items", {})
    compare_product_ids = [
        int(product_id)
        for product_ids in compare_items.values()
        for product_id in product_ids
    ]
    wishlist_product_ids = list(
        request.user.wishlist_items.values_list("product_id", flat=True)
    ) if request.user.is_authenticated else []
    return {
        "navigation_categories": Category.objects.filter(
            is_active=True,
            parent__isnull=True,
        ).order_by("name")[:8],
        "cart_count": cart_count,
        "compare_count": len(compare_product_ids),
        "compare_product_ids": compare_product_ids,
        "wishlist_count": len(wishlist_product_ids),
        "wishlist_product_ids": wishlist_product_ids,
        "unread_notification_count": unread_notification_count,
    }
