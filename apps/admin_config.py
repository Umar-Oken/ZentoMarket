from django.contrib.admin.apps import AdminConfig


class SuperuserAdminConfig(AdminConfig):
    default_site = "apps.admin_site.ZentoAdminSite"
