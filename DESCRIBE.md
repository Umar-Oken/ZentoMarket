# ZentoMarket — loyiha tavsifi

Ushbu hujjat repositorydagi Django sozlamalari, modellar, view va URL kodlari,
template'lar, static fayllar hamda management command'larni ko‘rib chiqib
tayyorlandi. Unda hozir kodda mavjud bo‘lgan xatti-harakatlar tasvirlanadi;
README'dagi reja yoki demo matnlarining o‘zi amalga oshirilgan funksiya deb
qabul qilinmagan.

## 1. Loyiha nomi

**ZentoMarket** — Django asosida yaratilgan, o‘zbek tilidagi marketplace demo
loyihasi. Interfeys matnlari asosan o‘zbekcha, pul qiymatlari so‘mda
ko‘rsatiladi.

## 2. Loyiha maqsadi

Loyiha bitta saytda mahsulotlarni ko‘rish va qidirish, sotuvchilar va
do‘konlarni ko‘rsatish, savat va buyurtmalarni boshqarish, shuningdek
sotuvchilikka ariza berish va sotuvchilar uchun mahsulot/buyurtma boshqaruvini
namoyish etadi. Xaridor akkaunti, admin boshqaruvi va sotuvchi kabineti
alohida oqimlarga ega.

Bu production to‘lov platformasi emas: karta to‘lovi provayderiga real so‘rov
yuborilmaydi. To‘lov yozuvlari demo provider va holatlar bilan yaratiladi.

## 3. Ishlatilgan texnologiyalar

- **Python va Django 6.1** — server, ORM, autentifikatsiya, admin, formalar,
  session va HTML rendering.
- **PostgreSQL** — `root/settings.py` dagi asosiy DB backend;
  `psycopg2-binary` orqali ulanadi. DB sozlamalari `.env` dan olinadi.
- **SQLite** — `root/test_settings.py` da testlar uchun xotiradagi baza.
- **Django Templates** — frontend HTML va sahifa merosxo‘rligi.
- **Oddiy JavaScript va CSS** — `apps/static/apps/assets/` ichida.
- **Pillow** — `ImageField` rasmlari bilan ishlash uchun.
- **python-dotenv** — `.env` ni yuklash uchun.
- **Yandex Maps JavaScript API 2.1** — topshirish punktlari xaritasi uchun;
  browser API key `YANDEX_MAPS_API_KEY` muhit o‘zgaruvchisidan olinadi.
- **Email backend** — Django console backend; alohida SMTP xizmati
  sozlanmagan.

## 4. Loyiha strukturasi

```text
manage.py                   Django buyruqlarini ishga tushirish
root/
  settings.py               Django, database, templates, media va auth sozlamalari
  urls.py                   /admin/ va apps URL'larini ulash, xato sahifalari
  wsgi.py, asgi.py          WSGI/ASGI kirish nuqtalari
apps/
  models.py                 Marketplace va foydalanuvchi modellari
  views.py                  Sahifalar va HTTP endpoint'lar
  urls.py                   Ilova URL marshrutlari
  forms.py                  Ro‘yxatdan o‘tish, checkout, seller va boshqa formalar
  services.py               Savat, checkout, buyurtma, chat va manzil qoidalari
  signals.py                Buyurtma/ariza/review hodisalari va xabarnomalar
  admin.py                  Django admin ro‘yxatlari va konfiguratsiyasi
  managers.py               Email asosidagi User manager
  context_processors.py     Header navigatsiyasi uchun umumiy kontekst
  migrations/               0001–0017 ma’lumotlar sxemasi migratsiyalari
  management/commands/      Demo va katalog to‘ldirish buyruqlari
  static/apps/assets/       CSS, JavaScript va SVG placeholder'lar
  test_*.py, tests.py        Ilova testlari
templates/
  *.html                    Sahifa template'lari
  includes/                 Umumiy header, footer, karta va navigatsiya qismlari
  registration/             Parolni tiklash sahifalari va xat shabloni
media/                      Yuklangan foydalanuvchi va kategoriya rasmlari
requirements.txt            Python dependency'lari
Makefile                    Test, check, migration, seed va run target'lari
```

