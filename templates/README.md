# Zento Marketplace templates

Marketplace sahifalari Django template inheritance asosida tuzilgan.

## Tuzilma

- `base.html` — umumiy HTML skeleti, CSS va JavaScript ulanishlari.
- `includes/` — topbar, header, footer va kabinet navigatsiyasi.
- Qolgan `.html` fayllar — faqat o‘z sahifasining `{% block content %}` qismi.
- Ichki havolalar Django `{% url %}` teglari orqali ishlaydi.
- Sahifalar hozircha `apps/urls.py` ichidagi `TemplateView` bilan ochiladi.

Loyihani Django server orqali ishga tushiring va bosh sahifa uchun `/` manzilini oching.

## Included pages

Home, catalog, category, search results, product details, seller store, compare, wishlist, cart, checkout, order success, sign in, sign up, password recovery, account dashboard, orders, order details, addresses, notifications, admin chat, pickup points, FAQ, contact and 404.
