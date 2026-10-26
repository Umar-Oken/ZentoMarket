const $ = (s, c = document) => c.querySelector(s), $$ = (s, c = document) => [...c.querySelectorAll(s)];

const formatMoney = (value) => {
    const number = Number(value || 0);
    return `${number.toLocaleString('uz-UZ', { maximumFractionDigits: 0 })} so‘m`;
};

const updateVariantSelection = (button) => {
    const detail = button.closest('[data-product-detail]');
    if (!detail) return;
    const priceEl = detail.querySelector('[data-product-price]');
    const installmentEl = detail.querySelector('[data-installment-price]');
    const stockEl = detail.querySelector('[data-product-stock]');
    const hiddenInput = detail.querySelector('[data-selected-variant]');
    const actionButtons = $$('[data-purchase-action]', detail);

    const price = button.dataset.price;
    const installment = button.dataset.installment;
    const stock = Number(button.dataset.stock || 0);
    const variantId = button.dataset.variantId;

    if (priceEl) priceEl.textContent = formatMoney(price);
    if (installmentEl) installmentEl.textContent = `${formatMoney(installment).replace(' so‘m', '')} so‘mdan × 12 oy`;
    if (stockEl) stockEl.textContent = stock > 0 ? `${stock} dona` : 'sotuvda yo‘q';
    if (hiddenInput) hiddenInput.value = variantId || '';

    actionButtons.forEach((node) => {
        if (stock > 0) {
            node.disabled = false;
            node.setAttribute('aria-disabled', 'false');
            node.classList.remove('is-disabled');
        } else {
            node.disabled = true;
            node.setAttribute('aria-disabled', 'true');
            node.classList.add('is-disabled');
        }
    });

    $$('[data-product-variant]', detail).forEach((item) => {
        const isActive = item === button;
        item.classList.toggle('active', isActive);
        item.setAttribute('aria-pressed', String(isActive));
    });
};

$$('[data-product-variant]').forEach((button) => {
    button.addEventListener('click', () => updateVariantSelection(button));
});

$$('[data-purchase-action]').forEach((button) => {
    button.addEventListener('click', (event) => {
        if (button.getAttribute('aria-disabled') === 'true' || button.disabled) {
            event.preventDefault();
        }
    });
});

const updateWishlistButtons = (productId, isInWishlist) => {
    $$(`[data-wishlist][data-product-id="${productId}"]`).forEach((button) => {
        button.dataset.inWishlist = String(isInWishlist);
        button.textContent = isInWishlist ? '♥' : '♡';
        button.style.color = isInWishlist ? 'var(--hot)' : '';
    });
};