Template'lar `root/settings.py` orqali root `templates/` papkasidan,
`APP_DIRS=True` bilan yuklanadi. Static CSS va JavaScript `base.html` orqali
ulangan. `media/` fayllari `DEBUG=True` holatida root URL konfiguratsiyasidan
beriladi.

## 5. Asosiy Django app'lar

Loyihada bitta loyiha ichidagi asosiy Django ilova — **`apps`** mavjud.
`root` esa Django project konfiguratsiya paketi. `apps.apps.AppsConfig`
`ready()` ichida `signals` modulini yuklaydi.

`apps` katalogda katalog, akkaunt, buyurtma, chat, sotuvchi va admin
funksiyalari bir ilovada jamlangan; ular alohida Django app'larga bo‘linmagan.
Django'ning `admin`, `auth`, `contenttypes`, `sessions`, `messages` va
`staticfiles` ilovalari ham yoqilgan.

## 6. Ma’lumotlar bazasi va asosiy modellar

Asosiy sozlamada `django.db.backends.postgresql_psycopg2` ishlatiladi.
`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` `.env` orqali
beriladi. Migratsiyalar `apps/migrations/` ichida; test sozlamasi esa
`:memory:` SQLite ishlatadi.

Muhim modellar va ularning vazifalari:

- **User** — `AbstractUser` dan kengaytirilgan custom user; login maydoni
  email, email unique, `phone`, `avatar`, `role` (`customer`/`seller`)
  mavjud. `username` o‘chirilmagan; ro‘yxatdan o‘tishda email asosida unikal
  username yaratiladi.
- **SellerApplication**, **Seller** — sotuvchilikka ariza, review statusi va
  faollashtirilgan seller profili. Seller user'ga one-to-one bog‘langan.
- **Store**, **Category**, **Brand**, **Product**, **ProductVariant** —
  katalog, taxonomiya, brend, mahsulot va uning variantlari.
- **Cart**, **CartItem**, **Wishlist** — user savati (one-to-one), savat
  qatorlari va DB'da saqlanadigan sevimlilar.
- **Address**, **DeliveryPoint** — xaridor manzillari va olib ketish punktlari.
- **Order**, **OrderItem**, **Payment**, **ReturnRequest**, **Review** —
  buyurtma, buyurtma satri, demo to‘lov, qaytarish so‘rovi va sharh.
- **Notification** — user'ga bog‘langan o‘qilgan/o‘qilmagan xabarnomalar.
- **Chat**, **ChatMessage**, **ContactMessage** — yordam/sotuvchi chatlari,
  chat xabarlari va aloqa formasi murojaatlari.
- **TimeStampedModel** — ko‘plab modellarga `created_at` / `updated_at`
  qo‘shadigan abstract asosiy model.

Modellar foreign key va unique constraint'lar bilan bog‘langan. O‘chirish
qoidalarida `CASCADE`, `PROTECT` va `SET_NULL` qo‘llanadi. Masalan, buyurtma
foydalanuvchisi va buyurtma satridagi mahsulot himoyalanadi. Bir foydalanuvchi
uchun faqat bitta default manzil, savatda esa bir xil mahsulot/variant uchun
bitta qator bo‘lishi DB constraint'lari bilan ta’minlanadi.

## 7. Mahsulot va kategoriya tizimi

Category nomi, slug'i, tavsifi, rasmi, active holati, parent category'si va
ixtiyoriy Store aloqasiga ega. Bitta category ko‘plab mahsulotlarni o‘z ichiga
oladi; parent aloqasi orqali kategoriya daraxti tuziladi. Category slug'i
bo‘sh bo‘lsa, nomidan avtomatik yaratiladi.

