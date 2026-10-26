"""
URL configuration for root project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.shortcuts import render
from django.urls import include, path
from django.conf.urls.static import static
import logging


logger = logging.getLogger(__name__)


def handler404(request, exception):
    logger.warning("404 for %s", request.get_full_path())
    return render(request, "404.html", status=404)


def handler500(request):
    logger.error("500 for %s", request.get_full_path())
    return render(request, "500.html", status=500)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