$$('[data-wishlist]').forEach(b => b.addEventListener('click', async (e) => {
    e.preventDefault();
    const productId = b.dataset.productId;

    try {
        const response = await fetch(`/wishlist/${productId}/toggle/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
            }
        });

        if (response.status === 401) {
            const data = await response.json().catch(() => ({}));
            window.location.href = data.login_url || '/login/?next=' + encodeURIComponent(window.location.href);
            return;
        }

        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            window.location.href = response.url || `/login/?next=${encodeURIComponent(window.location.href)}`;
            return;
        }
        const data = await response.json();
        if (data.success) {
            const newState = data.is_in_wishlist;
            updateWishlistButtons(productId, newState);
            toast(newState ? "Sevimlilarga qo'shildi" : "Sevimlilardan olib tashlandi");

            $$('[data-wishlist-count]').forEach((node) => node.textContent = data.wishlist_count);
            if (!newState && document.querySelector('[data-wishlist-page]')) {
                const card = b.closest('[data-wishlist-card]');
                card?.remove();
                const total = document.querySelector('[data-wishlist-total]');
                if (total) total.textContent = `${data.wishlist_count} ta mahsulot`;
                if (!data.wishlist_count) window.location.reload();
            }
        }
    } catch (error) {
        console.error('Wishlist error:', error);
        toast('Xatolik yuz berdi');
    }
}));

const updateCompareButtons = (productId, inCompare) => {
    $$(`[data-compare][data-product-id="${productId}"]`).forEach((button) => {
        button.dataset.inCompare = String(inCompare);
        button.textContent = inCompare ? 'Taqqoslashdan olib tashlash' : 'Taqqoslash';
    });
};

const postCompare = async (url, productId) => {
    const response = await fetch(url, {
        method: 'POST',
        headers: {'X-CSRFToken': getCookie('csrftoken'), 'X-Requested-With': 'XMLHttpRequest'},
        body: new URLSearchParams(productId ? {product_id: productId} : {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) throw new Error(data.error || 'Taqqoslashda xatolik yuz berdi');
    $$('[data-compare-count]').forEach((node) => node.textContent = data.compare_count);
    return data;
};

$$('[data-compare]').forEach((button) => button.addEventListener('click', async () => {
    const productId = button.dataset.productId;
    const inCompare = button.dataset.inCompare === 'true';
    button.disabled = true;
    try {
        await postCompare(inCompare ? '/compare/remove/' : '/compare/add/', productId);
        updateCompareButtons(productId, !inCompare);
        toast(inCompare ? 'Taqqoslashdan olib tashlandi' : 'Taqqoslashga qo‘shildi');
    } catch (error) {
        toast(error.message);
    } finally {
        button.disabled = false;
    }
}));

$$('[data-compare-remove]').forEach((button) => button.addEventListener('click', async () => {
    const productId = button.dataset.productId;
    try {
        await postCompare('/compare/remove/', productId);
        $$(`[data-compare-cell="${productId}"]`).forEach((cell) => cell.remove());
        updateCompareButtons(productId, false);
        if (!document.querySelector('[data-compare-cell]')) window.location.reload();
    } catch (error) {
        toast(error.message);
    }
}));

document.querySelector('[data-compare-clear]')?.addEventListener('click', async (event) => {
    event.currentTarget.disabled = true;
    try {
        await postCompare('/compare/clear/');
        window.location.reload();
    } catch (error) {
        event.currentTarget.disabled = false;
        toast(error.message);
    }
});

const postCart = async (url, values = {}) => {
    const response = await fetch(url, {
        method: 'POST',
        headers: {'X-CSRFToken': getCookie('csrftoken'), 'X-Requested-With': 'XMLHttpRequest'},
        body: new URLSearchParams(values),
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && data.login_url) {
        window.location.href = data.login_url;
        return null;
    }
    if (!response.ok || !data.success) throw new Error(data.error || 'Xatolik yuz berdi');
    $$('[data-cart-count]').forEach((node) => node.textContent = data.cart_count);
    return data;
};

$$('[data-cart]').forEach((button) => button.addEventListener('click', async () => {
    const detail = button.closest('[data-product-detail]');
    button.disabled = true;
    try {
        const data = await postCart('/cart/add/', {
            product_id: button.dataset.productId || detail?.dataset.productId,
            variant_id: detail?.querySelector('[data-selected-variant]')?.value || '',
            quantity: 1,
        });
        if (data) toast('Mahsulot savatga qo‘shildi');
    } catch (error) {
        toast(error.message);
    } finally {
        button.disabled = false;
    }
}));

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
$$('[data-cart-item]').forEach((item) => {
    const currentQuantity = () => Number(item.querySelector('[data-quantity]')?.textContent || 1);
    $$('[data-qty] button', item).forEach((button) => button.addEventListener('click', async () => {
        const quantity = currentQuantity() + (button.dataset.step === 'up' ? 1 : -1);
        if (quantity < 1) return;
        try {
            await postCart(item.dataset.updateUrl, {quantity});
            window.location.reload();
        } catch (error) {
            toast(error.message);
        }
    }));
    item.querySelector('[data-remove-item]')?.addEventListener('click', async () => {
        try {
            await postCart(item.dataset.removeUrl);
            window.location.reload();
        } catch (error) {
            toast(error.message);
        }
    });
});

document.querySelector('[data-clear-cart]')?.addEventListener('click', async (event) => {
    event.currentTarget.disabled = true;
    try {
        await postCart(event.currentTarget.dataset.clearUrl);
        window.location.reload();
    } catch (error) {
        event.currentTarget.disabled = false;
        toast(error.message);
    }
});

const checkoutForm = document.querySelector('[data-checkout-form]');
if (checkoutForm) {
    const deliveryFee = checkoutForm.querySelector('[data-delivery-fee]');
    const orderTotal = checkoutForm.querySelector('[data-order-total]');
    const pickupFields = checkoutForm.querySelector('[data-pickup-fields]');
    const addressFields = checkoutForm.querySelector('[data-address-fields]');
    const calculateSubtotal = () => {
        const items = checkoutForm.querySelectorAll('[data-checkout-item]');
        if (!items.length) return Number(orderTotal?.dataset.subtotal || 0);
        return [...items].reduce((sum, item) => (
            sum + Number(item.dataset.price || 0) * Number(item.dataset.quantity || 0)
        ), 0);
    };
    const updateDelivery = () => {
        const type = checkoutForm.querySelector('[data-delivery-type]:checked')?.value;
        const fee = type === 'address' ? 25000 : 0;
        const subtotal = calculateSubtotal();
        if (pickupFields) pickupFields.hidden = type !== 'pickup';
        if (addressFields) addressFields.hidden = type !== 'address';
        if (deliveryFee) deliveryFee.textContent = `${formatMoney(fee)}`;
        if (orderTotal) orderTotal.textContent = formatMoney(subtotal + fee);
    };
    checkoutForm.querySelectorAll('[data-delivery-type]').forEach((input) => {
        input.addEventListener('change', updateDelivery);
    });
    updateDelivery();
}
$('.chat-form')?.addEventListener('submit', e => {
    e.preventDefault();
    const i = $('input', e.currentTarget);
    if (!i.value.trim()) return;
    const d = document.createElement('div');
    d.className = 'msg me';
    d.textContent = i.value;
    $('.messages').append(d);
    i.value = '';
    $('.messages').scrollTop = $('.messages').scrollHeight
});
const mobileMenu = $('.mobile-menu');
const siteNavigation = $('#site-navigation');
mobileMenu?.addEventListener('click', () => {
    const expanded = mobileMenu.getAttribute('aria-expanded') === 'true';
    mobileMenu.setAttribute('aria-expanded', String(!expanded));
    mobileMenu.setAttribute('aria-label', expanded ? 'Menyuni ochish' : 'Menyuni yopish');
    document.querySelector('.header')?.classList.toggle('mobile-menu-open', !expanded);
    siteNavigation?.toggleAttribute('hidden', expanded);
});

function toast(t) {
    let e = $('.toast');
    if (!e) {
        e = document.createElement('div');
        e.className = 'toast';
        document.body.append(e)
    }
    e.textContent = t;
    e.classList.add('show');
    setTimeout(() => e.classList.remove('show'), 2200)
}