Product seller va category'ga majburiy, Store va Brand'ga optional
bog‘lanadi. SKU va slug unique. Narx (`price`), eski narx (`old_price`),
qoldiq, tavsif va active holati saqlanadi. Eski narx joriy narxdan baland
bo‘lsa chegirma foizi hisoblanadi; installment qiymati narxni 12 ga bo‘lish
orqali ko‘rsatiladi.

`ProductVariant` mahsulotga tegishli nom, SKU, qo‘shimcha narx va alohida
qoldiq saqlaydi. Uning narxi `Product.price + extra_price`. Product modelida
rasm maydoni yo‘q; mahsulot sahifalari rasmga bog‘liq emas. Category rasmiga
`ImageField` bor, foydalanuvchi avatarlari, seller logosi va brand logosi ham
rasm maydonlariga ega. Yuklangan odatiy rasmlar sana papkalariga,
kategoriya rasmlari esa `media/categories/` ichiga saqlanadi.

Katalog sahifalarida faol category, product, brand va store'lar ko‘rsatiladi.
Kategoriya sahifasi o‘zining faol avlod kategoriyalaridagi mahsulotlarni ham
qamrab oladi. Qidiruv nom, tavsif, SKU, brand, category va seller nomi
bo‘yicha ishlaydi. Category, seller va qidiruv natijalarida brand, narx
oralig‘i, chegirma, reyting, mavjudlik filterlari, ommaboplik/narx/reyting/
yangilik bo‘yicha tartiblash va pagination mavjud. Ommaboplik buyurtmalar
soniga asoslanadi; bekor qilingan va qaytarilgan buyurtmalar hisoblanmaydi.
Mahsulot tafsilotida reyting, savdo soni, faol variantlar va shu kategoriyadagi
o‘xshash mahsulotlar ko‘rsatiladi.

## 8. Do‘konlar tizimi

**Store** — nom, slug va tavsifga ega katalog/do‘kon yozuvi. U Category va
Product bilan bog‘lanishi mumkin; bitta Store ko‘p category va product'ga ega
bo‘ladi. `/stores/` barcha do‘konlarni, `/stores/<slug>/` do‘konning faol
mahsulotlarini ko‘rsatadi.

**Seller** esa do‘kon profilidan alohida, foydalanuvchi bilan one-to-one
bog‘langan sotuvchi akkauntidir. Unda do‘kon nomi, logo, tavsif, manzil,
telefon, reyting, tasdiqlanganlik va faollik maydonlari bor. Mahsulot
Seller'ga majburiy biriktiriladi; Store aloqasi optional bo‘lgani uchun Seller
va Store bir xil tushuncha emas. Seller profilingiz sahifasi nom yoki ID
orqali ochilishi mumkin.

Mijoz `/sell/` sahifasidan sotuvchi arizasi yuboradi. Ariza admin tomonidan
tasdiqlanganda signal `Seller` profilini yaratadi (yoki mavjudini saqlaydi)
va user rolini `seller` qiladi. Faqat `seller` roli hamda faol Seller profili
bor user sotuvchi kabinetiga kira oladi.

## 9. Savat va buyurtma tizimi

Savat faqat tizimga kirgan user'lar uchun; `CartService` user'ga bitta Cart
yaratadi. Savatga mahsulot qo‘shish, miqdorni o‘zgartirish, qatorni o‘chirish
va savatni bo‘shatish POST endpoint'lari orqali bajariladi. Xizmat zaxira
tugagani, mahsulot/variant faol emasligi, variant mos kelmasligi yoki miqdor
zaxiradan oshib ketishini tekshiradi va JSON xatosini qaytaradi. Savat jami
serverda hisoblanadi. CartItem qo‘shilgan paytdagi narxni saqlaydi, ammo
checkout buyurtma narxini ayni vaqtdagi Product/Variant narxidan qayta
hisoblaydi.

