from django.contrib.admin.sites import AdminSite


class ZentoAdminSite(AdminSite):
    site_header = "Zento Global Administration"
    site_title = "Zento Admin"
    index_title = "Global Super Admin"

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser
