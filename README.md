# ZentoMarket

Django asosidagi marketplace demo loyihasi. Mahsulot katalogi, qidiruv va filterlar, wishlist/compare, savat, checkout, buyurtmalar, kabinet, chat va seller oqimlarini o‘z ichiga oladi.

## Ishga tushirish

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set a unique local-only demo password in .env before seeding.
python manage.py migrate
python manage.py seed_market
python manage.py seed_products
python manage.py download_category_images
python manage.py runserver
```

PostgreSQL sozlamalari `.env` orqali beriladi. Lokal testlar PostgreSQL talab qilmaydi:

```bash
make test
make check
```

`seed_market` demo foydalanuvchilarini yaratish uchun `.env` ichida `DEMO_PASSWORD`
qiymatini talab qiladi va production muhitida ishlamaydi. Bu demo hisoblar uchun
ishlatiladigan parolni ommaviy manba kodiga kiritmang yoki production’da qayta
ishlatmang.

## Environment variables

Lokal sozlamalar uchun `.env.example` faylini `.env` ga nusxalang. `.env` maxfiy
qiymatlar saqlashi mumkin: uni Git’ga qo‘shmang. `.env.example` esa qiymatsiz
namuna bo‘lib, repoda saqlanishi mumkin.

| O‘zgaruvchi | Vazifasi |
|---|---|
| `DJANGO_ENV` | `development` yoki `production` muhitini tanlaydi. |
| `SECRET_KEY` | Django maxfiy kaliti; production’da albatta alohida, tasodifiy qiymat bering. |
| `DEBUG` | Debug rejimi; production’da `false` bo‘lishi shart. |
| `ALLOWED_HOSTS` | Ruxsat berilgan host nomlari, vergul bilan ajratiladi. |
| `CSRF_TRUSTED_ORIGINS` | Zarur CSRF originlari, `https://` bilan va vergul bilan ajratib. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL ulanish sozlamalari; parol maxfiy. |
| `YANDEX_MAPS_API_KEY` | Xarita API kaliti; ishlatilmasa bo‘sh qoldiring va provayderda domen/API bo‘yicha cheklang. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Production SMTP sozlamalari; parol maxfiy. |
| `EMAIL_BACKEND`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT` | Email backend va transport sozlamalari. Production’da console backend ishlatilmaydi. |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` | HTTPS, cookie va HSTS himoyalari. Production defaultlari yoqilgan; TLS to‘g‘ri ishlashini tekshiring. |
| `DEMO_PASSWORD` | Faqat lokal `seed_market` uchun demo paroli; production’da ishlatilmaydi. |

Production konfiguratsiyasi misoli (maxfiy qiymatlarni faqat deploy platformasining
secret store’ida saqlang):

```dotenv
DJANGO_ENV=production
SECRET_KEY=<deployment-secret>
DEBUG=false
ALLOWED_HOSTS=shop.example.com
CSRF_TRUSTED_ORIGINS=https://shop.example.com
DB_NAME=<database-name>
DB_USER=<database-user>
DB_PASSWORD=<database-password>
DB_HOST=<database-host>
DB_PORT=5432
EMAIL_HOST=<smtp-host>
EMAIL_PORT=587
EMAIL_HOST_USER=<smtp-user>
EMAIL_HOST_PASSWORD=<smtp-password>
EMAIL_USE_TLS=true
```

## Production xavfsizlik sozlamalari

Production muhitida `DJANGO_ENV=production` ni belgilang va `SECRET_KEY` ni maxfiy
environment variable sifatida uzating. `SECRET_KEY` yo‘q bo‘lsa, ilova ishga
tushmaydi. `DEBUG=false` va faqat haqiqiy domenlardan iborat `ALLOWED_HOSTS`
majburiy; domenlar vergul bilan ajratiladi. Zarur bo‘lsa,
`CSRF_TRUSTED_ORIGINS` ga `https://` bilan boshlanadigan ishonchli originlarni
vergul bilan ajratib kiriting.