Checkout bitta transaction ichida savat, mahsulot va variant qatorlarini
lock qilib, faollik va qoldiqni tekshiradi. Yetkazib berish topshirish
punktidan olish (0 so‘m) yoki manzilga yetkazish (25 000 so‘m) bo‘lishi mumkin.
Manzil avval saqlangani yoki checkout'da yangidan kiritilgani bo‘ladi.
To‘lov variantlari: karta, yetkazilganda naqd pul va demo installment.
Buyurtma va OrderItem qatorlari yaratiladi, qoldiq kamaytiriladi, demo Payment
yozuvi yaratiladi va Cart bo‘shatiladi. Karta holati `demo_authorized`,
boshqa variantlar esa demo kutilayotgan holatlarda saqlanadi. Tashqi to‘lov
integratsiyasi mavjud kodda yo‘q.

Order `new`, `confirmed`, `processing`, `shipped`, `delivered`, `cancelled`,
`returned` holatlariga ega. OrderItem buyurtma paytidagi mahsulot nomi va
narxini, miqdorini hamda seller aloqasini saqlaydi. Foydalanuvchi `new` yoki
`confirmed` buyurtmani bekor qilganda qoldiq tiklanadi; eski buyurtmani
savatga qayta qo‘shish mumkin, faol bo‘lmagan yoki qoldig‘i yetarli bo‘lmagan
mahsulotlar qo‘shilmaydi. Faqat yetkazilgan buyurtma uchun xarid tasdiqlangan
review va qaytarish so‘rovi yuborish mumkin. Bir orderdagi product uchun
bitta review, order uchun bitta qaytarish so‘rovi cheklovi bor.

DeliveryPoint nom, hudud/shahar, manzil, telefon, ish vaqti, koordinata va
active holatini saqlaydi. Pickup sahifasi qidiruv hamda hudud/shahar
filtrlarini taklif qiladi va koordinatali nuqtalarni Yandex xaritasiga uzatadi.

## 10. Foydalanuvchi imkoniyatlari

Saytga kiruvchi foydalanuvchi (xaridor) quyidagilarni qila oladi:

- ro‘yxatdan o‘tish, email bilan kirish/chiqish, parolni tiklash va
  almashtirish; profil, avatar, telefon va saqlangan manzillarni boshqarish;
- category, store va product kataloglarini ko‘rish, qidirish, filtrlash,
  tartiblash hamda mahsulot tavsifi, variant, qoldiq va sharhlarni ko‘rish;
