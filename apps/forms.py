import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import (
    Address, Brand, Category, ContactMessage, DeliveryPoint, ProductVariant,
    Review, Seller, SellerApplication, Store, User,
)


class EmailAuthenticationForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, label="Eslab qolish")

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].widget = forms.EmailInput(attrs={
            "class": "field",
            "placeholder": "siz@example.com",
            "autocomplete": "email",
            "autofocus": True,
        })
        self.fields["password"].label = "Parol"
        self.fields["password"].widget.attrs.update({
            "class": "field",
            "placeholder": "Parolingiz",
            "autocomplete": "current-password",
        })

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class UserRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="Ism")
    last_name = forms.CharField(max_length=150, label="Familiya")
    email = forms.EmailField(label="Email")
    phone = forms.CharField(max_length=30, label="Telefon")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_options = {
            "first_name": ("Aziza", "given-name"),
            "last_name": ("Karimova", "family-name"),
            "email": ("siz@example.com", "email"),
            "phone": ("+998 90 123 45 67", "tel"),
            "password1": ("Kamida 8 ta belgi", "new-password"),
            "password2": ("Parolni qayta kiriting", "new-password"),
        }
        for name, (placeholder, autocomplete) in field_options.items():
            self.fields[name].widget.attrs.update({
                "class": "field",
                "placeholder": placeholder,
                "autocomplete": autocomplete,
            })
        self.fields["password1"].label = "Parol"
        self.fields["password2"].label = "Parolni tasdiqlang"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Bu email bilan hisob allaqachon mavjud.")
        return email

    def clean_phone(self):
        phone = re.sub(r"[\s()\-]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"\+998\d{9}", phone):
            raise forms.ValidationError("Telefonni +998 90 123 45 67 formatida kiriting.")
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data["phone"]
        user.role = User.Role.CUSTOMER
        if commit:
            user.save()
        return user


class AdminUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
        )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone", "avatar")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "field", "autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"class": "field", "autocomplete": "family-name"}),
            "phone": forms.TextInput(attrs={"class": "field", "autocomplete": "tel"}),
            "avatar": forms.ClearableFileInput(attrs={"class": "field", "accept": "image/*"}),
        }

    def clean_phone(self):
        phone = re.sub(r"[\s()\-]", "", self.cleaned_data.get("phone", ""))
        if phone and not re.fullmatch(r"\+998\d{9}", phone):
            raise forms.ValidationError("Telefonni +998 90 123 45 67 formatida kiriting.")
        return phone


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ("title", "city", "street", "house_number", "phone", "is_default")
        widgets = {
            "title": forms.TextInput(attrs={"class": "field"}),
            "city": forms.TextInput(attrs={"class": "field"}),
            "street": forms.TextInput(attrs={"class": "field"}),
            "house_number": forms.TextInput(attrs={"class": "field"}),
            "phone": forms.TextInput(attrs={"class": "field", "autocomplete": "tel"}),
            "is_default": forms.CheckboxInput(),
        }

    def clean_phone(self):
        phone = re.sub(r"[\s()\-]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"\+998\d{9}", phone):
            raise forms.ValidationError("Telefonni +998 90 123 45 67 formatida kiriting.")
        return phone


class SellerApplicationForm(forms.ModelForm):
    class Meta:
        model = SellerApplication
        fields = ("full_name", "phone", "store_name", "category", "estimated_product_count")
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "field", "autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"class": "field", "autocomplete": "tel", "placeholder": "+998 90 123 45 67"}),
            "store_name": forms.TextInput(attrs={"class": "field"}),
            "category": forms.Select(attrs={"class": "field"}),
            "estimated_product_count": forms.NumberInput(attrs={"class": "field", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")

    def clean_phone(self):
        phone = re.sub(r"[\s()\-]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"\+998\d{9}", phone):
            raise forms.ValidationError("Telefonni +998 90 123 45 67 formatida kiriting.")
        return phone


class SellerProfileForm(forms.ModelForm):
    class Meta:
        model = Seller
        fields = ("store_name", "logo", "description", "address", "phone")
        widgets = {
            "store_name": forms.TextInput(attrs={"class": "field"}),
            "logo": forms.ClearableFileInput(attrs={"class": "field", "accept": "image/*"}),
            "description": forms.Textarea(attrs={"class": "field", "rows": 5}),
            "address": forms.TextInput(attrs={"class": "field"}),
            "phone": forms.TextInput(attrs={"class": "field", "autocomplete": "tel"}),
        }

    def clean_phone(self):
        phone = re.sub(r"[\s()\-]", "", self.cleaned_data.get("phone", ""))
        if phone and not re.fullmatch(r"\+998\d{9}", phone):
            raise forms.ValidationError("Telefonni +998 90 123 45 67 formatida kiriting.")
        return phone


class SuperAdminShopCreateForm(forms.Form):
    store_name = forms.CharField(max_length=255, label="Do‘kon nomi")
    description = forms.CharField(
        label="Tavsif",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    email = forms.EmailField(label="Shop admin emaili")
    phone = forms.CharField(max_length=30, label="Telefon", required=False)
    password = forms.CharField(
        min_length=8,
        label="Boshlang‘ich parol",
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field")

    def clean_store_name(self):
        name = self.cleaned_data["store_name"].strip()
        if Store.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError("Bu nomdagi do‘kon allaqachon mavjud.")
        return name

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Bu email bilan foydalanuvchi allaqachon mavjud.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        user = User(email=self.cleaned_data.get("email", ""))
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages)
        return password


class SuperAdminShopEditForm(forms.Form):
    store_name = forms.CharField(max_length=255, label="Do‘kon nomi")
    description = forms.CharField(
        label="Tavsif",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    admin_email = forms.EmailField(label="Admin login emaili")
    phone = forms.CharField(max_length=30, label="Telefon", required=False)
    store_is_active = forms.BooleanField(label="Do‘kon faol", required=False)
    admin_is_active = forms.BooleanField(label="Admin hisobi faol", required=False)
    new_password = forms.CharField(
        min_length=8,
        label="Yangi parol (ixtiyoriy)",
        required=False,
        widget=forms.PasswordInput,
    )

    def __init__(self, store, *args, **kwargs):
        self.store = store
        self.seller = store.seller
        self.admin_user = self.seller.user
        initial = kwargs.setdefault("initial", {})
        initial.update({
            "store_name": store.name,
            "description": store.description,
            "admin_email": self.admin_user.email,
            "phone": self.seller.phone,
            "store_is_active": store.is_active,
            "admin_is_active": self.admin_user.is_active,
        })
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field")

    def clean_store_name(self):
        name = self.cleaned_data["store_name"].strip()
        if Store.objects.filter(name__iexact=name).exclude(pk=self.store.pk).exists():
            raise forms.ValidationError("Bu nomdagi do‘kon allaqachon mavjud.")
        return name

    def clean_admin_email(self):
        email = self.cleaned_data["admin_email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.admin_user.pk).exists():
            raise forms.ValidationError("Bu email boshqa foydalanuvchiga tegishli.")
        return email

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password", "")
        if password:
            try:
                validate_password(password, self.admin_user)
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages)
        return password


class ProductCreateForm(forms.Form):
    name = forms.CharField(max_length=255, label="Mahsulot nomi")
    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        label="Kategoriya",
        empty_label="Kategoriyani tanlang",
    )
    brand = forms.CharField(max_length=100, label="Brend", required=False)
    price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Narxi (so'm)",
    )
    old_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        label="Eski narxi (so'm)",
        required=False,
    )
    stock = forms.IntegerField(min_value=0, label="Ombordagi soni")
    description = forms.CharField(label="Tavsif", required=False, widget=forms.Textarea(attrs={"rows": 5}))
    is_active = forms.BooleanField(label="Sotuvga chiqarish", required=False, initial=True)
    variants = forms.CharField(
        label="Variantlar",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text='Har bir variantni yangi qatorda yozing: Qora 128GB +0',
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("name")
        self.fields["brand"].widget.attrs["placeholder"] = "Masalan: Samsung"
        self.fields["variants"].widget.attrs["placeholder"] = "Qora 128GB +0\nKo‘k 256GB +500000"
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field")

    def clean_old_price(self):
        old_price = self.cleaned_data.get("old_price")
        price = self.cleaned_data.get("price")
        if old_price is not None and price is not None and old_price <= price:
            raise forms.ValidationError("Eski narx joriy narxdan katta bo‘lishi kerak.")
        return old_price

    def clean_variants(self):
        value = self.cleaned_data.get("variants", "")
        parsed = []
        for line in value.replace(",", "\n").splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.fullmatch(r"(.+?)\s*\+\s*([\d\s]+(?:[.,]\d{1,2})?)", line)
            if not match:
                raise forms.ValidationError(
                    "Variant formati noto‘g‘ri. Masalan: Qora 128GB +0"
                )
            name = match.group(1).strip()
            try:
                extra_price = Decimal(match.group(2).replace(" ", "").replace(",", "."))
            except InvalidOperation:
                raise forms.ValidationError("Variant qo‘shimcha narxi noto‘g‘ri.")
            if not name or extra_price < 0:
                raise forms.ValidationError("Variant nomi va narxi to‘g‘ri bo‘lishi kerak.")
            parsed.append((name, extra_price))
        if len({name.casefold() for name, _ in parsed}) != len(parsed):
            raise forms.ValidationError("Variant nomlari takrorlanmasligi kerak.")
        return parsed


class ProductUpdateForm(ProductCreateForm):
    """The product's core fields; variants are managed independently."""

    def __init__(self, *args, instance, **kwargs):
        self.instance = instance
        initial = kwargs.setdefault("initial", {})
        initial.update({
            "name": instance.name,
            "category": instance.category_id,
            "brand": instance.brand.name if instance.brand else "",
            "price": instance.price,
            "old_price": instance.old_price,
            "stock": instance.stock,
            "description": instance.description,
            "is_active": instance.is_active,
        })
        super().__init__(*args, **kwargs)
        self.fields.pop("variants")
class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ("name", "extra_price", "stock", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "field"}),
            "extra_price": forms.NumberInput(attrs={"class": "field", "min": 0}),
            "stock": forms.NumberInput(attrs={"class": "field", "min": 0}),
            "is_active": forms.CheckboxInput(),
        }


class CheckoutForm(forms.Form):
    DELIVERY_CHOICES = (
        ("pickup", "Topshirish punktidan olish"),
        ("address", "Kuryer orqali"),
    )
    PAYMENT_CHOICES = (
        ("card", "Karta orqali onlayn"),
        ("cash", "Yetkazilganda naqd"),
        ("installment", "Zento Pay — 12 oyga"),
    )

    first_name = forms.CharField(max_length=150, label="Ism")
    last_name = forms.CharField(max_length=150, label="Familiya")
    phone = forms.CharField(max_length=30, label="Telefon")
    email = forms.EmailField(label="Email")
    delivery_type = forms.ChoiceField(
        choices=DELIVERY_CHOICES,
        widget=forms.RadioSelect,
        label="Yetkazib berish usuli",
    )
    address = forms.ModelChoiceField(
        queryset=Address.objects.none(),
        required=False,
        empty_label="Mavjud manzilni tanlang",
        label="Saqlangan manzil",
    )
    city = forms.CharField(max_length=100, required=False, label="Shahar")
    street = forms.CharField(max_length=255, required=False, label="Ko‘cha")
    house_number = forms.CharField(max_length=30, required=False, label="Uy raqami")
    delivery_point = forms.ModelChoiceField(
        queryset=DeliveryPoint.objects.none(),
        required=False,
        empty_label="Topshirish punktini tanlang",
        label="Topshirish punkti",
    )
    payment_type = forms.ChoiceField(choices=PAYMENT_CHOICES, label="To‘lov usuli")
    notes = forms.CharField(
        required=False,
        label="Izoh",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["address"].queryset = Address.objects.filter(user=user).order_by("-is_default", "-updated_at")
        self.fields["delivery_point"].queryset = DeliveryPoint.objects.filter(is_active=True).order_by("name")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field")

    def clean_phone(self):
        phone = re.sub(r"[\s()\-]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"\+998\d{9}", phone):
            raise forms.ValidationError("Telefonni +998 90 123 45 67 formatida kiriting.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("delivery_type") == "pickup":
            if not cleaned.get("delivery_point"):
                self.add_error("delivery_point", "Topshirish punktini tanlang.")
            cleaned["delivery_fee"] = Decimal("0")
        elif not cleaned.get("address") and not (cleaned.get("city") and cleaned.get("street")):
            self.add_error("address", "Mavjud manzilni tanlang yoki yangi manzil kiriting.")
            cleaned["delivery_fee"] = Decimal("25000")
        else:
            cleaned["delivery_fee"] = Decimal("25000")
        return cleaned


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "text")
        widgets = {
            "rating": forms.Select(
                choices=[(value, f"{value} / 5") for value in range(1, 6)],
                attrs={"class": "field"},
            ),
            "text": forms.Textarea(attrs={"class": "field", "rows": 3}),
        }


class ReturnRequestForm(forms.Form):
    reason = forms.CharField(
        label="Qaytarish sababi",
        min_length=10,
        max_length=2000,
        widget=forms.Textarea(attrs={"class": "field", "rows": 4}),
    )


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("full_name", "email", "subject", "message")
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "field", "placeholder": "Ismingiz", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"class": "field", "placeholder": "siz@example.com", "autocomplete": "email"}),
            "subject": forms.Select(attrs={"class": "field"}),
            "message": forms.Textarea(attrs={"class": "field", "rows": 7, "placeholder": "Muammoni batafsil yozing"}),
        }

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if len(message) < 10:
            raise forms.ValidationError("Xabar kamida 10 ta belgidan iborat bo‘lishi kerak.")
        return message