Production sozlamalari HTTPS redirect, secure session/CSRF cookie va bir yillik
HSTS ni yoqadi. Ularni faqat TLS production reverse-proxy yoki serverda to‘g‘ri
sozlanganidan keyin ishga tushiring. HSTS subdomainlari avtomatik yoqilmaydi;
barcha subdomainlar HTTPS ekanligi tasdiqlangandagina
`SECURE_HSTS_INCLUDE_SUBDOMAINS=true` ni belgilang. Production email uchun SMTP
sozlamalarini (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`) maxfiy muhit qiymatlari bilan bering;
console email backend productionda taqiqlangan, chunki u parol tiklash
havolalarini logga chiqarishi mumkin. TLS reverse-proxyda tugatilsa,
`SECURE_SSL_REDIRECT` bilan redirect loop bo‘lmasligi uchun proxy ishonchli
`X-Forwarded-Proto` qiymatini uzatishini alohida sozlang; Django proxy headerini
faqat ushbu headerni ishonchli proxy to‘liq boshqarganida qabul qilishi kerak.

Production sozlamalari bilan deployment tekshiruvi:

```bash
DJANGO_ENV=production DEBUG=false \
SECRET_KEY='deployment-secret-from-your-secret-manager' \
ALLOWED_HOSTS='shop.example.com' \
EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend' \
python manage.py check --deploy
```

Yuqoridagi buyruqdagi kalit namunaviy qiymat emas: uni buyruq satriga yozmang;
secret manager yoki deployment muhitidan oling. Repo tarixida ilgari commit
qilingan `.env` bo‘lsa, oddiy o‘chirish uni Git tarixidan olib tashlamaydi.
GitHub’ga yuborishdan oldin undagi amaldagi/reused parol va API kalitlarini
almashtiring. Tarixni qayta yozish hamkorlar bilan kelishilgan alohida amal
bo‘lib, bu loyiha tarixiga avtomatik o‘zgartirish kiritilmagan.

Pickup point map uses Yandex Maps JavaScript API 2.1. Create a browser-restricted
Yandex Maps API key and set it in `.env`:

```dotenv
YANDEX_MAPS_API_KEY=your_api_key_here
```

The key is exposed only to the pickup page because the Yandex JavaScript API
requires a public browser key. `SECRET_KEY` must remain private and must never
be used as the map key. If the variable is empty, the pickup page shows a
developer-friendly map configuration error instead of attempting to load a map.

`seed_market` demo katalog va foydalanuvchilarni yaratadi; demo login ma’lumotlari komandani ishga tushirganda konsolga chiqariladi. Haqiqiy karta to‘lovi amalga oshirilmaydi.

## Universal katalog

Universal katalog uchun quyidagi sahifalar mavjud:

* `/categories/` — barcha kategoriyalar
* `/categories/<slug>/` — kategoriya mahsulotlari
* `/stores/` — barcha do‘konlar
* `/stores/<slug>/` — do‘kon mahsulotlari
* `/products/` — barcha mahsulotlar
* `/products/<id>/` — mahsulot tafsilotlari

Demo kategoriyalar, do‘konlar va 60 ta mahsulotni idempotent tarzda qo‘shish:

```bash
python manage.py seed_products
```

Ushbu command rasmlar yuklamaydi va qayta ishlatilganda mavjud yozuvlarni yangilaydi.

Mahsulot katalogi product rasmlarisiz ishlaydi: product nomi, kategoriya,
tavsif, narx, qoldiq va variantlar orqali ko‘rsatiladi.

Kategoriyalarga Wikimedia Commons’dan mos, tayyor internet rasmlarini yuklash:

```bash
python manage.py download_category_images
```

Command mavjud category rasmlarini almashtirmaydi, har bir yangi rasmni
`media/categories/` ichiga saqlaydi, takroriy source URL ishlatmaydi va
topilmagan kategoriyalarni konsolda alohida chiqaradi. Saqlashdan oldin tekshirish:

```bash
python manage.py download_category_images --dry-run
```

Kategoriya nomiga mos mavjud rasmlarni ham qayta tekshirib almashtirish:

```bash
python manage.py download_category_images --replace-all
```

Faqat aniq kategoriyalarni yangilash uchun:

```bash
python manage.py download_category_images \
  --replace-all \
  --slugs poyabzallar,mebel,telefon-aksessuarlari
```

Bo‘sh bo‘lgan mavjud kategoriyalarni mahsulotlar bilan to‘ldirish uchun:

```bash
python manage.py seed_empty_category_products
```

Bu command mavjud kategoriyalar va do‘konlarni topadi, yangi kategoriya yoki do‘kon yaratmaydi,
rasm yuklamaydi va har bir ko‘rsatilgan kategoriyada kamida 5 ta mahsulot bo‘lishini ta’minlaydi.
Mahsulot kategoriya ichida nomi bilan tekshiriladi, shuning uchun command qayta ishlatilganda
duplicate yaratmaydi. Avvaldan 5 yoki undan ko‘p mahsulotga ega kategoriya o‘zgartirilmaydi.

Kategoriyalarni alohida do‘konlarga biriktirish va mavjud mahsulotlarning Store qiymatini
kategoriyasiga moslash:

```bash
python manage.py assign_category_stores
```

Command `Category.store` munosabatini o‘rnatadi, kerakli Zento do‘konlarini duplicate’siz
yaratadi va shu kategoriyadagi barcha mahsulotlarning `Product.store` qiymatini yangilaydi.

## Multi-vendor admin

`python manage.py migrate` migratsiyalari faqat mavjud `Seller` profillari uchun shop yozuvlarini
yaratadi va ularga unique `SHOP-<seller id>` code beradi. Katalogdagi mavjud `Store` yozuvlari
seller shop deb belgilanmaydi. Yangi shop va login hisoblarini faqat superuser yaratishi mumkin.

* `/super-admin/` — shop yaratish, tahrirlash, faollashtirish, admin email/parolini boshqarish,
  shop statistikasi va global Django Admin havolalari.
* `/admin/` — superuser uchun barcha shop, mahsulot, buyurtma va user boshqaruvi.
* `/seller/dashboard/` yoki `/seller-dashboard/` — faol shop adminining o‘z shop statistikasi.
* `/seller/products/`, `/seller/orders/`, `/seller/customers/` — faqat o‘z shop ma’lumotlari.

Shop adminlar email va parol bilan `/login/` orqali kiradi. Yangi hisob paroli Django parol
xeshlash tizimi bilan saqlanadi. Shop orderlari `SellerOrder` orqali seller bo‘yicha ajratiladi;
aralash savatdagi orderga bitta `Store` foreign key qo‘shilmaydi.