- mahsulotlarni sevimlilarga qo‘shish va bir kategoriya doirasida to‘rttagacha
  mahsulotni taqqoslash (taqqoslash ro‘yxati session'da saqlanadi);
- savatni boshqarish, checkout qilish, yetkazish va demo to‘lov turini
  tanlash, buyurtmani tasdiqlash;
- o‘z buyurtmalarini holat/sana bo‘yicha filtrlash, tafsilotini ko‘rish,
  mumkin bo‘lsa bekor qilish yoki qayta buyurtma berish, yetkazilgandan
  keyin sharh va qaytarish so‘rovi yuborish;
- xabarnomalarni ko‘rish va bittasini yoki barchasini o‘qilgan deb belgilash;
- yordam chatini yaratish/xabar yuborish, mahsulot yoki buyurtmaga bog‘lash,
  aloqa formasini yuborish va FAQ ko‘rish;
- `/sell/` sahifasida sotuvchi bo‘lish uchun ariza yuborish.

Kirish talab qilinadigan harakatlar login sahifasiga yo‘naltiradi; ayrim
endpoint'lar obyekt egasini joriy user bilan tekshiradi.

## 11. Admin imkoniyatlari

Django admin `/admin/` manzilida. Custom UserAdmin email, ism, role, staff
va faollik bo‘yicha qidirish hamda filtrlash imkonini beradi. Admin'da
quyidagi modellar ro‘yxatdan o‘tkazilgan: User, SellerApplication, Seller,
Store, Category, Brand, Product, ProductVariant, Cart, CartItem, Wishlist,
Address, Order, OrderItem, Review, ReturnRequest, DeliveryPoint, Payment,
Notification, ContactMessage, Chat va ChatMessage.

Admin category rasmini preview qilish, slug boshqarish, product variantlari
va order item'larini inline ko‘rish, ro‘yxatlarni qidirish/filtrlash mumkin.
SellerApplication arizachiga tegishli maydonlar read-only; status kabi
maydonlarni admin o‘zgartira oladi. Status `approved` qilib saqlanganda signal
Seller profilini yaratib, user rolini `seller` qiladi. Order status
o‘zgarganda foydalanuvchiga notification yoziladi.

## 12. Frontend qismi

Frontend Django template'larida serverda render qilinadi; SPA framework yoki
frontend build pipeline dependency ko‘rinmaydi. `base.html` umumiy HTML
skeleti, CSS/JS ulanishi, topbar/header/footer va `content` block'ni beradi.
`includes/` ichida header, footer, topbar, account navigation, pagination,
product card va product filter qismlari bor.

`apps/static/apps/assets/css/style.css` asosiy stylesheet. `app.js` variant
tanlanganda narx/qoldiqni yangilash, wishlist va compare'ni fetch orqali
boshqarish, cart AJAX amallari, checkout yetkazish narxini hisoblash, mobil
menyu va toast xabarlariga javob beradi. Chat va map template'larida inline
JavaScript ham mavjud. Rasm uchun placeholder SVG'lar bor, ammo Product
modeli mahsulot rasmini saqlamaydi.

Sahifalar: bosh sahifa, katalog/category, do‘kon, qidiruv, mahsulot
tafsilotlari, cart/checkout, autentifikatsiya/account, buyurtmalar,
notification/chat, seller kabineti, yordam sahifalari va 403/404/500
template'lari. HTML fayllar `templates/` va uning ichki papkalarida.

## 13. Backend qismi

`root/urls.py` `/admin/` ni Django admin'ga, qolgan root URL'larni
`apps.urls` ga yo‘naltiradi. Marketplace view va endpoint'lar
`apps/views.py` da, form validatsiyalari `apps/forms.py` da. Kirish va seller
huquqlari `LoginRequiredMixin`, `@login_required`, `SellerRequiredMixin`
hamda POST-only decorator'lar orqali tekshiriladi.

`apps/services.py` CartService, CheckoutService, OrderService,
SellerOrderService, AddressService, ChatService va NotificationService
biznes qoidalarini jamlaydi. Checkout, qoldiq o‘zgarishi va seller order
statuslarini yangilash kabi amallarda transaction va row lock ishlatiladi.
Model signal'lari order yaratish/status o‘zgarishi, seller application
yuborish/tasdiqlash, review va return request uchun notification yaratadi.
Bu real-time WebSocket xabarlari emas; xabarlar DB'da saqlanadi.

`apps/context_processors.py` umumiy navigatsiyaga category, cart/wishlist/
compare soni va ID'lari hamda o‘qilmagan notification sonini uzatadi.
Application log'lari console'ga yoziladi. Contact view xabarni DB'ga
saqlaydi va Django console email backend orqali email yuborishga urinadi.

## 14. Loyihaning asosiy ishlash jarayoni

1. Django `.env` dan sozlamalarni olib, PostgreSQL ulanishi, custom User,
   template va media konfiguratsiyasini tayyorlaydi.
2. Foydalanuvchi katalog yoki qidiruvdan mahsulot topadi; filter va sort
   holati GET parameter'larida saqlanadi.
3. Wishlist va cart tegishli endpoint/service'lar orqali yangilanadi.
   Wishlist DB'da, compare category bo‘yicha guruhlangan holda session'da.
4. Kirgan user checkout formasini yuboradi. Server forma va qoldiqni
   tekshiradi; muvaffaqiyatda order, item va demo payment yaratib, qoldiqni
   yangilaydi va cart'ni bo‘shatadi.
5. User account'da order holatini kuzatadi va ruxsat berilgan amallarni
   bajaradi. Signal'lar order va boshqa hodisalar uchun notification yaratadi.
6. Admin seller application'ni ko‘rib chiqadi. Tasdiqlangan seller seller
   kabinetida profil, product, variant va o‘z buyurtmalarini boshqaradi.
   Seller order holatlari `new → confirmed → processing → shipped` tartibida
   o‘tadi; bir nechta seller qatnashgan order'ni bitta seller yangilay olmaydi.

## 15. Hozirda mavjud asosiy funksiyalar

URL, view va template kodlarida quyidagilar amalga oshirilgan:

- bosh sahifada category, chegirmali product, best seller va brand bo‘limlari;
  category/store/product ro‘yxatlari va tafsilot sahifalari;
- qidiruv, category/seller product filter'lari, sort va pagination;
- email orqali auth, registration, profil, password reset/change va address book;
- session compare, DB wishlist, cart AJAX API, checkout va order tarixi;
- pickup point qidiruvi/filterlari va koordinatali xarita;
- order cancel/reorder, yetkazilgan buyurtma review'i va return request;
- DB notification, chat yaratish/xabar yuborish, contact forma va FAQ;
- seller arizasi, dashboard, product/variant boshqaruvi va seller order
  holatini cheklangan tarzda yangilash;
- Django admin va 403/404/500 error template'lari.

`apps/management/commands/` ichidagi ma’lumot tayyorlash buyruqlari:
`seed_market`, `seed_products`, `seed_empty_category_products`,
`assign_category_stores`, `download_category_images` va
`seed_delivery_points`. Ular demo foydalanuvchi/ma’lumotlar, katalog,
do‘kon aloqalari, topshirish punktlari va category rasmlarini tayyorlaydi.
README'da `seed_products` 60 ta demo mahsulot yaratishi qayd etilgan;
mahsulot rasmlari emas, category rasmlari alohida yuklanadi.

## 16. Muhim bog‘lanishlar va dependencylar

- Product bitta Seller va Category'ga majburiy, Store va Brand'ga ixtiyoriy
  ulanadi. Category boshqa Category'ning child'i bo‘lishi va Store'ga
  ixtiyoriy ulanadi.
- ProductVariant Product'ga tegishli. CartItem Cart, Product va ixtiyoriy
  Variant'ni; OrderItem Order, Product, ixtiyoriy Variant va Seller'ni
  bog‘laydi.
- User bitta Cart hamda ko‘p Address, Order, Wishlist item, Notification va
  Chat'ga ega bo‘ladi. Seller profili User bilan one-to-one.
- Order user, ixtiyoriy Address yoki DeliveryPoint, bitta Payment va ko‘p
  OrderItem bilan bog‘langan. ReturnRequest Order'ga one-to-one; Review User,
  Product va ixtiyoriy Order'ga tegishli.
- Compare browser session'da; cart, wishlist, order, chat va notification
  ma’lumotlari database'da saqlanadi.
- `requirements.txt`: `Django>=6.1,<6.2`, `Pillow>=12.0`,
  `psycopg2-binary>=2.9`, `python-dotenv>=1.0`.
- Yandex Maps JavaScript API tashqi bog‘lanish hisoblanadi. Category rasm
  yuklovchi management command Wikimedia Commons'dan rasmlar qidirib oladi.

## 17. Loyihaning umumiy xulosasi

ZentoMarket — server-rendered Django marketplace demo bo‘lib, foydalanuvchi,
katalog, seller workflow, cart/checkout, order lifecycle, support va admin
qismlarini bitta `apps` Django ilovasida jamlaydi. Asosiy model aloqalari,
validatsiyalar hamda qoldiq/buyurtma jarayonlari kodda mavjud. Shu bilan
birga, haqiqiy payment gateway yoki SMTP xizmati, Product rasm modeli,
frontend SPA/framework ko‘rinmaydi; checkout'dagi to‘lov yozuvlari demo
holatlardir. Ushbu farqlar loyihaning hozirgi qamrovi va cheklovlarini
to‘g‘ri tushunishga yordam beradi.
